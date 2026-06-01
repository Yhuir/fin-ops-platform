from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from fin_ops_platform.services.turnover_ledger_extra_service import (
    TurnoverLedgerExtraService,
    TurnoverLedgerExtraValidationError,
)


class TurnoverLedgerExtraServiceTests(unittest.TestCase):
    def test_empty_snapshot_restores_empty_service(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        self.assertEqual(service.snapshot(), {"version": 1, "extras": []})

    def test_upsert_new_relation_extra_normalizes_fields(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        extra = service.upsert(
            " turnover_rel_001 ",
            {
                "interest_rate_type": " annual ",
                "interest_rate_value": Decimal("0.06"),
                "interest_paid_amount": "15.125",
                "interest_paid_date": "2026-05-12",
                "interest_payment_method": "  银行转账  ",
                "note": "  首次录入  ",
            },
            actor=" YNSYLP005 ",
        )

        self.assertEqual(extra["relation_id"], "turnover_rel_001")
        self.assertEqual(extra["interest_rate_type"], "annual")
        self.assertEqual(extra["interest_rate_value"], "0.060000")
        self.assertEqual(extra["interest_paid_amount"], "15.13")
        self.assertEqual(extra["interest_paid_date"], "2026-05-12")
        self.assertEqual(extra["interest_payment_method"], "银行转账")
        self.assertEqual(extra["note"], "首次录入")
        self.assertEqual(extra["updated_by"], "YNSYLP005")
        datetime.fromisoformat(str(extra["updated_at"]))
        self.assertEqual(service.get("turnover_rel_001"), extra)

    def test_upsert_updates_existing_extra_and_preserves_missing_fields(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)
        created = service.upsert(
            "turnover_rel_001",
            {
                "interest_rate_type": "annual",
                "interest_rate_value": "0.060000",
                "interest_paid_amount": "10.00",
                "note": "old",
            },
            actor="creator",
        )

        updated = service.upsert(
            "turnover_rel_001",
            {"note": " new "},
            actor="editor",
        )

        self.assertEqual(updated["interest_rate_type"], "annual")
        self.assertEqual(updated["interest_rate_value"], "0.060000")
        self.assertEqual(updated["interest_paid_amount"], "10.00")
        self.assertEqual(updated["note"], "new")
        self.assertEqual(updated["updated_by"], "editor")
        self.assertNotEqual(updated["updated_at"], created["updated_at"])

    def test_normalize_update_matches_upsert_shape_without_mutating_snapshot(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)
        service.upsert(
            "turnover_rel_001",
            {
                "interest_rate_type": "annual",
                "interest_rate_value": "0.060000",
                "interest_paid_amount": "10.00",
                "note": "old",
            },
            actor="creator",
        )
        before_snapshot = service.snapshot()

        normalized = service.normalize_update(
            "turnover_rel_001",
            {"note": " new ", "interest_paid_amount": "12.345"},
            actor="editor",
        )

        self.assertEqual(normalized["interest_rate_type"], "annual")
        self.assertEqual(normalized["interest_rate_value"], "0.060000")
        self.assertEqual(normalized["interest_paid_amount"], "12.35")
        self.assertEqual(normalized["note"], "new")
        self.assertEqual(normalized["updated_by"], "editor")
        self.assertEqual(service.snapshot(), before_snapshot)

    def test_none_interest_rate_normalizes_to_zero(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        extra = service.upsert(
            "turnover_rel_001",
            {
                "interest_rate_type": "none",
                "interest_rate_value": "0.99",
                "interest_paid_amount": "",
                "interest_paid_date": "",
            },
            actor="user",
        )

        self.assertEqual(extra["interest_rate_type"], "none")
        self.assertEqual(extra["interest_rate_value"], "0.000000")
        self.assertEqual(extra["interest_paid_amount"], "0.00")
        self.assertIsNone(extra["interest_paid_date"])

    def test_invalid_interest_rate_type_is_rejected(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {"interest_rate_type": "weekly"},
                actor="user",
            )

    def test_negative_amount_or_rate_is_rejected(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {"interest_rate_value": "-0.01"},
                actor="user",
            )

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {"interest_paid_amount": "-1.00"},
                actor="user",
            )

    def test_invalid_date_is_rejected(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {"interest_paid_date": "2026-02-30"},
                actor="user",
            )

    def test_empty_relation_id_and_overlong_text_are_rejected(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(" ", {}, actor="user")

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {"note": "x" * 501},
                actor="user",
            )

        with self.assertRaises(TurnoverLedgerExtraValidationError):
            service.upsert(
                "turnover_rel_001",
                {},
                actor="x" * 65,
            )

    def test_remove_deletes_existing_extra(self) -> None:
        service = TurnoverLedgerExtraService.from_snapshot(None)
        service.upsert("turnover_rel_001", {"note": "delete me"}, actor="user")

        service.remove("turnover_rel_001", actor="user")

        self.assertIsNone(service.get("turnover_rel_001"))
        self.assertEqual(service.snapshot(), {"version": 1, "extras": []})


if __name__ == "__main__":
    unittest.main()
