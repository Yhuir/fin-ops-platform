alter table if exists read_model.bank_detail_rows
    add column if not exists manual_category_third_label text,
    add column if not exists auto_category_third_label text,
    add column if not exists effective_category_third_label text,
    add column if not exists effective_turnover_role text,
    add column if not exists effective_turnover_action_type text,
    add column if not exists effective_turnover_family text;

create index if not exists bank_detail_rows_effective_third_label_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_category_third_label);

create index if not exists bank_detail_rows_effective_turnover_action_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_turnover_action_type);

create index if not exists bank_detail_rows_effective_turnover_family_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_turnover_family);
