#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo "==> Pulling latest from main..."
git pull origin main

echo "==> Building and restarting containers..."
docker compose build
docker compose up -d

echo "==> Done. Tailing logs (ctrl-c to exit)..."
docker compose logs -f --tail=20
