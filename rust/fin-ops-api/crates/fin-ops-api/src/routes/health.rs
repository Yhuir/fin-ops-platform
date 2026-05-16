use axum::{
    extract::State,
    http::{header::CONTENT_TYPE, StatusCode},
    response::IntoResponse,
    routing::get,
    Json, Router,
};
use serde::Serialize;

use crate::{
    error::AppError, observability::metrics::PROMETHEUS_CONTENT_TYPE,
    services::health::HealthService, state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/healthz", get(healthz))
        .route("/readyz", get(readyz))
        .route("/metrics", get(metrics))
}

#[derive(Serialize)]
struct HealthzResponse {
    status: &'static str,
    service: &'static str,
}

async fn healthz() -> Json<HealthzResponse> {
    Json(HealthzResponse {
        status: "ok",
        service: "fin-ops-api",
    })
}

async fn readyz(State(state): State<AppState>) -> impl IntoResponse {
    let report = HealthService::readiness(&state).await;
    let status = if report.is_ready() {
        StatusCode::OK
    } else {
        StatusCode::SERVICE_UNAVAILABLE
    };

    (status, Json(report))
}

async fn metrics(State(state): State<AppState>) -> Result<impl IntoResponse, AppError> {
    let body = state.metrics.render()?;

    Ok(([(CONTENT_TYPE, PROMETHEUS_CONTENT_TYPE)], body))
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

    struct StaticReadinessProbe {
        check: DependencyCheck,
    }

    #[async_trait]
    impl ReadinessProbe for StaticReadinessProbe {
        async fn check_postgres(&self) -> DependencyCheck {
            self.check.clone()
        }
    }

    #[tokio::test]
    async fn healthz_does_not_require_database_readiness() {
        let state = AppState::for_tests(Arc::new(StaticReadinessProbe {
            check: DependencyCheck::not_ready("postgres", true, "db unavailable"),
        }));
        let response = crate::build_router(state)
            .oneshot(
                Request::builder()
                    .uri("/healthz")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["status"], "ok");
        assert_eq!(body["service"], "fin-ops-api");
    }

    #[tokio::test]
    async fn readyz_reports_postgres_probe_failure() {
        let state = AppState::for_tests(Arc::new(StaticReadinessProbe {
            check: DependencyCheck::not_ready("postgres", true, "db unavailable"),
        }));
        let response = crate::build_router(state)
            .oneshot(
                Request::builder()
                    .uri("/readyz")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = to_json(response.into_body()).await;
        assert_eq!(body["status"], "not_ready");
        assert_eq!(body["checks"][0]["name"], "postgres");
        assert_eq!(body["checks"][0]["ready"], false);
    }

    #[tokio::test]
    async fn metrics_endpoint_exposes_prometheus_text() {
        let state = AppState::for_tests(Arc::new(StaticReadinessProbe {
            check: DependencyCheck::ready("postgres", true),
        }));
        let app = crate::build_router(state);

        app.clone()
            .oneshot(
                Request::builder()
                    .uri("/healthz")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        let response = app
            .oneshot(
                Request::builder()
                    .uri("/metrics")
                    .header("x-fin-ops-internal-request", "1")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();

        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let body = String::from_utf8(body.to_vec()).unwrap();
        assert!(body.contains("http_requests_total"));
    }

    async fn to_json(body: Body) -> Value {
        let bytes = to_bytes(body, usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }
}
