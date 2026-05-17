pub mod app_health;
pub mod business_read;
pub mod finance_writes;
pub mod health;
pub mod import_files;
pub mod low_risk_read;
pub mod platform_legacy;
pub mod read_models;
pub mod task_status;
pub mod turnover_ledger;
pub mod workbench_writes;

use axum::{
    extract::DefaultBodyLimit,
    http::{
        header::{
            ACCEPT, ACCESS_CONTROL_REQUEST_HEADERS, ACCESS_CONTROL_REQUEST_METHOD, AUTHORIZATION,
            CONTENT_TYPE, ORIGIN,
        },
        HeaderName, Method, StatusCode,
    },
    middleware as axum_middleware, Router,
};
use tower::ServiceBuilder;
use tower_http::{
    cors::{AllowOrigin, CorsLayer},
    timeout::TimeoutLayer,
    trace::TraceLayer,
};

use crate::{
    config::CorsConfig,
    middleware::{
        auth::enforce_route_policy, request_metrics::record_http_metrics, trace_id::ensure_trace_id,
    },
    state::AppState,
};

pub fn router(state: AppState) -> Router {
    let timeout = state.config.server.request_timeout;
    let max_body_bytes = state.config.server.max_body_bytes;

    Router::new()
        .merge(health::router())
        .merge(app_health::router())
        .merge(business_read::router())
        .merge(finance_writes::router())
        .merge(import_files::router())
        .merge(low_risk_read::router())
        .merge(platform_legacy::router())
        .merge(read_models::router())
        .merge(task_status::router())
        .merge(turnover_ledger::router())
        .merge(workbench_writes::router())
        .with_state(state.clone())
        .layer(
            ServiceBuilder::new()
                .layer(TraceLayer::new_for_http())
                .layer(cors_layer(&state.config.cors))
                .layer(TimeoutLayer::with_status_code(
                    StatusCode::REQUEST_TIMEOUT,
                    timeout,
                ))
                .layer(DefaultBodyLimit::max(max_body_bytes))
                .layer(axum_middleware::from_fn_with_state(
                    state.clone(),
                    record_http_metrics,
                ))
                .layer(axum_middleware::from_fn_with_state(
                    state.clone(),
                    enforce_route_policy,
                ))
                .layer(axum_middleware::from_fn(ensure_trace_id)),
        )
}

fn cors_layer(config: &CorsConfig) -> CorsLayer {
    let allowed_origins = config.allowed_origins.clone();
    let allow_localhost = config.allow_localhost;
    CorsLayer::new()
        .allow_origin(AllowOrigin::predicate(move |origin, _parts| {
            let Ok(origin) = origin.to_str() else {
                return false;
            };
            allowed_origins.iter().any(|allowed| allowed == origin)
                || (allow_localhost && is_localhost_origin(origin))
        }))
        .allow_methods([
            Method::GET,
            Method::POST,
            Method::PUT,
            Method::PATCH,
            Method::DELETE,
            Method::OPTIONS,
        ])
        .allow_headers([
            ACCEPT,
            AUTHORIZATION,
            CONTENT_TYPE,
            ORIGIN,
            ACCESS_CONTROL_REQUEST_HEADERS,
            ACCESS_CONTROL_REQUEST_METHOD,
            HeaderName::from_static("x-request-id"),
            HeaderName::from_static("x-oa-token"),
            HeaderName::from_static("x-fin-ops-oa-user-id"),
            HeaderName::from_static("x-fin-ops-oa-username"),
            HeaderName::from_static("x-fin-ops-oa-display-name"),
            HeaderName::from_static("x-fin-ops-oa-roles"),
            HeaderName::from_static("x-fin-ops-oa-permissions"),
        ])
        .expose_headers([HeaderName::from_static("x-request-id")])
        .allow_credentials(true)
}

