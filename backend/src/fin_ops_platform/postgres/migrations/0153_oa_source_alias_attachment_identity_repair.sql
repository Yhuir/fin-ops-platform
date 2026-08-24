set local lock_timeout = '10s';
set local statement_timeout = '1min';

do $$
declare
    v_alias_row_id constant text := 'oa-exp-2327';
    v_canonical_row_id constant text := 'oa-exp-6a86a63777bca2d0c5f62d07';
    v_expected_legacy_item_ids constant text[] := array[
        'oa-exp-2327:item:0:d91d8bb509c9',
        'oa-exp-2327:item:1:a48a5229fa61'
    ]::text[];
    v_expected_current_item_ids constant text[] := array[
        'oa-exp-6a86a63777bca2d0c5f62d07:item:0:f45376305de2',
        'oa-exp-6a86a63777bca2d0c5f62d07:item:1:32417101b6eb'
    ]::text[];
    canonical_count integer;
    alias_application_count integer;
    existing_alias_count integer;
    existing_canonical_row_id text;
    existing_status text;
    invoice_source_link_count integer;
    matched_invoice_attachment_count integer;
    current_item_ids text[];
    bridge_item_ids text[];
    matched_current_item_ids text[];
    attachment_key_hashes text[];
    invoice_attachment_key_hashes text[];
    invoice_ids text[];
    invoice_item_ids text[];
    evidence_mappings text[];
    evidence_hash text;
