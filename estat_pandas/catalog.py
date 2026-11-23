from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .errors import CatalogError, DatasetNotFoundError


_CATALOG_PATH = Path(__file__).with_name("catalog.json")
_PROVIDERS = {"estat", "boj", "csv"}
_FREQUENCIES = {
    "daily",
    "monthly",
    "quarterly",
    "annual",
    "fiscal_year",
    "irregular",
}
_SEASONAL_ADJUSTMENTS = {
    "seasonally_adjusted",
    "not_seasonally_adjusted",
    "not_applicable",
}
_SOURCE_FIELDS = {
    "estat": {
        "required": {"provider"},
        "optional": {
            "stats_data_id",
            "filters",
            "segments",
            "lang",
            "timeout",
            "retry_count",
        },
    },
    "boj": {
        "required": {"provider", "db", "series_code"},
        "optional": {"lang", "layer", "timeout", "retry_count"},
    },
    "csv": {
        "required": {
            "provider",
            "url",
            "series_code",
            "date_column",
            "date_format",
            "value_column",
            "encoding",
            "delimiter",
        },
        "optional": {
            "skiprows",
            "thousands",
            "timeout",
            "retry_count",
            "classification_columns",
        },
    },
}


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    title: str
    source: dict[str, Any]
    unit: str
    frequency: str
    seasonal_adjustment: str
    classifications: dict[str, dict[str, str]]


def _require_string(value, field, context):
    if not isinstance(value, str) or not value.strip():
        raise CatalogError(f"{context}.{field} must be a non-empty string")


def _validate_estat_selection(stats_data_id, filters, classifications, context):
    _require_string(stats_data_id, "stats_data_id", context)
    if not isinstance(filters, dict) or not filters:
        raise CatalogError(f"{context}.filters must be a non-empty object")
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in filters.items()
    ):
        raise CatalogError(f"{context}.filters keys and values must be strings")

    filter_classifications = {
        "cdArea": "area",
        "cdTab": "table",
        **{
            f"cdCat{number:02d}": f"cat{number:02d}"
            for number in range(1, 16)
        },
    }
    for parameter, name in filter_classifications.items():
        if parameter not in filters:
            continue
        classification = classifications.get(name)
        if classification is None:
            raise CatalogError(
                f"{context}.classifications.{name} is required by "
                f"filter {parameter}"
            )
        if classification["code"] != filters[parameter]:
            raise CatalogError(
                f"{context}.classifications.{name}.code must match "
                f"filters.{parameter}"
            )


def _validate_estat_segments(segments, frequency, context):
    if not isinstance(segments, list) or not segments:
        raise CatalogError(f"{context}.segments must be a non-empty array")

    previous_end = None
    for index, segment in enumerate(segments):
        segment_context = f"{context}.segments[{index}]"
        required = {
            "stats_data_id",
            "filters",
            "start",
            "end",
            "classifications",
        }
        if not isinstance(segment, dict) or set(segment) != required:
            raise CatalogError(
                f"{segment_context} must contain {sorted(required)} only"
            )
        classifications = segment["classifications"]
        if not isinstance(classifications, dict):
            raise CatalogError(
                f"{segment_context}.classifications must be an object"
            )
        for name, classification in classifications.items():
            if (
                not isinstance(name, str)
                or not isinstance(classification, dict)
                or set(classification) != {"code", "label"}
            ):
                raise CatalogError(
                    f"{segment_context}.classifications has an invalid entry"
                )
            _require_string(
                classification["code"], "code", f"{segment_context}.{name}"
            )
            _require_string(
                classification["label"], "label", f"{segment_context}.{name}"
            )
        _validate_estat_selection(
            segment["stats_data_id"],
            segment["filters"],
            classifications,
            segment_context,
        )

        start_value = segment["start"]
        end_value = segment["end"]
        try:
            start_date = date.fromisoformat(start_value)
            end_date = date.fromisoformat(end_value) if end_value is not None else None
        except (TypeError, ValueError) as error:
            raise CatalogError(
                f"{segment_context}.start and end must be ISO dates"
            ) from error
        if start_date.isoformat() != start_value or (
            end_value is not None and end_date.isoformat() != end_value
        ):
            raise CatalogError(
                f"{segment_context}.start and end must use YYYY-MM-DD format"
            )
        if end_date is not None and start_date > end_date:
            raise CatalogError(f"{segment_context}.start must not follow end")
        if previous_end is None and index > 0:
            raise CatalogError("only the final e-Stat segment may have an open end")
        if previous_end is not None and start_date <= previous_end:
            raise CatalogError("e-Stat segments must be ordered and non-overlapping")
        if previous_end is not None and frequency == "monthly":
            next_month = previous_end.month % 12 + 1
            next_year = previous_end.year + (previous_end.month == 12)
            if start_date != date(next_year, next_month, 1):
                raise CatalogError("monthly e-Stat segments must be contiguous")
        if frequency == "monthly" and (
            start_date.day != 1
            or (end_date is not None and end_date.day != 1)
        ):
            raise CatalogError(
                f"{segment_context} monthly bounds must be first-of-month dates"
            )
        previous_end = end_date


