use std::{
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use sqlx::PgPool;
use uuid::Uuid;

use crate::{
    config::ApiConfig,
    error::AppError,
    infra::{self, DependencyClients},
    observability::metrics::Metrics,
    services::health::{PostgresReadinessProbe, ReadinessProbe},
};

#[derive(Clone)]
pub struct AppState {
    pub config: Arc<ApiConfig>,
    pub db: PgPool,
    pub dependencies: DependencyClients,
    pub metrics: Metrics,
    pub readiness_probe: Arc<dyn ReadinessProbe>,
    pub clock: Arc<dyn Clock>,
    pub id_generator: Arc<dyn IdGenerator>,
}

impl AppState {
    pub fn from_config(config: ApiConfig) -> Result<Self, AppError> {
        let db = infra::postgres::build_pool(&config.database)?;
        let dependencies = DependencyClients::from_config(&config);
        let metrics = Metrics::new()?;
        let readiness_probe = Arc::new(PostgresReadinessProbe::new(db.clone()));

        Ok(Self {
            config: Arc::new(config),
            db,
            dependencies,
            metrics,
            readiness_probe,
            clock: Arc::new(SystemClock),
            id_generator: Arc::new(UuidGenerator),
        })
    }

    #[cfg(test)]
    pub fn for_tests(readiness_probe: Arc<dyn ReadinessProbe>) -> Self {
        let config = ApiConfig::from_reader(|key| match key {
            "DATABASE_URL" => {
                Some("postgres://fin_ops_api:***@127.0.0.1:5432/fin_ops_test".to_owned())
            }
            _ => None,
        })
        .expect("test config should be valid");
        let db = infra::postgres::build_pool(&config.database).expect("test database URL is valid");

        Self {
            config: Arc::new(config.clone()),
            db,
            dependencies: DependencyClients::from_config(&config),
            metrics: Metrics::new().expect("test metrics registry should be valid"),
            readiness_probe,
            clock: Arc::new(SystemClock),
            id_generator: Arc::new(UuidGenerator),
        }
    }
}

pub trait Clock: Send + Sync {
    fn now_unix_seconds(&self) -> u64;
}

pub struct SystemClock;

impl Clock for SystemClock {
    fn now_unix_seconds(&self) -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs()
    }
}

pub trait IdGenerator: Send + Sync {
    fn new_id(&self) -> String;
}

pub struct UuidGenerator;

impl IdGenerator for UuidGenerator {
    fn new_id(&self) -> String {
        Uuid::new_v4().to_string()
    }
}
