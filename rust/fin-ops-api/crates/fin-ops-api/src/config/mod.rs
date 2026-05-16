use std::{env, net::SocketAddr, str::FromStr, time::Duration};

use thiserror::Error;

const DEFAULT_BIND_ADDR: &str = "127.0.0.1:8080";
const DEFAULT_REQUEST_TIMEOUT_SECS: u64 = 30;
const DEFAULT_MAX_BODY_BYTES: usize = 25 * 1024 * 1024;
const DEFAULT_DB_MAX_CONNECTIONS: u32 = 5;
const DEFAULT_REQUIRED_PERMISSION: &str = "finops:app:view";
const DEFAULT_ADMIN_USERNAME: &str = "YNSYLP005";
const DEFAULT_METRICS_INTERNAL_HEADER: &str = "x-fin-ops-internal-request";
const DEFAULT_METRICS_INTERNAL_VALUE: &str = "1";
const DEFAULT_S3_PRESIGN_TTL_SECS: u64 = 300;
const MAX_S3_PRESIGN_TTL_SECS: u64 = 900;

#[derive(Clone)]
pub struct ApiConfig {
    pub server: ServerConfig,
    pub database: DatabaseConfig,
    pub redis: RedisConfig,
    pub nats: NatsConfig,
    pub s3: S3Config,
    pub observability: ObservabilityConfig,
    pub auth: AuthConfig,
    pub cors: CorsConfig,
    pub metrics_access: MetricsAccessConfig,
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
    pub presign_ttl: Duration,
}

#[derive(Clone)]
pub struct ObservabilityConfig {
    pub log_filter: String,
}

#[derive(Clone)]
pub struct AuthConfig {
    pub identity_adapter: OaIdentityAdapter,
    pub required_permission: String,
    pub allowed_usernames: Vec<String>,
    pub allowed_roles: Vec<String>,
    pub readonly_export_usernames: Vec<String>,
    pub admin_usernames: Vec<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OaIdentityAdapter {
    Disabled,
    TrustedHeaders,
}

#[derive(Clone)]
pub struct CorsConfig {
    pub allowed_origins: Vec<String>,
    pub allow_localhost: bool,
}

#[derive(Clone)]
pub struct MetricsAccessConfig {
    pub require_auth: bool,
    pub internal_header: String,
    pub internal_value: String,
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
                    DEFAULT_BIND_ADDR
                        .parse()
                        .expect("default bind address must be valid"),
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
                presign_ttl: Duration::from_secs(
                    parse_or_default(
                        &read_env,
                        "S3_PRESIGN_TTL_SECS",
                        DEFAULT_S3_PRESIGN_TTL_SECS,
                    )?
                    .clamp(1, MAX_S3_PRESIGN_TTL_SECS),
                ),
            },
            observability: ObservabilityConfig {
                log_filter: optional(&read_env, "RUST_LOG")
                    .unwrap_or_else(|| "fin_ops_api=info,tower_http=info".to_owned()),
            },
            auth: AuthConfig {
                identity_adapter: parse_or_default(
                    &read_env,
                    "FIN_OPS_OA_IDENTITY_ADAPTER",
                    OaIdentityAdapter::Disabled,
                )?,
                required_permission: optional(&read_env, "FIN_OPS_OA_REQUIRED_PERMISSION")
                    .unwrap_or_else(|| DEFAULT_REQUIRED_PERMISSION.to_owned()),
                allowed_usernames: csv(&read_env, "FIN_OPS_ALLOWED_USERNAMES"),
                allowed_roles: csv(&read_env, "FIN_OPS_ALLOWED_ROLES"),
                readonly_export_usernames: csv(&read_env, "FIN_OPS_READONLY_EXPORT_USERNAMES"),
                admin_usernames: {
                    let mut values = vec![DEFAULT_ADMIN_USERNAME.to_owned()];
                    values.extend(csv(&read_env, "FIN_OPS_ADMIN_USERNAMES"));
                    normalize_values(values)
                },
            },
            cors: CorsConfig {
                allowed_origins: csv(&read_env, "FIN_OPS_CORS_ALLOWED_ORIGINS"),
                allow_localhost: parse_bool_or_default(
                    &read_env,
                    "FIN_OPS_CORS_ALLOW_LOCALHOST",
                    false,
                )?,
            },
            metrics_access: MetricsAccessConfig {
                require_auth: parse_bool_or_default(&read_env, "METRICS_REQUIRE_AUTH", true)?,
                internal_header: optional(&read_env, "FIN_OPS_METRICS_INTERNAL_HEADER")
                    .unwrap_or_else(|| DEFAULT_METRICS_INTERNAL_HEADER.to_owned()),
                internal_value: optional(&read_env, "FIN_OPS_METRICS_INTERNAL_VALUE")
                    .unwrap_or_else(|| DEFAULT_METRICS_INTERNAL_VALUE.to_owned()),
            },
        })
    }
}

