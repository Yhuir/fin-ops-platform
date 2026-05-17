use async_trait::async_trait;
use serde_json::{json, Value};
use sqlx::{PgPool, Row, Transaction};
use uuid::Uuid;

use crate::repositories::workbench_settings_projection::{
    workbench_settings_value_from_raw, ProjectSettingSnapshot,
};
use crate::services::platform_legacy::{
    BackgroundJobAcknowledgeCommand, ImportSessionBatch, ImportSessionFile,
    ImportSessionProjection, LedgerListRequest, LedgerStatusCommand, MatchingResultRow,
    MatchingResultsRequest, PlatformJobCommand, PlatformJobCommandResult, PlatformLegacyRepository,
    PlatformLegacyRepositoryError, ProjectAssignmentCommand, ProjectDeleteCommand,
    ProjectProfileCommand, ProjectWriteProjection, ReminderListRequest, WorkbenchSettingsCommand,
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
        .bind(job_command_outbox_event_type(&command.operation))
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

        insert_data_reset_request_if_needed(&mut tx, &command, task_id, outbox_event_id).await?;
        insert_reminder_run_if_needed(&mut tx, &command, task_id, outbox_event_id).await?;

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

    async fn acknowledge_background_job(
        &self,
        command: BackgroundJobAcknowledgeCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "background_job.acknowledge",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }

        let task = sqlx::query(BACKGROUND_JOB_ACK_TARGET_SQL)
            .bind(command.job_id)
            .bind(&command.actor.actor_id)
            .fetch_optional(&mut *tx)
            .await?;
        if task.is_none() {
            return Err(PlatformLegacyRepositoryError::NotFound {
                resource: "background_job",
            });
        }

        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        sqlx::query(
            r#"
            insert into job.worker_task_acknowledgements (
              task_id,
              actor_id,
              acknowledged_at,
              reason,
              idempotency_key,
              trace_id,
              created_by,
              updated_by
            )
            values ($1, $2, now(), $3, $4, $5, $2, $2)
            on conflict (task_id, actor_id) do update
            set acknowledged_at = excluded.acknowledged_at,
                reason = excluded.reason,
                idempotency_key = excluded.idempotency_key,
                trace_id = excluded.trace_id,
                updated_by = excluded.updated_by,
                updated_at = now()
            "#,
        )
        .bind(command.job_id)
        .bind(&command.actor.actor_id)
        .bind(&command.reason)
        .bind(&command.idempotency_key)
        .bind(&trace_id)
        .execute(&mut *tx)
        .await
        .map_err(map_sqlx_error)?;

        insert_generic_audit_event(
            &mut tx,
            "background_job.acknowledged",
            "acknowledge",
            "worker_task",
            command.job_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            json!({"acknowledged": true, "reason": command.reason}),
            json!({"operation": "background_job.acknowledge"}),
        )
        .await?;

        let task = sqlx::query(BACKGROUND_JOB_ACK_TARGET_SQL)
            .bind(command.job_id)
            .bind(&command.actor.actor_id)
            .fetch_one(&mut *tx)
            .await?;
        let job = worker_task_ack_json(&task);
        record_idempotency_value(
            &mut tx,
            "background_job.acknowledge",
            &command.idempotency_key,
            &command.request_payload,
            &job,
            "worker_task",
            command.job_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(job)
    }

    async fn current_workbench_settings(&self) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        let settings = current_settings_projection_value(&mut tx).await?;
        tx.commit().await?;
        Ok(settings)
    }

    async fn save_workbench_settings(
        &self,
        command: WorkbenchSettingsCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "settings.save",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }
        if let Some(expected_version) = command.expected_version {
            let version = current_settings_version(&mut tx).await?;
            if version != expected_version {
                return Err(PlatformLegacyRepositoryError::Conflict {
                    code: "settings_version_conflict",
                    message: "settings version does not match expected_version".to_owned(),
                });
            }
        }
        let profile_id = Uuid::new_v4();
        let version = current_settings_version(&mut tx).await? + 1;
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        sqlx::query(
            r#"
            update app.settings_profiles
            set status = 'superseded',
                updated_by = $1,
                updated_at = now()
            where settings_key = 'workbench' and status = 'active'
            "#,
        )
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
        .await?;
        sqlx::query(
            r#"
            insert into app.settings_profiles (
              id,
              settings_key,
              version,
              settings_payload,
              status,
              idempotency_key,
              created_by,
              updated_by
            )
            values ($1, 'workbench', $2, $3, 'active', $4, $5, $5)
            "#,
        )
        .bind(profile_id)
        .bind(version)
        .bind(&command.settings)
        .bind(&command.idempotency_key)
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
        .await
        .map_err(map_sqlx_error)?;
        let response = current_settings_projection_value(&mut tx).await?;
        insert_generic_audit_event(
            &mut tx,
            "settings.updated",
            "update",
            "settings_profile",
            profile_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            response.clone(),
            json!({"operation": "settings.save", "version": version}),
        )
        .await?;
        insert_identity_role_provisioning_request_if_needed(
            &mut tx, profile_id, version, &response, &command, &trace_id,
        )
        .await?;
        record_idempotency_value(
            &mut tx,
            "settings.save",
            &command.idempotency_key,
            &command.request_payload,
            &response,
            "settings_profile",
            profile_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(response)
    }

    async fn create_project_profile(
        &self,
        command: ProjectProfileCommand,
    ) -> Result<ProjectWriteProjection, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "project_profile.upsert",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(ProjectWriteProjection {
                project: existing["project"].clone(),
                settings: existing["settings"].clone(),
                hub: existing["hub"].clone(),
            });
        }
        let project_id = Uuid::new_v4();
        if let Some(expected_version) = command.expected_version {
            let existing_version =
                project_profile_version_by_code(&mut tx, &command.project_code).await?;
            if existing_version != Some(expected_version as i32) {
                return Err(PlatformLegacyRepositoryError::Conflict {
                    code: "project_profile_version_conflict",
                    message: "project profile version does not match expected_version".to_owned(),
                });
            }
        }
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        let row = sqlx::query(PROJECT_PROFILE_INSERT_SQL)
            .bind(project_id)
            .bind(&command.project_code)
            .bind(&command.project_name)
            .bind(&command.project_status)
            .bind(&command.department_name)
            .bind(&command.owner_name)
            .bind(&command.idempotency_key)
            .bind(&command.actor.actor_id)
            .fetch_one(&mut *tx)
            .await
            .map_err(map_sqlx_error)?;
        let project_id: Uuid = row.try_get("id")?;
        let project = find_project_value(&mut tx, project_id).await?.ok_or(
            PlatformLegacyRepositoryError::NotFound {
                resource: "project",
            },
        )?;
        insert_generic_audit_event(
            &mut tx,
            "project_profile.upserted",
            "upsert",
            "project_profile",
            project_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            project.clone(),
            json!({"operation": "project_profile.upsert", "actor_id": command.actor_id}),
        )
        .await?;
        let settings = current_settings_projection_value(&mut tx).await?;
        let hub = project_hub_value(&mut tx).await?;
        let response = json!({"project": project, "settings": settings, "hub": hub});
        record_idempotency_value(
            &mut tx,
            "project_profile.upsert",
            &command.idempotency_key,
            &command.request_payload,
            &response,
            "project_profile",
            project_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(ProjectWriteProjection {
            project: response["project"].clone(),
            settings: response["settings"].clone(),
            hub: response["hub"].clone(),
        })
    }

    async fn deactivate_project_profile(
        &self,
        command: ProjectDeleteCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "project_profile.deactivate",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }
        let result = sqlx::query(
            r#"
            update app.project_profiles
            set project_status = 'inactive',
                deactivated_at = coalesce(deactivated_at, now()),
                deactivated_by = $2,
                version = version + 1,
                updated_by = $2,
                updated_at = now()
            where id = $1
              and ($3::integer is null or version = $3)
            "#,
        )
        .bind(command.project_id)
        .bind(&command.actor.actor_id)
        .bind(command.expected_version.map(|value| value as i32))
        .execute(&mut *tx)
        .await?;
        if result.rows_affected() == 0 {
            if project_exists(&mut tx, command.project_id).await? {
                return Err(PlatformLegacyRepositoryError::Conflict {
                    code: "project_profile_version_conflict",
                    message: "project profile version does not match expected_version".to_owned(),
                });
            }
            return Err(PlatformLegacyRepositoryError::NotFound {
                resource: "project",
            });
        }
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        let settings = current_settings_projection_value(&mut tx).await?;
        insert_generic_audit_event(
            &mut tx,
            "project_profile.deactivated",
            "deactivate",
            "project_profile",
            command.project_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            settings.clone(),
            json!({"operation": "project_profile.deactivate"}),
        )
        .await?;
        record_idempotency_value(
            &mut tx,
            "project_profile.deactivate",
            &command.idempotency_key,
            &command.request_payload,
            &settings,
            "project_profile",
            command.project_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(settings)
    }

    async fn list_project_hub(&self) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        let hub = project_hub_value(&mut tx).await?;
        tx.commit().await?;
        Ok(hub)
    }

    async fn resolve_project_id(
        &self,
        project_id: &str,
    ) -> Result<Option<Uuid>, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        let resolved = resolve_project_id_value(&mut tx, project_id).await?;
        tx.commit().await?;
        Ok(resolved)
    }

    async fn find_project_detail(
        &self,
        project_id: Uuid,
    ) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        let project = find_project_detail_value(&mut tx, project_id).await?;
        tx.commit().await?;
        Ok(project)
    }

    async fn assign_project(
        &self,
        command: ProjectAssignmentCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "project.assign",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }
        if find_project_value(&mut tx, command.project_id)
            .await?
            .is_none()
            || !project_assignment_target_exists(&mut tx, &command.object_type, command.object_id)
                .await?
        {
            return Err(PlatformLegacyRepositoryError::NotFound {
                resource: "project_or_object",
            });
        }
        let assignment_id = Uuid::new_v4();
        sqlx::query(
            r#"
            update app.project_assignments
            set status = 'superseded',
                version = version + 1,
                updated_by = $3,
                updated_at = now()
            where object_type = $1
              and object_id = $2
              and status = 'active'
            "#,
        )
        .bind(&command.object_type)
        .bind(command.object_id)
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
        .await?;
        sqlx::query(
            r#"
            insert into app.project_assignments (
              id,
              object_type,
              object_id,
              project_id,
              status,
              note,
              idempotency_key,
              created_by,
              updated_by
            )
            values ($1, $2, $3, $4, 'active', $5, $6, $7, $7)
            "#,
        )
        .bind(assignment_id)
        .bind(&command.object_type)
        .bind(command.object_id)
        .bind(command.project_id)
        .bind(&command.note)
        .bind(&command.idempotency_key)
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
        .await
        .map_err(map_sqlx_error)?;
        let project = find_project_value(&mut tx, command.project_id)
            .await?
            .ok_or(PlatformLegacyRepositoryError::NotFound {
                resource: "project",
            })?;
        let project_display_id = project
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or_else(|| project["project_uuid"].as_str().unwrap_or_default())
            .to_owned();
        update_project_assignment_target_project(
            &mut tx,
            &command.object_type,
            command.object_id,
            command.project_id,
            &project_display_id,
            &command.actor.actor_id,
        )
        .await?;
        let internal_assignment = json!({
            "assignment_id": assignment_id,
            "id": assignment_id,
            "object_type": command.object_type,
            "object_id": command.object_id,
            "project_id": command.project_id,
            "project_uuid": command.project_id,
            "status": "active",
            "note": command.note,
            "actor_id": command.actor_id
        });
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        insert_generic_audit_event(
            &mut tx,
            "project.assigned",
            "assign",
            "project_assignment",
            assignment_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            internal_assignment.clone(),
            json!({
                "operation": "project.assign",
                "expected_version": command.expected_version
            }),
        )
        .await?;
        sqlx::query(PROJECT_ASSIGNMENT_EVENT_SQL)
            .bind(command.project_id)
            .bind(assignment_id)
            .bind(&internal_assignment)
            .bind(&command.idempotency_key)
            .bind(&command.actor.actor_id)
            .execute(&mut *tx)
            .await
            .map_err(map_sqlx_error)?;
        let detail = find_project_detail_value(&mut tx, command.project_id)
            .await?
            .unwrap_or_else(|| json!({"project": project}));
        let assigned_object_id = command.object_id.to_string();
        let assignment = detail["assignments"]
            .as_array()
            .and_then(|assignments| {
                assignments.iter().find(|assignment| {
                    assignment.get("object_type").and_then(Value::as_str)
                        == Some(command.object_type.as_str())
                        && assignment.get("object_id").and_then(Value::as_str)
                            == Some(assigned_object_id.as_str())
                })
            })
            .cloned()
            .unwrap_or_else(|| {
                json!({
                    "id": "project_assign_0001",
                    "object_type": command.object_type,
                    "object_id": command.object_id,
                    "project_id": command.project_id,
                    "note": command.note,
                    "assigned_by": command.actor_id,
                    "source": "manual"
                })
            });
        let response = json!({
            "assignment": assignment,
            "project": detail["project"].clone(),
            "summary": detail["summary"].clone(),
            "assignments": detail["assignments"].clone(),
            "objects": detail["objects"].clone()
        });
        record_idempotency_value(
            &mut tx,
            "project.assign",
            &command.idempotency_key,
            &command.request_payload,
            &response,
            "project_assignment",
            assignment_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(response)
    }

    async fn list_ledgers(
        &self,
        request: LedgerListRequest,
    ) -> Result<Vec<Value>, PlatformLegacyRepositoryError> {
        let rows = sqlx::query(LEDGERS_LIST_SQL)
            .bind(request.view)
            .bind(request.as_of)
            .bind(request.status)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter()
            .map(|row| {
                row.try_get("ledger")
                    .map_err(PlatformLegacyRepositoryError::from)
            })
            .collect()
    }

    async fn find_ledger(
        &self,
        ledger_id: Uuid,
    ) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
        let row = sqlx::query(LEDGER_DETAIL_SQL)
            .bind(ledger_id)
            .fetch_optional(&self.pool)
            .await?;
        row.map(|row| row.try_get("ledger"))
            .transpose()
            .map_err(PlatformLegacyRepositoryError::from)
    }

    async fn change_ledger_status(
        &self,
        command: LedgerStatusCommand,
    ) -> Result<Value, PlatformLegacyRepositoryError> {
        let mut tx = self.pool.begin().await?;
        if let Some(existing) = find_idempotent_value(
            &mut tx,
            "ledger.status",
            &command.idempotency_key,
            &command.request_payload,
        )
        .await?
        {
            tx.commit().await?;
            return Ok(existing);
        }
        let row = sqlx::query("select status, version from app.ledgers where id = $1")
            .bind(command.ledger_id)
            .fetch_optional(&mut *tx)
            .await?;
        let Some(row) = row else {
            return Err(PlatformLegacyRepositoryError::NotFound { resource: "ledger" });
        };
        let previous_status: String = row.try_get("status")?;
        let current_version: i32 = row.try_get("version")?;
        if command
            .expected_version
            .is_some_and(|expected| expected as i32 != current_version)
        {
            return Err(PlatformLegacyRepositoryError::Conflict {
                code: "ledger_version_conflict",
                message: "ledger version does not match expected_version".to_owned(),
            });
        }
        sqlx::query(
            r#"
            update app.ledgers
            set status = coalesce($2, status),
                due_at = case
                    when $3::text is null then due_at
                    else to_date($3, 'YYYY-MM-DD')::timestamptz
                end,
                ledger_payload = case
                    when $5::text is null then ledger_payload
                    else jsonb_set(ledger_payload, '{latest_note}', to_jsonb($5::text), true)
                end,
                closed_at = case
                    when coalesce($2, status) in ('resolved', 'cancelled') then coalesce(closed_at, now())
                    else null
                end,
                version = version + 1,
                updated_by = $4,
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(command.ledger_id)
        .bind(command.status.as_deref())
        .bind(&command.expected_date)
        .bind(&command.actor.actor_id)
        .bind(command.note.as_deref())
        .execute(&mut *tx)
        .await?;
        sqlx::query(
            r#"
            insert into app.ledger_events (
              ledger_id,
              event_type,
              previous_status,
              new_status,
              event_payload,
              affected_scopes,
              idempotency_key,
              created_by,
              updated_by
            )
            values ($1, 'status_changed', $2, $3, $4, array['ledgers'], $5, $6, $6)
            "#,
        )
        .bind(command.ledger_id)
        .bind(&previous_status)
        .bind(command.status.as_deref().unwrap_or(&previous_status))
        .bind(json!({
            "actor_id": command.actor_id,
            "status": command.status.clone(),
            "expected_date": command.expected_date.clone(),
            "note": command.note.clone(),
            "expected_version": command.expected_version
        }))
        .bind(&command.idempotency_key)
        .bind(&command.actor.actor_id)
        .execute(&mut *tx)
        .await
        .map_err(map_sqlx_error)?;
        let ledger = find_ledger_value(&mut tx, command.ledger_id)
            .await?
            .ok_or(PlatformLegacyRepositoryError::NotFound { resource: "ledger" })?;
        let trace_id = command
            .actor
            .request_id
            .clone()
            .unwrap_or_else(|| command.idempotency_key.clone());
        insert_generic_audit_event(
            &mut tx,
            "ledger.status_changed",
            "status_changed",
            "ledger",
            command.ledger_id,
            &command.actor,
            &trace_id,
            &command.idempotency_key,
            ledger.clone(),
            json!({"operation": "ledger.status"}),
        )
        .await?;
        record_idempotency_value(
            &mut tx,
            "ledger.status",
            &command.idempotency_key,
            &command.request_payload,
            &ledger,
            "ledger",
            command.ledger_id,
            &command.actor.actor_id,
        )
        .await?;
        tx.commit().await?;
        Ok(ledger)
    }

    async fn list_reminders(
        &self,
        request: ReminderListRequest,
    ) -> Result<Vec<Value>, PlatformLegacyRepositoryError> {
        let rows = sqlx::query(REMINDERS_LIST_SQL)
            .bind(request.as_of)
            .bind(request.status)
            .fetch_all(&self.pool)
            .await?;
        rows.into_iter()
            .map(|row| {
                row.try_get("reminder")
                    .map_err(PlatformLegacyRepositoryError::from)
            })
            .collect()
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
where job.worker_tasks.id = $1
  and (
    visibility = 'system'
    or created_by = $2
    or owner_user_id::text = $2
  )
  and status in ('failed', 'dead_lettered')
  and retryable is true
"#;

const IMPORT_FILE_RETRY_TARGET_SQL: &str = r#"
select 1
from app.import_files
where id = $1
  and parse_status = 'failed'
"#;

const IDENTITY_ROLE_PROVISIONING_TASK_TYPE: &str = "identity_role_provisioning";
const IDENTITY_ROLE_PROVISIONING_OUTBOX_EVENT_TYPE: &str = "identity.role_provisioning_requested";
const IDENTITY_ROLE_PROVISIONING_SUBJECT: &str = "finops.jobs.identity.role_provisioning";
const IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION: &str = "finops.identity.role_provisioning.v1";

const IDENTITY_PROVISIONING_PAYLOAD_HASH_SQL: &str = r#"
select encode(digest($1::jsonb::text, 'sha256'), 'hex') as payload_hash
"#;

const IDENTITY_PROVISIONING_EXISTING_SQL: &str = r#"
select id
from app.identity_provisioning_requests
where payload_hash = $1
   or (settings_profile_id = $2 and settings_version = $3)
limit 1
"#;

const IDENTITY_PROVISIONING_TASK_INSERT_SQL: &str = r#"
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
  array['identity_roles', 'workbench_settings'],
  $7
)
"#;

const IDENTITY_PROVISIONING_OUTBOX_INSERT_SQL: &str = r#"
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
  'identity_provisioning_request',
  $2,
  $3,
  $4,
  $5,
  'pending',
  $6,
  $7
)
"#;

