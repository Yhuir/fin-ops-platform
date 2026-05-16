pub mod health;

use axum::{middleware as axum_middleware, Router};
use tower::ServiceBuilder;
use tower_http::{
    cors::CorsLayer, limit::RequestBodyLimitLayer, timeout::TimeoutLayer, trace::TraceLayer,
};

use crate::{
    middleware::{request_metrics::record_http_metrics, trace_id::ensure_trace_id},
    state::AppState,
};

pub fn router(state: AppState) -> Router {
    let timeout = state.config.server.request_timeout;
    let max_body_bytes = state.config.server.max_body_bytes;

    Router::new()
        .merge(health::router())
        .with_state(state.clone())
        .layer(
            ServiceBuilder::new()
                .layer(TraceLayer::new_for_http())
                .layer(CorsLayer::permissive())
                .layer(TimeoutLayer::new(timeout))
                .layer(RequestBodyLimitLayer::new(max_body_bytes))
                .layer(axum_middleware::from_fn_with_state(
                    state.clone(),
                    record_http_metrics,
                ))
                .layer(axum_middleware::from_fn(ensure_trace_id)),
        )
}

