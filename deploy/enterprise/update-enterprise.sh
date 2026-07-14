#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
[[ "$(id -u)" == 0 ]] || { echo "Run as root" >&2; exit 1; }
[[ -r /etc/default/bw-monitor ]] || { echo "Missing /etc/default/bw-monitor; run install-enterprise.sh first" >&2; exit 1; }
[[ -r /etc/default/bw-monitor-enterprise ]] || { echo "Missing /etc/default/bw-monitor-enterprise; run install-enterprise.sh first" >&2; exit 1; }
SKIP_PREFLIGHT=0
while (($#)); do
  case "$1" in
    --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
    -h|--help) echo "Usage: $0 [--skip-preflight]"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done
set -a
. /etc/default/bw-monitor
set +a
args=(--update --backup-db --public-ip "${BW_PUBLIC_IP:-}" --port "${BW_PUBLIC_PORT:-8080}")
((SKIP_PREFLIGHT)) && args+=(--skip-preflight)
"$REPO_ROOT/deploy/monitor/install-monitor.sh" "${args[@]}"
"$REPO_ROOT/deploy/enterprise/install-enterprise.sh" \
  --skip-base-install \
  --no-docker-install \
  --no-history-migration \
  --public-ip "${BW_PUBLIC_IP:-}" \
  --port "${BW_PUBLIC_PORT:-8080}"
