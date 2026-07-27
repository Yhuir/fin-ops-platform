from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.postgres_repositories.bank_transaction_import_page_audit import (
    audit_bank_transaction_import_page,
)
from fin_ops_platform.services.postgres_repositories.app_health_system_audit import (
    audit_app_health_system_snapshot,
)
from fin_ops_platform.services.postgres_repositories.audit_report import AuditSnapshot, read_only_audit_snapshot
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import audit_cost_statistics_page
from fin_ops_platform.services.postgres_repositories.invoice_import_page_audit import audit_invoice_import_page
from fin_ops_platform.services.postgres_repositories.etc_tickets_page_audit import audit_etc_tickets_page
from fin_ops_platform.services.postgres_repositories.etc_import_page_audit import audit_etc_import_page
from fin_ops_platform.services.postgres_repositories.page_business_audit import audit_page_business_read_model
from fin_ops_platform.services.postgres_repositories.settings_page_audit import audit_settings_page
from fin_ops_platform.services.postgres_repositories.tax_offset_page_audit import audit_tax_offset_page
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import audit_workbench_relation_display
from fin_ops_platform.services.page_audit_registry import PAGE_AUDIT_REGISTRY, PageAuditRegistration, page_audit_registration


class PostgresOperationsAuditRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def audit_page(
        self,
        *,
        page_key: str,
        tenant_id: str,
        sample_limit: int,
    ) -> dict[str, Any]:
        registration = page_audit_registration(page_key)
        if registration.executor == "system":
            raise ValueError("App Health system audit requires the explicit system orchestration boundary.")
        return self._audit_registration(
            registration,
            tenant_id=tenant_id,
            sample_limit=sample_limit,
        )

    def audit_system(
        self,
        *,
        tenant_id: str,
        sample_limit: int,
        dashboard_payload_builder: Callable[[Any], dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_tenant = str(tenant_id or "default").strip() or "default"
        limit = max(int(sample_limit or 50), 1)
        registrations = tuple(PAGE_AUDIT_REGISTRY.values())
        if any(registration.availability != "ready" for registration in registrations):
            unavailable = [
                registration.page_key for registration in registrations if registration.availability != "ready"
            ]
            raise ValueError(f"System audit requires every registered page proof to be ready: {unavailable}")
        with read_only_audit_snapshot(self._connection) as snapshot:
            identity_row = snapshot.connection.fetch_one(
                "select pg_current_snapshot()::text as snapshot_identity, transaction_timestamp() as snapshot_generated_at"
            ) or {}
            snapshot_identity = str(identity_row.get("snapshot_identity") or "").strip()
            if snapshot.database_snapshot and not snapshot_identity:
                raise ValueError("PostgreSQL system audit snapshot identity is unavailable.")
            snapshot_generated_at = _isoformat(identity_row.get("snapshot_generated_at"))
            page_reports = [
                self._audit_registration(
                    registration,
                    tenant_id=normalized_tenant,
                    sample_limit=limit,
                    audit_snapshot=snapshot,
                    system_snapshot_identity=snapshot_identity,
                )
                for registration in registrations
                if registration.executor != "system"
            ]
            dashboard_payload = dashboard_payload_builder(snapshot.connection)
            payload = audit_app_health_system_snapshot(
                snapshot.connection,
                tenant_id=normalized_tenant,
                sample_limit=limit,
                snapshot_identity=snapshot_identity,
                snapshot_generated_at=snapshot_generated_at,
                snapshot_consistency=snapshot.consistency,
                database_snapshot=snapshot.database_snapshot,
                registrations=registrations,
                page_reports=page_reports,
                dashboard_payload=dashboard_payload,
            )
            system_registration = page_audit_registration("app-health-operations")
            return self._registered_payload(payload, system_registration, system_snapshot_identity=snapshot_identity)

    def _audit_registration(
        self,
        registration: PageAuditRegistration,
        *,
        tenant_id: str,
        sample_limit: int,
        audit_snapshot: AuditSnapshot | None = None,
        system_snapshot_identity: str = "",
    ) -> dict[str, Any]:
        if registration.executor == "workbench":
            payload = audit_workbench_relation_display(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "cost_statistics":
            payload = audit_cost_statistics_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "page_business":
            payload = audit_page_business_read_model(
                self._connection,
                domain_key=str(registration.executor_domain_key),
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "tax_offset":
            payload = audit_tax_offset_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "etc_tickets":
            payload = audit_etc_tickets_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "etc_import":
            payload = audit_etc_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "settings":
            payload = audit_settings_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "bank_transaction_import":
            payload = audit_bank_transaction_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        elif registration.executor == "invoice_import":
            payload = audit_invoice_import_page(
                self._connection,
                tenant_id=tenant_id,
                example_limit=sample_limit,
                audit_snapshot=audit_snapshot,
            )
        else:
            raise ValueError(f"Page audit proof is unavailable for {registration.page_key}.")
        return self._registered_payload(
            payload,
            registration,
            system_snapshot_identity=system_snapshot_identity,
        )

    @staticmethod
    def _registered_payload(
        payload: dict[str, Any],
        registration: PageAuditRegistration,
        *,
        system_snapshot_identity: str = "",
    ) -> dict[str, Any]:
        audit_contract = dict(payload.get("audit_contract") or {})
        audit_contract.update(
            {
                "contract_revision": registration.contract_revision,
                "proof_availability": registration.availability,
                "registered_read_model_keys": list(registration.read_model_keys),
                "relation_proof_required": registration.relation_proof_required,
                **(
                    {"system_snapshot_identity": system_snapshot_identity}
                    if system_snapshot_identity
                    else {}
                ),
            }
        )
        return {
            **payload,
            "page_key": registration.page_key,
            "label": registration.label,
            "audit_contract": audit_contract,
        }


def _isoformat(value: Any) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    isoformat = getattr(value, "isoformat", None)
    return str(isoformat() if callable(isoformat) else value)
