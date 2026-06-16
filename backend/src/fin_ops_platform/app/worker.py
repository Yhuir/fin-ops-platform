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
from fin_ops_platform.services.bank_account_balance_projection import BankAccountBalanceProjectionBuilder
from fin_ops_platform.services.bank_account_balance_read_model_refresh import BankAccountBalanceReadModelRefreshService
from fin_ops_platform.services.bank_detail_read_model_refresh import BankDetailReadModelRefreshService
from fin_ops_platform.services.bank_detail_sql_projection import BankDetailSqlProjectionBuilder
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_effective_category_provider import BankTransactionEffectiveCategoryProvider
from fin_ops_platform.services.bank_transaction_tag_read_facade import BankTransactionTagReadFacade
from fin_ops_platform.services.cost_tax_sql_projection import (
    CostStatisticsSqlProjectionBuilder,
    TaxOffsetSqlProjectionBuilder,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.import_job_queue import IMPORT_PROCESS_REQUESTED_EVENT
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_usage_collection_read_model_refresh import (
    InvoiceUsageCollectionReadModelRefreshService,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import InvoiceUsageCollectionSqlProjectionBuilder
from fin_ops_platform.services.invoice_lifecycle_read_model_refresh import (
    INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE,
    InvoiceLifecycleReadModelRefreshService,
)
from fin_ops_platform.services.invoice_lifecycle_sql_projection import InvoiceLifecycleSqlProjectionBuilder
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.no_oa_bank_batch_read_model_refresh import (
    NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE,
    NoOaBankBatchReadModelRefreshService,
)
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION, PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_state_store import LegacyGridFSFileReader, PostgresStateStore
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository, RuntimeQueueSettings
from fin_ops_platform.services.rabbitmq_runtime import RabbitMqConsumer, rabbitmq_event_routes
from fin_ops_platform.services.read_model_readiness import ReadModelReadinessReporter
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
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
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder
from fin_ops_platform.services.state_store import default_data_dir
from fin_ops_platform.services.tax_offset_read_model_refresh import TaxOffsetReadModelRefreshService
from fin_ops_platform.services.turnover_ledger_read_model_refresh import TurnoverLedgerReadModelRefreshService
from fin_ops_platform.services.turnover_ledger_sql_projection import TurnoverLedgerSqlProjectionBuilder
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade
from fin_ops_platform.services.workbench_relation_read_model_refresh import (
    WORKBENCH_RELATION_REFRESH_EVENT_TYPE,
    WorkbenchRelationReadModelRefreshService,
)
from fin_ops_platform.services.workbench_relation_sql_projection import WorkbenchRelationSqlProjectionBuilder
from fin_ops_platform.services.workbench_candidate_match_service import CANDIDATE_MATCH_SCHEMA_VERSION
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_exception_rules import RULE_VERSION as WORKBENCH_EXCEPTION_RULE_VERSION
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_groups_page_cache import (
    WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION,
    WorkbenchGroupsPageCacheWarmer,
    workbench_groups_sync_cache_warmup_enabled_from_env,
    workbench_groups_redis_ttl_seconds_from_env,
)
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION, WorkbenchSqlProjectionBuilder


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
    parser.add_argument("--enable-workbench-read-model-refresh", action="store_true", help="Register workbench SQL read model refresh handler.")
    parser.add_argument("--enable-workbench-relation-read-model-refresh", action="store_true", help="Register workbench relation distribution read model refresh handler.")
    parser.add_argument("--enable-cost-statistics-read-model-refresh", action="store_true", help="Register cost statistics SQL read model refresh handler.")
    parser.add_argument("--enable-tax-offset-read-model-refresh", action="store_true", help="Register tax offset SQL read model refresh handler.")
    parser.add_argument("--enable-search-read-model-refresh", action="store_true", help="Register search SQL read model refresh handler.")
    parser.add_argument("--enable-pending-invoice-read-model-refresh", action="store_true", help="Register pending invoice SQL read model refresh handler.")
    parser.add_argument("--enable-invoice-lifecycle-read-model-refresh", action="store_true", help="Register invoice lifecycle SQL read model refresh handler.")
    parser.add_argument("--enable-bank-account-balance-read-model-refresh", action="store_true", help="Register bank account balance SQL read model refresh handler.")
    parser.add_argument("--enable-bank-detail-read-model-refresh", action="store_true", help="Register bank detail SQL read model refresh handler.")
    parser.add_argument("--enable-no-oa-bank-batch-read-model-refresh", action="store_true", help="Register no-OA bank batch SQL read model refresh handler.")
    parser.add_argument("--enable-turnover-ledger-read-model-refresh", action="store_true", help="Register turnover ledger SQL read model refresh handler.")
    parser.add_argument("--enable-input-invoice-usage-read-model-refresh", action="store_true", help="Register input invoice usage SQL read model refresh handler.")
    parser.add_argument("--enable-output-invoice-collection-read-model-refresh", action="store_true", help="Register output invoice collection SQL read model refresh handler.")
    parser.add_argument("--enable-oa-pending-payment-read-model-refresh", action="store_true", help="Register OA pending payment SQL read model refresh handler.")
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
    bank_transaction_tag_read_facade = (
        BankTransactionTagReadFacade(
            read_model_repository=read_model_repository,
            queue_repository=queue,
        )
        if read_model_repository is not None
        else None
    )
    workbench_relation_read_facade = (
        WorkbenchRelationReadFacade(
            read_model_repository=read_model_repository,
            queue_repository=queue,
        )
        if read_model_repository is not None
        else None
    )
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
    readiness_reporter = (
        ReadModelReadinessReporter(readiness_repository=RuntimeMonitoringRepository(connection))
        if connection is not None
        else None
    )

    def _read_model_handler(handler: Any) -> Any:
        return readiness_reporter.wrap_handler(handler) if readiness_reporter is not None else handler

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
    if args.enable_workbench_read_model_refresh:
        projection_builder = WorkbenchSqlProjectionBuilder(connection=connection)
        page_cache_warmer = (
            WorkbenchGroupsPageCacheWarmer(
                repository=read_model_repository,
                redis_helper=redis_helper,
                schema_version=WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION,
                ttl_seconds=workbench_groups_redis_ttl_seconds_from_env(),
            )
            if workbench_groups_sync_cache_warmup_enabled_from_env()
            else None
        )
        refresh_service = WorkbenchReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
            post_refresh_warmer=page_cache_warmer.warm_scope if page_cache_warmer is not None else None,
        )
        handlers["workbench.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "workbench.read_model.refresh" not in config.event_types:
            config.event_types.append("workbench.read_model.refresh")
    if args.enable_workbench_relation_read_model_refresh:
        projection_builder = WorkbenchRelationSqlProjectionBuilder(
            connection=connection,
            read_model_repository=read_model_repository,
        )
        refresh_service = WorkbenchRelationReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers[WORKBENCH_RELATION_REFRESH_EVENT_TYPE] = _read_model_handler(refresh_service.handle_runtime_event)
        if WORKBENCH_RELATION_REFRESH_EVENT_TYPE not in config.event_types:
            config.event_types.append(WORKBENCH_RELATION_REFRESH_EVENT_TYPE)
    if args.enable_cost_statistics_read_model_refresh:
        projection_builder = CostStatisticsSqlProjectionBuilder(connection=connection, redis_helper=redis_helper)
        refresh_service = CostStatisticsReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["cost_statistics.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "cost_statistics.read_model.refresh" not in config.event_types:
            config.event_types.append("cost_statistics.read_model.refresh")
    if args.enable_tax_offset_read_model_refresh:
        projection_builder = TaxOffsetSqlProjectionBuilder(connection=connection, redis_helper=redis_helper)
        refresh_service = TaxOffsetReadModelRefreshService(projection_builder=projection_builder, queue_repository=queue)
        handlers["tax_offset.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "tax_offset.read_model.refresh" not in config.event_types:
            config.event_types.append("tax_offset.read_model.refresh")
    if args.enable_search_read_model_refresh or args.enable_pending_invoice_read_model_refresh:
        projection_builder = SearchPendingSqlProjectionBuilder(
            connection=connection,
            read_model_repository=read_model_repository,
            bank_transaction_tag_read_facade=bank_transaction_tag_read_facade,
            workbench_relation_read_facade=workbench_relation_read_facade,
        )
        refresh_service = SearchPendingReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        if args.enable_search_read_model_refresh:
            handlers["search.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
            if "search.read_model.refresh" not in config.event_types:
                config.event_types.append("search.read_model.refresh")
        if args.enable_pending_invoice_read_model_refresh:
            handlers["pending_invoice.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
            if "pending_invoice.read_model.refresh" not in config.event_types:
                config.event_types.append("pending_invoice.read_model.refresh")
    if args.enable_bank_detail_read_model_refresh:
        projection_builder = BankDetailSqlProjectionBuilder(
            connection=connection,
            workbench_relation_read_facade=workbench_relation_read_facade,
        )
        refresh_service = BankDetailReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["bank_detail.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "bank_detail.read_model.refresh" not in config.event_types:
            config.event_types.append("bank_detail.read_model.refresh")
    if args.enable_no_oa_bank_batch_read_model_refresh:
        state_store = PostgresStateStore(data_dir=default_data_dir(), connection=connection) if connection is not None else None
        category_service = BankTransactionCategoryService.from_snapshot(
            state_store.load_bank_transaction_categories() if state_store is not None else {}
        )
        auto_category_service = BankTransactionAutoCategoryService(category_service=category_service)
        app_settings_service = AppSettingsService(
            state_store,
            SimpleNamespace(restore_manual_projects=lambda _projects: None, list_projects=lambda: []),
            bank_transaction_category_service=category_service,
            bank_transaction_auto_category_service=auto_category_service,
        )
        pair_relation_service = WorkbenchPairRelationService.from_snapshot(
            state_store.load_workbench_pair_relations() if state_store is not None else {}
        )
        no_oa_service = NoOaBankBatchService.from_snapshot(
            state_store.load_no_oa_bank_batches() if state_store is not None else {},
            pair_relation_service=pair_relation_service,
        )
        refresh_service = NoOaBankBatchReadModelRefreshService(
            import_service=ImportNormalizationService(
                fact_repository=state_store.import_fact_repository if state_store is not None else None
            ),
            effective_category_provider=bank_transaction_tag_read_facade
            or BankTransactionEffectiveCategoryProvider(
                category_service=category_service,
                auto_category_service=auto_category_service,
            ),
            no_oa_bank_batch_service=no_oa_service,
            app_settings_service=app_settings_service,
            bank_transaction_category_service=category_service,
            pair_relation_service=pair_relation_service,
            workbench_read_model_service=WorkbenchReadModelService.from_snapshot(
                {}
            ),
            state_store=state_store or SimpleNamespace(save_no_oa_bank_batches=lambda _snapshot: None),
            queue_repository=queue,
            workbench_matching_source_versions_provider=lambda: _no_oa_workbench_matching_source_versions(
                app_settings_service
            ),
            relation_facade=workbench_relation_read_facade,
        )
        handlers[NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE] = _read_model_handler(refresh_service.handle_runtime_event)
        if NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE not in config.event_types:
            config.event_types.append(NO_OA_BANK_BATCH_REFRESH_EVENT_TYPE)
    if args.enable_turnover_ledger_read_model_refresh:
        projection_builder = TurnoverLedgerSqlProjectionBuilder(
            connection=connection,
            bank_transaction_tag_read_facade=bank_transaction_tag_read_facade,
            workbench_relation_read_facade=workbench_relation_read_facade,
        )
        refresh_service = TurnoverLedgerReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["turnover_ledger.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "turnover_ledger.read_model.refresh" not in config.event_types:
            config.event_types.append("turnover_ledger.read_model.refresh")
    if args.enable_bank_account_balance_read_model_refresh:
        projection_builder = BankAccountBalanceProjectionBuilder(connection=connection)
        refresh_service = BankAccountBalanceReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers["bank_account_balance.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
        if "bank_account_balance.read_model.refresh" not in config.event_types:
            config.event_types.append("bank_account_balance.read_model.refresh")
    if args.enable_invoice_lifecycle_read_model_refresh:
        projection_builder = InvoiceLifecycleSqlProjectionBuilder(
            connection=connection,
            read_model_repository=read_model_repository,
            workbench_relation_read_facade=workbench_relation_read_facade,
        )
        refresh_service = InvoiceLifecycleReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        handlers[INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE] = _read_model_handler(refresh_service.handle_runtime_event)
        if INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE not in config.event_types:
            config.event_types.append(INVOICE_LIFECYCLE_REFRESH_EVENT_TYPE)
    if (
        args.enable_input_invoice_usage_read_model_refresh
        or args.enable_output_invoice_collection_read_model_refresh
        or args.enable_oa_pending_payment_read_model_refresh
    ):
        projection_builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=connection,
            workbench_relation_read_facade=workbench_relation_read_facade,
        )
        refresh_service = InvoiceUsageCollectionReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        if args.enable_input_invoice_usage_read_model_refresh:
            handlers["input_invoice_usage.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
            if "input_invoice_usage.read_model.refresh" not in config.event_types:
                config.event_types.append("input_invoice_usage.read_model.refresh")
        if args.enable_output_invoice_collection_read_model_refresh:
            handlers["output_invoice_collection.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
            if "output_invoice_collection.read_model.refresh" not in config.event_types:
                config.event_types.append("output_invoice_collection.read_model.refresh")
        if args.enable_oa_pending_payment_read_model_refresh:
            handlers["oa_pending_payment.read_model.refresh"] = _read_model_handler(refresh_service.handle_runtime_event)
            if "oa_pending_payment.read_model.refresh" not in config.event_types:
                config.event_types.append("oa_pending_payment.read_model.refresh")
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
        )
        handlers.update(import_handlers.handlers)
        if IMPORT_PROCESS_REQUESTED_EVENT not in config.event_types:
            config.event_types.append(IMPORT_PROCESS_REQUESTED_EVENT)
        if queue_settings.backend == "postgres" and IMPORT_FACT_CHANGED_EVENT not in config.event_types:
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
