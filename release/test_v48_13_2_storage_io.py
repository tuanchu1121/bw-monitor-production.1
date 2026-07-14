#!/usr/bin/env python3
import importlib.util
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def load_module(app_path, db_path):
    os.environ["BW_MONITOR_DB"] = db_path
    os.environ["BW_MONITOR_TOKEN"] = "storage-test-token"
    spec = importlib.util.spec_from_file_location("bw_storage_test_app", app_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def response_html(response):
    if isinstance(response, tuple):
        response = response[0]
    return response.get_data(as_text=True)


def main():
    app_path = Path(sys.argv[1] if len(sys.argv) > 1 else "./bw_monitor_app_v48_12_9_operations_ui.py").resolve()
    agent_path = Path(sys.argv[2] if len(sys.argv) > 2 else "./bwagent_daemon_v10_dynamic_abuse.py").resolve()
    source = app_path.read_text(encoding="utf-8")
    agent_source = agent_path.read_text(encoding="utf-8")

    # Scope guard: the disk-only release must not replace the old main views.
    check("top-vm-v48131" not in source, "Top VM renderer was unexpectedly replaced")
    check("vm_page_v48131" not in source, "VM Detail renderer was unexpectedly wrapped")
    check("vm_abuse_page_v48131" not in source, "VM Abuse renderer was unexpectedly wrapped")
    check('def storage_io_page()' in source, "Storage I/O route is missing")
    check('Latest sample lookback' in source, "Storage I/O lookback control is missing")
    check('ALLOCATED / ASSIGNED' in source, "Allocated/Assigned compact column is missing")
    check('AGENT_VERSION = 11' in agent_source, "Agent v11 marker is missing")
    check('"virsh", "domstats", "--list-active", "--vcpu", "--balloon", "--block"' in agent_source, "Agent no longer uses one bulk domstats call")
    check('"disks": disks' in agent_source, "Agent does not send per-disk payloads")
    check('"storage_devices": storage_devices' in agent_source, "Agent does not send node storage payloads")

    with tempfile.TemporaryDirectory(prefix="bw-storage-test-") as td:
        db_path = str(Path(td) / "bandwidth.db")
        mod = load_module(str(app_path), db_path)
        now = int(time.time())
        conn = mod.db()
        try:
            mod.ensure_disk_io_schema(conn)
            mod.ingest_disk_io_current(
                conn,
                "UT-Storage-1",
                now,
                60,
                [{
                    "vm_uuid": "8510ddeb-df0b-4f14-a074-d13cdac1d9e2",
                    "disks": [
                        {
                            "target": "vda",
                            "source": "/home/vf-data/disk/8510ddeb_1.img",
                            "role": "customer",
                            "mount": "/home",
                            "storage_device": "/dev/md3",
                            "storage_block": "md3",
                            "storage_fstype": "ext4",
                            "capacity_bytes": 40 * 1024**3,
                            "allocation_bytes": 18 * 1024**3,
                            "physical_bytes": 18 * 1024**3,
                            "read_delta": 2 * 1024**2,
                            "write_delta": 5 * 1024**2,
                            "read_reqs_delta": 30,
                            "write_reqs_delta": 80,
                            "interval_seconds": 60,
                        },
                        {
                            "target": "vdb",
                            "source": "/home2/8510ddeb_2.img",
                            "role": "customer",
                            "mount": "/home2",
                            "storage_device": "/dev/sda1",
                            "storage_block": "sda1",
                            "storage_fstype": "ext4",
                            "capacity_bytes": 1024 * 1024**3,
                            "allocation_bytes": 785 * 1024**3,
                            "physical_bytes": 785 * 1024**3,
                            "read_delta": 76 * 1024**2,
                            "write_delta": 1139 * 1024**2,
                            "read_reqs_delta": 8910,
                            "write_reqs_delta": 110580,
                            "interval_seconds": 60,
                        },
                        {
                            "target": "sdx",
                            "source": "/home/vf-data/server/8510ddeb/cloud-drive.img",
                            "role": "auxiliary",
                            "mount": "/home",
                            "storage_device": "/dev/md3",
                            "storage_block": "md3",
                            "capacity_bytes": 0,
                            "allocation_bytes": 0,
                            "read_delta": 0,
                            "write_delta": 0,
                            "read_reqs_delta": 0,
                            "write_reqs_delta": 0,
                            "interval_seconds": 60,
                        },
                    ],
                }],
                {
                    "storage_devices": [
                        {
                            "mount": "/home",
                            "device": "/dev/md3",
                            "block": "md3",
                            "raid_level": "raid1",
                            "fstype": "ext4",
                            "size": 7 * 1024**4,
                            "used": 3 * 1024**4,
                            "avail": 4 * 1024**4,
                            "use_percent": 42.8,
                            "read_bps": 100 * 1024**2,
                            "write_bps": 80 * 1024**2,
                            "read_iops": 500,
                            "write_iops": 600,
                            "util_percent": 35,
                        },
                        {
                            "mount": "/home2",
                            "device": "/dev/sda1",
                            "block": "sda1",
                            "raid_level": "",
                            "fstype": "ext4",
                            "size": 203 * 1024**4,
                            "used": 60 * 1024**4,
                            "avail": 134 * 1024**4,
                            "use_percent": 29.5,
                            "read_bps": 250 * 1024**2,
                            "write_bps": 120 * 1024**2,
                            "read_iops": 1500,
                            "write_iops": 3200,
                            "util_percent": 82,
                        },
                    ]
                },
            )
            conn.commit()
            check(conn.execute("SELECT COUNT(*) FROM vm_disk_current").fetchone()[0] == 3, "latest VM disk rows were not stored")
            check(conn.execute("SELECT COUNT(*) FROM node_storage_current").fetchone()[0] == 2, "latest storage rows were not stored")
        finally:
            conn.close()

        with mod.app.test_request_context("/storage?view=disks&period=15m&sort=allocated&order=desc&q=home2"):
            html = response_html(mod.storage_io_page())
        check("VM Disks" in html, "VM disk view did not render")
        check("8510ddeb-df0b-4f14-a074-d13cdac1d9e2" in html, "VM UUID is missing from disk view")
        check("vdb" in html and "/home2" in html and "/dev/sda1" in html, "per-disk storage mapping is missing")
        check("cloud-drive.img" not in html, "auxiliary cloud disk leaked into customer disk view")
        check("sort=allocated" in html and "sort=writeiops" in html, "disk sort links are missing")
        check("period=15m" in html, "lookback period was not preserved")

        with mod.app.test_request_context("/storage?view=backends&period=15m&sort=writeiops&order=desc"):
            html = response_html(mod.storage_io_page())
        check("Storage Backends" in html, "storage backend view did not render")
        check("/home2" in html and "/dev/sda1" in html, "SATA storage mapping is missing")
        check("hardware/unknown RAID" in html, "unknown hardware RAID label is missing")
        check("VM DISKS" in html and "UTIL" in html, "backend operational columns are missing")

        # UUID purge removes only VM disk rows. Node storage remains intact.
        conn = mod.db()
        try:
            mod.purge_vm_data(conn, "UT-Storage-1", "8510ddeb-df0b-4f14-a074-d13cdac1d9e2")
            conn.commit()
            check(conn.execute("SELECT COUNT(*) FROM vm_disk_current").fetchone()[0] == 0, "UUID purge left VM disk rows")
            check(conn.execute("SELECT COUNT(*) FROM node_storage_current").fetchone()[0] == 2, "UUID purge incorrectly deleted node storage rows")
        finally:
            conn.close()

    print("PASS: v48.13.2 disk-only collector, compact Storage I/O, lookback, sorting and UUID cleanup")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
