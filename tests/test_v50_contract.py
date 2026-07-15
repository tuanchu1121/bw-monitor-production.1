#!/usr/bin/env python3
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]

def need(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)

version = (ROOT / "VERSION").read_text().strip()
need(version == "50.0.4-prod-r1-one-command", f"unexpected VERSION: {version}")

app = (ROOT / "app/app.py").read_text()
pg = (ROOT / "app/bw_pg.py").read_text()
agent = (ROOT / "deploy/agent/agent.py").read_text()
playbook = (ROOT / "ansible/deploy-agent.yml").read_text()
installer = (ROOT / "deploy/postgres/install-postgres-native.sh").read_text()
compose = (ROOT / "postgres/docker-compose.yml").read_text()
timescale = (ROOT / "postgres/sql/002_timescale.sql").read_text()
indexes = (ROOT / "postgres/sql/003_native_indexes.sql").read_text()

# Exact cadence and retention from the supplied production code.
need("CACHE_BUCKET_SECONDS = 300" in app, "monitor cadence is not 300 seconds")
need("local 15-second network peak summaries, still one push per 5 minutes" in app.lower(), "original 15s/5m marker missing")
need("RAW_RETENTION_DAYS = min(2" in app, "2-day raw retention missing")
need("HOURLY_RETENTION_DAYS = min(7" in app, "7-day hourly retention missing")
need("SAMPLE_SECONDS = max(5, int(os.environ.get(\"BW_AGENT_SAMPLE_SECONDS\", \"15\")))" in agent, "Agent 15-second sampler default missing")
need("PUSH_SECONDS = max(60, int(os.environ.get(\"BW_AGENT_PUSH_SECONDS\", \"300\")))" in agent, "Agent 300-second push default missing")
need("bwagent_sample_seconds: 15" in playbook and "bwagent_push_seconds: 300" in playbook, "Ansible cadence defaults missing")

# PostgreSQL/TimescaleDB is the only runtime data store.
need("import sqlite3" not in "\n".join(p.read_text(errors="ignore") for p in (ROOT / "app").glob("*.py")), "runtime imports sqlite3")
runtime_py = "\n".join(p.read_text(errors="ignore") for base in (ROOT / "app", ROOT / "deploy") for p in base.rglob("*.py"))
need("sqlite3.connect" not in runtime_py, "sqlite3.connect remains in runtime Python source")
need("psycopg_pool" in pg and "ConnectionPool" in pg, "psycopg connection pool missing")
need("CREATE EXTENSION IF NOT EXISTS timescaledb" in timescale, "TimescaleDB extension setup missing")
need("create_hypertable" in timescale and "set_integer_now_func" in timescale, "Timescale hypertable setup missing")
need("127.0.0.1:${BW_PG_PORT:-55432}:5432" in compose, "PostgreSQL is not loopback-only")
need("BW_REDIS_ENABLED='$REDIS_CACHE'" in installer, "optional Redis flag missing")
need("REDIS_CACHE=0" in installer, "Redis must be disabled by default")
need("fresh-install PostgreSQL Native" in installer, "fresh-install PostgreSQL-native contract missing")
need("does not import SQLite data" in installer, "no-SQLite-migration contract missing")

# Full old UI, storage and abuse behavior must remain in the package.
markers = [
    '@app.route("/push", methods=["POST"])',
    'def top_page',
    'def vm_abuse_page',
    'def storage_io_page',
    'def vm_page',
    'def purge_vm_data',
    '_v48133_disk_sort_link("SLOTS", "diskcount"',
    'storage-vm-identity',
    'storage-top-card',
    'vm_disk_current',
    'node_storage_current',
    'vm_abuse_events',
    'vm_abuse_incidents',
    'api_v1_performance',
]
for marker in markers:
    need(marker in app, f"full application marker missing: {marker}")
need(len(app.splitlines()) > 25000, "full legacy UI/business logic was not preserved")

# PostgreSQL resolves GROUP BY role to the input np.role column in this query,
# leaving np.bridge ungrouped. Group by the normalized SELECT expression via
# output position instead.
need("GROUP BY np.node, role" not in app, "PostgreSQL-incompatible physical NIC role grouping remains")
need("GROUP BY np.node, 2" in app, "PostgreSQL physical NIC role grouping fix missing")
# abuse_policy_versions is keyed by revision, not id. It must never enter the
# generated-id compatibility list or psycopg will append an invalid RETURNING id.
serial_block = pg.split("_SERIAL_TABLES = {", 1)[1].split("}", 1)[0]
need('"abuse_policy_versions"' not in serial_block, "revision-keyed abuse_policy_versions incorrectly treated as id-serial")
need('BEGIN(?:\\s+IMMEDIATE)?' in pg, "legacy BEGIN compatibility no-op missing")
need("ProtectHome=read-only" in (ROOT / "deploy/agent/install-agent.sh").read_text(), "Agent service must see /home")
need("become: \"{{ (ansible_user | default('root')) != 'root' }}\"" in playbook, "root Ansible nodes should not require sudo")

# Product deployment and operations.
for path in [
    "install.sh", "update.sh", "backup.sh", "restore.sh", "doctor.sh",
    "db-check.sh", "audit.sh", "collect-diagnostics.sh", "uninstall.sh",
    "deploy/postgres/bw-monitorctl.sh", "deploy/postgres/backup.sh",
    "deploy/postgres/restore.sh", "deploy/postgres/doctor.sh",
    "deploy/postgres/bw-monitor-retention.timer", "postgres/docker-compose.yml",
]:
    need((ROOT / path).exists(), f"missing product file: {path}")
need("--domain" in installer and "certbot --nginx" in installer, "domain/Let's Encrypt installer path missing")
need("--public-ip" in installer and "--ip-mode" in installer, "IP installer/switch mode missing")
need("pg_dump" in (ROOT / "deploy/postgres/backup.sh").read_text(), "PostgreSQL backup missing")
need("pg_restore" in (ROOT / "deploy/postgres/restore.sh").read_text(), "PostgreSQL restore missing")
need("USING brin" in indexes, "compact history BRIN indexes missing")

print("PASS: v50 static product contract")
