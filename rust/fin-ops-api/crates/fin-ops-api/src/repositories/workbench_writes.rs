use std::collections::{BTreeMap, BTreeSet};

use async_trait::async_trait;
use serde_json::{json, Value};
use sqlx::{PgPool, Row, Transaction};
use uuid::Uuid;

use crate::services::workbench_writes::{
    WorkbenchWriteCommand, WorkbenchWriteRepository, WorkbenchWriteRepositoryError,
    WorkbenchWriteResponse, WriteActor,
};

#[derive(Clone)]
pub struct SqlxWorkbenchWriteRepository {
    pool: PgPool,
}

impl SqlxWorkbenchWriteRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl WorkbenchWriteRepository for SqlxWorkbenchWriteRepository {
    async fn execute(
        &self,
        command: WorkbenchWriteCommand,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
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
            WorkbenchWriteCommand::ConfirmLink {
                actor,
                month,
                row_ids,
                case_id,
                note,
                ..
            } => {
                confirm_link(
                    &mut tx,
                    actor,
                    month,
                    row_ids,
                    *case_id,
                    note.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::RevokeLink {
                action,
                actor,
                month,
                case_id,
                row_ids,
                expected_version,
                note,
                ..
            } => {
                revoke_link(
                    &mut tx,
                    action,
                    actor,
                    month,
                    *case_id,
                    row_ids,
                    *expected_version,
                    note.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::ExceptionApply {
                actor,
                month,
                row_ids,
                scenario_code,
                action_code,
                payload,
                ..
            } => {
                apply_exception(
                    &mut tx,
                    actor,
                    month,
                    row_ids,
                    scenario_code,
                    action_code,
                    payload,
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::SpecialReconciliationAction {
                action,
                actor,
                month,
                row_ids,
                expected_version,
                note,
                special_metadata,
                ..
            } => {
                update_special_reconciliation_metadata(
                    &mut tx,
                    action,
                    actor,
                    month,
                    row_ids,
                    *expected_version,
                    note.as_deref(),
                    special_metadata,
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::ExceptionCancel {
                actor,
                month,
                exception_case_id,
                row_ids,
                expected_version,
                comment,
                ..
            } => {
                cancel_exception(
                    &mut tx,
                    actor,
                    month,
                    *exception_case_id,
                    row_ids,
                    *expected_version,
                    comment.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::IgnoreRow {
                actor,
                month,
                row_id,
                comment,
                ..
            } => {
                ignore_row(
                    &mut tx,
                    actor,
                    month,
                    *row_id,
                    comment.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::UnignoreRow {
                actor,
                month,
                row_id,
                expected_version,
                ..
            } => {
                unignore_row(
                    &mut tx,
                    actor,
                    month,
                    *row_id,
                    *expected_version,
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::NoOaBatchSubmit {
                actor,
                batch_id,
                expected_version,
                note,
                ..
            } => {
                submit_no_oa_batch(
                    &mut tx,
                    actor,
                    *batch_id,
                    *expected_version,
                    note.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
            WorkbenchWriteCommand::NoOaBatchWithdraw {
                actor,
                batch_id,
                expected_version,
                reason,
                ..
            } => {
                withdraw_no_oa_batch(
                    &mut tx,
                    actor,
                    *batch_id,
                    *expected_version,
                    reason.as_deref(),
                    command.idempotency_key(),
                    command.request_payload(),
                )
                .await?
            }
        };

        record_idempotency(&mut tx, &command, &response).await?;
        tx.commit().await?;
        Ok(response)
    }
}

#[derive(Debug, Clone)]
struct WorkbenchRowRef {
    row_id: Uuid,
    row_type: String,
    source_entity_type: String,
    source_entity_id: Uuid,
    scope_month: String,
}

#[derive(Debug, Clone)]
struct LockedFactRow {
    row_type: String,
    object_type: String,
    object_id: Uuid,
    object_month: String,
    amount_cents: i64,
    written_off_amount_cents: i64,
    status: String,
    direction: String,
    source_snapshot: Value,
}

#[derive(Debug, Clone)]
struct AppliedFactRow {
    row_type: String,
    object_type: String,
    object_id: Uuid,
    object_month: String,
    applied_amount_cents: i64,
    source_snapshot: Value,
}

#[derive(Debug, Clone)]
struct ReconciliationFacts {
    rows: Vec<AppliedFactRow>,
    total_amount_cents: i64,
    difference_amount_cents: i64,
    biz_side: &'static str,
}

impl ReconciliationFacts {
    fn from_locked_rows(rows: &[LockedFactRow]) -> Result<Self, WorkbenchWriteRepositoryError> {
        if rows.is_empty() {
            return Err(conflict(
                "invalid_row_ids",
                "at least one fact row is required",
            ));
        }

        let mut totals_by_type = BTreeMap::<String, i64>::new();
        let mut directions = BTreeSet::<&'static str>::new();
        let mut applied_rows = Vec::with_capacity(rows.len());
        for row in rows {
            validate_fact_row_for_confirm(row)?;
            let open_amount = row.amount_cents - row.written_off_amount_cents;
            *totals_by_type.entry(row.row_type.clone()).or_default() += open_amount;
            match row.row_type.as_str() {
                "bank" => match row.direction.as_str() {
                    "inflow" => {
                        directions.insert("receivable");
                    }
                    "outflow" => {
                        directions.insert("payable");
                    }
                    _ => {}
                },
                "invoice" => match row.direction.as_str() {
                    "output" => {
                        directions.insert("receivable");
                    }
                    "input" => {
                        directions.insert("payable");
                    }
                    _ => {}
                },
                _ => {}
            }
            applied_rows.push(AppliedFactRow {
                row_type: row.row_type.clone(),
                object_type: row.object_type.clone(),
                object_id: row.object_id,
                object_month: row.object_month.clone(),
                applied_amount_cents: open_amount,
                source_snapshot: row.source_snapshot.clone(),
            });
        }

        let mut totals = totals_by_type
            .values()
            .copied()
            .filter(|value| *value > 0)
            .collect::<Vec<_>>();
        totals.sort();
        let total_amount_cents = totals.iter().copied().max().unwrap_or(0);
        let difference_amount_cents = match (totals.first(), totals.last()) {
            (Some(first), Some(last)) => last - first,
            _ => 0,
        };
        let biz_side = match directions.len() {
            1 => *directions.iter().next().unwrap(),
            0 => "unknown",
            _ => "mixed",
        };

        Ok(Self {
            rows: applied_rows,
            total_amount_cents,
            difference_amount_cents,
            biz_side,
        })
    }
}

#[derive(Debug, Clone, Copy)]
enum FactMutation {
    Confirm,
    Revoke,
}

async fn replay_idempotent_response(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    operation: &str,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<Option<WorkbenchWriteResponse>, WorkbenchWriteRepositoryError> {
    let row = sqlx::query(
        r#"
        select request_payload, response_payload
        from app.write_idempotency_records
        where operation = $1 and idempotency_key = $2
        for update
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
        return Err(WorkbenchWriteRepositoryError::IdempotencyConflict);
    }
    let mut response: WorkbenchWriteResponse =
        serde_json::from_value(row.try_get("response_payload")?).map_err(|error| {
            WorkbenchWriteRepositoryError::Conflict {
                code: "invalid_write_state",
                message: format!("stored idempotency response is invalid: {error}"),
            }
        })?;
    response.idempotent_replay = true;
    Ok(Some(response))
}

async fn record_idempotency(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &WorkbenchWriteCommand,
    response: &WorkbenchWriteResponse,
) -> Result<(), WorkbenchWriteRepositoryError> {
    let response_payload = serde_json::to_value(response).unwrap_or_else(|_| json!({}));
    let (aggregate_type, aggregate_id) = aggregate_for_response(response)?;
    sqlx::query(
        r#"
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
        "#,
    )
    .bind(command.operation())
    .bind(command.idempotency_key())
    .bind(command.request_payload())
    .bind(response_payload)
    .bind(aggregate_type)
    .bind(aggregate_id)
    .bind(command.actor_id())
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok(())
}

fn aggregate_for_response(
    response: &WorkbenchWriteResponse,
) -> Result<(&'static str, Uuid), WorkbenchWriteRepositoryError> {
    if let Some(case_id) = &response.case_id {
        return Ok(("reconciliation_case", parse_uuid_response(case_id)?));
    }
    if let Some(exception_case_id) = &response.exception_case_id {
        return Ok((
            "workbench_exception_case",
            parse_uuid_response(exception_case_id)?,
        ));
    }
    if let Some(batch_id) = &response.batch_id {
        return Ok(("no_oa_bank_batch", parse_uuid_response(batch_id)?));
    }
    Err(WorkbenchWriteRepositoryError::Conflict {
        code: "invalid_write_state",
        message: "write response is missing aggregate id".to_owned(),
    })
}

fn parse_uuid_response(value: &str) -> Result<Uuid, WorkbenchWriteRepositoryError> {
    Uuid::parse_str(value).map_err(|_| WorkbenchWriteRepositoryError::Conflict {
        code: "invalid_write_state",
        message: "write response aggregate id is not a UUID".to_owned(),
    })
}

async fn confirm_link(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    month: &str,
    row_ids: &[Uuid],
    case_id: Uuid,
    note: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = load_workbench_rows(tx, month, row_ids).await?;
    ensure_rows_unbound(tx, &rows).await?;
    let facts = load_locked_fact_rows(tx, &rows).await?;
    let reconciliation = ReconciliationFacts::from_locked_rows(&facts)?;

    sqlx::query(
        r#"
        insert into app.reconciliation_cases (
          id,
          case_type,
          biz_side,
          total_amount,
          difference_amount,
          status,
          remark,
          idempotency_key,
          confirmed_at,
          created_by,
          raw_payload
        )
        values ($1, 'manual', $2, $3::numeric, $4::numeric, 'confirmed', $5, $6, now(), $7, $8)
        "#,
    )
    .bind(case_id)
    .bind(reconciliation.biz_side)
    .bind(amount_string(reconciliation.total_amount_cents))
    .bind(amount_string(reconciliation.difference_amount_cents))
    .bind(note)
    .bind(idempotency_key)
    .bind(&actor.actor_id)
    .bind(request_payload)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;

    for row in &reconciliation.rows {
        sqlx::query(
            r#"
            insert into app.reconciliation_case_rows (
              case_id,
              object_type,
              object_id,
              object_month,
              side_role,
              applied_amount,
              binding_status,
              source_snapshot,
              raw_payload
            )
            values (
              $1,
              $2,
              $3,
              to_date($4 || '-01', 'YYYY-MM-DD'),
              $5,
              $6::numeric,
              'active',
              $7,
              $8
            )
            "#,
        )
        .bind(case_id)
        .bind(&row.object_type)
        .bind(row.object_id)
        .bind(&row.object_month)
        .bind(side_role(&row.row_type))
        .bind(amount_string(row.applied_amount_cents))
        .bind(row.source_snapshot.clone())
        .bind(request_payload)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
        mutate_fact_written_off(tx, row, FactMutation::Confirm).await?;
    }

    let affected_months = months_from_rows(&rows);
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "confirm_link",
        "reconciliation.confirmed",
        "reconciliation_case",
        case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "reconciliation.confirmed",
        "confirm_link",
        "reconciliation_case",
        case_id,
        actor,
        idempotency_key,
        json!({}),
        json!({
            "status": "confirmed",
            "row_ids": row_ids,
            "total_amount": amount_string(reconciliation.total_amount_cents),
            "difference_amount": amount_string(reconciliation.difference_amount_cents)
        }),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "confirm_link",
        rows.iter().map(|row| row.row_id).collect(),
        affected_months,
        Some(case_id),
        None,
        None,
        Some(1),
        task_id,
        outbox_id,
        format!("已确认 {} 条记录关联。", rows.len()),
    ))
}

async fn revoke_link(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    action: &str,
    actor: &WriteActor,
    month: &str,
    case_id: Option<Uuid>,
    row_ids: &[Uuid],
    expected_version: i32,
    note: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let (resolved_case_id, affected_row_ids, affected_months) = match case_id {
        Some(case_id) => {
            let refs = load_case_row_refs(tx, case_id).await?;
            (
                case_id,
                refs.iter()
                    .map(|row| row.row_id.unwrap_or(row.source_entity_id))
                    .collect(),
                months_from_case_refs(&refs, month),
            )
        }
        None => {
            let rows = load_workbench_rows(tx, month, row_ids).await?;
            let case_id = active_case_id_for_rows(tx, &rows).await?;
            (
                case_id,
                rows.iter().map(|row| row.row_id).collect(),
                months_from_rows(&rows),
            )
        }
    };

    let case_row = sqlx::query(
        r#"
        select status, row_version
        from app.reconciliation_cases
        where id = $1
        for update
        "#,
    )
    .bind(resolved_case_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "reconciliation_case",
    })?;
    let status: String = case_row.try_get("status")?;
    let row_version: i32 = case_row.try_get("row_version")?;
    if row_version != expected_version {
        return Err(conflict(
            "version_conflict",
            "reconciliation case version conflict",
        ));
    }
    if status == "cancelled" {
        return Err(conflict(
            "invalid_write_state",
            "reconciliation case is already cancelled",
        ));
    }

    let updated = sqlx::query(
        r#"
        update app.reconciliation_cases
        set
          status = 'cancelled',
          cancelled_at = now(),
          row_version = row_version + 1,
          raw_payload = raw_payload || jsonb_build_object(
            'cancelled_by', $2::text,
            'cancel_note', $3::text
          )
        where id = $1 and row_version = $4
        returning row_version
        "#,
    )
    .bind(resolved_case_id)
    .bind(&actor.actor_id)
    .bind(note.unwrap_or(""))
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?;
    let updated_version = updated
        .ok_or_else(|| conflict("version_conflict", "reconciliation case version conflict"))?
        .try_get("row_version")?;
    let case_rows = load_case_row_refs(tx, resolved_case_id).await?;
    for row in &case_rows {
        mutate_case_row_fact_written_off(tx, row, FactMutation::Revoke).await?;
    }
    sqlx::query(
        r#"
        update app.reconciliation_case_rows
        set binding_status = 'reverted'
        where case_id = $1 and binding_status = 'active'
        "#,
    )
    .bind(resolved_case_id)
    .execute(&mut **tx)
    .await?;

    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        action,
        "reconciliation.revoked",
        "reconciliation_case",
        resolved_case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "reconciliation.revoked",
        action,
        "reconciliation_case",
        resolved_case_id,
        actor,
        idempotency_key,
        json!({"status": status, "row_version": row_version}),
        json!({"status": "cancelled", "row_version": updated_version}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        action,
        affected_row_ids,
        affected_months,
        Some(resolved_case_id),
        None,
        None,
        Some(updated_version),
        task_id,
        outbox_id,
        "已撤销核销关系。".to_owned(),
    ))
}

async fn apply_exception(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    month: &str,
    row_ids: &[Uuid],
    scenario_code: &str,
    action_code: &str,
    payload: &Value,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = load_workbench_rows(tx, month, row_ids).await?;
    let exception_case_id = Uuid::new_v4();
    let source_invoice_ids = source_ids_for_type(&rows, "invoice");
    let source_bank_txn_ids = source_ids_for_type(&rows, "bank");
    let resolution_action = resolution_action(action_code);
    sqlx::query(
        r#"
        insert into app.workbench_exception_cases (
          id,
          biz_side,
          exception_code,
          exception_title,
          status,
          resolution_action,
          note,
          source_invoice_ids,
          source_bank_txn_ids,
          created_by,
          resolved_by,
          resolved_at,
          idempotency_key,
          raw_payload
        )
        values (
          $1,
          'unknown',
          $2,
          $3,
          'resolved',
          $4,
          $5,
          $6,
          $7,
          $8,
          $8,
          now(),
          $9,
          $10
        )
        "#,
    )
    .bind(exception_case_id)
    .bind(scenario_code)
    .bind(action_code)
    .bind(resolution_action)
    .bind(payload.get("note").and_then(Value::as_str).unwrap_or(""))
    .bind(source_invoice_ids)
    .bind(source_bank_txn_ids)
    .bind(&actor.actor_id)
    .bind(idempotency_key)
    .bind(request_payload)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;

    let affected_months = months_from_rows(&rows);
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "exception.apply",
        "exception.updated",
        "workbench_exception_case",
        exception_case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "exception.updated",
        "exception.apply",
        "workbench_exception_case",
        exception_case_id,
        actor,
        idempotency_key,
        json!({}),
        json!({"status": "resolved", "row_ids": row_ids}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "exception.apply",
        rows.iter().map(|row| row.row_id).collect(),
        affected_months,
        None,
        Some(exception_case_id),
        None,
        Some(1),
        task_id,
        outbox_id,
        "已处理异常。".to_owned(),
    ))
}

async fn cancel_exception(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    month: &str,
    exception_case_id: Option<Uuid>,
    row_ids: &[Uuid],
    expected_version: i32,
    comment: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = if row_ids.is_empty() {
        Vec::new()
    } else {
        load_workbench_rows(tx, month, row_ids).await?
    };
    let resolved_case_id = match exception_case_id {
        Some(value) => value,
        None => active_exception_case_for_rows(tx, &rows).await?,
    };
    let case_row = sqlx::query(
        r#"
        select status, row_version
        from app.workbench_exception_cases
        where id = $1
        for update
        "#,
    )
    .bind(resolved_case_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "exception_case",
    })?;
    let status: String = case_row.try_get("status")?;
    let row_version: i32 = case_row.try_get("row_version")?;
    if row_version != expected_version {
        return Err(conflict(
            "version_conflict",
            "exception case version conflict",
        ));
    }
    if status == "cancelled" {
        return Err(conflict(
            "invalid_write_state",
            "exception case is already cancelled",
        ));
    }
    let updated_version: i32 = sqlx::query(
        r#"
        update app.workbench_exception_cases
        set
          status = 'cancelled',
          resolved_at = coalesce(resolved_at, now()),
          cancelled_at = now(),
          cancelled_by = $2,
          row_version = row_version + 1,
          raw_payload = raw_payload || jsonb_build_object('cancel_comment', $3::text)
        where id = $1 and row_version = $4
        returning row_version
        "#,
    )
    .bind(resolved_case_id)
    .bind(&actor.actor_id)
    .bind(comment.unwrap_or(""))
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or_else(|| conflict("version_conflict", "exception case version conflict"))?
    .try_get("row_version")?;
    let affected_months = if rows.is_empty() {
        vec![month.to_owned()]
    } else {
        months_from_rows(&rows)
    };
    let affected_row_ids = rows.iter().map(|row| row.row_id).collect();
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "exception.cancel",
        "exception.updated",
        "workbench_exception_case",
        resolved_case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "exception.updated",
        "exception.cancel",
        "workbench_exception_case",
        resolved_case_id,
        actor,
        idempotency_key,
        json!({"status": status, "row_version": row_version}),
        json!({"status": "cancelled", "row_version": updated_version}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "exception.cancel",
        affected_row_ids,
        affected_months,
        None,
        Some(resolved_case_id),
        None,
        Some(updated_version),
        task_id,
        outbox_id,
        "已撤回异常处理。".to_owned(),
    ))
}

async fn update_special_reconciliation_metadata(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    action: &str,
    actor: &WriteActor,
    month: &str,
    row_ids: &[Uuid],
    expected_version: i32,
    note: Option<&str>,
    special_metadata: &Value,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = load_workbench_rows(tx, month, row_ids).await?;
    let case_id = active_case_id_for_rows(tx, &rows).await?;
    let case_row = sqlx::query(
        r#"
        select status, row_version, raw_payload
        from app.reconciliation_cases
        where id = $1
        for update
        "#,
    )
    .bind(case_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "reconciliation_case",
    })?;
    let status: String = case_row.try_get("status")?;
    let row_version: i32 = case_row.try_get("row_version")?;
    let raw_payload: Value = case_row.try_get("raw_payload")?;
    if row_version != expected_version {
        return Err(conflict(
            "version_conflict",
            "reconciliation case version conflict",
        ));
    }
    if status != "confirmed" {
        return Err(conflict(
            "invalid_write_state",
            "only confirmed reconciliation cases can receive special metadata",
        ));
    }
    validate_special_action_against_rows(action, &rows)?;
    let updated_version: i32 = sqlx::query(
        r#"
        update app.reconciliation_cases
        set
          raw_payload = raw_payload || jsonb_build_object(
            'special_metadata', $2::jsonb,
            'special_action', $3::text,
            'special_note', $4::text,
            'special_updated_by', $5::text
          ),
          row_version = row_version + 1,
          updated_at = now()
        where id = $1 and row_version = $6
        returning row_version
        "#,
    )
    .bind(case_id)
    .bind(special_metadata)
    .bind(action)
    .bind(note.unwrap_or(""))
    .bind(&actor.actor_id)
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or_else(|| conflict("version_conflict", "reconciliation case version conflict"))?
    .try_get("row_version")?;

    let affected_months = months_from_rows(&rows);
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        action,
        "reconciliation.confirmed",
        "reconciliation_case",
        case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "reconciliation.confirmed",
        action,
        "reconciliation_case",
        case_id,
        actor,
        idempotency_key,
        json!({"row_version": row_version, "raw_payload": raw_payload}),
        json!({"row_version": updated_version, "special_metadata": special_metadata}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        action,
        rows.iter().map(|row| row.row_id).collect(),
        affected_months,
        Some(case_id),
        None,
        None,
        Some(updated_version),
        task_id,
        outbox_id,
        "已更新特殊处理。".to_owned(),
    ))
}

fn validate_special_action_against_rows(
    action: &str,
    rows: &[WorkbenchRowRef],
) -> Result<(), WorkbenchWriteRepositoryError> {
    let row_types = rows
        .iter()
        .map(|row| row.row_type.as_str())
        .collect::<BTreeSet<_>>();
    match action {
        "confirm_cash_pass_through" => {
            if !row_types.contains("oa")
                || !row_types.contains("bank")
                || row_types.contains("invoice")
            {
                return Err(conflict(
                    "invalid_write_state",
                    "cash pass-through requires OA and bank rows without invoice rows",
                ));
            }
        }
        "confirm_cash_ticket_purchase" => {
            if !row_types.contains("oa")
                || !row_types.contains("bank")
                || !row_types.contains("invoice")
            {
                return Err(conflict(
                    "invalid_write_state",
                    "cash ticket purchase requires OA, bank, and invoice rows",
                ));
            }
        }
        "cancel_cash_special" => {}
        _ => {
            return Err(conflict(
                "invalid_write_state",
                format!("unsupported special reconciliation action: {action}"),
            ));
        }
    }
    Ok(())
}

async fn ignore_row(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    month: &str,
    row_id: Uuid,
    comment: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = load_workbench_rows(tx, month, &[row_id]).await?;
    let row = rows
        .first()
        .expect("load_workbench_rows returns requested row");
    let exception_case_id = Uuid::new_v4();
    sqlx::query(
        r#"
        insert into app.workbench_exception_cases (
          id,
          biz_side,
          exception_code,
          exception_title,
          status,
          resolution_action,
          note,
          source_invoice_ids,
          source_bank_txn_ids,
          created_by,
          resolved_by,
          resolved_at,
          idempotency_key,
          raw_payload
        )
        values (
          $1,
          'unknown',
          'manual_ignore',
          'ignore row',
          'ignored',
          'ignore',
          $2,
          $3,
          $4,
          $5,
          $5,
          now(),
          $6,
          $7
        )
        "#,
    )
    .bind(exception_case_id)
    .bind(comment.unwrap_or(""))
    .bind(source_ids_for_type(&rows, "invoice"))
    .bind(source_ids_for_type(&rows, "bank"))
    .bind(&actor.actor_id)
    .bind(idempotency_key)
    .bind(request_payload)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;

    sqlx::query(
        r#"
        insert into app.workbench_row_overrides (
          row_type,
          source_object_type,
          source_object_id,
          scope_month,
          override_type,
          override_payload,
          raw_payload,
          status,
          created_by,
          idempotency_key
        )
        values (
          $1,
          $2,
          $3,
          to_date($4 || '-01', 'YYYY-MM-DD'),
          'ignore',
          $5,
          $6,
          'active',
          $7,
          $8
        )
        "#,
    )
    .bind(&row.row_type)
    .bind(&row.source_entity_type)
    .bind(row.source_entity_id)
    .bind(&row.scope_month)
    .bind(json!({"comment": comment.unwrap_or(""), "exception_case_id": exception_case_id}))
    .bind(request_payload)
    .bind(&actor.actor_id)
    .bind(idempotency_key)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;

    let affected_months = months_from_rows(&rows);
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "row_override.ignore",
        "exception.updated",
        "workbench_exception_case",
        exception_case_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "exception.updated",
        "row_override.ignore",
        "workbench_exception_case",
        exception_case_id,
        actor,
        idempotency_key,
        json!({}),
        json!({"status": "ignored", "row_id": row_id}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "row_override.ignore",
        vec![row_id],
        affected_months,
        None,
        Some(exception_case_id),
        None,
        Some(1),
        task_id,
        outbox_id,
        "已忽略 1 条记录。".to_owned(),
    ))
}

async fn unignore_row(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    month: &str,
    row_id: Uuid,
    expected_version: i32,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let rows = load_workbench_rows(tx, month, &[row_id]).await?;
    let row = rows
        .first()
        .expect("load_workbench_rows returns requested row");
    let override_row = sqlx::query(
        r#"
        select id, row_version
        from app.workbench_row_overrides
        where source_object_type = $1
          and source_object_id = $2
          and scope_month = to_date($3 || '-01', 'YYYY-MM-DD')
          and override_type = 'ignore'
          and status = 'active'
        for update
        "#,
    )
    .bind(&row.source_entity_type)
    .bind(row.source_entity_id)
    .bind(&row.scope_month)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "workbench_row",
    })?;
    let override_id: Uuid = override_row.try_get("id")?;
    let row_version: i32 = override_row.try_get("row_version")?;
    if row_version != expected_version {
        return Err(conflict(
            "version_conflict",
            "row override version conflict",
        ));
    }
    let updated_version: i32 = sqlx::query(
        r#"
        update app.workbench_row_overrides
        set
          status = 'cancelled',
          cancelled_at = now(),
          cancelled_by = $2,
          row_version = row_version + 1
        where id = $1 and row_version = $3
        returning row_version
        "#,
    )
    .bind(override_id)
    .bind(&actor.actor_id)
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or_else(|| conflict("version_conflict", "row override version conflict"))?
    .try_get("row_version")?;
    sqlx::query(
        r#"
        update app.workbench_exception_cases
        set
          status = 'cancelled',
          resolved_at = coalesce(resolved_at, now()),
          cancelled_at = now(),
          cancelled_by = $3,
          row_version = row_version + 1
        where status = 'ignored'
          and (
            source_invoice_ids && $1::uuid[]
            or source_bank_txn_ids && $2::uuid[]
          )
        "#,
    )
    .bind(source_ids_for_type(&rows, "invoice"))
    .bind(source_ids_for_type(&rows, "bank"))
    .bind(&actor.actor_id)
    .execute(&mut **tx)
    .await?;

    let affected_months = months_from_rows(&rows);
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "row_override.unignore",
        "exception.updated",
        "workbench_row_override",
        override_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "exception.updated",
        "row_override.unignore",
        "workbench_row_override",
        override_id,
        actor,
        idempotency_key,
        json!({"row_version": row_version}),
        json!({"status": "cancelled", "row_version": updated_version}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "row_override.unignore",
        vec![row_id],
        affected_months,
        None,
        None,
        None,
        Some(updated_version),
        task_id,
        outbox_id,
        "已撤回忽略 1 条记录。".to_owned(),
    ))
}

async fn submit_no_oa_batch(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    batch_id: Uuid,
    expected_version: i32,
    note: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let batch = lock_no_oa_batch(tx, batch_id).await?;
    let status: String = batch.try_get("status")?;
    let row_version: i32 = batch.try_get("row_version")?;
    if row_version != expected_version {
        return Err(conflict("version_conflict", "no-OA batch version conflict"));
    }
    if status != "draft" {
        return Err(conflict(
            "invalid_write_state",
            "only draft no-OA batches can be submitted",
        ));
    }
    let scope_month = batch.try_get::<String, _>("scope_month")?;
    let bank_transaction_ids: Vec<Uuid> = batch.try_get("bank_transaction_ids")?;
    let facts = load_locked_bank_transaction_facts(tx, &scope_month, &bank_transaction_ids).await?;
    ensure_fact_rows_unbound(tx, &facts).await?;
    let reconciliation = ReconciliationFacts::from_locked_rows(&facts)?;
    let relation_case_id = Uuid::new_v4();
    sqlx::query(
        r#"
        insert into app.reconciliation_cases (
          id,
          case_type,
          biz_side,
          total_amount,
          difference_amount,
          status,
          remark,
          idempotency_key,
          confirmed_at,
          created_by,
          raw_payload
        )
        values ($1, 'manual', $2, $3::numeric, $4::numeric, 'confirmed', $5, $6, now(), $7, $8)
        "#,
    )
    .bind(relation_case_id)
    .bind(reconciliation.biz_side)
    .bind(amount_string(reconciliation.total_amount_cents))
    .bind(amount_string(reconciliation.difference_amount_cents))
    .bind(note.unwrap_or("免OA流水批量处理"))
    .bind(format!("no_oa_batch.submit:{idempotency_key}"))
    .bind(&actor.actor_id)
    .bind(request_payload)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    for fact in &reconciliation.rows {
        sqlx::query(
            r#"
            insert into app.reconciliation_case_rows (
              case_id,
              object_type,
              object_id,
              object_month,
              side_role,
              applied_amount,
              binding_status,
              source_snapshot,
              raw_payload
            )
            values (
              $1,
              $2,
              $3,
              to_date($4 || '-01', 'YYYY-MM-DD'),
              'bank',
              $5::numeric,
              'active',
              $6,
              $7
            )
            "#,
        )
        .bind(relation_case_id)
        .bind(&fact.object_type)
        .bind(fact.object_id)
        .bind(&fact.object_month)
        .bind(amount_string(fact.applied_amount_cents))
        .bind(json!({
            "source": "no_oa_bank_batch",
            "batch_id": batch_id,
            "fact": fact.source_snapshot
        }))
        .bind(request_payload)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
        mutate_fact_written_off(tx, fact, FactMutation::Confirm).await?;
    }
    let updated_version: i32 = sqlx::query(
        r#"
        update app.no_oa_bank_batches
        set
          status = 'submitted',
          submitted_at = now(),
          relation_case_id = $2,
          row_version = row_version + 1
        where id = $1 and row_version = $3
        returning row_version
        "#,
    )
    .bind(batch_id)
    .bind(relation_case_id)
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or_else(|| conflict("version_conflict", "no-OA batch version conflict"))?
    .try_get("row_version")?;

    let affected_months = vec![month_from_date_string(&scope_month)];
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "no_oa_batch.submit",
        "no_oa_batch.updated",
        "no_oa_bank_batch",
        batch_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "no_oa_batch.updated",
        "no_oa_batch.submit",
        "no_oa_bank_batch",
        batch_id,
        actor,
        idempotency_key,
        json!({"status": status, "row_version": row_version}),
        json!({"status": "submitted", "row_version": updated_version, "relation_case_id": relation_case_id}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "no_oa_batch.submit",
        bank_transaction_ids,
        affected_months,
        Some(relation_case_id),
        None,
        Some(batch_id),
        Some(updated_version),
        task_id,
        outbox_id,
        "免OA流水批次已提交。".to_owned(),
    ))
}

async fn withdraw_no_oa_batch(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    batch_id: Uuid,
    expected_version: i32,
    reason: Option<&str>,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
    let batch = lock_no_oa_batch(tx, batch_id).await?;
    let status: String = batch.try_get("status")?;
    let row_version: i32 = batch.try_get("row_version")?;
    if row_version != expected_version {
        return Err(conflict("version_conflict", "no-OA batch version conflict"));
    }
    if !matches!(status.as_str(), "submitted" | "confirmed") {
        return Err(conflict(
            "invalid_write_state",
            "only submitted no-OA batches can be withdrawn",
        ));
    }
    let scope_month = batch.try_get::<String, _>("scope_month")?;
    let bank_transaction_ids: Vec<Uuid> = batch.try_get("bank_transaction_ids")?;
    let relation_case_id: Option<Uuid> = batch.try_get("relation_case_id")?;
    if let Some(case_id) = relation_case_id {
        let case_rows = load_case_row_refs(tx, case_id).await?;
        for row in &case_rows {
            mutate_case_row_fact_written_off(tx, row, FactMutation::Revoke).await?;
        }
        sqlx::query(
            r#"
            update app.reconciliation_cases
            set status = 'cancelled', cancelled_at = now(), row_version = row_version + 1
            where id = $1 and status <> 'cancelled'
            "#,
        )
        .bind(case_id)
        .execute(&mut **tx)
        .await?;
        sqlx::query(
            r#"
            update app.reconciliation_case_rows
            set binding_status = 'reverted'
            where case_id = $1 and binding_status = 'active'
            "#,
        )
        .bind(case_id)
        .execute(&mut **tx)
        .await?;
    }
    let updated_version: i32 = sqlx::query(
        r#"
        update app.no_oa_bank_batches
        set
          status = 'cancelled',
          cancelled_at = now(),
          cancelled_by = $2,
          row_version = row_version + 1,
          raw_payload = raw_payload || jsonb_build_object('withdraw_reason', $3::text)
        where id = $1 and row_version = $4
        returning row_version
        "#,
    )
    .bind(batch_id)
    .bind(&actor.actor_id)
    .bind(reason.unwrap_or(""))
    .bind(expected_version)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or_else(|| conflict("version_conflict", "no-OA batch version conflict"))?
    .try_get("row_version")?;

    let affected_months = vec![month_from_date_string(&scope_month)];
    let (task_id, outbox_id) = enqueue_rebuild(
        tx,
        actor,
        "no_oa_batch.withdraw",
        "no_oa_batch.updated",
        "no_oa_bank_batch",
        batch_id,
        idempotency_key,
        &affected_months,
    )
    .await?;
    insert_audit_event(
        tx,
        "no_oa_batch.updated",
        "no_oa_batch.withdraw",
        "no_oa_bank_batch",
        batch_id,
        actor,
        idempotency_key,
        json!({"status": status, "row_version": row_version}),
        json!({"status": "cancelled", "row_version": updated_version}),
        request_payload.clone(),
    )
    .await?;

    Ok(response(
        "no_oa_batch.withdraw",
        bank_transaction_ids,
        affected_months,
        relation_case_id,
        None,
        Some(batch_id),
        Some(updated_version),
        task_id,
        outbox_id,
        "免OA流水批次已撤回。".to_owned(),
    ))
}

async fn load_workbench_rows(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    month: &str,
    row_ids: &[Uuid],
) -> Result<Vec<WorkbenchRowRef>, WorkbenchWriteRepositoryError> {
    let rows = sqlx::query(
        r#"
        select
          row_id,
          row_type,
          source_entity_type,
          source_entity_id,
          to_char(scope_month, 'YYYY-MM') as scope_month
        from read_model.workbench_rows
        where scope_month = to_date($1 || '-01', 'YYYY-MM-DD')
          and row_id = any($2)
        for update
        "#,
    )
    .bind(month)
    .bind(row_ids)
    .fetch_all(&mut **tx)
    .await?;
    if rows.len() != row_ids.len() {
        return Err(WorkbenchWriteRepositoryError::NotFound {
            resource: "workbench_row",
        });
    }
    rows.into_iter()
        .map(|row| {
            Ok(WorkbenchRowRef {
                row_id: row.try_get("row_id")?,
                row_type: row.try_get("row_type")?,
                source_entity_type: row.try_get("source_entity_type")?,
                source_entity_id: row.try_get("source_entity_id")?,
                scope_month: row.try_get("scope_month")?,
            })
        })
        .collect()
}

async fn load_locked_fact_rows(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    rows: &[WorkbenchRowRef],
) -> Result<Vec<LockedFactRow>, WorkbenchWriteRepositoryError> {
    let mut facts = Vec::with_capacity(rows.len());
    for row in rows {
        let fact = match row.source_entity_type.as_str() {
            "bank_transaction" => lock_bank_transaction_fact(tx, row).await?,
            "invoice" => lock_invoice_fact(tx, row).await?,
            "oa_application" => lock_oa_application_fact(tx, row).await?,
            "oa_application_item" => lock_oa_application_item_fact(tx, row).await?,
            _ => {
                return Err(conflict(
                    "invalid_write_state",
                    format!(
                        "unsupported workbench source object type: {}",
                        row.source_entity_type
                    ),
                ));
            }
        };
        facts.push(fact);
    }
    Ok(facts)
}

async fn lock_bank_transaction_fact(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &WorkbenchRowRef,
) -> Result<LockedFactRow, WorkbenchWriteRepositoryError> {
    if row.row_type != "bank" {
        return Err(conflict(
            "invalid_write_state",
            "bank transaction source must map to a bank workbench row",
        ));
    }
    let fact = sqlx::query(
        r#"
        select
          amount::text as amount,
          written_off_amount::text as written_off_amount,
          status,
          txn_direction,
          raw_payload
        from app.bank_transactions
        where txn_month = to_date($1 || '-01', 'YYYY-MM-DD')
          and id = $2
        for update
        "#,
    )
    .bind(&row.scope_month)
    .bind(row.source_entity_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "workbench_row",
    })?;
    locked_fact_from_row(
        row,
        "bank_transaction",
        fact.try_get::<String, _>("amount")?,
        fact.try_get::<String, _>("written_off_amount")?,
        fact.try_get("status")?,
        fact.try_get("txn_direction")?,
        fact.try_get("raw_payload")?,
    )
}

async fn lock_invoice_fact(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &WorkbenchRowRef,
) -> Result<LockedFactRow, WorkbenchWriteRepositoryError> {
    if row.row_type != "invoice" {
        return Err(conflict(
            "invalid_write_state",
            "invoice source must map to an invoice workbench row",
        ));
    }
    let fact = sqlx::query(
        r#"
        select
          amount::text as amount,
          written_off_amount::text as written_off_amount,
          status,
          invoice_type,
          raw_payload
        from app.invoices
        where invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
          and id = $2
        for update
        "#,
    )
    .bind(&row.scope_month)
    .bind(row.source_entity_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "workbench_row",
    })?;
    locked_fact_from_row(
        row,
        "invoice",
        fact.try_get::<String, _>("amount")?,
        fact.try_get::<String, _>("written_off_amount")?,
        fact.try_get("status")?,
        fact.try_get("invoice_type")?,
        fact.try_get("raw_payload")?,
    )
}

