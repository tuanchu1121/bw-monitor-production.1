#!/usr/bin/env python3
import hashlib
import importlib.util
import os
import pathlib
import re
import sys
import tempfile

APP_PATH = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "bw_monitor_app_v48_12_2_maintenance_fix.py").resolve()
TOKEN_RE = re.compile(r"bwm_live_[0-9a-f]{12}_[A-Za-z0-9_-]{32,}")


def load_app(db_path, trust_proxy=False):
    os.environ["BW_MONITOR_DB"] = str(db_path)
    os.environ["BW_MONITOR_TOKEN"] = "v48122-test-agent-token"
    os.environ["BW_API_RATE_LIMIT_PER_MINUTE"] = "1000"
    os.environ["BW_API_ACCESS_LOGS"] = "1"
    os.environ["BW_WEB_TRUST_PROXY"] = "1" if trust_proxy else "0"
    spec = importlib.util.spec_from_file_location(f"bw_monitor_v48122_test_{id(db_path)}", str(APP_PATH))
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load application")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admin_session(client, csrf="v48122-csrf"):
    with client.session_transaction() as sess:
        sess["admin_authenticated"] = True
        sess["admin_username"] = "admin"
        sess["dashboard_authenticated"] = True
        sess["dashboard_username"] = "admin"
        sess["dashboard_role"] = "admin"
        sess["csrf_token"] = csrf
    return csrf


def bearer(token):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "v48.12.2-regression",
    }


def extract_token(response):
    match = TOKEN_RE.search(response.get_data(as_text=True))
    if not match:
        raise AssertionError("Plaintext API key was not rendered once")
    return match.group(0)


