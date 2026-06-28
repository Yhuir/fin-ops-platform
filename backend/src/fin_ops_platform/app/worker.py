from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from types import SimpleNamespace
from threading import Thread
from typing import Any

from fin_ops_platform.services.app_settings_service import (
    AppSettingsService,
    DEFAULT_OA_IMPORT_FORM_TYPES,
    DEFAULT_OA_IMPORT_STATUSES,
    DEFAULT_OA_RETENTION_CUTOFF_DATE,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_effective_category_provider import BankTransactionEffectiveCategoryProvider
from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.import_job_queue import IMPORT_PROCESS_REQUESTED_EVENT
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_pending_payment_relation_promotion_service import OaPendingPaymentRelationPromotionService
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION, PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.postgres_state_store import LegacyGridFSFileReader, PostgresStateStore
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository, RuntimeQueueSettings
from fin_ops_platform.services.rabbitmq_runtime import RabbitMqConsumer, rabbitmq_event_routes
from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig
from fin_ops_platform.services.runtime_worker_handlers import (
    IMPORT_FACT_CHANGED_EVENT,
    ImportRuntimeProcessorFactory,
    WorkbenchMatchingWorkerFactory,
    build_import_job_handler_bundle,
    check_import_job_processors,
    handle_import_fact_changed_event,
)
from fin_ops_platform.services.runtime_worker_registry import (
    RuntimeWorkerRegistration,
    get_registration_by_instance_name,
    worker_claim_event_types,
    worker_registrations,
)
from fin_ops_platform.services.state_store import default_data_dir
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService
from fin_ops_platform.services.workbench_candidate_match_service import CANDIDATE_MATCH_SCHEMA_VERSION
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_exception_rules import RULE_VERSION as WORKBENCH_EXCEPTION_RULE_VERSION
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_projection_versions import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


APP_SETTINGS_KEY = "app_settings"
OA_IMPORT_FORM_TYPES = {"payment_request", "expense_claim"}
OA_IMPORT_STATUSES = {"completed", "in_progress"}
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform standalone runtime worker")
    parser.add_argument("--registration", default=None, help="Runtime worker registry instance name to enable.")
    parser.add_argument("--worker-instance", default=None, help="Expected runtime worker instance name.")
    parser.add_argument("--worker-id", default=None, help="Stable worker id for PostgreSQL locks and heartbeats.")
    parser.add_argument("--worker-kind", default=None, help="Worker heartbeat kind. Defaults to the enabled handler family.")
    parser.add_argument("--event-type", action="append", default=[], help="Outbox event type to claim. Repeatable.")
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--lock-timeout-seconds", type=int, default=300)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    parser.add_argument("--dependency-not-fresh-delay-seconds", type=float, default=2.0)
    parser.add_argument("--max-attempts", type=int, default=5)
    parser.add_argument("--task-timeout-seconds", type=int, default=None)
    parser.add_argument("--statement-timeout-seconds", type=int, default=None)
    parser.add_argument("--max-iterations", type=int, default=None, help="Testing/smoke limit. Omit to run continuously.")
    parser.add_argument("--max-events-per-iteration", type=int, default=1, help="Maximum events to drain before an idle sleep.")
    parser.add_argument("--enable-file-object-migration", action="store_true", help="Register GridFS to object storage migration handler.")
    parser.add_argument("--enable-oa-sync", action="store_true", help="Register OA Mongo to PostgreSQL projection sync handler.")
    parser.add_argument("--enable-import-job-processing", action="store_true", help="Register import job worker handler.")
    parser.add_argument("--enable-workbench-matching", action="store_true", help="Poll DB-backed workbench matching dirty scopes.")
    parser.add_argument("--workbench-matching-batch-size", type=int, default=10)
    parser.add_argument("--workbench-matching-lease-seconds", type=int, default=600)
    parser.add_argument("--workbench-matching-retry-delay-seconds", type=int, default=None)
    parser.add_argument("--check", action="store_true", help="Print worker configuration and exit without polling.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    postgres_configuration_error = ""
    try:
        settings = PostgresSettings.from_env()
    except PostgresConfigurationError as exc:
        if not args.check:
            raise
        settings = None
        postgres_configuration_error = str(exc)
    queue_settings = RuntimeQueueSettings.from_env()
    registration = _apply_registration_args(args, queue_settings=queue_settings)
    connection = PostgresConnection(settings) if settings is not None else None
    queue = RuntimeQueueRepository(connection) if connection is not None else SimpleNamespace()
    read_model_repository = PostgresReadModelRepository(connection) if connection is not None else None
    redis_helper = RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env())
    config = RuntimeWorkerConfig(
        worker_id=args.worker_id or RuntimeWorkerConfig().worker_id,
        worker_instance=args.worker_instance or getattr(registration, "instance_name", None),
        event_types=list(args.event_type or []),
        poll_interval_seconds=args.poll_interval_seconds,
        lock_timeout_seconds=args.lock_timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
        dependency_not_fresh_delay_seconds=args.dependency_not_fresh_delay_seconds,
        task_timeout_seconds=args.task_timeout_seconds,
        statement_timeout_seconds=args.statement_timeout_seconds,
        max_iterations=args.max_iterations,
        max_events_per_iteration=args.max_events_per_iteration,
        max_attempts=args.max_attempts,
        worker_kind=args.worker_kind or _infer_worker_kind(args),
    )
    oa_payment_source_adapter: MongoOAAdapter | None = None

    def _oa_payment_source_adapter() -> MongoOAAdapter | None:
        nonlocal oa_payment_source_adapter
        if oa_payment_source_adapter is not None:
            return oa_payment_source_adapter
        if connection is None:
            return None
        oa_settings = load_mongo_oa_settings(default_data_dir())
        if oa_settings is None:
            return None
        ops_tax_etc_repository = PostgresOpsTaxEtcRepository(connection)
        adapter = _build_oa_sync_source_adapter(
            settings=oa_settings,
            attachment_invoice_cache=ops_tax_etc_repository,
        )
        oa_runtime_settings = _load_oa_runtime_settings(connection)
        adapter.set_import_settings_provider(lambda: dict(oa_runtime_settings["oa_import"]))
        oa_payment_source_adapter = adapter
        return adapter

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
        oa_payment_source_adapter = source_adapter
        oa_runtime_settings = _load_oa_runtime_settings(connection)
        source_adapter.set_import_settings_provider(lambda: dict(oa_runtime_settings["oa_import"]))
        projection_repository = PostgresOAProjectionRepository(connection)
        pending_relation_repository = PostgresOaPendingPaymentRelationRepository(connection)
        relation_command_service = WorkbenchRelationCommandService(
            relation_repository=PostgresWorkbenchRelationRepository(connection),
        )
        pending_relation_promoter = OaPendingPaymentRelationPromotionService(
            pending_relation_service=pending_relation_repository,
            relation_command_service=relation_command_service,
        )
        sync_service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=queue,
            retention_cutoff_date_provider=lambda: str(oa_runtime_settings["cutoff_date"]),
            pending_payment_relation_promoter=pending_relation_promoter,
        )
        handlers["oa.sync"] = sync_service.handle_runtime_event
        if "oa.sync" not in config.event_types:
            config.event_types.append("oa.sync")
    if args.enable_import_job_processing:
        import_processors = (
            check_import_job_processors()
            if args.check
            else ImportRuntimeProcessorFactory(
                data_dir=default_data_dir(),
                connection=connection,
                queue_repository=queue,
            ).build_processors()
        )
        import_handlers = build_import_job_handler_bundle(
            connection=connection,
            worker_id=config.worker_id,
            processors=import_processors,
            include_import_fact_changed=True,
            queue_repository=queue,
        )
        handlers.update(import_handlers.handlers)
        if IMPORT_PROCESS_REQUESTED_EVENT not in config.event_types:
            config.event_types.append(IMPORT_PROCESS_REQUESTED_EVENT)
        if IMPORT_FACT_CHANGED_EVENT not in config.event_types:
            config.event_types.append(IMPORT_FACT_CHANGED_EVENT)

    if args.check:
        print(
            json.dumps(
                {
                    "service": "fin-ops-platform-worker",
                    "postgres": settings.redacted_database_url if settings is not None else "unconfigured",
                    "postgres_config_error": postgres_configuration_error,
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
                    "worker_instance": args.worker_instance or getattr(registration, "instance_name", None),
                    "worker_kind": config.worker_kind,
                    "event_types": config.event_types,
                    "handlers": sorted(handlers),
                    "registration": _registration_check_payload(registration),
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
        workbench_dirty_scope_worker = WorkbenchMatchingWorkerFactory(
            data_dir=default_data_dir(),
            connection=connection,
        ).build_dirty_scope_worker(
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


def _handle_import_fact_changed_event(event: Any) -> dict[str, Any]:
    return handle_import_fact_changed_event(event)


def _no_oa_workbench_matching_source_versions(app_settings_service: AppSettingsService) -> dict[str, object]:
    payload: dict[str, object] = {
        "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
        "workbench_candidate_match_schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
        "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
        "workbench_exception_rules_version": WORKBENCH_EXCEPTION_RULE_VERSION,
        "workbench_exception_projection_version": EXCEPTION_PROJECTION_VERSION,
        "bank_auto_tag_rules_version": _current_bank_auto_tag_rules_version(app_settings_service),
    }
    parser_version = MongoOAAdapter._attachment_invoice_cache_parser_version()
    if parser_version:
        payload["oa_attachment_invoice_parser_version"] = parser_version
    if OA_PROJECTION_SYNC_VERSION:
        payload["oa_projection_sync_version"] = OA_PROJECTION_SYNC_VERSION
    return payload


def _current_bank_auto_tag_rules_version(app_settings_service: AppSettingsService) -> int:
    try:
        payload = app_settings_service.get_bank_auto_tag_rules_payload(can_save=False)
        return int(payload.get("version") or 1)
    except Exception:
        return 1


def _infer_worker_kind(args: argparse.Namespace) -> str:
    enabled = []
    for registration in worker_registrations():
        if not registration.handler_flags:
            continue
        attr_names = [_argparse_attr_name(flag) for flag in registration.handler_flags]
        if any(bool(getattr(args, attr_name, False)) for attr_name in attr_names):
            enabled.append(registration.worker_kind)
    return enabled[0] if len(enabled) == 1 else "runtime"


def _apply_registration_args(
    args: argparse.Namespace,
    *,
    queue_settings: RuntimeQueueSettings,
) -> RuntimeWorkerRegistration | None:
    if not args.registration:
        return None
    try:
        registration = get_registration_by_instance_name(str(args.registration))
    except KeyError as exc:
        raise SystemExit(str(exc)) from exc
    if args.worker_instance and args.worker_instance != registration.instance_name:
        raise SystemExit(
            f"Worker instance {args.worker_instance!r} does not match registration {registration.instance_name!r}."
        )
    args.worker_instance = registration.instance_name
    if args.worker_kind and args.worker_kind != registration.worker_kind:
        raise SystemExit(
            f"Worker kind {args.worker_kind!r} does not match registration kind {registration.worker_kind!r}."
        )
    args.worker_kind = registration.worker_kind
    for flag in registration.handler_flags:
        setattr(args, _argparse_attr_name(flag), True)
    transport = "rabbitmq" if queue_settings.backend == "rabbitmq" else "postgres"
    args.event_type = list(worker_claim_event_types(registration, transport=transport))
    return registration


def _registration_check_payload(registration: RuntimeWorkerRegistration | None) -> dict[str, object] | None:
    if registration is None:
        return None
    return {
        "instance_name": registration.instance_name,
        "worker_kind": registration.worker_kind,
        "required": registration.required,
        "rabbitmq_eligible": registration.rabbitmq_eligible,
        "event_types": list(registration.event_types),
        "postgres_claim_event_types": list(registration.claim_event_types(transport="postgres")),
        "rabbitmq_claim_event_types": list(registration.claim_event_types(transport="rabbitmq")),
        "handler_flags": list(registration.handler_flags),
    }


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
