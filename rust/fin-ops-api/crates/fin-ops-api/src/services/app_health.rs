use serde::Serialize;
use serde_json::{json, Value};
use std::time::{SystemTime, UNIX_EPOCH};

use crate::{
    middleware::auth::AuthenticatedSession,
    repositories::business_read::WorkbenchStaleScopeRow,
    services::{
        business_read::OaSyncStatusResponse,
        task_status::{BackgroundJobDto, BackgroundJobsActiveResponse},
    },
};

#[derive(Debug, Serialize)]
pub struct AppHealthSnapshot {
    pub version: i32,
    pub status: String,
    pub generated_at: String,
    pub session: AppHealthSession,
    pub oa_sync: OaSyncStatusResponse,
    pub workbench_read_model: WorkbenchReadModelHealth,
    pub background_jobs: BackgroundJobsHealth,
    pub dependencies: Value,
    pub metrics: Value,
    pub alerts: Value,
}

#[derive(Debug, Serialize)]
pub struct AppHealthSession {
    pub status: String,
    pub user: AppHealthUser,
    pub allowed: bool,
    pub access_tier: String,
    pub can_access_app: bool,
    pub can_mutate_data: bool,
    pub can_admin_access: bool,
}

#[derive(Debug, Serialize)]
pub struct AppHealthUser {
    pub user_id: String,
    pub username: String,
    pub display_name: String,
}

