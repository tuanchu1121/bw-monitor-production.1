#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALLER="$ROOT/deploy/monitor/install-monitor.sh"
BOOTSTRAP="$ROOT/install.sh"

fail() { echo "ERROR: $*" >&2; exit 1; }
line_of() {
  local pattern="$1"
  grep -nF "$pattern" "$INSTALLER" | head -n1 | cut -d: -f1
}

[[ -f "$INSTALLER" ]] || fail "Installer not found"
bash -n "$INSTALLER"
bash -n "$BOOTSTRAP"

grep -q 'RELEASE="48.13.0-prod-r1"' "$INSTALLER" || fail "v48.13.0 release marker missing"
grep -q 'tuanchu1121/bw-monitor-production.1' "$BOOTSTRAP" || fail "bootstrap repository default is wrong"
grep -q 'tuanchu1121/bw-monitor-production.1' "$INSTALLER" || fail "deployment repository default is wrong"
grep -q '^wait_for_http()' "$INSTALLER" || fail "HTTP readiness retry helper is missing"
grep -q 'wait_for_http "http://127.0.0.1:$PORT/login" "Local health" 60 2' "$INSTALLER" || fail "local HTTP readiness loop is missing"
grep -q 'Credentials are preserved in $CREDENTIAL_FILE' "$INSTALLER" || fail "health failure does not preserve credentials"
grep -q 'Existing Admin password hash was found but $CREDENTIAL_FILE is missing' "$INSTALLER" || fail "interrupted-install credential recovery is missing"

cred_line="$(line_of 'Write root-only deployment credentials before service verification')"
verify_line="$(line_of 'Verify production services')"
[[ -n "$cred_line" && -n "$verify_line" ]] || fail "Could not locate credential/verification stages"
(( cred_line < verify_line )) || fail "Credentials must be written before service verification"

grep -q "printf 'BW_ADMIN_PASSWORD=%q" "$INSTALLER" || fail "Admin password is not written to the credential file"
grep -q "chmod 0600 \"\$CREDENTIAL_FILE\"" "$INSTALLER" || fail "Credential file mode 0600 is missing"

echo "PASS: production installer writes credentials before health checks, retries HTTP readiness, and recovers interrupted installs"
