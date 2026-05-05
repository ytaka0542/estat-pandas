FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ① まず requirements.txt だけをコピーしてインストール
# これにより、ライブラリがコンテナのベース層にしっかり刻まれます
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ② その後に、setup.py を含むソースコード一式をコピー
COPY . .

# ③ 最後に、自作パッケージ(estat_pandas)をインストール
# これにより setup.py に書かれた依存関係（pandas_datareader等）も補完されます
RUN pip install -e .

CMD ["/bin/bash"]