from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Sequence, TextIO
from uuid import uuid4

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository


PASS = "pass"
SKIP = "skip"
FAIL = "fail"

REPO_ROOT = Path(__file__).resolve().parents[4]
POSTGRES_STATE_STORE = REPO_ROOT / "backend/src/fin_ops_platform/services/postgres_state_store.py"
APP_SERVER = REPO_ROOT / "backend/src/fin_ops_platform/app/server.py"

ALLOWED_POSTGRES_SNAPSHOT_READS = {
    "oa_sync_state": "worker-source-state: OA sync checkpoint; exit after OA sync state is formalized.",
    "manual_oa_imports": "legacy-runtime-temporary: manual OA import state; exit after app/manual OA repository coverage.",
    "etc_state": "legacy-runtime-temporary: ETC counters and compatibility state; exit after ETC counter tables are complete.",
    "etc_reconciliation_state": "legacy-runtime-temporary: ETC reconciliation counters; exit after reconciliation counter tables are complete.",
    "historical_etc_repair_bundles": "migration-shadow-test-only: historical repair metadata fallback.",
    "historical_etc_repair_parsed_seeds": "migration-shadow-test-only: historical repair parsed seed fallback.",
    "historical_etc_repair_states": "migration-shadow-test-only: historical repair state fallback.",
    "background_jobs": "legacy-runtime-temporary: background job mirror/read compatibility; exit after runtime queue fully replaces old jobs.",
    "app_health_alerts": "legacy-runtime-temporary: active health alert compatibility; exit after audit/app health table is sole source.",
    "workbench_pair_relations": "legacy-runtime-temporary: relation migration compatibility; exit after repository shadow mismatch is zero.",
    "workbench_overrides": "legacy-runtime-temporary: workbench override compatibility; exit after formal override rows cover all reads.",
    "no_oa_bank_batches": "legacy-runtime-temporary: no-OA batch relation compatibility; exit after formal rows cover all historical batches.",
    "bank_transaction_categories": "legacy-runtime-temporary: category settings compatibility; exit after formal category rows/settings cover all data.",
    "turnover_relations": "legacy-runtime-temporary: turnover relation compatibility; exit after formal rows cover all relations.",
    "turnover_ledger_extras": "legacy-runtime-temporary: ledger extra compatibility; exit after formal rows cover all extras.",
    "full_state": "migration-shadow-test-only: disabled by default; only read when FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT=1.",
    "workbench_exception_cases": "legacy-runtime-temporary: exception case compatibility; exit after formal rows cover all cases.",
    "imports": "migration-shadow-test-only: only used by explicit legacy full snapshot imports path.",
    "file_imports": "migration-shadow-test-only: only used by explicit legacy full snapshot file imports path.",
    "matching": "legacy-runtime-temporary: matching run compatibility; exit after formal matching tables are sole source.",
}

FORBIDDEN_MIGRATED_READ_MODEL_SNAPSHOT_READS = {
    "workbench_read_models",
    "workbench_candidate_matches",
    "cost_statistics_read_models",
    "tax_offset_read_models",
}


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Final runtime SQL/read-model convergence closure harness.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--output", type=Path, help="Write JSON report to a file.")
    parser.add_argument(
        "--require-real-infra",
        action="store_true",
        help="Treat missing PostgreSQL/Redis/MinIO/OA real infrastructure checks as failures.",
    )
    parser.add_argument("--run-unit-tests", action="store_true", help="Run targeted local guard tests.")
    parser.add_argument("--run-full-unit-tests", action="store_true", help="Run full unittest discovery.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout, stderr: TextIO = sys.stderr) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    checks = run_checks(
        require_real_infra=args.require_real_infra,
        run_unit_tests=args.run_unit_tests,
        run_full_unit_tests=args.run_full_unit_tests,
    )
    status = _overall_status(checks)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "require_real_infra": args.require_real_infra,
        "checks": [check.to_dict() for check in checks],
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded if args.json else _format_text_report(report), file=stdout)
    return 0 if status == PASS else 1


