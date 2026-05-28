do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.workbench_generations to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_snapshots to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_summary to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_rows to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_groups to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.workbench_group_rows to fin_ops_app_runtime;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_app_runtime;
        grant select, insert, update on job.outbox_events to fin_ops_app_runtime;
    end if;
end $$;
