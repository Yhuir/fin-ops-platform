from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.file_object_migration import GridFSObjectMigrationService
from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_projection_sync import OAProjectionSyncService
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
from fin_ops_platform.services.postgres_state_store import LegacyGridFSFileReader
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_redis import RuntimeRedisHelper, RuntimeRedisSettings
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.state_store import default_data_dir
from fin_ops_platform.services.tax_offset_read_model_refresh import TaxOffsetReadModelRefreshService
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="fin-ops-platform standalone runtime worker")
    parser.add_argument("--worker-id", default=None, help="Stable worker id for PostgreSQL locks and heartbeats.")
    parser.add_argument("--event-type", action="append", default=[], help="Outbox event type to claim. Repeatable.")
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--lock-timeout-seconds", type=int, default=300)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    parser.add_argument("--max-iterations", type=int, default=None, help="Testing/smoke limit. Omit to run continuously.")
    parser.add_argument("--enable-file-object-migration", action="store_true", help="Register GridFS to object storage migration handler.")
    parser.add_argument("--enable-workbench-read-model-refresh", action="store_true", help="Register workbench SQL read model refresh handler.")
    parser.add_argument("--enable-cost-statistics-read-model-refresh", action="store_true", help="Register cost statistics SQL read model refresh handler.")
    parser.add_argument("--enable-tax-offset-read-model-refresh", action="store_true", help="Register tax offset SQL read model refresh handler.")
    parser.add_argument("--enable-search-read-model-refresh", action="store_true", help="Register search SQL read model refresh handler.")
    parser.add_argument("--enable-pending-invoice-read-model-refresh", action="store_true", help="Register pending invoice SQL read model refresh handler.")
    parser.add_argument("--enable-oa-sync", action="store_true", help="Register OA Mongo to PostgreSQL projection sync handler.")
    parser.add_argument("--check", action="store_true", help="Print worker configuration and exit without polling.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    queue = RuntimeQueueRepository(connection)
    redis_helper = RuntimeRedisHelper.from_settings(RuntimeRedisSettings.from_env())
    config = RuntimeWorkerConfig(
        worker_id=args.worker_id or RuntimeWorkerConfig().worker_id,
        event_types=list(args.event_type or []),
        poll_interval_seconds=args.poll_interval_seconds,
        lock_timeout_seconds=args.lock_timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
        max_iterations=args.max_iterations,
    )
    handlers = {}
    application = None
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
        source_adapter = MongoOAAdapter(settings=oa_settings)
        projection_repository = PostgresOAProjectionRepository(connection)
        sync_service = OAProjectionSyncService(
            source_adapter=source_adapter,
            projection_repository=projection_repository,
            queue_repository=queue,
        )
        handlers["oa.sync"] = sync_service.handle_runtime_event
        if "oa.sync" not in config.event_types:
            config.event_types.append("oa.sync")
    if args.enable_workbench_read_model_refresh:
        from fin_ops_platform.app.server import build_application

        application = application or build_application(data_dir=default_data_dir())
        refresh_service = WorkbenchReadModelRefreshService(application=application, queue_repository=queue)
        handlers["workbench.read_model.refresh"] = refresh_service.handle_runtime_event
        if "workbench.read_model.refresh" not in config.event_types:
            config.event_types.append("workbench.read_model.refresh")
    if args.enable_cost_statistics_read_model_refresh:
        from fin_ops_platform.app.server import build_application

        application = application or build_application(data_dir=default_data_dir())
        refresh_service = CostStatisticsReadModelRefreshService(application=application, queue_repository=queue)
        handlers["cost_statistics.read_model.refresh"] = refresh_service.handle_runtime_event
        if "cost_statistics.read_model.refresh" not in config.event_types:
            config.event_types.append("cost_statistics.read_model.refresh")
    if args.enable_tax_offset_read_model_refresh:
        from fin_ops_platform.app.server import build_application

        application = application or build_application(data_dir=default_data_dir())
        refresh_service = TaxOffsetReadModelRefreshService(application=application, queue_repository=queue)
        handlers["tax_offset.read_model.refresh"] = refresh_service.handle_runtime_event
        if "tax_offset.read_model.refresh" not in config.event_types:
            config.event_types.append("tax_offset.read_model.refresh")
    if args.enable_search_read_model_refresh or args.enable_pending_invoice_read_model_refresh:
        from fin_ops_platform.app.server import build_application

        application = application or build_application(data_dir=default_data_dir())
        refresh_service = SearchPendingReadModelRefreshService(application=application, queue_repository=queue)
        if args.enable_search_read_model_refresh:
            handlers["search.read_model.refresh"] = refresh_service.handle_runtime_event
            if "search.read_model.refresh" not in config.event_types:
                config.event_types.append("search.read_model.refresh")
        if args.enable_pending_invoice_read_model_refresh:
            handlers["pending_invoice.read_model.refresh"] = refresh_service.handle_runtime_event
            if "pending_invoice.read_model.refresh" not in config.event_types:
                config.event_types.append("pending_invoice.read_model.refresh")

    if args.check:
        print(
            json.dumps(
                {
                    "service": "fin-ops-platform-worker",
                    "postgres": settings.redacted_database_url,
                    "redis_enabled": redis_helper.enabled,
                    "event_types": config.event_types,
                    "handlers": sorted(handlers),
                    "poll_interval_seconds": config.poll_interval_seconds,
                    "lock_timeout_seconds": config.lock_timeout_seconds,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    worker = RuntimeWorker(queue_repository=queue, config=config, redis_helper=redis_helper, handlers=handlers)
    worker.run_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
