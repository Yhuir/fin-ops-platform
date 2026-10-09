from __future__ import annotations

import json
import re
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Protocol

SETTINGS_KEY = "input_invoice_usage_payment_status_rules"
DEFAULT_VERSION = 1
IDEMPOTENCY_LIMIT = 100


class InputInvoiceUsagePaymentRulesValidationError(ValueError):
    def __init__(self, error_code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


@dataclass(frozen=True)
class PaymentStatusEvaluationContext:
    has_oa: bool
    has_bank: bool
    applicant_name: str
    fully_matched: bool
    invoice_oa_amount_matched: bool
    payment_comparison: str
    invoice_net_sign: str | None = None


class InputInvoiceUsagePaymentRulesProvider(Protocol):
    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]: ...

    def rules_source_version(self) -> int: ...

    def evaluate(self, context: PaymentStatusEvaluationContext) -> dict[str, str]: ...


# Rule operators match existing fact states; absent/invalid facts never match.
PAYMENT_COMPARISON_STATES = {
    "equal": ("equal",), "less": ("less",), "greater": ("greater",),
    "less_equal": ("less", "equal"), "greater_equal": ("greater", "equal"),
}
INVOICE_NET_SIGN_STATES = {
    "positive": ("positive",), "zero": ("zero",), "negative": ("negative",),
    "nonnegative": ("positive", "zero"), "nonpositive": ("negative", "zero"),
}


DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "id": "cash_turnover_chen_xiuyun",
        "statusCode": "cash_turnover",
        "label": "现金往来",
        "priority": 1,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": True, "fullyMatched": True, "applicantNames": ["陈秀云"]},
    },
    {
        "id": "paid_full_match",
        "statusCode": "paid",
        "label": "发票＝付款",
        "priority": 2,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": True, "fullyMatched": True, "paymentComparison": "equal"},
    },
    {
        "id": "offset_zhou_jieying",
        "statusCode": "offset",
        "label": "冲",
        "priority": 3,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantNames": ["周洁莹"], "invoiceOaAmountMatched": True},
    },
    {
        "id": "offset_liu_shugang_no_pay",
        "statusCode": "offset",
        "label": "冲",
        "priority": 4,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantNames": ["刘树刚"]},
    },
    {
        "id": "offset_wei_dailian",
        "statusCode": "offset",
        "label": "冲",
        "priority": 5,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantNames": ["韦代连"]},
    },
    {
        "id": "waiting_payment",
        "statusCode": "waiting_payment",
        "label": "未关联流水",
        "priority": 6,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False},
    },
]

# Base classifications are normal editable rules, never evaluator branches.
DEFAULT_RULES.extend([
    {"id": "base_paid_equal", "statusCode": "paid", "label": "发票＝付款", "priority": 7, "enabled": True,
     "conditions": {"hasBank": True, "paymentComparison": "equal"}},
    {"id": "base_paid_less", "statusCode": "invoice_less_payment", "label": "发票＜付款", "priority": 8, "enabled": True,
     "conditions": {"hasBank": True, "paymentComparison": "less"}},
    {"id": "base_paid_greater", "statusCode": "invoice_greater_payment", "label": "发票＞付款", "priority": 9, "enabled": True,
     "conditions": {"hasBank": True, "paymentComparison": "greater"}},
    {"id": "base_unpaid", "statusCode": "waiting_payment", "label": "未关联流水", "priority": 10, "enabled": True,
     "conditions": {"hasBank": False}},
])
OUTPUT_STATUS_CODES = frozenset({"cash_turnover", "paid", "offset", "waiting_payment",
                                 "invoice_less_payment", "invoice_greater_payment"})


def payment_category_parents(rule: dict[str, Any]) -> tuple[str, ...]:
    """Possible destinations depend on conditions; the actual bank relation decides each row."""
    conditions = rule["conditions"]
    if conditions.get("hasBank") is True or conditions.get("fullyMatched") is True or "paymentComparison" in conditions:
        return ("paid",)
    if conditions.get("hasBank") is False:
        return ("unpaid",)
    return ("paid", "unpaid")


def payment_categories(settings: dict[str, Any]) -> list[dict[str, str]]:
    categories = {}
    for rule in settings["rules"]:
        for parent in payment_category_parents(rule):
            categories[(rule["statusCode"], parent)] = {"id": rule["statusCode"], "label": rule["label"], "parent": parent}
    return list(categories.values())


