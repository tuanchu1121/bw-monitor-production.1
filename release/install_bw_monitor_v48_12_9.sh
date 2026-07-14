#!/usr/bin/env bash
set -Eeuo pipefail

APP_SRC="${1:-./bw_monitor_app_v48_12_9_operations_ui.py}"
RUNNER_SRC="${2:-./bw_monitor_maintenance_v48_12_9_single_worker.py}"
SERVICE_SRC="${3:-./bw-monitor-maintenance-v48.12.9@.service}"
BASE_TEST_SRC="${4:-./test_abuse_engine_v48_10_0.py}"
RELEASE_TEST_SRC="${5:-./test_v48_10_4_compact_ram.py}"
UI_TEST_SRC="${6:-./test_v48_10_6_ui_darkfix.py}"
API_TEST_SRC="${7:-./test_v48_11_0_api_management.py}"
API_HUB_TEST_SRC="${8:-./test_v48_12_0_api_abuse_hub.py}"
POLISH_TEST_SRC="${9:-./test_v48_12_2_maintenance_api_cleanup.py}"
COMPACT_TEST_SRC="${10:-./test_v48_12_3_safe_compact.py}"
GUARD_TEST_SRC="${11:-./test_v48_12_4_maintenance_guard.py}"
AGENT_SRC="${12:-./bwagent_daemon_v10_dynamic_abuse.py}"
RECOVERY_SRC="${13:-./recover_bw_monitor_maintenance_v48_12_9.sh}"
DB_CHECK_SRC="${14:-./check_bw_monitor_db_v48_12_9.sh}"
RETENTION_RUNNER_SRC="${15:-./bw_monitor_retention_v48_12_9.py}"
RETENTION_SERVICE_SRC="${16:-./bw-monitor-retention-v48.12.9.service}"
RETENTION_TIMER_SRC="${17:-./bw-monitor-retention-v48.12.9.timer}"
BOUNDED_TEST_SRC="${18:-./test_v48_12_5_bounded_retention.py}"
INTELLIGENCE_TEST_SRC="${19:-./test_v48_12_6_abuse_intelligence.py}"
SIMPLE_ABUSE_TEST_SRC="${20:-./test_v48_12_7_simple_abuse_dashboard.py}"
ABUSE_TABLE_TEST_SRC="${21:-./test_v48_12_8_abuse_table.py}"
OPERATIONS_TEST_SRC="${22:-./test_v48_12_9_operations_ui.py}"
STORAGE_TEST_SRC="${23:-./test_v48_13_4_storage_precision.py}"
STORAGE_HISTORY_TEST_SRC="${24:-./test_v48_13_7_storage_history.py}"

TARGET_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
APP_TARGET="${BW_MONITOR_APP_TARGET:-$TARGET_DIR/app.py}"
RUNNER_TARGET="$TARGET_DIR/bw_monitor_maintenance.py"
SERVICE_TARGET="/etc/systemd/system/bw-monitor-maintenance@.service"
RETENTION_RUNNER_TARGET="$TARGET_DIR/bw_monitor_retention.py"
RETENTION_SERVICE_TARGET="/etc/systemd/system/bw-monitor-retention.service"
RETENTION_TIMER_TARGET="/etc/systemd/system/bw-monitor-retention.timer"
DB_TARGET="${BW_MONITOR_DB:-$TARGET_DIR/bandwidth.db}"
SERVICE_NAME="${BW_MONITOR_SERVICE:-bw-monitor.service}"
STAMP="$(date +%F-%H%M%S)"
BACKUP_DIR="$TARGET_DIR/backup-v48.12.9-$STAMP"
BACKUP_DB="${BW_BACKUP_DB:-0}"
DEPLOY_STARTED=0

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

for file in "$APP_SRC" "$RUNNER_SRC" "$SERVICE_SRC" "$BASE_TEST_SRC" "$RELEASE_TEST_SRC" "$UI_TEST_SRC" "$API_TEST_SRC" "$API_HUB_TEST_SRC" "$POLISH_TEST_SRC" "$COMPACT_TEST_SRC" "$GUARD_TEST_SRC" "$AGENT_SRC" "$RECOVERY_SRC" "$DB_CHECK_SRC" "$RETENTION_RUNNER_SRC" "$RETENTION_SERVICE_SRC" "$RETENTION_TIMER_SRC" "$BOUNDED_TEST_SRC" "$INTELLIGENCE_TEST_SRC" "$SIMPLE_ABUSE_TEST_SRC" "$ABUSE_TABLE_TEST_SRC" "$OPERATIONS_TEST_SRC" "$STORAGE_TEST_SRC" "$STORAGE_HISTORY_TEST_SRC"; do
  [[ -f "$file" ]] || die "Missing file: $file"
done

