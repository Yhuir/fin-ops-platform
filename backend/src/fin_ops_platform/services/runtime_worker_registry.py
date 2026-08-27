from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeWorkerRegistration:
    instance_name: str
    worker_kind: str
    handler_flags: tuple[str, ...] = ()
    event_types: tuple[str, ...] = ()
    claim_scope_keys: tuple[str, ...] = ()
    exclude_claim_scope_keys: tuple[str, ...] = ()
    required: bool = False
    env_example: str = ""
    heartbeat_stale_after_seconds: int = 300
    dependencies: tuple[str, ...] = ()


RUNTIME_WORKER_REGISTRY: tuple[RuntimeWorkerRegistration, ...] = (
    RuntimeWorkerRegistration(
        instance_name="oa-sync",
        worker_kind="oa-sync",
        handler_flags=("--enable-oa-sync",),
        event_types=("oa.sync", "oa.payment_status.reconcile"),
        required=True,
        env_example="fin-ops.worker.oa-sync.env.example",
        dependencies=("postgres", "oa_mongo"),
    ),
    RuntimeWorkerRegistration(
        instance_name="workbench-matching",
        worker_kind="workbench-matching",
        handler_flags=("--enable-workbench-matching",),
        required=True,
        env_example="fin-ops.worker.workbench-matching.env.example",
        heartbeat_stale_after_seconds=900,
        dependencies=("postgres", "workbench_matching_dirty_scopes"),
    ),
    RuntimeWorkerRegistration(
        instance_name="import",
        worker_kind="import-job",
        handler_flags=("--enable-import-job-processing",),
        event_types=("import.process.requested",),
        required=True,
        env_example="fin-ops.worker.import.env.example",
        heartbeat_stale_after_seconds=900,
    ),
    RuntimeWorkerRegistration(
        instance_name="settings-maintenance",
        worker_kind="settings-maintenance",
        handler_flags=("--enable-settings-maintenance",),
        event_types=(
            "settings.data_reset.requested",
            "settings.bank_relation_requirements.recalculate.requested",
        ),
        required=True,
        env_example="fin-ops.worker.settings-maintenance.env.example",
        heartbeat_stale_after_seconds=900,
        dependencies=("postgres",),
    ),
)


def worker_registrations(
    *,
    required_only: bool = False,
) -> tuple[RuntimeWorkerRegistration, ...]:
    registrations = RUNTIME_WORKER_REGISTRY
    if required_only:
        registrations = tuple(registration for registration in registrations if registration.required)
    return registrations


def required_worker_instance_names() -> tuple[str, ...]:
    return tuple(registration.instance_name for registration in worker_registrations(required_only=True))


def required_worker_kinds() -> tuple[str, ...]:
    return tuple(registration.worker_kind for registration in worker_registrations(required_only=True))


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
) -> tuple[str, ...]:
    return registration.event_types


def worker_command_args(
    registration: RuntimeWorkerRegistration,
) -> tuple[str, ...]:
    args: list[str] = list(registration.handler_flags)
    for event_type in worker_claim_event_types(registration):
        args.extend(["--event-type", event_type])
    for scope_key in registration.claim_scope_keys:
        args.extend(["--claim-scope-key", scope_key])
    for scope_key in registration.exclude_claim_scope_keys:
        args.extend(["--exclude-claim-scope-key", scope_key])
    return tuple(args)


def worker_check_command_args(
    registration: RuntimeWorkerRegistration,
) -> tuple[str, ...]:
    return (
        "--registration",
        registration.instance_name,
        "--worker-instance",
        registration.instance_name,
        "--check",
    )
