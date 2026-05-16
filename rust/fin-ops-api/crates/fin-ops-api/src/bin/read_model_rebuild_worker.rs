use std::{env, fs, time::Duration};

use fin_ops_api::{
    config::ApiConfig, infra::postgres, jobs::read_model_rebuild::ReadModelRebuildWorker,
    observability::logging,
};
use serde_json::Value;

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    let args = Args::parse()?;
    let api_config = ApiConfig::from_env()?;
    logging::init(&api_config.observability)?;

    let pool = postgres::build_pool(&api_config.database)?;
    let worker = ReadModelRebuildWorker::new(pool, args.worker_id);

    match args.mode {
        Mode::Once => {
            let summary = worker.run_once().await?;
            tracing::info!(
                claimed = summary.claimed,
                rebuilt_targets = summary.rebuilt_targets,
                row_count = summary.row_count,
                stale_scopes = summary.stale_scopes,
                "read model rebuild once completed"
            );
        }
        Mode::Loop => {
            worker
                .run_loop(Duration::from_secs(args.interval_seconds))
                .await?;
        }
        Mode::Payload(payload) => {
            let summary = worker.rebuild_payload(payload, None).await?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "rebuilt_targets": summary.rebuilt_targets,
                    "row_count": summary.row_count,
                    "stale_scopes": summary.stale_scopes
                }))?
            );
        }
        Mode::StaleMetrics => {
            let stale_scopes = worker.count_stale_scopes().await?;
            println!(
                "{}",
                serde_json::to_string_pretty(&serde_json::json!({
                    "metric": "finops_read_model_stale_scopes",
                    "stale_scopes": stale_scopes
                }))?
            );
        }
    }

    Ok(())
}

#[derive(Debug)]
struct Args {
    mode: Mode,
    worker_id: String,
    interval_seconds: u64,
}

#[derive(Debug)]
enum Mode {
    Once,
    Loop,
    Payload(Value),
    StaleMetrics,
}

impl Args {
    fn parse() -> Result<Self, String> {
        let mut mode = Mode::Once;
        let mut worker_id =
            env::var("READ_MODEL_WORKER_ID").unwrap_or_else(|_| default_worker_id());
        let mut interval_seconds = read_env("READ_MODEL_WORKER_INTERVAL_SECONDS", 5_u64)?;

        let mut args = env::args().skip(1);
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--once" => mode = Mode::Once,
                "--loop" => mode = Mode::Loop,
                "--stale-metrics" => mode = Mode::StaleMetrics,
                "--payload-json" => {
                    let value = args
                        .next()
                        .ok_or_else(|| "--payload-json requires a JSON value".to_owned())?;
                    let payload = serde_json::from_str(&value)
                        .map_err(|error| format!("invalid --payload-json: {error}"))?;
                    mode = Mode::Payload(payload);
                }
                "--payload-file" => {
                    let path = args
                        .next()
                        .ok_or_else(|| "--payload-file requires a path".to_owned())?;
                    let content =
                        fs::read_to_string(&path).map_err(|error| format!("{path}: {error}"))?;
                    let payload = serde_json::from_str(&content)
                        .map_err(|error| format!("invalid --payload-file JSON: {error}"))?;
                    mode = Mode::Payload(payload);
                }
                "--worker-id" => {
                    worker_id = args
                        .next()
                        .ok_or_else(|| "--worker-id requires a value".to_owned())?;
                }
                "--interval-seconds" => {
                    interval_seconds = args
                        .next()
                        .ok_or_else(|| "--interval-seconds requires a value".to_owned())?
                        .parse::<u64>()
                        .map_err(|error| format!("invalid --interval-seconds: {error}"))?;
                }
                "--help" | "-h" => return Err(usage()),
                _ => return Err(format!("unknown argument: {arg}\n{}", usage())),
            }
        }

        Ok(Self {
            mode,
            worker_id,
            interval_seconds,
        })
    }
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

fn default_worker_id() -> String {
    let hostname = env::var("HOSTNAME").unwrap_or_else(|_| "local".to_owned());
    format!("read-model-worker-{hostname}-{}", std::process::id())
}

fn usage() -> String {
    "usage: read_model_rebuild_worker [--once|--loop|--stale-metrics|--payload-json JSON|--payload-file PATH] [--worker-id ID] [--interval-seconds N]\nconfiguration: DATABASE_URL, READ_MODEL_WORKER_ID, READ_MODEL_WORKER_INTERVAL_SECONDS".to_owned()
}
