#!/usr/bin/env bash
set -Eeuo pipefail
REPO="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
REF="${BW_GITHUB_REF:-main}"
TOKEN="${GITHUB_TOKEN:-}"
SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD}")" 2>/dev/null && pwd || true)"
if [[ -x "$SELF_DIR/deploy/postgres/install-postgres-native.sh" ]]; then
  export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
  exec bash "$SELF_DIR/deploy/postgres/install-postgres-native.sh" "$@"
fi
command -v curl >/dev/null || { echo 'curl is required' >&2; exit 1; }
command -v tar >/dev/null || { echo 'tar is required' >&2; exit 1; }
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [[ -n "$TOKEN" ]]; then
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 \
    -H "Authorization: Bearer $TOKEN" -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/$REPO/tarball/$REF" -o "$TMP/repo.tar.gz"
else
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 \
    "https://codeload.github.com/$REPO/tar.gz/$REF" -o "$TMP/repo.tar.gz"
fi
tar -xzf "$TMP/repo.tar.gz" -C "$TMP"
ROOT="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
[[ -x "$ROOT/deploy/postgres/install-postgres-native.sh" ]] || { echo 'Downloaded repository is incomplete. Push the v50 release to the selected ref.' >&2; exit 1; }
export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
exec bash "$ROOT/deploy/postgres/install-postgres-native.sh" "$@"
