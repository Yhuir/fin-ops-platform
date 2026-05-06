from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha1
from typing import Any


DIRTY_SCOPE_WARNING_SECONDS = 300
DIRTY_SCOPE_CRITICAL_SECONDS = 900
WORKBENCH_REBUILD_WARNING_SECONDS = 300
BACKGROUND_JOB_WARNING_SECONDS = 600
RECENT_RECOVERED_LIMIT = 20


@dataclass(slots=True)
class AppHealthAlert:
    alert_id: str
    kind: str
    severity: str
    status: str
    message: str
    scope: str | None
    first_seen_at: str
    last_seen_at: str
    recovered_at: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


class AppHealthAlertService:
    def __init__(self, records: dict[str, AppHealthAlert] | None = None) -> None:
        self._records = dict(records or {})

    @classmethod
    def from_snapshot(cls, snapshot: object) -> "AppHealthAlertService":
        if not isinstance(snapshot, dict):
            return cls()
        raw_records = snapshot.get("records", snapshot)
        if not isinstance(raw_records, dict):
            return cls()
        records: dict[str, AppHealthAlert] = {}
        for raw_alert_id, raw_payload in raw_records.items():
            if not isinstance(raw_payload, dict):
                continue
            alert_id = str(raw_payload.get("alert_id") or raw_alert_id or "").strip()
            if not alert_id:
                continue
            records[alert_id] = AppHealthAlert(
                alert_id=alert_id,
                kind=str(raw_payload.get("kind") or "unknown"),
                severity=str(raw_payload.get("severity") or "warning"),
                status=str(raw_payload.get("status") or "active"),
                message=str(raw_payload.get("message") or ""),
                scope=str(raw_payload.get("scope")) if raw_payload.get("scope") not in (None, "") else None,
                first_seen_at=str(raw_payload.get("first_seen_at") or cls._now_iso()),
                last_seen_at=str(raw_payload.get("last_seen_at") or cls._now_iso()),
                recovered_at=(
                    str(raw_payload.get("recovered_at"))
                    if raw_payload.get("recovered_at") not in (None, "")
                    else None
                ),
            )
        return cls(records)

    def snapshot(self) -> dict[str, Any]:
        return {
            "records": {
                alert_id: alert.to_payload()
                for alert_id, alert in sorted(self._records.items())
            }
        }

    def evaluate(self, snapshot: dict[str, Any], *, now: datetime | None = None) -> dict[str, list[dict[str, Any]]]:
        current_time = now or datetime.now(UTC)
        now_iso = current_time.isoformat()
        desired = self._build_desired_alerts(snapshot, current_time)
        desired_ids = set(desired)

        for alert_id, desired_alert in desired.items():
            previous = self._records.get(alert_id)
            if previous is None or previous.status == "recovered":
                desired_alert.first_seen_at = now_iso
            else:
                desired_alert.first_seen_at = previous.first_seen_at
            desired_alert.last_seen_at = now_iso
            self._records[alert_id] = desired_alert

        for alert_id, previous in list(self._records.items()):
            if alert_id in desired_ids or previous.status != "active":
                continue
            previous.status = "recovered"
            previous.last_seen_at = now_iso
            previous.recovered_at = now_iso
            self._records[alert_id] = previous

        active = [
            alert.to_payload()
            for alert in self._records.values()
            if alert.status == "active"
        ]
        recovered = [
            alert.to_payload()
            for alert in self._records.values()
            if alert.status == "recovered"
        ]
        active.sort(key=lambda item: (self._severity_rank(str(item.get("severity"))), str(item.get("last_seen_at"))))
        recovered.sort(key=lambda item: str(item.get("recovered_at") or ""), reverse=True)
        return {
            "active": active,
            "recent_recovered": recovered[:RECENT_RECOVERED_LIMIT],
        }

    def _build_desired_alerts(
        self,
        snapshot: dict[str, Any],
        now: datetime,
    ) -> dict[str, AppHealthAlert]:
        alerts: dict[str, AppHealthAlert] = {}
        metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}
        oa_sync = snapshot.get("oa_sync") if isinstance(snapshot.get("oa_sync"), dict) else {}
        workbench = snapshot.get("workbench_read_model") if isinstance(snapshot.get("workbench_read_model"), dict) else {}
        background_jobs = snapshot.get("background_jobs") if isinstance(snapshot.get("background_jobs"), dict) else {}
        dependencies = snapshot.get("dependencies") if isinstance(snapshot.get("dependencies"), dict) else {}
        session = snapshot.get("session") if isinstance(snapshot.get("session"), dict) else {}

        dirty_scope_ages = metrics.get("dirty_scope_age_seconds")
        if not isinstance(dirty_scope_ages, dict):
            dirty_scope_ages = {}
        dirty_scopes = [
            str(scope)
            for scope in list(oa_sync.get("dirty_scopes", []) or [])
            if str(scope).strip()
        ]
        for scope in dirty_scopes:
            age_seconds = self._as_float(dirty_scope_ages.get(scope), default=self._as_float(oa_sync.get("lag_seconds")))
            if age_seconds < DIRTY_SCOPE_WARNING_SECONDS:
                continue
            severity = "critical" if age_seconds >= DIRTY_SCOPE_CRITICAL_SECONDS else "warning"
            self._put_alert(
                alerts,
                kind="oa_sync_dirty_scope",
                severity=severity,
                scope=scope,
                message=f"OA 数据变更已等待 {int(age_seconds)} 秒，关联台读模型尚未刷新。",
                now=now,
            )

        rebuild_seconds = self._as_float(metrics.get("workbench_rebuild_running_seconds_max"))
        if str(workbench.get("status") or "") == "rebuilding" and rebuild_seconds >= WORKBENCH_REBUILD_WARNING_SECONDS:
            self._put_alert(
                alerts,
                kind="workbench_rebuild_long_running",
                severity="warning",
                scope="workbench_read_model",
                message=f"关联台读模型重建已运行 {int(rebuild_seconds)} 秒。",
                now=now,
            )

        jobs = background_jobs.get("jobs") if isinstance(background_jobs.get("jobs"), list) else []
        for job in jobs:
            if not isinstance(job, dict) or str(job.get("status") or "") != "running":
                continue
            duration_seconds = self._seconds_since(job.get("started_at") or job.get("created_at"), now)
            if duration_seconds < BACKGROUND_JOB_WARNING_SECONDS:
                continue
            job_label = str(job.get("label") or job.get("type") or job.get("job_id") or "后台任务")
            self._put_alert(
                alerts,
                kind="background_job_long_running",
                severity="warning",
                scope=str(job.get("job_id") or job_label),
                message=f"{job_label} 已运行 {int(duration_seconds)} 秒。",
                now=now,
            )

        for dependency_name, dependency in dependencies.items():
            if not isinstance(dependency, dict) or dependency.get("status") != "unavailable":
                continue
            message = str(dependency.get("message") or f"{dependency_name} 不可用。")
            self._put_alert(
                alerts,
                kind="dependency_unavailable",
                severity="critical",
                scope=str(dependency_name),
                message=message,
                now=now,
            )

        if session.get("status") == "blocked":
            self._put_alert(
                alerts,
                kind="session_blocked",
                severity="critical",
                scope="oa_session",
                message="OA 登录态或权限不可用，当前用户操作应被阻断。",
                now=now,
            )
        return alerts

    @classmethod
    def _put_alert(
        cls,
        alerts: dict[str, AppHealthAlert],
        *,
        kind: str,
        severity: str,
        scope: str | None,
        message: str,
        now: datetime,
    ) -> None:
        alert_id = cls._alert_id(kind, scope)
        now_iso = now.isoformat()
        alerts[alert_id] = AppHealthAlert(
            alert_id=alert_id,
            kind=kind,
            severity=severity,
            status="active",
            message=message,
            scope=scope,
            first_seen_at=now_iso,
            last_seen_at=now_iso,
        )

    @staticmethod
    def _alert_id(kind: str, scope: str | None) -> str:
        raw = f"{kind}:{scope or ''}"
        return f"app_health_{sha1(raw.encode('utf-8')).hexdigest()[:16]}"

    @staticmethod
    def _severity_rank(severity: str) -> int:
        return {"critical": 0, "warning": 1, "info": 2}.get(severity, 3)

    @staticmethod
    def _seconds_since(value: object, now: datetime) -> float:
        if not value:
            return 0.0
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return max(0.0, (now - parsed.astimezone(UTC)).total_seconds())

    @staticmethod
    def _as_float(value: object, *, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(UTC).isoformat()
