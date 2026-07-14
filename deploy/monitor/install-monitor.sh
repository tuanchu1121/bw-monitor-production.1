#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE="48.13.2-prod-r1-disk-only"
GITHUB_REPO="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
GITHUB_REF="${BW_GITHUB_REF:-main}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
RELEASE_DIR="$REPO_ROOT/release"
APP_DIR="/opt/bw-monitor"
ENV_FILE="/etc/default/bw-monitor"
SERVICE_FILE="/etc/systemd/system/bw-monitor.service"
CREDENTIAL_FILE="/root/bw-monitor-credentials.env"
NGINX_SITE="/etc/nginx/sites-available/bw-monitor.conf"

DOMAIN=""
DOMAIN_EXPLICIT=0
LE_EMAIL=""
PUBLIC_IP=""
PUBLIC_IP_EXPLICIT=0
PORT="8080"
PORT_EXPLICIT=0
ADMIN_USER="admin"
ADMIN_USER_EXPLICIT=0
ADMIN_PASSWORD="${BW_ADMIN_PASSWORD:-}"
MONITOR_TOKEN="${BW_MONITOR_TOKEN:-}"
TIMEZONE="Asia/Ho_Chi_Minh"
WORKERS=""
WORKERS_EXPLICIT=0
THREADS="2"
THREADS_EXPLICIT=0
NO_TLS=0
NO_TLS_EXPLICIT=0
NO_NGINX=0
ENABLE_FIREWALL=0
SSH_PORT=""
BACKUP_DB=0
RECOVER_STUCK=0
RUN_RETENTION_NOW=0
UPDATE_ONLY=0
SKIP_PREFLIGHT=0

log() { printf '\n==> %s\n' "$*"; }
warn() { printf '\nWARNING: %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'USAGE'
BW Monitor production installer

Usage:
  install-monitor.sh [options]

Fresh monitor with public IP:
  ./install-monitor.sh --public-ip 203.0.113.10 --port 8080

Fresh monitor with HTTPS domain:
  ./install-monitor.sh --domain monitor.example.com --email ops@example.com

Options:
  --domain NAME             Configure Nginx for this domain.
  --email ADDRESS           Let's Encrypt email. Required with TLS domain.
  --public-ip ADDRESS       Public IPv4/IPv6 shown in generated Agent URL.
  --port NUMBER             Internal/public Gunicorn port. Default: 8080.
  --admin-user NAME         Initial Admin username. Default: admin.
  --admin-password VALUE    Initial/reset Admin password. Prefer BW_ADMIN_PASSWORD env.
  --monitor-token VALUE     Agent push token. Prefer BW_MONITOR_TOKEN env.
  --timezone NAME           Server timezone. Default: Asia/Ho_Chi_Minh.
  --workers NUMBER          Gunicorn workers. Default: auto, max 4.
  --threads NUMBER          Threads per worker. Default: 2.
  --no-tls                  Use HTTP for a domain. Not recommended for production.
  --no-nginx                Do not install Nginx. Exposes Gunicorn on --port.
  --firewall                Configure and enable UFW. SSH port is detected.
  --ssh-port NUMBER         SSH port to allow before enabling UFW.
  --backup-db               Create a consistent SQLite backup during upgrade.
  --recover-stuck           Recover stale maintenance units/queue before install.
  --run-retention-now       Start the first retention run after installation.
  --update                  Preserve existing settings and update application files only.
  --skip-preflight          Skip release regression tests. Not recommended.
  -h, --help                Show this help.

Secrets can be supplied without command-line arguments:
  BW_ADMIN_PASSWORD='strong password' BW_MONITOR_TOKEN='token' ./install-monitor.sh ...
USAGE
}

