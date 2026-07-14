# Installation and Configuration

## Supported deployment model

BW Monitor is installed directly on a Debian or Ubuntu server with systemd. The production wrapper installs Python, creates `/opt/bw-monitor/venv`, installs pinned dependencies, writes a root-only environment, runs the exact v48.12.9-r4 release preflight, installs systemd units, and validates the local endpoint.

## Fresh IP installation

```bash
sudo apt-get update \
&& sudo apt-get install -y curl ca-certificates \
&& curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo bash -s -- \
  --public-ip 203.0.113.10 \
  --port 8080 \
  --run-retention-now
```

Optional non-interactive secrets:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo env \
  BW_ADMIN_PASSWORD='USE_A_LONG_UNIQUE_PASSWORD' \
  BW_MONITOR_TOKEN='USE_A_LONG_RANDOM_AGENT_TOKEN' \
  bash -s -- \
    --public-ip 203.0.113.10 \
    --port 8080
```

## Fresh domain installation

```bash
sudo apt-get update \
&& sudo apt-get install -y curl ca-certificates \
&& curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo bash -s -- \
  --domain monitor.example.com \
  --email ops@example.com
```


## Installer readiness and credential guarantees

The installer writes `/etc/default/bw-monitor` and `/root/bw-monitor-credentials.env` before it starts final service verification. It then waits for the real local `/login` endpoint, rather than treating the systemd `active` state as proof that Gunicorn is ready. The local readiness loop retries for up to approximately two minutes.

If an earlier interrupted installation created an Admin password hash but failed before writing the plaintext credential file, rerunning the normal installation command generates a new Admin password, replaces the hash, and writes a complete root-only credential file automatically.

## Installer options

```text
--domain NAME
--email ADDRESS
--public-ip ADDRESS
--port NUMBER
--admin-user NAME
--admin-password VALUE
--monitor-token VALUE
--timezone NAME
--workers NUMBER
--threads NUMBER
--no-tls
--no-nginx
--firewall
--ssh-port NUMBER
--backup-db
--recover-stuck
--run-retention-now
--update
--skip-preflight
```

`--skip-preflight` is intended only for controlled debugging. Production installation should run the bundled release preflight.

## Installed paths

```text
/opt/bw-monitor/app.py
/opt/bw-monitor/bandwidth.db
/opt/bw-monitor/venv/
/opt/bw-monitor/start-monitor.sh
/opt/bw-monitor/doctor.sh
/opt/bw-monitor/audit.sh
/opt/bw-monitor/db-check.sh
/opt/bw-monitor/backup.sh
/opt/bw-monitor/restore.sh
/opt/bw-monitor/collect-diagnostics.sh
/etc/default/bw-monitor
/root/bw-monitor-credentials.env
/etc/systemd/system/bw-monitor.service
/etc/systemd/system/bw-monitor-maintenance@.service
/etc/systemd/system/bw-monitor-retention.service
/etc/systemd/system/bw-monitor-retention.timer
```

Domain mode additionally installs an Nginx site and a Certbot-managed certificate.

## Environment safety

`/etc/default/bw-monitor` and `/root/bw-monitor-credentials.env` are installed as `root:root` mode `0600`. Do not paste these files into public tickets. The diagnostics collector redacts known secret fields.

## Update behavior

`update.sh` invokes the same production installer with `--update --recover-stuck`. It preserves the existing environment and database and updates application/systemd helper files. Add `--backup-db` when sufficient disk space exists and a full pre-update SQLite backup is required.

## Post-install validation

```bash
systemctl status bw-monitor.service --no-pager -l
systemctl status bw-monitor-retention.timer --no-pager -l
curl -I http://127.0.0.1:8080/login
sudo /opt/bw-monitor/doctor.sh
sudo /opt/bw-monitor/db-check.sh --timeout 120
```
