use std::{env, net::SocketAddr, str::FromStr, time::Duration};

use thiserror::Error;

const DEFAULT_BIND_ADDR: &str = "127.0.0.1:8080";
const DEFAULT_REQUEST_TIMEOUT_SECS: u64 = 30;
const DEFAULT_MAX_BODY_BYTES: usize = 25 * 1024 * 1024;
const DEFAULT_DB_MAX_CONNECTIONS: u32 = 5;

#[derive(Clone)]
pub struct ApiConfig {
    pub server: ServerConfig,
    pub database: DatabaseConfig,
    pub redis: RedisConfig,
    pub nats: NatsConfig,
    pub s3: S3Config,
    pub observability: ObservabilityConfig,
}

#[derive(Clone)]
pub struct ServerConfig {
    pub bind_addr: SocketAddr,
    pub request_timeout: Duration,
    pub max_body_bytes: usize,
}

#[derive(Clone)]
pub struct DatabaseConfig {
    pub url: String,
    pub max_connections: u32,
}

#[derive(Clone)]
pub struct RedisConfig {
    pub url: Option<String>,
}

#[derive(Clone)]
pub struct NatsConfig {
    pub url: Option<String>,
}

#[derive(Clone)]
pub struct S3Config {
    pub endpoint: Option<String>,
    pub bucket: Option<String>,
    pub region: Option<String>,
}

#[derive(Clone)]
pub struct ObservabilityConfig {
    pub log_filter: String,
}

#[derive(Debug, Error, PartialEq, Eq)]
pub enum ConfigError {
    #[error("missing required environment variable: {0}")]
    MissingRequired(&'static str),
    #[error("invalid environment variable {name}: {reason}")]
    InvalidValue { name: &'static str, reason: String },
}

impl ApiConfig {
    pub fn from_env() -> Result<Self, ConfigError> {
        Self::from_reader(|key| env::var(key).ok())
    }

    pub fn from_reader(
        read_env: impl Fn(&'static str) -> Option<String>,
    ) -> Result<Self, ConfigError> {
        let database_url = required(&read_env, "DATABASE_URL")?;

        Ok(Self {
            server: ServerConfig {
                bind_addr: parse_or_default(
                    &read_env,
                    "FIN_OPS_API_BIND_ADDR",
                    DEFAULT_BIND_ADDR,
                )?,
                request_timeout: Duration::from_secs(parse_or_default(
                    &read_env,
                    "FIN_OPS_API_REQUEST_TIMEOUT_SECS",
                    DEFAULT_REQUEST_TIMEOUT_SECS,
                )?),
                max_body_bytes: parse_or_default(
                    &read_env,
                    "FIN_OPS_API_MAX_BODY_BYTES",
                    DEFAULT_MAX_BODY_BYTES,
                )?,
            },
            database: DatabaseConfig {
                url: database_url,
                max_connections: parse_or_default(
                    &read_env,
                    "DATABASE_MAX_CONNECTIONS",
                    DEFAULT_DB_MAX_CONNECTIONS,
                )?,
            },
            redis: RedisConfig {
                url: optional(&read_env, "REDIS_URL"),
            },
            nats: NatsConfig {
                url: optional(&read_env, "NATS_URL"),
            },
            s3: S3Config {
                endpoint: optional(&read_env, "S3_ENDPOINT"),
                bucket: optional(&read_env, "S3_BUCKET"),
                region: optional(&read_env, "S3_REGION"),
            },
            observability: ObservabilityConfig {
                log_filter: optional(&read_env, "RUST_LOG")
                    .unwrap_or_else(|| "fin_ops_api=info,tower_http=info".to_owned()),
            },
        })
    }
}

fn required(
    read_env: &impl Fn(&'static str) -> Option<String>,
    name: &'static str,
) -> Result<String, ConfigError> {
    optional(read_env, name).ok_or(ConfigError::MissingRequired(name))
}

fn optional(
    read_env: &impl Fn(&'static str) -> Option<String>,
    name: &'static str,
) -> Option<String> {
    read_env(name).and_then(|value| {
        let trimmed = value.trim();
        (!trimmed.is_empty()).then(|| trimmed.to_owned())
    })
}

fn parse_or_default<T>(
    read_env: &impl Fn(&'static str) -> Option<String>,
    name: &'static str,
    default: T,
) -> Result<T, ConfigError>
where
    T: FromStr,
    T::Err: std::fmt::Display,
{
    match optional(read_env, name) {
        Some(value) => value.parse::<T>().map_err(|error| ConfigError::InvalidValue {
            name,
            reason: error.to_string(),
        }),
        None => Ok(default),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fails_fast_when_database_url_is_missing() {
        let error = match ApiConfig::from_reader(|_| None) {
            Ok(_) => panic!("config should fail without DATABASE_URL"),
            Err(error) => error,
        };

        assert_eq!(error, ConfigError::MissingRequired("DATABASE_URL"));
    }

    #[test]
    fn reads_required_and_optional_infrastructure_config() {
        let config = ApiConfig::from_reader(|key| match key {
            "DATABASE_URL" => Some("postgres://fin_ops_api:***@localhost/fin_ops".to_owned()),
            "REDIS_URL" => Some("redis://localhost:6379".to_owned()),
            "NATS_URL" => Some("nats://localhost:4222".to_owned()),
            "S3_ENDPOINT" => Some("http://localhost:9000".to_owned()),
            "S3_BUCKET" => Some("fin-ops-local".to_owned()),
            "FIN_OPS_API_BIND_ADDR" => Some("127.0.0.1:9090".to_owned()),
            _ => None,
        })
        .unwrap();

        assert_eq!(config.server.bind_addr.to_string(), "127.0.0.1:9090");
        assert_eq!(config.database.max_connections, DEFAULT_DB_MAX_CONNECTIONS);
        assert_eq!(config.redis.url.as_deref(), Some("redis://localhost:6379"));
        assert_eq!(config.nats.url.as_deref(), Some("nats://localhost:4222"));
        assert_eq!(config.s3.endpoint.as_deref(), Some("http://localhost:9000"));
        assert_eq!(config.s3.bucket.as_deref(), Some("fin-ops-local"));
    }
}
