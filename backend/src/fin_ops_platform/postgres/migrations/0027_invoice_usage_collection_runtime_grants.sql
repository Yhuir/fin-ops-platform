do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.input_invoice_usage_rows to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.input_invoice_usage_scopes to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.output_invoice_collection_rows to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.output_invoice_collection_scopes to fin_ops_app_runtime;
    end if;
end $$;
