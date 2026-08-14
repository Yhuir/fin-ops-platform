from __future__ import annotations

import inspect
import unittest
from typing import Any

from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.pending_invoice_service import (
    PendingInvoiceApplicationService,
    PendingInvoiceQueryService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class FakeOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records_by_id = {record.id: record for record in records}
        self.requested_row_ids: list[list[str]] = []

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized = [str(row_id).strip() for row_id in row_ids if str(row_id).strip()]
        self.requested_row_ids.append(normalized)
        return [self.records_by_id[row_id] for row_id in normalized if row_id in self.records_by_id]


class FakeCanonicalRelationReader:
    def __init__(
        self,
        rows: list[dict[str, object]] | None = None,
        groups: list[dict[str, object]] | None = None,
        *,
        relations: list[dict[str, object]] | None = None,
    ) -> None:
        del rows
        self.relations = [
            self._canonical_relation(group)
            for group in list(groups or [])
            if isinstance(group, dict)
        ]
        self.relations.extend(
            dict(relation) for relation in list(relations or []) if isinstance(relation, dict)
        )
        self.calls: list[list[str]] = []

    @classmethod
    def from_pair_service(
        cls,
        *,
        pair_service: WorkbenchPairRelationService,
        transactions: list[BankTransaction],
        invoices: list[Invoice],
        oa_projection: FakeOAProjection | None = None,
    ) -> "FakeCanonicalRelationReader":
        del transactions, invoices, oa_projection
        return cls(relations=[dict(item) for item in pair_service.list_active_relations()])

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized = [str(row_id).strip() for row_id in row_ids if str(row_id).strip()]
        self.calls.append(normalized)
        wanted = set(normalized)
        return [
            dict(relation)
            for relation in self.relations
            if wanted.intersection(str(item) for item in list(relation.get("row_ids") or []))
            and str(relation.get("relation_status") or "linked") == "linked"
            and str(relation.get("relation_mode") or "") != "unlinked_evidence"
        ]

    @staticmethod
    def _canonical_relation(group: dict[str, object]) -> dict[str, object]:
        payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
        relation = dict(payload)
        relation.setdefault("case_id", group.get("group_id") or payload.get("group_id"))
        relation.setdefault("row_ids", list(payload.get("row_ids") or []))
        relation.setdefault("row_types", list(payload.get("row_types") or []))
        relation.setdefault("relation_mode", payload.get("relation_mode") or "manual_confirmed")
        relation.setdefault("status", "active")
        relation.setdefault("amount_check", dict(payload.get("amount_check") or {}))
        return relation


class PendingInvoiceDirectReadBoundaryTests(unittest.TestCase):
    def test_query_boundary_requires_canonical_relation_reader(self) -> None:
        parameters = inspect.signature(PendingInvoiceQueryService).parameters
        self.assertIn("relation_reader", parameters)
        self.assertNotIn("relation_facade", parameters)

    def test_application_boundary_has_no_relation_projection_dependency(self) -> None:
        parameters = inspect.signature(PendingInvoiceApplicationService).parameters
        self.assertIn("relation_command_service", parameters)
        self.assertNotIn("relation_facade", parameters)


if __name__ == "__main__":
    unittest.main()
