create index if not exists workbench_relation_groups_batch_accounting_year_scope_group_idx
    on read_model.workbench_relation_groups (
        tenant_id,
        (
            coalesce(
                nullif(payload->'special_metadata'->>'bank_year', ''),
                nullif(payload->'special_metadata'->>'year', '')
            )
        ),
        scope_key,
        group_id
    )
    where relation_status = 'linked'
      and payload->'special_metadata'->>'source' = 'batch_accounting';
