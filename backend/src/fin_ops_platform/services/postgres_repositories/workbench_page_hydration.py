from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_details_canonical_query import (
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.bank_settings import bank_accounts_from_settings_payload
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    OA_EXTERNAL_SOURCE_ID_FIELD_NAMES,
    normalize_oa_attachment_expense_item_ids,
)
from fin_ops_platform.services.postgres_repositories.common import (
    row_payload,
    serialize_value,
    text_list,
    without_keys,
)
from fin_ops_platform.services.postgres_repositories.oa_source_alias_sql import (
    oa_source_aliases_sql,
)
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
    invoice_source_kinds,
)

# One relation lookup, one batch read per present canonical pane, one settings
# lookup, one set-based ETC summary read, overrides, and anomaly decisions.  The
# budget is independent of page/member count; a higher count is a regression.
WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET = 8
WORKBENCH_SUMMARY_HYDRATION_STATEMENT_BUDGET = 2


def pending_oa_application_time_sql(alias: str) -> str:
    """Return the canonical pending-OA application time SQL expression."""

    return f"""coalesce(
        nullif(btrim({alias}.source_payload#>>'{{detail_fields,申请时间}}'), ''),
        nullif(btrim({alias}.source_payload#>>'{{detail_fields,申请日期}}'), ''),
        nullif(btrim({alias}.source_payload->>'application_time'), ''),
        nullif(btrim({alias}.source_payload->>'application_date'), '')
    )"""


def pending_oa_application_date_sql(alias: str) -> str:
    application_time = pending_oa_application_time_sql(alias)
    return f"""case
        when ({application_time}) ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
        then substring(({application_time}) from 1 for 10)::date
        else null::date
    end"""


def oa_source_identity_aliases_sql(source_payload: str) -> str:
    """Return the compact external OA identity aliases used during hydration."""

    source_identity_values = ",\n                ".join(
        f"({source_payload}{path}->>'{field_name}')"
        for path in ("", "->'detail_fields'", "->'summary_fields'", "->'metadata'")
        for field_name in OA_EXTERNAL_SOURCE_ID_FIELD_NAMES
    )
    return f"""coalesce((
        select jsonb_agg(identity.value order by identity.value)
        from (values
            {source_identity_values}
        ) identity(value)
        where nullif(btrim(identity.value), '') is not null
    ), '[]'::jsonb)"""


def oa_expense_items_with_supporting_documents_sql(
    oa_row_id_sql: str,
    expense_items_sql: str,
) -> str:
    """Attach active supplemental evidence to each OA expense item in one SQL read."""

    return f"""
        coalesce((
            select jsonb_agg(
                item.value || jsonb_build_object(
                    'supporting_documents', coalesce((
                        select jsonb_agg(jsonb_build_object(
                            'id', document.id::text,
                            'file_name', document.original_filename,
                            'content_type', document.content_type,
                            'size_bytes', document.size_bytes,
                            'created_at', document.created_at::text,
                            'content_url', '/api/workbench/oa-invoice-supplements/documents/' || document.id::text || '/content'
                        ) order by document.created_at, document.id)
                        from app.workbench_oa_supporting_documents document
                        where document.oa_row_id = {oa_row_id_sql}
                          and document.expense_item_id = coalesce(
                              item.value->>'id', item.value->>'expense_item_id'
                          )
                          and document.status = 'active'
                    ), '[]'::jsonb)
                )
                order by item.ordinality
            )
            from jsonb_array_elements(
                case when jsonb_typeof({expense_items_sql}) = 'array'
                     then {expense_items_sql}
                     else '[]'::jsonb end
            ) with ordinality item(value, ordinality)
        ), '[]'::jsonb)
    """


