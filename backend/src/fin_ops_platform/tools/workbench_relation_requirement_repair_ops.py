from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
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
    workbench_relation_command_service,
)


REPAIR_ACTOR_ID = "system:workbench_requirement_repair"
REPAIR_OPERATION_TYPE = "bank_transaction_paired_policy_requirement_backfill"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Repair frozen OA/invoice requirement snapshots on historical Workbench relations."
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint from a dry run")

    app = build_tool_runtime_application(None)
    command_service = workbench_relation_command_service(app)
    relations = command_service.list_active_relations()
    targets = [relation for relation in relations if _snapshot_missing(relation)]
    tag_facade = bank_transaction_tag_read_facade(app)
    rules_payload = bank_flow_rule_batch_tag_rules_payload(app)
    plan = _build_plan(targets, tag_facade=tag_facade, rules_payload=rules_payload)
    fingerprint = _fingerprint(plan)

    if args.execute and fingerprint != args.expected_fingerprint:
        raise RuntimeError(
            "Workbench relation requirement sources changed after dry-run; rerun dry-run before execute."
        )

    written = 0
    affected_months: set[str] = set()
    if args.execute:
        for item in plan:
            result = command_service.update_relation_metadata_for_case_id(
                case_id=item["case_id"],
                special_metadata=item["special_metadata"],
                actor_id=REPAIR_ACTOR_ID,
                note="Backfill frozen bank tag OA/invoice requirements through the canonical relation command.",
                idempotency_key=f"workbench-requirement-backfill-v1:{item['case_id']}",
                history_operation_type=REPAIR_OPERATION_TYPE,
            )
            written += 1
            affected_months.update(
                str(value).strip()
                for value in list(result.get("affected_months") or [])
                if str(value).strip()
            )

    report = _public_report(
        relations=relations,
        plan=plan,
        rules_payload=rules_payload,
        fingerprint=fingerprint,
        mode="execute" if args.execute else "dry_run",
        written=written,
        affected_months=affected_months,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


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
        tag_codes = list(
            dict.fromkeys(
                tag_code
                for row_id in _bank_row_ids(relation)
                if (
                    tag_code := _category_code(
                        category_records.get(row_id)
                        if isinstance(category_records.get(row_id), dict)
                        else {}
                    )
                )
            )
        )
        built = build_bank_relation_requirement_metadata(
            tag_codes=tag_codes,
            rules_payload=rules_payload,
        )
        existing = relation.get("special_metadata")
        existing = existing if isinstance(existing, dict) else {}
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
        plan.append(
            {
                "case_id": str(relation.get("case_id") or "").strip(),
                "updated_at": str(relation.get("updated_at") or ""),
                "month_scope": str(relation.get("month_scope") or "all"),
                "row_ids": [str(value) for value in list(relation.get("row_ids") or [])],
                "row_types": [str(value) for value in list(relation.get("row_types") or [])],
                "bank_tag_codes": tag_codes,
                "special_metadata": built,
            }
        )
    return plan


def _snapshot_missing(relation: dict[str, Any]) -> bool:
    row_types = {str(value or "").strip().lower() for value in list(relation.get("row_types") or [])}
    if "bank" not in row_types or _is_exempt_relation(relation):
        return False
    metadata = relation.get("special_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    has_oa = "requires_oa" in metadata or "paired_requires_oa" in metadata
    has_invoice = "requires_invoice" in metadata or "paired_requires_invoice" in metadata
    return not (has_oa and has_invoice)


def _is_exempt_relation(relation: dict[str, Any]) -> bool:
    metadata = relation.get("special_metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    amount_check = relation.get("amount_check")
    amount_check = amount_check if isinstance(amount_check, dict) else {}
    return bool(
        str(relation.get("relation_mode") or "").strip() == "turnover_manual_closure"
        or str(metadata.get("source") or "").strip() == "batch_accounting"
        or isinstance(metadata.get("etc_batch_link"), dict)
        or str(
            amount_check.get("external_etc_batch_id")
            or amount_check.get("etc_batch_id")
            or ""
        ).strip()
    )


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
    encoded = json.dumps(
        plan,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return sha256(encoded).hexdigest()


def _public_report(
    *,
    relations: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    rules_payload: dict[str, Any],
    fingerprint: str,
    mode: str,
    written: int,
    affected_months: set[str],
) -> dict[str, Any]:
    requirement_counts = Counter(
        "oa={oa},invoice={invoice}".format(
            oa=int(bool(item["special_metadata"]["requires_oa"])),
            invoice=int(bool(item["special_metadata"]["requires_invoice"])),
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
        "target_relation_count": len(plan),
        "written_relation_count": written,
        "rule_version": rules_payload.get("version"),
        "source_fingerprint": fingerprint,
        "requirement_counts": dict(sorted(requirement_counts.items())),
        "row_type_counts": dict(sorted(row_type_counts.items())),
        "top_tag_codes": tag_counts.most_common(20),
        "affected_months": sorted(affected_months),
        "sample_case_ids": [item["case_id"] for item in plan[:10]],
    }


if __name__ == "__main__":
    raise SystemExit(main())
