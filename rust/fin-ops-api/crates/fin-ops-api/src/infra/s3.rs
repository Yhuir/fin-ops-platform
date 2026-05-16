use crate::config::S3Config;

#[derive(Clone)]
pub struct S3ClientPlaceholder {
    configured: bool,
}

impl S3ClientPlaceholder {
    pub fn from_config(config: &S3Config) -> Self {
        Self {
            configured: config.endpoint.is_some() && config.bucket.is_some(),
        }
    }

    pub fn configured(&self) -> bool {
        self.configured
    }
}