async fn lock_oa_application_fact(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &WorkbenchRowRef,
) -> Result<LockedFactRow, WorkbenchWriteRepositoryError> {
    if row.row_type != "oa" {
        return Err(conflict(
            "invalid_write_state",
            "OA source must map to an OA workbench row",
        ));
    }
    let fact = sqlx::query(
        r#"
        select
          coalesce(amount, 0)::text as amount,
          '0.00'::text as written_off_amount,
          status,
          coalesce(nullif(form_type, ''), 'unknown') as direction,
          raw_payload
        from app.oa_applications
        where source_updated_month = to_date($1 || '-01', 'YYYY-MM-DD')
          and id = $2
        for update
        "#,
    )
    .bind(&row.scope_month)
    .bind(row.source_entity_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "workbench_row",
    })?;
    locked_fact_from_row(
        row,
        "oa_application",
        fact.try_get::<String, _>("amount")?,
        fact.try_get::<String, _>("written_off_amount")?,
        fact.try_get("status")?,
        fact.try_get("direction")?,
        fact.try_get("raw_payload")?,
    )
}

async fn lock_oa_application_item_fact(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &WorkbenchRowRef,
) -> Result<LockedFactRow, WorkbenchWriteRepositoryError> {
    if row.row_type != "oa" {
        return Err(conflict(
            "invalid_write_state",
            "OA item source must map to an OA workbench row",
        ));
    }
    let fact = sqlx::query(
        r#"
        select
          coalesce(item.amount, app.amount, 0)::text as amount,
          '0.00'::text as written_off_amount,
          app.status,
          coalesce(nullif(item.item_type, ''), nullif(app.form_type, ''), 'unknown') as direction,
          item.raw_payload
        from app.oa_application_items item
        join app.oa_applications app
          on app.source_updated_month = item.application_month
         and app.id = item.application_id
        where item.application_month = to_date($1 || '-01', 'YYYY-MM-DD')
          and item.id = $2
        for update of item, app
        "#,
    )
    .bind(&row.scope_month)
    .bind(row.source_entity_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "workbench_row",
    })?;
    locked_fact_from_row(
        row,
        "oa_application_item",
        fact.try_get::<String, _>("amount")?,
        fact.try_get::<String, _>("written_off_amount")?,
        fact.try_get("status")?,
        fact.try_get("direction")?,
        fact.try_get("raw_payload")?,
    )
}

