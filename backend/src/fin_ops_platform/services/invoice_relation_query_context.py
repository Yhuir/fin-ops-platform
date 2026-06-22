from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_relation_distribution_mapper import (
    relation_dicts_by_row_id_from_distribution_payload,
)
from fin_ops_platform.services.workbench_relation_read_facade import FRESH_WORKBENCH_RELATION_STATUS, WorkbenchRelationReadFacade


class DistributedInvoiceRelationContext:
    """Request-scoped distributed relation index for invoice relation query pages.

    The input-invoice usage and output-invoice collection pages both need the same
    cross-fact reads: invoice rows, distributed workbench relations, bank transactions,
    and sometimes OA projection records. Keeping those indexes in one query context
    prevents per-row repository scans while preserving the existing service
    contracts.
    """

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        oa_projection: Any | None = None,
        month_hint: str | None = None,
        require_fresh_relations: bool = True,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._oa_projection = oa_projection
        self._month_hint = str(month_hint or "").strip() or None
        self._require_fresh_relations = require_fresh_relations
        self._invoices_by_scope: dict[tuple[str, str], list[Invoice]] = {}
        self._bank_transactions_by_id: dict[str, BankTransaction] | None = None
        self._distributed_relations_by_row_id: dict[str, list[dict[str, Any]]] = {}
        self._distributed_loaded_all_for_month = False
        self._oa_records_by_id: dict[str, OAApplicationRecord] = {}
        self._oa_loaded_all = False

    def list_invoices(self, *, month: str | None, invoice_type: InvoiceType) -> list[Invoice]:
        cache_key = (
            str(month).strip() if month not in (None, "") else "",
            str(invoice_type.value if isinstance(invoice_type, InvoiceType) else invoice_type),
        )
        if cache_key not in self._invoices_by_scope:
            self._invoices_by_scope[cache_key] = list(
                self._import_service.list_invoices(month=month, invoice_type=invoice_type)
            )
        return list(self._invoices_by_scope[cache_key])

    def bank_transactions_by_id(self) -> dict[str, BankTransaction]:
        if self._bank_transactions_by_id is None:
            self._bank_transactions_by_id = {
                transaction.id: transaction
                for transaction in self._import_service.list_transactions(month="all")
            }
        return self._bank_transactions_by_id

    def distributed_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        resolved_row_ids = {str(row_id).strip() for row_id in row_ids if str(row_id).strip()}
        if not resolved_row_ids:
            return []
        return self._distributed_active_relations_for_row_ids(sorted(resolved_row_ids))

    def relation_summaries_for_row(self, row_id: str) -> list[dict[str, Any]]:
        return [
            {
                "caseId": relation.get("case_id", ""),
                "relationMode": relation.get("relation_mode", ""),
                "rowIds": list(relation.get("row_ids") or []),
                "rowTypes": list(relation.get("row_types") or []),
                "amountCheck": deepcopy(relation.get("amount_check") or {}),
                "relationStatus": relation_status(relation),
                "relation_status": relation_status(relation),
                "relationSource": str(relation.get("relation_source") or ""),
            }
            for relation in self.distributed_relations_for_row_ids([row_id])
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
        for relation in self.distributed_relations_for_row_ids(row_ids):
            for row_id, row_type in self.typed_relation_rows(relation):
                if row_type == "oa" and row_id not in seen:
                    seen.add(row_id)
                    oa_ids.append(row_id)
        self.oa_records_by_id(oa_ids)

    def preload_relation_rows(self, row_ids: list[str]) -> None:
        normalized_ids = _dedupe_preserve_order(str(row_id).strip() for row_id in list(row_ids or []))
        if not normalized_ids:
            return
        self._load_distributed_relations(normalized_ids)

    def add_distributed_relations(self, relations: list[dict[str, Any]]) -> None:
        for relation in list(relations or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or relation.get("relation_id") or "").strip()
            if not case_id:
                continue
            for row_id, _row_type in self.typed_relation_rows(relation):
                if not row_id:
                    continue
                self._distributed_relations_by_row_id.setdefault(row_id, [])
                existing_case_ids = {
                    str(item.get("case_id") or item.get("relation_id") or "").strip()
                    for item in self._distributed_relations_by_row_id[row_id]
                }
                if case_id not in existing_case_ids:
                    self._distributed_relations_by_row_id[row_id].append(deepcopy(relation))

    def _distributed_active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        self._load_distributed_relations(row_ids)
        relations_by_case_id: dict[str, dict[str, Any]] = {}
        for row_id in row_ids:
            for relation in self._distributed_relations_by_row_id.get(row_id, []):
                case_id = str(relation.get("case_id") or "")
                relations_by_case_id[case_id] = relation
        return [deepcopy(relation) for relation in relations_by_case_id.values()]

    def _load_distributed_relations(self, row_ids: list[str]) -> None:
        if self._relation_facade is None:
            return
        normalized_ids = _dedupe_preserve_order(str(row_id).strip() for row_id in list(row_ids or []))
        if not normalized_ids:
            return
        if self._month_hint and self._month_hint != "all" and not self._distributed_loaded_all_for_month:
            result = self._relation_facade.list_by_month(
                self._month_hint,
                require_fresh=self._require_fresh_relations,
                reason="invoice_relation_query_context_month_read",
            )
            self._assert_fresh_distribution(result)
            self._merge_distributed_result(result)
            self._distributed_loaded_all_for_month = True
            return
        missing_ids = [
            row_id
            for row_id in normalized_ids
            if row_id not in self._distributed_relations_by_row_id
        ]
        if not missing_ids:
            return
        result = self._relation_facade.get_by_row_ids(
            missing_ids,
            require_fresh=self._require_fresh_relations,
            reason="invoice_relation_query_context_row_read",
            month_hint=self._month_hint,
        )
        self._assert_fresh_distribution(result)
        self._merge_distributed_result(result)
        for row_id in missing_ids:
            self._distributed_relations_by_row_id.setdefault(row_id, [])

    def _assert_fresh_distribution(self, result: dict[str, Any]) -> None:
        if not self._require_fresh_relations:
            return
        if str(result.get("status") or "") != FRESH_WORKBENCH_RELATION_STATUS:
            reasons = ",".join(str(item) for item in list(result.get("stale_reasons") or []))
            scope_keys = ",".join(str(item) for item in list(result.get("read_model_scope_keys") or []))
            raise RuntimeError(
                "workbench_relation_read_model_not_fresh"
                f": status={result.get('status')}, scope_keys={scope_keys}, reasons={reasons}"
            )

    def _merge_distributed_result(self, result: dict[str, Any]) -> None:
        relations_by_row_id = relation_dicts_by_row_id_from_distribution_payload(result)
        for row_id, relations in relations_by_row_id.items():
            self._distributed_relations_by_row_id.setdefault(row_id, [])
            existing_case_ids = {str(relation.get("case_id") or "") for relation in self._distributed_relations_by_row_id[row_id]}
            for group in relations:
                case_id = str(group.get("case_id") or "")
                if case_id and case_id not in existing_case_ids:
                    self._distributed_relations_by_row_id[row_id].append(group)
                    existing_case_ids.add(case_id)
        for row in list(result.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id") or "").strip()
            if row_id:
                self._distributed_relations_by_row_id.setdefault(row_id, [])

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


def relation_status(relation: dict[str, Any] | None) -> str:
    if not relation:
        return ""
    resolved = str(relation.get("relation_status") or relation.get("relationStatus") or "").strip()
    if resolved:
        return resolved
    if str(relation.get("status") or "").strip() == "active":
        return "linked"
    return ""


def relation_is_linked(relation: dict[str, Any] | None) -> bool:
    return relation_status(relation) == "linked"


def summary_relation_status(summary: dict[str, Any] | None) -> str:
    if not summary:
        return ""
    resolved = str(summary.get("relationStatus") or summary.get("relation_status") or "").strip()
    return resolved or "linked"


def summary_is_linked(summary: dict[str, Any] | None) -> bool:
    return summary_relation_status(summary) == "linked"


def _infer_row_type(row_id: str) -> str:
    if row_id.startswith("bank"):
        return "bank"
    if row_id.startswith("oa"):
        return "oa"
    return "invoice"


def _relation_from_distribution_group(group: dict[str, Any]) -> dict[str, Any]:
    payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
    row_ids = text_list(payload.get("row_ids"))
    row_types = text_list(payload.get("row_types"))
    if not row_ids:
        typed = [
            *[(row_id, "oa") for row_id in text_list(group.get("oa_row_ids"))],
            *[(row_id, "bank") for row_id in text_list(group.get("bank_transaction_ids"))],
            *[(row_id, "invoice") for row_id in text_list(group.get("input_invoice_ids"))],
            *[(row_id, "invoice") for row_id in text_list(group.get("output_invoice_ids"))],
        ]
        row_ids = [row_id for row_id, _row_type in typed]
        row_types = [row_type for _row_id, row_type in typed]
    return {
        "case_id": str(group.get("group_id") or payload.get("group_id") or ""),
        "relation_mode": str(payload.get("relation_mode") or group.get("relation_source") or ""),
        "relation_status": str(payload.get("relation_status") or group.get("relation_status") or "").strip() or "linked",
        "row_ids": row_ids,
        "row_types": row_types,
        "amount_check": deepcopy(payload.get("amount_check") if isinstance(payload.get("amount_check"), dict) else {}),
        "special_metadata": deepcopy(
            payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {}
        ),
    }


def text_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
