# Audit and Diagnostics

## Quick doctor

```bash
sudo /opt/bw-monitor/doctor.sh
```

Checks service/timer state, Python compilation, local HTTP, database presence, secret-file permissions, free disk, maintenance worker count, and database readability.

## Deep audit

```bash
sudo /opt/bw-monitor/audit.sh
```

Checks:

- host, OS, kernel and release markers;
- systemd services/timers and maintenance workers;
- Python runtime and pinned packages;
- application compilation;
- environment and credential permissions;
- selected non-secret environment values;
- listening sockets, Nginx syntax and HTTP endpoints;
- public HTTPS certificate metadata when configured;
- disk and SQLite/WAL sizes;
- SQLite quick/integrity result;
- recent warning/error logs.

## Full release preflight

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production.1/main/audit.sh \
| sudo bash -s -- --full-preflight
```

This downloads the current repository revision and runs all release regression suites against temporary SQLite databases. It does not install files when `BW_PREFLIGHT_ONLY=1` is used internally.

## Sanitized diagnostics

```bash
sudo /opt/bw-monitor/collect-diagnostics.sh
```

The output archive is mode `0600` and excludes database content. Known token, password hash, secret key and Authorization values are redacted. Review the archive manually before sharing because logs can still contain environment-specific hostnames, IPs, UUIDs and operational details.
