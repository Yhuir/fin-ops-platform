use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

use crate::services::workbench_writes::WriteActor;

#[derive(Debug, thiserror::Error)]
pub enum FinanceWriteServiceError {
    #[error("invalid request: {message}")]
    InvalidRequest { code: &'static str, message: String },
    #[error("write conflict: {message}")]
    Conflict { code: &'static str, message: String },
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
    #[error(transparent)]
    Repository(FinanceWriteRepositoryError),
}

#[derive(Debug, thiserror::Error)]
pub enum FinanceWriteRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
    #[error("idempotency key was reused with a different payload")]
    IdempotencyConflict,
    #[error("write conflict: {code}")]
    Conflict { code: &'static str, message: String },
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
}

#[async_trait]
pub trait FinanceWriteRepository: Send + Sync {
    async fn execute(
        &self,
        command: FinanceWriteCommand,
    ) -> Result<BankCategoryUpdateResponse, FinanceWriteRepositoryError>;
}

pub struct FinanceWriteService<R> {
    repository: R,
}

impl<R> FinanceWriteService<R>
where
    R: FinanceWriteRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn save_bank_transaction_categories_as(
        &self,
        request: BankCategoryUpdateRequest,
        actor: WriteActor,
    ) -> Result<BankCategoryUpdateResponse, FinanceWriteServiceError> {
        if request.updates.is_empty() {
            return Err(invalid_request(
                "invalid_category_update",
                "updates must be a non-empty array",
            ));
        }
        let actor = validate_actor(actor)?;
        let updates = request
            .updates
            .into_iter()
            .map(normalize_update)
            .collect::<Result<Vec<_>, _>>()?;
        let mut seen = std::collections::BTreeSet::new();
        for update in &updates {
            if !seen.insert(update.transaction_id) {
                return Err(invalid_request(
                    "invalid_category_update",
                    "duplicate transaction_id in updates",
                ));
            }
        }
        let idempotency_key = request
            .idempotency_key
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| derived_bank_category_idempotency_key(&actor, &updates));
        let request_payload = serde_json::json!({
            "updates": updates.iter().map(|update| serde_json::json!({
                "transaction_id": update.transaction_id,
                "category_code": update.category_code,
                "expected_version": update.expected_version
            })).collect::<Vec<_>>(),
            "trusted_actor": {
                "actor_id": actor.actor_id,
                "actor_type": actor.actor_type,
                "request_id": actor.request_id
            }
        });
        self.repository
            .execute(FinanceWriteCommand::BankCategoryUpdate(
                BankCategoryUpdateCommand {
                    idempotency_key,
                    actor,
                    updates,
                    request_payload,
                },
            ))
            .await
            .map_err(FinanceWriteServiceError::from)
    }
}

#[derive(Debug, Clone)]
pub enum FinanceWriteCommand {
    BankCategoryUpdate(BankCategoryUpdateCommand),
}

#[derive(Debug, Clone)]
pub struct BankCategoryUpdateCommand {
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub updates: Vec<BankCategoryUpdateItem>,
    pub request_payload: Value,
}

