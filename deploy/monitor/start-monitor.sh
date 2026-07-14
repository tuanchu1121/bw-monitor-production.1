#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
BIND="${BW_GUNICORN_BIND:-127.0.0.1:8080}"
WORKERS="${BW_GUNICORN_WORKERS:-4}"
THREADS="${BW_GUNICORN_THREADS:-4}"
TIMEOUT="${BW_GUNICORN_TIMEOUT:-300}"
GRACEFUL_TIMEOUT="${BW_GUNICORN_GRACEFUL_TIMEOUT:-60}"
KEEPALIVE="${BW_GUNICORN_KEEPALIVE:-5}"
MAX_REQUESTS="${BW_GUNICORN_MAX_REQUESTS:-2000}"
MAX_REQUESTS_JITTER="${BW_GUNICORN_MAX_REQUESTS_JITTER:-200}"
ACCESS_LOG="${BW_GUNICORN_ACCESS_LOG:-}"
ERROR_LOG="${BW_GUNICORN_ERROR_LOG:--}"
PRELOAD="${BW_GUNICORN_PRELOAD:-1}"

cd "$APP_DIR"

args=(
  --chdir "$APP_DIR"
  --bind "$BIND"
  --workers "$WORKERS"
  --worker-class gthread
  --threads "$THREADS"
  --timeout "$TIMEOUT"
  --graceful-timeout "$GRACEFUL_TIMEOUT"
  --keep-alive "$KEEPALIVE"
  --max-requests "$MAX_REQUESTS"
  --max-requests-jitter "$MAX_REQUESTS_JITTER"
  --worker-tmp-dir /run/bw-monitor
  --control-socket /run/bw-monitor/gunicorn.ctl
  --error-logfile "$ERROR_LOG"
  --capture-output
  --log-level "${BW_GUNICORN_LOG_LEVEL:-info}"
)

if [[ "$PRELOAD" == "1" ]]; then
  args+=(--preload)
fi

if [[ -n "$ACCESS_LOG" ]]; then
  args+=(--access-logfile "$ACCESS_LOG")
fi

exec "$APP_DIR/venv/bin/gunicorn" "${args[@]}" app:app
