alter table read_model.cost_statistics_read_models
    add column if not exists published_source_version bigint;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'cost_statistics_published_source_version_nonnegative_chk'
          and conrelid = 'read_model.cost_statistics_read_models'::regclass
    ) then
        alter table read_model.cost_statistics_read_models
            add constraint cost_statistics_published_source_version_nonnegative_chk
            check (published_source_version is null or published_source_version >= 0);
    end if;
end $$;

create index if not exists read_model_dirty_scopes_cost_latest_version_idx
    on job.read_model_dirty_scopes (
        tenant_id,
        scope_type,
        scope_key,
        source_version desc,
        updated_at desc,
        id desc
    )
    where scope_type = 'cost_statistics';
