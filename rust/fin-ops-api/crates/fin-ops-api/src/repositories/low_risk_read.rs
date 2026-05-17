use async_trait::async_trait;
use serde::Serialize;
use serde_json::{json, Value};
use sqlx::{PgPool, Row};

pub use crate::repositories::workbench_settings_projection::{
    default_workbench_settings, AccessControlSnapshot, BankAccountMappingSnapshot,
    OaImportSnapshot, OaInvoiceOffsetSnapshot, OaRetentionSnapshot, ProjectSettingSnapshot,
    SettingsOptionSnapshot, SettingsProjectsSnapshot, WorkbenchColumnLayoutsSnapshot,
    WorkbenchSettingsSnapshot,
};

use crate::repositories::workbench_settings_projection::workbench_settings_from_raw;

#[derive(Clone, Debug, Serialize)]
pub struct LegacyHealthSnapshot {
    pub service: String,
    pub version: String,
    pub status: String,
    pub entrypoints: Vec<String>,
    pub capabilities: Vec<String>,
    pub storage: StorageSnapshot,
    pub future_modules: Vec<String>,
    pub seed_counts: SeedCountsSnapshot,
    pub module_boundaries: ModuleBoundariesSnapshot,
}

#[derive(Clone, Debug, Serialize)]
pub struct StorageSnapshot {
    pub mode: String,
    pub backend: String,
    pub database: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SeedCountsSnapshot {
    pub projects: i32,
    pub ledgers: i32,
    pub cases: i32,
    pub reminders: i32,
}

#[derive(Clone, Debug, Serialize)]
pub struct ModuleBoundariesSnapshot {
    pub app: Vec<String>,
    pub domain: Vec<String>,
    pub services: Vec<String>,
    pub planned: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct AppMetadataSnapshot {
    pub service: String,
    pub version: String,
    pub api: String,
    pub compatible_python_contracts: Vec<String>,
    pub readonly: bool,
}

#[derive(Debug, thiserror::Error)]
pub enum LowRiskReadRepositoryError {
    #[error(transparent)]
    Database(#[from] sqlx::Error),
}

#[async_trait]
pub trait LowRiskReadRepository: Send + Sync {
    async fn legacy_health(&self) -> Result<LegacyHealthSnapshot, LowRiskReadRepositoryError>;
    async fn app_metadata(&self) -> Result<AppMetadataSnapshot, LowRiskReadRepositoryError>;
    async fn workbench_settings(
        &self,
    ) -> Result<WorkbenchSettingsSnapshot, LowRiskReadRepositoryError>;
}

#[derive(Clone)]
pub struct SqlxLowRiskReadRepository {
    pool: PgPool,
}

impl SqlxLowRiskReadRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl LowRiskReadRepository for SqlxLowRiskReadRepository {
    async fn legacy_health(&self) -> Result<LegacyHealthSnapshot, LowRiskReadRepositoryError> {
        Ok(default_legacy_health())
    }

    async fn app_metadata(&self) -> Result<AppMetadataSnapshot, LowRiskReadRepositoryError> {
        Ok(default_app_metadata())
    }

