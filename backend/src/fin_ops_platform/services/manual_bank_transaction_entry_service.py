from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
import re
from typing import Any, Callable, Protocol

from fin_ops_platform.domain.enums import ImportDecision
from fin_ops_platform.services.bank_transaction_identity_service import BankTransactionIdentityService
from fin_ops_platform.services.import_file_service import FileImportSession


CENT = Decimal("0.01")
MAX_MANUAL_BANK_TRANSACTIONS = 50
ACCOUNT_SEPARATOR_RE = re.compile(r"[\s-]+")
LOCAL_DATE_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}$")


class ManualBankTransactionEntryError(ValueError):
    def __init__(
        self,
        error: str,
        message: str,
        *,
        status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
    ) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code


class ManualBankImportPort(Protocol):
    def preview_manual_bank_transaction_entries(
        self,
        *,
        imported_by: str,
        entries: list[dict[str, Any]],
    ) -> FileImportSession: ...


@dataclass(frozen=True, slots=True)
class ManualBankTransactionEntryBatchPreview:
    session: FileImportSession
    file_ids: list[str]
    values: list[dict[str, str]]


BANK_REFERENCE_FIELDS: tuple[tuple[tuple[str, ...], dict[str, str]], ...] = (
    (("建设银行", "中国建设银行"), {"key": "account_detail_no", "label": "账户明细编号-交易流水号"}),
    (("民生银行", "中国民生银行"), {"key": "bank_serial_no", "label": "交易流水号"}),
    (("平安银行",), {"key": "bank_serial_no", "label": "核心唯一流水号"}),
    (("光大银行", "中国光大银行"), {"key": "enterprise_serial_no", "label": "企业流水号"}),
    (("工商银行", "中国工商银行"), {"key": "bank_serial_no", "label": "银行流水号"}),
    (("交通银行",), {"key": "bank_serial_no", "label": "银行流水号"}),
)


def manual_bank_reference_field(bank_name: str) -> dict[str, str] | None:
    normalized = str(bank_name or "").strip()
    for markers, field in BANK_REFERENCE_FIELDS:
        if any(marker in normalized for marker in markers):
            return dict(field)
    return None


