#!/usr/bin/env bash
set -Eeuo pipefail
ENV_FILE="${BW_ENTERPRISE_ENV_FILE:-/etc/default/bw-monitor-enterprise}"
[[ -r "$ENV_FILE" ]] || { echo "Missing $ENV_FILE" >&2; exit 1; }
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a
COMPOSE_FILE="${BW_ENTERPRISE_COMPOSE_FILE:-/opt/bw-monitor/enterprise/docker-compose.enterprise.yml}"
compose() {
  if docker compose version >/dev/null 2>&1; then docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  elif command -v docker-compose >/dev/null 2>&1; then docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
  else echo "Docker Compose is not installed" >&2; return 1; fi
}
cmd="${1:-status}"; shift || true
case "$cmd" in
  up) compose up -d "$@" ;;
  down) compose down "$@" ;;
  restart) compose restart "$@" ;;
  pull) compose pull "$@" ;;
  status|ps) compose ps "$@" ;;
  logs) compose logs --tail=200 "$@" ;;
  psql) exec docker exec -it bw-timescaledb psql -U "$BW_PG_USER" -d "$BW_PG_DATABASE" "$@" ;;
  schema)
    docker exec -i bw-timescaledb psql -v ON_ERROR_STOP=1 -U "$BW_PG_USER" -d "$BW_PG_DATABASE" < /opt/bw-monitor/enterprise/sql/001_enterprise_schema.sql
    docker exec -i bw-timescaledb psql -v ON_ERROR_STOP=1 -U "$BW_PG_USER" -d "$BW_PG_DATABASE" < /opt/bw-monitor/enterprise/sql/002_enterprise_views.sql
    ;;
  *) echo "Usage: $0 {up|down|restart|pull|status|logs|psql|schema}" >&2; exit 2 ;;
esac
