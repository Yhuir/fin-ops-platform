from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
from copy import deepcopy
from hashlib import sha256
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)
from fin_ops_platform.tools.runtime_application import (
    bank_flow_rule_batch_tag_rules_payload,
    bank_transaction_tag_read_facade,
    build_tool_runtime_application,
    persist_workbench_pair_relations,
    workbench_relation_command_service,
)


CANONICAL_REQUIREMENT_SOURCE = "bank_transaction_paired_policy"
REPAIR_ACTOR_ID = "system:workbench_requirement_repair"
REPAIR_OPERATION_TYPE = "bank_transaction_paired_policy_requirement_backfill"
ROLLBACK_ACTOR_ID = "system:workbench_requirement_repair_rollback"
ROLLBACK_OPERATION_TYPE = "bank_transaction_paired_policy_requirement_rollback"
_FORWARD_NOTE_PREFIX = "Workbench requirement repair execute fingerprint="
_ROLLBACK_NOTE_PREFIX = "Workbench requirement repair rollback fingerprint="


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair frozen OA/invoice requirement snapshots on historical Workbench relations."
    )
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

    if mode in {"rollback_dry_run", "rollback"}:
        report = _run_rollback(
            app=app,
            command_service=command_service,
            relations=relations,
            histories=histories,
            fingerprint=str(args.expected_fingerprint),
            execute=mode == "rollback",
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0

    targets = [relation for relation in relations if _snapshot_missing(relation)]
    tag_facade = bank_transaction_tag_read_facade(app)
    raw_rules_payload = bank_flow_rule_batch_tag_rules_payload(app)
    rules_payload = raw_rules_payload if isinstance(raw_rules_payload, dict) else {}
    fresh_plan = _build_plan(targets, tag_facade=tag_facade, rules_payload=rules_payload)

    if mode == "execute":
        fingerprint = str(args.expected_fingerprint)
        full_plan, pending_plan = _reconstruct_forward_plan(
            fresh_plan=fresh_plan,
            histories=histories,
            current_relations=relations,
            expected_fingerprint=fingerprint,
        )
        if _fingerprint(full_plan) != fingerprint:
            raise RuntimeError(
                "Workbench relation requirement sources changed after dry-run; rerun dry-run before execute."
            )
    else:
        full_plan = fresh_plan
        pending_plan = fresh_plan
        fingerprint = _fingerprint(full_plan)

    written = 0
    affected_months: set[str] = set()
    if mode == "execute":
        for item in pending_plan:
            result = command_service.update_relation_metadata_for_case_id(
                case_id=item["case_id"],
                special_metadata=item["special_metadata"],
                actor_id=REPAIR_ACTOR_ID,
                note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
                idempotency_key=f"workbench-requirement-backfill-v2:{fingerprint}:{item['case_id']}",
                history_operation_type=REPAIR_OPERATION_TYPE,
            )
            persist_workbench_pair_relations(app, [item["case_id"]])
            written += 1
            affected_months.update(_affected_months(result))

    report = _public_forward_report(
        relations=relations,
        plan=pending_plan,
        rules_payload=rules_payload,
        fingerprint=fingerprint,
        mode=mode,
        written=written,
        affected_months=affected_months,
        original_plan_count=len(full_plan),
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


def _build_plan(
    relations: list[dict[str, Any]],
    *,
    tag_facade: Any,
    rules_payload: dict[str, Any],
) -> list[dict[str, Any]]:
    bank_row_ids = list(
        dict.fromkeys(row_id for relation in relations for row_id in _bank_row_ids(relation))
    )
    scope_keys = list(
        dict.fromkeys(
            scope_key
            for relation in relations
            if (scope_key := str(relation.get("month_scope") or "").strip())
            and scope_key != "all"
        )
    )
    category_records = tag_facade.category_records_by_transaction_ids(
        bank_row_ids,
        require_fresh=True,
        reason="workbench_requirement_backfill",
        scope_keys_hint=scope_keys,
    )
    if not isinstance(category_records, dict):
        raise RuntimeError("Bank transaction tag read returned an invalid result.")

    plan: list[dict[str, Any]] = []
    for relation in sorted(relations, key=lambda item: str(item.get("case_id") or "")):
        raw_tag_codes = [
            _category_code(
                category_records.get(row_id)
                if isinstance(category_records.get(row_id), dict)
                else {}
            )
            for row_id in _bank_row_ids(relation)
        ]
        tag_codes = list(
            dict.fromkeys(
                tag_code
                for tag_code in raw_tag_codes
                if tag_code
            )
        )
        built = build_bank_relation_requirement_metadata(
            tag_codes=raw_tag_codes,
            rules_payload=rules_payload,
        )
        existing = relation.get("special_metadata")
        existing = deepcopy(existing) if isinstance(existing, dict) else {}
        if str(relation.get("relation_mode") or "").strip() != "turnover_manual_closure":
            built["requires_oa"] = _existing_or_built_requirement(
                existing,
                canonical_key="requires_oa",
                legacy_key="paired_requires_oa",
                built=bool(built["requires_oa"]),
            )
            built["requires_invoice"] = _existing_or_built_requirement(
                existing,
                canonical_key="requires_invoice",
                legacy_key="paired_requires_invoice",
                built=bool(built["requires_invoice"]),
            )
        intended_special_metadata = {**existing, **deepcopy(built)}
        plan.append(
            {
                "case_id": str(relation.get("case_id") or "").strip(),
                "before_relation": deepcopy(relation),
                "intended_special_metadata": intended_special_metadata,
                "special_metadata": built,
                "month_scope": str(relation.get("month_scope") or "all"),
                "row_types": [str(value) for value in list(relation.get("row_types") or [])],
                "bank_tag_codes": tag_codes,
            }
        )
    return plan


def _snapshot_missing(relation: dict[str, Any]) -> bool:
    if str(relation.get("status") or "").strip() != "active":
        return False
    row_types = {str(value or "").strip().lower() for value in list(relation.get("row_types") or [])}
    if "bank" not in row_types or _is_exempt_relation(relation):
        return False
    metadata = relation.get("special_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    has_requirements = (
        ("requires_oa" in metadata or "paired_requires_oa" in metadata)
        and ("requires_invoice" in metadata or "paired_requires_invoice" in metadata)
    )
    if str(relation.get("relation_mode") or "").strip() != "turnover_manual_closure":
        return not has_requirements
    return bool(
        not has_requirements
        or str(metadata.get("paired_requirement_source") or "").strip()
        != CANONICAL_REQUIREMENT_SOURCE
        or not isinstance(metadata.get("paired_requirement_tag_codes"), list)
        or not _valid_requirement_version(metadata.get("paired_requirement_version"))
    )


def _is_exempt_relation(relation: dict[str, Any]) -> bool:
    metadata = relation.get("special_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    amount_check = relation.get("amount_check")
    amount_check = amount_check if isinstance(amount_check, dict) else {}
    return bool(
        str(metadata.get("source") or "").strip() == "batch_accounting"
        or isinstance(metadata.get("etc_batch_link"), dict)
        or str(
            amount_check.get("external_etc_batch_id")
            or amount_check.get("etc_batch_id")
            or ""
        ).strip()
    )


def _valid_requirement_version(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _reconstruct_forward_plan(
    *,
    fresh_plan: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    current_relations: list[dict[str, Any]],
    expected_fingerprint: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    history_records = _matched_history_records(
        histories,
        actor_id=REPAIR_ACTOR_ID,
        operation_type=REPAIR_OPERATION_TYPE,
        note=f"{_FORWARD_NOTE_PREFIX}{expected_fingerprint}",
    )
    applied_items: dict[str, dict[str, Any]] = {}
    applied_after: dict[str, dict[str, Any]] = {}
    for history in history_records:
        before, after = _single_history_transition(history)
        case_id = str(before.get("case_id") or "").strip()
        item = _plan_item_from_transition(before, after)
        if case_id in applied_items and applied_items[case_id] != item:
            raise RuntimeError(f"Conflicting execute histories for Workbench relation {case_id}.")
        applied_items[case_id] = item
        applied_after[case_id] = after

    pending_items = {str(item["case_id"]): item for item in fresh_plan}
    if set(applied_items).intersection(pending_items):
        raise RuntimeError("Workbench requirement repair history and current targets overlap.")
    full_plan = sorted(
        [*applied_items.values(), *pending_items.values()],
        key=lambda item: str(item["case_id"]),
    )
    if _fingerprint(full_plan) != expected_fingerprint:
        raise RuntimeError(
            "Workbench relation requirement sources changed after dry-run; rerun dry-run before execute."
        )

    current_by_case = _active_relations_by_case(current_relations)
    for case_id, after in applied_after.items():
        if current_by_case.get(case_id) != after:
            raise RuntimeError(f"Workbench requirement repair drift detected for applied case {case_id}.")
    for case_id, item in pending_items.items():
        if current_by_case.get(case_id) != item["before_relation"]:
            raise RuntimeError(f"Workbench requirement repair drift detected for pending case {case_id}.")
    return full_plan, sorted(pending_items.values(), key=lambda item: str(item["case_id"]))


def _run_rollback(
    *,
    app: Any,
    command_service: Any,
    relations: list[dict[str, Any]],
    histories: list[dict[str, Any]],
    fingerprint: str,
    execute: bool,
) -> dict[str, Any]:
    execute_records = _matched_history_records(
        histories,
        actor_id=REPAIR_ACTOR_ID,
        operation_type=REPAIR_OPERATION_TYPE,
        note=f"{_FORWARD_NOTE_PREFIX}{fingerprint}",
    )
    if not execute_records:
        raise RuntimeError("No matching execute history exists for the supplied repair fingerprint.")
    execute_by_case: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    original_plan: list[dict[str, Any]] = []
    for history in execute_records:
        before, after = _single_history_transition(history)
        case_id = str(before.get("case_id") or "").strip()
        transition = (before, after)
        if case_id in execute_by_case and execute_by_case[case_id] != transition:
            raise RuntimeError(f"Conflicting execute histories for Workbench relation {case_id}.")
        execute_by_case[case_id] = transition
        original_plan.append(_plan_item_from_transition(before, after))
    if _fingerprint(original_plan) != fingerprint:
        raise RuntimeError("Matching execute histories do not reconstruct the supplied repair fingerprint.")

    rollback_records = _matched_history_records(
        histories,
        actor_id=ROLLBACK_ACTOR_ID,
        operation_type=ROLLBACK_OPERATION_TYPE,
        note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
    )
    rollback_by_case: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for history in rollback_records:
        rollback_before, rollback_after = _single_history_transition(history)
        case_id = str(rollback_before.get("case_id") or "").strip()
        transition = (rollback_before, rollback_after)
        if case_id in rollback_by_case and rollback_by_case[case_id] != transition:
            raise RuntimeError(f"Conflicting rollback histories for Workbench relation {case_id}.")
        rollback_by_case[case_id] = transition
    if not set(rollback_by_case).issubset(execute_by_case):
        raise RuntimeError("Rollback history contains a case outside the execute fingerprint.")

    current_by_case = _active_relations_by_case(relations)
    pending: list[tuple[str, dict[str, Any]]] = []
    for case_id in sorted(execute_by_case):
        before, after = execute_by_case[case_id]
        current = current_by_case.get(case_id)
        rollback_transition = rollback_by_case.get(case_id)
        if rollback_transition is None:
            if current != after:
                raise RuntimeError(f"Workbench requirement rollback drift detected for pending case {case_id}.")
            metadata = before.get("special_metadata")
            pending.append((case_id, deepcopy(metadata) if isinstance(metadata, dict) else {}))
            continue
        rollback_before, rollback_after = rollback_transition
        expected_metadata = before.get("special_metadata")
        if rollback_before != after or (
            rollback_after.get("special_metadata")
            != (expected_metadata if isinstance(expected_metadata, dict) else {})
        ):
            raise RuntimeError(f"Workbench requirement rollback history drift detected for case {case_id}.")
        if current != rollback_after:
            raise RuntimeError(f"Workbench requirement rollback drift detected for restored case {case_id}.")

    written = 0
    affected_months: set[str] = set()
    if execute:
        for case_id, preimage in pending:
            result = command_service.update_relation_metadata_for_case_id(
                case_id=case_id,
                special_metadata=preimage,
                replace_special_metadata=True,
                actor_id=ROLLBACK_ACTOR_ID,
                note=f"{_ROLLBACK_NOTE_PREFIX}{fingerprint}",
                idempotency_key=f"workbench-requirement-rollback-v1:{fingerprint}:{case_id}",
                history_operation_type=ROLLBACK_OPERATION_TYPE,
            )
            persist_workbench_pair_relations(app, [case_id])
            written += 1
            affected_months.update(_affected_months(result))

    return {
        "status": "applied" if execute else "dry_run",
        "mode": "rollback" if execute else "rollback_dry_run",
        "active_relation_count": len(relations),
        "execute_history_count": len(execute_by_case),
        "already_restored_relation_count": len(rollback_by_case),
        "target_relation_count": len(pending),
        "written_relation_count": written,
        "source_fingerprint": fingerprint,
        "affected_months": sorted(affected_months),
        "sample_case_ids": [case_id for case_id, _metadata in pending[:10]],
    }


def _matched_history_records(
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
        and str(history.get("created_by") or "").strip() == actor_id
        and str(history.get("operation_type") or "").strip() == operation_type
        and str(history.get("note") or "").strip() == note
    ]


def _single_history_transition(history: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    before_relations = list(history.get("before_relations") or [])
    after_relations = list(history.get("after_relations") or [])
    if len(before_relations) != 1 or len(after_relations) != 1:
        raise RuntimeError("Requirement repair history must contain exactly one before/after relation.")
    before = before_relations[0]
    after = after_relations[0]
    if not isinstance(before, dict) or not isinstance(after, dict):
        raise RuntimeError("Requirement repair history contains an invalid relation image.")
    before_case = str(before.get("case_id") or "").strip()
    after_case = str(after.get("case_id") or "").strip()
    if not before_case or before_case != after_case:
        raise RuntimeError("Requirement repair history relation identity is invalid.")
    return deepcopy(before), deepcopy(after)


def _plan_item_from_transition(
    before: dict[str, Any],
    after: dict[str, Any]
) -> dict[str, Any]:
    after_metadata = after.get("special_metadata")
    after_metadata = deepcopy(after_metadata) if isinstance(after_metadata, dict) else {}
    tag_codes = after_metadata.get("paired_requirement_tag_codes")
    tag_codes = [str(value) for value in tag_codes] if isinstance(tag_codes, list) else []
    return {
        "case_id": str(before.get("case_id") or "").strip(),
        "before_relation": deepcopy(before),
        "intended_special_metadata": after_metadata,
        "special_metadata": after_metadata,
        "month_scope": str(before.get("month_scope") or "all"),
        "row_types": [str(value) for value in list(before.get("row_types") or [])],
        "bank_tag_codes": tag_codes,
    }


def _active_relations_by_case(relations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for relation in relations:
        case_id = str(relation.get("case_id") or "").strip()
        if not case_id or case_id in result:
            raise RuntimeError("Active Workbench relation case identity is missing or duplicated.")
        result[case_id] = deepcopy(relation)
    return result


def _bank_row_ids(relation: dict[str, Any]) -> list[str]:
    row_ids = list(relation.get("row_ids") or [])
    row_types = list(relation.get("row_types") or [])
    return [
        str(row_id or "").strip()
        for index, row_id in enumerate(row_ids)
        if str(row_id or "").strip()
        and str(row_types[index] if index < len(row_types) else "").strip().lower() == "bank"
    ]


def _category_code(record: dict[str, Any]) -> str:
    return str(record.get("effective_category_code") or record.get("category_code") or "").strip()


def _existing_or_built_requirement(
    metadata: dict[str, Any],
    *,
    canonical_key: str,
    legacy_key: str,
    built: bool,
) -> bool:
    if canonical_key in metadata:
        return bool(metadata[canonical_key])
    if legacy_key in metadata:
        return bool(metadata[legacy_key])
    return built


def _fingerprint(plan: list[dict[str, Any]]) -> str:
    payload = [
        {
            "case_id": str(item.get("case_id") or ""),
            "before_relation": item.get("before_relation"),
            "intended_special_metadata": item.get("intended_special_metadata"),
        }
        for item in sorted(plan, key=lambda value: str(value.get("case_id") or ""))
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()


def _affected_months(result: dict[str, Any]) -> set[str]:
    return {
        str(value).strip()
        for value in list(result.get("affected_months") or [])
        if str(value).strip()
    }


def _public_forward_report(
    *,
    relations: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    rules_payload: dict[str, Any],
    fingerprint: str,
    mode: str,
    written: int,
    affected_months: set[str],
    original_plan_count: int,
) -> dict[str, Any]:
    requirement_counts = Counter(
        "oa={oa},invoice={invoice}".format(
            oa=int(bool(item["intended_special_metadata"]["requires_oa"])),
            invoice=int(bool(item["intended_special_metadata"]["requires_invoice"])),
        )
        for item in plan
    )
    row_type_counts = Counter(
        "+".join(
            sorted({str(value).strip().lower() for value in item["row_types"] if str(value).strip()})
        )
        for item in plan
    )
    tag_counts = Counter(tag_code for item in plan for tag_code in item["bank_tag_codes"])
    return {
        "status": "applied" if mode == "execute" else "dry_run",
        "mode": mode,
        "active_relation_count": len(relations),
        "original_plan_relation_count": original_plan_count,
        "target_relation_count": len(plan),
        "written_relation_count": written,
        "rule_version": rules_payload.get("version"),
        "source_fingerprint": fingerprint,
        "fingerprint_contract": "exact_before_relation+intended_special_metadata",
        "requirement_counts": dict(sorted(requirement_counts.items())),
        "row_type_counts": dict(sorted(row_type_counts.items())),
        "top_tag_codes": tag_counts.most_common(20),
        "affected_months": sorted(affected_months),
        "sample_case_ids": [item["case_id"] for item in plan[:10]],
    }


if __name__ == "__main__":
    raise SystemExit(main())
