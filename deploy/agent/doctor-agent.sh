#!/usr/bin/env bash
set -Eeuo pipefail
FAIL=0
ok(){ echo "[ OK ] $*"; }
fail(){ echo "[FAIL] $*"; FAIL=$((FAIL+1)); }
warn(){ echo "[WARN] $*"; }
[[ -f /usr/local/lib/bwagent/agent.py ]] && ok 'Agent source exists' || fail 'Agent source is missing'
python3 -m py_compile /usr/local/lib/bwagent/agent.py && ok 'Agent source compiles' || fail 'Agent source does not compile'
systemctl is-active --quiet bwagent.service && ok 'bwagent.service is active' || fail 'bwagent.service is not active'
systemctl is-enabled --quiet bwagent.service && ok 'bwagent.service is enabled' || warn 'bwagent.service is not enabled'
if [[ -f /etc/bwagent.env ]]; then
  mode="$(stat -c %a /etc/bwagent.env)"; [[ "$mode" == 600 ]] && ok '/etc/bwagent.env mode is 0600' || warn "/etc/bwagent.env mode is $mode"
  awk -F= '/^(BW_AGENT_API|BW_AGENT_SAMPLE_SECONDS|BW_AGENT_PUSH_SECONDS|BW_AGENT_BRIDGE_ROLES)=/{print}' /etc/bwagent.env
else fail '/etc/bwagent.env is missing'; fi
command -v virsh >/dev/null && ok 'virsh is available' || fail 'virsh is missing'
echo; journalctl -u bwagent.service -n 40 --no-pager || true
((FAIL == 0)) || exit 2
