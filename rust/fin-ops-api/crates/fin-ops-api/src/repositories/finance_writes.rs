use async_trait::async_trait;
use serde_json::{json, Value};
use sqlx::{PgPool, Row, Transaction};
use uuid::Uuid;

use crate::services::{
    finance_writes::{
        category_descriptor, BankCategoryUpdateCommand, BankCategoryUpdateResponse,
        BankCategoryUpdateResult, FinanceWriteCommand, FinanceWriteRepository,
        FinanceWriteRepositoryError,
    },
    workbench_writes::WriteActor,
};

#[derive(Clone)]
pub struct SqlxFinanceWriteRepository {
    pool: PgPool,
}

impl SqlxFinanceWriteRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl FinanceWriteRepository for SqlxFinanceWriteRepository {
    async fn execute(
        &self,
        command: FinanceWriteCommand,
    ) -> Result<BankCategoryUpdateResponse, FinanceWriteRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(response) = replay_idempotent_response(
            &mut tx,
            command.operation(),
            command.idempotency_key(),
            command.request_payload(),
        )
        .await?
        {
            tx.commit().await?;
            return Ok(response);
        }

        let response = match &command {
            FinanceWriteCommand::BankCategoryUpdate(command) => {
                execute_bank_category_update(&mut tx, command).await?
            }
        };
        record_idempotency(&mut tx, &command, &response).await?;
        tx.commit().await?;
        Ok(response)
    }
}

#[derive(Debug)]
struct BankTransactionTarget {
    transaction_id: Uuid,
    txn_month: String,
}

#[derive(Debug)]
struct ActiveCategory {
    id: Uuid,
    category_code: Option<String>,
    version: i64,
    raw_payload: Value,
}

async fn execute_bank_category_update(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &BankCategoryUpdateCommand,
) -> Result<BankCategoryUpdateResponse, FinanceWriteRepositoryError> {
    let mut affected_months = Vec::<String>::new();
    let mut updated_transaction_ids = Vec::<String>::new();
    let mut updated_categories = Vec::<BankCategoryUpdateResult>::new();
    let mut before = Vec::<Value>::new();
    let mut after = Vec::<Value>::new();
    let mut category_ids = Vec::<Uuid>::new();

    for update in &command.updates {
        let target = lock_bank_transaction(tx, update.transaction_id).await?;
        let active = lock_active_category(tx, target.transaction_id, &target.txn_month).await?;
        let actual_version = active
            .as_ref()
            .map(|category| category.version)
            .unwrap_or(0);
        if let Some(expected_version) = update.expected_version {
            if expected_version != actual_version {
                return Err(FinanceWriteRepositoryError::Conflict {
                    code: "category_version_conflict",
                    message: "Bank transaction category version conflict.".to_owned(),
                });
            }
        }
        let next_version = actual_version + 1;
        if let Some(active) = &active {
            replace_active_category(tx, active.id, &command.actor).await?;
        }
        let (category_label, category_path) = update
            .category_code
            .as_deref()
            .and_then(category_descriptor)
            .map(|(label, path)| {
                (
                    Some(label.to_owned()),
                    path.iter()
                        .map(|item| (*item).to_owned())
                        .collect::<Vec<_>>(),
                )
            })
            .unwrap_or((None, Vec::new()));
        let raw_payload = json!({
            "schema_version": "finops.bank_transaction_category.manual.v1",
            "category_code": update.category_code,
            "category_label": category_label,
            "category_path": category_path,
            "category_source": "manual",
            "category_version": next_version,
            "previous_category_code": active.as_ref().and_then(|category| category.category_code.clone()),
            "updated_by": command.actor.actor_id,
            "request_id": command.actor.request_id
        });
        let category_id = insert_bank_category(tx, &target, &command.actor, &raw_payload).await?;
        insert_bank_category_event(
            tx,
            category_id,
            &target,
            active.as_ref(),
            &raw_payload,
            &command.actor,
            &command.idempotency_key,
        )
        .await?;
        category_ids.push(category_id);
        affected_months.push(target.txn_month.clone());
        updated_transaction_ids.push(target.transaction_id.to_string());
        before.push(json!({
            "transaction_id": target.transaction_id,
            "category": active.as_ref().map(|category| &category.raw_payload)
        }));
        after.push(json!({
            "transaction_id": target.transaction_id,
            "category_id": category_id,
            "category": raw_payload
        }));
        updated_categories.push(BankCategoryUpdateResult {
            transaction_id: target.transaction_id.to_string(),
            category_code: update.category_code.clone(),
            category_label,
            category_path,
            version: next_version,
        });
    }

    affected_months.sort();
    affected_months.dedup();
    let aggregate_id = category_ids
        .first()
        .copied()
        .or_else(|| command.updates.first().map(|update| update.transaction_id))
        .ok_or(FinanceWriteRepositoryError::NotFound {
            resource: "bank_transaction",
        })?;
    let (rebuild_task_id, outbox_event_id) = enqueue_rebuild(
        tx,
        &command.actor,
        "bank_transaction.category.patch",
        aggregate_id,
        &command.idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "bank_transaction.category_changed",
        "patch",
        "bank_transaction_category",
        aggregate_id,
        &command.actor,
        &command.idempotency_key,
        json!({ "categories": before }),
        json!({ "categories": after }),
        json!({
            "affected_months": affected_months,
            "rebuild_task_id": rebuild_task_id,
            "outbox_event_id": outbox_event_id
        }),
    )
    .await?;

    Ok(BankCategoryUpdateResponse {
        updated_transaction_ids,
        updated_categories,
        affected_months,
        workbench_rebuild_queued: true,
        turnover_relations_updated: true,
        turnover_ledger_invalidated: true,
        rebuild_task_id: Some(rebuild_task_id.to_string()),
        outbox_event_id: Some(outbox_event_id.to_string()),
        idempotency_key: command.idempotency_key.clone(),
    })
}

