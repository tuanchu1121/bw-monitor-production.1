# Ansible Deployment

## Inventory

```bash
cp ansible/inventory.example.ini ansible/inventory.ini
nano ansible/inventory.ini
```

Example:

```ini
[kvm_nodes]
192.0.2.11 ansible_port=22
192.0.2.12 ansible_port=1812

[kvm_nodes:vars]
ansible_user=root
```

## Deploy Agent

```bash
bash ansible/deploy-agent.sh \
  -i ansible/inventory.ini \
  --api 'https://monitor.example.com/push' \
  --token 'PASTE_THE_MONITOR_PUSH_TOKEN' \
  --forks 20 \
  --serial 10
```

The wrapper writes secrets to a temporary mode-0600 extra-vars file and deletes it on exit. Ansible tasks carrying the token use `no_log: true`.

## Limit hosts

```bash
bash ansible/deploy-agent.sh \
  -i ansible/inventory.ini \
  --api 'https://monitor.example.com/push' \
  --token 'PASTE_THE_MONITOR_PUSH_TOKEN' \
  --limit 'EPYC_SG'
```

## Remove Agents

```bash
bash ansible/remove-agent.sh \
  -i ansible/inventory.ini \
  --forks 20
```

Preserve Agent state by passing the playbook variable:

```bash
ansible-playbook \
  -i ansible/inventory.ini \
  ansible/remove-agent.yml \
  -e bwagent_keep_state=true
```

## Deploy a Monitor through Ansible

Copy and edit variables:

```bash
cp ansible/monitor-vars.example.yml ansible/monitor-vars.yml
nano ansible/monitor-vars.yml
```

Use Ansible Vault for the Admin password and Monitor token:

```bash
ansible-vault encrypt ansible/monitor-vars.yml
ansible-playbook \
  -i ansible/inventory.ini \
  ansible/deploy-monitor.yml \
  -e @ansible/monitor-vars.yml \
  --ask-vault-pass
```

The Monitor playbook copies the exact release and deployment code to the target, runs the production installer, and verifies the Monitor service and retention timer.
