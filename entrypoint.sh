#!/bin/sh
set -e

# Fix data directory permissions for bind mounts.
# This runs as root before switching to the non-root appuser.
DATA_DIR="$(dirname "${T212_DB_PATH:-/app/data/monitor.db}")"
mkdir -p "$DATA_DIR"
chown -R appuser:appgroup "$DATA_DIR" 2>/dev/null || true

# Switch to non-root user and run the application.
exec gosu appuser:appgroup "$@"