def run_checks(*, require_real_infra: bool, run_unit_tests: bool, run_full_unit_tests: bool) -> list[CheckResult]:
    checks = [
        _check_static_snapshot_fallbacks(),
        _check_static_production_builder_boundaries(),
        _check_docker_daemon(require_real_infra=require_real_infra),
        _check_postgres(require_real_infra=require_real_infra),
        _check_redis(require_real_infra=require_real_infra),
        _check_object_storage(require_real_infra=require_real_infra),
        _check_file_object_migration(require_real_infra=require_real_infra),
        _check_oa_source(require_real_infra=require_real_infra),
        _check_worker_configuration(require_real_infra=require_real_infra),
        _check_performance_probe(require_real_infra=require_real_infra),
    ]
    if run_unit_tests:
        checks.append(_run_targeted_unit_tests())
    if run_full_unit_tests:
        checks.append(_run_full_unit_tests())
    return checks


def _check_static_snapshot_fallbacks() -> CheckResult:
    source = POSTGRES_STATE_STORE.read_text(encoding="utf-8")
    keys = re.findall(r"_load_snapshot\(\s*[\"']([^\"']+)[\"']\s*\)", source)
    unknown = sorted({key for key in keys if key not in ALLOWED_POSTGRES_SNAPSHOT_READS})
    forbidden = sorted({key for key in keys if key in FORBIDDEN_MIGRATED_READ_MODEL_SNAPSHOT_READS})
    if unknown or forbidden:
        return CheckResult(
            name="static.postgres_snapshot_fallbacks",
            status=FAIL,
            detail="PostgresStateStore has unclassified or forbidden _load_snapshot reads.",
            metadata={"unknown": unknown, "forbidden": forbidden, "keys": sorted(set(keys))},
        )
    return CheckResult(
        name="static.postgres_snapshot_fallbacks",
        status=PASS,
        detail="All remaining _load_snapshot reads are classified; migrated read model fallbacks are absent.",
        metadata={"classified": {key: ALLOWED_POSTGRES_SNAPSHOT_READS[key] for key in sorted(set(keys))}},
    )


def _check_static_production_builder_boundaries() -> CheckResult:
    source = APP_SERVER.read_text(encoding="utf-8")
    required_snippets = (
        "def _requires_sql_read_model_runtime",
        "api_sql_repository_unavailable",
        "read_model_unavailable",
    )
    missing = [snippet for snippet in required_snippets if snippet not in source]
    risky_patterns = [
        r"return\s+self\._json_response\(HTTPStatus\.OK,\s*self\._build_api_workbench_payload\(current_month\)\)",
    ]
    risks = [pattern for pattern in risky_patterns if re.search(pattern, source) and "if self._requires_sql_read_model_runtime()" not in source]
    if missing or risks:
        return CheckResult(
            name="static.production_builder_boundaries",
            status=FAIL,
            detail="Production builder boundary guard is missing or ambiguous.",
            metadata={"missing": missing, "risks": risks},
        )
    return CheckResult(
        name="static.production_builder_boundaries",
        status=PASS,
        detail="Production PostgreSQL runtime has explicit read_model_unavailable boundaries before legacy builders.",
    )


def _check_docker_daemon(*, require_real_infra: bool) -> CheckResult:
    result = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=10)
    if result.returncode == 0:
        return CheckResult(name="infra.docker", status=PASS, detail=f"Docker daemon reachable: {result.stdout.strip()}")
    return CheckResult(
        name="infra.docker",
        status=FAIL if require_real_infra else SKIP,
        detail="Docker daemon is not reachable; local disposable PostgreSQL/Redis/MinIO cannot be started automatically.",
        metadata={"stderr": result.stderr.strip()},
    )


