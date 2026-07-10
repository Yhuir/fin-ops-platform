from __future__ import annotations

from typing import Any, Protocol


class OperationsAuditRepository(Protocol):
    def audit_input_invoice_usage(self, *, tenant_id: str, sample_limit: int) -> dict[str, Any]: ...

    def audit_output_invoice_collection(self, *, tenant_id: str, sample_limit: int) -> dict[str, Any]: ...

    def audit_page_business(
        self,
        *,
        domain_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]: ...


class OperationsAuditService:
    def __init__(self, repository: OperationsAuditRepository) -> None:
        self._repository = repository

    def audit_input_invoice_usage(self, *, tenant_id: str, sample_limit: int = 50) -> dict[str, Any]:
        return self._repository.audit_input_invoice_usage(
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    def audit_output_invoice_collection(self, *, tenant_id: str, sample_limit: int = 50) -> dict[str, Any]:
        return self._repository.audit_output_invoice_collection(
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    def audit_page_business(
        self,
        *,
        domain_key: str,
        tenant_id: str,
        sample_limit: int = 50,
    ) -> dict[str, Any]:
        return self._repository.audit_page_business(
            domain_key=domain_key,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )
