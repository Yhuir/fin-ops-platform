use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::post,
    Json, Router,
};
use serde::Serialize;
use uuid::Uuid;

use crate::{
    middleware::{auth::AuthenticatedSession, trace_id::TraceId},
    repositories::workbench_writes::SqlxWorkbenchWriteRepository,
    services::workbench_writes::{
        BankExceptionRequest, CancelExceptionRequest, CashSpecialRequest, ConfirmLinkRequest,
        ExceptionApplyRequest, MarkExceptionRequest, NoOaBatchSubmitRequest,
        NoOaBatchWithdrawRequest, NoOaBulkSubmitRequest, RevokeLinkRequest, RowOverrideRequest,
        WorkbenchWriteRepositoryError, WorkbenchWriteService, WorkbenchWriteServiceError,
        WriteActor,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/workbench/actions/confirm-link", post(confirm_link))
        .route(
            "/api/workbench/actions/confirm-link/preview",
            post(confirm_link_preview),
        )
        .route("/api/workbench/actions/withdraw-link", post(withdraw_link))
        .route(
            "/api/workbench/actions/withdraw-link/preview",
            post(withdraw_link_preview),
        )
        .route("/api/workbench/actions/cancel-link", post(cancel_link))
        .route(
            "/api/workbench/actions/mark-exception",
            post(mark_exception),
        )
        .route(
            "/api/workbench/actions/update-bank-exception",
            post(update_bank_exception),
        )
        .route(
            "/api/workbench/actions/oa-bank-exception",
            post(oa_bank_exception),
        )
        .route(
            "/api/workbench/actions/confirm-personal-advance-repayment",
            post(confirm_personal_advance_repayment),
        )
        .route(
            "/api/workbench/actions/confirm-cash-pass-through",
            post(confirm_cash_pass_through),
        )
        .route(
            "/api/workbench/actions/confirm-cash-ticket-purchase",
            post(confirm_cash_ticket_purchase),
        )
        .route(
            "/api/workbench/actions/cancel-cash-special",
            post(cancel_cash_special),
        )
        .route("/api/workbench/exception/apply", post(apply_exception))
        .route(
            "/api/workbench/actions/cancel-exception",
            post(cancel_exception),
        )
        .route("/api/workbench/actions/ignore-row", post(ignore_row))
        .route("/api/workbench/actions/unignore-row", post(unignore_row))
        .route(
            "/api/no-oa-bank-batches/submit",
            post(bulk_submit_no_oa_batches),
        )
        .route(
            "/api/no-oa-bank-batches/{batch_id}/submit",
            post(submit_no_oa_batch),
        )
        .route(
            "/api/no-oa-bank-batches/{batch_id}/withdraw",
            post(withdraw_no_oa_batch),
        )
}

async fn confirm_link(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<ConfirmLinkRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .confirm_link_as(request, actor)
            .await?,
    ))
}

async fn confirm_link_preview(
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<ConfirmLinkRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    if request.row_ids.len() < 2 {
        return Err(WorkbenchWriteApiError::BadRequest {
            code: "invalid_row_ids",
            message: "confirm_link preview requires at least two row_ids".to_owned(),
        });
    }
    Ok(Json(serde_json::json!({
        "success": true,
        "action": "confirm_link_preview",
        "month": request.month,
        "row_ids": request.row_ids,
        "shadow_only": true,
        "checks": [
            "lock app facts by read_model row source identity",
            "verify source status and remaining amount",
            "compute total_amount, difference_amount and applied_amount before confirm"
        ]
    })))
}

async fn withdraw_link(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<RevokeLinkRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .withdraw_link_as(request, actor)
            .await?,
    ))
}

async fn withdraw_link_preview(
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<RevokeLinkRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    Ok(Json(serde_json::json!({
        "success": true,
        "action": "withdraw_link_preview",
        "month": request.month,
        "case_id": request.case_id,
        "row_id": request.row_id,
        "row_ids": request.row_ids,
        "shadow_only": true,
        "checks": [
            "lock active reconciliation case",
            "lock active reconciliation rows",
            "restore bank/invoice written_off_amount from applied_amount"
        ]
    })))
}

