from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.app.server import build_application as _build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.import_job_queue import IMPORT_PROCESS_REQUESTED_EVENT, ImportJob
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.workbench_object_identity_arbitration import (
    WorkbenchObjectIdentityArbitrationService,
)
from fin_ops_platform.services.workbench_relation_grouping import WorkbenchRelationGroupingService


class _LocalTurnoverReadModelFixtureRepository:
    """Expose local test facts through the production query service's read-model contract."""

    def __init__(self, application: Application) -> None:
        self._application = application

    def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object]:
        service = self._application._turnover_ledger_service  # noqa: SLF001
        query = {
            "family": str(kwargs.get("family") or "all"),
            "direction": str(kwargs.get("direction") or "all"),
            "status": str(kwargs["status"]) if kwargs.get("status") not in (None, "") else None,
            "page": int(kwargs.get("page") or 1),
            "page_size": int(kwargs.get("page_size") or 50),
        }
        payload = service.list_ledger(**query)
        result = dict(payload)
        grouped = service.list_grouped_ledger(**query)
        groups_by_key = {
            (str(group.get("family") or ""), str(group.get("counterparty_name") or "")): group
            for group in list(grouped.get("groups") or [])
            if isinstance(group, dict)
        }
        result["rows"] = [
            {
                **row,
                "flow_rows": list(group.get("flow_rows") or []),
                "allocation_lots": list(group.get("allocation_lots") or []),
                "lot_rows": list(group.get("lot_rows") or []),
            }
            if isinstance(row, dict)
            and isinstance(
                group := groups_by_key.get(
                    (str(row.get("family") or ""), str(row.get("counterparty_name") or ""))
                ),
                dict,
            )
            else row
            for row in list(payload.get("rows") or [])
        ]
        result["source_versions"] = dict(self._application._turnover_ledger_source_versions())  # noqa: SLF001
        result["refresh_status"] = "fresh"
        return result


def build_local_state_application(*args, **kwargs):
    data_dir = kwargs.get("data_dir")
    if data_dir is None and args:
        data_dir = args[0]
    if data_dir is None:
        return _build_application(*args, **kwargs)
    def build_local_store(requested_data_dir: Path | None):
        if requested_data_dir is None:
            return None
        return ApplicationStateStore(requested_data_dir)

    def load_local_bootstrap_state(application: Application) -> dict[str, object]:
        load_local_pickle = getattr(getattr(application, "_state_store", None), "_load_local_pickle", None)
        loaded = load_local_pickle() if callable(load_local_pickle) else {}
        return loaded if isinstance(loaded, dict) else {}

    with (
        patch("fin_ops_platform.app.server.build_state_store", side_effect=build_local_store),
        patch.object(Application, "_runtime_bootstrap_state", load_local_bootstrap_state),
    ):
        application = _build_application(*args, **kwargs)
    application._turnover_ledger_query_service._read_repository = _LocalTurnoverReadModelFixtureRepository(  # noqa: SLF001
        application
    )
    return application


def seed_confirmed_import(
    application: Application,
    *,
    batch_type: BatchType | str,
    source_name: str,
    imported_by: str,
    rows: list[dict[str, object]],
):
    """Create test facts through the service port used by the file/session workflow."""

    preview = application._import_service.preview_import(  # noqa: SLF001
        batch_type=batch_type if isinstance(batch_type, BatchType) else BatchType(batch_type),
        source_name=source_name,
        imported_by=imported_by,
        rows=rows,
    )
    persist = getattr(application._state_store, "save_import_delta", None)  # noqa: SLF001
    if callable(persist):
        persist(
            {
                "imports": application._import_service.persistence_snapshot_for_batches(  # noqa: SLF001
                    [preview.id],
                    include_facts=False,
                )
            }
        )
    batch = application._import_service.confirm_import(preview.id)  # noqa: SLF001
    if callable(persist):
        persist(
            {
                "imports": application._import_service.persistence_snapshot_for_batches([preview.id])  # noqa: SLF001
            }
        )
    return preview, batch


