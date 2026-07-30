from __future__ import annotations


WORKBENCH_RELATION_EXTERNAL_ETC_BATCH_ID_SQL = """
coalesce(
    nullif(relation.amount_check->>'external_etc_batch_id', ''),
    nullif(relation.amount_check->>'etc_batch_id', ''),
    nullif(relation.special_metadata->>'external_etc_batch_id', ''),
    nullif(relation.special_metadata->>'etc_batch_id', ''),
    nullif(relation.special_metadata#>>'{etc_batch_link,external_etc_batch_id}', ''),
    nullif(relation.special_metadata#>>'{etc_batch_link,etc_batch_id}', ''),
    nullif(
        relation.special_metadata#>>'{historical_etc_business_batch_migration,external_etc_batch_id}',
        ''
    ),
    nullif(
        relation.special_metadata#>>'{historical_etc_business_batch_migration,etc_batch_id}',
        ''
    )
)
"""


CANONICAL_ETC_BATCH_CANDIDATES_SQL = """
select coalesce(
           nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
           link.business_batch_id
       ) as external_batch_id
from app.etc_batch_invoice_links link
join app.invoices invoice
  on invoice.id = link.invoice_id
left join app.etc_business_batches batch
  on batch.business_batch_id = link.business_batch_id
where link.link_status = 'active'
  and invoice.status <> 'deleted'
union all
select coalesce(
           nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
           nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
           batch.business_batch_id
       ) as external_batch_id
from app.etc_business_batches batch
join lateral jsonb_array_elements_text(
    case
        when jsonb_typeof(batch.raw_payload->'normalized_payload'->'invoice_ids') = 'array'
            then batch.raw_payload->'normalized_payload'->'invoice_ids'
        else '[]'::jsonb
    end
) member(invoice_id) on true
join app.etc_invoices invoice
  on invoice.etc_invoice_id = member.invoice_id
  or coalesce(invoice.legacy_mongo_id, '') = member.invoice_id
where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
  and invoice.status <> 'deleted'
union all
select coalesce(
           nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
           submission.submission_batch_id
       ) as external_batch_id
from app.etc_submission_batches submission
join app.invoices invoice
  on submission.submission_batch_id = coalesce(
      invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
      ''
  )
  or coalesce(
      nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
      submission.submission_batch_id
  ) = coalesce(
      invoice.raw_payload->'normalized_payload'->>'etc_submission_batch_id',
      ''
  )
where submission.status in ('submitted_confirmed', 'submitted', 'closed')
  and invoice.status <> 'deleted'
  and (
        invoice.workbench_visibility = 'hidden_after_etc_submission'
     or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
            = 'hidden_after_etc_submission'
     or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
            = 'submitted'
  )
"""
