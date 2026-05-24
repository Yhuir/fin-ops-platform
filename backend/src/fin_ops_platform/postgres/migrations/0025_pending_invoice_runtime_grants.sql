-- Runtime role grants for pending invoice scope read model.

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.pending_invoice_scopes to fin_ops_app_runtime;
    end if;
end $$;
