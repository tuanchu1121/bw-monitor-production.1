#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
REF="${BW_GITHUB_REF:-main}"
TOKEN="${GITHUB_TOKEN:-}"
SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD}")" 2>/dev/null && pwd || true)"
if [[ -x "$SELF_DIR/deploy/enterprise/uninstall-enterprise.sh" ]]; then exec bash "$SELF_DIR/deploy/enterprise/uninstall-enterprise.sh" "$@"; fi
command -v curl >/dev/null || { echo 'curl is required' >&2; exit 1; }
command -v tar >/dev/null || { echo 'tar is required' >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
headers=(); [[ -n "$TOKEN" ]] && headers=(-H "Authorization: Bearer $TOKEN" -H "X-GitHub-Api-Version: 2022-11-28")
curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 "${headers[@]}" "https://api.github.com/repos/$REPO/tarball/$REF" -o "$TMP/repo.tar.gz"
tar -xzf "$TMP/repo.tar.gz" -C "$TMP"
ROOT="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
exec bash "$ROOT/deploy/enterprise/uninstall-enterprise.sh" "$@"
