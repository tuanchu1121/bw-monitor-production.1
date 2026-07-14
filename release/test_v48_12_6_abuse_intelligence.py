#!/usr/bin/env python3
import importlib.util
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def load_module(app_path, db_path):
    os.environ['BW_MONITOR_DB'] = str(db_path)
    os.environ['BW_MONITOR_TOKEN'] = 'test-token'
    spec = importlib.util.spec_from_file_location('bw_monitor_v48126_test', app_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    if len(sys.argv) != 2:
        raise SystemExit('usage: test_v48_12_6_abuse_intelligence.py APP.py')
    app_path = Path(sys.argv[1]).resolve()
    source = app_path.read_text()
    required = [
        'V48126_VERSION = "48.12.6"',
        'ABUSE_ENGINE_VERSION = "cycles-v3-ram"',
        'CREATE TABLE IF NOT EXISTS vm_abuse_incidents',
        'RAM_SUSTAINED',
        'def vm_abuse_page_v48126',
        '/api/v1/abuse/incidents',
        '/api/v1/abuse/rankings',
        'Select all on this page',
        'bw-chart-modal',
        '_v48126_visible_sql',
    ]
    for needle in required:
        assert needle in source, f'missing marker: {needle}'

    with tempfile.TemporaryDirectory() as td:
        db_path = Path(td) / 'test.db'
        m = load_module(app_path, db_path)
        assert m.V48126_VERSION == '48.12.6'
        assert m.ABUSE_ENGINE_VERSION == 'cycles-v3-ram'
        conn = m.db()
        try:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            assert 'vm_abuse_incidents' in tables
            state_cols = {r[1] for r in conn.execute('PRAGMA table_info(vm_abuse_state)')}
            for col in ('ram_streak_cycles','ram_rss_percent','ram_guest_used_percent','ram_usable_percent'):
                assert col in state_cols, col
            event_cols = {r[1] for r in conn.execute('PRAGMA table_info(vm_abuse_events)')}
            assert 'ram_guest_used_percent' in event_cols

            cfg = m.get_abuse_settings(conn)
            assert cfg['ram_enabled'] is False
            assert cfg['ram_required_cycles'] == 2
            assert cfg['engine_version'] == 'cycles-v3-ram'

            m.refresh_fast_current_state(conn, 'RAM-CACHE', 1800000000, 300, [], [{
                'vm_uuid':'RAM-VM', 'interval_seconds':300,
                'cpu_normalized_percent':1.0, 'cpu_core_percent':4.0, 'vcpu_current':4,
                'ram_current_kib':262144, 'ram_rss_kib':200000,
                'ram_available_kib':250000, 'ram_unused_kib':50000, 'ram_usable_kib':180000,
            }], {}, False)
            conn.commit()
            ram_cache = conn.execute(
                "SELECT ram_unused_kib,ram_usable_kib FROM vm_current_fast WHERE node='RAM-CACHE' AND vm_uuid='RAM-VM'"
            ).fetchone()
            assert tuple(ram_cache) == (50000,180000), ram_cache

            # Engine migration must preserve existing Network/CPU/Disk current
            # truth and streaks, while adopting the cycles-v3 marker.
            conn.execute("""UPDATE vm_abuse_state SET is_abuse=1,abuse_since=1799999700,
                         abuse_flags='CPU_SUSTAINED',severity=1.2,cpu_streak_cycles=6,
                         cpu_streak_seconds=1800,engine_version='cycles-v2'
                         WHERE node='RAM-CACHE' AND vm_uuid='RAM-VM'""")
            conn.commit()
            m._v48126_migrate_schema()
            migrated = conn.execute("""SELECT is_abuse,abuse_flags,cpu_streak_cycles,
                                      cpu_streak_seconds,engine_version
                                      FROM vm_abuse_state
                                      WHERE node='RAM-CACHE' AND vm_uuid='RAM-VM'""").fetchone()
            assert tuple(migrated) == (1,'CPU_SUSTAINED',6,1800,'cycles-v3-ram'), migrated

            conn.execute("INSERT INTO node_inventory(node,first_seen,last_push,status,hidden_at,deleted_at) VALUES('HIDDEN',1,1,'hidden',1,NULL)")
            conn.commit()
            assert not m._v48126_is_visible(conn, 'HIDDEN', 'V1')
            assert m._v48126_is_visible(conn, 'VISIBLE', 'V2')

            state = {'node':'N1','vm_uuid':'V1','abuse_since':1000,'policy_revision':2}
            m._v48126_apply_incident_event(conn,'started',state,1000,'CPU_SUSTAINED',1.2,2,m.ABUSE_ENGINE_VERSION)
            m._v48126_apply_incident_event(conn,'updated',state,1600,'CPU_SUSTAINED,RAM_SUSTAINED',1.5,2,m.ABUSE_ENGINE_VERSION)
            m._v48126_apply_incident_event(conn,'recovered',state,4600,'CPU_SUSTAINED,RAM_SUSTAINED',1.5,2,m.ABUSE_ENGINE_VERSION)
            conn.commit()
            incident = conn.execute('SELECT status,duration_seconds,max_severity,weighted_score,event_count,abuse_flags FROM vm_abuse_incidents').fetchone()
            assert tuple(incident[:3]) == ('closed',3600,1.5)
            assert float(incident[3]) == 2.5
            assert int(incident[4]) == 3
            assert 'RAM_SUSTAINED' in incident[5]

            # A policy revision must close any open incident before streak reset.
            m._v48126_apply_incident_event(conn,'started',{'node':'N2','vm_uuid':'V2'},5000,'RAM_SUSTAINED',1.2,2,m.ABUSE_ENGINE_VERSION)
            m._v4810_reset_current_state_for_policy(conn, 3, 5600)
            conn.commit()
            policy_closed = conn.execute(
                "SELECT status,ended_at,duration_seconds FROM vm_abuse_incidents WHERE node='N2' AND vm_uuid='V2'"
            ).fetchone()
            assert tuple(policy_closed) == ('closed',5600,600), policy_closed
        finally:
            conn.close()

        assert m._v48126_ram_hit(
            {'ram_effective_enabled':True,'ram_rss_percent':95.0,'ram_guest_used_percent':95.0,'ram_low_usable_percent':5.0},
            {'rss_percent':96.0,'guest_used_percent':90.0,'usable_percent':10.0,'guest_valid':True},
        )[0]

        # Rendering smoke test. v48.12.8 keeps the v48.12.6 incident
        # engine/API but simplifies the public dashboard to Current + Events.
        with m.app.test_request_context('/abuse/vms?tab=summary'):
            renderer = getattr(m, 'vm_abuse_page_v48128', m.vm_abuse_page_v48126)
            response = renderer()
            assert response.status_code == 200
            html = response.get_data(as_text=True)
            assert 'Current Abuse' in html
            assert 'Abuse Events' in html
            assert 'RAM' in html

        with m.app.test_request_context('/admin/abuse'):
            html = m.abuse_settings_admin_card()
            assert 'name="ram_enabled"' in html
            assert 'Guest Used %' in html
            assert 'Low Usable %' in html

    print('PASS: v48.12.6 RAM abuse policy, incident intelligence, effective visibility and chart UX')


if __name__ == '__main__':
    main()
