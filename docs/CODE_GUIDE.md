# Code Guide and Internal Architecture

This document describes the source layout so operators and reviewers can audit the system without first reverse-engineering every file.

## Monitor application

Primary source:

```text
release/bw_monitor_app_v48_12_9_operations_ui.py
```

Installed as:

```text
/opt/bw-monitor/app.py
```

The application is a versioned monolithic Flask service. Major logical sections are separated by helpers, schema migrations, route groups and release markers.

### Configuration and startup

Environment values are read from `/etc/default/bw-monitor`. Startup initializes SQLite schema/migrations, current caches, Abuse policy state, API management tables, inventory visibility rules, and bounded-retention configuration.

### Ingestion

`POST /push` authenticates with `X-Token: BW_MONITOR_TOKEN`. The Agent sends node metrics, VM metrics, network deltas/peaks/windows, physical NIC context, filesystem data and Agent health. The Monitor deduplicates pushes by node and push time, updates current caches, writes historical data and evaluates Abuse rules.

### Current metrics and inventory

Current state is separated from historical rows to keep dashboard reads bounded. VM visibility is effective only when both the VM and its parent node are visible. Hiding a node does not rewrite every child VM status and does not delete metrics.

### Abuse Engine

The current engine marker is:

```text
cycles-v3-ram
```

It evaluates sustained Network, CPU, RAM and Disk conditions. Current state lives in `vm_abuse_state`. Raw transitions live in `vm_abuse_events`. Grouped Start→End occurrences live in `vm_abuse_incidents`. The operations dashboard exposes Current Abuse and grouped Abuse Events by VM.

Severity shown in Current Abuse is the maximum active rule ratio, not a sum. The UI displays rule-specific color chips and metric-local Abuse duration.

### REST API v1

API keys are separate from the Agent push token. Keys have scopes, expiration, rate limits, optional Allowed IP/CIDR rules, revocation/rotation and audit logs. Plaintext key secrets are shown only at creation/rotation; only hashes are stored.

### Dashboard and Admin

The dashboard is read-oriented. Admin pages manage API keys, Abuse policy, cleanup, inventory visibility, maintenance, retention and application operations. Destructive operations use explicit confirmation and are separated from read-only views.

### Maintenance

Primary source:

```text
release/bw_monitor_maintenance_v48_12_9_single_worker.py
```

The maintenance worker uses a fail-fast file lock and bounded job processing. The systemd template includes a recovery safety net so the web service is restarted if a worker is terminated during an offline compact stage.

### Retention

Primary source:

```text
release/bw_monitor_retention_v48_12_9.py
```

The timer runs every six hours with randomized delay. The retention worker does not stop the web service and does not run `VACUUM`. It keeps 48 hours of full pushes, one hourly snapshot through day 7, and deletes older historical data.

## Agent

Primary source:

```text
deploy/agent/agent.py
```

The Agent samples locally every 15 seconds by default and pushes every 300 seconds. It collects:

- VM TAP bytes, packets, drops, errors, average and local peak Mbps/PPS;
- sustained high-window seconds and sample quality;
- VM vCPU/core and normalized Full CPU;
- libvirt balloon RAM including current, unused and usable values;
- VM disk bytes and IOPS;
- node CPU/load/RAM/disk/uptime/filesystems;
- physical NICs under configured bridges;
- bridge IPs and collection timing health.

The Agent stores durable state in `/var/lib/bw-agent`. It does not commit counters until a push succeeds, reducing gaps after temporary Monitor/network failures.

## Deployment layer

`deploy/monitor/install-monitor.sh` wraps the exact release installer. It handles OS dependencies, venv, production environment, systemd, Nginx/Certbot, credentials and service verification.

The exact release installer under `release/` owns version-specific application migration, rollback, retention/maintenance units and regression tests.

## Review strategy

For a release review:

1. Verify `VERSION` and application build markers.
2. Run `.github/workflows/ci.yml` or `tools/release-audit.sh` locally.
3. Review environment defaults in `deploy/monitor/install-monitor.sh`.
4. Review `POST /push` authentication and API key authentication separately.
5. Review all SQL migrations and destructive Admin actions.
6. Review retention table lists and age cutoffs.
7. Review systemd hardening and writable paths.
8. Run the full release preflight on temporary databases.
