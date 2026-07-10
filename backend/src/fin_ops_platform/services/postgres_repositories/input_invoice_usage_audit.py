from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.invoice_read_model_audit import (
    INPUT_INVOICE_AUDIT_CONTRACT,
    audit_invoice_read_model,
    invoice_predicate,
)


INPUT_INVOICE_PREDICATE = invoice_predicate(INPUT_INVOICE_AUDIT_CONTRACT)


def audit_input_invoice_usage_read_model(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
) -> dict[str, Any]:
    return audit_invoice_read_model(
        connection,
        contract=INPUT_INVOICE_AUDIT_CONTRACT,
        tenant_id=tenant_id,
        example_limit=example_limit,
    )
