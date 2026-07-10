do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.oa_pending_payment_admissions to fin_ops_app_runtime;
    end if;
end $$;
