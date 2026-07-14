# Quick Commands

## Install Monitor with IP

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo bash -s -- --public-ip 203.0.113.10 --port 8080 --run-retention-now
```

## Install Monitor with domain

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo bash -s -- --domain monitor.example.com --email ops@example.com
```

## Install/update one Agent

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install-agent.sh \
| sudo env BW_AGENT_API='https://monitor.example.com/push' BW_AGENT_TOKEN='TOKEN' bash
```

## Update Monitor

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/update.sh | sudo bash
```

## Doctor

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/doctor.sh | sudo bash
```

## Full audit

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/audit.sh \
| sudo bash -s -- --full-preflight
```

## Database check

```bash
sudo /opt/bw-monitor/db-check.sh --timeout 120
```

## Backup

```bash
sudo /opt/bw-monitor/backup.sh
```

## Diagnostics

```bash
sudo /opt/bw-monitor/collect-diagnostics.sh
```

## Logs

```bash
journalctl -fu bw-monitor.service
journalctl -fu bw-monitor-retention.service
journalctl -fu bwagent.service
```

## Safe Monitor removal

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/uninstall.sh \
| sudo bash -s -- --yes
```

## Agent removal

```bash
curl -fsSL https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/uninstall-agent.sh \
| sudo bash
```
