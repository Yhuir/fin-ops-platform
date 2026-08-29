from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any

import fitz


_PAGE = (595.28, 419.53)
_FONT = "china-s"


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _money_text(value: Any) -> str:
    return f"{_money(value):,.2f}"


def _uppercase_rmb(value: Any) -> str:
    amount = _money(value)
    if amount < 0:
        raise ValueError("receipt amount must not be negative")
    integer, fraction = f"{amount:.2f}".split(".")
    if len(integer) > 12:
        raise ValueError("receipt amount exceeds supported range")
    digits = "零壹贰叁肆伍陆柒捌玖"
    small_units = ("", "拾", "佰", "仟")
    large_units = ("", "万", "亿")

    def four_digit_text(chunk: str) -> str:
        result: list[str] = []
        pending_zero = False
        for index, character in enumerate(chunk.zfill(4)):
            digit = int(character)
            unit_index = 3 - index
            if digit == 0:
                pending_zero = bool(result)
                continue
            if pending_zero:
                result.append("零")
                pending_zero = False
            result.extend((digits[digit], small_units[unit_index]))
        return "".join(result)

    chunks: list[str] = []
    remaining = integer
    while remaining:
        chunks.append(remaining[-4:])
        remaining = remaining[:-4]
    integer_parts: list[str] = []
    zero_between = False
    for group_index in range(len(chunks) - 1, -1, -1):
        chunk_value = int(chunks[group_index])
        if chunk_value == 0:
            if integer_parts:
                zero_between = True
            continue
        if integer_parts and (zero_between or chunk_value < 1000):
            integer_parts.append("零")
        integer_parts.append(f"{four_digit_text(chunks[group_index])}{large_units[group_index]}")
        zero_between = False
    integer_text = "".join(integer_parts) or "零"
    jiao, fen = int(fraction[0]), int(fraction[1])
    fraction_text = ""
    if jiao:
        fraction_text += f"{digits[jiao]}角"
    if fen:
        if not jiao:
            fraction_text += "零"
        fraction_text += f"{digits[fen]}分"
    return f"人民币 {integer_text}元{fraction_text or '整'}"


def _date_text(value: Any) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%Y年%m月%d日")
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return parsed.strftime("%Y年%m月%d日")


class WorkbenchReceiptPdfRenderer:
    """Render the approved A5 landscape receipt layout as a printable PDF."""

    def render(self, snapshot: dict[str, Any]) -> bytes:
        document = fitz.open()
        for receipt in snapshot["receipts"]:
            lines = list(receipt["invoice_lines"])
            chunks = [lines[index : index + 5] for index in range(0, len(lines), 5)] or [[]]
            for copy_label in ("收款人留存", "付款人留存"):
                for page_index, chunk in enumerate(chunks, start=1):
                    self._draw_page(
                        document.new_page(width=_PAGE[0], height=_PAGE[1]),
                        receipt,
                        chunk,
                        copy_label=copy_label,
                        page_index=page_index,
                        page_count=len(chunks),
                    )
        buffer = BytesIO()
        document.save(buffer, garbage=4, deflate=True)
        document.close()
        return buffer.getvalue()

    @staticmethod
    def _text(
        page: fitz.Page,
        rect: tuple[float, float, float, float],
        text: str,
        *,
        size: float = 10,
        align: int = 0,
    ) -> None:
        page.insert_textbox(fitz.Rect(*rect), text, fontname=_FONT, fontsize=size, align=align, color=(0, 0, 0))

    def _draw_page(
        self,
        page: fitz.Page,
        receipt: dict[str, Any],
        invoice_lines: list[dict[str, Any]],
        *,
        copy_label: str,
        page_index: int,
        page_count: int,
    ) -> None:
        page.draw_rect(fitz.Rect(22, 14, 573, 403), color=(0.1, 0.1, 0.1), width=0.8)
        self._text(page, (24, 18, 571, 39), "云南溯源科技有限公司", size=11, align=1)
        self._text(page, (24, 34, 571, 75), "收  据", size=20, align=1)
        self._text(page, (40, 74, 555, 92), _date_text(receipt["date"]), size=10, align=1)
        self._text(page, (40, 94, 555, 116), f"兹收到 {receipt['payer']} 交来如下款项", size=11)
        if page_count > 1:
            self._text(page, (455, 70, 555, 89), f"第 {page_index}/{page_count} 页", size=8, align=2)

        left, top, right, row_height = 40, 121, 555, 32
        columns = (left, 330, 430, right)
        for x in columns:
            page.draw_line((x, top), (x, top + row_height * 7), color=(0.25, 0.25, 0.25), width=0.6)
        for index in range(8):
            y = top + row_height * index
            page.draw_line((left, y), (right, y), color=(0.25, 0.25, 0.25), width=0.6)
        self._text(page, (left + 4, top + 7, 330, top + 28), "摘要", size=10, align=1)
        self._text(page, (334, top + 7, 430, top + 28), "金额", size=10, align=1)
        self._text(page, (434, top + 7, right, top + 28), "备注", size=10, align=1)

        for index, line in enumerate(invoice_lines):
            y = top + row_height * (index + 1)
            summary = f"销项发票 {line['invoice_no']}"
            self._text(page, (left + 5, y + 6, 326, y + 29), summary, size=8.5)
            self._text(page, (334, y + 6, 426, y + 29), _money_text(line["amount"]), size=9, align=2)
            self._text(page, (434, y + 6, 551, y + 29), str(line.get("note") or ""), size=8)

        total_y = top + row_height * 6
        self._text(page, (left + 5, total_y + 7, 125, total_y + 29), "合计：", size=10, align=1)
        self._text(page, (125, total_y + 7, 330, total_y + 29), _uppercase_rmb(receipt["amount"]), size=8.5)
        self._text(page, (334, total_y + 7, 426, total_y + 29), _money_text(receipt["amount"]), size=10, align=2)
        footer_y = top + row_height * 7 + 12
        self._text(page, (40, footer_y, 240, footer_y + 22), f"主管：{receipt.get('supervisor') or ''}", size=9)
        self._text(page, (280, footer_y, 470, footer_y + 22), f"经手人：{receipt.get('handler') or ''}", size=9)
        self._text(page, (470, footer_y, 555, footer_y + 22), copy_label, size=8, align=2)
