import sys
import os
import pandas as pd
from dotenv import load_dotenv
#ライブラリのインポート
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import estat_pandas as web

def get_unemployment_rate(api_key):
    """労働力調査から完全失業率を取得"""
    # 統計表ID: 0003009146
    df = web.DataReader("0003009146", "estat", api_key=api_key)
    # フィルタリング: 男女計(0), 完全失業率(08), 全産業(000)
    df_u = df[
        (df["@cat03"] == "0") &
        (df["@cat02"] == "08") &
        (df["@cat01"] == "000")
    ].copy()

    # 数値変換とソート
    df_u["unemployment"] = pd.to_numeric(df_u["$"], errors="coerce")
    df_u = df_u.sort_values("DATE")
    
    return df_u[["DATE", "unemployment"]]

def main():
    load_dotenv()
    APP_ID = os.getenv("ESTAT_APP_ID")
    df=get_unemployment_rate(APP_ID)
    df.to_csv("urate.csv", index=False, encoding="utf-8-sig")

if __name__ == "__main__":
    main()