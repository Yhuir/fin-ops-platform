from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from threading import RLock
from typing import Any


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class WorkbenchMatchingDirtyScopeService:
    def __init__(self, *, dirty_scopes: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._dirty_scopes = self._normalize_dirty_scopes(dirty_scopes or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchMatchingDirtyScopeService":
        if not snapshot:
            return cls()
        dirty_scopes = snapshot.get("dirty_scopes")
        return cls(dirty_scopes=dirty_scopes if isinstance(dirty_scopes, dict) else {})

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"dirty_scopes": deepcopy(self._dirty_scopes)}

    def mark_dirty(self, scope_months: list[str], *, reason: str, error: str | None = None) -> list[str]:
        normalized_months = self._normalize_months(scope_months)
        if not normalized_months:
            return []
        timestamp = self._timestamp()
        with self._lock:
            for month in normalized_months:
                existing = self._dirty_scopes.get(month, {})
                reasons = [
                    str(item).strip()
                    for item in list(existing.get("reasons") or [])
                    if str(item).strip()
                ]
                resolved_reason = str(reason or "").strip() or "unknown"
                if resolved_reason not in reasons:
                    reasons.append(resolved_reason)
                self._dirty_scopes[month] = {
                    "scope_month": month,
                    "reasons": reasons,
                    "last_error": str(error or existing.get("last_error") or ""),
                    "attempt_count": int(existing.get("attempt_count", 0) or 0),
                    "created_at": str(existing.get("created_at") or timestamp),
                    "updated_at": timestamp,
                }
        return normalized_months

    def take_dirty_scopes(self, *, limit: int | None = None) -> list[str]:
        with self._lock:
            months = sorted(self._dirty_scopes.keys())
            if limit is not None:
                months = months[: max(int(limit), 0)]
            for month in months:
                self._dirty_scopes.pop(month, None)
            return months

    def requeue_dirty_scopes(self, scope_months: list[str], *, reason: str, error: str) -> list[str]:
        normalized_months = self.mark_dirty(scope_months, reason=reason, error=error)
        with self._lock:
            for month in normalized_months:
                entry = self._dirty_scopes.get(month)
                if isinstance(entry, dict):
                    entry["attempt_count"] = int(entry.get("attempt_count", 0) or 0) + 1
                    entry["updated_at"] = self._timestamp()
        return normalized_months

    def list_dirty_scopes(self) -> list[dict[str, Any]]:
        with self._lock:
            return [deepcopy(self._dirty_scopes[month]) for month in sorted(self._dirty_scopes)]

    @classmethod
    def _normalize_dirty_scopes(cls, dirty_scopes: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for scope_month, entry in dirty_scopes.items():
            month = str(scope_month or entry.get("scope_month") if isinstance(entry, dict) else "").strip()
            if not MONTH_RE.match(month) or not isinstance(entry, dict):
                continue
            normalized[month] = {
                "scope_month": month,
                "reasons": [
                    str(item).strip()
                    for item in list(entry.get("reasons") or [])
                    if str(item).strip()
                ],
                "last_error": str(entry.get("last_error") or ""),
                "attempt_count": int(entry.get("attempt_count", 0) or 0),
                "created_at": str(entry.get("created_at") or cls._timestamp()),
                "updated_at": str(entry.get("updated_at") or cls._timestamp()),
            }
        return normalized

    @staticmethod
    def _normalize_months(scope_months: list[str]) -> list[str]:
        months = [
            str(month).strip()
            for month in list(scope_months or [])
            if MONTH_RE.match(str(month).strip())
        ]
        return sorted(dict.fromkeys(months))

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
