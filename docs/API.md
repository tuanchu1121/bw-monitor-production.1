# REST API Overview

REST API v1 uses scoped Bearer API keys created in Admin. Do not use `BW_MONITOR_TOKEN` for API clients; that token is reserved for Agent ingestion.

Authentication:

```http
Authorization: Bearer bwm_live_<key-id>_<secret>
```

Common endpoints:

```text
GET /api/v1/me
GET /api/v1/health
GET /api/v1/nodes
GET /api/v1/vms
GET /api/v1/vms/<uuid>/current
GET /api/v1/bandwidth/vms
GET /api/v1/bandwidth/vms/<uuid>
GET /api/v1/abuse/summary
GET /api/v1/abuse/vms
GET /api/v1/abuse/vms/<uuid>
GET /api/v1/abuse/events
GET /api/v1/abuse/incidents
GET /api/v1/abuse/rankings
GET /api/v1/logs/requests
GET /api/v1/logs/events
```

Scopes:

```text
node:read
vm:read
bandwidth:read
abuse:read
abuse_events:read
api_logs:read
```

Example:

```bash
API_KEY='PASTE_A_SCOPED_API_KEY'

curl -sS \
  -H "Authorization: Bearer ${API_KEY}" \
  'https://monitor.example.com/api/v1/abuse/vms?limit=100' \
| jq
```

Use Allowed IP/CIDR restrictions, expiration and least-privilege scopes for production clients. Rotate any key pasted into logs or chat.

See `release/API_V1_REFERENCE.txt` for the release-specific compact reference.
