#!/bin/bash
set -e

cd "$(dirname "$0")"

echo "=== Stopping containers ==="
docker compose down

echo "=== Loading images ==="
docker load -i agent-research-app.tar.gz
docker load -i agent-research-web.tar.gz

echo "=== Starting containers ==="
docker compose up -d

echo "=== Done ==="
docker compose ps