impl FromStr for OaIdentityAdapter {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value.trim().to_ascii_lowercase().as_str() {
            "" | "none" | "disabled" => Ok(Self::Disabled),
            "trusted_headers" | "trusted-header" | "headers" => Ok(Self::TrustedHeaders),
            other => Err(format!("unsupported OA identity adapter: {other}")),
        }
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
        Some(value) => value
            .parse::<T>()
            .map_err(|error| ConfigError::InvalidValue {
                name,
                reason: error.to_string(),
            }),
        None => Ok(default),
    }
}

fn parse_bool_or_default(
    read_env: &impl Fn(&'static str) -> Option<String>,
    name: &'static str,
    default: bool,
) -> Result<bool, ConfigError> {
    match optional(read_env, name) {
        Some(value) => match value.trim().to_ascii_lowercase().as_str() {
            "1" | "true" | "yes" | "on" => Ok(true),
            "0" | "false" | "no" | "off" => Ok(false),
            _ => Err(ConfigError::InvalidValue {
                name,
                reason: "expected boolean value".to_owned(),
            }),
        },
        None => Ok(default),
    }
}

fn csv(read_env: &impl Fn(&'static str) -> Option<String>, name: &'static str) -> Vec<String> {
    optional(read_env, name)
        .map(|value| normalize_values(value.split(',').map(str::to_owned)))
        .unwrap_or_default()
}

fn normalize_values(values: impl IntoIterator<Item = String>) -> Vec<String> {
    let mut normalized = Vec::new();
    for value in values {
        let item = value.trim();
        if item.is_empty() || normalized.iter().any(|seen| seen == item) {
            continue;
        }
        normalized.push(item.to_owned());
    }
    normalized
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
            "S3_PRESIGN_TTL_SECS" => Some("600".to_owned()),
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
        assert_eq!(config.s3.presign_ttl, Duration::from_secs(600));
        assert_eq!(config.auth.identity_adapter, OaIdentityAdapter::Disabled);
        assert_eq!(config.auth.required_permission, "finops:app:view");
        assert_eq!(config.auth.admin_usernames, vec!["YNSYLP005"]);
        assert!(config.metrics_access.require_auth);
    }

    #[test]
    fn reads_auth_cors_and_metrics_security_config() {
        let config = ApiConfig::from_reader(|key| match key {
            "DATABASE_URL" => Some("postgres://fin_ops_api:***@localhost/fin_ops".to_owned()),
            "FIN_OPS_OA_IDENTITY_ADAPTER" => Some("trusted_headers".to_owned()),
            "FIN_OPS_ALLOWED_USERNAMES" => Some("alice,bob,alice".to_owned()),
            "FIN_OPS_READONLY_EXPORT_USERNAMES" => Some("reader".to_owned()),
            "FIN_OPS_ADMIN_USERNAMES" => Some("admin".to_owned()),
            "FIN_OPS_CORS_ALLOWED_ORIGINS" => {
                Some("https://oa.example.test,http://localhost:5173".to_owned())
            }
            "FIN_OPS_CORS_ALLOW_LOCALHOST" => Some("1".to_owned()),
            "METRICS_REQUIRE_AUTH" => Some("0".to_owned()),
            "FIN_OPS_METRICS_INTERNAL_HEADER" => Some("x-internal".to_owned()),
            _ => None,
        })
        .unwrap();

        assert_eq!(
            config.auth.identity_adapter,
            OaIdentityAdapter::TrustedHeaders
        );
        assert_eq!(config.auth.allowed_usernames, vec!["alice", "bob"]);
        assert_eq!(config.auth.readonly_export_usernames, vec!["reader"]);
        assert_eq!(config.auth.admin_usernames, vec!["YNSYLP005", "admin"]);
        assert_eq!(
            config.cors.allowed_origins,
            vec!["https://oa.example.test", "http://localhost:5173"]
        );
        assert!(config.cors.allow_localhost);
        assert!(!config.metrics_access.require_auth);
        assert_eq!(config.metrics_access.internal_header, "x-internal");
    }

    #[test]
    fn caps_s3_presign_ttl_to_short_lived_maximum() {
        let config = ApiConfig::from_reader(|key| match key {
            "DATABASE_URL" => Some("postgres://fin_ops_api:***@localhost/fin_ops".to_owned()),
            "S3_BUCKET" => Some("fin-ops-local".to_owned()),
            "S3_PRESIGN_TTL_SECS" => Some("3600".to_owned()),
            _ => None,
        })
        .unwrap();

        assert_eq!(
            config.s3.presign_ttl,
            Duration::from_secs(MAX_S3_PRESIGN_TTL_SECS)
        );
    }
}
