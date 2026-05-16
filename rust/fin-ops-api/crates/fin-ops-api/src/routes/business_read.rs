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
    repositories::business_read::SqlxBusinessReadRepository,
    services::business_read::{
        BankDetailAccountsQuery, BankDetailTransactionsQuery, BusinessReadService,
        BusinessReadServiceError, CostExportPreviewQuery, CostProjectStatisticsQuery,
        CostReadModelQuery, CostTransactionDetailQuery, EtcBatchQuery, EtcInvoiceListQuery,
        NoOaBatchListQuery, TaxCertifiedImportsQuery, TaxOffsetQuery,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/bank-details/accounts", get(list_bank_detail_accounts))
        .route(
            "/api/bank-details/transactions",
            get(list_bank_detail_transactions),
        )
        .route("/api/no-oa-bank-batches", get(list_no_oa_bank_batches))
        .route(
            "/api/no-oa-bank-batches/{batch_id}",
            get(get_no_oa_bank_batch),
        )
        .route("/api/tax-offset", get(get_tax_offset))
        .route("/api/tax-offset/calculate", post(calculate_tax_offset))
        .route(
            "/api/tax-offset/certified-imports",
            get(get_tax_certified_imports),
        )
        .route("/api/etc/import", post(etc_direct_import_removed))
        .route("/api/etc/invoices", get(list_etc_invoices))
        .route("/api/etc/batches", get(list_etc_batches))
        .route("/api/etc/batches/{batch_id}", get(get_etc_batch))
        .route("/api/cost-statistics", get(get_cost_statistics))
        .route("/api/cost-statistics/explorer", get(get_cost_statistics))
        .route(
            "/api/cost-statistics/projects/{project_name}",
            get(get_cost_project_statistics),
        )
        .route(
            "/api/cost-statistics/export-preview",
            get(get_cost_export_preview),
        )
        .route(
            "/api/cost-statistics/transactions/{transaction_id}",
            get(get_cost_transaction_detail),
        )
        .route("/api/oa-sync/status", get(get_oa_sync_status))
}

async fn list_bank_detail_accounts(
    State(state): State<AppState>,
    Query(query): Query<BankDetailAccountsQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state)
            .list_bank_detail_accounts(query)
            .await?,
    ))
}

async fn list_bank_detail_transactions(
    State(state): State<AppState>,
    Query(query): Query<BankDetailTransactionsQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state)
            .list_bank_detail_transactions(query)
            .await?,
    ))
}

async fn list_no_oa_bank_batches(
    State(state): State<AppState>,
    Query(query): Query<NoOaBatchListQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).list_no_oa_batches(query).await?))
}

async fn get_no_oa_bank_batch(
    State(state): State<AppState>,
    Path(batch_id): Path<String>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    let batch_id = parse_uuid("batch_id", &batch_id)?;
    Ok(Json(build_service(&state).get_no_oa_batch(batch_id).await?))
}

async fn get_tax_offset(
    State(state): State<AppState>,
    Query(query): Query<TaxOffsetQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).get_tax_offset(query).await?))
}

async fn calculate_tax_offset(
    State(state): State<AppState>,
    Json(request): Json<crate::services::business_read::TaxOffsetCalculateRequest>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state).calculate_tax_offset(request).await?,
    ))
}

async fn get_tax_certified_imports(
    State(state): State<AppState>,
    Query(query): Query<TaxCertifiedImportsQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state)
            .get_tax_certified_imports(query)
            .await?,
    ))
}

async fn list_etc_invoices(
    State(state): State<AppState>,
    Query(query): Query<EtcInvoiceListQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).list_etc_invoices(query).await?))
}

async fn etc_direct_import_removed() -> impl IntoResponse {
    (
        StatusCode::GONE,
        Json(ErrorDetails {
            error: "etc_direct_import_removed".to_owned(),
            message: "Use /api/etc/import/preview and /api/etc/import/confirm.".to_owned(),
        }),
    )
}

async fn list_etc_batches(
    State(state): State<AppState>,
    Query(query): Query<EtcBatchQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).list_etc_batches(query).await?))
}

async fn get_etc_batch(
    State(state): State<AppState>,
    Path(batch_id): Path<String>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).get_etc_batch(&batch_id).await?))
}

async fn get_cost_statistics(
    State(state): State<AppState>,
    Query(query): Query<CostReadModelQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state).get_cost_statistics(query).await?,
    ))
}

async fn get_cost_project_statistics(
    State(state): State<AppState>,
    Path(project_name): Path<String>,
    Query(mut query): Query<CostProjectStatisticsQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    query.project_name = project_name;
    Ok(Json(
        build_service(&state)
            .get_cost_project_statistics(query)
            .await?,
    ))
}

async fn get_cost_export_preview(
    State(state): State<AppState>,
    Query(query): Query<CostExportPreviewQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(
        build_service(&state).get_cost_export_preview(query).await?,
    ))
}

async fn get_cost_transaction_detail(
    State(state): State<AppState>,
    Path(transaction_id): Path<String>,
    Query(mut query): Query<CostTransactionDetailQuery>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    query.transaction_id = transaction_id;
    Ok(Json(
        build_service(&state)
            .get_cost_transaction_detail(query)
            .await?,
    ))
}

async fn get_oa_sync_status(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, BusinessReadApiError> {
    Ok(Json(build_service(&state).oa_sync_status().await?))
}

fn build_service(state: &AppState) -> BusinessReadService<SqlxBusinessReadRepository> {
    BusinessReadService::new(SqlxBusinessReadRepository::new(state.db.clone()))
}

fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, BusinessReadApiError> {
    Uuid::parse_str(value).map_err(|_| BusinessReadApiError::BadRequest {
        code: "invalid_uuid",
        message: format!("{field} must be a valid UUID"),
    })
}

#[derive(Debug)]
enum BusinessReadApiError {
    BadRequest { code: &'static str, message: String },
    NotFound { code: &'static str, message: String },
    DatabaseUnavailable,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: String,
    message: String,
}

impl From<BusinessReadServiceError> for BusinessReadApiError {
    fn from(error: BusinessReadServiceError) -> Self {
        match error {
            BusinessReadServiceError::InvalidRequest { code, message } => Self::BadRequest {
                code,
                message: message.to_owned(),
            },
            BusinessReadServiceError::NotFound { resource } => Self::NotFound {
                code: match resource {
                    "no_oa_bank_batch" => "no_oa_bank_batch_not_found",
                    "etc_batch" => "etc_batch_not_found",
                    "tax_offset_read_model" => "tax_offset_read_model_not_found",
                    "cost_statistics_read_model" => "cost_statistics_read_model_not_found",
                    "cost_statistics_transaction" => "cost_statistics_transaction_not_found",
                    _ => "not_found",
                },
                message: format!("{resource} was not found"),
            },
            BusinessReadServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl IntoResponse for BusinessReadApiError {
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
