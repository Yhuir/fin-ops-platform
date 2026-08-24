set local lock_timeout = '10s';
set local statement_timeout = '1min';

do $$
declare
    v_alias_row_id constant text := 'oa-exp-2327';
    v_canonical_row_id constant text := 'oa-exp-6a86a63777bca2d0c5f62d07';
    v_expected_item_ids constant text[] := array[
        'oa-exp-2327:item:0:d91d8bb509c9',
        'oa-exp-2327:item:1:a48a5229fa61'
    ]::text[];
    canonical_count integer;
    alias_application_count integer;
    existing_alias_count integer;
    existing_canonical_row_id text;
    existing_status text;
    bridge_item_ids text[];
    bridge_row_indexes text[];
    attachment_key_hashes text[];
    invoice_ids text[];
    invoice_item_ids text[];
    invoice_row_indexes text[];
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
        where source.source_expense_item_id = any(v_expected_item_ids)
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
        where source.source_expense_item_id = any(v_expected_item_ids)
    ),
    invoice_sources as materialized (
        select distinct
            coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
            source_link.value->>'source_expense_item_id' as source_expense_item_id,
            source_link.value->>'source_expense_row_index' as source_expense_row_index,
            source_link.value->>'source_attachment_key' as source_attachment_key
        from app.invoices invoice
        cross join lateral jsonb_array_elements(
            case
                when jsonb_typeof(invoice.source_links) = 'array' then invoice.source_links
                else '[]'::jsonb
            end
        ) source_link(value)
        where invoice.status <> 'deleted'
          and source_link.value->>'source_type' = 'oa_attachment_invoice'
          and source_link.value->>'source_expense_item_id' = any(v_expected_item_ids)
          and exists (
              select 1
              from bridge_sources bridge
              where source_link.value->>'source_attachment_key' in (
                  bridge.owned_attachment_key,
                  bridge.source_attachment_key,
                  bridge.cache_source_attachment_key
              )
          )
    )
    select
        coalesce(array(
            select distinct bridge.source_expense_item_id
            from bridge_sources bridge
            order by bridge.source_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct bridge.source_expense_row_index
            from bridge_sources bridge
            where nullif(bridge.source_expense_row_index, '') is not null
            order by bridge.source_expense_row_index
        ), array[]::text[]),
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
        ), array[]::text[]),
        coalesce(array(
            select distinct source.invoice_id
            from invoice_sources source
            order by source.invoice_id
        ), array[]::text[]),
        coalesce(array(
            select distinct source.source_expense_item_id
            from invoice_sources source
            order by source.source_expense_item_id
        ), array[]::text[]),
        coalesce(array(
            select distinct source.source_expense_row_index
            from invoice_sources source
            where nullif(source.source_expense_row_index, '') is not null
            order by source.source_expense_row_index
        ), array[]::text[])
    into
        bridge_item_ids,
        bridge_row_indexes,
        attachment_key_hashes,
        invoice_ids,
        invoice_item_ids,
        invoice_row_indexes;

    if bridge_item_ids <> v_expected_item_ids then
        raise exception '0153: attachment bridge item identities do not match reviewed evidence';
    end if;
    if invoice_item_ids <> bridge_item_ids then
        raise exception '0153: invoice and attachment bridge item identities disagree';
    end if;
    if bridge_row_indexes <> array['0', '1']::text[]
       or invoice_row_indexes <> bridge_row_indexes then
        raise exception '0153: invoice and attachment bridge row indexes disagree';
    end if;
    if invoice_ids <> array['inv_imported_0898', 'inv_imported_0899']::text[] then
        raise exception '0153: canonical invoice identities do not match reviewed evidence';
    end if;
    if cardinality(attachment_key_hashes) < 2 then
        raise exception '0153: exact attachment key evidence is incomplete';
    end if;

    evidence_hash := encode(
        digest(
            concat_ws(
                '|',
                v_alias_row_id,
                v_canonical_row_id,
                array_to_string(bridge_item_ids, ','),
                array_to_string(bridge_row_indexes, ','),
                array_to_string(invoice_ids, ','),
                array_to_string(attachment_key_hashes, ',')
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
            'contract', 'oa-source-alias-attachment-identity-repair-v1',
            'bridge_item_count', cardinality(bridge_item_ids),
            'invoice_count', cardinality(invoice_ids),
            'row_indexes', bridge_row_indexes,
            'attachment_key_hashes', attachment_key_hashes
        ),
        now()
    );
end $$;
