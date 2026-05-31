from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_TRANSACTION_CATEGORY_DEFINITIONS,
    BANK_TRANSACTION_CATEGORY_LABELS,
    BankTransactionCategoryService,
)
from fin_ops_platform.services.turnover_relation_service import (
    TURNOVER_CATEGORY_RULES,
    TurnoverRelationService,
)


MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.000001")
ZERO = Decimal("0.00")
ZERO_RATE = Decimal("0.000000")
TURNOVER_LEDGER_SCHEMA_VERSION = "2026-05-turnover-ledger-v1"
TURNOVER_FAMILY_LABELS = {
    "personal": "个人往来",
    "company": "公司往来",
    "bank": "银行往来",
    "business": "业务往来",
    "uncategorized": "待分类",
}
TURNOVER_STATUS_LABELS = {
    "deterministic": "完全闭合",
    "confirmed": "人工确认",
    "suggested": "待人工确认",
    "conflict": "冲突",
    "stale": "已过期",
    "withdrawn": "已撤回",
}
ROW_TONES = {
    "deterministic": "success",
    "confirmed": "success",
    "suggested": "warning",
    "conflict": "danger",
    "stale": "muted",
    "withdrawn": "muted",
}
VALID_FAMILY_FILTERS = {"all", *TURNOVER_FAMILY_LABELS.keys()}
VALID_DIRECTION_FILTERS = {"all", "borrow_in", "borrow_out"}


