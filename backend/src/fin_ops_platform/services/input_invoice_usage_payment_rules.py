from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Callable, Protocol

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


class InputInvoiceUsagePaymentRulesProvider(Protocol):
    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]: ...

    def rules_source_version(self) -> int: ...

    def evaluate(self, context: PaymentStatusEvaluationContext) -> dict[str, str]: ...


DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "id": "cash_turnover_chen_xiuyun",
        "statusCode": "cash_turnover",
        "label": "现金往来",
        "description": "陈秀云 OA + 流水 + 关联台完全匹配",
        "reason": "自动识别陈秀云 OA，有流水且完全匹配",
        "priority": 1,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": True, "fullyMatched": True, "applicantName": "陈秀云"},
    },
    {
        "id": "paid_full_match",
        "statusCode": "paid",
        "label": "已付款",
        "description": "有 OA、有流水，并且关联台完全匹配",
        "reason": "自动识别有 OA 有流水且完全匹配",
        "priority": 2,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": True, "fullyMatched": True},
    },
    {
        "id": "offset_zhou_jieying",
        "statusCode": "offset_zhou_jieying",
        "label": "冲",
        "description": "周洁莹 OA、无流水，发票和 OA 金额匹配",
        "reason": "自动识别周洁莹 OA，无流水且金额匹配",
        "priority": 3,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantName": "周洁莹", "invoiceOaAmountMatched": True},
    },
    {
        "id": "offset_liu_shugang_no_pay",
        "statusCode": "offset_liu_shugang_no_pay",
        "label": "冲",
        "description": "刘树刚不付 OA、无流水",
        "reason": "自动识别刘树刚不付 OA，无流水",
        "priority": 4,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantName": "刘树刚不付"},
    },
    {
        "id": "offset_wei_dailian",
        "statusCode": "offset_wei_dailian",
        "label": "冲",
        "description": "韦代连 OA、无流水",
        "reason": "自动识别韦代连 OA，无流水",
        "priority": 5,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False, "applicantName": "韦代连"},
    },
    {
        "id": "waiting_payment",
        "statusCode": "waiting_payment",
        "label": "待付款",
        "description": "有 OA、无流水",
        "reason": "自动识别有 OA 无流水",
        "priority": 6,
        "enabled": True,
        "conditions": {"hasOa": True, "hasBank": False},
    },
    {
        "id": "pending_default",
        "statusCode": "pending",
        "label": "待处理",
        "description": "规则不能自动闭环",
        "reason": "规则不能自动闭环",
        "priority": 7,
        "enabled": True,
        "conditions": {"fallback": True},
    },
]

DEFAULT_PENDING_DIRECTIONS: list[dict[str, str]] = [
    {"code": "pending", "label": "待处理"},
    {"code": "wei_dailian_batch_reverse", "label": "韦代连批量反提oa"},
    {"code": "chen_xiuyun_batch_reverse", "label": "陈秀云批量反提oa"},
    {"code": "zhou_jieying_batch_reverse", "label": "周洁莹批量反提oa"},
    {"code": "liu_shugang_pay_batch_reverse", "label": "刘树刚付批量反提oa"},
    {"code": "liu_shugang_no_pay_batch_reverse", "label": "刘树刚不付批量反提oa"},
    {"code": "liu_hanjing_batch_reverse", "label": "刘涵静批量反提oa"},
]

_DEFAULT_RULES_BY_ID = {str(rule["id"]): rule for rule in DEFAULT_RULES}
_DEFAULT_PENDING_CODES = {str(item["code"]) for item in DEFAULT_PENDING_DIRECTIONS}
_SUPPORTED_APPLICANTS = {
    str(rule.get("conditions", {}).get("applicantName"))
    for rule in DEFAULT_RULES
    if str(rule.get("conditions", {}).get("applicantName") or "").strip()
}