fn locked_fact_from_row(
    row: &WorkbenchRowRef,
    object_type: &str,
    amount: String,
    written_off_amount: String,
    status: String,
    direction: String,
    raw_payload: Value,
) -> Result<LockedFactRow, WorkbenchWriteRepositoryError> {
    Ok(LockedFactRow {
        row_type: row.row_type.clone(),
        object_type: object_type.to_owned(),
        object_id: row.source_entity_id,
        object_month: row.scope_month.clone(),
        amount_cents: parse_amount_cents(&amount)?,
        written_off_amount_cents: parse_amount_cents(&written_off_amount)?,
        status: status.clone(),
        direction: direction.clone(),
        source_snapshot: json!({
            "row_id": row.row_id,
            "row_type": row.row_type,
            "source_entity_type": row.source_entity_type,
            "source_entity_id": row.source_entity_id,
            "amount": amount,
            "written_off_amount": written_off_amount,
            "status": status,
            "direction": direction,
            "raw_payload": raw_payload
        }),
    })
}

async fn ensure_rows_unbound(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    rows: &[WorkbenchRowRef],
) -> Result<(), WorkbenchWriteRepositoryError> {
    for row in rows {
        let active = sqlx::query(
            r#"
            select case_id
            from app.reconciliation_case_rows
            where object_type = $1
              and object_id = $2
              and binding_status = 'active'
            limit 1
            for update
            "#,
        )
        .bind(&row.source_entity_type)
        .bind(row.source_entity_id)
        .fetch_optional(&mut **tx)
        .await?;
        if active.is_some() {
            return Err(conflict(
                "reconciliation_row_already_bound",
                "selected row already belongs to an active reconciliation case",
            ));
        }
    }
    Ok(())
}