def classification_tree(settings: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    groups = []
    for parent, label in (("paid", "已付款"), ("unpaid", "未付款")):
        children = [{"id": f"category:{item['id']}", "label": item["label"],
                     "count": counts.get(f"{parent}:{item['id']}", 0)}
                    for item in payment_categories(settings) if item["parent"] == parent]
        groups.append({"id": parent, "label": label, "tone": parent,
                       "count": counts.get(parent, 0), "children": children})
    return {key: {"id": key, "label": label, "count": counts.get(key, 0)}
            for key, label in (("all", "全部发票"), ("used", "已使用"), ("unused", "待使用"))} | {
                "groups": groups, "version": settings["version"]}


class AppSettingsInputInvoiceUsagePaymentRulesProvider:
    def __init__(
        self, *, state_store: Any | None, audit_service: Any | None = None,
        transaction_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._state_store = state_store
        self._audit_service = audit_service
        self._transaction_factory = transaction_factory

    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]:
        return public_payment_status_rules_payload(
            self._current_settings(),
            read_only=self._state_store is None,
            can_save=bool(can_save and self._state_store is not None),
        )

    def rules_source_version(self) -> int:
        return int(self._current_settings()["version"])

    def evaluate(self, context: PaymentStatusEvaluationContext) -> dict[str, str]:
        return evaluate_payment_status(self._current_settings(), context)

    def update_payment_status_rules(
        self,
        payload: dict[str, Any] | None,
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        if self._state_store is None:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "input_invoice_usage_payment_rules_read_only",
                "Input invoice usage payment status rules are read-only in this runtime.",
            )
        if self._transaction_factory is not None:
            with self._transaction_factory() as transaction:
                return self._update_payment_status_rules(payload, actor_id=actor_id, transaction=transaction)
        return self._update_payment_status_rules(payload, actor_id=actor_id)

    def _update_payment_status_rules(
        self, payload: dict[str, Any] | None, *, actor_id: str, transaction: Any | None = None,
    ) -> dict[str, Any]:
        request = payload if isinstance(payload, dict) else {}
        if transaction is not None:
            from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
            persisted_payload = PostgresOpsTaxEtcRepository(transaction).load_app_settings_for_update()
        else:
            persisted_payload = self._load_app_settings()
        current = normalize_payment_status_rules_settings(persisted_payload.get(SETTINGS_KEY))
        idempotency_key = _required_text(
            request.get("idempotencyKey", request.get("idempotency_key")),
            "idempotencyKey",
            "input_invoice_usage_payment_rules_idempotency_key_required",
        )
        desired = normalize_payment_status_rules_update(request, current_settings=current)
        fingerprint = _fingerprint(desired)
        idempotency_records = _normalize_idempotency_records(current.get("idempotencyRecords"))
        existing_record = idempotency_records.get(idempotency_key)
        if isinstance(existing_record, dict):
            if existing_record.get("fingerprint") != fingerprint:
                raise InputInvoiceUsagePaymentRulesValidationError(
                    "input_invoice_usage_payment_rules_idempotency_conflict",
                    "The same idempotency key was used with different payment rules payload.",
                )
            response = existing_record.get("response")
            if isinstance(response, dict):
                return deepcopy(response)

        expected_version = _required_int(
            request.get("expectedVersion", request.get("expected_version")),
            "expectedVersion",
            "input_invoice_usage_payment_rules_expected_version_required",
        )
        if expected_version != int(current["version"]):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "input_invoice_usage_payment_rules_version_conflict",
                "Input invoice usage payment status rules version conflict.",
                details={"expectedVersion": expected_version, "actualVersion": int(current["version"])},
            )

        next_settings = {
            "version": int(current["version"]) + 1,
            "rules": desired["rules"],
            "idempotencyRecords": idempotency_records,
        }
        response = public_payment_status_rules_payload(next_settings, read_only=False, can_save=True)
        next_settings["idempotencyRecords"] = _append_idempotency_record(
            idempotency_records,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            response=response,
        )
        next_payload = dict(persisted_payload)
        next_payload[SETTINGS_KEY] = next_settings
        if transaction is not None:
            persisted = self._state_store.save_app_settings_for_versioned_family_in_transaction(
                next_payload, family_key=SETTINGS_KEY, expected_version=current["version"], transaction=transaction,
            )
            if persisted is None:
                raise InputInvoiceUsagePaymentRulesValidationError(
                    "input_invoice_usage_payment_rules_version_conflict", "Payment rule version conflict.",
                )
            from fin_ops_platform.services.postgres_repositories.operations_audit import (
                PostgresOperationsAuditRepository,
            )
            PostgresOperationsAuditRepository(transaction).append_operation_event({
                "event_type": "operation.completed", "object_type": "app_settings", "object_id": SETTINGS_KEY,
                "actor_id": actor_id, "action": "input_invoice_usage_payment_status_rules_updated",
                "page_key": "input-invoice-usage", "operation_location": "进项发票使用情况/支付规则",
                "scope": "all", "payload": {"before": current, "after": next_settings},
            })
        else:
            self._state_store.save_app_settings(next_payload)
        event = {
            "scope_type": "input_invoice_usage",
            "scope_key": "all",
            "reason": "payment_status_rules_updated",
            "old_version": int(current["version"]),
            "new_version": int(next_settings["version"]),
        }
        if transaction is None:
            self._record_audit(actor_id=actor_id, event=event, before=current, after=next_settings)
        return response

    def _current_settings(self) -> dict[str, Any]:
        return normalize_payment_status_rules_settings(self._load_app_settings().get(SETTINGS_KEY))

    def _load_app_settings(self) -> dict[str, Any]:
        if self._state_store is None:
            return {}
        payload = self._state_store.load_app_settings()
        if not isinstance(payload, dict):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_payment_rules_settings", "Application settings must be an object.",
            )
        return payload

    def _record_audit(
        self,
        *,
        actor_id: str,
        event: dict[str, object],
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> None:
        if self._audit_service is None:
            return
        record_action = getattr(self._audit_service, "record_action", None)
        if not callable(record_action):
            return
        record_action(
            actor_id=str(actor_id or "input_invoice_usage_payment_rules"),
            action="input_invoice_usage_payment_status_rules_updated",
            entity_type="app_settings",
            entity_id=SETTINGS_KEY,
            metadata={
                "old_version": int(event["old_version"]),
                "new_version": int(event["new_version"]),
                "changed_rule_ids": _changed_rule_ids(before, after),
            },
        )


class PostgresInputInvoiceUsagePaymentRulesStateStore:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_app_settings(self) -> dict[str, Any]:
        fetch_one = getattr(self._connection, "fetch_one", None)
        if not callable(fetch_one):
            return {}
        row = fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s limit 1",
            ("app_settings",),
        )
        if not isinstance(row, dict):
            return {}
        payload = row.get("settings_payload")
        return payload if isinstance(payload, dict) else {}


