import math

import pandas as pd

from .catalog import DatasetSpec, get_dataset_spec
from .errors import DataValidationError, NoDataError
from .providers import BOJProvider, CSVProvider, EStatProvider


_PROVIDERS = {
    "estat": EStatProvider(),
    "boj": BOJProvider(),
    "csv": CSVProvider(),
}
_MISSING_VALUES = {"", "-", "－", "–", "—", "…", "...", "秘匿"}
_CANONICAL_COLUMNS = [
    "DATE",
    "value",
    "dataset_key",
    "provider",
    "series_code",
    "unit",
    "frequency",
    "seasonal_adjustment",
]


def _normalize_bound(value, name):
    if value is None:
        return None
    try:
        result = pd.Timestamp(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be a valid date") from error
    if pd.isna(result) or result.tz is not None:
        raise ValueError(f"{name} must be a valid timezone-naive date")
    return result


def _normalize_result(dataset, frame, start, end):
    if not isinstance(frame, pd.DataFrame):
        raise DataValidationError(
            f"{dataset.source['provider']} provider must return a DataFrame"
        )
    if not frame.columns.is_unique:
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains duplicate columns"
        )
    if frame.empty:
        raise NoDataError(f"dataset {dataset.key!r} returned no observations")
    if not {"DATE", "value"}.issubset(frame.columns):
        raise DataValidationError(
            f"provider result for {dataset.key!r} must include DATE and value"
        )

    result = frame.copy()
    try:
        dates = pd.to_datetime(result["DATE"], errors="coerce")
    except (TypeError, ValueError) as error:
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains invalid dates"
        ) from error
    if dates.isna().any():
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains invalid dates"
        )
    if dates.dt.tz is not None:
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains timezone-aware dates"
        )
    result["DATE"] = dates

    raw_values = result["value"]
    text_values = raw_values.astype("string").str.strip()
    missing = raw_values.isna() | text_values.isin(_MISSING_VALUES)
    numeric_values = pd.to_numeric(text_values.mask(missing), errors="coerce")
    invalid = ~missing & numeric_values.isna()
    if invalid.any():
        samples = sorted(text_values.loc[invalid].unique().tolist())[:5]
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains non-numeric values: "
            f"{samples}"
        )
    non_finite = numeric_values.map(
        lambda value: pd.notna(value) and not math.isfinite(float(value))
    )
    if non_finite.any():
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains infinite values"
        )
    result["value"] = numeric_values

    if "series_code" not in result:
        source = dataset.source
        series_code = source.get(
            "series_code", source.get("stats_data_id", dataset.key)
        )
        result["series_code"] = series_code
    result["series_code"] = result["series_code"].astype("string").str.strip()
    if result["series_code"].isna().any() or result["series_code"].eq("").any():
        raise DataValidationError(
            f"provider result for {dataset.key!r} contains a missing series code"
        )

    if start is not None:
        result = result.loc[result["DATE"] >= start]
    if end is not None:
        result = result.loc[result["DATE"] <= end]
    if result.empty:
        raise NoDataError(
            f"dataset {dataset.key!r} has no observations within the requested period"
        )

    duplicates = result.duplicated(["DATE", "series_code"], keep=False)
    if duplicates.any():
        raise DataValidationError(
            f"provider result for {dataset.key!r} has duplicate date/series rows"
        )

    result["dataset_key"] = dataset.key
    result["provider"] = dataset.source["provider"]
    result["unit"] = dataset.unit
    result["frequency"] = dataset.frequency
    result["seasonal_adjustment"] = dataset.seasonal_adjustment
    extra_columns = [column for column in result if column not in _CANONICAL_COLUMNS]
    result = result[_CANONICAL_COLUMNS + extra_columns]
    return result.sort_values(["DATE", "series_code"], kind="stable").reset_index(
        drop=True
    )


def load(dataset_key, start=None, end=None):
    """Load one explicitly cataloged dataset from its declared provider."""
    if not isinstance(dataset_key, str) or not dataset_key.strip():
        raise ValueError("dataset_key must be a non-empty string")
    spec: DatasetSpec = get_dataset_spec(dataset_key)
    start_bound = _normalize_bound(start, "start")
    end_bound = _normalize_bound(end, "end")
    if start_bound is not None and end_bound is not None and start_bound > end_bound:
        raise ValueError("start must be on or before end")

    provider = _PROVIDERS[spec.source["provider"]]
    observations = provider.fetch(spec, start_bound, end_bound)
    return _normalize_result(spec, observations, start_bound, end_bound)

