use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, thiserror::Error)]
pub enum WorkbenchWriteServiceError {
    #[error("invalid request: {message}")]
    InvalidRequest { code: &'static str, message: String },
    #[error("write conflict: {message}")]
    Conflict { code: &'static str, message: String },
    #[error("{resource} not found")]
    NotFound { resource: &'static str },
    #[error(transparent)]
    Repository(WorkbenchWriteRepositoryError),
}

#[derive(Debug, thiserror::Error)]
pub enum WorkbenchWriteRepositoryError {
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
pub trait WorkbenchWriteRepository: Send + Sync {
    async fn execute(
        &self,
        command: WorkbenchWriteCommand,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError>;
}

pub struct WorkbenchWriteService<R> {
    repository: R,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct WriteActor {
    pub actor_id: String,
    pub actor_type: String,
    pub request_id: Option<String>,
}

impl WriteActor {
    pub fn oa_user(actor_id: impl Into<String>, request_id: Option<String>) -> Self {
        Self {
            actor_id: actor_id.into(),
            actor_type: "oa_user".to_owned(),
            request_id,
        }
    }

    fn legacy_user(actor_id: impl Into<String>) -> Self {
        Self {
            actor_id: actor_id.into(),
            actor_type: "user".to_owned(),
            request_id: None,
        }
    }
}

impl<R> WorkbenchWriteService<R>
where
    R: WorkbenchWriteRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn confirm_link(
        &self,
        request: ConfirmLinkRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.confirm_link_as(request, actor).await
    }

    pub async fn confirm_link_as(
        &self,
        request: ConfirmLinkRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let row_ids = normalize_uuid_list(&request.row_ids, "invalid_row_ids")?;
        if row_ids.len() < 2 {
            return Err(invalid_request(
                "invalid_row_ids",
                "confirm_link requires at least two row_ids",
            ));
        }
        if amount_check_requires_note(request.amount_check.as_ref())
            && clean_optional(&request.note).is_none()
        {
            return Err(invalid_request(
                "amount_mismatch_note_required",
                "amount mismatch requires a note before confirming reconciliation",
            ));
        }
        let case_id = match clean_optional(&request.case_id) {
            Some(value) => parse_uuid("case_id", &value)?,
            None => Uuid::new_v4(),
        };
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::ConfirmLink {
                idempotency_key,
                actor,
                month,
                row_ids,
                case_id,
                note: clean_optional(&request.note),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn submit_no_oa_batch(
        &self,
        batch_id: Uuid,
        request: NoOaBatchSubmitRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.submit_no_oa_batch_as(batch_id, request, actor).await
    }

    pub async fn submit_no_oa_batch_as(
        &self,
        batch_id: Uuid,
        request: NoOaBatchSubmitRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let expected_version = request.expected_version.ok_or_else(|| {
            invalid_request(
                "missing_expected_version",
                "expected_version is required for no-OA batch submit",
            )
        })?;
        if expected_version <= 0 {
            return Err(invalid_request(
                "invalid_expected_version",
                "expected_version must be greater than zero",
            ));
        }
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::NoOaBatchSubmit {
                idempotency_key,
                actor,
                batch_id,
                expected_version,
                note: clean_optional(&request.note),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn withdraw_link(
        &self,
        request: RevokeLinkRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.revoke_link("withdraw_link", request, actor).await
    }

    pub async fn withdraw_link_as(
        &self,
        request: RevokeLinkRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        self.revoke_link("withdraw_link", request, actor).await
    }

    pub async fn cancel_link(
        &self,
        request: RevokeLinkRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.revoke_link("cancel_link", request, actor).await
    }

    pub async fn cancel_link_as(
        &self,
        request: RevokeLinkRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        self.revoke_link("cancel_link", request, actor).await
    }

    async fn revoke_link(
        &self,
        action: &'static str,
        request: RevokeLinkRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let expected_version = positive_expected_version(request.expected_version)?;
        let case_id = clean_optional(&request.case_id)
            .map(|value| parse_uuid("case_id", &value))
            .transpose()?;
        let row_ids =
            normalize_optional_row_ids(request.row_ids.as_deref(), request.row_id.as_deref())?;
        if case_id.is_none() && row_ids.is_empty() {
            return Err(invalid_request(
                "invalid_row_ids",
                "case_id or row_ids is required for link revoke",
            ));
        }
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::RevokeLink {
                action,
                idempotency_key,
                actor,
                month,
                case_id,
                row_ids,
                expected_version,
                note: clean_optional(&request.note).or_else(|| clean_optional(&request.comment)),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn apply_exception(
        &self,
        request: ExceptionApplyRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.apply_exception_as(request, actor).await
    }

    pub async fn apply_exception_as(
        &self,
        request: ExceptionApplyRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let row_ids = normalize_uuid_list(&request.row_ids, "invalid_row_ids")?;
        let scenario_code = required_text(&request.scenario_code, "missing_scenario_code")?;
        let action_code = required_text(&request.action_code, "missing_action_code")?;
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::ExceptionApply {
                idempotency_key,
                actor,
                month,
                row_ids,
                scenario_code,
                action_code,
                payload: request
                    .payload
                    .unwrap_or_else(|| Value::Object(Default::default())),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn mark_exception_as(
        &self,
        request: MarkExceptionRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let row_ids =
            normalize_optional_row_ids(request.row_ids.as_deref(), request.row_id.as_deref())?;
        self.apply_exception_as(
            ExceptionApplyRequest {
                month: request.month,
                row_ids: row_ids.into_iter().map(|value| value.to_string()).collect(),
                scenario_code: request.exception_code,
                action_code: "mark_exception".to_owned(),
                payload: Some(serde_json::json!({
                    "note": request.comment,
                    "source_action": "mark_exception"
                })),
                idempotency_key: request.idempotency_key,
                actor: request.actor,
            },
            actor,
        )
        .await
    }

    pub async fn bank_exception_as(
        &self,
        action: &'static str,
        request: BankExceptionRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let scenario_code = clean_optional(&request.relation_code)
            .or_else(|| clean_optional(&request.exception_code))
            .unwrap_or_else(|| "manual_review".to_owned());
        let relation_label =
            clean_optional(&request.relation_label).unwrap_or_else(|| scenario_code.clone());
        let row_ids =
            normalize_optional_row_ids(request.row_ids.as_deref(), request.row_id.as_deref())?;
        if row_ids.is_empty() {
            return Err(invalid_request(
                "invalid_row_ids",
                "row_id or row_ids is required",
            ));
        }
        self.apply_exception_as(
            ExceptionApplyRequest {
                month: request.month,
                row_ids: row_ids.into_iter().map(|value| value.to_string()).collect(),
                scenario_code,
                action_code: action.to_owned(),
                payload: Some(serde_json::json!({
                    "note": request.comment,
                    "relation_label": relation_label,
                    "source_action": action
                })),
                idempotency_key: request.idempotency_key,
                actor: request.actor,
            },
            actor,
        )
        .await
    }

    pub async fn special_reconciliation_action_as(
        &self,
        action: &'static str,
        request: CashSpecialRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let row_ids = normalize_uuid_list(&request.row_ids, "invalid_row_ids")?;
        let expected_version = positive_expected_version(request.expected_version)?;
        let special_metadata = special_metadata_for_action(action, &request)?;
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::SpecialReconciliationAction {
                action,
                idempotency_key,
                actor,
                month,
                row_ids,
                expected_version,
                note: clean_optional(&request.note).or_else(|| clean_optional(&request.comment)),
                special_metadata,
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn cancel_exception(
        &self,
        request: CancelExceptionRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.cancel_exception_as(request, actor).await
    }

    pub async fn cancel_exception_as(
        &self,
        request: CancelExceptionRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let expected_version = positive_expected_version(request.expected_version)?;
        let exception_case_id = clean_optional(&request.exception_case_id)
            .map(|value| parse_uuid("exception_case_id", &value))
            .transpose()?;
        let row_ids = normalize_optional_row_ids(request.row_ids.as_deref(), None)?;
        if exception_case_id.is_none() && row_ids.is_empty() {
            return Err(invalid_request(
                "invalid_row_ids",
                "exception_case_id or row_ids is required",
            ));
        }
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::ExceptionCancel {
                idempotency_key,
                actor,
                month,
                exception_case_id,
                row_ids,
                expected_version,
                comment: clean_optional(&request.comment),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn ignore_row(
        &self,
        request: RowOverrideRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.ignore_row_as(request, actor).await
    }

    pub async fn ignore_row_as(
        &self,
        request: RowOverrideRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let row_id = parse_uuid("row_id", request.row_id.trim())?;
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::IgnoreRow {
                idempotency_key,
                actor,
                month,
                row_id,
                comment: clean_optional(&request.comment),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn unignore_row(
        &self,
        request: RowOverrideRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.unignore_row_as(request, actor).await
    }

    pub async fn unignore_row_as(
        &self,
        request: RowOverrideRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let month = normalize_month(&request.month)?;
        let row_id = parse_uuid("row_id", request.row_id.trim())?;
        let expected_version = positive_expected_version(request.expected_version)?;
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::UnignoreRow {
                idempotency_key,
                actor,
                month,
                row_id,
                expected_version,
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn withdraw_no_oa_batch(
        &self,
        batch_id: Uuid,
        request: NoOaBatchWithdrawRequest,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let actor = legacy_actor(&request.actor)?;
        self.withdraw_no_oa_batch_as(batch_id, request, actor).await
    }

    pub async fn withdraw_no_oa_batch_as(
        &self,
        batch_id: Uuid,
        request: NoOaBatchWithdrawRequest,
        actor: WriteActor,
    ) -> Result<WorkbenchWriteResponse, WorkbenchWriteServiceError> {
        let idempotency_key = required_text(&request.idempotency_key, "missing_idempotency_key")?;
        let actor = validate_actor(actor)?;
        let expected_version = positive_expected_version(request.expected_version)?;
        let request_payload = trusted_request_payload(&request, &actor);

        self.repository
            .execute(WorkbenchWriteCommand::NoOaBatchWithdraw {
                idempotency_key,
                actor,
                batch_id,
                expected_version,
                reason: clean_optional(&request.reason).or_else(|| clean_optional(&request.note)),
                request_payload,
            })
            .await
            .map_err(WorkbenchWriteServiceError::from)
    }

    pub async fn bulk_submit_no_oa_batches(
        &self,
        request: NoOaBulkSubmitRequest,
    ) -> NoOaBulkSubmitResponse {
        self.bulk_submit_no_oa_batches_inner(request, None).await
    }

    pub async fn bulk_submit_no_oa_batches_as(
        &self,
        request: NoOaBulkSubmitRequest,
        actor: WriteActor,
    ) -> NoOaBulkSubmitResponse {
        self.bulk_submit_no_oa_batches_inner(request, Some(actor))
            .await
    }

    async fn bulk_submit_no_oa_batches_inner(
        &self,
        request: NoOaBulkSubmitRequest,
        trusted_actor: Option<WriteActor>,
    ) -> NoOaBulkSubmitResponse {
        let shared_actor = clean_optional(&request.actor);
        let mut results = Vec::new();
        let mut affected_months = Vec::new();

        for item in request.batches {
            let batch_id = match Uuid::parse_str(item.batch_id.trim()) {
                Ok(value) => value,
                Err(_) => {
                    results.push(NoOaBulkSubmitItemResponse::failed(
                        item.batch_id,
                        "invalid_uuid",
                    ));
                    continue;
                }
            };
            let actor = match &trusted_actor {
                Some(actor) => actor.clone(),
                None => {
                    let Some(actor) = clean_optional(&item.actor).or_else(|| shared_actor.clone())
                    else {
                        results.push(NoOaBulkSubmitItemResponse::failed(
                            batch_id.to_string(),
                            "missing_actor",
                        ));
                        continue;
                    };
                    match legacy_actor(&actor) {
                        Ok(actor) => actor,
                        Err(_) => {
                            results.push(NoOaBulkSubmitItemResponse::failed(
                                batch_id.to_string(),
                                "missing_actor",
                            ));
                            continue;
                        }
                    }
                }
            };
            match self
                .submit_no_oa_batch_as(
                    batch_id,
                    NoOaBatchSubmitRequest {
                        expected_version: item.expected_version,
                        note: item.note,
                        idempotency_key: item.idempotency_key,
                        actor: actor.actor_id.clone(),
                    },
                    actor,
                )
                .await
            {
                Ok(response) => {
                    affected_months.extend(response.affected_months.clone());
                    results.push(NoOaBulkSubmitItemResponse {
                        batch_id: batch_id.to_string(),
                        status: "submitted".to_owned(),
                        error: None,
                        response: Some(response),
                    });
                }
                Err(error) => results.push(NoOaBulkSubmitItemResponse::failed(
                    batch_id.to_string(),
                    service_error_code(&error),
                )),
            }
        }

        affected_months.sort();
        affected_months.dedup();
        let submitted = results
            .iter()
            .filter(|result| result.status == "submitted")
            .count();
        let failed = results.len().saturating_sub(submitted);

        NoOaBulkSubmitResponse {
            summary: NoOaBulkSubmitSummary { submitted, failed },
            results,
            affected_months,
        }
    }
}

#[derive(Debug, Clone)]
pub enum WorkbenchWriteCommand {
    ConfirmLink {
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        row_ids: Vec<Uuid>,
        case_id: Uuid,
        note: Option<String>,
        request_payload: Value,
    },
    NoOaBatchSubmit {
        idempotency_key: String,
        actor: WriteActor,
        batch_id: Uuid,
        expected_version: i32,
        note: Option<String>,
        request_payload: Value,
    },
    RevokeLink {
        action: &'static str,
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        case_id: Option<Uuid>,
        row_ids: Vec<Uuid>,
        expected_version: i32,
        note: Option<String>,
        request_payload: Value,
    },
    ExceptionApply {
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        row_ids: Vec<Uuid>,
        scenario_code: String,
        action_code: String,
        payload: Value,
        request_payload: Value,
    },
    SpecialReconciliationAction {
        action: &'static str,
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        row_ids: Vec<Uuid>,
        expected_version: i32,
        note: Option<String>,
        special_metadata: Value,
        request_payload: Value,
    },
    ExceptionCancel {
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        exception_case_id: Option<Uuid>,
        row_ids: Vec<Uuid>,
        expected_version: i32,
        comment: Option<String>,
        request_payload: Value,
    },
    IgnoreRow {
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        row_id: Uuid,
        comment: Option<String>,
        request_payload: Value,
    },
    UnignoreRow {
        idempotency_key: String,
        actor: WriteActor,
        month: String,
        row_id: Uuid,
        expected_version: i32,
        request_payload: Value,
    },
    NoOaBatchWithdraw {
        idempotency_key: String,
        actor: WriteActor,
        batch_id: Uuid,
        expected_version: i32,
        reason: Option<String>,
        request_payload: Value,
    },
}

impl WorkbenchWriteCommand {
    pub fn operation(&self) -> &'static str {
        match self {
            Self::ConfirmLink { .. } => "confirm_link",
            Self::NoOaBatchSubmit { .. } => "no_oa_batch.submit",
            Self::RevokeLink { action, .. } => action,
            Self::ExceptionApply { .. } => "exception.apply",
            Self::SpecialReconciliationAction { action, .. } => action,
            Self::ExceptionCancel { .. } => "exception.cancel",
            Self::IgnoreRow { .. } => "row_override.ignore",
            Self::UnignoreRow { .. } => "row_override.unignore",
            Self::NoOaBatchWithdraw { .. } => "no_oa_batch.withdraw",
        }
    }

    pub fn idempotency_key(&self) -> &str {
        match self {
            Self::ConfirmLink {
                idempotency_key, ..
            }
            | Self::NoOaBatchSubmit {
                idempotency_key, ..
            }
            | Self::RevokeLink {
                idempotency_key, ..
            }
            | Self::ExceptionApply {
                idempotency_key, ..
            }
            | Self::SpecialReconciliationAction {
                idempotency_key, ..
            }
            | Self::ExceptionCancel {
                idempotency_key, ..
            }
            | Self::IgnoreRow {
                idempotency_key, ..
            }
            | Self::UnignoreRow {
                idempotency_key, ..
            }
            | Self::NoOaBatchWithdraw {
                idempotency_key, ..
            } => idempotency_key,
        }
    }

    pub fn actor(&self) -> &WriteActor {
        match self {
            Self::ConfirmLink { actor, .. }
            | Self::NoOaBatchSubmit { actor, .. }
            | Self::RevokeLink { actor, .. }
            | Self::ExceptionApply { actor, .. }
            | Self::SpecialReconciliationAction { actor, .. }
            | Self::ExceptionCancel { actor, .. }
            | Self::IgnoreRow { actor, .. }
            | Self::UnignoreRow { actor, .. }
            | Self::NoOaBatchWithdraw { actor, .. } => actor,
        }
    }

    pub fn actor_id(&self) -> &str {
        &self.actor().actor_id
    }

    pub fn request_payload(&self) -> &Value {
        match self {
            Self::ConfirmLink {
                request_payload, ..
            }
            | Self::NoOaBatchSubmit {
                request_payload, ..
            }
            | Self::RevokeLink {
                request_payload, ..
            }
            | Self::ExceptionApply {
                request_payload, ..
            }
            | Self::SpecialReconciliationAction {
                request_payload, ..
            }
            | Self::ExceptionCancel {
                request_payload, ..
            }
            | Self::IgnoreRow {
                request_payload, ..
            }
            | Self::UnignoreRow {
                request_payload, ..
            }
            | Self::NoOaBatchWithdraw {
                request_payload, ..
            } => request_payload,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ConfirmLinkRequest {
    pub month: String,
    pub row_ids: Vec<String>,
    pub case_id: Option<String>,
    pub note: Option<String>,
    pub amount_check: Option<Value>,
    #[serde(default)]
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct NoOaBatchSubmitRequest {
    pub expected_version: Option<i32>,
    pub note: Option<String>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RevokeLinkRequest {
    pub month: String,
    pub row_ids: Option<Vec<String>>,
    pub row_id: Option<String>,
    pub case_id: Option<String>,
    pub expected_version: Option<i32>,
    pub note: Option<String>,
    pub comment: Option<String>,
    #[serde(default)]
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ExceptionApplyRequest {
    pub month: String,
    pub row_ids: Vec<String>,
    pub scenario_code: String,
    pub action_code: String,
    pub payload: Option<Value>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MarkExceptionRequest {
    pub month: String,
    pub row_ids: Option<Vec<String>>,
    pub row_id: Option<String>,
    pub exception_code: String,
    pub comment: Option<String>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BankExceptionRequest {
    pub month: String,
    pub row_id: Option<String>,
    pub row_ids: Option<Vec<String>>,
    pub relation_code: Option<String>,
    pub relation_label: Option<String>,
    pub exception_code: Option<String>,
    pub comment: Option<String>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CashSpecialRequest {
    pub month: String,
    pub row_ids: Vec<String>,
    pub cash_amount: Option<String>,
    pub ticket_cost_amount: Option<String>,
    pub project_id: Option<String>,
    pub project_name: Option<String>,
    pub note: Option<String>,
    pub comment: Option<String>,
    pub expected_version: Option<i32>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CancelExceptionRequest {
    pub month: String,
    pub row_ids: Option<Vec<String>>,
    pub exception_case_id: Option<String>,
    pub expected_version: Option<i32>,
    pub comment: Option<String>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct RowOverrideRequest {
    pub month: String,
    pub row_id: String,
    pub comment: Option<String>,
    pub expected_version: Option<i32>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct NoOaBatchWithdrawRequest {
    pub expected_version: Option<i32>,
    pub reason: Option<String>,
    pub note: Option<String>,
    pub idempotency_key: String,
    #[serde(default)]
    pub actor: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct NoOaBulkSubmitRequest {
    pub actor: Option<String>,
    pub batches: Vec<NoOaBulkSubmitItemRequest>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct NoOaBulkSubmitItemRequest {
    pub batch_id: String,
    pub expected_version: Option<i32>,
    pub note: Option<String>,
    pub idempotency_key: String,
    pub actor: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct WorkbenchWriteResponse {
    pub success: bool,
    pub action: String,
    pub idempotent_replay: bool,
    pub affected_row_ids: Vec<String>,
    pub affected_months: Vec<String>,
    pub case_id: Option<String>,
    pub exception_case_id: Option<String>,
    pub batch_id: Option<String>,
    pub row_version: Option<i32>,
    pub rebuild_task_id: String,
    pub outbox_event_id: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct NoOaBulkSubmitResponse {
    pub summary: NoOaBulkSubmitSummary,
    pub results: Vec<NoOaBulkSubmitItemResponse>,
    pub affected_months: Vec<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct NoOaBulkSubmitSummary {
    pub submitted: usize,
    pub failed: usize,
}

#[derive(Debug, Clone, Serialize)]
pub struct NoOaBulkSubmitItemResponse {
    pub batch_id: String,
    pub status: String,
    pub error: Option<String>,
    pub response: Option<WorkbenchWriteResponse>,
}

impl NoOaBulkSubmitItemResponse {
    fn failed(batch_id: String, error: &str) -> Self {
        Self {
            batch_id,
            status: "failed".to_owned(),
            error: Some(error.to_owned()),
            response: None,
        }
    }
}

fn invalid_request(code: &'static str, message: impl Into<String>) -> WorkbenchWriteServiceError {
    WorkbenchWriteServiceError::InvalidRequest {
        code,
        message: message.into(),
    }
}

impl From<WorkbenchWriteRepositoryError> for WorkbenchWriteServiceError {
    fn from(error: WorkbenchWriteRepositoryError) -> Self {
        match error {
            WorkbenchWriteRepositoryError::Database(error) => {
                WorkbenchWriteServiceError::Repository(WorkbenchWriteRepositoryError::Database(
                    error,
                ))
            }
            WorkbenchWriteRepositoryError::IdempotencyConflict => Self::Conflict {
                code: "idempotency_key_reused_with_different_payload",
                message: "idempotency key was reused with a different payload".to_owned(),
            },
            WorkbenchWriteRepositoryError::Conflict { code, message } => {
                Self::Conflict { code, message }
            }
            WorkbenchWriteRepositoryError::NotFound { resource } => Self::NotFound { resource },
        }
    }
}

fn legacy_actor(value: &str) -> Result<WriteActor, WorkbenchWriteServiceError> {
    Ok(WriteActor::legacy_user(required_text(
        value,
        "missing_actor",
    )?))
}

fn validate_actor(actor: WriteActor) -> Result<WriteActor, WorkbenchWriteServiceError> {
    if actor.actor_id.trim().is_empty() {
        return Err(invalid_request(
            "missing_actor",
            "required field is missing",
        ));
    }
    if actor.actor_type.trim().is_empty() {
        return Err(invalid_request(
            "missing_actor_type",
            "actor_type is required for write audit",
        ));
    }
    Ok(WriteActor {
        actor_id: actor.actor_id.trim().to_owned(),
        actor_type: actor.actor_type.trim().to_owned(),
        request_id: actor
            .request_id
            .as_deref()
            .map(str::trim)
            .filter(|value| !value.is_empty())
            .map(ToOwned::to_owned),
    })
}

fn trusted_request_payload<T>(request: &T, actor: &WriteActor) -> Value
where
    T: Serialize,
{
    let mut payload = serde_json::to_value(request).unwrap_or(Value::Null);
    if let Value::Object(object) = &mut payload {
        object.insert(
            "trusted_actor".to_owned(),
            serde_json::json!({
                "actor_id": &actor.actor_id,
                "actor_type": &actor.actor_type,
            }),
        );
        if let Some(request_id) = &actor.request_id {
            object.insert("request_id".to_owned(), Value::String(request_id.clone()));
            object.insert("trace_id".to_owned(), Value::String(request_id.clone()));
        }
    }
    payload
}

fn required_text(
    value: &str,
    missing_code: &'static str,
) -> Result<String, WorkbenchWriteServiceError> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(invalid_request(missing_code, "required field is missing"));
    }
    Ok(trimmed.to_owned())
}

fn clean_optional(value: &Option<String>) -> Option<String> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn positive_expected_version(value: Option<i32>) -> Result<i32, WorkbenchWriteServiceError> {
    let expected_version = value.ok_or_else(|| {
        invalid_request(
            "missing_expected_version",
            "expected_version is required for this write operation",
        )
    })?;
    if expected_version <= 0 {
        return Err(invalid_request(
            "invalid_expected_version",
            "expected_version must be greater than zero",
        ));
    }
    Ok(expected_version)
}

fn normalize_month(value: &str) -> Result<String, WorkbenchWriteServiceError> {
    let trimmed = value.trim();
    let valid = trimmed.len() == 7
        && trimmed.as_bytes().get(4) == Some(&b'-')
        && trimmed[..4].chars().all(|ch| ch.is_ascii_digit())
        && trimmed[5..].chars().all(|ch| ch.is_ascii_digit())
        && matches!(trimmed[5..].parse::<u8>(), Ok(1..=12));
    if !valid {
        return Err(invalid_request("invalid_month", "month must use YYYY-MM"));
    }
    Ok(trimmed.to_owned())
}

fn normalize_uuid_list(
    values: &[String],
    code: &'static str,
) -> Result<Vec<Uuid>, WorkbenchWriteServiceError> {
    let mut parsed = Vec::new();
    for value in values {
        let trimmed = value.trim();
        if trimmed.is_empty() {
            continue;
        }
        parsed.push(
            parse_uuid("row_id", trimmed)
                .map_err(|_| invalid_request(code, "row_ids must contain valid UUID values"))?,
        );
    }
    parsed.sort();
    parsed.dedup();
    if parsed.is_empty() {
        return Err(invalid_request(code, "row_ids is required"));
    }
    Ok(parsed)
}

fn normalize_optional_row_ids(
    row_ids: Option<&[String]>,
    row_id: Option<&str>,
) -> Result<Vec<Uuid>, WorkbenchWriteServiceError> {
    let mut values = row_ids.unwrap_or(&[]).to_vec();
    if let Some(row_id) = row_id {
        values.push(row_id.to_owned());
    }
    if values.is_empty() {
        return Ok(vec![]);
    }
    normalize_uuid_list(&values, "invalid_row_ids")
}

fn parse_uuid(field: &'static str, value: &str) -> Result<Uuid, WorkbenchWriteServiceError> {
    Uuid::parse_str(value)
        .map_err(|_| invalid_request("invalid_uuid", format!("{field} must be a valid UUID")))
}

fn amount_check_requires_note(amount_check: Option<&Value>) -> bool {
    let Some(amount_check) = amount_check else {
        return false;
    };
    amount_check
        .get("requires_note")
        .and_then(Value::as_bool)
        .unwrap_or(false)
        || matches!(
            amount_check.get("status").and_then(Value::as_str),
            Some("mismatch" | "difference" | "unbalanced")
        )
}

fn special_metadata_for_action(
    action: &str,
    request: &CashSpecialRequest,
) -> Result<Value, WorkbenchWriteServiceError> {
    match action {
        "confirm_cash_pass_through" => Ok(serde_json::json!({
            "special_type": "cash_pass_through",
            "cash_amount": clean_optional(&request.cash_amount).unwrap_or_else(|| "0.00".to_owned()),
            "ticket_cost_amount": "0.00",
            "cost_policy": "exclude_all",
            "note": clean_optional(&request.note).or_else(|| clean_optional(&request.comment)).unwrap_or_default()
        })),
        "confirm_cash_ticket_purchase" => {
            let ticket_cost_amount =
                clean_optional(&request.ticket_cost_amount).ok_or_else(|| {
                    invalid_request(
                        "invalid_cash_ticket_purchase_request",
                        "ticket_cost_amount is required",
                    )
                })?;
            if ticket_cost_amount != "0" && ticket_cost_amount != "0.00" {
                let has_project = clean_optional(&request.project_id).is_some()
                    || clean_optional(&request.project_name).is_some();
                if !has_project {
                    return Err(invalid_request(
                        "invalid_cash_ticket_purchase_request",
                        "project_id or project_name is required when ticket_cost_amount is greater than 0",
                    ));
                }
            }
            Ok(serde_json::json!({
                "special_type": "cash_ticket_purchase",
                "cash_amount": clean_optional(&request.cash_amount).unwrap_or_else(|| "0.00".to_owned()),
                "ticket_cost_amount": ticket_cost_amount,
                "project_id": clean_optional(&request.project_id).unwrap_or_default(),
                "project_name": clean_optional(&request.project_name).unwrap_or_default(),
                "cost_policy": "include_ticket_cost_only",
                "note": clean_optional(&request.note).or_else(|| clean_optional(&request.comment)).unwrap_or_default()
            }))
        }
        "cancel_cash_special" => Ok(serde_json::json!({})),
        _ => Err(invalid_request(
            "invalid_write_action",
            format!("unsupported special reconciliation action: {action}"),
        )),
    }
}

fn service_error_code(error: &WorkbenchWriteServiceError) -> &'static str {
    match error {
        WorkbenchWriteServiceError::InvalidRequest { code, .. }
        | WorkbenchWriteServiceError::Conflict { code, .. } => code,
        WorkbenchWriteServiceError::NotFound { resource } => match *resource {
            "no_oa_bank_batch" => "no_oa_bank_batch_not_found",
            "reconciliation_case" => "reconciliation_case_not_found",
            "workbench_row" => "workbench_row_not_found",
            "exception_case" => "exception_case_not_found",
            _ => "not_found",
        },
        WorkbenchWriteServiceError::Repository(_) => "database_unavailable",
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use super::*;
    use serde_json::json;

    #[derive(Clone, Default)]
    struct RecordingRepository {
        commands: Arc<Mutex<Vec<WorkbenchWriteCommand>>>,
        response: Arc<Mutex<Option<WorkbenchWriteResponse>>>,
    }

    #[async_trait]
    impl WorkbenchWriteRepository for RecordingRepository {
        async fn execute(
            &self,
            command: WorkbenchWriteCommand,
        ) -> Result<WorkbenchWriteResponse, WorkbenchWriteRepositoryError> {
            self.commands.lock().unwrap().push(command);
            Ok(self
                .response
                .lock()
                .unwrap()
                .clone()
                .unwrap_or_else(|| response("confirm_link")))
        }
    }

    #[tokio::test]
    async fn confirm_link_requires_idempotency_key_before_repository_call() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let error = service
            .confirm_link(ConfirmLinkRequest {
                month: "2026-05".to_owned(),
                row_ids: vec![uuid(1).to_string(), uuid(2).to_string()],
                case_id: None,
                note: None,
                amount_check: None,
                idempotency_key: " ".to_owned(),
                actor: "YNSYLP005".to_owned(),
            })
            .await
            .unwrap_err();

        assert_error_code(error, "missing_idempotency_key");
        assert!(repository.commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn confirm_link_requires_note_for_mismatched_amounts() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let error = service
            .confirm_link(ConfirmLinkRequest {
                month: "2026-05".to_owned(),
                row_ids: vec![uuid(1).to_string(), uuid(2).to_string()],
                case_id: None,
                note: None,
                amount_check: Some(json!({"status": "mismatch", "requires_note": true})),
                idempotency_key: "confirm:2026-05:1".to_owned(),
                actor: "YNSYLP005".to_owned(),
            })
            .await
            .unwrap_err();

        assert_error_code(error, "amount_mismatch_note_required");
        assert!(repository.commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn confirm_link_builds_transactional_command_for_repository() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let output = service
            .confirm_link(ConfirmLinkRequest {
                month: "2026-05".to_owned(),
                row_ids: vec![uuid(1).to_string(), uuid(2).to_string()],
                case_id: Some(uuid(99).to_string()),
                note: Some("已核对差额".to_owned()),
                amount_check: Some(json!({"status": "mismatch", "requires_note": true})),
                idempotency_key: "confirm:2026-05:1".to_owned(),
                actor: "YNSYLP005".to_owned(),
            })
            .await
            .unwrap();

        assert_eq!(output.action, "confirm_link");
        let commands = repository.commands.lock().unwrap();
        assert_eq!(commands.len(), 1);
        match &commands[0] {
            WorkbenchWriteCommand::ConfirmLink {
                idempotency_key,
                actor,
                month,
                row_ids,
                case_id,
                note,
                request_payload,
            } => {
                assert_eq!(idempotency_key, "confirm:2026-05:1");
                assert_eq!(actor.actor_id, "YNSYLP005");
                assert_eq!(actor.actor_type, "user");
                assert_eq!(month, "2026-05");
                assert_eq!(row_ids, &vec![uuid(1), uuid(2)]);
                assert_eq!(case_id, &uuid(99));
                assert_eq!(note.as_deref(), Some("已核对差额"));
                assert_eq!(request_payload["idempotency_key"], "confirm:2026-05:1");
            }
            _ => panic!("expected confirm command"),
        }
    }

    #[tokio::test]
    async fn trusted_actor_context_is_recorded_in_command_payload() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());
        let actor = WriteActor::oa_user("session_user", Some("trace-001".to_owned()));

        service
            .confirm_link_as(
                ConfirmLinkRequest {
                    month: "2026-05".to_owned(),
                    row_ids: vec![uuid(1).to_string(), uuid(2).to_string()],
                    case_id: Some(uuid(99).to_string()),
                    note: Some("已核对".to_owned()),
                    amount_check: None,
                    idempotency_key: "confirm:trusted-actor:1".to_owned(),
                    actor: "session_user".to_owned(),
                },
                actor,
            )
            .await
            .unwrap();

        let commands = repository.commands.lock().unwrap();
        match &commands[0] {
            WorkbenchWriteCommand::ConfirmLink {
                actor,
                request_payload,
                ..
            } => {
                assert_eq!(actor.actor_id, "session_user");
                assert_eq!(actor.actor_type, "oa_user");
                assert_eq!(actor.request_id.as_deref(), Some("trace-001"));
                assert_eq!(request_payload["trusted_actor"]["actor_id"], "session_user");
                assert_eq!(request_payload["trusted_actor"]["actor_type"], "oa_user");
                assert_eq!(request_payload["request_id"], "trace-001");
                assert_eq!(request_payload["trace_id"], "trace-001");
            }
            _ => panic!("expected confirm command"),
        }
    }

    #[tokio::test]
    async fn no_oa_submit_requires_expected_version() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let error = service
            .submit_no_oa_batch(
                uuid(40),
                NoOaBatchSubmitRequest {
                    expected_version: None,
                    note: None,
                    idempotency_key: "no-oa:submit:1".to_owned(),
                    actor: "YNSYLP005".to_owned(),
                },
            )
            .await
            .unwrap_err();

        assert_error_code(error, "missing_expected_version");
        assert!(repository.commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn no_oa_bulk_submit_requires_actor_from_request_or_item() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let output = service
            .bulk_submit_no_oa_batches(NoOaBulkSubmitRequest {
                actor: None,
                batches: vec![NoOaBulkSubmitItemRequest {
                    batch_id: uuid(10).to_string(),
                    expected_version: Some(1),
                    note: None,
                    idempotency_key: "no-oa:submit:10".to_owned(),
                    actor: None,
                }],
            })
            .await;

        assert_eq!(output.summary.submitted, 0);
        assert_eq!(output.summary.failed, 1);
        assert_eq!(output.results[0].error.as_deref(), Some("missing_actor"));
        assert!(repository.commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn cancel_exception_requires_expected_version() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let error = service
            .cancel_exception(CancelExceptionRequest {
                month: "2026-05".to_owned(),
                row_ids: Some(vec![uuid(1).to_string()]),
                exception_case_id: None,
                expected_version: None,
                comment: None,
                idempotency_key: "exception:cancel:1".to_owned(),
                actor: "YNSYLP005".to_owned(),
            })
            .await
            .unwrap_err();

        assert_error_code(error, "missing_expected_version");
        assert!(repository.commands.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn ignore_row_builds_override_command() {
        let repository = RecordingRepository::default();
        let service = WorkbenchWriteService::new(repository.clone());

        let output = service
            .ignore_row(RowOverrideRequest {
                month: "2026-05".to_owned(),
                row_id: uuid(10).to_string(),
                comment: Some("重复导入".to_owned()),
                expected_version: None,
                idempotency_key: "ignore:row:1".to_owned(),
                actor: "YNSYLP005".to_owned(),
            })
            .await
            .unwrap();

        assert_eq!(output.action, "confirm_link");
        let commands = repository.commands.lock().unwrap();
        assert_eq!(commands.len(), 1);
        match &commands[0] {
            WorkbenchWriteCommand::IgnoreRow {
                idempotency_key,
                actor,
                month,
                row_id,
                comment,
                ..
            } => {
                assert_eq!(idempotency_key, "ignore:row:1");
                assert_eq!(actor.actor_id, "YNSYLP005");
                assert_eq!(actor.actor_type, "user");
                assert_eq!(month, "2026-05");
                assert_eq!(row_id, &uuid(10));
                assert_eq!(comment.as_deref(), Some("重复导入"));
            }
            _ => panic!("expected ignore row command"),
        }
    }

    fn response(action: &str) -> WorkbenchWriteResponse {
        WorkbenchWriteResponse {
            success: true,
            action: action.to_owned(),
            idempotent_replay: false,
            affected_row_ids: vec![],
            affected_months: vec!["2026-05".to_owned()],
            case_id: Some(uuid(99).to_string()),
            exception_case_id: None,
            batch_id: None,
            row_version: Some(1),
            rebuild_task_id: uuid(70).to_string(),
            outbox_event_id: uuid(71).to_string(),
            message: "ok".to_owned(),
        }
    }

    fn assert_error_code(error: WorkbenchWriteServiceError, expected: &str) {
        match error {
            WorkbenchWriteServiceError::InvalidRequest { code, .. } => assert_eq!(code, expected),
            other => panic!("expected invalid request error, got {other:?}"),
        }
    }

    fn uuid(seed: u128) -> Uuid {
        Uuid::from_u128(seed)
    }
}
