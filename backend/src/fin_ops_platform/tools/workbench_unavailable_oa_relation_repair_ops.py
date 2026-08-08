from __future__ import annotations

import argparse
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    persist_workbench_pair_relations,
    workbench_relation_command_service,
)


REPAIR_ACTOR_ID = "system:workbench_unavailable_oa_relation_repair"
REPAIR_REASON_PREFIX = "Remove unavailable canonical OA relation member fingerprint="


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove unavailable canonical OA members from one active Workbench relation."
    )
    parser.add_argument("--case-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    if args.dry_run and args.expected_fingerprint:
        raise SystemExit("--dry-run does not accept --expected-fingerprint")
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint")

    app = build_tool_runtime_application(None)
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        report = repair_unavailable_oa_relation(
            app=app,
            connection=connection,
            case_id=str(args.case_id).strip(),
            execute=bool(args.execute),
            expected_fingerprint=(
                str(args.expected_fingerprint).strip()
                if args.expected_fingerprint
                else None
            ),
        )
    finally:
        connection.close()
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def repair_unavailable_oa_relation(
    *,
    app: Any,
    connection: Any,
    case_id: str,
    execute: bool,
    expected_fingerprint: str | None,
) -> dict[str, Any]:
    if not case_id:
        raise RuntimeError("case_id must be non-empty")
    command_service = workbench_relation_command_service(app)
    relation = _active_relation(command_service.list_active_relations(), case_id)
    plan = _build_plan(connection, relation)
    fingerprint = _fingerprint(plan)
    if expected_fingerprint is not None and fingerprint != expected_fingerprint:
        raise RuntimeError(
            "Workbench relation changed after dry-run; rerun dry-run before execute."
        )

    changed_case_ids: list[str] = []
    affected_months: list[str] = []
    if execute:
        result = command_service.remove_rows_from_active_relations(
            row_ids=list(plan["missing_oa_row_ids"]),
            actor_id=REPAIR_ACTOR_ID,
            reason=f"{REPAIR_REASON_PREFIX}{fingerprint}",
        )
        changed_case_ids = sorted(
            str(value).strip()
            for value in list(result.get("changed_case_ids") or [])
            if str(value).strip()
        )
        if changed_case_ids != [case_id]:
            raise RuntimeError(
                f"Expected repair to change only {case_id}; changed {changed_case_ids}."
            )
        persist_workbench_pair_relations(app, changed_case_ids)
        affected_months = sorted(
            str(value).strip()
            for value in list(result.get("affected_months") or [])
            if str(value).strip()
        )

    return {
        "mode": "execute" if execute else "dry_run",
        "status": "repaired" if execute else "ready",
        "case_id": case_id,
        "fingerprint": fingerprint,
        "missing_oa_row_ids": list(plan["missing_oa_row_ids"]),
        "surviving_members": list(plan["surviving_members"]),
        "result_action": plan["result_action"],
        "changed_case_ids": changed_case_ids,
        "affected_months": affected_months,
    }


def discover_unavailable_oa_relation_repairs(
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    connection = PostgresConnection(PostgresSettings.from_env())
    try:
        return _build_repair_summaries(connection, relations)
    finally:
        connection.close()


def _build_repair_summaries(
    connection: Any,
    relations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    oa_row_ids = list(
        dict.fromkeys(
            row_id
            for relation in relations
            for row_id, row_type in _aligned_members(relation)
            if row_type == "oa"
        )
    )
    existing_oa_row_ids = _existing_oa_row_ids(connection, oa_row_ids)
    summaries: list[dict[str, Any]] = []
    for relation in relations:
        plan = _build_plan_from_existing(relation, existing_oa_row_ids)
        if plan is None:
            continue
        summaries.append(
            {
                "case_id": plan["case_id"],
                "fingerprint": _fingerprint(plan),
                "missing_oa_row_ids": list(plan["missing_oa_row_ids"]),
                "surviving_members": list(plan["surviving_members"]),
                "result_action": plan["result_action"],
            }
        )
    return sorted(summaries, key=lambda item: str(item["case_id"]))


def _active_relation(relations: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    matches = [
        deepcopy(relation)
        for relation in relations
        if str(relation.get("case_id") or "").strip() == case_id
        and str(relation.get("status") or "").strip() == "active"
    ]
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one active Workbench relation for {case_id}; found {len(matches)}."
        )
    return matches[0]


def _build_plan(connection: Any, relation: dict[str, Any]) -> dict[str, Any]:
    oa_row_ids = [
        row_id
        for row_id, row_type in _aligned_members(relation)
        if row_type == "oa"
    ]
    plan = _build_plan_from_existing(
        relation,
        _existing_oa_row_ids(connection, oa_row_ids),
    )
    if plan is None:
        raise RuntimeError("All OA relation members still exist in canonical facts.")
    return plan


def _aligned_members(relation: dict[str, Any]) -> list[tuple[str, str]]:
    row_ids = [str(value or "").strip() for value in list(relation.get("row_ids") or [])]
    row_types = [
        str(value or "").strip().lower()
        for value in list(relation.get("row_types") or [])
    ]
    if len(row_ids) != len(row_types) or not row_ids or any(not value for value in row_ids):
        raise RuntimeError("Workbench relation row_ids/row_types are not aligned.")
    return list(zip(row_ids, row_types, strict=True))


def _existing_oa_row_ids(connection: Any, oa_row_ids: list[str]) -> set[str]:
    if not oa_row_ids:
        return set()
    existing_rows = connection.fetch_all(
        """
        select row_id
        from app.oa_applications
        where row_id = any(%s::text[]) and status <> 'deleted'
        order by row_id
        """,
        (oa_row_ids,),
    )
    return {
        str(row.get("row_id") or "").strip()
        for row in existing_rows
        if str(row.get("row_id") or "").strip()
    }


def _build_plan_from_existing(
    relation: dict[str, Any],
    existing_oa_row_ids: set[str],
) -> dict[str, Any] | None:
    members = _aligned_members(relation)
    oa_row_ids = [
        row_id
        for row_id, row_type in members
        if row_type == "oa"
    ]
    if not oa_row_ids:
        return None
    missing_oa_row_ids = sorted(set(oa_row_ids) - existing_oa_row_ids)
    if not missing_oa_row_ids:
        return None
    surviving_members = [
        {"row_id": row_id, "row_type": row_type}
        for row_id, row_type in members
        if row_id not in missing_oa_row_ids
    ]
    metadata = relation.get("special_metadata")
    binding_parents = {
        str(binding.get("parent_oa_row_id") or "").strip()
        for binding in list((metadata or {}).get("oa_attachment_bindings") or [])
        if isinstance(binding, dict)
    }
    result_action = (
        "replace_relation"
        if len(surviving_members) >= 2
        and not binding_parents.intersection(missing_oa_row_ids)
        else "cancel_relation"
    )
    return {
        "case_id": str(relation.get("case_id") or "").strip(),
        "relation_version": relation.get("version"),
        "month_scope": str(relation.get("month_scope") or "all"),
        "relation_mode": str(relation.get("relation_mode") or ""),
        "row_ids": [row_id for row_id, _row_type in members],
        "row_types": [row_type for _row_id, row_type in members],
        "missing_oa_row_ids": missing_oa_row_ids,
        "surviving_members": surviving_members,
        "result_action": result_action,
        "oa_attachment_binding_parents": sorted(binding_parents),
    }


def _fingerprint(plan: dict[str, Any]) -> str:
    return sha256(
        json.dumps(plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
