use async_trait::async_trait;
use serde_json::Value;
use sqlx::{PgPool, Row};

use crate::services::turnover_ledger::{
    TurnoverBankFactRow, TurnoverLedgerRepository, TurnoverLedgerRepositoryError,
};

#[derive(Clone)]
pub struct SqlxTurnoverLedgerRepository {
    pool: PgPool,
}

impl SqlxTurnoverLedgerRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl TurnoverLedgerRepository for SqlxTurnoverLedgerRepository {
    async fn list_turnover_bank_rows(
        &self,
    ) -> Result<Vec<TurnoverBankFactRow>, TurnoverLedgerRepositoryError> {
        sqlx::query(TURNOVER_BANK_ROWS_SQL)
            .fetch_all(&self.pool)
            .await?
            .into_iter()
            .map(row_to_turnover_bank_fact)
            .collect()
    }
}

const TURNOVER_BANK_ROWS_SQL: &str = r#"
select
  t.id::text as id,
  coalesce(
    to_char(coalesce(t.trade_time, t.txn_date::timestamptz) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    to_char(t.txn_date, 'YYYY-MM-DD')
  ) as transaction_at,
  t.txn_direction,
  t.amount::text as amount,
  coalesce(nullif(t.counterparty_name_raw, ''), t.counterparty_name_normalized, '') as counterparty_name,
  t.account_no,
  coalesce(nullif(t.raw_payload->>'imported_bank_name', ''), nullif(t.raw_payload->>'bank_name', ''), '未知银行') as bank_name,
  t.summary,
  t.remark,
  nullif(t.raw_payload->>'purpose', '') as purpose,
  coalesce(t.bank_text_fields, '[]'::jsonb) as bank_text_fields,
  coalesce(nullif(c.raw_payload->>'category_code', ''), c.category_type, '') as category_code,
  coalesce(nullif(c.raw_payload->>'category_label', ''), c.category_type, '') as category_label
from app.bank_transactions t
join lateral (
  select c.*
  from app.bank_transaction_categories c
  where c.bank_transaction_month = t.txn_month
    and c.bank_transaction_id = t.id
    and c.status = 'active'
  order by c.updated_at desc, c.created_at desc, c.id
  limit 1
) c on true
where coalesce(nullif(c.raw_payload->>'category_code', ''), c.category_type, '') in (
  'borrow_in_personal_pending_repayment',
  'borrow_in_personal_repaid',
  'borrow_in_company_pending_repayment',
  'borrow_in_company_repaid',
  'borrow_in_bank_pending_repayment',
  'borrow_in_bank_repaid',
  'borrow_out_personal_lent',
  'borrow_out_personal_pending_collection',
  'borrow_out_company_lent',
  'borrow_out_company_pending_collection',
  'borrow_out_goods_lent',
  'borrow_out_goods_pending_collection',
  'business_warranty_pending_collection',
  'business_bid_bond_pending_collection',
  'business_performance_bond_pending_collection',
  'business_invoiced_pending_collection'
)
order by coalesce(t.trade_time, t.txn_date::timestamptz) desc, t.id
"#;

fn row_to_turnover_bank_fact(
    row: sqlx::postgres::PgRow,
) -> Result<TurnoverBankFactRow, TurnoverLedgerRepositoryError> {
    let bank_text_fields: Value = row.try_get("bank_text_fields")?;
    Ok(TurnoverBankFactRow {
        id: row.try_get("id")?,
        transaction_at: row.try_get("transaction_at")?,
        txn_direction: row.try_get("txn_direction")?,
        amount: row.try_get("amount")?,
        counterparty_name: row.try_get("counterparty_name")?,
        account_no: row.try_get("account_no")?,
        bank_name: row.try_get("bank_name")?,
        summary: row.try_get("summary")?,
        remark: row.try_get("remark")?,
        purpose: row.try_get("purpose")?,
        bank_text_fields: bank_text_values(&bank_text_fields),
        category_code: row.try_get("category_code")?,
        category_label: row.try_get("category_label")?,
    })
}

fn bank_text_values(value: &Value) -> Vec<String> {
    let Some(items) = value.as_array() else {
        return Vec::new();
    };
    items
        .iter()
        .filter_map(|item| {
            if let Some(text) = item.as_str() {
                return Some(text.trim().to_owned()).filter(|text| !text.is_empty());
            }
            item.as_object()
                .and_then(|object| object.get("value"))
                .and_then(Value::as_str)
                .map(str::trim)
                .map(ToOwned::to_owned)
                .filter(|text| !text.is_empty())
        })
        .collect()
}
