from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    event_uuid,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    text,
    text_list,
)
from fin_ops_platform.services.postgres_snapshot_contracts import normalize_workbench_pair_relations
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


class PostgresWorkbenchRelationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select case_id as key, raw_payload from app.workbench_pair_relations order by case_id")
        if not rows:
            return {}
        history_rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relation_history
            order by
                (raw_payload->'raw_payload'->>'_stage04_child_index')::integer nulls last,
                occurred_at,
                case_id
            """
        )
        return normalize_workbench_pair_relations(
            {str(row.get("key")): row_payload(row, "raw_payload") for row in rows},
            [payload for row in history_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_row_ids = text_list(row_ids)
        normalized_case_ids = text_list(case_ids)
        predicates: list[str] = []
        params: list[Any] = []
        if normalized_row_ids:
            predicates.append("row_ids && %s::text[]")
            params.append(normalized_row_ids)
        if normalized_case_ids:
            predicates.append("case_id = any(%s::text[])")
            params.append(normalized_case_ids)
        if not predicates:
            return {}

        rows = self._connection.fetch_all(
            f"""
            select case_id as key, raw_payload
            from app.workbench_pair_relations
            where {' or '.join(predicates)}
            order by case_id
            """,
            tuple(params),
        )
        if not rows:
            return {}

        relations = {
            str(row.get("key")): row_payload(row, "raw_payload")
            for row in rows
        }
        selected_case_ids = text_list(list(relations))
        history_rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relation_history
            where case_id = any(%s::text[])
            order by
                (raw_payload->'raw_payload'->>'_stage04_child_index')::integer nulls last,
                occurred_at,
                case_id
            """,
            (selected_case_ids,),
        )
        return normalize_workbench_pair_relations(
            relations,
            [payload for row in history_rows if isinstance((payload := row_payload(row, "raw_payload")), dict)],
        )

    def load_active_workbench_pair_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        normalized_case_id = text(case_id)
        if not normalized_case_id:
            return None
        rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relations
            where case_id = %s
              and status = 'active'
            limit 1
            """,
            (normalized_case_id,),
        )
        if not rows:
            return None
        payload = row_payload(rows[0], "raw_payload")
        return dict(payload) if isinstance(payload, dict) else None

    def load_active_bank_requirement_relations_for_tag_codes(
        self,
        tag_codes: list[str],
    ) -> list[dict[str, Any]]:
        normalized_tag_codes = text_list(tag_codes)
        if not normalized_tag_codes:
            return []
        rows = self._connection.fetch_all(
            """
            select raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and special_metadata->>'paired_requirement_source' = 'bank_transaction_paired_policy'
              and (
                    special_metadata->'paired_requirement_tag_codes' ?| %s::text[]
                    or special_metadata->>'paired_requirement_tag_code' = any(%s::text[])
              )
            order by case_id
            """,
            (normalized_tag_codes, normalized_tag_codes),
        )
        return [
            dict(payload)
            for row in rows
            if isinstance((payload := row_payload(row, "raw_payload")), dict)
        ]

    def load_active_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_row_ids = text_list(row_ids)
        normalized_case_ids = text_list(case_ids)
        predicates: list[str] = []
        params: list[Any] = []
        if normalized_row_ids:
            predicates.append("row_ids && %s::text[]")
            params.append(normalized_row_ids)
        if normalized_case_ids:
            predicates.append("case_id = any(%s::text[])")
            params.append(normalized_case_ids)
        if not predicates:
            return {"pair_relations": {}}
        rows = self._connection.fetch_all(
            f"""
            select case_id as key, raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and ({' or '.join(predicates)})
            order by case_id
            """,
            tuple(params),
        )
        return {
            "pair_relations": {
                str(row.get("key")): payload
                for row in rows
                if isinstance((payload := row_payload(row, "raw_payload")), dict)
            }
        }

    def workbench_relation_source_bundle_from_source(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Read active canonical relation membership and version in one snapshot."""
        _ = tenant_id
        normalized_scope_key = text(scope_key) or ""
        normalized_row_ids = text_list(row_ids)
        if not normalized_row_ids:
            return {"rows": [], "source_versions": {}}
        month = month_start(normalized_scope_key)
        if month:
            summary_predicate = "(month_scope = %s::date or row_ids && %s::text[])"
            summary_params: list[Any] = [month, normalized_row_ids]
        else:
            summary_predicate = "row_ids && %s::text[]"
            summary_params = [normalized_row_ids]
        row = self._connection.fetch_one(
            f"""
            with selected_relations as materialized (
                select
                    case_id, status, relation_mode, month_scope, row_ids,
                    row_types, amount_check, special_metadata, raw_payload,
                    updated_at
                from app.workbench_pair_relations
                where status = 'active'
                  and row_ids && %s::text[]
            ),
            source_summary as (
                select
                    count(*)::integer as relation_count,
                    coalesce(max(updated_at)::text, '') as relation_updated_at,
                    md5(coalesce(string_agg(
                        concat_ws(
                            ':',
                            case_id,
                            relation_mode,
                            month_scope::text,
                            array_to_string(row_ids, ','),
                            array_to_string(row_types, ','),
                            updated_at::text
                        ),
                        '|' order by case_id
                    ), '')) as relation_membership_version
                from app.workbench_pair_relations
                where status = 'active'
                  and {summary_predicate}
            )
            select
                coalesce(
                    (
                        select jsonb_agg(
                            (to_jsonb(selected_relations) - 'updated_at')
                            order by updated_at desc, case_id
                        )
                        from selected_relations
                    ),
                    '[]'::jsonb
                ) as rows,
                source_summary.relation_count,
                source_summary.relation_updated_at,
                source_summary.relation_membership_version
            from source_summary
            """,
            tuple([normalized_row_ids, *summary_params]),
        )
        payload = row if isinstance(row, dict) else {}
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        return {
            "rows": [dict(item) for item in rows if isinstance(item, dict)],
            "source_versions": {
                "source": "app.workbench_pair_relations",
                "scope_key": normalized_scope_key,
                "relation_count": int_value(payload.get("relation_count"), 0),
                "relation_updated_at": text(payload.get("relation_updated_at")) or "",
                "relation_membership_version": text(
                    payload.get("relation_membership_version")
                )
                or "",
            },
        }

    def acquire_relation_member_locks(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> list[str]:
        normalized_row_ids = text_list(row_ids)
        normalized_row_types = text_list(row_types)
        normalized_case_ids = text_list(case_ids)
        member_keys: set[str] = set()
        for index, row_id in enumerate(normalized_row_ids):
            row_type = (
                normalized_row_types[index]
                if index < len(normalized_row_types)
                else row_type_for_workbench_row_id(row_id, unknown="")
            )
            if not row_type:
                raise ValueError(f"Cannot resolve Workbench relation member type for {row_id}.")
            member_keys.add(f"{row_type}:{row_id}")
        if normalized_case_ids:
            persisted_rows = self._connection.fetch_all(
                """
                select case_id, row_ids, row_types
                from app.workbench_pair_relations
                where case_id = any(%s::text[])
                  and status = 'active'
                order by case_id
                """,
                (normalized_case_ids,),
            )
            for relation in persisted_rows:
                persisted_ids = text_list(relation.get("row_ids"))
                persisted_types = text_list(relation.get("row_types"))
                for index, row_id in enumerate(persisted_ids):
                    row_type = (
                        persisted_types[index]
                        if index < len(persisted_types)
                        else row_type_for_workbench_row_id(row_id, unknown="")
                    )
                    if not row_type:
                        raise ValueError(f"Cannot resolve persisted Workbench relation member type for {row_id}.")
                    member_keys.add(f"{row_type}:{row_id}")
        ordered_keys = sorted(member_keys)
        if ordered_keys:
            self._connection.fetch_all(
                """
                select pg_advisory_xact_lock(
                    hashtextextended('workbench_relation_member:' || ordered.member_key, 0)
                )
                from (
                    select member_key
                    from unnest(%s::text[]) as members(member_key)
                    order by member_key
                ) ordered
                """,
                (ordered_keys,),
            )
        return ordered_keys

    def lock_canonical_relation_members(
        self,
        row_ids: list[str],
        *,
        row_types: list[str],
    ) -> list[str]:
        normalized_row_ids = text_list(row_ids)
        normalized_row_types = text_list(row_types)
        if len(normalized_row_ids) != len(normalized_row_types):
            raise ValueError("Workbench relation member ids and types must stay aligned.")

        requested = {
            (row_type, row_id)
            for row_id, row_type in zip(normalized_row_ids, normalized_row_types, strict=True)
            if row_type in {"oa", "bank", "invoice"}
        }
        found: set[tuple[str, str]] = set()
        queries = {
            "oa": """
                select row_id
                from app.oa_applications
                where row_id = any(%s::text[])
                  and status <> 'deleted'
                order by row_id
                for key share
            """,
            "bank": """
                select coalesce(legacy_mongo_id, id::text) as row_id
                from app.bank_transactions
                where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                  and status <> 'deleted'
                order by coalesce(legacy_mongo_id, id::text)
                for key share
            """,
            "invoice": """
                select coalesce(legacy_mongo_id, id::text) as row_id
                from app.invoices
                where coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                  and status <> 'deleted'
                order by coalesce(legacy_mongo_id, id::text)
                for key share
            """,
        }
        for row_type, sql in queries.items():
            typed_row_ids = sorted(row_id for member_type, row_id in requested if member_type == row_type)
            if not typed_row_ids:
                continue
            found.update(
                (row_type, text(row.get("row_id")))
                for row in self._connection.fetch_all(sql, (typed_row_ids,))
                if text(row.get("row_id"))
            )
        return sorted(f"{row_type}:{row_id}" for row_type, row_id in requested - found)

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | None = None,
    ) -> None:
        self._save_workbench_pair_relations(
            snapshot,
            changed_case_ids=changed_case_ids,
        )

    def save_workbench_pair_relation_delta(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        self._save_workbench_pair_relations(
            snapshot,
            changed_case_ids=set(text_list(changed_case_ids)),
        )

    def _save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | None,
    ) -> None:
        def write(connection: Any) -> None:
            relations = snapshot.get("pair_relations") if isinstance(snapshot, dict) else None
            changed_ids = {str(item) for item in changed_case_ids} if changed_case_ids is not None else None
            for case_id, payload in iter_mapping(relations):
                if changed_ids is not None and case_id not in changed_ids:
                    continue
                connection.execute(
                    """
                    insert into app.workbench_pair_relations(
                        case_id, relation_mode, status, version, month_scope, row_ids, row_types,
                        note, amount_check, special_metadata, source_versions, raw_payload
                    )
                    values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s)
                    on conflict (case_id) do update set
                        relation_mode = excluded.relation_mode,
                        status = excluded.status,
                        version = excluded.version,
                        month_scope = excluded.month_scope,
                        row_ids = excluded.row_ids,
                        row_types = excluded.row_types,
                        note = excluded.note,
                        amount_check = excluded.amount_check,
                        special_metadata = excluded.special_metadata,
                        source_versions = excluded.source_versions,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        case_id,
                        text(payload.get("relation_mode") or payload.get("mode") or "unknown"),
                        text(payload.get("status") or "active"),
                        int_value(payload.get("version"), 1),
                        month_start(payload.get("month_scope") or payload.get("scope_month") or payload.get("month")),
                        text_list(payload.get("row_ids")),
                        text_list(payload.get("row_types")),
                        text(payload.get("note")),
                        jsonb(payload.get("amount_check") if isinstance(payload.get("amount_check"), dict) else {}),
                        jsonb(payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {}),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            self._append_workbench_pair_relation_history(
                connection,
                history,
                changed_case_ids=changed_ids,
            )

        run_in_transaction(self._connection, write)

    def _append_workbench_pair_relation_history(
        self,
        connection: Any,
        history: Any,
        *,
        changed_case_ids: set[str] | None,
    ) -> None:
        if not isinstance(history, list):
            return
        case_ids = {
            normalized
            for item in history
            if isinstance(item, dict)
            for normalized in self._history_case_ids(item)
        }
        if changed_case_ids is not None:
            case_ids &= changed_case_ids
        if not case_ids:
            return
        rows_by_id: dict[str, tuple[Any, ...]] = {}
        for item in history:
            if not isinstance(item, dict):
                continue
            item_case_ids = self._history_case_ids(item)
            if changed_case_ids is not None and not (set(item_case_ids) & changed_case_ids):
                continue
            for case_id in item_case_ids:
                row_id = event_uuid("workbench_pair_relation_history", case_id, item)
                rows_by_id[row_id] = (
                    row_id,
                    case_id,
                    text(item.get("operation_type") or item.get("event_type") or "unknown"),
                    text(item.get("created_by") or item.get("actor_id")),
                    text(item.get("created_at") or item.get("occurred_at")),
                    text(item.get("request_id")),
                    jsonb(item.get("before_relations") if isinstance(item.get("before_relations"), list) else item.get("before_payload") or {}),
                    jsonb(item.get("after_relations") if isinstance(item.get("after_relations"), list) else item.get("after_payload") or {}),
                    jsonb({"normalized_payload": item}),
                )
        rows = list(rows_by_id.values())
        if not rows:
            return
        value_sql = ", ".join(
            ["(%s::uuid, %s::text, %s::text, %s::text, %s::text, %s::text, %s::jsonb, %s::jsonb, %s::jsonb)"]
            * len(rows)
        )
        connection.execute(
            f"""
            with input(
                id, case_id, event_type, actor_id, occurred_at, request_id,
                before_payload, after_payload, raw_payload
            ) as (
                values {value_sql}
            )
            insert into app.workbench_pair_relation_history(
                id, relation_id, case_id, event_type, actor_id, occurred_at,
                request_id, before_payload, after_payload, raw_payload
            )
            select
                input.id,
                relation.id,
                input.case_id,
                input.event_type,
                input.actor_id,
                coalesce(input.occurred_at::timestamptz, now()),
                nullif(input.request_id, ''),
                input.before_payload,
                input.after_payload,
                input.raw_payload
            from input
            left join app.workbench_pair_relations relation on relation.case_id = input.case_id
            on conflict (id) do nothing
            """,
            tuple(value for row in rows for value in row),
        )

    @staticmethod
    def _history_case_ids(item: dict[str, Any]) -> list[str]:
        case_ids: list[str] = []
        for key in ("case_id", "relation_case_id"):
            if normalized := text(item.get(key)):
                case_ids.append(normalized)
        for collection_key in ("after_relations", "before_relations"):
            relations = item.get(collection_key)
            if isinstance(relations, list):
                for relation in relations:
                    if isinstance(relation, dict) and (normalized := text(relation.get("case_id"))):
                        case_ids.append(normalized)
        return sorted(set(case_ids))
