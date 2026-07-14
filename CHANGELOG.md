# Changelog

## 48.13.3-prod-r1-storage-integrated

- Fixed exact UUID purge so deleting one VM removes only that VM from Current Abuse, Abuse Events, Top VM, Dashboard, retained 5-minute/history data and disk current data. Unrelated VMs remain visible immediately.
- Added a compact total disk-capacity meter to Top VM between RAM and Disk R/s. It shows Host Allocated / Assigned across all customer disks and supports Allocated, Assigned, Allocated %, and Disk Count sorting.
- Added per-disk capacity cards inside VM Overview and a Virtual Disk I/O section between Overview and charts with source, storage, Read/Write, IOPS and current capacity.
- Reworked Storage I/O with a large search field, node/IP display, copy controls, one grouped row per UUID, and a renamed Storage Node view.
- Improved filesystem discovery with real `findmnt` data so separate large `/home`, `/home2`, LVM, device-mapper and hardware-RAID-backed mounts remain distinct from the OS `/` filesystem.
- Preserved the original v48.12.9-r4 Dashboard, VM Abuse, Node Health, Admin, CPU, RAM, network and chart behavior outside the requested disk integration.

## 48.13.2-prod-r2-disk-only

- Added per-mount Read/Write, Read/Write IOPS and Util to the existing Node Filesystems table.
- Fixed VM purge so live 5m caches, Current Abuse, raw Abuse events and grouped Abuse Events are removed by node + UUID.
- Kept all original v48.12.9-r4 Dashboard, Top VM, VM Abuse, Node Health and Admin renderers unchanged.


## 48.12.9-r4-prod-r2

- Fixed fresh domain installation health checks to wait for the actual HTTP endpoint instead of checking immediately after systemd becomes active.
- Credentials are now written before service verification and remain available when a later health check fails.
- A rerun can recover from a missing credentials file by generating a new Admin password and replacing the stored hash safely.
- Updated all default repository URLs to `tuanchu1121/bw-monitor-production.1`.

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

## 48.13.2-prod-r1-disk-only
- Restored the untouched 48.12.9-r4 UI/logic as the base.
- Added only the Storage I/O tab and per-disk/current-storage collector.
- Added compact allocated/assigned meter, search, lookback, sorting and pagination inside Storage I/O.
