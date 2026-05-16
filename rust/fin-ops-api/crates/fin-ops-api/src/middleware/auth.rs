use axum::{
    extract::{Request, State},
    http::{
        header::{AUTHORIZATION, COOKIE},
        HeaderMap, HeaderName, Method, StatusCode,
    },
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

use crate::{
    config::{AuthConfig, MetricsAccessConfig, OaIdentityAdapter},
    middleware::trace_id::{TraceId, REQUEST_ID_HEADER},
    state::AppState,
};

const BEARER_PREFIX: &str = "bearer ";
const OA_TOKEN_COOKIE_NAME: &str = "Admin-Token";
const OA_TOKEN_HEADER: HeaderName = HeaderName::from_static("x-oa-token");
const OA_USER_ID_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-user-id");
const OA_USERNAME_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-username");
const OA_NICKNAME_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-nickname");
const OA_DISPLAY_NAME_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-display-name");
const OA_DEPT_ID_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-dept-id");
const OA_DEPT_NAME_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-dept-name");
const OA_AVATAR_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-avatar");
const OA_ROLES_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-roles");
const OA_PERMISSIONS_HEADER: HeaderName = HeaderName::from_static("x-fin-ops-oa-permissions");

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthenticatedSession {
    pub identity: OaUserIdentity,
    pub allowed: bool,
    pub access_tier: String,
    pub can_access_app: bool,
    pub can_mutate_data: bool,
    pub can_admin_access: bool,
    pub request_id: Option<String>,
}

impl AuthenticatedSession {
    pub fn actor_id(&self) -> String {
        let username = self.identity.username.trim();
        if !username.is_empty() {
            return username.to_owned();
        }
        self.identity.user_id.clone()
    }
}

#[derive(Clone, Debug, PartialEq, Eq, Serialize)]
pub struct OaUserIdentity {
    pub user_id: String,
    pub username: String,
    pub nickname: String,
    pub display_name: String,
    pub dept_id: Option<String>,
    pub dept_name: Option<String>,
    pub avatar: Option<String>,
    pub roles: Vec<String>,
    pub permissions: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthError {
    InvalidSession,
    IdentityUnavailable,
    IdentityLookupFailed,
    Forbidden,
    PermissionDenied,
    AdminOnly,
    MetricsForbidden,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RoutePolicy {
    Public,
    AppSession,
    Mutate,
    Admin,
    InternalMetrics,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: &'static str,
    message: &'static str,
}

pub async fn enforce_route_policy(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Response {
    let policy = route_policy(request.method(), request.uri().path());
    match policy {
        RoutePolicy::Public => next.run(request).await,
        RoutePolicy::InternalMetrics => {
            if metrics_access_allowed(request.headers(), &state.config.metrics_access) {
                return next.run(request).await;
            }
            if !state.config.metrics_access.require_auth {
                return next.run(request).await;
            }
            match resolve_authenticated_session_for_request(&request, &state.config.auth) {
                Ok(session) if session.can_admin_access => {
                    request.extensions_mut().insert(session);
                    next.run(request).await
                }
                Ok(_) => AuthError::MetricsForbidden.into_response(),
                Err(AuthError::InvalidSession) => AuthError::MetricsForbidden.into_response(),
                Err(error) => error.into_response(),
            }
        }
        RoutePolicy::AppSession | RoutePolicy::Mutate | RoutePolicy::Admin => {
            let session =
                match resolve_authenticated_session_for_request(&request, &state.config.auth) {
                    Ok(session) => session,
                    Err(error) => return error.into_response(),
                };
            if !session.can_access_app {
                return AuthError::Forbidden.into_response();
            }
            if policy == RoutePolicy::Mutate && !session.can_mutate_data {
                return AuthError::PermissionDenied.into_response();
            }
            if policy == RoutePolicy::Admin && !session.can_admin_access {
                return AuthError::AdminOnly.into_response();
            }
            request.extensions_mut().insert(session);
            next.run(request).await
        }
    }
}

pub fn resolve_authenticated_session(
    headers: &HeaderMap,
    config: &AuthConfig,
    request_id: Option<String>,
) -> Result<AuthenticatedSession, AuthError> {
    let _token = extract_oa_token(headers).ok_or(AuthError::InvalidSession)?;
    let identity = match config.identity_adapter {
        OaIdentityAdapter::Disabled => return Err(AuthError::IdentityUnavailable),
        OaIdentityAdapter::TrustedHeaders => trusted_header_identity(headers)?,
    };
    Ok(apply_access_policy(identity, config, request_id))
}

fn resolve_authenticated_session_for_request(
    request: &Request,
    config: &AuthConfig,
) -> Result<AuthenticatedSession, AuthError> {
    let request_id = request
        .extensions()
        .get::<TraceId>()
        .map(|trace_id| trace_id.0.clone())
        .or_else(|| header_text(request.headers(), &REQUEST_ID_HEADER));
    resolve_authenticated_session(request.headers(), config, request_id)
}

fn route_policy(method: &Method, path: &str) -> RoutePolicy {
    if method == Method::OPTIONS {
        return RoutePolicy::Public;
    }
    match path {
        "/health" | "/healthz" | "/readyz" | "/api/session/me" | "/api/app-metadata" => {
            return RoutePolicy::Public;
        }
        "/metrics" => return RoutePolicy::InternalMetrics,
        _ => {}
    }

    if is_admin_route(method, path) {
        return RoutePolicy::Admin;
    }
    if is_protected_business_route(path) {
        if is_mutation_method(method) {
            RoutePolicy::Mutate
        } else {
            RoutePolicy::AppSession
        }
    } else {
        RoutePolicy::Public
    }
}

fn is_admin_route(method: &Method, path: &str) -> bool {
    is_mutation_method(method) && path.starts_with("/api/workbench/settings/data-reset")
}

fn is_protected_business_route(path: &str) -> bool {
    const PREFIXES: &[&str] = &[
        "/api/",
        "/workbench",
        "/integrations",
        "/projects",
        "/ledgers",
        "/reminders",
        "/reconciliation",
        "/imports",
        "/matching",
    ];
    PREFIXES.iter().any(|prefix| path.starts_with(prefix))
}

fn is_mutation_method(method: &Method) -> bool {
    matches!(
        *method,
        Method::POST | Method::PUT | Method::PATCH | Method::DELETE
    )
}

fn metrics_access_allowed(headers: &HeaderMap, config: &MetricsAccessConfig) -> bool {
    let Ok(name) = HeaderName::from_bytes(config.internal_header.as_bytes()) else {
        return false;
    };
    header_text(headers, &name).as_deref() == Some(config.internal_value.as_str())
}

pub fn extract_oa_token(headers: &HeaderMap) -> Option<String> {
    if let Some(value) = header_text(headers, &AUTHORIZATION) {
        let normalized = value.trim();
        if normalized.to_ascii_lowercase().starts_with(BEARER_PREFIX) {
            let token = normalized[BEARER_PREFIX.len()..].trim();
            if !token.is_empty() {
                return Some(token.to_owned());
            }
        }
    }
    if let Some(token) = header_text(headers, &OA_TOKEN_HEADER) {
        if !token.trim().is_empty() {
            return Some(token.trim().to_owned());
        }
    }
    header_text(headers, &COOKIE).and_then(|cookie| token_from_cookie(&cookie))
}

fn trusted_header_identity(headers: &HeaderMap) -> Result<OaUserIdentity, AuthError> {
    let user_id =
        header_text(headers, &OA_USER_ID_HEADER).ok_or(AuthError::IdentityLookupFailed)?;
    let username =
        header_text(headers, &OA_USERNAME_HEADER).ok_or(AuthError::IdentityLookupFailed)?;
    if user_id.trim().is_empty() || username.trim().is_empty() {
        return Err(AuthError::IdentityLookupFailed);
    }
    let nickname = header_text(headers, &OA_NICKNAME_HEADER).unwrap_or_default();
    let display_name = header_text(headers, &OA_DISPLAY_NAME_HEADER)
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| {
            if nickname.trim().is_empty() {
                username.clone()
            } else {
                nickname.clone()
            }
        });

    Ok(OaUserIdentity {
        user_id,
        username,
        nickname,
        display_name,
        dept_id: optional_header(headers, &OA_DEPT_ID_HEADER),
        dept_name: optional_header(headers, &OA_DEPT_NAME_HEADER),
        avatar: optional_header(headers, &OA_AVATAR_HEADER),
        roles: csv_header(headers, &OA_ROLES_HEADER),
        permissions: csv_header(headers, &OA_PERMISSIONS_HEADER),
    })
}

fn apply_access_policy(
    identity: OaUserIdentity,
    config: &AuthConfig,
    request_id: Option<String>,
) -> AuthenticatedSession {
    let permissions = normalize_values(identity.permissions.iter().cloned());
    let roles = normalize_values(identity.roles.iter().cloned());
    let username = identity.username.trim();
    let can_access_app = (!config.required_permission.trim().is_empty()
        && permissions
            .iter()
            .any(|permission| permission == &config.required_permission))
        || config
            .allowed_usernames
            .iter()
            .any(|allowed| allowed == username)
        || config
            .allowed_roles
            .iter()
            .any(|role| roles.iter().any(|identity_role| identity_role == role));

    let (access_tier, can_mutate_data, can_admin_access) = if !can_access_app {
        ("denied", false, false)
    } else if config.admin_usernames.iter().any(|admin| admin == username) {
        ("admin", true, true)
    } else if config
        .readonly_export_usernames
        .iter()
        .any(|readonly| readonly == username)
    {
        ("read_export_only", false, false)
    } else {
        ("full_access", true, false)
    };

    AuthenticatedSession {
        identity: OaUserIdentity {
            roles,
            permissions,
            ..identity
        },
        allowed: can_access_app,
        access_tier: access_tier.to_owned(),
        can_access_app,
        can_mutate_data,
        can_admin_access,
        request_id,
    }
}

fn token_from_cookie(cookie_header: &str) -> Option<String> {
    cookie_header.split(';').find_map(|part| {
        let (name, value) = part.trim().split_once('=')?;
        if name.trim() != OA_TOKEN_COOKIE_NAME {
            return None;
        }
        let token = value.trim();
        (!token.is_empty()).then(|| token.to_owned())
    })
}

fn header_text(headers: &HeaderMap, name: &HeaderName) -> Option<String> {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(ToOwned::to_owned)
}

fn optional_header(headers: &HeaderMap, name: &HeaderName) -> Option<String> {
    header_text(headers, name).filter(|value| !value.trim().is_empty())
}

fn csv_header(headers: &HeaderMap, name: &HeaderName) -> Vec<String> {
    header_text(headers, name)
        .map(|value| normalize_values(value.split(',').map(str::to_owned)))
        .unwrap_or_default()
}

fn normalize_values(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut normalized = Vec::new();
    for value in values {
        let item = value.trim();
        if item.is_empty() || normalized.iter().any(|seen| seen == item) {
            continue;
        }
        normalized.push(item.to_owned());
    }
    normalized
}

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let (status, body) = match self {
            Self::InvalidSession => (
                StatusCode::UNAUTHORIZED,
                ErrorDetails {
                    error: "invalid_oa_session",
                    message: "缺少 OA 登录态，请从 OA 系统进入。",
                },
            ),
            Self::IdentityUnavailable => (
                StatusCode::SERVICE_UNAVAILABLE,
                ErrorDetails {
                    error: "oa_identity_unavailable",
                    message: "OA 身份服务未配置。",
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
            Self::PermissionDenied => (
                StatusCode::FORBIDDEN,
                ErrorDetails {
                    error: "permission_denied",
                    message: "当前账户没有执行该写操作的权限。",
                },
            ),
            Self::AdminOnly => (
                StatusCode::FORBIDDEN,
                ErrorDetails {
                    error: "admin_only",
                    message: "当前账号没有管理员权限。",
                },
            ),
            Self::MetricsForbidden => (
                StatusCode::FORBIDDEN,
                ErrorDetails {
                    error: "metrics_forbidden",
                    message: "metrics endpoint requires internal access.",
                },
            ),
        };
        (status, Json(body)).into_response()
    }
}

#[cfg(test)]
mod tests {
    use axum::http::HeaderValue;

    use super::*;
    use crate::config::AuthConfig;

    fn trusted_config() -> AuthConfig {
        AuthConfig {
            identity_adapter: OaIdentityAdapter::TrustedHeaders,
            required_permission: "finops:app:view".to_owned(),
            allowed_usernames: vec![],
            allowed_roles: vec![],
            readonly_export_usernames: vec!["reader".to_owned()],
            admin_usernames: vec!["YNSYLP005".to_owned(), "admin".to_owned()],
        }
    }

    #[test]
    fn extracts_bearer_or_cookie_token_without_recording_secret() {
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_static("Bearer opaque-token"),
        );
        assert_eq!(extract_oa_token(&headers).as_deref(), Some("opaque-token"));

        let mut headers = HeaderMap::new();
        headers.insert(
            COOKIE,
            HeaderValue::from_static("other=1; Admin-Token=cookie-token"),
        );
        assert_eq!(extract_oa_token(&headers).as_deref(), Some("cookie-token"));
    }

    #[test]
    fn trusted_headers_evaluate_readonly_policy() {
        let mut headers = HeaderMap::new();
        headers.insert(
            AUTHORIZATION,
            HeaderValue::from_static("Bearer opaque-token"),
        );
        headers.insert(OA_USER_ID_HEADER, HeaderValue::from_static("reader-id"));
        headers.insert(OA_USERNAME_HEADER, HeaderValue::from_static("reader"));
        headers.insert(
            OA_PERMISSIONS_HEADER,
            HeaderValue::from_static("finops:app:view"),
        );

        let session = resolve_authenticated_session(&headers, &trusted_config(), None).unwrap();

        assert!(session.can_access_app);
        assert!(!session.can_mutate_data);
        assert_eq!(session.access_tier, "read_export_only");
    }
}
