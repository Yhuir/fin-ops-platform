use crate::config::NatsConfig;

#[derive(Clone)]
pub struct NatsClientPlaceholder {
    configured: bool,
}

impl NatsClientPlaceholder {
    pub fn from_config(config: &NatsConfig) -> Self {
        Self {
            configured: config.url.is_some(),
        }
    }

    pub fn configured(&self) -> bool {
        self.configured
    }
}

