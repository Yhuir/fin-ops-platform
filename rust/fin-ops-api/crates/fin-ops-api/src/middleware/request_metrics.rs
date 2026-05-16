use std::time::Instant;

use axum::{
    extract::{Request, State},
    middleware::Next,
    response::Response,
};

use crate::state::AppState;

pub async fn record_http_metrics(
    State(state): State<AppState>,
    request: Request,
    next: Next,
) -> Response {
    let method = request.method().as_str().to_owned();
    let path = request.uri().path().to_owned();
    let started_at = Instant::now();

    let response = next.run(request).await;
    state.metrics.record_http_request(
        &method,
        &path,
        response.status().as_u16(),
        started_at.elapsed(),
    );

    response
}
