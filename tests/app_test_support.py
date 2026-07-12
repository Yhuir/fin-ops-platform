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
        return _build_application(*args, **kwargs)


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
    application._persist_import_preview_state()  # noqa: SLF001
    batch = application._import_service.confirm_import(preview.id)  # noqa: SLF001
    application._persist_import_preview_state()  # noqa: SLF001
    return preview, batch


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
