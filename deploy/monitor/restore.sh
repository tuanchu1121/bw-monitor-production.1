#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
BACKUP_DIR=""
YES=0
RESTORE_CONFIG=1
usage(){ cat <<'USAGE'
Usage: restore.sh --from /var/backups/bw-monitor/YYYYmmdd-HHMMSS [--yes] [--db-only]

Restores a backup created by backup.sh. The current database/config is backed up
again before replacement. Services are stopped only during the final swap.
USAGE
}
while (($#)); do case "$1" in
  --from) BACKUP_DIR="${2:?missing value}"; shift 2;;
  --yes) YES=1; shift;;
  --db-only) RESTORE_CONFIG=0; shift;;
  -h|--help) usage; exit 0;;
  *) echo "Unknown option: $1" >&2; exit 2;;
esac; done
[[ "$(id -u)" == 0 ]] || { echo 'Run as root.' >&2; exit 1; }
[[ -n "$BACKUP_DIR" && -d "$BACKUP_DIR" ]] || { usage; exit 2; }
[[ -f "$BACKUP_DIR/bandwidth.db" ]] || { echo 'Backup database is missing.' >&2; exit 2; }
python="$APP_DIR/venv/bin/python3"; [[ -x "$python" ]] || python="$(command -v python3)"
BACKUP_DB="$BACKUP_DIR/bandwidth.db" "$python" - <<'PY_RESTORE'
import os, sqlite3
p=os.environ['BACKUP_DB']
c=sqlite3.connect('file:'+p+'?mode=ro', uri=True, timeout=30)
rows=[r[0] for r in c.execute('PRAGMA quick_check')]
c.close()
if rows != ['ok']:
    raise SystemExit('Backup quick_check failed: ' + repr(rows[:20]))
print('Backup quick_check: ok')
PY_RESTORE
if ((YES == 0)); then
  [[ -r /dev/tty && -w /dev/tty ]] || { echo 'Non-interactive restore requires --yes.' >&2; exit 2; }
  printf 'Type RESTORE BW MONITOR to continue: ' >/dev/tty
  IFS= read -r answer </dev/tty
  [[ "$answer" == 'RESTORE BW MONITOR' ]] || { echo 'Cancelled.'; exit 1; }
fi
if [[ -x "$APP_DIR/backup.sh" && -f "$APP_DIR/bandwidth.db" ]]; then "$APP_DIR/backup.sh"; fi
systemctl stop bw-monitor-retention.timer bw-monitor-retention.service bw-monitor.service || true
install -o root -g root -m 0600 "$BACKUP_DIR/bandwidth.db" "$APP_DIR/bandwidth.db"
rm -f "$APP_DIR/bandwidth.db-wal" "$APP_DIR/bandwidth.db-shm"
if ((RESTORE_CONFIG)); then
  [[ -f "$BACKUP_DIR/bw-monitor.env" ]] && install -o root -g root -m 0600 "$BACKUP_DIR/bw-monitor.env" "$ENV_FILE"
  [[ -f "$BACKUP_DIR/credentials.env" ]] && install -o root -g root -m 0600 "$BACKUP_DIR/credentials.env" /root/bw-monitor-credentials.env
fi
systemctl daemon-reload
systemctl enable --now bw-monitor-retention.timer
systemctl restart bw-monitor.service
systemctl is-active --quiet bw-monitor.service || { journalctl -u bw-monitor.service -n 200 --no-pager; exit 1; }
echo "Restore completed from: $BACKUP_DIR"
