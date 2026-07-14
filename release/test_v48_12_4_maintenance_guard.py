#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from types import SimpleNamespace


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    import sys
    if len(sys.argv) != 4:
        raise SystemExit('usage: test APP.py RUNNER.py SERVICE')
    app_path = Path(sys.argv[1]).resolve()
    runner_path = Path(sys.argv[2]).resolve()
    service_path = Path(sys.argv[3]).resolve()

    app_text = app_path.read_text(encoding='utf-8')
    runner_text = runner_path.read_text(encoding='utf-8')
    service_text = service_path.read_text(encoding='utf-8')
    assert 'V48124_VERSION = "48.12.4"' in app_text
    assert 'MAX_ACTIVE_MAINTENANCE_JOBS = 1' in app_text
    assert 'Only one job is allowed' in app_text
    assert 'BW_MAX_PURGE_SELECTION_ITEMS' in app_text
    assert 'LOCK_EX | fcntl.LOCK_NB' in runner_text
    assert 'MAX_SELECTION_ITEMS' in runner_text
    assert 'Not enough free disk space for safe VACUUM' in runner_text
    assert 'ExecStopPost=' in service_text
    assert 'TimeoutStartSec=6h' in service_text
    assert 'TimeoutStartSec=infinity' not in service_text

    with tempfile.TemporaryDirectory(prefix='bwm-v48124-') as tmp:
        os.environ['BW_MONITOR_DB'] = str(Path(tmp) / 'app.db')
        os.environ.setdefault('BW_MONITOR_TOKEN', 'test-token')
        app = load(app_path, 'bw_monitor_app_v48124_test')
        assert app.MAX_ACTIVE_MAINTENANCE_JOBS == 1
        assert app.app.view_functions['admin_delete_node'].__name__ == 'admin_delete_node_v48124'
        assert app.app.view_functions['admin_delete_vm'].__name__ == 'admin_delete_vm_v48124'
        assert app.app.view_functions['admin_restore_node'].__name__ == 'admin_restore_node_v48124'
        assert app.app.view_functions['admin_restore_vm'].__name__ == 'admin_restore_vm_v48124'
        assert app.app.view_functions['admin_bulk_nodes'].__name__ == 'admin_bulk_nodes_v48124'
        assert app.app.view_functions['admin_bulk_vms'].__name__ == 'admin_bulk_vms_v48124'
        assert 'v48124-submit-once' in app.V48124_UI_JS
        app._v48124_maintenance_runner_paths = lambda: '/bin/true'
        app.subprocess.run = lambda *a, **k: SimpleNamespace(returncode=0, stdout='')

        first_id, _ = app.enqueue_maintenance_job('checkpoint', {}, 'tester')
        try:
            app.enqueue_maintenance_job('checkpoint', {}, 'tester')
        except RuntimeError as exc:
            assert f'job #{first_id}' in str(exc).lower()
        else:
            raise AssertionError('second active maintenance job was accepted')

        conn = app.db()
        try:
            conn.execute("UPDATE maintenance_jobs SET status='error',finished_at=? WHERE id=?", (app.now_ts(), first_id))
            conn.commit()
        finally:
            conn.close()

        jobs = app.enqueue_batched_purge_jobs('purge_nodes', [f'node-{i}' for i in range(10)], 'tester')
        assert len(jobs) == 1 and jobs[0][2] == 10, jobs
        conn = app.db()
        try:
            row = conn.execute('SELECT parameters FROM maintenance_jobs WHERE id=?', (jobs[0][0],)).fetchone()
            params = json.loads(row[0])
            assert len(params['nodes']) == 10
            assert params['batch_size'] == app.MAX_PURGE_ITEMS_PER_JOB
        finally:
            conn.close()

    runner = load(runner_path, 'bw_monitor_runner_v48124_test')
    with tempfile.TemporaryDirectory(prefix='bwm-v48124-runner-') as tmp:
        runner.LOCK_PATH = Path(tmp) / 'maintenance.lock'
        h1 = runner.acquire_lock()
        try:
            try:
                runner.acquire_lock()
            except RuntimeError as exc:
                assert 'already owns' in str(exc)
            else:
                raise AssertionError('duplicate worker acquired lock')
        finally:
            import fcntl
            fcntl.flock(h1.fileno(), fcntl.LOCK_UN)
            h1.close()

        db_path = str(Path(tmp) / 'runner.db')
        conn = sqlite3.connect(db_path)
        conn.execute('CREATE TABLE maintenance_jobs(id INTEGER PRIMARY KEY,status TEXT,message TEXT,started_at INTEGER,finished_at INTEGER)')
        conn.execute("INSERT INTO maintenance_jobs(id,status,message) VALUES(1,'running','')")
        conn.commit(); conn.close()
        seen: list[str] = []

        class FakeModule:
            DB = db_path
            MAX_PURGE_ITEMS_PER_JOB = 3
            @staticmethod
            def db():
                return sqlite3.connect(db_path, timeout=5)
            @staticmethod
            def purge_node_data(conn, node):
                seen.append(node)
                return {'rows': 1}

        result = runner._transactional_purge(
            FakeModule, 'purge_nodes',
            {'nodes': [f'n{i}' for i in range(8)], 'batch_size': 3, '_job_id': 1},
        )
        assert result['count'] == 8
        assert seen == [f'n{i}' for i in range(8)]

        old_usage = runner.shutil.disk_usage
        runner.shutil.disk_usage = lambda path: SimpleNamespace(total=1000, used=999, free=1)
        old_reserve = runner.VACUUM_FREE_RESERVE
        runner.VACUUM_FREE_RESERVE = 64
        test_db = Path(tmp) / 'large.db'
        test_db.write_bytes(b'x' * 128)
        try:
            try:
                runner.vacuum_database(str(test_db))
            except RuntimeError as exc:
                assert 'Not enough free disk space' in str(exc)
            else:
                raise AssertionError('unsafe VACUUM was not rejected')
        finally:
            runner.shutil.disk_usage = old_usage
            runner.VACUUM_FREE_RESERVE = old_reserve

    print('PASS: v48.12.4 single-worker guard, one-job bulk purge, lock fail-fast, VACUUM safety')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