const LOCK_BANK_TRANSACTION_SQL: &str = r#"
select id, to_char(txn_month, 'YYYY-MM') as txn_month
from app.bank_transactions
where id = $1
for update
"#;

const LOCK_ACTIVE_BANK_CATEGORY_SQL: &str = r#"
select
  id,
  case
    when raw_payload ? 'category_code' then nullif(raw_payload->>'category_code', '')
    else nullif(category_type, '')
  end as category_code,
  case
    when raw_payload->>'category_version' ~ '^[0-9]+$' then (raw_payload->>'category_version')::bigint
    when raw_payload->>'version' ~ '^[0-9]+$' then (raw_payload->>'version')::bigint
    else 1
  end as category_version,
  raw_payload
from app.bank_transaction_categories
where bank_transaction_id = $1
  and bank_transaction_month = to_date($2 || '-01', 'YYYY-MM-DD')
  and status = 'active'
order by updated_at desc, created_at desc, id
limit 1
for update
"#;

const REPLACE_ACTIVE_BANK_CATEGORY_SQL: &str = r#"
update app.bank_transaction_categories
set status = 'replaced',
    updated_by = $2,
    cancelled_by = $2,
    cancelled_at = now()
where id = $1
"#;

const INSERT_BANK_CATEGORY_SQL: &str = r#"
insert into app.bank_transaction_categories (
  id,
  bank_transaction_month,
  bank_transaction_id,
  category_type,
  status,
  amount,
  raw_payload,
  created_by,
  updated_by
)
values (
  $1,
  to_date($2 || '-01', 'YYYY-MM-DD'),
  $3,
  'other',
  'active',
  0,
  $4,
  $5,
  $5
)
"#;

const INSERT_BANK_CATEGORY_EVENT_SQL: &str = r#"
insert into app.bank_transaction_category_events (
  category_id,
  bank_transaction_month,
  bank_transaction_id,
  event_type,
  previous_status,
  new_status,
  amount,
  event_payload,
  raw_payload,
  idempotency_key,
  created_by
)
values (
  $1,
  to_date($2 || '-01', 'YYYY-MM-DD'),
  $3,
  $4,
  $5,
  'active',
  0,
  $6,
  $6,
  $7,
  $8
)
"#;