def _validate_dataset(key, raw):
    context = f"datasets.{key}"
    if not isinstance(key, str) or not key.strip():
        raise CatalogError("dataset keys must be non-empty strings")
    if not isinstance(raw, dict):
        raise CatalogError(f"{context} must be an object")

    required = {
        "title",
        "source",
        "unit",
        "frequency",
        "seasonal_adjustment",
        "classifications",
    }
    missing = required - set(raw)
    extra = set(raw) - required
    if missing or extra:
        raise CatalogError(
            f"{context} fields mismatch "
            f"(missing={sorted(missing)}, unexpected={sorted(extra)})"
        )

    _require_string(raw["title"], "title", context)
    _require_string(raw["unit"], "unit", context)
    if not isinstance(raw["frequency"], str) or raw["frequency"] not in _FREQUENCIES:
        raise CatalogError(
            f"{context}.frequency must be one of {sorted(_FREQUENCIES)}"
        )
    if (
        not isinstance(raw["seasonal_adjustment"], str)
        or raw["seasonal_adjustment"] not in _SEASONAL_ADJUSTMENTS
    ):
        raise CatalogError(
            f"{context}.seasonal_adjustment must be one of "
            f"{sorted(_SEASONAL_ADJUSTMENTS)}"
        )
    classifications = raw["classifications"]
    if not isinstance(classifications, dict):
        raise CatalogError(f"{context}.classifications must be an object")
    for name, classification in classifications.items():
        if not isinstance(name, str) or not isinstance(classification, dict):
            raise CatalogError(f"{context}.classifications has an invalid entry")
        if set(classification) != {"code", "label"}:
            raise CatalogError(
                f"{context}.classifications.{name} must contain code and label"
            )
        _require_string(classification["code"], "code", f"{context}.{name}")
        _require_string(classification["label"], "label", f"{context}.{name}")

    source = raw["source"]
    if not isinstance(source, dict):
        raise CatalogError(f"{context}.source must be an object")
    provider = source.get("provider")
    if not isinstance(provider, str) or provider not in _PROVIDERS:
        raise CatalogError(
            f"{context}.source.provider must be one of {sorted(_PROVIDERS)}"
        )
    source_fields = _SOURCE_FIELDS[provider]
    missing = source_fields["required"] - set(source)
    extra = set(source) - source_fields["required"] - source_fields["optional"]
    if missing or extra:
        raise CatalogError(
            f"{context}.source fields mismatch "
            f"(missing={sorted(missing)}, unexpected={sorted(extra)})"
        )
    for field in ("timeout", "retry_count"):
        if field in source and (
            not isinstance(source[field], int)
            or isinstance(source[field], bool)
            or source[field] < 0
        ):
            raise CatalogError(f"{context}.source.{field} must be a non-negative integer")
    if "timeout" in source and source["timeout"] == 0:
        raise CatalogError(f"{context}.source.timeout must be greater than zero")

    if provider == "estat":
        has_single_selection = "stats_data_id" in source or "filters" in source
        if "segments" in source:
            if has_single_selection:
                raise CatalogError(
                    f"{context}.source must use either filters or segments"
                )
            if classifications:
                raise CatalogError(
                    f"{context}.classifications must be empty for segmented "
                    "e-Stat sources"
                )
            _validate_estat_segments(
                source["segments"], raw["frequency"], f"{context}.source"
            )
        else:
            if not {"stats_data_id", "filters"}.issubset(source):
                raise CatalogError(
                    f"{context}.source must contain stats_data_id and filters "
                    "or segments"
                )
            _validate_estat_selection(
                source["stats_data_id"],
                source["filters"],
                classifications,
                f"{context}.source",
            )
        lang = source.get("lang", "jp")
        if not isinstance(lang, str) or lang not in {"jp", "en"}:
            raise CatalogError(f"{context}.source.lang must be 'jp' or 'en'")
    elif provider == "boj":
        _require_string(source["db"], "db", context)
        _require_string(source["series_code"], "series_code", context)
        lang = source.get("lang", "jp")
        if not isinstance(lang, str) or lang not in {"jp", "en"}:
            raise CatalogError(f"{context}.source.lang must be 'jp' or 'en'")
        database_classification = classifications.get("database")
        if (
            database_classification is not None
            and database_classification["code"] != source["db"]
        ):
            raise CatalogError(
                f"{context}.classifications.database.code must match source.db"
            )
        series_classification = classifications.get("series")
        if (
            series_classification is not None
            and series_classification["code"] != source["series_code"]
        ):
            raise CatalogError(
                f"{context}.classifications.series.code must match "
                "source.series_code"
            )
    else:
        _require_string(source["url"], "url", context)
        _require_string(source["series_code"], "series_code", context)
        parsed_url = urlparse(source["url"])
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise CatalogError(f"{context}.source.url must use HTTPS")
        for field in (
            "date_column",
            "date_format",
            "value_column",
            "encoding",
            "delimiter",
        ):
            _require_string(source[field], field, context)
        if "skiprows" in source and (
            not isinstance(source["skiprows"], int)
            or isinstance(source["skiprows"], bool)
            or source["skiprows"] < 0
        ):
            raise CatalogError(f"{context}.source.skiprows must be a non-negative integer")
        if "thousands" in source:
            _require_string(source["thousands"], "thousands", context)
        classification_columns = source.get("classification_columns", {})
        if not isinstance(classification_columns, dict) or any(
            not isinstance(name, str)
            or not isinstance(column, str)
            or not column.strip()
            for name, column in classification_columns.items()
        ):
            raise CatalogError(
                f"{context}.source.classification_columns must map names to columns"
            )
        if set(classification_columns) != set(raw["classifications"]):
            raise CatalogError(
                f"{context}.source.classification_columns must map every "
                "catalog classification"
            )

    return DatasetSpec(
        key=key,
        title=raw["title"],
        source=source,
        unit=raw["unit"],
        frequency=raw["frequency"],
        seasonal_adjustment=raw["seasonal_adjustment"],
        classifications=classifications,
    )


def validate_catalog(catalog):
    if not isinstance(catalog, dict) or set(catalog) != {
        "schema_version",
        "datasets",
    }:
        raise CatalogError("catalog must contain schema_version and datasets only")
    if (
        not isinstance(catalog["schema_version"], int)
        or isinstance(catalog["schema_version"], bool)
        or catalog["schema_version"] != 1
    ):
        raise CatalogError("unsupported catalog schema_version")
    datasets = catalog["datasets"]
    if not isinstance(datasets, dict) or not datasets:
        raise CatalogError("catalog.datasets must be a non-empty object")
    return {
        key: _validate_dataset(key, definition)
        for key, definition in datasets.items()
    }


def load_catalog(path=None):
    catalog_path = Path(path) if path is not None else _CATALOG_PATH
    try:
        with catalog_path.open(encoding="utf-8") as file:
            catalog = json.load(file)
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"cannot read catalog {catalog_path}: {error}") from error
    return validate_catalog(catalog)


def get_dataset_spec(dataset_key, catalog_path=None):
    datasets = load_catalog(catalog_path)
    try:
        return datasets[dataset_key]
    except KeyError as error:
        raise DatasetNotFoundError(
            f"dataset key is not registered: {dataset_key!r}"
        ) from error
