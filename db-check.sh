#!/usr/bin/env bash
set -Eeuo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "/opt/bw-monitor/db-check.sh" && "$(readlink -f "/opt/bw-monitor/db-check.sh")" != "$(readlink -f "$0")" ]]; then exec "/opt/bw-monitor/db-check.sh" "$@"; fi
exec "$DIR/deploy/postgres/db-check.sh" "$@"
