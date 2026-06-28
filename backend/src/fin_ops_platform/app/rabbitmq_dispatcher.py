from __future__ import annotations

import argparse
import json
import os
from collections.abc import Sequence

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.rabbitmq_runtime import (
    RabbitMqDispatcher,
    RabbitMqDispatcherConfig,
    RabbitMqPublisher,
    rabbitmq_event_routes,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository, RuntimeQueueSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish PostgreSQL outbox envelopes to RabbitMQ with publisher confirms.")
    parser.add_argument("--publisher-id", default=None, help="Stable dispatcher id for PostgreSQL publish locks.")
    parser.add_argument(
        "--event-type",
        action="append",
        default=[],
        help="Outbox event type to publish. Repeatable. Defaults to configured RabbitMQ dispatch event types.",
    )
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--lock-timeout-seconds", type=int, default=300)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--max-iterations", type=int, default=None)
    parser.add_argument("--shadow-publish", action="store_true", help="Allow publishing while FIN_OPS_QUEUE_BACKEND=postgres.")
    parser.add_argument("--check", action="store_true", help="Print dispatcher configuration and exit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = RuntimeQueueSettings.from_env()
    shadow_publish = bool(args.shadow_publish or settings.rabbitmq_shadow_publish)
    if settings.backend != "rabbitmq" and not shadow_publish:
        raise RuntimeError(
            "RabbitMQ dispatcher requires FIN_OPS_QUEUE_BACKEND=rabbitmq or explicit --shadow-publish/RABBITMQ_SHADOW_PUBLISH=true."
        )
    if not settings.rabbitmq_url:
        raise RuntimeError("RabbitMQ dispatcher requires RABBITMQ_URL.")

    event_types = tuple(args.event_type or settings.rabbitmq_dispatch_event_types)
    config = RabbitMqDispatcherConfig(
        publisher_id=args.publisher_id or f"rabbitmq-dispatcher-{os.getpid()}",
        batch_size=args.batch_size,
        lock_timeout_seconds=args.lock_timeout_seconds,
        retry_delay_seconds=args.retry_delay_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        max_iterations=args.max_iterations,
        event_types=event_types,
        shadow_publish=shadow_publish,
    )
    if args.check:
        print(
            json.dumps(
                {
                    "service": "fin-ops-platform-rabbitmq-dispatcher",
                    "queue_backend": settings.backend,
                    "shadow_publish": shadow_publish,
                    "rabbitmq_configured": bool(settings.rabbitmq_url),
                    "rabbitmq_exchange": settings.rabbitmq_exchange,
                    "publisher_id": config.publisher_id,
                    "batch_size": config.batch_size,
                    "event_types": list(config.event_types),
                    "event_routes": {
                        event_type: {
                            "queue": route.queue,
                            "routing_key": route.routing_key,
                            "dead_letter_queue": route.dead_letter_queue,
                            "dead_letter_routing_key": route.dead_letter_routing_key,
                        }
                        for event_type, route in rabbitmq_event_routes(settings).items()
                        if event_type in config.event_types
                    },
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    connection = PostgresConnection(PostgresSettings.from_env())
    queue = RuntimeQueueRepository(connection)
    publisher = RabbitMqPublisher(settings)
    dispatcher = RabbitMqDispatcher(queue_repository=queue, publisher=publisher, config=config)
    try:
        dispatcher.run_forever()
    finally:
        publisher.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
