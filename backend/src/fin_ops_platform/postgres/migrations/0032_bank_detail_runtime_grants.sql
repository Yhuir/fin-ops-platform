do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.bank_detail_rows to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.bank_detail_scopes to fin_ops_app_runtime;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_app_runtime;
        grant select, insert, update on job.outbox_events to fin_ops_app_runtime;
    end if;
end $$;
