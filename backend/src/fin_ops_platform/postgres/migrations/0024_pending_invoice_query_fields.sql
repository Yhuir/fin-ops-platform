-- Native query fields for the upgraded pending invoice page.

alter table read_model.pending_invoice_rows
    add column if not exists status_code text,
    add column if not exists seller_name text,
    add column if not exists invoice_total numeric(20, 6),
    add column if not exists oa_applicant text,
    add column if not exists project_name text;

create table if not exists read_model.pending_invoice_scopes (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null unique,
    direction text not null,
    filter_group text not null default 'all',
    row_count integer not null default 0,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (direction in ('expense', 'income')),
    check (filter_group in ('all', 'requires_invoice', 'bank_statement_as_invoice', 'no_invoice_required'))
);

update read_model.pending_invoice_rows
set
    status_code = coalesce(
        nullif(status_code, ''),
        nullif(payload->'invoice_acquisition_status'->>'code', '')
    ),
    seller_name = coalesce(
        nullif(seller_name, ''),
        nullif(payload->'input_invoices'->'primary'->>'seller_name', '')
    ),
    invoice_total = coalesce(
        invoice_total,
        case
            when nullif(payload->'input_invoices'->'payment_summary'->>'invoice_total', '') ~ '^-?[0-9]+(\\.[0-9]+)?$'
            then nullif(payload->'input_invoices'->'payment_summary'->>'invoice_total', '')::numeric
            else null
        end
    ),
    oa_applicant = coalesce(
        nullif(oa_applicant, ''),
        nullif(payload->'oa'->'primary'->>'applicant', ''),
        nullif(payload->>'oa_applicant', '')
    ),
    project_name = coalesce(
        nullif(project_name, ''),
        nullif(payload->'oa'->'primary'->>'project_name', '')
    )
where status_code is null
   or seller_name is null
   or invoice_total is null
   or oa_applicant is null
   or project_name is null;

create index if not exists pending_invoice_rows_status_idx
    on read_model.pending_invoice_rows (direction, filter_group, status_code, trade_date desc, row_id);

create index if not exists pending_invoice_rows_seller_trgm
    on read_model.pending_invoice_rows using gin (seller_name gin_trgm_ops);

create index if not exists pending_invoice_rows_oa_applicant_trgm
    on read_model.pending_invoice_rows using gin (oa_applicant gin_trgm_ops);

create index if not exists pending_invoice_rows_project_trgm
    on read_model.pending_invoice_rows using gin (project_name gin_trgm_ops);

create index if not exists pending_invoice_rows_invoice_total_idx
    on read_model.pending_invoice_rows (direction, invoice_total);

create index if not exists pending_invoice_scopes_direction_filter_idx
    on read_model.pending_invoice_scopes (direction, filter_group, generated_at desc);

do $$
begin
    grant select on read_model.pending_invoice_scopes to fin_ops_api;
    grant select, insert, update, delete on read_model.pending_invoice_scopes to fin_ops_worker;
    grant select on read_model.pending_invoice_scopes to fin_ops_readonly;
    grant select, insert, update, delete on read_model.pending_invoice_scopes to fin_ops_migrator;
exception
    when undefined_object then
        null;
end $$;
