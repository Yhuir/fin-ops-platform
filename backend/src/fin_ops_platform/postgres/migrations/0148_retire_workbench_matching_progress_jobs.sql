-- Retire the synthetic Workbench matching progress jobs. Actual matching work
-- is owned by job.workbench_matching_dirty_scopes and its dedicated worker.

set local lock_timeout = '5s';
set local statement_timeout = '30s';

with retired_jobs as (
    select
        id,
        now() as retired_at,
        coalesce(raw_payload->'normalized_payload', '{}'::jsonb) as normalized_payload
    from job.background_jobs
    where job_type = 'workbench_matching'
      and status in ('queued', 'running')
    for update
)
update job.background_jobs as jobs
set
    status = 'superseded',
    progress = jobs.progress || jsonb_build_object(
        'phase', 'superseded',
        'message', '历史关联台匹配进度已停用。'
    ),
    error = null,
    attention = '{}'::jsonb,
    raw_payload = jsonb_set(
        jobs.raw_payload,
        '{normalized_payload}',
        retired_jobs.normalized_payload || jsonb_build_object(
            'status', 'superseded',
            'phase', 'superseded',
            'message', '历史关联台匹配进度已停用。',
            'short_label', '关联台匹配进度已停用',
            'error', null,
            'finished_at', retired_jobs.retired_at,
            'superseded_at', retired_jobs.retired_at,
            'updated_at', retired_jobs.retired_at
        ),
        true
    ),
    updated_at = retired_jobs.retired_at
from retired_jobs
where jobs.id = retired_jobs.id;
