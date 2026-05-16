use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha1::{Digest, Sha1};
use std::collections::{BTreeMap, BTreeSet};

const FAMILIES: [(&str, &str); 4] = [
    ("personal", "个人往来"),
    ("company", "公司往来"),
    ("bank", "银行往来"),
    ("business", "业务往来"),
];
const TURNOVER_EXPORT_COLUMNS: [&str; 25] = [
    "序号",
    "行类型",
    "源银行流水ID",
    "流水方向",
    "流水金额",
    "往来大类",
    "对方户名",
    "待还款金额",
    "待收款金额",
    "余额",
    "借款金额",
    "借款日",
    "还款金额",
    "还款日",
    "对方开户机构",
    "还款备注",
    "利率类型",
    "利率值",
    "已还利息额",
    "借款天数",
    "应还利息",
    "还利息日期",
    "还利息方式",
    "备注",
    "关系状态",
];

#[derive(Debug, thiserror::Error)]
pub enum TurnoverLedgerServiceError {
    #[error("invalid request: {message}")]
    InvalidRequest {
        code: &'static str,
        message: &'static str,
    },
    #[error("unknown relation id")]
    UnknownRelationId,
    #[error(transparent)]
    Repository(#[from] TurnoverLedgerRepositoryError),
}

#[derive(Debug, thiserror::Error)]
pub enum TurnoverLedgerRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait TurnoverLedgerRepository: Send + Sync {
    async fn list_turnover_bank_rows(
        &self,
    ) -> Result<Vec<TurnoverBankFactRow>, TurnoverLedgerRepositoryError>;
}

pub struct TurnoverLedgerService<R> {
    repository: R,
}

impl<R> TurnoverLedgerService<R>
where
    R: TurnoverLedgerRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn list_ledger(
        &self,
        query: TurnoverLedgerQuery,
    ) -> Result<TurnoverLedgerResponse, TurnoverLedgerServiceError> {
        let page = turnover_page(query.page.as_deref())?;
        let page_size = turnover_page_size(query.page_size.as_deref())?;
        let rows = self.repository.list_turnover_bank_rows().await?;
        let relations = build_relations(&rows);
        let rows_by_id = rows
            .iter()
            .map(|row| (row.id.clone(), row.clone()))
            .collect::<BTreeMap<_, _>>();
        let all_rows = relations
            .iter()
            .filter_map(|relation| flat_row_payload(relation, &rows_by_id))
            .collect::<Vec<_>>();
        let filtered_rows = apply_filters(
            all_rows.clone(),
            query.family.as_deref(),
            query.status.as_deref(),
        );
        let filtered_summary = summary(&filtered_rows);
        let mut sorted_rows = filtered_rows;
        sorted_rows.sort_by(|a, b| {
            (
                b.first_transaction_at.as_deref().unwrap_or_default(),
                b.relation_id.as_str(),
            )
                .cmp(&(
                    a.first_transaction_at.as_deref().unwrap_or_default(),
                    a.relation_id.as_str(),
                ))
        });
        let total = sorted_rows.len() as i64;
        let start = ((page - 1) * page_size) as usize;
        let end = start.saturating_add(page_size as usize);
        let page_rows = sorted_rows
            .into_iter()
            .skip(start)
            .take(end.saturating_sub(start))
            .collect::<Vec<_>>();
        Ok(TurnoverLedgerResponse {
            summary: filtered_summary,
            family_summaries: family_summaries(&all_rows),
            rows: page_rows,
            pagination: TurnoverLedgerPagination {
                page,
                page_size,
                total,
            },
            filters: TurnoverLedgerFilters {
                family: normalize_family(query.family.as_deref()),
                status: normalize_status(query.status.as_deref()),
            },
        })
    }

    pub async fn list_grouped_ledger(
        &self,
        query: TurnoverLedgerQuery,
    ) -> Result<TurnoverLedgerGroupedResponse, TurnoverLedgerServiceError> {
        let page = turnover_page(query.page.as_deref())?;
        let page_size = turnover_page_size(query.page_size.as_deref())?;
        let rows = self.repository.list_turnover_bank_rows().await?;
        let relations = build_relations(&rows);
        let rows_by_id = rows
            .iter()
            .map(|row| (row.id.clone(), row.clone()))
            .collect::<BTreeMap<_, _>>();
        let items = relations
            .iter()
            .filter_map(|relation| grouped_item(relation, &rows_by_id))
            .collect::<Vec<_>>();
        let all_legacy_rows = items
            .iter()
            .map(|item| item.legacy.clone())
            .collect::<Vec<_>>();
        let filtered_items =
            apply_item_filters(items, query.family.as_deref(), query.status.as_deref());
        let legacy_rows = filtered_items
            .iter()
            .map(|item| item.legacy.clone())
            .collect::<Vec<_>>();
        let mut groups = group_items(filtered_items);
        groups.sort_by(|a, b| b.group_id.cmp(&a.group_id));
        let total = groups.len() as i64;
        let start = ((page - 1) * page_size) as usize;
        let page_groups = groups
            .into_iter()
            .skip(start)
            .take(page_size as usize)
            .collect::<Vec<_>>();
        Ok(TurnoverLedgerGroupedResponse {
            summary: summary(&legacy_rows),
            family_summaries: family_summaries(&all_legacy_rows),
            groups: page_groups,
            pagination: TurnoverLedgerPagination {
                page,
                page_size,
                total,
            },
            filters: TurnoverLedgerFilters {
                family: normalize_family(query.family.as_deref()),
                status: normalize_status(query.status.as_deref()),
            },
        })
    }

    pub async fn export_preview(
        &self,
        query: TurnoverLedgerQuery,
    ) -> Result<Value, TurnoverLedgerServiceError> {
        let family = normalize_family(query.family.as_deref());
        let limit = turnover_preview_limit(query.limit.as_deref())?;
        let grouped = self
            .list_grouped_ledger(TurnoverLedgerQuery {
                view: Some("grouped".to_owned()),
                family: Some(family.clone()),
                status: None,
                page: Some("1".to_owned()),
                page_size: Some(limit.max(200).to_string()),
                limit: None,
            })
            .await?;
        let rows = turnover_export_rows(&grouped, &family);
        let preview_rows = rows
            .iter()
            .take(limit as usize)
            .cloned()
            .collect::<Vec<_>>();
        Ok(json!({
            "columns": TURNOVER_EXPORT_COLUMNS,
            "rows": preview_rows,
            "totals": turnover_export_totals(&rows),
            "pagination": {
                "preview_count": preview_rows.len(),
                "total": rows.len(),
                "limit": limit,
            },
            "filters": {"family": family},
        }))
    }

    pub async fn get_relation_detail(
        &self,
        relation_id: &str,
    ) -> Result<Value, TurnoverLedgerServiceError> {
        let normalized_relation_id = relation_id.trim();
        if normalized_relation_id.is_empty() {
            return Err(TurnoverLedgerServiceError::UnknownRelationId);
        }
        let rows = self.repository.list_turnover_bank_rows().await?;
        let relations = build_relations(&rows);
        let rows_by_id = rows
            .iter()
            .map(|row| (row.id.clone(), row.clone()))
            .collect::<BTreeMap<_, _>>();
        let Some(relation) = relations
            .iter()
            .find(|relation| relation.relation_id == normalized_relation_id)
        else {
            return Err(TurnoverLedgerServiceError::UnknownRelationId);
        };
        let row = flat_row_payload(relation, &rows_by_id);
        let bank_rows = relation
            .bank_row_ids
            .iter()
            .filter_map(|row_id| rows_by_id.get(row_id))
            .map(turnover_bank_detail_row)
            .collect::<Vec<_>>();
        Ok(json!({
            "relation": relation_detail_payload(relation),
            "row": row,
            "bank_rows": bank_rows,
            "audit_history": [],
        }))
    }
}

