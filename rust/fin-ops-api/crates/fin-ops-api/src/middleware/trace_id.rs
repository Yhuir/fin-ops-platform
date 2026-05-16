use std::time::Instant;

use axum::{
    extract::Request,
    http::{header::HeaderName, HeaderValue},
    middleware::Next,
    response::Response,
};
use uuid::Uuid;

pub const REQUEST_ID_HEADER: HeaderName = HeaderName::from_static("x-request-id");

#[derive(Clone)]
pub struct TraceId(pub String);

pub async fn ensure_trace_id(mut request: Request, next: Next) -> Response {
    let method = request.method().clone();
    let path = request.uri().path().to_owned();
    let started_at = Instant::now();
    let trace_id = request
        .headers()
        .get(&REQUEST_ID_HEADER)
        .and_then(|value| value.to_str().ok())
        .filter(|value| !value.trim().is_empty())
        .map(ToOwned::to_owned)
        .unwrap_or_else(|| Uuid::new_v4().to_string());

    request.extensions_mut().insert(TraceId(trace_id.clone()));

    let mut response = next.run(request).await;
    if let Ok(header_value) = HeaderValue::from_str(&trace_id) {
        response.headers_mut().insert(REQUEST_ID_HEADER, header_value);
    }

    tracing::info!(
        trace_id = %trace_id,
        method = %method,
        path = %path,
        status = response.status().as_u16(),
        elapsed_ms = started_at.elapsed().as_millis(),
        "request completed",
    );

    response
}