class AppSettingsInputInvoiceUsagePaymentRulesProvider:
    def __init__(self, *, state_store: Any | None, audit_service: Any | None = None) -> None:
        self._state_store = state_store
        self._audit_service = audit_service

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
        after_saved: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, Any]:
        if self._state_store is None:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "input_invoice_usage_payment_rules_read_only",
                "Input invoice usage payment status rules are read-only in this runtime.",
            )
        request = payload if isinstance(payload, dict) else {}
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
            "pendingDirections": desired["pendingDirections"],
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
        self._state_store.save_app_settings(next_payload)
        event = {
            "scope_type": "input_invoice_usage",
            "scope_key": "all",
            "reason": "payment_status_rules_updated",
            "old_version": int(current["version"]),
            "new_version": int(next_settings["version"]),
        }
        self._record_audit(actor_id=actor_id, event=event, before=current, after=next_settings)
        if after_saved is not None:
            after_saved(dict(event))
        return response

    def _current_settings(self) -> dict[str, Any]:
        return normalize_payment_status_rules_settings(self._load_app_settings().get(SETTINGS_KEY))

    def _load_app_settings(self) -> dict[str, Any]:
        if self._state_store is None:
            return {}
        load = getattr(self._state_store, "load_app_settings", None)
        if not callable(load):
            return {}
        payload = load()
        return payload if isinstance(payload, dict) else {}

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
                "pending_directions_changed": before.get("pendingDirections") != after.get("pendingDirections"),
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
    raw = value if isinstance(value, dict) else {}
    version = _optional_positive_int(raw.get("version"), DEFAULT_VERSION)
    raw_rules = raw.get("rules") if isinstance(raw.get("rules"), list) else DEFAULT_RULES
    raw_pending = raw.get("pendingDirections") if isinstance(raw.get("pendingDirections"), list) else raw.get("pending_directions")
    if not isinstance(raw_pending, list):
        raw_pending = DEFAULT_PENDING_DIRECTIONS
    rules = _normalize_rules(
        raw_rules,
        require_complete=False,
        exact_conditions=_has_complete_rule_set(raw_rules),
    )
    pending_directions = _normalize_pending_directions(raw_pending, require_complete=False)
    return {
        "version": version,
        "rules": rules,
        "pendingDirections": pending_directions,
        "idempotencyRecords": _normalize_idempotency_records(raw.get("idempotencyRecords")),
    }


def normalize_payment_status_rules_update(
    payload: dict[str, Any],
    *,
    current_settings: dict[str, Any],
) -> dict[str, Any]:
    current_rules_by_id = {
        str(rule.get("id")): rule
        for rule in current_settings.get("rules", [])
        if isinstance(rule, dict) and str(rule.get("id") or "").strip()
    }
    return {
        "rules": _normalize_rules(
            payload.get("rules"),
            require_complete=True,
            current_rules_by_id=current_rules_by_id,
            exact_conditions=True,
        ),
        "pendingDirections": _normalize_pending_directions(payload.get("pendingDirections"), require_complete=True),
    }


def public_payment_status_rules_payload(
    settings: dict[str, Any],
    *,
    read_only: bool,
    can_save: bool,
) -> dict[str, Any]:
    normalized = normalize_payment_status_rules_settings(settings)
    return {
        "version": int(normalized["version"]),
        "readOnly": bool(read_only),
        "rules": deepcopy(normalized["rules"]),
        "pendingDirections": deepcopy(normalized["pendingDirections"]),
        "permissions": {"canSave": bool(can_save), "can_save": bool(can_save)},
        "sourceMetadata": {
            "settingsKey": SETTINGS_KEY,
            "source": "app_settings" if not read_only else "default_rules",
            "sourceVersionField": "input_invoice_usage_payment_rules_version",
        },
    }


def evaluate_payment_status(settings: dict[str, Any], context: PaymentStatusEvaluationContext) -> dict[str, str]:
    normalized = normalize_payment_status_rules_settings(settings)
    fallback: dict[str, Any] | None = None
    for rule in sorted(normalized["rules"], key=lambda item: (int(item["priority"]), str(item["id"]))):
        if not bool(rule.get("enabled", True)):
            continue
        conditions = rule.get("conditions") if isinstance(rule.get("conditions"), dict) else {}
        if conditions.get("fallback") is True:
            fallback = rule
            continue
        if _conditions_match(conditions, context):
            return _status_payload(rule)
    return _status_payload(fallback or _DEFAULT_RULES_BY_ID["pending_default"])