with tempfile.TemporaryDirectory(prefix="bw-monitor-v48122-test-") as tmp:
    module = load_app(pathlib.Path(tmp) / "test.db")
    assert module.V48122_VERSION == "48.12.2"
    assert "api_logs:read" in module.API_SUPPORTED_SCOPES
    required = {
        "admin_api_key_edit",
        "api_v1_request_logs",
        "api_v1_management_logs",
    }
    assert not (required - set(module.app.view_functions))

    # The dark-mode patch requested by the operator is embedded in source.
    css = module.V48106_UI_CSS
    for needle in (
        ".count-badges > span",
        "background:#10243a!important",
        "border:1px solid #31577e!important",
        "border-color:#2b4260!important",
        "color:#ffffff!important",
    ):
        assert needle in css, needle

    # The old bug double-bound the click handler. The marker prevents a second bind.
    with module.app.test_request_context("/login"):
        field = module._v48106_password_field(
            "login-password", "password", "Password", "current-password"
        )
        login_html = module._v48106_login_document(
            action="/login",
            title="Welcome back",
            subtitle="Secure operations access",
            username_value="",
            next_url="/",
            extra_fields=field,
        )
    assert "btn.dataset.bwToggleBound==='1'" in login_html
    assert "btn.dataset.bwToggleBound='1'" in login_html
    assert "data-target=\"login-password\"" in login_html

    module.set_admin_credentials("admin", "strong-v48122-test-password")
    admin = module.app.test_client()
    csrf = admin_session(admin)

    # Internal Dashboard/Admin pages receive automatic Show/Hide controls.
    password_page = admin.get("/admin/password")
    password_html = password_page.get_data(as_text=True)
    assert password_page.status_code == 200
    assert "v48122-password-ui" in password_html
    assert "bw-password-toggle" in password_html

    created = admin.post(
        "/admin/api-keys/create",
        data={
            "csrf_token": csrf,
            "name": "Full Monitor Integration",
            "scopes": [
                "abuse:read",
                "abuse_events:read",
                "vm:read",
                "node:read",
                "bandwidth:read",
                "api_logs:read",
            ],
            "expiration": "never",
            "allowed_ips": "",
            "note": "v48.12.2 test",
        },
        follow_redirects=True,
    )
    assert created.status_code == 200
    token = extract_token(created)
    key_id, secret = module._api_parse_token(token)
    assert key_id and secret

    conn = module.db()
    try:
        before = module._api_get_key_by_id(conn, key_id)
        original_hash = before["secret_hash"]
    finally:
        conn.close()
    assert original_hash == hashlib.sha256(secret.encode()).hexdigest()

    # Existing key can be edited without rotation. Secret/hash remains unchanged.
    edited = admin.post(
        "/admin/api-keys/edit",
        data={
            "csrf_token": csrf,
            "key_id": key_id,
            "name": "Full Monitor Integration Updated",
            "scopes": [
                "abuse:read",
                "abuse_events:read",
                "vm:read",
                "node:read",
                "bandwidth:read",
                "api_logs:read",
            ],
            "allowed_ips": "127.0.0.1\n10.0.0.0/8",
            "expiration": "keep",
            "note": "allowlist updated without rotation",
        },
        follow_redirects=True,
    )
    assert edited.status_code == 200
    assert "existing secret remains valid" in edited.get_data(as_text=True)

    conn = module.db()
    try:
        after = module._api_get_key_by_id(conn, key_id)
        event_types = [
            r[0]
            for r in conn.execute(
                "SELECT event_type FROM api_key_events WHERE key_id=? ORDER BY id", (key_id,)
            ).fetchall()
        ]
    finally:
        conn.close()
    assert after["secret_hash"] == original_hash
    assert after["allowed_ips"] == ["127.0.0.1", "10.0.0.0/8"]
    assert "api_logs:read" in after["scopes"]
    assert "KEY_UPDATED" in event_types

    api = module.app.test_client()
    me = api.get("/api/v1/me", headers=bearer(token))
    assert me.status_code == 200, me.get_data(as_text=True)

    request_logs = api.get("/api/v1/logs/requests?limit=100", headers=bearer(token))
    assert request_logs.status_code == 200, request_logs.get_data(as_text=True)
    request_payload = request_logs.get_json()
    assert any(item["path"] == "/api/v1/me" for item in request_payload["data"])

    event_logs = api.get("/api/v1/logs/events?limit=100", headers=bearer(token))
    assert event_logs.status_code == 200, event_logs.get_data(as_text=True)
    assert any(item["event_type"] == "KEY_UPDATED" for item in event_logs.get_json()["data"])

    keys_page = admin.get("/admin/api-keys?tab=keys")
    keys_html = keys_page.get_data(as_text=True)
    assert keys_page.status_code == 200
    for needle in (
        "Create API key",
        "api_logs:read",
        "vm:read",
        "bandwidth:read",
        "/admin/api-keys/edit",
        "API CONTROL CENTER",
    ):
        assert needle in keys_html, needle

    docs_page = admin.get("/admin/api-keys?tab=docs")
    docs_html = docs_page.get_data(as_text=True)
    for needle in (
        "ABUSE-FIRST API V1",
        "/api/v1/abuse/vms",
        "/api/v1/vms",
        "/api/v1/nodes",
        "/api/v1/bandwidth/vms",
        "/api/v1/logs/requests",
        "/api/v1/logs/events",
    ):
        assert needle in docs_html, needle

    # Regression: maintenance_jobs.parameters is stored as JSON TEXT. The old
    # queue renderer called .get() on that string and made the Admin page return
    # HTTP 500 immediately after Clear API Logs was queued.
    assert module._maintenance_target_summary(
        "clear_api_logs", '{"kind":"all","compact":false}'
    ) == "Request Logs + Management Events"
    assert module._maintenance_target_summary(
        "clear_api_logs", '{"kind":"access","compact":true}'
    ) == "API Request Logs + VACUUM"
    assert module._maintenance_target_summary(
        "clear_api_data", {"compact": True}
    ) == "All external API keys + all API logs + VACUUM"

    conn = module.db()
    try:
        conn.execute(
            """INSERT INTO maintenance_jobs(
                created_at,action,parameters,status,requested_by,message,unit_name
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                module.now_ts(),
                "clear_api_logs",
                '{"kind":"all","compact":false}',
                "queued",
                "admin",
                "Waiting for maintenance worker",
                "bw-monitor-maintenance@test.service",
            ),
        )
        conn.commit()
    finally:
        conn.close()
    maintenance_page = admin.get("/admin?section=maintenance")
    assert maintenance_page.status_code == 200, maintenance_page.get_data(as_text=True)
    maintenance_html = maintenance_page.get_data(as_text=True)
    assert "Clear API logs" in maintenance_html
    assert "Request Logs + Management Events" in maintenance_html

    # Direct cleanup logic deletes both API-owned log tables while preserving
    # active keys. This is the exact function used by the out-of-process worker.
    conn = module.db()
    try:
        before_keys = conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0]
        before_access = conn.execute("SELECT COUNT(*) FROM api_access_logs").fetchone()[0]
        before_events = conn.execute("SELECT COUNT(*) FROM api_key_events").fetchone()[0]
    finally:
        conn.close()
    assert before_keys >= 1
    assert before_access >= 1
    assert before_events >= 1
    cleanup = module.clear_api_logs("all")
    assert cleanup["total_deleted"] >= 2
    conn = module.db()
    try:
        assert conn.execute("SELECT COUNT(*) FROM api_keys").fetchone()[0] == before_keys
        assert conn.execute("SELECT COUNT(*) FROM api_access_logs").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM api_key_events").fetchone()[0] == 0
    finally:
        conn.close()

    # ProxyFix is opt-in for domain/Nginx deployments.
    proxy_module = load_app(pathlib.Path(tmp) / "proxy.db", trust_proxy=True)
    assert proxy_module.WEB_TRUST_PROXY is True
    assert proxy_module.app.wsgi_app.__class__.__name__ == "ProxyFix"

print("PASS: v48.12.2 requested dark-mode contrast patch")
print("PASS: login double-bind fixed and Dashboard/Admin password toggles injected")
print("PASS: Allowed IP/scopes/note/expiry editable without rotating API secret")
print("PASS: abuse-first but complete VM/Node/Bandwidth/API Log permissions and docs")
print("PASS: API request and management log endpoints")
print("PASS: maintenance queue renders API cleanup jobs from persisted JSON without HTTP 500")
print("PASS: API log cleanup deletes request/events logs while preserving active keys")
print("PASS: opt-in trusted reverse-proxy support for domain/HTTPS deployments")
