do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update on app.tax_offset_plans to fin_ops_app_runtime;
    end if;
end $$;
