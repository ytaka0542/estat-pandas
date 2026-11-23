import time

import pandas as pd
import requests
from pandas_datareader.base import _BaseReader

from .errors import ProviderError


class EStatAPIError(ProviderError):
    """Raised when e-Stat cannot return a valid response for a request."""


class EStatReader(_BaseReader):
    _BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/"
    _QUARTERLY_AGGREGATIONS = {"mean", "sum", "last", "compound_percent"}
    _RESERVED_DATA_PARAMS = {"appId", "statsDataId", "metaGetFlg", "lang"}
    _FILTER_COLUMNS = {
        "cdTab": "@tab",
        "cdArea": "@area",
        "cdTime": "@time",
    }
    _MISSING_VALUE_MARKERS = {"", "-", "－", "–", "—", "…", "...", "秘匿"}

    def __init__(
        self,
        symbols,
        api_key=None,
        lang="jp",
        start=None,
        end=None,
        expected_unit=None,
        expected_period_type=None,
        quarterly_aggregation=None,
        **kwargs,
    ):
        pdr_parameters = {
            "retry_count",
            "pause",
            "timeout",
            "session",
            "freq",
        }
        pdr_kwargs = {}
        estat_kwargs = {}
        for key, value in kwargs.items():
            if key in pdr_parameters:
                pdr_kwargs[key] = value
            else:
                estat_kwargs[key] = value

        super().__init__(
            symbols=symbols,
            start=start,
            end=end,
            **pdr_kwargs,
        )

        if symbols is None or symbols == "":
            raise ValueError("e-Stat statsDataId を指定してください")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("e-Stat APIキーを指定してください")
        if not isinstance(lang, str) or lang.lower() not in {"jp", "en"}:
            raise ValueError("lang は 'jp' または 'en' を指定してください")

        reserved_params = self._RESERVED_DATA_PARAMS.intersection(estat_kwargs)
        if reserved_params:
            names = ", ".join(sorted(reserved_params))
            raise ValueError(f"予約済みのe-Statパラメーターは指定できません: {names}")

        period_types = {"month", "quarter", "year", "fiscal_year"}
        if (
            expected_period_type is not None
            and expected_period_type not in period_types
        ):
            allowed = ", ".join(sorted(period_types))
            raise ValueError(f"expected_period_type は {allowed} を指定してください")
        if expected_unit is not None and (
            not isinstance(expected_unit, str) or not expected_unit
        ):
            raise ValueError("expected_unit は空でない文字列を指定してください")

        if quarterly_aggregation not in (
            None,
            *self._QUARTERLY_AGGREGATIONS,
        ):
            allowed = ", ".join(sorted(self._QUARTERLY_AGGREGATIONS))
            raise ValueError(
                f"quarterly_aggregation は None または {allowed} を指定してください"
            )

        self.api_key = api_key.strip()
        self.lang = "J" if lang.lower() == "jp" else "E"
        self.ext_params = estat_kwargs
        self.start = self._normalize_date_bound(start, "start")
        self.end = self._normalize_date_bound(end, "end")
        if self.start is not None and self.end is not None and self.start > self.end:
            raise ValueError("start は end 以前の日付を指定してください")
        self.expected_unit = expected_unit
        self.expected_period_type = expected_period_type
        self.quarterly_aggregation = quarterly_aggregation

    @staticmethod
    def _normalize_date_bound(value, name):
        if value is None:
            return None
        try:
            normalized = pd.Timestamp(value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{name} を日付として解釈できません: {value!r}") from error
        if pd.isna(normalized):
            raise ValueError(f"{name} に有効な日付を指定してください")
        return normalized

    @property
    def url(self):
        return self._BASE_URL + "getStatsData"

    def _get_params(self, symbols):
        return {
            **self.ext_params,
            "appId": self.api_key,
            "statsDataId": symbols,
            "metaGetFlg": "Y",
            "lang": self.lang,
        }

    @staticmethod
    def _request_json(
        url,
        params,
        timeout,
        operation,
        session=None,
        retry_count=0,
        pause=0,
    ):
        client = session or requests
        for attempt in range(retry_count + 1):
            try:
                response = client.get(url, params=params, timeout=timeout)
            except requests.RequestException as error:
                if attempt < retry_count:
                    time.sleep(pause)
                    continue
                raise EStatAPIError(
                    f"e-Stat {operation} request failed ({type(error).__name__})"
                ) from None

            if response.status_code >= 500 and attempt < retry_count:
                time.sleep(pause)
                continue
            break

        if response.status_code != 200:
            raise EStatAPIError(
                f"e-Stat {operation} request failed with HTTP {response.status_code}"
            )

        try:
            payload = response.json()
        except ValueError as error:
            raise EStatAPIError(
                f"e-Stat {operation} response was not valid JSON"
            ) from error

        if not isinstance(payload, dict):
            raise EStatAPIError(
                f"e-Stat {operation} response must be a JSON object"
            )
        return payload

    @staticmethod
    def _get_api_root(payload, root_key, operation):
        root = payload.get(root_key)
        if not isinstance(root, dict):
            raise EStatAPIError(
                f"e-Stat {operation} response is missing {root_key}"
            )

        result = root.get("RESULT")
        if not isinstance(result, dict):
            raise EStatAPIError(
                f"e-Stat {operation} response is missing RESULT metadata"
            )

        status = str(result.get("STATUS", ""))
        if status != "0":
            message = result.get("ERROR_MSG") or "詳細メッセージなし"
            raise EStatAPIError(
                f"e-Stat {operation} failed (STATUS={status or 'missing'}): {message}"
            )
        return root

    def read(self):
        payload = self._request_json(
            self.url,
            self._get_params(self.symbols),
            self.timeout,
            "getStatsData",
            session=self.session,
            retry_count=self.retry_count,
            pause=self.pause,
        )
        return self._read_content(payload)

    def _read_content(self, payload):
        root = self._get_api_root(payload, "GET_STATS_DATA", "getStatsData")
        statistical_data = root.get("STATISTICAL_DATA")
        if not isinstance(statistical_data, dict):
            raise EStatAPIError("e-Stat response is missing STATISTICAL_DATA")

        data_inf = statistical_data.get("DATA_INF")
        if not isinstance(data_inf, dict):
            raise EStatAPIError("e-Stat response is missing DATA_INF")

        values = data_inf.get("VALUE")
        if isinstance(values, dict):
            values = [values]
        if not isinstance(values, list) or not values:
            raise EStatAPIError("e-Stat returned no observations for the request")
        if any(not isinstance(value, dict) for value in values):
            raise EStatAPIError("e-Stat VALUE must contain observation objects")

        df = pd.DataFrame(values)
        missing_columns = {"@time", "$"} - set(df.columns)
        if missing_columns:
            columns = ", ".join(sorted(missing_columns))
            raise EStatAPIError(
                f"e-Stat observations are missing required columns: {columns}"
            )

        class_inf = statistical_data.get("CLASS_INF", {})
        if not isinstance(class_inf, dict):
            raise EStatAPIError("e-Stat CLASS_INF must be an object")
        label_dict = self._build_label_dict_from_meta(
            class_inf.get("CLASS_OBJ", [])
        )
        df = self._apply_labels(df, label_dict)
        self._validate_labels(df, label_dict)
        self._validate_requested_filters(df)

        parsed_times = [self._parse_time_code(code) for code in df["@time"]]
        df["DATE"] = [parsed[0] for parsed in parsed_times]
        df["period_type"] = [parsed[1] for parsed in parsed_times]
        self._validate_expected_metadata(df)

        if self.quarterly_aggregation is not None:
            df = self._add_quarter_rows(df, self.quarterly_aggregation)

        if self.start is not None:
            df = df.loc[df["DATE"] >= self.start]
        if self.end is not None:
            df = df.loc[df["DATE"] <= self.end]
        return df.reset_index(drop=True)

    def _validate_expected_metadata(self, df):
        if self.expected_unit is not None:
            if "@unit" not in df:
                raise EStatAPIError("e-Stat response is missing @unit")
            if df["@unit"].isna().any():
                raise EStatAPIError(
                    f"Expected unit {self.expected_unit!r}, but some observations "
                    "have no @unit"
                )
            units = set(df["@unit"].dropna().astype(str))
            if units != {self.expected_unit}:
                raise EStatAPIError(
                    f"Expected unit {self.expected_unit!r}, received "
                    f"{sorted(units)}"
                )

        if self.expected_period_type is not None:
            period_types = set(df["period_type"].dropna().astype(str))
            if period_types != {self.expected_period_type}:
                raise EStatAPIError(
                    f"Expected period type {self.expected_period_type!r}, received "
                    f"{sorted(period_types)}"
                )

    @staticmethod
    def _build_label_dict_from_meta(class_objs):
        if class_objs is None:
            return {}
        if isinstance(class_objs, dict):
            class_objs = [class_objs]
        if not isinstance(class_objs, list):
            raise EStatAPIError("e-Stat CLASS_OBJ must be an object or list")

        label_dict = {}
        for class_object in class_objs:
            if not isinstance(class_object, dict):
                raise EStatAPIError("e-Stat CLASS_OBJ contains an invalid entry")

            category_id = class_object.get("@id")
            if not isinstance(category_id, str) or not category_id:
                raise EStatAPIError("e-Stat CLASS_OBJ entry is missing @id")

            classes = class_object.get("CLASS", [])
            if isinstance(classes, dict):
                classes = [classes]
            if not isinstance(classes, list):
                raise EStatAPIError(
                    f"e-Stat CLASS for {category_id} must be an object or list"
                )

            labels = {}
            for item in classes:
                if not isinstance(item, dict):
                    raise EStatAPIError(
                        f"e-Stat CLASS for {category_id} contains an invalid entry"
                    )
                code = item.get("@code")
                name = item.get("@name")
                if code is None or name is None:
                    raise EStatAPIError(
                        f"e-Stat CLASS for {category_id} is missing @code or @name"
                    )
                labels[str(code)] = str(name)
            label_dict[category_id] = labels
        return label_dict

    @staticmethod
    def _apply_labels(df, label_dict):
        df = df.copy()
        for column in df.columns:
            if not column.startswith("@"):
                continue
            category_id = column[1:]
            if category_id in label_dict:
                label_column = f"{category_id}_label"
                df[label_column] = df[column].astype(str).map(label_dict[category_id])
        return df

    @staticmethod
    def _validate_labels(df, label_dict):
        for column in df.columns:
            if not (column.startswith("@cat") or column.startswith("@area")):
                continue
            label_column = f"{column[1:]}_label"
            if column[1:] not in label_dict or label_column not in df:
                raise EStatAPIError(
                    f"e-Stat metadata is missing labels for {column}"
                )
            missing_labels = df[column].notna() & df[label_column].isna()
            if missing_labels.any():
                codes = sorted(df.loc[missing_labels, column].astype(str).unique())
                raise EStatAPIError(
                    f"e-Stat metadata has no labels for {column} codes: {codes}"
                )

    def _validate_requested_filters(self, df):
        filters = {
            **self._FILTER_COLUMNS,
            **{
                f"cdCat{number:02d}": f"@cat{number:02d}"
                for number in range(1, 16)
            },
        }
        for parameter, column in filters.items():
            if parameter not in self.ext_params:
                continue
            if column not in df:
                raise EStatAPIError(
                    f"e-Stat response is missing filtered column {column}"
                )

            requested = self.ext_params[parameter]
            if isinstance(requested, (list, tuple, set)):
                expected_codes = {str(code) for code in requested}
            else:
                expected_codes = {
                    code.strip()
                    for code in str(requested).split(",")
                    if code.strip()
                }
            returned_codes = set(df[column].dropna().astype(str))
            unexpected = returned_codes - expected_codes
            missing = expected_codes - returned_codes
            if unexpected or missing:
                raise EStatAPIError(
                    f"e-Stat filter {parameter}={sorted(expected_codes)} "
                    f"returned codes {sorted(returned_codes)} "
                    f"(unexpected={sorted(unexpected)}, missing={sorted(missing)})"
                )

    @staticmethod
    def _parse_time_code(code):
        value = str(code).strip()
        if len(value) != 10 or not value.isdigit():
            raise ValueError(f"Unsupported e-Stat time code: {code!r}")

        year = int(value[:4])
        middle = value[4:6]
        start_month = value[6:8]
        end_month = value[8:10]
        quarter_map = {"0103": 1, "0406": 4, "0709": 7, "1012": 10}

        if middle == "00" and value[-4:] in quarter_map:
            month = quarter_map[value[-4:]]
            return pd.Timestamp(year=year, month=month, day=1), "quarter"
        if middle == "00" and start_month == "00" and end_month == "00":
            return pd.Timestamp(year=year, month=1, day=1), "year"
        if middle == "10" and start_month == "00" and end_month == "00":
            return pd.Timestamp(year=year, month=4, day=1), "fiscal_year"
        if (
            middle == "00"
            and start_month == end_month
            and start_month in {f"{month:02d}" for month in range(1, 13)}
        ):
            return (
                pd.Timestamp(year=year, month=int(start_month), day=1),
                "month",
            )
        raise ValueError(f"Unsupported e-Stat time code: {code!r}")

    def _estat_time_to_date(self, code):
        return self._parse_time_code(code)[0]

    def _estat_time_type(self, code):
        return self._parse_time_code(code)[1]

    def _add_quarter_rows(self, df, aggregation):
        if aggregation not in self._QUARTERLY_AGGREGATIONS:
            allowed = ", ".join(sorted(self._QUARTERLY_AGGREGATIONS))
            raise ValueError(f"aggregation must be one of: {allowed}")
        required_columns = {"DATE", "$", "period_type"}
        missing_columns = required_columns - set(df.columns)
        if missing_columns:
            columns = ", ".join(sorted(missing_columns))
            raise ValueError(f"Cannot aggregate without columns: {columns}")

        monthly = df.loc[df["period_type"] == "month"].copy()
        quarterly = df.loc[df["period_type"] == "quarter"]
        if not monthly.empty and not quarterly.empty:
            raise ValueError(
                "Monthly and native quarterly rows are mixed; select one frequency "
                "before aggregation"
            )
        if monthly.empty:
            if not quarterly.empty:
                return df
            raise ValueError(
                "Quarterly aggregation was requested, but no monthly data exists"
            )

        if aggregation == "compound_percent":
            if "@unit" not in monthly:
                raise ValueError(
                    "compound_percent requires an explicit percentage @unit"
                )
            units = set(monthly["@unit"].dropna().astype(str))
            if not units or not units.issubset({"%", "％"}):
                raise ValueError(
                    "compound_percent can only be used with percentage-unit data"
                )

        dimension_columns = [
            column
            for column in df.columns
            if column not in {"@time", "DATE", "$", "period_type", "time_label"}
            and not column.endswith("_label")
        ]
        label_columns = [
            column
            for column in df.columns
            if column.endswith("_label") and column != "time_label"
        ]
        if dimension_columns:
            group_key = (
                dimension_columns[0]
                if len(dimension_columns) == 1
                else dimension_columns
            )
            grouped = monthly.groupby(group_key, dropna=False, sort=False)
        else:
            grouped = [(None, monthly)]

        quarter_rows = []
        for _, group in grouped:
            group = group.sort_values("DATE")
            indexed = group.set_index("DATE")
            if indexed.index.has_duplicates:
                raise ValueError(
                    "Multiple monthly observations exist for the same selected series"
                )

            numeric_values = pd.to_numeric(indexed["$"], errors="coerce")
            invalid_values = (
                indexed["$"].notna()
                & numeric_values.isna()
                & ~indexed["$"].astype(str).str.strip().isin(
                    self._MISSING_VALUE_MARKERS
                )
            )
            if invalid_values.any():
                values = sorted(indexed.loc[invalid_values, "$"].astype(str).unique())
                raise ValueError(
                    f"Monthly values contain non-numeric entries: {values}"
                )

            periods = sorted(group["DATE"].dt.to_period("Q").unique())
            for period in periods:
                quarter_start = period.start_time.normalize()
                expected_months = pd.date_range(
                    quarter_start,
                    periods=3,
                    freq="MS",
                )
                values = numeric_values.reindex(expected_months)
                if aggregation == "last":
                    value = values.iloc[-1]
                elif values.notna().all():
                    if aggregation == "mean":
                        value = values.mean()
                    elif aggregation == "sum":
                        value = values.sum()
                    else:
                        value = ((1 + values / 100).prod() - 1) * 100
                else:
                    value = float("nan")

                row = group.iloc[0].to_dict()
                row["DATE"] = quarter_start
                row["$"] = value
                row["period_type"] = "quarter"
                start_month = quarter_start.month
                end_month = start_month + 2
                row["@time"] = (
                    f"{quarter_start.year:04d}00"
                    f"{start_month:02d}{end_month:02d}"
                )
                if "time_label" in df:
                    row["time_label"] = (
                        f"{quarter_start.year}年{start_month}〜{end_month}月期"
                    )
                for column in label_columns:
                    row[column] = group.iloc[0][column]
                quarter_rows.append(row)

        if not quarter_rows:
            raise ValueError("No quarterly rows could be generated from monthly data")

        result = pd.concat(
            [df, pd.DataFrame(quarter_rows)],
            ignore_index=True,
            sort=False,
        )
        return result.sort_values("DATE", kind="stable").reset_index(drop=True)

    @classmethod
    def search(
        cls,
        keyword,
        api_key,
        lang="jp",
        timeout=30,
        session=None,
        retry_count=3,
        pause=0.1,
        **kwargs,
    ):
        if not isinstance(keyword, str) or not keyword.strip():
            raise ValueError("検索語を指定してください")
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("e-Stat APIキーを指定してください")
        if not isinstance(lang, str) or lang.lower() not in {"jp", "en"}:
            raise ValueError("lang は 'jp' または 'en' を指定してください")

        reserved_params = {"appId", "lang", "searchWord"}.intersection(kwargs)
        if reserved_params:
            names = ", ".join(sorted(reserved_params))
            raise ValueError(f"予約済みのe-Statパラメーターは指定できません: {names}")

        url = cls._BASE_URL + "getStatsList"
        payload = cls._request_json(
            url,
            {
                **kwargs,
                "appId": api_key.strip(),
                "lang": "J" if lang.lower() == "jp" else "E",
                "searchWord": keyword,
            },
            timeout,
            "getStatsList",
            session=session,
            retry_count=retry_count,
            pause=pause,
        )
        root = payload.get("GET_STATS_LIST")
        if isinstance(root, dict):
            result = root.get("RESULT")
            if isinstance(result, dict) and str(result.get("STATUS")) == "300":
                return pd.DataFrame(columns=["id", "stat_name", "title"])
        root = cls._get_api_root(payload, "GET_STATS_LIST", "getStatsList")
        data_list = root.get("DATALIST_INF")
        if data_list is None:
            return pd.DataFrame(columns=["id", "stat_name", "title"])
        if not isinstance(data_list, dict):
            raise EStatAPIError("e-Stat DATALIST_INF must be an object")

        items = data_list.get("TABLE_INF", [])
        if isinstance(items, dict):
            items = [items]
        if items is None:
            items = []
        if not isinstance(items, list):
            raise EStatAPIError("e-Stat TABLE_INF must be an object or list")

        rows = []
        for item in items:
            if not isinstance(item, dict) or "@id" not in item:
                raise EStatAPIError("e-Stat TABLE_INF contains an invalid entry")
            rows.append(
                {
                    "id": item["@id"],
                    "stat_name": cls._extract_text(item.get("STAT_NAME")),
                    "title": cls._extract_text(item.get("TITLE")),
                }
            )
        return pd.DataFrame(rows, columns=["id", "stat_name", "title"])

    @staticmethod
    def _extract_text(value):
        if isinstance(value, dict):
            return value.get("$")
        return value


def DataReader(name, data_source=None, *args, **kwargs):
    """Read e-Stat data or delegate other sources to pandas-datareader."""
    if data_source == "estat":
        return EStatReader(name, *args, **kwargs).read()

    import pandas_datareader.data as pdr

    return pdr.DataReader(name, data_source, *args, **kwargs)


def search(keyword, api_key, lang="jp", **kwargs):
    """Search e-Stat tables and return their IDs and titles."""
    return EStatReader.search(keyword, api_key, lang, **kwargs)
