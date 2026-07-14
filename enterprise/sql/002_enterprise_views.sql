\set ON_ERROR_STOP on
CREATE OR REPLACE VIEW bw.vm_disk_summary_current AS
SELECT node,vm_uuid,
       count(*) FILTER (WHERE role='customer')::integer AS disk_count,
       COALESCE(sum(allocation_bytes) FILTER (WHERE role='customer'),0)::bigint AS allocated_bytes,
       COALESCE(sum(capacity_bytes) FILTER (WHERE role='customer'),0)::bigint AS assigned_bytes,
       CASE WHEN COALESCE(sum(capacity_bytes) FILTER (WHERE role='customer'),0)>0
            THEN COALESCE(sum(allocation_bytes) FILTER (WHERE role='customer'),0)::double precision /
                 sum(capacity_bytes) FILTER (WHERE role='customer')::double precision
            ELSE 0 END AS allocation_ratio,
       COALESCE(sum(read_bps) FILTER (WHERE role='customer'),0)::double precision AS read_bps,
       COALESCE(sum(write_bps) FILTER (WHERE role='customer'),0)::double precision AS write_bps,
       COALESCE(sum(read_iops) FILTER (WHERE role='customer'),0)::double precision AS read_iops,
       COALESCE(sum(write_iops) FILTER (WHERE role='customer'),0)::double precision AS write_iops,
       max(last_seen) AS last_seen
FROM bw.vm_disk_current
GROUP BY node,vm_uuid;

CREATE OR REPLACE VIEW bw.node_storage_summary_current AS
SELECT node,
       count(*)::integer AS mount_count,
       COALESCE(sum(size_bytes),0)::bigint AS size_bytes,
       COALESCE(sum(used_bytes),0)::bigint AS used_bytes,
       CASE WHEN COALESCE(sum(size_bytes),0)>0
            THEN COALESCE(sum(used_bytes),0)::double precision/sum(size_bytes)::double precision
            ELSE 0 END AS use_ratio,
       COALESCE(sum(read_bps),0)::double precision AS read_bps,
       COALESCE(sum(write_bps),0)::double precision AS write_bps,
       COALESCE(sum(read_iops),0)::double precision AS read_iops,
       COALESCE(sum(write_iops),0)::double precision AS write_iops,
       COALESCE(max(util_percent),0)::double precision AS hottest_util_percent,
       max(last_seen) AS last_seen
FROM bw.node_storage_current
GROUP BY node;

CREATE OR REPLACE VIEW bw.enterprise_health AS
SELECT
  (SELECT count(*) FROM bw.node_current) AS nodes,
  (SELECT count(*) FROM bw.vm_current) AS vms,
  (SELECT count(*) FROM bw.vm_disk_current WHERE role='customer') AS customer_disks,
  (SELECT count(*) FROM bw.node_storage_current) AS storage_mounts,
  (SELECT max(last_seen) FROM bw.node_current) AS latest_node_sample,
  (SELECT count(*) FROM bw.dead_letters) AS dead_letters;
