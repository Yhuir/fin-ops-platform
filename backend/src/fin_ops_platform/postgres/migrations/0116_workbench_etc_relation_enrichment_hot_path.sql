create index if not exists oa_applications_etc_batch_marker_idx
    on app.oa_applications (
        (normalized_payload->>'etc_batch_id'),
        (coalesce(application_date, scope_month))
    )
    where status <> 'deleted'
      and nullif(normalized_payload->>'etc_batch_id', '') is not null;

create index if not exists etc_business_batches_external_scope_idx
    on app.etc_business_batches (
        (coalesce(
            nullif(raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            business_batch_id
        )),
        scope_month
    )
    where status in ('oa_submitted', 'manually_marked_submitted', 'closed');

create index if not exists workbench_pair_relations_active_etc_link_idx
    on app.workbench_pair_relations (
        (special_metadata->'etc_batch_link'->>'external_etc_batch_id')
    )
    where status = 'active'
      and nullif(special_metadata->'etc_batch_link'->>'external_etc_batch_id', '') is not null;