async fn ensure_fact_rows_unbound(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    rows: &[LockedFactRow],
) -> Result<(), WorkbenchWriteRepositoryError> {
    for row in rows {
        let active = sqlx::query(
            r#"
            select case_id
            from app.reconciliation_case_rows
            where object_type = $1
              and object_id = $2
              and binding_status = 'active'
            limit 1
            for update
            "#,
        )
        .bind(&row.object_type)
        .bind(row.object_id)
        .fetch_optional(&mut **tx)
        .await?;
        if active.is_some() {
            return Err(conflict(
                "reconciliation_row_already_bound",
                "selected row already belongs to an active reconciliation case",
            ));
        }
    }
    Ok(())
}

async fn load_locked_bank_transaction_facts(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    scope_month: &str,
    bank_transaction_ids: &[Uuid],
) -> Result<Vec<LockedFactRow>, WorkbenchWriteRepositoryError> {
    let mut facts = Vec::with_capacity(bank_transaction_ids.len());
    for bank_transaction_id in bank_transaction_ids {
        let row_ref = WorkbenchRowRef {
            row_id: *bank_transaction_id,
            row_type: "bank".to_owned(),
            source_entity_type: "bank_transaction".to_owned(),
            source_entity_id: *bank_transaction_id,
            scope_month: month_from_date_string(scope_month),
        };
        facts.push(lock_bank_transaction_fact(tx, &row_ref).await?);
    }
    if facts.len() != bank_transaction_ids.len() {
        return Err(WorkbenchWriteRepositoryError::NotFound {
            resource: "workbench_row",
        });
    }
    Ok(facts)
}

