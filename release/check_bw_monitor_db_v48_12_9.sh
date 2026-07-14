#!/usr/bin/env bash
set -u
DB="${BW_MONITOR_DB:-/opt/bw-monitor/bandwidth.db}"
MODE="${1:-fast}"

printf 'Database: %s\n' "$DB"
ls -lh "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true
printf '\nMaintenance processes:\n'
ps -eo pid,etime,stat,cmd | grep -E '[b]w_monitor_(maintenance|retention).py' || true
printf '\nOpen database handles:\n'
fuser -v "$DB" "$DB-wal" "$DB-shm" 2>/dev/null || true

printf '\nFast probe:\n'
timeout 20 sqlite3 "$DB" 'PRAGMA schema_version; SELECT COUNT(*) FROM sqlite_master;' 2>&1
RC=$?
printf 'FAST_EXIT=%s\n' "$RC"
if [[ "$RC" -eq 124 ]]; then
  echo 'RESULT: fast probe timed out. The DB is busy/locked or storage is stalled.'
elif [[ "$RC" -ne 0 ]]; then
  echo 'RESULT: fast probe failed.'
else
  echo 'RESULT: fast probe passed.'
fi

FINAL_RC="$RC"
if [[ "$MODE" == '--quick-check' || "$MODE" == 'quick' ]]; then
  printf '\nPRAGMA quick_check (up to 10 minutes):\n'
  OUT="/tmp/bw-monitor-quick-check.$$.txt"
  timeout 600 sqlite3 "$DB" 'PRAGMA quick_check;' >"$OUT" 2>&1
  QRC=$?
  cat "$OUT"
  rm -f "$OUT"
  printf 'QUICK_CHECK_EXIT=%s\n' "$QRC"
  FINAL_RC="$QRC"
  if [[ "$QRC" -eq 0 ]]; then
    echo 'RESULT: quick_check completed.'
  elif [[ "$QRC" -eq 124 ]]; then
    echo 'RESULT: quick_check timed out after 600 seconds. Blank output alone is not a PASS.'
  else
    echo 'RESULT: quick_check failed.'
  fi
fi

exit "$FINAL_RC"
