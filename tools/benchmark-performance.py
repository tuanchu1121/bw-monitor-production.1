#!/usr/bin/env python3
"""Synthetic microbenchmark for the v48.14.0 current-summary query path.

This measures local SQLite summary build and indexed top-N queries. It is not an
end-to-end browser benchmark and does not predict production latency.
"""
from __future__ import annotations

import argparse
import os
import random
import sqlite3
import statistics
import tempfile
import time
from pathlib import Path


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    pos = (len(values) - 1) * p
    lo = int(pos)
    hi = min(lo + 1, len(values) - 1)
    frac = pos - lo
    return values[lo] * (1 - frac) + values[hi] * frac


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vms", type=int, default=50_000)
    ap.add_argument("--disks-per-vm", type=int, default=2)
    ap.add_argument("--nodes", type=int, default=250)
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--page-size", type=int, default=30)
    ap.add_argument("--keep-db", action="store_true")
    args = ap.parse_args()

    if min(args.vms, args.disks_per_vm, args.nodes, args.queries, args.page_size) <= 0:
        ap.error("all numeric arguments must be positive")

    fd, name = tempfile.mkstemp(prefix="bw-monitor-v48140-bench-", suffix=".db")
    os.close(fd)
    path = Path(name)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-262144")
    conn.executescript("""
    CREATE TABLE vm_disk_current(
      node TEXT NOT NULL, vm_uuid TEXT NOT NULL, target TEXT NOT NULL,
      role TEXT NOT NULL, mount TEXT NOT NULL,
      allocation_bytes INTEGER NOT NULL, capacity_bytes INTEGER NOT NULL,
      physical_bytes INTEGER NOT NULL, read_bps REAL NOT NULL,
      write_bps REAL NOT NULL, read_iops REAL NOT NULL,
      write_iops REAL NOT NULL, last_seen INTEGER NOT NULL
    );
    CREATE TABLE vm_disk_summary_current(
      node TEXT NOT NULL, vm_uuid TEXT NOT NULL, disk_count INTEGER NOT NULL,
      allocated_bytes INTEGER NOT NULL, assigned_bytes INTEGER NOT NULL,
      physical_bytes INTEGER NOT NULL, allocation_ratio REAL NOT NULL,
      read_bps REAL NOT NULL, write_bps REAL NOT NULL,
      read_iops REAL NOT NULL, write_iops REAL NOT NULL,
      last_seen INTEGER NOT NULL, PRIMARY KEY(node,vm_uuid)
    ) WITHOUT ROWID;
    CREATE INDEX idx_bench_wiops ON vm_disk_summary_current(write_iops DESC,node,vm_uuid);
    CREATE INDEX idx_bench_write ON vm_disk_summary_current(write_bps DESC,node,vm_uuid);
    CREATE INDEX idx_bench_alloc ON vm_disk_summary_current(allocated_bytes DESC,node,vm_uuid);
    CREATE INDEX idx_bench_ratio ON vm_disk_summary_current(allocation_ratio DESC,node,vm_uuid);
    CREATE INDEX idx_bench_slots ON vm_disk_summary_current(disk_count DESC,node,vm_uuid);
    """)

    rng = random.Random(48140)
    now = int(time.time())
    batch: list[tuple[object, ...]] = []
    insert_started = time.perf_counter()
    for i in range(args.vms):
        node = f"node-{i % args.nodes:04d}"
        vm_uuid = f"00000000-0000-4000-8000-{i:012d}"
        for d in range(args.disks_per_vm):
            capacity = (40 + ((i + d * 31) % 2000)) * 1024**3
            ratio = 0.05 + rng.random() * 0.94
            allocation = int(capacity * ratio)
            read_bps = rng.random() * 600 * 1024**2
            write_bps = rng.random() * 350 * 1024**2
            read_iops = rng.random() * 4000
            write_iops = rng.random() * 6000
            batch.append((
                node, vm_uuid, f"vd{chr(97+d)}", "customer",
                "/home" if d == 0 else f"/home{d+1}",
                allocation, capacity, allocation, read_bps, write_bps,
                read_iops, write_iops, now,
            ))
            if len(batch) >= 10_000:
                conn.executemany("INSERT INTO vm_disk_current VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
                batch.clear()
    if batch:
        conn.executemany("INSERT INTO vm_disk_current VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", batch)
    conn.commit()
    insert_seconds = time.perf_counter() - insert_started

    build_started = time.perf_counter()
    conn.execute("""
      INSERT INTO vm_disk_summary_current
      SELECT node,vm_uuid,COUNT(*),SUM(allocation_bytes),SUM(capacity_bytes),
             SUM(physical_bytes),
             CASE WHEN SUM(capacity_bytes)>0 THEN SUM(allocation_bytes)*1.0/SUM(capacity_bytes) ELSE 0 END,
             SUM(read_bps),SUM(write_bps),SUM(read_iops),SUM(write_iops),MAX(last_seen)
        FROM vm_disk_current
       WHERE role='customer'
       GROUP BY node,vm_uuid
    """)
    conn.commit()
    build_seconds = time.perf_counter() - build_started

    query_sql = {
        "write_iops": "SELECT node,vm_uuid,write_iops FROM vm_disk_summary_current ORDER BY write_iops DESC,node,vm_uuid LIMIT ?",
        "write_bps": "SELECT node,vm_uuid,write_bps FROM vm_disk_summary_current ORDER BY write_bps DESC,node,vm_uuid LIMIT ?",
        "allocated": "SELECT node,vm_uuid,allocated_bytes FROM vm_disk_summary_current ORDER BY allocated_bytes DESC,node,vm_uuid LIMIT ?",
        "ratio": "SELECT node,vm_uuid,allocation_ratio FROM vm_disk_summary_current ORDER BY allocation_ratio DESC,node,vm_uuid LIMIT ?",
        "slots": "SELECT node,vm_uuid,disk_count FROM vm_disk_summary_current ORDER BY disk_count DESC,node,vm_uuid LIMIT ?",
    }
    timings: dict[str, list[float]] = {key: [] for key in query_sql}
    # Warm the page cache and prepared statements.
    for sql in query_sql.values():
        conn.execute(sql, (args.page_size,)).fetchall()
    keys = list(query_sql)
    for i in range(args.queries):
        key = keys[i % len(keys)]
        started = time.perf_counter()
        conn.execute(query_sql[key], (args.page_size,)).fetchall()
        timings[key].append((time.perf_counter() - started) * 1000)

    db_mib = path.stat().st_size / 1024**2
    wal = Path(str(path) + "-wal")
    wal_mib = wal.stat().st_size / 1024**2 if wal.exists() else 0.0
    print("BW Monitor v48.14.0 synthetic current-summary benchmark")
    print("=" * 65)
    print(f"VMs: {args.vms:,} | disks: {args.vms * args.disks_per_vm:,} | nodes: {args.nodes:,}")
    print(f"Raw insert: {insert_seconds:.3f}s | summary build: {build_seconds:.3f}s")
    print(f"SQLite file: {db_mib:.1f} MiB | WAL: {wal_mib:.1f} MiB")
    print(f"Indexed top-{args.page_size} query latency ({args.queries:,} total queries):")
    for key in keys:
        vals = timings[key]
        print(
            f"  {key:11s} avg={statistics.fmean(vals):7.3f} ms "
            f"p50={percentile(vals, 0.50):7.3f} ms "
            f"p95={percentile(vals, 0.95):7.3f} ms "
            f"max={max(vals):7.3f} ms"
        )
    print("\nNote: this is a local SQL microbenchmark, not end-to-end page latency.")
    conn.close()
    if args.keep_db:
        print(f"Database kept at: {path}")
    else:
        for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
