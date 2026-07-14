#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
RUN_PREFLIGHT=0
FULL_DB=0

usage(){ cat <<'USAGE'
Usage: audit.sh [--full-preflight] [--full-db]

Production audit for a deployed BW Monitor.
  --full-preflight  Run every bundled regression suite from the repository
  --full-db         Run SQLite integrity_check instead of quick_check
USAGE
}
while (($#)); do case "$1" in
  --full-preflight) RUN_PREFLIGHT=1; shift;;
  --full-db) FULL_DB=1; shift;;
  -h|--help) usage; exit 0;;
  *) echo "Unknown option: $1" >&2; exit 2;;
esac; done

FAIL=0; WARN=0
section(){ printf '\n\n### %s\n%s\n' "$*" '========================================================================'; }
ok(){ printf '[ OK ] %s\n' "$*"; }
warn(){ printf '[WARN] %s\n' "$*"; WARN=$((WARN+1)); }
fail(){ printf '[FAIL] %s\n' "$*"; FAIL=$((FAIL+1)); }

section 'Identity and release'
echo "Host: $(hostname -f 2>/dev/null || hostname)"
echo "Kernel: $(uname -srmo)"
[[ -r /etc/os-release ]] && grep -E '^(PRETTY_NAME|VERSION_ID)=' /etc/os-release || true
echo "Time: $(date --iso-8601=seconds)"
if [[ -f "$APP_DIR/DEPLOY_VERSION" ]]; then
  echo "Deploy version: $(cat "$APP_DIR/DEPLOY_VERSION")"
else warn 'DEPLOY_VERSION is missing'; fi
if [[ -f "$APP_DIR/app.py" ]]; then
  grep -nE 'V48129_VERSION|V48129_BUILD|ABUSE_ENGINE_VERSION' "$APP_DIR/app.py" | tail -n 10 || warn 'Expected release markers were not found'
else fail "$APP_DIR/app.py is missing"; fi

section 'Services and timers'
for unit in bw-monitor.service bw-monitor-retention.timer bw-monitor-retention.service; do
  printf '%-36s enabled=%-10s active=%s\n' "$unit" "$(systemctl is-enabled "$unit" 2>/dev/null || true)" "$(systemctl is-active "$unit" 2>/dev/null || true)"
done
systemctl list-timers bw-monitor-retention.timer --all --no-pager || true
mapfile -t maintenance < <(systemctl list-units --all --no-legend 'bw-monitor-maintenance@*.service' 2>/dev/null | awk '{print $1,$3,$4}')
printf 'Maintenance units: %s\n' "${#maintenance[@]}"
printf '%s\n' "${maintenance[@]:-none}"
pgrep -af '/opt/bw-monitor/(app.py|bw_monitor_maintenance.py|bw_monitor_retention.py)' || true

section 'Source and Python'
if [[ -x "$APP_DIR/venv/bin/python3" ]]; then
  "$APP_DIR/venv/bin/python3" --version
  "$APP_DIR/venv/bin/pip" freeze | grep -E '^(Flask|Werkzeug|gunicorn)==' || true
  if "$APP_DIR/venv/bin/python3" -m py_compile "$APP_DIR/app.py"; then ok 'app.py compiles'; else fail 'app.py does not compile'; fi
else fail 'Python venv is missing'; fi

section 'Configuration permissions'
for f in "$ENV_FILE" /root/bw-monitor-credentials.env; do
  if [[ -e "$f" ]]; then stat -c '%a %U:%G %n' "$f"; else warn "Missing $f"; fi
done
if [[ -r "$ENV_FILE" ]]; then
  awk -F= '/^(BW_DOMAIN|BW_PUBLIC_IP|BW_PUBLIC_PORT|BW_PUBLIC_URL|BW_PUSH_URL|BW_GUNICORN_BIND|BW_GUNICORN_WORKERS|BW_GUNICORN_THREADS|BW_RAW_RETENTION_DAYS|BW_HOURLY_RETENTION_DAYS|BW_NGINX_ENABLED|BW_TLS_ENABLED)=/{print}' "$ENV_FILE"
fi

section 'Sockets, reverse proxy and HTTP'
ss -lntp | grep -E ':(80|443|8080)\b|gunicorn|nginx' || true
if command -v nginx >/dev/null 2>&1; then nginx -t && ok 'Nginx configuration is valid' || fail 'Nginx configuration is invalid'; fi
if [[ -r "$ENV_FILE" ]]; then
  set -a; . "$ENV_FILE"; set +a
fi
bind="${BW_GUNICORN_BIND:-127.0.0.1:8080}"; port="${bind##*:}"
for path in /login /health /admin/login; do
  code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 3 --max-time 15 "http://127.0.0.1:$port$path" || true)"
  printf '%-24s HTTP %s\n' "local $path" "${code:-failed}"
done
if [[ -n "${BW_PUBLIC_URL:-}" ]]; then
  code="$(curl -ksS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 20 "${BW_PUBLIC_URL%/}/login" || true)"
  printf '%-24s HTTP %s\n' 'public /login' "${code:-failed}"
fi
if [[ -n "${BW_DOMAIN:-}" ]] && command -v openssl >/dev/null 2>&1; then
  echo | openssl s_client -servername "$BW_DOMAIN" -connect "$BW_DOMAIN:443" 2>/dev/null | openssl x509 -noout -subject -issuer -dates 2>/dev/null || warn 'Could not read public TLS certificate'
fi

section 'Disk and database files'
df -h "$APP_DIR" || true
ls -lh "$APP_DIR"/bandwidth.db* 2>/dev/null || true
if [[ -x "$APP_DIR/db-check.sh" ]]; then
  args=(--timeout 120); ((FULL_DB)) && args+=(--full)
  rc=0
  "$APP_DIR/db-check.sh" "${args[@]}" || rc=$?
  if ((rc == 124)); then warn 'Database integrity scan timed out; rerun with a longer --timeout';
  elif ((rc != 0)); then fail "Database check failed with exit $rc";
  else ok 'Database check passed'; fi
else fail "$APP_DIR/db-check.sh is missing"; fi

section 'Recent warnings and errors'
journalctl -u bw-monitor.service -u bw-monitor-retention.service --since '24 hours ago' -p warning --no-pager | tail -n 300 || true

if ((RUN_PREFLIGHT)); then
  section 'Full bundled release preflight'
  if [[ -x "$REPO_ROOT/release/install_bw_monitor_v48_12_9.sh" ]]; then
    if (cd "$REPO_ROOT/release" && BW_PYTHON_BIN="$APP_DIR/venv/bin/python3" BW_PREFLIGHT_ONLY=1 ./install_bw_monitor_v48_12_9.sh); then
      ok 'Full release preflight passed'
    else
      fail 'Full release preflight failed'
    fi
  else
    fail 'Bundled release installer is unavailable; run audit through the GitHub repository wrapper'
  fi
fi

section 'Audit summary'
printf 'Failures: %d\nWarnings: %d\n' "$FAIL" "$WARN"
((FAIL == 0)) || exit 2
