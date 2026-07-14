# Production Operations

## Service status

```bash
systemctl status bw-monitor.service --no-pager -l
systemctl status bw-monitor-retention.timer --no-pager -l
systemctl list-timers bw-monitor-retention.timer --all
```

## Logs

```bash
journalctl -u bw-monitor.service -n 200 --no-pager
journalctl -fu bw-monitor.service
journalctl -u bw-monitor-retention.service -n 200 --no-pager
```

## Quick doctor

```bash
sudo /opt/bw-monitor/doctor.sh
```

## Deep audit

```bash
sudo /opt/bw-monitor/audit.sh
```

Run every bundled release regression through the repository wrapper:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/audit.sh \
| sudo bash -s -- --full-preflight
```

## Backup

```bash
sudo /opt/bw-monitor/backup.sh
ls -lah /var/backups/bw-monitor
```

## Retention

```bash
systemctl start bw-monitor-retention.service
journalctl -u bw-monitor-retention.service -n 200 --no-pager
```

Retention does not run `VACUUM`. Deleted pages remain reusable by SQLite. Use Admin maintenance compact only during a planned window and only after checking free disk and creating a backup.

## Maintenance recovery

```bash
/opt/bw-monitor/recover_bw_monitor_maintenance_v48_12_9.sh
systemctl restart bw-monitor.service
```

## Configuration

```text
/etc/default/bw-monitor
```

After an intentional configuration edit:

```bash
chmod 600 /etc/default/bw-monitor
systemctl restart bw-monitor.service
sudo /opt/bw-monitor/doctor.sh
```

## Capacity observations

Watch:

```bash
df -h /opt/bw-monitor
ls -lh /opt/bw-monitor/bandwidth.db*
systemctl status bw-monitor.service --no-pager -l
```

Large WAL growth, low disk space, repeated SQLite busy errors, retention failures, or long integrity scans should be investigated before attempting a compact operation.