PYTHON_BIN="${BW_PYTHON_BIN:-}"
if [[ -n "$PYTHON_BIN" && ! -x "$PYTHON_BIN" ]]; then
  die "BW_PYTHON_BIN is not executable: $PYTHON_BIN"
fi
if [[ -z "$PYTHON_BIN" ]]; then
  for candidate in "$TARGET_DIR/venv/bin/python3" "$TARGET_DIR/.venv/bin/python3" /usr/bin/python3; do
    if [[ -x "$candidate" ]]; then
      PYTHON_BIN="$candidate"
      break
    fi
  done
fi
[[ -n "$PYTHON_BIN" ]] || die "No Python 3 interpreter found"

rollback() {
  local reason="${1:-deployment verification failed}"
  echo >&2
  echo "Deployment failed: $reason" >&2
  if [[ "$DEPLOY_STARTED" != "1" ]]; then
    return 0
  fi
  echo "Restoring files from: $BACKUP_DIR" >&2
  [[ -f "$BACKUP_DIR/app.py" ]] && install -m 0644 "$BACKUP_DIR/app.py" "$APP_TARGET"
  [[ -f "$BACKUP_DIR/bw_monitor_maintenance.py" ]] && install -m 0755 "$BACKUP_DIR/bw_monitor_maintenance.py" "$RUNNER_TARGET"
  [[ -f "$BACKUP_DIR/bw-monitor-maintenance@.service" ]] && install -m 0644 "$BACKUP_DIR/bw-monitor-maintenance@.service" "$SERVICE_TARGET"
  if [[ -f "$BACKUP_DIR/bw_monitor_retention.py" ]]; then install -m 0755 "$BACKUP_DIR/bw_monitor_retention.py" "$RETENTION_RUNNER_TARGET"; else rm -f "$RETENTION_RUNNER_TARGET"; fi
  if [[ -f "$BACKUP_DIR/bw-monitor-retention.service" ]]; then install -m 0644 "$BACKUP_DIR/bw-monitor-retention.service" "$RETENTION_SERVICE_TARGET"; else rm -f "$RETENTION_SERVICE_TARGET"; fi
  if [[ -f "$BACKUP_DIR/bw-monitor-retention.timer" ]]; then install -m 0644 "$BACKUP_DIR/bw-monitor-retention.timer" "$RETENTION_TIMER_TARGET"; else rm -f "$RETENTION_TIMER_TARGET"; fi
  systemctl daemon-reload || true
  if [[ -f "$RETENTION_TIMER_TARGET" ]]; then
    systemctl enable --now bw-monitor-retention.timer >/dev/null 2>&1 || true
  else
    systemctl disable --now bw-monitor-retention.timer >/dev/null 2>&1 || true
  fi
  systemctl restart "$SERVICE_NAME" || true
  systemctl status "$SERVICE_NAME" --no-pager -l >&2 || true
}

