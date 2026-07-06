-- Speed up cost_statistics parent rollups over materialized month shards.

create index if not exists cost_statistics_rows_parent_rollup_idx
    on read_model.cost_statistics_rows (
        project_scope,
        scope_month,
        trade_date desc nulls last,
        trade_time_text desc,
        transaction_id,
        row_key
    )
    where scope_month is not null;
