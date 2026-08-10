create index if not exists import_files_lifecycle_batch_idx
    on app.import_files (
        (coalesce(
            raw_payload->'normalized_payload'->>'batch_id',
            raw_payload->'normalized_payload'->>'preview_batch_id'
        )),
        uploaded_at desc,
        id desc
    )
    where coalesce(
        raw_payload->'normalized_payload'->>'batch_id',
        raw_payload->'normalized_payload'->>'preview_batch_id'
    ) is not null;

create index if not exists import_jobs_session_latest_idx
    on job.import_jobs (import_session_id, created_at desc, id desc)
    where import_session_id is not null;
