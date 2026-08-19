from __future__ import annotations

import random
import unittest
from copy import deepcopy

from fin_ops_platform.services.workbench_relation_grouping import (
    WorkbenchRelationGroupingService,
    WorkbenchRelationPreviewGroupingService,
)
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
    evaluate_bank_relation_completion,
)

from tests.workbench_deterministic_relation_fixtures import (
    YUNNAN_LIFU_CASE_ID,
    omitted_thirteen_invoice_fixture,
    yunnan_lifu_520_fixture,
)


def row_for_fact(fact) -> dict[str, object]:
    amount = f"{fact.amount_minor / 100:.2f}"
    return {
        "id": fact.row_id,
        "type": fact.row_type,
        "object_identity_key": fact.canonical_object_identity,
        "amount": amount,
        "amount_value": amount,
        "status": "unpaired",
    }


def active_relation(batch, *, relation_mode: str = "manual_confirmed") -> dict[str, object]:
    anchor = batch.active_relations[0]
    rows = {fact.member_key: fact for fact in batch.facts}
    return {
        "case_id": anchor.case_id,
        "row_ids": [rows[key].row_id for key in anchor.member_keys],
        "row_types": [key[0] for key in anchor.member_keys],
        "status": "active",
        "relation_mode": relation_mode,
    }


