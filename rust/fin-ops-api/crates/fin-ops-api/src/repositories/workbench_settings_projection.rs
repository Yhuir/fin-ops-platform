use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

const DEFAULT_ADMIN_USERNAME: &str = "YNSYLP005";
const DEFAULT_OA_RETENTION_CUTOFF_DATE: &str = "2026-01-01";
const DEFAULT_OA_INVOICE_OFFSET_APPLICANT: &str = "周洁莹";
const DEFAULT_OA_IMPORT_FORM_TYPES: &[&str] = &["payment_request", "expense_claim"];
const DEFAULT_OA_IMPORT_STATUSES: &[&str] = &["completed"];
const OA_IMPORT_FORM_TYPE_OPTIONS: &[(&str, &str)] = &[
    ("payment_request", "支付申请"),
    ("expense_claim", "日常报销"),
];
const OA_IMPORT_STATUS_OPTIONS: &[(&str, &str)] =
    &[("completed", "已完成"), ("in_progress", "进行中")];
const OA_LAYOUT_DEFAULT: &[&str] = &[
    "applicant",
    "projectName",
    "amount",
    "counterparty",
    "reason",
];
const BANK_LAYOUT_DEFAULT: &[&str] = &["counterparty", "amount", "loanRepaymentDate", "note"];
const INVOICE_LAYOUT_DEFAULT: &[&str] = &[
    "sellerName",
    "buyerName",
    "issueDate",
    "amount",
    "grossAmount",
];

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkbenchSettingsSnapshot {
    pub projects: SettingsProjectsSnapshot,
    pub bank_account_mappings: Vec<BankAccountMappingSnapshot>,
    pub access_control: AccessControlSnapshot,
    pub workbench_column_layouts: WorkbenchColumnLayoutsSnapshot,
    pub oa_retention: OaRetentionSnapshot,
    pub oa_import: OaImportSnapshot,
    pub oa_invoice_offset: OaInvoiceOffsetSnapshot,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SettingsProjectsSnapshot {
    pub active: Vec<ProjectSettingSnapshot>,
    pub completed: Vec<ProjectSettingSnapshot>,
    pub completed_project_ids: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct ProjectSettingSnapshot {
    pub id: String,
    pub project_code: String,
    pub project_name: String,
    pub project_status: String,
    pub source: String,
    pub department_name: Option<String>,
    pub owner_name: Option<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct BankAccountMappingSnapshot {
    pub id: String,
    pub last4: String,
    pub bank_name: String,
    pub short_name: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct AccessControlSnapshot {
    pub allowed_usernames: Vec<String>,
    pub readonly_export_usernames: Vec<String>,
    pub admin_usernames: Vec<String>,
    pub full_access_usernames: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct WorkbenchColumnLayoutsSnapshot {
    pub oa: Vec<String>,
    pub bank: Vec<String>,
    pub invoice: Vec<String>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct OaRetentionSnapshot {
    pub cutoff_date: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct OaImportSnapshot {
    pub form_types: Vec<String>,
    pub statuses: Vec<String>,
    pub available_form_types: Vec<SettingsOptionSnapshot>,
    pub available_statuses: Vec<SettingsOptionSnapshot>,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct SettingsOptionSnapshot {
    pub id: String,
    pub label: String,
}

#[derive(Clone, Debug, Serialize, Deserialize, PartialEq, Eq)]
pub struct OaInvoiceOffsetSnapshot {
    pub applicant_names: Vec<String>,
}

pub fn default_workbench_settings() -> WorkbenchSettingsSnapshot {
    workbench_settings_from_raw(&json!({}), Vec::new())
}

pub fn workbench_settings_value_from_raw(
    raw: &Value,
    projects: Vec<ProjectSettingSnapshot>,
) -> Value {
    serde_json::to_value(workbench_settings_from_raw(raw, projects))
        .expect("workbench settings projection should serialize")
}

pub fn workbench_settings_from_raw(
    raw: &Value,
    projects: Vec<ProjectSettingSnapshot>,
) -> WorkbenchSettingsSnapshot {
    let raw = raw.as_object();
    let completed_project_ids =
        normalized_string_list(raw.and_then(|value| value.get("completed_project_ids")));
    let completed_project_id_set = completed_project_ids
        .iter()
        .cloned()
        .collect::<std::collections::BTreeSet<_>>();
    let (active, completed) = partition_projects(projects, &completed_project_id_set);
    let admin_usernames = admin_usernames(raw.and_then(|value| value.get("admin_usernames")));
    let allowed_usernames = allowed_usernames(
        raw.and_then(|value| value.get("allowed_usernames")),
        &admin_usernames,
    );
    let readonly_export_usernames = readonly_export_usernames(
        raw.and_then(|value| value.get("readonly_export_usernames")),
        &allowed_usernames,
        &admin_usernames,
    );
    let full_access_usernames = full_access_usernames(
        &allowed_usernames,
        &readonly_export_usernames,
        &admin_usernames,
    );

    WorkbenchSettingsSnapshot {
        projects: SettingsProjectsSnapshot {
            active,
            completed,
            completed_project_ids,
        },
        bank_account_mappings: bank_account_mappings(
            raw.and_then(|value| value.get("bank_account_mappings")),
        ),
        access_control: AccessControlSnapshot {
            allowed_usernames,
            readonly_export_usernames,
            admin_usernames,
            full_access_usernames,
        },
        workbench_column_layouts: WorkbenchColumnLayoutsSnapshot {
            oa: normalized_layout(
                raw.and_then(|value| value.get("workbench_column_layouts"))
                    .and_then(|value| value.get("oa")),
                OA_LAYOUT_DEFAULT,
            ),
            bank: normalized_layout(
                raw.and_then(|value| value.get("workbench_column_layouts"))
                    .and_then(|value| value.get("bank")),
                BANK_LAYOUT_DEFAULT,
            ),
            invoice: normalized_layout(
                raw.and_then(|value| value.get("workbench_column_layouts"))
                    .and_then(|value| value.get("invoice")),
                INVOICE_LAYOUT_DEFAULT,
            ),
        },
        oa_retention: OaRetentionSnapshot {
            cutoff_date: normalized_iso_date(
                raw.and_then(|value| value.get("oa_retention"))
                    .and_then(|value| value.get("cutoff_date")),
            ),
        },
        oa_import: OaImportSnapshot {
            form_types: normalized_option_list(
                raw.and_then(|value| value.get("oa_import"))
                    .and_then(|value| value.get("form_types")),
                OA_IMPORT_FORM_TYPE_OPTIONS,
                DEFAULT_OA_IMPORT_FORM_TYPES,
            ),
            statuses: normalized_option_list(
                raw.and_then(|value| value.get("oa_import"))
                    .and_then(|value| value.get("statuses")),
                OA_IMPORT_STATUS_OPTIONS,
                DEFAULT_OA_IMPORT_STATUSES,
            ),
            available_form_types: option_snapshots(OA_IMPORT_FORM_TYPE_OPTIONS),
            available_statuses: option_snapshots(OA_IMPORT_STATUS_OPTIONS),
        },
        oa_invoice_offset: OaInvoiceOffsetSnapshot {
            applicant_names: normalized_applicant_names(
                raw.and_then(|value| value.get("oa_invoice_offset"))
                    .and_then(|value| value.get("applicant_names")),
            ),
        },
    }
}

fn partition_projects(
    projects: Vec<ProjectSettingSnapshot>,
    completed_project_ids: &std::collections::BTreeSet<String>,
) -> (Vec<ProjectSettingSnapshot>, Vec<ProjectSettingSnapshot>) {
    let mut active = Vec::new();
    let mut completed = Vec::new();
    for mut project in projects {
        if completed_project_ids.contains(&project.id) {
            project.project_status = "completed".to_owned();
            completed.push(project);
        } else {
            project.project_status = "active".to_owned();
            active.push(project);
        }
    }
    (active, completed)
}

fn bank_account_mappings(value: Option<&Value>) -> Vec<BankAccountMappingSnapshot> {
    let mut seen = std::collections::BTreeSet::new();
    let mut mappings = value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_object)
        .filter_map(|item| {
            let last4 = trimmed(item.get("last4"))?;
            let bank_name = trimmed(item.get("bank_name"))?;
            if last4.len() != 4 || !last4.chars().all(|ch| ch.is_ascii_digit()) {
                return None;
            }
            if !seen.insert(last4.clone()) {
                return None;
            }
            Some(BankAccountMappingSnapshot {
                id: trimmed(item.get("id")).unwrap_or_else(|| format!("bank_mapping_{last4}")),
                last4,
                bank_name,
                short_name: trimmed(item.get("short_name")).unwrap_or_default(),
            })
        })
        .collect::<Vec<_>>();
    mappings.sort_by(|left, right| {
        left.bank_name
            .cmp(&right.bank_name)
            .then(left.last4.cmp(&right.last4))
    });
    mappings
}

fn admin_usernames(value: Option<&Value>) -> Vec<String> {
    let mut values = normalized_string_list(value);
    if !values.iter().any(|item| item == DEFAULT_ADMIN_USERNAME) {
        values.push(DEFAULT_ADMIN_USERNAME.to_owned());
    }
    values.sort();
    values
}

fn allowed_usernames(value: Option<&Value>, admin_usernames: &[String]) -> Vec<String> {
    let mut values = normalized_string_list(value);
    for username in admin_usernames {
        if !values.iter().any(|item| item == username) {
            values.push(username.clone());
        }
    }
    values.sort();
    values
}

fn readonly_export_usernames(
    value: Option<&Value>,
    allowed_usernames: &[String],
    admin_usernames: &[String],
) -> Vec<String> {
    normalized_string_list(value)
        .into_iter()
        .filter(|username| {
            allowed_usernames.contains(username) && !admin_usernames.contains(username)
        })
        .collect()
}

fn full_access_usernames(
    allowed_usernames: &[String],
    readonly_export_usernames: &[String],
    admin_usernames: &[String],
) -> Vec<String> {
    allowed_usernames
        .iter()
        .filter(|username| {
            !readonly_export_usernames.contains(username) && !admin_usernames.contains(username)
        })
        .cloned()
        .collect()
}

fn normalized_string_list(value: Option<&Value>) -> Vec<String> {
    let mut values = value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(trimmed_value)
        .collect::<Vec<_>>();
    values.sort();
    values.dedup();
    values
}

fn normalized_layout(value: Option<&Value>, defaults: &[&str]) -> Vec<String> {
    let mut keys = Vec::new();
    let mut seen = std::collections::BTreeSet::new();
    for key in value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(trimmed_value)
    {
        if defaults.contains(&key.as_str()) && seen.insert(key.clone()) {
            keys.push(key);
        }
    }
    for key in defaults {
        if seen.insert((*key).to_owned()) {
            keys.push((*key).to_owned());
        }
    }
    keys
}

fn normalized_iso_date(value: Option<&Value>) -> String {
    let Some(value) = trimmed(value) else {
        return DEFAULT_OA_RETENTION_CUTOFF_DATE.to_owned();
    };
    if is_iso_date(&value) {
        value
    } else {
        DEFAULT_OA_RETENTION_CUTOFF_DATE.to_owned()
    }
}

fn normalized_option_list(
    value: Option<&Value>,
    options: &[(&str, &str)],
    defaults: &[&str],
) -> Vec<String> {
    let allowed = options
        .iter()
        .map(|(id, _)| *id)
        .collect::<std::collections::BTreeSet<_>>();
    let seen = value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(trimmed_value)
        .filter(|item| allowed.contains(item.as_str()))
        .collect::<std::collections::BTreeSet<_>>();
    if seen.is_empty() && value.is_none() {
        return defaults.iter().map(|item| (*item).to_owned()).collect();
    }
    options
        .iter()
        .map(|(id, _)| *id)
        .filter(|id| seen.contains(*id))
        .map(str::to_owned)
        .collect()
}

fn normalized_applicant_names(value: Option<&Value>) -> Vec<String> {
    match value {
        None => vec![DEFAULT_OA_INVOICE_OFFSET_APPLICANT.to_owned()],
        Some(_) => normalized_string_list(value),
    }
}

fn option_snapshots(options: &[(&str, &str)]) -> Vec<SettingsOptionSnapshot> {
    options
        .iter()
        .map(|(id, label)| SettingsOptionSnapshot {
            id: (*id).to_owned(),
            label: (*label).to_owned(),
        })
        .collect()
}

fn trimmed(value: Option<&Value>) -> Option<String> {
    value.and_then(trimmed_value)
}

fn trimmed_value(value: &Value) -> Option<String> {
    let value = match value {
        Value::String(value) => value.trim().to_owned(),
        Value::Null => String::new(),
        other => other.to_string().trim().to_owned(),
    };
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}

fn is_iso_date(value: &str) -> bool {
    let parts = value.split('-').collect::<Vec<_>>();
    parts.len() == 3
        && parts[0].len() == 4
        && parts[1].len() == 2
        && parts[2].len() == 2
        && parts
            .iter()
            .all(|part| part.chars().all(|ch| ch.is_ascii_digit()))
        && matches!(parts[1].parse::<u8>(), Ok(1..=12))
        && matches!(parts[2].parse::<u8>(), Ok(1..=31))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn projection_matches_legacy_settings_normalization() {
        let payload = workbench_settings_from_raw(
            &json!({
                "completed_project_ids": ["project-2", "project-2"],
                "bank_account_mappings": [
                    {"last4": "0001", "bank_name": "B Bank", "short_name": "B"},
                    {"last4": "bad", "bank_name": "ignored"},
                    {"last4": "0002", "bank_name": "A Bank", "short_name": "A"}
                ],
                "allowed_usernames": ["FULL001", "READONLY001"],
                "readonly_export_usernames": ["READONLY001", "YNSYLP005", "OUTSIDER"],
                "admin_usernames": ["ADMIN002"],
                "workbench_column_layouts": {"oa": ["projectName", "projectName", "invalid"]},
                "oa_import": {"form_types": ["expense_claim", "payment_request"], "statuses": ["in_progress", "completed"]},
                "oa_invoice_offset": {"applicant_names": [" 周洁莹 ", "李四", "周洁莹"]}
            }),
            vec![
                ProjectSettingSnapshot {
                    id: "project-1".to_owned(),
                    project_code: "P001".to_owned(),
                    project_name: "Active".to_owned(),
                    project_status: "active".to_owned(),
                    source: "manual".to_owned(),
                    department_name: None,
                    owner_name: None,
                },
                ProjectSettingSnapshot {
                    id: "project-2".to_owned(),
                    project_code: "P002".to_owned(),
                    project_name: "Completed".to_owned(),
                    project_status: "active".to_owned(),
                    source: "oa".to_owned(),
                    department_name: None,
                    owner_name: None,
                },
            ],
        );

        assert_eq!(payload.projects.active[0].project_name, "Active");
        assert_eq!(payload.projects.completed[0].project_status, "completed");
        assert_eq!(
            payload
                .bank_account_mappings
                .iter()
                .map(|item| item.last4.as_str())
                .collect::<Vec<_>>(),
            vec!["0002", "0001"]
        );
        assert_eq!(
            payload.access_control.allowed_usernames,
            vec!["ADMIN002", "FULL001", "READONLY001", "YNSYLP005"]
        );
        assert_eq!(
            payload.access_control.readonly_export_usernames,
            vec!["READONLY001"]
        );
        assert_eq!(
            payload.access_control.full_access_usernames,
            vec!["FULL001"]
        );
        assert_eq!(
            payload.workbench_column_layouts.oa,
            vec![
                "projectName",
                "applicant",
                "amount",
                "counterparty",
                "reason"
            ]
        );
        assert_eq!(payload.oa_import.statuses, vec!["completed", "in_progress"]);
        assert_eq!(
            payload.oa_invoice_offset.applicant_names,
            vec!["周洁莹", "李四"]
        );
    }
}
