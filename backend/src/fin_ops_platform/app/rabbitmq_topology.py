from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.rabbitmq_runtime import RabbitMqTopologyManager
from fin_ops_platform.services.runtime_queue import RuntimeQueueSettings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or apply fin-ops RabbitMQ topology.")
    parser.add_argument("--apply", action="store_true", help="Declare durable RabbitMQ exchange, queue, DLX and DLQ.")
    parser.add_argument("--check", action="store_true", help="Print topology plan without declaring broker resources.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = RuntimeQueueSettings.from_env()
    manager = RabbitMqTopologyManager(settings)
    if args.apply:
        payload = {"status": "applied", "topology": manager.apply()}
    else:
        payload = {"status": "planned", "topology": manager.plan()}
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