def normalize_payment_status_rules_settings(value: Any) -> dict[str, Any]:
    # Absence is the initial configuration, not a recovery path for malformed settings.
    if value is None or value == {}:
        return {"version": DEFAULT_VERSION, "rules": _normalize_rules(DEFAULT_RULES), "idempotencyRecords": {}}
    if not isinstance(value, dict):
        raise InputInvoiceUsagePaymentRulesValidationError(
            "invalid_input_invoice_usage_payment_rules_settings", "Payment rule settings must be an object.",
        )
    if "pendingDirections" in value or "pending_directions" in value:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "input_invoice_usage_payment_rules_migration_required", "Payment rule configuration migration is required.",
        )
    return {
        "version": _required_int(value.get("version"), "version", "invalid_input_invoice_usage_payment_rules_version"),
        "rules": _normalize_rules(value.get("rules")),
        "idempotencyRecords": _normalize_idempotency_records(value.get("idempotencyRecords")),
    }


def normalize_payment_status_rules_update(
    payload: dict[str, Any], *, current_settings: dict[str, Any],
) -> dict[str, Any]:
    return {"rules": _normalize_rules(payload.get("rules"))}


def public_payment_status_rules_payload(
    settings: dict[str, Any], *, read_only: bool, can_save: bool,
) -> dict[str, Any]:
    normalized = normalize_payment_status_rules_settings(settings)
    return {
        "version": int(normalized["version"]),
        "readOnly": bool(read_only),
        "rules": [
            {**deepcopy(rule), "description": condition_description(rule["conditions"]),
             "reason": condition_description(rule["conditions"])}
            for rule in normalized["rules"]
        ],
        "permissions": {"canSave": bool(can_save), "can_save": bool(can_save)},
        "sourceMetadata": {
            "settingsKey": SETTINGS_KEY,
            "source": "app_settings" if not read_only else "default_rules",
            "sourceVersionField": "input_invoice_usage_payment_rules_version",
        },
    }


def evaluate_payment_status(settings: dict[str, Any], context: PaymentStatusEvaluationContext) -> dict[str, str]:
    normalized = normalize_payment_status_rules_settings(settings)
    for rule in normalized["rules"]:
        if rule["enabled"] and _conditions_match(rule["conditions"], context):
            return _status_payload(rule)
    reason = {
        "missing_invoice_amount": "关联发票缺少价税合计",
        "missing_bank_evidence": "关联银行流水明细缺失" if context.has_bank else "未命中已配置规则",
        "invalid_bank_amount": "关联流水金额或收支方向不完整",
        "ambiguous_bank_scope": "拆分流水的付款用途尚未明确",
        "invalid": "金额比较信息不完整",
    }.get(context.payment_comparison, "未命中已配置规则")
    return {"code": "unclassified", "label": "未分类", "reason": reason,
            "matchedRuleId": "", "severity": "warning"}


