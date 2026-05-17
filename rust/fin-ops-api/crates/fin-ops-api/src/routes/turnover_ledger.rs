use axum::{
    body::Body,
    extract::{Path, Query, State},
    http::{
        header::{CONTENT_DISPOSITION, CONTENT_TYPE},
        StatusCode,
    },
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
            "/api/turnover-ledger/export",
            get(get_turnover_ledger_export),
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

async fn get_turnover_ledger_export(
    State(state): State<AppState>,
    Query(query): Query<TurnoverLedgerQuery>,
) -> Result<Response, TurnoverLedgerApiError> {
    let service = TurnoverLedgerService::new(SqlxTurnoverLedgerRepository::new(state.db.clone()));
    let file = service.export_xlsx(query, &current_china_date()).await?;
    Response::builder()
        .status(StatusCode::OK)
        .header(CONTENT_TYPE, file.content_type)
        .header(CONTENT_DISPOSITION, content_disposition(&file.filename))
        .header("x-fin-ops-export-row-count", file.row_count.to_string())
        .body(Body::from(file.bytes))
        .map_err(|_| TurnoverLedgerApiError::DatabaseUnavailable)
}

async fn get_turnover_ledger_relation(
    State(state): State<AppState>,
    Path(relation_id): Path<String>,
) -> Result<impl IntoResponse, TurnoverLedgerApiError> {
    let service = TurnoverLedgerService::new(SqlxTurnoverLedgerRepository::new(state.db.clone()));
    Ok(Json(service.get_relation_detail(&relation_id).await?))
}

fn content_disposition(filename: &str) -> String {
    format!("attachment; filename*=UTF-8''{}", percent_encode(filename))
}

fn percent_encode(value: &str) -> String {
    let mut encoded = String::new();
    for byte in value.as_bytes() {
        let ch = *byte as char;
        if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.' | '~') {
            encoded.push(ch);
        } else {
            encoded.push_str(&format!("%{byte:02X}"));
        }
    }
    encoded
}

fn current_china_date() -> String {
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default();
    let days = ((now.as_secs() + 8 * 3_600) / 86_400) as i64;
    let (year, month, day) = civil_from_days(days);
    format!("{year:04}-{month:02}-{day:02}")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_unix_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 } / 146_097;
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1_460 + doe / 36_524 - doe / 146_096) / 365;
    let y = yoe + era * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = mp + if mp < 10 { 3 } else { -9 };
    let year = y + if month <= 2 { 1 } else { 0 };
    (year, month, day)
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
