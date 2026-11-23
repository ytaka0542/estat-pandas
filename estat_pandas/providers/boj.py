from __future__ import annotations

import pandas as pd

from ..catalog import DatasetSpec
from ..errors import DataValidationError, ProviderError
from .http import get_json


class BOJProvider:
    _BASE_URL = "https://www.stat-search.boj.or.jp/api/v1/"
    _FREQUENCY_MAP = {
        "DAILY": "daily",
        "MONTHLY": "monthly",
        "QUARTERLY": "quarterly",
        "ANNUAL": "annual",
    }
    _DATE_FORMAT_MAP = {
        "DAILY": "%Y%m%d",
        "MONTHLY": "%Y%m",
        "QUARTERLY": "%Y%m%d",
        "ANNUAL": "%Y%m%d",
    }

    def fetch(
        self,
        dataset: DatasetSpec,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        source = dataset.source
        codes = [source["series_code"]]
        params = {
            "db": source["db"],
            "lang": "JP" if source.get("lang", "jp") == "jp" else "EN",
            "code": ",".join(codes),
        }
        if source.get("layer") is not None:
            params["layer"] = source["layer"]
        if start is not None:
            params["startDate"] = start.strftime("%Y%m")
        if end is not None:
            params["endDate"] = end.strftime("%Y%m")

        payload = get_json(
            self._BASE_URL + "getDataCode",
            params,
            source.get("timeout", 30),
            "Bank of Japan",
            retry_count=source.get("retry_count", 2),
        )
        if str(payload.get("STATUS")) != "200":
            message = payload.get("MESSAGE") or "no message"
            raise ProviderError(f"Bank of Japan API failed: {message}")

        series_list = payload.get("RESULTSET")
        if not isinstance(series_list, list) or not series_list:
            raise ProviderError(
                f"Bank of Japan returned no observations for {dataset.key!r}"
            )

        returned_codes = {
            str(series.get("SERIES_CODE"))
            for series in series_list
            if isinstance(series, dict)
        }
        if returned_codes != set(codes):
            raise DataValidationError(
                f"Bank of Japan returned series codes {sorted(returned_codes)}, "
                f"expected {sorted(codes)}"
            )

        expected_series = dataset.classifications.get("series")
        rows = []
        for series in series_list:
            if not isinstance(series, dict):
                raise ProviderError("Bank of Japan RESULTSET contains an invalid entry")
            code = str(series["SERIES_CODE"])
            name, unit, frequency, date_values, observations = self._series_fields(
                series, source.get("lang", "jp")
            )
            if unit != dataset.unit:
                raise DataValidationError(
                    f"Bank of Japan unit mismatch for {code}: "
                    f"expected {dataset.unit!r}, received {unit!r}"
                )
            normalized_frequency = self._FREQUENCY_MAP.get(frequency)
            if normalized_frequency != dataset.frequency:
                raise DataValidationError(
                    f"Bank of Japan frequency mismatch for {code}: "
                    f"expected {dataset.frequency!r}, received {frequency!r}"
                )
            if expected_series is not None and (
                expected_series["code"] != code
                or expected_series["label"] != name
            ):
                raise DataValidationError(
                    f"Bank of Japan series metadata does not match catalog for {code}"
                )
            if len(date_values) != len(observations):
                raise ProviderError(
                    f"Bank of Japan date/value count mismatch for {code}"
                )
            date_format = self._DATE_FORMAT_MAP.get(frequency)
            if date_format is None:
                raise ProviderError(
                    f"Bank of Japan returned an unsupported frequency for {code}"
                )
            try:
                dates = pd.to_datetime(
                    pd.Series(date_values, dtype="string"),
                    format=date_format,
                    errors="raise",
                )
            except (TypeError, ValueError) as error:
                raise ProviderError(
                    f"Bank of Japan returned an invalid date for {code}"
                ) from error
            rows.extend(
                {
                    "DATE": date,
                    "value": value,
                    "series_code": code,
                    "series_name": name,
                    "category": self._category(series, source.get("lang", "jp")),
                }
                for date, value in zip(dates, observations)
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _series_fields(series, lang):
        values = series.get("VALUES")
        if not isinstance(values, dict):
            raise ProviderError("Bank of Japan series is missing VALUES")
        if lang == "jp":
            name = series.get("NAME_OF_TIME_SERIES_J")
            unit = series.get("UNIT_J")
        else:
            name = series.get("NAME_OF_TIME_SERIES")
            unit = series.get("UNIT")
        frequency = series.get("FREQUENCY")
        dates = values.get("SURVEY_DATES")
        observations = values.get("VALUES")
        if not isinstance(name, str) or not isinstance(unit, str):
            raise ProviderError("Bank of Japan series metadata is incomplete")
        if not isinstance(frequency, str):
            raise ProviderError("Bank of Japan series frequency is missing")
        if not isinstance(dates, list) or not isinstance(observations, list):
            raise ProviderError("Bank of Japan VALUES must contain date and value lists")
        return name, unit, frequency, dates, observations

    @staticmethod
    def _category(series, lang):
        field = "CATEGORY_J" if lang == "jp" else "CATEGORY"
        category = series.get(field)
        return category if isinstance(category, str) else None

    @classmethod
    def search(cls, db, lang="jp", timeout=30):
        if not isinstance(db, str) or not db.strip():
            raise ValueError("BOJ database code is required")
        if lang not in {"jp", "en"}:
            raise ValueError("lang must be 'jp' or 'en'")
        payload = get_json(
            cls._BASE_URL + "getMetadata",
            {
                "format": "json",
                "lang": "JP" if lang == "jp" else "EN",
                "db": db,
            },
            timeout,
            "Bank of Japan metadata search",
        )
        if str(payload.get("STATUS")) != "200":
            message = payload.get("MESSAGE") or "no message"
            raise ProviderError(f"Bank of Japan metadata search failed: {message}")
        items = payload.get("RESULTSET")
        if items is None:
            return pd.DataFrame(
                columns=["SERIES_CODE", "NAME_OF_TIME_SERIES", "FREQUENCY", "UNIT"]
            )
        if not isinstance(items, list):
            raise ProviderError("Bank of Japan metadata RESULTSET must be a list")
        return pd.DataFrame(items)

