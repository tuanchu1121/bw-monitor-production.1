# Operations checklist

Daily/regular checks:

```bash
bw-monitorctl doctor
bw-monitorctl status
systemctl list-timers --all | grep bw-monitor
```

Weekly:

```bash
bw-monitorctl db-check
bw-monitorctl backup
find /var/backups/bw-monitor -maxdepth 1 -type d -printf '%TY-%Tm-%Td %p\n' | sort
```

Before update:

```bash
bw-monitorctl backup
bw-monitorctl update
bw-monitorctl doctor
```

For support bundle:

```bash
bw-monitorctl diagnostics
```

Review the archive before sharing it. The collector redacts environment secret values and does not include a database dump.
