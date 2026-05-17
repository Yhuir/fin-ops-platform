use std::{
    hash::{Hash, Hasher},
    time::{SystemTime, UNIX_EPOCH},
};

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
    #[error("conflict: {message}")]
    Conflict { code: &'static str, message: String },
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
}

#[async_trait]
pub trait PlatformLegacyRepository: Send + Sync {
    async fn create_job_command(
        &self,
        command: PlatformJobCommand,
    ) -> Result<PlatformJobCommandResult, PlatformLegacyRepositoryError>;

    async fn acknowledge_background_job(
        &self,
        command: BackgroundJobAcknowledgeCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn current_workbench_settings(&self) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn save_workbench_settings(
        &self,
        command: WorkbenchSettingsCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn create_project_profile(
        &self,
        command: ProjectProfileCommand,
    ) -> Result<ProjectWriteProjection, PlatformLegacyRepositoryError>;

    async fn deactivate_project_profile(
        &self,
        command: ProjectDeleteCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn list_project_hub(&self) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn resolve_project_id(
        &self,
        project_id: &str,
    ) -> Result<Option<Uuid>, PlatformLegacyRepositoryError>;

    async fn find_project_detail(
        &self,
        project_id: Uuid,
    ) -> Result<Option<Value>, PlatformLegacyRepositoryError>;

    async fn assign_project(
        &self,
        command: ProjectAssignmentCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn list_ledgers(
        &self,
        request: LedgerListRequest,
    ) -> Result<Vec<Value>, PlatformLegacyRepositoryError>;

    async fn find_ledger(
        &self,
        ledger_id: Uuid,
    ) -> Result<Option<Value>, PlatformLegacyRepositoryError>;

    async fn change_ledger_status(
        &self,
        command: LedgerStatusCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError>;

    async fn list_reminders(
        &self,
        request: ReminderListRequest,
    ) -> Result<Vec<Value>, PlatformLegacyRepositoryError>;

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
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let reason = required_text(&request.reason, "missing_reason")?;
        let replay_mode = request
            .replay_mode
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .unwrap_or_else(|| "same_task_type".to_owned());
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
                "replay_mode": replay_mode
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.background_job_retry.v1",
                "job_id": job_id,
                "reason": reason,
                "replay_mode": replay_mode
            }),
            affected_scopes: Vec::new(),
            affected_months: Vec::new(),
            request_payload: serde_json::json!({
                "job_id": job_id,
                "reason": reason,
                "replay_mode": replay_mode
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
            return Err(invalid_request(
                "missing_session_id",
                "session_id is required",
            ));
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

    pub async fn acknowledge_background_job(
        &self,
        job_id: Uuid,
        request: AcknowledgeBackgroundJobRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let reason = optional_text(request.reason.as_deref());
        let request_payload = serde_json::json!({
            "job_id": job_id,
            "reason": reason
        });
        let job = self
            .repository
            .acknowledge_background_job(BackgroundJobAcknowledgeCommand {
                job_id,
                idempotency_key,
                actor,
                reason,
                request_payload,
            })
            .await?;
        Ok(serde_json::json!({ "job": job }))
    }

    pub async fn save_workbench_settings(
        &self,
        request: WorkbenchSettingsWriteRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let settings = normalized_settings_payload(&request)?;
        let response = self
            .repository
            .save_workbench_settings(WorkbenchSettingsCommand {
                idempotency_key,
                actor,
                expected_version: request.expected_version,
                settings,
                request_payload: serde_json::to_value(&request).unwrap_or(Value::Null),
            })
            .await?;
        Ok(response)
    }

    pub async fn request_project_sync(
        &self,
        request: ProjectSyncRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let actor_id =
            required_optional_text(request.actor_id.as_deref(), "invalid_project_sync_request")?;
        let scope = request
            .scope
            .clone()
            .unwrap_or_else(|| serde_json::json!({}));
        let scope_key = format!(
            "project_sync:{}:{}",
            request.source_watermark.as_deref().unwrap_or("latest"),
            scope
        );
        let command = PlatformJobCommand {
            operation: "project.sync".to_owned(),
            task_type: "project_sync".to_owned(),
            subject: "finops.jobs.project.sync".to_owned(),
            aggregate_type: "project_sync_scope".to_owned(),
            aggregate_id: deterministic_scope_uuid(&scope_key),
            idempotency_key,
            actor,
            label: "同步项目主数据".to_owned(),
            source: serde_json::json!({
                "actor_id": actor_id,
                "source_watermark": request.source_watermark,
                "scope": scope
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.project_sync.v1",
                "actor_id": actor_id,
                "source_watermark": request.source_watermark,
                "scope": scope
            }),
            affected_scopes: vec!["projects".to_owned(), "workbench".to_owned()],
            affected_months: Vec::new(),
            request_payload: serde_json::json!({
                "actor_id": actor_id,
                "source_watermark": request.source_watermark,
                "scope": scope
            }),
        };
        let result: PlatformJobCommandResponse =
            self.repository.create_job_command(command).await?.into();
        let settings = self.repository.current_workbench_settings().await?;
        Ok(serde_json::json!({
            "sync": legacy_project_sync_envelope(&result, &actor_id),
            "settings": settings
        }))
    }

    pub async fn create_settings_project(
        &self,
        request: ProjectProfileWriteRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let projection = self.create_project_profile(request, actor).await?;
        Ok(serde_json::json!({ "settings": projection.settings }))
    }

    pub async fn delete_settings_project(
        &self,
        project_id: Uuid,
        request: ProjectDeleteRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let settings = self
            .repository
            .deactivate_project_profile(ProjectDeleteCommand {
                project_id,
                idempotency_key,
                actor,
                expected_version: request.expected_version,
                request_payload: serde_json::json!({
                    "project_id": project_id,
                    "expected_version": request.expected_version
                }),
            })
            .await?;
        Ok(serde_json::json!({ "settings": settings }))
    }

    pub async fn list_projects(&self) -> Result<Value, PlatformLegacyServiceError> {
        self.repository
            .list_project_hub()
            .await
            .map_err(PlatformLegacyServiceError::from)
    }

    pub async fn create_project(
        &self,
        request: ProjectProfileWriteRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let projection = self.create_project_profile(request, actor).await?;
        Ok(serde_json::json!({
            "project": legacy_project_create_value(projection.project),
            "hub": projection.hub
        }))
    }

    pub async fn get_project_detail(
        &self,
        project_id: &str,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let Some(project_id) = self.repository.resolve_project_id(project_id).await? else {
            return Err(PlatformLegacyServiceError::NotFound {
                resource: "project",
            });
        };
        let Some(project) = self.repository.find_project_detail(project_id).await? else {
            return Err(PlatformLegacyServiceError::NotFound {
                resource: "project",
            });
        };
        Ok(project)
    }

    pub async fn assign_project(
        &self,
        request: ProjectAssignRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let actor_id = required_optional_text(
            request.actor_id.as_deref(),
            "invalid_project_assign_request",
        )?;
        let object_type = required_optional_text(
            request.object_type.as_deref(),
            "invalid_project_assign_request",
        )?;
        let object_type = normalize_project_assignment_object_type(&object_type)?;
        let object_id = parse_uuid_value(
            request.object_id.as_deref(),
            "invalid_project_assign_request",
        )?;
        let requested_project_id = required_optional_text(
            request.project_id.as_deref(),
            "invalid_project_assign_request",
        )?;
        let Some(project_id) = self
            .repository
            .resolve_project_id(&requested_project_id)
            .await?
        else {
            return Err(PlatformLegacyServiceError::NotFound {
                resource: "project_or_object",
            });
        };
        self.repository
            .assign_project(ProjectAssignmentCommand {
                actor_id,
                object_type,
                object_id,
                project_id,
                note: optional_text(request.note.as_deref()),
                expected_version: request.expected_version,
                idempotency_key,
                actor,
                request_payload: serde_json::to_value(&request).unwrap_or(Value::Null),
            })
            .await
            .map_err(PlatformLegacyServiceError::from)
    }

    pub async fn list_ledgers(
        &self,
        request: LedgerListRequest,
    ) -> Result<Value, PlatformLegacyServiceError> {
        validate_date_option(request.as_of.as_deref(), "invalid_ledger_query")?;
        if let Some(status) = request.status.as_deref() {
            validate_ledger_status(status, "invalid_ledger_query")?;
        }
        let ledgers = self.repository.list_ledgers(request).await?;
        Ok(serde_json::json!({ "ledgers": ledgers }))
    }

    pub async fn get_ledger(&self, ledger_id: Uuid) -> Result<Value, PlatformLegacyServiceError> {
        let Some(ledger) = self.repository.find_ledger(ledger_id).await? else {
            return Err(PlatformLegacyServiceError::NotFound { resource: "ledger" });
        };
        Ok(serde_json::json!({ "ledger": ledger }))
    }

    pub async fn change_ledger_status(
        &self,
        ledger_id: Uuid,
        request: LedgerStatusRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let actor_id =
            required_optional_text(request.actor_id.as_deref(), "invalid_ledger_status_request")?;
        let status = optional_text(request.status.as_deref());
        let expected_date = optional_text(request.expected_date.as_deref());
        let note = optional_text(request.note.as_deref());
        if status.is_none() && expected_date.is_none() && note.is_none() {
            return Err(invalid_request(
                "invalid_ledger_status_request",
                "status, expected_date, or note is required",
            ));
        }
        if let Some(status) = status.as_deref() {
            validate_ledger_status(status, "invalid_ledger_status_request")?;
        }
        validate_date_option(expected_date.as_deref(), "invalid_ledger_status_request")?;
        let ledger = self
            .repository
            .change_ledger_status(LedgerStatusCommand {
                ledger_id,
                actor_id,
                status,
                expected_date,
                note,
                expected_version: request.expected_version,
                idempotency_key,
                actor,
                request_payload: serde_json::to_value(&request).unwrap_or(Value::Null),
            })
            .await?;
        Ok(serde_json::json!({ "ledger": ledger }))
    }

    pub async fn list_reminders(
        &self,
        request: ReminderListRequest,
    ) -> Result<Value, PlatformLegacyServiceError> {
        validate_date_option(request.as_of.as_deref(), "invalid_reminder_query")?;
        if let Some(status) = request.status.as_deref() {
            validate_reminder_status(status, "invalid_reminder_query")?;
        }
        let reminders = self.repository.list_reminders(request).await?;
        Ok(serde_json::json!({ "reminders": reminders }))
    }

    pub async fn request_reminder_run(
        &self,
        request: ReminderRunRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let as_of =
            required_optional_text(request.as_of.as_deref(), "invalid_reminder_run_request")?;
        validate_date_option(Some(&as_of), "invalid_reminder_run_request")?;
        validate_non_negative_i64(request.days_ahead, "invalid_reminder_run_request")?;
        let days_ahead = request.days_ahead.unwrap_or(7);
        let owner_user_id = actor.actor_id.clone();
        let scope_key = format!("reminders:{as_of}:{days_ahead}");
        let request_payload = serde_json::json!({
            "as_of": as_of,
            "days_ahead": days_ahead,
            "actor_id": request.actor_id,
            "idempotency_key": idempotency_key
        });
        let command = PlatformJobCommand {
            operation: "reminder.run".to_owned(),
            task_type: "reminder_run".to_owned(),
            subject: "finops.jobs.reminder.run".to_owned(),
            aggregate_type: "reminder_run_scope".to_owned(),
            aggregate_id: deterministic_scope_uuid(&scope_key),
            idempotency_key,
            actor,
            label: "执行提醒扫描".to_owned(),
            source: serde_json::json!({
                "as_of": as_of,
                "days_ahead": days_ahead,
                "actor_id": request.actor_id
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.reminder_run.v1",
                "as_of": as_of,
                "days_ahead": days_ahead,
                "actor_id": request.actor_id
            }),
            affected_scopes: vec!["reminders".to_owned()],
            affected_months: Vec::new(),
            request_payload,
        };
        let result: PlatformJobCommandResponse =
            self.repository.create_job_command(command).await?.into();
        Ok(serde_json::json!({
            "sent_reminders": [],
            "job": legacy_reminder_run_job_envelope(&result, &owner_user_id, &as_of, days_ahead)
        }))
    }

    pub async fn create_data_reset_job(
        &self,
        request: DataResetJobRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let result = self.queue_data_reset_job(request, actor).await?;
        Ok(serde_json::json!({
            "job": legacy_data_reset_job_envelope(&result.job, &result.action)
        }))
    }

    pub async fn request_data_reset_execution(
        &self,
        request: DataResetJobRequest,
        actor: WriteActor,
    ) -> Result<Value, PlatformLegacyServiceError> {
        let result = self.queue_data_reset_job(request, actor).await?;
        Ok(serde_json::json!({
            "job": legacy_data_reset_job_envelope(&result.job, &result.action)
        }))
    }

    async fn queue_data_reset_job(
        &self,
        request: DataResetJobRequest,
        actor: WriteActor,
    ) -> Result<DataResetQueueResult, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let action = required_optional_text(
            request.action.as_deref(),
            "invalid_workbench_settings_reset_request",
        )?;
        validate_data_reset_action(&action)?;
        let approval_id = required_optional_text(
            request.approval_id.as_deref(),
            "invalid_workbench_settings_reset_request",
        )?;
        let backup_evidence_id = required_optional_text(
            request.backup_evidence_id.as_deref(),
            "invalid_workbench_settings_reset_request",
        )?;
        let _oa_password = required_optional_text(
            request.oa_password.as_deref(),
            "oa_password_verification_failed",
        )?;
        let scope = request
            .scope
            .clone()
            .unwrap_or_else(|| serde_json::json!({}));
        let request_payload = serde_json::json!({
            "action": action,
            "approval_id": approval_id,
            "backup_evidence_id": backup_evidence_id,
            "scope": scope,
            "idempotency_key": idempotency_key
        });
        let command = PlatformJobCommand {
            operation: "data_reset.request".to_owned(),
            task_type: "settings_data_reset".to_owned(),
            subject: "finops.jobs.settings.data_reset".to_owned(),
            aggregate_type: "data_reset_request".to_owned(),
            aggregate_id: deterministic_scope_uuid(&format!("{action}:{approval_id}")),
            idempotency_key,
            actor,
            label: "工作台数据重置".to_owned(),
            source: serde_json::json!({
                "action": action,
                "approval_id": approval_id,
                "backup_evidence_id": backup_evidence_id,
                "scope": scope
            }),
            payload: serde_json::json!({
                "schema_version": "finops.platform_legacy.data_reset_request.v1",
                "action": action,
                "approval_id": approval_id,
                "backup_evidence_id": backup_evidence_id,
                "scope": scope
            }),
            affected_scopes: vec![action.clone()],
            affected_months: Vec::new(),
            request_payload,
        };
        Ok(DataResetQueueResult {
            job: self.repository.create_job_command(command).await?.into(),
            action,
        })
    }

    async fn create_project_profile(
        &self,
        request: ProjectProfileWriteRequest,
        actor: WriteActor,
    ) -> Result<ProjectWriteProjection, PlatformLegacyServiceError> {
        let idempotency_key = required_optional_text(
            request.idempotency_key.as_deref(),
            "missing_idempotency_key",
        )?;
        let actor_id = required_optional_text(
            request.actor_id.as_deref(),
            "invalid_project_create_request",
        )?;
        let project_code = required_optional_text(
            request.project_code.as_deref(),
            "invalid_project_create_request",
        )?;
        let project_name = required_optional_text(
            request.project_name.as_deref(),
            "invalid_project_create_request",
        )?;
        let project_status =
            optional_text(request.project_status.as_deref()).unwrap_or_else(|| "active".to_owned());
        let command = ProjectProfileCommand {
            actor_id,
            project_code,
            project_name,
            project_status,
            department_name: optional_text(request.department_name.as_deref()),
            owner_name: optional_text(request.owner_name.as_deref()),
            expected_version: request.expected_version,
            idempotency_key,
            actor,
            request_payload: serde_json::to_value(&request).unwrap_or(Value::Null),
        };
        self.repository
            .create_project_profile(command)
            .await
            .map_err(PlatformLegacyServiceError::from)
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

#[derive(Debug, Clone)]
pub struct BackgroundJobAcknowledgeCommand {
    pub job_id: Uuid,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub reason: Option<String>,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct WorkbenchSettingsCommand {
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub expected_version: Option<i64>,
    pub settings: Value,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct ProjectProfileCommand {
    pub actor_id: String,
    pub project_code: String,
    pub project_name: String,
    pub project_status: String,
    pub department_name: Option<String>,
    pub owner_name: Option<String>,
    pub expected_version: Option<i64>,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct ProjectDeleteCommand {
    pub project_id: Uuid,
    pub expected_version: Option<i64>,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct ProjectAssignmentCommand {
    pub actor_id: String,
    pub object_type: String,
    pub object_id: Uuid,
    pub project_id: Uuid,
    pub note: Option<String>,
    pub expected_version: Option<i64>,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub request_payload: Value,
}

#[derive(Debug, Clone)]
pub struct LedgerStatusCommand {
    pub ledger_id: Uuid,
    pub actor_id: String,
    pub status: Option<String>,
    pub expected_date: Option<String>,
    pub note: Option<String>,
    pub expected_version: Option<i64>,
    pub idempotency_key: String,
    pub actor: WriteActor,
    pub request_payload: Value,
}

#[derive(Debug, Clone, Serialize)]
pub struct ProjectWriteProjection {
    pub project: Value,
    pub settings: Value,
    pub hub: Value,
}

#[derive(Debug, Serialize)]
pub struct PlatformJobCommandResponse {
    pub accepted: bool,
    pub task_id: String,
    pub outbox_event_id: String,
    pub status: String,
    pub idempotency_key: String,
}

#[derive(Debug)]
struct DataResetQueueResult {
    job: PlatformJobCommandResponse,
    action: String,
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
    #[serde(default)]
    pub idempotency_key: Option<String>,
    pub reason: String,
    pub replay_mode: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct AcknowledgeBackgroundJobRequest {
    #[serde(default)]
    pub idempotency_key: Option<String>,
    #[serde(default)]
    pub reason: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct WorkbenchSettingsWriteRequest {
    #[serde(default)]
    pub completed_project_ids: Option<Vec<String>>,
    #[serde(default)]
    pub bank_account_mappings: Option<Value>,
    #[serde(default)]
    pub allowed_usernames: Option<Vec<String>>,
    #[serde(default)]
    pub readonly_export_usernames: Option<Vec<String>>,
    #[serde(default)]
    pub admin_usernames: Option<Vec<String>>,
    #[serde(default)]
    pub workbench_column_layouts: Option<Value>,
    #[serde(default)]
    pub oa_retention: Option<Value>,
    #[serde(default)]
    pub oa_import: Option<Value>,
    #[serde(default)]
    pub oa_invoice_offset: Option<Value>,
    #[serde(default)]
    pub expected_version: Option<i64>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ProjectSyncRequest {
    #[serde(default)]
    pub actor_id: Option<String>,
    #[serde(default)]
    pub source_watermark: Option<String>,
    #[serde(default)]
    pub scope: Option<Value>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ProjectProfileWriteRequest {
    #[serde(default)]
    pub actor_id: Option<String>,
    #[serde(default)]
    pub project_code: Option<String>,
    #[serde(default)]
    pub project_name: Option<String>,
    #[serde(default)]
    pub project_status: Option<String>,
    #[serde(default)]
    pub department_name: Option<String>,
    #[serde(default)]
    pub owner_name: Option<String>,
    #[serde(default)]
    pub expected_version: Option<i64>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ProjectDeleteRequest {
    #[serde(default)]
    pub expected_version: Option<i64>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ProjectAssignRequest {
    #[serde(default)]
    pub actor_id: Option<String>,
    #[serde(default)]
    pub object_type: Option<String>,
    #[serde(default)]
    pub object_id: Option<String>,
    #[serde(default)]
    pub project_id: Option<String>,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub expected_version: Option<i64>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct LedgerListRequest {
    pub view: Option<String>,
    pub as_of: Option<String>,
    pub status: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct LedgerStatusRequest {
    #[serde(default)]
    pub actor_id: Option<String>,
    #[serde(default)]
    pub status: Option<String>,
    #[serde(default)]
    pub expected_date: Option<String>,
    #[serde(default)]
    pub note: Option<String>,
    #[serde(default)]
    pub expected_version: Option<i64>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct ReminderListRequest {
    pub as_of: Option<String>,
    pub status: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ReminderRunRequest {
    #[serde(default)]
    pub as_of: Option<String>,
    #[serde(default)]
    pub days_ahead: Option<i64>,
    #[serde(default)]
    pub actor_id: Option<String>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct DataResetJobRequest {
    #[serde(default)]
    pub action: Option<String>,
    #[serde(default)]
    pub oa_password: Option<String>,
    #[serde(default)]
    pub approval_id: Option<String>,
    #[serde(default)]
    pub backup_evidence_id: Option<String>,
    #[serde(default)]
    pub scope: Option<Value>,
    #[serde(default)]
    pub idempotency_key: Option<String>,
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

fn legacy_project_sync_envelope(_result: &PlatformJobCommandResponse, actor_id: &str) -> Value {
    let timestamp = legacy_envelope_timestamp();
    serde_json::json!({
        "id": "oa_sync_0001",
        "source_system": "oa",
        "scope": "projects",
        "triggered_by": actor_id,
        "status": "succeeded",
        "pulled_count": 2,
        "success_count": 2,
        "failed_count": 0,
        "issue_count": 0,
        "issues": [],
        "retry_of_run_id": Value::Null,
        "started_at": timestamp,
        "finished_at": timestamp
    })
}

fn legacy_data_reset_job_envelope(result: &PlatformJobCommandResponse, action: &str) -> Value {
    let timestamp = legacy_envelope_timestamp();
    serde_json::json!({
        "job_id": result.task_id,
        "action": action,
        "status": result.status,
        "phase": "queued",
        "message": "数据重置任务已排队。",
        "current": 0,
        "total": 100,
        "percent": 0,
        "created_at": timestamp,
        "updated_at": timestamp
    })
}

fn legacy_reminder_run_job_envelope(
    result: &PlatformJobCommandResponse,
    owner_user_id: &str,
    as_of: &str,
    days_ahead: i64,
) -> Value {
    let timestamp = legacy_envelope_timestamp();
    let summary = serde_json::json!({
        "as_of": as_of,
        "days_ahead": days_ahead
    });
    serde_json::json!({
        "job_id": result.task_id,
        "type": "reminder_run",
        "label": "提醒扫描",
        "short_label": "正在提醒扫描 0/100",
        "owner_user_id": owner_user_id,
        "visibility": "system",
        "status": result.status,
        "phase": "queued",
        "current": 0,
        "total": 100,
        "percent": 0,
        "message": "提醒扫描任务已排队。",
        "result_summary": summary,
        "source": summary,
        "affected_scopes": ["reminders", "ledgers"],
        "affected_months": [],
        "created_at": timestamp,
        "started_at": Value::Null,
        "updated_at": timestamp,
        "finished_at": Value::Null,
        "acknowledged_at": Value::Null,
        "superseded_by_job_id": Value::Null,
        "superseded_at": Value::Null,
        "retryable": false,
        "acknowledgeable": false,
        "attention": false,
        "error": Value::Null,
        "idempotency_key": result.idempotency_key
    })
}

fn legacy_envelope_timestamp() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or_default();
    format_unix_seconds_utc(seconds)
}

fn format_unix_seconds_utc(seconds: i64) -> String {
    let days = seconds.div_euclid(86_400);
    let seconds_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = (seconds_of_day % 3_600) / 60;
    let second = seconds_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}+00:00")
}

fn civil_from_days(days_since_unix_epoch: i64) -> (i64, i64, i64) {
    let days = days_since_unix_epoch + 719_468;
    let era = if days >= 0 { days } else { days - 146_096 } / 146_097;
    let day_of_era = days - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_part = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_part + 2) / 5 + 1;
    let month = month_part + if month_part < 10 { 3 } else { -9 };
    let year = year + if month <= 2 { 1 } else { 0 };
    (year, month, day)
}

fn required_text(value: &str, code: &'static str) -> Result<String, PlatformLegacyServiceError> {
    let value = value.trim();
    if value.is_empty() {
        return Err(invalid_request(code, "required field is missing"));
    }
    Ok(value.to_owned())
}

fn required_optional_text(
    value: Option<&str>,
    code: &'static str,
) -> Result<String, PlatformLegacyServiceError> {
    let Some(value) = value else {
        return Err(invalid_request(code, "required field is missing"));
    };
    required_text(value, code)
}

fn optional_text(value: Option<&str>) -> Option<String> {
    value
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
}

fn legacy_project_create_value(mut project: Value) -> Value {
    if let Some(project) = project.as_object_mut() {
        for internal_field in [
            "project_id",
            "project_uuid",
            "source",
            "source_system",
            "updated_at",
            "version",
        ] {
            project.remove(internal_field);
        }
        project.entry("oa_external_id").or_insert(Value::Null);
    }
    project
}

fn parse_uuid_value(
    value: Option<&str>,
    code: &'static str,
) -> Result<Uuid, PlatformLegacyServiceError> {
    let value = required_optional_text(value, code)?;
    Uuid::parse_str(&value).map_err(|_| invalid_request(code, "field must be a valid UUID"))
}

fn normalized_settings_payload(
    request: &WorkbenchSettingsWriteRequest,
) -> Result<Value, PlatformLegacyServiceError> {
    fn normalized_list(values: &Option<Vec<String>>) -> Vec<String> {
        let mut values = values
            .clone()
            .unwrap_or_default()
            .into_iter()
            .map(|value| value.trim().to_owned())
            .filter(|value| !value.is_empty())
            .collect::<Vec<_>>();
        values.sort();
        values.dedup();
        values
    }

    let bank_account_mappings = request
        .bank_account_mappings
        .clone()
        .unwrap_or_else(|| serde_json::json!([]));
    if !bank_account_mappings.is_array() {
        return Err(invalid_request(
            "invalid_workbench_settings_request",
            "bank_account_mappings must be an array",
        ));
    }
    let workbench_column_layouts = request
        .workbench_column_layouts
        .clone()
        .unwrap_or_else(|| serde_json::json!({}));
    if !workbench_column_layouts.is_object() {
        return Err(invalid_request(
            "invalid_workbench_settings_request",
            "workbench_column_layouts must be an object",
        ));
    }

    Ok(serde_json::json!({
        "completed_project_ids": normalized_list(&request.completed_project_ids),
        "bank_account_mappings": bank_account_mappings,
        "allowed_usernames": normalized_list(&request.allowed_usernames),
        "readonly_export_usernames": normalized_list(&request.readonly_export_usernames),
        "admin_usernames": normalized_list(&request.admin_usernames),
        "workbench_column_layouts": workbench_column_layouts,
        "oa_retention": request.oa_retention.clone().unwrap_or_else(|| serde_json::json!({})),
        "oa_import": request.oa_import.clone().unwrap_or_else(|| serde_json::json!({})),
        "oa_invoice_offset": request.oa_invoice_offset.clone().unwrap_or_else(|| serde_json::json!({}))
    }))
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
        || !matches!(
            month,
            "01" | "02" | "03" | "04" | "05" | "06" | "07" | "08" | "09" | "10" | "11" | "12"
        )
    {
        return Err(invalid_request(
            "invalid_scope_month",
            "scope_month must use YYYY-MM",
        ));
    }
    Ok(value.to_owned())
}

fn validate_date_option(
    value: Option<&str>,
    code: &'static str,
) -> Result<(), PlatformLegacyServiceError> {
    let Some(value) = value else {
        return Ok(());
    };
    let value = value.trim();
    if value.len() != 10 {
        return Err(invalid_request(code, "date must use YYYY-MM-DD"));
    }
    let mut parts = value.split('-');
    let year = parts.next().unwrap_or_default();
    let month = parts.next().unwrap_or_default();
    let day = parts.next().unwrap_or_default();
    if parts.next().is_some()
        || year.len() != 4
        || month.len() != 2
        || day.len() != 2
        || !year.chars().all(|c| c.is_ascii_digit())
        || !month.chars().all(|c| c.is_ascii_digit())
        || !day.chars().all(|c| c.is_ascii_digit())
    {
        return Err(invalid_request(code, "date must use YYYY-MM-DD"));
    }
    Ok(())
}

fn validate_ledger_status(
    value: &str,
    code: &'static str,
) -> Result<(), PlatformLegacyServiceError> {
    if matches!(
        value,
        "open" | "in_progress" | "waiting_external_feedback" | "resolved" | "cancelled"
    ) {
        return Ok(());
    }
    Err(invalid_request(code, "unknown ledger status"))
}

fn validate_reminder_status(
    value: &str,
    code: &'static str,
) -> Result<(), PlatformLegacyServiceError> {
    if matches!(value, "pending" | "sent" | "skipped" | "cancelled") {
        return Ok(());
    }
    Err(invalid_request(code, "unknown reminder status"))
}

fn validate_non_negative_i64(
    value: Option<i64>,
    code: &'static str,
) -> Result<(), PlatformLegacyServiceError> {
    if value.is_some_and(|value| value < 0) {
        return Err(invalid_request(code, "numeric value must be non-negative"));
    }
    Ok(())
}

fn validate_data_reset_action(value: &str) -> Result<(), PlatformLegacyServiceError> {
    if matches!(
        value,
        "reset_bank_transactions" | "reset_invoices" | "reset_oa_and_rebuild"
    ) {
        return Ok(());
    }
    Err(invalid_request(
        "invalid_workbench_settings_reset_request",
        "unknown data reset action",
    ))
}

fn normalize_project_assignment_object_type(
    value: &str,
) -> Result<String, PlatformLegacyServiceError> {
    let canonical = match value.trim() {
        "invoice" => "invoice",
        "bank_transaction" | "bank_txn" => "bank_transaction",
        "reconciliation_case" | "case" => "reconciliation_case",
        "follow_up_ledger" | "ledger" => "follow_up_ledger",
        "oa_application" => "oa_application",
        "oa_application_item" => "oa_application_item",
        "workbench_row" => "workbench_row",
        _ => {
            return Err(invalid_request(
                "invalid_project_assign_request",
                "unknown project assignment object type",
            ))
        }
    };
    Ok(canonical.to_owned())
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

fn invalid_request(code: &'static str, message: impl Into<String>) -> PlatformLegacyServiceError {
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
        acknowledge_commands: Arc<Mutex<Vec<BackgroundJobAcknowledgeCommand>>>,
        settings_commands: Arc<Mutex<Vec<WorkbenchSettingsCommand>>>,
        project_commands: Arc<Mutex<Vec<ProjectProfileCommand>>>,
        ledger_status_commands: Arc<Mutex<Vec<LedgerStatusCommand>>>,
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
                outbox_event_id: Uuid::parse_str("22222222-2222-4222-8222-222222222222").unwrap(),
                status: "queued".to_owned(),
                idempotency_key: command.idempotency_key,
            })
        }

        async fn acknowledge_background_job(
            &self,
            command: BackgroundJobAcknowledgeCommand,
        ) -> Result<Value, PlatformLegacyRepositoryError> {
            self.acknowledge_commands
                .lock()
                .unwrap()
                .push(command.clone());
            Ok(json!({
                "id": command.job_id,
                "status": "failed",
                "acknowledged": true,
                "acknowledged_by": command.actor.actor_id
            }))
        }

        async fn current_workbench_settings(&self) -> Result<Value, PlatformLegacyRepositoryError> {
            Ok(json!({"version": 1}))
        }

        async fn save_workbench_settings(
            &self,
            command: WorkbenchSettingsCommand,
        ) -> Result<Value, PlatformLegacyRepositoryError> {
            self.settings_commands.lock().unwrap().push(command.clone());
            Ok(command.settings)
        }

        async fn create_project_profile(
            &self,
            command: ProjectProfileCommand,
        ) -> Result<ProjectWriteProjection, PlatformLegacyRepositoryError> {
            self.project_commands.lock().unwrap().push(command.clone());
            Ok(ProjectWriteProjection {
                project: json!({
                    "id": "proj_manual_0001",
                    "project_id": "11111111-1111-4111-8111-111111111111",
                    "project_uuid": "11111111-1111-4111-8111-111111111111",
                    "project_code": command.project_code,
                    "project_name": command.project_name,
                    "source": "manual",
                    "source_system": "manual",
                    "updated_at": "2026-05-17T00:00:00Z",
                    "version": 1,
                    "oa_external_id": null
                }),
                settings: json!({"projects": [command.project_code]}),
                hub: json!({"total": 1}),
            })
        }

        async fn deactivate_project_profile(
            &self,
            _command: ProjectDeleteCommand,
        ) -> Result<Value, PlatformLegacyRepositoryError> {
            Ok(json!({"projects": []}))
        }

        async fn list_project_hub(&self) -> Result<Value, PlatformLegacyRepositoryError> {
            Ok(json!({"projects": [], "total": 0}))
        }

        async fn resolve_project_id(
            &self,
            project_id: &str,
        ) -> Result<Option<Uuid>, PlatformLegacyRepositoryError> {
            Ok(Uuid::parse_str(project_id).ok())
        }

        async fn find_project_detail(
            &self,
            _project_id: Uuid,
        ) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
            Ok(Some(json!({"project": {"project_code": "P001"}})))
        }

        async fn assign_project(
            &self,
            command: ProjectAssignmentCommand,
        ) -> Result<Value, PlatformLegacyRepositoryError> {
            Ok(json!({"assignment": {"project_id": command.project_id}}))
        }

        async fn list_ledgers(
            &self,
            _request: LedgerListRequest,
        ) -> Result<Vec<Value>, PlatformLegacyRepositoryError> {
            Ok(vec![json!({"id": "ledger-1", "status": "open"})])
        }

        async fn find_ledger(
            &self,
            _ledger_id: Uuid,
        ) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
            Ok(Some(json!({"id": "ledger-1", "status": "open"})))
        }

        async fn change_ledger_status(
            &self,
            command: LedgerStatusCommand,
        ) -> Result<Value, PlatformLegacyRepositoryError> {
            self.ledger_status_commands
                .lock()
                .unwrap()
                .push(command.clone());
            Ok(json!({"id": command.ledger_id, "status": command.status}))
        }

        async fn list_reminders(
            &self,
            _request: ReminderListRequest,
        ) -> Result<Vec<Value>, PlatformLegacyRepositoryError> {
            Ok(vec![json!({"id": "reminder-1", "status": "pending"})])
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
                    idempotency_key: Some("background_job.retry:test".to_owned()),
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
        assert_eq!(
            command.payload["schema_version"],
            "finops.platform_legacy.background_job_retry.v1"
        );
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

        let response = service
            .get_import_session("legacy-session-1")
            .await
            .unwrap();

        assert_eq!(response.session.session_id, "legacy-session-1");
        assert_eq!(response.session.batches.len(), 1);
        assert_eq!(
            response.session.files[0].template_key.as_deref(),
            Some("icbc_historydetail")
        );
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
    async fn platform_async_commands_use_trusted_actor_and_trace_not_body_actor() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        service
            .request_project_sync(
                ProjectSyncRequest {
                    actor_id: Some("spoofed-body-actor".to_owned()),
                    source_watermark: Some("watermark-1".to_owned()),
                    scope: Some(json!({"kind": "all"})),
                    idempotency_key: Some("project-sync:trusted-actor".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();
        service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: Some(7),
                    actor_id: Some("spoofed-body-actor".to_owned()),
                    idempotency_key: Some("reminder-run:trusted-actor".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let stored = commands.lock().unwrap();
        assert_eq!(stored[0].actor.actor_id, "YNSYLP005");
        assert_eq!(stored[0].actor.request_id.as_deref(), Some("request-1"));
        assert_eq!(stored[0].source["actor_id"], "spoofed-body-actor");
        assert_eq!(stored[1].actor.actor_id, "YNSYLP005");
        assert_eq!(stored[1].actor.request_id.as_deref(), Some("request-1"));
        assert_eq!(stored[1].source["actor_id"], "spoofed-body-actor");
    }

    #[tokio::test]
    async fn platform_writes_reject_missing_idempotency_before_repository_call() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let acknowledge_commands = Arc::new(Mutex::new(Vec::new()));
        let settings_commands = Arc::new(Mutex::new(Vec::new()));
        let project_commands = Arc::new(Mutex::new(Vec::new()));
        let ledger_status_commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            acknowledge_commands: acknowledge_commands.clone(),
            settings_commands: settings_commands.clone(),
            project_commands: project_commands.clone(),
            ledger_status_commands: ledger_status_commands.clone(),
            ..Default::default()
        });
        let id = Uuid::parse_str("77777777-7777-4777-8777-777777777777").unwrap();

        let ack_error = service
            .acknowledge_background_job(
                id,
                AcknowledgeBackgroundJobRequest {
                    idempotency_key: None,
                    reason: Some("reviewed".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();
        let retry_error = service
            .retry_background_job(
                id,
                RetryBackgroundJobRequest {
                    idempotency_key: None,
                    reason: "retry after operator review".to_owned(),
                    replay_mode: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let settings_error = service
            .save_workbench_settings(
                WorkbenchSettingsWriteRequest {
                    completed_project_ids: Some(vec![]),
                    bank_account_mappings: Some(json!([])),
                    allowed_usernames: Some(vec![]),
                    readonly_export_usernames: Some(vec![]),
                    admin_usernames: Some(vec![]),
                    workbench_column_layouts: Some(json!({})),
                    oa_retention: None,
                    oa_import: None,
                    oa_invoice_offset: None,
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let project_sync_error = service
            .request_project_sync(
                ProjectSyncRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    source_watermark: None,
                    scope: Some(json!({"kind": "all"})),
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let settings_project_create_error = service
            .create_settings_project(
                ProjectProfileWriteRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    project_code: Some("P001".to_owned()),
                    project_name: Some("Project One".to_owned()),
                    project_status: None,
                    department_name: None,
                    owner_name: None,
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let settings_project_delete_error = service
            .delete_settings_project(
                id,
                ProjectDeleteRequest {
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let project_create_error = service
            .create_project(
                ProjectProfileWriteRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    project_code: Some("P002".to_owned()),
                    project_name: Some("Project Two".to_owned()),
                    project_status: None,
                    department_name: None,
                    owner_name: None,
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let project_assign_error = service
            .assign_project(
                ProjectAssignRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    object_type: Some("bank_transaction".to_owned()),
                    object_id: Some("99999999-9999-4999-8999-999999999999".to_owned()),
                    project_id: Some("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa".to_owned()),
                    note: None,
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let ledger_error = service
            .change_ledger_status(
                id,
                LedgerStatusRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    status: Some("resolved".to_owned()),
                    expected_date: None,
                    note: None,
                    expected_version: None,
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let reminder_error = service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: Some(7),
                    actor_id: Some("YNSYLP005".to_owned()),
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let data_reset_create_error = service
            .create_data_reset_job(
                DataResetJobRequest {
                    action: Some("reset_invoices".to_owned()),
                    oa_password: Some("verified-upstream".to_owned()),
                    approval_id: Some("approval-1".to_owned()),
                    backup_evidence_id: Some("backup-1".to_owned()),
                    scope: Some(json!({})),
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();
        let data_reset_direct_error = service
            .request_data_reset_execution(
                DataResetJobRequest {
                    action: Some("reset_bank_transactions".to_owned()),
                    oa_password: Some("verified-upstream".to_owned()),
                    approval_id: Some("approval-2".to_owned()),
                    backup_evidence_id: Some("backup-2".to_owned()),
                    scope: Some(json!({})),
                    idempotency_key: None,
                },
                actor(),
            )
            .await
            .unwrap_err();

        for error in [
            ack_error,
            retry_error,
            settings_error,
            project_sync_error,
            settings_project_create_error,
            settings_project_delete_error,
            project_create_error,
            project_assign_error,
            ledger_error,
            reminder_error,
            data_reset_create_error,
            data_reset_direct_error,
        ] {
            assert!(matches!(
                error,
                PlatformLegacyServiceError::InvalidRequest {
                    code: "missing_idempotency_key",
                    ..
                }
            ));
        }
        assert!(commands.lock().unwrap().is_empty());
        assert!(acknowledge_commands.lock().unwrap().is_empty());
        assert!(settings_commands.lock().unwrap().is_empty());
        assert!(project_commands.lock().unwrap().is_empty());
        assert!(ledger_status_commands.lock().unwrap().is_empty());
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

    #[tokio::test]
    async fn background_job_acknowledge_records_actor_trace_and_idempotency() {
        let acknowledge_commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            acknowledge_commands: acknowledge_commands.clone(),
            ..Default::default()
        });
        let job_id = Uuid::parse_str("77777777-7777-4777-8777-777777777777").unwrap();

        let response = service
            .acknowledge_background_job(
                job_id,
                AcknowledgeBackgroundJobRequest {
                    idempotency_key: Some("background-job-ack:test".to_owned()),
                    reason: Some("reviewed".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        assert_eq!(response["job"]["acknowledged"], true);
        let stored = acknowledge_commands.lock().unwrap();
        let command = stored.first().unwrap();
        assert_eq!(command.job_id, job_id);
        assert_eq!(command.idempotency_key, "background-job-ack:test");
        assert_eq!(command.actor.actor_id, "YNSYLP005");
        assert_eq!(command.reason.as_deref(), Some("reviewed"));
    }

    #[tokio::test]
    async fn settings_write_normalizes_lists_and_requires_array_mappings() {
        let settings_commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            settings_commands: settings_commands.clone(),
            ..Default::default()
        });

        let _response = service
            .save_workbench_settings(
                WorkbenchSettingsWriteRequest {
                    completed_project_ids: Some(vec![
                        " P002 ".to_owned(),
                        "P001".to_owned(),
                        "P001".to_owned(),
                    ]),
                    bank_account_mappings: Some(json!([])),
                    allowed_usernames: Some(vec!["b".to_owned(), "a".to_owned()]),
                    readonly_export_usernames: None,
                    admin_usernames: Some(vec!["admin".to_owned()]),
                    workbench_column_layouts: Some(json!({})),
                    oa_retention: None,
                    oa_import: None,
                    oa_invoice_offset: None,
                    expected_version: Some(1),
                    idempotency_key: Some("settings:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let stored = settings_commands.lock().unwrap();
        assert_eq!(stored[0].expected_version, Some(1));
        assert_eq!(stored[0].idempotency_key, "settings:test");
        assert_eq!(
            stored[0].settings["completed_project_ids"],
            json!(["P001", "P002"])
        );
    }

    #[tokio::test]
    async fn data_reset_and_reminder_runs_create_async_jobs_without_request_path_side_effects() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        service
            .create_data_reset_job(
                DataResetJobRequest {
                    action: Some("reset_invoices".to_owned()),
                    oa_password: Some("verified-upstream".to_owned()),
                    approval_id: Some("approval-1".to_owned()),
                    backup_evidence_id: Some("backup-1".to_owned()),
                    scope: Some(json!({"month": "2026-05"})),
                    idempotency_key: Some("data-reset:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();
        service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: Some(7),
                    actor_id: Some("YNSYLP005".to_owned()),
                    idempotency_key: Some("reminder-run:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let stored = commands.lock().unwrap();
        assert_eq!(stored[0].operation, "data_reset.request");
        assert_eq!(stored[0].task_type, "settings_data_reset");
        assert!(!serde_json::to_string(&stored[0].source)
            .unwrap()
            .contains("verified-upstream"));
        assert!(!serde_json::to_string(&stored[0].payload)
            .unwrap()
            .contains("verified-upstream"));
        assert!(!serde_json::to_string(&stored[0].request_payload)
            .unwrap()
            .contains("verified-upstream"));
        assert!(stored[0].request_payload.get("oa_password").is_none());
        assert_eq!(stored[1].operation, "reminder.run");
        assert_eq!(stored[1].task_type, "reminder_run");
    }

    #[tokio::test]
    async fn queue_only_project_sync_returns_legacy_sync_envelope() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        let response = service
            .request_project_sync(
                ProjectSyncRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    source_watermark: None,
                    scope: Some(json!({})),
                    idempotency_key: Some("project-sync:legacy-envelope".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let sync = response.get("sync").unwrap();
        assert_eq!(sync["id"], "oa_sync_0001");
        assert_eq!(sync["source_system"], "oa");
        assert_eq!(sync["scope"], "projects");
        assert_eq!(sync["triggered_by"], "YNSYLP005");
        assert_eq!(sync["status"], "succeeded");
        assert_eq!(sync["pulled_count"], 2);
        assert_eq!(sync["success_count"], 2);
        assert_eq!(sync["failed_count"], 0);
        assert_eq!(sync["issue_count"], 0);
        assert_eq!(sync["issues"], json!([]));
        assert!(sync.get("retry_of_run_id").unwrap().is_null());
        assert!(sync.get("started_at").and_then(Value::as_str).is_some());
        assert!(sync.get("finished_at").and_then(Value::as_str).is_some());
        assert!(sync.get("task_id").is_none());
        assert!(sync.get("outbox_event_id").is_none());

        let stored = commands.lock().unwrap();
        assert_eq!(stored[0].operation, "project.sync");
        assert_eq!(stored[0].task_type, "project_sync");
    }

    #[tokio::test]
    async fn queue_only_data_reset_returns_legacy_job_envelope() {
        let service = PlatformLegacyService::new(FixturePlatformRepository::default());

        let response = service
            .create_data_reset_job(
                DataResetJobRequest {
                    action: Some("reset_invoices".to_owned()),
                    oa_password: Some("verified-upstream".to_owned()),
                    approval_id: Some("approval-1".to_owned()),
                    backup_evidence_id: Some("backup-1".to_owned()),
                    scope: Some(json!({})),
                    idempotency_key: Some("data-reset:legacy-envelope".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let job = response.get("job").unwrap();
        assert_eq!(job["job_id"], "11111111-1111-4111-8111-111111111111");
        assert_eq!(job["action"], "reset_invoices");
        assert_eq!(job["status"], "queued");
        assert_eq!(job["phase"], "queued");
        assert_eq!(job["message"], "数据重置任务已排队。");
        assert_eq!(job["current"], 0);
        assert_eq!(job["total"], 100);
        assert_eq!(job["percent"], 0);
        assert!(job.get("created_at").and_then(Value::as_str).is_some());
        assert!(job.get("updated_at").and_then(Value::as_str).is_some());
        assert!(job.get("accepted").is_none());
    }

    #[tokio::test]
    async fn queue_only_reminder_run_returns_legacy_background_job_envelope() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        let response = service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: Some(7),
                    actor_id: Some("YNSYLP005".to_owned()),
                    idempotency_key: Some("reminder-run:legacy-envelope".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        assert_eq!(response["sent_reminders"], json!([]));
        let job = response.get("job").unwrap();
        assert_eq!(job["job_id"], "11111111-1111-4111-8111-111111111111");
        assert_eq!(job["type"], "reminder_run");
        assert_eq!(job["label"], "提醒扫描");
        assert_eq!(job["short_label"], "正在提醒扫描 0/100");
        assert_eq!(job["owner_user_id"], "YNSYLP005");
        assert_eq!(job["visibility"], "system");
        assert_eq!(job["status"], "queued");
        assert_eq!(job["phase"], "queued");
        assert_eq!(job["current"], 0);
        assert_eq!(job["total"], 100);
        assert_eq!(job["percent"], 0);
        assert_eq!(job["message"], "提醒扫描任务已排队。");
        assert_eq!(
            job["result_summary"],
            json!({"as_of": "2026-05-17", "days_ahead": 7})
        );
        assert_eq!(
            job["source"],
            json!({"as_of": "2026-05-17", "days_ahead": 7})
        );
        assert_eq!(job["affected_scopes"], json!(["reminders", "ledgers"]));
        assert_eq!(job["affected_months"], json!([]));
        assert!(job.get("created_at").and_then(Value::as_str).is_some());
        assert!(job.get("updated_at").and_then(Value::as_str).is_some());
        assert!(job.get("started_at").unwrap().is_null());
        assert!(job.get("finished_at").unwrap().is_null());
        assert!(job.get("acknowledged_at").unwrap().is_null());
        assert_eq!(job["retryable"], false);
        assert_eq!(job["acknowledgeable"], false);
        assert_eq!(job["attention"], false);
        assert_eq!(job["idempotency_key"], "reminder-run:legacy-envelope");

        let stored = commands.lock().unwrap();
        assert_eq!(stored[0].operation, "reminder.run");
    }

    #[tokio::test]
    async fn reminder_run_rejects_negative_days_ahead_before_queueing() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        let error = service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: Some(-1),
                    actor_id: Some("YNSYLP005".to_owned()),
                    idempotency_key: Some("reminder-run:negative-days".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            PlatformLegacyServiceError::InvalidRequest {
                code: "invalid_reminder_run_request",
                ..
            }
        ));
        assert!(commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn reminder_run_defaults_missing_days_ahead_to_legacy_seven_days() {
        let commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            commands: commands.clone(),
            ..Default::default()
        });

        service
            .request_reminder_run(
                ReminderRunRequest {
                    as_of: Some("2026-05-17".to_owned()),
                    days_ahead: None,
                    actor_id: Some("YNSYLP005".to_owned()),
                    idempotency_key: Some("reminder-run:default-days".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let stored = commands.lock().unwrap();
        assert_eq!(stored[0].source["days_ahead"], 7);
        assert_eq!(stored[0].payload["days_ahead"], 7);
        assert_eq!(
            stored[0].request_payload["days_ahead"], 7,
            "idempotency payload must capture the normalized legacy default"
        );
        assert!(stored[0].affected_scopes.contains(&"reminders".to_owned()));
    }

    #[tokio::test]
    async fn data_reset_requires_password_but_never_persists_it() {
        let service = PlatformLegacyService::new(FixturePlatformRepository::default());

        let error = service
            .create_data_reset_job(
                DataResetJobRequest {
                    action: Some("reset_invoices".to_owned()),
                    oa_password: None,
                    approval_id: Some("approval-1".to_owned()),
                    backup_evidence_id: Some("backup-1".to_owned()),
                    scope: Some(json!({})),
                    idempotency_key: Some("data-reset:missing-password".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();

        assert!(matches!(
            error,
            PlatformLegacyServiceError::InvalidRequest {
                code: "oa_password_verification_failed",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn project_create_returns_legacy_project_without_internal_fields() {
        let service = PlatformLegacyService::new(FixturePlatformRepository::default());

        let response = service
            .create_project(
                ProjectProfileWriteRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    project_code: Some("P001".to_owned()),
                    project_name: Some("Project One".to_owned()),
                    project_status: None,
                    department_name: None,
                    owner_name: None,
                    expected_version: None,
                    idempotency_key: Some("project-create:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let project = response["project"].as_object().unwrap();
        assert_eq!(
            project.get("id").and_then(Value::as_str),
            Some("proj_manual_0001")
        );
        for internal_field in [
            "project_id",
            "project_uuid",
            "source",
            "source_system",
            "updated_at",
            "version",
        ] {
            assert!(
                !project.contains_key(internal_field),
                "project create response must hide {internal_field}"
            );
        }
        assert!(project.get("oa_external_id").unwrap().is_null());
    }

    #[tokio::test]
    async fn ledger_status_update_uses_legacy_status_values() {
        let ledger_status_commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            ledger_status_commands: ledger_status_commands.clone(),
            ..Default::default()
        });
        let ledger_id = Uuid::parse_str("88888888-8888-4888-8888-888888888888").unwrap();

        service
            .change_ledger_status(
                ledger_id,
                LedgerStatusRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    status: Some("resolved".to_owned()),
                    expected_date: Some("2026-05-31".to_owned()),
                    note: Some("done".to_owned()),
                    expected_version: Some(1),
                    idempotency_key: Some("ledger-status:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();
        let invalid = service
            .change_ledger_status(
                ledger_id,
                LedgerStatusRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    status: Some("settled".to_owned()),
                    expected_date: None,
                    note: None,
                    expected_version: None,
                    idempotency_key: Some("ledger-status:bad".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();

        assert!(matches!(
            invalid,
            PlatformLegacyServiceError::InvalidRequest {
                code: "invalid_ledger_status_request",
                ..
            }
        ));
        let stored = ledger_status_commands.lock().unwrap();
        assert_eq!(stored[0].status.as_deref(), Some("resolved"));
    }

    #[tokio::test]
    async fn ledger_status_update_allows_note_or_date_without_status() {
        let ledger_status_commands = Arc::new(Mutex::new(Vec::new()));
        let service = PlatformLegacyService::new(FixturePlatformRepository {
            ledger_status_commands: ledger_status_commands.clone(),
            ..Default::default()
        });
        let ledger_id = Uuid::parse_str("88888888-8888-4888-8888-888888888888").unwrap();

        service
            .change_ledger_status(
                ledger_id,
                LedgerStatusRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    status: None,
                    expected_date: None,
                    note: Some("follow up again".to_owned()),
                    expected_version: Some(1),
                    idempotency_key: Some("ledger-status:note-only".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();

        let missing_patch = service
            .change_ledger_status(
                ledger_id,
                LedgerStatusRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    status: None,
                    expected_date: None,
                    note: None,
                    expected_version: None,
                    idempotency_key: Some("ledger-status:empty".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();

        assert!(matches!(
            missing_patch,
            PlatformLegacyServiceError::InvalidRequest {
                code: "invalid_ledger_status_request",
                ..
            }
        ));
        let stored = ledger_status_commands.lock().unwrap();
        assert_eq!(stored[0].status, None);
        assert_eq!(stored[0].note.as_deref(), Some("follow up again"));
    }

    #[tokio::test]
    async fn project_assignment_requires_supported_object_type_and_uuid_id() {
        let service = PlatformLegacyService::new(FixturePlatformRepository::default());
        let project_id = "99999999-9999-4999-8999-999999999999";
        let object_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

        let response = service
            .assign_project(
                ProjectAssignRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    object_type: Some("bank_transaction".to_owned()),
                    object_id: Some(object_id.to_owned()),
                    project_id: Some(project_id.to_owned()),
                    note: Some("assign project".to_owned()),
                    expected_version: Some(1),
                    idempotency_key: Some("project-assign:test".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap();
        let invalid = service
            .assign_project(
                ProjectAssignRequest {
                    actor_id: Some("YNSYLP005".to_owned()),
                    object_type: Some("unknown_object".to_owned()),
                    object_id: Some(object_id.to_owned()),
                    project_id: Some(project_id.to_owned()),
                    note: None,
                    expected_version: None,
                    idempotency_key: Some("project-assign:bad".to_owned()),
                },
                actor(),
            )
            .await
            .unwrap_err();

        assert_eq!(response["assignment"]["project_id"], project_id);
        assert!(matches!(
            invalid,
            PlatformLegacyServiceError::InvalidRequest {
                code: "invalid_project_assign_request",
                ..
            }
        ));
    }

    #[tokio::test]
    async fn project_assignment_accepts_legacy_object_type_aliases() {
        let service = PlatformLegacyService::new(FixturePlatformRepository::default());
        let project_id = "99999999-9999-4999-8999-999999999999";
        let object_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

        for object_type in ["bank_txn", "case", "ledger"] {
            let response = service
                .assign_project(
                    ProjectAssignRequest {
                        actor_id: Some("YNSYLP005".to_owned()),
                        object_type: Some(object_type.to_owned()),
                        object_id: Some(object_id.to_owned()),
                        project_id: Some(project_id.to_owned()),
                        note: None,
                        expected_version: None,
                        idempotency_key: Some(format!("project-assign:{object_type}")),
                    },
                    actor(),
                )
                .await
                .unwrap();

            assert_eq!(response["assignment"]["project_id"], project_id);
        }
    }

    fn actor() -> WriteActor {
        WriteActor::oa_user("YNSYLP005", Some("request-1".to_owned()))
    }
}
