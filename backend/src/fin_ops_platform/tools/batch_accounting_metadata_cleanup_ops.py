from __future__ import annotations

import argparse
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    persist_workbench_pair_relations,
    workbench_relation_command_service,
)


RETIRED_KEYS = ("bank_row_id", "oa_row_ids", "invoice_row_ids", "year")
REPAIR_ACTOR_ID = "system:batch_accounting_metadata_cleanup"
REPAIR_OPERATION_TYPE = "batch_accounting_metadata_cleanup"
ROLLBACK_ACTOR_ID = "system:batch_accounting_metadata_cleanup_rollback"
ROLLBACK_OPERATION_TYPE = "batch_accounting_metadata_cleanup_rollback"
_FORWARD_NOTE_PREFIX = "Batch accounting metadata cleanup fingerprint="
_ROLLBACK_NOTE_PREFIX = "Batch accounting metadata cleanup rollback fingerprint="


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Remove retired batch-accounting membership metadata.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--rollback-dry-run", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    parser.add_argument("--expected-fingerprint")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    mode = _mode(args)
    if mode == "dry_run" and args.expected_fingerprint:
        raise SystemExit("--dry-run does not accept --expected-fingerprint")
    if mode != "dry_run" and not args.expected_fingerprint:
        raise SystemExit(f"--{mode.replace('_', '-')} requires --expected-fingerprint")

    app = build_tool_runtime_application(None)
    command_service = workbench_relation_command_service(app)
    relations = command_service.list_active_relations()
    histories = command_service.list_history()
    fingerprint = str(args.expected_fingerprint or "")

    if mode in {"rollback_dry_run", "rollback"}:
        report = _rollback(
            app=app,
            command_service=command_service,
            relations=relations,
            histories=histories,
            fingerprint=fingerprint,
            execute=mode == "rollback",
        )
    else:
        report = _forward(
            app=app,
            command_service=command_service,
            relations=relations,
            histories=histories,
            expected_fingerprint=fingerprint or None,
            execute=mode == "execute",
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _mode(args: argparse.Namespace) -> str:
    if args.execute:
        return "execute"
    if args.rollback_dry_run:
        return "rollback_dry_run"
    if args.rollback:
        return "rollback"
    return "dry_run"


def _forward(
    *,
    app: Any,
    command_service: Any,
    relations: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    expected_fingerprint: str | None,
    execute: bool,
) -> dict[str, Any]:
    fresh_plan = _build_plan(relations)
    pending_plan = fresh_plan
    full_plan = fresh_plan
    fingerprint = _fingerprint(full_plan)
    if execute:
        full_plan, pending_plan = _reconstruct_forward_plan(
            fresh_plan=fresh_plan,
            histories=histories,
            current_relations=relations,
            expected_fingerprint=str(expected_fingerprint),
        )
        fingerprint = _fingerprint(full_plan)

    written = 0
    affected_months: set[str] = set()
    if execute:
        for item in pending_plan:
            result = command_service.update_relation_metadata_for_case_id(
                case_id=item["case_id"],
                special_metadata=item["intended_special_metadata"],
                replace_special_metadata=True,
                actor_id=REPAIR_ACTOR_ID,
                note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
                idempotency_key=f"batch-accounting-metadata-cleanup-v1:{fingerprint}:{item['case_id']}",
                history_operation_type=REPAIR_OPERATION_TYPE,
            )
            persist_workbench_pair_relations(app, [item["case_id"]])
            affected_months.update(_affected_months(result))
            written += 1
    return _report(
        mode="execute" if execute else "dry_run",
        relations=relations,
        plan=pending_plan,
        fingerprint=fingerprint,
        original_plan_count=len(full_plan),
        written=written,
        affected_months=affected_months,
    )


def _build_plan(relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for relation in sorted(relations, key=lambda item: str(item.get("case_id") or "")):
        if str(relation.get("status") or "") != "active":
            continue
        if str(relation.get("relation_mode") or "") != "batch_accounting":
            continue
        metadata = relation.get("special_metadata")
        metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
        if not any(key in metadata for key in RETIRED_KEYS):
            continue
        plan.append(
            {
                "case_id": str(relation.get("case_id") or "").strip(),
                "before_relation": deepcopy(relation),
                "intended_special_metadata": {
                    key: value for key, value in metadata.items() if key not in RETIRED_KEYS
                },
            }
        )
    return plan


def _reconstruct_forward_plan(
    *,
    fresh_plan: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    current_relations: list[dict[str, Any]],
    expected_fingerprint: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: dict[str, dict[str, Any]] = {}
    applied_after: dict[str, dict[str, Any]] = {}
    for history in _matched_histories(
        histories,
        actor_id=REPAIR_ACTOR_ID,
        operation_type=REPAIR_OPERATION_TYPE,
        note=f"{_FORWARD_NOTE_PREFIX}{expected_fingerprint}",
    ):
        before, after = _transition(history)
        item = _plan_item(before, after)
        case_id = item["case_id"]
        if case_id in applied and applied[case_id] != item:
            raise RuntimeError(f"Conflicting cleanup histories for batch relation {case_id}.")
        applied[case_id] = item
        applied_after[case_id] = after

    pending = {item["case_id"]: item for item in fresh_plan}
    if set(applied).intersection(pending):
        raise RuntimeError("Batch metadata cleanup history and current targets overlap.")
    full_plan = sorted([*applied.values(), *pending.values()], key=lambda item: item["case_id"])
    if _fingerprint(full_plan) != expected_fingerprint:
        raise RuntimeError("Batch metadata changed after dry-run; rerun dry-run before execute.")

    current_by_case = _relations_by_case(current_relations)
    for case_id, relation in applied_after.items():
        if current_by_case.get(case_id) != relation:
            raise RuntimeError(f"Batch metadata cleanup drift detected for applied case {case_id}.")
    for case_id, item in pending.items():
        if current_by_case.get(case_id) != item["before_relation"]:
            raise RuntimeError(f"Batch metadata cleanup drift detected for pending case {case_id}.")
    return full_plan, sorted(pending.values(), key=lambda item: item["case_id"])


def _rollback(
    *,
    app: Any,
    command_service: Any,
    relations: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    fingerprint: str,
    execute: bool,
) -> dict[str, Any]:
    execute_transitions: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    original_plan: list[dict[str, Any]] = []
    for history in _matched_histories(
        histories,
        actor_id=REPAIR_ACTOR_ID,
        operation_type=REPAIR_OPERATION_TYPE,
        note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
    ):
        before, after = _transition(history)
        case_id = str(before.get("case_id") or "")
        transition = (before, after)
        if case_id in execute_transitions and execute_transitions[case_id] != transition:
            raise RuntimeError(f"Conflicting cleanup histories for batch relation {case_id}.")
        execute_transitions[case_id] = transition
        original_plan.append(_plan_item(before, after))
    if not execute_transitions or _fingerprint(original_plan) != fingerprint:
        raise RuntimeError("Cleanup histories do not reconstruct the supplied fingerprint.")

    rollback_transitions: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for history in _matched_histories(
        histories,
        actor_id=ROLLBACK_ACTOR_ID,
        operation_type=ROLLBACK_OPERATION_TYPE,
        note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
    ):
        before, after = _transition(history)
        case_id = str(before.get("case_id") or "")
        transition = (before, after)
        if case_id in rollback_transitions and rollback_transitions[case_id] != transition:
            raise RuntimeError(f"Conflicting rollback histories for batch relation {case_id}.")
        rollback_transitions[case_id] = transition
    if not set(rollback_transitions).issubset(execute_transitions):
        raise RuntimeError("Rollback history contains a case outside the cleanup fingerprint.")

    current_by_case = _relations_by_case(relations)
    pending: list[tuple[str, dict[str, Any]]] = []
    for case_id in sorted(execute_transitions):
        before, after = execute_transitions[case_id]
        restored_metadata = before.get("special_metadata")
        restored_metadata = deepcopy(restored_metadata) if isinstance(restored_metadata, dict) else {}
        rollback_transition = rollback_transitions.get(case_id)
        if rollback_transition is None:
            if current_by_case.get(case_id) != after:
                raise RuntimeError(f"Batch metadata rollback drift detected for pending case {case_id}.")
            pending.append((case_id, restored_metadata))
            continue
        rollback_before, rollback_after = rollback_transition
        if rollback_before != after or rollback_after.get("special_metadata") != restored_metadata:
            raise RuntimeError(f"Batch metadata rollback history drift detected for case {case_id}.")
        if current_by_case.get(case_id) != rollback_after:
            raise RuntimeError(f"Batch metadata rollback drift detected for restored case {case_id}.")

    written = 0
    affected_months: set[str] = set()
    if execute:
        for case_id, metadata in pending:
            result = command_service.update_relation_metadata_for_case_id(
                case_id=case_id,
                special_metadata=metadata,
                replace_special_metadata=True,
                actor_id=ROLLBACK_ACTOR_ID,
                note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
                idempotency_key=f"batch-accounting-metadata-cleanup-rollback-v1:{fingerprint}:{case_id}",
                history_operation_type=ROLLBACK_OPERATION_TYPE,
            )
            persist_workbench_pair_relations(app, [case_id])
            affected_months.update(_affected_months(result))
            written += 1
    return {
        "status": "applied" if execute else "dry_run",
        "mode": "rollback" if execute else "rollback_dry_run",
        "source_fingerprint": fingerprint,
        "execute_history_count": len(execute_transitions),
        "already_restored_relation_count": len(rollback_transitions),
        "target_relation_count": len(pending),
        "written_relation_count": written,
        "affected_months": sorted(affected_months),
        "sample_case_ids": [case_id for case_id, _metadata in pending[:10]],
    }


def _matched_histories(
    histories: list[dict[str, Any]],
    *,
    actor_id: str,
    operation_type: str,
    note: str,
) -> list[dict[str, Any]]:
    return [
        deepcopy(history)
        for history in histories
        if isinstance(history, dict)
        and str(history.get("created_by") or "") == actor_id
        and str(history.get("operation_type") or "") == operation_type
        and str(history.get("note") or "") == note
    ]


def _transition(history: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before = list(history.get("before_relations") or [])
    after = list(history.get("after_relations") or [])
    if len(before) != 1 or len(after) != 1 or not isinstance(before[0], dict) or not isinstance(after[0], dict):
        raise RuntimeError("Batch metadata cleanup history must contain one before/after relation.")
    if str(before[0].get("case_id") or "") != str(after[0].get("case_id") or ""):
        raise RuntimeError("Batch metadata cleanup history relation identity is invalid.")
    return deepcopy(before[0]), deepcopy(after[0])


def _plan_item(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_metadata = before.get("special_metadata")
    before_metadata = deepcopy(before_metadata) if isinstance(before_metadata, dict) else {}
    metadata = after.get("special_metadata")
    metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
    expected_metadata = {key: value for key, value in before_metadata.items() if key not in RETIRED_KEYS}
    if (
        str(before.get("status") or "") != "active"
        or str(before.get("relation_mode") or "") != "batch_accounting"
        or metadata != expected_metadata
    ):
        raise RuntimeError("Batch metadata cleanup history does not match the cleanup contract.")
    return {
        "case_id": str(before.get("case_id") or ""),
        "before_relation": deepcopy(before),
        "intended_special_metadata": metadata,
    }


def _relations_by_case(relations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relation in relations:
        case_id = str(relation.get("case_id") or "")
        if not case_id or case_id in result:
            raise RuntimeError("Active batch relation case identity is missing or duplicated.")
        result[case_id] = deepcopy(relation)
    return result


def _fingerprint(plan: list[dict[str, Any]]) -> str:
    payload = [
        {
            "case_id": item["case_id"],
            "before_relation": item["before_relation"],
            "intended_special_metadata": item["intended_special_metadata"],
        }
        for item in sorted(plan, key=lambda value: value["case_id"])
    ]
    return sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _affected_months(result: dict[str, Any]) -> set[str]:
    return {str(value) for value in list(result.get("affected_months") or []) if str(value)}


def _report(
    *,
    mode: str,
    relations: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    fingerprint: str,
    original_plan_count: int,
    written: int,
    affected_months: set[str],
) -> dict[str, Any]:
    return {
        "status": "applied" if mode == "execute" else "dry_run",
        "mode": mode,
        "active_relation_count": len(relations),
        "original_plan_relation_count": original_plan_count,
        "target_relation_count": len(plan),
        "written_relation_count": written,
        "source_fingerprint": fingerprint,
        "fingerprint_contract": "exact_before_relation+intended_special_metadata",
        "retired_keys": list(RETIRED_KEYS),
        "affected_months": sorted(affected_months),
        "sample_case_ids": [item["case_id"] for item in plan[:10]],
    }


if __name__ == "__main__":
    raise SystemExit(main())
