# BW Monitor v48.12.9-r4 Production

BW Monitor is a production-oriented monitoring stack for KVM/libvirt nodes and their virtual machines. It combines a persistent node Agent, a Flask/Gunicorn Monitor, SQLite WAL storage, bounded retention, scoped REST APIs, an Abuse Engine, an operations dashboard, and safe maintenance tooling.

This repository contains the complete deployment source for **BW Monitor v48.12.9-r4-prod-r2**. It is designed for Debian 12+ and Ubuntu 22.04+ servers using systemd.

> This is proprietary software. See [LICENSE](LICENSE). Do not publish credentials, database files, API keys, or production-specific secrets.

## Architecture

```text
KVM/libvirt nodes
  └─ bwagent.service
       ├─ samples VM/network state locally every 15 seconds
       ├─ aggregates VM CPU, RAM, disk, network and node health
       └─ pushes a durable payload every 300 seconds
                  │
                  ▼
       HTTP IP:port or HTTPS domain
                  │
                  ▼
        Nginx → Gunicorn → Flask
                  │
                  ▼
  SQLite WAL + current caches + Abuse Engine
                  │
                  ├─ Dashboard / Admin
                  ├─ Scoped REST API v1
                  ├─ single-worker maintenance
                  └─ bounded retention timer
```

Default retention policy:

```text
0 → 48 hours     keep every real 5-minute push
48 hours → 7 days keep one real synchronized snapshot per hour
> 7 days          delete historical metrics/logs/events
```

Current state, inventory, users, API keys, Allowed IP/CIDR rules, current Abuse state, and application settings are not removed by historical retention.

## Repository layout

```text
install.sh                     one-command Monitor installer
update.sh                      one-command in-place update
uninstall.sh                   safe Monitor removal
install-agent.sh               one-command Agent install/update
uninstall-agent.sh             Agent removal
doctor.sh                      fast deployed-Monitor health check
audit.sh                       deep production audit
db-check.sh                    read-only SQLite health check
backup.sh                      consistent SQLite/config backup
restore.sh                     guarded backup restore
collect-diagnostics.sh         sanitized support bundle
publish-github.sh              validate, push and optionally create a release

release/                       exact v48.12.9-r4 application release and tests
deploy/monitor/                Monitor systemd/Nginx/operations tooling
deploy/agent/                  Agent service, installer and doctor
ansible/                       Agent and Monitor playbooks
docs/                          English operations documentation
.github/workflows/             CI and release validation
```

## Quick start: new Monitor by public IP

On a minimal Debian/Ubuntu server, use this complete bootstrap command. It installs `curl` first, then deploys BW Monitor:

```bash
sudo apt-get update \
&& sudo apt-get install -y curl ca-certificates \
&& curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install.sh \
| sudo bash -s -- \
  --public-ip 203.0.113.10 \
  --port 8080 \
  --run-retention-now
```

The installer generates a strong Admin password and Agent push token when they are not supplied. The credential file is written **before** service health verification, so credentials remain available even when a later Nginx, TLS or application readiness check fails. Root-only credentials are written to:

```text
/root/bw-monitor-credentials.env
```

Show them:

```bash
sudo cat /root/bw-monitor-credentials.env
```

IP mode exposes Gunicorn on the selected port and uses HTTP. Use a domain with HTTPS for Internet-facing production deployments whenever possible.

## Quick start: new Monitor by domain and HTTPS

Before running this command:

1. Point the domain A/AAAA record to the Monitor server.
2. Allow inbound TCP 80 and 443.
3. Ensure no other web server is occupying the requested Nginx site.

```bash
sudo apt-get update \
&& sudo apt-get install -y curl ca-certificates \
&& curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install.sh \
| sudo bash -s -- \
  --domain monitor.example.com \
  --email ops@example.com \
  --run-retention-now
```

Domain mode automatically installs Nginx and Certbot, binds Gunicorn to loopback, enables trusted-proxy handling only for local Nginx, enables secure cookies after certificate issuance, and verifies public HTTPS.

Resulting endpoints:

```text
Dashboard:  https://monitor.example.com/
Admin:      https://monitor.example.com/admin
Agent push: https://monitor.example.com/push
```

## Install or update an Agent on one KVM node

Use the push URL and token printed by the Monitor installer:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install-agent.sh \
| sudo env \
  BW_AGENT_API='https://monitor.example.com/push' \
  BW_AGENT_TOKEN='PASTE_THE_MONITOR_PUSH_TOKEN' \
  bash
```

For an IP Monitor:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install-agent.sh \
| sudo env \
  BW_AGENT_API='http://203.0.113.10:8080/push' \
  BW_AGENT_TOKEN='PASTE_THE_MONITOR_PUSH_TOKEN' \
  bash
```

Running the same command again updates the Agent while preserving counters and durable pending state. Use `--reset-state` only when an intentional counter reset is required.

Agent checks:

```bash
systemctl status bwagent.service --no-pager -l
journalctl -u bwagent.service -n 100 --no-pager
bwagent-doctor
```

## Deploy Agents with Ansible

Clone the repository on the Ansible controller:

```bash
git clone https://github.com/tuanchu1121/bw-monitor-production.1.git
cd bw-monitor
cp ansible/inventory.example.ini ansible/inventory.ini
nano ansible/inventory.ini
```

Deploy in bounded batches:

