from copy import deepcopy
import logging
import unittest

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_matching_orchestrator import (
    WORKBENCH_EXCEPTION_RULES_VERSION,
    WorkbenchMatchingRelationReadPort,
    WorkbenchMatchingOrchestrator,
)
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION, WorkbenchMatchingRules
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandService
from fin_ops_platform.services.workbench_special_pair_rule_service import WORKBENCH_SPECIAL_RULES_VERSION


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

    def test_legacy_mode_persists_free_engine_bank_invoice_candidate(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()

        summary = self._orchestrator(
            row_provider=FakeRowProvider(
                bank_rows={
                    "2026-02": [
                        {
                            "id": "bank-ccb-8106",
                            "type": "bank",
                            "trade_time": "2026-02-11 11:49:39",
                            "credit_amount": "13440.00",
                            "debit_amount": "",
                            "counterparty_name": "北京长征高科技有限公司",
                            "summary": "",
                            "remark": "",
                        }
                    ]
                },
                invoice_rows={
                    "2026-02": [
                        {
                            "id": "invoice-output-052520",
                            "type": "invoice",
                            "amount": "13440.00",
                            "total_with_tax": "13440.00",
                            "seller_name": "云南溯源科技有限公司",
                            "seller_tax_no": "915300007194052520",
                            "buyer_name": "北京长征高科技有限公司",
                            "buyer_tax_no": "91110106102126771H",
                            "invoice_type": "销项发票",
                            "issue_date": "2026-02-11",
                        }
                    ]
                },
            ),
            candidate_service=candidate_service,
            rules=WorkbenchMatchingRules(include_special_rules=False),
        ).run(changed_scope_months=["2026-02"], reason="unit-test", request_id="req-bank-invoice")

        candidates = candidate_service.list_candidates_by_month("2026-02")
        self.assertEqual(summary["auto_closed_count"], 1)
        self.assertEqual([candidate["rule_code"] for candidate in candidates], ["bank_invoice_exact_amount"])
        self.assertEqual(candidates[0]["status"], "auto_closed")
        self.assertEqual(candidates[0]["bank_row_ids"], ["bank-ccb-8106"])
        self.assertEqual(candidates[0]["invoice_row_ids"], ["invoice-output-052520"])
        self.assertEqual(
            candidates[0]["special_metadata"]["workbench_reconciliation_decision"]["rule_code"],
            "bank_invoice_exact_amount",
        )

    def test_legacy_mode_auto_links_only_safe_auto_closed_candidate(self) -> None:
        relation_repository = FakeRelationRepository()
        candidate_service = WorkbenchCandidateMatchService()
        safe_candidate = candidate(
            "2026-02",
            "bank_invoice_exact_amount",
            ["bank-safe", "invoice-safe"],
            status="auto_closed",
        )
        conflicted_candidate = {
            **candidate(
                "2026-02",
                "bank_invoice_exact_amount_conflict",
                ["bank-conflict", "invoice-conflict"],
                status="auto_closed",
            ),
            "conflict_candidate_keys": ["candidate:other"],
        }

        summary = self._orchestrator(
            row_provider=FakeRowProvider(
                bank_rows={
                    "2026-02": [
                        bank_row("bank-safe", month="2026-02", amount="100.00"),
                        bank_row("bank-conflict", month="2026-02", amount="100.00"),
                    ]
                },
                invoice_rows={
                    "2026-02": [
                        invoice_row("invoice-safe", amount="100.00"),
                        invoice_row("invoice-conflict", amount="100.00"),
                    ]
                },
            ),
            pair_relation_service=WorkbenchPairRelationService(),
            candidate_service=candidate_service,
            relation_command_service=WorkbenchRelationCommandService(relation_repository=relation_repository),
            rules=StaticRules([safe_candidate, conflicted_candidate]),
        ).run(changed_scope_months=["2026-02"], reason="unit-test", request_id="req-auto-link")

        self.assertEqual(summary["auto_closed_count"], 2)
        self.assertEqual(summary["auto_linked_relation_count"], 1)
        relation_service = WorkbenchPairRelationService.from_snapshot(relation_repository.snapshot)
        self.assertIsNotNone(relation_service.get_active_relation_by_row_id("bank-safe"))
        self.assertIsNone(relation_service.get_active_relation_by_row_id("bank-conflict"))
        statuses_by_rule = {
            item["rule_code"]: item["status"]
            for item in candidate_service.list_candidates_by_month("2026-02")
        }
        self.assertEqual(statuses_by_rule["bank_invoice_exact_amount"], "consumed")
        self.assertEqual(statuses_by_rule["bank_invoice_exact_amount_conflict"], "auto_closed")

    def test_legacy_mode_persists_oa_bank_exact_sum_candidate(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()
        read_model_service = WorkbenchReadModelService()
        read_model_service.upsert_read_model(scope_key="2026-05", payload={"cached": True})

        summary = self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={"2026-05": [oa_row("oa-split", amount="300.00")]},
                bank_rows={
                    "2026-05": [
                        bank_row("bank-120", amount="120.00"),
                        bank_row("bank-180", amount="180.00"),
                    ]
                },
            ),
            candidate_service=candidate_service,
            read_model_service=read_model_service,
            rules=WorkbenchMatchingRules(include_special_rules=False),
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-oa-bank-sum")

        candidates = candidate_service.list_candidates_by_month("2026-05")
        exact_sum = next(candidate for candidate in candidates if candidate["rule_code"] == "oa_bank_exact_sum")
        self.assertGreaterEqual(summary["candidate_count"], 1)
        self.assertEqual(exact_sum["status"], "incomplete")
        self.assertEqual(exact_sum["candidate_type"], "oa_bank")
        self.assertEqual(exact_sum["oa_row_ids"], ["oa-split"])
        self.assertCountEqual(exact_sum["bank_row_ids"], ["bank-120", "bank-180"])
        self.assertEqual(exact_sum["amount"], "300.00")
        self.assertIsNone(read_model_service.get_read_model("2026-05"))

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

    def test_active_pair_relation_rows_are_excluded_regardless_of_relation_mode(self) -> None:
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-internal-transfer",
            row_ids=["bank-held"],
            row_types=["bank"],
            relation_mode="internal_transfer_pair",
            created_by="tester",
            month_scope="2026-05",
        )
        rules = EchoRules()

        summary = self._orchestrator(
            row_provider=FakeRowProvider(bank_rows={"2026-05": [row("bank-held"), row("bank-free")]}),
            pair_relation_service=pair_service,
            rules=rules,
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-002b")

        self.assertEqual(rules.calls[0]["bank_rows"], [row("bank-free")])
        self.assertEqual(summary["suppressed_by_pair_relation_count"], 1)

    def test_active_exception_case_rows_keep_candidate_evidence_but_suppress_auto_close(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()
        rules = StaticRules([candidate("2026-05", "auto_rule", ["bank-case"], status="auto_closed")])

        summary = self._orchestrator(
            row_provider=FakeRowProvider(bank_rows={"2026-05": [row("bank-case")]}),
            candidate_service=candidate_service,
            exception_case_service=FakeExceptionCaseService({"bank-case": "WEX-000001"}),
            rules=rules,
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-002c")

        stored = candidate_service.list_candidates_by_month("2026-05")[0]
        self.assertEqual(stored["status"], "suppressed")
        self.assertEqual(stored["suppressed_reason"], "active_exception_case")
        self.assertEqual(stored["consumed_by_case_id"], "WEX-000001")
        self.assertEqual(summary["auto_closed_count"], 0)
        self.assertEqual(summary["suppressed_by_exception_case_count"], 1)
        self.assertEqual(summary["candidate_attached_to_exception_case_count"], 1)

    def test_source_versions_include_matching_special_and_exception_rules_versions(self) -> None:
        candidate_service = WorkbenchCandidateMatchService()

        self._orchestrator(
            row_provider=FakeRowProvider(),
            candidate_service=candidate_service,
            rules=StaticRules([]),
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-002d")

        self.assertTrue(
            candidate_service.is_scope_fresh(
                "2026-05",
                source_versions={
                    "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
                    "workbench_special_rules_version": WORKBENCH_SPECIAL_RULES_VERSION,
                    "workbench_exception_rules_version": WORKBENCH_EXCEPTION_RULES_VERSION,
                },
            )
        )

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
        first_candidates = candidate_service.list_candidates_by_month("2026-05")
        orchestrator.run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-004b")

        second_candidates = candidate_service.list_candidates_by_month("2026-05")
        self.assertEqual([candidate["candidate_key"] for candidate in second_candidates], [first_candidates[0]["candidate_key"]])
        self.assertEqual(len(second_candidates), 1)
        self.assertTrue(candidate_service.is_scope_fresh("2026-05", source_versions=orchestrator._source_versions()))

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
        self.assertEqual(summary["skipped_rule_count"], 0)
        self.assertIsInstance(summary["duration_ms"], int)

    def test_summary_accumulates_rule_skips_and_reports_month_progress(self) -> None:
        progress_updates: list[dict[str, object]] = []

        summary = self._orchestrator(
            row_provider=FakeRowProvider(),
            rules=SkippingRules(),
        ).run(
            changed_scope_months=["2026-05", "2026-06"],
            reason="unit-test",
            request_id="req-005b",
            progress_callback=progress_updates.append,
        )

        self.assertEqual(summary["processed_months"], ["2026-05", "2026-06"])
        self.assertEqual(summary["current_month"], "2026-06")
        self.assertEqual(summary["skipped_rule_count"], 4)
        self.assertEqual(len(summary["skipped_rules"]), 4)
        self.assertEqual([update["current_month"] for update in progress_updates], ["2026-05", "2026-06"])
        self.assertEqual(progress_updates[-1]["processed_months"], ["2026-05", "2026-06"])

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

    def test_decision_store_mode_collects_window_rows_and_does_not_write_legacy_candidates(self) -> None:
        decision_store = WorkbenchReconciliationDecisionStore()
        candidate_service = WorkbenchCandidateMatchService()
        candidate_service.upsert_candidate(candidate("2026-06", "old_legacy_rule", ["bank-old"]))

        summary = self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={"2026-05": [oa_row("oa-may")]},
                bank_rows={"2026-06": [bank_row("bank-june")]},
            ),
            candidate_service=candidate_service,
            decision_store=decision_store,
            rules=StaticRules([candidate("2026-06", "legacy_rule", ["bank-legacy"])]),
        ).run(changed_scope_months=["2026-06"], reason="unit-test", request_id="req-007")

        self.assertEqual(candidate_service.list_candidates_by_month("2026-06"), [])
        decisions = decision_store.list_decisions("2026-06")
        self.assertEqual([decision["row_ids"] for decision in decisions], [["oa-may", "bank-june"]])
        self.assertEqual(summary["decision_count"], 1)
        self.assertEqual(summary["candidate_count"], 0)

    def test_legacy_mode_excludes_active_relation_rows_in_matching_window(self) -> None:
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-next-month-no-oa",
            row_ids=["bank-held-3000", "bank-held-6000"],
            row_types=["bank", "bank"],
            relation_mode="no_oa_bank_batch",
            created_by="tester",
            month_scope="2026-03",
        )
        rules = EchoRules()

        self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={"2026-02": [oa_row("oa-loan-interest", month="2026-02", amount="9600.00")]},
                bank_rows={
                    "2026-02": [
                        bank_row("bank-fee-a", month="2026-02", amount="300.00"),
                        bank_row("bank-held-3000", month="2026-03", amount="3000.00"),
                        bank_row("bank-held-6000", month="2026-03", amount="6000.00"),
                    ]
                },
            ),
            pair_relation_service=pair_service,
            rules=rules,
        ).run(changed_scope_months=["2026-02"], reason="unit-test", request_id="req-legacy-held-window")

        self.assertEqual([row["id"] for row in rules.calls[0]["bank_rows"]], ["bank-fee-a"])

    def test_decision_store_mode_uses_source_oa_month_for_attachment_invoice_ownership(self) -> None:
        decision_store = WorkbenchReconciliationDecisionStore()

        self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={
                    "2026-01": [
                        {
                            "id": "oa-exp-1989",
                            "type": "oa",
                            "month": "2026-01",
                            "amount": "607.00",
                            "applicant": "何琛",
                            "apply_type": "日常报销",
                            "reason": "何琛 石林复烤住宿费",
                        }
                    ]
                },
                bank_rows={
                    "2026-03": [
                        {
                            "id": "bank-8106",
                            "type": "bank",
                            "month": "2026-03",
                            "debit_amount": "607.00",
                            "credit_amount": "",
                            "counterparty_name": "何琛",
                            "summary": "报销",
                        }
                    ]
                },
                invoice_rows={
                    "2026-01": [
                        {
                            "id": "oa-att-inv-160",
                            "type": "invoice",
                            "source_kind": "oa_attachment_invoice",
                            "derived_from_oa_id": "oa-exp-1989",
                            "invoice_type": "进项发票",
                            "issue_date": "2025-12-31",
                            "amount": "158.42",
                            "total_with_tax": "160.00",
                            "seller_name": "石林盛泰红酒店",
                        },
                        {
                            "id": "oa-att-inv-447",
                            "type": "invoice",
                            "source_kind": "oa_attachment_invoice",
                            "derived_from_oa_id": "oa-exp-1989",
                            "invoice_type": "进项发票",
                            "issue_date": "2026-01-23",
                            "amount": "447.00",
                            "total_with_tax": "447.00",
                            "seller_name": "石林复烤交通住宿汇总",
                        },
                    ]
                },
            ),
            decision_store=decision_store,
            rules=StaticRules([]),
        ).run(changed_scope_months=["2026-03"], reason="unit-test", request_id="req-source-month")

        decisions = decision_store.list_decisions("2026-03")
        self.assertEqual(len(decisions), 1)
        self.assertEqual(decisions[0]["rule_code"], "oa_attachment_invoice_with_bank")
        self.assertCountEqual(decisions[0]["invoice_row_ids"], ["oa-att-inv-160", "oa-att-inv-447"])
        self.assertIn("oa-att-inv-160", decisions[0]["row_ids"])

    def test_decision_store_mode_persists_oa_bank_exact_sum_decision(self) -> None:
        decision_store = WorkbenchReconciliationDecisionStore()
        candidate_service = WorkbenchCandidateMatchService()
        read_model_service = WorkbenchReadModelService()
        read_model_service.upsert_read_model(scope_key="2026-05", payload={"cached": True})

        summary = self._orchestrator(
            row_provider=FakeRowProvider(
                oa_rows={"2026-05": [oa_row("oa-split", amount="300.00")]},
                bank_rows={
                    "2026-05": [
                        bank_row("bank-120", amount="120.00", month="2026-05"),
                        bank_row("bank-180", amount="180.00", month="2026-05"),
                    ]
                },
            ),
            candidate_service=candidate_service,
            read_model_service=read_model_service,
            decision_store=decision_store,
            rules=StaticRules([]),
        ).run(changed_scope_months=["2026-05"], reason="unit-test", request_id="req-decision-oa-bank-sum")

        decisions = decision_store.list_decisions("2026-05")
        self.assertEqual(candidate_service.list_candidates_by_month("2026-05"), [])
        self.assertEqual(summary["decision_count"], 1)
        self.assertEqual(summary["paired_decision_count"], 1)
        self.assertEqual(decisions[0]["rule_code"], "oa_bank_exact_sum")
        self.assertEqual(decisions[0]["match_shape"], "oa_bank")
        self.assertEqual(decisions[0]["row_ids"], ["oa-split", "bank-120", "bank-180"])
        self.assertEqual(decisions[0]["oa_row_ids"], ["oa-split"])
        self.assertEqual(decisions[0]["bank_row_ids"], ["bank-120", "bank-180"])
        self.assertTrue(decisions[0]["payment_amount_closed"])
        self.assertIsNone(decisions[0]["invoice_amount_closed"])
        self.assertIsNone(read_model_service.get_read_model("2026-05"))

    def _orchestrator(
        self,
        *,
        row_provider: object,
        pair_relation_service: WorkbenchPairRelationService | None = None,
        candidate_service: WorkbenchCandidateMatchService | None = None,
        read_model_service: WorkbenchReadModelService | None = None,
        exception_case_service: object | None = None,
        decision_store: WorkbenchReconciliationDecisionStore | None = None,
        relation_command_service: object | None = None,
        rules: object,
    ) -> WorkbenchMatchingOrchestrator:
        return WorkbenchMatchingOrchestrator(
            row_provider=row_provider,
            relation_read_port=WorkbenchMatchingRelationReadPort(pair_relation_service or WorkbenchPairRelationService()),
            candidate_match_service=candidate_service or WorkbenchCandidateMatchService(),
            read_model_service=read_model_service or WorkbenchReadModelService(),
            decision_store=decision_store,
            relation_command_service=relation_command_service,
            rules=rules,
            exception_case_service=exception_case_service,
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


class FakeRelationRepository:
    def __init__(self) -> None:
        self.snapshot: dict[str, object] = {}
        self.save_calls: list[dict[str, object]] = []

    def load_workbench_pair_relations(self) -> dict[str, object]:
        return deepcopy(self.snapshot)

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, object]:
        return WorkbenchPairRelationService.from_snapshot(self.snapshot).snapshot_for_row_ids(
            list(row_ids or []),
            case_ids=list(case_ids or []),
        )

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: set[str] | None = None,
    ) -> None:
        self.save_calls.append(
            {
                "snapshot": deepcopy(snapshot),
                "changed_case_ids": set(changed_case_ids or set()),
            }
        )
        self.snapshot = deepcopy(snapshot)


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


