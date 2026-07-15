# Troubleshooting

Start with:

```bash
bw-monitorctl doctor
bw-monitorctl status
bw-monitorctl logs all 300
bw-monitorctl db-check
```

## Web not opening

```bash
systemctl status bw-monitor --no-pager -l
journalctl -u bw-monitor -n 300 --no-pager
curl -fsS http://127.0.0.1:8080/livez
curl -fsS http://127.0.0.1:8080/healthz
systemctl status bw-monitor-health-watch.timer --no-pager -l
journalctl -t bw-monitor-health-watch -n 100 --no-pager
```

In domain mode:

```bash
nginx -t
systemctl status nginx --no-pager -l
curl -I https://monitor.example.com/login
```

## PostgreSQL container not healthy

```bash
docker ps -a --filter name=bw-timescaledb
docker logs --tail 300 bw-timescaledb
cat /etc/default/bw-monitor-postgres
```

Do not paste real passwords/tokens into public tickets.

## Agent does not appear

```bash
systemctl status bwagent --no-pager -l
journalctl -u bwagent -n 300 --no-pager
cat /etc/bwagent.env
```

Confirm endpoint, token, DNS/TLS and outbound connectivity. A new Agent normally appears after its next 300-second push.

## Ansible says sudo not found

Set `ansible_user=root`. The bundled playbook automatically disables privilege escalation for root. Non-root users need sudo.

## `/home` missing from storage

```bash
systemctl show bwagent -p ProtectHome
```

Expected:

```text
ProtectHome=read-only
```

Redeploy the Agent if it still says `true`.

## Backup/restore problem

```bash
find /var/backups/bw-monitor -maxdepth 2 -name SHA256SUMS -print
bw-monitorctl logs postgres 300
```

The restore command creates a pre-restore dump before replacing the database.


## Intermittent 502 Bad Gateway

A 502 means Nginx could not reach a healthy Gunicorn listener at that instant. Check both layers instead of assuming PostgreSQL is corrupt:

```bash
bw-monitorctl health
systemctl status nginx bw-monitor --no-pager -l
journalctl -u nginx -u bw-monitor --since "15 minutes ago" --no-pager
journalctl -t bw-monitor-health-watch --since "15 minutes ago" --no-pager
```

v50.1 includes a local liveness watchdog, unlimited systemd restart attempts, shorter restart delay, Gunicorn worker heartbeat temp files in `/dev/shm`, and hardened Nginx upstream timeouts. `/livez` deliberately does not query PostgreSQL; `/healthz` does.

## Hidden Node or VM still appears

After v50.1, Hide/Restore increments a PostgreSQL-backed cache generation shared by all workers. Dashboard search and Storage queries also join the visibility inventory directly. Check the inventory state:

```sql
SELECT node,status,deleted_at FROM node_inventory WHERE node='NODE';
SELECT node,vm_uuid,status,deleted_at FROM vm_inventory WHERE vm_uuid='UUID';
```

Then bypass page cache once while diagnosing:

```text
/?_nocache=1
/storage?_nocache=1
```