def _check_postgres(*, require_real_infra: bool) -> CheckResult:
    database_url = _postgres_database_url()
    if not database_url:
        return CheckResult(
            name="infra.postgres",
            status=FAIL if require_real_infra else SKIP,
            detail="FIN_OPS_TEST_DATABASE_URL, FIN_OPS_POSTGRES_DATABASE_URL, or DATABASE_URL is not set.",
        )
    try:
        status = migrate.run_psql(database_url, sql="select 1;")
        migration_status = _run(
            [sys.executable, "-m", "fin_ops_platform.postgres.migrate", "status", "--database-url", database_url],
            env=_python_env(),
            timeout=60,
        )
        integration = _run(
            [
                sys.executable,
                "-m",
                "unittest",
                "tests.test_runtime_infrastructure_postgres_integration",
                "-v",
            ],
            env={**_python_env(), "FIN_OPS_TEST_DATABASE_URL": database_url, "FIN_OPS_ALLOW_POSTGRES_TEST_DB": "1"},
            timeout=180,
        )
    except Exception as exc:
        return CheckResult(name="infra.postgres", status=FAIL, detail=str(exc))
    if migration_status.returncode != 0 or integration.returncode != 0:
        return CheckResult(
            name="infra.postgres",
            status=FAIL,
            detail="PostgreSQL migration/status or runtime integration tests failed.",
            metadata={
                "select": status,
                "migration_stderr": migration_status.stderr[-4000:],
                "integration_stderr": integration.stderr[-4000:],
            },
        )
    return CheckResult(
        name="infra.postgres",
        status=PASS,
        detail="PostgreSQL reachable; migration status and runtime queue integration tests passed.",
        metadata={"database": migrate.redact_database_url(database_url)},
    )


def _check_redis(*, require_real_infra: bool) -> CheckResult:
    redis_url = (os.getenv("FIN_OPS_REDIS_URL") or os.getenv("REDIS_URL") or "").strip()
    if not redis_url:
        return CheckResult(
            name="infra.redis",
            status=FAIL if require_real_infra else SKIP,
            detail="FIN_OPS_REDIS_URL or REDIS_URL is not set.",
        )
    script = (
        "from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings;"
        "h=RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env());"
        "assert h.set_json('closure-smoke', {'ok': True}, ttl_seconds=5);"
        "assert h.get_json('closure-smoke') == {'ok': True};"
        "h.delete('closure-smoke');"
        "print('redis-ok')"
    )
    result = _run([sys.executable, "-c", script], env=_python_env(), timeout=20)
    if result.returncode != 0:
        return CheckResult(name="infra.redis", status=FAIL, detail="Redis TTL smoke failed.", metadata={"stderr": result.stderr})
    return CheckResult(name="infra.redis", status=PASS, detail="Redis set/get/delete TTL smoke passed.")


def _check_object_storage(*, require_real_infra: bool) -> CheckResult:
    try:
        settings = ObjectStorageSettings.from_env()
    except Exception as exc:
        return CheckResult(name="infra.object_storage", status=FAIL, detail=str(exc))
    if not settings.enabled:
        return CheckResult(
            name="infra.object_storage",
            status=FAIL if require_real_infra else SKIP,
            detail="OBJECT_STORAGE_BACKEND is not s3/minio; MinIO/S3 smoke skipped.",
        )
    key = f"runtime-convergence-smoke/{uuid4().hex}.txt"
    content = f"runtime-convergence:{uuid4().hex}".encode("utf-8")
    try:
        repository = S3ObjectStorageRepository(settings)
        repository.put_object(key, content, content_type="text/plain")
        downloaded = repository.get_object(key)
        repository.delete_object(key)
    except Exception as exc:
        return CheckResult(name="infra.object_storage", status=FAIL, detail=f"MinIO/S3 smoke failed: {exc}")
    if hashlib.sha256(downloaded).hexdigest() != hashlib.sha256(content).hexdigest():
        return CheckResult(name="infra.object_storage", status=FAIL, detail="MinIO/S3 checksum mismatch.")
    return CheckResult(name="infra.object_storage", status=PASS, detail="MinIO/S3 put/get/delete checksum smoke passed.")


