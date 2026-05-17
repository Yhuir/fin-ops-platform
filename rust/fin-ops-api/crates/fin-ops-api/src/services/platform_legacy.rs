use std::hash::{Hash, Hasher};

use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

use crate::services::workbench_writes::WriteActor;

#[derive(Debug, thiserror::Error)]
pub enum PlatformLegacyServiceError {
    #[error("invalid request: {message}")]
    InvalidRequest { code: &'static str, message: String },
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
    #[error(transparent)]
    Repository(#[from] PlatformLegacyRepositoryError),
}

#[derive(Debug, thiserror::Error)]
pub enum PlatformLegacyRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
    #[error("idempotency key was reused with a different payload")]
    IdempotencyConflict,
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
}

#[async_trait]
pub trait PlatformLegacyRepository: Send + Sync {
    async fn create_job_command(
        &self,
        command: PlatformJobCommand,
    ) -> Result<PlatformJobCommandResult, PlatformLegacyRepositoryError>;

    async fn find_import_session(
        &self,
        session_id: &str,
    ) -> Result<Option<ImportSessionProjection>, PlatformLegacyRepositoryError>;

    async fn list_matching_results(
        &self,
        request: MatchingResultsRequest,
    ) -> Result<Vec<MatchingResultRow>, PlatformLegacyRepositoryError>;

    async fn find_matching_result(
        &self,
        result_id: Uuid,
    ) -> Result<Option<MatchingResultRow>, PlatformLegacyRepositoryError>;
}

pub struct PlatformLegacyService<R> {
    repository: R,
}

impl<R> PlatformLegacyService<R>
where
    R: PlatformLegacyRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn retry_background_job(
        &self,
        job_id: Uuid,
        request: RetryBackgroundJobRequest,
        actor: WriteActor,
    ) -> Result<PlatformJobCommandResponse, PlatformLegacyServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let reason = required_text(&request.reason, "missing_reason")?;
        let command = PlatformJobCommand {
            operation: "background_job.retry".to_owned(),
            task_type: "background_job.retry".to_owned(),
            subject: "finops.jobs.worker_task.retry".to_owned(),
            aggregate_type: "worker_task".to_owned(),
            aggregate_id: job_id,
            idempotency_key,
            actor,
            label: "重试后台任务".to_owned(),
            source: serde_json::json!({
                "job_id": job_id,
                "reason": reason,
                "replay_mode": request.replay_mode.unwrap_or_else(|| "same_task_type".to_owned())
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.background_job_retry.v1",
                "job_id": job_id,
                "reason": reason
            }),
            affected_scopes: Vec::new(),
            affected_months: Vec::new(),
            request_payload: serde_json::json!({
                "job_id": job_id,
                "reason": reason
            }),
        };
        Ok(self.repository.create_job_command(command).await?.into())
    }

    pub async fn retry_import_file(
        &self,
        file_id: Uuid,
        request: RetryImportFileRequest,
        actor: WriteActor,
    ) -> Result<PlatformJobCommandResponse, PlatformLegacyServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let reason = required_text(&request.reason, "missing_reason")?;
        let command = PlatformJobCommand {
            operation: "import_file.retry".to_owned(),
            task_type: "import.parse".to_owned(),
            subject: "finops.jobs.import.parse".to_owned(),
            aggregate_type: "import_file".to_owned(),
            aggregate_id: file_id,
            idempotency_key,
            actor,
            label: "重试导入文件解析".to_owned(),
            source: serde_json::json!({
                "file_id": file_id,
                "reason": reason
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.import_file_retry.v1",
                "file_id": file_id,
                "reason": reason
            }),
            affected_scopes: Vec::new(),
            affected_months: Vec::new(),
            request_payload: serde_json::json!({
                "file_id": file_id,
                "reason": reason
            }),
        };
        Ok(self.repository.create_job_command(command).await?.into())
    }

    pub async fn request_matching_run(
        &self,
        request: MatchingRunRequest,
        actor: WriteActor,
    ) -> Result<PlatformJobCommandResponse, PlatformLegacyServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let scope_month = normalize_month(&request.scope_month)?;
        let reason = request
            .reason
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "manual_rebuild".to_owned());
        let scope_key = format!("workbench:{scope_month}");
        let command = PlatformJobCommand {
            operation: "matching.run".to_owned(),
            task_type: "workbench_matching".to_owned(),
            subject: "finops.jobs.workbench.matching".to_owned(),
            aggregate_type: "matching_scope".to_owned(),
            aggregate_id: deterministic_scope_uuid(&scope_key),
            idempotency_key,
            actor,
            label: "重建工作台候选匹配".to_owned(),
            source: serde_json::json!({
                "scope_month": scope_month,
                "reason": reason
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.matching_run.v1",
                "scope_month": scope_month,
                "reason": reason
            }),
            affected_scopes: vec![scope_key],
            affected_months: vec![format!("{scope_month}-01")],
            request_payload: serde_json::json!({
                "scope_month": scope_month,
                "reason": reason
            }),
        };
        Ok(self.repository.create_job_command(command).await?.into())
    }

    pub async fn get_import_session(
        &self,
        session_id: &str,
    ) -> Result<ImportSessionResponse, PlatformLegacyServiceError> {
        let session_id = session_id.trim();
        if session_id.is_empty() {
            return Err(invalid_request("missing_session_id", "session_id is required"));
        }
        let Some(session) = self.repository.find_import_session(session_id).await? else {
            return Err(PlatformLegacyServiceError::NotFound {
                resource: "import_session",
            });
        };
        Ok(ImportSessionResponse { session })
    }

    pub async fn list_matching_results(
        &self,
        request: MatchingResultsRequest,
    ) -> Result<MatchingResultsResponse, PlatformLegacyServiceError> {
        if let Some(month) = request.scope_month.as_deref() {
            normalize_month(month)?;
        }
        let results = self.repository.list_matching_results(request).await?;
        Ok(MatchingResultsResponse {
            total: results.len(),
            results,
        })
    }

    pub async fn get_matching_result(
        &self,
        result_id: Uuid,
    ) -> Result<MatchingResultResponse, PlatformLegacyServiceError> {
        let Some(result) = self.repository.find_matching_result(result_id).await? else {
            return Err(PlatformLegacyServiceError::NotFound {
                resource: "matching_result",
            });
        };
        Ok(MatchingResultResponse { result })
    }
}

