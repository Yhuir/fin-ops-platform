from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


RuntimeWorkerTransport = Literal["postgres", "rabbitmq"]


@dataclass(frozen=True)
class RuntimeWorkerRegistration:
    instance_name: str
    worker_kind: str
    handler_flags: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    postgres_claim_event_types: tuple[str, ...] = ()
    required: bool = False
    rabbitmq_eligible: bool = False
    env_example: str = ""
    rabbitmq_env_example: str | None = None
    heartbeat_stale_after_seconds: int = 300
    dependencies: tuple[str, ...] = ()

    def claim_event_types(self, *, transport: RuntimeWorkerTransport = "postgres") -> tuple[str, ...]:
        if transport == "postgres" and self.postgres_claim_event_types:
            return self.postgres_claim_event_types
        return self.event_types


RUNTIME_WORKER_REGISTRY: tuple[RuntimeWorkerRegistration, ...] = (
    RuntimeWorkerRegistration(
        instance_name="oa-sync",
        worker_kind="oa-sync",
        handler_flags=("--enable-oa-sync",),
        event_types=("oa.sync",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.oa-sync.env.example",
        rabbitmq_env_example="fin-ops.worker.oa-sync-rabbitmq.env.example",
        dependencies=("postgres", "oa_mongo"),
    ),
    RuntimeWorkerRegistration(
        instance_name="workbench-matching",
        worker_kind="workbench-matching",
        handler_flags=("--enable-workbench-matching",),
        required=True,
        rabbitmq_eligible=False,
        env_example="fin-ops.worker.workbench-matching.env.example",
        heartbeat_stale_after_seconds=900,
        dependencies=("postgres", "workbench_matching_dirty_scopes"),
    ),
    RuntimeWorkerRegistration(
        instance_name="import",
        worker_kind="import-job",
        handler_flags=("--enable-import-job-processing",),
        event_types=("import.process.requested", "import.fact.changed"),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.import.env.example",
        rabbitmq_env_example="fin-ops.worker-import-rabbitmq.env.example",
        heartbeat_stale_after_seconds=900,
    ),
    RuntimeWorkerRegistration(
        instance_name="file-migration",
        worker_kind="file-object-migration",
        handler_flags=("--enable-file-object-migration",),
        event_types=("file_object.gridfs_migration",),
        required=False,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.file-migration.env.example",
        rabbitmq_env_example="fin-ops.worker.file-migration-rabbitmq.env.example",
        heartbeat_stale_after_seconds=900,
        dependencies=("postgres", "legacy_gridfs", "object_storage"),
    ),
)


def worker_registrations(
    *,
    required_only: bool = False,
    rabbitmq_eligible_only: bool = False,
) -> tuple[RuntimeWorkerRegistration, ...]:
    registrations = RUNTIME_WORKER_REGISTRY
    if required_only:
        registrations = tuple(registration for registration in registrations if registration.required)
    if rabbitmq_eligible_only:
        registrations = tuple(registration for registration in registrations if registration.rabbitmq_eligible)
    return registrations


def required_worker_instance_names() -> tuple[str, ...]:
    return tuple(registration.instance_name for registration in worker_registrations(required_only=True))


def required_worker_kinds() -> tuple[str, ...]:
    return tuple(registration.worker_kind for registration in worker_registrations(required_only=True))


def rabbitmq_dispatch_event_types() -> tuple[str, ...]:
    return _unique_event_types(worker_registrations(rabbitmq_eligible_only=True))


def registration_by_worker_kind() -> dict[str, RuntimeWorkerRegistration]:
    return {registration.worker_kind: registration for registration in worker_registrations()}


def registration_by_instance_name() -> dict[str, RuntimeWorkerRegistration]:
    return {registration.instance_name: registration for registration in worker_registrations()}


def get_registration_by_instance_name(instance_name: str) -> RuntimeWorkerRegistration:
    normalized = str(instance_name or "").strip()
    registration = registration_by_instance_name().get(normalized)
    if registration is None:
        raise KeyError(f"Unknown runtime worker registration: {normalized!r}.")
    return registration


def worker_claim_event_types(
    registration: RuntimeWorkerRegistration,
    *,
    transport: RuntimeWorkerTransport = "postgres",
) -> tuple[str, ...]:
    return registration.claim_event_types(transport=transport)


def worker_command_args(
    registration: RuntimeWorkerRegistration,
    *,
    transport: RuntimeWorkerTransport = "postgres",
) -> tuple[str, ...]:
    args: list[str] = list(registration.handler_flags)
    for event_type in worker_claim_event_types(registration, transport=transport):
        args.extend(["--event-type", event_type])
    return tuple(args)


def worker_check_command_args(
    registration: RuntimeWorkerRegistration,
    *,
    transport: RuntimeWorkerTransport = "postgres",
) -> tuple[str, ...]:
    return (
        "--registration",
        registration.instance_name,
        "--worker-instance",
        registration.instance_name,
        "--check",
    )


def _unique_event_types(registrations: tuple[RuntimeWorkerRegistration, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    event_types: list[str] = []
    for registration in registrations:
        for event_type in registration.event_types:
            if event_type in seen:
                continue
            seen.add(event_type)
            event_types.append(event_type)
    return tuple(event_types)
