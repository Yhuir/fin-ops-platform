create table if not exists app.output_invoice_collection_status_overrides (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    invoice_identity_key text not null,
    invoice_id text,
    status_code text,
    expected_collection_date date,
    note text not null default '',
    version integer not null default 1,
    status text not null default 'active',
    created_by text not null default '',
    created_at timestamptz not null default now(),
    updated_by text not null default '',
    updated_at timestamptz not null default now(),
    revoked_by text,
    revoked_at timestamptz,
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_collection_status_overrides_status_chk
        check (status in ('active', 'revoked')),
    constraint output_invoice_collection_status_overrides_code_chk
        check (status_code is null or status_code in ('pending_collection', 'pending_red_invoice', 'collected'))
);

create unique index if not exists output_invoice_collection_status_overrides_active_uidx
    on app.output_invoice_collection_status_overrides(tenant_id, invoice_identity_key)
    where status = 'active';

create index if not exists output_invoice_collection_status_overrides_invoice_idx
    on app.output_invoice_collection_status_overrides(tenant_id, invoice_id);

create table if not exists app.output_invoice_collection_reminders (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    invoice_identity_key text not null,
    invoice_id text,
    remind_at timestamptz not null,
    channel text not null default 'oa',
    note text not null default '',
    status text not null default 'active',
    sent_at timestamptz,
    result jsonb not null default '{}'::jsonb,
    created_by text not null default '',
    created_at timestamptz not null default now(),
    updated_by text not null default '',
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_collection_reminders_status_chk
        check (status in ('active', 'cancelled', 'sent', 'failed')),
    constraint output_invoice_collection_reminders_channel_chk
        check (channel in ('oa', 'email', 'manual'))
);

create unique index if not exists output_invoice_collection_reminders_active_uidx
    on app.output_invoice_collection_reminders(tenant_id, invoice_identity_key)
    where status = 'active';

create index if not exists output_invoice_collection_reminders_due_idx
    on app.output_invoice_collection_reminders(tenant_id, status, remind_at);

create table if not exists app.output_invoice_collection_red_relations (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    invoice_identity_key text not null,
    invoice_id text,
    related_invoice_identity_key text not null,
    related_invoice_id text,
    relation_type text not null,
    evidence text not null default '',
    confidence text not null default 'manual_confirmed',
    source text not null default 'manual',
    version integer not null default 1,
    status text not null default 'active',
    created_by text not null default '',
    created_at timestamptz not null default now(),
    updated_by text not null default '',
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_collection_red_relations_status_chk
        check (status in ('active', 'revoked')),
    constraint output_invoice_collection_red_relations_type_chk
        check (relation_type in ('red_invoice', 'blue_invoice'))
);

create unique index if not exists output_invoice_collection_red_relations_active_uidx
    on app.output_invoice_collection_red_relations(tenant_id, invoice_identity_key, related_invoice_identity_key)
    where status = 'active';

create table if not exists app.output_invoice_receipt_settings (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    prefix text not null default 'SK',
    reset_period text not null default 'monthly',
    version integer not null default 1,
    updated_by text not null default '',
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_receipt_settings_reset_period_chk
        check (reset_period in ('monthly', 'yearly', 'none'))
);

create unique index if not exists output_invoice_receipt_settings_tenant_uidx
    on app.output_invoice_receipt_settings(tenant_id);

create table if not exists app.output_invoice_receipt_number_counters (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    prefix text not null,
    period_key text not null,
    next_sequence integer not null default 1,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create unique index if not exists output_invoice_receipt_number_counters_scope_uidx
    on app.output_invoice_receipt_number_counters(tenant_id, prefix, period_key);

create table if not exists app.output_invoice_receipts (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    receipt_no text not null,
    invoice_identity_key text not null,
    invoice_id text,
    bank_transaction_id text,
    amount numeric(18, 2) not null,
    status text not null default 'issued',
    idempotency_key text not null,
    payload jsonb not null default '{}'::jsonb,
    created_by text not null default '',
    created_at timestamptz not null default now(),
    updated_by text not null default '',
    updated_at timestamptz not null default now(),
    voided_by text,
    voided_at timestamptz,
    void_reason text,
    reissued_from_receipt_id uuid,
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_receipts_status_chk
        check (status in ('issued', 'voided', 'reissued'))
);

create unique index if not exists output_invoice_receipts_receipt_no_uidx
    on app.output_invoice_receipts(tenant_id, receipt_no);

create unique index if not exists output_invoice_receipts_idempotency_uidx
    on app.output_invoice_receipts(tenant_id, idempotency_key);

create index if not exists output_invoice_receipts_invoice_idx
    on app.output_invoice_receipts(tenant_id, invoice_identity_key, invoice_id);

create table if not exists app.output_invoice_receipt_events (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    receipt_id uuid not null,
    event_type text not null,
    actor_id text not null default '',
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint output_invoice_receipt_events_type_chk
        check (event_type in ('created', 'voided', 'reissued'))
);

create index if not exists output_invoice_receipt_events_receipt_idx
    on app.output_invoice_receipt_events(tenant_id, receipt_id, created_at desc);

grant select, insert, update on app.output_invoice_collection_status_overrides to fin_ops_app_runtime;
grant select, insert, update on app.output_invoice_collection_reminders to fin_ops_app_runtime;
grant select, insert, update on app.output_invoice_collection_red_relations to fin_ops_app_runtime;
grant select, insert, update on app.output_invoice_receipt_settings to fin_ops_app_runtime;
grant select, insert, update on app.output_invoice_receipt_number_counters to fin_ops_app_runtime;
grant select, insert, update on app.output_invoice_receipts to fin_ops_app_runtime;
grant select, insert on app.output_invoice_receipt_events to fin_ops_app_runtime;

grant select on app.output_invoice_collection_status_overrides to fin_ops_api;
grant select on app.output_invoice_collection_reminders to fin_ops_api;
grant select on app.output_invoice_collection_red_relations to fin_ops_api;
grant select on app.output_invoice_receipt_settings to fin_ops_api;
grant select on app.output_invoice_receipt_number_counters to fin_ops_api;
grant select on app.output_invoice_receipts to fin_ops_api;
grant select on app.output_invoice_receipt_events to fin_ops_api;
