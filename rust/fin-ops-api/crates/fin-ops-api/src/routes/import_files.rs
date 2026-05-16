use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::Serialize;
use uuid::Uuid;

use crate::{
    repositories::import_files::SqlxImportFileRepository,
    services::import_files::{
        ImportFileService, ImportFileServiceError, ListImportBatchesRequest, UploadPreflightPolicy,
        UploadPreflightRequest,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/imports/templates", get(import_templates))
        .route("/imports/batches", get(list_import_batches))
        .route("/imports/batches/{batch_id}", get(get_import_batch))
        .route("/imports/files/upload-preflight", post(upload_preflight))
        .route("/imports/files/{file_id}", get(get_import_file))
        .route("/api/files/objects/{file_object_id}", get(get_file_object))
}

async fn import_templates(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(service.templates()))
}

async fn list_import_batches(
    State(state): State<AppState>,
    Query(query): Query<ListImportBatchesRequest>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(service.list_batches(query).await?))
}

async fn get_import_batch(
    State(state): State<AppState>,
    Path(batch_id): Path<String>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(
        service
            .get_batch(parse_uuid("batch_id", &batch_id)?)
            .await?,
    ))
}

async fn get_import_file(
    State(state): State<AppState>,
    Path(file_id): Path<String>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(
        service
            .get_import_file(parse_uuid("file_id", &file_id)?)
            .await?,
    ))
}

async fn get_file_object(
    State(state): State<AppState>,
    Path(file_object_id): Path<String>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(
        service
            .get_file_object(parse_uuid("file_object_id", &file_object_id)?)
            .await?,
    ))
}

async fn upload_preflight(
    State(state): State<AppState>,
    Json(request): Json<UploadPreflightRequest>,
) -> Result<impl IntoResponse, ImportFilesApiError> {
    let service = build_service(&state);
    Ok(Json(service.upload_preflight(request).await?))
}

fn build_service(
    state: &AppState,
) -> ImportFileService<SqlxImportFileRepository, crate::infra::s3::S3Client> {
    ImportFileService::new(
        SqlxImportFileRepository::new(state.db.clone()),
        UploadPreflightPolicy::from_config(
            state.config.s3.bucket.as_deref(),
            state.dependencies.s3.configured(),
        ),
        state.dependencies.s3.clone(),
    )
}

fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, ImportFilesApiError> {
    Uuid::parse_str(value).map_err(|_| ImportFilesApiError::BadRequest {
        code: "invalid_uuid",
        message: format!("{field} must be a valid UUID"),
    })
}

#[derive(Debug)]
enum ImportFilesApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<ImportFileServiceError> for ImportFilesApiError {
    fn from(error: ImportFileServiceError) -> Self {
        match error {
            ImportFileServiceError::InvalidRequest { code, message } => Self::BadRequest {
                code,
                message: message.to_owned(),
            },
            ImportFileServiceError::NotFound { resource } => Self::NotFound {
                code: "not_found",
                message: format!("{resource} was not found"),
            },
            ImportFileServiceError::Repository(_) => Self::DatabaseUnavailable,
            ImportFileServiceError::FileAccess(_) => Self::DatabaseUnavailable,
        }
    }
}

impl IntoResponse for ImportFilesApiError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            Self::BadRequest { code, message } => (
                StatusCode::BAD_REQUEST,
                ErrorDetails {
                    error: code.to_owned(),
                    message,
                },
            ),
            Self::NotFound { code, message } => (
                StatusCode::NOT_FOUND,
                ErrorDetails {
                    error: code.to_owned(),
                    message,
                },
            ),
            Self::DatabaseUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                ErrorDetails {
                    error: "database_unavailable".to_owned(),
                    message: "database dependency is unavailable".to_owned(),
                },
            ),
        };

        (status, Json(body)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::Request,
    };
    use serde_json::Value;
    use tower::ServiceExt;

    use super::*;
    use crate::services::health::{DependencyCheck, ReadinessProbe};

    struct StaticReadinessProbe;

    #[async_trait]
    impl ReadinessProbe for StaticReadinessProbe {
        async fn check_postgres(&self) -> DependencyCheck {
            DependencyCheck::ready("postgres", true)
        }
    }

    #[tokio::test]
    async fn import_templates_match_legacy_python_contract() {
        let response = authorized_request("/imports/templates").await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        let templates = body["templates"].as_array().unwrap();
        assert_eq!(templates.len(), 7);
        assert!(templates
            .iter()
            .any(|template| template["template_code"] == "invoice_export"));
        assert!(templates
            .iter()
            .any(|template| template["template_code"] == "icbc_historydetail"));
    }

    #[tokio::test]
    async fn invalid_import_batch_id_uses_public_error_shape() {
        let response = authorized_request("/imports/batches/not-a-uuid").await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_uuid");
        assert!(body["message"].as_str().unwrap().contains("batch_id"));
    }

    async fn authorized_request(uri: &str) -> axum::response::Response {
        let state = AppState::for_tests_with_env(Arc::new(StaticReadinessProbe), |key| match key {
            "DATABASE_URL" => {
                Some("postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops_test".to_owned())
            }
            "FIN_OPS_OA_IDENTITY_ADAPTER" => Some("trusted_headers".to_owned()),
            _ => None,
        });
        crate::build_router(state)
            .oneshot(
                Request::builder()
                    .uri(uri)
                    .header("authorization", "Bearer opaque-oa-token")
                    .header("x-fin-ops-oa-user-id", "YNSYLP005-id")
                    .header("x-fin-ops-oa-username", "YNSYLP005")
                    .header("x-fin-ops-oa-permissions", "finops:app:view")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn to_json(body: Body) -> Value {
        let bytes = to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }
}
