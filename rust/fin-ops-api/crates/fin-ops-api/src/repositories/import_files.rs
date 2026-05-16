use async_trait::async_trait;
use serde_json::Value;
use sqlx::{PgPool, Row};
use uuid::Uuid;

#[derive(Clone, Debug)]
pub struct ImportBatchRow {
    pub id: Uuid,
    pub batch_type: String,
    pub source_type: String,
    pub source_name: Option<String>,
    pub status: String,
    pub row_count: i32,
    pub success_count: i32,
    pub error_count: i32,
    pub duplicate_count: i32,
    pub suspected_duplicate_count: i32,
    pub updated_count: i32,
    pub checksum: Option<String>,
    pub source_system: Option<String>,
    pub source_reference: Option<String>,
    pub source_metadata: Value,
    pub legacy_session_id: Option<String>,
    pub legacy_import_id: Option<String>,
    pub created_by: Option<String>,
    pub updated_by: Option<String>,
    pub confirmed_at: Option<String>,
    pub reverted_at: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug)]
pub struct ImportFileRow {
    pub id: Uuid,
    pub batch_id: Uuid,
    pub file_object_id: Option<Uuid>,
    pub file_role: String,
    pub parse_status: String,
    pub row_count: i32,
    pub error_count: i32,
    pub template_key: Option<String>,
    pub checksum: Option<String>,
    pub source_file_id: Option<String>,
    pub source_path: Option<String>,
    pub source_metadata: Value,
    pub legacy_file_id: Option<String>,
    pub legacy_gridfs_id: Option<String>,
    pub file_name: Option<String>,
    pub content_type: Option<String>,
    pub byte_size: Option<i64>,
    pub sha256: Option<String>,
    pub storage_provider: Option<String>,
    pub bucket: Option<String>,
    pub object_key: Option<String>,
    pub object_version: Option<String>,
    pub etag: Option<String>,
    pub storage_class: Option<String>,
    pub purpose: Option<String>,
    pub file_object_metadata: Option<Value>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug)]
pub struct FileObjectRow {
    pub id: Uuid,
    pub storage_provider: String,
    pub bucket: String,
    pub object_key: String,
    pub object_version: Option<String>,
    pub file_name: String,
    pub content_type: Option<String>,
    pub byte_size: i64,
    pub sha256: String,
    pub etag: Option<String>,
    pub storage_class: Option<String>,
    pub metadata: Value,
    pub legacy_gridfs_id: Option<String>,
    pub purpose: String,
    pub created_by: Option<String>,
    pub created_at: String,
}

