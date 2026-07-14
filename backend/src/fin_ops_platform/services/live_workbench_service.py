from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Invoice, MatchingResult
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_LABELS
from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService


ZERO = Decimal("0.00")
DEFAULT_COMPANY_NAME = "溯源科技有限公司"
LEGACY_DEMO_TRANSACTION_SOURCES = {"bank_transaction.json"}
INTERNAL_TRANSFER_RULE_CODE = "internal_transfer_pair"
DEFAULT_BANK_TEXT_FIELD_LABELS = ("摘要", "备注", "用途", "交易用途", "客户附言", "附言")


class LiveWorkbenchService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        matching_service: MatchingEngineService,
        *,
        bank_account_resolver: BankAccountResolver | None = None,
        category_provider: Any | None = None,
        bank_text_fields: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        self._import_service = import_service
        self._matching_service = matching_service
        self._bank_account_resolver = bank_account_resolver or BankAccountResolver()
        self._category_provider = category_provider
        self._bank_text_field_labels = tuple(
            label for label in (bank_text_fields or DEFAULT_BANK_TEXT_FIELD_LABELS) if isinstance(label, str) and label.strip()
        )
        self._detail_rows_by_id: dict[str, dict[str, Any]] = {}
        self._company_identity: tuple[str, str | None] = (DEFAULT_COMPANY_NAME, None)

    def has_rows_for_month(self, month: str) -> bool:
        if month == "all":
            return bool([invoice for invoice in self._import_service.list_invoices(month="all") if self._invoice_is_workbench_visible(invoice)] or self._import_service.list_transactions(month="all"))
        return any(
            invoice.invoice_date and invoice.invoice_date.startswith(month)
            for invoice in self._import_service.list_invoices(month=month)
            if self._invoice_is_workbench_visible(invoice)
        ) or any(
            transaction.txn_date and transaction.txn_date.startswith(month) for transaction in self._import_service.list_transactions(month=month)
        )

    def get_workbench(self, month: str) -> dict[str, Any]:
        self._rebuild_cache(month=month)

        paired: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        unpaired: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}

        for row in self._detail_rows_by_id.values():
            row_month = row.get("_month")
            if month != "all" and row_month != month:
                continue
            (paired if row["_section"] == "paired" else unpaired)[row["type"]].append(self._serialize_row(row))

        month_rows = [*paired["bank"], *paired["invoice"], *unpaired["bank"], *unpaired["invoice"]]
        return {
            "month": month,
            "summary": {
                "oa_count": 0,
                "bank_count": len(paired["bank"]) + len(unpaired["bank"]),
                "invoice_count": len(paired["invoice"]) + len(unpaired["invoice"]),
                "paired_count": len(paired["bank"]) + len(paired["invoice"]),
                "unpaired_count": len(unpaired["bank"]) + len(unpaired["invoice"]),
                "exception_count": sum(1 for row in month_rows if row.get("invoice_relation", row.get("invoice_bank_relation", {})).get("tone") == "danger"),
            },
            "paired": paired,
            "unpaired": unpaired,
        }

    def get_row_detail(self, row_id: str) -> dict[str, Any]:
        rows = self.get_rows_detail([row_id])
        row = rows.get(row_id)
        if row is None:
            raise KeyError(row_id)
        return payload_from_cache_row(row)

    def get_rows_detail(self, row_ids: list[str]) -> dict[str, dict[str, Any]]:
        result_by_object_id = self._existing_results_by_object_id()
        self._company_identity = self._resolve_company_identity()
        excluded_transaction_batch_ids = self._excluded_transaction_batch_ids()
        payload: dict[str, dict[str, Any]] = {}
        for row_id in row_ids:
            normalized_row_id = str(row_id)
            row = self._build_detail_row_by_id(
                normalized_row_id,
                result_by_object_id=result_by_object_id,
                excluded_transaction_batch_ids=excluded_transaction_batch_ids,
            )
            if row is not None:
                payload[normalized_row_id] = row
        return payload

    def get_case_rows(self, case_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        self._rebuild_cache()
        rows: list[dict[str, Any]] = []
        for row in self._detail_rows_by_id.values():
            if row.get("case_id") != case_id:
                continue
            row_month = row.get("_month")
            if month not in (None, "", "all") and row_month != month:
                continue
            payload = self._serialize_row(row)
            payload["summary_fields"] = dict(row["_summary_fields"])
            payload["detail_fields"] = dict(row["_detail_fields"])
            rows.append(payload)
        return rows

    def _build_detail_row_by_id(
        self,
        row_id: str,
        *,
        result_by_object_id: dict[str, MatchingResult],
        excluded_transaction_batch_ids: set[str],
    ) -> dict[str, Any] | None:
        try:
            invoice = self._import_service.get_invoice(row_id)
        except KeyError:
            invoice = None
        if invoice is not None:
            if not self._invoice_is_workbench_visible(invoice):
                return None
            return self._build_invoice_row(invoice, result_by_object_id.get(row_id))

        try:
            transaction = self._import_service.get_transaction(row_id)
        except KeyError:
            return None
        if transaction.source_batch_id in excluded_transaction_batch_ids:
            return None
        category = self._category_for_transaction(transaction)
        return self._build_bank_row(transaction, result_by_object_id.get(row_id), category=category)

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def _build_bank_row(
        self,
        transaction: BankTransaction,
        result: MatchingResult | None,
        *,
        category: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        relation = unlinked_relation_payload()
        section = "unpaired"
        payment_account_label = self._bank_account_resolver.resolve_label(
            transaction.account_no,
            transaction.account_name,
            preferred_bank_name=transaction.imported_bank_name,
            preferred_last4=transaction.imported_bank_last4,
        )
        direction_label = "支出" if transaction.txn_direction.value == "outflow" else "收入"
        account_field_label = "支付账户" if transaction.txn_direction.value == "outflow" else "收款账户"
        remark_value = self._build_bank_remark(transaction, result)
        category_payload = self._normalize_category_record(category)
        tags = self._bank_row_tags(transaction, category_payload)
        bank_text_fields = self._build_bank_text_fields(transaction)
        return {
            "id": transaction.id,
            "type": "bank",
            "case_id": None,
            "direction": direction_label,
            "account_no": transaction.account_no,
            "account_name": transaction.account_name,
            "counterparty_account_no": transaction.counterparty_account_no,
            "trade_time": transaction.trade_time,
            "debit_amount": format_decimal(transaction.amount) if transaction.txn_direction.value == "outflow" else "",
            "credit_amount": format_decimal(transaction.amount) if transaction.txn_direction.value == "inflow" else "",
            "counterparty_name": transaction.counterparty_name_raw,
            "payment_account_label": payment_account_label,
            "invoice_relation": relation,
            "pay_receive_time": transaction.pay_receive_time or transaction.trade_time,
            "summary": transaction.summary,
            "remark": remark_value,
            "category_code": category_payload.get("category_code") if category_payload else None,
            "category_label": category_payload.get("category_label") if category_payload else None,
            "category_path": list(category_payload.get("category_path") or []) if category_payload else [],
            "category_primary_label": category_payload.get("category_primary_label") if category_payload else None,
            "category_sub_label": category_payload.get("category_sub_label") if category_payload else None,
            "category_label_path": list(category_payload.get("category_label_path") or []) if category_payload else [],
            "category_source": category_payload.get("category_source") if category_payload else None,
            "tags": tags,
            "bank_text_fields": bank_text_fields,
            "repayment_date": "",
            "available_actions": self._available_actions("bank", section),
            "_month": transaction.txn_date[:7] if transaction.txn_date else "",
            "_section": section,
            "_summary_fields": {
                "资金方向": direction_label,
                "交易时间": transaction.trade_time or "--",
                "借方发生额": format_decimal(transaction.amount) if transaction.txn_direction.value == "outflow" else "—",
                "贷方发生额": format_decimal(transaction.amount) if transaction.txn_direction.value == "inflow" else "—",
                "对方户名": transaction.counterparty_name_raw,
                account_field_label: payment_account_label,
                "和发票关联情况": relation["label"],
                "支付/收款时间": transaction.pay_receive_time or transaction.trade_time or "--",
                "备注": remark_value or "—",
                "还借款日期": "—",
            },
            "_detail_fields": {
                "资金方向": direction_label,
                "账号": transaction.account_no,
                "账户名称": transaction.account_name or "—",
                "余额": format_decimal(transaction.balance) if transaction.balance is not None else "—",
                "币种": transaction.currency or "CNY",
                "对方账号": transaction.counterparty_account_no or "—",
                "对方开户机构": transaction.counterparty_bank_name or "—",
                "记账日期": transaction.booked_date or transaction.txn_date or "—",
                "摘要": transaction.summary or "—",
                "备注": remark_value or "—",
                "账户明细编号-交易流水号": transaction.account_detail_no or "—",
                "企业流水号": transaction.enterprise_serial_no or "—",
                "凭证种类": transaction.voucher_kind or "—",
                "凭证号": transaction.voucher_no or "—",
            },
        }

    def _build_invoice_row(self, invoice: Invoice, result: MatchingResult | None) -> dict[str, Any]:
        relation = unlinked_relation_payload()
        section = "unpaired"
        seller_name, buyer_name = self._resolve_invoice_parties(invoice)
        seller_tax_no, buyer_tax_no = self._resolve_invoice_tax_nos(invoice)
        return {
            "id": invoice.id,
            "type": "invoice",
            "case_id": None,
            "seller_tax_no": seller_tax_no,
            "seller_name": seller_name,
            "buyer_tax_no": buyer_tax_no,
            "buyer_name": buyer_name,
            "invoice_code": invoice.invoice_code or "—",
            "invoice_no": invoice.invoice_no or "—",
            "digital_invoice_no": invoice.digital_invoice_no or "—",
            "issue_date": invoice.invoice_date,
            "amount": format_decimal(invoice.amount),
            "tax_rate": invoice.tax_rate or "—",
            "tax_amount": format_decimal(invoice.tax_amount) if invoice.tax_amount is not None else "—",
            "total_with_tax": format_decimal(invoice.total_with_tax) if invoice.total_with_tax is not None else "—",
            "invoice_type": "销项发票" if invoice.invoice_type.value == "output" else "进项发票",
            "invoice_bank_relation": relation,
            "source_kind": "etc_invoice" if "ETC" in list(getattr(invoice, "tags", []) or []) else "manual_invoice",
            "tags": list(getattr(invoice, "tags", []) or []),
            "etc_invoice_id": getattr(invoice, "etc_invoice_id", None),
            "etc_import_batch_id": getattr(invoice, "etc_import_batch_id", None),
            "etc_submission_batch_id": getattr(invoice, "etc_submission_batch_id", None),
            "etc_submission_status": getattr(invoice, "etc_submission_status", None),
            "available_actions": self._available_actions("invoice", section),
            "_month": invoice.invoice_date[:7] if invoice.invoice_date else "",
            "_section": section,
            "_summary_fields": {
                "销方识别号": seller_tax_no or "—",
                "销方名称": seller_name or "—",
                "购方识别号": buyer_tax_no or "—",
                "购买方名称": buyer_name or "—",
                "开票日期": invoice.invoice_date or "—",
                "金额": format_decimal(invoice.amount),
                "税率": invoice.tax_rate or "—",
                "税额": format_decimal(invoice.tax_amount) if invoice.tax_amount is not None else "—",
                "价税合计": format_decimal(invoice.total_with_tax) if invoice.total_with_tax is not None else "—",
                "发票类型": "销项发票" if invoice.invoice_type.value == "output" else "进项发票",
            },
            "_detail_fields": {
                "序号": invoice.id,
                "发票代码": invoice.invoice_code or "—",
                "发票号码": invoice.invoice_no or "—",
                "数电发票号码": invoice.digital_invoice_no or "—",
                "税收分类编码": invoice.tax_classification_code or "—",
                "特定业务类型": invoice.specific_business_type or "—",
                "货物或应税劳务名称": invoice.taxable_item_name or "—",
                "规格型号": invoice.specification_model or "—",
                "单位": invoice.unit or "—",
                "数量": format_decimal(invoice.quantity) if invoice.quantity is not None else "—",
                "单价": format_decimal(invoice.unit_price) if invoice.unit_price is not None else "—",
                "发票来源": invoice.invoice_source or "—",
                "发票票种": invoice.invoice_kind or "—",
                "发票状态": invoice.invoice_status_from_source or "—",
                "是否正数发票": invoice.is_positive_invoice or "—",
                "发票风险等级": invoice.risk_level or "—",
                "开票人": invoice.issuer or "—",
                "备注": invoice.remark or "—",
                "标签": "、".join(list(getattr(invoice, "tags", []) or [])) or "—",
                "ETC导入批次": getattr(invoice, "etc_import_batch_id", None) or "—",
                "ETC提交批次": getattr(invoice, "etc_submission_batch_id", None) or "—",
            },
        }

    def _rebuild_cache(self, *, month: str = "all") -> None:
        self._company_identity = self._resolve_company_identity()
        excluded_transaction_batch_ids = self._excluded_transaction_batch_ids()
        result_by_object_id = self._existing_results_by_object_id()
        self._detail_rows_by_id = {}
        for invoice in self._import_service.list_invoices(month=month):
            if not self._invoice_is_workbench_visible(invoice):
                continue
            self._detail_rows_by_id[invoice.id] = self._build_invoice_row(invoice, result_by_object_id.get(invoice.id))
        transactions = [
            transaction
            for transaction in self._import_service.list_transactions(month=month)
            if transaction.source_batch_id not in excluded_transaction_batch_ids
        ]
        categories_by_transaction_id = self._categories_for_transactions(transactions)
        for transaction in transactions:
            if transaction.source_batch_id in excluded_transaction_batch_ids:
                continue
            self._detail_rows_by_id[transaction.id] = self._build_bank_row(
                transaction,
                result_by_object_id.get(transaction.id),
                category=categories_by_transaction_id.get(transaction.id),
            )

    def _existing_results_by_object_id(self) -> dict[str, MatchingResult]:
        latest_run = self._matching_service.latest_run()
        result_by_object_id: dict[str, MatchingResult] = {}
        if latest_run is None:
            return result_by_object_id

        for result in latest_run.results:
            for invoice_id in result.invoice_ids:
                result_by_object_id[invoice_id] = result
            for transaction_id in result.transaction_ids:
                result_by_object_id[transaction_id] = result
        return result_by_object_id

    def _build_bank_remark(self, transaction: BankTransaction, result: MatchingResult | None) -> str:
        base_remark = (transaction.remark or transaction.summary or "").strip()
        if result is None or result.rule_code != INTERNAL_TRANSFER_RULE_CODE:
            return base_remark

        counterpart = self._internal_transfer_counterpart_transaction(transaction.id, result)
        if counterpart is None:
            return base_remark

        counterpart_account_label = self._compact_bank_account_label(
            counterpart.account_no,
            counterpart.account_name,
            preferred_bank_name=counterpart.imported_bank_name,
            preferred_last4=counterpart.imported_bank_last4,
        )
        if not counterpart_account_label:
            return base_remark

        counterpart_prefix = "支付账户" if transaction.txn_direction == TransactionDirection.INFLOW else "收款账户"
        counterpart_text = f"{counterpart_prefix}：{counterpart_account_label}"
        if not base_remark:
            return counterpart_text
        if counterpart_text in base_remark:
            return base_remark
        return f"{base_remark}；{counterpart_text}"

    def _category_for_transaction(self, transaction: BankTransaction) -> dict[str, Any] | None:
        return self._categories_for_transactions([transaction]).get(transaction.id)

    def _categories_for_transactions(self, transactions: list[Any]) -> dict[str, dict[str, str]]:
        provider = self._category_provider
        if provider is None or not transactions:
            return {}

        transaction_ids = [
            str(getattr(transaction, "id", transaction) or "").strip()
            for transaction in transactions
            if str(getattr(transaction, "id", transaction) or "").strip()
        ]
        if not transaction_ids:
            return {}

        raw_records: Any
        category_records_by_transaction_ids = getattr(provider, "category_records_by_transaction_ids", None)
        if callable(category_records_by_transaction_ids):
            raw_records = category_records_by_transaction_ids(transaction_ids, require_fresh=False)
        elif hasattr(provider, "bulk_get_for_rows"):
            raw_records = provider.bulk_get_for_rows(transactions)
        elif hasattr(provider, "bulk_get"):
            raw_records = provider.bulk_get(transaction_ids)
        elif hasattr(provider, "get"):
            raw_records = {
                transaction_id: provider.get(transaction_id)
                for transaction_id in transaction_ids
            }
        else:
            return {}

        normalized: dict[str, dict[str, str]] = {}
        if isinstance(raw_records, dict):
            iterable = raw_records.items()
        elif isinstance(raw_records, list):
            iterable = ((str(record.get("transaction_id") or ""), record) for record in raw_records if isinstance(record, dict))
        else:
            return {}

        for transaction_id, record in iterable:
            category = self._normalize_category_record(record)
            if category is not None:
                normalized[str(transaction_id)] = category
        return normalized

    @staticmethod
    def _normalize_category_record(record: Any) -> dict[str, Any] | None:
        if record is None:
            return None
        code = str(
            LiveWorkbenchService._record_value(record, "category_code")
            or LiveWorkbenchService._record_value(record, "code")
            or ""
        ).strip()
        if code not in BANK_TRANSACTION_CATEGORY_LABELS:
            return None
        label = str(
            LiveWorkbenchService._record_value(record, "category_label")
            or LiveWorkbenchService._record_value(record, "label")
            or BANK_TRANSACTION_CATEGORY_LABELS[code]
        ).strip()
        source = str(
            LiveWorkbenchService._record_value(record, "category_source")
            or LiveWorkbenchService._record_value(record, "source")
            or "manual"
        ).strip() or "manual"
        primary_label = str(
            LiveWorkbenchService._record_value(record, "category_primary_label")
            or LiveWorkbenchService._record_value(record, "effective_category_primary_label")
            or ""
        ).strip()
        sub_label = str(
            LiveWorkbenchService._record_value(record, "category_sub_label")
            or LiveWorkbenchService._record_value(record, "effective_category_sub_label")
            or ""
        ).strip()
        label_path = [
            str(item).strip()
            for item in list(
                LiveWorkbenchService._record_value(record, "category_label_path")
                or LiveWorkbenchService._record_value(record, "effective_category_label_path")
                or []
            )
            if str(item).strip()
        ]
        if not label_path:
            label_path = [item for item in (primary_label, sub_label) if item]
        return {
            "category_code": code,
            "category_label": label,
            "category_path": [
                str(item).strip()
                for item in list(LiveWorkbenchService._record_value(record, "category_path") or [])
                if str(item).strip()
            ],
            "category_primary_label": primary_label or None,
            "category_sub_label": sub_label or None,
            "category_label_path": label_path,
            "category_source": source,
        }

    @staticmethod
    def _record_value(record: Any, key: str) -> Any:
        if isinstance(record, dict):
            return record.get(key)
        return getattr(record, key, None)

    @staticmethod
    def _bank_row_tags(transaction: BankTransaction, category: dict[str, Any] | None) -> list[str]:
        tags: list[str] = []
        for tag in list(getattr(transaction, "tags", []) or []):
            text = str(tag).strip()
            if text and text not in tags:
                tags.append(text)
        for label in list((category or {}).get("category_label_path") or []):
            text = str(label).strip()
            if text and text not in tags:
                tags.append(text)
        category_label = str((category or {}).get("category_label") or "").strip()
        if category_label and category_label not in tags:
            tags.append(category_label)
        return tags

    def _build_bank_text_fields(self, transaction: BankTransaction) -> list[dict[str, str]]:
        fields_by_label: dict[str, str] = {}
        raw_fields = getattr(transaction, "bank_text_fields", None)
        if isinstance(raw_fields, dict):
            for label, value in raw_fields.items():
                self._add_bank_text_field(fields_by_label, label, value)
        elif isinstance(raw_fields, list):
            for item in raw_fields:
                if isinstance(item, dict):
                    self._add_bank_text_field(fields_by_label, item.get("label"), item.get("value"))

        self._add_bank_text_field(fields_by_label, "摘要", transaction.summary)
        self._add_bank_text_field(fields_by_label, "备注", transaction.remark)

        return [
            {"label": label, "value": fields_by_label[label]}
            for label in self._bank_text_field_labels
            if label in fields_by_label
        ]

    @staticmethod
    def _add_bank_text_field(fields_by_label: dict[str, str], label: Any, value: Any) -> None:
        normalized_label = str(label or "").strip()
        if not normalized_label or normalized_label in fields_by_label:
            return
        if value in (None, "", "--", "—"):
            return
        text = str(value).strip()
        if text:
            fields_by_label[normalized_label] = text

    def _internal_transfer_counterpart_transaction(
        self,
        transaction_id: str,
        result: MatchingResult,
    ) -> BankTransaction | None:
        counterpart_ids = [candidate_id for candidate_id in result.transaction_ids if candidate_id != transaction_id]
        if not counterpart_ids:
            return None
        transactions_by_id = {transaction.id: transaction for transaction in self._import_service.list_transactions()}
        return transactions_by_id.get(counterpart_ids[0])

    def _compact_bank_account_label(
        self,
        account_no: str | None,
        account_name: str | None,
        *,
        preferred_bank_name: str | None = None,
        preferred_last4: str | None = None,
    ) -> str:
        full_label = self._bank_account_resolver.resolve_label(
            account_no,
            account_name,
            preferred_bank_name=preferred_bank_name,
            preferred_last4=preferred_last4,
        ).strip()
        compact_label = full_label
        for marker in (" 基本户 ", " 一般户 ", " 专户 ", " 账户 "):
            compact_label = compact_label.replace(marker, " ")
        return " ".join(compact_label.split())

    def _excluded_transaction_batch_ids(self) -> set[str]:
        return {
            preview.id
            for preview in self._import_service.list_batches()
            if preview.batch.batch_type.value == "bank_transaction"
            and preview.batch.source_name in LEGACY_DEMO_TRANSACTION_SOURCES
        }

    def _resolve_company_identity(self) -> tuple[str, str | None]:
        candidates: Counter[tuple[str, str | None]] = Counter()
        for invoice in self._import_service.list_invoices():
            for tax_no, company_name in (
                (invoice.seller_tax_no, invoice.seller_name),
                (invoice.buyer_tax_no, invoice.buyer_name),
            ):
                if not is_company_identity(tax_no, company_name):
                    continue
                resolved_name = company_name.strip() if isinstance(company_name, str) and company_name.strip() else DEFAULT_COMPANY_NAME
                resolved_tax_no = tax_no.strip() if isinstance(tax_no, str) and tax_no.strip() else None
                candidates[(resolved_name, resolved_tax_no)] += 1

        if not candidates:
            return (DEFAULT_COMPANY_NAME, None)

        (company_name, company_tax_no), _ = max(
            candidates.items(),
            key=lambda item: (item[1], 1 if item[0][1] else 0, len(item[0][0] or "")),
        )
        return company_name or DEFAULT_COMPANY_NAME, company_tax_no

    def _resolve_invoice_parties(self, invoice: Invoice) -> tuple[str | None, str | None]:
        company_name, _ = self._company_identity
        if invoice.invoice_type.value == "output":
            return invoice.seller_name or company_name, invoice.buyer_name or invoice.counterparty.name
        return invoice.seller_name or invoice.counterparty.name, invoice.buyer_name or company_name

    def _resolve_invoice_tax_nos(self, invoice: Invoice) -> tuple[str | None, str | None]:
        _, company_tax_no = self._company_identity
        if invoice.invoice_type.value == "output":
            return invoice.seller_tax_no or company_tax_no, invoice.buyer_tax_no or invoice.counterparty.tax_no
        return invoice.seller_tax_no or invoice.counterparty.tax_no, invoice.buyer_tax_no or company_tax_no

    @staticmethod
    def _available_actions(row_type: str, section: str) -> list[str]:
        if row_type == "bank":
            if section == "unpaired":
                return ["detail", "view_relation", "cancel_link", "handle_exception"]
            return ["detail"]
        if row_type == "invoice" and section == "unpaired":
            return ["detail", "confirm_link", "mark_exception", "ignore"]
        return ["detail"]

    @staticmethod
    def _invoice_is_workbench_visible(invoice: Invoice) -> bool:
        return getattr(invoice, "workbench_visibility", "visible") != "hidden_after_etc_submission"


def unlinked_relation_payload() -> dict[str, str]:
    return {"code": "unlinked", "label": "未配对", "tone": "warn"}


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(ZERO + Decimal('0.01')):,.2f}"


def payload_from_cache_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = LiveWorkbenchService._serialize_row(row)
    payload["summary_fields"] = dict(row["_summary_fields"])
    payload["detail_fields"] = dict(row["_detail_fields"])
    return payload
