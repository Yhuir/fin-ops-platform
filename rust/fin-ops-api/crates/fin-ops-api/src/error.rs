use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use thiserror::Error;

use crate::{config::ConfigError, observability::metrics::MetricsError};

#[derive(Debug, Error)]
pub enum AppError {
    #[error(transparent)]
    Config(#[from] ConfigError),
    #[error(transparent)]
    Database(#[from] sqlx::Error),
    #[error(transparent)]
    Metrics(#[from] MetricsError),
}

#[derive(Serialize)]
struct ErrorBody {
    error: ErrorDetails,
}

#[derive(Serialize)]
struct ErrorDetails {
    code: &'static str,
    message: String,
}

impl AppError {
    fn status_code(&self) -> StatusCode {
        match self {
            Self::Config(_) => StatusCode::INTERNAL_SERVER_ERROR,
            Self::Database(_) => StatusCode::SERVICE_UNAVAILABLE,
            Self::Metrics(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    fn code(&self) -> &'static str {
        match self {
            Self::Config(_) => "configuration_error",
            Self::Database(_) => "database_unavailable",
            Self::Metrics(_) => "metrics_error",
        }
    }

    fn public_message(&self) -> String {
        match self {
            Self::Config(error) => error.to_string(),
            Self::Database(_) => "database dependency is unavailable".to_owned(),
            Self::Metrics(_) => "metrics endpoint is unavailable".to_owned(),
        }
    }
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let status = self.status_code();
        let body = ErrorBody {
            error: ErrorDetails {
                code: self.code(),
                message: self.public_message(),
            },
        };

        (status, Json(body)).into_response()
    }
}