class ManualBankTransactionEntryService:
    def __init__(
        self,
        *,
        file_import_service: ManualBankImportPort,
        bank_account_mappings_provider: Callable[[], list[dict[str, Any]]],
    ) -> None:
        self._file_import_service = file_import_service
        self._bank_account_mappings_provider = bank_account_mappings_provider
        self._identity_service = BankTransactionIdentityService()

    def preview_batch(
        self,
        *,
        payloads: list[dict[str, Any]],
        imported_by: str,
    ) -> ManualBankTransactionEntryBatchPreview:
        if not payloads:
            raise ManualBankTransactionEntryError("manual_bank_transaction_batch_empty", "请至少录入一笔流水。")
        if len(payloads) > MAX_MANUAL_BANK_TRANSACTIONS:
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_batch_too_large",
                f"单次最多录入 {MAX_MANUAL_BANK_TRANSACTIONS} 笔流水。",
            )

        mappings = {
            str(item.get("id") or "").strip(): item
            for item in self._bank_account_mappings_provider()
            if str(item.get("id") or "").strip()
        }
        normalized_entries = [self._normalize_payload(payload, mappings=mappings) for payload in payloads]
        identities: set[str] = set()
        for _values, row in normalized_entries:
            identity = self._identity_service.identity_for_mapping(row)
            if not identity.identity_key:
                raise ManualBankTransactionEntryError(
                    "manual_bank_transaction_identity_incomplete",
                    "流水缺少可用于正式去重的银行流水标识。",
                )
            if identity.identity_key in identities:
                raise ManualBankTransactionEntryError(
                    "manual_bank_transaction_batch_duplicate",
                    "本次录入中存在重复流水，请修改或删除重复项后再预览。",
                    status_code=HTTPStatus.CONFLICT,
                )
            identities.add(identity.identity_key)

        session = self._file_import_service.preview_manual_bank_transaction_entries(
            imported_by=imported_by,
            entries=[row for _values, row in normalized_entries],
        )
        file_ids = [
            file_item.id
            for file_item in session.files
            if file_item.row_results
            and all(result.decision == ImportDecision.CREATED for result in file_item.row_results)
        ]
        return ManualBankTransactionEntryBatchPreview(
            session=session,
            file_ids=file_ids,
            values=[values for values, _row in normalized_entries],
        )

    def _normalize_payload(
        self,
        payload: dict[str, Any],
        *,
        mappings: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, str], dict[str, Any]]:
        mapping_id = self._required_text(payload, "bank_mapping_id", "请选择银行账户。")
        mapping = mappings.get(mapping_id)
        if mapping is None:
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_mapping_not_found",
                "所选银行账户不存在或已被删除，请刷新后重试。",
                status_code=HTTPStatus.CONFLICT,
            )
        bank_name = self._required_mapping_text(mapping, "bank_name", "所选银行账户缺少银行名称。")
        last4 = self._required_mapping_text(mapping, "last4", "所选银行账户缺少账户尾号。")
        short_name = str(mapping.get("short_name") or "").strip()

        account_no = ACCOUNT_SEPARATOR_RE.sub("", self._required_text(payload, "account_no", "请填写本方账号。"))
        if not account_no.isdigit() or not account_no.endswith(last4):
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_account_mismatch",
                f"本方账号必须为数字，且尾号与所选账户 {last4} 一致。",
            )
        direction = self._choice(payload, "direction", {"inflow", "outflow"}, "请选择收入或支出。")
        amount = self._money(payload, "amount", "金额", positive=True)
        balance = self._money(payload, "balance", "余额", positive=False)
        trade_time = self._trade_time(payload.get("trade_time"))
        counterparty_name = self._required_text(payload, "counterparty_name", "请填写对方户名。")
        currency = self._required_text(payload, "currency", "请填写币种。").upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ManualBankTransactionEntryError("manual_bank_transaction_currency_invalid", "币种必须为三位英文代码。")

        reference_field = manual_bank_reference_field(bank_name)
        if reference_field is None:
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_bank_not_supported",
                f"{bank_name}尚未配置手工流水录入字段，请先补齐银行模板。",
            )
        reference_key = reference_field["key"]
        reference_value = self._required_text(payload, reference_key, f"请填写{reference_field['label']}。")
        values = {
            "bank_mapping_id": mapping_id,
            "bank_name": bank_name,
            "bank_short_name": short_name,
            "last4": last4,
            "account_no": account_no,
            "account_name": self._text(payload.get("account_name")),
            "direction": direction,
            "amount": self._money_text(amount),
            "balance": self._money_text(balance),
            "trade_time": trade_time,
            "currency": currency,
            "counterparty_name": counterparty_name,
            "counterparty_account_no": ACCOUNT_SEPARATOR_RE.sub("", self._text(payload.get("counterparty_account_no"))),
            "counterparty_bank_name": self._text(payload.get("counterparty_bank_name")),
            "summary": self._text(payload.get("summary")),
            "remark": self._text(payload.get("remark")),
            "reference_field_key": reference_key,
            "reference_field_label": reference_field["label"],
            "reference_value": reference_value,
        }
        row: dict[str, Any] = {
            "account_no": account_no,
            "account_name": values["account_name"],
            "trade_time": trade_time,
            "txn_date": trade_time[:10],
            "direction": direction,
            "amount": values["amount"],
            "debit_amount": values["amount"] if direction == "outflow" else "0.00",
            "credit_amount": values["amount"] if direction == "inflow" else "0.00",
            "balance": values["balance"],
            "currency": currency,
            "counterparty_name": counterparty_name,
            "counterparty_account_no": values["counterparty_account_no"],
            "counterparty_bank_name": values["counterparty_bank_name"],
            "summary": values["summary"],
            "remark": values["remark"],
            reference_key: reference_value,
            "selected_bank_mapping_id": mapping_id,
            "selected_bank_name": bank_name,
            "selected_bank_short_name": short_name,
            "selected_bank_last4": last4,
            "detected_bank_name": bank_name,
            "detected_last4": last4,
        }
        return values, row

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    def _required_text(self, payload: dict[str, Any], key: str, message: str) -> str:
        value = self._text(payload.get(key))
        if not value:
            raise ManualBankTransactionEntryError(f"manual_bank_transaction_{key}_required", message)
        return value

    def _required_mapping_text(self, mapping: dict[str, Any], key: str, message: str) -> str:
        value = self._text(mapping.get(key))
        if not value:
            raise ManualBankTransactionEntryError(f"manual_bank_transaction_mapping_{key}_required", message)
        return value

    def _choice(self, payload: dict[str, Any], key: str, choices: set[str], message: str) -> str:
        value = self._required_text(payload, key, message)
        if value not in choices:
            raise ManualBankTransactionEntryError(f"manual_bank_transaction_{key}_invalid", message)
        return value

    def _money(self, payload: dict[str, Any], key: str, label: str, *, positive: bool) -> Decimal:
        text = self._required_text(payload, key, f"请填写{label}。")
        try:
            value = Decimal(text).quantize(CENT)
        except (InvalidOperation, ValueError) as exc:
            raise ManualBankTransactionEntryError(
                f"manual_bank_transaction_{key}_invalid",
                f"{label}格式不正确。",
            ) from exc
        if positive and value <= 0:
            raise ManualBankTransactionEntryError(
                f"manual_bank_transaction_{key}_invalid",
                f"{label}必须大于 0。",
            )
        return value

    @staticmethod
    def _money_text(value: Decimal) -> str:
        return format(value, ".2f")

    @staticmethod
    def _trade_time(value: Any) -> str:
        text = str(value or "").strip()
        if not LOCAL_DATE_TIME_RE.fullmatch(text):
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_trade_time_invalid",
                "交易时间必须精确到秒。",
            )
        try:
            parsed = datetime.fromisoformat(text.replace(" ", "T"))
        except ValueError as exc:
            raise ManualBankTransactionEntryError(
                "manual_bank_transaction_trade_time_invalid",
                "交易时间格式不正确。",
            ) from exc
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
