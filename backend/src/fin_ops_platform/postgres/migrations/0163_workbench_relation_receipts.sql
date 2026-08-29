set local lock_timeout = '10s';
set local statement_timeout = '1min';

create table if not exists app.workbench_relation_receipts (
    id uuid primary key default gen_random_uuid(),
    relation_id uuid not null references app.workbench_pair_relations(id),
    case_id text not null,
    relation_version integer not null,
    source_fingerprint text not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
    file_object_id uuid not null references app.file_objects(id),
    storage_uri text not null,
    receipt_count integer not null check (receipt_count > 0),
    total_amount numeric(20, 6) not null check (total_amount >= 0),
    snapshot jsonb not null check (jsonb_typeof(snapshot) = 'object'),
    generated_by_id text not null,
    generated_by_account text not null,
    generated_by_name text not null,
    generated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    unique (case_id, source_fingerprint)
);

create index workbench_relation_receipts_relation_idx
    on app.workbench_relation_receipts (relation_id, generated_at desc);

grant select, insert on app.workbench_relation_receipts to fin_ops_api, app_runtime;
grant select on app.workbench_relation_receipts to fin_ops_readonly;
grant select, insert, update, delete on app.workbench_relation_receipts to fin_ops_migrator;