class _BudgetedReadConnection:
    def __init__(self, connection: Any, *, maximum_statements: int) -> None:
        self._connection = connection
        self._maximum_statements = maximum_statements
        self.statement_count = 0

    def _record(self) -> None:
        self.statement_count += 1
        if self.statement_count > self._maximum_statements:
            raise RuntimeError(
                "Workbench page hydration exceeded its fixed SQL statement budget."
            )

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        self._record()
        return self._connection.fetch_all(sql, params)

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        self._record()
        return self._connection.fetch_one(sql, params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class PostgresWorkbenchPageHydrationRepository:
    """Batch hydration boundary for already-selected Workbench page groups."""

    def __init__(self, connection: Any, *, tenant_id: str = "default") -> None:
        self._connection = connection
        self._tenant_id = str(tenant_id or "").strip()
        if not self._tenant_id:
            raise ValueError("tenant_id is required for Workbench page hydration.")

    def hydrate_rows(
        self,
        typed_row_ids: dict[str, set[str]],
        *,
        require_exact: bool = True,
        etc_summary_external_ids: dict[str, str] | None = None,
    ) -> dict[tuple[str, str], dict[str, Any]]:
        connection = _BudgetedReadConnection(
            self._connection,
            maximum_statements=WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET,
        )
        normalized_ids = {
            row_type: {
                str(row_id).strip()
                for row_id in set(typed_row_ids.get(row_type, set()))
                if str(row_id).strip()
            }
            for row_type in ("oa", "bank", "invoice")
        }
        expected_typed_ids = {
            (row_type, row_id)
            for row_type, row_ids in normalized_ids.items()
            for row_id in row_ids
        }
        if not expected_typed_ids:
            return {}
        settings = (
            self._settings_payload(connection) if normalized_ids["bank"] else {}
        )
        builder = WorkbenchCanonicalRowsBuilder(
            connection=connection,
            bank_account_resolver=self._bank_account_resolver(settings),
        )
        rows_by_typed_id = builder.load_page_rows(
            normalized_ids,
            etc_summary_external_ids=etc_summary_external_ids,
        )
        self._enrich_bank_category_projection(
            rows_by_typed_id,
            connection=connection,
            settings=settings,
        )
        if require_exact and set(rows_by_typed_id) != expected_typed_ids:
            missing = sorted(expected_typed_ids - set(rows_by_typed_id))
            raise ValueError(
                "Canonical Workbench rows changed during hydration: "
                + ",".join(f"{row_type}:{row_id}" for row_type, row_id in missing)
            )
        return rows_by_typed_id

    def hydrate_groups(
        self,
        *,
        scope_key: str,
        descriptors: list[dict[str, Any]],
        detail_level: str,
    ) -> list[dict[str, Any]]:
        if not descriptors:
            return []
        if detail_level == "summary":
            return self._hydrate_summary_groups(
                scope_key=scope_key,
                descriptors=descriptors,
            )
        connection = _BudgetedReadConnection(
            self._connection,
            maximum_statements=WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET,
        )
        relation_case_ids = {
            str(descriptor.get("detail_key") or "")
            for descriptor in descriptors
            if str(descriptor.get("group_kind") or "") == "relation"
        }
        relations, decisions = self._load_relations(
            relation_case_ids,
            connection=connection,
        )
        typed_row_ids: dict[str, set[str]] = {
            "oa": set(),
            "bank": set(),
            "invoice": set(),
        }
        for descriptor in descriptors:
            member_ids = text_list(descriptor.get("member_ids"))
            member_types = text_list(descriptor.get("member_types"))
            if len(member_ids) != len(member_types) or not member_ids:
                raise ValueError(
                    "Canonical Workbench page descriptor has invalid typed members."
                )
            for row_id, row_type in zip(member_ids, member_types, strict=True):
                if row_type in typed_row_ids:
                    typed_row_ids[row_type].add(row_id)
                    continue
                raise ValueError(
                    f"Canonical Workbench page descriptor has unsupported row type: {row_type}."
                )

        etc_summary_external_ids: dict[str, str] = {}
        for descriptor in descriptors:
            external_batch_id = str(descriptor.get("external_etc_batch_id") or "").strip()
            if not external_batch_id:
                continue
            for row_id, row_type in zip(
                text_list(descriptor.get("member_ids")),
                text_list(descriptor.get("member_types")),
                strict=True,
            ):
                if row_type != "invoice" or not row_id.startswith("etc-summary-"):
                    continue
                previous = etc_summary_external_ids.setdefault(row_id, external_batch_id)
                if previous != external_batch_id:
                    raise ValueError("ETC summary row identity maps to multiple external batches.")

        settings = (
            self._settings_payload(connection) if typed_row_ids["bank"] else {}
        )
        builder = WorkbenchCanonicalRowsBuilder(
            connection=connection,
            bank_account_resolver=self._bank_account_resolver(settings),
        )
        page_etc_summaries = builder.load_page_etc_summaries(
            relations,
            required_external_batch_ids=set(etc_summary_external_ids.values()),
        )
        rows_by_typed_id = builder.load_page_rows(
            typed_row_ids,
            etc_summary_external_ids=etc_summary_external_ids,
            page_etc_summaries=page_etc_summaries,
        )
        self._enrich_bank_category_projection(
            rows_by_typed_id,
            connection=connection,
            settings=settings,
        )
        expected_typed_ids = {
            (row_type, row_id)
            for row_type, row_ids in typed_row_ids.items()
            for row_id in row_ids
        }
        if set(rows_by_typed_id) != expected_typed_ids:
            missing = sorted(expected_typed_ids - set(rows_by_typed_id))
            raise ValueError(
                "Canonical Workbench page members changed during hydration: "
                + ",".join(f"{row_type}:{row_id}" for row_type, row_id in missing)
            )
        normalize_oa_attachment_expense_item_ids(list(rows_by_typed_id.values()))
        grouped = builder.build_page_groups(
            scope_key=scope_key,
            rows_by_typed_id=rows_by_typed_id,
            relations=relations,
            anomaly_review_decisions=decisions,
            page_etc_summaries=page_etc_summaries,
        )
        grouped_groups = [
            group
            for zone in ("paired", "unpaired")
            for group in list((grouped.get(zone) or {}).get("groups") or [])
            if isinstance(group, dict)
        ]
        groups_by_id = {
            str(group.get("group_id") or ""): group for group in grouped_groups
        }
        groups_by_member = {
            (str(row.get("type") or ""), str(row.get("id") or "")): group
            for group in grouped_groups
            for row in self.group_rows(group)
            if str(row.get("type") or "") and str(row.get("id") or "")
        }
        result: list[dict[str, Any]] = []
        for descriptor in descriptors:
            if str(descriptor.get("group_kind") or "") == "relation":
                group = groups_by_id.get(f"case:{descriptor.get('detail_key') or ''}")
            else:
                member_ids = text_list(descriptor.get("member_ids"))
                member_types = text_list(descriptor.get("member_types"))
                group = (
                    groups_by_member.get((member_types[0], member_ids[0]))
                    if member_ids and member_types
                    else None
                )
            if not isinstance(group, dict):
                raise RuntimeError(
                    "Workbench page hydration could not assemble a selected group."
                )
            actual_zone = str(group.get("zone") or "")
            descriptor_zone = str(descriptor.get("zone") or "")
            if descriptor_zone and actual_zone != descriptor_zone:
                raise RuntimeError(
                    "Workbench direct candidate zone disagrees with canonical completion policy."
                )
            payload = self._with_group_counts(group)
            payload["detail_key"] = str(descriptor.get("detail_key") or "")
            if detail_level == "summary":
                payload = self._compact_group(payload)
            result.append(payload)
        return result

    def _hydrate_summary_groups(
        self,
        *,
        scope_key: str,
        descriptors: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Hydrate one page into compact DTOs with bounded set queries.

        This path deliberately does not select source ``raw_payload`` or full
        ``detail_fields``/``source_links``.  The source facts, active relation
        decorations, row overrides, page-local amount-mismatch decisions, and
        ETC aggregates are returned by one statement whose cardinality is
        bounded by the already-selected page descriptors. A second statement
        classifies only bank transaction IDs present on that page.
        """

        member_types: list[str] = []
        member_ids: list[str] = []
        relation_case_ids: list[str] = []
        external_batch_ids: set[str] = set()
        etc_row_ids_by_external_batch_id: dict[str, str] = {}
        for descriptor in descriptors:
            descriptor_ids = text_list(descriptor.get("member_ids"))
            descriptor_types = text_list(descriptor.get("member_types"))
            if len(descriptor_ids) != len(descriptor_types) or not descriptor_ids:
                raise ValueError(
                    "Canonical Workbench page descriptor has invalid typed members."
                )
            for row_id, row_type in zip(
                descriptor_ids,
                descriptor_types,
                strict=True,
            ):
                normalized_type = self._normalize_row_type(row_type)
                if normalized_type not in {"oa", "bank", "invoice"}:
                    raise ValueError(
                        "Canonical Workbench page descriptor has unsupported row type: "
                        f"{row_type}."
                    )
                member_types.append(normalized_type)
                member_ids.append(row_id)
            if str(descriptor.get("group_kind") or "") == "relation":
                relation_case_ids.append(str(descriptor.get("detail_key") or ""))
            external_batch_id = str(
                descriptor.get("external_etc_batch_id") or ""
            ).strip()
            if external_batch_id:
                external_batch_ids.add(external_batch_id)
                for row_id, row_type in zip(
                    descriptor_ids,
                    descriptor_types,
                    strict=True,
                ):
                    if (
                        self._normalize_row_type(row_type) == "invoice"
                        and row_id.startswith("etc-summary-")
                    ):
                        previous = etc_row_ids_by_external_batch_id.setdefault(
                            external_batch_id,
                            row_id,
                        )
                        if previous != row_id:
                            raise ValueError(
                                "ETC summary external identity maps to multiple page rows."
                            )

        connection = _BudgetedReadConnection(
            self._connection,
            maximum_statements=WORKBENCH_SUMMARY_HYDRATION_STATEMENT_BUDGET,
        )
        rows = connection.fetch_all(
            """
            with requested_members(row_type, row_id) as materialized (
                select distinct requested.row_type, requested.row_id
                from unnest(%s::text[], %s::text[])
                    as requested(row_type, row_id)
            ),
            requested_relations(case_id) as materialized (
                select distinct btrim(requested.case_id)
                from unnest(%s::text[]) requested(case_id)
                where nullif(btrim(requested.case_id), '') is not null
            ),
            requested_etc(external_batch_id) as materialized (
                select distinct btrim(requested.external_batch_id)
                from unnest(%s::text[]) requested(external_batch_id)
                where nullif(btrim(requested.external_batch_id), '') is not null
            ),
            completed_oa_rows as materialized (
                select
                    'row'::text as record_kind,
                    'oa'::text as row_type,
                    oa.row_id,
                    null::text as case_id,
                    null::text as external_batch_id,
                    jsonb_strip_nulls(jsonb_build_object(
                        'id', oa.row_id,
                        'type', 'oa',
                        'source_kind', 'oa',
                        'status', 'unpaired',
                        'workflow_status', coalesce(nullif(oa.workflow_status, ''), 'completed'),
                        'applicant', oa.applicant,
                        'apply_time', coalesce(
                            oa.normalized_payload->>'apply_time',
                            oa.normalized_payload->>'application_time',
                            oa.normalized_payload#>>'{detail_fields,申请时间}',
                            oa.application_date::text
                        ),
                        'application_date', oa.application_date::text,
                        'completed_at', coalesce(
                            oa.normalized_payload->>'completed_at',
                            oa.normalized_payload#>>'{detail_fields,审批完成时间}',
                            oa.approved_at::text
                        ),
                        'date', oa.application_date::text,
                        'project_name', coalesce(
                            nullif(oa.normalized_payload->>'project_name_display', ''),
                            oa.project_name
                        ),
                        'apply_type', coalesce(
                            oa.normalized_payload->>'apply_type',
                            oa.normalized_payload#>>'{detail_fields,申请类型}'
                        ),
                        'expense_type', nullif(
                            btrim(oa.normalized_payload->>'expense_type'),
                            ''
                        ),
                        'counterparty_name', coalesce(
                            oa.normalized_payload->>'counterparty_name',
                            oa.normalized_payload#>>'{detail_fields,往来单位}'
                        ),
                        'amount', oa.amount::text,
                        'reconciliation_amount', oa.normalized_payload->>'reconciliation_amount',
                        'amount_source', oa.normalized_payload->>'amount_source',
                        'amount_mismatch', oa.normalized_payload->'amount_mismatch',
                        'reason', oa.normalized_payload->>'reason',
                        'expense_items', coalesce((
                            select jsonb_agg(
                                jsonb_strip_nulls(jsonb_build_object(
                                    'id', coalesce(item.value->>'id', item.value->>'expense_item_id'),
                                    'expense_item_id', item.value->>'expense_item_id',
                                    'row_index', item.value->>'row_index',
                                    'project_name', item.value->>'project_name',
                                    'expense_type', item.value->>'expense_type',
                                    'amount', coalesce(
                                        item.value->>'amount',
                                        item.value->>'settlement_amount',
                                        item.value->>'total_with_tax'
                                    ),
                                    'fee_content', item.value->>'fee_content',
                                    'fee_description', item.value->>'fee_description',
                                    'attachment_file_count', item.value->>'attachment_file_count'
                                )) order by item.ordinality
                            )
                            from jsonb_array_elements(
                                case when jsonb_typeof(oa.normalized_payload->'expense_items') = 'array'
                                     then oa.normalized_payload->'expense_items'
                                     else '[]'::jsonb end
                            ) with ordinality as item(value, ordinality)
                        ), '[]'::jsonb),
                        'source_aliases', to_jsonb(__COMPLETED_OA_SOURCE_ALIASES_SQL__),
                        'source_identity_aliases', __COMPLETED_OA_SOURCE_IDENTITY_ALIASES_SQL__,
                        'oa_row_id', oa.normalized_payload->>'oa_row_id',
                        'oa_id', oa.normalized_payload->>'oa_id',
                        'source_oa_row_id', oa.normalized_payload->>'source_oa_row_id',
                        'object_identity_key', oa.normalized_payload->>'object_identity_key',
                        'available_actions', jsonb_build_array('detail')
                    )) as payload
                from app.oa_applications oa
                join requested_members requested
                  on requested.row_type = 'oa' and requested.row_id = oa.row_id
                where oa.status <> 'deleted'
                  and (
                      oa.workflow_status is null
                      or oa.workflow_status = ''
                      or oa.workflow_status in (
                          'completed', '已完成', 'approved', 'APPROVED', 'Approved', '2'
                      )
                  )
            ),
            pending_oa_rows(
                record_kind, row_type, row_id, case_id, external_batch_id, payload
            ) as materialized (
                select
                    'row'::text,
                    'oa'::text,
                    admission.oa_id,
                    null::text,
                    null::text,
                    jsonb_strip_nulls(jsonb_build_object(
                        'id', admission.oa_id,
                        'type', 'oa',
                        'source_kind', 'oa',
                        'status', 'unpaired',
                        'workflow_status', 'in_progress',
                        'applicant', coalesce(
                            admission.source_payload->>'applicant',
                            admission.applicant
                        ),
                        'apply_time', __PENDING_OA_APPLICATION_TIME_SQL__,
                        'application_date', __PENDING_OA_APPLICATION_DATE_SQL__::text,
                        'date', __PENDING_OA_APPLICATION_DATE_SQL__::text,
                        'project_name', coalesce(
                            admission.project_name_display,
                            admission.project_name
                        ),
                        'apply_type', coalesce(
                            admission.source_payload->>'apply_type',
                            admission.source_payload->>'application_type',
                            admission.source_payload->>'form_type'
                        ),
                        'expense_type', nullif(
                            btrim(admission.source_payload->>'expense_type'),
                            ''
                        ),
                        'counterparty_name', admission.source_payload->>'counterparty_name',
                        'amount', admission.amount::text,
                        'reconciliation_amount', admission.source_payload->>'reconciliation_amount',
                        'reason', admission.source_payload->>'reason',
                        'expense_items', coalesce((
                            select jsonb_agg(
                                jsonb_strip_nulls(jsonb_build_object(
                                    'id', coalesce(item.value->>'id', item.value->>'expense_item_id'),
                                    'expense_item_id', item.value->>'expense_item_id',
                                    'row_index', item.value->>'row_index',
                                    'project_name', item.value->>'project_name',
                                    'expense_type', item.value->>'expense_type',
                                    'amount', coalesce(
                                        item.value->>'amount',
                                        item.value->>'settlement_amount',
                                        item.value->>'total_with_tax'
                                    ),
                                    'fee_content', item.value->>'fee_content',
                                    'fee_description', item.value->>'fee_description',
                                    'attachment_file_count', item.value->>'attachment_file_count'
                                )) order by item.ordinality
                            )
                            from jsonb_array_elements(
                                case when jsonb_typeof(admission.source_payload->'expense_items') = 'array'
                                     then admission.source_payload->'expense_items'
                                     else '[]'::jsonb end
                            ) with ordinality as item(value, ordinality)
                        ), '[]'::jsonb),
                        'source_aliases', admission.source_payload->'source_aliases',
                        'source_identity_aliases', __PENDING_OA_SOURCE_IDENTITY_ALIASES_SQL__,
                        'oa_row_id', admission.source_payload->>'oa_row_id',
                        'oa_id', admission.source_payload->>'oa_id',
                        'source_oa_row_id', admission.source_payload->>'source_oa_row_id',
                        'object_identity_key', admission.source_payload->>'object_identity_key',
                        'available_actions', jsonb_build_array('detail')
                    ))
                from app.oa_pending_payment_admissions admission
                join requested_members requested
                  on requested.row_type = 'oa' and requested.row_id = admission.oa_id
                where admission.tenant_id = %s
                  and admission.workflow_status = 'in_progress'
            ),
            oa_identity_guard as materialized (
                select 1 / case when count(*) = 0 then 1 else 0 end as guard
                from (
                    select oa_rows.row_id
                    from (
                        select row_id from completed_oa_rows
                        union all
                        select row_id from pending_oa_rows
                    ) oa_rows
                    group by oa_rows.row_id
                    having count(*) > 1
                ) duplicate_oa_rows
            ),
            selected_settings as materialized (
                select coalesce(settings.settings_payload, '{}'::jsonb) as payload
                from (select 1) singleton
                left join app.app_settings settings on settings.settings_key = 'app_settings'
            ),
            bank_settings_row as materialized (
                select
                    'settings'::text as record_kind,
                    null::text as row_type,
                    null::text as row_id,
                    null::text as case_id,
                    null::text as external_batch_id,
                    selected_settings.payload
                from selected_settings
                where exists (
                    select 1
                    from requested_members
                    where requested_members.row_type = 'bank'
                )
            ),
            bank_rows as materialized (
                select
                    'row'::text as record_kind,
                    'bank'::text as row_type,
                    coalesce(bank.legacy_mongo_id, bank.id::text) as row_id,
                    null::text as case_id,
                    null::text as external_batch_id,
                    jsonb_strip_nulls(jsonb_build_object(
                        'id', coalesce(bank.legacy_mongo_id, bank.id::text),
                        'type', 'bank',
                        'source_kind', 'bank_transaction',
                        'status', 'unpaired',
                        'trade_time', coalesce(bank.trade_time, bank.txn_date::timestamptz)::text,
                        'txn_direction', bank.txn_direction,
                        'direction', case
                            when lower(coalesce(bank.txn_direction, '')) in
                                 ('out', 'outflow', 'debit', 'expense', '支出')
                                 or coalesce(bank.signed_amount, 0) < 0
                                then '支出'
                            else '收入'
                        end,
                        'debit_amount', case
                            when lower(coalesce(bank.txn_direction, '')) in
                                 ('out', 'outflow', 'debit', 'expense', '支出')
                                 or coalesce(bank.signed_amount, 0) < 0
                                then bank.amount::text else null end,
                        'credit_amount', case
                            when lower(coalesce(bank.txn_direction, '')) in
                                 ('out', 'outflow', 'debit', 'expense', '支出')
                                 or coalesce(bank.signed_amount, 0) < 0
                                then null else bank.amount::text end,
                        'counterparty_name', bank.counterparty_name_raw,
                        'payment_account_label', concat_ws(
                            ' ',
                            coalesce(
                                account_mapping.bank_name,
                                case
                                    when bank.account_no like '6225%%' then '招商银行'
                                    when bank.account_no like '6222%%' then '工商银行'
                                    when bank.account_no like '6217%%' then '建设银行'
                                    when bank.account_no like '6228%%' then '农业银行'
                                    when bank.account_no like '6214%%' then '中国银行'
                                    else '未识别银行'
                                end
                            ),
                            case
                                when bank.account_name like '%%基本%%' then '基本户'
                                when bank.account_name like '%%一般%%' then '一般户'
                                when bank.account_name like '%%专户%%' then '专户'
                                else '账户'
                            end,
                            right(bank.account_no, 4)
                        ),
                        'pay_receive_time', coalesce(
                            bank.pay_receive_time,
                            bank.trade_time,
                            bank.txn_date::timestamptz
                        )::text,
                        'summary', bank.summary,
                        'remark', bank.remark,
                        'project_id', bank.project_id,
                        'bank_text_fields', jsonb_strip_nulls(jsonb_build_array(
                            jsonb_build_object('label', '摘要', 'value', bank.summary),
                            jsonb_build_object('label', '备注', 'value', bank.remark)
                        )),
                        'invoice_relation', jsonb_build_object(
                            'code', 'pending_invoice_match',
                            'label', '待关联发票',
                            'tone', 'warn'
                        ),
                        'available_actions', jsonb_build_array(
                            'detail', 'view_relation', 'cancel_link'
                        )
                    )) as payload
                from app.bank_transactions bank
                join requested_members requested
                  on requested.row_type = 'bank'
                 and requested.row_id = coalesce(bank.legacy_mongo_id, bank.id::text)
                cross join selected_settings settings
                left join lateral (
                    select mapping.value->>'bank_name' as bank_name
                    from jsonb_array_elements(
                        case when jsonb_typeof(settings.payload->'bank_account_mappings') = 'array'
                             then settings.payload->'bank_account_mappings'
                             else '[]'::jsonb end
                    ) mapping(value)
                    where mapping.value->>'last4' = right(bank.account_no, 4)
                    order by mapping.value->>'bank_name'
                    limit 1
                ) account_mapping on true
                where bank.status <> 'deleted'
            ),
            invoice_rows as materialized (
                select
                    'row'::text as record_kind,
                    'invoice'::text as row_type,
                    coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
                    null::text as case_id,
                    null::text as external_batch_id,
                    jsonb_strip_nulls(jsonb_build_object(
                        'id', coalesce(invoice.legacy_mongo_id, invoice.id::text),
                        'type', 'invoice',
                        'source_kind', case
                            when link_flags.has_oa_attachment then 'oa_attachment_invoice'
                            when link_flags.has_manual_import then 'manual_invoice_import'
                            else 'invoice' end,
                        'source_kinds', link_flags.source_kinds,
                        'status', 'unpaired',
                        'invoice_type', invoice.invoice_type,
                        'invoice_no', invoice.invoice_no,
                        'invoice_code', invoice.invoice_code,
                        'digital_invoice_no', invoice.digital_invoice_no,
                        'issue_date', invoice.invoice_date::text,
                        'counterparty_name', coalesce(
                            invoice.counterparty_name,
                            invoice.seller_name,
                            invoice.buyer_name
                        ),
                        'seller_name', invoice.seller_name,
                        'seller_tax_no', invoice.seller_tax_no,
                        'buyer_name', invoice.buyer_name,
                        'buyer_tax_no', invoice.buyer_tax_no,
                        'amount', invoice.amount::text,
                        'tax_rate', invoice.tax_rate,
                        'tax_amount', invoice.tax_amount,
                        'total_with_tax', coalesce(invoice.total_with_tax, invoice.amount)::text,
                        'tags', coalesce(invoice.tags, array[]::text[]) ||
                            case when link_flags.has_manual_import then array['人工导入']::text[]
                                 else array[]::text[] end ||
                            case when link_flags.has_oa_attachment then array['OA附件']::text[]
                                 else array[]::text[] end,
                        'source_links', link_flags.compact_links,
                        'derived_from_oa_id', link_flags.oa_link->>'derived_from_oa_id',
                        'source_workbench_row_id', link_flags.oa_link->>'source_workbench_row_id',
                        'source_attachment_key', link_flags.oa_link->>'source_attachment_key',
                        'source_attachment_name', link_flags.oa_link->>'source_attachment_name',
                        'source_expense_item_ids', link_flags.expense_item_ids,
                        'source_expense_row_index', link_flags.oa_link->>'source_expense_row_index',
                        'invoice_bank_relation', jsonb_build_object(
                            'code', 'pending_collection',
                            'label', '待匹配流水',
                            'tone', 'warn'
                        ),
                        'available_actions', jsonb_build_array(
                            'detail', 'confirm_link'
                        )
                    )) as payload
                from app.invoices invoice
                join requested_members requested
                  on requested.row_type = 'invoice'
                 and requested.row_id = coalesce(invoice.legacy_mongo_id, invoice.id::text)
                 and requested.row_id not like 'etc-summary-%%'
                left join lateral (
                    select
                        bool_or(link.source_type = 'oa_attachment_invoice')
                            as has_oa_attachment,
                        bool_or(link.source_type = 'manual_invoice_import')
                            as has_manual_import,
                        coalesce(
                            jsonb_agg(
                                to_jsonb(link.source_type)
                                order by
                                    case link.source_type
                                        when 'manual_invoice_import' then 0
                                        when 'oa_attachment_invoice' then 1
                                        when 'oa_expense_item_invoice' then 2
                                        else 3
                                    end,
                                    link.ordinality
                            ) filter (where nullif(btrim(link.source_type), '') is not null),
                            '[]'::jsonb
                        ) as source_kinds,
                        coalesce(jsonb_agg(link.compact_link order by link.ordinality)
                            filter (where link.source_type in (
                                'oa_attachment_invoice',
                                'oa_expense_item_invoice'
                            )),
                            '[]'::jsonb) as compact_links,
                        coalesce(jsonb_agg(to_jsonb(link.compact_link->>'source_expense_item_id') order by link.ordinality)
                            filter (
                                where (
                                    link.source_type = 'oa_expense_item_invoice'
                                    or (
                                        not link.has_explicit_expense_link
                                        and link.source_type = 'oa_attachment_invoice'
                                    )
                                )
                                  and nullif(link.compact_link->>'source_expense_item_id', '') is not null
                            ), '[]'::jsonb) as expense_item_ids,
                        (array_agg(
                            link.compact_link
                            order by
                                case when link.source_type = 'oa_expense_item_invoice' then 0 else 1 end,
                                link.ordinality
                        )
                            filter (where link.source_type in (
                                'oa_attachment_invoice',
                                'oa_expense_item_invoice'
                            )))[1]
                            as oa_link
                    from (
                        select
                            source.ordinality,
                            coalesce(
                                source.value->>'source_type',
                                source.value->>'type',
                                source.value->>'source'
                            ) as source_type,
                            bool_or(coalesce(
                                source.value->>'source_type',
                                source.value->>'type',
                                source.value->>'source'
                            ) = 'oa_expense_item_invoice') over ()
                                as has_explicit_expense_link,
                            jsonb_strip_nulls(jsonb_build_object(
                                'source_type', coalesce(
                                    source.value->>'source_type',
                                    source.value->>'type',
                                    source.value->>'source'
                                ),
                                'source_expense_item_id', source.value->>'source_expense_item_id',
                                'source_expense_row_index', source.value->>'source_expense_row_index',
                                'derived_from_oa_id', source.value->>'derived_from_oa_id',
                                'source_workbench_row_id', source.value->>'source_workbench_row_id',
                                'source_attachment_key', source.value->>'source_attachment_key',
                                'source_attachment_name', source.value->>'source_attachment_name'
                            )) as compact_link
                        from jsonb_array_elements(
                            case
                                when jsonb_typeof(invoice.source_links) = 'array'
                                    then invoice.source_links
                                when jsonb_typeof(invoice.raw_payload->'source_links') = 'array'
                                    then invoice.raw_payload->'source_links'
                                when jsonb_typeof(
                                    invoice.raw_payload->'normalized_payload'->'source_links'
                                ) = 'array'
                                    then invoice.raw_payload->'normalized_payload'->'source_links'
                                else '[]'::jsonb
                            end
                        ) with ordinality source(value, ordinality)
                    ) link
                ) link_flags on true
                where invoice.status <> 'deleted'
                  and coalesce(invoice.workbench_visibility, 'visible')
                        <> 'hidden_after_etc_submission'
                  and coalesce(
                        invoice.raw_payload->'normalized_payload'->>'workbench_visibility',
                        'visible'
                      ) <> 'hidden_after_etc_submission'
                  and coalesce(
                        invoice.raw_payload->'normalized_payload'->>'etc_submission_status',
                        ''
                      ) <> 'submitted'
                  and not exists (
                      select 1 from app.etc_batch_invoice_links overlap_link
                      where overlap_link.link_status = 'active'
                        and overlap_link.invoice_id = invoice.id
                  )
                  and not exists (
                      select 1
                      from app.etc_invoices etc_invoice
                      left join app.etc_business_batches batch
                        on batch.business_batch_id = etc_invoice.business_batch_id
                      where (
                              (
                                  nullif(coalesce(invoice.digital_invoice_no, invoice.invoice_no), '')
                                      is not null
                                  and etc_invoice.invoice_no = coalesce(
                                      invoice.digital_invoice_no,
                                      invoice.invoice_no
                                  )
                              )
                           or (
                                  nullif(invoice.invoice_code, '') is not null
                              and nullif(invoice.invoice_no, '') is not null
                              and etc_invoice.invoice_code = invoice.invoice_code
                              and etc_invoice.invoice_no = invoice.invoice_no
                              )
                      )
                        and (
                              batch.status in (
                                  'oa_submitted', 'manually_marked_submitted', 'closed'
                              )
                           or (
                                  etc_invoice.status = 'submitted'
                              and coalesce(batch.status, '') <> 'deleted'
                              )
                        )
                  )
            ),
            relation_rows as materialized (
                select
                    'relation'::text as record_kind,
                    null::text as row_type,
                    null::text as row_id,
                    relation.case_id,
                    coalesce(
                        nullif(relation.amount_check->>'external_etc_batch_id', ''),
                        nullif(relation.amount_check->>'etc_batch_id', ''),
                        nullif(relation.special_metadata->>'external_etc_batch_id', ''),
                        nullif(relation.special_metadata->>'etc_batch_id', ''),
                        nullif(relation.special_metadata#>>'{etc_batch_link,external_etc_batch_id}', ''),
                        nullif(relation.special_metadata#>>'{etc_batch_link,etc_batch_id}', ''),
                        nullif(relation.special_metadata#>>'{historical_etc_business_batch_migration,external_etc_batch_id}', ''),
                        nullif(relation.special_metadata#>>'{historical_etc_business_batch_migration,etc_batch_id}', '')
                    ) as external_batch_id,
                    jsonb_strip_nulls(jsonb_build_object(
                        'case_id', relation.case_id,
                        'status', 'active',
                        'relation_mode', relation.relation_mode,
                        'month_scope', relation.month_scope::text,
                        'row_ids', relation.row_ids,
                        'row_types', array(
                            select case lower(member.row_type)
                                when 'oa_application' then 'oa'
                                when 'bank_transaction' then 'bank'
                                when 'invoice_record' then 'invoice'
                                when 'formal_invoice' then 'invoice'
                                when 'input' then 'invoice'
                                when 'input_invoice' then 'invoice'
                                when 'output' then 'invoice'
                                when 'output_invoice' then 'invoice'
                                when 'etc_summary' then 'invoice'
                                else lower(member.row_type) end
                            from unnest(relation.row_types) with ordinality
                                member(row_type, ordinality)
                            order by member.ordinality
                        ),
                        'amount_check', relation.amount_check,
                        'special_metadata', relation.special_metadata,
                        'display_tags', coalesce(
                            relation.raw_payload->'normalized_payload'->'display_tags',
                            relation.raw_payload->'display_tags'
                        )
                    )) as payload
                from app.workbench_pair_relations relation
                join requested_relations requested on requested.case_id = relation.case_id
                where relation.status = 'active'
            ),
            override_rows as materialized (
                select
                    'override'::text as record_kind,
                    override.row_type,
                    override.row_id,
                    null::text as case_id,
                    null::text as external_batch_id,
                    coalesce(
                        override.override_payload,
                        override.raw_payload->'normalized_payload',
                        override.raw_payload,
                        '{}'::jsonb
                    ) as payload
                from app.workbench_row_overrides override
                join requested_members requested
                  on requested.row_type = override.row_type
                 and requested.row_id = override.row_id
                where override.status = 'active'
            ),
            selected_decisions as materialized (
                select
                    'decision'::text as record_kind,
                    null::text as row_type,
                    null::text as row_id,
                    regexp_replace(decision.group_id, '^case:', '') as case_id,
                    null::text as external_batch_id,
                    jsonb_build_object(
                        'fingerprint', decision.fingerprint,
                        'decision', decision.resolution,
                        'note', coalesce(
                            decision.raw_payload#>>'{normalized_payload,note}',
                            ''
                        ),
                        'reviewed_by', coalesce(decision.updated_by, ''),
                        'reviewed_at', decision.updated_at
                    ) as payload
                from (
                    select
                        exception.raw_payload#>>'{normalized_payload,group_id}' as group_id,
                        exception.raw_payload#>>'{normalized_payload,fingerprint}'
                            as fingerprint,
                        exception.resolution,
                        exception.updated_by,
                        exception.updated_at,
                        exception.raw_payload,
                        row_number() over (
                            partition by exception.raw_payload#>>'{normalized_payload,group_id}'
                            order by exception.updated_at desc,
                                     exception.version desc,
                                     exception.case_id desc
                        ) as decision_rank
                    from app.workbench_exception_cases exception
                    where exception.scenario = 'workbench_anomaly_review'
                      and exception.raw_payload#>>'{normalized_payload,group_id}' = any(
                          select 'case:' || requested.case_id
                          from requested_relations requested
                      )
                ) decision
                join app.workbench_pair_relations relation
                  on relation.status = 'active'
                 and relation.case_id = regexp_replace(decision.group_id, '^case:', '')
                where decision.decision_rank = 1
                  and decision.updated_at >= relation.updated_at
            ),
            etc_source_rows as materialized (
                select
                    1 as source_rank,
                    requested.external_batch_id,
                    coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id,
                    invoice.invoice_no,
                    invoice.invoice_code,
                    invoice.digital_invoice_no,
                    invoice.invoice_date,
                    invoice.seller_name,
                    invoice.counterparty_name,
                    invoice.buyer_name,
                    invoice.amount,
                    invoice.total_with_tax,
                    invoice.tax_rate,
                    invoice.tax_amount,
                    invoice.invoice_type
                from requested_etc requested
                join app.etc_batch_invoice_links link on link.link_status = 'active'
                join app.invoices invoice
                  on invoice.id = link.invoice_id and invoice.status <> 'deleted'
                left join app.etc_business_batches batch
                  on batch.business_batch_id = link.business_batch_id
                where requested.external_batch_id = coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    link.business_batch_id
                )
                union all
                select
                    2,
                    requested.external_batch_id,
                    coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text),
                    invoice.invoice_no,
                    invoice.invoice_code,
                    invoice.invoice_no,
                    invoice.invoice_date,
                    invoice.seller_name,
                    invoice.seller_name,
                    invoice.buyer_name,
                    invoice.amount,
                    invoice.total_with_tax,
                    coalesce(
                        invoice.raw_payload->'normalized_payload'->>'tax_rate',
                        '—'
                    ),
                    invoice.tax_amount,
                    '进项发票'::text
                from requested_etc requested
                join app.etc_business_batches batch
                  on batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                 and requested.external_batch_id = coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                 )
                join app.etc_invoices invoice
                  on invoice.business_batch_id = batch.business_batch_id
                 and invoice.status <> 'deleted'
                union all
                select
                    3,
                    requested.external_batch_id,
                    coalesce(invoice.legacy_mongo_id, invoice.id::text),
                    invoice.invoice_no,
                    invoice.invoice_code,
                    invoice.digital_invoice_no,
                    invoice.invoice_date,
                    invoice.seller_name,
                    invoice.counterparty_name,
                    invoice.buyer_name,
                    invoice.amount,
                    invoice.total_with_tax,
                    invoice.tax_rate,
                    invoice.tax_amount,
                    invoice.invoice_type
                from requested_etc requested
                join app.etc_submission_batches submission
                  on submission.status in ('submitted_confirmed', 'submitted', 'closed')
                 and requested.external_batch_id = coalesce(
                    nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                    submission.submission_batch_id
                 )
                join app.invoices invoice
                  on invoice.status <> 'deleted'
                 and (
                        submission.submission_batch_id = coalesce(
                            invoice.raw_payload->'normalized_payload'
                                ->>'etc_submission_batch_id',
                            ''
                        )
                     or requested.external_batch_id = coalesce(
                            invoice.raw_payload->'normalized_payload'
                                ->>'etc_submission_batch_id',
                            ''
                        )
                 )
                 and (
                        invoice.workbench_visibility = 'hidden_after_etc_submission'
                     or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
                            = 'hidden_after_etc_submission'
                     or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
                            = 'submitted'
                 )
            ),
            preferred_etc_rows as materialized (
                select source.*,
                       case when source.source_rank in (1, 2) then 1 else 2 end
                           as source_tier,
                       row_number() over (
                           partition by source.external_batch_id,
                               coalesce(
                                   nullif(source.digital_invoice_no, ''),
                                   nullif(source.invoice_no, ''),
                                   source.row_id
                           )
                           order by source.source_rank, source.row_id
                       ) as identity_rank,
                       min(case when source.source_rank in (1, 2) then 1 else 2 end) over (
                           partition by source.external_batch_id
                       ) as preferred_source_tier
                from etc_source_rows source
            ),
            etc_summary_rows as materialized (
                select
                    'etc'::text as record_kind,
                    'invoice'::text as row_type,
                    'etc-summary-' || regexp_replace(
                        preferred.external_batch_id,
                        '[^A-Za-z0-9_-]+',
                        '-',
                        'g'
                    ) as row_id,
                    null::text as case_id,
                    preferred.external_batch_id,
                    jsonb_build_object(
                        'invoice_count', count(*)::bigint,
                        'total_amount', coalesce(sum(
                            coalesce(preferred.total_with_tax, preferred.amount, 0)
                        ), 0)::text,
                        'issue_date_min', min(preferred.invoice_date)::text,
                        'issue_date_max', max(preferred.invoice_date)::text,
                        'seller_name', (array_agg(
                            coalesce(preferred.seller_name, preferred.counterparty_name)
                            order by preferred.invoice_date, preferred.row_id
                        ))[1],
                        'first_invoice', (jsonb_agg(jsonb_build_object(
                            'row_id', preferred.row_id,
                            'invoice_no', preferred.invoice_no,
                            'invoice_code', preferred.invoice_code,
                            'digital_invoice_no', preferred.digital_invoice_no,
                            'invoice_date', preferred.invoice_date,
                            'seller_name', preferred.seller_name,
                            'counterparty_name', preferred.counterparty_name,
                            'buyer_name', preferred.buyer_name,
                            'amount', preferred.amount,
                            'total_with_tax', preferred.total_with_tax,
                            'tax_rate', preferred.tax_rate,
                            'tax_amount', preferred.tax_amount,
                            'invoice_type', preferred.invoice_type
                        ) order by preferred.invoice_date, preferred.row_id)->0)
                    ) as payload
                from preferred_etc_rows preferred
                where preferred.source_tier = preferred.preferred_source_tier
                  and preferred.identity_rank = 1
                group by preferred.external_batch_id
            )
            select completed_oa_rows.* from completed_oa_rows
            cross join oa_identity_guard
            where oa_identity_guard.guard = 1
            union all select pending_oa_rows.* from pending_oa_rows
            cross join oa_identity_guard
            where oa_identity_guard.guard = 1
            union all select * from bank_rows
            union all select * from invoice_rows
            union all select * from relation_rows
            union all select * from override_rows
            union all select * from selected_decisions
            union all select * from etc_summary_rows
            union all select * from bank_settings_row
            order by record_kind, case_id, row_type, row_id
            """
            .replace(
                "__PENDING_OA_APPLICATION_TIME_SQL__",
                pending_oa_application_time_sql("admission"),
            )
            .replace(
                "__PENDING_OA_APPLICATION_DATE_SQL__",
                pending_oa_application_date_sql("admission"),
            )
            .replace(
                "__COMPLETED_OA_SOURCE_ALIASES_SQL__",
                oa_source_aliases_sql("oa", "oa.normalized_payload"),
            )
            .replace(
                "__COMPLETED_OA_SOURCE_IDENTITY_ALIASES_SQL__",
                oa_source_identity_aliases_sql("oa.normalized_payload"),
            )
            .replace(
                "__PENDING_OA_SOURCE_IDENTITY_ALIASES_SQL__",
                oa_source_identity_aliases_sql("admission.source_payload"),
            ),
            (
                member_types,
                member_ids,
                relation_case_ids,
                sorted(external_batch_ids),
                self._tenant_id,
            ),
        )

        rows_by_typed_id: dict[tuple[str, str], dict[str, Any]] = {}
        relations: list[dict[str, Any]] = []
        page_overrides: dict[tuple[str, str], dict[str, Any]] = {}
        decisions: dict[str, dict[str, Any]] = {}
        page_etc_summaries: dict[str, dict[str, Any]] = {}
        settings: dict[str, Any] | None = None
        for source in rows:
            record_kind = str(source.get("record_kind") or "")
            payload = row_payload(source, "payload")
            payload = dict(payload) if isinstance(payload, dict) else {}
            if record_kind == "row":
                if str(source.get("row_type") or "").strip() == "invoice":
                    payload["source_kinds"] = invoice_source_kinds(
                        [
                            {"source_type": source_kind}
                            for source_kind in list(payload.get("source_kinds") or [])
                        ]
                    )
                identity = (
                    self._normalize_row_type(source.get("row_type")),
                    str(source.get("row_id") or "").strip(),
                )
                if identity in rows_by_typed_id:
                    raise ValueError(
                        "Duplicate compact canonical Workbench page member: "
                        f"{identity[0]}:{identity[1]}."
                    )
                rows_by_typed_id[identity] = payload
            elif record_kind == "relation":
                relations.append(payload)
            elif record_kind == "override":
                page_overrides[(
                    self._normalize_row_type(source.get("row_type")),
                    str(source.get("row_id") or "").strip(),
                )] = payload
            elif record_kind == "decision":
                fingerprint = str(payload.get("fingerprint") or "").strip()
                decision = str(payload.get("decision") or "").strip()
                if fingerprint and decision in {"accept_paired", "keep_unpaired"}:
                    decisions[fingerprint] = payload
            elif record_kind == "etc":
                external_batch_id = str(
                    source.get("external_batch_id") or ""
                ).strip()
                row_id = etc_row_ids_by_external_batch_id.get(
                    external_batch_id,
                    str(source.get("row_id") or "").strip(),
                )
                summary = self._compact_etc_summary_row(
                    row_id=row_id,
                    external_batch_id=external_batch_id,
                    payload=payload,
                )
                page_etc_summaries[external_batch_id] = summary
                if ("invoice", row_id) in set(zip(member_types, member_ids, strict=True)):
                    rows_by_typed_id[("invoice", row_id)] = summary
            elif record_kind == "settings":
                if settings is not None:
                    raise ValueError(
                        "Canonical Workbench compact hydration returned duplicate settings."
                    )
                settings = payload

        expected_typed_ids = set(zip(member_types, member_ids, strict=True))
        if set(rows_by_typed_id) != expected_typed_ids:
            missing = sorted(expected_typed_ids - set(rows_by_typed_id))
            raise ValueError(
                "Canonical Workbench compact page members changed during hydration: "
                + ",".join(f"{row_type}:{row_id}" for row_type, row_id in missing)
            )
        if any(row_type == "bank" for row_type, _row_id in expected_typed_ids):
            if settings is None:
                raise ValueError(
                    "Canonical Workbench compact hydration did not return settings."
                )
            self._enrich_bank_category_projection(
                rows_by_typed_id,
                connection=connection,
                settings=settings,
            )
        normalize_oa_attachment_expense_item_ids(list(rows_by_typed_id.values()))
        grouped = WorkbenchCanonicalRowsBuilder(
            connection=connection
        ).build_page_groups(
            scope_key=scope_key,
            rows_by_typed_id=rows_by_typed_id,
            relations=relations,
            page_overrides=page_overrides,
            anomaly_review_decisions=decisions,
            page_etc_summaries=page_etc_summaries,
        )
        grouped_groups = [
            group
            for zone in ("paired", "unpaired")
            for group in list((grouped.get(zone) or {}).get("groups") or [])
            if isinstance(group, dict)
        ]
        groups_by_id = {
            str(group.get("group_id") or ""): group for group in grouped_groups
        }
        groups_by_member = {
            (str(row.get("type") or ""), str(row.get("id") or "")): group
            for group in grouped_groups
            for row in self.group_rows(group)
            if str(row.get("type") or "") and str(row.get("id") or "")
        }
        result: list[dict[str, Any]] = []
        for descriptor in descriptors:
            if str(descriptor.get("group_kind") or "") == "relation":
                group = groups_by_id.get(f"case:{descriptor.get('detail_key') or ''}")
            else:
                descriptor_ids = text_list(descriptor.get("member_ids"))
                descriptor_types = text_list(descriptor.get("member_types"))
                group = groups_by_member.get((descriptor_types[0], descriptor_ids[0]))
            if not isinstance(group, dict):
                raise RuntimeError(
                    "Workbench compact hydration could not assemble a selected group."
                )
            descriptor_zone = str(descriptor.get("zone") or "")
            if descriptor_zone and str(group.get("zone") or "") != descriptor_zone:
                raise RuntimeError(
                    "Workbench direct candidate zone disagrees with canonical completion policy."
                )
            result_payload = self._with_group_counts(group)
            result_payload["detail_key"] = str(descriptor.get("detail_key") or "")
            result.append(self._compact_group(result_payload))
        return result

    @staticmethod
    def _settings_payload(connection: Any) -> dict[str, Any]:
        row = connection.fetch_one(
            """
            select settings_payload
            from app.app_settings
            where settings_key = 'app_settings'
            limit 1
            """
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else None
        return dict(payload) if isinstance(payload, dict) else {}

    @staticmethod
    def _bank_account_resolver(settings: dict[str, Any]) -> BankAccountResolver:
        mappings: dict[str, str] = {}
        for account in bank_accounts_from_settings_payload(settings):
            last4 = str(account.get("account_last4") or "").strip()
            bank_name = str(account.get("bank_name") or "").strip()
            if last4 and bank_name:
                mappings.setdefault(last4, bank_name)
        return BankAccountResolver(lambda: dict(mappings))

    def _enrich_bank_category_projection(
        self,
        rows_by_typed_id: dict[tuple[str, str], dict[str, Any]],
        *,
        connection: Any,
        settings: dict[str, Any],
    ) -> None:
        transaction_ids = sorted(
            row_id
            for row_type, row_id in rows_by_typed_id
            if row_type == "bank"
        )
        if not transaction_ids:
            return
        projections = (
            PostgresBankDetailsCanonicalQueryRepository.workbench_category_projection_rows(
                connection,
                settings=settings,
                transaction_ids=transaction_ids,
                tenant_id=self._tenant_id,
            )
        )
        for transaction_id in transaction_ids:
            projection = projections.get(transaction_id) or {
                "category_resolution_status": "unmatched"
            }
            rows_by_typed_id[("bank", transaction_id)].update(projection)

    @staticmethod
    def _compact_etc_summary_row(
        *,
        row_id: str,
        external_batch_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        count = max(0, int(payload.get("invoice_count") or 0))
        try:
            total = Decimal(str(payload.get("total_amount") or "0")).quantize(
                Decimal("0.01")
            )
        except (InvalidOperation, TypeError, ValueError):
            total = Decimal("0.00")
        minimum = str(payload.get("issue_date_min") or "").strip()
        maximum = str(payload.get("issue_date_max") or "").strip()
        issue_range = minimum if minimum == maximum else " 至 ".join(
            value for value in (minimum, maximum) if value
        )
        title = f"ETC发票 {count} 张"
        amount = f"{total:.2f}"
        first_invoice = payload.get("first_invoice")
        detail_rows = (
            [
                WorkbenchCanonicalRowsBuilder._etc_invoice_detail_row(
                    first_invoice,
                    external_batch_id=external_batch_id,
                )
            ]
            if isinstance(first_invoice, dict)
            else []
        )
        return {
            "id": row_id,
            "type": "invoice",
            "source_kind": "etc_invoice_summary",
            "status": "unpaired",
            "seller_tax_no": "ETC批次",
            "seller_name": title,
            "buyer_tax_no": external_batch_id,
            "buyer_name": str(payload.get("seller_name") or "ETC发票"),
            "invoice_code": external_batch_id,
            "invoice_no": title,
            "digital_invoice_no": title,
            "issue_date": issue_range or "—",
            "amount": amount,
            "amount_value": str(total),
            "tax_rate": "—",
            "tax_amount": "—",
            "total_with_tax": amount,
            "invoice_type": "进项发票",
            "invoice_bank_relation": {
                "code": "pending_oa_bank_match",
                "label": "待匹配OA/流水",
                "tone": "warn",
            },
            "tags": ["ETC", "ETC批量提交"],
            "etc_batch_id": external_batch_id,
            "etc_invoice_count": count,
            "etc_invoice_detail_count": count,
            "etc_invoice_detail_rows": detail_rows,
            "available_actions": ["detail"],
        }

    def _load_relations(
        self,
        case_ids: set[str],
        *,
        connection: Any,
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if not case_ids:
            return [], {}
        rows = connection.fetch_all(
            """
            select relation.case_id, relation.relation_mode, relation.month_scope,
                   relation.row_ids, relation.row_types, relation.amount_check,
                   relation.special_metadata, relation.raw_payload,
                   relation.updated_at as relation_updated_at,
                   decision.fingerprint as decision_fingerprint,
                   decision.resolution as decision_resolution,
                   decision.updated_by as decision_updated_by,
                   decision.updated_at as decision_updated_at,
                   decision.raw_payload#>>'{normalized_payload,note}' as decision_note
            from app.workbench_pair_relations relation
            left join lateral (
                select
                    exception.raw_payload#>>'{normalized_payload,fingerprint}'
                        as fingerprint,
                    exception.resolution,
                    exception.updated_by,
                    exception.updated_at,
                    exception.raw_payload
                from app.workbench_exception_cases exception
                where exception.scenario = 'workbench_anomaly_review'
                  and exception.raw_payload#>>'{normalized_payload,group_id}'
                      = 'case:' || relation.case_id
                order by exception.updated_at desc,
                         exception.version desc,
                         exception.case_id desc
                limit 1
            ) decision on true
            where relation.status = 'active'
              and relation.case_id = any(%s::text[])
            order by relation.case_id
            """,
            (sorted(case_ids),),
        )
        relations: list[dict[str, Any]] = []
        decisions: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = row_payload(row, "raw_payload")
            payload = payload if isinstance(payload, dict) else {}
            relations.append(
                {
                    **payload,
                    "case_id": str(row.get("case_id") or ""),
                    "status": "active",
                    "relation_mode": row.get("relation_mode") or payload.get("relation_mode"),
                    "row_ids": text_list(row.get("row_ids")),
                    "row_types": [
                        self._normalize_row_type(value)
                        for value in text_list(row.get("row_types"))
                    ],
                    "amount_check": row_payload(row, "amount_check") or {},
                    "special_metadata": row_payload(row, "special_metadata") or {},
                }
            )
            fingerprint = str(row.get("decision_fingerprint") or "").strip()
            resolution = str(row.get("decision_resolution") or "").strip()
            reviewed_at = row.get("decision_updated_at")
            relation_updated_at = row.get("relation_updated_at")
            if (
                fingerprint
                and resolution in {"accept_paired", "keep_unpaired"}
                and reviewed_at is not None
                and relation_updated_at is not None
                and reviewed_at >= relation_updated_at
            ):
                decisions[fingerprint] = {
                    "decision": resolution,
                    "note": str(row.get("decision_note") or ""),
                    "reviewed_by": str(row.get("decision_updated_by") or ""),
                    "reviewed_at": serialize_value(reviewed_at),
                }
        return relations, decisions

    @staticmethod
    def group_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for pane in ("oa", "bank", "invoice"):
            rows.extend(
                row
                for row in list(group.get(f"{pane}_rows") or [])
                if isinstance(row, dict)
            )
        collapsed = group.get("collapsed_rows")
        if isinstance(collapsed, dict):
            for pane in ("oa", "bank", "invoice"):
                rows.extend(
                    row
                    for row in list(collapsed.get(pane) or [])
                    if isinstance(row, dict)
                )
        return rows

    @staticmethod
    def _with_group_counts(group: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(group)
        fact_counts = {
            pane: sum(
                1 for row in list(payload.get(f"{pane}_rows") or []) if isinstance(row, dict)
            )
            for pane in ("oa", "bank", "invoice")
        }
        fact_counts["rows"] = sum(fact_counts.values())
        display_counts = dict(fact_counts)
        collapsed = payload.get("collapsed_rows")
        if isinstance(collapsed, dict):
            for pane in ("oa", "bank", "invoice"):
                display_counts[pane] += sum(
                    1 for row in list(collapsed.get(pane) or []) if isinstance(row, dict)
                )
            display_counts["rows"] = sum(
                display_counts[pane] for pane in ("oa", "bank", "invoice")
            )
        payload["row_counts"] = fact_counts
        payload["display_row_counts"] = display_counts
        payload["row_count"] = fact_counts["rows"]
        return payload

    @staticmethod
    def _compact_group(group: dict[str, Any]) -> dict[str, Any]:
        compact = without_keys(
            group,
            {
                "raw_payload",
                "payload",
                "source_payload",
                "source_links",
                "source_versions",
                "detail_fields",
                "object_identity",
                "artifacts",
                "evidences",
                "ocr_text",
                "full_text",
            },
        )
        if isinstance(compact, dict):
            collapsed = compact.get("collapsed_rows")
            invoice_rows = list(compact.get("invoice_rows") or [])
            is_etc_summary = any(
                isinstance(row, dict)
                and str(row.get("source_kind") or "").strip() == "etc_invoice_summary"
                for row in invoice_rows
            )
            first_etc_invoice = next(
                (
                    row
                    for row in list(collapsed.get("invoice") or [])
                    if isinstance(row, dict)
                    and str(row.get("source_kind") or "").strip() == "etc_invoice"
                ),
                None,
            ) if isinstance(collapsed, dict) and is_etc_summary else None
            if first_etc_invoice is None:
                compact.pop("collapsed_rows", None)
            else:
                compact["collapsed_rows"] = {"invoice": [first_etc_invoice]}
            for pane in ("oa", "bank", "invoice"):
                visible_rows = list(compact.get(f"{pane}_rows") or [])
                if pane == "invoice":
                    visible_rows.extend(list((compact.get("collapsed_rows") or {}).get("invoice") or []))
                for row in visible_rows:
                    if not isinstance(row, dict):
                        continue
                    # Summary pages inherit the relation-level amount check in
                    # the frontend. Repeating the same payload on every row is
                    # both redundant and a material transfer/serialization cost.
                    row.pop("relation_amount_check", None)
                    for key in (
                        "object_identity_key",
                        "object_identity_kind",
                        "object_identity_source",
                        "object_identity_confidence",
                        "source_identity_aliases",
                    ):
                        row.pop(key, None)
                    metadata = row.get("special_metadata")
                    if isinstance(metadata, dict):
                        compact_metadata = {
                            key: metadata[key]
                            for key in ("relation_mode", "source_batch_id", "batch_version")
                            if key in metadata
                        }
                        if compact_metadata:
                            row["special_metadata"] = compact_metadata
                        else:
                            row.pop("special_metadata", None)
        return compact

    @staticmethod
    def _normalize_row_type(value: object) -> str:
        normalized = str(value or "").strip().lower()
        return {
            "oa_application": "oa",
            "bank_transaction": "bank",
            "invoice_record": "invoice",
            "formal_invoice": "invoice",
            "input": "invoice",
            "input_invoice": "invoice",
            "output": "invoice",
            "output_invoice": "invoice",
            "etc_summary": "invoice",
        }.get(normalized, normalized)


__all__ = [
    "PostgresWorkbenchPageHydrationRepository",
    "WORKBENCH_PAGE_HYDRATION_STATEMENT_BUDGET",
    "WORKBENCH_SUMMARY_HYDRATION_STATEMENT_BUDGET",
    "oa_expense_items_with_supporting_documents_sql",
]
