from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from fin_ops_platform.services.page_audit_registry import page_audit_registration


class OperationsAuditRepository(Protocol):
    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]: ...

    def audit_system(
        self,
        *,
        tenant_id: str,
        sample_limit: int,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]: ...


class PageAuditUnavailableError(ValueError):
    pass


class OperationsAuditService:
    def __init__(
        self,
        repository: OperationsAuditRepository,
        *,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self._repository = repository
        self._dashboard_payload_builder = dashboard_payload_builder

    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int = 50,
    ) -> dict[str, Any]:
        registration = page_audit_registration(page_key)
        if registration.availability != "ready":
            raise PageAuditUnavailableError(
                f"Page audit proof is unavailable for {registration.page_key}: {registration.unavailable_reason}"
            )
        if registration.executor == "system":
            if self._dashboard_payload_builder is None:
                raise PageAuditUnavailableError("App Health system audit dashboard projection is unavailable.")
            return self._repository.audit_system(
                tenant_id=tenant_id,
                sample_limit=sample_limit,
                dashboard_payload_builder=self._dashboard_payload_builder,
            )
        return self._repository.audit_page(
            page_key=registration.page_key,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )
