set local lock_timeout = '10s';
set local statement_timeout = '1min';

do $$
declare
    v_relation_case_id constant text := 'CASE-BATCH-txn_imported_1453';
    v_group_id constant text := 'case:CASE-BATCH-txn_imported_1453';
    v_scope_month constant date := date '2026-04-01';
    v_external_batch_id constant text := 'ETC-OA-20260413-241125';
    v_business_batch_id constant text := 'etc_business_batch_hist_20260413_241125';
    v_expected_invoice_count constant integer := 44;
    v_expected_invoice_total constant numeric := 2411.25;
    v_expected_invoice_contract_sha256 constant text :=
        '4aa0f9ee52fea682caa89ead17a9ad29b3c830c77b25f9aca0ab2acf9d7455fa';
    v_old_fingerprint constant text :=
        'e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76';
    v_new_fingerprint constant text :=
        'cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b';
    v_removed_evidence constant text :=
        '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f';
    v_remaining_evidence constant text[] := array[
        '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
        'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
    ]::text[];
    v_expected_old_evidence constant text[] := array[
        '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f',
        '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
        'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
    ]::text[];
    v_expected_members constant text[] := array[
        'bank:txn_imported_1453',
        'invoice:etc-summary-ETC-OA-20260413-241125',
        'oa:oa-exp-2080'
    ]::text[];
    v_expected_oa_items constant text[] := array[
        '1|oa-exp-2080:item:0:63f422ef26de|0|2169.68|0',
        '1|oa-exp-2080:item:1:3b08cbfe865a|1|241.57|0'
    ]::text[];
    v_old_case_id constant text :=
        'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
    v_new_case_id constant text :=
        'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
    v_reviewed_at constant timestamptz :=
        timestamptz '2026-08-25T17:01:44.700999+08:00';
    v_corrected_version constant integer := 3;
    v_correction_actor constant text := 'system:migration:0155';
    v_correction_contract constant text :=
        'etc-summary-anomaly-targeted-revalidation-v1';
    relation_row app.workbench_pair_relations%rowtype;
    bank_row app.bank_transactions%rowtype;
    old_decision app.workbench_exception_cases%rowtype;
    current_new_decision app.workbench_exception_cases%rowtype;
    oa_row app.oa_applications%rowtype;
    batch_row app.etc_business_batches%rowtype;
    relation_count integer;
    bank_count integer;
    oa_count integer;
    batch_count integer;
    invoice_detail_count integer;
    invoice_detail_total numeric;
    preferred_invoice_count integer;
    preferred_invoice_total numeric;
    canonical_invoice_contract jsonb;
    preferred_invoice_contract jsonb;
    canonical_invoice_contract_sha256 text;
    preferred_invoice_contract_sha256 text;
    old_count integer;
    new_count integer;
    conflict_count integer;
    correction_event_count integer;
    valid_correction_event_count integer;
    correction_audit_count integer;
    valid_correction_audit_count integer;
    migration_event_count integer;
    valid_migration_event_count integer;
    relation_members text[];
    external_batch_marker text;
    oa_item_contract text[];
    computed_evidence text[];
    computed_fingerprint text;
    old_evidence text[];
    old_codes text[];
    new_evidence text[];
    new_codes text[];
    prior_decision jsonb;
    expected_evidence_contract jsonb;
    expected_v2_payload jsonb;
    normalized_payload jsonb;
    expected_audit_payload jsonb;
    correction_updated_at timestamptz;
