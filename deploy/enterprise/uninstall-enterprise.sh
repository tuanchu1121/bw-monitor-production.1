#!/usr/bin/env bash
set -Eeuo pipefail
PURGE=0; YES=0
while (($#)); do case "$1" in --purge-data) PURGE=1;shift;; --yes) YES=1;shift;; *) echo "Usage: $0 [--purge-data --yes]" >&2;exit 2;; esac; done
[[ "$(id -u)" == 0 ]] || { echo "Run as root" >&2; exit 1; }
if ((PURGE && !YES)); then echo "Refusing data purge without --yes" >&2; exit 1; fi
systemctl disable --now bw-enterprise-writer.service bw-enterprise-reconcile.timer bw-enterprise-backup.timer 2>/dev/null || true
systemctl stop bw-enterprise-migrate.service bw-enterprise-reconcile.service bw-enterprise-backup.service 2>/dev/null || true
if [[ -r /etc/default/bw-monitor-enterprise ]]; then
  set -a; . /etc/default/bw-monitor-enterprise; set +a
  if ((PURGE)); then
    if docker compose version >/dev/null 2>&1; then docker compose --env-file /etc/default/bw-monitor-enterprise -f /opt/bw-monitor/enterprise/docker-compose.enterprise.yml down -v
    elif command -v docker-compose >/dev/null 2>&1; then docker-compose --env-file /etc/default/bw-monitor-enterprise -f /opt/bw-monitor/enterprise/docker-compose.enterprise.yml down -v; fi
  else
    if docker compose version >/dev/null 2>&1; then docker compose --env-file /etc/default/bw-monitor-enterprise -f /opt/bw-monitor/enterprise/docker-compose.enterprise.yml down
    elif command -v docker-compose >/dev/null 2>&1; then docker-compose --env-file /etc/default/bw-monitor-enterprise -f /opt/bw-monitor/enterprise/docker-compose.enterprise.yml down; fi
  fi
fi
rm -f /etc/systemd/system/bw-enterprise-{writer,migrate,reconcile,backup}.service /etc/systemd/system/bw-enterprise-{reconcile,backup}.timer
rm -f /etc/systemd/system/bw-monitor.service.d/49-enterprise-spool.conf
rmdir /etc/systemd/system/bw-monitor.service.d 2>/dev/null || true
rm -f /usr/local/sbin/bw-enterprise /usr/local/sbin/bw-enterprise-doctor /usr/local/sbin/bw-enterprise-backup
python3 - /etc/default/bw-monitor <<'PY'
import pathlib,sys
p=pathlib.Path(sys.argv[1])
if p.exists():
    lines=[x for x in p.read_text().splitlines() if not x.startswith('BW_ENTERPRISE_')]
    p.write_text('\n'.join(lines)+'\n')
PY
rm -f /etc/default/bw-monitor-enterprise
((PURGE)) && rm -rf /var/lib/bw-monitor-enterprise /var/log/bw-monitor-enterprise /opt/bw-monitor/enterprise || true
systemctl daemon-reload
systemctl restart bw-monitor.service 2>/dev/null || true
echo "BW Monitor Enterprise layer removed. Legacy-compatible web application remains installed."
