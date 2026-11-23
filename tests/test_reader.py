import unittest
from unittest.mock import Mock, patch

import pandas as pd

from estat_pandas import EStatAPIError, EStatReader


def make_data_response(time_codes=("2024000101", "2024000202")):
    observations = []
    for code, value in zip(time_codes, range(1, len(time_codes) + 1)):
        observations.append(
            {
                "@tab": "test-table",
                "@cat01": "000",
                "@area": "00000",
                "@time": code,
                "$": str(value),
                "@unit": "%",
            }
        )
    return {
        "GET_STATS_DATA": {
            "RESULT": {"STATUS": 0},
            "STATISTICAL_DATA": {
                "DATA_INF": {"VALUE": observations},
                "CLASS_INF": {
                    "CLASS_OBJ": [
                        {
                            "@id": "cat01",
                            "CLASS": {"@code": "000", "@name": "総数"},
                        },
                        {
                            "@id": "area",
                            "CLASS": {"@code": "00000", "@name": "全国"},
                        },
                    ]
                },
            },
        }
    }


class EStatReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader = EStatReader("test-table", api_key="test-key")

    def test_read_preserves_native_monthly_frequency_by_default(self):
        data = self.reader._read_content(make_data_response())
        self.assertEqual(len(data), 2)
        self.assertEqual(set(data["period_type"]), {"month"})
        self.assertEqual(data["cat01_label"].tolist(), ["総数", "総数"])
        self.assertEqual(data["area_label"].tolist(), ["全国", "全国"])

    def test_date_bounds_are_normalized_and_applied(self):
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            start="2024-02-01",
            end="2024-02-29",
        )
        data = reader._read_content(
            make_data_response(("2024000101", "2024000202", "2024000303"))
        )
        self.assertEqual(data["DATE"].tolist(), [pd.Timestamp("2024-02-01")])

    def test_requested_category_and_area_codes_are_validated(self):
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            cdCat01="001",
            cdArea="00000",
        )
        with self.assertRaises(EStatAPIError):
            reader._read_content(make_data_response())

    def test_expected_unit_and_frequency_are_validated(self):
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            expected_unit="persons",
            expected_period_type="month",
        )
        with self.assertRaises(EStatAPIError):
            reader._read_content(make_data_response())

    def test_expected_unit_rejects_observations_without_unit_metadata(self):
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            expected_unit="%",
        )
        payload = make_data_response()
        payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"][0][
            "@unit"
        ] = None

        with self.assertRaisesRegex(EStatAPIError, "no @unit"):
            reader._read_content(payload)

    def test_api_status_error_is_not_converted_to_empty_data(self):
        payload = make_data_response()
        payload["GET_STATS_DATA"]["RESULT"] = {
            "STATUS": 403,
            "ERROR_MSG": "invalid app id",
        }
        with self.assertRaisesRegex(EStatAPIError, "STATUS=403"):
            self.reader._read_content(payload)

    def test_empty_observations_raise_an_error(self):
        payload = make_data_response()
        payload["GET_STATS_DATA"]["STATISTICAL_DATA"]["DATA_INF"]["VALUE"] = []
        with self.assertRaisesRegex(EStatAPIError, "no observations"):
            self.reader._read_content(payload)

    def test_unknown_time_code_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unsupported e-Stat time code"):
            self.reader._estat_time_to_date("2024-01")

    @patch("requests.Session.get")
    def test_http_failure_raises_without_returning_empty_dataframe(self, get):
        get.return_value = Mock(status_code=503)
        reader = EStatReader("test-table", api_key="test-key", retry_count=0)
        with self.assertRaisesRegex(EStatAPIError, "HTTP 503"):
            reader.read()
        self.assertEqual(get.call_args.kwargs["timeout"], reader.timeout)

    @patch("requests.Session.get")
    def test_transient_http_error_is_retried(self, get):
        response = Mock(status_code=200)
        response.json.return_value = make_data_response()
        get.side_effect = [Mock(status_code=503), response]
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            retry_count=1,
            pause=0,
        )
        data = reader.read()
        self.assertEqual(len(data), 2)
        self.assertEqual(get.call_count, 2)

    @patch("requests.Session.get")
    def test_api_filter_and_timeout_are_sent(self, get):
        reader = EStatReader(
            "test-table",
            api_key="test-key",
            cdCat01="000",
            timeout=7,
        )
        response = Mock(status_code=200)
        response.json.return_value = make_data_response()
        get.return_value = response

        data = reader.read()

        self.assertEqual(len(data), 2)
        self.assertEqual(get.call_args.kwargs["timeout"], 7)
        self.assertEqual(get.call_args.kwargs["params"]["cdCat01"], "000")

    @patch("requests.get")
    def test_search_no_matches_returns_an_empty_result(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {
            "GET_STATS_LIST": {
                "RESULT": {"STATUS": 300, "ERROR_MSG": "no data"}
            }
        }
        get.return_value = response
        result = EStatReader.search("no match", api_key="test-key")
        self.assertTrue(result.empty)
        self.assertEqual(list(result.columns), ["id", "stat_name", "title"])

    @patch("requests.get")
    def test_search_api_error_is_raised(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {
            "GET_STATS_LIST": {
                "RESULT": {"STATUS": 403, "ERROR_MSG": "invalid app id"}
            }
        }
        get.return_value = response
        with self.assertRaisesRegex(EStatAPIError, "STATUS=403"):
            EStatReader.search("完全失業率", api_key="test-key")

    def test_missing_api_key_is_rejected_before_request(self):
        with self.assertRaisesRegex(ValueError, "APIキー"):
            EStatReader("test-table")


if __name__ == "__main__":
    unittest.main()
