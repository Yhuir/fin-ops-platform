use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use uuid::Uuid;

use crate::repositories::business_read::{
    BankDetailAccountRow, BankDetailTransactionFilter, BankDetailTransactionRow,
    BankDetailTransactionRows, BusinessReadRepository, BusinessReadRepositoryError,
    EtcBatchDetailRows, EtcBatchRow, EtcBatchRows, EtcInvoiceRow, EtcInvoiceRows,
    EtcPlateSummaryRow, NoOaBatchRow, NoOaDetailRow, OaSyncStatusRow, ReadModelPayloadRow,
    TaxCertifiedImportRow, WorkbenchStaleScopeRow,
};

#[derive(Debug, thiserror::Error)]
pub enum BusinessReadServiceError {
    #[error("resource not found")]
    NotFound { resource: &'static str },
    #[error("invalid request: {message}")]
    InvalidRequest {
        code: &'static str,
        message: &'static str,
    },
    #[error(transparent)]
    Repository(#[from] BusinessReadRepositoryError),
}

pub struct BusinessReadService<R> {
    repository: R,
}

impl<R> BusinessReadService<R>
where
    R: BusinessReadRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn list_no_oa_batches(
        &self,
        query: NoOaBatchListQuery,
    ) -> Result<NoOaBatchListResponse, BusinessReadServiceError> {
        let month = optional_month(query.month.as_deref())?;
        let batches = self
            .repository
            .list_no_oa_batches(NoOaBatchListFilter {
                month,
                status: clean_optional(query.status),
                bucket: clean_optional(query.bucket),
                batch_type: clean_optional(query.r#type),
                account_key: clean_optional(query.account_key),
            })
            .await?;
        Ok(NoOaBatchListResponse::from_rows(batches))
    }

    pub async fn list_bank_detail_accounts(
        &self,
        query: BankDetailAccountsQuery,
    ) -> Result<BankDetailAccountsResponse, BusinessReadServiceError> {
        let filter = BankDetailDateFilter {
            date_from: optional_date(query.date_from.as_deref())?,
            date_to: optional_date(query.date_to.as_deref())?,
        };
        let rows = self.repository.list_bank_detail_accounts(filter).await?;
        Ok(BankDetailAccountsResponse::from_rows(rows))
    }

    pub async fn list_bank_detail_transactions(
        &self,
        query: BankDetailTransactionsQuery,
    ) -> Result<BankDetailTransactionsResponse, BusinessReadServiceError> {
        let page = positive_page(query.page)?;
        let page_size = capped_page_size(query.page_size)?;
        let filter = BankDetailTransactionFilter {
            account_key: clean_optional(query.account_key),
            date_from: optional_date(query.date_from.as_deref())?,
            date_to: optional_date(query.date_to.as_deref())?,
            keyword: clean_optional(query.keyword),
            limit: page_size,
            offset: (page - 1) * page_size,
        };
        let account_key = filter.account_key.clone();
        let date_from = filter.date_from.clone();
        let date_to = filter.date_to.clone();
        let result = self
            .repository
            .list_bank_detail_transactions(filter)
            .await?;
        Ok(BankDetailTransactionsResponse::from_rows(
            account_key,
            date_from,
            date_to,
            page,
            page_size,
            result,
        ))
    }

    pub async fn get_no_oa_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<NoOaBatchDetailResponse, BusinessReadServiceError> {
        let Some((batch, rows)) = self.repository.find_no_oa_batch(batch_id).await? else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "no_oa_bank_batch",
            });
        };
        Ok(NoOaBatchDetailResponse {
            tag_counts: batch.tag_counts.clone(),
            direction_counts: batch.direction_counts.clone(),
            batch: batch.into(),
            rows: rows.into_iter().map(Into::into).collect(),
        })
    }

    pub async fn get_tax_offset(
        &self,
        query: TaxOffsetQuery,
    ) -> Result<Value, BusinessReadServiceError> {
        let month = required_month(query.month.as_deref())?;
        let Some(row) = self.repository.find_tax_offset_read_model(&month).await? else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "tax_offset_read_model",
            });
        };
        read_model_payload(row, json!({ "api_strategy": "tax_offset_read_model_only" }))
    }

    pub async fn calculate_tax_offset(
        &self,
        request: TaxOffsetCalculateRequest,
    ) -> Result<Value, BusinessReadServiceError> {
        let month = required_tax_offset_calculate_month(request.month.as_deref())?;
        request
            .selected_output_ids
            .as_ref()
            .ok_or(BusinessReadServiceError::InvalidRequest {
                code: "invalid_tax_offset_calculate_request",
                message: "selected_output_ids is required",
            })?;
        let selected_input_ids =
            request
                .selected_input_ids
                .ok_or(BusinessReadServiceError::InvalidRequest {
                    code: "invalid_tax_offset_calculate_request",
                    message: "selected_input_ids is required",
                })?;
        let Some(row) = self.repository.find_tax_offset_read_model(&month).await? else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "tax_offset_read_model",
            });
        };
        Ok(tax_offset_calculate_payload(
            &month,
            &row.payload,
            &selected_input_ids,
        ))
    }

    pub async fn get_tax_certified_imports(
        &self,
        query: TaxCertifiedImportsQuery,
    ) -> Result<TaxCertifiedImportsResponse, BusinessReadServiceError> {
        let month = required_tax_certified_import_month(query.month.as_deref())?;
        let records = self.repository.list_tax_certified_imports(&month).await?;
        Ok(TaxCertifiedImportsResponse { month, records })
    }

    pub async fn list_etc_invoices(
        &self,
        query: EtcInvoiceListQuery,
    ) -> Result<EtcInvoiceListResponse, BusinessReadServiceError> {
        let page = etc_page(query.page.as_deref())?;
        let page_size = etc_page_size(query.page_size.as_deref())?;
        let status = clean_optional(query.status)
            .map(valid_etc_invoice_status)
            .transpose()?;
        let rows = self
            .repository
            .list_etc_invoices(EtcInvoiceListFilter {
                status,
                month: optional_month(query.month.as_deref())?,
                plate: clean_optional(query.plate),
                keyword: clean_optional(query.keyword),
                limit: page_size,
                offset: (page - 1) * page_size,
            })
            .await?;
        Ok(EtcInvoiceListResponse::from_rows(page, page_size, rows))
    }

    pub async fn list_etc_batches(
        &self,
        query: EtcBatchQuery,
    ) -> Result<EtcBatchListResponse, BusinessReadServiceError> {
        let page = etc_batch_page(query.page.as_deref())?;
        let page_size = etc_batch_page_size(query.page_size.as_deref())?;
        let rows = self
            .repository
            .list_etc_batches(EtcBatchFilter {
                status: clean_optional(query.status).map(|value| value.to_lowercase()),
                month: optional_month(query.month.as_deref())?,
                plate: clean_optional(query.plate),
                keyword: clean_optional(query.keyword),
                limit: page_size,
                offset: (page - 1) * page_size,
            })
            .await?;

        let selected_detail = if let Some(first) = rows.rows.first() {
            self.repository.find_etc_batch(&first.id).await?
        } else {
            None
        };

        Ok(EtcBatchListResponse::from_rows(
            page,
            page_size,
            rows,
            selected_detail,
        ))
    }

    pub async fn get_etc_batch(
        &self,
        batch_id: &str,
    ) -> Result<EtcBatchDetailResponse, BusinessReadServiceError> {
        let Some(rows) = self.repository.find_etc_batch(batch_id).await? else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "etc_batch",
            });
        };
        Ok(rows.into())
    }

    pub async fn get_cost_statistics(
        &self,
        query: CostReadModelQuery,
    ) -> Result<Value, BusinessReadServiceError> {
        let month = required_month_or_all(query.month.as_deref())?;
        let project_scope = cost_project_scope(query.project_scope.clone())?;
        let Some(row) = self
            .repository
            .find_cost_statistics_read_model(&month, &project_scope)
            .await?
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_read_model",
            });
        };
        read_model_payload(
            row,
            json!({ "api_strategy": "cost_statistics_read_model_only" }),
        )
    }

    pub async fn get_cost_project_statistics(
        &self,
        query: CostProjectStatisticsQuery,
    ) -> Result<Value, BusinessReadServiceError> {
        let month = required_month_or_all(query.month.as_deref())?;
        let project_scope = cost_project_scope(query.project_scope.clone())?;
        let Some(row) = self
            .repository
            .find_cost_statistics_read_model(&month, &project_scope)
            .await?
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_read_model",
            });
        };
        Ok(cost_project_detail_payload(
            &row.payload,
            &month,
            &query.project_name,
        ))
    }

    pub async fn get_cost_export_preview(
        &self,
        query: CostExportPreviewQuery,
    ) -> Result<Value, BusinessReadServiceError> {
        let month = required_month_or_all(query.month.as_deref())?;
        let view = cost_export_preview_view(query.view.as_deref())?;
        let project_scope = cost_project_scope(query.project_scope.clone())?;
        let Some(row) = self
            .repository
            .find_cost_statistics_read_model(&month, &project_scope)
            .await?
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_read_model",
            });
        };
        cost_export_preview_payload(&row.payload, month, view, query)
    }

    pub async fn get_cost_transaction_detail(
        &self,
        query: CostTransactionDetailQuery,
    ) -> Result<Value, BusinessReadServiceError> {
        let project_scope = cost_project_scope(query.project_scope)?;
        let Some(month) = self
            .repository
            .find_cost_transaction_month(&query.transaction_id)
            .await?
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_transaction",
            });
        };
        let Some(row) = self
            .repository
            .find_cost_statistics_read_model(&month, &project_scope)
            .await?
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_read_model",
            });
        };
        let Some(cost_row) = cost_time_rows(&row.payload)
            .into_iter()
            .find(|row| value_string(row, "transaction_id") == query.transaction_id)
        else {
            return Err(BusinessReadServiceError::NotFound {
                resource: "cost_statistics_transaction",
            });
        };
        let workbench_row = self
            .repository
            .find_workbench_row_payload(&query.transaction_id, &month)
            .await?
            .unwrap_or_else(|| json!({}));
        Ok(cost_transaction_detail_payload(
            &month,
            cost_row,
            &query.transaction_id,
            &workbench_row,
        ))
    }

    pub async fn oa_sync_status(&self) -> Result<OaSyncStatusResponse, BusinessReadServiceError> {
        Ok(self.repository.oa_sync_status().await?.into())
    }

    pub async fn list_workbench_stale_scopes(
        &self,
    ) -> Result<Vec<WorkbenchStaleScopeRow>, BusinessReadServiceError> {
        Ok(self.repository.list_workbench_stale_scopes().await?)
    }
}

#[derive(Debug, Deserialize)]
pub struct NoOaBatchListQuery {
    pub month: Option<String>,
    pub status: Option<String>,
    pub bucket: Option<String>,
    pub r#type: Option<String>,
    pub account_key: Option<String>,
}

