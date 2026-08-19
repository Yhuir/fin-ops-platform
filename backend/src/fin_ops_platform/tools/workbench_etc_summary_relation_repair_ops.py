from __future__ import annotations

import argparse
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.workbench_etc_batch_link import (
    relation_external_etc_batch_ids,
    workbench_etc_summary_row_id,
)
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    persist_workbench_pair_relations,
    workbench_relation_command_service,
)


REPAIR_ACTOR_ID = "system:workbench_etc_summary_relation_repair"
REPAIR_OPERATION_TYPE = "workbench_etc_summary_relation_repair"
ROLLBACK_ACTOR_ID = "system:workbench_etc_summary_relation_repair_rollback"
ROLLBACK_OPERATION_TYPE = "workbench_etc_summary_relation_repair_rollback"
_FORWARD_NOTE_PREFIX = "Workbench ETC summary relation repair fingerprint="
_ROLLBACK_NOTE_PREFIX = "Workbench ETC summary relation repair rollback fingerprint="
_INVOICE_ROW_TYPES = frozenset({"invoice", "formal_invoice", "input_invoice", "output_invoice"})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Attach one proven ETC summary relation to its durable external batch identity."
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--external-etc-batch-id", required=True)
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

    case_id = str(args.case_id).strip()
    external_batch_id = str(args.external_etc_batch_id).strip()
    if not case_id or not external_batch_id:
        raise SystemExit("--case-id and --external-etc-batch-id must be non-empty")

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
            case_id=case_id,
            external_batch_id=external_batch_id,
            fingerprint=fingerprint,
            execute=mode == "rollback",
        )
    else:
        report = _forward(
            app=app,
            command_service=command_service,
            relations=relations,
            case_id=case_id,
            external_batch_id=external_batch_id,
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
    case_id: str,
    external_batch_id: str,
    expected_fingerprint: str | None,
    execute: bool,
) -> dict[str, Any]:
    relation = _active_relation(relations, case_id)
    identity = _validated_identity(relation, external_batch_id)
    fingerprint = _fingerprint(identity)
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise RuntimeError(
            "Workbench ETC summary relation changed after dry-run; rerun dry-run before execute."
        )

    existing_batch_ids = relation_external_etc_batch_ids(relation)
    if existing_batch_ids and existing_batch_ids != frozenset({external_batch_id}):
        raise RuntimeError(
            f"Workbench relation {case_id} already points to conflicting ETC batches: "
            f"{sorted(existing_batch_ids)}."
        )
    expected_summary_row_id = str(identity["expected_summary_row_id"])
    current_metadata = (
        deepcopy(relation.get("special_metadata"))
        if isinstance(relation.get("special_metadata"), dict)
        else {}
    )
    already_applied = (
        bool(identity["summary_is_member"])
        and existing_batch_ids == frozenset({external_batch_id})
        and str(current_metadata.get("external_etc_batch_id") or "").strip()
        == external_batch_id
    )
    affected_months: set[str] = set()
    written = 0
    if execute and not already_applied:
        target = deepcopy(relation)
        if not identity["summary_is_member"]:
            target["row_ids"] = [*list(target.get("row_ids") or []), expected_summary_row_id]
            target["row_types"] = [*list(target.get("row_types") or []), "invoice"]
        target["special_metadata"] = {
            **current_metadata,
            "external_etc_batch_id": external_batch_id,
        }
        result = _replace_relation(
            command_service=command_service,
            target=target,
            before=relation,
            actor_id=REPAIR_ACTOR_ID,
            history_note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
            idempotency_key=f"workbench-etc-summary-repair-v1:{fingerprint}:{case_id}",
            operation_type=REPAIR_OPERATION_TYPE,
        )
        persist_workbench_pair_relations(app, [case_id])
        affected_months.update(_affected_months(result))
        written = 1

    return _report(
        mode="execute" if execute else "dry_run",
        identity=identity,
        fingerprint=fingerprint,
        written=written,
        already_applied=already_applied,
        affected_months=affected_months,
    )