say "Pre-flight syntax and release checks"
"$PYTHON_BIN" -m py_compile "$APP_SRC" "$RUNNER_SRC" "$RETENTION_RUNNER_SRC" "$BASE_TEST_SRC" "$RELEASE_TEST_SRC" "$UI_TEST_SRC" "$API_TEST_SRC" "$API_HUB_TEST_SRC" "$POLISH_TEST_SRC" "$COMPACT_TEST_SRC" "$GUARD_TEST_SRC" "$BOUNDED_TEST_SRC" "$INTELLIGENCE_TEST_SRC" "$SIMPLE_ABUSE_TEST_SRC" "$ABUSE_TABLE_TEST_SRC" "$OPERATIONS_TEST_SRC" "$STORAGE_TEST_SRC" "$STORAGE_HISTORY_TEST_SRC" "$AGENT_SRC"
bash -n "$0" "$RECOVERY_SRC" "$DB_CHECK_SRC"
grep -q 'V4810_VERSION = "48.10.0"' "$APP_SRC" || die "Missing v48.10.0 engine marker"
grep -q 'V48101_VERSION = "48.10.1"' "$APP_SRC" || die "Missing v48.10.1 wide UI marker"
grep -q 'V48102_VERSION = "48.10.2"' "$APP_SRC" || die "Missing v48.10.2 operational UI marker"
grep -q 'V48103_VERSION = "48.10.3"' "$APP_SRC" || die "Missing v48.10.3 guest RAM base marker"
grep -q 'V48104_VERSION = "48.10.4"' "$APP_SRC" || die "Missing v48.10.4 compact RAM marker"
grep -q 'V48105_VERSION = "48.10.5"' "$APP_SRC" || die "Missing v48.10.5 UI polish marker"
grep -q 'V48106_VERSION = "48.10.6"' "$APP_SRC" || die "Missing v48.10.6 login/darkfix marker"
grep -q 'V48110_VERSION = "48.11.0"' "$APP_SRC" || die "Missing v48.11.0 API marker"
grep -q 'V48120_VERSION = "48.12.0"' "$APP_SRC" || die "Missing v48.12.0 API Hub marker"
grep -q 'V48122_VERSION = "48.12.2"' "$APP_SRC" || die "Missing v48.12.2 API Admin polish marker"
grep -q 'V48123_VERSION = "48.12.3"' "$APP_SRC" || die "Missing v48.12.3 safe compact marker"
grep -q 'V48124_VERSION = "48.12.4"' "$APP_SRC" || die "Missing v48.12.4 maintenance guard marker"
grep -q 'V48125_VERSION = "48.12.5"' "$APP_SRC" || die "Missing v48.12.5 bounded retention marker"
grep -q 'V48126_VERSION = "48.12.6"' "$APP_SRC" || die "Missing v48.12.6 Abuse Intelligence marker"
grep -q 'V48127_VERSION = "48.12.7"' "$APP_SRC" || die "Missing v48.12.7 simplified Abuse dashboard marker"
grep -q 'V48128_VERSION = "48.12.8"' "$APP_SRC" || die "Missing v48.12.8 Abuse table marker"
grep -q 'V48129_VERSION = "48.12.9"' "$APP_SRC" || die "Missing v48.12.9 operations Abuse marker"
grep -q 'V48129_BUILD = "r4"' "$APP_SRC" || die "Missing v48.12.9-r4 compact UI marker"
grep -q 'V48133_VERSION = "48.13.3"' "$APP_SRC" || die "Missing v48.13.3 storage integration marker"
grep -q 'V48134_VERSION = "48.13.4"' "$APP_SRC" || die "Missing v48.13.4 storage precision marker"
grep -q 'V48135_VERSION = "48.13.5"' "$APP_SRC" || die "Missing v48.13.5 storage root-bars marker"
grep -q 'V48135_BUILD = "r2"' "$APP_SRC" || die "Missing v48.13.5-r2 VM disk panels marker"
grep -q 'V48136_VERSION = "48.13.6"' "$APP_SRC" || die "Missing v48.13.6 grouped storage marker"
grep -q 'V48136_BUILD = "r1"' "$APP_SRC" || die "Missing v48.13.6-r1 grouped storage build marker"
grep -q 'V48137_VERSION = "48.13.7"' "$APP_SRC" || die "Missing v48.13.7 retained storage marker"
grep -q 'V48137_BUILD = "r1"' "$APP_SRC" || die "Missing v48.13.7-r1 retained storage build marker"
grep -q 'storage_payload' "$APP_SRC" || die "Missing retained Storage payload"
grep -q 'Custom Snapshot Time' "$APP_SRC" || die "Missing Storage custom snapshot control"
grep -q 'CREATE TABLE IF NOT EXISTS vm_disk_current' "$APP_SRC" || die "Missing per-disk current schema"
grep -q 'AGENT_VERSION = 12' "$AGENT_SRC" || die "Missing Agent v12 real-filesystem collector"
grep -q 'def _v48129_metric_abuse_time' "$APP_SRC" || die "Missing metric-local Abuse duration helper"
grep -q 'def _v48129_vm_detail_cpu_stat' "$APP_SRC" || die "Missing VM detail CPU Full meter"
grep -q 'def admin_api_keys_page' "$APP_SRC" || die "Missing API Management admin page"
grep -q 'def api_v1_abuse_vms' "$APP_SRC" || die "Missing current abuse API"
grep -q 'def api_v1_abuse_events' "$APP_SRC" || die "Missing abuse events API"
grep -q 'def api_v1_vms' "$APP_SRC" || die "Missing current VM API"
grep -q 'def api_v1_bandwidth_vms' "$APP_SRC" || die "Missing bandwidth API"
grep -q 'def api_v1_abuse_summary' "$APP_SRC" || die "Missing abuse summary API"
grep -q 'def admin_api_key_delete' "$APP_SRC" || die "Missing permanent API key deletion"
grep -q 'def admin_api_logs_clear' "$APP_SRC" || die "Missing API log cleanup UI"
grep -q 'def admin_api_key_edit' "$APP_SRC" || die "Missing editable API key settings"
grep -q 'def api_v1_request_logs' "$APP_SRC" || die "Missing API request-log endpoint"
grep -q 'def api_v1_management_logs' "$APP_SRC" || die "Missing API management-log endpoint"
grep -q 'BW_WEB_TRUST_PROXY' "$APP_SRC" || die "Missing trusted reverse-proxy support"
grep -q 'CREATE TABLE IF NOT EXISTS api_access_logs' "$APP_SRC" || die "Missing API request log schema"
grep -q 'def clear_all_api_data' "$APP_SRC" || die "Missing full API data cleanup"
grep -q 'CREATE TABLE IF NOT EXISTS api_keys' "$APP_SRC" || die "Missing API key schema"
grep -q 'login-card-pro' "$APP_SRC" || die "Missing dedicated login layout"
grep -q 'table-vm-polished' "$APP_SRC" || die "Missing balanced VM table layout"
grep -q '_v48105_cpu_usage_block' "$APP_SRC" || die "Missing reusable CPU meter"
grep -q 'def admin_login_v48106' "$APP_SRC" || die "Missing dedicated admin login"
grep -q 'function bindPasswordToggles' "$APP_SRC" || die "Missing robust password toggle"
grep -q 'V48106_UI_CSS' "$APP_SRC" || die "Missing dark chip/input contrast layer"
grep -q 'ABUSE_ENGINE_VERSION = "cycles-v3-ram"' "$APP_SRC" || die "Missing cycles-v3-ram engine marker"
grep -q 'const BW_AUTO_REFRESH_MS = 5000' "$APP_SRC" || die "Missing five-second partial refresh"
grep -q 'def reset_all_app_data' "$APP_SRC" || die "Missing full operational reset"
grep -q 'def vm_guest_ram_metrics' "$APP_SRC" || die "Missing guest RAM calculation"
grep -q 'guest_used_kib' "$APP_SRC" || die "Missing Guest Used data path"
grep -q 'ram_unused_kib' "$APP_SRC" || die "Missing balloon unused field"
grep -q 'ram_usable_kib' "$APP_SRC" || die "Missing balloon usable field"
grep -q 'V48103_RAM_SORT_KEYS' "$APP_SRC" || die "Missing RAM sort modes"
grep -q 'ram-sort-menu' "$APP_SRC" || die "Missing compact RAM sort menu"
grep -q 'vm-ram-compact' "$APP_SRC" || die "Missing compact RAM row renderer"
grep -q 'RAM_SUSTAINED' "$APP_SRC" || die "Missing RAM sustained Abuse flag"
grep -q 'CREATE TABLE IF NOT EXISTS vm_abuse_incidents' "$APP_SRC" || die "Missing Abuse incident schema"
grep -q '/api/v1/abuse/incidents' "$APP_SRC" || die "Missing Abuse incidents API"
grep -q '/api/v1/abuse/rankings' "$APP_SRC" || die "Missing Abuse rankings API"
grep -q 'function decorateCharts' "$APP_SRC" || die "Missing expandable chart modal"
grep -q 'Select all on this page' "$APP_SRC" || die "Missing page selection helpers"
grep -q 'def vm_abuse_page_v48128' "$APP_SRC" || die "Missing v48.12.8 Abuse table base"
grep -q 'def vm_abuse_page_v48129' "$APP_SRC" || die "Missing v48.12.9 Current Abuse / Abuse Events dashboard"
grep -q 'def clear_abuse_events_v48129' "$APP_SRC" || die "Missing synchronized Abuse History cleanup"
grep -q 'def reset_all_abuse_data_v48129' "$APP_SRC" || die "Missing explicit all-Abuse reset"
grep -q 'def manage_vm_abuse_data_v48129' "$APP_SRC" || die "Missing per-VM Abuse data controls"
grep -q 'PPS PEAK / WINDOW' "$APP_SRC" || die "Missing PPS Peak / Window operations column"
grep -q 'chip-network' "$APP_SRC" || die "Missing color-coded Abuse rule chips"
[[ $(grep -c 'DELETE FROM vm_abuse_incidents' "$APP_SRC") -ge 4 ]] || die "Abuse incident cleanup paths are incomplete"
grep -q 'ABUSE COUNT' "$APP_SRC" || die "Missing grouped VM Abuse occurrence count"
grep -q 'data-event-toggle' "$APP_SRC" || die "Missing expandable Abuse occurrence timeline"
grep -q 'ram_unused_kib' "$AGENT_SRC" || die "Agent does not report ram_unused_kib"
grep -q 'ram_usable_kib' "$AGENT_SRC" || die "Agent does not report ram_usable_kib"
grep -q 'clear_live_cache' "$RUNNER_SRC" || die "Maintenance runner does not support clear_live_cache"
grep -q 'reset_app_data' "$RUNNER_SRC" || die "Maintenance runner does not support reset_app_data"
grep -q 'clear_api_logs' "$RUNNER_SRC" || die "Maintenance runner does not support clear_api_logs"
grep -q 'clear_api_data' "$RUNNER_SRC" || die "Maintenance runner does not support clear_api_data"
grep -q 'LOCK_EX | fcntl.LOCK_NB' "$RUNNER_SRC" || die "Maintenance runner lock is not fail-fast"
grep -q 'ExecStopPost=' "$SERVICE_SRC" || die "Maintenance service lacks web recovery safety net"
! grep -q 'TimeoutStartSec=infinity' "$SERVICE_SRC" || die "Maintenance service still has an infinite start timeout"
grep -q 'OnCalendar=\*-\*-\* 00,06,12,18:20:00' "$RETENTION_TIMER_SRC" || die "Retention timer is not scheduled every six hours"
grep -q 'RandomizedDelaySec=20m' "$RETENTION_TIMER_SRC" || die "Retention timer lacks randomized delay"
grep -q 'LOCK_EX | fcntl.LOCK_NB' "$RETENTION_RUNNER_SRC" || die "Automatic retention lock is not fail-fast"
grep -q 'TimeoutStartSec=12h' "$RETENTION_SERVICE_SRC" || die "Automatic retention timeout is not 12h"
grep -q 'RAW_RETENTION_DAYS = min(2' "$APP_SRC" || die "Raw retention is not hard-capped at 2 days"
grep -q 'HOURLY_RETENTION_DAYS = min(7' "$APP_SRC" || die "History retention is not hard-capped at 7 days"

