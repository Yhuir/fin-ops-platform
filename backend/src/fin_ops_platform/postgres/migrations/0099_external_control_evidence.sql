create table if not exists audit.external_control_evidence (
    evidence_id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    domain text not null check (domain in ('bank', 'oa', 'invoice', 'etc')),
    contract_version text not null,
    coverage_mode text not null check (coverage_mode = 'complete_snapshot'),
    scope_key text not null check (scope_key = 'all'),
    source_system text not null,
    source_snapshot_id text not null,
    observed_at timestamptz not null,
    valid_until timestamptz not null,
    artifact_sha256 text not null check (artifact_sha256 ~ '^[0-9a-f]{64}$'),
    artifact_size_bytes bigint not null check (artifact_size_bytes >= 0),
    collector_name text not null,
    collector_version text not null,
    manifest_fingerprint text not null check (manifest_fingerprint ~ '^[0-9a-f]{64}$'),
    declared_controls jsonb not null,
    item_count integer not null check (item_count >= 0),
    status text not null default 'registered' check (status in ('registered', 'revoked')),
    registered_by text not null,
    registration_reason text not null,
    registered_at timestamptz not null default now(),
    revoked_by text,
    revocation_reason text,
    revoked_at timestamptz,
    unique (tenant_id, domain, manifest_fingerprint),
    check (valid_until > observed_at),
    check (
        (status = 'registered' and revoked_by is null and revocation_reason is null and revoked_at is null)
        or
        (status = 'revoked' and revoked_by is not null and revocation_reason is not null and revoked_at is not null)
    )
);

create table if not exists audit.external_control_evidence_items (
    evidence_id uuid not null references audit.external_control_evidence(evidence_id),
    item_kind text not null,
    item_key text not null,
    content_fingerprint text not null check (content_fingerprint ~ '^[0-9a-f]{64}$'),
    normalized_fields jsonb not null,
    primary key (evidence_id, item_kind, item_key)
);

create index if not exists external_control_evidence_latest_idx
    on audit.external_control_evidence (tenant_id, domain, observed_at desc, registered_at desc, evidence_id desc);

create index if not exists external_control_evidence_items_key_idx
    on audit.external_control_evidence_items (item_kind, item_key, evidence_id);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on audit.external_control_evidence, audit.external_control_evidence_items to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on audit.external_control_evidence, audit.external_control_evidence_items to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on audit.external_control_evidence, audit.external_control_evidence_items to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update on audit.external_control_evidence to fin_ops_migrator;
        grant select, insert on audit.external_control_evidence_items to fin_ops_migrator;
    end if;
end $$;
