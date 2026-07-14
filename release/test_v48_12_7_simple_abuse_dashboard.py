#!/usr/bin/env python3
import importlib.util
import os
import sys
import tempfile
from pathlib import Path


def load_module(app_path, db_path):
    os.environ['BW_MONITOR_DB'] = str(db_path)
    os.environ['BW_MONITOR_TOKEN'] = 'test-token'
    spec = importlib.util.spec_from_file_location('bw_monitor_v48127_test', app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: test_v48_12_7_simple_abuse_dashboard.py APP.py')
    app_path = Path(sys.argv[1]).resolve()
    source = app_path.read_text()
    for needle in (
        'V48127_VERSION = "48.12.7"',
        'def vm_abuse_page_v48127',
        'Current Abuse',
        'Abuse Events',
        'ABUSE COUNT',
        'View {safe_int(occurrences,0)} occurrence',
        'data-event-toggle',
        'Copy UUID',
    ):
        assert needle in source, f'missing marker: {needle}'

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / 'test.db'
        m = load_module(app_path, db_path)
        assert m.V48127_VERSION == '48.12.7'
        now = m.now_ts()
        conn = m.db()
        try:
            cfg = m.get_abuse_settings(conn)
            conn.execute("""
              INSERT INTO vm_abuse_state(
                node,vm_uuid,last_seen,is_abuse,abuse_since,abuse_flags,severity,
                cpu_full_percent,cpu_core_percent,vcpu_current,
                policy_revision,engine_version
              ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """, ('N1','VM-AAA',now,1,now-1200,'CPU_SUSTAINED',1.25,96.0,384.0,4,cfg['revision'],m.ABUSE_ENGINE_VERSION))
            # Three separate Abuse occurrences for the same VM.
            for start, end, severity, flags in (
                (now-20000, now-19000, 1.1, 'CPU_SUSTAINED'),
                (now-12000, now-9000, 1.3, 'CPU_SUSTAINED,RAM_SUSTAINED'),
                (now-4000, now-1000, 1.5, 'DISK_SUSTAINED'),
            ):
                state = {'node':'N1','vm_uuid':'VM-AAA','abuse_since':start,'policy_revision':cfg['revision']}
                m._v48126_apply_incident_event(conn, 'started', state, start, flags, severity, cfg['revision'], m.ABUSE_ENGINE_VERSION)
                m._v48126_apply_incident_event(conn, 'recovered', state, end, flags, severity, cfg['revision'], m.ABUSE_ENGINE_VERSION)
            conn.commit()
        finally:
            conn.close()

        with m.app.test_request_context('/abuse/vms?tab=current&sort=cpu&order=desc'):
            response = m.vm_abuse_page_v48127()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'Current Abuse' in html
            assert 'Abuse Events' in html
            assert 'REASON / SEVERITY' in html
            assert 'CPU ↓' in html
            assert 'data-copy="VM-AAA"' in html
            assert 'Summary</a>' not in html
            assert 'Raw Events</a>' not in html

        # Legacy dashboard links map to the simplified Abuse Events tab.
        with m.app.test_request_context('/abuse/vms?tab=summary&range=7d&sort=occurrences&order=desc'):
            response = m.vm_abuse_page_v48127()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'Abuse Events by VM' in html
            assert '3 times' in html
            assert 'View 3 occurrences' in html
            assert html.count('RECOVERED') >= 3
            assert 'TOTAL DURATION' in html
            assert 'MAX SEVERITY' in html
            assert 'data-copy="VM-AAA"' in html
            assert 'VM Abuse Ranking' not in html
            assert 'Raw Abuse Events' not in html

    print('PASS: v48.12.7 simplified Current Abuse and grouped Abuse Events dashboard')


if __name__ == '__main__':
    main()