say "Run isolated regression suites on temporary SQLite databases"
"$PYTHON_BIN" "$BASE_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$RELEASE_TEST_SRC" "$APP_SRC" "$AGENT_SRC"
"$PYTHON_BIN" "$UI_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$API_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$API_HUB_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$POLISH_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$COMPACT_TEST_SRC" "$APP_SRC" "$RUNNER_SRC"
"$PYTHON_BIN" "$GUARD_TEST_SRC" "$APP_SRC" "$RUNNER_SRC" "$SERVICE_SRC"
"$PYTHON_BIN" "$BOUNDED_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$INTELLIGENCE_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$SIMPLE_ABUSE_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$ABUSE_TABLE_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$OPERATIONS_TEST_SRC" "$APP_SRC"
"$PYTHON_BIN" "$STORAGE_TEST_SRC" "$APP_SRC" "$AGENT_SRC"
"$PYTHON_BIN" "$STORAGE_HISTORY_TEST_SRC" "$APP_SRC"

if [[ "${BW_PREFLIGHT_ONLY:-0}" == "1" ]]; then
  echo
  echo "BW Monitor v48.13.7-r1 retained-storage pre-flight checks passed. No files were installed."
  exit 0
fi

say "Pause automatic retention during deployment"
systemctl stop bw-monitor-retention.timer >/dev/null 2>&1 || true
systemctl stop bw-monitor-retention.service >/dev/null 2>&1 || true
pkill -TERM -f '/opt/bw-monitor/bw_monitor_retention.py' 2>/dev/null || true

