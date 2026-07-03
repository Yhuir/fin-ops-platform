from __future__ import annotations

from typing import Callable


class WorkbenchPairRelationDisplayPolicy:
    """Builds Workbench relation display payloads by relation mode and row type."""

    def __init__(
        self,
        *,
        no_oa_relation_display_payload: Callable[[dict[str, object] | None], dict[str, str]],
        bank_transaction_tag_label: Callable[[str], str],
        no_oa_bank_batch_relation_mode: str,
        bank_flow_rule_batch_relation_mode: str,
        personal_advance_repayment_mode: str,
        oa_invoice_offset_auto_match_mode: str,
    ) -> None:
        self._no_oa_relation_display_payload = no_oa_relation_display_payload
        self._bank_transaction_tag_label = bank_transaction_tag_label
        self._no_oa_bank_batch_relation_mode = no_oa_bank_batch_relation_mode
        self._bank_flow_rule_batch_relation_mode = bank_flow_rule_batch_relation_mode
        self._personal_advance_repayment_mode = personal_advance_repayment_mode
        self._oa_invoice_offset_auto_match_mode = oa_invoice_offset_auto_match_mode

    def display_payload(
        self,
        *,
        relation_mode: str,
        row_type: str = "",
        special_metadata: dict[str, object] | None = None,
    ) -> dict[str, str]:
        if relation_mode == self._no_oa_bank_batch_relation_mode:
            return self._no_oa_relation_display_payload(special_metadata)
        if relation_mode == self._bank_flow_rule_batch_relation_mode:
            return {
                "code": self._bank_flow_rule_batch_relation_mode,
                "label": "已匹配：流水规则",
                "tone": "success",
            }
        if relation_mode == "internal_transfer_pair":
            return {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"}
        if relation_mode == "salary_personal_auto_match":
            salary_label = self._bank_transaction_tag_label("salary")
            return {"code": "salary_personal_auto_match", "label": f"已匹配：{salary_label}", "tone": "success"}
        if relation_mode == self._personal_advance_repayment_mode:
            return {"code": self._personal_advance_repayment_mode, "label": "已匹配：还清个人暂借款", "tone": "success"}
        if relation_mode == "turnover_manual_closure":
            return {"code": "turnover_manual_closure", "label": "外部往来款闭环", "tone": "success"}
        if relation_mode == self._oa_invoice_offset_auto_match_mode:
            if row_type == "invoice":
                return {"code": self._oa_invoice_offset_auto_match_mode, "label": "已关联OA", "tone": "success"}
            return {"code": self._oa_invoice_offset_auto_match_mode, "label": "待找流水与发票", "tone": "warn"}
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}
