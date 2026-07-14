#!/usr/bin/env python3
"""Focused regression coverage for v48.13.9 Abuse disk capacity and Storage cards."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time


def check(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("bw_monitor_v48139_test_app", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} APP.py", file=sys.stderr)
        return 2
    app_path = Path(sys.argv[1]).resolve()
    source = app_path.read_text(encoding="utf-8")
    check('V48139_VERSION = "48.13.9"' in source, "v48.13.9 marker is missing")
    check('V48139_BUILD = "r1"' in source, "v48.13.9-r1 marker is missing")
    check('"diskallocated", "diskassigned", "diskallocpct", "diskslots"' in source, "Abuse disk-capacity sort keys are missing")
    check("storage-entity-card-v48139" in source and "storage-disk-row-v48139" in source, "new Storage card hierarchy is missing")
    check("View details" in source and "Overall" in source and "Performance" in source and "Disks" in source, "Storage card sections are incomplete")

    with tempfile.TemporaryDirectory(prefix="bw-monitor-v48139-test-") as tmp:
        os.environ["BW_MONITOR_DB"] = str(Path(tmp) / "test.db")
        os.environ["BW_MONITOR_TOKEN"] = "v48139-test-token"
        mod = load_module(app_path)
        now = int(time.time())
        conn = mod.db()
        try:
            cfg = mod.get_abuse_settings()
            cols = {row[1] for row in conn.execute("PRAGMA table_info(vm_abuse_state)")}
            values = {
                "node": "node-a", "vm_uuid": "vm-a", "last_seen": now,
                "is_abuse": 1, "abuse_since": now - 600,
                "abuse_flags": "DISK_WRITE", "severity": 2.0,
                "disk_write_bps": 1024.0, "disk_write_iops": 20.0,
                "policy_revision": cfg["revision"], "engine_version": mod.ABUSE_ENGINE_VERSION,
            }
            names = [name for name in values if name in cols]
            conn.execute(
                f"INSERT INTO vm_abuse_state({','.join(names)}) VALUES({','.join('?' for _ in names)})",
                [values[name] for name in names],
            )
            conn.execute(
                "INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,last_iface,last_bridge,status) VALUES(?,?,?,?,?,?,?)",
                ("node-a", "vm-a", now, now, "vnet-a", "br0", "active"),
            )
            mod.ensure_disk_io_schema(conn)
            for target, capacity, allocated in (
                ("vda", 40 * 1024**3, 20 * 1024**3),
                ("vdb", 100 * 1024**3, 80 * 1024**3),
            ):
                conn.execute(
                    "INSERT INTO vm_disk_current(node,vm_uuid,target,source,role,capacity_bytes,allocation_bytes,last_seen) VALUES(?,?,?,?,?,?,?,?)",
                    ("node-a", "vm-a", target, f"/{target}.img", "customer", capacity, allocated, now),
                )
            conn.commit()
        finally:
            conn.close()

        with mod.app.test_request_context("/abuse/vms?tab=current&sort=diskallocated&order=desc"):
            response = mod.app.view_functions["vm_abuse_page"]()
            html = response.get_data(as_text=True)
        check("ALLOCATED / ASSIGNED" in html and "SLOTS" in html, "Abuse disk-capacity header is missing")
        check("100.00 GiB / 140.00 GiB" in html and "2 disk slots" in html, "Abuse disk totals are wrong")
        check("sort=diskallocated" in html and "sort=diskslots" in html, "Abuse capacity sort links are missing")
        check("abuse-current-v48139" in html, "v48.13.9 Abuse table layer is not active")

    print("PASS: v48.13.9 sortable Abuse disk capacity and clear grouped Storage cards")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
