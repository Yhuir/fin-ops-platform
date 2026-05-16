use crate::repositories::task_status::{
    TaskAttemptStatusRow, TaskStatusRepository, TaskStatusRepositoryError, TaskStatusRow,
};

#[derive(Debug, thiserror::Error)]
pub enum TaskStatusServiceError {
    #[error("task not found")]
    NotFound,
    #[error(transparent)]
    Repository(#[from] TaskStatusRepositoryError),
}

pub struct TaskStatusService<R> {
    repository: R,
}

impl<R> TaskStatusService<R>
where
    R: TaskStatusRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn get_task_status(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<TaskStatusResponse, TaskStatusServiceError> {
        let Some(task) = self.repository.find_task(task_id).await? else {
            return Err(TaskStatusServiceError::NotFound);
        };
        let attempts = self.repository.list_attempts(task_id).await?;

        Ok(TaskStatusResponse {
            task: TaskStatusDto::from_row(task),
            attempts: attempts
                .into_iter()
                .map(TaskAttemptStatusDto::from_row)
                .collect(),
        })
    }

    pub async fn get_data_reset_job(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<DataResetJobResponse, TaskStatusServiceError> {
        let Some(task) = self.repository.find_task(task_id).await? else {
            return Err(TaskStatusServiceError::NotFound);
        };
        if task.task_type != "settings_data_reset" {
            return Err(TaskStatusServiceError::NotFound);
        }
        Ok(DataResetJobResponse {
            job: Some(DataResetJobDto::from_row(task)),
        })
    }

    pub async fn get_active_data_reset_job(
        &self,
    ) -> Result<DataResetJobResponse, TaskStatusServiceError> {
        Ok(DataResetJobResponse {
            job: self
                .repository
                .find_active_data_reset_task()
                .await?
                .map(DataResetJobDto::from_row),
        })
    }

    pub async fn get_background_job(
        &self,
        task_id: uuid::Uuid,
    ) -> Result<BackgroundJobResponse, TaskStatusServiceError> {
        let Some(task) = self.repository.find_task(task_id).await? else {
            return Err(TaskStatusServiceError::NotFound);
        };
        if task.visibility != "system" {
            return Err(TaskStatusServiceError::NotFound);
        }
        Ok(BackgroundJobResponse {
            job: BackgroundJobDto::from_row(task),
        })
    }

    pub async fn get_active_background_jobs(
        &self,
    ) -> Result<BackgroundJobsActiveResponse, TaskStatusServiceError> {
        let rows = self.repository.list_active_background_tasks().await?;
        let mut active_jobs = Vec::new();
        let mut attention_jobs = Vec::new();

        for row in rows {
            let job = BackgroundJobDto::from_row(row);
            if job.attention {
                attention_jobs.push(job);
            } else if is_legacy_active_background_status(&job.status) {
                active_jobs.push(job);
            }
        }

        let mut jobs = active_jobs.clone();
        let mut seen_job_ids: std::collections::HashSet<String> =
            jobs.iter().map(|job| job.job_id.clone()).collect();
        for job in &attention_jobs {
            if seen_job_ids.insert(job.job_id.clone()) {
                jobs.push(job.clone());
            }
        }

        Ok(BackgroundJobsActiveResponse {
            jobs,
            active_jobs,
            attention_jobs,
        })
    }
}

#[derive(Debug, serde::Serialize)]
pub struct TaskStatusResponse {
    pub task: TaskStatusDto,
    pub attempts: Vec<TaskAttemptStatusDto>,
}

#[derive(Debug, serde::Serialize)]
pub struct DataResetJobResponse {
    pub job: Option<DataResetJobDto>,
}

#[derive(Debug, serde::Serialize)]
pub struct BackgroundJobsActiveResponse {
    pub jobs: Vec<BackgroundJobDto>,
    pub active_jobs: Vec<BackgroundJobDto>,
    pub attention_jobs: Vec<BackgroundJobDto>,
}

#[derive(Debug, serde::Serialize)]
pub struct BackgroundJobResponse {
    pub job: BackgroundJobDto,
}

#[derive(Clone, Debug, serde::Serialize)]
pub struct BackgroundJobDto {
    pub job_id: String,
    #[serde(rename = "type")]
    pub task_type: String,
    pub label: String,
    pub short_label: String,
    pub owner_user_id: Option<String>,
    pub visibility: String,
    pub status: String,
    pub phase: String,
    pub current: i32,
    pub total: i32,
    pub percent: i32,
    pub message: String,
    pub result_summary: serde_json::Value,
    pub error: Option<String>,
    pub idempotency_key: Option<String>,
    pub source: serde_json::Value,
    pub affected_scopes: Vec<String>,
    pub affected_months: Vec<String>,
    pub retryable: bool,
    pub acknowledgeable: bool,
    pub attention: bool,
    pub superseded_by_job_id: Option<String>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub updated_at: String,
    pub finished_at: Option<String>,
    pub acknowledged_at: Option<String>,
    pub superseded_at: Option<String>,
}

impl BackgroundJobDto {
    fn from_row(row: TaskStatusRow) -> Self {
        let status = legacy_background_status(&row.status, &row.result_summary);
        let result_summary = sanitize_json(row.result_summary.clone());
        let source = sanitize_json(row.source.clone());
        let error = row.error_summary.clone();
        let retryable =
            row.retryable || legacy_retryable(&row.task_type, &result_summary, &source, &row);
        let acknowledgeable = is_legacy_attention_background_status(&status);
        Self {
            job_id: row.task_id,
            task_type: row.task_type.clone(),
            label: row.label.clone(),
            short_label: legacy_background_short_label(
                &status,
                &row.label,
                row.current_count,
                row.total_count,
            ),
            owner_user_id: row.owner_user_id,
            visibility: row.visibility,
            status: status.clone(),
            phase: legacy_background_phase(&status, &row.phase),
            current: row.current_count,
            total: row.total_count,
            percent: row.percent,
            message: json_text(&result_summary, "message")
                .or_else(|| error.clone())
                .unwrap_or_else(|| public_task_message(&row.status, error.as_deref())),
            result_summary,
            error,
            idempotency_key: row.idempotency_key,
            source,
            affected_scopes: row.affected_scopes,
            affected_months: row.affected_months,
            retryable,
            acknowledgeable,
            attention: acknowledgeable,
            superseded_by_job_id: None,
            created_at: row.created_at,
            started_at: row.started_at,
            updated_at: row.updated_at,
            finished_at: row.finished_at,
            acknowledged_at: None,
            superseded_at: None,
        }
    }
}

#[derive(Debug, serde::Serialize)]
pub struct DataResetJobDto {
    pub job_id: String,
    pub action: String,
    pub status: String,
    pub phase: String,
    pub message: String,
    pub current: i32,
    pub total: i32,
    pub percent: i32,
    pub created_at: String,
    pub updated_at: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
}

impl DataResetJobDto {
    fn from_row(row: TaskStatusRow) -> Self {
        let legacy_status = data_reset_legacy_status(&row.status);
        let action = json_text(&row.source, "action")
            .or_else(|| json_text(&row.result_summary, "action"))
            .unwrap_or_default();
        let result =
            data_reset_result_payload(&row.result_summary, &action, &legacy_status, &row.task_id);
        Self {
            job_id: row.task_id,
            action,
            status: legacy_status,
            phase: row.phase,
            message: json_text(&row.result_summary, "message")
                .or_else(|| row.error_summary.clone())
                .unwrap_or_else(|| public_task_message(&row.status, None)),
            current: row.current_count,
            total: row.total_count,
            percent: row.percent,
            created_at: row.created_at,
            updated_at: row.updated_at,
            error: row.error_summary,
            result,
        }
    }
}

#[derive(Debug, serde::Serialize)]
pub struct TaskStatusDto {
    pub task_id: String,
    #[serde(rename = "type")]
    pub task_type: String,
    pub label: String,
    pub short_label: String,
    pub owner_user_id: Option<String>,
    pub visibility: String,
    pub status: String,
    pub phase: String,
    pub current: i32,
    pub total: i32,
    pub percent: i32,
    pub message: String,
    pub result_summary: serde_json::Value,
    pub error_code: Option<String>,
    pub error_summary: Option<String>,
    pub retryable: bool,
    pub attempt_count: i32,
    pub max_attempts: i32,
    pub next_attempt_at: Option<String>,
    pub source: serde_json::Value,
    pub affected_scopes: Vec<String>,
    pub affected_months: Vec<String>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub updated_at: String,
    pub finished_at: Option<String>,
    pub cancelled_at: Option<String>,
}

impl TaskStatusDto {
    fn from_row(row: TaskStatusRow) -> Self {
        let message = public_task_message(&row.status, row.error_summary.as_deref());
        let short_label = short_label(&row.status, &row.label, row.current_count, row.total_count);
        Self {
            task_id: row.task_id,
            task_type: row.task_type,
            label: row.label,
            short_label,
            owner_user_id: row.owner_user_id,
            visibility: row.visibility,
            status: row.status,
            phase: row.phase,
            current: row.current_count,
            total: row.total_count,
            percent: row.percent,
            message,
            result_summary: sanitize_json(row.result_summary),
            error_code: row.error_code,
            error_summary: row.error_summary,
            retryable: row.retryable,
            attempt_count: row.attempt_count,
            max_attempts: row.max_attempts,
            next_attempt_at: row.next_attempt_at,
            source: sanitize_json(row.source),
            affected_scopes: row.affected_scopes,
            affected_months: row.affected_months,
            created_at: row.created_at,
            started_at: row.started_at,
            updated_at: row.updated_at,
            finished_at: row.finished_at,
            cancelled_at: row.cancelled_at,
        }
    }
}

#[derive(Debug, serde::Serialize)]
pub struct TaskAttemptStatusDto {
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

impl TaskAttemptStatusDto {
    fn from_row(row: TaskAttemptStatusRow) -> Self {
        Self {
            attempt_id: row.attempt_id,
            attempt_no: row.attempt_no,
            worker_id: row.worker_id,
            nats_stream: row.nats_stream,
            nats_consumer: row.nats_consumer,
            nats_sequence: row.nats_sequence,
            started_at: row.started_at,
            heartbeat_at: row.heartbeat_at,
            finished_at: row.finished_at,
            duration_ms: row.duration_ms,
            status: row.status,
            error_code: row.error_code,
            error_summary: row.error_summary,
        }
    }
}

fn public_task_message(status: &str, error_summary: Option<&str>) -> String {
    match status {
        "queued" => "后台任务已排队。".to_owned(),
        "running" => "后台任务正在执行。".to_owned(),
        "succeeded" => "后台任务已完成。".to_owned(),
        "retrying" => "后台任务失败，等待重试。".to_owned(),
        "failed" => error_summary.unwrap_or("后台任务失败。").to_owned(),
        "dead_lettered" => error_summary
            .unwrap_or("后台任务已进入人工处理队列。")
            .to_owned(),
        "cancelled" => "后台任务已取消。".to_owned(),
        _ => "后台任务状态未知。".to_owned(),
    }
}

fn data_reset_legacy_status(status: &str) -> String {
    match status {
        "succeeded" => "completed",
        "dead_lettered" => "failed",
        "cancelled" => "cancelled",
        other => other,
    }
    .to_owned()
}

fn data_reset_result_payload(
    result_summary: &serde_json::Value,
    action: &str,
    legacy_status: &str,
    job_id: &str,
) -> Option<serde_json::Value> {
    let serde_json::Value::Object(source) = result_summary else {
        return None;
    };
    if source.is_empty() {
        return None;
    }
    if !(source.contains_key("cleared_collections")
        || source.contains_key("deleted_counts")
        || legacy_status == "completed")
    {
        return None;
    }
    let mut result = source.clone();
    result
        .entry("action".to_owned())
        .or_insert_with(|| serde_json::Value::String(action.to_owned()));
    result
        .entry("status".to_owned())
        .or_insert_with(|| serde_json::Value::String(legacy_status.to_owned()));
    result
        .entry("job_id".to_owned())
        .or_insert_with(|| serde_json::Value::String(job_id.to_owned()));
    Some(sanitize_json(serde_json::Value::Object(result)))
}

fn json_text(value: &serde_json::Value, key: &str) -> Option<String> {
    value
        .get(key)
        .and_then(serde_json::Value::as_str)
        .map(str::to_owned)
        .filter(|value| !value.trim().is_empty())
}

fn short_label(status: &str, label: &str, current: i32, total: i32) -> String {
    let progress = if total > 0 {
        format!(" {}/{}", current, total)
    } else {
        String::new()
    };
    match status {
        "queued" | "running" | "retrying" => format!("正在{}{}", label, progress),
        "succeeded" => format!("{}完成{}", label, progress),
        "failed" => format!("{}失败", label),
        "dead_lettered" => format!("{}待人工处理", label),
        "cancelled" => format!("{}已取消", label),
        _ => label.to_owned(),
    }
}

fn legacy_background_status(status: &str, result_summary: &serde_json::Value) -> String {
    if status == "succeeded" && json_bool(result_summary, "partial_success") {
        return "partial_success".to_owned();
    }
    match status {
        "retrying" => "queued",
        "dead_lettered" => "failed",
        other => other,
    }
    .to_owned()
}

fn legacy_background_phase(status: &str, phase: &str) -> String {
    if status == "partial_success" {
        return "partial_success".to_owned();
    }
    phase.to_owned()
}

fn legacy_background_short_label(status: &str, label: &str, current: i32, total: i32) -> String {
    let label = if label.trim().is_empty() {
        "后台任务"
    } else {
        label.trim()
    };
    let progress = if total > 0 {
        format!(" {}/{}", current, total)
    } else {
        String::new()
    };
    match status {
        "queued" | "running" => format!("正在{}{}", label, progress),
        "succeeded" => format!("{}完成{}", label, progress),
        "partial_success" => format!("{}部分完成{}", label, progress),
        "failed" => format!("{}失败", label),
        "superseded" => format!("{}已被新任务替代", label),
        _ => label.to_owned(),
    }
}

fn is_legacy_active_background_status(status: &str) -> bool {
    matches!(status, "queued" | "running" | "succeeded")
}

fn is_legacy_attention_background_status(status: &str) -> bool {
    matches!(status, "failed" | "partial_success")
}

fn legacy_retryable(
    task_type: &str,
    result_summary: &serde_json::Value,
    source: &serde_json::Value,
    row: &TaskStatusRow,
) -> bool {
    match task_type {
        "file_import" => {
            json_has_value(source, "session_id") && json_has_values(source, "selected_file_ids")
        }
        "workbench_matching" => {
            !row.affected_months.is_empty()
                || json_has_values(source, "affected_months")
                || json_has_values(source, "months")
                || json_has_values(source, "scope_months")
                || json_has_value(source, "scope_month")
        }
        "cost_statistics_cache_warmup" => {
            json_has_values(result_summary, "failed_scope_keys")
                || json_has_values(result_summary, "remaining_scope_keys")
                || json_has_values(result_summary, "target_scope_keys")
                || !row.affected_months.is_empty()
                || !row.affected_scopes.is_empty()
                || json_has_values(source, "affected_months")
                || json_has_values(source, "months")
                || json_has_value(source, "month")
                || json_has_values(source, "target_scope_keys")
        }
        _ => false,
    }
}

fn json_bool(value: &serde_json::Value, key: &str) -> bool {
    match value.get(key) {
        Some(serde_json::Value::Bool(value)) => *value,
        Some(serde_json::Value::String(value)) => {
            matches!(
                value.trim().to_ascii_lowercase().as_str(),
                "true" | "1" | "yes"
            )
        }
        Some(serde_json::Value::Number(value)) => value.as_i64() == Some(1),
        _ => false,
    }
}

fn json_has_value(value: &serde_json::Value, key: &str) -> bool {
    value.get(key).is_some_and(|value| match value {
        serde_json::Value::Null => false,
        serde_json::Value::String(value) => !value.trim().is_empty(),
        serde_json::Value::Array(values) => values.iter().any(json_value_present),
        other => json_value_present(other),
    })
}

fn json_has_values(value: &serde_json::Value, key: &str) -> bool {
    value.get(key).is_some_and(|value| match value {
        serde_json::Value::Array(values) => values.iter().any(json_value_present),
        other => json_value_present(other),
    })
}

fn json_value_present(value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::Null => false,
        serde_json::Value::String(value) => !value.trim().is_empty(),
        serde_json::Value::Array(values) => values.iter().any(json_value_present),
        serde_json::Value::Object(values) => !values.is_empty(),
        serde_json::Value::Bool(value) => *value,
        serde_json::Value::Number(_) => true,
    }
}

fn sanitize_json(value: serde_json::Value) -> serde_json::Value {
    match value {
        serde_json::Value::Object(map) => {
            let sanitized = map
                .into_iter()
                .filter_map(|(key, value)| {
                    if is_sensitive_key(&key) {
                        None
                    } else {
                        Some((key, sanitize_json(value)))
                    }
                })
                .collect();
            serde_json::Value::Object(sanitized)
        }
        serde_json::Value::Array(values) => {
            serde_json::Value::Array(values.into_iter().map(sanitize_json).collect())
        }
        other => other,
    }
}

fn is_sensitive_key(key: &str) -> bool {
    let lowered = key.to_ascii_lowercase();
    [
        "password",
        "token",
        "secret",
        "credential",
        "raw_file",
        "raw_content",
        "stack",
        "traceback",
    ]
    .iter()
    .any(|part| lowered.contains(part))
}

#[cfg(test)]
mod tests {
    use super::*;
    use async_trait::async_trait;
    use serde_json::json;

    struct FixtureTaskStatusRepository {
        task: Option<TaskStatusRow>,
        active_data_reset_task: Option<TaskStatusRow>,
        active_background_tasks: Vec<TaskStatusRow>,
        attempts: Vec<TaskAttemptStatusRow>,
    }

    #[async_trait]
    impl TaskStatusRepository for FixtureTaskStatusRepository {
        async fn find_task(
            &self,
            _task_id: uuid::Uuid,
        ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError> {
            Ok(self.task.clone())
        }

        async fn list_attempts(
            &self,
            _task_id: uuid::Uuid,
        ) -> Result<Vec<TaskAttemptStatusRow>, TaskStatusRepositoryError> {
            Ok(self.attempts.clone())
        }

        async fn find_active_data_reset_task(
            &self,
        ) -> Result<Option<TaskStatusRow>, TaskStatusRepositoryError> {
            Ok(self.active_data_reset_task.clone())
        }

        async fn list_active_background_tasks(
            &self,
        ) -> Result<Vec<TaskStatusRow>, TaskStatusRepositoryError> {
            Ok(self.active_background_tasks.clone())
        }
    }

    #[tokio::test]
    async fn task_status_response_keeps_frontend_fields_and_sanitizes_json() {
        let task_id = uuid::Uuid::parse_str("22222222-2222-4222-8222-222222222222").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: Some(TaskStatusRow {
                task_id: task_id.to_string(),
                task_type: "read_model.rebuild".to_owned(),
                label: "重建工作台".to_owned(),
                owner_user_id: Some("33333333-3333-4333-8333-333333333333".to_owned()),
                visibility: "owner".to_owned(),
                status: "running".to_owned(),
                phase: "rebuilding".to_owned(),
                source: json!({"session_id": "session-1", "access_token": "hidden"}),
                result_summary: json!({"rebuilt": 3, "stack": "internal stack"}),
                affected_scopes: vec!["workbench:2026-05".to_owned()],
                affected_months: vec!["2026-05-01".to_owned()],
                current_count: 3,
                total_count: 10,
                percent: 30,
                error_code: Some("INTERNAL_ERROR".to_owned()),
                error_summary: Some("可展示错误".to_owned()),
                idempotency_key: Some("worker:read_model.rebuild:test".to_owned()),
                retryable: true,
                attempt_count: 1,
                max_attempts: 5,
                next_attempt_at: None,
                created_at: "2026-05-16T10:00:00Z".to_owned(),
                started_at: Some("2026-05-16T10:01:00Z".to_owned()),
                updated_at: "2026-05-16T10:02:00Z".to_owned(),
                finished_at: None,
                cancelled_at: None,
            }),
            active_data_reset_task: None,
            active_background_tasks: vec![],
            attempts: vec![TaskAttemptStatusRow {
                attempt_id: "44444444-4444-4444-8444-444444444444".to_owned(),
                attempt_no: 1,
                worker_id: "worker-1".to_owned(),
                nats_stream: Some("FINOPS_JOBS".to_owned()),
                nats_consumer: Some("read-model-workers".to_owned()),
                nats_sequence: Some(42),
                started_at: "2026-05-16T10:01:00Z".to_owned(),
                heartbeat_at: Some("2026-05-16T10:02:00Z".to_owned()),
                finished_at: None,
                duration_ms: None,
                status: "running".to_owned(),
                error_code: None,
                error_summary: None,
            }],
        });

        let response = service.get_task_status(task_id).await.unwrap();
        let payload = serde_json::to_value(response).unwrap();

        assert_eq!(payload["task"]["task_id"], task_id.to_string());
        assert_eq!(payload["task"]["type"], "read_model.rebuild");
        assert_eq!(payload["task"]["short_label"], "正在重建工作台 3/10");
        assert_eq!(payload["task"]["current"], 3);
        assert_eq!(payload["task"]["total"], 10);
        assert_eq!(payload["task"]["message"], "后台任务正在执行。");
        assert_eq!(
            payload["task"]["source"],
            json!({"session_id": "session-1"})
        );
        assert_eq!(payload["task"]["result_summary"], json!({"rebuilt": 3}));
        assert!(payload["attempts"][0].get("error_detail").is_none());
    }

    #[tokio::test]
    async fn missing_task_returns_not_found() {
        let task_id = uuid::Uuid::parse_str("22222222-2222-4222-8222-222222222222").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: None,
            active_data_reset_task: None,
            active_background_tasks: vec![],
            attempts: vec![],
        });

