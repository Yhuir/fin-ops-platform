alter table app.oa_applications
    add column if not exists workflow_status text;

update app.oa_applications
set workflow_status = case
        when nullif(normalized_payload->>'workflow_status', '') in ('completed', 'in_progress')
            then nullif(normalized_payload->>'workflow_status', '')
        when nullif(normalized_payload->>'process_status', '') in ('completed', 'in_progress')
            then nullif(normalized_payload->>'process_status', '')
        when nullif(normalized_payload->'detail_fields'->>'流程状态', '') = '已完成'
            then 'completed'
        when nullif(normalized_payload->'detail_fields'->>'流程状态', '') = '进行中'
            then 'in_progress'
        else workflow_status
    end
where workflow_status is null;

create index if not exists oa_applications_workflow_status_scope_idx
    on app.oa_applications (workflow_status, scope_month, row_id);
