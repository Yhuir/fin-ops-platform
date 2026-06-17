alter table read_model.oa_pending_payment_rows
    add column if not exists oa_workflow_status text;

update read_model.oa_pending_payment_rows
set oa_workflow_status = nullif(payload->'oa'->>'workflowStatus', '')
where oa_workflow_status is null
  and nullif(payload->'oa'->>'workflowStatus', '') is not null;

create index if not exists oa_pending_payment_rows_workflow_scope_idx
    on read_model.oa_pending_payment_rows (oa_workflow_status, scope_key, scope_month);
