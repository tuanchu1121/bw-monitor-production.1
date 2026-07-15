#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
COPY="$TMP/repo"
mkdir -p "$COPY"

tar --exclude='./.git' --exclude='./dist' --exclude='*/__pycache__' \
  -C "$ROOT" -cf - . | tar -C "$COPY" -xf -
find "$COPY" -type f -name '*.sh' -exec chmod 0644 {} +

[[ ! -x "$COPY/install.sh" ]] || { echo 'Simulation failed to remove executable mode.' >&2; exit 1; }
bash "$COPY/install.sh" --help >/dev/null
bash "$COPY/install-enterprise.sh" --help >/dev/null
bash "$COPY/install-core.sh" --help >/dev/null
bash "$COPY/install-agent.sh" --help >/dev/null
bash "$COPY/uninstall-agent.sh" --help >/dev/null
bash "$COPY/preflight.sh" --help >/dev/null

grep -Fq 'repo_complete "$ROOT"' "$COPY/install.sh"
grep -Fq 'normalize_shell_modes "$ROOT"' "$COPY/install.sh"
grep -Fq 'exec bash "$ROOT/deploy/postgres/install-postgres-native.sh"' "$COPY/install.sh"

echo 'PASS: Windows GitHub Desktop non-executable shell mode compatibility'
