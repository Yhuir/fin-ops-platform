set local lock_timeout = '10s';
set local statement_timeout = '1min';

do $$
declare
    v_relation_case_id constant text := 'CASE-BATCH-txn_imported_1453';
    v_group_id constant text := 'case:CASE-BATCH-txn_imported_1453';
    v_scope_month constant date := date '2026-04-01';
    v_old_fingerprint constant text :=
        'e21ebad42ce05610276655cc07aea50fd9cde2a23721d05e4c15b9f6491d1b76';
    v_new_fingerprint constant text :=
        'cdab5ebcc4b83c29027d67e457fb81baff4c10f08a044a09ed6cc9498bf9863b';
    v_removed_evidence constant text :=
        '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f';
    v_remaining_evidence constant text[] := array[
        '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
        'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
    ]::text[];
    v_expected_old_evidence constant text[] := array[
        '3b49216f9f5fedecfbc65a94cb9bce02bb23cb44ec5078e51e9665710e61ee6f',
        '630c2bb2856e5a614790cd2df30a84625cddac2daf467fc8b149124f3bd64c5d',
        'f1f2d1612a1499e8485182dddaa365f9a89c5abd5186cf30580b900a4a9b55af'
    ]::text[];
    v_expected_members constant text[] := array[
        'bank:txn_imported_1453',
        'invoice:etc-summary-ETC-OA-20260413-241125',
        'oa:oa-exp-2080'
    ]::text[];
    v_old_case_id constant text :=
        'ANOMALY-REVIEW-e21ebad42ce05610276655cc07aea50fd';
    v_new_case_id constant text :=
        'ANOMALY-REVIEW-cdab5ebcc4b83c29027d67e457fb81ba';
    v_reviewed_at constant timestamptz :=
        timestamptz '2026-08-25T17:01:44.700999+08:00';
    v_migrated_version constant integer := 2;
    old_decision app.workbench_exception_cases%rowtype;
    current_new_decision app.workbench_exception_cases%rowtype;
    relation_row app.workbench_pair_relations%rowtype;
    old_count integer;
    new_count integer;
    relation_count integer;
    old_evidence text[];
    old_codes text[];
    new_evidence text[];
    new_codes text[];
    relation_members text[];
    normalized_payload jsonb;
