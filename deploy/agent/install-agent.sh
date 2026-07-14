#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE="$SCRIPT_DIR/agent.py"
DOCTOR_SOURCE="$SCRIPT_DIR/doctor-agent.sh"
INSTALL_DIR="/usr/local/lib/bwagent"
SCRIPT_TARGET="$INSTALL_DIR/agent.py"
STATE_DIR="/var/lib/bw-agent"
ENV_FILE="/etc/bwagent.env"
SERVICE_FILE="/etc/systemd/system/bwagent.service"
DOCTOR_TARGET="/usr/local/sbin/bwagent-doctor"

API="${BW_AGENT_API:-}"
TOKEN="${BW_AGENT_TOKEN:-}"
SAMPLE_SECONDS="${BW_AGENT_SAMPLE_SECONDS:-15}"
PUSH_SECONDS="${BW_AGENT_PUSH_SECONDS:-300}"
MAX_LOAD="${BW_AGENT_MAX_LOAD:-160}"
SKIP_HEAVY="${BW_AGENT_SKIP_HEAVY_ON_OVERLOAD:-0}"
PPS_WARN="${BW_AGENT_PPS_WARN:-200000}"
MBPS_WARN="${BW_AGENT_MBPS_WARN:-800}"
BRIDGE_ROLES="${BW_AGENT_BRIDGE_ROLES:-public:br0,private:br1}"
RESET_STATE=0
SKIP_CHECK=0

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
usage() {
  cat <<'USAGE'
BW Agent one-command installer

Usage:
  install-agent.sh --api https://monitor.example.com/push --token TOKEN [options]

Options:
  --api URL                 Monitor /push endpoint.
  --token TOKEN             BW_MONITOR_TOKEN from the monitor.
  --sample-seconds NUMBER   Local network sample interval. Default: 15.
  --push-seconds NUMBER     HTTP push interval. Default: 300.
  --bridge-roles VALUE      Default: public:br0,private:br1.
  --max-load NUMBER         Agent high-load reference. Default: 160.
  --skip-heavy-on-overload  Allow heavy VM collection to be skipped on overload.
  --reset-state             Remove old counters/runtime before starting.
  --skip-connectivity-check Do not pre-check the monitor login endpoint.
  -h, --help                Show help.

Prefer environment variables for secrets:
  BW_AGENT_API='https://monitor.example.com/push' BW_AGENT_TOKEN='...' ./install-agent.sh
USAGE
}

while (($#)); do
  case "$1" in
    --api) API="${2:?missing value}"; shift 2 ;;
    --token) TOKEN="${2:?missing value}"; shift 2 ;;
    --sample-seconds) SAMPLE_SECONDS="${2:?missing value}"; shift 2 ;;
    --push-seconds) PUSH_SECONDS="${2:?missing value}"; shift 2 ;;
    --bridge-roles) BRIDGE_ROLES="${2:?missing value}"; shift 2 ;;
    --max-load) MAX_LOAD="${2:?missing value}"; shift 2 ;;
    --skip-heavy-on-overload) SKIP_HEAVY=1; shift ;;
    --reset-state) RESET_STATE=1; shift ;;
    --skip-connectivity-check) SKIP_CHECK=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$(id -u)" == "0" ]] || die "Run as root or through sudo."
