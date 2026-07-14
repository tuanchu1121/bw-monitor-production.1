#!/usr/bin/env bash
set -Eeuo pipefail
RELEASE="49.0.0-prod-r1-enterprise-timescale"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
BASE_INSTALL="$REPO_ROOT/deploy/monitor/install-monitor.sh"
ENT_SRC="$REPO_ROOT/enterprise"
APP_DIR="/opt/bw-monitor"
ENT_DIR="$APP_DIR/enterprise"
ENV_FILE="/etc/default/bw-monitor"
ENT_ENV="/etc/default/bw-monitor-enterprise"
CRED_FILE="/root/bw-monitor-credentials.env"
PUBLIC_IP=""; PORT="8080"; DOMAIN=""; EMAIL=""; NO_TLS=0; NO_NGINX=0
PG_PORT="55432"; PG_PASSWORD="${BW_PG_PASSWORD:-}"; PG_USER="bwmonitor"; PG_DATABASE="bwmonitor"
TIMESCALE_IMAGE="timescale/timescaledb:2.28.1-pg17-oss"
SKIP_BASE=0; SKIP_PREFLIGHT=0; INSTALL_DOCKER=1; MIGRATE_HISTORY=1; FOREGROUND_MIGRATION=0

log(){ printf '\n==> %s\n' "$*"; }
warn(){ printf '\nWARNING: %s\n' "$*" >&2; }
die(){ printf '\nERROR: %s\n' "$*" >&2; exit 1; }
usage(){ cat <<'EOF'
BW Monitor v49 Enterprise installer

Usage:
  ./install-enterprise.sh --public-ip 45.92.158.124

Options:
  --public-ip IP           Monitor public IP.
  --port PORT              Gunicorn/public port. Default 8080.
  --domain NAME            Optional Nginx/HTTPS domain.
  --email ADDRESS          Let's Encrypt email for a new domain certificate.
  --no-tls                 Use HTTP for domain.
  --no-nginx               Do not configure Nginx.
  --pg-port PORT           Local TimescaleDB port. Default 55432.
  --db-password VALUE      Existing/new Timescale DB password. Alphanumeric preferred.
  --timescale-image IMAGE  Default timescale/timescaledb:2.28.1-pg17-oss.
  --skip-base-install      Do not reinstall/update the legacy-compatible web app.
  --skip-preflight         Skip the base regression suite.
  --no-docker-install      Require Docker/Compose to already exist.
  --no-history-migration   Sync current state only; do not backfill SQLite history.
  --foreground-migration   Wait for full SQLite historical migration to finish.
  -h, --help               Show help.
EOF
}
while (($#)); do case "$1" in
  --public-ip) PUBLIC_IP="${2:?}"; shift 2;; --port) PORT="${2:?}"; shift 2;;
  --domain) DOMAIN="${2:?}"; shift 2;; --email) EMAIL="${2:?}"; shift 2;;
  --no-tls) NO_TLS=1; shift;; --no-nginx) NO_NGINX=1; shift;;
  --pg-port) PG_PORT="${2:?}"; shift 2;; --db-password) PG_PASSWORD="${2:?}"; shift 2;;
  --timescale-image) TIMESCALE_IMAGE="${2:?}"; shift 2;; --skip-base-install) SKIP_BASE=1; shift;;
  --skip-preflight) SKIP_PREFLIGHT=1; shift;; --no-docker-install) INSTALL_DOCKER=0; shift;;
  --no-history-migration) MIGRATE_HISTORY=0; shift;; --foreground-migration) FOREGROUND_MIGRATION=1; shift;;
  -h|--help) usage; exit 0;; *) die "Unknown option: $1";; esac; done
[[ "$(id -u)" == 0 ]] || die "Run as root"
[[ "$PORT" =~ ^[0-9]+$ ]] || die "Invalid --port"
[[ "$PG_PORT" =~ ^[0-9]+$ ]] || die "Invalid --pg-port"
[[ -x "$BASE_INSTALL" ]] || die "Missing base installer"

