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


class InputInvoiceUsagePaymentRulesProvider(Protocol):
    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]: ...

    def rules_source_version(self) -> int: ...

    def evaluate(self, context: PaymentStatusEvaluationContext) -> dict[str, str]: ...


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
        "label": "已付款",
        "priority": 2,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": True, "fullyMatched": True},
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

OUTPUT_PARENTS = {"cash_turnover": "paid", "paid": "paid", "offset": "unpaid", "waiting_payment": "unpaid",
                  "invoice_less_payment": "paid", "invoice_greater_payment": "paid"}
OUTPUT_STATUS_CODES = frozenset(OUTPUT_PARENTS)
AMOUNT_CATEGORIES = {"paid": "发票＝付款", "invoice_less_payment": "发票＜付款", "invoice_greater_payment": "发票＞付款"}


def payment_category_parent(rule: dict[str, Any]) -> str:
    code = rule["statusCode"]
    return OUTPUT_PARENTS[code] if code in OUTPUT_PARENTS else rule["parentStatus"]


def payment_categories(settings: dict[str, Any]) -> list[dict[str, str]]:
    categories = {code: {"id": code, "label": label, "parent": "paid"} for code, label in AMOUNT_CATEGORIES.items()}
    for rule in settings["rules"]:
        code = rule["statusCode"]
        label = "发票＝付款" if code == "paid" and rule["label"] == "已付款" else rule["label"]
        categories[code] = {"id": code, "label": label, "parent": payment_category_parent(rule)}
    return list(categories.values())


def classification_tree(settings: dict[str, Any], counts: dict[str, int]) -> dict[str, Any]:
    groups = []
    for parent, label in (("paid", "已付款"), ("unpaid", "未付款")):
        children = [{"id": "category:" + item["id"], "label": item["label"], "count": counts.get(item["id"], 0)}
                    for item in payment_categories(settings) if item["parent"] == parent]
        groups.append({"id": parent, "label": label, "tone": parent,
                       "count": sum(item["count"] for item in children), "children": children})
    groups.append({"id": "pending", "label": "待核对", "tone": "pending", "count": counts.get("pending", 0), "children": []})
    used = sum(item["count"] for item in groups)
    unused = counts.get("unused", 0)
    return {"all": {"id": "all", "label": "全部发票", "count": used + unused},
            "used": {"id": "used", "label": "已使用", "count": used},
            "unused": {"id": "unused", "label": "待使用", "count": unused}, "groups": groups,
            "version": settings["version"]}



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
            {**deepcopy(rule), "parentStatus": payment_category_parent(rule), "description": condition_description(rule["conditions"]),
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
        if payment_category_parent(rule) == "paid" and context.payment_comparison == "invalid":
            continue
        expected = {"paid": "equal", "invoice_less_payment": "less", "invoice_greater_payment": "greater"}.get(rule["statusCode"])
        if expected and context.payment_comparison != expected:
            continue
        if rule["enabled"] and _conditions_match(rule["conditions"], context):
            return _status_payload(rule)
    comparison_code = {"equal": "paid", "less": "invoice_less_payment", "greater": "invoice_greater_payment"}.get(context.payment_comparison)
    if comparison_code:
        return {"code": comparison_code, "label": next(item["label"] for item in payment_categories(normalized) if item["id"] == comparison_code),
                "reason": "正式关联组发票与支出流水金额比较", "matchedRuleId": "", "severity": "success"}
    if not context.has_oa:
        reason = "缺少 OA 关联；已有流水" if context.has_bank else "缺少 OA 和流水关联"
    else:
        reason = "缺少流水关联" if not context.has_bank else "付款金额或支付条件待核对"
    return {"code": "pending", "label": "待核对", "reason": reason,
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
    parents_by_code: dict[str, str] = {}
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
        parent = item.get("parentStatus", OUTPUT_PARENTS.get(code))
        if not isinstance(parent, str) or parent not in {"paid", "unpaid"} or (code in OUTPUT_PARENTS and parent != OUTPUT_PARENTS[code]):
            raise InputInvoiceUsagePaymentRulesValidationError("invalid_payment_category_parent", "分类父级无效。")
        if code in parents_by_code and parents_by_code[code] != parent:
            raise InputInvoiceUsagePaymentRulesValidationError("conflicting_payment_category_parent", "同一分类必须属于同一父级。")
        parents_by_code[code] = parent
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
        if code not in OUTPUT_PARENTS:
            normalized_rule["parentStatus"] = parent
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
    if set(value) - {*bool_keys, "applicantNames", "paymentComparison"}:
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
        elif key == "paymentComparison":
            if not isinstance(item, str) or item not in {"equal", "less", "greater"}:
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
        parts.append({"equal": "发票＝付款", "less": "发票＜付款", "greater": "发票＞付款"}[conditions["paymentComparison"]])
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
    if "paymentComparison" in conditions and conditions["paymentComparison"] != context.payment_comparison:
        return False
    applicants = conditions.get("applicantNames", [])
    if applicants and normalize_applicant_name(context.applicant_name) not in applicants:
        return False
    return True


def _status_payload(rule: dict[str, Any]) -> dict[str, str]:
    return {
        "code": rule["statusCode"], "label": "发票＝付款" if rule["statusCode"] == "paid" and rule["label"] == "已付款" else rule["label"],
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
