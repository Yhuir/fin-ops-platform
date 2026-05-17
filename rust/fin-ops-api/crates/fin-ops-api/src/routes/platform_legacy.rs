use axum::{
    extract::{Extension, Path, Query, State},
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::{delete, get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

use crate::{
    middleware::{auth::AuthenticatedSession, trace_id::TraceId},
    repositories::platform_legacy::SqlxPlatformLegacyRepository,
    services::{
        platform_legacy::{
            AcknowledgeBackgroundJobRequest, DataResetJobRequest, LedgerListRequest,
            LedgerStatusRequest, MatchingResultsRequest, PlatformLegacyRepositoryError,
            PlatformLegacyService, PlatformLegacyServiceError, ProjectAssignRequest,
            ProjectDeleteRequest, ProjectProfileWriteRequest, ProjectSyncRequest,
            ReminderListRequest, ReminderRunRequest, RetryBackgroundJobRequest,
            RetryImportFileRequest, WorkbenchSettingsWriteRequest,
        },
        workbench_writes::WriteActor,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route(
            "/api/background-jobs/{job_id}/acknowledge",
            post(acknowledge_background_job),
        )
        .route(
            "/api/background-jobs/{job_id}/retry",
            post(retry_background_job),
        )
        .route("/api/workbench/settings", post(save_workbench_settings))
        .route(
            "/api/workbench/settings/projects/sync",
            post(request_project_sync),
        )
        .route(
            "/api/workbench/settings/projects",
            post(create_settings_project),
        )
        .route(
            "/api/workbench/settings/projects/{project_id}",
            delete(delete_settings_project),
        )
        .route(
            "/api/workbench/settings/data-reset/jobs",
            post(create_data_reset_job),
        )
        .route(
            "/api/workbench/settings/data-reset",
            post(request_data_reset_execution),
        )
        .route("/projects", get(list_projects).post(create_project))
        .route("/projects/assign", post(assign_project))
        .route("/projects/{project_id}", get(get_project_detail))
        .route("/ledgers", get(list_ledgers))
        .route("/ledgers/{ledger_id}", get(get_ledger))
        .route("/ledgers/{ledger_id}/status", post(change_ledger_status))
        .route("/reminders", get(list_reminders))
        .route("/reminders/run", post(request_reminder_run))
        .route("/imports/files/retry", post(retry_import_file))
        .route(
            "/imports/files/sessions/{session_id}",
            get(get_import_session),
        )
        .route("/matching/run", post(request_matching_run))
        .route("/matching/results", get(list_matching_results))
        .route("/matching/results/{result_id}", get(get_matching_result))
}

async fn acknowledge_background_job(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Path(job_id): Path<String>,
    Json(mut request): Json<AcknowledgeBackgroundJobRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let job_id = parse_uuid("job_id", &job_id)?;
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .acknowledge_background_job(job_id, request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn retry_background_job(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Path(job_id): Path<String>,
    Json(mut request): Json<RetryBackgroundJobRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let job_id = parse_uuid("job_id", &job_id)?;
    apply_idempotency_header(&headers, &mut request.idempotency_key);
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

async fn save_workbench_settings(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<WorkbenchSettingsWriteRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .save_workbench_settings(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn request_project_sync(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<ProjectSyncRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .request_project_sync(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn create_settings_project(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<ProjectProfileWriteRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .create_settings_project(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn delete_settings_project(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Path(project_id): Path<String>,
    Json(mut request): Json<ProjectDeleteRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let project_id = parse_uuid("project_id", &project_id)?;
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .delete_settings_project(project_id, request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn create_data_reset_job(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<DataResetJobRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .create_data_reset_job(request, trusted_actor(&session, trace_id))
                .await?,
        ),
    ))
}

async fn request_data_reset_execution(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<DataResetJobRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .request_data_reset_execution(request, trusted_actor(&session, trace_id))
                .await?,
        ),
    ))
}

async fn list_projects(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.list_projects().await?))
}

async fn create_project(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<ProjectProfileWriteRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .create_project(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn get_project_detail(
    State(state): State<AppState>,
    Path(project_id): Path<String>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.get_project_detail(&project_id).await?))
}

async fn assign_project(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<ProjectAssignRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .assign_project(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn list_ledgers(
    State(state): State<AppState>,
    Query(request): Query<LedgerListRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.list_ledgers(request).await?))
}

async fn get_ledger(
    State(state): State<AppState>,
    Path(ledger_id): Path<String>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let ledger_id = parse_uuid("ledger_id", &ledger_id)?;
    let service = build_service(&state);
    Ok(Json(service.get_ledger(ledger_id).await?))
}

async fn change_ledger_status(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Path(ledger_id): Path<String>,
    Json(mut request): Json<LedgerStatusRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let ledger_id = parse_uuid("ledger_id", &ledger_id)?;
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok(Json(
        service
            .change_ledger_status(ledger_id, request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

async fn list_reminders(
    State(state): State<AppState>,
    Query(request): Query<ReminderListRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    let service = build_service(&state);
    Ok(Json(service.list_reminders(request).await?))
}

async fn request_reminder_run(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    headers: HeaderMap,
    Json(mut request): Json<ReminderRunRequest>,
) -> Result<impl IntoResponse, PlatformLegacyApiError> {
    apply_idempotency_header(&headers, &mut request.idempotency_key);
    let service = build_service(&state);
    Ok((
        StatusCode::ACCEPTED,
        Json(
            service
                .request_reminder_run(request, trusted_actor(&session, trace_id))
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

fn apply_idempotency_header(headers: &HeaderMap, target: &mut Option<String>) {
    if target
        .as_deref()
        .is_some_and(|value| !value.trim().is_empty())
    {
        return;
    }
    if let Some(value) = headers
        .get("Idempotency-Key")
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .filter(|value| !value.is_empty())
    {
        *target = Some(value.to_owned());
    }
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
                code: not_found_code(resource),
                message: format!("{resource} was not found"),
            },
            PlatformLegacyServiceError::Repository(
                PlatformLegacyRepositoryError::IdempotencyConflict,
            ) => Self::Conflict {
                code: "idempotency_conflict",
                message: "idempotency key was reused with a different payload".to_owned(),
            },
            PlatformLegacyServiceError::Repository(PlatformLegacyRepositoryError::Conflict {
                code,
                message,
            }) => Self::Conflict { code, message },
            PlatformLegacyServiceError::Repository(PlatformLegacyRepositoryError::NotFound {
                resource,
            }) => Self::NotFound {
                code: not_found_code(resource),
                message: format!("{resource} was not found"),
            },
            PlatformLegacyServiceError::Repository(PlatformLegacyRepositoryError::Database(_)) => {
                Self::DatabaseUnavailable
            }
        }
    }
}

fn not_found_code(resource: &'static str) -> &'static str {
    match resource {
        "background_job" => "background_job_not_found",
        "project" => "project_not_found",
        "project_or_object" => "project_or_object_not_found",
        "ledger" => "ledger_not_found",
        "settings_version" => "settings_version_conflict",
        "retryable_background_job" => "background_job_not_retryable",
        "retryable_import_file" => "import_file_not_retryable",
        _ => "not_found",
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
