set local lock_timeout = '10s';
set local statement_timeout = '1min';

do $$
declare
    decision record;
    reviewer_account text;
    reviewer_name text;
    account_count integer;
    updated_count integer;
    normalized_payload jsonb;
begin
    for decision in
        select
            exception.id,
            exception.case_id,
            exception.updated_by,
            exception.updated_at,
            exception.raw_payload
        from app.workbench_exception_cases exception
        where exception.scenario = 'workbench_anomaly_review'
          and nullif(
              btrim(exception.raw_payload#>>'{normalized_payload,actor_account}'),
              ''
          ) is null
        order by exception.case_id
        for update
    loop
        if nullif(btrim(decision.updated_by), '') is null then
            raise exception '0156: anomaly review % has no internal reviewer id', decision.case_id;
        end if;
        if jsonb_typeof(decision.raw_payload->'normalized_payload') is distinct from 'object' then
            raise exception '0156: anomaly review % has no normalized payload', decision.case_id;
        end if;

        select count(distinct lower(btrim(event.actor_account)))::integer
        into account_count
        from audit.events event
        where event.actor_id = decision.updated_by
          and nullif(btrim(event.actor_account), '') is not null;

        if account_count <> 1 then
            raise exception
                '0156: anomaly reviewer % for case % has % authoritative accounts',
                decision.updated_by,
                decision.case_id,
                account_count;
        end if;

        select btrim(event.actor_account)
        into strict reviewer_account
        from audit.events event
        where event.actor_id = decision.updated_by
          and nullif(btrim(event.actor_account), '') is not null
        order by event.occurred_at desc, event.id desc
        limit 1;

        select coalesce((
            select btrim(event.actor_name)
            from audit.events event
            where event.actor_id = decision.updated_by
              and lower(btrim(event.actor_account)) = lower(reviewer_account)
              and nullif(btrim(event.actor_name), '') is not null
            order by event.occurred_at desc, event.id desc
            limit 1
        ), '')
        into reviewer_name;

        normalized_payload := jsonb_set(
            jsonb_set(
                decision.raw_payload->'normalized_payload',
                '{actor_account}',
                to_jsonb(reviewer_account),
                true
            ),
            '{actor_name}',
            to_jsonb(reviewer_name),
            true
        );

        update app.workbench_exception_cases exception
        set raw_payload = jsonb_set(
            decision.raw_payload,
            '{normalized_payload}',
            normalized_payload,
            false
        )
        where exception.id = decision.id
          and nullif(
              btrim(exception.raw_payload#>>'{normalized_payload,actor_account}'),
              ''
          ) is null;
        get diagnostics updated_count = row_count;
        if updated_count <> 1 then
            raise exception '0156: anomaly review % changed while backfilling', decision.case_id;
        end if;

        insert into app.workbench_exception_case_events(
            exception_case_id,
            case_id,
            event_type,
            actor_id,
            payload,
            raw_payload
        ) values (
            decision.id,
            decision.case_id,
            'workbench_anomaly_reviewer_identity_backfilled',
            'system:migration:0156',
            jsonb_build_object(
                'reviewer_id', decision.updated_by,
                'reviewer_account', reviewer_account,
                'reviewer_name', reviewer_name,
                'reviewed_at', decision.updated_at
            ),
            jsonb_build_object(
                'migration', '0156_backfill_workbench_anomaly_reviewer_identity',
                'reviewer_id', decision.updated_by,
                'reviewer_account', reviewer_account,
                'reviewer_name', reviewer_name,
                'reviewed_at', decision.updated_at
            )
        );
    end loop;
end $$;
