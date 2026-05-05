#!/bin/bash
set -e

# ビルドと起動
docker compose up -d --build

# 起動したコンテナにbashで入る
# コンテナを「bash」を起動させた状態で新しく立ち上げる
docker compose run --rm test_env bash