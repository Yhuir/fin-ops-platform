-- Bound Cost all-scope access convergence without changing refresh semantics.
--
-- The Cost parent gate reads the latest durable Workbench and Bank Detail
-- versions for every month. Keep these indexes partial so unrelated read
-- models do not pay their storage/write cost.

create index if not exists read_model_dirty_scopes_workbench_latest_version_idx
    on job.read_model_dirty_scopes (
        tenant_id,
        scope_type,
        scope_key,
        source_version desc,
        updated_at desc,
        id desc
    )
    where scope_type = 'workbench';

create index if not exists read_model_dirty_scopes_bank_detail_latest_version_idx
    on job.read_model_dirty_scopes (
        tenant_id,
        scope_type,
        scope_key,
        source_version desc,
        updated_at desc,
        id desc
    )
    where scope_type = 'bank_detail';

-- Workbench canonical source proofs select the latest scoped exception and
-- override timestamps before comparing an active generation.

create index if not exists workbench_exception_cases_scope_updated_idx
    on app.workbench_exception_cases (scope_month, updated_at desc);

create index if not exists workbench_row_overrides_scope_updated_idx
    on app.workbench_row_overrides (scope_month, updated_at desc);
