from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import count
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import (
    BankTransaction,
    FollowUpLedger,
    Invoice,
    ProjectAssignmentRecord,
    ProjectMaster,
    ProjectSummary,
    ReconciliationCase,
)
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


ZERO = Decimal("0.00")
ASSIGNABLE_TYPES = {"invoice", "bank_transaction", "reconciliation_case", "follow_up_ledger"}


class ProjectCostingService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        reconciliation_service: ManualReconciliationService,
        ledger_service: LedgerReminderService,
        integration_service: IntegrationHubService,
        audit_service: AuditTrailService,
    ) -> None:
        self._import_service = import_service
        self._reconciliation_service = reconciliation_service
        self._ledger_service = ledger_service
        self._integration_service = integration_service
        self._audit_service = audit_service

        self._manual_project_sequence = count(1)
        self._assignment_sequence = count(1)
        self._manual_projects: dict[str, ProjectMaster] = {}
        self._placeholder_projects: dict[str, ProjectMaster] = {}
        self._assignments_by_id: dict[str, ProjectAssignmentRecord] = {}
        self._assignment_index: dict[tuple[str, str], str] = {}

    def create_project(
        self,
        *,
        actor_id: str,
        project_code: str,
        project_name: str,
        project_status: str = "active",
        department_name: str | None = None,
        owner_name: str | None = None,
    ) -> ProjectMaster:
        if not project_code.strip():
            raise ValueError("project_code is required")
        if not project_name.strip():
            raise ValueError("project_name is required")

        project = ProjectMaster(
            id=f"proj_manual_{next(self._manual_project_sequence):04d}",
            project_code=project_code.strip(),
            project_name=project_name.strip(),
            project_status=project_status.strip() or "active",
            department_name=department_name.strip() if department_name else None,
            owner_name=owner_name.strip() if owner_name else None,
        )
        self._manual_projects[project.id] = project
        self._audit_service.record_action(
            actor_id=actor_id,
            action="project_master_created",
            entity_type="project_master",
            entity_id=project.id,
            metadata={"project_code": project.project_code, "project_name": project.project_name},
        )
        return project

    def list_projects(self) -> list[ProjectMaster]:
        self._ensure_placeholder_projects()
        manual_projects = list(reversed(list(self._manual_projects.values())))
        integration_projects = self._integration_service.list_projects()
        placeholder_projects = [
            project
            for project in self._placeholder_projects.values()
            if project.id not in {item.id for item in manual_projects}
            and project.id not in {item.id for item in integration_projects}
        ]
        return [*manual_projects, *integration_projects, *sorted(placeholder_projects, key=lambda item: item.project_code)]

    def get_project(self, project_id: str) -> ProjectMaster:
        self._ensure_placeholder_projects()
        if project_id in self._manual_projects:
            return self._manual_projects[project_id]
        try:
            return self._integration_service.get_project(project_id)
        except KeyError:
            pass
        return self._placeholder_projects[project_id]

    def assign_project(
        self,
        *,
        actor_id: str,
        object_type: str,
        object_id: str,
        project_id: str,
        note: str | None = None,
    ) -> ProjectAssignmentRecord:
        canonical_type = self._normalize_object_type(object_type)
        if canonical_type not in ASSIGNABLE_TYPES:
            raise ValueError(f"Unsupported object_type: {object_type}")
        project = self.get_project(project_id)
        target = self._get_object(canonical_type, object_id)
        before_project_id = getattr(target, "project_id", None)
        self._set_object_project(target, project.id)

        assignment = ProjectAssignmentRecord(
            id=f"project_assign_{next(self._assignment_sequence):04d}",
            object_type=canonical_type,
            object_id=object_id,
            project_id=project.id,
            source="manual",
            assigned_by=actor_id,
            note=note,
        )
        self._assignments_by_id[assignment.id] = assignment
        self._assignment_index[(canonical_type, object_id)] = assignment.id

        if canonical_type == "reconciliation_case":
            for ledger in self._ledger_service.list_ledgers(view="all"):
                if ledger.source_case_id == object_id and ledger.project_id is None:
                    ledger.project_id = project.id

        self._audit_service.record_action(
            actor_id=actor_id,
            action="project_assignment_recorded",
            entity_type=canonical_type,
            entity_id=object_id,
            metadata={
                "before_project_id": before_project_id,
                "after_project_id": project.id,
                "project_code": project.project_code,
                "note": note,
            },
        )
        return assignment

    def resolve_project_for_object(self, object_type: str, object_id: str) -> ProjectMaster | None:
        canonical_type = self._normalize_object_type(object_type)
        assignment = self._latest_assignment(canonical_type, object_id)
        if assignment is not None:
            return self.get_project(assignment.project_id)

        if canonical_type == "invoice":
            invoice = self._import_service.get_invoice(object_id)
            return self._resolve_invoice_project(invoice)
        if canonical_type == "bank_transaction":
            transaction = self._import_service.get_transaction(object_id)
            return self._project_from_id(transaction.project_id)
        if canonical_type == "reconciliation_case":
            case = self._reconciliation_service.get_case(object_id)
            return self._resolve_case_project(case)
        if canonical_type == "follow_up_ledger":
            ledger = self._ledger_service.get_ledger(object_id)
            return self._resolve_ledger_project(ledger)
        return None

    def build_project_hub(self) -> dict[str, object]:
        summaries = self.list_project_summaries()
        return {
            "projects": self.list_projects(),
            "summaries": summaries,
            "totals": {
                "income_amount": sum((item.income_amount for item in summaries), start=ZERO),
                "expense_amount": sum((item.expense_amount for item in summaries), start=ZERO),
                "reconciled_amount": sum((item.reconciled_amount for item in summaries), start=ZERO),
                "open_ledger_amount": sum((item.open_ledger_amount for item in summaries), start=ZERO),
            },
            "assignable_objects": self._build_assignable_objects(),
        }

    def list_project_summaries(self) -> list[ProjectSummary]:
        summaries: dict[str, ProjectSummary] = {}
        for project in self.list_projects():
            summaries[project.id] = ProjectSummary(
                project_id=project.id,
                project_code=project.project_code,
                project_name=project.project_name,
            )

        for invoice in self._import_service.list_invoices():
            project = self._resolve_invoice_project(invoice)
            if project is None:
                continue
            summary = summaries[project.id]
            summary.invoice_count += 1
            if invoice.invoice_type == InvoiceType.OUTPUT:
                summary.income_amount += invoice.amount
            else:
                summary.expense_amount += invoice.amount

        for transaction in self._import_service.list_transactions():
            project = self.resolve_project_for_object("bank_transaction", transaction.id)
            if project is None:
                continue
            summaries[project.id].transaction_count += 1

        for case in self._reconciliation_service.list_cases():
            project = self._resolve_case_project(case)
            if project is None:
                continue
            summary = summaries[project.id]
            summary.case_count += 1
            summary.reconciled_amount += case.total_amount

        for ledger in self._ledger_service.list_ledgers(view="all"):
            project = self._resolve_ledger_project(ledger)
            if project is None:
                continue
            summary = summaries[project.id]
            summary.ledger_count += 1
            summary.open_ledger_amount += ledger.open_amount

        return [summary for summary in summaries.values() if self._summary_has_data(summary) or summary.project_id in self._manual_projects]

    def get_project_detail(self, project_id: str) -> dict[str, object]:
        project = self.get_project(project_id)
        summary = next(
            (item for item in self.list_project_summaries() if item.project_id == project_id),
            ProjectSummary(project_id=project.id, project_code=project.project_code, project_name=project.project_name),
        )
        assignments = [
            assignment
            for assignment in sorted(self._assignments_by_id.values(), key=lambda item: item.created_at, reverse=True)
            if assignment.project_id == project_id
        ]
        related_objects = [
            item for item in self._build_assignable_objects() if item["effective_project_id"] == project_id
        ]
        return {
            "project": project,
            "summary": summary,
            "assignments": assignments,
            "objects": related_objects,
        }

    def _resolve_invoice_project(self, invoice: Invoice) -> ProjectMaster | None:
        if invoice.oa_form_id:
            document = self._integration_service.find_document_by_external_id(invoice.oa_form_id)
            if document is not None and document.project_external_id:
                project = self._integration_service.find_project_by_external_id(document.project_external_id)
                if project is not None:
                    return project
        return self._project_from_id(invoice.project_id)

    def _resolve_case_project(self, case: ReconciliationCase) -> ProjectMaster | None:
        oa_ids = [case.approval_form_id, *case.related_oa_ids]
        for external_id in filter(None, oa_ids):
            document = self._integration_service.find_document_by_external_id(str(external_id))
            if document is not None and document.project_external_id:
                project = self._integration_service.find_project_by_external_id(document.project_external_id)
                if project is not None:
                    return project
        if case.project_id:
            return self._project_from_id(case.project_id)
        related_project_ids = {
            project.id
            for line in case.lines
            for project in [self.resolve_project_for_object(line.object_type, line.object_id)]
            if project is not None
        }
        if len(related_project_ids) == 1:
            return self.get_project(next(iter(related_project_ids)))
        return None

    def _resolve_ledger_project(self, ledger: FollowUpLedger) -> ProjectMaster | None:
        if ledger.project_id:
            return self._project_from_id(ledger.project_id)
        if ledger.source_case_id:
            return self.resolve_project_for_object("reconciliation_case", ledger.source_case_id)
        if ledger.source_object_type == "invoice":
            return self.resolve_project_for_object("invoice", ledger.source_object_id)
        return None

    def _project_from_id(self, project_id: str | None) -> ProjectMaster | None:
        if not project_id:
            return None
        try:
            return self.get_project(project_id)
        except KeyError:
            self._placeholder_projects[project_id] = ProjectMaster(
                id=project_id,
                project_code=project_id.upper(),
                project_name=f"项目 {project_id}",
                project_status="active",
            )
            return self._placeholder_projects[project_id]

    def _latest_assignment(self, object_type: str, object_id: str) -> ProjectAssignmentRecord | None:
        assignment_id = self._assignment_index.get((object_type, object_id))
        return self._assignments_by_id.get(assignment_id) if assignment_id is not None else None

    def _ensure_placeholder_projects(self) -> None:
        candidate_ids = set()
        candidate_ids.update(
            invoice.project_id for invoice in self._import_service.list_invoices() if invoice.project_id
        )
        candidate_ids.update(
            transaction.project_id for transaction in self._import_service.list_transactions() if transaction.project_id
        )
        candidate_ids.update(
            case.project_id for case in self._reconciliation_service.list_cases() if case.project_id
        )
        candidate_ids.update(
            ledger.project_id for ledger in self._ledger_service.list_ledgers(view="all") if ledger.project_id
        )
        candidate_ids.update(assignment.project_id for assignment in self._assignments_by_id.values())
        for project_id in candidate_ids:
            if project_id in self._manual_projects or project_id in self._placeholder_projects:
                continue
            try:
                self._integration_service.get_project(project_id)
                continue
            except KeyError:
                pass
            self._placeholder_projects[project_id] = ProjectMaster(
                id=project_id,
                project_code=project_id.upper(),
                project_name=f"项目 {project_id}",
                project_status="active",
            )

    def _build_assignable_objects(self) -> list[dict[str, Any]]:
        objects: list[dict[str, Any]] = []
        for invoice in self._import_service.list_invoices():
            effective_project = self._resolve_invoice_project(invoice)
            objects.append(
                {
                    "object_type": "invoice",
                    "object_id": invoice.id,
                    "title": invoice.invoice_no,
                    "counterparty": invoice.counterparty.name,
                    "amount": invoice.amount,
                    "status": invoice.status.value,
                    "current_project_id": invoice.project_id,
                    "effective_project_id": effective_project.id if effective_project else None,
                }
            )
        for transaction in self._import_service.list_transactions():
            effective_project = self.resolve_project_for_object("bank_transaction", transaction.id)
            objects.append(
                {
                    "object_type": "bank_transaction",
                    "object_id": transaction.id,
                    "title": transaction.bank_serial_no or transaction.account_no,
                    "counterparty": transaction.counterparty_name_raw,
                    "amount": transaction.amount,
                    "status": transaction.status.value,
                    "current_project_id": transaction.project_id,
                    "effective_project_id": effective_project.id if effective_project else None,
                }
            )
        for case in self._reconciliation_service.list_cases():
            effective_project = self._resolve_case_project(case)
            objects.append(
                {
                    "object_type": "reconciliation_case",
                    "object_id": case.id,
                    "title": case.id,
                    "counterparty": case.counterparty_id,
                    "amount": case.total_amount,
                    "status": case.status.value,
                    "current_project_id": case.project_id,
                    "effective_project_id": effective_project.id if effective_project else None,
                }
            )
        for ledger in self._ledger_service.list_ledgers(view="all"):
            effective_project = self._resolve_ledger_project(ledger)
            objects.append(
                {
                    "object_type": "follow_up_ledger",
                    "object_id": ledger.id,
                    "title": ledger.id,
                    "counterparty": ledger.counterparty_id,
                    "amount": ledger.open_amount,
                    "status": ledger.status.value,
                    "current_project_id": ledger.project_id,
                    "effective_project_id": effective_project.id if effective_project else None,
                }
            )
        return objects

    @staticmethod
    def _summary_has_data(summary: ProjectSummary) -> bool:
        return any(
            [
                summary.income_amount != ZERO,
                summary.expense_amount != ZERO,
                summary.reconciled_amount != ZERO,
                summary.open_ledger_amount != ZERO,
                summary.invoice_count,
                summary.transaction_count,
                summary.case_count,
                summary.ledger_count,
            ]
        )

    @staticmethod
    def _normalize_object_type(object_type: str) -> str:
        mapping = {
            "invoice": "invoice",
            "bank_transaction": "bank_transaction",
            "bank_txn": "bank_transaction",
            "reconciliation_case": "reconciliation_case",
            "case": "reconciliation_case",
            "follow_up_ledger": "follow_up_ledger",
            "ledger": "follow_up_ledger",
        }
        canonical = mapping.get(object_type)
        if canonical is None:
            raise ValueError(f"Unsupported object_type: {object_type}")
        return canonical

    def _get_object(self, object_type: str, object_id: str) -> Invoice | BankTransaction | ReconciliationCase | FollowUpLedger:
        if object_type == "invoice":
            return self._import_service.get_invoice(object_id)
        if object_type == "bank_transaction":
            return self._import_service.get_transaction(object_id)
        if object_type == "reconciliation_case":
            return self._reconciliation_service.get_case(object_id)
        return self._ledger_service.get_ledger(object_id)

    @staticmethod
    def _set_object_project(
        target: Invoice | BankTransaction | ReconciliationCase | FollowUpLedger,
        project_id: str,
    ) -> None:
        target.project_id = project_id