#[derive(Debug, Clone)]
pub struct PlatformJobCommand {
    pub operation: String,
    pub task_type: String,
    pub subject: String,
    pub aggregate_type: String,
    pub aggregate_id: Uuid,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub label: String,
    pub source: Value,
    pub payload: Value,
    pub affected_scopes: Vec<String>,
    pub affected_months: Vec<String>,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct PlatformJobCommandResult {
    pub task_id: Uuid,
    pub outbox_event_id: Uuid,
    pub status: String,
    pub idempotency_key: String,
}

#[derive(Debug, Serialize)]
pub struct PlatformJobCommandResponse {
    pub accepted: bool,
    pub task_id: String,
    pub outbox_event_id: String,
    pub status: String,
    pub idempotency_key: String,
}

impl From<PlatformJobCommandResult> for PlatformJobCommandResponse {
    fn from(value: PlatformJobCommandResult) -> Self {
        Self {
            accepted: true,
            task_id: value.task_id.to_string(),
            outbox_event_id: value.outbox_event_id.to_string(),
            status: value.status,
            idempotency_key: value.idempotency_key,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct RetryBackgroundJobRequest {
    pub idempotency_key: String,
    pub reason: String,
    pub replay_mode: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct RetryImportFileRequest {
    pub idempotency_key: String,
    pub reason: String,
}

#[derive(Debug, Deserialize)]
pub struct MatchingRunRequest {
    pub idempotency_key: String,
    pub scope_month: String,
    pub reason: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ImportSessionProjection {
    pub session_id: String,
    pub batches: Vec<ImportSessionBatch>,
    pub files: Vec<ImportSessionFile>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ImportSessionBatch {
    pub id: String,
    pub batch_type: String,
    pub status: String,
    pub row_count: i32,
    pub success_count: i32,
    pub error_count: i32,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct ImportSessionFile {
    pub id: String,
    pub batch_id: String,
    pub file_object_id: Option<String>,
    pub parse_status: String,
    pub row_count: i32,
    pub error_count: i32,
    pub template_key: Option<String>,
    pub created_at: String,
    pub updated_at: String,
}

#[derive(Debug, Serialize)]
pub struct ImportSessionResponse {
    pub session: ImportSessionProjection,
}

#[derive(Clone, Debug, Deserialize)]
pub struct MatchingResultsRequest {
    pub scope_month: Option<String>,
    pub status: Option<String>,
    pub limit: Option<i64>,
}

#[derive(Clone, Debug, Serialize)]
pub struct MatchingResultRow {
    pub result_id: String,
    pub scope_month: String,
    pub candidate_key: String,
    pub status: String,
    pub score: String,
    pub payload: Value,
    pub source_versions: Value,
    pub updated_at: String,
}

#[derive(Debug, Serialize)]
pub struct MatchingResultsResponse {
    pub total: usize,
    pub results: Vec<MatchingResultRow>,
}

#[derive(Debug, Serialize)]
pub struct MatchingResultResponse {
    pub result: MatchingResultRow,
}

fn required_text(value: &str, code: &'static str) -> Result<String, PlatformLegacyServiceError> {
    let value = value.trim();
    if value.is_empty() {
        return Err(invalid_request(code, "required field is missing"));
    }
    Ok(value.to_owned())
}

fn normalize_month(value: &str) -> Result<String, PlatformLegacyServiceError> {
    let value = value.trim();
    if value.len() != 7 {
        return Err(invalid_request(
            "invalid_scope_month",
            "scope_month must use YYYY-MM",
        ));
    }
    let mut parts = value.split('-');
    let year = parts.next().unwrap_or_default();
    let month = parts.next().unwrap_or_default();
    if parts.next().is_some()
        || year.len() != 4
        || month.len() != 2
        || !year.chars().all(|c| c.is_ascii_digit())
        || !month.chars().all(|c| c.is_ascii_digit())
        || !matches!(month, "01" | "02" | "03" | "04" | "05" | "06" | "07" | "08" | "09" | "10" | "11" | "12")
    {
        return Err(invalid_request(
            "invalid_scope_month",
            "scope_month must use YYYY-MM",
        ));
    }
    Ok(value.to_owned())
}

fn deterministic_scope_uuid(scope_key: &str) -> Uuid {
    let mut first = std::collections::hash_map::DefaultHasher::new();
    scope_key.hash(&mut first);
    let mut second = std::collections::hash_map::DefaultHasher::new();
    "finops.platform_legacy".hash(&mut second);
    scope_key.hash(&mut second);
    let value = ((first.finish() as u128) << 64) | second.finish() as u128;
    Uuid::from_u128(value)
}

fn invalid_request(
    code: &'static str,
    message: impl Into<String>,
) -> PlatformLegacyServiceError {
    PlatformLegacyServiceError::InvalidRequest {
        code,
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use async_trait::async_trait;
    use serde_json::json;

    use super::*;

    #[derive(Default)]
    struct FixturePlatformRepository {
        commands: Arc<Mutex<Vec<PlatformJobCommand>>>,
        import_session: Option<ImportSessionProjection>,
        matching_results: Vec<MatchingResultRow>,
        matching_result: Option<MatchingResultRow>,
    }

    #[async_trait]
    impl PlatformLegacyRepository for FixturePlatformRepository {
        async fn create_job_command(
            &self,
            command: PlatformJobCommand,
        ) -> Result<PlatformJobCommandResult, PlatformLegacyRepositoryError> {
            self.commands.lock().unwrap().push(command.clone());
            Ok(PlatformJobCommandResult {
                task_id: Uuid::parse_str("11111111-1111-4111-8111-111111111111").unwrap(),
                outbox_event_id: Uuid::parse_str("22222222-2222-4222-8222-222222222222")
                    .unwrap(),
                status: "queued".to_owned(),
                idempotency_key: command.idempotency_key,
            })
        }

        async fn find_import_session(
            &self,
            _session_id: &str,
        ) -> Result<Option<ImportSessionProjection>, PlatformLegacyRepositoryError> {
            Ok(self.import_session.clone())
        }

        async fn list_matching_results(
            &self,
            _request: MatchingResultsRequest,
        ) -> Result<Vec<MatchingResultRow>, PlatformLegacyRepositoryError> {
            Ok(self.matching_results.clone())
        }

        async fn find_matching_result(
            &self,
            _result_id: Uuid,
        ) -> Result<Option<MatchingResultRow>, PlatformLegacyRepositoryError> {
            Ok(self.matching_result.clone())
        }
    }

    #[tokio::test]
    async fn background_job_retry_creates_job_command_with_actor_and_idempotency() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });
        let job_id = Uuid::parse_str("33333333-3333-4333-8333-333333333333").unwrap();

        let response = service
            .retry_background_job(
                job_id,
                RetryBackgroundJobRequest {
                    idempotency_key: "background_job.retry:test".to_owned(),
                    reason: "staging replay".to_owned(),
                    replay_mode: None,
                },
                actor(),
            )
            .await
            .unwrap();

        assert_eq!(response.status, "queued");
        let stored = commands.lock().unwrap();
        let command = stored.first().unwrap();
        assert_eq!(command.operation, "background_job.retry");
        assert_eq!(command.aggregate_id, job_id);
        assert_eq!(command.idempotency_key, "background_job.retry:test");
        assert_eq!(command.actor.actor_id, "YNSYLP005");
        assert_eq!(command.payload["schema_version"], "finops.platform_legacy.background_job_retry.v1");
    }

    #[tokio::test]
    async fn import_session_projection_returns_batches_and_files_without_legacy_state() {
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            import_session: Some(ImportSessionProjection {
                session_id: "legacy-session-1".to_owned(),
                batches: vec![ImportSessionBatch {
                    id: "44444444-4444-4444-8444-444444444444".to_owned(),
                    batch_type: "bank_transaction".to_owned(),
                    status: "completed".to_owned(),
                    row_count: 2,
                    success_count: 2,
                    error_count: 0,
                    created_at: "2026-05-17T00:00:00Z".to_owned(),
                    updated_at: "2026-05-17T00:00:00Z".to_owned(),
                }],
                files: vec![ImportSessionFile {
                    id: "55555555-5555-4555-8555-555555555555".to_owned(),
                    batch_id: "44444444-4444-4444-8444-444444444444".to_owned(),
                    file_object_id: None,
                    parse_status: "parsed".to_owned(),
                    row_count: 2,
                    error_count: 0,
                    template_key: Some("icbc_historydetail".to_owned()),
                    created_at: "2026-05-17T00:00:00Z".to_owned(),
                    updated_at: "2026-05-17T00:00:00Z".to_owned(),
                }],
            }),
            ..Default::default()
        });

        let response = service.get_import_session("legacy-session-1").await.unwrap();

        assert_eq!(response.session.session_id, "legacy-session-1");
        assert_eq!(response.session.batches.len(), 1);
        assert_eq!(response.session.files[0].template_key.as_deref(), Some("icbc_historydetail"));
    }

    #[tokio::test]
    async fn matching_run_creates_scoped_worker_command() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        service
            .request_matching_run(
                MatchingRunRequest {
                    idempotency_key: "matching.run:2026-05".to_owned(),
                    scope_month: "2026-05".to_owned(),
                    reason: None,
                },
                actor(),
            )
            .await
            .unwrap();

        let stored = commands.lock().unwrap();
        let command = stored.first().unwrap();
        assert_eq!(command.task_type, "workbench_matching");
        assert_eq!(command.affected_scopes, vec!["workbench:2026-05"]);
        assert_eq!(command.affected_months, vec!["2026-05-01"]);
    }

    #[tokio::test]
    async fn matching_results_return_candidate_read_model_rows() {
        let result = MatchingResultRow {
            result_id: "66666666-6666-4666-8666-666666666666".to_owned(),
            scope_month: "2026-05-01".to_owned(),
            candidate_key: "bank:1:invoice:1".to_owned(),
            status: "suggested".to_owned(),
            score: "0.980000".to_owned(),
            payload: json!({"bank_row_id": "bank-1"}),
            source_versions: json!({"fact_updated_at": "2026-05-17T00:00:00Z"}),
            updated_at: "2026-05-17T00:00:00Z".to_owned(),
        };
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            matching_results: vec![result.clone()],
            matching_result: Some(result.clone()),
            ..Default::default()
        });

        let list = service
            .list_matching_results(MatchingResultsRequest {
                scope_month: Some("2026-05".to_owned()),
                status: Some("suggested".to_owned()),
                limit: Some(20),
            })
            .await
            .unwrap();
        let detail = service
            .get_matching_result(Uuid::parse_str(&result.result_id).unwrap())
            .await
            .unwrap();

        assert_eq!(list.total, 1);
        assert_eq!(detail.result.candidate_key, "bank:1:invoice:1");
    }

    fn actor() -> WriteActor {
        WriteActor::oa_user("YNSYLP005", Some("request-1".to_owned()))
    }
}
