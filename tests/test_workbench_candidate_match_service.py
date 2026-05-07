import unittest

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService


class WorkbenchCandidateMatchServiceTests(unittest.TestCase):
    def test_upsert_candidate_is_idempotent_for_same_stable_key(self) -> None:
        service = WorkbenchCandidateMatchService()

        first = service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_bank_invoice",
                "status": "needs_review",
                "confidence": "medium",
                "rule_code": "same_amount",
                "row_ids": ["oa-001", "bank-001", "invoice-001"],
                "oa_row_ids": ["oa-001"],
                "bank_row_ids": ["bank-001"],
                "invoice_row_ids": ["invoice-001"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "初次候选",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-06T10:00:00+00:00",
                "source_versions": {"workbench": "v1"},
            }
        )
        second = service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_bank_invoice",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "same_amount",
                "row_ids": ["invoice-001", "oa-001", "bank-001"],
                "oa_row_ids": ["oa-001"],
                "bank_row_ids": ["bank-001"],
                "invoice_row_ids": ["invoice-001"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "重新生成后自动闭合",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-06T11:00:00+00:00",
                "source_versions": {"workbench": "v2"},
            }
        )

        self.assertEqual(second["candidate_id"], first["candidate_id"])
        self.assertEqual(second["candidate_key"], first["candidate_key"])
        self.assertEqual(second["status"], "auto_closed")
        self.assertEqual(second["confidence"], "high")
        self.assertEqual(len(service.list_candidates_by_month("2026-05")), 1)

    def test_list_candidates_by_month_returns_only_matching_month(self) -> None:
        service = WorkbenchCandidateMatchService()
        service.upsert_candidate(self._candidate("2026-04", "rule-a", ["bank-001"]))
        may_candidate = service.upsert_candidate(self._candidate("2026-05", "rule-a", ["bank-002"]))

        self.assertEqual(service.list_candidates_by_month("2026-05"), [may_candidate])
        self.assertEqual(service.list_candidates_by_month("2026-06"), [])

    def test_delete_month_removes_only_that_month(self) -> None:
        service = WorkbenchCandidateMatchService()
        april = service.upsert_candidate(self._candidate("2026-04", "rule-a", ["bank-001"]))
        may = service.upsert_candidate(self._candidate("2026-05", "rule-a", ["bank-002"]))

        deleted_keys = service.delete_month("2026-05")

        self.assertEqual(deleted_keys, [may["candidate_key"]])
        self.assertEqual(service.list_candidates_by_month("2026-04"), [april])
        self.assertEqual(service.list_candidates_by_month("2026-05"), [])

    def test_clear_removes_all_candidates(self) -> None:
        service = WorkbenchCandidateMatchService()
        first = service.upsert_candidate(self._candidate("2026-04", "rule-a", ["bank-001"]))
        second = service.upsert_candidate(self._candidate("2026-05", "rule-a", ["bank-002"]))

        deleted_keys = service.clear()

        self.assertCountEqual(deleted_keys, [first["candidate_key"], second["candidate_key"]])
        self.assertEqual(service.snapshot(), {"candidates": {}})

    def test_snapshot_from_snapshot_round_trip_deepcopies_candidates(self) -> None:
        service = WorkbenchCandidateMatchService()
        candidate = service.upsert_candidate(
            {
                **self._candidate("2026-05", "rule-a", ["oa-001", "bank-001"]),
                "conflict_candidate_keys": ["candidate:conflict"],
                "source_versions": {"oa": "sync-001", "bank": "import-001"},
            }
        )

        snapshot = service.snapshot()
        restored = WorkbenchCandidateMatchService.from_snapshot(snapshot)
        snapshot["candidates"][candidate["candidate_key"]]["row_ids"].append("mutated")
        loaded = restored.list_candidates_by_month("2026-05")
        loaded[0]["row_ids"].append("mutated-again")

        self.assertEqual(restored.snapshot(), {"candidates": {candidate["candidate_key"]: candidate}})

    def test_candidate_key_is_stable_when_row_id_order_changes(self) -> None:
        service = WorkbenchCandidateMatchService()

        first_key = service.build_candidate_key(
            scope_month="2026-05",
            rule_code="same_amount",
            row_ids=["oa-001", "bank-001", "invoice-001"],
        )
        second_key = service.build_candidate_key(
            scope_month="2026-05",
            rule_code="same_amount",
            row_ids=["invoice-001", "oa-001", "bank-001"],
        )
        different_rule_key = service.build_candidate_key(
            scope_month="2026-05",
            rule_code="amount_delta",
            row_ids=["invoice-001", "oa-001", "bank-001"],
        )

        self.assertEqual(first_key, second_key)
        self.assertNotEqual(first_key, different_rule_key)

    def _candidate(self, month: str, rule_code: str, row_ids: list[str]) -> dict[str, object]:
        return {
            "scope_month": month,
            "candidate_type": "oa_bank_invoice",
            "status": "needs_review",
            "confidence": "medium",
            "rule_code": rule_code,
            "row_ids": row_ids,
            "oa_row_ids": [row_id for row_id in row_ids if row_id.startswith("oa-")],
            "bank_row_ids": [row_id for row_id in row_ids if row_id.startswith("bank-")],
            "invoice_row_ids": [row_id for row_id in row_ids if row_id.startswith("invoice-")],
            "amount": "100.00",
            "amount_delta": "0.00",
            "explanation": "候选说明",
            "conflict_candidate_keys": [],
            "generated_at": "2026-05-06T10:00:00+00:00",
            "source_versions": {},
        }


if __name__ == "__main__":
    unittest.main()
