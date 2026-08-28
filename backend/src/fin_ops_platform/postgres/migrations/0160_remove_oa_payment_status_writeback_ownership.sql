set local lock_timeout = '10s';
set local statement_timeout = '2min';

drop table if exists app.oa_payment_status_writeback_states;

with canonical_oa as (
    select 'default'::text as tenant_id, row_id as oa_id
    from app.oa_applications
    where nullif(btrim(row_id), '') is not null
      and (
          workflow_status is null
          or workflow_status = ''
          or workflow_status in ('completed', '已完成', 'approved', 'APPROVED', 'Approved', '2')
      )
    union
    select tenant_id, oa_id
    from app.oa_pending_payment_admissions
    where nullif(btrim(oa_id), '') is not null
)
insert into job.outbox_events(
    tenant_id, event_type, aggregate_type, aggregate_id, scope_type, scope_key,
    dedupe_key, payload, schema_version, source_version, priority, raw_payload
)
select
    admitted.tenant_id,
    'oa.payment_status.reconcile',
    'oa_payment_status',
    admitted.oa_id,
    'oa_payment_status',
    admitted.oa_id,
    'oa.payment_status.reconcile:rule-0160:' || md5(admitted.tenant_id || ':' || admitted.oa_id),
    jsonb_build_object(
        'oa_row_ids', jsonb_build_array(admitted.oa_id),
        'reason', 'migration_0160_rule_reconcile'
    ),
    1,
    1,
    'high',
    jsonb_build_object('migration', '0160_remove_oa_payment_status_writeback_ownership')
from canonical_oa admitted
on conflict (tenant_id, dedupe_key)
where dedupe_key is not null and status = 'pending'
do nothing;
