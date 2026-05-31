from __future__ import annotations

from decimal import Decimal
from typing import Any

from fin_ops_platform.services.output_invoice_collection_models import (
    MANUAL_COLLECTION_STATUS_BY_CODE,
    MANUAL_COLLECTION_STATUS_OPTIONS,
    RED_REFUND_STATUS_CODES,
)


class OutputInvoiceCollectionStatusOverlayService:
    """Applies versioned lifecycle facts over Sheet6 automatic status rules."""

    def status_rules_payload(self, base_payload: dict[str, Any], *, can_save: bool = True, can_admin: bool = False) -> dict[str, Any]:
        payload = dict(base_payload)
        payload["readOnly"] = False
        payload["manualStatusOptions"] = [dict(item) for item in MANUAL_COLLECTION_STATUS_OPTIONS]
        payload["permissions"] = {"can_save": bool(can_save), "can_admin": bool(can_admin)}
        payload["version"] = str(payload.get("version") or "sheet6-static-v1") + "+lifecycle-v1"
        payload["futureWriteBoundary"] = {
            "statusRuleEditing": "规则仍由服务端版本化发布；本接口只开放行级手动状态和提醒。",
            "manualStatus": "手动状态写入 PostgreSQL lifecycle facts，并异步刷新销项收款 read model。",
        }
        return payload

    def apply_manual_override(
        self,
        status: dict[str, Any],
        *,
        override: dict[str, Any] | None,
        reminder: dict[str, Any] | None,
    ) -> dict[str, Any]:
        result = dict(status)
        if override and str(override.get("status") or "active") == "active":
            current_code = str(result.get("code") or "")
            code = str(override.get("statusCode") or override.get("status_code") or "").strip()
            option = MANUAL_COLLECTION_STATUS_BY_CODE.get(code)
            if option is not None and current_code not in RED_REFUND_STATUS_CODES:
                collected_amount = str(result.get("collectedAmount") or "0.00")
                pending_amount = str(result.get("pendingAmount") or "0.00")
                if code == "collected":
                    pending_amount = "0.00"
                result.update(
                    {
                        "code": code,
                        "label": option["label"],
                        "severity": option["severity"],
                        "matchedRuleId": option["matchedRuleId"],
                        "reason": str(override.get("note") or "人工设置收款状态。"),
                        "collectedAmount": collected_amount,
                        "pendingAmount": pending_amount,
                        "manualOverride": dict(override),
                        "expectedCollectionDate": override.get("expectedCollectionDate")
                        or override.get("expected_collection_date"),
                    }
                )
            else:
                result["manualOverride"] = dict(override)
                result["expectedCollectionDate"] = override.get("expectedCollectionDate") or override.get("expected_collection_date")
        else:
            result.setdefault("manualOverride", None)
            result.setdefault("expectedCollectionDate", None)
        result["reminder"] = dict(reminder) if reminder and str(reminder.get("status") or "active") == "active" else None
        return result

    @staticmethod
    def can_set_status(status_code: str) -> bool:
        return str(status_code or "").strip() in MANUAL_COLLECTION_STATUS_BY_CODE

    @staticmethod
    def non_negative_amount(value: Any) -> Decimal:
        amount = Decimal(str(value or "0").replace(",", "").strip() or "0")
        if amount < Decimal("0"):
            raise ValueError("amount must be non-negative.")
        return amount
