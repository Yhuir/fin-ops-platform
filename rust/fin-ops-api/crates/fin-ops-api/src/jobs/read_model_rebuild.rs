use serde_json::{json, Value};
use sqlx::{PgPool, Row, Transaction};
use std::time::Duration;
use thiserror::Error;
use tokio::time::sleep;
use uuid::Uuid;

const REBUILD_SCHEMA_VERSION: &str = "finops.read_model.rebuild_requested.v1";
const WORKBENCH_SCHEMA_VERSION: &str = "2026-05-workbench-postgres-v1";
const COST_SCHEMA_VERSION: &str = "2026-05-cost-statistics-explorer-v1";
const TAX_SCHEMA_VERSION: &str = "2026-05-tax-offset-month-v1";
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum ReadModelKind {
    Workbench,
    SearchIndex,
    CostStatistics,
    TaxOffset,
}

impl ReadModelKind {
    fn from_str(value: &str) -> Result<Self, ReadModelRebuildError> {
        match value {
            "workbench" => Ok(Self::Workbench),
            "search_index" => Ok(Self::SearchIndex),
            "cost_statistics" => Ok(Self::CostStatistics),
            "tax_offset" => Ok(Self::TaxOffset),
            _ => Err(ReadModelRebuildError::InvalidPayload {
                code: "READ_MODEL_UNKNOWN_MODEL",
                message: format!("unsupported read model: {value}"),
            }),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RebuildTarget {
    pub model: ReadModelKind,
    pub scope_key: String,
    pub month: Option<String>,
}

impl RebuildTarget {
    pub fn new(model: ReadModelKind, scope_key: &str, month: Option<&str>) -> Self {
        Self {
            model,
            scope_key: scope_key.to_owned(),
            month: month.map(ToOwned::to_owned),
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct RebuildRequest {
    pub reason: String,
    pub source_versions: Value,
    pub targets: Vec<RebuildTarget>,
    pub force: bool,
}

impl RebuildRequest {
    pub fn from_payload(payload: Value) -> Result<Self, ReadModelRebuildError> {
        let object = payload.as_object().ok_or_else(|| {
            invalid_payload("READ_MODEL_PAYLOAD_INVALID", "payload must be an object")
        })?;
        let schema_version = object
            .get("schema_version")
            .and_then(Value::as_str)
            .unwrap_or_default();
        if schema_version != REBUILD_SCHEMA_VERSION {
            return Err(invalid_payload(
                "READ_MODEL_SCHEMA_UNSUPPORTED",
                "unsupported read model rebuild payload schema_version",
            ));
        }

        let models = string_array(object.get("models"));
        if models.is_empty() {
            return Err(invalid_payload(
                "READ_MODEL_MODELS_MISSING",
                "payload.models must contain at least one model",
            ));
        }
        let months = string_array(object.get("months"));
        for month in &months {
            validate_month(month)?;
        }
        let scope_keys = string_array(object.get("scope_keys"));
        let reason = object
            .get("reason")
            .and_then(Value::as_str)
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .ok_or_else(|| {
                invalid_payload("READ_MODEL_REASON_MISSING", "payload.reason is required")
            })?
            .to_owned();
        let source_versions = source_version_metadata(object)?;
        if !has_fact_watermark(&source_versions) {
            return Err(invalid_payload(
                "READ_MODEL_SOURCE_VERSION_MISSING",
                "payload.source_versions.fact_updated_at or payload.source_watermark.fact_updated_at is required",
            ));
        }

        let mut targets = Vec::new();
        for model in models {
            let kind = ReadModelKind::from_str(&model)?;
            push_targets_for_model(&mut targets, kind, &scope_keys, &months)?;
        }
        if targets.is_empty() {
            return Err(invalid_payload(
                "READ_MODEL_SCOPE_MISSING",
                "payload must resolve to at least one model scope",
            ));
        }

        Ok(Self {
            reason,
            source_versions,
            targets,
            force: object
                .get("force")
                .and_then(Value::as_bool)
                .unwrap_or(false),
        })
    }
}

#[derive(Debug, Error)]
pub enum ReadModelRebuildError {
    #[error("{code}: {message}")]
    InvalidPayload { code: &'static str, message: String },
    #[error("{code}: {message}")]
    Validation { code: &'static str, message: String },
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

impl ReadModelRebuildError {
    pub fn code(&self) -> &'static str {
        match self {
            Self::InvalidPayload { code, .. } | Self::Validation { code, .. } => code,
            Self::Database(_) => "READ_MODEL_DATABASE_ERROR",
        }
    }
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct RebuildSummary {
    pub claimed: bool,
    pub rebuilt_targets: usize,
    pub row_count: i64,
    pub stale_scopes: i64,
}

#[derive(Clone)]
pub struct ReadModelRebuildWorker {
    pool: PgPool,
    worker_id: String,
}

impl ReadModelRebuildWorker {
    pub fn new(pool: PgPool, worker_id: impl Into<String>) -> Self {
        Self {
            pool,
            worker_id: worker_id.into(),
        }
    }

    pub async fn run_once(&self) -> Result<RebuildSummary, ReadModelRebuildError> {
        let Some(task) = self.claim_one_task().await? else {
            return Ok(RebuildSummary::default());
        };

        match self
            .rebuild_payload(task.payload.clone(), Some(task.id))
            .await
        {
            Ok(mut summary) => {
                summary.claimed = true;
                self.mark_task_succeeded(task.id, &summary).await?;
                Ok(summary)
            }
            Err(error) => {
                self.mark_task_failed(task.id, &error).await?;
                Err(error)
            }
        }
    }

    pub async fn run_loop(&self, interval: Duration) -> Result<(), ReadModelRebuildError> {
        loop {
            let summary = self.run_once().await?;
            tracing::info!(
                claimed = summary.claimed,
                rebuilt_targets = summary.rebuilt_targets,
                row_count = summary.row_count,
                stale_scopes = summary.stale_scopes,
                "read model rebuild worker iteration completed"
            );
            sleep(interval).await;
        }
    }

    pub async fn rebuild_payload(
        &self,
        payload: Value,
        task_id: Option<Uuid>,
    ) -> Result<RebuildSummary, ReadModelRebuildError> {
        let request = RebuildRequest::from_payload(payload)?;
        let mut summary = RebuildSummary::default();
        for target in &request.targets {
            let rows = match target.model {
                ReadModelKind::Workbench => {
                    let month = target.month.as_deref().ok_or_else(|| {
                        invalid_payload(
                            "READ_MODEL_SCOPE_MISSING",
                            "workbench rebuild requires month",
                        )
                    })?;
                    self.rebuild_workbench_month(month, &request, task_id)
                        .await?
                }
                ReadModelKind::SearchIndex => {
                    let month = target.month.as_deref().ok_or_else(|| {
                        invalid_payload(
                            "READ_MODEL_SCOPE_MISSING",
                            "search index rebuild requires month",
                        )
                    })?;
                    self.rebuild_search_index_month(month, &request).await?
                }
                ReadModelKind::CostStatistics => {
                    self.rebuild_cost_statistics(target, &request, task_id)
                        .await?
                }
                ReadModelKind::TaxOffset => {
                    let month = target.month.as_deref().ok_or_else(|| {
                        invalid_payload(
                            "READ_MODEL_SCOPE_MISSING",
                            "tax offset rebuild requires month",
                        )
                    })?;
                    self.rebuild_tax_offset_month(month, &request, task_id)
                        .await?
                }
            };
            summary.rebuilt_targets += 1;
            summary.row_count += rows;
        }
        summary.stale_scopes = self.count_stale_scopes().await?;
        Ok(summary)
    }

    async fn claim_one_task(&self) -> Result<Option<WorkerTask>, ReadModelRebuildError> {
        let row = sqlx::query(
            r#"
            with picked as (
              select id
              from job.worker_tasks
              where task_type = 'read_model.rebuild'
                and status in ('queued', 'retrying')
                and available_at <= now()
              order by priority desc, available_at asc, created_at asc
              for update skip locked
              limit 1
            )
            update job.worker_tasks task
            set status = 'running',
                phase = 'rebuilding',
                locked_by = $1,
                locked_at = now(),
                started_at = coalesce(started_at, now()),
                attempt_count = least(attempt_count + 1, max_attempts),
                error_code = null,
                error_summary = null,
                updated_at = now()
            from picked
            where task.id = picked.id
            returning task.id, task.payload
            "#,
        )
        .bind(&self.worker_id)
        .fetch_optional(&self.pool)
        .await?;

        Ok(row.map(|row| WorkerTask {
            id: row.get("id"),
            payload: row.get("payload"),
        }))
    }

    async fn mark_task_succeeded(
        &self,
        task_id: Uuid,
        summary: &RebuildSummary,
    ) -> Result<(), ReadModelRebuildError> {
        sqlx::query(
            r#"
            update job.worker_tasks
            set status = 'succeeded',
                phase = 'succeeded',
                result_summary = $2,
                current_count = total_count,
                percent = 100,
                locked_by = null,
                locked_at = null,
                finished_at = now(),
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(task_id)
        .bind(json!({
            "rebuilt_targets": summary.rebuilt_targets,
            "row_count": summary.row_count,
            "stale_scopes": summary.stale_scopes
        }))
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    async fn mark_task_failed(
        &self,
        task_id: Uuid,
        error: &ReadModelRebuildError,
    ) -> Result<(), ReadModelRebuildError> {
        sqlx::query(
            r#"
            update job.worker_tasks
            set status = 'failed',
                phase = 'failed',
                error_code = $2,
                error_summary = $3,
                retryable = false,
                locked_by = null,
                locked_at = null,
                finished_at = now(),
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(task_id)
        .bind(error.code())
        .bind(error.to_string())
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    async fn rebuild_workbench_month(
        &self,
        month: &str,
        request: &RebuildRequest,
        task_id: Option<Uuid>,
    ) -> Result<i64, ReadModelRebuildError> {
        validate_month(month)?;
        let mut tx = self.pool.begin().await?;
        sqlx::query(
            "select read_model.ensure_scope_month_partitions(to_date($1 || '-01', 'YYYY-MM-DD'))",
        )
        .bind(month)
        .execute(&mut *tx)
        .await?;
        sqlx::query(WORKBENCH_TEMP_SQL).execute(&mut *tx).await?;
        sqlx::query(WORKBENCH_INSERT_BANK_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;
        sqlx::query(WORKBENCH_INSERT_INVOICE_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;
        sqlx::query(WORKBENCH_INSERT_OA_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;

        let row_count = scalar_i64(
            &mut tx,
            "select count(*)::bigint from workbench_rebuild_rows",
        )
        .await?;
        sqlx::query("delete from read_model.workbench_rows where scope_month = to_date($1 || '-01', 'YYYY-MM-DD')")
            .bind(month)
            .execute(&mut *tx)
            .await?;
        sqlx::query(WORKBENCH_PUBLISH_ROWS_SQL)
            .execute(&mut *tx)
            .await?;
        sqlx::query(WORKBENCH_PUBLISH_SNAPSHOT_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .bind(&request.reason)
            .bind(task_id)
            .bind(WORKBENCH_SCHEMA_VERSION)
            .execute(&mut *tx)
            .await?;
        tx.commit().await?;
        Ok(row_count)
    }

    async fn rebuild_search_index_month(
        &self,
        month: &str,
        request: &RebuildRequest,
    ) -> Result<i64, ReadModelRebuildError> {
        validate_month(month)?;
        let mut tx = self.pool.begin().await?;
        sqlx::query("select read_model.create_search_index_rows_partition(to_date($1 || '-01', 'YYYY-MM-DD'))")
            .bind(month)
            .execute(&mut *tx)
            .await?;
        sqlx::query(SEARCH_TEMP_SQL).execute(&mut *tx).await?;
        sqlx::query(SEARCH_INSERT_BANK_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;
        sqlx::query(SEARCH_INSERT_INVOICE_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;
        sqlx::query(SEARCH_INSERT_OA_SQL)
            .bind(month)
            .bind(&request.source_versions)
            .execute(&mut *tx)
            .await?;
        let row_count = scalar_i64(
            &mut tx,
            "select count(*)::bigint from search_index_rebuild_rows",
        )
        .await?;
        sqlx::query("delete from read_model.search_index_rows where scope_month = to_date($1 || '-01', 'YYYY-MM-DD')")
            .bind(month)
            .execute(&mut *tx)
            .await?;
        sqlx::query(SEARCH_PUBLISH_SQL).execute(&mut *tx).await?;
        tx.commit().await?;
        Ok(row_count)
    }

    async fn rebuild_cost_statistics(
        &self,
        target: &RebuildTarget,
        request: &RebuildRequest,
        task_id: Option<Uuid>,
    ) -> Result<i64, ReadModelRebuildError> {
        let (project_scope, month) = parse_cost_scope_key(&target.scope_key)?;
        let mut tx = self.pool.begin().await?;
        let payload: Value = sqlx::query(COST_PAYLOAD_SQL)
            .bind(&month)
            .bind(&project_scope)
            .fetch_one(&mut *tx)
            .await?
            .get("payload");
        sqlx::query(COST_UPSERT_SQL)
            .bind(&target.scope_key)
            .bind(&month)
            .bind(&project_scope)
            .bind(&payload)
            .bind(vec![
                format!("workbench:{month}"),
                format!("search:{month}"),
            ])
            .bind(&request.source_versions)
            .bind(task_id)
            .bind(COST_SCHEMA_VERSION)
            .execute(&mut *tx)
            .await?;
        assert_cost_ready(&mut tx, &target.scope_key).await?;
        tx.commit().await?;
        Ok(payload
            .get("summary")
            .and_then(|summary| summary.get("transaction_count"))
            .and_then(Value::as_i64)
            .unwrap_or(0))
    }

    async fn rebuild_tax_offset_month(
        &self,
        month: &str,
        request: &RebuildRequest,
        task_id: Option<Uuid>,
    ) -> Result<i64, ReadModelRebuildError> {
        validate_month(month)?;
        let mut tx = self.pool.begin().await?;
        let payload: Value = sqlx::query(TAX_PAYLOAD_SQL)
            .bind(month)
            .fetch_one(&mut *tx)
            .await?
            .get("payload");
        validate_tax_payload(&payload)?;
        sqlx::query(TAX_UPSERT_SQL)
            .bind(month)
            .bind(&payload)
            .bind(vec![
                format!("workbench:{month}"),
                format!("search:{month}"),
            ])
            .bind(&request.source_versions)
            .bind(task_id)
            .bind(TAX_SCHEMA_VERSION)
            .execute(&mut *tx)
            .await?;
        assert_tax_ready(&mut tx, month).await?;
        tx.commit().await?;
        Ok(payload
            .get("output_items")
            .and_then(Value::as_array)
            .map(|items| items.len() as i64)
            .unwrap_or(0)
            + payload
                .get("input_plan_items")
                .and_then(Value::as_array)
                .map(|items| items.len() as i64)
                .unwrap_or(0)
            + payload
                .get("certified_items")
                .and_then(Value::as_array)
                .map(|items| items.len() as i64)
                .unwrap_or(0))
    }

    pub async fn count_stale_scopes(&self) -> Result<i64, ReadModelRebuildError> {
        scalar_i64_pool(
            &self.pool,
            r#"
            select (
              (select count(*) from read_model.workbench_snapshots where stale)
              + (select count(*) from read_model.cost_statistics_read_models where stale or cache_status <> 'ready')
              + (select count(*) from read_model.tax_offset_read_models where stale or cache_status <> 'ready')
              + (select count(distinct scope_month) from read_model.search_index_rows where stale)
            )::bigint
            "#,
        )
        .await
    }
}

#[derive(Debug)]
struct WorkerTask {
    id: Uuid,
    payload: Value,
}

pub fn validate_tax_payload(payload: &Value) -> Result<(), ReadModelRebuildError> {
    for key in ["output_items", "input_plan_items", "certified_items"] {
        if !payload.get(key).is_some_and(Value::is_array) {
            return Err(ReadModelRebuildError::Validation {
                code: "READ_MODEL_TAX_PAYLOAD_INVALID",
                message: format!("tax offset payload.{key} must be an array"),
            });
        }
    }
    Ok(())
}

fn push_targets_for_model(
    targets: &mut Vec<RebuildTarget>,
    kind: ReadModelKind,
    scope_keys: &[String],
    months: &[String],
) -> Result<(), ReadModelRebuildError> {
    match kind {
        ReadModelKind::Workbench => {
            let mut keys = scope_keys
                .iter()
                .filter(|key| key.starts_with("workbench:"))
                .cloned()
                .collect::<Vec<_>>();
            if keys.is_empty() {
                keys = months
                    .iter()
                    .map(|month| format!("workbench:{month}"))
                    .collect();
            }
            for key in keys {
                let month = key
                    .strip_prefix("workbench:")
                    .filter(|value| *value != "all");
                if let Some(month) = month {
                    validate_month(month)?;
                    push_unique(
                        targets,
                        RebuildTarget::new(ReadModelKind::Workbench, &key, Some(month)),
                    );
                }
            }
        }
        ReadModelKind::SearchIndex => {
            let keys = if months.is_empty() {
                scope_keys
                    .iter()
                    .filter_map(|key| month_from_scope_key(key))
                    .collect::<Vec<_>>()
            } else {
                months.to_vec()
            };
            for month in keys {
                validate_month(&month)?;
                push_unique(
                    targets,
                    RebuildTarget::new(
                        ReadModelKind::SearchIndex,
                        &format!("search:{month}"),
                        Some(&month),
                    ),
                );
            }
        }
        ReadModelKind::CostStatistics => {
            let keys = scope_keys
                .iter()
                .filter(|key| is_cost_scope_key(key))
                .cloned()
                .collect::<Vec<_>>();
            if keys.is_empty() {
                for month in months {
                    for project_scope in ["active", "all"] {
                        push_unique(
                            targets,
                            RebuildTarget::new(
                                ReadModelKind::CostStatistics,
                                &format!("{project_scope}:{month}"),
                                Some(month),
                            ),
                        );
                    }
                }
            } else {
                for key in keys {
                    let (_, month) = parse_cost_scope_key(&key)?;
                    push_unique(
                        targets,
                        RebuildTarget::new(ReadModelKind::CostStatistics, &key, Some(&month)),
                    );
                }
            }
        }
        ReadModelKind::TaxOffset => {
            let keys = scope_keys
                .iter()
                .filter(|key| is_yyyy_mm(key))
                .cloned()
                .collect::<Vec<_>>();
            let months = if keys.is_empty() {
                months.to_vec()
            } else {
                keys
            };
            for month in months {
                validate_month(&month)?;
                push_unique(
                    targets,
                    RebuildTarget::new(ReadModelKind::TaxOffset, &month, Some(&month)),
                );
            }
        }
    }
    Ok(())
}

fn push_unique(targets: &mut Vec<RebuildTarget>, target: RebuildTarget) {
    if !targets.contains(&target) {
        targets.push(target);
    }
}

fn string_array(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
        .collect()
}

fn source_version_metadata(
    object: &serde_json::Map<String, Value>,
) -> Result<Value, ReadModelRebuildError> {
    object
        .get("source_versions")
        .or_else(|| object.get("source_watermark"))
        .cloned()
        .filter(Value::is_object)
        .ok_or_else(|| {
            invalid_payload(
                "READ_MODEL_SOURCE_VERSION_MISSING",
                "payload.source_versions or payload.source_watermark must be an object with fact_updated_at",
            )
        })
}

fn has_fact_watermark(value: &Value) -> bool {
    value
        .get("fact_updated_at")
        .and_then(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .is_some()
}

fn month_from_scope_key(key: &str) -> Option<String> {
    if is_yyyy_mm(key) {
        return Some(key.to_owned());
    }
    key.rsplit_once(':')
        .map(|(_, month)| month)
        .filter(|month| is_yyyy_mm(month))
        .map(ToOwned::to_owned)
}

fn parse_cost_scope_key(scope_key: &str) -> Result<(String, String), ReadModelRebuildError> {
    let Some((project_scope, month)) = scope_key.split_once(':') else {
        return Err(invalid_payload(
            "READ_MODEL_COST_SCOPE_INVALID",
            "cost statistics scope_key must use project_scope:YYYY-MM",
        ));
    };
    if !matches!(project_scope, "active" | "all") || !(is_yyyy_mm(month) || month == "all") {
        return Err(invalid_payload(
            "READ_MODEL_COST_SCOPE_INVALID",
            "cost statistics scope_key must use active|all:YYYY-MM or active|all:all",
        ));
    }
    Ok((project_scope.to_owned(), month.to_owned()))
}

fn is_cost_scope_key(key: &str) -> bool {
    parse_cost_scope_key(key).is_ok()
}

fn validate_month(month: &str) -> Result<(), ReadModelRebuildError> {
    if is_yyyy_mm(month) {
        Ok(())
    } else {
        Err(invalid_payload(
            "READ_MODEL_MONTH_INVALID",
            "month must use YYYY-MM",
        ))
    }
}

fn is_yyyy_mm(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 7
        && bytes[0..4].iter().all(|byte| byte.is_ascii_digit())
        && bytes[4] == b'-'
        && bytes[5..7].iter().all(|byte| byte.is_ascii_digit())
        && matches!(
            &value[5..7],
            "01" | "02" | "03" | "04" | "05" | "06" | "07" | "08" | "09" | "10" | "11" | "12"
        )
}

fn invalid_payload(code: &'static str, message: impl Into<String>) -> ReadModelRebuildError {
    ReadModelRebuildError::InvalidPayload {
        code,
        message: message.into(),
    }
}

async fn scalar_i64(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    sql: &str,
) -> Result<i64, ReadModelRebuildError> {
    let row = sqlx::query(sql).fetch_one(&mut **tx).await?;
    Ok(row.get::<i64, _>(0))
}

async fn scalar_i64_pool(pool: &PgPool, sql: &str) -> Result<i64, ReadModelRebuildError> {
    let row = sqlx::query(sql).fetch_one(pool).await?;
    Ok(row.get::<i64, _>(0))
}

async fn assert_cost_ready(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    scope_key: &str,
) -> Result<(), ReadModelRebuildError> {
    let row = sqlx::query(
        r#"
        select count(*)::bigint as failures
        from read_model.cost_statistics_read_models
        where scope_key = $1
          and (
            entry_count <> coalesce(nullif(payload #>> '{summary,transaction_count}', '')::integer, jsonb_array_length(coalesce(payload -> 'time_rows', '[]'::jsonb)))
            or schema_version <> '2026-05-cost-statistics-explorer-v1'
            or cache_status <> 'ready'
            or stale
          )
        "#,
    )
    .bind(scope_key)
    .fetch_one(&mut **tx)
    .await?;
    let failures: i64 = row.get("failures");
    if failures == 0 {
        Ok(())
    } else {
        Err(ReadModelRebuildError::Validation {
            code: "READ_MODEL_VALIDATION_FAILED",
            message: format!("cost_statistics {scope_key} failed post-publish validation"),
        })
    }
}

async fn assert_tax_ready(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    scope_key: &str,
) -> Result<(), ReadModelRebuildError> {
    let row = sqlx::query(
        r#"
        select count(*)::bigint as failures
        from read_model.tax_offset_read_models
        where scope_key = $1
          and (
            output_count <> jsonb_array_length(payload -> 'output_items')
            or input_plan_count <> jsonb_array_length(payload -> 'input_plan_items')
            or certified_count <> jsonb_array_length(payload -> 'certified_items')
            or schema_version <> '2026-05-tax-offset-month-v1'
            or cache_status <> 'ready'
            or stale
          )
        "#,
    )
    .bind(scope_key)
    .fetch_one(&mut **tx)
    .await?;
    let failures: i64 = row.get("failures");
    if failures == 0 {
        Ok(())
    } else {
        Err(ReadModelRebuildError::Validation {
            code: "READ_MODEL_VALIDATION_FAILED",
            message: format!("tax_offset {scope_key} failed post-publish validation"),
        })
    }
}

const WORKBENCH_TEMP_SQL: &str = r#"
create temporary table workbench_rebuild_rows
(like read_model.workbench_rows including defaults)
on commit drop
"#;

const WORKBENCH_INSERT_BANK_SQL: &str = r#"
insert into workbench_rebuild_rows (
  scope_month, scope_key, row_id, row_type, source_kind, source_entity_type, source_entity_id,
  business_date, counterparty_name, project_id, project_name, amount, direction, status, zone_hint,
  group_key, relation_case_id, exception_case_id, ignored, handled_exception, payload, source_versions,
  generated_at, stale
)
select
  b.txn_month,
  'workbench:' || to_char(b.txn_month, 'YYYY-MM'),
  b.id,
  'bank',
  'app.bank_transactions',
  'bank_transaction',
  b.id,
  b.txn_date,
  b.counterparty_name_raw,
  b.project_id,
  nullif(coalesce(wro.override_payload ->> 'project_name', b.raw_payload #>> '{project_name}'), ''),
  b.amount,
  b.txn_direction,
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  coalesce(rel.case_id::text, exc.id::text),
  rel.case_id,
  exc.id,
  ignored.id is not null,
  exc.id is not null and exc.status in ('resolved', 'ignored'),
  jsonb_strip_nulls(jsonb_build_object(
    'id', b.id,
    'type', 'bank',
    'case_id', rel.case_id,
    'direction', case when b.txn_direction = 'outflow' then '支出' else '收入' end,
    'trade_time', to_char(b.trade_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'pay_receive_time', to_char(coalesce(b.pay_receive_time, b.trade_time) at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
    'amount', b.amount::text,
    'debit_amount', case when b.txn_direction = 'outflow' then b.amount::text else '' end,
    'credit_amount', case when b.txn_direction = 'inflow' then b.amount::text else '' end,
    'counterparty_name', b.counterparty_name_raw,
    'account_name', b.account_name,
    'summary', b.summary,
    'remark', b.remark,
    'available_actions', case when rel.case_id is null then jsonb_build_array('confirm_link', 'ignore') else jsonb_build_array('cancel_link') end,
    'summary_fields', jsonb_build_object('资金方向', b.txn_direction, '交易时间', coalesce(b.txn_date::text, '—'), '对方户名', b.counterparty_name_raw, '金额', b.amount::text),
    'detail_fields', jsonb_build_object('账号', b.account_no, '账户名称', coalesce(b.account_name, '—'), '摘要', coalesce(b.summary, '—'), '备注', coalesce(b.remark, '—'))
  )),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.bank_transactions b
left join lateral (
  select r.case_id
  from app.reconciliation_case_rows r
  join app.reconciliation_cases c on c.id = r.case_id and c.status = 'confirmed'
  where r.object_type = 'bank_transaction'
    and r.object_id = b.id
    and r.binding_status = 'active'
  order by r.created_at desc
  limit 1
) rel on true
left join lateral (
  select o.id, o.override_payload
  from app.workbench_row_overrides o
  where o.source_object_type = 'bank_transaction'
    and o.source_object_id = b.id
    and o.override_type = 'project_assignment'
    and o.status = 'active'
  order by o.updated_at desc
  limit 1
) wro on true
left join lateral (
  select o.id
  from app.workbench_row_overrides o
  where o.source_object_type = 'bank_transaction'
    and o.source_object_id = b.id
    and o.override_type = 'ignore'
    and o.status = 'active'
  limit 1
) ignored on true
left join lateral (
  select e.id, e.status
  from app.workbench_exception_cases e
  where b.id = any(e.source_bank_txn_ids)
     or e.source_case_id = rel.case_id
  order by e.updated_at desc
  limit 1
) exc on true
where b.txn_month = to_date($1 || '-01', 'YYYY-MM-DD')
"#;

const WORKBENCH_INSERT_INVOICE_SQL: &str = r#"
insert into workbench_rebuild_rows (
  scope_month, scope_key, row_id, row_type, source_kind, source_entity_type, source_entity_id,
  business_date, counterparty_name, project_id, project_name, amount, direction, status, zone_hint,
  group_key, relation_case_id, exception_case_id, ignored, handled_exception, payload, source_versions,
  generated_at, stale
)
select
  i.invoice_month,
  'workbench:' || to_char(i.invoice_month, 'YYYY-MM'),
  i.id,
  'invoice',
  'app.invoices',
  'invoice',
  i.id,
  i.invoice_date,
  coalesce(i.seller_name, i.buyer_name),
  i.project_id,
  nullif(i.raw_payload #>> '{project_name}', ''),
  coalesce(i.total_with_tax, i.amount),
  i.invoice_type,
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  coalesce(rel.case_id::text, exc.id::text),
  rel.case_id,
  exc.id,
  ignored.id is not null,
  exc.id is not null and exc.status in ('resolved', 'ignored'),
  jsonb_strip_nulls(jsonb_build_object(
    'id', i.id,
    'type', 'invoice',
    'case_id', rel.case_id,
    'seller_tax_no', i.seller_tax_no,
    'seller_name', i.seller_name,
    'buyer_tax_no', i.buyer_tax_no,
    'buyer_name', i.buyer_name,
    'invoice_code', i.invoice_code,
    'invoice_no', i.invoice_no,
    'digital_invoice_no', i.digital_invoice_no,
    'issue_date', i.invoice_date,
    'amount', i.amount::text,
    'tax_amount', i.tax_amount::text,
    'total_with_tax', coalesce(i.total_with_tax, i.amount)::text,
    'invoice_type', case when i.invoice_type = 'output' then '销项发票' else '进项发票' end,
    'available_actions', case when rel.case_id is null then jsonb_build_array('confirm_link', 'ignore') else jsonb_build_array('cancel_link') end,
    'summary_fields', jsonb_build_object('开票日期', coalesce(i.invoice_date::text, '—'), '金额', i.amount::text, '价税合计', coalesce(i.total_with_tax, i.amount)::text, '发票类型', i.invoice_type),
    'detail_fields', jsonb_build_object('发票代码', coalesce(i.invoice_code, '—'), '发票号码', i.invoice_no, '数电发票号码', coalesce(i.digital_invoice_no, '—'), '备注', coalesce(i.remark, '—'))
  )),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.invoices i
left join lateral (
  select r.case_id
  from app.reconciliation_case_rows r
  join app.reconciliation_cases c on c.id = r.case_id and c.status = 'confirmed'
  where r.object_type = 'invoice'
    and r.object_id = i.id
    and r.binding_status = 'active'
  order by r.created_at desc
  limit 1
) rel on true
left join lateral (
  select o.id
  from app.workbench_row_overrides o
  where o.source_object_type = 'invoice'
    and o.source_object_id = i.id
    and o.override_type = 'ignore'
    and o.status = 'active'
  limit 1
) ignored on true
left join lateral (
  select e.id, e.status
  from app.workbench_exception_cases e
  where i.id = any(e.source_invoice_ids)
     or e.source_case_id = rel.case_id
  order by e.updated_at desc
  limit 1
) exc on true
where i.invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
  and i.workbench_visibility = 'visible'
"#;

const WORKBENCH_INSERT_OA_SQL: &str = r#"
insert into workbench_rebuild_rows (
  scope_month, scope_key, row_id, row_type, source_kind, source_entity_type, source_entity_id,
  business_date, counterparty_name, project_id, project_name, amount, direction, status, zone_hint,
  group_key, relation_case_id, exception_case_id, ignored, handled_exception, payload, source_versions,
  generated_at, stale
)
select
  coalesce(oa.approved_month, oa.source_updated_month),
  'workbench:' || to_char(coalesce(oa.approved_month, oa.source_updated_month), 'YYYY-MM'),
  oa.id,
  'oa',
  'app.oa_applications',
  'oa_application',
  oa.id,
  coalesce(oa.approved_at::date, oa.source_updated_at::date),
  oa.counterparty_name,
  oa.project_id,
  oa.project_name,
  oa.amount,
  'oa',
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  case
    when ignored.id is not null then 'ignored'
    when rel.case_id is not null then 'paired'
    when exc.id is not null and exc.status in ('resolved', 'ignored') then 'processed_exception'
    else 'open'
  end,
  coalesce(rel.case_id::text, exc.id::text),
  rel.case_id,
  exc.id,
  ignored.id is not null,
  exc.id is not null and exc.status in ('resolved', 'ignored'),
  jsonb_strip_nulls(jsonb_build_object(
    'id', oa.id,
    'type', 'oa',
    'case_id', rel.case_id,
    'workflow_no', oa.workflow_no,
    'title', oa.title,
    'form_type', oa.form_type,
    'status', oa.status,
    'applicant', oa.applicant,
    'department_name', oa.department_name,
    'project_id', oa.project_id,
    'project_name', oa.project_name,
    'counterparty_name', oa.counterparty_name,
    'amount', oa.amount::text,
    'available_actions', case when rel.case_id is null then jsonb_build_array('confirm_link', 'ignore') else jsonb_build_array('cancel_link') end,
    'summary_fields', jsonb_build_object('流程编号', coalesce(oa.workflow_no, '—'), '申请人', coalesce(oa.applicant, '—'), '项目名称', coalesce(oa.project_name, '—'), '金额', coalesce(oa.amount::text, '—')),
    'detail_fields', jsonb_build_object('表单类型', oa.form_type, '部门', coalesce(oa.department_name, '—'), '对方户名', coalesce(oa.counterparty_name, '—'))
  )),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.oa_applications oa
left join lateral (
  select r.case_id
  from app.reconciliation_case_rows r
  join app.reconciliation_cases c on c.id = r.case_id and c.status = 'confirmed'
  where r.object_type = 'oa_application'
    and r.object_id = oa.id
    and r.binding_status = 'active'
  order by r.created_at desc
  limit 1
) rel on true
left join lateral (
  select o.id
  from app.workbench_row_overrides o
  where o.source_object_type = 'oa_application'
    and o.source_object_id = oa.id
    and o.override_type = 'ignore'
    and o.status = 'active'
  limit 1
) ignored on true
left join lateral (
  select e.id, e.status
  from app.workbench_exception_cases e
  where e.source_case_id = rel.case_id
  order by e.updated_at desc
  limit 1
) exc on true
where coalesce(oa.approved_month, oa.source_updated_month) = to_date($1 || '-01', 'YYYY-MM-DD')
"#;

const WORKBENCH_PUBLISH_ROWS_SQL: &str = r#"
insert into read_model.workbench_rows (
  id, scope_month, scope_key, row_id, row_type, source_kind, source_entity_type, source_entity_id,
  business_date, counterparty_name, project_id, project_name, amount, direction, status, zone_hint,
  group_key, relation_case_id, candidate_match_id, exception_case_id, ignored, handled_exception,
  payload, source_versions, generated_at, stale, stale_reason
)
select
  id, scope_month, scope_key, row_id, row_type, source_kind, source_entity_type, source_entity_id,
  business_date, counterparty_name, project_id, project_name, amount, direction, status, zone_hint,
  group_key, relation_case_id, candidate_match_id, exception_case_id, ignored, handled_exception,
  payload, source_versions, generated_at, false, null
from workbench_rebuild_rows
"#;

const WORKBENCH_PUBLISH_SNAPSHOT_SQL: &str = r#"
insert into read_model.workbench_snapshots (
  scope_key, scope_type, scope_month, schema_version, payload, ignored_rows, summary,
  source_versions, generated_at, stale, stale_reason, rebuild_task_id, updated_at
)
select
  'workbench:' || $1::text,
  'month',
  to_date($1 || '-01', 'YYYY-MM-DD'),
  $5,
  jsonb_build_object(
    'month', $1::text,
    'summary', summary,
    'rebuild_blockers', jsonb_build_array('candidate_match_id_requires_app_candidate_fact_source'),
    'paired', jsonb_build_object(
      'oa', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'oa' and zone_hint = 'paired'), '[]'::jsonb),
      'bank', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'bank' and zone_hint = 'paired'), '[]'::jsonb),
      'invoice', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'invoice' and zone_hint = 'paired'), '[]'::jsonb)
    ),
    'open', jsonb_build_object(
      'oa', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'oa' and zone_hint = 'open'), '[]'::jsonb),
      'bank', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'bank' and zone_hint = 'open'), '[]'::jsonb),
      'invoice', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where row_type = 'invoice' and zone_hint = 'open'), '[]'::jsonb)
    ),
    'processed_exception', coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where zone_hint = 'processed_exception'), '[]'::jsonb)
  ),
  coalesce((select jsonb_agg(payload order by business_date desc nulls last) from workbench_rebuild_rows where ignored), '[]'::jsonb),
  summary,
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false,
  null,
  $4::uuid,
  now()
from (
  select jsonb_build_object(
    'oa_count', count(*) filter (where row_type = 'oa'),
    'bank_count', count(*) filter (where row_type = 'bank'),
    'invoice_count', count(*) filter (where row_type = 'invoice'),
    'paired_count', count(*) filter (where zone_hint = 'paired'),
    'open_count', count(*) filter (where zone_hint = 'open'),
    'ignored_count', count(*) filter (where zone_hint = 'ignored'),
    'exception_count', count(*) filter (where zone_hint = 'processed_exception'),
    'row_count', count(*),
    'stale_reason', $3::text,
    'blockers', jsonb_build_array('candidate_match_id_requires_app_candidate_fact_source')
  ) as summary
  from workbench_rebuild_rows
) s
on conflict (scope_key) do update set
  scope_type = excluded.scope_type,
  scope_month = excluded.scope_month,
  schema_version = excluded.schema_version,
  payload = excluded.payload,
  ignored_rows = excluded.ignored_rows,
  summary = excluded.summary,
  source_versions = excluded.source_versions,
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  rebuild_task_id = excluded.rebuild_task_id,
  updated_at = now()
"#;

const SEARCH_TEMP_SQL: &str = r#"
create temporary table search_index_rebuild_rows
(like read_model.search_index_rows including defaults)
on commit drop
"#;

const SEARCH_INSERT_BANK_SQL: &str = r#"
insert into search_index_rebuild_rows (
  entity_type, entity_id, source_kind, scope_month, title, subtitle, searchable_text,
  searchable_tokens, amount, status, zone_hint, project_id, project_name, jump_target, payload,
  source_versions, generated_at, stale
)
select
  'bank_transaction',
  b.id,
  'app.bank_transactions',
  b.txn_month,
  coalesce(nullif(b.counterparty_name_raw, ''), '银行流水'),
  concat_ws(' · ', b.account_name, b.txn_direction, b.txn_date::text),
  concat_ws(' ', b.id::text, b.counterparty_name_raw, b.counterparty_name_normalized, b.bank_serial_no, b.enterprise_serial_no, b.summary, b.remark, b.txn_direction, b.amount::text, b.txn_date::text, w.project_name),
  jsonb_build_object('counterparty', b.counterparty_name_normalized, 'direction', b.txn_direction),
  b.amount,
  coalesce(w.status, b.status),
  coalesce(w.zone_hint, 'open'),
  b.project_id,
  w.project_name,
  jsonb_build_object('route', 'workbench', 'month', $1::text, 'scope_month', b.txn_month, 'entity_type', 'bank_transaction', 'entity_id', b.id, 'record_type', 'bank', 'row_id', coalesce(w.row_id, b.id), 'zone_hint', coalesce(w.zone_hint, 'open'), 'group_id', w.group_key),
  jsonb_build_object('txn_date', b.txn_date, 'currency', b.currency),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.bank_transactions b
left join read_model.workbench_rows w
  on w.scope_month = b.txn_month
 and w.source_entity_type = 'bank_transaction'
 and w.source_entity_id = b.id
 and not w.stale
where b.txn_month = to_date($1 || '-01', 'YYYY-MM-DD')
"#;

const SEARCH_INSERT_INVOICE_SQL: &str = r#"
insert into search_index_rebuild_rows (
  entity_type, entity_id, source_kind, scope_month, title, subtitle, searchable_text,
  searchable_tokens, amount, status, zone_hint, project_id, project_name, jump_target, payload,
  source_versions, generated_at, stale
)
select
  'invoice',
  i.id,
  'app.invoices',
  i.invoice_month,
  coalesce(i.invoice_no, i.digital_invoice_no, i.seller_name, '发票'),
  concat_ws(' · ', i.invoice_type, i.seller_name, i.buyer_name),
  concat_ws(' ', i.id::text, i.invoice_no, i.invoice_code, i.digital_invoice_no, i.seller_name, i.buyer_name, i.amount::text, i.total_with_tax::text, i.invoice_date::text, i.invoice_type, i.status, w.project_name, i.remark),
  jsonb_build_object('invoice_no', coalesce(i.invoice_no, i.digital_invoice_no), 'seller', i.seller_name, 'buyer', i.buyer_name),
  coalesce(i.total_with_tax, i.amount),
  coalesce(w.status, i.status),
  coalesce(w.zone_hint, 'open'),
  i.project_id,
  w.project_name,
  jsonb_build_object('route', 'workbench', 'month', $1::text, 'scope_month', i.invoice_month, 'entity_type', 'invoice', 'entity_id', i.id, 'record_type', 'invoice', 'row_id', coalesce(w.row_id, i.id), 'zone_hint', coalesce(w.zone_hint, 'open'), 'group_id', w.group_key),
  jsonb_build_object('invoice_type', i.invoice_type, 'invoice_date', i.invoice_date, 'currency', i.currency),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.invoices i
left join read_model.workbench_rows w
  on w.scope_month = i.invoice_month
 and w.source_entity_type = 'invoice'
 and w.source_entity_id = i.id
 and not w.stale
where i.invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
  and i.workbench_visibility = 'visible'
"#;

const SEARCH_INSERT_OA_SQL: &str = r#"
insert into search_index_rebuild_rows (
  entity_type, entity_id, source_kind, scope_month, title, subtitle, searchable_text,
  searchable_tokens, amount, status, zone_hint, project_id, project_name, jump_target, payload,
  source_versions, generated_at, stale
)
select
  'oa_application',
  oa.id,
  'app.oa_applications',
  coalesce(oa.approved_month, oa.source_updated_month),
  coalesce(oa.workflow_no, oa.title, oa.project_name, 'OA'),
  concat_ws(' · ', oa.form_type, oa.applicant, oa.counterparty_name),
  concat_ws(' ', oa.id::text, oa.oa_source_id, oa.workflow_no, oa.title, oa.form_type, oa.status, oa.applicant, oa.department_name, oa.project_id, oa.project_name, oa.counterparty_name, oa.amount::text),
  jsonb_build_object('workflow_no', oa.workflow_no, 'applicant', oa.applicant, 'form_type', oa.form_type),
  oa.amount,
  coalesce(w.status, oa.status),
  coalesce(w.zone_hint, 'open'),
  oa.project_id,
  oa.project_name,
  jsonb_build_object('route', 'workbench', 'month', $1::text, 'scope_month', coalesce(oa.approved_month, oa.source_updated_month), 'entity_type', 'oa_application', 'entity_id', oa.id, 'record_type', 'oa', 'row_id', coalesce(w.row_id, oa.id), 'zone_hint', coalesce(w.zone_hint, 'open'), 'group_id', w.group_key),
  jsonb_build_object('oa_source_id', oa.oa_source_id, 'workflow_no', oa.workflow_no, 'form_type', oa.form_type),
  $2::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  now(),
  false
from app.oa_applications oa
left join read_model.workbench_rows w
  on w.scope_month = coalesce(oa.approved_month, oa.source_updated_month)
 and w.source_entity_type = 'oa_application'
 and w.source_entity_id = oa.id
 and not w.stale
where coalesce(oa.approved_month, oa.source_updated_month) = to_date($1 || '-01', 'YYYY-MM-DD')
"#;

const SEARCH_PUBLISH_SQL: &str = r#"
insert into read_model.search_index_rows (
  id, entity_type, entity_id, source_kind, scope_month, title, subtitle, searchable_text,
  searchable_tokens, amount, status, zone_hint, project_id, project_name, jump_target, payload,
  source_versions, generated_at, stale, stale_reason
)
select
  id, entity_type, entity_id, source_kind, scope_month, title, subtitle, searchable_text,
  searchable_tokens, amount, status, zone_hint, project_id, project_name, jump_target, payload,
  source_versions, generated_at, false, null
from search_index_rebuild_rows
"#;

const COST_PAYLOAD_SQL: &str = r#"
with bank_entries as (
  select
    b.id as transaction_id,
    b.trade_time,
    b.txn_date,
    b.counterparty_name_raw,
    b.account_name,
    b.txn_direction,
    b.amount,
    b.remark,
    coalesce(oa.project_name, b.raw_payload #>> '{project_name}', '未关联项目') as project_name,
    coalesce(oa.project_id, b.project_id) as project_id,
    coalesce(item.expense_type, b.raw_payload #>> '{expense_type}', '未归类') as expense_type,
    coalesce(item.normalized_payload #>> '{expense_content}', item.raw_payload #>> '{expense_content}', b.summary, '未填写费用内容') as expense_content,
    oa.applicant as oa_applicant,
    jsonb_strip_nulls(jsonb_build_object(
      'transaction_id', b.id,
      'project_scope', $2::text,
      'blockers', case
        when oa.id is null or item.id is null then jsonb_build_array('cost_context_missing_oa_or_expense_item')
        when $2::text = 'active' then jsonb_build_array('active_project_scope_uses_all_until_project_status_fact_exists')
        else '[]'::jsonb
      end
    )) as metadata
  from app.bank_transactions b
  left join lateral (
    select r.case_id
    from app.reconciliation_case_rows r
    join app.reconciliation_cases c on c.id = r.case_id and c.status = 'confirmed'
    where r.object_type = 'bank_transaction'
      and r.object_id = b.id
      and r.binding_status = 'active'
    order by r.created_at desc
    limit 1
  ) rel on true
  left join lateral (
    select oa.*
    from app.reconciliation_case_rows r
    join app.oa_applications oa on oa.id = r.object_id
    where r.case_id = rel.case_id
      and r.object_type = 'oa_application'
      and r.binding_status = 'active'
    limit 1
  ) oa on true
  left join lateral (
    select i.*
    from app.oa_application_items i
    where i.application_id = oa.id
      and i.item_type in ('expense', 'project', 'other')
    order by i.line_no
    limit 1
  ) item on true
  where ($1::text = 'all' or b.txn_month = to_date($1 || '-01', 'YYYY-MM-DD'))
    and b.txn_direction = 'outflow'
),
serialized as (
  select
    jsonb_build_object(
      'group_id', transaction_id::text,
      'transaction_id', transaction_id::text,
      'trade_time', coalesce(to_char(trade_time at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), txn_date::text, ''),
      'direction', '支出',
      'project_name', project_name,
      'project_id', project_id,
      'expense_type', expense_type,
      'expense_content', expense_content,
      'amount', amount::text,
      'counterparty_name', counterparty_name_raw,
      'payment_account_label', coalesce(account_name, ''),
      'remark', coalesce(remark, ''),
      'oa_applicant', coalesce(oa_applicant, '—'),
      'metadata', metadata
    ) as row_payload,
    *
  from bank_entries
)
select jsonb_build_object(
  'month', $1::text,
  'project_scope', $2::text,
  'summary', jsonb_build_object(
    'row_count', count(distinct (project_name, expense_type, expense_content)),
    'transaction_count', count(*),
    'total_amount', coalesce(sum(amount), 0)::text,
    'blockers', coalesce(jsonb_agg(distinct blocker.value) filter (where blocker.value is not null), '[]'::jsonb)
  ),
  'time_rows', coalesce(jsonb_agg(row_payload order by trade_time desc nulls last, transaction_id) filter (where transaction_id is not null), '[]'::jsonb),
  'project_rows', coalesce((
    select jsonb_agg(jsonb_build_object('project_name', project_name, 'total_amount', total_amount::text, 'transaction_count', transaction_count, 'expense_type_count', expense_type_count) order by total_amount desc, project_name)
    from (
      select project_name, sum(amount) total_amount, count(*) transaction_count, count(distinct expense_type) expense_type_count
      from bank_entries
      group by project_name
    ) p
  ), '[]'::jsonb),
  'expense_type_rows', coalesce((
    select jsonb_agg(jsonb_build_object('expense_type', expense_type, 'total_amount', total_amount::text, 'transaction_count', transaction_count, 'project_count', project_count) order by total_amount desc, expense_type)
    from (
      select expense_type, sum(amount) total_amount, count(*) transaction_count, count(distinct project_name) project_count
      from bank_entries
      group by expense_type
    ) e
  ), '[]'::jsonb)
) as payload
from serialized
left join lateral jsonb_array_elements(serialized.metadata -> 'blockers') blocker(value) on true
"#;

const COST_UPSERT_SQL: &str = r#"
insert into read_model.cost_statistics_read_models (
  scope_key, scope_type, scope_month, project_scope, schema_version, payload, summary,
  entry_count, source_scope_keys, source_versions, cache_status, generated_at, stale,
  stale_reason, rebuild_task_id, updated_at
) values (
  $1::text,
  case when $2::text = 'all' then 'all_time' else 'month' end,
  case when $2::text = 'all' then null else to_date($2::text || '-01', 'YYYY-MM-DD') end,
  $3::text,
  $8::text,
  $4::jsonb,
  coalesce($4::jsonb -> 'summary', '{}'::jsonb),
  coalesce(nullif($4::jsonb #>> '{summary,transaction_count}', '')::integer, jsonb_array_length(coalesce($4::jsonb -> 'time_rows', '[]'::jsonb))),
  $5::text[],
  $6::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  'ready',
  now(),
  false,
  null,
  $7::uuid,
  now()
)
on conflict (scope_key) do update set
  scope_type = excluded.scope_type,
  scope_month = excluded.scope_month,
  project_scope = excluded.project_scope,
  schema_version = excluded.schema_version,
  payload = excluded.payload,
  summary = excluded.summary,
  entry_count = excluded.entry_count,
  source_scope_keys = excluded.source_scope_keys,
  source_versions = excluded.source_versions,
  cache_status = 'ready',
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  rebuild_task_id = excluded.rebuild_task_id,
  updated_at = now()
"#;

const TAX_PAYLOAD_SQL: &str = r#"
with output_items as (
  select jsonb_build_object(
    'id', i.id::text,
    'buyer_name', coalesce(i.buyer_name, ''),
    'issue_date', coalesce(i.invoice_date::text, ''),
    'invoice_no', i.invoice_no,
    'invoice_code', i.invoice_code,
    'digital_invoice_no', i.digital_invoice_no,
    'tax_rate', coalesce(i.tax_rate::text, '—'),
    'tax_amount', coalesce(i.tax_amount, 0)::text,
    'total_with_tax', coalesce(i.total_with_tax, i.amount + coalesce(i.tax_amount, 0))::text,
    'invoice_type', '销项发票',
    'buyer_tax_no', i.buyer_tax_no,
    'seller_tax_no', i.seller_tax_no
  ) as item
  from app.invoices i
  where i.invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
    and i.invoice_type = 'output'
    and i.tax_amount is not null
),
input_items as (
  select jsonb_build_object(
    'id', i.id::text,
    'seller_name', coalesce(i.seller_name, ''),
    'seller_tax_no', i.seller_tax_no,
    'issue_date', coalesce(i.invoice_date::text, ''),
    'invoice_no', i.invoice_no,
    'invoice_code', i.invoice_code,
    'digital_invoice_no', i.digital_invoice_no,
    'tax_amount', coalesce(i.tax_amount, 0)::text,
    'total_with_tax', coalesce(i.total_with_tax, i.amount + coalesce(i.tax_amount, 0))::text,
    'risk_level', coalesce(i.risk_level, '待评估'),
    'invoice_type', '进项发票',
    'tax_rate', coalesce(i.tax_rate::text, '—'),
    'certified_status', case when c.id is null then '待认证' else '已认证' end,
    'is_locked_certified', c.id is not null
  ) as item
  from app.invoices i
  left join app.invoice_certifications c
    on c.invoice_month = i.invoice_month
   and c.invoice_id = i.id
   and c.status = 'certified'
  where i.invoice_month = to_date($1 || '-01', 'YYYY-MM-DD')
    and i.invoice_type = 'input'
    and i.tax_amount is not null
),
certified_items as (
  select jsonb_build_object(
    'id', c.id::text,
    'unique_key', c.source_unique_key,
    'digital_invoice_no', i.digital_invoice_no,
    'invoice_code', i.invoice_code,
    'invoice_no', i.invoice_no,
    'seller_tax_no', i.seller_tax_no,
    'seller_name', i.seller_name,
    'issue_date', i.invoice_date,
    'amount', c.certified_amount::text,
    'tax_amount', c.certified_tax_amount::text,
    'deductible_tax_amount', c.certified_tax_amount::text,
    'total_with_tax', (c.certified_amount + c.certified_tax_amount)::text,
    'status', '已认证',
    'selection_status', c.status,
    'invoice_status', i.status
  ) as item,
  i.id::text as input_id
  from app.invoice_certifications c
  join app.invoices i on i.invoice_month = c.invoice_month and i.id = c.invoice_id
  where c.certification_month = to_date($1 || '-01', 'YYYY-MM-DD')
    and c.status = 'certified'
)
select jsonb_build_object(
  'month', $1::text,
  'output_items', coalesce((select jsonb_agg(item order by item ->> 'issue_date') from output_items), '[]'::jsonb),
  'input_items', coalesce((select jsonb_agg(item order by item ->> 'issue_date') from input_items), '[]'::jsonb),
  'input_plan_items', coalesce((select jsonb_agg(item order by item ->> 'issue_date') from input_items), '[]'::jsonb),
  'certified_items', coalesce((select jsonb_agg(item order by item ->> 'issue_date') from certified_items), '[]'::jsonb),
  'certified_matched_rows', coalesce((select jsonb_agg(item || jsonb_build_object('matched_input_id', input_id, 'matched_invoice_no', item ->> 'invoice_no')) from certified_items), '[]'::jsonb),
  'certified_outside_plan_rows', '[]'::jsonb,
  'locked_certified_input_ids', coalesce((select jsonb_agg(input_id) from certified_items), '[]'::jsonb),
  'default_selected_output_ids', coalesce((select jsonb_agg(item ->> 'id') from output_items), '[]'::jsonb),
  'default_selected_input_ids', coalesce((select jsonb_agg(item ->> 'id') from input_items where (item ->> 'is_locked_certified')::boolean is not true), '[]'::jsonb),
  'summary', jsonb_build_object(
    'output_tax', coalesce((select sum((item ->> 'tax_amount')::numeric) from output_items), 0)::text,
    'certified_input_tax', coalesce((select sum((item ->> 'tax_amount')::numeric) from certified_items), 0)::text,
    'planned_input_tax', coalesce((select sum((item ->> 'tax_amount')::numeric) from input_items where (item ->> 'is_locked_certified')::boolean is not true), 0)::text,
    'blockers', '[]'::jsonb
  )
) as payload
"#;

const TAX_UPSERT_SQL: &str = r#"
insert into read_model.tax_offset_read_models (
  scope_key, scope_month, schema_version, payload, output_count, input_plan_count,
  certified_count, source_scope_keys, source_versions, cache_status, generated_at,
  stale, stale_reason, rebuild_task_id, updated_at
) values (
  $1::text,
  to_date($1::text || '-01', 'YYYY-MM-DD'),
  $6::text,
  $2::jsonb,
  jsonb_array_length($2::jsonb -> 'output_items'),
  jsonb_array_length($2::jsonb -> 'input_plan_items'),
  jsonb_array_length($2::jsonb -> 'certified_items'),
  $3::text[],
  $4::jsonb || jsonb_build_object('rules_version', 'read-model-rebuild-worker.v1'),
  'ready',
  now(),
  false,
  null,
  $5::uuid,
  now()
)
on conflict (scope_key) do update set
  scope_month = excluded.scope_month,
  schema_version = excluded.schema_version,
  payload = excluded.payload,
  output_count = excluded.output_count,
  input_plan_count = excluded.input_plan_count,
  certified_count = excluded.certified_count,
  source_scope_keys = excluded.source_scope_keys,
  source_versions = excluded.source_versions,
  cache_status = 'ready',
  generated_at = excluded.generated_at,
  stale = false,
  stale_reason = null,
  rebuild_task_id = excluded.rebuild_task_id,
  updated_at = now()
"#;

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn rebuild_payload_expands_requested_models_and_scope_keys() {
        let payload = RebuildRequest::from_payload(json!({
            "schema_version": "finops.read_model.rebuild_requested.v1",
            "models": ["workbench", "search_index", "cost_statistics", "tax_offset"],
            "scope_keys": ["workbench:2026-05", "active:2026-05", "all:2026-05", "2026-05"],
            "months": ["2026-05"],
            "scope_type": "month",
            "reason": "import.batch_confirmed",
            "source_versions": {"fact_updated_at": "2026-05-16T08:30:00Z"}
        }))
        .unwrap();

        assert_eq!(
            payload.targets,
            vec![
                RebuildTarget::new(
                    ReadModelKind::Workbench,
                    "workbench:2026-05",
                    Some("2026-05")
                ),
                RebuildTarget::new(
                    ReadModelKind::SearchIndex,
                    "search:2026-05",
                    Some("2026-05")
                ),
                RebuildTarget::new(
                    ReadModelKind::CostStatistics,
                    "active:2026-05",
                    Some("2026-05")
                ),
                RebuildTarget::new(
                    ReadModelKind::CostStatistics,
                    "all:2026-05",
                    Some("2026-05")
                ),
                RebuildTarget::new(ReadModelKind::TaxOffset, "2026-05", Some("2026-05")),
            ]
        );
    }

    #[test]
    fn rebuild_payload_rejects_missing_fact_watermark() {
        let error = RebuildRequest::from_payload(json!({
            "schema_version": "finops.read_model.rebuild_requested.v1",
            "models": ["workbench"],
            "months": ["2026-05"],
            "reason": "manual.invalidate",
            "source_versions": {}
        }))
        .unwrap_err();

        assert_eq!(error.code(), "READ_MODEL_SOURCE_VERSION_MISSING");
    }

    #[test]
    fn rebuild_payload_accepts_source_watermark_as_version_metadata() {
        let payload = RebuildRequest::from_payload(json!({
            "schema_version": "finops.read_model.rebuild_requested.v1",
            "models": ["search_index"],
            "months": ["2026-05"],
            "reason": "manual.invalidate",
            "source_watermark": {
                "fact_updated_at": "2026-05-16T08:30:00Z",
                "bank_transactions_max_updated_at": "2026-05-16T08:29:00Z"
            }
        }))
        .unwrap();

        assert_eq!(
            payload.source_versions,
            json!({
                "fact_updated_at": "2026-05-16T08:30:00Z",
                "bank_transactions_max_updated_at": "2026-05-16T08:29:00Z"
            })
        );
        assert_eq!(
            payload.targets,
            vec![RebuildTarget::new(
                ReadModelKind::SearchIndex,
                "search:2026-05",
                Some("2026-05")
            )]
        );
    }

    #[test]
    fn tax_payload_validation_requires_all_three_item_arrays() {
        let error = validate_tax_payload(&json!({
            "month": "2026-05",
            "output_items": [],
            "input_plan_items": []
        }))
        .unwrap_err();

        assert_eq!(error.code(), "READ_MODEL_TAX_PAYLOAD_INVALID");
    }

    #[test]
    fn cost_statistics_accepts_all_time_scope_keys() {
        let payload = RebuildRequest::from_payload(json!({
            "schema_version": "finops.read_model.rebuild_requested.v1",
            "models": ["cost_statistics"],
            "scope_keys": ["active:all", "all:all"],
            "months": [],
            "scope_type": "all_time",
            "reason": "manual.invalidate",
            "source_versions": {"fact_updated_at": "2026-05-16T08:30:00Z"}
        }))
        .unwrap();

        assert_eq!(
            payload.targets,
            vec![
                RebuildTarget::new(ReadModelKind::CostStatistics, "active:all", Some("all")),
                RebuildTarget::new(ReadModelKind::CostStatistics, "all:all", Some("all")),
            ]
        );
    }
}
