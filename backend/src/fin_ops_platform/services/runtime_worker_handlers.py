from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.app_settings_service import (
    DEFAULT_OA_IMPORT_FORM_TYPES,
    DEFAULT_OA_IMPORT_STATUSES,
    DEFAULT_OA_RETENTION_CUTOFF_DATE,
    AppSettingsService,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.bank_account_balance_read_model_refresh_producer import (
    BankAccountBalanceReadModelRefreshProducer,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.derived_data_lifecycle_service import DerivedDataLifecycleService
from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import EtcService
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.import_job_queue import (
    IMPORT_PROCESS_REQUESTED_EVENT,
    ImportJobRepository,
    ImportJobWorker,
)
from fin_ops_platform.services.import_processing_service import ImportProcessingService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.pending_invoice_scope_planner import (
    pending_invoice_read_model_scope_keys_for_import_state,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.reconciliation import ManualReconciliationService
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.search_read_model_refresh_producer import SearchReadModelRefreshProducer
from fin_ops_platform.services.search_service import SearchService
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_exception_rules import RULE_VERSION as WORKBENCH_EXCEPTION_RULE_VERSION
from fin_ops_platform.services.workbench_free_matching_engine import (
    RULE_VERSION as WORKBENCH_FORMAL_RELATION_RULE_VERSION,
)
from fin_ops_platform.services.workbench_free_matching_engine import (
    WorkbenchFreeMatchingEngine,
)
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import WorkbenchReconciliationDirtyQueue
from fin_ops_platform.services.workbench_sql_projection import (
    WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
    WorkbenchSqlProjectionBuilder,
)
from fin_ops_platform.services.workbench_uow import RuntimeQueueReadModelRefreshWriter, WorkbenchWriteUnitOfWork

IMPORT_FACT_CHANGED_EVENT = "import.fact.changed"
IMPORT_JOB_PROCESSOR_TYPES = (
    "file_import.confirm",
    "etc_invoice_import.confirm",
    "tax_certified_import.confirm",
    "oa_manual_import.create",
)
SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class RuntimeWorkerHandlerBundle:
    handlers: dict[str, Callable[[Any], dict[str, Any]]]


class ImportRuntimeProcessorFactory:
    def __init__(self, *, data_dir: str | Path, connection: Any, queue_repository: Any | None = None) -> None:
        self._data_dir = data_dir
        self._connection = connection
        self._queue_repository = queue_repository

    def build_processors(self) -> dict[str, Callable[[Any], dict[str, object]]]:
        return {import_type: self._durable_processor(import_type) for import_type in IMPORT_JOB_PROCESSOR_TYPES}

    def _durable_processor(self, import_type: str) -> Callable[[Any], dict[str, object]]:
        def process(job: Any) -> dict[str, object]:
            processor = self._build_processors_from_durable_state().get(import_type)
            if not callable(processor):
                raise RuntimeError(f"Import processor is not registered: {import_type}")
            return processor(job)

        return process

    def _build_processors_from_durable_state(self) -> dict[str, Callable[[Any], dict[str, object]]]:
        state_store = self._state_store()
        import_fact_repository = getattr(state_store, "import_fact_repository", None)
        import_service = ImportNormalizationService.from_snapshot(
            _call_or_empty(state_store, "load_imports_snapshot"),
            id_registry=state_store,
            fact_repository=import_fact_repository,
        )
        file_import_service = FileImportService.from_snapshot(
            import_service,
            _call_or_empty(state_store, "load_file_imports_snapshot"),
            file_store=state_store,
        )
        tax_certified_import_service = TaxCertifiedImportService(state_store=state_store)
        from fin_ops_platform.services.etc_import_preview_service import EtcImportPreviewService
        from fin_ops_platform.services.etc_import_session_store import build_etc_import_session_store

        etc_import_session_store = build_etc_import_session_store(state_store)
        etc_service = EtcService(state_store=state_store, import_session_store=etc_import_session_store)
        etc_service.set_canonical_invoice_key_exists(_canonical_invoice_key_exists(import_service))
        etc_reconciliation_task_service = EtcReconciliationTaskService(state_store=state_store)
        etc_import_preview_service = EtcImportPreviewService(
            etc_service=etc_service,
            task_service=etc_reconciliation_task_service,
            session_store=etc_import_session_store,
        )
        background_job_service = BackgroundJobService(state_store)
        category_service = BankTransactionCategoryService.from_snapshot(
            state_store.load_bank_transaction_categories(),
            transaction_exists=lambda transaction_id: bool(_bank_transaction_by_id(import_service, transaction_id)),
        )
        auto_category_service = BankTransactionAutoCategoryService(category_service=category_service)
        project_costing_service = _project_costing_service(import_service)
        app_settings_service = AppSettingsService(
            state_store,
            project_costing_service,
            oa_role_sync_service=OARoleSyncService.from_environment(),
            bank_transaction_category_service=category_service,
            bank_transaction_auto_category_service=auto_category_service,
            audit_service=AuditTrailService(),
        )
        lifecycle = _RuntimeWorkerDerivedLifecycle(
            queue_repository=self._queue_repository,
            state_store=state_store,
            search_service=_runtime_search_service(import_service),
            workbench_source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
        )
        persist_confirmed_import_delta = _persist_confirmed_import_delta_callback(
            lifecycle=lifecycle,
        )
        processing_service = ImportProcessingService(
            file_import_service=file_import_service,
            tax_certified_import_service=tax_certified_import_service,
            etc_service=etc_service,
            etc_reconciliation_task_service=etc_reconciliation_task_service,
            background_job_service=background_job_service,
            serialize_value=_serialize_value,
            execute_derived_data_lifecycle_event=lifecycle.execute_event,
            schedule_or_run_workbench_auto_matching_for_scopes=lifecycle.schedule_workbench_matching,
            enqueue_workbench_auto_matching_for_scopes=lifecycle.enqueue_workbench_matching_job,
            persist_confirmed_import_delta=persist_confirmed_import_delta,
            invalidate_tax_offset_read_model_scopes=lifecycle.invalidate_tax_offset_scopes,
            workbench_matching_scope_months_for_import_file_session=_workbench_matching_scope_months_for_import_file_session,
            tax_offset_scope_keys_for_import_file_session=_tax_offset_scope_keys_for_import_file_session,
            cost_statistics_scope_keys_for_import_file_session=_cost_statistics_scope_keys_for_import_file_session,
            bank_detail_scope_keys_for_import_file_session=_bank_detail_scope_keys_for_import_file_session,
            input_invoice_usage_scope_keys_for_import_file_session=_input_invoice_usage_scope_keys_for_import_file_session,
            output_invoice_collection_scope_keys_for_import_file_session=_output_invoice_collection_scope_keys_for_import_file_session,
            link_etc_import_result_to_existing_invoices=_link_etc_import_result_to_existing_invoices(
                import_service,
                etc_service,
                state_store,
            ),
            refresh_after_etc_invoice_link=lifecycle.refresh_after_etc_invoice_link,
            etc_import_preview_service=etc_import_preview_service,
            oa_manual_import_create_processor=_oa_manual_import_create_processor(state_store=state_store),
        )
        return processing_service.build_import_job_processors()

    def _state_store(self) -> Any:
        from fin_ops_platform.services.object_storage import ObjectStorageSettings, S3ObjectStorageRepository
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore

        object_storage_settings = ObjectStorageSettings.from_env()
        object_storage_repository = (
            S3ObjectStorageRepository(object_storage_settings) if object_storage_settings.enabled else None
        )
        kwargs = {
            "data_dir": self._data_dir,
            "connection": self._connection,
        }
        if object_storage_repository is not None:
            kwargs["object_storage_repository"] = object_storage_repository
        return PostgresStateStore(**kwargs)


class WorkbenchMatchingWorkerFactory:
    def __init__(self, *, data_dir: str | Path, connection: Any) -> None:
        self._data_dir = data_dir
        self._connection = connection

    def build_dirty_scope_worker(
        self,
        *,
        heartbeat_recorder: Any,
        worker_id: str,
        poll_interval_seconds: float,
        batch_size: int,
        lease_seconds: int,
        retry_delay_seconds: int | None,
        max_iterations: int | None,
    ) -> WorkbenchMatchingDirtyScopeWorker:
        state_store = self._state_store()
        read_model_repository = getattr(state_store, "read_model_repository", None)
        app_settings_service = _app_settings_service(state_store)
        queue_repository = RuntimeQueueRepository(self._connection)
        relation_uow = WorkbenchWriteUnitOfWork(
            connection=self._connection,
            repository_factory=self._workbench_uow_repository_factory,
            read_model_refresh_writer=RuntimeQueueReadModelRefreshWriter(
                queue_repository,
                tenant_id="default",
                priority="high",
            ),
            idempotency_store=PostgresWorkbenchIdempotencyRepository(self._connection),
        )
        return build_workbench_matching_dirty_scope_worker(
            dirty_queue=WorkbenchReconciliationDirtyQueue(repository=read_model_repository),
            matching_orchestrator=WorkbenchMatchingOrchestrator(
                fact_repository=PostgresWorkbenchFormalRelationFactRepository(self._connection),
                matcher=WorkbenchFreeMatchingEngine(),
                relation_uow=relation_uow,
                source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
            ),
            source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
            heartbeat_recorder=heartbeat_recorder,
            worker_id=worker_id,
            poll_interval_seconds=poll_interval_seconds,
            batch_size=batch_size,
            lease_seconds=lease_seconds,
            retry_delay_seconds=retry_delay_seconds,
            max_iterations=max_iterations,
        )

    def _state_store(self) -> Any:
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore

        return PostgresStateStore(data_dir=self._data_dir, connection=self._connection)

    @staticmethod
    def _workbench_uow_repository_factory(transaction: Any) -> SimpleNamespace:
        workbench_repository = PostgresWorkbenchRepository(transaction)
        return SimpleNamespace(
            pair_relations=PostgresWorkbenchRelationRepository(transaction, enqueue_refreshes=False),
            exception_cases=workbench_repository,
            row_overrides=workbench_repository,
        )


def build_import_job_handler_bundle(
    *,
    connection: Any,
    worker_id: str,
    processors: dict[str, Callable[[Any], dict[str, object]]],
    include_import_fact_changed: bool,
    queue_repository: Any | None = None,
) -> RuntimeWorkerHandlerBundle:
    import_job_repository = ImportJobRepository(connection)
    import_job_worker = ImportJobWorker(
        repository=import_job_repository,
        worker_id=worker_id,
        processors=processors,
    )
    handlers: dict[str, Callable[[Any], dict[str, Any]]] = {
        IMPORT_PROCESS_REQUESTED_EVENT: import_job_worker.handle_runtime_event,
    }
    if include_import_fact_changed:
        handlers[IMPORT_FACT_CHANGED_EVENT] = lambda event: handle_import_fact_changed_event(
            event,
            queue_repository=queue_repository,
        )
    return RuntimeWorkerHandlerBundle(handlers=handlers)


class _RuntimeWorkerDerivedLifecycle:
    def __init__(
        self,
        *,
        queue_repository: Any | None,
        state_store: Any,
        search_service: SearchService,
        workbench_source_versions_provider: Callable[[], dict[str, object]],
        search_read_model_refresh_producer: Any | None = None,
        bank_account_balance_read_model_refresh_producer: Any | None = None,
    ) -> None:
        self._queue_repository = queue_repository
        self._state_store = state_store
        self._search_service = search_service
        self._lifecycle = DerivedDataLifecycleService()
        self._read_model_refresh_gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        self._search_read_model_refresh_producer = (
            search_read_model_refresh_producer
            or SearchReadModelRefreshProducer(refresh_gateway_provider=lambda: self._read_model_refresh_gateway)
        )
        self._bank_account_balance_read_model_refresh_producer = (
            bank_account_balance_read_model_refresh_producer
            or BankAccountBalanceReadModelRefreshProducer(refresh_gateway_provider=lambda: self._read_model_refresh_gateway)
        )
        self._workbench_source_versions_provider = workbench_source_versions_provider

    def execute_event(
        self,
        event: str,
        *,
        months: list[str] | None = None,
        scope_keys: list[str] | None = None,
        include_all: bool = True,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        plan = self._lifecycle.plan_event(
            event,
            months=months,
            scope_keys=scope_keys,
            include_all=include_all,
            dry_run=False,
            metadata=metadata,
        )
        reason = str((metadata or {}).get("reason") or event).strip()
        return self._lifecycle.execute_plan(
            plan,
            executors=self._executors_for_reason(reason),
        )

    def schedule_workbench_matching(self, scope_months: list[str], *, reason: str, **_kwargs: object) -> dict[str, object]:
        return {
            "queued_months": self._mark_workbench_matching_months(scope_months, reason=reason),
            "processed_months": [],
            "planned_relation_count": 0,
            "reason": reason,
        }

    def enqueue_workbench_matching_job(
        self,
        scope_months: list[str],
        *,
        reason: str,
        owner_user_id: str,
        source: dict[str, object] | None = None,
        triggered_by: str | None = None,
    ) -> Any | None:
        months = self._mark_workbench_matching_months(scope_months, reason=reason)
        if not months:
            return None
        create_job = getattr(BackgroundJobService(self._state_store), "create_job", None)
        if not callable(create_job):
            return None
        return create_job(
            job_type="workbench_matching",
            label="生成正式配对关系",
            owner_user_id=owner_user_id,
            phase="queued",
            current=0,
            total=len(months),
            message="生成正式配对关系任务已创建。",
            result_summary={"processed_months": [], "affected_months": months, "planned_relation_count": 0},
            source={**(source or {}), "reason": reason, "scope_months": months, "triggered_by": triggered_by},
            affected_scopes=["workbench"],
            affected_months=months,
        )

    def invalidate_tax_offset_scopes(self, scope_keys: list[str], *, reason: str) -> list[str]:
        return self._enqueue_scopes("tax_offset", scope_keys, reason=reason)

    def refresh_after_etc_invoice_link(self, changed_months: list[str], *, reason: str) -> None:
        months = [month for month in _dedupe_text(changed_months) if SEARCH_MONTH_RE.match(month)]
        if not months:
            return
        self.execute_event(
            "etc_import_confirmed",
            months=months,
            metadata={"source": "etc_invoice_link", "reason": reason},
        )
        self.schedule_workbench_matching(months, reason=reason)

    def persist_confirmed_import_delta(
        self,
        *,
        import_state_payload: dict[str, Any],
        cost_statistics_scope_keys: list[str] | None = None,
        bank_detail_scope_keys: list[str] | None = None,
        input_invoice_usage_scope_keys: list[str] | None = None,
        output_invoice_collection_scope_keys: list[str] | None = None,
        invalidate_cost_statistics: bool = True,
    ) -> None:
        payload = dict(import_state_payload or {})
        if not payload or set(payload) - {"imports", "file_imports"}:
            raise ValueError("File import persistence requires only imports and file_imports payloads.")
        persist = getattr(self._state_store, "save_import_delta", None)
        if not callable(persist):
            raise RuntimeError("File import confirmation requires the import delta persistence port.")
        persist(payload)
        self._execute_import_state_changed(
            cost_statistics_scope_keys=cost_statistics_scope_keys,
            bank_detail_scope_keys=bank_detail_scope_keys,
            input_invoice_usage_scope_keys=input_invoice_usage_scope_keys,
            output_invoice_collection_scope_keys=output_invoice_collection_scope_keys,
            invalidate_cost_statistics=invalidate_cost_statistics,
        )

    def _executors_for_reason(self, reason: str) -> dict[str, Callable[[dict[str, object]], dict[str, object] | None]]:
        return {
            "workbench_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "workbench", reason),
            "workbench_relation_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "workbench_relation", reason),
            "workbench_matching_dirty_scopes": lambda domain_plan: self._mark_workbench_matching(domain_plan, reason),
            "invoice_lifecycle_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "invoice_lifecycle", reason),
            "cost_statistics_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "cost_statistics", reason),
            "tax_offset_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "tax_offset", reason),
            "tax_offset_month_cache": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
            "pending_invoice_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "pending_invoice", reason),
            "input_invoice_usage_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "input_invoice_usage", reason),
            "output_invoice_collection_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "output_invoice_collection", reason),
            "oa_pending_payment_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "oa_pending_payment", reason),
            "bank_account_balance_read_model": lambda domain_plan: self._enqueue_bank_account_balance_domain(domain_plan, reason),
            "bank_detail_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "bank_detail", reason),
            "no_oa_bank_batch_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "no_oa_bank_batch", reason),
            "bank_flow_rule_batch_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "bank_flow_rule_batch", reason),
            "search_cache": lambda domain_plan: self._clear_search_cache(domain_plan),
            "oa_adapter_records_cache": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
            "historical_etc_repair_state": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
        }

    def _execute_import_state_changed(
        self,
        *,
        cost_statistics_scope_keys: list[str] | None,
        bank_detail_scope_keys: list[str] | None,
        input_invoice_usage_scope_keys: list[str] | None,
        output_invoice_collection_scope_keys: list[str] | None,
        invalidate_cost_statistics: bool,
    ) -> dict[str, object]:
        reason = "import_state_changed"
        plan = self._lifecycle.plan_event(
            reason,
            scope_keys=cost_statistics_scope_keys or ["all"],
            include_all=False,
            dry_run=False,
            metadata={"source": "runtime_import_state", "reason": reason},
        )
        domain_scope_keys = self._import_state_domain_scope_keys(
            cost_statistics_scope_keys=cost_statistics_scope_keys,
            bank_detail_scope_keys=bank_detail_scope_keys,
            input_invoice_usage_scope_keys=input_invoice_usage_scope_keys,
            output_invoice_collection_scope_keys=output_invoice_collection_scope_keys,
            invalidate_cost_statistics=invalidate_cost_statistics,
        )
        plan["domains"] = self._domains_with_scope_overrides(plan, domain_scope_keys)
        executors = self._executors_for_reason(reason)
        executors["bank_detail_read_model"] = lambda domain_plan: self._enqueue_domain(
            domain_plan,
            "bank_detail",
            "import_facts_changed",
        )
        executors["search_cache"] = lambda domain_plan: self._refresh_import_search(domain_plan, reason)
        return self._lifecycle.execute_plan(plan, executors=executors)

    @staticmethod
    def _import_state_domain_scope_keys(
        *,
        cost_statistics_scope_keys: list[str] | None,
        bank_detail_scope_keys: list[str] | None,
        input_invoice_usage_scope_keys: list[str] | None,
        output_invoice_collection_scope_keys: list[str] | None,
        invalidate_cost_statistics: bool,
    ) -> dict[str, list[str]]:
        cost_scope_keys = list(cost_statistics_scope_keys or ["all"])
        bank_scope_keys = list(bank_detail_scope_keys or [])
        input_scope_keys = list(input_invoice_usage_scope_keys) if input_invoice_usage_scope_keys is not None else cost_scope_keys
        output_scope_keys = (
            list(output_invoice_collection_scope_keys)
            if output_invoice_collection_scope_keys is not None
            else cost_scope_keys
        )
        return {
            "workbench_read_model": _workbench_read_model_scope_keys_for_import_state(cost_statistics_scope_keys),
            "workbench_relation_read_model": cost_scope_keys,
            "invoice_lifecycle_read_model": cost_scope_keys,
            "pending_invoice_read_model": pending_invoice_read_model_scope_keys_for_import_state(
                cost_statistics_scope_keys,
                bank_detail_scope_keys,
            ),
            "input_invoice_usage_read_model": input_scope_keys,
            "output_invoice_collection_read_model": output_scope_keys,
            "oa_pending_payment_read_model": cost_scope_keys,
            "bank_account_balance_read_model": ["all"] if bank_scope_keys else [],
            "bank_detail_read_model": bank_scope_keys,
            "cost_statistics_read_model": cost_scope_keys if invalidate_cost_statistics else [],
            "search_cache": cost_scope_keys,
        }

    @staticmethod
    def _domains_with_scope_overrides(
        plan: dict[str, object],
        domain_scope_keys: dict[str, list[str]],
    ) -> list[dict[str, object]]:
        domains: list[dict[str, object]] = []
        for domain_plan in list(plan.get("domains") or []):
            if not isinstance(domain_plan, dict):
                continue
            domain_name = str(domain_plan.get("domain") or "").strip()
            next_plan = dict(domain_plan)
            if domain_name in domain_scope_keys:
                scope_keys = _dedupe_text(domain_scope_keys[domain_name])
                if not scope_keys:
                    continue
                next_plan["scope_keys"] = scope_keys
                next_plan["estimated_count"] = len(scope_keys)
            domains.append(next_plan)
        return domains

    def _refresh_import_search(self, domain_plan: dict[str, object], reason: str) -> dict[str, object]:
        self._search_service.clear_cache()
        scope_keys = self._scope_keys(domain_plan) or ["all"]
        enqueued = self._search_read_model_refresh_producer.enqueue(scope_keys, reason=reason)
        return {
            "deleted_counts": {"search_cache": 1},
            "invalidated_scopes": scope_keys,
            "enqueued_jobs": ["search.read_model.refresh"] if enqueued else [],
        }

    def _enqueue_bank_account_balance_domain(self, domain_plan: dict[str, object], reason: str) -> dict[str, object]:
        enqueued_scope_keys = self._bank_account_balance_read_model_refresh_producer.enqueue_scope_keys(
            self._scope_keys(domain_plan) or ["all"],
            reason=reason,
        )
        return {
            "deleted_counts": {"bank_account_balance": 0},
            "invalidated_scopes": enqueued_scope_keys,
            "enqueued_jobs": ["bank_account_balance.read_model.refresh"] if enqueued_scope_keys else [],
        }

    def _enqueue_domain(self, domain_plan: dict[str, object], scope_type: str, reason: str) -> dict[str, object]:
        scope_keys = self._scope_keys(domain_plan) or ["all"]
        return {
            "deleted_counts": {scope_type: 0},
            "invalidated_scopes": self._enqueue_scopes(scope_type, scope_keys, reason=reason),
            "enqueued_jobs": [f"{scope_type}.read_model.refresh"] if scope_keys else [],
        }

    def _enqueue_scopes(self, scope_type: str, scope_keys: list[str], *, reason: str) -> list[str]:
        return self._read_model_refresh_gateway.enqueue_many(scope_type, scope_keys, reason=reason)

    def _mark_workbench_matching(self, domain_plan: dict[str, object], reason: str) -> dict[str, object]:
        months = [scope for scope in self._scope_keys(domain_plan) if SEARCH_MONTH_RE.match(scope)]
        return {"invalidated_scopes": self._mark_workbench_matching_months(months, reason=reason)}

    def _mark_workbench_matching_months(self, scope_months: list[str], *, reason: str) -> list[str]:
        months = [month for month in _dedupe_text(scope_months) if SEARCH_MONTH_RE.match(month)]
        repository = getattr(self._state_store, "read_model_repository", None)
        dirty_queue = WorkbenchReconciliationDirtyQueue(repository=repository)
        return list(
            dirty_queue.mark_dirty_expanded(
                months,
                reason=reason,
                source_versions=self._workbench_source_versions_provider(),
            )
        )

    def _clear_search_cache(self, domain_plan: dict[str, object]) -> dict[str, object]:
        self._search_service.clear_cache()
        return {"invalidated_scopes": self._scope_keys(domain_plan)}

    @staticmethod
    def _scope_keys(domain_plan: dict[str, object]) -> list[str]:
        raw_scope_keys = domain_plan.get("scope_keys") if isinstance(domain_plan, dict) else []
        return _dedupe_text(raw_scope_keys if isinstance(raw_scope_keys, list) else [])


def _runtime_search_service(import_service: ImportNormalizationService) -> SearchService:
    return SearchService(known_months_loader=lambda: _known_import_months(import_service))


def _known_import_months(import_service: ImportNormalizationService) -> list[str]:
    months: set[str] = set()
    for transaction in import_service.list_transactions(month="all"):
        value = str(transaction.txn_date or transaction.trade_time or "").strip()[:7]
        if SEARCH_MONTH_RE.match(value):
            months.add(value)
    for invoice in import_service.list_invoices(month="all"):
        value = str(invoice.invoice_date or "").strip()[:7]
        if SEARCH_MONTH_RE.match(value):
            months.add(value)
    return sorted(months, reverse=True)


def build_workbench_matching_dirty_scope_worker(
    *,
    dirty_queue: Any,
    matching_orchestrator: Any,
    source_versions_provider: Callable[[], dict[str, object]],
    heartbeat_recorder: Any,
    worker_id: str,
    poll_interval_seconds: float,
    batch_size: int,
    lease_seconds: int,
    retry_delay_seconds: int | None,
    max_iterations: int | None,
) -> WorkbenchMatchingDirtyScopeWorker:
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


def _call_or_empty(container: Any, method_name: str) -> dict[str, Any]:
    method = getattr(container, method_name, None)
    if callable(method):
        value = method()
        return value if isinstance(value, dict) else {}
    return {}


def _serialize_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _serialize_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    return value


def _dedupe_text(values: Any) -> list[str]:
    return sorted(dict.fromkeys(str(value).strip() for value in list(values or []) if str(value).strip()))


def _bank_transaction_by_id(import_service: Any, transaction_id: str) -> Any | None:
    normalized = str(transaction_id or "").strip()
    if not normalized:
        return None
    for transaction in import_service.list_transactions():
        if str(getattr(transaction, "id", "") or "").strip() == normalized:
            return transaction
    return None


def _canonical_invoice_key_exists(import_service: Any) -> Callable[[str], bool]:
    def exists(canonical_key: str) -> bool:
        normalized = str(canonical_key or "").strip()
        if not normalized:
            return False
        exists_method = getattr(import_service, "canonical_invoice_key_exists", None)
        if callable(exists_method):
            return bool(exists_method(normalized))
        return False

    return exists


def _project_costing_service(import_service: Any) -> ProjectCostingService:
    audit_service = AuditTrailService()
    matching_service = MatchingEngineService.from_snapshot(import_service, {})
    reconciliation_service = ManualReconciliationService(import_service, matching_service, audit_service)
    ledger_service = LedgerReminderService(import_service, audit_service)
    integration_service = IntegrationHubService(import_service, audit_service)
    return ProjectCostingService(import_service, reconciliation_service, ledger_service, integration_service, audit_service)


def _app_settings_service(state_store: Any) -> AppSettingsService:
    import_service = ImportNormalizationService.from_snapshot(
        _call_or_empty(state_store, "load_imports_snapshot"),
        id_registry=state_store,
        fact_repository=getattr(state_store, "import_fact_repository", None),
    )
    category_service = BankTransactionCategoryService.from_snapshot(state_store.load_bank_transaction_categories())
    auto_category_service = BankTransactionAutoCategoryService(category_service=category_service)
    return AppSettingsService(
        state_store,
        _project_costing_service(import_service),
        oa_role_sync_service=OARoleSyncService.from_environment(),
        bank_transaction_category_service=category_service,
        bank_transaction_auto_category_service=auto_category_service,
        audit_service=AuditTrailService(),
    )


def _workbench_matching_source_versions(app_settings_service: AppSettingsService) -> dict[str, object]:
    payload: dict[str, object] = {
        "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
        "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
        "workbench_exception_rules_version": WORKBENCH_EXCEPTION_RULE_VERSION,
        "workbench_exception_projection_version": EXCEPTION_PROJECTION_VERSION,
        "bank_auto_tag_rules_version": _current_bank_auto_tag_rules_version(app_settings_service),
    }
    parser_version = attachment_invoice_cache_parser_version()
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


def _persist_confirmed_import_delta_callback(
    *,
    lifecycle: _RuntimeWorkerDerivedLifecycle,
) -> Callable[..., None]:
    return lambda **kwargs: lifecycle.persist_confirmed_import_delta(**kwargs)


def _link_etc_import_result_to_existing_invoices(
    import_service: Any,
    etc_service: Any,
    state_store: Any,
) -> Callable[[Any], list[str]]:
    persist = getattr(state_store, "save_invoice_etc_metadata", None)
    if not callable(persist):
        raise RuntimeError("ETC import processing requires the canonical invoice metadata persistence port.")
    link_service = EtcExistingInvoiceLinkService(
        import_service=import_service,
        etc_service=etc_service,
        persist_linked_invoices=persist,
    )

    def link(result: Any) -> list[str]:
        return link_service.link_import_result_to_existing_invoices(result)

    return link


def _oa_manual_import_create_processor(*, state_store: Any) -> Callable[[Any], dict[str, object]]:
    def process(import_job: Any) -> dict[str, object]:
        row_ids = import_job.payload.get("row_ids")
        if not isinstance(row_ids, list):
            raise ValueError("import job payload.row_ids is required.")
        actor_id = str(import_job.payload.get("actor_id") or import_job.created_by or "workbench_settings").strip()
        add_manual_oa_imports = getattr(state_store, "add_manual_oa_imports", None)
        if not callable(add_manual_oa_imports):
            raise RuntimeError("state_store must expose add_manual_oa_imports for OA manual import jobs.")
        return add_manual_oa_imports([str(row_id) for row_id in row_ids], actor_id=actor_id)

    return process


def _workbench_matching_scope_months_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    selected = {str(file_id) for file_id in list(selected_file_ids or [])}
    rows: list[Any] = []
    for file in list(getattr(session, "files", []) or []):
        if str(getattr(file, "id", "") or "") in selected:
            rows.extend(list(getattr(file, "normalized_rows", []) or []))
    return _workbench_matching_scope_months_for_import_rows(rows)


def _workbench_matching_scope_months_for_import_rows(rows: Any) -> list[str]:
    months: set[str] = set()
    for row in list(rows or []):
        payload = row if isinstance(row, dict) else getattr(row, "__dict__", {})
        for key in ("trade_time", "trade_date", "pay_receive_time", "invoice_date"):
            value = str(payload.get(key) or "").strip()
            if SEARCH_MONTH_RE.match(value[:7]):
                months.add(value[:7])
    return sorted(months)


def _tax_offset_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    selected = {str(file_id) for file_id in list(selected_file_ids or [])}
    rows: list[Any] = []
    for file in list(getattr(session, "files", []) or []):
        if str(getattr(file, "id", "") or "") not in selected:
            continue
        if str(getattr(file, "status", "") or "") != "confirmed":
            continue
        if _normalized_batch_type(getattr(file, "batch_type", None)) not in {
            BatchType.INPUT_INVOICE,
            BatchType.OUTPUT_INVOICE,
        }:
            continue
        rows.extend(list(getattr(file, "normalized_rows", []) or []))
    return _tax_offset_scope_keys_for_import_rows(rows)


def _tax_offset_scope_keys_for_import_rows(rows: Any) -> list[str]:
    return _workbench_matching_scope_months_for_import_rows(rows)


def _cost_statistics_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    return _workbench_matching_scope_months_for_import_file_session(session, selected_file_ids)


def _cost_statistics_scope_keys_for_import_rows(rows: Any) -> list[str]:
    months = _workbench_matching_scope_months_for_import_rows(rows)
    return months or ["all"]


def _bank_detail_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    selected = {str(file_id) for file_id in list(selected_file_ids or [])}
    rows: list[Any] = []
    for file in list(getattr(session, "files", []) or []):
        if str(getattr(file, "id", "") or "") in selected:
            rows.extend(list(getattr(file, "normalized_rows", []) or []))
    return _bank_detail_scope_keys_for_import_rows(rows)


def _bank_detail_scope_keys_for_import_rows(rows: Any) -> list[str]:
    months: set[str] = set()
    for row in list(rows or []):
        payload = row if isinstance(row, dict) else getattr(row, "__dict__", {})
        if not any(str(payload.get(key) or "").strip() for key in ("account_no", "bank_serial_no", "txn_direction")):
            continue
        for key in ("txn_date", "trade_time", "trade_date", "pay_receive_time"):
            value = str(payload.get(key) or "").strip()
            if SEARCH_MONTH_RE.match(value[:7]):
                months.add(value[:7])
    return sorted(months)


def _input_invoice_usage_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    return _invoice_relation_scope_keys_for_import_file_session(session, selected_file_ids, BatchType.INPUT_INVOICE)


def _output_invoice_collection_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    return _invoice_relation_scope_keys_for_import_file_session(session, selected_file_ids, BatchType.OUTPUT_INVOICE)


def _invoice_relation_scope_keys_for_import_file_session(
    session: Any,
    selected_file_ids: list[str],
    batch_type: BatchType,
) -> list[str]:
    selected = {str(file_id) for file_id in list(selected_file_ids or [])}
    rows: list[Any] = []
    for file in list(getattr(session, "files", []) or []):
        if str(getattr(file, "id", "") or "") not in selected:
            continue
        if str(getattr(file, "status", "") or "") != "confirmed":
            continue
        if _normalized_batch_type(getattr(file, "batch_type", None)) != batch_type:
            continue
        rows.extend(list(getattr(file, "normalized_rows", []) or []))
    return _cost_statistics_scope_keys_for_import_rows(rows) if rows else []


def _normalized_batch_type(value: Any) -> BatchType | None:
    if isinstance(value, BatchType):
        return value
    try:
        return BatchType(str(value or "").strip())
    except ValueError:
        return None


def _workbench_read_model_scope_keys_for_import_state(scope_keys: list[str] | None) -> list[str]:
    month_scope_keys = [scope_key for scope_key in _dedupe_text(scope_keys or []) if SEARCH_MONTH_RE.match(scope_key)]
    return month_scope_keys or ["all"]


class _WorkbenchSqlMatchingRowProvider:
    def __init__(self, *, connection: Any) -> None:
        self._builder = WorkbenchSqlProjectionBuilder(connection=connection)

    def rows_for_scope(self, scope_month: str) -> dict[str, list[dict[str, object]]]:
        month = str(scope_month or "").strip()
        return {
            "oa_rows": list(self._builder._oa_projection_rows(month)),
            "bank_rows": list(self._builder._bank_rows(month)),
            "invoice_rows": list(self._builder._invoice_rows(month)),
        }


def handle_import_fact_changed_event(event: Any, *, queue_repository: Any | None = None) -> dict[str, Any]:
    scope_type = str(getattr(event, "scope_type", None) or event.payload.get("scope_type") or "").strip()
    scope_key = str(getattr(event, "scope_key", None) or event.payload.get("scope_key") or "").strip()
    refresh_enqueued = False
    if scope_type == "bank_detail" and scope_key:
        gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        refresh_enqueued = bool(gateway.enqueue_one("bank_detail", scope_key, reason="import_facts_changed"))
    dirty_scope_completed = False
    complete = getattr(queue_repository, "complete_read_model_refresh", None)
    if callable(complete) and scope_type and scope_key:
        source_version = getattr(event, "source_version", None) or event.payload.get("source_version") or 0
        complete(
            tenant_id=str(getattr(event, "tenant_id", None) or "default"),
            scope_type=scope_type,
            scope_key=scope_key,
            source_version=source_version,
        )
        dirty_scope_completed = True
    return {
        "status": "acknowledged",
        "event_type": IMPORT_FACT_CHANGED_EVENT,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "refresh_enqueued": refresh_enqueued,
        "dirty_scope_completed": dirty_scope_completed,
        "note": "import fact dirty scopes are persisted by the import fact writer",
    }


def check_import_job_processors() -> dict[str, Callable[[Any], dict[str, object]]]:
    return {
        "file_import.confirm": _check_processor,
        "etc_invoice_import.confirm": _check_processor,
        "tax_certified_import.confirm": _check_processor,
        "oa_manual_import.create": _check_processor,
    }


def _check_processor(_job: Any) -> dict[str, object]:
    return {"status": "check"}
