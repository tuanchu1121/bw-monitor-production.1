# Quick commands

```bash
bw-monitorctl status
bw-monitorctl doctor
bw-monitorctl db-check
bw-monitorctl logs all 200
bw-monitorctl follow monitor
bw-monitorctl restart
bw-monitorctl backup
bw-monitorctl retention
bw-monitorctl vacuum
bw-monitorctl psql
bw-monitorctl urls
bw-monitorctl credentials
bw-monitorctl version
bw-monitorctl update
```

Agent:

```bash
systemctl status bwagent --no-pager -l
journalctl -fu bwagent
```

Ansible Agent deployment:

```bash
bash ansible/deploy-agent.sh \
-i ansible/test.txt \
--api 'https://monitor.example.com/push' \
--token "$BW_TOKEN" \
--forks 20 \
--serial 10
```
