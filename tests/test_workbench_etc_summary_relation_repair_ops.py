from __future__ import annotations

from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import workbench_etc_summary_relation_repair_ops as repair_ops


def _relation(*, marker: str | None = None, include_summary: bool = True) -> dict[str, object]:
    metadata: dict[str, object] = {"requires_oa": True, "requires_invoice": True}
    if marker:
        metadata["external_etc_batch_id"] = marker
    return {
        "case_id": "CASE-AUTO-0084",
        "status": "active",
        "relation_mode": "manual_confirmed",
        "month_scope": "2026-07",
        "row_ids": [
            "oa-1",
            "bank-1",
            *(["etc-summary-etc_20260720_001"] if include_summary else []),
        ],
        "row_types": ["oa", "bank", *(["invoice"] if include_summary else [])],
        "special_metadata": metadata,
        "updated_at": "2026-07-30T09:00:00+08:00",
    }


class _CommandService:
    def __init__(self, relation: dict[str, object]) -> None:
        self.relation = deepcopy(relation)
        self.histories: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []

    def list_active_relations(self) -> list[dict[str, object]]:
        return [deepcopy(self.relation)]

    def list_history(self) -> list[dict[str, object]]:
        return deepcopy(self.histories)

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.updates.append(deepcopy(kwargs))
        before = deepcopy(self.relation)
        self.relation = {
            **deepcopy(self.relation),
            "row_ids": deepcopy(kwargs["row_ids"]),
            "row_types": deepcopy(kwargs["row_types"]),
            "relation_mode": kwargs["relation_mode"],
            "month_scope": kwargs["month_scope"],
            "amount_check": deepcopy(kwargs["amount_check"]),
            "special_metadata": deepcopy(kwargs["special_metadata"]),
            "evidence": deepcopy(kwargs["evidence"]),
            "oa_exemption": deepcopy(kwargs["oa_exemption"]),
            "display_tags": deepcopy(kwargs["display_tags"]),
        }
        self.relation["updated_at"] = f"2026-07-30T09:{len(self.histories) + 1:02d}:00+08:00"
        self.histories.append(
            {
                "operation_type": kwargs["history_operation_type"],
                "created_by": kwargs["actor_id"],
                "note": kwargs["history_note"],
                "before_relations": [before],
                "after_relations": [deepcopy(self.relation)],
            }
        )
        return {"affected_months": ["2026-07"]}


def _run(command: _CommandService, argv: list[str]) -> dict[str, object]:
    output = io.StringIO()
    with (
        patch.object(repair_ops, "build_tool_runtime_application", return_value=object()),
        patch.object(repair_ops, "workbench_relation_command_service", return_value=command),
        patch.object(repair_ops, "persist_workbench_pair_relations"),
    ):
        repair_ops.main(argv, stdout=output)
    return json.loads(output.getvalue())


def _args(mode: str, fingerprint: str | None = None) -> list[str]:
    values = [
        "--case-id",
        "CASE-AUTO-0084",
        "--external-etc-batch-id",
        "etc_20260720_001",
        mode,
    ]
    if fingerprint:
        values.extend(["--expected-fingerprint", fingerprint])
    return values


class WorkbenchEtcSummaryRelationRepairOpsTests(unittest.TestCase):
    def test_execute_is_fingerprint_guarded_and_idempotent(self) -> None:
        command = _CommandService(_relation())
        fingerprint = str(_run(command, _args("--dry-run"))["source_fingerprint"])

        applied = _run(command, _args("--execute", fingerprint))
        replay = _run(command, _args("--execute", fingerprint))

        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(replay["written_relation_count"], 0)
        self.assertTrue(replay["already_applied"])
        self.assertEqual(
            command.relation["special_metadata"]["external_etc_batch_id"],
            "etc_20260720_001",
        )
        self.assertEqual(len(command.updates), 1)

    def test_execute_adds_missing_summary_member_from_exact_relation_marker(self) -> None:
        command = _CommandService(
            _relation(marker="etc_20260720_001", include_summary=False)
        )
        fingerprint = str(_run(command, _args("--dry-run"))["source_fingerprint"])

        applied = _run(command, _args("--execute", fingerprint))

        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(
            command.relation["row_ids"],
            ["oa-1", "bank-1", "etc-summary-etc_20260720_001"],
        )
        self.assertEqual(command.relation["row_types"], ["oa", "bank", "invoice"])

    def test_rejects_wrong_summary_row_or_conflicting_marker(self) -> None:
        wrong_row = _relation()
        wrong_row["row_ids"] = ["oa-1", "bank-1", "etc-summary-other"]
        with self.assertRaisesRegex(RuntimeError, "proven invoice summary row"):
            _run(_CommandService(wrong_row), _args("--dry-run"))

        with self.assertRaisesRegex(RuntimeError, "conflicting ETC batches"):
            _run(_CommandService(_relation(marker="other-batch")), _args("--dry-run"))

    def test_rollback_restores_exact_metadata_preimage(self) -> None:
        command = _CommandService(_relation())
        original_relation = deepcopy(command.relation)
        fingerprint = str(_run(command, _args("--dry-run"))["source_fingerprint"])
        _run(command, _args("--execute", fingerprint))

        preview = _run(command, _args("--rollback-dry-run", fingerprint))
        applied = _run(command, _args("--rollback", fingerprint))

        self.assertEqual(preview["written_relation_count"], 0)
        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(command.relation["special_metadata"], original_relation["special_metadata"])
        self.assertEqual(command.relation["row_ids"], original_relation["row_ids"])
        self.assertEqual(command.relation["row_types"], original_relation["row_types"])

    def test_rollback_removes_summary_member_added_to_metadata_only_relation(self) -> None:
        command = _CommandService(
            _relation(marker="etc_20260720_001", include_summary=False)
        )
        fingerprint = str(_run(command, _args("--dry-run"))["source_fingerprint"])
        _run(command, _args("--execute", fingerprint))

        _run(command, _args("--rollback", fingerprint))

        self.assertEqual(command.relation["row_ids"], ["oa-1", "bank-1"])
        self.assertEqual(command.relation["row_types"], ["oa", "bank"])


if __name__ == "__main__":
    unittest.main()
