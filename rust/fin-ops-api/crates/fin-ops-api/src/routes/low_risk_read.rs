use axum::{
    extract::State,
    http::{HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::{
    middleware::auth::{resolve_authenticated_session, AuthError, AuthenticatedSession},
    repositories::low_risk_read::SqlxLowRiskReadRepository,
    services::low_risk_read::{
        LowRiskReadService, LowRiskReadServiceError, SessionError, SessionMeResponse,
        SessionUserDto,
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/health", get(legacy_health))
        .route("/api/app-metadata", get(app_metadata))
        .route("/api/session/me", get(session_me))
        .route("/api/workbench/settings", get(workbench_settings))
}

async fn legacy_health(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, LowRiskReadApiError> {
    let service = build_service(&state);
    Ok(Json(service.legacy_health().await?))
}

async fn app_metadata(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, LowRiskReadApiError> {
    let service = build_service(&state);
    Ok(Json(service.app_metadata().await?))
}

async fn session_me(
    State(state): State<AppState>,
    headers: HeaderMap,
) -> Result<impl IntoResponse, LowRiskReadApiError> {
    let session = resolve_authenticated_session(&headers, &state.config.auth, None)?;
    Ok(Json(session_me_response(session)))
}

fn session_me_response(session: AuthenticatedSession) -> SessionMeResponse {
    SessionMeResponse {
        user: SessionUserDto {
            user_id: session.identity.user_id,
            username: session.identity.username,
            nickname: session.identity.nickname,
            display_name: session.identity.display_name,
            dept_id: session.identity.dept_id,
            dept_name: session.identity.dept_name,
            avatar: session.identity.avatar,
        },
        roles: session.identity.roles,
        permissions: session.identity.permissions,
        allowed: session.allowed,
        access_tier: session.access_tier,
        can_access_app: session.can_access_app,
        can_mutate_data: session.can_mutate_data,
        can_admin_access: session.can_admin_access,
    }
}

async fn workbench_settings(
    State(state): State<AppState>,
) -> Result<impl IntoResponse, LowRiskReadApiError> {
    let service = build_service(&state);
    Ok(Json(service.workbench_settings().await?))
}

fn build_service(state: &AppState) -> LowRiskReadService<SqlxLowRiskReadRepository> {
    LowRiskReadService::new(SqlxLowRiskReadRepository::new(state.db.clone()))
}

#[derive(Debug)]
enum LowRiskReadApiError {
    InvalidSession,
    IdentityUnavailable,
    IdentityLookupFailed,
    DatabaseUnavailable,
    Forbidden,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: &'static str,
    message: &'static str,
}

impl From<LowRiskReadServiceError> for LowRiskReadApiError {
    fn from(error: LowRiskReadServiceError) -> Self {
        match error {
            LowRiskReadServiceError::Repository(_) => Self::DatabaseUnavailable,
        }
    }
}

impl From<SessionError> for LowRiskReadApiError {
    fn from(error: SessionError) -> Self {
        match error {
            SessionError::InvalidSession => Self::InvalidSession,
            SessionError::IdentityUnavailable => Self::IdentityUnavailable,
        }
    }
}

impl From<AuthError> for LowRiskReadApiError {
    fn from(error: AuthError) -> Self {
        match error {
            AuthError::InvalidSession => Self::InvalidSession,
            AuthError::IdentityUnavailable => Self::IdentityUnavailable,
            AuthError::IdentityLookupFailed => Self::IdentityLookupFailed,
            AuthError::Forbidden
            | AuthError::PermissionDenied
            | AuthError::AdminOnly
            | AuthError::MetricsForbidden => Self::Forbidden,
        }
    }
}

impl IntoResponse for LowRiskReadApiError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            Self::InvalidSession => (
                StatusCode::UNAUTHORIZED,
                ErrorDetails {
                    error: "invalid_oa_session",
                    message: "\u{7f3a}\u{5c11} OA \u{767b}\u{5f55}\u{6001}\u{ff0c}\u{8bf7}\u{4ece} OA \u{7cfb}\u{7edf}\u{8fdb}\u{5165}\u{3002}",
                },
            ),
            Self::IdentityUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                ErrorDetails {
                    error: "oa_identity_unavailable",
                    message: "OA \u{8eab}\u{4efd}\u{670d}\u{52a1}\u{672a}\u{914d}\u{7f6e}\u{3002}",
                },
            ),
            Self::IdentityLookupFailed => (
                StatusCode::BAD_GATEWAY,
                ErrorDetails {
                    error: "oa_identity_lookup_failed",
                    message: "OA 身份解析失败。",
                },
            ),
            Self::Forbidden => (
                StatusCode::FORBIDDEN,
                ErrorDetails {
                    error: "forbidden",
                    message: "当前 OA 账户未被授权访问财务运营平台。",
                },
            ),
            Self::DatabaseUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                ErrorDetails {
                    error: "database_unavailable",
                    message: "database dependency is unavailable",
                },
            ),
        };

        (status, Json(body)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::Request,
    };
    use serde_json::Value;
    use tower::ServiceExt;

    use super::*;
    use crate::services::health::{DependencyCheck, ReadinessProbe};

    struct StaticReadinessProbe;

    #[async_trait]
    impl ReadinessProbe for StaticReadinessProbe {
        async fn check_postgres(&self) -> DependencyCheck {
            DependencyCheck::ready("postgres", true)
        }
    }

    #[tokio::test]
    async fn legacy_health_matches_python_foundation_shape() {
        let response = request("/health").await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["service"], "fin-ops-platform-api");
        assert_eq!(body["status"], "ready");
        assert!(body["entrypoints"]
            .as_array()
            .unwrap()
            .contains(&Value::String("/api/session/me".to_owned())));
        assert!(body["module_boundaries"].is_object());
    }

    #[tokio::test]
    async fn settings_read_contract_has_frontend_required_fields() {
        let response = authorized_request("/api/workbench/settings").await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        assert!(body["projects"]["active"].as_array().unwrap().is_empty());
        assert!(body["bank_account_mappings"].as_array().unwrap().is_empty());
        assert_eq!(body["access_control"]["admin_usernames"][0], "YNSYLP005");
        assert_eq!(body["oa_retention"]["cutoff_date"], "2026-01-01");
        assert_eq!(body["oa_import"]["form_types"][0], "payment_request");
    }

    #[tokio::test]
    async fn session_me_preserves_legacy_error_shape_without_identity_adapter() {
        let response = request("/api/session/me").await;

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_oa_session");
        assert!(body["message"].as_str().unwrap().contains("OA"));

        let response = request_with_bearer("/api/session/me").await;

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "oa_identity_unavailable");
    }

    #[tokio::test]
    async fn app_metadata_reports_readonly_axum_contract() {
        let response = request("/api/app-metadata").await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["service"], "fin-ops-api");
        assert_eq!(body["readonly"], true);
        assert!(body["compatible_python_contracts"]
            .as_array()
            .unwrap()
            .contains(&Value::String("/api/workbench/settings".to_owned())));
    }

    async fn request(uri: &str) -> axum::response::Response {
        let state = AppState::for_tests(Arc::new(StaticReadinessProbe));
        crate::build_router(state)
            .oneshot(Request::builder().uri(uri).body(Body::empty()).unwrap())
            .await
            .unwrap()
    }

    async fn request_with_bearer(uri: &str) -> axum::response::Response {
        let state = AppState::for_tests(Arc::new(StaticReadinessProbe));
        crate::build_router(state)
            .oneshot(
                Request::builder()
                    .uri(uri)
                    .header("authorization", "Bearer opaque-oa-token")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn authorized_request(uri: &str) -> axum::response::Response {
        let state = AppState::for_tests_with_env(Arc::new(StaticReadinessProbe), |key| match key {
            "DATABASE_URL" => {
                Some("postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops_test".to_owned())
            }
            "FIN_OPS_OA_IDENTITY_ADAPTER" => Some("trusted_headers".to_owned()),
            _ => None,
        });
        crate::build_router(state)
            .oneshot(
                Request::builder()
                    .uri(uri)
                    .header("authorization", "Bearer opaque-oa-token")
                    .header("x-fin-ops-oa-user-id", "YNSYLP005-id")
                    .header("x-fin-ops-oa-username", "YNSYLP005")
                    .header("x-fin-ops-oa-permissions", "finops:app:view")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap()
    }

    async fn to_json(body: Body) -> Value {
        let bytes = to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }
}
