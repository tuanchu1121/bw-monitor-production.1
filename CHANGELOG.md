# Changelog

## 48.13.6-prod-r1-storage-grouped

- Fixed Top VM `ALLOC`, `ASSIGNED`, and `%` sorting by allowing the new disk sort keys through the final request sanitizer.
- Changed VM Disks All view to one row per VM UUID with `vda`, `vdb`, `vdc`, and all customer disks nested inside; selecting a storage mount keeps the forensic one-disk-per-row view.
- Changed Storage Node All view to one row per node with every real filesystem nested inside; selecting a mount keeps the detailed per-filesystem view.
- Changed Agent systemd hardening from `ProtectHome=true` to `ProtectHome=read-only` so a separate LVM/RAID `/home` is visible to the collector without granting write access.
- Preserved the original Dashboard, Abuse, Node Health, Admin, CPU, RAM, network, charts, exact UUID purge, and per-disk VM detail behavior.

## 48.13.5-prod-r2-vm-disk-panels

- Removed the repeated `TOTAL HOST ALLOCATED / ASSIGNED` strip from VM Detail → Virtual Disk I/O.
- Kept the compact total VM Disk capacity meter in Overview.
- Virtual Disk I/O now shows only clean, separate `vda`, `vdb`, and other customer-disk panels, each with Allocated / Assigned, percentage bar, Read, Write, Read IOPS, Write IOPS, source, filesystem, physical size, and last sample.
- Kept Top VM total disk capacity between RAM and Disk R/s with independent `ALLOC`, `ASSIGNED`, and `%` sorting.

## 48.13.5-prod-r1-storage-root-bars

- Fixed the maintenance-import migration bug that cleared every VM's Current Abuse when one UUID purge job started. Purging one UUID now removes only that UUID while unrelated Current Abuse and Abuse Events remain visible immediately.
- Purge-by-UUID removes all copies of that UUID from VM-scoped current caches, 5-minute/history tables, inventory, disk current data and Abuse history without deleting node storage metrics.
- Fixed separate `/home`, `/home2`, `/home3`, LVM, device-mapper and mdraid discovery by recursively parsing `findmnt` and resolving block counters through `MAJ:MIN`.
- Fixed Node Filesystems so current Read, Write, Read IOPS, Write IOPS and Util are overlaid onto every retained mount row instead of only `/`.
- Kept Top VM one-row-per-VM and added a compact sortable total Host Allocated / Assigned meter between RAM and Disk R/s with tighter, aligned column widths.
- Added per-disk capacity cards to VM Overview and separate per-disk I/O panels between Overview and charts.
- Changed Storage I/O VM Disks to one real customer disk per row with search, node IP, UUID copy, capacity meter, I/O and IOPS sorting. Renamed Storage Backends to Storage Node.
- Added Active, Hidden and Stale filters to Admin node and VM inventory.

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
