from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.state_store import ApplicationStateStore


BACKGROUND_JOB_STATUSES = {
    "queued",
    "running",
    "succeeded",
    "partial_success",
    "failed",
    "cancelled",
    "acknowledged",
}
ACTIVE_BACKGROUND_JOB_STATUSES = {"queued", "running"}
TERMINAL_BACKGROUND_JOB_STATUSES = {"succeeded", "partial_success", "failed", "cancelled", "acknowledged"}
IDEMPOTENT_REUSABLE_STATUSES = {"queued", "running", "succeeded", "partial_success"}
SENSITIVE_KEY_PARTS = ("password", "token", "secret", "content", "raw_file", "raw")


@dataclass(slots=True)
class BackgroundJob:
    job_id: str
    type: str
    label: str
    short_label: str
    owner_user_id: str
    visibility: str
    status: str
    phase: str
    current: int
    total: int
    percent: int
    message: str
    result_summary: dict[str, object]
    error: str | None
    idempotency_key: str | None
    source: dict[str, object]
    affected_scopes: list[str]
    affected_months: list[str]
    created_at: str
    started_at: str | None
    updated_at: str
    finished_at: str | None
    acknowledged_at: str | None

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


class BackgroundJobNotFoundError(KeyError):
    pass


class BackgroundJobAccessError(PermissionError):
    pass


