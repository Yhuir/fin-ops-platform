use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Serialize;
use uuid::Uuid;

use crate::{
    repositories::read_models::SqlxReadModelRepository,
    services::read_models::{
        ReadModelService, ReadModelServiceError, SearchQuery, WorkbenchMonthQuery,
        WorkbenchRowDetailQuery,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/workbench", get(get_workbench))
        .route("/api/workbench/ignored", get(get_ignored_workbench_rows))
        .route(
            "/api/workbench/read-model/status",
            get(get_workbench_status),
        )
        .route("/api/workbench/rows/{row_id}", get(get_workbench_row))
        .route("/api/search", get(search))
}

async fn get_workbench(
    State(state): State<AppState>,
    Query(query): Query<WorkbenchMonthQuery>,
) -> Result<impl IntoResponse, ReadModelApiError> {
    let service = build_service(&state);
    Ok(Json(service.get_workbench(query).await?))
}

async fn get_ignored_workbench_rows(
    State(state): State<AppState>,
    Query(query): Query<WorkbenchMonthQuery>,
) -> Result<impl IntoResponse, ReadModelApiError> {
    let service = build_service(&state);
    Ok(Json(service.get_ignored_rows(query).await?))
}

async fn get_workbench_status(
    State(state): State<AppState>,
    Query(query): Query<WorkbenchMonthQuery>,
) -> Result<impl IntoResponse, ReadModelApiError> {
    let service = build_service(&state);
    Ok(Json(service.get_workbench_status(query).await?))
}

async fn get_workbench_row(
    State(state): State<AppState>,
    Path(row_id): Path<String>,
    Query(query): Query<WorkbenchRowDetailQuery>,
) -> Result<impl IntoResponse, ReadModelApiError> {
    let row_id = Uuid::parse_str(&row_id).map_err(|_| ReadModelApiError::BadRequest {
        code: "invalid_row_id",
        message: "row_id must be a UUID".to_owned(),
    })?;
    let service = build_service(&state);
    Ok(Json(service.get_row_detail(row_id, query).await?))
}

async fn search(
    State(state): State<AppState>,
    Query(query): Query<SearchQuery>,
) -> Result<impl IntoResponse, ReadModelApiError> {
    let service = build_service(&state);
    Ok(Json(service.search(query).await?))
}

fn build_service(state: &AppState) -> ReadModelService<SqlxReadModelRepository> {
    ReadModelService::new(SqlxReadModelRepository::new(state.db.clone()))
}

#[derive(Debug)]
enum ReadModelApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<ReadModelServiceError> for ReadModelApiError {
    fn from(error: ReadModelServiceError) -> Self {
        match error {
            ReadModelServiceError::InvalidRequest { code, message } => Self::BadRequest {
                code,
                message: message.to_owned(),
            },
            ReadModelServiceError::NotFound { resource } => Self::NotFound {
                code: "read_model_not_found",
                message: format!("{resource} was not found"),
            },
            ReadModelServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl IntoResponse for ReadModelApiError {
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
    async fn workbench_rejects_all_time_without_database_access() {
        let response = request("/api/workbench?month=all").await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "all_time_workbench_not_supported");
    }

    #[tokio::test]
    async fn search_empty_query_returns_frontend_compatible_empty_payload() {
        let response = request("/api/search?q=&scope=all&month=all").await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["summary"]["total"], 0);
        assert!(body["oa_results"].as_array().unwrap().is_empty());
        assert!(body["bank_results"].as_array().unwrap().is_empty());
        assert!(body["invoice_results"].as_array().unwrap().is_empty());
    }

    #[tokio::test]
    async fn row_detail_rejects_non_uuid_row_id() {
        let response = request("/api/workbench/rows/not-a-uuid").await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_row_id");
    }

    async fn request(uri: &str) -> axum::response::Response {
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
