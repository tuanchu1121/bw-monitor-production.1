# Changelog

## 50.1.1-prod-r1-stability-fix

- Make display timezone a presentation-only setting; it no longer changes retention or storage bucket boundaries.
- Preserve custom snapshot instants as Unix epochs across UTC/Asia/Ho_Chi_Minh switches.
- Add an authoritative Current VMs on Node table sourced from the latest VM inventory/current metrics, independent of br0/br1 interface collection.
- Keep hidden/deleted VMs out of the new Node VM inventory.

## 50.1.0-prod-r1-production-hardening

- Added `/livez` and `/healthz`, a 30-second local liveness watchdog, faster systemd recovery, Gunicorn worker temp files in `/dev/shm`, and hardened Nginx upstream handling to reduce intermittent Bad Gateway windows.
- Reworked Current Abuse into a fluid full-width table with compact columns and responsive card rows on narrower screens.
- Corrected PostgreSQL size labels: the headline now shows actual database data size; physical WAL files are shown separately as reserved/recycled PostgreSQL storage, and the obsolete SQLite SHM label is removed.
- Automatically archives leftover `bandwidth.db`, `bandwidth.db-wal` and `bandwidth.db-shm` files during install/update. They are never used by the PostgreSQL-native runtime.
- Hidden VMs can no longer revive a Node through Dashboard search aliases; hidden Nodes/VMs are excluded consistently from Storage results and filter dropdowns.
- Persisted page-cache generations in PostgreSQL so Hide/Restore invalidates every Gunicorn worker immediately even without Redis.
- Added shared display timezone selection for `Asia/Ho_Chi_Minh (UTC+7)` and `UTC (UTC+0)` in Admin and through `bw-monitorctl timezone`.
- Kept all timestamps stored as Unix/UTC values; the timezone setting changes display and retained hourly bucket alignment only.

## 50.0.4-prod-r1-one-command

- Fix PostgreSQL `GroupingError` on the Node Health dashboard caused by grouping the computed physical-network role by the conflicting input column name.
- Group the normalized physical-network role by output position (`GROUP BY np.node, 2`), which is valid on PostgreSQL and remains compatible with the legacy query shape.
- Add a regression contract so the incompatible `GROUP BY np.node, role` form cannot return.
- Stage installs from the canonical `SHA256SUMS` manifest, so stale v48/v49 files left by Windows Explorer or GitHub Desktop are ignored.
- Verify every canonical source file before installing.
- Keep the release preflight strict while making the one-command bootstrap resilient to dirty merged repositories.
- Preserve support for non-executable `.sh` files published from Windows.

## 50.0.1-prod-r1-one-command

- Fixed one-command GitHub installation when a release is published from Windows GitHub Desktop and shell files do not retain the Linux executable bit.
- Replaced executable-mode completeness checks with explicit required-file validation.
- Normalized shell modes after GitHub tarball extraction while invoking all source scripts explicitly through `bash`.
- Hardened preflight, release audit, wrappers, management helpers and GitHub Actions against file-mode differences.
- Added a release test that simulates every `.sh` file being published as mode `0644`.

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
