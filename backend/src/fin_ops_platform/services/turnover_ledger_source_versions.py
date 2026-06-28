from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION
from fin_ops_platform.services.snapshot_version import snapshot_version
from fin_ops_platform.services.turnover_ledger_service import TURNOVER_LEDGER_SCHEMA_VERSION
from fin_ops_platform.services.turnover_relation_service import TURNOVER_RELATION_SCHEMA_VERSION


def build_turnover_ledger_source_versions(
    *,
    relation_service: Any,
    extra_snapshot_provider: Callable[[], dict[str, Any]],
    app_settings_service: Any,
    bank_transaction_category_service: Any,
    bank_auto_tag_rules_version_provider: Callable[[], Any] | None = None,
    oa_projection_sync_version: str | None = OA_PROJECTION_SYNC_VERSION,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "turnover_ledger_schema_version": TURNOVER_LEDGER_SCHEMA_VERSION,
        "turnover_relation_schema_version": TURNOVER_RELATION_SCHEMA_VERSION,
        "bank_transaction_category_schema_version": BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
        "bank_auto_tag_rules_version": (
            bank_auto_tag_rules_version_provider()
            if bank_auto_tag_rules_version_provider is not None
            else _bank_auto_tag_rules_version(app_settings_service)
        ),
        "turnover_relation_snapshot_version": snapshot_version(
            relation_service.snapshot()
        ),
        "turnover_ledger_extras_snapshot_version": snapshot_version(
            extra_snapshot_provider()
        ),
        "turnover_ledger_tag_selection_snapshot_version": snapshot_version(
            app_settings_service.get_turnover_ledger_tag_selection_payload()
        ),
        "bank_transaction_category_snapshot_version": snapshot_version(
            bank_transaction_category_service.snapshot()
        ),
    }
    if oa_projection_sync_version:
        payload["oa_projection_sync_version"] = oa_projection_sync_version
    return payload


def _bank_auto_tag_rules_version(app_settings_service: Any) -> int:
    get_payload = getattr(app_settings_service, "get_bank_auto_tag_rules_payload", None)
    if not callable(get_payload):
        return 1
    payload = get_payload()
    if not isinstance(payload, dict):
        return 1
    try:
        return int(payload.get("version") or 1)
    except (TypeError, ValueError):
        return 1
