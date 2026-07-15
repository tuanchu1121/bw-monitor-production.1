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
