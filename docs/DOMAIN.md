# Domain and HTTPS Deployment

## Prerequisites

- The domain A/AAAA record resolves to the Monitor server.
- TCP ports 80 and 443 are reachable from the Internet.
- The server clock is correct.
- No conflicting Nginx/Apache site occupies the domain.

## Install

```bash
curl -fsSL \
https://raw.githubusercontent.com/tuanchu1121/bw-monitor-production/main/install.sh \
| sudo bash -s -- \
  --domain monitor.example.com \
  --email ops@example.com
```

The installer:

1. Binds Gunicorn to `127.0.0.1:8080`.
2. Installs an Nginx reverse proxy.
3. Requests or installs a Let's Encrypt certificate with Certbot.
4. Redirects HTTP to HTTPS.
5. Enables secure Admin cookies.
6. Trusts forwarding headers only from loopback Nginx.
7. Verifies local HTTP and public HTTPS.

## Validate

```bash
nginx -t
systemctl status nginx --no-pager -l
systemctl status bw-monitor --no-pager -l
curl -I https://monitor.example.com/login
sudo /opt/bw-monitor/audit.sh
```

## Firewall

In domain mode, expose only 80/443 publicly. Do not expose the Gunicorn port. The installer can configure UFW with `--firewall`; verify the detected SSH port before enabling it on unusual systems.

## Existing certificate

When a matching Certbot certificate already exists, the installer reuses it. When the first certificate is issued, `--email` is required.

## Changing a domain

Run the installer again with the new `--domain` and `--email`. Validate DNS before the change. Review old certificates and Nginx sites after successful migration.
