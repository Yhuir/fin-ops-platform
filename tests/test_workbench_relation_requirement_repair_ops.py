from __future__ import annotations

from copy import deepcopy
import io
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import workbench_relation_requirement_repair_ops as repair_ops


class _CommandService:
    def __init__(self, relations: list[dict[str, object]], *, fail_after: int | None = None) -> None:
        self.relations = deepcopy(relations)
        self.history: list[dict[str, object]] = []
        self.updates: list[dict[str, object]] = []
        self.fail_after = fail_after

    def list_active_relations(self) -> list[dict[str, object]]:
        return [deepcopy(item) for item in self.relations if item.get("status") == "active"]

    def list_history(self) -> list[dict[str, object]]:
        return deepcopy(self.history)

    def update_relation_metadata_for_case_id(self, **kwargs: object) -> dict[str, object]:
        if self.fail_after is not None and len(self.updates) >= self.fail_after:
            raise RuntimeError("injected repair interruption")
        self.updates.append(deepcopy(dict(kwargs)))
        case_id = str(kwargs.get("case_id") or "")
        metadata = kwargs.get("special_metadata")
        replace = bool(kwargs.get("replace_special_metadata"))
        for relation in self.relations:
            if relation.get("case_id") != case_id or not isinstance(metadata, dict):
                continue
            before = deepcopy(relation)
            existing = relation.get("special_metadata")
            relation["special_metadata"] = (
                deepcopy(metadata)
                if replace
                else {
                    **(deepcopy(existing) if isinstance(existing, dict) else {}),
                    **deepcopy(metadata),
                }
            )
            relation["updated_at"] = f"2026-07-22T18:{len(self.history):02d}:00+08:00"
            after = deepcopy(relation)
            self.history.append(
                {
                    "operation_id": f"history-{len(self.history) + 1}",
                    "operation_type": str(kwargs.get("history_operation_type") or ""),
                    "before_relations": [before],
                    "after_relations": [after],
                    "affected_row_ids": list(relation.get("row_ids") or []),
                    "created_by": str(kwargs.get("actor_id") or ""),
                    "note": str(kwargs.get("note") or ""),
                }
            )
            return {"affected_months": ["2026-06"], "history": deepcopy(self.history[-1])}
        raise AssertionError(f"missing relation {case_id}")


class _CategoryProvider:
    def __init__(self, category_code: str = "expense:engineering_service:personnel_insurance") -> None:
        self.category_code = category_code
        self.calls: list[list[str]] = []

    def bulk_get_for_rows(self, rows: list[dict[str, object]]) -> dict[str, object]:
        row_ids = [str(row.get("id") or "") for row in rows]
        self.calls.append(list(row_ids))
        return {
            row_id: {"effective_category_code": self.category_code}
            for row_id in row_ids
            if self.category_code
        }


class _InvalidCategoryProvider:
    def bulk_get_for_rows(self, _rows: list[dict[str, object]]) -> object:
        return None


class _ImportService:
    def __init__(self, command: _CommandService) -> None:
        self._command = command

    def list_transactions(self, **_kwargs: object) -> list[dict[str, object]]:
        return [
            {"id": row_id}
            for relation in self._command.relations
            for row_id, row_type in zip(
                list(relation.get("row_ids") or []),
                list(relation.get("row_types") or []),
                strict=True,
            )
            if str(row_type).strip().lower() == "bank"
        ]


def _relation(
    case_id: str = "case-1",
    *,
    mode: str = "turnover_manual_closure",
    metadata: dict[str, object] | None = None,
    status: str = "active",
) -> dict[str, object]:
    return {
        "case_id": case_id,
        "status": status,
        "relation_mode": mode,
        "month_scope": "2026-06",
        "row_ids": [f"oa-{case_id}", f"bank-{case_id}"],
        "row_types": ["oa", "bank"],
        "special_metadata": deepcopy(metadata or {}),
        "amount_check": {},
        "created_at": "2026-07-20T10:00:00+08:00",
        "updated_at": "2026-07-21T10:00:00+08:00",
    }


def _rules(*, requires_oa: bool = True, requires_invoice: bool = True) -> dict[str, object]:
    return {
        "version": 7,
        "requirements_by_tag_code": {
            "expense:engineering_service:personnel_insurance": {
                "requires_oa": requires_oa,
                "requires_invoice": requires_invoice,
            }
        },
    }


