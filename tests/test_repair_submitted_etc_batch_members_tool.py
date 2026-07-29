from __future__ import annotations

import json
import unittest
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories.submitted_etc_batch_member_repair import (
    build_submitted_etc_batch_member_repair_plan,
)
from fin_ops_platform.tools.repair_submitted_etc_batch_members import main

INVOICE_SPECS = [
    {"invoice_number": "1001", "plate_number": "云A1"},
    {"invoice_number": "1002", "plate_number": "云A1"},
    {"invoice_number": "1003", "plate_number": "云B2"},
    {"invoice_number": "1004", "plate_number": "云B2"},
]


def _snapshot() -> dict:
    current = [
        {
            "etc_invoice_id": "etc_invoice_0639",
            "invoice_number": "old-1",
            "invoice_date": "2026-06-01",
            "total_with_tax": Decimal("40.00"),
            "plate_number": "云A1",
        },
        {
            "etc_invoice_id": "etc_invoice_0640",
            "invoice_number": "old-2",
            "invoice_date": "2026-06-02",
            "total_with_tax": Decimal("60.00"),
            "plate_number": "云B2",
        },
    ]
    current_ids = [row["etc_invoice_id"] for row in current]
    canonical = [
        {
            "invoice_id": f"canonical-{index}",
            "legacy_invoice_id": f"legacy-{index}",
            "invoice_number": number,
            "invoice_date": "2026-06-28",
            "amount": amount - Decimal("0.10"),
            "tax_amount": Decimal("0.10"),
            "total_with_tax": amount,
            "status": "pending",
            "etc_invoice_id": None,
            "workbench_visibility": "visible",
        }
        for index, (number, amount) in enumerate(
            [
                ("1001", Decimal("23.50")),
                ("1002", Decimal("23.50")),
                ("1003", Decimal("3.24")),
                ("1004", Decimal("4.22")),
            ],
            start=1,
        )
    ]
    return {
        "business_batch": {
            "business_batch_id": "business-1",
            "task_id": "task-1",
            "status": "manually_marked_submitted",
            "scope_month": "2026-07-01",
            "invoice_count": 6,
            "total_amount": Decimal("154.46"),
            "version": 12,
            "raw_payload": {"normalized_payload": {"invoice_ids": current_ids}},
            "payload": {
                "invoice_ids": current_ids,
                "submission_batch_id": "submission-1",
                "external_etc_batch_id": "etc-1",
                "oa_draft_id": "draft-1",
            },
        },
        "submission_batch": {
            "submission_batch_id": "submission-1",
            "status": "submitted_confirmed",
            "invoice_ids": current_ids,
            "version": 1,
            "raw_payload": {"normalized_payload": {"invoice_ids": current_ids}},
            "payload": {
                "invoice_ids": current_ids,
                "etc_batch_id": "etc-1",
                "oa_draft_id": "draft-1",
            },
        },
        "reconciliation_task": {
            "task_id": "task-1",
            "status": "closed",
            "version": 22,
            "result_summary": {"etc_invoice_count": 6, "etc_invoice_amount": "154.46"},
            "raw_payload": {"normalized_payload": {"status": "closed"}},
            "payload": {"status": "closed"},
        },
        "canonical_targets": canonical,
        "current_etc_invoices": current,
        "target_etc_invoices": [],
        "active_links": [],
        "max_etc_invoice_counter": 640,
    }


def _plan(snapshot: dict) -> dict:
    return build_submitted_etc_batch_member_repair_plan(
        snapshot,
        business_batch_id="business-1",
        submission_batch_id="submission-1",
        external_etc_batch_id="etc-1",
        invoice_specs=INVOICE_SPECS,
        expected_target_total=Decimal("54.46"),
        expected_result_count=6,
        expected_result_total=Decimal("154.46"),
    )


