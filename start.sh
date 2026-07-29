#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/crime-ai-api"

exec gunicorn \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --timeout 120 \
  wsgi:app