#[derive(Debug)]
pub struct NoOaBatchListFilter {
    pub month: Option<String>,
    pub status: Option<String>,
    pub bucket: Option<String>,
    pub batch_type: Option<String>,
    pub account_key: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BankDetailAccountsQuery {
    pub date_from: Option<String>,
    pub date_to: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct BankDetailTransactionsQuery {
    pub account_key: Option<String>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
    pub keyword: Option<String>,
    pub page: Option<i64>,
    pub page_size: Option<i64>,
}

#[derive(Debug)]
pub struct BankDetailDateFilter {
    pub date_from: Option<String>,
    pub date_to: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct TaxOffsetQuery {
    pub month: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct TaxOffsetCalculateRequest {
    pub month: Option<String>,
    pub selected_output_ids: Option<Vec<String>>,
    pub selected_input_ids: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct TaxCertifiedImportsQuery {
    pub month: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct EtcInvoiceListQuery {
    pub status: Option<String>,
    pub month: Option<String>,
    pub plate: Option<String>,
    pub keyword: Option<String>,
    pub page: Option<String>,
    pub page_size: Option<String>,
}

#[derive(Debug)]
pub struct EtcInvoiceListFilter {
    pub status: Option<String>,
    pub month: Option<String>,
    pub plate: Option<String>,
    pub keyword: Option<String>,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Deserialize)]
pub struct EtcBatchQuery {
    pub status: Option<String>,
    pub month: Option<String>,
    pub plate: Option<String>,
    pub keyword: Option<String>,
    pub page: Option<String>,
    pub page_size: Option<String>,
}

#[derive(Debug)]
pub struct EtcBatchFilter {
    pub status: Option<String>,
    pub month: Option<String>,
    pub plate: Option<String>,
    pub keyword: Option<String>,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Debug, Deserialize)]
pub struct CostReadModelQuery {
    pub month: Option<String>,
    pub project_scope: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct CostProjectStatisticsQuery {
    pub month: Option<String>,
    pub project_scope: Option<String>,
    #[serde(skip)]
    pub project_name: String,
}

#[derive(Debug, Deserialize)]
pub struct CostExportPreviewQuery {
    pub month: Option<String>,
    pub view: Option<String>,
    pub project_scope: Option<String>,
    #[serde(default)]
    pub project_name: Vec<String>,
    #[serde(default)]
    pub expense_type: Vec<String>,
    pub start_month: Option<String>,
    pub end_month: Option<String>,
    pub start_date: Option<String>,
    pub end_date: Option<String>,
    pub aggregate_by: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct CostTransactionDetailQuery {
    pub project_scope: Option<String>,
    #[serde(skip)]
    pub transaction_id: String,
}

#[derive(Debug, Serialize)]
pub struct BankDetailAccountsResponse {
    pub accounts: Vec<BankDetailAccountDto>,
    pub total_balance: Option<String>,
    pub balance_account_count: i64,
    pub missing_balance_account_count: i64,
}

#[derive(Debug, Serialize)]
pub struct TaxCertifiedImportsResponse {
    pub month: String,
    pub records: Vec<TaxCertifiedImportRow>,
}

#[derive(Debug, Serialize)]
pub struct EtcInvoiceListResponse {
    pub items: Vec<EtcInvoiceRow>,
    pub counts: BTreeMap<String, i64>,
    pub page: i64,
    #[serde(rename = "pageSize")]
    pub page_size: i64,
    pub total: i64,
}

#[derive(Debug, Serialize)]
pub struct EtcBatchListResponse {
    pub items: Vec<EtcBatchDto>,
    pub counts: BTreeMap<String, i64>,
    pub pagination: EtcBatchPagination,
    #[serde(rename = "selectedBatch")]
    pub selected_batch: Option<EtcBatchDetailResponse>,
    #[serde(rename = "plateSummary")]
    pub plate_summary: Vec<EtcPlateSummaryRow>,
    #[serde(rename = "invoiceItems")]
    pub invoice_items: Vec<EtcInvoiceRow>,
}

#[derive(Debug, Serialize)]
pub struct EtcBatchPagination {
    pub page: i64,
    pub page_size: i64,
    pub total: i64,
}

#[derive(Clone, Debug, Serialize)]
pub struct EtcBatchDto {
    pub id: String,
    pub batch_id: String,
    pub etc_batch_id: String,
    pub external_batch_id: String,
    pub status: String,
    pub source_type: String,
    pub invoice_count: i64,
    pub total_amount: String,
    pub tax_amount: String,
    pub issue_start_date: Option<String>,
    pub issue_end_date: Option<String>,
    pub passage_start_date: Option<String>,
    pub passage_end_date: Option<String>,
    pub plate_count: usize,
    pub plate_summary: Vec<EtcPlateSummaryRow>,
    pub linked_oa_row_id: Option<String>,
    pub linked_oa_case_id: Option<String>,
    pub linked_oa_applicant: String,
    pub linked_oa_apply_date: String,
    pub linked_oa_amount: String,
    pub amount_delta: Option<String>,
    pub note: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct EtcBatchDetailResponse {
    pub batch: EtcBatchDto,
    pub summary: EtcBatchDto,
    #[serde(rename = "plateSummary")]
    pub plate_summary: Vec<EtcPlateSummaryRow>,
    #[serde(rename = "invoiceItems")]
    pub invoice_items: Vec<EtcInvoiceRow>,
    #[serde(rename = "supplementItems")]
    pub supplement_items: Vec<Value>,
}

impl EtcInvoiceListResponse {
    fn from_rows(page: i64, page_size: i64, rows: EtcInvoiceRows) -> Self {
        let mut counts = BTreeMap::new();
        counts.insert("unsubmitted".to_owned(), rows.unsubmitted_count);
        counts.insert("submitted".to_owned(), rows.submitted_count);
        counts.insert("current".to_owned(), rows.total);
        Self {
            items: rows.rows,
            counts,
            page,
            page_size,
            total: rows.total,
        }
    }
}

impl EtcBatchListResponse {
    fn from_rows(
        page: i64,
        page_size: i64,
        rows: EtcBatchRows,
        selected_detail: Option<EtcBatchDetailRows>,
    ) -> Self {
        let mut counts = BTreeMap::new();
        counts.insert("unsubmitted".to_owned(), rows.unsubmitted_count);
        counts.insert("submitted".to_owned(), rows.submitted_count);
        counts.insert("current".to_owned(), rows.total);
        let fallback_selected = rows
            .rows
            .first()
            .cloned()
            .map(EtcBatchDetailResponse::from_summary);
        let selected_batch = selected_detail.map(Into::into).or(fallback_selected);
        let plate_summary = selected_batch
            .as_ref()
            .map(|detail| detail.plate_summary.clone())
            .unwrap_or_default();
        let invoice_items = selected_batch
            .as_ref()
            .map(|detail| detail.invoice_items.clone())
            .unwrap_or_default();
        Self {
            items: rows.rows.into_iter().map(Into::into).collect(),
            counts,
            pagination: EtcBatchPagination {
                page,
                page_size,
                total: rows.total,
            },
            selected_batch,
            plate_summary,
            invoice_items,
        }
    }
}

impl EtcBatchDetailResponse {
    fn from_summary(summary: EtcBatchRow) -> Self {
        let summary: EtcBatchDto = summary.into();
        Self {
            batch: summary.clone(),
            plate_summary: summary.plate_summary.clone(),
            summary,
            invoice_items: Vec::new(),
            supplement_items: Vec::new(),
        }
    }
}

impl From<EtcBatchDetailRows> for EtcBatchDetailResponse {
    fn from(rows: EtcBatchDetailRows) -> Self {
        let summary: EtcBatchDto = rows.summary.into();
        Self {
            batch: summary.clone(),
            plate_summary: summary.plate_summary.clone(),
            summary,
            invoice_items: rows.invoices,
            supplement_items: Vec::new(),
        }
    }
}

impl From<EtcBatchRow> for EtcBatchDto {
    fn from(row: EtcBatchRow) -> Self {
        let plate_count = row.plate_summary.len();
        Self {
            batch_id: row.id.clone(),
            external_batch_id: row.etc_batch_id.clone(),
            linked_oa_applicant: String::new(),
            linked_oa_apply_date: String::new(),
            linked_oa_amount: String::new(),
            plate_count,
            id: row.id,
            etc_batch_id: row.etc_batch_id,
            status: row.status,
            source_type: row.source_type,
            invoice_count: row.invoice_count,
            total_amount: row.total_amount,
            tax_amount: row.tax_amount,
            issue_start_date: row.issue_start_date,
            issue_end_date: row.issue_end_date,
            passage_start_date: row.passage_start_date,
            passage_end_date: row.passage_end_date,
            plate_summary: row.plate_summary,
            linked_oa_row_id: row.linked_oa_row_id,
            linked_oa_case_id: row.linked_oa_case_id,
            amount_delta: row.amount_delta,
            note: row.note,
            created_at: row.created_at,
        }
    }
}

impl BankDetailAccountsResponse {
    fn from_rows(rows: Vec<BankDetailAccountRow>) -> Self {
        let mut total_balance = "0.00".to_owned();
        let mut balance_account_count = 0;
        let mut missing_balance_account_count = 0;
        let mut accounts = Vec::with_capacity(rows.len());
        for row in rows {
            if let Some(balance) = &row.latest_balance {
                balance_account_count += 1;
                total_balance = add_money_strings(&total_balance, balance);
            } else {
                missing_balance_account_count += 1;
            }
            accounts.push(row.into());
        }
        Self {
            accounts,
            total_balance: if balance_account_count > 0 {
                Some(total_balance)
            } else {
                None
            },
            balance_account_count,
            missing_balance_account_count,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct BankDetailAccountDto {
    pub account_key: String,
    pub bank_name: String,
    pub account_last4: String,
    pub display_name: String,
    pub latest_balance: Option<String>,
    pub latest_balance_at: Option<String>,
    pub has_balance: bool,
    pub transaction_count: i64,
}

impl From<BankDetailAccountRow> for BankDetailAccountDto {
    fn from(row: BankDetailAccountRow) -> Self {
        let display_name = format!("{} {}", row.bank_name, row.account_last4);
        let has_balance = row.latest_balance.is_some();
        Self {
            account_key: row.account_key,
            bank_name: row.bank_name,
            account_last4: row.account_last4,
            display_name,
            latest_balance: row.latest_balance,
            latest_balance_at: row.latest_balance_at,
            has_balance,
            transaction_count: row.transaction_count,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct BankDetailTransactionsResponse {
    pub account_key: Option<String>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
    pub rows: Vec<BankDetailTransactionDto>,
    pub category_counts: BTreeMap<String, i64>,
    pub pagination: BankDetailPaginationDto,
}

impl BankDetailTransactionsResponse {
    fn from_rows(
        account_key: Option<String>,
        date_from: Option<String>,
        date_to: Option<String>,
        page: i64,
        page_size: i64,
        result: BankDetailTransactionRows,
    ) -> Self {
        let category_counts = category_counts_from_rows(result.category_counts);
        Self {
            account_key,
            date_from,
            date_to,
            rows: result.rows.into_iter().map(Into::into).collect(),
            category_counts,
            pagination: BankDetailPaginationDto {
                page,
                page_size,
                total: result.total,
            },
        }
    }
}

#[derive(Debug, Serialize)]
pub struct BankDetailTransactionDto {
    pub id: String,
    pub trade_time: String,
    pub counterparty_name: String,
    pub direction: String,
    pub direction_label: String,
    pub amount: String,
    pub balance: Option<String>,
    pub summary: String,
    pub purpose: String,
    pub bank_name: String,
    pub account_last4: String,
    pub manual_category_code: Option<String>,
    pub manual_category_label: Option<String>,
    pub manual_category_path: Vec<String>,
    pub manual_category_source: String,
    pub manual_category_version: i64,
    pub auto_category_code: Option<String>,
    pub auto_category_label: Option<String>,
    pub auto_category_path: Vec<String>,
    pub auto_category_source: String,
    pub auto_category_reason: String,
    pub auto_category_confidence: String,
    pub auto_category_version: i64,
    pub effective_category_code: Option<String>,
    pub effective_category_label: Option<String>,
    pub effective_category_path: Vec<String>,
    pub effective_category_source: String,
    pub effective_category_version: i64,
    pub category_code: Option<String>,
    pub category_label: Option<String>,
    pub category_path: Vec<String>,
    pub category_source: String,
    pub category_version: i64,
    pub oa_relation_tag: String,
    pub invoice_relation_tag: String,
    pub relation_tags: Vec<String>,
    pub relation_case_id: Option<String>,
}

impl From<BankDetailTransactionRow> for BankDetailTransactionDto {
    fn from(row: BankDetailTransactionRow) -> Self {
        let direction = if row.direction == "inflow" {
            "income"
        } else {
            "expense"
        }
        .to_owned();
        let direction_label = if row.direction == "inflow" {
            "收"
        } else {
            "支"
        }
        .to_owned();
        let manual_category = row
            .manual_category_code
            .as_deref()
            .map(|code| category_descriptor(code, &row.category_raw_payload));
        let manual_category_label = manual_category
            .as_ref()
            .map(|category| category.label.clone());
        let manual_category_path = manual_category
            .as_ref()
            .map(|category| category.path.clone())
            .unwrap_or_default();
        let manual_category_source = row
            .manual_category_code
            .as_ref()
            .map(|_| {
                row.manual_category_source
                    .unwrap_or_else(|| "manual".to_owned())
            })
            .unwrap_or_default();
        let manual_category_version = if row.manual_category_code.is_some() {
            row.manual_category_version.unwrap_or(1)
        } else {
            0
        };
        let effective_category_code = row.manual_category_code.clone();
        let effective_category_label = manual_category_label.clone();
        let effective_category_path = manual_category_path.clone();
        let effective_category_source = manual_category_source.clone();
        let effective_category_version = manual_category_version;
        Self {
            id: row.id,
            trade_time: row.trade_time,
            counterparty_name: row.counterparty_name,
            direction,
            direction_label,
            amount: row.amount,
            balance: row.balance,
            summary: row.summary.unwrap_or_default(),
            purpose: row
                .remark
                .or_else(|| json_string(&row.raw_payload, "purpose"))
                .unwrap_or_default(),
            bank_name: row.bank_name,
            account_last4: row.account_last4,
            manual_category_code: row.manual_category_code.clone(),
            manual_category_label,
            manual_category_path,
            manual_category_source,
            manual_category_version,
            auto_category_code: None,
            auto_category_label: None,
            auto_category_path: Vec::new(),
            auto_category_source: String::new(),
            auto_category_reason: String::new(),
            auto_category_confidence: String::new(),
            auto_category_version: 0,
            effective_category_code: effective_category_code.clone(),
            effective_category_label: effective_category_label.clone(),
            effective_category_path: effective_category_path.clone(),
            effective_category_source: effective_category_source.clone(),
            effective_category_version,
            category_code: effective_category_code,
            category_label: effective_category_label,
            category_path: effective_category_path,
            category_source: effective_category_source,
            category_version: effective_category_version,
            oa_relation_tag: "无oa".to_owned(),
            invoice_relation_tag: "无发票".to_owned(),
            relation_tags: vec!["无oa".to_owned(), "无发票".to_owned()],
            relation_case_id: None,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct BankDetailPaginationDto {
    pub page: i64,
    pub page_size: i64,
    pub total: i64,
}

#[derive(Debug, Serialize)]
pub struct NoOaBatchListResponse {
    pub summary: NoOaBatchSummary,
    pub batches: Vec<NoOaBatchDto>,
}

impl NoOaBatchListResponse {
    fn from_rows(rows: Vec<NoOaBatchRow>) -> Self {
        let mut summary = NoOaBatchSummary::default();
        let mut batches = Vec::with_capacity(rows.len());
        for row in rows {
            summary.include(&row);
            batches.push(row.into());
        }
        Self { summary, batches }
    }
}

#[derive(Debug, Default, Serialize)]
pub struct NoOaBatchSummary {
    pub draft_count: i64,
    pub submitted_count: i64,
    pub withdrawn_count: i64,
    pub conflict_count: i64,
    pub stale_count: i64,
    pub total_amount: String,
    pub categories: Vec<Value>,
}

impl NoOaBatchSummary {
    fn include(&mut self, row: &NoOaBatchRow) {
        match status_bucket(&row.status) {
            "draft" => self.draft_count += 1,
            "submitted" => self.submitted_count += 1,
            "withdrawn" => self.withdrawn_count += 1,
            "conflict" => self.conflict_count += 1,
            "stale" => self.stale_count += 1,
            _ => {}
        }
        self.total_amount = add_money_strings(&self.total_amount, &row.total_amount);
    }
}

#[derive(Debug, Serialize)]
pub struct NoOaBatchDetailResponse {
    pub batch: NoOaBatchDto,
    pub rows: Vec<NoOaDetailRowDto>,
    pub tag_counts: Value,
    pub direction_counts: Value,
}

#[derive(Debug, Serialize)]
pub struct NoOaBatchDto {
    pub batch_id: String,
    pub batch_type: String,
    pub batch_label: String,
    pub scope_month: String,
    pub account_key: String,
    pub bank_name: String,
    pub account_last4: String,
    pub status: String,
    pub status_bucket: String,
    pub row_count: i64,
    pub total_amount: String,
    pub submitted_by: String,
    pub submitted_at: Option<String>,
    pub withdrawn_by: String,
    pub withdrawn_at: Option<String>,
    pub conflict_reason: String,
    pub blocked_reason: String,
    pub tag_counts: Value,
    pub direction_counts: Value,
    pub can_submit: bool,
    pub can_withdraw: bool,
    pub version: i64,
}

impl From<NoOaBatchRow> for NoOaBatchDto {
    fn from(row: NoOaBatchRow) -> Self {
        let raw = row.raw_payload;
        let batch_type =
            json_string(&raw, "batch_type").unwrap_or_else(|| "no_oa_bank_batch".to_owned());
        Self {
            batch_id: row.batch_id,
            batch_type,
            batch_label: json_string(&raw, "batch_label").unwrap_or_else(|| "免OA流水".to_owned()),
            scope_month: row.scope_month,
            account_key: json_string(&raw, "account_key").unwrap_or_default(),
            bank_name: json_string(&raw, "bank_name").unwrap_or_default(),
            account_last4: json_string(&raw, "account_last4").unwrap_or_default(),
            status_bucket: status_bucket(&row.status).to_owned(),
            can_submit: row.status == "draft",
            can_withdraw: row.status == "submitted" || row.status == "confirmed",
            submitted_by: json_string(&raw, "submitted_by").unwrap_or_default(),
            submitted_at: row.submitted_at,
            withdrawn_by: json_string(&raw, "withdrawn_by").unwrap_or_default(),
            withdrawn_at: row.cancelled_at,
            conflict_reason: json_string(&raw, "conflict_reason").unwrap_or_default(),
            blocked_reason: json_string(&raw, "blocked_reason").unwrap_or_default(),
            tag_counts: row.tag_counts,
            direction_counts: row.direction_counts,
            status: row.status,
            row_count: row.row_count,
            total_amount: row.total_amount,
            version: row.row_version,
        }
    }
}

#[derive(Debug, Serialize)]
pub struct NoOaDetailRowDto {
    pub transaction_id: String,
    pub trade_time: String,
    pub counterparty_name: String,
    pub direction: String,
    pub direction_label: String,
    pub amount: String,
    pub summary: String,
    pub purpose: String,
    pub remark: String,
    pub category_code: String,
    pub category_label: String,
    pub category_source: String,
}

impl From<NoOaDetailRow> for NoOaDetailRowDto {
    fn from(row: NoOaDetailRow) -> Self {
        let direction_label = if row.direction == "inflow" {
            "收入"
        } else {
            "支出"
        }
        .to_owned();
        Self {
            transaction_id: row.transaction_id,
            trade_time: row.trade_time.unwrap_or_else(|| row.txn_date.clone()),
            counterparty_name: row.counterparty_name,
            direction: row.direction,
            direction_label,
            amount: row.amount,
            summary: row.summary.unwrap_or_default(),
            purpose: json_string(&row.raw_payload, "purpose").unwrap_or_default(),
            remark: row.remark.unwrap_or_default(),
            category_code: row.category_code.unwrap_or_default(),
            category_label: row.category_label.unwrap_or_default(),
            category_source: row.category_source.unwrap_or_default(),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct OaSyncStatusResponse {
    pub status: String,
    pub last_run_id: Option<String>,
    pub last_started_at: Option<String>,
    pub last_finished_at: Option<String>,
    pub last_synced_at: Option<String>,
    pub source_system: Option<String>,
    pub scope: Option<String>,
    pub processed_count: i64,
    pub success_count: i64,
    pub failed_count: i64,
    pub error_message: Option<String>,
    pub source: &'static str,
}

impl From<OaSyncStatusRow> for OaSyncStatusResponse {
    fn from(row: OaSyncStatusRow) -> Self {
        Self {
            status: row.status.unwrap_or_else(|| "not_started".to_owned()),
            last_run_id: row.last_run_id,
            last_started_at: row.last_started_at,
            last_finished_at: row.last_finished_at,
            last_synced_at: row.last_synced_at,
            source_system: row.source_system,
            scope: row.scope,
            processed_count: row.processed_count.unwrap_or(0),
            success_count: row.success_count.unwrap_or(0),
            failed_count: row.failed_count.unwrap_or(0),
            error_message: row.error_message,
            source: "postgresql.app.oa_sync_runs",
        }
    }
}

fn read_model_payload(
    row: ReadModelPayloadRow,
    mut extra_status: Value,
) -> Result<Value, BusinessReadServiceError> {
    let mut payload = object_payload(row.payload, "read model payload must be an object")?;
    let mut status = json!({
        "scope_key": row.scope_key,
        "scope_type": row.scope_type,
        "scope_month": row.scope_month,
        "schema_version": row.schema_version,
        "cache_status": row.cache_status,
        "stale": row.stale,
        "stale_reason": row.stale_reason,
        "source_scope_keys": row.source_scope_keys,
        "source_versions": row.source_versions,
        "generated_at": row.generated_at,
        "updated_at": row.updated_at,
        "rebuild_task_id": row.rebuild_task_id
    });
    merge_object(&mut status, &mut extra_status);
    payload.insert("read_model_status".to_owned(), status);
    Ok(Value::Object(payload))
}

fn object_payload(
    value: Value,
    message: &'static str,
) -> Result<Map<String, Value>, BusinessReadServiceError> {
    match value {
        Value::Object(map) => Ok(map),
        _ => Err(invalid_request("invalid_read_model_payload", message)),
    }
}

fn merge_object(target: &mut Value, source: &mut Value) {
    if let (Value::Object(target), Value::Object(source)) = (target, source) {
        for (key, value) in source {
            target.insert(key.to_owned(), value.take());
        }
    }
}

fn required_month(value: Option<&str>) -> Result<String, BusinessReadServiceError> {
    let value = value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            invalid_request("invalid_month", "month is required and must use YYYY-MM")
        })?;
    if is_yyyy_mm(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid_request("invalid_month", "month must use YYYY-MM"))
    }
}

fn required_tax_certified_import_month(
    value: Option<&str>,
) -> Result<String, BusinessReadServiceError> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Err(invalid_request(
            "invalid_tax_certified_import_request",
            "month is required.",
        ));
    };
    if is_yyyy_mm(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid_request(
            "invalid_tax_certified_import_request",
            "month must use YYYY-MM.",
        ))
    }
}

fn required_tax_offset_calculate_month(
    value: Option<&str>,
) -> Result<String, BusinessReadServiceError> {
    let Some(value) = value.map(str::trim).filter(|value| !value.is_empty()) else {
        return Err(invalid_request(
            "invalid_tax_offset_calculate_request",
            "month is required and must use YYYY-MM.",
        ));
    };
    if is_yyyy_mm(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid_request(
            "invalid_tax_offset_calculate_request",
            "month must use YYYY-MM.",
        ))
    }
}

fn required_month_or_all(value: Option<&str>) -> Result<String, BusinessReadServiceError> {
    let value = value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .ok_or_else(|| {
            invalid_request(
                "invalid_month",
                "month is required and must be all or YYYY-MM",
            )
        })?;
    if value == "all" || is_yyyy_mm(value) {
        Ok(value.to_owned())
    } else {
        Err(invalid_request(
            "invalid_month",
            "month must be all or YYYY-MM",
        ))
    }
}

fn optional_month(value: Option<&str>) -> Result<Option<String>, BusinessReadServiceError> {
    match value.map(str::trim).filter(|value| !value.is_empty()) {
        Some(value) if is_yyyy_mm(value) => Ok(Some(value.to_owned())),
        Some(_) => Err(invalid_request("invalid_month", "month must use YYYY-MM")),
        None => Ok(None),
    }
}

fn optional_date(value: Option<&str>) -> Result<Option<String>, BusinessReadServiceError> {
    match value.map(str::trim).filter(|value| !value.is_empty()) {
        Some(value) if is_yyyy_mm_dd(value) => Ok(Some(value.to_owned())),
        Some(_) => Err(invalid_request("invalid_date", "date must use YYYY-MM-DD")),
        None => Ok(None),
    }
}

fn positive_page(value: Option<i64>) -> Result<i64, BusinessReadServiceError> {
    match value.unwrap_or(1) {
        page if page > 0 => Ok(page),
        _ => Err(invalid_request(
            "invalid_pagination",
            "page must be positive",
        )),
    }
}

fn capped_page_size(value: Option<i64>) -> Result<i64, BusinessReadServiceError> {
    match value.unwrap_or(100) {
        size if size > 0 => Ok(size.min(500)),
        _ => Err(invalid_request(
            "invalid_pagination",
            "page_size must be positive",
        )),
    }
}

fn etc_page(value: Option<&str>) -> Result<i64, BusinessReadServiceError> {
    match clean_optional_str(value) {
        Some(raw) => raw.parse::<i64>().map(|page| page.max(1)).map_err(|_| {
            invalid_request(
                "invalid_etc_invoice_request",
                "page and page_size must be integers.",
            )
        }),
        None => Ok(1),
    }
}

fn etc_page_size(value: Option<&str>) -> Result<i64, BusinessReadServiceError> {
    match clean_optional_str(value) {
        Some(raw) => raw
            .parse::<i64>()
            .map(|page_size| page_size.clamp(1, 500))
            .map_err(|_| {
                invalid_request(
                    "invalid_etc_invoice_request",
                    "page and page_size must be integers.",
                )
            }),
        None => Ok(50),
    }
}

fn etc_batch_page(value: Option<&str>) -> Result<i64, BusinessReadServiceError> {
    match clean_optional_str(value) {
        Some(raw) => raw.parse::<i64>().map(|page| page.max(1)).map_err(|_| {
            invalid_request(
                "invalid_etc_batch_request",
                "page and page_size must be integers.",
            )
        }),
        None => Ok(1),
    }
}

fn etc_batch_page_size(value: Option<&str>) -> Result<i64, BusinessReadServiceError> {
    match clean_optional_str(value) {
        Some(raw) => raw
            .parse::<i64>()
            .map(|page_size| page_size.clamp(1, 500))
            .map_err(|_| {
                invalid_request(
                    "invalid_etc_batch_request",
                    "page and page_size must be integers.",
                )
            }),
        None => Ok(50),
    }
}

fn valid_etc_invoice_status(value: String) -> Result<String, BusinessReadServiceError> {
    match value.as_str() {
        "unsubmitted" | "submitted" => Ok(value),
        _ => Err(invalid_request(
            "invalid_etc_invoice_request",
            "status must be unsubmitted or submitted.",
        )),
    }
}

fn is_yyyy_mm(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7
        && bytes[4] == b'-'
        && bytes[0..4].iter().all(u8::is_ascii_digit)
        && bytes[5..7].iter().all(u8::is_ascii_digit)
        && matches!(
            &bytes[5..7],
            b"01"
                | b"02"
                | b"03"
                | b"04"
                | b"05"
                | b"06"
                | b"07"
                | b"08"
                | b"09"
                | b"10"
                | b"11"
                | b"12"
        )
}

fn is_yyyy_mm_dd(value: &str) -> bool {
    let bytes = value.as_bytes();
    if bytes.len() != 10
        || bytes[4] != b'-'
        || bytes[7] != b'-'
        || !bytes[0..4].iter().all(u8::is_ascii_digit)
        || !bytes[5..7].iter().all(u8::is_ascii_digit)
        || !bytes[8..10].iter().all(u8::is_ascii_digit)
    {
        return false;
    }
    let month = parse_two_digits(&bytes[5..7]);
    let day = parse_two_digits(&bytes[8..10]);
    matches!(month, 1..=12) && matches!(day, 1..=31)
}

fn parse_two_digits(bytes: &[u8]) -> u8 {
    (bytes[0] - b'0') * 10 + (bytes[1] - b'0')
}

fn clean_optional(value: Option<String>) -> Option<String> {
    value
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty() && value != "all")
}

fn clean_optional_str(value: Option<&str>) -> Option<&str> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty() && *value != "all")
}

fn cost_project_scope(value: Option<String>) -> Result<String, BusinessReadServiceError> {
    match value.map(|value| value.trim().to_ascii_lowercase()) {
        Some(value) if value == "active" || value == "all" => Ok(value),
        Some(_) => Err(invalid_request(
            "invalid_cost_statistics_project_scope",
            "project_scope must be active or all",
        )),
        None => Ok("active".to_owned()),
    }
}

fn cost_export_preview_view(value: Option<&str>) -> Result<&'static str, BusinessReadServiceError> {
    match value.map(str::trim) {
        Some("time") => Ok("time"),
        Some("project") => Ok("project"),
        Some("expense_type") => Ok("expense_type"),
        _ => Err(invalid_request(
            "invalid_cost_statistics_export_preview_request",
            "view must be time, project, or expense_type.",
        )),
    }
}

fn cost_project_aggregate_by(value: Option<&str>) -> Option<&'static str> {
    match value.map(str::trim) {
        Some("month") => Some("month"),
        Some("year") => Some("year"),
        _ => None,
    }
}

fn clean_vec(values: Vec<String>) -> Vec<String> {
    let mut values = values
        .into_iter()
        .map(|value| value.trim().to_owned())
        .filter(|value| !value.is_empty())
        .collect::<Vec<_>>();
    values.sort();
    values.dedup();
    values
}

fn invalid_request(code: &'static str, message: &'static str) -> BusinessReadServiceError {
    BusinessReadServiceError::InvalidRequest { code, message }
}

fn status_bucket(status: &str) -> &'static str {
    match status {
        "draft" => "draft",
        "submitted" | "confirmed" => "submitted",
        "cancelled" => "withdrawn",
        _ => "stale",
    }
}

fn json_string(value: &Value, key: &str) -> Option<String> {
    value.get(key).and_then(Value::as_str).map(str::to_owned)
}

fn category_counts_from_rows(rows: Vec<(String, i64)>) -> BTreeMap<String, i64> {
    let mut counts = BTreeMap::new();
    for code in category_count_keys() {
        counts.insert((*code).to_owned(), 0);
    }
    for (code, count) in rows {
        if counts.contains_key(&code) {
            counts.insert(code, count);
        } else {
            *counts.entry("uncategorized".to_owned()).or_insert(0) += count;
        }
    }
    counts
}

fn category_count_keys() -> &'static [&'static str] {
    &[
        "borrow_in_personal_pending_repayment",
        "borrow_in_personal_repaid",
        "borrow_in_company_pending_repayment",
        "borrow_in_company_repaid",
        "borrow_in_bank_pending_repayment",
        "borrow_in_bank_repaid",
        "borrow_out_personal_lent",
        "borrow_out_personal_pending_collection",
        "borrow_out_company_lent",
        "borrow_out_company_pending_collection",
        "borrow_out_goods_lent",
        "borrow_out_goods_pending_collection",
        "business_warranty_pending_collection",
        "business_bid_bond_pending_collection",
        "business_performance_bond_pending_collection",
        "business_invoiced_pending_collection",
        "fee",
        "salary",
        "holiday_bonus",
        "bonus",
        "external_turnover",
        "internal_transfer",
        "offset",
        "cash_turnover",
        "uncategorized",
    ]
}

#[derive(Debug)]
struct CategoryDescriptor {
    label: String,
    path: Vec<String>,
}

fn category_descriptor(code: &str, raw_payload: &Value) -> CategoryDescriptor {
    let label = json_string(raw_payload, "category_label")
        .or_else(|| json_string(raw_payload, "label"))
        .or_else(|| category_taxonomy(code).map(|(label, _)| label.to_owned()))
        .unwrap_or_else(|| code.to_owned());
    let path = raw_payload
        .get("category_path")
        .or_else(|| raw_payload.get("path"))
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect::<Vec<_>>()
        })
        .filter(|items| !items.is_empty())
        .or_else(|| {
            category_taxonomy(code)
                .map(|(_, path)| path.iter().map(|item| (*item).to_owned()).collect())
        })
        .unwrap_or_default();
    CategoryDescriptor { label, path }
}

fn category_taxonomy(code: &str) -> Option<(&'static str, &'static [&'static str])> {
    match code {
        "borrow_in_personal_pending_repayment" => {
            Some(("个人暂借款：待还款", &["借入", "个人往来款", "待还款"]))
        }
        "borrow_in_personal_repaid" => {
            Some(("个人暂借款：已还款", &["借入", "个人往来款", "已还款"]))
        }
        "borrow_in_company_pending_repayment" => {
            Some(("公司暂借款：待还款", &["借入", "公司往来款", "待还款"]))
        }
        "borrow_in_company_repaid" => {
            Some(("公司暂借款：已还款", &["借入", "公司往来款", "已还款"]))
        }
        "borrow_in_bank_pending_repayment" => {
            Some(("银行往来款：待还款", &["借入", "银行往来款", "待还款"]))
        }
        "borrow_in_bank_repaid" => Some(("银行往来款：已还款", &["借入", "银行往来款", "已还款"])),
        "borrow_out_personal_lent" => {
            Some(("个人往来款：已借款", &["借出", "个人往来款", "已借款"]))
        }
        "borrow_out_personal_pending_collection" => {
            Some(("个人往来款：待收款", &["借出", "个人往来款", "待收款"]))
        }
        "borrow_out_company_lent" => {
            Some(("公司往来款：已借款", &["借出", "公司往来款", "已借款"]))
        }
        "borrow_out_company_pending_collection" => {
            Some(("公司往来款：待收款", &["借出", "公司往来款", "待收款"]))
        }
        "borrow_out_goods_lent" => Some(("货款往来款：已借款", &["借出", "货款往来款", "已借款"])),
        "borrow_out_goods_pending_collection" => {
            Some(("货款往来款：待收款", &["借出", "货款往来款", "待收款"]))
        }
        "business_warranty_pending_collection" => {
            Some(("质保金：待收款", &["业务往来", "质保金", "待收款"]))
        }
        "business_bid_bond_pending_collection" => {
            Some(("投标保证金：待收款", &["业务往来", "投标保证金", "待收款"]))
        }
        "business_performance_bond_pending_collection" => {
            Some(("履约保证金：待收款", &["业务往来", "履约保证金", "待收款"]))
        }
        "business_invoiced_pending_collection" => Some((
            "已开发票未收款：待收款",
            &["业务往来", "已开发票未收款", "待收款"],
        )),
        "fee" => Some(("手续费", &["自动识别", "手续费"])),
        "salary" => Some(("工资", &["自动识别", "工资"])),
        "holiday_bonus" => Some(("过节费", &["自动识别", "过节费"])),
        "bonus" => Some(("奖金", &["自动识别", "奖金"])),
        "external_turnover" => Some(("外部往来款", &[])),
        "internal_transfer" => Some(("内部往来款", &["自动识别", "内部往来款"])),
        "offset" => Some(("冲", &[])),
        "cash_turnover" => Some(("现金往来", &[])),
        "prepayment" => Some(("预付款", &["手工分类", "预付款"])),
        "advance_receipt" => Some(("预收款", &["手工分类", "预收款"])),
        "pending_refund" => Some(("待退款", &["手工分类", "待退款"])),
        "counterparty_confirmation" => Some(("待对方确认", &["手工分类", "待对方确认"])),
        "other" => Some(("其他", &["手工分类", "其他"])),
        _ => None,
    }
}

fn add_money_strings(left: &str, right: &str) -> String {
    let left = left.parse::<f64>().unwrap_or(0.0);
    let right = right.parse::<f64>().unwrap_or(0.0);
    format!("{:.2}", left + right)
}

fn cost_project_detail_payload(payload: &Value, month: &str, project_name: &str) -> Value {
    let mut rows = cost_time_rows(payload)
        .into_iter()
        .filter(|row| value_string(row, "project_name") == project_name)
        .map(|row| {
            json!({
                "transaction_id": value_string(row, "transaction_id"),
                "trade_time": value_string(row, "trade_time"),
                "direction": value_string_or(row, "direction", "支出"),
                "expense_type": value_string(row, "expense_type"),
                "expense_content": value_string(row, "expense_content"),
                "amount": value_money(row, "amount"),
                "counterparty_name": value_string(row, "counterparty_name"),
                "payment_account_label": value_string(row, "payment_account_label"),
            })
        })
        .collect::<Vec<_>>();
    rows.sort_by(|left, right| {
        (
            value_string(left, "trade_time"),
            value_string(left, "transaction_id"),
        )
            .cmp(&(
                value_string(right, "trade_time"),
                value_string(right, "transaction_id"),
            ))
    });
    let total_amount = rows.iter().fold("0.00".to_owned(), |total, row| {
        add_money_strings(&total, &value_money(row, "amount"))
    });
    json!({
        "month": month,
        "project_name": project_name,
        "summary": {
            "row_count": rows.len(),
            "transaction_count": rows.len(),
            "total_amount": total_amount,
        },
        "rows": rows,
    })
}

fn cost_export_preview_payload(
    payload: &Value,
    month: String,
    view: &str,
    query: CostExportPreviewQuery,
) -> Result<Value, BusinessReadServiceError> {
    let project_names = clean_vec(query.project_name);
    let expense_types = clean_vec(query.expense_type);
    let aggregate_by = cost_project_aggregate_by(query.aggregate_by.as_deref());
    let rows = cost_filtered_rows(
        payload,
        &month,
        DateFilter {
            start_month: query.start_month.as_deref(),
            end_month: query.end_month.as_deref(),
            start_date: query.start_date.as_deref(),
            end_date: query.end_date.as_deref(),
        },
        &project_names,
        &expense_types,
    );
    let scope_label = cost_scope_label(
        &month,
        query.start_month.as_deref(),
        query.end_month.as_deref(),
        query.start_date.as_deref(),
        query.end_date.as_deref(),
    );

    match view {
        "time" => Ok(cost_time_export_preview(&scope_label, rows)),
        "expense_type" => {
            if expense_types.is_empty() {
                return Err(BusinessReadServiceError::InvalidRequest {
                    code: "invalid_cost_statistics_export_preview_request",
                    message: "expense_type is required for expense_type export preview",
                });
            }
            Ok(cost_expense_type_export_preview(
                &scope_label,
                &expense_types,
                rows,
            ))
        }
        "project" => {
            if project_names.is_empty() {
                return Err(BusinessReadServiceError::InvalidRequest {
                    code: "invalid_cost_statistics_export_preview_request",
                    message: "project_name is required for project export preview",
                });
            }
            Ok(cost_project_export_preview(
                &scope_label,
                &project_names,
                aggregate_by.unwrap_or("month"),
                rows,
            ))
        }
        _ => unreachable!("validated cost export preview view"),
    }
}

struct DateFilter<'a> {
    start_month: Option<&'a str>,
    end_month: Option<&'a str>,
    start_date: Option<&'a str>,
    end_date: Option<&'a str>,
}

fn cost_filtered_rows<'a>(
    payload: &'a Value,
    month: &str,
    filter: DateFilter<'_>,
    project_names: &[String],
    expense_types: &[String],
) -> Vec<&'a Value> {
    let mut start_month = filter.start_month.map(str::to_owned);
    let mut end_month = filter.end_month.map(str::to_owned);
    if start_month.is_none() {
        start_month = filter
            .start_date
            .map(|value| value.chars().take(7).collect());
    }
    if end_month.is_none() {
        end_month = filter.end_date.map(|value| value.chars().take(7).collect());
    }
    if start_month
        .as_ref()
        .zip(end_month.as_ref())
        .is_some_and(|(start, end)| start > end)
    {
        std::mem::swap(&mut start_month, &mut end_month);
    }

    let mut start_date = filter.start_date.map(str::to_owned);
    let mut end_date = filter.end_date.map(str::to_owned);
    if start_date
        .as_ref()
        .zip(end_date.as_ref())
        .is_some_and(|(start, end)| start > end)
    {
        std::mem::swap(&mut start_date, &mut end_date);
    }

    let project_name_set = project_names.iter().collect::<BTreeSet<_>>();
    let expense_type_set = expense_types.iter().collect::<BTreeSet<_>>();
    let mut rows = cost_time_rows(payload)
        .into_iter()
        .filter(|row| {
            let trade_time = value_string(row, "trade_time");
            let trade_month = trade_time.chars().take(7).collect::<String>();
            let trade_date = trade_time.chars().take(10).collect::<String>();
            if month != "all" && trade_month != month {
                return false;
            }
            if start_month
                .as_ref()
                .is_some_and(|start| trade_month < *start)
            {
                return false;
            }
            if end_month.as_ref().is_some_and(|end| trade_month > *end) {
                return false;
            }
            if start_date.as_ref().is_some_and(|start| trade_date < *start) {
                return false;
            }
            if end_date.as_ref().is_some_and(|end| trade_date > *end) {
                return false;
            }
            if !project_name_set.is_empty()
                && !project_name_set.contains(&value_string(row, "project_name"))
            {
                return false;
            }
            if !expense_type_set.is_empty()
                && !expense_type_set.contains(&value_string(row, "expense_type"))
            {
                return false;
            }
            true
        })
        .collect::<Vec<_>>();
    rows.sort_by(|left, right| {
        (
            value_string(right, "trade_time"),
            value_string(right, "transaction_id"),
        )
            .cmp(&(
                value_string(left, "trade_time"),
                value_string(left, "transaction_id"),
            ))
    });
    rows
}

fn cost_time_export_preview(scope_label: &str, rows: Vec<&Value>) -> Value {
    let total_amount = rows.iter().fold("0.00".to_owned(), |total, row| {
        add_money_strings(&total, &value_money(row, "amount"))
    });
    let preview_rows = rows
        .iter()
        .map(|row| {
            json!([
                value_string(row, "trade_time"),
                value_string(row, "project_name"),
                value_string(row, "expense_type"),
                value_money(row, "amount"),
                value_string(row, "expense_content"),
                value_string_or(row, "direction", "支出"),
                value_string(row, "counterparty_name"),
                value_string(row, "payment_account_label"),
            ])
        })
        .collect::<Vec<_>>();
    cost_preview_payload(
        "time",
        &cost_export_filename(scope_label, "time", &[], None, None),
        scope_label,
        vec!["按时间统计"],
        vec![
            "时间",
            "项目名称",
            "费用类型",
            "金额",
            "费用内容",
            "资金方向",
            "对方户名",
            "支付账户",
        ],
        preview_rows,
        total_amount,
    )
}

fn cost_expense_type_export_preview(
    scope_label: &str,
    expense_types: &[String],
    rows: Vec<&Value>,
) -> Value {
    let total_amount = rows.iter().fold("0.00".to_owned(), |total, row| {
        add_money_strings(&total, &value_money(row, "amount"))
    });
    let preview_rows = rows
        .iter()
        .map(|row| {
            json!([
                value_string(row, "trade_time"),
                value_string(row, "project_name"),
                value_string_or(row, "direction", "支出"),
                value_money(row, "amount"),
                value_string(row, "expense_content"),
                value_string(row, "counterparty_name"),
                value_string(row, "payment_account_label"),
            ])
        })
        .collect::<Vec<_>>();
    cost_preview_payload(
        "expense_type",
        &cost_export_filename(
            scope_label,
            "expense_type",
            &[],
            None,
            Some(cost_expense_type_label(expense_types)),
        ),
        scope_label,
        vec!["按费用类型统计"],
        vec![
            "时间",
            "项目名称",
            "资金方向",
            "金额",
            "费用内容",
            "对方户名",
            "支付账户",
        ],
        preview_rows,
        total_amount,
    )
}

fn cost_project_export_preview(
    scope_label: &str,
    project_names: &[String],
    aggregate_by: &str,
    rows: Vec<&Value>,
) -> Value {
    let mut buckets: BTreeMap<(String, String, String, String), (f64, i64)> = BTreeMap::new();
    for row in rows {
        let trade_time = value_string(row, "trade_time");
        let period_label = if aggregate_by == "year" {
            trade_time.chars().take(4).collect::<String>()
        } else {
            trade_time.chars().take(7).collect::<String>()
        };
        let period_label = if period_label.is_empty() {
            "—".to_owned()
        } else {
            period_label
        };
        let key = (
            period_label,
            value_string(row, "project_name"),
            value_string(row, "expense_type"),
            value_string(row, "expense_content"),
        );
        let bucket = buckets.entry(key).or_insert((0.0, 0));
        bucket.0 += value_money_f64(row, "amount");
        bucket.1 += 1;
    }
    let mut total_amount = "0.00".to_owned();
    let preview_rows = buckets
        .into_iter()
        .map(
            |((period_label, project_name, expense_type, expense_content), (amount, count))| {
                let amount = format_money_f64(amount);
                total_amount = add_money_strings(&total_amount, &amount);
                json!([
                    period_label,
                    project_name,
                    expense_type,
                    amount,
                    expense_content,
                    count.to_string(),
                ])
            },
        )
        .collect::<Vec<_>>();
    cost_preview_payload(
        "project",
        &cost_export_filename(
            scope_label,
            "project",
            project_names,
            Some(aggregate_by),
            None,
        ),
        scope_label,
        vec!["按项目统计"],
        vec![
            "统计周期",
            "项目名称",
            "费用类型",
            "金额",
            "费用内容",
            "支出笔数",
        ],
        preview_rows,
        total_amount,
    )
}

fn cost_preview_payload(
    view: &str,
    file_name: &str,
    scope_label: &str,
    sheet_names: Vec<&str>,
    columns: Vec<&str>,
    rows: Vec<Value>,
    total_amount: String,
) -> Value {
    json!({
        "view": view,
        "file_name": file_name,
        "scope_label": scope_label,
        "sheet_names": sheet_names,
        "columns": columns,
        "rows": rows,
        "summary": {
            "row_count": rows.len(),
            "transaction_count": rows.len(),
            "total_amount": total_amount,
            "sheet_count": sheet_names.len(),
        },
    })
}

fn cost_scope_label(
    month: &str,
    start_month: Option<&str>,
    end_month: Option<&str>,
    start_date: Option<&str>,
    end_date: Option<&str>,
) -> String {
    if let (Some(start_date), Some(end_date)) = (start_date, end_date) {
        return format!("{start_date}至{end_date}");
    }
    if let (Some(start_month), Some(end_month)) = (start_month, end_month) {
        return format!("{start_month}至{end_month}");
    }
    if month == "all" {
        "全部期间".to_owned()
    } else {
        month.to_owned()
    }
}

fn cost_export_filename(
    scope_label: &str,
    view: &str,
    project_names: &[String],
    aggregate_by: Option<&str>,
    expense_type: Option<String>,
) -> String {
    let month_segment = if scope_label == "all" {
        "全部期间"
    } else {
        scope_label
    };
    match view {
        "time" => format!("成本统计_{month_segment}_按时间统计.xlsx"),
        "project" => {
            if let Some(aggregate_by) = aggregate_by {
                let aggregate_label = if aggregate_by == "year" { "年" } else { "月" };
                format!(
                    "成本统计_{month_segment}_按项目统计_按{aggregate_label}_{}.xlsx",
                    cost_project_export_label(project_names)
                )
            } else {
                format!(
                    "成本统计_{month_segment}_项目明细_{}.xlsx",
                    sanitize_filename_part(
                        project_names
                            .first()
                            .map(String::as_str)
                            .unwrap_or("未命名项目")
                    )
                )
            }
        }
        "expense_type" => format!(
            "成本统计_{month_segment}_按费用类型统计_{}.xlsx",
            sanitize_filename_part(expense_type.as_deref().unwrap_or("未命名费用类型"))
        ),
        _ => format!("成本统计_{month_segment}.xlsx"),
    }
}

fn cost_expense_type_label(expense_types: &[String]) -> String {
    if expense_types.is_empty() {
        return "未命名费用类型".to_owned();
    }
    let mut ordered = expense_types.to_vec();
    ordered.sort();
    ordered.dedup();
    if ordered.len() == 1 {
        ordered[0].clone()
    } else {
        format!("{}等{}类", ordered[0], ordered.len())
    }
}

fn cost_project_export_label(project_names: &[String]) -> String {
    if project_names.is_empty() {
        return "未命名项目".to_owned();
    }
    let mut ordered = project_names.to_vec();
    ordered.sort();
    ordered.dedup();
    if ordered.len() == 1 {
        sanitize_filename_part(&ordered[0])
    } else {
        format!(
            "{}等{}个项目",
            sanitize_filename_part(&ordered[0]),
            ordered.len()
        )
    }
}

fn sanitize_filename_part(value: &str) -> String {
    let sanitized = value
        .trim()
        .replace('/', "-")
        .replace('\\', "-")
        .replace(':', "：");
    sanitized.chars().take(80).collect()
}

fn tax_offset_calculate_payload(
    month: &str,
    payload: &Value,
    selected_input_ids: &[String],
) -> Value {
    let output_items = tax_item_rows(payload, "output_items");
    let input_plan_items = tax_item_rows(payload, "input_plan_items");
    let certified_items = tax_item_rows(payload, "certified_items");
    let locked_input_ids = payload
        .get("locked_certified_input_ids")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .map(str::to_owned)
                .collect::<std::collections::BTreeSet<_>>()
        })
        .unwrap_or_default();
    let selected_input_id_set = selected_input_ids
        .iter()
        .map(String::as_str)
        .collect::<std::collections::BTreeSet<_>>();

    let output_tax = output_items.iter().fold(0.0, |total, item| {
        total + value_money_f64(item, "tax_amount")
    });
    let certified_input_tax = certified_items
        .iter()
        .fold(0.0, |total, item| total + tax_certified_amount_f64(item));
    let planned_input_tax = input_plan_items.iter().fold(0.0, |total, item| {
        let id = value_string(item, "id");
        if selected_input_id_set.contains(id.as_str()) && !locked_input_ids.contains(&id) {
            total + value_money_f64(item, "tax_amount")
        } else {
            total
        }
    });
    let input_tax = certified_input_tax + planned_input_tax;
    let deductible_tax = output_tax.min(input_tax);
    let payable_tax = output_tax - deductible_tax;
    let carry_forward_tax = input_tax - deductible_tax;
    let result_label = if payable_tax > 0.0 {
        "本月应纳税额"
    } else {
        "本月留抵税额"
    };
    let result_amount = if payable_tax > 0.0 {
        payable_tax
    } else {
        carry_forward_tax
    };

    json!({
        "month": month,
        "selected_output_ids": output_items
            .iter()
            .map(|item| value_string(item, "id"))
            .collect::<Vec<_>>(),
        "selected_input_ids": selected_input_ids,
        "summary": {
            "output_tax": format_money_f64(output_tax),
            "certified_input_tax": format_money_f64(certified_input_tax),
            "planned_input_tax": format_money_f64(planned_input_tax),
            "input_tax": format_money_f64(input_tax),
            "deductible_tax": format_money_f64(deductible_tax),
            "result_label": result_label,
            "result_amount": format_money_f64(result_amount),
        }
    })
}