say "Check for active/stuck maintenance workers"
ACTIVE_UNITS="$(systemctl list-units --all --plain --no-legend 'bw-monitor-maintenance@*.service' 2>/dev/null | awk '$3=="activating" || $3=="active" {print $1}' | paste -sd, - || true)"
ACTIVE_PIDS="$(pgrep -f '/opt/bw-monitor/bw_monitor_maintenance.py' | paste -sd, - || true)"
ACTIVE_ROWS="0"
if [[ -f "$DB_TARGET" ]]; then
  ACTIVE_ROWS="$(DB_PATH="$DB_TARGET" "$PYTHON_BIN" - <<'PYDB' 2>/dev/null || echo unknown
import os, sqlite3
path=os.environ['DB_PATH']
conn=sqlite3.connect(path, timeout=3)
try:
    conn.execute('PRAGMA busy_timeout=3000')
    tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if 'maintenance_jobs' not in tables:
        print(0)
    else:
        print(int(conn.execute("SELECT COUNT(*) FROM maintenance_jobs WHERE status IN ('queued','running')").fetchone()[0] or 0))
finally:
    conn.close()
PYDB
)"
fi
if [[ -n "$ACTIVE_UNITS" || -n "$ACTIVE_PIDS" || "$ACTIVE_ROWS" != "0" ]]; then
  if [[ "${BW_RECOVER_STUCK_MAINTENANCE:-0}" != "1" ]]; then
    die "Active/stale maintenance detected (units=${ACTIVE_UNITS:-none}, pids=${ACTIVE_PIDS:-none}, queue_rows=${ACTIVE_ROWS}). Run ./recover_bw_monitor_maintenance_v48_12_9.sh first, or rerun with BW_RECOVER_STUCK_MAINTENANCE=1 to recover automatically."
  fi
  say "Recover active maintenance before deployment"
  RECOVERY_SCRIPT="$(dirname "$0")/recover_bw_monitor_maintenance_v48_12_9.sh"
  [[ -x "$RECOVERY_SCRIPT" ]] || die "Missing executable recovery script: $RECOVERY_SCRIPT"
  BW_MONITOR_DB="$DB_TARGET" BW_MONITOR_SERVICE="$SERVICE_NAME" "$RECOVERY_SCRIPT"
fi