# Preserve the existing database identity on upgrades. PostgreSQL initializes
# the password only once, so silently generating a new password for an existing
# Docker volume would lock the writer out of its own database.
if [[ -r "$ENT_ENV" ]]; then
  set -a; . "$ENT_ENV"; set +a
  [[ -z "$PG_PASSWORD" ]] && PG_PASSWORD="${BW_PG_PASSWORD:-}"
  [[ "$PG_PORT" == "55432" && -n "${BW_PG_PORT:-}" ]] && PG_PORT="$BW_PG_PORT"
  [[ "$PG_USER" == "bwmonitor" && -n "${BW_PG_USER:-}" ]] && PG_USER="$BW_PG_USER"
  [[ "$PG_DATABASE" == "bwmonitor" && -n "${BW_PG_DATABASE:-}" ]] && PG_DATABASE="$BW_PG_DATABASE"
  [[ "$TIMESCALE_IMAGE" == "timescale/timescaledb:2.28.1-pg17-oss" && -n "${BW_TIMESCALE_IMAGE:-}" ]] && TIMESCALE_IMAGE="$BW_TIMESCALE_IMAGE"
fi

if [[ -r "$ENV_FILE" ]]; then
  set -a; . "$ENV_FILE"; set +a
  [[ -z "$PUBLIC_IP" ]] && PUBLIC_IP="${BW_PUBLIC_IP:-}"
  [[ "$PORT" == "8080" && -n "${BW_PUBLIC_PORT:-}" ]] && PORT="$BW_PUBLIC_PORT"
fi
if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++)if($i=="src"){print $(i+1);exit}}' || true)"
  [[ -n "$PUBLIC_IP" ]] || PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

if ((SKIP_BASE==0)); then
  log "Install/update the v49 legacy-compatible web and control plane"
  BASE_ARGS=(--public-ip "$PUBLIC_IP" --port "$PORT" --backup-db)
  [[ -n "$DOMAIN" ]] && BASE_ARGS+=(--domain "$DOMAIN")
  [[ -n "$EMAIL" ]] && BASE_ARGS+=(--email "$EMAIL")
  ((NO_TLS)) && BASE_ARGS+=(--no-tls)
  ((NO_NGINX)) && BASE_ARGS+=(--no-nginx)
  ((SKIP_PREFLIGHT)) && BASE_ARGS+=(--skip-preflight)
  if [[ -r "$ENV_FILE" ]]; then BASE_ARGS+=(--update); fi
  if [[ -r "$CRED_FILE" ]]; then
    set -a; . "$CRED_FILE"; set +a
    export BW_ADMIN_PASSWORD="${BW_ADMIN_PASSWORD:-}"
    export BW_MONITOR_TOKEN="${BW_MONITOR_TOKEN:-}"
  fi
  "$BASE_INSTALL" "${BASE_ARGS[@]}"
fi
[[ -r "$ENV_FILE" ]] || die "$ENV_FILE was not created by the base installation"

log "Install Docker and Compose runtime"
export DEBIAN_FRONTEND=noninteractive
if ((INSTALL_DOCKER)); then
  apt-get update -y
  apt-get install -y --no-install-recommends docker.io ca-certificates curl jq
  systemctl enable --now docker
  if ! docker compose version >/dev/null 2>&1; then
    apt-get install -y docker-compose-plugin 2>/dev/null || apt-get install -y docker-compose
  fi
fi
command -v docker >/dev/null || die "Docker is required"
if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then die "Docker Compose is required"; fi

log "Install Enterprise Python dependencies"
"$APP_DIR/venv/bin/pip" install --upgrade 'psycopg[binary,pool]>=3.2,<4' 'redis>=5,<7'

log "Size PostgreSQL/TimescaleDB from host RAM"
RAM_MIB="$(( $(awk '/^MemTotal:/{print $2;exit}' /proc/meminfo) / 1024 ))"
shared=$((RAM_MIB/4)); ((shared<512))&&shared=512; ((shared>8192))&&shared=8192
effective=$((RAM_MIB*65/100)); ((effective<1024))&&effective=1024; ((effective>32768))&&effective=32768
maintenance=$((RAM_MIB/16)); ((maintenance<256))&&maintenance=256; ((maintenance>2048))&&maintenance=2048
if ((RAM_MIB>=32768)); then work=64; shm=4gb; workers=24; parallel=12
elif ((RAM_MIB>=16384)); then work=32; shm=2gb; workers=16; parallel=8
else work=16; shm=1gb; workers=12; parallel=4; fi
[[ -n "$PG_PASSWORD" ]] || PG_PASSWORD="$(openssl rand -hex 32)"
[[ "$PG_PASSWORD" =~ ^[A-Za-z0-9._-]{16,200}$ ]] || die "DB password must be 16-200 safe characters: A-Z a-z 0-9 . _ -"

