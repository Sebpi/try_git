#!/bin/sh
set -e

# Runs as root only long enough to fix ownership on the mounted volume, then
# hands off to the unprivileged appuser -- same pattern as stock-picker's
# entrypoint (see its CLAUDE.md "Deploy / runtime").
mkdir -p "${DATA_DIR:-/app/data}"
chown -R appuser:appuser "${DATA_DIR:-/app/data}"

cd /app/backend
exec gosu appuser uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}"
