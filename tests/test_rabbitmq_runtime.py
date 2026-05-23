from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
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
        "event_type": "workbench.read_model.refresh",
        "aggregate_type": "read_model",
        "aggregate_id": "all",
        "scope_type": "workbench",
        "scope_key": "all",
        "dedupe_key": "workbench.read_model.refresh:workbench:all",
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


class FakeQueue:
    def __init__(self) -> None:
        self.events = [event()]
        self.published: list[tuple[str, str, str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self.claim_by_id_result = event(status="processing", attempts=1)
        self.current_event: RuntimeQueueEvent | None = None

    def claim_publishable_events(self, *, publisher_id, event_types, lock_timeout_seconds, limit):
        return list(self.events)

    def mark_published(self, event_id, *, publisher_id, exchange, routing_key, message_id, confirm_latency_ms=None):
        self.published.append((event_id, exchange, routing_key, message_id))
        return True

    def mark_publish_failed(self, event_id, *, publisher_id, error, retry_delay_seconds):
        self.failed.append((event_id, error))
        return True

    def claim_event_by_id(self, *, event_id, worker_id, event_types):
        return self.claim_by_id_result

    def get_event(self, event_id):
        return self.current_event


class FakeWorker:
    def __init__(self) -> None:
        self.processed: list[str] = []
        self.heartbeats: list[tuple[str, dict[str, object]]] = []

    def process_claimed_event(self, claimed):
        self.processed.append(claimed.event_id)
        return RuntimeWorkerResult.PROCESSED

    def record_heartbeat(self, status, payload):
        self.heartbeats.append((status, payload))


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
                "RABBITMQ_WORKBENCH_ROUTING_KEY": "workbench.read_model.refresh",
            }
        )
        channel = FakeChannel()
        publisher = RabbitMqPublisher(settings, channel=channel)

        result = publisher.publish(event().to_envelope())

        self.assertEqual(result.exchange, "finops.events")
        self.assertEqual(result.routing_key, "workbench.read_model.refresh")
        self.assertEqual(result.message_id, "event-1")
        self.assertTrue(channel.confirmed)
        call = channel.calls[0][1]
        self.assertEqual(call["exchange"], "finops.events")
        self.assertEqual(call["routing_key"], "workbench.read_model.refresh")
        self.assertEqual(call["mandatory"], True)
        self.assertIn(b'"event_id":"event-1"', call["body"])

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
        self.assertIn("finops.workbench.read_model.refresh", declared_queues)
        self.assertIn("finops.search.read_model.refresh", declared_queues)
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

    def test_dispatcher_check_defaults_to_workbench_event_type(self) -> None:
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
        self.assertEqual(payload["event_routes"]["search.read_model.refresh"]["queue"], "finops.search.read_model.refresh")

    def test_consumer_subscribes_to_queues_for_registered_event_types(self) -> None:
        queue = FakeQueue()
        channel = FakeChannel()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=queue,
            worker=FakeWorker(),
            worker_id="worker-1",
            event_types=["search.read_model.refresh", "pending_invoice.read_model.refresh"],
            lock_timeout_seconds=300,
        )

        self.assertEqual(
            consumer._queue_names_for_event_types(),
            ["finops.search.read_model.refresh", "finops.pending_invoice.read_model.refresh"],
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
            event_types=["workbench.read_model.refresh"],
            lock_timeout_seconds=300,
        )

        result = consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=123)

        self.assertEqual(result, RuntimeWorkerResult.PROCESSED)
        self.assertEqual(worker.processed, ["event-1"])
        self.assertEqual(channel.acked, [123])
        self.assertEqual(channel.nacked, [])

    def test_consumer_records_idle_heartbeat_for_rabbitmq_transport(self) -> None:
        worker = FakeWorker()
        settings = RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"})
        consumer = RabbitMqConsumer(
            settings=settings,
            queue_repository=FakeQueue(),
            worker=worker,
            worker_id="worker-1",
            event_types=["workbench.read_model.refresh"],
            lock_timeout_seconds=300,
        )

        consumer._record_consumer_heartbeat("idle")

        self.assertEqual(worker.heartbeats[0][0], "idle")
        self.assertEqual(worker.heartbeats[0][1]["transport"], "rabbitmq")
        self.assertEqual(worker.heartbeats[0][1]["event_types"], ["workbench.read_model.refresh"])

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
            event_types=["workbench.read_model.refresh"],
            lock_timeout_seconds=300,
        )

        result = consumer.process_envelope(event().to_envelope(), channel=channel, delivery_tag=456)

        self.assertEqual(result, "rejected_missing_event")
        self.assertEqual(channel.rejected, [(456, False)])

    def test_management_metrics_aggregates_all_supported_queues(self) -> None:
        routes = rabbitmq_event_routes(RuntimeQueueSettings.from_env({"RABBITMQ_URL": "amqp://rabbitmq.internal"}))

        self.assertEqual(routes["cost_statistics.read_model.refresh"].routing_key, "cost_statistics.read_model.refresh")
        self.assertEqual(routes["tax_offset.read_model.refresh"].queue, "finops.tax_offset.read_model.refresh")


if __name__ == "__main__":
    unittest.main()