fn cost_transaction_detail_payload(
    month: &str,
    cost_row: &Value,
    transaction_id: &str,
    workbench_row: &Value,
) -> Value {
    json!({
        "month": month,
        "transaction": {
            "id": transaction_id,
            "project_name": value_string(cost_row, "project_name"),
            "expense_type": value_string(cost_row, "expense_type"),
            "expense_content": value_string(cost_row, "expense_content"),
            "trade_time": value_string(cost_row, "trade_time"),
            "direction": value_string_or(cost_row, "direction", "支出"),
            "amount": value_money(cost_row, "amount"),
            "counterparty_name": value_string(cost_row, "counterparty_name"),
            "payment_account_label": value_string(cost_row, "payment_account_label"),
            "remark": value_string(cost_row, "remark"),
            "oa_applicant": value_string(cost_row, "oa_applicant"),
            "summary_fields": object_or_empty(workbench_row.get("summary_fields")),
            "detail_fields": object_or_empty(workbench_row.get("detail_fields")),
        },
    })
}

fn cost_time_rows(payload: &Value) -> Vec<&Value> {
    payload
        .get("time_rows")
        .and_then(Value::as_array)
        .map(|rows| rows.iter().collect())
        .unwrap_or_default()
}

fn tax_item_rows<'a>(payload: &'a Value, key: &str) -> Vec<&'a Value> {
    payload
        .get(key)
        .and_then(Value::as_array)
        .map(|rows| rows.iter().collect())
        .unwrap_or_default()
}

