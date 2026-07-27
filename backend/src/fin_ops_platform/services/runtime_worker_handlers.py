from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)
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
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
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
from fin_ops_platform.services.reconciliation import ManualReconciliationService
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
from fin_ops_platform.services.workbench_etc_batch_link import WORKBENCH_ETC_BATCH_LINK_VERSION
from fin_ops_platform.services.workbench_matching_dirty_scope_worker import (
    WorkbenchMatchingDirtyScopeWorker,
    WorkbenchMatchingDirtyScopeWorkerConfig,
)
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import WorkbenchReconciliationDirtyQueue
from fin_ops_platform.services.workbench_canonical_rows import WorkbenchCanonicalRowsBuilder
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork

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
    def __init__(self, *, data_dir: str | Path, connection: Any) -> None:
        self._data_dir = data_dir
        self._connection = connection

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
        import_support = _RuntimeWorkerImportSupport(
            state_store=state_store,
            search_service=_runtime_search_service(import_service),
            workbench_source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
        )
        processing_service = ImportProcessingService(
            file_import_service=file_import_service,
            tax_certified_import_service=tax_certified_import_service,
            etc_service=etc_service,
            etc_reconciliation_task_service=etc_reconciliation_task_service,
            background_job_service=background_job_service,
            serialize_value=_serialize_value,
            enqueue_workbench_auto_matching_for_scopes=import_support.enqueue_workbench_matching_job,
            persist_confirmed_import_delta=import_support.persist_confirmed_import_delta,
            workbench_matching_scope_months_for_import_file_session=_workbench_matching_scope_months_for_import_file_session,
            tax_offset_scope_keys_for_import_file_session=_tax_offset_scope_keys_for_import_file_session,
            bank_scope_keys_for_import_file_session=_bank_scope_keys_for_import_file_session,
            input_invoice_usage_scope_keys_for_import_file_session=_input_invoice_usage_scope_keys_for_import_file_session,
            output_invoice_collection_scope_keys_for_import_file_session=_output_invoice_collection_scope_keys_for_import_file_session,
            link_etc_import_result_to_existing_invoices=_link_etc_import_result_to_existing_invoices(
                import_service,
                etc_service,
                state_store,
            ),
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
        category_service = BankTransactionCategoryService.from_snapshot(
            state_store.load_bank_transaction_categories()
        )
        category_provider = BankTransactionEffectiveCategoryProvider(
            category_service=category_service,
            auto_category_service=BankTransactionAutoCategoryService(
                category_service=category_service
            ),
        )
        relation_uow = WorkbenchWriteUnitOfWork(
            connection=self._connection,
            repository_factory=self._workbench_uow_repository_factory,
            idempotency_store=PostgresWorkbenchIdempotencyRepository(self._connection),
        )
        return build_workbench_matching_dirty_scope_worker(
            dirty_queue=WorkbenchReconciliationDirtyQueue(repository=read_model_repository),
            matching_orchestrator=WorkbenchMatchingOrchestrator(
                fact_repository=PostgresWorkbenchFormalRelationFactRepository(self._connection),
                matcher=WorkbenchFreeMatchingEngine(),
                relation_uow=relation_uow,
                source_versions_provider=lambda: _workbench_matching_source_versions(app_settings_service),
                bank_category_provider=category_provider,
                bank_flow_rule_tag_rules_payload=(
                    app_settings_service.get_bank_flow_rule_batch_tag_rules_payload
                ),
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
            pair_relations=PostgresWorkbenchRelationRepository(transaction),
            etc_batch_links=PostgresWorkbenchFormalRelationFactRepository(transaction),
            exception_cases=workbench_repository,
            row_overrides=workbench_repository,
        )


def build_import_job_handler_bundle(
    *,
    connection: Any,
    worker_id: str,
    processors: dict[str, Callable[[Any], dict[str, object]]],
) -> RuntimeWorkerHandlerBundle:
    import_job_repository = ImportJobRepository(connection)
    import_job_worker = ImportJobWorker(
        repository=import_job_repository,
        worker_id=worker_id,
        processors=processors,
    )
    return RuntimeWorkerHandlerBundle(
        handlers={IMPORT_PROCESS_REQUESTED_EVENT: import_job_worker.handle_runtime_event}
    )


class _RuntimeWorkerImportSupport:
    def __init__(
        self,
        *,
        state_store: Any,
        search_service: SearchService,
        workbench_source_versions_provider: Callable[[], dict[str, object]],
    ) -> None:
        self._state_store = state_store
        self._search_service = search_service
        self._workbench_source_versions_provider = workbench_source_versions_provider

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

    def persist_confirmed_import_delta(
        self,
        *,
        import_state_payload: dict[str, Any],
    ) -> None:
        payload = dict(import_state_payload or {})
        if not payload or set(payload) - {"imports", "file_imports"}:
            raise ValueError("File import persistence requires only imports and file_imports payloads.")
        persist = getattr(self._state_store, "save_import_delta", None)
        if not callable(persist):
            raise RuntimeError("File import confirmation requires the import delta persistence port.")
        persist(payload)
        self._search_service.clear_cache()

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
        "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
        "workbench_etc_batch_link_version": WORKBENCH_ETC_BATCH_LINK_VERSION,
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


def _bank_scope_keys_for_import_file_session(
    session: Any,
    selected_file_ids: list[str],
) -> list[str]:
    selected = {str(file_id) for file_id in list(selected_file_ids or [])}
    rows: list[Any] = []
    for file in list(getattr(session, "files", []) or []):
        if str(getattr(file, "id", "") or "") in selected:
            rows.extend(list(getattr(file, "normalized_rows", []) or []))
    return _bank_scope_keys_for_import_rows(rows)


def _bank_scope_keys_for_import_rows(rows: Any) -> list[str]:
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
    return _workbench_matching_scope_months_for_import_rows(rows) if rows else []


def _normalized_batch_type(value: Any) -> BatchType | None:
    if isinstance(value, BatchType):
        return value
    try:
        return BatchType(str(value or "").strip())
    except ValueError:
        return None


class _WorkbenchSqlMatchingRowProvider:
    def __init__(self, *, connection: Any) -> None:
        self._builder = WorkbenchCanonicalRowsBuilder(connection=connection)

    def rows_for_scope(self, scope_month: str) -> dict[str, list[dict[str, object]]]:
        month = str(scope_month or "").strip()
        return {
            "oa_rows": list(self._builder._oa_projection_rows(month)),
            "bank_rows": list(self._builder._bank_rows(month)),
            "invoice_rows": list(self._builder._invoice_rows(month)),
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
