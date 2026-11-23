import copy
import unittest

from estat_pandas import (
    CatalogError,
    DatasetNotFoundError,
    get_dataset_spec,
    load_catalog,
)


class CatalogTests(unittest.TestCase):
    def test_builtin_catalog_registers_explicit_fred_style_series(self):
        catalog = load_catalog()
        self.assertEqual(
            catalog["JPN_CPI_CORE_YOY"].source["provider"],
            "estat",
        )
        self.assertEqual(
            catalog["JPN_CALL_RATE_OVERNIGHT"].source["provider"],
            "boj",
        )
        self.assertTrue(all(key.startswith("JPN_") for key in catalog))
        unemployment = catalog["JPN_UNEMPLOYMENT_RATE"]
        self.assertEqual(unemployment.frequency, "quarterly")
        self.assertEqual(unemployment.unit, "％")
        self.assertEqual(unemployment.source["filters"]["cdTab"], "02")
        self.assertEqual(
            unemployment.seasonal_adjustment,
            "not_seasonally_adjusted",
        )
        monthly_unemployment = catalog["JPN_UNEMPLOYMENT_RATE_MONTHLY"]
        self.assertEqual(monthly_unemployment.frequency, "monthly")
        self.assertEqual(monthly_unemployment.unit, "％")
        self.assertEqual(
            monthly_unemployment.seasonal_adjustment,
            "not_seasonally_adjusted",
        )
        self.assertEqual(
            monthly_unemployment.source["stats_data_id"],
            "0003005865",
        )
        self.assertEqual(
            monthly_unemployment.source["filters"]["cdCat02"],
            "08",
        )

    def test_gdp_series_use_current_2020_base_seasonally_adjusted_tables(self):
        catalog = load_catalog()
        nominal = catalog["JPN_GDP_NOMINAL_SA"]
        real = catalog["JPN_GDP_REAL_SA"]

        self.assertEqual(nominal.source["stats_data_id"], "0003109785")
        self.assertEqual(real.source["stats_data_id"], "0003109750")
        self.assertEqual(nominal.source["filters"]["cdCat01"], "11")
        self.assertEqual(real.source["filters"]["cdCat01"], "11")
        self.assertEqual(nominal.unit, "10億円")
        self.assertEqual(real.unit, "10億円")
        self.assertEqual(nominal.seasonal_adjustment, "seasonally_adjusted")
        self.assertEqual(real.seasonal_adjustment, "seasonally_adjusted")
        self.assertEqual(
            catalog["JPN_CPI_CORE_YOY"].source["filters"]["cdCat01"],
            "0161",
        )
        self.assertEqual(
            catalog["JPN_CPI_CORE_CORE_YOY"].source["filters"]["cdCat01"],
            "0178",
        )

    def test_population_series_pin_each_census_vintage_and_total_population(self):
        catalog = load_catalog()
        population = catalog["JPN_POPULATION_TOTAL"]
        segments = population.source["segments"]
        self.assertEqual(population.source["provider"], "estat")
        self.assertEqual(population.unit, "千人")
        self.assertEqual(population.frequency, "monthly")
        self.assertEqual(
            [
                (segment["start"], segment["end"])
                for segment in segments
            ],
            [
                ("1990-10-01", "2015-09-01"),
                ("2015-10-01", "2020-09-01"),
                ("2020-10-01", "2025-09-01"),
                ("2025-10-01", None),
            ],
        )
        expected = {
            "JPN_POPULATION_TOTAL_1990_2015": (
                "0004029362",
                {"cdArea": "00000", "cdCat01": "000", "cdCat02": "001"},
            ),
            "JPN_POPULATION_TOTAL_2015_BASE": (
                "0003446819",
                {
                    "cdArea": "00000",
                    "cdCat02": "000",
                    "cdCat03": "01000",
                    "cdCat04": "001",
                },
            ),
            "JPN_POPULATION_TOTAL_2020_BASE": (
                "0003443840",
                {
                    "cdArea": "00000",
                    "cdCat01": "01",
                    "cdCat02": "000",
                    "cdCat03": "01000",
                    "cdCat04": "001",
                },
            ),
            "JPN_POPULATION_TOTAL_2025_BASE": (
                "0004055903",
                {
                    "cdArea": "00000",
                    "cdCat01": "01",
                    "cdCat02": "000",
                    "cdCat03": "01000",
                    "cdCat04": "001",
                },
            ),
        }
        for key, (table_id, filters) in expected.items():
            with self.subTest(key=key):
                spec = catalog[key]
                self.assertEqual(spec.source["stats_data_id"], table_id)
                self.assertEqual(spec.source["filters"], filters)
                self.assertEqual(spec.frequency, "monthly")
                self.assertEqual(spec.unit, "千人")

    def test_unknown_dataset_key_is_not_resolved_by_search(self):
        with self.assertRaises(DatasetNotFoundError):
            get_dataset_spec("完全失業率")

    def test_catalog_rejects_missing_provider_fields(self):
        import json
        from pathlib import Path

        from estat_pandas.catalog import validate_catalog

        catalog_path = Path(__file__).parents[1] / "estat_pandas" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(catalog)
        del invalid["datasets"]["JPN_CPI_CORE_YOY"]["source"]["filters"]

        with self.assertRaisesRegex(CatalogError, "filters"):
            validate_catalog(invalid)

    def test_catalog_rejects_overlapping_estat_segments(self):
        import json
        from pathlib import Path

        from estat_pandas.catalog import validate_catalog

        catalog_path = Path(__file__).parents[1] / "estat_pandas" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(catalog)
        invalid["datasets"]["JPN_POPULATION_TOTAL"]["source"]["segments"][1][
            "start"
        ] = "2015-09-01"

        with self.assertRaisesRegex(CatalogError, "non-overlapping"):
            validate_catalog(invalid)

    def test_catalog_rejects_gaps_between_monthly_estat_segments(self):
        import json
        from pathlib import Path

        from estat_pandas.catalog import validate_catalog

        catalog_path = Path(__file__).parents[1] / "estat_pandas" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(catalog)
        invalid["datasets"]["JPN_POPULATION_TOTAL"]["source"]["segments"][1][
            "start"
        ] = "2015-11-01"

        with self.assertRaisesRegex(CatalogError, "must be contiguous"):
            validate_catalog(invalid)

    def test_catalog_rejects_classification_codes_that_conflict_with_sources(self):
        import json
        from pathlib import Path

        from estat_pandas.catalog import validate_catalog

        catalog_path = Path(__file__).parents[1] / "estat_pandas" / "catalog.json"
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        invalid = copy.deepcopy(catalog)
        invalid["datasets"]["JPN_CALL_RATE_OVERNIGHT"][
            "classifications"
        ]["database"]["code"] = "OTHER"

        with self.assertRaisesRegex(CatalogError, "database.code"):
            validate_catalog(invalid)

    def test_catalog_rejects_generic_http_and_html_sources(self):
        from estat_pandas.catalog import validate_catalog

        catalog = {
            "schema_version": 1,
            "datasets": {
                "example": {
                    "title": "Example",
                    "source": {
                        "provider": "html",
                        "url": "https://example.test/data",
                    },
                    "unit": "index",
                    "frequency": "monthly",
                    "seasonal_adjustment": "not_applicable",
                    "classifications": {},
                }
            },
        }
        with self.assertRaisesRegex(CatalogError, "source.provider"):
            validate_catalog(catalog)


if __name__ == "__main__":
    unittest.main()
