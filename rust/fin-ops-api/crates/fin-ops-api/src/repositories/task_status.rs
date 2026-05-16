use async_trait::async_trait;
use sqlx::{PgPool, Row};

#[derive(Clone, Debug)]
pub struct TaskStatusRow {
    pub task_id: String,
    pub task_type: String,
    pub label: String,
    pub owner_user_id: Option<String>,
    pub visibility: String,
    pub status: String,
    pub phase: String,
    pub source: serde_json::Value,
    pub result_summary: serde_json::Value,
    pub affected_scopes: Vec<String>,
    pub affected_months: Vec<String>,
    pub current_count: i32,
    pub total_count: i32,
    pub percent: i32,
    pub error_code: Option<String>,
    pub error_summary: Option<String>,
    pub idempotency_key: Option<String>,
    pub retryable: bool,
    pub attempt_count: i32,
    pub max_attempts: i32,
    pub next_attempt_at: Option<String>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub updated_at: String,
    pub finished_at: Option<String>,
    pub cancelled_at: Option<String>,
}

#[derive(Clone, Debug)]
pub struct TaskAttemptStatusRow {
    pub attempt_id: String,
    pub attempt_no: i32,
    pub worker_id: String,
    pub nats_stream: Option<String>,
    pub nats_consumer: Option<String>,
    pub nats_sequence: Option<i64>,
    pub started_at: String,
    pub heartbeat_at: Option<String>,
    pub finished_at: Option<String>,
    pub duration_ms: Option<i32>,
    pub status: String,
    pub error_code: Option<String>,
    pub error_summary: Option<String>,
}

