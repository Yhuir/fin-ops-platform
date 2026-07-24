from __future__ import annotations

from fin_ops_platform.services.input_invoice_usage_service import SOURCE_VERSION as INPUT_INVOICE_USAGE_SOURCE_VERSION
from fin_ops_platform.services.invoice_lifecycle_policy import INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.output_invoice_collection_service import (
    SOURCE_VERSION as OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION,
)
from fin_ops_platform.services.oa_pending_payment_projection_rows import (
    OA_PENDING_PAYMENT_PROJECTION_RULES_VERSION,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)


def input_invoice_usage_source_versions(
    payment_status_rules_version: int | str | None = None,
    *,
    oa_reverse_batch_source_version: str | None = None,
) -> dict[str, object]:
    normalized_rules_version = payment_status_rules_version if payment_status_rules_version not in (None, "") else 1
    versions: dict[str, object] = {
        "input_invoice_usage_source_version": INPUT_INVOICE_USAGE_SOURCE_VERSION,
        "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
        "input_invoice_usage_payment_rules_version": normalized_rules_version,
        "input_invoice_usage_statistics_schema_version": 2,
        "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }
    if oa_reverse_batch_source_version not in (None, ""):
        versions["input_invoice_usage_oa_reverse_batch_source_version"] = str(oa_reverse_batch_source_version)
    return versions


def output_invoice_collection_source_versions() -> dict[str, object]:
    return {
        "output_invoice_collection_source_version": OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION,
        "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
        "output_invoice_collection_lifecycle_schema_version": 1,
        "output_invoice_collection_status_rules_version": "sheet6-static-v1+lifecycle-v1",
        "output_invoice_receipt_schema_version": 1,
        "output_invoice_collection_statistics_schema_version": 1,
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }


def oa_pending_payment_source_versions() -> dict[str, object]:
    return {
        "oa_pending_payment_source_version": OA_PENDING_PAYMENT_PROJECTION_RULES_VERSION,
        "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
        "oa_pending_payment_canonical_relation_schema_version": 1,
        "oa_pending_payment_bank_import_fact_schema_version": 1,
        "oa_pending_payment_input_invoice_import_fact_schema_version": 1,
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }


def invoice_relation_dependency_status(
    *,
    scope_state: dict[str, object],
    relation_state: dict[str, object],
    base_source_versions: dict[str, object],
) -> dict[str, object]:
    required_base_source_versions = require_expected_source_versions(
        base_source_versions,
        context="invoice_usage_collection_base_dependency",
    )
    scope_keys = [
        str(scope_key).strip()
        for scope_key in list(scope_state.get("scope_keys") or [])
        if str(scope_key).strip()
    ]
    consumer_versions_by_scope = (
        scope_state.get("source_versions_by_scope")
        if isinstance(scope_state.get("source_versions_by_scope"), dict)
        else {}
    )
    canonical_versions_by_scope = (
        scope_state.get("canonical_source_versions_by_scope")
        if isinstance(scope_state.get("canonical_source_versions_by_scope"), dict)
        else {}
    )
    relation_versions_by_scope = (
        relation_state.get("read_model_scope_source_versions")
        if isinstance(relation_state.get("read_model_scope_source_versions"), dict)
        else {}
    )
    blocking_scope_keys = [
        str(scope_key).strip()
        for scope_key in list(scope_state.get("blocking_scope_keys") or [])
        if str(scope_key).strip()
    ]
    active_event_scope_keys = {
        str(scope_key).strip()
        for scope_key in list(scope_state.get("active_event_scope_keys") or [])
        if str(scope_key).strip()
    }
    stale_reasons: list[str] = []
    for scope_key in scope_keys:
        consumer_versions = consumer_versions_by_scope.get(scope_key)
        canonical_versions = canonical_versions_by_scope.get(scope_key)
        required_scope_source_versions = require_expected_source_versions(
            {
                **required_base_source_versions,
                **(
                    canonical_versions
                    if isinstance(canonical_versions, dict)
                    else {}
                ),
            },
            context=f"invoice_usage_collection_source_dependency:{scope_key}",
        )
        mismatch_reasons = source_version_mismatch_reasons(
            expected=required_scope_source_versions,
            actual=consumer_versions if isinstance(consumer_versions, dict) else {},
        )
        if mismatch_reasons:
            blocking_scope_keys.append(scope_key)
            stale_reasons.extend(
                f"{scope_key}:{reason}"
                for reason in mismatch_reasons
            )
    relation_status = str(relation_state.get("status") or "unavailable").strip()
    if relation_status != "fresh":
        relation_blocking_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(relation_state.get("refresh_scope_keys") or scope_keys)
            if str(scope_key).strip()
        ]
        blocking_scope_keys.extend(relation_blocking_scope_keys)
        stale_reasons.extend(
            f"workbench_relation:{reason}"
            for reason in list(relation_state.get("stale_reasons") or [relation_status])
            if str(reason).strip()
        )
    else:
        for scope_key in scope_keys:
            consumer_versions = consumer_versions_by_scope.get(scope_key)
            embedded_relation_versions = (
                consumer_versions.get("workbench_relation_source_versions")
                if isinstance(consumer_versions, dict)
                and isinstance(consumer_versions.get("workbench_relation_source_versions"), dict)
                else {}
            )
            current_relation_versions = relation_versions_by_scope.get(scope_key)
            if not isinstance(current_relation_versions, dict) or not current_relation_versions:
                blocking_scope_keys.append(scope_key)
                stale_reasons.append(
                    f"{scope_key}:workbench_relation:source_versions_missing"
                )
                continue
            required_relation_source_versions = require_expected_source_versions(
                current_relation_versions,
                context=f"invoice_usage_collection_relation_dependency:{scope_key}",
            )
            mismatch_reasons = source_version_mismatch_reasons(
                expected=required_relation_source_versions,
                actual=embedded_relation_versions,
            )
            if mismatch_reasons:
                blocking_scope_keys.append(scope_key)
                stale_reasons.extend(
                    f"{scope_key}:workbench_relation:{reason}"
                    for reason in mismatch_reasons
                )
    normalized_blocking_scope_keys = list(dict.fromkeys(blocking_scope_keys))
    return {
        "status": "fresh" if not normalized_blocking_scope_keys else "refreshing",
        "scope_keys": scope_keys,
        "blocking_scope_keys": normalized_blocking_scope_keys,
        "refresh_scope_keys": [
            scope_key
            for scope_key in normalized_blocking_scope_keys
            if scope_key not in active_event_scope_keys
        ],
        "stale_reasons": list(dict.fromkeys(stale_reasons)),
    }
