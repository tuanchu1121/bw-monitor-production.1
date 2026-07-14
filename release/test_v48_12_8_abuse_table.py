#!/usr/bin/env python3
import importlib.util
import os
import sys
import tempfile
from pathlib import Path


def load_module(app_path, db_path):
    os.environ['BW_MONITOR_DB'] = str(db_path)
    os.environ['BW_MONITOR_TOKEN'] = 'test-token'
    spec = importlib.util.spec_from_file_location('bw_monitor_v48128_test', app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: test_v48_12_8_abuse_table.py APP.py')
    app_path = Path(sys.argv[1]).resolve()
    source = app_path.read_text()
    for needle in (
        'V48128_VERSION = "48.12.8"',
        'def _v48128_current_page',
        'MAX RATIO',
        'PPS AVG',
        'PPS PEAK',
        'TOTAL MINUTES',
        'LONGEST MINUTES',
        'def clear_abuse_events_v48128',
        'def clear_vm_abuse_data_v48128',
        'Low-usable RAM uses a bounded 1.00x–2.00x inverse scale',
    ):
        assert needle in source, f'missing marker: {needle}'

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / 'test.db'
        m = load_module(app_path, db_path)
        assert m.V48128_VERSION == '48.12.8'
        assert abs(m._v48128_low_usable_ratio(5, 0) - 2.0) < 0.0001
        assert abs(m._v48128_low_usable_ratio(5, 2.5) - 1.5) < 0.0001
        assert abs(m._v48128_low_usable_ratio(5, 5) - 1.0) < 0.0001

        now = m.now_ts()
        conn = m.db()
        try:
            # Enable a simple RAM rule for transparent ratio rendering.
            for key, value in {
                'abuse_ram_enabled': '1',
                'abuse_ram_rss_percent': '95',
                'abuse_ram_guest_used_percent': '90',
                'abuse_ram_low_usable_percent': '5',
                'abuse_ram_required_seconds': '600',
            }.items():
                conn.execute("INSERT INTO admin_settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (key, value, now))
            conn.commit()
            cfg = m.get_abuse_settings(conn)
            conn.execute("""
              INSERT INTO vm_abuse_state(
                node,vm_uuid,last_seen,is_abuse,abuse_since,abuse_flags,severity,
                ram_streak_seconds,ram_current_kib,ram_rss_kib,ram_available_kib,ram_usable_kib,
                ram_rss_percent,ram_guest_used_percent,ram_usable_percent,
                policy_revision,engine_version
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, ('N1','VM-AAA',now,1,now-1800,'RAM_SUSTAINED',50.0,1800,
                  8*1024*1024,8*1024*1024,8*1024*1024,0,100.0,100.0,0.0,
                  cfg['revision'],m.ABUSE_ENGINE_VERSION))
            # Two separate incident rows for minute display and sorting.
            for start, end, sev in ((now-7200, now-5400, 1.2), (now-3600, now-1800, 1.5)):
                state = {'node':'N1','vm_uuid':'VM-AAA','abuse_since':start,'policy_revision':cfg['revision']}
                m._v48126_apply_incident_event(conn, 'started', state, start, 'RAM_SUSTAINED', sev, cfg['revision'], m.ABUSE_ENGINE_VERSION)
                m._v48126_apply_incident_event(conn, 'recovered', state, end, 'RAM_SUSTAINED', sev, cfg['revision'], m.ABUSE_ENGINE_VERSION)
            conn.commit()
        finally:
            conn.close()

        with m.app.test_request_context('/abuse/vms?tab=current&sort=ramrss&order=desc'):
            response = m.vm_abuse_page_v48128()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'MAX RATIO' in html
            assert 'PPS AVG' in html and 'PPS PEAK' in html
            assert 'Host RSS ↓' in html
            assert 'RAM Low Usable: usable 0.00% vs low threshold 5.00%' in html
            assert '50.00x' not in html
            assert '2.00x' in html

        with m.app.test_request_context('/abuse/vms?tab=events&sort=duration&order=desc&range=7d'):
            response = m.vm_abuse_page_v48128()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'TOTAL MINUTES ↓' in html
            assert 'LONGEST MINUTES' in html
            assert '60 min' in html
            assert 'View 2 occurrences' in html
            assert 'Sort: Total minutes' in html

        # Admin deletion must synchronize raw events and grouped incidents.
        conn = m.db()
        try:
            cfg = m.get_abuse_settings(conn)
            state = {'node':'N2','vm_uuid':'VM-BBB','abuse_since':now-600,'policy_revision':cfg['revision'], 'abuse_flags':'CPU_SUSTAINED', 'severity':1.1}
            m._v48126_insert_abuse_event(conn, 'started', state, now-600, flags='CPU_SUSTAINED', severity=1.1, cfg=cfg)
            m._v48126_insert_abuse_event(conn, 'recovered', state, now, flags='CPU_SUSTAINED', severity=1.1, cfg=cfg)
            conn.commit()
            assert conn.execute("SELECT COUNT(*) FROM vm_abuse_incidents WHERE node='N2' AND vm_uuid='VM-BBB'").fetchone()[0] >= 1
        finally:
            conn.close()
        m.require_admin = lambda: None
        m.dashboard_username = lambda: 'admin'
        m.get_admin_username = lambda: 'admin'
        m.log_account_event = lambda *a, **k: None
        with m.app.test_request_context('/admin/abuse-clear', method='POST', data={'mode':'all','confirm_text':'CLEAR ALL ABUSE LOGS'}):
            response = m.clear_abuse_events_v48128()
            assert response.status_code == 302
        conn = m.db()
        try:
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_events').fetchone()[0] == 0
            assert conn.execute('SELECT COUNT(*) FROM vm_abuse_incidents').fetchone()[0] == 0
        finally:
            conn.close()

    print('PASS: v48.12.8 Top-VM-style Abuse sorting, bounded ratio, exact minutes, and synchronized cleanup')


if __name__ == '__main__':
    main()
