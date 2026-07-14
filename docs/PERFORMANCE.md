# Performance architecture

BW Monitor 48.14.0 keeps SQLite as the durable source of truth for compatibility, and adds a shared hot path for large current datasets.

## Read path

1. Repeated authenticated HTML pages are served from Redis for a short TTL.
2. If Redis is unavailable, each Gunicorn worker uses a bounded local LRU cache.
3. Cache misses query materialized current summaries instead of re-running per-disk `SUM/GROUP BY` work.
4. Storage I/O uses SQL pagination and loads child disks/filesystems only for the visible page.
5. HTML/JSON responses are gzip-compressed and off-screen cards use browser `content-visibility`.

Redis never stores the authoritative monitoring state. Clearing or restarting Redis only causes temporary cache misses.

## Write path

Agent push ingestion remains transactionally durable in SQLite WAL. The per-node push updates:

- `vm_disk_current`
- `node_storage_current`
- `vm_disk_summary_current`
- `node_storage_mount_summary_current`

The summary update is bounded to the node that pushed. Schema DDL is performed once during process startup, not on every request or push.

## Default tuning

The installer sizes SQLite cache and mmap settings from system RAM:

| Monitor RAM | SQLite page cache | SQLite mmap | Local fallback items |
|---|---:|---:|---:|
| under 8 GiB | 128 MiB | 512 MiB | 256 |
| 8–15 GiB | 256 MiB | 1 GiB | 512 |
| 16–31 GiB | 512 MiB | 2 GiB | 1,024 |
| 32 GiB+ | 1 GiB | 4 GiB | 2,048 |

Existing custom values in `/etc/default/bw-monitor` are preserved on update.

## Important environment values

```text
BW_REDIS_ENABLED=1
BW_REDIS_URL=redis://127.0.0.1:6379/0
BW_PAGE_CACHE_ENABLED=1
BW_PAGE_CACHE_TTL=6
BW_LOCAL_CACHE_ITEMS=512
BW_SQLITE_CACHE_MIB=256
BW_SQLITE_MMAP_MIB=1024
BW_SQLITE_WAL_AUTOCHECKPOINT=4000
BW_SQLITE_JOURNAL_LIMIT_MIB=256
BW_GUNICORN_PRELOAD=1
BW_GUNICORN_WORKERS=4
BW_GUNICORN_THREADS=4
```

Restart `bw-monitor.service` after changing these values.

## Operations checks

```bash
redis-cli ping
systemctl status bw-monitor redis-server --no-pager -l
/opt/bw-monitor/doctor.sh
```

After logging in, open `/api/v1/performance` to see cache status, SQLite tuning and summary row counts.

The application also returns:

```text
Server-Timing: app;dur=...
X-BW-App-Time-Ms: ...
X-BW-Performance: 48.14.0
X-BW-Cache: HIT|MISS
```

`X-BW-Cache` is present on cached page routes.

## Benchmark

```bash
python3 tools/benchmark-performance.py \
  --vms 50000 \
  --disks-per-vm 2 \
  --nodes 250 \
  --queries 250 \
  --page-size 30
```

This is a local SQL microbenchmark. It measures summary construction and indexed top-N reads, not network, Flask template, browser or storage-device latency.

## Scaling boundary

The 48.14.0 architecture is the fastest low-risk path that preserves the existing app and database. For installations that need substantially more than roughly 100,000 active VMs, months of raw metric history, or many simultaneous API/dashboard readers, the next architectural step should be PostgreSQL/TimescaleDB for durable time-series history while keeping Redis for hot current state. That is a database migration project, not a drop-in performance patch.
