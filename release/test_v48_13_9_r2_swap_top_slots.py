#!/usr/bin/env python3
"""Focused regression for active swap inventory and Top VM SLOTS sorting."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys


def check(value, message):
    if not value:
        raise AssertionError(message)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} APP.py AGENT.py", file=sys.stderr)
        return 2
    app_path = Path(sys.argv[1]).resolve()
    agent_path = Path(sys.argv[2]).resolve()
    app_source = app_path.read_text(encoding="utf-8")
    agent_source = agent_path.read_text(encoding="utf-8")
    check('V48139_BUILD = "r2"' in app_source, "r2 application marker missing")
    check('_v48133_disk_sort_link("SLOTS", "diskcount"' in app_source, "Top VM SLOTS sort missing")
    check('def collect_swap_filesystems()' in agent_source, "swap collector missing")
    check('filesystems.extend(collect_swap_filesystems())' in agent_source, "swap inventory is not attached to node storage")

    agent = load(agent_path, "bwagent_v48139r2_test")
    real_path = agent.Path

    class FakeProcPath:
        def __init__(self, value):
            self.value = str(value)
        def read_text(self, *args, **kwargs):
            if self.value == "/proc/swaps":
                return "Filename\tType\tSize\tUsed\tPriority\n/dev/md127 partition 67107836 1048576 -2\n"
            return real_path(self.value).read_text(*args, **kwargs)

    agent.Path = FakeProcPath
    rows = agent.collect_swap_filesystems()
    check(len(rows) == 1, "expected one active swap row")
    row = rows[0]
    check(row["mount"] == "SWAP", "swap row label is wrong")
    check(row["device"] == "/dev/md127", "swap source is wrong")
    check(row["fstype"] == "swap", "swap fstype is wrong")
    check(row["size"] == 67107836 * 1024, "swap size conversion is wrong")
    check(row["used"] == 1048576 * 1024, "swap used conversion is wrong")
    check(row["avail"] == row["size"] - row["used"], "swap available bytes are wrong")
    check(row["use_percent"] > 0, "swap percent should be positive")
    print("PASS: active swap is exported as node storage and Top VM exposes SLOTS sorting")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
