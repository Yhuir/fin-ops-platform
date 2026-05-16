use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::{
    repositories::turnover_ledger::SqlxTurnoverLedgerRepository,
    services::turnover_ledger::{
        TurnoverLedgerQuery, TurnoverLedgerService, TurnoverLedgerServiceError,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/turnover-ledger", get(get_turnover_ledger))
        .route(
            "/api/turnover-ledger/export-preview",
            get(get_turnover_ledger_export_preview),
        )
        .route(
            "/api/turnover-ledger/relations/{relation_id}",
            get(get_turnover_ledger_relation),
        )
}

async fn get_turnover_ledger(
    State(state): State<AppState>,
    Query(query): Query<TurnoverLedgerQuery>,
) -> Result<impl IntoResponse, TurnoverLedgerApiError> {
    let grouped = query
        .view
        .as_deref()
        .is_some_and(|view| view.trim().eq_ignore_ascii_case("grouped"));
    let service = TurnoverLedgerService::new(SqlxTurnoverLedgerRepository::new(state.db.clone()));
    let payload = if grouped {
        serde_json::to_value(service.list_grouped_ledger(query).await?)
    } else {
        serde_json::to_value(service.list_ledger(query).await?)
    }
    .map_err(|_| TurnoverLedgerApiError::DatabaseUnavailable)?;
    Ok(Json(payload))
}

async fn get_turnover_ledger_export_preview(
    State(state): State<AppState>,
    Query(query): Query<TurnoverLedgerQuery>,
) -> Result<impl IntoResponse, TurnoverLedgerApiError> {
    let service = TurnoverLedgerService::new(SqlxTurnoverLedgerRepository::new(state.db.clone()));
    Ok(Json(service.export_preview(query).await?))
}

async fn get_turnover_ledger_relation(
    State(state): State<AppState>,
    Path(relation_id): Path<String>,
) -> Result<impl IntoResponse, TurnoverLedgerApiError> {
    let service = TurnoverLedgerService::new(SqlxTurnoverLedgerRepository::new(state.db.clone()));
    Ok(Json(service.get_relation_detail(&relation_id).await?))
}

#[derive(Debug)]
enum TurnoverLedgerApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<TurnoverLedgerServiceError> for TurnoverLedgerApiError {
    fn from(error: TurnoverLedgerServiceError) -> Self {
        match error {
            TurnoverLedgerServiceError::InvalidRequest { code, message } => Self::BadRequest {
                code,
                message: message.to_owned(),
            },
            TurnoverLedgerServiceError::UnknownRelationId => Self::NotFound {
                code: "unknown_relation_id",
                message: "往来款关系不存在。".to_owned(),
            },
            TurnoverLedgerServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl IntoResponse for TurnoverLedgerApiError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            Self::BadRequest { code, message } => (
                StatusCode::BAD_REQUEST,
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
            Self::NotFound { code, message } => (
                StatusCode::NOT_FOUND,
                ErrorDetails {
                    error: code.to_owned(),
                    message,
                },
            ),
        };
        (status, Json(body)).into_response()
    }
}
