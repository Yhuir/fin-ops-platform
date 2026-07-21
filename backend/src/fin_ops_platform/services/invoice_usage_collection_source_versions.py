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


def input_invoice_usage_source_versions(payment_status_rules_version: int | str | None = None) -> dict[str, object]:
    normalized_rules_version = payment_status_rules_version if payment_status_rules_version not in (None, "") else 1
    return {
        "input_invoice_usage_source_version": INPUT_INVOICE_USAGE_SOURCE_VERSION,
        "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
        "input_invoice_usage_payment_rules_version": normalized_rules_version,
        "input_invoice_usage_statistics_schema_version": 1,
        "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
    }


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
