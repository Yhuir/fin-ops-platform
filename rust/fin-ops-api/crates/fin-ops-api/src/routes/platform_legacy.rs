use axum::{
    extract::{Extension, Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::{
    middleware::{auth::AuthenticatedSession, trace_id::TraceId},
    repositories::platform_legacy::SqlxPlatformLegacyRepository,
    services::{
        platform_legacy::{
            MatchingResultsRequest, PlatformLegacyRepositoryError, PlatformLegacyService,
            PlatformLegacyServiceError, RetryBackgroundJobRequest, RetryImportFileRequest,
        },
        workbench_writes::WriteActor,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/api/background-jobs/{job_id}/retry",
            post(retry_background_job),
        )
        .route("/imports/files/retry", post(retry_import_file))
        .route(
            "/imports/files/sessions/{session_id}",
            get(get_import_session),
        )
        .route("/matching/run", post(request_matching_run))
        .route("/matching/results", get(list_matching_results))
        .route("/matching/results/{result_id}", get(get_matching_result))
}

async fn retry_background_job(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Path(job_id): Path<String>,
    Json(request): Json<RetryBackgroundJobRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let job_id = parse_uuid("job_id", &job_id)?;
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .retry_background_job(job_id, request, trusted_actor(&session, trace_id))
                .await?,
        ),
    ))
}

async fn retry_import_file(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<RetryImportFileApiRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let file_id = parse_uuid("file_id", &request.file_id)?;
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .retry_import_file(
                    file_id,
                    RetryImportFileRequest {
                        idempotency_key: request.idempotency_key,
                        reason: request.reason,
                    },
                    trusted_actor(&session, trace_id),
                )
                .await?,
        ),
    ))
}

async fn get_import_session(
    State(state): State<AppState>,
    Path(session_id): Path<String>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.get_import_session(&session_id).await?))
}

async fn request_matching_run(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<crate::services::platform_legacy::MatchingRunRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .request_matching_run(request, trusted_actor(&session, trace_id))
                .await?,
        ),
    ))
}

async fn list_matching_results(
    State(state): State<AppState>,
    Query(request): Query<MatchingResultsRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.list_matching_results(request).await?))
}

async fn get_matching_result(
    State(state): State<AppState>,
    Path(result_id): Path<String>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let result_id = parse_uuid("result_id", &result_id)?;
    let service = build_service(&state);
    Ok(Json(service.get_matching_result(result_id).await?))
}

fn build_service(state: &AppState) -> PlatformLegacyService<SqlxPlatformLegacyRepository> {
    PlatformLegacyService::new(SqlxPlatformLegacyRepository::new(state.db.clone()))
}

fn trusted_actor(
    session: &AuthenticatedSession,
    trace_id: Option<Extension<TraceId>>,
) -> WriteActor {
    WriteActor::oa_user(
        session.actor_id(),
        trace_id
            .map(|Extension(trace_id)| trace_id.0)
            .or_else(|| session.request_id.clone()),
    )
}

fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, PlatformLegacyApiError> {
    Uuid::parse_str(value).map_err(|_| PlatformLegacyApiError::BadRequest {
        code: "invalid_uuid",
        message: format!("{field} must be a valid UUID"),
    })
}

#[derive(Debug)]
enum PlatformLegacyApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    Conflict { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Debug, Deserialize)]
struct RetryImportFileApiRequest {
    file_id: String,
    idempotency_key: String,
    reason: String,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<PlatformLegacyServiceError> for PlatformLegacyApiError {
    fn from(error: PlatformLegacyServiceError) -> Self {
        match error {
            PlatformLegacyServiceError::InvalidRequest { code, message } => {
                Self::BadRequest { code, message }
            }
            PlatformLegacyServiceError::NotFound { resource } => Self::NotFound {
                code: "not_found",
                message: format!("{resource} was not found"),
            },
            PlatformLegacyServiceError::Repository(
                PlatformLegacyRepositoryError::IdempotencyConflict,
            ) => Self::Conflict {
                code: "idempotency_conflict",
                message: "idempotency key was reused with a different payload".to_owned(),
            },
            PlatformLegacyServiceError::Repository(PlatformLegacyRepositoryError::NotFound {
                resource,
            }) => Self::NotFound {
                code: "not_found",
                message: format!("{resource} was not found"),
            },
            PlatformLegacyServiceError::Repository(PlatformLegacyRepositoryError::Database(_)) => {
                Self::DatabaseUnavailable
            }
        }
    }
}

impl IntoResponse for PlatformLegacyApiError {
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
            Self::Conflict { code, message } => (
                StatusCode::CONFLICT,
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
