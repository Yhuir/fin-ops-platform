use async_trait::async_trait;
use serde_json::{json, Value};
use sqlx::{PgPool, Row, Transaction};
use uuid::Uuid;

use crate::services::platform_legacy::{
    ImportSessionBatch, ImportSessionFile, ImportSessionProjection, MatchingResultRow,
    MatchingResultsRequest, PlatformJobCommand, PlatformJobCommandResult,
    PlatformLegacyRepository, PlatformLegacyRepositoryError,
};

#[derive(Clone)]
pub struct SqlxPlatformLegacyRepository {
    pool: PgPool,
}

impl SqlxPlatformLegacyRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl PlatformLegacyRepository for SqlxPlatformLegacyRepository {
    async fn create_job_command(
        &self,
        command: PlatformJobCommand,
    ) -> Result<PlatformJobCommandResult, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_response(
            &mut tx,
            &command.operation,
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }
        ensure_retry_target_exists(&mut tx, &command).await?;

        let task_id = Uuid::new_v4();
        let outbox_event_id = Uuid::new_v4();
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());

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
              $2,
              'queued',
              'queued',
              0,
              $3,
              'system',
              $4,
              $5,
              $6,
              $7,
              array(select to_date(value, 'YYYY-MM-DD') from unnest($8::text[]) as value),
              $9
            )
            "#,
        )
        .bind(task_id)
        .bind(&command.task_type)
        .bind(&command.idempotency_key)
        .bind(&command.label)
        .bind(&command.source)
        .bind(&command.payload)
        .bind(&command.affected_scopes)
        .bind(&command.affected_months)
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
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
            values ($1, $2, $3, $4, $5, $6, 'pending', $7, $8)
            "#,
        )
        .bind(outbox_event_id)
        .bind(&command.aggregate_type)
        .bind(command.aggregate_id)
        .bind(format!("{}.requested", command.operation))
        .bind(&command.subject)
        .bind(&command.payload)
        .bind(format!(
            "outbox:{}:{}",
            command.operation, command.idempotency_key
        ))
        .bind(&trace_id)
        .execute(&mut *tx)
        .await
        .map_err(map_sqlx_error)?;

        insert_audit_event(&mut tx, &command, task_id, outbox_event_id, &trace_id).await?;

        let result = PlatformJobCommandResult {
            task_id,
            outbox_event_id,
            status: "queued".to_owned(),
            idempotency_key: command.idempotency_key.clone(),
        };
        record_idempotency(&mut tx, &command, &result).await?;
        tx.commit().await?;
        Ok(result)
    }

    async fn find_import_session(
        &self,
        session_id: &str,
    ) -> Result<Option<ImportSessionProjection>, PlatformLegacyRepositoryError> {
        let batches = sqlx::query(
            r#"
            select
              id::text as id,
              batch_type,
              status,
              row_count,
              success_count,
              error_count,
              to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
              to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
            from app.import_batches
            where legacy_collection = 'import_sessions'
              and legacy_id = $1
            order by created_at asc, id asc
            "#,
        )
        .bind(session_id)
        .fetch_all(&self.pool)
        .await?;

        if batches.is_empty() {
            return Ok(None);
        }
        let batch_ids = batches
            .iter()
            .map(|row| row.try_get::<String, _>("id"))
            .collect::<Result<Vec<_>, _>>()?;
        let files = sqlx::query(
            r#"
            select
              f.id::text as id,
              f.batch_id::text as batch_id,
              f.file_object_id::text as file_object_id,
              f.parse_status,
              f.row_count,
              f.error_count,
              f.template_key,
              to_char(f.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
              to_char(f.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
            from app.import_files f
            where f.batch_id = any($1::uuid[])
            order by f.created_at asc, f.id asc
            "#,
        )
        .bind(
            batch_ids
                .iter()
                .map(|id| Uuid::parse_str(id))
                .collect::<Result<Vec<_>, _>>()
                .unwrap_or_default(),
        )
        .fetch_all(&self.pool)
        .await?;

        let batches = batches
            .into_iter()
            .map(|row| {
                Ok(ImportSessionBatch {
                    id: row.try_get("id")?,
                    batch_type: row.try_get("batch_type")?,
                    status: row.try_get("status")?,
                    row_count: row.try_get("row_count")?,
                    success_count: row.try_get("success_count")?,
                    error_count: row.try_get("error_count")?,
                    created_at: row.try_get("created_at")?,
                    updated_at: row.try_get("updated_at")?,
                })
            })
            .collect::<Result<Vec<_>, sqlx::Error>>()?;

        let files = files
            .into_iter()
            .map(|row| {
                Ok(ImportSessionFile {
                    id: row.try_get("id")?,
                    batch_id: row.try_get("batch_id")?,
                    file_object_id: row.try_get("file_object_id")?,
                    parse_status: row.try_get("parse_status")?,
                    row_count: row.try_get("row_count")?,
                    error_count: row.try_get("error_count")?,
                    template_key: row.try_get("template_key")?,
                    created_at: row.try_get("created_at")?,
                    updated_at: row.try_get("updated_at")?,
                })
            })
            .collect::<Result<Vec<_>, sqlx::Error>>()?;

        Ok(Some(ImportSessionProjection {
            session_id: session_id.to_owned(),
            batches,
            files,
        }))
    }

    async fn list_matching_results(
        &self,
        request: MatchingResultsRequest,
    ) -> Result<Vec<MatchingResultRow>, PlatformLegacyRepositoryError> {
        let limit = request.limit.unwrap_or(50).clamp(1, 200);
        let rows = sqlx::query(MATCHING_RESULTS_SQL)
            .bind(request.scope_month)
            .bind(request.status)
            .bind(limit)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter().map(matching_result_from_row).collect()
    }

    async fn find_matching_result(
        &self,
        result_id: Uuid,
    ) -> Result<Option<MatchingResultRow>, PlatformLegacyRepositoryError> {
        let row = sqlx::query(
            r#"
            select
              id::text as result_id,
              to_char(scope_month, 'YYYY-MM-DD') as scope_month,
              candidate_key,
              status,
              score::text as score,
              jsonb_build_object(
                'oa_application_id', oa_application_id,
                'bank_transaction_id', bank_transaction_id,
                'invoice_id', invoice_id,
                'reasons', reasons
              ) as payload,
              source_versions,
              to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
            from read_model.workbench_candidate_matches
            where id = $1
            "#,
        )
        .bind(result_id)
        .fetch_optional(&self.pool)
        .await?;
        row.map(matching_result_from_row).transpose()
    }
}

const MATCHING_RESULTS_SQL: &str = r#"
select
  id::text as result_id,
  to_char(scope_month, 'YYYY-MM-DD') as scope_month,
  candidate_key,
  status,
  score::text as score,
  jsonb_build_object(
    'oa_application_id', oa_application_id,
    'bank_transaction_id', bank_transaction_id,
    'invoice_id', invoice_id,
    'reasons', reasons
  ) as payload,
  source_versions,
  to_char(updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at
from read_model.workbench_candidate_matches
where ($1::text is null or scope_month = to_date($1 || '-01', 'YYYY-MM-DD'))
  and ($2::text is null or status = $2)
order by scope_month desc, score desc, updated_at desc, id desc
limit $3
"#;

const BACKGROUND_JOB_RETRY_TARGET_SQL: &str = r#"
select 1
from job.worker_tasks
where id = $1
  and status in ('failed', 'dead_lettered')
  and retryable is true
"#;

const IMPORT_FILE_RETRY_TARGET_SQL: &str = r#"
select 1
from app.import_files
where id = $1
  and parse_status = 'failed'
"#;

async fn ensure_retry_target_exists(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
) -> Result<(), PlatformLegacyRepositoryError> {
    let (sql, resource) = match command.operation.as_str() {
        "background_job.retry" => (BACKGROUND_JOB_RETRY_TARGET_SQL, "retryable_background_job"),
        "import_file.retry" => (IMPORT_FILE_RETRY_TARGET_SQL, "retryable_import_file"),
        _ => return Ok(()),
    };
    let exists = sqlx::query(sql)
        .bind(command.aggregate_id)
        .fetch_optional(&mut **tx)
        .await?;
    if exists.is_none() {
        return Err(PlatformLegacyRepositoryError::NotFound { resource });
    }
    Ok(())
}

async fn find_idempotent_response(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    operation: &str,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<Option<PlatformJobCommandResult>, PlatformLegacyRepositoryError> {
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
        return Err(PlatformLegacyRepositoryError::IdempotencyConflict);
    }
    let response: Value = row.try_get("response_payload")?;
    Ok(Some(PlatformJobCommandResult {
        task_id: value_uuid(&response, "task_id")?,
        outbox_event_id: value_uuid(&response, "outbox_event_id")?,
        status: response
            .get("status")
            .and_then(Value::as_str)
            .unwrap_or("queued")
            .to_owned(),
        idempotency_key: response
            .get("idempotency_key")
            .and_then(Value::as_str)
            .unwrap_or(idempotency_key)
            .to_owned(),
    }))
}

async fn record_idempotency(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
    result: &PlatformJobCommandResult,
) -> Result<(), PlatformLegacyRepositoryError> {
    let response_payload = json!({
        "accepted": true,
        "task_id": result.task_id,
        "outbox_event_id": result.outbox_event_id,
        "status": result.status,
        "idempotency_key": result.idempotency_key
    });
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
    .bind(&command.operation)
    .bind(&command.idempotency_key)
    .bind(&command.request_payload)
    .bind(response_payload)
    .bind(&command.aggregate_type)
    .bind(command.aggregate_id)
    .bind(&command.actor.actor_id)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok(())
}

async fn insert_audit_event(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
    task_id: Uuid,
    outbox_event_id: Uuid,
    trace_id: &str,
) -> Result<(), PlatformLegacyRepositoryError> {
    sqlx::query(
        r#"
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
          after_state,
          metadata
        )
        values ($1, 'request', $2, $3, $4, 'user', $5, $5, $6, $7, $8)
        "#,
    )
    .bind(format!("{}.requested", command.operation))
    .bind(&command.aggregate_type)
    .bind(command.aggregate_id)
    .bind(&command.actor.actor_id)
    .bind(trace_id)
    .bind(&command.idempotency_key)
    .bind(json!({
        "task_id": task_id,
        "outbox_event_id": outbox_event_id,
        "status": "queued"
    }))
    .bind(json!({
        "operation": command.operation,
        "subject": command.subject
    }))
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok(())
}

fn matching_result_from_row(
    row: sqlx::postgres::PgRow,
) -> Result<MatchingResultRow, PlatformLegacyRepositoryError> {
    Ok(MatchingResultRow {
        result_id: row.try_get("result_id")?,
        scope_month: row.try_get("scope_month")?,
        candidate_key: row.try_get("candidate_key")?,
        status: row.try_get("status")?,
        score: row.try_get("score")?,
        payload: row.try_get("payload")?,
        source_versions: row.try_get("source_versions")?,
        updated_at: row.try_get("updated_at")?,
    })
}

fn value_uuid(value: &Value, key: &'static str) -> Result<Uuid, PlatformLegacyRepositoryError> {
    value
        .get(key)
        .and_then(Value::as_str)
        .and_then(|value| Uuid::parse_str(value).ok())
        .ok_or(PlatformLegacyRepositoryError::NotFound { resource: key })
}

fn map_sqlx_error(error: sqlx::Error) -> PlatformLegacyRepositoryError {
    if let sqlx::Error::Database(database_error) = &error {
        if database_error.is_unique_violation() {
            return PlatformLegacyRepositoryError::IdempotencyConflict;
        }
    }
    PlatformLegacyRepositoryError::Database(error)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matching_results_query_reads_candidate_match_read_model_only() {
        assert!(MATCHING_RESULTS_SQL.contains("read_model.workbench_candidate_matches"));
        assert!(!MATCHING_RESULTS_SQL.contains("app.mongo"));
        assert!(!MATCHING_RESULTS_SQL.contains("oa_source"));
        assert!(MATCHING_RESULTS_SQL.contains("scope_month"));
        assert!(MATCHING_RESULTS_SQL.contains("score desc"));
    }

    #[test]
    fn retry_target_queries_require_failed_postgresql_facts() {
        assert!(BACKGROUND_JOB_RETRY_TARGET_SQL.contains("from job.worker_tasks"));
        assert!(BACKGROUND_JOB_RETRY_TARGET_SQL.contains("'failed'"));
        assert!(BACKGROUND_JOB_RETRY_TARGET_SQL.contains("'dead_lettered'"));
        assert!(BACKGROUND_JOB_RETRY_TARGET_SQL.contains("retryable is true"));
        assert!(IMPORT_FILE_RETRY_TARGET_SQL.contains("from app.import_files"));
        assert!(IMPORT_FILE_RETRY_TARGET_SQL.contains("parse_status = 'failed'"));
    }
}
