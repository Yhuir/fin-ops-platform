alter table if exists read_model.bank_detail_rows
    add column if not exists manual_confirmed_category_code text,
    add column if not exists auto_candidate_category_codes text[] not null default '{}'::text[],
    add column if not exists auto_candidate_categories jsonb not null default '[]'::jsonb,
    add column if not exists category_resolution_status text not null default 'unmatched',
    add column if not exists category_rule_version text;

create index if not exists bank_detail_rows_resolution_status_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, category_resolution_status);
