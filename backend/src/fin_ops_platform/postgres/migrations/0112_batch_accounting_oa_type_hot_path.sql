create index if not exists workbench_rows_batch_accounting_oa_type_trgm_idx
    on read_model.workbench_rows using gin (
        (
            coalesce(payload->>'apply_type', '')
            || ' '
            || coalesce(payload->>'expense_type', '')
        ) gin_trgm_ops
    )
    where source_kind = 'oa'
      and scope_key <> 'all';