def _check_file_object_migration(*, require_real_infra: bool) -> CheckResult:
    database_url = _postgres_database_url()
    try:
        settings = ObjectStorageSettings.from_env()
    except Exception as exc:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail=str(exc))
    has_app_mongo_settings = bool(
        (os.getenv("FIN_OPS_APP_MONGO_HOST") or "").strip()
        and (os.getenv("FIN_OPS_APP_MONGO_DATABASE") or "").strip()
    )
    if not database_url or not settings.enabled or not has_app_mongo_settings:
        missing = []
        if not database_url:
            missing.append("PostgreSQL URL")
        if not settings.enabled:
            missing.append("OBJECT_STORAGE_BACKEND=s3|minio")
        if not has_app_mongo_settings:
            missing.append("FIN_OPS_APP_MONGO_HOST/FIN_OPS_APP_MONGO_DATABASE")
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL if require_real_infra else SKIP,
            detail="GridFS backfill/verify/cleanup smoke skipped; missing " + ", ".join(missing) + ".",
        )

    legacy_gridfs_id = f"closure-gridfs-{uuid4().hex}"
    row_id = str(uuid4())
    temp_row_id = str(uuid4())
    content = f"legacy-gridfs:{uuid4().hex}".encode("utf-8")
    temp_key = f"runtime-convergence-smoke/orphan/{uuid4().hex}.tmp"
    sha256 = hashlib.sha256(content).hexdigest()
    seed_result = _run(
        [
            sys.executable,
            "-c",
            (
                "from gridfs import GridFSBucket;"
                "from pymongo import MongoClient;"
                "from fin_ops_platform.services.state_store import load_mongo_state_settings, default_data_dir;"
                "settings=load_mongo_state_settings(default_data_dir());"
                "assert settings is not None;"
                "client=MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=settings.request_timeout_ms);"
                "bucket=GridFSBucket(client[settings.database], bucket_name='import_file_blobs');"
                f"file_id={legacy_gridfs_id!r};"
                f"bucket.upload_from_stream_with_id(file_id, 'closure-gridfs.txt', {content!r}, metadata={{'source':'runtime_convergence_closure'}});"
                "client.close();"
                "print('gridfs-seeded')"
            ),
        ],
        env=_python_env(),
        timeout=60,
    )
    if seed_result.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="Could not seed legacy GridFS object for migration smoke.",
            metadata={"stderr": seed_result.stderr[-4000:]},
        )

    storage_uri = f"gridfs://import_file_blobs/{legacy_gridfs_id}"
    try:
        repository = S3ObjectStorageRepository(settings)
        repository.put_object(temp_key, content, content_type="application/octet-stream")
        _seed_file_object_migration_rows(
            database_url=database_url,
            row_id=row_id,
            temp_row_id=temp_row_id,
            legacy_gridfs_id=legacy_gridfs_id,
            storage_uri=storage_uri,
            backend=settings.backend,
            bucket=settings.bucket,
            temp_key=temp_key,
            sha256=sha256,
            size_bytes=len(content),
        )
    except Exception as exc:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail=f"Could not seed PostgreSQL/S3 migration rows: {exc}")

    migrate_event = _enqueue_runtime_event(
        database_url=database_url,
        event_type="file_object.gridfs_migration",
        dedupe_key=f"closure:file_object.migrate:{uuid4().hex}",
        payload={"action": "migrate", "limit": 10},
    )
    if migrate_event.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="Could not enqueue file object migration event.",
            metadata={"stderr": migrate_event.stderr[-4000:]},
        )
    worker_env = {**_python_env(), "FIN_OPS_POSTGRES_DATABASE_URL": database_url}
    migrate_worker = _run(
        [
            sys.executable,
            "-m",
            "fin_ops_platform.app.worker",
            "--worker-id",
            f"closure-file-worker-{uuid4().hex[:8]}",
            "--enable-file-object-migration",
            "--event-type",
            "file_object.gridfs_migration",
            "--max-iterations",
            "1",
            "--poll-interval-seconds",
            "0.1",
        ],
        env=worker_env,
        timeout=120,
    )
    if migrate_worker.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="GridFS migration worker smoke failed.",
            metadata={"stdout": migrate_worker.stdout[-4000:], "stderr": migrate_worker.stderr[-4000:]},
        )

    verify_result = _run(
        [sys.executable, "-m", "fin_ops_platform.tools.verify_file_object_migration", "--limit", "10"],
        env=worker_env,
        timeout=60,
    )
    if verify_result.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="GridFS migrated object checksum verification failed.",
            metadata={"stdout": verify_result.stdout[-4000:], "stderr": verify_result.stderr[-4000:]},
        )

    migrated_object_key = _fetch_file_object_value(database_url=database_url, row_id=row_id, column="object_key")
    if not migrated_object_key:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail="GridFS migration did not write an object_key.")
    try:
        migrated_content = repository.get_object(migrated_object_key)
    except Exception as exc:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail=f"Migrated object could not be read from S3: {exc}")
    if hashlib.sha256(migrated_content).hexdigest() != sha256:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail="Migrated GridFS object checksum mismatch.")

    try:
        migrate.run_psql(
            database_url,
            sql=f"update app.file_objects set migration_status = 'tombstoned', updated_at = now() where id = '{row_id}'::uuid;",
        )
    except Exception as exc:
        return CheckResult(name="infra.file_object_migration", status=FAIL, detail=f"Could not tombstone migrated row for cleanup smoke: {exc}")
    cleanup_event = _enqueue_runtime_event(
        database_url=database_url,
        event_type="file_object.gridfs_migration",
        dedupe_key=f"closure:file_object.cleanup:{uuid4().hex}",
        payload={"action": "cleanup", "limit": 10},
    )
    if cleanup_event.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="Could not enqueue file object cleanup event.",
            metadata={"stderr": cleanup_event.stderr[-4000:]},
        )
    cleanup_worker = _run(
        [
            sys.executable,
            "-m",
            "fin_ops_platform.app.worker",
            "--worker-id",
            f"closure-file-worker-{uuid4().hex[:8]}",
            "--enable-file-object-migration",
            "--event-type",
            "file_object.gridfs_migration",
            "--max-iterations",
            "1",
            "--poll-interval-seconds",
            "0.1",
        ],
        env=worker_env,
        timeout=120,
    )
    if cleanup_worker.returncode != 0:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="File object orphan cleanup worker smoke failed.",
            metadata={"stdout": cleanup_worker.stdout[-4000:], "stderr": cleanup_worker.stderr[-4000:]},
        )
    leftovers = []
    for key in (migrated_object_key, temp_key):
        try:
            repository.get_object(key)
            leftovers.append(key)
        except Exception:
            pass
    if leftovers:
        return CheckResult(
            name="infra.file_object_migration",
            status=FAIL,
            detail="File object cleanup smoke left S3 objects behind.",
            metadata={"leftovers": leftovers},
        )

    return CheckResult(
        name="infra.file_object_migration",
        status=PASS,
        detail="GridFS backfill, checksum verify, and orphan cleanup worker smoke passed.",
        metadata={
            "legacy_gridfs_id": legacy_gridfs_id,
            "migrated_object_key": migrated_object_key,
            "verify_stdout": verify_result.stdout.strip(),
            "migrate_worker_stdout": migrate_worker.stdout[-4000:],
            "cleanup_worker_stdout": cleanup_worker.stdout[-4000:],
        },
    )


