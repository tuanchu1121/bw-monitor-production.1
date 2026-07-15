#!/usr/bin/env bash
set -Eeuo pipefail
CMD="${1:-help}"; shift || true
APP=/opt/bw-monitor
if [[ -r /etc/default/bw-monitor ]]; then set -a; . /etc/default/bw-monitor; set +a; fi
case "$CMD" in
  status)
    systemctl status bw-monitor.service bw-monitor-health-watch.timer bw-monitor-retention.timer docker --no-pager -l || true
    echo; docker ps --filter name=bw-timescaledb
    ;;
  doctor) exec bash "$APP/doctor.sh" "$@" ;;
  audit) exec bash "$APP/audit.sh" "$@" ;;
  db-check|database) exec bash "$APP/db-check.sh" "$@" ;;
  backup) exec bash "$APP/backup.sh" "$@" ;;
  restore) exec bash "$APP/restore.sh" "$@" ;;
  diagnostics) exec bash "$APP/collect-diagnostics.sh" "$@" ;;
  logs)
    target="${1:-monitor}"; lines="${2:-200}"
    case "$target" in
      monitor|web) journalctl -u bw-monitor.service -n "$lines" --no-pager ;;
      retention) journalctl -u bw-monitor-retention.service -n "$lines" --no-pager ;;
      postgres|timescale) docker logs --tail "$lines" bw-timescaledb ;;
      all) journalctl -u bw-monitor.service -u bw-monitor-retention.service -n "$lines" --no-pager; docker logs --tail "$lines" bw-timescaledb ;;
      *) echo "Unknown log target: $target" >&2; exit 2 ;;
    esac
    ;;
  follow)
    target="${1:-monitor}"
    case "$target" in
      monitor|web) exec journalctl -fu bw-monitor.service ;;
      retention) exec journalctl -fu bw-monitor-retention.service ;;
      postgres|timescale) exec docker logs -f --tail 100 bw-timescaledb ;;
      *) echo "Unknown follow target: $target" >&2; exit 2 ;;
    esac
    ;;
  restart)
    systemctl restart bw-monitor.service
    "$APP/doctor.sh"
    ;;
  health)
    port="${BW_PUBLIC_PORT:-8080}"
    curl -fsS "http://127.0.0.1:${port}/livez"; echo
    curl -fsS "http://127.0.0.1:${port}/healthz"; echo
    ;;
  timezone)
    action="${1:-status}"; shift || true
    case "$action" in
      status)
        "$APP/venv/bin/python3" - <<'PYTZ'
import app
name = app._v501_refresh_timezone(force=True)
print(f"{name} ({app.DISPLAY_TIMEZONE_CHOICES[name]})")
PYTZ
        ;;
      set)
        zone="${1:?Usage: bw-monitorctl timezone set UTC|Asia/Ho_Chi_Minh}"
        [[ "$zone" == "UTC" || "$zone" == "Asia/Ho_Chi_Minh" ]] || { echo 'Supported: UTC or Asia/Ho_Chi_Minh' >&2; exit 2; }
        "$APP/venv/bin/python3" - "$zone" <<'PYTZ'
import sys
import app
zone = sys.argv[1]
app.set_admin_setting(app.V501_TIMEZONE_SETTING, zone)
app._v501_refresh_timezone(force=True)
app._v48140_bump_cache_generation()
print(f"Display timezone: {zone}")
PYTZ
        systemctl reload bw-monitor.service 2>/dev/null || systemctl restart bw-monitor.service
        ;;
      *) echo 'Usage: bw-monitorctl timezone status|set UTC|Asia/Ho_Chi_Minh' >&2; exit 2 ;;
    esac
    ;;
  retention)
    systemctl start bw-monitor-retention.service
    journalctl -fu bw-monitor-retention.service
    ;;
  vacuum)
    set -a; . /etc/default/bw-monitor-postgres; set +a
    docker exec bw-timescaledb vacuumdb -U "$BW_PG_USER" -d "$BW_PG_DATABASE" --analyze-in-stages
    ;;
  psql)
    set -a; . /etc/default/bw-monitor-postgres; set +a
    exec docker exec -it bw-timescaledb psql -U "$BW_PG_USER" -d "$BW_PG_DATABASE" "$@"
    ;;
  credentials) cat /root/bw-monitor-credentials.env ;;
  urls)
    set -a; . /etc/default/bw-monitor; set +a
    printf 'Dashboard: %s/\nAdmin: %s/admin\nAgent push: %s\n' "$BW_PUBLIC_URL" "$BW_PUBLIC_URL" "$BW_PUSH_URL"
    ;;
  version) cat "$APP/DEPLOY_VERSION" ;;
  update)
    repo="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"
    ref="${BW_GITHUB_REF:-main}"
    exec bash -c 'curl -fsSL "https://raw.githubusercontent.com/$1/$2/update.sh" | bash' _ "$repo" "$ref" ;;
  domain)
    action="${1:-status}"; shift || true
    case "$action" in
      status)
        printf 'Domain: %s
TLS: %s
Public URL: %s
' "${BW_DOMAIN:-<none>}" "${BW_TLS_ENABLED:-0}" "${BW_PUBLIC_URL:-}"
        ;;
      set)
        domain="${1:?Usage: bw-monitorctl domain set DOMAIN EMAIL}"; email="${2:?Usage: bw-monitorctl domain set DOMAIN EMAIL}"
        repo="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"; ref="${BW_GITHUB_REF:-main}"
        exec bash -c 'curl -fsSL "https://raw.githubusercontent.com/$1/$2/install.sh" | bash -s -- --update --domain "$3" --email "$4"' _ "$repo" "$ref" "$domain" "$email"
        ;;
      remove)
        ip="${1:-${BW_PUBLIC_IP:-}}"; port="${2:-${BW_PUBLIC_PORT:-8080}}"
        [[ -n "$ip" ]] || { echo 'Public IP is required.' >&2; exit 2; }
        repo="${BW_GITHUB_REPO:-tuanchu1121/bw-monitor-production.1}"; ref="${BW_GITHUB_REF:-main}"
        exec bash -c 'curl -fsSL "https://raw.githubusercontent.com/$1/$2/install.sh" | bash -s -- --update --ip-mode --public-ip "$3" --port "$4"' _ "$repo" "$ref" "$ip" "$port"
        ;;
      *) echo 'Usage: bw-monitorctl domain status|set DOMAIN EMAIL|remove [IP] [PORT]' >&2; exit 2 ;;
    esac
    ;;
  help|--help|-h)
    cat <<'EOF'
bw-monitorctl commands:
  status                 services and container
  doctor                 fast health check
  audit                  deep read-only audit
  db-check               PostgreSQL/Timescale details
  backup                 pg_dump + protected config backup
  restore --from DIR     restore a backup
  diagnostics            sanitized support bundle
  logs [target] [lines]  monitor|retention|postgres|all
  follow [target]        live logs
  restart                restart and verify web
  health                 local process and PostgreSQL health endpoints
  timezone status        show shared display timezone
  timezone set ZONE      set UTC or Asia/Ho_Chi_Minh
  retention              run bounded retention now
  vacuum                 online VACUUM/ANALYZE
  psql                   PostgreSQL shell
  credentials            root-only generated credentials
  urls                    dashboard/admin/push URLs
  version                 deployed version
  update                  update from configured GitHub repo/ref
  domain status           show domain/TLS state
  domain set D E          switch to domain D with Let's Encrypt email E
  domain remove [IP] [P]  switch back to public IP mode
EOF
    ;;
  *) echo "Unknown command: $CMD" >&2; "$0" help; exit 2 ;;
esac
