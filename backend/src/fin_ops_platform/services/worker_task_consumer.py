from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.worker_task_protocol import (
    RetryableWorkerError,
    WorkerDelivery,
    WorkerProtocolError,
    WorkerRunSummary,
    WorkerTaskContext,
    WorkerTaskEnvelope,
    WorkerTaskRepository,
    WorkerTaskRunner,
    sanitize_error_detail,
)


WorkerHandler = Callable[[WorkerTaskEnvelope, WorkerTaskContext], Mapping[str, object] | None]
Clock = Callable[[], datetime]


async def consume_worker_message(
    message: object,
    *,
    repository: WorkerTaskRepository,
    worker_id: str,
    handler: WorkerHandler,
    clock: Clock | None = None,
) -> WorkerRunSummary:
    clock = clock or (lambda: datetime.now(UTC))
    raw_payload = _message_data(message)
    try:
        decoded = json.loads(raw_payload.decode("utf-8"))
        if not isinstance(decoded, dict):
            raise WorkerProtocolError(
                "WORKER_TASK_MESSAGE_INVALID",
                "Worker task message payload must be a JSON object.",
            )
        envelope = WorkerTaskEnvelope.from_mapping(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, WorkerProtocolError) as exc:
        error_code = getattr(exc, "error_code", "WORKER_TASK_MESSAGE_INVALID")
        error_summary = getattr(exc, "error_summary", "Worker task message cannot be decoded.")
        error_detail = getattr(exc, "error_detail", {"exception_type": exc.__class__.__name__})
        repository.record_nats_dead_letter(
            envelope_payload=_dead_letter_payload(raw_payload),
            error_code=error_code,
            error_summary=error_summary,
            error_detail=sanitize_error_detail(dict(error_detail)),
            created_at=clock(),
        )
        await _term_or_ack(message)
        return WorkerRunSummary(
            task_id="",
            attempt_id=None,
            attempt_no=None,
            status="dead_lettered",
            error_code=error_code,
            error_summary=error_summary,
        )

    runner = WorkerTaskRunner(repository=repository, worker_id=worker_id, clock=clock)
    result = runner.run(envelope, handler, delivery=_delivery(message))
    if result.status == "retrying":
        await _nak(message, _retry_delay_seconds(repository, clock))
    elif result.status == "dead_lettered":
        await _term_or_ack(message)
    else:
        await _ack(message)
    return result


async def consume_nats_forever(
    *,
    nats_url: str,
    subject: str,
    durable: str,
    stream: str,
    repository: WorkerTaskRepository,
    worker_id: str,
    handler: WorkerHandler,
    batch_size: int = 1,
    fetch_timeout_seconds: float = 5.0,
    clock: Clock | None = None,
) -> None:
    try:
        import nats  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError("nats-py is required for the NATS worker consumer.") from exc

    nc = await nats.connect(nats_url)
    js = nc.jetstream()
    subscription = await js.pull_subscribe(subject, durable=durable, stream=stream)
    try:
        while True:
            try:
                messages = await subscription.fetch(batch_size, timeout=fetch_timeout_seconds)
            except TimeoutError:
                continue
            for message in messages:
                await consume_worker_message(
                    message,
                    repository=repository,
                    worker_id=worker_id,
                    handler=handler,
                    clock=clock,
                )
    finally:
        await nc.drain()


def _message_data(message: object) -> bytes:
    data = getattr(message, "data", None)
    if isinstance(data, bytes):
        return data
    if isinstance(data, str):
        return data.encode("utf-8")
    raise WorkerProtocolError(
        "WORKER_TASK_MESSAGE_INVALID",
        "Worker task message data must be bytes.",
    )


def _delivery(message: object) -> WorkerDelivery:
    metadata = getattr(message, "metadata", None)
    sequence = getattr(metadata, "sequence", None)
    return WorkerDelivery(
        nats_stream=getattr(metadata, "stream", None),
        nats_consumer=getattr(metadata, "consumer", None),
        nats_sequence=getattr(sequence, "stream", None) if sequence is not None else None,
    )


def _dead_letter_payload(raw_payload: bytes) -> dict[str, object]:
    try:
        decoded = json.loads(raw_payload.decode("utf-8"))
        if isinstance(decoded, dict):
            return dict(decoded)
    except Exception:
        pass
    return {"message_id": "00000000-0000-4000-8000-000000000000", "raw_message": raw_payload.decode("utf-8", errors="replace")}


async def _ack(message: object) -> None:
    if hasattr(message, "ack"):
        await _call_async(getattr(message, "ack"))


async def _nak(message: object, delay_seconds: float | None) -> None:
    if not hasattr(message, "nak"):
        return
    nak = getattr(message, "nak")
    try:
        result = nak(delay_seconds)
    except TypeError:
        result = nak()
    if asyncio.iscoroutine(result):
        await result


async def _term_or_ack(message: object) -> None:
    if hasattr(message, "term"):
        await _call_async(getattr(message, "term"))
        return
    await _ack(message)


async def _call_async(function: Callable[..., Any]) -> None:
    result = function()
    if asyncio.iscoroutine(result):
        await result


def _retry_delay_seconds(repository: WorkerTaskRepository, clock: Clock) -> float | None:
    next_attempt_at = getattr(repository, "next_attempt_at", None)
    if isinstance(next_attempt_at, datetime):
        return max(0.0, (next_attempt_at - clock()).total_seconds())
    return None
