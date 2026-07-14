#!/usr/bin/env bash
set -Eeuo pipefail
set -a
. /etc/default/bw-monitor
. /etc/default/bw-monitor-enterprise
set +a
exec /opt/bw-monitor/venv/bin/python3 /opt/bw-monitor/enterprise/bw_enterprise_migrate.py "$@"