#[derive(Debug, Serialize)]
pub struct WorkbenchReadModelHealth {
    pub status: String,
    pub dirty_scopes: Vec<String>,
    pub matching_dirty_scopes: Vec<Value>,
    pub matching_running_scopes: Vec<String>,
    pub last_matching_error: Option<String>,
    pub rebuild_job_ids: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct BackgroundJobsHealth {
    pub active: usize,
    pub queued: usize,
    pub running: usize,
    pub attention: usize,
    pub primary_running: Option<BackgroundJobDto>,
    pub primary_attention: Option<BackgroundJobDto>,
    pub active_jobs: Vec<BackgroundJobDto>,
    pub attention_jobs: Vec<BackgroundJobDto>,
    pub jobs: Vec<BackgroundJobDto>,
}

pub fn build_app_health_snapshot(
    session: AuthenticatedSession,
    oa_sync: OaSyncStatusResponse,
    stale_scopes: Vec<WorkbenchStaleScopeRow>,
    background_jobs: BackgroundJobsActiveResponse,
) -> AppHealthSnapshot {
    let matching_running_scopes = matching_running_scopes(&background_jobs.active_jobs);
    let matching_dirty_scopes = matching_dirty_scope_payloads(&stale_scopes, &background_jobs);
    let dirty_scopes = dirty_scopes(&stale_scopes);
    let rebuild_jobs = rebuild_jobs(&background_jobs.active_jobs);
    let workbench_status = workbench_status(
        &oa_sync.status,
        &dirty_scopes,
        &matching_running_scopes,
        &rebuild_jobs,
    );
    let session_blocked = !session.allowed || !session.can_access_app;
    let dependency_unavailable = oa_sync.status == "error";
    let status = if session_blocked || dependency_unavailable {
        "blocked"
    } else if !dirty_scopes.is_empty()
        || !matching_running_scopes.is_empty()
        || !rebuild_jobs.is_empty()
        || !background_jobs.active_jobs.is_empty()
        || !background_jobs.attention_jobs.is_empty()
    {
        "busy"
    } else {
        "ok"
    }
    .to_owned();
    let background_jobs = background_jobs_health(background_jobs);

    AppHealthSnapshot {
        version: 1,
        status,
        generated_at: now_utc_iso(),
        session: session_payload(session, session_blocked),
        dependencies: json!({
            "oa_identity": {"status": "available"},
            "oa_sync": {
                "status": if dependency_unavailable { "unavailable" } else { "available" },
                "message": oa_sync.error_message.clone(),
            },
            "background_jobs": {"status": "available"},
            "state_store": {
                "status": "available",
                "storage_mode": "postgresql",
                "backend": "postgresql",
            },
        }),
        metrics: json!({
            "dirty_scope_count": dirty_scopes.len(),
            "workbench_matching_dirty_scope_count": matching_dirty_scopes.len(),
            "background_jobs_active_count": background_jobs.active,
            "background_jobs_running_count": background_jobs.running,
            "background_jobs_attention_count": background_jobs.attention,
            "active_alert_count": 0,
        }),
        alerts: json!({"active": [], "recent_recovered": []}),
        oa_sync,
        workbench_read_model: WorkbenchReadModelHealth {
            status: workbench_status,
            dirty_scopes,
            matching_dirty_scopes,
            matching_running_scopes,
            last_matching_error: last_matching_error(&background_jobs.attention_jobs),
            rebuild_job_ids: rebuild_jobs.into_iter().map(|job| job.job_id).collect(),
        },
        background_jobs,
    }
}

fn session_payload(session: AuthenticatedSession, blocked: bool) -> AppHealthSession {
    AppHealthSession {
        status: if blocked { "blocked" } else { "authenticated" }.to_owned(),
        user: AppHealthUser {
            user_id: session.identity.user_id,
            username: session.identity.username,
            display_name: session.identity.display_name,
        },
        allowed: session.allowed,
        access_tier: session.access_tier,
        can_access_app: session.can_access_app,
        can_mutate_data: session.can_mutate_data,
        can_admin_access: session.can_admin_access,
    }
}

fn workbench_status(
    oa_status: &str,
    dirty_scopes: &[String],
    matching_running_scopes: &[String],
    rebuild_jobs: &[BackgroundJobDto],
) -> String {
    if oa_status == "error" {
        "error"
    } else if !matching_running_scopes.is_empty() || !rebuild_jobs.is_empty() {
        "rebuilding"
    } else if !dirty_scopes.is_empty() {
        "stale"
    } else {
        "ready"
    }
    .to_owned()
}

fn background_jobs_health(background_jobs: BackgroundJobsActiveResponse) -> BackgroundJobsHealth {
    let queued = background_jobs
        .active_jobs
        .iter()
        .filter(|job| job.status == "queued")
        .count();
    let running = background_jobs
        .active_jobs
        .iter()
        .filter(|job| job.status == "running")
        .count();
    BackgroundJobsHealth {
        active: background_jobs.active_jobs.len(),
        queued,
        running,
        attention: background_jobs.attention_jobs.len(),
        primary_running: latest_job(
            background_jobs
                .active_jobs
                .iter()
                .filter(|job| job.status == "queued" || job.status == "running"),
        ),
        primary_attention: latest_job(background_jobs.attention_jobs.iter()),
        active_jobs: background_jobs.active_jobs,
        attention_jobs: background_jobs.attention_jobs,
        jobs: background_jobs.jobs,
    }
}

fn latest_job<'a>(jobs: impl Iterator<Item = &'a BackgroundJobDto>) -> Option<BackgroundJobDto> {
    jobs.max_by_key(|job| job.updated_at.clone()).cloned()
}

fn rebuild_jobs(active_jobs: &[BackgroundJobDto]) -> Vec<BackgroundJobDto> {
    active_jobs
        .iter()
        .filter(|job| {
            (job.status == "queued" || job.status == "running")
                && (matches!(
                    job.task_type.as_str(),
                    "workbench_rebuild"
                        | "workbench_read_model_rebuild"
                        | "oa_sync_workbench_rebuild"
                ) || (job.task_type.contains("workbench") && job.task_type.contains("rebuild")))
        })
        .cloned()
        .collect()
}

fn matching_running_scopes(active_jobs: &[BackgroundJobDto]) -> Vec<String> {
    let mut scopes: Vec<String> = active_jobs
        .iter()
        .filter(|job| {
            job.task_type == "workbench_matching"
                && (job.status == "queued" || job.status == "running")
        })
        .flat_map(|job| job.affected_months.iter().chain(job.affected_scopes.iter()))
        .filter_map(|scope| normalize_scope(scope))
        .collect();
    scopes.sort();
    scopes.dedup();
    scopes
}

