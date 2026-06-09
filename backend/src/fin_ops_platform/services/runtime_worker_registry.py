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
    read_model_key: str | None = None
    read_model_scope_type: str | None = None

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
        instance_name="workbench",
        worker_kind="workbench-read-model",
        handler_flags=("--enable-workbench-read-model-refresh",),
        event_types=("workbench.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.workbench.env.example",
        rabbitmq_env_example="fin-ops.worker.workbench-rabbitmq.env.example",
        read_model_key="workbench",
        read_model_scope_type="workbench",
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
        instance_name="workbench-relation",
        worker_kind="workbench-relation-read-model",
        handler_flags=("--enable-workbench-relation-read-model-refresh",),
        event_types=("workbench_relation.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.workbench-relation.env.example",
        rabbitmq_env_example="fin-ops.worker.workbench-relation-rabbitmq.env.example",
        read_model_key="workbench_relation",
        read_model_scope_type="workbench_relation",
    ),
    RuntimeWorkerRegistration(
        instance_name="bank-detail",
        worker_kind="bank-detail-read-model",
        handler_flags=("--enable-bank-detail-read-model-refresh",),
        event_types=("bank_detail.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.bank-detail.env.example",
        rabbitmq_env_example="fin-ops.worker.bank-detail-rabbitmq.env.example",
        read_model_key="bank_detail",
        read_model_scope_type="bank_detail",
    ),
    RuntimeWorkerRegistration(
        instance_name="turnover-ledger",
        worker_kind="turnover-ledger-read-model",
        handler_flags=("--enable-turnover-ledger-read-model-refresh",),
        event_types=("turnover_ledger.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.turnover-ledger.env.example",
        rabbitmq_env_example="fin-ops.worker.turnover-ledger-rabbitmq.env.example",
        read_model_key="turnover_ledger",
        read_model_scope_type="turnover_ledger",
    ),
    RuntimeWorkerRegistration(
        instance_name="search-pending",
        worker_kind="search-pending-read-model",
        handler_flags=("--enable-search-read-model-refresh", "--enable-pending-invoice-read-model-refresh"),
        event_types=("search.read_model.refresh", "pending_invoice.read_model.refresh"),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.search-pending.env.example",
        rabbitmq_env_example="fin-ops.worker.search-pending-rabbitmq.env.example",
        read_model_key="search",
        read_model_scope_type="search",
    ),
    RuntimeWorkerRegistration(
        instance_name="invoice-lifecycle",
        worker_kind="invoice-lifecycle-read-model",
        handler_flags=("--enable-invoice-lifecycle-read-model-refresh",),
        event_types=("invoice_lifecycle.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.invoice-lifecycle.env.example",
        rabbitmq_env_example="fin-ops.worker.invoice-lifecycle-rabbitmq.env.example",
        read_model_key="invoice_lifecycle",
        read_model_scope_type="invoice_lifecycle",
    ),
    RuntimeWorkerRegistration(
        instance_name="invoice-usage-collection",
        worker_kind="invoice-usage-collection-read-model",
        handler_flags=(
            "--enable-input-invoice-usage-read-model-refresh",
            "--enable-output-invoice-collection-read-model-refresh",
            "--enable-oa-pending-payment-read-model-refresh",
        ),
        event_types=(
            "input_invoice_usage.read_model.refresh",
            "output_invoice_collection.read_model.refresh",
            "oa_pending_payment.read_model.refresh",
        ),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.invoice-usage-collection.env.example",
        rabbitmq_env_example="fin-ops.worker.invoice-usage-collection-rabbitmq.env.example",
        read_model_key="input_invoice_usage",
        read_model_scope_type="input_invoice_usage",
    ),
    RuntimeWorkerRegistration(
        instance_name="cost-tax",
        worker_kind="cost-tax-read-model",
        handler_flags=("--enable-cost-statistics-read-model-refresh", "--enable-tax-offset-read-model-refresh"),
        event_types=("cost_statistics.read_model.refresh", "tax_offset.read_model.refresh"),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.cost-tax.env.example",
        rabbitmq_env_example="fin-ops.worker.cost-tax-rabbitmq.env.example",
        read_model_key="cost_statistics",
        read_model_scope_type="cost_statistics",
    ),
    RuntimeWorkerRegistration(
        instance_name="import",
        worker_kind="import-job",
        handler_flags=("--enable-import-job-processing",),
        event_types=("import.process.requested",),
        postgres_claim_event_types=("import.process.requested", "import.fact.changed"),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.import.env.example",
        rabbitmq_env_example="fin-ops.worker-import-rabbitmq.env.example",
        heartbeat_stale_after_seconds=900,
    ),
    RuntimeWorkerRegistration(
        instance_name="no-oa-bank-batch",
        worker_kind="no-oa-bank-batch-read-model",
        handler_flags=("--enable-no-oa-bank-batch-read-model-refresh",),
        event_types=("no_oa_bank_batch.read_model.refresh",),
        required=True,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.no-oa-bank-batch.env.example",
        rabbitmq_env_example="fin-ops.worker.no-oa-bank-batch-rabbitmq.env.example",
        read_model_key="no_oa_bank_batch",
        read_model_scope_type="no_oa_bank_batch",
    ),
    RuntimeWorkerRegistration(
        instance_name="bank-account-balance",
        worker_kind="bank-account-balance-read-model",
        handler_flags=("--enable-bank-account-balance-read-model-refresh",),
        event_types=("bank_account_balance.read_model.refresh",),
        required=False,
        rabbitmq_eligible=True,
        env_example="fin-ops.worker.bank-account-balance.env.example",
        rabbitmq_env_example="fin-ops.worker.bank-account-balance-rabbitmq.env.example",
        read_model_key="bank_account_balance",
        read_model_scope_type="bank_account_balance",
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


def read_model_event_types() -> dict[str, tuple[str, str]]:
    event_types: dict[str, tuple[str, str]] = {}
    for registration in worker_registrations():
        if not registration.read_model_key or not registration.read_model_scope_type:
            continue
        for event_type in registration.event_types:
            if not event_type.endswith(".read_model.refresh"):
                continue
            key = _read_model_key_for_event(registration, event_type)
            scope_type = _scope_type_for_event(registration, event_type)
            event_types[event_type] = (key, scope_type)
    return event_types


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


def _read_model_key_for_event(registration: RuntimeWorkerRegistration, event_type: str) -> str:
    prefix = event_type.removesuffix(".read_model.refresh")
    if prefix in {"pending_invoice", "tax_offset", "output_invoice_collection", "oa_pending_payment"}:
        return prefix
    return registration.read_model_key or prefix


def _scope_type_for_event(registration: RuntimeWorkerRegistration, event_type: str) -> str:
    prefix = event_type.removesuffix(".read_model.refresh")
    if prefix in {
        "pending_invoice",
        "tax_offset",
        "output_invoice_collection",
        "oa_pending_payment",
        "bank_account_balance",
    }:
        return prefix
    return registration.read_model_scope_type or prefix
