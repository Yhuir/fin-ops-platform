from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class InvoiceRelationQueryContext:
    """Request-scoped fact index for invoice relation query pages.

    The input-invoice usage and output-invoice collection pages both need the same
    cross-fact reads: invoice rows, active workbench relations, bank transactions,
    and sometimes OA projection records. Keeping those indexes in one query context
    prevents per-row repository scans while preserving the existing service
    contracts.
    """

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        pair_relation_service: WorkbenchPairRelationService,
        oa_projection: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._pair_relation_service = pair_relation_service
        self._oa_projection = oa_projection
        self._bank_transactions_by_id: dict[str, BankTransaction] | None = None
        self._active_relations_by_row_id: dict[str, list[dict[str, Any]]] | None = None
        self._oa_records_by_id: dict[str, OAApplicationRecord] = {}
        self._oa_loaded_all = False

    def list_invoices(self, *, month: str | None, invoice_type: InvoiceType) -> list[Invoice]:
        return self._import_service.list_invoices(month=month, invoice_type=invoice_type)

    def bank_transactions_by_id(self) -> dict[str, BankTransaction]:
        if self._bank_transactions_by_id is None:
            self._bank_transactions_by_id = {
                transaction.id: transaction
                for transaction in self._import_service.list_transactions(month="all")
            }
        return self._bank_transactions_by_id

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        resolved_row_ids = {str(row_id).strip() for row_id in row_ids if str(row_id).strip()}
        if not resolved_row_ids:
            return []
        if self._active_relations_by_row_id is None:
            self._active_relations_by_row_id = self._build_active_relation_index()
        relations_by_case_id: dict[str, dict[str, Any]] = {}
        for row_id in resolved_row_ids:
            for relation in self._active_relations_by_row_id.get(row_id, []):
                case_id = str(relation.get("case_id") or "")
                relations_by_case_id[case_id] = relation
        return [deepcopy(relation) for relation in relations_by_case_id.values()]

    def relation_summaries_for_row(self, row_id: str) -> list[dict[str, Any]]:
        return [
            {
                "caseId": relation.get("case_id", ""),
                "relationMode": relation.get("relation_mode", ""),
                "rowIds": list(relation.get("row_ids") or []),
                "rowTypes": list(relation.get("row_types") or []),
                "amountCheck": deepcopy(relation.get("amount_check") or {}),
            }
            for relation in self.active_relations_for_row_ids([row_id])
        ]

    def oa_records_by_id(self, oa_ids: list[str]) -> dict[str, OAApplicationRecord]:
        normalized_ids = [str(oa_id).strip() for oa_id in oa_ids if str(oa_id).strip()]
        if not normalized_ids or self._oa_projection is None:
            return {}
        missing_ids = [oa_id for oa_id in normalized_ids if oa_id not in self._oa_records_by_id]
        if missing_ids:
            self._load_oa_records(missing_ids)
        return {
            oa_id: self._oa_records_by_id[oa_id]
            for oa_id in normalized_ids
            if oa_id in self._oa_records_by_id
        }

    def preload_oa_records_from_relations(self, row_ids: list[str]) -> None:
        oa_ids: list[str] = []
        seen: set[str] = set()
        for relation in self.active_relations_for_row_ids(row_ids):
            for row_id, row_type in self.typed_relation_rows(relation):
                if row_type == "oa" and row_id not in seen:
                    seen.add(row_id)
                    oa_ids.append(row_id)
        self.oa_records_by_id(oa_ids)

    def _build_active_relation_index(self) -> dict[str, list[dict[str, Any]]]:
        list_active = getattr(self._pair_relation_service, "list_active_relations", None)
        if not callable(list_active):
            return {}
        relations_by_row_id: dict[str, list[dict[str, Any]]] = {}
        for relation in list(list_active() or []):
            if not isinstance(relation, dict):
                continue
            for row_id in list(relation.get("row_ids") or []):
                normalized_row_id = str(row_id).strip()
                if normalized_row_id:
                    relations_by_row_id.setdefault(normalized_row_id, []).append(relation)
        return relations_by_row_id

    def _load_oa_records(self, oa_ids: list[str]) -> None:
        list_by_ids = getattr(self._oa_projection, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            records = list_by_ids(oa_ids)
        elif not self._oa_loaded_all:
            list_all = getattr(self._oa_projection, "list_all_application_records", None)
            records = list_all() if callable(list_all) else []
            self._oa_loaded_all = True
        else:
            records = []
        for record in records:
            if isinstance(record, OAApplicationRecord):
                self._oa_records_by_id[record.id] = record

    @staticmethod
    def typed_relation_rows(relation: dict[str, Any]) -> list[tuple[str, str]]:
        row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
        typed = []
        for index, row_id in enumerate(row_ids):
            row_type = row_types[index] if index < len(row_types) else _infer_row_type(row_id)
            typed.append((row_id, row_type))
        return typed


def _infer_row_type(row_id: str) -> str:
    if row_id.startswith("bank"):
        return "bank"
    if row_id.startswith("oa"):
        return "oa"
    return "invoice"
