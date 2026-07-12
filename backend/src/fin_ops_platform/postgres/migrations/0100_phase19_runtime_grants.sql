do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.etc_import_session_files to fin_ops_app_runtime;
        grant select on audit.external_control_evidence, audit.external_control_evidence_items to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update, delete on app.etc_import_session_files to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on app.etc_import_session_files to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.etc_import_session_files to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.etc_import_session_files to fin_ops_migrator;
    end if;
end $$;
