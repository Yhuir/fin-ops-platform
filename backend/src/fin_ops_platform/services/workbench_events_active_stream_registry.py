from __future__ import annotations

from threading import Lock
from typing import Any


class WorkbenchEventsActiveStreamRegistry:
    """Process-local active stream counter for Workbench SSE diagnostics."""

    def __init__(self, *, lock: Any | None = None, active_streams: dict[str, int] | None = None) -> None:
        self._lock = lock if lock is not None else Lock()
        self._active_streams = active_streams if active_streams is not None else {}

    def mark_started(self, scope_key: str) -> None:
        with self._lock:
            self._active_streams[scope_key] = int(self._active_streams.get(scope_key, 0)) + 1

    def mark_closed(self, scope_key: str) -> None:
        with self._lock:
            current_count = int(self._active_streams.get(scope_key, 0))
            if current_count <= 1:
                self._active_streams.pop(scope_key, None)
            else:
                self._active_streams[scope_key] = current_count - 1

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._active_streams)
