#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
DB="${BW_MONITOR_DB:-$APP_DIR/bandwidth.db}"
FAIL=0
WARN=0

ok(){ printf '[ OK ] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; WARN=$((WARN+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }

if [[ -r "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  DB="${BW_MONITOR_DB:-$DB}"
else
  fail "Missing or unreadable environment: $ENV_FILE"
fi

printf 'BW Monitor quick doctor\n%s\n' '================================================================'
for unit in bw-monitor.service bw-monitor-retention.timer; do
  if systemctl is-active --quiet "$unit"; then ok "$unit is active"; else fail "$unit is not active"; fi
done

if [[ -x "$APP_DIR/venv/bin/python3" && -f "$APP_DIR/app.py" ]]; then
  if "$APP_DIR/venv/bin/python3" -m py_compile "$APP_DIR/app.py" 2>/tmp/bwm-doctor-compile.err; then
    ok 'Application source compiles'
  else
    fail "Application compile failed: $(tr '\n' ' ' </tmp/bwm-doctor-compile.err | tail -c 500)"
  fi
else
  fail 'Application Python environment or app.py is missing'
fi
rm -f /tmp/bwm-doctor-compile.err

bind="${BW_GUNICORN_BIND:-127.0.0.1:8080}"
port="${bind##*:}"
code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 10 "http://127.0.0.1:${port}/login" || true)"
if [[ "$code" == 200 || "$code" == 302 ]]; then ok "Local /login returned HTTP $code"; else fail "Local /login returned ${code:-no response}"; fi

if [[ -f "$DB" ]]; then
  ok "Database exists: $DB ($(du -h "$DB" | awk '{print $1}'))"
else
  fail "Database is missing: $DB"
fi

for f in "$ENV_FILE" /root/bw-monitor-credentials.env; do
  [[ -e "$f" ]] || { [[ "$f" == *credentials* ]] && warn "Optional credential file is missing: $f"; continue; }
  mode="$(stat -c '%a' "$f" 2>/dev/null || echo unknown)"
  owner="$(stat -c '%U:%G' "$f" 2>/dev/null || echo unknown)"
  if [[ "$mode" == 600 && "$owner" == root:root ]]; then ok "$f permissions are 0600 root:root"; else warn "$f permissions are $mode $owner; expected 600 root:root"; fi
done

if [[ -d "$(dirname "$DB")" ]]; then
  free_kb="$(df -Pk "$(dirname "$DB")" | awk 'NR==2{print $4}')"
  if [[ "$free_kb" =~ ^[0-9]+$ ]]; then
    if ((free_kb < 1048576)); then fail "Less than 1 GiB free on DB filesystem";
    elif ((free_kb < 5242880)); then warn "Less than 5 GiB free on DB filesystem";
    else ok "Database filesystem free: $(df -h "$(dirname "$DB")" | awk 'NR==2{print $4}')"; fi
  fi
fi

workers="$(pgrep -fc '/opt/bw-monitor/bw_monitor_maintenance.py' || true)"
if ((workers > 1)); then fail "Multiple maintenance workers are running: $workers"; elif ((workers == 1)); then warn 'One maintenance worker is active'; else ok 'No maintenance worker is active'; fi

if [[ -x "$APP_DIR/db-check.sh" ]]; then
  if "$APP_DIR/db-check.sh" --no-integrity >/tmp/bwm-doctor-db.txt 2>&1; then ok 'Database metadata can be read'; else fail 'Database metadata check failed'; fi
else
  warn "$APP_DIR/db-check.sh is missing"
fi

printf '\nRecent service errors\n%s\n' '----------------------------------------------------------------'
journalctl -u bw-monitor.service -p warning -n 15 --no-pager 2>/dev/null || true
printf '\nSummary: failures=%d warnings=%d\n' "$FAIL" "$WARN"
((FAIL == 0)) || exit 2
