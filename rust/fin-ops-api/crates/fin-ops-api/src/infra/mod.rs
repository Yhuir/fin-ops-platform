pub mod nats;
pub mod postgres;
pub mod redis;
pub mod s3;

use crate::config::ApiConfig;

#[derive(Clone)]
pub struct DependencyClients {
    pub redis: redis::RedisClientPlaceholder,
    pub nats: nats::NatsClientPlaceholder,
    pub s3: s3::S3ClientPlaceholder,
}

impl DependencyClients {
    pub fn from_config(config: &ApiConfig) -> Self {
        Self {
            redis: redis::RedisClientPlaceholder::from_config(&config.redis),
            nats: nats::NatsClientPlaceholder::from_config(&config.nats),
            s3: s3::S3ClientPlaceholder::from_config(&config.s3),
        }
    }
}

