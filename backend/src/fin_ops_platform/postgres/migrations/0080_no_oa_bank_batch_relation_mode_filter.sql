create index if not exists no_oa_bank_batch_rows_relation_mode_filters_idx
    on read_model.no_oa_bank_batch_rows (
        (coalesce(nullif(payload->>'relation_mode', ''), 'no_oa_bank_batch')),
        scope_month,
        status_bucket,
        batch_type,
        account_key
    );
