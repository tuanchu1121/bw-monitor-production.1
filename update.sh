#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
REF="${BW_GITHUB_REF:-main}"
TOKEN="${GITHUB_TOKEN:-}"
TMP=""
trap '[[ -n "$TMP" ]] && rm -rf "$TMP"' EXIT

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD}")" 2>/dev/null && pwd || true)"
if [[ -f "$SELF_DIR/deploy/monitor/install-monitor.sh" ]]; then
  export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
  exec bash "$SELF_DIR/deploy/monitor/install-monitor.sh" --update --recover-stuck "$@"
fi
command -v curl >/dev/null 2>&1 || { echo 'curl is required' >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo 'tar is required' >&2; exit 1; }
TMP="$(mktemp -d)"
headers=()
[[ -n "$TOKEN" ]] && headers=(-H "Authorization: Bearer $TOKEN" -H "X-GitHub-Api-Version: 2022-11-28")
curl -fL --retry 3 --retry-delay 2 --connect-timeout 15 "${headers[@]}"   "https://api.github.com/repos/$REPO/tarball/$REF" -o "$TMP/repo.tar.gz"
tar -xzf "$TMP/repo.tar.gz" -C "$TMP"
ROOT="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
[[ -f "$ROOT/deploy/monitor/install-monitor.sh" ]] || { echo 'Downloaded repository is incomplete.' >&2; exit 1; }
export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
exec bash "$ROOT/deploy/monitor/install-monitor.sh" --update --recover-stuck "$@"
