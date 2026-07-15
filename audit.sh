#!/usr/bin/env bash
set -Eeuo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "/opt/bw-monitor/audit.sh" && "$(readlink -f "/opt/bw-monitor/audit.sh")" != "$(readlink -f "$0")" ]]; then exec "/opt/bw-monitor/audit.sh" "$@"; fi
exec "$DIR/deploy/postgres/audit.sh" "$@"