async fn cancel_link(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<RevokeLinkRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state).cancel_link_as(request, actor).await?,
    ))
}

async fn mark_exception(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<MarkExceptionRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .mark_exception_as(request, actor)
            .await?,
    ))
}

async fn update_bank_exception(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<BankExceptionRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .bank_exception_as("update_bank_exception", request, actor)
            .await?,
    ))
}

async fn oa_bank_exception(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<BankExceptionRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .bank_exception_as("oa_bank_exception", request, actor)
            .await?,
    ))
}

async fn confirm_personal_advance_repayment(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<BankExceptionRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    if request.exception_code.is_none() {
        request.exception_code = Some("personal_advance_repayment_settlement".to_owned());
    }
    Ok(Json(
        build_service(&state)
            .bank_exception_as("personal_advance_repayment", request, actor)
            .await?,
    ))
}

async fn confirm_cash_pass_through(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<CashSpecialRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .special_reconciliation_action_as("confirm_cash_pass_through", request, actor)
            .await?,
    ))
}

async fn confirm_cash_ticket_purchase(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<CashSpecialRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .special_reconciliation_action_as("confirm_cash_ticket_purchase", request, actor)
            .await?,
    ))
}

async fn cancel_cash_special(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<CashSpecialRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .special_reconciliation_action_as("cancel_cash_special", request, actor)
            .await?,
    ))
}

async fn apply_exception(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<ExceptionApplyRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .apply_exception_as(request, actor)
            .await?,
    ))
}

async fn cancel_exception(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<CancelExceptionRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .cancel_exception_as(request, actor)
            .await?,
    ))
}

async fn ignore_row(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<RowOverrideRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state).ignore_row_as(request, actor).await?,
    ))
}

async fn unignore_row(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(mut request): Json<RowOverrideRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .unignore_row_as(request, actor)
            .await?,
    ))
}

async fn submit_no_oa_batch(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Path(batch_id): Path<String>,
    Json(mut request): Json<NoOaBatchSubmitRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .submit_no_oa_batch_as(parse_uuid("batch_id", &batch_id)?, request, actor)
            .await?,
    ))
}

async fn withdraw_no_oa_batch(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Path(batch_id): Path<String>,
    Json(mut request): Json<NoOaBatchWithdrawRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_compatible_actor(&request.actor, &actor)?;
    request.actor = actor.actor_id.clone();
    Ok(Json(
        build_service(&state)
            .withdraw_no_oa_batch_as(parse_uuid("batch_id", &batch_id)?, request, actor)
            .await?,
    ))
}

async fn bulk_submit_no_oa_batches(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
    trace_id: Option<Extension<TraceId>>,
    Json(request): Json<NoOaBulkSubmitRequest>,
) -> Result<impl IntoResponse, WorkbenchWriteApiError> {
    let actor = trusted_actor(&session, trace_id);
    enforce_bulk_actor_compatibility(&request, &actor)?;
    Ok(Json(
        build_service(&state)
            .bulk_submit_no_oa_batches_as(request, actor)
            .await,
    ))
}

fn build_service(state: &AppState) -> WorkbenchWriteService<SqlxWorkbenchWriteRepository> {
    WorkbenchWriteService::new(SqlxWorkbenchWriteRepository::new(state.db.clone()))
}

fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, WorkbenchWriteApiError> {
    Uuid::parse_str(value).map_err(|_| WorkbenchWriteApiError::BadRequest {
        code: "invalid_uuid",
        message: format!("{field} must be a valid UUID"),
    })
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

fn enforce_compatible_actor(
    body_actor: &str,
    trusted_actor: &WriteActor,
) -> Result<(), WorkbenchWriteApiError> {
    let body_actor = body_actor.trim();
    if body_actor.is_empty() || body_actor == trusted_actor.actor_id {
        return Ok(());
    }
    Err(WorkbenchWriteApiError::Forbidden {
        code: "actor_mismatch",
        message: "body actor does not match authenticated OA session".to_owned(),
    })
}

fn enforce_optional_actor(
    body_actor: Option<&String>,
    trusted_actor: &WriteActor,
) -> Result<(), WorkbenchWriteApiError> {
    match body_actor {
        Some(actor) => enforce_compatible_actor(actor, trusted_actor),
        None => Ok(()),
    }
}

fn enforce_bulk_actor_compatibility(
    request: &NoOaBulkSubmitRequest,
    trusted_actor: &WriteActor,
) -> Result<(), WorkbenchWriteApiError> {
    enforce_optional_actor(request.actor.as_ref(), trusted_actor)?;
    for item in &request.batches {
        enforce_optional_actor(item.actor.as_ref(), trusted_actor)?;
    }
    Ok(())
}

#[derive(Debug)]
enum WorkbenchWriteApiError {
    BadRequest { code: &'static str, message: String },
    Forbidden { code: &'static str, message: String },
    Conflict { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<WorkbenchWriteServiceError> for WorkbenchWriteApiError {
    fn from(error: WorkbenchWriteServiceError) -> Self {
        match error {
            WorkbenchWriteServiceError::InvalidRequest { code, message } => {
                Self::BadRequest { code, message }
            }
            WorkbenchWriteServiceError::Conflict { code, message } => {
                Self::Conflict { code, message }
            }
            WorkbenchWriteServiceError::NotFound { resource } => Self::NotFound {
                code: match resource {
                    "workbench_row" => "workbench_row_not_found",
                    "reconciliation_case" => "reconciliation_case_not_found",
                    "exception_case" => "exception_case_not_found",
                    "no_oa_bank_batch" => "no_oa_bank_batch_not_found",
                    _ => "not_found",
                },
                message: format!("{resource} was not found"),
            },
            WorkbenchWriteServiceError::Repository(error) => match error {
                WorkbenchWriteRepositoryError::Database(_) => Self::DatabaseUnavailable,
                WorkbenchWriteRepositoryError::IdempotencyConflict => Self::Conflict {
                    code: "idempotency_key_reused_with_different_payload",
                    message: "idempotency key was reused with a different payload".to_owned(),
                },
                WorkbenchWriteRepositoryError::Conflict { code, message } => {
                    Self::Conflict { code, message }
                }
                WorkbenchWriteRepositoryError::NotFound { resource } => Self::NotFound {
                    code: "not_found",
                    message: format!("{resource} was not found"),
                },
            },
        }
    }
}

impl IntoResponse for WorkbenchWriteApiError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            Self::BadRequest { code, message } => (
                StatusCode::BAD_REQUEST,
                ErrorDetails {
                    error: code.to_owned(),
                    message,
                },
            ),
            Self::Forbidden { code, message } => (
                StatusCode::FORBIDDEN,
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
    async fn confirm_link_missing_idempotency_returns_public_400_without_database_write() {
        let response = post_json(
            "/api/workbench/actions/confirm-link",
            json!({
                "month": "2026-05",
                "row_ids": [
                    "00000000-0000-0000-0000-000000000001",
                    "00000000-0000-0000-0000-000000000002"
                ],
                "idempotency_key": "",
                "actor": "YNSYLP005"
            }),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "missing_idempotency_key");
    }

    #[tokio::test]
    async fn no_oa_submit_rejects_invalid_batch_id() {
        let response = post_json(
            "/api/no-oa-bank-batches/not-a-uuid/submit",
            json!({
                "expected_version": 1,
                "idempotency_key": "no-oa:1",
                "actor": "YNSYLP005"
            }),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_uuid");
    }

    async fn post_json(uri: &str, payload: Value) -> axum::response::Response {
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
                    .method("POST")
                    .uri(uri)
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
