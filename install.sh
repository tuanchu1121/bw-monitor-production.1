#!/usr/bin/env bash
set -Eeuo pipefail

REPO="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
REF="${BW_GITHUB_REF:-main}"
TOKEN="${GITHUB_TOKEN:-}"
SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$PWD}")" 2>/dev/null && pwd || true)"

repo_complete() {
  local root="$1" path
  local missing=()
  for path in \
    deploy/postgres/install-postgres-native.sh \
    app/app.py \
    app/bw_pg.py \
    postgres/docker-compose.yml \
    requirements.txt \
    VERSION
  do
    [[ -f "$root/$path" ]] || missing+=("$path")
  done
  if ((${#missing[@]})); then
    printf 'Downloaded repository is incomplete. Missing:\n' >&2
    printf '  - %s\n' "${missing[@]}" >&2
    printf 'Push the complete v50 release to: %s@%s\n' "$REPO" "$REF" >&2
    return 1
  fi
}

normalize_shell_modes() {
  local root="$1"
  # GitHub Desktop on Windows may publish .sh files as 0644. Runtime never
  # depends on that Git mode, but normalizing makes local Linux use convenient.
  find "$root" -type f -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true
}

if repo_complete "$SELF_DIR" >/dev/null 2>&1; then
  normalize_shell_modes "$SELF_DIR"
  export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
  exec bash "$SELF_DIR/deploy/postgres/install-postgres-native.sh" "$@"
fi

command -v curl >/dev/null 2>&1 || { echo 'curl is required' >&2; exit 1; }
command -v tar >/dev/null 2>&1 || { echo 'tar is required' >&2; exit 1; }
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

if [[ -n "$TOKEN" ]]; then
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 \
    -H "Authorization: Bearer $TOKEN" \
    -H 'X-GitHub-Api-Version: 2022-11-28' \
    "https://api.github.com/repos/$REPO/tarball/$REF" \
    -o "$TMP/repo.tar.gz"
else
  curl -fL --retry 4 --retry-delay 2 --connect-timeout 20 \
    "https://codeload.github.com/$REPO/tar.gz/$REF" \
    -o "$TMP/repo.tar.gz"
fi

tar -xzf "$TMP/repo.tar.gz" -C "$TMP"
ROOT="$(find "$TMP" -mindepth 1 -maxdepth 1 -type d | head -n1)"
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo 'Downloaded repository archive could not be extracted.' >&2; exit 1; }
repo_complete "$ROOT"
normalize_shell_modes "$ROOT"
export BW_GITHUB_REPO="$REPO" BW_GITHUB_REF="$REF"
exec bash "$ROOT/deploy/postgres/install-postgres-native.sh" "$@"