async fn active_case_id_for_rows(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    rows: &[WorkbenchRowRef],
) -> Result<Uuid, WorkbenchWriteRepositoryError> {
    let mut case_ids = BTreeSet::new();
    for row in rows {
        let active = sqlx::query(
            r#"
            select case_id
            from app.reconciliation_case_rows
            where object_type = $1
              and object_id = $2
              and binding_status = 'active'
            for update
            "#,
        )
        .bind(&row.source_entity_type)
        .bind(row.source_entity_id)
        .fetch_all(&mut **tx)
        .await?;
        for active_row in active {
            case_ids.insert(active_row.try_get::<Uuid, _>("case_id")?);
        }
    }
    if case_ids.len() != 1 {
        return Err(if case_ids.is_empty() {
            WorkbenchWriteRepositoryError::NotFound {
                resource: "reconciliation_case",
            }
        } else {
            conflict(
                "invalid_write_state",
                "selected rows belong to multiple active reconciliation cases",
            )
        });
    }
    Ok(*case_ids.iter().next().unwrap())
}

async fn active_exception_case_for_rows(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    rows: &[WorkbenchRowRef],
) -> Result<Uuid, WorkbenchWriteRepositoryError> {
    let bank_ids = source_ids_for_type(rows, "bank");
    let invoice_ids = source_ids_for_type(rows, "invoice");
    let row = sqlx::query(
        r#"
        select id
        from app.workbench_exception_cases
        where status in ('open', 'in_progress', 'resolved', 'ignored')
          and (
            source_invoice_ids && $1::uuid[]
            or source_bank_txn_ids && $2::uuid[]
          )
        order by updated_at desc
        limit 1
        for update
        "#,
    )
    .bind(invoice_ids)
    .bind(bank_ids)
    .fetch_optional(&mut **tx)
    .await?;
    row.map(|row| row.try_get("id"))
        .transpose()
        .map_err(WorkbenchWriteRepositoryError::from)?
        .ok_or(WorkbenchWriteRepositoryError::NotFound {
            resource: "exception_case",
        })
}

