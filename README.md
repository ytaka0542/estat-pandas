# estat-pandas

`estat-pandas` loads explicitly registered economic time series from e-Stat,
the Bank of Japan, or a specifically configured official CSV source. All
sources use the same `load(dataset_key, start, end)` interface and return a
validated pandas DataFrame.

## Install for development

From this directory, install the package in editable mode:

```bash
python -m pip install -e .
```

## Load a registered series

```python
from estat_pandas import load

cpi = load(
    "JPN_CPI_CORE_YOY",
    start="2024-01-01",
    end="2024-12-01",
)

print(cpi[["DATE", "value", "unit", "frequency"]])

population = load(
    "JPN_POPULATION_TOTAL",
    start="2010-01-01",
    end="2025-12-01",
)
```

Catalog keys use descriptive, FRED-inspired `JPN_<CONCEPT>_<DETAIL>` names.
They are local catalog keys, not FRED series IDs.

Registered series cover:

- GDP: nominal and real, seasonally adjusted, quarterly
- Expenditure components: household consumption, gross fixed capital
  formation, government consumption, and net exports (nominal and real,
  seasonally adjusted, quarterly)
- Prices: headline CPI, CPI excluding fresh food, and CPI excluding fresh food
  and energy (year-over-year, monthly)
- Labor: unemployment rate (monthly and quarterly), employment, and
  labor-force participation rates (quarterly)
- Population: national total population (`JPN_POPULATION_TOTAL`), with monthly
  census-base vintages joined at explicit, non-overlapping date boundaries
- Money: M2 and seasonally adjusted monetary base (monthly)
- Interest and exchange rates: overnight call rate, base discount/lending
  rate, and USD/JPY central rate

The GDP entries use the current 2020-base e-Stat tables. The real GDP and
expenditure series are chain-volume measures; expenditure components should
not be assumed to add exactly because chain-volume measures are not generally
additive.
Population values are absolute counts in thousands, not an index rescaled to a
base year. The census reference identifies the estimate vintage; the segments
join the source tables to provide one monthly series and do not apply a scale
adjustment. The vintage-specific keys remain available to inspect each table.

The common columns are `DATE`, `value`, `dataset_key`, `provider`,
`series_code`, `unit`, `frequency`, and `seasonal_adjustment`. Provider
classification labels and other source metadata are retained as additional
columns. Date bounds are inclusive; results are sorted by date and series code.
Observations keep the source's native frequency; `load()` does not aggregate
or resample them.
An unknown key, invalid response, metadata mismatch, or empty requested period
raises an explicit error. The loader never chooses a series from a keyword
search and never falls back to another provider.

## e-Stat API key

Set `ESTAT_APP_ID` in the environment before loading an e-Stat dataset:

```bash
export ESTAT_APP_ID="your-app-id"
```

The key is only needed for e-Stat. Bank of Japan and CSV providers do not read
it.

## Dataset catalog

The packaged catalog is [estat_pandas/catalog.json](estat_pandas/catalog.json).
Each entry fixes its provider, source identifiers and filters, classification
codes and labels, unit, native frequency, and seasonal-adjustment status.
Segmented e-Stat entries can explicitly join multiple tables into one logical
series; their per-segment identifiers, classifications, and date boundaries
are validated before data is returned.
Catalog entries are validated before a provider is called.

For example, an e-Stat entry pins the table and filters rather than relying on
a search result:

```json
{
  "source": {
    "provider": "estat",
    "stats_data_id": "0003427113",
    "filters": {
      "cdArea": "00000",
      "cdTab": "3",
      "cdCat01": "0161"
    }
  },
  "unit": "%",
  "frequency": "monthly",
  "seasonal_adjustment": "not_seasonally_adjusted"
}
```

Supported frequency values are `daily`, `monthly`, `quarterly`, `annual`,
`fiscal_year`, and `irregular`. Seasonal adjustment must be explicitly marked
`seasonally_adjusted`, `not_seasonally_adjusted`, or `not_applicable`.

## Providers

- **e-Stat** uses `stats_data_id` and exact API filters. `ESTAT_APP_ID` is
  required. Returned unit, frequency, classification codes, and labels are
  checked against the catalog.
- **Bank of Japan** uses the exact database and series code. Its metadata,
  frequency, unit, and returned series codes are checked against the catalog.
- **Official CSV** entries must specify an HTTPS URL, series code, date/value
  columns, date format, encoding, and delimiter. If classifications are
  present, the exact CSV column for each classification must also be declared.
  The provider reads CSV only; it does not infer Excel or HTML layouts. For a
  non-flat source, add a dedicated parser for that source instead of a generic
  format guesser.

To register an official CSV series, add a catalog entry with a source such as:

```json
{
  "source": {
    "provider": "csv",
    "url": "https://official.example.jp/data.csv",
    "series_code": "SERIES-001",
    "date_column": "month",
    "date_format": "%Y-%m",
    "value_column": "value",
    "encoding": "utf-8",
    "delimiter": ",",
    "classification_columns": {
      "area": "area_code"
    }
  },
  "classifications": {
    "area": {
      "code": "00000",
      "label": "National"
    }
  }
}
```

The URL and parsing details must identify the official CSV for that series;
the example URL above is illustrative and must not be used as a real source.

## Candidate search

Search results are for human review and do not register or load a dataset:

```python
import os

from estat_pandas import search, search_boj

estat_candidates = search("完全失業率", api_key=os.environ["ESTAT_APP_ID"])
boj_candidates = search_boj("FM01")
```

After confirming a table and series, add the exact selection to the catalog.
`load()` accepts catalog keys only.

## Compatibility

The lower-level `DataReader`, `EStatReader`, and e-Stat `search()` interfaces
remain available for existing scripts. New data-loading code should use the
catalog-backed `load()` API so provider selection and output validation are
consistent.

## Run tests

From this directory, run:

```bash
./test.sh
```

This runs offline unit tests and needs neither an e-Stat API key nor live
provider access. Docker Compose is used by the script.

Please check the [e-Stat API terms of use](https://www.e-stat.go.jp/api/api-info/e-stat-usage-rules)
when using e-Stat data.

## Install the pre-commit hook

Install the local test hook once per clone:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install pre-commit
pre-commit install
```

After installation, commits run `./test.sh` automatically.
