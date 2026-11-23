from __future__ import annotations

from io import BytesIO

import pandas as pd

from ..catalog import DatasetSpec
from ..errors import ProviderError
from .http import get_response


class CSVProvider:
    def fetch(
        self,
        dataset: DatasetSpec,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        source = dataset.source
        response = get_response(
            source["url"],
            params=None,
            timeout=source.get("timeout", 30),
            provider="official CSV",
            retry_count=source.get("retry_count", 1),
        )
        classification_columns = source.get("classification_columns", {})
        try:
            frame = pd.read_csv(
                BytesIO(response.content),
                sep=source["delimiter"],
                encoding=source["encoding"],
                skiprows=source.get("skiprows", 0),
                thousands=source.get("thousands"),
                dtype={column: "string" for column in classification_columns.values()},
            )
        except (UnicodeError, ValueError, pd.errors.ParserError) as error:
            raise ProviderError(
                f"official CSV could not be parsed for {dataset.key!r}"
            ) from error

        date_column = source["date_column"]
        value_column = source["value_column"]
        missing_columns = {date_column, value_column} - set(frame.columns)
        if missing_columns:
            raise ProviderError(
                f"official CSV is missing configured columns: "
                f"{sorted(missing_columns)}"
            )
        for name, classification in dataset.classifications.items():
            column = classification_columns[name]
            if column not in frame:
                raise ProviderError(
                    f"official CSV is missing configured classification column "
                    f"{column!r}"
                )
            frame = frame.loc[
                frame[column].astype("string").str.strip() == classification["code"]
            ].copy()
            if frame.empty:
                raise ProviderError(
                    f"official CSV has no rows for classification {name!r}="
                    f"{classification['code']!r}"
                )
        try:
            dates = pd.to_datetime(
                frame[date_column],
                format=source["date_format"],
                errors="raise",
            )
        except (TypeError, ValueError) as error:
            raise ProviderError(
                f"official CSV has invalid dates in {date_column!r}"
            ) from error
        result = pd.DataFrame(
            {
                "DATE": dates,
                "value": frame[value_column],
                "series_code": source["series_code"],
            }
        )
        for name, classification in dataset.classifications.items():
            result[f"classification_{name}_code"] = classification["code"]
            result[f"classification_{name}_label"] = classification["label"]
        return result