const IDENTITY_PROVISIONING_REQUEST_INSERT_SQL: &str = r#"
insert into app.identity_provisioning_requests (
  id,
  settings_profile_id,
  settings_version,
  status,
  requested_by,
  worker_task_id,
  outbox_event_id,
  idempotency_key,
  trace_id,
  payload_hash,
  created_by,
  updated_by
)
values (
  $1,
  $2,
  $3,
  'queued',
  $4,
  $5,
  $6,
  $7,
  $8,
  $9,
  $4,
  $4
)
on conflict do nothing
returning id
"#;

const BACKGROUND_JOB_ACK_TARGET_SQL: &str = r#"
select
  job.worker_tasks.id::text as id,
  job.worker_tasks.task_type,
  job.worker_tasks.status,
  job.worker_tasks.phase,
  job.worker_tasks.visibility,
  job.worker_tasks.label,
  coalesce(job.worker_tasks.owner_user_id::text, job.worker_tasks.created_by) as owner_user_id,
  job.worker_tasks.source,
  job.worker_tasks.payload,
  job.worker_tasks.result_summary,
  job.worker_tasks.current_count,
  job.worker_tasks.total_count,
  job.worker_tasks.percent,
  job.worker_tasks.error_summary,
  job.worker_tasks.idempotency_key,
  job.worker_tasks.affected_scopes,
  coalesce(array(select to_char(value, 'YYYY-MM-DD') from unnest(job.worker_tasks.affected_months) as value), '{}') as affected_months,
  to_char(job.worker_tasks.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as created_at,
  to_char(job.worker_tasks.started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"') as started_at,
  to_char(job.worker_tasks.updated_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as updated_at,
  to_char(job.worker_tasks.finished_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"+00:00"') as finished_at,
  job.worker_tasks.retryable,
  to_char(ack.acknowledged_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as acknowledged_at
from job.worker_tasks
left join job.worker_task_acknowledgements ack
  on ack.task_id = job.worker_tasks.id
 and ack.actor_id = $2
where job.worker_tasks.id = $1
  and (
    job.worker_tasks.visibility = 'system'
    or job.worker_tasks.created_by = $2
    or job.worker_tasks.owner_user_id::text = $2
  )
"#;

const CURRENT_SETTINGS_SQL: &str = r#"
select settings_payload
from app.settings_profiles
where settings_key = 'workbench' and status = 'active'
order by version desc
limit 1
"#;

const PROJECT_PROFILE_INSERT_SQL: &str = r#"
insert into app.project_profiles (
  id,
  project_code,
  project_name,
  project_status,
  project_source,
  department_name,
  owner_name,
  idempotency_key,
  created_by,
  updated_by
)
values ($1, $2, $3, $4, 'manual', $5, $6, $7, $8, $8)
on conflict (project_code) do update
set project_name = excluded.project_name,
    project_status = excluded.project_status,
    department_name = excluded.department_name,
    owner_name = excluded.owner_name,
    version = app.project_profiles.version + 1,
    idempotency_key = excluded.idempotency_key,
    updated_by = excluded.updated_by,
    updated_at = now()
returning id
"#;

const PROJECT_ASSIGNMENT_EVENT_SQL: &str = r#"
insert into app.project_profile_events (
  project_id,
  assignment_id,
  event_type,
  before_state,
  after_state,
  affected_scopes,
  idempotency_key,
  created_by,
  updated_by
)
values (
  $1,
  $2,
  'assigned',
  '{}'::jsonb,
  $3,
  array['workbench', 'search', 'cost_statistics'],
  $4,
  $5,
  $5
)
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
on conflict (operation, idempotency_key) do update
set response_payload = excluded.response_payload,
    aggregate_type = excluded.aggregate_type,
    aggregate_id = excluded.aggregate_id,
    status = 'completed'
where app.write_idempotency_records.request_payload = excluded.request_payload
"#;

const PROJECT_HUB_SQL: &str = r#"
with project_base as (
  select
    p.*,
    coalesce(
      lm.legacy_id,
      case
        when p.project_code like 'SHADOW-%-MAIN' and p.external_project_id is not null then p.external_project_id
        else null
      end,
      p.id::text
    ) as display_id
  from app.project_profiles p
  left join lateral (
    select legacy_id
    from staging.legacy_id_map
    where target_schema = 'app'
      and target_table = 'project_profiles'
      and target_id = p.id
    order by created_at desc
    limit 1
  ) lm on true
  where p.project_status = 'active'
),
project_summaries as (
  select
    p.id as project_uuid,
    jsonb_build_object(
      'project_id', p.display_id,
      'project_uuid', p.id::text,
      'project_code', p.project_code,
      'project_name', p.project_name,
      'invoice_count', coalesce((select count(*) from app.project_assignments a where a.project_id = p.id and a.object_type = 'invoice' and a.status = 'active'), 0),
      'transaction_count', coalesce((select count(*) from app.project_assignments a where a.project_id = p.id and a.object_type = 'bank_transaction' and a.status = 'active'), 0),
      'case_count', coalesce((select count(*) from app.project_assignments a where a.project_id = p.id and a.object_type = 'reconciliation_case' and a.status = 'active'), 0),
      'ledger_count', coalesce((select count(*) from app.project_assignments a where a.project_id = p.id and a.object_type = 'follow_up_ledger' and a.status = 'active'), 0)
        + coalesce((select count(*) from app.ledgers l where l.project_id = p.id), 0),
      'income_amount', '0.00',
      'expense_amount', '0.00',
      'reconciled_amount', '0.00',
      'open_ledger_amount', coalesce((select sum(l.remaining_amount)::text from app.ledgers l where l.project_id = p.id), '0.00')
    ) as summary
  from project_base p
),
assignable_objects as (
  select jsonb_build_object(
    'object_type', object_type,
    'object_id', object_id,
    'title', title,
    'counterparty', counterparty,
    'amount', amount,
    'status', status,
    'current_project_id', current_project_id,
    'current_project_uuid', current_project_uuid,
    'effective_project_id', effective_project_id,
    'effective_project_uuid', effective_project_uuid
  ) as object
  from (
    select
      'bank_transaction' as object_type,
      b.id::text as object_id,
      coalesce(b.bank_serial_no, b.account_no) as title,
      b.counterparty_name_raw as counterparty,
      b.amount::text as amount,
      b.status,
      b.project_id as current_project_id,
      bp.id::text as current_project_uuid,
      coalesce(ap.display_id, bp.display_id, bl.display_id) as effective_project_id,
      coalesce(a.project_id, bp.id, bl.project_id)::text as effective_project_uuid
    from app.bank_transactions b
    left join app.project_assignments a on a.object_type = 'bank_transaction' and a.object_id = b.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base bp on bp.id::text = b.project_id or bp.display_id = b.project_id
    left join lateral (
      select l.project_id, lp.display_id
      from app.ledgers l
      join project_base lp on lp.id = l.project_id
      where l.ledger_payload->>'source_object_type' = 'bank_transaction'
        and l.ledger_payload->>'source_object_id' = b.id::text
      order by l.updated_at desc, l.id desc
      limit 1
    ) bl on true
    union all
    select
      'invoice',
      i.id::text,
      i.invoice_no,
      coalesce(i.buyer_name, i.seller_name),
      i.amount::text,
      i.status,
      i.project_id,
      ip.id::text,
      coalesce(ap.display_id, ip.display_id),
      coalesce(a.project_id, ip.id)::text
    from app.invoices i
    left join app.project_assignments a on a.object_type = 'invoice' and a.object_id = i.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base ip on ip.id::text = i.project_id or ip.display_id = i.project_id
    union all
    select
      'reconciliation_case',
      c.id::text,
      c.id::text,
      c.counterparty_name,
      c.total_amount::text,
      c.status,
      c.project_id,
      cp.id::text,
      coalesce(ap.display_id, cp.display_id),
      coalesce(a.project_id, cp.id)::text
    from app.reconciliation_cases c
    left join app.project_assignments a on a.object_type = 'reconciliation_case' and a.object_id = c.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base cp on cp.id::text = c.project_id or cp.display_id = c.project_id
    union all
    select
      'follow_up_ledger',
      l.id::text,
      l.id::text,
      l.counterparty_name,
      l.remaining_amount::text,
      l.status,
      l.project_id::text,
      l.project_id::text,
      coalesce(ap.display_id, lp.display_id),
      coalesce(a.project_id, l.project_id)::text
    from app.ledgers l
    left join project_base lp on lp.id = l.project_id
    left join app.project_assignments a on a.object_type = 'follow_up_ledger' and a.object_id = l.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
  ) objects
)
select jsonb_build_object(
  'projects',
  coalesce(
    jsonb_agg(
      jsonb_build_object(
        'id', display_id,
        'project_id', display_id,
        'project_uuid', id::text,
        'project_code', project_code,
        'project_name', project_name,
        'project_status', project_status,
        'source_system', project_source,
        'source', case project_source when 'oa_sync' then 'oa' else project_source end,
        'oa_external_id', null,
        'department_name', department_name,
        'owner_name', owner_name,
        'version', version
      )
      order by project_code
    ) filter (where id is not null),
    '[]'::jsonb
  ),
  'summaries', coalesce((select jsonb_agg(summary order by summary->>'project_code') from project_summaries), '[]'::jsonb),
  'totals', jsonb_build_object(
    'income_amount', '0.00',
    'expense_amount', '0.00',
    'reconciled_amount', '0.00',
    'open_ledger_amount', coalesce((select sum(l.remaining_amount)::text from app.ledgers l), '0.00')
  ),
  'assignable_objects', coalesce((select jsonb_agg(object order by object->>'object_type', object->>'object_id') from assignable_objects), '[]'::jsonb),
  'total', count(id)
) as hub
from project_base
"#;

const PROJECT_VALUE_SQL: &str = r#"
select jsonb_build_object(
  'id', coalesce(lm.legacy_id, case when p.project_code like 'SHADOW-%-MAIN' and p.external_project_id is not null then p.external_project_id else null end, p.id::text),
  'project_id', coalesce(lm.legacy_id, case when p.project_code like 'SHADOW-%-MAIN' and p.external_project_id is not null then p.external_project_id else null end, p.id::text),
  'project_uuid', p.id::text,
  'project_code', p.project_code,
  'project_name', p.project_name,
  'project_status', p.project_status,
  'source_system', p.project_source,
  'source', case p.project_source when 'oa_sync' then 'oa' else p.project_source end,
  'oa_external_id', null,
  'department_name', p.department_name,
  'owner_name', p.owner_name,
  'version', p.version
) as project
from app.project_profiles p
left join lateral (
  select legacy_id
  from staging.legacy_id_map
  where target_schema = 'app'
    and target_table = 'project_profiles'
    and target_id = p.id
  order by created_at desc
  limit 1
) lm on true
where p.id = $1
"#;

const PROJECT_ID_RESOLVE_SQL: &str = r#"
select p.id
from app.project_profiles p
left join staging.legacy_id_map lm
  on lm.target_schema = 'app'
 and lm.target_table = 'project_profiles'
 and lm.target_id = p.id
where p.legacy_id = $1
   or lm.legacy_id = $1
   or p.external_project_id = $1
   or p.project_code = $1
order by p.updated_at desc
limit 1
"#;

const PROJECT_DETAIL_SQL: &str = r#"
with project_base as (
  select
    p.*,
    coalesce(
      lm.legacy_id,
      case
        when p.project_code like 'SHADOW-%-MAIN' and p.external_project_id is not null then p.external_project_id
        else null
      end,
      p.id::text
    ) as display_id
  from app.project_profiles p
  left join lateral (
    select legacy_id
    from staging.legacy_id_map
    where target_schema = 'app'
      and target_table = 'project_profiles'
      and target_id = p.id
    order by created_at desc
    limit 1
  ) lm on true
  where p.id = $1
),
assignment_rows as (
  select jsonb_build_object(
    'id', format('project_assign_%s', lpad(row_number() over (order by a.created_at asc, a.id asc)::text, 4, '0')),
    'object_type', a.object_type,
    'object_id', a.object_id::text,
    'project_id', a.project_id::text,
    'note', a.note,
    'assigned_by', a.created_by,
    'source', 'manual',
    'created_at', to_char(a.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"')
  ) as assignment
  from app.project_assignments a
  join project_base p on p.id = a.project_id
  where a.status = 'active'
  order by a.created_at desc, a.id desc
),
object_rows as (
  select object
  from (
    select
      coalesce(a.project_id, bp.id, bl.project_id) as effective_project_uuid,
      jsonb_build_object(
        'object_type', 'bank_transaction',
        'object_id', b.id::text,
        'title', coalesce(b.bank_serial_no, b.account_no),
        'counterparty', b.counterparty_name_raw,
        'amount', b.amount::text,
        'status', b.status,
        'current_project_id', b.project_id,
        'current_project_uuid', bp.id::text,
        'effective_project_id', coalesce(ap.display_id, bp.display_id, bl.display_id),
        'effective_project_uuid', coalesce(a.project_id, bp.id, bl.project_id)::text
      ) as object
    from app.bank_transactions b
    left join app.project_assignments a on a.object_type = 'bank_transaction' and a.object_id = b.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base bp on bp.id::text = b.project_id or bp.display_id = b.project_id
    left join lateral (
      select l.project_id, lp.display_id
      from app.ledgers l
      join project_base lp on lp.id = l.project_id
      where l.ledger_payload->>'source_object_type' = 'bank_transaction'
        and l.ledger_payload->>'source_object_id' = b.id::text
      order by l.updated_at desc, l.id desc
      limit 1
    ) bl on true
    union all
    select
      coalesce(a.project_id, ip.id),
      jsonb_build_object(
        'object_type', 'invoice',
        'object_id', i.id::text,
        'title', i.invoice_no,
        'counterparty', coalesce(i.buyer_name, i.seller_name),
        'amount', i.amount::text,
        'status', i.status,
        'current_project_id', i.project_id,
        'current_project_uuid', ip.id::text,
        'effective_project_id', coalesce(ap.display_id, ip.display_id),
        'effective_project_uuid', coalesce(a.project_id, ip.id)::text
      )
    from app.invoices i
    left join app.project_assignments a on a.object_type = 'invoice' and a.object_id = i.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base ip on ip.id::text = i.project_id or ip.display_id = i.project_id
    union all
    select
      coalesce(a.project_id, cp.id),
      jsonb_build_object(
        'object_type', 'reconciliation_case',
        'object_id', c.id::text,
        'title', c.id::text,
        'counterparty', c.counterparty_name,
        'amount', c.total_amount::text,
        'status', c.status,
        'current_project_id', c.project_id,
        'current_project_uuid', cp.id::text,
        'effective_project_id', coalesce(ap.display_id, cp.display_id),
        'effective_project_uuid', coalesce(a.project_id, cp.id)::text
      )
    from app.reconciliation_cases c
    left join app.project_assignments a on a.object_type = 'reconciliation_case' and a.object_id = c.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base cp on cp.id::text = c.project_id or cp.display_id = c.project_id
    union all
    select
      coalesce(a.project_id, l.project_id),
      jsonb_build_object(
        'object_type', 'follow_up_ledger',
        'object_id', l.id::text,
        'title', l.id::text,
        'counterparty', l.counterparty_name,
        'amount', l.remaining_amount::text,
        'status', l.status,
        'current_project_id', l.project_id::text,
        'current_project_uuid', l.project_id::text,
        'effective_project_id', coalesce(ap.display_id, lp.display_id),
        'effective_project_uuid', coalesce(a.project_id, l.project_id)::text
      )
    from app.ledgers l
    left join app.project_assignments a on a.object_type = 'follow_up_ledger' and a.object_id = l.id and a.status = 'active'
    left join project_base ap on ap.id = a.project_id
    left join project_base lp on lp.id = l.project_id
  ) objects
  where effective_project_uuid = $1
)
select jsonb_build_object(
  'project', jsonb_build_object(
    'id', display_id,
    'project_id', display_id,
    'project_uuid', id::text,
    'project_code', project_code,
    'project_name', project_name,
    'project_status', project_status,
    'source_system', project_source,
    'source', case project_source when 'oa_sync' then 'oa' else project_source end,
    'oa_external_id', null,
    'department_name', department_name,
    'owner_name', owner_name,
    'version', version
  ),
  'summary', jsonb_build_object(
    'project_id', display_id,
    'project_uuid', id::text,
    'project_code', project_code,
    'project_name', project_name,
    'invoice_count', coalesce((select count(*) from app.project_assignments a where a.project_id = project_base.id and a.object_type = 'invoice' and a.status = 'active'), 0),
    'transaction_count', coalesce((select count(*) from app.project_assignments a where a.project_id = project_base.id and a.object_type = 'bank_transaction' and a.status = 'active'), 0),
    'case_count', coalesce((select count(*) from app.project_assignments a where a.project_id = project_base.id and a.object_type = 'reconciliation_case' and a.status = 'active'), 0),
    'ledger_count', coalesce((select count(*) from app.project_assignments a where a.project_id = project_base.id and a.object_type = 'follow_up_ledger' and a.status = 'active'), 0)
      + coalesce((select count(*) from app.ledgers l where l.project_id = project_base.id), 0),
    'income_amount', '0.00',
    'expense_amount', '0.00',
    'reconciled_amount', '0.00',
    'open_ledger_amount', coalesce((select sum(l.remaining_amount)::text from app.ledgers l where l.project_id = project_base.id), '0.00')
  ),
  'assignments', coalesce((select jsonb_agg(assignment) from assignment_rows), '[]'::jsonb),
  'objects', coalesce((select jsonb_agg(object) from object_rows), '[]'::jsonb)
) as project
from project_base
"#;

const PROJECT_SETTINGS_SQL: &str = r#"
select
  id::text as id,
  project_code,
  project_name,
  project_status,
  case project_source when 'oa_sync' then 'oa' else project_source end as source,
  department_name,
  owner_name
from app.project_profiles
where project_status = 'active'
order by project_code, project_name, id
"#;

const LEDGERS_LIST_SQL: &str = r#"
select jsonb_build_object(
  'id', id::text,
  'ledger_type', ledger_type,
  'counterparty_name', counterparty_name,
  'open_amount', amount::text,
  'expected_date', to_char(due_at at time zone 'UTC', 'YYYY-MM-DD'),
  'status', status,
  'last_reminded_at', ledger_payload->>'last_reminded_at',
  'created_at', to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
) as ledger
from app.ledgers
where (
    $1::text is null
    or $1::text = 'all'
    or (
      $1::text = 'overdue'
      and status not in ('resolved', 'cancelled')
      and due_at::date < coalesce(to_date($2, 'YYYY-MM-DD'), current_date)
    )
    or (
      $1::text = 'due'
      and status not in ('resolved', 'cancelled')
      and due_at::date between coalesce(to_date($2, 'YYYY-MM-DD'), current_date)
        and coalesce(to_date($2, 'YYYY-MM-DD'), current_date) + 7
    )
    or (
      $1::text not in ('all', 'overdue', 'due')
      and status not in ('resolved', 'cancelled')
    )
  )
  and ($3::text is null or status = $3)
order by due_at nulls last, updated_at desc, id desc
"#;

const LEDGER_DETAIL_SQL: &str = r#"
select jsonb_build_object(
  'id', id::text,
  'ledger_type', ledger_type,
  'counterparty_name', counterparty_name,
  'open_amount', amount::text,
  'expected_date', to_char(due_at at time zone 'UTC', 'YYYY-MM-DD'),
  'status', status,
  'last_reminded_at', ledger_payload->>'last_reminded_at',
  'created_at', to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'events', coalesce((
    select jsonb_agg(
      jsonb_build_object(
        'event_type', e.event_type,
        'previous_status', e.previous_status,
        'new_status', e.new_status,
        'event_payload', e.event_payload,
        'created_at', to_char(e.created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
      )
      order by e.created_at desc
    )
    from app.ledger_events e
    where e.ledger_id = app.ledgers.id
  ), '[]'::jsonb)
) as ledger
from app.ledgers
where id = $1
"#;

const REMINDERS_LIST_SQL: &str = r#"
select jsonb_build_object(
  'id', id::text,
  'ledger_id', ledger_id::text,
  'remind_at', to_char(due_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  'status', status,
  'sent_result', message_payload->'sent_result',
  'sent_at', message_payload->>'sent_at',
  'created_at', to_char(created_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
) as reminder
from app.reminders
where ($1::text is null or due_at::date <= to_date($1, 'YYYY-MM-DD'))
  and ($2::text is null or status = $2)
order by due_at asc, updated_at desc, id desc
"#;

async fn ensure_retry_target_exists(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
) -> Result<(), PlatformLegacyRepositoryError> {
    let (exists, resource) = match command.operation.as_str() {
        "background_job.retry" => (
            sqlx::query(BACKGROUND_JOB_RETRY_TARGET_SQL)
                .bind(command.aggregate_id)
                .bind(&command.actor.actor_id)
                .fetch_optional(&mut **tx)
                .await?,
            "retryable_background_job",
        ),
        "import_file.retry" => (
            sqlx::query(IMPORT_FILE_RETRY_TARGET_SQL)
                .bind(command.aggregate_id)
                .fetch_optional(&mut **tx)
                .await?,
            "retryable_import_file",
        ),
        _ => return Ok(()),
    };
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

async fn find_idempotent_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    operation: &str,
    idempotency_key: &str,
    request_payload: &Value,
) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
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
    row.try_get("response_payload")
        .map(Some)
        .map_err(PlatformLegacyRepositoryError::from)
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
    let outcome = sqlx::query(RECORD_IDEMPOTENCY_SQL)
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
    if outcome.rows_affected() == 0 {
        return Err(PlatformLegacyRepositoryError::IdempotencyConflict);
    }
    Ok(())
}

async fn record_idempotency_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    operation: &str,
    idempotency_key: &str,
    request_payload: &Value,
    response_payload: &Value,
    aggregate_type: &str,
    aggregate_id: Uuid,
    actor_id: &str,
) -> Result<(), PlatformLegacyRepositoryError> {
    let outcome = sqlx::query(RECORD_IDEMPOTENCY_SQL)
        .bind(operation)
        .bind(idempotency_key)
        .bind(request_payload)
        .bind(response_payload)
        .bind(aggregate_type)
        .bind(aggregate_id)
        .bind(actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    if outcome.rows_affected() == 0 {
        return Err(PlatformLegacyRepositoryError::IdempotencyConflict);
    }
    Ok(())
}

async fn insert_data_reset_request_if_needed(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
    task_id: Uuid,
    outbox_event_id: Uuid,
) -> Result<(), PlatformLegacyRepositoryError> {
    if command.operation != "data_reset.request" {
        return Ok(());
    }
    let action = command.source.get("action").and_then(Value::as_str).ok_or(
        PlatformLegacyRepositoryError::NotFound {
            resource: "data_reset_action",
        },
    )?;
    let active = sqlx::query(
        r#"
        select id
        from app.data_reset_requests
        where action = $1
          and status in ('queued', 'running')
          and idempotency_key <> $2
        limit 1
        "#,
    )
    .bind(action)
    .bind(&command.idempotency_key)
    .fetch_optional(&mut **tx)
    .await?;
    if active.is_some() {
        return Err(PlatformLegacyRepositoryError::Conflict {
            code: "settings_data_reset_job_running",
            message: "a data reset job for this action is already queued or running".to_owned(),
        });
    }
    sqlx::query(
        r#"
        insert into app.data_reset_requests (
          id,
          worker_task_id,
          outbox_event_id,
          action,
          status,
          scope,
          approval_id,
          backup_evidence_id,
          requested_by,
          execution_mode,
          idempotency_key,
          created_by,
          updated_by
        )
        values (
          $1,
          $1,
          $2,
          $3,
          'queued',
          $4,
          $5,
          $6,
          $7,
          'queued',
          $8,
          $7,
          $7
        )
        "#,
    )
    .bind(task_id)
    .bind(outbox_event_id)
    .bind(action)
    .bind(
        command
            .source
            .get("scope")
            .cloned()
            .unwrap_or_else(|| json!({})),
    )
    .bind(command.source.get("approval_id").and_then(Value::as_str))
    .bind(
        command
            .source
            .get("backup_evidence_id")
            .and_then(Value::as_str),
    )
    .bind(&command.actor.actor_id)
    .bind(&command.idempotency_key)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok(())
}

async fn insert_reminder_run_if_needed(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    command: &PlatformJobCommand,
    task_id: Uuid,
    outbox_event_id: Uuid,
) -> Result<(), PlatformLegacyRepositoryError> {
    if command.operation != "reminder.run" {
        return Ok(());
    }
    let as_of = command.source.get("as_of").and_then(Value::as_str).ok_or(
        PlatformLegacyRepositoryError::NotFound {
            resource: "reminder_run_as_of",
        },
    )?;
    let days_ahead = command.source.get("days_ahead").and_then(Value::as_i64);
    sqlx::query(
        r#"
        insert into app.reminder_runs (
          id,
          worker_task_id,
          outbox_event_id,
          run_scope,
          status,
          as_of,
          days_ahead,
          idempotency_key,
          created_by,
          updated_by
        )
        values (
          $1,
          $1,
          $2,
          $3,
          'queued',
          to_date($4, 'YYYY-MM-DD'),
          $5,
          $6,
          $7,
          $7
        )
        "#,
    )
    .bind(task_id)
    .bind(outbox_event_id)
    .bind(&command.source)
    .bind(as_of)
    .bind(days_ahead.map(|value| value as i32))
    .bind(&command.idempotency_key)
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
    .bind(job_command_audit_event_type(&command.operation))
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

fn job_command_audit_event_type(operation: &str) -> &'static str {
    match operation {
        "background_job.retry" => "background_job.retry_requested",
        "import_file.retry" => "import_file.retry_requested",
        "matching.run" => "matching.run_requested",
        "project.sync" => "project_sync.requested",
        "data_reset.request" => "data_reset.requested",
        "reminder.run" => "reminder.run_requested",
        _ => "platform_job.requested",
    }
}

fn job_command_outbox_event_type(operation: &str) -> &'static str {
    match operation {
        "background_job.retry" => "worker_task.retry_requested",
        "import_file.retry" => "import.parse_requested",
        "matching.run" => "workbench_matching.requested",
        "project.sync" => "project.sync_requested",
        "data_reset.request" => "data_reset.requested",
        "reminder.run" => "reminder.run_requested",
        _ => "platform_job.requested",
    }
}

async fn insert_generic_audit_event(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    event_type: &str,
    action: &str,
    entity_type: &str,
    entity_id: Uuid,
    actor: &crate::services::workbench_writes::WriteActor,
    trace_id: &str,
    idempotency_key: &str,
    after_state: Value,
    metadata: Value,
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
        values ($1, $2, $3, $4, $5, 'user', $6, $6, $7, $8, $9)
        "#,
    )
    .bind(event_type)
    .bind(action)
    .bind(entity_type)
    .bind(entity_id)
    .bind(&actor.actor_id)
    .bind(trace_id)
    .bind(idempotency_key)
    .bind(after_state)
    .bind(metadata)
    .execute(&mut **tx)
    .await
    .map_err(map_sqlx_error)?;
    Ok(())
}

async fn insert_identity_role_provisioning_request_if_needed(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    settings_profile_id: Uuid,
    settings_version: i64,
    settings_projection: &Value,
    command: &WorkbenchSettingsCommand,
    trace_id: &str,
) -> Result<(), PlatformLegacyRepositoryError> {
    let access_control = settings_projection
        .get("access_control")
        .cloned()
        .unwrap_or_else(|| json!({}));
    let assignments = identity_role_assignments(&access_control);
    let hash_basis = json!({
        "schema_version": IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION,
        "source": "workbench_settings",
        "access_control": access_control,
        "assignments": assignments
    });
    let payload_hash: String = sqlx::query(IDENTITY_PROVISIONING_PAYLOAD_HASH_SQL)
        .bind(&hash_basis)
        .fetch_one(&mut **tx)
        .await?
        .try_get("payload_hash")?;
    let existing = sqlx::query(IDENTITY_PROVISIONING_EXISTING_SQL)
        .bind(&payload_hash)
        .bind(settings_profile_id)
        .bind(settings_version as i32)
        .fetch_optional(&mut **tx)
        .await?;
    if existing.is_some() {
        return Ok(());
    }

    let request_id = Uuid::new_v4();
    let task_id = Uuid::new_v4();
    let outbox_event_id = Uuid::new_v4();
    let provisioning_idempotency_key =
        format!("identity_role_provisioning:{settings_profile_id}:{settings_version}");
    let outbox_idempotency_key = format!("outbox:{provisioning_idempotency_key}");
    let payload = json!({
        "schema_version": IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION,
        "settings_profile_id": settings_profile_id,
        "settings_version": settings_version,
        "access_control": access_control,
        "assignments": assignments,
        "source": "workbench_settings",
        "requested_by": command.actor.actor_id,
        "trace_id": trace_id
    });
    let source = json!({
        "settings_profile_id": settings_profile_id,
        "settings_version": settings_version,
        "source": "workbench_settings",
        "payload_hash": payload_hash
    });

    sqlx::query(IDENTITY_PROVISIONING_TASK_INSERT_SQL)
        .bind(task_id)
        .bind(IDENTITY_ROLE_PROVISIONING_TASK_TYPE)
        .bind(&provisioning_idempotency_key)
        .bind("同步身份角色")
        .bind(&source)
        .bind(&payload)
        .bind(&command.actor.actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    sqlx::query(IDENTITY_PROVISIONING_OUTBOX_INSERT_SQL)
        .bind(outbox_event_id)
        .bind(request_id)
        .bind(IDENTITY_ROLE_PROVISIONING_OUTBOX_EVENT_TYPE)
        .bind(IDENTITY_ROLE_PROVISIONING_SUBJECT)
        .bind(&payload)
        .bind(&outbox_idempotency_key)
        .bind(trace_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    let inserted = sqlx::query(IDENTITY_PROVISIONING_REQUEST_INSERT_SQL)
        .bind(request_id)
        .bind(settings_profile_id)
        .bind(settings_version as i32)
        .bind(&command.actor.actor_id)
        .bind(task_id)
        .bind(outbox_event_id)
        .bind(&provisioning_idempotency_key)
        .bind(trace_id)
        .bind(&payload_hash)
        .fetch_optional(&mut **tx)
        .await
        .map_err(map_sqlx_error)?;
    if inserted.is_none() {
        sqlx::query("delete from job.outbox_events where id = $1")
            .bind(outbox_event_id)
            .execute(&mut **tx)
            .await
            .map_err(map_sqlx_error)?;
        sqlx::query("delete from job.worker_tasks where id = $1")
            .bind(task_id)
            .execute(&mut **tx)
            .await
            .map_err(map_sqlx_error)?;
        return Ok(());
    }

    insert_generic_audit_event(
        tx,
        "identity_role_provisioning.requested",
        "request",
        "identity_provisioning_request",
        request_id,
        &command.actor,
        trace_id,
        &provisioning_idempotency_key,
        json!({
            "request_id": request_id,
            "settings_profile_id": settings_profile_id,
            "settings_version": settings_version,
            "worker_task_id": task_id,
            "outbox_event_id": outbox_event_id,
            "status": "queued",
            "payload_hash": payload_hash
        }),
        json!({
            "operation": "identity_role_provisioning.request",
            "settings_save_idempotency_key": command.idempotency_key
        }),
    )
    .await?;
    Ok(())
}

fn identity_role_assignments(access_control: &Value) -> Value {
    let mut assignments = Vec::new();
    for username in string_array_field(access_control, "readonly_export_usernames") {
        assignments.push(json!({
            "username": username,
            "tier": "read_export_only"
        }));
    }
    for username in string_array_field(access_control, "full_access_usernames") {
        assignments.push(json!({
            "username": username,
            "tier": "full_access"
        }));
    }
    for username in string_array_field(access_control, "admin_usernames") {
        assignments.push(json!({
            "username": username,
            "tier": "admin"
        }));
    }
    Value::Array(assignments)
}

fn string_array_field(value: &Value, field: &str) -> Vec<String> {
    value
        .get(field)
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_owned)
        .collect()
}

async fn current_settings_version(
    tx: &mut Transaction<'_, sqlx::Postgres>,
) -> Result<i64, PlatformLegacyRepositoryError> {
    let row = sqlx::query(
        r#"
        select coalesce(max(version), 0)::bigint as version
        from app.settings_profiles
        where settings_key = 'workbench'
        "#,
    )
    .fetch_one(&mut **tx)
    .await?;
    row.try_get("version")
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn project_profile_version_by_code(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    project_code: &str,
) -> Result<Option<i32>, PlatformLegacyRepositoryError> {
    let row = sqlx::query(
        r#"
        select version
        from app.project_profiles
        where project_code = $1
        "#,
    )
    .bind(project_code)
    .fetch_optional(&mut **tx)
    .await?;
    row.map(|row| row.try_get("version"))
        .transpose()
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn project_exists(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    project_id: Uuid,
) -> Result<bool, PlatformLegacyRepositoryError> {
    let row = sqlx::query(
        r#"
        select 1
        from app.project_profiles
        where id = $1
        "#,
    )
    .bind(project_id)
    .fetch_optional(&mut **tx)
    .await?;
    Ok(row.is_some())
}

async fn current_settings_projection_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
) -> Result<Value, PlatformLegacyRepositoryError> {
    let row = sqlx::query(CURRENT_SETTINGS_SQL)
        .fetch_optional(&mut **tx)
        .await?;
    let raw_settings = row
        .map(|row| row.try_get("settings_payload"))
        .transpose()?
        .unwrap_or_else(|| json!({}));
    let project_rows = sqlx::query(PROJECT_SETTINGS_SQL)
        .fetch_all(&mut **tx)
        .await?;
    let projects = project_rows
        .into_iter()
        .map(|row| {
            Ok(ProjectSettingSnapshot {
                id: row.try_get("id")?,
                project_code: row.try_get("project_code")?,
                project_name: row.try_get("project_name")?,
                project_status: row.try_get("project_status")?,
                source: row.try_get("source")?,
                department_name: row.try_get("department_name")?,
                owner_name: row.try_get("owner_name")?,
            })
        })
        .collect::<Result<Vec<_>, sqlx::Error>>()?;
    Ok(workbench_settings_value_from_raw(&raw_settings, projects))
}

async fn project_hub_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
) -> Result<Value, PlatformLegacyRepositoryError> {
    let row = sqlx::query(PROJECT_HUB_SQL).fetch_one(&mut **tx).await?;
    row.try_get("hub")
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn find_project_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    project_id: Uuid,
) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
    let row = sqlx::query(PROJECT_VALUE_SQL)
        .bind(project_id)
        .fetch_optional(&mut **tx)
        .await?;
    row.map(|row| row.try_get("project"))
        .transpose()
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn find_project_detail_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    project_id: Uuid,
) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
    let row = sqlx::query(PROJECT_DETAIL_SQL)
        .bind(project_id)
        .fetch_optional(&mut **tx)
        .await?;
    row.map(|row| row.try_get("project"))
        .transpose()
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn resolve_project_id_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    project_id: &str,
) -> Result<Option<Uuid>, PlatformLegacyRepositoryError> {
    let project_id = project_id.trim();
    if project_id.is_empty() {
        return Ok(None);
    }
    if let Ok(uuid) = Uuid::parse_str(project_id) {
        if project_exists(tx, uuid).await? {
            return Ok(Some(uuid));
        }
    }
    let row = sqlx::query(PROJECT_ID_RESOLVE_SQL)
        .bind(project_id)
        .fetch_optional(&mut **tx)
        .await?;
    row.map(|row| row.try_get("id"))
        .transpose()
        .map_err(PlatformLegacyRepositoryError::from)
}

async fn project_assignment_target_exists(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    object_type: &str,
    object_id: Uuid,
) -> Result<bool, PlatformLegacyRepositoryError> {
    let sql = match object_type {
        "bank_transaction" => "select 1 from app.bank_transactions where id = $1",
        "invoice" => "select 1 from app.invoices where id = $1",
        "reconciliation_case" => "select 1 from app.reconciliation_cases where id = $1",
        "follow_up_ledger" => "select 1 from app.ledgers where id = $1",
        "oa_application" => "select 1 from app.oa_applications where id = $1",
        "oa_application_item" => "select 1 from app.oa_application_items where id = $1",
        "workbench_row" => "select 1 from read_model.workbench_rows where id = $1 limit 1",
        _ => return Ok(false),
    };
    Ok(sqlx::query(sql)
        .bind(object_id)
        .fetch_optional(&mut **tx)
        .await?
        .is_some())
}

async fn update_project_assignment_target_project(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    object_type: &str,
    object_id: Uuid,
    project_id: Uuid,
    _project_display_id: &str,
    actor_id: &str,
) -> Result<(), PlatformLegacyRepositoryError> {
    let result = match object_type {
        "bank_transaction" => sqlx::query(
            r#"
            update app.bank_transactions
            set project_id = $2,
                updated_by = $3,
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(object_id)
        .bind(project_id.to_string())
        .bind(actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?,
        "invoice" => sqlx::query(
            r#"
            update app.invoices
            set project_id = $2,
                updated_by = $3,
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(object_id)
        .bind(project_id.to_string())
        .bind(actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?,
        "reconciliation_case" => sqlx::query(
            r#"
            update app.reconciliation_cases
            set project_id = $2,
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(object_id)
        .bind(project_id.to_string())
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?,
        "follow_up_ledger" => sqlx::query(
            r#"
            update app.ledgers
            set project_id = $2,
                updated_by = $3,
                updated_at = now()
            where id = $1
            "#,
        )
        .bind(object_id)
        .bind(project_id)
        .bind(actor_id)
        .execute(&mut **tx)
        .await
        .map_err(map_sqlx_error)?,
        _ => return Ok(()),
    };
    if result.rows_affected() == 0 {
        return Err(PlatformLegacyRepositoryError::NotFound {
            resource: "project_or_object",
        });
    }
    Ok(())
}

async fn find_ledger_value(
    tx: &mut Transaction<'_, sqlx::Postgres>,
    ledger_id: Uuid,
) -> Result<Option<Value>, PlatformLegacyRepositoryError> {
    let row = sqlx::query(LEDGER_DETAIL_SQL)
        .bind(ledger_id)
        .fetch_optional(&mut **tx)
        .await?;
    row.map(|row| row.try_get("ledger"))
        .transpose()
        .map_err(PlatformLegacyRepositoryError::from)
}

fn worker_task_ack_json(row: &sqlx::postgres::PgRow) -> Value {
    let task_type = row.try_get::<String, _>("task_type").unwrap_or_default();
    let label = row.try_get::<String, _>("label").unwrap_or_default();
    let task_status = row.try_get::<String, _>("status").unwrap_or_default();
    let phase = row.try_get::<String, _>("phase").unwrap_or_default();
    let current = row.try_get::<i32, _>("current_count").unwrap_or_default();
    let total = row.try_get::<i32, _>("total_count").unwrap_or_default();
    let percent = row.try_get::<i32, _>("percent").unwrap_or_default();
    let source = row
        .try_get::<Value, _>("source")
        .unwrap_or_else(|_| json!({}));
    let payload = row
        .try_get::<Value, _>("payload")
        .unwrap_or_else(|_| json!({}));
    let message = payload
        .get("message")
        .and_then(Value::as_str)
        .or_else(|| source.get("message").and_then(Value::as_str))
        .map(str::to_owned)
        .or_else(|| {
            row.try_get::<Option<String>, _>("error_summary")
                .ok()
                .flatten()
        })
        .unwrap_or_else(|| label.clone());
    let retryable = row.try_get::<bool, _>("retryable").unwrap_or(false)
        && matches!(task_status.as_str(), "failed" | "dead_lettered");
    json!({
        "job_id": row.try_get::<String, _>("id").unwrap_or_default(),
        "type": task_type,
        "label": label,
        "short_label": row.try_get::<String, _>("label").unwrap_or_default(),
        "owner_user_id": row.try_get::<Option<String>, _>("owner_user_id").ok().flatten(),
        "visibility": row.try_get::<String, _>("visibility").unwrap_or_default(),
        "status": "acknowledged",
        "phase": phase,
        "current": current,
        "total": total,
        "percent": percent,
        "message": message,
        "result_summary": row.try_get::<Value, _>("result_summary").unwrap_or_else(|_| json!({})),
        "error": row.try_get::<Option<String>, _>("error_summary").ok().flatten(),
        "idempotency_key": row.try_get::<Option<String>, _>("idempotency_key").ok().flatten(),
        "source": source,
        "affected_scopes": row.try_get::<Vec<String>, _>("affected_scopes").unwrap_or_default(),
        "affected_months": row.try_get::<Vec<String>, _>("affected_months").unwrap_or_default(),
        "created_at": row.try_get::<String, _>("created_at").unwrap_or_default(),
        "started_at": row.try_get::<Option<String>, _>("started_at").ok().flatten(),
        "updated_at": row.try_get::<String, _>("updated_at").unwrap_or_default(),
        "finished_at": row.try_get::<Option<String>, _>("finished_at").ok().flatten(),
        "acknowledged_at": row.try_get::<Option<String>, _>("acknowledged_at").ok().flatten(),
        "superseded_by_job_id": Value::Null,
        "superseded_at": Value::Null,
        "retryable": retryable,
        "acknowledgeable": false,
        "attention": false
    })
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
            return PlatformLegacyRepositoryError::Conflict {
                code: "database_constraint_violation",
                message: format!(
                    "database unique constraint violated: {}",
                    database_error.constraint().unwrap_or("unknown")
                ),
            };
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

    #[test]
    fn job_command_event_names_match_frozen_platform_contracts() {
        assert_eq!(
            job_command_audit_event_type("background_job.retry"),
            "background_job.retry_requested"
        );
        assert_eq!(
            job_command_outbox_event_type("background_job.retry"),
            "worker_task.retry_requested"
        );
        assert_eq!(
            job_command_audit_event_type("project.sync"),
            "project_sync.requested"
        );
        assert_eq!(
            job_command_outbox_event_type("project.sync"),
            "project.sync_requested"
        );
        assert_eq!(
            job_command_audit_event_type("data_reset.request"),
            "data_reset.requested"
        );
        assert_eq!(
            job_command_outbox_event_type("data_reset.request"),
            "data_reset.requested"
        );
        assert_eq!(
            job_command_audit_event_type("reminder.run"),
            "reminder.run_requested"
        );
        assert_eq!(
            job_command_outbox_event_type("reminder.run"),
            "reminder.run_requested"
        );
    }

    #[test]
    fn settings_write_queues_identity_role_provisioning_contract() {
        assert_eq!(
            IDENTITY_ROLE_PROVISIONING_TASK_TYPE,
            "identity_role_provisioning"
        );
        assert_eq!(
            IDENTITY_ROLE_PROVISIONING_OUTBOX_EVENT_TYPE,
            "identity.role_provisioning_requested"
        );
        assert_eq!(
            IDENTITY_ROLE_PROVISIONING_SUBJECT,
            "finops.jobs.identity.role_provisioning"
        );
        assert_eq!(
            IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION,
            "finops.identity.role_provisioning.v1"
        );
        assert!(
            IDENTITY_PROVISIONING_REQUEST_INSERT_SQL.contains("app.identity_provisioning_requests")
        );
        assert!(IDENTITY_PROVISIONING_REQUEST_INSERT_SQL.contains("payload_hash"));
        assert!(IDENTITY_PROVISIONING_REQUEST_INSERT_SQL.contains("returning id"));
        assert!(IDENTITY_PROVISIONING_EXISTING_SQL.contains("payload_hash = $1"));
        assert!(IDENTITY_PROVISIONING_EXISTING_SQL.contains("settings_profile_id = $2"));
        assert!(!IDENTITY_PROVISIONING_TASK_INSERT_SQL.contains("sys_user_role"));
        assert!(!IDENTITY_PROVISIONING_OUTBOX_INSERT_SQL.contains("sys_user_role"));
    }

    #[test]
    fn identity_role_assignments_preserve_legacy_oa_role_tiers() {
        let assignments = identity_role_assignments(&json!({
            "readonly_export_usernames": ["READ001"],
            "full_access_usernames": ["FULL001"],
            "admin_usernames": ["ADMIN001"]
        }));

        assert_eq!(
            assignments,
            json!([
                {"username": "READ001", "tier": "read_export_only"},
                {"username": "FULL001", "tier": "full_access"},
                {"username": "ADMIN001", "tier": "admin"}
            ])
        );
    }

    #[test]
    fn platform_queries_use_postgresql_facts_for_p0_legacy_routes() {
        assert!(BACKGROUND_JOB_ACK_TARGET_SQL.contains("from job.worker_tasks"));
        assert!(PROJECT_HUB_SQL.contains("from app.project_profiles"));
        assert!(LEDGERS_LIST_SQL.contains("from app.ledgers"));
        assert!(LEDGER_DETAIL_SQL.contains("from app.ledger_events"));
        assert!(REMINDERS_LIST_SQL.contains("from app.reminders"));
        assert!(PROJECT_PROFILE_INSERT_SQL.contains("project_source"));
        assert!(CURRENT_SETTINGS_SQL.contains("status = 'active'"));
        assert!(PROJECT_SETTINGS_SQL.contains("from app.project_profiles"));
        assert!(PROJECT_DETAIL_SQL.contains("from app.project_profiles"));
    }

    #[test]
    fn background_job_ack_query_exposes_legacy_job_envelope_fields() {
        for field in [
            "current_count",
            "total_count",
            "percent",
            "result_summary",
            "error_summary",
            "idempotency_key",
            "affected_scopes",
            "affected_months",
            "started_at",
            "finished_at",
            "retryable",
        ] {
            assert!(
                BACKGROUND_JOB_ACK_TARGET_SQL.contains(field),
                "ack response query must select {field}"
            );
        }
    }

    #[test]
    fn background_job_ack_query_qualifies_ambiguous_worker_task_columns() {
        for fragment in [
            "job.worker_tasks.id::text as id",
            "job.worker_tasks.idempotency_key",
            "job.worker_tasks.created_at",
            "job.worker_tasks.updated_at",
            "where job.worker_tasks.id = $1",
        ] {
            assert!(
                BACKGROUND_JOB_ACK_TARGET_SQL.contains(fragment),
                "ack query must qualify {fragment}"
            );
        }
        assert!(!BACKGROUND_JOB_ACK_TARGET_SQL.contains("\nwhere id = $1"));
    }

    #[test]
    fn project_profile_upsert_returns_actual_project_id() {
        assert!(
            PROJECT_PROFILE_INSERT_SQL.contains("returning id"),
            "project upsert must return the inserted or updated row id"
        );
    }

    #[test]
    fn idempotency_record_insert_conflicts_only_on_different_payload() {
        assert!(
            RECORD_IDEMPOTENCY_SQL.contains("on conflict (operation, idempotency_key) do update")
        );
        assert!(RECORD_IDEMPOTENCY_SQL.contains(
            "where app.write_idempotency_records.request_payload = excluded.request_payload"
        ));
    }

    #[test]
    fn project_queries_return_legacy_hub_and_detail_envelopes() {
        for field in ["'summaries'", "'totals'", "'assignable_objects'"] {
            assert!(
                PROJECT_HUB_SQL.contains(field),
                "project hub query must include {field}"
            );
        }
        assert!(
            PROJECT_HUB_SQL.contains("'oa_external_id', null"),
            "project hub query must expose legacy oa_external_id null"
        );
        for field in ["'summary'", "'assignments'", "'objects'"] {
            assert!(
                PROJECT_DETAIL_SQL.contains(field),
                "project detail query must include {field}"
            );
        }
        assert!(
            PROJECT_DETAIL_SQL.contains("'oa_external_id', null"),
            "project detail query must expose legacy oa_external_id null"
        );
    }

    #[test]
    fn project_object_queries_expose_legacy_current_and_effective_project_ids() {
        for query in [PROJECT_HUB_SQL, PROJECT_DETAIL_SQL] {
            assert!(
                query.contains("'current_project_uuid'"),
                "project object projection must include current_project_uuid"
            );
            assert!(
                query.contains("coalesce(a.project_id, bp.id, bl.project_id)::text"),
                "bank transactions must derive effective project UUID from assignment, direct project, or linked ledger"
            );
            assert!(
                query.contains("l.project_id::text"),
                "ledger current_project_id must remain the raw project UUID"
            );
            assert!(
                query.contains("coalesce(a.project_id, l.project_id)::text"),
                "ledger effective_project_uuid must fall back to the ledger project"
            );
            assert!(
                query.contains("'title', l.id::text")
                    || query.contains("'follow_up_ledger',\n      l.id::text,\n      l.id::text"),
                "ledger object title must match legacy UUID title projection"
            );
        }
    }

    #[test]
    fn project_assignment_query_uses_legacy_public_assignment_shape() {
        assert!(
            PROJECT_DETAIL_SQL.contains("format('project_assign_%s'"),
            "assignment public id must use the legacy project_assign_0001 shape"
        );
        for field in ["'assigned_by'", "'source'", "'created_at'"] {
            assert!(
                PROJECT_DETAIL_SQL.contains(field),
                "assignment projection must include {field}"
            );
        }
        for internal_field in [
            "'assignment_id', a.id::text",
            "'project_uuid', a.project_id::text",
            "'status', a.status",
            "'updated_at', to_char(a.updated_at",
        ] {
            assert!(
                !PROJECT_DETAIL_SQL.contains(internal_field),
                "assignment projection must not expose {internal_field}"
            );
        }
    }

    #[test]
    fn project_assignment_event_uses_allowed_schema_event_type() {
        assert!(!PROJECT_ASSIGNMENT_EVENT_SQL.contains("assignment_changed"));
        assert!(PROJECT_ASSIGNMENT_EVENT_SQL.contains("'assigned'"));
    }

    #[test]
    fn ledger_list_query_preserves_legacy_view_semantics() {
        assert!(LEDGERS_LIST_SQL.contains("$1::text = 'overdue'"));
        assert!(LEDGERS_LIST_SQL.contains("due_at::date < coalesce"));
        assert!(LEDGERS_LIST_SQL.contains("$1::text = 'due'"));
        assert!(LEDGERS_LIST_SQL.contains("+ 7"));
        assert!(LEDGERS_LIST_SQL.contains("status not in ('resolved', 'cancelled')"));
        assert!(LEDGERS_LIST_SQL.contains("$1::text not in ('all', 'overdue', 'due')"));
    }
}