def _check_oa_source(*, require_real_infra: bool) -> CheckResult:
    has_mongo_settings = bool(
        (os.getenv("FIN_OPS_OA_MONGO_HOST") or "").strip()
        and (os.getenv("FIN_OPS_OA_MONGO_DATABASE") or "").strip()
    )
    if not has_mongo_settings:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL if require_real_infra else SKIP,
            detail="FIN_OPS_OA_MONGO_HOST and FIN_OPS_OA_MONGO_DATABASE are not configured; real OA projection sync smoke skipped.",
        )
    source_script = (
        "import json;"
        "from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings;"
        "from fin_ops_platform.services.state_store import default_data_dir;"
        "settings=load_mongo_oa_settings(default_data_dir());"
        "assert settings is not None;"
        "adapter=MongoOAAdapter(settings=settings);"
        "months=adapter.list_available_months();"
        "status=adapter.get_read_status();"
        "assert status.code != 'error', status.message;"
        "sample_month=months[0] if months else 'all';"
        "sample_records=adapter.list_application_records(sample_month) if sample_month != 'all' else adapter.list_all_application_records();"
        "status=adapter.get_read_status();"
        "assert status.code != 'error', status.message;"
        "print(json.dumps({'months': months[:5], 'month_count': len(months), 'sample_month': sample_month, 'sample_record_count': len(sample_records), 'status': status.code}, ensure_ascii=False, sort_keys=True))"
    )
    source_result = _run([sys.executable, "-c", source_script], env=_python_env(), timeout=60)
    if source_result.returncode != 0:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL,
            detail="Real OA Mongo source read smoke failed.",
            metadata={"stderr": source_result.stderr[-4000:]},
        )
    try:
        source_payload = json.loads(source_result.stdout.strip() or "{}")
    except json.JSONDecodeError:
        source_payload = {}
    if int(source_payload.get("sample_record_count") or 0) <= 0:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL if require_real_infra else SKIP,
            detail="OA Mongo source is reachable but returned no application records for projection sync smoke.",
            metadata={"stdout": source_result.stdout.strip()},
        )

    database_url = _postgres_database_url()
    if not database_url:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL if require_real_infra else SKIP,
            detail="No PostgreSQL URL available for OA projection worker smoke.",
            metadata={"source": source_payload},
        )
    scope_key = str(source_payload.get("sample_month") or "all")
    dedupe_key = f"closure:oa.sync:{uuid4().hex}"
    enqueue_script = (
        "import json;"
        "from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings;"
        "from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository;"
        "connection=PostgresConnection(PostgresSettings.from_env());"
        "queue=RuntimeQueueRepository(connection);"
        f"event=queue.enqueue(event_type='oa.sync', aggregate_type='oa', aggregate_id={scope_key!r}, scope_type='oa', scope_key={scope_key!r}, dedupe_key={dedupe_key!r}, payload={{'scope_key': {scope_key!r}, 'reason': 'runtime_convergence_closure'}});"
        "print(json.dumps({'event_id': event.event_id, 'scope_key': event.scope_key}, sort_keys=True))"
    )
    env = {**_python_env(), "FIN_OPS_POSTGRES_DATABASE_URL": database_url}
    enqueue_result = _run([sys.executable, "-c", enqueue_script], env=env, timeout=30)
    if enqueue_result.returncode != 0:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL,
            detail="OA projection worker smoke could not enqueue oa.sync event.",
            metadata={"source": source_payload, "stderr": enqueue_result.stderr[-4000:]},
        )
    worker_result = _run(
        [
            sys.executable,
            "-m",
            "fin_ops_platform.app.worker",
            "--worker-id",
            f"closure-oa-worker-{uuid4().hex[:8]}",
            "--enable-oa-sync",
            "--event-type",
            "oa.sync",
            "--max-iterations",
            "1",
            "--poll-interval-seconds",
            "0.1",
        ],
        env=env,
        timeout=120,
    )
    if worker_result.returncode != 0:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL,
            detail="OA projection worker smoke failed while processing oa.sync.",
            metadata={
                "source": source_payload,
                "enqueue_stdout": enqueue_result.stdout.strip(),
                "stdout": worker_result.stdout[-4000:],
                "stderr": worker_result.stderr[-4000:],
            },
        )
    scope_month_literal = f"'{scope_key.replace("'", "''")}-01'::date"
    verify_sql = f"""
select json_build_object(
    'oa_sync_done_count', (select count(*) from job.outbox_events where event_type = 'oa.sync' and dedupe_key = '{dedupe_key}' and status = 'done'),
    'oa_projection_rows', (select count(*) from app.oa_applications where scope_month = {scope_month_literal}),
    'oa_sync_runs', (select count(*) from app.oa_sync_runs where sync_type = 'oa_projection'),
    'dirty_scope_count', (select count(*) from job.read_model_dirty_scopes where reason = 'oa_projection_sync')
)::text;
"""
    try:
        verification_output = migrate.run_psql(database_url, sql=verify_sql)
        verification = json.loads(verification_output)
    except Exception as exc:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL,
            detail=f"OA projection worker smoke verification failed: {exc}",
            metadata={"source": source_payload, "worker_stdout": worker_result.stdout[-4000:]},
        )
    missing = [
        key
        for key in ("oa_sync_done_count", "oa_projection_rows", "oa_sync_runs", "dirty_scope_count")
        if int(verification.get(key) or 0) <= 0
    ]
    if missing:
        return CheckResult(
            name="infra.oa_source",
            status=FAIL,
            detail="OA projection worker smoke did not produce all expected PostgreSQL effects.",
            metadata={
                "source": source_payload,
                "verification": verification,
                "missing": missing,
                "worker_stdout": worker_result.stdout[-4000:],
            },
        )
    return CheckResult(
        name="infra.oa_source",
        status=PASS,
        detail="Real OA Mongo source read and oa.sync worker projection smoke passed.",
        metadata={
            "source": source_payload,
            "verification": verification,
            "worker_stdout": worker_result.stdout[-4000:],
        },
    )


