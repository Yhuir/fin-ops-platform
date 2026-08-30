from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from fin_ops_platform.services.output_invoice_reversal import reversal_target_invoice_nos
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
    return Decimal(str(value or "0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _date_key(row: dict[str, Any]) -> str:
    value = (
        row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date")
    )
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return datetime.fromisoformat(str(value or "").replace("Z", "+00:00")).date().isoformat()
    except ValueError as exc:
        raise WorkbenchReceiptError(
            "receipt_transaction_date_missing",
            "收入流水缺少有效交易日期，不能编辑收据。",
            409,
        ) from exc


def _normalized_name(value: Any) -> str:
    return "".join(str(value or "").split()).casefold()


def _invoice_no(row: dict[str, Any]) -> str:
    return "".join(
        str(row.get("digital_invoice_no") or row.get("invoice_no") or "").split()
    )


def _invoice_amount(row: dict[str, Any]) -> Decimal:
    value = row.get("total_with_tax")
    if value is None or str(value).strip() == "":
        value = row.get("amount")
    return _decimal(value)


def _invoice_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("raw_payload")
    return payload if isinstance(payload, dict) else {}


def _invoice_remark(row: dict[str, Any]) -> str:
    payload = _invoice_payload(row)
    normalized = payload.get("normalized_payload")
    normalized_payload = normalized if isinstance(normalized, dict) else {}
    return str(
        normalized_payload.get("remark")
        or payload.get("备注")
        or payload.get("remark")
        or ""
    ).strip()


def _invoice_summary(row: dict[str, Any]) -> str:
    payload = _invoice_payload(row)
    normalized = payload.get("normalized_payload")
    normalized_payload = normalized if isinstance(normalized, dict) else {}
    taxable_item_name = str(
        normalized_payload.get("taxable_item_name")
        or payload.get("taxable_item_name")
        or payload.get("货物或应税劳务名称")
        or payload.get("货物或应税劳务、服务名称")
        or ""
    ).strip()
    return taxable_item_name or f"销项发票 {_invoice_no(row)}"


def _receipt_key(bank_rows: list[dict[str, Any]]) -> str:
    row_ids = sorted(str(row["id"]) for row in bank_rows)
    return hashlib.sha256("\n".join(row_ids).encode("utf-8")).hexdigest()[:20]


def _issue(code: str, message: str, *invoice_ids: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "invoice_ids": list(dict.fromkeys(invoice_ids)),
    }


class WorkbenchRelationReceiptService:
    def __init__(
        self, *, repository: Any, file_store: Any, audit_repository: Any, renderer: Any
    ) -> None:
        self._repository = repository
        self._file_store = file_store
        self._audit_repository = audit_repository
        self._renderer = renderer

    def draft_receipt(self, *, case_id: str) -> dict[str, Any]:
        relation = self._load_relation(case_id)
        return self._build_draft(relation)

    def print_receipt(
        self,
        *,
        case_id: str,
        relation_version: Any,
        source_fingerprint: str,
        receipts: Any,
        issues_acknowledged: bool,
        actor_id: str,
        actor_account: str,
        actor_name: str,
        request_id: str,
    ) -> WorkbenchReceiptFile:
        relation = self._load_relation(case_id)
        case_id = str(relation["case_id"])
        source_draft = self._build_draft(relation)
        try:
            submitted_version = int(relation_version)
        except (TypeError, ValueError) as exc:
            raise WorkbenchReceiptError(
                "invalid_receipt_request", "收据关系版本无效。", 400
            ) from exc
        if submitted_version != int(source_draft["relation_version"]):
            raise WorkbenchReceiptError(
                "receipt_relation_version_conflict",
                "关联关系已发生变化，请刷新收据草稿后重试。",
                409,
            )
        if str(source_fingerprint or "").strip() != source_draft["source_fingerprint"]:
            raise WorkbenchReceiptError(
                "receipt_source_conflict",
                "关联关系或来源数据已发生变化，请刷新收据草稿后重试。",
                409,
            )
        if source_draft["issues"] and not issues_acknowledged:
            raise WorkbenchReceiptError(
                "receipt_reversal_issue_unacknowledged",
                "请先核对并确认收据中的发票冲销异常。",
                409,
            )

        normalized_receipts = self._validate_receipts(source_draft, receipts)
        snapshot = {
            "case_id": source_draft["case_id"],
            "relation_version": source_draft["relation_version"],
            "source_fingerprint": source_draft["source_fingerprint"],
            "total_amount": source_draft["total_amount"],
            "receipts": normalized_receipts,
            "original_receipts": source_draft["receipts"],
            "reversal_adjustments": source_draft["reversal_adjustments"],
            "issues": source_draft["issues"],
            "issues_acknowledged": bool(issues_acknowledged),
        }
        document_fingerprint = _fingerprint(snapshot)
        existing = self._repository.find_by_fingerprint(case_id, document_fingerprint)
        reused = existing is not None
        if existing is None:
            receipt_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"fin-ops:workbench-receipt:{case_id}:{document_fingerprint}",
                )
            )
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
                    "source_fingerprint": document_fingerprint,
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
                    document_fingerprint=document_fingerprint,
                )
        content = self._file_store.read_workbench_relation_receipt(
            str(existing["storage_uri"])
        )
        self._audit(
            "receipt_print_requested",
            existing["id"],
            case_id,
            actor_id,
            actor_account,
            actor_name,
            request_id,
            snapshot,
            document_fingerprint=document_fingerprint,
        )
        return WorkbenchReceiptFile(
            content=content,
            file_name=f"收据-{case_id}.pdf",
            receipt_id=str(existing["id"]),
            receipt_count=int(existing["receipt_count"]),
            reused=reused,
        )

    def _load_relation(self, case_id: str) -> dict[str, Any]:
        normalized_case_id = str(case_id or "").strip()
        if not normalized_case_id:
            raise WorkbenchReceiptError(
                "invalid_receipt_request", "缺少关联关系编号。", 400
            )
        relation = self._repository.load_active_relation(normalized_case_id)
        if relation is None:
            raise WorkbenchReceiptError(
                "workbench_relation_not_found",
                "关联关系不存在或已撤回，请刷新后重试。",
                404,
            )
        return relation

    def _build_draft(self, relation: dict[str, Any]) -> dict[str, Any]:
        row_types = [str(value) for value in relation.get("row_types") or []]
        bank_rows = list(relation.get("bank_rows") or [])
        invoice_rows = list(relation.get("invoice_rows") or [])
        if "oa" in row_types or not bank_rows or not invoice_rows:
            raise WorkbenchReceiptError(
                "receipt_relation_not_eligible",
                "仅无 OA 的收入加销项发票关联关系可以编辑收据。",
                409,
            )
        if len(bank_rows) != row_types.count("bank") or len(invoice_rows) != row_types.count(
            "invoice"
        ):
            raise WorkbenchReceiptError(
                "receipt_relation_members_incomplete",
                "关联关系成员已变化，请刷新后重试。",
                409,
            )
        if any(
            str(row.get("txn_direction") or "").strip().lower() != "inflow"
            for row in bank_rows
        ):
            raise WorkbenchReceiptError(
                "receipt_relation_not_income",
                "该关联关系包含非收入流水，不能编辑收据。",
                409,
            )
        if any(_decimal(row.get("amount")) <= Decimal("0.00") for row in bank_rows):
            raise WorkbenchReceiptError(
                "receipt_income_amount_invalid", "收入流水金额必须大于零。", 409
            )
        if any(
            normalize_invoice_kind(row.get("invoice_type")) != "output"
            for row in invoice_rows
        ):
            raise WorkbenchReceiptError(
                "receipt_relation_not_output_invoice",
                "该关联关系包含非销项发票，不能编辑收据。",
                409,
            )
        if any(not _invoice_no(row) for row in invoice_rows):
            raise WorkbenchReceiptError(
                "receipt_invoice_number_missing",
                "销项发票缺少发票号码，不能编辑收据。",
                409,
            )
        currencies = {
            normalize_receipt_currency(row.get("currency"))
            for row in [*bank_rows, *invoice_rows]
        }
        if currencies != {"CNY"}:
            raise WorkbenchReceiptError(
                "receipt_currency_not_supported",
                "收据当前仅支持单一人民币币种。",
                409,
            )

        payer_labels: dict[str, str] = {}
        for row in bank_rows:
            payer = str(
                row.get("normalized_counterparty_name")
                or row.get("counterparty_name_raw")
                or row.get("counterparty_name")
                or ""
            ).strip()
            if not payer:
                raise WorkbenchReceiptError(
                    "receipt_payer_missing",
                    "收入流水缺少付款方名称，不能编辑收据。",
                    409,
                )
            payer_labels.setdefault(_normalized_name(payer), payer)
        if len(payer_labels) != 1:
            raise WorkbenchReceiptError(
                "receipt_payer_ambiguous",
                "同一关联关系包含多个付款单位，不能合并为一张收据。",
                409,
            )

        target_invoice_nos = reversal_target_invoice_nos(
            _invoice_remark(row) for row in invoice_rows
        )
        reversal_target_rows = (
            self._repository.load_output_invoices_by_numbers(target_invoice_nos)
            if target_invoice_nos
            else []
        )
        net_amounts, reversal_adjustments, issues = self._apply_reversals(
            invoice_rows,
            [*invoice_rows, *reversal_target_rows],
        )

        total_amount = sum(
            (_decimal(row.get("amount")) for row in bank_rows), Decimal("0.00")
        )
        lines = []
        for row in invoice_rows:
            row_id = str(row["id"])
            amount = net_amounts[row_id]
            if amount == Decimal("0.00"):
                continue
            lines.append(
                {
                    "source_invoice_ids": [row_id],
                    "invoice_no": _invoice_no(row),
                    "summary": _invoice_summary(row),
                    "amount": f"{amount:.2f}",
                    "note": "",
                }
            )
        line_total = sum(
            (_decimal(line["amount"]) for line in lines), Decimal("0.00")
        )
        receipts = [
            {
                "receipt_key": _receipt_key(bank_rows),
                "payer": next(iter(payer_labels.values())),
                "date": max(_date_key(row) for row in bank_rows),
                "currency": "CNY",
                "income_amount": f"{total_amount:.2f}",
                "line_total": f"{line_total:.2f}",
                "balanced": bool(lines) and line_total == total_amount,
                "handler": "",
                "supervisor": "",
                "bank_transaction_ids": [str(row["id"]) for row in bank_rows],
                "lines": lines,
            }
        ]

        source_payload = {
            "case_id": str(relation["case_id"]),
            "relation_version": int(relation["version"]),
            "total_amount": f"{total_amount:.2f}",
            "receipts": receipts,
            "reversal_adjustments": reversal_adjustments,
            "issues": issues,
        }
        return {
            **source_payload,
            "source_fingerprint": _fingerprint(source_payload),
            "can_print": not issues
            and all(bool(receipt["balanced"]) for receipt in receipts),
        }

    @staticmethod
    def _apply_reversals(
        relation_invoices: list[dict[str, Any]],
        candidate_invoices: list[dict[str, Any]],
    ) -> tuple[dict[str, Decimal], list[dict[str, Any]], list[dict[str, Any]]]:
        unique_candidates: dict[str, dict[str, Any]] = {}
        for row in candidate_invoices:
            row_id = str(row.get("id") or "").strip()
            if row_id:
                unique_candidates.setdefault(row_id, row)

        by_invoice_no: dict[str, list[dict[str, Any]]] = {}
        for row in unique_candidates.values():
            invoice_no = _invoice_no(row)
            if invoice_no:
                by_invoice_no.setdefault(invoice_no, []).append(row)

        net_amounts = {
            str(row["id"]): _invoice_amount(row) for row in relation_invoices
        }
        target_remaining = {
            row_id: _invoice_amount(row) for row_id, row in unique_candidates.items()
        }
        adjustments: list[dict[str, Any]] = []
        issues: list[dict[str, Any]] = []
        for red in relation_invoices:
            red_id = str(red["id"])
            red_amount = net_amounts[red_id]
            if red_amount >= Decimal("0.00"):
                continue
            targets = reversal_target_invoice_nos([_invoice_remark(red)])
            if len(targets) != 1:
                issues.append(
                    _issue(
                        "receipt_reversal_target_unresolved",
                        f"红字发票 {_invoice_no(red)} 未提供唯一、明确的被冲蓝票号码。",
                        red_id,
                    )
                )
                continue
            target_no = targets[0]
            candidates = [
                row
                for row in by_invoice_no.get(target_no, [])
                if str(row.get("id")) != red_id
                and normalize_invoice_kind(row.get("invoice_type")) == "output"
                and _invoice_amount(row) > Decimal("0.00")
            ]
            if len(candidates) != 1:
                issues.append(
                    _issue(
                        "receipt_reversal_target_unresolved",
                        f"红字发票 {_invoice_no(red)} 指向的蓝字发票 {target_no} 无法唯一定位。",
                        red_id,
                        *(str(row.get("id")) for row in candidates),
                    )
                )
                continue
            blue = candidates[0]
            blue_id = str(blue["id"])
            remaining = target_remaining[blue_id]
            reversal_amount = abs(red_amount)
            if reversal_amount > remaining:
                issues.append(
                    _issue(
                        "receipt_reversal_amount_invalid",
                        f"红字发票 {_invoice_no(red)} 的冲销金额超过蓝字发票 {target_no} 的剩余金额。",
                        red_id,
                        blue_id,
                    )
                )
                continue
            net_amounts[red_id] = Decimal("0.00")
            target_remaining[blue_id] = remaining - reversal_amount
            if blue_id in net_amounts:
                net_amounts[blue_id] = target_remaining[blue_id]
            adjustments.append(
                {
                    "kind": "full"
                    if target_remaining[blue_id] == Decimal("0.00")
                    else "partial",
                    "red_invoice_id": red_id,
                    "red_invoice_no": _invoice_no(red),
                    "blue_invoice_id": blue_id,
                    "blue_invoice_no": target_no,
                    "amount": f"{reversal_amount:.2f}",
                }
            )
        return net_amounts, adjustments, issues

    @staticmethod
    def _validate_receipts(
        source_draft: dict[str, Any], submitted_receipts: Any
    ) -> list[dict[str, Any]]:
        if not isinstance(submitted_receipts, list) or not submitted_receipts:
            raise WorkbenchReceiptError(
                "invalid_receipt_document", "收据内容不能为空。", 400
            )
        source_by_key = {
            str(receipt["receipt_key"]): receipt
            for receipt in source_draft["receipts"]
        }
        if len(submitted_receipts) != len(source_by_key):
            raise WorkbenchReceiptError(
                "invalid_receipt_document",
                "收据数量与当前关系不一致，请刷新后重试。",
                400,
            )

        normalized: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for submitted in submitted_receipts:
            if not isinstance(submitted, dict):
                raise WorkbenchReceiptError(
                    "invalid_receipt_document", "收据内容格式无效。", 400
                )
            receipt_key = str(submitted.get("receipt_key") or "").strip()
            source = source_by_key.get(receipt_key)
            if source is None or receipt_key in seen_keys:
                raise WorkbenchReceiptError(
                    "invalid_receipt_document",
                    "收据与当前关系分组不一致，请刷新后重试。",
                    400,
                )
            seen_keys.add(receipt_key)
            payer = str(submitted.get("payer") or "").strip()
            if not payer:
                raise WorkbenchReceiptError(
                    "receipt_payer_missing", "付款单位不能为空。", 400
                )
            date_text = str(submitted.get("date") or "").strip()
            try:
                date.fromisoformat(date_text)
            except ValueError as exc:
                raise WorkbenchReceiptError(
                    "invalid_receipt_date", "收据日期格式无效。", 400
                ) from exc
            submitted_lines = submitted.get("lines")
            if not isinstance(submitted_lines, list) or not submitted_lines:
                raise WorkbenchReceiptError(
                    "receipt_lines_empty", "收据至少需要一条款项明细。", 400
                )
            lines: list[dict[str, Any]] = []
            line_total = Decimal("0.00")
            for line in submitted_lines:
                if not isinstance(line, dict):
                    raise WorkbenchReceiptError(
                        "invalid_receipt_line", "收据明细格式无效。", 400
                    )
                summary = str(line.get("summary") or "").strip()
                if not summary:
                    raise WorkbenchReceiptError(
                        "receipt_line_summary_missing", "收据摘要不能为空。", 400
                    )
                try:
                    amount = _decimal(line.get("amount"))
                except (InvalidOperation, TypeError, ValueError) as exc:
                    raise WorkbenchReceiptError(
                        "receipt_line_amount_invalid", "收据明细金额格式无效。", 400
                    ) from exc
                if amount <= Decimal("0.00"):
                    raise WorkbenchReceiptError(
                        "receipt_line_amount_invalid", "收据明细金额必须大于零。", 400
                    )
                line_total += amount
                lines.append(
                    {
                        "summary": summary,
                        "amount": f"{amount:.2f}",
                        "note": str(line.get("note") or "").strip(),
                    }
                )
            income_amount = _decimal(source["income_amount"])
            if line_total != income_amount:
                raise WorkbenchReceiptError(
                    "receipt_amount_unbalanced",
                    f"收据明细合计 {line_total:.2f} 与收入金额 {income_amount:.2f} 不一致。",
                    409,
                )
            normalized.append(
                {
                    "receipt_key": receipt_key,
                    "payer": payer,
                    "date": date_text,
                    "currency": "CNY",
                    "amount": f"{income_amount:.2f}",
                    "handler": str(submitted.get("handler") or "").strip(),
                    "supervisor": str(submitted.get("supervisor") or "").strip(),
                    "bank_transaction_ids": list(source["bank_transaction_ids"]),
                    "lines": lines,
                }
            )
        return normalized

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
        *,
        document_fingerprint: str,
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
                    "source_fingerprint": snapshot["source_fingerprint"],
                    "document_fingerprint": document_fingerprint,
                    "issues_acknowledged": snapshot["issues_acknowledged"],
                },
            }
        )
