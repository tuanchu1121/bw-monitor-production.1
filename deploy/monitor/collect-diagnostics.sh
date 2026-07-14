#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${BW_MONITOR_DIR:-/opt/bw-monitor}"
ENV_FILE="${BW_MONITOR_ENV:-/etc/default/bw-monitor}"
OUT_DIR="${BW_DIAG_DIR:-/root}"
stamp="$(date +%Y%m%d-%H%M%S)"; work="$(mktemp -d)"; bundle="$OUT_DIR/bw-monitor-diagnostics-$stamp.tar.gz"
trap 'rm -rf "$work"' EXIT
mkdir -p "$work"
redact(){
  sed -E \
    -e "s#^(BW_MONITOR_TOKEN|BW_ADMIN_PASSWORD_HASH|BW_ADMIN_SECRET_KEY|BW_ADMIN_PASSWORD|BW_AGENT_TOKEN)=.*#\1='<REDACTED>'#" \
    -e "s#(Authorization: Bearer )[A-Za-z0-9._:-]+#\1<REDACTED>#g"
}
{
  echo "generated_at=$(date --iso-8601=seconds)"; hostnamectl 2>/dev/null || hostname; uname -a; cat /etc/os-release 2>/dev/null || true
} > "$work/system.txt"
for cmd in \
  "systemctl status bw-monitor.service --no-pager -l" \
  "systemctl status bw-monitor-retention.timer --no-pager -l" \
  "systemctl status bw-monitor-retention.service --no-pager -l" \
  "systemctl list-timers bw-monitor-retention.timer --all --no-pager" \
  "systemctl list-units --all 'bw-monitor-maintenance@*.service' --no-pager" \
  "ss -lntp" \
  "df -h" \
  "df -i" \
  "ps auxww"; do
  name="$(echo "$cmd" | tr ' /@*' '_____')"; bash -lc "$cmd" > "$work/$name.txt" 2>&1 || true
done
journalctl -u bw-monitor.service -u bw-monitor-retention.service --since '48 hours ago' --no-pager | redact > "$work/journal.txt" 2>&1 || true
[[ -r "$ENV_FILE" ]] && redact < "$ENV_FILE" > "$work/bw-monitor.env.redacted"
[[ -r /root/bw-monitor-credentials.env ]] && redact < /root/bw-monitor-credentials.env > "$work/credentials.env.redacted"
[[ -f "$APP_DIR/DEPLOY_VERSION" ]] && cp "$APP_DIR/DEPLOY_VERSION" "$work/"
[[ -f "$APP_DIR/app.py" ]] && { sha256sum "$APP_DIR/app.py" > "$work/app.sha256"; grep -nE 'V48129_VERSION|V48129_BUILD|ABUSE_ENGINE_VERSION' "$APP_DIR/app.py" > "$work/app-markers.txt" || true; }
ls -lah "$APP_DIR" > "$work/app-directory.txt" 2>&1 || true
if [[ -x "$APP_DIR/db-check.sh" ]]; then "$APP_DIR/db-check.sh" --no-integrity --json > "$work/database.json" 2>&1 || true; fi
if command -v nginx >/dev/null 2>&1; then nginx -T 2>&1 | redact > "$work/nginx.txt" || true; fi
find "$work" -type f -exec chmod 0600 {} +
tar -C "$work" -czf "$bundle" .
chmod 0600 "$bundle"
echo "Sanitized diagnostics bundle: $bundle"
echo 'Review it before sharing. Database rows and secret values are not included.'