fn dirty_scopes(stale_scopes: &[WorkbenchStaleScopeRow]) -> Vec<String> {
    let mut scopes: Vec<String> = stale_scopes
        .iter()
        .filter_map(|row| normalize_scope(&row.scope))
        .collect();
    scopes.sort();
    scopes.dedup();
    scopes
}

fn matching_dirty_scope_payloads(
    stale_scopes: &[WorkbenchStaleScopeRow],
    background_jobs: &BackgroundJobsActiveResponse,
) -> Vec<Value> {
    stale_scopes
        .iter()
        .filter_map(|row| {
            let scope_month = normalize_scope(&row.scope)?;
            Some(json!({
                "scope_month": scope_month,
                "reason": row.stale_reason,
                "updated_at": row.updated_at,
                "last_error": matching_error_for_scope(&scope_month, &background_jobs.attention_jobs),
                "source": "read_model.workbench_snapshots",
            }))
        })
        .collect()
}

fn matching_error_for_scope(scope: &str, attention_jobs: &[BackgroundJobDto]) -> Option<String> {
    attention_jobs
        .iter()
        .filter(|job| job.task_type == "workbench_matching")
        .filter(|job| {
            job.affected_months
                .iter()
                .chain(job.affected_scopes.iter())
                .filter_map(|value| normalize_scope(value))
                .any(|value| value == scope)
        })
        .filter_map(|job| job.error.clone())
        .last()
}

fn last_matching_error(attention_jobs: &[BackgroundJobDto]) -> Option<String> {
    attention_jobs
        .iter()
        .rev()
        .find(|job| job.task_type == "workbench_matching")
        .and_then(|job| job.error.clone())
}

fn normalize_scope(value: &str) -> Option<String> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return None;
    }
    if trimmed.len() >= 7 && trimmed.as_bytes().get(4) == Some(&b'-') {
        return Some(trimmed[..7].to_owned());
    }
    Some(trimmed.to_owned())
}

fn now_utc_iso() -> String {
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    let days = seconds.div_euclid(86_400);
    let seconds_of_day = seconds.rem_euclid(86_400);
    let (year, month, day) = civil_from_days(days);
    let hour = seconds_of_day / 3_600;
    let minute = (seconds_of_day % 3_600) / 60;
    let second = seconds_of_day % 60;
    format!("{year:04}-{month:02}-{day:02}T{hour:02}:{minute:02}:{second:02}Z")
}