def _rollback(
    *,
    app: Any,
    command_service: Any,
    relations: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    case_id: str,
    external_batch_id: str,
    fingerprint: str,
    execute: bool,
) -> dict[str, Any]:
    forward_history = _unique_history(
        histories,
        actor_id=REPAIR_ACTOR_ID,
        operation_type=REPAIR_OPERATION_TYPE,
        note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
        case_id=case_id,
    )
    before, after = _transition(forward_history)
    identity = _validated_identity(before, external_batch_id)
    if _fingerprint(identity) != fingerprint:
        raise RuntimeError("Workbench ETC summary repair history does not match the fingerprint.")

    rollback_history = _optional_unique_history(
        histories,
        actor_id=ROLLBACK_ACTOR_ID,
        operation_type=ROLLBACK_OPERATION_TYPE,
        note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
        case_id=case_id,
    )
    current = _active_relation(relations, case_id)
    if rollback_history is not None:
        _rollback_before, rollback_after = _transition(rollback_history)
        if current != rollback_after:
            raise RuntimeError("Workbench ETC summary rollback drift detected after prior rollback.")
        already_applied = True
    else:
        if current != after:
            raise RuntimeError("Workbench ETC summary relation changed after repair; refusing rollback.")
        already_applied = False

    affected_months: set[str] = set()
    written = 0
    if execute and not already_applied:
        result = _replace_relation(
            command_service=command_service,
            target=before,
            before=current,
            actor_id=ROLLBACK_ACTOR_ID,
            history_note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
            idempotency_key=f"workbench-etc-summary-repair-rollback-v1:{fingerprint}:{case_id}",
            operation_type=ROLLBACK_OPERATION_TYPE,
        )
        persist_workbench_pair_relations(app, [case_id])
        affected_months.update(_affected_months(result))
        written = 1

    return _report(
        mode="rollback" if execute else "rollback_dry_run",
        identity=identity,
        fingerprint=fingerprint,
        written=written,
        already_applied=already_applied,
        affected_months=affected_months,
    )


