-- Runtime grants for workbench reconciliation read model.

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.workbench_reconciliation_decisions to fin_ops_app_runtime;
        grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_app_runtime;
        grant select, insert, update on app.matching_runs to fin_ops_app_runtime;
    end if;
end $$;
