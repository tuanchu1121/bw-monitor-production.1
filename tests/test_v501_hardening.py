#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
app = (ROOT / "app/app.py").read_text()
installer = (ROOT / "deploy/postgres/install-postgres-native.sh").read_text()
service = (ROOT / "deploy/postgres/bw-monitor.service").read_text()
nginx = (ROOT / "deploy/postgres/nginx.conf.tpl").read_text()
start = (ROOT / "deploy/postgres/start-monitor.sh").read_text()
ctl = (ROOT / "deploy/postgres/bw-monitorctl.sh").read_text()

def need(condition, message):
    if not condition:
        raise AssertionError(message)

need("V501_VERSION = \"50.1.1-prod-r1-stability-fix\"" in app, "v50.1.1 marker missing")
need('@app.route("/livez")' in app and '@app.route("/healthz")' in app, "health endpoints missing")
need("bw-monitor-health-watch.timer" in installer, "health watchdog is not installed")
need("StartLimitIntervalSec=0" in service and "Restart=always" in service, "systemd recovery hardening missing")
need("--worker-tmp-dir" in start and "/dev/shm" in start, "Gunicorn worker tmp hardening missing")
need("proxy_next_upstream" in nginx and "proxy_connect_timeout 5s" in nginx, "Nginx upstream hardening missing")
need("min-width:2380px" not in app, "Abuse VM still forces a 2380px table")
need(".abuse-current-v48139{width:100%!important;min-width:0!important;table-layout:fixed!important}" in app, "fluid Abuse VM table missing")
need("Display timezone" in app and "Asia/Ho_Chi_Minh" in app and '"UTC": "UTC (UTC+0)"' in app, "timezone selector missing")
need("BW_DISPLAY_TIMEZONE" in installer and "--display-timezone" in installer, "timezone installer support missing")
need("timezone set UTC" in ctl, "timezone CLI missing")
need("WAL reserved/recycled" in app and "SHM {human" not in app, "PostgreSQL size labels still use SQLite semantics")
need("Archive legacy SQLite files if present" in installer, "legacy SQLite archive step missing")
need("COALESCE(svi.status, 'active')!='hidden'" in app, "Dashboard search can still match hidden vm_inventory rows")
need("WHERE vis.node=svl.node AND vis.vm_uuid=svl.vm_uuid" in app, "Dashboard location search lacks visibility join")
need("COALESCE(ni.status,'active')!='hidden'" in app, "Storage hidden-node predicate missing")
need("page_cache_generation" in app and "_v501_invalidate_visibility_cache" in app, "cross-worker cache invalidation missing")
print("PASS: v50.1 production hardening contract")

# v50.1.1 stability invariants.
need("global TZ_NAME, TZ\n" in app, "display timezone should not mutate retention/storage offset")
need("global TZ_NAME, TZ, RETENTION_TZ_OFFSET_SECONDS" not in app, "display timezone still mutates retention offset")
need('if value.startswith("@")' in app and 'return f"@{timestamp}"' in app, "absolute custom snapshot preservation missing")
need("Current VMs on Node" in app and "_v5011_node_vm_inventory_rows" in app, "authoritative per-node VM inventory missing")
need("This list does not depend on br0/br1 interface rows" in app, "node VM list independence marker missing")
print("PASS: v50.1.1 timezone and node inventory stability contract")
