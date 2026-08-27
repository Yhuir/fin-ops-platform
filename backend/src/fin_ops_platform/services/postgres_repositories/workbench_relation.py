from __future__ import annotations

from hashlib import sha1
from typing import Any, Callable

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
from fin_ops_platform.services.oa_payment_status_reconcile_contract import (
    OA_PAYMENT_STATUS_RECONCILE_EVENT,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


class PostgresWorkbenchRelationRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._post_commit_callback_registrar: Callable[[Callable[[], None]], None] | None = None

    def bind_post_commit_callback_registrar(
        self,
        registrar: Callable[[Callable[[], None]], None],
    ) -> None:
        self._post_commit_callback_registrar = registrar

    def register_post_commit_callback(self, callback: Callable[[], None]) -> bool:
        registrar = self._post_commit_callback_registrar
        if registrar is None:
            return False
        registrar(callback)
        return True

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

    def load_active_workbench_pair_relation_by_case_id_for_update(
        self,
        case_id: str,
    ) -> dict[str, Any] | None:
        normalized_case_id = text(case_id)
        if not normalized_case_id:
            return None
        rows = self._connection.fetch_all(
            """
            select case_id, relation_mode, row_ids, row_types, raw_payload, updated_at
            from app.workbench_pair_relations
            where case_id = %s
              and status = 'active'
            limit 1
            for update
            """,
            (normalized_case_id,),
        )
        if not rows:
            return None
        row = rows[0]
        payload = row_payload(row, "raw_payload")
        return {
            **(dict(payload) if isinstance(payload, dict) else {}),
            "case_id": normalized_case_id,
            "relation_mode": text(row.get("relation_mode")),
            "row_ids": text_list(row.get("row_ids")),
            "row_types": text_list(row.get("row_types")),
            "updated_at": row.get("updated_at"),
        }

    def load_active_bank_requirement_relations_for_tag_codes(
        self,
        tag_codes: list[str],
    ) -> list[dict[str, Any]]:
        normalized_tag_codes = text_list(tag_codes)
        if not normalized_tag_codes:
            return []
        rows = self._connection.fetch_all(
            """
            select
                relation.raw_payload,
                coalesce(
                    array(
                        select distinct to_char(bank.txn_month, 'YYYY-MM')
                        from app.bank_transactions bank
                        where coalesce(bank.legacy_mongo_id, bank.id::text)
                              = any(relation.row_ids)
                          and bank.status <> 'deleted'
                          and bank.txn_month is not null
                        order by 1
                    ),
                    array[]::text[]
                ) as canonical_bank_months
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and relation.case_id !~ '^(candidate|decision|temp):'
              and relation.special_metadata->>'paired_requirement_source' = 'bank_transaction_paired_policy'
              and (
                    relation.special_metadata->'paired_requirement_tag_codes' ?| %s::text[]
                    or relation.special_metadata->>'paired_requirement_tag_code' = any(%s::text[])
              )
            order by relation.case_id
            """,
            (normalized_tag_codes, normalized_tag_codes),
        )
        relations: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "raw_payload")
            if not isinstance(payload, dict):
                continue
            relation = dict(payload)
            relation["_canonical_bank_months"] = list(
                dict.fromkeys(text_list(row.get("canonical_bank_months")))
            )
            relations.append(relation)
        return relations

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

    def load_active_workbench_pair_relations_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_row_ids = text_list(row_ids)
        normalized_row_types = text_list(row_types)
        if len(normalized_row_ids) != len(normalized_row_types):
            raise ValueError("row_types must align with row_ids.")
        normalized_case_ids = text_list(case_ids)
        predicates: list[str] = []
        params: list[Any] = []
        if normalized_row_ids:
            predicates.append(
                """
                exists (
                    select 1
                    from unnest(relation.row_ids, relation.row_types)
                         as member(row_id, row_type)
                    join unnest(%s::text[], %s::text[])
                         as requested(row_id, row_type)
                      on requested.row_id = member.row_id
                     and requested.row_type = case
                         when member.row_type in ('oa', 'oa_application') then 'oa'
                         when member.row_type in ('bank', 'bank_transaction') then 'bank'
                         when member.row_type in (
                             'invoice', 'invoice_record', 'formal', 'formal_invoice',
                             'input', 'input_invoice', 'output', 'output_invoice',
                             'etc_summary', 'etc_invoice_summary'
                         ) then 'invoice'
                         else member.row_type
                     end
                )
                """
            )
            params.extend((normalized_row_ids, normalized_row_types))
        if normalized_case_ids:
            predicates.append("relation.case_id = any(%s::text[])")
            params.append(normalized_case_ids)
        if not predicates:
            return {"pair_relations": {}}
        rows = self._connection.fetch_all(
            f"""
            select relation.case_id as key, relation.raw_payload
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and cardinality(relation.row_ids) = cardinality(relation.row_types)
              and ({' or '.join(predicates)})
            order by relation.case_id
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
        member_keys.update(f"case:{case_id}" for case_id in normalized_case_ids)
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
        tenant_id: str | None = None,
    ) -> list[str]:
        normalized_row_ids = text_list(row_ids)
        normalized_row_types = text_list(row_types)
        normalized_tenant_id = text(tenant_id) or ""
        if len(normalized_row_ids) != len(normalized_row_types):
            raise ValueError("Workbench relation member ids and types must stay aligned.")

        requested = {
            (row_type, row_id)
            for row_id, row_type in zip(normalized_row_ids, normalized_row_types, strict=True)
            if row_type in {"oa", "bank", "invoice"}
        }
        found: set[tuple[str, str]] = set()
        queries = {
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
        oa_row_ids = sorted(
            row_id for member_type, row_id in requested if member_type == "oa"
        )
        if oa_row_ids:
            oa_rows = self._connection.fetch_all(
                """
                with completed_oa as materialized (
                    select oa.row_id
                    from app.oa_applications oa
                    where oa.row_id = any(%s::text[])
                      and oa.status <> 'deleted'
                      and (
                            oa.workflow_status is null
                            or oa.workflow_status = ''
                            or oa.workflow_status in (
                                'completed', '已完成', 'approved',
                                'APPROVED', 'Approved', '2'
                            )
                      )
                    order by oa.row_id
                    for key share of oa
                ),
                in_progress_oa as materialized (
                    select admission.oa_id as row_id
                    from app.oa_pending_payment_admissions admission
                    where admission.tenant_id = %s
                      and admission.oa_id = any(%s::text[])
                      and admission.workflow_status = 'in_progress'
                    order by admission.oa_id, admission.scope_key
                    for key share of admission
                ),
                source_candidates as (
                    select row_id from completed_oa
                    union all
                    select row_id from in_progress_oa
                )
                select row_id, count(*)::integer as source_count
                from source_candidates
                group by row_id
                order by row_id
                """,
                (oa_row_ids, normalized_tenant_id, oa_row_ids),
            )
            found.update(
                ("oa", resolved_row_id)
                for row in oa_rows
                if int(row.get("source_count") or 0) == 1
                if (resolved_row_id := text(row.get("row_id")))
            )
        for row_type, sql in queries.items():
            typed_row_ids = sorted(row_id for member_type, row_id in requested if member_type == row_type)
            if not typed_row_ids:
                continue
            found.update(
                (row_type, text(row.get("row_id")))
                for row in self._connection.fetch_all(sql, (typed_row_ids,))
                if text(row.get("row_id"))
            )
        etc_summary_row_ids = sorted(
            row_id
            for member_type, row_id in requested
            if member_type == "invoice" and row_id.startswith("etc-summary-")
        )
        if etc_summary_row_ids:
            etc_summary_rows = self._connection.fetch_all(
                """
                select
                    'etc-summary-' || regexp_replace(
                        coalesce(
                            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                            batch.business_batch_id
                        ),
                        '[^A-Za-z0-9_-]+',
                        '-',
                        'g'
                    ) as row_id
                from app.etc_business_batches batch
                where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                  and 'etc-summary-' || regexp_replace(
                        coalesce(
                            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                            batch.business_batch_id
                        ),
                        '[^A-Za-z0-9_-]+',
                        '-',
                        'g'
                      ) = any(%s::text[])
                  and exists (
                      select 1
                      from app.etc_invoices invoice
                      where invoice.business_batch_id = batch.business_batch_id
                        and invoice.status <> 'deleted'
                  )
                order by row_id
                for key share of batch
                """,
                (etc_summary_row_ids,),
            )
            found.update(
                ("invoice", resolved_row_id)
                for row in etc_summary_rows
                if (resolved_row_id := text(row.get("row_id")))
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
            selected_relations = [
                (case_id, payload)
                for case_id, payload in iter_mapping(relations)
                if changed_ids is None or case_id in changed_ids
            ]
            reconcile_candidates = [
                (case_id, payload, event_payload)
                for case_id, payload in selected_relations
                if (event_payload := _oa_payment_reconcile_payload(case_id, payload)) is not None
            ]
            existing_reconcile_signatures = _existing_reconcile_signatures(
                connection,
                [case_id for case_id, _payload, _event_payload in reconcile_candidates],
            )
            reconcile_events: list[tuple[str, dict[str, Any]]] = []
            for case_id, payload in selected_relations:
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
                    where app.workbench_pair_relations.relation_mode is distinct from excluded.relation_mode
                       or app.workbench_pair_relations.status is distinct from excluded.status
                       or app.workbench_pair_relations.version is distinct from excluded.version
                       or app.workbench_pair_relations.month_scope is distinct from excluded.month_scope
                       or app.workbench_pair_relations.row_ids is distinct from excluded.row_ids
                       or app.workbench_pair_relations.row_types is distinct from excluded.row_types
                       or app.workbench_pair_relations.note is distinct from excluded.note
                       or app.workbench_pair_relations.amount_check is distinct from excluded.amount_check
                       or app.workbench_pair_relations.special_metadata is distinct from excluded.special_metadata
                       or app.workbench_pair_relations.source_versions is distinct from excluded.source_versions
                       or app.workbench_pair_relations.raw_payload #- '{normalized_payload,updated_at}'
                          is distinct from excluded.raw_payload #- '{normalized_payload,updated_at}'
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
                event_payload = _oa_payment_reconcile_payload(case_id, payload)
                if (
                    event_payload is not None
                    and existing_reconcile_signatures.get(case_id)
                    != _reconcile_signature(payload)
                ):
                    reconcile_events.append((case_id, event_payload))
            history = snapshot.get("pair_relation_history") if isinstance(snapshot, dict) else None
            self._append_workbench_pair_relation_history(
                connection,
                history,
                changed_case_ids=changed_ids,
            )
            queue = RuntimeQueueRepository(connection)
            for case_id, event_payload in reconcile_events:
                fingerprint = sha1(
                    "|".join(
                        [
                            case_id,
                            str(event_payload["relation_status"]),
                            str(event_payload["relation_version"]),
                            *event_payload["oa_row_ids"],
                        ]
                    ).encode("utf-8")
                ).hexdigest()
                queue.enqueue_in_transaction(
                    transaction=connection,
                    event_type=OA_PAYMENT_STATUS_RECONCILE_EVENT,
                    aggregate_type="workbench_relation",
                    aggregate_id=case_id,
                    scope_type="oa_payment_status",
                    scope_key=case_id,
                    dedupe_key=f"{OA_PAYMENT_STATUS_RECONCILE_EVENT}:{fingerprint}",
                    payload=event_payload,
                    source_version=event_payload["relation_version"],
                    priority="high",
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


def _oa_payment_reconcile_payload(case_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    row_ids = text_list(payload.get("row_ids"))
    row_types = text_list(payload.get("row_types"))
    if len(row_ids) != len(row_types):
        return None
    oa_row_ids = [
        row_id
        for row_id, row_type in zip(row_ids, row_types, strict=True)
        if row_type in {"oa", "oa_application"}
    ]
    has_bank = any(row_type in {"bank", "bank_transaction"} for row_type in row_types)
    if not oa_row_ids or not has_bank:
        return None
    return {
        "oa_row_ids": oa_row_ids,
        "relation_case_id": case_id,
        "relation_status": text(payload.get("status")) or "active",
        "relation_version": int_value(payload.get("version"), 1),
        "reason": "workbench_relation_changed",
    }


def _existing_reconcile_signatures(
    connection: Any,
    case_ids: list[str],
) -> dict[str, tuple[str, int, tuple[str, ...], tuple[str, ...]]]:
    normalized_case_ids = text_list(case_ids)
    if not normalized_case_ids:
        return {}
    rows = connection.fetch_all(
        """
        select case_id, status, version, row_ids, row_types
        from app.workbench_pair_relations
        where case_id = any(%s::text[])
        """,
        (normalized_case_ids,),
    )
    return {
        case_id: (
            text(row.get("status")) or "active",
            int_value(row.get("version"), 1),
            tuple(text_list(row.get("row_ids"))),
            tuple(text_list(row.get("row_types"))),
        )
        for row in rows
        if (case_id := text(row.get("case_id")))
    }


def _reconcile_signature(
    payload: dict[str, Any],
) -> tuple[str, int, tuple[str, ...], tuple[str, ...]]:
    return (
        text(payload.get("status")) or "active",
        int_value(payload.get("version"), 1),
        tuple(text_list(payload.get("row_ids"))),
        tuple(text_list(payload.get("row_types"))),
    )
