#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: test_v48_12_3_safe_compact.py APP.py RUNNER.py")
    app_path = Path(sys.argv[1]).resolve()
    runner_path = Path(sys.argv[2]).resolve()

    app_text = app_path.read_text(encoding="utf-8")
    assert 'V48123_VERSION = "48.12.3"' in app_text
    assert 'name="action" value="delete_history"' in app_text
    assert 'Delete history only' in app_text
    assert 'only during the SQLite <code>VACUUM</code> rewrite' in app_text

    runner = load_module(runner_path, "bw_monitor_maintenance_v48123_test")
    events: list[str] = []

    runner.detect_app_service = lambda: "bw-monitor.service"
    runner.stop_service = lambda service: events.append("stop") or True
    runner._start_service_reliably = lambda service: events.append("start")
    runner.vacuum_database = lambda db: events.append("vacuum") or {
        "db_bytes_before": 100,
        "db_bytes_after": 50,
        "reclaimed_bytes": 50,
    }

    class FakeModule:
        DB = "/tmp/nonexistent-v48123-test.db"

        @staticmethod
        def delete_history_older_than(days):
            events.append(f"delete:{days}")
            return {"days": days, "total_deleted": 7}

        @staticmethod
        def clear_api_logs(kind):
            events.append(f"clear_api_logs:{kind}")
            return {"kind": kind, "deleted": 3}

        @staticmethod
        def clear_all_api_data():
            events.append("clear_api_data")
            return {"deleted": 4}

    result = runner.execute_action(FakeModule, "delete_compact", {"days": 7})
    assert events == ["delete:7", "stop", "vacuum", "start"], events
    assert result["delete"]["total_deleted"] == 7
    assert result["service_restarted"] is True

    events.clear()
    runner.execute_action(FakeModule, "clear_api_logs", {"kind": "all", "compact": False})
    assert events == ["clear_api_logs:all"], events

    events.clear()
    runner.execute_action(FakeModule, "clear_api_logs", {"kind": "requests", "compact": True})
    assert events == ["clear_api_logs:requests", "stop", "vacuum", "start"], events

    events.clear()
    runner.execute_action(FakeModule, "clear_api_data", {"compact": False})
    assert events == ["clear_api_data"], events

    print("PASS: v48.12.3 safe compact keeps deletion online and limits outage to VACUUM")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