const ENQUEUE_REBUILD_SQL: &str = r#"
insert into job.worker_tasks (
  id,
  task_type,
  status,
  phase,
  priority,
  idempotency_key,
  visibility,
  label,
  source,
  payload,
  affected_scopes,
  affected_months,
  created_by
)
values (
  $1,
  'read_model.rebuild',
  'queued',
  'queued',
  0,
  $2,
  'system',
  '重建银行分类影响读模型',
  $3,
  $4,
  $5,
  array(select to_date(value || '-01', 'YYYY-MM-DD') from unnest($6::text[]) as value),
  $7
)
"#;

const INSERT_REBUILD_OUTBOX_SQL: &str = r#"
insert into job.outbox_events (
  id,
  aggregate_type,
  aggregate_id,
  event_type,
  subject,
  payload,
  status,
  idempotency_key,
  trace_id
)
values (
  $1,
  'bank_transaction_category',
  $2,
  'read_model.rebuild_requested',
  'finops.jobs.read_model.rebuild',
  $3,
  'pending',
  $4,
  $5
)
"#;

const INSERT_AUDIT_SQL: &str = r#"
insert into audit.events (
  event_type,
  action,
  entity_type,
  entity_id,
  actor_id,
  actor_type,
  trace_id,
  request_id,
  idempotency_key,
  before_state,
  after_state,
  diff,
  metadata
)
values ($1, $2, $3, $4, $5, 'user', $6, $6, $7, $8, $9, '{}'::jsonb, $10)
"#;

const RECORD_IDEMPOTENCY_SQL: &str = r#"
insert into app.write_idempotency_records (
  operation,
  idempotency_key,
  request_payload,
  response_payload,
  aggregate_type,
  aggregate_id,
  status,
  created_by
)
values ($1, $2, $3, $4, $5, $6, 'completed', $7)
"#;

async fn lock_bank_transaction(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    transaction_id: Uuid,
) -> Result<BankTransactionTarget, FinanceWriteRepositoryError> {
    let row = sqlx::query(LOCK_BANK_TRANSACTION_SQL)
        .bind(transaction_id)
        .fetch_optional(&mut **tx)
        .await?;
    let Some(row) = row else {
        return Err(FinanceWriteRepositoryError::NotFound {
            resource: "bank_transaction",
        });
    };
    Ok(BankTransactionTarget {
        transaction_id: row.try_get("id")?,
        txn_month: row.try_get("txn_month")?,
    })
}

async fn lock_active_category(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    transaction_id: Uuid,
    txn_month: &str,
) -> Result<Option<ActiveCategory>, FinanceWriteRepositoryError> {
    let row = sqlx::query(LOCK_ACTIVE_BANK_CATEGORY_SQL)
        .bind(transaction_id)
        .bind(txn_month)
        .fetch_optional(&mut **tx)
        .await?;
    row.map(|row| {
        Ok(ActiveCategory {
            id: row.try_get("id")?,
            category_code: row.try_get("category_code")?,
            version: row.try_get("category_version")?,
            raw_payload: row.try_get("raw_payload")?,
        })
    })
    .transpose()
}

