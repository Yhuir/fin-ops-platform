use std::time::Instant;

use axum::{
    extract::{MatchedPath, Request, State},
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
    let route = request
        .extensions()
        .get::<MatchedPath>()
        .map(|matched_path| matched_path.as_str().to_owned())
        .unwrap_or_else(|| normalize_path_label(request.uri().path()));
    let started_at = Instant::now();

    let response = next.run(request).await;
    state.metrics.record_http_request(
        &method,
        &route,
        response.status().as_u16(),
        started_at.elapsed(),
    );

    response
}

fn normalize_path_label(path: &str) -> String {
    let normalized_segments = path
        .split('/')
        .map(|segment| {
            if segment.is_empty() {
                String::new()
            } else if is_uuid_like(segment) {
                ":uuid".to_owned()
            } else if is_numeric_segment(segment) {
                ":id".to_owned()
            } else if is_month_like(segment) {
                ":month".to_owned()
            } else {
                segment.to_owned()
            }
        })
        .collect::<Vec<_>>()
        .join("/");

    if normalized_segments.is_empty() {
        "/".to_owned()
    } else {
        normalized_segments
    }
}

fn is_uuid_like(segment: &str) -> bool {
    let bytes = segment.as_bytes();
    bytes.len() == 36
        && bytes.iter().enumerate().all(|(index, byte)| match index {
            8 | 13 | 18 | 23 => *byte == b'-',
            _ => byte.is_ascii_hexdigit(),
        })
}

fn is_numeric_segment(segment: &str) -> bool {
    !segment.is_empty() && segment.bytes().all(|byte| byte.is_ascii_digit())
}

fn is_month_like(segment: &str) -> bool {
    let bytes = segment.as_bytes();
    bytes.len() == 7
        && bytes[0..4].iter().all(|byte| byte.is_ascii_digit())
        && bytes[4] == b'-'
        && bytes[5..7].iter().all(|byte| byte.is_ascii_digit())
}

#[cfg(test)]
mod tests {
    use super::normalize_path_label;

    #[test]
    fn normalizes_high_cardinality_path_segments() {
        assert_eq!(
            normalize_path_label(
                "/api/workbench/2026-05/rows/550e8400-e29b-41d4-a716-446655440000/attempts/42"
            ),
            "/api/workbench/:month/rows/:uuid/attempts/:id"
        );
    }

    #[test]
    fn keeps_static_path_segments_readable() {
        assert_eq!(
            normalize_path_label("/api/imports/history"),
            "/api/imports/history"
        );
    }
}
