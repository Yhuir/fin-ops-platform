use std::{env, time::Duration};

use fin_ops_api::{
    config::ApiConfig,
    infra::{nats::JetStreamEventPublisher, postgres},
    jobs::outbox_publisher::{OutboxPublisher, OutboxPublisherConfig, SqlxOutboxRepository},
    observability::logging,
};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let mode = parse_mode()?;
    let api_config = ApiConfig::from_env()?;
    logging::init(&api_config.observability)?;

    let db = postgres::build_pool(&api_config.database)?;
    let repository = SqlxOutboxRepository::new(db);
    let publisher = JetStreamEventPublisher::connect(&api_config.nats).await?;
    let service = OutboxPublisher::new(repository, publisher, outbox_config()?);

    match mode {
        Mode::Once => {
            let summary = service.publish_once().await?;
            tracing::info!(
                claimed = summary.claimed,
                published = summary.published,
                retrying = summary.retrying,
                dead_lettered = summary.dead_lettered,
                failed_to_record = summary.failed_to_record,
                "outbox publish once completed"
            );
        }
        Mode::Loop => {
            let interval = Duration::from_secs(read_env("OUTBOX_LOOP_INTERVAL_SECONDS", 5_u64)?);
            service
                .run_loop(interval, || async {
                    shutdown_signal().await;
                })
                .await?;
        }
    }

    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Mode {
    Once,
    Loop,
}

fn parse_mode() -> Result<Mode, String> {
    let mut mode = Mode::Once;
    for arg in env::args().skip(1) {
        match arg.as_str() {
            "--once" => mode = Mode::Once,
            "--loop" => mode = Mode::Loop,
            "--help" | "-h" => {
                return Err(
                    "usage: outbox_publisher [--once|--loop]\nconfiguration: OUTBOX_PUBLISHER_ID, OUTBOX_BATCH_SIZE, OUTBOX_MAX_ATTEMPTS, OUTBOX_BACKOFF_SECONDS, OUTBOX_STALE_LOCK_SECONDS, OUTBOX_LOOP_INTERVAL_SECONDS".to_owned(),
                );
            }
            _ => return Err(format!("unknown argument: {arg}")),
        }
    }
    Ok(mode)
}

fn outbox_config() -> Result<OutboxPublisherConfig, String> {
    let mut config = OutboxPublisherConfig::new(
        env::var("OUTBOX_PUBLISHER_ID").unwrap_or_else(|_| hostname_publisher_id()),
    );
    config.batch_size = read_env("OUTBOX_BATCH_SIZE", config.batch_size)?;
    config.max_publish_attempts = read_env("OUTBOX_MAX_ATTEMPTS", config.max_publish_attempts)?;
    config.retry_backoff_seconds =
        read_env("OUTBOX_BACKOFF_SECONDS", config.retry_backoff_seconds)?;
    config.stale_lock_seconds = read_env("OUTBOX_STALE_LOCK_SECONDS", config.stale_lock_seconds)?;
    Ok(config)
}

fn read_env<T>(name: &'static str, default: T) -> Result<T, String>
where
    T: std::str::FromStr,
    T::Err: std::fmt::Display,
{
    match env::var(name) {
        Ok(value) if !value.trim().is_empty() => value
            .parse::<T>()
            .map_err(|error| format!("invalid {name}: {error}")),
        _ => Ok(default),
    }
}

fn hostname_publisher_id() -> String {
    let hostname = env::var("HOSTNAME").unwrap_or_else(|_| "local".to_owned());
    format!("outbox-publisher-{hostname}-{}", std::process::id())
}

async fn shutdown_signal() {
    let ctrl_c = async {
        if let Err(error) = tokio::signal::ctrl_c().await {
            tracing::error!(%error, "failed to install ctrl-c handler");
        }
    };

    #[cfg(unix)]
    let terminate = async {
        match tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()) {
            Ok(mut signal) => {
                signal.recv().await;
            }
            Err(error) => {
                tracing::error!(%error, "failed to install terminate handler");
            }
        }
    };

    #[cfg(not(unix))]
    let terminate = std::future::pending::<()>();

    tokio::select! {
        _ = ctrl_c => {},
        _ = terminate => {},
    }
}
