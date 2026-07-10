from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.invoice_read_model_audit import (
    OUTPUT_INVOICE_AUDIT_CONTRACT,
    audit_invoice_read_model,
    invoice_predicate,
)


OUTPUT_INVOICE_PREDICATE = invoice_predicate(OUTPUT_INVOICE_AUDIT_CONTRACT)


def audit_output_invoice_collection_read_model(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
) -> dict[str, Any]:
    return audit_invoice_read_model(
        connection,
        contract=OUTPUT_INVOICE_AUDIT_CONTRACT,
        tenant_id=tenant_id,
        example_limit=example_limit,
    )
