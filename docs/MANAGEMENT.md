# Management CLI

`bw-monitorctl` is installed at `/usr/local/sbin/bw-monitorctl`.

```bash
bw-monitorctl help
```

Core commands:

```bash
bw-monitorctl status
bw-monitorctl doctor
bw-monitorctl audit
bw-monitorctl db-check
bw-monitorctl urls
bw-monitorctl credentials
bw-monitorctl version
bw-monitorctl health
bw-monitorctl timezone status
bw-monitorctl timezone set UTC
bw-monitorctl timezone set Asia/Ho_Chi_Minh
```

Logs:

```bash
bw-monitorctl logs monitor 300
bw-monitorctl logs retention 300
bw-monitorctl logs postgres 300
bw-monitorctl logs all 300
bw-monitorctl follow monitor
bw-monitorctl follow postgres
```

Database and maintenance:

```bash
bw-monitorctl psql
bw-monitorctl retention
bw-monitorctl vacuum
bw-monitorctl backup
bw-monitorctl restore --from PATH --yes
```

Deployment:

```bash
bw-monitorctl update
bw-monitorctl domain status
bw-monitorctl domain set monitor.example.com ops@example.com
bw-monitorctl domain remove 203.0.113.10 8080
```

The `vacuum` command runs online PostgreSQL `VACUUM/ANALYZE`; it is not a file rewrite operation.


## Display timezone

The shared UI timezone is stored in PostgreSQL and applies across all Gunicorn workers:

```bash
bw-monitorctl timezone status
bw-monitorctl timezone set UTC
bw-monitorctl timezone set Asia/Ho_Chi_Minh
```

The same setting is available in **Admin → Overview → Display timezone**. Metric timestamps remain Unix/UTC values in PostgreSQL. This setting changes rendering only; retention and storage bucket boundaries do not change.

## Web liveness

```bash
bw-monitorctl health
systemctl status bw-monitor-health-watch.timer --no-pager
journalctl -t bw-monitor-health-watch -n 100 --no-pager
```

`/livez` checks the Gunicorn process without touching PostgreSQL. `/healthz` also verifies the database. The watchdog restarts the web service only after two consecutive `/livez` failures, so a temporary database error does not cause a restart loop.