def _normalize_rules(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise InputInvoiceUsagePaymentRulesValidationError(
            "input_invoice_usage_payment_rules_required", "Payment status rules must be an array.",
        )
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_priorities: set[int] = set()
    labels_by_code: dict[str, str] = {}
    for item in value:
        if not isinstance(item, dict):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_payment_rule", "Each payment status rule must be an object.",
            )
        rule_id = _required_text(item.get("id"), "id", "invalid_input_invoice_usage_payment_rule_id")
        if rule_id in seen_ids:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "duplicate_input_invoice_usage_payment_rule", f"Duplicate payment status rule id: {rule_id}",
            )
        seen_ids.add(rule_id)
        priority = _required_int(item.get("priority"), "priority", "invalid_input_invoice_usage_payment_rule_priority")
        if priority in seen_priorities:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "duplicate_input_invoice_usage_payment_rule_priority", f"Duplicate payment status rule priority: {priority}",
            )
        seen_priorities.add(priority)
        code = item.get("statusCode")
        if not isinstance(code, str) or (code not in OUTPUT_STATUS_CODES and not re.fullmatch(r"custom_[a-z0-9_]{1,72}", code)):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_payment_rule_status", "Unsupported payment status output.",
            )
        enabled = item.get("enabled")
        if type(enabled) is not bool:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_payment_rule_enabled", "enabled must be a boolean.",
            )
        label = _required_text(item.get("label"), "label", "invalid_input_invoice_usage_payment_rule_label")
        if code in labels_by_code and labels_by_code[code] != label:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "conflicting_input_invoice_usage_payment_rule_labels", "Rules with the same output class must use the same display label.",
            )
        labels_by_code[code] = label
        normalized_rule = {
            "id": rule_id, "statusCode": code, "label": label, "priority": priority,
            "enabled": enabled, "conditions": _normalize_conditions(rule_id, item.get("conditions")),
        }
        normalized.append(normalized_rule)
    return sorted(normalized, key=lambda item: (item["priority"], item["id"]))


def normalize_applicant_name(value: str) -> str:
    """Match OA name text consistently; this is not an account identity."""
    return re.sub(r"[\s\u200b\ufeff]+", "", value)


def _normalize_conditions(rule_id: str, value: Any) -> dict[str, Any]:
    bool_keys = ("hasOa", "hasBank", "fullyMatched", "invoiceOaAmountMatched")
    if not isinstance(value, dict) or not value:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "empty_input_invoice_usage_payment_rule_conditions", "Payment status rule conditions cannot be empty.",
        )
    if set(value) - {*bool_keys, "applicantNames", "paymentComparison", "invoiceNetSign"}:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "unsupported_input_invoice_usage_payment_rule_constraint", "Unsupported payment rule condition.",
        )
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if key in bool_keys:
            if type(item) is not bool:
                raise InputInvoiceUsagePaymentRulesValidationError(
                    "invalid_input_invoice_usage_payment_rule_condition", f"{key} must be a boolean.",
                )
            normalized[key] = item
        elif key == "invoiceNetSign":
            if not isinstance(item, str) or item not in INVOICE_NET_SIGN_STATES:
                raise InputInvoiceUsagePaymentRulesValidationError("invalid_invoice_net_sign", "发票净额条件无效。")
            normalized[key] = item
        elif key == "paymentComparison":
            if not isinstance(item, str) or item not in PAYMENT_COMPARISON_STATES:
                raise InputInvoiceUsagePaymentRulesValidationError("invalid_payment_comparison", "金额比较条件无效。")
            normalized[key] = item
        else:
            if not isinstance(item, list) or not item or len(item) > 200:
                raise InputInvoiceUsagePaymentRulesValidationError(
                    "invalid_input_invoice_usage_payment_rule_applicant", "applicantNames must contain 1–200 names.",
                )
            names = [normalize_applicant_name(_required_text(name, key, "invalid_input_invoice_usage_payment_rule_applicant")) for name in item]
            if not all(names):
                raise InputInvoiceUsagePaymentRulesValidationError(
                    "invalid_input_invoice_usage_payment_rule_applicant", "Applicant names cannot be blank.",
                )
            normalized[key] = sorted(set(names))
    impossible = (
        ("paymentComparison" in normalized and normalized.get("hasBank") is False)
        or (normalized.get("fullyMatched") is True and normalized.get("paymentComparison") in {"less", "greater"})
        or
        (normalized.get("hasOa") is False and (normalized.get("applicantNames") or normalized.get("invoiceOaAmountMatched") is True))
        or (normalized.get("fullyMatched") is True and (
            normalized.get("hasOa") is False or normalized.get("hasBank") is False
            or normalized.get("invoiceOaAmountMatched") is False
        ))
    )
    if impossible:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "contradictory_input_invoice_usage_payment_rule_conditions", "Payment rule conditions contradict each other.",
            details={"ruleId": rule_id},
        )
    return normalized