#[derive(Debug, thiserror::Error)]
pub enum TaskStatusRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait TaskStatusRepository: Send + Sync {
    async fn find_task(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError>;

    async fn list_attempts(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<Vec<TaskAttemptStatusRow>, TaskStatusRepositoryError>;

    async fn find_active_data_reset_task(
        &self,
    ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError>;

    async fn list_active_background_tasks(
        &self,
    ) -> Result<Vec<TaskStatusRow>, TaskStatusRepositoryError>;
}

#[derive(Clone)]
pub struct SqlxTaskStatusRepository {
    pool: PgPool,
}

impl SqlxTaskStatusRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl TaskStatusRepository for SqlxTaskStatusRepository {
    async fn find_task(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError> {
        let row = sqlx::query(
            r#"
            select
              t.id::text as task_id,
              t.task_type,
              t.label,
              t.owner_user_id::text as owner_user_id,
              t.visibility,
              t.status,
              t.phase,
              t.source,
              t.result_summary,
              t.affected_scopes,
              coalesce(
                (
                  select array_agg(to_char(month_value, 'YYYY-MM-DD') order by month_value)
                  from unnest(t.affected_months) as months(month_value)
                ),
                array[]::text[]
              ) as affected_months,
              t.current_count,
              t.total_count,
              t.percent,
              t.error_code,
              t.error_summary,
              t.idempotency_key,
              t.retryable,
              t.attempt_count,
              t.max_attempts,
              to_char(t.next_attempt_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as next_attempt_at,
              to_char(t.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
              to_char(t.started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started_at,
              to_char(t.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at,
              to_char(t.finished_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as finished_at,
              to_char(t.cancelled_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as cancelled_at
            from job.worker_tasks t
            where t.id = $1
            "#,
        )
        .bind(task_id)
        .fetch_optional(&self.pool)
        .await?;

        row.map(row_to_task_status).transpose()
    }

    async fn list_attempts(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<Vec<TaskAttemptStatusRow>, TaskStatusRepositoryError> {
        let rows = sqlx::query(
            r#"
            select
              id::text as attempt_id,
              attempt_no,
              worker_id,
              nats_stream,
              nats_consumer,
              nats_sequence,
              to_char(started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started_at,
              to_char(heartbeat_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as heartbeat_at,
              to_char(finished_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as finished_at,
              duration_ms,
              status,
              error_code,
              error_summary
            from job.worker_attempts
            where task_id = $1
            order by attempt_no asc
            "#,
        )
        .bind(task_id)
        .fetch_all(&self.pool)
        .await?;

        rows.into_iter().map(row_to_task_attempt).collect()
    }

    async fn find_active_data_reset_task(
        &self,
    ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError> {
        let query = format!(
            "{}{}",
            TASK_STATUS_SELECT_SQL,
            r#"
            where t.task_type = 'settings_data_reset'
              and t.status in ('queued', 'running')
              and t.visibility = 'system'
            order by t.updated_at desc, t.id desc
            limit 1
            "#
        );
        let row = sqlx::query(&query).fetch_optional(&self.pool).await?;

        row.map(row_to_task_status).transpose()
    }

    async fn list_active_background_tasks(
        &self,
    ) -> Result<Vec<TaskStatusRow>, TaskStatusRepositoryError> {
        let query = format!(
            "{}{}",
            TASK_STATUS_SELECT_SQL,
            r#"
            where t.visibility = 'system'
              and (
                t.status in ('queued', 'running', 'retrying', 'failed', 'dead_lettered')
                or (
                  t.status = 'succeeded'
                  and (
                    lower(coalesce(t.result_summary->>'partial_success', 'false')) in ('true', '1', 'yes')
                    or coalesce(t.finished_at, t.updated_at) >= now() - interval '8 seconds'
                  )
                )
              )
            order by
              case
                when t.status in ('queued', 'running', 'retrying') then 0
                when t.status = 'succeeded'
                  and lower(coalesce(t.result_summary->>'partial_success', 'false')) not in ('true', '1', 'yes')
                  then 0
                else 1
              end,
              t.updated_at desc,
              t.id desc
            "#
        );
        let rows = sqlx::query(&query).fetch_all(&self.pool).await?;

        rows.into_iter().map(row_to_task_status).collect()
    }
}

const TASK_STATUS_SELECT_SQL: &str = r#"
            select
              t.id::text as task_id,
              t.task_type,
              t.label,
              t.owner_user_id::text as owner_user_id,
              t.visibility,
              t.status,
              t.phase,
              t.source,
              t.result_summary,
              t.affected_scopes,
              coalesce(
                (
                  select array_agg(to_char(month_value, 'YYYY-MM-DD') order by month_value)
                  from unnest(t.affected_months) as months(month_value)
                ),
                array[]::text[]
              ) as affected_months,
              t.current_count,
              t.total_count,
              t.percent,
              t.error_code,
              t.error_summary,
              t.idempotency_key,
              t.retryable,
              t.attempt_count,
              t.max_attempts,
              to_char(t.next_attempt_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as next_attempt_at,
              to_char(t.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
              to_char(t.started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as started_at,
              to_char(t.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at,
              to_char(t.finished_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as finished_at,
              to_char(t.cancelled_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as cancelled_at
            from job.worker_tasks t
"#;

fn row_to_task_status(
    row: sqlx::postgres::PgRow,
) -> Result<TaskStatusRow, TaskStatusRepositoryError> {
    Ok(TaskStatusRow {
        task_id: row.try_get("task_id")?,
        task_type: row.try_get("task_type")?,
        label: row.try_get("label")?,
        owner_user_id: row.try_get("owner_user_id")?,
        visibility: row.try_get("visibility")?,
        status: row.try_get("status")?,
        phase: row.try_get("phase")?,
        source: row.try_get("source")?,
        result_summary: row.try_get("result_summary")?,
        affected_scopes: row.try_get("affected_scopes")?,
        affected_months: row.try_get("affected_months")?,
        current_count: row.try_get("current_count")?,
        total_count: row.try_get("total_count")?,
        percent: row.try_get("percent")?,
        error_code: row.try_get("error_code")?,
        error_summary: row.try_get("error_summary")?,
        idempotency_key: row.try_get("idempotency_key")?,
        retryable: row.try_get("retryable")?,
        attempt_count: row.try_get("attempt_count")?,
        max_attempts: row.try_get("max_attempts")?,
        next_attempt_at: row.try_get("next_attempt_at")?,
        created_at: row.try_get("created_at")?,
        started_at: row.try_get("started_at")?,
        updated_at: row.try_get("updated_at")?,
        finished_at: row.try_get("finished_at")?,
        cancelled_at: row.try_get("cancelled_at")?,
    })
}

fn row_to_task_attempt(
    row: sqlx::postgres::PgRow,
) -> Result<TaskAttemptStatusRow, TaskStatusRepositoryError> {
    Ok(TaskAttemptStatusRow {
        attempt_id: row.try_get("attempt_id")?,
        attempt_no: row.try_get("attempt_no")?,
        worker_id: row.try_get("worker_id")?,
        nats_stream: row.try_get("nats_stream")?,
        nats_consumer: row.try_get("nats_consumer")?,
        nats_sequence: row.try_get("nats_sequence")?,
        started_at: row.try_get("started_at")?,
        heartbeat_at: row.try_get("heartbeat_at")?,
        finished_at: row.try_get("finished_at")?,
        duration_ms: row.try_get("duration_ms")?,
        status: row.try_get("status")?,
        error_code: row.try_get("error_code")?,
        error_summary: row.try_get("error_summary")?,
    })
}
