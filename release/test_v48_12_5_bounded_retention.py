#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time


def load_module(app_path: str, db_path: str):
    os.environ["BW_MONITOR_DB"] = db_path
    os.environ["BW_MONITOR_TOKEN"] = "v48125-test-token"
    # Stale legacy values must be clamped by the release.
    os.environ["BW_RAW_RETENTION_DAYS"] = "7"
    os.environ["BW_HOURLY_RETENTION_DAYS"] = "30"
    os.environ["BW_API_ACCESS_LOG_RETENTION_DAYS"] = "30"
    spec = importlib.util.spec_from_file_location("bw_monitor_v48125_test", app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load app")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def insert_node_stat(conn, bucket: int, suffix: str):
    conn.execute("""
        INSERT INTO node_stats(
            bucket,node,bridge,iface,vm_uuid,interval_seconds,last_push
        ) VALUES(?,?,?,?,?,?,?)
    """, (bucket, "NODE-A", "br0", f"tap-{suffix}", f"vm-{suffix}", 300, bucket))
    conn.execute("""
        INSERT INTO node_push_snapshots(
            node,bucket,push_time,last_push,vm_count,iface_count,inventory_complete,retention_tier
        ) VALUES(?,?,?,?,1,1,1,'raw')
    """, ("NODE-A", bucket, bucket, bucket))


def insert_event_rows(conn, now: int):
    old = now - 8 * 86400
    new = now - 3600
    conn.execute("INSERT INTO node_logs(time,event,node) VALUES(?,?,?)", (old,"old","NODE-A"))
    conn.execute("INSERT INTO node_logs(time,event,node) VALUES(?,?,?)", (new,"new","NODE-A"))
    conn.execute("INSERT INTO account_logs(time,realm,event) VALUES(?,?,?)", (old,"admin","old"))
    conn.execute("INSERT INTO account_logs(time,realm,event) VALUES(?,?,?)", (new,"admin","new"))
    conn.execute("INSERT INTO api_access_logs(request_time,request_id) VALUES(?,?)", (old,"old"))
    conn.execute("INSERT INTO api_access_logs(request_time,request_id) VALUES(?,?)", (new,"new"))
    conn.execute("INSERT INTO api_key_events(event_time,event_type) VALUES(?,?)", (old,"OLD"))
    conn.execute("INSERT INTO api_key_events(event_time,event_type) VALUES(?,?)", (new,"NEW"))
    conn.execute("""INSERT INTO node_missed_events(
        node,last_good_push,missed_from,recovered_at,created_at
    ) VALUES(?,?,?,?,?)""", ("NODE-A",old-600,old-300,old,old))
    conn.execute("""INSERT INTO node_missed_events(
        node,last_good_push,missed_from,recovered_at,created_at
    ) VALUES(?,?,?,?,?)""", ("NODE-A",new-600,new-300,new,new))
    conn.execute("""INSERT INTO vm_migration_events(
        time,vm_uuid,old_node,new_node,new_seen
    ) VALUES(?,?,?,?,?)""", (old,"vm-old","A","B",old))
    conn.execute("""INSERT INTO vm_migration_events(
        time,vm_uuid,old_node,new_node,new_seen
    ) VALUES(?,?,?,?,?)""", (new,"vm-new","A","B",new))
    conn.execute("""INSERT INTO vm_abuse_events(
        event_time,event_type,node,vm_uuid
    ) VALUES(?,?,?,?)""", (old,"started","NODE-A","vm-old"))
    conn.execute("""INSERT INTO vm_abuse_events(
        event_time,event_type,node,vm_uuid
    ) VALUES(?,?,?,?)""", (new,"started","NODE-A","vm-new"))
    conn.execute("""INSERT INTO maintenance_jobs(
        created_at,started_at,finished_at,action,status
    ) VALUES(?,?,?,?,?)""", (old,old,old,"old","done"))
    conn.execute("""INSERT INTO maintenance_jobs(
        created_at,started_at,action,status
    ) VALUES(?,?,?,?)""", (new,new,"active","running"))
    conn.execute("""INSERT INTO retention_runs(
        started_at,finished_at,status,raw_cutoff,hourly_cutoff
    ) VALUES(?,?,?,?,?)""", (old,old,"ok",old,old))


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: test_v48_12_5_bounded_retention.py APP.py", file=sys.stderr)
        return 2
    app_path = str(Path(sys.argv[1]).resolve())
    with tempfile.TemporaryDirectory(prefix="bw-v48125-") as tmp:
        db_path = str(Path(tmp) / "test.db")
        module = load_module(app_path, db_path)
        assert module.V48125_VERSION == "48.12.5"
        assert module.RAW_RETENTION_DAYS == 2
        assert module.HOURLY_RETENTION_DAYS == 7
        assert module.API_ACCESS_LOG_RETENTION_DAYS == 7
        assert "1mo" not in module.PERIODS
        assert module.clean_period("1mo") == "7d"

        now = module.now_ts()
        raw_bucket = module.bucket_for(now - 86400)
        old_bucket = module.bucket_for(now - 8 * 86400)
        hour_base = module.local_hour_start(now - 3 * 86400)
        hourly_buckets = [module.bucket_for(hour_base + offset) for offset in (300, 900, 1500)]

        conn = module.db()
        try:
            insert_node_stat(conn, raw_bucket, "raw")
            for index, bucket in enumerate(hourly_buckets):
                insert_node_stat(conn, bucket, f"hour-{index}")
            insert_node_stat(conn, old_bucket, "old")

            for ts, label in ((now-8*86400,"old"),(now-3600,"new")):
                conn.execute("""INSERT INTO bandwidth_hourly(
                    hour_start,node,vm_uuid,bridge,last_push
                ) VALUES(?,?,?,?,?)""", (module.local_hour_start(ts),"NODE-A",f"vm-bh-{label}","br0",ts))
                conn.execute("""INSERT INTO bandwidth_daily(
                    day_start,node,vm_uuid,bridge,last_push
                ) VALUES(?,?,?,?,?)""", (module.local_day_start(ts),"NODE-A",f"vm-bd-{label}","br0",ts))

            conn.execute("""INSERT INTO api_keys(
                key_id,name,secret_hash,created_at
            ) VALUES(?,?,?,?)""", ("keepkey000001","keep","hash",now-30*86400))
            conn.execute("""INSERT INTO vm_current_fast(
                node,vm_uuid,last_seen
            ) VALUES(?,?,?)""", ("NODE-A","vm-current",now))
            insert_event_rows(conn, now)
            conn.commit()
        finally:
            conn.close()

        result = module.run_retention(dry_run=False)
        assert result["policy"]["raw_days"] == 2
        assert result["policy"]["hourly_days"] == 7
        assert result["policy"]["history_days"] == 7
        assert result["snapshot_backfill_needed"] is True

        # A second recurring run must trust node_push_snapshots instead of
        # rescanning all large VM/interface history tables.
        second = module.run_retention(dry_run=False)
        assert second["snapshot_backfill_needed"] is False

        conn = module.db()
        try:
            buckets = [r[0] for r in conn.execute(
                "SELECT bucket FROM node_stats WHERE node='NODE-A' ORDER BY bucket"
            )]
            assert raw_bucket in buckets, buckets
            kept_hourly = [b for b in hourly_buckets if b in buckets]
            assert len(kept_hourly) == 1, (hourly_buckets, buckets)
            assert old_bucket not in buckets, buckets
            tier = conn.execute(
                "SELECT retention_tier FROM node_push_snapshots WHERE node='NODE-A' AND bucket=?",
                (kept_hourly[0],),
            ).fetchone()
            assert tier and tier[0] == "hourly", tier

            for table in ("bandwidth_hourly","bandwidth_daily","node_logs","account_logs",
                          "api_access_logs","api_key_events","node_missed_events",
                          "vm_migration_events","vm_abuse_events"):
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert count == 1, (table, count)
            assert conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM vm_current_fast").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM maintenance_jobs WHERE status='running'").fetchone()[0] == 1
            assert conn.execute("SELECT COUNT(*) FROM maintenance_jobs WHERE action='old'").fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM retention_runs WHERE started_at<?", (now-7*86400,)).fetchone()[0] == 0
        finally:
            conn.close()

        print("PASS: v48.12.5 hard clamps legacy 7/30 settings to 2/7")
        print("PASS: latest 48h retains every real 5-minute snapshot")
        print("PASS: days 3-7 retain one real snapshot per node/local-hour")
        print("PASS: history/log/event rows older than 7 days are deleted")
        print("PASS: expensive snapshot-table backfill runs once, not every timer cycle")
        print("PASS: current state, active queue rows and API keys are preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