def _check_worker_configuration(*, require_real_infra: bool) -> CheckResult:
    database_url = _postgres_database_url()
    if not database_url:
        return CheckResult(
            name="worker.check",
            status=FAIL if require_real_infra else SKIP,
            detail="No PostgreSQL URL available for worker --check.",
        )
    result = _run(
        [
            sys.executable,
            "-m",
            "fin_ops_platform.app.worker",
            "--check",
            "--enable-workbench-read-model-refresh",
            "--enable-cost-statistics-read-model-refresh",
            "--enable-tax-offset-read-model-refresh",
            "--enable-search-read-model-refresh",
            "--enable-pending-invoice-read-model-refresh",
        ],
        env={**_python_env(), "FIN_OPS_POSTGRES_DATABASE_URL": database_url},
        timeout=30,
    )
    if result.returncode != 0:
        return CheckResult(name="worker.check", status=FAIL, detail="Worker --check failed.", metadata={"stderr": result.stderr})
    return CheckResult(name="worker.check", status=PASS, detail="Worker --check passed.", metadata={"stdout": result.stdout})


def _check_performance_probe(*, require_real_infra: bool) -> CheckResult:
    database_url = _postgres_database_url()
    if not database_url:
        return CheckResult(
            name="performance.read_models",
            status=FAIL if require_real_infra else SKIP,
            detail="No PostgreSQL URL available for read model EXPLAIN/timing probes.",
        )
    sql = """
explain (analyze, buffers, format json)
select count(*) from read_model.workbench_rows;
explain (analyze, buffers, format json)
select count(*) from read_model.cost_statistics_read_models;
explain (analyze, buffers, format json)
select count(*) from read_model.tax_offset_read_models;
"""
    try:
        output = migrate.run_psql(database_url, sql=sql)
    except Exception as exc:
        return CheckResult(name="performance.read_models", status=FAIL, detail=f"Read model performance probe failed: {exc}")
    return CheckResult(
        name="performance.read_models",
        status=PASS,
        detail="Read model EXPLAIN ANALYZE probes completed.",
        metadata={"output_sample": output[:2000]},
    )


