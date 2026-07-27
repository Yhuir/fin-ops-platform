from __future__ import annotations

from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import batch_accounting_metadata_cleanup_ops as cleanup_ops


def _relation(
    case_id: str,
    *,
    metadata: dict[str, object] | None = None,
    mode: str = "batch_accounting",
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "status": "active",
        "relation_mode": mode,
        "month_scope": "2026-06",
        "row_ids": [f"bank-{case_id}", f"oa-{case_id}"],
        "row_types": ["bank", "oa"],
        "special_metadata": deepcopy(metadata or {}),
        "updated_at": "2026-07-27T10:00:00+08:00",
    }


class _CommandService:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self.relations = deepcopy(relations)
        self.histories: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []

    def list_active_relations(self) -> list[dict[str, object]]:
        return deepcopy(self.relations)

    def list_history(self) -> list[dict[str, object]]:
        return deepcopy(self.histories)

    def update_relation_metadata_for_case_id(self, **kwargs: object) -> dict[str, object]:
        self.updates.append(deepcopy(kwargs))
        case_id = str(kwargs["case_id"])
        for relation in self.relations:
            if relation["case_id"] != case_id:
                continue
            before = deepcopy(relation)
            relation["special_metadata"] = deepcopy(kwargs["special_metadata"])
            relation["updated_at"] = f"2026-07-27T10:{len(self.histories) + 1:02d}:00+08:00"
            after = deepcopy(relation)
            self.histories.append(
                {
                    "operation_type": kwargs["history_operation_type"],
                    "created_by": kwargs["actor_id"],
                    "note": kwargs["note"],
                    "before_relations": [before],
                    "after_relations": [after],
                }
            )
            return {"affected_months": ["2026-06"]}
        raise AssertionError(f"missing relation {case_id}")


def _run(command: _CommandService, argv: list[str]) -> dict[str, object]:
    output = io.StringIO()
    with (
        patch.object(cleanup_ops, "build_tool_runtime_application", return_value=object()),
        patch.object(cleanup_ops, "workbench_relation_command_service", return_value=command),
        patch.object(cleanup_ops, "persist_workbench_pair_relations"),
    ):
        cleanup_ops.main(argv, stdout=output)
    return json.loads(output.getvalue())


class BatchAccountingMetadataCleanupOpsTests(unittest.TestCase):
    def test_plan_targets_only_active_batch_relations_with_retired_keys(self) -> None:
        targets = cleanup_ops._build_plan(
            [
                _relation(
                    "target",
                    metadata={
                        "source": "batch_accounting",
                        "bank_row_id": "bank-target",
                        "oa_row_ids": ["oa-target"],
                        "invoice_row_ids": [],
                        "year": "2026",
                        "bank_year": "2026",
                    },
                ),
                _relation("clean", metadata={"source": "batch_accounting", "bank_year": "2026"}),
                _relation("other", metadata={"bank_row_id": "bank-other"}, mode="manual_confirmed"),
            ]
        )

        self.assertEqual([item["case_id"] for item in targets], ["target"])
        self.assertEqual(
            targets[0]["intended_special_metadata"],
            {"source": "batch_accounting", "bank_year": "2026"},
        )

    def test_execute_is_fingerprint_guarded_and_idempotent(self) -> None:
        command = _CommandService(
            [_relation("target", metadata={"source": "batch_accounting", "bank_row_id": "bank-target"})]
        )
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])

        applied = _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        replay = _run(command, ["--execute", "--expected-fingerprint", fingerprint])

        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(replay["written_relation_count"], 0)
        self.assertEqual(command.relations[0]["special_metadata"], {"source": "batch_accounting"})
        self.assertEqual(len(command.updates), 1)

    def test_execute_rejects_preimage_drift_before_write(self) -> None:
        command = _CommandService(
            [_relation("target", metadata={"source": "batch_accounting", "bank_row_id": "bank-target"})]
        )
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        command.relations[0]["special_metadata"]["bank_row_id"] = "bank-drift"

        with self.assertRaisesRegex(RuntimeError, "changed after dry-run"):
            _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        self.assertEqual(command.updates, [])

    def test_rollback_restores_exact_metadata_preimage(self) -> None:
        original = {
            "source": "batch_accounting",
            "bank_year": "2026",
            "bank_row_id": "bank-target",
            "oa_row_ids": ["oa-target"],
        }
        command = _CommandService([_relation("target", metadata=original)])
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        _run(command, ["--execute", "--expected-fingerprint", fingerprint])

        preview = _run(command, ["--rollback-dry-run", "--expected-fingerprint", fingerprint])
        applied = _run(command, ["--rollback", "--expected-fingerprint", fingerprint])

        self.assertEqual(preview["target_relation_count"], 1)
        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(command.relations[0]["special_metadata"], original)


if __name__ == "__main__":
    unittest.main()
