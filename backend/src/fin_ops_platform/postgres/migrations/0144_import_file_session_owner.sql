update app.import_files import_file
set
    uploaded_by = import_batch.imported_by,
    raw_payload = jsonb_set(
        coalesce(import_file.raw_payload, '{}'::jsonb),
        '{normalized_payload}',
        coalesce(import_file.raw_payload->'normalized_payload', '{}'::jsonb)
            || jsonb_build_object('imported_by', import_batch.imported_by),
        true
    )
from app.import_batches import_batch
where nullif(import_batch.imported_by, '') is not null
  and coalesce(
      import_file.raw_payload->'normalized_payload'->>'batch_id',
      import_file.raw_payload->'normalized_payload'->>'preview_batch_id'
  ) in (import_batch.legacy_mongo_id, import_batch.id::text)
  and nullif(coalesce(
      import_file.raw_payload->'normalized_payload'->>'imported_by',
      import_file.uploaded_by
  ), '') is null;
