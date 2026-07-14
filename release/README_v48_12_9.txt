BW Monitor v48.12.9-r4
======================

Purpose
-------
v48.12.9 is an operations-focused refinement of v48.12.8. It keeps the
existing Agent v10 payload, cycles-v3-ram Abuse engine, REST API v1,
48-hour raw / 7-day bounded retention, API Management, maintenance guard,
and all current Node/VM data.

Dashboard Abuse
---------------
The public Dashboard exposes only two tabs:

1. Current Abuse
2. Abuse Events

Current Abuse is a Top-VM-style table with independent sorting for:

- Network AVG: RX Mbps / TX Mbps
- PPS Peak / Window: RX PPS / TX PPS
- CPU: Full % / Core %
- RAM: Guest % / Used GiB / Host RSS / Assigned
- Disk: Read / Write / Read IOPS / Write IOPS
- Reason / Severity
- Node / VM
- Last Seen

The Reason / Severity cell contains:

- Transparent MAX ratio and the metric that produced it
- Network chip in blue
- CPU chip in red
- RAM chip in purple
- Disk chip in orange
- Active duration chip in amber
- Exact policy threshold and sustained duration in every rule chip

CPU and RAM cells use resource meters normalized to the VM's assigned
resources. The meter color changes at 70%, 85% and 95%.

Abuse Events
------------
One row is shown per Node + VM UUID. The row contains:

- Abuse occurrence count
- Total Abuse minutes
- Longest occurrence minutes
- Maximum ratio
- Primary/reason chips
- Last Abuse time
- Copy UUID

Click the row or View button to expand every occurrence with:

- Started
- Ended / Active now
- Exact duration in minutes and human-readable form
- Maximum ratio
- Color-coded reasons
- Raw transition count

Admin Abuse cleanup
-------------------
Three data sets are shown explicitly:

- vm_abuse_state: Current Abuse and sustained streaks
- vm_abuse_events: raw STARTED / UPDATED / RECOVERED transitions
- vm_abuse_incidents: grouped Abuse Events by VM

Clear all history:

- Deletes vm_abuse_events
- Deletes vm_abuse_incidents
- Preserves vm_abuse_state

Clear matching / selected:

- Deletes matching raw events
- Rebuilds vm_abuse_incidents from the remaining raw history

Reset all Abuse data:

- Deletes vm_abuse_events
- Deletes vm_abuse_incidents
- Deletes vm_abuse_state

Per-VM Abuse controls allow independent selection of:

- Delete Raw History
- Delete Abuse Events by VM
- Reset Current Abuse + streak

A VM that still exceeds policy can reappear after its sustained window.

Upgrade safety
--------------
The installer:

- Compiles all Python files
- Runs every regression suite from v48.10.0 through v48.12.9
- Verifies the complete incident cleanup contract in the source
- Backs up installed code and systemd units
- Optionally creates a consistent SQLite backup with BW_BACKUP_DB=1
- Installs the app, maintenance worker and bounded-retention service/timer
- Restarts and verifies bw-monitor.service
- Imports the installed app against an isolated temporary database
- Verifies that the active clear_abuse_events endpoint is the v48.12.9 implementation
- Rolls back installed files if post-install verification fails

Install
-------

cd /root
unzip -o bw-monitor-v48.12.9-r4-full.zip
cd /root/bw-monitor-v48.12.9-r4-full
chmod +x install_bw_monitor_v48_12_9.sh

Preflight only:

BW_PREFLIGHT_ONLY=1 ./install_bw_monitor_v48_12_9.sh

Production upgrade with DB backup and stale-maintenance recovery:

BW_RECOVER_STUCK_MAINTENANCE=1 \
BW_BACKUP_DB=1 \
./install_bw_monitor_v48_12_9.sh

No Agent redeployment is required.

Post-install checks
-------------------

systemctl status bw-monitor --no-pager -l
systemctl status bw-monitor-retention.timer --no-pager -l
journalctl -u bw-monitor -n 200 --no-pager
curl -I http://127.0.0.1:8080/login

Verify installed release and cleanup route:

grep -n 'V48129_VERSION = "48.12.9"' /opt/bw-monitor/app.py
grep -n 'def clear_abuse_events_v48129' /opt/bw-monitor/app.py
grep -nF 'DELETE FROM vm_abuse_incidents' /opt/bw-monitor/app.py

The last command should show multiple cleanup paths, not only the incident
rebuild function.

R3 UI note
----------
CPU and RAM cells in Current Abuse use a stable compact Top VM presentation. Sorting remains selectable from the column headers and no longer changes the internal row layout.
