#!/usr/bin/env python3
"""Synthetic regression tests for BW Monitor v48.10.0 abuse engine.

Runs against a temporary SQLite database. It does not touch the production DB.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import tempfile


def load_app(path: Path, db_path: Path):
    os.environ["BW_MONITOR_DB"] = str(db_path)
    os.environ.setdefault("BW_MONITOR_TOKEN", "self-test-token")
    spec = importlib.util.spec_from_file_location("bw_monitor_v4810_test", str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_payload(cfg, *, rx_mbps=0.0, tx_mbps=0.0, over_rx=0, over_tx=0,
                 reported=None, cpu=0.0, read_mibps=0.0, write_mibps=0.0,
                 iops=0.0, vm_uuid="vm-test"):
    sec = 300
    reported = cfg["network_pps"] if reported is None else reported
    interface = {
        "vm_uuid": vm_uuid,
        "bridge": "br0",
        "iface": "vnet0",
        "interval_seconds": sec,
        "rx_delta": int(rx_mbps * 1_000_000 / 8 * sec),
        "tx_delta": int(tx_mbps * 1_000_000 / 8 * sec),
        "rx_packets_delta": int((cfg["network_pps"] + 10_000) * sec) if over_rx else 0,
        "tx_packets_delta": int((cfg["network_pps"] + 10_000) * sec) if over_tx else 0,
        "rx_pps_peak": cfg["network_pps"] + 50_000 if over_rx else 0,
        "tx_pps_peak": cfg["network_pps"] + 50_000 if over_tx else 0,
        "seconds_over_rx_pps": int(over_rx),
        "seconds_over_tx_pps": int(over_tx),
        "pps_warn_threshold": float(reported),
        "network_sample_count": 20,
        "network_sample_expected": 20,
        "network_sample_quality": "GOOD",
    }
    vm = {
        "vm_uuid": vm_uuid,
        "interval_seconds": sec,
        "cpu_normalized_percent": float(cpu),
        "cpu_core_percent": float(cpu) * 4,
        "vcpu_current": 4,
        "disk_read_delta": int(read_mibps * 1024 * 1024 * sec),
        "disk_write_delta": int(write_mibps * 1024 * 1024 * sec),
        "disk_read_reqs_delta": int(iops * sec),
        "disk_write_reqs_delta": 0,
    }
    return interface, vm


def push(module, node, ts, cfg, **kwargs):
    interface, vm = make_payload(cfg, **kwargs)
    conn = module.db()
    try:
        module.refresh_fast_current_state(
            conn, node, ts, 300, [interface], [vm], {}, False
        )
        conn.commit()
        return conn.execute("""
            SELECT is_abuse,abuse_flags,policy_revision,
                   cpu_streak_cycles,disk_streak_cycles,
                   network_rx_mbps_streak_cycles,network_tx_mbps_streak_cycles,
                   network_pps_policy_synced,seconds_over_rx_pps,seconds_over_tx_pps
            FROM vm_abuse_state WHERE node=? AND vm_uuid='vm-test'
        """, (node,)).fetchone()
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("app", nargs="?", default="bw_monitor_app_v48_10_0_policy_engine.py")
    args = parser.parse_args()
    app_path = Path(args.app).resolve()
    if not app_path.is_file():
        raise SystemExit(f"App file not found: {app_path}")

    with tempfile.TemporaryDirectory(prefix="bw-monitor-v4810-test-") as tmp:
        module = load_app(app_path, Path(tmp) / "test.db")
        assert module.V4810_VERSION == "48.10.0"
        assert module.ABUSE_ENGINE_VERSION in {"cycles-v2", "cycles-v3-ram"}

        defaults = dict(module.ABUSE_SETTING_DEFAULTS)

        # CPU: 30 minutes is exactly six complete 5-minute cycles even when
        # original agent intervals would have been 297-299 seconds.
        values = dict(defaults)
        values.update({
            "abuse_network_enabled": "0",
            "abuse_network_mbps_enabled": "0",
            "abuse_disk_enabled": "0",
            "abuse_cpu_enabled": "1",
            "abuse_cpu_full_percent": "90",
            "abuse_cpu_required_seconds": "1800",
        })
        cfg = module._v4810_save_policy(values, "self-test", "cpu")
        base = 1_800_000_000
        for cycle in range(1, 7):
            row = push(module, "node-cpu", base + cycle * 300, cfg, cpu=95)
            assert row[3] == cycle, row
            assert row[0] == (1 if cycle == 6 else 0), row
        assert "CPU_SUSTAINED" in row[1], row

        # Policy changes reset current streaks and create a new revision.
        old_revision = cfg["revision"]
        values["abuse_cpu_full_percent"] = "99"
        cfg = module._v4810_save_policy(values, "self-test", "policy-reset")
        assert cfg["revision"] == old_revision + 1
        conn = module.db()
        try:
            state = conn.execute("""
                SELECT is_abuse,cpu_streak_cycles,abuse_flags,policy_revision
                FROM vm_abuse_state WHERE node='node-cpu' AND vm_uuid='vm-test'
            """).fetchone()
        finally:
            conn.close()
        assert state == (0, 0, "", cfg["revision"]), state

        # PPS: timers collected under the old threshold must not trigger.
        values = dict(defaults)
        values.update({
            "abuse_network_enabled": "1",
            "abuse_network_pps": "250000",
            "abuse_network_required_seconds": "270",
            "abuse_network_mbps_enabled": "0",
            "abuse_cpu_enabled": "0",
            "abuse_disk_enabled": "0",
        })
        cfg = module._v4810_save_policy(values, "self-test", "pps")
        row = push(module, "node-pps", base + 300, cfg, over_rx=285, reported=200000)
        assert row[0] == 0 and row[7] == 0 and row[8] == 0, row
        row = push(module, "node-pps", base + 600, cfg, over_rx=285, reported=250000)
        assert row[0] == 1 and "NETWORK_RX_PPS" in row[1] and row[7] == 1, row

        # AVG Mbps: one configured 5-minute cycle applies on the first complete
        # push and is directional.
        values.update({
            "abuse_network_enabled": "0",
            "abuse_network_mbps_enabled": "1",
            "abuse_network_avg_mbps": "800",
            "abuse_network_mbps_required_seconds": "300",
        })
        cfg = module._v4810_save_policy(values, "self-test", "mbps")
        row = push(module, "node-mbps", base + 300, cfg, rx_mbps=850)
        assert row[0] == 1 and "NETWORK_RX_AVG_MBPS" in row[1] and row[5] == 1, row

        # Disk: 15 minutes is exactly three complete cycles.
        values.update({
            "abuse_network_mbps_enabled": "0",
            "abuse_disk_enabled": "1",
            "abuse_disk_bps": str(200 * 1024 * 1024),
            "abuse_disk_iops": "0",
            "abuse_disk_required_seconds": "900",
        })
        cfg = module._v4810_save_policy(values, "self-test", "disk")
        for cycle in range(1, 4):
            row = push(module, "node-disk", base + cycle * 300, cfg, read_mibps=210)
            assert row[4] == cycle, row
            assert row[0] == (1 if cycle == 3 else 0), row
        assert "DISK_SUSTAINED" in row[1], row

        # Same-bucket duplicate-like evaluation must not add another cycle.
        row2 = push(module, "node-disk", base + 3 * 300 + 30, cfg, read_mibps=210)
        assert row2[4] == 3, row2

        # Event and policy audit persistence.
        conn = module.db()
        try:
            events = conn.execute("SELECT event_type,abuse_flags,policy_revision FROM vm_abuse_events").fetchall()
            versions = conn.execute("SELECT revision,action FROM abuse_policy_versions").fetchall()
        finally:
            conn.close()
        assert any(e[0] == "started" and "CPU_SUSTAINED" in e[1] for e in events)
        assert any(e[0] == "started" and "NETWORK_RX_PPS" in e[1] for e in events)
        assert any(e[0] == "started" and "NETWORK_RX_AVG_MBPS" in e[1] for e in events)
        assert any(e[0] == "started" and "DISK_SUSTAINED" in e[1] for e in events)
        assert len(versions) >= 5

        # Render the current viewer and policy card to catch template/index bugs.
        with module.app.test_request_context("/abuse/vms"):
            response = module.app.view_functions["vm_abuse_page"]()
            html = response.get_data(as_text=True)
            assert response.status_code == 200
            assert "Policy" in html and module.ABUSE_ENGINE_VERSION in html
        with module.app.test_request_context("/admin/abuse"):
            card = module.abuse_settings_admin_card()
            assert "Save & Apply New Revision" in card
            assert "Rule engine progress" in card

    print("v48.10.0 abuse engine self-test: PASS")
    print("- dynamic policy revision: PASS")
    print("- exact CPU cycles: PASS")
    print("- PPS threshold synchronization: PASS")
    print("- directional AVG Mbps: PASS")
    print("- disk sustained cycles: PASS")
    print("- event/policy audit: PASS")
    print("- viewer/admin rendering: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
