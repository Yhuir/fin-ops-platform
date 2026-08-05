from __future__ import annotations

from copy import deepcopy
from datetime import date
from typing import Any


ETC_OA_DRAFT_PREFILL_FAMILY = "etc"
INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY = "input_invoice_usage"

OA_APPLICATION_TYPE_OPTIONS = (
    ("s0", "设备货款及材料费"),
    ("s1", "人工费/劳务费/服务费"),
    ("s2", "住宿费"),
    ("s3", "招待费（餐费、烟酒等）"),
    ("s4", "交通费"),
    ("s5", "车辆使用费（汽油、过路、保险、维修、税费等）"),
    ("s6", "车辆维修"),
    ("s7", "运费/邮费/杂费"),
    ("s8", "房屋使用费（户租、水电、维修、车位、屋业等）"),
    ("s9", "经营/办公费用"),
    ("10s", "财务费用"),
    ("11s", "借款"),
    ("12s", "还款"),
    ("13s", "其他"),
    ("14s", "固定资产"),
)
OA_PAYMENT_METHOD_OPTIONS = (
    ("Bank_transfer", "银行转账"),
    ("Alipay", "支付宝"),
    ("WeChat_pay", "微信支付"),
    ("Cash_payment", "现金支付"),
)
OA_INVOICE_KIND_OPTIONS = (
    ("VAT_ordinary_invoice", "增值税专用发票"),
    ("Special_invoice", "普通发票/行政收据"),
    ("3", "无发票（收据及付款截图）"),
    ("tax", "完税凭证/税票"),
)

DEFAULT_OA_PROJECT_ID = "6486ca70cd6cae5d4e2b0b48"
DEFAULT_OA_PROJECT_NAME = "云南溯源科技"

_DEFAULTS: dict[str, dict[str, object]] = {
    ETC_OA_DRAFT_PREFILL_FAMILY: {
        "version": 1,
        "application_type": "s5",
        "payment_method": "Bank_transfer",
        "invoice_kind": "Special_invoice",
        "project_id": DEFAULT_OA_PROJECT_ID,
        "project_name": DEFAULT_OA_PROJECT_NAME,
        "payee": "刘树刚",
        "bank": "建设银行",
        "bank_account": "6217003860012460901",
        "reason_template": "{bill_month}月账单{submission_month}月{submission_day}日 支付 ETC批里提交",
    },
    INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY: {
        "version": 1,
        "application_type": "s5",
        "payment_method": "Bank_transfer",
        "invoice_kind": "Special_invoice",
        "project_id": DEFAULT_OA_PROJECT_ID,
        "project_name": DEFAULT_OA_PROJECT_NAME,
        "payee": "",
        "bank": "",
        "bank_account": "",
        "reason_template": "进项发票反提 OA，发票数={invoice_count}；发票号码={invoice_numbers}",
    },
}

_ALLOWED_TOKENS = {
    ETC_OA_DRAFT_PREFILL_FAMILY: {"bill_month", "submission_month", "submission_day"},
    INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY: {"invoice_count", "invoice_numbers"},
}


class OADraftPrefillValidationError(ValueError):
    pass


def default_oa_draft_prefill(family: str) -> dict[str, object]:
    return deepcopy(_DEFAULTS[_normalize_family(family)])


def normalize_oa_draft_prefill(
    family: str,
    value: Any,
    *,
    validate: bool = False,
) -> dict[str, object]:
    normalized_family = _normalize_family(family)
    raw = value if isinstance(value, dict) else {}
    result = default_oa_draft_prefill(normalized_family)
    version = raw.get("version", result["version"])
    if isinstance(version, bool):
        version = 1
    try:
        result["version"] = max(int(version), 1)
    except (TypeError, ValueError):
        result["version"] = 1

    option_fields = {
        "application_type": OA_APPLICATION_TYPE_OPTIONS,
        "payment_method": OA_PAYMENT_METHOD_OPTIONS,
        "invoice_kind": OA_INVOICE_KIND_OPTIONS,
    }
    for field_name, options in option_fields.items():
        candidate = str(raw.get(field_name, result[field_name]) or "").strip()
        allowed = {option[0] for option in options}
        if candidate in allowed:
            result[field_name] = candidate
        elif validate:
            raise OADraftPrefillValidationError(f"Unsupported OA draft prefill option: {field_name}={candidate}")

    for field_name, limit in (
        ("project_id", 128),
        ("project_name", 128),
        ("payee", 128),
        ("bank", 128),
        ("bank_account", 64),
        ("reason_template", 500),
    ):
        candidate = str(raw.get(field_name, result[field_name]) or "").strip()
        if len(candidate) > limit:
            if validate:
                raise OADraftPrefillValidationError(f"OA draft prefill field is too long: {field_name}")
            candidate = str(result[field_name])
        result[field_name] = candidate

    for required in ("project_id", "project_name", "reason_template"):
        if validate and not str(result[required]).strip():
            raise OADraftPrefillValidationError(f"OA draft prefill field is required: {required}")

    if normalized_family == INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY:
        result["payee"] = ""

    if validate:
        template = str(result["reason_template"])
        unknown_tokens = {
            token.split("}", 1)[0]
            for token in template.split("{")[1:]
            if "}" in token
        } - _ALLOWED_TOKENS[normalized_family]
        if unknown_tokens or "{" in _remove_allowed_tokens(template, _ALLOWED_TOKENS[normalized_family]):
            raise OADraftPrefillValidationError("OA draft reason template contains an unsupported token.")
    return result


def oa_draft_prefill_options() -> dict[str, list[dict[str, str]]]:
    return {
        "application_types": _public_options(OA_APPLICATION_TYPE_OPTIONS),
        "payment_methods": _public_options(OA_PAYMENT_METHOD_OPTIONS),
        "invoice_kinds": _public_options(OA_INVOICE_KIND_OPTIONS),
    }


def render_oa_draft_reason(
    family: str,
    template: object,
    *,
    submission_date: date | None = None,
    bill_date: date | None = None,
    invoice_numbers: list[str] | None = None,
) -> str:
    normalized_family = _normalize_family(family)
    text = str(template or default_oa_draft_prefill(normalized_family)["reason_template"])
    if normalized_family == ETC_OA_DRAFT_PREFILL_FAMILY:
        submitted = submission_date or date.today()
        billed = bill_date or submitted
        replacements = {
            "bill_month": str(billed.month),
            "submission_month": str(submitted.month),
            "submission_day": str(submitted.day),
        }
    else:
        numbers = [str(number).strip() for number in list(invoice_numbers or []) if str(number).strip()]
        replacements = {
            "invoice_count": str(len(numbers)),
            "invoice_numbers": ";".join(numbers),
        }
    for token, replacement in replacements.items():
        text = text.replace(f"{{{token}}}", replacement)
    return text.strip()


def _normalize_family(family: str) -> str:
    normalized = str(family or "").strip()
    if normalized not in _DEFAULTS:
        raise OADraftPrefillValidationError(f"Unsupported OA draft prefill family: {normalized}")
    return normalized


def _public_options(options: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
    return [{"value": value, "label": label} for value, label in options]


def _remove_allowed_tokens(template: str, tokens: set[str]) -> str:
    result = template
    for token in tokens:
        result = result.replace(f"{{{token}}}", "")
    return result
