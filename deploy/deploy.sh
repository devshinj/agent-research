#!/bin/bash
set -e

cd "$(dirname "$0")"

# --clean 옵션: 모델 삭제 후 재학습 (DB 유저 데이터는 유지)
CLEAN_MODELS=false
if [ "$1" = "--clean" ]; then
    CLEAN_MODELS=true
fi

echo "=== Stopping containers ==="
docker compose down

if [ "$CLEAN_MODELS" = true ]; then
    echo "=== Cleaning model files ==="
    docker run --rm -v app-data:/app/data alpine sh -c \
        "rm -rf /app/data/models/* && echo 'Models deleted'" 2>/dev/null || true
    echo "=== Model cleanup done (DB and user data preserved) ==="
fi

echo "=== Loading images ==="
docker load -i agent-research-app.tar.gz
docker load -i agent-research-web.tar.gz

echo "=== Starting containers ==="
docker compose up -d

echo "=== Done ==="
docker compose ps
