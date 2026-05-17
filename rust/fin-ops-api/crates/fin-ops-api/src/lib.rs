pub mod config;
pub mod error;
pub mod infra;
pub mod jobs;
pub mod middleware;
pub mod observability;
pub mod repositories;
pub mod routes;
pub mod services;
pub mod state;

#[cfg(test)]
mod migration_contracts;

use axum::Router;

use crate::state::AppState;

pub fn build_router(state: AppState) -> Router {
    routes::router(state)
}
