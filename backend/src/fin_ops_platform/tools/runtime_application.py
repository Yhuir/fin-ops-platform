from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.runtime_paths import default_data_dir


def build_tool_runtime_application(data_dir: Path | None) -> Any:
    root = data_dir or default_data_dir()
    app = build_application(data_dir=root, bootstrap_mode="lightweight")
    initialize_runtime_state = getattr(app, "initialize_tool_runtime_state", None)
    runtime_state_snapshot = getattr(app, "tool_runtime_state_snapshot", None)
    if not callable(initialize_runtime_state) or not callable(runtime_state_snapshot):
        raise RuntimeError("Application tool runtime state boundary is unavailable.")
    initialize_runtime_state(runtime_state_snapshot())
    return app


def etc_state_persister(app: Any) -> Callable[[], None]:
    persist = getattr(tool_runtime_ports(app), "persist_etc_state", None)
    if not callable(persist):
        raise RuntimeError("ETC tool runtime state persistence boundary is unavailable.")
    return persist


def invoice_etc_metadata_persister(app: Any) -> Callable[[Any], Any] | None:
    save_invoice_etc_metadata = getattr(tool_runtime_ports(app), "save_invoice_etc_metadata", None)
    return save_invoice_etc_metadata if callable(save_invoice_etc_metadata) else None


def bank_auto_tag_rules_runtime(data_dir: Path | None) -> Any:
    return tool_runtime_ports(build_tool_runtime_application(data_dir))


def tool_runtime_ports(app: Any) -> Any:
    ports = getattr(app, "tool_runtime_ports", None)
    if not callable(ports):
        raise RuntimeError("Application tool runtime ports are unavailable.")
    return ports()


def import_service(app: Any) -> Any:
    return tool_runtime_ports(app).import_service


def etc_service(app: Any) -> Any:
    return tool_runtime_ports(app).etc_service


def etc_reconciliation_task_service(app: Any) -> Any:
    return tool_runtime_ports(app).etc_reconciliation_task_service


def workbench_relation_command_service(app: Any) -> Any:
    return tool_runtime_ports(app).workbench_relation_command_service


def workbench_relation_reader(app: Any) -> Any | None:
    return getattr(tool_runtime_ports(app), "workbench_relation_reader", None)


def bank_transaction_tag_read_facade(app: Any) -> Any:
    facade = getattr(tool_runtime_ports(app), "bank_transaction_tag_read_facade", None)
    if facade is None:
        raise RuntimeError("Bank transaction tag read boundary is unavailable.")
    return facade


def bank_flow_rule_batch_tag_rules_payload(app: Any) -> dict[str, Any]:
    provider = getattr(tool_runtime_ports(app), "get_bank_flow_rule_batch_tag_rules_payload", None)
    if not callable(provider):
        raise RuntimeError("Bank flow rule tag requirements boundary is unavailable.")
    payload = provider()
    if not isinstance(payload, dict):
        raise RuntimeError("Bank flow rule tag requirements payload is invalid.")
    return dict(payload)


def object_identity_repository(app: Any) -> Any | None:
    repository = getattr(tool_runtime_ports(app), "object_identity_repository", None)
    finder = getattr(repository, "find_invoice_by_identity", None)
    return repository if callable(finder) else None


def persist_workbench_pair_relations(app: Any, case_ids: list[str]) -> Any:
    return tool_runtime_ports(app).persist_workbench_pair_relations(case_ids)


def invalidate_workbench_scopes(app: Any, scope_keys: list[str]) -> Any:
    return tool_runtime_ports(app).invalidate_workbench_scopes(scope_keys)
