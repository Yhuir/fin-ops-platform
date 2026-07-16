-- Production API and runtime workers share the restricted app runtime role.
-- Grant the structured cost bank-flow table the same access contract as the
-- existing cost read-model tables.

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.cost_statistics_bank_flow_rows to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on read_model.cost_statistics_bank_flow_rows to fin_ops_app;
    end if;
end $$;
