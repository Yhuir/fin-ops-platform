from decimal import Decimal
import unittest

from fin_ops_platform.services.audit import AuditTrailService


class FakeAuditRepository:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def append_operation_event(self, event: dict[str, object]) -> dict[str, object]:
        self.events.append(event)
        return {"id": "10000000-0000-4000-8000-000000000001"}


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

    def test_record_action_persists_durable_event_and_removes_sensitive_metadata(self) -> None:
        repository = FakeAuditRepository()
        service = AuditTrailService(repository)

        entry = service.record_action(
            actor_id="YNSYLP005",
            action="manual_reconciliation_created",
            entity_type="reconciliation_case",
            entity_id="rc_001",
            before_amount=Decimal("0.00"),
            after_amount=Decimal("100.00"),
            metadata={
                "event_type": "reconciliation.created",
                "page_key": "reconciliation-workbench",
                "password": "must-not-persist",
                "nested": {"token": "must-not-persist", "kept": "value"},
            },
        )

        self.assertEqual(entry.id, "10000000-0000-4000-8000-000000000001")
        self.assertEqual(service.list_entries(), [])
        event = repository.events[0]
        self.assertEqual(event["actor_id"], "YNSYLP005")
        self.assertEqual(event["page_key"], "reconciliation-workbench")
        payload = event["payload"]
        self.assertIsInstance(payload, dict)
        assert isinstance(payload, dict)
        self.assertEqual(payload["before"], {"amount": "0.00"})
        self.assertEqual(payload["after"], {"amount": "100.00"})
        metadata = payload["metadata"]
        self.assertNotIn("password", metadata)
        self.assertEqual(metadata["nested"], {"kept": "value"})


if __name__ == "__main__":
    unittest.main()
