# BW Monitor v49 Enterprise Architecture

BW Monitor v49 adds a scale-out data plane without replacing the proven v48 operational UI or Agent protocol.

## Architecture

```text
KVM/libvirt Agents
        │
        ▼
Flask /push
        │
        ├── SQLite WAL compatibility/control plane
        │     users, API keys, Admin, Abuse state, maintenance, existing UI
        │
        └── atomic local outbox
                │
                ▼
          Redis Streams
                │
                ▼
       bw-enterprise-writer
                │
                ▼
 PostgreSQL 17 + TimescaleDB
        ├── raw hypertables
        ├── current projections
        ├── 5-minute continuous aggregates
        └── 1-hour continuous aggregates
```

The SQLite path remains available when TimescaleDB is down. Every accepted push is written to an atomic spool file before it is queued to Redis. The writer deletes that spool file only after the Timescale transaction commits. Redis is the fast transport, not the only durability layer.

## What moves to TimescaleDB

- VM network samples and PPS/Mbps history
- VM CPU, RAM and aggregate disk history
- Per-virtual-disk capacity, throughput and IOPS
- Node CPU, RAM, swap and aggregate disk history
- Per-mount node storage capacity, throughput, IOPS and utilization
- Physical interface metrics
- Agent health and collector timings
- Current analytical projections for nodes, VMs, disks and storage mounts
- 5-minute and 1-hour continuous aggregates

## What remains in SQLite

- Existing Dashboard, Top VM, VM Abuse, Node Health and Admin compatibility
- Users, sessions, API keys and authorization
- Current Abuse state and operational event workflow
- Maintenance queue and application settings
- The original bounded-retention data used by the current UI

This hybrid split is intentional. It permits an online migration and keeps the existing monitor usable during a PostgreSQL, Docker or Redis incident.

## New installation or complete in-place upgrade

Push the release to the configured GitHub repository, then run:

```bash
unset HISTFILE

curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/install-enterprise.sh \
| bash -s -- \
--public-ip 45.92.158.124
```

The installer:

1. Backs up the existing SQLite database.
2. Installs or updates the v49 web/control plane.
3. Installs Docker and Compose when required.
4. Starts a local TimescaleDB container bound only to `127.0.0.1:55432`.
5. Creates the schema, hypertables, current projections and continuous aggregates.
6. Installs the Redis Stream writer, reconciliation timer and backup timer.
7. Migrates current SQLite state synchronously.
8. Starts historical migration in the background.

Use `--foreground-migration` when the installer must wait for the entire historical backfill.

## Status and logs

```bash
bw-enterprise status
bw-enterprise-doctor

systemctl status \
bw-monitor \
bw-enterprise-writer \
bw-enterprise-migrate \
redis-server \
--no-pager -l

journalctl -fu bw-enterprise-writer.service
journalctl -fu bw-enterprise-migrate.service
```

The web status page is:

```text
http://MONITOR-IP:PORT/enterprise
```

## Migration behavior

The historical migrator uses a checkpoint table in TimescaleDB. It can resume after interruption without starting from row zero. Current-state reconciliation runs daily and updates the current projection tables.

```bash
systemctl status bw-enterprise-migrate.service --no-pager -l
journalctl -u bw-enterprise-migrate.service -n 200 --no-pager
```

Restart a failed migration:

```bash
systemctl restart bw-enterprise-migrate.service
```

Run current-state reconciliation manually:

```bash
systemctl start bw-enterprise-reconcile.service
```

## Exact purge behavior

VM and node purge jobs commit to SQLite first, then enqueue an Enterprise control record through the same atomic outbox. TimescaleDB deletes the matching current and historical VM/node rows and refreshes affected aggregate ranges. Purge tombstones prevent older queued pushes from resurrecting deleted data. A genuinely newer Agent sample can recreate a VM that still exists on the hypervisor.

## Backups

A daily timer backs up both SQLite and TimescaleDB:

```bash
bw-enterprise-backup
systemctl list-timers bw-enterprise-backup.timer
```

Backups are stored under:

```text
/opt/bw-monitor/backups/enterprise/
```

Each backup contains:

- a consistent SQLite copy
- a custom-format PostgreSQL dump
- Monitor and Enterprise environment files
- the root-only credential file when present
- SHA256 checksums

Restore:

```bash
/opt/bw-monitor/enterprise/bw-enterprise-restore.sh \
/opt/bw-monitor/backups/enterprise/YYYYMMDD-HHMMSS
```

## Enterprise APIs

Authenticated endpoints:

```text
/api/v1/enterprise/health
/api/v1/enterprise/top-disks
/api/v1/enterprise/storage
/api/v1/enterprise/vm/<uuid>/disks
/api/v1/enterprise/history/vm/<uuid>?period=24h
/api/v1/enterprise/history/disks/<uuid>?period=7d
/api/v1/enterprise/history/storage?node=NODE&mount=/home&period=30d
```

History periods: `1h`, `6h`, `24h`, `2d`, `7d`, `30d`, `90d`, `180d`.

Periods up to two days use 5-minute aggregates. Longer periods use 1-hour aggregates.

## Data retention

Default v49 Enterprise retention:

- raw accepted push envelopes: 14 days, redacted by default
- raw time-series hypertables: 30 days
- 5-minute and 1-hour continuous aggregates: retained for long-range analytics
- SQLite compatibility retention: unchanged from the existing monitor

Set `BW_ENTERPRISE_STORE_RAW_PUSH='1'` only when full raw payload retention is operationally necessary. The default stores a redacted summary to avoid duplicating every UUID and disk object in raw JSON.

## Resource sizing

For a local all-in-one Monitor, use NVMe storage. The installer sizes PostgreSQL memory conservatively from host RAM and keeps TimescaleDB local-only. For very large fleets, move TimescaleDB to a dedicated host and keep the Monitor/Redis/web tier separate in a later deployment phase.

The installer does not promise a fixed latency. Actual performance depends on VM count, disk count, sample cadence, historical depth, storage latency and concurrent users.

## Update

After the first Enterprise installation:

```bash
unset HISTFILE

curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/update-enterprise.sh \
| bash
```

## Uninstall only the Enterprise layer

Keep the legacy-compatible web app and SQLite data:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-enterprise.sh \
| bash
```

Remove the Timescale Docker volume and Enterprise spool too:

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/uninstall-enterprise.sh \
| bash -s -- \
--purge-data \
--yes
```