def identities(groups: list[dict[str, object]]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for group in groups:
        collapsed = group.get("collapsed_rows") if isinstance(group.get("collapsed_rows"), dict) else {}
        for row_type in ("oa", "bank", "invoice"):
            rows = list(collapsed.get(row_type) or group.get(f"{row_type}_rows") or [])
            for row in rows:
                if isinstance(row, dict) and row.get("object_identity_key"):
                    result.add((row_type, str(row["object_identity_key"])))
    return result


class WorkbenchRelationGroupingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchRelationGroupingService()

    def test_520_historical_oa_invoice_relation_stays_grouped_while_waiting_for_bank(self) -> None:
        batch = yunnan_lifu_520_fixture()
        rows = {fact.row_id: row_for_fact(fact) for fact in batch.facts}

        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[active_relation(batch)],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["unpaired_count"], 1)
        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["group_id"], f"case:{YUNNAN_LIFU_CASE_ID}")
        self.assertEqual(group["group_type"], "relation")
        self.assertEqual(group["completion"], {"is_complete": False, "missing_row_types": ["bank"]})
        self.assertEqual(identities([group]), {fact.member_key for fact in batch.facts})

    def test_thirteen_invoices_are_thirteen_unpaired_singletons_totaling_170949_minor_units(self) -> None:
        batch = omitted_thirteen_invoice_fixture()
        rows = {fact.row_id: row_for_fact(fact) for fact in batch.facts}

        payload = self.service.group_payload("all", rows_by_id=rows, active_relations=[])

        groups = payload["unpaired"]["groups"]
        self.assertEqual(len(groups), 13)
        self.assertTrue(all(len(group["invoice_rows"]) == 1 for group in groups))
        self.assertEqual(sum(fact.amount_minor for fact in batch.facts), 170_949)
        self.assertEqual(identities(groups), {fact.member_key for fact in batch.facts})

    def test_partition_is_exact_and_candidate_metadata_cannot_merge_rows(self) -> None:
        rows = {
            "oa-a": {"id": "oa-a", "type": "oa", "object_identity_key": "oa-a", "candidate_key": "same"},
            "bank-a": {"id": "bank-a", "type": "bank", "object_identity_key": "bank-a", "candidate_key": "same"},
            "invoice-a": {
                "id": "invoice-a",
                "type": "invoice",
                "object_identity_key": "invoice-a",
                "workbench_reconciliation_decision": {"decision_status": "paired"},
            },
        }
        relation = {
            "case_id": "case:decision:historical",
            "row_ids": ["oa-a", "bank-a"],
            "row_types": ["oa", "bank"],
            "status": "active",
            "relation_mode": "automatic_match",
            "special_metadata": {"requires_oa": True, "requires_invoice": False},
        }

        payload = self.service.group_payload("2026-05", rows_by_id=rows, active_relations=[relation])

        paired = identities(payload["paired"]["groups"])
        unpaired = identities(payload["unpaired"]["groups"])
        canonical = {(str(row["type"]), str(row["object_identity_key"])) for row in rows.values()}
        self.assertEqual(paired, {("oa", "oa-a"), ("bank", "bank-a")})
        self.assertEqual(unpaired, {("invoice", "invoice-a")})
        self.assertFalse(paired & unpaired)
        self.assertEqual(paired | unpaired, canonical)

    def test_group_payload_keeps_nested_input_and_output_ownership_isolated(self) -> None:
        rows = {
            "oa-a": {
                "id": "oa-a",
                "type": "oa",
                "object_identity_key": "oa-a",
                "detail_fields": {"项目名称": "原项目"},
            },
            "bank-a": {
                "id": "bank-a",
                "type": "bank",
                "object_identity_key": "bank-a",
                "tags": ["原标签"],
            },
        }
        relation = {
            "case_id": "case:ownership-isolation",
            "row_ids": ["oa-a", "bank-a"],
            "row_types": ["oa", "bank"],
            "status": "active",
            "special_metadata": {"requires_invoice": False},
            "amount_check": {"status": "matched", "difference": "0.00"},
        }
        original_rows = deepcopy(rows)
        original_relation = deepcopy(relation)

        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[relation],
        )

        self.assertEqual(rows, original_rows)
        self.assertEqual(relation, original_relation)
        group = payload["paired"]["groups"][0]
        group["oa_rows"][0]["detail_fields"]["项目名称"] = "已修改"
        group["bank_rows"][0]["tags"].append("新标签")
        group["special_metadata"]["requires_invoice"] = True
        group["amount_check"]["difference"] = "1.00"
        self.assertEqual(rows, original_rows)
        self.assertEqual(relation, original_relation)

    def test_unpaired_row_does_not_leak_legacy_candidate_ownership(self) -> None:
        payload = self.service.group_payload(
            "2026-01",
            rows_by_id={
                "oa-pay-1982": {
                    "id": "oa-pay-1982",
                    "type": "oa",
                    "object_identity_key": "oa-pay-1982",
                    "status": "paired",
                    "case_id": "candidate:025bf390496affde60b984e7a06785ae174cb0d13fc052559b005a71380dcaf4",
                    "relation_mode": "automatic_decision",
                    "workbench_reconciliation_decision": {"decision_status": "paired"},
                }
            },
            active_relations=[],
        )

        row = payload["unpaired"]["groups"][0]["oa_rows"][0]
        self.assertEqual(row["status"], "unpaired")
        self.assertNotIn("case_id", row)
        self.assertNotIn("relation_mode", row)

    def test_unpaired_row_preserves_active_override_relation_mode(self) -> None:
        payload = self.service.group_payload(
            "2026-01",
            rows_by_id={
                "oa-pay-1977": {
                    "id": "oa-pay-1977",
                    "type": "oa",
                    "object_identity_key": "oa-pay-1977",
                    "case_id": None,
                    "relation_mode": "pending_input_invoice",
                }
            },
            active_relations=[],
        )

        row = payload["unpaired"]["groups"][0]["oa_rows"][0]
        self.assertEqual(row["status"], "unpaired")
        self.assertIsNone(row["case_id"])
        self.assertEqual(row["relation_mode"], "pending_input_invoice")

    def test_legacy_exception_metadata_does_not_change_group_or_exception_counts(self) -> None:
        payload = self.service.group_payload(
            "2026-01",
            rows_by_id={
                "oa-pay-1977": {
                    "id": "oa-pay-1977",
                    "type": "oa",
                    "object_identity_key": "oa-pay-1977",
                    "handled_exception": True,
                    "processed_exception_summary": {"display_tags": ["待找进项发票"]},
                    "oa_bank_relation": {"code": "danger", "tone": "danger"},
                }
            },
            active_relations=[],
        )

        group = payload["unpaired"]["groups"][0]
        self.assertNotIn("exception_state", group)
        self.assertNotIn("processed_exception_summary", group)
        self.assertEqual(payload["summary"]["unpaired_exception_count"], 0)
        self.assertEqual(payload["summary"]["paired_exception_count"], 0)

    def test_unpaired_etc_summary_preserves_all_collapsed_invoice_details(self) -> None:
        payload = self.service.group_payload(
            "2026-04",
            rows_by_id={
                "etc-summary-batch-1": {
                    "id": "etc-summary-batch-1",
                    "type": "invoice",
                    "object_identity_key": "etc-summary:batch-1",
                    "source_kind": "etc_invoice_summary",
                    "status": "unpaired",
                    "etc_invoice_count": 2,
                    "etc_invoice_detail_rows": [
                        {
                            "id": "etc-invoice-1",
                            "type": "invoice",
                            "source_kind": "etc_invoice",
                            "status": "paired",
                            "amount_value": "12.34",
                        },
                        {
                            "id": "etc-invoice-2",
                            "type": "invoice",
                            "source_kind": "etc_invoice",
                            "status": "paired",
                            "amount_value": "56.78",
                        },
                    ],
                }
            },
            active_relations=[],
        )

        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["display_mode"], "collapsed_summary")
        self.assertTrue(group["default_collapsed"])
        self.assertEqual(group["summary_row"]["id"], "etc-summary-batch-1")
        self.assertEqual(group["summary_row"]["status"], "unpaired")
        self.assertEqual(
            [row["id"] for row in group["collapsed_rows"]["invoice"]],
            ["etc-invoice-1", "etc-invoice-2"],
        )
        self.assertEqual(
            [row["status"] for row in group["collapsed_rows"]["invoice"]],
            ["unpaired", "unpaired"],
        )
        self.assertEqual(group["collapsed_row_counts"], {"invoice": 2})

    def test_etc_summary_count_can_exceed_loaded_preview_rows(self) -> None:
        payload = self.service.group_payload(
            "2026-04",
            rows_by_id={
                "etc-summary-batch-68": {
                    "id": "etc-summary-batch-68",
                    "type": "invoice",
                    "object_identity_key": "etc-summary:batch-68",
                    "source_kind": "etc_invoice_summary",
                    "status": "unpaired",
                    "etc_invoice_count": 68,
                    "etc_invoice_detail_count": 68,
                    "etc_invoice_detail_rows": [
                        {
                            "id": "etc-invoice-1",
                            "type": "invoice",
                            "source_kind": "etc_invoice",
                            "status": "paired",
                            "amount_value": "12.34",
                        }
                    ],
                }
            },
            active_relations=[],
        )

        group = payload["unpaired"]["groups"][0]
        self.assertEqual(
            [row["id"] for row in group["collapsed_rows"]["invoice"]],
            ["etc-invoice-1"],
        )
        self.assertEqual(group["collapsed_row_counts"], {"invoice": 68})

    def test_no_oa_single_pane_relation_is_paired_without_collapsing_rows(self) -> None:
        rows = {
            "bank-a": {"id": "bank-a", "type": "bank", "object_identity_key": "bank-a"},
            "bank-b": {"id": "bank-b", "type": "bank", "object_identity_key": "bank-b"},
        }
        relation = {
            "case_id": "CASE-BANK-BATCH",
            "row_ids": ["bank-a", "bank-b"],
            "row_types": ["bank", "bank"],
            "status": "active",
            "relation_mode": "no_oa_bank_batch",
            "special_metadata": {
                "paired_requires_oa": False,
                "paired_requires_invoice": False,
            },
        }

        payload = self.service.group_payload("2026-05", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["unpaired_count"], 0)
        self.assertEqual(identities(payload["paired"]["groups"]), {("bank", "bank-a"), ("bank", "bank-b")})
        group = payload["paired"]["groups"][0]
        self.assertNotIn("display_mode", group)
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-a", "bank-b"])
        self.assertNotIn("collapsed_rows", group)

    def test_bank_flow_rule_batch_only_collapses_when_more_than_three_rows(self) -> None:
        for row_count, should_collapse in ((3, False), (4, True)):
            with self.subTest(row_count=row_count):
                rows = {
                    f"bank-{index}": {
                        "id": f"bank-{index}",
                        "type": "bank",
                        "object_identity_key": f"bank-{index}",
                        "amount": "10.00",
                    }
                    for index in range(row_count)
                }
                relation = {
                    "case_id": f"CASE-BANK-FLOW-{row_count}",
                    "row_ids": list(rows),
                    "status": "active",
                    "relation_mode": "bank_flow_rule_batch",
                    "special_metadata": {
                        "paired_requires_oa": False,
                        "paired_requires_invoice": False,
                    },
                }

                payload = self.service.group_payload("2026-05", rows_by_id=rows, active_relations=[relation])

                group = payload["paired"]["groups"][0]
                if should_collapse:
                    self.assertEqual(group["display_mode"], "collapsed_summary")
                    self.assertEqual(group["collapsed_row_counts"], {"bank": 4})
                    self.assertEqual(len(group["collapsed_rows"]["bank"]), 4)
                    self.assertEqual(group["bank_rows"][0]["source_kind"], "bank_flow_rule_batch_summary")
                else:
                    self.assertNotIn("display_mode", group)
                    self.assertEqual(len(group["bank_rows"]), 3)
                    self.assertNotIn("collapsed_rows", group)

    def test_bank_relation_required_invoice_stays_grouped_in_unpaired(self) -> None:
        rows = {
            "oa-a": {"id": "oa-a", "type": "oa", "object_identity_key": "oa-a"},
            "bank-a": {"id": "bank-a", "type": "bank", "object_identity_key": "bank-a"},
        }
        relation = {
            "case_id": "case:insurance",
            "row_ids": ["oa-a", "bank-a"],
            "row_types": ["oa", "bank"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "special_metadata": {"requires_oa": True, "requires_invoice": True},
        }

        payload = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["unpaired_count"], 1)
        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["group_type"], "relation")
        self.assertEqual(group["case_id"], "case:insurance")
        self.assertEqual(group["completion"], {"is_complete": False, "missing_row_types": ["invoice"]})
        self.assertEqual(identities([group]), {("oa", "oa-a"), ("bank", "bank-a")})

    def test_turnover_manual_closure_active_bank_only_waits_for_required_oa(self) -> None:
        rows = {
            "bank-in": {"id": "bank-in", "type": "bank", "object_identity_key": "bank-in"},
            "bank-out": {"id": "bank-out", "type": "bank", "object_identity_key": "bank-out"},
        }
        relation = {
            "case_id": "turnover:closure-waiting-oa",
            "row_ids": ["bank-in", "bank-out"],
            "row_types": ["bank", "bank"],
            "status": "active",
            "relation_mode": "turnover_manual_closure",
            "special_metadata": {
                "requires_oa": True,
                "requires_invoice": False,
                "paired_requirement_source": "bank_transaction_paired_policy",
            },
        }

        payload = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual(payload["summary"]["unpaired_count"], 1)
        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["case_id"], "turnover:closure-waiting-oa")
        self.assertEqual(group["completion"], {"is_complete": False, "missing_row_types": ["oa"]})
        self.assertEqual(identities(payload["paired"]["groups"]), set())
        self.assertEqual(identities([group]), {("bank", "bank-in"), ("bank", "bank-out")})

    def test_turnover_manual_closure_uses_payment_leg_instead_of_zero_net(self) -> None:
        rows = {
            "oa-240000": {
                "id": "oa-240000",
                "type": "oa",
                "object_identity_key": "oa-240000",
                "amount": "240000.00",
                "apply_type": "支付申请",
            },
            "bank-in": {
                "id": "bank-in",
                "type": "bank",
                "object_identity_key": "bank-in",
                "credit_amount": "240000.00",
            },
            "bank-out": {
                "id": "bank-out",
                "type": "bank",
                "object_identity_key": "bank-out",
                "debit_amount": "240000.00",
            },
        }
        relation = {
            "case_id": "turnover:closure-240000",
            "row_ids": list(rows),
            "row_types": ["oa", "bank", "bank"],
            "status": "active",
            "relation_mode": "turnover_manual_closure",
            "special_metadata": {"requires_oa": True, "requires_invoice": False},
            "amount_check": {},
        }

        payload = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        group = payload["paired"]["groups"][0]
        self.assertNotIn("workbench_anomaly", group)
        self.assertEqual(group["amount_check"]["status"], "matched")
        self.assertEqual(group["amount_check"]["bank_total"], "240000.00")
        self.assertEqual(group["amount_check"]["bank_net_total"], "0.00")

    def test_in_progress_oa_keeps_materially_complete_case_unpaired_until_same_oa_completes(self) -> None:
        rows = {
            "oa-progress": {
                "id": "oa-progress",
                "type": "oa",
                "object_identity_key": "oa-progress",
                "workflow_status": "in_progress",
            },
            "bank-1": {"id": "bank-1", "type": "bank", "object_identity_key": "bank-1"},
            "invoice-1": {"id": "invoice-1", "type": "invoice", "object_identity_key": "invoice-1"},
        }
        relation = {
            "case_id": "case:stable",
            "row_ids": ["oa-progress", "bank-1", "invoice-1"],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "special_metadata": {"requires_oa": True, "requires_invoice": True},
        }

        in_progress = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(in_progress["summary"]["paired_count"], 0)
        group = in_progress["unpaired"]["groups"][0]
        self.assertEqual(group["case_id"], "case:stable")
        self.assertEqual(group["completion"]["missing_row_types"], [])
        self.assertEqual(group["completion"]["blocking_reasons"], ["oa_in_progress"])

        rows["oa-progress"]["workflow_status"] = "completed"
        completed = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(completed["summary"]["paired_count"], 1)
        self.assertEqual(completed["paired"]["groups"][0]["case_id"], "case:stable")

    def test_any_in_progress_oa_blocks_multi_oa_case(self) -> None:
        completion = evaluate_bank_relation_completion(
            row_types=["oa", "oa", "bank"],
            oa_workflow_statuses=["completed", "in_progress"],
            special_metadata={"requires_oa": True, "requires_invoice": False},
        )

        self.assertEqual(completion["missing_row_types"], [])
        self.assertEqual(completion["blocking_reasons"], ["oa_in_progress"])
        self.assertFalse(completion["is_complete"])

    def test_bank_policy_requirement_matrix_and_required_type_completion(self) -> None:
        cases = [
            (True, False, ["oa"]),
            (False, True, ["invoice"]),
            (True, True, ["oa", "invoice"]),
            (False, False, []),
        ]
        for requires_oa, requires_invoice, missing in cases:
            with self.subTest(requires_oa=requires_oa, requires_invoice=requires_invoice):
                metadata = build_bank_relation_requirement_metadata(
                    tag_codes=["policy-tag"],
                    rules_payload={
                        "version": 7,
                        "requirements_by_tag_code": {
                            "policy-tag": {
                                "requires_oa": requires_oa,
                                "requires_invoice": requires_invoice,
                            }
                        },
                    },
                )

                incomplete = evaluate_bank_relation_completion(
                    row_types=["bank"],
                    special_metadata=metadata,
                )
                complete = evaluate_bank_relation_completion(
                    row_types=[
                        "bank",
                        *(("oa",) if requires_oa else ()),
                        *(("invoice",) if requires_invoice else ()),
                    ],
                    special_metadata=metadata,
                )

                self.assertEqual(incomplete["missing_row_types"], missing)
                self.assertEqual(complete, {"is_complete": True, "missing_row_types": []})

    def test_bank_policy_multiple_tags_or_requirements_and_unknowns_fail_closed(self) -> None:
        rules_payload = {
            "version": 9,
            "requirements_by_tag_code": {
                "requires-oa": {"requires_oa": True, "requires_invoice": False},
                "requires-invoice": {"requires_oa": False, "requires_invoice": True},
                "requires-neither": {"requires_oa": False, "requires_invoice": False},
            },
        }

        combined = build_bank_relation_requirement_metadata(
            tag_codes=["requires-oa", "requires-neither", "requires-invoice", "requires-oa"],
            rules_payload=rules_payload,
        )
        unknown = build_bank_relation_requirement_metadata(
            tag_codes=["requires-neither", "unknown-tag"],
            rules_payload=rules_payload,
        )
        empty = build_bank_relation_requirement_metadata(tag_codes=[], rules_payload=rules_payload)
        partially_missing = build_bank_relation_requirement_metadata(
            tag_codes=["requires-neither", ""],
            rules_payload=rules_payload,
        )
        missing_rules = build_bank_relation_requirement_metadata(
            tag_codes=["requires-neither"],
            rules_payload={},
        )

        self.assertEqual(combined["paired_requirement_tag_codes"], ["requires-oa", "requires-neither", "requires-invoice"])
        self.assertTrue(combined["requires_oa"])
        self.assertTrue(combined["requires_invoice"])
        for metadata in (unknown, empty, missing_rules):
            self.assertTrue(metadata["requires_oa"])
            self.assertTrue(metadata["requires_invoice"])
        self.assertEqual(partially_missing["paired_requirement_tag_codes"], ["requires-neither"])
        self.assertTrue(partially_missing["requires_oa"])
        self.assertTrue(partially_missing["requires_invoice"])

    def test_only_batch_accounting_source_bypasses_bank_completion_requirements(self) -> None:
        self.assertEqual(
            evaluate_bank_relation_completion(
                row_types=["oa", "invoice"],
                special_metadata={"source": "batch_accounting"},
                relation_mode="manual_confirmed",
            ),
            {"is_complete": True, "missing_row_types": []},
        )

    def test_etc_batch_identity_does_not_bypass_bank_completion_requirements(self) -> None:
        for metadata, amount_check in [
            (
                {
                    "etc_batch_link": {"external_etc_batch_id": "etc-1"},
                    "requires_oa": True,
                    "requires_invoice": False,
                },
                {},
            ),
            (
                {
                    "external_etc_batch_id": "etc-2",
                    "requires_oa": True,
                    "requires_invoice": False,
                },
                {"etc_batch_id": "etc-2"},
            ),
        ]:
            with self.subTest(metadata=metadata, amount_check=amount_check):
                self.assertEqual(
                    evaluate_bank_relation_completion(
                        row_types=["bank", "invoice"],
                        special_metadata=metadata,
                        relation_mode="manual_confirmed",
                        amount_check=amount_check,
                    ),
                    {"is_complete": False, "missing_row_types": ["oa"]},
                )

    def test_ordinary_oa_relation_without_bank_is_incomplete(self) -> None:
        self.assertEqual(
            evaluate_bank_relation_completion(
                row_types=["oa", "invoice"],
                special_metadata={"source": "oa_attachment_invoice"},
            ),
            {"is_complete": False, "missing_row_types": ["bank"]},
        )

    def test_bank_relation_missing_requirement_metadata_fails_closed(self) -> None:
        rows = {
            "oa-a": {"id": "oa-a", "type": "oa", "object_identity_key": "oa-a"},
            "bank-a": {"id": "bank-a", "type": "bank", "object_identity_key": "bank-a"},
        }
        relation = {
            "case_id": "case:missing-policy",
            "row_ids": ["oa-a", "bank-a"],
            "row_types": ["oa", "bank"],
            "status": "active",
        }

        payload = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["completion"]["missing_row_types"], ["invoice"])

    def test_bank_relation_enters_paired_after_required_invoice_is_present(self) -> None:
        rows = {
            "oa-a": {"id": "oa-a", "type": "oa", "object_identity_key": "oa-a"},
            "bank-a": {"id": "bank-a", "type": "bank", "object_identity_key": "bank-a"},
            "invoice-a": {"id": "invoice-a", "type": "invoice", "object_identity_key": "invoice-a"},
        }
        relation = {
            "case_id": "case:complete-insurance",
            "row_ids": ["oa-a", "bank-a", "invoice-a"],
            "row_types": ["oa", "bank", "invoice"],
            "status": "active",
            "special_metadata": {"requires_oa": True, "requires_invoice": True},
        }

        payload = self.service.group_payload("2026-06", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["paired"]["groups"][0]["completion"]["missing_row_types"], [])

    def test_attachment_invoice_display_item_id_uses_canonical_oa_alias_and_exact_row_index(self) -> None:
        original_source_item_id = (
            "oa-exp-6a0ee8613bb8164165d8c61a:item:2:9ca59ea6e4ab"
        )
        rows = {
            "oa-exp-2206": {
                "id": "oa-exp-2206",
                "type": "oa",
                "object_identity_key": "oa-exp-2206",
                "detail_fields": {"Mongo文档ID": "6a0ee8613bb8164165d8c61a"},
                "expense_items": [
                    {
                        "id": "oa-exp-2206:item:2:5f9f908c6e6d",
                        "row_index": "2",
                        "project_name": "曲靖卷烟厂项目",
                        "amount": "60.00",
                    }
                ],
            },
            "inv_imported_0058": {
                "id": "inv_imported_0058",
                "type": "invoice",
                "object_identity_key": "inv_imported_0058",
                "source_kind": "oa_attachment_invoice",
                "source_expense_item_id": original_source_item_id,
                "source_expense_row_index": "2",
            },
        }
        relation = {
            "case_id": "CASE-OA-ATT-2206",
            "row_ids": list(rows),
            "row_types": ["oa", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
        }

        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[relation],
        )

        self.assertEqual(payload["summary"]["paired_count"], 0)
        group = payload["unpaired"]["groups"][0]
        self.assertEqual(group["completion"], {"is_complete": False, "missing_row_types": ["bank"]})
        invoice = group["invoice_rows"][0]
        self.assertEqual(
            invoice["source_expense_item_ids"],
            ["oa-exp-2206:item:2:5f9f908c6e6d"],
        )
        self.assertEqual(invoice["source_oa_id"], "oa-exp-2206")
        self.assertEqual(rows["inv_imported_0058"]["source_expense_item_id"], original_source_item_id)

    def test_shared_attachment_invoice_keeps_both_expense_item_sources_without_false_anomaly(self) -> None:
        rows = {
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "object_identity_key": "oa-1",
                "amount": "36.00",
                "apply_type": "日常报销",
                "expense_items": [
                    {
                        "id": "oa-1:item:0",
                        "row_index": "0",
                        "amount": "18.00",
                        "attachment_file_count": "1",
                    },
                    {
                        "id": "oa-1:item:1",
                        "row_index": "1",
                        "amount": "18.00",
                        "attachment_file_count": "1",
                    },
                ],
            },
            "bank-1": {
                "id": "bank-1",
                "type": "bank",
                "object_identity_key": "bank-1",
                "amount": "36.00",
                "direction": "expense",
            },
            "invoice-36": {
                "id": "invoice-36",
                "type": "invoice",
                "object_identity_key": "invoice-36",
                "source_kind": "oa_attachment_invoice",
                "total_with_tax": "36.00",
                "source_links": [
                    {
                        "source_type": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                        "source_expense_item_id": "oa-1:item:0",
                        "source_expense_row_index": "0",
                    },
                    {
                        "source_type": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                        "source_expense_item_id": "oa-1:item:1",
                        "source_expense_row_index": "1",
                    },
                ],
            },
        }

        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[{
                "case_id": "CASE-SHARED-INVOICE",
                "row_ids": list(rows),
                "row_types": ["oa", "bank", "invoice"],
                "status": "active",
                "relation_mode": "manual_confirmed",
            }],
        )

        group = payload["paired"]["groups"][0]
        self.assertEqual(
            group["invoice_rows"][0]["source_expense_item_ids"],
            ["oa-1:item:0", "oa-1:item:1"],
        )
        self.assertNotIn("workbench_anomaly", group)

    def test_relation_display_amount_check_replaces_stale_gross_total_with_net_total(self) -> None:
        rows = {
            "oa-1015": {
                "id": "oa-1015",
                "type": "oa",
                "amount": "1015",
                "object_identity_key": "oa-1015",
            },
            "bank-payment": {
                "id": "bank-payment",
                "type": "bank",
                "debit_amount": "1050",
                "object_identity_key": "bank-payment",
            },
            "bank-refund": {
                "id": "bank-refund",
                "type": "bank",
                "credit_amount": "35",
                "object_identity_key": "bank-refund",
            },
            "invoice-1015": {
                "id": "invoice-1015",
                "type": "invoice",
                "invoice_type": "input",
                "total_with_tax": "1015",
                "object_identity_key": "invoice-1015",
            },
        }
        relation = {
            "case_id": "CASE-NET-1015",
            "row_ids": list(rows),
            "row_types": ["oa", "bank", "bank", "invoice"],
            "status": "active",
            "relation_mode": "manual_confirmed",
            "special_metadata": {"requires_oa": True, "requires_invoice": True},
            "amount_check": {
                "status": "mismatch",
                "oa_total": "1015.00",
                "bank_total": "1050.00",
                "invoice_total": "1015.00",
                "amount_delta": "35.00",
                "requires_note": True,
            },
        }

        payload = self.service.group_payload(
            "all",
            rows_by_id=rows,
            active_relations=[relation],
        )

        group = payload["paired"]["groups"][0]
        self.assertNotIn("workbench_anomaly", group)
        self.assertEqual(group["amount_check"]["status"], "matched")
        self.assertEqual(group["amount_check"]["bank_gross_total"], "1050.00")
        self.assertEqual(group["amount_check"]["bank_contra_total"], "35.00")
        self.assertEqual(group["amount_check"]["bank_total"], "1015.00")
        self.assertEqual(group["amount_check"]["amount_delta"], "0.00")
        self.assertFalse(group["amount_check"]["requires_note"])
        for row_type in ("oa", "bank", "invoice"):
            for row in group[f"{row_type}_rows"]:
                self.assertEqual(row["relation_amount_check"]["status"], "matched")
                self.assertEqual(row["relation_amount_check"]["bank_total"], "1015.00")

    def test_input_order_and_decorations_do_not_change_membership_or_group_ids(self) -> None:
        batch = yunnan_lifu_520_fixture()
        base_rows = [row_for_fact(fact) for fact in batch.facts]
        relation = active_relation(batch)
        expected = None
        for seed in range(8):
            shuffled = deepcopy(base_rows)
            random.Random(seed).shuffle(shuffled)
            shuffled[0]["tags"] = [f"decoration-{seed}"]
            payload = self.service.group_payload(
                "2026-05",
                rows_by_id={str(row["id"]): row for row in shuffled},
                active_relations=[relation],
            )
            current = (
                [group["group_id"] for group in payload["paired"]["groups"]],
                identities(payload["paired"]["groups"]),
                identities(payload["unpaired"]["groups"]),
            )
            expected = current if expected is None else expected
            self.assertEqual(current, expected)

    def test_missing_or_duplicate_canonical_identity_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing object_identity_key"):
            self.service.group_payload(
                "2026-05",
                rows_by_id={"oa-a": {"id": "oa-a", "type": "oa"}},
                active_relations=[],
            )
        with self.assertRaisesRegex(ValueError, "represented by multiple rows"):
            self.service.group_payload(
                "2026-05",
                rows_by_id={
                    "invoice-a": {"id": "invoice-a", "type": "invoice", "object_identity_key": "invoice-no"},
                    "invoice-b": {"id": "invoice-b", "type": "invoice", "object_identity_key": "invoice-no"},
                },
                active_relations=[],
            )

    def test_anomaly_blocks_pairing_until_review_accepts_current_fingerprint(self) -> None:
        rows = {
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "object_identity_key": "oa-1",
                "amount": "100.00",
                "apply_type": "付款",
            },
            "invoice-1": {
                "id": "invoice-1",
                "type": "invoice",
                "object_identity_key": "invoice-1",
                "total_with_tax": "99.99",
                "invoice_type": "input",
            },
            "bank-1": {
                "id": "bank-1",
                "type": "bank",
                "object_identity_key": "bank-1",
                "amount": "100.00",
                "direction": "expense",
            },
        }
        relation = {
            "case_id": "CASE-AMOUNT-1",
            "row_ids": list(rows),
            "row_types": ["oa", "invoice", "bank"],
            "status": "active",
            "relation_mode": "manual_confirmed",
        }

        active_payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[relation],
        )
        active_group = active_payload["unpaired"]["groups"][0]
        fingerprint = active_group["workbench_anomaly"]["fingerprint"]
        self.assertEqual(active_payload["summary"]["unpaired_exception_count"], 1)
        self.assertEqual(active_payload["summary"]["paired_exception_count"], 0)
        self.assertEqual(active_group["workbench_anomaly"]["review_decision"], "pending")
        self.assertEqual(
            {item["display_label"] for item in active_group["workbench_anomaly"]["items"]},
            {"OA发票金额不一致", "流水发票金额不一致"},
        )
        self.assertIn("anomaly_review_required", active_group["completion"]["blocking_reasons"])
        self.assertNotIn("amount_anomaly", active_group["invoice_rows"][0])

        accepted_payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[relation],
            anomaly_review_decisions={
                fingerprint: {
                    "decision": "accept_paired",
                    "reviewed_item_fingerprints": [
                        item["fingerprint"]
                        for item in active_group["workbench_anomaly"]["items"]
                    ],
                    "reviewed_by": "reviewer",
                }
            },
        )
        accepted_group = accepted_payload["paired"]["groups"][0]
        self.assertEqual(accepted_payload["summary"]["unpaired_exception_count"], 0)
        self.assertEqual(accepted_payload["summary"]["paired_exception_count"], 1)
        self.assertEqual(
            accepted_group["workbench_anomaly"]["review_decision"],
            "accept_paired",
        )
        self.assertEqual(
            {item["display_label"] for item in accepted_group["workbench_anomaly"]["items"]},
            {"已接受：OA发票金额不一致", "已接受：流水发票金额不一致"},
        )

    def test_uploaded_expense_item_without_parsed_invoice_is_an_active_group_exception(self) -> None:
        rows = {
                "oa-1": {
                    "id": "oa-1",
                    "type": "oa",
                    "object_identity_key": "oa-1",
                    "amount": "38.00",
                    "apply_type": "日常报销",
                    "expense_items": [{
                        "id": "oa-1:item:0",
                        "amount": "38.00",
                        "attachment_file_count": "1",
                    }],
                },
                "bank-1": {
                    "id": "bank-1",
                    "type": "bank",
                    "object_identity_key": "bank-1",
                    "amount": "38.00",
                    "direction": "expense",
                },
            }
        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[{
                "case_id": "CASE-MISSING-1",
                "row_ids": list(rows),
                "row_types": ["oa", "bank"],
                "status": "active",
                "relation_mode": "manual_confirmed",
                "special_metadata": {"requires_oa": True, "requires_invoice": True},
            }],
        )

        group = payload["unpaired"]["groups"][0]
        item = group["workbench_anomaly"]["items"][0]
        self.assertEqual(payload["summary"]["unpaired_exception_count"], 1)
        self.assertEqual(group["workbench_anomaly"]["review_decision"], "pending")
        self.assertEqual(item["code"], "oa_invoice_attachment_unparsed")
        self.assertEqual(item["display_label"], "OA发票附件未解析")
        self.assertEqual(item["source_expense_item_ids"], ["oa-1:item:0"])
        self.assertEqual(item["invoice_row_ids"], [])
class WorkbenchRelationPreviewGroupingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchRelationPreviewGroupingService(
            serialize_value=deepcopy,
            row_type_for_row_id=lambda row_id: str(row_id).split("-", 1)[0],
            derive_row_tags=lambda row, group, relation: [
                str(relation.get("relation_mode") or "formal")
            ],
        )

    def test_formal_origin_does_not_change_paired_visibility_and_unpaired_rows_remain_visible(
        self,
    ) -> None:
        selected_rows = [
            {"id": "oa-1", "type": "oa"},
            {"id": "invoice-1", "type": "invoice"},
            {"id": "bank-1", "type": "bank"},
        ]

        for relation_mode in ("manual_confirmed", "automatic_match", "historical_import"):
            groups = self.service.group_relations(
                [
                    {
                        "case_id": "decision:historical-1",
                        "row_ids": ["oa-1", "invoice-1"],
                        "row_types": ["oa", "invoice"],
                        "status": "active",
                        "relation_mode": relation_mode,
                    }
                ],
                selected_rows=selected_rows,
            )

            self.assertEqual(len(groups), 2)
            relation_group, bank_group = groups
            self.assertEqual(relation_group["group_id"], "case:decision:historical-1")
            self.assertEqual(relation_group["group_type"], "relation")
            self.assertEqual(relation_group["zone"], "unpaired")
            self.assertEqual(relation_group["status"], "unpaired")
            self.assertEqual(relation_group["completion"]["missing_row_types"], ["bank"])
            self.assertEqual([row["status"] for row in relation_group["oa_rows"]], ["unpaired"])
            self.assertEqual([row["status"] for row in relation_group["invoice_rows"]], ["unpaired"])
            self.assertEqual(bank_group["group_type"], "selection")
            self.assertEqual(bank_group["zone"], "unpaired")
            self.assertEqual(bank_group["status"], "unpaired")
            self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["bank-1"])
            self.assertEqual([row["status"] for row in bank_group["bank_rows"]], ["unpaired"])

    def test_invalid_preview_contract_fails_fast(self) -> None:
        with self.assertRaisesRegex(ValueError, "ungrouped_selected_rows"):
            self.service.group_relations(
                [],
                selected_rows=[],
                ungrouped_selected_rows="hidden",
            )
        with self.assertRaisesRegex(ValueError, "Unsupported Workbench row type"):
            self.service.group_relations(
                [],
                selected_rows=[{"id": "other-1", "type": "other"}],
                ungrouped_selected_rows="individual",
            )

    def test_incomplete_bank_relation_preview_stays_in_unpaired(self) -> None:
        groups = self.service.group_relations(
            [
                {
                    "case_id": "case:incomplete-preview",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                    "special_metadata": {"requires_oa": True, "requires_invoice": True},
                }
            ],
            selected_rows=[
                {"id": "oa-1", "type": "oa"},
                {"id": "bank-1", "type": "bank"},
            ],
        )

        self.assertEqual(groups[0]["zone"], "unpaired")
        self.assertEqual(groups[0]["completion"]["missing_row_types"], ["invoice"])
        self.assertEqual([row["status"] for row in groups[0]["bank_rows"]], ["unpaired"])


if __name__ == "__main__":
    unittest.main()
