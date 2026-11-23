import unittest

import pandas as pd

from estat_pandas import EStatReader


class QuarterlyAggregationTests(unittest.TestCase):
    def setUp(self):
        self.reader = EStatReader("test-table", api_key="test-key")

    @staticmethod
    def monthly_frame(values, unit="%"):
        months = pd.date_range("2024-01-01", periods=len(values), freq="MS")
        return pd.DataFrame(
            {
                "DATE": months,
                "$": values,
                "period_type": ["month"] * len(values),
                "@unit": [unit] * len(values),
                "@cat01": ["A"] * len(values),
                "cat01_label": ["Example"] * len(values),
            }
        )

    def test_percentage_mean_is_explicit_and_not_compounded(self):
        out = self.reader._add_quarter_rows(
            self.monthly_frame([1.0, 2.0, 3.0]),
            aggregation="mean",
        )
        quarter = out[out["period_type"] == "quarter"]
        self.assertEqual(len(quarter), 1)
        self.assertEqual(quarter["$"].iloc[0], 2.0)
        self.assertEqual(quarter["@time"].iloc[0], "2024000103")

    def test_compound_percentage_changes_when_explicitly_requested(self):
        out = self.reader._add_quarter_rows(
            self.monthly_frame([1.0, 2.0, 3.0]),
            aggregation="compound_percent",
        )
        quarter_value = out.loc[out["period_type"] == "quarter", "$"].iloc[0]
        expected = (1.01 * 1.02 * 1.03 - 1) * 100
        self.assertAlmostEqual(quarter_value, expected)

    def test_flow_sum_and_stock_last_are_explicit(self):
        monthly = self.monthly_frame([10, 20, 30], unit="億円")
        summed = self.reader._add_quarter_rows(monthly, aggregation="sum")
        last = self.reader._add_quarter_rows(monthly, aggregation="last")
        self.assertEqual(
            summed.loc[summed["period_type"] == "quarter", "$"].iloc[0],
            60,
        )
        self.assertEqual(
            last.loc[last["period_type"] == "quarter", "$"].iloc[0],
            30,
        )

    def test_incomplete_quarter_is_marked_missing(self):
        monthly = self.monthly_frame([10, 20])
        out = self.reader._add_quarter_rows(monthly, aggregation="mean")
        quarter_value = out.loc[out["period_type"] == "quarter", "$"].iloc[0]
        self.assertTrue(pd.isna(quarter_value))

    def test_compound_percentage_requires_percent_unit(self):
        with self.assertRaises(ValueError):
            self.reader._add_quarter_rows(
                self.monthly_frame([10, 20, 30], unit="億円"),
                aggregation="compound_percent",
            )

    def test_mixed_monthly_and_native_quarterly_data_is_rejected(self):
        monthly = self.monthly_frame([10, 20, 30])
        native_quarterly = monthly.iloc[[0]].copy()
        native_quarterly["period_type"] = "quarter"
        with self.assertRaises(ValueError):
            self.reader._add_quarter_rows(
                pd.concat([monthly, native_quarterly], ignore_index=True),
                aggregation="mean",
            )


if __name__ == "__main__":
    unittest.main()
