# Changelog

## 50.0.0-prod-r1-postgres-native

- Preserved the complete production UI, Agent protocol, Abuse Engine, storage/disk views, Admin workflow and scoped REST API.
- Replaced the runtime database with PostgreSQL 17 + TimescaleDB as the single source of truth.
- Added psycopg 3 connection pooling and an isolated compatibility/data-access layer so the mature application behavior remains intact without a second database.
- Kept exact Agent behavior: 15-second local sampling and one durable 300-second push.
- Kept exact retention: every real 5-minute push for 48 hours, one synchronized real snapshot/hour through 7 days, then bounded deletion.
- Added Timescale hypertables for supported history tables, integer-time partitioning, compact BRIN indexes and current-state sort indexes.
- Made Redis an optional page cache only, disabled by default and never authoritative.
- Added GitHub one-command fresh installation by public IP or domain with Nginx and Let's Encrypt.
- Added PostgreSQL backup/restore, doctor, audit, DB check, diagnostics, retention/backup timers and `bw-monitorctl`.
- Added full Agent/Monitor Ansible playbooks. Root SSH nodes no longer require sudo.
- Added static product contracts, live PostgreSQL application integration tests, CI and release archive tooling.
- Fresh-install release. Legacy database data is intentionally not imported.

## Lineage

v50 is built from the complete v48.12.9-r4 through v48.14/v49 UI and Agent feature lineage. The v50 runtime deliberately removes the transitional multi-store architecture and ships one PostgreSQL/TimescaleDB data plane.
