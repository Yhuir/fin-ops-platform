do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.workbench_generation_stats to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on read_model.workbench_generation_stats to fin_ops_app;
    end if;
end $$;
