-- OA pending-payment all-scope freshness gate hot path.
--
-- The gate must select the greatest durable source version for every month.
-- Keep this index partial so other read models do not pay its write/storage cost.

create index if not exists read_model_dirty_scopes_oa_latest_version_idx
    on job.read_model_dirty_scopes (
        tenant_id,
        scope_type,
        scope_key,
        source_version desc,
        updated_at desc,
        id desc
    )
    where scope_type = 'oa_pending_payment';
