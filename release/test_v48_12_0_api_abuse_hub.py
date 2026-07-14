#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import re
import sys
import tempfile
import time

APP_PATH = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "bw_monitor_app_v48_12_0_api_abuse_hub.py").resolve()
TOKEN_RE = re.compile(r"bwm_live_[0-9a-f]{12}_[A-Za-z0-9_-]{32,}")


def load_app(db_path):
    os.environ["BW_MONITOR_DB"] = str(db_path)
    os.environ["BW_MONITOR_TOKEN"] = "v48120-test-agent-token"
    os.environ["BW_API_RATE_LIMIT_PER_MINUTE"] = "1000"
    os.environ["BW_API_ACCESS_LOGS"] = "1"
    spec = importlib.util.spec_from_file_location("bw_monitor_v48120_test", str(APP_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load application")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admin_session(client, csrf="v48120-csrf"):
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
        sess["admin_username"] = "admin"
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"
        sess["dashboard_role"] = "admin"
        sess["csrf_token"] = csrf
    return csrf


def bearer(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json", "User-Agent": "v48.12.0-regression"}


def extract_token(response):
    match = TOKEN_RE.search(response.get_data(as_text=True))
    if not match:
        raise AssertionError("Plaintext API key was not rendered once")
    return match.group(0)


def insert_abuse_fixture(module):
    now = int(time.time())
    conn = module.db()
    try:
        conn.execute(
            """INSERT INTO vm_current_fast(
                node,vm_uuid,last_seen,interval_seconds,iface_count,
                public_mbps,private_mbps,rx_mbps,tx_mbps,total_mbps,
                rx_pps,tx_pps,total_pps,rx_peak_mbps,tx_peak_mbps,total_peak_mbps,
                rx_peak_pps,tx_peak_pps,total_peak_pps,
                sample_count,sample_expected,sample_max_gap,sample_quality,
                seconds_over_rx_pps,seconds_over_tx_pps,drops,errors,
                cpu_full_percent,cpu_core_percent,vcpu_current,
                ram_current_kib,ram_rss_kib,ram_available_kib,ram_unused_kib,ram_usable_kib,
                disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "NODE-A", "kvm77733", now, 300, 1,
                10.0, 0.0, 0.1, 0.2, 0.3,
                10.0, 20.0, 30.0, 1.0, 2.0, 3.0,
                100.0, 200.0, 300.0,
                20, 20, 15.0, "GOOD",
                0, 0, 0, 0,
                99.1, 594.6, 6,
                33554432, 30000000, 33554432, 4000000, 8000000,
                89039680.0, 283702.0, 1130.7, 27.1,
            ),
        )
        conn.execute(
            """INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,last_iface,last_bridge,status)
               VALUES(?,?,?,?,?,?,?)""",
            ("NODE-A", "kvm77733", now - 86400, now, "kvm77733.0", "br0", "active"),
        )
        conn.execute(
            """INSERT INTO vm_abuse_state(
                node,vm_uuid,last_seen,is_abuse,abuse_since,abuse_flags,severity,
                network_rx_hit,network_tx_hit,network_rx_mbps_hit,network_tx_mbps_hit,
                network_rx_mbps_streak_seconds,network_tx_mbps_streak_seconds,rx_mbps,tx_mbps,
                rx_pps,tx_pps,rx_peak_pps,tx_peak_pps,seconds_over_rx_pps,seconds_over_tx_pps,
                cpu_full_percent,cpu_core_percent,vcpu_current,cpu_streak_seconds,
                disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops,disk_streak_seconds,
                policy_revision,engine_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "NODE-A", "kvm77733", now, 1, now - 3600, "CPU_SUSTAINED", 1.1,
                0, 0, 0, 0, 0, 0, 0.1, 0.2,
                10.0, 20.0, 100.0, 200.0, 0, 0,
                99.1, 594.6, 6, 3600,
                89039680.0, 283702.0, 1130.7, 27.1, 0,
                1, module.ABUSE_ENGINE_VERSION,
            ),
        )
        conn.execute(
            """INSERT INTO vm_abuse_events(
                event_time,event_type,node,vm_uuid,abuse_flags,severity,
                rx_mbps,tx_mbps,rx_pps,tx_pps,rx_peak_pps,tx_peak_pps,
                seconds_over_rx_pps,seconds_over_tx_pps,
                cpu_full_percent,cpu_core_percent,vcpu_current,cpu_streak_seconds,
                disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops,disk_streak_seconds,
                policy_revision,engine_version,detail
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                now - 3000, "started", "NODE-A", "kvm77733", "CPU_SUSTAINED", 1.1,
                0.1, 0.2, 10.0, 20.0, 100.0, 200.0,
                0, 0, 99.1, 594.6, 6, 3600,
                89039680.0, 283702.0, 1130.7, 27.1, 0,
                1, module.ABUSE_ENGINE_VERSION, "CPU sustained fixture",
            ),
        )
        conn.commit()
    finally:
        conn.close()


with tempfile.TemporaryDirectory(prefix="bw-monitor-v48120-test-") as tmp:
    module = load_app(pathlib.Path(tmp) / "test.db")
    assert module.V48120_VERSION == "48.12.0"
    required = {
        "admin_api_key_delete", "admin_api_logs_clear", "api_v1_abuse_summary",
        "admin_api_keys_page", "api_v1_abuse_vms", "api_v1_abuse_vm", "api_v1_abuse_events",
    }
    missing = required - set(module.app.view_functions)
    assert not missing, sorted(missing)

    conn = module.db()
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"api_keys", "api_key_events", "api_access_logs"} <= tables
        cols = {r[1] for r in conn.execute("PRAGMA table_info(api_access_logs)")}
        assert {"request_id", "key_id", "path", "status_code", "duration_ms", "user_agent"} <= cols
    finally:
        conn.close()

    module.set_admin_credentials("admin", "strong-v48120-test-password")
    admin = module.app.test_client()
    csrf = admin_session(admin)
    created = admin.post(
        "/admin/api-keys/create",
        data={
            "csrf_token": csrf,
            "name": "Windows Abuse App",
            "scopes": ["abuse:read", "abuse_events:read"],
            "expiration": "never",
            "allowed_ips": "",
            "note": "v48.12.0 test",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    token = extract_token(created)
    key_id, _ = module._api_parse_token(token)
    assert key_id

    insert_abuse_fixture(module)
    api = module.app.test_client()
    summary = api.get("/api/v1/abuse/vms", headers=bearer(token))
    assert summary.status_code == 200, summary.get_data(as_text=True)
    payload = summary.get_json()
    assert payload["meta"]["view"] == "summary"
    assert payload["data"][0]["vm_uuid"] == "kvm77733"
    assert payload["data"][0]["primary_type"] == "cpu"
    assert "cpu" in payload["data"][0] and "policy" not in payload["data"][0]

    full = api.get("/api/v1/abuse/vms?view=full", headers=bearer(token)).get_json()
    assert full["meta"]["view"] == "full"
    assert "policy" in full["data"][0] and "network" in full["data"][0]

    abuse_summary = api.get("/api/v1/abuse/summary", headers=bearer(token))
    assert abuse_summary.status_code == 200
    assert abuse_summary.get_json()["data"]["current_abuse"] == 1

    events = api.get("/api/v1/abuse/events", headers=bearer(token))
    assert events.status_code == 200
    assert events.get_json()["meta"]["view"] == "summary"

    conn = module.db()
    try:
        access_rows = conn.execute("SELECT key_id,path,status_code,user_agent FROM api_access_logs WHERE key_id=?", (key_id,)).fetchall()
        assert len(access_rows) >= 4
        assert any(r[1] == "/api/v1/abuse/vms" and r[2] == 200 for r in access_rows)
        assert any("v48.12.0-regression" in r[3] for r in access_rows)
    finally:
        conn.close()

    request_page = admin.get("/admin/api-keys?tab=requests")
    event_page = admin.get("/admin/api-keys?tab=events")
    docs_page = admin.get("/admin/api-keys?tab=docs")
    for response in (request_page, event_page, docs_page):
        assert response.status_code == 200
    assert "API Request Logs" in request_page.get_data(as_text=True)
    assert "/api/v1/abuse/vms" in request_page.get_data(as_text=True)
    assert "API Management Events" in event_page.get_data(as_text=True)
    assert "/api/v1/abuse/summary" in docs_page.get_data(as_text=True)

    # Direct cleanup keeps keys.
    cleared = module.clear_api_logs("all")
    assert cleared["total_deleted"] > 0
    conn = module.db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM api_keys WHERE key_id=?", (key_id,)).fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM api_access_logs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_key_events").fetchone()[0] == 0
    finally:
        conn.close()

    # Generate fresh logs, then permanent delete must remove the key and related logs.
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 200
    deleted = admin.post(
        "/admin/api-keys/delete",
        data={"csrf_token": csrf, "key_id": key_id, "confirm_text": f"DELETE {key_id}"},
        follow_redirects=True,
    )
    assert deleted.status_code == 200
    assert api.get("/api/v1/me", headers=bearer(token)).status_code == 401
    conn = module.db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM api_keys WHERE key_id=?", (key_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_access_logs WHERE key_id=?", (key_id,)).fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_key_events WHERE key_id=?", (key_id,)).fetchone()[0] == 0
    finally:
        conn.close()

    # API-data cleanup removes all API-owned rows but leaves the monitor schema intact.
    with module.app.test_request_context("/admin/api-keys", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        conn = module.db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            module._api_create_key_record(conn, "Second Abuse App", ["abuse:read"], [], None, "test")
            conn.commit()
        finally:
            conn.close()
    all_cleared = module.clear_all_api_data()
    assert all_cleared["total_deleted"] >= 2
    conn = module.db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_access_logs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_key_events").fetchone()[0] == 0
        assert conn.execute("SELECT 1").fetchone()[0] == 1
    finally:
        conn.close()

    with module.app.test_request_context("/admin"):
        maintenance_html = module.database_maintenance_card()
        assert "Clear API logs" in maintenance_html
        assert "Clear all API data" in maintenance_html

print("PASS: v48.12.0 abuse-first summary/full API")
print("PASS: authenticated API request logs and Admin log views")
print("PASS: permanent key deletion removes key and related logs")
print("PASS: API log cleanup, API data cleanup and Maintenance controls")