while (($#)); do
  case "$1" in
    --domain) DOMAIN="${2:?missing value}"; DOMAIN_EXPLICIT=1; shift 2 ;;
    --email) LE_EMAIL="${2:?missing value}"; shift 2 ;;
    --public-ip) PUBLIC_IP="${2:?missing value}"; PUBLIC_IP_EXPLICIT=1; shift 2 ;;
    --port) PORT="${2:?missing value}"; PORT_EXPLICIT=1; shift 2 ;;
    --admin-user) ADMIN_USER="${2:?missing value}"; ADMIN_USER_EXPLICIT=1; shift 2 ;;
    --admin-password) ADMIN_PASSWORD="${2:?missing value}"; shift 2 ;;
    --monitor-token) MONITOR_TOKEN="${2:?missing value}"; shift 2 ;;
    --timezone) TIMEZONE="${2:?missing value}"; shift 2 ;;
    --workers) WORKERS="${2:?missing value}"; WORKERS_EXPLICIT=1; shift 2 ;;
    --threads) THREADS="${2:?missing value}"; THREADS_EXPLICIT=1; shift 2 ;;
    --ssh-port) SSH_PORT="${2:?missing value}"; shift 2 ;;
    --no-tls) NO_TLS=1; NO_TLS_EXPLICIT=1; shift ;;
    --no-nginx) NO_NGINX=1; shift ;;
    --firewall) ENABLE_FIREWALL=1; shift ;;
    --backup-db) BACKUP_DB=1; shift ;;
    --recover-stuck) RECOVER_STUCK=1; shift ;;
    --run-retention-now) RUN_RETENTION_NOW=1; shift ;;
    --update) UPDATE_ONLY=1; shift ;;
    --skip-preflight) SKIP_PREFLIGHT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$(id -u)" == "0" ]] || die "Run as root or through sudo."
