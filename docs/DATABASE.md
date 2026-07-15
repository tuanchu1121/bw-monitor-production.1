# POSTGRESQL 17 + TIMESCALEDB

## Runtime

```text
Container: bw-timescaledb
Database: bw_monitor
User: bw_monitor
Host bind: 127.0.0.1:55432
Docker volume: bw_monitor_postgres_data
```

PostgreSQL/TimescaleDB là nguồn dữ liệu duy nhất.

## Kiểm tra nhanh

```bash
virtinfra-monitorctl db-check
```

```bash
virtinfra-monitorctl psql
```

## Container

```bash
docker ps --filter name=bw-timescaledb
```

```bash
docker inspect -f '{{.State.Health.Status}}' bw-timescaledb
```

```bash
docker logs --tail 300 bw-timescaledb
```

## Volume

```bash
docker volume inspect bw_monitor_postgres_data
```

Không xóa volume này khi chưa có backup đã verify.

## Database size

```bash
virtinfra-monitorctl psql -c "SELECT pg_size_pretty(pg_database_size(current_database())) AS database_size;"
```

## Hypertables

```bash
virtinfra-monitorctl psql -c "SELECT hypertable_name,num_chunks FROM timescaledb_information.hypertables ORDER BY hypertable_name;"
```

## Consumption table

```text
node_bandwidth_consumption_2h
```

Mỗi row là một node và một bucket 2 giờ. Bảng lưu 8 counter tổng, coverage, sample count, agent version và received time. Không lưu UUID VM.

## VACUUM online

```bash
virtinfra-monitorctl vacuum
```

Routine VACUUM giúp tái sử dụng dead tuples. Không dùng `VACUUM FULL` trong giờ production.

## Backup/restore

```bash
virtinfra-monitorctl backup
```

```bash
virtinfra-monitorctl restore --from /var/backups/bw-monitor/YYYYMMDD-HHMMSS --yes
```
