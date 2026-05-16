use async_trait::async_trait;
use serde::Serialize;
use sqlx::PgPool;

use crate::state::AppState;

#[derive(Clone, Serialize)]
pub struct ReadinessReport {
    pub status: &'static str,
    pub checks: Vec<DependencyCheck>,
}

impl ReadinessReport {
    pub fn is_ready(&self) -> bool {
        self.checks
            .iter()
            .filter(|check| check.required)
            .all(|check| check.ready)
    }
}

#[derive(Clone, Serialize)]
pub struct DependencyCheck {
    pub name: &'static str,
    pub required: bool,
    pub ready: bool,
    pub status: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
}

impl DependencyCheck {
    pub fn ready(name: &'static str, required: bool) -> Self {
        Self {
            name,
            required,
            ready: true,
            status: "ready",
            message: None,
        }
    }

    pub fn not_ready(name: &'static str, required: bool, message: impl Into<String>) -> Self {
        Self {
            name,
            required,
            ready: false,
            status: "not_ready",
            message: Some(message.into()),
        }
    }

    pub fn not_configured(name: &'static str) -> Self {
        Self {
            name,
            required: false,
            ready: false,
            status: "not_configured",
            message: None,
        }
    }
}

#[async_trait]
pub trait ReadinessProbe: Send + Sync {
    async fn check_postgres(&self) -> DependencyCheck;
}

#[derive(Clone)]
pub struct PostgresReadinessProbe {
    pool: PgPool,
}

impl PostgresReadinessProbe {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl ReadinessProbe for PostgresReadinessProbe {
    async fn check_postgres(&self) -> DependencyCheck {
        match sqlx::query("SELECT 1").execute(&self.pool).await {
            Ok(_) => DependencyCheck::ready("postgres", true),
            Err(error) => DependencyCheck::not_ready("postgres", true, error.to_string()),
        }
    }
}

pub struct HealthService;

impl HealthService {
    pub async fn readiness(state: &AppState) -> ReadinessReport {
        let mut checks = Vec::with_capacity(4);
        let postgres = state.readiness_probe.check_postgres().await;
        state
            .metrics
            .record_readiness_check(postgres.name, postgres.ready);
        checks.push(postgres);

        checks.push(optional_dependency_check(
            "redis",
            state.dependencies.redis.configured(),
        ));
        checks.push(optional_dependency_check(
            "nats",
            state.dependencies.nats.configured(),
        ));
        checks.push(optional_dependency_check(
            "s3",
            state.dependencies.s3.configured(),
        ));

        let ready = checks
            .iter()
            .filter(|check| check.required)
            .all(|check| check.ready);

        ReadinessReport {
            status: if ready { "ready" } else { "not_ready" },
            checks,
        }
    }
}

fn optional_dependency_check(name: &'static str, configured: bool) -> DependencyCheck {
    if configured {
        DependencyCheck::ready(name, false)
    } else {
        DependencyCheck::not_configured(name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn readiness_report_only_requires_required_checks() {
        let report = ReadinessReport {
            status: "ready",
            checks: vec![
                DependencyCheck::ready("postgres", true),
                DependencyCheck::not_configured("redis"),
            ],
        };

        assert!(report.is_ready());
    }
}