begin
    select count(*)::integer
    into old_count
    from app.workbench_exception_cases exception
    where exception.case_id = v_old_case_id;

    -- Fresh and unrelated databases have no reviewed production decision to migrate.
    if old_count = 0 then
        return;
    end if;
    if old_count <> 1 then
        raise exception '0154: old ETC anomaly review decision is not unique';
    end if;

    select *
    into strict old_decision
    from app.workbench_exception_cases exception
    where exception.case_id = v_old_case_id
    for update;

    select coalesce(array_agg(evidence.value order by evidence.value), array[]::text[])
    into old_evidence
    from jsonb_array_elements_text(
        case
            when jsonb_typeof(
                old_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
            ) = 'array'
                then old_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
            else '[]'::jsonb
        end
    ) as evidence(value);
    select coalesce(array_agg(code.value order by code.value), array[]::text[])
    into old_codes
    from jsonb_array_elements_text(
        case
            when jsonb_typeof(
                old_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
            ) = 'array'
                then old_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
            else '[]'::jsonb
        end
    ) as code(value);

    if old_decision.status is distinct from 'resolved'
       or old_decision.resolution is distinct from 'accept_paired'
       or old_decision.version is distinct from 1
       or old_decision.scenario is distinct from 'workbench_anomaly_review'
       or old_decision.scope_month is distinct from v_scope_month
       or old_decision.updated_by is distinct from '8'
       or old_decision.updated_at is distinct from v_reviewed_at
       or old_decision.raw_payload#>>'{normalized_payload,fingerprint}'
            is distinct from v_old_fingerprint
       or old_decision.raw_payload#>>'{normalized_payload,group_id}'
            is distinct from v_group_id
       or old_decision.raw_payload#>>'{normalized_payload,decision}'
            is distinct from 'accept_paired'
       or old_decision.raw_payload#>>'{normalized_payload,version}'
            is distinct from '1'
       or old_evidence is distinct from v_expected_old_evidence
       or old_codes is distinct from array[
            'oa_invoice_attachment_absent',
            'oa_invoice_attachment_unassigned'
       ]::text[] then
        raise exception '0154: old ETC anomaly review evidence differs from the reviewed contract';
    end if;

    select count(*)::integer
    into relation_count
    from app.workbench_pair_relations relation
    where relation.case_id = v_relation_case_id;
    if relation_count <> 1 then
        raise exception '0154: target ETC relation is not unique';
    end if;

    select *
    into strict relation_row
    from app.workbench_pair_relations relation
    where relation.case_id = v_relation_case_id
    for update;

    select coalesce(array_agg(member_key order by member_key), array[]::text[])
    into relation_members
    from (
        select concat(
            case lower(btrim(member.row_type))
                when 'oa_application' then 'oa'
                when 'bank_transaction' then 'bank'
                when 'formal_invoice' then 'invoice'
                when 'input_invoice' then 'invoice'
                when 'output_invoice' then 'invoice'
                when 'etc_summary' then 'invoice'
                when 'etc_invoice_summary' then 'invoice'
                else lower(btrim(member.row_type))
            end,
            ':',
            btrim(member.row_id)
        ) as member_key
        from unnest(relation_row.row_ids, relation_row.row_types)
            as member(row_id, row_type)
    ) normalized_members;

    if relation_row.status is distinct from 'active'
       or relation_row.relation_mode is distinct from 'batch_accounting'
       or relation_row.month_scope is distinct from v_scope_month
       or relation_members is distinct from v_expected_members
       or relation_row.amount_check->>'status' is distinct from 'matched'
       or relation_row.amount_check->>'oa_total' is distinct from '2411.25'
       or relation_row.amount_check->>'bank_total' is distinct from '2411.25'
       or relation_row.amount_check->>'invoice_total' is distinct from '2411.25'
       or relation_row.amount_check->>'amount_delta' is distinct from '0.00'
       or relation_row.updated_at is null
       or relation_row.updated_at > v_reviewed_at then
        raise exception '0154: target ETC relation changed after review';
    end if;

    select count(*)::integer
    into new_count
    from app.workbench_exception_cases exception
    where exception.case_id = v_new_case_id;
    if new_count > 1 then
        raise exception '0154: migrated ETC anomaly review decision is not unique';
    end if;

    if new_count = 1 then
        select *
        into strict current_new_decision
        from app.workbench_exception_cases exception
        where exception.case_id = v_new_case_id
        for update;

        select coalesce(array_agg(evidence.value order by evidence.value), array[]::text[])
        into new_evidence
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    current_new_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                ) = 'array'
                    then current_new_decision.raw_payload#>'{normalized_payload,evidence_item_fingerprints}'
                else '[]'::jsonb
            end
        ) as evidence(value);
        select coalesce(array_agg(code.value order by code.value), array[]::text[])
        into new_codes
        from jsonb_array_elements_text(
            case
                when jsonb_typeof(
                    current_new_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                ) = 'array'
                    then current_new_decision.raw_payload#>'{normalized_payload,detected_classification_codes}'
                else '[]'::jsonb
            end
        ) as code(value);

        if current_new_decision.status is not distinct from 'resolved'
           and current_new_decision.resolution is not distinct from 'accept_paired'
           and current_new_decision.version is not distinct from v_migrated_version
           and current_new_decision.scenario is not distinct from 'workbench_anomaly_review'
           and current_new_decision.scope_month is not distinct from v_scope_month
           and current_new_decision.updated_by is not distinct from old_decision.updated_by
           and current_new_decision.updated_at is not distinct from v_reviewed_at
           and current_new_decision.raw_payload#>>'{normalized_payload,fingerprint}'
                is not distinct from v_new_fingerprint
           and current_new_decision.raw_payload#>>'{normalized_payload,group_id}'
                is not distinct from v_group_id
           and current_new_decision.raw_payload#>>'{normalized_payload,decision}'
                is not distinct from 'accept_paired'
           and current_new_decision.raw_payload#>>'{normalized_payload,version}'
                is not distinct from v_migrated_version::text
           and new_evidence is not distinct from v_remaining_evidence
           and new_codes is not distinct from array['oa_invoice_attachment_absent']::text[] then
            return;
        end if;
        raise exception '0154: migrated ETC anomaly review decision conflicts with existing state';
    end if;

    normalized_payload := jsonb_build_object(
        'case_id', v_new_case_id,
        'status', 'resolved',
        'version', v_migrated_version,
        'business_line', 'reconciliation_workbench',
        'scenario_code', 'workbench_anomaly_review',
        'fingerprint', v_new_fingerprint,
        'group_id', v_group_id,
        'scope_month', '2026-04',
        'decision', 'accept_paired',
        'note', coalesce(old_decision.raw_payload#>>'{normalized_payload,note}', ''),
        'detected_classification_codes', jsonb_build_array('oa_invoice_attachment_absent'),
        'evidence_item_fingerprints', to_jsonb(v_remaining_evidence),
        'row_ids', '[]'::jsonb,
        'candidate_ids', '[]'::jsonb,
        'updated_by', old_decision.updated_by,
        'migration_contract', 'etc-summary-unassigned-removal-v1',
        'migrated_from_fingerprint', v_old_fingerprint,
        'removed_evidence_fingerprint', v_removed_evidence,
        'migrated_by', 'system:migration:0154'
    );

    insert into app.workbench_exception_cases(
        case_id, status, resolution, version, business_line, scenario, scope_month,
        row_ids, candidate_ids, created_by, created_at, updated_by, updated_at, raw_payload
    ) values (
        v_new_case_id, 'resolved', 'accept_paired', v_migrated_version,
        'reconciliation_workbench',
        'workbench_anomaly_review', v_scope_month, array[]::text[], array[]::text[],
        old_decision.created_by, old_decision.created_at,
        old_decision.updated_by, old_decision.updated_at,
        jsonb_build_object('normalized_payload', normalized_payload)
    );

    insert into app.workbench_exception_case_events(
        exception_case_id, case_id, event_type, actor_id, payload, raw_payload
    ) values (
        (select id from app.workbench_exception_cases where case_id = v_new_case_id),
        v_new_case_id,
        'workbench_anomaly_review_migrated',
        'system:migration:0154',
        normalized_payload,
        jsonb_build_object('normalized_payload', normalized_payload)
    );
end $$;
