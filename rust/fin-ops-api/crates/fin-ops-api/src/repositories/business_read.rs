use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sqlx::{PgPool, Row};
use uuid::Uuid;

use crate::services::business_read::{
    BankDetailDateFilter, EtcBatchFilter, EtcInvoiceListFilter, NoOaBatchListFilter,
};

#[derive(Clone, Debug)]
pub struct BankDetailAccountRow {
    pub account_key: String,
    pub bank_name: String,
    pub account_last4: String,
    pub latest_balance: Option<String>,
    pub latest_balance_at: Option<String>,
    pub transaction_count: i64,
}

#[derive(Clone, Debug)]
pub struct BankDetailTransactionRow {
    pub id: String,
    pub trade_time: String,
    pub counterparty_name: String,
    pub direction: String,
    pub amount: String,
    pub balance: Option<String>,
    pub summary: Option<String>,
    pub remark: Option<String>,
    pub bank_name: String,
    pub account_last4: String,
    pub raw_payload: Value,
    pub manual_category_code: Option<String>,
    pub manual_category_source: Option<String>,
    pub manual_category_version: Option<i64>,
    pub category_raw_payload: Value,
}

#[derive(Clone, Debug)]
pub struct BankDetailTransactionFilter {
    pub account_key: Option<String>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
    pub keyword: Option<String>,
    pub limit: i64,
    pub offset: i64,
}

#[derive(Clone, Debug)]
pub struct BankDetailTransactionRows {
    pub rows: Vec<BankDetailTransactionRow>,
    pub category_counts: Vec<(String, i64)>,
    pub total: i64,
}

#[derive(Clone, Debug)]
pub struct NoOaBatchRow {
    pub batch_id: String,
    pub scope_month: String,
    pub status: String,
    pub row_count: i64,
    pub total_amount: String,
    pub submitted_at: Option<String>,
    pub cancelled_at: Option<String>,
    pub raw_payload: Value,
    pub row_version: i64,
    pub tag_counts: Value,
    pub direction_counts: Value,
}

#[derive(Clone, Debug)]
pub struct NoOaDetailRow {
    pub transaction_id: String,
    pub txn_date: String,
    pub trade_time: Option<String>,
    pub counterparty_name: String,
    pub direction: String,
    pub amount: String,
    pub summary: Option<String>,
    pub remark: Option<String>,
    pub raw_payload: Value,
    pub category_code: Option<String>,
    pub category_label: Option<String>,
    pub category_source: Option<String>,
}

