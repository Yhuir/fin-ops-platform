update app.invoices
set data_fingerprint = case
        when coalesce(raw_payload->'normalized_payload'->>'source_unique_key', source_unique_key, '') <> ''
            then null
        else data_fingerprint
    end,
    raw_payload = case
        when coalesce(raw_payload->'normalized_payload'->>'source_unique_key', source_unique_key, '') <> ''
            then jsonb_set(
                coalesce(raw_payload, '{}'::jsonb),
                '{normalized_payload}',
                coalesce(raw_payload->'normalized_payload', '{}'::jsonb) - 'data_fingerprint',
                true
            )
        else raw_payload
    end,
    updated_at = now()
where (
        source_unique_key is not null
        and btrim(source_unique_key) <> ''
        and (
            data_fingerprint is not null
            or coalesce(raw_payload->'normalized_payload', '{}'::jsonb) ? 'data_fingerprint'
        )
    )
   or (
        coalesce(raw_payload->'normalized_payload'->>'source_unique_key', '') <> ''
        and (
            data_fingerprint is not null
            or coalesce(raw_payload->'normalized_payload', '{}'::jsonb) ? 'data_fingerprint'
        )
    );
