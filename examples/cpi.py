import sys
import os
import pandas as pd
from dotenv import load_dotenv
#ライブラリのインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import estat_pandas as web

def get_cpi_rate(api_key):
    """労働力調査から完全失業率を取得"""
    # 統計表ID: 0003009146
    params = {"cdCat01": "0178"}
    df_cpi = web.DataReader(
        name="0003427113",
        data_source="estat",
        api_key=api_key,
        **params
        )
    
    # unit が % の行だけ残す（＝前年比インフレ率）
    df_cpi = df_cpi[df_cpi["@unit"] == "%"].copy()
    df_cpi.to_csv("cpi0.csv", index=False, encoding="utf-8-sig")
    # 年度を数値化
    df_cpi["@time"] = df_cpi["@time"].astype(int)
    # quarter年だけ取り出す
    df_cpi = df_cpi[df_cpi["period_type"] == "quarter"].copy()
    # インフレ率を float に変換
    df_cpi["inflation"] = pd.to_numeric(df_cpi["$"], errors="coerce")
    df_cpi.to_csv("cpi.csv", index=False, encoding="utf-8-sig")
    # 必要な列だけ
    df_cpi = df_cpi[["DATE", "inflation"]]
    return df_cpi

def main():
    load_dotenv()
    APP_ID = os.getenv("ESTAT_APP_ID")
    df=get_cpi_rate(APP_ID)
    df.to_csv("urate.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    main()