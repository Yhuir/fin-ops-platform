from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from threading import Event, Thread
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection
from fin_ops_platform.services.postgres_repositories.import_job_status import scoped_import_jobs
from fin_ops_platform.services.runtime_queue import PRIORITY_VALUES
from fin_ops_platform.services.runtime_worker import (
    RuntimeWorker,
    RuntimeWorkerConfig,
    RuntimeWorkerResult,
    RuntimeWorkerShutdownRequested,
    RuntimeWorkerTaskTimeout,
)


class ImportJobDataError(ValueError):
    pass


class ImportJobIdempotencyConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportJob:
    import_job_id: str
    tenant_id: str
    import_type: str
    import_session_id: str | None
    source_file_id: str | None
    idempotency_key: str | None
    request_fingerprint: str | None
    status: str
    stage: str
    priority: str
    attempt_count: int
    max_attempts: int
    last_error: str | None
    payload: dict[str, Any]
    result_payload: dict[str, Any]
    raw_payload: dict[str, Any]
    created_by: str | None
    trace_id: str | None
    version: int = 1
    claim_version: int = 0
    locked_by: str | None = None
    affected_domains: tuple[str, ...] | None = None
    acknowledged_at: Any = None
    created_at: Any = None
    updated_at: Any = None
    finished_at: Any = None
    completion: ImportJobCompletion | None = field(default=None, repr=False, compare=False)


ImportJobProcessor = Callable[[ImportJob], dict[str, Any] | None]


