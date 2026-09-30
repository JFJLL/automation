#!/usr/bin/env bash
set -euo pipefail

cd /opt/automation
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi
exec uvicorn sync_console.app.main:app \
  --host 127.0.0.1 \
  --port 8088 \
  --workers 1
