from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fin_ops_platform.services.workbench_invoice_direction import normalize_invoice_kind
from fin_ops_platform.services.workbench_relation_receipt_eligibility import (
    normalize_receipt_currency,
)


class WorkbenchReceiptError(ValueError):
    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class WorkbenchReceiptFile:
    content: bytes
    file_name: str
    receipt_id: str
    receipt_count: int
    reused: bool


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _date_key(row: dict[str, Any]) -> str:
    value = row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date")
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date().isoformat()


def _normalized_name(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


class WorkbenchRelationReceiptService:
    def __init__(self, *, repository: Any, file_store: Any, audit_repository: Any, renderer: Any) -> None:
        self._repository = repository
        self._file_store = file_store
        self._audit_repository = audit_repository
        self._renderer = renderer

    def print_receipt(
        self,
        *,
        case_id: str,
        actor_id: str,
        actor_account: str,
        actor_name: str,
        request_id: str,
    ) -> WorkbenchReceiptFile:
        case_id = str(case_id or "").strip()
        if not case_id:
            raise WorkbenchReceiptError("invalid_receipt_request", "缺少关联关系编号。", 400)
        relation = self._repository.load_active_relation(case_id)
        if relation is None:
            raise WorkbenchReceiptError("workbench_relation_not_found", "关联关系不存在或已撤回，请刷新后重试。", 404)
        snapshot = self._build_snapshot(relation)
        fingerprint = hashlib.sha256(
            json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        existing = self._repository.find_by_fingerprint(case_id, fingerprint)
        reused = existing is not None
        if existing is None:
            receipt_id = str(uuid5(NAMESPACE_URL, f"fin-ops:workbench-receipt:{case_id}:{fingerprint}"))
            content = self._renderer.render(snapshot)
            stored = self._file_store.store_workbench_relation_receipt(
                receipt_id=receipt_id,
                file_name=f"workbench-receipt-{case_id}.pdf",
                content=content,
                content_type="application/pdf",
            )
            existing, created = self._repository.insert(
                {
                    "id": receipt_id,
                    "relation_id": relation["id"],
                    "case_id": case_id,
                    "relation_version": relation["version"],
                    "source_fingerprint": fingerprint,
                    "file_object_id": stored["file_object_id"],
                    "storage_uri": stored["storage_uri"],
                    "receipt_count": len(snapshot["receipts"]),
                    "total_amount": snapshot["total_amount"],
                    "snapshot": snapshot,
                    "generated_by_id": actor_id,
                    "generated_by_account": actor_account,
                    "generated_by_name": actor_name,
                }
            )
            reused = not created
            if created:
                self._audit(
                    "receipt_generated",
                    existing["id"],
                    case_id,
                    actor_id,
                    actor_account,
                    actor_name,
                    request_id,
                    snapshot,
                )
        content = self._file_store.read_workbench_relation_receipt(str(existing["storage_uri"]))
        self._audit(
            "receipt_print_requested",
            existing["id"],
            case_id,
            actor_id,
            actor_account,
            actor_name,
            request_id,
            snapshot,
        )
        return WorkbenchReceiptFile(
            content=content,
            file_name=f"收据-{case_id}.pdf",
            receipt_id=str(existing["id"]),
            receipt_count=int(existing["receipt_count"]),
            reused=reused,
        )

    def _build_snapshot(self, relation: dict[str, Any]) -> dict[str, Any]:
        row_types = [str(value) for value in relation.get("row_types") or []]
        bank_rows = list(relation.get("bank_rows") or [])
        invoice_rows = list(relation.get("invoice_rows") or [])
        if "oa" in row_types or not bank_rows or not invoice_rows:
            raise WorkbenchReceiptError("receipt_relation_not_eligible", "仅无 OA 的收入加销项发票关联关系可以打印收据。", 409)
        if len(bank_rows) != row_types.count("bank") or len(invoice_rows) != row_types.count("invoice"):
            raise WorkbenchReceiptError("receipt_relation_members_incomplete", "关联关系成员已变化，请刷新后重试。", 409)
        if any(str(row.get("txn_direction") or "").strip().lower() != "inflow" for row in bank_rows):
            raise WorkbenchReceiptError("receipt_relation_not_income", "该关联关系包含非收入流水，不能打印收据。", 409)
        if any(_decimal(row.get("amount")) <= Decimal("0.00") for row in bank_rows):
            raise WorkbenchReceiptError("receipt_income_amount_invalid", "收入流水金额必须大于零。", 409)
        if any(normalize_invoice_kind(row.get("invoice_type")) != "output" for row in invoice_rows):
            raise WorkbenchReceiptError("receipt_relation_not_output_invoice", "该关联关系包含非销项发票，不能打印收据。", 409)
        if any(not str(row.get("digital_invoice_no") or row.get("invoice_no") or "").strip() for row in invoice_rows):
            raise WorkbenchReceiptError("receipt_invoice_number_missing", "销项发票缺少发票号码，不能打印收据。", 409)
        currencies = {
            normalize_receipt_currency(row.get("currency"))
            for row in [*bank_rows, *invoice_rows]
        }
        if currencies != {"CNY"}:
            raise WorkbenchReceiptError("receipt_currency_not_supported", "收据当前仅支持单一人民币币种。", 409)

        groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
        payer_labels: dict[tuple[str, str, str], str] = {}
        for row in bank_rows:
            payer = str(row.get("normalized_counterparty_name") or row.get("counterparty_name_raw") or "").strip()
            if not payer:
                raise WorkbenchReceiptError("receipt_payer_missing", "收入流水缺少付款方名称，不能打印收据。", 409)
            key = (_normalized_name(payer), _date_key(row), normalize_receipt_currency(row.get("currency")))
            groups.setdefault(key, []).append(row)
            payer_labels.setdefault(key, payer)

        invoices_by_group: dict[tuple[str, str, str], list[dict[str, Any]]] = {key: [] for key in groups}
        if len(groups) == 1:
            invoices_by_group[next(iter(groups))] = invoice_rows
        else:
            for invoice in invoice_rows:
                buyer_key = _normalized_name(invoice.get("buyer_name") or invoice.get("counterparty_name"))
                invoice_date = str(invoice.get("invoice_date") or "").strip()
                payer_candidates = [key for key in groups if key[0] == buyer_key]
                if len(payer_candidates) == 1:
                    candidates = payer_candidates
                else:
                    candidates = [key for key in payer_candidates if invoice_date and key[1] == invoice_date]
                if len(candidates) != 1:
                    raise WorkbenchReceiptError(
                        "receipt_invoice_group_ambiguous",
                        f"发票 {invoice.get('invoice_no') or invoice.get('id')} 无法唯一归入付款方与日期分组。",
                        409,
                    )
                invoices_by_group[candidates[0]].append(invoice)

        receipts: list[dict[str, Any]] = []
        total_amount = Decimal("0.00")
        for key in sorted(groups, key=lambda item: (item[1], item[0])):
            amount = sum((_decimal(row.get("amount")) for row in groups[key]), Decimal("0.00"))
            total_amount += amount
            receipts.append(
                {
                    "payer": payer_labels[key],
                    "date": key[1],
                    "currency": key[2],
                    "amount": f"{amount:.2f}",
                    "handler": "",
                    "supervisor": "",
                    "bank_transaction_ids": [str(row["id"]) for row in groups[key]],
                    "invoice_lines": [
                        {
                            "id": str(row["id"]),
                            "invoice_no": str(row.get("digital_invoice_no") or row.get("invoice_no") or "").strip(),
                            "date": str(row.get("invoice_date") or ""),
                            "amount": f"{_decimal(row.get('total_with_tax') or row.get('amount')):.2f}",
                            "note": str(
                                (row.get("raw_payload") or {}).get("备注")
                                or (row.get("raw_payload") or {}).get("remark")
                                or ""
                            ).strip(),
                        }
                        for row in invoices_by_group[key]
                    ],
                }
            )
        return {
            "case_id": str(relation["case_id"]),
            "relation_version": int(relation["version"]),
            "total_amount": f"{total_amount:.2f}",
            "receipts": receipts,
        }

    def _audit(
        self,
        event_type: str,
        receipt_id: str,
        case_id: str,
        actor_id: str,
        actor_account: str,
        actor_name: str,
        request_id: str,
        snapshot: dict[str, Any],
    ) -> None:
        self._audit_repository.append_operation_event(
            {
                "event_type": event_type,
                "object_type": "workbench_relation_receipt",
                "object_id": receipt_id,
                "actor_id": actor_id,
                "actor_account": actor_account,
                "actor_name": actor_name,
                "action": event_type,
                "page_key": "reconciliation-workbench",
                "operation_location": "关联台收据",
                "request_id": request_id,
                "outcome": "success",
                "payload": {
                    "case_id": case_id,
                    "receipt_count": len(snapshot["receipts"]),
                    "total_amount": snapshot["total_amount"],
                },
            }
        )
