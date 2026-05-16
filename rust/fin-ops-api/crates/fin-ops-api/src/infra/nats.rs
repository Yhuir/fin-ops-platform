use async_trait::async_trait;
use thiserror::Error;

use crate::{
    config::NatsConfig,
    jobs::outbox_publisher::{EventPublisher, PublishAck, PublishFailure, PublishMessage},
};

const NATS_MESSAGE_ID_HEADER: &str = "Nats-Msg-Id";
const EVENT_ID_HEADER: &str = "X-Event-Id";
const IDEMPOTENCY_KEY_HEADER: &str = "X-Idempotency-Key";
const TRACE_ID_HEADER: &str = "X-Trace-Id";

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

#[derive(Debug, Error)]
pub enum NatsClientError {
    #[error("NATS_URL is required for JetStream publisher")]
    MissingUrl,
    #[error("failed to connect to NATS: {0}")]
    Connect(String),
}

#[derive(Clone)]
pub struct JetStreamEventPublisher {
    jetstream: async_nats::jetstream::Context,
}

impl JetStreamEventPublisher {
    pub async fn connect(config: &NatsConfig) -> Result<Self, NatsClientError> {
        let url = config.url.as_deref().ok_or(NatsClientError::MissingUrl)?;
        let client = async_nats::connect(url).await.map_err(|error| {
            NatsClientError::Connect(redact_connection_error(&error.to_string()))
        })?;
        Ok(Self {
            jetstream: async_nats::jetstream::new(client),
        })
    }

    pub fn from_context(jetstream: async_nats::jetstream::Context) -> Self {
        Self { jetstream }
    }
}

#[async_trait]
impl EventPublisher for JetStreamEventPublisher {
    async fn publish(&self, message: PublishMessage) -> Result<PublishAck, PublishFailure> {
        let payload = serde_json::to_vec(&message.payload).map_err(|error| {
            PublishFailure::permanent("payload_encode_failed", error.to_string())
        })?;
        let headers = build_publish_headers(
            &message.message_id.to_string(),
            &message.idempotency_key,
            message.trace_id.as_deref(),
        );

        let ack_future = self
            .jetstream
            .publish_with_headers(message.subject.clone(), headers, payload.into())
            .await
            .map_err(|error| {
                PublishFailure::retryable("jetstream_publish_failed", error.to_string())
            })?;
        let ack = ack_future.await.map_err(|error| {
            PublishFailure::retryable("jetstream_publish_ack_failed", error.to_string())
        })?;

        Ok(PublishAck {
            provider_message_id: Some(format!("{}:{}", ack.stream, ack.sequence)),
        })
    }
}

pub(crate) fn build_publish_headers(
    message_id: &str,
    idempotency_key: &str,
    trace_id: Option<&str>,
) -> async_nats::HeaderMap {
    let mut headers = async_nats::HeaderMap::new();
    headers.insert(NATS_MESSAGE_ID_HEADER, message_id);
    headers.insert(EVENT_ID_HEADER, message_id);
    headers.insert(IDEMPOTENCY_KEY_HEADER, idempotency_key);
    if let Some(trace_id) = trace_id.filter(|value| !value.trim().is_empty()) {
        headers.insert(TRACE_ID_HEADER, trace_id);
    }
    headers
}

fn redact_connection_error(message: &str) -> String {
    if message.contains("://") || message.to_ascii_lowercase().contains("password") {
        "redacted NATS connection error".to_owned()
    } else {
        message.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn publish_headers_include_message_id_idempotency_key_and_trace_id() {
        let headers = build_publish_headers(
            "11111111-1111-4111-8111-111111111111",
            "read_model.rebuild:workbench:2026-05:v42",
            Some("trace-001"),
        );

        assert_eq!(
            headers.get("Nats-Msg-Id").map(|value| value.as_str()),
            Some("11111111-1111-4111-8111-111111111111")
        );
        assert_eq!(
            headers.get("X-Idempotency-Key").map(|value| value.as_str()),
            Some("read_model.rebuild:workbench:2026-05:v42")
        );
        assert_eq!(
            headers.get("X-Trace-Id").map(|value| value.as_str()),
            Some("trace-001")
        );
        assert_eq!(
            headers.get("X-Event-Id").map(|value| value.as_str()),
            Some("11111111-1111-4111-8111-111111111111")
        );
    }
}
