#!/usr/bin/env bash
set -Eeuo pipefail
REPO="tuanchu1121/bw-monitor-production.1"
VISIBILITY="--private"
FORCE=0
CREATE_RELEASE=0
SKIP_AUDIT=0
TAG="v48.13.6-prod-r1"

usage(){ cat <<'USAGE'
Usage: publish-github.sh [options]

Options:
  --repo OWNER/NAME   Target repository. Default: tuanchu1121/bw-monitor-production.1
  --private           Create a private repository when missing (default)
  --public            Create a public repository when missing
  --release           Build archives and create/update tag/release v48.13.6-prod-r1
  --tag NAME          Override the release tag
  --force             Push main with --force-with-lease
  --skip-audit        Skip local validation. Not recommended
  -h, --help          Show help

Prerequisite:
  gh auth login
USAGE
}
while (($#)); do case "$1" in
  --repo) REPO="${2:?missing value}"; shift 2;;
  --private) VISIBILITY="--private"; shift;;
  --public) VISIBILITY="--public"; shift;;
  --release) CREATE_RELEASE=1; shift;;
  --tag) TAG="${2:?missing value}"; shift 2;;
  --force) FORCE=1; shift;;
  --skip-audit) SKIP_AUDIT=1; shift;;
  -h|--help) usage; exit 0;;
  *) echo "Unknown option: $1" >&2; exit 2;;
esac; done

command -v git >/dev/null 2>&1 || { echo 'git is required.' >&2; exit 1; }
command -v gh >/dev/null 2>&1 || { echo 'GitHub CLI gh is required.' >&2; exit 1; }
gh auth status >/dev/null
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if ((SKIP_AUDIT == 0)); then
  ./tools/release-audit.sh
fi

[[ -d .git ]] || git init -b main
if ! git config user.name >/dev/null; then git config user.name "${GIT_AUTHOR_NAME:-Chu Van Tuan}"; fi
if ! git config user.email >/dev/null; then git config user.email "${GIT_AUTHOR_EMAIL:-tuanchuu1121@gmail.com}"; fi

git add -A
if ! git diff --cached --quiet; then
  git commit -m "BW Monitor v48.13.6-r1 grouped-storage production"
fi

if gh repo view "$REPO" >/dev/null 2>&1; then
  if git remote get-url origin >/dev/null 2>&1; then git remote set-url origin "https://github.com/$REPO.git"; else git remote add origin "https://github.com/$REPO.git"; fi
  if ((FORCE)); then git push -u origin main --force-with-lease; else git push -u origin main; fi
else
  gh repo create "$REPO" "$VISIBILITY" --source=. --remote=origin --push
fi

if ((CREATE_RELEASE)); then
  ./tools/build-dist.sh
  git tag -f "$TAG"
  git push origin "$TAG" --force
  mapfile -t assets < <(find dist -maxdepth 1 -type f \( -name '*.zip' -o -name '*.tar.gz' -o -name 'SHA256SUMS' \) | sort)
  if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
    gh release upload "$TAG" "${assets[@]}" --repo "$REPO" --clobber
  else
    gh release create "$TAG" "${assets[@]}" --repo "$REPO" --title "BW Monitor $TAG" --generate-notes
  fi
fi

echo
echo "Published: https://github.com/$REPO"
echo "Raw installer: https://raw.githubusercontent.com/$REPO/main/install.sh"