fn is_localhost_origin(origin: &str) -> bool {
    origin.starts_with("http://localhost:")
        || origin.starts_with("http://127.0.0.1:")
        || origin.starts_with("http://[::1]:")
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use async_trait::async_trait;
    use axum::{
        body::{to_bytes, Body},
        http::{header, Method, Request, StatusCode},
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;

    use crate::{
        services::health::{DependencyCheck, ReadinessProbe},
        state::AppState,
    };

    struct StaticReadinessProbe;

    #[async_trait]
    impl ReadinessProbe for StaticReadinessProbe {
        async fn check_postgres(&self) -> DependencyCheck {
            DependencyCheck::ready("postgres", true)
        }
    }

    #[tokio::test]
    async fn protected_business_route_rejects_missing_oa_session() {
        let response = request(
            trusted_header_state(),
            Request::builder()
                .uri("/api/workbench/settings")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_oa_session");
    }

    #[tokio::test]
    async fn app_health_stream_rejects_missing_oa_session() {
        let response = request(
            trusted_header_state(),
            Request::builder()
                .uri("/api/app-health/stream")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_oa_session");
    }

    #[tokio::test]
    async fn protected_business_route_keeps_503_when_adapter_is_not_configured() {
        let response = request(
            AppState::for_tests(Arc::new(StaticReadinessProbe)),
            Request::builder()
                .uri("/api/workbench/settings")
                .header(header::AUTHORIZATION, "Bearer opaque-oa-token")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "oa_identity_unavailable");
    }

    #[tokio::test]
    async fn protected_business_route_forbids_identity_without_app_permission() {
        let response = request(
            trusted_header_state(),
            authorized_request("/api/workbench/settings", "blocked_user", "")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "forbidden");
    }

    #[tokio::test]
    async fn readonly_identity_can_read_but_cannot_write() {
        let read_response = request(
            trusted_header_state(),
            authorized_request(
                "/api/workbench/settings",
                "readonly_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;
        assert_eq!(read_response.status(), StatusCode::OK);

        let write_response = request(
            trusted_header_state(),
            authorized_json_request(
                "/api/workbench/actions/confirm-link",
                "readonly_user",
                "finops:app:view",
                json!({
                    "month": "2026-05",
                    "row_ids": [
                        "00000000-0000-0000-0000-000000000001",
                        "00000000-0000-0000-0000-000000000002"
                    ],
                    "idempotency_key": "confirm:readonly:1"
                }),
            ),
        )
        .await;

        assert_eq!(write_response.status(), StatusCode::FORBIDDEN);
        let body = to_json(write_response.into_body()).await;
        assert_eq!(body["error"], "permission_denied");
    }

    #[tokio::test]
    async fn write_route_rejects_body_actor_mismatch() {
        let response = request(
            trusted_header_state(),
            authorized_json_request(
                "/api/workbench/actions/confirm-link",
                "writer_user",
                "finops:app:view",
                json!({
                    "month": "2026-05",
                    "row_ids": [
                        "00000000-0000-0000-0000-000000000001",
                        "00000000-0000-0000-0000-000000000002"
                    ],
                    "idempotency_key": "confirm:actor-mismatch:1",
                    "actor": "spoofed_user"
                }),
            ),
        )
        .await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "actor_mismatch");
    }

    #[tokio::test]
    async fn no_oa_batch_detail_rejects_non_uuid_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/no-oa-bank-batches/not-a-uuid",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_uuid");
    }

    #[tokio::test]
    async fn tax_offset_rejects_all_time_month_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/tax-offset?month=all",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_month");
    }

    #[tokio::test]
    async fn tax_certified_imports_require_month_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/tax-offset/certified-imports",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_tax_certified_import_request");
    }

    #[tokio::test]
    async fn data_reset_job_status_uses_legacy_not_found_shape_for_bad_id() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/workbench/settings/data-reset/jobs/not-a-uuid",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "settings_data_reset_job_not_found");
    }

    #[tokio::test]
    async fn etc_invoices_rejects_invalid_page_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/etc/invoices?page=not-a-number&page_size=20",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_etc_invoice_request");
    }

    #[tokio::test]
    async fn etc_direct_import_keeps_legacy_removed_contract() {
        let response = request(
            trusted_header_state(),
            authorized_json_request(
                "/api/etc/import",
                "writer_user",
                "finops:app:view",
                json!({}),
            ),
        )
        .await;

        assert_eq!(response.status(), StatusCode::GONE);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "etc_direct_import_removed");
        assert_eq!(
            body["message"],
            "Use /api/etc/import/preview and /api/etc/import/confirm."
        );
    }

    #[tokio::test]
    async fn bank_detail_accounts_rejects_invalid_date_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/bank-details/accounts?date_to=2026-13-01",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_date");
    }

    #[tokio::test]
    async fn bank_detail_transactions_rejects_invalid_date_before_database_access() {
        let response = request(
            trusted_header_state(),
            authorized_request(
                "/api/bank-details/transactions?date_from=not-a-date",
                "viewer_user",
                "finops:app:view",
            )
            .body(Body::empty())
            .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["error"], "invalid_date");
    }

    #[tokio::test]
    async fn metrics_requires_internal_marker_by_default() {
        let blocked_response = request(
            trusted_header_state(),
            Request::builder()
                .uri("/metrics")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(blocked_response.status(), StatusCode::FORBIDDEN);

        let allowed_response = request(
            trusted_header_state(),
            Request::builder()
                .uri("/metrics")
                .header("x-fin-ops-internal-request", "1")
                .body(Body::empty())
                .unwrap(),
        )
        .await;
        assert_eq!(allowed_response.status(), StatusCode::OK);
    }

    #[tokio::test]
    async fn cors_uses_configured_origin_allowlist() {
        let allowed = request(
            trusted_header_state(),
            Request::builder()
                .method(Method::OPTIONS)
                .uri("/api/workbench/settings")
                .header(header::ORIGIN, "https://oa.example.test")
                .header(header::ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert_eq!(allowed.status(), StatusCode::OK);
        assert_eq!(
            allowed.headers().get(header::ACCESS_CONTROL_ALLOW_ORIGIN),
            Some(&"https://oa.example.test".parse().unwrap())
        );

        let denied = request(
            trusted_header_state(),
            Request::builder()
                .method(Method::OPTIONS)
                .uri("/api/workbench/settings")
                .header(header::ORIGIN, "https://evil.example.test")
                .header(header::ACCESS_CONTROL_REQUEST_METHOD, "GET")
                .body(Body::empty())
                .unwrap(),
        )
        .await;

        assert!(denied
            .headers()
            .get(header::ACCESS_CONTROL_ALLOW_ORIGIN)
            .is_none());
    }

    fn trusted_header_state() -> AppState {
        AppState::for_tests_with_env(Arc::new(StaticReadinessProbe), |key| match key {
            "DATABASE_URL" => {
                Some("postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops_test".to_owned())
            }
            "FIN_OPS_OA_IDENTITY_ADAPTER" => Some("trusted_headers".to_owned()),
            "FIN_OPS_OA_REQUIRED_PERMISSION" => Some("finops:app:view".to_owned()),
            "FIN_OPS_READONLY_EXPORT_USERNAMES" => Some("readonly_user".to_owned()),
            "FIN_OPS_ADMIN_USERNAMES" => Some("admin_user".to_owned()),
            "FIN_OPS_CORS_ALLOWED_ORIGINS" => Some("https://oa.example.test".to_owned()),
            "FIN_OPS_METRICS_INTERNAL_HEADER" => Some("x-fin-ops-internal-request".to_owned()),
            "FIN_OPS_METRICS_INTERNAL_VALUE" => Some("1".to_owned()),
            _ => None,
        })
    }

    fn authorized_request(
        uri: &str,
        username: &str,
        permissions: &str,
    ) -> axum::http::request::Builder {
        Request::builder()
            .uri(uri)
            .header(header::AUTHORIZATION, "Bearer opaque-oa-token")
            .header("x-fin-ops-oa-user-id", format!("{username}-id"))
            .header("x-fin-ops-oa-username", username)
            .header("x-fin-ops-oa-display-name", username)
            .header("x-fin-ops-oa-permissions", permissions)
    }

    fn authorized_json_request(
        uri: &str,
        username: &str,
        permissions: &str,
        payload: Value,
    ) -> Request<Body> {
        authorized_request(uri, username, permissions)
            .method(Method::POST)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(payload.to_string()))
            .unwrap()
    }

    async fn request(state: AppState, request: Request<Body>) -> axum::response::Response {
        crate::build_router(state).oneshot(request).await.unwrap()
    }

    async fn to_json(body: Body) -> Value {
        let bytes = to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }
}
