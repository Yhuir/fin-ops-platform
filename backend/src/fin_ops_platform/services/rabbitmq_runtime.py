from __future__ import annotations

from dataclasses import dataclass
from time import monotonic, sleep, time
import base64
import json
from typing import Any, Iterable
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen

from fin_ops_platform.services.runtime_queue import RuntimeQueueDataError, RuntimeQueueEvent, RuntimeQueueSettings
from fin_ops_platform.services.runtime_worker_registry import rabbitmq_dispatch_event_types
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerResult


MAX_ENVELOPE_BYTES = 4096
FORBIDDEN_ENVELOPE_KEYS = {"payload", "raw_payload", "snapshot", "large_snapshot", "business_fact"}
SUPPORTED_EVENT_TYPES = rabbitmq_dispatch_event_types()


@dataclass(frozen=True)
class RabbitMqEventRoute:
    event_type: str
    queue: str
    routing_key: str
    dead_letter_queue: str
    dead_letter_routing_key: str


def rabbitmq_event_routes(settings: RuntimeQueueSettings) -> dict[str, RabbitMqEventRoute]:
    routes: dict[str, RabbitMqEventRoute] = {}
    for event_type in SUPPORTED_EVENT_TYPES:
        queue = _queue_name_for_event(settings, event_type)
        routing_key = _routing_key_for_event(settings, event_type)
        routes[event_type] = RabbitMqEventRoute(
            event_type=event_type,
            queue=queue,
            routing_key=routing_key,
            dead_letter_queue=f"{queue}.dlq",
            dead_letter_routing_key=f"{routing_key}.dead",
        )
    return routes


class RabbitMqRuntimeError(RuntimeError):
    pass


class RabbitMqConfigurationError(RabbitMqRuntimeError):
    pass


class RabbitMqEnvelopeError(RabbitMqRuntimeError):
    pass


class RabbitMqPublishError(RabbitMqRuntimeError):
    pass


@dataclass(frozen=True)
class RabbitMqPublishResult:
    exchange: str
    routing_key: str
    message_id: str
    confirm_latency_ms: float


@dataclass(frozen=True)
class RabbitMqDispatcherConfig:
    publisher_id: str
    batch_size: int = 100
    lock_timeout_seconds: int = 300
    retry_delay_seconds: int = 60
    poll_interval_seconds: float = 5.0
    max_iterations: int | None = None
    event_types: tuple[str, ...] = ()
    shadow_publish: bool = False

    def __post_init__(self) -> None:
        if not str(self.publisher_id or "").strip():
            raise ValueError("publisher_id is required.")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if self.lock_timeout_seconds <= 0:
            raise ValueError("lock_timeout_seconds must be positive.")
        if self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive.")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive.")


def validate_rabbitmq_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise RabbitMqEnvelopeError("RabbitMQ envelope must be a JSON object.")
    forbidden = sorted(key for key in envelope if key in FORBIDDEN_ENVELOPE_KEYS)
    if forbidden:
        raise RabbitMqEnvelopeError(f"RabbitMQ envelope contains forbidden business payload keys: {forbidden}.")
    required = ("schema_version", "event_id", "event_type", "scope_type", "scope_key", "source_version", "priority")
    missing = [key for key in required if key not in envelope]
    if missing:
        raise RabbitMqEnvelopeError(f"RabbitMQ envelope is missing required keys: {missing}.")
    if int(envelope.get("schema_version") or 0) != 1:
        raise RabbitMqEnvelopeError("RabbitMQ envelope schema_version must be 1.")
    for key in ("event_id", "event_type", "scope_type", "scope_key", "priority"):
        if not str(envelope.get(key) or "").strip():
            raise RabbitMqEnvelopeError(f"RabbitMQ envelope key {key} is required.")
    encoded = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > MAX_ENVELOPE_BYTES:
        raise RabbitMqEnvelopeError(f"RabbitMQ envelope is too large: {len(encoded)} bytes.")
    return envelope


