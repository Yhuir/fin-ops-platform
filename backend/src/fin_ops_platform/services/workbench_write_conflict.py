from __future__ import annotations

from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any


DEFAULT_WORKBENCH_WRITE_CONFLICT_MESSAGE = "工作台数据已变化，请刷新后重试。"


@dataclass(frozen=True)
class WorkbenchWriteConflict(ValueError):
    action: str
    reason: str
    expected: dict[str, Any] = field(default_factory=dict)
    actual: dict[str, Any] = field(default_factory=dict)
    message: str = DEFAULT_WORKBENCH_WRITE_CONFLICT_MESSAGE
    status_code: int = int(HTTPStatus.CONFLICT)

    def __post_init__(self) -> None:
        ValueError.__init__(self, self.message)

    def to_response_payload(self) -> dict[str, Any]:
        return {
            "status_code": self.status_code,
            "payload": {
                "error": "workbench_write_conflict",
                "message": self.message,
                "conflict": {
                    "action": self.action,
                    "reason": self.reason,
                    "expected": dict(self.expected),
                    "actual": dict(self.actual),
                },
            },
        }
