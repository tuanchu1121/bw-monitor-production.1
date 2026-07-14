# Security Policy

## Never commit or publish

- `/etc/default/bw-monitor`
- `/root/bw-monitor-credentials.env`
- `/etc/bwagent.env`
- `bandwidth.db`, `bandwidth.db-wal`, `bandwidth.db-shm`
- plaintext REST API keys
- Agent push tokens
- Admin passwords or password hashes
- decrypted Ansible secret files or Vault passwords
- production diagnostic bundles unless reviewed and intentionally shared

## Token separation

`BW_MONITOR_TOKEN` authenticates Agent `POST /push` ingestion only. External applications must use separately generated scoped REST API keys. Never give the Agent token to a desktop/API client.

## Recommended deployment

Use domain + HTTPS mode for Internet-facing production. It binds Gunicorn to loopback and exposes Nginx on 80/443. Do not open the internal Gunicorn port publicly in this mode.

## Secrets at rest

The installer writes Monitor and Agent environments as `root:root` mode `0600`. The root credential file is also mode `0600`. Keep root access restricted and include these files in secure backup handling.

## REST API keys

Use least-privilege scopes, expiration, per-key rate limits and Allowed IP/CIDR restrictions. Rotate keys after accidental disclosure. Plaintext key secrets are not recoverable after the one-time creation/rotation display.

## GitHub visibility

A public repository exposes source code, not secrets. This repository is prepared to contain no database or real credentials. A private repository requires an authenticated GitHub token for remote bootstrap scripts; use a fine-grained read-only token when possible.

## Diagnostics

`collect-diagnostics.sh` redacts known secret fields and does not include the database. Logs can still contain hostnames, IP addresses, UUIDs and operational metadata. Review every bundle before sharing.

## Reporting

Do not open a public issue containing production credentials, customer data, complete logs, database files or unredacted environment files.
