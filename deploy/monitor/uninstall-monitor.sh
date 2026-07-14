#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="/opt/bw-monitor"
ENV_FILE="/etc/default/bw-monitor"
CRED_FILE="/root/bw-monitor-credentials.env"
PURGE_DATA=0
PURGE_CERT=0
PURGE_PACKAGES=0
YES=0
BACKUP_ROOT="/var/backups/bw-monitor"

usage() {
  cat <<'USAGE'
Usage: uninstall-monitor.sh [options]

Default behavior:
  - stop and remove Monitor services, code, Nginx site and protected environment;
  - create a restorable SQLite/config backup under /var/backups/bw-monitor;
  - keep system packages and TLS certificate.

Options:
  --purge-data      Delete application data without creating a backup.
  --purge-cert      Delete the Certbot certificate for the configured domain.
  --purge-packages  Remove Nginx/Certbot packages after uninstall.
  --yes             Do not ask for destructive confirmation.
  -h, --help        Show help.
USAGE
}
while (($#)); do
  case "$1" in
    --purge-data) PURGE_DATA=1; shift ;;
    --purge-cert) PURGE_CERT=1; shift ;;
    --purge-packages) PURGE_PACKAGES=1; shift ;;
    --yes) YES=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ "$(id -u)" == "0" ]] || { echo 'Run as root.' >&2; exit 1; }

DOMAIN=""
DB="$APP_DIR/bandwidth.db"
if [[ -r "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  DOMAIN="${BW_DOMAIN:-}"
  DB="${BW_MONITOR_DB:-$DB}"
fi

if ((PURGE_DATA && YES == 0)); then
  if [[ -r /dev/tty && -w /dev/tty ]]; then
    printf 'Type PURGE BW MONITOR to permanently delete all Monitor data: ' >/dev/tty
    IFS= read -r answer </dev/tty
    [[ "$answer" == 'PURGE BW MONITOR' ]] || { echo 'Cancelled.'; exit 1; }
  else
    echo '--purge-data in non-interactive mode also requires --yes.' >&2
    exit 1
  fi
fi

printf '\n==> Stop Monitor and every maintenance unit\n'
mapfile -t maintenance_units < <(systemctl list-units --all --no-legend 'bw-monitor-maintenance@*.service' 2>/dev/null | awk '{print $1}')
((${#maintenance_units[@]} == 0)) || systemctl stop "${maintenance_units[@]}" >/dev/null 2>&1 || true
systemctl disable --now bw-monitor-retention.timer >/dev/null 2>&1 || true
systemctl stop bw-monitor-retention.service bw-monitor.service >/dev/null 2>&1 || true
pkill -TERM -f '/opt/bw-monitor/bw_monitor_maintenance.py' >/dev/null 2>&1 || true
sleep 2
pkill -KILL -f '/opt/bw-monitor/bw_monitor_maintenance.py' >/dev/null 2>&1 || true

if ((PURGE_DATA == 0)); then
  stamp="$(date +%Y%m%d-%H%M%S)"
  backup_dir="$BACKUP_ROOT/$stamp"
  install -d -m 0700 "$backup_dir"
  printf '\n==> Create restorable backup: %s\n' "$backup_dir"
  if [[ -f "$DB" ]]; then
    if command -v sqlite3 >/dev/null 2>&1; then
      sqlite3 "$DB" ".timeout 60000" ".backup '$backup_dir/bandwidth.db'" || cp -a "$DB" "$backup_dir/bandwidth.db"
    else
      cp -a "$DB" "$backup_dir/bandwidth.db"
    fi
  fi
  [[ -f "$DB-wal" ]] && cp -a "$DB-wal" "$backup_dir/" || true
  [[ -f "$DB-shm" ]] && cp -a "$DB-shm" "$backup_dir/" || true
  [[ -f "$ENV_FILE" ]] && cp -a "$ENV_FILE" "$backup_dir/bw-monitor.env"
  [[ -f "$CRED_FILE" ]] && cp -a "$CRED_FILE" "$backup_dir/credentials.env"
  [[ -f "$APP_DIR/DEPLOY_VERSION" ]] && cp -a "$APP_DIR/DEPLOY_VERSION" "$backup_dir/"
  chmod -R go-rwx "$backup_dir"
fi

printf '\n==> Remove Monitor services and application\n'
rm -f \
  /etc/systemd/system/bw-monitor.service \
  /etc/systemd/system/bw-monitor-maintenance@.service \
  /etc/systemd/system/bw-monitor-retention.service \
  /etc/systemd/system/bw-monitor-retention.timer \
  "$ENV_FILE" \
  "$CRED_FILE" \
  /run/bw-monitor-maintenance-web-offline
rm -rf "$APP_DIR"
systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true

printf '\n==> Remove Nginx site\n'
rm -f /etc/nginx/sites-enabled/bw-monitor.conf /etc/nginx/sites-available/bw-monitor.conf
if command -v nginx >/dev/null 2>&1; then
  nginx -t >/dev/null 2>&1 && systemctl reload nginx >/dev/null 2>&1 || true
fi

if ((PURGE_CERT)) && [[ -n "$DOMAIN" ]] && command -v certbot >/dev/null 2>&1; then
  printf '\n==> Delete Certbot certificate for %s\n' "$DOMAIN"
  certbot delete --non-interactive --cert-name "$DOMAIN" || true
fi

if ((PURGE_PACKAGES)); then
  printf '\n==> Remove optional reverse-proxy packages\n'
  apt-get purge -y nginx nginx-common certbot python3-certbot-nginx || true
  apt-get autoremove -y || true
fi

if pgrep -af '/opt/bw-monitor/(app.py|bw_monitor_)' >/dev/null 2>&1; then
  echo 'WARNING: a BW Monitor process still appears to be running:' >&2
  pgrep -af '/opt/bw-monitor/(app.py|bw_monitor_)' >&2 || true
fi

echo
if ((PURGE_DATA)); then
  echo 'BW Monitor removed and application data purged.'
else
  echo "BW Monitor removed. Restorable backup: $backup_dir"
fi
