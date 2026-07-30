-- 0130_canonical_finance_domain_contracts
-- Enforce canonical fact/relation shapes for new writes without rewriting history.

set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table app.invoices
    add constraint invoices_canonical_date_month_chk
        check (
            (invoice_date is null and invoice_month is null)
            or (
                invoice_date is not null
                and invoice_month is not null
                and invoice_month = date_trunc('month', invoice_date::timestamp)::date
            )
        ) not valid,
    add constraint invoices_source_links_array_chk
        check (jsonb_typeof(source_links) = 'array') not valid,
    add constraint invoices_raw_payload_object_chk
        check (jsonb_typeof(raw_payload) = 'object') not valid;

alter table app.bank_transactions
    add constraint bank_transactions_direction_chk
        check (txn_direction in ('inflow', 'outflow')) not valid,
    add constraint bank_transactions_canonical_date_month_chk
        check (
            (txn_date is null and txn_month is null)
            or (
                txn_date is not null
                and txn_month is not null
                and txn_month = date_trunc('month', txn_date::timestamp)::date
            )
        ) not valid,
    add constraint bank_transactions_text_fields_array_chk
        check (jsonb_typeof(bank_text_fields) = 'array') not valid,
    add constraint bank_transactions_raw_payload_object_chk
        check (jsonb_typeof(raw_payload) = 'object') not valid;

alter table app.workbench_pair_relations
    add constraint workbench_pair_relations_version_chk
        check (version >= 1) not valid,
    add constraint workbench_pair_relations_month_scope_chk
        check (
            month_scope is null
            or month_scope = date_trunc('month', month_scope::timestamp)::date
        ) not valid,
    add constraint workbench_pair_relations_row_cardinality_chk
        check (
            cardinality(row_ids) > 0
            and cardinality(row_ids) = cardinality(row_types)
        ) not valid,
    add constraint workbench_pair_relations_row_values_chk
        check (
            array_position(row_ids, null) is null
            and array_position(row_types, null) is null
            and array_to_string(row_ids, chr(1))
                !~ ('(^|' || chr(1) || ')[[:space:]]*($|' || chr(1) || ')')
            and array_to_string(row_types, chr(1))
                !~ ('(^|' || chr(1) || ')[[:space:]]*($|' || chr(1) || ')')
        ) not valid,
    add constraint workbench_pair_relations_json_objects_chk
        check (
            jsonb_typeof(amount_check) = 'object'
            and jsonb_typeof(special_metadata) = 'object'
            and jsonb_typeof(source_versions) = 'object'
            and jsonb_typeof(raw_payload) = 'object'
        ) not valid;

alter table job.background_jobs
    add constraint background_jobs_affected_months_chk
        check (
            array_position(affected_months, null) is null
            and (
                cardinality(affected_months) = 0
                or array_to_string(affected_months, ',')
                    ~ '^[0-9]{4}-(0[1-9]|1[0-2])(,[0-9]{4}-(0[1-9]|1[0-2]))*$'
            )
        ) not valid,
    add constraint background_jobs_json_objects_chk
        check (
            jsonb_typeof(progress) = 'object'
            and jsonb_typeof(result_summary) = 'object'
            and jsonb_typeof(attention) = 'object'
            and jsonb_typeof(raw_payload) = 'object'
        ) not valid;