[[ -f "$SOURCE" ]] || die "Agent source is missing: $SOURCE"
[[ -f "$DOCTOR_SOURCE" ]] || die "Agent doctor is missing: $DOCTOR_SOURCE"
[[ -n "$API" ]] || die "Missing --api or BW_AGENT_API."
[[ -n "$TOKEN" ]] || die "Missing --token or BW_AGENT_TOKEN."
[[ "$API" =~ ^https?://[^[:space:]\']+$ ]] || die "Invalid Agent API URL."
[[ "$TOKEN" =~ ^[A-Za-z0-9._:-]{6,200}$ ]] || die "Invalid token format."
[[ "$SAMPLE_SECONDS" =~ ^[0-9]+$ ]] && ((SAMPLE_SECONDS >= 5 && SAMPLE_SECONDS <= 300)) || die "sample-seconds must be 5-300."
[[ "$PUSH_SECONDS" =~ ^[0-9]+$ ]] && ((PUSH_SECONDS >= 60 && PUSH_SECONDS <= 3600)) || die "push-seconds must be 60-3600."
[[ "$MAX_LOAD" =~ ^[0-9]+([.][0-9]+)?$ ]] || die "Invalid max-load."
[[ "$SKIP_HEAVY" == "0" || "$SKIP_HEAVY" == "1" ]] || die "Invalid skip-heavy value."
[[ "$BRIDGE_ROLES" != *"'"* && "$BRIDGE_ROLES" != *$'\n'* ]] || die "Invalid bridge roles."

[[ "$API" == */push ]] || API="${API%/}/push"

for cmd in python3 virsh ip df systemctl; do
  command -v "$cmd" >/dev/null 2>&1 || die "Required command is missing: $cmd"
done

if ((SKIP_CHECK == 0)); then
  base="${API%/push}"
  log "Check monitor endpoint"
  code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 10 --max-time 20 "$base/login" || true)"
  [[ "$code" == "200" || "$code" == "302" ]] || die "Monitor pre-check failed: $base/login returned ${code:-no response}. Use --skip-connectivity-check only when intentional."
fi

log "Stop old BW Agent units"
for unit in bwagent.service bwagent.timer bw-agent.service bw-agent.timer; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
done
for pid in $(pgrep -f '^(/usr/bin/)?python3? /usr/local/lib/bwagent/agent\.py$' 2>/dev/null || true); do
  kill -TERM "$pid" 2>/dev/null || true
done
sleep 1

log "Install Agent source and protected environment"
install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -d -o root -g root -m 0700 "$STATE_DIR"
install -o root -g root -m 0755 "$SOURCE" "$SCRIPT_TARGET"
install -o root -g root -m 0755 "$DOCTOR_SOURCE" "$DOCTOR_TARGET"
python3 -m py_compile "$SCRIPT_TARGET"
if ((RESET_STATE)); then
  rm -f "$STATE_DIR/state.json" "$STATE_DIR/runtime.json"
fi

cat > "$ENV_FILE" <<EOF_ENV
BW_AGENT_API='$API'
BW_AGENT_TOKEN='$TOKEN'
BW_AGENT_STATE='$STATE_DIR/state.json'
BW_AGENT_RUNTIME='$STATE_DIR/runtime.json'
BW_AGENT_SAMPLE_SECONDS='$SAMPLE_SECONDS'
BW_AGENT_PUSH_SECONDS='$PUSH_SECONDS'
BW_AGENT_MAX_LOAD='$MAX_LOAD'
BW_AGENT_SKIP_HEAVY_ON_OVERLOAD='$SKIP_HEAVY'
BW_AGENT_PPS_WARN='$PPS_WARN'
BW_AGENT_MBPS_WARN='$MBPS_WARN'
BW_AGENT_STALE_IFACE_SECONDS='600'
BW_AGENT_COLLECT_VM_NET='1'
BW_AGENT_COLLECT_VM_PERF='1'
BW_AGENT_COLLECT_NODE_HOST='1'
BW_AGENT_COLLECT_PHYSICAL_NET='1'
BW_AGENT_BRIDGE_ROLES='$BRIDGE_ROLES'
BW_AGENT_API_TIMEOUT='30'
BW_AGENT_DOMSTATS_TIMEOUT='180'
BW_AGENT_VIRSH_LIST_TIMEOUT='30'
BW_AGENT_DOMIFLIST_TIMEOUT='30'
BW_AGENT_QUIET='0'
EOF_ENV
chmod 0600 "$ENV_FILE"

cat > "$SERVICE_FILE" <<'EOF_SERVICE'
[Unit]
Description=BW Monitor Agent v10 persistent collector
Wants=network-online.target
After=network-online.target libvirtd.service
ConditionPathExists=/usr/local/lib/bwagent/agent.py

[Service]
Type=simple
User=root
Group=root
EnvironmentFile=/etc/bwagent.env
ExecStart=/usr/bin/python3 /usr/local/lib/bwagent/agent.py
Restart=always
RestartSec=5
Nice=10
IOSchedulingClass=idle
MemoryHigh=256M
MemoryMax=512M
TimeoutStopSec=30
KillSignal=SIGTERM
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=full
ReadWritePaths=/var/lib/bw-agent /run
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF_SERVICE

rm -f /etc/systemd/system/bwagent.timer /etc/systemd/system/bw-agent.timer \
      /usr/local/sbin/bwagent-load-check /usr/local/sbin/bw-agent-load-check
systemctl daemon-reload
systemctl reset-failed bwagent.service >/dev/null 2>&1 || true
systemctl enable --now bwagent.service

for _ in $(seq 1 20); do
  systemctl is-active --quiet bwagent.service && break
  sleep 1
done
systemctl is-active --quiet bwagent.service || {
  journalctl -u bwagent.service -n 100 --no-pager >&2 || true
  die "bwagent.service did not become active."
}
sleep 3
systemctl is-active --quiet bwagent.service || die "bwagent.service exited after startup."

cat <<EOF_DONE

BW Agent installed successfully.
Service:       active
Monitor API:   $API
Sample:        ${SAMPLE_SECONDS}s
Push:          ${PUSH_SECONDS}s
Environment:   $ENV_FILE (0600)
State:         $STATE_DIR
Logs:          journalctl -fu bwagent.service
Status:        systemctl status bwagent.service --no-pager -l
Doctor:        bwagent-doctor
EOF_DONE