begin
    select count(*)::integer
    into relation_count
    from app.workbench_pair_relations relation
    where relation.case_id = v_relation_case_id;

    if relation_count = 0 then
        select count(*)::integer
        into conflict_count
        from (
            select 1
            from app.workbench_exception_cases exception
            where exception.case_id in (v_old_case_id, v_new_case_id)
               or exception.raw_payload#>>'{normalized_payload,group_id}' = v_group_id
            union all
            select 1
            from app.workbench_exception_case_events event
            where event.case_id in (v_old_case_id, v_new_case_id)
               or event.payload->>'case_id' in (v_old_case_id, v_new_case_id)
               or event.raw_payload#>>'{normalized_payload,case_id}'
                    in (v_old_case_id, v_new_case_id)
               or event.payload->>'fingerprint' in (v_old_fingerprint, v_new_fingerprint)
               or event.raw_payload#>>'{normalized_payload,fingerprint}'
                    in (v_old_fingerprint, v_new_fingerprint)
               or event.payload->>'group_id' = v_group_id
               or event.raw_payload#>>'{normalized_payload,group_id}' = v_group_id
               or event.payload->>'target_relation_case_id' = v_relation_case_id
               or event.raw_payload#>>'{normalized_payload,target_relation_case_id}'
                    = v_relation_case_id
            union all
            select 1
            from app.workbench_pair_relation_history history
            where history.case_id = v_relation_case_id
            union all
            select 1
            from audit.events audit
            where audit.request_id = 'migration:0155:CASE-BATCH-txn_imported_1453'
               or audit.object_id in (v_old_case_id, v_new_case_id)
               or audit.payload->>'target_relation_case_id' = v_relation_case_id
               or audit.payload->>'target_exception_case_id' = v_new_case_id
               or audit.payload->>'fingerprint' in (v_old_fingerprint, v_new_fingerprint)
            union all
            select 1 from app.oa_applications oa where oa.row_id = 'oa-exp-2080'
            union all
            select 1
            from app.bank_transactions bank
            where bank.legacy_mongo_id = 'txn_imported_1453'
               or bank.id::text = 'txn_imported_1453'
            union all
            select 1
            from app.etc_business_batches batch
            where batch.business_batch_id = v_business_batch_id
               or coalesce(
                    nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                    nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                    batch.business_batch_id
                  ) = v_external_batch_id
            union all
            select 1
            from app.etc_invoices invoice
            where invoice.business_batch_id in (v_business_batch_id, v_external_batch_id)
            union all
            select 1
            from app.etc_batch_invoice_links link
            left join app.etc_business_batches batch
              on batch.business_batch_id = link.business_batch_id
            where (
                    link.business_batch_id in (v_business_batch_id, v_external_batch_id)
                    or coalesce(
                        nullif(
                            batch.raw_payload->'normalized_payload'
                                ->>'external_etc_batch_id',
                            ''
                        ),
                        nullif(
                            batch.raw_payload->'normalized_payload'
                                ->>'externalEtcBatchId',
                            ''
                        ),
                        nullif(
                            batch.raw_payload->'normalized_payload'
                                ->>'submission_batch_id',
                            ''
                        ),
                        nullif(
                            batch.raw_payload->'normalized_payload'
                                ->>'submissionBatchId',
                            ''
                        ),
                        link.business_batch_id
                    ) = v_external_batch_id
                  )
            union all
            select 1
            from app.etc_submission_batches submission
            where submission.submission_batch_id in (
                    v_external_batch_id,
                    v_business_batch_id
                  )
               or nullif(
                    submission.raw_payload->'normalized_payload'->>'etc_batch_id',
                    ''
                  ) in (v_external_batch_id, v_business_batch_id)
            union all
            select 1
            from app.invoices invoice
            where nullif(
                    invoice.raw_payload->'normalized_payload'
                        ->>'etc_submission_batch_id',
                    ''
                  ) in (v_external_batch_id, v_business_batch_id)
               or nullif(
                    invoice.raw_payload->'normalized_payload'->>'etc_batch_id',
                    ''
                  ) in (v_external_batch_id, v_business_batch_id)
               or nullif(
                    invoice.raw_payload->'normalized_payload'
                        ->>'external_etc_batch_id',
                    ''
                  ) = v_external_batch_id
            union all
            select 1
            from app.workbench_pair_relations relation
            where relation.row_ids && array[
                'oa-exp-2080',
                'txn_imported_1453',
                'etc-summary-ETC-OA-20260413-241125'
            ]::text[]
               or coalesce(
                    nullif(btrim(relation.amount_check->>'external_etc_batch_id'), ''),
                    nullif(btrim(relation.amount_check->>'etc_batch_id'), ''),
                    nullif(btrim(relation.special_metadata->>'external_etc_batch_id'), ''),
                    nullif(btrim(relation.special_metadata->>'etc_batch_id'), ''),
                    nullif(btrim(
                        relation.special_metadata
                            #>>'{etc_batch_link,external_etc_batch_id}'
                    ), ''),
                    nullif(btrim(
                        relation.special_metadata#>>'{etc_batch_link,etc_batch_id}'
                    ), ''),
                    nullif(btrim(
                        relation.special_metadata
                            #>>'{historical_etc_business_batch_migration,external_etc_batch_id}'
                    ), ''),
                    nullif(btrim(
                        relation.special_metadata
                            #>>'{historical_etc_business_batch_migration,etc_batch_id}'
                    ), '')
                  ) = v_external_batch_id
        ) target_anchor;
        if conflict_count <> 0 then
            raise exception '0155: target ETC relation is missing while target state partially exists';
        end if;
        return;
    end if;
    if relation_count <> 1 then
        raise exception '0155: target ETC relation is not unique';
    end if;

    select *
    into strict relation_row
    from app.workbench_pair_relations relation
    where relation.case_id = v_relation_case_id
    for update;

    select coalesce(array_agg(member_key order by member_key), array[]::text[])
    into relation_members
    from (
        select concat(
            case lower(btrim(member.row_type))
                when 'oa_application' then 'oa'
                when 'bank_transaction' then 'bank'
                when 'formal_invoice' then 'invoice'
                when 'input_invoice' then 'invoice'
                when 'output_invoice' then 'invoice'
                when 'etc_summary' then 'invoice'
                when 'etc_invoice_summary' then 'invoice'
                else lower(btrim(member.row_type))
            end,
            ':',
            btrim(member.row_id)
        ) as member_key
        from unnest(relation_row.row_ids, relation_row.row_types)
            as member(row_id, row_type)
    ) normalized_members;

    external_batch_marker := coalesce(
        nullif(btrim(relation_row.amount_check->>'external_etc_batch_id'), ''),
        nullif(btrim(relation_row.amount_check->>'etc_batch_id'), ''),
        nullif(btrim(relation_row.special_metadata->>'external_etc_batch_id'), ''),
        nullif(btrim(relation_row.special_metadata->>'etc_batch_id'), ''),
        nullif(btrim(
            relation_row.special_metadata#>>'{etc_batch_link,external_etc_batch_id}'
        ), ''),
        nullif(btrim(relation_row.special_metadata#>>'{etc_batch_link,etc_batch_id}'), ''),
        nullif(btrim(
            relation_row.special_metadata
                #>>'{historical_etc_business_batch_migration,external_etc_batch_id}'
        ), ''),
        nullif(btrim(
            relation_row.special_metadata
                #>>'{historical_etc_business_batch_migration,etc_batch_id}'
        ), '')
    );

    if relation_row.status is distinct from 'active'
       or relation_row.relation_mode is distinct from 'batch_accounting'
       or relation_row.month_scope is distinct from v_scope_month
       or relation_members is distinct from v_expected_members
       or external_batch_marker is distinct from v_external_batch_id
       or relation_row.amount_check->>'status' is distinct from 'matched'
       or relation_row.amount_check->>'oa_total' is distinct from '2411.25'
       or relation_row.amount_check->>'bank_total' is distinct from '2411.25'
       or relation_row.amount_check->>'invoice_total' is distinct from '2411.25'
       or relation_row.amount_check->>'amount_delta' is distinct from '0.00'
       or relation_row.updated_at is null
       or relation_row.withdrawn_by is not null
       or relation_row.withdrawn_at is not null then
        raise exception '0155: target ETC relation differs from the authorized correction contract';
    end if;

    select count(*)::integer
    into bank_count
    from app.bank_transactions bank
    where bank.legacy_mongo_id = 'txn_imported_1453'
       or bank.id::text = 'txn_imported_1453';
    if bank_count <> 1 then
        raise exception '0155: target bank transaction identity is not unique';
    end if;

    select *
    into strict bank_row
    from app.bank_transactions bank
    where bank.legacy_mongo_id = 'txn_imported_1453'
       or bank.id::text = 'txn_imported_1453'
    for share;

    if bank_row.legacy_mongo_id is distinct from 'txn_imported_1453'
       or bank_row.status = 'deleted'
       or bank_row.txn_month is distinct from v_scope_month
       or bank_row.txn_direction is distinct from 'outflow'
       or round(bank_row.amount, 2) is distinct from v_expected_invoice_total then
        raise exception '0155: target bank transaction differs from the authorized correction contract';
    end if;

    select count(*)::integer
    into batch_count
    from app.etc_business_batches batch
    where batch.business_batch_id = v_business_batch_id
       or coalesce(
            nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            batch.business_batch_id
          ) = v_external_batch_id;
    if batch_count <> 1 then
        raise exception '0155: target canonical ETC summary owner is not unique';
    end if;

    select *
    into strict batch_row
    from app.etc_business_batches batch
    where batch.business_batch_id = v_business_batch_id
    for share;

    select count(*)::integer,
           round(coalesce(sum(coalesce(invoice.total_with_tax, invoice.amount)), 0), 2)
    into invoice_detail_count, invoice_detail_total
    from app.etc_invoices invoice
    where invoice.business_batch_id = v_business_batch_id
      and invoice.status <> 'deleted';

    if batch_row.status is distinct from 'manually_marked_submitted'
       or batch_row.scope_month is distinct from v_scope_month
       or batch_row.invoice_count is distinct from v_expected_invoice_count
       or round(batch_row.total_amount, 2) is distinct from v_expected_invoice_total
       or coalesce(
            nullif(batch_row.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
            nullif(batch_row.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
            nullif(batch_row.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
            nullif(batch_row.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
            batch_row.business_batch_id
          ) is distinct from v_external_batch_id
       or jsonb_array_length(
            case
                when jsonb_typeof(
                    batch_row.raw_payload#>'{normalized_payload,invoice_ids}'
                ) = 'array'
                    then batch_row.raw_payload#>'{normalized_payload,invoice_ids}'
                else '[]'::jsonb
            end
          ) is distinct from v_expected_invoice_count
       or invoice_detail_count is distinct from v_expected_invoice_count
       or invoice_detail_total is distinct from v_expected_invoice_total then
        raise exception '0155: target canonical ETC summary differs from the authorized correction contract';
    end if;

    with runtime_source_rows as (
        select
            2 as source_rank,
            coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                batch.business_batch_id
            ) as external_batch_id,
            coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text)
                as row_id,
            coalesce(
                nullif(invoice.invoice_no, ''),
                coalesce(invoice.legacy_mongo_id, invoice.etc_invoice_id, invoice.id::text)
            ) as invoice_identity,
            coalesce(invoice.total_with_tax, invoice.amount) as invoice_amount
        from app.etc_business_batches batch
        join app.etc_invoices invoice
          on invoice.business_batch_id = batch.business_batch_id
         and invoice.status <> 'deleted'
        where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
        union all
        select
            1,
            coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                link.business_batch_id
            ),
            coalesce(invoice.legacy_mongo_id, invoice.id::text),
            coalesce(
                nullif(invoice.digital_invoice_no, ''),
                nullif(invoice.invoice_no, ''),
                coalesce(invoice.legacy_mongo_id, invoice.id::text)
            ),
            coalesce(invoice.total_with_tax, invoice.amount)
        from app.etc_batch_invoice_links link
        join app.invoices invoice on invoice.id = link.invoice_id
        left join app.etc_business_batches batch
          on batch.business_batch_id = link.business_batch_id
        where link.link_status = 'active'
          and invoice.status <> 'deleted'
        union all
        select
            3,
            coalesce(
                nullif(submission.raw_payload->'normalized_payload'->>'etc_batch_id', ''),
                submission.submission_batch_id
            ),
            coalesce(invoice.legacy_mongo_id, invoice.id::text),
            coalesce(
                nullif(invoice.digital_invoice_no, ''),
                nullif(invoice.invoice_no, ''),
                coalesce(invoice.legacy_mongo_id, invoice.id::text)
            ),
            coalesce(invoice.total_with_tax, invoice.amount)
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
          and (
              invoice.workbench_visibility = 'hidden_after_etc_submission'
              or invoice.raw_payload->'normalized_payload'->>'workbench_visibility'
                  = 'hidden_after_etc_submission'
              or invoice.raw_payload->'normalized_payload'->>'etc_submission_status'
                  = 'submitted'
          )
    ), runtime_preferred_rows as (
        select
            source.*,
            case when source.source_rank in (1, 2) then 1 else 2 end as source_tier,
            row_number() over (
                partition by source.external_batch_id, source.invoice_identity
                order by source.source_rank, source.row_id
            ) as identity_rank,
            min(case when source.source_rank in (1, 2) then 1 else 2 end) over (
                partition by source.external_batch_id
            ) as preferred_source_tier
        from runtime_source_rows source
        where source.external_batch_id = v_external_batch_id
    ), canonical_runtime_facts as (
        select
            coalesce(
                jsonb_agg(
                    jsonb_build_array(source.invoice_identity, source.invoice_amount)
                    order by source.invoice_identity, source.row_id
                ),
                '[]'::jsonb
            ) as invoice_contract,
            encode(digest(convert_to(string_agg(
                octet_length(source.invoice_identity)::text
                    || ':' || source.invoice_identity
                    || ':' || to_char(
                        round(source.invoice_amount, 2),
                        'FM999999999999999999990.00'
                    ),
                E'\n' order by source.invoice_identity, source.row_id
            ), 'UTF8'), 'sha256'), 'hex') as invoice_contract_sha256
        from runtime_source_rows source
        where source.external_batch_id = v_external_batch_id
          and source.source_rank = 2
    ), preferred_runtime_facts as (
        select
            count(*)::integer as invoice_count,
            round(coalesce(sum(preferred.invoice_amount), 0), 2) as invoice_total,
            coalesce(
                jsonb_agg(
                    jsonb_build_array(
                        preferred.invoice_identity,
                        preferred.invoice_amount
                    )
                    order by preferred.invoice_identity, preferred.row_id
                ),
                '[]'::jsonb
            ) as invoice_contract,
            encode(digest(convert_to(string_agg(
                octet_length(preferred.invoice_identity)::text
                    || ':' || preferred.invoice_identity
                    || ':' || to_char(
                        round(preferred.invoice_amount, 2),
                        'FM999999999999999999990.00'
                    ),
                E'\n' order by preferred.invoice_identity, preferred.row_id
            ), 'UTF8'), 'sha256'), 'hex') as invoice_contract_sha256
        from runtime_preferred_rows preferred
        where preferred.source_tier = preferred.preferred_source_tier
          and preferred.identity_rank = 1
    )
    select
        preferred.invoice_count,
        preferred.invoice_total,
        canonical.invoice_contract,
        preferred.invoice_contract,
        canonical.invoice_contract_sha256,
        preferred.invoice_contract_sha256
    into
        preferred_invoice_count,
        preferred_invoice_total,
        canonical_invoice_contract,
        preferred_invoice_contract,
        canonical_invoice_contract_sha256,
        preferred_invoice_contract_sha256
    from preferred_runtime_facts preferred
    cross join canonical_runtime_facts canonical;

    if preferred_invoice_count is distinct from v_expected_invoice_count
       or preferred_invoice_total is distinct from v_expected_invoice_total
       or canonical_invoice_contract_sha256
            is distinct from v_expected_invoice_contract_sha256
       or preferred_invoice_contract_sha256
            is distinct from v_expected_invoice_contract_sha256
       or preferred_invoice_contract is distinct from canonical_invoice_contract then
        raise exception '0155: runtime preferred ETC summary differs from the authorized correction contract';
    end if;

    select count(*)::integer
    into oa_count
    from app.oa_applications oa
    where oa.row_id = 'oa-exp-2080';
    if oa_count <> 1 then
        raise exception '0155: target OA source is not unique';
    end if;

    select *
    into strict oa_row
    from app.oa_applications oa
    where oa.row_id = 'oa-exp-2080'
    for share;

    select coalesce(array_agg(item_contract order by item_contract), array[]::text[])
    into oa_item_contract
    from (
        select concat_ws(
            '|',
            identity.identity_count::text,
            coalesce(identity.item_id, '<missing>'),
            coalesce(item.value->>'row_index', '<missing>'),
            case
                when replace(coalesce(
                    item.value->>'amount',
                    item.value->>'settlement_amount',
                    item.value->>'total_with_tax'
                ), ',', '') ~ '^[+-]?[0-9]+([.][0-9]+)?$'
                    then to_char(round(replace(coalesce(
                        item.value->>'amount',
                        item.value->>'settlement_amount',
                        item.value->>'total_with_tax'
                    ), ',', '')::numeric, 2), 'FM999999999999999999990.00')
                else '<invalid>'
            end,
            case
                when coalesce(item.value->>'attachment_file_count', '') ~ '^[0-9]+$'
                    then greatest(0, (item.value->>'attachment_file_count')::integer)::text
                else '<invalid>'
            end
        ) as item_contract
        from jsonb_array_elements(
            case
                when jsonb_typeof(oa_row.normalized_payload->'expense_items') = 'array'
                    then oa_row.normalized_payload->'expense_items'
                else '[]'::jsonb
            end
        ) item(value)
        cross join lateral (
            select count(distinct item_identity.value)::integer as identity_count,
                   min(item_identity.value) as item_id
            from (values
                (nullif(btrim(item.value->>'id'), '')),
                (nullif(btrim(item.value->>'row_id'), '')),
                (nullif(btrim(item.value->>'expense_item_id'), ''))
            ) item_identity(value)
            where item_identity.value is not null
        ) identity
    ) normalized_items;

    if oa_row.status = 'deleted'
       or oa_row.workflow_status is distinct from 'completed'
       or oa_row.scope_month is distinct from v_scope_month
       or round(oa_row.amount, 2) is distinct from 2411.25::numeric
       or oa_item_contract is distinct from v_expected_oa_items then
        raise exception '0155: target OA evidence differs from the authorized correction contract';
    end if;

    select array_agg(fingerprint order by fingerprint)
    into computed_evidence
    from (
        select encode(digest(
            convert_to(v_relation_case_id, 'UTF8') || decode('00', 'hex') ||
            convert_to('oa_invoice_attachment_absent', 'UTF8') || decode('00', 'hex') ||
            convert_to(expected.item_id, 'UTF8') || decode('00', 'hex') ||
            convert_to(expected.amount, 'UTF8') || decode('00', 'hex') ||
            decode('00', 'hex') ||
            decode('00', 'hex') ||
            convert_to('0', 'UTF8'),
            'sha256'
        ), 'hex') as fingerprint
        from (values
            ('oa-exp-2080:item:0:63f422ef26de', '2169.68'),
            ('oa-exp-2080:item:1:3b08cbfe865a', '241.57')
        ) expected(item_id, amount)
    ) evidence;
    select encode(digest(
        convert_to(v_relation_case_id, 'UTF8') || decode('00', 'hex') ||
        convert_to(computed_evidence[1], 'UTF8') || decode('00', 'hex') ||
        convert_to(computed_evidence[2], 'UTF8'),
        'sha256'
    ), 'hex')
    into computed_fingerprint;
    if computed_evidence is distinct from v_remaining_evidence
       or computed_fingerprint is distinct from v_new_fingerprint then
        raise exception '0155: fixed anomaly fingerprint contract is internally inconsistent';
    end if;

    expected_evidence_contract := jsonb_build_array(
        jsonb_build_object(
            'fingerprint', v_remaining_evidence[1],
            'code', 'oa_invoice_attachment_absent',
            'comparison_unit_id', 'oa-exp-2080:item:0:63f422ef26de',
            'source_oa_ids', jsonb_build_array('oa-exp-2080'),
            'invoice_row_ids', '[]'::jsonb,
            'row_index', 0,
            'oa_total', '2169.68',
            'attachment_file_count', 0,
            'display_scope', 'expense_item',
            'display_pane', 'oa'
        ),
        jsonb_build_object(
            'fingerprint', v_remaining_evidence[2],
            'code', 'oa_invoice_attachment_absent',
            'comparison_unit_id', 'oa-exp-2080:item:1:3b08cbfe865a',
            'source_oa_ids', jsonb_build_array('oa-exp-2080'),
            'invoice_row_ids', '[]'::jsonb,
            'row_index', 1,
            'oa_total', '241.57',
            'attachment_file_count', 0,
            'display_scope', 'expense_item',
            'display_pane', 'oa'
        )
    );

    select count(*)::integer
    into conflict_count
    from app.workbench_exception_cases exception
    where exception.raw_payload#>>'{normalized_payload,group_id}' = v_group_id
      and exception.case_id not in (v_old_case_id, v_new_case_id);
    if conflict_count <> 0 then
        raise exception '0155: another current decision exists for the target ETC group';
    end if;

    select count(*)::integer
    into conflict_count
    from app.workbench_exception_case_events event
    where (
            event.case_id in (v_old_case_id, v_new_case_id)
            or event.payload->>'group_id' = v_group_id
            or event.raw_payload#>>'{normalized_payload,group_id}' = v_group_id
          )
      and (
            event.event_type = 'workbench_anomaly_acceptance_withdrawn'
            or event.payload->>'decision' = 'keep_unpaired'
            or event.raw_payload#>>'{normalized_payload,decision}' = 'keep_unpaired'
          );
    if conflict_count <> 0 then
        raise exception '0155: a target anomaly acceptance withdrawal exists';
    end if;

    select count(*)::integer
    into old_count
    from app.workbench_exception_cases exception
    where exception.case_id = v_old_case_id;
    if old_count > 1 then
        raise exception '0155: old ETC anomaly review decision is not unique';
    end if;
    if old_count = 1 then
        select *
        into strict old_decision
        from app.workbench_exception_cases exception
        where exception.case_id = v_old_case_id
        for update;

        select coalesce(array_agg(evidence.value order by evidence.value), array[]::text[])
        into old_evidence
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    old_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                ) = 'array'
                    then old_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                else '[]'::jsonb
            end
        ) evidence(value);
        select coalesce(array_agg(code.value order by code.value), array[]::text[])
        into old_codes
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    old_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                ) = 'array'
                    then old_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                else '[]'::jsonb
            end
        ) code(value);

        if old_decision.status is distinct from 'resolved'
           or old_decision.resolution is distinct from 'accept_paired'
           or old_decision.version is distinct from 1
           or old_decision.business_line is distinct from 'reconciliation_workbench'
           or old_decision.scenario is distinct from 'workbench_anomaly_review'
           or old_decision.scope_month is distinct from v_scope_month
           or old_decision.row_ids is distinct from array[]::text[]
           or old_decision.candidate_ids is distinct from array[]::text[]
           or old_decision.updated_by is distinct from '8'
           or old_decision.updated_at is distinct from v_reviewed_at
           or old_decision.raw_payload#>>'{normalized_payload,case_id}'
                is distinct from v_old_case_id
           or old_decision.raw_payload#>>'{normalized_payload,status}'
                is distinct from 'resolved'
           or old_decision.raw_payload#>>'{normalized_payload,version}'
                is distinct from '1'
           or old_decision.raw_payload#>>'{normalized_payload,business_line}'
                is distinct from 'reconciliation_workbench'
           or old_decision.raw_payload#>>'{normalized_payload,scenario_code}'
                is distinct from 'workbench_anomaly_review'
           or old_decision.raw_payload#>>'{normalized_payload,scope_month}'
                is distinct from '2026-04'
           or old_decision.raw_payload#>>'{normalized_payload,updated_by}'
                is distinct from '8'
           or old_decision.raw_payload#>'{normalized_payload,row_ids}'
                is distinct from '[]'::jsonb
           or old_decision.raw_payload#>'{normalized_payload,candidate_ids}'
                is distinct from '[]'::jsonb
           or old_decision.raw_payload#>>'{normalized_payload,fingerprint}'
                is distinct from v_old_fingerprint
           or old_decision.raw_payload#>>'{normalized_payload,group_id}'
                is distinct from v_group_id
           or old_decision.raw_payload#>>'{normalized_payload,decision}'
                is distinct from 'accept_paired'
           or old_evidence is distinct from v_expected_old_evidence
           or old_codes is distinct from array[
                'oa_invoice_attachment_absent',
                'oa_invoice_attachment_unassigned'
           ]::text[] then
            raise exception '0155: old ETC anomaly review decision conflicts with the authorized correction';
        end if;
    end if;

    select count(*)::integer
    into new_count
    from app.workbench_exception_cases exception
    where exception.case_id = v_new_case_id;
    if new_count > 1 then
        raise exception '0155: current ETC anomaly review decision is not unique';
    end if;

    select count(*)::integer
    into correction_event_count
    from app.workbench_exception_case_events event
    where (
          event.case_id in (v_old_case_id, v_new_case_id)
          or event.exception_case_id in (
                select exception.id
                from app.workbench_exception_cases exception
                where exception.case_id in (v_old_case_id, v_new_case_id)
          )
          or event.payload->>'target_relation_case_id' = v_relation_case_id
          or event.raw_payload#>>'{normalized_payload,target_relation_case_id}'
              = v_relation_case_id
      )
      and (
          event.event_type = 'workbench_anomaly_review_system_corrected'
          or event.actor_id = v_correction_actor
          or event.payload->>'correction_contract' = v_correction_contract
          or event.raw_payload#>>'{normalized_payload,correction_contract}'
              = v_correction_contract
      );
    select count(*)::integer
    into correction_audit_count
    from audit.events audit
    where audit.request_id = 'migration:0155:CASE-BATCH-txn_imported_1453'
       or (
            (
                audit.object_id in (v_old_case_id, v_new_case_id)
                or audit.payload->>'target_relation_case_id' = v_relation_case_id
            )
            and (
                audit.event_type = 'workbench.anomaly_review.system_corrected'
                or audit.actor_id = v_correction_actor
                or audit.payload->>'contract_revision' = v_correction_contract
            )
       );

    if new_count = 0
       and (correction_event_count <> 0 or correction_audit_count <> 0) then
        raise exception '0155: system correction audit exists without the target decision';
    end if;
    if new_count = 1 then
        select *
        into strict current_new_decision
        from app.workbench_exception_cases exception
        where exception.case_id = v_new_case_id
        for update;

        select coalesce(array_agg(evidence.value order by evidence.value), array[]::text[])
        into new_evidence
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    current_new_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                ) = 'array'
                    then current_new_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                else '[]'::jsonb
            end
        ) evidence(value);
        select coalesce(array_agg(code.value order by code.value), array[]::text[])
        into new_codes
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    current_new_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                ) = 'array'
                    then current_new_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                else '[]'::jsonb
            end
        ) code(value);

        if current_new_decision.status is distinct from 'resolved'
           or current_new_decision.resolution is distinct from 'accept_paired'
           or current_new_decision.version not in (2, v_corrected_version)
           or current_new_decision.business_line is distinct from 'reconciliation_workbench'
           or current_new_decision.scenario is distinct from 'workbench_anomaly_review'
           or current_new_decision.scope_month is distinct from v_scope_month
           or current_new_decision.row_ids is distinct from array[]::text[]
           or current_new_decision.candidate_ids is distinct from array[]::text[]
           or current_new_decision.raw_payload#>>'{normalized_payload,case_id}'
                is distinct from v_new_case_id
           or current_new_decision.raw_payload#>>'{normalized_payload,status}'
                is distinct from 'resolved'
           or current_new_decision.raw_payload#>>'{normalized_payload,version}'
                is distinct from current_new_decision.version::text
           or current_new_decision.raw_payload#>>'{normalized_payload,business_line}'
                is distinct from 'reconciliation_workbench'
           or current_new_decision.raw_payload#>>'{normalized_payload,scenario_code}'
                is distinct from 'workbench_anomaly_review'
           or current_new_decision.raw_payload#>>'{normalized_payload,scope_month}'
                is distinct from '2026-04'
           or current_new_decision.raw_payload#>>'{normalized_payload,fingerprint}'
                is distinct from v_new_fingerprint
           or current_new_decision.raw_payload#>>'{normalized_payload,group_id}'
                is distinct from v_group_id
           or current_new_decision.raw_payload#>>'{normalized_payload,decision}'
                is distinct from 'accept_paired'
           or current_new_decision.raw_payload#>'{normalized_payload,row_ids}'
                is distinct from '[]'::jsonb
           or current_new_decision.raw_payload#>'{normalized_payload,candidate_ids}'
                is distinct from '[]'::jsonb
           or new_evidence is distinct from v_remaining_evidence
           or new_codes is distinct from array['oa_invoice_attachment_absent']::text[]
           or (
                current_new_decision.version = 2
                and (
                    current_new_decision.updated_by is distinct from '8'
                    or current_new_decision.updated_at is distinct from v_reviewed_at
                    or current_new_decision.raw_payload#>>'{normalized_payload,updated_by}'
                        is distinct from '8'
                    or current_new_decision.raw_payload#>>'{normalized_payload,migration_contract}'
                        is distinct from 'etc-summary-unassigned-removal-v1'
                    or current_new_decision.raw_payload#>>'{normalized_payload,migrated_by}'
                        is distinct from 'system:migration:0154'
                    or current_new_decision.raw_payload#>>'{normalized_payload,migrated_from_fingerprint}'
                        is distinct from v_old_fingerprint
                    or current_new_decision.raw_payload#>>'{normalized_payload,removed_evidence_fingerprint}'
                        is distinct from v_removed_evidence
                )
           )
           or (
                current_new_decision.version = v_corrected_version
                and (
                    current_new_decision.updated_by is distinct from v_correction_actor
                    or current_new_decision.raw_payload#>>'{normalized_payload,updated_by}'
                        is distinct from v_correction_actor
                    or current_new_decision.raw_payload#>>'{normalized_payload,correction_contract}'
                        is distinct from v_correction_contract
                    or current_new_decision.raw_payload#>>'{normalized_payload,correction_reason}'
                        is distinct from 'exact_system_targeted_correction'
                    or current_new_decision.raw_payload#>>'{normalized_payload,target_relation_case_id}'
                        is distinct from v_relation_case_id
                    or current_new_decision.raw_payload#>>'{normalized_payload,target_external_etc_batch_id}'
                        is distinct from v_external_batch_id
                    or (
                        current_new_decision.raw_payload
                            #>>'{normalized_payload,effective_relation_updated_at}'
                       )::timestamptz is distinct from relation_row.updated_at
                    or (
                        current_new_decision.raw_payload
                            #>>'{normalized_payload,system_correction_updated_at}'
                       )::timestamptz is distinct from current_new_decision.updated_at
                    or current_new_decision.raw_payload
                            #>>'{normalized_payload,canonical_etc_summary_contract,business_batch_id}'
                        is distinct from v_business_batch_id
                    or current_new_decision.raw_payload
                            #>>'{normalized_payload,canonical_etc_summary_contract,external_etc_batch_id}'
                        is distinct from v_external_batch_id
                    or current_new_decision.raw_payload
                            #>>'{normalized_payload,canonical_etc_summary_contract,detail_count}'
                        is distinct from v_expected_invoice_count::text
                    or current_new_decision.raw_payload
                            #>>'{normalized_payload,canonical_etc_summary_contract,invoice_total}'
                        is distinct from '2411.25'
                    or current_new_decision.raw_payload#>'{normalized_payload,evidence_contract}'
                        is distinct from expected_evidence_contract
                    or current_new_decision.raw_payload#>>'{normalized_payload,migrated_from_fingerprint}'
                        is distinct from v_old_fingerprint
                    or current_new_decision.raw_payload#>>'{normalized_payload,removed_evidence_fingerprint}'
                        is distinct from v_removed_evidence
                )
           ) then
            raise exception '0155: current ETC anomaly review decision conflicts with the authorized correction';
        end if;

        if current_new_decision.version = 2 then
            if old_count <> 1 then
                raise exception '0155: exact v2 migration lineage is missing the old reviewed decision';
            end if;
            expected_v2_payload := jsonb_build_object(
                'case_id', v_new_case_id,
                'status', 'resolved',
                'version', 2,
                'business_line', 'reconciliation_workbench',
                'scenario_code', 'workbench_anomaly_review',
                'fingerprint', v_new_fingerprint,
                'group_id', v_group_id,
                'scope_month', '2026-04',
                'decision', 'accept_paired',
                'note', coalesce(
                    old_decision.raw_payload#>>'{normalized_payload,note}',
                    ''
                ),
                'detected_classification_codes',
                    jsonb_build_array('oa_invoice_attachment_absent'),
                'evidence_item_fingerprints', to_jsonb(v_remaining_evidence),
                'row_ids', '[]'::jsonb,
                'candidate_ids', '[]'::jsonb,
                'updated_by', '8',
                'migration_contract', 'etc-summary-unassigned-removal-v1',
                'migrated_from_fingerprint', v_old_fingerprint,
                'removed_evidence_fingerprint', v_removed_evidence,
                'migrated_by', 'system:migration:0154'
            );
            if current_new_decision.created_by is distinct from old_decision.created_by
               or current_new_decision.created_at is distinct from old_decision.created_at
               or current_new_decision.raw_payload is distinct from jsonb_build_object(
                    'normalized_payload',
                    expected_v2_payload
               ) then
                raise exception '0155: exact v2 decision conflicts with the 0154 generated contract';
            end if;

            select count(*)::integer
            into migration_event_count
            from app.workbench_exception_case_events event
            where (
                    event.exception_case_id = current_new_decision.id
                    or event.case_id = v_new_case_id
                    or event.payload->>'case_id' = v_new_case_id
                    or event.raw_payload#>>'{normalized_payload,case_id}' = v_new_case_id
                    or event.payload->>'fingerprint' = v_new_fingerprint
                    or event.raw_payload#>>'{normalized_payload,fingerprint}'
                        = v_new_fingerprint
                    or event.payload->>'group_id' = v_group_id
                    or event.raw_payload#>>'{normalized_payload,group_id}' = v_group_id
                  )
              and (
                    event.event_type = 'workbench_anomaly_review_migrated'
                    or event.actor_id = 'system:migration:0154'
                    or event.payload->>'migration_contract'
                        = 'etc-summary-unassigned-removal-v1'
                    or event.raw_payload#>>'{normalized_payload,migration_contract}'
                        = 'etc-summary-unassigned-removal-v1'
                  );
            select count(*)::integer
            into valid_migration_event_count
            from app.workbench_exception_case_events event
            where event.exception_case_id = current_new_decision.id
              and event.case_id = v_new_case_id
              and event.event_type = 'workbench_anomaly_review_migrated'
              and event.actor_id = 'system:migration:0154'
              and event.occurred_at >= v_reviewed_at
              and event.payload = expected_v2_payload
              and event.raw_payload = jsonb_build_object(
                    'normalized_payload',
                    expected_v2_payload
              )
              and event.payload = current_new_decision.raw_payload->'normalized_payload'
              and event.raw_payload = current_new_decision.raw_payload;
            if migration_event_count <> 1 or valid_migration_event_count <> 1 then
                raise exception '0155: exact v2 migration lineage event is missing or conflicting';
            end if;
            if correction_event_count <> 0 or correction_audit_count <> 0 then
                raise exception '0155: system correction audit conflicts with the exact v2 decision';
            end if;
            if current_new_decision.updated_at >= relation_row.updated_at
               and (old_count = 0 or current_new_decision.updated_at >= old_decision.updated_at) then
                return;
            end if;
        else
            expected_audit_payload := jsonb_build_object(
                'contract_revision', v_correction_contract,
                'summary', '固定 ETC 异常审阅已按当前关系版本重验证',
                'target_relation_case_id', v_relation_case_id,
                'target_exception_case_id', v_new_case_id,
                'fingerprint', v_new_fingerprint,
                'decision', 'accept_paired',
                'effective_relation_updated_at', relation_row.updated_at,
                'system_correction_updated_at', current_new_decision.updated_at,
                'evidence_item_fingerprints', to_jsonb(v_remaining_evidence),
                'canonical_etc_summary_contract', jsonb_build_object(
                    'business_batch_id', v_business_batch_id,
                    'external_etc_batch_id', v_external_batch_id,
                    'detail_count', v_expected_invoice_count,
                    'invoice_total', '2411.25'
                )
            );
            select count(*)::integer
            into valid_correction_event_count
            from app.workbench_exception_case_events event
            where event.case_id = v_new_case_id
              and event.exception_case_id = current_new_decision.id
              and event.event_type = 'workbench_anomaly_review_system_corrected'
              and event.actor_id = v_correction_actor
              and event.payload = current_new_decision.raw_payload->'normalized_payload'
              and event.raw_payload = current_new_decision.raw_payload;
            select count(*)::integer
            into valid_correction_audit_count
            from audit.events audit
            where audit.event_type = 'workbench.anomaly_review.system_corrected'
              and audit.object_type = 'workbench_exception_case'
              and audit.object_id = v_new_case_id
              and audit.actor_id = v_correction_actor
              and audit.action = 'workbench.exception.review.system_correction'
              and audit.page_key = 'reconciliation-workbench'
              and audit.operation_location = 'database_migration'
              and audit.reason = '对固定 ETC 关系和两条真实缺附件证据执行经授权的系统重验证'
              and audit.outcome = 'success'
              and audit.request_id = 'migration:0155:CASE-BATCH-txn_imported_1453'
              and audit.payload = expected_audit_payload
              and audit.raw_payload = '{}'::jsonb;
            if correction_event_count <> 1
               or valid_correction_event_count <> 1
               or correction_audit_count <> 1
               or valid_correction_audit_count <> 1 then
                raise exception '0155: exact v3 decision has incomplete or conflicting system correction audit';
            end if;
            if current_new_decision.updated_at < relation_row.updated_at
               or (old_count = 1 and current_new_decision.updated_at < old_decision.updated_at) then
                raise exception '0155: exact v3 system correction is stale';
            end if;
            return;
        end if;
    end if;

    correction_updated_at := greatest(
        relation_row.updated_at,
        case
            when old_count = 1 then old_decision.updated_at
            else relation_row.updated_at
        end,
        case
            when new_count = 1 then current_new_decision.updated_at
            else relation_row.updated_at
        end
    ) + interval '1 microsecond';

    prior_decision := case
        when new_count = 1 then jsonb_build_object(
            'case_id', current_new_decision.case_id,
            'version', current_new_decision.version,
            'updated_by', current_new_decision.updated_by,
            'updated_at', current_new_decision.updated_at
        )
        when old_count = 1 then jsonb_build_object(
            'case_id', old_decision.case_id,
            'version', old_decision.version,
            'updated_by', old_decision.updated_by,
            'updated_at', old_decision.updated_at
        )
        else null
    end;
    normalized_payload := jsonb_strip_nulls(jsonb_build_object(
        'case_id', v_new_case_id,
        'status', 'resolved',
        'version', v_corrected_version,
        'business_line', 'reconciliation_workbench',
        'scenario_code', 'workbench_anomaly_review',
        'fingerprint', v_new_fingerprint,
        'group_id', v_group_id,
        'scope_month', '2026-04',
        'decision', 'accept_paired',
        'note', case
            when new_count = 1
                then coalesce(current_new_decision.raw_payload#>>'{normalized_payload,note}', '')
            when old_count = 1
                then coalesce(old_decision.raw_payload#>>'{normalized_payload,note}', '')
            else ''
        end,
        'detected_classification_codes', jsonb_build_array('oa_invoice_attachment_absent'),
        'evidence_item_fingerprints', to_jsonb(v_remaining_evidence),
        'evidence_contract', expected_evidence_contract,
        'row_ids', '[]'::jsonb,
        'candidate_ids', '[]'::jsonb,
        'updated_by', v_correction_actor,
        'effective_relation_updated_at', relation_row.updated_at,
        'system_correction_updated_at', correction_updated_at,
        'target_relation_case_id', v_relation_case_id,
        'target_external_etc_batch_id', v_external_batch_id,
        'canonical_etc_summary_contract', jsonb_build_object(
            'business_batch_id', v_business_batch_id,
            'external_etc_batch_id', v_external_batch_id,
            'detail_count', v_expected_invoice_count,
            'invoice_total', to_char(v_expected_invoice_total, 'FM999999999999999999990.00')
        ),
        'correction_contract', v_correction_contract,
        'correction_reason', 'exact_system_targeted_correction',
        'migrated_from_fingerprint', v_old_fingerprint,
        'removed_evidence_fingerprint', v_removed_evidence,
        'prior_decision', prior_decision
    ));
    expected_audit_payload := jsonb_build_object(
        'contract_revision', v_correction_contract,
        'summary', '固定 ETC 异常审阅已按当前关系版本重验证',
        'target_relation_case_id', v_relation_case_id,
        'target_exception_case_id', v_new_case_id,
        'fingerprint', v_new_fingerprint,
        'decision', 'accept_paired',
        'effective_relation_updated_at', relation_row.updated_at,
        'system_correction_updated_at', correction_updated_at,
        'evidence_item_fingerprints', to_jsonb(v_remaining_evidence),
        'canonical_etc_summary_contract', jsonb_build_object(
            'business_batch_id', v_business_batch_id,
            'external_etc_batch_id', v_external_batch_id,
            'detail_count', v_expected_invoice_count,
            'invoice_total', '2411.25'
        )
    );

    if new_count = 0 then
        insert into app.workbench_exception_cases(
            case_id, status, resolution, version, business_line, scenario, scope_month,
            row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
        ) values (
            v_new_case_id, 'resolved', 'accept_paired', v_corrected_version,
            'reconciliation_workbench', 'workbench_anomaly_review', v_scope_month,
            array[]::text[], array[]::text[], v_correction_actor, correction_updated_at,
            v_correction_actor, correction_updated_at,
            jsonb_build_object('normalized_payload', normalized_payload)
        );
    else
        update app.workbench_exception_cases
        set status = 'resolved',
            resolution = 'accept_paired',
            version = v_corrected_version,
            business_line = 'reconciliation_workbench',
            scenario = 'workbench_anomaly_review',
            scope_month = v_scope_month,
            row_ids = array[]::text[],
            candidate_ids = array[]::text[],
            updated_by = v_correction_actor,
            updated_at = correction_updated_at,
            raw_payload = jsonb_build_object('normalized_payload', normalized_payload)
        where case_id = v_new_case_id;
    end if;

    insert into app.workbench_exception_case_events(
        exception_case_id, case_id, event_type, actor_id, payload, raw_payload
    ) values (
        (select id from app.workbench_exception_cases where case_id = v_new_case_id),
        v_new_case_id,
        'workbench_anomaly_review_system_corrected',
        v_correction_actor,
        normalized_payload,
        jsonb_build_object('normalized_payload', normalized_payload)
    );

    insert into audit.events(
        event_type, object_type, object_id, actor_id, action, page_key,
        operation_location, reason, outcome, request_id, payload, raw_payload
    ) values (
        'workbench.anomaly_review.system_corrected',
        'workbench_exception_case',
        v_new_case_id,
        v_correction_actor,
        'workbench.exception.review.system_correction',
        'reconciliation-workbench',
        'database_migration',
        '对固定 ETC 关系和两条真实缺附件证据执行经授权的系统重验证',
        'success',
        'migration:0155:CASE-BATCH-txn_imported_1453',
        expected_audit_payload,
        '{}'::jsonb
    );
end $$;
