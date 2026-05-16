use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{
        sse::{Event, KeepAlive, Sse},
        IntoResponse, Response,
    },
    routing::get,
    Json, Router,
};
use futures_util::{stream, Stream};
use serde::Serialize;
use serde_json::json;
use std::{collections::VecDeque, convert::Infallible, time::Duration};
use tokio::time::sleep;

use crate::{
    middleware::auth::AuthenticatedSession,
    repositories::{
        business_read::SqlxBusinessReadRepository, task_status::SqlxTaskStatusRepository,
    },
    services::{
        app_health::{build_app_health_snapshot, AppHealthSnapshot},
        business_read::{BusinessReadService, BusinessReadServiceError},
        task_status::{TaskStatusService, TaskStatusServiceError},
    },
    state::AppState,
};

pub fn router() -> Router<AppState> {
    Router::new()
        .route("/api/app-health", get(get_app_health))
        .route("/api/app-health/stream", get(get_app_health_stream))
}

async fn get_app_health(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
) -> Result<impl IntoResponse, AppHealthApiError> {
    let business_service =
        BusinessReadService::new(SqlxBusinessReadRepository::new(state.db.clone()));
    let task_service = TaskStatusService::new(SqlxTaskStatusRepository::new(state.db.clone()));
    let oa_sync = business_service.oa_sync_status().await?;
    let stale_scopes = business_service.list_workbench_stale_scopes().await?;
    let background_jobs = task_service.get_active_background_jobs().await?;

    Ok(Json(build_app_health_snapshot(
        session,
        oa_sync,
        stale_scopes,
        background_jobs,
    )))
}

async fn get_app_health_stream(
    State(state): State<AppState>,
    Extension(session): Extension<AuthenticatedSession>,
) -> Result<Sse<impl Stream<Item = Result<Event, Infallible>>>, AppHealthApiError> {
    let initial_snapshot = load_app_health_snapshot(&state, session.clone()).await?;
    let initial_events = app_health_sse_events(&initial_snapshot)?;
    let tick_state = state.clone();
    let tick_session = session;
    let stream = stream::unfold(
        (
            VecDeque::from(initial_events.into_iter().map(Ok).collect::<Vec<_>>()),
            tick_state,
            tick_session,
        ),
        |(mut pending_events, state, session)| async move {
            if let Some(event) = pending_events.pop_front() {
                return Some((event, (pending_events, state, session)));
            }
            sleep(Duration::from_secs(5)).await;
            let next_events = match load_app_health_snapshot(&state, session.clone()).await {
                Ok(snapshot) => app_health_sse_events(&snapshot)
                    .map(|events| events.into_iter().map(Ok).collect())
                    .unwrap_or_else(|error| vec![Ok(app_health_sse_error_event(error))]),
                Err(error) => vec![Ok(app_health_sse_error_event(error))],
            };
            pending_events = VecDeque::from(next_events);
            let event = pending_events.pop_front().unwrap_or_else(|| {
                Ok(app_health_sse_error_event(AppHealthApiError::Serialization))
            });
            Some((event, (pending_events, state, session)))
        },
    );

    Ok(Sse::new(stream).keep_alive(KeepAlive::default()))
}

async fn load_app_health_snapshot(
    state: &AppState,
    session: AuthenticatedSession,
) -> Result<AppHealthSnapshot, AppHealthApiError> {
    let business_service =
        BusinessReadService::new(SqlxBusinessReadRepository::new(state.db.clone()));
    let task_service = TaskStatusService::new(SqlxTaskStatusRepository::new(state.db.clone()));
    let oa_sync = business_service.oa_sync_status().await?;
    let stale_scopes = business_service.list_workbench_stale_scopes().await?;
    let background_jobs = task_service.get_active_background_jobs().await?;

    Ok(build_app_health_snapshot(
        session,
        oa_sync,
        stale_scopes,
        background_jobs,
    ))
}

fn app_health_sse_events(snapshot: &AppHealthSnapshot) -> Result<Vec<Event>, AppHealthApiError> {
    Ok(vec![
        Event::default()
            .event("app_health")
            .data(serde_json::to_string(snapshot).map_err(AppHealthApiError::from)?),
        Event::default().event("heartbeat").data(
            serde_json::to_string(&json!({"generated_at": snapshot.generated_at}))
                .map_err(AppHealthApiError::from)?,
        ),
    ])
}

fn app_health_sse_error_event(error: AppHealthApiError) -> Event {
    let (code, message) = error.public_error();
    Event::default().event("app_health_error").data(
        serde_json::to_string(&json!({"error": code, "message": message}))
            .unwrap_or_else(|_| "{\"error\":\"app_health_stream_error\"}".to_owned()),
    )
}

#[derive(Debug)]
enum AppHealthApiError {
    DatabaseUnavailable,
    Serialization,
}

#[derive(Serialize)]
struct ErrorDetails {
    error: &'static str,
    message: &'static str,
}

impl From<BusinessReadServiceError> for AppHealthApiError {
    fn from(_: BusinessReadServiceError) -> Self {
        Self::DatabaseUnavailable
    }
}

impl From<TaskStatusServiceError> for AppHealthApiError {
    fn from(_: TaskStatusServiceError) -> Self {
        Self::DatabaseUnavailable
    }
}

impl From<serde_json::Error> for AppHealthApiError {
    fn from(_: serde_json::Error) -> Self {
        Self::Serialization
    }
}

impl AppHealthApiError {
    fn public_error(&self) -> (&'static str, &'static str) {
        match self {
            Self::DatabaseUnavailable => {
                ("database_unavailable", "database dependency is unavailable")
            }
            Self::Serialization => (
                "app_health_serialization_failed",
                "app health payload serialization failed",
            ),
        }
    }
}

impl IntoResponse for AppHealthApiError {
    fn into_response(self) -> Response {
        let status = match &self {
            Self::DatabaseUnavailable => StatusCode::SERVICE_UNAVAILABLE,
            Self::Serialization => StatusCode::INTERNAL_SERVER_ERROR,
        };
        let (error, message) = self.public_error();
        let body = ErrorDetails { error, message };
        (status, Json(body)).into_response()
    }
}