class BackgroundJobService:
    def __init__(
        self,
        state_store: ApplicationStateStore | None = None,
        *,
        max_workers: int = 2,
        recent_success_seconds: int = 8,
        stale_after_seconds: int = 300,
    ) -> None:
        self._state_store = state_store
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="background-job")
        self._recent_success_window = timedelta(seconds=max(0, int(recent_success_seconds)))
        self._stale_after = timedelta(seconds=max(1, int(stale_after_seconds)))
        self._memory_jobs: dict[str, dict[str, object]] = {}
        self._mark_interrupted_jobs_failed()

    def create_job(
        self,
        *,
        job_type: str,
        label: str,
        owner_user_id: str,
        visibility: str = "owner",
        phase: str = "queued",
        current: int = 0,
        total: int = 0,
        message: str | None = None,
        result_summary: dict[str, object] | None = None,
        idempotency_key: str | None = None,
        source: dict[str, object] | None = None,
        affected_scopes: list[str] | None = None,
        affected_months: list[str] | None = None,
    ) -> BackgroundJob:
        now = self._now()
        safe_current, safe_total, percent = self._normalize_progress(current, total)
        job = BackgroundJob(
            job_id=self._new_job_id(),
            type=str(job_type).strip(),
            label=str(label).strip(),
            short_label="",
            owner_user_id=self._normalize_owner(owner_user_id),
            visibility=self._normalize_visibility(visibility),
            status="queued",
            phase=str(phase or "queued").strip() or "queued",
            current=safe_current,
            total=safe_total,
            percent=percent,
            message=str(message or "后台任务已排队。"),
            result_summary=self._sanitize_mapping(result_summary or {}),
            error=None,
            idempotency_key=str(idempotency_key).strip() if idempotency_key else None,
            source=self._sanitize_mapping(source or {}),
            affected_scopes=[str(item) for item in (affected_scopes or [])],
            affected_months=[str(item) for item in (affected_months or [])],
            created_at=now,
            started_at=None,
            updated_at=now,
            finished_at=None,
            acknowledged_at=None,
        )
        job.short_label = self._build_short_label(job)
        with self._lock:
            jobs = self._load_jobs()
            jobs[job.job_id] = job.to_payload()
            self._save_jobs(jobs)
        return job

    def create_or_get_idempotent_job(
        self,
        *,
        job_type: str,
        label: str,
        owner_user_id: str,
        idempotency_key: str,
        visibility: str = "owner",
        phase: str = "queued",
        current: int = 0,
        total: int = 0,
        message: str | None = None,
        result_summary: dict[str, object] | None = None,
        source: dict[str, object] | None = None,
        affected_scopes: list[str] | None = None,
        affected_months: list[str] | None = None,
    ) -> BackgroundJob:
        job, _created = self.create_or_get_idempotent_job_with_created(
            job_type=job_type,
            label=label,
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
            visibility=visibility,
            phase=phase,
            current=current,
            total=total,
            message=message,
            result_summary=result_summary,
            source=source,
            affected_scopes=affected_scopes,
            affected_months=affected_months,
        )
        return job

    def create_or_get_idempotent_job_with_created(
        self,
        *,
        job_type: str,
        label: str,
        owner_user_id: str,
        idempotency_key: str,
        visibility: str = "owner",
        phase: str = "queued",
        current: int = 0,
        total: int = 0,
        message: str | None = None,
        result_summary: dict[str, object] | None = None,
        source: dict[str, object] | None = None,
        affected_scopes: list[str] | None = None,
        affected_months: list[str] | None = None,
        reuse_any_status: bool = False,
    ) -> tuple[BackgroundJob, bool]:
        normalized_owner = self._normalize_owner(owner_user_id)
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            return self.create_job(
                job_type=job_type,
                label=label,
                owner_user_id=normalized_owner,
                visibility=visibility,
                phase=phase,
                current=current,
                total=total,
                message=message,
                result_summary=result_summary,
                source=source,
                affected_scopes=affected_scopes,
                affected_months=affected_months,
            ), True

        with self._lock:
            jobs = self._load_jobs()
            for payload in jobs.values():
                job = self._job_from_payload(payload)
                if (
                    job.owner_user_id == normalized_owner
                    and job.idempotency_key == normalized_key
                    and (reuse_any_status or job.status in IDEMPOTENT_REUSABLE_STATUSES)
                ):
                    return job, False

            now = self._now()
            safe_current, safe_total, percent = self._normalize_progress(current, total)
            job = BackgroundJob(
                job_id=self._new_job_id(),
                type=str(job_type).strip(),
                label=str(label).strip(),
                short_label="",
                owner_user_id=normalized_owner,
                visibility=self._normalize_visibility(visibility),
                status="queued",
                phase=str(phase or "queued").strip() or "queued",
                current=safe_current,
                total=safe_total,
                percent=percent,
                message=str(message or "后台任务已排队。"),
                result_summary=self._sanitize_mapping(result_summary or {}),
                error=None,
                idempotency_key=normalized_key,
                source=self._sanitize_mapping(source or {}),
                affected_scopes=[str(item) for item in (affected_scopes or [])],
                affected_months=[str(item) for item in (affected_months or [])],
                created_at=now,
                started_at=None,
                updated_at=now,
                finished_at=None,
                acknowledged_at=None,
            )
            job.short_label = self._build_short_label(job)
            jobs[job.job_id] = job.to_payload()
            self._save_jobs(jobs)
            return job, True

    def start_job(self, job_id: str) -> BackgroundJob:
        now = self._now()

        def mutate(job: BackgroundJob) -> None:
            job.status = "running"
            job.phase = "running" if job.phase == "queued" else job.phase
            job.started_at = job.started_at or now
            job.updated_at = now
            job.message = job.message if job.message and job.message != "后台任务已排队。" else "后台任务已开始。"

        return self._mutate_job(job_id, mutate)

    def update_progress(
        self,
        job_id: str,
        *,
        phase: str,
        message: str,
        current: int,
        total: int,
        result_summary: dict[str, object] | None = None,
    ) -> BackgroundJob:
        def mutate(job: BackgroundJob) -> None:
            safe_current, safe_total, percent = self._normalize_progress(current, total)
            job.status = "running" if job.status == "queued" else job.status
            job.phase = str(phase or job.phase).strip() or job.phase
            job.message = str(message or job.message)
            job.current = safe_current
            job.total = safe_total
            job.percent = percent
            if result_summary is not None:
                job.result_summary = self._sanitize_mapping(result_summary)
            job.updated_at = self._now()

        return self._mutate_job(job_id, mutate)

    def succeed_job(
        self,
        job_id: str,
        message: str,
        result_summary: dict[str, object] | None = None,
        *,
        status: str = "succeeded",
    ) -> BackgroundJob:
        if status not in {"succeeded", "partial_success"}:
            raise ValueError("success status must be succeeded or partial_success.")

        def mutate(job: BackgroundJob) -> None:
            now = self._now()
            job.status = status
            job.phase = "complete" if status == "succeeded" else "partial_success"
            job.message = str(message or job.message)
            if job.total > 0:
                job.current = job.total
                job.percent = 100
            if result_summary is not None:
                job.result_summary = self._sanitize_mapping(result_summary)
            job.error = None
            job.finished_at = now
            job.updated_at = now

        return self._mutate_job(job_id, mutate)

    def fail_job(self, job_id: str, message: str, error: str) -> BackgroundJob:
        def mutate(job: BackgroundJob) -> None:
            now = self._now()
            job.status = "failed"
            job.phase = "failed"
            job.message = str(message or "后台任务失败。")
            job.error = str(error or message or "后台任务失败。")
            job.finished_at = now
            job.updated_at = now

        return self._mutate_job(job_id, mutate)

    def acknowledge_job(self, job_id: str, owner_user_id: str) -> BackgroundJob:
        owner = self._normalize_owner(owner_user_id)

        def mutate(job: BackgroundJob) -> None:
            if not self._can_view(job, owner, include_system=True):
                raise BackgroundJobAccessError(job.job_id)
            if job.status == "acknowledged":
                return
            now = self._now()
            job.status = "acknowledged"
            job.acknowledged_at = now
            job.updated_at = now

        return self._mutate_job(job_id, mutate)

    def get_job(self, job_id: str, owner_user_id: str) -> BackgroundJob:
        owner = self._normalize_owner(owner_user_id)
        with self._lock:
            jobs = self._load_jobs()
            payload = jobs.get(str(job_id or "").strip())
            if payload is None:
                raise BackgroundJobNotFoundError(job_id)
            job = self._job_from_payload(payload)
        if not self._can_view(job, owner, include_system=True):
            raise BackgroundJobAccessError(job.job_id)
        return job

    def get_idempotent_job(self, owner_user_id: str, idempotency_key: str) -> BackgroundJob | None:
        owner = self._normalize_owner(owner_user_id)
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            return None
        with self._lock:
            jobs = [self._job_from_payload(payload) for payload in self._load_jobs().values()]
        for job in jobs:
            if job.owner_user_id == owner and job.idempotency_key == normalized_key:
                return job
        return None

    def list_active_jobs(self, owner_user_id: str, *, include_system: bool = True) -> list[BackgroundJob]:
        owner = self._normalize_owner(owner_user_id)
        now = datetime.now(UTC)
        with self._lock:
            jobs = [self._job_from_payload(payload) for payload in self._load_jobs().values()]
        active_jobs = [
            job
            for job in jobs
            if self._can_view(job, owner, include_system=include_system) and self._is_active(job, now)
        ]
        return sorted(active_jobs, key=lambda item: item.updated_at, reverse=True)

    def run_job(self, job: BackgroundJob, handler: Callable[[BackgroundJob], dict[str, object] | None]) -> Future:
        def runner() -> None:
            running_job = self.start_job(job.job_id)
            try:
                result_summary = handler(running_job)
            except Exception as exc:
                self.fail_job(job.job_id, "后台任务失败。", str(exc))
                return
            completed = self.get_job(job.job_id, running_job.owner_user_id)
            if completed.status not in TERMINAL_BACKGROUND_JOB_STATUSES:
                self.succeed_job(job.job_id, completed.message or "后台任务已完成。", result_summary=result_summary)

        return self._executor.submit(runner)

    def _mutate_job(self, job_id: str, mutator: Callable[[BackgroundJob], None]) -> BackgroundJob:
        normalized_job_id = str(job_id or "").strip()
        with self._lock:
            jobs = self._load_jobs()
            payload = jobs.get(normalized_job_id)
            if payload is None:
                raise BackgroundJobNotFoundError(normalized_job_id)
            job = self._job_from_payload(payload)
            mutator(job)
            job.short_label = self._build_short_label(job)
            jobs[job.job_id] = job.to_payload()
            self._save_jobs(jobs)
            return job

    def _mark_interrupted_jobs_failed(self) -> None:
        cutoff = datetime.now(UTC) - self._stale_after
        with self._lock:
            jobs = self._load_jobs()
            changed = False
            for job_id, payload in list(jobs.items()):
                job = self._job_from_payload(payload)
                if job.status not in ACTIVE_BACKGROUND_JOB_STATUSES:
                    continue
                updated_at = self._parse_time(job.updated_at)
                if updated_at is not None and updated_at > cutoff:
                    continue
                now = self._now()
                job.status = "failed"
                job.phase = "failed"
                job.message = "服务重启，任务已中断，请重新执行。"
                job.error = "interrupted_by_restart"
                job.finished_at = now
                job.updated_at = now
                job.short_label = self._build_short_label(job)
                jobs[job_id] = job.to_payload()
                changed = True
            if changed:
                self._save_jobs(jobs)

    def _load_jobs(self) -> dict[str, dict[str, object]]:
        if self._state_store is not None:
            return self._state_store.load_background_jobs()
        return {key: dict(value) for key, value in self._memory_jobs.items()}

    def _save_jobs(self, jobs: dict[str, dict[str, object]]) -> None:
        sanitized = {
            str(job_id): self._sanitize_mapping(payload)
            for job_id, payload in jobs.items()
            if isinstance(payload, dict)
        }
        if self._state_store is not None:
            self._state_store.save_background_jobs(sanitized)
            return
        self._memory_jobs = sanitized

    @classmethod
    def _job_from_payload(cls, payload: dict[str, object]) -> BackgroundJob:
        now = cls._now()
        status = str(payload.get("status") or "queued")
        if status not in BACKGROUND_JOB_STATUSES:
            status = "queued"
        current, total, percent = cls._normalize_progress(payload.get("current", 0), payload.get("total", 0))
        job = BackgroundJob(
            job_id=str(payload.get("job_id") or payload.get("id") or ""),
            type=str(payload.get("type") or ""),
            label=str(payload.get("label") or ""),
            short_label=str(payload.get("short_label") or ""),
            owner_user_id=cls._normalize_owner(payload.get("owner_user_id")),
            visibility=cls._normalize_visibility(payload.get("visibility")),
            status=status,
            phase=str(payload.get("phase") or status),
            current=current,
            total=total,
            percent=percent,
            message=str(payload.get("message") or ""),
            result_summary=cls._sanitize_mapping(payload.get("result_summary") if isinstance(payload.get("result_summary"), dict) else {}),
            error=str(payload.get("error")) if payload.get("error") not in (None, "") else None,
            idempotency_key=str(payload.get("idempotency_key")) if payload.get("idempotency_key") not in (None, "") else None,
            source=cls._sanitize_mapping(payload.get("source") if isinstance(payload.get("source"), dict) else {}),
            affected_scopes=[str(item) for item in payload.get("affected_scopes", [])] if isinstance(payload.get("affected_scopes"), list) else [],
            affected_months=[str(item) for item in payload.get("affected_months", [])] if isinstance(payload.get("affected_months"), list) else [],
            created_at=str(payload.get("created_at") or now),
            started_at=str(payload.get("started_at")) if payload.get("started_at") not in (None, "") else None,
            updated_at=str(payload.get("updated_at") or now),
            finished_at=str(payload.get("finished_at")) if payload.get("finished_at") not in (None, "") else None,
            acknowledged_at=str(payload.get("acknowledged_at")) if payload.get("acknowledged_at") not in (None, "") else None,
        )
        job.short_label = job.short_label or cls._build_short_label(job)
        return job

    @staticmethod
    def _build_short_label(job: BackgroundJob) -> str:
        label = job.label.strip() or "后台任务"
        progress = f" {job.current}/{job.total}" if job.total > 0 else ""
        if job.status in {"queued", "running"}:
            return f"正在{label}{progress}"
        if job.status == "succeeded":
            return f"{label}完成{progress}"
        if job.status == "partial_success":
            return f"{label}部分完成{progress}"
        if job.status == "failed":
            return f"{label}失败"
        return label

    def _is_active(self, job: BackgroundJob, now: datetime) -> bool:
        if job.status in ACTIVE_BACKGROUND_JOB_STATUSES:
            return True
        if job.acknowledged_at:
            return False
        if job.status in {"failed", "partial_success"}:
            return True
        if job.status == "succeeded":
            finished_at = self._parse_time(job.finished_at or job.updated_at)
            if finished_at is None:
                return True
            return now - finished_at <= self._recent_success_window
        return False

    @staticmethod
    def _can_view(job: BackgroundJob, owner_user_id: str, *, include_system: bool) -> bool:
        if job.owner_user_id == owner_user_id:
            return True
        if include_system and job.visibility == "system":
            return True
        return False

    @classmethod
    def _sanitize_mapping(cls, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            return {}
        sanitized: dict[str, object] = {}
        for key, value in payload.items():
            normalized_key = str(key)
            lowered_key = normalized_key.lower()
            if any(part in lowered_key for part in SENSITIVE_KEY_PARTS):
                continue
            sanitized[normalized_key] = cls._sanitize_value(value)
        return sanitized

    @classmethod
    def _sanitize_value(cls, value: object) -> object:
        if isinstance(value, dict):
            return cls._sanitize_mapping(value)
        if isinstance(value, list):
            return [cls._sanitize_value(item) for item in value]
        if isinstance(value, tuple):
            return [cls._sanitize_value(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return str(value)

    @staticmethod
    def _normalize_progress(current: object, total: object) -> tuple[int, int, int]:
        try:
            safe_total = max(0, int(total))
        except (TypeError, ValueError):
            safe_total = 0
        try:
            safe_current = max(0, int(current))
        except (TypeError, ValueError):
            safe_current = 0
        if safe_total > 0:
            safe_current = min(safe_current, safe_total)
            return safe_current, safe_total, int((safe_current / safe_total) * 100)
        return safe_current, 0, 0

    @staticmethod
    def _normalize_owner(owner_user_id: object) -> str:
        owner = str(owner_user_id or "").strip()
        return owner or "web_finance_user"

    @staticmethod
    def _normalize_visibility(visibility: object) -> str:
        normalized = str(visibility or "owner").strip()
        return normalized if normalized in {"owner", "admin", "system"} else "owner"

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _new_job_id() -> str:
        return f"job_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
