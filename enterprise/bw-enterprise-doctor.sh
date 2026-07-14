#!/usr/bin/env bash
set -uo pipefail
pass=0; warn=0; fail=0
ok(){ printf 'PASS  %s\n' "$*"; pass=$((pass+1)); }
wa(){ printf 'WARN  %s\n' "$*"; warn=$((warn+1)); }
no(){ printf 'FAIL  %s\n' "$*"; fail=$((fail+1)); }
[[ -r /etc/default/bw-monitor-enterprise ]] || { no "missing /etc/default/bw-monitor-enterprise"; exit 1; }
set -a
. /etc/default/bw-monitor 2>/dev/null || true
. /etc/default/bw-monitor-enterprise
set +a
systemctl is-active --quiet bw-monitor.service && ok "bw-monitor.service active" || no "bw-monitor.service inactive"
systemctl is-active --quiet bw-enterprise-writer.service && ok "enterprise writer active" || no "enterprise writer inactive"
systemctl is-active --quiet redis-server.service && ok "redis-server active" || wa "redis-server unit not active"
redis-cli -u "${BW_REDIS_URL:-redis://127.0.0.1:6379/0}" ping 2>/dev/null | grep -q PONG && ok "Redis PING" || no "Redis unavailable"
docker inspect -f '{{.State.Health.Status}}' bw-timescaledb 2>/dev/null | grep -q healthy && ok "TimescaleDB container healthy" || no "TimescaleDB container not healthy"
if docker exec bw-timescaledb psql -U "$BW_PG_USER" -d "$BW_PG_DATABASE" -Atqc "SELECT extversion FROM pg_extension WHERE extname='timescaledb'" >/tmp/bw-ts-version.$$ 2>/dev/null; then
  ok "TimescaleDB extension $(cat /tmp/bw-ts-version.$$)"
else no "TimescaleDB SQL check failed"; fi
rm -f /tmp/bw-ts-version.$$
health="$(docker exec bw-timescaledb psql -U "$BW_PG_USER" -d "$BW_PG_DATABASE" -AtF'|' -c "SELECT nodes,vms,customer_disks,storage_mounts,COALESCE(dead_letters,0) FROM bw.enterprise_health" 2>/dev/null || true)"
[[ -n "$health" ]] && ok "projection counts node|vm|disk|mount|dead = $health" || no "enterprise_health view unavailable"
qlen="$(redis-cli -u "${BW_REDIS_URL:-redis://127.0.0.1:6379/0}" XLEN "${BW_ENTERPRISE_STREAM:-bw:enterprise:ingest:v1}" 2>/dev/null || echo '?')"
ok "Redis stream length $qlen"
spool="$(find "${BW_ENTERPRISE_SPOOL:-/var/lib/bw-monitor-enterprise/spool}/inbox" -maxdepth 1 -type f -name '*.json' 2>/dev/null | wc -l)"
if ((spool>0)); then wa "spool contains $spool payloads"; else ok "spool empty"; fi
pending="$(redis-cli -u "${BW_REDIS_URL:-redis://127.0.0.1:6379/0}" XPENDING "${BW_ENTERPRISE_STREAM:-bw:enterprise:ingest:v1}" "${BW_ENTERPRISE_CONSUMER_GROUP:-bw-enterprise-writers}" 2>/dev/null | head -1 || echo '?')"
[[ "$pending" =~ ^[0-9]+$ && "$pending" -gt 1000 ]] && wa "pending stream entries $pending" || ok "pending stream entries ${pending:-0}"
printf '\nSummary: PASS=%s WARN=%s FAIL=%s\n' "$pass" "$warn" "$fail"
((fail==0))