fn value_string(value: &Value, key: &str) -> String {
    value_string_or(value, key, "")
}

fn value_string_or(value: &Value, key: &str, default: &str) -> String {
    value
        .get(key)
        .and_then(Value::as_str)
        .unwrap_or(default)
        .to_owned()
}

fn value_money(value: &Value, key: &str) -> String {
    match value.get(key) {
        Some(Value::String(raw)) => format!("{:.2}", raw.parse::<f64>().unwrap_or(0.0)),
        Some(Value::Number(raw)) => format!("{:.2}", raw.as_f64().unwrap_or(0.0)),
        _ => "0.00".to_owned(),
    }
}

fn value_money_f64(value: &Value, key: &str) -> f64 {
    match value.get(key) {
        Some(Value::String(raw)) => raw.replace(',', "").parse::<f64>().unwrap_or(0.0),
        Some(Value::Number(raw)) => raw.as_f64().unwrap_or(0.0),
        _ => 0.0,
    }
}

fn tax_certified_amount_f64(value: &Value) -> f64 {
    if value.get("deductible_tax_amount").is_some_and(|value| {
        !matches!(value, Value::Null) && value.as_str().is_none_or(|raw| !raw.trim().is_empty())
    }) {
        value_money_f64(value, "deductible_tax_amount")
    } else {
        value_money_f64(value, "tax_amount")
    }
}

