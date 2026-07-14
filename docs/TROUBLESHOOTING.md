# Troubleshooting

## Monitor does not start

```bash
systemctl status bw-monitor.service --no-pager -l
journalctl -u bw-monitor.service -n 300 --no-pager
/opt/bw-monitor/venv/bin/python3 -m py_compile /opt/bw-monitor/app.py
sudo /opt/bw-monitor/doctor.sh
```

A Python compile error must be fixed before restarting repeatedly. The production systemd unit also compile-checks `app.py` before Gunicorn starts.

## Local page fails

```bash
source /etc/default/bw-monitor
ss -lntp | grep -E 'gunicorn|:8080'
curl -v http://127.0.0.1:8080/login
```

In domain mode, Gunicorn should normally listen on loopback only.

## Domain/HTTPS fails

```bash
getent ahosts monitor.example.com
nginx -t
systemctl status nginx --no-pager -l
certbot certificates
curl -Iv https://monitor.example.com/login
```

Verify DNS, firewall rules, certificate state and Nginx configuration in that order.

## Agent is not pushing

```bash
bwagent-doctor
journalctl -u bwagent.service -n 200 --no-pager
grep -E '^(BW_AGENT_API|BW_AGENT_SAMPLE_SECONDS|BW_AGENT_PUSH_SECONDS)=' /etc/bwagent.env
curl -I https://monitor.example.com/login
```

Do not print `BW_AGENT_TOKEN` into public logs.

## SQLite busy/locked errors

```bash
pgrep -af '/opt/bw-monitor/bw_monitor_maintenance.py'
systemctl list-units --all 'bw-monitor-maintenance@*.service'
ls -lh /opt/bw-monitor/bandwidth.db*
sudo /opt/bw-monitor/db-check.sh --no-integrity
```

Only one maintenance worker should run. Use the bundled recovery script when a stale maintenance unit or queue row remains.

## Database quick check times out

```bash
sudo /opt/bw-monitor/db-check.sh --timeout 600
```

A timeout is not the same as a failed integrity result. Check disk I/O, database size, active workload and maintenance state. Run a full integrity check only during a suitable window.

## Abuse History was cleared but Current Abuse remains

`Current Abuse`, raw Abuse events, and grouped Abuse incidents are separate data groups. Clearing history intentionally does not mark an actively abusive VM as healthy. Use the explicit Admin reset action only when the current state/streak must also be reset. A VM still above policy thresholds can reappear after the sustained window.

## Create a support bundle

```bash
sudo /opt/bw-monitor/collect-diagnostics.sh
```

## Installer stopped at local HTTP health check

Production deployment revision `48.12.9-r4-prod-r2` waits for the actual `/login` endpoint and writes credentials before the wait begins. A temporary `HTTP 000` during the first few attempts is normal while Gunicorn starts.

Check credentials immediately:

```bash
sudo cat /root/bw-monitor-credentials.env
```

Then inspect readiness:

```bash
systemctl status bw-monitor.service --no-pager -l
journalctl -u bw-monitor.service -n 250 --no-pager
curl -I http://127.0.0.1:8080/login
```

For an installation interrupted by the older `prod-r1` health-check bug, update the repository and rerun the same normal install command. The installer detects a missing credential file, generates a new Admin password, updates the stored password hash, and completes without a manual password-recovery block.
