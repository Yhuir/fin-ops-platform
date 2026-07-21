from __future__ import annotations

from datetime import date
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.workbench_free_matching_engine import (
    ActiveFormalRelationAnchor,
    FormalRelationFact,
    FormalRelationFactBatch,
    FormalRelationReference,
    WorkbenchFreeMatchingEngine,
)
from fin_ops_platform.services.workbench_matching_orchestrator import (
    AUTO_RELATION_ACTOR,
    WorkbenchMatchingOrchestrator,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import CallbackWorkbenchRelationRepository
from tests.workbench_deterministic_relation_fixtures import yunnan_lifu_520_fixture


def fact(
    row_type: str,
    row_id: str,
    amount_minor: int = 52_000,
    *,
    evidence: tuple[tuple[str, str], ...] = (("counterparty", "云南立孚科技有限公司"),),
    references: tuple[FormalRelationReference, ...] = (),
) -> FormalRelationFact:
    return FormalRelationFact(
        row_type=row_type,
        canonical_object_identity=row_id,
        row_id=row_id,
        amount_minor=amount_minor,
        currency="CNY",
        direction="expenditure",
        fact_date=date(2026, 5, 7),
        evidence_keys=evidence,
        references=references,
        source_version=f"source:{row_id}",
    )


class RecordingFactRepository:
    def __init__(
        self,
        fact_batch: FormalRelationFactBatch,
        *,
        etc_batch_link_candidates: list[dict[str, object]] | None = None,
    ) -> None:
        self.fact_batch = fact_batch
        self.etc_batch_link_candidates = list(etc_batch_link_candidates or [])
        self.calls: list[dict[str, object]] = []

    def load_batch(self, scope_months: list[str], *, source_versions: dict[str, object]) -> FormalRelationFactBatch:
        self.calls.append({"scope_months": list(scope_months), "source_versions": dict(source_versions)})
        return self.fact_batch

    def load_etc_batch_link_candidates(self, scope_months: list[str]) -> list[dict[str, object]]:
        self.calls.append({"etc_scope_months": list(scope_months)})
        return list(self.etc_batch_link_candidates)


class RecordingEtcBatchLinkRepository:
    def validate_etc_batch_links(self, links: list[dict[str, object]]) -> dict[str, object]:
        return {"valid": bool(links), "issues": []}


class RecordingBankTagFacade:
    def __init__(
        self,
        category_codes: dict[str, str] | None = None,
        *,
        status: str = "fresh",
        omitted_ids: set[str] | None = None,
    ) -> None:
        self.category_codes = dict(category_codes or {})
        self.status = status
        self.omitted_ids = set(omitted_ids or set())
        self.calls: list[list[str]] = []

    def get_by_transaction_ids(self, transaction_ids: list[str], **_kwargs: object) -> dict[str, object]:
        self.calls.append(list(transaction_ids))
        return {
            "status": self.status,
            "rows": [
                {
                    "transaction_id": transaction_id,
                    "effective_category_code": self.category_codes.get(
                        transaction_id, "custom_engineering_services"
                    ),
                }
                for transaction_id in transaction_ids
                if transaction_id not in self.omitted_ids
            ],
        }


class RecordingUow:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self.snapshot = snapshot or {"pair_relations": {}, "pair_relation_history": []}
        self.calls: list[object] = []
        self.save_count = 0

    def run(self, command: object, handler) -> dict[str, object]:
        self.calls.append(command)

        def save_snapshot(snapshot: dict[str, object], *, changed_case_ids: list[str]) -> None:
            self.save_count += 1
            _ = changed_case_ids
            self.snapshot = snapshot

        context = SimpleNamespace(
            pair_relations=CallbackWorkbenchRelationRepository(
                load_snapshot=lambda: self.snapshot,
                save_snapshot=save_snapshot,
            ),
            etc_batch_links=RecordingEtcBatchLinkRepository(),
            exception_cases=object(),
            row_overrides=object(),
            idempotency_store={},
        )
        result = dict(handler(context))
        result["outbox_event_ids"] = ["outbox-1"]
        result["idempotent_replay"] = False
        return result


class WorkbenchMatchingOrchestratorTests(unittest.TestCase):
    def _orchestrator(
        self,
        fact_batch: FormalRelationFactBatch,
        *,
        uow: RecordingUow | None = None,
        etc_batch_link_candidates: list[dict[str, object]] | None = None,
        bank_tag_facade: RecordingBankTagFacade | None = None,
    ) -> tuple[WorkbenchMatchingOrchestrator, RecordingFactRepository, RecordingUow]:
        repository = RecordingFactRepository(
            fact_batch,
            etc_batch_link_candidates=etc_batch_link_candidates,
        )
        resolved_uow = uow or RecordingUow()
        return (
            WorkbenchMatchingOrchestrator(
                fact_repository=repository,
                matcher=WorkbenchFreeMatchingEngine(),
                relation_uow=resolved_uow,
                source_versions_provider=lambda: {"matching": "v1"},
                bank_tag_read_facade=bank_tag_facade or RecordingBankTagFacade(),
                bank_flow_rule_tag_rules_payload=lambda: {
                    "version": 11,
                    "requirements_by_tag_code": {
                        "custom_engineering_services": {
                            "requires_oa": True,
                            "requires_invoice": True,
                        }
                    },
                },
            ),
            repository,
            resolved_uow,
        )

    def test_safe_plan_is_written_once_through_one_batch_uow(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-520"), fact("invoice", "inv-520")))
        orchestrator, repository, uow = self._orchestrator(fixture)

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-1",
        )

        self.assertEqual(len(repository.calls), 2)
        self.assertEqual(len(uow.calls), 1)
        self.assertEqual(uow.save_count, 1)
        self.assertEqual(summary["planned_relation_count"], 1)
        self.assertEqual(summary["created_relation_count"], 1)
        self.assertEqual(summary["extended_relation_count"], 0)
        self.assertEqual(summary["outbox_event_ids"], ["outbox-1"])
        relation = next(iter(uow.snapshot["pair_relations"].values()))
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
        self.assertEqual(relation["status"], "active")
        self.assertEqual(relation["created_by"], AUTO_RELATION_ACTOR)
        self.assertEqual(relation["special_metadata"]["formal_relation"]["origin"], "system_deterministic")
        self.assertNotIn("cost_statistics", uow.calls[0].refresh_metadata["downstream_scope_types"])

    def test_bank_plan_persists_one_bulk_requirement_snapshot(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-520"), fact("bank", "bank-520")))
        tag_facade = RecordingBankTagFacade()
        orchestrator, _repository, uow = self._orchestrator(
            fixture,
            bank_tag_facade=tag_facade,
        )

        orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-bank-requirements",
        )

        self.assertEqual(tag_facade.calls, [["bank-520"]])
        relation = next(iter(uow.snapshot["pair_relations"].values()))
        self.assertEqual(
            {
                "requires_oa": relation["special_metadata"]["requires_oa"],
                "requires_invoice": relation["special_metadata"]["requires_invoice"],
                "paired_requirement_version": relation["special_metadata"]["paired_requirement_version"],
            },
            {"requires_oa": True, "requires_invoice": True, "paired_requirement_version": 11},
        )

    def test_bank_plan_fails_before_uow_when_tag_read_model_is_not_fresh(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-520"), fact("bank", "bank-520")))
        orchestrator, _repository, uow = self._orchestrator(
            fixture,
            bank_tag_facade=RecordingBankTagFacade(status="refreshing"),
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            orchestrator.run(
                changed_scope_months=["2026-05"],
                reason="dirty_scope_retry",
                request_id="request-bank-tags-refreshing",
            )

        self.assertEqual(uow.calls, [])

    def test_bank_plan_fails_before_uow_when_tag_row_is_missing(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-520"), fact("bank", "bank-520")))
        orchestrator, _repository, uow = self._orchestrator(
            fixture,
            bank_tag_facade=RecordingBankTagFacade(omitted_ids={"bank-520"}),
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_tag_rows_missing"):
            orchestrator.run(
                changed_scope_months=["2026-05"],
                reason="dirty_scope_retry",
                request_id="request-bank-tags-missing",
            )

        self.assertEqual(uow.calls, [])

    def test_no_plan_does_not_open_uow_or_write_history_outbox(self) -> None:
        fixture = FormalRelationFactBatch(
            facts=(
                fact("oa", "oa-unmatched", evidence=()),
                fact("invoice", "invoice-unmatched", evidence=()),
            )
        )
        orchestrator, repository, uow = self._orchestrator(fixture)

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-2",
        )

        self.assertEqual(len(repository.calls), 2)
        self.assertEqual(uow.calls, [])
        self.assertEqual(summary["planned_relation_count"], 0)
        self.assertEqual(summary["outbox_event_ids"], [])

    def test_ambiguous_result_is_zero_write_and_reports_blocker(self) -> None:
        fixture = FormalRelationFactBatch(
            facts=(fact("oa", "oa-ambiguous"), fact("bank", "bank-a"), fact("bank", "bank-b"))
        )
        orchestrator, _repository, uow = self._orchestrator(fixture)

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-3",
        )

        self.assertEqual(uow.calls, [])
        self.assertEqual(summary["ambiguous_component_count"], 1)
        self.assertEqual(summary["blocked_reason_counts"], {"ambiguous_partition": 1})

    def test_existing_520_relation_is_preserved_without_recreation(self) -> None:
        fixture = yunnan_lifu_520_fixture()
        existing_snapshot = {
            "pair_relations": {
                fixture.active_relations[0].case_id: {
                    "case_id": fixture.active_relations[0].case_id,
                    "row_ids": [fact.row_id for fact in fixture.facts],
                    "row_types": [fact.row_type for fact in fixture.facts],
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "version": 1,
                    "month_scope": "2026-05",
                }
            },
            "pair_relation_history": [],
        }
        uow = RecordingUow(existing_snapshot)
        orchestrator, _repository, _uow = self._orchestrator(fixture, uow=uow)

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-520",
        )

        self.assertEqual(uow.calls, [])
        self.assertEqual(summary["preserved_active_count"], 1)
        self.assertEqual(uow.snapshot, existing_snapshot)

    def test_explicit_reference_extension_keeps_active_case_id(self) -> None:
        oa = fact("oa", "oa-active")
        invoice = fact("invoice", "invoice-active")
        bank = fact(
            "bank",
            "bank-new",
            evidence=(),
            references=(
                FormalRelationReference(
                    kind="canonical_source",
                    value="bank-to-oa",
                    target_row_type="oa",
                    target_identity="oa-active",
                ),
            ),
        )
        case_id = "case:decision:historical"
        fixture = FormalRelationFactBatch(
            facts=(oa, invoice, bank),
            active_relations=(ActiveFormalRelationAnchor(case_id, (oa.member_key, invoice.member_key)),),
        )
        existing_snapshot = {
            "pair_relations": {
                case_id: {
                    "case_id": case_id,
                    "row_ids": [oa.row_id, invoice.row_id],
                    "row_types": [oa.row_type, invoice.row_type],
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "version": 1,
                    "month_scope": "2026-05",
                }
            },
            "pair_relation_history": [],
        }
        orchestrator, _repository, uow = self._orchestrator(fixture, uow=RecordingUow(existing_snapshot))

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="dirty_scope_retry",
            request_id="request-extension",
        )

        self.assertEqual(summary["created_relation_count"], 0)
        self.assertEqual(summary["extended_relation_count"], 1)
        self.assertEqual(summary["relation_ids"], [case_id])
        self.assertEqual(set(uow.snapshot["pair_relations"][case_id]["row_ids"]), {"oa-active", "invoice-active", "bank-new"})

    def test_summary_and_command_contract_have_no_candidate_or_decision_state(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-clean"), fact("invoice", "invoice-clean")))
        orchestrator, _repository, uow = self._orchestrator(fixture)

        summary = orchestrator.run(
            changed_scope_months=["2026-05", "2026-05"],
            reason="dirty_scope_retry",
            request_id="request-clean",
        )

        serialized = repr((summary, uow.calls[0]))
        self.assertNotIn("candidate", serialized.lower())
        self.assertNotIn("decision", serialized.lower())
        self.assertEqual(summary["scope_months"], ["2026-05"])

    def test_same_run_relation_carries_exact_etc_link_with_one_save(self) -> None:
        fixture = FormalRelationFactBatch(facts=(fact("oa", "oa-etc"), fact("bank", "bank-etc")))
        candidate = {
            "oa_row_id": "oa-etc",
            "business_batch_id": "etc_business_batch_0014",
            "external_etc_batch_id": "etc_20260622_001",
            "submission_batch_id": "etc_submission_0014",
            "invoice_count": 34,
            "total_amount": "1584.35",
            "external_batch_owner_count": 1,
            "scope_keys": ["2026-05", "all"],
        }
        orchestrator, _repository, uow = self._orchestrator(
            fixture,
            etc_batch_link_candidates=[candidate],
        )

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="oa_projection_sync",
            request_id="request-etc",
        )

        self.assertEqual(uow.save_count, 1)
        self.assertEqual(summary["enriched_relation_count"], 1)
        self.assertEqual(uow.calls[0].scope_keys, ("2026-05",))
        relation = next(iter(uow.snapshot["pair_relations"].values()))
        self.assertEqual(
            relation["special_metadata"]["etc_batch_link"]["external_etc_batch_id"],
            "etc_20260622_001",
        )
        self.assertEqual(relation["special_metadata"]["etc_batch_link"]["invoice_count"], 34)

    def test_existing_relation_is_enriched_without_creating_a_new_relation(self) -> None:
        oa = fact("oa", "oa-existing-etc")
        bank = fact("bank", "bank-existing-etc")
        case_id = "case:existing-etc"
        fixture = FormalRelationFactBatch(
            facts=(oa, bank),
            active_relations=(ActiveFormalRelationAnchor(case_id, (oa.member_key, bank.member_key)),),
        )
        snapshot = {
            "pair_relations": {
                case_id: {
                    "case_id": case_id,
                    "row_ids": [oa.row_id, bank.row_id],
                    "row_types": [oa.row_type, bank.row_type],
                    "relation_mode": "manual_confirmed",
                    "status": "active",
                    "version": 1,
                    "month_scope": "2026-05",
                }
            },
            "pair_relation_history": [],
        }
        candidate = {
            "oa_row_id": oa.row_id,
            "business_batch_id": "etc_business_batch_0014",
            "external_etc_batch_id": "etc_20260622_001",
            "submission_batch_id": "etc_submission_0014",
            "invoice_count": 34,
            "total_amount": "1584.35",
            "external_batch_owner_count": 1,
            "scope_keys": ["2026-05", "all"],
        }
        orchestrator, _repository, uow = self._orchestrator(
            fixture,
            uow=RecordingUow(snapshot),
            etc_batch_link_candidates=[candidate],
        )

        summary = orchestrator.run(
            changed_scope_months=["2026-05"],
            reason="oa_projection_sync",
            request_id="request-existing-etc",
        )

        self.assertEqual(summary["planned_relation_count"], 0)
        self.assertEqual(summary["enriched_relation_count"], 1)
        self.assertEqual(uow.calls[0].scope_keys, ("2026-05",))
        self.assertEqual(uow.save_count, 1)
        self.assertEqual(set(uow.snapshot["pair_relations"]), {case_id})

    def test_invalid_input_fails_before_repository_or_uow(self) -> None:
        fixture = FormalRelationFactBatch(facts=())
        orchestrator, repository, uow = self._orchestrator(fixture)

        for kwargs in (
            {"changed_scope_months": [], "reason": "x", "request_id": "r"},
            {"changed_scope_months": ["2026-13"], "reason": "x", "request_id": "r"},
            {"changed_scope_months": ["2026-05"], "reason": "", "request_id": "r"},
            {"changed_scope_months": ["2026-05"], "reason": "x", "request_id": ""},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises((TypeError, ValueError)):
                orchestrator.run(**kwargs)
        self.assertEqual(repository.calls, [])
        self.assertEqual(uow.calls, [])


if __name__ == "__main__":
    unittest.main()