#[derive(Debug)]
struct CaseRowRef {
    row_id: Option<Uuid>,
    object_type: String,
    source_entity_id: Uuid,
    object_month: Option<String>,
    applied_amount_cents: i64,
}

async fn load_case_row_refs(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    case_id: Uuid,
) -> Result<Vec<CaseRowRef>, WorkbenchWriteRepositoryError> {
    let rows = sqlx::query(
        r#"
        select
          case_rows.object_type,
          case_rows.object_id,
          to_char(case_rows.object_month, 'YYYY-MM') as object_month,
          case_rows.applied_amount::text as applied_amount,
          read_rows.row_id
        from app.reconciliation_case_rows case_rows
        left join read_model.workbench_rows read_rows
          on read_rows.source_entity_type = case_rows.object_type
         and read_rows.source_entity_id = case_rows.object_id
         and read_rows.scope_month = case_rows.object_month
        where case_rows.case_id = $1
          and case_rows.binding_status = 'active'
        for update of case_rows
        "#,
    )
    .bind(case_id)
    .fetch_all(&mut **tx)
    .await?;
    if rows.is_empty() {
        return Err(WorkbenchWriteRepositoryError::NotFound {
            resource: "reconciliation_case",
        });
    }
    rows.into_iter()
        .map(|row| {
            Ok(CaseRowRef {
                row_id: row.try_get("row_id")?,
                object_type: row.try_get("object_type")?,
                source_entity_id: row.try_get("object_id")?,
                object_month: row.try_get("object_month")?,
                applied_amount_cents: parse_amount_cents(
                    row.try_get::<String, _>("applied_amount")?.as_str(),
                )?,
            })
        })
        .collect()
}

async fn lock_no_oa_batch(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    batch_id: Uuid,
) -> Result<sqlx::postgres::PgRow, WorkbenchWriteRepositoryError> {
    sqlx::query(
        r#"
        select
          id,
          status,
          row_version,
          to_char(scope_month, 'YYYY-MM-DD') as scope_month,
          bank_transaction_ids,
          relation_case_id
        from app.no_oa_bank_batches
        where id = $1
        for update
        "#,
    )
    .bind(batch_id)
    .fetch_optional(&mut **tx)
    .await?
    .ok_or(WorkbenchWriteRepositoryError::NotFound {
        resource: "no_oa_bank_batch",
    })
}

