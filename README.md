## インストールと準備
GitHubから直接最新版をインストールできます。

```bash
pip install --no-cache-dir git+https://github.com/ytaka0542/estat-pandas.git
```

## 使い方
基本的な使い方は以下の通りです。
```python
import estat_pandas

# 1. クライアントの準備
app_id = "あなたのappId"
client = estat_pandas.Client(app_id=app_id)

# 2. データの取得 (statsDataIdを指定)
df = client.get_data(stats_data_id="0003412307")

# 3. あとはPandasで分析するだけ！
print(df.head())
'''
# 1. クライアントの初期化（e-StatのappIdを指定）
client = estat_pandas.Client(app_id="YOUR_APP_ID")

# 2. 統計表IDを指定してデータを取得
# 例: 消費者物価指数 (0003412307)
df = client.get_data(stats_data_id="0003412307")

# 3. Pandas DataFrameとしてそのまま分析可能！
print(df.head())
```
## 免責事項
このサービスは、政府統計総合窓口(e-Stat)のAPI機能を使用していますが、サービスの内容は国によって保証されたものではありません。

---
## クレジット
本ライブラリが提供する統計データは、[政府統計総合窓口(e-Stat)](https://www.e-stat.go.jp/)のAPIを利用しています。
利用にあたっては、[e-Stat利用規約](https://www.e-stat.go.jp/api/api-info/e-stat-usage-rules)をご確認ください。