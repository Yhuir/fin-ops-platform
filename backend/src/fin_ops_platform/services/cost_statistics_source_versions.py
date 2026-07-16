from __future__ import annotations

from typing import Any

from fin_ops_platform.services.cost_statistics_bank_accounts import (
    bank_account_mappings_fingerprint_from_settings_payload,
    bank_auto_tag_rules_version_from_settings_payload,
)

COST_STATISTICS_READ_MODEL_SCHEMA_VERSION = "2026-07-cost-statistics-structured-rows-v9"


def cost_statistics_source_versions(
    *,
    month: str,
    settings_payload: dict[str, Any],
    workbench_source_versions: dict[str, Any] | None = None,
    bank_detail_source_versions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the single business source-version contract shared by publish and query gates."""

    from fin_ops_platform.services.oa_attachment_invoice_cache import (
        attachment_invoice_cache_parser_version,
    )
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
        "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }
    if normalized_month == "all":
        return source_versions
    if workbench_source_versions:
        source_versions["workbench_source_versions"] = dict(workbench_source_versions)
    if bank_detail_source_versions is not None:
        source_versions["bank_detail_source_versions"] = dict(bank_detail_source_versions)
    return source_versions
