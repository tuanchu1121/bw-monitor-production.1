#!/usr/bin/env python3
"""Focused regression tests for BW Monitor v48.10.4 compact guest-aware VM RAM.

Checks:
- existing v48.10.2 CPU/disk/live-refresh behavior remains present;
- Agent balloon fields are retained in current caches;
- Guest Used = balloon.available - balloon.usable;
- missing balloon stats remain N/A and never fall back to Host RSS;
- Top VM, per-node VM tables and current VM Abuse sort RAM independently by
  Guest %, Guest GiB, Host RSS and Assigned RAM;
- VM detail and node/VM charts use Guest Used, Host RSS and Assigned labels;
- RAM remains visibility only in VM Abuse and is not an abuse flag.
"""
from __future__ import annotations

import importlib.util
from html.parser import HTMLParser
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time




class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)

    def text(self):
        return " ".join(" ".join(self.parts).split())


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(value, message: str) -> None:
    if not value:
        raise AssertionError(message)


def insert_vm(conn: sqlite3.Connection, now: int, node: str, uuid: str, *,
              assigned: int, rss: int, available: int, unused: int, usable: int,
              cpu_core: float, cpu_full: float, vcpu: int,
              disk_read: float = 100.0, disk_write: float = 200.0) -> None:
    conn.execute(
        """INSERT INTO vm_current_fast(
             node,vm_uuid,last_seen,interval_seconds,iface_count,
             rx_bytes,tx_bytes,total_bytes,total_mbps,total_peak_mbps,total_pps,total_peak_pps,
             sample_count,sample_expected,sample_max_gap,sample_quality,
             cpu_full_percent,cpu_core_percent,vcpu_current,
             ram_current_kib,ram_rss_kib,ram_available_kib,ram_unused_kib,ram_usable_kib,
             disk_read_bps,disk_write_bps
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (node,uuid,now,300,1,100,100,200,10,20,30,40,20,20,10,"GOOD",
         cpu_full,cpu_core,vcpu,assigned,rss,available,unused,usable,disk_read,disk_write),
    )
    conn.execute(
        "INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,last_iface,last_bridge,status) VALUES(?,?,?,?,?,?,?)",
        (node,uuid,now,now,f"vnet-{uuid[-4:]}","br0","active"),
    )
    conn.execute(
        """INSERT INTO vm_iface_current(
             node,vm_uuid,bridge,iface,last_seen,interval_seconds,
             rx_bytes,tx_bytes,rx_packets,tx_packets,
             sample_count,sample_expected,sample_max_gap,sample_quality
           ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (node,uuid,"br0",f"vnet-{uuid[-4:]}",now,300,100,100,10,10,20,20,10,"GOOD"),
    )


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print(f"Usage: {sys.argv[0]} APP.py [AGENT.py]", file=sys.stderr)
        return 2

    app_path = Path(sys.argv[1]).resolve()
    agent_path = Path(sys.argv[2]).resolve() if len(sys.argv) == 3 else app_path.with_name(
        "bwagent_daemon_v10_dynamic_abuse.py"
    )

    with tempfile.TemporaryDirectory(prefix="bw-monitor-v48104-test-") as tmp:
        db_path = Path(tmp) / "test.db"
        os.environ["BW_MONITOR_DB"] = str(db_path)
        os.environ["BW_MONITOR_TOKEN"] = "v48104-test-token"
        appmod = load_module(app_path, "bw_monitor_v48104_test_app")

        check(getattr(appmod, "V48103_VERSION", "") == "48.10.3", "missing v48.10.3 guest RAM base marker")
        check(getattr(appmod, "V48104_VERSION", "") == "48.10.4", "wrong v48.10.4 marker")
        check(appmod.app.view_functions["vm_abuse_page"].__name__ in {"vm_abuse_page_v48103", "vm_abuse_page_v48126", "vm_abuse_page_v48128", "vm_abuse_page_v48129"}, "guest-aware abuse/intelligence view is not active")
        check(appmod.app.view_functions["vm_page"].__name__ in {"vm_page_v48103", "vm_page_v48133", "vm_page_v48135"}, "guest-aware VM detail view is not active")

        conn = appmod.db()
        try:
            for table in ("vm_current_fast", "vm_latest_metrics", "vm_perf_stats"):
                columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
                check("ram_unused_kib" in columns, f"{table} is missing ram_unused_kib")
                check("ram_usable_kib" in columns, f"{table} is missing ram_usable_kib")
        finally:
            conn.close()

        # Formula and missing-stat safety.
        metric = appmod.vm_guest_ram_metrics(100_000, 90_000, 100_000, 10_000, 20_000)
        check(metric["has_guest"], "valid balloon stats were rejected")
        check(metric["guest_used_kib"] == 80_000, "Guest Used formula is not available - usable")
        check(abs(metric["guest_used_pct"] - 80.0) < 0.001, "Guest Used percent is wrong")
        missing = appmod.vm_guest_ram_metrics(64_000, 60_000, 0, 0, 0)
        check(not missing["has_guest"], "missing balloon stats were treated as valid")
        missing_html = appmod.fmt_vm_ram_block(64_000, 60_000, 0, 0, 0)
        check("N/A" in missing_html and appmod.fmt_kib(60_000) in missing_html, "N/A/Host RSS fallback display is wrong")
        check("GUEST USED" in missing_html and "HOST RSS" in missing_html, "detailed RAM labels are unclear")
        compact_valid = appmod.fmt_vm_ram_block(100_000, 90_000, 100_000, 10_000, 20_000, compact=True)
        check("80.0% used" in compact_valid and "RSS" in compact_valid, "compact RAM block is missing the essential metrics")
        check("ASSIGNED" not in compact_valid and "Balloon stats OK" not in compact_valid, "compact RAM block is still too verbose")
        compact_missing = appmod.fmt_vm_ram_block(64_000, 60_000, 0, 0, 0, compact=True)
        check("N/A /" in compact_missing and "guest stats unavailable" in compact_missing, "compact missing-stat display is unclear")

        agent_source = agent_path.read_text(encoding="utf-8")
        for field in ("ram_current_kib", "ram_rss_kib", "ram_available_kib", "ram_unused_kib", "ram_usable_kib"):
            check(field in agent_source, f"Agent is missing {field}")

        now = int(time.time())
        bucket = appmod.bucket_for(now)
        node = "NODE-A"
        # Deliberately make each RAM sort key choose a different VM.
        records = [
            # Highest Guest %: 90%; Guest Used 90,000 KiB.
            ("vm-guest-pct", 100_000, 80_000, 100_000, 5_000, 10_000, 799.5, 88.8, 9),
            # Highest Guest GiB: 200,000 KiB; 50%.
            ("vm-guest-used", 400_000, 150_000, 400_000, 100_000, 200_000, 400.0, 50.0, 8),
            # Highest Host RSS.
            ("vm-host-rss", 600_000, 550_000, 600_000, 400_000, 500_000, 100.0, 12.5, 8),
            # Highest allocation.
            ("vm-assigned", 800_000, 120_000, 800_000, 700_000, 750_000, 50.0, 6.25, 8),
            # No guest balloon stats; must always sort after valid Guest values.
            ("vm-no-balloon", 64_000, 60_000, 0, 0, 0, 25.0, 12.5, 2),
        ]
        conn = appmod.db()
        try:
            for uuid,assigned,rss,available,unused,usable,cpu_core,cpu_full,vcpu in records:
                insert_vm(
                    conn, now, node, uuid,
                    assigned=assigned, rss=rss, available=available, unused=unused, usable=usable,
                    cpu_core=cpu_core, cpu_full=cpu_full, vcpu=vcpu,
                )
                conn.execute(
                    """INSERT INTO vm_perf_stats(
                         time,bucket,node,vm_uuid,interval_seconds,vcpu_current,cpu_percent,
                         ram_current_kib,ram_rss_kib,ram_available_kib,ram_unused_kib,ram_usable_kib,
                         disk_read_delta,disk_write_delta,last_push
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (now,bucket,node,uuid,300,vcpu,cpu_full,assigned,rss,available,unused,usable,30_000,60_000,now),
                )
                conn.execute(
                    """INSERT INTO node_stats(
                         bucket,node,bridge,iface,vm_uuid,rx_delta,tx_delta,
                         rx_packets_delta,tx_packets_delta,interval_seconds,last_push
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (bucket,node,"br0",f"vnet-{uuid[-4:]}",uuid,100,100,10,10,300,now),
                )
            conn.execute(
                "INSERT INTO node_current_fast(node,last_seen,interval_seconds,vm_count,iface_count,total_bytes,total_packets) VALUES(?,?,?,?,?,?,?)",
                (node,now,300,len(records),len(records),1_000,100),
            )
            conn.commit()
        finally:
            conn.close()

        expected = {
            "ram": "vm-guest-pct",
            "ramused": "vm-guest-used",
            "ramrss": "vm-host-rss",
            "ramassigned": "vm-assigned",
        }

        # Top VM: all four RAM sort modes, one RAM column, N/A last.
        for key, first_uuid in expected.items():
            with appmod.app.test_request_context(f"/top?sort={key}&order=desc&limit=1000"):
                rows, *_ = appmod.get_top_vm_rows("5m", sort_by=key, order="desc", limit=1000)
                check(rows and rows[0][1] == first_uuid, f"Top VM {key} sort is wrong")
                if key in {"ram", "ramused"}:
                    check(rows[-1][1] == "vm-no-balloon", f"Top VM {key} did not keep N/A last")
        # Historical period path uses the same guest-aware RAM contract.
        with appmod.app.test_request_context("/top?period=1h&sort=ram&order=desc&limit=1000"):
            history_rows, *_ = appmod.get_top_vm_rows("1h", sort_by="ram", order="desc", limit=1000)
            check(history_rows and history_rows[0][1] == "vm-guest-pct" and history_rows[-1][1] == "vm-no-balloon", "historical Top VM Guest% sort is wrong")
        with appmod.app.test_request_context(f"/node?node={node}&period=1h&sort=ram&order=desc"):
            history_rows, *_ = appmod.query_node_bridge(node, "1h", "br0", sort_by="ram", order="desc")
            check(history_rows and history_rows[0][1] == "vm-guest-pct" and history_rows[-1][1] == "vm-no-balloon", "historical node VM Guest% sort is wrong")

        with appmod.app.test_request_context("/top?sort=ram&order=desc&limit=1000"):
            rows, *_ = appmod.get_top_vm_rows("5m", sort_by="ram", order="desc", limit=1000)
            top_html = appmod.top_vm_table(rows, "5m", "", "ram", "desc", "all", 1000)
            check(top_html.count("ram-compact-sort-head") == 1, "Top VM should keep one compact RAM column")
            check(top_html.count("ram-sort-menu") == 1, "Top VM RAM sort controls are not collapsed into one menu")
            for label in ("Guest %", "Used GiB", "Host RSS", "Assigned", "% used", "RSS", "N/A /"):
                check(label in top_html, f"Top VM compact RAM UI is missing {label}")
            check("ram-dual-head" not in top_html, "old four-link RAM header survived")
            check("799.5%" in top_html and "88.8% FULL" in top_html, "existing dual CPU display regressed")

        # Per-node VM/interface table: same four independent RAM sorts.
        for key, first_uuid in expected.items():
            with appmod.app.test_request_context(f"/node?node={node}&period=5m&sort={key}&order=desc"):
                rows, *_ = appmod.query_node_bridge(node, "5m", "br0", sort_by=key, order="desc")
                check(rows and rows[0][1] == first_uuid, f"Node VM table {key} sort is wrong")
                if key in {"ram", "ramused"}:
                    check(rows[-1][1] == "vm-no-balloon", f"Node VM table {key} did not keep N/A last")
        with appmod.app.test_request_context(f"/node?node={node}&period=5m&sort=ram&order=desc"):
            rows, *_ = appmod.query_node_bridge(node, "5m", "br0", sort_by="ram", order="desc")
            node_table = appmod.interface_table("Public", "br0", node, rows, "5m", sort_by="ram", order="desc")
            check(node_table.count("ram-sort-menu") == 1, "Per-node RAM sort controls are not collapsed")
            for label in ("Guest %", "Used GiB", "Host RSS", "Assigned", "% used", "RSS", "N/A /"):
                check(label in node_table, f"Per-node compact RAM UI is missing {label}")
            check("ram-dual-head" not in node_table, "old per-node four-link RAM header survived")

        # Writer persistence: Agent already sends these values, current cache must retain them.
        conn = appmod.db()
        try:
            appmod.refresh_fast_current_state(
                conn, "NODE-WRITER", now, 300, [], [{
                    "vm_uuid": "vm-writer",
                    "interval_seconds": 300,
                    "cpu_normalized_percent": 1.0,
                    "cpu_core_percent": 4.0,
                    "vcpu_current": 4,
                    "ram_current_kib": 262_144,
                    "ram_rss_kib": 200_000,
                    "ram_available_kib": 250_000,
                    "ram_unused_kib": 50_000,
                    "ram_usable_kib": 180_000,
                }], {}, False,
            )
            conn.commit()
            got = conn.execute(
                "SELECT ram_unused_kib,ram_usable_kib FROM vm_current_fast WHERE node=? AND vm_uuid=?",
                ("NODE-WRITER","vm-writer"),
            ).fetchone()
            check(got == (50_000,180_000), "current cache did not retain unused/usable balloon fields")
        finally:
            conn.close()

        # Current VM Abuse: RAM is an informational sortable column only.
        cfg = appmod.get_abuse_settings()
        conn = appmod.db()
        try:
            for i,(uuid,*_rest) in enumerate(records):
                conn.execute(
                    """INSERT INTO vm_abuse_state(
                         node,vm_uuid,last_seen,is_abuse,abuse_since,abuse_flags,severity,
                         disk_read_bps,disk_write_bps,disk_streak_cycles,policy_revision,engine_version
                       ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (node,uuid,now,1,now-300,"DISK_SUSTAINED",1.0+i/10,100+i,200+i,2,cfg["revision"],appmod.ABUSE_ENGINE_VERSION),
                )
            conn.commit()
        finally:
            conn.close()
        for key, first_uuid in expected.items():
            with appmod.app.test_request_context(f"/abuse/vms?sort={key}&order=desc&limit=1000"):
                rows, *_ = appmod._v48103_current_abuse_query("", key, "desc", 1000)
                check(rows and rows[0][1] == first_uuid, f"VM Abuse {key} sort is wrong")
        with appmod.app.test_request_context("/abuse/vms?sort=ram&order=asc&limit=1000"):
            asc_rows, *_ = appmod._v48103_current_abuse_query("", "ram", "asc", 1000)
            check(asc_rows and asc_rows[-1][1] == "vm-no-balloon", "VM Abuse ascending Guest% sort did not keep N/A last")
        with appmod.app.test_request_context("/abuse/vms?sort=ram&order=desc&limit=1000"):
            abuse_html = appmod._v48103_current_abuse_page("", "ram", "desc", 1000)
            check(abuse_html.count("ram-sort-menu") == 1, "VM Abuse RAM sort controls are not collapsed")
            for label in ("Guest %", "Used GiB", "Host RSS", "Assigned", "% used", "RSS"):
                check(label in abuse_html, f"VM Abuse compact RAM UI is missing {label}")
            check("RAM is <b>visibility only</b>" in abuse_html, "RAM visibility-only warning is missing")
            check("ram-dual-head" not in abuse_html, "old VM Abuse four-link RAM header survived")
            parser = TextExtractor()
            parser.feed(abuse_html)
            check("cycles" not in parser.text().lower(), "visible current VM Abuse still exposes cycles")
            check("READ" in abuse_html and "WRITE" in abuse_html, "directional disk sort regressed")

        # VM detail and charts.
        with appmod.app.test_request_context(
            f"/vm?node={node}&vm_uuid=vm-guest-pct&bridge=br0&iface=vnet-t-pct&period=5m"
        ):
            response = appmod.vm_page_v48103()
            html = response.get_data(as_text=True)
            check(response.status_code == 200, "VM detail did not render")
            check("GUEST USED" in html and "90.0% used" in html and "HOST RSS" in html and "ASSIGNED" in html, "VM detail RAM card is not guest-aware")
            check("RAM RSS / Assigned" not in html, "old ambiguous VM RAM card survived")
            check("Guest Used" in html and "Host RSS" in html, "VM RAM chart labels are wrong")

        perf_rows, *_ = appmod.query_vm_perf_chart(node, "vm-guest-pct", "1h")
        check(perf_rows and perf_rows[-1]["guest_used_bytes"] == 90_000 * 1024, "VM chart Guest Used series is wrong")
        node_rows, *_ = appmod.query_node_perf_chart(node, "1h")
        check(node_rows and node_rows[-1]["guest_stats_count"] == 4, "node chart valid guest-stat count is wrong")
        check(node_rows[-1]["guest_used_bytes"] == (90_000+200_000+100_000+50_000)*1024, "node chart Guest Used sum is wrong")
        overview = appmod.get_node_metric_overview(node, "5m")
        check(overview is not None and overview[10] == 4, "node overview valid guest-stat count is wrong")

        # v48.10.2 live-refresh and full reset primitives must remain present.
        source = app_path.read_text(encoding="utf-8")
        check("const BW_AUTO_REFRESH_MS = 5000" in source, "five-second partial refresh regressed")
        check("if (!silent) window.location.assign(requestedUrl);" in source, "silent refresh can force a full reload")
        check("preserveScroll: true" in source, "partial refresh no longer preserves scroll")
        check("def reset_all_app_data" in source, "full operational reset is missing")

    print("PASS: v48.10.4 compact guest RAM formula and N/A safety")
    print("PASS: v48.10.4 current-cache balloon persistence")
    print("PASS: v48.10.4 compact Top VM and per-node RAM sorting")
    print("PASS: v48.10.4 compact VM Abuse informational RAM sorting")
    print("PASS: v48.10.4 VM detail and aggregate RAM charts")
    print("PASS: v48.10.2 CPU/disk/live-refresh/reset features preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