#[derive(Debug, Deserialize)]
pub struct BankCategoryUpdateRequest {
    #[serde(default)]
    pub idempotency_key: Option<String>,
    pub updates: Vec<BankCategoryUpdateItem>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct BankCategoryUpdateItem {
    pub transaction_id: Uuid,
    pub category_code: Option<String>,
    pub expected_version: Option<i64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BankCategoryUpdateResponse {
    pub updated_transaction_ids: Vec<String>,
    pub updated_categories: Vec<BankCategoryUpdateResult>,
    pub affected_months: Vec<String>,
    pub workbench_rebuild_queued: bool,
    pub turnover_relations_updated: bool,
    pub turnover_ledger_invalidated: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub rebuild_task_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub outbox_event_id: Option<String>,
    pub idempotency_key: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BankCategoryUpdateResult {
    pub transaction_id: String,
    pub category_code: Option<String>,
    pub category_label: Option<String>,
    pub category_path: Vec<String>,
    pub version: i64,
}

impl FinanceWriteCommand {
    pub fn operation(&self) -> &'static str {
        match self {
            Self::BankCategoryUpdate(_) => "bank_transaction.category.patch",
        }
    }

    pub fn idempotency_key(&self) -> &str {
        match self {
            Self::BankCategoryUpdate(command) => &command.idempotency_key,
        }
    }

    pub fn request_payload(&self) -> &Value {
        match self {
            Self::BankCategoryUpdate(command) => &command.request_payload,
        }
    }

    pub fn actor_id(&self) -> &str {
        match self {
            Self::BankCategoryUpdate(command) => &command.actor.actor_id,
        }
    }
}

impl From<FinanceWriteRepositoryError> for FinanceWriteServiceError {
    fn from(error: FinanceWriteRepositoryError) -> Self {
        match error {
            FinanceWriteRepositoryError::IdempotencyConflict => Self::Conflict {
                code: "idempotency_conflict",
                message: "idempotency key was reused with a different payload".to_owned(),
            },
            FinanceWriteRepositoryError::Conflict { code, message } => {
                Self::Conflict { code, message }
            }
            FinanceWriteRepositoryError::NotFound { resource } => Self::NotFound { resource },
            FinanceWriteRepositoryError::Database(error) => {
                Self::Repository(FinanceWriteRepositoryError::Database(error))
            }
        }
    }
}

fn normalize_update(
    mut update: BankCategoryUpdateItem,
) -> Result<BankCategoryUpdateItem, FinanceWriteServiceError> {
    if let Some(value) = update.category_code.take() {
        let value = value.trim().to_owned();
        update.category_code = if value.is_empty() { None } else { Some(value) };
    }
    if let Some(version) = update.expected_version {
        if version < 0 {
            return Err(invalid_request(
                "invalid_expected_version",
                "expected_version must not be negative",
            ));
        }
    }
    if let Some(code) = update.category_code.as_deref() {
        if category_descriptor(code).is_none() {
            return Err(invalid_request(
                "invalid_category_update",
                format!("unknown bank transaction category code: {code}"),
            ));
        }
    }
    Ok(update)
}

fn validate_actor(actor: WriteActor) -> Result<WriteActor, FinanceWriteServiceError> {
    if actor.actor_id.trim().is_empty() {
        return Err(invalid_request("permission_denied", "actor is required"));
    }
    Ok(actor)
}

fn derived_bank_category_idempotency_key(
    actor: &WriteActor,
    updates: &[BankCategoryUpdateItem],
) -> String {
    let mut parts = updates
        .iter()
        .map(|update| {
            format!(
                "{}:{}:{}",
                update.transaction_id,
                update.category_code.as_deref().unwrap_or("clear"),
                update
                    .expected_version
                    .map(|value| value.to_string())
                    .unwrap_or_else(|| "none".to_owned())
            )
        })
        .collect::<Vec<_>>();
    parts.sort();
    format!(
        "bank.category:{}:{}:{}",
        actor.actor_id,
        actor.request_id.as_deref().unwrap_or("no-request-id"),
        parts.join("|")
    )
}

pub fn category_descriptor(code: &str) -> Option<(&'static str, &'static [&'static str])> {
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
        "external_turnover" => Some(("外部往来款", &[])),
        "internal_transfer" => Some(("内部往来款", &["自动识别", "内部往来款"])),
        "offset" => Some(("冲", &[])),
        "cash_turnover" => Some(("现金往来", &[])),
        "fee" => Some(("手续费", &["自动识别", "手续费"])),
        "salary" => Some(("工资", &["自动识别", "工资"])),
        "holiday_bonus" => Some(("过节费", &["自动识别", "过节费"])),
        "bonus" => Some(("奖金", &["自动识别", "奖金"])),
        _ => None,
    }
}

fn invalid_request(code: &'static str, message: impl Into<String>) -> FinanceWriteServiceError {
    FinanceWriteServiceError::InvalidRequest {
        code,
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use async_trait::async_trait;
    use serde_json::json;
    use uuid::Uuid;

    use super::*;
    use crate::services::workbench_writes::WriteActor;

    #[derive(Default)]
    struct FixtureFinanceWriteRepository {
        commands: Arc<Mutex<Vec<FinanceWriteCommand>>>,
    }

    #[async_trait]
    impl FinanceWriteRepository for FixtureFinanceWriteRepository {
        async fn execute(
            &self,
            command: FinanceWriteCommand,
        ) -> Result<BankCategoryUpdateResponse, FinanceWriteRepositoryError> {
            self.commands.lock().unwrap().push(command);
            Ok(BankCategoryUpdateResponse {
                updated_transaction_ids: vec!["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".to_owned()],
                updated_categories: vec![BankCategoryUpdateResult {
                    transaction_id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".to_owned(),
                    category_code: Some("borrow_in_company_pending_repayment".to_owned()),
                    category_label: Some("公司暂借款：待还款".to_owned()),
                    category_path: vec![
                        "借入".to_owned(),
                        "公司往来款".to_owned(),
                        "待还款".to_owned(),
                    ],
                    version: 2,
                }],
                affected_months: vec!["2026-05".to_owned()],
                workbench_rebuild_queued: true,
                turnover_relations_updated: true,
                turnover_ledger_invalidated: true,
                rebuild_task_id: Some("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb".to_owned()),
                outbox_event_id: Some("cccccccc-cccc-4ccc-8ccc-cccccccccccc".to_owned()),
                idempotency_key: "bank.category:request-1".to_owned(),
            })
        }
    }

    #[tokio::test]
    async fn bank_category_update_builds_audited_idempotent_rebuild_command() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = FinanceWriteService::new(FixtureFinanceWriteRepository {
            commands: commands.clone(),
        });

        let response = service
            .save_bank_transaction_categories_as(
                BankCategoryUpdateRequest {
                    idempotency_key: Some("bank.category:request-1".to_owned()),
                    updates: vec![BankCategoryUpdateItem {
                        transaction_id: Uuid::parse_str("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
                            .unwrap(),
                        category_code: Some("borrow_in_company_pending_repayment".to_owned()),
                        expected_version: Some(1),
                    }],
                },
                WriteActor::oa_user("YNSYLP005", Some("trace-1".to_owned())),
            )
            .await
            .unwrap();

        assert_eq!(response.updated_transaction_ids.len(), 1);
        let stored = commands.lock().unwrap();
        let FinanceWriteCommand::BankCategoryUpdate(command) = stored.first().unwrap();
        assert_eq!(command.actor.actor_id, "YNSYLP005");
        assert_eq!(command.idempotency_key, "bank.category:request-1");
        assert_eq!(
            command.updates[0].category_code.as_deref(),
            Some("borrow_in_company_pending_repayment")
        );
        assert_eq!(
            command.request_payload["trusted_actor"]["actor_id"],
            "YNSYLP005"
        );
        assert_eq!(
            command.request_payload["updates"][0]["transaction_id"],
            json!("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
        );
    }
}
