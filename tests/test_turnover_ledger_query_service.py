from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.read_models import (
    _turnover_ledger_family_summary,
    _turnover_ledger_summary,
)
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService


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

    def test_query_service_delegates_to_direct_payload_builder(self) -> None:
        calls: list[dict[str, object]] = []
        service = TurnoverLedgerQueryService(
            legacy_payload_builder=lambda **kwargs: calls.append(dict(kwargs)) or {
                "rows": [{"relation_id": "direct"}],
                "pagination": {"page": kwargs["page"], "page_size": kwargs["page_size"], "total": 1},
            },
        )

        payload = service.list_ledger(family="company", direction="all", status=None, page=2, page_size=25)

        self.assertEqual(payload["rows"], [{"relation_id": "direct"}])
        self.assertEqual(calls, [{"family": "company", "direction": "all", "status": None, "page": 2, "page_size": 25}])


if __name__ == "__main__":
    unittest.main()