def _run_targeted_unit_tests() -> CheckResult:
    result = _run(
        [
            sys.executable,
            "-m",
            "unittest",
            "tests.test_runtime_bootstrap",
            "tests.test_postgres_state_store",
            "tests.test_workbench_sql_runtime",
            "tests.test_cost_statistics_sql_runtime",
            "tests.test_tax_offset_sql_runtime",
            "-v",
        ],
        env=_python_env(),
        timeout=180,
    )
    return CheckResult(
        name="tests.targeted",
        status=PASS if result.returncode == 0 else FAIL,
        detail="Targeted runtime convergence tests passed." if result.returncode == 0 else "Targeted tests failed.",
        metadata={"stderr": result.stderr[-4000:]},
    )


def _run_full_unit_tests() -> CheckResult:
    result = _run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        env=_python_env(),
        timeout=600,
    )
    return CheckResult(
        name="tests.full_unittest",
        status=PASS if result.returncode == 0 else FAIL,
        detail="Full unittest discovery passed." if result.returncode == 0 else "Full unittest discovery failed.",
        metadata={"stderr": result.stderr[-4000:]},
    )


def _seed_file_object_migration_rows(
    *,
    database_url: str,
    row_id: str,
    temp_row_id: str,
    legacy_gridfs_id: str,
    storage_uri: str,
    backend: str,
    bucket: str,
    temp_key: str,
    sha256: str,
    size_bytes: int,
) -> None:
    sql = f"""
insert into app.file_objects(
    id, legacy_mongo_id, legacy_gridfs_id, storage_backend, storage_uri,
    bucket_name, object_key, filename, sha256, size_bytes, content_type,
    migration_status, raw_payload, created_at, updated_at
) values (
    '{row_id}'::uuid, 'closure-{legacy_gridfs_id}', '{legacy_gridfs_id}', 'gridfs_legacy', '{storage_uri}',
    null, null, 'closure-gridfs.txt', '{sha256}', {size_bytes}, 'text/plain',
    'legacy', '{{"source":"runtime_convergence_closure"}}'::jsonb, now(), now()
)
on conflict (legacy_mongo_id) do update set
    legacy_gridfs_id = excluded.legacy_gridfs_id,
    storage_backend = excluded.storage_backend,
    storage_uri = excluded.storage_uri,
    bucket_name = excluded.bucket_name,
    object_key = excluded.object_key,
    filename = excluded.filename,
    sha256 = excluded.sha256,
    size_bytes = excluded.size_bytes,
    content_type = excluded.content_type,
    migration_status = excluded.migration_status,
    temporary_object_key = null,
    updated_at = now();

insert into app.file_objects(
    id, legacy_mongo_id, storage_backend, storage_uri, bucket_name,
    object_key, filename, sha256, size_bytes, content_type,
    migration_status, temporary_object_key, raw_payload, created_at, updated_at
) values (
    '{temp_row_id}'::uuid, 'closure-temp-{temp_row_id}', '{backend}', '{backend}://{bucket}/{temp_key}', '{bucket}',
    null, 'closure-orphan.tmp', '{sha256}', {size_bytes}, 'application/octet-stream',
    'pending_upload', '{temp_key}', '{{"source":"runtime_convergence_closure"}}'::jsonb, now(), now()
)
on conflict (legacy_mongo_id) do update set
    storage_backend = excluded.storage_backend,
    storage_uri = excluded.storage_uri,
    bucket_name = excluded.bucket_name,
    temporary_object_key = excluded.temporary_object_key,
    migration_status = excluded.migration_status,
    updated_at = now();
"""
    migrate.run_psql(database_url, sql=sql)


