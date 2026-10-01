"""销项列表税率口径；只规范来源文本，不从金额推算税率。"""
import re
from decimal import Decimal


def normalize_output_tax_rate(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return "未提供"
    if text == "mixed":
        return "多税率"
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%?", text):
        return text
    number = Decimal(text.removesuffix("%"))
    if not text.endswith("%") and number <= 1:
        number *= 100
    formatted = format(number, "f")
    return (formatted.rstrip("0").rstrip(".") if "." in formatted else formatted) + "%"