async fn enqueue_rebuild(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    actor: &WriteActor,
    operation: &str,
    reason: &str,
    aggregate_type: &str,
    aggregate_id: Uuid,
    idempotency_key: &str,
    affected_months: &[String],
) -> Result<(Uuid, Uuid), WorkbenchWriteRepositoryError> {
    let task_id = Uuid::new_v4();
    let event_id = Uuid::new_v4();
    let scope_keys = rebuild_scope_keys(affected_months);
    let fact_updated_at = utc_now_string(tx).await?;
    let trace_id = actor
        .request_id
        .clone()
        .unwrap_or_else(|| format!("{operation}:{idempotency_key}"));
    let source = json!({
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_id": event_id
    });
    let payload = json!({
        "schema_version": "finops.read_model.rebuild_requested.v1",
        "models": ["workbench", "search_index", "cost_statistics"],
        "scope_keys": scope_keys,
        "months": affected_months,
        "scope_type": "month",
        "reason": reason,
        "source": source,
        "source_versions": {
            "fact_updated_at": fact_updated_at,
            "write_operation": operation
        },
        "priority": "normal",
        "force": false,
        "requested_by": &actor.actor_id,
        "requested_by_type": &actor.actor_type,
        "request_id": trace_id.clone(),
        "trace_id": trace_id.clone()
    });
    let task_key = format!("worker:read_model.rebuild:{operation}:{idempotency_key}");
    sqlx::query(
        r#"
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
          '重建工作台读模型',
          $3,
          $4,
          $5,
          array(select to_date(value || '-01', 'YYYY-MM-DD') from unnest($6::text[]) as value),
          $7
        )
        "#,
    )
    .bind(task_id)
    .bind(task_key)
    .bind(source.clone())
    .bind(payload.clone())
    .bind(&scope_keys)
    .bind(affected_months)
    .bind(&actor.actor_id)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    sqlx::query(
        r#"
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
          $2,
          $3,
          'read_model.rebuild_requested',
          'finops.jobs.read_model.rebuild',
          $4,
          'pending',
          $5,
          $6
        )
        "#,
    )
    .bind(event_id)
    .bind(aggregate_type)
    .bind(aggregate_id)
    .bind(payload)
    .bind(format!(
        "outbox:read_model.rebuild:{operation}:{idempotency_key}"
    ))
    .bind(trace_id)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok((task_id, event_id))
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
) -> Result<(), WorkbenchWriteRepositoryError> {
    sqlx::query(
        r#"
        insert into audit.events (
          event_type,
          action,
          entity_type,
          entity_id,
          actor_id,
          actor_type,
          idempotency_key,
          before_state,
          after_state,
          diff,
          metadata
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, '{}'::jsonb, $10)
        "#,
    )
    .bind(event_type)
    .bind(action)
    .bind(entity_type)
    .bind(entity_id)
    .bind(&actor.actor_id)
    .bind(&actor.actor_type)
    .bind(idempotency_key)
    .bind(before_state)
    .bind(after_state)
    .bind(metadata)
    .execute(&mut **tx)
    .await?;
    Ok(())
}

async fn utc_now_string(
    tx: &mut Transaction<'_, sqlx::Postgres>,
) -> Result<String, WorkbenchWriteRepositoryError> {
    let row = sqlx::query(
        r#"select to_char(now() at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as now_utc"#,
    )
    .fetch_one(&mut **tx)
    .await?;
    Ok(row.try_get("now_utc")?)
}

fn response(
    action: &str,
    affected_row_ids: Vec<Uuid>,
    affected_months: Vec<String>,
    case_id: Option<Uuid>,
    exception_case_id: Option<Uuid>,
    batch_id: Option<Uuid>,
    row_version: Option<i32>,
    rebuild_task_id: Uuid,
    outbox_event_id: Uuid,
    message: String,
) -> WorkbenchWriteResponse {
    WorkbenchWriteResponse {
        success: true,
        action: action.to_owned(),
        idempotent_replay: false,
        affected_row_ids: affected_row_ids
            .into_iter()
            .map(|value| value.to_string())
            .collect(),
        affected_months,
        case_id: case_id.map(|value| value.to_string()),
        exception_case_id: exception_case_id.map(|value| value.to_string()),
        batch_id: batch_id.map(|value| value.to_string()),
        row_version,
        rebuild_task_id: rebuild_task_id.to_string(),
        outbox_event_id: outbox_event_id.to_string(),
        message,
    }
}

fn months_from_rows(rows: &[WorkbenchRowRef]) -> Vec<String> {
    let mut months = rows
        .iter()
        .map(|row| row.scope_month.clone())
        .collect::<Vec<_>>();
    months.sort();
    months.dedup();
    months
}

fn months_from_case_refs(rows: &[CaseRowRef], fallback_month: &str) -> Vec<String> {
    let mut months = rows
        .iter()
        .filter_map(|row| row.object_month.clone())
        .collect::<Vec<_>>();
    if months.is_empty() {
        months.push(fallback_month.to_owned());
    }
    months.sort();
    months.dedup();
    months
}

fn rebuild_scope_keys(months: &[String]) -> Vec<String> {
    let mut keys = Vec::new();
    for month in months {
        keys.push(format!("workbench:{month}"));
        keys.push(format!("search:{month}"));
        keys.push(format!("active:{month}"));
        keys.push(format!("all:{month}"));
    }
    keys.sort();
    keys.dedup();
    keys
}

fn side_role(row_type: &str) -> &'static str {
    match row_type {
        "bank" => "bank",
        "invoice" => "invoice",
        "oa" => "oa",
        _ => "offset",
    }
}

fn validate_fact_row_for_confirm(row: &LockedFactRow) -> Result<(), WorkbenchWriteRepositoryError> {
    match row.row_type.as_str() {
        "bank" | "invoice" => {
            if !matches!(row.status.as_str(), "pending" | "partially_reconciled") {
                return Err(conflict(
                    "invalid_write_state",
                    format!(
                        "{} row is not available for reconciliation: {}",
                        row.row_type, row.status
                    ),
                ));
            }
            if row.amount_cents <= row.written_off_amount_cents {
                return Err(conflict(
                    "invalid_write_state",
                    format!("{} row has no remaining amount to reconcile", row.row_type),
                ));
            }
        }
        "oa" => {
            if row.status != "approved" {
                return Err(conflict(
                    "invalid_write_state",
                    format!("OA row is not approved: {}", row.status),
                ));
            }
            if row.amount_cents <= 0 {
                return Err(conflict(
                    "invalid_write_state",
                    "OA row amount must be greater than zero",
                ));
            }
        }
        _ => {
            return Err(conflict(
                "invalid_write_state",
                format!("unsupported workbench row type: {}", row.row_type),
            ));
        }
    }
    Ok(())
}

async fn mutate_fact_written_off(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &AppliedFactRow,
    mutation: FactMutation,
) -> Result<(), WorkbenchWriteRepositoryError> {
    match row.object_type.as_str() {
        "bank_transaction" => {
            let current = sqlx::query(
                r#"
                select amount::text as amount, written_off_amount::text as written_off_amount
                from app.bank_transactions
                where txn_month = to_date($1 || '-01', 'YYYY-MM-DD')
                  and id = $2
                for update
                "#,
            )
            .bind(&row.object_month)
            .bind(row.object_id)
            .fetch_one(&mut **tx)
            .await?;
            let next_written_off = next_written_off_cents(
                &current.try_get::<String, _>("amount")?,
                &current.try_get::<String, _>("written_off_amount")?,
                row.applied_amount_cents,
                mutation,
            )?;
            let next_status =
                status_for_written_off(&current.try_get::<String, _>("amount")?, next_written_off)?;
            sqlx::query(
                r#"
                update app.bank_transactions
                set written_off_amount = $3::numeric,
                    status = $4,
                    updated_at = now()
                where txn_month = to_date($1 || '-01', 'YYYY-MM-DD')
                  and id = $2
                "#,
            )
            .bind(&row.object_month)
            .bind(row.object_id)
            .bind(amount_string(next_written_off))
            .bind(next_status)
            .execute(&mut **tx)
            .await?;
        }
        "invoice" => {
            let current = sqlx::query(
                r#"
                select amount::text as amount, written_off_amount::text as written_off_amount
                from app.invoices
                where invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
                  and id = $2
                for update
                "#,
            )
            .bind(&row.object_month)
            .bind(row.object_id)
            .fetch_one(&mut **tx)
            .await?;
            let amount = current.try_get::<String, _>("amount")?;
            let next_written_off = next_written_off_cents(
                &amount,
                &current.try_get::<String, _>("written_off_amount")?,
                row.applied_amount_cents,
                mutation,
            )?;
            let next_status = status_for_written_off(&amount, next_written_off)?;
            sqlx::query(
                r#"
                update app.invoices
                set written_off_amount = $3::numeric,
                    status = $4,
                    updated_at = now()
                where invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
                  and id = $2
                "#,
            )
            .bind(&row.object_month)
            .bind(row.object_id)
            .bind(amount_string(next_written_off))
            .bind(next_status)
            .execute(&mut **tx)
            .await?;
        }
        "oa_application" | "oa_application_item" => {}
        _ => {
            return Err(conflict(
                "invalid_write_state",
                format!(
                    "unsupported reconciliation object type: {}",
                    row.object_type
                ),
            ));
        }
    }
    Ok(())
}