#[derive(Debug, thiserror::Error)]
pub enum ImportFileRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait ImportFileRepository: Send + Sync {
    async fn list_batches(
        &self,
        status: Option<&str>,
        batch_type: Option<&str>,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<ImportBatchRow>, ImportFileRepositoryError>;

    async fn find_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Option<ImportBatchRow>, ImportFileRepositoryError>;

    async fn list_files_for_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Vec<ImportFileRow>, ImportFileRepositoryError>;

    async fn find_import_file(
        &self,
        file_id: Uuid,
    ) -> Result<Option<ImportFileRow>, ImportFileRepositoryError>;

    async fn find_file_object(
        &self,
        file_object_id: Uuid,
    ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError>;

    async fn find_file_object_by_sha256(
        &self,
        sha256: &str,
    ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError>;
}

#[derive(Clone)]
pub struct SqlxImportFileRepository {
    pool: PgPool,
}

impl SqlxImportFileRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl ImportFileRepository for SqlxImportFileRepository {
    async fn list_batches(
        &self,
        status: Option<&str>,
        batch_type: Option<&str>,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<ImportBatchRow>, ImportFileRepositoryError> {
        let rows = sqlx::query(BATCH_SELECT_SQL)
            .bind(status)
            .bind(batch_type)
            .bind(limit)
            .bind(offset)
            .fetch_all(&self.pool)
            .await?;

        rows.into_iter()
            .map(|row| import_batch_from_row(row).map_err(ImportFileRepositoryError::from))
            .collect()
    }

    async fn find_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Option<ImportBatchRow>, ImportFileRepositoryError> {
        let row = sqlx::query(BATCH_BY_ID_SQL)
            .bind(batch_id)
            .fetch_optional(&self.pool)
            .await?;

        row.map(import_batch_from_row)
            .transpose()
            .map_err(ImportFileRepositoryError::from)
    }

    async fn list_files_for_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Vec<ImportFileRow>, ImportFileRepositoryError> {
        let rows = sqlx::query(IMPORT_FILES_BY_BATCH_SQL)
            .bind(batch_id)
            .fetch_all(&self.pool)
            .await?;

        rows.into_iter()
            .map(|row| import_file_from_row(row).map_err(ImportFileRepositoryError::from))
            .collect()
    }

    async fn find_import_file(
        &self,
        file_id: Uuid,
    ) -> Result<Option<ImportFileRow>, ImportFileRepositoryError> {
        let row = sqlx::query(IMPORT_FILE_BY_ID_SQL)
            .bind(file_id)
            .fetch_optional(&self.pool)
            .await?;

        row.map(import_file_from_row)
            .transpose()
            .map_err(ImportFileRepositoryError::from)
    }

    async fn find_file_object(
        &self,
        file_object_id: Uuid,
    ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError> {
        let row = sqlx::query(FILE_OBJECT_BY_ID_SQL)
            .bind(file_object_id)
            .fetch_optional(&self.pool)
            .await?;

        row.map(file_object_from_row)
            .transpose()
            .map_err(ImportFileRepositoryError::from)
    }

    async fn find_file_object_by_sha256(
        &self,
        sha256: &str,
    ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError> {
        let row = sqlx::query(FILE_OBJECT_BY_SHA256_SQL)
            .bind(sha256)
            .fetch_optional(&self.pool)
            .await?;

        row.map(file_object_from_row)
            .transpose()
            .map_err(ImportFileRepositoryError::from)
    }
}

const BATCH_SELECT_SQL: &str = r#"
select
    id,
    batch_type,
    source_type,
    source_name,
    status,
    row_count,
    success_count,
    error_count,
    duplicate_count,
    suspected_duplicate_count,
    updated_count,
    checksum,
    source_system,
    source_reference,
    source_metadata,
    case when legacy_collection = 'import_sessions' then legacy_id end as legacy_session_id,
    case when legacy_collection <> 'import_sessions' then legacy_id end as legacy_import_id,
    created_by,
    updated_by,
    to_char(confirmed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as confirmed_at,
    to_char(reverted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as reverted_at,
    to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
    to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from app.import_batches
where ($1::text is null or status = $1)
  and ($2::text is null or batch_type = $2)
order by created_at desc, id desc
limit $3 offset $4
"#;

const BATCH_BY_ID_SQL: &str = r#"
select
    id,
    batch_type,
    source_type,
    source_name,
    status,
    row_count,
    success_count,
    error_count,
    duplicate_count,
    suspected_duplicate_count,
    updated_count,
    checksum,
    source_system,
    source_reference,
    source_metadata,
    case when legacy_collection = 'import_sessions' then legacy_id end as legacy_session_id,
    case when legacy_collection <> 'import_sessions' then legacy_id end as legacy_import_id,
    created_by,
    updated_by,
    to_char(confirmed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as confirmed_at,
    to_char(reverted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as reverted_at,
    to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
    to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from app.import_batches
where id = $1
"#;

const IMPORT_FILES_BY_BATCH_SQL: &str = r#"
select
    f.id,
    f.batch_id,
    f.file_object_id,
    f.file_role,
    f.parse_status,
    f.row_count,
    f.error_count,
    f.template_key,
    f.checksum,
    f.source_file_id,
    f.source_path,
    f.source_metadata,
    f.legacy_id as legacy_file_id,
    o.legacy_gridfs_id,
    o.file_name,
    o.content_type,
    o.byte_size,
    o.sha256,
    o.storage_provider,
    o.bucket,
    o.object_key,
    o.object_version,
    o.etag,
    o.storage_class,
    o.purpose,
    o.metadata as file_object_metadata,
    to_char(f.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
    to_char(f.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from app.import_files f
left join app.file_objects o on o.id = f.file_object_id
where f.batch_id = $1
order by f.created_at asc, f.id asc
"#;

const IMPORT_FILE_BY_ID_SQL: &str = r#"
select
    f.id,
    f.batch_id,
    f.file_object_id,
    f.file_role,
    f.parse_status,
    f.row_count,
    f.error_count,
    f.template_key,
    f.checksum,
    f.source_file_id,
    f.source_path,
    f.source_metadata,
    f.legacy_id as legacy_file_id,
    o.legacy_gridfs_id,
    o.file_name,
    o.content_type,
    o.byte_size,
    o.sha256,
    o.storage_provider,
    o.bucket,
    o.object_key,
    o.object_version,
    o.etag,
    o.storage_class,
    o.purpose,
    o.metadata as file_object_metadata,
    to_char(f.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
    to_char(f.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from app.import_files f
left join app.file_objects o on o.id = f.file_object_id
where f.id = $1
"#;

const FILE_OBJECT_BY_ID_SQL: &str = r#"
select
    id,
    storage_provider,
    bucket,
    object_key,
    object_version,
    file_name,
    content_type,
    byte_size,
    sha256,
    etag,
    storage_class,
    metadata,
    legacy_gridfs_id,
    purpose,
    created_by,
    to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at
from app.file_objects
where id = $1
"#;

const FILE_OBJECT_BY_SHA256_SQL: &str = r#"
select
    id,
    storage_provider,
    bucket,
    object_key,
    object_version,
    file_name,
    content_type,
    byte_size,
    sha256,
    etag,
    storage_class,
    metadata,
    legacy_gridfs_id,
    purpose,
    created_by,
    to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at
from app.file_objects
where sha256 = $1
order by created_at desc, id desc
limit 1
"#;

fn import_batch_from_row(row: sqlx::postgres::PgRow) -> Result<ImportBatchRow, sqlx::Error> {
    Ok(ImportBatchRow {
        id: row.try_get("id")?,
        batch_type: row.try_get("batch_type")?,
        source_type: row.try_get("source_type")?,
        source_name: row.try_get("source_name")?,
        status: row.try_get("status")?,
        row_count: row.try_get("row_count")?,
        success_count: row.try_get("success_count")?,
        error_count: row.try_get("error_count")?,
        duplicate_count: row.try_get("duplicate_count")?,
        suspected_duplicate_count: row.try_get("suspected_duplicate_count")?,
        updated_count: row.try_get("updated_count")?,
        checksum: row.try_get("checksum")?,
        source_system: row.try_get("source_system")?,
        source_reference: row.try_get("source_reference")?,
        source_metadata: row.try_get("source_metadata")?,
        legacy_session_id: row.try_get("legacy_session_id")?,
        legacy_import_id: row.try_get("legacy_import_id")?,
        created_by: row.try_get("created_by")?,
        updated_by: row.try_get("updated_by")?,
        confirmed_at: row.try_get("confirmed_at")?,
        reverted_at: row.try_get("reverted_at")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn import_file_from_row(row: sqlx::postgres::PgRow) -> Result<ImportFileRow, sqlx::Error> {
    Ok(ImportFileRow {
        id: row.try_get("id")?,
        batch_id: row.try_get("batch_id")?,
        file_object_id: row.try_get("file_object_id")?,
        file_role: row.try_get("file_role")?,
        parse_status: row.try_get("parse_status")?,
        row_count: row.try_get("row_count")?,
        error_count: row.try_get("error_count")?,
        template_key: row.try_get("template_key")?,
        checksum: row.try_get("checksum")?,
        source_file_id: row.try_get("source_file_id")?,
        source_path: row.try_get("source_path")?,
        source_metadata: row.try_get("source_metadata")?,
        legacy_file_id: row.try_get("legacy_file_id")?,
        legacy_gridfs_id: row.try_get("legacy_gridfs_id")?,
        file_name: row.try_get("file_name")?,
        content_type: row.try_get("content_type")?,
        byte_size: row.try_get("byte_size")?,
        sha256: row.try_get("sha256")?,
        storage_provider: row.try_get("storage_provider")?,
        bucket: row.try_get("bucket")?,
        object_key: row.try_get("object_key")?,
        object_version: row.try_get("object_version")?,
        etag: row.try_get("etag")?,
        storage_class: row.try_get("storage_class")?,
        purpose: row.try_get("purpose")?,
        file_object_metadata: row.try_get("file_object_metadata")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn file_object_from_row(row: sqlx::postgres::PgRow) -> Result<FileObjectRow, sqlx::Error> {
    Ok(FileObjectRow {
        id: row.try_get("id")?,
        storage_provider: row.try_get("storage_provider")?,
        bucket: row.try_get("bucket")?,
        object_key: row.try_get("object_key")?,
        object_version: row.try_get("object_version")?,
        file_name: row.try_get("file_name")?,
        content_type: row.try_get("content_type")?,
        byte_size: row.try_get("byte_size")?,
        sha256: row.try_get("sha256")?,
        etag: row.try_get("etag")?,
        storage_class: row.try_get("storage_class")?,
        metadata: row.try_get("metadata")?,
        legacy_gridfs_id: row.try_get("legacy_gridfs_id")?,
        purpose: row.try_get("purpose")?,
        created_by: row.try_get("created_by")?,
        created_at: row.try_get("created_at")?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn import_file_queries_map_legacy_columns_from_current_schema() {
        for sql in [IMPORT_FILES_BY_BATCH_SQL, IMPORT_FILE_BY_ID_SQL] {
            assert!(!sql.contains("f.legacy_file_id"));
            assert!(!sql.contains("f.legacy_gridfs_id"));
            assert!(sql.contains("f.legacy_id as legacy_file_id"));
            assert!(sql.contains("o.legacy_gridfs_id"));
        }
    }
}
