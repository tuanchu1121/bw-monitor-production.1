#!/usr/bin/env bash
set -Eeuo pipefail
DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -x "/opt/bw-monitor/restore.sh" && "$(readlink -f "/opt/bw-monitor/restore.sh")" != "$(readlink -f "$0")" ]]; then exec "/opt/bw-monitor/restore.sh" "$@"; fi
exec "$DIR/deploy/postgres/restore.sh" "$@"
