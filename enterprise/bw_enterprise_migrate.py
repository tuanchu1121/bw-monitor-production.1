#!/usr/bin/env python3
"""Online/backfill migration from the legacy BW Monitor SQLite DB to v49 TimescaleDB."""
from __future__ import annotations
import argparse, json, logging, os, sqlite3, sys, time, zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import psycopg
from psycopg.types.json import Jsonb

LOG=logging.getLogger("bw-enterprise-migrate")

def si(v:Any,d:int=0)->int:
    try:return int(v)
    except Exception:return d

def sf(v:Any,d:float=0.0)->float:
    try:return float(v)
    except Exception:return d

def dt(v:Any)->datetime:return datetime.fromtimestamp(max(0,si(v,int(time.time()))),tz=timezone.utc)
def txt(v:Any,n:int=4096)->str:return str(v or "")[:n]

class Migrator:
    def __init__(self, sqlite_path:str, dsn:str, batch:int=5000, force:bool=False):
        self.sqlite_path=sqlite_path; self.dsn=dsn; self.batch=max(100,min(50000,batch)); self.force=force
        self.sq=sqlite3.connect(f"file:{sqlite_path}?mode=ro",uri=True,timeout=60)
        self.sq.row_factory=sqlite3.Row
        self.pg=psycopg.connect(dsn,connect_timeout=10,application_name="bw-enterprise-migrate")
    def close(self): self.sq.close(); self.pg.close()
    def tables(self): return {r[0] for r in self.sq.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    def checkpoint(self,name:str)->tuple[int,bool,int]:
        with self.pg.cursor() as c:
            c.execute("SELECT last_id,completed,rows_migrated FROM bw.migration_checkpoint WHERE table_name=%s",(name,)); r=c.fetchone()
        return (int(r[0]),bool(r[1]),int(r[2])) if r else (0,False,0)
    def save(self,name:str,last:int,done:bool,rows:int):
        with self.pg.cursor() as c:
            c.execute("""INSERT INTO bw.migration_checkpoint(table_name,last_id,completed,rows_migrated)
                         VALUES(%s,%s,%s,%s) ON CONFLICT(table_name) DO UPDATE SET
                         last_id=excluded.last_id,completed=excluded.completed,rows_migrated=excluded.rows_migrated,updated_at=now()""",(name,last,done,rows))
        self.pg.commit()
    def run_rows(self,name:str,select_sql:str,handler:Callable[[list[sqlite3.Row]],None]):
        if name not in self.tables(): LOG.info("skip missing table=%s",name); return
        last,done,total=self.checkpoint(name)
        if done and not self.force: LOG.info("skip completed table=%s rows=%s",name,total); return
        if self.force: last=0; total=0
        while True:
            rows=self.sq.execute(select_sql,(last,self.batch)).fetchall()
            if not rows: self.save(name,last,True,total); LOG.info("completed table=%s rows=%s",name,total); return
            handler(rows); self.pg.commit(); last=si(rows[-1]["_rid"]); total+=len(rows); self.save(name,last,False,total)
            LOG.info("migrated table=%s rows=%s last=%s",name,total,last)
    def migrate_current(self):
        tables=self.tables()
        if "node_inventory" in tables:
            public_ips = {}
            private_ips = {}
            if "node_bridge_addresses_latest" in tables:
                for r in self.sq.execute("SELECT node,role,primary_ipv4 FROM node_bridge_addresses_latest").fetchall():
                    role = txt(r["role"], 32).lower()
                    if role == "public": public_ips[r["node"]] = txt(r["primary_ipv4"], 128)
                    elif role == "private": private_ips[r["node"]] = txt(r["primary_ipv4"], 128)
            vm_counts = {}
            if "vm_inventory" in tables:
                for r in self.sq.execute("SELECT node,COUNT(*) AS c FROM vm_inventory WHERE deleted_at IS NULL GROUP BY node").fetchall():
                    vm_counts[r["node"]] = si(r["c"])
            rows = self.sq.execute("SELECT node,last_push FROM node_inventory WHERE deleted_at IS NULL").fetchall()
            vals = [(r["node"],dt(r["last_push"]),si(r["last_push"]),300,0,False,vm_counts.get(r["node"],0),0,public_ips.get(r["node"],""),private_ips.get(r["node"],""),Jsonb({"source":"sqlite-migration"})) for r in rows]
            with self.pg.cursor() as c:
                c.executemany("""INSERT INTO bw.node_current(node,last_seen,push_time,interval_seconds,agent_version,inventory_complete,vm_count,iface_count,public_ipv4,private_ipv4,payload_summary)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(node) DO UPDATE SET last_seen=excluded.last_seen,push_time=excluded.push_time,vm_count=excluded.vm_count,public_ipv4=excluded.public_ipv4,private_ipv4=excluded.private_ipv4,payload_summary=excluded.payload_summary,updated_at=now()""", vals)
            self.pg.commit(); LOG.info("current nodes=%s",len(vals))
        if "vm_disk_current" in tables:
            rows=self.sq.execute("SELECT * FROM vm_disk_current").fetchall()
            vals=[(r["node"],r["vm_uuid"],r["target"],r["source"],r["role"],r["mount"],r["storage_device"],r["storage_block"],r["storage_fstype"],si(r["capacity_bytes"]),si(r["allocation_bytes"]),si(r["physical_bytes"]),sf(r["read_bps"]),sf(r["write_bps"]),sf(r["read_iops"]),sf(r["write_iops"]),dt(r["last_seen"]),si(r["last_seen"])) for r in rows]
            with self.pg.cursor() as c:
                c.executemany("""INSERT INTO bw.vm_disk_current(node,vm_uuid,target,source,role,mount,storage_device,storage_block,storage_fstype,capacity_bytes,allocation_bytes,physical_bytes,read_bps,write_bps,read_iops,write_iops,last_seen,push_time)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(node,vm_uuid,target,source) DO UPDATE SET role=excluded.role,mount=excluded.mount,storage_device=excluded.storage_device,storage_block=excluded.storage_block,storage_fstype=excluded.storage_fstype,capacity_bytes=excluded.capacity_bytes,allocation_bytes=excluded.allocation_bytes,physical_bytes=excluded.physical_bytes,read_bps=excluded.read_bps,write_bps=excluded.write_bps,read_iops=excluded.read_iops,write_iops=excluded.write_iops,last_seen=excluded.last_seen,push_time=excluded.push_time,updated_at=now()""",vals)
            self.pg.commit(); LOG.info("current vm disks=%s",len(vals))
        if "node_storage_current" in tables:
            rows=self.sq.execute("SELECT * FROM node_storage_current").fetchall(); vals=[]
            for r in rows: vals.append((r["node"],r["mount"],r["device"],r["block"],r["raid_level"],r["fstype"],si(r["size"]),si(r["used"]),si(r["avail"]),sf(r["use_percent"]),sf(r["read_bps"]),sf(r["write_bps"]),sf(r["read_iops"]),sf(r["write_iops"]),sf(r["util_percent"]),dt(r["last_seen"]),si(r["last_seen"])))
            with self.pg.cursor() as c:
                c.executemany("""INSERT INTO bw.node_storage_current(node,mount,device,block,raid_level,fstype,size_bytes,used_bytes,avail_bytes,use_percent,read_bps,write_bps,read_iops,write_iops,util_percent,last_seen,push_time)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(node,mount) DO UPDATE SET device=excluded.device,block=excluded.block,raid_level=excluded.raid_level,fstype=excluded.fstype,size_bytes=excluded.size_bytes,used_bytes=excluded.used_bytes,avail_bytes=excluded.avail_bytes,use_percent=excluded.use_percent,read_bps=excluded.read_bps,write_bps=excluded.write_bps,read_iops=excluded.read_iops,write_iops=excluded.write_iops,util_percent=excluded.util_percent,last_seen=excluded.last_seen,push_time=excluded.push_time,updated_at=now()""",vals)
            self.pg.commit(); LOG.info("current node storage=%s",len(vals))
        if "vm_latest_metrics" in tables:
            disk_iops = {}
            if "vm_disk_current" in tables:
                for d in self.sq.execute("SELECT node,vm_uuid,SUM(read_iops) AS ri,SUM(write_iops) AS wi FROM vm_disk_current WHERE role='customer' GROUP BY node,vm_uuid").fetchall():
                    disk_iops[(d["node"],d["vm_uuid"])] = (sf(d["ri"]),sf(d["wi"]))
            rows=self.sq.execute("SELECT * FROM vm_latest_metrics").fetchall(); vals=[]
            for r in rows:
                ri,wi=disk_iops.get((r["node"],r["vm_uuid"]),(0.0,0.0))
                vals.append((r["node"],r["vm_uuid"],dt(r["last_seen"]),si(r["last_seen"]),si(r["vcpu_current"]),sf(r["cpu_percent"]),si(r["ram_current_kib"]),si(r["ram_maximum_kib"]),si(r["ram_rss_kib"]),sf(r["disk_read_bps"]),sf(r["disk_write_bps"]),ri,wi))
            with self.pg.cursor() as c:
                c.executemany("""INSERT INTO bw.vm_current(node,vm_uuid,last_seen,push_time,vcpu_current,cpu_percent,ram_current_kib,ram_maximum_kib,ram_rss_kib,disk_read_bps,disk_write_bps,disk_read_iops,disk_write_iops)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(node,vm_uuid) DO UPDATE SET last_seen=excluded.last_seen,push_time=excluded.push_time,vcpu_current=excluded.vcpu_current,cpu_percent=excluded.cpu_percent,ram_current_kib=excluded.ram_current_kib,ram_maximum_kib=excluded.ram_maximum_kib,ram_rss_kib=excluded.ram_rss_kib,disk_read_bps=excluded.disk_read_bps,disk_write_bps=excluded.disk_write_bps,updated_at=now()""",vals)
            self.pg.commit(); LOG.info("current vms=%s",len(vals))
    def migrate_history(self):
        def node_stats(rows):
            vals=[]
            for r in rows:
                iv=max(1,si(r["interval_seconds"],300)); rx=si(r["rx_delta"]);tx=si(r["tx_delta"]);rxp=si(r["rx_packets_delta"]);txp=si(r["tx_packets_delta"])
                vals.append((dt(r["last_push"]),r["node"],r["vm_uuid"],r["iface"],r["bridge"],iv,rx,tx,rxp,txp,rx*8/iv/1e6,tx*8/iv/1e6,rxp/iv,txp/iv,sf(r["rx_mbps_peak"]),sf(r["tx_mbps_peak"]),sf(r["rx_pps_peak"]),sf(r["tx_pps_peak"]),si(r["rx_drop_delta"]),si(r["tx_drop_delta"]),si(r["rx_error_delta"]),si(r["tx_error_delta"]),txt(r["network_sample_quality"],32)))
            with self.pg.cursor() as c:c.executemany("INSERT INTO bw.vm_network_metrics VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",vals)
        self.run_rows("node_stats","SELECT rowid AS _rid,* FROM node_stats WHERE rowid>? ORDER BY rowid LIMIT ?",node_stats)
        def perf(rows):
            vals=[]
            for r in rows:
                iv=max(1,si(r["interval_seconds"],300));dr=si(r["disk_read_delta"]);dw=si(r["disk_write_delta"]);rr=si(r["disk_read_reqs_delta"]);wr=si(r["disk_write_reqs_delta"])
                vals.append((dt(r["time"]),r["node"],r["vm_uuid"],iv,si(r["vcpu_current"]),sf(r["cpu_percent"]),si(r["ram_current_kib"]),si(r["ram_maximum_kib"]),si(r["ram_rss_kib"]),si(r["ram_available_kib"]),si(r["ram_unused_kib"]),si(r["ram_usable_kib"]),dr,dw,rr,wr,dr/iv,dw/iv,rr/iv,wr/iv))
            with self.pg.cursor() as c:c.executemany("INSERT INTO bw.vm_perf_metrics VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",vals)
        self.run_rows("vm_perf_stats","SELECT id AS _rid,* FROM vm_perf_stats WHERE id>? ORDER BY id LIMIT ?",perf)
        def host(rows):
            vals=[(dt(r["time"]),r["node"],si(r["interval_seconds"],300),sf(r["load1"]),sf(r["load5"]),sf(r["load15"]),si(r["cpu_count"]),sf(r["cpu_percent"]),si(r["mem_total"]),si(r["mem_available"]),si(r["mem_used"]),si(r["swap_total"]),si(r["swap_used"]),sf(r["disk_read_bps"]),sf(r["disk_write_bps"]),si(r["uptime_seconds"])) for r in rows]
            with self.pg.cursor() as c:c.executemany("INSERT INTO bw.node_host_metrics VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",vals)
        self.run_rows("node_host_stats","SELECT id AS _rid,* FROM node_host_stats WHERE id>? ORDER BY id LIMIT ?",host)
        def fs(rows):
            vals=[(dt(r["time"]),r["node"],r["mount"],r["device"] or "","","",r["fstype"] or "",si(r["size"]),si(r["used"]),si(r["avail"]),sf(r["use_percent"]),0.0,0.0,0.0,0.0,0.0) for r in rows]
            with self.pg.cursor() as c:c.executemany("INSERT INTO bw.node_storage_metrics VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",vals)
        self.run_rows("node_filesystem_stats","SELECT id AS _rid,* FROM node_filesystem_stats WHERE id>? ORDER BY id LIMIT ?",fs)
        def snapshots(rows):
            vals=[(r["node"],si(r["bucket"]),si(r["push_time"]),si(r["vm_count"]),si(r["iface_count"]),txt(r["retention_tier"],32)) for r in rows]
            disk_vals=[]; storage_vals=[]
            for r in rows:
                if "storage_payload" not in r.keys() or r["storage_payload"] is None:
                    continue
                try:
                    data=json.loads(zlib.decompress(bytes(r["storage_payload"])).decode("utf-8"))
                    when=dt(data.get("t") or r["push_time"]); interval=max(1,si(data.get("i"),300)); node=r["node"]
                    for d in data.get("d") or []:
                        if not isinstance(d,list) or len(d)<14: continue
                        rb=sf(d[10]);wb=sf(d[11]);ri=sf(d[12]);wi=sf(d[13])
                        disk_vals.append((when,node,txt(d[0],255),txt(d[1],128),txt(d[2]),"customer",txt(d[3],1024),txt(d[4],1024),txt(d[5],255),txt(d[6],64),si(d[7]),si(d[8]),si(d[9]),interval,int(rb*interval),int(wb*interval),int(ri*interval),int(wi*interval),rb,wb,ri,wi))
                    for st in data.get("s") or []:
                        if not isinstance(st,list) or len(st)<14: continue
                        storage_vals.append((when,node,txt(st[0],1024),txt(st[1],1024),txt(st[2],255),txt(st[3],64),txt(st[4],64),si(st[5]),si(st[6]),si(st[7]),sf(st[8]),sf(st[9]),sf(st[10]),sf(st[11]),sf(st[12]),sf(st[13])))
                except Exception:
                    LOG.exception("could not decode retained storage payload node=%s bucket=%s",r["node"],r["bucket"])
            with self.pg.cursor() as c:
                c.executemany("INSERT INTO bw.legacy_snapshot_index(node,bucket,push_time,vm_count,iface_count,retention_tier) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",vals)
                if disk_vals:c.executemany("""INSERT INTO bw.vm_disk_metrics(time,node,vm_uuid,target,source,role,mount,storage_device,storage_block,storage_fstype,capacity_bytes,allocation_bytes,physical_bytes,interval_seconds,read_bytes,write_bytes,read_reqs,write_reqs,read_bps,write_bps,read_iops,write_iops) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",disk_vals)
                if storage_vals:c.executemany("""INSERT INTO bw.node_storage_metrics(time,node,mount,device,block,raid_level,fstype,size_bytes,used_bytes,avail_bytes,use_percent,read_bps,write_bps,read_iops,write_iops,util_percent) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",storage_vals)
        self.run_rows("node_push_snapshots","SELECT rowid AS _rid,* FROM node_push_snapshots WHERE rowid>? ORDER BY rowid LIMIT ?",snapshots)
    def refresh(self):
        with self.pg.cursor() as c:
            for view in ("bw.vm_network_5m","bw.vm_perf_5m","bw.vm_disk_5m","bw.node_storage_5m","bw.vm_network_1h","bw.vm_perf_1h","bw.vm_disk_1h","bw.node_storage_1h"):
                try:c.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)");self.pg.commit()
                except Exception:self.pg.rollback();LOG.exception("refresh failed %s",view)


def main()->int:
    p=argparse.ArgumentParser();p.add_argument("--sqlite",default=os.environ.get("BW_MONITOR_DB","/opt/bw-monitor/bandwidth.db"));p.add_argument("--dsn",default=os.environ.get("BW_ENTERPRISE_PG_DSN",""));p.add_argument("--batch",type=int,default=5000);p.add_argument("--current-only",action="store_true");p.add_argument("--history-only",action="store_true");p.add_argument("--force",action="store_true");p.add_argument("--refresh",action="store_true");p.add_argument("--log-level",default="INFO");a=p.parse_args()
    logging.basicConfig(level=getattr(logging,a.log_level.upper(),logging.INFO),format="%(asctime)s %(levelname)s %(message)s")
    if not a.dsn: p.error("--dsn or BW_ENTERPRISE_PG_DSN is required")
    if not Path(a.sqlite).is_file(): p.error(f"SQLite DB not found: {a.sqlite}")
    m=Migrator(a.sqlite,a.dsn,a.batch,a.force)
    try:
        if not a.history_only:m.migrate_current()
        if not a.current_only:m.migrate_history()
        if a.refresh:m.refresh()
    finally:m.close()
    return 0
if __name__=="__main__":raise SystemExit(main())
