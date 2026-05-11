import unittest

from fin_ops_platform.services.workbench_candidate_match_service import (
    CANDIDATE_MATCH_SCHEMA_VERSION,
    WorkbenchCandidateMatchService,
)


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
        self.assertEqual(
            service.snapshot(),
            {"schema_version": CANDIDATE_MATCH_SCHEMA_VERSION, "candidates": {}, "scope_runs": {}},
        )

    def test_snapshot_from_snapshot_round_trip_deepcopies_candidates(self) -> None:
        service = WorkbenchCandidateMatchService()
        candidate = service.upsert_candidate(
            {
                **self._candidate("2026-05", "rule-a", ["oa-001", "bank-001"]),
                "conflict_candidate_keys": ["candidate:conflict"],
                "source_versions": {"oa": "sync-001", "bank": "import-001"},
                "special_metadata": {"evidence": {"score": 101, "strong": ["counterparty_match"]}},
            }
        )

        snapshot = service.snapshot()
        restored = WorkbenchCandidateMatchService.from_snapshot(snapshot)
        snapshot["candidates"][candidate["candidate_key"]]["row_ids"].append("mutated")
        loaded = restored.list_candidates_by_month("2026-05")
        loaded[0]["row_ids"].append("mutated-again")

        self.assertEqual(
            restored.snapshot(),
            {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "candidates": {candidate["candidate_key"]: candidate},
                "scope_runs": {},
            },
        )

    def test_from_snapshot_upgrades_candidates_from_old_schema_versions(self) -> None:
        service = WorkbenchCandidateMatchService()
        candidate = service.upsert_candidate(self._candidate("2026-05", "rule-a", ["oa-001", "bank-001"]))
        snapshot = service.snapshot()
        snapshot["candidates"][candidate["candidate_key"]]["schema_version"] = "old-schema"

        restored = WorkbenchCandidateMatchService.from_snapshot(snapshot)

        restored_candidate = restored.list_candidates_by_month("2026-05")[0]
        self.assertEqual(restored_candidate["schema_version"], CANDIDATE_MATCH_SCHEMA_VERSION)
        self.assertEqual(restored_candidate["candidate_key"], candidate["candidate_key"])
        self.assertEqual(restored_candidate["status"], "needs_review")
        self.assertEqual(restored_candidate["consumed_by_case_id"], "")
        self.assertEqual(restored_candidate["consumed_by_relation_case_id"], "")
        self.assertEqual(restored_candidate["suppressed_reason"], "")
        self.assertEqual(restored_candidate["exception_preview"], {})

    def test_consumed_and_suppressed_candidates_are_persisted_and_restored(self) -> None:
        service = WorkbenchCandidateMatchService()
        first = service.upsert_candidate(self._candidate("2026-05", "rule-a", ["bank-001"]))
        second = service.upsert_candidate(self._candidate("2026-05", "rule-b", ["bank-002"]))
        service.mark_scope_processed(
            "2026-05",
            source_versions={"rules": "v1"},
            candidate_count=2,
            request_id="req-001",
            reason="test",
        )

        consumed = service.mark_candidates_consumed(
            candidate_keys=[first["candidate_key"]],
            consumed_by_case_id="WEX-000001",
            consumed_by_relation_case_id="CASE-000001",
        )
        suppressed = service.mark_candidates_suppressed(
            row_ids=["bank-002"],
            suppressed_reason="active_exception_case",
            consumed_by_case_id="WEX-000002",
            exception_preview={"scenario_code": "pending_invoice", "available_action_codes": ["attach_invoice"]},
        )

        self.assertEqual(consumed[0]["status"], "consumed")
        self.assertEqual(consumed[0]["consumed_by_case_id"], "WEX-000001")
        self.assertEqual(consumed[0]["consumed_by_relation_case_id"], "CASE-000001")
        self.assertEqual(suppressed[0]["status"], "suppressed")
        self.assertEqual(suppressed[0]["suppressed_reason"], "active_exception_case")
        self.assertEqual(
            suppressed[0]["exception_preview"],
            {"scenario_code": "pending_invoice", "available_action_codes": ["attach_invoice"]},
        )
        self.assertTrue(service.is_scope_fresh("2026-05", source_versions={"rules": "v1"}))

        restored = WorkbenchCandidateMatchService.from_snapshot(service.snapshot())
        restored_statuses = {
            candidate["candidate_key"]: candidate
            for candidate in restored.list_candidates_by_month("2026-05")
        }
        self.assertEqual(restored_statuses[first["candidate_key"]]["status"], "consumed")
        self.assertEqual(restored_statuses[second["candidate_key"]]["status"], "suppressed")

    def test_consumed_and_suppressed_statuses_normalize_from_snapshot(self) -> None:
        snapshot = {
            "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
            "candidates": {},
            "scope_runs": {},
        }
        consumed = self._candidate("2026-05", "rule-consumed", ["bank-001"])
        consumed["status"] = "consumed"
        consumed["consumed_by_case_id"] = "WEX-000001"
        suppressed = self._candidate("2026-05", "rule-suppressed", ["bank-002"])
        suppressed["status"] = "suppressed"
        suppressed["suppressed_reason"] = "active_pair_relation"
        for payload in (consumed, suppressed):
            key = WorkbenchCandidateMatchService.build_candidate_key(
                scope_month=str(payload["scope_month"]),
                rule_code=str(payload["rule_code"]),
                row_ids=list(payload["row_ids"]),
            )
            payload["candidate_key"] = key
            payload["candidate_id"] = key
            payload["schema_version"] = CANDIDATE_MATCH_SCHEMA_VERSION
            snapshot["candidates"][key] = payload

        restored = WorkbenchCandidateMatchService.from_snapshot(snapshot)

        self.assertEqual(
            [candidate["status"] for candidate in restored.list_candidates_by_month("2026-05")],
            ["consumed", "suppressed"],
        )

    def test_scope_freshness_requires_current_schema_and_matching_source_versions(self) -> None:
        service = WorkbenchCandidateMatchService()
        source_versions = {"workbench": "v1", "rules": "r1"}

        self.assertFalse(service.is_scope_fresh("2026-05", source_versions=source_versions))

        service.mark_scope_processed(
            "2026-05",
            source_versions=source_versions,
            candidate_count=0,
            request_id="req-001",
            reason="test",
        )

        self.assertTrue(service.is_scope_fresh("2026-05", source_versions=source_versions))
        self.assertFalse(service.is_scope_fresh("2026-05", source_versions={"workbench": "v2", "rules": "r1"}))
        self.assertEqual(service.stale_scope_months(["2026-05", "2026-06"], source_versions=source_versions), ["2026-06"])

    def test_scope_freshness_allows_persisted_source_versions_to_have_newer_metadata_fields(self) -> None:
        service = WorkbenchCandidateMatchService()
        service.mark_scope_processed(
            "2026-05",
            source_versions={
                "workbench_matching_rules_version": "matching-v1",
                "workbench_special_rules_version": "special-v1",
                "workbench_exception_rules_version": "exception-v1",
            },
            candidate_count=0,
            request_id="req-001",
            reason="test",
        )

        self.assertTrue(
            service.is_scope_fresh(
                "2026-05",
                source_versions={"workbench_matching_rules_version": "matching-v1"},
            )
        )
        self.assertFalse(
            service.is_scope_fresh(
                "2026-05",
                source_versions={"workbench_matching_rules_version": "matching-v2"},
            )
        )

    def test_from_snapshot_discards_old_scope_run_schema_versions(self) -> None:
        restored = WorkbenchCandidateMatchService.from_snapshot(
            {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "candidates": {},
                "scope_runs": {
                    "2026-05": {
                        "schema_version": "old-schema",
                        "source_versions": {"workbench": "v1"},
                        "candidate_count": 0,
                    }
                },
            }
        )

        self.assertFalse(restored.is_scope_fresh("2026-05", source_versions={"workbench": "v1"}))

    def test_delete_month_and_clear_remove_scope_run_freshness(self) -> None:
        service = WorkbenchCandidateMatchService()
        service.upsert_candidate(self._candidate("2026-05", "rule-a", ["bank-001"]))
        service.mark_scope_processed(
            "2026-05",
            source_versions={"workbench": "v1"},
            candidate_count=1,
            request_id="req-001",
            reason="test",
        )

        service.delete_month("2026-05")
        self.assertFalse(service.is_scope_fresh("2026-05", source_versions={"workbench": "v1"}))

        service.mark_scope_processed(
            "2026-06",
            source_versions={"workbench": "v1"},
            candidate_count=0,
            request_id="req-002",
            reason="test",
        )
        service.clear()
        self.assertFalse(service.is_scope_fresh("2026-06", source_versions={"workbench": "v1"}))

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
