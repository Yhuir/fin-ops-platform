alter table if exists read_model.bank_detail_rows
    add column if not exists manual_category_primary_label text,
    add column if not exists manual_category_sub_label text,
    add column if not exists manual_category_label_path text[] not null default '{}'::text[],
    add column if not exists auto_category_primary_label text,
    add column if not exists auto_category_sub_label text,
    add column if not exists auto_category_label_path text[] not null default '{}'::text[],
    add column if not exists effective_category_primary_label text,
    add column if not exists effective_category_sub_label text,
    add column if not exists effective_category_label_path text[] not null default '{}'::text[];

create index if not exists bank_detail_rows_effective_primary_label_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_category_primary_label);

create index if not exists bank_detail_rows_effective_sub_label_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_category_sub_label);