fn format_money_f64(value: f64) -> String {
    format!("{value:.2}")
}

fn object_or_empty(value: Option<&Value>) -> Value {
    value
        .and_then(Value::as_object)
        .map(|object| Value::Object(object.clone()))
        .unwrap_or_else(|| Value::Object(Map::new()))
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;

    #[derive(Clone, Default)]
    struct StubBusinessReadRepository {
        tax_read_model: Option<ReadModelPayloadRow>,
        cost_read_model: Option<ReadModelPayloadRow>,
        transaction_month: Option<String>,
        workbench_row_payload: Option<Value>,
        tax_certified_imports: Vec<TaxCertifiedImportRow>,
        etc_invoice_rows: EtcInvoiceRows,
        etc_batch_rows: EtcBatchRows,
        etc_batch_detail: Option<EtcBatchDetailRows>,
    }

    #[async_trait]
    impl BusinessReadRepository for StubBusinessReadRepository {
        async fn list_bank_detail_accounts(
            &self,
            _filter: BankDetailDateFilter,
        ) -> Result<Vec<BankDetailAccountRow>, BusinessReadRepositoryError> {
            Ok(Vec::new())
        }

        async fn list_bank_detail_transactions(
            &self,
            _filter: BankDetailTransactionFilter,
        ) -> Result<BankDetailTransactionRows, BusinessReadRepositoryError> {
            Ok(BankDetailTransactionRows {
                rows: Vec::new(),
                category_counts: Vec::new(),
                total: 0,
            })
        }

        async fn list_no_oa_batches(
            &self,
            _filter: NoOaBatchListFilter,
        ) -> Result<Vec<NoOaBatchRow>, BusinessReadRepositoryError> {
            Ok(Vec::new())
        }

        async fn find_no_oa_batch(
            &self,
            _batch_id: Uuid,
        ) -> Result<Option<(NoOaBatchRow, Vec<NoOaDetailRow>)>, BusinessReadRepositoryError>
        {
            Ok(None)
        }

        async fn find_tax_offset_read_model(
            &self,
            _month: &str,
        ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError> {
            Ok(self.tax_read_model.clone())
        }

        async fn list_tax_certified_imports(
            &self,
            _month: &str,
        ) -> Result<Vec<TaxCertifiedImportRow>, BusinessReadRepositoryError> {
            Ok(self.tax_certified_imports.clone())
        }

        async fn list_etc_invoices(
            &self,
            _filter: EtcInvoiceListFilter,
        ) -> Result<EtcInvoiceRows, BusinessReadRepositoryError> {
            Ok(self.etc_invoice_rows.clone())
        }

        async fn list_etc_batches(
            &self,
            _filter: EtcBatchFilter,
        ) -> Result<EtcBatchRows, BusinessReadRepositoryError> {
            Ok(self.etc_batch_rows.clone())
        }

        async fn find_etc_batch(
            &self,
            _batch_id: &str,
        ) -> Result<Option<EtcBatchDetailRows>, BusinessReadRepositoryError> {
            Ok(self.etc_batch_detail.clone())
        }

        async fn find_cost_statistics_read_model(
            &self,
            _month: &str,
            _project_scope: &str,
        ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError> {
            Ok(self.cost_read_model.clone())
        }

        async fn find_cost_transaction_month(
            &self,
            _transaction_id: &str,
        ) -> Result<Option<String>, BusinessReadRepositoryError> {
            Ok(self.transaction_month.clone())
        }

        async fn find_workbench_row_payload(
            &self,
            _row_id: &str,
            _month: &str,
        ) -> Result<Option<Value>, BusinessReadRepositoryError> {
            Ok(self.workbench_row_payload.clone())
        }

        async fn oa_sync_status(&self) -> Result<OaSyncStatusRow, BusinessReadRepositoryError> {
            Ok(OaSyncStatusRow {
                status: None,
                last_run_id: None,
                last_started_at: None,
                last_finished_at: None,
                last_synced_at: None,
                source_system: None,
                scope: None,
                processed_count: None,
                success_count: None,
                failed_count: None,
                error_message: None,
            })
        }

        async fn list_workbench_stale_scopes(
            &self,
        ) -> Result<Vec<WorkbenchStaleScopeRow>, BusinessReadRepositoryError> {
            Ok(Vec::new())
        }
    }

    fn ready_cost_read_model(payload: Value) -> ReadModelPayloadRow {
        ReadModelPayloadRow {
            scope_key: "active:2026-03".to_owned(),
            scope_type: "month".to_owned(),
            scope_month: Some("2026-03-01".to_owned()),
            schema_version: "2026-05-cost-statistics-explorer-v1".to_owned(),
            payload,
            source_scope_keys: vec!["workbench:2026-03".to_owned()],
            source_versions: json!({}),
            cache_status: "ready".to_owned(),
            generated_at: "2026-05-16T00:00:00Z".to_owned(),
            stale: false,
            stale_reason: None,
            rebuild_task_id: None,
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }

    fn ready_tax_read_model(payload: Value) -> ReadModelPayloadRow {
        ReadModelPayloadRow {
            scope_key: "tax_offset:2026-03".to_owned(),
            scope_type: "month".to_owned(),
            scope_month: Some("2026-03-01".to_owned()),
            schema_version: "2026-05-tax-offset-month-v1".to_owned(),
            payload,
            source_scope_keys: vec!["invoice:2026-03".to_owned()],
            source_versions: json!({}),
            cache_status: "ready".to_owned(),
            generated_at: "2026-05-16T00:00:00Z".to_owned(),
            stale: false,
            stale_reason: None,
            rebuild_task_id: None,
            updated_at: "2026-05-16T00:00:00Z".to_owned(),
        }
    }

    #[tokio::test]
    async fn tax_offset_calculate_uses_read_model_payload_without_writing() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            tax_read_model: Some(ready_tax_read_model(json!({
                "month": "2026-03",
                "output_items": [
                    {"id": "output-1", "tax_amount": "100.00"},
                    {"id": "output-2", "tax_amount": "20.00"}
                ],
                "input_plan_items": [
                    {"id": "input-1", "tax_amount": "80.00"},
                    {"id": "input-2", "tax_amount": "70.00"}
                ],
                "certified_items": [
                    {"id": "certified-1", "tax_amount": "35.00", "deductible_tax_amount": "30.00"}
                ],
                "locked_certified_input_ids": ["input-2"]
            }))),
            ..Default::default()
        });

        let payload = service
            .calculate_tax_offset(TaxOffsetCalculateRequest {
                month: Some("2026-03".to_owned()),
                selected_output_ids: Some(vec!["output-2".to_owned()]),
                selected_input_ids: Some(vec!["input-1".to_owned(), "input-2".to_owned()]),
            })
            .await
            .unwrap();

        assert_eq!(payload["month"], "2026-03");
        assert_eq!(
            payload["selected_output_ids"],
            json!(["output-1", "output-2"])
        );
        assert_eq!(payload["selected_input_ids"], json!(["input-1", "input-2"]));
        assert_eq!(payload["summary"]["output_tax"], "120.00");
        assert_eq!(payload["summary"]["certified_input_tax"], "30.00");
        assert_eq!(payload["summary"]["planned_input_tax"], "80.00");
        assert_eq!(payload["summary"]["input_tax"], "110.00");
        assert_eq!(payload["summary"]["deductible_tax"], "110.00");
        assert_eq!(payload["summary"]["result_label"], "本月应纳税额");
        assert_eq!(payload["summary"]["result_amount"], "10.00");
    }

    #[tokio::test]
    async fn tax_offset_calculate_requires_legacy_selected_output_ids_key() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            tax_read_model: Some(ready_tax_read_model(json!({
                "month": "2026-03",
                "output_items": [],
                "input_plan_items": [],
                "certified_items": [],
                "locked_certified_input_ids": []
            }))),
            ..Default::default()
        });

        let error = service
            .calculate_tax_offset(TaxOffsetCalculateRequest {
                month: Some("2026-03".to_owned()),
                selected_output_ids: None,
                selected_input_ids: Some(vec![]),
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            BusinessReadServiceError::InvalidRequest {
                code: "invalid_tax_offset_calculate_request",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn cost_project_detail_is_derived_from_cost_read_model_time_rows() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            cost_read_model: Some(ready_cost_read_model(json!({
                "month": "2026-03",
                "time_rows": [
                    {
                        "transaction_id": "txn-late",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-11 09:00:00",
                        "direction": "支出",
                        "expense_type": "交通费",
                        "expense_content": "现场交通",
                        "amount": "40.50",
                        "counterparty_name": "滴滴",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-other",
                        "project_name": "其他项目",
                        "trade_time": "2026-03-10 10:00:00",
                        "direction": "支出",
                        "expense_type": "材料费",
                        "expense_content": "材料",
                        "amount": "99.00",
                        "counterparty_name": "供应商",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-early",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-10 09:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "1250.00",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106"
                    }
                ]
            }))),
            ..Default::default()
        });

        let payload = service
            .get_cost_project_statistics(CostProjectStatisticsQuery {
                month: Some("2026-03".to_owned()),
                project_scope: Some("active".to_owned()),
                project_name: "云南溯源科技".to_owned(),
            })
            .await
            .unwrap();

        assert_eq!(payload["month"], "2026-03");
        assert_eq!(payload["project_name"], "云南溯源科技");
        assert_eq!(payload["summary"]["row_count"], 2);
        assert_eq!(payload["summary"]["transaction_count"], 2);
        assert_eq!(payload["summary"]["total_amount"], "1290.50");
        assert_eq!(payload["rows"][0]["transaction_id"], "txn-early");
        assert_eq!(payload["rows"][1]["transaction_id"], "txn-late");
    }

    #[tokio::test]
    async fn cost_export_preview_time_uses_read_model_rows_with_legacy_shape() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            cost_read_model: Some(ready_cost_read_model(json!({
                "month": "all",
                "time_rows": [
                    {
                        "transaction_id": "txn-in-range-late",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-10 16:00:00",
                        "direction": "支出",
                        "expense_type": "交通费",
                        "expense_content": "现场往返交通",
                        "amount": "40.50",
                        "counterparty_name": "滴滴",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-outside",
                        "project_name": "其他项目",
                        "trade_time": "2026-03-11 09:00:00",
                        "direction": "支出",
                        "expense_type": "材料费",
                        "expense_content": "材料",
                        "amount": "99.00",
                        "counterparty_name": "供应商",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-in-range-early",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-10 09:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "1250",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106"
                    }
                ]
            }))),
            ..Default::default()
        });

        let payload = service
            .get_cost_export_preview(CostExportPreviewQuery {
                month: Some("all".to_owned()),
                view: Some("time".to_owned()),
                project_scope: Some("active".to_owned()),
                project_name: vec![],
                expense_type: vec![],
                start_month: None,
                end_month: None,
                start_date: Some("2026-03-10".to_owned()),
                end_date: Some("2026-03-10".to_owned()),
                aggregate_by: None,
            })
            .await
            .unwrap();

        assert_eq!(payload["view"], "time");
        assert_eq!(
            payload["file_name"],
            "成本统计_2026-03-10至2026-03-10_按时间统计.xlsx"
        );
        assert_eq!(payload["scope_label"], "2026-03-10至2026-03-10");
        assert_eq!(payload["sheet_names"], json!(["按时间统计"]));
        assert_eq!(
            payload["columns"],
            json!([
                "时间",
                "项目名称",
                "费用类型",
                "金额",
                "费用内容",
                "资金方向",
                "对方户名",
                "支付账户"
            ])
        );
        assert_eq!(
            payload["rows"],
            json!([
                [
                    "2026-03-10 16:00:00",
                    "云南溯源科技",
                    "交通费",
                    "40.50",
                    "现场往返交通",
                    "支出",
                    "滴滴",
                    "建行 8106"
                ],
                [
                    "2026-03-10 09:00:00",
                    "云南溯源科技",
                    "设备货款及材料费",
                    "1250.00",
                    "PLC 模块采购",
                    "支出",
                    "昆明设备供应商",
                    "建行 8106"
                ]
            ])
        );
        assert_eq!(payload["summary"]["row_count"], 2);
        assert_eq!(payload["summary"]["transaction_count"], 2);
        assert_eq!(payload["summary"]["total_amount"], "1290.50");
        assert_eq!(payload["summary"]["sheet_count"], 1);
    }

    #[tokio::test]
    async fn cost_export_preview_project_aggregate_matches_frontend_query_shape() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            cost_read_model: Some(ready_cost_read_model(json!({
                "month": "all",
                "time_rows": [
                    {
                        "transaction_id": "txn-1",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-10 16:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "1250.00",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-2",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-12 09:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "30.50",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106"
                    },
                    {
                        "transaction_id": "txn-other",
                        "project_name": "其他项目",
                        "trade_time": "2026-03-12 09:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "99.00",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106"
                    }
                ]
            }))),
            ..Default::default()
        });

        let payload = service
            .get_cost_export_preview(CostExportPreviewQuery {
                month: Some("all".to_owned()),
                view: Some("project".to_owned()),
                project_scope: Some("all".to_owned()),
                project_name: vec!["云南溯源科技".to_owned()],
                expense_type: vec!["设备货款及材料费".to_owned()],
                start_month: None,
                end_month: None,
                start_date: None,
                end_date: None,
                aggregate_by: Some("month".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(payload["view"], "project");
        assert_eq!(
            payload["file_name"],
            "成本统计_全部期间_按项目统计_按月_云南溯源科技.xlsx"
        );
        assert_eq!(payload["sheet_names"], json!(["按项目统计"]));
        assert_eq!(
            payload["columns"],
            json!([
                "统计周期",
                "项目名称",
                "费用类型",
                "金额",
                "费用内容",
                "支出笔数"
            ])
        );
        assert_eq!(
            payload["rows"],
            json!([[
                "2026-03",
                "云南溯源科技",
                "设备货款及材料费",
                "1280.50",
                "PLC 模块采购",
                "2"
            ]])
        );
        assert_eq!(payload["summary"]["total_amount"], "1280.50");
    }

    #[tokio::test]
    async fn cost_export_preview_expense_type_requires_expense_type_filter() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            cost_read_model: Some(ready_cost_read_model(json!({
                "month": "2026-03",
                "time_rows": []
            }))),
            ..Default::default()
        });

        let error = service
            .get_cost_export_preview(CostExportPreviewQuery {
                month: Some("2026-03".to_owned()),
                view: Some("expense_type".to_owned()),
                project_scope: Some("active".to_owned()),
                project_name: vec![],
                expense_type: vec![],
                start_month: None,
                end_month: None,
                start_date: None,
                end_date: None,
                aggregate_by: None,
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            BusinessReadServiceError::InvalidRequest {
                code: "invalid_cost_statistics_export_preview_request",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn cost_transaction_detail_combines_cost_read_model_with_workbench_row_fields() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            transaction_month: Some("2026-03".to_owned()),
            workbench_row_payload: Some(json!({
                "summary_fields": {"项目名称": "云南溯源科技"},
                "detail_fields": {"申请人": "张三"}
            })),
            cost_read_model: Some(ready_cost_read_model(json!({
                "month": "2026-03",
                "time_rows": [
                    {
                        "transaction_id": "txn-cost-1",
                        "project_name": "云南溯源科技",
                        "trade_time": "2026-03-10 09:00:00",
                        "direction": "支出",
                        "expense_type": "设备货款及材料费",
                        "expense_content": "PLC 模块采购",
                        "amount": "1250.00",
                        "counterparty_name": "昆明设备供应商",
                        "payment_account_label": "建行 8106",
                        "remark": "设备采购款",
                        "oa_applicant": "李四"
                    }
                ]
            }))),
            ..Default::default()
        });

        let payload = service
            .get_cost_transaction_detail(CostTransactionDetailQuery {
                transaction_id: "txn-cost-1".to_owned(),
                project_scope: Some("active".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(payload["month"], "2026-03");
        assert_eq!(payload["transaction"]["id"], "txn-cost-1");
        assert_eq!(payload["transaction"]["project_name"], "云南溯源科技");
        assert_eq!(payload["transaction"]["expense_type"], "设备货款及材料费");
        assert_eq!(
            payload["transaction"]["summary_fields"]["项目名称"],
            "云南溯源科技"
        );
        assert_eq!(payload["transaction"]["detail_fields"]["申请人"], "张三");
    }

    #[tokio::test]
    async fn tax_certified_imports_require_month_and_preserve_legacy_record_shape() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            tax_certified_imports: vec![TaxCertifiedImportRow {
                id: "digital:002".to_owned(),
                unique_key: "digital:002".to_owned(),
                month: "2026-01".to_owned(),
                source_file_name: "认证结果.xlsx".to_owned(),
                source_row_number: 3,
                taxpayer_tax_no: Some("91530000MA00000002".to_owned()),
                taxpayer_name: Some("云南测试公司".to_owned()),
                digital_invoice_no: Some("002".to_owned()),
                invoice_code: None,
                invoice_no: Some("INV-002".to_owned()),
                issue_date: Some("2026-01-02".to_owned()),
                seller_tax_no: Some("SELLER-TAX-2".to_owned()),
                seller_name: Some("供应商二".to_owned()),
                amount: Some("200.00".to_owned()),
                tax_amount: Some("12.00".to_owned()),
                deductible_tax_amount: Some("12.00".to_owned()),
                selection_status: Some("已认证".to_owned()),
                invoice_status: Some("正常".to_owned()),
                selection_time: Some("2026-01-05 10:00:00".to_owned()),
                invoice_source: Some("电子发票服务平台".to_owned()),
                invoice_kind: Some("增值税专用发票".to_owned()),
                risk_level: Some("低".to_owned()),
                imported_at: "2026-01-05T02:00:00Z".to_owned(),
            }],
            ..Default::default()
        });

        let missing_month = service
            .get_tax_certified_imports(TaxCertifiedImportsQuery { month: None })
            .await
            .unwrap_err();
        assert!(matches!(
            missing_month,
            BusinessReadServiceError::InvalidRequest {
                code: "invalid_tax_certified_import_request",
                ..
            }
        ));

        let payload = service
            .get_tax_certified_imports(TaxCertifiedImportsQuery {
                month: Some("2026-01".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(payload.month, "2026-01");
        assert_eq!(payload.records.len(), 1);
        assert_eq!(
            payload.records[0].selection_status.as_deref(),
            Some("已认证")
        );
        assert_eq!(
            payload.records[0].deductible_tax_amount.as_deref(),
            Some("12.00")
        );
    }

    #[tokio::test]
    async fn etc_invoice_list_preserves_python_counts_pagination_and_item_shape() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            etc_invoice_rows: EtcInvoiceRows {
                rows: vec![EtcInvoiceRow {
                    id: "etc_invoice_0002".to_owned(),
                    invoice_number: "ETC002".to_owned(),
                    issue_date: "2026-02-03".to_owned(),
                    passage_start_date: Some("2026-02-01".to_owned()),
                    passage_end_date: Some("2026-02-02".to_owned()),
                    plate_number: Some("云A12345".to_owned()),
                    vehicle_type: Some("小型车".to_owned()),
                    seller_name: Some("高速公路运营方".to_owned()),
                    seller_tax_no: Some("SELLER-TAX".to_owned()),
                    buyer_name: Some("云南测试公司".to_owned()),
                    buyer_tax_no: Some("BUYER-TAX".to_owned()),
                    amount_without_tax: "100.00".to_owned(),
                    tax_amount: "3.00".to_owned(),
                    total_amount: "103.00".to_owned(),
                    tax_rate: Some("3%".to_owned()),
                    zip_source_name: "etc-202602.zip".to_owned(),
                    xml_file_path: Some("xml/ETC002.xml".to_owned()),
                    xml_file_hash: Some("xml-hash".to_owned()),
                    pdf_file_path: Some("pdf/ETC002.pdf".to_owned()),
                    pdf_file_hash: Some("pdf-hash".to_owned()),
                    status: "submitted".to_owned(),
                    import_batch_id: Some("import-batch-1".to_owned()),
                    import_session_id: Some("session-1".to_owned()),
                    current_batch_id: Some("current-batch-1".to_owned()),
                    last_batch_id: Some("last-batch-1".to_owned()),
                    created_at: "2026-02-03T01:00:00Z".to_owned(),
                    updated_at: "2026-02-03T02:00:00Z".to_owned(),
                    has_pdf: false,
                    has_xml: false,
                }],
                total: 3,
                unsubmitted_count: 2,
                submitted_count: 1,
            },
            ..Default::default()
        });

        let payload = service
            .list_etc_invoices(EtcInvoiceListQuery {
                status: Some("submitted".to_owned()),
                month: Some("2026-02".to_owned()),
                plate: Some("云A".to_owned()),
                keyword: Some("ETC002".to_owned()),
                page: Some("0".to_owned()),
                page_size: Some("999".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(payload.page, 1);
        assert_eq!(payload.page_size, 500);
        assert_eq!(payload.total, 3);
        assert_eq!(payload.counts["unsubmitted"], 2);
        assert_eq!(payload.counts["submitted"], 1);
        assert_eq!(payload.counts["current"], 3);
        assert_eq!(payload.items[0].invoice_number, "ETC002");
        assert_eq!(payload.items[0].status, "submitted");
        assert!(!payload.items[0].has_pdf);
        assert!(!payload.items[0].has_xml);
    }

    #[tokio::test]
    async fn etc_invoice_list_rejects_non_integer_pagination_like_python_api() {
        let service = BusinessReadService::new(StubBusinessReadRepository::default());
        let error = service
            .list_etc_invoices(EtcInvoiceListQuery {
                page: Some("not-a-number".to_owned()),
                page_size: Some("20".to_owned()),
                status: None,
                month: None,
                plate: None,
                keyword: None,
            })
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            BusinessReadServiceError::InvalidRequest {
                code: "invalid_etc_invoice_request",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn etc_batch_list_uses_postgres_facts_with_legacy_envelope() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            etc_batch_rows: EtcBatchRows {
                rows: vec![EtcBatchRow {
                    id: "etc_import_batch_001".to_owned(),
                    etc_batch_id: "etc_import_batch_001".to_owned(),
                    status: "unsubmitted".to_owned(),
                    source_type: "etc_import".to_owned(),
                    invoice_count: 2,
                    total_amount: "100.00".to_owned(),
                    tax_amount: "5.00".to_owned(),
                    issue_start_date: Some("2026-05-01".to_owned()),
                    issue_end_date: Some("2026-05-02".to_owned()),
                    passage_start_date: Some("2026-05-01".to_owned()),
                    passage_end_date: Some("2026-05-02".to_owned()),
                    plate_summary: vec![EtcPlateSummaryRow {
                        plate_number: "云A12345".to_owned(),
                        invoice_count: 2,
                        total_amount: "100.00".to_owned(),
                    }],
                    linked_oa_row_id: None,
                    linked_oa_case_id: None,
                    amount_delta: None,
                    note: None,
                    created_at: "2026-05-17T01:00:00Z".to_owned(),
                }],
                total: 1,
                unsubmitted_count: 1,
                submitted_count: 0,
            },
            ..Default::default()
        });

        let response = service
            .list_etc_batches(EtcBatchQuery {
                status: Some("unsubmitted".to_owned()),
                month: Some("2026-05".to_owned()),
                plate: None,
                keyword: None,
                page: Some("1".to_owned()),
                page_size: Some("50".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(response.items[0].id, "etc_import_batch_001");
        assert_eq!(response.items[0].etc_batch_id, "etc_import_batch_001");
        assert_eq!(response.items[0].source_type, "etc_import");
        assert_eq!(response.items[0].plate_summary[0].plate_number, "云A12345");
        assert_eq!(response.counts["unsubmitted"], 1);
        assert_eq!(response.pagination.total, 1);
        assert!(response.selected_batch.is_some());
    }

    #[tokio::test]
    async fn etc_batch_detail_returns_summary_plate_and_invoice_items() {
        let service = BusinessReadService::new(StubBusinessReadRepository {
            etc_batch_detail: Some(EtcBatchDetailRows {
                summary: EtcBatchRow {
                    id: "etc_batch_001".to_owned(),
                    etc_batch_id: "ETC-OA-001".to_owned(),
                    status: "submitted".to_owned(),
                    source_type: "normal_oa_draft".to_owned(),
                    invoice_count: 1,
                    total_amount: "50.00".to_owned(),
                    tax_amount: "2.50".to_owned(),
                    issue_start_date: Some("2026-05-03".to_owned()),
                    issue_end_date: Some("2026-05-03".to_owned()),
                    passage_start_date: Some("2026-05-03".to_owned()),
                    passage_end_date: Some("2026-05-03".to_owned()),
                    plate_summary: vec![EtcPlateSummaryRow {
                        plate_number: "云A99999".to_owned(),
                        invoice_count: 1,
                        total_amount: "50.00".to_owned(),
                    }],
                    linked_oa_row_id: Some("oa-row-1".to_owned()),
                    linked_oa_case_id: Some("oa-case-1".to_owned()),
                    amount_delta: Some("0.00".to_owned()),
                    note: Some("已提交".to_owned()),
                    created_at: "2026-05-17T02:00:00Z".to_owned(),
                },
                invoices: vec![EtcInvoiceRow {
                    id: "etc_invoice_001".to_owned(),
                    invoice_number: "2450000001".to_owned(),
                    issue_date: "2026-05-03".to_owned(),
                    passage_start_date: Some("2026-05-03".to_owned()),
                    passage_end_date: Some("2026-05-03".to_owned()),
                    plate_number: Some("云A99999".to_owned()),
                    vehicle_type: None,
                    seller_name: Some("ETC服务商".to_owned()),
                    seller_tax_no: None,
                    buyer_name: None,
                    buyer_tax_no: None,
                    amount_without_tax: "47.50".to_owned(),
                    tax_amount: "2.50".to_owned(),
                    total_amount: "50.00".to_owned(),
                    tax_rate: None,
                    zip_source_name: "etc.zip".to_owned(),
                    xml_file_path: None,
                    xml_file_hash: None,
                    pdf_file_path: None,
                    pdf_file_hash: None,
                    status: "submitted".to_owned(),
                    import_batch_id: Some("etc_import_batch_001".to_owned()),
                    import_session_id: None,
                    current_batch_id: Some("etc_batch_001".to_owned()),
                    last_batch_id: Some("etc_batch_001".to_owned()),
                    created_at: "2026-05-17T02:00:00Z".to_owned(),
                    updated_at: "2026-05-17T02:00:00Z".to_owned(),
                    has_pdf: false,
                    has_xml: false,
                }],
            }),
            ..Default::default()
        });

        let response = service.get_etc_batch("etc_batch_001").await.unwrap();

        assert_eq!(response.summary.etc_batch_id, "ETC-OA-001");
        assert_eq!(response.batch.id, "etc_batch_001");
        assert_eq!(response.plate_summary[0].plate_number, "云A99999");
        assert_eq!(response.invoice_items[0].invoice_number, "2450000001");
    }
}
