use sqlx::{postgres::PgPoolOptions, PgPool};

use crate::config::DatabaseConfig;

pub fn build_pool(config: &DatabaseConfig) -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        .max_connections(config.max_connections)
        .connect_lazy(&config.url)
}
