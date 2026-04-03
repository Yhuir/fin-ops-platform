from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from itertools import count
from typing import Any, Protocol

from fin_ops_platform.domain.enums import IntegrationObjectType, IntegrationSource, IntegrationSyncStatus
from fin_ops_platform.domain.models import (
    IntegrationMapping,
    IntegrationSyncIssue,
    IntegrationSyncRun,
    OADocument,
    ProjectMaster,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService, clean_string


SUPPORTED_SCOPES = (
    "all",
    "counterparties",
    "projects",
    "approval_forms",
    "payment_requests",
    "expense_claims",
)

DOCUMENT_SCOPE_TYPES = {
    "approval_forms": IntegrationObjectType.APPROVAL_FORM,
    "payment_requests": IntegrationObjectType.PAYMENT_REQUEST,
    "expense_claims": IntegrationObjectType.EXPENSE_CLAIM,
}


class OAAdapter(Protocol):
    name: str

    def fetch_counterparties(self) -> list[dict[str, Any]]: ...

    def fetch_projects(self) -> list[dict[str, Any]]: ...

    def fetch_documents(self, scope: str) -> list[dict[str, Any]]: ...


@dataclass(slots=True)
class MockOAAdapter:
    name: str = "mock_oa"

    def fetch_counterparties(self) -> list[dict[str, Any]]:
        return [
            {"external_id": "OA-CP-001", "name": "Acme Supplies", "counterparty_type": "customer_vendor"},
            {"external_id": "OA-CP-002", "name": "Delta Client", "counterparty_type": "customer"},
        ]

    def fetch_projects(self) -> list[dict[str, Any]]:
        return [
            {
                "external_id": "OA-PROJ-001",
                "project_code": "PJT-001",
                "project_name": "华东改造项目",
                "project_status": "active",
                "department_name": "交付中心",
                "owner_name": "张三",
            },
            {
                "external_id": "OA-PROJ-002",
                "project_code": "PJT-002",
                "project_name": "智能工厂项目",
                "project_status": "active",
                "department_name": "制造事业部",
                "owner_name": "李四",
            },
        ]

    def fetch_documents(self, scope: str) -> list[dict[str, Any]]:
        fixtures = {
            "approval_forms": [
                {
                    "external_id": "OA-AF-001",
                    "form_no": "SP-202603-001",
                    "title": "办公用品采购审批",
                    "applicant_name": "王敏",
                    "amount": "1200.00",
                    "counterparty_name": "Acme Supplies",
                    "project_external_id": "OA-PROJ-001",
                    "project_name": "华东改造项目",
                    "form_status": "approved",
                    "submitted_at": "2026-03-24T09:00:00+08:00",
                    "completed_at": "2026-03-24T11:00:00+08:00",
                }
            ],
            "payment_requests": [
                {
                    "external_id": "OA-PR-001",
                    "form_no": "FKSQ-202603-001",
                    "title": "供应商付款申请",
                    "applicant_name": "赵华",
                    "amount": "300.00",
                    "counterparty_name": "Acme Supplies",
                    "project_external_id": "OA-PROJ-001",
                    "project_name": "华东改造项目",
                    "form_status": "approved",
                    "submitted_at": "2026-03-25T09:30:00+08:00",
                    "completed_at": "2026-03-25T14:00:00+08:00",
                },
                {
                    "external_id": "OA-PR-002",
                    "form_no": "FKSQ-202603-002",
                    "title": "设备尾款支付",
                    "applicant_name": "陈涛",
                    "amount": "5800.00",
                    "counterparty_name": "Delta Client",
                    "project_external_id": "OA-PROJ-002",
                    "project_name": "智能工厂项目",
                    "form_status": "approved",
                    "submitted_at": "2026-03-26T10:30:00+08:00",
                    "completed_at": "2026-03-26T15:20:00+08:00",
                },
            ],
            "expense_claims": [
                {
                    "external_id": "OA-EC-001",
                    "form_no": "BX-202603-001",
                    "title": "差旅报销",
                    "applicant_name": "刘宁",
                    "amount": "860.00",
                    "counterparty_name": "",
                    "project_external_id": "OA-PROJ-002",
                    "project_name": "智能工厂项目",
                    "form_status": "approved",
                    "submitted_at": "2026-03-23T16:00:00+08:00",
                    "completed_at": "2026-03-24T10:00:00+08:00",
                }
            ],
        }
        return fixtures[scope]


class IntegrationHubService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        audit_service: AuditTrailService,
        adapter: OAAdapter | None = None,
    ) -> None:
        self._import_service = import_service
        self._audit_service = audit_service
        self._adapter = adapter or MockOAAdapter()

        self._mapping_counter = count(1)
        self._project_counter = count(1)
        self._document_counter = count(1)
        self._run_counter = count(1)
        self._issue_counter = count(1)

        self._mappings_by_id: dict[str, IntegrationMapping] = {}
        self._mapping_index: dict[tuple[IntegrationSource, IntegrationObjectType, str], str] = {}
        self._projects_by_id: dict[str, ProjectMaster] = {}
        self._project_external_index: dict[str, str] = {}
        self._documents_by_id: dict[str, OADocument] = {}
        self._document_external_index: dict[tuple[str, str], str] = {}
        self._runs_by_id: dict[str, IntegrationSyncRun] = {}

    def sync(self, *, scope: str = "all", triggered_by: str, retry_run_id: str | None = None) -> IntegrationSyncRun:
        effective_scope = scope or "all"
        if retry_run_id is not None:
            effective_scope = self.get_sync_run(retry_run_id).scope
        if effective_scope not in SUPPORTED_SCOPES:
            raise ValueError(f"Unsupported OA sync scope: {effective_scope}")

        run = IntegrationSyncRun(
            id=f"oa_sync_{next(self._run_counter):04d}",
            source_system=IntegrationSource.OA,
            scope=effective_scope,
            triggered_by=triggered_by,
            status=IntegrationSyncStatus.SUCCEEDED,
            pulled_count=0,
            success_count=0,
            failed_count=0,
            retry_of_run_id=retry_run_id,
        )

        scopes_to_sync = SUPPORTED_SCOPES[1:] if effective_scope == "all" else (effective_scope,)
        for current_scope in scopes_to_sync:
            records = self._fetch_scope(current_scope)
            run.pulled_count += len(records)
            for record in records:
                try:
                    self._sync_record(current_scope, record)
                    run.success_count += 1
                except ValueError as exc:
                    run.failed_count += 1
                    run.issues.append(
                        IntegrationSyncIssue(
                            id=f"oa_issue_{next(self._issue_counter):04d}",
                            run_id=run.id,
                            object_type=self._scope_object_type(current_scope),
                            external_id=str(record.get("external_id") or "unknown"),
                            title=clean_string(record.get("title") or record.get("name") or current_scope),
                            reason=str(exc),
                        )
                    )

        if run.failed_count and run.success_count:
            run.status = IntegrationSyncStatus.PARTIAL
        elif run.failed_count:
            run.status = IntegrationSyncStatus.FAILED
        run.finished_at = datetime.now(UTC)
        self._runs_by_id[run.id] = run

        self._audit_service.record_action(
            actor_id=triggered_by,
            action="oa_sync_completed",
            entity_type="integration_sync_run",
            entity_id=run.id,
            metadata={
                "scope": effective_scope,
                "status": run.status.value,
                "pulled_count": run.pulled_count,
                "success_count": run.success_count,
                "failed_count": run.failed_count,
                "retry_of_run_id": retry_run_id,
            },
        )
        return run

    def build_dashboard(self) -> dict[str, Any]:
        runs = self.list_sync_runs()
        return {
            "source_system": IntegrationSource.OA,
            "adapter": self._adapter.name,
            "supported_scopes": list(SUPPORTED_SCOPES),
            "summary": {
                "mapping_count": len(self._mappings_by_id),
                "project_count": len(self._projects_by_id),
                "document_count": len(self._documents_by_id),
                "run_count": len(self._runs_by_id),
                "latest_run_id": runs[0].id if runs else None,
            },
            "runs": runs,
            "mappings": self.list_mappings(),
            "projects": self.list_projects(),
            "documents": self.list_documents(),
        }

    def list_sync_runs(self) -> list[IntegrationSyncRun]:
        return sorted(self._runs_by_id.values(), key=lambda item: item.started_at, reverse=True)

    def get_sync_run(self, run_id: str) -> IntegrationSyncRun:
        return self._runs_by_id[run_id]

    def list_mappings(self, *, object_type: str | IntegrationObjectType | None = None) -> list[IntegrationMapping]:
        mappings = list(self._mappings_by_id.values())
        if object_type is not None:
            expected = IntegrationObjectType(object_type)
            mappings = [mapping for mapping in mappings if mapping.object_type == expected]
        return sorted(mappings, key=lambda item: item.last_synced_at, reverse=True)

    def list_projects(self) -> list[ProjectMaster]:
        return sorted(self._projects_by_id.values(), key=lambda item: item.project_code)

    def get_project(self, project_id: str) -> ProjectMaster:
        return self._projects_by_id[project_id]

    def find_project_by_external_id(self, external_id: str) -> ProjectMaster | None:
        project_id = self._project_external_index.get(external_id)
        return self._projects_by_id.get(project_id) if project_id is not None else None

    def list_documents(self) -> list[OADocument]:
        return sorted(self._documents_by_id.values(), key=lambda item: item.form_no)

    def find_document_by_external_id(self, external_id: str) -> OADocument | None:
        for (_, indexed_external_id), document_id in self._document_external_index.items():
            if indexed_external_id == external_id:
                return self._documents_by_id[document_id]
        return None

    def _fetch_scope(self, scope: str) -> list[dict[str, Any]]:
        if scope == "counterparties":
            return self._adapter.fetch_counterparties()
        if scope == "projects":
            return self._adapter.fetch_projects()
        return self._adapter.fetch_documents(scope)

    def _sync_record(self, scope: str, record: dict[str, Any]) -> None:
        if scope == "counterparties":
            self._sync_counterparty(record)
            return
        if scope == "projects":
            self._sync_project(record)
            return
        self._sync_document(scope, record)

    def _sync_counterparty(self, record: dict[str, Any]) -> None:
        external_id = clean_string(record.get("external_id", ""))
        name = clean_string(record.get("name", ""))
        if not external_id:
            raise ValueError("external_id is required")
        if not name:
            raise ValueError("name is required")

        counterparty = self._import_service.find_counterparty_by_name(name, create_if_missing=False)
        if counterparty is not None:
            counterparty.oa_external_id = external_id
        self._upsert_mapping(
            object_type=IntegrationObjectType.COUNTERPARTY,
            external_id=external_id,
            internal_object_type="counterparty" if counterparty else None,
            internal_object_id=counterparty.id if counterparty else None,
            display_name=name,
        )

    def _sync_project(self, record: dict[str, Any]) -> None:
        external_id = clean_string(record.get("external_id", ""))
        project_code = clean_string(record.get("project_code", ""))
        project_name = clean_string(record.get("project_name", ""))
        if not external_id:
            raise ValueError("external_id is required")
        if not project_code:
            raise ValueError("project_code is required")
        if not project_name:
            raise ValueError("project_name is required")

        existing_id = self._project_external_index.get(external_id)
        if existing_id is None:
            project = ProjectMaster(
                id=f"proj_oa_{next(self._project_counter):04d}",
                project_code=project_code,
                project_name=project_name,
                project_status=clean_string(record.get("project_status", "")) or "active",
                oa_external_id=external_id,
                department_name=clean_string(record.get("department_name", "")) or None,
                owner_name=clean_string(record.get("owner_name", "")) or None,
            )
            self._projects_by_id[project.id] = project
            self._project_external_index[external_id] = project.id
        else:
            project = self._projects_by_id[existing_id]
            project.project_code = project_code
            project.project_name = project_name
            project.project_status = clean_string(record.get("project_status", "")) or project.project_status
            project.department_name = clean_string(record.get("department_name", "")) or project.department_name
            project.owner_name = clean_string(record.get("owner_name", "")) or project.owner_name

        self._upsert_mapping(
            object_type=IntegrationObjectType.PROJECT,
            external_id=external_id,
            internal_object_type="project",
            internal_object_id=project.id,
            display_name=project.project_name,
        )

    def _sync_document(self, scope: str, record: dict[str, Any]) -> None:
        object_type = self._scope_object_type(scope)
        external_id = clean_string(record.get("external_id", ""))
        form_no = clean_string(record.get("form_no", ""))
        title = clean_string(record.get("title", ""))
        applicant_name = clean_string(record.get("applicant_name", ""))
        if not external_id:
            raise ValueError("external_id is required")
        if not form_no:
            raise ValueError("form_no is required")
        if not title:
            raise ValueError("title is required")
        if not applicant_name:
            raise ValueError("applicant_name is required")

        existing_id = self._document_external_index.get((scope, external_id))
        amount = self._parse_amount(record.get("amount"))
        if existing_id is None:
            document = OADocument(
                id=f"oa_doc_{next(self._document_counter):04d}",
                document_type=object_type.value,
                oa_external_id=external_id,
                form_no=form_no,
                title=title,
                applicant_name=applicant_name,
                amount=amount,
                counterparty_name=clean_string(record.get("counterparty_name", "")) or None,
                project_external_id=clean_string(record.get("project_external_id", "")) or None,
                project_name=clean_string(record.get("project_name", "")) or None,
                form_status=clean_string(record.get("form_status", "")) or "approved",
                submitted_at=clean_string(record.get("submitted_at", "")) or None,
                completed_at=clean_string(record.get("completed_at", "")) or None,
                source_payload=dict(record),
            )
            self._documents_by_id[document.id] = document
            self._document_external_index[(scope, external_id)] = document.id
        else:
            document = self._documents_by_id[existing_id]
            document.form_no = form_no
            document.title = title
            document.applicant_name = applicant_name
            document.amount = amount
            document.counterparty_name = clean_string(record.get("counterparty_name", "")) or None
            document.project_external_id = clean_string(record.get("project_external_id", "")) or None
            document.project_name = clean_string(record.get("project_name", "")) or None
            document.form_status = clean_string(record.get("form_status", "")) or document.form_status
            document.submitted_at = clean_string(record.get("submitted_at", "")) or None
            document.completed_at = clean_string(record.get("completed_at", "")) or None
            document.source_payload = dict(record)

        self._upsert_mapping(
            object_type=object_type,
            external_id=external_id,
            internal_object_type="oa_document",
            internal_object_id=document.id,
            display_name=document.title,
        )

    def _upsert_mapping(
        self,
        *,
        object_type: IntegrationObjectType,
        external_id: str,
        internal_object_type: str | None,
        internal_object_id: str | None,
        display_name: str | None,
    ) -> None:
        key = (IntegrationSource.OA, object_type, external_id)
        existing_id = self._mapping_index.get(key)
        if existing_id is None:
            mapping = IntegrationMapping(
                id=f"oa_map_{next(self._mapping_counter):04d}",
                source_system=IntegrationSource.OA,
                object_type=object_type,
                external_id=external_id,
                internal_object_type=internal_object_type,
                internal_object_id=internal_object_id,
                display_name=display_name,
            )
            self._mappings_by_id[mapping.id] = mapping
            self._mapping_index[key] = mapping.id
            return

        mapping = self._mappings_by_id[existing_id]
        mapping.internal_object_type = internal_object_type
        mapping.internal_object_id = internal_object_id
        mapping.display_name = display_name
        mapping.last_synced_at = datetime.now(UTC)

    @staticmethod
    def _scope_object_type(scope: str) -> IntegrationObjectType:
        if scope == "counterparties":
            return IntegrationObjectType.COUNTERPARTY
        if scope == "projects":
            return IntegrationObjectType.PROJECT
        return DOCUMENT_SCOPE_TYPES[scope]

    @staticmethod
    def _parse_amount(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", ""))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount is invalid") from exc
