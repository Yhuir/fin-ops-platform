from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    InputInvoiceUsagePaymentRulesProvider,
    PaymentStatusEvaluationContext,
)
from fin_ops_platform.services.pending_invoice_status import pending_invoice_status_payload

INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION = 1


class InvoiceLifecyclePolicy:
    """Single rule boundary for invoice lifecycle display decisions.

    The policy deliberately has no SQL, HTTP, or Application dependency. It
    normalizes existing page-specific status rules behind a single lifecycle
    entrypoint while preserving current API payload shapes.
    """

    def __init__(
        self,
        *,
        input_payment_rules_provider: InputInvoiceUsagePaymentRulesProvider | None = None,
        output_collection_status_rule_service: Any | None = None,
    ) -> None:
        self._input_payment_rules_provider = input_payment_rules_provider
        if output_collection_status_rule_service is None:
            from fin_ops_platform.services.output_invoice_collection_service import (
                OutputInvoiceCollectionStatusRuleService,
            )

            output_collection_status_rule_service = OutputInvoiceCollectionStatusRuleService()
        self._output_collection_status_rule_service = output_collection_status_rule_service

    def source_versions(self) -> dict[str, object]:
        versions: dict[str, object] = {
            "invoice_lifecycle_policy_schema_version": INVOICE_LIFECYCLE_POLICY_SCHEMA_VERSION,
            "output_invoice_collection_status_rules_version": "sheet6-static-v1+lifecycle-v1",
        }
        if self._input_payment_rules_provider is not None:
            versions["input_invoice_usage_payment_rules_version"] = self._input_payment_rules_provider.rules_source_version()
        return versions

    def evaluate_pending_invoice_acquisition(
        self,
        *,
        direction: str,
        group: str | None,
        has_invoices: bool,
        payment_summary: dict[str, Any],
        matched_rule: dict[str, Any] | None,
        status_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return pending_invoice_status_payload(
            direction=direction,
            group=group,
            has_invoices=has_invoices,
            payment_summary=payment_summary,
            matched_rule=matched_rule,
            status_override=status_override,
        )

    def evaluate_input_invoice_payment(
        self,
        *,
        has_oa: bool,
        has_bank: bool,
        applicant_name: str,
        fully_matched: bool,
        invoice_oa_amount_matched: bool,
    ) -> dict[str, str]:
        if self._input_payment_rules_provider is None:
            raise ValueError("input_payment_rules_provider is required for input invoice usage payment evaluation.")
        if has_oa and has_bank and not fully_matched:
            return {
                "code": "pending",
                "label": "待处理",
                "reason": "有 OA 和流水，但关联台不能证明发票、OA、流水完全匹配",
                "matchedRuleId": "pending_default",
                "severity": "warning",
            }
        return self._input_payment_rules_provider.evaluate(
            PaymentStatusEvaluationContext(
                has_oa=has_oa,
                has_bank=has_bank,
                applicant_name=applicant_name,
                fully_matched=fully_matched,
                invoice_oa_amount_matched=invoice_oa_amount_matched,
            )
        )

    def evaluate_oa_payment(
        self,
        *,
        oa_amount: Any,
        paid_total: Any,
        has_bank: bool,
        has_missing_bank_relation: bool = False,
        has_non_outflow_bank_relation: bool = False,
        merged_payment: bool = False,
    ) -> dict[str, str]:
        if not has_bank:
            return _status("unpaid", "未支付", "未关联支出流水")
        if has_missing_bank_relation:
            return _status("paid", "已支付", "已存在已配对流水关系，流水事实缺失不影响付款状态")
        if has_non_outflow_bank_relation:
            return _status("paid", "已支付", "已存在已配对流水关系，流水方向待检查但不影响付款状态")
        amount = _optional_decimal(oa_amount)
        paid = _decimal(paid_total)
        if amount is not None and _within_cent(paid, amount):
            return _status("paid", "已支付", "已存在已配对支出流水关系")
        return _status("paid", "已支付", "已存在已配对支出流水关系，金额差额不影响付款状态")

    def evaluate_output_invoice_collection(
        self,
        *,
        invoice_total: Any,
        own_inflow_total: Any,
        related_inflow_total: Any,
        related_outflow_total: Any,
        has_red_relation: bool,
        fully_matched: bool,
    ) -> dict[str, Any]:
        return self._output_collection_status_rule_service.classify(
            invoice_total=_decimal(invoice_total),
            own_inflow_total=_decimal(own_inflow_total),
            related_inflow_total=_decimal(related_inflow_total),
            related_outflow_total=_decimal(related_outflow_total),
            has_red_relation=has_red_relation,
            fully_matched=fully_matched,
        )

    def evaluate_tax_certification(
        self,
        *,
        is_certified: bool,
        certified_item: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if is_certified:
            payload = {
                "code": "certified",
                "label": "已认证",
                "reason": "税局认证记录已匹配该发票。",
                "severity": "success",
                "certified_status": "已认证",
                "is_locked_certified": True,
            }
            if certified_item:
                payload["certified_item"] = dict(certified_item)
            return payload
        return {
            "code": "pending_certification",
            "label": "待认证",
            "reason": "未匹配税局认证记录。",
            "severity": "warning",
            "certified_status": "待认证",
            "is_locked_certified": False,
        }


def _status(code: str, label: str, reason: str) -> dict[str, str]:
    severity = "success" if code == "paid" else "warning"
    return {"code": code, "label": label, "reason": reason, "severity": severity}


def _optional_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    parsed = _optional_decimal(value)
    return parsed if parsed is not None else Decimal("0.00")


def _within_cent(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= Decimal("0.01")
