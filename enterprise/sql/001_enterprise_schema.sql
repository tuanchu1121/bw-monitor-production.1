\set ON_ERROR_STOP on
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS bw;

CREATE TABLE IF NOT EXISTS bw.enterprise_meta (
  key text PRIMARY KEY,
  value text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO bw.enterprise_meta(key,value)
VALUES ('schema_version','49.0.0')
ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=now();

CREATE TABLE IF NOT EXISTS bw.ingest_receipts (
  node text NOT NULL,
  push_time bigint NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  stream_id text,
  PRIMARY KEY(node,push_time)
);

CREATE TABLE IF NOT EXISTS bw.purge_tombstones (
  scope text NOT NULL,
  key text NOT NULL,
  cutoff_push_time bigint NOT NULL,
  purged_at timestamptz NOT NULL DEFAULT now(),
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY(scope,key)
);
CREATE INDEX IF NOT EXISTS ix_purge_tombstones_cutoff ON bw.purge_tombstones(cutoff_push_time DESC);

CREATE TABLE IF NOT EXISTS bw.dead_letters (
  id bigserial PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  stream_id text,
  node text,
  push_time bigint,
  error text NOT NULL,
  payload jsonb
);

CREATE TABLE IF NOT EXISTS bw.agent_push_raw (
  time timestamptz NOT NULL,
  node text NOT NULL,
  push_time bigint NOT NULL,
  interval_seconds integer NOT NULL DEFAULT 300,
  agent_version integer NOT NULL DEFAULT 0,
  received_at timestamptz NOT NULL DEFAULT now(),
  payload jsonb NOT NULL
);
SELECT create_hypertable('bw.agent_push_raw','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_push_raw_node_time ON bw.agent_push_raw(node,push_time,time);
CREATE INDEX IF NOT EXISTS ix_agent_push_raw_node_time ON bw.agent_push_raw(node,time DESC);

CREATE TABLE IF NOT EXISTS bw.node_current (
  node text PRIMARY KEY,
  last_seen timestamptz NOT NULL,
  push_time bigint NOT NULL,
  interval_seconds integer NOT NULL DEFAULT 300,
  agent_version integer NOT NULL DEFAULT 0,
  inventory_complete boolean NOT NULL DEFAULT false,
  vm_count integer NOT NULL DEFAULT 0,
  iface_count integer NOT NULL DEFAULT 0,
  public_ipv4 text NOT NULL DEFAULT '',
  private_ipv4 text NOT NULL DEFAULT '',
  payload_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_node_current_seen ON bw.node_current(last_seen DESC);

CREATE TABLE IF NOT EXISTS bw.vm_current (
  node text NOT NULL,
  vm_uuid text NOT NULL,
  last_seen timestamptz NOT NULL,
  push_time bigint NOT NULL,
  vcpu_current integer NOT NULL DEFAULT 0,
  cpu_percent double precision NOT NULL DEFAULT 0,
  ram_current_kib bigint NOT NULL DEFAULT 0,
  ram_maximum_kib bigint NOT NULL DEFAULT 0,
  ram_rss_kib bigint NOT NULL DEFAULT 0,
  disk_read_bps double precision NOT NULL DEFAULT 0,
  disk_write_bps double precision NOT NULL DEFAULT 0,
  disk_read_iops double precision NOT NULL DEFAULT 0,
  disk_write_iops double precision NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(node,vm_uuid)
);
CREATE INDEX IF NOT EXISTS ix_vm_current_uuid ON bw.vm_current(vm_uuid);
CREATE INDEX IF NOT EXISTS ix_vm_current_cpu ON bw.vm_current(cpu_percent DESC);
CREATE INDEX IF NOT EXISTS ix_vm_current_seen ON bw.vm_current(last_seen DESC);

CREATE TABLE IF NOT EXISTS bw.vm_disk_current (
  node text NOT NULL,
  vm_uuid text NOT NULL,
  target text NOT NULL,
  source text NOT NULL DEFAULT '',
  role text NOT NULL DEFAULT 'unknown',
  mount text NOT NULL DEFAULT '',
  storage_device text NOT NULL DEFAULT '',
  storage_block text NOT NULL DEFAULT '',
  storage_fstype text NOT NULL DEFAULT '',
  capacity_bytes bigint NOT NULL DEFAULT 0,
  allocation_bytes bigint NOT NULL DEFAULT 0,
  physical_bytes bigint NOT NULL DEFAULT 0,
  read_bps double precision NOT NULL DEFAULT 0,
  write_bps double precision NOT NULL DEFAULT 0,
  read_iops double precision NOT NULL DEFAULT 0,
  write_iops double precision NOT NULL DEFAULT 0,
  last_seen timestamptz NOT NULL,
  push_time bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(node,vm_uuid,target,source)
);
CREATE INDEX IF NOT EXISTS ix_vm_disk_current_uuid ON bw.vm_disk_current(vm_uuid);
CREATE INDEX IF NOT EXISTS ix_vm_disk_current_storage ON bw.vm_disk_current(node,mount,write_iops DESC,write_bps DESC);
CREATE INDEX IF NOT EXISTS ix_vm_disk_current_alloc ON bw.vm_disk_current(allocation_bytes DESC);

CREATE TABLE IF NOT EXISTS bw.node_storage_current (
  node text NOT NULL,
  mount text NOT NULL,
  device text NOT NULL DEFAULT '',
  block text NOT NULL DEFAULT '',
  raid_level text NOT NULL DEFAULT '',
  fstype text NOT NULL DEFAULT '',
  size_bytes bigint NOT NULL DEFAULT 0,
  used_bytes bigint NOT NULL DEFAULT 0,
  avail_bytes bigint NOT NULL DEFAULT 0,
  use_percent double precision NOT NULL DEFAULT 0,
  read_bps double precision NOT NULL DEFAULT 0,
  write_bps double precision NOT NULL DEFAULT 0,
  read_iops double precision NOT NULL DEFAULT 0,
  write_iops double precision NOT NULL DEFAULT 0,
  util_percent double precision NOT NULL DEFAULT 0,
  last_seen timestamptz NOT NULL,
  push_time bigint NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(node,mount)
);
CREATE INDEX IF NOT EXISTS ix_node_storage_current_load ON bw.node_storage_current(write_iops DESC,write_bps DESC);
CREATE INDEX IF NOT EXISTS ix_node_storage_current_seen ON bw.node_storage_current(last_seen DESC);

CREATE TABLE IF NOT EXISTS bw.vm_network_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  vm_uuid text NOT NULL,
  iface text NOT NULL DEFAULT '',
  bridge text NOT NULL DEFAULT '',
  interval_seconds integer NOT NULL DEFAULT 300,
  rx_bytes bigint NOT NULL DEFAULT 0,
  tx_bytes bigint NOT NULL DEFAULT 0,
  rx_packets bigint NOT NULL DEFAULT 0,
  tx_packets bigint NOT NULL DEFAULT 0,
  rx_mbps double precision NOT NULL DEFAULT 0,
  tx_mbps double precision NOT NULL DEFAULT 0,
  rx_pps double precision NOT NULL DEFAULT 0,
  tx_pps double precision NOT NULL DEFAULT 0,
  rx_mbps_peak double precision NOT NULL DEFAULT 0,
  tx_mbps_peak double precision NOT NULL DEFAULT 0,
  rx_pps_peak double precision NOT NULL DEFAULT 0,
  tx_pps_peak double precision NOT NULL DEFAULT 0,
  rx_drops bigint NOT NULL DEFAULT 0,
  tx_drops bigint NOT NULL DEFAULT 0,
  rx_errors bigint NOT NULL DEFAULT 0,
  tx_errors bigint NOT NULL DEFAULT 0,
  quality text NOT NULL DEFAULT 'LEGACY'
);
SELECT create_hypertable('bw.vm_network_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_vm_network_node_vm_time ON bw.vm_network_metrics(node,vm_uuid,time DESC);
CREATE INDEX IF NOT EXISTS ix_vm_network_vm_time ON bw.vm_network_metrics(vm_uuid,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vm_network_sample ON bw.vm_network_metrics(time,node,vm_uuid,iface,bridge);

CREATE TABLE IF NOT EXISTS bw.vm_perf_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  vm_uuid text NOT NULL,
  interval_seconds integer NOT NULL DEFAULT 300,
  vcpu_current integer NOT NULL DEFAULT 0,
  cpu_percent double precision NOT NULL DEFAULT 0,
  ram_current_kib bigint NOT NULL DEFAULT 0,
  ram_maximum_kib bigint NOT NULL DEFAULT 0,
  ram_rss_kib bigint NOT NULL DEFAULT 0,
  ram_available_kib bigint NOT NULL DEFAULT 0,
  ram_unused_kib bigint NOT NULL DEFAULT 0,
  ram_usable_kib bigint NOT NULL DEFAULT 0,
  disk_read_bytes bigint NOT NULL DEFAULT 0,
  disk_write_bytes bigint NOT NULL DEFAULT 0,
  disk_read_reqs bigint NOT NULL DEFAULT 0,
  disk_write_reqs bigint NOT NULL DEFAULT 0,
  disk_read_bps double precision NOT NULL DEFAULT 0,
  disk_write_bps double precision NOT NULL DEFAULT 0,
  disk_read_iops double precision NOT NULL DEFAULT 0,
  disk_write_iops double precision NOT NULL DEFAULT 0
);
SELECT create_hypertable('bw.vm_perf_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_vm_perf_node_vm_time ON bw.vm_perf_metrics(node,vm_uuid,time DESC);
CREATE INDEX IF NOT EXISTS ix_vm_perf_vm_time ON bw.vm_perf_metrics(vm_uuid,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vm_perf_sample ON bw.vm_perf_metrics(time,node,vm_uuid);

CREATE TABLE IF NOT EXISTS bw.vm_disk_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  vm_uuid text NOT NULL,
  target text NOT NULL,
  source text NOT NULL DEFAULT '',
  role text NOT NULL DEFAULT 'unknown',
  mount text NOT NULL DEFAULT '',
  storage_device text NOT NULL DEFAULT '',
  storage_block text NOT NULL DEFAULT '',
  storage_fstype text NOT NULL DEFAULT '',
  capacity_bytes bigint NOT NULL DEFAULT 0,
  allocation_bytes bigint NOT NULL DEFAULT 0,
  physical_bytes bigint NOT NULL DEFAULT 0,
  interval_seconds integer NOT NULL DEFAULT 300,
  read_bytes bigint NOT NULL DEFAULT 0,
  write_bytes bigint NOT NULL DEFAULT 0,
  read_reqs bigint NOT NULL DEFAULT 0,
  write_reqs bigint NOT NULL DEFAULT 0,
  read_bps double precision NOT NULL DEFAULT 0,
  write_bps double precision NOT NULL DEFAULT 0,
  read_iops double precision NOT NULL DEFAULT 0,
  write_iops double precision NOT NULL DEFAULT 0
);
SELECT create_hypertable('bw.vm_disk_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_vm_disk_node_vm_time ON bw.vm_disk_metrics(node,vm_uuid,time DESC);
CREATE INDEX IF NOT EXISTS ix_vm_disk_mount_time ON bw.vm_disk_metrics(node,mount,time DESC);
CREATE INDEX IF NOT EXISTS ix_vm_disk_write_iops ON bw.vm_disk_metrics(write_iops DESC,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_vm_disk_sample ON bw.vm_disk_metrics(time,node,vm_uuid,target,source);

CREATE TABLE IF NOT EXISTS bw.node_host_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  interval_seconds integer NOT NULL DEFAULT 300,
  load1 double precision NOT NULL DEFAULT 0,
  load5 double precision NOT NULL DEFAULT 0,
  load15 double precision NOT NULL DEFAULT 0,
  cpu_count integer NOT NULL DEFAULT 0,
  cpu_percent double precision NOT NULL DEFAULT 0,
  mem_total bigint NOT NULL DEFAULT 0,
  mem_available bigint NOT NULL DEFAULT 0,
  mem_used bigint NOT NULL DEFAULT 0,
  swap_total bigint NOT NULL DEFAULT 0,
  swap_used bigint NOT NULL DEFAULT 0,
  disk_read_bps double precision NOT NULL DEFAULT 0,
  disk_write_bps double precision NOT NULL DEFAULT 0,
  uptime_seconds bigint NOT NULL DEFAULT 0
);
SELECT create_hypertable('bw.node_host_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_node_host_node_time ON bw.node_host_metrics(node,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_node_host_sample ON bw.node_host_metrics(time,node);

CREATE TABLE IF NOT EXISTS bw.node_storage_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  mount text NOT NULL,
  device text NOT NULL DEFAULT '',
  block text NOT NULL DEFAULT '',
  raid_level text NOT NULL DEFAULT '',
  fstype text NOT NULL DEFAULT '',
  size_bytes bigint NOT NULL DEFAULT 0,
  used_bytes bigint NOT NULL DEFAULT 0,
  avail_bytes bigint NOT NULL DEFAULT 0,
  use_percent double precision NOT NULL DEFAULT 0,
  read_bps double precision NOT NULL DEFAULT 0,
  write_bps double precision NOT NULL DEFAULT 0,
  read_iops double precision NOT NULL DEFAULT 0,
  write_iops double precision NOT NULL DEFAULT 0,
  util_percent double precision NOT NULL DEFAULT 0
);
SELECT create_hypertable('bw.node_storage_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_node_storage_node_mount_time ON bw.node_storage_metrics(node,mount,time DESC);
CREATE INDEX IF NOT EXISTS ix_node_storage_load ON bw.node_storage_metrics(write_iops DESC,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_node_storage_sample ON bw.node_storage_metrics(time,node,mount);

CREATE TABLE IF NOT EXISTS bw.physical_network_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  role text NOT NULL DEFAULT '',
  bridge text NOT NULL DEFAULT '',
  iface text NOT NULL DEFAULT '',
  interval_seconds integer NOT NULL DEFAULT 300,
  rx_bytes bigint NOT NULL DEFAULT 0,
  tx_bytes bigint NOT NULL DEFAULT 0,
  rx_packets bigint NOT NULL DEFAULT 0,
  tx_packets bigint NOT NULL DEFAULT 0,
  rx_mbps double precision NOT NULL DEFAULT 0,
  tx_mbps double precision NOT NULL DEFAULT 0,
  rx_pps double precision NOT NULL DEFAULT 0,
  tx_pps double precision NOT NULL DEFAULT 0,
  rx_drops bigint NOT NULL DEFAULT 0,
  tx_drops bigint NOT NULL DEFAULT 0,
  rx_errors bigint NOT NULL DEFAULT 0,
  tx_errors bigint NOT NULL DEFAULT 0
);
SELECT create_hypertable('bw.physical_network_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_phys_net_node_time ON bw.physical_network_metrics(node,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_phys_net_sample ON bw.physical_network_metrics(time,node,role,bridge,iface);

CREATE TABLE IF NOT EXISTS bw.agent_health_metrics (
  time timestamptz NOT NULL,
  node text NOT NULL,
  agent_version integer NOT NULL DEFAULT 0,
  interval_seconds integer NOT NULL DEFAULT 300,
  duration_ms integer NOT NULL DEFAULT 0,
  virsh_list_ms integer NOT NULL DEFAULT 0,
  vm_network_ms integer NOT NULL DEFAULT 0,
  vm_perf_ms integer NOT NULL DEFAULT 0,
  node_host_ms integer NOT NULL DEFAULT 0,
  physical_network_ms integer NOT NULL DEFAULT 0,
  vm_names integer NOT NULL DEFAULT 0,
  interfaces integer NOT NULL DEFAULT 0,
  vms integer NOT NULL DEFAULT 0,
  physical_interfaces integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  overloaded boolean NOT NULL DEFAULT false,
  errors jsonb NOT NULL DEFAULT '[]'::jsonb
);
SELECT create_hypertable('bw.agent_health_metrics','time',if_not_exists=>TRUE,chunk_time_interval=>INTERVAL '1 day');
CREATE INDEX IF NOT EXISTS ix_agent_health_node_time ON bw.agent_health_metrics(node,time DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_health_sample ON bw.agent_health_metrics(time,node);

CREATE TABLE IF NOT EXISTS bw.legacy_snapshot_index (
  node text NOT NULL,
  bucket bigint NOT NULL,
  push_time bigint NOT NULL,
  vm_count integer NOT NULL DEFAULT 0,
  iface_count integer NOT NULL DEFAULT 0,
  retention_tier text NOT NULL DEFAULT 'raw',
  migrated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(node,bucket)
);

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_network_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes',time) AS bucket,
       node,vm_uuid,
       avg(rx_mbps) AS rx_mbps_avg,avg(tx_mbps) AS tx_mbps_avg,
       max(rx_mbps_peak) AS rx_mbps_peak,max(tx_mbps_peak) AS tx_mbps_peak,
       avg(rx_pps) AS rx_pps_avg,avg(tx_pps) AS tx_pps_avg,
       max(rx_pps_peak) AS rx_pps_peak,max(tx_pps_peak) AS tx_pps_peak,
       sum(rx_bytes) AS rx_bytes,sum(tx_bytes) AS tx_bytes,
       count(*) AS samples
FROM bw.vm_network_metrics
GROUP BY bucket,node,vm_uuid
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_perf_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes',time) AS bucket,
       node,vm_uuid,
       avg(cpu_percent) AS cpu_percent_avg,max(cpu_percent) AS cpu_percent_peak,
       last(vcpu_current,time) AS vcpu_current,
       last(ram_current_kib,time) AS ram_current_kib,
       last(ram_maximum_kib,time) AS ram_maximum_kib,
       last(ram_rss_kib,time) AS ram_rss_kib,
       avg(disk_read_bps) AS disk_read_bps,
       avg(disk_write_bps) AS disk_write_bps,
       avg(disk_read_iops) AS disk_read_iops,
       avg(disk_write_iops) AS disk_write_iops,
       count(*) AS samples
FROM bw.vm_perf_metrics
GROUP BY bucket,node,vm_uuid
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_disk_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes',time) AS bucket,
       node,vm_uuid,target,mount,storage_device,
       last(capacity_bytes,time) AS capacity_bytes,
       last(allocation_bytes,time) AS allocation_bytes,
       avg(read_bps) AS read_bps,avg(write_bps) AS write_bps,
       avg(read_iops) AS read_iops,avg(write_iops) AS write_iops,
       max(read_bps) AS read_bps_peak,max(write_bps) AS write_bps_peak,
       max(read_iops) AS read_iops_peak,max(write_iops) AS write_iops_peak,
       count(*) AS samples
FROM bw.vm_disk_metrics
WHERE role='customer'
GROUP BY bucket,node,vm_uuid,target,mount,storage_device
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.node_storage_5m
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '5 minutes',time) AS bucket,
       node,mount,device,
       last(size_bytes,time) AS size_bytes,last(used_bytes,time) AS used_bytes,
       last(use_percent,time) AS use_percent,
       avg(read_bps) AS read_bps,avg(write_bps) AS write_bps,
       avg(read_iops) AS read_iops,avg(write_iops) AS write_iops,
       max(util_percent) AS util_percent_peak,
       count(*) AS samples
FROM bw.node_storage_metrics
GROUP BY bucket,node,mount,device
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_network_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour',time) AS bucket,
       node,vm_uuid,
       avg(rx_mbps) AS rx_mbps_avg,avg(tx_mbps) AS tx_mbps_avg,
       max(rx_mbps_peak) AS rx_mbps_peak,max(tx_mbps_peak) AS tx_mbps_peak,
       avg(rx_pps) AS rx_pps_avg,avg(tx_pps) AS tx_pps_avg,
       max(rx_pps_peak) AS rx_pps_peak,max(tx_pps_peak) AS tx_pps_peak,
       sum(rx_bytes) AS rx_bytes,sum(tx_bytes) AS tx_bytes,
       count(*) AS samples
FROM bw.vm_network_metrics
GROUP BY bucket,node,vm_uuid
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_perf_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour',time) AS bucket,
       node,vm_uuid,
       avg(cpu_percent) AS cpu_percent_avg,max(cpu_percent) AS cpu_percent_peak,
       last(vcpu_current,time) AS vcpu_current,
       last(ram_current_kib,time) AS ram_current_kib,
       last(ram_maximum_kib,time) AS ram_maximum_kib,
       last(ram_rss_kib,time) AS ram_rss_kib,
       avg(disk_read_bps) AS disk_read_bps,
       avg(disk_write_bps) AS disk_write_bps,
       avg(disk_read_iops) AS disk_read_iops,
       avg(disk_write_iops) AS disk_write_iops,
       count(*) AS samples
FROM bw.vm_perf_metrics
GROUP BY bucket,node,vm_uuid
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_disk_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour',time) AS bucket,
       node,vm_uuid,target,mount,storage_device,
       last(capacity_bytes,time) AS capacity_bytes,
       last(allocation_bytes,time) AS allocation_bytes,
       avg(read_bps) AS read_bps,avg(write_bps) AS write_bps,
       avg(read_iops) AS read_iops,avg(write_iops) AS write_iops,
       max(read_bps) AS read_bps_peak,max(write_bps) AS write_bps_peak,
       max(read_iops) AS read_iops_peak,max(write_iops) AS write_iops_peak,
       count(*) AS samples
FROM bw.vm_disk_metrics
WHERE role='customer'
GROUP BY bucket,node,vm_uuid,target,mount,storage_device
WITH NO DATA;

CREATE MATERIALIZED VIEW IF NOT EXISTS bw.node_storage_1h
WITH (timescaledb.continuous) AS
SELECT time_bucket(INTERVAL '1 hour',time) AS bucket,
       node,mount,device,
       last(size_bytes,time) AS size_bytes,last(used_bytes,time) AS used_bytes,
       last(use_percent,time) AS use_percent,
       avg(read_bps) AS read_bps,avg(write_bps) AS write_bps,
       avg(read_iops) AS read_iops,avg(write_iops) AS write_iops,
       max(util_percent) AS util_percent_peak,
       count(*) AS samples
FROM bw.node_storage_metrics
GROUP BY bucket,node,mount,device
WITH NO DATA;

DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_network_1h',start_offset=>INTERVAL '31 days',end_offset=>INTERVAL '5 minutes',schedule_interval=>INTERVAL '15 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_perf_1h',start_offset=>INTERVAL '31 days',end_offset=>INTERVAL '5 minutes',schedule_interval=>INTERVAL '15 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_disk_1h',start_offset=>INTERVAL '31 days',end_offset=>INTERVAL '5 minutes',schedule_interval=>INTERVAL '15 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.node_storage_1h',start_offset=>INTERVAL '31 days',end_offset=>INTERVAL '5 minutes',schedule_interval=>INTERVAL '15 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_network_5m',start_offset=>INTERVAL '2 days',end_offset=>INTERVAL '1 minute',schedule_interval=>INTERVAL '2 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_perf_5m',start_offset=>INTERVAL '2 days',end_offset=>INTERVAL '1 minute',schedule_interval=>INTERVAL '2 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.vm_disk_5m',start_offset=>INTERVAL '2 days',end_offset=>INTERVAL '1 minute',schedule_interval=>INTERVAL '2 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  PERFORM add_continuous_aggregate_policy('bw.node_storage_5m',start_offset=>INTERVAL '2 days',end_offset=>INTERVAL '1 minute',schedule_interval=>INTERVAL '2 minutes');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN PERFORM add_retention_policy('bw.agent_push_raw',INTERVAL '14 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.vm_network_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.vm_perf_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.vm_disk_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.node_host_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.node_storage_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.physical_network_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN PERFORM add_retention_policy('bw.agent_health_metrics',INTERVAL '30 days'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ANALYZE bw.node_current;
ANALYZE bw.vm_current;
ANALYZE bw.vm_disk_current;
ANALYZE bw.node_storage_current;

CREATE TABLE IF NOT EXISTS bw.migration_checkpoint (
  table_name text PRIMARY KEY,
  last_id bigint NOT NULL DEFAULT 0,
  completed boolean NOT NULL DEFAULT false,
  rows_migrated bigint NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT now()
);
