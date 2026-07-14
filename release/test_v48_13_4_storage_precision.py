#!/usr/bin/env python3
"""Regression coverage for v48.13.6-r1 grouped storage and filesystem precision.

Checks:
- per-disk Agent payload and robust /home mount discovery;
- Top VM total Host Allocated / Assigned column and disk sorting;
- VM detail per-disk capacity cards and per-disk I/O table placement;
- grouped VM Disks/Storage Node All views plus per-mount forensic views;
- Node Filesystems fallback for a separate /home mount;
- exact UUID purge that preserves every unrelated VM's Abuse state/history.
"""
from __future__ import annotations

import importlib.util
import os
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


def insert_fast_vm(conn, now, node, vm_uuid, total_bytes):
    conn.execute(
        "INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,status) VALUES(?,?,?,?,?)",
        (node, vm_uuid, now, now, "active"),
    )
    conn.execute(
        """INSERT INTO vm_current_fast(
             node,vm_uuid,last_seen,interval_seconds,iface_count,
             rx_bytes,tx_bytes,total_bytes,total_mbps,total_peak_mbps,total_pps,total_peak_pps,
             sample_count,sample_expected,sample_quality,
             cpu_full_percent,cpu_core_percent,vcpu_current,
             ram_current_kib,ram_rss_kib,ram_available_kib,
             disk_read_bps,disk_write_bps
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (node, vm_uuid, now, 300, 1, total_bytes // 2, total_bytes // 2, total_bytes,
         10, 20, 30, 40, 20, 20, "GOOD", 25, 100, 4,
         8 * 1024**2, 5 * 1024**2, 6 * 1024**2, 1024, 2048),
    )


def main():
    app_path = Path(sys.argv[1] if len(sys.argv) > 1 else "./bw_monitor_app_v48_12_9_operations_ui.py").resolve()
    agent_path = Path(sys.argv[2] if len(sys.argv) > 2 else "./bwagent_daemon_v10_dynamic_abuse.py").resolve()
    source = app_path.read_text(encoding="utf-8")
    agent_source = agent_path.read_text(encoding="utf-8")

    check('V48136_VERSION = "48.13.6"' in source, "v48.13.6 marker is missing")
    check('V48136_BUILD = "r1"' in source, "v48.13.6-r1 marker is missing")
    check('disk-capacity-sort-head' in source and 'diskallocated' in source and 'diskassigned' in source, "Top VM disk capacity sorting is missing")
    check('Virtual Disk I/O' in source and 'vm-disk-total-overview' in source, "VM overview/per-disk detail UI is missing")
    check('TOTAL HOST ALLOCATED / ASSIGNED' not in source, "obsolete total strip is still present in Virtual Disk I/O")
    check('Storage Node' in source and 'storage-vm-group-row' in source and 'storage-node-group-row' in source, "grouped Storage I/O UI is missing")
    check('Search node, IP, UUID, disk, path or mount' in source, "Storage I/O search bar is missing")
    check('def purge_vm_data(conn, node, vm_uuid' in source and 'DELETE FROM {table} WHERE vm_uuid=?' in source, "exact UUID purge override is missing")
    check("NOT IN ('cycles-v2','cycles-v3','cycles-v3-ram')" in source, "app import can still reset current abuse for the final engine")
    check('All status' in source and 'Active' in source and 'Hidden' in source and 'Stale' in source, "Admin status filters are missing")
    check('AGENT_VERSION = 12' in agent_source, "Agent v12 marker is missing")
    agent_installer = app_path.parent.parent / 'deploy' / 'agent' / 'install-agent.sh'
    if agent_installer.exists():
        installer_source = agent_installer.read_text(encoding='utf-8')
        check('ProtectHome=read-only' in installer_source and 'ProtectHome=true' not in installer_source, "Agent service still hides /home")
    check('"virsh", "domstats", "--list-active", "--vcpu", "--balloon", "--block"' in agent_source, "Agent no longer uses one bulk domstats call")
    check('_collect_df_filesystems' in agent_source and '_collect_findmnt_metadata' in agent_source and '_dedupe_filesystem_roots' in agent_source, "Agent does not merge df/findmnt or dedupe filesystem roots")
    check('Do not require SOURCE to start with /dev/' in agent_source, "mount mapping still rejects non-/dev storage sources")
    check('"disks": disks' in agent_source and '"storage_devices": storage_devices' in agent_source, "Agent per-disk/storage payload is incomplete")

    # Agent mount inventory: a separate LVM /home must survive while
    # systemd bind aliases of / are collapsed.
    agent_spec = importlib.util.spec_from_file_location("bw_storage_test_agent", agent_path)
    agent_mod = importlib.util.module_from_spec(agent_spec)
    agent_spec.loader.exec_module(agent_mod)
    old_df = agent_mod._collect_df_filesystems
    old_findmnt = agent_mod._collect_findmnt_metadata
    try:
        agent_mod._collect_df_filesystems = lambda: {
            "/": {"device":"/dev/md125","maj_min":"9:125","fstype":"xfs","mount":"/","size":160,"used":10,"avail":150,"use_percent":6,"fsroot":"/","submount":False},
            "/home": {"device":"/dev/mapper/almalinux-home","maj_min":"253:0","fstype":"xfs","mount":"/home","size":11000,"used":6800,"avail":3800,"use_percent":65,"fsroot":"/","submount":False},
            "/etc": {"device":"/dev/md125","maj_min":"9:125","fstype":"xfs","mount":"/etc","size":160,"used":10,"avail":150,"use_percent":6,"fsroot":"/etc","submount":True},
        }
        agent_mod._collect_findmnt_metadata = lambda: {
            "/": {"device":"/dev/md125","maj_min":"9:125","fstype":"xfs","mount":"/","fsroot":"/","submount":False},
            "/home": {"device":"/dev/mapper/almalinux-home","maj_min":"253:0","fstype":"xfs","mount":"/home","fsroot":"/","submount":False},
            "/etc": {"device":"/dev/md125","maj_min":"9:125","fstype":"xfs","mount":"/etc","fsroot":"/etc","submount":True},
        }
        mounts = {row["mount"] for row in agent_mod.collect_filesystems()}
        check(mounts == {"/", "/home"}, f"Agent real filesystem filtering is wrong: {mounts}")
    finally:
        agent_mod._collect_df_filesystems = old_df
        agent_mod._collect_findmnt_metadata = old_findmnt

    with tempfile.TemporaryDirectory(prefix="bw-storage-test-") as td:
        db_path = str(Path(td) / "bandwidth.db")
        mod = load_module(str(app_path), db_path)
        now = int(time.time())
        node = "UT-Storage-1"
        vm_uuid = "8510ddeb-df0b-4f14-a074-d13cdac1d9e2"
        other_uuid = "other-abuse-vm"
        conn = mod.db()
        try:
            mod.ensure_disk_io_schema(conn)
            conn.execute(
                "INSERT INTO node_bridge_addresses_latest(node,role,bridge,primary_ipv4,ipv4_json,last_seen) VALUES(?,?,?,?,?,?)",
                (node, "public", "br0", "167.253.159.3", '["167.253.159.3"]', now),
            )
            insert_fast_vm(conn, now, node, vm_uuid, 1000)
            insert_fast_vm(conn, now, node, other_uuid, 500)
            mod.ingest_disk_io_current(
                conn, node, now, 60,
                [{
                    "vm_uuid": vm_uuid,
                    "disks": [
                        {
                            "target": "vda", "source": f"/home/vf-data/disk/{vm_uuid}_1.img", "role": "customer",
                            "mount": "/home", "storage_device": "/dev/md3", "storage_block": "md3", "storage_fstype": "ext4",
                            "capacity_bytes": 40 * 1024**3, "allocation_bytes": 18 * 1024**3, "physical_bytes": 18 * 1024**3,
                            "read_delta": 2 * 1024**2, "write_delta": 5 * 1024**2,
                            "read_reqs_delta": 30, "write_reqs_delta": 80, "interval_seconds": 60,
                        },
                        {
                            "target": "vdb", "source": f"/home2/{vm_uuid}_2.img", "role": "customer",
                            "mount": "/home2", "storage_device": "/dev/sda1", "storage_block": "sda1", "storage_fstype": "ext4",
                            "capacity_bytes": 1024 * 1024**3, "allocation_bytes": 785 * 1024**3, "physical_bytes": 785 * 1024**3,
                            "read_delta": 76 * 1024**2, "write_delta": 1139 * 1024**2,
                            "read_reqs_delta": 8910, "write_reqs_delta": 110580, "interval_seconds": 60,
                        },
                        {
                            "target": "sdx", "source": f"/home/vf-data/server/{vm_uuid}/cloud-drive.img", "role": "auxiliary",
                            "mount": "/home", "storage_device": "/dev/md3", "storage_block": "md3",
                            "capacity_bytes": 0, "allocation_bytes": 0, "read_delta": 0, "write_delta": 0,
                            "read_reqs_delta": 0, "write_reqs_delta": 0, "interval_seconds": 60,
                        },
                    ],
                }],
                {"storage_devices": [
                    {"mount": "/", "device": "/dev/sda2", "block": "sda2", "fstype": "xfs",
                     "size": 160 * 1024**3, "used": 20 * 1024**3, "avail": 140 * 1024**3,
                     "use_percent": 12.5, "read_bps": 1024, "write_bps": 2048, "read_iops": 2, "write_iops": 3, "util_percent": 1},
                    {"mount": "/home", "device": "/dev/mapper/storage-home", "block": "dm-3", "fstype": "xfs",
                     "size": 200 * 1024**4, "used": 122 * 1024**4, "avail": 78 * 1024**4,
                     "use_percent": 61.0, "read_bps": 100 * 1024**2, "write_bps": 80 * 1024**2,
                     "read_iops": 500, "write_iops": 600, "util_percent": 35},
                    {"mount": "/home2", "device": "/dev/sda1", "block": "sda1", "fstype": "ext4",
                     "size": 203 * 1024**4, "used": 60 * 1024**4, "avail": 134 * 1024**4,
                     "use_percent": 29.5, "read_bps": 250 * 1024**2, "write_bps": 120 * 1024**2,
                     "read_iops": 1500, "write_iops": 3200, "util_percent": 82},
                ]},
            )
            # A second VM with a smaller disk gives Top VM a real disk sort comparison.
            conn.execute(
                """INSERT INTO vm_disk_current(
                     node,vm_uuid,target,source,role,mount,storage_device,capacity_bytes,allocation_bytes,last_seen
                   ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (node, other_uuid, "vda", f"/home/{other_uuid}.img", "customer", "/home", "/dev/mapper/storage-home",
                 80 * 1024**3, 10 * 1024**3, now),
            )
            conn.commit()
        finally:
            conn.close()

        # Top VM: total capacity is between RAM and Disk R/s and sortable.
        check(mod.clean_top_sort("diskallocated") == "diskallocated", "Top VM sanitizer discards ALLOC sort")
        check(mod.clean_top_sort("diskassigned") == "diskassigned", "Top VM sanitizer discards ASSIGNED sort")
        check(mod.clean_top_sort("diskallocpct") == "diskallocpct", "Top VM sanitizer discards % sort")
        with mod.app.test_request_context("/top?period=5m&sort=diskallocated&order=desc"):
            rows, *_ = mod.get_top_vm_rows("5m", sort_by="diskallocated", order="desc", limit=100)
            check(rows and rows[0][1] == vm_uuid, "Top VM disk allocated sort is wrong")
            top_html = mod.top_vm_table(rows, "5m", "", "diskallocated", "desc", "all", 100)
        check(top_html.count("ram-compact-sort-head") == 1, "Top VM RAM column was changed")
        check(top_html.count("<th class=\"num-head disk-capacity-sort-head\">") == 1, "Top VM must have one disk capacity column")
        check("v48135-top-disk-meter-fix" in top_html and ".disk-cap-meter i" in top_html, "Top VM disk capacity meter CSS is missing")
        check(top_html.index("<th class=\"num-head ram-compact-sort-head\">") < top_html.index("<th class=\"num-head disk-capacity-sort-head\">") < top_html.index("DISK R/s"), "disk capacity column is not between RAM and Disk R/s")
        check("ALLOCATED / ASSIGNED" in top_html and "ALLOC" in top_html and "ASSIGNED" in top_html, "Top VM disk capacity header is incomplete")
        check('col class="top-rank"' in top_html and 'col class="top-ifaces"' in top_html, "Top VM width controls are missing")
        check("/vm?" in top_html, "Top VM UUID does not open VM detail")

        # VM detail: capacity cards are in Overview and I/O table is between Overview and charts.
        with mod.app.test_request_context(f"/vm?node={node}&vm_uuid={vm_uuid}&period=1h"):
            vm_html = response_html(mod.app.view_functions["vm_page"]())
        check("VM DISK" in vm_html and "vm-disk-total-overview" in vm_html, "VM Overview does not show total allocated / assigned capacity")
        check("Virtual Disk I/O" in vm_html and "READ IOPS" in vm_html and "WRITE IOPS" in vm_html, "VM per-disk I/O panels are missing")
        check("TOTAL HOST ALLOCATED / ASSIGNED" not in vm_html and "vm-disk-total-strip" not in vm_html, "VM detail still renders the repeated total disk strip")
        check(vm_html.count("VIRTUAL DISK") >= 2 and "ALLOCATED / ASSIGNED" in vm_html, "VM detail does not show one clean capacity panel per disk")
        check(vm_html.index("Overview") < vm_html.index("Virtual Disk I/O") < vm_html.index("Average Mbps"), "VM disk detail is not between Overview and charts")
        check("cloud-drive.img" not in vm_html, "auxiliary cloud disk leaked into VM customer disk detail")

        # Storage I/O All view: one VM row with all customer disks nested.
        with mod.app.test_request_context("/storage?view=disks&period=15m&sort=allocated&order=desc&q=167.253.159.3"):
            disk_html = response_html(mod.app.view_functions["storage_io_page"]())
        check("Search node, IP, UUID, disk, path or mount" in disk_html, "Storage search field is missing")
        check("167.253.159.3" in disk_html and 'data-copy="167.253.159.3"' in disk_html, "node IP/copy is missing")
        check(vm_uuid in disk_html and f'data-copy="{vm_uuid}"' in disk_html, "UUID/copy is missing")
        check("VIEW: GROUPED BY UUID" in disk_html and "storage-vm-group-row" in disk_html, "VM Disks All view is not grouped by UUID")
        check("vda" in disk_html and "vdb" in disk_html and disk_html.count("storage-child-item") >= 2, "grouped VM row does not contain all disks")
        check("cloud-drive.img" not in disk_html, "auxiliary disk leaked into grouped VM disks")

        # Selecting a storage mount switches to one matching disk per row.
        with mod.app.test_request_context("/storage?view=disks&period=15m&node=UT-Storage-1&mount=/home2&sort=writeiops&order=desc"):
            filtered_disk_html = response_html(mod.app.view_functions["storage_io_page"]())
        check("FILTERED STORAGE: /home2" in filtered_disk_html, "filtered storage mode banner is missing")
        check("storage-single-disk-row" in filtered_disk_html and "vdb" in filtered_disk_html, "filtered storage mode is not one disk per row")

        # Storage Node All view groups all real mounts under one node.
        with mod.app.test_request_context("/storage?view=nodes&period=15m&q=home"):
            node_html = response_html(mod.app.view_functions["storage_io_page"]())
        check("Storage Node" in node_html and "Storage Backends" not in node_html, "Storage Backends was not renamed")
        check("VIEW: GROUPED BY NODE" in node_html and "storage-node-group-row" in node_html, "Storage Node All view is not grouped by node")
        check("/home" in node_html and "/dev/mapper/storage-home" in node_html and "200.00 TiB" in node_html, "separate /home storage is missing or incorrectly collapsed into /")
        check("/home2" in node_html and "167.253.159.3" in node_html, "grouped Storage Node is missing a child mount or IP")

        # Selecting a filesystem keeps the direct matching-mount table.
        with mod.app.test_request_context("/storage?view=nodes&period=15m&node=UT-Storage-1&mount=/home"):
            filtered_node_html = response_html(mod.app.view_functions["storage_io_page"]())
        check("FILTERED FILESYSTEM: /home" in filtered_node_html, "filtered filesystem mode banner is missing")

        # Node Filesystems fallback appends current mounts missing from a retained snapshot.
        conn = mod.db()
        try:
            bucket = (now // mod.CACHE_BUCKET_SECONDS) * mod.CACHE_BUCKET_SECONDS
            conn.execute("INSERT INTO node_stats(bucket,node,bridge,iface,vm_uuid,last_push) VALUES(?,?,?,?,?,?)", (bucket,node,"br0","tap","x",now))
            conn.execute("INSERT INTO node_filesystem_stats(time,node,mount,device,fstype,size,used,avail,use_percent,last_push) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (bucket,node,"/","/dev/sda2","xfs",160*1024**3,20*1024**3,140*1024**3,12.5,now))
            conn.commit()
        finally:
            conn.close()
        with mod.app.test_request_context("/node/x?period=5m"):
            fs_rows = mod.get_node_filesystems_snapshot(node, "5m")
        mounts = {r[0] for r in fs_rows}
        check("/" in mounts and "/home" in mounts and "/home2" in mounts, "Node Filesystems did not preserve separate current mounts")
        fs_by_mount = {r[0]: r for r in fs_rows}
        check(float(fs_by_mount["/home"][8] or 0) > 0 and float(fs_by_mount["/home"][11] or 0) > 0, "Node Filesystems did not overlay current /home Read/IOPS")
        check(float(fs_by_mount["/home2"][9] or 0) > 0 and float(fs_by_mount["/home2"][12] or 0) > 0, "Node Filesystems did not overlay current /home2 Write/IOPS")
        with mod.app.test_request_context("/node/x?period=5m"):
            fs_html = mod.node_filesystem_table(fs_rows + [("/etc", "/dev/sda2[/etc]", "xfs", 160*1024**3, 20*1024**3, 140*1024**3, 12.5, now, 1, 2, 3, 4, 5, now)])
        check("USED / SIZE" in fs_html and "disk-capacity" in fs_html, "Node Filesystems does not use a RAM-like Used / Size bar")
        check("/etc" not in fs_html, "Node Filesystems still shows service-sandbox bind aliases")

        # Exact UUID purge: target disappears everywhere, unrelated Current Abuse
        # and Abuse Events remain untouched, node storage remains.
        conn = mod.db()
        try:
            for u in (vm_uuid, other_uuid):
                conn.execute("INSERT OR REPLACE INTO vm_abuse_state(node,vm_uuid,last_seen,is_abuse,engine_version) VALUES(?,?,?,1,?)", (node,u,now,"cycles-v3-ram"))
                conn.execute("INSERT INTO vm_abuse_events(event_time,event_type,node,vm_uuid) VALUES(?,?,?,?)", (now,"started",node,u))
                conn.execute("INSERT INTO vm_abuse_incidents(node,vm_uuid,started_at,last_event_at) VALUES(?,?,?,?)", (node,u,now,now))
            # Same UUID on an old migration node must also be removed.
            conn.execute("INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,status) VALUES(?,?,?,?,?)", ("OLD-NODE",vm_uuid,now,now,"active"))
            conn.execute("INSERT INTO vm_current_fast(node,vm_uuid,last_seen) VALUES(?,?,?)", ("OLD-NODE",vm_uuid,now))
            conn.commit()
            # Import/migration safety: a maintenance worker importing the app
            # must not clear every VM's current abuse before the selected purge.
            mod._v4810_migrate_schema()
            check(conn.execute("SELECT COUNT(*) FROM vm_abuse_state WHERE is_abuse=1").fetchone()[0] == 2, "app migration reset unrelated Current Abuse")
            mod.purge_vm_data(conn, node, vm_uuid)
            conn.commit()
            for table in ("vm_disk_current","vm_inventory","vm_current_fast","vm_abuse_state","vm_abuse_events","vm_abuse_incidents"):
                check(conn.execute(f"SELECT COUNT(*) FROM {table} WHERE vm_uuid=?", (vm_uuid,)).fetchone()[0] == 0, f"exact UUID purge left {table} rows")
            check(conn.execute("SELECT COUNT(*) FROM vm_abuse_state WHERE vm_uuid=?", (other_uuid,)).fetchone()[0] == 1, "purging one UUID cleared another VM's Current Abuse")
            check(conn.execute("SELECT COUNT(*) FROM vm_abuse_events WHERE vm_uuid=?", (other_uuid,)).fetchone()[0] == 1, "purging one UUID cleared another VM's Abuse Events")
            check(conn.execute("SELECT COUNT(*) FROM node_storage_current WHERE node=?", (node,)).fetchone()[0] == 3, "UUID purge incorrectly deleted node storage")
        finally:
            conn.close()

    print("PASS: v48.13.6-r1 grouped Storage I/O, working Top VM ALLOC/ASSIGNED/% sorting, visible /home and exact UUID purge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
