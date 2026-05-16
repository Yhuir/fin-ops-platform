use std::{string::FromUtf8Error, time::Duration};

use prometheus::{
    Encoder, HistogramOpts, HistogramVec, IntCounterVec, Opts, Registry, TextEncoder,
};
use thiserror::Error;

pub const PROMETHEUS_CONTENT_TYPE: &str = "text/plain; version=0.0.4; charset=utf-8";

#[derive(Clone)]
pub struct Metrics {
    registry: Registry,
    http_requests_total: IntCounterVec,
    http_request_duration_seconds: HistogramVec,
    readiness_checks_total: IntCounterVec,
}

#[derive(Debug, Error)]
pub enum MetricsError {
    #[error(transparent)]
    Prometheus(#[from] prometheus::Error),
    #[error(transparent)]
    Utf8(#[from] FromUtf8Error),
}

impl Metrics {
    pub fn new() -> Result<Self, MetricsError> {
        let registry = Registry::new();
        let http_requests_total = IntCounterVec::new(
            Opts::new("http_requests_total", "Total HTTP requests handled by the API."),
            &["method", "path", "status"],
        )?;
        let http_request_duration_seconds = HistogramVec::new(
            HistogramOpts::new(
                "http_request_duration_seconds",
                "HTTP request duration in seconds.",
            ),
            &["method", "path", "status"],
        )?;
        let readiness_checks_total = IntCounterVec::new(
            Opts::new(
                "readiness_checks_total",
                "Total dependency readiness checks by dependency and result.",
            ),
            &["dependency", "result"],
        )?;

        registry.register(Box::new(http_requests_total.clone()))?;
        registry.register(Box::new(http_request_duration_seconds.clone()))?;
        registry.register(Box::new(readiness_checks_total.clone()))?;

        Ok(Self {
            registry,
            http_requests_total,
            http_request_duration_seconds,
            readiness_checks_total,
        })
    }

    pub fn record_http_request(
        &self,
        method: &str,
        path: &str,
        status: u16,
        elapsed: Duration,
    ) {
        let status = status.to_string();
        self.http_requests_total
            .with_label_values(&[method, path, &status])
            .inc();
        self.http_request_duration_seconds
            .with_label_values(&[method, path, &status])
            .observe(elapsed.as_secs_f64());
    }

    pub fn record_readiness_check(&self, dependency: &str, ready: bool) {
        let result = if ready { "ready" } else { "not_ready" };
        self.readiness_checks_total
            .with_label_values(&[dependency, result])
            .inc();
    }

    pub fn render(&self) -> Result<String, MetricsError> {
        let encoder = TextEncoder::new();
        let mut buffer = Vec::new();
        encoder.encode(&self.registry.gather(), &mut buffer)?;

        Ok(String::from_utf8(buffer)?)
    }
}

