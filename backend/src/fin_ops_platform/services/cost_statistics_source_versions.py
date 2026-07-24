from __future__ import annotations

from typing import Any

from fin_ops_platform.services.cost_statistics_bank_accounts import (
    bank_account_mappings_fingerprint_from_settings_payload,
    bank_auto_tag_rules_version_from_settings_payload,
)

COST_STATISTICS_READ_MODEL_SCHEMA_VERSION = "2026-07-cost-statistics-oa-bank-flow-v11"


def cost_statistics_source_versions(
    *,
    month: str,
    settings_payload: dict[str, Any],
    workbench_source_versions: dict[str, Any] | None = None,
    bank_detail_source_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single business source-version contract shared by publish and query gates."""

    from fin_ops_platform.services.postgres_repositories.oa_projection import (
        OA_PROJECTION_SYNC_VERSION,
    )
    from fin_ops_platform.services.workbench_sql_projection import (
        WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
    )

    normalized_month = str(month or "all").strip() or "all"
    source_versions: dict[str, Any] = {
        "cost_statistics_read_model_schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
        "workbench_scope_key": normalized_month,
        "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
        "bank_auto_tag_rules_version": bank_auto_tag_rules_version_from_settings_payload(settings_payload),
        "bank_account_mappings_fingerprint": bank_account_mappings_fingerprint_from_settings_payload(settings_payload),
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }
    if normalized_month != "all" and workbench_source_versions:
        source_versions["workbench_source_versions"] = dict(workbench_source_versions)
    if bank_detail_source_versions is not None:
        source_versions["bank_detail_source_versions"] = dict(bank_detail_source_versions)
    return source_versions


def cost_statistics_semantic_source_versions(source_versions: dict[str, Any]) -> dict[str, Any]:
    """Remove upstream generation counters that Cost does not consume."""

    normalized = dict(source_versions or {})
    workbench = normalized.get("workbench_source_versions")
    if isinstance(workbench, dict):
        normalized["workbench_source_versions"] = {
            key: value
            for key, value in workbench.items()
            if key != "source_version"
        }
    bank_detail = normalized.get("bank_detail_source_versions")
    if isinstance(bank_detail, dict):
        normalized["bank_detail_source_versions"] = {
            key: value
            for key, value in bank_detail.items()
            if key
            not in {
                "source_version",
                "workbench_relation_source_versions",
                "bank_transactions_context_row_count",
                "bank_transactions_updated_at",
            }
        }
    return normalized


def cost_statistics_bank_flow_source_versions(source_versions: dict[str, Any]) -> dict[str, Any]:
    """Return the source proof consumed by Bank Detail-backed Cost views."""

    normalized = cost_statistics_semantic_source_versions(source_versions)
    for key in (
        "workbench_scope_key",
        "workbench_read_model_schema_version",
        "workbench_source_versions",
        "oa_projection_sync_version",
    ):
        normalized.pop(key, None)
    return normalized