def _normalize_rules(
    value: Any,
    *,
    require_complete: bool,
    current_rules_by_id: dict[str, dict[str, Any]] | None = None,
    exact_conditions: bool = False,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        if require_complete:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "input_invoice_usage_payment_rules_required",
                "Payment status rules must be a complete rules array.",
            )
        value = DEFAULT_RULES
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_priorities: set[int] = set()
    for item in value:
        if not isinstance(item, dict):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_payment_rule",
                "Each payment status rule must be an object.",
            )
        rule_id = str(item.get("id") or "").strip()
        default = _DEFAULT_RULES_BY_ID.get(rule_id)
        if default is None:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "unknown_input_invoice_usage_payment_rule",
                f"Unsupported payment status rule id: {rule_id}",
                details={"ruleId": rule_id},
            )
        if rule_id in seen_ids:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "duplicate_input_invoice_usage_payment_rule",
                f"Duplicate payment status rule id: {rule_id}",
                details={"ruleId": rule_id},
            )
        seen_ids.add(rule_id)
        priority = _required_int(item.get("priority", default["priority"]), "priority", "invalid_input_invoice_usage_payment_rule_priority")
        if priority in seen_priorities:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "duplicate_input_invoice_usage_payment_rule_priority",
                f"Duplicate payment status rule priority: {priority}",
                details={"priority": priority},
            )
        seen_priorities.add(priority)
        current_rule = (current_rules_by_id or {}).get(rule_id) if exact_conditions else None
        if exact_conditions and "conditions" not in item and isinstance(current_rule, dict):
            conditions_value = current_rule.get("conditions", default.get("conditions"))
        else:
            conditions_value = item.get("conditions", default.get("conditions"))
        conditions = _normalize_conditions(rule_id, conditions_value, exact=exact_conditions)
        normalized.append(
            {
                "id": rule_id,
                "statusCode": str(default["statusCode"]),
                "label": _required_text(item.get("label", default["label"]), "label", "invalid_input_invoice_usage_payment_rule_label"),
                "description": _required_text(
                    item.get("description", default["description"]),
                    "description",
                    "invalid_input_invoice_usage_payment_rule_description",
                ),
                "reason": str(item.get("reason") or default["reason"]).strip() or str(default["reason"]),
                "priority": priority,
                "enabled": bool(item.get("enabled", default.get("enabled", True))),
                "conditions": conditions,
            }
        )
    if require_complete and seen_ids != set(_DEFAULT_RULES_BY_ID):
        missing = sorted(set(_DEFAULT_RULES_BY_ID).difference(seen_ids))
        raise InputInvoiceUsagePaymentRulesValidationError(
            "incomplete_input_invoice_usage_payment_rules",
            "Payment status rules update must include every supported rule.",
            details={"missingRuleIds": missing},
        )
    if not require_complete:
        existing = {str(rule["id"]) for rule in normalized}
        for default in DEFAULT_RULES:
            if str(default["id"]) not in existing:
                normalized.append(deepcopy(default))
    return sorted(normalized, key=lambda item: (int(item["priority"]), str(item["id"])))


def _has_complete_rule_set(value: Any) -> bool:
    if not isinstance(value, list):
        return False
    rule_ids = {
        str(item.get("id") or "").strip()
        for item in value
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    return rule_ids == set(_DEFAULT_RULES_BY_ID)


def _normalize_conditions(rule_id: str, value: Any, *, exact: bool = False) -> dict[str, Any]:
    default_conditions = deepcopy(_DEFAULT_RULES_BY_ID[rule_id].get("conditions") or {})
    conditions = value if isinstance(value, dict) else default_conditions
    applicant = str(conditions.get("applicantName") or "").strip()
    default_applicant = str(default_conditions.get("applicantName") or "").strip()
    if default_applicant:
        if applicant and applicant != default_applicant:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "unsupported_input_invoice_usage_payment_rule_constraint",
                "Unsupported applicant constraint for input invoice usage payment rule.",
                details={"ruleId": rule_id, "applicantName": applicant},
            )
        if exact and not applicant:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "unsupported_input_invoice_usage_payment_rule_constraint",
                "Unsupported applicant constraint for input invoice usage payment rule.",
                details={"ruleId": rule_id, "applicantName": applicant},
            )
    elif applicant:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "unsupported_input_invoice_usage_payment_rule_constraint",
            "Unsupported applicant constraint for input invoice usage payment rule.",
            details={"ruleId": rule_id, "applicantName": applicant},
        )
    if conditions.get("fallback") is True and default_conditions.get("fallback") is not True:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "unsupported_input_invoice_usage_payment_rule_constraint",
            "Only the pending default rule can be configured as fallback.",
            details={"ruleId": rule_id},
        )
    normalized = {} if exact else deepcopy(default_conditions)
    for key in ("hasOa", "hasBank", "fullyMatched", "invoiceOaAmountMatched", "fallback"):
        if key in conditions:
            normalized[key] = bool(conditions[key])
    if default_conditions.get("fallback") is True:
        normalized["fallback"] = True
    if default_applicant:
        normalized["applicantName"] = default_applicant
    if normalized.get("fallback") is not True and not any(
        key in normalized
        for key in ("hasOa", "hasBank", "fullyMatched", "invoiceOaAmountMatched", "applicantName")
    ):
        raise InputInvoiceUsagePaymentRulesValidationError(
            "empty_input_invoice_usage_payment_rule_conditions",
            "Payment status rule conditions cannot be empty.",
            details={"ruleId": rule_id},
        )
    return normalized


