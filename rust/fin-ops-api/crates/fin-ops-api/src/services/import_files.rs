use std::collections::BTreeMap;

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use uuid::Uuid;

use crate::repositories::import_files::{
    FileObjectRow, ImportBatchRow, ImportFileRepository, ImportFileRepositoryError, ImportFileRow,
};

const DEFAULT_LIST_LIMIT: i64 = 50;
const MAX_LIST_LIMIT: i64 = 200;
const MAX_UPLOAD_BYTES: i64 = 25 * 1024 * 1024;
const DEFAULT_BUCKET_LABEL: &str = "configured-by-deployment";
const DEFAULT_STORAGE_PROVIDER_LABEL: &str = "minio_or_s3";

const ALLOWED_EXTENSIONS: &[&str] = &[".xls", ".xlsx"];
const ALLOWED_CONTENT_TYPES: &[&str] = &[
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
];

#[derive(Debug, thiserror::Error)]
pub enum ImportFileServiceError {
    #[error(transparent)]
    Repository(#[from] ImportFileRepositoryError),
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
    #[error("invalid request: {message}")]
    InvalidRequest {
        code: &'static str,
        message: &'static str,
    },
    #[error("file object access unavailable")]
    FileAccess(#[from] FileObjectAccessError),
}

pub struct ImportFileService<R, A> {
    repository: R,
    preflight_policy: UploadPreflightPolicy,
    file_access: A,
}

impl<R, A> ImportFileService<R, A>
where
    R: ImportFileRepository,
    A: FileObjectAccessProvider,
{
    pub fn new(repository: R, preflight_policy: UploadPreflightPolicy, file_access: A) -> Self {
        Self {
            repository,
            preflight_policy,
            file_access,
        }
    }

    pub async fn list_batches(
        &self,
        request: ListImportBatchesRequest,
    ) -> Result<ImportBatchListResponse, ImportFileServiceError> {
        let limit = request
            .limit
            .unwrap_or(DEFAULT_LIST_LIMIT)
            .clamp(1, MAX_LIST_LIMIT);
        let offset = request.offset.unwrap_or(0).max(0);
        let status = clean_optional_filter(request.status);
        let batch_type = clean_optional_filter(request.batch_type);

        validate_import_status(status.as_deref())?;
        validate_batch_type(batch_type.as_deref())?;

        let batches = self
            .repository
            .list_batches(status.as_deref(), batch_type.as_deref(), limit, offset)
            .await?
            .into_iter()
            .map(ImportBatchDto::from_row)
            .collect::<Vec<_>>();

        let returned = batches.len();

        Ok(ImportBatchListResponse {
            batches,
            pagination: PaginationDto {
                limit,
                offset,
                returned,
            },
        })
    }

    pub async fn get_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<ImportBatchDetailResponse, ImportFileServiceError> {
        let batch = self.repository.find_batch(batch_id).await?.ok_or(
            ImportFileServiceError::NotFound {
                resource: "import_batch",
            },
        )?;
        let files = self.repository.list_files_for_batch(batch_id).await?;

        Ok(ImportBatchDetailResponse {
            batch: ImportBatchDto::from_row(batch),
            files: files.into_iter().map(ImportFileDto::from_row).collect(),
        })
    }

    pub async fn download_batch(
        &self,
        batch_id: Uuid,
        request: ImportBatchDownloadRequest,
    ) -> Result<ImportBatchDownloadResponse, ImportFileServiceError> {
        let format = request
            .format
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("json");
        if !matches!(format, "json" | "manifest") {
            return Err(invalid_request(
                "invalid_import_batch_download_request",
                "format must be json or manifest",
            ));
        }

        let batch = self.repository.find_batch(batch_id).await?.ok_or(
            ImportFileServiceError::NotFound {
                resource: "import_batch",
            },
        )?;
        let files = self.repository.list_files_for_batch(batch_id).await?;
        let mut download_files = Vec::with_capacity(files.len());

        for file in files {
            let file_object = match file.file_object_id {
                Some(file_object_id) => self.repository.find_file_object(file_object_id).await?,
                None => None,
            };
            let access = match file_object.as_ref() {
                Some(file_object) => self
                    .access_for_file_object(file_object)
                    .await
                    .map_err(ImportFileServiceError::FileAccess)?,
                None => FileObjectAccessDto::unavailable("file_object_missing"),
            };
            download_files.push(ImportBatchDownloadFileDto {
                file: ImportFileDto::from_row(file),
                file_object: file_object.map(FileObjectDto::from_row),
                access,
            });
        }

        let file_name = format!("{}.json", batch.id);
        Ok(ImportBatchDownloadResponse {
            batch: ImportBatchDto::from_row(batch),
            files: download_files,
            download: ImportBatchDownloadDto {
                format: "json".to_owned(),
                content_type: "application/json; charset=utf-8".to_owned(),
                content_disposition: format!("attachment; filename=\"{file_name}\""),
                delivery: "object_manifest".to_owned(),
            },
        })
    }

    pub async fn get_import_file(
        &self,
        file_id: Uuid,
    ) -> Result<ImportFileMetadataResponse, ImportFileServiceError> {
        let file = self.repository.find_import_file(file_id).await?.ok_or(
            ImportFileServiceError::NotFound {
                resource: "import_file",
            },
        )?;

        Ok(ImportFileMetadataResponse {
            file: ImportFileDto::from_row(file),
        })
    }

    pub async fn get_file_object(
        &self,
        file_object_id: Uuid,
    ) -> Result<FileObjectResponse, ImportFileServiceError> {
        let file_object = self
            .repository
            .find_file_object(file_object_id)
            .await?
            .ok_or(ImportFileServiceError::NotFound {
                resource: "file_object",
            })?;
        let access = self
            .access_for_file_object(&file_object)
            .await
            .map_err(ImportFileServiceError::FileAccess)?;

        Ok(FileObjectResponse {
            file_object: FileObjectDto::from_row(file_object),
            access,
        })
    }

    pub fn templates(&self) -> ImportTemplatesResponse {
        ImportTemplatesResponse {
            templates: import_templates(),
        }
    }

    pub async fn upload_preflight(
        &self,
        request: UploadPreflightRequest,
    ) -> Result<UploadPreflightResponse, ImportFileServiceError> {
        let file_name = request.file_name.trim();
        if file_name.is_empty() {
            return Err(invalid_request(
                "invalid_file_name",
                "file_name is required",
            ));
        }

        let extension = file_extension(file_name).ok_or_else(|| {
            invalid_request(
                "unsupported_file_extension",
                "file_name must end with .xls or .xlsx",
            )
        })?;
        if !ALLOWED_EXTENSIONS.contains(&extension.as_str()) {
            return Err(invalid_request(
                "unsupported_file_extension",
                "file_name must end with .xls or .xlsx",
            ));
        }

        if request.byte_size <= 0 || request.byte_size > MAX_UPLOAD_BYTES {
            return Err(invalid_request(
                "invalid_byte_size",
                "byte_size must be between 1 and the configured API body limit",
            ));
        }

        let sha256 = request.sha256.trim().to_ascii_lowercase();
        if !is_valid_sha256(&sha256) {
            return Err(invalid_request(
                "invalid_sha256",
                "sha256 must be a 64-character lowercase hex digest",
            ));
        }

        let content_type = request
            .content_type
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned)
            .unwrap_or_else(|| infer_content_type(&extension).to_owned());
        if !ALLOWED_CONTENT_TYPES.contains(&content_type.as_str()) {
            return Err(invalid_request(
                "unsupported_content_type",
                "content_type is not allowed for import upload preflight",
            ));
        }

        let purpose = request
            .purpose
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .unwrap_or("import_source")
            .to_owned();
        if purpose != "import_source" {
            return Err(invalid_request(
                "unsupported_purpose",
                "purpose must be import_source for this preflight endpoint",
            ));
        }

        let existing_file_object = self.repository.find_file_object_by_sha256(&sha256).await?;
        let duplicate = existing_file_object.is_some();
        let upload_required = !duplicate;
        let object_key = existing_file_object
            .as_ref()
            .map(|row| row.object_key.clone())
            .unwrap_or_else(|| object_key_for_sha256(&sha256, &extension));

        let mut metadata = BTreeMap::new();
        metadata.insert("contract".to_owned(), json!("p3-09b-upload-preflight"));
        metadata.insert("sha256".to_owned(), json!(sha256));
        metadata.insert("source".to_owned(), json!("axum-preflight"));

        Ok(UploadPreflightResponse {
            accepted: true,
            upload_required,
            duplicate,
            existing_file_object: existing_file_object.map(FileObjectDto::from_row),
            file: UploadPreflightFileDto {
                file_name: file_name.to_owned(),
                content_type,
                byte_size: request.byte_size,
                sha256,
                extension,
                purpose,
            },
            object: UploadPreflightObjectDto {
                storage_provider: self.preflight_policy.storage_provider.clone(),
                bucket: self.preflight_policy.bucket.clone(),
                object_key,
                upload_method: "server_mediated".to_owned(),
                metadata,
            },
            constraints: UploadPreflightConstraintsDto {
                max_byte_size: MAX_UPLOAD_BYTES,
                allowed_extensions: ALLOWED_EXTENSIONS
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect(),
                allowed_content_types: ALLOWED_CONTENT_TYPES
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect(),
            },
        })
    }

    async fn access_for_file_object(
        &self,
        file_object: &FileObjectRow,
    ) -> Result<FileObjectAccessDto, FileObjectAccessError> {
        match self
            .file_access
            .presign_get_object(
                &file_object.bucket,
                &file_object.object_key,
                file_object.object_version.as_deref(),
            )
            .await
        {
            Ok(grant) => Ok(FileObjectAccessDto::from_grant(grant)),
            Err(FileObjectAccessError::NotConfigured) => Ok(FileObjectAccessDto::unavailable(
                "object_storage_not_configured",
            )),
            Err(FileObjectAccessError::BucketNotAllowed) => Ok(FileObjectAccessDto::unavailable(
                "object_bucket_not_allowed",
            )),
            Err(error) => Err(error),
        }
    }
}

#[derive(Clone)]
pub struct UploadPreflightPolicy {
    pub storage_provider: String,
    pub bucket: String,
}

#[async_trait]
pub trait FileObjectAccessProvider: Clone + Send + Sync + 'static {
    async fn presign_get_object(
        &self,
        bucket: &str,
        object_key: &str,
        object_version: Option<&str>,
    ) -> Result<FileObjectAccessGrant, FileObjectAccessError>;
}

