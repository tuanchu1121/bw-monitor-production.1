#!/usr/bin/env python3
import importlib.util
import os
import sys
import tempfile
from pathlib import Path


def load_module(app_path, db_path):
    os.environ['BW_MONITOR_DB'] = str(db_path)
    os.environ['BW_MONITOR_TOKEN'] = 'test-token'
    spec = importlib.util.spec_from_file_location('bw_monitor_v48129_test', app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: test_v48_12_9_operations_ui.py APP.py')
    app_path = Path(sys.argv[1]).resolve()
    source = app_path.read_text()
    for needle in (
        'V48129_VERSION = "48.12.9"',
        'V48129_BUILD = "r4"',
        'def _v48129_current_page',
        'REASON / SEVERITY',
        'PPS PEAK / WINDOW',
        'RX Mbps',
        'TX Mbps',
        'Guest %',
        'Used GiB',
        'Host RSS',
        'Assigned',
        'chip-network',
        'chip-cpu',
        'chip-ram',
        'chip-disk',
        'chip-time',
        'def clear_abuse_events_v48129',
        'def reset_all_abuse_data_v48129',
        'def manage_vm_abuse_data_v48129',
        'RESET ALL ABUSE DATA',
    ):
        assert needle in source, f'missing marker: {needle}'
    assert source.count('DELETE FROM vm_abuse_incidents') >= 4, 'cleanup paths are incomplete'

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / 'test.db'
        m = load_module(app_path, db_path)
        assert m.V48129_VERSION == '48.12.9'
        assert m.V48129_BUILD == 'r4'
        now = m.now_ts()
        conn = m.db()
        try:
            cfg = m.get_abuse_settings(conn)
            flags = 'NETWORK_RX_AVG_MBPS,CPU_SUSTAINED,RAM_SUSTAINED,DISK_SUSTAINED'
            conn.execute("""
              INSERT INTO vm_abuse_state(
                node,vm_uuid,last_seen,is_abuse,abuse_since,abuse_flags,severity,
                rx_mbps,tx_mbps,rx_pps,tx_pps,rx_peak_pps,tx_peak_pps,
                seconds_over_rx_pps,seconds_over_tx_pps,
                network_rx_mbps_streak_seconds,network_tx_mbps_streak_seconds,
                cpu_full_percent,cpu_core_percent,vcpu_current,cpu_streak_seconds,
                ram_streak_seconds,ram_current_kib,ram_rss_kib,ram_available_kib,ram_usable_kib,
                ram_rss_percent,ram_guest_used_percent,ram_usable_percent,
                disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops,disk_streak_seconds,
                policy_revision,engine_version
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                'NODE-A','VM-OPS-001',now,1,now-5400,flags,2.0,
                max(900.0, cfg['network_avg_mbps'] * 1.2),100.0,12000,8000,55000,25000,
                270,120,600,0,
                96.0,384.0,4,1800,
                1200,8*1024*1024,7*1024*1024,8*1024*1024,256*1024,
                87.5,96.0,3.0,
                250*1024*1024,10*1024*1024,4000,2000,900,
                cfg['revision'],m.ABUSE_ENGINE_VERSION,
            ))
            # Two closed occurrences for the grouped Events tab.
            for start, end, sev in ((now-7200, now-6300, 1.2), (now-3600, now-1800, 1.7)):
                state = {'node':'NODE-A','vm_uuid':'VM-OPS-001','abuse_since':start,'policy_revision':cfg['revision']}
                m._v48126_apply_incident_event(conn, 'started', state, start, flags, sev, cfg['revision'], m.ABUSE_ENGINE_VERSION)
                m._v48126_apply_incident_event(conn, 'recovered', state, end, flags, sev, cfg['revision'], m.ABUSE_ENGINE_VERSION)
            conn.commit()
        finally:
            conn.close()

        with m.app.test_request_context('/abuse/vms?tab=current&sort=tx_mbps&order=desc'):
            response = m.vm_abuse_page_v48129()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            for marker in (
                'REASON / SEVERITY', 'NETWORK AVG', 'RX Mbps', 'TX Mbps ↓',
                'PPS PEAK / WINDOW', 'RX PPS', 'TX PPS',
                'Full %', 'Core %', 'Guest %', 'Used GiB', 'Host RSS', 'Assigned',
                'Read', 'Write', 'Read IOPS', 'Write IOPS',
                'resource-meter', 'cpu-core-value', 'ram-used-value', 'min sustained', 'RSS ', 'chip-network', 'chip-cpu', 'chip-ram', 'chip-disk',
                'metric-abuse-time-network', 'metric-abuse-time-cpu', 'metric-abuse-time-ram', 'metric-abuse-time-disk',
                'Abusing 1h 30m', 'Copy UUID',
            ):
                assert marker in html, f'Current Abuse missing {marker}'
            assert 'PPS AVG' not in html, 'old extra PPS AVG column is still visible'
            assert 'MAX RATIO</th>' not in html, 'ratio should stay inside REASON / SEVERITY'
            reason_html = m._v48129_reason_cell({
                'abuse_flags': flags, 'severity': 2.0,
                'rx_mbps': max(900.0, cfg['network_avg_mbps'] * 1.2),
                'cpu_full_percent': 96.0, 'ram_guest_used_percent': 96.0,
                'ram_rss_percent': 87.5, 'ram_usable_percent': 3.0,
                'disk_read_bps': 250*1024*1024, 'disk_write_bps': 10*1024*1024,
                'disk_read_iops': 4000, 'disk_write_iops': 2000,
            }, cfg, now-5400)
            assert 'Abusing ' not in reason_html, 'duration must not be inside REASON / SEVERITY'
            assert 'MAX:' not in reason_html, 'compact reason cell must not show ratio formula text'
            cpu_stat = m._v48129_vm_detail_cpu_stat(330.0, 4)
            assert '82.5% full' in cpu_stat and '330.0% core · 4 vCPU' in cpu_stat
            assert 'vm-detail-cpu-meter' in cpu_stat

        with m.app.test_request_context('/abuse/vms?tab=events&sort=duration&order=desc&range=7d'):
            response = m.vm_abuse_page_v48129()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            for marker in ('Abuse Events by VM', 'TOTAL MINUTES ↓', 'LONGEST MINUTES', 'View 2 occurrences', 'Copy UUID', 'DURATION / MINUTES', 'chip-time'):
                assert marker in html, f'Abuse Events missing {marker}'

        # All History cleanup must clear raw + incidents but preserve Current Abuse.
        conn = m.db()
        try:
            cfg = m.get_abuse_settings(conn)
            state = {'node':'NODE-B','vm_uuid':'VM-HISTORY','abuse_since':now-600,'policy_revision':cfg['revision'], 'abuse_flags':'CPU_SUSTAINED', 'severity':1.1}
            m._v48126_insert_abuse_event(conn, 'started', state, now-600, flags='CPU_SUSTAINED', severity=1.1, cfg=cfg)
            m._v48126_insert_abuse_event(conn, 'recovered', state, now, flags='CPU_SUSTAINED', severity=1.1, cfg=cfg)
            conn.commit()
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_events').fetchone()[0] > 0
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_incidents').fetchone()[0] > 0
        finally:
            conn.close()
        m.require_admin = lambda: None
        m.dashboard_username = lambda: 'admin'
        m.get_admin_username = lambda: 'admin'
        m.log_account_event = lambda *a, **k: None
        with m.app.test_request_context('/admin/abuse-clear', method='POST', data={'mode':'all','confirm_text':'CLEAR ALL ABUSE LOGS'}):
            response = m.clear_abuse_events_v48129()
            assert response.status_code == 302
        conn = m.db()
        try:
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_events').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_incidents').fetchone()[0] == 0
            assert conn.execute("SELECT COUNT(*) FROM vm_abuse_state WHERE node='NODE-A' AND vm_uuid='VM-OPS-001'").fetchone()[0] == 1
        finally:
            conn.close()

        # Explicit reset-all must clear all three Abuse datasets only.
        conn = m.db()
        try:
            cfg = m.get_abuse_settings(conn)
            state = {'node':'NODE-C','vm_uuid':'VM-RESET','abuse_since':now-300,'policy_revision':cfg['revision'], 'abuse_flags':'CPU_SUSTAINED', 'severity':1.2}
            m._v48126_insert_abuse_event(conn, 'started', state, now-300, flags='CPU_SUSTAINED', severity=1.2, cfg=cfg)
            conn.commit()
        finally:
            conn.close()
        with m.app.test_request_context('/admin/abuse-data/reset-all-v48129', method='POST', data={'confirm_text':'RESET ALL ABUSE DATA'}):
            response = m.reset_all_abuse_data_v48129()
            assert response.status_code == 302
        conn = m.db()
        try:
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_events').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_incidents').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_state').fetchone()[0] == 0
        finally:
            conn.close()

    print('PASS: v48.12.9-r4 compact Abuse layout, metric-local duration, VM CPU Full meter, grouped Events, and complete cleanup')


if __name__ == '__main__':
    main()
