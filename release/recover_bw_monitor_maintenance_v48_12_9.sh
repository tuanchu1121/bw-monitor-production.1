#!/usr/bin/env bash
set -Eeuo pipefail

DB="${BW_MONITOR_DB:-/opt/bw-monitor/bandwidth.db}"
APP_SERVICE="${BW_MONITOR_SERVICE:-bw-monitor.service}"
RUNNER_PATTERN='/opt/bw-monitor/bw_monitor_maintenance.py'
MARKER='/run/bw-monitor-maintenance-web-offline'

say(){ printf '\n==> %s\n' "$*"; }

say "Stop automatic retention while recovering maintenance"
systemctl stop bw-monitor-retention.service >/dev/null 2>&1 || true
pkill -TERM -f '/opt/bw-monitor/bw_monitor_retention.py' 2>/dev/null || true
sleep 1
pkill -KILL -f '/opt/bw-monitor/bw_monitor_retention.py' 2>/dev/null || true

say "Stop every maintenance instance"
mapfile -t UNITS < <(systemctl list-units --all --plain --no-legend 'bw-monitor-maintenance@*.service' 2>/dev/null | awk '{print $1}' | grep -E '^bw-monitor-maintenance@[0-9]+\.service$' || true)
if ((${#UNITS[@]})); then
  systemctl stop "${UNITS[@]}" || true
else
  echo "No loaded maintenance instance found."
fi

say "Terminate orphan maintenance workers"
pkill -TERM -f "$RUNNER_PATTERN" 2>/dev/null || true
sleep 3
pkill -KILL -f "$RUNNER_PATTERN" 2>/dev/null || true

say "Recover queued/running rows"
if [[ -f "$DB" ]]; then
  DB_PATH="$DB" python3 - <<'PY'
import os, sqlite3, time
path=os.environ['DB_PATH']
conn=sqlite3.connect(path, timeout=10)
try:
    conn.execute('PRAGMA busy_timeout=10000')
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'maintenance_jobs' in tables:
        cur=conn.execute("""
          UPDATE maintenance_jobs
          SET status='error', finished_at=?,
              message='Cancelled by v48.12.6 maintenance recovery tool'
          WHERE status IN ('queued','running')
        """, (int(time.time()),))
        conn.commit()
        print(f"Recovered {max(0,cur.rowcount)} active queue row(s).")
    else:
        print('maintenance_jobs table does not exist; nothing to recover.')
finally:
    conn.close()
PY
else
  echo "Database not found: $DB"
fi

say "Restore dashboard service"
if [[ -s "$MARKER" ]]; then
  MARKED_SERVICE="$(head -n1 "$MARKER" | tr -cd 'A-Za-z0-9@_.:-')"
  [[ -n "$MARKED_SERVICE" ]] && APP_SERVICE="$MARKED_SERVICE"
fi
rm -f "$MARKER"
systemctl reset-failed "$APP_SERVICE" || true
systemctl start "$APP_SERVICE"
systemctl is-active --quiet "$APP_SERVICE"

say "Reset failed maintenance units"
if ((${#UNITS[@]})); then
  systemctl reset-failed "${UNITS[@]}" || true
fi

say "Fast SQLite probe"
set +e
timeout 20 sqlite3 "$DB" 'PRAGMA schema_version; SELECT COUNT(*) FROM sqlite_master;' 2>&1
RC=$?
set -e
case "$RC" in
  0) echo "Fast SQLite probe: PASS" ;;
  124) echo "Fast SQLite probe: TIMEOUT after 20s" >&2; exit 2 ;;
  *) echo "Fast SQLite probe: FAILED (exit $RC)" >&2; exit "$RC" ;;
esac

echo
echo "Recovery completed. Dashboard: $(systemctl is-active "$APP_SERVICE" 2>/dev/null || true)"
