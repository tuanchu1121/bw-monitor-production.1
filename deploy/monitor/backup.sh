#!/usr/bin/env bash
set -Eeuo pipefail
ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
BACKUP_ROOT="${BW_BACKUP_ROOT:-/var/backups/bw-monitor}"
KEEP_DAYS="${BW_BACKUP_KEEP_DAYS:-14}"
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
DB="${BW_MONITOR_DB:-$APP_DIR/bandwidth.db}"
[[ -r "$ENV_FILE" ]] && { set -a; . "$ENV_FILE"; set +a; DB="${BW_MONITOR_DB:-$DB}"; }
[[ -f "$DB" ]] || { echo "Database not found: $DB" >&2; exit 1; }
stamp="$(date +%Y%m%d-%H%M%S)"; dest="$BACKUP_ROOT/$stamp"
install -d -m 0700 "$dest"
python="$APP_DIR/venv/bin/python3"; [[ -x "$python" ]] || python="$(command -v python3)"
DB_SOURCE="$DB" DB_BACKUP="$dest/bandwidth.db" "$python" - <<'PY_BACKUP'
import os, sqlite3
src=os.environ['DB_SOURCE']; dst=os.environ['DB_BACKUP']
a=sqlite3.connect(src, timeout=60); b=sqlite3.connect(dst, timeout=60)
try:
    a.execute('PRAGMA busy_timeout=60000')
    a.backup(b, pages=8192, sleep=0.05)
    b.commit()
finally:
    b.close(); a.close()
print('SQLite backup:', dst)
PY_BACKUP
[[ -f "$ENV_FILE" ]] && cp -a "$ENV_FILE" "$dest/bw-monitor.env"
[[ -f /root/bw-monitor-credentials.env ]] && cp -a /root/bw-monitor-credentials.env "$dest/credentials.env"
[[ -f "$APP_DIR/DEPLOY_VERSION" ]] && cp -a "$APP_DIR/DEPLOY_VERSION" "$dest/DEPLOY_VERSION"
[[ -f "$APP_DIR/app.py" ]] && sha256sum "$APP_DIR/app.py" > "$dest/app.py.sha256"
{
  echo "created_at=$(date --iso-8601=seconds)"
  echo "hostname=$(hostname -f 2>/dev/null || hostname)"
  echo "database_source=$DB"
  echo "database_bytes=$(stat -c %s "$DB")"
  echo "deploy_version=$(cat "$APP_DIR/DEPLOY_VERSION" 2>/dev/null || echo unknown)"
} > "$dest/MANIFEST.txt"
(cd "$dest" && sha256sum bandwidth.db bw-monitor.env credentials.env DEPLOY_VERSION 2>/dev/null > SHA256SUMS || true)
chmod -R go-rwx "$dest"
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$KEEP_DAYS" -exec rm -rf {} +
echo "Backup completed: $dest"
