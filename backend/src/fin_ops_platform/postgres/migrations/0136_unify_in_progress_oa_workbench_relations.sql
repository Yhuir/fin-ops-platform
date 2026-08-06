do $$
begin
    if exists (
        select 1
        from app.oa_pending_payment_bank_relations pending
        join app.workbench_pair_relations relation
          on relation.status = 'active'
         and relation.row_ids && (pending.oa_row_ids || pending.bank_transaction_ids)
        where pending.status = 'active'
        group by pending.relation_id
        having count(distinct relation.case_id) > 1
    ) then
        raise exception 'Cannot migrate OA pending relation spanning multiple active Workbench cases.';
    end if;

    if exists (
        select 1
        from app.oa_pending_payment_bank_relations left_pending
        join app.oa_pending_payment_bank_relations right_pending
          on left_pending.relation_id < right_pending.relation_id
         and (
             left_pending.oa_row_ids && right_pending.oa_row_ids
             or left_pending.bank_transaction_ids && right_pending.bank_transaction_ids
         )
        where left_pending.status = 'active'
          and right_pending.status = 'active'
    ) then
        raise exception 'Cannot migrate overlapping active OA pending relations.';
    end if;
end $$;

create temporary table oa_pending_relation_migration_plan on commit drop as
select
    pending.*,
    coalesce(
        active_relation.case_id,
        nullif(btrim(pending.migrated_from_workbench_case_id), ''),
        pending.relation_id
    ) as target_case_id
from app.oa_pending_payment_bank_relations pending
left join lateral (
    select relation.case_id
    from app.workbench_pair_relations relation
    where relation.status = 'active'
      and relation.row_ids && (pending.oa_row_ids || pending.bank_transaction_ids)
    order by relation.updated_at desc, relation.case_id
    limit 1
) active_relation on true
where pending.status = 'active';

do $$
begin
    if exists (
        select 1
        from oa_pending_relation_migration_plan plan
        join app.workbench_pair_relations relation on relation.case_id = plan.target_case_id
        where relation.status = 'active'
          and not relation.row_ids && (plan.oa_row_ids || plan.bank_transaction_ids)
    ) then
        raise exception 'Cannot migrate OA pending relation into an unrelated active Workbench case.';
    end if;
end $$;

