from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from threading import Thread
from typing import Any

from fin_ops_platform.services.app_settings_service import (
    DEFAULT_OA_IMPORT_FORM_TYPES,
    DEFAULT_OA_IMPORT_STATUSES,
    DEFAULT_OA_RETENTION_CUTOFF_DATE,
)
from fin_ops_platform.services.bank_account_balance_projection import BankAccountBalanceProjectionBuilder
from fin_ops_platform.services.bank_account_balance_read_model_refresh import BankAccountBalanceReadModelRefreshService
from fin_ops_platform.services.bank_detail_read_model_refresh import BankDetailReadModelRefreshService
from fin_ops_platform.services.bank_detail_sql_projection import BankDetailSqlProjectionBuilder
from fin_ops_platform.services.cost_tax_sql_projection import (
    CostStatisticsSqlProjectionBuilder,
    TaxOffsetSqlProjectionBuilder,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.etc_business_batch_application_service import ETC_BUSINESS_OA_DETECTION_EVENT_TYPE
from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.import_job_queue import IMPORT_PROCESS_REQUESTED_EVENT, ImportJobRepository, ImportJobWorker
from fin_ops_platform.services.invoice_usage_collection_read_model_refresh import (
    InvoiceUsageCollectionReadModelRefreshService,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import InvoiceUsageCollectionSqlProjectionBuilder
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_state_store import LegacyGridFSFileReader
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository, RuntimeQueueSettings
from fin_ops_platform.services.rabbitmq_runtime import RabbitMqConsumer, rabbitmq_event_routes
from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig
from fin_ops_platform.services.runtime_worker_registry import worker_registrations
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder
from fin_ops_platform.services.state_store import default_data_dir
from fin_ops_platform.services.tax_offset_read_model_refresh import TaxOffsetReadModelRefreshService
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder


APP_SETTINGS_KEY = "app_settings"
OA_IMPORT_FORM_TYPES = {"payment_request", "expense_claim"}
OA_IMPORT_STATUSES = {"completed", "in_progress"}
IMPORT_FACT_CHANGED_EVENT = "import.fact.changed"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform standalone runtime worker")
    parser.add_argument("--worker-id", default=None, help="Stable worker id for PostgreSQL locks and heartbeats.")
    parser.add_argument("--worker-kind", default=None, help="Worker heartbeat kind. Defaults to the enabled handler family.")
    parser.add_argument("--event-type", action="append", default=[], help="Outbox event type to claim. Repeatable.")
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--lock-timeout-seconds", type=int, default=300)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--task-timeout-seconds", type=int, default=None)
    parser.add_argument("--statement-timeout-seconds", type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=None, help="Testing/smoke limit. Omit to run continuously.")
    parser.add_argument("--max-events-per-iteration", type=int, default=1, help="Maximum events to drain before an idle sleep.")
    parser.add_argument("--enable-file-object-migration", action="store_true", help="Register GridFS to object storage migration handler.")
    parser.add_argument("--enable-workbench-read-model-refresh", action="store_true", help="Register workbench SQL read model refresh handler.")
    parser.add_argument("--enable-cost-statistics-read-model-refresh", action="store_true", help="Register cost statistics SQL read model refresh handler.")
    parser.add_argument("--enable-tax-offset-read-model-refresh", action="store_true", help="Register tax offset SQL read model refresh handler.")
    parser.add_argument("--enable-search-read-model-refresh", action="store_true", help="Register search SQL read model refresh handler.")
    parser.add_argument("--enable-pending-invoice-read-model-refresh", action="store_true", help="Register pending invoice SQL read model refresh handler.")
    parser.add_argument("--enable-bank-account-balance-read-model-refresh", action="store_true", help="Register bank account balance SQL read model refresh handler.")
    parser.add_argument("--enable-bank-detail-read-model-refresh", action="store_true", help="Register bank detail SQL read model refresh handler.")
    parser.add_argument("--enable-input-invoice-usage-read-model-refresh", action="store_true", help="Register input invoice usage SQL read model refresh handler.")
    parser.add_argument("--enable-output-invoice-collection-read-model-refresh", action="store_true", help="Register output invoice collection SQL read model refresh handler.")
    parser.add_argument("--enable-oa-pending-payment-read-model-refresh", action="store_true", help="Register OA pending payment SQL read model refresh handler.")
    parser.add_argument("--enable-oa-sync", action="store_true", help="Register OA Mongo to PostgreSQL projection sync handler.")
    parser.add_argument("--enable-etc-business-oa-detection", action="store_true", help="Register ETC business batch OA detection handler.")
    parser.add_argument("--enable-import-job-processing", action="store_true", help="Register import job worker handler.")
    parser.add_argument("--enable-workbench-matching", action="store_true", help="Poll DB-backed workbench matching dirty scopes.")
    parser.add_argument("--workbench-matching-batch-size", type=int, default=10)
    parser.add_argument("--workbench-matching-lease-seconds", type=int, default=600)
    parser.add_argument("--workbench-matching-retry-delay-seconds", type=int, default=None)
    parser.add_argument("--check", action="store_true", help="Print worker configuration and exit without polling.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = PostgresSettings.from_env()
    queue_settings = RuntimeQueueSettings.from_env()
    connection = PostgresConnection(settings)
    queue = RuntimeQueueRepository(connection)
    redis_helper = RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env())
    config = RuntimeWorkerConfig(
        worker_id=args.worker_id or RuntimeWorkerConfig().worker_id,
        event_types=list(args.event_type or []),
        poll_interval_seconds=args.poll_interval_seconds,
        lock_timeout_seconds=args.lock_timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        statement_timeout_seconds=args.statement_timeout_seconds,
        max_iterations=args.max_iterations,
        max_events_per_iteration=args.max_events_per_iteration,
        max_attempts=args.max_attempts,
        worker_kind=args.worker_kind or _infer_worker_kind(args),
    )
    handlers = {}
    if args.enable_file_object_migration:
        object_storage_settings = ObjectStorageSettings.from_env()
        object_storage_repository = S3ObjectStorageRepository(object_storage_settings)
        legacy_file_reader = LegacyGridFSFileReader.from_data_dir(default_data_dir())
        if legacy_file_reader is None:
            raise RuntimeError("GridFS migration worker requires legacy Mongo/GridFS configuration.")
        migration_service = GridFSObjectMigrationService(
            connection=connection,
            object_storage_repository=object_storage_repository,
            legacy_file_reader=legacy_file_reader,
            storage_backend=object_storage_settings.backend,
            bucket_name=object_storage_settings.bucket,
        )
        handlers["file_object.gridfs_migration"] = migration_service.handle_runtime_event
        if "file_object.gridfs_migration" not in config.event_types:
            config.event_types.append("file_object.gridfs_migration")
    if args.enable_oa_sync:
        oa_settings = load_mongo_oa_settings(default_data_dir())
        if oa_settings is None:
            raise RuntimeError("OA sync worker requires FIN_OPS_OA_MONGO_* configuration or oa_mongo_config.json.")
        ops_tax_etc_repository = PostgresOpsTaxEtcRepository(connection)
        source_adapter = _build_oa_sync_source_adapter(
            settings=oa_settings,
            attachment_invoice_cache=ops_tax_etc_repository,
        )
        oa_runtime_settings = _load_oa_runtime_settings(connection)
        source_adapter.set_import_settings_provider(lambda: dict(oa_runtime_settings["oa_import"]))
        projection_repository = PostgresOAProjectionRepository(connection)
        sync_service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=queue,
            retention_cutoff_date_provider=lambda: str(oa_runtime_settings["cutoff_date"]),
        )
        handlers["oa.sync"] = sync_service.handle_runtime_event
        if "oa.sync" not in config.event_types:
            config.event_types.append("oa.sync")
    if args.enable_etc_business_oa_detection:
        from fin_ops_platform.app.server import Application

        etc_application = Application(data_dir=default_data_dir())
        etc_business_service = etc_application._etc_business_application_service()
        handlers[ETC_BUSINESS_OA_DETECTION_EVENT_TYPE] = lambda event: _handle_etc_business_oa_detection_event(
            etc_business_service,
            event,
        )
        if ETC_BUSINESS_OA_DETECTION_EVENT_TYPE not in config.event_types:
            config.event_types.append(ETC_BUSINESS_OA_DETECTION_EVENT_TYPE)
    if args.enable_workbench_read_model_refresh:
        projection_builder = WorkbenchSqlProjectionBuilder(connection=connection)
        refresh_service = WorkbenchReadModelRefreshService(projection_builder=projection_builder, queue_repository=queue)
        handlers["workbench.read_model.refresh"] = refresh_service.handle_runtime_event
        if "workbench.read_model.refresh" not in config.event_types:
            config.event_types.append("workbench.read_model.refresh")
    if args.enable_cost_statistics_read_model_refresh:
        projection_builder = CostStatisticsSqlProjectionBuilder(connection=connection, redis_helper=redis_helper)
        refresh_service = CostStatisticsReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["cost_statistics.read_model.refresh"] = refresh_service.handle_runtime_event
        if "cost_statistics.read_model.refresh" not in config.event_types:
            config.event_types.append("cost_statistics.read_model.refresh")
    if args.enable_tax_offset_read_model_refresh:
        projection_builder = TaxOffsetSqlProjectionBuilder(connection=connection, redis_helper=redis_helper)
        refresh_service = TaxOffsetReadModelRefreshService(projection_builder=projection_builder, queue_repository=queue)
        handlers["tax_offset.read_model.refresh"] = refresh_service.handle_runtime_event
        if "tax_offset.read_model.refresh" not in config.event_types:
            config.event_types.append("tax_offset.read_model.refresh")
    if args.enable_search_read_model_refresh or args.enable_pending_invoice_read_model_refresh:
        projection_builder = SearchPendingSqlProjectionBuilder(connection=connection)
        refresh_service = SearchPendingReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        if args.enable_search_read_model_refresh:
            handlers["search.read_model.refresh"] = refresh_service.handle_runtime_event
            if "search.read_model.refresh" not in config.event_types:
                config.event_types.append("search.read_model.refresh")
        if args.enable_pending_invoice_read_model_refresh:
            handlers["pending_invoice.read_model.refresh"] = refresh_service.handle_runtime_event
            if "pending_invoice.read_model.refresh" not in config.event_types:
                config.event_types.append("pending_invoice.read_model.refresh")
    if args.enable_bank_detail_read_model_refresh:
        projection_builder = BankDetailSqlProjectionBuilder(connection=connection)
        refresh_service = BankDetailReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["bank_detail.read_model.refresh"] = refresh_service.handle_runtime_event
        if "bank_detail.read_model.refresh" not in config.event_types:
            config.event_types.append("bank_detail.read_model.refresh")
    if args.enable_bank_account_balance_read_model_refresh:
        projection_builder = BankAccountBalanceProjectionBuilder(connection=connection)
        refresh_service = BankAccountBalanceReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["bank_account_balance.read_model.refresh"] = refresh_service.handle_runtime_event
        if "bank_account_balance.read_model.refresh" not in config.event_types:
            config.event_types.append("bank_account_balance.read_model.refresh")
    if (
        args.enable_input_invoice_usage_read_model_refresh
        or args.enable_output_invoice_collection_read_model_refresh
        or args.enable_oa_pending_payment_read_model_refresh
    ):
        projection_builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=connection)
        refresh_service = InvoiceUsageCollectionReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        if args.enable_input_invoice_usage_read_model_refresh:
            handlers["input_invoice_usage.read_model.refresh"] = refresh_service.handle_runtime_event
            if "input_invoice_usage.read_model.refresh" not in config.event_types:
                config.event_types.append("input_invoice_usage.read_model.refresh")
        if args.enable_output_invoice_collection_read_model_refresh:
            handlers["output_invoice_collection.read_model.refresh"] = refresh_service.handle_runtime_event
            if "output_invoice_collection.read_model.refresh" not in config.event_types:
                config.event_types.append("output_invoice_collection.read_model.refresh")
        if args.enable_oa_pending_payment_read_model_refresh:
            handlers["oa_pending_payment.read_model.refresh"] = refresh_service.handle_runtime_event
            if "oa_pending_payment.read_model.refresh" not in config.event_types:
                config.event_types.append("oa_pending_payment.read_model.refresh")
    if args.enable_import_job_processing:
        from fin_ops_platform.app.server import Application

        import_application = Application(data_dir=default_data_dir())
        import_job_repository = ImportJobRepository(connection)
        import_job_worker = ImportJobWorker(
            repository=import_job_repository,
            worker_id=config.worker_id,
            processors=import_application.build_import_job_processors(),
        )
        handlers[IMPORT_PROCESS_REQUESTED_EVENT] = import_job_worker.handle_runtime_event
        handlers[IMPORT_FACT_CHANGED_EVENT] = _handle_import_fact_changed_event
        if IMPORT_PROCESS_REQUESTED_EVENT not in config.event_types:
            config.event_types.append(IMPORT_PROCESS_REQUESTED_EVENT)
        if queue_settings.backend == "postgres" and IMPORT_FACT_CHANGED_EVENT not in config.event_types:
            config.event_types.append(IMPORT_FACT_CHANGED_EVENT)

    if args.check:
        print(
            json.dumps(
                {
                    "service": "fin-ops-platform-worker",
                    "postgres": settings.redacted_database_url,
                    "queue_backend": queue_settings.backend,
                    "rabbitmq_configured": bool(queue_settings.rabbitmq_url),
                    "rabbitmq_exchange": queue_settings.rabbitmq_exchange,
                    "rabbitmq_event_routes": {
                        event_type: {
                            "queue": route.queue,
                            "routing_key": route.routing_key,
                            "dead_letter_queue": route.dead_letter_queue,
                        }
                        for event_type, route in rabbitmq_event_routes(queue_settings).items()
                        if event_type in config.event_types
                    },
                    "redis_enabled": redis_helper.enabled,
                    "runtime_transport": "rabbitmq" if queue_settings.backend == "rabbitmq" else "postgres",
                    "worker_kind": config.worker_kind,
                    "event_types": config.event_types,
                    "handlers": sorted(handlers),
                    "poll_interval_seconds": config.poll_interval_seconds,
                    "lock_timeout_seconds": config.lock_timeout_seconds,
                    "task_timeout_seconds": config.task_timeout_seconds,
                    "statement_timeout_seconds": config.statement_timeout_seconds,
                    "max_attempts": config.max_attempts,
                    "max_events_per_iteration": config.max_events_per_iteration,
                    "workbench_matching_enabled": bool(args.enable_workbench_matching),
                    "workbench_matching_batch_size": args.workbench_matching_batch_size,
                    "workbench_matching_lease_seconds": args.workbench_matching_lease_seconds,
                    "workbench_matching_retry_delay_seconds": args.workbench_matching_retry_delay_seconds,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    if args.enable_workbench_matching:
        from fin_ops_platform.app.server import Application

        workbench_application = Application(data_dir=default_data_dir())
        workbench_dirty_scope_worker = _build_workbench_matching_dirty_scope_worker(
            workbench_application,
            heartbeat_recorder=queue,
            worker_id=config.worker_id,
            poll_interval_seconds=args.poll_interval_seconds,
            batch_size=args.workbench_matching_batch_size,
            lease_seconds=args.workbench_matching_lease_seconds,
            retry_delay_seconds=args.workbench_matching_retry_delay_seconds,
            max_iterations=args.max_iterations,
        )
        if not config.event_types and not handlers:
            workbench_dirty_scope_worker.run_forever()
            return 0
        Thread(
            target=workbench_dirty_scope_worker.run_forever,
            daemon=True,
        ).start()

    worker = RuntimeWorker(queue_repository=queue, config=config, redis_helper=redis_helper, handlers=handlers)
    if queue_settings.backend == "rabbitmq":
        event_types = list(config.event_types or sorted(handlers))
        consumer = RabbitMqConsumer(
            settings=queue_settings,
            queue_repository=queue,
            worker=worker,
            worker_id=config.worker_id,
            event_types=event_types,
            lock_timeout_seconds=config.lock_timeout_seconds,
        )
        consumer.consume_forever()
        return 0
    worker.run_forever()
    return 0


def _build_workbench_matching_dirty_scope_worker(
    application: Any,
    *,
    heartbeat_recorder: Any,
    worker_id: str,
    poll_interval_seconds: float,
    batch_size: int,
    lease_seconds: int,
    retry_delay_seconds: int | None,
    max_iterations: int | None,
) -> WorkbenchMatchingDirtyScopeWorker:
    dirty_queue = _required_application_dependency(application, "_workbench_reconciliation_dirty_queue")
    matching_orchestrator = _required_application_dependency(application, "_workbench_matching_orchestrator")
    source_versions_provider = _required_application_dependency(application, "_workbench_matching_source_versions")
    if not callable(source_versions_provider):
        raise RuntimeError("Workbench matching worker requires a callable source version provider.")
    return WorkbenchMatchingDirtyScopeWorker(
        dirty_queue=dirty_queue,
        matching_orchestrator=matching_orchestrator,
        source_versions_provider=source_versions_provider,
        heartbeat_recorder=heartbeat_recorder,
        config=WorkbenchMatchingDirtyScopeWorkerConfig(
            worker_id=worker_id,
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            retry_delay_seconds=retry_delay_seconds,
            max_iterations=max_iterations,
        ),
    )


def _required_application_dependency(application: Any, attr_name: str) -> Any:
    dependency = getattr(application, attr_name, None)
    if dependency is None:
        raise RuntimeError(f"Workbench matching worker requires Application.{attr_name}.")
    return dependency


def _handle_import_fact_changed_event(event: Any) -> dict[str, Any]:
    scope_type = str(getattr(event, "scope_type", None) or event.payload.get("scope_type") or "").strip()
    scope_key = str(getattr(event, "scope_key", None) or event.payload.get("scope_key") or "").strip()
    return {
        "status": "acknowledged",
        "event_type": IMPORT_FACT_CHANGED_EVENT,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "note": "import fact dirty scopes are persisted by the import fact writer",
    }


def _handle_etc_business_oa_detection_event(service: Any, event: Any) -> dict[str, Any]:
    payload = getattr(event, "payload", {}) or {}
    business_batch_id = str(payload.get("business_batch_id") or getattr(event, "aggregate_id", "") or "").strip()
    if not business_batch_id:
        raise ValueError("business_batch_id is required for ETC OA detection event.")
    expected_version = payload.get("expected_version")
    if expected_version in (None, ""):
        expected_version = None
    else:
        expected_version = int(expected_version)
    batch = service.refresh_oa_detection(business_batch_id, expected_version=expected_version)
    if str(getattr(batch, "status", "")) == "oa_submission_detecting":
        service.enqueue_oa_detection(batch)
    else:
        service.sync_invoices_after_oa_detection(batch, reason="etc_business_oa_status_detected_async")
    return {
        "status": str(getattr(batch, "status", "")),
        "business_batch_id": business_batch_id,
        "version": int(getattr(batch, "version", 0) or 0),
    }


def _infer_worker_kind(args: argparse.Namespace) -> str:
    enabled = []
    for registration in worker_registrations():
        if not registration.handler_flags:
            continue
        attr_names = [_argparse_attr_name(flag) for flag in registration.handler_flags]
        if any(bool(getattr(args, attr_name, False)) for attr_name in attr_names):
            enabled.append(registration.worker_kind)
    return enabled[0] if len(enabled) == 1 else "runtime"


def _argparse_attr_name(flag: str) -> str:
    return flag.lstrip("-").replace("-", "_")


def _build_oa_sync_source_adapter(
    *,
    settings: Any,
    attachment_invoice_cache: Any,
) -> MongoOAAdapter:
    return MongoOAAdapter(settings=settings, attachment_invoice_cache=attachment_invoice_cache)


def _load_oa_runtime_settings(connection: PostgresConnection) -> dict[str, Any]:
    row = connection.fetch_one(
        "select settings_payload from app.app_settings where settings_key = %s",
        (APP_SETTINGS_KEY,),
    )
    payload = row.get("settings_payload") if isinstance(row, dict) else {}
    settings = payload if isinstance(payload, dict) else {}
    import_settings = settings.get("oa_import") if isinstance(settings.get("oa_import"), dict) else {}
    retention_settings = settings.get("oa_retention") if isinstance(settings.get("oa_retention"), dict) else {}
    return {
        "cutoff_date": str(retention_settings.get("cutoff_date") or DEFAULT_OA_RETENTION_CUTOFF_DATE).strip()
        or DEFAULT_OA_RETENTION_CUTOFF_DATE,
        "oa_import": {
            "form_types": _normalize_option_list(
                import_settings.get("form_types"),
                allowed_values=OA_IMPORT_FORM_TYPES,
                default_values=DEFAULT_OA_IMPORT_FORM_TYPES,
            ),
            "statuses": _normalize_option_list(
                import_settings.get("statuses"),
                allowed_values=OA_IMPORT_STATUSES,
                default_values=DEFAULT_OA_IMPORT_STATUSES,
            ),
        },
    }


def _normalize_option_list(value: Any, *, allowed_values: set[str], default_values: list[str]) -> list[str]:
    if not isinstance(value, list):
        return list(default_values)
    seen = {str(item).strip() for item in value if str(item).strip() in allowed_values}
    return [item for item in default_values if item in seen] + [
        item for item in sorted(seen) if item not in default_values
    ]


if __name__ == "__main__":
    raise SystemExit(main())
