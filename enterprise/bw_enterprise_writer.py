#!/usr/bin/env python3
"""BW Monitor v49 asynchronous TimescaleDB writer.

Consumes accepted agent payloads from Redis Streams, keeps current projections in
PostgreSQL and appends high-volume metrics to Timescale hypertables.  The legacy
SQLite application remains the compatibility/control database, so a Timescale
outage never blocks /push or the dashboard.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import socket
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import psycopg
from psycopg.types.json import Jsonb
import redis

LOG = logging.getLogger("bw-enterprise-writer")
STOP = False


def env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def text(value: Any, limit: int = 4096) -> str:
    return str(value or "")[:limit]


def utc_from_epoch(value: Any) -> datetime:
    return datetime.fromtimestamp(max(0, safe_int(value, int(time.time()))), tz=timezone.utc)


def iter_dicts(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                yield item


def json_dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


class EnterpriseWriter:
    def __init__(self) -> None:
        self.pg_dsn = os.environ.get("BW_ENTERPRISE_PG_DSN", "").strip()
        self.redis_url = os.environ.get("BW_REDIS_URL", "redis://127.0.0.1:6379/0")
        self.stream = os.environ.get("BW_ENTERPRISE_STREAM", "bw:enterprise:ingest:v1")
        self.group = os.environ.get("BW_ENTERPRISE_CONSUMER_GROUP", "bw-enterprise-writers")
        self.consumer = os.environ.get("BW_ENTERPRISE_CONSUMER", f"{socket.gethostname()}-{os.getpid()}")
        self.block_ms = env_int("BW_ENTERPRISE_STREAM_BLOCK_MS", 5000)
        self.batch = max(1, min(500, env_int("BW_ENTERPRISE_STREAM_BATCH", 50)))
        self.claim_idle_ms = max(30000, env_int("BW_ENTERPRISE_CLAIM_IDLE_MS", 120000))
        self.max_retries = max(1, env_int("BW_ENTERPRISE_MAX_RETRIES", 8))
        self.retain_acked = max(1000, env_int("BW_ENTERPRISE_STREAM_RETAIN_ACKED", 10000))
        self.store_raw = os.environ.get("BW_ENTERPRISE_STORE_RAW_PUSH", "0") == "1"
        self.spool = Path(os.environ.get("BW_ENTERPRISE_SPOOL", "/var/lib/bw-monitor-enterprise/spool"))
        self.spool_inbox = self.spool / "inbox"
        self.spool_bad = self.spool / "bad"
        self.spool_inbox.mkdir(parents=True, exist_ok=True)
        self.spool_bad.mkdir(parents=True, exist_ok=True)
        if not self.pg_dsn:
            raise RuntimeError("BW_ENTERPRISE_PG_DSN is required")
        self.redis = redis.Redis.from_url(self.redis_url, decode_responses=True, socket_timeout=5, socket_connect_timeout=3)
        self._ensure_group()

    def _ensure_group(self) -> None:
        try:
            self.redis.xgroup_create(self.stream, self.group, id="0-0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def pg(self) -> psycopg.Connection:
        return psycopg.connect(self.pg_dsn, connect_timeout=10, application_name="bw-enterprise-writer")

    @staticmethod
    def _bridge_ips(payload: dict[str, Any]) -> tuple[str, str]:
        public = private = ""
        for item in iter_dicts(payload.get("bridge_addresses")):
            role = text(item.get("role"), 32).lower()
            value = text(item.get("primary_ipv4"), 128)
            if role == "public" and not public:
                public = value
            elif role == "private" and not private:
                private = value
        return public, private

    def ingest(self, payload: dict[str, Any], stream_id: str = "") -> str:
        node = text(payload.get("node"), 255).strip()
        push_time = safe_int(payload.get("time"), 0)
        if not node or push_time <= 0:
            raise ValueError("payload must contain node and positive time")
        sample_time = utc_from_epoch(push_time)
        interval = max(1, min(3600, safe_int(payload.get("interval"), 300)))
        agent_version = safe_int(payload.get("version"), 0)
        vms = list(iter_dicts(payload.get("vms")))
        interfaces = list(iter_dicts(payload.get("interfaces")))
        physical = list(iter_dicts(payload.get("physical_interfaces")))
        node_host = payload.get("node_host") if isinstance(payload.get("node_host"), dict) else {}
        health = payload.get("agent_health") if isinstance(payload.get("agent_health"), dict) else {}
        public_ip, private_ip = self._bridge_ips(payload)

        with self.pg() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT scope,key,cutoff_push_time FROM bw.purge_tombstones WHERE (scope='node' AND key=%s) OR (scope='node_vms' AND key=%s) OR (scope='vm' AND key=ANY(%s::text[]))", (node,node,[text(v.get("vm_uuid"),255) for v in vms if v.get("vm_uuid")]))
                tombstones = cur.fetchall()
            node_cutoff = max((safe_int(r[2]) for r in tombstones if r[0]=='node'), default=0)
            if node_cutoff >= push_time:
                return "tombstoned-node"
            node_vms_cutoff = max((safe_int(r[2]) for r in tombstones if r[0]=='node_vms'), default=0)
            vm_cutoffs = {str(r[1]): safe_int(r[2]) for r in tombstones if r[0]=='vm'}
            if node_vms_cutoff >= push_time:
                vms = []
                interfaces = []
            else:
                blocked = {u for u,c in vm_cutoffs.items() if c >= push_time}
                if blocked:
                    vms = [v for v in vms if text(v.get("vm_uuid"),255) not in blocked]
                    interfaces = [i for i in interfaces if text(i.get("vm_uuid"),255) not in blocked]

            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO bw.ingest_receipts(node,push_time,stream_id)
                       VALUES(%s,%s,%s) ON CONFLICT DO NOTHING RETURNING node""",
                    (node, push_time, stream_id or None),
                )
                if cur.fetchone() is None:
                    return "duplicate"

                summary = {
                    "vm_count": len(vms),
                    "iface_count": len(interfaces),
                    "physical_iface_count": len(physical),
                    "filesystems": len(node_host.get("filesystems") or []),
                    "storage_devices": len(node_host.get("storage_devices") or []),
                }
                raw_payload = payload if self.store_raw else {"redacted": True, "node": node, "time": push_time, "summary": summary}
                cur.execute(
                    """INSERT INTO bw.agent_push_raw(time,node,push_time,interval_seconds,agent_version,payload)
                       VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (sample_time, node, push_time, interval, agent_version, Jsonb(raw_payload)),
                )
                cur.execute(
                    """INSERT INTO bw.node_current(
                           node,last_seen,push_time,interval_seconds,agent_version,inventory_complete,
                           vm_count,iface_count,public_ipv4,private_ipv4,payload_summary)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT(node) DO UPDATE SET
                         last_seen=excluded.last_seen,push_time=excluded.push_time,
                         interval_seconds=excluded.interval_seconds,agent_version=excluded.agent_version,
                         inventory_complete=excluded.inventory_complete,vm_count=excluded.vm_count,
                         iface_count=excluded.iface_count,public_ipv4=excluded.public_ipv4,
                         private_ipv4=excluded.private_ipv4,payload_summary=excluded.payload_summary,
                         updated_at=now()""",
                    (
                        node, sample_time, push_time, interval, agent_version,
                        bool(payload.get("inventory_complete")), len(vms), len(interfaces),
                        public_ip, private_ip, Jsonb(summary),
                    ),
                )

                self._insert_network(cur, node, sample_time, interval, interfaces)
                self._insert_vms(cur, node, sample_time, push_time, interval, vms)
                self._insert_node(cur, node, sample_time, push_time, interval, node_host)
                self._insert_physical(cur, node, sample_time, interval, physical)
                self._insert_health(cur, node, sample_time, interval, agent_version, health)

                if payload.get("inventory_complete") is True:
                    cur.execute("DELETE FROM bw.vm_current WHERE node=%s AND push_time<%s", (node, push_time))
                    cur.execute("DELETE FROM bw.vm_disk_current WHERE node=%s AND push_time<%s", (node, push_time))
                cur.execute("DELETE FROM bw.node_storage_current WHERE node=%s AND push_time<%s", (node, push_time))
            conn.commit()
        return "inserted"

    def _insert_network(self, cur: psycopg.Cursor, node: str, when: datetime, interval: int, rows: list[dict[str, Any]]) -> None:
        values = []
        for row in rows:
            vm_uuid = text(row.get("vm_uuid"), 255).strip()
            if not vm_uuid:
                continue
            ri = max(1, safe_int(row.get("interval_seconds"), interval))
            rx = max(0, safe_int(row.get("rx_delta"), 0)); tx = max(0, safe_int(row.get("tx_delta"), 0))
            rxp = max(0, safe_int(row.get("rx_packets_delta"), 0)); txp = max(0, safe_int(row.get("tx_packets_delta"), 0))
            values.append((
                when,node,vm_uuid,text(row.get("iface"),128),text(row.get("bridge"),128),ri,
                rx,tx,rxp,txp,rx*8.0/ri/1_000_000.0,tx*8.0/ri/1_000_000.0,
                rxp/float(ri),txp/float(ri),safe_float(row.get("rx_mbps_peak")),safe_float(row.get("tx_mbps_peak")),
                safe_float(row.get("rx_pps_peak")),safe_float(row.get("tx_pps_peak")),
                max(0,safe_int(row.get("rx_drop_delta"))),max(0,safe_int(row.get("tx_drop_delta"))),
                max(0,safe_int(row.get("rx_error_delta"))),max(0,safe_int(row.get("tx_error_delta"))),
                text(row.get("network_sample_quality") or row.get("sample_quality") or "LEGACY",32),
            ))
        if values:
            cur.executemany(
                """INSERT INTO bw.vm_network_metrics(
                    time,node,vm_uuid,iface,bridge,interval_seconds,rx_bytes,tx_bytes,rx_packets,tx_packets,
                    rx_mbps,tx_mbps,rx_pps,tx_pps,rx_mbps_peak,tx_mbps_peak,rx_pps_peak,tx_pps_peak,
                    rx_drops,tx_drops,rx_errors,tx_errors,quality)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                values,
            )

    def _insert_vms(self, cur: psycopg.Cursor, node: str, when: datetime, push_time: int, interval: int, rows: list[dict[str, Any]]) -> None:
        perf_values = []
        current_values = []
        disk_values = []
        disk_current = []
        for row in rows:
            vm_uuid = text(row.get("vm_uuid"),255).strip()
            if not vm_uuid:
                continue
            ri = max(1, safe_int(row.get("interval_seconds"), interval))
            dr = max(0,safe_int(row.get("disk_read_delta"))); dw = max(0,safe_int(row.get("disk_write_delta")))
            drr = max(0,safe_int(row.get("disk_read_reqs_delta"))); dwr = max(0,safe_int(row.get("disk_write_reqs_delta")))
            perf_values.append((
                when,node,vm_uuid,ri,safe_int(row.get("vcpu_current")),safe_float(row.get("cpu_percent")),
                safe_int(row.get("ram_current_kib")),safe_int(row.get("ram_maximum_kib")),safe_int(row.get("ram_rss_kib")),
                safe_int(row.get("ram_available_kib")),safe_int(row.get("ram_unused_kib")),safe_int(row.get("ram_usable_kib")),
                dr,dw,drr,dwr,dr/float(ri),dw/float(ri),drr/float(ri),dwr/float(ri),
            ))
            current_values.append((
                node,vm_uuid,when,push_time,safe_int(row.get("vcpu_current")),safe_float(row.get("cpu_percent")),
                safe_int(row.get("ram_current_kib")),safe_int(row.get("ram_maximum_kib")),safe_int(row.get("ram_rss_kib")),
                dr/float(ri),dw/float(ri),drr/float(ri),dwr/float(ri),
            ))
            for disk in iter_dicts(row.get("disks")):
                target = text(disk.get("target"),128).strip()
                if not target:
                    continue
                di = max(1,safe_int(disk.get("interval_seconds"),ri))
                rd = max(0,safe_int(disk.get("read_delta"))); wd = max(0,safe_int(disk.get("write_delta")))
                rr = max(0,safe_int(disk.get("read_reqs_delta"))); wr = max(0,safe_int(disk.get("write_reqs_delta")))
                common = (
                    node,vm_uuid,target,text(disk.get("source"),4096),text(disk.get("role") or "unknown",32),
                    text(disk.get("mount"),1024),text(disk.get("storage_device"),1024),text(disk.get("storage_block"),255),
                    text(disk.get("storage_fstype"),64),max(0,safe_int(disk.get("capacity_bytes"))),
                    max(0,safe_int(disk.get("allocation_bytes"))),max(0,safe_int(disk.get("physical_bytes"))),
                    di,rd,wd,rr,wr,rd/float(di),wd/float(di),rr/float(di),wr/float(di),
                )
                disk_values.append((when,) + common)
                disk_current.append(common[:12] + common[17:21] + (when,push_time))
        if perf_values:
            cur.executemany(
                """INSERT INTO bw.vm_perf_metrics(
                    time,node,vm_uuid,interval_seconds,vcpu_current,cpu_percent,ram_current_kib,ram_maximum_kib,
                    ram_rss_kib,ram_available_kib,ram_unused_kib,ram_usable_kib,disk_read_bytes,disk_write_bytes,
                    disk_read_reqs,disk_write_reqs,disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                perf_values,
            )
        if current_values:
            cur.executemany(
                """INSERT INTO bw.vm_current(
                    node,vm_uuid,last_seen,push_time,vcpu_current,cpu_percent,ram_current_kib,ram_maximum_kib,
                    ram_rss_kib,disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(node,vm_uuid) DO UPDATE SET
                    last_seen=excluded.last_seen,push_time=excluded.push_time,vcpu_current=excluded.vcpu_current,
                    cpu_percent=excluded.cpu_percent,ram_current_kib=excluded.ram_current_kib,
                    ram_maximum_kib=excluded.ram_maximum_kib,ram_rss_kib=excluded.ram_rss_kib,
                    disk_read_bps=excluded.disk_read_bps,disk_write_bps=excluded.disk_write_bps,
                    disk_read_iops=excluded.disk_read_iops,disk_write_iops=excluded.disk_write_iops,updated_at=now()""",
                current_values,
            )
        if disk_values:
            cur.executemany(
                """INSERT INTO bw.vm_disk_metrics(
                    time,node,vm_uuid,target,source,role,mount,storage_device,storage_block,storage_fstype,
                    capacity_bytes,allocation_bytes,physical_bytes,interval_seconds,read_bytes,write_bytes,
                    read_reqs,write_reqs,read_bps,write_bps,read_iops,write_iops)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                disk_values,
            )
        if disk_current:
            cur.executemany(
                """INSERT INTO bw.vm_disk_current(
                    node,vm_uuid,target,source,role,mount,storage_device,storage_block,storage_fstype,
                    capacity_bytes,allocation_bytes,physical_bytes,read_bps,write_bps,read_iops,write_iops,last_seen,push_time)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(node,vm_uuid,target,source) DO UPDATE SET
                    role=excluded.role,mount=excluded.mount,storage_device=excluded.storage_device,
                    storage_block=excluded.storage_block,storage_fstype=excluded.storage_fstype,
                    capacity_bytes=excluded.capacity_bytes,allocation_bytes=excluded.allocation_bytes,
                    physical_bytes=excluded.physical_bytes,read_bps=excluded.read_bps,write_bps=excluded.write_bps,
                    read_iops=excluded.read_iops,write_iops=excluded.write_iops,last_seen=excluded.last_seen,
                    push_time=excluded.push_time,updated_at=now()""",
                disk_current,
            )

    def _insert_node(self, cur: psycopg.Cursor, node: str, when: datetime, push_time: int, interval: int, host: dict[str, Any]) -> None:
        if not host:
            return
        cur.execute(
            """INSERT INTO bw.node_host_metrics(
                time,node,interval_seconds,load1,load5,load15,cpu_count,cpu_percent,mem_total,mem_available,
                mem_used,swap_total,swap_used,disk_read_bps,disk_write_bps,uptime_seconds)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                when,node,interval,safe_float(host.get("load1")),safe_float(host.get("load5")),safe_float(host.get("load15")),
                safe_int(host.get("cpu_count")),safe_float(host.get("cpu_percent")),safe_int(host.get("mem_total")),
                safe_int(host.get("mem_available")),safe_int(host.get("mem_used")),safe_int(host.get("swap_total")),
                safe_int(host.get("swap_used")),safe_float(host.get("disk_read_bps")),safe_float(host.get("disk_write_bps")),
                safe_int(host.get("uptime_seconds")),
            ),
        )
        storage_values = []
        current_values = []
        rows = host.get("storage_devices") or host.get("filesystems") or []
        for row in iter_dicts(rows):
            mount = text(row.get("mount"),1024).strip()
            if not mount:
                continue
            values = (
                node,mount,text(row.get("device"),1024),text(row.get("block"),255),text(row.get("raid_level"),64),
                text(row.get("fstype"),64),safe_int(row.get("size")),safe_int(row.get("used")),safe_int(row.get("avail")),
                safe_float(row.get("use_percent")),safe_float(row.get("read_bps")),safe_float(row.get("write_bps")),
                safe_float(row.get("read_iops")),safe_float(row.get("write_iops")),safe_float(row.get("util_percent")),
            )
            storage_values.append((when,) + values)
            current_values.append(values + (when,push_time))
        if storage_values:
            cur.executemany(
                """INSERT INTO bw.node_storage_metrics(
                    time,node,mount,device,block,raid_level,fstype,size_bytes,used_bytes,avail_bytes,use_percent,
                    read_bps,write_bps,read_iops,write_iops,util_percent)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                storage_values,
            )
        if current_values:
            cur.executemany(
                """INSERT INTO bw.node_storage_current(
                    node,mount,device,block,raid_level,fstype,size_bytes,used_bytes,avail_bytes,use_percent,
                    read_bps,write_bps,read_iops,write_iops,util_percent,last_seen,push_time)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(node,mount) DO UPDATE SET
                    device=excluded.device,block=excluded.block,raid_level=excluded.raid_level,fstype=excluded.fstype,
                    size_bytes=excluded.size_bytes,used_bytes=excluded.used_bytes,avail_bytes=excluded.avail_bytes,
                    use_percent=excluded.use_percent,read_bps=excluded.read_bps,write_bps=excluded.write_bps,
                    read_iops=excluded.read_iops,write_iops=excluded.write_iops,util_percent=excluded.util_percent,
                    last_seen=excluded.last_seen,push_time=excluded.push_time,updated_at=now()""",
                current_values,
            )

    def _insert_physical(self, cur: psycopg.Cursor, node: str, when: datetime, interval: int, rows: list[dict[str, Any]]) -> None:
        values = []
        for row in rows:
            ri = max(1,safe_int(row.get("interval_seconds"),interval))
            rx=max(0,safe_int(row.get("rx_delta"))); tx=max(0,safe_int(row.get("tx_delta")))
            rxp=max(0,safe_int(row.get("rx_packets_delta"))); txp=max(0,safe_int(row.get("tx_packets_delta")))
            values.append((when,node,text(row.get("role"),32),text(row.get("bridge"),128),text(row.get("iface"),128),ri,
                           rx,tx,rxp,txp,rx*8.0/ri/1_000_000.0,tx*8.0/ri/1_000_000.0,rxp/float(ri),txp/float(ri),
                           safe_int(row.get("rx_drop_delta")),safe_int(row.get("tx_drop_delta")),safe_int(row.get("rx_error_delta")),safe_int(row.get("tx_error_delta"))))
        if values:
            cur.executemany(
                """INSERT INTO bw.physical_network_metrics(
                    time,node,role,bridge,iface,interval_seconds,rx_bytes,tx_bytes,rx_packets,tx_packets,
                    rx_mbps,tx_mbps,rx_pps,tx_pps,rx_drops,tx_drops,rx_errors,tx_errors)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                values,
            )

    def _insert_health(self, cur: psycopg.Cursor, node: str, when: datetime, interval: int, version: int, health: dict[str, Any]) -> None:
        if not health:
            return
        timings = health.get("timings") if isinstance(health.get("timings"),dict) else {}
        counts = health.get("counts") if isinstance(health.get("counts"),dict) else {}
        errors = health.get("errors") if isinstance(health.get("errors"),list) else []
        cur.execute(
            """INSERT INTO bw.agent_health_metrics(
                time,node,agent_version,interval_seconds,duration_ms,virsh_list_ms,vm_network_ms,vm_perf_ms,
                node_host_ms,physical_network_ms,vm_names,interfaces,vms,physical_interfaces,error_count,overloaded,errors)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (when,node,version,interval,safe_int(health.get("duration_ms")),safe_int(timings.get("virsh_list_ms")),
             safe_int(timings.get("vm_network_ms")),safe_int(timings.get("vm_perf_ms")),safe_int(timings.get("node_host_ms")),
             safe_int(timings.get("physical_network_ms")),safe_int(counts.get("vm_names")),safe_int(counts.get("interfaces")),
             safe_int(counts.get("vms")),safe_int(counts.get("physical_interfaces")),len(errors),bool(health.get("overloaded")),Jsonb(errors)),
        )

    def _refresh_ranges(self, ranges: dict[str, tuple[datetime | None, datetime | None]]) -> None:
        mapping = {
            "network": ("bw.vm_network_5m", "bw.vm_network_1h"),
            "perf": ("bw.vm_perf_5m", "bw.vm_perf_1h"),
            "disk": ("bw.vm_disk_5m", "bw.vm_disk_1h"),
            "storage": ("bw.node_storage_5m", "bw.node_storage_1h"),
        }
        conn = self.pg()
        conn.autocommit = True
        try:
            with conn.cursor() as cur:
                for kind, (start, end) in ranges.items():
                    if start is None or end is None:
                        continue
                    start = start.replace(second=0, microsecond=0)
                    end = end.replace(second=0, microsecond=0)
                    for view in mapping.get(kind, ()):
                        try:
                            cur.execute("CALL refresh_continuous_aggregate(%s,%s,%s)", (view, start, end))
                        except Exception:
                            LOG.exception("continuous aggregate refresh failed view=%s", view)
                            raise
        finally:
            conn.close()

    @staticmethod
    def _range_for(cur: psycopg.Cursor, table: str, where: str, params: tuple[Any, ...]) -> tuple[datetime | None, datetime | None]:
        cur.execute(f"SELECT min(time),max(time) FROM {table} WHERE {where}", params)
        row = cur.fetchone()
        if not row or row[0] is None or row[1] is None:
            return None, None
        from datetime import timedelta
        return row[0] - timedelta(minutes=5), row[1] + timedelta(hours=1, minutes=5)

    def process_control(self, envelope: dict[str, Any], control_id: str = "") -> str:
        action = text(envelope.get("action"), 64)
        node = text(envelope.get("node"), 255)
        vm_uuid = text(envelope.get("vm_uuid"), 255)
        cutoff = max(1, safe_int(envelope.get("time"), int(time.time())))
        if action not in {"purge_vm", "purge_node_vms", "purge_node"}:
            raise ValueError(f"unknown control action: {action}")
        with self.pg() as conn, conn.cursor() as cur:
            detail = Jsonb({"node": node, "vm_uuid": vm_uuid, "control_id": control_id})
            if action == "purge_vm":
                if not vm_uuid:
                    raise ValueError("purge_vm requires vm_uuid")
                cur.execute("INSERT INTO bw.purge_tombstones(scope,key,cutoff_push_time,detail) VALUES('vm',%s,%s,%s) ON CONFLICT(scope,key) DO UPDATE SET cutoff_push_time=GREATEST(bw.purge_tombstones.cutoff_push_time,excluded.cutoff_push_time),purged_at=now(),detail=excluded.detail", (vm_uuid,cutoff,detail))
                ranges = {
                    "network": self._range_for(cur,"bw.vm_network_metrics","vm_uuid=%s",(vm_uuid,)),
                    "perf": self._range_for(cur,"bw.vm_perf_metrics","vm_uuid=%s",(vm_uuid,)),
                    "disk": self._range_for(cur,"bw.vm_disk_metrics","vm_uuid=%s",(vm_uuid,)),
                }
                cur.execute("DELETE FROM bw.vm_network_metrics WHERE vm_uuid=%s",(vm_uuid,))
                cur.execute("DELETE FROM bw.vm_perf_metrics WHERE vm_uuid=%s",(vm_uuid,))
                cur.execute("DELETE FROM bw.vm_disk_metrics WHERE vm_uuid=%s",(vm_uuid,))
                cur.execute("DELETE FROM bw.vm_current WHERE vm_uuid=%s",(vm_uuid,))
                cur.execute("DELETE FROM bw.vm_disk_current WHERE vm_uuid=%s",(vm_uuid,))
            elif action == "purge_node_vms":
                if not node:
                    raise ValueError("purge_node_vms requires node")
                cur.execute("INSERT INTO bw.purge_tombstones(scope,key,cutoff_push_time,detail) VALUES('node_vms',%s,%s,%s) ON CONFLICT(scope,key) DO UPDATE SET cutoff_push_time=GREATEST(bw.purge_tombstones.cutoff_push_time,excluded.cutoff_push_time),purged_at=now(),detail=excluded.detail",(node,cutoff,detail))
                ranges={
                    "network": self._range_for(cur,"bw.vm_network_metrics","node=%s",(node,)),
                    "perf": self._range_for(cur,"bw.vm_perf_metrics","node=%s",(node,)),
                    "disk": self._range_for(cur,"bw.vm_disk_metrics","node=%s",(node,)),
                }
                for table in ("bw.vm_network_metrics","bw.vm_perf_metrics","bw.vm_disk_metrics","bw.vm_current","bw.vm_disk_current"):
                    cur.execute(f"DELETE FROM {table} WHERE node=%s",(node,))
            else:
                if not node:
                    raise ValueError("purge_node requires node")
                cur.execute("INSERT INTO bw.purge_tombstones(scope,key,cutoff_push_time,detail) VALUES('node',%s,%s,%s) ON CONFLICT(scope,key) DO UPDATE SET cutoff_push_time=GREATEST(bw.purge_tombstones.cutoff_push_time,excluded.cutoff_push_time),purged_at=now(),detail=excluded.detail",(node,cutoff,detail))
                ranges={
                    "network": self._range_for(cur,"bw.vm_network_metrics","node=%s",(node,)),
                    "perf": self._range_for(cur,"bw.vm_perf_metrics","node=%s",(node,)),
                    "disk": self._range_for(cur,"bw.vm_disk_metrics","node=%s",(node,)),
                    "storage": self._range_for(cur,"bw.node_storage_metrics","node=%s",(node,)),
                }
                for table in ("bw.vm_network_metrics","bw.vm_perf_metrics","bw.vm_disk_metrics","bw.node_host_metrics","bw.node_storage_metrics","bw.physical_network_metrics","bw.agent_health_metrics","bw.vm_current","bw.vm_disk_current","bw.node_storage_current","bw.node_current","bw.agent_push_raw","bw.ingest_receipts"):
                    cur.execute(f"DELETE FROM {table} WHERE node=%s",(node,))
            conn.commit()
        self._refresh_ranges(ranges)
        LOG.warning("processed control action=%s node=%s vm_uuid=%s", action, node, vm_uuid)
        return action

    def _spool_path_from_field(self, value: str) -> Path | None:
        if not value:
            return None
        try:
            candidate = Path(value).resolve()
            root = self.spool_inbox.resolve()
            candidate.relative_to(root)
            return candidate
        except Exception:
            LOG.warning("ignored unsafe spool path=%r", value)
            return None

    def _remove_spool_field(self, fields: dict[str, str]) -> None:
        path = self._spool_path_from_field(fields.get("spool_file") or "")
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                LOG.exception("could not remove committed spool file=%s", path)

    def process_stream_entry(self, stream_id: str, fields: dict[str, str]) -> bool:
        raw = fields.get("payload") or ""
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("payload is not an object")
            if (fields.get("kind") or payload.get("_bw_kind")) == "control":
                result = self.process_control(payload, stream_id)
            else:
                result = self.ingest(payload, stream_id)
            self.redis.xack(self.stream, self.group, stream_id)
            self.redis.hdel(f"{self.stream}:failures", stream_id)
            self._remove_spool_field(fields)
            LOG.info("%s node=%s time=%s stream=%s", result, payload.get("node"), payload.get("time"), stream_id)
            return True
        except Exception as exc:
            failures = self.redis.hincrby(f"{self.stream}:failures", stream_id, 1)
            LOG.exception("ingest failed stream=%s attempt=%s", stream_id, failures)
            if failures >= self.max_retries:
                self._dead_letter(stream_id, raw, exc, fields)
            return False

    def _dead_letter(self, stream_id: str, raw: str, exc: Exception, fields: dict[str, str] | None = None) -> None:
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {"raw": raw[:100000]}
        try:
            with self.pg() as conn, conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO bw.dead_letters(stream_id,node,push_time,error,payload) VALUES(%s,%s,%s,%s,%s)",
                    (stream_id,text(payload.get("node"),255),safe_int(payload.get("time"),0),text(exc,4000),Jsonb(payload)),
                )
                conn.commit()
            self.redis.xack(self.stream,self.group,stream_id)
            self.redis.hdel(f"{self.stream}:failures",stream_id)
            if fields:
                path = self._spool_path_from_field(fields.get("spool_file") or "")
                if path is not None and path.exists():
                    try:
                        path.replace(self.spool_bad / path.name)
                    except Exception:
                        LOG.exception("could not move dead-letter spool file=%s", path)
            LOG.error("dead-lettered stream=%s",stream_id)
        except Exception:
            LOG.exception("could not dead-letter stream=%s",stream_id)

    def process_spool(self, limit: int = 100) -> int:
        count = 0
        for path in sorted(self.spool_inbox.glob("*.json"))[:limit]:
            fail_path = path.with_suffix(path.suffix + ".fail")
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if payload.get("_bw_kind") == "control":
                    self.process_control(payload, f"spool:{path.name}")
                else:
                    self.ingest(payload, f"spool:{path.name}")
                path.unlink(missing_ok=True)
                fail_path.unlink(missing_ok=True)
                count += 1
            except (psycopg.OperationalError, psycopg.InterfaceError):
                LOG.exception("spool delayed because PostgreSQL is unavailable path=%s", path)
                break
            except Exception as exc:
                LOG.exception("spool ingest failed path=%s", path)
                failures = 1
                try:
                    failures = int(fail_path.read_text().strip() or "0") + 1 if fail_path.exists() else 1
                    fail_path.write_text(str(failures), encoding="ascii")
                except Exception:
                    pass
                if failures >= self.max_retries:
                    try:
                        payload = json.loads(path.read_text(encoding="utf-8"))
                    except Exception:
                        payload = {"raw_file": path.name}
                    try:
                        with self.pg() as conn, conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO bw.dead_letters(stream_id,node,push_time,error,payload) VALUES(%s,%s,%s,%s,%s)",
                                (f"spool:{path.name}", text(payload.get("node"),255), safe_int(payload.get("time"),0), text(exc,4000), Jsonb(payload)),
                            )
                            conn.commit()
                        path.replace(self.spool_bad / path.name)
                        fail_path.unlink(missing_ok=True)
                    except Exception:
                        LOG.exception("could not dead-letter spool path=%s", path)
        return count

    def trim_stream(self) -> None:
        """Trim only acknowledged history; never trim pending/unprocessed entries."""
        try:
            groups = self.redis.xinfo_groups(self.stream)
            group = next((g for g in groups if g.get("name") == self.group), None)
            pending = safe_int(group.get("pending"), 0) if group else 0
            if pending <= 0:
                self.redis.xtrim(self.stream, maxlen=self.retain_acked, approximate=True)
                return
            oldest = self.redis.xpending_range(self.stream, self.group, min="-", max="+", count=1)
            if oldest:
                message_id = oldest[0].get("message_id") if isinstance(oldest[0], dict) else oldest[0][0]
                if message_id:
                    self.redis.xtrim(self.stream, minid=message_id, approximate=False)
        except Exception:
            LOG.exception("safe stream trim failed")

    def reclaim(self) -> int:
        try:
            result = self.redis.xautoclaim(self.stream,self.group,self.consumer,min_idle_time=self.claim_idle_ms,start_id="0-0",count=self.batch)
            entries = result[1] if isinstance(result,(list,tuple)) and len(result)>1 else []
            for stream_id, fields in entries:
                self.process_stream_entry(stream_id,fields)
            return len(entries)
        except Exception:
            LOG.exception("pending reclaim failed")
            return 0

    def run(self) -> None:
        LOG.info("writer started consumer=%s stream=%s group=%s",self.consumer,self.stream,self.group)
        last_reclaim = 0.0
        last_spool = 0.0
        last_trim = 0.0
        while not STOP:
            try:
                if time.monotonic()-last_reclaim > 30:
                    self.reclaim(); last_reclaim=time.monotonic()
                messages = self.redis.xreadgroup(self.group,self.consumer,{self.stream:">"},count=self.batch,block=self.block_ms)
                for _stream, entries in messages:
                    for stream_id, fields in entries:
                        self.process_stream_entry(stream_id,fields)
                if time.monotonic()-last_spool > 15:
                    self.process_spool(50); last_spool=time.monotonic()
                if time.monotonic()-last_trim > 60:
                    self.trim_stream(); last_trim=time.monotonic()
            except redis.RedisError:
                LOG.exception("redis unavailable; draining durable spool directly")
                try:
                    self.process_spool(100)
                except Exception:
                    LOG.exception("direct spool drain failed")
                time.sleep(3)
            except psycopg.Error:
                LOG.exception("postgres unavailable; stream and spool retained")
                time.sleep(3)
            except Exception:
                LOG.exception("writer loop error")
                time.sleep(2)
        LOG.info("writer stopped")


