from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Callable

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BankTransactionAutoCategoryService,
    resolve_effective_category,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_TRANSACTION_CATEGORY_LABELS,
    BANK_TRANSACTION_CATEGORY_COUNT_KEYS,
    BankTransactionCategoryService,
)

PURPOSE_TEXT_LABELS = ("用途", "交易用途")
SUMMARY_TEXT_LABELS = ("摘要",)
NOTE_TEXT_LABELS = ("备注", "附言", "客户附言")
UNCATEGORIZED_CATEGORY_FILTER_CODE = "uncategorized"


class BankDetailsService:
    def __init__(
        self,
        import_service: Any,
        *,
        category_service: BankTransactionCategoryService | None = None,
        auto_category_service: BankTransactionAutoCategoryService | None = None,
        relation_tag_provider: Callable[[str], dict[str, Any] | None] | None = None,
        relation_tag_batch_provider: Callable[[list[str]], dict[str, dict[str, Any]]] | None = None,
        fact_repository: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._category_service = category_service
        self._auto_category_service = auto_category_service
        self._relation_tag_provider = relation_tag_provider
        self._relation_tag_batch_provider = relation_tag_batch_provider
        self._fact_repository = fact_repository

    def list_accounts(self, *, date_from: str | None = None, date_to: str | None = None) -> dict[str, Any]:
        sql_account_loader = getattr(self._fact_repository, "list_bank_transaction_accounts", None)
        if callable(sql_account_loader):
            account_rows = list(sql_account_loader(date_from=date_from, date_to=date_to) or [])
            accounts = []
            for row in account_rows:
                account = self._account_payload(row)
                latest_balance = row.get("latest_balance")
                account["latest_balance"] = self._format_decimal(latest_balance) if latest_balance is not None else None
                account["latest_balance_at"] = self._date_text(row.get("latest_balance_at"))
                account["has_balance"] = latest_balance is not None
                account["transaction_count"] = int(row.get("transaction_count") or 0)
                accounts.append(account)
            sorted_accounts = sorted(accounts, key=lambda item: (item["bank_name"], item["account_last4"]))
            total_balance = sum(
                (Decimal(str(account["latest_balance"])) for account in sorted_accounts if account.get("has_balance")),
                Decimal("0.00"),
            )
            return {
                "accounts": sorted_accounts,
                "total_balance": self._format_decimal(total_balance) if any(account.get("has_balance") for account in sorted_accounts) else None,
                "balance_account_count": sum(1 for account in sorted_accounts if account.get("has_balance")),
                "missing_balance_account_count": sum(1 for account in sorted_accounts if not account.get("has_balance")),
            }
        transactions = self._transactions()
        filtered_counts: dict[str, int] = {}
        accounts: dict[str, dict[str, Any]] = {}
        for transaction in transactions:
            row = self._transaction_payload(transaction)
            account = self._account_payload(row)
            accounts.setdefault(account["account_key"], account)
            if self._date_in_range(row.get("trade_time") or row.get("txn_date"), date_from=date_from, date_to=date_to):
                filtered_counts[account["account_key"]] = filtered_counts.get(account["account_key"], 0) + 1

        for account_key, account in accounts.items():
            account_transactions = [
                self._transaction_payload(transaction)
                for transaction in transactions
                if self._account_key(self._transaction_payload(transaction)) == account_key
            ]
            latest = self._latest_balance_transaction(account_transactions)
            if latest is None:
                account["latest_balance"] = None
                account["latest_balance_at"] = None
                account["has_balance"] = False
            else:
                account["latest_balance"] = self._format_decimal(latest.get("balance"))
                account["latest_balance_at"] = self._date_text(latest.get("trade_time") or latest.get("txn_date"))
                account["has_balance"] = True
            account["transaction_count"] = filtered_counts.get(account_key, 0)

        sorted_accounts = sorted(accounts.values(), key=lambda item: (item["bank_name"], item["account_last4"]))
        total_balance = sum(
            (Decimal(str(account["latest_balance"])) for account in sorted_accounts if account.get("has_balance")),
            Decimal("0.00"),
        )
        return {
            "accounts": sorted_accounts,
            "total_balance": self._format_decimal(total_balance) if any(account.get("has_balance") for account in sorted_accounts) else None,
            "balance_account_count": sum(1 for account in sorted_accounts if account.get("has_balance")),
            "missing_balance_account_count": sum(1 for account in sorted_accounts if not account.get("has_balance")),
        }

    def list_transactions(
        self,
        *,
        account_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        category_code: str | None = None,
        category_primary_label: str | None = None,
        category_sub_label: str | None = None,
        category_third_label: str | None = None,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        normalized_page = max(int(page or 1), 1)
        normalized_page_size = min(max(int(page_size or 100), 1), 500)
        normalized_keyword = self._normalize_keyword(keyword)
        normalized_category_code = self._normalize_keyword(category_code)
        normalized_category_primary_label = self._normalize_keyword(category_primary_label)
        normalized_category_sub_label = self._normalize_keyword(category_sub_label)
        normalized_category_third_label = self._normalize_keyword(category_third_label)
        sql_page_loader = getattr(self._fact_repository, "list_bank_transactions_page", None)
        if callable(sql_page_loader):
            transactions, total = sql_page_loader(
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=normalized_keyword,
                category_code=normalized_category_code,
                category_primary_label=normalized_category_primary_label,
                category_sub_label=normalized_category_sub_label,
                category_third_label=normalized_category_third_label,
                page=normalized_page,
                page_size=normalized_page_size,
            )
            display_payloads = [self._transaction_payload(transaction) for transaction in transactions]
            auto_context_payloads = self._sql_auto_category_context_payloads(
                display_payloads,
                date_from=date_from,
                date_to=date_to,
            )
            auto_categories = self._auto_category_payloads(auto_context_payloads)
            relation_tags_by_id = self._relation_tag_relations(
                [str(payload.get("id") or "") for payload in display_payloads]
            )
            rows = [
                self.row_payload(
                    payload,
                    auto_category=auto_categories.get(str(payload.get("id") or "")),
                    relation=relation_tags_by_id.get(str(payload.get("id") or "")),
                )
                for payload in display_payloads
            ]
            return {
                "account_key": account_key,
                "date_from": date_from,
                "date_to": date_to,
                "rows": rows,
                "category_counts": self._category_counts(rows),
                "bank_transaction_tags": self._bank_transaction_tags_payload(),
                "pagination": {
                    "page": normalized_page,
                    "page_size": normalized_page_size,
                    "total": total,
                },
            }
        context_payloads: list[dict[str, Any]] = []
        display_payloads: list[dict[str, Any]] = []
        for transaction in self._transactions():
            payload = self._transaction_payload(transaction)
            if not self._date_in_range(payload.get("trade_time") or payload.get("txn_date"), date_from=date_from, date_to=date_to):
                continue
            context_payloads.append(payload)
            if account_key and self._account_key(payload) != account_key:
                continue
            display_payloads.append(payload)
        auto_categories = self._auto_category_payloads(context_payloads)
        relation_tags_by_id = self._relation_tag_relations(
            [str(payload.get("id") or "") for payload in display_payloads]
        )
        rows = [
            self.row_payload(
                payload,
                auto_category=auto_categories.get(str(payload.get("id") or "")),
                relation=relation_tags_by_id.get(str(payload.get("id") or "")),
            )
            for payload in display_payloads
        ]
        if normalized_keyword:
            rows = [row for row in rows if self._row_matches_keyword(row, normalized_keyword)]
        rows = [
            row for row in rows
            if self._row_matches_category_filters(
                row,
                category_code=normalized_category_code,
                category_primary_label=normalized_category_primary_label,
                category_sub_label=normalized_category_sub_label,
                category_third_label=normalized_category_third_label,
            )
        ]
        rows.sort(key=lambda item: str(item.get("trade_time") or ""), reverse=True)
        total = len(rows)
        start = (normalized_page - 1) * normalized_page_size
        end = start + normalized_page_size
        return {
            "account_key": account_key,
            "date_from": date_from,
            "date_to": date_to,
            "rows": rows[start:end],
            "category_counts": self._category_counts(rows),
            "bank_transaction_tags": self._bank_transaction_tags_payload(),
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": total,
            },
        }

    def _transactions(self) -> list[Any]:
        return list(self._import_service.list_transactions())

    def _transaction_payload(self, transaction: Any) -> dict[str, Any]:
        if is_dataclass(transaction):
            return asdict(transaction)
        return dict(transaction)

    def _account_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        bank_name = str(row.get("imported_bank_name") or row.get("bank_name") or "未知银行").strip() or "未知银行"
        account_last4 = str(row.get("imported_bank_last4") or row.get("account_last4") or "")[-4:] or str(row.get("account_no") or "")[-4:] or "unknown"
        account_key = self._account_key({**row, "imported_bank_name": bank_name, "imported_bank_last4": account_last4})
        return {
            "account_key": account_key,
            "bank_name": bank_name,
            "account_last4": account_last4,
            "display_name": f"{bank_name} {account_last4}",
            "latest_balance": None,
            "latest_balance_at": None,
            "has_balance": False,
            "transaction_count": 0,
        }

    def _account_key(self, row: dict[str, Any]) -> str:
        explicit_key = str(row.get("account_key") or "").strip()
        if explicit_key:
            return explicit_key
        bank_name = str(row.get("imported_bank_name") or row.get("bank_name") or "未知银行").strip() or "未知银行"
        account_last4 = str(row.get("imported_bank_last4") or row.get("account_last4") or "")[-4:] or str(row.get("account_no") or "")[-4:] or "unknown"
        normalized_bank = bank_name.lower().replace(" ", "-")
        return f"{normalized_bank}:{account_last4}"

    def _latest_balance_transaction(self, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        with_balance = [row for row in rows if row.get("balance") not in (None, "", "—")]
        if not with_balance:
            return None
        return max(with_balance, key=lambda row: str(row.get("trade_time") or row.get("txn_date") or ""))

    def row_payload(
        self,
        row: dict[str, Any],
        *,
        manual_category: dict[str, Any] | None = None,
        auto_category: dict[str, Any] | None = None,
        relation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        direction = self._direction(row)
        account = self._account_payload(row)
        manual_category = (
            dict(manual_category)
            if isinstance(manual_category, dict)
            else self._category_payload(str(row.get("id") or ""))
        )
        effective_category = resolve_effective_category(manual_category, auto_category)
        effective_code = effective_category["effective_category_code"]
        effective_label = effective_category["effective_category_label"]
        effective_path = list(effective_category["effective_category_path"] or [])
        effective_source = effective_category["effective_category_source"]
        manual_source = str(manual_category.get("source") or "")
        manual_confirmed_code = manual_category["category_code"] if manual_source == "auto_confirmation" else None
        auto_status = str(auto_category.get("category_resolution_status") or "") if isinstance(auto_category, dict) else ""
        category_resolution_status = (
            "manual_confirmed"
            if manual_confirmed_code or effective_source in {"manual", "manual_confirmation"}
            else (auto_status or "unmatched")
        )
        relation_tags = self._relation_tag_payload(relation)
        text_fields = self._bank_text_display_fields(row)
        return {
            "id": str(row.get("id") or ""),
            "trade_time": self._trade_time_text(row.get("trade_time") or row.get("txn_date")),
            "counterparty_name": str(row.get("counterparty_name_raw") or row.get("counterparty_name") or ""),
            "direction": direction,
            "direction_label": "收" if direction == "income" else "支",
            "amount": self._format_decimal(row.get("amount")),
            "balance": self._format_decimal(row.get("balance")) if row.get("balance") is not None else None,
            "summary": text_fields["summary_text"],
            "purpose": text_fields["purpose_text"] or text_fields["note_text"],
            "purpose_text": text_fields["purpose_text"],
            "summary_text": text_fields["summary_text"],
            "note_text": text_fields["note_text"],
            "bank_name": account["bank_name"],
            "account_last4": account["account_last4"],
            "manual_category_code": manual_category["category_code"],
            "manual_category_label": manual_category["category_label"],
            "manual_category_primary_label": manual_category.get("category_primary_label"),
            "manual_category_sub_label": manual_category.get("category_sub_label"),
            "manual_category_third_label": manual_category.get("category_third_label"),
            "manual_category_label_path": list(manual_category.get("category_label_path") or []),
            "manual_category_path": list(manual_category.get("category_path") or []),
            "manual_category_source": str(manual_category.get("source") or ""),
            "manual_category_version": manual_category["category_version"],
            "manual_confirmed_category_code": manual_confirmed_code,
            "auto_category_code": auto_category.get("category_code") if isinstance(auto_category, dict) else None,
            "auto_category_label": auto_category.get("category_label") if isinstance(auto_category, dict) else None,
            "auto_category_primary_label": auto_category.get("category_primary_label") if isinstance(auto_category, dict) else None,
            "auto_category_sub_label": auto_category.get("category_sub_label") if isinstance(auto_category, dict) else None,
            "auto_category_third_label": auto_category.get("category_third_label") if isinstance(auto_category, dict) else None,
            "auto_category_label_path": list(auto_category.get("category_label_path") or []) if isinstance(auto_category, dict) else [],
            "auto_category_path": list(auto_category.get("category_path") or []) if isinstance(auto_category, dict) else [],
            "auto_category_source": str(auto_category.get("source") or "") if isinstance(auto_category, dict) else "",
            "auto_category_reason": str(auto_category.get("reason") or "") if isinstance(auto_category, dict) else "",
            "auto_category_confidence": str(auto_category.get("confidence") or "") if isinstance(auto_category, dict) else "",
            "auto_category_evidence": dict(auto_category.get("auto_category_evidence") or {}) if isinstance(auto_category, dict) else {},
            "auto_candidate_category_codes": list(auto_category.get("auto_candidate_category_codes") or []) if isinstance(auto_category, dict) else [],
            "auto_candidate_categories": list(auto_category.get("auto_candidate_categories") or []) if isinstance(auto_category, dict) else [],
            "internal_transfer_counterpart": (
                dict(auto_category.get("internal_transfer_counterpart"))
                if isinstance(auto_category, dict)
                and isinstance(auto_category.get("internal_transfer_counterpart"), dict)
                else None
            ),
            "category_resolution_status": category_resolution_status,
            "category_rule_version": str(auto_category.get("rule_version") or manual_category.get("category_rule_version") or "") if isinstance(auto_category, dict) else str(manual_category.get("category_rule_version") or ""),
            "effective_category_code": effective_code,
            "effective_category_label": effective_label,
            "effective_category_primary_label": effective_category.get("effective_category_primary_label"),
            "effective_category_sub_label": effective_category.get("effective_category_sub_label"),
            "effective_category_third_label": effective_category.get("effective_category_third_label"),
            "effective_category_label_path": list(effective_category.get("effective_category_label_path") or []),
            "effective_category_path": effective_path,
            "effective_category_source": effective_source,
            "category_code": effective_code,
            "category_label": effective_label,
            "category_primary_label": effective_category.get("effective_category_primary_label"),
            "category_sub_label": effective_category.get("effective_category_sub_label"),
            "category_third_label": effective_category.get("effective_category_third_label"),
            "category_label_path": list(effective_category.get("effective_category_label_path") or []),
            "category_path": effective_path,
            "category_source": effective_source,
            "category_version": manual_category["category_version"],
            "turnover_role": effective_category.get("turnover_role"),
            "turnover_action_type": effective_category.get("turnover_action_type"),
            "turnover_family": effective_category.get("turnover_family"),
            **relation_tags,
        }

    def _category_payload(self, transaction_id: str) -> dict[str, Any]:
        if self._category_service is None:
            return {"category_code": None, "category_label": None, "category_path": [], "category_version": 0}
        return self._category_service.get(transaction_id)

    def _auto_category_payloads(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if self._auto_category_service is None:
            return {}
        return self._auto_category_service.suggestions_by_transaction_id(
            [self._auto_category_input_row(row) for row in rows]
        )

    def _sql_auto_category_context_payloads(
        self,
        display_payloads: list[dict[str, Any]],
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> list[dict[str, Any]]:
        context_loader = getattr(self._fact_repository, "list_bank_transactions_auto_category_context", None)
        if not callable(context_loader):
            return list(display_payloads)
        context_date_from, context_date_to = _auto_category_context_date_range(date_from=date_from, date_to=date_to)
        context_rows = context_loader(date_from=context_date_from, date_to=context_date_to)
        context_payloads = [self._transaction_payload(transaction) for transaction in list(context_rows or [])]
        payloads_by_id = {
            str(payload.get("id") or ""): payload
            for payload in context_payloads
            if str(payload.get("id") or "").strip()
        }
        for payload in display_payloads:
            transaction_id = str(payload.get("id") or "").strip()
            if transaction_id:
                payloads_by_id.setdefault(transaction_id, payload)
        return list(payloads_by_id.values()) or list(display_payloads)

    def auto_category_input_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return self._auto_category_input_row(row)

    def _auto_category_input_row(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = dict(row)
        direction = self._direction(row)
        amount = self._format_decimal(row.get("amount"))
        payload["counterparty_name"] = str(row.get("counterparty_name") or row.get("counterparty_name_raw") or "")
        payload["debit_amount"] = amount if direction == "expense" else ""
        payload["credit_amount"] = amount if direction == "income" else ""
        payload["pay_receive_time"] = str(row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date") or "")
        return payload

    def _relation_tag_relations(self, transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        normalized_ids = [str(transaction_id).strip() for transaction_id in transaction_ids if str(transaction_id).strip()]
        if not normalized_ids:
            return {}
        if self._relation_tag_batch_provider is not None:
            try:
                relations = self._relation_tag_batch_provider(normalized_ids)
            except Exception:
                return {}
            return {
                str(transaction_id).strip(): dict(relation)
                for transaction_id, relation in dict(relations or {}).items()
                if str(transaction_id).strip() and isinstance(relation, dict)
            }
        if self._relation_tag_provider is None:
            return {}
        relations: dict[str, dict[str, Any]] = {}
        for transaction_id in normalized_ids:
            try:
                relation = self._relation_tag_provider(transaction_id)
            except Exception:
                continue
            if isinstance(relation, dict):
                relations[transaction_id] = dict(relation)
        return relations

    def _relation_tag_payload(self, relation: dict[str, Any] | None) -> dict[str, Any]:
        if isinstance(relation, dict):
            relation_status = str(relation.get("relation_status") or "linked").strip() or "linked"
            if relation_status != "linked":
                relation = None
        row_types = set()
        if isinstance(relation, dict):
            row_types = {
                str(row_type).strip()
                for row_type in list(relation.get("row_types") or [])
                if str(row_type).strip()
            }
        relation_status = "linked" if isinstance(relation, dict) else "unlinked"
        oa_relation_tag = "有oa" if "oa" in row_types else "无oa"
        invoice_relation_tag = "有发票" if "invoice" in row_types else "无发票"
        payload: dict[str, Any] = {
            "oa_relation_tag": oa_relation_tag,
            "invoice_relation_tag": invoice_relation_tag,
            "relation_tags": [oa_relation_tag, invoice_relation_tag],
        }
        payload["relation_status"] = relation_status
        if isinstance(relation, dict) and str(relation.get("case_id") or "").strip():
            payload["relation_case_id"] = str(relation.get("case_id") or "").strip()
        return payload

    def _category_counts(self, rows: list[dict[str, Any]]) -> dict[str, int]:
        if self._category_service is not None:
            counts = {key: 0 for key in self._category_service.tag_count_keys()}
        else:
            counts = {key: 0 for key in BANK_TRANSACTION_CATEGORY_COUNT_KEYS}
        for row in rows:
            category_code = row.get("effective_category_code")
            if self._has_category_definition(category_code):
                counts.setdefault(str(category_code), 0)
                counts[str(category_code)] += 1
            else:
                counts["uncategorized"] += 1
        return counts

    def _has_category_definition(self, category_code: Any) -> bool:
        if self._category_service is not None:
            return self._category_service.has_tag_definition(
                str(category_code) if category_code is not None else None
            )
        return category_code in BANK_TRANSACTION_CATEGORY_LABELS

    def _bank_transaction_tags_payload(self) -> dict[str, Any]:
        if self._category_service is None:
            return {"version": 1, "definitions": []}
        return self._category_service.tag_dictionary_payload()

    @classmethod
    def _row_matches_keyword(cls, row: dict[str, Any], keyword: str) -> bool:
        haystack = " ".join(cls._search_text_values(row)).lower()
        return keyword.lower() in haystack

    @staticmethod
    def _row_matches_category_filters(
        row: dict[str, Any],
        *,
        category_code: str,
        category_primary_label: str,
        category_sub_label: str,
        category_third_label: str,
    ) -> bool:
        if category_code:
            effective_category_code = str(row.get("effective_category_code") or "").strip()
            if category_code == UNCATEGORIZED_CATEGORY_FILTER_CODE:
                if effective_category_code:
                    return False
            elif effective_category_code != category_code:
                return False
        if category_primary_label and str(row.get("effective_category_primary_label") or "").strip() != category_primary_label:
            return False
        if category_sub_label and str(row.get("effective_category_sub_label") or "").strip() != category_sub_label:
            return False
        if category_third_label and str(row.get("effective_category_third_label") or "").strip() != category_third_label:
            return False
        return True

    @classmethod
    def _search_text_values(cls, row: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in (
            "counterparty_name",
            "trade_time",
            "direction_label",
            "amount",
            "balance",
            "summary",
            "purpose",
            "purpose_text",
            "summary_text",
            "note_text",
            "bank_name",
            "account_last4",
            "manual_category_label",
            "manual_category_primary_label",
            "manual_category_sub_label",
            "manual_category_third_label",
            "auto_category_label",
            "auto_category_primary_label",
            "auto_category_sub_label",
            "auto_category_third_label",
            "effective_category_label",
            "effective_category_primary_label",
            "effective_category_sub_label",
            "effective_category_third_label",
            "category_label",
            "category_primary_label",
            "category_sub_label",
            "category_third_label",
            "oa_relation_tag",
            "invoice_relation_tag",
        ):
            cls._append_search_value(values, row.get(key))
        for key in (
            "manual_category_path",
            "manual_category_label_path",
            "auto_category_path",
            "auto_category_label_path",
            "effective_category_path",
            "effective_category_label_path",
            "category_path",
            "category_label_path",
            "relation_tags",
        ):
            cls._append_search_value(values, row.get(key))
        return values

    @classmethod
    def _append_search_value(cls, values: list[str], value: Any) -> None:
        if value is None:
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                cls._append_search_value(values, item)
            return
        text = str(value).strip()
        if text:
            values.append(text)

    @staticmethod
    def _normalize_keyword(value: str | None) -> str:
        return str(value or "").strip()

    @staticmethod
    def _direction(row: dict[str, Any]) -> str:
        direction = row.get("txn_direction")
        value = direction.value if isinstance(direction, TransactionDirection) else str(direction or "")
        return "income" if value == TransactionDirection.INFLOW.value else "expense"

    @staticmethod
    def _date_in_range(value: Any, *, date_from: str | None, date_to: str | None) -> bool:
        date_text = BankDetailsService._date_text(value)
        if date_from and date_text < date_from:
            return False
        if date_to and date_text > date_to:
            return False
        return True

    @staticmethod
    def _date_text(value: Any) -> str:
        if isinstance(value, datetime):
            return value.date().isoformat()
        text = str(value or "").strip()
        return text[:10]

    @classmethod
    def _bank_text_display_fields(cls, row: dict[str, Any]) -> dict[str, str]:
        fields_by_label = cls._bank_text_fields_by_label(row.get("bank_text_fields"))
        summary_text = cls._first_field_value(fields_by_label, SUMMARY_TEXT_LABELS)
        purpose_text = cls._first_field_value(fields_by_label, PURPOSE_TEXT_LABELS)
        note_text = cls._first_field_value(fields_by_label, NOTE_TEXT_LABELS)
        if not fields_by_label:
            summary_text = str(row.get("summary") or "")
            purpose_text = str(row.get("purpose") or "")
            note_text = str(row.get("remark") or "")
        return {
            "purpose_text": purpose_text.strip(),
            "summary_text": summary_text.strip(),
            "note_text": note_text.strip(),
        }

    @staticmethod
    def _bank_text_fields_by_label(value: Any) -> dict[str, str]:
        fields: dict[str, str] = {}
        if isinstance(value, dict):
            iterable = [{"label": label, "value": field_value} for label, field_value in value.items()]
        else:
            iterable = list(value or []) if isinstance(value, list) else []
        for item in iterable:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            text = str(item.get("value") or "").strip()
            if label and text and label not in fields:
                fields[label] = text
        return fields

    @staticmethod
    def _first_field_value(fields_by_label: dict[str, str], labels: tuple[str, ...]) -> str:
        for label in labels:
            value = fields_by_label.get(label)
            if value:
                return value
        return ""

    @staticmethod
    def _trade_time_text(value: Any) -> str:
        if isinstance(value, datetime):
            return value.replace(tzinfo=None).isoformat(sep=" ")
        text = str(value or "").strip().replace("T", " ")
        if len(text) >= 25 and text[19] in {"+", "-"} and text[20:22].isdigit() and text[23:25].isdigit():
            return text[:19]
        if text.endswith("Z") and len(text) >= 20:
            return text[:19]
        return text

    @staticmethod
    def _format_decimal(value: Any) -> str:
        return f"{Decimal(str(value)):.2f}"


def _auto_category_context_date_range(*, date_from: str | None, date_to: str | None) -> tuple[str | None, str | None]:
    return _shift_iso_date(date_from, days=-2), _shift_iso_date(date_to, days=2)


def _shift_iso_date(value: str | None, *, days: int) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return text
    return (parsed + timedelta(days=days)).isoformat()