def build_grouped_workbench_projection(
    application: Application,
    month: str,
    *,
    include_query_rows: bool = True,
) -> dict[str, object]:
    """Project local test facts through the current pure Workbench grouping boundary.

    Local-state tests do not have the production PostgreSQL active-generation repository.
    They must inspect canonical facts and formal relations directly instead of restoring the
    removed full-page runtime fallback.
    """

    normalized_month = str(month or "").strip() or "all"
    rows_by_id: dict[str, dict[str, object]] = {}
    if include_query_rows:
        source_payload = application._workbench_query_service.get_workbench(normalized_month)  # noqa: SLF001
        for zone in ("paired", "unpaired"):
            zone_payload = source_payload.get(zone)
            if not isinstance(zone_payload, dict):
                continue
            for row_type in ("oa", "bank", "invoice"):
                for raw_row in list(zone_payload.get(row_type) or []):
                    if not isinstance(raw_row, dict):
                        continue
                    row = dict(raw_row)
                    row_id = str(row.get("id") or "").strip()
                    if row_id:
                        rows_by_id[row_id] = row

    fact_ids = [
        str(fact.id)
        for fact in [
            *application._import_service.list_transactions(month=normalized_month),  # noqa: SLF001
            *application._import_service.list_invoices(month=normalized_month),  # noqa: SLF001
        ]
        if str(getattr(fact, "id", "")).strip()
    ]
    if fact_ids:
        for row in application._resolve_live_rows_direct(fact_ids, month_hint=normalized_month):  # noqa: SLF001
            rows_by_id[str(row["id"])] = dict(row)

    active_relations = [
        dict(relation)
        for relation in application._workbench_pair_relation_service.list_active_relations()  # noqa: SLF001
        if normalized_month == "all"
        or str(relation.get("month_scope") or "all") in {"all", normalized_month}
    ]
    missing_relation_row_ids = [
        str(row_id)
        for relation in active_relations
        for row_id in list(relation.get("row_ids") or [])
        if str(row_id).strip() and str(row_id) not in rows_by_id
    ]
    if missing_relation_row_ids:
        for row in application._resolve_live_rows_direct(  # noqa: SLF001
            list(dict.fromkeys(missing_relation_row_ids)),
            month_hint=normalized_month,
        ):
            rows_by_id[str(row["id"])] = dict(row)

    WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)
    return WorkbenchRelationGroupingService().group_payload(
        normalized_month,
        rows_by_id=rows_by_id,
        active_relations=active_relations,
    )


class FreshWorkbenchWriteGateRepository:
    def __init__(self, version: str) -> None:
        self.version = str(version)

    def get_workbench_groups_freshness_status(self, **_kwargs: object) -> dict[str, object]:
        return {
            "read_model_status": "fresh",
            "read_model_version": self.version,
        }


def install_fresh_workbench_write_gate(application: Application, *, version: str = "test-generation-1") -> str:
    """Install only the generation precondition I/O required by local write-contract tests."""

    application._workbench_sql_read_repository = FreshWorkbenchWriteGateRepository(version)  # noqa: SLF001
    application._workbench_sql_read_model_stale_reasons = lambda *_args, **_kwargs: []  # noqa: SLF001
    return str(version)