def self_test() -> int:
    sample = {
        "node":"node-1","time":1700000000,"interval":300,"version":12,
        "interfaces":[{"vm_uuid":"u1","iface":"vnet0","rx_delta":300000,"tx_delta":600000,"rx_packets_delta":300,"tx_packets_delta":600}],
        "vms":[{"vm_uuid":"u1","vcpu_current":2,"cpu_percent":50,"ram_current_kib":1024,"ram_maximum_kib":2048,
                "disk_read_delta":3000,"disk_write_delta":6000,"disk_read_reqs_delta":3,"disk_write_reqs_delta":6,
                "disks":[{"target":"vda","source":"/home/u1_1.img","role":"customer","mount":"/home","capacity_bytes":10000,"allocation_bytes":5000,"read_delta":3000,"write_delta":6000,"read_reqs_delta":3,"write_reqs_delta":6,"interval_seconds":300}]}],
        "node_host":{"storage_devices":[{"mount":"/home","device":"/dev/md0","size":100000,"used":50000,"read_bps":10,"write_bps":20}]},
    }
    assert sample["vms"][0]["disks"][0]["write_delta"]/300 == 20
    assert utc_from_epoch(sample["time"]).tzinfo is not None
    print("PASS: bw_enterprise_writer normalization self-test")
    return 0


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--self-test",action="store_true")
    parser.add_argument("--once",action="store_true",help="process spool and one stream batch, then exit")
    parser.add_argument("--log-level",default=os.environ.get("BW_ENTERPRISE_LOG_LEVEL","INFO"))
    args=parser.parse_args()
    logging.basicConfig(level=getattr(logging,args.log_level.upper(),logging.INFO),format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if args.self_test:
        return self_test()
    writer=EnterpriseWriter()
    if args.once:
        writer.process_spool(1000)
        messages=writer.redis.xreadgroup(writer.group,writer.consumer,{writer.stream:">"},count=writer.batch,block=1)
        for _stream,entries in messages:
            for stream_id,fields in entries: writer.process_stream_entry(stream_id,fields)
        return 0
    writer.run(); return 0


def _stop(*_args: Any) -> None:
    global STOP
    STOP=True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM,_stop); signal.signal(signal.SIGINT,_stop)
    raise SystemExit(main())