class RabbitMqTopologyManager:
    def __init__(self, settings: RuntimeQueueSettings) -> None:
        self._settings = settings

    def plan(self) -> dict[str, Any]:
        return {
            "exchange": self._settings.rabbitmq_exchange,
            "exchange_type": "topic",
            "dead_letter_exchange": self._settings.rabbitmq_dead_letter_exchange,
            "durable": True,
            "prefetch": self._settings.rabbitmq_prefetch,
            "queues": [
                {
                    "event_type": route.event_type,
                    "queue": route.queue,
                    "routing_key": route.routing_key,
                    "dead_letter_queue": route.dead_letter_queue,
                    "dead_letter_routing_key": route.dead_letter_routing_key,
                }
                for route in rabbitmq_event_routes(self._settings).values()
            ],
        }

    def apply(self, channel: Any | None = None) -> dict[str, Any]:
        if channel is not None:
            self._declare(channel)
            return self.plan()
        with _blocking_connection(self._settings) as connection:
            channel = connection.channel()
            self._declare(channel)
        return self.plan()

    def _declare(self, channel: Any) -> None:
        plan = self.plan()
        channel.exchange_declare(exchange=plan["dead_letter_exchange"], exchange_type="topic", durable=True)
        channel.exchange_declare(exchange=plan["exchange"], exchange_type=plan["exchange_type"], durable=True)
        for route in rabbitmq_event_routes(self._settings).values():
            channel.queue_declare(queue=route.dead_letter_queue, durable=True)
            channel.queue_bind(
                queue=route.dead_letter_queue,
                exchange=plan["dead_letter_exchange"],
                routing_key=route.dead_letter_routing_key,
            )
            channel.queue_declare(
                queue=route.queue,
                durable=True,
                arguments={
                    "x-dead-letter-exchange": plan["dead_letter_exchange"],
                    "x-dead-letter-routing-key": route.dead_letter_routing_key,
                },
            )
            channel.queue_bind(queue=route.queue, exchange=plan["exchange"], routing_key=route.routing_key)


