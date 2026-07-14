# BW Monitor Agent

The Agent is a persistent root service on each KVM/libvirt node. It samples locally, calculates deltas, preserves pending payloads, and commits counters only after a successful Monitor push.

## One-command install

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install-agent.sh \
| sudo env \
  BW_AGENT_API='https://monitor.example.com/push' \
  BW_AGENT_TOKEN='PASTE_THE_MONITOR_PUSH_TOKEN' \
  bash
```

## Main settings

```text
--sample-seconds 15
--push-seconds 300
--bridge-roles 'public:br0,private:br1'
--max-load 160
--skip-heavy-on-overload
--reset-state
--skip-connectivity-check
```

## Installed paths

```text
/usr/local/lib/bwagent/agent.py
/usr/local/sbin/bwagent-doctor
/etc/bwagent.env
/etc/systemd/system/bwagent.service
/var/lib/bw-agent/state.json
/var/lib/bw-agent/runtime.json
```

`/etc/bwagent.env` is mode `0600` and contains the push token. Do not commit or share it.

## Update

Run the install command again. Existing state is preserved unless `--reset-state` is explicitly supplied.

## Verify

```bash
systemctl is-active bwagent.service
systemctl status bwagent.service --no-pager -l
journalctl -u bwagent.service -n 100 --no-pager
bwagent-doctor
```

## Uninstall

Remove code/config and state:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-agent.sh \
| sudo bash
```

Preserve state:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-agent.sh \
| sudo bash -s -- --keep-state
```
