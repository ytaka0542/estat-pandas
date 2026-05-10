from pandas_datareader.base import _BaseReader
import pandas as pd
import requests

# ---------------------------------------------------------
# 1. 職人クラス（e-Stat専用）
# ---------------------------------------------------------
class EStatReader(_BaseReader):
    _BASE_URL = "https://api.e-stat.go.jp/rest/3.0/app/json/"

    def __init__(self, symbols, api_key=None, lang="jp", start=None, end=None, **kwargs):
        # 1. PDR（親クラス）が認識できる標準的な引数リスト
        # これらは super().__init__ に渡す
        pdr_standard_args = [
            "start", "end", "retry_count", "pause", 
            "timeout", "session", "chunksize"
        ]

        # 2. 引数を「PDR用」と「e-Stat（その他）用」に自動仕分け
        pdr_kwargs = {}
        estat_kwargs = {}

        for k, v in kwargs.items():
            if k in pdr_standard_args:
                pdr_kwargs[k] = v
            else:
                estat_kwargs[k] = v

        # 3. 親クラスには PDR 用だけを渡す（これで TypeError が出ない）
        super(EStatReader, self).__init__(symbols=symbols, **pdr_kwargs)

        # 4. 残りはすべて e-Stat のクエリパラメータとして保持
        self.api_key = api_key
        self.lang = "J" if lang == "jp" else "E"
        self.ext_params = estat_kwargs
        self.start = start
        self.end = end

    @property
    def url(self):
        """PDRが内部で呼ぶURL。ここを上書きすれば安全にURLを指定できる"""
        return self._BASE_URL + "getStatsData"

    def _get_params(self, symbols):
        return {
            "appId": self.api_key,
            "statsDataId": symbols,
            "metaGetFlg": "Y",
            "lang": self.lang,
            **self.ext_params
        }

    def read(self):
        params = self._get_params(self.symbols)
        response = requests.get(self.url, params=params, timeout=self.timeout)
        if response.status_code != 200:
            raise Exception(f"e-Stat API Error: {response.status_code}")
        return self._read_content(response.json())

    def _read_content(self, out):
        """JSONをパースしてDataFrameにする一連のロジック"""
        res_root = out.get("GET_STATS_DATA", {})
        
        # エラーチェック
        status = res_root.get("RESULT", {}).get("STATUS")
        if status != 0 and str(status) != "0":
            msg = res_root.get("RESULT", {}).get("ERROR_MSG")
            print(f"API Warning: {msg}")
            return pd.DataFrame()

        # 1. データ本体
        data_inf = res_root.get("STATISTICAL_DATA", {}).get("DATA_INF", {})
        values = data_inf.get("VALUE", [])
        if not values:
            return pd.DataFrame()
        df = pd.DataFrame(values)

        # 2. メタデータ（ラベル辞書）
        class_inf = res_root.get("STATISTICAL_DATA", {}).get("CLASS_INF", {})
        class_objs = class_inf.get("CLASS_OBJ", [])
        label_dict = self._build_label_dict_from_meta(class_objs)

        # 3. ラベル付与
        df = self._apply_labels(df, label_dict)

        # 4. 時間変換
        df["DATE"] = df["@time"].apply(self._estat_time_to_date)
        df["period_type"] = df["@time"].apply(self._estat_time_type)
        if self.start is not None:
            df = df[df["DATE"] >= self.start]
        if self.end is not None:
            df = df[df["DATE"] <= self.end]

        # 5. 四半期計算
        df = self._add_quarter_rows(df)

        return df

    # --- ヘルパーメソッド群 ---
    def _build_label_dict_from_meta(self, class_objs):
        label_dict = {}
        if isinstance(class_objs, dict): class_objs = [class_objs]
        for obj in class_objs:
            cat_id = obj["@id"]
            classes = obj.get("CLASS", [])
            if isinstance(classes, dict):
                label_dict[cat_id] = {classes["@code"]: classes["@name"]}
            elif isinstance(classes, list):
                label_dict[cat_id] = {c["@code"]: c["@name"] for c in classes}
        return label_dict

    def _apply_labels(self, df, label_dict):
        for col in df.columns:
            cat_key = col.replace("@", "")
            if cat_key in label_dict:
                df[f"{cat_key}_label"] = df[col].map(label_dict[cat_key])
        return df

    def _estat_time_to_date(self, code):
        code = str(code)
        if len(code) == 10 and code.isdigit():
            year = int(code[:4])
            mid = code[4:6]
            start_month = code[6:8]
            q = code[-4:]
            quarter_map = {"0103": 1, "0406": 4, "0709": 7, "1012": 10}
            if q in quarter_map: return pd.Timestamp(year=year, month=quarter_map[q], day=1)
            elif mid == "00" and start_month == "00": return pd.Timestamp(year=year, month=1, day=1)
            elif mid == "10" and start_month == "00": return pd.Timestamp(year=year, month=4, day=1)
            elif mid == "00" and start_month != "00": return pd.Timestamp(year=year, month=int(start_month), day=1)
        return None

    def _estat_time_type(self, code):
        code = str(code)
        if len(code) == 10 and code.isdigit():
            q = code[-4:]
            mid = code[4:6]
            sm = code[6:8]
            em = code[8:10]
            if q in ("0103", "0406", "0709", "1012"): return "quarter"
            if mid == "00" and sm == "00": return "year"
            if mid == "10" and sm == "00": return "fiscal_year"
            if sm == em and sm != "00": return "month"
        return "unknown"

    def _add_quarter_rows(self, df):
        if (df["period_type"] == "quarter").any(): return df
        quarter_rows = []
        cat_cols = [c for c in df.columns if c.startswith("@cat")]
        area_cols = [c for c in df.columns if c.startswith("@area")]
        group_keys = cat_cols + area_cols + ["@unit"]
        label_cols = [c for c in df.columns if c.endswith("_label")]

        for keys, g in df.groupby(group_keys):
            g_month = g[(g["period_type"] == "month")].copy()
            if g_month.empty: continue
            g_month["$"] = pd.to_numeric(g_month["$"], errors="coerce")
            m = g_month.set_index("DATE")["$"] / 100
            # --- %か否か ---
            if g_month["@unit"].iloc[0] in ["%", "％"]:
                # パーセント → 四半期リターン（複利）
                m = m / 100
                q = (1 + m).resample("QS-JAN").prod() - 1
                q = q * 100
            else:
                # パーセント以外 → 四半期平均
                q = m.resample("QS-JAN").mean()
            for date, value in q.items():
                row = {"DATE": date, "$": value, "period_type": "quarter"}
                for col in group_keys + label_cols: row[col] = g.iloc[0][col]
                y = date.year
                mo = date.month
                row["@time"] = {1: f"{y}000103", 4: f"{y}000406", 7: f"{y}000709", 10: f"{y}001012"}[mo]
                quarter_rows.append(row)
        return pd.concat([df, pd.DataFrame(quarter_rows)], ignore_index=True).sort_values("DATE").reset_index(drop=True)
    @classmethod
    def search(cls, keyword, api_key, lang="jp", **kwargs):
        """検索機能（クラスメソッド）"""
        base_url = "https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList"
        params = {"appId": api_key, "lang": "J" if lang == "jp" else "E", "searchWord": keyword, **kwargs}
        res = requests.get(base_url, params=params).json()
        try:
            items = res["GET_STATS_LIST"]["DATALIST_INF"]["TABLE_INF"]
            if isinstance(items, dict): items = [items]
            return pd.DataFrame([{"id": t["@id"], "stat_name": t["STAT_NAME"]["$"], "title": t["TITLE"]["$"]} for t in items])
        except: return pd.DataFrame()
# ---------------------------------------------------------
# 2. 受付窓口（ユーザーが使う関数）
# ---------------------------------------------------------
def DataReader(name, data_source=None, *args, **kwargs):
    """
    web.DataReader(...) として呼ばれる「何でも屋」の窓口
    """
    if data_source == "estat":
        # .read() を付けずに、クラスのインスタンス（読取機）だけを返す
        return EStatReader(symbols=name, **kwargs).read()
    
    import pandas_datareader.data as pdr
    return pdr.DataReader(name, data_source, *args, **kwargs)

def search(keyword, api_key, lang="jp", **kwargs):
    """web.search(...) として呼ばれる検索窓口"""
    # EStatReader内に実装したクラスメソッドを呼び出す
    return EStatReader.search(keyword, api_key, lang, **kwargs)