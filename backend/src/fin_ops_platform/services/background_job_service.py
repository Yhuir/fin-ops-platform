from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
from threading import Lock
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.app_status_job_registry import APP_STATUS_BACKGROUND_JOB_REGISTRY
from fin_ops_platform.services.runtime_state_policy import RETIRED_BACKGROUND_JOB_TYPES
from fin_ops_platform.services.state_store_protocol import ApplicationStateStoreProtocol


BACKGROUND_JOB_STATUSES = {
    "queued",
    "running",
    "succeeded",
    "partial_success",
    "failed",
    "cancelled",
    "acknowledged",
    "superseded",
}
ACTIVE_BACKGROUND_JOB_STATUSES = {"queued", "running"}
ATTENTION_BACKGROUND_JOB_STATUSES = {"failed", "partial_success"}
TERMINAL_BACKGROUND_JOB_STATUSES = {
    "succeeded",
    "partial_success",
    "failed",
    "cancelled",
    "acknowledged",
    "superseded",
}
IDEMPOTENT_REQUEUEABLE_STATUSES = {"failed", "partial_success"}
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
    percent: int | None
    message: str
    result_summary: dict[str, object]
    error: str | None
    idempotency_key: str | None
    request_fingerprint: str | None
    source: dict[str, object]
    affected_scopes: list[str]
    affected_months: list[str]
    created_at: str
    started_at: str | None
    updated_at: str
    finished_at: str | None
    acknowledged_at: str | None
    superseded_by_job_id: str | None
    superseded_at: str | None

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
        affected_domains = _string_list(source.get("affected_domains") if isinstance(source, dict) else None)
        route = str(source.get("route") or "").strip() if isinstance(source, dict) else ""
        definition = APP_STATUS_BACKGROUND_JOB_REGISTRY.get(self.type)
        if not affected_domains and definition is not None:
            affected_domains = list(definition.affected_domains)
        if not route and definition is not None:
            route = definition.route
        payload["affected_domains"] = affected_domains
        payload["route"] = route or "/operations/app-health"
        return payload


class BackgroundJobNotFoundError(KeyError):
    pass


class BackgroundJobAccessError(PermissionError):
    pass


class BackgroundJobIdempotencyConflict(RuntimeError):
    pass


