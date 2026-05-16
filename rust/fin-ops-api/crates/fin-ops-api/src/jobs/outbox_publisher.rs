use async_trait::async_trait;
use serde_json::Value;
use std::{future::Future, time::Duration};

use sqlx::{PgPool, Row};
use thiserror::Error;
use tokio::time::sleep;
use uuid::Uuid;

const SENSITIVE_KEY_PARTS: &[&str] = &[
    "password",
    "token",
    "secret",
    "credential",
    "uri",
    "url",
    "raw_file",
    "content",
];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutboxPublisherConfig {
    pub publisher_id: String,
    pub batch_size: i64,
    pub max_publish_attempts: i32,
    pub retry_backoff_seconds: i32,
    pub stale_lock_seconds: i32,
}

impl OutboxPublisherConfig {
    pub fn new(publisher_id: impl Into<String>) -> Self {
        Self {
            publisher_id: publisher_id.into(),
            batch_size: 100,
            max_publish_attempts: 5,
            retry_backoff_seconds: 30,
            stale_lock_seconds: 300,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct OutboxEvent {
    pub id: Uuid,
    pub subject: String,
    pub payload: Value,
    pub event_type: String,
    pub aggregate_type: String,
    pub aggregate_id: Uuid,
    pub idempotency_key: String,
    pub trace_id: Option<String>,
    pub attempt_count: i32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PublishMessage {
    pub message_id: Uuid,
    pub subject: String,
    pub payload: Value,
    pub idempotency_key: String,
    pub trace_id: Option<String>,
}

impl From<&OutboxEvent> for PublishMessage {
    fn from(event: &OutboxEvent) -> Self {
        Self {
            message_id: event.id,
            subject: event.subject.clone(),
            payload: event.payload.clone(),
            idempotency_key: event.idempotency_key.clone(),
            trace_id: event.trace_id.clone(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PublishAck {
    pub provider_message_id: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PublishFailure {
    pub code: String,
    pub message: String,
    pub retryable: bool,
}

impl PublishFailure {
    pub fn retryable(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: sanitize_failure_message(&message.into()),
            retryable: true,
        }
    }

    pub fn permanent(code: impl Into<String>, message: impl Into<String>) -> Self {
        Self {
            code: code.into(),
            message: sanitize_failure_message(&message.into()),
            retryable: false,
        }
    }
}

#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct OutboxPublishSummary {
    pub claimed: usize,
    pub published: usize,
    pub retrying: usize,
    pub dead_lettered: usize,
    pub failed_to_record: usize,
}

#[derive(Debug, Error)]
pub enum OutboxPublisherError {
    #[error(transparent)]
    Repository(#[from] OutboxRepositoryError),
}

#[derive(Debug, Error)]
pub enum OutboxRepositoryError {
    #[error(transparent)]
    Sqlx(#[from] sqlx::Error),
    #[error("outbox event {event_id} was not in the expected publisher state")]
    UnexpectedState { event_id: Uuid },
}

#[async_trait]
pub trait OutboxRepository: Send + Sync {
    async fn claim_batch(
        &self,
        publisher_id: &str,
        batch_size: i64,
        stale_lock_seconds: i32,
    ) -> Result<Vec<OutboxEvent>, OutboxRepositoryError>;

    async fn mark_published(
        &self,
        event_id: Uuid,
        publisher_id: &str,
        ack: &PublishAck,
    ) -> Result<(), OutboxRepositoryError>;

    async fn mark_retrying(
        &self,
        event: &OutboxEvent,
        publisher_id: &str,
        failure: &PublishFailure,
        retry_backoff_seconds: i32,
    ) -> Result<(), OutboxRepositoryError>;

    async fn mark_dead_lettered(
        &self,
        event: &OutboxEvent,
        publisher_id: &str,
        failure: &PublishFailure,
    ) -> Result<(), OutboxRepositoryError>;
}

#[async_trait]
pub trait EventPublisher: Send + Sync {
    async fn publish(&self, message: PublishMessage) -> Result<PublishAck, PublishFailure>;
}

pub struct OutboxPublisher<R, P> {
    repository: R,
    publisher: P,
    config: OutboxPublisherConfig,
}

impl<R, P> OutboxPublisher<R, P>
where
    R: OutboxRepository,
    P: EventPublisher,
{
    pub fn new(repository: R, publisher: P, config: OutboxPublisherConfig) -> Self {
        Self {
            repository,
            publisher,
            config,
        }
    }

    pub async fn publish_once(&self) -> Result<OutboxPublishSummary, OutboxPublisherError> {
        let events = self
            .repository
            .claim_batch(
                &self.config.publisher_id,
                self.config.batch_size,
                self.config.stale_lock_seconds,
            )
            .await?;
        let mut summary = OutboxPublishSummary {
            claimed: events.len(),
            ..OutboxPublishSummary::default()
        };

        for event in events {
            let message = PublishMessage::from(&event);
            let publish_result = if payload_contains_sensitive_fields(&message.payload) {
                Err(PublishFailure::permanent(
                    "outbox_payload_contains_sensitive_field",
                    "Outbox payload contains a sensitive field and was not published.",
                ))
            } else {
                self.publisher.publish(message).await
            };

            match publish_result {
                Ok(ack) => match self
                    .repository
                    .mark_published(event.id, &self.config.publisher_id, &ack)
                    .await
                {
                    Ok(()) => summary.published += 1,
                    Err(_) => summary.failed_to_record += 1,
                },
                Err(failure) => {
                    let should_dead_letter = !failure.retryable
                        || event.attempt_count >= self.config.max_publish_attempts;
                    let result = if should_dead_letter {
                        self.repository
                            .mark_dead_lettered(&event, &self.config.publisher_id, &failure)
                            .await
                            .map(|_| {
                                summary.dead_lettered += 1;
                            })
                    } else {
                        self.repository
                            .mark_retrying(
                                &event,
                                &self.config.publisher_id,
                                &failure,
                                self.config.retry_backoff_seconds,
                            )
                            .await
                            .map(|_| {
                                summary.retrying += 1;
                            })
                    };

                    if result.is_err() {
                        summary.failed_to_record += 1;
                    }
                }
            }
        }

        Ok(summary)
    }

    pub async fn run_loop<S, Fut>(
        &self,
        interval: Duration,
        mut shutdown: S,
    ) -> Result<(), OutboxPublisherError>
    where
        S: FnMut() -> Fut,
        Fut: Future<Output = ()>,
    {
        loop {
            tokio::select! {
                result = self.publish_once() => {
                    let summary = result?;
                    tracing::info!(
                        claimed = summary.claimed,
                        published = summary.published,
                        retrying = summary.retrying,
                        dead_lettered = summary.dead_lettered,
                        failed_to_record = summary.failed_to_record,
                        "outbox publish batch completed"
                    );
                    tokio::select! {
                        _ = sleep(interval) => {}
                        _ = shutdown() => {
                            tracing::info!("outbox publisher shutdown signal received");
                            return Ok(());
                        }
                    }
                }
                _ = shutdown() => {
                    tracing::info!("outbox publisher shutdown signal received");
                    return Ok(());
                }
            }
        }
    }
}

#[derive(Clone)]
pub struct SqlxOutboxRepository {
    pool: PgPool,
}

impl SqlxOutboxRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl OutboxRepository for SqlxOutboxRepository {
    async fn claim_batch(
        &self,
        publisher_id: &str,
        batch_size: i64,
        stale_lock_seconds: i32,
    ) -> Result<Vec<OutboxEvent>, OutboxRepositoryError> {
        let rows = sqlx::query(
            r#"
            with recovered as (
              update job.outbox_events
              set status = 'retrying',
                  available_at = now(),
                  locked_by = null,
                  locked_at = null,
                  last_error_code = 'publisher_lock_expired',
                  last_error = 'Publisher lock expired before the event was marked published.',
                  updated_at = now()
              where status = 'publishing'
                and locked_at < now() - make_interval(secs => $3)
              returning id
            ),
            picked as (
              select id
              from job.outbox_events
              where status in ('pending', 'retrying')
                and available_at <= now()
              order by available_at asc, created_at asc
              for update skip locked
              limit $1
            )
            update job.outbox_events event
            set status = 'publishing',
                locked_by = $2,
                locked_at = now(),
                attempt_count = event.attempt_count + 1,
                last_error_code = null,
                last_error = null,
                updated_at = now()
            from picked
            where event.id = picked.id
            returning
                event.id,
                event.subject,
                event.payload,
                event.event_type,
                event.aggregate_type,
                event.aggregate_id,
                event.idempotency_key,
                event.trace_id,
                event.attempt_count
            "#,
        )
        .bind(batch_size)
        .bind(publisher_id)
        .bind(stale_lock_seconds)
        .fetch_all(&self.pool)
        .await?;

        Ok(rows
            .into_iter()
            .map(|row| OutboxEvent {
                id: row.get("id"),
                subject: row.get("subject"),
                payload: row.get("payload"),
                event_type: row.get("event_type"),
                aggregate_type: row.get("aggregate_type"),
                aggregate_id: row.get("aggregate_id"),
                idempotency_key: row.get("idempotency_key"),
                trace_id: row.get("trace_id"),
                attempt_count: row.get("attempt_count"),
            })
            .collect())
    }

    async fn mark_published(
        &self,
        event_id: Uuid,
        publisher_id: &str,
        ack: &PublishAck,
    ) -> Result<(), OutboxRepositoryError> {
        let result = sqlx::query(
            r#"
            update job.outbox_events
            set status = 'published',
                published_at = now(),
                locked_by = null,
                locked_at = null,
                last_error_code = null,
                last_error = null,
                updated_at = now()
            where id = $1
              and status = 'publishing'
              and locked_by = $2
            "#,
        )
        .bind(event_id)
        .bind(publisher_id)
        .execute(&self.pool)
        .await?;

        let _ = ack;
        if result.rows_affected() != 1 {
            return Err(OutboxRepositoryError::UnexpectedState { event_id });
        }
        Ok(())
    }

    async fn mark_retrying(
        &self,
        event: &OutboxEvent,
        publisher_id: &str,
        failure: &PublishFailure,
        retry_backoff_seconds: i32,
    ) -> Result<(), OutboxRepositoryError> {
        let result = sqlx::query(
            r#"
            update job.outbox_events
            set status = 'retrying',
                available_at = now() + make_interval(secs => $3),
                locked_by = null,
                locked_at = null,
                last_error_code = $4,
                last_error = $5,
                updated_at = now()
            where id = $1
              and status = 'publishing'
              and locked_by = $2
            "#,
        )
        .bind(event.id)
        .bind(publisher_id)
        .bind(retry_backoff_seconds)
        .bind(&failure.code)
        .bind(&failure.message)
        .execute(&self.pool)
        .await?;

        if result.rows_affected() != 1 {
            return Err(OutboxRepositoryError::UnexpectedState { event_id: event.id });
        }
        Ok(())
    }

    async fn mark_dead_lettered(
        &self,
        event: &OutboxEvent,
        publisher_id: &str,
        failure: &PublishFailure,
    ) -> Result<(), OutboxRepositoryError> {
        let mut transaction = self.pool.begin().await?;
        let result = sqlx::query(
            r#"
            update job.outbox_events
            set status = 'dead_lettered',
                locked_by = null,
                locked_at = null,
                last_error_code = $4,
                last_error = $5,
                updated_at = now()
            where id = $1
              and status = 'publishing'
              and locked_by = $2
              and attempt_count = $3
            "#,
        )
        .bind(event.id)
        .bind(publisher_id)
        .bind(event.attempt_count)
        .bind(&failure.code)
        .bind(&failure.message)
        .execute(&mut *transaction)
        .await?;

        if result.rows_affected() != 1 {
            return Err(OutboxRepositoryError::UnexpectedState { event_id: event.id });
        }

        sqlx::query(
            r#"
            insert into job.dead_letters (
                source_kind,
                source_id,
                subject,
                idempotency_key,
                payload,
                error_code,
                error_summary,
                error_detail
            )
            values (
                'outbox',
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                jsonb_build_object(
                    'publisher_id', $7,
                    'event_type', $8,
                    'aggregate_type', $9,
                    'aggregate_id', $10::text,
                    'attempt_count', $11
                )
            )
            "#,
        )
        .bind(event.id)
        .bind(&event.subject)
        .bind(&event.idempotency_key)
        .bind(&event.payload)
        .bind(&failure.code)
        .bind(&failure.message)
        .bind(publisher_id)
        .bind(&event.event_type)
        .bind(&event.aggregate_type)
        .bind(event.aggregate_id)
        .bind(event.attempt_count)
        .execute(&mut *transaction)
        .await?;

        transaction.commit().await?;
        Ok(())
    }
}

fn payload_contains_sensitive_fields(value: &Value) -> bool {
    match value {
        Value::Object(map) => map.iter().any(|(key, value)| {
            let key = key.to_ascii_lowercase();
            SENSITIVE_KEY_PARTS.iter().any(|part| key.contains(part))
                || payload_contains_sensitive_fields(value)
        }),
        Value::Array(values) => values.iter().any(payload_contains_sensitive_fields),
        Value::String(text) => string_looks_sensitive(text),
        _ => false,
    }
}

fn string_looks_sensitive(text: &str) -> bool {
    let lowered = text.to_ascii_lowercase();
    (["password=", "token=", "secret=", "credential="]
        .iter()
        .any(|part| lowered.contains(part))
        && SENSITIVE_KEY_PARTS
            .iter()
            .any(|part| lowered.contains(part)))
        || contains_url_credentials(&lowered)
}

fn contains_url_credentials(text: &str) -> bool {
    let Some(scheme_index) = text.find("://") else {
        return false;
    };
    let after_scheme = &text[(scheme_index + 3)..];
    let Some(authority_end) = after_scheme.find('@') else {
        return false;
    };
    after_scheme[..authority_end].contains(':')
}

fn sanitize_failure_message(message: &str) -> String {
    if string_looks_sensitive(message) {
        "redacted sensitive error detail".to_owned()
    } else {
        message.to_owned()
    }
}

#[cfg(test)]
mod tests {
    use std::sync::{Arc, Mutex};

    use super::*;

    #[derive(Clone)]
    struct FakeRepository {
        events: Arc<Mutex<Vec<OutboxEvent>>>,
        published: Arc<Mutex<Vec<Uuid>>>,
        retrying: Arc<Mutex<Vec<Uuid>>>,
        dead_lettered: Arc<Mutex<Vec<Uuid>>>,
    }

    impl FakeRepository {
        fn new(events: Vec<OutboxEvent>) -> Self {
            Self {
                events: Arc::new(Mutex::new(events)),
                published: Arc::new(Mutex::new(Vec::new())),
                retrying: Arc::new(Mutex::new(Vec::new())),
                dead_lettered: Arc::new(Mutex::new(Vec::new())),
            }
        }
    }

    #[async_trait]
    impl OutboxRepository for FakeRepository {
        async fn claim_batch(
            &self,
            _publisher_id: &str,
            batch_size: i64,
            _stale_lock_seconds: i32,
        ) -> Result<Vec<OutboxEvent>, OutboxRepositoryError> {
            let mut events = self.events.lock().unwrap();
            let claimed_count = usize::min(events.len(), batch_size as usize);
            Ok(events.drain(0..claimed_count).collect())
        }

        async fn mark_published(
            &self,
            event_id: Uuid,
            _publisher_id: &str,
            _ack: &PublishAck,
        ) -> Result<(), OutboxRepositoryError> {
            self.published.lock().unwrap().push(event_id);
            Ok(())
        }

        async fn mark_retrying(
            &self,
            event: &OutboxEvent,
            _publisher_id: &str,
            _failure: &PublishFailure,
            _retry_backoff_seconds: i32,
        ) -> Result<(), OutboxRepositoryError> {
            self.retrying.lock().unwrap().push(event.id);
            Ok(())
        }

        async fn mark_dead_lettered(
            &self,
            event: &OutboxEvent,
            _publisher_id: &str,
            _failure: &PublishFailure,
        ) -> Result<(), OutboxRepositoryError> {
            self.dead_lettered.lock().unwrap().push(event.id);
            Ok(())
        }
    }

    #[derive(Clone)]
    struct FakePublisher {
        result: Arc<Mutex<Result<PublishAck, PublishFailure>>>,
        messages: Arc<Mutex<Vec<PublishMessage>>>,
    }

    impl FakePublisher {
        fn succeeding() -> Self {
            Self {
                result: Arc::new(Mutex::new(Ok(PublishAck {
                    provider_message_id: Some("ack-1".to_owned()),
                }))),
                messages: Arc::new(Mutex::new(Vec::new())),
            }
        }

        fn failing(failure: PublishFailure) -> Self {
            Self {
                result: Arc::new(Mutex::new(Err(failure))),
                messages: Arc::new(Mutex::new(Vec::new())),
            }
        }
    }

    #[async_trait]
    impl EventPublisher for FakePublisher {
        async fn publish(&self, message: PublishMessage) -> Result<PublishAck, PublishFailure> {
            self.messages.lock().unwrap().push(message);
            self.result.lock().unwrap().clone()
        }
    }

    #[tokio::test]
    async fn marks_successful_publish_as_published_after_ack() {
        let event = outbox_event(1);
        let repository = FakeRepository::new(vec![event.clone()]);
        let publisher = FakePublisher::succeeding();
        let service = OutboxPublisher::new(
            repository.clone(),
            publisher.clone(),
            OutboxPublisherConfig::new("publisher-a"),
        );

        let summary = service.publish_once().await.unwrap();

        assert_eq!(summary.claimed, 1);
        assert_eq!(summary.published, 1);
        assert_eq!(*repository.published.lock().unwrap(), vec![event.id]);
    }

    #[tokio::test]
    async fn retries_retryable_publish_failure_before_max_attempts() {
        let mut event = outbox_event(2);
        event.attempt_count = 2;
        let repository = FakeRepository::new(vec![event.clone()]);
        let publisher = FakePublisher::failing(PublishFailure::retryable(
            "publish_timeout",
            "publish timed out",
        ));
        let mut config = OutboxPublisherConfig::new("publisher-a");
        config.max_publish_attempts = 5;
        let service = OutboxPublisher::new(repository.clone(), publisher, config);

        let summary = service.publish_once().await.unwrap();

        assert_eq!(summary.retrying, 1);
        assert_eq!(*repository.retrying.lock().unwrap(), vec![event.id]);
        assert!(repository.dead_lettered.lock().unwrap().is_empty());
    }

    #[tokio::test]
    async fn dead_letters_non_retryable_or_exhausted_publish_failure() {
        let mut event = outbox_event(3);
        event.attempt_count = 5;
        let repository = FakeRepository::new(vec![event.clone()]);
        let publisher = FakePublisher::failing(PublishFailure::retryable(
            "publish_timeout",
            "publish timed out",
        ));
        let mut config = OutboxPublisherConfig::new("publisher-a");
        config.max_publish_attempts = 5;
        let service = OutboxPublisher::new(repository.clone(), publisher, config);

        let summary = service.publish_once().await.unwrap();

        assert_eq!(summary.dead_lettered, 1);
        assert_eq!(*repository.dead_lettered.lock().unwrap(), vec![event.id]);
    }

    #[tokio::test]
    async fn publishes_payload_without_interpreting_business_fields() {
        let mut event = outbox_event(4);
        event.payload = serde_json::json!({
            "unknown_business_payload": {
                "nested": ["kept", "as-is"],
                "amount": "123.45"
            }
        });
        let repository = FakeRepository::new(vec![event.clone()]);
        let publisher = FakePublisher::succeeding();
        let service = OutboxPublisher::new(
            repository,
            publisher.clone(),
            OutboxPublisherConfig::new("publisher-a"),
        );

        service.publish_once().await.unwrap();

        let messages = publisher.messages.lock().unwrap();
        assert_eq!(messages[0].payload, event.payload);
        assert_eq!(messages[0].subject, event.subject);
    }

    #[tokio::test]
    async fn dead_letters_message_with_sensitive_payload_before_publish() {
        let mut event = outbox_event(5);
        event.payload = serde_json::json!({
            "task_id": event.id.to_string(),
            "api_token": "secret-token-value"
        });
        let repository = FakeRepository::new(vec![event.clone()]);
        let publisher = FakePublisher::succeeding();
        let service = OutboxPublisher::new(
            repository.clone(),
            publisher.clone(),
            OutboxPublisherConfig::new("publisher-a"),
        );

        let summary = service.publish_once().await.unwrap();

        assert_eq!(summary.dead_lettered, 1);
        assert_eq!(*repository.dead_lettered.lock().unwrap(), vec![event.id]);
        assert!(publisher.messages.lock().unwrap().is_empty());
    }

    fn outbox_event(seed: u128) -> OutboxEvent {
        OutboxEvent {
            id: Uuid::from_u128(seed),
            subject: "finops.jobs.import.parse".to_owned(),
            payload: serde_json::json!({"task_id": seed.to_string()}),
            event_type: "import.parse_requested".to_owned(),
            aggregate_type: "import_file".to_owned(),
            aggregate_id: Uuid::from_u128(seed + 10_000),
            idempotency_key: format!("import.parse:{seed}"),
            trace_id: Some(format!("trace-{seed}")),
            attempt_count: 1,
        }
    }
}