log "Verify Enterprise release files"
python3 -m py_compile "$ENT_SRC/bw_enterprise_writer.py" "$ENT_SRC/bw_enterprise_migrate.py"
bash -n "$ENT_SRC"/*.sh "$SCRIPT_DIR"/*.sh

log "Install Enterprise files"
install -d -m 0750 "$ENT_DIR" "$ENT_DIR/sql" /var/lib/bw-monitor-enterprise/spool/inbox /var/lib/bw-monitor-enterprise/spool/bad /var/log/bw-monitor-enterprise
install -m 0644 "$ENT_SRC/docker-compose.enterprise.yml" "$ENT_DIR/docker-compose.enterprise.yml"
install -m 0644 "$ENT_SRC/sql/001_enterprise_schema.sql" "$ENT_DIR/sql/001_enterprise_schema.sql"
install -m 0644 "$ENT_SRC/sql/002_enterprise_views.sql" "$ENT_DIR/sql/002_enterprise_views.sql"
for f in bw_enterprise_writer.py bw_enterprise_migrate.py; do install -m 0755 "$ENT_SRC/$f" "$ENT_DIR/$f"; done
for f in bw-enterprise-ctl.sh bw-enterprise-backup.sh bw-enterprise-restore.sh bw-enterprise-doctor.sh; do install -m 0755 "$ENT_SRC/$f" "$ENT_DIR/$f"; done
if [[ -f "$REPO_ROOT/docs/ENTERPRISE.md" ]]; then install -m 0644 "$REPO_ROOT/docs/ENTERPRISE.md" "$ENT_DIR/ENTERPRISE.md"; fi

cat > "$ENT_ENV.tmp" <<EOF
BW_ENTERPRISE_RELEASE='$RELEASE'
BW_ENTERPRISE_ENABLED='1'
BW_ENTERPRISE_PG_DSN='postgresql://$PG_USER:$PG_PASSWORD@127.0.0.1:$PG_PORT/$PG_DATABASE'
BW_ENTERPRISE_STREAM='bw:enterprise:ingest:v1'
BW_ENTERPRISE_STREAM_MAXLEN='0'
BW_ENTERPRISE_CONSUMER_GROUP='bw-enterprise-writers'
BW_ENTERPRISE_STREAM_BATCH='100'
BW_ENTERPRISE_STREAM_RETAIN_ACKED='10000'
BW_ENTERPRISE_STREAM_BLOCK_MS='3000'
BW_ENTERPRISE_CLAIM_IDLE_MS='120000'
BW_ENTERPRISE_MAX_RETRIES='8'
BW_ENTERPRISE_STORE_RAW_PUSH='0'
BW_ENTERPRISE_SPOOL='/var/lib/bw-monitor-enterprise/spool'
BW_ENTERPRISE_COMPOSE_FILE='$ENT_DIR/docker-compose.enterprise.yml'
BW_ENTERPRISE_BACKUP_DIR='/opt/bw-monitor/backups/enterprise'
BW_ENTERPRISE_BACKUP_KEEP_DAYS='14'
BW_TIMESCALE_IMAGE='$TIMESCALE_IMAGE'
BW_PG_PORT='$PG_PORT'
BW_PG_USER='$PG_USER'
BW_PG_DATABASE='$PG_DATABASE'
BW_PG_PASSWORD='$PG_PASSWORD'
BW_PG_SHARED_BUFFERS='${shared}MB'
BW_PG_EFFECTIVE_CACHE_SIZE='${effective}MB'
BW_PG_MAINTENANCE_WORK_MEM='${maintenance}MB'
BW_PG_WORK_MEM='${work}MB'
BW_PG_MAX_CONNECTIONS='100'
BW_PG_MAX_WORKERS='$workers'
BW_PG_MAX_PARALLEL_WORKERS='$parallel'
BW_PG_MAX_PARALLEL_PER_GATHER='4'
BW_TSDB_BACKGROUND_WORKERS='8'
BW_PG_SHM_SIZE='$shm'
EOF
install -o root -g root -m 0600 "$ENT_ENV.tmp" "$ENT_ENV"; rm -f "$ENT_ENV.tmp"

# Add only the web-facing Enterprise variables to the existing environment.
python3 - "$ENV_FILE" "$ENT_ENV" <<'PY'
import pathlib,sys
base=pathlib.Path(sys.argv[1]); ent=pathlib.Path(sys.argv[2])
keys={"BW_ENTERPRISE_ENABLED","BW_ENTERPRISE_PG_DSN","BW_ENTERPRISE_STREAM","BW_ENTERPRISE_STREAM_MAXLEN","BW_ENTERPRISE_SPOOL"}
values={}
for line in ent.read_text().splitlines():
    if "=" in line and line.split("=",1)[0] in keys: values[line.split("=",1)[0]]=line
old=base.read_text().splitlines(); out=[x for x in old if x.split("=",1)[0] not in keys]
out += [values[k] for k in sorted(values)]
base.write_text("\n".join(out)+"\n")
PY
chmod 0600 "$ENV_FILE"

log "Start local TimescaleDB"
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$ENT_ENV" -f "$ENT_DIR/docker-compose.enterprise.yml")
else
  compose=(docker-compose --env-file "$ENT_ENV" -f "$ENT_DIR/docker-compose.enterprise.yml")
fi
"${compose[@]}" pull
"${compose[@]}" up -d
for i in $(seq 1 90); do
  if docker exec bw-timescaledb pg_isready -U "$PG_USER" -d "$PG_DATABASE" >/dev/null 2>&1; then break; fi
  ((i==90)) && { "${compose[@]}" logs --tail=200 timescaledb >&2 || true; die "TimescaleDB did not become ready"; }
  sleep 2
done

log "Create Timescale hypertables, projections and continuous aggregates"
docker exec -i bw-timescaledb psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DATABASE" < "$ENT_DIR/sql/001_enterprise_schema.sql"
docker exec -i bw-timescaledb psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DATABASE" < "$ENT_DIR/sql/002_enterprise_views.sql"

log "Install Enterprise systemd services"
# The web service writes the durable outbox before acknowledging an agent push.
# Keep the original service hardening and add only this explicit writable path.
install -d -m 0755 /etc/systemd/system/bw-monitor.service.d
cat > /etc/systemd/system/bw-monitor.service.d/49-enterprise-spool.conf <<'EOF'
[Service]
ReadWritePaths=/var/lib/bw-monitor-enterprise
EOF
for f in bw-enterprise-writer.service bw-enterprise-migrate.service bw-enterprise-reconcile.service bw-enterprise-reconcile.timer bw-enterprise-backup.service bw-enterprise-backup.timer; do
  install -m 0644 "$ENT_SRC/$f" "/etc/systemd/system/$f"
done
ln -sfn "$ENT_DIR/bw-enterprise-ctl.sh" /usr/local/sbin/bw-enterprise
ln -sfn "$ENT_DIR/bw-enterprise-doctor.sh" /usr/local/sbin/bw-enterprise-doctor
ln -sfn "$ENT_DIR/bw-enterprise-backup.sh" /usr/local/sbin/bw-enterprise-backup
systemctl daemon-reload
systemctl enable --now bw-enterprise-writer.service bw-enterprise-reconcile.timer bw-enterprise-backup.timer
systemctl restart bw-monitor.service

log "Synchronize current SQLite state into TimescaleDB"
"$APP_DIR/venv/bin/python3" "$ENT_DIR/bw_enterprise_migrate.py" --current-only

if ((MIGRATE_HISTORY)); then
  log "Start historical SQLite migration"
  if ((FOREGROUND_MIGRATION)); then systemctl start bw-enterprise-migrate.service
  else systemctl start --no-block bw-enterprise-migrate.service; fi
fi

set -a
. "$ENV_FILE"
set +a

log "Verify Enterprise stack"
"$ENT_DIR/bw-enterprise-doctor.sh" || warn "Doctor reported a problem. Check the output above and journalctl -u bw-enterprise-writer."
cat <<EOF

============================================================
BW Monitor $RELEASE installed
============================================================
Dashboard:          ${BW_PUBLIC_URL:-http://$PUBLIC_IP:$PORT}
Enterprise status:  ${BW_PUBLIC_URL:-http://$PUBLIC_IP:$PORT}/enterprise
Enterprise health:  ${BW_PUBLIC_URL:-http://$PUBLIC_IP:$PORT}/api/v1/enterprise/health
TimescaleDB:        127.0.0.1:$PG_PORT (local only)
Enterprise env:     $ENT_ENV
Control:            bw-enterprise status|logs|psql
Doctor:             bw-enterprise-doctor
Backup now:         bw-enterprise-backup
Writer logs:        journalctl -fu bw-enterprise-writer.service
Migration logs:     journalctl -fu bw-enterprise-migrate.service
Migration status:   systemctl status bw-enterprise-migrate.service
============================================================
EOF
