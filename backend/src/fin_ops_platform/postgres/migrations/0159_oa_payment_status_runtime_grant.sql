set local lock_timeout = '10s';
set local statement_timeout = '30s';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update on app.oa_payment_status_writeback_states to fin_ops_app_runtime;
    end if;
end $$;
