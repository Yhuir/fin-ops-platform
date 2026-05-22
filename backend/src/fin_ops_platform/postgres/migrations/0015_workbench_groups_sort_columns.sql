alter table read_model.workbench_groups
    add column if not exists oa_sort_min text,
    add column if not exists oa_sort_max text,
    add column if not exists bank_sort_min text,
    add column if not exists bank_sort_max text,
    add column if not exists invoice_sort_min text,
    add column if not exists invoice_sort_max text;

create index if not exists workbench_groups_oa_sort_idx
    on read_model.workbench_groups (scope_key, zone, oa_sort_min, oa_sort_max, updated_at desc);

create index if not exists workbench_groups_bank_sort_idx
    on read_model.workbench_groups (scope_key, zone, bank_sort_min, bank_sort_max, updated_at desc);

create index if not exists workbench_groups_invoice_sort_idx
    on read_model.workbench_groups (scope_key, zone, invoice_sort_min, invoice_sort_max, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_groups to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_groups to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_groups to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_groups to fin_ops_migrator;
    end if;
end $$;