class RabbitMqPublisher:
    def __init__(self, settings: RuntimeQueueSettings, *, channel: Any | None = None) -> None:
        self._settings = settings
        self._channel = channel
        self._connection: Any | None = None
        self._confirm_enabled = False

    def close(self) -> None:
        connection = self._connection
        self._connection = None
        self._channel = None
        self._confirm_enabled = False
        if connection is not None:
            close = getattr(connection, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    return

    def publish(self, envelope: dict[str, Any]) -> RabbitMqPublishResult:
        validate_rabbitmq_envelope(envelope)
        channel = self._ensure_channel()
        exchange = self._settings.rabbitmq_exchange
        routing_key = self._routing_key_for(envelope)
        message_id = str(envelope["event_id"])
        body = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        properties = _basic_properties(
            content_type="application/json",
            delivery_mode=2,
            message_id=message_id,
            timestamp=int(time()),
            headers={
                "schema_version": int(envelope["schema_version"]),
                "trace_id": envelope.get("trace_id"),
                "event_type": envelope.get("event_type"),
            },
        )
        started_at = monotonic()
        try:
            published = channel.basic_publish(
                exchange=exchange,
                routing_key=routing_key,
                body=body,
                properties=properties,
                mandatory=True,
            )
        except Exception:
            self.close()
            raise
        if published is False:
            self.close()
            raise RabbitMqPublishError("RabbitMQ basic_publish returned false under publisher confirms.")
        return RabbitMqPublishResult(
            exchange=exchange,
            routing_key=routing_key,
            message_id=message_id,
            confirm_latency_ms=(monotonic() - started_at) * 1000,
        )

    def _ensure_channel(self) -> Any:
        if self._connection is not None and not _is_open(self._connection):
            self.close()
        if self._channel is not None and not _is_open(self._channel):
            self.close()
        if self._channel is None:
            self._connection = _open_blocking_connection(self._settings)
            self._channel = self._connection.channel()
        if self._settings.rabbitmq_publish_confirm and not self._confirm_enabled:
            confirm_delivery = getattr(self._channel, "confirm_delivery", None)
            if callable(confirm_delivery):
                confirm_delivery()
            self._confirm_enabled = True
        return self._channel

    def _routing_key_for(self, envelope: dict[str, Any]) -> str:
        event_type = str(envelope.get("event_type") or "")
        route = rabbitmq_event_routes(self._settings).get(event_type)
        if route is None:
            raise RabbitMqPublishError(f"Unsupported RabbitMQ event type: {event_type}.")
        return route.routing_key


class RabbitMqDispatcher:
    def __init__(self, *, queue_repository: Any, publisher: RabbitMqPublisher, config: RabbitMqDispatcherConfig) -> None:
        self._queue = queue_repository
        self._publisher = publisher
        self._config = config

    def dispatch_once(self) -> dict[str, Any]:
        paused = getattr(self._queue, "is_runtime_control_paused", None)
        if callable(paused) and paused("dispatcher"):
            return {"claimed": 0, "published": 0, "failed": 0, "paused": True, "event_ids": []}
        events = self._queue.claim_publishable_events(
            publisher_id=self._config.publisher_id,
            event_types=self._config.event_types,
            lock_timeout_seconds=self._config.lock_timeout_seconds,
            limit=self._config.batch_size,
        )
        result: dict[str, Any] = {"claimed": len(events), "published": 0, "failed": 0, "event_ids": []}
        for event in events:
            result["event_ids"].append(event.event_id)
            try:
                publish_result = self._publisher.publish(event.to_envelope())
                marked = self._queue.mark_published(
                    event.event_id,
                    publisher_id=self._config.publisher_id,
                    exchange=publish_result.exchange,
                    routing_key=publish_result.routing_key,
                    message_id=publish_result.message_id,
                    confirm_latency_ms=publish_result.confirm_latency_ms,
                )
                if not marked:
                    raise RabbitMqPublishError(f"PostgreSQL publish confirm update failed for event {event.event_id}.")
                result["published"] += 1
            except Exception as exc:
                self._queue.mark_publish_failed(
                    event.event_id,
                    publisher_id=self._config.publisher_id,
                    error=str(exc) or exc.__class__.__name__,
                    retry_delay_seconds=self._config.retry_delay_seconds,
                )
                result["failed"] += 1
        return result

    def run_forever(self) -> None:
        iterations = 0
        while self._config.max_iterations is None or iterations < self._config.max_iterations:
            result = self.dispatch_once()
            iterations += 1
            if int(result.get("claimed") or 0) == 0:
                sleep(self._config.poll_interval_seconds)


class RabbitMqConsumer:
    def __init__(
        self,
        *,
        settings: RuntimeQueueSettings,
        queue_repository: Any,
        worker: RuntimeWorker,
        worker_id: str,
        event_types: Iterable[str],
        lock_timeout_seconds: int,
    ) -> None:
        self._settings = settings
        self._queue = queue_repository
        self._worker = worker
        self._worker_id = worker_id
        self._event_types = tuple(event_types)
        self._lock_timeout_seconds = lock_timeout_seconds

    def process_envelope(self, envelope: dict[str, Any], *, channel: Any, delivery_tag: Any) -> RuntimeWorkerResult | str:
        try:
            validate_rabbitmq_envelope(envelope)
        except RabbitMqEnvelopeError:
            channel.basic_reject(delivery_tag=delivery_tag, requeue=False)
            return "rejected_invalid_envelope"

        event_id = str(envelope["event_id"])
        event = self._queue.claim_event_by_id(
            event_id=event_id,
            worker_id=self._worker_id,
            event_types=self._event_types,
            lock_timeout_seconds=self._lock_timeout_seconds,
        )
        if event is None:
            current = self._queue.get_event(event_id)
            if current is None:
                channel.basic_reject(delivery_tag=delivery_tag, requeue=False)
                return "rejected_missing_event"
            channel.basic_ack(delivery_tag=delivery_tag)
            return f"acked_non_claimable_{current.status}"

        try:
            result = self._worker.process_claimed_event(event)
        except Exception:
            channel.basic_nack(delivery_tag=delivery_tag, requeue=True)
            raise
        channel.basic_ack(delivery_tag=delivery_tag)
        return result

    def consume_forever(self) -> None:
        paused = getattr(self._queue, "is_runtime_control_paused", None)
        if callable(paused) and paused("consumer"):
            raise RabbitMqRuntimeError("RabbitMQ consumer is paused by runtime:rabbitmq_control.")
        with _blocking_connection(self._settings) as connection:
            channel = connection.channel()
            channel.basic_qos(prefetch_count=self._settings.rabbitmq_prefetch)

            def on_message(ch: Any, method: Any, _properties: Any, body: bytes) -> None:
                envelope = json.loads(body.decode("utf-8"))
                self.process_envelope(envelope, channel=ch, delivery_tag=method.delivery_tag)

            for queue_name in self._queue_names_for_event_types():
                channel.basic_consume(queue=queue_name, on_message_callback=on_message)
            heartbeat_interval_seconds = min(30.0, max(5.0, float(self._settings.rabbitmq_heartbeat_seconds) / 2.0))
            next_heartbeat_at = 0.0
            while True:
                try:
                    connection.process_data_events(time_limit=1.0)
                    now = monotonic()
                    if now >= next_heartbeat_at:
                        drain_result = self.drain_postgres_queue_once()
                        heartbeat_status = (
                            "postgres_queue_processed"
                            if drain_result == RuntimeWorkerResult.PROCESSED
                            else "idle"
                        )
                        self._record_consumer_heartbeat(heartbeat_status)
                        next_heartbeat_at = now + heartbeat_interval_seconds
                except KeyboardInterrupt:
                    self._record_consumer_heartbeat("stopped")
                    return

    def drain_postgres_queue_once(self) -> RuntimeWorkerResult | str:
        try:
            return self._worker.run_once()
        except Exception as exc:
            self._record_consumer_heartbeat(
                "postgres_queue_error",
                {
                    "transport": "rabbitmq",
                    "event_types": list(self._event_types),
                    "error": str(exc) or exc.__class__.__name__,
                },
            )
            return "postgres_queue_error"

    def _record_consumer_heartbeat(self, status: str) -> None:
        record = getattr(self._worker, "record_heartbeat", None)
        if callable(record):
            record(
                status,
                {
                    "transport": "rabbitmq",
                    "event_types": list(self._event_types),
                    "consumer_idle": status == "idle",
                },
            )

    def _queue_names_for_event_types(self) -> list[str]:
        routes = rabbitmq_event_routes(self._settings)
        queue_names: list[str] = []
        for event_type in self._event_types:
            route = routes.get(event_type)
            if route is None:
                raise RabbitMqConfigurationError(f"Unsupported RabbitMQ consumer event type: {event_type}.")
            if route.queue not in queue_names:
                queue_names.append(route.queue)
        if not queue_names:
            raise RabbitMqConfigurationError("RabbitMQ consumer requires at least one supported event type.")
        return queue_names


class RabbitMqManagementMetrics:
    def __init__(self, settings: RuntimeQueueSettings) -> None:
        self._settings = settings

    def summary(self) -> dict[str, Any]:
        if not self._settings.rabbitmq_management_url:
            return {"rabbitmq_management_configured": False}
        try:
            queues: dict[str, Any] = {}
            total_depth = 0
            total_unacked = 0
            total_consumers = 0
            total_dlq = 0
            for route in rabbitmq_event_routes(self._settings).values():
                queue = self._fetch_queue(route.queue)
                dlq = self._fetch_queue(route.dead_letter_queue)
                queue_depth = int(queue.get("messages") or 0)
                unacked = int(queue.get("messages_unacknowledged") or 0)
                consumers = int(queue.get("consumers") or 0)
                dlq_count = int(dlq.get("messages") or 0)
                total_depth += queue_depth
                total_unacked += unacked
                total_consumers += consumers
                total_dlq += dlq_count
                queues[route.event_type] = {
                    "queue": route.queue,
                    "routing_key": route.routing_key,
                    "messages": queue_depth,
                    "unacked": unacked,
                    "consumers": consumers,
                    "dead_letter_queue": route.dead_letter_queue,
                    "dead_letter_messages": dlq_count,
                }
            return {
                "rabbitmq_management_configured": True,
                "rabbitmq_queue_depth": total_depth,
                "rabbitmq_unacked_messages": total_unacked,
                "rabbitmq_consumer_count": total_consumers,
                "rabbitmq_dlq_count": total_dlq,
                "rabbitmq_oldest_message_age_seconds": None,
                "rabbitmq_queues": queues,
            }
        except Exception as exc:
            return {
                "rabbitmq_management_configured": True,
                "rabbitmq_metric_error": str(exc) or exc.__class__.__name__,
            }

    def _fetch_queue(self, queue_name: str) -> dict[str, Any]:
        base_url = self._settings.rabbitmq_management_url or ""
        url = urljoin(
            base_url.rstrip("/") + "/",
            f"api/queues/{quote(self._settings.rabbitmq_vhost or '/', safe='')}/{quote(queue_name, safe='')}",
        )
        request = Request(url)
        username = self._settings.rabbitmq_management_username
        password = self._settings.rabbitmq_management_password
        if username and password:
            token = base64.b64encode(f"{username}:{password}".encode()).decode()
            request.add_header("Authorization", f"Basic {token}")
        with urlopen(request, timeout=self._settings.rabbitmq_management_timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return payload if isinstance(payload, dict) else {}


def _open_blocking_connection(settings: RuntimeQueueSettings) -> Any:
    if not settings.rabbitmq_url:
        raise RabbitMqConfigurationError("RABBITMQ_URL is required when RabbitMQ runtime is enabled.")
    try:
        import pika
    except ImportError as exc:  # pragma: no cover - depends on deployment environment.
        raise RabbitMqConfigurationError("RabbitMQ runtime requires the pika package.") from exc
    parameters = pika.URLParameters(settings.rabbitmq_url)
    if settings.rabbitmq_vhost:
        parameters.virtual_host = settings.rabbitmq_vhost
    parameters.heartbeat = settings.rabbitmq_heartbeat_seconds
    parameters.blocked_connection_timeout = settings.rabbitmq_blocked_connection_timeout_seconds
    return pika.BlockingConnection(parameters)


def _is_open(candidate: Any) -> bool:
    is_open = getattr(candidate, "is_open", None)
    if isinstance(is_open, bool):
        return is_open
    is_closed = getattr(candidate, "is_closed", None)
    if isinstance(is_closed, bool):
        return not is_closed
    return True


class _blocking_connection:
    def __init__(self, settings: RuntimeQueueSettings) -> None:
        self._settings = settings
        self._connection: Any | None = None

    def __enter__(self) -> Any:
        self._connection = _open_blocking_connection(self._settings)
        return self._connection

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> bool:
        if self._connection is not None:
            self._connection.close()
        return False


def _basic_properties(**kwargs: Any) -> Any:
    try:
        import pika
    except ImportError:  # pragma: no cover - tests pass fake channels without constructing properties.
        return kwargs
    return pika.BasicProperties(**kwargs)


def _queue_name_for_event(settings: RuntimeQueueSettings, event_type: str) -> str:
    if event_type == "workbench.read_model.refresh":
        return settings.rabbitmq_workbench_queue
    return f"{settings.rabbitmq_queue_prefix}.{event_type}"


def _routing_key_for_event(settings: RuntimeQueueSettings, event_type: str) -> str:
    if event_type == "workbench.read_model.refresh":
        return settings.rabbitmq_workbench_routing_key
    return event_type
