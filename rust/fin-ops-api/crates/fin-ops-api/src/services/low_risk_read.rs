use crate::repositories::low_risk_read::{
    AppMetadataSnapshot, LegacyHealthSnapshot, LowRiskReadRepository, LowRiskReadRepositoryError,
    WorkbenchSettingsSnapshot,
};

#[derive(Debug, thiserror::Error)]
pub enum LowRiskReadServiceError {
    #[error(transparent)]
    Repository(#[from] LowRiskReadRepositoryError),
}

pub struct LowRiskReadService<R> {
    repository: R,
}

impl<R> LowRiskReadService<R>
where
    R: LowRiskReadRepository,
{
    pub fn new(repository: R) -> Self {
        Self { repository }
    }

    pub async fn legacy_health(&self) -> Result<LegacyHealthSnapshot, LowRiskReadServiceError> {
        Ok(self.repository.legacy_health().await?)
    }

    pub async fn app_metadata(&self) -> Result<AppMetadataSnapshot, LowRiskReadServiceError> {
        Ok(self.repository.app_metadata().await?)
    }

    pub async fn workbench_settings(
        &self,
    ) -> Result<WorkbenchSettingsSnapshot, LowRiskReadServiceError> {
        Ok(self.repository.workbench_settings().await?)
    }

    pub fn session_me(&self, auth_header: Option<&str>) -> Result<SessionMeResponse, SessionError> {
        match auth_header.map(str::trim).filter(|value| !value.is_empty()) {
            None => Err(SessionError::InvalidSession),
            Some(_) => Err(SessionError::IdentityUnavailable),
        }
    }
}

#[derive(Debug, serde::Serialize)]
pub struct SessionMeResponse {
    pub user: SessionUserDto,
    pub roles: Vec<String>,
    pub permissions: Vec<String>,
    pub allowed: bool,
    pub access_tier: String,
    pub can_access_app: bool,
    pub can_mutate_data: bool,
    pub can_admin_access: bool,
}

#[derive(Debug, serde::Serialize)]
pub struct SessionUserDto {
    pub user_id: String,
    pub username: String,
    pub nickname: String,
    pub display_name: String,
    pub dept_id: Option<String>,
    pub dept_name: Option<String>,
    pub avatar: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionError {
    InvalidSession,
    IdentityUnavailable,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::repositories::low_risk_read::{
        default_app_metadata, default_legacy_health, default_workbench_settings,
        LowRiskReadRepositoryError,
    };
    use async_trait::async_trait;

    struct StaticRepository;

    #[async_trait]
    impl LowRiskReadRepository for StaticRepository {
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

    #[tokio::test]
    async fn settings_contract_keeps_required_frontend_fields() {
        let service = LowRiskReadService::new(StaticRepository);
        let settings = service.workbench_settings().await.unwrap();

        assert!(settings.projects.active.is_empty());
        assert_eq!(settings.access_control.admin_usernames, vec!["YNSYLP005"]);
        assert_eq!(settings.oa_retention.cutoff_date, "2026-01-01");
        assert_eq!(
            settings.oa_import.form_types,
            vec!["payment_request", "expense_claim"]
        );
        assert_eq!(settings.oa_import.statuses, vec!["completed"]);
    }

    #[test]
    fn session_me_does_not_forge_identity_without_adapter() {
        let service = LowRiskReadService::new(StaticRepository);

        assert_eq!(
            service.session_me(None).unwrap_err(),
            SessionError::InvalidSession
        );
        assert_eq!(
            service.session_me(Some("Bearer opaque-token")).unwrap_err(),
            SessionError::IdentityUnavailable
        );
    }
}