class SubmittedEtcBatchMemberRepairPlanTests(unittest.TestCase):
    def test_ready_plan_is_exact_and_fingerprint_guarded(self) -> None:
        plan = _plan(_snapshot())

        self.assertEqual(plan["status"], "ready")
        self.assertEqual(plan["blocking_reasons"], [])
        self.assertEqual(plan["scope_months"], ["2026-06", "2026-07"])
        self.assertEqual(
            [item["etc_invoice_id"] for item in plan["planned_invoices"]],
            ["etc_invoice_0641", "etc_invoice_0642", "etc_invoice_0643", "etc_invoice_0644"],
        )
        self.assertEqual(len(plan["fingerprint"]), 64)

    def test_partial_repair_fails_closed(self) -> None:
        snapshot = _snapshot()
        snapshot["canonical_targets"][0]["etc_invoice_id"] = "etc_invoice_0641"
        snapshot["canonical_targets"][0]["workbench_visibility"] = "hidden_after_etc_submission"

        plan = _plan(snapshot)

        self.assertEqual(plan["status"], "blocked")
        self.assertIn("partial_repair_state", plan["blocking_reasons"])

    def test_fully_repaired_state_is_idempotent(self) -> None:
        snapshot = _snapshot()
        new_rows = []
        links = []
        for offset, canonical in enumerate(snapshot["canonical_targets"], start=1):
            etc_invoice_id = f"etc_invoice_{640 + offset:04d}"
            canonical["etc_invoice_id"] = etc_invoice_id
            canonical["workbench_visibility"] = "hidden_after_etc_submission"
            new_rows.append(
                {
                    "etc_invoice_id": etc_invoice_id,
                    "invoice_number": canonical["invoice_number"],
                    "invoice_date": canonical["invoice_date"],
                    "total_with_tax": canonical["total_with_tax"],
                    "plate_number": INVOICE_SPECS[offset - 1]["plate_number"],
                    "business_batch_id": "business-1",
                }
            )
            links.append(
                {
                    "invoice_id": canonical["invoice_id"],
                    "business_batch_id": "business-1",
                    "etc_invoice_id": etc_invoice_id,
                }
            )
        snapshot["current_etc_invoices"].extend(new_rows)
        snapshot["target_etc_invoices"] = new_rows
        snapshot["active_links"] = links
        all_ids = [row["etc_invoice_id"] for row in snapshot["current_etc_invoices"]]
        snapshot["business_batch"]["payload"]["invoice_ids"] = all_ids
        snapshot["submission_batch"]["invoice_ids"] = all_ids
        snapshot["submission_batch"]["payload"]["invoice_ids"] = all_ids

        plan = _plan(snapshot)

        self.assertEqual(plan["status"], "already_repaired")
        self.assertEqual(plan["blocking_reasons"], [])


class RepairSubmittedEtcBatchMembersToolTests(unittest.TestCase):
    def test_execute_uses_preview_fingerprint_and_refreshes_only_reported_scopes(self) -> None:
        preview = _plan(_snapshot())
        repository = SimpleNamespace(
            preview=lambda **_kwargs: preview,
            apply=lambda **_kwargs: {
                **preview,
                "status": "already_repaired",
                "applied": True,
                "updated_count": 4,
            },
        )
        refresh_calls: list[tuple[object, list[str], str]] = []
        app = object()
        args = [
            "--business-batch-id",
            "business-1",
            "--submission-batch-id",
            "submission-1",
            "--external-etc-batch-id",
            "etc-1",
            *sum((["--invoice", f"{item['invoice_number']}={item['plate_number']}"] for item in INVOICE_SPECS), []),
            "--expected-target-total",
            "54.46",
            "--expected-result-count",
            "6",
            "--expected-result-total",
            "154.46",
            "--execute",
            "--expected-fingerprint",
            preview["fingerprint"],
            "--operator",
            "ops",
            "--reason",
            "approved repair",
        ]
        with (
            patch(
                "fin_ops_platform.tools.repair_submitted_etc_batch_members.PostgresSettings.from_env"
            ),
            patch(
                "fin_ops_platform.tools.repair_submitted_etc_batch_members.PostgresConnection"
            ),
            patch(
                "fin_ops_platform.tools.repair_submitted_etc_batch_members.SubmittedEtcBatchMemberRepairRepository",
                return_value=repository,
            ),
            patch(
                "fin_ops_platform.tools.repair_submitted_etc_batch_members.build_tool_runtime_application",
                return_value=app,
            ),
            patch(
                "fin_ops_platform.tools.repair_submitted_etc_batch_members.refresh_after_historical_etc_repair_link",
                side_effect=lambda runtime, months, *, reason: refresh_calls.append(
                    (runtime, months, reason)
                ),
            ),
        ):
            output = StringIO()
            self.assertEqual(main(args, stdout=output), 0)

        report = json.loads(output.getvalue())
        self.assertEqual(report["updated_count"], 4)
        self.assertEqual(
            refresh_calls,
            [(app, ["2026-06", "2026-07"], "submitted_etc_batch_members_repaired")],
        )


if __name__ == "__main__":
    unittest.main()
