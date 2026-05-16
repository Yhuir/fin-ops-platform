use async_trait::async_trait;
use serde::Serialize;
use sqlx::PgPool;

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

#[derive(Clone, Debug, Serialize)]
pub struct WorkbenchSettingsSnapshot {
    pub projects: SettingsProjectsSnapshot,
    pub bank_account_mappings: Vec<BankAccountMappingSnapshot>,
    pub access_control: AccessControlSnapshot,
    pub workbench_column_layouts: WorkbenchColumnLayoutsSnapshot,
    pub oa_retention: OaRetentionSnapshot,
    pub oa_import: OaImportSnapshot,
    pub oa_invoice_offset: OaInvoiceOffsetSnapshot,
}

#[derive(Clone, Debug, Serialize)]
pub struct SettingsProjectsSnapshot {
    pub active: Vec<ProjectSettingSnapshot>,
    pub completed: Vec<ProjectSettingSnapshot>,
    pub completed_project_ids: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct ProjectSettingSnapshot {
    pub id: String,
    pub project_code: String,
    pub project_name: String,
    pub project_status: String,
    pub source: String,
    pub department_name: Option<String>,
    pub owner_name: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct BankAccountMappingSnapshot {
    pub id: String,
    pub last4: String,
    pub bank_name: String,
    pub short_name: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct AccessControlSnapshot {
    pub allowed_usernames: Vec<String>,
    pub readonly_export_usernames: Vec<String>,
    pub admin_usernames: Vec<String>,
    pub full_access_usernames: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct WorkbenchColumnLayoutsSnapshot {
    pub oa: Vec<String>,
    pub bank: Vec<String>,
    pub invoice: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct OaRetentionSnapshot {
    pub cutoff_date: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct OaImportSnapshot {
    pub form_types: Vec<String>,
    pub statuses: Vec<String>,
    pub available_form_types: Vec<SettingsOptionSnapshot>,
    pub available_statuses: Vec<SettingsOptionSnapshot>,
}

#[derive(Clone, Debug, Serialize)]
pub struct SettingsOptionSnapshot {
    pub id: String,
    pub label: String,
}

#[derive(Clone, Debug, Serialize)]
pub struct OaInvoiceOffsetSnapshot {
    pub applicant_names: Vec<String>,
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
    _pool: PgPool,
}

impl SqlxLowRiskReadRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { _pool: pool }
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
        Ok(default_workbench_settings())
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

pub fn default_workbench_settings() -> WorkbenchSettingsSnapshot {
    WorkbenchSettingsSnapshot {
        projects: SettingsProjectsSnapshot {
            active: Vec::new(),
            completed: Vec::new(),
            completed_project_ids: Vec::new(),
        },
        bank_account_mappings: Vec::new(),
        access_control: AccessControlSnapshot {
            allowed_usernames: vec!["YNSYLP005".to_owned()],
            readonly_export_usernames: Vec::new(),
            admin_usernames: vec!["YNSYLP005".to_owned()],
            full_access_usernames: Vec::new(),
        },
        workbench_column_layouts: WorkbenchColumnLayoutsSnapshot {
            oa: vec![
                "applicant".to_owned(),
                "projectName".to_owned(),
                "amount".to_owned(),
                "counterparty".to_owned(),
                "reason".to_owned(),
            ],
            bank: vec![
                "counterparty".to_owned(),
                "amount".to_owned(),
                "loanRepaymentDate".to_owned(),
                "note".to_owned(),
            ],
            invoice: vec![
                "sellerName".to_owned(),
                "buyerName".to_owned(),
                "issueDate".to_owned(),
                "amount".to_owned(),
                "grossAmount".to_owned(),
            ],
        },
        oa_retention: OaRetentionSnapshot {
            cutoff_date: "2026-01-01".to_owned(),
        },
        oa_import: OaImportSnapshot {
            form_types: vec!["payment_request".to_owned(), "expense_claim".to_owned()],
            statuses: vec!["completed".to_owned()],
            available_form_types: vec![
                SettingsOptionSnapshot {
                    id: "payment_request".to_owned(),
                    label: "\u{652f}\u{4ed8}\u{7533}\u{8bf7}".to_owned(),
                },
                SettingsOptionSnapshot {
                    id: "expense_claim".to_owned(),
                    label: "\u{65e5}\u{5e38}\u{62a5}\u{9500}".to_owned(),
                },
            ],
            available_statuses: vec![
                SettingsOptionSnapshot {
                    id: "completed".to_owned(),
                    label: "\u{5df2}\u{5b8c}\u{6210}".to_owned(),
                },
                SettingsOptionSnapshot {
                    id: "in_progress".to_owned(),
                    label: "\u{8fdb}\u{884c}\u{4e2d}".to_owned(),
                },
            ],
        },
        oa_invoice_offset: OaInvoiceOffsetSnapshot {
            applicant_names: vec!["\u{5468}\u{6d01}\u{83b9}".to_owned()],
        },
    }
}
