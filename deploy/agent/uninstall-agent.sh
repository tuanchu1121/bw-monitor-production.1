#!/usr/bin/env bash
set -Eeuo pipefail
KEEP_STATE=0
while (($#)); do
  case "$1" in
    --keep-state) KEEP_STATE=1; shift ;;
    -h|--help)
      echo 'Usage: uninstall-agent.sh [--keep-state]'
      exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 1 ;;
  esac
done
[[ "$(id -u)" == "0" ]] || { echo 'Run as root.' >&2; exit 1; }

for unit in bwagent.service bwagent.timer bw-agent.service bw-agent.timer; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
  systemctl kill --kill-who=all --signal=KILL "$unit" >/dev/null 2>&1 || true
done
for pid in $(pgrep -f '^(/usr/bin/)?python3? /usr/local/lib/bwagent/agent\.py$' 2>/dev/null || true); do
  kill -KILL "$pid" 2>/dev/null || true
done
rm -f \
  /etc/systemd/system/bwagent.service \
  /etc/systemd/system/bwagent.timer \
  /etc/systemd/system/bw-agent.service \
  /etc/systemd/system/bw-agent.timer \
  /usr/lib/systemd/system/bwagent.service \
  /usr/lib/systemd/system/bwagent.timer \
  /usr/lib/systemd/system/bw-agent.service \
  /usr/lib/systemd/system/bw-agent.timer \
  /lib/systemd/system/bwagent.service \
  /lib/systemd/system/bwagent.timer \
  /lib/systemd/system/bw-agent.service \
  /lib/systemd/system/bw-agent.timer \
  /etc/bwagent.env \
  /etc/default/bwagent \
  /etc/sysconfig/bwagent \
  /usr/local/sbin/bwagent-load-check \
  /usr/local/sbin/bw-agent-load-check \
  /usr/local/sbin/bwagent-doctor
rm -rf /usr/local/lib/bwagent /opt/bwagent /opt/bw-agent /var/log/bwagent
if ((KEEP_STATE == 0)); then
  rm -rf /var/lib/bw-agent /var/lib/bwagent
fi
systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true

echo 'BW Agent removed successfully.'
if ((KEEP_STATE)); then echo 'State preserved at /var/lib/bw-agent.'; fi
