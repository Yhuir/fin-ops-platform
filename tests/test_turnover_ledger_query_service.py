from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.read_models import (
    _turnover_ledger_family_summary,
    _turnover_ledger_summary,
)
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


class FakeRepository:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object] | None:
        self.calls.append(dict(kwargs))
        return self.payload


class TurnoverLedgerQueryServiceTests(unittest.TestCase):
    def test_read_model_summary_uses_explicit_group_amount_fields(self) -> None:
        rows = [
            {
                "relation_id": "group-personal",
                "family": "personal",
                "pending_repayment_amount": "1000.00",
                "repaid_amount": "200.00",
                "pending_collection_amount": "500.00",
                "collected_amount": "300.00",
                "closed_amount": "0.00",
                "balance_amount": "1500.00",
            }
        ]

        summary = _turnover_ledger_summary(rows)
        family_summary = _turnover_ledger_family_summary("personal", rows)

        self.assertEqual(summary["pending_repayment_amount"], "1000.00")
        self.assertEqual(summary["repaid_amount"], "200.00")
        self.assertEqual(summary["pending_collection_amount"], "500.00")
        self.assertEqual(summary["collected_amount"], "300.00")
        self.assertEqual(family_summary["pending_repayment_amount"], "1000.00")
        self.assertEqual(family_summary["repaid_amount"], "200.00")
        self.assertEqual(family_summary["pending_collection_amount"], "500.00")
        self.assertEqual(family_summary["collected_amount"], "300.00")
        self.assertEqual(family_summary["pending_amount"], "1500.00")

    def test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "stale"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {"turnover_ledger_schema_version": "old"},
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "new"},
            legacy_payload_builder=lambda **_kwargs: {"rows": [], "pagination": {"total": 0}},
            settings_provider=lambda: {"postgres_required": True},
        )

        payload = service.list_ledger(family="all", direction="all", status=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertEqual(payload["rows"], [{"relation_id": "stale"}])
        self.assertEqual(queue.enqueued, [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_stale"}])

    def test_fresh_sql_read_model_is_returned_without_legacy_rebuild(self) -> None:
        queue = FakeQueue()
        legacy_calls: list[dict[str, object]] = []
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "fresh"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {"turnover_ledger_schema_version": "same"},
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "same"},
            legacy_payload_builder=lambda **kwargs: legacy_calls.append(dict(kwargs)) or {"rows": []},
            settings_provider=lambda: {"postgres_required": True},
        )

        payload = service.list_ledger(family="company", direction="all", status=None, page=2, page_size=25)

        self.assertEqual(payload["rows"], [{"relation_id": "fresh"}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls[0]["family"], "company")
        self.assertEqual(repository.calls[0]["page"], 2)
        self.assertEqual(queue.enqueued, [])
        self.assertEqual(legacy_calls, [])


if __name__ == "__main__":
    unittest.main()
