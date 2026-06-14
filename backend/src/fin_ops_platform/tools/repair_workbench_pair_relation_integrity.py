from __future__ import annotations

import argparse
from collections.abc import Sequence
from copy import deepcopy
from datetime import UTC, datetime
import json
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


OA_ATTACHMENT_PREFIX = "oa-att-"
OA_AUTO_OFFSET_MODE = "oa_invoice_offset_auto_match"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair active workbench pair relations that reference rows no longer present in SQL read models.")
    parser.add_argument("--execute", action="store_true", help="Persist changes. Without this flag the command is a dry run.")
    parser.add_argument("--actor-id", default="system:workbench-relation-integrity-repair")
    parser.add_argument("--limit", type=int, default=0, help="Maximum number of changed relations to persist; 0 means no limit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    snapshot = PostgresWorkbenchRepository(connection).load_workbench_pair_relations()
    repair = build_repair_plan(
        snapshot,
        current_rows=_load_current_workbench_rows(connection),
        existing_oa_row_ids=_load_existing_oa_row_ids(connection),
        actor_id=str(args.actor_id),
        limit=max(0, int(args.limit or 0)),
    )
    if args.execute and repair["changed_case_ids"]:
        repository = PostgresWorkbenchRepository(connection)
        repository.save_workbench_pair_relations(
            repair["snapshot"],
            changed_case_ids=set(repair["changed_case_ids"]),
        )
    print(json.dumps({key: value for key, value in repair.items() if key != "snapshot"}, ensure_ascii=False, sort_keys=True))
    return 0 if repair["status"] == "ok" else 1


def build_repair_plan(
    snapshot: dict[str, Any],
    *,
    current_rows: list[dict[str, Any]],
    existing_oa_row_ids: set[str],
    actor_id: str,
    limit: int = 0,
) -> dict[str, Any]:
    pair_relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
    if not isinstance(pair_relations, dict):
        return {"status": "ok", "changed_case_ids": [], "cancelled_case_ids": [], "repaired_case_ids": [], "snapshot": snapshot}

    rows_by_id = {
        str(row.get("row_id") or "").strip(): row
        for row in current_rows
        if str(row.get("row_id") or "").strip()
    }
    attachment_rows_by_parent: dict[str, list[str]] = {}
    for row_id, row in rows_by_id.items():
        source_kind = str(row.get("source_kind") or "").strip()
        parent = str(row.get("derived_from_oa_id") or "").strip()
        if parent and source_kind == "oa_attachment_invoice":
            attachment_rows_by_parent.setdefault(parent, []).append(row_id)

    repaired_snapshot = deepcopy(snapshot)
    repaired_relations = repaired_snapshot.setdefault("pair_relations", {})
    history = repaired_snapshot.setdefault("pair_relation_history", [])
    changed_case_ids: list[str] = []
    repaired_case_ids: list[str] = []
    cancelled_case_ids: list[str] = []
    timestamp = datetime.now(UTC).isoformat()

    for case_id, relation in list(repaired_relations.items()):
        if limit and len(changed_case_ids) >= limit:
            break
        if not isinstance(relation, dict) or str(relation.get("status") or "") != "active":
            continue
        before = deepcopy(relation)
        row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
        row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
        entries = [
            (row_id, row_types[index] if index < len(row_types) else _row_type_for_id(row_id))
            for index, row_id in enumerate(row_ids)
        ]
        parent_oa_ids = [
            row_id
            for row_id, row_type in entries
            if row_id in rows_by_id
            and (row_type == "oa" or (row_id.startswith("oa-") and not row_id.startswith(OA_ATTACHMENT_PREFIX)))
        ]
        expected_entries = [(row_id, row_type) for row_id, row_type in entries if row_id in rows_by_id]
        for parent_oa_id in parent_oa_ids:
            for attachment_row_id in sorted(attachment_rows_by_parent.get(parent_oa_id, [])):
                expected_entries.append((attachment_row_id, "invoice"))
        expected_entries = _dedupe_entries(expected_entries)
        missing_entries = [(row_id, row_type) for row_id, row_type in entries if row_id not in rows_by_id]
        expected_row_ids = [row_id for row_id, _row_type in expected_entries]
        if not missing_entries and expected_row_ids == row_ids:
            continue

        missing_oa_ids = [
            row_id
            for row_id, row_type in missing_entries
            if row_type == "oa" or (row_id.startswith("oa-") and not row_id.startswith(OA_ATTACHMENT_PREFIX))
        ]
        relation_mode = str(relation.get("relation_mode") or "")
        if relation_mode == OA_AUTO_OFFSET_MODE and missing_oa_ids and any(row_id not in existing_oa_row_ids for row_id in missing_oa_ids):
            after = _cancel_relation(relation, timestamp=timestamp, actor_id=actor_id)
            repaired_relations[str(case_id)] = after
            history.append(
                _history_entry(
                    operation_type="repair_cancel_stale_relation",
                    before=before,
                    after=after,
                    affected_row_ids=row_ids,
                    actor_id=actor_id,
                    timestamp=timestamp,
                    note="Cancelled active auto relation because its OA source row is no longer present after PostgreSQL migration.",
                )
            )
            changed_case_ids.append(str(case_id))
            cancelled_case_ids.append(str(case_id))
            continue

        new_entries = expected_entries
        if [row_id for row_id, _row_type in new_entries] == row_ids:
            continue
        if len(new_entries) < 2:
            after = _cancel_relation(relation, timestamp=timestamp, actor_id=actor_id)
            operation_type = "repair_cancel_empty_relation"
            cancelled_case_ids.append(str(case_id))
        else:
            after = _replace_relation_rows(relation, new_entries, timestamp=timestamp, actor_id=actor_id)
            operation_type = "repair_relation_rows"
            repaired_case_ids.append(str(case_id))
        repaired_relations[str(case_id)] = after
        history.append(
            _history_entry(
                operation_type=operation_type,
                before=before,
                after=after,
                affected_row_ids=sorted({*row_ids, *(row_id for row_id, _row_type in new_entries)}),
                actor_id=actor_id,
                timestamp=timestamp,
                note="Reconciled active relation row_ids with SQL-native workbench read model rows.",
            )
        )
        changed_case_ids.append(str(case_id))

    return {
        "status": "ok",
        "changed_case_ids": changed_case_ids,
        "repaired_case_ids": repaired_case_ids,
        "cancelled_case_ids": cancelled_case_ids,
        "changed_count": len(changed_case_ids),
        "repaired_count": len(repaired_case_ids),
        "cancelled_count": len(cancelled_case_ids),
        "snapshot": repaired_snapshot,
    }


def _load_current_workbench_rows(connection: PostgresConnection) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select row_id, source_kind, payload->>'derived_from_oa_id' as derived_from_oa_id
        from read_model.workbench_rows
        where scope_key = 'all'
        order by row_id
        """
    )


def _load_existing_oa_row_ids(connection: PostgresConnection) -> set[str]:
    rows = connection.fetch_all("select row_id from app.oa_applications order by row_id")
    return {str(row.get("row_id") or "").strip() for row in rows if str(row.get("row_id") or "").strip()}


def _replace_relation_rows(
    relation: dict[str, Any],
    entries: list[tuple[str, str]],
    *,
    timestamp: str,
    actor_id: str,
) -> dict[str, Any]:
    updated = deepcopy(relation)
    updated["row_ids"] = [row_id for row_id, _row_type in entries]
    updated["row_types"] = [row_type for _row_id, row_type in entries]
    updated["updated_at"] = timestamp
    metadata = dict(updated.get("special_metadata") if isinstance(updated.get("special_metadata"), dict) else {})
    metadata["relation_integrity_repaired_at"] = timestamp
    metadata["relation_integrity_repaired_by"] = actor_id
    updated["special_metadata"] = metadata
    return updated


def _cancel_relation(relation: dict[str, Any], *, timestamp: str, actor_id: str) -> dict[str, Any]:
    updated = deepcopy(relation)
    updated["status"] = "cancelled"
    updated["updated_at"] = timestamp
    updated["withdrawn_at"] = timestamp
    updated["withdrawn_by"] = actor_id
    metadata = dict(updated.get("special_metadata") if isinstance(updated.get("special_metadata"), dict) else {})
    metadata["relation_integrity_cancelled_at"] = timestamp
    metadata["relation_integrity_cancelled_by"] = actor_id
    updated["special_metadata"] = metadata
    return updated


def _history_entry(
    *,
    operation_type: str,
    before: dict[str, Any],
    after: dict[str, Any],
    affected_row_ids: list[str],
    actor_id: str,
    timestamp: str,
    note: str,
) -> dict[str, Any]:
    return {
        "operation_type": operation_type,
        "before_relations": [deepcopy(before)],
        "after_relations": [deepcopy(after)],
        "affected_row_ids": [row_id for row_id in affected_row_ids if row_id],
        "created_by": actor_id,
        "created_at": timestamp,
        "note": note,
    }


def _dedupe_entries(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    seen: set[str] = set()
    for row_id, row_type in entries:
        if not row_id or row_id in seen:
            continue
        seen.add(row_id)
        result.append((row_id, row_type or _row_type_for_id(row_id)))
    return result


def _row_type_for_id(row_id: str) -> str:
    return row_type_for_workbench_row_id(row_id, unknown="bank")


if __name__ == "__main__":
    raise SystemExit(main())
