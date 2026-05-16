create table app.import_batches (
  id uuid primary key default gen_random_uuid(),
  batch_type text not null,
  source_type text not null,
  source_name text not null,
  status text not null,
  idempotency_key text not null,
  row_count integer not null default 0,
  success_count integer not null default 0,
  error_count integer not null default 0,
  duplicate_count integer not null default 0,
  suspected_duplicate_count integer not null default 0,
  updated_count integer not null default 0,
  checksum text,
  source_system text,
  source_reference text,
  source_metadata jsonb not null default '{}'::jsonb,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  updated_by text,
  confirmed_at timestamptz,
  reverted_at timestamptz,
  reverted_by text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint import_batches_batch_type_chk check (
    batch_type in (
      'output_invoice',
      'input_invoice',
      'bank_transaction',
      'tax_certified',
      'etc',
      'oa_sync',
      'mongo_migration'
    )
  ),
  constraint import_batches_status_chk check (
    status in (
      'pending',
      'completed',
      'completed_with_errors',
      'reverted',
      'failed'
    )
  ),
  constraint import_batches_row_count_chk check (row_count >= 0),
  constraint import_batches_success_count_chk check (success_count >= 0),
  constraint import_batches_error_count_chk check (error_count >= 0),
  constraint import_batches_duplicate_count_chk check (duplicate_count >= 0),
  constraint import_batches_suspected_duplicate_count_chk check (suspected_duplicate_count >= 0),
  constraint import_batches_updated_count_chk check (updated_count >= 0),
  constraint import_batches_source_metadata_object_chk check (jsonb_typeof(source_metadata) = 'object'),
  constraint import_batches_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint import_batches_idempotency_key_uk unique (idempotency_key)
);

create trigger import_batches_set_updated_at
before update on app.import_batches
for each row
execute function app.set_updated_at();

create unique index import_batches_legacy_collection_id_uk
  on app.import_batches (legacy_collection, legacy_id)
  where legacy_collection is not null;

create index import_batches_status_created_at_idx
  on app.import_batches (status, created_at desc);

create index import_batches_batch_type_status_idx
  on app.import_batches (batch_type, status);

create index import_batches_created_by_created_at_idx
  on app.import_batches (created_by, created_at desc);

create table app.file_objects (
  id uuid primary key default gen_random_uuid(),
  storage_provider text not null,
  bucket text not null,
  object_key text not null,
  object_version text,
  file_name text not null,
  content_type text,
  byte_size bigint not null,
  sha256 text not null,
  etag text,
  storage_class text,
  metadata jsonb not null default '{}'::jsonb,
  legacy_gridfs_id text,
  purpose text not null,
  created_by text,
  created_at timestamptz not null default now(),
  constraint file_objects_storage_provider_chk check (
    storage_provider in ('minio', 's3')
  ),
  constraint file_objects_byte_size_chk check (byte_size >= 0),
  constraint file_objects_sha256_chk check (sha256 ~ '^[0-9a-f]{64}$'),
  constraint file_objects_metadata_object_chk check (jsonb_typeof(metadata) = 'object')
);

create unique index file_objects_object_location_uk
  on app.file_objects (bucket, object_key, object_version) nulls not distinct;

create unique index file_objects_legacy_gridfs_id_uk
  on app.file_objects (legacy_gridfs_id)
  where legacy_gridfs_id is not null;

create index file_objects_sha256_idx
  on app.file_objects (sha256);

create index file_objects_purpose_created_at_idx
  on app.file_objects (purpose, created_at desc);

create table app.import_files (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null,
  file_object_id uuid not null,
  file_role text not null,
  parse_status text not null,
  row_count integer not null default 0,
  error_count integer not null default 0,
  template_key text,
  checksum text,
  source_file_id text,
  source_path text,
  source_metadata jsonb not null default '{}'::jsonb,
  legacy_collection text,
  legacy_id text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint import_files_batch_id_fkey
    foreign key (batch_id) references app.import_batches(id),
  constraint import_files_file_object_id_fkey
    foreign key (file_object_id) references app.file_objects(id),
  constraint import_files_parse_status_chk check (
    parse_status in (
      'pending',
      'queued',
      'parsing',
      'parsed',
      'parsed_with_errors',
      'failed',
      'skipped'
    )
  ),
  constraint import_files_row_count_chk check (row_count >= 0),
  constraint import_files_error_count_chk check (error_count >= 0),
  constraint import_files_source_metadata_object_chk check (jsonb_typeof(source_metadata) = 'object'),
  constraint import_files_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint import_files_batch_file_role_uk unique (batch_id, file_object_id, file_role)
);

create trigger import_files_set_updated_at
before update on app.import_files
for each row
execute function app.set_updated_at();

create unique index import_files_legacy_collection_id_uk
  on app.import_files (legacy_collection, legacy_id)
  where legacy_collection is not null;

create index import_files_batch_id_idx
  on app.import_files (batch_id);

create index import_files_file_object_id_idx
  on app.import_files (file_object_id);

create index import_files_parse_status_created_at_idx
  on app.import_files (parse_status, created_at desc);
