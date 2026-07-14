#!/usr/bin/env python3
import gzip
import importlib.util
import os
import pathlib
import tempfile
import time


def check(value, message):
    if not value:
        raise AssertionError(message)


def load_app(path, db_path):
    os.environ["BW_MONITOR_DB"] = str(db_path)
    os.environ["BW_MONITOR_TOKEN"] = "performance-test-token"
    os.environ["BW_REDIS_ENABLED"] = "0"
    os.environ["BW_PAGE_CACHE_ENABLED"] = "0"
    spec = importlib.util.spec_from_file_location("bw_monitor_v48140_test", str(path))
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def main():
    app_path = pathlib.Path(__file__).with_name("bw_monitor_app_v48_12_9_operations_ui.py")
    with tempfile.TemporaryDirectory(prefix="bw-monitor-v48140-") as tmp:
        module = load_app(app_path, pathlib.Path(tmp) / "perf.db")
        check(module.V48140_VERSION == "48.14.0", "performance marker is missing")
        check(module.V48140_BUILD == "r1", "performance build marker is missing")
        check(module.db.__name__ == "db", "fast db helper is not active")

        conn = module.db()
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            check("vm_disk_summary_current" in tables, "VM disk summary table is missing")
            check("node_storage_mount_summary_current" in tables, "node mount summary table is missing")
            indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            for name in (
                "idx_v48140_vmdisk_write_iops",
                "idx_v48140_vmdisk_alloc",
                "idx_v48140_vmdisk_slots",
                "idx_v48140_mount_write_iops",
                "idx_v48140_disk_role_mount_node",
            ):
                check(name in indexes, f"missing performance index: {name}")

            now = int(time.time())
            rows = [
                ("node-a", "uuid-a", "vda", "/home/a.img", "customer", "/home", 1000, 400, 500, 10, 20, 1, 2, now),
                ("node-a", "uuid-a", "vdb", "/home2/a.img", "customer", "/home2", 2000, 600, 700, 30, 40, 3, 4, now),
                ("node-a", "uuid-b", "vda", "/home/b.img", "customer", "/home", 4000, 1000, 1200, 50, 60, 5, 6, now),
            ]
            conn.executemany("""
                INSERT INTO vm_disk_current(
                  node,vm_uuid,target,source,role,mount,capacity_bytes,allocation_bytes,
                  physical_bytes,read_bps,write_bps,read_iops,write_iops,last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)
            conn.executemany("""
                INSERT INTO node_storage_current(
                  node,mount,device,block,raid_level,fstype,size,used,avail,use_percent,
                  read_bps,write_bps,read_iops,write_iops,util_percent,last_seen
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, [
                ("node-a", "/home", "/dev/md1", "md1", "raid10", "xfs", 10000, 5000, 5000, 50, 100, 200, 10, 20, 30, now),
                ("node-a", "/home2", "/dev/sda1", "sda1", "hardware/unknown RAID", "xfs", 20000, 8000, 12000, 40, 300, 400, 30, 40, 70, now),
            ])
            module._v48140_refresh_node_summaries(conn, "node-a")
            conn.commit()

            vm = conn.execute("""
              SELECT disk_count,allocated_bytes,assigned_bytes,read_bps,write_iops,allocation_ratio
                FROM vm_disk_summary_current WHERE node='node-a' AND vm_uuid='uuid-a'
            """).fetchone()
            check(vm[:5] == (2, 1000, 3000, 40.0, 6.0), "VM materialized summary is incorrect")
            check(abs(vm[5] - (1 / 3)) < 0.0001, "VM allocation ratio is incorrect")
            mount = conn.execute("""
              SELECT disk_count,vm_count FROM node_storage_mount_summary_current
               WHERE node='node-a' AND mount='/home'
            """).fetchone()
            check(mount == (2, 2), "node mount summary counts are incorrect")

            totals = module._v48133_disk_totals_for_pairs([("node-a", "uuid-a"), ("node-a", "uuid-b")])
            check(totals[("node-a", "uuid-a")] == (1000, 3000, 2), "Top VM summary lookup is incorrect")

            plan = " ".join(str(r[-1]) for r in conn.execute(
                "EXPLAIN QUERY PLAN SELECT node,vm_uuid FROM vm_disk_summary_current ORDER BY write_iops DESC LIMIT 10"
            ).fetchall())
            check("idx_v48140_vmdisk_write_iops" in plan, "write IOPS sort does not use the materialized index")
        finally:
            conn.close()

        module._v48140_cache_set("test-key", "hello", 10)
        check(module._v48140_cache_get("test-key") == "hello", "local cache fallback is not working")

        with module.app.test_request_context("/performance-test", headers={"Accept-Encoding": "gzip"}):
            response = module.app.make_response("x" * 4096)
            response.mimetype = "text/html"
            response = module._v48140_response_performance(response)
            check(response.headers.get("Content-Encoding") == "gzip", "direct response compression is not active")
            check(gzip.decompress(response.get_data()) == b"x" * 4096, "compressed response is corrupt")

        check("api_v1_performance_v48140" in module.app.view_functions, "performance health endpoint is missing")
        check("content-visibility:auto" in module.V48140_RENDER_CSS, "browser render containment is missing")

    print("PASS: v48.14.0 Redis/SQLite/materialized-summary performance edition")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
