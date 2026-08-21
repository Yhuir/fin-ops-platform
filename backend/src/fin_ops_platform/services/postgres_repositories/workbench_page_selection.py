from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from typing import Any, TypeVar

from fin_ops_platform.services.postgres_repositories.common import (
    month_start,
    row_payload,
    text_list,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_hydration import (
    PostgresWorkbenchPageHydrationRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    _COMPLETED_OA_SQL,
    _RELATION_EXTERNAL_BATCH_SQL,
    _VISIBLE_INVOICE_SQL,
)
from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
    WorkbenchRelationPreviewSelectionError,
    is_workbench_data_integrity_query_error,
    is_transient_postgres_query_error,
)
from fin_ops_platform.services.workbench_filter_options import (
    normalize_workbench_scope_key,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_row_identity import (
    workbench_row_identity_key,
)
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


T = TypeVar("T")
ROW_TYPES = frozenset({"oa", "bank", "invoice"})
WORKBENCH_SELECTION_QUERY_TIMEOUT_SECONDS = 5


class PostgresWorkbenchPageSelectionRepository:
    """Canonical selection boundary shared by preview, tools, and write UoWs."""

    def __init__(self, connection: Any, *, tenant_id: str) -> None:
        self._connection = connection
        self._tenant_id = str(tenant_id or "").strip()
        if not self._tenant_id:
            raise ValueError("tenant_id is required for Workbench canonical selection.")

    def get_workbench_relation_preview_selection(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        row_types: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._in_snapshot(
            lambda repository: repository._relation_preview_selection(
                scope_key=scope_key,
                row_ids=row_ids,
                row_types=row_types,
            )
        )

    def get_canonical_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        return self._in_snapshot(
            lambda repository: repository._canonical_rows_by_ids(
                row_ids=row_ids,
                row_types=row_types,
            )
        )

    def get_canonical_rows_by_ids_in_current_transaction(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """Hydrate exact canonical rows without opening a nested transaction."""

        return self._canonical_rows_by_ids(row_ids=row_ids, row_types=row_types)

    def get_oa_expense_items_by_row_ids_in_current_transaction(
        self,
        oa_row_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        """Lock and return the current canonical expense items for exact OA rows."""

        normalized_ids = [str(row_id or "").strip() for row_id in oa_row_ids]
        if (
            not normalized_ids
            or any(not row_id for row_id in normalized_ids)
            or len(set(normalized_ids)) != len(normalized_ids)
        ):
            raise ValueError("Canonical OA row ids must be non-empty and unique.")
        rows = self._connection.fetch_all(
            f"""
            with requested as materialized (
                select row_id, position::bigint
                from unnest(%s::text[]) with ordinality
                    as requested_row(row_id, position)
            ),
            completed as materialized (
                select
                    requested.position,
                    oa.row_id,
                    case
                        when jsonb_typeof(oa.normalized_payload->'expense_items') = 'array'
                            then oa.normalized_payload->'expense_items'
                        else '[]'::jsonb
                    end as expense_items
                from requested
                join app.oa_applications oa on oa.row_id = requested.row_id
                where oa.status <> 'deleted'
                  and {_COMPLETED_OA_SQL}
                for share of oa
            ),
            pending as materialized (
                select
                    requested.position,
                    admission.oa_id as row_id,
                    case
                        when jsonb_typeof(admission.source_payload->'expense_items') = 'array'
                            then admission.source_payload->'expense_items'
                        else '[]'::jsonb
                    end as expense_items
                from requested
                join app.oa_pending_payment_admissions admission
                  on admission.oa_id = requested.row_id
                where admission.tenant_id = %s
                  and admission.workflow_status = 'in_progress'
                for share of admission
            )
            select position, row_id, expense_items
            from completed
            union all
            select position, row_id, expense_items
            from pending
            order by position
            """,
            (normalized_ids, self._tenant_id),
        )
        resolved_ids = [str(row.get("row_id") or "").strip() for row in rows]
        if resolved_ids != normalized_ids:
            raise ValueError("Canonical OA expense item source changed.")
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            expense_items = row_payload(row, "expense_items")
            if not isinstance(expense_items, list):
                expense_items = []
            result[row_id] = [
                dict(item) for item in expense_items if isinstance(item, dict)
            ]
        return result

    def resolve_canonical_identity_type_candidates_in_current_transaction(
        self,
        row_ids: list[str],
    ) -> dict[str, list[str]]:
        """Resolve raw IDs through the same source arbitration used by direct selection.

        The caller owns the transaction. Candidate multiplicity is preserved so legacy
        identity repair can fail closed for both cross-pane and same-pane ambiguity.
        """
        requested = self._selection_identities(row_ids=row_ids, row_types=None)
        requested_ids = [row_id for _row_type, row_id in requested]
        rows = self._resolve_source_descriptors(
            row_ids=requested_ids,
            row_types=None,
            scope_key="all",
            require_exact=False,
        )
        candidates = {row_id: [] for row_id in requested_ids}
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            row_type = self._row_type(row.get("row_type"))
            if row_id in candidates and row_type:
                candidates[row_id].append(row_type)
        return candidates

    def list_workbench_ignored_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        return self._in_snapshot(
            lambda repository: repository._ignored_rows(scope_key=scope_key)
        )

    def validate_workbench_relation_selection_in_current_transaction(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        row_types: list[str],
    ) -> list[dict[str, str]]:
        identities = self._selection_identities(row_ids=row_ids, row_types=row_types)
        try:
            source_rows = self._resolve_source_descriptors(
                row_ids=[row_id for _row_type, row_id in identities],
                row_types=[row_type for row_type, _row_id in identities],
                scope_key=self._scope_key(scope_key),
            )
            matches = [
                (str(row.get("row_type") or ""), str(row.get("row_id") or ""))
                for row in source_rows
            ]
            if matches != identities:
                raise ValueError("Canonical Workbench selection changed.")
        except ValueError as error:
            raise WorkbenchWriteConflict(
                action="confirm_link",
                reason="canonical_selection_changed",
                expected={
                    "row_ids": [row_id for _row_type, row_id in identities],
                    "row_types": [row_type for row_type, _row_id in identities],
                },
                actual={"error": "relation_preview_rows_missing"},
            ) from error
        result: list[dict[str, str]] = []
        for source, (row_type, row_id) in zip(source_rows, matches, strict=True):
            result.append({
                "row_id": row_id,
                "pane": row_type,
                "source_kind": str(source.get("source_kind") or row_type),
                "external_etc_batch_id": str(
                    source.get("external_etc_batch_id") or ""
                ),
            })
        return result

    def _in_snapshot(
        self,
        operation: Callable[["PostgresWorkbenchPageSelectionRepository"], T],
    ) -> T:
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            raise RuntimeError("Workbench canonical selection requires transaction support.")
        try:
            with transaction_factory() as transaction:
                transaction.execute("set transaction isolation level repeatable read read only")
                transaction.execute(
                    f"set local statement_timeout = '{WORKBENCH_SELECTION_QUERY_TIMEOUT_SECONDS}s'"
                )
                return operation(
                    PostgresWorkbenchPageSelectionRepository(
                        transaction,
                        tenant_id=self._tenant_id,
                    )
                )
        except Exception as error:
            if is_transient_postgres_query_error(
                error
            ) or is_workbench_data_integrity_query_error(error):
                raise WorkbenchDirectQueryUnavailable(
                    "Workbench canonical selection is temporarily unavailable."
                ) from error
            raise

    def _relation_preview_selection(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        row_types: list[str] | None,
    ) -> dict[str, Any]:
        normalized_scope = self._scope_key(scope_key)
        identities = self._selection_identities(row_ids=row_ids, row_types=row_types)
        descriptors = self._selection_descriptors(
            scope_key=normalized_scope,
            identities=identities,
        )
        matched_identities = self._validated_matches(
            identities=identities,
            descriptors=descriptors,
        )
        groups = PostgresWorkbenchPageHydrationRepository(
            self._connection,
            tenant_id=self._tenant_id,
        ).hydrate_groups(
            scope_key=normalized_scope,
            descriptors=[{**descriptor, "zone": ""} for descriptor in descriptors],
            detail_level="full",
        )
        if len(groups) != len(descriptors):
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )
        rows_by_identity: dict[tuple[str, str], dict[str, Any]] = {}
        group_rows: list[dict[str, Any]] = []
        for group in groups:
            for row in PostgresWorkbenchPageHydrationRepository.group_rows(group):
                row_type = self._row_type(row.get("type"))
                row_id = str(row.get("id") or "").strip()
                if not row_type or not row_id:
                    continue
                key = (row_type, row_id)
                previous = rows_by_identity.setdefault(key, row)
                if previous is not row and previous != row:
                    raise WorkbenchRelationPreviewSelectionError(
                        code="relation_preview_rows_ambiguous",
                        message="所选关联台记录内容不一致，请刷新后重试。",
                    )
                group_rows.append(row)
        missing = [identity for identity in matched_identities if identity not in rows_by_identity]
        if missing:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )
        selected_rows = [rows_by_identity[identity] for identity in matched_identities]
        selected_set = set(matched_identities)
        context_rows = self._dedupe_rows(
            row
            for row in group_rows
            if (
                self._row_type(row.get("type")),
                str(row.get("id") or "").strip(),
            )
            not in selected_set
        )

        return {
            "scope_key": normalized_scope,
            "selected_row_ids": [row_id for _row_type, row_id in matched_identities],
            "selected_row_types": [row_type for row_type, _row_id in matched_identities],
            "selected_rows": selected_rows,
            "context_rows": context_rows,
            "rows": [*selected_rows, *context_rows],
        }

    def _selection_descriptors(
        self,
        *,
        scope_key: str,
        identities: list[tuple[str, str]],
    ) -> list[dict[str, Any]]:
        requested_types = [row_type for row_type, _row_id in identities]
        try:
            sources = self._resolve_source_descriptors(
                row_ids=[row_id for _row_type, row_id in identities],
                row_types=requested_types if any(requested_types) else None,
                scope_key=scope_key,
            )
        except ValueError as error:
            ambiguous = "ambiguous" in str(error).lower()
            raise WorkbenchRelationPreviewSelectionError(
                code=(
                    "relation_preview_rows_ambiguous"
                    if ambiguous
                    else "relation_preview_rows_missing"
                ),
                message=(
                    "所选关联台记录内容不一致，请刷新后重试。"
                    if ambiguous
                    else "所选工作台记录已变化，请刷新后重试。"
                ),
            ) from error
        positions = [int(row.get("position") or 0) for row in sources]
        row_types = [str(row.get("row_type") or "") for row in sources]
        row_ids = [str(row.get("row_id") or "") for row in sources]
        source_kinds = [str(row.get("source_kind") or "") for row in sources]
        external_batch_ids = [
            str(row.get("external_etc_batch_id") or "") for row in sources
        ]
        scope_months = [row.get("scope_month") for row in sources]
        updated_ats = [row.get("updated_at") for row in sources]
        normalized_member_type = self._normalized_member_type_sql("member.row_type")
        return self._connection.fetch_all(
            f"""
            with selected_sources as materialized (
                select
                    source.position::bigint as selected_position,
                    source.row_type,
                    source.row_id,
                    source.source_kind,
                    nullif(source.external_batch_id, '') as external_etc_batch_id,
                    source.scope_month,
                    source.updated_at
                from unnest(
                    %s::bigint[], %s::text[], %s::text[], %s::text[],
                    %s::text[], %s::date[], %s::timestamptz[]
                ) as source(
                    position, row_type, row_id, source_kind,
                    external_batch_id, scope_month, updated_at
                )
            ),
            candidate_relations as materialized (
                select relation.*,
                       {_RELATION_EXTERNAL_BATCH_SQL} as external_etc_batch_id
                from app.workbench_pair_relations relation
                where relation.status = 'active'
                  and relation.row_ids && %s::text[]
                  and exists (
                      select 1
                      from unnest(relation.row_ids, relation.row_types)
                          as member(row_id, row_type)
                      join selected_sources source
                        on source.row_id = member.row_id
                       and source.row_type = {normalized_member_type}
                  )
            ),
            invalid_relation_shapes as materialized (
                select relation.id
                from candidate_relations relation
                where coalesce(cardinality(relation.row_ids), -1) = 0
                   or coalesce(cardinality(relation.row_ids), -1)
                        <> coalesce(cardinality(relation.row_types), -2)
                   or exists (
                        select 1
                        from unnest(relation.row_ids, relation.row_types)
                            as member(row_id, row_type)
                        where nullif(btrim(member.row_id), '') is null
                           or {normalized_member_type} is null
                   )
                   or exists (
                        select 1
                        from unnest(relation.row_ids, relation.row_types)
                            as member(row_id, row_type)
                        group by member.row_id, {normalized_member_type}
                        having count(*) > 1
                   )
            ),
            relation_shape_guard as materialized (
                select 1 / case when count(*) = 0 then 1 else 0 end as guard
                from invalid_relation_shapes
            ),
            relation_members as materialized (
                select
                    relation.id as relation_id,
                    member.ordinality,
                    member.row_id,
                    {normalized_member_type} as row_type
                from candidate_relations relation
                cross join relation_shape_guard guard
                cross join lateral unnest(relation.row_ids, relation.row_types)
                    with ordinality as member(row_id, row_type, ordinality)
                where guard.guard = 1
            ),
            matched_selection as materialized (
                select
                    source.selected_position,
                    relation.id as relation_id,
                    member.row_type,
                    member.row_id,
                    source.source_kind
                from selected_sources source
                join relation_members member
                  on member.row_type = source.row_type
                 and member.row_id = source.row_id
                join candidate_relations relation on relation.id = member.relation_id
            ),
            relation_descriptors as materialized (
                select
                    'case:' || relation.case_id as internal_key,
                    relation.case_id as detail_key,
                    'relation'::text as group_kind,
                    case
                        when exists (
                            select 1
                            from relation_members member
                            join app.oa_pending_payment_admissions pending
                              on member.row_type = 'oa'
                             and pending.tenant_id = %s
                             and pending.workflow_status = 'in_progress'
                             and pending.oa_id = member.row_id
                            where member.relation_id = relation.id
                        ) then 'unpaired'
                        when coalesce(relation.special_metadata->>'source', '')
                             = 'batch_accounting' then 'paired'
                        when 'oa' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        )) and not ('bank' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        ))) then 'unpaired'
                        when 'bank' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        )) and coalesce(
                            (relation.special_metadata->>'requires_oa')::boolean,
                            (relation.special_metadata->>'paired_requires_oa')::boolean,
                            true
                        ) and not ('oa' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        ))) then 'unpaired'
                        when 'bank' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        )) and coalesce(
                            (relation.special_metadata->>'requires_invoice')::boolean,
                            (relation.special_metadata->>'paired_requires_invoice')::boolean,
                            true
                        ) and not ('invoice' = any(array(
                            select member.row_type from relation_members member
                            where member.relation_id = relation.id
                        ))) then 'unpaired'
                        else 'paired'
                    end as zone,
                    relation.row_ids as member_ids,
                    array(
                        select member.row_type
                        from relation_members member
                        where member.relation_id = relation.id
                        order by member.ordinality
                    )::text[] as member_types,
                    relation.month_scope as scope_month,
                    relation.updated_at,
                    relation.external_etc_batch_id,
                    array_remove(array[
                        case when 'oa' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  )) and not ('bank' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  ))) then 'bank' end,
                        case when 'bank' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  )) and coalesce(
                                      (relation.special_metadata->>'requires_oa')::boolean,
                                      (relation.special_metadata->>'paired_requires_oa')::boolean,
                                      true
                                  ) and not ('oa' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  )) ) and coalesce(
                                      relation.special_metadata->>'source', ''
                                  ) <> 'batch_accounting' then 'oa' end,
                        case when 'bank' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  )) and coalesce(
                                      (relation.special_metadata->>'requires_invoice')::boolean,
                                      (relation.special_metadata->>'paired_requires_invoice')::boolean,
                                      true
                                  ) and not ('invoice' = any(array(
                                      select member.row_type from relation_members member
                                      where member.relation_id = relation.id
                                  )) ) and coalesce(
                                      relation.special_metadata->>'source', ''
                                  ) <> 'batch_accounting' then 'invoice' end
                    ], null)::text[] as missing_row_types,
                    array_agg(match.selected_position order by match.selected_position)
                        as selected_positions,
                    array_agg(match.row_type order by match.selected_position)
                        as selected_row_types,
                    array_agg(match.row_id order by match.selected_position)
                        as selected_row_ids,
                    array_agg(match.source_kind order by match.selected_position)
                        as selected_source_kinds
                from candidate_relations relation
                join matched_selection match on match.relation_id = relation.id
                group by
                    relation.id, relation.case_id, relation.row_ids,
                    relation.month_scope, relation.updated_at,
                    relation.special_metadata, relation.external_etc_batch_id
            ),
            singleton_descriptors as materialized (
                select
                    'row:' || source.row_type || ':' || source.row_id as internal_key,
                    'v1:' || to_char(source.scope_month, 'YYYY-MM') || ':' ||
                        source.row_type || ':' ||
                        encode(convert_to(source.row_id, 'UTF8'), 'hex') as detail_key,
                    'unpaired'::text as group_kind,
                    'unpaired'::text as zone,
                    array[source.row_id]::text[] as member_ids,
                    array[source.row_type]::text[] as member_types,
                    source.scope_month,
                    source.updated_at,
                    source.external_etc_batch_id,
                    array[]::text[] as missing_row_types,
                    array[source.selected_position]::bigint[] as selected_positions,
                    array[source.row_type]::text[] as selected_row_types,
                    array[source.row_id]::text[] as selected_row_ids,
                    array[source.source_kind]::text[] as selected_source_kinds
                from selected_sources source
                where not exists (
                    select 1 from matched_selection match
                    where match.selected_position = source.selected_position
                )
                  and not exists (
                      select 1
                      from app.workbench_row_overrides override
                      where override.status = 'active'
                        and override.row_type = source.row_type
                        and override.row_id = source.row_id
                        and coalesce(
                            (override.override_payload->>'ignored')::boolean,
                            override.override_payload->>'status' = 'ignored',
                            false
                        )
                  )
            )
            select * from relation_descriptors
            union all
            select * from singleton_descriptors
            order by internal_key
            """,
            (
                positions,
                row_types,
                row_ids,
                source_kinds,
                external_batch_ids,
                scope_months,
                updated_ats,
                row_ids,
                self._tenant_id,
            ),
        )

    @classmethod
    def _validated_matches(
        cls,
        *,
        identities: list[tuple[str, str]],
        descriptors: list[dict[str, Any]],
    ) -> list[tuple[str, str]]:
        matches_by_position: dict[int, list[tuple[str, str]]] = {
            position: [] for position in range(1, len(identities) + 1)
        }
        for descriptor in descriptors:
            positions = cls._integer_list(descriptor.get("selected_positions"))
            row_types = text_list(descriptor.get("selected_row_types"))
            row_ids = text_list(descriptor.get("selected_row_ids"))
            for position, row_type, row_id in zip(
                positions,
                row_types,
                row_ids,
                strict=False,
            ):
                matches_by_position.setdefault(position, []).append((row_type, row_id))
        missing_positions = [
            position for position, matches in matches_by_position.items() if not matches
        ]
        if missing_positions:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )
        ambiguous_positions = [
            position
            for position, matches in matches_by_position.items()
            if len(matches) != 1 or len(set(matches)) != 1
        ]
        if ambiguous_positions:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_ambiguous",
                message="所选关联台记录内容不一致，请刷新后重试。",
            )
        resolved = [matches_by_position[position][0] for position in matches_by_position]
        for requested, actual in zip(identities, resolved, strict=True):
            requested_type, requested_id = requested
            if requested_id != actual[1] or (requested_type and requested_type != actual[0]):
                raise WorkbenchRelationPreviewSelectionError(
                    code="relation_preview_rows_ambiguous",
                    message="所选关联台记录内容不一致，请刷新后重试。",
                )
        return resolved

    def _canonical_rows_by_ids(
        self,
        *,
        row_ids: list[str],
        row_types: list[str] | None,
    ) -> dict[str, dict[str, Any]]:
        source_rows = self._resolve_source_descriptors(
            row_ids=row_ids,
            row_types=row_types,
            scope_key="all",
        )
        identities = [
            (str(row.get("row_type") or ""), str(row.get("row_id") or ""))
            for row in source_rows
        ]
        typed_row_ids = {
            row_type: {
                row_id for resolved_type, row_id in identities if resolved_type == row_type
            }
            for row_type in ROW_TYPES
        }
        rows = PostgresWorkbenchPageHydrationRepository(
            self._connection,
            tenant_id=self._tenant_id,
        ).hydrate_rows(
            typed_row_ids,
            etc_summary_external_ids={
                str(row.get("row_id") or ""): str(
                    row.get("external_etc_batch_id") or ""
                )
                for row in source_rows
                if str(row.get("external_etc_batch_id") or "")
            },
        )
        result: dict[str, dict[str, Any]] = {}
        for identity in identities:
            row_type, row_id = identity
            if row_id in result:
                raise ValueError(f"Canonical Workbench row id is ambiguous: {row_id}.")
            result[row_id] = rows[(row_type, row_id)]
        return result

    def _resolve_source_identities(
        self,
        *,
        row_ids: list[str],
        row_types: list[str] | None,
    ) -> list[tuple[str, str]]:
        rows = self._resolve_source_descriptors(
            row_ids=row_ids,
            row_types=row_types,
            scope_key="all",
        )
        return [
            (str(row.get("row_type") or ""), str(row.get("row_id") or ""))
            for row in rows
        ]

    def _resolve_source_descriptors(
        self,
        *,
        row_ids: list[str],
        row_types: list[str] | None,
        scope_key: str,
        require_exact: bool = True,
    ) -> list[dict[str, Any]]:
        requested = self._selection_identities(row_ids=row_ids, row_types=row_types)
        requested_types = [row_type for row_type, _row_id in requested]
        requested_ids = [row_id for _row_type, row_id in requested]
        normalized_scope = self._scope_key(scope_key)
        scope_month = None if normalized_scope == "all" else month_start(normalized_scope)
        rows = self._connection.fetch_all(
            f"""
            with requested as (
                select position::bigint as position,
                       nullif(row_type, '') as row_type,
                       row_id
                from unnest(%s::text[], %s::text[]) with ordinality
                    as value(row_type, row_id, position)
            ),
            etc_summary_source_keys as materialized (
                select coalesce(
                           nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                           batch.business_batch_id
                       ) as external_batch_id,
                       batch.scope_month,
                       batch.updated_at
                from app.etc_business_batches batch
                where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                  and exists (
                      select 1 from requested
                      where (row_type is null or row_type = 'invoice')
                        and row_id like 'etc-summary-%%'
                  )
                  and exists (
                      select 1 from app.etc_invoices invoice
                      where invoice.business_batch_id = batch.business_batch_id
                        and invoice.status <> 'deleted'
                  )
                union all
                select coalesce(
                           nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                           nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                           link.business_batch_id
                       ),
                       coalesce(batch.scope_month, invoice.invoice_month),
                       greatest(link.updated_at, batch.updated_at, invoice.updated_at)
                from app.etc_batch_invoice_links link
                join app.invoices invoice on invoice.id = link.invoice_id
                left join app.etc_business_batches batch
                  on batch.business_batch_id = link.business_batch_id
                where link.link_status = 'active'
                  and invoice.status <> 'deleted'
                  and exists (
                      select 1 from requested
                      where (row_type is null or row_type = 'invoice')
                        and row_id like 'etc-summary-%%'
                  )
                union all
                select coalesce(
                           nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                           submission.submission_batch_id
                       ),
                       coalesce(submission.scope_month, invoice.invoice_month),
                       greatest(submission.updated_at, invoice.updated_at)
                from app.etc_submission_batches submission
                join app.invoices invoice
                  on submission.submission_batch_id = coalesce(
                      invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id', ''
                  )
                  or coalesce(
                      nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                      submission.submission_batch_id
                  ) = coalesce(
                      invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id', ''
                  )
                where submission.status in ('submitted_confirmed', 'submitted', 'closed')
                  and invoice.status <> 'deleted'
                  and exists (
                      select 1 from requested
                      where (row_type is null or row_type = 'invoice')
                        and row_id like 'etc-summary-%%'
                  )
            ),
            etc_summary_keys as materialized (
                select distinct on (source.external_batch_id)
                       'etc-summary-' || regexp_replace(
                           source.external_batch_id, '[^A-Za-z0-9_-]+', '-', 'g'
                       ) as row_id,
                       source.external_batch_id,
                       source.scope_month,
                       source.updated_at
                from etc_summary_source_keys source
                where nullif(source.external_batch_id, '') is not null
                  and source.scope_month is not null
                order by source.external_batch_id, source.updated_at desc nulls last
            ),
            requested_invoice_hard_identities as materialized (
                select distinct
                    case
                        when nullif(invoice.digital_invoice_no, '') is not null
                            then 'digital:' || invoice.digital_invoice_no
                        when nullif(invoice.invoice_code, '') is not null
                         and nullif(invoice.invoice_no, '') is not null
                            then 'code-no:' || invoice.invoice_code || ':' ||
                                 invoice.invoice_no
                        else 'row:' || coalesce(
                            invoice.legacy_mongo_id, invoice.id::text
                        )
                    end as hard_identity
                from requested
                join app.invoices invoice
                  on coalesce(invoice.legacy_mongo_id, invoice.id::text)
                     = requested.row_id
                where (requested.row_type is null or requested.row_type = 'invoice')
                  and {_VISIBLE_INVOICE_SQL}
            ),
            invoice_identity_candidates as materialized (
                select
                    coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
                    case when exists (
                        select 1
                        from jsonb_array_elements(
                            case when jsonb_typeof(invoice.source_links) = 'array'
                                 then invoice.source_links else '[]'::jsonb end
                        ) source_link
                        where coalesce(
                            source_link->>'source_type',
                            source_link->>'type',
                            source_link->>'source'
                        ) = 'oa_attachment_invoice'
                    ) then 'oa_attachment_invoice'
                    when exists (
                        select 1
                        from jsonb_array_elements(
                            case
                                when jsonb_typeof(invoice.source_links) = 'array'
                                    then invoice.source_links
                                when jsonb_typeof(invoice.raw_payload->'source_links')
                                     = 'array'
                                    then invoice.raw_payload->'source_links'
                                else '[]'::jsonb
                            end
                        ) source_link
                        where coalesce(
                            source_link->>'source_type',
                            source_link->>'type',
                            source_link->>'source'
                        ) = 'manual_invoice_import'
                    ) then 'manual_invoice_import'
                    else 'invoice' end as source_kind,
                    invoice.invoice_month as scope_month,
                    invoice.updated_at,
                    requested_identity.hard_identity,
                    exists (
                        select 1
                        from app.workbench_pair_relations owner_relation
                        where owner_relation.status = 'active'
                          and cardinality(owner_relation.row_ids)
                              = cardinality(owner_relation.row_types)
                          and exists (
                              select 1
                              from unnest(
                                  owner_relation.row_ids,
                                  owner_relation.row_types
                              ) owner_member(row_id, row_type)
                              where owner_member.row_id = coalesce(
                                        invoice.legacy_mongo_id,
                                        invoice.id::text
                                    )
                                and {self._normalized_member_type_sql('owner_member.row_type')}
                                    = 'invoice'
                          )
                    ) as active_relation_member
                from app.invoices invoice
                join requested_invoice_hard_identities requested_identity
                  on requested_identity.hard_identity = case
                        when nullif(invoice.digital_invoice_no, '') is not null
                            then 'digital:' || invoice.digital_invoice_no
                        when nullif(invoice.invoice_code, '') is not null
                         and nullif(invoice.invoice_no, '') is not null
                            then 'code-no:' || invoice.invoice_code || ':' ||
                                 invoice.invoice_no
                        else 'row:' || coalesce(
                            invoice.legacy_mongo_id, invoice.id::text
                        )
                     end
                where {_VISIBLE_INVOICE_SQL}
            ),
            ranked_invoice_candidates as materialized (
                select candidate.*,
                       row_number() over (
                           partition by candidate.hard_identity
                           order by candidate.active_relation_member desc,
                                    case when candidate.source_kind = 'invoice'
                                         then 0 else 1 end,
                                    candidate.row_id
                       ) as identity_rank
                from invoice_identity_candidates candidate
            ),
            invoice_relation_identity_conflicts as materialized (
                select candidate.hard_identity
                from invoice_identity_candidates candidate
                group by candidate.hard_identity
                having count(*) filter (where candidate.active_relation_member) > 1
            ),
            invoice_identity_guard as materialized (
                select 1 / case when count(*) = 0 then 1 else 0 end as guard
                from invoice_relation_identity_conflicts
            ),
            source_candidates as (
                select requested.position, 'oa'::text as row_type, oa.row_id,
                       'oa'::text as source_kind, null::text as external_etc_batch_id,
                       coalesce(
                           oa.scope_month,
                           date_trunc('month', oa.application_date)::date
                       ) as scope_month,
                       oa.updated_at
                from requested
                join app.oa_applications oa on oa.row_id = requested.row_id
                where (requested.row_type is null or requested.row_type = 'oa')
                  and oa.status <> 'deleted'
                  and {_COMPLETED_OA_SQL}
                  and (%s::text = 'all' or coalesce(
                      oa.scope_month, date_trunc('month', oa.application_date)::date
                  ) = %s::date)
                union all
                select requested.position, 'oa'::text, admission.oa_id,
                       'oa'::text, null::text,
                       (admission.scope_key || '-01')::date,
                       admission.updated_at
                from requested
                join app.oa_pending_payment_admissions admission
                  on admission.oa_id = requested.row_id
                where (requested.row_type is null or requested.row_type = 'oa')
                  and admission.tenant_id = %s
                  and admission.workflow_status = 'in_progress'
                  and (%s::text = 'all' or admission.scope_key = %s::text)
                union all
                select requested.position, 'bank'::text,
                       coalesce(bank.legacy_mongo_id, bank.id::text),
                       'bank_transaction'::text, null::text,
                       bank.txn_month, bank.updated_at
                from requested
                join app.bank_transactions bank
                  on coalesce(bank.legacy_mongo_id, bank.id::text) = requested.row_id
                where (requested.row_type is null or requested.row_type = 'bank')
                  and bank.status <> 'deleted'
                  and (%s::text = 'all' or bank.txn_month = %s::date)
                union all
                select requested.position, 'invoice'::text,
                       invoice.row_id, invoice.source_kind, null::text,
                       invoice.scope_month, invoice.updated_at
                from requested
                join ranked_invoice_candidates invoice
                  on invoice.row_id = requested.row_id
                cross join invoice_identity_guard guard
                where (requested.row_type is null or requested.row_type = 'invoice')
                  and invoice.identity_rank = 1
                  and guard.guard = 1
                  and (%s::text = 'all' or invoice.scope_month = %s::date)
                union all
                select requested.position, 'invoice'::text, summary.row_id,
                       'etc_invoice_summary'::text, summary.external_batch_id,
                       summary.scope_month, summary.updated_at
                from requested
                join etc_summary_keys summary on summary.row_id = requested.row_id
                where (requested.row_type is null or requested.row_type = 'invoice')
                  and (%s::text = 'all' or summary.scope_month = %s::date)
            )
            select position, row_type, row_id, source_kind,
                   external_etc_batch_id, scope_month, updated_at
            from source_candidates
            order by position, row_type
            """,
            (
                requested_types,
                requested_ids,
                normalized_scope,
                scope_month,
                self._tenant_id,
                normalized_scope,
                normalized_scope,
                normalized_scope,
                scope_month,
                normalized_scope,
                scope_month,
                normalized_scope,
                scope_month,
            ),
        )
        if not require_exact:
            return rows
        counts = Counter(int(row.get("position") or 0) for row in rows)
        if any(counts.get(position, 0) == 0 for position in range(1, len(requested) + 1)):
            raise ValueError("Canonical Workbench row selection is missing.")
        if any(counts.get(position, 0) > 1 for position in range(1, len(requested) + 1)):
            raise ValueError("Canonical Workbench row selection is ambiguous.")
        return rows

    def _ignored_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        normalized_scope = self._scope_key(scope_key)
        scope_sql = ""
        params: list[Any] = []
        if normalized_scope != "all":
            scope_sql = "and override.scope_month = %s::date"
            params.append(month_start(normalized_scope))
        rows = self._connection.fetch_all(
            f"""
            select override.row_type, override.row_id,
                   override.override_payload, override.raw_payload
            from app.workbench_row_overrides override
            where override.status = 'active'
              {scope_sql}
              and coalesce(
                  (override.override_payload->>'ignored')::boolean,
                  override.override_payload->>'status' = 'ignored',
                  false
              )
            order by override.updated_at desc, override.row_type, override.row_id
            """,
            tuple(params),
        )
        typed_sources = [
            (row, (row_type, row_id))
            for row in rows
            if (row_type := self._row_type(row.get("row_type")))
            if (row_id := str(row.get("row_id") or "").strip())
        ]
        identities = [identity for _row, identity in typed_sources]
        hydrated = PostgresWorkbenchPageHydrationRepository(
            self._connection,
            tenant_id=self._tenant_id,
        ).hydrate_rows(
            {
                row_type: {
                    row_id
                    for candidate_type, row_id in identities
                    if candidate_type == row_type
                }
                for row_type in ROW_TYPES
            },
            require_exact=False,
        )
        result: list[dict[str, Any]] = []
        for source, identity in typed_sources:
            row = hydrated.get(identity)
            if not isinstance(row, dict):
                continue
            override = row_payload(source, "override_payload", "raw_payload")
            service = WorkbenchOverrideService.from_snapshot(
                {
                    "row_overrides": {
                        workbench_row_identity_key(*identity): {
                            **(override if isinstance(override, dict) else {}),
                            "row_id": identity[1],
                            "row_type": identity[0],
                        }
                    }
                }
            )
            result.append(service.apply_to_row(row))
        return result

    @classmethod
    def _selection_identities(
        cls,
        *,
        row_ids: list[str],
        row_types: list[str] | None,
    ) -> list[tuple[str, str]]:
        raw_ids = [str(value or "").strip() for value in list(row_ids or [])]
        if row_types is not None and len(row_types) != len(raw_ids):
            raise ValueError("row_types must align with row_ids.")
        raw_types = (
            [cls._row_type(value) for value in row_types]
            if row_types is not None
            else [""] * len(raw_ids)
        )
        if row_types is not None and any(not row_type for row_type in raw_types):
            raise ValueError("row_types must contain only oa, bank or invoice.")
        identities: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for row_type, row_id in zip(raw_types, raw_ids, strict=True):
            if not row_id:
                raise ValueError("row_ids must contain non-empty identifiers.")
            identity = (row_type, row_id)
            if identity in seen:
                raise ValueError("canonical Workbench selection contains a duplicate typed row.")
            seen.add(identity)
            identities.append(identity)
        if not identities:
            raise ValueError("at least one canonical Workbench row is required.")
        return identities

    @staticmethod
    def _row_type(value: object) -> str:
        normalized = str(value or "").strip().lower()
        normalized = {
            "oa_application": "oa",
            "bank_transaction": "bank",
            "invoice_record": "invoice",
        }.get(normalized, normalized)
        return normalized if normalized in ROW_TYPES else ""

    @staticmethod
    def _integer_list(value: object) -> list[int]:
        return [int(item) for item in list(value or [])]

    @staticmethod
    def _normalized_member_type_sql(expression: str) -> str:
        return f"""
            case lower(nullif(btrim({expression}), ''))
                when 'oa' then 'oa'
                when 'oa_application' then 'oa'
                when 'bank' then 'bank'
                when 'bank_transaction' then 'bank'
                when 'invoice' then 'invoice'
                when 'invoice_record' then 'invoice'
                when 'formal_invoice' then 'invoice'
                when 'input' then 'invoice'
                when 'input_invoice' then 'invoice'
                when 'output' then 'invoice'
                when 'output_invoice' then 'invoice'
                when 'etc_summary' then 'invoice'
                when 'etc_invoice_summary' then 'invoice'
                else null
            end
        """

    @classmethod
    def _dedupe_rows(cls, rows: Any) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for row in rows:
            if not isinstance(row, dict):
                continue
            identity = (
                cls._row_type(row.get("type")),
                str(row.get("id") or "").strip(),
            )
            if not all(identity) or identity in seen:
                continue
            seen.add(identity)
            result.append(row)
        return result

    @staticmethod
    def _scope_key(scope_key: str | None) -> str:
        return normalize_workbench_scope_key(scope_key)

    def _scope_params(self, scope_key: str) -> list[Any]:
        normalized = self._scope_key(scope_key)
        return [
            normalized,
            normalized,
            None if normalized == "all" else month_start(normalized),
            self._tenant_id,
        ]


__all__ = ["PostgresWorkbenchPageSelectionRepository"]
