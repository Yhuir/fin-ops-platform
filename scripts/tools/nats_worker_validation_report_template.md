# NATS Outbox / Worker Staging Validation Report

Date:
Environment:
NATS URL:
Database:
Validator:

## 1. pending -> published -> consumed

- Seed outbox event id:
- Worker task id:
- Expected subject:
- Publisher command:
- Worker command:
- Evidence:
  - `job.outbox_events.status` changed from `pending` to `published`:
  - `job.outbox_events.published_at`:
  - `job.worker_tasks.status` changed to `succeeded`:
  - `job.worker_attempts.nats_stream / nats_consumer / nats_sequence`:
- Result:

## 2. retry

- Injected failure:
- Expected retryable error code:
- Evidence:
  - outbox publisher retry `status='retrying'` and `available_at > now()`:
  - worker retry `status='retrying'` and `next_attempt_at`:
  - NATS message was `nak`ed or redelivered:
- Result:

## 3. dead-letter

- Injected non-retryable or exhausted failure:
- Expected dead-letter source kind:
- Evidence:
  - source row status changed to `dead_lettered`:
  - `job.dead_letters` open row:
  - sanitized `error_detail` contains no secrets:
- Result:

## 4. replay

- Dead letter id:
- Replay command:
- Evidence:
  - `job.dead_letters.replay_status='replayed'`:
  - outbox event or worker task re-entered `retrying` without changing idempotency key:
  - replayed message/task completed or returned to expected retry/dead-letter state:
- Result:

## 5. Commands

```bash
cargo run -p fin-ops-api --bin outbox_publisher --manifest-path rust/fin-ops-api/Cargo.toml -- --once
cargo run -p fin-ops-api --bin outbox_publisher --manifest-path rust/fin-ops-api/Cargo.toml -- --loop
PYTHONPATH=backend/src python3 scripts/tools/job_dead_letter_replay.py list
PYTHONPATH=backend/src python3 scripts/tools/job_dead_letter_replay.py replay --dead-letter-id <uuid>
```

## 6. Sign-off

- Pending/published/consumed:
- Retry:
- Dead-letter:
- Replay:
- Residual risks:
