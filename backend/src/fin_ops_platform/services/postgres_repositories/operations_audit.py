from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.input_invoice_usage_audit import (
    audit_input_invoice_usage_read_model,
)
from fin_ops_platform.services.postgres_repositories.output_invoice_collection_audit import (
    audit_output_invoice_collection_read_model,
)
from fin_ops_platform.services.postgres_repositories.page_business_audit import audit_page_business_read_model


class PostgresOperationsAuditRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def audit_input_invoice_usage(self, *, tenant_id: str, sample_limit: int) -> dict[str, Any]:
        return audit_input_invoice_usage_read_model(
            self._connection,
            tenant_id=tenant_id,
            example_limit=sample_limit,
        )

    def audit_output_invoice_collection(self, *, tenant_id: str, sample_limit: int) -> dict[str, Any]:
        return audit_output_invoice_collection_read_model(
            self._connection,
            tenant_id=tenant_id,
            example_limit=sample_limit,
        )

    def audit_page_business(
        self,
        *,
        domain_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]:
        return audit_page_business_read_model(
            self._connection,
            domain_key=domain_key,
            tenant_id=tenant_id,
            example_limit=sample_limit,
        )
