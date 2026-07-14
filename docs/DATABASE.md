# Database Design and Health Checks

BW Monitor uses SQLite in WAL mode. The application keeps current state and bounded historical data in the same database.

## Important data groups

Current/inventory data:

```text
node_inventory
vm_inventory
current/cache tables
vm_abuse_state
users/settings
api_keys
```

Historical data:

```text
node_stats
vm_perf
bandwidth history tables
vm_abuse_events
vm_abuse_incidents
api_access_logs
api_management_events
node/account logs
maintenance history
retention history
```

## Retention

```text
0 → 48 hours      every real push is retained
48 hours → 7 days one real hourly snapshot is retained
> 7 days           historical rows are deleted
```

The retention worker uses a fail-fast lock, bounded batches, and does not stop the web service or run `VACUUM`.

## Read-only database check

```bash
sudo /opt/bw-monitor/db-check.sh --timeout 120
```

The report includes:

- database, WAL and SHM sizes;
- SQLite version and journal mode;
- page size, page count and freelist count;
- estimated reusable free bytes;
- schema table/index counts;
- row counts for important tables;
- `PRAGMA quick_check` result;
- elapsed time and timeout status.

The checker opens SQLite with `mode=ro`, enables `query_only`, and never writes application data.

## Full integrity check

Run during a maintenance window on large databases:

```bash
sudo /opt/bw-monitor/db-check.sh \
  --full \
  --timeout 3600
```

Exit codes:

```text
0    check passed
2    file/open/query error
3    integrity result was not ok
124  scan exceeded the configured timeout
```

A timeout does not by itself prove corruption. It means the scan did not finish in the allotted time.

## Consistent backup

```bash
sudo /opt/bw-monitor/backup.sh
```

The script uses the SQLite backup API, so the live database does not need to be copied together with WAL/SHM files manually.

## Do not do this on a live large DB

Do not delete `-wal` or `-shm` while the service is running. Do not copy only `bandwidth.db` with `cp` as a normal backup while writes are active. Do not run automatic `VACUUM` on every retention cycle. Do not infer corruption from a blank `sqlite3 PRAGMA quick_check` command without checking its exit code and timeout.
