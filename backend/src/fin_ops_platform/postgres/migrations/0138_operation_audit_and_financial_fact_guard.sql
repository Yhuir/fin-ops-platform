alter table audit.events
    add column if not exists action text,
    add column if not exists page_key text,
    add column if not exists operation_location text,
    add column if not exists reason text,
    add column if not exists outcome text not null default 'success',
    add column if not exists request_id text;

create index if not exists audit_events_action_time_idx
    on audit.events (action, occurred_at desc, id desc);
create index if not exists audit_events_page_time_idx
    on audit.events (page_key, occurred_at desc, id desc);
create index if not exists audit_events_outcome_time_idx
    on audit.events (outcome, occurred_at desc, id desc);
create index if not exists audit_events_request_idx
    on audit.events (request_id) where request_id is not null;

create table if not exists app.financial_fact_corrections (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null,
    entity_id text not null,
    operation text not null,
    actor_id text not null,
    reason text not null,
    occurred_at timestamptz not null default now(),
    before_value jsonb,
    after_value jsonb
);

create index if not exists financial_fact_corrections_entity_idx
    on app.financial_fact_corrections (entity_type, entity_id, occurred_at desc);

create or replace function audit.reject_append_only_change()
returns trigger
language plpgsql
as $$
begin
    raise exception '% is append-only', tg_table_schema || '.' || tg_table_name
        using errcode = '55000';
end;
$$;

drop trigger if exists audit_events_append_only on audit.events;
create trigger audit_events_append_only
before update or delete on audit.events
for each row execute function audit.reject_append_only_change();

drop trigger if exists financial_fact_corrections_append_only on app.financial_fact_corrections;
create trigger financial_fact_corrections_append_only
before update or delete on app.financial_fact_corrections
for each row execute function audit.reject_append_only_change();

create or replace function app.guard_financial_fact_change()
returns trigger
language plpgsql
as $$
declare
    correction_reason text := nullif(current_setting('fin_ops.correction_reason', true), '');
    correction_actor text := coalesce(nullif(current_setting('fin_ops.actor_id', true), ''), 'database');
    entity_identifier text;
    before_payload jsonb;
    after_payload jsonb;
    protected_change boolean := false;
begin
    entity_identifier := coalesce(old.legacy_mongo_id, old.id::text);
    before_payload := to_jsonb(old) - array['raw_payload', 'bank_text_fields', 'source_links'];
    after_payload := case
        when tg_op = 'DELETE' then null
        else to_jsonb(new) - array['raw_payload', 'bank_text_fields', 'source_links']
    end;

    if tg_op = 'DELETE' then
        protected_change := true;
    elsif tg_table_name = 'bank_transactions' then
        protected_change :=
            old.account_no is distinct from new.account_no
            or old.txn_direction is distinct from new.txn_direction
            or old.amount is distinct from new.amount
            or old.signed_amount is distinct from new.signed_amount
            or old.txn_date is distinct from new.txn_date
            or old.trade_time is distinct from new.trade_time
            or old.bank_serial_no is distinct from new.bank_serial_no
            or old.source_unique_key is distinct from new.source_unique_key
            or old.data_fingerprint is distinct from new.data_fingerprint;
    elsif tg_table_name = 'invoices' then
        protected_change :=
            old.invoice_type is distinct from new.invoice_type
            or old.invoice_no is distinct from new.invoice_no
            or old.invoice_code is distinct from new.invoice_code
            or old.digital_invoice_no is distinct from new.digital_invoice_no
            or old.invoice_date is distinct from new.invoice_date
            or old.amount is distinct from new.amount
            or old.signed_amount is distinct from new.signed_amount
            or old.tax_amount is distinct from new.tax_amount
            or old.total_with_tax is distinct from new.total_with_tax
            or old.currency is distinct from new.currency
            or old.source_unique_key is distinct from new.source_unique_key
            or old.data_fingerprint is distinct from new.data_fingerprint;
    end if;

    if not protected_change then
        return new;
    end if;
    if correction_reason is null then
        raise exception 'Financial fact % % requires fin_ops.correction_reason', tg_table_name, entity_identifier
            using errcode = '55000';
    end if;

    insert into app.financial_fact_corrections(
        entity_type, entity_id, operation, actor_id, reason, before_value, after_value
    )
    values (
        tg_table_name, entity_identifier, lower(tg_op), correction_actor,
        correction_reason, before_payload, after_payload
    );

    insert into audit.events(
        event_type, object_type, object_id, actor_id, action, page_key,
        operation_location, reason, outcome, payload
    )
    values (
        'financial_fact.corrected', tg_table_name, entity_identifier, correction_actor,
        lower(tg_op), 'database', 'database_trigger', correction_reason, 'success',
        jsonb_build_object('before', before_payload, 'after', after_payload, 'summary', correction_reason)
    );
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end;
$$;

drop trigger if exists bank_transactions_financial_fact_guard on app.bank_transactions;
create trigger bank_transactions_financial_fact_guard
before update or delete on app.bank_transactions
for each row execute function app.guard_financial_fact_change();

drop trigger if exists invoices_financial_fact_guard on app.invoices;
create trigger invoices_financial_fact_guard
before update or delete on app.invoices
for each row execute function app.guard_financial_fact_change();

create or replace function app.guard_workbench_relation_history_change()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'UPDATE'
       and (to_jsonb(new) - 'relation_id') = (to_jsonb(old) - 'relation_id')
       and new.relation_id is null then
        return new;
    end if;
    raise exception 'app.workbench_pair_relation_history is append-only'
        using errcode = '55000';
end;
$$;

drop trigger if exists workbench_pair_relation_history_append_only on app.workbench_pair_relation_history;
create trigger workbench_pair_relation_history_append_only
before update or delete on app.workbench_pair_relation_history
for each row execute function app.guard_workbench_relation_history_change();

insert into audit.events(
    event_type, actor_id, action, page_key, operation_location, reason, outcome, payload
)
select
    'audit.coverage_started', 'system', 'enable_operation_history', 'operation-history',
    'database_migration', '仅记录功能上线后的操作', 'success',
    jsonb_build_object('contract_revision', 'operation-audit-v1', 'summary', '操作历史记录已启用')
where not exists (
    select 1 from audit.events where event_type = 'audit.coverage_started'
);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant usage on schema app, audit to fin_ops_app_runtime;
        revoke update, delete on audit.events from fin_ops_app_runtime;
        grant select, insert on audit.events to fin_ops_app_runtime;
        revoke update, delete on app.financial_fact_corrections from fin_ops_app_runtime;
        grant select, insert on app.financial_fact_corrections to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant usage on schema app, audit to fin_ops_app;
        revoke update, delete on audit.events from fin_ops_app;
        grant select, insert on audit.events to fin_ops_app;
        revoke update, delete on app.financial_fact_corrections from fin_ops_app;
        grant select, insert on app.financial_fact_corrections to fin_ops_app;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema app, audit to fin_ops_api;
        revoke update, delete on audit.events from fin_ops_api;
        grant select, insert on audit.events to fin_ops_api;
        revoke update, delete on app.financial_fact_corrections from fin_ops_api;
        grant select, insert on app.financial_fact_corrections to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema app, audit to fin_ops_worker;
        revoke update, delete on audit.events from fin_ops_worker;
        grant select, insert on audit.events to fin_ops_worker;
        revoke update, delete on app.financial_fact_corrections from fin_ops_worker;
        grant select, insert on app.financial_fact_corrections to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema app, audit to fin_ops_readonly;
        grant select on audit.events, app.financial_fact_corrections to fin_ops_readonly;
    end if;
end $$;
