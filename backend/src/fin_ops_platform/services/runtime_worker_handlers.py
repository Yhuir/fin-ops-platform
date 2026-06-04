from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import re
from pathlib import Path
from typing import Any, Callable

from fin_ops_platform.services.app_settings_service import (
    AppSettingsService,
    DEFAULT_OA_IMPORT_FORM_TYPES,
    DEFAULT_OA_IMPORT_STATUSES,
    DEFAULT_OA_RETENTION_CUTOFF_DATE,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.derived_data_lifecycle_service import DerivedDataLifecycleService
from fin_ops_platform.services.etc_business_batch_application_service import ETC_BUSINESS_OA_DETECTION_EVENT_TYPE
from fin_ops_platform.services.etc_business_batch_application_service import EtcBusinessBatchApplicationService
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_service import EtcService
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.import_job_queue import IMPORT_PROCESS_REQUESTED_EVENT, ImportJobRepository, ImportJobWorker
from fin_ops_platform.services.import_processing_service import ImportProcessingService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.reconciliation import ManualReconciliationService
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.search_service import SearchService
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService
from fin_ops_platform.services.workbench_candidate_match_service import (
    CANDIDATE_MATCH_SCHEMA_VERSION,
    WorkbenchCandidateMatchService,
)
from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_exception_rules import RULE_VERSION as WORKBENCH_EXCEPTION_RULE_VERSION
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION, WorkbenchMatchingRules
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import WorkbenchReconciliationDirtyQueue
from fin_ops_platform.services.workbench_special_pair_rule_service import WorkbenchSpecialPairRuleService
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION, WorkbenchSqlProjectionBuilder


IMPORT_FACT_CHANGED_EVENT = "import.fact.changed"
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
        etc_service = EtcService(state_store=state_store)
        etc_service.set_canonical_invoice_key_exists(_canonical_invoice_key_exists(import_service))
        etc_reconciliation_task_service = EtcReconciliationTaskService(state_store=state_store)
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
        persist_import_state = _persist_import_state_callback(
            lifecycle=lifecycle,
            state_store=state_store,
            import_service=import_service,
            file_import_service=file_import_service,
            etc_service=etc_service,
            etc_reconciliation_task_service=etc_reconciliation_task_service,
            tax_certified_import_service=tax_certified_import_service,
        )
        processing_service = ImportProcessingService(
            import_service=import_service,
            file_import_service=file_import_service,
            tax_certified_import_service=tax_certified_import_service,
            etc_service=etc_service,
            etc_reconciliation_task_service=etc_reconciliation_task_service,
            background_job_service=background_job_service,
            serialize_value=_serialize_value,
            execute_derived_data_lifecycle_event=lifecycle.execute_event,
            schedule_or_run_workbench_auto_matching_for_scopes=lifecycle.schedule_workbench_matching,
            enqueue_workbench_auto_matching_for_scopes=lifecycle.enqueue_workbench_matching_job,
            persist_state_with_workbench_invalidation=persist_import_state,
            invalidate_tax_offset_read_model_scopes=lifecycle.invalidate_tax_offset_scopes,
            workbench_matching_scope_months_for_import_preview=_workbench_matching_scope_months_for_import_preview,
            workbench_matching_scope_months_for_import_file_session=_workbench_matching_scope_months_for_import_file_session,
            tax_offset_scope_keys_for_import_preview=_tax_offset_scope_keys_for_import_preview,
            tax_offset_scope_keys_for_import_file_session=_tax_offset_scope_keys_for_import_file_session,
            cost_statistics_scope_keys_for_import_preview=_cost_statistics_scope_keys_for_import_preview,
            cost_statistics_scope_keys_for_import_file_session=_cost_statistics_scope_keys_for_import_file_session,
            sync_etc_import_result_to_canonical_invoices=_sync_etc_import_result_to_canonical_invoices(import_service),
            refresh_after_etc_invoice_sync=lifecycle.refresh_after_etc_invoice_sync,
            oa_manual_import_create_processor=_oa_manual_import_create_processor(state_store=state_store),
        )
        return processing_service.build_import_job_processors()

    def _state_store(self) -> Any:
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore

        return PostgresStateStore(data_dir=self._data_dir, connection=self._connection)


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
        pair_relation_service = WorkbenchPairRelationService.from_snapshot(state_store.load_workbench_pair_relations())
        app_settings_service = _app_settings_service(state_store)
        row_provider = _WorkbenchSqlMatchingRowProvider(connection=self._connection)
        return build_workbench_matching_dirty_scope_worker(
            dirty_queue=WorkbenchReconciliationDirtyQueue(repository=read_model_repository),
            matching_orchestrator=WorkbenchMatchingOrchestrator(
                row_provider=row_provider.rows_for_scope,
                pair_relation_service=pair_relation_service,
                candidate_match_service=WorkbenchCandidateMatchService.from_snapshot(state_store.load_workbench_candidate_matches()),
                read_model_service=WorkbenchReadModelService.from_snapshot({}),
                rules=WorkbenchMatchingRules(include_special_rules=False),
                special_rule_service=WorkbenchSpecialPairRuleService(),
                exception_case_service=WorkbenchExceptionCaseService.from_snapshot(state_store.load_workbench_exception_cases()),
                decision_store=WorkbenchReconciliationDecisionStore(repository=read_model_repository),
                settings_provider=lambda: _workbench_matching_settings(app_settings_service),
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


class EtcBusinessOaDetectionWorkerFactory:
    def __init__(self, *, data_dir: str | Path, connection: Any, queue_repository: Any | None = None) -> None:
        self._data_dir = data_dir
        self._connection = connection
        self._queue_repository = queue_repository

    def build_service(self) -> EtcBusinessBatchApplicationService:
        state_store = self._state_store()
        import_service = ImportNormalizationService.from_snapshot(
            _call_or_empty(state_store, "load_imports_snapshot"),
            id_registry=state_store,
            fact_repository=getattr(state_store, "import_fact_repository", None),
        )
        etc_service = EtcService(state_store=state_store)
        etc_service.set_canonical_invoice_key_exists(_canonical_invoice_key_exists(import_service))
        app_settings_service = _app_settings_service(state_store)
        lifecycle = _RuntimeWorkerDerivedLifecycle(
            queue_repository=self._queue_repository,
            state_store=state_store,
            search_service=_runtime_search_service(import_service),
            workbench_source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
        )
        return EtcBusinessBatchApplicationService(
            etc_service=etc_service,
            reconciliation_task_service=EtcReconciliationTaskService(state_store=state_store),
            queue_repository=self._queue_repository,
            oa_client_factory=_unsupported_etc_oa_client_factory,
            oa_adapter_provider=lambda: None,
            sync_etc_invoices_to_canonical_invoices=_sync_etc_invoices_to_canonical_invoices(import_service),
            refresh_after_etc_invoice_sync=lifecycle.refresh_after_etc_invoice_sync,
        )

    def _state_store(self) -> Any:
        from fin_ops_platform.services.postgres_state_store import PostgresStateStore

        return PostgresStateStore(data_dir=self._data_dir, connection=self._connection)


def build_import_job_handler_bundle(
    *,
    connection: Any,
    worker_id: str,
    processors: dict[str, Callable[[Any], dict[str, object]]],
    include_import_fact_changed: bool,
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
        handlers[IMPORT_FACT_CHANGED_EVENT] = handle_import_fact_changed_event
    return RuntimeWorkerHandlerBundle(handlers=handlers)


class _RuntimeWorkerDerivedLifecycle:
    def __init__(
        self,
        *,
        queue_repository: Any | None,
        state_store: Any,
        search_service: SearchService,
        workbench_source_versions_provider: Callable[[], dict[str, object]],
    ) -> None:
        self._queue_repository = queue_repository
        self._state_store = state_store
        self._search_service = search_service
        self._lifecycle = DerivedDataLifecycleService()
        self._workbench_source_versions_provider = workbench_source_versions_provider

    def execute_event(
        self,
        event: str,
        *,
        months: list[str] | None = None,
        scope_keys: list[str] | None = None,
        include_all: bool = True,
        metadata: dict[str, object] | None = None,
        schedule_cost_warmup: bool = True,
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
            executors={
                "workbench_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "workbench", reason),
                "workbench_relation_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "workbench_relation", reason),
                "workbench_candidate_matches": lambda domain_plan: self._mark_workbench_matching(domain_plan, reason),
                "workbench_matching_dirty_scopes": lambda domain_plan: self._mark_workbench_matching(domain_plan, reason),
                "invoice_lifecycle_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "invoice_lifecycle", reason),
                "cost_statistics_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "cost_statistics", reason),
                "tax_offset_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "tax_offset", reason),
                "tax_offset_month_cache": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
                "pending_invoice_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "pending_invoice", reason),
                "bank_account_balance_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "bank_account_balance", reason),
                "bank_detail_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "bank_detail", reason),
                "no_oa_bank_batch_read_model": lambda domain_plan: self._enqueue_domain(domain_plan, "no_oa_bank_batch", reason),
                "search_cache": lambda domain_plan: self._clear_search_cache(domain_plan),
                "oa_adapter_records_cache": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
                "historical_etc_repair_state": lambda domain_plan: {"invalidated_scopes": self._scope_keys(domain_plan)},
            },
        )

    def schedule_workbench_matching(self, scope_months: list[str], *, reason: str, **_kwargs: object) -> dict[str, object]:
        return {
            "queued_months": self._mark_workbench_matching_months(scope_months, reason=reason),
            "processed_months": [],
            "candidate_count": 0,
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
            label="生成关联台候选",
            owner_user_id=owner_user_id,
            phase="queued",
            current=0,
            total=len(months),
            message="生成关联台候选任务已创建。",
            result_summary={"processed_months": [], "affected_months": months, "candidate_count": 0},
            source={**(source or {}), "reason": reason, "scope_months": months, "triggered_by": triggered_by},
            affected_scopes=["workbench"],
            affected_months=months,
        )

    def invalidate_tax_offset_scopes(self, scope_keys: list[str], *, reason: str) -> list[str]:
        return self._enqueue_scopes("tax_offset", scope_keys, reason=reason)

    def refresh_after_etc_invoice_sync(self, changed_months: list[str], *, reason: str) -> None:
        months = [month for month in _dedupe_text(changed_months) if SEARCH_MONTH_RE.match(month)]
        if not months:
            return
        self.execute_event(
            "etc_import_confirmed",
            months=months,
            metadata={"source": "etc_invoice_sync", "reason": reason},
        )
        self.schedule_workbench_matching(months, reason=reason)

    def persist_import_state(
        self,
        *,
        import_service: Any,
        file_import_service: Any,
        etc_service: Any,
        etc_reconciliation_task_service: Any,
        tax_certified_import_service: Any,
        cost_statistics_scope_keys: list[str] | None = None,
        invalidate_cost_statistics: bool = True,
    ) -> None:
        self._search_service.clear_cache()
        payload = {
            "imports": import_service.snapshot(),
            "file_imports": file_import_service.snapshot(),
        }
        save = getattr(self._state_store, "save", None)
        if callable(save):
            save(payload)
        save_etc_state = getattr(self._state_store, "save_etc_state", None)
        if callable(save_etc_state):
            save_etc_state(
                {
                    **etc_service.snapshot(),
                    "reconciliation_tasks": etc_reconciliation_task_service.snapshot(),
                }
            )
        save_tax_certified_imports = getattr(self._state_store, "save_tax_certified_imports", None)
        if callable(save_tax_certified_imports):
            save_tax_certified_imports(tax_certified_import_service.snapshot())
        self._enqueue_scopes("workbench", ["all"], reason="import_state_changed")
        self._enqueue_scopes("workbench_relation", cost_statistics_scope_keys or ["all"], reason="import_state_changed")
        self._enqueue_scopes("invoice_lifecycle", cost_statistics_scope_keys or ["all"], reason="import_state_changed")
        self._enqueue_scopes("search", cost_statistics_scope_keys or ["all"], reason="import_state_changed")
        self._enqueue_scopes("pending_invoice", ["expense:all", "income:all", "income:cash_income"], reason="import_state_changed")
        self._enqueue_scopes(
            "input_invoice_usage",
            cost_statistics_scope_keys or ["all"],
            reason="import_state_changed",
        )
        self._enqueue_scopes(
            "output_invoice_collection",
            cost_statistics_scope_keys or ["all"],
            reason="import_state_changed",
        )
        self._enqueue_scopes("oa_pending_payment", cost_statistics_scope_keys or ["all"], reason="import_state_changed")
        if invalidate_cost_statistics:
            self._enqueue_scopes("cost_statistics", cost_statistics_scope_keys or ["all"], reason="import_state_changed")

    def _enqueue_domain(self, domain_plan: dict[str, object], scope_type: str, reason: str) -> dict[str, object]:
        scope_keys = self._scope_keys(domain_plan) or ["all"]
        return {
            "deleted_counts": {scope_type: 0},
            "invalidated_scopes": self._enqueue_scopes(scope_type, scope_keys, reason=reason),
            "enqueued_jobs": [f"{scope_type}.read_model.refresh"] if scope_keys else [],
        }

    def _enqueue_scopes(self, scope_type: str, scope_keys: list[str], *, reason: str) -> list[str]:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        enqueued: list[str] = []
        for scope_key in _dedupe_text(scope_keys):
            if callable(enqueue):
                enqueue(scope_type=scope_type, scope_key=scope_key, reason=reason)
            enqueued.append(scope_key)
        return enqueued

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


def build_etc_business_oa_detection_handler(service: Any) -> Callable[[Any], dict[str, Any]]:
    return lambda event: handle_etc_business_oa_detection_event(service, event)


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


def required_worker_dependency(container: Any, attr_name: str) -> Any:
    dependency = getattr(container, attr_name, None)
    if dependency is None:
        raise RuntimeError(f"Worker handler bootstrap requires dependency {attr_name}.")
    return dependency


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


def _workbench_matching_settings(app_settings_service: AppSettingsService) -> dict[str, object]:
    return {"offset_applicant_names": app_settings_service.get_oa_invoice_offset_applicant_names()}


def _workbench_matching_source_versions(app_settings_service: AppSettingsService) -> dict[str, object]:
    payload: dict[str, object] = {
        "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
        "workbench_candidate_match_schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
        "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
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


def _persist_import_state_callback(
    *,
    lifecycle: _RuntimeWorkerDerivedLifecycle,
    state_store: Any,
    import_service: Any,
    file_import_service: Any,
    etc_service: Any,
    etc_reconciliation_task_service: Any,
    tax_certified_import_service: Any,
) -> Callable[..., None]:
    return lambda **kwargs: lifecycle.persist_import_state(
        import_service=import_service,
        file_import_service=file_import_service,
        etc_service=etc_service,
        etc_reconciliation_task_service=etc_reconciliation_task_service,
        tax_certified_import_service=tax_certified_import_service,
        **kwargs,
    )


def _sync_etc_import_result_to_canonical_invoices(import_service: Any) -> Callable[[Any], list[str]]:
    def sync(result: Any) -> list[str]:
        changed_months: set[str] = set()
        for etc_invoice in list(getattr(result, "invoices", None) or getattr(result, "imported_invoices", None) or []):
            invoice = import_service.upsert_etc_invoice(etc_invoice)
            for date_value in (
                getattr(invoice, "invoice_date", None),
                getattr(etc_invoice, "issue_date", None),
                getattr(etc_invoice, "passage_start_date", None),
                getattr(etc_invoice, "passage_end_date", None),
            ):
                if isinstance(date_value, str) and SEARCH_MONTH_RE.match(date_value[:7]):
                    changed_months.add(date_value[:7])
        return sorted(changed_months)

    return sync


def _sync_etc_invoices_to_canonical_invoices(import_service: Any) -> Callable[[list[Any]], list[str]]:
    def sync(etc_invoices: list[Any]) -> list[str]:
        changed_months: set[str] = set()
        for etc_invoice in list(etc_invoices or []):
            invoice = import_service.upsert_etc_invoice(etc_invoice)
            for date_value in (
                getattr(invoice, "invoice_date", None),
                getattr(etc_invoice, "issue_date", None),
                getattr(etc_invoice, "passage_start_date", None),
                getattr(etc_invoice, "passage_end_date", None),
            ):
                if isinstance(date_value, str) and SEARCH_MONTH_RE.match(date_value[:7]):
                    changed_months.add(date_value[:7])
        return sorted(changed_months)

    return sync


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


def _unsupported_etc_oa_client_factory(*_args: Any, **_kwargs: Any) -> Any:
    raise RuntimeError("ETC OA draft HTTP client is not available in the OA detection worker.")


def _workbench_matching_scope_months_for_import_preview(preview: Any) -> list[str]:
    return _workbench_matching_scope_months_for_import_rows(getattr(preview, "normalized_rows", []))


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


def _tax_offset_scope_keys_for_import_preview(preview: Any) -> list[str]:
    return _tax_offset_scope_keys_for_import_rows(getattr(preview, "normalized_rows", []))


def _tax_offset_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    return _workbench_matching_scope_months_for_import_file_session(session, selected_file_ids)


def _tax_offset_scope_keys_for_import_rows(rows: Any) -> list[str]:
    return _workbench_matching_scope_months_for_import_rows(rows)


def _cost_statistics_scope_keys_for_import_preview(preview: Any) -> list[str]:
    return _cost_statistics_scope_keys_for_import_rows(getattr(preview, "normalized_rows", []))


def _cost_statistics_scope_keys_for_import_file_session(session: Any, selected_file_ids: list[str]) -> list[str]:
    return _workbench_matching_scope_months_for_import_file_session(session, selected_file_ids)


def _cost_statistics_scope_keys_for_import_rows(rows: Any) -> list[str]:
    months = _workbench_matching_scope_months_for_import_rows(rows)
    return months or ["all"]


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


def handle_import_fact_changed_event(event: Any) -> dict[str, Any]:
    scope_type = str(getattr(event, "scope_type", None) or event.payload.get("scope_type") or "").strip()
    scope_key = str(getattr(event, "scope_key", None) or event.payload.get("scope_key") or "").strip()
    return {
        "status": "acknowledged",
        "event_type": IMPORT_FACT_CHANGED_EVENT,
        "scope_type": scope_type,
        "scope_key": scope_key,
        "note": "import fact dirty scopes are persisted by the import fact writer",
    }


def handle_etc_business_oa_detection_event(service: Any, event: Any) -> dict[str, Any]:
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


def check_import_job_processors() -> dict[str, Callable[[Any], dict[str, object]]]:
    return {
        "general_import.confirm": _check_processor,
        "file_import.confirm": _check_processor,
        "etc_invoice_import.confirm": _check_processor,
        "tax_certified_import.confirm": _check_processor,
        "oa_manual_import.create": _check_processor,
    }


def _check_processor(_job: Any) -> dict[str, object]:
    return {"status": "check"}
