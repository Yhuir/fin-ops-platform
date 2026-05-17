use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::patch,
    Json, Router,
};
use serde::Serialize;

use crate::{
    middleware::{auth::AuthenticatedSession, trace_id::TraceId},
    repositories::finance_writes::SqlxFinanceWriteRepository,
    services::{
        finance_writes::{
            BankCategoryUpdateRequest, FinanceWriteRepositoryError, FinanceWriteService,
            FinanceWriteServiceError,
        },
        workbench_writes::WriteActor,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new().route(
        "/api/bank-details/transactions/categories",
        patch(update_bank_transaction_categories),
    )
}

async fn update_bank_transaction_categories(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<BankCategoryUpdateRequest>,
) -> Result<impl IntoResponse, FinanceWriteApiError> {
    Ok(Json(
        build_service(&state)
            .save_bank_transaction_categories_as(request, trusted_actor(&session, trace_id))
            .await?,
    ))
}

fn build_service(state: &AppState) -> FinanceWriteService<SqlxFinanceWriteRepository> {
    FinanceWriteService::new(SqlxFinanceWriteRepository::new(state.db.clone()))
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

#[derive(Debug)]
enum FinanceWriteApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    Conflict { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<FinanceWriteServiceError> for FinanceWriteApiError {
    fn from(error: FinanceWriteServiceError) -> Self {
        match error {
            FinanceWriteServiceError::InvalidRequest { code, message } => {
                Self::BadRequest { code, message }
            }
            FinanceWriteServiceError::Conflict { code, message } => {
                Self::Conflict { code, message }
            }
            FinanceWriteServiceError::NotFound { resource } => Self::NotFound {
                code: "not_found",
                message: format!("{resource} was not found"),
            },
            FinanceWriteServiceError::Repository(
                FinanceWriteRepositoryError::IdempotencyConflict,
            ) => Self::Conflict {
                code: "idempotency_conflict",
                message: "idempotency key was reused with a different payload".to_owned(),
            },
            FinanceWriteServiceError::Repository(FinanceWriteRepositoryError::Conflict {
                code,
                message,
            }) => Self::Conflict { code, message },
            FinanceWriteServiceError::Repository(FinanceWriteRepositoryError::NotFound {
                resource,
            }) => Self::NotFound {
                code: "not_found",
                message: format!("{resource} was not found"),
            },
            FinanceWriteServiceError::Repository(FinanceWriteRepositoryError::Database(_)) => {
                Self::DatabaseUnavailable
            }
        }
    }
}

impl IntoResponse for FinanceWriteApiError {
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

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::Request,
    };
    use serde_json::{json, Value};
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
    async fn category_patch_rejects_unknown_category_before_database_write() {
        let response = patch_json(json!({
            "updates": [
                {
                    "transaction_id": "00000000-0000-0000-0000-000000000001",
                    "category_code": "not_a_frozen_category",
                    "expected_version": 1
                }
            ]
        }))
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_category_update");
    }

    async fn patch_json(payload: Value) -> axum::response::Response {
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
                    .method("PATCH")
                    .uri("/api/bank-details/transactions/categories")
                    .header("content-type", "application/json")
                    .header("authorization", "Bearer opaque-oa-token")
                    .header("x-fin-ops-oa-user-id", "YNSYLP005-id")
                    .header("x-fin-ops-oa-username", "YNSYLP005")
                    .header("x-fin-ops-oa-permissions", "finops:app:view")
                    .body(Body::from(payload.to_string()))
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