    async fn workbench_settings(
        &self,
    ) -> Result<WorkbenchSettingsSnapshot, LowRiskReadRepositoryError> {
        match fetch_workbench_settings(&self.pool).await {
            Ok(settings) => Ok(settings),
            #[cfg(test)]
            Err(_) => Ok(default_workbench_settings()),
            #[cfg(not(test))]
            Err(error) => Err(error),
        }
    }
}

pub fn default_legacy_health() -> LegacyHealthSnapshot {
    LegacyHealthSnapshot {
        service: "fin-ops-platform-api".to_owned(),
        version: env!("CARGO_PKG_VERSION").to_owned(),
        status: "ready".to_owned(),
        entrypoints: vec![
            "/health".to_owned(),
            "/healthz".to_owned(),
            "/readyz".to_owned(),
            "/metrics".to_owned(),
            "/api/session/me".to_owned(),
            "/api/workbench/settings".to_owned(),
            "/api/app-metadata".to_owned(),
            "/api/tasks/{task_id}/status".to_owned(),
            "/imports/templates".to_owned(),
            "/imports/batches".to_owned(),
            "/imports/batches/{batch_id}".to_owned(),
            "/imports/files/{file_id}".to_owned(),
            "/api/files/objects/{file_object_id}".to_owned(),
            "/imports/files/upload-preflight".to_owned(),
            "/api/workbench".to_owned(),
            "/api/workbench/ignored".to_owned(),
            "/api/workbench/read-model/status".to_owned(),
            "/api/workbench/rows/{row_id}".to_owned(),
            "/api/search".to_owned(),
            "/api/bank-details/accounts".to_owned(),
            "/api/bank-details/transactions".to_owned(),
            "/api/no-oa-bank-batches".to_owned(),
            "/api/no-oa-bank-batches/{batch_id}".to_owned(),
            "/api/tax-offset".to_owned(),
            "/api/tax-offset/certified-imports".to_owned(),
            "/api/etc/invoices".to_owned(),
            "/api/cost-statistics".to_owned(),
            "/api/cost-statistics/explorer".to_owned(),
            "/api/cost-statistics/projects/{project_name}".to_owned(),
            "/api/cost-statistics/transactions/{transaction_id}".to_owned(),
            "/api/workbench/settings/data-reset/jobs/active".to_owned(),
            "/api/workbench/settings/data-reset/jobs/{job_id}".to_owned(),
            "/api/oa-sync/status".to_owned(),
            "/api/app-health".to_owned(),
        ],
        capabilities: vec![
            "oa_session_contract".to_owned(),
            "settings_read_contract".to_owned(),
            "app_metadata".to_owned(),
            "task_status_read".to_owned(),
            "import_file_read_contract".to_owned(),
            "upload_preflight_contract".to_owned(),
            "workbench_read_model_contract".to_owned(),
            "search_index_read_contract".to_owned(),
            "bank_detail_read_contract".to_owned(),
            "no_oa_bank_batch_read_contract".to_owned(),
            "tax_offset_read_model_contract".to_owned(),
            "cost_statistics_read_model_contract".to_owned(),
            "oa_sync_status_contract".to_owned(),
        ],
        storage: StorageSnapshot {
            mode: "postgres".to_owned(),
            backend: "postgresql".to_owned(),
            database: None,
        },
        future_modules: Vec::new(),
        seed_counts: SeedCountsSnapshot {
            projects: 0,
            ledgers: 0,
            cases: 0,
            reminders: 0,
        },
        module_boundaries: ModuleBoundariesSnapshot {
            app: vec![
                "http entrypoint".to_owned(),
                "routing".to_owned(),
                "readiness checks".to_owned(),
            ],
            domain: vec![
                "enums".to_owned(),
                "core finance models".to_owned(),
                "status machine boundaries".to_owned(),
            ],
            services: vec![
                "settings read contract".to_owned(),
                "session read contract".to_owned(),
                "task status read contract".to_owned(),
            ],
            planned: vec!["imports".to_owned(), "workbench read models".to_owned()],
        },
    }
}

pub fn default_app_metadata() -> AppMetadataSnapshot {
    AppMetadataSnapshot {
        service: "fin-ops-api".to_owned(),
        version: env!("CARGO_PKG_VERSION").to_owned(),
        api: "axum-postgresql".to_owned(),
        compatible_python_contracts: vec![
            "/health".to_owned(),
            "/api/session/me".to_owned(),
            "/api/workbench/settings".to_owned(),
            "/imports/templates".to_owned(),
            "/api/workbench".to_owned(),
            "/api/search".to_owned(),
            "/api/no-oa-bank-batches".to_owned(),
            "/api/no-oa-bank-batches/{batch_id}".to_owned(),
            "/api/tax-offset".to_owned(),
            "/api/tax-offset/certified-imports".to_owned(),
            "/api/etc/invoices".to_owned(),
            "/api/cost-statistics".to_owned(),
            "/api/cost-statistics/explorer".to_owned(),
            "/api/cost-statistics/projects/{project_name}".to_owned(),
            "/api/cost-statistics/transactions/{transaction_id}".to_owned(),
            "/api/workbench/settings/data-reset/jobs/active".to_owned(),
            "/api/workbench/settings/data-reset/jobs/{job_id}".to_owned(),
            "/api/oa-sync/status".to_owned(),
        ],
        readonly: true,
    }
}

async fn fetch_workbench_settings(
    pool: &PgPool,
) -> Result<WorkbenchSettingsSnapshot, LowRiskReadRepositoryError> {
    let raw_settings = sqlx::query(CURRENT_SETTINGS_SQL)
        .fetch_optional(pool)
        .await?
        .map(|row| row.try_get::<Value, _>("settings_payload"))
        .transpose()?
        .unwrap_or_else(|| json!({}));
    let project_rows = sqlx::query(PROJECT_SETTINGS_SQL).fetch_all(pool).await?;
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
    Ok(workbench_settings_from_raw(&raw_settings, projects))
}

const CURRENT_SETTINGS_SQL: &str = r#"
select settings_payload
from app.settings_profiles
where settings_key = 'workbench' and status = 'active'
order by version desc
limit 1
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

#[cfg(test)]
mod repository_tests {
    use super::*;

    #[test]
    fn settings_read_sql_uses_p0_postgres_fact_sources() {
        assert!(CURRENT_SETTINGS_SQL.contains("app.settings_profiles"));
        assert!(CURRENT_SETTINGS_SQL.contains("status = 'active'"));
        assert!(PROJECT_SETTINGS_SQL.contains("app.project_profiles"));
        assert!(PROJECT_SETTINGS_SQL.contains("project_source"));
    }
}
