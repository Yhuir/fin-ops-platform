from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from typing import Sequence, TextIO

from fin_ops_platform.services.runtime_worker_registry import (
    RuntimeWorkerRegistration,
    get_registration_by_instance_name,
    required_worker_instance_names,
    worker_check_command_args,
    worker_command_args,
    worker_registrations,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Print fin-ops runtime worker registry metadata.")
    parser.add_argument("--json", action="store_true", help="Print full worker registry as JSON.")
    parser.add_argument("--instances", action="store_true", help="Print all registered worker instance names.")
    parser.add_argument("--required-instances", action="store_true", help="Print required worker instance names.")
    parser.add_argument("--event-types", action="store_true", help="Print all registered durable event types.")
    parser.add_argument("--env-example", help="Print env example filename for a worker instance.")
    parser.add_argument("--worker-check-command", help="Print app.worker --check args for a worker instance.")
    parser.add_argument("--worker-command", help="Print app.worker args for a worker instance.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    if args.instances:
        print(" ".join(registration.instance_name for registration in worker_registrations()), file=stdout)
        return 0
    if args.required_instances:
        print(" ".join(required_worker_instance_names()), file=stdout)
        return 0
    if args.event_types:
        print(
            " ".join(
                sorted(
                    {
                        event_type
                        for registration in worker_registrations()
                        for event_type in registration.event_types
                    }
                )
            ),
            file=stdout,
        )
        return 0
    if args.env_example:
        print(get_registration_by_instance_name(args.env_example).env_example, file=stdout)
        return 0
    if args.worker_check_command:
        registration = get_registration_by_instance_name(args.worker_check_command)
        print(" ".join(worker_check_command_args(registration)), file=stdout)
        return 0
    if args.worker_command:
        registration = get_registration_by_instance_name(args.worker_command)
        print(" ".join(worker_command_args(registration)), file=stdout)
        return 0
    payload = [_registration_payload(registration) for registration in worker_registrations()]
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _registration_payload(registration: RuntimeWorkerRegistration) -> dict[str, object]:
    payload = asdict(registration)
    payload["command_args"] = list(worker_command_args(registration))
    payload["check_command_args"] = list(worker_check_command_args(registration))
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