say "Create rollback backup"
mkdir -p "$BACKUP_DIR"
[[ -f "$APP_TARGET" ]] && cp -a "$APP_TARGET" "$BACKUP_DIR/app.py"
[[ -f "$RUNNER_TARGET" ]] && cp -a "$RUNNER_TARGET" "$BACKUP_DIR/bw_monitor_maintenance.py"
[[ -f "$SERVICE_TARGET" ]] && cp -a "$SERVICE_TARGET" "$BACKUP_DIR/bw-monitor-maintenance@.service"
[[ -f "$RETENTION_RUNNER_TARGET" ]] && cp -a "$RETENTION_RUNNER_TARGET" "$BACKUP_DIR/bw_monitor_retention.py"
[[ -f "$RETENTION_SERVICE_TARGET" ]] && cp -a "$RETENTION_SERVICE_TARGET" "$BACKUP_DIR/bw-monitor-retention.service"
[[ -f "$RETENTION_TIMER_TARGET" ]] && cp -a "$RETENTION_TIMER_TARGET" "$BACKUP_DIR/bw-monitor-retention.timer"

if [[ "$BACKUP_DB" == "1" && -f "$DB_TARGET" ]]; then
  say "Create a consistent SQLite backup"
  DB_SOURCE="$DB_TARGET" DB_BACKUP="$BACKUP_DIR/bandwidth.db" "$PYTHON_BIN" - <<'PY'
import os, sqlite3
src = os.environ["DB_SOURCE"]
dst = os.environ["DB_BACKUP"]
source = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=60)
target = sqlite3.connect(dst, timeout=60)
try:
    source.backup(target, pages=4096, sleep=0.05)
    target.commit()
finally:
    target.close()
    source.close()
print(f"SQLite backup: {dst}")
PY
else
  echo "Database is preserved in place. Set BW_BACKUP_DB=1 for a consistent full DB backup."
fi

say "Install v48.12.9 files"
mkdir -p "$TARGET_DIR"
DEPLOY_STARTED=1
install -m 0644 "$APP_SRC" "$APP_TARGET"
install -m 0755 "$RUNNER_SRC" "$RUNNER_TARGET"
install -m 0644 "$SERVICE_SRC" "$SERVICE_TARGET"
install -m 0755 "$RETENTION_RUNNER_SRC" "$RETENTION_RUNNER_TARGET"
install -m 0644 "$RETENTION_SERVICE_SRC" "$RETENTION_SERVICE_TARGET"
install -m 0644 "$RETENTION_TIMER_SRC" "$RETENTION_TIMER_TARGET"
install -m 0755 "$RECOVERY_SRC" "$TARGET_DIR/recover_bw_monitor_maintenance_v48_12_9.sh"
install -m 0755 "$DB_CHECK_SRC" "$TARGET_DIR/check_bw_monitor_db_v48_12_9.sh"

if ! "$PYTHON_BIN" -m py_compile "$APP_TARGET" "$RUNNER_TARGET" "$RETENTION_RUNNER_TARGET"; then
  rollback "installed files did not compile"
  exit 1
fi

say "Reload systemd and restart monitor"
systemctl unmask bw-monitor-maintenance@.service >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl unmask bw-monitor-retention.service bw-monitor-retention.timer >/dev/null 2>&1 || true
systemctl enable --now bw-monitor-retention.timer
if ! systemctl restart "$SERVICE_NAME"; then
  rollback "systemd could not restart $SERVICE_NAME"
  exit 1
fi

for _ in $(seq 1 20); do
  systemctl is-active --quiet "$SERVICE_NAME" && break
  sleep 1
done
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  journalctl -u "$SERVICE_NAME" -n 250 --no-pager >&2 || true
  rollback "$SERVICE_NAME is not active"
  exit 1
fi
sleep 4
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  journalctl -u "$SERVICE_NAME" -n 250 --no-pager >&2 || true
  rollback "$SERVICE_NAME did not stay active"
  exit 1
fi
MAIN_PID="$(systemctl show "$SERVICE_NAME" -p MainPID --value 2>/dev/null || true)"
[[ "$MAIN_PID" =~ ^[1-9][0-9]*$ ]] || {
  journalctl -u "$SERVICE_NAME" -n 250 --no-pager >&2 || true
  rollback "$SERVICE_NAME has no live MainPID"
  exit 1
}

