from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(slots=True)
class OAApplicationRecord:
    id: str
    month: str
    section: str
    case_id: str | None
    applicant: str
    project_name: str
    apply_type: str
    amount: str
    counterparty_name: str
    reason: str
    relation_code: str
    relation_label: str
    relation_tone: str
    expense_type: str | None = None
    expense_content: str | None = None
    detail_fields: dict[str, str] = field(default_factory=dict)


class OAAdapter(Protocol):
    def list_application_records(self, month: str) -> list[OAApplicationRecord]: ...


class InMemoryOAAdapter:
    def __init__(self, seed_data: dict[str, list[OAApplicationRecord]]) -> None:
        self._seed_data = seed_data

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._seed_data.get(month, []))

    def list_available_months(self) -> list[str]:
        return sorted(self._seed_data.keys())
