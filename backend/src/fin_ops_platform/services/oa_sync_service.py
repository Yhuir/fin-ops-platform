from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Iterable


@dataclass(slots=True)
class OASyncStatus:
    status: str = "synced"
    message: str = "OA 已同步"
    dirty_scopes: list[str] = field(default_factory=list)
    last_seen_change_at: str | None = None
    last_synced_at: str | None = None
    lag_seconds: int = 0
    failed_event_count: int = 0
    version: int = 0

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "message": self.message,
            "dirty_scopes": list(self.dirty_scopes),
            "last_seen_change_at": self.last_seen_change_at,
            "last_synced_at": self.last_synced_at,
            "lag_seconds": self.lag_seconds,
            "failed_event_count": self.failed_event_count,
            "version": self.version,
        }


class OASyncService:
    def __init__(self) -> None:
        self._lock = RLock()
        self._dirty_scopes: set[str] = set()
        self._status = OASyncStatus(last_synced_at=self._now())

    def status_payload(self) -> dict[str, Any]:
        with self._lock:
            self._refresh_lag_locked()
            return self._status.to_payload()

    def mark_changed(self, scopes: Iterable[str], *, reason: str = "oa_changed") -> dict[str, Any]:
        normalized_scopes = self._normalize_scopes(scopes)
        if not normalized_scopes:
            normalized_scopes = ["all"]
        if any(scope != "all" for scope in normalized_scopes):
            normalized_scopes = sorted({*normalized_scopes, "all"})
        now = self._now()
        with self._lock:
            self._dirty_scopes.update(normalized_scopes)
            self._status.status = "refreshing"
            self._status.message = "OA 有更新，关联台刷新中。"
            self._status.dirty_scopes = sorted(self._dirty_scopes)
            self._status.last_seen_change_at = now
            self._status.version += 1
            self._refresh_lag_locked()
            payload = self._status.to_payload()
        return deepcopy(payload)

    def take_dirty_scopes(self) -> list[str]:
        with self._lock:
            scopes = sorted(self._dirty_scopes)
            self._dirty_scopes.clear()
            self._status.dirty_scopes = []
            return scopes

    def mark_synced(self, scopes: Iterable[str], *, message: str = "OA 已同步") -> dict[str, Any]:
        normalized_scopes = self._normalize_scopes(scopes)
        now = self._now()
        with self._lock:
            self._status.status = "synced"
            self._status.message = message
            self._status.dirty_scopes = sorted(self._dirty_scopes)
            self._status.last_synced_at = now
            self._status.lag_seconds = 0
            self._status.version += 1
            payload = self._status.to_payload()
        return deepcopy(payload)

    def mark_error(self, message: str, *, scopes: Iterable[str] = ()) -> dict[str, Any]:
        normalized_scopes = self._normalize_scopes(scopes)
        with self._lock:
            self._status.status = "error"
            self._status.message = message or "OA 同步失败"
            self._status.dirty_scopes = sorted(self._dirty_scopes)
            self._status.failed_event_count += 1
            self._status.version += 1
            self._refresh_lag_locked()
            payload = self._status.to_payload()
        return deepcopy(payload)

    def _refresh_lag_locked(self) -> None:
        if not self._status.last_seen_change_at or self._status.status == "synced":
            self._status.lag_seconds = 0
            return
        try:
            seen = datetime.fromisoformat(self._status.last_seen_change_at)
        except ValueError:
            self._status.lag_seconds = 0
            return
        self._status.lag_seconds = max(0, int((datetime.now(UTC) - seen).total_seconds()))

    @staticmethod
    def _normalize_scopes(scopes: Iterable[str]) -> list[str]:
        normalized = {
            str(scope).strip()
            for scope in list(scopes or [])
            if str(scope).strip()
        }
        return sorted(normalized)

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
