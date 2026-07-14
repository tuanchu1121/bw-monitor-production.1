#!/usr/bin/env bash
set -Eeuo pipefail
set -a
. /etc/default/bw-monitor
. /etc/default/bw-monitor-enterprise
set +a
BACKUP_ROOT="${BW_ENTERPRISE_BACKUP_DIR:-/opt/bw-monitor/backups/enterprise}"
KEEP_DAYS="${BW_ENTERPRISE_BACKUP_KEEP_DAYS:-14}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_ROOT/$STAMP"
mkdir -p "$OUT"
chmod 0700 "$BACKUP_ROOT" "$OUT"

if [[ -f "${BW_MONITOR_DB:-/opt/bw-monitor/bandwidth.db}" ]]; then
  python3 - "$BW_MONITOR_DB" "$OUT/bandwidth.db" <<'PY'
import sqlite3,sys
src=sqlite3.connect(f"file:{sys.argv[1]}?mode=ro",uri=True,timeout=60)
dst=sqlite3.connect(sys.argv[2],timeout=60)
try: src.backup(dst,pages=4096,sleep=0.02); dst.commit()
finally: dst.close(); src.close()
PY
fi

docker exec bw-timescaledb pg_dump -U "$BW_PG_USER" -d "$BW_PG_DATABASE" -Fc > "$OUT/timescale.dump"
cp -a /etc/default/bw-monitor "$OUT/bw-monitor.env"
cp -a /etc/default/bw-monitor-enterprise "$OUT/bw-monitor-enterprise.env"
cp -a /root/bw-monitor-credentials.env "$OUT/credentials.env" 2>/dev/null || true
sha256sum "$OUT"/* > "$OUT/SHA256SUMS"
chmod 0600 "$OUT"/*
find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 -type d -mtime "+$KEEP_DAYS" -print0 | xargs -0r rm -rf
printf 'Enterprise backup complete: %s\n' "$OUT"