[[ "$PORT" =~ ^[0-9]+$ ]] && ((PORT >= 1 && PORT <= 65535)) || die "Invalid port: $PORT"
[[ "$THREADS" =~ ^[0-9]+$ ]] && ((THREADS >= 1 && THREADS <= 64)) || die "Invalid thread count: $THREADS"
[[ -z "$WORKERS" || "$WORKERS" =~ ^[0-9]+$ ]] || die "Invalid worker count: $WORKERS"
[[ "$ADMIN_USER" =~ ^[A-Za-z0-9_.@-]{1,80}$ ]] || die "Admin username contains unsupported characters."
[[ -d "$RELEASE_DIR" ]] || die "Release directory is missing: $RELEASE_DIR"
[[ -f "$RELEASE_DIR/install_bw_monitor_v48_12_9.sh" ]] || die "Release installer is missing."
chmod +x "$RELEASE_DIR"/*.sh "$SCRIPT_DIR"/*.sh 2>/dev/null || true

if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
else
  die "/etc/os-release is missing."
fi
case "${ID:-}" in
  debian|ubuntu) ;;
  *) die "Supported operating systems: Debian and Ubuntu. Found: ${ID:-unknown}" ;;
esac

EXISTING=0
if [[ -r "$ENV_FILE" ]]; then
  EXISTING=1
  set -a
  # shellcheck disable=SC1090
  . "$ENV_FILE"
  set +a
  [[ -n "${BW_DOMAIN:-}" && -z "$DOMAIN" ]] && DOMAIN="$BW_DOMAIN"
  ((PUBLIC_IP_EXPLICIT)) || { [[ -n "${BW_PUBLIC_IP:-}" ]] && PUBLIC_IP="$BW_PUBLIC_IP"; }
  ((PORT_EXPLICIT)) || { [[ -n "${BW_PUBLIC_PORT:-}" ]] && PORT="$BW_PUBLIC_PORT"; }
  ((ADMIN_USER_EXPLICIT)) || { [[ -n "${BW_ADMIN_USERNAME:-}" ]] && ADMIN_USER="$BW_ADMIN_USERNAME"; }
  [[ -n "${BW_MONITOR_TOKEN:-}" && -z "$MONITOR_TOKEN" ]] && MONITOR_TOKEN="$BW_MONITOR_TOKEN"
  ((WORKERS_EXPLICIT)) || { [[ -n "${BW_GUNICORN_WORKERS:-}" ]] && WORKERS="$BW_GUNICORN_WORKERS"; }
  ((THREADS_EXPLICIT)) || { [[ -n "${BW_GUNICORN_THREADS:-}" ]] && THREADS="$BW_GUNICORN_THREADS"; }
  if ((NO_TLS_EXPLICIT == 0 && DOMAIN_EXPLICIT == 0)) && [[ -n "${BW_DOMAIN:-}" && "${BW_TLS_ENABLED:-0}" != "1" ]]; then NO_TLS=1; fi
  [[ "${BW_NGINX_ENABLED:-0}" == "1" ]] && NO_NGINX=0
fi

if ((UPDATE_ONLY)) && ((EXISTING == 0)); then
  die "--update requires an existing $ENV_FILE. Run a normal installation first."
fi

if [[ -n "$DOMAIN" ]]; then
  [[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || die "Invalid domain: $DOMAIN"
  if ((NO_NGINX)); then
    ((NO_TLS)) || die "TLS domain deployment requires Nginx. Remove --no-nginx or add --no-tls."
  fi
  if ((NO_TLS == 0)) && [[ ! -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
    [[ "$LE_EMAIL" == *@*.* ]] || die "--email is required for the first Let's Encrypt certificate issuance."
  fi
fi

if [[ -z "$WORKERS" ]]; then
  cpu_count="$(nproc 2>/dev/null || echo 2)"
  if ((cpu_count >= 8)); then WORKERS=4
  elif ((cpu_count >= 4)); then WORKERS=3
  else WORKERS=2
  fi
fi
((WORKERS >= 1 && WORKERS <= 16)) || die "Workers must be between 1 and 16."

random_secret() { openssl rand -base64 "$1" | tr -d '\n=+/' | cut -c1-"$2"; }

if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(ip -o route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' || true)"
  [[ -n "$PUBLIC_IP" ]] || PUBLIC_IP="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi

log "Install operating-system dependencies"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
packages=(ca-certificates curl openssl python3 python3-venv python3-pip sqlite3)
if [[ -n "$DOMAIN" && $NO_NGINX -eq 0 ]]; then
  packages+=(nginx)
  if ((NO_TLS == 0)); then
    packages+=(certbot python3-certbot-nginx)
  fi
fi
if ((ENABLE_FIREWALL)); then packages+=(ufw); fi
apt-get install -y --no-install-recommends "${packages[@]}"
python3 - <<'PY_VERSION'
import sys
if sys.version_info < (3, 10):
    raise SystemExit(f"Python 3.10+ is required; found {sys.version.split()[0]}")
print(f"Python runtime: {sys.version.split()[0]}")
PY_VERSION

if command -v timedatectl >/dev/null 2>&1; then
  timedatectl set-timezone "$TIMEZONE" || warn "Could not set timezone to $TIMEZONE"
fi

log "Prepare Python environment"
install -d -m 0750 "$APP_DIR"
if [[ ! -x "$APP_DIR/venv/bin/python3" ]]; then
  python3 -m venv "$APP_DIR/venv"
fi
"$APP_DIR/venv/bin/python3" -m pip install --upgrade pip wheel setuptools
"$APP_DIR/venv/bin/pip" install --upgrade -r "$REPO_ROOT/requirements.txt"

OLD_ADMIN_HASH="${BW_ADMIN_PASSWORD_HASH:-}"
OLD_APP_SECRET="${BW_ADMIN_SECRET_KEY:-}"
if [[ -z "$MONITOR_TOKEN" ]]; then
  MONITOR_TOKEN="bwm_push_$(random_secret 48 48)"
fi
[[ "$MONITOR_TOKEN" =~ ^[A-Za-z0-9._:-]{16,200}$ ]] || die "Monitor token must be 16-200 characters using A-Z, a-z, 0-9, dot, underscore, colon or dash."
if [[ -z "$OLD_APP_SECRET" ]]; then
  OLD_APP_SECRET="$(random_secret 96 80)"
fi

SAVED_ADMIN_PASSWORD=""
if [[ -r "$CREDENTIAL_FILE" ]]; then
  SAVED_ADMIN_PASSWORD="$(bash -c 'set -a; . "$1"; printf "%s" "${BW_ADMIN_PASSWORD:-}"' _ "$CREDENTIAL_FILE" 2>/dev/null || true)"
fi

GENERATED_PASSWORD=0
RECOVERED_PASSWORD=0
if [[ -z "$ADMIN_PASSWORD" && -n "$SAVED_ADMIN_PASSWORD" ]]; then
  ADMIN_PASSWORD="$SAVED_ADMIN_PASSWORD"
fi
if [[ -z "$ADMIN_PASSWORD" && -z "$OLD_ADMIN_HASH" ]]; then
  ADMIN_PASSWORD="$(random_secret 48 24)"
  GENERATED_PASSWORD=1
fi
if [[ -z "$ADMIN_PASSWORD" && -n "$OLD_ADMIN_HASH" && $UPDATE_ONLY -eq 0 && ! -r "$CREDENTIAL_FILE" ]]; then
  ADMIN_PASSWORD="$(random_secret 48 24)"
  GENERATED_PASSWORD=1
  RECOVERED_PASSWORD=1
  warn "Existing Admin password hash was found but $CREDENTIAL_FILE is missing. A new Admin password will be generated and stored."
fi

if [[ -n "$ADMIN_PASSWORD" ]]; then
  ((${#ADMIN_PASSWORD} >= 12)) || die "Admin password must contain at least 12 characters."
  ADMIN_HASH="$($APP_DIR/venv/bin/python3 - "$ADMIN_PASSWORD" <<'PY'
import sys
from werkzeug.security import generate_password_hash
print(generate_password_hash(sys.argv[1]))
PY
)"
else
  ADMIN_HASH="$OLD_ADMIN_HASH"
fi
[[ -n "$ADMIN_HASH" ]] || die "Could not determine Admin password hash."

if [[ -n "$DOMAIN" && $NO_NGINX -eq 0 ]]; then
  GUNICORN_BIND="127.0.0.1:$PORT"
  WEB_TRUST_PROXY=1
  API_TRUST_PROXY=1
else
  GUNICORN_BIND="0.0.0.0:$PORT"
  WEB_TRUST_PROXY=0
  API_TRUST_PROXY=0
fi
COOKIE_SECURE=0
if [[ -n "$DOMAIN" && $NO_NGINX -eq 0 && $NO_TLS -eq 0 && -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" ]]; then
  COOKIE_SECURE=1
fi

if [[ -n "$DOMAIN" ]]; then
  if ((NO_NGINX)); then
    PUBLIC_URL="http://$DOMAIN:$PORT"
  elif ((NO_TLS)); then
    PUBLIC_URL="http://$DOMAIN"
  else
    PUBLIC_URL="https://$DOMAIN"
  fi
else
  host_for_url="${PUBLIC_IP:-127.0.0.1}"
  [[ "$host_for_url" == *:* ]] && host_for_url="[$host_for_url]"
  PUBLIC_URL="http://$host_for_url:$PORT"
fi
PUSH_URL="$PUBLIC_URL/push"

log "Write protected production environment"
install -d -m 0755 "$(dirname "$ENV_FILE")"
tmp_env="$(mktemp)"
cat > "$tmp_env" <<EOF_ENV
BW_MONITOR_TOKEN='$MONITOR_TOKEN'
BW_MONITOR_DB='$APP_DIR/bandwidth.db'
BW_ADMIN_USERNAME='$ADMIN_USER'
BW_ADMIN_PASSWORD_HASH='$ADMIN_HASH'
BW_ADMIN_SECRET_KEY='$OLD_APP_SECRET'
BW_ADMIN_COOKIE_SECURE='$COOKIE_SECURE'
BW_WEB_TRUST_PROXY='$WEB_TRUST_PROXY'
BW_API_TRUST_PROXY='$API_TRUST_PROXY'
BW_API_TRUSTED_PROXIES='127.0.0.1/32,::1/128'
BW_API_ACCESS_LOGS='1'
BW_API_ACCESS_LOG_RETENTION_DAYS='7'
BW_API_RATE_LIMIT_PER_MINUTE='120'
BW_API_MAX_LIMIT='500'
BW_API_LAST_USED_FLUSH_SECONDS='60'
BW_RAW_RETENTION_DAYS='2'
BW_HOURLY_RETENTION_DAYS='7'
BW_RETENTION_BATCH_ROWS='25000'
BW_RETENTION_TZ_OFFSET_SECONDS='25200'
BW_WRITE_LEGACY_USAGE='0'
BW_BACKFILL_CACHE_ON_START='0'
BW_BACKFILL_INVENTORY_ON_START='0'
BW_MAX_PURGE_ITEMS_PER_JOB='3'
BW_MAX_PURGE_SELECTION_ITEMS='300'
BW_GUNICORN_BIND='$GUNICORN_BIND'
BW_GUNICORN_WORKERS='$WORKERS'
BW_GUNICORN_THREADS='$THREADS'
BW_GUNICORN_TIMEOUT='300'
BW_GUNICORN_GRACEFUL_TIMEOUT='60'
BW_GUNICORN_KEEPALIVE='5'
BW_GUNICORN_MAX_REQUESTS='2000'
BW_GUNICORN_MAX_REQUESTS_JITTER='200'
BW_GUNICORN_LOG_LEVEL='info'
BW_GUNICORN_ACCESS_LOG=''
BW_GUNICORN_ERROR_LOG='-'
BW_DOMAIN='$DOMAIN'
BW_PUBLIC_IP='$PUBLIC_IP'
BW_PUBLIC_PORT='$PORT'
BW_PUBLIC_URL='$PUBLIC_URL'
BW_PUSH_URL='$PUSH_URL'
BW_TLS_ENABLED='$COOKIE_SECURE'
BW_NGINX_ENABLED='$(( NO_NGINX == 0 && ${#DOMAIN} > 0 ? 1 : 0 ))'
EOF_ENV
install -o root -g root -m 0600 "$tmp_env" "$ENV_FILE"
rm -f "$tmp_env"

log "Write root-only deployment credentials before service verification"
password_to_store="$ADMIN_PASSWORD"
[[ -n "$password_to_store" ]] || password_to_store="$SAVED_ADMIN_PASSWORD"
{
  printf 'BW_MONITOR_RELEASE=%q\n' "$RELEASE"
  printf 'BW_MONITOR_URL=%q\n' "$PUBLIC_URL"
  printf 'BW_PUSH_URL=%q\n' "$PUSH_URL"
  printf 'BW_MONITOR_TOKEN=%q\n' "$MONITOR_TOKEN"
  printf 'BW_ADMIN_USERNAME=%q\n' "$ADMIN_USER"
  printf 'BW_ADMIN_PASSWORD=%q\n' "$password_to_store"
  printf 'BW_DOMAIN=%q\n' "$DOMAIN"
  printf 'BW_PUBLIC_IP=%q\n' "$PUBLIC_IP"
} > "$CREDENTIAL_FILE"
chmod 0600 "$CREDENTIAL_FILE"

install -o root -g root -m 0755 "$SCRIPT_DIR/start-monitor.sh" "$APP_DIR/start-monitor.sh"
for helper in doctor audit db-check backup restore collect-diagnostics; do
  install -o root -g root -m 0755 "$SCRIPT_DIR/${helper}.sh" "$APP_DIR/${helper}.sh"
done
install -o root -g root -m 0644 "$SCRIPT_DIR/bw-monitor.service" "$SERVICE_FILE"
install -o root -g root -m 0644 "$REPO_ROOT/VERSION" "$APP_DIR/DEPLOY_VERSION"
install -o root -g root -m 0644 "$REPO_ROOT/requirements.txt" "$APP_DIR/requirements.txt"
systemctl daemon-reload
systemctl unmask bw-monitor.service >/dev/null 2>&1 || true
systemctl enable bw-monitor.service >/dev/null

if ((SKIP_PREFLIGHT == 0)); then
  log "Run full release preflight and regression suite"
  (
    cd "$RELEASE_DIR"
    BW_PYTHON_BIN="$APP_DIR/venv/bin/python3" \
      BW_PREFLIGHT_ONLY=1 \
      ./install_bw_monitor_v48_12_9.sh
  )
fi

log "Install or upgrade BW Monitor application"
(
  cd "$RELEASE_DIR"
  BW_PYTHON_BIN="$APP_DIR/venv/bin/python3" \
  BW_BACKUP_DB="$BACKUP_DB" \
  BW_RECOVER_STUCK_MAINTENANCE="$RECOVER_STUCK" \
    ./install_bw_monitor_v48_12_9.sh
)

if [[ -n "$DOMAIN" && $NO_NGINX -eq 0 && ( $UPDATE_ONLY -eq 0 || $DOMAIN_EXPLICIT -eq 1 ) ]]; then
  log "Configure Nginx reverse proxy for $DOMAIN"
  sed -e "s/__DOMAIN__/$DOMAIN/g" -e "s/__PORT__/$PORT/g" \
    "$SCRIPT_DIR/nginx-bw-monitor.conf.tpl" > "$NGINX_SITE"
  ln -sfn "$NGINX_SITE" /etc/nginx/sites-enabled/bw-monitor.conf
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl enable --now nginx
  systemctl reload nginx

  if ((NO_TLS == 0)); then
    log "Issue or renew Let's Encrypt certificate"
    getent ahosts "$DOMAIN" >/dev/null 2>&1 || die "Domain $DOMAIN does not resolve yet. Point DNS to this server, then rerun the installer."
    if [[ -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" && -z "$LE_EMAIL" ]]; then
      certbot install --nginx --non-interactive --cert-name "$DOMAIN" || true
      certbot --nginx --non-interactive --redirect -d "$DOMAIN"
    else
      certbot --nginx --non-interactive --agree-tos --redirect \
        --email "$LE_EMAIL" -d "$DOMAIN"
    fi
    sed -i "s/^BW_ADMIN_COOKIE_SECURE=.*/BW_ADMIN_COOKIE_SECURE='1'/" "$ENV_FILE"
    sed -i "s/^BW_TLS_ENABLED=.*/BW_TLS_ENABLED='1'/" "$ENV_FILE"
    systemctl restart bw-monitor.service
    COOKIE_SECURE=1
  fi
