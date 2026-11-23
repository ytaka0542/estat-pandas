import unittest
from unittest.mock import patch

import pandas as pd

from estat_pandas import (
    DataValidationError,
    DatasetNotFoundError,
    DatasetSpec,
    NoDataError,
    load,
)
from estat_pandas.providers.csv import CSVProvider


def make_spec(provider="csv"):
    source = {
        "provider": provider,
        "series_code": "SERIES-1",
    }
    if provider == "csv":
        source.update(
            {
                "url": "https://example.test/series.csv",
                "date_column": "date",
                "date_format": "%Y-%m-%d",
                "value_column": "amount",
                "encoding": "utf-8",
                "delimiter": ",",
            }
        )
    return DatasetSpec(
        key="test.series",
        title="Test series",
        source=source,
        unit="index",
        frequency="monthly",
        seasonal_adjustment="not_applicable",
        classifications={},
    )


class StaticProvider:
    def __init__(self, frame):
        self.frame = frame
        self.requested_bounds = None

    def fetch(self, dataset, start, end):
        self.requested_bounds = (start, end)
        return self.frame.copy()


class LoadTests(unittest.TestCase):
    def test_load_returns_sorted_canonical_data_and_applies_inclusive_bounds(self):
        spec = make_spec()
        provider = StaticProvider(
            pd.DataFrame(
                {
                    "DATE": ["2024-03-01", "2024-01-01", "2024-02-01"],
                    "value": ["3.5", "1.5", "2.5"],
                }
            )
        )
        with (
            patch("estat_pandas.loader.get_dataset_spec", return_value=spec),
            patch.dict("estat_pandas.loader._PROVIDERS", {"csv": provider}),
        ):
            frame = load("test.series", "2024-01-01", "2024-02-01")

        self.assertEqual(frame["DATE"].tolist(), list(pd.to_datetime(
            ["2024-01-01", "2024-02-01"]
        )))
        self.assertEqual(frame["value"].tolist(), [1.5, 2.5])
        self.assertEqual(frame["dataset_key"].unique().tolist(), ["test.series"])
        self.assertEqual(frame["provider"].unique().tolist(), ["csv"])
        self.assertEqual(frame["seasonal_adjustment"].unique().tolist(), ["not_applicable"])
        self.assertEqual(provider.requested_bounds[0], pd.Timestamp("2024-01-01"))

    def test_invalid_values_and_duplicate_series_dates_are_rejected(self):
        spec = make_spec()
        invalid = StaticProvider(
            pd.DataFrame({"DATE": ["2024-01-01"], "value": ["not numeric"]})
        )
        duplicate = StaticProvider(
            pd.DataFrame(
                {
                    "DATE": ["2024-01-01", "2024-01-01"],
                    "value": [1, 2],
                    "series_code": ["S", "S"],
                }
            )
        )
        with patch("estat_pandas.loader.get_dataset_spec", return_value=spec):
            with patch.dict("estat_pandas.loader._PROVIDERS", {"csv": invalid}):
                with self.assertRaises(DataValidationError):
                    load("test.series")
            with patch.dict("estat_pandas.loader._PROVIDERS", {"csv": duplicate}):
                with self.assertRaisesRegex(DataValidationError, "duplicate"):
                    load("test.series")

    def test_empty_requested_range_raises_no_data(self):
        spec = make_spec()
        provider = StaticProvider(
            pd.DataFrame({"DATE": ["2024-01-01"], "value": [1]})
        )
        with (
            patch("estat_pandas.loader.get_dataset_spec", return_value=spec),
            patch.dict("estat_pandas.loader._PROVIDERS", {"csv": provider}),
        ):
            with self.assertRaises(NoDataError):
                load("test.series", start="2025-01-01")

    def test_invalid_range_fails_before_provider_request(self):
        spec = make_spec()
        provider = StaticProvider(pd.DataFrame({"DATE": [], "value": []}))
        with (
            patch("estat_pandas.loader.get_dataset_spec", return_value=spec),
            patch.dict("estat_pandas.loader._PROVIDERS", {"csv": provider}),
        ):
            with self.assertRaisesRegex(ValueError, "on or before"):
                load("test.series", "2024-02-01", "2024-01-01")
        self.assertIsNone(provider.requested_bounds)

    def test_unregistered_key_is_not_sent_to_a_provider(self):
        with patch(
            "estat_pandas.loader.get_dataset_spec",
            side_effect=DatasetNotFoundError("missing"),
        ):
            with self.assertRaises(DatasetNotFoundError):
                load("not-registered")

    def test_registered_csv_provider_returns_shared_data_contract(self):
        spec = make_spec()
        response = type("Response", (), {"content": b"date,amount\n2024-01-01,3\n"})()
        with (
            patch("estat_pandas.loader.get_dataset_spec", return_value=spec),
            patch.dict("estat_pandas.loader._PROVIDERS", {"csv": CSVProvider()}),
            patch(
                "estat_pandas.providers.csv.get_response",
                return_value=response,
            ),
        ):
            frame = load("test.series")

        self.assertEqual(frame["value"].tolist(), [3])
        self.assertEqual(frame["provider"].tolist(), ["csv"])
        self.assertEqual(frame["unit"].tolist(), ["index"])


if __name__ == "__main__":
    unittest.main()