def _enqueue_runtime_event(*, database_url: str, event_type: str, dedupe_key: str, payload: dict[str, Any]) -> subprocess.CompletedProcess[str]:
    script = (
        "import json;"
        "from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings;"
        "from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository;"
        "connection=PostgresConnection(PostgresSettings.from_env());"
        "queue=RuntimeQueueRepository(connection);"
        f"event=queue.enqueue(event_type={event_type!r}, aggregate_type='closure', aggregate_id={dedupe_key!r}, dedupe_key={dedupe_key!r}, payload={payload!r});"
        "print(json.dumps({'event_id': event.event_id}, sort_keys=True))"
    )
    return _run([sys.executable, "-c", script], env={**_python_env(), "FIN_OPS_POSTGRES_DATABASE_URL": database_url}, timeout=30)


def _fetch_file_object_value(*, database_url: str, row_id: str, column: str) -> str:
    if column not in {"object_key", "temporary_object_key", "migration_status"}:
        raise ValueError("Unsupported file object column.")
    output = migrate.run_psql(database_url, sql=f"select coalesce({column}, '') from app.file_objects where id = '{row_id}'::uuid;")
    return str(output or "").strip()


def _postgres_database_url() -> str:
    return (
        os.getenv("FIN_OPS_TEST_DATABASE_URL")
        or os.getenv("FIN_OPS_POSTGRES_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    ).strip()


def _python_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend/src"
    return env


def _run(command: Sequence[str], *, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _overall_status(checks: Sequence[CheckResult]) -> str:
    if any(check.status == FAIL for check in checks):
        return FAIL
    if any(check.status == SKIP for check in checks):
        return SKIP
    return PASS


def _format_text_report(report: dict[str, Any]) -> str:
    lines = [f"runtime convergence closure: {report['status']}"]
    for check in report["checks"]:
        lines.append(f"- {check['status']}: {check['name']} - {check['detail']}")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())
