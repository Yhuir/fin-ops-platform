use axum::{
    extract::{Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::{
    repositories::task_status::SqlxTaskStatusRepository,
    services::task_status::{TaskStatusService, TaskStatusServiceError},
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/tasks/{task_id}/status", get(get_task_status))
        .route(
            "/api/background-jobs/active",
            get(get_active_background_jobs),
        )
        .route("/api/background-jobs/{job_id}", get(get_background_job))
        .route(
            "/api/workbench/settings/data-reset/jobs/active",
            get(get_active_data_reset_job),
        )
        .route(
            "/api/workbench/settings/data-reset/jobs/{job_id}",
            get(get_data_reset_job),
        )
}

async fn get_task_status(
    State(state): State<AppState>,
    Path(task_id): Path<String>,
) -> Result<impl IntoResponse, TaskStatusApiError> {
    let task_id = uuid::Uuid::parse_str(&task_id).map_err(|_| TaskStatusApiError::InvalidTaskId)?;
    let repository = SqlxTaskStatusRepository::new(state.db.clone());
    let service = TaskStatusService::new(repository);
    let response = service.get_task_status(task_id).await?;

    Ok(Json(response))
}

async fn get_active_background_jobs(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, BackgroundJobsApiError> {
    let repository = SqlxTaskStatusRepository::new(state.db.clone());
    let service = TaskStatusService::new(repository);
    Ok(Json(service.get_active_background_jobs().await?))
}

async fn get_background_job(
    State(state): State<AppState>,
    Path(job_id): Path<String>,
) -> Result<impl IntoResponse, BackgroundJobsApiError> {
    let job_id = uuid::Uuid::parse_str(&job_id).map_err(|_| BackgroundJobsApiError::NotFound)?;
    let repository = SqlxTaskStatusRepository::new(state.db.clone());
    let service = TaskStatusService::new(repository);
    Ok(Json(service.get_background_job(job_id).await?))
}

async fn get_active_data_reset_job(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, DataResetJobApiError> {
    let repository = SqlxTaskStatusRepository::new(state.db.clone());
    let service = TaskStatusService::new(repository);
    Ok(Json(service.get_active_data_reset_job().await?))
}

async fn get_data_reset_job(
    State(state): State<AppState>,
    Path(job_id): Path<String>,
) -> Result<impl IntoResponse, DataResetJobApiError> {
    let job_id = uuid::Uuid::parse_str(&job_id).map_err(|_| DataResetJobApiError::NotFound)?;
    let repository = SqlxTaskStatusRepository::new(state.db.clone());
    let service = TaskStatusService::new(repository);
    Ok(Json(service.get_data_reset_job(job_id).await?))
}

#[derive(Debug)]
enum TaskStatusApiError {
    InvalidTaskId,
    NotFound,
    DatabaseUnavailable,
}

#[derive(Debug)]
enum DataResetJobApiError {
    NotFound,
    DatabaseUnavailable,
}

#[derive(Debug)]
enum BackgroundJobsApiError {
    NotFound,
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorBody {
    error: ErrorDetails,
}

#[derive(Serialize)]
struct ErrorDetails {
    code: &'static str,
    message: &'static str,
}

#[derive(Serialize)]
struct LegacyErrorDetails {
    error: &'static str,
    message: &'static str,
}

impl From<TaskStatusServiceError> for TaskStatusApiError {
    fn from(error: TaskStatusServiceError) -> Self {
        match error {
            TaskStatusServiceError::NotFound => Self::NotFound,
            TaskStatusServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl From<TaskStatusServiceError> for DataResetJobApiError {
    fn from(error: TaskStatusServiceError) -> Self {
        match error {
            TaskStatusServiceError::NotFound => Self::NotFound,
            TaskStatusServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl From<TaskStatusServiceError> for BackgroundJobsApiError {
    fn from(error: TaskStatusServiceError) -> Self {
        match error {
            TaskStatusServiceError::NotFound => Self::NotFound,
            TaskStatusServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl IntoResponse for TaskStatusApiError {
    fn into_response(self) -> Response {
        let (status, code, message) = match self {
            Self::InvalidTaskId => (
                StatusCode::BAD_REQUEST,
                "invalid_task_id",
                "task_id must be a UUID",
            ),
            Self::NotFound => (
                StatusCode::NOT_FOUND,
                "task_not_found",
                "task was not found",
            ),
            Self::DatabaseUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "database_unavailable",
                "database dependency is unavailable",
            ),
        };
        (
            status,
            Json(ErrorBody {
                error: ErrorDetails { code, message },
            }),
        )
            .into_response()
    }
}

impl IntoResponse for DataResetJobApiError {
    fn into_response(self) -> Response {
        let (status, error, message) = match self {
            Self::NotFound => (
                StatusCode::NOT_FOUND,
                "settings_data_reset_job_not_found",
                "数据重置任务不存在或已过期。",
            ),
            Self::DatabaseUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "database_unavailable",
                "database dependency is unavailable",
            ),
        };
        (status, Json(LegacyErrorDetails { error, message })).into_response()
    }
}

impl IntoResponse for BackgroundJobsApiError {
    fn into_response(self) -> Response {
        let (status, error, message) = match self {
            Self::NotFound => (
                StatusCode::NOT_FOUND,
                "background_job_not_found",
                "后台任务不存在或不可见。",
            ),
            Self::DatabaseUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                "database_unavailable",
                "database dependency is unavailable",
            ),
        };
        (status, Json(LegacyErrorDetails { error, message })).into_response()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    #[tokio::test]
    async fn background_jobs_error_keeps_legacy_top_level_shape() {
        let response = BackgroundJobsApiError::DatabaseUnavailable.into_response();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = to_bytes(response.into_body(), 1024).await.unwrap();
        let payload: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(payload["error"], "database_unavailable");
        assert_eq!(payload["message"], "database dependency is unavailable");
        assert!(payload
            .get("error")
            .and_then(|value| value.get("code"))
            .is_none());
    }
}