def _active_relation(relations: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    matches = [
        deepcopy(relation)
        for relation in relations
        if str(relation.get("case_id") or "").strip() == case_id
        and str(relation.get("status") or "").strip() == "active"
    ]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one active Workbench relation for {case_id}; found {len(matches)}.")
    return matches[0]


def _validated_identity(relation: dict[str, Any], external_batch_id: str) -> dict[str, Any]:
    row_ids = [str(value or "").strip() for value in list(relation.get("row_ids") or [])]
    row_types = [str(value or "").strip().lower() for value in list(relation.get("row_types") or [])]
    if len(row_ids) != len(row_types):
        raise RuntimeError("Workbench relation row_ids/row_types are not aligned.")
    expected_summary_row_id = workbench_etc_summary_row_id(external_batch_id)
    if len(row_ids) != len(set(row_ids)):
        raise RuntimeError("Workbench relation contains duplicate member ids.")
    summary_indexes = [index for index, row_id in enumerate(row_ids) if row_id == expected_summary_row_id]
    if len(summary_indexes) > 1 or (
        summary_indexes and row_types[summary_indexes[0]] not in _INVOICE_ROW_TYPES
    ):
        raise RuntimeError(
            f"Workbench relation does not contain the proven invoice summary row "
            f"{expected_summary_row_id} exactly once."
        )
    marker_ids = relation_external_etc_batch_ids(relation)
    if marker_ids and marker_ids != frozenset({external_batch_id}):
        raise RuntimeError(
            f"Workbench relation points to conflicting ETC batches: {sorted(marker_ids)}."
        )
    summary_is_member = len(summary_indexes) == 1
    if not summary_is_member and not marker_ids:
        raise RuntimeError(
            f"Workbench relation contains neither the proven invoice summary row "
            f"{expected_summary_row_id} nor the exact ETC batch marker."
        )
    oa_row_ids = [
        row_id
        for row_id, row_type in zip(row_ids, row_types, strict=True)
        if row_type in {"oa", "oa_application"}
    ]
    if len(oa_row_ids) != 1:
        raise RuntimeError(
            "Workbench ETC summary repair requires exactly one OA member in the target relation."
        )
    return {
        "case_id": str(relation.get("case_id") or "").strip(),
        "external_etc_batch_id": external_batch_id,
        "expected_summary_row_id": expected_summary_row_id,
        "month_scope": str(relation.get("month_scope") or "all"),
        "relation_mode": str(relation.get("relation_mode") or ""),
        "row_ids": row_ids,
        "row_types": row_types,
        "desired_row_ids": [*row_ids, *([] if summary_is_member else [expected_summary_row_id])],
        "desired_row_types": [*row_types, *([] if summary_is_member else ["invoice"])],
        "oa_row_id": oa_row_ids[0],
        "summary_is_member": summary_is_member,
        "relation_batch_markers": sorted(marker_ids),
    }


def _replace_relation(
    *,
    command_service: Any,
    target: dict[str, Any],
    before: dict[str, Any],
    actor_id: str,
    history_note: str,
    idempotency_key: str,
    operation_type: str,
) -> dict[str, Any]:
    return command_service.confirm_relation(
        case_id=str(target.get("case_id") or ""),
        row_ids=[str(value) for value in list(target.get("row_ids") or [])],
        row_types=[str(value) for value in list(target.get("row_types") or [])],
        relation_mode=str(target.get("relation_mode") or "manual_confirmed"),
        actor_id=actor_id,
        month_scope=str(target.get("month_scope") or "all"),
        note=str(target.get("note") or "") or None,
        amount_check=deepcopy(target.get("amount_check") or {}),
        special_metadata=deepcopy(target.get("special_metadata") or {}),
        evidence=deepcopy(target.get("evidence") or {}),
        oa_exemption=deepcopy(target.get("oa_exemption") or {}),
        display_tags=[str(value) for value in list(target.get("display_tags") or [])],
        exception_case_id=str(target.get("exception_case_id") or "") or None,
        rule_version=str(target.get("rule_version") or "") or None,
        relation_created_by=str(target.get("created_by") or actor_id),
        history_note=history_note,
        idempotency_key=idempotency_key,
        before_relations=[deepcopy(before)],
        replace_existing=True,
        history_operation_type=operation_type,
    )


def _fingerprint(identity: dict[str, Any]) -> str:
    stable_identity = {
        key: identity[key]
        for key in (
            "case_id",
            "external_etc_batch_id",
            "expected_summary_row_id",
            "month_scope",
            "relation_mode",
            "desired_row_ids",
            "desired_row_types",
            "oa_row_id",
        )
    }
    return sha256(
        json.dumps(stable_identity, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _unique_history(
    histories: list[dict[str, Any]],
    *,
    actor_id: str,
    operation_type: str,
    note: str,
    case_id: str,
) -> dict[str, Any]:
    history = _optional_unique_history(
        histories,
        actor_id=actor_id,
        operation_type=operation_type,
        note=note,
        case_id=case_id,
    )
    if history is None:
        raise RuntimeError("Workbench ETC summary repair history was not found.")
    return history


def _optional_unique_history(
    histories: list[dict[str, Any]],
    *,
    actor_id: str,
    operation_type: str,
    note: str,
    case_id: str,
) -> dict[str, Any] | None:
    matches = [
        deepcopy(history)
        for history in histories
        if str(history.get("created_by") or "") == actor_id
        and str(history.get("operation_type") or "") == operation_type
        and str(history.get("note") or "") == note
        and any(
            str(relation.get("case_id") or "") == case_id
            for relation in [
                *list(history.get("before_relations") or []),
                *list(history.get("after_relations") or []),
            ]
            if isinstance(relation, dict)
        )
    ]
    if len(matches) > 1:
        raise RuntimeError("Conflicting Workbench ETC summary repair histories were found.")
    return matches[0] if matches else None


def _transition(history: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before_relations = list(history.get("before_relations") or [])
    after_relations = list(history.get("after_relations") or [])
    if (
        len(before_relations) != 1
        or len(after_relations) != 1
        or not isinstance(before_relations[0], dict)
        or not isinstance(after_relations[0], dict)
    ):
        raise RuntimeError("Workbench ETC summary repair history transition is invalid.")
    return deepcopy(before_relations[0]), deepcopy(after_relations[0])


def _affected_months(result: dict[str, Any]) -> set[str]:
    return {str(value) for value in list(result.get("affected_months") or []) if str(value)}


def _report(
    *,
    mode: str,
    identity: dict[str, Any],
    fingerprint: str,
    written: int,
    already_applied: bool,
    affected_months: set[str],
) -> dict[str, Any]:
    return {
        "status": "applied" if mode in {"execute", "rollback"} else "dry_run",
        "mode": mode,
        "case_id": identity["case_id"],
        "external_etc_batch_id": identity["external_etc_batch_id"],
        "expected_summary_row_id": identity["expected_summary_row_id"],
        "source_fingerprint": fingerprint,
        "fingerprint_contract": (
            "case+batch+month+mode+desired_ordered_row_ids+desired_ordered_row_types+oa_member"
        ),
        "written_relation_count": written,
        "already_applied": already_applied,
        "affected_months": sorted(affected_months),
    }


if __name__ == "__main__":
    raise SystemExit(main())