class FakeExceptionCaseService:
    def __init__(self, row_case_index: dict[str, str]) -> None:
        self.row_case_index = row_case_index

    def case_ids_for_rows(self, row_ids: list[str]) -> list[str]:
        case_ids: list[str] = []
        for row_id in row_ids:
            case_id = self.row_case_index.get(row_id)
            if case_id and case_id not in case_ids:
                case_ids.append(case_id)
        return case_ids


class SkippingRules:
    def __init__(self) -> None:
        self.calls: list[str] = []

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
        self.calls.append(scope_month)
        return []

    def last_summary(self) -> dict[str, object]:
        scope_month = self.calls[-1]
        return {
            "skipped_rule_count": 2,
            "skipped_rules": [
                {
                    "scope_month": scope_month,
                    "rule_code": "oa_multi_invoice_exact_sum",
                    "reason": "sum_match_candidate_cap_exceeded",
                },
                {
                    "scope_month": scope_month,
                    "rule_code": "oa_bank_multi_invoice_exact_sum",
                    "reason": "sum_match_state_cap_exceeded",
                },
            ],
        }


def row(row_id: str) -> dict[str, object]:
    return {"id": row_id}


def oa_row(row_id: str, *, month: str = "2026-05", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "month": month,
        "amount": amount,
        "applicant": "张三",
        "project_name": "项目A",
        "reason": "支付供应商",
    }


def bank_row(row_id: str, *, month: str = "2026-06", amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "month": month,
        "debit_amount": amount,
        "credit_amount": "",
        "counterparty_name": "供应商",
        "summary": "支付供应商",
    }


def invoice_row(row_id: str, *, amount: str = "100.00") -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "amount": amount,
        "total_with_tax": amount,
        "seller_name": "供应商",
        "buyer_name": "客户",
        "invoice_type": "进项发票",
        "issue_date": "2026-02-11",
    }


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
