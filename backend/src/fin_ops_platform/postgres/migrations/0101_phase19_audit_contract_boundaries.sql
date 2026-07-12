alter table app.import_files
    add column if not exists audit_contract_revision text;

alter table app.import_files
    alter column audit_contract_revision set default 'import-page-audit.v1';

comment on column app.import_files.audit_contract_revision is
    'Versioned strict page-audit contract. NULL identifies pre-contract history whose workflow provenance must not be fabricated.';

alter table app.etc_import_sessions
    add column if not exists audit_contract_revision text;

alter table app.etc_import_sessions
    alter column audit_contract_revision set default 'etc-import-page-audit.v1';

comment on column app.etc_import_sessions.audit_contract_revision is
    'Versioned strict ETC import audit contract. NULL identifies historical/synthetic sessions outside the durable session contract.';

update app.workbench_pair_relations
set relation_mode = 'batch_accounting',
    raw_payload = jsonb_set(
        jsonb_set(
            case
                when jsonb_typeof(coalesce(raw_payload, '{}'::jsonb)->'normalized_payload') = 'object'
                then coalesce(raw_payload, '{}'::jsonb)
                else jsonb_set(coalesce(raw_payload, '{}'::jsonb), '{normalized_payload}', '{}'::jsonb, true)
            end,
            '{normalized_payload,relation_mode}',
            '"batch_accounting"'::jsonb,
            true
        ),
        '{relation_mode}',
        '"batch_accounting"'::jsonb,
        true
    ),
    updated_at = now()
where status = 'active'
  and special_metadata->>'source' = 'batch_accounting'
  and relation_mode is distinct from 'batch_accounting';

insert into app.etc_reconciliation_tasks(
    task_id,
    status,
    scope_month,
    result_summary,
    version,
    raw_payload
)
select
    batch.task_id,
    'imported',
    batch.scope_month,
    '{}'::jsonb,
    1,
    jsonb_build_object(
        'normalized_payload',
        jsonb_build_object(
            'task_id', batch.task_id,
            'status', 'imported',
            'version', 1,
            'title', coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'title', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                '历史ETC批次 ' || coalesce(to_char(batch.scope_month, 'YYYY-MM'), batch.business_batch_id)
            )
        )
    )
from app.etc_business_batches batch
where batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
  and nullif(batch.task_id, '') is not null
  and not exists (
      select 1
      from app.etc_reconciliation_tasks task
      where task.task_id = batch.task_id
        and task.status <> 'deleted'
  )
on conflict (task_id) do nothing;

with task_titles as (
    select task.task_id,
           coalesce(
               nullif(task.raw_payload->'normalized_payload'->>'title', ''),
               nullif(task.raw_payload->>'title', ''),
               task.task_id
           ) as title
    from app.etc_reconciliation_tasks task
    where task.status <> 'deleted'
)
update app.etc_business_batches batch
set raw_payload = jsonb_set(
        case
            when jsonb_typeof(coalesce(batch.raw_payload, '{}'::jsonb)->'normalized_payload') = 'object'
            then coalesce(batch.raw_payload, '{}'::jsonb)
            else jsonb_set(coalesce(batch.raw_payload, '{}'::jsonb), '{normalized_payload}', '{}'::jsonb, true)
        end,
        '{normalized_payload,title}',
        to_jsonb(task_titles.title),
        true
    ),
    updated_at = now()
from task_titles
where batch.task_id = task_titles.task_id
  and batch.status in (
      'draft', 'reviewing', 'ready_for_import', 'importing', 'imported', 'import_failed',
      'import_partial_failed', 'oa_draft_creating', 'oa_draft_failed', 'oa_confirmation_pending',
      'not_submitted', 'manually_marked_not_submitted', 'migration_conflict',
      'business_batch_invariant_broken', 'oa_submitted', 'manually_marked_submitted', 'closed'
  )
  and coalesce(batch.raw_payload->'normalized_payload'->>'title', '') is distinct from task_titles.title;

with active_business_batches as (
    select business_batch_id
    from app.etc_business_batches
    where status in (
        'draft', 'reviewing', 'ready_for_import', 'importing', 'imported', 'import_failed',
        'import_partial_failed', 'oa_draft_creating', 'oa_draft_failed', 'oa_confirmation_pending',
        'not_submitted', 'manually_marked_not_submitted', 'migration_conflict',
        'business_batch_invariant_broken', 'oa_submitted', 'manually_marked_submitted', 'closed'
    )
), orphaned_invoice as (
    select invoice.id, invoice.batch_id
    from app.etc_invoices invoice
    where invoice.status <> 'deleted'
      and nullif(invoice.business_batch_id, '') is not null
      and not exists (
          select 1
          from active_business_batches batch
          where batch.business_batch_id = invoice.business_batch_id
      )
)
update app.etc_invoices invoice
set business_batch_id = null,
    raw_payload = jsonb_set(
        jsonb_set(
            case
                when jsonb_typeof(coalesce(invoice.raw_payload, '{}'::jsonb)->'normalized_payload') = 'object'
                then coalesce(invoice.raw_payload, '{}'::jsonb)
                else jsonb_set(coalesce(invoice.raw_payload, '{}'::jsonb), '{normalized_payload}', '{}'::jsonb, true)
            end,
            '{normalized_payload,business_batch_id}',
            'null'::jsonb,
            true
        ),
        '{normalized_payload,import_batch_id}',
        to_jsonb(orphaned_invoice.batch_id),
        true
    ),
    updated_at = now()
from orphaned_invoice
where invoice.id = orphaned_invoice.id;

with task_files as (
    select file.task_id,
           jsonb_agg(
               coalesce(file.raw_payload->'normalized_payload', file.raw_payload, '{}'::jsonb)
               || jsonb_build_object('file_id', file.file_id)
               order by file.file_id
           ) as source_files
    from app.etc_reconciliation_files file
    where file.status <> 'deleted'
      and nullif(file.task_id, '') is not null
    group by file.task_id
)
update app.etc_reconciliation_tasks task
set raw_payload = jsonb_set(
        case
            when jsonb_typeof(coalesce(task.raw_payload, '{}'::jsonb)->'normalized_payload') = 'object'
            then coalesce(task.raw_payload, '{}'::jsonb)
            else jsonb_set(coalesce(task.raw_payload, '{}'::jsonb), '{normalized_payload}', '{}'::jsonb, true)
        end,
        '{normalized_payload,source_files}',
        task_files.source_files,
        true
    ),
    updated_at = now()
from task_files
where task.task_id = task_files.task_id
  and task.status <> 'deleted'
  and coalesce(task.raw_payload->'normalized_payload'->'source_files', '[]'::jsonb)
      is distinct from task_files.source_files;
