use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

use crate::config::ObservabilityConfig;

pub fn init(config: &ObservabilityConfig) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let env_filter = EnvFilter::try_new(&config.log_filter)?;

    tracing_subscriber::registry()
        .with(env_filter)
        .with(fmt::layer().json())
        .try_init()?;

    Ok(())
}

