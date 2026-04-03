from decimal import Decimal
import unittest

from fin_ops_platform.services.audit import AuditTrailService


class AuditTrailServiceTests(unittest.TestCase):
    def test_record_action_keeps_amounts_and_metadata_for_manual_finance_actions(self) -> None:
        service = AuditTrailService()

        entry = service.record_action(
            actor_id="user_finance_01",
            action="manual_reconciliation_created",
            entity_type="reconciliation_case",
            entity_id="rc_001",
            before_amount=Decimal("0.00"),
            after_amount=Decimal("100.00"),
            metadata={"case_type": "manual", "project_id": "proj_001"},
        )

        self.assertEqual(entry.actor_id, "user_finance_01")
        self.assertEqual(entry.before_amount, Decimal("0.00"))
        self.assertEqual(entry.after_amount, Decimal("100.00"))
        self.assertEqual(entry.metadata["project_id"], "proj_001")


if __name__ == "__main__":
    unittest.main()
