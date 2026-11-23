#!/usr/bin/env bash
set -euo pipefail

# ビルドと起動
docker compose up -d --build

# 起動したコンテナにbashで入る
docker compose exec test_env bash