def _normalize_pending_directions(value: Any, *, require_complete: bool) -> list[dict[str, str]]:
    if not isinstance(value, list):
        if require_complete:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "input_invoice_usage_pending_directions_required",
                "Pending directions must be a complete array.",
            )
        value = DEFAULT_PENDING_DIRECTIONS
    normalized: list[dict[str, str]] = []
    seen_codes: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise InputInvoiceUsagePaymentRulesValidationError(
                "invalid_input_invoice_usage_pending_direction",
                "Each pending direction must be an object.",
            )
        code = str(item.get("code") or "").strip()
        if code not in _DEFAULT_PENDING_CODES:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "unknown_input_invoice_usage_pending_direction",
                f"Unsupported pending direction code: {code}",
                details={"code": code},
            )
        if code in seen_codes:
            raise InputInvoiceUsagePaymentRulesValidationError(
                "duplicate_input_invoice_usage_pending_direction",
                f"Duplicate pending direction code: {code}",
                details={"code": code},
            )
        seen_codes.add(code)
        normalized.append(
            {
                "code": code,
                "label": _required_text(item.get("label"), "label", "invalid_input_invoice_usage_pending_direction_label"),
            }
        )
    if require_complete and seen_codes != _DEFAULT_PENDING_CODES:
        raise InputInvoiceUsagePaymentRulesValidationError(
            "incomplete_input_invoice_usage_pending_directions",
            "Pending directions update must include every supported direction.",
            details={"missingCodes": sorted(_DEFAULT_PENDING_CODES.difference(seen_codes))},
        )
    if not require_complete:
        for default in DEFAULT_PENDING_DIRECTIONS:
            if str(default["code"]) not in seen_codes:
                normalized.append(dict(default))
    order = {str(item["code"]): index for index, item in enumerate(DEFAULT_PENDING_DIRECTIONS)}
    return sorted(normalized, key=lambda item: order.get(str(item["code"]), 999))


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
    applicant = str(conditions.get("applicantName") or "").strip()
    if applicant and applicant != context.applicant_name:
        return False
    return True


def _status_payload(rule: dict[str, Any]) -> dict[str, str]:
    code = str(rule.get("statusCode") or "pending")
    return {
        "code": code,
        "label": str(rule.get("label") or "待处理"),
        "reason": str(rule.get("reason") or rule.get("description") or "规则不能自动闭环"),
        "matchedRuleId": str(rule.get("id") or "pending_default"),
        "severity": "warning" if code == "pending" else "success",
    }


def _required_text(value: Any, field: str, error_code: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} is required.")
    return normalized


def _required_int(value: Any, field: str, error_code: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be an integer.") from exc
    if number < 1:
        raise InputInvoiceUsagePaymentRulesValidationError(error_code, f"{field} must be a positive integer.")
    return number


def _optional_positive_int(value: Any, default: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


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
    before_rules = {str(rule.get("id")): rule for rule in list(before.get("rules") or []) if isinstance(rule, dict)}
    changed: list[str] = []
    for rule in list(after.get("rules") or []):
        if not isinstance(rule, dict):
            continue
        rule_id = str(rule.get("id"))
        if before_rules.get(rule_id) != rule:
            changed.append(rule_id)
    return changed
