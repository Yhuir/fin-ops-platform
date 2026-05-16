use crate::config::RedisConfig;

#[derive(Clone)]
pub struct RedisClientPlaceholder {
    configured: bool,
}

impl RedisClientPlaceholder {
    pub fn from_config(config: &RedisConfig) -> Self {
        Self {
            configured: config.url.is_some(),
        }
    }

    pub fn configured(&self) -> bool {
        self.configured
    }
}

