do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant usage on schema app, read_model, audit to fin_ops_api;
        grant select, insert, update on all tables in schema app to fin_ops_api;
        grant select on all tables in schema read_model to fin_ops_api;
        grant insert on audit.events to fin_ops_api;
        grant usage, select on all sequences in schema app, read_model, audit to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant usage on schema app, read_model, job, audit, staging to fin_ops_worker;
        grant select, insert, update on all tables in schema app, read_model, job, audit, staging to fin_ops_worker;
        grant usage, select on all sequences in schema app, read_model, job, audit, staging to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant usage on schema app, read_model, job, audit, staging to fin_ops_readonly;
        grant select on all tables in schema app, read_model, job, audit, staging to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant usage, create on schema app, read_model, job, audit, staging to fin_ops_migrator;
        grant select, insert, update on public.schema_migrations to fin_ops_migrator;
        grant select, insert, update on all tables in schema app, read_model, job, audit, staging to fin_ops_migrator;
        grant usage, select on all sequences in schema app, read_model, job, audit, staging to fin_ops_migrator;
    end if;
end $$;