        let error = service.get_task_status(task_id).await.unwrap_err();

        assert!(matches!(error, TaskStatusServiceError::NotFound));
    }

    #[tokio::test]
    async fn data_reset_job_response_matches_legacy_settings_poll_shape() {
        let task_id = uuid::Uuid::parse_str("55555555-5555-4555-8555-555555555555").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: Some(data_reset_task(
                task_id,
                "succeeded",
                json!({
                    "action": "reset_invoices",
                    "status": "success",
                    "cleared_collections": ["invoices"],
                    "deleted_counts": {"invoices": 12},
                    "protected_targets": ["settings"],
                    "rebuild_status": "completed",
                    "message": "发票数据已重置。"
                }),
            )),
            active_data_reset_task: None,
            active_background_tasks: vec![],
            attempts: vec![],
        });

        let response = service.get_data_reset_job(task_id).await.unwrap();
        let payload = serde_json::to_value(response).unwrap();

        assert_eq!(payload["job"]["job_id"], task_id.to_string());
        assert_eq!(payload["job"]["action"], "reset_invoices");
        assert_eq!(payload["job"]["status"], "completed");
        assert_eq!(payload["job"]["phase"], "complete");
        assert_eq!(payload["job"]["current"], 100);
        assert_eq!(payload["job"]["total"], 100);
        assert_eq!(payload["job"]["percent"], 100);
        assert_eq!(payload["job"]["result"]["job_id"], task_id.to_string());
        assert_eq!(payload["job"]["result"]["status"], "success");
        assert_eq!(payload["job"]["result"]["deleted_counts"]["invoices"], 12);
    }

    #[tokio::test]
    async fn active_data_reset_job_returns_nullable_legacy_job_wrapper() {
        let active_task_id = uuid::Uuid::parse_str("66666666-6666-4666-8666-666666666666").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: None,
            active_data_reset_task: Some(data_reset_task(
                active_task_id,
                "running",
                json!({"action": "reset_oa_and_rebuild"}),
            )),
            active_background_tasks: vec![],
            attempts: vec![],
        });

        let response = service.get_active_data_reset_job().await.unwrap();
        let payload = serde_json::to_value(response).unwrap();

        assert_eq!(payload["job"]["job_id"], active_task_id.to_string());
        assert_eq!(payload["job"]["action"], "reset_oa_and_rebuild");
        assert_eq!(payload["job"]["status"], "running");

        let empty = TaskStatusService::new(FixtureTaskStatusRepository {
            task: None,
            active_data_reset_task: None,
            active_background_tasks: vec![],
            attempts: vec![],
        })
        .get_active_data_reset_job()
        .await
        .unwrap();
        assert!(serde_json::to_value(empty).unwrap()["job"].is_null());
    }

    #[tokio::test]
    async fn active_background_jobs_response_matches_legacy_list_shape() {
        let running_task_id =
            uuid::Uuid::parse_str("77777777-7777-4777-8777-777777777777").unwrap();
        let failed_task_id = uuid::Uuid::parse_str("88888888-8888-4888-8888-888888888888").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: None,
            active_data_reset_task: None,
            active_background_tasks: vec![
                background_task(
                    running_task_id,
                    "etc_invoice_import",
                    "导入 ETC发票",
                    "running",
                    1,
                    2,
                    json!({}),
                    None,
                ),
                background_task(
                    failed_task_id,
                    "cost_statistics_cache_warmup",
                    "预热成本统计缓存",
                    "dead_lettered",
                    0,
                    0,
                    json!({"target_scope_keys": ["cost_statistics:2026-03"]}),
                    Some("服务重启，任务已中断，请重新执行。"),
                ),
            ],
            attempts: vec![],
        });

        let response = service
            .get_active_background_jobs()
            .await
            .expect("active background jobs should serialize");
        let payload = serde_json::to_value(response).unwrap();

        assert_eq!(payload["jobs"][0]["job_id"], running_task_id.to_string());
        assert_eq!(payload["jobs"][0]["type"], "etc_invoice_import");
        assert_eq!(payload["jobs"][0]["short_label"], "正在导入 ETC发票 1/2");
        assert_eq!(payload["jobs"][0]["message"], "后台任务正在执行。");
        assert_eq!(payload["jobs"][0]["retryable"], false);
        assert_eq!(payload["jobs"][0]["acknowledgeable"], false);
        assert_eq!(payload["jobs"][0]["attention"], false);
        assert_eq!(
            payload["active_jobs"][0]["job_id"],
            running_task_id.to_string()
        );
        assert_eq!(
            payload["attention_jobs"][0]["job_id"],
            failed_task_id.to_string()
        );
        assert_eq!(payload["attention_jobs"][0]["status"], "failed");
        assert_eq!(payload["attention_jobs"][0]["acknowledgeable"], true);
        assert_eq!(payload["attention_jobs"][0]["attention"], true);
    }

    #[tokio::test]
    async fn background_job_detail_returns_legacy_job_wrapper() {
        let task_id = uuid::Uuid::parse_str("99999999-9999-4999-8999-999999999999").unwrap();
        let service = TaskStatusService::new(FixtureTaskStatusRepository {
            task: Some(background_task(
                task_id,
                "workbench_matching",
                "自动匹配工作台",
                "retrying",
                0,
                0,
                json!({"message": "等待重试。"}),
                Some("临时依赖失败。"),
            )),
            active_data_reset_task: None,
            active_background_tasks: vec![],
            attempts: vec![],
        });

        let response = service.get_background_job(task_id).await.unwrap();
        let payload = serde_json::to_value(response).unwrap();

        assert_eq!(payload["job"]["job_id"], task_id.to_string());
        assert_eq!(payload["job"]["type"], "workbench_matching");
        assert_eq!(payload["job"]["status"], "queued");
        assert_eq!(payload["job"]["short_label"], "正在自动匹配工作台");
        assert_eq!(payload["job"]["message"], "等待重试。");
    }

    fn data_reset_task(
        task_id: uuid::Uuid,
        status: &str,
        result_summary: serde_json::Value,
    ) -> TaskStatusRow {
        let action = result_summary
            .get("action")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("reset_invoices")
            .to_owned();
        TaskStatusRow {
            task_id: task_id.to_string(),
            task_type: "settings_data_reset".to_owned(),
            label: "重置发票数据".to_owned(),
            owner_user_id: None,
            visibility: "system".to_owned(),
            status: status.to_owned(),
            phase: if status == "succeeded" {
                "complete"
            } else {
                "rebuild"
            }
            .to_owned(),
            source: json!({"action": action}),
            result_summary,
            affected_scopes: vec!["settings".to_owned(), "workbench".to_owned()],
            affected_months: vec![],
            current_count: if status == "succeeded" { 100 } else { 42 },
            total_count: 100,
            percent: if status == "succeeded" { 100 } else { 42 },
            error_code: None,
            error_summary: None,
            idempotency_key: Some(format!("settings_data_reset:{action}")),
            retryable: false,
            attempt_count: 1,
            max_attempts: 1,
            next_attempt_at: None,
            created_at: "2026-05-16T10:00:00Z".to_owned(),
            started_at: Some("2026-05-16T10:01:00Z".to_owned()),
            updated_at: "2026-05-16T10:02:00Z".to_owned(),
            finished_at: if status == "succeeded" {
                Some("2026-05-16T10:03:00Z".to_owned())
            } else {
                None
            },
            cancelled_at: None,
        }
    }

    fn background_task(
        task_id: uuid::Uuid,
        task_type: &str,
        label: &str,
        status: &str,
        current: i32,
        total: i32,
        result_summary: serde_json::Value,
        error_summary: Option<&str>,
    ) -> TaskStatusRow {
        TaskStatusRow {
            task_id: task_id.to_string(),
            task_type: task_type.to_owned(),
            label: label.to_owned(),
            owner_user_id: None,
            visibility: "system".to_owned(),
            status: status.to_owned(),
            phase: status.to_owned(),
            source: json!({"reason": "shadow_validation_fixture"}),
            result_summary,
            affected_scopes: vec![],
            affected_months: vec![],
            current_count: current,
            total_count: total,
            percent: if total > 0 {
                ((current as f64 / total as f64) * 100.0) as i32
            } else {
                0
            },
            error_code: error_summary.map(|_| "interrupted_by_restart".to_owned()),
            error_summary: error_summary.map(str::to_owned),
            idempotency_key: Some(format!("worker:{task_type}:{task_id}")),
            retryable: false,
            attempt_count: 1,
            max_attempts: 3,
            next_attempt_at: None,
            created_at: "2026-05-16T10:00:00Z".to_owned(),
            started_at: Some("2026-05-16T10:01:00Z".to_owned()),
            updated_at: "2026-05-16T10:02:00Z".to_owned(),
            finished_at: if matches!(status, "failed" | "dead_lettered" | "succeeded") {
                Some("2026-05-16T10:03:00Z".to_owned())
            } else {
                None
            },
            cancelled_at: None,
        }
    }
}
