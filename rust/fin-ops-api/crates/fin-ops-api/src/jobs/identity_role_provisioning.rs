use serde::{Deserialize, Serialize};

pub const IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION: &str = "finops.identity.role_provisioning.v1";
pub const IDENTITY_ROLE_PROVISIONING_TASK_TYPE: &str = "identity_role_provisioning";
pub const IDENTITY_ROLE_PROVISIONING_SUBJECT: &str = "finops.jobs.identity.role_provisioning";

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct IdentityRoleProvisioningPayload {
    pub schema_version: String,
    pub settings_profile_id: String,
    pub settings_version: i64,
    pub access_control: serde_json::Value,
    pub assignments: Vec<IdentityRoleAssignment>,
    pub source: String,
    pub requested_by: String,
    pub trace_id: String,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
pub struct IdentityRoleAssignment {
    pub username: String,
    pub tier: IdentityRoleTier,
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum IdentityRoleTier {
    ReadExportOnly,
    FullAccess,
    Admin,
}

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum IdentityRoleProvisioningPayloadError {
    #[error("unsupported identity role provisioning schema version")]
    UnsupportedSchemaVersion,
    #[error("identity role provisioning payload has an empty required field")]
    EmptyRequiredField,
    #[error("identity role provisioning payload contains a sensitive field")]
    SensitiveField,
}

pub fn validate_payload(
    payload: &IdentityRoleProvisioningPayload,
) -> Result<(), IdentityRoleProvisioningPayloadError> {
    if payload.schema_version != IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION {
        return Err(IdentityRoleProvisioningPayloadError::UnsupportedSchemaVersion);
    }
    if payload.settings_profile_id.trim().is_empty()
        || payload.settings_version <= 0
        || payload.source.trim().is_empty()
        || payload.requested_by.trim().is_empty()
        || payload.trace_id.trim().is_empty()
        || payload
            .assignments
            .iter()
            .any(|assignment| assignment.username.trim().is_empty())
    {
        return Err(IdentityRoleProvisioningPayloadError::EmptyRequiredField);
    }
    if contains_sensitive_key(&payload.access_control) {
        return Err(IdentityRoleProvisioningPayloadError::SensitiveField);
    }
    Ok(())
}

fn contains_sensitive_key(value: &serde_json::Value) -> bool {
    match value {
        serde_json::Value::Object(map) => map.iter().any(|(key, value)| {
            let normalized = key.to_ascii_lowercase();
            matches!(
                normalized.as_str(),
                "password" | "secret" | "token" | "credential" | "credentials"
            ) || contains_sensitive_key(value)
        }),
        serde_json::Value::Array(items) => items.iter().any(contains_sensitive_key),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use serde_json::json;

    use super::*;

    #[test]
    fn identity_role_provisioning_payload_accepts_contract_shape_without_secrets() {
        let payload = IdentityRoleProvisioningPayload {
            schema_version: IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION.to_owned(),
            settings_profile_id: "11111111-1111-4111-8111-111111111111".to_owned(),
            settings_version: 2,
            access_control: json!({
                "allowed_usernames": ["READ001", "FULL001", "ADMIN001"],
                "readonly_export_usernames": ["READ001"],
                "full_access_usernames": ["FULL001"],
                "admin_usernames": ["ADMIN001"]
            }),
            assignments: vec![
                IdentityRoleAssignment {
                    username: "READ001".to_owned(),
                    tier: IdentityRoleTier::ReadExportOnly,
                },
                IdentityRoleAssignment {
                    username: "FULL001".to_owned(),
                    tier: IdentityRoleTier::FullAccess,
                },
                IdentityRoleAssignment {
                    username: "ADMIN001".to_owned(),
                    tier: IdentityRoleTier::Admin,
                },
            ],
            source: "workbench_settings".to_owned(),
            requested_by: "YNSYLP005".to_owned(),
            trace_id: "request-1".to_owned(),
        };

        validate_payload(&payload).unwrap();
    }

    #[test]
    fn identity_role_provisioning_payload_rejects_secret_bearing_access_control() {
        let payload = IdentityRoleProvisioningPayload {
            schema_version: IDENTITY_ROLE_PROVISIONING_SCHEMA_VERSION.to_owned(),
            settings_profile_id: "11111111-1111-4111-8111-111111111111".to_owned(),
            settings_version: 2,
            access_control: json!({
                "allowed_usernames": ["READ001"],
                "password": "do-not-publish"
            }),
            assignments: vec![IdentityRoleAssignment {
                username: "READ001".to_owned(),
                tier: IdentityRoleTier::ReadExportOnly,
            }],
            source: "workbench_settings".to_owned(),
            requested_by: "YNSYLP005".to_owned(),
            trace_id: "request-1".to_owned(),
        };

        assert_eq!(
            validate_payload(&payload),
            Err(IdentityRoleProvisioningPayloadError::SensitiveField)
        );
    }
}