with plan_groups as (
    select
        plan.target_case_id,
        min(plan.scope_month) as pending_scope_month,
        (array_agg(plan.note order by plan.updated_at desc nulls last))[1] as pending_note,
        (array_agg(plan.amount_check order by plan.updated_at desc nulls last))[1] as pending_amount_check,
        (array_agg(plan.source_versions order by plan.updated_at desc nulls last))[1] as pending_source_versions,
        (array_agg(plan.created_by order by plan.created_at nulls last))[1] as pending_created_by,
        min(plan.created_at) as pending_created_at,
        array_agg(plan.relation_id order by plan.relation_id) as pending_relation_ids
    from oa_pending_relation_migration_plan plan
    group by plan.target_case_id
),
member_candidates as (
    select
        groups.target_case_id,
        member.row_id,
        member.row_type,
        member.priority,
        member.ordinality
    from plan_groups groups
    left join app.workbench_pair_relations relation on relation.case_id = groups.target_case_id
    cross join lateral (
        select ids.row_id, coalesce(types.row_type, '') as row_type, 0 as priority, ids.ordinality
        from unnest(coalesce(relation.row_ids, array[]::text[])) with ordinality as ids(row_id, ordinality)
        left join unnest(coalesce(relation.row_types, array[]::text[])) with ordinality as types(row_type, ordinality)
          on types.ordinality = ids.ordinality
        union all
        select oa_id, 'oa', 1, oa_order
        from oa_pending_relation_migration_plan plan
        cross join lateral unnest(plan.oa_row_ids) with ordinality as oa_rows(oa_id, oa_order)
        where plan.target_case_id = groups.target_case_id
        union all
        select bank_id, 'bank', 2, bank_order
        from oa_pending_relation_migration_plan plan
        cross join lateral unnest(plan.bank_transaction_ids) with ordinality as bank_rows(bank_id, bank_order)
        where plan.target_case_id = groups.target_case_id
    ) member
    where nullif(btrim(member.row_id), '') is not null
),
deduplicated_members as (
    select distinct on (target_case_id, row_id)
        target_case_id,
        row_id,
        case
            when row_type in ('oa', 'bank', 'invoice') then row_type
            when row_id like 'oa%%' then 'oa'
            when row_id like 'bank%%' or row_id like 'txn_%%' then 'bank'
            else 'invoice'
        end as row_type,
        priority,
        ordinality
    from member_candidates
    order by target_case_id, row_id, priority, ordinality
),
merged_members as (
    select
        target_case_id,
        array_agg(row_id order by priority, ordinality, row_id) as row_ids,
        array_agg(row_type order by priority, ordinality, row_id) as row_types
    from deduplicated_members
    group by target_case_id
),
merged_relations as (
    select
        groups.target_case_id as case_id,
        coalesce(nullif(relation.relation_mode, ''), 'manual_confirmed') as relation_mode,
        coalesce(relation.version, 0) + 1 as version,
        coalesce(relation.month_scope, groups.pending_scope_month) as month_scope,
        members.row_ids,
        members.row_types,
        coalesce(relation.note, groups.pending_note) as note,
        case
            when coalesce(relation.amount_check, '{}'::jsonb) <> '{}'::jsonb then relation.amount_check
            else coalesce(groups.pending_amount_check, '{}'::jsonb)
        end as amount_check,
        (
            coalesce(relation.special_metadata, '{}'::jsonb)
            - 'migrated_to_pending_relation_id'
            - 'migration'
        ) || jsonb_build_object(
            'origin', 'oa_pending_payment',
            'migrated_from_pending_relation_ids', to_jsonb(groups.pending_relation_ids),
            'migration', '0136_unify_in_progress_oa_workbench_relations'
        ) as special_metadata,
        case
            when coalesce(relation.source_versions, '{}'::jsonb) <> '{}'::jsonb then relation.source_versions
            else coalesce(groups.pending_source_versions, '{}'::jsonb)
        end as source_versions,
        coalesce(relation.created_by, groups.pending_created_by, 'migration:0136') as created_by,
        coalesce(relation.created_at, groups.pending_created_at, now()) as created_at
    from plan_groups groups
    join merged_members members on members.target_case_id = groups.target_case_id
    left join app.workbench_pair_relations relation on relation.case_id = groups.target_case_id
),
upserted as (
    insert into app.workbench_pair_relations(
        case_id, relation_mode, status, version, month_scope, row_ids, row_types,
        note, amount_check, special_metadata, source_versions, created_by, created_at,
        updated_at, withdrawn_by, withdrawn_at, raw_payload
    )
    select
        merged.case_id,
        merged.relation_mode,
        'active',
        merged.version,
        merged.month_scope,
        merged.row_ids,
        merged.row_types,
        merged.note,
        merged.amount_check,
        merged.special_metadata,
        merged.source_versions,
        merged.created_by,
        merged.created_at,
        now(),
        null,
        null,
        jsonb_build_object(
            'normalized_payload',
            jsonb_build_object(
                'case_id', merged.case_id,
                'relation_mode', merged.relation_mode,
                'status', 'active',
                'version', merged.version,
                'month_scope', to_char(merged.month_scope, 'YYYY-MM'),
                'row_ids', to_jsonb(merged.row_ids),
                'row_types', to_jsonb(merged.row_types),
                'note', merged.note,
                'amount_check', merged.amount_check,
                'special_metadata', merged.special_metadata,
                'source_versions', merged.source_versions,
                'created_by', merged.created_by,
                'created_at', merged.created_at,
                'updated_at', now()
            )
        )
    from merged_relations merged
    on conflict (case_id) do update set
        relation_mode = excluded.relation_mode,
        status = 'active',
        version = excluded.version,
        month_scope = excluded.month_scope,
        row_ids = excluded.row_ids,
        row_types = excluded.row_types,
        note = excluded.note,
        amount_check = excluded.amount_check,
        special_metadata = excluded.special_metadata,
        source_versions = excluded.source_versions,
        raw_payload = excluded.raw_payload,
        updated_at = now(),
        withdrawn_by = null,
        withdrawn_at = null
    returning id, case_id, raw_payload
)
insert into app.workbench_pair_relation_history(
    relation_id, case_id, event_type, actor_id, before_payload, after_payload, raw_payload
)
select
    upserted.id,
    upserted.case_id,
    'migrate_oa_pending_relation_to_formal',
    'migration:0136',
    jsonb_agg(
        jsonb_build_object(
            'relation_id', plan.relation_id,
            'status', plan.status,
            'oa_row_ids', plan.oa_row_ids,
            'bank_transaction_ids', plan.bank_transaction_ids
        ) order by plan.relation_id
    ),
    upserted.raw_payload->'normalized_payload',
    jsonb_build_object(
        'normalized_payload',
        jsonb_build_object(
            'operation_type', 'migrate_oa_pending_relation_to_formal',
            'case_id', upserted.case_id,
            'created_by', 'migration:0136'
        )
    )
