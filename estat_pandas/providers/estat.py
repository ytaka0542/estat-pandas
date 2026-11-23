from __future__ import annotations

import os

import pandas as pd

from ..catalog import DatasetSpec
from ..errors import DataValidationError, ProviderError
from ..reader import EStatReader


_FREQUENCY_TO_ESTAT_PERIOD = {
    "monthly": "month",
    "quarterly": "quarter",
    "annual": "year",
    "fiscal_year": "fiscal_year",
}
_CLASSIFICATION_COLUMNS = {
    "area": ("cdArea", "@area"),
    "table": ("cdTab", "@tab"),
}


class EStatProvider:
    def fetch(
        self,
        dataset: DatasetSpec,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        if dataset.frequency not in _FREQUENCY_TO_ESTAT_PERIOD:
            raise DataValidationError(
                f"e-Stat does not support catalog frequency {dataset.frequency!r}"
            )
        api_key = os.environ.get("ESTAT_APP_ID")
        if not api_key:
            raise ProviderError(
                "ESTAT_APP_ID must be set to load an e-Stat dataset"
            )

        source = dataset.source
        try:
            reader = EStatReader(
                source["stats_data_id"],
                api_key=api_key,
                lang=source.get("lang", "jp"),
                start=start,
                end=end,
                expected_unit=dataset.unit,
                expected_period_type=_FREQUENCY_TO_ESTAT_PERIOD[dataset.frequency],
                timeout=source.get("timeout", 30),
                retry_count=source.get("retry_count", 3),
                **source["filters"],
            )
            frame = reader.read()
        except (ValueError, RuntimeError) as error:
            if isinstance(error, ProviderError):
                raise
            raise ProviderError(
                f"e-Stat failed to load dataset {dataset.key!r}: {error}"
            ) from error

        if frame.empty:
            raise ProviderError(f"e-Stat returned no observations for {dataset.key!r}")

        result = pd.DataFrame(
            {
                "DATE": frame["DATE"],
                "value": frame["$"],
                "series_code": source["stats_data_id"],
            }
        )
        for name, classification in dataset.classifications.items():
            if name.startswith("cat") and name[3:].isdigit():
                request_name = f"cdCat{int(name[3:]):02d}"
                response_column = f"@cat{int(name[3:]):02d}"
            else:
                request_name, response_column = _CLASSIFICATION_COLUMNS.get(
                    name, (None, None)
                )
            if request_name is None:
                continue
            if source["filters"].get(request_name) != classification["code"]:
                raise DataValidationError(
                    f"catalog classification {name!r} does not match "
                    f"the {request_name} filter"
                )
            label_column = f"{response_column[1:]}_label"
            if response_column not in frame or label_column not in frame:
                raise DataValidationError(
                    f"e-Stat response is missing classification {name!r}"
                )
            returned_codes = set(frame[response_column].dropna().astype(str))
            returned_labels = set(frame[label_column].dropna().astype(str))
            if returned_codes != {classification["code"]}:
                raise DataValidationError(
                    f"e-Stat returned unexpected codes for {name!r}: "
                    f"{sorted(returned_codes)}"
                )
            if returned_labels != {classification["label"]}:
                raise DataValidationError(
                    f"e-Stat label for {name!r} does not match catalog"
                )
            result[f"classification_{name}_code"] = frame[response_column].values
            result[f"classification_{name}_label"] = frame[label_column].values
        return result