class BackgroundJobService:
    def __init__(
        self,
        state_store: ApplicationStateStoreProtocol | None = None,
        *,
        recent_success_seconds: int = 8,
        stale_after_seconds: int = 300,
    ) -> None:
        self._state_store = state_store
        self._lock = Lock()
        self._recent_success_window = timedelta(seconds=max(0, int(recent_success_seconds)))
        self._stale_after = timedelta(seconds=max(1, int(stale_after_seconds)))
        self._memory_jobs: dict[str, dict[str, object]] = {}

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
        job = self.build_job(
            job_type=job_type,
            label=label,
            owner_user_id=owner_user_id,
            visibility=visibility,
            phase=phase,
            current=current,
            total=total,
            message=message,
            result_summary=result_summary,
            idempotency_key=idempotency_key,
            source=source,
            affected_scopes=affected_scopes,
            affected_months=affected_months,
        )
        with self._lock:
            self._save_job(job)
        return job

    def build_job(
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
            request_fingerprint=None,
            source=self._sanitize_mapping(source or {}),
            affected_scopes=[str(item) for item in (affected_scopes or [])],
            affected_months=[str(item) for item in (affected_months or [])],
            created_at=now,
            started_at=None,
            updated_at=now,
            finished_at=None,
            acknowledged_at=None,
            superseded_by_job_id=None,
            superseded_at=None,
        )
        job.short_label = self._build_short_label(job)
        job.request_fingerprint = self._request_fingerprint(job)
        return job

    @classmethod
    def job_from_payload(cls, payload: dict[str, object]) -> BackgroundJob:
        return cls._job_from_payload(payload)

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

        candidate = self.build_job(
            job_type=job_type,
            label=label,
            owner_user_id=normalized_owner,
            visibility=visibility,
            phase=phase,
            current=current,
            total=total,
            message=message,
            result_summary=result_summary,
            idempotency_key=normalized_key,
            source=source,
            affected_scopes=affected_scopes,
            affected_months=affected_months,
        )
        with self._lock:
            if self._state_store is not None:
                payload, activated = self._state_store.create_or_requeue_background_job(
                    candidate.to_payload(),
                    reuse_any_status=reuse_any_status,
                )
                if payload is None:
                    raise BackgroundJobIdempotencyConflict(
                        "The same background job idempotency key was used for a different request."
                    )
                return self._job_from_payload(payload), activated

            jobs = self._load_jobs()
            for payload in jobs.values():
                existing = self._job_from_payload(payload)
                if (
                    existing.owner_user_id != normalized_owner
                    or existing.type != candidate.type
                    or existing.idempotency_key != normalized_key
                ):
                    continue
                if (
                    existing.request_fingerprint
                    and existing.request_fingerprint != candidate.request_fingerprint
                ):
                    raise BackgroundJobIdempotencyConflict(
                        "The same background job idempotency key was used for a different request."
                    )
                if not reuse_any_status and existing.status in IDEMPOTENT_REQUEUEABLE_STATUSES:
                    candidate.job_id = existing.job_id
                    candidate.created_at = existing.created_at
                    self._save_job(candidate)
                    return candidate, True
                return existing, False
            self._save_job(candidate)
            return candidate, True

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

    def acknowledge_jobs(self, job_ids: list[str], owner_user_id: str) -> list[BackgroundJob]:
        owner = self._normalize_owner(owner_user_id)
        normalized_job_ids = [str(job_id or "").strip() for job_id in job_ids]
        normalized_job_ids = [job_id for job_id in normalized_job_ids if job_id]
        if not normalized_job_ids:
            return []
        with self._lock:
            loaded_jobs: list[BackgroundJob] = []
            for job_id in normalized_job_ids:
                payload = self._load_job(job_id)
                if payload is None:
                    raise BackgroundJobNotFoundError(job_id)
                job = self._job_from_payload(payload)
                if not self._can_view(job, owner, include_system=True):
                    raise BackgroundJobAccessError(job.job_id)
                loaded_jobs.append(job)

            now = self._now()
            acknowledged_jobs: list[BackgroundJob] = []
            for job in loaded_jobs:
                if job.status != "acknowledged":
                    job.status = "acknowledged"
                    job.acknowledged_at = now
                    job.updated_at = now
                    job.short_label = self._build_short_label(job)
                    self._save_job(job)
                acknowledged_jobs.append(job)
            return acknowledged_jobs

    def supersede_job(
        self,
        job_id: str,
        owner_user_id: str,
        *,
        superseded_by_job_id: str,
    ) -> BackgroundJob:
        owner = self._normalize_owner(owner_user_id)
        replacement_job_id = str(superseded_by_job_id or "").strip()
        if not replacement_job_id:
            raise ValueError("superseded_by_job_id is required.")

        def mutate(job: BackgroundJob) -> None:
            if not self._can_view(job, owner, include_system=True):
                raise BackgroundJobAccessError(job.job_id)
            if job.status == "superseded" and job.superseded_by_job_id == replacement_job_id:
                return
            now = self._now()
            job.status = "superseded"
            job.phase = "superseded"
            job.superseded_by_job_id = replacement_job_id
            job.superseded_at = now
            job.finished_at = job.finished_at or now
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
            if job.type not in RETIRED_BACKGROUND_JOB_TYPES
            and self._can_view(job, owner, include_system=include_system)
            and self._is_active(job, now)
        ]
        return sorted(active_jobs, key=lambda item: item.updated_at, reverse=True)

    def active_source_values(self, *, job_type: str, source_key: str) -> set[str]:
        normalized_type = str(job_type or "").strip()
        normalized_key = str(source_key or "").strip()
        if not normalized_type or not normalized_key:
            return set()
        now = datetime.now(UTC)
        with self._lock:
            jobs = [self._job_from_payload(payload) for payload in self._load_jobs().values()]
        values: set[str] = set()
        for job in jobs:
            if job.type != normalized_type or not self._is_active(job, now):
                continue
            source = job.source if isinstance(job.source, dict) else {}
            value = str(source.get(normalized_key) or "").strip()
            if value:
                values.add(value)
        return values

    def list_attention_jobs(self, owner_user_id: str, *, include_system: bool = True) -> list[BackgroundJob]:
        owner = self._normalize_owner(owner_user_id)
        with self._lock:
            jobs = [self._job_from_payload(payload) for payload in self._load_jobs().values()]
        attention_jobs = [
            job
            for job in jobs
            if job.type not in RETIRED_BACKGROUND_JOB_TYPES
            and self._can_view(job, owner, include_system=include_system)
            and self._is_attention(job)
        ]
        return sorted(attention_jobs, key=lambda item: item.updated_at, reverse=True)

    def list_app_health_jobs(
        self,
        owner_user_id: str,
        *,
        include_system: bool = True,
    ) -> tuple[list[BackgroundJob], list[BackgroundJob]]:
        """Load one durable snapshot for App Health active/attention views."""
        owner = self._normalize_owner(owner_user_id)
        now = datetime.now(UTC)
        with self._lock:
            jobs = [self._job_from_payload(payload) for payload in self._load_jobs().values()]
        visible_jobs = [
            job
            for job in jobs
            if job.type not in RETIRED_BACKGROUND_JOB_TYPES
            and self._can_view(job, owner, include_system=include_system)
        ]
        active_jobs = sorted(
            (job for job in visible_jobs if self._is_active(job, now)),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        attention_jobs = sorted(
            (job for job in visible_jobs if self._is_attention(job)),
            key=lambda item: item.updated_at,
            reverse=True,
        )
        return active_jobs, attention_jobs

    def _mutate_job(self, job_id: str, mutator: Callable[[BackgroundJob], None]) -> BackgroundJob:
        normalized_job_id = str(job_id or "").strip()
        with self._lock:
            payload = self._load_job(normalized_job_id)
            if payload is None:
                raise BackgroundJobNotFoundError(normalized_job_id)
            job = self._job_from_payload(payload)
            mutator(job)
            job.short_label = self._build_short_label(job)
            self._save_job(job)
            return job

    def recover_interrupted_jobs(self) -> int:
        cutoff = datetime.now(UTC) - self._stale_after
        recovered = 0
        with self._lock:
            jobs = self._load_jobs()
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
                recovered += 1
                self._save_job(job)
        return recovered

    def _load_job(self, job_id: str) -> dict[str, object] | None:
        if self._state_store is not None:
            payload = self._state_store.load_background_job(job_id)
            return dict(payload) if isinstance(payload, dict) else None
        payload = self._memory_jobs.get(job_id)
        return dict(payload) if isinstance(payload, dict) else None

    def _load_jobs(self) -> dict[str, dict[str, object]]:
        if self._state_store is not None:
            return self._state_store.load_background_jobs()
        return {key: dict(value) for key, value in self._memory_jobs.items()}

    def _save_job(self, job: BackgroundJob) -> None:
        payload = self._sanitize_mapping(job.to_payload())
        if self._state_store is not None:
            self._state_store.save_background_job(payload)
            return
        self._memory_jobs[job.job_id] = payload

    @classmethod
    def _job_from_payload(cls, payload: dict[str, object]) -> BackgroundJob:
        now = cls._now()
        status = str(payload.get("status") or "queued")
        if status not in BACKGROUND_JOB_STATUSES:
            status = "queued"
        current, total, percent = cls._normalize_progress(payload.get("current", 0), payload.get("total", 0))
        source = cls._sanitize_mapping(payload.get("source") if isinstance(payload.get("source"), dict) else {})
        if "affected_domains" not in source and isinstance(payload.get("affected_domains"), list):
            source["affected_domains"] = [str(item) for item in payload.get("affected_domains", [])]
        if "route" not in source and payload.get("route") not in (None, ""):
            source["route"] = str(payload.get("route"))
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
            request_fingerprint=(
                str(payload.get("request_fingerprint"))
                if payload.get("request_fingerprint") not in (None, "")
                else None
            ),
            source=source,
            affected_scopes=[str(item) for item in payload.get("affected_scopes", [])] if isinstance(payload.get("affected_scopes"), list) else [],
            affected_months=[str(item) for item in payload.get("affected_months", [])] if isinstance(payload.get("affected_months"), list) else [],
            created_at=str(payload.get("created_at") or now),
            started_at=str(payload.get("started_at")) if payload.get("started_at") not in (None, "") else None,
            updated_at=str(payload.get("updated_at") or now),
            finished_at=str(payload.get("finished_at")) if payload.get("finished_at") not in (None, "") else None,
            acknowledged_at=str(payload.get("acknowledged_at")) if payload.get("acknowledged_at") not in (None, "") else None,
            superseded_by_job_id=(
                str(payload.get("superseded_by_job_id"))
                if payload.get("superseded_by_job_id") not in (None, "")
                else None
            ),
            superseded_at=str(payload.get("superseded_at")) if payload.get("superseded_at") not in (None, "") else None,
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
        if job.status == "superseded":
            return f"{label}已被新任务替代"
        return label

    def _is_active(self, job: BackgroundJob, now: datetime) -> bool:
        if job.status in ACTIVE_BACKGROUND_JOB_STATUSES:
            return True
        if job.status in {"acknowledged", "superseded"}:
            return False
        if job.acknowledged_at:
            return False
        if job.status == "succeeded":
            finished_at = self._parse_time(job.finished_at or job.updated_at)
            if finished_at is None:
                return True
            return now - finished_at <= self._recent_success_window
        return False

    @staticmethod
    def _is_attention(job: BackgroundJob) -> bool:
        if job.status not in ATTENTION_BACKGROUND_JOB_STATUSES:
            return False
        return not bool(job.acknowledged_at or job.superseded_at)

    @staticmethod
    def _request_fingerprint(job: BackgroundJob) -> str | None:
        if not job.idempotency_key:
            return None
        payload = {
            "type": job.type,
            "owner_user_id": job.owner_user_id,
            "visibility": job.visibility,
            "idempotency_key": job.idempotency_key,
            "source": job.source,
            "affected_scopes": job.affected_scopes,
            "affected_months": job.affected_months,
            "total": job.total,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

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


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