class DurableImportQueueHarness:
    """Test driver for the same durable file-import job boundary used in production."""

    def __init__(self, application: Application) -> None:
        self.application = application
        self.events: list[SimpleNamespace] = []
        self.jobs: list[ImportJob] = []
        self._processed: set[str] = set()
        self.fail_next_enqueue = False

    def enqueue(self, **kwargs):
        if self.fail_next_enqueue:
            self.fail_next_enqueue = False
            raise RuntimeError("test durable import queue unavailable")
        event = SimpleNamespace(event_id=f"test-import-event-{len(self.events) + 1}", **kwargs)
        self.events.append(event)
        return event

    def create_or_get_job(self, **kwargs) -> ImportJob:
        idempotency_key = str(kwargs.get("idempotency_key") or "")
        for job in self.jobs:
            if job.idempotency_key == idempotency_key:
                if job.status in {"pending", "failed", "dead_lettered"}:
                    updated = replace(
                        job,
                        status="pending",
                        stage="queued",
                        attempt_count=0,
                        last_error=None,
                        payload=dict(kwargs.get("payload") or {}),
                        raw_payload=dict(kwargs.get("raw_payload") or {}),
                        created_by=str(kwargs.get("created_by") or "") or None,
                    )
                    self.jobs[self.jobs.index(job)] = updated
                    return updated
                return job
        job = ImportJob(
            import_job_id=f"test-import-job-{len(self.jobs) + 1}",
            tenant_id=str(kwargs.get("tenant_id") or "default"),
            import_type=str(kwargs["import_type"]),
            import_session_id=str(kwargs.get("import_session_id") or "") or None,
            source_file_id=str(kwargs.get("source_file_id") or "") or None,
            idempotency_key=idempotency_key or None,
            status="pending",
            stage="queued",
            priority=str(kwargs.get("priority") or "normal"),
            attempt_count=0,
            max_attempts=int(kwargs.get("max_attempts") or 5),
            last_error=None,
            payload=dict(kwargs.get("payload") or {}),
            result_payload={},
            raw_payload=dict(kwargs.get("raw_payload") or {}),
            created_by=str(kwargs.get("created_by") or "") or None,
            trace_id=str(kwargs.get("trace_id") or "") or None,
        )
        self.jobs.append(job)
        return job

    def enqueue_process_requested(self, *, queue_repository, import_job: ImportJob, reason: str):
        return queue_repository.enqueue(
            event_type=IMPORT_PROCESS_REQUESTED_EVENT,
            aggregate_type="import_job",
            aggregate_id=import_job.import_job_id,
            scope_type="import",
            scope_key=import_job.import_type,
            dedupe_key=f"{IMPORT_PROCESS_REQUESTED_EVENT}:{import_job.tenant_id}:{import_job.import_job_id}",
            payload={"import_job_id": import_job.import_job_id, "import_type": import_job.import_type, "reason": reason},
            tenant_id=import_job.tenant_id,
            source_version=0,
            priority=import_job.priority,
            trace_id=import_job.trace_id,
        )

    def get_job(self, import_job_id: str) -> ImportJob | None:
        return next((job for job in self.jobs if job.import_job_id == import_job_id), None)

    def process_all(self, *, raise_errors: bool = True) -> None:
        processors = self.application._import_processing_service.build_import_job_processors()  # noqa: SLF001
        for index, job in enumerate(list(self.jobs)):
            if job.import_job_id in self._processed:
                continue
            try:
                result = processors[job.import_type](job)
            except Exception as exc:
                self.jobs[index] = replace(job, status="failed", stage="processor_failed", last_error=str(exc))
                if raise_errors:
                    raise
                continue
            self.jobs[index] = replace(job, status="succeeded", stage="succeeded", result_payload=dict(result))
            self._processed.add(job.import_job_id)


def install_durable_import_queue(application: Application) -> DurableImportQueueHarness:
    harness = DurableImportQueueHarness(application)
    current = getattr(application, "_runtime_repositories", None)
    values = dict(vars(current)) if current is not None and hasattr(current, "__dict__") else {}
    values.update(
        {
            "queue_repository": harness,
            "queue_settings": SimpleNamespace(backend="postgres"),
            "summary": getattr(current, "summary", lambda: {}),
        }
    )
    application._runtime_repositories = SimpleNamespace(**values)  # noqa: SLF001
    application._import_job_repository = harness  # noqa: SLF001
    return harness
