from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import serialize_value

EVIDENCE_SCHEMA_VERSION = 1


def workbench_oa_target(
    *,
    case_id: str | None,
    oa_row_id: str | None,
    expense_item_id: str | None,
) -> dict[str, Any]:
    normalized_case_id = _text(case_id)
    fields = [
        {
            "label": "关联关系",
            "value": normalized_case_id or "尚未建立，将在本次操作中创建",
        },
        {"label": "OA 付款项", "value": _text(oa_row_id)},
        {"label": "OA 子付款项", "value": _text(expense_item_id)},
    ]
    return {
        "kind": "oa_expense_item_relation",
        "title": f"关联关系 {normalized_case_id}" if normalized_case_id else "OA 子付款项关联",
        "fields": [field for field in fields if field.get("value")],
    }


def supporting_document_artifact(
    document: dict[str, Any],
    *,
    availability: str = "available",
    artifact_key: str | None = None,
) -> dict[str, Any]:
    normalized_availability = availability if availability in {"available", "deleted", "not_saved"} else "not_saved"
    return {
        "artifact_key": _text(artifact_key) or _text(document.get("id")) or "supporting-document",
        "kind": "file",
        "title": _text(document.get("file_name") or document.get("original_filename")) or "补充凭证",
        "media_type": _text(document.get("content_type")),
        "size_bytes": _integer(document.get("size_bytes")),
        "preview_url": _text(document.get("content_url")) if normalized_availability == "available" else None,
        "availability": normalized_availability,
    }


def attempted_supporting_document_artifacts(files: list[Any]) -> list[dict[str, Any]]:
    return [
        supporting_document_artifact(
            {
                "file_name": getattr(file, "file_name", "") or "补充凭证",
                "size_bytes": len(bytes(getattr(file, "content", b"") or b"")),
            },
            availability="not_saved",
            artifact_key=f"attempt-{index}",
        )
        for index, file in enumerate(files, start=1)
    ]


def manual_invoice_record(
    normalized: dict[str, Any],
    *,
    record_key: str,
) -> dict[str, Any]:
    invoice_number = _text(
        normalized.get("digital_invoice_no")
        or normalized.get("invoice_number")
        or normalized.get("invoice_no")
    )
    fields = [
        {"label": "发票号码", "value": invoice_number},
        {"label": "发票代码", "value": _text(normalized.get("invoice_code"))},
        {"label": "销方名称", "value": _text(normalized.get("seller_name"))},
        {"label": "销方识别号", "value": _text(normalized.get("seller_tax_no"))},
        {"label": "购方名称", "value": _text(normalized.get("buyer_name"))},
        {"label": "购方识别号", "value": _text(normalized.get("buyer_tax_no"))},
        {
            "label": "开票日期",
            "value": _text(normalized.get("issue_date") or normalized.get("invoice_date")),
        },
        {"label": "不含税金额", "value": _text(normalized.get("amount") or normalized.get("net_amount"))},
        {"label": "税额", "value": _text(normalized.get("tax_amount"))},
        {"label": "价税合计", "value": _text(normalized.get("total_with_tax"))},
    ]
    return {
        "record_key": _text(record_key) or invoice_number or "manual-invoice",
        "kind": "invoice",
        "title": invoice_number or "手工录入发票",
        "fields": [field for field in fields if field.get("value")],
    }


def build_operation_evidence(
    *,
    target: dict[str, Any] | None = None,
    artifacts: list[dict[str, Any]] | None = None,
    records: list[dict[str, Any]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
) -> dict[str, Any]:
    return normalize_operation_evidence(
        {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "target": target,
            "artifacts": artifacts or [],
            "records": records or [],
            "changes": changes or [],
            "failure": (
                {"code": _text(failure_code), "message": _text(failure_message)}
                if failure_code or failure_message
                else None
            ),
        }
    )


def normalize_operation_evidence(value: Any) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    target = source.get("target") if isinstance(source.get("target"), dict) else None
    failure = source.get("failure") if isinstance(source.get("failure"), dict) else None
    return serialize_value(
        {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "target": _normalize_target(target),
            "artifacts": [
                normalized
                for item in list(source.get("artifacts") or [])
                if isinstance(item, dict)
                for normalized in [_normalize_artifact(item)]
                if normalized is not None
            ],
            "records": [
                normalized
                for item in list(source.get("records") or [])
                if isinstance(item, dict)
                for normalized in [_normalize_record(item)]
                if normalized is not None
            ],
            "changes": [
                normalized
                for item in list(source.get("changes") or [])
                if isinstance(item, dict)
                for normalized in [_normalize_change(item)]
                if normalized is not None
            ],
            "failure": (
                {
                    "code": _text(failure.get("code")),
                    "message": _text(failure.get("message")) or "操作失败。",
                }
                if failure
                else None
            ),
        }
    )


def _normalize_target(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not value:
        return None
    title = _text(value.get("title"))
    if not title:
        return None
    return {
        "kind": _text(value.get("kind")) or "business_target",
        "title": title,
        "fields": _normalize_fields(value.get("fields")),
    }


def _normalize_artifact(value: dict[str, Any]) -> dict[str, Any] | None:
    title = _text(value.get("title"))
    if not title:
        return None
    availability = _text(value.get("availability")) or "not_saved"
    if availability not in {"available", "deleted", "not_saved"}:
        availability = "not_saved"
    return {
        "artifact_key": _text(value.get("artifact_key")) or title,
        "kind": "file",
        "title": title,
        "media_type": _text(value.get("media_type")),
        "size_bytes": _integer(value.get("size_bytes")),
        "preview_url": _text(value.get("preview_url")) if availability == "available" else None,
        "availability": availability,
    }


def _normalize_record(value: dict[str, Any]) -> dict[str, Any] | None:
    title = _text(value.get("title"))
    if not title:
        return None
    return {
        "record_key": _text(value.get("record_key")) or title,
        "kind": _text(value.get("kind")) or "business_record",
        "title": title,
        "fields": _normalize_fields(value.get("fields")),
    }


def _normalize_change(value: dict[str, Any]) -> dict[str, Any] | None:
    label = _text(value.get("label"))
    before = _text(value.get("before"))
    after = _text(value.get("after"))
    if not label or (not before and not after):
        return None
    return {"label": label, "before": before, "after": after}


def _normalize_fields(value: Any) -> list[dict[str, str]]:
    return [
        {"label": label, "value": field_value}
        for item in list(value or [])
        if isinstance(item, dict)
        for label, field_value in [(_text(item.get("label")), _text(item.get("value")))]
        if label and field_value
    ]


def _text(value: Any) -> str | None:
    normalized = str(value or "").strip()
    return normalized or None


def _integer(value: Any) -> int | None:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return max(0, normalized)