#[derive(Clone, Debug)]
pub struct ReadModelPayloadRow {
    pub scope_key: String,
    pub scope_type: String,
    pub scope_month: Option<String>,
    pub schema_version: String,
    pub payload: Value,
    pub source_scope_keys: Vec<String>,
    pub source_versions: Value,
    pub cache_status: String,
    pub generated_at: String,
    pub stale: bool,
    pub stale_reason: Option<String>,
    pub rebuild_task_id: Option<String>,
    pub updated_at: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct TaxCertifiedImportRow {
    pub id: String,
    pub unique_key: String,
    pub month: String,
    pub source_file_name: String,
    pub source_row_number: i64,
    pub taxpayer_tax_no: Option<String>,
    pub taxpayer_name: Option<String>,
    pub digital_invoice_no: Option<String>,
    pub invoice_code: Option<String>,
    pub invoice_no: Option<String>,
    pub issue_date: Option<String>,
    pub seller_tax_no: Option<String>,
    pub seller_name: Option<String>,
    pub amount: Option<String>,
    pub tax_amount: Option<String>,
    pub deductible_tax_amount: Option<String>,
    pub selection_status: Option<String>,
    pub invoice_status: Option<String>,
    pub selection_time: Option<String>,
    pub invoice_source: Option<String>,
    pub invoice_kind: Option<String>,
    pub risk_level: Option<String>,
    pub imported_at: String,
}

#[derive(Clone, Debug, Default)]
pub struct EtcInvoiceRows {
    pub rows: Vec<EtcInvoiceRow>,
    pub total: i64,
    pub unsubmitted_count: i64,
    pub submitted_count: i64,
}

#[derive(Clone, Debug, Default)]
pub struct EtcBatchRows {
    pub rows: Vec<EtcBatchRow>,
    pub total: i64,
    pub unsubmitted_count: i64,
    pub submitted_count: i64,
}

#[derive(Clone, Debug)]
pub struct EtcBatchDetailRows {
    pub summary: EtcBatchRow,
    pub invoices: Vec<EtcInvoiceRow>,
}

#[derive(Clone, Debug)]
pub struct EtcBatchRow {
    pub id: String,
    pub etc_batch_id: String,
    pub status: String,
    pub source_type: String,
    pub invoice_count: i64,
    pub total_amount: String,
    pub tax_amount: String,
    pub issue_start_date: Option<String>,
    pub issue_end_date: Option<String>,
    pub passage_start_date: Option<String>,
    pub passage_end_date: Option<String>,
    pub plate_summary: Vec<EtcPlateSummaryRow>,
    pub linked_oa_row_id: Option<String>,
    pub linked_oa_case_id: Option<String>,
    pub amount_delta: Option<String>,
    pub note: Option<String>,
    pub created_at: String,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct EtcPlateSummaryRow {
    pub plate_number: String,
    pub invoice_count: i64,
    pub total_amount: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct EtcInvoiceRow {
    pub id: String,
    pub invoice_number: String,
    pub issue_date: String,
    pub passage_start_date: Option<String>,
    pub passage_end_date: Option<String>,
    pub plate_number: Option<String>,
    pub vehicle_type: Option<String>,
    pub seller_name: Option<String>,
    pub seller_tax_no: Option<String>,
    pub buyer_name: Option<String>,
    pub buyer_tax_no: Option<String>,
    pub amount_without_tax: String,
    pub tax_amount: String,
    pub total_amount: String,
    pub tax_rate: Option<String>,
    pub zip_source_name: String,
    pub xml_file_path: Option<String>,
    pub xml_file_hash: Option<String>,
    pub pdf_file_path: Option<String>,
    pub pdf_file_hash: Option<String>,
    pub status: String,
    pub import_batch_id: Option<String>,
    pub import_session_id: Option<String>,
    pub current_batch_id: Option<String>,
    pub last_batch_id: Option<String>,
    pub created_at: String,
    pub updated_at: String,
    pub has_pdf: bool,
    pub has_xml: bool,
}

#[derive(Clone, Debug)]
pub struct OaSyncStatusRow {
    pub status: Option<String>,
    pub last_run_id: Option<String>,
    pub last_started_at: Option<String>,
    pub last_finished_at: Option<String>,
    pub last_synced_at: Option<String>,
    pub source_system: Option<String>,
    pub scope: Option<String>,
    pub processed_count: Option<i64>,
    pub success_count: Option<i64>,
    pub failed_count: Option<i64>,
    pub error_message: Option<String>,
}

#[derive(Clone, Debug)]
pub struct WorkbenchStaleScopeRow {
    pub scope: String,
    pub stale_reason: Option<String>,
    pub updated_at: String,
}

#[derive(Debug, thiserror::Error)]
pub enum BusinessReadRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait BusinessReadRepository: Send + Sync {
    async fn list_bank_detail_accounts(
        &self,
        filter: BankDetailDateFilter,
    ) -> Result<Vec<BankDetailAccountRow>, BusinessReadRepositoryError>;
    async fn list_bank_detail_transactions(
        &self,
        filter: BankDetailTransactionFilter,
    ) -> Result<BankDetailTransactionRows, BusinessReadRepositoryError>;
    async fn list_no_oa_batches(
        &self,
        filter: NoOaBatchListFilter,
    ) -> Result<Vec<NoOaBatchRow>, BusinessReadRepositoryError>;
    async fn find_no_oa_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Option<(NoOaBatchRow, Vec<NoOaDetailRow>)>, BusinessReadRepositoryError>;
    async fn find_tax_offset_read_model(
        &self,
        month: &str,
    ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError>;
    async fn list_tax_certified_imports(
        &self,
        month: &str,
    ) -> Result<Vec<TaxCertifiedImportRow>, BusinessReadRepositoryError>;
    async fn list_etc_invoices(
        &self,
        filter: EtcInvoiceListFilter,
    ) -> Result<EtcInvoiceRows, BusinessReadRepositoryError>;
    async fn list_etc_batches(
        &self,
        filter: EtcBatchFilter,
    ) -> Result<EtcBatchRows, BusinessReadRepositoryError>;
    async fn find_etc_batch(
        &self,
        batch_id: &str,
    ) -> Result<Option<EtcBatchDetailRows>, BusinessReadRepositoryError>;
    async fn find_cost_statistics_read_model(
        &self,
        month: &str,
        project_scope: &str,
    ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError>;
    async fn find_cost_transaction_month(
        &self,
        transaction_id: &str,
    ) -> Result<Option<String>, BusinessReadRepositoryError>;
    async fn find_workbench_row_payload(
        &self,
        row_id: &str,
        month: &str,
    ) -> Result<Option<Value>, BusinessReadRepositoryError>;
    async fn oa_sync_status(&self) -> Result<OaSyncStatusRow, BusinessReadRepositoryError>;
    async fn list_workbench_stale_scopes(
        &self,
    ) -> Result<Vec<WorkbenchStaleScopeRow>, BusinessReadRepositoryError>;
}

#[derive(Clone)]
pub struct SqlxBusinessReadRepository {
    pool: PgPool,
}

impl SqlxBusinessReadRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl BusinessReadRepository for SqlxBusinessReadRepository {
    async fn list_bank_detail_accounts(
        &self,
        filter: BankDetailDateFilter,
    ) -> Result<Vec<BankDetailAccountRow>, BusinessReadRepositoryError> {
        let rows = sqlx::query(BANK_DETAIL_ACCOUNTS_SQL)
            .bind(filter.date_from)
            .bind(filter.date_to)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter().map(row_to_bank_detail_account).collect()
    }

    async fn list_bank_detail_transactions(
        &self,
        filter: BankDetailTransactionFilter,
    ) -> Result<BankDetailTransactionRows, BusinessReadRepositoryError> {
        let rows = sqlx::query(BANK_DETAIL_TRANSACTIONS_SQL)
            .bind(filter.account_key.clone())
            .bind(filter.date_from.clone())
            .bind(filter.date_to.clone())
            .bind(filter.keyword.clone())
            .bind(filter.limit)
            .bind(filter.offset)
            .fetch_all(&self.pool)
            .await?;
        let rows = rows
            .into_iter()
            .map(row_to_bank_detail_transaction)
            .collect::<Result<Vec<_>, _>>()?;

        let category_rows = sqlx::query(BANK_DETAIL_CATEGORY_COUNTS_SQL)
            .bind(filter.account_key)
            .bind(filter.date_from)
            .bind(filter.date_to)
            .bind(filter.keyword)
            .fetch_all(&self.pool)
            .await?;
        let mut total = 0;
        let mut category_counts = Vec::with_capacity(category_rows.len());
        for row in category_rows {
            let code: String = row.try_get("category_code")?;
            let count: i64 = row.try_get("row_count")?;
            total += count;
            category_counts.push((code, count));
        }

        Ok(BankDetailTransactionRows {
            rows,
            category_counts,
            total,
        })
    }

    async fn list_no_oa_batches(
        &self,
        filter: NoOaBatchListFilter,
    ) -> Result<Vec<NoOaBatchRow>, BusinessReadRepositoryError> {
        let rows = sqlx::query(NO_OA_BATCH_LIST_SQL)
            .bind(filter.month)
            .bind(filter.status)
            .bind(filter.bucket)
            .bind(filter.batch_type)
            .bind(filter.account_key)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter().map(row_to_no_oa_batch).collect()
    }

    async fn find_no_oa_batch(
        &self,
        batch_id: Uuid,
    ) -> Result<Option<(NoOaBatchRow, Vec<NoOaDetailRow>)>, BusinessReadRepositoryError> {
        let Some(batch_row) = sqlx::query(NO_OA_BATCH_DETAIL_SQL)
            .bind(batch_id)
            .fetch_optional(&self.pool)
            .await?
        else {
            return Ok(None);
        };
        let batch = row_to_no_oa_batch(batch_row)?;
        let rows = sqlx::query(NO_OA_BATCH_DETAIL_ROWS_SQL)
            .bind(batch_id)
            .fetch_all(&self.pool)
            .await?;
        let rows = rows
            .into_iter()
            .map(row_to_no_oa_detail)
            .collect::<Result<_, _>>()?;
        Ok(Some((batch, rows)))
    }

    async fn find_tax_offset_read_model(
        &self,
        month: &str,
    ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError> {
        sqlx::query(TAX_OFFSET_READ_MODEL_SQL)
            .bind(month)
            .fetch_optional(&self.pool)
            .await?
            .map(row_to_read_model_payload)
            .transpose()
    }

    async fn list_tax_certified_imports(
        &self,
        month: &str,
    ) -> Result<Vec<TaxCertifiedImportRow>, BusinessReadRepositoryError> {
        let rows = sqlx::query(TAX_CERTIFIED_IMPORTS_SQL)
            .bind(month)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter().map(row_to_tax_certified_import).collect()
    }

    async fn list_etc_invoices(
        &self,
        filter: EtcInvoiceListFilter,
    ) -> Result<EtcInvoiceRows, BusinessReadRepositoryError> {
        let invoices_sql = etc_invoices_sql();
        let rows = sqlx::query(&invoices_sql)
            .bind(filter.status.clone())
            .bind(filter.month.clone())
            .bind(filter.plate.clone())
            .bind(filter.keyword.clone())
            .bind(filter.limit)
            .bind(filter.offset)
            .fetch_all(&self.pool)
            .await?;
        let rows = rows
            .into_iter()
            .map(row_to_etc_invoice)
            .collect::<Result<Vec<_>, _>>()?;

        let total_sql = etc_invoices_total_sql();
        let total_row = sqlx::query(&total_sql)
            .bind(filter.status)
            .bind(filter.month)
            .bind(filter.plate)
            .bind(filter.keyword)
            .fetch_one(&self.pool)
            .await?;
        let status_counts_sql = etc_invoices_status_counts_sql();
        let counts_row = sqlx::query(&status_counts_sql)
            .fetch_one(&self.pool)
            .await?;

        Ok(EtcInvoiceRows {
            rows,
            total: total_row.try_get("total")?,
            unsubmitted_count: counts_row.try_get("unsubmitted_count")?,
            submitted_count: counts_row.try_get("submitted_count")?,
        })
    }

    async fn list_etc_batches(
        &self,
        filter: EtcBatchFilter,
    ) -> Result<EtcBatchRows, BusinessReadRepositoryError> {
        let batch_sql = etc_batches_sql();
        let rows = sqlx::query(&batch_sql)
            .bind(filter.status.clone())
            .bind(filter.month.clone())
            .bind(filter.plate.clone())
            .bind(filter.keyword.clone())
            .bind(filter.limit)
            .bind(filter.offset)
            .fetch_all(&self.pool)
            .await?;
        let rows = rows
            .into_iter()
            .map(row_to_etc_batch)
            .collect::<Result<Vec<_>, _>>()?;

        let total_sql = etc_batches_total_sql();
        let total: i64 = sqlx::query_scalar(&total_sql)
            .bind(filter.status)
            .bind(filter.month)
            .bind(filter.plate)
            .bind(filter.keyword)
            .fetch_one(&self.pool)
            .await?;

        let counts_sql = etc_batches_status_counts_sql();
        let counts_row = sqlx::query(&counts_sql).fetch_one(&self.pool).await?;

        Ok(EtcBatchRows {
            rows,
            total,
            unsubmitted_count: counts_row.try_get("unsubmitted_count")?,
            submitted_count: counts_row.try_get("submitted_count")?,
        })
    }

    async fn find_etc_batch(
        &self,
        batch_id: &str,
    ) -> Result<Option<EtcBatchDetailRows>, BusinessReadRepositoryError> {
        let summary_sql = etc_batch_detail_summary_sql();
        let Some(summary_row) = sqlx::query(&summary_sql)
            .bind(Option::<String>::None)
            .bind(Option::<String>::None)
            .bind(Option::<String>::None)
            .bind(Option::<String>::None)
            .bind(batch_id)
            .fetch_optional(&self.pool)
            .await?
        else {
            return Ok(None);
        };
        let summary = row_to_etc_batch(summary_row)?;

        let invoices_sql = etc_batch_detail_invoices_sql();
        let invoices = sqlx::query(&invoices_sql)
            .bind(batch_id)
            .fetch_all(&self.pool)
            .await?
            .into_iter()
            .map(row_to_etc_invoice)
            .collect::<Result<Vec<_>, _>>()?;

        Ok(Some(EtcBatchDetailRows { summary, invoices }))
    }

    async fn find_cost_statistics_read_model(
        &self,
        month: &str,
        project_scope: &str,
    ) -> Result<Option<ReadModelPayloadRow>, BusinessReadRepositoryError> {
        sqlx::query(COST_STATISTICS_READ_MODEL_SQL)
            .bind(format!("{project_scope}:{month}"))
            .fetch_optional(&self.pool)
            .await?
            .map(row_to_read_model_payload)
            .transpose()
    }

    async fn find_cost_transaction_month(
        &self,
        transaction_id: &str,
    ) -> Result<Option<String>, BusinessReadRepositoryError> {
        let row = sqlx::query(COST_TRANSACTION_MONTH_SQL)
            .bind(transaction_id)
            .fetch_optional(&self.pool)
            .await?;
        Ok(row.map(|row| row.try_get("scope_month")).transpose()?)
    }

    async fn find_workbench_row_payload(
        &self,
        row_id: &str,
        month: &str,
    ) -> Result<Option<Value>, BusinessReadRepositoryError> {
        let row = sqlx::query(WORKBENCH_ROW_PAYLOAD_SQL)
            .bind(row_id)
            .bind(month)
            .fetch_optional(&self.pool)
            .await?;
        Ok(row.map(|row| row.try_get("payload")).transpose()?)
    }

    async fn oa_sync_status(&self) -> Result<OaSyncStatusRow, BusinessReadRepositoryError> {
        let row = sqlx::query(OA_SYNC_STATUS_SQL)
            .fetch_one(&self.pool)
            .await?;
        Ok(OaSyncStatusRow {
            status: row.try_get("status")?,
            last_run_id: row.try_get("last_run_id")?,
            last_started_at: row.try_get("last_started_at")?,
            last_finished_at: row.try_get("last_finished_at")?,
            last_synced_at: row.try_get("last_synced_at")?,
            source_system: row.try_get("source_system")?,
            scope: row.try_get("scope")?,
            processed_count: row.try_get("processed_count")?,
            success_count: row.try_get("success_count")?,
            failed_count: row.try_get("failed_count")?,
            error_message: row.try_get("error_message")?,
        })
    }

    async fn list_workbench_stale_scopes(
        &self,
    ) -> Result<Vec<WorkbenchStaleScopeRow>, BusinessReadRepositoryError> {
        let rows = sqlx::query(WORKBENCH_STALE_SCOPES_SQL)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter().map(row_to_workbench_stale_scope).collect()
    }
}

const NO_OA_BATCH_LIST_SQL: &str = r#"
select
  b.id::text as batch_id,
  to_char(b.scope_month, 'YYYY-MM') as scope_month,
  b.status,
  cardinality(b.bank_transaction_ids)::bigint as row_count,
  b.total_amount::text as total_amount,
  to_char(b.submitted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as submitted_at,
  to_char(b.cancelled_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as cancelled_at,
  b.raw_payload,
  coalesce(b.row_version, 1)::bigint as row_version,
  coalesce(b.raw_payload->'tag_counts', '{}'::jsonb) as tag_counts,
  coalesce(b.raw_payload->'direction_counts', '{}'::jsonb) as direction_counts
from app.no_oa_bank_batches b
where ($1::text is null or b.scope_month = to_date($1::text || '-01', 'YYYY-MM-DD'))
  and ($2::text is null or b.status = $2::text)
  and ($3::text is null or case when b.status = 'cancelled' then 'withdrawn' when b.status in ('submitted', 'confirmed') then 'submitted' else b.status end = $3::text)
  and ($4::text is null or b.raw_payload->>'batch_type' = $4::text)
  and ($5::text is null or b.raw_payload->>'account_key' = $5::text)
order by b.scope_month desc, b.created_at desc, b.id
limit 500
"#;

const BANK_DETAIL_ACCOUNTS_SQL: &str = r#"
with account_base as (
  select
    t.id,
    t.txn_date,
    coalesce(t.trade_time, t.txn_date::timestamptz) as event_time,
    coalesce(
      nullif(t.raw_payload->>'imported_bank_name', ''),
      nullif(t.raw_payload->>'bank_name', ''),
      '未知银行'
    ) as bank_name,
    coalesce(
      nullif(right(coalesce(t.raw_payload->>'imported_bank_last4', t.raw_payload->>'account_last4', ''), 4), ''),
      nullif(right(regexp_replace(t.account_no, '\D', '', 'g'), 4), ''),
      'unknown'
    ) as account_last4,
    t.balance
  from app.bank_transactions t
),
normalized as (
  select
    lower(replace(bank_name, ' ', '-')) || ':' || account_last4 as account_key,
    bank_name,
    account_last4,
    txn_date,
    event_time,
    id,
    balance
  from account_base
),
accounts as (
  select
    account_key,
    bank_name,
    account_last4,
    count(*) filter (
      where ($1::text is null or txn_date >= $1::date)
        and ($2::text is null or txn_date <= $2::date)
    )::bigint as transaction_count
  from normalized
  group by account_key, bank_name, account_last4
),
latest_balance as (
  select distinct on (account_key)
    account_key,
    balance::text as latest_balance,
    to_char(event_time at time zone 'UTC', 'YYYY-MM-DD') as latest_balance_at
  from normalized
  where balance is not null
  order by account_key, event_time desc, id
)
select
  a.account_key,
  a.bank_name,
  a.account_last4,
  lb.latest_balance,
  lb.latest_balance_at,
  a.transaction_count
from accounts a
left join latest_balance lb on lb.account_key = a.account_key
order by a.bank_name, a.account_last4
"#;

const COST_TRANSACTION_MONTH_SQL: &str = r#"
select to_char(txn_date, 'YYYY-MM') as scope_month
from app.bank_transactions
where id::text = $1
limit 1
"#;

const WORKBENCH_ROW_PAYLOAD_SQL: &str = r#"
select payload
from read_model.workbench_rows
where row_id::text = $1
  and scope_month = to_date($2::text || '-01', 'YYYY-MM-DD')
order by updated_at desc
limit 1
"#;

const TAX_CERTIFIED_IMPORTS_SQL: &str = r#"
select
  coalesce(nullif(c.raw_payload->>'id', ''), c.source_unique_key, c.id::text) as id,
  coalesce(nullif(c.raw_payload->>'unique_key', ''), c.source_unique_key, c.id::text) as unique_key,
  to_char(c.certification_month, 'YYYY-MM') as month,
  coalesce(c.raw_payload->>'source_file_name', '') as source_file_name,
  case
    when coalesce(c.raw_payload->>'source_row_number', '') ~ '^[0-9]+$'
      then (c.raw_payload->>'source_row_number')::bigint
    else 0::bigint
  end as source_row_number,
  nullif(c.raw_payload->>'taxpayer_tax_no', '') as taxpayer_tax_no,
  nullif(c.raw_payload->>'taxpayer_name', '') as taxpayer_name,
  coalesce(nullif(c.raw_payload->>'digital_invoice_no', ''), i.digital_invoice_no) as digital_invoice_no,
  coalesce(nullif(c.raw_payload->>'invoice_code', ''), i.invoice_code) as invoice_code,
  coalesce(nullif(c.raw_payload->>'invoice_no', ''), i.invoice_no) as invoice_no,
  coalesce(nullif(c.raw_payload->>'issue_date', ''), to_char(i.invoice_date, 'YYYY-MM-DD')) as issue_date,
  coalesce(nullif(c.raw_payload->>'seller_tax_no', ''), i.seller_tax_no) as seller_tax_no,
  coalesce(nullif(c.raw_payload->>'seller_name', ''), i.seller_name) as seller_name,
  coalesce(nullif(c.raw_payload->>'amount', ''), i.amount::text) as amount,
  coalesce(nullif(c.raw_payload->>'tax_amount', ''), i.tax_amount::text) as tax_amount,
  coalesce(nullif(c.raw_payload->>'deductible_tax_amount', ''), c.certified_tax_amount::text) as deductible_tax_amount,
  coalesce(nullif(c.raw_payload->>'selection_status', ''), c.status) as selection_status,
  coalesce(nullif(c.raw_payload->>'invoice_status', ''), i.invoice_status_from_source) as invoice_status,
  nullif(c.raw_payload->>'selection_time', '') as selection_time,
  nullif(c.raw_payload->>'invoice_source', '') as invoice_source,
  nullif(c.raw_payload->>'invoice_kind', '') as invoice_kind,
  coalesce(nullif(c.raw_payload->>'risk_level', ''), i.risk_level) as risk_level,
  to_char(coalesce(c.certified_at, c.created_at) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as imported_at
from app.invoice_certifications c
join app.invoices i
  on i.invoice_month = c.invoice_month
 and i.id = c.invoice_id
where c.certification_month = to_date($1::text || '-01', 'YYYY-MM-DD')
  and c.status <> 'cancelled'
  and (
    c.certification_source = 'tax_certified_import'
    or c.legacy_collection = 'tax_certified_import_records'
  )
order by source_file_name, source_row_number, invoice_no, id
"#;

const ETC_INVOICE_BASE_SQL: &str = r#"
with base as (
  select
    coalesce(nullif(i.raw_payload->>'id', ''), i.etc_invoice_id, i.id::text) as id,
    coalesce(
      nullif(i.raw_payload->>'invoice_number', ''),
      nullif(i.digital_invoice_no, ''),
      nullif(i.invoice_no, ''),
      i.id::text
    ) as invoice_number,
    coalesce(nullif(i.raw_payload->>'issue_date', ''), to_char(i.invoice_date, 'YYYY-MM-DD'), '') as issue_date,
    nullif(i.raw_payload->>'passage_start_date', '') as passage_start_date,
    nullif(i.raw_payload->>'passage_end_date', '') as passage_end_date,
    nullif(i.raw_payload->>'plate_number', '') as plate_number,
    nullif(i.raw_payload->>'vehicle_type', '') as vehicle_type,
    coalesce(nullif(i.raw_payload->>'seller_name', ''), i.seller_name) as seller_name,
    coalesce(nullif(i.raw_payload->>'seller_tax_no', ''), i.seller_tax_no) as seller_tax_no,
    coalesce(nullif(i.raw_payload->>'buyer_name', ''), i.buyer_name) as buyer_name,
    coalesce(nullif(i.raw_payload->>'buyer_tax_no', ''), i.buyer_tax_no) as buyer_tax_no,
    coalesce(nullif(i.raw_payload->>'amount_without_tax', ''), i.amount::text, '0.00') as amount_without_tax,
    coalesce(nullif(i.raw_payload->>'tax_amount', ''), i.tax_amount::text, '0.00') as tax_amount,
    coalesce(nullif(i.raw_payload->>'total_amount', ''), i.total_with_tax::text, '0.00') as total_amount,
    coalesce(nullif(i.raw_payload->>'tax_rate', ''), i.tax_rate::text) as tax_rate,
    coalesce(nullif(i.raw_payload->>'zip_source_name', ''), '') as zip_source_name,
    nullif(i.raw_payload->>'xml_file_path', '') as xml_file_path,
    nullif(i.raw_payload->>'xml_file_hash', '') as xml_file_hash,
    nullif(i.raw_payload->>'pdf_file_path', '') as pdf_file_path,
    nullif(i.raw_payload->>'pdf_file_hash', '') as pdf_file_hash,
    case
      when i.raw_payload->>'status' in ('unsubmitted', 'submitted') then i.raw_payload->>'status'
      when i.etc_submission_status in ('submitted', 'submitted_confirmed') or i.etc_submission_batch_id is not null then 'submitted'
      else 'unsubmitted'
    end as status,
    coalesce(nullif(i.raw_payload->>'import_batch_id', ''), i.etc_import_batch_id) as import_batch_id,
    nullif(i.raw_payload->>'import_session_id', '') as import_session_id,
    coalesce(nullif(i.raw_payload->>'current_batch_id', ''), i.etc_submission_batch_id) as current_batch_id,
    nullif(i.raw_payload->>'last_batch_id', '') as last_batch_id,
    nullif(i.raw_payload->>'etc_batch_id', '') as legacy_etc_batch_id,
    nullif(i.raw_payload->>'source_type', '') as legacy_source_type,
    nullif(i.raw_payload->>'linked_oa_row_id', '') as linked_oa_row_id,
    nullif(i.raw_payload->>'linked_oa_case_id', '') as linked_oa_case_id,
    nullif(i.raw_payload->>'amount_delta', '') as amount_delta,
    nullif(i.raw_payload->>'note', '') as note,
    coalesce(
      nullif(i.raw_payload->>'created_at', ''),
      to_char(i.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    ) as created_at,
    coalesce(
      nullif(i.raw_payload->>'updated_at', ''),
      to_char(i.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
    ) as updated_at
  from app.invoices i
  where i.invoice_type = 'input'
    and (
      i.etc_invoice_id is not null
      or i.etc_import_batch_id is not null
      or i.raw_payload ? 'zip_source_name'
      or i.raw_payload ? 'plate_number'
    )
)
"#;

fn etc_invoices_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
select
  id,
  invoice_number,
  issue_date,
  passage_start_date,
  passage_end_date,
  plate_number,
  vehicle_type,
  seller_name,
  seller_tax_no,
  buyer_name,
  buyer_tax_no,
  amount_without_tax,
  tax_amount,
  total_amount,
  tax_rate,
  zip_source_name,
  xml_file_path,
  xml_file_hash,
  pdf_file_path,
  pdf_file_hash,
  status,
  import_batch_id,
  import_session_id,
  current_batch_id,
  last_batch_id,
  created_at,
  updated_at,
  false as has_pdf,
  false as has_xml
from base
where ($1::text is null or status = $1::text)
  and ($2::text is null or issue_date like $2::text || '%')
  and ($3::text is null or coalesce(plate_number, '') ilike '%' || $3::text || '%')
  and (
    $4::text is null
    or concat_ws(' ', invoice_number, seller_name, buyer_name, plate_number) ilike '%' || $4::text || '%'
  )
order by issue_date desc, invoice_number desc
limit $5 offset $6
"#
    )
}

fn etc_invoices_total_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
select count(*)::bigint as total
from base
where ($1::text is null or status = $1::text)
  and ($2::text is null or issue_date like $2::text || '%')
  and ($3::text is null or coalesce(plate_number, '') ilike '%' || $3::text || '%')
  and (
    $4::text is null
    or concat_ws(' ', invoice_number, seller_name, buyer_name, plate_number) ilike '%' || $4::text || '%'
  )
"#
    )
}

fn etc_invoices_status_counts_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
select
  count(*) filter (where status = 'unsubmitted')::bigint as unsubmitted_count,
  count(*) filter (where status = 'submitted')::bigint as submitted_count
from base
"#
    )
}

fn etc_batch_base_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
, batch_base as (
  select
    *,
    case when status = 'submitted' then current_batch_id else import_batch_id end as batch_id,
    case
      when status = 'submitted' then coalesce(legacy_etc_batch_id, nullif(current_batch_id, ''), import_batch_id)
      else coalesce(legacy_etc_batch_id, import_batch_id)
    end as etc_batch_id,
    coalesce(
      legacy_source_type,
      case when status = 'submitted' then 'normal_oa_draft' else 'etc_import' end
    ) as source_type
  from base
  where (
    (status = 'submitted' and nullif(current_batch_id, '') is not null)
    or (status = 'unsubmitted' and nullif(import_batch_id, '') is not null and nullif(current_batch_id, '') is null)
  )
),
filtered as (
  select *
  from batch_base
  where ($1::text is null or status = $1::text)
    and (
      $2::text is null
      or issue_date like $2::text || '%'
      or coalesce(passage_start_date, '') like $2::text || '%'
      or coalesce(passage_end_date, '') like $2::text || '%'
    )
    and ($3::text is null or coalesce(plate_number, '') ilike '%' || $3::text || '%')
    and (
      $4::text is null
      or concat_ws(' ', batch_id, etc_batch_id, invoice_number, seller_name, buyer_name, plate_number) ilike '%' || $4::text || '%'
    )
),
grouped as (
  select
    batch_id as id,
    max(etc_batch_id) as etc_batch_id,
    status,
    max(source_type) as source_type,
    count(*)::bigint as invoice_count,
    to_char(
      coalesce(sum(
        case
          when replace(total_amount, ',', '') ~ '^-?[0-9]+(\.[0-9]+)?$'
          then replace(total_amount, ',', '')::numeric
          else 0
        end
      ), 0),
      'FM999999999999990.00'
    ) as total_amount,
    to_char(
      coalesce(sum(
        case
          when replace(tax_amount, ',', '') ~ '^-?[0-9]+(\.[0-9]+)?$'
          then replace(tax_amount, ',', '')::numeric
          else 0
        end
      ), 0),
      'FM999999999999990.00'
    ) as tax_amount,
    min(nullif(issue_date, '')) as issue_start_date,
    max(nullif(issue_date, '')) as issue_end_date,
    min(nullif(passage_start_date, '')) as passage_start_date,
    max(nullif(passage_end_date, '')) as passage_end_date,
    max(linked_oa_row_id) as linked_oa_row_id,
    max(linked_oa_case_id) as linked_oa_case_id,
    max(amount_delta) as amount_delta,
    max(note) as note,
    min(created_at) as created_at
  from filtered
  group by batch_id, status
),
plate_grouped as (
  select
    batch_id,
    coalesce(nullif(plate_number, ''), '未识别车牌') as plate_number,
    count(*)::bigint as invoice_count,
    to_char(
      coalesce(sum(
        case
          when replace(total_amount, ',', '') ~ '^-?[0-9]+(\.[0-9]+)?$'
          then replace(total_amount, ',', '')::numeric
          else 0
        end
      ), 0),
      'FM999999999999990.00'
    ) as total_amount
  from filtered
  group by batch_id, coalesce(nullif(plate_number, ''), '未识别车牌')
),
plate_summary as (
  select
    batch_id,
    jsonb_agg(
      jsonb_build_object(
        'plate_number', plate_number,
        'invoice_count', invoice_count,
        'total_amount', total_amount
      )
      order by invoice_count desc, plate_number
    ) as plate_summary
  from plate_grouped
  group by batch_id
)
"#
    )
}

fn etc_batches_sql() -> String {
    format!(
        "{}{}",
        etc_batch_base_sql(),
        r#"
select
  grouped.id,
  grouped.etc_batch_id,
  grouped.status,
  grouped.source_type,
  grouped.invoice_count,
  grouped.total_amount,
  grouped.tax_amount,
  grouped.issue_start_date,
  grouped.issue_end_date,
  grouped.passage_start_date,
  grouped.passage_end_date,
  coalesce(plate_summary.plate_summary, '[]'::jsonb) as plate_summary,
  grouped.linked_oa_row_id,
  grouped.linked_oa_case_id,
  grouped.amount_delta,
  grouped.note,
  grouped.created_at
from grouped
left join plate_summary on plate_summary.batch_id = grouped.id
order by grouped.created_at desc, grouped.id desc
limit $5 offset $6
"#
    )
}

fn etc_batches_total_sql() -> String {
    format!(
        "{}{}",
        etc_batch_base_sql(),
        r#"
select count(*)::bigint as total
from grouped
"#
    )
}

fn etc_batches_status_counts_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
, batch_base as (
  select
    case when status = 'submitted' then current_batch_id else import_batch_id end as batch_id,
    status
  from base
  where (
    (status = 'submitted' and nullif(current_batch_id, '') is not null)
    or (status = 'unsubmitted' and nullif(import_batch_id, '') is not null and nullif(current_batch_id, '') is null)
  )
),
distinct_batches as (
  select distinct batch_id, status
  from batch_base
)
select
  count(*) filter (where status = 'unsubmitted')::bigint as unsubmitted_count,
  count(*) filter (where status = 'submitted')::bigint as submitted_count
from distinct_batches
"#
    )
}

fn etc_batch_detail_summary_sql() -> String {
    format!(
        "{}{}",
        etc_batch_base_sql(),
        r#"
select
  grouped.id,
  grouped.etc_batch_id,
  grouped.status,
  grouped.source_type,
  grouped.invoice_count,
  grouped.total_amount,
  grouped.tax_amount,
  grouped.issue_start_date,
  grouped.issue_end_date,
  grouped.passage_start_date,
  grouped.passage_end_date,
  coalesce(plate_summary.plate_summary, '[]'::jsonb) as plate_summary,
  grouped.linked_oa_row_id,
  grouped.linked_oa_case_id,
  grouped.amount_delta,
  grouped.note,
  grouped.created_at
from grouped
left join plate_summary on plate_summary.batch_id = grouped.id
where grouped.id = $5::text or grouped.etc_batch_id = $5::text
limit 1
"#
    )
}

fn etc_batch_detail_invoices_sql() -> String {
    format!(
        "{}{}",
        ETC_INVOICE_BASE_SQL,
        r#"
, batch_base as (
  select
    *,
    case when status = 'submitted' then current_batch_id else import_batch_id end as batch_id,
    case
      when status = 'submitted' then coalesce(legacy_etc_batch_id, nullif(current_batch_id, ''), import_batch_id)
      else coalesce(legacy_etc_batch_id, import_batch_id)
    end as etc_batch_id
  from base
  where (
    (status = 'submitted' and nullif(current_batch_id, '') is not null)
    or (status = 'unsubmitted' and nullif(import_batch_id, '') is not null and nullif(current_batch_id, '') is null)
  )
)
select
  id,
  invoice_number,
  issue_date,
  passage_start_date,
  passage_end_date,
  plate_number,
  vehicle_type,
  seller_name,
  seller_tax_no,
  buyer_name,
  buyer_tax_no,
  amount_without_tax,
  tax_amount,
  total_amount,
  tax_rate,
  zip_source_name,
  xml_file_path,
  xml_file_hash,
  pdf_file_path,
  pdf_file_hash,
  status,
  import_batch_id,
  import_session_id,
  current_batch_id,
  last_batch_id,
  created_at,
  updated_at,
  false as has_pdf,
  false as has_xml
from batch_base
where batch_id = $1::text or etc_batch_id = $1::text
order by issue_date desc, invoice_number desc
"#
    )
}

const BANK_DETAIL_TRANSACTIONS_SQL: &str = r#"
with normalized as (
  select
    t.id::text as id,
    t.txn_date,
    to_char(coalesce(t.trade_time, t.txn_date::timestamptz) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as trade_time,
    coalesce(t.trade_time, t.txn_date::timestamptz) as event_time,
    coalesce(t.counterparty_name_raw, '') as counterparty_name,
    t.txn_direction as direction,
    t.amount::text as amount,
    t.balance::text as balance,
    t.summary,
    t.remark,
    coalesce(
      nullif(t.raw_payload->>'imported_bank_name', ''),
      nullif(t.raw_payload->>'bank_name', ''),
      '未知银行'
    ) as bank_name,
    coalesce(
      nullif(right(coalesce(t.raw_payload->>'imported_bank_last4', t.raw_payload->>'account_last4', ''), 4), ''),
      nullif(right(regexp_replace(t.account_no, '\D', '', 'g'), 4), ''),
      'unknown'
    ) as account_last4,
    lower(replace(coalesce(
      nullif(t.raw_payload->>'imported_bank_name', ''),
      nullif(t.raw_payload->>'bank_name', ''),
      '未知银行'
    ), ' ', '-')) || ':' || coalesce(
      nullif(right(coalesce(t.raw_payload->>'imported_bank_last4', t.raw_payload->>'account_last4', ''), 4), ''),
      nullif(right(regexp_replace(t.account_no, '\D', '', 'g'), 4), ''),
      'unknown'
    ) as account_key,
    t.raw_payload,
    case
      when c.raw_payload ? 'category_code' then nullif(c.raw_payload->>'category_code', '')
      else c.category_type
    end as manual_category_code,
    coalesce(c.raw_payload->>'category_source', c.raw_payload->>'source', 'manual') as manual_category_source,
    case
      when c.raw_payload->>'category_version' ~ '^[0-9]+$' then (c.raw_payload->>'category_version')::bigint
      when c.raw_payload->>'version' ~ '^[0-9]+$' then (c.raw_payload->>'version')::bigint
      else null
    end as manual_category_version,
    coalesce(c.raw_payload, '{}'::jsonb) as category_raw_payload
  from app.bank_transactions t
  left join lateral (
    select c.*
    from app.bank_transaction_categories c
    where c.bank_transaction_month = t.txn_month
      and c.bank_transaction_id = t.id
      and c.status = 'active'
    order by c.updated_at desc, c.created_at desc, c.id
    limit 1
  ) c on true
),
filtered as (
  select *
  from normalized
  where ($1::text is null or account_key = $1::text)
    and ($2::text is null or txn_date >= $2::date)
    and ($3::text is null or txn_date <= $3::date)
    and (
      $4::text is null
      or concat_ws(
        ' ',
        id,
        trade_time,
        counterparty_name,
        case when direction = 'inflow' then '收' else '支' end,
        amount,
        balance,
        summary,
        raw_payload->>'purpose',
        bank_name,
        account_last4,
        case
          when category_raw_payload ? 'category_code' then nullif(category_raw_payload->>'category_code', '')
          else manual_category_code
        end,
        category_raw_payload->>'category_label'
      ) ilike '%' || $4::text || '%'
    )
)
select
  id,
  trade_time,
  counterparty_name,
  direction,
  amount,
  balance,
  summary,
  remark,
  bank_name,
  account_last4,
  raw_payload,
  manual_category_code,
  manual_category_source,
  manual_category_version,
  category_raw_payload
from filtered
order by event_time desc, id
limit $5 offset $6
"#;

const BANK_DETAIL_CATEGORY_COUNTS_SQL: &str = r#"
with normalized as (
  select
    t.id::text as id,
    t.txn_date,
    to_char(coalesce(t.trade_time, t.txn_date::timestamptz) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as trade_time,
    coalesce(t.counterparty_name_raw, '') as counterparty_name,
    t.txn_direction as direction,
    t.amount::text as amount,
    t.balance::text as balance,
    t.summary,
    t.remark,
    coalesce(
      nullif(t.raw_payload->>'imported_bank_name', ''),
      nullif(t.raw_payload->>'bank_name', ''),
      '未知银行'
    ) as bank_name,
    coalesce(
      nullif(right(coalesce(t.raw_payload->>'imported_bank_last4', t.raw_payload->>'account_last4', ''), 4), ''),
      nullif(right(regexp_replace(t.account_no, '\D', '', 'g'), 4), ''),
      'unknown'
    ) as account_last4,
    lower(replace(coalesce(
      nullif(t.raw_payload->>'imported_bank_name', ''),
      nullif(t.raw_payload->>'bank_name', ''),
      '未知银行'
    ), ' ', '-')) || ':' || coalesce(
      nullif(right(coalesce(t.raw_payload->>'imported_bank_last4', t.raw_payload->>'account_last4', ''), 4), ''),
      nullif(right(regexp_replace(t.account_no, '\D', '', 'g'), 4), ''),
      'unknown'
    ) as account_key,
    t.raw_payload,
    case
      when c.raw_payload ? 'category_code' then nullif(c.raw_payload->>'category_code', '')
      else c.category_type
    end as manual_category_code,
    coalesce(c.raw_payload, '{}'::jsonb) as category_raw_payload
  from app.bank_transactions t
  left join lateral (
    select c.*
    from app.bank_transaction_categories c
    where c.bank_transaction_month = t.txn_month
      and c.bank_transaction_id = t.id
      and c.status = 'active'
    order by c.updated_at desc, c.created_at desc, c.id
    limit 1
  ) c on true
),
filtered as (
  select *
  from normalized
  where ($1::text is null or account_key = $1::text)
    and ($2::text is null or txn_date >= $2::date)
    and ($3::text is null or txn_date <= $3::date)
    and (
      $4::text is null
      or concat_ws(
        ' ',
        id,
        trade_time,
        counterparty_name,
        case when direction = 'inflow' then '收' else '支' end,
        amount,
        balance,
        summary,
        raw_payload->>'purpose',
        bank_name,
        account_last4,
        manual_category_code,
        category_raw_payload->>'category_label'
      ) ilike '%' || $4::text || '%'
    )
)
select coalesce(manual_category_code, 'uncategorized') as category_code, count(*)::bigint as row_count
from filtered
group by coalesce(manual_category_code, 'uncategorized')
order by row_count desc, category_code
"#;

const NO_OA_BATCH_DETAIL_SQL: &str = r#"
select
  b.id::text as batch_id,
  to_char(b.scope_month, 'YYYY-MM') as scope_month,
  b.status,
  cardinality(b.bank_transaction_ids)::bigint as row_count,
  b.total_amount::text as total_amount,
  to_char(b.submitted_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as submitted_at,
  to_char(b.cancelled_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as cancelled_at,
  b.raw_payload,
  coalesce(b.row_version, 1)::bigint as row_version,
  coalesce(b.raw_payload->'tag_counts', '{}'::jsonb) as tag_counts,
  coalesce(b.raw_payload->'direction_counts', '{}'::jsonb) as direction_counts
from app.no_oa_bank_batches b
where b.id = $1
"#;

const NO_OA_BATCH_DETAIL_ROWS_SQL: &str = r#"
select
  t.id::text as transaction_id,
  to_char(t.txn_date, 'YYYY-MM-DD') as txn_date,
  to_char(t.trade_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as trade_time,
  t.counterparty_name_raw as counterparty_name,
  t.txn_direction as direction,
  t.amount::text as amount,
  t.summary,
  t.remark,
  t.raw_payload,
  c.category_type as category_code,
  c.raw_payload->>'category_label' as category_label,
  c.raw_payload->>'category_source' as category_source
from app.no_oa_bank_batches b
join app.bank_transactions t
  on t.txn_month = b.scope_month
 and t.id = any(b.bank_transaction_ids)
left join app.bank_transaction_categories c
  on c.bank_transaction_month = t.txn_month
 and c.bank_transaction_id = t.id
 and c.status = 'active'
where b.id = $1
order by t.txn_date desc, t.trade_time desc nulls last, t.id
"#;

const TAX_OFFSET_READ_MODEL_SQL: &str = r#"
select
  scope_key,
  'month'::text as scope_type,
  to_char(scope_month, 'YYYY-MM-DD') as scope_month,
  schema_version,
  payload,
  source_scope_keys,
  source_versions,
  cache_status,
  to_char(generated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as generated_at,
  stale,
  stale_reason,
  rebuild_task_id::text as rebuild_task_id,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.tax_offset_read_models
where scope_key = $1
"#;

const COST_STATISTICS_READ_MODEL_SQL: &str = r#"
select
  scope_key,
  scope_type,
  to_char(scope_month, 'YYYY-MM-DD') as scope_month,
  schema_version,
  payload,
  source_scope_keys,
  source_versions,
  cache_status,
  to_char(generated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as generated_at,
  stale,
  stale_reason,
  rebuild_task_id::text as rebuild_task_id,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.cost_statistics_read_models
where scope_key = $1
"#;

const OA_SYNC_STATUS_SQL: &str = r#"
with latest_run as (
  select *
  from app.oa_sync_runs
  order by started_at desc, id desc
  limit 1
),
latest_watermark as (
  select *
  from app.oa_sync_watermarks
  order by updated_at desc, source_system, scope
  limit 1
)
select
  latest_run.status,
  latest_run.id::text as last_run_id,
  to_char(latest_run.started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as last_started_at,
  to_char(latest_run.finished_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as last_finished_at,
  to_char(latest_watermark.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as last_synced_at,
  coalesce(latest_run.source_system, latest_watermark.source_system) as source_system,
  coalesce(latest_run.scope, latest_watermark.scope) as scope,
  latest_run.processed_count::bigint as processed_count,
  latest_run.success_count::bigint as success_count,
  latest_run.failed_count::bigint as failed_count,
  latest_run.error_message
from (select 1) anchor
left join latest_run on true
left join latest_watermark on true
"#;

const WORKBENCH_STALE_SCOPES_SQL: &str = r#"
select
  case
    when scope_month is null then scope_key
    else to_char(scope_month, 'YYYY-MM')
  end as scope,
  stale_reason,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.workbench_snapshots
where stale
order by scope_month nulls last, scope_key
"#;

fn row_to_no_oa_batch(
    row: sqlx::postgres::PgRow,
) -> Result<NoOaBatchRow, BusinessReadRepositoryError> {
    Ok(NoOaBatchRow {
        batch_id: row.try_get("batch_id")?,
        scope_month: row.try_get("scope_month")?,
        status: row.try_get("status")?,
        row_count: row.try_get("row_count")?,
        total_amount: row.try_get("total_amount")?,
        submitted_at: row.try_get("submitted_at")?,
        cancelled_at: row.try_get("cancelled_at")?,
        raw_payload: row.try_get("raw_payload")?,
        row_version: row.try_get("row_version")?,
        tag_counts: row.try_get("tag_counts")?,
        direction_counts: row.try_get("direction_counts")?,
    })
}

fn row_to_workbench_stale_scope(
    row: sqlx::postgres::PgRow,
) -> Result<WorkbenchStaleScopeRow, BusinessReadRepositoryError> {
    Ok(WorkbenchStaleScopeRow {
        scope: row.try_get("scope")?,
        stale_reason: row.try_get("stale_reason")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn row_to_bank_detail_account(
    row: sqlx::postgres::PgRow,
) -> Result<BankDetailAccountRow, BusinessReadRepositoryError> {
    Ok(BankDetailAccountRow {
        account_key: row.try_get("account_key")?,
        bank_name: row.try_get("bank_name")?,
        account_last4: row.try_get("account_last4")?,
        latest_balance: row.try_get("latest_balance")?,
        latest_balance_at: row.try_get("latest_balance_at")?,
        transaction_count: row.try_get("transaction_count")?,
    })
}

fn row_to_bank_detail_transaction(
    row: sqlx::postgres::PgRow,
) -> Result<BankDetailTransactionRow, BusinessReadRepositoryError> {
    Ok(BankDetailTransactionRow {
        id: row.try_get("id")?,
        trade_time: row.try_get("trade_time")?,
        counterparty_name: row.try_get("counterparty_name")?,
        direction: row.try_get("direction")?,
        amount: row.try_get("amount")?,
        balance: row.try_get("balance")?,
        summary: row.try_get("summary")?,
        remark: row.try_get("remark")?,
        bank_name: row.try_get("bank_name")?,
        account_last4: row.try_get("account_last4")?,
        raw_payload: row.try_get("raw_payload")?,
        manual_category_code: row.try_get("manual_category_code")?,
        manual_category_source: row.try_get("manual_category_source")?,
        manual_category_version: row.try_get("manual_category_version")?,
        category_raw_payload: row.try_get("category_raw_payload")?,
    })
}

fn row_to_no_oa_detail(
    row: sqlx::postgres::PgRow,
) -> Result<NoOaDetailRow, BusinessReadRepositoryError> {
    Ok(NoOaDetailRow {
        transaction_id: row.try_get("transaction_id")?,
        txn_date: row.try_get("txn_date")?,
        trade_time: row.try_get("trade_time")?,
        counterparty_name: row.try_get("counterparty_name")?,
        direction: row.try_get("direction")?,
        amount: row.try_get("amount")?,
        summary: row.try_get("summary")?,
        remark: row.try_get("remark")?,
        raw_payload: row.try_get("raw_payload")?,
        category_code: row.try_get("category_code")?,
        category_label: row.try_get("category_label")?,
        category_source: row.try_get("category_source")?,
    })
}

fn row_to_tax_certified_import(
    row: sqlx::postgres::PgRow,
) -> Result<TaxCertifiedImportRow, BusinessReadRepositoryError> {
    Ok(TaxCertifiedImportRow {
        id: row.try_get("id")?,
        unique_key: row.try_get("unique_key")?,
        month: row.try_get("month")?,
        source_file_name: row.try_get("source_file_name")?,
        source_row_number: row.try_get("source_row_number")?,
        taxpayer_tax_no: row.try_get("taxpayer_tax_no")?,
        taxpayer_name: row.try_get("taxpayer_name")?,
        digital_invoice_no: row.try_get("digital_invoice_no")?,
        invoice_code: row.try_get("invoice_code")?,
        invoice_no: row.try_get("invoice_no")?,
        issue_date: row.try_get("issue_date")?,
        seller_tax_no: row.try_get("seller_tax_no")?,
        seller_name: row.try_get("seller_name")?,
        amount: row.try_get("amount")?,
        tax_amount: row.try_get("tax_amount")?,
        deductible_tax_amount: row.try_get("deductible_tax_amount")?,
        selection_status: row.try_get("selection_status")?,
        invoice_status: row.try_get("invoice_status")?,
        selection_time: row.try_get("selection_time")?,
        invoice_source: row.try_get("invoice_source")?,
        invoice_kind: row.try_get("invoice_kind")?,
        risk_level: row.try_get("risk_level")?,
        imported_at: row.try_get("imported_at")?,
    })
}

fn row_to_etc_invoice(
    row: sqlx::postgres::PgRow,
) -> Result<EtcInvoiceRow, BusinessReadRepositoryError> {
    Ok(EtcInvoiceRow {
        id: row.try_get("id")?,
        invoice_number: row.try_get("invoice_number")?,
        issue_date: row.try_get("issue_date")?,
        passage_start_date: row.try_get("passage_start_date")?,
        passage_end_date: row.try_get("passage_end_date")?,
        plate_number: row.try_get("plate_number")?,
        vehicle_type: row.try_get("vehicle_type")?,
        seller_name: row.try_get("seller_name")?,
        seller_tax_no: row.try_get("seller_tax_no")?,
        buyer_name: row.try_get("buyer_name")?,
        buyer_tax_no: row.try_get("buyer_tax_no")?,
        amount_without_tax: row.try_get("amount_without_tax")?,
        tax_amount: row.try_get("tax_amount")?,
        total_amount: row.try_get("total_amount")?,
        tax_rate: row.try_get("tax_rate")?,
        zip_source_name: row.try_get("zip_source_name")?,
        xml_file_path: row.try_get("xml_file_path")?,
        xml_file_hash: row.try_get("xml_file_hash")?,
        pdf_file_path: row.try_get("pdf_file_path")?,
        pdf_file_hash: row.try_get("pdf_file_hash")?,
        status: row.try_get("status")?,
        import_batch_id: row.try_get("import_batch_id")?,
        import_session_id: row.try_get("import_session_id")?,
        current_batch_id: row.try_get("current_batch_id")?,
        last_batch_id: row.try_get("last_batch_id")?,
        created_at: row.try_get("created_at")?,
        updated_at: row.try_get("updated_at")?,
        has_pdf: row.try_get("has_pdf")?,
        has_xml: row.try_get("has_xml")?,
    })
}

fn row_to_etc_batch(
    row: sqlx::postgres::PgRow,
) -> Result<EtcBatchRow, BusinessReadRepositoryError> {
    let plate_summary_value: Value = row.try_get("plate_summary")?;
    let plate_summary = serde_json::from_value(plate_summary_value).map_err(|error| {
        BusinessReadRepositoryError::Database(sqlx::Error::ColumnDecode {
            index: "plate_summary".to_owned(),
            source: Box::new(error),
        })
    })?;
    Ok(EtcBatchRow {
        id: row.try_get("id")?,
        etc_batch_id: row.try_get("etc_batch_id")?,
        status: row.try_get("status")?,
        source_type: row.try_get("source_type")?,
        invoice_count: row.try_get("invoice_count")?,
        total_amount: row.try_get("total_amount")?,
        tax_amount: row.try_get("tax_amount")?,
        issue_start_date: row.try_get("issue_start_date")?,
        issue_end_date: row.try_get("issue_end_date")?,
        passage_start_date: row.try_get("passage_start_date")?,
        passage_end_date: row.try_get("passage_end_date")?,
        plate_summary,
        linked_oa_row_id: row.try_get("linked_oa_row_id")?,
        linked_oa_case_id: row.try_get("linked_oa_case_id")?,
        amount_delta: row.try_get("amount_delta")?,
        note: row.try_get("note")?,
        created_at: row.try_get("created_at")?,
    })
}

fn row_to_read_model_payload(
    row: sqlx::postgres::PgRow,
) -> Result<ReadModelPayloadRow, BusinessReadRepositoryError> {
    Ok(ReadModelPayloadRow {
        scope_key: row.try_get("scope_key")?,
        scope_type: row.try_get("scope_type")?,
        scope_month: row.try_get("scope_month")?,
        schema_version: row.try_get("schema_version")?,
        payload: row.try_get("payload")?,
        source_scope_keys: row.try_get("source_scope_keys")?,
        source_versions: row.try_get("source_versions")?,
        cache_status: row.try_get("cache_status")?,
        generated_at: row.try_get("generated_at")?,
        stale: row.try_get("stale")?,
        stale_reason: row.try_get("stale_reason")?,
        rebuild_task_id: row.try_get("rebuild_task_id")?,
        updated_at: row.try_get("updated_at")?,
    })
}