fn civil_from_days(days_since_epoch: i64) -> (i64, i64, i64) {
    let z = days_since_epoch + 719_468;
    let era = if z >= 0 { z } else { z - 146_096 }.div_euclid(146_097);
    let day_of_era = z - era * 146_097;
    let year_of_era = (day_of_era - day_of_era / 1_460 + day_of_era / 36_524
        - day_of_era / 146_096)
        .div_euclid(365);
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_piece = (5 * day_of_year + 2).div_euclid(153);
    let day = day_of_year - (153 * month_piece + 2).div_euclid(5) + 1;
    let month = month_piece + if month_piece < 10 { 3 } else { -9 };
    if month <= 2 {
        year += 1;
    }
    (year, month, day)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{middleware::auth::OaUserIdentity, services::task_status::BackgroundJobDto};

    #[test]
    fn app_health_reports_stale_and_matching_status_from_postgres_facts() {
        let snapshot = build_app_health_snapshot(
            session(true),
            oa_sync("synced"),
            vec![WorkbenchStaleScopeRow {
                scope: "2026-05".to_owned(),
                stale_reason: Some("import.confirmed".to_owned()),
                updated_at: "2026-05-17T02:00:00Z".to_owned(),
            }],
            BackgroundJobsActiveResponse {
                jobs: vec![job(
                    "matching-running",
                    "workbench_matching",
                    "running",
                    None,
                )],
                active_jobs: vec![job(
                    "matching-running",
                    "workbench_matching",
                    "running",
                    None,
                )],
                attention_jobs: vec![job(
                    "matching-failed",
                    "workbench_matching",
                    "failed",
                    Some("候选生成失败"),
                )],
            },
        );

        assert_eq!(snapshot.status, "busy");
        assert_eq!(snapshot.workbench_read_model.status, "rebuilding");
        assert_eq!(snapshot.workbench_read_model.dirty_scopes, vec!["2026-05"]);
        assert_eq!(
            snapshot.workbench_read_model.matching_running_scopes,
            vec!["2026-05"]
        );
        assert_eq!(
            snapshot.workbench_read_model.last_matching_error.as_deref(),
            Some("候选生成失败")
        );
        assert_eq!(snapshot.background_jobs.running, 1);
        assert_eq!(snapshot.background_jobs.attention, 1);
        assert_eq!(
            snapshot.dependencies["state_store"]["backend"],
            "postgresql"
        );
    }

    #[test]
    fn app_health_blocks_when_session_cannot_access_app() {
        let snapshot = build_app_health_snapshot(
            session(false),
            oa_sync("synced"),
            Vec::new(),
            BackgroundJobsActiveResponse {
                jobs: Vec::new(),
                active_jobs: Vec::new(),
                attention_jobs: Vec::new(),
            },
        );

        assert_eq!(snapshot.status, "blocked");
        assert_eq!(snapshot.session.status, "blocked");
    }

    fn session(can_access_app: bool) -> AuthenticatedSession {
        AuthenticatedSession {
            identity: OaUserIdentity {
                user_id: "u-1".to_owned(),
                username: "ops.user".to_owned(),
                nickname: "ops".to_owned(),
                display_name: "Ops User".to_owned(),
                dept_id: None,
                dept_name: None,
                avatar: None,
                roles: vec!["admin".to_owned()],
                permissions: vec!["finops:access".to_owned()],
            },
            allowed: can_access_app,
            access_tier: if can_access_app { "admin" } else { "blocked" }.to_owned(),
            can_access_app,
            can_mutate_data: can_access_app,
            can_admin_access: can_access_app,
            request_id: Some("req-1".to_owned()),
        }
    }

    fn oa_sync(status: &str) -> OaSyncStatusResponse {
        OaSyncStatusResponse {
            status: status.to_owned(),
            last_run_id: None,
            last_started_at: None,
            last_finished_at: None,
            last_synced_at: Some("2026-05-17T01:00:00Z".to_owned()),
            source_system: Some("oa".to_owned()),
            scope: Some("all".to_owned()),
            processed_count: 0,
            success_count: 0,
            failed_count: 0,
            error_message: None,
            source: "postgresql.app.oa_sync_runs",
        }
    }

    fn job(id: &str, task_type: &str, status: &str, error: Option<&str>) -> BackgroundJobDto {
        BackgroundJobDto {
            job_id: id.to_owned(),
            task_type: task_type.to_owned(),
            label: "生成关联台候选".to_owned(),
            short_label: "Running".to_owned(),
            owner_user_id: None,
            visibility: "system".to_owned(),
            status: status.to_owned(),
            phase: "workbench_matching".to_owned(),
            current: 0,
            total: 1,
            percent: 0,
            message: "running".to_owned(),
            result_summary: json!({}),
            error: error.map(str::to_owned),
            idempotency_key: None,
            source: json!({}),
            affected_scopes: Vec::new(),
            affected_months: vec!["2026-05-01".to_owned()],
            retryable: true,
            acknowledgeable: status == "failed",
            attention: status == "failed",
            superseded_by_job_id: None,
            created_at: "2026-05-17T01:00:00Z".to_owned(),
            started_at: Some("2026-05-17T01:00:00Z".to_owned()),
            updated_at: "2026-05-17T01:05:00Z".to_owned(),
            finished_at: None,
            acknowledged_at: None,
            superseded_at: None,
        }
    }
}
