#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
DB="${BW_MONITOR_DB:-$APP_DIR/bandwidth.db}"
MODE="quick"
TIMEOUT_SECONDS="${BW_DB_CHECK_TIMEOUT:-60}"
NO_INTEGRITY=0
JSON=0

usage() {
  cat <<'USAGE'
Usage: db-check.sh [options]

Read-only SQLite health and inventory check.

Options:
  --db PATH          Database path. Default: /opt/bw-monitor/bandwidth.db
  --timeout SEC      Abort integrity scan after this many seconds. Default: 60
  --full             Run PRAGMA integrity_check instead of quick_check
  --no-integrity     Show metadata/counts only; skip quick/integrity check
  --json             Emit JSON instead of the human-readable report
  -h, --help         Show this help

The script never VACUUMs, migrates, deletes, or writes application data.
USAGE
}
while (($#)); do
  case "$1" in
    --db) DB="${2:?missing value}"; shift 2 ;;
    --timeout) TIMEOUT_SECONDS="${2:?missing value}"; shift 2 ;;
    --full) MODE="full"; shift ;;
    --no-integrity) NO_INTEGRITY=1; shift ;;
    --json) JSON=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

if [[ -r "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  [[ "$DB" == "$APP_DIR/bandwidth.db" ]] && DB="${BW_MONITOR_DB:-$DB}"
fi
[[ "$TIMEOUT_SECONDS" =~ ^[0-9]+$ ]] && ((TIMEOUT_SECONDS >= 1 && TIMEOUT_SECONDS <= 86400)) || {
  echo "Invalid timeout: $TIMEOUT_SECONDS" >&2; exit 2;
}
[[ -f "$DB" ]] || { echo "Database not found: $DB" >&2; exit 2; }
PYTHON="$APP_DIR/venv/bin/python3"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3 || true)"
[[ -n "$PYTHON" ]] || { echo 'python3 is required' >&2; exit 2; }

DB_PATH="$DB" CHECK_MODE="$MODE" CHECK_TIMEOUT="$TIMEOUT_SECONDS" NO_INTEGRITY="$NO_INTEGRITY" JSON_OUTPUT="$JSON" "$PYTHON" - <<'PY_DB_CHECK'
import json, os, sqlite3, sys, time
from pathlib import Path

path = Path(os.environ['DB_PATH'])
mode = os.environ['CHECK_MODE']
timeout = int(os.environ['CHECK_TIMEOUT'])
no_integrity = os.environ['NO_INTEGRITY'] == '1'
json_output = os.environ['JSON_OUTPUT'] == '1'
started = time.monotonic()
result = {
    'database': str(path),
    'database_bytes': path.stat().st_size,
    'wal_bytes': Path(str(path) + '-wal').stat().st_size if Path(str(path) + '-wal').exists() else 0,
    'shm_bytes': Path(str(path) + '-shm').stat().st_size if Path(str(path) + '-shm').exists() else 0,
    'mode': 'metadata-only' if no_integrity else mode,
    'integrity': 'skipped' if no_integrity else None,
    'timed_out': False,
    'metadata': {},
    'counts': {},
    'errors': [],
}
important = [
    'node_stats', 'vm_perf', 'node_inventory', 'vm_inventory',
    'vm_abuse_state', 'vm_abuse_events', 'vm_abuse_incidents',
    'api_keys', 'api_access_logs', 'api_management_events',
    'maintenance_jobs', 'retention_runs'
]
try:
    uri = 'file:' + str(path) + '?mode=ro'
    conn = sqlite3.connect(uri, uri=True, timeout=5)
    conn.execute('PRAGMA query_only=ON')
    conn.execute('PRAGMA busy_timeout=5000')
    deadline = time.monotonic() + timeout
    def progress():
        return 1 if time.monotonic() > deadline else 0
    conn.set_progress_handler(progress, 20000)
    scalar_pragmas = ['journal_mode','page_size','page_count','freelist_count','user_version','schema_version','wal_autocheckpoint']
    for name in scalar_pragmas:
        try:
            row = conn.execute(f'PRAGMA {name}').fetchone()
            result['metadata'][name] = row[0] if row else None
        except Exception as exc:
            result['metadata'][name] = f'ERROR: {exc}'
    result['metadata']['sqlite_version'] = sqlite3.sqlite_version
    result['metadata']['table_count'] = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    result['metadata']['index_count'] = conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for table in important:
        if table in existing:
            try:
                result['counts'][table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
            except Exception as exc:
                result['counts'][table] = f'ERROR: {exc}'
    if not no_integrity:
        pragma = 'integrity_check' if mode == 'full' else 'quick_check'
        try:
            rows = [str(r[0]) for r in conn.execute(f'PRAGMA {pragma}')]
            result['integrity'] = 'ok' if rows == ['ok'] else rows
        except sqlite3.OperationalError as exc:
            if 'interrupted' in str(exc).lower():
                result['integrity'] = 'timeout'
                result['timed_out'] = True
            else:
                raise
    conn.close()
except Exception as exc:
    result['errors'].append(f'{type(exc).__name__}: {exc}')
result['elapsed_seconds'] = round(time.monotonic() - started, 3)
page_size = result['metadata'].get('page_size')
freelist = result['metadata'].get('freelist_count')
if isinstance(page_size, int) and isinstance(freelist, int):
    result['metadata']['reusable_free_bytes'] = page_size * freelist

if json_output:
    print(json.dumps(result, indent=2, sort_keys=True))
else:
    def size(n):
        units=['B','KiB','MiB','GiB','TiB']; x=float(n)
        for u in units:
            if x < 1024 or u == units[-1]: return f'{x:.2f} {u}'
            x /= 1024
    print('BW Monitor SQLite health report')
    print('=' * 64)
    print(f"Database:             {result['database']}")
    print(f"Database size:        {size(result['database_bytes'])}")
    print(f"WAL size:             {size(result['wal_bytes'])}")
    print(f"SHM size:             {size(result['shm_bytes'])}")
    for key in ['sqlite_version','journal_mode','page_size','page_count','freelist_count','reusable_free_bytes','table_count','index_count','user_version','schema_version','wal_autocheckpoint']:
        if key in result['metadata']:
            value=result['metadata'][key]
            if key == 'reusable_free_bytes' and isinstance(value, int): value=size(value)
            print(f"{key.replace('_',' ').title()+':':22} {value}")
    print('\nImportant table row counts')
    print('-' * 64)
    for k,v in result['counts'].items(): print(f'{k:30} {v}')
    print('\nIntegrity scan')
    print('-' * 64)
    print(f"Mode:                 {result['mode']}")
    print(f"Result:               {result['integrity']}")
    print(f"Elapsed:              {result['elapsed_seconds']}s")
    if result['errors']:
        print('\nErrors')
        for err in result['errors']: print(f'- {err}')

if result['errors']:
    sys.exit(2)
if result['timed_out']:
    sys.exit(124)
if isinstance(result['integrity'], list) or result['integrity'] not in ('ok','skipped'):
    sys.exit(3)
PY_DB_CHECK
