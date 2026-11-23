# estat-pandas

`estat-pandas` reads e-Stat API tables into pandas DataFrames. The reader keeps
the source frequency by default and validates requested category filters,
metadata, and time codes.

## Installation

```bash
pip install --no-cache-dir git+https://github.com/ytaka0542/estat-pandas.git
```

## API key

Set the e-Stat application ID in an environment variable instead of embedding
it in source code:

```bash
export ESTAT_APP_ID="your-app-id"
```

## Read a precisely selected series

```python
import os

from estat_pandas import DataReader

api_key = os.environ["ESTAT_APP_ID"]

unemployment = DataReader(
    "0003009146",
    "estat",
    api_key=api_key,
    cdArea="00000",  # 全国
    cdCat01="000",   # 全産業
    cdCat02="08",    # 完全失業率
    cdCat03="0",     # 男女計
    expected_unit="％",
    expected_period_type="quarter",
)
```

The returned DataFrame retains e-Stat columns such as `@time`, `$`, `@unit`,
and category codes, and adds labels, `DATE`, and `period_type`. Category filters,
when supplied, are checked against the returned codes. `expected_unit` and
`expected_period_type` can be used to reject an unexpected series definition.

## Frequency conversion is explicit

Monthly observations are not converted automatically. If quarterly values are
appropriate for the series, specify the aggregation rule:

```python
cpi_quarterly = DataReader(
    "0003427113",
    "estat",
    api_key=api_key,
    cdArea="00000",  # 全国
    cdTab="3",       # 前年同月比
    cdCat01="0178",
    expected_unit="%",
    expected_period_type="month",
    quarterly_aggregation="mean",
)
cpi_quarterly = cpi_quarterly[
    cpi_quarterly["period_type"] == "quarter"
]
```

Supported rules are `mean`, `sum`, `last`, and `compound_percent`. The caller
is responsible for choosing a rule that matches the statistic's meaning.
`mean`, `sum`, and `compound_percent` require all three monthly observations;
otherwise the quarterly value is missing. `last` uses only the quarter-end
month. Native-frequency observations remain in the result alongside generated
quarters.

## Search

Search is for reviewing candidate tables; it does not select a table or series
for subsequent requests.

```python
from estat_pandas import search

candidates = search("完全失業率", api_key=api_key)
```

## Errors

Invalid API responses, API errors, missing observations, unexpected metadata,
and unsupported time codes raise `EStatAPIError` or `ValueError`. Missing
observations are not replaced with zero.

Please check the [e-Stat API terms of use](https://www.e-stat.go.jp/api/api-info/e-stat-usage-rules).

## Run tests

From this directory, run:

```bash
./test.sh
```

The script builds the Docker image if needed, runs the offline unit and
quarterly aggregation tests, and removes the test container afterward. Docker
Compose is required; the tests do not need an e-Stat API key.

## Install the pre-commit hook

The test hook configuration is shared through `.pre-commit-config.yaml`.
Install it once in each local clone:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install pre-commit
pre-commit install
```

After installation, commits run `./test.sh` automatically.
