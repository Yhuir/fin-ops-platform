from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
import signal
import unittest
from unittest.mock import patch

from fin_ops_platform.app import rabbitmq_dispatcher
from fin_ops_platform.services.rabbitmq_runtime import (
    RabbitMqConsumer,
    RabbitMqDispatcher,
    RabbitMqDispatcherConfig,
    RabbitMqEnvelopeError,
    RabbitMqPublisher,
    RabbitMqTopologyManager,
    SUPPORTED_EVENT_TYPES,
    rabbitmq_event_routes,
    validate_rabbitmq_envelope,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent, RuntimeQueueSettings
from fin_ops_platform.services.runtime_worker import RuntimeWorkerResult


def event(**overrides: object) -> RuntimeQueueEvent:
    payload = {
        "event_id": "event-1",
        "tenant_id": "default",
        "event_type": "oa.sync",
        "aggregate_type": "oa",
        "aggregate_id": "all",
        "scope_type": "oa",
        "scope_key": "all",
        "dedupe_key": "oa.sync:oa:all",
        "payload": {"source_version": 3},
        "attempts": 0,
        "status": "pending",
        "schema_version": 1,
        "source_version": 3,
        "priority": "normal",
        "trace_id": "trace-1",
    }
    payload.update(overrides)
    return RuntimeQueueEvent(**payload)


class FakeChannel:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.acked: list[object] = []
        self.nacked: list[tuple[object, bool]] = []
        self.rejected: list[tuple[object, bool]] = []
        self.confirmed = False
        self.is_open = True

    def confirm_delivery(self) -> None:
        self.confirmed = True

    def basic_publish(self, **kwargs):
        self.calls.append(("basic_publish", kwargs))
        return True

    def exchange_declare(self, **kwargs):
        self.calls.append(("exchange_declare", kwargs))

    def queue_declare(self, **kwargs):
        self.calls.append(("queue_declare", kwargs))

    def queue_bind(self, **kwargs):
        self.calls.append(("queue_bind", kwargs))

    def basic_ack(self, *, delivery_tag):
        self.acked.append(delivery_tag)

    def basic_nack(self, *, delivery_tag, requeue):
        self.nacked.append((delivery_tag, requeue))

    def basic_reject(self, *, delivery_tag, requeue):
        self.rejected.append((delivery_tag, requeue))

    def basic_qos(self, *, prefetch_count):
        self.calls.append(("basic_qos", {"prefetch_count": prefetch_count}))

    def basic_consume(self, **kwargs):
        self.calls.append(("basic_consume", kwargs))

    def start_consuming(self):
        self.calls.append(("start_consuming", {}))


class ClosedFakeChannel(FakeChannel):
    def __init__(self) -> None:
        super().__init__()
        self.is_open = False

    def basic_publish(self, **kwargs):
        raise RuntimeError("Channel is closed.")


class TimedOutFakeChannel(FakeChannel):
    def basic_publish(self, **kwargs):
        signal.raise_signal(signal.SIGALRM)
        return True


class FakeConnection:
    def __init__(self, channel: FakeChannel) -> None:
        self.channel_obj = channel
        self.closed = False
        self.is_open = True
        self.process_data_events_calls = 0
        self.process_data_events_time_limits: list[float] = []
        self.raise_on_process_data_events: BaseException | None = None
        self.raise_after_process_data_events_calls: int | None = None

    def channel(self) -> FakeChannel:
        return self.channel_obj

    def process_data_events(self, *, time_limit):
        self.process_data_events_calls += 1
        self.process_data_events_time_limits.append(time_limit)
        if (
            self.raise_after_process_data_events_calls is not None
            and self.process_data_events_calls >= self.raise_after_process_data_events_calls
        ):
            raise KeyboardInterrupt()
        if self.raise_on_process_data_events is not None:
            raise self.raise_on_process_data_events

    def close(self) -> None:
        self.closed = True
        self.is_open = False


class FakeQueue:
    def __init__(self) -> None:
        self.events = [event()]
        self.published: list[tuple[str, str, str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.claim_by_id_result = event(status="processing", attempts=1)
        self.current_event: RuntimeQueueEvent | None = None
        self.claim_by_id_calls: list[dict[str, object]] = []

    def claim_publishable_events(self, *, publisher_id, event_types, lock_timeout_seconds, limit):
        return list(self.events)

    def mark_published(self, event_id, *, publisher_id, exchange, routing_key, message_id, confirm_latency_ms=None):
        self.published.append((event_id, exchange, routing_key, message_id))
        return True

    def mark_publish_failed(self, event_id, *, publisher_id, error, retry_delay_seconds):
        self.failed.append((event_id, error))
        return True

    def claim_event_by_id(self, *, event_id, worker_id, event_types, lock_timeout_seconds=300):
        self.claim_by_id_calls.append(
            {
                "event_id": event_id,
                "worker_id": worker_id,
                "event_types": list(event_types),
                "lock_timeout_seconds": lock_timeout_seconds,
            }
        )
        return self.claim_by_id_result

    def get_event(self, event_id):
        return self.current_event


class FakeWorker:
    def __init__(self) -> None:
        self.processed: list[str] = []
        self.heartbeats: list[tuple[str, dict[str, object]]] = []
        self.run_once_calls = 0
        self.run_once_result = RuntimeWorkerResult.IDLE
        self.process_claimed_event_result = RuntimeWorkerResult.PROCESSED

    def process_claimed_event(self, claimed):
        self.processed.append(claimed.event_id)
        return self.process_claimed_event_result

    def record_heartbeat(self, status, payload):
        self.heartbeats.append((status, payload))

    def run_once(self):
        self.run_once_calls += 1
        return self.run_once_result


class RabbitMqRuntimeTests(unittest.TestCase):
    def test_validate_envelope_rejects_business_payload(self) -> None:
        envelope = event().to_envelope()
        envelope["payload"] = {"forbidden": True}

        with self.assertRaises(RabbitMqEnvelopeError):
            validate_rabbitmq_envelope(envelope)

    def test_publisher_sends_persistent_confirmed_json_message(self) -> None:
        settings = RuntimeQueueSettings.from_env(
            {
                "FIN_OPS_QUEUE_BACKEND": "rabbitmq",
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
                "RABBITMQ_EXCHANGE": "finops.events",
            }
        )
        channel = FakeChannel()
        publisher = RabbitMqPublisher(settings, channel=channel)

        result = publisher.publish(event().to_envelope())

        self.assertEqual(result.exchange, "finops.events")
        self.assertEqual(result.routing_key, "oa.sync")
        self.assertEqual(result.message_id, "event-1")
        self.assertTrue(channel.confirmed)
        call = channel.calls[0][1]
        self.assertEqual(call["exchange"], "finops.events")
        self.assertEqual(call["routing_key"], "oa.sync")
        self.assertEqual(call["mandatory"], True)
        self.assertIn(b'"event_id":"event-1"', call["body"])

    def test_publisher_reopens_known_closed_channel_before_publish(self) -> None:
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        closed_channel = ClosedFakeChannel()
        reopened_channel = FakeChannel()
        publisher = RabbitMqPublisher(settings, channel=closed_channel)

        with patch(
            "fin_ops_platform.services.rabbitmq_runtime._open_blocking_connection",
            return_value=FakeConnection(reopened_channel),
        ):
            result = publisher.publish(event().to_envelope())

        self.assertEqual(result.message_id, "event-1")
        self.assertEqual(len(reopened_channel.calls), 1)
        self.assertEqual(closed_channel.calls, [])

    def test_topology_manager_declares_durable_exchange_queue_and_dlq(self) -> None:
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        channel = FakeChannel()

        plan = RabbitMqTopologyManager(settings).apply(channel)

        self.assertEqual(plan["exchange"], "finops.events")
        self.assertEqual([item["event_type"] for item in plan["queues"]], list(SUPPORTED_EVENT_TYPES))
        call_names = [name for name, _kwargs in channel.calls]
        self.assertEqual(call_names[:2], ["exchange_declare", "exchange_declare"])
        self.assertEqual(call_names.count("queue_declare"), len(SUPPORTED_EVENT_TYPES) * 2)
        self.assertEqual(call_names.count("queue_bind"), len(SUPPORTED_EVENT_TYPES) * 2)
        declared_queues = [kwargs["queue"] for name, kwargs in channel.calls if name == "queue_declare"]
        self.assertNotIn("finops.workbench.read_model.refresh", declared_queues)
        self.assertIn("finops.oa.sync", declared_queues)
        self.assertNotIn("finops.no_oa_bank_batch.read_model.refresh", declared_queues)
        self.assertIn("finops.oa.sync.dlq", declared_queues)
        self.assertIn("finops.import.process.requested", declared_queues)

    def test_dispatcher_marks_published_only_after_publisher_success(self) -> None:
        queue = FakeQueue()
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        dispatcher = RabbitMqDispatcher(
            queue_repository=queue,
            publisher=RabbitMqPublisher(settings, channel=channel),
            config=RabbitMqDispatcherConfig(publisher_id="publisher-1", batch_size=10),
        )

        result = dispatcher.dispatch_once()

        self.assertEqual(result["claimed"], 1)
        self.assertEqual(result["published"], 1)
        self.assertEqual(queue.published[0][0], "event-1")
        self.assertEqual(queue.failed, [])

    def test_dispatcher_releases_publish_lock_after_confirm_timeout(self) -> None:
        queue = FakeQueue()
        settings = RuntimeQueueSettings.from_env(
            {
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
                "RABBITMQ_PUBLISH_TIMEOUT_SECONDS": "1",
            }
        )
        dispatcher = RabbitMqDispatcher(
            queue_repository=queue,
            publisher=RabbitMqPublisher(settings, channel=TimedOutFakeChannel()),
            config=RabbitMqDispatcherConfig(publisher_id="publisher-1", batch_size=10),
        )

        result = dispatcher.dispatch_once()

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["published"], 0)
        self.assertIn("publisher confirm exceeded 1 seconds", queue.failed[0][1])

    def test_dispatcher_check_defaults_to_active_registry_event_types(self) -> None:
        stdout = StringIO()

        with patch.dict(
            os.environ,
            {
                "FIN_OPS_QUEUE_BACKEND": "postgres",
                "RABBITMQ_SHADOW_PUBLISH": "true",
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
            },
            clear=True,
        ), redirect_stdout(stdout):
            exit_code = rabbitmq_dispatcher.main(["--check", "--shadow-publish"])

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["event_types"], list(SUPPORTED_EVENT_TYPES))
        self.assertEqual(payload["event_routes"]["oa.sync"]["queue"], "finops.oa.sync")

    def test_rabbitmq_routes_contain_only_registered_domain_events(self) -> None:
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        routes = rabbitmq_event_routes(settings)
        topology = RabbitMqTopologyManager(settings).plan()

        self.assertEqual(
            {
                event_type
                for event_type in SUPPORTED_EVENT_TYPES
                if event_type.endswith(".read_model.refresh")
            },
            set(),
        )
        self.assertEqual(
            {
                item["event_type"]
                for item in topology["queues"]
                if str(item["event_type"]).endswith(".read_model.refresh")
            },
            set(),
        )
        self.assertEqual(routes["oa.sync"].queue, "finops.oa.sync")
        self.assertNotIn("workbench.read_model.refresh", routes)
        self.assertNotIn("no_oa_bank_batch.read_model.refresh", routes)

    def test_consumer_subscribes_to_queues_for_registered_event_types(self) -> None:
        queue = FakeQueue()
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=FakeWorker(),
            worker_id="worker-1",
            event_types=["oa.sync", "import.process.requested"],
            lock_timeout_seconds=300,
        )

        self.assertEqual(
            consumer._queue_names_for_event_types(),
            ["finops.oa.sync", "finops.import.process.requested"],
        )

    def test_consumer_claims_postgres_event_before_acknowledging_rabbitmq(self) -> None:
        queue = FakeQueue()
        worker = FakeWorker()
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=300,
        )

        result = consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=123)

        self.assertEqual(result, RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.processed, ["event-1"])
        self.assertEqual(channel.acked, [123])
        self.assertEqual(channel.nacked, [])
        self.assertEqual(queue.claim_by_id_calls[0]["lock_timeout_seconds"], 300)

    def test_consumer_acks_rabbitmq_envelope_after_postgres_event_is_deferred(self) -> None:
        queue = FakeQueue()
        worker = FakeWorker()
        worker.process_claimed_event_result = RuntimeWorkerResult.DEFERRED
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=300,
        )

        result = consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=456)

        self.assertEqual(result, RuntimeWorkerResult.DEFERRED)
        self.assertEqual(worker.processed, ["event-1"])
        self.assertEqual(channel.acked, [456])
        self.assertEqual(channel.nacked, [])

    def test_consumer_passes_lock_timeout_for_stale_processing_reclaim(self) -> None:
        queue = FakeQueue()
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=FakeWorker(),
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=45,
        )

        consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=789)

        self.assertEqual(queue.claim_by_id_calls[0]["lock_timeout_seconds"], 45)

    def test_consumer_can_drain_postgres_queue_when_no_rabbitmq_message_arrives(self) -> None:
        worker = FakeWorker()
        worker.run_once_result = RuntimeWorkerResult.PROCESSED
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=FakeQueue(),
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=45,
        )

        result = consumer.drain_postgres_queue_once()

        self.assertEqual(result, RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.run_once_calls, 1)

    def test_consumer_drains_postgres_queue_on_short_interval_independent_of_heartbeat(self) -> None:
        worker = FakeWorker()
        worker.run_once_result = RuntimeWorkerResult.IDLE
        channel = FakeChannel()
        connection = FakeConnection(channel)
        connection.raise_after_process_data_events_calls = 4
        settings = RuntimeQueueSettings.from_env(
            {
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
                "RABBITMQ_HEARTBEAT_SECONDS": "60",
                "RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS": "0.1",
            }
        )
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=FakeQueue(),
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=45,
        )

        with patch(
            "fin_ops_platform.services.rabbitmq_runtime._open_blocking_connection",
            return_value=connection,
        ), patch(
            "fin_ops_platform.services.rabbitmq_runtime.monotonic",
            side_effect=[0.0, 0.5, 1.0, 1.5],
        ):
            consumer.consume_forever()

        self.assertEqual(worker.run_once_calls, 3)
        self.assertEqual(connection.process_data_events_time_limits, [0.1, 0.1, 0.1, 0.1])
        idle_heartbeats = [status for status, _payload in worker.heartbeats if status == "idle"]
        self.assertEqual(idle_heartbeats, ["idle"])

    def test_runtime_queue_settings_parses_consumer_postgres_drain_interval(self) -> None:
        settings = RuntimeQueueSettings.from_env(
            {
                "RABBITMQ_URL": "amqp://rabbitmq.internal",
                "RABBITMQ_CONSUMER_POSTGRES_DRAIN_INTERVAL_SECONDS": "0.25",
            }
        )

        self.assertEqual(settings.rabbitmq_consumer_postgres_drain_interval_seconds, 0.25)
        self.assertEqual(
            settings.summary()["rabbitmq_consumer_postgres_drain_interval_seconds"],
            0.25,
        )

    def test_runtime_queue_settings_default_consumer_postgres_drain_interval_is_fast(self) -> None:
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})

        self.assertEqual(settings.rabbitmq_consumer_postgres_drain_interval_seconds, 0.05)

    def test_consumer_records_idle_heartbeat_for_rabbitmq_transport(self) -> None:
        worker = FakeWorker()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=FakeQueue(),
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=300,
        )

        consumer._record_consumer_heartbeat("idle")

        self.assertEqual(worker.heartbeats[0][0], "idle")
        self.assertEqual(worker.heartbeats[0][1]["transport"], "rabbitmq")
        self.assertEqual(worker.heartbeats[0][1]["event_types"], ["oa.sync"])

    def test_consumer_exits_cleanly_on_keyboard_interrupt(self) -> None:
        worker = FakeWorker()
        channel = FakeChannel()
        connection = FakeConnection(channel)
        connection.raise_on_process_data_events = KeyboardInterrupt()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=FakeQueue(),
            worker=worker,
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=300,
        )

        with patch(
            "fin_ops_platform.services.rabbitmq_runtime._open_blocking_connection",
            return_value=connection,
        ):
            consumer.consume_forever()

        self.assertEqual(connection.process_data_events_calls, 1)
        self.assertTrue(connection.closed)
        self.assertEqual(worker.heartbeats[-1][0], "stopped")
        self.assertEqual(worker.heartbeats[-1][1]["transport"], "rabbitmq")

    def test_consumer_rejects_message_without_postgres_fact(self) -> None:
        queue = FakeQueue()
        queue.claim_by_id_result = None
        queue.current_event = None
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=FakeWorker(),
            worker_id="worker-1",
            event_types=["oa.sync"],
            lock_timeout_seconds=300,
        )

        result = consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=456)

        self.assertEqual(result, "rejected_missing_event")
        self.assertEqual(channel.rejected, [(456, False)])

    def test_management_metrics_aggregates_all_supported_queues(self) -> None:
        routes = rabbitmq_event_routes(RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"}))

        self.assertEqual(set(routes), set(SUPPORTED_EVENT_TYPES))
        self.assertEqual(len(SUPPORTED_EVENT_TYPES), len(set(SUPPORTED_EVENT_TYPES)))
        self.assertNotIn("workbench.read_model.refresh", routes)
        self.assertIn("oa.sync", routes)
        self.assertIn("oa.sync", routes)
        self.assertIn("import.process.requested", routes)
        self.assertNotIn("bank_detail.read_model.refresh", routes)
        self.assertNotIn("pending_invoice.read_model.refresh", routes)
        self.assertNotIn("tax_offset.read_model.refresh", routes)


if __name__ == "__main__":
    unittest.main()
