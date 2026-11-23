import unittest
from unittest.mock import Mock, patch

import pandas as pd

from estat_pandas import DatasetSpec, ProviderError
from estat_pandas.errors import DataValidationError
from estat_pandas.providers.boj import BOJProvider
from estat_pandas.providers.csv import CSVProvider
from estat_pandas.providers.estat import EStatProvider


class ProviderTests(unittest.TestCase):
    @staticmethod
    def cpi_spec():
        return DatasetSpec(
            key="JPN_CPI_CORE_CORE_YOY",
            title="CPI",
            source={
                "provider": "estat",
                "stats_data_id": "table-1",
                "filters": {
                    "cdArea": "00000",
                    "cdTab": "3",
                    "cdCat01": "0178",
                },
                "lang": "jp",
            },
            unit="%",
            frequency="monthly",
            seasonal_adjustment="not_seasonally_adjusted",
            classifications={
                "area": {"code": "00000", "label": "全国"},
                "table": {"code": "3", "label": "前年同月比"},
                "cat01": {"code": "0178", "label": "コア指数"},
            },
        )

    def test_estat_provider_applies_catalog_selection_and_labels(self):
        source_frame = pd.DataFrame(
            {
                "DATE": [pd.Timestamp("2024-01-01")],
                "$": ["2.1"],
                "@area": ["00000"],
                "area_label": ["全国"],
                "@tab": ["3"],
                "tab_label": ["前年同月比"],
                "@cat01": ["0178"],
                "cat01_label": ["コア指数"],
            }
        )
        with (
            patch.dict("os.environ", {"ESTAT_APP_ID": "test-key"}),
            patch("estat_pandas.providers.estat.EStatReader") as reader_class,
        ):
            reader_class.return_value.read.return_value = source_frame
            result = EStatProvider().fetch(
                self.cpi_spec(), pd.Timestamp("2024-01-01"), None
            )

        self.assertEqual(result["value"].tolist(), ["2.1"])
        self.assertEqual(
            result["classification_cat01_label"].tolist(),
            ["コア指数"],
        )
        self.assertEqual(reader_class.call_args.kwargs["cdTab"], "3")

    def test_estat_provider_rejects_catalog_label_drift(self):
        frame = pd.DataFrame(
            {
                "DATE": [pd.Timestamp("2024-01-01")],
                "$": ["2.1"],
                "@area": ["00000"],
                "area_label": ["全国"],
                "@tab": ["3"],
                "tab_label": ["別の表"],
                "@cat01": ["0178"],
                "cat01_label": ["コア指数"],
            }
        )
        with (
            patch.dict("os.environ", {"ESTAT_APP_ID": "test-key"}),
            patch("estat_pandas.providers.estat.EStatReader") as reader_class,
        ):
            reader_class.return_value.read.return_value = frame
            with self.assertRaisesRegex(DataValidationError, "does not match catalog"):
                EStatProvider().fetch(self.cpi_spec(), None, None)

    def test_estat_provider_requires_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ProviderError, "ESTAT_APP_ID"):
                EStatProvider().fetch(self.cpi_spec(), None, None)

    def test_boj_provider_checks_metadata_and_normalizes_daily_values(self):
        spec = DatasetSpec(
            key="JPN_CALL_RATE_OVERNIGHT",
            title="Call rate",
            source={
                "provider": "boj",
                "db": "FM01",
                "series_code": "STRDCLUCON",
                "lang": "jp",
            },
            unit="年％",
            frequency="daily",
            seasonal_adjustment="not_applicable",
            classifications={
                "series": {
                    "code": "STRDCLUCON",
                    "label": "無担保コールＯ／Ｎ物レート／平均値 日次／金利",
                }
            },
        )
        payload = {
            "STATUS": 200,
            "RESULTSET": [
                {
                    "SERIES_CODE": "STRDCLUCON",
                    "NAME_OF_TIME_SERIES_J": "無担保コールＯ／Ｎ物レート／平均値 日次／金利",
                    "UNIT_J": "年％",
                    "CATEGORY_J": "金利",
                    "FREQUENCY": "DAILY",
                    "VALUES": {
                        "SURVEY_DATES": ["20240104", "20240105"],
                        "VALUES": ["0.001", "0.002"],
                    },
                }
            ],
        }
        with patch("estat_pandas.providers.boj.get_json", return_value=payload):
            result = BOJProvider().fetch(spec, None, None)

        self.assertEqual(result["DATE"].tolist(), list(pd.to_datetime(
            ["2024-01-04", "2024-01-05"]
        )))
        self.assertEqual(result["value"].tolist(), ["0.001", "0.002"])
        self.assertEqual(result["category"].tolist(), ["金利", "金利"])

    def test_boj_provider_parses_monthly_dates(self):
        spec = DatasetSpec(
            key="JPN_M2",
            title="M2",
            source={
                "provider": "boj",
                "db": "MD02",
                "series_code": "MAM1NAM2M2MO",
                "lang": "jp",
            },
            unit="億円",
            frequency="monthly",
            seasonal_adjustment="not_seasonally_adjusted",
            classifications={
                "series": {
                    "code": "MAM1NAM2M2MO",
                    "label": "Ｍ２／平／マネーストック",
                }
            },
        )
        payload = {
            "STATUS": 200,
            "RESULTSET": [
                {
                    "SERIES_CODE": "MAM1NAM2M2MO",
                    "NAME_OF_TIME_SERIES_J": "Ｍ２／平／マネーストック",
                    "UNIT_J": "億円",
                    "FREQUENCY": "MONTHLY",
                    "VALUES": {
                        "SURVEY_DATES": ["202401", "202402"],
                        "VALUES": ["123", "124"],
                    },
                }
            ],
        }
        with patch("estat_pandas.providers.boj.get_json", return_value=payload):
            result = BOJProvider().fetch(spec, None, None)

        self.assertEqual(
            result["DATE"].tolist(),
            list(pd.to_datetime(["2024-01-01", "2024-02-01"])),
        )
        self.assertEqual(result["value"].tolist(), ["123", "124"])

    def test_boj_provider_rejects_unit_drift(self):
        provider = BOJProvider()
        spec = DatasetSpec(
            key="boj.test",
            title="Test",
            source={
                "provider": "boj",
                "db": "FM01",
                "series_code": "X",
            },
            unit="%",
            frequency="daily",
            seasonal_adjustment="not_applicable",
            classifications={},
        )
        payload = {
            "STATUS": 200,
            "RESULTSET": [
                {
                    "SERIES_CODE": "X",
                    "NAME_OF_TIME_SERIES_J": "Test",
                    "UNIT_J": "円",
                    "FREQUENCY": "DAILY",
                    "VALUES": {"SURVEY_DATES": ["20240101"], "VALUES": ["1"]},
                }
            ],
        }
        with patch("estat_pandas.providers.boj.get_json", return_value=payload):
            with self.assertRaisesRegex(DataValidationError, "unit mismatch"):
                provider.fetch(spec, None, None)

    def test_csv_provider_uses_only_declared_flat_csv_columns(self):
        spec = DatasetSpec(
            key="csv.test",
            title="CSV series",
            source={
                "provider": "csv",
                "url": "https://example.test/series.csv",
                "series_code": "CSV-1",
                "date_column": "month",
                "date_format": "%Y-%m",
                "value_column": "index",
                "encoding": "utf-8",
                "delimiter": ",",
                "classification_columns": {"group": "group_code"},
            },
            unit="index",
            frequency="monthly",
            seasonal_adjustment="not_applicable",
            classifications={"group": {"code": "001", "label": "Selected group"}},
        )
        response = Mock(
            content=b"month,group_code,index\n2024-01,001,101.2\n2024-01,002,99.9\n"
        )
        with patch(
            "estat_pandas.providers.csv.get_response",
            return_value=response,
        ):
            result = CSVProvider().fetch(spec, None, None)

        self.assertEqual(result["DATE"].iloc[0], pd.Timestamp("2024-01-01"))
        self.assertEqual(result["value"].iloc[0], 101.2)
        self.assertEqual(result["series_code"].iloc[0], "CSV-1")
        self.assertEqual(
            result["classification_group_label"].iloc[0],
            "Selected group",
        )


if __name__ == "__main__":
    unittest.main()
