#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import sys
import tempfile


def load_module(path: str):
    tmp = tempfile.TemporaryDirectory(prefix="bw-monitor-v48105-test-")
    os.environ["BW_MONITOR_DB"] = str(pathlib.Path(tmp.name) / "test.db")
    os.environ.setdefault("BW_MONITOR_TOKEN", "test-token")
    spec = importlib.util.spec_from_file_location("bw_monitor_v48105_test", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load app")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tmp, module


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(f"Usage: {sys.argv[0]} APP.py")
    tmp, m = load_module(sys.argv[1])
    try:
        require(getattr(m, "V48105_VERSION", "") == "48.10.5", "missing v48.10.5 marker")

        with m.app.test_request_context("/login"):
            login = m._v48105_login_document("/", "", "", "")
        for required in ("login-topbar", "login-card-pro", "Operations Console", "Authorized access only", "Sign in"):
            require(required in login, f"login missing {required}")
        for forbidden in ("class=\"main-nav\"", ">Dashboard<", ">Top VM<", ">VM Abuse<", ">Node Health<", "Green@1234", "default login credentials"):
            require(forbidden not in login, f"login leaked dashboard/default content: {forbidden}")
        print("PASS: dedicated professional login without dashboard navigation/default credentials")

        cpu = m._v48105_cpu_usage_block(799.5, 88.8, 9, "10/15 min sustained", compact=True)
        for required in ("799.5%", "88.8% full", "cpu-meter", "width:88.8%", "9 vCPU", "10/15 min sustained"):
            require(required in cpu, f"CPU block missing {required}")
        print("PASS: reusable CPU meter block")

        row = (
            "6506500549", "c2588e5b-2a5b-498d-a0f9-936674084ee9",
            344_690_000, 330_520_000, 675_210_000,
            1000, 1000, 2000, 0, 0,
            18.88, 35.03, 1690.0, 2670.0,
            20, 20, 15, 0, 0, 0,
            3.3, 6, 20.0,
            5_700_000, 11_000_000,
            0.0, 113_980.0,
            "active", 1_783_640_000, 1_783_640_000, 300,
            11_000_000, 6_900_000, 7_050_000,
        )
        with m.app.test_request_context("/node/TEST?period=5m"):
            table = m.interface_table("Public", "br0", "TEST", [row], "5m")
        require("table-vm-polished" in table, "node VM table missing polished class")
        require("cpu-meter" in table and "20.0%" in table and "3.3% full" in table, "node VM table missing CPU meter values")
        print("PASS: node VM table CPU meter and polished layout")

        cfg = m.get_abuse_settings()
        fake = [
            "TEST", "c2588e5b-2a5b-498d-a0f9-936674084ee9",
            1_783_640_000, 1_783_639_000, "CPU_SUSTAINED,DISK_SUSTAINED", 2.5,
            100.0, 200.0, 3000.0, 4000.0, 0, 0,
            88.8, 799.5, 9, 600,
            100_000.0, 200_000.0, 20.0, 30.0, 600,
            "96.9.213.241", 10.0, 20.0, 300, 300, 2, 2, 1, 1, 1, 0, cfg["revision"],
            11_000_000, 9_000_000, 11_000_000, 1_000_000, 1_500_000,
        ]
        old_query = m._v48103_current_abuse_query
        m._v48103_current_abuse_query = lambda q, s, o, l: ([tuple(fake)], 1, (0, 0, 1, 1), s, o, cfg)
        try:
            with m.app.test_request_context("/abuse/vms?tab=current"):
                abuse = m._v48103_current_abuse_page("", "severity", "desc", 200)
        finally:
            m._v48103_current_abuse_query = old_query
        require("abuse-v48105-table" in abuse, "abuse table missing polished class")
        require("799.5%" in abuse and "88.8% full" in abuse and "cpu-meter" in abuse, "abuse table missing CPU meter")
        print("PASS: VM Abuse CPU meter and balanced table")

        css = m.V48105_UI_CSS
        for required in ("--v5-text", "#d9e5f3", "table-vm-polished", "min-width:1780px", "cpu-usage-block"):
            require(required in css, f"UI CSS missing {required}")
        print("PASS: light/dark contrast and balanced width layer")

        require(getattr(m, "V48106_VERSION", "") == "48.10.6", "missing v48.10.6 marker")
        require(m.app.view_functions["dashboard_login"].__name__ == "dashboard_login_v48106", "dashboard login override missing")
        require(m.app.view_functions["admin_login"].__name__ == "admin_login_v48106", "admin login override missing")
        require(m.app.view_functions["admin_setup"].__name__ == "admin_setup_v48106", "admin setup override missing")
        with m.app.test_request_context("/login"):
            password = m._v48106_password_field("login-password", "password", "Password", "current-password")
            login6 = m._v48106_login_document(
                action="/login", title="Welcome back", subtitle="Secure operations access",
                username_value="", next_url="/", extra_fields=password,
            )
        for required in ("data-target=\"login-password\"", "bindPasswordToggles", "Operations Console", "Authorized access only"):
            require(required in login6, f"v48.10.6 login missing {required}")
        require('class="main-nav"' not in login6, "v48.10.6 login leaked dashboard navigation")
        css6 = m.V48106_UI_CSS
        for required in ("#10243a", "count-badges > span", "overview-meta > span", "background:#07111b", "border-color:#2b4260"):
            require(required in css6, f"v48.10.6 dark UI missing {required}")
        print("PASS: admin login parity, password toggle and darker dark-mode chips")

        print("v48.10.6 UI regression: PASS")
    finally:
        tmp.cleanup()


if __name__ == "__main__":
    main()