from upserted
join oa_pending_relation_migration_plan plan on plan.target_case_id = upserted.case_id
group by upserted.id, upserted.case_id, upserted.raw_payload;

insert into app.oa_pending_payment_bank_relation_events(
    relation_id, event_type, actor_id, before_payload, after_payload, raw_payload
)
select
    plan.relation_id,
    'migrate_to_formal_workbench_relation',
    'migration:0136',
    jsonb_build_object(
        'status', plan.status,
        'oa_row_ids', plan.oa_row_ids,
        'bank_transaction_ids', plan.bank_transaction_ids
    ),
    jsonb_build_object(
        'status', 'promoted',
        'promoted_workbench_case_id', plan.target_case_id
    ),
    jsonb_build_object(
        'normalized_payload',
        jsonb_build_object('source', 'migration:0136')
    )
from oa_pending_relation_migration_plan plan;

update app.oa_pending_payment_bank_relations pending
set
    status = 'promoted',
    version = pending.version + 1,
    promoted_workbench_case_id = plan.target_case_id,
    updated_at = now(),
    raw_payload = jsonb_set(
        jsonb_set(
            coalesce(pending.raw_payload, '{}'::jsonb),
            '{normalized_payload,status}',
            to_jsonb('promoted'::text),
            true
        ),
        '{normalized_payload,promoted_workbench_case_id}',
        to_jsonb(plan.target_case_id),
        true
    )
from oa_pending_relation_migration_plan plan
where pending.relation_id = plan.relation_id;

update app.bank_transaction_relation_claims claim
set
    status = 'promoted',
    released_by = 'migration:0136',
    released_at = now(),
    release_reason = 'Formal Workbench relation is now the sole active owner.',
    updated_at = now(),
    raw_payload = jsonb_set(
        jsonb_set(
            coalesce(claim.raw_payload, '{}'::jsonb),
            '{normalized_payload,status}',
            to_jsonb('promoted'::text),
            true
        ),
        '{normalized_payload,release_reason}',
        to_jsonb('Formal Workbench relation is now the sole active owner.'::text),
        true
    )
where claim.status = 'active'
  and claim.owner_type = 'oa_pending_payment_relation'
  and claim.owner_id = any(
      select plan.relation_id
      from oa_pending_relation_migration_plan plan
  );

do $$
declare
    role_name text;
begin
    foreach role_name in array array['fin_ops_app_runtime', 'fin_ops_api', 'fin_ops_worker', 'fin_ops_readonly']
    loop
        if exists (select 1 from pg_roles where rolname = role_name) then
            execute format(
                'revoke insert, update, delete on app.oa_pending_payment_bank_relations, app.bank_transaction_relation_claims, app.oa_pending_payment_bank_relation_events from %I',
                role_name
            );
            execute format(
                'grant select on app.oa_pending_payment_bank_relations, app.bank_transaction_relation_claims, app.oa_pending_payment_bank_relation_events to %I',
                role_name
            );
        end if;
    end loop;
end $$;