class ImportJobRepository:
    def __init__(self, connection: PostgresConnection) -> None:
        self._connection = connection

    def create_or_get_job(
        self,
        *,
        import_type: str,
        tenant_id: str = "default",
        import_session_id: str | None = None,
        source_file_id: str | None = None,
        idempotency_key: str | None = None,
        payload: dict[str, Any] | None = None,
        raw_payload: dict[str, Any] | None = None,
        created_by: str | None = None,
        trace_id: str | None = None,
        priority: str = "normal",
        max_attempts: int = 5,
        available_at: Any | None = None,
        stage: str = "commit",
        status: str = "pending",
        transaction: Any = None,
    ) -> ImportJob:
        if stage not in {"prepare", "commit"} or status not in {"pending", "awaiting_confirmation"}:
            raise ImportJobDataError("Invalid initial import stage or status.")
        normalized_import_type = _required_text(import_type, "import_type")
        normalized_tenant_id = _optional_text(tenant_id) or "default"
        normalized_priority = _normalize_priority(priority)
        normalized_max_attempts = _positive_int(max_attempts, "max_attempts")
        normalized_payload = _normalize_payload(payload, "payload")
        normalized_raw_payload = _normalize_payload(raw_payload, "raw_payload")
        normalized_idempotency_key = _optional_text(idempotency_key)
        request_fingerprint = _import_request_fingerprint(
            tenant_id=normalized_tenant_id,
            import_type=normalized_import_type,
            import_session_id=_optional_text(import_session_id),
            source_file_id=_optional_text(source_file_id),
            payload=normalized_payload,
        )
        with (nullcontext(transaction) if transaction is not None else self._connection.transaction()) as transaction:
            row = transaction.fetch_one(
                """
                insert into job.import_jobs (
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    max_attempts,
                    payload,
                    raw_payload,
                    created_by,
                    trace_id,
                    available_at
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s, now()))
                on conflict (tenant_id, idempotency_key)
                where idempotency_key is not null
                do update set updated_at=job.import_jobs.updated_at
                where job.import_jobs.created_by is not distinct from excluded.created_by
                  and (job.import_jobs.request_fingerprint is null
                       or job.import_jobs.request_fingerprint = excluded.request_fingerprint)
                returning
                    id::text as import_job_id,
                    tenant_id,
                    import_type,
                    import_session_id,
                    source_file_id,
                    idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    priority,
                    attempt_count,
                    max_attempts,
                    last_error,
                    payload,
                    result_payload,
                    raw_payload,
                    created_by,
                    trace_id, version, claim_version, locked_by, acknowledged_at, created_at, updated_at, finished_at
                """,
                (
                    normalized_tenant_id,
                    normalized_import_type,
                    _optional_text(import_session_id),
                    _optional_text(source_file_id),
                    normalized_idempotency_key,
                    request_fingerprint,
                    status,
                    stage,
                    normalized_priority,
                    normalized_max_attempts,
                    self._json_param(normalized_payload),
                    self._json_param(normalized_raw_payload),
                    _optional_text(created_by),
                    _optional_text(trace_id),
                    available_at,
                ),
            )
        if row is None:
            raise ImportJobIdempotencyConflict("The same import idempotency key was used for a different request.")
        return _job_from_row(row)

    def get_job(self, import_job_id: str) -> ImportJob | None:
        normalized_id = _required_text(import_job_id, "import_job_id")
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one(
                scoped_import_jobs("select * from job.import_jobs where id=%s")
                + "select *, id::text as import_job_id from scoped_jobs",
                (normalized_id,),
            )
        return _job_from_row(row) if row is not None else None

    def claim_next(self, worker_id: str, *, lock_timeout_seconds: int = 300, import_job_id: str | None = None) -> ImportJob | None:
        with self._connection.transaction() as transaction:
            # A crashed final attempt becomes visibly failed instead of remaining
            # permanently processing. No outbox receipt participates in ownership.
            transaction.execute("""
                with exhausted as (
                    select id from job.import_jobs
                    where (%s::uuid is null or id=%s::uuid) and attempt_count >= max_attempts
                        and (status='pending' or (status='processing'
                            and locked_at < now() - (%s * interval '1 second')))
                    for update skip locked
                )
                update job.import_jobs j set status='failed',
                    last_error='Import maximum attempts exhausted; explicit retry is required.',
                    locked_by=null, locked_at=null, finished_at=now(), updated_at=now(), version=version+1
                from exhausted where j.id=exhausted.id
            """, (import_job_id, import_job_id, lock_timeout_seconds,))
            row = transaction.fetch_one("""
                with candidate as (
                    select id from job.import_jobs
                    where (%s::uuid is null or id=%s::uuid) and attempt_count < max_attempts and (
                        (status='pending' and available_at<=now()) or
                        (status='processing' and locked_at < now() - (%s * interval '1 second'))
                    )
                    order by case priority when 'urgent' then 0 when 'high' then 1 when 'normal' then 2 else 3 end,
                        available_at, created_at
                    for update skip locked limit 1
                )
                update job.import_jobs j set status='processing',
                    stage=case when j.stage='prepare' then 'prepare' else 'commit' end,
                    attempt_count=j.attempt_count+1, claim_version=j.claim_version+1,
                    version=j.version+1, locked_by=%s, locked_at=now(),
                    started_at=coalesce(j.started_at,now()), last_error=null, updated_at=now()
                from candidate where j.id=candidate.id returning j.*, j.id::text as import_job_id
            """, (import_job_id, import_job_id, lock_timeout_seconds, _required_text(worker_id, "worker_id")))
        return _job_from_row(row) if row else None

    def renew(self, job: ImportJob) -> bool:
        return bool(self._connection.execute("""
            update job.import_jobs set locked_at=now() where id=%s and status='processing'
                and locked_by=%s and claim_version=%s
        """, (job.import_job_id, job.locked_by, job.claim_version)))

    def fail_claim(self, job: ImportJob, *, error: str, retry: bool, delay_seconds: int = 1) -> bool:
        retry = retry and job.attempt_count < job.max_attempts
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status=%s, last_error=%s,
                    result_payload=jsonb_build_object('error_code','processor_failed'),
                    available_at=now()+(%s*interval '1 second'),
                    finished_at=case when %s then null else now() end,
                    locked_by=null, locked_at=null, version=version+1, updated_at=now()
                where id=%s and status='processing' and locked_by=%s and claim_version=%s returning id
            """, ('pending' if retry else 'failed', error, delay_seconds, retry,
                  job.import_job_id, job.locked_by, job.claim_version))
        return row is not None

    def confirm_job(self, import_job_id: str, *, expected_version: int, payload: dict[str, Any]) -> ImportJob:
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status='pending', stage='commit', payload=%s,
                    version=version+1, available_at=now(), attempt_count=0,
                    acknowledged_at=null, last_error=null, updated_at=now()
                where id=%s and version=%s and status in ('awaiting_confirmation','needs_review')
                  and not (result_payload ? 'disposition')
                returning *, id::text as import_job_id
            """, (self._json_param(payload), import_job_id, expected_version))
        if row is None:
            raise ImportJobIdempotencyConflict("Import preview changed or confirmation already accepted.")
        return _job_from_row(row)

    def retry_job(self, import_job_id: str, *, expected_version: int) -> ImportJob:
        with self._connection.transaction() as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status='pending', attempt_count=0, last_error=null,
                    version=version+1, available_at=now(), finished_at=null, acknowledged_at=null, updated_at=now()
                where id=%s and version=%s and status='failed' and not (result_payload ? 'disposition')
                returning *, id::text as import_job_id
            """, (import_job_id, expected_version))
        if row is None:
            raise ImportJobIdempotencyConflict("Only a failed import can be retried.")
        return _job_from_row(row)

    def require_review(self, job: ImportJob, *, error: str) -> bool:
        return bool(self._connection.execute("""
            update job.import_jobs set status='needs_review', last_error=%s,
                result_payload=jsonb_build_object('error_code','review_required'),
                locked_by=null, locked_at=null, version=version+1, updated_at=now()
            where id=%s and status='processing' and locked_by=%s and claim_version=%s
        """, (error, job.import_job_id, job.locked_by, job.claim_version)))

    def mark_preview_needs_review(self, import_job_id: str, *, expected_version: int, transaction: Any = None) -> ImportJob:
        with (nullcontext(transaction) if transaction is not None else self._connection.transaction()) as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status='needs_review', version=version+1,
                    last_error='Preview dependencies changed; prepare again.', updated_at=now()
                where id=%s and version=%s and status='awaiting_confirmation'
                returning *, id::text as import_job_id
            """, (import_job_id, expected_version))
        if row is None:
            raise ImportJobIdempotencyConflict("Import preview changed before review transition.")
        return _job_from_row(row)

    def reprepare_job(self, import_job_id: str, *, expected_version: int, payload: dict[str, Any] | None = None, transaction: Any = None) -> ImportJob:
        with (nullcontext(transaction) if transaction is not None else self._connection.transaction()) as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status='pending', stage='prepare', attempt_count=0,
                    last_error=null, version=version+1, claim_version=claim_version+1, result_payload='{}'::jsonb,
                    payload=coalesce(%s,payload), available_at=now(), finished_at=null,
                    acknowledged_at=null, updated_at=now()
                where id=%s and version=%s and status in ('needs_review','awaiting_confirmation','failed')
                  and not (result_payload ? 'disposition')
                returning *, id::text as import_job_id
            """, (self._json_param(payload) if payload is not None else None, import_job_id, expected_version))
        if row is None:
            raise ImportJobIdempotencyConflict("Import preview changed before re-preparation.")
        return _job_from_row(row)

    def cancel_job(self, import_job_id: str, *, created_by: str, transaction: Any = None) -> ImportJob:
        with (nullcontext(transaction) if transaction is not None else self._connection.transaction()) as transaction:
            row = transaction.fetch_one("""
                update job.import_jobs set status='canceled', claim_version=claim_version+1,
                    version=version+1, locked_by=null, locked_at=null, finished_at=now(), updated_at=now()
                where id=%s and created_by=%s and not (result_payload ? 'disposition') and status in
                    ('pending','processing','awaiting_confirmation','needs_review','failed')
                returning *, id::text as import_job_id
            """, (import_job_id, created_by))
        if row is None:
            raise ImportJobIdempotencyConflict("Import already completed or is not owned by this user.")
        return _job_from_row(row)

    def acknowledge_job(self, import_job_id: str, *, created_by: str) -> bool:
        return bool(self._connection.execute("""
            update job.import_jobs set acknowledged_at=now() where id=%s and created_by=%s
                and status in ('succeeded','failed','canceled')
        """, (import_job_id, created_by)))

    def list_jobs(self, *, created_by: str, limit: int = 100, statuses: list[str] | None = None) -> list[ImportJob]:
        rows = self._connection.fetch_all(scoped_import_jobs("""
            select * from job.import_jobs
            where created_by=%s and acknowledged_at is null and (%s::text[] is null or status=any(%s))
            order by case when status in ('pending','processing','awaiting_confirmation','needs_review','failed') then 0 else 1 end,
                created_at desc limit %s
        """) + """
            select id::text as import_job_id, tenant_id, import_type, import_session_id, source_file_id,
                idempotency_key, request_fingerprint, status, stage, priority, attempt_count, max_attempts,
                last_error, created_by, trace_id, version, claim_version, locked_by,
                acknowledged_at, created_at, updated_at, finished_at, affected_domains,
                payload - 'upload_manifest' as payload,
                result_payload - 'session' - 'preview' as result_payload, '{}'::jsonb as raw_payload
            from scoped_jobs
            order by case when status in ('pending','processing','awaiting_confirmation','needs_review','failed') then 0 else 1 end,
                created_at desc
        """, (created_by, statuses, statuses, min(200, max(1, int(limit)))))
        return [_job_from_row(row) for row in rows]

    def get_by_idempotency_key(self, idempotency_key: str, *, created_by: str) -> ImportJob | None:
        row = self._connection.fetch_one("""
            select *, id::text as import_job_id from job.import_jobs
            where tenant_id='default' and idempotency_key=%s and created_by=%s
        """, (idempotency_key, created_by))
        return _job_from_row(row) if row else None

    def list_by_session(self, import_session_id: str) -> list[ImportJob]:
        return [_job_from_row(row) for row in self._connection.fetch_all("""
            select *, id::text as import_job_id from job.import_jobs
            where import_session_id=%s order by created_at desc limit 100
        """, (import_session_id,))]

    def _json_param(self, value: dict[str, Any]) -> Any:
        if isinstance(self._connection, PostgresConnection):
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        return value


class ImportJobLeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class ImportJobCompletion:
    job: ImportJob

    def lock(self, transaction: Any) -> None:
        row = transaction.fetch_one("""
            select id from job.import_jobs where id=%s and status='processing'
                and locked_by=%s and claim_version=%s for update
        """, (self.job.import_job_id, self.job.locked_by, self.job.claim_version))
        if row is None:
            raise ImportJobLeaseLost("Import ownership changed before commit.")
        self._assert_current_authorization(transaction)

    def _assert_current_authorization(self, transaction: Any) -> None:
        from fin_ops_platform.services.access_control_service import AccessControlService
        from fin_ops_platform.services.oa_identity_service import OAUserIdentity
        from fin_ops_platform.services.state_store_protocol import PROTECTED_ADMIN_USERNAME
        owner = str(self.job.created_by or "").strip()
        if owner == PROTECTED_ADMIN_USERNAME:
            return
        # FOR SHARE makes revocation and financial commit have a defined order,
        # without serializing concurrent import commits against one another.
        row = transaction.fetch_one("""
            select settings_payload from app.app_settings where settings_key='app_settings' for share
        """)
        snapshot = dict((row or {}).get("settings_payload") or {})
        decision = AccessControlService(access_control_snapshot_provider=lambda: snapshot).evaluate(
            OAUserIdentity(user_id=owner, username=owner, nickname=owner, display_name=owner)
        )
        required = {
            "etc_invoice_import.confirm": {"imports.etc-invoices"},
            "tax_certified_import.confirm": {"tax-offset"},
            "oa_manual_import.create": {"settings"},
        }.get(self.job.import_type, set())
        if self.job.import_type == "file_import.confirm":
            route = self.job.payload.get("route")
            if route == "/imports/bank-transactions":
                required.add("imports.bank-transactions")
            elif route == "/imports/invoices":
                required.add("imports.invoices")
            for file_row in transaction.fetch_all("""
                select distinct coalesce(nullif(raw_payload->'normalized_payload'->>'batch_type',''),
                    nullif(raw_payload->'normalized_payload'->>'override_batch_type','')) as batch_type
                from app.import_files where legacy_mongo_id=any(%s)
            """, (list(self.job.payload.get("selected_file_ids") or []),)):
                if file_row["batch_type"] == "bank_transaction":
                    required.add("imports.bank-transactions")
                elif file_row["batch_type"] in {"input_invoice", "output_invoice"}:
                    required.add("imports.invoices")
        if not required or not all(decision.can_access_page(page) for page in required):
            raise PermissionError("Import authorization was revoked or its target page is not authorized.")

    def succeed(self, transaction: Any, result_payload: dict[str, Any]) -> None:
        self._finish(transaction, result_payload, "succeeded")

    def fail(self, transaction: Any, result_payload: dict[str, Any], *, error: str) -> None:
        self._finish(transaction, result_payload, "failed", error=error)

    def preview(self, transaction: Any, result_payload: dict[str, Any], *, status: str = "awaiting_confirmation") -> None:
        if status not in {"awaiting_confirmation", "needs_review"}:
            raise ImportJobDataError("Invalid preview outcome.")
        self._finish(transaction, result_payload, status)

    def _finish(self, transaction: Any, result_payload: dict[str, Any], status: str, *, error: str | None = None) -> None:
        from psycopg.types.json import Jsonb
        row = transaction.fetch_one("""
            update job.import_jobs set status=%s, result_payload=%s, version=version+1,
                finished_at=case when %s in ('succeeded','failed') then now() else null end,
                locked_by=null, locked_at=null, last_error=%s, updated_at=now()
            where id=%s and status='processing' and locked_by=%s and claim_version=%s returning id
        """, (status, Jsonb(result_payload), status,
              error,
              self.job.import_job_id,
              self.job.locked_by, self.job.claim_version))
        if row is None:
            raise ImportJobLeaseLost("Import ownership changed during commit.")


class ImportJobWorker(RuntimeWorker):
    def __init__(self, *, repository: ImportJobRepository, worker_id: str,
                 processors: dict[str, ImportJobProcessor] | None = None,
                 config: RuntimeWorkerConfig | None = None, heartbeat_recorder: Any = None) -> None:
        super().__init__(queue_repository=heartbeat_recorder,
                         config=config or RuntimeWorkerConfig(worker_id=worker_id, worker_kind="import-job"))
        self._repository = repository
        self._worker_id = _required_text(worker_id, "worker_id")
        self._processors = dict(processors or {})

    @property
    def processors(self) -> tuple[str, ...]:
        return tuple(sorted(self._processors))

    def run_once(self) -> RuntimeWorkerResult:
        job = self._repository.claim_next(self._worker_id, lock_timeout_seconds=self._config.lock_timeout_seconds)
        if job is None:
            self._record_heartbeat("idle", {"queue": "job.import_jobs"})
            return RuntimeWorkerResult.IDLE
        return self.process_claimed_job(job)

    def process_claimed_job(self, job: ImportJob) -> RuntimeWorkerResult:
        job = replace(job, completion=ImportJobCompletion(job))
        self._record_heartbeat("processing", {"import_job_id": job.import_job_id, "import_type": job.import_type})
        processor = self._processors.get(job.import_type)
        if processor is None:
            self._repository.fail_claim(job, error=f"Unknown import type: {job.import_type}", retry=False)
            return RuntimeWorkerResult.FAILED_PERMANENT
        stopped = Event()
        def renew() -> None:
            while not stopped.wait(max(0.1, self._config.lock_timeout_seconds / 3)):
                try:
                    if not self._repository.renew(job):
                        return
                except Exception:
                    # The commit fence is authoritative. If renewal loses the DB,
                    # another claimant advances claim_version before it can write.
                    return
        renewal = Thread(target=renew, name="import-lease", daemon=True)
        renewal.start()
        try:
            with self._task_timeout(self._config.task_timeout_seconds):
                processor(job)
            current = self._repository.get_job(job.import_job_id)
            if current is not None and current.status == "failed":
                self._record_heartbeat("failed", {"import_job_id": job.import_job_id, "error": current.last_error}, force=True)
                return RuntimeWorkerResult.FAILED_PERMANENT
            if current is None or current.status not in {"succeeded", "awaiting_confirmation", "needs_review"}:
                raise RuntimeError("Import processor did not commit its result with domain facts.")
            self._record_heartbeat("idle", {"import_job_id": job.import_job_id, "processed": True}, force=True)
            return RuntimeWorkerResult.PROCESSED
        except RuntimeWorkerShutdownRequested as exc:
            self._repository.fail_claim(job, error=str(exc), retry=True, delay_seconds=0)
            raise
        except (Exception, RuntimeWorkerTaskTimeout) as exc:
            from fin_ops_platform.services.etc_reconciliation_zip_filter import StaleReconciliationPreviewError
            from fin_ops_platform.services.etc_service import EtcImportPreviewStaleError
            from fin_ops_platform.services.import_preview_audit import (
                ImportPreviewStaleError,
                ImportReviewRequiredError,
            )
            if isinstance(exc, (ImportPreviewStaleError, ImportReviewRequiredError, EtcImportPreviewStaleError, StaleReconciliationPreviewError)):
                self._repository.require_review(job, error=str(exc))
                return RuntimeWorkerResult.DEFERRED
            retry = _is_transient_import_failure(exc) and job.attempt_count < job.max_attempts
            self._repository.fail_claim(job, error=str(exc) or type(exc).__name__, retry=retry,
                                        delay_seconds=min(60, 2 ** max(0, job.attempt_count-1)))
            self._record_heartbeat("failed", {"import_job_id": job.import_job_id, "error": str(exc)})
            return RuntimeWorkerResult.FAILED_RETRYABLE if retry else RuntimeWorkerResult.FAILED_PERMANENT
        finally:
            stopped.set()
            renewal.join(timeout=1)


def _is_transient_import_failure(error: BaseException) -> bool:
    from psycopg import OperationalError
    from psycopg.errors import DeadlockDetected, LockNotAvailable, QueryCanceled, SerializationFailure

    from fin_ops_platform.services.object_storage import ObjectStorageReadError, ObjectStorageWriteError
    return isinstance(error, (RuntimeWorkerTaskTimeout, ConnectionError, TimeoutError, OperationalError, DeadlockDetected,
                              LockNotAvailable, QueryCanceled, SerializationFailure,
                              ObjectStorageReadError, ObjectStorageWriteError))


def _job_from_row(row: dict[str, Any]) -> ImportJob:
    payload = _normalize_payload(row.get("payload"), "payload")
    result_payload = _normalize_payload(row.get("result_payload"), "result_payload")
    raw_payload = _normalize_payload(row.get("raw_payload"), "raw_payload")
    return ImportJob(
        import_job_id=str(row["import_job_id"]),
        tenant_id=str(row["tenant_id"]),
        import_type=str(row["import_type"]),
        import_session_id=_optional_text(row.get("import_session_id")),
        source_file_id=_optional_text(row.get("source_file_id")),
        idempotency_key=_optional_text(row.get("idempotency_key")),
        request_fingerprint=_optional_text(row.get("request_fingerprint")),
        status=str(row["status"]),
        stage=str(row["stage"]),
        priority=_normalize_priority(row.get("priority") or "normal"),
        attempt_count=int(row.get("attempt_count") or 0),
        max_attempts=int(row.get("max_attempts") or 5),
        last_error=_optional_text(row.get("last_error")),
        payload=payload,
        result_payload=result_payload,
        raw_payload=raw_payload,
        created_by=_optional_text(row.get("created_by")),
        trace_id=_optional_text(row.get("trace_id")),
        version=int(row.get("version") or 1),
        claim_version=int(row.get("claim_version") or 0),
        locked_by=_optional_text(row.get("locked_by")),
        affected_domains=tuple(row["affected_domains"]) if "affected_domains" in row else None,
        acknowledged_at=row.get("acknowledged_at"),
        created_at=row.get("created_at"),
        updated_at=row.get("updated_at"),
        finished_at=row.get("finished_at"),
    )


def _normalize_payload(value: Any, name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ImportJobDataError(f"{name} must be a JSON object.")
    return value


def _import_request_fingerprint(
    *,
    tenant_id: str,
    import_type: str,
    import_session_id: str | None,
    source_file_id: str | None,
    payload: dict[str, Any],
) -> str:
    business_payload = {key: value for key, value in payload.items() if key != "background_job_id"}
    encoded = json.dumps(
        {
            "tenant_id": tenant_id,
            "import_type": import_type,
            "import_session_id": import_session_id,
            "source_file_id": source_file_id,
            "payload": business_payload,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _required_text(value: Any, name: str) -> str:
    normalized = _optional_text(value)
    if not normalized:
        raise ImportJobDataError(f"{name} is required.")
    return normalized


def _optional_text(value: Any) -> str | None:
    normalized = str(value).strip() if value is not None else ""
    return normalized or None


def _normalize_priority(value: Any) -> str:
    normalized = str(value or "normal").strip().lower() or "normal"
    if normalized not in PRIORITY_VALUES:
        raise ImportJobDataError(f"priority must be one of {sorted(PRIORITY_VALUES)}.")
    return normalized


def _positive_int(value: Any, name: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ImportJobDataError(f"{name} must be an integer.") from exc
    if normalized <= 0:
        raise ImportJobDataError(f"{name} must be positive.")
    return normalized
