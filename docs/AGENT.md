# BW Agent

The complete Agent source is `deploy/agent/agent.py`.

Exact defaults:

```text
local network sample: 15 seconds
Monitor push:         300 seconds
```

The Agent keeps a durable pending payload. On failure it retries the exact pending payload before building a new one. The Monitor de-duplicates by Node and push time.

Install one node:

```bash
read -rsp 'BW Agent token: ' BW_TOKEN
echo

curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install-agent.sh \
| env \
BW_AGENT_API='https://monitor.example.com/push' \
BW_AGENT_TOKEN="$BW_TOKEN" \
bash

unset BW_TOKEN
```

Check:

```bash
systemctl status bwagent --no-pager -l
journalctl -u bwagent -n 200 --no-pager
systemctl show bwagent -p ProtectHome --value
```

Expected `ProtectHome=read-only`. This lets the service inspect `/home` while preserving systemd hardening.