#[derive(Debug, Clone)]
pub struct FileObjectAccessGrant {
    pub method: String,
    pub url: String,
    pub ttl_seconds: u64,
    pub expires_at_unix_seconds: Option<u64>,
}

#[derive(Debug, thiserror::Error)]
pub enum FileObjectAccessError {
    #[error("object storage is not configured")]
    NotConfigured,
    #[error("file object bucket is not allowed by the configured object storage client")]
    BucketNotAllowed,
    #[error("presigned url generation failed")]
    PresignFailed(String),
}

impl UploadPreflightPolicy {
    pub fn from_config(bucket: Option<&str>, storage_configured: bool) -> Self {
        Self {
            storage_provider: if storage_configured {
                "minio".to_owned()
            } else {
                DEFAULT_STORAGE_PROVIDER_LABEL.to_owned()
            },
            bucket: bucket
                .filter(|value| !value.trim().is_empty())
                .map(ToOwned::to_owned)
                .unwrap_or_else(|| DEFAULT_BUCKET_LABEL.to_owned()),
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ListImportBatchesRequest {
    pub status: Option<String>,
    pub batch_type: Option<String>,
    pub limit: Option<i64>,
    pub offset: Option<i64>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ImportBatchDownloadRequest {
    pub format: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchListResponse {
    pub batches: Vec<ImportBatchDto>,
    pub pagination: PaginationDto,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchDetailResponse {
    pub batch: ImportBatchDto,
    pub files: Vec<ImportFileDto>,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchDownloadResponse {
    pub batch: ImportBatchDto,
    pub files: Vec<ImportBatchDownloadFileDto>,
    pub download: ImportBatchDownloadDto,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchDownloadFileDto {
    pub file: ImportFileDto,
    pub file_object: Option<FileObjectDto>,
    pub access: FileObjectAccessDto,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchDownloadDto {
    pub format: String,
    pub content_type: String,
    pub content_disposition: String,
    pub delivery: String,
}

#[derive(Debug, Serialize)]
pub struct ImportFileMetadataResponse {
    pub file: ImportFileDto,
}

#[derive(Debug, Serialize)]
pub struct FileObjectResponse {
    pub file_object: FileObjectDto,
    pub access: FileObjectAccessDto,
}

#[derive(Debug, Serialize)]
pub struct FileObjectAccessDto {
    pub method: String,
    pub url: Option<String>,
    pub ttl_seconds: Option<u64>,
    pub expires_at_unix_seconds: Option<u64>,
    pub unavailable_reason: Option<&'static str>,
}

impl FileObjectAccessDto {
    fn from_grant(grant: FileObjectAccessGrant) -> Self {
        Self {
            method: grant.method,
            url: Some(grant.url),
            ttl_seconds: Some(grant.ttl_seconds),
            expires_at_unix_seconds: grant.expires_at_unix_seconds,
            unavailable_reason: None,
        }
    }

    fn unavailable(reason: &'static str) -> Self {
        Self {
            method: "unavailable".to_owned(),
            url: None,
            ttl_seconds: None,
            expires_at_unix_seconds: None,
            unavailable_reason: Some(reason),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct PaginationDto {
    pub limit: i64,
    pub offset: i64,
    pub returned: usize,
}

#[derive(Debug, Serialize)]
pub struct ImportBatchDto {
    pub id: String,
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

impl ImportBatchDto {
    fn from_row(row: ImportBatchRow) -> Self {
        Self {
            id: row.id.to_string(),
            batch_type: row.batch_type,
            source_type: row.source_type,
            source_name: row.source_name,
            status: row.status,
            row_count: row.row_count,
            success_count: row.success_count,
            error_count: row.error_count,
            duplicate_count: row.duplicate_count,
            suspected_duplicate_count: row.suspected_duplicate_count,
            updated_count: row.updated_count,
            checksum: row.checksum,
            source_system: row.source_system,
            source_reference: row.source_reference,
            source_metadata: row.source_metadata,
            legacy_session_id: row.legacy_session_id,
            legacy_import_id: row.legacy_import_id,
            created_by: row.created_by,
            updated_by: row.updated_by,
            confirmed_at: row.confirmed_at,
            reverted_at: row.reverted_at,
            created_at: row.created_at,
            updated_at: row.updated_at,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ImportFileDto {
    pub id: String,
    pub batch_id: String,
    pub file_object_id: Option<String>,
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
    pub file_object: Option<ImportFileObjectSummaryDto>,
    pub created_at: String,
    pub updated_at: String,
}

impl ImportFileDto {
    fn from_row(row: ImportFileRow) -> Self {
        let file_object = row
            .file_object_id
            .map(|file_object_id| ImportFileObjectSummaryDto {
                id: file_object_id.to_string(),
                file_name: row.file_name,
                content_type: row.content_type,
                byte_size: row.byte_size,
                sha256: row.sha256,
                storage_provider: row.storage_provider,
                bucket: row.bucket,
                object_key: row.object_key,
                object_version: row.object_version,
                etag: row.etag,
                storage_class: row.storage_class,
                purpose: row.purpose,
                metadata: row.file_object_metadata,
            });

        Self {
            id: row.id.to_string(),
            batch_id: row.batch_id.to_string(),
            file_object_id: row.file_object_id.map(|value| value.to_string()),
            file_role: row.file_role,
            parse_status: row.parse_status,
            row_count: row.row_count,
            error_count: row.error_count,
            template_key: row.template_key,
            checksum: row.checksum,
            source_file_id: row.source_file_id,
            source_path: row.source_path,
            source_metadata: row.source_metadata,
            legacy_file_id: row.legacy_file_id,
            legacy_gridfs_id: row.legacy_gridfs_id,
            file_object,
            created_at: row.created_at,
            updated_at: row.updated_at,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ImportFileObjectSummaryDto {
    pub id: String,
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
    pub metadata: Option<Value>,
}

#[derive(Debug, Serialize)]
pub struct FileObjectDto {
    pub id: String,
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

impl FileObjectDto {
    fn from_row(row: FileObjectRow) -> Self {
        Self {
            id: row.id.to_string(),
            storage_provider: row.storage_provider,
            bucket: row.bucket,
            object_key: row.object_key,
            object_version: row.object_version,
            file_name: row.file_name,
            content_type: row.content_type,
            byte_size: row.byte_size,
            sha256: row.sha256,
            etag: row.etag,
            storage_class: row.storage_class,
            metadata: redact_secret_metadata(row.metadata),
            legacy_gridfs_id: row.legacy_gridfs_id,
            purpose: row.purpose,
            created_by: row.created_by,
            created_at: row.created_at,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ImportTemplatesResponse {
    pub templates: Vec<ImportTemplateDto>,
}

#[derive(Debug, Serialize)]
pub struct ImportTemplateDto {
    pub template_code: &'static str,
    pub label: &'static str,
    pub file_extensions: Vec<&'static str>,
    pub record_type: &'static str,
    pub allowed_batch_types: Vec<&'static str>,
    pub required_headers: Vec<&'static str>,
}

#[derive(Debug, Deserialize)]
pub struct UploadPreflightRequest {
    pub file_name: String,
    pub byte_size: i64,
    pub content_type: Option<String>,
    pub sha256: String,
    pub purpose: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct UploadPreflightResponse {
    pub accepted: bool,
    pub upload_required: bool,
    pub duplicate: bool,
    pub existing_file_object: Option<FileObjectDto>,
    pub file: UploadPreflightFileDto,
    pub object: UploadPreflightObjectDto,
    pub constraints: UploadPreflightConstraintsDto,
}

#[derive(Debug, Serialize)]
pub struct UploadPreflightFileDto {
    pub file_name: String,
    pub content_type: String,
    pub byte_size: i64,
    pub sha256: String,
    pub extension: String,
    pub purpose: String,
}

#[derive(Debug, Serialize)]
pub struct UploadPreflightObjectDto {
    pub storage_provider: String,
    pub bucket: String,
    pub object_key: String,
    pub upload_method: String,
    pub metadata: BTreeMap<String, Value>,
}

#[derive(Debug, Serialize)]
pub struct UploadPreflightConstraintsDto {
    pub max_byte_size: i64,
    pub allowed_extensions: Vec<String>,
    pub allowed_content_types: Vec<String>,
}

fn import_templates() -> Vec<ImportTemplateDto> {
    vec![
        ImportTemplateDto {
            template_code: "invoice_export",
            label: "发票导出",
            file_extensions: vec![".xlsx"],
            record_type: "invoice",
            allowed_batch_types: vec!["input_invoice", "output_invoice"],
            required_headers: vec![
                "发票代码",
                "发票号码",
                "销方识别号",
                "购买方名称",
                "开票日期",
                "金额",
                "税额",
            ],
        },
        ImportTemplateDto {
            template_code: "icbc_historydetail",
            label: "工商银行流水",
            file_extensions: vec![".xlsx"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec![
                "[HISTORYDETAIL]",
                "凭证号",
                "交易时间",
                "对方单位",
                "对方账号",
                "转入金额",
                "转出金额",
            ],
        },
        ImportTemplateDto {
            template_code: "ceb_transaction_detail",
            label: "光大银行流水",
            file_extensions: vec![".xls"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec![
                "交易日期",
                "交易时间",
                "借方发生额",
                "贷方发生额",
                "对方名称",
            ],
        },
        ImportTemplateDto {
            template_code: "ccb_transaction_detail",
            label: "建设银行流水",
            file_extensions: vec![".xls"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec!["交易日期", "摘要", "借方发生额", "贷方发生额", "对方户名"],
        },
        ImportTemplateDto {
            template_code: "cmbc_transaction_detail",
            label: "民生银行流水",
            file_extensions: vec![".xlsx"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec![
                "交易日期",
                "对方户名",
                "借方发生额",
                "贷方发生额",
                "交易摘要",
            ],
        },
        ImportTemplateDto {
            template_code: "pingan_transaction_detail",
            label: "平安银行流水",
            file_extensions: vec![".xlsx"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec!["交易日期", "对方户名", "收入金额", "支出金额", "摘要"],
        },
        ImportTemplateDto {
            template_code: "bocom_transaction_detail",
            label: "交通银行流水",
            file_extensions: vec![".xls", ".xlsx"],
            record_type: "bank_transaction",
            allowed_batch_types: vec!["bank_transaction"],
            required_headers: vec!["交易日期", "交易时间", "收入", "支出", "对方户名"],
        },
    ]
}

fn clean_optional_filter(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
}

fn validate_import_status(status: Option<&str>) -> Result<(), ImportFileServiceError> {
    if let Some(status) = status {
        let allowed = [
            "pending",
            "completed",
            "completed_with_errors",
            "reverted",
            "failed",
        ];
        if !allowed.contains(&status) {
            return Err(invalid_request(
                "invalid_status",
                "status is not a valid import batch status",
            ));
        }
    }
    Ok(())
}

fn validate_batch_type(batch_type: Option<&str>) -> Result<(), ImportFileServiceError> {
    if let Some(batch_type) = batch_type {
        let allowed = [
            "output_invoice",
            "input_invoice",
            "bank_transaction",
            "tax_certified",
            "etc",
            "oa_sync",
            "mongo_migration",
        ];
        if !allowed.contains(&batch_type) {
            return Err(invalid_request(
                "invalid_batch_type",
                "batch_type is not a valid import batch type",
            ));
        }
    }
    Ok(())
}

fn file_extension(file_name: &str) -> Option<String> {
    let (_, extension) = file_name.rsplit_once('.')?;
    Some(format!(".{}", extension.to_ascii_lowercase()))
}

fn infer_content_type(extension: &str) -> &'static str {
    match extension {
        ".xls" => "application/vnd.ms-excel",
        ".xlsx" => "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        _ => "application/octet-stream",
    }
}

fn is_valid_sha256(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn object_key_for_sha256(sha256: &str, extension: &str) -> String {
    format!(
        "imports/uploads/sha256/{}/{}{}",
        &sha256[0..2],
        sha256,
        extension
    )
}

fn invalid_request(code: &'static str, message: &'static str) -> ImportFileServiceError {
    ImportFileServiceError::InvalidRequest { code, message }
}

fn redact_secret_metadata(value: Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(
            map.into_iter()
                .map(|(key, value)| {
                    let lowered = key.to_ascii_lowercase();
                    let redacted = lowered.contains("secret")
                        || lowered.contains("access_key")
                        || lowered.contains("token")
                        || lowered.contains("password");
                    (
                        key,
                        if redacted {
                            Value::String("[redacted]".to_owned())
                        } else {
                            redact_secret_metadata(value)
                        },
                    )
                })
                .collect(),
        ),
        Value::Array(values) => {
            Value::Array(values.into_iter().map(redact_secret_metadata).collect())
        }
        other => other,
    }
}

#[cfg(test)]
mod tests {
    use async_trait::async_trait;

    use super::*;

    #[derive(Clone)]
    struct StaticRepository {
        duplicate: Option<FileObjectRow>,
        file_object: Option<FileObjectRow>,
        batch: Option<ImportBatchRow>,
        files: Vec<ImportFileRow>,
    }

    #[async_trait]
    impl ImportFileRepository for StaticRepository {
        async fn list_batches(
            &self,
            _status: Option<&str>,
            _batch_type: Option<&str>,
            _limit: i64,
            _offset: i64,
        ) -> Result<Vec<ImportBatchRow>, ImportFileRepositoryError> {
            Ok(Vec::new())
        }

        async fn find_batch(
            &self,
            _batch_id: Uuid,
        ) -> Result<Option<ImportBatchRow>, ImportFileRepositoryError> {
            Ok(self.batch.clone())
        }

        async fn list_files_for_batch(
            &self,
            _batch_id: Uuid,
        ) -> Result<Vec<ImportFileRow>, ImportFileRepositoryError> {
            Ok(self.files.clone())
        }

        async fn find_import_file(
            &self,
            _file_id: Uuid,
        ) -> Result<Option<ImportFileRow>, ImportFileRepositoryError> {
            Ok(None)
        }

        async fn find_file_object(
            &self,
            _file_object_id: Uuid,
        ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError> {
            Ok(self.file_object.clone())
        }

        async fn find_file_object_by_sha256(
            &self,
            _sha256: &str,
        ) -> Result<Option<FileObjectRow>, ImportFileRepositoryError> {
            Ok(self.duplicate.clone())
        }
    }

    #[tokio::test]
    async fn upload_preflight_rejects_unsupported_extension_before_storage_lookup() {
        let service = test_service(None);

        let error = service
            .upload_preflight(UploadPreflightRequest {
                file_name: "source.csv".to_owned(),
                byte_size: 1024,
                content_type: None,
                sha256: "a".repeat(64),
                purpose: None,
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            ImportFileServiceError::InvalidRequest {
                code: "unsupported_file_extension",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn upload_preflight_rejects_invalid_checksum() {
        let service = test_service(None);

        let error = service
            .upload_preflight(UploadPreflightRequest {
                file_name: "source.xlsx".to_owned(),
                byte_size: 1024,
                content_type: None,
                sha256: "not-a-checksum".to_owned(),
                purpose: None,
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            ImportFileServiceError::InvalidRequest {
                code: "invalid_sha256",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn upload_preflight_detects_existing_file_object_by_checksum() {
        let sha256 = "b".repeat(64);
        let existing = FileObjectRow {
            id: Uuid::parse_str("0196f550-cc6e-7000-8000-000000000001").unwrap(),
            storage_provider: "minio".to_owned(),
            bucket: "fin-ops-local".to_owned(),
            object_key: "imports/uploads/sha256/bb/existing.xlsx".to_owned(),
            object_version: None,
            file_name: "existing.xlsx".to_owned(),
            content_type: Some(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".to_owned(),
            ),
            byte_size: 2048,
            sha256: sha256.clone(),
            etag: None,
            storage_class: None,
            metadata: json!({}),
            legacy_gridfs_id: None,
            purpose: "import_source".to_owned(),
            created_by: Some("tester".to_owned()),
            created_at: "2026-05-16T00:00:00Z".to_owned(),
        };
        let service = test_service(Some(existing));

        let response = service
            .upload_preflight(UploadPreflightRequest {
                file_name: "source.xlsx".to_owned(),
                byte_size: 2048,
                content_type: None,
                sha256,
                purpose: None,
            })
            .await
            .unwrap();

        assert!(response.duplicate);
        assert!(!response.upload_required);
        assert_eq!(
            response.existing_file_object.unwrap().file_name,
            "existing.xlsx"
        );
    }

    #[tokio::test]
    async fn get_file_object_returns_short_lived_presigned_access_without_bare_secret_fields() {
        let file_object_id = Uuid::parse_str("0196f550-cc6e-7000-8000-000000000002").unwrap();
        let service = test_service_with_file_object(sample_file_object(file_object_id));

        let response = service.get_file_object(file_object_id).await.unwrap();
        let body = serde_json::to_value(&response).unwrap();

        assert_eq!(body["access"]["method"], "presigned_get");
        assert_eq!(body["access"]["ttl_seconds"], 300);
        assert!(body["access"]["url"]
            .as_str()
            .unwrap()
            .contains("X-Amz-Signature"));
        let serialized = serde_json::to_string(&body).unwrap();
        assert!(!serialized.contains("AKIA_TEST"));
        assert!(!serialized.contains("secret-access-key"));
    }

    #[tokio::test]
    async fn batch_download_returns_object_manifest_and_presigned_access() {
        let batch_id = Uuid::parse_str("0196f550-cc6e-7000-8000-000000000010").unwrap();
        let file_object_id = Uuid::parse_str("0196f550-cc6e-7000-8000-000000000011").unwrap();
        let service = test_service_with_batch(
            sample_import_batch(batch_id),
            vec![sample_import_file(batch_id, file_object_id)],
            sample_file_object(file_object_id),
        );

        let response = service
            .download_batch(batch_id, ImportBatchDownloadRequest { format: None })
            .await
            .unwrap();
        let body = serde_json::to_value(&response).unwrap();

        assert_eq!(body["download"]["delivery"], "object_manifest");
        assert_eq!(
            body["download"]["content_disposition"],
            format!("attachment; filename=\"{batch_id}.json\"")
        );
        assert_eq!(
            body["files"][0]["file"]["legacy_gridfs_id"],
            "import_file_0001"
        );
        assert_eq!(
            body["files"][0]["file_object"]["legacy_gridfs_id"],
            "import_file_0001"
        );
        assert_eq!(body["files"][0]["access"]["method"], "presigned_get");
    }

    #[tokio::test]
    async fn batch_download_rejects_unknown_format_without_presigning() {
        let batch_id = Uuid::parse_str("0196f550-cc6e-7000-8000-000000000010").unwrap();
        let service = test_service_with_batch(
            sample_import_batch(batch_id),
            Vec::new(),
            sample_file_object(Uuid::parse_str("0196f550-cc6e-7000-8000-000000000011").unwrap()),
        );

        let error = service
            .download_batch(
                batch_id,
                ImportBatchDownloadRequest {
                    format: Some("zip".to_owned()),
                },
            )
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            ImportFileServiceError::InvalidRequest {
                code: "invalid_import_batch_download_request",
                ..
            }
        ));
    }

    #[test]
    fn templates_preserve_frontend_import_contract() {
        let service = test_service(None);
        let templates = service.templates().templates;

        assert_eq!(templates.len(), 7);
        assert!(templates.iter().any(|template| {
            template.template_code == "invoice_export"
                && template.allowed_batch_types.contains(&"input_invoice")
                && template.required_headers.contains(&"发票号码")
        }));
    }

    fn test_service(
        duplicate: Option<FileObjectRow>,
    ) -> ImportFileService<StaticRepository, StaticAccessProvider> {
        ImportFileService::new(
            StaticRepository {
                duplicate,
                file_object: None,
                batch: None,
                files: Vec::new(),
            },
            UploadPreflightPolicy {
                storage_provider: "minio".to_owned(),
                bucket: "fin-ops-local".to_owned(),
            },
            StaticAccessProvider,
        )
    }

    fn test_service_with_file_object(
        file_object: FileObjectRow,
    ) -> ImportFileService<StaticRepository, StaticAccessProvider> {
        ImportFileService::new(
            StaticRepository {
                duplicate: None,
                file_object: Some(file_object),
                batch: None,
                files: Vec::new(),
            },
            UploadPreflightPolicy {
                storage_provider: "minio".to_owned(),
                bucket: "fin-ops-local".to_owned(),
            },
            StaticAccessProvider,
        )
    }

    fn test_service_with_batch(
        batch: ImportBatchRow,
        files: Vec<ImportFileRow>,
        file_object: FileObjectRow,
    ) -> ImportFileService<StaticRepository, StaticAccessProvider> {
        ImportFileService::new(
            StaticRepository {
                duplicate: None,
                file_object: Some(file_object),
                batch: Some(batch),
                files,
            },
            UploadPreflightPolicy {
                storage_provider: "minio".to_owned(),
                bucket: "fin-ops-local".to_owned(),
            },
            StaticAccessProvider,
        )
    }

    #[derive(Clone)]
    struct StaticAccessProvider;

    #[async_trait]
    impl FileObjectAccessProvider for StaticAccessProvider {
        async fn presign_get_object(
            &self,
            _bucket: &str,
            _object_key: &str,
            _object_version: Option<&str>,
        ) -> Result<FileObjectAccessGrant, FileObjectAccessError> {
            Ok(FileObjectAccessGrant {
                method: "presigned_get".to_owned(),
                url: "https://objects.example.test/file.xlsx?X-Amz-Signature=redacted".to_owned(),
                ttl_seconds: 300,
                expires_at_unix_seconds: Some(1_777_777_777),
            })
        }
    }

    fn sample_file_object(id: Uuid) -> FileObjectRow {
        FileObjectRow {
            id,
            storage_provider: "minio".to_owned(),
            bucket: "fin-ops-local".to_owned(),
            object_key: "staging/app-gridfs/import_source_file/2026/05/hash/file".to_owned(),
            object_version: None,
            file_name: "source.xlsx".to_owned(),
            content_type: Some(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".to_owned(),
            ),
            byte_size: 2048,
            sha256: "c".repeat(64),
            etag: Some("etag".to_owned()),
            storage_class: None,
            metadata: json!({"aws_access_key_id": "AKIA_TEST", "secret": "secret-access-key"}),
            legacy_gridfs_id: Some("import_file_0001".to_owned()),
            purpose: "import_source_file".to_owned(),
            created_by: Some("mongo_migration".to_owned()),
            created_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }

    fn sample_import_batch(id: Uuid) -> ImportBatchRow {
        ImportBatchRow {
            id,
            batch_type: "bank_transaction".to_owned(),
            source_type: "file".to_owned(),
            source_name: Some("source.xlsx".to_owned()),
            status: "completed".to_owned(),
            row_count: 1,
            success_count: 1,
            error_count: 0,
            duplicate_count: 0,
            suspected_duplicate_count: 0,
            updated_count: 0,
            checksum: Some("c".repeat(64)),
            source_system: Some("app_mongo".to_owned()),
            source_reference: Some("import_file_0001".to_owned()),
            source_metadata: json!({"legacy_gridfs_id": "import_file_0001"}),
            legacy_session_id: Some("session-1".to_owned()),
            legacy_import_id: None,
            created_by: Some("mongo_migration".to_owned()),
            updated_by: Some("mongo_migration".to_owned()),
            confirmed_at: Some("2026-05-16T00:00:00Z".to_owned()),
            reverted_at: None,
            created_at: "2026-05-16T00:00:00Z".to_owned(),
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }

    fn sample_import_file(batch_id: Uuid, file_object_id: Uuid) -> ImportFileRow {
        ImportFileRow {
            id: Uuid::parse_str("0196f550-cc6e-7000-8000-000000000012").unwrap(),
            batch_id,
            file_object_id: Some(file_object_id),
            file_role: "source".to_owned(),
            parse_status: "parsed".to_owned(),
            row_count: 1,
            error_count: 0,
            template_key: Some("icbc_historydetail".to_owned()),
            checksum: Some("c".repeat(64)),
            source_file_id: Some("import_file_0001".to_owned()),
            source_path: None,
            source_metadata: json!({"legacy_gridfs_id": "import_file_0001"}),
            legacy_file_id: Some("import_file_0001".to_owned()),
            legacy_gridfs_id: Some("import_file_0001".to_owned()),
            file_name: Some("source.xlsx".to_owned()),
            content_type: Some(
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet".to_owned(),
            ),
            byte_size: Some(2048),
            sha256: Some("c".repeat(64)),
            storage_provider: Some("minio".to_owned()),
            bucket: Some("fin-ops-local".to_owned()),
            object_key: Some("staging/app-gridfs/import_source_file/2026/05/hash/file".to_owned()),
            object_version: None,
            etag: Some("etag".to_owned()),
            storage_class: None,
            purpose: Some("import_source_file".to_owned()),
            file_object_metadata: Some(json!({"legacy_gridfs_id": "import_file_0001"})),
            created_at: "2026-05-16T00:00:00Z".to_owned(),
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }
}
