#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="/etc/default/bw-monitor"
STATE_FILE="/run/bw-monitor-health-watch.failures"
[[ -r "$ENV_FILE" ]] && { set -a; . "$ENV_FILE"; set +a; }

bind="${BW_GUNICORN_BIND:-127.0.0.1:8080}"
port="${bind##*:}"
[[ "$port" =~ ^[0-9]+$ ]] || port="${BW_PUBLIC_PORT:-8080}"
url="http://127.0.0.1:${port}/livez"

if curl -fsS --connect-timeout 2 --max-time 4 "$url" >/dev/null 2>&1; then
  printf '0\n' > "$STATE_FILE"
  exit 0
fi

failures=0
[[ -r "$STATE_FILE" ]] && read -r failures < "$STATE_FILE" || true
[[ "$failures" =~ ^[0-9]+$ ]] || failures=0
failures=$((failures + 1))
printf '%s\n' "$failures" > "$STATE_FILE"
logger -t bw-monitor-health-watch "live endpoint failed (${failures}/2): ${url}"

if (( failures >= 2 )); then
  logger -t bw-monitor-health-watch "restarting bw-monitor.service after consecutive live endpoint failures"
  systemctl restart bw-monitor.service
  printf '0\n' > "$STATE_FILE"
fi
