from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb


class PostgresOASourceAliasRepairRepository:
    """Bounded evidence and writer boundary for one historical OA alias."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def inspect_candidate(self, *, alias_row_id: str, canonical_row_id: str) -> dict[str, Any]:
        return dict(
            self._connection.fetch_one(
                """
                with canonical_oa as materialized (
                    select oa.id, oa.row_id
                    from app.oa_applications oa
                    where oa.row_id = %s
                      and oa.status <> 'deleted'
                ),
                owned_attachments as materialized (
                    select attachment.source_attachment_key
                    from app.oa_attachments attachment
                    join canonical_oa oa on oa.id = attachment.oa_application_id
                    where nullif(btrim(attachment.source_attachment_key), '') is not null
                ),
                bridge_sources as materialized (
                    select distinct
                        source.source_expense_item_id,
                        source.source_expense_row_index,
                        owned.source_attachment_key as owned_attachment_key,
                        source.source_attachment_key,
                        source.cache_source_attachment_key
                    from owned_attachments owned
                    join app.oa_attachment_invoice_cache_sources source
                      on source.source_attachment_key = owned.source_attachment_key
                    where split_part(source.source_expense_item_id, ':item:', 1) = %s
                    union
                    select distinct
                        source.source_expense_item_id,
                        source.source_expense_row_index,
                        owned.source_attachment_key,
                        source.source_attachment_key,
                        source.cache_source_attachment_key
                    from owned_attachments owned
                    join app.oa_attachment_invoice_cache_sources source
                      on source.cache_source_attachment_key = owned.source_attachment_key
                    where split_part(source.source_expense_item_id, ':item:', 1) = %s
                ),
                invoice_sources as materialized (
                    select distinct
                        invoice.id::text as invoice_id,
                        source_link.value->>'source_expense_item_id' as source_expense_item_id,
                        source_link.value->>'source_expense_row_index' as source_expense_row_index,
                        source_link.value->>'source_attachment_key' as source_attachment_key
                    from app.invoices invoice
                    cross join lateral jsonb_array_elements(
                        case when jsonb_typeof(invoice.source_links) = 'array'
                             then invoice.source_links else '[]'::jsonb end
                    ) source_link(value)
                    where invoice.status <> 'deleted'
                      and source_link.value->>'source_type' = 'oa_attachment_invoice'
                      and split_part(
                          source_link.value->>'source_expense_item_id', ':item:', 1
                      ) = %s
                      and exists (
                          select 1
                          from bridge_sources bridge
                          where source_link.value->>'source_attachment_key' in (
                              bridge.owned_attachment_key,
                              bridge.source_attachment_key,
                              bridge.cache_source_attachment_key
                          )
                      )
                ),
                existing_alias as materialized (
                    select alias.canonical_row_id, alias.status
                    from app.oa_source_aliases alias
                    where alias.alias_row_id = %s
                    order by alias.updated_at desc, alias.id desc
                    limit 1
                )
                select
                    (select count(*)::int from canonical_oa) as canonical_count,
                    (
                        select count(*)::int
                        from app.oa_applications alias_oa
                        where alias_oa.row_id = %s
                          and alias_oa.status <> 'deleted'
                    ) as alias_application_count,
                    (select canonical_row_id from existing_alias) as existing_canonical_row_id,
                    (select status from existing_alias) as existing_status,
                    coalesce(array(
                        select distinct bridge.source_expense_item_id
                        from bridge_sources bridge
                        order by bridge.source_expense_item_id
                    ), array[]::text[]) as bridge_item_ids,
                    coalesce(array(
                        select distinct bridge.source_expense_row_index
                        from bridge_sources bridge
                        where nullif(bridge.source_expense_row_index, '') is not null
                        order by bridge.source_expense_row_index
                    ), array[]::text[]) as bridge_row_indexes,
                    coalesce(array(
                        select distinct encode(digest(key.value, 'sha256'), 'hex')
                        from bridge_sources bridge
                        cross join lateral unnest(array[
                            bridge.owned_attachment_key,
                            bridge.source_attachment_key,
                            bridge.cache_source_attachment_key
                        ]) key(value)
                        where nullif(key.value, '') is not null
                        order by encode(digest(key.value, 'sha256'), 'hex')
                    ), array[]::text[]) as attachment_key_hashes,
                    coalesce(array(
                        select distinct invoice.invoice_id
                        from invoice_sources invoice
                        order by invoice.invoice_id
                    ), array[]::text[]) as invoice_ids,
                    coalesce(array(
                        select distinct invoice.source_expense_item_id
                        from invoice_sources invoice
                        order by invoice.source_expense_item_id
                    ), array[]::text[]) as invoice_item_ids,
                    coalesce(array(
                        select distinct invoice.source_expense_row_index
                        from invoice_sources invoice
                        where nullif(invoice.source_expense_row_index, '') is not null
                        order by invoice.source_expense_row_index
                    ), array[]::text[]) as invoice_row_indexes
                """,
                (
                    canonical_row_id,
                    alias_row_id,
                    alias_row_id,
                    alias_row_id,
                    alias_row_id,
                    alias_row_id,
                ),
            )
            or {}
        )

    def activate_alias(
        self,
        *,
        alias_row_id: str,
        canonical_row_id: str,
        reason: str,
        evidence_hash: str,
        reviewed_by: str,
        raw_payload: dict[str, Any],
    ) -> bool:
        return bool(
            self._connection.execute(
                """
                insert into app.oa_source_aliases(
                    alias_row_id, canonical_row_id, reason, evidence_hash,
                    status, reviewed_by, reviewed_at, raw_payload, updated_at
                )
                select %s, %s, %s, %s, 'active', %s, now(), %s, now()
                where exists (
                    select 1
                    from app.oa_applications oa
                    where oa.row_id = %s
                      and oa.status <> 'deleted'
                )
                  and not exists (
                    select 1
                    from app.oa_applications alias_oa
                    where alias_oa.row_id = %s
                      and alias_oa.status <> 'deleted'
                )
                  and not exists (
                    select 1
                    from app.oa_source_aliases alias
                    where alias.alias_row_id = %s
                )
                """,
                (
                    alias_row_id,
                    canonical_row_id,
                    reason,
                    evidence_hash,
                    reviewed_by,
                    jsonb(raw_payload),
                    canonical_row_id,
                    alias_row_id,
                    alias_row_id,
                ),
            )
            or 0
        )
