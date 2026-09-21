from __future__ import annotations

from typing import Any

# Read-only expansion. The stored relation continues to own the ETC summary;
# page consumers receive canonical invoices, never the summary as an invoice.
RELATION_INVOICE_READ_SQL = """
(
    select relation.id, relation.case_id, relation.relation_mode, relation.status,
           relation.version, relation.month_scope, relation.amount_check,
           relation.special_metadata, relation.source_versions, relation.raw_payload,
           relation.created_at, relation.updated_at,
           case when expanded.row_ids is null then relation.row_ids else expanded.row_ids end as row_ids,
           case when expanded.row_ids is null then relation.row_types else expanded.row_types end as row_types
    from app.workbench_pair_relations relation
    left join lateral (
        select array_agg(member.row_id order by member.position, member.row_id) as row_ids,
               array_agg(member.row_type order by member.position, member.row_id) as row_types
        from (
            select resolved.row_id, resolved.row_type, min(source.ordinality) as position
            from unnest(relation.row_ids, relation.row_types) with ordinality source(row_id, row_type, ordinality)
            cross join lateral (
                select source.row_id, source.row_type
                where source.row_type <> 'invoice' or source.row_id not like 'etc-summary-%%'
                union
                select coalesce(invoice.legacy_mongo_id, invoice.id::text), 'invoice'
                from app.etc_business_batches batch
                join app.invoices invoice on invoice.status <> 'deleted' and invoice.invoice_type = 'input'
                where source.row_type = 'invoice'
                  and source.row_id = 'etc-summary-' || regexp_replace(coalesce(
                      nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                      nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                      nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                      nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                      batch.business_batch_id), '[^A-Za-z0-9_-]+', '-', 'g')
                  and batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                  and (
                      exists (select 1 from app.etc_batch_invoice_links link
                              where link.business_batch_id = batch.business_batch_id
                                and link.invoice_id = invoice.id and link.link_status = 'active')
                      or exists (select 1 from app.etc_invoices etc
                                 where etc.business_batch_id = batch.business_batch_id
                                   and etc.status <> 'deleted' and etc.etc_invoice_id = invoice.etc_invoice_id)
                  )
                union
                select coalesce(invoice.legacy_mongo_id, invoice.id::text), 'invoice'
                from app.etc_submission_batches submission
                join app.invoices invoice
                  on invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id' in (
                      submission.submission_batch_id,
                      submission.raw_payload->'normalized_payload'->>'etc_batch_id')
                where source.row_type = 'invoice' and invoice.status <> 'deleted'
                  and invoice.invoice_type = 'input'
                  and submission.status in ('submitted_confirmed', 'submitted', 'closed')
                  and source.row_id = 'etc-summary-' || regexp_replace(coalesce(
                      nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                      submission.submission_batch_id), '[^A-Za-z0-9_-]+', '-', 'g')
            ) resolved
            group by resolved.row_id, resolved.row_type
        ) member
        where exists (select 1 from unnest(relation.row_ids) summary(row_id)
                      where summary.row_id like 'etc-summary-%%')
    ) expanded on true
)
"""


def expand_relation_invoices(connection: Any, relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expand only requested ETC relations in the caller's read snapshot."""
    case_ids = [relation['case_id'] for relation in relations
                if any(str(row_id).startswith('etc-summary-') for row_id in relation.get('row_ids', []))]
    if not case_ids:
        return relations
    rows = connection.fetch_all(
        f"select case_id, row_ids, row_types from {RELATION_INVOICE_READ_SQL} relation where case_id = any(%s::text[])",
        (case_ids,),
    )
    by_case = {row['case_id']: row for row in rows}
    return [{**relation, **by_case[relation['case_id']]} if relation['case_id'] in by_case else relation
            for relation in relations]