class TurnoverLedgerService:
    def __init__(
        self,
        *,
        import_service: Any,
        category_service: BankTransactionCategoryService,
        relation_service: TurnoverRelationService,
        extra_service: Any | None = None,
        category_provider: Any | None = None,
        today_provider: Callable[[], date] | None = None,
    ) -> None:
        self._import_service = import_service
        self._category_service = category_service
        self._category_provider = category_provider
        self._relation_service = relation_service
        self._extra_service = extra_service
        self._today_provider = today_provider or date.today

    def list_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        bank_rows = self._bank_rows()
        relations = self._relation_service.rebuild_from_bank_rows(bank_rows)
        rows_by_id = {str(row.get("id") or ""): row for row in bank_rows}
        ledger_rows = [self._row_payload(relation, rows_by_id) for relation in relations]
        ledger_rows = [row for row in ledger_rows if row is not None]
        filtered_rows = self._apply_filters(ledger_rows, family=family, direction=direction, status=status)
        filtered_rows.sort(
            key=lambda row: (
                str(row.get("first_transaction_at") or ""),
                str(row.get("relation_id") or ""),
            ),
            reverse=True,
        )
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 50), 1), 200)
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        return {
            "summary": self._summary(filtered_rows),
            "family_summaries": [
                self._family_summary(
                    family_key,
                    [row for row in ledger_rows if row.get("family") == family_key],
                )
                for family_key in TURNOVER_FAMILY_LABELS
            ],
            "rows": filtered_rows[start:end],
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": len(filtered_rows),
            },
            "filters": {
                "family": self._normalize_family(family),
                "direction": self._normalize_direction_filter(direction),
                "status": self._normalize_status(status),
            },
        }

    def list_grouped_ledger(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        bank_rows = self._bank_rows()
        relations = self._relation_service.rebuild_from_bank_rows(bank_rows)
        rows_by_id = {str(row.get("id") or ""): row for row in bank_rows}
        items: list[dict[str, Any]] = []
        for relation in relations:
            legacy_row = self._row_payload(relation, rows_by_id)
            if legacy_row is None:
                continue
            grouped_row = self._grouped_row_payload(relation, rows_by_id)
            if grouped_row is None:
                continue
            allocation_lots = self._lot_row_payloads(relation, rows_by_id)
            flow_rows = self._flow_row_payloads(relation, rows_by_id, allocation_lots)
            items.append(
                {
                    "legacy": legacy_row,
                    "row": grouped_row,
                    "flow_rows": flow_rows,
                    "allocation_lots": allocation_lots,
                    "family": legacy_row.get("family"),
                    "status": legacy_row.get("status"),
                    "counterparty_name": legacy_row.get("counterparty_name"),
                    "business_type": legacy_row.get("business_type"),
                    "balance_amount": self._money(legacy_row.get("balance_amount")),
                }
            )
        relation_row_ids = {
            str(row_id)
            for relation in relations
            for row_id in list(relation.get("bank_row_ids") or [])
            if str(row_id).strip()
        }
        for row in bank_rows:
            row_id = self._row_id(row)
            if row_id in relation_row_ids or str(row.get("category_code") or "") != "external_turnover":
                continue
            items.append(self._unclassified_item(row))

        filtered_items = self._apply_item_filters(items, family=family, direction=direction, status=status)
        filtered_items.sort(
            key=lambda item: (
                str(item["row"].get("borrow_date") or ""),
                str(item["row"].get("relation_id") or ""),
            ),
            reverse=True,
        )
        groups = self._group_items(filtered_items)
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 50), 1), 200)
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        legacy_rows = [item["legacy"] for item in filtered_items]
        all_legacy_rows = [item["legacy"] for item in items]
        return {
            "summary": self._summary(legacy_rows),
            "family_summaries": [
                self._family_summary(
                    family_key,
                    [row for row in all_legacy_rows if row.get("family") == family_key],
                )
                for family_key in TURNOVER_FAMILY_LABELS
            ],
            "groups": groups[start:end],
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": len(groups),
            },
            "filters": {
                "family": self._normalize_family(family),
                "direction": self._normalize_direction_filter(direction),
                "status": self._normalize_status(status),
            },
        }

    def get_relation_detail(self, relation_id: str) -> dict[str, Any]:
        normalized_relation_id = str(relation_id or "").strip()
        bank_rows = self._bank_rows()
        rows_by_id = {str(row.get("id") or ""): row for row in bank_rows}
        for relation in self._relation_service.relations():
            if str(relation.get("relation_id") or "") != normalized_relation_id:
                continue
            row_payload = self._row_payload(relation, rows_by_id)
            return {
                "relation": relation,
                "row": row_payload,
                "bank_rows": [
                    rows_by_id[row_id]
                    for row_id in list(relation.get("bank_row_ids") or [])
                    if row_id in rows_by_id
                ],
            }
        raise KeyError(normalized_relation_id)

    def _bank_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        try:
            transactions = list(self._import_service.list_transactions(month="all"))
        except TypeError:
            transactions = list(self._import_service.list_transactions())
        transaction_rows = [
            self._transaction_payload(transaction)
            for transaction in transactions
        ]
        categories_by_transaction_id = self._categories_for_rows(transaction_rows)
        for row in transaction_rows:
            transaction_id = str(row.get("id") or "").strip()
            if not transaction_id:
                continue
            category = categories_by_transaction_id.get(transaction_id, {})
            category_code = category.get("category_code")
            if category_code not in BANK_TRANSACTION_CATEGORY_DEFINITIONS and category_code != "external_turnover":
                continue
            enriched = dict(row)
            enriched["category_code"] = category_code
            enriched["category_label"] = category.get("category_label") or BANK_TRANSACTION_CATEGORY_LABELS.get(
                category_code
            )
            enriched["category_path"] = list(category.get("category_path") or [])
            enriched["category_primary_label"] = category.get("category_primary_label")
            enriched["category_sub_label"] = category.get("category_sub_label")
            enriched["category_third_label"] = category.get("category_third_label")
            enriched["category_label_path"] = list(category.get("category_label_path") or [])
            enriched["turnover_role"] = category.get("turnover_role")
            enriched["turnover_action_type"] = category.get("turnover_action_type")
            enriched["turnover_family"] = category.get("turnover_family")
            enriched["category_version"] = int(category.get("category_version") or 0)
            enriched["debit_amount"] = self._debit_amount(row)
            enriched["credit_amount"] = self._credit_amount(row)
            enriched["counterparty_name"] = str(row.get("counterparty_name_raw") or row.get("counterparty_name") or "")
            rows.append(enriched)
        return rows

    def _categories_for_rows(self, bank_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        transaction_ids = [
            str(row.get("id") or "").strip()
            for row in bank_rows
            if str(row.get("id") or "").strip()
        ]
        provider = self._category_provider
        if provider is not None and hasattr(provider, "bulk_get_for_rows"):
            raw_records = provider.bulk_get_for_rows(bank_rows)
        else:
            raw_records = self._category_service.bulk_get(transaction_ids)
        if not isinstance(raw_records, dict):
            raw_records = {}
        records = {
            str(transaction_id): record
            for transaction_id, record in raw_records.items()
            if isinstance(record, dict)
        }
        for transaction_id in transaction_ids:
            record = records.get(transaction_id) or {}
            if record.get("category_code") in BANK_TRANSACTION_CATEGORY_DEFINITIONS:
                continue
            manual = self._category_service.get(transaction_id)
            manual_code = str(manual.get("category_code") or "").strip()
            if manual_code in TURNOVER_CATEGORY_RULES:
                records[transaction_id] = manual
        return records

    @staticmethod
    def _transaction_payload(transaction: Any) -> dict[str, Any]:
        if is_dataclass(transaction):
            return asdict(transaction)
        return dict(transaction)

    @classmethod
    def _debit_amount(cls, row: dict[str, Any]) -> str:
        if cls._direction(row) == "outflow":
            return cls._format_money(cls._money(row.get("amount")))
        return "0.00"

    @classmethod
    def _credit_amount(cls, row: dict[str, Any]) -> str:
        if cls._direction(row) == "inflow":
            return cls._format_money(cls._money(row.get("amount")))
        return "0.00"

    @staticmethod
    def _direction(row: dict[str, Any]) -> str:
        value = row.get("txn_direction") or row.get("direction")
        if hasattr(value, "value"):
            value = value.value
        normalized = str(value or "").strip().lower()
        if normalized in {"inflow", "income", "收", "进"}:
            return "inflow"
        if normalized in {"outflow", "expense", "支", "出"}:
            return "outflow"
        signed = TurnoverLedgerService._money(row.get("signed_amount"))
        return "inflow" if signed > ZERO else "outflow"

    def _row_payload(self, relation: dict[str, Any], rows_by_id: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        bank_row_ids = [
            str(row_id)
            for row_id in list(relation.get("bank_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        if not bank_row_ids:
            return None
        bank_rows = [rows_by_id[row_id] for row_id in bank_row_ids]
        status = str(relation.get("status") or "")
        family = str(relation.get("category_family") or "")
        principal_amount = self._money(relation.get("principal_amount"))
        settled_amount = self._money(relation.get("settled_amount"))
        balance_amount = self._money(relation.get("balance_amount"))
        return {
            "relation_id": str(relation.get("relation_id") or ""),
            "status": status,
            "status_label": TURNOVER_STATUS_LABELS.get(status, status or "未知"),
            "row_tone": ROW_TONES.get(status, "muted"),
            "chips": self._chips(relation),
            "family": family,
            "family_label": TURNOVER_FAMILY_LABELS.get(family, family or "未知"),
            "counterparty_name": str(relation.get("counterparty_name") or ""),
            "principal_amount": self._format_money(principal_amount),
            "settled_amount": self._format_money(settled_amount),
            "balance_amount": self._format_money(balance_amount),
            "first_transaction_at": relation.get("first_transaction_at"),
            "last_settlement_at": relation.get("last_settlement_at"),
            "bank_account_labels": self._bank_account_labels(bank_rows),
            "summary_text": self._summary_text(bank_rows),
            "annual_interest_rate": None,
            "loan_days": self._loan_days(relation),
            "accrued_interest": None,
            "sync_to_workbench": bool(relation.get("sync_to_workbench")),
            "bank_row_ids": bank_row_ids,
            "category_codes": list(relation.get("category_codes") or []),
            "business_type": str(relation.get("business_type") or ""),
        }

    def _grouped_row_payload(
        self,
        relation: dict[str, Any],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        bank_row_ids = [
            str(row_id)
            for row_id in list(relation.get("bank_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        if not bank_row_ids:
            return None
        principal_row_ids = [
            str(row_id)
            for row_id in list(relation.get("principal_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        settlement_row_ids = [
            str(row_id)
            for row_id in list(relation.get("settlement_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        principal_rows = [rows_by_id[row_id] for row_id in principal_row_ids]
        settlement_rows = [rows_by_id[row_id] for row_id in settlement_row_ids]
        all_rows = [rows_by_id[row_id] for row_id in bank_row_ids]
        status = str(relation.get("status") or "")
        business_type = str(relation.get("business_type") or "")
        borrow_date = self._date_for_rows(principal_rows) or self._date_from_value(
            relation.get("first_transaction_at")
        )
        repayment_date = self._date_for_rows(settlement_rows, latest=True) or self._date_from_value(
            relation.get("last_settlement_at")
        )
        principal_amount = self._money(relation.get("principal_amount"))
        settled_amount = self._money(relation.get("settled_amount"))
        extra = self._extra_for_relation(str(relation.get("relation_id") or ""))
        interest_rate_type = self._interest_rate_type(extra.get("interest_rate_type"))
        interest_rate_value = (
            self._rate(extra.get("interest_rate_value"))
            if interest_rate_type != "none"
            else ZERO_RATE
        )
        interest_paid_amount = self._money(extra.get("interest_paid_amount"))
        loan_days = self._grouped_loan_days(borrow_date=borrow_date, repayment_date=repayment_date)
        accrued_interest = self._accrued_interest(
            principal_amount=principal_amount,
            interest_rate_type=interest_rate_type,
            interest_rate_value=interest_rate_value,
            loan_days=loan_days,
        )
        borrow_direction, repayment_direction = self._money_directions(business_type)
        return {
            "relation_id": str(relation.get("relation_id") or ""),
            "status": status,
            "status_label": TURNOVER_STATUS_LABELS.get(status, status or "未知"),
            "row_tone": ROW_TONES.get(status, "muted"),
            "borrow_amount": self._format_money(principal_amount),
            "borrow_date": borrow_date,
            "borrow_direction": borrow_direction,
            "repayment_amount": self._format_money(settled_amount),
            "repayment_date": repayment_date,
            "repayment_direction": repayment_direction,
            "balance_amount": self._format_money(principal_amount - settled_amount),
            "counterparty_bank_name": self._counterparty_bank_name(all_rows),
            "repayment_remark": self._summary_text(settlement_rows),
            "interest_rate_type": interest_rate_type,
            "interest_rate_value": self._format_rate(interest_rate_value),
            "interest_paid_amount": self._format_money(interest_paid_amount),
            "loan_days": loan_days,
            "accrued_interest": self._format_money(accrued_interest),
            "interest_paid_date": self._empty_to_none(extra.get("interest_paid_date")),
            "interest_payment_method": str(extra.get("interest_payment_method") or "").strip(),
            "note": str(extra.get("note") or "").strip(),
            "bank_row_ids": bank_row_ids,
        }

    def _lot_row_payloads(
        self,
        relation: dict[str, Any],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        relation_id = str(relation.get("relation_id") or "")
        principal_row_ids = [
            str(row_id)
            for row_id in list(relation.get("principal_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        settlement_row_ids = [
            str(row_id)
            for row_id in list(relation.get("settlement_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        principal_rows = sorted(
            (rows_by_id[row_id] for row_id in principal_row_ids),
            key=self._row_fifo_sort_key,
        )
        settlement_allocations = [
            {
                "row": rows_by_id[row_id],
                "row_id": row_id,
                "remaining_amount": self._row_amount(rows_by_id[row_id]),
            }
            for row_id in sorted(
                settlement_row_ids,
                key=lambda row_id: self._row_fifo_sort_key(rows_by_id[row_id]),
            )
        ]
        status = str(relation.get("status") or "")
        business_type = str(relation.get("business_type") or "")
        borrow_direction, repayment_direction = self._money_directions(business_type)
        extra = self._extra_for_relation(relation_id)
        interest_rate_type = self._interest_rate_type(extra.get("interest_rate_type"))
        interest_rate_value = (
            self._rate(extra.get("interest_rate_value"))
            if interest_rate_type != "none"
            else ZERO_RATE
        )
        interest_paid_amount = self._money(extra.get("interest_paid_amount"))

        lot_rows: list[dict[str, Any]] = []
        for principal_row in principal_rows:
            principal_bank_row_id = self._row_id(principal_row)
            borrow_amount = self._row_amount(principal_row)
            remaining_principal = borrow_amount
            repayment_amount = ZERO
            allocated_settlement_ids: list[str] = []
            allocated_settlement_rows: list[dict[str, Any]] = []
            latest_repayment_date: str | None = None
            fully_repaid_date: str | None = None

            for allocation in settlement_allocations:
                if remaining_principal <= ZERO:
                    break
                available = allocation["remaining_amount"]
                if available <= ZERO:
                    continue
                allocated_amount = min(remaining_principal, available)
                if allocated_amount <= ZERO:
                    continue
                allocation["remaining_amount"] = available - allocated_amount
                remaining_principal -= allocated_amount
                repayment_amount += allocated_amount
                settlement_row_id = str(allocation["row_id"])
                settlement_row = allocation["row"]
                if settlement_row_id not in allocated_settlement_ids:
                    allocated_settlement_ids.append(settlement_row_id)
                    allocated_settlement_rows.append(settlement_row)
                settlement_date = self._date_from_value(self._transaction_at(settlement_row))
                if settlement_date is not None:
                    latest_repayment_date = settlement_date
                if remaining_principal == ZERO:
                    fully_repaid_date = settlement_date

            borrow_date = self._date_from_value(self._transaction_at(principal_row))
            balance_amount = borrow_amount - repayment_amount
            loan_days = self._grouped_loan_days(
                borrow_date=borrow_date,
                repayment_date=fully_repaid_date if balance_amount == ZERO else None,
            )
            accrued_interest = self._accrued_interest(
                principal_amount=borrow_amount,
                interest_rate_type=interest_rate_type,
                interest_rate_value=interest_rate_value,
                loan_days=loan_days,
            )
            bank_row_ids = [principal_bank_row_id, *allocated_settlement_ids]
            lot_rows.append(
                {
                    "_lot_sort_key": self._row_fifo_sort_key(principal_row),
                    "row_kind": "allocation_lot",
                    "lot_id": f"{relation_id}:lot:{principal_bank_row_id}",
                    "relation_id": relation_id,
                    "parent_relation_id": relation_id,
                    "principal_bank_row_id": principal_bank_row_id,
                    "settlement_bank_row_ids": allocated_settlement_ids,
                    "status": status,
                    "status_label": TURNOVER_STATUS_LABELS.get(status, status or "未知"),
                    "row_tone": ROW_TONES.get(status, "muted"),
                    "borrow_amount": self._format_money(borrow_amount),
                    "borrow_date": borrow_date,
                    "borrow_direction": borrow_direction,
                    "allocated_repayment_amount": self._format_money(repayment_amount),
                    "repayment_amount": self._format_money(repayment_amount),
                    "repayment_date": latest_repayment_date,
                    "repayment_direction": repayment_direction,
                    "balance_amount": self._format_money(balance_amount),
                    "counterparty_bank_name": self._counterparty_bank_name(
                        [principal_row, *allocated_settlement_rows]
                    ),
                    "repayment_remark": self._summary_text(allocated_settlement_rows),
                    "interest_rate_type": interest_rate_type,
                    "interest_rate_value": self._format_rate(interest_rate_value),
                    "interest_paid_amount": self._format_money(interest_paid_amount),
                    "loan_days": loan_days,
                    "accrued_interest": self._format_money(accrued_interest),
                    "interest_paid_date": self._empty_to_none(extra.get("interest_paid_date")),
                    "interest_payment_method": str(extra.get("interest_payment_method") or "").strip(),
                    "note": str(extra.get("note") or "").strip(),
                    "bank_row_ids": bank_row_ids,
                }
            )
        return lot_rows

    def _flow_row_payloads(
        self,
        relation: dict[str, Any],
        rows_by_id: dict[str, dict[str, Any]],
        allocation_lots: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        relation_id = str(relation.get("relation_id") or "")
        business_type = str(relation.get("business_type") or "")
        bank_row_ids = [
            str(row_id)
            for row_id in list(relation.get("bank_row_ids") or [])
            if str(row_id) in rows_by_id
        ]
        lot_ids_by_bank_row_id: dict[str, list[str]] = {}
        for lot in allocation_lots:
            lot_id = str(lot.get("lot_id") or "").strip()
            if not lot_id:
                continue
            for bank_row_id in [
                lot.get("principal_bank_row_id"),
                *list(lot.get("settlement_bank_row_ids") or []),
            ]:
                normalized = str(bank_row_id or "").strip()
                if not normalized:
                    continue
                lot_ids = lot_ids_by_bank_row_id.setdefault(normalized, [])
                if lot_id not in lot_ids:
                    lot_ids.append(lot_id)

        flow_rows: list[dict[str, Any]] = []
        seen_bank_row_ids: set[str] = set()
        for bank_row_id in bank_row_ids:
            if bank_row_id in seen_bank_row_ids:
                continue
            seen_bank_row_ids.add(bank_row_id)
            bank_row = rows_by_id[bank_row_id]
            direction = "income" if self._direction(bank_row) == "inflow" else "expense"
            flow_amount = self._row_amount(bank_row)
            transaction_at = self._transaction_at(bank_row)
            transaction_date = self._date_from_value(transaction_at)
            borrow_amount = flow_amount if direction == "income" else ZERO
            repayment_amount = flow_amount if direction == "expense" else ZERO
            allocated_lot_ids = lot_ids_by_bank_row_id.get(bank_row_id, [])
            flow_rows.append(
                {
                    "_flow_sort_key": self._row_fifo_sort_key(bank_row),
                    "row_kind": "flow",
                    "flow_id": f"bank:{bank_row_id}",
                    "relation_id": relation_id,
                    "source_bank_row_id": bank_row_id,
                    "transaction_at": transaction_at,
                    "flow_direction": direction,
                    "flow_amount": self._format_money(flow_amount),
                    "borrow_amount": self._format_money(borrow_amount),
                    "borrow_date": transaction_date if direction == "income" else None,
                    "repayment_amount": self._format_money(repayment_amount),
                    "repayment_date": transaction_date if direction == "expense" else None,
                    "business_type": business_type,
                    "category_code": str(bank_row.get("category_code") or "").strip(),
                    "category_label": str(bank_row.get("category_label") or "").strip(),
                    "category_label_path": list(bank_row.get("category_label_path") or []),
                    "category_version": int(bank_row.get("category_version") or 0),
                    "counterparty_bank_name": self._counterparty_bank_name([bank_row]),
                    "summary_text": self._summary_text([bank_row]),
                    "allocation_status": self._allocation_status(allocated_lot_ids),
                    "allocated_lot_ids": allocated_lot_ids,
                    "bank_row_ids": [bank_row_id],
                }
            )
        return flow_rows

    def _unclassified_item(self, row: dict[str, Any]) -> dict[str, Any]:
        row_id = self._row_id(row)
        amount = self._row_amount(row)
        direction = "income" if self._direction(row) == "inflow" else "expense"
        transaction_at = self._transaction_at(row)
        flow_row = {
            "row_kind": "flow",
            "flow_id": f"bank:{row_id}",
            "relation_id": f"turnover_pending_{row_id}",
            "source_bank_row_id": row_id,
            "status": "unclassified",
            "status_label": "待分类",
            "row_tone": "warning",
            "transaction_at": transaction_at,
            "flow_direction": direction,
            "flow_amount": self._format_money(amount),
            "borrow_amount": self._format_money(amount if direction == "income" else ZERO),
            "borrow_date": self._date_from_value(transaction_at) if direction == "income" else None,
            "borrow_direction": "income",
            "repayment_amount": self._format_money(amount if direction == "expense" else ZERO),
            "repayment_date": self._date_from_value(transaction_at) if direction == "expense" else None,
            "repayment_direction": "expense",
            "business_type": "",
            "category_code": str(row.get("category_code") or "").strip(),
            "category_label": str(row.get("category_label") or "外部往来款").strip(),
            "category_label_path": list(row.get("category_label_path") or []),
            "category_version": int(row.get("category_version") or 0),
            "counterparty_bank_name": self._counterparty_bank_name([row]),
            "summary_text": self._summary_text([row]),
            "allocation_status": "unclassified",
            "allocated_lot_ids": [],
            "bank_row_ids": [row_id],
        }
        grouped_row = {
            **flow_row,
            "row_kind": "summary",
            "display_level": "unclassified_summary",
            "balance_amount": self._format_money(amount),
            "interest_rate_type": "none",
            "interest_rate_value": self._format_rate(ZERO_RATE),
            "interest_paid_amount": self._format_money(ZERO),
            "loan_days": None,
            "accrued_interest": self._format_money(ZERO),
            "interest_paid_date": None,
            "interest_payment_method": "",
            "note": "",
        }
        return {
            "legacy": {
                "relation_id": grouped_row["relation_id"],
                "status": "unclassified",
                "family": "uncategorized",
                "family_label": "待分类",
                "counterparty_name": str(row.get("counterparty_name") or ""),
                "principal_amount": self._format_money(amount),
                "settled_amount": self._format_money(ZERO),
                "balance_amount": self._format_money(amount),
                "first_transaction_at": transaction_at,
                "last_settlement_at": None,
                "bank_account_labels": self._bank_account_labels([row]),
                "summary_text": self._summary_text([row]),
                "sync_to_workbench": False,
                "bank_row_ids": [row_id],
                "category_codes": ["external_turnover"],
                "business_type": "",
            },
            "row": grouped_row,
            "flow_rows": [flow_row],
            "allocation_lots": [],
            "family": "uncategorized",
            "status": "unclassified",
            "counterparty_name": str(row.get("counterparty_name") or ""),
            "business_type": "",
            "balance_amount": amount,
        }

    @staticmethod
    def _allocation_status(allocated_lot_ids: list[str]) -> str:
        return "allocated" if allocated_lot_ids else "unallocated"

    @staticmethod
    def _dedupe_flow_rows(flow_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped_rows: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for row in flow_rows:
            source_bank_row_id = str(row.get("source_bank_row_id") or "").strip()
            if not source_bank_row_id or source_bank_row_id in seen_source_ids:
                continue
            seen_source_ids.add(source_bank_row_id)
            deduped_rows.append(row)
        return deduped_rows

    def _group_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups_by_key: dict[tuple[str, str], dict[str, Any]] = {}
        for item in items:
            family = str(item.get("family") or "")
            counterparty_name = str(item.get("counterparty_name") or "")
            group = groups_by_key.setdefault(
                (family, counterparty_name),
                {
                    "group_id": f"counterparty:{family}:{counterparty_name}",
                    "counterparty_name": counterparty_name,
                    "family": family,
                    "family_label": TURNOVER_FAMILY_LABELS.get(family, family or "未知"),
                    "rows": [],
                    "lot_rows": [],
                    "flow_rows": [],
                    "allocation_lots": [],
                    "_items": [],
                    "_pending_repayment": ZERO,
                    "_pending_collection": ZERO,
                },
            )
            group["_items"].append(item)
            group["flow_rows"].extend(item.get("flow_rows") or [])
            group["allocation_lots"].extend(item.get("allocation_lots") or [])
            balance_amount = item.get("balance_amount")
            if not isinstance(balance_amount, Decimal):
                balance_amount = self._money(balance_amount)
            if balance_amount <= ZERO:
                continue
            business_type = str(item.get("business_type") or "")
            if business_type == "borrow_in":
                group["_pending_repayment"] += balance_amount
            elif business_type in {"borrow_out", "business_receivable"}:
                group["_pending_collection"] += balance_amount

        groups: list[dict[str, Any]] = []
        for group in groups_by_key.values():
            pending_repayment = group.pop("_pending_repayment")
            pending_collection = group.pop("_pending_collection")
            group_items = group.pop("_items")
            flow_rows = sorted(
                self._dedupe_flow_rows(list(group.get("flow_rows") or [])),
                key=lambda row: (
                    row.get("_flow_sort_key") or ("", ""),
                ),
            )
            for flow_row in flow_rows:
                flow_row.pop("_flow_sort_key", None)
            allocation_lots = sorted(
                list(group.get("allocation_lots") or []),
                key=lambda row: (
                    row.get("_lot_sort_key") or ("", ""),
                ),
            )
            for allocation_lot in allocation_lots:
                allocation_lot.pop("_lot_sort_key", None)
            group["flow_rows"] = flow_rows
            group["allocation_lots"] = allocation_lots
            group["lot_rows"] = allocation_lots
            summary_row = self._summary_row_payload(group_items, allocation_lots, flow_rows)
            group.update(self._group_pending_payload(pending_repayment, pending_collection))
            group["summary_row"] = summary_row
            group["rows"] = [summary_row]
            group["row_span"] = 1 + len(flow_rows)
            groups.append(group)
        return groups

    def _summary_row_payload(
        self,
        items: list[dict[str, Any]],
        allocation_lots: list[dict[str, Any]],
        flow_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        relation_rows = [dict(item.get("row") or {}) for item in items]
        relation_ids = self._unique_texts(row.get("relation_id") for row in relation_rows)
        amount_rows = allocation_lots or relation_rows
        balance_rows = allocation_lots or relation_rows
        borrow_amount = sum((self._money(row.get("borrow_amount")) for row in amount_rows), ZERO)
        repayment_amount = sum((self._money(row.get("repayment_amount")) for row in amount_rows), ZERO)
        balance_amount = sum((self._money(row.get("balance_amount")) for row in balance_rows), ZERO)
        accrued_interest = sum((self._money(row.get("accrued_interest")) for row in allocation_lots), ZERO)
        interest_paid_amount = sum(
            (self._money(row.get("interest_paid_amount")) for row in relation_rows),
            ZERO,
        )
        borrow_dates = self._unique_texts(row.get("borrow_date") for row in amount_rows)
        repayment_dates = self._unique_texts(row.get("repayment_date") for row in amount_rows)
        bank_row_ids: list[str] = []
        for row in relation_rows:
            for bank_row_id in list(row.get("bank_row_ids") or []):
                normalized = str(bank_row_id or "").strip()
                if normalized and normalized not in bank_row_ids:
                    bank_row_ids.append(normalized)
        status = self._first_text(row.get("status") for row in relation_rows)
        interest_rate_type = self._first_text(row.get("interest_rate_type") for row in relation_rows) or "none"
        interest_rate_value = self._first_text(
            row.get("interest_rate_value") for row in relation_rows
        ) or self._format_rate(ZERO_RATE)
        return {
            "row_kind": "summary",
            "display_level": "group_summary",
            "relation_id": relation_ids[0] if len(relation_ids) == 1 else "",
            "status": status,
            "status_label": TURNOVER_STATUS_LABELS.get(status, status or "未知"),
            "row_tone": ROW_TONES.get(status, "muted"),
            "borrow_amount": self._format_money(borrow_amount),
            "borrow_date": borrow_dates[0] if borrow_dates else None,
            "borrow_direction": self._first_text(row.get("borrow_direction") for row in relation_rows),
            "repayment_amount": self._format_money(repayment_amount),
            "repayment_date": repayment_dates[-1] if repayment_dates else None,
            "repayment_direction": self._first_text(row.get("repayment_direction") for row in relation_rows),
            "balance_amount": self._format_money(balance_amount),
            "counterparty_bank_name": " / ".join(
                self._unique_texts(row.get("counterparty_bank_name") for row in relation_rows)
            ),
            "repayment_remark": " / ".join(
                self._unique_texts(row.get("repayment_remark") for row in relation_rows)
            ),
            "interest_rate_type": interest_rate_type,
            "interest_rate_value": interest_rate_value,
            "interest_paid_amount": self._format_money(interest_paid_amount),
            "loan_days": None,
            "accrued_interest": self._format_money(accrued_interest),
            "interest_paid_date": self._first_text(row.get("interest_paid_date") for row in relation_rows) or None,
            "interest_payment_method": " / ".join(
                self._unique_texts(row.get("interest_payment_method") for row in relation_rows)
            ),
            "note": " / ".join(self._unique_texts(row.get("note") for row in relation_rows)),
            "bank_row_ids": bank_row_ids,
        }

    @classmethod
    def _row_fifo_sort_key(cls, row: dict[str, Any]) -> tuple[str, str]:
        return (str(cls._transaction_at(row) or ""), cls._row_id(row))

    @classmethod
    def _row_amount(cls, row: dict[str, Any]) -> Decimal:
        if cls._direction(row) == "inflow":
            amount = cls._money(row.get("credit_amount"))
        else:
            amount = cls._money(row.get("debit_amount"))
        if amount == ZERO:
            amount = cls._money(row.get("amount"))
        return amount

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()

    @staticmethod
    def _unique_texts(values: Any) -> list[str]:
        unique_values: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique_values.append(text)
        return unique_values

    @staticmethod
    def _first_text(values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @classmethod
    def _group_pending_payload(cls, pending_repayment: Decimal, pending_collection: Decimal) -> dict[str, str]:
        if pending_repayment > ZERO and pending_collection > ZERO:
            return {
                "pending_direction": "mixed",
                "pending_direction_label": "混合余额",
                "pending_amount": cls._format_money(pending_repayment + pending_collection),
                "group_tone": "warning",
            }
        if pending_repayment > ZERO:
            return {
                "pending_direction": "repayment",
                "pending_direction_label": "待还款",
                "pending_amount": cls._format_money(pending_repayment),
                "group_tone": "warning",
            }
        if pending_collection > ZERO:
            return {
                "pending_direction": "collection",
                "pending_direction_label": "待收款",
                "pending_amount": cls._format_money(pending_collection),
                "group_tone": "success",
            }
        return {
            "pending_direction": "closed",
            "pending_direction_label": "已闭合",
            "pending_amount": cls._format_money(ZERO),
            "group_tone": "muted",
        }

    @staticmethod
    def _chips(relation: dict[str, Any]) -> list[dict[str, str]]:
        status = str(relation.get("status") or "")
        chips = [
            {
                "label": TURNOVER_STATUS_LABELS.get(status, status or "未知"),
                "tone": ROW_TONES.get(status, "muted"),
            }
        ]
        source = str(relation.get("source") or "")
        if source == "manual":
            chips.append({"label": "人工", "tone": "info"})
        elif source == "system":
            chips.append({"label": "系统", "tone": "neutral"})
        if bool(relation.get("sync_to_workbench")):
            chips.append({"label": "同步关联台", "tone": "success"})
        evidence = relation.get("evidence")
        if isinstance(evidence, dict):
            reason = evidence.get("auto_confirm_reason") or evidence.get("conflict_reason")
            if reason:
                chips.append({"label": str(reason), "tone": "neutral"})
        return chips

    @staticmethod
    def _bank_account_labels(rows: list[dict[str, Any]]) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        for row in rows:
            bank = str(row.get("imported_bank_name") or row.get("bank_name") or "未知银行").strip() or "未知银行"
            last4 = str(row.get("imported_bank_last4") or row.get("account_last4") or "")[-4:]
            if not last4:
                last4 = str(row.get("account_no") or "")[-4:] or "unknown"
            label = f"{bank} {last4}"
            if label not in seen:
                seen.add(label)
                labels.append(label)
        return labels

    @staticmethod
    def _summary_text(rows: list[dict[str, Any]]) -> str:
        values: list[str] = []
        seen: set[str] = set()
        for row in rows:
            for key in ("summary", "remark", "purpose"):
                value = str(row.get(key) or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
            for field in list(row.get("bank_text_fields") or []):
                if not isinstance(field, dict):
                    continue
                value = str(field.get("value") or "").strip()
                if value and value not in seen:
                    seen.add(value)
                    values.append(value)
        return " / ".join(values)

    @staticmethod
    def _counterparty_bank_name(rows: list[dict[str, Any]]) -> str:
        for row in rows:
            value = str(row.get("counterparty_bank_name") or "").strip()
            if value:
                return value
        return ""

    @classmethod
    def _date_for_rows(cls, rows: list[dict[str, Any]], *, latest: bool = False) -> str | None:
        values = [
            value
            for value in (cls._date_from_value(cls._transaction_at(row)) for row in rows)
            if value is not None
        ]
        if not values:
            return None
        return sorted(values)[-1 if latest else 0]

    @staticmethod
    def _transaction_at(row: dict[str, Any]) -> str | None:
        for key in (
            "transaction_at",
            "pay_receive_time",
            "trade_time",
            "transaction_time",
            "txn_date",
            "date",
            "business_date",
        ):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _date_from_value(value: Any) -> str | None:
        text = str(value or "").strip()
        if len(text) < 10:
            return None
        candidate = text[:10]
        try:
            date.fromisoformat(candidate)
        except ValueError:
            return None
        return candidate

    def _grouped_loan_days(self, *, borrow_date: str | None, repayment_date: str | None) -> int | None:
        if not borrow_date:
            return None
        try:
            start = date.fromisoformat(borrow_date)
            end = date.fromisoformat(repayment_date) if repayment_date else self._today_provider()
        except ValueError:
            return None
        return max((end - start).days, 0)

    @staticmethod
    def _loan_days(relation: dict[str, Any]) -> int | None:
        first = str(relation.get("first_transaction_at") or "")[:10]
        last = str(relation.get("last_settlement_at") or "")[:10]
        if not first or not last:
            return None
        from datetime import date

        try:
            start = date.fromisoformat(first)
            end = date.fromisoformat(last)
        except ValueError:
            return None
        return max((end - start).days, 0)

    def _extra_for_relation(self, relation_id: str) -> dict[str, Any]:
        if self._extra_service is None:
            return {}
        getter = getattr(self._extra_service, "get", None)
        if not callable(getter):
            return {}
        extra = getter(relation_id)
        return dict(extra) if isinstance(extra, dict) else {}

    @staticmethod
    def _interest_rate_type(value: Any) -> str:
        normalized = str(value or "none").strip().lower()
        return normalized if normalized in {"annual", "monthly", "none"} else "none"

    @classmethod
    def _accrued_interest(
        cls,
        *,
        principal_amount: Decimal,
        interest_rate_type: str,
        interest_rate_value: Decimal,
        loan_days: int | None,
    ) -> Decimal:
        if interest_rate_type == "annual" and loan_days is not None:
            return principal_amount * interest_rate_value * Decimal(loan_days) / Decimal(365)
        if interest_rate_type == "monthly" and loan_days is not None:
            return principal_amount * interest_rate_value * Decimal(loan_days) / Decimal(30)
        return ZERO

    @staticmethod
    def _money_directions(business_type: str) -> tuple[str, str]:
        if business_type == "borrow_in":
            return "income", "expense"
        return "expense", "income"

    @staticmethod
    def _empty_to_none(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None

    @classmethod
    def _summary(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        pending_repayment = ZERO
        repaid = ZERO
        pending_collection = ZERO
        collected = ZERO
        closed = ZERO
        suggested_count = 0
        conflict_count = 0
        for row in rows:
            principal = cls._money(row.get("principal_amount"))
            settled = cls._money(row.get("settled_amount"))
            balance = cls._money(row.get("balance_amount"))
            business_type = str(row.get("business_type") or "")
            if business_type == "borrow_in":
                pending_repayment += max(balance, ZERO)
                repaid += settled
            elif business_type in {"borrow_out", "business_receivable"}:
                pending_collection += max(balance, ZERO)
                collected += settled
            if balance == ZERO and row.get("status") in {"deterministic", "confirmed"}:
                closed += principal
            if row.get("status") == "suggested":
                suggested_count += 1
            if row.get("status") == "conflict":
                conflict_count += 1
        return {
            "pending_repayment_amount": cls._format_money(pending_repayment),
            "repaid_amount": cls._format_money(repaid),
            "pending_collection_amount": cls._format_money(pending_collection),
            "collected_amount": cls._format_money(collected),
            "closed_amount": cls._format_money(closed),
            "suggested_count": suggested_count,
            "conflict_count": conflict_count,
            "row_count": len(rows),
        }

    @classmethod
    def _family_summary(cls, family: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        summary = cls._summary(rows)
        pending_amount = cls._money(summary.get("pending_repayment_amount")) + cls._money(
            summary.get("pending_collection_amount")
        )
        return {
            "family": family,
            "label": TURNOVER_FAMILY_LABELS.get(family, family),
            "pending_amount": cls._format_money(pending_amount),
            "closed_amount": summary["closed_amount"],
            "row_count": summary["row_count"],
        }

    @classmethod
    def _apply_filters(
        cls,
        rows: list[dict[str, Any]],
        *,
        family: str,
        direction: str,
        status: str | None,
    ) -> list[dict[str, Any]]:
        family_filter = cls._normalize_family(family)
        direction_filter = cls._normalize_direction_filter(direction)
        status_filter = cls._normalize_status(status)
        filtered = list(rows)
        if direction_filter != "all":
            filtered = [row for row in filtered if cls._direction_filter_value(str(row.get("business_type") or "")) == direction_filter]
        if family_filter != "all":
            filtered = [row for row in filtered if row.get("family") == family_filter]
        if status_filter:
            filtered = [row for row in filtered if row.get("status") == status_filter]
        return filtered

    @classmethod
    def _apply_item_filters(
        cls,
        items: list[dict[str, Any]],
        *,
        family: str,
        direction: str,
        status: str | None,
    ) -> list[dict[str, Any]]:
        family_filter = cls._normalize_family(family)
        direction_filter = cls._normalize_direction_filter(direction)
        status_filter = cls._normalize_status(status)
        filtered = list(items)
        if direction_filter != "all":
            filtered = [item for item in filtered if cls._direction_filter_value(str(item.get("business_type") or "")) == direction_filter]
        if family_filter != "all":
            filtered = [item for item in filtered if item.get("family") == family_filter]
        if status_filter:
            filtered = [item for item in filtered if item.get("status") == status_filter]
        return filtered

    @staticmethod
    def _normalize_family(family: str | None) -> str:
        normalized = str(family or "all").strip().lower()
        return normalized if normalized in VALID_FAMILY_FILTERS else "all"

    @staticmethod
    def _normalize_direction_filter(direction: str | None) -> str:
        normalized = str(direction or "all").strip().lower()
        return normalized if normalized in VALID_DIRECTION_FILTERS else "all"

    @staticmethod
    def _direction_filter_value(business_type: str) -> str:
        if business_type == "borrow_in":
            return "borrow_in"
        if business_type in {"borrow_out", "business_receivable"}:
            return "borrow_out"
        return "all"

    @staticmethod
    def _normalize_status(status: str | None) -> str | None:
        normalized = str(status or "").strip().lower()
        return normalized or None

    @staticmethod
    def _money(value: Any) -> Decimal:
        if value is None:
            return ZERO
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO
        try:
            return Decimal(text).quantize(MONEY_QUANT)
        except (InvalidOperation, ValueError):
            return ZERO

    @staticmethod
    def _rate(value: Any) -> Decimal:
        if value is None:
            return ZERO_RATE
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO_RATE
        try:
            amount = Decimal(text)
        except (InvalidOperation, ValueError):
            return ZERO_RATE
        if amount < ZERO:
            return ZERO_RATE
        return amount.quantize(RATE_QUANT)

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value.quantize(MONEY_QUANT):.2f}"

    @staticmethod
    def _format_rate(value: Decimal) -> str:
        return f"{value.quantize(RATE_QUANT):.6f}"
