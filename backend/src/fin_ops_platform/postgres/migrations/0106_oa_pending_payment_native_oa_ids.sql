alter table read_model.oa_pending_payment_rows
    add column if not exists oa_ids text[] not null default array[]::text[];