def condition_description(conditions: dict[str, Any]) -> str:
    labels = {
        "hasOa": ("有 OA", "无 OA"), "hasBank": ("有流水", "无流水"),
        "fullyMatched": ("完全匹配", "未完全匹配"),
        "invoiceOaAmountMatched": ("发票与 OA 金额匹配", "发票与 OA 金额不匹配"),
    }
    parts = [f"申请人（任一）={'、'.join(conditions['applicantNames'])}"] if "applicantNames" in conditions else []
    parts.extend(pair[0] if conditions[key] else pair[1] for key, pair in labels.items() if key in conditions)
    if "paymentComparison" in conditions:
        parts.append({"equal": "发票＝付款", "less": "发票＜付款", "greater": "发票＞付款", "less_equal": "发票≤付款", "greater_equal": "发票≥付款"}[conditions["paymentComparison"]])
    if "invoiceNetSign" in conditions:
        parts.append({"positive": "发票净额为正", "zero": "发票净额为零", "negative": "发票净额为负", "nonnegative": "发票净额≥0", "nonpositive": "发票净额≤0"}[conditions["invoiceNetSign"]])
    return "；".join(parts)


def _conditions_match(conditions: dict[str, Any], context: PaymentStatusEvaluationContext) -> bool:
    checks = {
        "hasOa": context.has_oa,
        "hasBank": context.has_bank,
        "fullyMatched": context.fully_matched,
        "invoiceOaAmountMatched": context.invoice_oa_amount_matched,
    }
    for key, current_value in checks.items():
        if key in conditions and bool(conditions[key]) != bool(current_value):
            return False
    if "paymentComparison" in conditions and context.payment_comparison not in PAYMENT_COMPARISON_STATES[conditions["paymentComparison"]]:
        return False
    if "invoiceNetSign" in conditions and context.invoice_net_sign not in INVOICE_NET_SIGN_STATES[conditions["invoiceNetSign"]]:
        return False
    applicants = conditions.get("applicantNames", [])
    if applicants and normalize_applicant_name(context.applicant_name) not in applicants:
        return False
    return True


def _status_payload(rule: dict[str, Any]) -> dict[str, str]:
    return {
        "code": rule["statusCode"], "label": rule["label"],
        "reason": condition_description(rule["conditions"]),
        "matchedRuleId": rule["id"], "severity": "success",
    }


def _required_text(value: Any, field: str, error_code: str) -> str:
    if not isinstance(value, str):
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be text.")
    normalized = value.strip()
    if not normalized:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} is required.")
    return normalized


def _required_int(value: Any, field: str, error_code: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be an integer.")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be an integer.") from exc
    if number < 1:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be a positive integer.")
    return number


def _fingerprint(payload: dict[str, Any]) -> str:
    return sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _normalize_idempotency_records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    records: dict[str, dict[str, Any]] = {}
    for key, record in value.items():
        normalized_key = str(key).strip()
        if not normalized_key or not isinstance(record, dict):
            continue
        fingerprint = str(record.get("fingerprint") or "").strip()
        response = record.get("response")
        if fingerprint and isinstance(response, dict):
            records[normalized_key] = {"fingerprint": fingerprint, "response": deepcopy(response)}
    return records


def _append_idempotency_record(
    records: dict[str, dict[str, Any]],
    *,
    idempotency_key: str,
    fingerprint: str,
    response: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    next_records = dict(records)
    next_records[idempotency_key] = {"fingerprint": fingerprint, "response": deepcopy(response)}
    if len(next_records) <= IDEMPOTENCY_LIMIT:
        return next_records
    keep_keys = list(next_records.keys())[-IDEMPOTENCY_LIMIT:]
    return {key: next_records[key] for key in keep_keys}


def _changed_rule_ids(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_rules = {rule["id"]: rule for rule in before["rules"]}
    after_rules = {rule["id"]: rule for rule in after["rules"]}
    return sorted(rule_id for rule_id in before_rules.keys() | after_rules.keys() if before_rules.get(rule_id) != after_rules.get(rule_id))
