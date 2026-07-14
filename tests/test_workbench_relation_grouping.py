from __future__ import annotations

from copy import deepcopy
import random
import unittest

from fin_ops_platform.services.workbench_relation_grouping import (
    WorkbenchRelationGroupingService,
    WorkbenchRelationPreviewGroupingService,
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

    def test_520_historical_case_prefix_is_paired_without_reclassification(self) -> None:
        batch = yunnan_lifu_520_fixture()
        rows = {fact.row_id: row_for_fact(fact) for fact in batch.facts}

        payload = self.service.group_payload(
            "2026-05",
            rows_by_id=rows,
            active_relations=[active_relation(batch)],
        )

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["unpaired_count"], 0)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_id"], f"case:{YUNNAN_LIFU_CASE_ID}")
        self.assertEqual(group["group_type"], "relation")
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
        }

        payload = self.service.group_payload("2026-05", rows_by_id=rows, active_relations=[relation])

        paired = identities(payload["paired"]["groups"])
        unpaired = identities(payload["unpaired"]["groups"])
        canonical = {(str(row["type"]), str(row["object_identity_key"])) for row in rows.values()}
        self.assertEqual(paired, {("oa", "oa-a"), ("bank", "bank-a")})
        self.assertEqual(unpaired, {("invoice", "invoice-a")})
        self.assertFalse(paired & unpaired)
        self.assertEqual(paired | unpaired, canonical)

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

    def test_single_pane_active_relation_is_still_paired(self) -> None:
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
        }

        payload = self.service.group_payload("2026-05", rows_by_id=rows, active_relations=[relation])

        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(payload["summary"]["unpaired_count"], 0)
        self.assertEqual(identities(payload["paired"]["groups"]), {("bank", "bank-a"), ("bank", "bank-b")})
        self.assertEqual(payload["paired"]["groups"][0]["display_mode"], "collapsed_summary")

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
            paired, unpaired = groups
            self.assertEqual(paired["group_id"], "case:decision:historical-1")
            self.assertEqual(paired["group_type"], "relation")
            self.assertEqual(paired["zone"], "paired")
            self.assertEqual(paired["status"], "paired")
            self.assertEqual([row["status"] for row in paired["oa_rows"]], ["paired"])
            self.assertEqual([row["status"] for row in paired["invoice_rows"]], ["paired"])
            self.assertEqual(unpaired["group_type"], "selection")
            self.assertEqual(unpaired["zone"], "unpaired")
            self.assertEqual(unpaired["status"], "unpaired")
            self.assertEqual([row["id"] for row in unpaired["bank_rows"]], ["bank-1"])
            self.assertEqual([row["status"] for row in unpaired["bank_rows"]], ["unpaired"])

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


if __name__ == "__main__":
    unittest.main()
