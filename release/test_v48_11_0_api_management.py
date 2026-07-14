#!/usr/bin/env python3
import importlib.util
import json
import os
import pathlib
import re
import sys
import tempfile
import time

APP_PATH = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "bw_monitor_app_v48_11_0_api_management.py").resolve()
TOKEN_RE = re.compile(r"bwm_live_[0-9a-f]{12}_[A-Za-z0-9_-]{32,}")


def load_app(db_path):
    os.environ["BW_MONITOR_DB"] = str(db_path)
    os.environ["BW_MONITOR_TOKEN"] = "api-test-agent-token"
    os.environ["BW_API_RATE_LIMIT_PER_MINUTE"] = "1000"
    spec = importlib.util.spec_from_file_location("bw_monitor_api_test", str(APP_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load app module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admin_session(client, csrf="api-test-csrf"):
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
        sess["admin_username"] = "admin"
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"
        sess["dashboard_role"] = "admin"
        sess["csrf_token"] = csrf
    return csrf


def extract_token(response):
    match = TOKEN_RE.search(response.get_data(as_text=True))
    if not match:
        raise AssertionError("Plaintext API key was not shown after create/rotate")
    return match.group(0)


def bearer(token):
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def insert_fixture(module):
    now = int(time.time())
    policy_revision = module.get_abuse_settings()["revision"]
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
                "NODE-A", "11111111-2222-3333-4444-555555555555", now, 300, 1,
                910.0, 0.0, 12.0, 898.0, 910.0,
                3500.0, 225000.0, 228500.0, 25.0, 950.0, 955.0,
                8000.0, 360000.0, 363000.0,
                20, 20, 15.2, "GOOD",
                0, 285, 0, 0,
                94.0, 752.0, 8,
                67108864, 64000000, 67108864, 9000000, 19000000,
                10485760.0, 5242880.0, 800.0, 420.0,
            ),
        )
        conn.execute(
            """INSERT INTO vm_inventory(node,vm_uuid,first_seen,last_seen,last_iface,last_bridge,status)
               VALUES(?,?,?,?,?,?,?)""",
            ("NODE-A", "11111111-2222-3333-4444-555555555555", now - 86400, now, "tap100", "br0", "active"),
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
                "NODE-A", "11111111-2222-3333-4444-555555555555", now, 1, now - 900,
                "NETWORK_TX_PPS,NETWORK_TX_AVG_MBPS,CPU_SUSTAINED", 1.75,
                0, 1, 0, 1, 0, 900, 12.0, 898.0,
                3500.0, 225000.0, 8000.0, 360000.0, 0, 285,
                94.0, 752.0, 8, 1800,
                10485760.0, 5242880.0, 800.0, 420.0, 0,
                policy_revision, module.ABUSE_ENGINE_VERSION,
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
                now - 600, "started", "NODE-A", "11111111-2222-3333-4444-555555555555",
                "NETWORK_TX_PPS,NETWORK_TX_AVG_MBPS,CPU_SUSTAINED", 1.75,
                12.0, 898.0, 3500.0, 225000.0, 8000.0, 360000.0,
                0, 285, 94.0, 752.0, 8, 1800,
                10485760.0, 5242880.0, 800.0, 420.0, 0,
                policy_revision, module.ABUSE_ENGINE_VERSION, "API fixture event",
            ),
        )
        conn.execute(
            """INSERT INTO node_current_fast(
                node,last_seen,interval_seconds,vm_count,iface_count,
                public_bytes,private_bytes,total_bytes,public_packets,private_packets,total_packets,
                drops,errors,load1,load5,load15,cpu_count,cpu_percent,mem_total,mem_used,
                disk_read_bps,disk_write_bps,uptime_seconds
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "NODE-A", now, 300, 1, 1,
                1000, 0, 1000, 100, 0, 100,
                0, 0, 2.0, 1.5, 1.0, 64, 35.0, 274877906944, 137438953472,
                104857600.0, 52428800.0, 864000,
            ),
        )
        conn.commit()
    finally:
        conn.close()


with tempfile.TemporaryDirectory(prefix="bw-monitor-v48110-test-") as tmp:
    module = load_app(pathlib.Path(tmp) / "test.db")
    assert module.V48110_VERSION == "48.11.0"
    required_routes = {
        "admin_api_keys_page", "admin_api_key_create", "admin_api_key_revoke", "admin_api_key_rotate",
        "api_v1_me", "api_v1_health", "api_v1_abuse_vms", "api_v1_abuse_vm", "api_v1_abuse_events",
        "api_v1_vms", "api_v1_vm_current", "api_v1_nodes", "api_v1_bandwidth_vms", "api_v1_bandwidth_vm",
    }
    missing = required_routes - set(module.app.view_functions)
    assert not missing, f"Missing routes: {sorted(missing)}"

    conn = module.db()
    try:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"api_keys", "api_key_events"} <= tables
        columns = {row[1] for row in conn.execute("PRAGMA table_info(api_keys)")}
        assert {"key_id", "secret_hash", "scopes_json", "allowed_ips_json", "expires_at", "revoked_at"} <= columns
    finally:
        conn.close()

    module.set_admin_credentials("admin", "this-is-a-strong-api-test-password")
    client = module.app.test_client()
    csrf = admin_session(client)

    create = client.post(
        "/admin/api-keys/create",
        data={
            "csrf_token": csrf,
            "name": "Windows Abuse Monitor",
            "scopes": ["abuse:read", "abuse_events:read", "vm:read", "node:read", "bandwidth:read"],
            "expiration": "never",
            "allowed_ips": "",
            "note": "v48.11.0 regression",
        },
        follow_redirects=True,
    )
    assert create.status_code == 200
    token = extract_token(create)
    key_id, secret = module._api_parse_token(token)
    assert key_id and secret

    conn = module.db()
    try:
        row = conn.execute("SELECT secret_hash,scopes_json FROM api_keys WHERE key_id=?", (key_id,)).fetchone()
        assert row and row[0] == module._api_secret_hash(secret)
        assert token not in json.dumps(row)
        assert secret not in row[0]
    finally:
        conn.close()

    # Use a separate client with no dashboard/admin session. This catches
    # accidental interception by the legacy dashboard login middleware.
    api_client = module.app.test_client()
    me_response = api_client.get("/api/v1/me", headers=bearer(token))
    assert me_response.status_code == 200, me_response.get_data(as_text=True)
    assert me_response.get_json()["data"]["key_id"] == key_id
    assert api_client.get("/api/v1/health", headers=bearer(token)).status_code == 200
    assert api_client.get("/api/v1/me").status_code == 401
    assert api_client.get("/api/v1/me", headers=bearer("bwm_live_000000000000_invalid-invalid-invalid-invalid")).status_code == 401

    with module.app.test_request_context("/admin/api-keys", environ_base={"REMOTE_ADDR": "127.0.0.1"}):
        conn = module.db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            limited_id, limited_token = module._api_create_key_record(
                conn, "Abuse Only", ["abuse:read"], [], None, "test"
            )
            allow_id, allow_token = module._api_create_key_record(
                conn, "IP Locked", ["abuse:read"], ["203.0.113.0/24"], None, "test"
            )
            conn.commit()
        finally:
            conn.close()
    assert api_client.get("/api/v1/vms", headers=bearer(limited_token)).status_code == 403
    assert api_client.get("/api/v1/abuse/vms", headers=bearer(allow_token)).status_code == 403

    insert_fixture(module)
    checks = {
        "/api/v1/abuse/vms": "data",
        "/api/v1/abuse/vms/11111111-2222-3333-4444-555555555555?node=NODE-A": "data",
        "/api/v1/abuse/events": "data",
        "/api/v1/vms": "data",
        "/api/v1/vms/11111111-2222-3333-4444-555555555555/current?node=NODE-A": "data",
        "/api/v1/nodes": "data",
        "/api/v1/bandwidth/vms": "data",
        "/api/v1/bandwidth/vms/11111111-2222-3333-4444-555555555555?node=NODE-A": "data",
    }
    for path, field in checks.items():
        response = api_client.get(path, headers=bearer(token))
        assert response.status_code == 200, (path, response.status_code, response.get_data(as_text=True))
        payload = response.get_json()
        assert payload["ok"] is True and field in payload

    abuse = api_client.get("/api/v1/abuse/vms", headers=bearer(token)).get_json()
    assert abuse["meta"]["total"] == 1
    assert abuse["data"][0]["vm_uuid"] == "11111111-2222-3333-4444-555555555555"
    assert "NETWORK_TX_PPS" in abuse["data"][0]["flags"]
    assert abuse["data"][0]["sample"]["quality"] == "GOOD"

    rotate = client.post(
        "/admin/api-keys/rotate",
        data={"csrf_token": csrf, "key_id": key_id},
        follow_redirects=True,
    )
    assert rotate.status_code == 200
    new_token = extract_token(rotate)
    new_key_id, _ = module._api_parse_token(new_token)
    assert new_key_id and new_key_id != key_id
    assert api_client.get("/api/v1/me", headers=bearer(token)).status_code == 401
    assert api_client.get("/api/v1/me", headers=bearer(new_token)).status_code == 200

    revoke = client.post(
        "/admin/api-keys/revoke",
        data={"csrf_token": csrf, "key_id": new_key_id},
        follow_redirects=True,
    )
    assert revoke.status_code == 200
    assert api_client.get("/api/v1/me", headers=bearer(new_token)).status_code == 401

    page = client.get("/admin/api-keys")
    html = page.get_data(as_text=True)
    docs = client.get("/admin/api-keys?tab=docs")
    docs_html = docs.get_data(as_text=True)
    assert page.status_code == 200 and docs.status_code == 200
    assert "API Management" in html and "bandwidth:read" in html
    assert "/api/v1/abuse/vms" in docs_html
    assert token not in html and new_token not in html and token not in docs_html and new_token not in docs_html

print("PASS: v48.11.0 API schema and route registration")
print("PASS: one-time plaintext key, hash-only storage and Bearer auth")
print("PASS: scopes, IP allowlist, expiry-ready metadata and standardized errors")
print("PASS: abuse, events, VM current, bandwidth and node read-only APIs")
print("PASS: Admin create, rotate, revoke and audit UI")
