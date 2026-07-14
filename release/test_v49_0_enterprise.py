#!/usr/bin/env python3
import importlib.util, os, pathlib, sys, tempfile

def check(condition, message):
    if not condition:
        raise AssertionError(message)

def main():
    app_path=pathlib.Path(sys.argv[1] if len(sys.argv)>1 else "bw_monitor_app_v48_12_9_operations_ui.py").resolve()
    root=app_path.parent.parent
    with tempfile.TemporaryDirectory(prefix="bw-v49-test-") as td:
        os.environ["BW_MONITOR_DB"]=str(pathlib.Path(td)/"test.db")
        os.environ["BW_MONITOR_TOKEN"]="v49-test-token-123456"
        os.environ["BW_REDIS_ENABLED"]="0"
        os.environ["BW_ENTERPRISE_ENABLED"]="0"
        spec=importlib.util.spec_from_file_location("bw_v49_test",app_path)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        check(getattr(module,"V4900_VERSION","")=="49.0.0","missing v49 marker")
        endpoints=(
            "api_v1_enterprise_health_v4900","api_v1_enterprise_top_disks_v4900",
            "api_v1_enterprise_storage_v4900","api_v1_enterprise_vm_disks_v4900",
            "api_v1_enterprise_vm_history_v4900","api_v1_enterprise_disk_history_v4900",
            "api_v1_enterprise_storage_history_v4900","enterprise_page_v4900",
        )
        for endpoint in endpoints:
            check(endpoint in module.app.view_functions,f"missing endpoint {endpoint}")
        check(module.app.view_functions["push"].__name__=="push","push endpoint name compatibility changed")
        check(module._v4900_enqueue_payload({"node":"n","time":1})=="disabled","disabled enterprise queue should be a no-op")
        check(callable(module.enterprise_enqueue_control),"enterprise purge control queue missing")
    schema=(root/"enterprise/sql/001_enterprise_schema.sql").read_text()
    for marker in (
        "CREATE EXTENSION IF NOT EXISTS timescaledb",
        "create_hypertable('bw.vm_disk_metrics'",
        "CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_disk_5m",
        "CREATE MATERIALIZED VIEW IF NOT EXISTS bw.vm_disk_1h",
        "CREATE TABLE IF NOT EXISTS bw.purge_tombstones",
        "add_continuous_aggregate_policy","add_retention_policy",
    ):
        check(marker in schema,f"schema missing {marker}")
    writer=(root/"enterprise/bw_enterprise_writer.py").read_text()
    for marker in (
        "xreadgroup","xautoclaim","bw.ingest_receipts","bw.vm_disk_current",
        "bw.node_storage_current","process_spool","process_control","purge_tombstones",
        "BW_ENTERPRISE_STORE_RAW_PUSH",
    ):
        check(marker in writer,f"writer missing {marker}")
    runner=(root/"release/bw_monitor_maintenance_v48_12_9_single_worker.py").read_text()
    check("enterprise_enqueue_control" in runner,"maintenance purge is not synchronized to Timescale")
    installer=(root/"deploy/enterprise/install-enterprise.sh").read_text()
    for marker in (
        "timescale/timescaledb:2.28.1-pg17-oss","bw-enterprise-writer.service",
        "--no-history-migration","bw_enterprise_migrate.py\" --current-only",
        "49-enterprise-spool.conf","BW_ENTERPRISE_STREAM_MAXLEN='0'",
    ):
        check(marker in installer,f"installer missing {marker}")
    print("PASS: v49 enterprise queue, durable outbox, Timescale schema, history APIs, exact purge sync and migration contracts")
    return 0
if __name__=="__main__": raise SystemExit(main())