say "Verify installed v48.12.9 against an isolated temporary database"
if ! APP_VERIFY="$APP_TARGET" "$PYTHON_BIN" - <<'PY'
import importlib.util, os, pathlib, tempfile
app_path = pathlib.Path(os.environ["APP_VERIFY"]).resolve()
with tempfile.TemporaryDirectory(prefix="bw-monitor-v48129-install-check-") as tmp:
    os.environ["BW_MONITOR_DB"] = str(pathlib.Path(tmp) / "verify.db")
    os.environ.setdefault("BW_MONITOR_TOKEN", "install-check-token")
    spec = importlib.util.spec_from_file_location("bw_monitor_install_check", str(app_path))
    if spec is None or spec.loader is None:
        raise SystemExit("Cannot load installed app")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    versions = {
        "V4810_VERSION": "48.10.0",
        "V48101_VERSION": "48.10.1",
        "V48102_VERSION": "48.10.2",
        "V48103_VERSION": "48.10.3",
        "V48104_VERSION": "48.10.4",
        "V48105_VERSION": "48.10.5",
        "V48106_VERSION": "48.10.6",
        "V48110_VERSION": "48.11.0",
        "V48120_VERSION": "48.12.0",
        "V48122_VERSION": "48.12.2",
        "V48123_VERSION": "48.12.3",
        "V48124_VERSION": "48.12.4",
        "V48125_VERSION": "48.12.5",
        "V48126_VERSION": "48.12.6",
        "V48128_VERSION": "48.12.8",
        "V48129_VERSION": "48.12.9",
    }
    for key, expected in versions.items():
        if getattr(module, key, "") != expected:
            raise SystemExit(f"Wrong {key}")
    if getattr(module, "ABUSE_ENGINE_VERSION", "") != "cycles-v3-ram":
        raise SystemExit("Wrong abuse engine version")
    if getattr(module, "RAW_RETENTION_DAYS", 0) != 2:
        raise SystemExit("Wrong raw retention; expected 2 days")
    if getattr(module, "HOURLY_RETENTION_DAYS", 0) != 7:
        raise SystemExit("Wrong history retention; expected 7 days")
    if "1mo" in getattr(module, "PERIODS", {}):
        raise SystemExit("Unsupported 1mo period is still exposed")
    required = {
        "index", "top_page", "top_node_page", "node_page", "vm_page",
        "vm_abuse_page", "admin_page", "admin_abuse_page",
        "admin_abuse_settings", "admin_clear_live_cache", "push",
        "admin_api_keys_page", "admin_api_key_create", "admin_api_key_revoke", "admin_api_key_rotate",
        "admin_api_key_delete", "admin_api_logs_clear", "admin_api_key_edit",
        "api_v1_me", "api_v1_health", "api_v1_abuse_summary", "api_v1_abuse_vms", "api_v1_abuse_vm", "api_v1_abuse_events",
        "api_v1_vms", "api_v1_vm_current", "api_v1_nodes", "api_v1_bandwidth_vms", "api_v1_bandwidth_vm",
        "api_v1_request_logs", "api_v1_management_logs",
        "api_v1_abuse_incidents_v48126", "api_v1_abuse_rankings_v48126",
        "reset_all_abuse_data_v48129", "manage_vm_abuse_data_v48129",
    }
    missing = required - set(module.app.view_functions)
    if missing:
        raise SystemExit("Missing endpoints: " + ", ".join(sorted(missing)))
    conn = module.db()
    try:
        for table in ("vm_current_fast", "vm_latest_metrics", "vm_perf_stats"):
            cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for col in ("ram_unused_kib", "ram_usable_kib"):
                if col not in cols:
                    raise SystemExit(f"{table} missing {col}")
        api_tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"api_keys", "api_key_events", "api_access_logs"}.issubset(api_tables):
            raise SystemExit("API tables are missing")
        api_cols = {row[1] for row in conn.execute("PRAGMA table_info(api_keys)")}
        for col in ("key_id", "secret_hash", "scopes_json", "allowed_ips_json", "expires_at", "revoked_at"):
            if col not in api_cols:
                raise SystemExit(f"api_keys missing {col}")
        if "vm_abuse_incidents" not in api_tables:
            raise SystemExit("vm_abuse_incidents table is missing")
        abuse_cols = {row[1] for row in conn.execute("PRAGMA table_info(vm_abuse_state)")}
        for col in ("ram_streak_cycles", "ram_rss_percent", "ram_guest_used_percent", "ram_usable_percent"):
            if col not in abuse_cols:
                raise SystemExit(f"vm_abuse_state missing {col}")
    finally:
        conn.close()
    ram = module.vm_guest_ram_metrics(100000,90000,100000,10000,20000)
    if not ram["has_guest"] or ram["guest_used_kib"] != 80000 or abs(ram["guest_used_pct"]-80.0) > 0.001:
        raise SystemExit("Guest RAM formula verification failed")
    with module.app.test_request_context("/top?sort=ram&limit=1000"):
        html = module.top_vm_table([], "5m", "", "ram", "desc", "all", 1000)
        for label in ("Guest %", "Used GiB", "Host RSS", "Assigned"):
            if label not in html:
                raise SystemExit(f"Top VM missing RAM sort: {label}")
        if html.count("ram-sort-menu") != 1 or "ram-dual-head" in html:
            raise SystemExit("Top VM compact RAM sort menu verification failed")
        compact = module.fmt_vm_ram_block(100000,90000,100000,10000,20000,compact=True)
        if "80.0% used" not in compact or "RSS" not in compact or "ASSIGNED" in compact:
            raise SystemExit("Compact RAM row verification failed")
    with module.app.test_request_context("/abuse/vms?tab=current&type=ram"):
        response = module.vm_abuse_page_v48129()
        html = response.get_data(as_text=True)
        for marker in ("Current VM Abuse", "Abuse Events", "RAM", "REASON / SEVERITY", "PPS PEAK / WINDOW", "chip-time"):
            if marker not in html:
                raise SystemExit(f"Operations Abuse UI missing {marker}")
        if "Summary</a>" in html or "Raw Events</a>" in html:
            raise SystemExit("Removed Summary/Raw Events tabs are still visible")
    source_text = app_path.read_text()
    if source_text.count("DELETE FROM vm_abuse_incidents") < 4:
        raise SystemExit("Installed source is missing complete incident cleanup paths")
    if module.app.view_functions.get("clear_abuse_events").__name__ != "clear_abuse_events_v48129":
        raise SystemExit("Installed Clear Abuse route is not the v48.12.9 synchronized implementation")
    with module.app.test_request_context("/admin/abuse"):
        card = module.abuse_settings_admin_card()
        if 'name="ram_enabled"' not in card or "Guest Used" not in card or "Low Usable" not in card:
            raise SystemExit("RAM policy controls are missing")
    with module.app.test_request_context("/login"):
        password_html = module._v48106_password_field("login-password", "password", "Password", "current-password")
        login_html = module._v48106_login_document(
            action="/login", title="Welcome back", subtitle="Secure operations access",
            username_value="", next_url="/", extra_fields=password_html,
        )
        if 'class="main-nav"' in login_html or 'Green@1234' in login_html:
            raise SystemExit("Dedicated login verification failed")
        if 'data-target="login-password"' not in login_html or 'bindPasswordToggles' not in login_html:
            raise SystemExit("Password toggle verification failed")
        if module.app.view_functions.get("admin_login").__name__ != "admin_login_v48106":
            raise SystemExit("Admin login layout override verification failed")
        if "#10243a" not in module.V48106_UI_CSS or "border-color:#2b4260" not in module.V48106_UI_CSS:
            raise SystemExit("Dark chip contrast verification failed")
    cpu_html = module._v48105_cpu_usage_block(799.5, 88.8, 9, compact=True)
    if "cpu-meter" not in cpu_html or "799.5%" not in cpu_html or "88.8% full" not in cpu_html:
        raise SystemExit("CPU meter verification failed")
    print("Installed app version: 48.12.9")
    print("Retention: 2 days raw / one real hourly snapshot through day 7 / hard delete after day 7")
    print("Abuse API Hub / REST v1 / request logs: OK")
    print("Guest RAM formula/schema/compact sorts: OK")
    print("Abuse engine: cycles-v3-ram; operations table, grouped Events, RAM policy and complete cleanup: OK")
