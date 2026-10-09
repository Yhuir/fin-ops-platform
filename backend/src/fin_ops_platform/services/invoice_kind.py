"""原件票种的确定映射；不根据金额、税率或导入渠道推断。"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

SPECIAL_INVOICE_CODE = "vat_special"
INVOICE_KIND_NAMES = {
    "vat_special": "增值税专用发票",
    "vat_general": "普通发票",
    "toll": "通行费发票",
    "rail_ticket": "铁路电子客票",
    "motor_vehicle": "机动车销售统一发票",
    "machine_invoice": "通用机打发票",
    "non_tax_receipt": "非税收入一般缴款书",
}
_ALIASES = {
    "vat_special": (
        "进项专票",
        "增值税专用发票",
        "增值税电子专用发票",
        "电子专用发票",
        "电子发票(增值税专用发票)",
        "数电票(专用发票)",
        "数电发票(增值税专用发票)",
    ),
    "vat_general": (
        "普通发票",
        "增值税普通发票",
        "增值税电子普通发票",
        "电子普通发票",
        "电子发票(普通发票)",
        "电子发票(增值税普通发票)",
        "数电发票(普通发票)",
    ),
    "toll": ("通行费发票", "数电发票(通行费发票)"),
    "rail_ticket": ("铁路电子客票", "电子发票(铁路电子客票)", "数电发票(铁路电子客票)"),
    "motor_vehicle": ("机动车销售统一发票", "数电发票(机动车销售统一发票)"),
    "machine_invoice": ("通用机打发票",),
    "non_tax_receipt": ("非税收入一般缴款书",),
}


def normalize_kind_text(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")))


_CODES = {normalize_kind_text(label): code for code, labels in _ALIASES.items() for label in labels}


def invoice_kind_fields(value: Any, *, missing_status: str = "not_provided") -> dict[str, Any]:
    """保留原文；未映射与缺失不能作为已确认类型。"""
    raw = str(value).strip() if value is not None else ""
    text = normalize_kind_text(raw)
    code = _CODES.get(text)
    if code is None:
        for suffix, mapped in (
            ("增值税电子普通发票", "vat_general"),
            ("通用机打发票", "machine_invoice"),
            ("非税收入一般缴款书", "non_tax_receipt"),
        ):
            if re.fullmatch(r"[\u4e00-\u9fff]{2,8}" + suffix + r"(?:\(电子\))?", text):
                code = mapped
                break
    return {
        "invoice_kind": raw or None,
        "invoice_kind_code": code,
        "invoice_kind_status": "confirmed" if code else "unmapped" if raw else missing_status,
    }


def extract_invoice_kind(text: str) -> str | None:
    """只读取票面标题行；商品、代码、备注中的发票字样不作为标题。"""
    for line in text.splitlines():
        match = re.match(r"^(?:电[子⼦]发票|数电发票|数电票)\s*[（(][^）)\n]+[）)]", line.strip())
        if match:
            return match.group(0)
        if invoice_kind_fields(line)["invoice_kind_code"]:
            return line.strip()
    return None