fi

if ((ENABLE_FIREWALL)); then
  log "Configure UFW"
  if [[ -z "$SSH_PORT" ]]; then
    SSH_PORT="$(sshd -T 2>/dev/null | awk '$1=="port"{print $2; exit}' || true)"
    [[ -n "$SSH_PORT" ]] || SSH_PORT=22
  fi
  ufw allow "$SSH_PORT/tcp"
  if [[ -n "$DOMAIN" && $NO_NGINX -eq 0 ]]; then
    ufw allow 80/tcp
    ufw allow 443/tcp
  else
    ufw allow "$PORT/tcp"
  fi
  ufw --force enable
fi

wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts="${3:-60}"
  local delay="${4:-2}"
  local code="000"
  local i

  for i in $(seq 1 "$attempts"); do
    code="$(curl -sS -o /dev/null -w '%{http_code}' --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || true)"
    [[ -n "$code" ]] || code="000"
    printf '%s attempt %s/%s: HTTP %s\n' "$label" "$i" "$attempts" "$code"
    case "$code" in
      200|302) return 0 ;;
    esac
    if systemctl is-failed --quiet bw-monitor.service; then
      break
    fi
    sleep "$delay"
  done
  return 1
}

log "Verify production services"
systemctl restart bw-monitor.service
if ! wait_for_http "http://127.0.0.1:$PORT/login" "Local health" 60 2; then
  systemctl status bw-monitor.service --no-pager -l >&2 || true
  journalctl -u bw-monitor.service -n 250 --no-pager >&2 || true
  die "Local HTTP health check failed. Credentials are preserved in $CREDENTIAL_FILE."