PY
then
  rollback "post-install module verification failed"
  exit 1
fi

say "Retention timer status"
systemctl is-enabled --quiet bw-monitor-retention.timer || { rollback "retention timer is not enabled"; exit 1; }
systemctl status bw-monitor-retention.timer --no-pager -l || true

say "Service status"
systemctl status "$SERVICE_NAME" --no-pager -l

echo
echo "BW Monitor v48.12.9-r4 installed successfully."
echo "App:      $APP_TARGET"
echo "Runner:   $RUNNER_TARGET"
echo "Retention:$RETENTION_RUNNER_TARGET"
echo "Timer:    bw-monitor-retention.timer (every 6h, randomized up to 20m)"
echo "Recovery: $TARGET_DIR/recover_bw_monitor_maintenance_v48_12_9.sh"
echo "DB check: $TARGET_DIR/check_bw_monitor_db_v48_12_9.sh"
echo "Backup:   $BACKUP_DIR"
echo "Database: preserved; API access-log table and all additive schema are migrated automatically."
echo "Agent v10: redeploy is not required when the current Agent already reports available/unused/usable."
echo "RAM: optional sustained Abuse policy (RSS / Guest Used / Low Usable), disabled by default after upgrade."
echo "RAM sort: one collapsed menu keeps Guest %, Guest GiB, Host RSS and Assigned sorts."
echo "UI: higher light/dark contrast, balanced column widths and CPU meters on VM tables."
echo "Login: dedicated professional sign-in page without dashboard navigation or default credentials."
echo "API: Existing incident/ranking endpoints remain compatible; Dashboard is simplified to Current Abuse and grouped Abuse Events."
echo "Proxy: set BW_WEB_TRUST_PROXY=1 only behind a trusted local Nginx/HAProxy hop."
echo "Abuse UI: Current Abuse + grouped Abuse Events only; per-metric sort, CPU/RAM meters, colored policy chips and exact durations."
echo "Live UI: 5-second partial refresh; no browser document reload during normal refresh."