#[derive(Clone, Debug)]
pub struct TurnoverBankFactRow {
    pub id: String,
    pub transaction_at: Option<String>,
    pub txn_direction: String,
    pub amount: String,
    pub counterparty_name: String,
    pub account_no: String,
    pub bank_name: String,
    pub summary: Option<String>,
    pub remark: Option<String>,
    pub purpose: Option<String>,
    pub bank_text_fields: Vec<String>,
    pub category_code: String,
    pub category_label: String,
}

#[derive(Debug, Deserialize)]
pub struct TurnoverLedgerQuery {
    pub view: Option<String>,
    pub family: Option<String>,
    pub status: Option<String>,
    pub page: Option<String>,
    pub page_size: Option<String>,
    pub limit: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerResponse {
    pub summary: TurnoverLedgerSummary,
    pub family_summaries: Vec<TurnoverLedgerFamilySummary>,
    pub rows: Vec<TurnoverLedgerRow>,
    pub pagination: TurnoverLedgerPagination,
    pub filters: TurnoverLedgerFilters,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerGroupedResponse {
    pub summary: TurnoverLedgerSummary,
    pub family_summaries: Vec<TurnoverLedgerFamilySummary>,
    pub groups: Vec<TurnoverLedgerGroup>,
    pub pagination: TurnoverLedgerPagination,
    pub filters: TurnoverLedgerFilters,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerSummary {
    pub pending_repayment_amount: String,
    pub repaid_amount: String,
    pub pending_collection_amount: String,
    pub collected_amount: String,
    pub closed_amount: String,
    pub suggested_count: i64,
    pub conflict_count: i64,
    pub row_count: i64,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerFamilySummary {
    pub family: String,
    pub label: String,
    pub pending_amount: String,
    pub closed_amount: String,
    pub row_count: i64,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerPagination {
    pub page: i64,
    pub page_size: i64,
    pub total: i64,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerFilters {
    pub family: String,
    pub status: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerChip {
    pub label: String,
    pub tone: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerRow {
    pub relation_id: String,
    pub status: String,
    pub status_label: String,
    pub row_tone: String,
    pub chips: Vec<TurnoverLedgerChip>,
    pub family: String,
    pub family_label: String,
    pub counterparty_name: String,
    pub principal_amount: String,
    pub settled_amount: String,
    pub balance_amount: String,
    pub first_transaction_at: Option<String>,
    pub last_settlement_at: Option<String>,
    pub bank_account_labels: Vec<String>,
    pub summary_text: String,
    pub annual_interest_rate: Option<String>,
    pub loan_days: Option<i64>,
    pub accrued_interest: Option<String>,
    pub sync_to_workbench: bool,
    pub bank_row_ids: Vec<String>,
    pub category_codes: Vec<String>,
    pub business_type: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverGroupedRow {
    pub row_kind: String,
    pub display_level: Option<String>,
    pub relation_id: String,
    pub lot_id: String,
    pub flow_id: String,
    pub parent_relation_id: String,
    pub source_bank_row_id: String,
    pub principal_bank_row_id: String,
    pub settlement_bank_row_ids: Vec<String>,
    pub status: String,
    pub status_label: String,
    pub row_tone: String,
    pub transaction_at: Option<String>,
    pub flow_direction: String,
    pub flow_amount: String,
    pub borrow_amount: String,
    pub borrow_date: Option<String>,
    pub borrow_direction: String,
    pub repayment_amount: String,
    pub allocated_repayment_amount: String,
    pub repayment_date: Option<String>,
    pub repayment_direction: String,
    pub balance_amount: String,
    pub business_type: String,
    pub category_label: String,
    pub counterparty_bank_name: String,
    pub summary_text: String,
    pub allocation_status: String,
    pub allocated_lot_ids: Vec<String>,
    pub repayment_remark: String,
    pub interest_rate_type: String,
    pub interest_rate_value: String,
    pub interest_paid_amount: String,
    pub loan_days: Option<i64>,
    pub accrued_interest: String,
    pub interest_paid_date: Option<String>,
    pub interest_payment_method: String,
    pub note: String,
    pub bank_row_ids: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct TurnoverLedgerGroup {
    pub group_id: String,
    pub counterparty_name: String,
    pub family: String,
    pub family_label: String,
    pub pending_direction: String,
    pub pending_direction_label: String,
    pub pending_amount: String,
    pub pending_repayment_amount: String,
    pub pending_collection_amount: String,
    pub closed_amount: String,
    pub row_span: i64,
    pub group_tone: String,
    pub summary_row: TurnoverGroupedRow,
    pub flow_rows: Vec<TurnoverGroupedRow>,
    pub allocation_lots: Vec<TurnoverGroupedRow>,
    pub lot_rows: Vec<TurnoverGroupedRow>,
}

#[derive(Clone)]
struct CategoryRule {
    family: &'static str,
    business_type: &'static str,
    side: &'static str,
    expected_direction: Option<&'static str>,
}

#[derive(Clone)]
struct PreparedRow {
    id: String,
    category_code: String,
    family: String,
    business_type: String,
    side: String,
    direction: Option<String>,
    expected_direction: Option<String>,
    amount_cents: i64,
    counterparty_name: String,
    normalized_counterparty_name: String,
    transaction_at: Option<String>,
}

#[derive(Clone)]
struct TurnoverRelation {
    relation_id: String,
    status: String,
    family: String,
    business_type: String,
    category_codes: Vec<String>,
    counterparty_name: String,
    principal_row_ids: Vec<String>,
    settlement_row_ids: Vec<String>,
    bank_row_ids: Vec<String>,
    principal_amount: String,
    settled_amount: String,
    balance_amount: String,
    first_transaction_at: Option<String>,
    last_settlement_at: Option<String>,
    source: String,
    sync_to_workbench: bool,
    evidence_reason: String,
}

#[derive(Clone)]
struct GroupedItem {
    legacy: TurnoverLedgerRow,
    row: TurnoverGroupedRow,
    flow_rows: Vec<TurnoverGroupedRow>,
    family: String,
    status: String,
    counterparty_name: String,
    business_type: String,
    balance_cents: i64,
}

fn build_relations(rows: &[TurnoverBankFactRow]) -> Vec<TurnoverRelation> {
    let mut valid_rows = Vec::new();
    let mut conflict_rows = Vec::new();
    for row in rows {
        let Some(prepared) = prepare_row(row) else {
            continue;
        };
        if direction_is_valid(&prepared) {
            valid_rows.push(prepared);
        } else {
            conflict_rows.push(prepared);
        }
    }

    let mut relations = conflict_rows
        .into_iter()
        .map(conflict_relation)
        .collect::<Vec<_>>();
    let mut grouped: BTreeMap<(String, String, String, String), Vec<PreparedRow>> = BTreeMap::new();
    for row in valid_rows {
        let discriminator = if row.business_type == "business_receivable" {
            row.category_code.clone()
        } else {
            String::new()
        };
        grouped
            .entry((
                row.business_type.clone(),
                row.family.clone(),
                row.normalized_counterparty_name.clone(),
                discriminator,
            ))
            .or_default()
            .push(row);
    }
    relations.extend(grouped.into_values().filter_map(auto_relation));
    relations
}

fn prepare_row(row: &TurnoverBankFactRow) -> Option<PreparedRow> {
    let rule = category_rule(&row.category_code)?;
    let direction = match row.txn_direction.as_str() {
        "inflow" => Some("inflow".to_owned()),
        "outflow" => Some("outflow".to_owned()),
        _ => None,
    };
    let mut side = rule.side.to_owned();
    if rule.side == "by_direction" {
        side = match direction.as_deref() {
            Some("outflow") => "principal".to_owned(),
            Some("inflow") => "settlement".to_owned(),
            _ => "unknown".to_owned(),
        };
    }
    Some(PreparedRow {
        id: row.id.clone(),
        category_code: row.category_code.clone(),
        family: rule.family.to_owned(),
        business_type: rule.business_type.to_owned(),
        side,
        direction,
        expected_direction: rule.expected_direction.map(ToOwned::to_owned),
        amount_cents: parse_money_cents(&row.amount).abs(),
        counterparty_name: if row.counterparty_name.trim().is_empty() {
            "UNKNOWN".to_owned()
        } else {
            row.counterparty_name.trim().to_owned()
        },
        normalized_counterparty_name: normalize_counterparty(&row.counterparty_name),
        transaction_at: row.transaction_at.clone(),
    })
}

fn category_rule(code: &str) -> Option<CategoryRule> {
    let code = code.trim();
    for family in ["personal", "company", "bank"] {
        if code == format!("borrow_in_{family}_pending_repayment") {
            return Some(CategoryRule {
                family,
                business_type: "borrow_in",
                side: "principal",
                expected_direction: Some("inflow"),
            });
        }
        if code == format!("borrow_in_{family}_repaid") {
            return Some(CategoryRule {
                family,
                business_type: "borrow_in",
                side: "settlement",
                expected_direction: Some("outflow"),
            });
        }
    }
    for (family, code_family) in [
        ("personal", "personal"),
        ("company", "company"),
        ("business", "goods"),
    ] {
        if code == format!("borrow_out_{code_family}_lent") {
            return Some(CategoryRule {
                family,
                business_type: "borrow_out",
                side: "principal",
                expected_direction: Some("outflow"),
            });
        }
        if code == format!("borrow_out_{code_family}_pending_collection") {
            return Some(CategoryRule {
                family,
                business_type: "borrow_out",
                side: "settlement",
                expected_direction: Some("inflow"),
            });
        }
    }
    if matches!(
        code,
        "business_warranty_pending_collection"
            | "business_bid_bond_pending_collection"
            | "business_performance_bond_pending_collection"
            | "business_invoiced_pending_collection"
    ) {
        return Some(CategoryRule {
            family: "business",
            business_type: "business_receivable",
            side: "by_direction",
            expected_direction: None,
        });
    }
    None
}

fn direction_is_valid(row: &PreparedRow) -> bool {
    if row.amount_cents <= 0 {
        return false;
    }
    match row.expected_direction.as_deref() {
        Some(expected) => row.direction.as_deref() == Some(expected),
        None => matches!(row.direction.as_deref(), Some("inflow" | "outflow")),
    }
}

fn conflict_relation(row: PreparedRow) -> TurnoverRelation {
    let principal = if row.side == "principal" {
        row.amount_cents
    } else {
        0
    };
    let settled = if row.side == "settlement" {
        row.amount_cents
    } else {
        0
    };
    relation_from_parts(
        vec![row],
        principal,
        settled,
        "conflict",
        "invalid_direction",
    )
}

fn auto_relation(rows: Vec<PreparedRow>) -> Option<TurnoverRelation> {
    let principal = rows
        .iter()
        .filter(|row| row.side == "principal")
        .map(|row| row.amount_cents)
        .sum::<i64>();
    let settled = rows
        .iter()
        .filter(|row| row.side == "settlement")
        .map(|row| row.amount_cents)
        .sum::<i64>();
    if principal == 0 && settled == 0 {
        return None;
    }
    let principal_count = rows.iter().filter(|row| row.side == "principal").count();
    let settlement_count = rows.iter().filter(|row| row.side == "settlement").count();
    let reason = if principal - settled == 0
        && principal_count >= 1
        && settlement_count >= 1
        && (principal_count == 1 || settlement_count == 1)
    {
        "unique_exact_fifo_closed"
    } else if principal - settled == 0 {
        "multiple_solutions"
    } else {
        "partial_closed"
    };
    let status = if reason == "unique_exact_fifo_closed" {
        "deterministic"
    } else {
        "suggested"
    };
    Some(relation_from_parts(
        rows, principal, settled, status, reason,
    ))
}

fn relation_from_parts(
    rows: Vec<PreparedRow>,
    principal: i64,
    settled: i64,
    status: &str,
    evidence_reason: &str,
) -> TurnoverRelation {
    let family = rows
        .first()
        .map(|row| row.family.clone())
        .unwrap_or_default();
    let business_type = rows
        .first()
        .map(|row| row.business_type.clone())
        .unwrap_or_default();
    let counterparty_name = rows
        .first()
        .map(|row| row.counterparty_name.clone())
        .unwrap_or_default();
    let mut bank_row_ids = rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>();
    let principal_row_ids = rows
        .iter()
        .filter(|row| row.side == "principal")
        .map(|row| row.id.clone())
        .collect::<Vec<_>>();
    let settlement_row_ids = rows
        .iter()
        .filter(|row| row.side == "settlement")
        .map(|row| row.id.clone())
        .collect::<Vec<_>>();
    let category_codes = rows
        .iter()
        .map(|row| row.category_code.clone())
        .collect::<BTreeSet<_>>()
        .into_iter()
        .collect::<Vec<_>>();
    bank_row_ids.sort();
    let first_transaction_at = rows
        .iter()
        .filter_map(|row| row.transaction_at.clone())
        .min();
    let last_settlement_at = rows
        .iter()
        .filter(|row| row.side == "settlement")
        .filter_map(|row| row.transaction_at.clone())
        .max();
    let sync_to_workbench = matches!(status, "deterministic" | "confirmed");
    TurnoverRelation {
        relation_id: relation_id(&bank_row_ids),
        status: status.to_owned(),
        family,
        business_type,
        category_codes,
        counterparty_name,
        principal_row_ids,
        settlement_row_ids,
        bank_row_ids,
        principal_amount: format_money(principal),
        settled_amount: format_money(settled),
        balance_amount: format_money(principal - settled),
        first_transaction_at,
        last_settlement_at,
        source: "system".to_owned(),
        sync_to_workbench,
        evidence_reason: evidence_reason.to_owned(),
    }
}

fn flat_row_payload(
    relation: &TurnoverRelation,
    rows_by_id: &BTreeMap<String, TurnoverBankFactRow>,
) -> Option<TurnoverLedgerRow> {
    let bank_rows = relation
        .bank_row_ids
        .iter()
        .filter_map(|id| rows_by_id.get(id))
        .cloned()
        .collect::<Vec<_>>();
    if bank_rows.is_empty() {
        return None;
    }
    Some(TurnoverLedgerRow {
        relation_id: relation.relation_id.clone(),
        status: relation.status.clone(),
        status_label: status_label(&relation.status).to_owned(),
        row_tone: row_tone(&relation.status).to_owned(),
        chips: chips(relation),
        family: relation.family.clone(),
        family_label: family_label(&relation.family).to_owned(),
        counterparty_name: relation.counterparty_name.clone(),
        principal_amount: relation.principal_amount.clone(),
        settled_amount: relation.settled_amount.clone(),
        balance_amount: relation.balance_amount.clone(),
        first_transaction_at: relation.first_transaction_at.clone(),
        last_settlement_at: relation.last_settlement_at.clone(),
        bank_account_labels: bank_account_labels(&bank_rows),
        summary_text: summary_text(&bank_rows),
        annual_interest_rate: None,
        loan_days: loan_days(
            relation.first_transaction_at.as_deref(),
            relation.last_settlement_at.as_deref(),
        ),
        accrued_interest: None,
        sync_to_workbench: relation.sync_to_workbench,
        bank_row_ids: relation.bank_row_ids.clone(),
        category_codes: relation.category_codes.clone(),
        business_type: relation.business_type.clone(),
    })
}

fn grouped_item(
    relation: &TurnoverRelation,
    rows_by_id: &BTreeMap<String, TurnoverBankFactRow>,
) -> Option<GroupedItem> {
    let legacy = flat_row_payload(relation, rows_by_id)?;
    let summary_row = grouped_row_from_relation(relation, &legacy);
    let flow_rows = relation
        .bank_row_ids
        .iter()
        .filter_map(|id| rows_by_id.get(id))
        .map(|row| flow_row(relation, row))
        .collect::<Vec<_>>();
    Some(GroupedItem {
        family: legacy.family.clone(),
        status: legacy.status.clone(),
        counterparty_name: legacy.counterparty_name.clone(),
        business_type: legacy.business_type.clone(),
        balance_cents: parse_money_cents(&legacy.balance_amount),
        legacy,
        row: summary_row,
        flow_rows,
    })
}

fn grouped_row_from_relation(
    relation: &TurnoverRelation,
    legacy: &TurnoverLedgerRow,
) -> TurnoverGroupedRow {
    let (borrow_direction, repayment_direction) = money_directions(&relation.business_type);
    TurnoverGroupedRow {
        row_kind: "summary".to_owned(),
        display_level: Some("group_summary".to_owned()),
        relation_id: relation.relation_id.clone(),
        lot_id: String::new(),
        flow_id: String::new(),
        parent_relation_id: String::new(),
        source_bank_row_id: String::new(),
        principal_bank_row_id: if relation.principal_row_ids.len() == 1 {
            relation.principal_row_ids[0].clone()
        } else {
            String::new()
        },
        settlement_bank_row_ids: relation.settlement_row_ids.clone(),
        status: relation.status.clone(),
        status_label: status_label(&relation.status).to_owned(),
        row_tone: row_tone(&relation.status).to_owned(),
        transaction_at: None,
        flow_direction: String::new(),
        flow_amount: "0.00".to_owned(),
        borrow_amount: relation.principal_amount.clone(),
        borrow_date: date_text(relation.first_transaction_at.as_deref()),
        borrow_direction: borrow_direction.to_owned(),
        repayment_amount: relation.settled_amount.clone(),
        allocated_repayment_amount: relation.settled_amount.clone(),
        repayment_date: date_text(relation.last_settlement_at.as_deref()),
        repayment_direction: repayment_direction.to_owned(),
        balance_amount: relation.balance_amount.clone(),
        business_type: relation.business_type.clone(),
        category_label: String::new(),
        counterparty_bank_name: legacy.bank_account_labels.join(" / "),
        summary_text: legacy.summary_text.clone(),
        allocation_status: "not_applicable".to_owned(),
        allocated_lot_ids: Vec::new(),
        repayment_remark: legacy.summary_text.clone(),
        interest_rate_type: "none".to_owned(),
        interest_rate_value: "0.000000".to_owned(),
        interest_paid_amount: "0.00".to_owned(),
        loan_days: legacy.loan_days,
        accrued_interest: "0.00".to_owned(),
        interest_paid_date: None,
        interest_payment_method: String::new(),
        note: String::new(),
        bank_row_ids: relation.bank_row_ids.clone(),
    }
}

fn flow_row(relation: &TurnoverRelation, row: &TurnoverBankFactRow) -> TurnoverGroupedRow {
    let direction = if row.txn_direction == "inflow" {
        "income"
    } else {
        "expense"
    };
    let amount = format_money(parse_money_cents(&row.amount));
    TurnoverGroupedRow {
        row_kind: "flow".to_owned(),
        display_level: None,
        relation_id: relation.relation_id.clone(),
        lot_id: String::new(),
        flow_id: format!("bank:{}", row.id),
        parent_relation_id: relation.relation_id.clone(),
        source_bank_row_id: row.id.clone(),
        principal_bank_row_id: String::new(),
        settlement_bank_row_ids: Vec::new(),
        status: relation.status.clone(),
        status_label: status_label(&relation.status).to_owned(),
        row_tone: row_tone(&relation.status).to_owned(),
        transaction_at: row.transaction_at.clone(),
        flow_direction: direction.to_owned(),
        flow_amount: amount.clone(),
        borrow_amount: if direction == "income" {
            amount.clone()
        } else {
            "0.00".to_owned()
        },
        borrow_date: if direction == "income" {
            date_text(row.transaction_at.as_deref())
        } else {
            None
        },
        borrow_direction: String::new(),
        repayment_amount: if direction == "expense" {
            amount.clone()
        } else {
            "0.00".to_owned()
        },
        allocated_repayment_amount: "0.00".to_owned(),
        repayment_date: if direction == "expense" {
            date_text(row.transaction_at.as_deref())
        } else {
            None
        },
        repayment_direction: String::new(),
        balance_amount: "0.00".to_owned(),
        business_type: relation.business_type.clone(),
        category_label: row.category_label.clone(),
        counterparty_bank_name: bank_account_labels(std::slice::from_ref(row)).join(" / "),
        summary_text: summary_text(std::slice::from_ref(row)),
        allocation_status: "unallocated".to_owned(),
        allocated_lot_ids: Vec::new(),
        repayment_remark: summary_text(std::slice::from_ref(row)),
        interest_rate_type: "none".to_owned(),
        interest_rate_value: "0.000000".to_owned(),
        interest_paid_amount: "0.00".to_owned(),
        loan_days: None,
        accrued_interest: "0.00".to_owned(),
        interest_paid_date: None,
        interest_payment_method: String::new(),
        note: String::new(),
        bank_row_ids: vec![row.id.clone()],
    }
}

fn group_items(items: Vec<GroupedItem>) -> Vec<TurnoverLedgerGroup> {
    let mut groups: BTreeMap<(String, String), Vec<GroupedItem>> = BTreeMap::new();
    for item in items {
        groups
            .entry((item.family.clone(), item.counterparty_name.clone()))
            .or_default()
            .push(item);
    }
    groups
        .into_iter()
        .map(|((family, counterparty_name), group_items)| {
            let mut flow_rows = group_items
                .iter()
                .flat_map(|item| item.flow_rows.clone())
                .collect::<Vec<_>>();
            flow_rows.sort_by(|a, b| {
                a.transaction_at
                    .as_deref()
                    .unwrap_or_default()
                    .cmp(b.transaction_at.as_deref().unwrap_or_default())
            });
            let pending_repayment = group_items
                .iter()
                .filter(|item| item.business_type == "borrow_in")
                .map(|item| item.balance_cents.max(0))
                .sum::<i64>();
            let pending_collection = group_items
                .iter()
                .filter(|item| {
                    matches!(
                        item.business_type.as_str(),
                        "borrow_out" | "business_receivable"
                    )
                })
                .map(|item| item.balance_cents.max(0))
                .sum::<i64>();
            let (pending_direction, pending_direction_label, pending_amount, group_tone) =
                group_pending_payload(pending_repayment, pending_collection);
            let summary_row = group_items
                .first()
                .map(|item| item.row.clone())
                .unwrap_or_else(empty_grouped_row);
            TurnoverLedgerGroup {
                group_id: format!("counterparty:{family}:{counterparty_name}"),
                counterparty_name,
                family: family.clone(),
                family_label: family_label(&family).to_owned(),
                pending_direction,
                pending_direction_label,
                pending_amount,
                pending_repayment_amount: format_money(pending_repayment),
                pending_collection_amount: format_money(pending_collection),
                closed_amount: if pending_repayment == 0 && pending_collection == 0 {
                    summary_row.borrow_amount.clone()
                } else {
                    "0.00".to_owned()
                },
                row_span: 1 + flow_rows.len() as i64,
                group_tone,
                summary_row,
                flow_rows,
                allocation_lots: Vec::new(),
                lot_rows: Vec::new(),
            }
        })
        .collect()
}

fn turnover_export_rows(grouped: &TurnoverLedgerGroupedResponse, family: &str) -> Vec<Value> {
    let mut rows = Vec::new();
    let mut sequence = 1_i64;
    for group in &grouped.groups {
        if family != "all" && group.family != family {
            continue;
        }
        rows.push(turnover_export_row(
            sequence,
            group,
            &group.summary_row,
            "summary",
        ));
        sequence += 1;
        let mut seen_source_ids = BTreeSet::new();
        for flow in &group.flow_rows {
            if !flow.source_bank_row_id.is_empty()
                && !seen_source_ids.insert(flow.source_bank_row_id.clone())
            {
                continue;
            }
            rows.push(turnover_export_row(sequence, group, flow, "flow"));
            sequence += 1;
        }
    }
    rows
}

fn relation_detail_payload(relation: &TurnoverRelation) -> Value {
    json!({
        "relation_id": relation.relation_id,
        "status": relation.status,
        "category_family": relation.family,
        "business_type": relation.business_type,
        "category_codes": relation.category_codes,
        "counterparty_name": relation.counterparty_name,
        "normalized_counterparty_name": normalize_counterparty(&relation.counterparty_name),
        "principal_row_ids": relation.principal_row_ids,
        "settlement_row_ids": relation.settlement_row_ids,
        "bank_row_ids": relation.bank_row_ids,
        "principal_amount": relation.principal_amount,
        "settled_amount": relation.settled_amount,
        "balance_amount": relation.balance_amount,
        "direction_semantics": direction_semantics(&relation.business_type),
        "first_transaction_at": relation.first_transaction_at,
        "last_settlement_at": relation.last_settlement_at,
        "source": relation.source,
        "sync_to_workbench": relation.sync_to_workbench,
        "evidence": relation_evidence(relation),
        "version": 1,
        "created_by": "system",
        "created_at": null,
        "updated_by": "system",
        "updated_at": null,
    })
}

fn relation_evidence(relation: &TurnoverRelation) -> Value {
    if relation.status == "conflict" {
        return json!({
            "matched_fields": ["category_code"],
            "conflict_reason": relation.evidence_reason,
        });
    }
    json!({
        "matched_fields": ["category_code", "counterparty_name", "amount"],
        "auto_confirm_reason": relation.evidence_reason,
    })
}

fn turnover_bank_detail_row(row: &TurnoverBankFactRow) -> Value {
    let amount = format_money(parse_money_cents(&row.amount).abs());
    let is_outflow = row.txn_direction == "outflow";
    json!({
        "id": row.id,
        "trade_time": row.transaction_at,
        "counterparty_name": row.counterparty_name,
        "counterparty_name_raw": row.counterparty_name,
        "direction": row.txn_direction,
        "txn_direction": row.txn_direction,
        "direction_label": if is_outflow { "支" } else { "收" },
        "amount": amount,
        "debit_amount": if is_outflow { amount.clone() } else { "0.00".to_owned() },
        "credit_amount": if is_outflow { "0.00".to_owned() } else { amount },
        "bank_account_label": bank_account_labels(std::slice::from_ref(row)).join(" / "),
        "imported_bank_name": row.bank_name,
        "imported_bank_last4": account_last4(&row.account_no),
        "bank_name": row.bank_name,
        "account_last4": account_last4(&row.account_no),
        "summary": row.summary,
        "remark": row.remark,
        "purpose": row.purpose,
        "category_label": row.category_label,
    })
}

fn account_last4(account_no: &str) -> String {
    let digits = account_no
        .chars()
        .filter(char::is_ascii_digit)
        .collect::<String>();
    if digits.len() >= 4 {
        digits[digits.len() - 4..].to_owned()
    } else {
        String::new()
    }
}

fn direction_semantics(business_type: &str) -> &str {
    match business_type {
        "borrow_in" => "borrow_in_principal",
        "borrow_out" => "borrow_out_principal",
        "business_receivable" => "business_receivable",
        _ => "",
    }
}

fn turnover_export_row(
    sequence: i64,
    group: &TurnoverLedgerGroup,
    row: &TurnoverGroupedRow,
    row_type: &str,
) -> Value {
    let is_flow = row_type == "flow";
    let balance_amount = if value_present(&row.balance_amount) {
        parse_money_cents(&row.balance_amount)
    } else {
        parse_money_cents(&group.pending_amount)
    };
    let (pending_repayment, pending_collection) =
        turnover_export_pending_amounts(group, row, balance_amount);
    let flow_amount = if is_flow {
        format_money(parse_money_cents(&row.flow_amount))
    } else {
        "0.00".to_owned()
    };
    json!({
        "序号": sequence,
        "行类型": if is_flow { "真实流水" } else { "合计" },
        "源银行流水ID": if is_flow { row.source_bank_row_id.as_str() } else { "" },
        "流水方向": if is_flow { row.flow_direction.as_str() } else { "" },
        "流水金额": flow_amount,
        "往来大类": non_empty(&group.family_label, &row.category_label),
        "对方户名": group.counterparty_name,
        "待还款金额": format_money(pending_repayment),
        "待收款金额": format_money(pending_collection),
        "余额": format_money(balance_amount),
        "借款金额": format_money(parse_money_cents(&row.borrow_amount)),
        "借款日": row.borrow_date.as_deref().unwrap_or(""),
        "还款金额": format_money(parse_money_cents(&row.repayment_amount)),
        "还款日": row.repayment_date.as_deref().unwrap_or(""),
        "对方开户机构": row.counterparty_bank_name,
        "还款备注": row.repayment_remark,
        "利率类型": interest_rate_type_label(&row.interest_rate_type),
        "利率值": if row.interest_rate_value.is_empty() { "0.000000" } else { row.interest_rate_value.as_str() },
        "已还利息额": format_money(parse_money_cents(&row.interest_paid_amount)),
        "借款天数": row.loan_days.map(Value::from).unwrap_or(Value::String(String::new())),
        "应还利息": format_money(parse_money_cents(&row.accrued_interest)),
        "还利息日期": row.interest_paid_date.as_deref().unwrap_or(""),
        "还利息方式": row.interest_payment_method,
        "备注": row.note,
        "关系状态": non_empty(&row.status_label, &row.status),
        "row_type": if is_flow { "flow" } else { "summary" },
        "lot_id": "",
        "source_bank_row_id": if is_flow { row.source_bank_row_id.as_str() } else { "" },
        "flow_direction": if is_flow { row.flow_direction.as_str() } else { "" },
        "flow_amount": if is_flow { format_money(parse_money_cents(&row.flow_amount)) } else { "0.00".to_owned() },
        "balance_amount": format_money(balance_amount),
    })
}

fn turnover_export_pending_amounts(
    group: &TurnoverLedgerGroup,
    row: &TurnoverGroupedRow,
    balance_amount: i64,
) -> (i64, i64) {
    match row.business_type.as_str() {
        "borrow_in" => (balance_amount, 0),
        "borrow_out" | "business_receivable" => (0, balance_amount),
        _ if group.pending_direction == "repayment" => (balance_amount, 0),
        _ if group.pending_direction == "collection" => (0, balance_amount),
        _ => (0, 0),
    }
}

fn turnover_export_totals(rows: &[Value]) -> Value {
    let summary_rows = rows
        .iter()
        .filter(|row| row.get("row_type").and_then(Value::as_str) == Some("summary"))
        .collect::<Vec<_>>();
    let total_rows = if summary_rows.is_empty() {
        rows.iter().collect::<Vec<_>>()
    } else {
        summary_rows
    };
    json!({
        "row_count": rows.len(),
        "pending_repayment_amount": format_money(sum_export_column(&total_rows, "待还款金额")),
        "pending_collection_amount": format_money(sum_export_column(&total_rows, "待收款金额")),
        "borrow_amount": format_money(sum_export_column(&total_rows, "借款金额")),
        "repayment_amount": format_money(sum_export_column(&total_rows, "还款金额")),
        "accrued_interest": format_money(sum_export_column(&total_rows, "应还利息")),
    })
}

fn sum_export_column(rows: &[&Value], key: &str) -> i64 {
    rows.iter()
        .filter_map(|row| row.get(key).and_then(Value::as_str))
        .map(parse_money_cents)
        .sum()
}

fn turnover_preview_limit(value: Option<&str>) -> Result<i64, TurnoverLedgerServiceError> {
    match clean_optional(value) {
        Some(raw) => raw.parse::<i64>().map(|limit| limit.max(1)).map_err(|_| {
            TurnoverLedgerServiceError::InvalidRequest {
                code: "invalid_turnover_ledger_export_request",
                message: "limit must be an integer.",
            }
        }),
        None => Ok(20),
    }
}

fn interest_rate_type_label(value: &str) -> &str {
    match value {
        "annual" => "年利率",
        "monthly" => "月利率",
        "none" | "" => "无息",
        other => other,
    }
}

fn value_present(value: &str) -> bool {
    !value.trim().is_empty()
}

fn non_empty<'a>(value: &'a str, fallback: &'a str) -> &'a str {
    if value.trim().is_empty() {
        fallback
    } else {
        value
    }
}

fn empty_grouped_row() -> TurnoverGroupedRow {
    TurnoverGroupedRow {
        row_kind: "summary".to_owned(),
        display_level: Some("group_summary".to_owned()),
        relation_id: String::new(),
        lot_id: String::new(),
        flow_id: String::new(),
        parent_relation_id: String::new(),
        source_bank_row_id: String::new(),
        principal_bank_row_id: String::new(),
        settlement_bank_row_ids: Vec::new(),
        status: String::new(),
        status_label: String::new(),
        row_tone: "muted".to_owned(),
        transaction_at: None,
        flow_direction: String::new(),
        flow_amount: "0.00".to_owned(),
        borrow_amount: "0.00".to_owned(),
        borrow_date: None,
        borrow_direction: String::new(),
        repayment_amount: "0.00".to_owned(),
        allocated_repayment_amount: "0.00".to_owned(),
        repayment_date: None,
        repayment_direction: String::new(),
        balance_amount: "0.00".to_owned(),
        business_type: String::new(),
        category_label: String::new(),
        counterparty_bank_name: String::new(),
        summary_text: String::new(),
        allocation_status: "not_applicable".to_owned(),
        allocated_lot_ids: Vec::new(),
        repayment_remark: String::new(),
        interest_rate_type: "none".to_owned(),
        interest_rate_value: "0.000000".to_owned(),
        interest_paid_amount: "0.00".to_owned(),
        loan_days: None,
        accrued_interest: "0.00".to_owned(),
        interest_paid_date: None,
        interest_payment_method: String::new(),
        note: String::new(),
        bank_row_ids: Vec::new(),
    }
}

fn apply_filters(
    rows: Vec<TurnoverLedgerRow>,
    family: Option<&str>,
    status: Option<&str>,
) -> Vec<TurnoverLedgerRow> {
    let family = normalize_family(family);
    let status = normalize_status(status);
    rows.into_iter()
        .filter(|row| family == "all" || row.family == family)
        .filter(|row| status.as_ref().is_none_or(|status| &row.status == status))
        .collect()
}

fn apply_item_filters(
    rows: Vec<GroupedItem>,
    family: Option<&str>,
    status: Option<&str>,
) -> Vec<GroupedItem> {
    let family = normalize_family(family);
    let status = normalize_status(status);
    rows.into_iter()
        .filter(|row| family == "all" || row.family == family)
        .filter(|row| status.as_ref().is_none_or(|status| &row.status == status))
        .collect()
}

fn summary(rows: &[TurnoverLedgerRow]) -> TurnoverLedgerSummary {
    let mut pending_repayment = 0;
    let mut repaid = 0;
    let mut pending_collection = 0;
    let mut collected = 0;
    let mut closed = 0;
    let mut suggested_count = 0;
    let mut conflict_count = 0;
    for row in rows {
        let principal = parse_money_cents(&row.principal_amount);
        let settled = parse_money_cents(&row.settled_amount);
        let balance = parse_money_cents(&row.balance_amount);
        if row.business_type == "borrow_in" {
            pending_repayment += balance.max(0);
            repaid += settled;
        } else if matches!(
            row.business_type.as_str(),
            "borrow_out" | "business_receivable"
        ) {
            pending_collection += balance.max(0);
            collected += settled;
        }
        if balance == 0 && matches!(row.status.as_str(), "deterministic" | "confirmed") {
            closed += principal;
        }
        if row.status == "suggested" {
            suggested_count += 1;
        }
        if row.status == "conflict" {
            conflict_count += 1;
        }
    }
    TurnoverLedgerSummary {
        pending_repayment_amount: format_money(pending_repayment),
        repaid_amount: format_money(repaid),
        pending_collection_amount: format_money(pending_collection),
        collected_amount: format_money(collected),
        closed_amount: format_money(closed),
        suggested_count,
        conflict_count,
        row_count: rows.len() as i64,
    }
}

fn family_summaries(rows: &[TurnoverLedgerRow]) -> Vec<TurnoverLedgerFamilySummary> {
    FAMILIES
        .iter()
        .map(|(family, label)| {
            let family_rows = rows
                .iter()
                .filter(|row| row.family == *family)
                .cloned()
                .collect::<Vec<_>>();
            let family_summary = summary(&family_rows);
            let pending_amount = parse_money_cents(&family_summary.pending_repayment_amount)
                + parse_money_cents(&family_summary.pending_collection_amount);
            TurnoverLedgerFamilySummary {
                family: (*family).to_owned(),
                label: (*label).to_owned(),
                pending_amount: format_money(pending_amount),
                closed_amount: family_summary.closed_amount,
                row_count: family_summary.row_count,
            }
        })
        .collect()
}

fn chips(relation: &TurnoverRelation) -> Vec<TurnoverLedgerChip> {
    let mut chips = vec![TurnoverLedgerChip {
        label: status_label(&relation.status).to_owned(),
        tone: row_tone(&relation.status).to_owned(),
    }];
    if relation.source == "system" {
        chips.push(TurnoverLedgerChip {
            label: "系统".to_owned(),
            tone: "neutral".to_owned(),
        });
    }
    if relation.sync_to_workbench {
        chips.push(TurnoverLedgerChip {
            label: "同步关联台".to_owned(),
            tone: "success".to_owned(),
        });
    }
    if !relation.evidence_reason.is_empty() {
        chips.push(TurnoverLedgerChip {
            label: relation.evidence_reason.clone(),
            tone: "neutral".to_owned(),
        });
    }
    chips
}

fn bank_account_labels(rows: &[TurnoverBankFactRow]) -> Vec<String> {
    let mut labels = Vec::new();
    for row in rows {
        let digits = row
            .account_no
            .chars()
            .filter(char::is_ascii_digit)
            .collect::<String>();
        let last4 = if digits.len() >= 4 {
            &digits[digits.len() - 4..]
        } else {
            "unknown"
        };
        let label = format!("{} {}", empty_default(&row.bank_name, "未知银行"), last4);
        if !labels.contains(&label) {
            labels.push(label);
        }
    }
    labels
}

fn summary_text(rows: &[TurnoverBankFactRow]) -> String {
    let mut values = Vec::new();
    for row in rows {
        for value in [
            row.summary.as_deref(),
            row.remark.as_deref(),
            row.purpose.as_deref(),
        ]
        .into_iter()
        .flatten()
        {
            let value = value.trim();
            if !value.is_empty() && !values.contains(&value.to_owned()) {
                values.push(value.to_owned());
            }
        }
        for value in &row.bank_text_fields {
            let value = value.trim();
            if !value.is_empty() && !values.contains(&value.to_owned()) {
                values.push(value.to_owned());
            }
        }
    }
    values.join(" / ")
}

fn group_pending_payload(
    pending_repayment: i64,
    pending_collection: i64,
) -> (String, String, String, String) {
    if pending_repayment > 0 && pending_collection > 0 {
        (
            "mixed".to_owned(),
            "混合余额".to_owned(),
            format_money(pending_repayment + pending_collection),
            "warning".to_owned(),
        )
    } else if pending_repayment > 0 {
        (
            "repayment".to_owned(),
            "待还款".to_owned(),
            format_money(pending_repayment),
            "warning".to_owned(),
        )
    } else if pending_collection > 0 {
        (
            "collection".to_owned(),
            "待收款".to_owned(),
            format_money(pending_collection),
            "success".to_owned(),
        )
    } else {
        (
            "closed".to_owned(),
            "已闭合".to_owned(),
            "0.00".to_owned(),
            "muted".to_owned(),
        )
    }
}

fn relation_id(row_ids: &[String]) -> String {
    let mut sorted_ids = row_ids.to_vec();
    sorted_ids.sort();
    let mut hasher = Sha1::new();
    hasher.update(sorted_ids.join("|").as_bytes());
    let digest = format!("{:x}", hasher.finalize());
    format!("turnover_rel_{}", &digest[..16])
}

fn turnover_page(value: Option<&str>) -> Result<i64, TurnoverLedgerServiceError> {
    match clean_optional(value) {
        Some(raw) => raw
            .parse::<i64>()
            .map(|page| page.max(1))
            .map_err(|_| invalid_turnover_request("page and page_size must be integers.")),
        None => Ok(1),
    }
}

fn turnover_page_size(value: Option<&str>) -> Result<i64, TurnoverLedgerServiceError> {
    match clean_optional(value) {
        Some(raw) => raw
            .parse::<i64>()
            .map(|page_size| page_size.clamp(1, 200))
            .map_err(|_| invalid_turnover_request("page and page_size must be integers.")),
        None => Ok(50),
    }
}

fn invalid_turnover_request(message: &'static str) -> TurnoverLedgerServiceError {
    TurnoverLedgerServiceError::InvalidRequest {
        code: "invalid_turnover_ledger_request",
        message,
    }
}

fn parse_money_cents(value: &str) -> i64 {
    let raw = value.replace(',', "");
    let raw = raw.trim();
    if raw.is_empty() {
        return 0;
    }
    let negative = raw.starts_with('-');
    let raw = raw.trim_start_matches('-');
    let mut parts = raw.split('.');
    let yuan = parts
        .next()
        .unwrap_or("0")
        .parse::<i64>()
        .unwrap_or_default();
    let cents_raw = parts.next().unwrap_or("0");
    let mut cents_text = cents_raw.chars().take(2).collect::<String>();
    while cents_text.len() < 2 {
        cents_text.push('0');
    }
    let cents = cents_text.parse::<i64>().unwrap_or_default();
    let amount = yuan.saturating_mul(100).saturating_add(cents);
    if negative {
        -amount
    } else {
        amount
    }
}

fn format_money(cents: i64) -> String {
    let sign = if cents < 0 { "-" } else { "" };
    let cents = cents.abs();
    format!("{sign}{}.{:02}", cents / 100, cents % 100)
}

fn normalize_counterparty(value: &str) -> String {
    let normalized = value.split_whitespace().collect::<Vec<_>>().join(" ");
    if normalized.is_empty() {
        "UNKNOWN".to_owned()
    } else {
        normalized
    }
}

fn normalize_family(value: Option<&str>) -> String {
    let family = value.unwrap_or("all").trim().to_lowercase();
    if family == "all" || FAMILIES.iter().any(|(candidate, _)| *candidate == family) {
        family
    } else {
        "all".to_owned()
    }
}

fn normalize_status(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_lowercase)
}

fn clean_optional(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn family_label(value: &str) -> &str {
    FAMILIES
        .iter()
        .find_map(|(family, label)| (*family == value).then_some(*label))
        .unwrap_or(value)
}

fn status_label(value: &str) -> &str {
    match value {
        "deterministic" => "完全闭合",
        "confirmed" => "人工确认",
        "suggested" => "待人工确认",
        "conflict" => "冲突",
        "stale" => "已过期",
        "withdrawn" => "已撤回",
        _ => value,
    }
}

fn row_tone(value: &str) -> &str {
    match value {
        "deterministic" | "confirmed" => "success",
        "suggested" => "warning",
        "conflict" => "danger",
        "stale" | "withdrawn" => "muted",
        _ => "muted",
    }
}

fn money_directions(business_type: &str) -> (&str, &str) {
    if business_type == "borrow_in" {
        ("income", "expense")
    } else {
        ("expense", "income")
    }
}

fn date_text(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| value.len() >= 10)
        .map(|value| value[..10].to_owned())
}

fn loan_days(first: Option<&str>, last: Option<&str>) -> Option<i64> {
    let first = date_text(first)?;
    let last = date_text(last)?;
    let first = days_from_civil(&first)?;
    let last = days_from_civil(&last)?;
    Some((last - first).max(0))
}

fn days_from_civil(value: &str) -> Option<i64> {
    let mut parts = value.split('-');
    let y = parts.next()?.parse::<i64>().ok()?;
    let m = parts.next()?.parse::<i64>().ok()?;
    let d = parts.next()?.parse::<i64>().ok()?;
    if !(1..=12).contains(&m) || !(1..=31).contains(&d) {
        return None;
    }
    let y = y - i64::from(m <= 2);
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = m + if m > 2 { -3 } else { 9 };
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    Some(era * 146097 + doe - 719468)
}

fn empty_default<'a>(value: &'a str, default: &'a str) -> &'a str {
    if value.trim().is_empty() {
        default
    } else {
        value.trim()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;

    #[derive(Clone, Default)]
    struct StubTurnoverLedgerRepository {
        rows: Vec<TurnoverBankFactRow>,
    }

    #[async_trait]
    impl TurnoverLedgerRepository for StubTurnoverLedgerRepository {
        async fn list_turnover_bank_rows(
            &self,
        ) -> Result<Vec<TurnoverBankFactRow>, TurnoverLedgerRepositoryError> {
            Ok(self.rows.clone())
        }
    }

    #[tokio::test]
    async fn flat_ledger_uses_bank_category_facts_and_python_summary_shape() {
        let service = TurnoverLedgerService::new(StubTurnoverLedgerRepository {
            rows: vec![
                TurnoverBankFactRow {
                    id: "txn-borrow".to_owned(),
                    transaction_at: Some("2026-05-01T02:00:00Z".to_owned()),
                    txn_direction: "inflow".to_owned(),
                    amount: "200.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("公司暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_pending_repayment".to_owned(),
                    category_label: "公司暂借款：待还款".to_owned(),
                },
                TurnoverBankFactRow {
                    id: "txn-repay".to_owned(),
                    transaction_at: Some("2026-05-03T02:00:00Z".to_owned()),
                    txn_direction: "outflow".to_owned(),
                    amount: "80.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("归还暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_repaid".to_owned(),
                    category_label: "公司暂借款：已还款".to_owned(),
                },
            ],
        });

        let response = service
            .list_ledger(TurnoverLedgerQuery {
                view: None,
                family: Some("company".to_owned()),
                status: Some("suggested".to_owned()),
                page: Some("1".to_owned()),
                page_size: Some("50".to_owned()),
                limit: None,
            })
            .await
            .unwrap();

        assert_eq!(response.summary.pending_repayment_amount, "120.00");
        assert_eq!(response.summary.repaid_amount, "80.00");
        assert_eq!(response.summary.row_count, 1);
        assert_eq!(response.pagination.total, 1);
        assert_eq!(response.filters.family, "company");
        assert_eq!(response.filters.status.as_deref(), Some("suggested"));
        assert_eq!(response.rows[0].family, "company");
        assert_eq!(response.rows[0].status, "suggested");
        assert_eq!(
            response.rows[0].bank_row_ids,
            vec!["txn-borrow", "txn-repay"]
        );
        assert_eq!(
            response.rows[0].relation_id,
            "turnover_rel_438a07b576e27837"
        );
    }

    #[tokio::test]
    async fn grouped_ledger_preserves_grouped_envelope_for_frontend() {
        let service = TurnoverLedgerService::new(StubTurnoverLedgerRepository {
            rows: vec![TurnoverBankFactRow {
                id: "txn-business".to_owned(),
                transaction_at: Some("2026-05-02T02:00:00Z".to_owned()),
                txn_direction: "outflow".to_owned(),
                amount: "500.00".to_owned(),
                counterparty_name: "昆明建设集团".to_owned(),
                account_no: "6222000012348106".to_owned(),
                bank_name: "建行".to_owned(),
                summary: Some("投标保证金".to_owned()),
                remark: None,
                purpose: None,
                bank_text_fields: Vec::new(),
                category_code: "business_bid_bond_pending_collection".to_owned(),
                category_label: "投标保证金待收款".to_owned(),
            }],
        });

        let response = service
            .list_grouped_ledger(TurnoverLedgerQuery {
                view: Some("grouped".to_owned()),
                family: Some("business".to_owned()),
                status: None,
                page: Some("1".to_owned()),
                page_size: Some("50".to_owned()),
                limit: None,
            })
            .await
            .unwrap();

        assert_eq!(response.summary.pending_collection_amount, "500.00");
        assert_eq!(response.pagination.total, 1);
        assert_eq!(response.filters.family, "business");
        assert_eq!(response.filters.status, None);
        assert_eq!(response.groups[0].counterparty_name, "昆明建设集团");
        assert_eq!(response.groups[0].summary_row.row_kind, "summary");
        assert_eq!(
            response.groups[0].flow_rows[0].source_bank_row_id,
            "txn-business"
        );
        assert_eq!(response.groups[0].row_span, 2);
    }

    #[tokio::test]
    async fn export_preview_uses_grouped_ledger_rows_with_legacy_preview_shape() {
        let service = TurnoverLedgerService::new(StubTurnoverLedgerRepository {
            rows: vec![
                TurnoverBankFactRow {
                    id: "txn-borrow".to_owned(),
                    transaction_at: Some("2026-05-01T02:00:00Z".to_owned()),
                    txn_direction: "inflow".to_owned(),
                    amount: "200.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("公司暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_pending_repayment".to_owned(),
                    category_label: "公司暂借款：待还款".to_owned(),
                },
                TurnoverBankFactRow {
                    id: "txn-repay".to_owned(),
                    transaction_at: Some("2026-05-03T02:00:00Z".to_owned()),
                    txn_direction: "outflow".to_owned(),
                    amount: "80.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("归还暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_repaid".to_owned(),
                    category_label: "公司暂借款：已还款".to_owned(),
                },
            ],
        });

        let preview = service
            .export_preview(TurnoverLedgerQuery {
                view: None,
                family: Some("company".to_owned()),
                status: None,
                page: None,
                page_size: None,
                limit: Some("2".to_owned()),
            })
            .await
            .unwrap();

        assert_eq!(preview["columns"][0], "序号");
        assert_eq!(preview["filters"]["family"], "company");
        assert_eq!(preview["pagination"]["preview_count"], 2);
        assert_eq!(preview["pagination"]["total"], 3);
        assert_eq!(preview["totals"]["row_count"], 3);
        assert_eq!(preview["totals"]["pending_repayment_amount"], "120.00");
        assert_eq!(preview["rows"][0]["行类型"], "合计");
        assert_eq!(preview["rows"][0]["待还款金额"], "120.00");
        assert_eq!(preview["rows"][1]["行类型"], "真实流水");
        assert_eq!(preview["rows"][1]["源银行流水ID"], "txn-borrow");
    }

    #[tokio::test]
    async fn relation_detail_returns_legacy_relation_row_and_bank_rows() {
        let service = TurnoverLedgerService::new(StubTurnoverLedgerRepository {
            rows: vec![
                TurnoverBankFactRow {
                    id: "txn-borrow".to_owned(),
                    transaction_at: Some("2026-05-01T02:00:00Z".to_owned()),
                    txn_direction: "inflow".to_owned(),
                    amount: "200.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("公司暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_pending_repayment".to_owned(),
                    category_label: "公司暂借款：待还款".to_owned(),
                },
                TurnoverBankFactRow {
                    id: "txn-repay".to_owned(),
                    transaction_at: Some("2026-05-03T02:00:00Z".to_owned()),
                    txn_direction: "outflow".to_owned(),
                    amount: "80.00".to_owned(),
                    counterparty_name: "云南路桥".to_owned(),
                    account_no: "6222000012348106".to_owned(),
                    bank_name: "建行".to_owned(),
                    summary: Some("归还暂借款".to_owned()),
                    remark: None,
                    purpose: None,
                    bank_text_fields: Vec::new(),
                    category_code: "borrow_in_company_repaid".to_owned(),
                    category_label: "公司暂借款：已还款".to_owned(),
                },
            ],
        });

        let detail = service
            .get_relation_detail("turnover_rel_438a07b576e27837")
            .await
            .unwrap();

        assert_eq!(
            detail["relation"]["relation_id"],
            "turnover_rel_438a07b576e27837"
        );
        assert_eq!(detail["relation"]["principal_amount"], "200.00");
        assert_eq!(detail["row"]["balance_amount"], "120.00");
        assert_eq!(detail["bank_rows"][0]["id"], "txn-borrow");
        assert_eq!(detail["bank_rows"][0]["debit_amount"], "0.00");
        assert_eq!(detail["bank_rows"][0]["credit_amount"], "200.00");
        assert_eq!(detail["bank_rows"][1]["debit_amount"], "80.00");
        assert_eq!(detail["audit_history"], json!([]));
    }
}