def _run(
    command: _CommandService,
    argv: list[str],
    *,
    category_provider: object | None = None,
    rules: object | None = None,
    persisted: list[str] | None = None,
) -> dict[str, object]:
    output = io.StringIO()
    persisted = persisted if persisted is not None else []
    with (
        patch.object(repair_ops, "build_tool_runtime_application", return_value=object()),
        patch.object(repair_ops, "workbench_relation_command_service", return_value=command),
        patch.object(
            repair_ops,
            "bank_transaction_effective_category_provider",
            return_value=category_provider or _CategoryProvider(),
        ),
        patch.object(
            repair_ops,
            "import_service",
            return_value=_ImportService(command),
        ),
        patch.object(
            repair_ops,
            "bank_flow_rule_batch_tag_rules_payload",
            return_value=_rules() if rules is None else rules,
        ),
        patch.object(
            repair_ops,
            "persist_workbench_pair_relations",
            side_effect=lambda _app, case_ids: persisted.extend(case_ids),
        ),
    ):
        repair_ops.main(argv, stdout=output)
    return json.loads(output.getvalue())


class WorkbenchRelationRequirementRepairOpsTests(unittest.TestCase):
    def test_turnover_legacy_sources_and_missing_canonical_fields_are_targets(self) -> None:
        canonical = {
            "paired_requirement_source": "bank_transaction_paired_policy",
            "paired_requirement_tag_codes": ["tag-1"],
            "paired_requirement_version": 1,
            "requires_oa": True,
            "requires_invoice": False,
        }
        invalid_metadata = [
            {**canonical, "paired_requirement_source": "turnover_ledger_manual_closure"},
            {**canonical, "paired_requirement_source": "no_oa_bank_batch_tag_selection"},
            {**canonical, "paired_requirement_source": "unexpected_source"},
            {key: value for key, value in canonical.items() if key != "paired_requirement_tag_codes"},
            {key: value for key, value in canonical.items() if key != "paired_requirement_version"},
        ]
        for metadata in invalid_metadata:
            with self.subTest(metadata=metadata):
                self.assertTrue(repair_ops._snapshot_missing(_relation(metadata=metadata)))
        self.assertFalse(repair_ops._snapshot_missing(_relation(metadata=canonical)))

    def test_inactive_ordinary_etc_and_batch_relations_are_exempt(self) -> None:
        inactive = _relation(status="cancelled")
        ordinary_complete = _relation(
            mode="manual_confirmed",
            metadata={"requires_oa": True, "requires_invoice": False},
        )
        etc = _relation()
        etc["amount_check"] = {"external_etc_batch_id": "etc-1"}
        batch = _relation(metadata={"source": "batch_accounting"})

        self.assertFalse(repair_ops._snapshot_missing(inactive))
        self.assertFalse(repair_ops._snapshot_missing(ordinary_complete))
        self.assertFalse(repair_ops._snapshot_missing(etc))
        self.assertFalse(repair_ops._snapshot_missing(batch))

    def test_turnover_overwrites_legacy_requires_but_ordinary_preserves_them(self) -> None:
        legacy = {"requires_oa": False, "requires_invoice": False}
        turnover = _relation("turnover", metadata=legacy)
        ordinary = _relation("ordinary", mode="manual_confirmed", metadata={"paired_requires_invoice": False})

        plan = repair_ops._build_plan(
            [turnover, ordinary],
            category_provider=_CategoryProvider(),
            bank_rows=[{"id": "bank-turnover"}, {"id": "bank-ordinary"}],
            rules_payload=_rules(),
        )
        by_case = {str(item["case_id"]): item for item in plan}

        self.assertEqual(by_case["turnover"]["special_metadata"]["requires_oa"], True)
        self.assertEqual(by_case["turnover"]["special_metadata"]["requires_invoice"], True)
        self.assertEqual(by_case["ordinary"]["special_metadata"]["requires_invoice"], False)
        self.assertEqual(by_case["ordinary"]["special_metadata"]["requires_oa"], True)

    def test_forward_fingerprint_binds_exact_preimage_and_intended_after(self) -> None:
        relation = _relation(metadata={"legacy_key": "before"})
        plan = repair_ops._build_plan(
            [relation],
            category_provider=_CategoryProvider(),
            bank_rows=[{"id": "bank-case-1"}],
            rules_payload=_rules(),
        )
        fingerprint = repair_ops._fingerprint(plan)
        changed_preimage = deepcopy(plan)
        changed_preimage[0]["before_relation"]["special_metadata"]["legacy_key"] = "drift"
        changed_after = deepcopy(plan)
        changed_after[0]["intended_special_metadata"]["requires_invoice"] = False

        self.assertNotEqual(repair_ops._fingerprint(changed_preimage), fingerprint)
        self.assertNotEqual(repair_ops._fingerprint(changed_after), fingerprint)

    def test_execute_writes_fingerprint_bound_history_and_is_idempotent(self) -> None:
        command = _CommandService([_relation(metadata={"legacy_key": "kept"})])
        dry_run = _run(command, ["--dry-run"])
        fingerprint = str(dry_run["source_fingerprint"])
        persisted: list[str] = []

        applied = _run(
            command,
            ["--execute", "--expected-fingerprint", fingerprint],
            persisted=persisted,
        )
        replay = _run(
            command,
            ["--execute", "--expected-fingerprint", fingerprint],
            persisted=persisted,
        )

        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(replay["written_relation_count"], 0)
        self.assertEqual(len(command.updates), 1)
        self.assertEqual(persisted, ["case-1"])
        update = command.updates[0]
        self.assertEqual(update["actor_id"], repair_ops.REPAIR_ACTOR_ID)
        self.assertEqual(update["history_operation_type"], repair_ops.REPAIR_OPERATION_TYPE)
        self.assertIn(fingerprint, str(update["note"]))
        self.assertIn(fingerprint, str(update["idempotency_key"]))

    def test_partial_execute_reconstructs_original_plan_and_continues(self) -> None:
        command = _CommandService([_relation("case-1"), _relation("case-2")], fail_after=1)
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        persisted: list[str] = []
        with self.assertRaisesRegex(RuntimeError, "injected repair interruption"):
            _run(
                command,
                ["--execute", "--expected-fingerprint", fingerprint],
                persisted=persisted,
            )
        command.fail_after = None

        report = _run(
            command,
            ["--execute", "--expected-fingerprint", fingerprint],
            persisted=persisted,
        )

        self.assertEqual(report["written_relation_count"], 1)
        self.assertEqual([item["case_id"] for item in command.updates], ["case-1", "case-2"])
        self.assertEqual(persisted, ["case-1", "case-2"])

    def test_partial_execute_rejects_applied_case_drift_before_new_write(self) -> None:
        command = _CommandService([_relation("case-1"), _relation("case-2")], fail_after=1)
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        with self.assertRaisesRegex(RuntimeError, "injected repair interruption"):
            _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        command.fail_after = None
        command.relations[0]["special_metadata"]["drift"] = True
        before = len(command.updates)

        with self.assertRaisesRegex(RuntimeError, "drift"):
            _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        self.assertEqual(len(command.updates), before)

    def test_stale_fingerprint_and_invalid_tag_provider_fail_before_any_write(self) -> None:
        command = _CommandService([_relation()])
        with self.assertRaisesRegex(RuntimeError, "sources changed"):
            _run(command, ["--execute", "--expected-fingerprint", "stale"])
        with self.assertRaisesRegex(RuntimeError, "invalid result"):
            _run(
                command,
                ["--dry-run"],
                category_provider=_InvalidCategoryProvider(),
            )
        self.assertEqual(command.updates, [])

    def test_missing_tags_and_rules_fail_closed(self) -> None:
        command = _CommandService([_relation(metadata={"requires_oa": False, "requires_invoice": False})])
        report = _run(
            command,
            ["--dry-run"],
            category_provider=_CategoryProvider(""),
            rules={},
        )
        self.assertEqual(report["requirement_counts"], {"oa=1,invoice=1": 1})

    def test_partial_missing_bank_tag_fails_closed_with_one_bulk_read(self) -> None:
        relation = _relation(metadata={"requires_oa": False, "requires_invoice": False})
        relation["row_ids"] = ["bank-known", "bank-missing"]
        relation["row_types"] = ["bank", "bank"]

        class PartialMissingCategoryProvider:
            def __init__(self) -> None:
                self.calls: list[list[str]] = []

            def bulk_get_for_rows(
                self,
                rows: list[dict[str, object]],
            ) -> dict[str, object]:
                row_ids = [str(row.get("id") or "") for row in rows]
                self.calls.append(list(row_ids))
                return {
                    "bank-known": {
                        "effective_category_code": "expense:engineering_service:personnel_insurance"
                    },
                    "bank-missing": {"effective_category_code": ""},
                }

        category_provider = PartialMissingCategoryProvider()
        plan = repair_ops._build_plan(
            [relation],
            category_provider=category_provider,
            bank_rows=[{"id": "bank-known"}, {"id": "bank-missing"}],
            rules_payload=_rules(requires_oa=False, requires_invoice=False),
        )

        self.assertEqual(plan[0]["bank_tag_codes"], ["expense:engineering_service:personnel_insurance"])
        self.assertEqual(
            plan[0]["special_metadata"]["paired_requirement_tag_codes"],
            ["expense:engineering_service:personnel_insurance"],
        )
        self.assertTrue(plan[0]["special_metadata"]["requires_oa"])
        self.assertTrue(plan[0]["special_metadata"]["requires_invoice"])
        self.assertEqual(category_provider.calls, [["bank-known", "bank-missing"]])

    def test_rollback_restores_exact_metadata_without_recreating_relation(self) -> None:
        preimage = {"legacy_key": "keep", "requires_oa": False, "requires_invoice": False}
        command = _CommandService([_relation(metadata=preimage)])
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        relation_after_execute = deepcopy(command.relations[0])

        preview = _run(
            command,
            ["--rollback-dry-run", "--expected-fingerprint", fingerprint],
        )
        applied = _run(command, ["--rollback", "--expected-fingerprint", fingerprint])
        replay = _run(command, ["--rollback", "--expected-fingerprint", fingerprint])
        empty = _run(
            command,
            ["--rollback-dry-run", "--expected-fingerprint", fingerprint],
        )

        self.assertEqual(preview["target_relation_count"], 1)
        self.assertEqual(applied["written_relation_count"], 1)
        self.assertEqual(replay["written_relation_count"], 0)
        self.assertEqual(empty["target_relation_count"], 0)
        self.assertEqual(command.relations[0]["special_metadata"], preimage)
        for field in ("case_id", "status", "relation_mode", "row_ids", "row_types", "created_at"):
            self.assertEqual(command.relations[0][field], relation_after_execute[field])
        rollback_update = command.updates[-1]
        self.assertEqual(rollback_update["replace_special_metadata"], True)
        self.assertEqual(rollback_update["history_operation_type"], repair_ops.ROLLBACK_OPERATION_TYPE)

    def test_partial_rollback_retry_skips_restored_case_and_continues(self) -> None:
        command = _CommandService([_relation("case-1"), _relation("case-2")])
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        command.fail_after = len(command.updates) + 1
        with self.assertRaisesRegex(RuntimeError, "injected repair interruption"):
            _run(command, ["--rollback", "--expected-fingerprint", fingerprint])
        command.fail_after = None

        report = _run(command, ["--rollback", "--expected-fingerprint", fingerprint])

        self.assertEqual(report["written_relation_count"], 1)
        rollback_cases = [
            item["case_id"]
            for item in command.updates
            if item.get("history_operation_type") == repair_ops.ROLLBACK_OPERATION_TYPE
        ]
        self.assertEqual(rollback_cases, ["case-1", "case-2"])

    def test_rollback_drift_fails_before_any_write(self) -> None:
        command = _CommandService([_relation("case-1"), _relation("case-2")])
        fingerprint = str(_run(command, ["--dry-run"])["source_fingerprint"])
        _run(command, ["--execute", "--expected-fingerprint", fingerprint])
        command.relations[1]["special_metadata"]["drift"] = True
        before = len(command.updates)

        with self.assertRaisesRegex(RuntimeError, "drift"):
            _run(command, ["--rollback", "--expected-fingerprint", fingerprint])
        self.assertEqual(len(command.updates), before)

    def test_rollback_requires_matching_execute_history(self) -> None:
        command = _CommandService([_relation()])
        with self.assertRaisesRegex(RuntimeError, "matching execute history"):
            _run(command, ["--rollback-dry-run", "--expected-fingerprint", "unknown"])
        self.assertEqual(command.updates, [])


if __name__ == "__main__":
    unittest.main()
