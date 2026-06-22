create table if not exists app.etc_batch_invoice_links (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    business_batch_id text not null,
    etc_invoice_id text,
    invoice_id uuid not null references app.invoices(id),
    identity_key text not null,
    invoice_no text,
    invoice_code text,
    digital_invoice_no text,
    invoice_date date,
    link_status text not null default 'active',
    link_source text not null,
    confidence text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (link_status in ('active', 'removed')),
    check (confidence in ('strict', 'manual_review'))
);

create unique index if not exists etc_batch_invoice_links_active_identity_uidx
    on app.etc_batch_invoice_links (tenant_id, business_batch_id, identity_key)
    where link_status = 'active';

create unique index if not exists etc_batch_invoice_links_active_invoice_uidx
    on app.etc_batch_invoice_links (tenant_id, business_batch_id, invoice_id)
    where link_status = 'active';

create index if not exists etc_batch_invoice_links_business_batch_idx
    on app.etc_batch_invoice_links (tenant_id, business_batch_id, link_status);

create index if not exists etc_batch_invoice_links_invoice_idx
    on app.etc_batch_invoice_links (invoice_id, link_status);

create index if not exists etc_batch_invoice_links_etc_invoice_idx
    on app.etc_batch_invoice_links (etc_invoice_id)
    where etc_invoice_id is not null;

