from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.import_job_queue import ImportJob


class TaxCertifiedImportJobService:
    def __init__(self, *, import_job_repository_provider: Callable[[], Any]) -> None:
        self._import_job_repository_provider = import_job_repository_provider

    def get_confirm_job_payload(self, import_job_id: str) -> dict[str, Any]:
        normalized_import_job_id = str(import_job_id or "").strip()
        if not normalized_import_job_id:
            raise ValueError("import_job_id is required.")
        repository = self._import_job_repository_provider()
        import_job = repository.get_job(normalized_import_job_id)
        if import_job is None or import_job.import_type != "tax_certified_import.confirm":
            raise KeyError(normalized_import_job_id)
        return self.serialize_import_job(import_job)

    @staticmethod
    def serialize_import_job(import_job: ImportJob) -> dict[str, Any]:
        return {
            "import_job_id": import_job.import_job_id,
            "tenant_id": import_job.tenant_id,
            "import_type": import_job.import_type,
            "import_session_id": import_job.import_session_id,
            "source_file_id": import_job.source_file_id,
            "status": import_job.status,
            "stage": import_job.stage,
            "priority": import_job.priority,
            "attempt_count": import_job.attempt_count,
            "max_attempts": import_job.max_attempts,
            "last_error": import_job.last_error,
            "trace_id": import_job.trace_id,
            "result_payload": import_job.result_payload,
        }