fi
systemctl is-active --quiet bw-monitor.service || {
  journalctl -u bw-monitor.service -n 200 --no-pager >&2 || true
  die "bw-monitor.service is not active. Credentials are preserved in $CREDENTIAL_FILE."
}
systemctl is-active --quiet bw-monitor-retention.timer || die "bw-monitor-retention.timer is not active. Credentials are preserved in $CREDENTIAL_FILE."
if [[ -n "$DOMAIN" && $NO_TLS -eq 0 ]]; then
  if ! wait_for_http "https://$DOMAIN/login" "HTTPS health" 30 2; then
    nginx -t >&2 || true
    journalctl -u nginx -n 100 --no-pager >&2 || true
    die "HTTPS health check failed. Credentials are preserved in $CREDENTIAL_FILE."
  fi
fi

if ((RUN_RETENTION_NOW)); then
  log "Start first bounded-retention run"
  systemctl start bw-monitor-retention.service
fi

cat <<EOF_DONE

============================================================
BW Monitor $RELEASE deployed successfully
============================================================
Dashboard:       $PUBLIC_URL/
Admin:           $PUBLIC_URL/admin
Agent push URL:  $PUSH_URL
Admin username:  $ADMIN_USER
Agent token:     $MONITOR_TOKEN
Credentials:     $CREDENTIAL_FILE  (root only, mode 0600)
Environment:     $ENV_FILE         (root only, mode 0600)
Doctor:          $APP_DIR/doctor.sh
Audit:           $APP_DIR/audit.sh
Database check:  $APP_DIR/db-check.sh
Backup:          $APP_DIR/backup.sh
Diagnostics:     $APP_DIR/collect-diagnostics.sh
Monitor logs:    journalctl -fu bw-monitor.service
Retention logs:  journalctl -fu bw-monitor-retention.service

Agent one-command example:
  curl -fsSL https://raw.githubusercontent.com/$GITHUB_REPO/$GITHUB_REF/install-agent.sh | sudo env BW_AGENT_API='$PUSH_URL' BW_AGENT_TOKEN='$MONITOR_TOKEN' bash
============================================================
EOF_DONE

if ((GENERATED_PASSWORD)); then
  echo "Generated Admin password: $ADMIN_PASSWORD"
  echo "It is stored in $CREDENTIAL_FILE (root only, mode 0600)."
fi
if ((RECOVERED_PASSWORD)); then
  echo "The previous plaintext Admin password was unavailable, so the Admin password hash was safely replaced."
fi
