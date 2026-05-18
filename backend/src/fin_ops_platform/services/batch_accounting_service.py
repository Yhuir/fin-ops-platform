from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from typing import Any, Callable, Iterable
from uuid import uuid4

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


BATCH_ACCOUNTING_SOURCE = "batch_accounting"
BATCH_ACCOUNTING_COUNTERPARTY_NAME = "批量账务集中处理"


class BatchAccountingError(ValueError):
    def __init__(self, code: str, message: str | None = None, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.payload = payload or {}


@dataclass
class _WorkbenchContext:
    rows_by_id: dict[str, dict[str, Any]]
    groups: list[dict[str, Any]]
    bank_rows: list[dict[str, Any]]
    open_oa_rows: list[dict[str, Any]]
    invoice_ids_by_oa_id: dict[str, list[str]]
    eligible_bank_rows: list[dict[str, Any]]
    eligible_oa_rows: list[dict[str, Any]]


class BatchAccountingService:
    def __init__(
        self,
        *,
        grouped_workbench_loader: Callable[[str], dict[str, Any]],
        pair_relation_service: WorkbenchPairRelationService,
        case_id_provider: Callable[[], str] | None = None,
    ) -> None:
        self._grouped_workbench_loader = grouped_workbench_loader
        self._pair_relation_service = pair_relation_service
        self._case_id_provider = case_id_provider or (lambda: f"CASE-BATCH-{uuid4().hex[:16].upper()}")

    def build_payload(self, *, year: str, bucket: str) -> dict[str, Any]:
        resolved_year = self._validate_year(year)
        if bucket not in {"unsubmitted", "submitted"}:
            raise BatchAccountingError("invalid_batch_accounting_bucket", "bucket must be unsubmitted or submitted.")
        context = self._build_context(resolved_year)
        submitted_relations = self._submitted_relations(resolved_year, context)
        if bucket == "submitted":
            bank_rows, relations_by_bank_row_id = self._submitted_payload(submitted_relations, context)
            oa_rows: list[dict[str, Any]] = []
        else:
            bank_rows = [self._bank_row_payload(row) for row in context.eligible_bank_rows]
            oa_rows = [self._oa_row_payload(row, context.invoice_ids_by_oa_id.get(str(row.get("id")), [])) for row in context.eligible_oa_rows]
            relations_by_bank_row_id = {}
        return {
            "summary": {
                "unsubmitted_count": len(context.eligible_bank_rows),
                "submitted_count": len(submitted_relations),
            },
            "bank_rows": bank_rows,
            "oa_rows": oa_rows,
            "relations_by_bank_row_id": relations_by_bank_row_id,
        }

    def submit(
        self,
        *,
        year: str,
        bank_row_id: str,
        oa_row_ids: list[str],
        actor: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        resolved_year = self._validate_year(year)
        normalized_bank_row_id = self._required_id(bank_row_id, "bank_row_id")
        normalized_oa_row_ids = self._normalize_ids(oa_row_ids)
        context = self._build_context(resolved_year)
        bank_row = context.rows_by_id.get(normalized_bank_row_id)
        if not isinstance(bank_row, dict) or not self._is_batch_bank_row(bank_row, resolved_year, require_unlinked=False):
            raise BatchAccountingError("invalid_batch_accounting_bank_row", "银行流水不符合批量账务提交条件。")
        active_bank_relation = self._pair_relation_service.get_active_relation_by_row_id(normalized_bank_row_id)
        if isinstance(active_bank_relation, dict):
            raise BatchAccountingError("batch_accounting_bank_row_already_linked", "银行流水已有关联关系，请刷新后重试。")
        if expected_version is not None:
            row_version = self._optional_int(bank_row.get("version"))
            if row_version is not None and row_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "银行流水版本已变化，请刷新后重试。")

        eligible_oa_by_id = {str(row.get("id")): row for row in context.eligible_oa_rows}
        selected_oa_rows: list[dict[str, Any]] = []
        for oa_row_id in normalized_oa_row_ids:
            oa_row = eligible_oa_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict):
                raise BatchAccountingError("invalid_batch_accounting_oa_row", "OA 单据不符合批量账务提交条件。")
            selected_oa_rows.append(oa_row)

        bank_amount = self._bank_expense_amount(bank_row)
        oa_amount = sum((self._money(row.get("amount")) or Decimal("0.00") for row in selected_oa_rows), Decimal("0.00"))
        if self._quantize(bank_amount) != self._quantize(oa_amount):
            raise BatchAccountingError(
                "batch_accounting_amount_mismatch",
                "银行流水金额与所选 OA 金额合计不一致。",
                payload={
                    "bank_amount": self._format_amount(bank_amount),
                    "oa_amount": self._format_amount(oa_amount),
                    "amount_delta": self._format_amount(bank_amount - oa_amount),
                },
            )

        invoice_row_ids = self._linked_invoice_row_ids(normalized_oa_row_ids, context)
        row_ids = self._dedupe([normalized_bank_row_id, *normalized_oa_row_ids, *invoice_row_ids])
        rows = [context.rows_by_id.get(row_id, {"id": row_id, "type": self._row_type_for_row_id(row_id)}) for row_id in row_ids]
        row_types = [self._row_type(row, row_id) for row, row_id in zip(rows, row_ids, strict=False)]
        before_relations = self._pair_relation_service.active_relations_for_row_ids(row_ids)
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(rows, existing_relations=before_relations, month_scope=self._month_scope(rows)),
        )
        amount_check = {
            "status": "matched",
            "direction": "expense",
            "bank_amount": self._format_amount(bank_amount),
            "oa_amount": self._format_amount(oa_amount),
            "amount_delta": "0.00",
        }
        relation, _history = self._pair_relation_service.replace_with_confirmed_relation(
            case_id=self._case_id_provider(),
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by=actor,
            month_scope=self._month_scope(rows),
            note="日常报销批量账务管理提交",
            amount_check=amount_check,
            special_metadata={
                "source": BATCH_ACCOUNTING_SOURCE,
                "bank_row_id": normalized_bank_row_id,
                "oa_row_ids": normalized_oa_row_ids,
                "invoice_row_ids": invoice_row_ids,
                "year": resolved_year,
                "created_by": actor,
            },
            before_relations=history_before_relations,
        )
        return {
            "success": True,
            "action": "submit_batch_accounting",
            "relation_id": str(relation.get("case_id") or ""),
            "pair_relation": relation,
            "affected_row_ids": row_ids,
            "changed_case_ids": self._dedupe(
                [
                    *[str(item.get("case_id") or "") for item in before_relations],
                    str(relation.get("case_id") or ""),
                ]
            ),
            "month_scope": str(relation.get("month_scope") or "all"),
            "amount_check": amount_check,
            "message": f"已关联批量账务流水与 {len(normalized_oa_row_ids)} 项 OA。",
        }

    def withdraw(
        self,
        *,
        relation_id: str,
        actor: str,
        reason: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        normalized_relation_id = self._required_id(relation_id, "relation_id")
        note = str(reason or "").strip()
        if not note:
            raise BatchAccountingError("batch_accounting_withdraw_reason_required", "撤回原因不能为空。")
        active_relation = self._pair_relation_service.get_active_relation_by_case_id(normalized_relation_id)
        if not self._is_batch_accounting_relation(active_relation):
            raise BatchAccountingError("batch_accounting_relation_not_found", "批量账务关联不存在或不可撤回。")
        if expected_version is not None:
            relation_version = self._optional_int(active_relation.get("version") if isinstance(active_relation, dict) else None)
            if relation_version is not None and relation_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "关联版本已变化，请刷新后重试。")
        row_ids = self._normalize_ids(list(active_relation.get("row_ids") or []))
        restored_relations, _history = self._pair_relation_service.withdraw_latest_for_row_ids(
            row_ids,
            created_by=actor,
            note=note,
        )
        affected_row_ids = self._dedupe(
            [
                *row_ids,
                *[
                    str(row_id)
                    for relation in restored_relations
                    for row_id in list(relation.get("row_ids") or [])
                    if str(row_id).strip()
                ],
            ]
        )
        return {
            "success": True,
            "action": "withdraw_batch_accounting",
            "relation_id": normalized_relation_id,
            "affected_row_ids": affected_row_ids,
            "restored_relations": restored_relations,
            "changed_case_ids": self._dedupe(
                [normalized_relation_id, *[str(relation.get("case_id") or "") for relation in restored_relations]]
            ),
            "month_scope": str(active_relation.get("month_scope") or "all"),
            "message": "已撤回批量账务关联。",
        }

    def _build_context(self, year: str) -> _WorkbenchContext:
        payload = self._grouped_workbench_loader("all")
        groups = self._groups_from_payload(payload)
        rows_by_id: dict[str, dict[str, Any]] = {}
        bank_rows: list[dict[str, Any]] = []
        open_oa_rows: list[dict[str, Any]] = []
        invoice_ids_by_oa_id: dict[str, list[str]] = {}
        for group in groups:
            section = str(group.get("_section") or "")
            for row in list(group.get("bank_rows") or []):
                if not isinstance(row, dict):
                    continue
                bank_row = self._annotated_row(row, group, section)
                rows_by_id[str(bank_row.get("id"))] = bank_row
                bank_rows.append(bank_row)
            group_oa_rows = [
                self._annotated_row(row, group, section)
                for row in list(group.get("oa_rows") or [])
                if isinstance(row, dict)
            ]
            for row in group_oa_rows:
                rows_by_id[str(row.get("id"))] = row
                if section == "open":
                    open_oa_rows.append(row)
            invoice_rows = [
                self._annotated_row(row, group, section)
                for row in list(group.get("invoice_rows") or [])
                if isinstance(row, dict)
            ]
            for row in invoice_rows:
                rows_by_id[str(row.get("id"))] = row
            if section == "open":
                self._index_group_invoice_links(group_oa_rows, invoice_rows, invoice_ids_by_oa_id)
        eligible_bank_rows = [row for row in bank_rows if self._is_batch_bank_row(row, year, require_unlinked=True)]
        eligible_oa_rows = [row for row in open_oa_rows if self._is_eligible_oa_row(row, year)]
        return _WorkbenchContext(
            rows_by_id=rows_by_id,
            groups=groups,
            bank_rows=bank_rows,
            open_oa_rows=open_oa_rows,
            invoice_ids_by_oa_id=invoice_ids_by_oa_id,
            eligible_bank_rows=eligible_bank_rows,
            eligible_oa_rows=eligible_oa_rows,
        )

    @staticmethod
    def _groups_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for section in ("open", "paired"):
            section_payload = payload.get(section)
            if not isinstance(section_payload, dict):
                continue
            for group in list(section_payload.get("groups") or []):
                if isinstance(group, dict):
                    groups.append({**group, "_section": section})
        return groups

    @staticmethod
    def _annotated_row(row: dict[str, Any], group: dict[str, Any], section: str) -> dict[str, Any]:
        result = deepcopy(row)
        result["_section"] = section
        result["_group_id"] = str(group.get("group_id") or "")
        group_case_id = str(group.get("case_id") or "").strip()
        if not group_case_id and str(group.get("group_id") or "").startswith("case:"):
            group_case_id = str(group.get("group_id"))[5:]
        result["_group_case_id"] = group_case_id
        return result

    def _index_group_invoice_links(
        self,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        invoice_ids_by_oa_id: dict[str, list[str]],
    ) -> None:
        oa_ids = [str(row.get("id") or "").strip() for row in oa_rows if str(row.get("id") or "").strip()]
        for invoice_row in invoice_rows:
            if not self._is_oa_attachment_invoice(invoice_row):
                continue
            invoice_id = str(invoice_row.get("id") or "").strip()
            if not invoice_id:
                continue
            linked_oa_id = self._invoice_source_oa_id(invoice_row, oa_ids)
            if linked_oa_id:
                invoice_ids_by_oa_id.setdefault(linked_oa_id, []).append(invoice_id)

    def _is_batch_bank_row(self, row: dict[str, Any], year: str, *, require_unlinked: bool) -> bool:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            return False
        if str(row.get("type") or "bank") != "bank" and self._row_type_for_row_id(row_id) != "bank":
            return False
        if self._clean_text(row.get("counterparty_name")) != BATCH_ACCOUNTING_COUNTERPARTY_NAME:
            return False
        if not self._row_year_matches(row, year, keys=("trade_time", "pay_receive_time", "txn_date", "transaction_date", "date")):
            return False
        if self._bank_expense_amount(row) <= Decimal("0.00"):
            return False
        if require_unlinked and self._pair_relation_service.get_active_relation_by_row_id(row_id) is not None:
            return False
        return True

    def _is_eligible_oa_row(self, row: dict[str, Any], year: str) -> bool:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            return False
        if self._pair_relation_service.get_active_relation_by_row_id(row_id) is not None:
            return False
        if str(row.get("type") or "oa") != "oa" and self._row_type_for_row_id(row_id) != "oa":
            return False
        if ":item:" in row_id or str(row.get("row_kind") or "").strip() in {"schedule_detail", "detail"}:
            return False
        if not self._contains_daily_reimbursement(row):
            return False
        return self._row_year_matches(
            row,
            year,
            keys=("apply_time", "application_time", "application_date", "date", "created_at"),
            nested_date_keys=("申请日期", "单据日期", "日期"),
        )

    def _submitted_relations(self, year: str, context: _WorkbenchContext) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        for relation in self._pair_relation_service.list_active_relations():
            if not self._is_batch_accounting_relation(relation):
                continue
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            bank_row_id = str(metadata.get("bank_row_id") or "").strip()
            bank_row = context.rows_by_id.get(bank_row_id)
            if str(metadata.get("year") or "").strip() == year or (
                isinstance(bank_row, dict) and self._row_year_matches(bank_row, year, keys=("trade_time", "pay_receive_time", "txn_date"))
            ):
                relations.append(relation)
        return relations

    def _submitted_payload(
        self,
        relations: list[dict[str, Any]],
        context: _WorkbenchContext,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        bank_rows: list[dict[str, Any]] = []
        relations_by_bank_row_id: dict[str, Any] = {}
        for relation in relations:
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            bank_row_id = str(metadata.get("bank_row_id") or "").strip()
            if not bank_row_id:
                bank_row_id = next(
                    (str(row_id) for row_id in list(relation.get("row_ids") or []) if self._row_type_for_row_id(str(row_id)) == "bank"),
                    "",
                )
            if not bank_row_id:
                continue
            bank_row = context.rows_by_id.get(bank_row_id, {"id": bank_row_id, "type": "bank"})
            bank_payload = self._bank_row_payload(bank_row, relation_id=str(relation.get("case_id") or ""))
            bank_rows.append(bank_payload)
            oa_row_ids = [str(row_id) for row_id in list(metadata.get("oa_row_ids") or []) if str(row_id).strip()]
            invoice_row_ids = [str(row_id) for row_id in list(metadata.get("invoice_row_ids") or []) if str(row_id).strip()]
            relations_by_bank_row_id[bank_row_id] = {
                "relation_id": str(relation.get("case_id") or ""),
                "relation": deepcopy(relation),
                "oa_rows": [self._oa_row_payload(context.rows_by_id.get(row_id, {"id": row_id, "type": "oa"}), []) for row_id in oa_row_ids],
                "invoice_rows": [
                    deepcopy(context.rows_by_id.get(row_id, {"id": row_id, "type": "invoice"}))
                    for row_id in invoice_row_ids
                ],
                "metadata": deepcopy(metadata),
            }
        return bank_rows, relations_by_bank_row_id

    def _bank_row_payload(self, row: dict[str, Any], *, relation_id: str = "") -> dict[str, Any]:
        amount = self._bank_expense_amount(row)
        bank_name, account_last4 = self._bank_account_parts(row)
        return {
            "id": str(row.get("id") or ""),
            "trade_time": str(row.get("trade_time") or row.get("pay_receive_time") or row.get("txn_date") or ""),
            "counterparty_name": self._clean_text(row.get("counterparty_name")),
            "direction": "expense",
            "direction_label": "支出",
            "amount": self._format_amount(amount),
            "bank_name": bank_name,
            "account_last4": account_last4,
            "relation_id": relation_id,
            "version": self._optional_int(row.get("version")) or 1,
        }

    def _oa_row_payload(self, row: dict[str, Any], linked_invoice_row_ids: list[str]) -> dict[str, Any]:
        return {
            "id": str(row.get("id") or ""),
            "applicant": self._first_text(row, ("applicant", "applicant_name", "apply_user", "userName"), ("申请人",)),
            "apply_time": self._first_text(
                row,
                ("apply_time", "application_time", "application_date", "date", "created_at"),
                ("申请日期", "单据日期", "日期"),
            ),
            "project_name": self._first_text(row, ("project_name", "project"), ("项目名称", "项目")),
            "amount": self._format_amount(self._money(row.get("amount")) or Decimal("0.00")),
            "reason": self._first_text(row, ("reason", "remark"), ("申请事由", "报销事由", "事由", "备注")),
            "apply_type": str(row.get("apply_type") or ""),
            "expense_type": str(row.get("expense_type") or ""),
            "linked_invoice_row_ids": list(linked_invoice_row_ids),
        }

    def _synthetic_existing_case_relations(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        existing_relations: list[dict[str, Any]],
        month_scope: str,
    ) -> list[dict[str, Any]]:
        covered_row_ids = {
            str(row_id).strip()
            for relation in existing_relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        rows_by_case_id: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            row_id = str(row.get("id") or "").strip()
            case_id = str(row.get("case_id") or row.get("_group_case_id") or "").strip()
            if not row_id or not case_id or row_id in covered_row_ids:
                continue
            rows_by_case_id.setdefault(case_id, []).append(row)
        relations: list[dict[str, Any]] = []
        for case_id, case_rows in rows_by_case_id.items():
            if len(case_rows) < 2:
                continue
            relations.append(
                {
                    "case_id": case_id,
                    "row_ids": [str(row.get("id") or "").strip() for row in case_rows],
                    "row_types": [self._row_type(row, str(row.get("id") or "")) for row in case_rows],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": month_scope,
                }
            )
        return relations

    @staticmethod
    def _merge_relation_snapshots(
        primary_relations: list[dict[str, Any]],
        secondary_relations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for relation in [*primary_relations, *secondary_relations]:
            case_id = str(relation.get("case_id") or "").strip()
            if case_id:
                merged[case_id] = relation
        return list(merged.values())

    def _linked_invoice_row_ids(self, oa_row_ids: list[str], context: _WorkbenchContext) -> list[str]:
        invoice_row_ids: list[str] = []
        for oa_row_id in oa_row_ids:
            invoice_row_ids.extend(context.invoice_ids_by_oa_id.get(oa_row_id, []))
        return self._dedupe(invoice_row_ids)

    @staticmethod
    def _is_batch_accounting_relation(relation: dict[str, Any] | None) -> bool:
        if not isinstance(relation, dict):
            return False
        metadata = relation.get("special_metadata")
        return relation.get("status") == "active" and isinstance(metadata, dict) and metadata.get("source") == BATCH_ACCOUNTING_SOURCE

    @staticmethod
    def _validate_year(year: str) -> str:
        resolved_year = str(year or "").strip()
        if not re.fullmatch(r"20\d{2}", resolved_year):
            raise BatchAccountingError("invalid_batch_accounting_year", "year must be a four-digit year.")
        return resolved_year

    @staticmethod
    def _required_id(value: str, field_name: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise BatchAccountingError("invalid_batch_accounting_request", f"{field_name} is required.")
        return resolved

    @classmethod
    def _normalize_ids(cls, values: list[Any]) -> list[str]:
        ids = cls._dedupe([str(value or "").strip() for value in values])
        if not ids:
            raise BatchAccountingError("invalid_batch_accounting_request", "at least one OA row is required.")
        return ids

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _first_text(
        cls,
        row: dict[str, Any],
        keys: tuple[str, ...],
        nested_keys: tuple[str, ...] = (),
    ) -> str:
        for key in keys:
            value = cls._clean_text(row.get(key))
            if value:
                return value
        for nested_field in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_field)
            if not isinstance(nested, dict):
                continue
            for key in nested_keys:
                value = cls._clean_text(nested.get(key))
                if value:
                    return value
        return ""

    @classmethod
    def _contains_daily_reimbursement(cls, row: dict[str, Any]) -> bool:
        return "日常报销" in cls._clean_text(row.get("apply_type")) or "日常报销" in cls._clean_text(row.get("expense_type"))

    @classmethod
    def _row_year_matches(
        cls,
        row: dict[str, Any],
        year: str,
        *,
        keys: tuple[str, ...],
        nested_date_keys: tuple[str, ...] = (),
    ) -> bool:
        values: list[Any] = [row.get(key) for key in keys]
        for nested_key in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_key)
            if isinstance(nested, dict):
                values.extend(nested.get(key) for key in nested_date_keys)
        return any(str(value or "").strip().startswith(year) for value in values)

    @classmethod
    def _bank_expense_amount(cls, row: dict[str, Any]) -> Decimal:
        debit = cls._money(row.get("debit_amount"))
        if debit is not None and debit > Decimal("0.00"):
            return debit
        direction = cls._clean_text(row.get("direction") or row.get("txn_direction") or row.get("direction_code")).lower()
        amount = cls._money(row.get("amount")) or cls._money(row.get("signed_amount")) or Decimal("0.00")
        if direction in {"expense", "outflow", "支出"}:
            return abs(amount)
        signed_amount = cls._money(row.get("signed_amount"))
        if signed_amount is not None and signed_amount < Decimal("0.00"):
            return abs(signed_amount)
        return Decimal("0.00")

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "")).copy_abs()
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def _format_amount(cls, value: Decimal) -> str:
        return f"{cls._quantize(value):.2f}"

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _bank_account_parts(cls, row: dict[str, Any]) -> tuple[str, str]:
        label = cls._clean_text(row.get("payment_account_label") or row.get("account_label"))
        bank_name = cls._clean_text(row.get("bank_name") or row.get("selected_bank_name") or row.get("imported_bank_name"))
        account_last4 = cls._clean_text(row.get("account_last4") or row.get("selected_bank_last4") or row.get("imported_bank_last4"))
        if label:
            parts = label.split()
            if not bank_name and parts:
                bank_name = parts[0].replace("基本户", "").replace("一般户", "")
            if not account_last4:
                digit_groups = re.findall(r"\d{4,}", label)
                if digit_groups:
                    account_last4 = digit_groups[-1][-4:]
        return bank_name, account_last4

    @classmethod
    def _is_oa_attachment_invoice(cls, row: dict[str, Any]) -> bool:
        return cls._clean_text(row.get("source_kind")) == "oa_attachment_invoice" or cls._clean_text(row.get("id")).startswith("oa-att-inv-")

    @classmethod
    def _invoice_source_oa_id(cls, invoice_row: dict[str, Any], oa_ids: list[str]) -> str | None:
        for key in ("derived_from_oa_id", "source_oa_id", "oa_row_id"):
            value = cls._clean_text(invoice_row.get(key))
            if value in oa_ids:
                return value
        invoice_id = cls._clean_text(invoice_row.get("id"))
        prefix = "oa-att-inv-"
        if invoice_id.startswith(prefix):
            tail = invoice_id[len(prefix):]
            for oa_id in sorted(oa_ids, key=len, reverse=True):
                if tail == oa_id or tail.startswith(f"{oa_id}-"):
                    return oa_id
        if len(oa_ids) == 1:
            return oa_ids[0]
        return None

    @classmethod
    def _row_type(cls, row: dict[str, Any], row_id: str) -> str:
        return str(row.get("type") or cls._row_type_for_row_id(row_id) or "unknown")

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        lowered = str(row_id or "").strip().lower()
        if lowered.startswith("oa-att-inv-"):
            return "invoice"
        if lowered.startswith("oa-"):
            return "oa"
        if lowered.startswith(("bk-", "txn-", "txn_", "bank-")):
            return "bank"
        if lowered.startswith(("iv-", "invoice-", "etc-summary-")):
            return "invoice"
        return "unknown"

    @classmethod
    def _month_scope(cls, rows: Iterable[dict[str, Any]]) -> str:
        months = {
            month
            for row in rows
            for month in [cls._row_month(row)]
            if month is not None
        }
        if len(months) == 1:
            return next(iter(months))
        return "all"

    @classmethod
    def _row_month(cls, row: dict[str, Any]) -> str | None:
        for key in (
            "trade_time",
            "pay_receive_time",
            "txn_date",
            "apply_time",
            "application_time",
            "application_date",
            "issue_date",
        ):
            value = str(row.get(key) or "").strip()
            if re.match(r"20\d{2}-\d{2}", value):
                return value[:7]
        for nested_key in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_key)
            if not isinstance(nested, dict):
                continue
            for key in ("申请日期", "单据日期", "日期"):
                value = str(nested.get(key) or "").strip()
                if re.match(r"20\d{2}-\d{2}", value):
                    return value[:7]
        return None
