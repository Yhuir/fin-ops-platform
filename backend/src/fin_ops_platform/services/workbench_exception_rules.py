from __future__ import annotations

from copy import deepcopy
from typing import Any


RULE_VERSION = "exception_rules_v1"

ACTION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "confirm_closed": {
        "label": "确认支出闭环",
        "result_status": "closed",
        "relation_mode": "expense_closed",
    },
    "wait_input_invoice": {
        "label": "等待进项发票",
        "result_status": "open",
        "relation_mode": "pending_input_invoice",
        "required_fields": ["note"],
    },
    "continue_wait_input_invoice": {
        "label": "继续追进项发票",
        "result_status": "open",
        "relation_mode": "pending_input_invoice",
        "required_fields": ["note"],
    },
    "confirm_extra_invoice_owner": {
        "label": "确认票多归属",
        "result_status": "open",
        "relation_mode": "extra_invoice_owner_review",
        "required_fields": ["note"],
    },
    "wait_bank_payment": {
        "label": "等待支出流水",
        "result_status": "open",
        "relation_mode": "pending_bank_payment",
        "required_fields": ["note"],
    },
    "confirm_payable_or_installment": {
        "label": "确认应付或分期",
        "result_status": "open",
        "relation_mode": "payable_or_installment",
        "required_fields": ["note"],
    },
    "confirm_overpayment_recovery": {
        "label": "确认多付追款",
        "result_status": "open",
        "relation_mode": "overpayment_recovery",
        "required_fields": ["note"],
    },
    "request_missing_oa": {
        "label": "要求补 OA",
        "result_status": "open",
        "relation_mode": "pending_oa",
        "required_fields": ["note"],
    },
    "confirm_oa_exempt_auto": {
        "label": "自动免 OA",
        "result_status": "closed",
        "relation_mode": "oa_exempt",
    },
    "confirm_oa_exempt_manual": {
        "label": "人工确认免 OA",
        "result_status": "closed",
        "relation_mode": "oa_exempt",
        "required_fields": ["reason_code", "note"],
    },
    "manual_review": {
        "label": "人工复核",
        "result_status": "open",
        "relation_mode": "manual_review",
        "required_fields": ["note"],
    },
    "confirm_income_closed": {
        "label": "确认收入闭环",
        "result_status": "closed",
        "relation_mode": "income_closed",
    },
    "wait_output_invoice": {
        "label": "等待销项发票",
        "result_status": "open",
        "relation_mode": "pending_output_invoice",
        "required_fields": ["note"],
    },
    "confirm_no_invoice_income": {
        "label": "确认无需开票收入",
        "result_status": "closed",
        "relation_mode": "no_invoice_income",
        "required_fields": ["reason_code", "note"],
    },
    "wait_collection": {
        "label": "等待收款",
        "result_status": "open",
        "relation_mode": "pending_collection",
        "required_fields": ["note"],
    },
    "confirm_refund_or_more_invoice": {
        "label": "确认退款或补开票",
        "result_status": "open",
        "relation_mode": "refund_or_more_output_invoice",
        "required_fields": ["note"],
    },
    "confirm_output_invoice_void_or_red": {
        "label": "确认销项票作废或红冲",
        "result_status": "closed",
        "relation_mode": "output_invoice_void_or_red",
        "required_fields": ["note"],
    },
    "income_data_anomaly_manual_review": {
        "label": "收入数据异常复核",
        "result_status": "open",
        "relation_mode": "income_data_anomaly",
        "required_fields": ["note"],
    },
}

