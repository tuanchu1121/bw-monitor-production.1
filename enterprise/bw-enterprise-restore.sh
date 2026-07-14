#!/usr/bin/env bash
set -Eeuo pipefail
DIR="${1:-}"
[[ -n "$DIR" && -d "$DIR" ]] || { echo "Usage: $0 /path/to/enterprise-backup" >&2; exit 2; }
[[ -f "$DIR/timescale.dump" ]] || { echo "Missing timescale.dump" >&2; exit 1; }
set -a
. /etc/default/bw-monitor
. /etc/default/bw-monitor-enterprise
set +a
systemctl stop bw-enterprise-writer.service bw-monitor.service
trap 'systemctl start bw-monitor.service bw-enterprise-writer.service >/dev/null 2>&1 || true' EXIT

docker exec -i bw-timescaledb psql -U "$BW_PG_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$BW_PG_DATABASE' AND pid<>pg_backend_pid();
DROP DATABASE IF EXISTS "$BW_PG_DATABASE";
CREATE DATABASE "$BW_PG_DATABASE" OWNER "$BW_PG_USER";
SQL
cat "$DIR/timescale.dump" | docker exec -i bw-timescaledb pg_restore -U "$BW_PG_USER" -d "$BW_PG_DATABASE" --no-owner --no-privileges
if [[ -f "$DIR/bandwidth.db" ]]; then
  cp -a "$BW_MONITOR_DB" "$BW_MONITOR_DB.before-enterprise-restore.$(date +%s)" 2>/dev/null || true
  install -m 0640 "$DIR/bandwidth.db" "$BW_MONITOR_DB"
fi
systemctl start bw-monitor.service bw-enterprise-writer.service
trap - EXIT
printf 'Enterprise restore complete from %s\n' "$DIR"
