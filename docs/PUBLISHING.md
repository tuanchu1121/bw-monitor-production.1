# Publishing to GitHub

## GitHub CLI method

Install and authenticate GitHub CLI on a trusted workstation, then run from this repository root:

```bash
gh auth login
./publish-github.sh \
  --repo tuanchu1121/bw-monitor-production.1 \
  --public \
  --release
```

The helper:

1. runs the local release audit;
2. checks for database/cache/secret files;
3. validates every shell script, Python file and YAML file;
4. runs the full v48.13.5 storage-root-bars release preflight;
5. regenerates and verifies checksums;
6. initializes Git when needed;
7. creates or updates the GitHub repository;
8. pushes the `main` branch;
9. builds ZIP/TAR.GZ source archives;
10. creates or updates the `v48.13.5-prod-r1` GitHub Release.

## GitHub Web method

1. Create a repository named `bw-monitor-production` under `tuanchu1121`.
2. Choose public visibility when unauthenticated one-command `curl` installation is desired.
3. Upload the contents of this repository root, not an additional outer directory.
4. Confirm the GitHub root contains:

```text
install.sh
README.md
release/
deploy/
ansible/
docs/
.github/
```

5. Wait for the `BW Monitor CI` workflow to pass.

## Private repository bootstrap

For a private repository, export a fine-grained read-only token before using a bootstrap script:

```bash
export GITHUB_TOKEN='READ_ONLY_TOKEN'
export BW_GITHUB_REPO='tuanchu1121/bw-monitor-production.1'
export BW_GITHUB_REF='main'

curl -fsSL \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H 'Accept: application/vnd.github.raw+json' \
  "https://api.github.com/repos/$BW_GITHUB_REPO/contents/install.sh?ref=$BW_GITHUB_REF" \
| sudo -E bash -s -- --public-ip 203.0.113.10 --port 8080
```

A public repository is operationally simpler for raw one-command installers, provided no secrets or customer data are ever committed.
