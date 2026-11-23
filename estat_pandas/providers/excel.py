from __future__ import annotations

import calendar
import numbers
import os
import re
import unicodedata
from io import BytesIO
from urllib.parse import urlparse
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from ..catalog import DatasetSpec
from ..errors import ProviderError
from .http import get_json, get_response


_DATA_CATALOG_API_URL = (
    "https://api.e-stat.go.jp/rest/3.0/app/json/getDataCatalog"
)
_DATA_CATALOG_PAGE_SIZE = 100
_MONTHS = {
    name.casefold(): month
    for month in range(1, 13)
    for name in (calendar.month_abbr[month], calendar.month_name[month])
}
_MONTHS["sept"] = 9
_ERA_BASE_YEARS = {"昭和": 1925, "平成": 1988, "令和": 2018}


def _is_missing(value):
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return bool(pd.isna(value))


def _parse_year(value):
    if _is_missing(value):
        return None
    if isinstance(value, numbers.Real) and not isinstance(value, bool):
        year = int(value)
        if value == year and 1900 <= year <= 2100:
            return year

    text = unicodedata.normalize("NFKC", str(value)).strip()
    match = re.search(r"(?<!\d)(\d{4})(?!\d)", text)
    if match:
        return int(match.group(1))
    for era, base_year in _ERA_BASE_YEARS.items():
        match = re.search(rf"{era}\s*(元|\d+)\s*年", text)
        if match:
            era_year = 1 if match.group(1) == "元" else int(match.group(1))
            return base_year + era_year
    return None


def _parse_month(value):
    if _is_missing(value):
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip().casefold()
    match = re.search(r"(\d{1,2})\s*月", text)
    if match:
        month = int(match.group(1))
        return month if 1 <= month <= 12 else None
    return _MONTHS.get(text.rstrip("."))


def _as_list(value, field):
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return value
    raise ProviderError(f"e-Stat data catalog has invalid {field}")


def _data_catalog_page(dataset, api_key, start_position):
    source = dataset.source
    payload = get_json(
        _DATA_CATALOG_API_URL,
        params={
            "appId": api_key,
            "statsCode": source["stats_code"],
            "searchWord": source["search_word"],
            "dataType": "XLS",
            "startPosition": str(start_position),
            "limit": str(_DATA_CATALOG_PAGE_SIZE),
            "lang": "J",
        },
        timeout=source.get("timeout", 30),
        provider="e-Stat data catalog",
        retry_count=source.get("retry_count", 1),
    )
    root = payload.get("GET_DATA_CATALOG")
    if not isinstance(root, dict):
        raise ProviderError("e-Stat data catalog returned an invalid response")
    result = root.get("RESULT", {})
    if str(result.get("STATUS")) != "0":
        message = result.get("ERROR_MSG", "unknown API error")
        raise ProviderError(f"e-Stat data catalog failed: {message}")

    info = root.get("DATA_CATALOG_LIST_INF")
    if not isinstance(info, dict):
        raise ProviderError("e-Stat data catalog response is missing its result list")
    try:
        total = int(info["NUMBER"])
    except (KeyError, TypeError, ValueError) as error:
        raise ProviderError("e-Stat data catalog returned an invalid result count") from error
    items = _as_list(info.get("DATA_CATALOG_INF"), "catalog entries")
    return total, items