WORKFLOW_BY_ACTION: dict[str, dict[str, Any]] = {
    "confirm_closed": {
        "state": "CLOSED",
        "allowed_next_events": ["REOPEN"],
        "default_due_policy": None,
        "requires_assignee": False,
    },
    "wait_input_invoice": {
        "state": "WAIT_INPUT_INVOICE",
        "allowed_next_events": ["ADD_INPUT_INVOICE", "CANCEL", "MANUAL_CLOSE"],
        "default_due_policy": "invoice_follow_up",
        "requires_assignee": True,
    },
    "continue_wait_input_invoice": {
        "state": "WAIT_INPUT_INVOICE",
        "allowed_next_events": ["ADD_INPUT_INVOICE", "CONFIRM_NO_INVOICE_PART", "CANCEL"],
        "default_due_policy": "invoice_follow_up",
        "requires_assignee": True,
    },
    "confirm_extra_invoice_owner": {
        "state": "EXTRA_INVOICE_OWNER_REVIEW",
        "allowed_next_events": ["CONFIRM_OWNER", "ADD_OA", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
    "wait_bank_payment": {
        "state": "WAIT_BANK_PAYMENT",
        "allowed_next_events": ["ADD_BANK_PAYMENT", "CANCEL", "MANUAL_CLOSE"],
        "default_due_policy": "payment_follow_up",
        "requires_assignee": True,
    },
    "confirm_payable_or_installment": {
        "state": "PAYABLE_OR_INSTALLMENT_REVIEW",
        "allowed_next_events": ["ADD_BANK_PAYMENT", "CONFIRM_INSTALLMENT", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": "payment_follow_up",
        "requires_assignee": True,
    },
    "confirm_overpayment_recovery": {
        "state": "OVERPAYMENT_RECOVERY",
        "allowed_next_events": ["ADD_REFUND_INCOME", "CONFIRM_RECOVERED", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": "recovery_follow_up",
        "requires_assignee": True,
    },
    "request_missing_oa": {
        "state": "WAIT_OA",
        "allowed_next_events": ["ADD_OA", "CONFIRM_OA_EXEMPT", "CANCEL"],
        "default_due_policy": "oa_follow_up",
        "requires_assignee": True,
    },
    "confirm_oa_exempt_auto": {
        "state": "OA_EXEMPT_CLOSED",
        "allowed_next_events": ["REOPEN", "MANUAL_REVIEW"],
        "default_due_policy": None,
        "requires_assignee": False,
    },
    "confirm_oa_exempt_manual": {
        "state": "OA_EXEMPT_REVIEW",
        "allowed_next_events": ["CONFIRM_OA_EXEMPT", "ADD_OA", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
    "manual_review": {
        "state": "MANUAL_REVIEW",
        "allowed_next_events": ["ADD_EVIDENCE", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
    "confirm_income_closed": {
        "state": "INCOME_CLOSED",
        "allowed_next_events": ["REOPEN"],
        "default_due_policy": None,
        "requires_assignee": False,
    },
    "wait_output_invoice": {
        "state": "WAIT_OUTPUT_INVOICE",
        "allowed_next_events": ["ADD_OUTPUT_INVOICE", "CONFIRM_NO_INVOICE_INCOME", "CANCEL"],
        "default_due_policy": "output_invoice_follow_up",
        "requires_assignee": True,
    },
    "confirm_no_invoice_income": {
        "state": "NO_INVOICE_INCOME_REVIEW",
        "allowed_next_events": ["CONFIRM_NO_INVOICE_INCOME", "ADD_OUTPUT_INVOICE", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
    "wait_collection": {
        "state": "WAIT_COLLECTION",
        "allowed_next_events": ["ADD_INCOME_BANK", "CONFIRM_BAD_DEBT", "CANCEL"],
        "default_due_policy": "collection_follow_up",
        "requires_assignee": True,
    },
    "confirm_refund_or_more_invoice": {
        "state": "REFUND_OR_MORE_OUTPUT_INVOICE",
        "allowed_next_events": ["ADD_REFUND_PAYMENT", "ADD_OUTPUT_INVOICE", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": "income_difference_follow_up",
        "requires_assignee": True,
    },
    "confirm_output_invoice_void_or_red": {
        "state": "OUTPUT_INVOICE_VOID_OR_RED",
        "allowed_next_events": ["ADD_RED_INVOICE", "CONFIRM_VOIDED", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
    "income_data_anomaly_manual_review": {
        "state": "DATA_ANOMALY",
        "allowed_next_events": ["FIX_DIRECTION", "REMOVE_OA", "MANUAL_CLOSE", "CANCEL"],
        "default_due_policy": None,
        "requires_assignee": True,
    },
}

SCENARIO_LABELS: dict[str, str] = {
    "data_anomaly_unknown_direction": "方向不明，需人工复核",
    "income_contains_oa_data_anomaly": "收入侧选择包含 OA，需修正分类",
    "expense_only_oa": "只有 OA",
    "expense_only_bank": "只有支出流水",
    "expense_only_bank_auto_oa_exempt": "支出流水命中自动免 OA",
    "expense_only_input_invoice": "只有进项发票",
    "expense_oa_bank_missing_input_invoice_equal": "OA 和支出流水一致，缺进项发票",
    "expense_oa_bank_missing_input_invoice_oa_more": "OA 大于支出流水，缺进项发票",
    "expense_oa_bank_missing_input_invoice_bank_more": "支出流水大于 OA，缺进项发票",
    "expense_oa_input_invoice_missing_bank_equal": "OA 和进项发票一致，缺支出流水",
    "expense_oa_input_invoice_missing_bank_oa_more": "OA 大于进项发票，缺支出流水",
    "expense_oa_input_invoice_missing_bank_invoice_more": "进项发票大于 OA，缺支出流水",
    "expense_bank_input_invoice_missing_oa_equal": "支出流水和进项发票一致，缺 OA",
    "expense_bank_input_invoice_missing_oa_bank_more": "支出流水大于进项发票，缺 OA",
    "expense_bank_input_invoice_missing_oa_invoice_more": "进项发票大于支出流水，缺 OA",
    "expense_all_equal": "OA、支出流水、进项发票金额一致",
    "expense_oa_bank_equal_input_invoice_less": "OA 和支出流水一致，进项发票金额较少",
    "expense_oa_bank_equal_input_invoice_more": "OA 和支出流水一致，进项发票金额较多",
    "expense_oa_input_invoice_equal_bank_less": "OA 和进项发票一致，支出流水金额较少",
    "expense_oa_input_invoice_equal_bank_more": "OA 和进项发票一致，支出流水金额较多",
    "expense_bank_input_invoice_equal_oa_less": "支出流水和进项发票一致，OA 金额较少",
    "expense_bank_input_invoice_equal_oa_more": "支出流水和进项发票一致，OA 金额较多",
    "expense_all_different": "OA、支出流水、进项发票金额均不一致",
    "income_only_bank": "只有收入流水",
    "income_only_output_invoice": "只有销项发票",
    "income_bank_output_invoice_equal": "收入流水和销项发票一致",
    "income_bank_more_than_output_invoice": "收入流水大于销项发票",
    "income_output_invoice_more_than_bank": "销项发票大于收入流水",
}


def action(action_code: str, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    definition = deepcopy(ACTION_DEFINITIONS[action_code])
    definition["action_code"] = action_code
    if payload is not None:
        definition["payload"] = deepcopy(payload)
    if action_code == "confirm_oa_exempt_manual":
        definition["payload_template"] = manual_oa_exemption_template()
    return definition


def workflow_for_action(action_code: str) -> dict[str, Any]:
    return deepcopy(WORKFLOW_BY_ACTION[action_code])


def scenario_label(scenario_code: str) -> str:
    return SCENARIO_LABELS.get(scenario_code, scenario_code)


def manual_oa_exemption_template() -> dict[str, Any]:
    return {
        "relation_mode": "oa_exempt",
        "oa_exemption": {
            "source": "manual",
            "reason_code": "manual_confirmed",
            "reason_label": "人工确认免 OA",
            "rule_code": None,
            "rule_version": RULE_VERSION,
            "evidence": {},
            "confirmed_by": None,
            "confirmed_at": None,
            "note": None,
        },
        "display_tags": ["人工免OA"],
    }
