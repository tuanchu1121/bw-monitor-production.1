## 48.13.0-prod-r1

- Per-VM-disk libvirt metrics with source, mount, backend, capacity, allocation, throughput and IOPS.
- Node storage current metrics and top contributors page.
- Backward-compatible aggregate disk metrics and Agent v10 payload support.

# Changelog

## 48.12.9-r4-prod-r2

- Fixed fresh domain installation health checks to wait for the actual HTTP endpoint instead of checking immediately after systemd becomes active.
- Credentials are now written before service verification and remain available when a later health check fails.
- A rerun can recover from a missing credentials file by generating a new Admin password and replacing the stored hash safely.
- Updated all default repository URLs to `tuanchu1121/bw-monitor-production`.

## 48.12.9-r4-prod-r1

### Application release

- Current Abuse operations table with compact Top-VM-style metrics.
- Network RX/TX average and PPS peak/window sorting.
- CPU Full/Core display with progress meters.
- Compact Guest RAM used/assigned/RSS display.
- Disk Read/Write and IOPS operations display.
- Color-coded Network, CPU, RAM and Disk Abuse rules in dark/light themes.
- Metric-local active Abuse duration.
- Grouped Abuse Events by VM with occurrence count, exact minutes, Start/End timeline and UUID copy.
- Custom RAM Abuse policy and `cycles-v3-ram` engine.
- Effective parent-node visibility for child VMs.
- Synchronized raw Abuse event/incident cleanup and explicit all-Abuse reset.
- 48-hour raw / 7-day bounded retention without automatic VACUUM.
- Single-worker guarded maintenance and web recovery safety net.

### Production repository

- One-command IP and domain/HTTPS Monitor deployment.
- One-command Monitor update preserving database/configuration.
- One-command Agent install/update and uninstall.
- Bounded-batch Ansible Agent deployment/removal.
- Optional Ansible Monitor deployment.
- Gunicorn systemd service and Nginx/Certbot domain mode.
- Root-only generated credentials and production environment.
- Quick doctor, deep audit, read-only SQLite check, consistent backup, guarded restore and sanitized diagnostics.
- GitHub Actions shell/Python/YAML checks and full release preflight.
- Local release audit, reproducible source archives, checksum manifest and GitHub publish helper.
- Full English installation, operations, database, audit, troubleshooting, API and code architecture documentation.
