#!/usr/bin/env python3
"""Regression coverage for v48.13.8 retained Storage I/O snapshots and identity-first UI.

Checks:
- compact storage payload is attached to retained node_push_snapshots;
- 5m remains a fast live view while age buttons open real older samples;
- custom datetime opens the nearest retained storage sample;
- storage dropdown values are unique across nodes;
- All views use compact VM/node cards and default to 30 rows;
- VM UUID is primary, node/IP are supporting metadata, controls match Top VM;
- allocated/assigned meters are visibly color-coded;
- exact UUID purge removes the UUID from retained storage payloads too.
"""
from __future__ import annotations

import importlib.util
import os
import tempfile
import time
from pathlib import Path


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def load_module(app_path, db_path):
    os.environ["BW_MONITOR_DB"] = db_path
    os.environ["BW_MONITOR_TOKEN"] = "storage-history-test"
    spec = importlib.util.spec_from_file_location("bw_storage_history_app", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def html_of(value):
    if isinstance(value, tuple):
        value = value[0]
    return value.get_data(as_text=True)


def insert_push(conn, mod, node, ts):
    bucket = mod.bucket_for(ts)
    conn.execute(
        """INSERT INTO node_push_snapshots(
             node,bucket,push_time,last_push,vm_count,iface_count,inventory_complete,retention_tier
           ) VALUES(?,?,?,?,?,?,?,?)""",
        (node, bucket, ts, ts, 1, 1, 1, "raw"),
    )


def disk_payload(vm_uuid, write_mib_s):
    return [{
        "vm_uuid": vm_uuid,
        "disks": [{
            "target": "vda",
            "source": f"/home/{vm_uuid}.img",
            "role": "customer",
            "mount": "/home",
            "storage_device": "/dev/mapper/almalinux-home",
            "storage_block": "dm-0",
            "storage_fstype": "xfs",
            "capacity_bytes": 100 * 1024**3,
            "allocation_bytes": 50 * 1024**3,
            "physical_bytes": 50 * 1024**3,
            "read_delta": 60 * 1024**2,
            "write_delta": int(write_mib_s * 60 * 1024**2),
            "read_reqs_delta": 60,
            "write_reqs_delta": int(write_mib_s * 60),
            "interval_seconds": 60,
        }],
    }]


def storage_payload(write_mib_s):
    return {"storage_devices": [{
        "mount": "/home",
        "device": "/dev/mapper/almalinux-home",
        "block": "dm-0",
        "raid_level": "raid10",
        "fstype": "xfs",
        "size": 10 * 1024**4,
        "used": 6 * 1024**4,
        "avail": 4 * 1024**4,
        "use_percent": 60.0,
        "read_bps": 2 * 1024**2,
        "write_bps": write_mib_s * 1024**2,
        "read_iops": 20,
        "write_iops": write_mib_s * 10,
        "util_percent": min(99.9, write_mib_s),
    }]}


def main():
    app_path = Path(sys.argv[1] if len(sys.argv) > 1 else "./bw_monitor_app_v48_12_9_operations_ui.py").resolve()
    source = app_path.read_text(encoding="utf-8")
    check('V48137_VERSION = "48.13.7"' in source, "v48.13.7 retained-history marker is missing")
    check('V48138_VERSION = "48.13.8"' in source, "v48.13.8 marker is missing")
    check('V48138_BUILD = "r1"' in source, "v48.13.8-r1 marker is missing")
    check('storage_payload' in source and 'zlib.compress' in source, "compressed retained Storage payload is missing")
    check('Custom Snapshot Time' in source and 'Snapshot lookback' in source, "Top VM-style Storage snapshot controls are missing")
    check('storage-vm-card' in source and 'storage-node-card' in source, "compact Storage card views are missing")
    check('storage-vm-identity' in source and 'identity-kicker' in source, "UUID-first VM identity layout is missing")
    check('disk-cap-meter' in source and '#12b76a' in source, "colored allocated/assigned meter is missing")
    check('SELECT DISTINCT mount FROM (' in source, "Storage dropdown mount deduplication is missing")

    with tempfile.TemporaryDirectory(prefix="bw-storage-history-") as td:
        db_path = str(Path(td) / "bandwidth.db")
        mod = load_module(str(app_path), db_path)
        now = (int(time.time()) // mod.CACHE_BUCKET_SECONDS) * mod.CACHE_BUCKET_SECONDS
        old = now - 10 * 60
        node1 = "node-a"
        node2 = "node-b"
        vm_uuid = "11111111-2222-3333-4444-555555555555"
        conn = mod.db()
        try:
            mod.ensure_storage_snapshot_schema(conn)
            for node, ip in ((node1, "10.0.0.1"), (node2, "10.0.0.2")):
                conn.execute(
                    "INSERT INTO node_bridge_addresses_latest(node,role,bridge,primary_ipv4,ipv4_json,last_seen) VALUES(?,?,?,?,?,?)",
                    (node, "public", "br0", ip, f'["{ip}"]', now),
                )
                conn.execute(
                    "INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,status) VALUES(?,?,?,?,?)",
                    (node, vm_uuid if node == node1 else "other-vm", old, now, "active"),
                )
            insert_push(conn, mod, node1, old)
            mod.ingest_disk_io_current(conn, node1, old, 60, disk_payload(vm_uuid, 10), storage_payload(10))
            insert_push(conn, mod, node1, now)
            mod.ingest_disk_io_current(conn, node1, now, 60, disk_payload(vm_uuid, 20), storage_payload(20))
            # Second node repeats /home to verify one unique dropdown option.
            insert_push(conn, mod, node2, now)
            mod.ingest_disk_io_current(conn, node2, now, 60, disk_payload("other-vm", 5), storage_payload(5))
            conn.commit()
            row = conn.execute(
                "SELECT length(storage_payload),storage_payload_version FROM node_push_snapshots WHERE node=? AND bucket=?",
                (node1, mod.bucket_for(old)),
            ).fetchone()
            check(row and int(row[0] or 0) > 0 and int(row[1] or 0) == 1, "retained Storage payload was not written")
        finally:
            conn.close()

        with mod.app.test_request_context("/storage?view=disks&period=5m"):
            live_html = html_of(mod.app.view_functions["storage_io_page"]())
        check("LIVE CURRENT" in live_html and "20.00 MiB/s" in live_html, "5m Storage view is not live/current")
        check("Custom Snapshot Time" in live_html and "Snapshot lookback" in live_html, "Top VM-style Storage time controls are not rendered")
        check("storage-top-card" in live_html and 'class="search"' in live_html, "Storage toolbar does not match Top VM workflow")
        check("storage-vm-identity" in live_html and "VM UUID" in live_html, "VM UUID is not the primary Storage identity")
        check("disk-cap-meter" in live_html, "allocated/assigned color meter is not rendered")
        check('option value="30" selected' in live_html, "Storage default row count is not 30")
        check(live_html.count('option value="/home"') == 1, "Storage dropdown repeats /home across nodes")
        check("storage-vm-card" in live_html, "VM All view is not using the compact card layout")

        with mod.app.test_request_context("/storage?view=disks&period=10m&node=node-a"):
            old_html = html_of(mod.app.view_functions["storage_io_page"]())
        check("RETAINED SNAPSHOT" in old_html, "10m age did not switch to retained history")
        check("10.00 MiB/s" in old_html and "20.00 MiB/s" not in old_html, "10m age did not open the real older sample")

        at_value = mod._datetime_local_value(old)
        with mod.app.test_request_context(f"/storage?view=nodes&period=5m&node=node-a&at={at_value}"):
            at_html = html_of(mod.app.view_functions["storage_io_page"]())
        check("RETAINED SNAPSHOT" in at_html and "10.00 MiB/s" in at_html, "custom datetime did not open the retained storage sample")
        check("storage-node-card" in at_html, "Storage Node All view is not using the compact card layout")

        # Purge must scrub retained disk payloads on the affected node, not only current tables.
        conn = mod.db()
        try:
            result = mod.purge_vm_data(conn, node1, vm_uuid)
            conn.commit()
            check(int(result.get("storage_snapshot_payloads", 0)) >= 1, "UUID purge did not scrub retained Storage payloads")
        finally:
            conn.close()
        with mod.app.test_request_context(f"/storage?view=disks&period=10m&node=node-a&q={vm_uuid}"):
            purged_html = html_of(mod.app.view_functions["storage_io_page"]())
        check(f'data-copy="{vm_uuid}"' not in purged_html and '<article class="storage-vm-card">' not in purged_html, "purged UUID remains visible in retained Storage history")

    print("PASS: v48.13.8 retained Storage snapshots, Top VM-style controls, UUID-first cards, color meters and historical UUID purge")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
