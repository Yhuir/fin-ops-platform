-- 0101 created deterministic historical reconciliation tasks before the task payload
-- timestamp contract was enforced. Preserve the typed canonical columns and copy only
-- missing payload timestamps so service hydration and ordering remain deterministic.
with reconciliation_task_payloads as (
    select
        task.id,
        case
            when jsonb_typeof(task.raw_payload) = 'object'
             and jsonb_typeof(task.raw_payload->'normalized_payload') = 'object'
            then task.raw_payload
            when jsonb_typeof(task.raw_payload) = 'object'
            then jsonb_set(task.raw_payload, '{normalized_payload}', '{}'::jsonb, true)
            else jsonb_build_object('normalized_payload', '{}'::jsonb)
        end as base_payload,
        case
            when jsonb_typeof(task.raw_payload->'normalized_payload') = 'object'
            then task.raw_payload->'normalized_payload'
            else '{}'::jsonb
        end as normalized_payload,
        task.created_at,
        task.updated_at
    from app.etc_reconciliation_tasks task
    where nullif(task.raw_payload->'normalized_payload'->>'created_at', '') is null
       or nullif(task.raw_payload->'normalized_payload'->>'updated_at', '') is null
)
update app.etc_reconciliation_tasks task
set raw_payload = jsonb_set(
        payload.base_payload,
        '{normalized_payload}',
        payload.normalized_payload
        || case
            when nullif(payload.normalized_payload->>'created_at', '') is null
            then jsonb_build_object('created_at', payload.created_at)
            else '{}'::jsonb
        end
        || case
            when nullif(payload.normalized_payload->>'updated_at', '') is null
            then jsonb_build_object('updated_at', payload.updated_at)
            else '{}'::jsonb
        end,
        true
    )
from reconciliation_task_payloads payload
where task.id = payload.id;