begin
    select count(*)::integer
    into canonical_count
    from app.oa_applications oa
    where oa.row_id = v_canonical_row_id
      and oa.status <> 'deleted';

    -- Fresh and unrelated databases must remain unchanged.
    if canonical_count = 0 then
        return;
    end if;
    if canonical_count <> 1 then
        raise exception '0153: canonical OA row was not found exactly once';
    end if;

    select count(*)::integer
    into alias_application_count
    from app.oa_applications oa
    where oa.row_id = v_alias_row_id
      and oa.status <> 'deleted';
    if alias_application_count <> 0 then
        raise exception '0153: historical OA row is still canonical';
    end if;

    select
        count(*)::integer,
        max(alias.canonical_row_id),
        max(alias.status)
    into existing_alias_count, existing_canonical_row_id, existing_status
    from app.oa_source_aliases alias
    where alias.alias_row_id = v_alias_row_id;
    if existing_alias_count > 0
       and not (
           existing_alias_count = 1
           and existing_canonical_row_id = v_canonical_row_id
           and existing_status = 'active'
       ) then
        raise exception '0153: historical OA alias has a conflicting review record';
    end if;

    with canonical_oa as materialized (
        select oa.id
        from app.oa_applications oa
        where oa.row_id = v_canonical_row_id
          and oa.status <> 'deleted'
    ),
    current_items as materialized (
        select item.row_id as source_expense_item_id
        from app.oa_application_items item
        join canonical_oa oa on oa.id = item.oa_application_id
        join (
            values
                ('oa-exp-6a86a63777bca2d0c5f62d07:item:0:f45376305de2'::text),
                ('oa-exp-6a86a63777bca2d0c5f62d07:item:1:32417101b6eb'::text)
        ) expected(source_expense_item_id)
          on expected.source_expense_item_id = item.row_id
    ),
    owned_attachments as materialized (
        select
            attachment.source_attachment_key,
            nullif(
                btrim(attachment.normalized_payload->>'source_expense_item_id'),
                ''
            ) as source_expense_item_id
        from app.oa_attachments attachment
        join canonical_oa oa on oa.id = attachment.oa_application_id
        where nullif(btrim(attachment.source_attachment_key), '') is not null
    ),
    bridge_sources as materialized (
        select distinct
            source.source_expense_item_id,
            owned.source_expense_item_id as owned_expense_item_id,
            owned.source_attachment_key as owned_attachment_key,
            source.source_attachment_key,
            source.cache_source_attachment_key
        from owned_attachments owned
        join app.oa_attachment_invoice_cache_sources source
          on source.source_attachment_key = owned.source_attachment_key
        union
        select distinct
            source.source_expense_item_id,
            owned.source_expense_item_id,
            owned.source_attachment_key,
            source.source_attachment_key,
            source.cache_source_attachment_key
        from owned_attachments owned
        join app.oa_attachment_invoice_cache_sources source
          on source.cache_source_attachment_key = owned.source_attachment_key
    ),
    current_attachment_items as materialized (
        select distinct
            owned.source_attachment_key as owned_attachment_key,
            item.source_expense_item_id as current_expense_item_id
        from owned_attachments owned
        join current_items item
          on item.source_expense_item_id = owned.source_expense_item_id
        union
        select distinct
            bridge.owned_attachment_key,
            item.source_expense_item_id
        from bridge_sources bridge
        join current_items item
          on item.source_expense_item_id = bridge.source_expense_item_id
    ),
    invoice_sources as materialized (
        select
            coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
            source_link.value->>'source_expense_item_id' as source_expense_item_id,
            source_link.value->>'source_attachment_key' as source_attachment_key
        from app.invoices invoice
        cross join lateral jsonb_array_elements(
            case
                when jsonb_typeof(invoice.source_links) = 'array' then invoice.source_links
                else '[]'::jsonb
            end
        ) source_link(value)
        where invoice.status <> 'deleted'
          and invoice.workbench_visibility = 'visible'
          and invoice.legacy_mongo_id in ('inv_imported_0898', 'inv_imported_0899')
          and source_link.value->>'source_type' = 'oa_attachment_invoice'
          and source_link.value->>'source_expense_item_id' = any(v_expected_legacy_item_ids)
          and nullif(source_link.value->>'source_attachment_key', '') is not null
    ),
    matched_evidence as materialized (
        select distinct
            invoice.invoice_id,
            invoice.source_expense_item_id as invoice_expense_item_id,
            invoice.source_attachment_key as invoice_attachment_key,
            current_item.current_expense_item_id,
            bridge.source_expense_item_id as bridge_expense_item_id,
            bridge.owned_attachment_key
        from invoice_sources invoice
        join bridge_sources bridge
          on invoice.source_attachment_key in (
             bridge.owned_attachment_key,
             bridge.source_attachment_key,
             bridge.cache_source_attachment_key
         )
        join current_attachment_items current_item
          on current_item.owned_attachment_key = bridge.owned_attachment_key
        where bridge.source_expense_item_id in (
             invoice.source_expense_item_id,
             current_item.current_expense_item_id
         )
    )
    select
        coalesce(array(
            select distinct item.source_expense_item_id
            from current_items item
            order by item.source_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct evidence.bridge_expense_item_id
            from matched_evidence evidence
            order by evidence.bridge_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct evidence.current_expense_item_id
            from matched_evidence evidence
            order by evidence.current_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct encode(digest(evidence.owned_attachment_key, 'sha256'), 'hex')
            from matched_evidence evidence
            order by encode(digest(evidence.owned_attachment_key, 'sha256'), 'hex')
        ), array[]::text[]),
        coalesce(array(
            select distinct encode(digest(source.source_attachment_key, 'sha256'), 'hex')
            from invoice_sources source
            order by encode(digest(source.source_attachment_key, 'sha256'), 'hex')
        ), array[]::text[]),
        coalesce(array(
            select distinct evidence.invoice_id
            from matched_evidence evidence
            order by evidence.invoice_id
        ), array[]::text[]),
        coalesce(array(
            select distinct source.source_expense_item_id
            from invoice_sources source
            order by source.source_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct concat_ws(
                '|',
                evidence.invoice_id,
                evidence.invoice_expense_item_id,
                evidence.current_expense_item_id,
                encode(digest(evidence.invoice_attachment_key, 'sha256'), 'hex'),
                encode(digest(evidence.owned_attachment_key, 'sha256'), 'hex')
            )
            from matched_evidence evidence
            order by concat_ws(
                '|',
                evidence.invoice_id,
                evidence.invoice_expense_item_id,
                evidence.current_expense_item_id,
                encode(digest(evidence.invoice_attachment_key, 'sha256'), 'hex'),
                encode(digest(evidence.owned_attachment_key, 'sha256'), 'hex')
            )
        ), array[]::text[]),
        (select count(*)::integer from invoice_sources),
        (
            select count(*)::integer
            from (
                select distinct evidence.invoice_id, evidence.owned_attachment_key
                from matched_evidence evidence
            ) matched_attachment
        )
    into
        current_item_ids,
        bridge_item_ids,
        matched_current_item_ids,
        attachment_key_hashes,
        invoice_attachment_key_hashes,
        invoice_ids,
        invoice_item_ids,
        evidence_mappings,
        invoice_source_link_count,
        matched_invoice_attachment_count;

    if current_item_ids <> v_expected_current_item_ids then
        raise exception '0153: current OA item identities do not match reviewed evidence';
    end if;
    if invoice_source_link_count <> 2
       or invoice_item_ids <> v_expected_legacy_item_ids then
        raise exception '0153: historical invoice source identities do not match reviewed evidence';
    end if;
    if matched_current_item_ids <> v_expected_current_item_ids
       or matched_invoice_attachment_count <> 2
       or cardinality(evidence_mappings) <> 2 then
        raise exception
            '0153: invoice and current attachment ownership disagree; current_items=%, bridge_items=%, matched_current_items=%, matched_attachments=%, mappings=%',
            current_item_ids,
            bridge_item_ids,
            matched_current_item_ids,
            matched_invoice_attachment_count,
            cardinality(evidence_mappings);
    end if;
    if invoice_ids <> array['inv_imported_0898', 'inv_imported_0899']::text[] then
        raise exception '0153: canonical invoice identities do not match reviewed evidence';
    end if;
    if cardinality(attachment_key_hashes) <> 2
       or cardinality(invoice_attachment_key_hashes) <> 2 then
        raise exception '0153: exact attachment key evidence is incomplete';
    end if;

    evidence_hash := encode(
        digest(
            concat_ws(
                '|',
                v_alias_row_id,
                v_canonical_row_id,
                array_to_string(current_item_ids, ','),
                array_to_string(bridge_item_ids, ','),
                array_to_string(matched_current_item_ids, ','),
                array_to_string(invoice_ids, ','),
                array_to_string(attachment_key_hashes, ','),
                array_to_string(invoice_attachment_key_hashes, ','),
                array_to_string(evidence_mappings, ',')
            ),
            'sha256'
        ),
        'hex'
    );

    if existing_alias_count = 1 then
        return;
    end if;

    insert into app.oa_source_aliases(
        alias_row_id,
        canonical_row_id,
        reason,
        evidence_hash,
        status,
        reviewed_by,
        reviewed_at,
        raw_payload,
        updated_at
    ) values (
        v_alias_row_id,
        v_canonical_row_id,
        'verified_attachment_identity_migration',
        evidence_hash,
        'active',
        'system:migration:0153',
        now(),
        jsonb_build_object(
            'contract', 'oa-source-alias-attachment-identity-repair-v3',
            'current_item_count', cardinality(current_item_ids),
            'bridge_item_count', cardinality(bridge_item_ids),
            'invoice_count', cardinality(invoice_ids),
            'item_mappings', evidence_mappings,
            'attachment_key_hashes', attachment_key_hashes,
            'invoice_attachment_key_hashes', invoice_attachment_key_hashes
        ),
        now()
    );
end $$;
