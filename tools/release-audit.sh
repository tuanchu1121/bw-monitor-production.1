#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
PYTHON="${BW_AUDIT_PYTHON:-}"
USE_CURRENT=0
[[ "${1:-}" == "--use-current-python" ]] && USE_CURRENT=1

log(){ printf '\n==> %s\n' "$*"; }
fail(){ echo "ERROR: $*" >&2; exit 1; }
cd "$ROOT"

log 'Remove generated Python caches and reject database files'
find . -path './.git' -prune -o -path './dist' -prune -o -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -not -path './.git/*' -not -path './dist/*' -delete
if find . -path './.git' -prune -o -path './dist' -prune -o \( -name 'bandwidth.db*' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print | grep -q .; then
  find . -path './.git' -prune -o -path './dist' -prune -o \( -name 'bandwidth.db*' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print
  fail 'Database files are present.'
fi
if grep -RInE --exclude-dir=.git --exclude-dir=dist \
  '(bwm_live_[0-9a-f]{12}_[A-Za-z0-9]{32,}|bwm_push_[A-Za-z0-9]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY)' .; then
  fail 'Potential committed secret detected.'
fi

log 'Validate shell syntax'
while IFS= read -r -d '' file; do echo "bash -n $file"; bash -n "$file"; done < <(find . -path './.git' -prune -o -path './dist' -prune -o -type f -name '*.sh' -print0)

if ((USE_CURRENT)); then
  [[ -n "$PYTHON" ]] || PYTHON="$(command -v python3)"
else
  log 'Create isolated validation venv'
  python3 -m venv "$TMP/venv"
  PYTHON="$TMP/venv/bin/python3"
  "$PYTHON" -m pip install --upgrade pip >/dev/null
  "$PYTHON" -m pip install -r requirements.txt PyYAML >/dev/null
fi

log 'Validate Python syntax'
"$PYTHON" -m py_compile release/*.py deploy/agent/agent.py

log 'Validate YAML syntax'
"$PYTHON" - <<'PY_YAML'
from pathlib import Path
import yaml
paths = sorted(Path('ansible').glob('*.yml')) + sorted(Path('.github/workflows').glob('*.yml'))
for path in paths:
    yaml.safe_load(path.read_text(encoding='utf-8'))
    print('YAML OK:', path)
PY_YAML

log 'Verify production installer flow'
./tools/test-installer-flow.sh

log 'Verify release identity and deployment links'
grep -q '^48.13.0-prod-r1$' VERSION || fail 'Root VERSION mismatch.'
grep -q '^48.13.0$' release/VERSION || fail 'Release VERSION mismatch.'
grep -q 'V48129_BUILD = "r4"' release/bw_monitor_app_v48_12_9_operations_ui.py || fail 'Application r4 marker missing.'
grep -q 'install_bw_monitor_v48_12_9.sh' deploy/monitor/install-monitor.sh || fail 'Production installer is not linked to v48.12.9.'
grep -q 'db-check.sh' deploy/monitor/install-monitor.sh || fail 'Database checker is not installed.'
grep -q 'collect-diagnostics.sh' deploy/monitor/install-monitor.sh || fail 'Diagnostics collector is not installed.'

log 'Run full release preflight'
(
  cd release
  BW_PYTHON_BIN="$PYTHON" BW_PREFLIGHT_ONLY=1 ./install_bw_monitor_v48_12_9.sh
)

log 'Remove Python caches created by validation'
find . -path './.git' -prune -o -path './dist' -prune -o -type d -name '__pycache__' -prune -exec rm -rf {} +
find . -type f \( -name '*.pyc' -o -name '*.pyo' \) -not -path './.git/*' -not -path './dist/*' -delete

log 'Generate and verify checksum manifests'
find release -maxdepth 1 -type f ! -name 'SHA256SUMS*' -print0 | sort -z | xargs -0 sha256sum > release/SHA256SUMS_v48_12_9.txt
find . -path './.git' -prune -o -path './dist' -prune -o -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS
sha256sum -c SHA256SUMS >/dev/null

log 'Release audit passed'
