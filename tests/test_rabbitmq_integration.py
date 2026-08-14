from __future__ import annotations

import json
import os
from uuid import uuid4
import unittest

from fin_ops_platform.services.rabbitmq_runtime import RabbitMqPublisher, RabbitMqTopologyManager, rabbitmq_event_routes
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent, RuntimeQueueSettings


def require_rabbitmq_test_url() -> str:
    url = (os.environ.get("RABBITMQ_TEST_URL") or "").strip()
    if not url:
        raise unittest.SkipTest("RABBITMQ_TEST_URL is not set; skipping RabbitMQ integration tests.")
    return url


class RabbitMqIntegrationTests(unittest.TestCase):
    def test_topology_publish_and_consume_envelope(self) -> None:
        rabbitmq_url = require_rabbitmq_test_url()
        suffix = uuid4().hex
        settings = RuntimeQueueSettings.from_env(
            {
                "FIN_OPS_QUEUE_BACKEND": "rabbitmq",
                "RABBITMQ_URL": rabbitmq_url,
                "RABBITMQ_EXCHANGE": f"finops.test.events.{suffix}",
                "RABBITMQ_QUEUE_PREFIX": f"finops.test.{suffix}",
                "RABBITMQ_DEAD_LETTER_EXCHANGE": f"finops.test.events.dlx.{suffix}",
            }
        )
        try:
            import pika
        except ImportError as exc:
            raise unittest.SkipTest("pika is not installed; skipping RabbitMQ integration tests.") from exc

        parameters = pika.URLParameters(rabbitmq_url)
        connection = pika.BlockingConnection(parameters)
        try:
            channel = connection.channel()
            RabbitMqTopologyManager(settings).apply(channel)
            route = rabbitmq_event_routes(settings)["oa.sync"]
            event = RuntimeQueueEvent(
                event_id=str(uuid4()),
                tenant_id="default",
                event_type="oa.sync",
                aggregate_type="oa_sync",
                aggregate_id="all",
                scope_type="oa_sync",
                scope_key="all",
                dedupe_key="oa.sync:default:all",
                payload={"source_version": 1},
                attempts=0,
                status="pending",
                schema_version=1,
                source_version=1,
                priority="normal",
                trace_id="trace-rabbitmq-test",
            )
            RabbitMqPublisher(settings, channel=channel).publish(event.to_envelope())
            _method, _properties, body = channel.basic_get(route.queue, auto_ack=True)
            self.assertIsNotNone(body)
            envelope = json.loads(body.decode("utf-8"))
            self.assertEqual(envelope["event_id"], event.event_id)
            self.assertNotIn("payload", envelope)
        finally:
            channel = connection.channel()
            queues = []
            for route in rabbitmq_event_routes(settings).values():
                queues.extend([route.queue, route.dead_letter_queue])
            for queue in queues:
                try:
                    channel.queue_delete(queue=queue)
                except Exception:
                    pass
            for exchange in (settings.rabbitmq_exchange, settings.rabbitmq_dead_letter_exchange):
                try:
                    channel.exchange_delete(exchange=exchange)
                except Exception:
                    pass
            connection.close()


if __name__ == "__main__":
    unittest.main()