async fn replace_active_category(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    category_id: Uuid,
    actor: &WriteActor,
) -> Result<(), FinanceWriteRepositoryError> {
    sqlx::query(REPLACE_ACTIVE_BANK_CATEGORY_SQL)
        .bind(category_id)
        .bind(&actor.actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok(())
}

async fn insert_bank_category(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    target: &BankTransactionTarget,
    actor: &WriteActor,
    raw_payload: &Value,
) -> Result<Uuid, FinanceWriteRepositoryError> {
    let category_id = Uuid::new_v4();
    sqlx::query(INSERT_BANK_CATEGORY_SQL)
        .bind(category_id)
        .bind(&target.txn_month)
        .bind(target.transaction_id)
        .bind(raw_payload)
        .bind(&actor.actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok(category_id)
}

async fn insert_bank_category_event(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    category_id: Uuid,
    target: &BankTransactionTarget,
    previous: Option<&ActiveCategory>,
    raw_payload: &Value,
    actor: &WriteActor,
    idempotency_key: &str,
) -> Result<(), FinanceWriteRepositoryError> {
    sqlx::query(INSERT_BANK_CATEGORY_EVENT_SQL)
        .bind(category_id)
        .bind(&target.txn_month)
        .bind(target.transaction_id)
        .bind(if previous.is_some() {
            "replaced"
        } else {
            "created"
        })
        .bind(previous.map(|_| "active"))
        .bind(raw_payload)
        .bind(format!(
            "bank.category.event:{idempotency_key}:{}",
            target.transaction_id
        ))
        .bind(&actor.actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok(())
}

async fn enqueue_rebuild(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    operation: &str,
    aggregate_id: Uuid,
    idempotency_key: &str,
    affected_months: &[String],
) -> Result<(Uuid, Uuid), FinanceWriteRepositoryError> {
    let task_id = Uuid::new_v4();
    let outbox_event_id = Uuid::new_v4();
    let scope_keys = rebuild_scope_keys(affected_months);
    let trace_id = actor
        .request_id
        .clone()
        .unwrap_or_else(|| format!("{operation}:{idempotency_key}"));
    let source = json!({
        "aggregate_type": "bank_transaction_category",
        "aggregate_id": aggregate_id,
        "operation": operation
    });
    let payload = json!({
        "schema_version": "finops.read_model.rebuild_requested.v1",
        "models": ["workbench", "search_index", "cost_statistics"],
        "scope_keys": scope_keys,
        "months": affected_months,
        "scope_type": "month",
        "reason": "bank_transaction.category_changed",
        "source": source,
        "source_versions": {
            "write_operation": operation
        },
        "priority": "normal",
        "force": false,
        "requested_by": actor.actor_id,
        "requested_by_type": actor.actor_type,
        "request_id": trace_id,
        "trace_id": trace_id
    });
    sqlx::query(ENQUEUE_REBUILD_SQL)
        .bind(task_id)
        .bind(format!(
            "worker:read_model.rebuild:{operation}:{idempotency_key}"
        ))
        .bind(source)
        .bind(payload.clone())
        .bind(&scope_keys)
        .bind(affected_months)
        .bind(&actor.actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    sqlx::query(INSERT_REBUILD_OUTBOX_SQL)
        .bind(outbox_event_id)
        .bind(aggregate_id)
        .bind(payload)
        .bind(format!(
            "outbox:read_model.rebuild:{operation}:{idempotency_key}"
        ))
        .bind(trace_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok((task_id, outbox_event_id))
}

async fn insert_audit_event(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    event_type: &str,
    action: &str,
    entity_type: &str,
    entity_id: Uuid,
    actor: &WriteActor,
    idempotency_key: &str,
    before_state: Value,
    after_state: Value,
    metadata: Value,
) -> Result<(), FinanceWriteRepositoryError> {
    let trace_id = actor
        .request_id
        .clone()
        .unwrap_or_else(|| idempotency_key.to_owned());
    sqlx::query(INSERT_AUDIT_SQL)
        .bind(event_type)
        .bind(action)
        .bind(entity_type)
        .bind(entity_id)
        .bind(&actor.actor_id)
        .bind(trace_id)
        .bind(idempotency_key)
        .bind(before_state)
        .bind(after_state)
        .bind(metadata)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok(())
}

async fn replay_idempotent_response(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    operation: &str,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<Option<BankCategoryUpdateResponse>, FinanceWriteRepositoryError> {
    let row = sqlx::query(
        r#"
        select request_payload, response_payload
        from app.write_idempotency_records
        where operation = $1 and idempotency_key = $2
        "#,
    )
    .bind(operation)
    .bind(idempotency_key)
    .fetch_optional(&mut **tx)
    .await?;
    let Some(row) = row else {
        return Ok(None);
    };
    let stored_request: Value = row.try_get("request_payload")?;
    if stored_request != *request_payload {
        return Err(FinanceWriteRepositoryError::IdempotencyConflict);
    }
    let mut response: BankCategoryUpdateResponse =
        serde_json::from_value(row.try_get("response_payload")?).map_err(|error| {
            FinanceWriteRepositoryError::Conflict {
                code: "invalid_write_state",
                message: format!("stored idempotency response is invalid: {error}"),
            }
        })?;
    response.workbench_rebuild_queued = true;
    Ok(Some(response))
}

async fn record_idempotency(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &FinanceWriteCommand,
    response: &BankCategoryUpdateResponse,
) -> Result<(), FinanceWriteRepositoryError> {
    let aggregate_id = response
        .updated_transaction_ids
        .first()
        .and_then(|value| Uuid::parse_str(value).ok())
        .ok_or(FinanceWriteRepositoryError::NotFound {
            resource: "bank_transaction",
        })?;
    sqlx::query(RECORD_IDEMPOTENCY_SQL)
        .bind(command.operation())
        .bind(command.idempotency_key())
        .bind(command.request_payload())
        .bind(serde_json::to_value(response).unwrap_or_else(|_| json!({})))
        .bind("bank_transaction")
        .bind(aggregate_id)
        .bind(command.actor_id())
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    Ok(())
}

fn rebuild_scope_keys(affected_months: &[String]) -> Vec<String> {
    let mut keys = Vec::new();
    for month in affected_months {
        keys.push(format!("workbench:{month}"));
        keys.push(format!("search_index:{month}"));
        keys.push(format!("cost_statistics:{month}:active"));
        keys.push(format!("cost_statistics:{month}:all"));
    }
    keys.sort();
    keys.dedup();
    keys
}

fn map_sqlx_error(error: sqlx::Error) -> FinanceWriteRepositoryError {
    if let sqlx::Error::Database(database_error) = &error {
        if database_error.is_unique_violation() {
            return FinanceWriteRepositoryError::IdempotencyConflict;
        }
    }
    FinanceWriteRepositoryError::Database(error)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bank_category_write_sql_uses_postgresql_facts_and_rebuild_outbox_only() {
        assert!(LOCK_BANK_TRANSACTION_SQL.contains("from app.bank_transactions"));
        assert!(LOCK_ACTIVE_BANK_CATEGORY_SQL.contains("from app.bank_transaction_categories"));
        assert!(INSERT_BANK_CATEGORY_SQL.contains("insert into app.bank_transaction_categories"));
        assert!(REPLACE_ACTIVE_BANK_CATEGORY_SQL.contains("status = 'replaced'"));
        assert!(INSERT_BANK_CATEGORY_EVENT_SQL
            .contains("insert into app.bank_transaction_category_events"));
        assert!(ENQUEUE_REBUILD_SQL.contains("insert into job.worker_tasks"));
        assert!(INSERT_REBUILD_OUTBOX_SQL.contains("read_model.rebuild_requested"));
        assert!(INSERT_AUDIT_SQL.contains("insert into audit.events"));
        assert!(RECORD_IDEMPOTENCY_SQL.contains("insert into app.write_idempotency_records"));
        let all_sql = [
            LOCK_BANK_TRANSACTION_SQL,
            LOCK_ACTIVE_BANK_CATEGORY_SQL,
            INSERT_BANK_CATEGORY_SQL,
            REPLACE_ACTIVE_BANK_CATEGORY_SQL,
            INSERT_BANK_CATEGORY_EVENT_SQL,
            ENQUEUE_REBUILD_SQL,
            INSERT_REBUILD_OUTBOX_SQL,
            INSERT_AUDIT_SQL,
            RECORD_IDEMPOTENCY_SQL,
        ]
        .join("\n");
        assert!(!all_sql.contains("app.mongo"));
        assert!(!all_sql.contains("oa_source"));
    }
}