```bash
bash ansible/deploy-agent.sh \
  -i ansible/inventory.ini \
  --api 'https://monitor.example.com/push' \
  --token 'PASTE_THE_MONITOR_PUSH_TOKEN' \
  --forks 20 \
  --serial 10
```

Limit a deployment:

```bash
bash ansible/deploy-agent.sh \
  -i ansible/inventory.ini \
  --api 'https://monitor.example.com/push' \
  --token 'PASTE_THE_MONITOR_PUSH_TOKEN' \
  --limit 'EPYC_SG'
```

Use Ansible Vault or an external secret store for production tokens. Do not commit plaintext tokens to inventory files.

## Update the Monitor

The update path preserves the database, Agent token, Admin users, API keys, Allowed IP rules, domain settings, and current state:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/update.sh \
| sudo bash
```

Create a consistent full database backup during update:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/update.sh \
| sudo bash -s -- --backup-db
```

Check free disk first when the database is large:

```bash
df -h /opt/bw-monitor
ls -lh /opt/bw-monitor/bandwidth.db*
```

## Operations and self-audit

Fast health check:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/doctor.sh \
| sudo bash
```

Deep production audit:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/audit.sh \
| sudo bash
```

Audit including every bundled regression suite:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/audit.sh \
| sudo bash -s -- --full-preflight
```

Read-only SQLite quick check:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/db-check.sh \
| sudo bash -s -- --timeout 120
```

Deep SQLite integrity check during a maintenance window:

```bash
sudo /opt/bw-monitor/db-check.sh --full --timeout 3600
```

The database checker never runs `VACUUM`, never migrates, never deletes rows, and opens the database read-only.

## Backup and restore

Create a consistent SQLite backup plus protected configuration:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/backup.sh \
| sudo bash
```

Backups are stored under:

```text
/var/backups/bw-monitor/YYYYmmdd-HHMMSS/
```

Restore:

```bash
sudo /opt/bw-monitor/restore.sh \
  --from /var/backups/bw-monitor/20260712-010203
```

The restore tool validates the backup with `PRAGMA quick_check`, backs up the current deployment again, stops services only for the final database swap, removes stale WAL/SHM files, and restarts/validates the service.

## Sanitized diagnostics bundle

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/collect-diagnostics.sh \
| sudo bash
```

The generated archive contains service status, recent logs, configuration with secrets redacted, source hashes/markers, Nginx output, disk information, and database metadata/counts. It does not include the database or plaintext secret values. Review the archive before sharing it.

## Uninstall

Safe Monitor uninstall, with an automatic restorable backup:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall.sh \
| sudo bash -s -- --yes
```

Permanent data purge, no uninstall backup:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall.sh \
| sudo bash -s -- --purge-data --yes
```

Remove an Agent and its state:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-agent.sh \
| sudo bash
```

Preserve Agent counter/state files:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-agent.sh \
| sudo bash -s -- --keep-state
```

## Publish this repository to GitHub

This source tree contains no production database or real credentials. To create or update `tuanchu1121/bw-monitor-production.1` from a machine authenticated with GitHub CLI:

```bash
gh auth login
./publish-github.sh \
  --repo tuanchu1121/bw-monitor-production.1 \
  --public \
  --release
```

The publish helper runs local syntax, checksum, YAML and full release preflight checks before committing. It pushes `main`, creates tag `v48.12.9-r4`, and can create/update a GitHub Release with production source archives.

For manual GitHub Web upload, create a repository named `bw-monitor`, then upload **the contents of this directory**, not the outer directory itself. The root of the GitHub repository must contain `install.sh`, `README.md`, `release/`, `deploy/`, and `ansible/`.

## Documentation

- [Publishing to GitHub](docs/PUBLISHING.md)
- [Installation and configuration](docs/INSTALL.md)
- [Domain and HTTPS deployment](docs/DOMAIN.md)
- [Agent deployment](docs/AGENT.md)
- [Ansible deployment](docs/ANSIBLE.md)
- [Operations](docs/OPERATIONS.md)
- [Database design and checks](docs/DATABASE.md)
- [Audit and diagnostics](docs/AUDIT.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Code guide and architecture](docs/CODE_GUIDE.md)
- [REST API overview](docs/API.md)
- [Quick command reference](docs/QUICK_COMMANDS.md)
- [Security policy](SECURITY.md)

## Production notes

- Keep `/etc/default/bw-monitor`, `/root/bw-monitor-credentials.env`, `/etc/bwagent.env`, database files, API secrets, and decrypted Ansible secret files out of Git.
- Use HTTPS domain mode for Internet-facing Monitor installations.
- Do not expose the Gunicorn loopback port when Nginx domain mode is enabled.
- Keep Agent `/push` tokens separate from scoped REST API keys.
- Review disk growth and retention health regularly.
- Do not run `VACUUM` automatically on a large live database. Use the guarded Admin maintenance action during a planned window only.

### Storage I/O extension (48.13.2)
This release keeps the original Dashboard, Top VM, VM Abuse and Node Health UI unchanged. The new **Storage I/O** tab provides per-VM-disk and per-node-storage current metrics with lookback filtering, search, sorting and pagination.


### 48.13.2-prod-r2 disk-only fixes

- Node Filesystems per-mount I/O: Read, Write, Read IOPS, Write IOPS and Util.
- Purging a VM clears all node+UUID live caches and Abuse history, so no 5m/search ghost remains after the purge job completes.