async fn mutate_case_row_fact_written_off(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    row: &CaseRowRef,
    mutation: FactMutation,
) -> Result<(), WorkbenchWriteRepositoryError> {
    let object_month = row
        .object_month
        .as_deref()
        .ok_or_else(|| conflict("invalid_write_state", "case row is missing object month"))?;
    mutate_fact_written_off(
        tx,
        &AppliedFactRow {
            row_type: side_role_to_row_type(&row.object_type).to_owned(),
            object_type: row.object_type.clone(),
            object_id: row.source_entity_id,
            object_month: object_month.to_owned(),
            applied_amount_cents: row.applied_amount_cents,
            source_snapshot: json!({}),
        },
        mutation,
    )
    .await
}

fn side_role_to_row_type(object_type: &str) -> &'static str {
    match object_type {
        "bank_transaction" => "bank",
        "invoice" => "invoice",
        "oa_application" | "oa_application_item" => "oa",
        _ => "offset",
    }
}

fn next_written_off_cents(
    amount: &str,
    written_off_amount: &str,
    applied_amount_cents: i64,
    mutation: FactMutation,
) -> Result<i64, WorkbenchWriteRepositoryError> {
    let amount_cents = parse_amount_cents(amount)?;
    let current_cents = parse_amount_cents(written_off_amount)?;
    let next = match mutation {
        FactMutation::Confirm => current_cents + applied_amount_cents,
        FactMutation::Revoke => current_cents - applied_amount_cents,
    };
    if next < 0 || next > amount_cents {
        return Err(conflict(
            "invalid_write_state",
            "written-off amount would exceed fact boundaries",
        ));
    }
    Ok(next)
}

fn status_for_written_off(
    amount: &str,
    written_off_cents: i64,
) -> Result<&'static str, WorkbenchWriteRepositoryError> {
    let amount_cents = parse_amount_cents(amount)?;
    if written_off_cents <= 0 {
        Ok("pending")
    } else if written_off_cents >= amount_cents {
        Ok("reconciled")
    } else {
        Ok("partially_reconciled")
    }
}

fn parse_amount_cents(value: &str) -> Result<i64, WorkbenchWriteRepositoryError> {
    let normalized = value.trim().replace(',', "");
    let (whole, fractional) = normalized
        .split_once('.')
        .map(|(whole, fractional)| (whole, fractional))
        .unwrap_or((normalized.as_str(), "0"));
    let whole_cents = whole.parse::<i64>().map_err(|_| {
        conflict(
            "invalid_write_state",
            format!("invalid amount value in fact row: {value}"),
        )
    })? * 100;
    let mut fraction = fractional
        .chars()
        .filter(|ch| ch.is_ascii_digit())
        .take(2)
        .collect::<String>();
    while fraction.len() < 2 {
        fraction.push('0');
    }
    let fractional_cents = fraction.parse::<i64>().map_err(|_| {
        conflict(
            "invalid_write_state",
            format!("invalid amount value in fact row: {value}"),
        )
    })?;
    Ok(whole_cents + fractional_cents)
}

fn amount_string(cents: i64) -> String {
    format!("{}.{:02}", cents / 100, cents.abs() % 100)
}

fn source_ids_for_type(rows: &[WorkbenchRowRef], row_type: &str) -> Vec<Uuid> {
    rows.iter()
        .filter(|row| row.row_type == row_type)
        .map(|row| row.source_entity_id)
        .collect()
}

fn resolution_action(action_code: &str) -> &'static str {
    match action_code {
        "manual_reconcile" => "manual_reconcile",
        "mark_no_oa" | "confirm_oa_exempt_auto" | "confirm_oa_exempt_manual" => "mark_no_oa",
        "create_turnover" => "create_turnover",
        "ignore" => "ignore",
        _ => "none",
    }
}

fn month_from_date_string(value: &str) -> String {
    value.get(..7).unwrap_or(value).to_owned()
}

fn conflict(code: &'static str, message: impl Into<String>) -> WorkbenchWriteRepositoryError {
    WorkbenchWriteRepositoryError::Conflict {
        code,
        message: message.into(),
    }
}

fn map_sqlx_error(error: sqlx::Error) -> WorkbenchWriteRepositoryError {
    if let sqlx::Error::Database(database_error) = &error {
        if database_error.code().as_deref() == Some("23505") {
            let constraint = database_error.constraint().unwrap_or_default();
            if constraint == "reconciliation_case_rows_active_object_uidx" {
                return conflict(
                    "reconciliation_row_already_bound",
                    "selected row already belongs to an active reconciliation case",
                );
            }
            return conflict(
                "idempotency_key_reused_with_different_payload",
                "unique write key conflict",
            );
        }
    }
    WorkbenchWriteRepositoryError::Database(error)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn workbench_writes_confirm_summary_uses_fact_open_amounts() {
        let facts = vec![
            fact("bank", "bank_transaction", "100.00", "0.00", "pending"),
            fact(
                "invoice",
                "invoice",
                "80.00",
                "10.00",
                "partially_reconciled",
            ),
            fact("oa", "oa_application", "70.00", "0.00", "approved"),
        ];

        let summary = ReconciliationFacts::from_locked_rows(&facts).unwrap();

        assert_eq!(summary.total_amount_cents, 10000);
        assert_eq!(summary.difference_amount_cents, 3000);
        assert_eq!(
            summary
                .rows
                .iter()
                .map(|row| (row.row_type.as_str(), row.applied_amount_cents))
                .collect::<Vec<_>>(),
            vec![("bank", 10000), ("invoice", 7000), ("oa", 7000)]
        );
        assert_eq!(summary.biz_side, "receivable");
    }

    #[test]
    fn workbench_writes_revoke_restores_written_off_amounts() {
        assert_eq!(
            next_written_off_cents("120.00", "80.00", 3000, FactMutation::Confirm).unwrap(),
            11000
        );
        assert_eq!(
            next_written_off_cents("120.00", "80.00", 3000, FactMutation::Revoke).unwrap(),
            5000
        );
        assert_eq!(status_for_written_off("120.00", 0).unwrap(), "pending");
        assert_eq!(
            status_for_written_off("120.00", 5000).unwrap(),
            "partially_reconciled"
        );
        assert_eq!(
            status_for_written_off("120.00", 12000).unwrap(),
            "reconciled"
        );
    }

    #[test]
    fn workbench_writes_rejects_invalid_fact_status_for_confirm() {
        let facts = vec![fact(
            "bank",
            "bank_transaction",
            "100.00",
            "100.00",
            "reconciled",
        )];

        let error = ReconciliationFacts::from_locked_rows(&facts).unwrap_err();

        assert!(matches!(
            error,
            WorkbenchWriteRepositoryError::Conflict {
                code: "invalid_write_state",
                ..
            }
        ));
    }

    fn fact(
        row_type: &str,
        object_type: &str,
        amount: &str,
        written_off_amount: &str,
        status: &str,
    ) -> LockedFactRow {
        LockedFactRow {
            row_type: row_type.to_owned(),
            object_type: object_type.to_owned(),
            object_id: Uuid::new_v4(),
            object_month: "2026-05".to_owned(),
            amount_cents: parse_amount_cents(amount).unwrap(),
            written_off_amount_cents: parse_amount_cents(written_off_amount).unwrap(),
            status: status.to_owned(),
            direction: "inflow".to_owned(),
            source_snapshot: json!({}),
        }
    }
}
