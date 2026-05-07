import logging
import unittest

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


class WorkbenchMatchingOrchestratorTests(unittest.TestCase):
    def test_recalculate_one_month_removes_old_candidates_and_upserts_new_candidates(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()
        old_candidate = candidate_service.upsert_candidate(candidate("2026-05", "old_rule", ["bank-old"]))
        candidate_service.upsert_candidate(candidate("2026-04", "other_month", ["bank-other"]))
        rules = StaticRules([candidate("2026-05", "new_rule", ["bank-001"])])

        summary = self._orchestrator(
            row_provider=FakeRowProvider(bank_rows={"2026-05": [row("bank-001")]}),
            candidate_service=candidate_service,
            rules=rules,
        ).run(
            changed_scope_months=["2026-05"],
            reason="unit-test",
            request_id="req-001",
        )

        may_candidates = candidate_service.list_candidates_by_month("2026-05")
        self.assertEqual([item["rule_code"] for item in may_candidates], ["new_rule"])
        self.assertNotEqual(may_candidates[0]["candidate_key"], old_candidate["candidate_key"])
        self.assertEqual(len(candidate_service.list_candidates_by_month("2026-04")), 1)
        self.assertEqual(summary["candidate_count"], 1)
        self.assertEqual(rules.calls[0]["bank_rows"], [row("bank-001")])

    def test_manual_confirmed_relation_row_ids_are_excluded_from_automatic_candidates(self) -> None:
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-manual",
            row_ids=["oa-held", "bank-held", "invoice-held"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-05",
        )
        rules = EchoRules()

        self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={"2026-05": [row("oa-held"), row("oa-free")]},
                bank_rows={"2026-05": [row("bank-held"), row("bank-free")]},
                invoice_rows={"2026-05": [row("invoice-held"), row("invoice-free")]},
            ),
            pair_relation_service=pair_service,
            rules=rules,
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-002")

        self.assertEqual(rules.calls[0]["oa_rows"], [row("oa-free")])
        self.assertEqual(rules.calls[0]["bank_rows"], [row("bank-free")])
        self.assertEqual(rules.calls[0]["invoice_rows"], [row("invoice-free")])

    def test_read_model_for_affected_scope_is_invalidated(self) -> None:
        read_model_service = WorkbenchReadModelService()
        read_model_service.upsert_read_model(scope_key="2026-05", payload={"cached": True})
        read_model_service.upsert_read_model(scope_key="all", payload={"cached": True})

        self._orchestrator(
            row_provider=FakeRowProvider(),
            read_model_service=read_model_service,
            rules=StaticRules([]),
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-003")

        self.assertIsNone(read_model_service.get_read_model("2026-05"))
        self.assertIsNone(read_model_service.get_read_model("all"))

    def test_run_is_idempotent_for_same_scope_and_rows(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()
        orchestrator = self._orchestrator(
            row_provider=FakeRowProvider(bank_rows={"2026-05": [row("bank-001")]}),
            candidate_service=candidate_service,
            rules=StaticRules([candidate("2026-05", "stable_rule", ["bank-001"])]),
        )

        orchestrator.run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-004a")
        first_snapshot = candidate_service.snapshot()
        orchestrator.run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-004b")

        self.assertEqual(candidate_service.snapshot(), first_snapshot)
        self.assertEqual(len(candidate_service.list_candidates_by_month("2026-05")), 1)

    def test_summary_counts_auto_closed_and_conflict_candidates(self) -> None:
        summary = self._orchestrator(
            row_provider=FakeRowProvider(),
            rules=StaticRules(
                [
                    candidate("2026-05", "closed", ["bank-closed"], status="auto_closed"),
                    candidate("2026-05", "conflict", ["bank-conflict"], status="conflict"),
                    candidate("2026-05", "review", ["bank-review"], status="needs_review"),
                ]
            ),
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-005")

        self.assertEqual(summary["request_id"], "req-005")
        self.assertEqual(summary["reason"], "unit-test")
        self.assertEqual(summary["scope_months"], ["2026-05"])
        self.assertEqual(summary["candidate_count"], 3)
        self.assertEqual(summary["auto_closed_count"], 1)
        self.assertEqual(summary["conflict_count"], 1)
        self.assertIsInstance(summary["duration_ms"], int)

    def test_failure_logs_failed_and_re_raises(self) -> None:
        with self.assertLogs("fin_ops_platform.services.workbench_matching_orchestrator", level="INFO") as logs:
            with self.assertRaisesRegex(RuntimeError, "rules failed"):
                self._orchestrator(row_provider=FakeRowProvider(), rules=FailingRules()).run(
                    changed_scope_months=["2026-05"],
                    reason="unit-test",
                    request_id="req-006",
                )

        self.assertTrue(any("workbench_matching.run.failed" in message for message in logs.output))
        self.assertTrue(any("req-006" in message for message in logs.output))

    def _orchestrator(
        self,
        *,
        row_provider: object,
        pair_relation_service: WorkbenchPairRelationService | None = None,
        candidate_service: WorkbenchCandidateMatchService | None = None,
        read_model_service: WorkbenchReadModelService | None = None,
        rules: object,
    ) -> WorkbenchMatchingOrchestrator:
        return WorkbenchMatchingOrchestrator(
            row_provider=row_provider,
            pair_relation_service=pair_relation_service or WorkbenchPairRelationService(),
            candidate_match_service=candidate_service or WorkbenchCandidateMatchService(),
            read_model_service=read_model_service or WorkbenchReadModelService(),
            rules=rules,
            logger=logging.getLogger("fin_ops_platform.services.workbench_matching_orchestrator"),
        )


class FakeRowProvider:
    def __init__(
        self,
        *,
        oa_rows: dict[str, list[dict[str, object]]] | None = None,
        bank_rows: dict[str, list[dict[str, object]]] | None = None,
        invoice_rows: dict[str, list[dict[str, object]]] | None = None,
    ) -> None:
        self.oa_rows = oa_rows or {}
        self.bank_rows = bank_rows or {}
        self.invoice_rows = invoice_rows or {}

    def get_oa_rows(self, scope_month: str) -> list[dict[str, object]]:
        return list(self.oa_rows.get(scope_month, []))

    def get_bank_rows(self, scope_month: str) -> list[dict[str, object]]:
        return list(self.bank_rows.get(scope_month, []))

    def get_invoice_rows(self, scope_month: str) -> list[dict[str, object]]:
        return list(self.invoice_rows.get(scope_month, []))


class StaticRules:
    def __init__(self, candidates: list[dict[str, object]]) -> None:
        self.candidates = candidates
        self.calls: list[dict[str, object]] = []

    def generate_candidates(
        self,
        scope_month: str,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        invoice_rows: list[dict[str, object]],
        *,
        settings: dict[str, object] | None = None,
        source_versions: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "scope_month": scope_month,
                "oa_rows": oa_rows,
                "bank_rows": bank_rows,
                "invoice_rows": invoice_rows,
                "settings": settings or {},
                "source_versions": source_versions or {},
            }
        )
        return list(self.candidates)


class EchoRules(StaticRules):
    def __init__(self) -> None:
        super().__init__([])

    def generate_candidates(
        self,
        scope_month: str,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        invoice_rows: list[dict[str, object]],
        *,
        settings: dict[str, object] | None = None,
        source_versions: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        self.calls.append(
            {
                "scope_month": scope_month,
                "oa_rows": oa_rows,
                "bank_rows": bank_rows,
                "invoice_rows": invoice_rows,
                "settings": settings or {},
                "source_versions": source_versions or {},
            }
        )
        return []


class FailingRules:
    def generate_candidates(
        self,
        scope_month: str,
        oa_rows: list[dict[str, object]],
        bank_rows: list[dict[str, object]],
        invoice_rows: list[dict[str, object]],
        *,
        settings: dict[str, object] | None = None,
        source_versions: dict[str, object] | None = None,
    ) -> list[dict[str, object]]:
        raise RuntimeError("rules failed")


def row(row_id: str) -> dict[str, object]:
    return {"id": row_id}


def candidate(
    month: str,
    rule_code: str,
    row_ids: list[str],
    *,
    status: str = "needs_review",
) -> dict[str, object]:
    return {
        "scope_month": month,
        "candidate_type": "bank",
        "status": status,
        "confidence": "high" if status == "auto_closed" else "medium",
        "rule_code": rule_code,
        "row_ids": row_ids,
        "oa_row_ids": [row_id for row_id in row_ids if row_id.startswith("oa-")],
        "bank_row_ids": [row_id for row_id in row_ids if row_id.startswith("bank-")],
        "invoice_row_ids": [row_id for row_id in row_ids if row_id.startswith("invoice-")],
        "amount": "100.00",
        "amount_delta": "0.00",
        "explanation": "candidate",
        "conflict_candidate_keys": [],
        "generated_at": "2026-05-07T00:00:00+00:00",
        "source_versions": {},
    }


if __name__ == "__main__":
    unittest.main()