def _resolve_workbook_url(dataset, api_key):
    candidates = []
    total, items = _data_catalog_page(dataset, api_key, 1)
    if total < 1:
        raise ProviderError(
            f"e-Stat has no Excel catalog entries for {dataset.key!r}"
        )

    for start_position in range(
        1, total + 1, _DATA_CATALOG_PAGE_SIZE
    ):
        if start_position > 1:
            page_total, items = _data_catalog_page(
                dataset, api_key, start_position
            )
            if page_total != total:
                raise ProviderError(
                    "e-Stat data catalog changed while resolving the workbook"
                )
        for item in items:
            dataset_info = item.get("DATASET")
            resources_info = item.get("RESOURCES")
            if not isinstance(dataset_info, dict) or not isinstance(
                resources_info, dict
            ):
                raise ProviderError("e-Stat data catalog entry is incomplete")
            resources = _as_list(
                resources_info.get("RESOURCE"), "resource entries"
            )
            for resource in resources:
                title = resource.get("TITLE")
                if not isinstance(title, dict):
                    continue
                table_name = title.get("TABLE_NAME", "")
                if (
                    resource.get("FORMAT") != "XLS"
                    or title.get("TABLE_NO") != dataset.source["table_no"]
                    or "主要項目" not in table_name
                    or "完全失業率" not in table_name
                ):
                    continue
                release_date = (
                    resource.get("RELEASE_DATE")
                    or dataset_info.get("RELEASE_DATE")
                    or ""
                )
                modified_date = (
                    resource.get("LAST_MODIFIED_DATE")
                    or dataset_info.get("LAST_MODIFIED_DATE")
                    or ""
                )
                candidates.append(
                    (
                        release_date,
                        modified_date,
                        str(item.get("@id", "")),
                        resource.get("URL"),
                    )
                )

    if not candidates:
        raise ProviderError(
            f"e-Stat has no matching Excel resource for {dataset.key!r}"
        )
    _, _, _, url = max(candidates, key=lambda candidate: candidate[:3])
    parsed_url = urlparse(url or "")
    if (
        parsed_url.scheme != "https"
        or parsed_url.hostname != "www.e-stat.go.jp"
        or parsed_url.path != "/stat-search/file-download"
    ):
        raise ProviderError("e-Stat data catalog returned an invalid workbook URL")
    return url


class EStatExcelProvider:
    def fetch(
        self,
        dataset: DatasetSpec,
        start: pd.Timestamp | None,
        end: pd.Timestamp | None,
    ) -> pd.DataFrame:
        api_key = os.environ.get("ESTAT_APP_ID")
        if not api_key:
            raise ProviderError(
                "ESTAT_APP_ID must be set to load an e-Stat Excel dataset"
            )

        source = dataset.source
        url = _resolve_workbook_url(dataset, api_key)
        response = get_response(
            url,
            params=None,
            timeout=source.get("timeout", 30),
            provider="e-Stat Excel",
            retry_count=source.get("retry_count", 1),
        )
        try:
            frame = pd.read_excel(
                BytesIO(response.content),
                sheet_name=source["sheet_name"],
                header=None,
                skiprows=source["skiprows"],
                engine="openpyxl",
            )
        except (
            BadZipFile,
            ImportError,
            InvalidFileException,
            OSError,
            ValueError,
        ) as error:
            raise ProviderError(
                f"e-Stat Excel could not be parsed for {dataset.key!r}"
            ) from error

        column_indexes = (
            source["year_column_index"],
            source["month_column_index"],
            source["value_column_index"],
        )
        if frame.shape[1] <= max(column_indexes):
            raise ProviderError(
                f"e-Stat Excel is missing configured columns for {dataset.key!r}"
            )

        year = None
        observations = []
        for _, row in frame.iterrows():
            month_value = row.iloc[source["month_column_index"]]
            value = row.iloc[source["value_column_index"]]
            if _is_missing(month_value):
                continue
            month = _parse_month(month_value)
            if month is None:
                if not _is_missing(value):
                    raise ProviderError(
                        f"e-Stat Excel has an invalid month for {dataset.key!r}"
                    )
                continue

            reported_year = _parse_year(row.iloc[source["year_column_index"]])
            if reported_year is not None:
                year = reported_year
            if year is None:
                raise ProviderError(
                    f"e-Stat Excel has no year for {dataset.key!r}"
                )
            if _is_missing(value):
                continue
            observations.append(
                {
                    "DATE": pd.Timestamp(year=year, month=month, day=1),
                    "value": value,
                    "series_code": source["series_code"],
                }
            )

        if not observations:
            raise ProviderError(
                f"e-Stat Excel returned no observations for {dataset.key!r}"
            )

        result = pd.DataFrame(observations)
        for name, classification in dataset.classifications.items():
            result[f"classification_{name}_code"] = classification["code"]
            result[f"classification_{name}_label"] = classification["label"]
        return result