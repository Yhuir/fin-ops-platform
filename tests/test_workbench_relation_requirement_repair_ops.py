from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import workbench_relation_requirement_repair_ops as repair_ops


class _CommandService:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self.relations = relations
        self.updates: list[dict[str, object]] = []

    def list_active_relations(self) -> list[dict[str, object]]:
        return self.relations

    def update_relation_metadata_for_case_id(self, **kwargs: object) -> dict[str, object]:
        self.updates.append(dict(kwargs))
        return {"affected_months": ["2026-06"]}


class _TagFacade:
    def category_records_by_transaction_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        return {
            row_id: {"effective_category_code": "expense:engineering_service:personnel_insurance"}
            for row_id in row_ids
        }


class _MissingTagFacade:
    def category_records_by_transaction_ids(self, _row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        return {}


def _ordinary_relation() -> dict[str, object]:
    return {
        "case_id": "case-1",
        "status": "active",
        "relation_mode": "manual_confirmed",
        "month_scope": "2026-06",
        "row_ids": ["oa-1", "bank-1"],
        "row_types": ["oa", "bank"],
        "special_metadata": {},
        "amount_check": {},
        "updated_at": "2026-07-21T10:00:00+08:00",
    }


def _rules() -> dict[str, object]:
    return {
        "version": 7,
        "requirements_by_tag_code": {
            "expense:engineering_service:personnel_insurance": {
                "requires_oa": True,
                "requires_invoice": True,
            }
        },
    }


class WorkbenchRelationRequirementRepairOpsTests(unittest.TestCase):
    def test_dry_run_builds_fingerprinted_fail_closed_plan_without_writes(self) -> None:
        command = _CommandService([_ordinary_relation()])
        output = io.StringIO()
        with (
            patch.object(repair_ops, "build_tool_runtime_application", return_value=object()),
            patch.object(repair_ops, "workbench_relation_command_service", return_value=command),
            patch.object(repair_ops, "bank_transaction_tag_read_facade", return_value=_TagFacade()),
            patch.object(repair_ops, "bank_flow_rule_batch_tag_rules_payload", return_value=_rules()),
        ):
            result = repair_ops.main(["--dry-run"], stdout=output)

        report = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(report["target_relation_count"], 1)
        self.assertEqual(report["requirement_counts"], {"oa=1,invoice=1": 1})
        self.assertEqual(len(report["source_fingerprint"]), 64)
        self.assertEqual(command.updates, [])

    def test_execute_requires_matching_dry_run_fingerprint_and_writes_audited_metadata(self) -> None:
        command = _CommandService([_ordinary_relation()])
        tag_facade = _TagFacade()
        plan = repair_ops._build_plan(command.relations, tag_facade=tag_facade, rules_payload=_rules())
        fingerprint = repair_ops._fingerprint(plan)
        output = io.StringIO()
        with (
            patch.object(repair_ops, "build_tool_runtime_application", return_value=object()),
            patch.object(repair_ops, "workbench_relation_command_service", return_value=command),
            patch.object(repair_ops, "bank_transaction_tag_read_facade", return_value=tag_facade),
            patch.object(repair_ops, "bank_flow_rule_batch_tag_rules_payload", return_value=_rules()),
        ):
            repair_ops.main(
                ["--execute", "--expected-fingerprint", fingerprint],
                stdout=output,
            )

        self.assertEqual(len(command.updates), 1)
        update = command.updates[0]
        self.assertEqual(update["actor_id"], repair_ops.REPAIR_ACTOR_ID)
        self.assertEqual(update["history_operation_type"], repair_ops.REPAIR_OPERATION_TYPE)
        self.assertEqual(update["special_metadata"]["requires_invoice"], True)
        self.assertEqual(json.loads(output.getvalue())["written_relation_count"], 1)

    def test_execute_rejects_stale_fingerprint_before_any_relation_write(self) -> None:
        command = _CommandService([_ordinary_relation()])
        with (
            patch.object(repair_ops, "build_tool_runtime_application", return_value=object()),
            patch.object(repair_ops, "workbench_relation_command_service", return_value=command),
            patch.object(repair_ops, "bank_transaction_tag_read_facade", return_value=_TagFacade()),
            patch.object(repair_ops, "bank_flow_rule_batch_tag_rules_payload", return_value=_rules()),
        ):
            with self.assertRaisesRegex(RuntimeError, "sources changed"):
                repair_ops.main(["--execute", "--expected-fingerprint", "stale"])
        self.assertEqual(command.updates, [])

    def test_missing_tag_fails_closed_and_existing_legacy_requirement_is_preserved(self) -> None:
        relation = _ordinary_relation()
        relation["special_metadata"] = {"paired_requires_invoice": False}

        plan = repair_ops._build_plan(
            [relation],
            tag_facade=_MissingTagFacade(),
            rules_payload=_rules(),
        )

        self.assertEqual(plan[0]["bank_tag_codes"], [])
        self.assertEqual(plan[0]["special_metadata"]["requires_oa"], True)
        self.assertEqual(plan[0]["special_metadata"]["requires_invoice"], False)

    def test_exempt_relations_and_complete_snapshots_are_not_targets(self) -> None:
        complete = _ordinary_relation()
        complete["special_metadata"] = {"requires_oa": True, "requires_invoice": True}
        turnover = _ordinary_relation()
        turnover["case_id"] = "case-turnover"
        turnover["relation_mode"] = "turnover_manual_closure"
        etc = _ordinary_relation()
        etc["case_id"] = "case-etc"
        etc["amount_check"] = {"external_etc_batch_id": "etc-1"}

        self.assertFalse(repair_ops._snapshot_missing(complete))
        self.assertFalse(repair_ops._snapshot_missing(turnover))
        self.assertFalse(repair_ops._snapshot_missing(etc))


if __name__ == "__main__":
    unittest.main()
