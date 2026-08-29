from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from typing import Any

import fitz


_PAGE = (595.28, 419.53)
_FONT = "china-s"
_LEFT = 56.69
_RIGHT = 14.17
_TOP = 48.19
_ROW_HEIGHT = 21.0
_COLUMN_WIDTHS = (8.0, 7.125, 9.0, 3.5, 7.5, 3.625, 8.5, 7.0, 18.25, 13.5)
_THIN = 0.55
_MEDIUM = 1.15


def _money(value: Any) -> Decimal:
    return Decimal(str(value or "0")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


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
        integer_parts.append(
            f"{four_digit_text(chunks[group_index])}{large_units[group_index]}"
        )
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


def _date_parts(value: Any) -> tuple[str, str, str]:
    if isinstance(value, datetime):
        value = value.date()
    if not isinstance(value, date):
        value = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    return str(value.year), str(value.month), str(value.day)


def _column_positions() -> tuple[float, ...]:
    available_width = _PAGE[0] - _LEFT - _RIGHT
    scale = available_width / sum(_COLUMN_WIDTHS)
    positions = [_LEFT]
    for width in _COLUMN_WIDTHS:
        positions.append(positions[-1] + width * scale)
    return tuple(positions)


_X = _column_positions()


class WorkbenchReceiptPdfRenderer:
    """Render the versioned 银行收据!A1:J12 layout on A5 landscape pages."""

    def render(self, snapshot: dict[str, Any]) -> bytes:
        document = fitz.open()
        for receipt in snapshot["receipts"]:
            lines = list(receipt["lines"])
            chunks = [lines[index : index + 5] for index in range(0, len(lines), 5)]
            for page_index, chunk in enumerate(chunks, start=1):
                self._draw_page(
                    document.new_page(width=_PAGE[0], height=_PAGE[1]),
                    receipt,
                    chunk,
                    page_index=page_index,
                    page_count=len(chunks),
                )
        buffer = BytesIO()
        document.save(buffer, garbage=4, deflate=True)
        document.close()
        return buffer.getvalue()

    @staticmethod
    def _cell_rect(
        row_index: int, start_column: int, end_column: int
    ) -> tuple[float, float, float, float]:
        top = _TOP + _ROW_HEIGHT * row_index
        return (_X[start_column], top, _X[end_column], top + _ROW_HEIGHT)

    @staticmethod
    def _text(
        page: fitz.Page,
        rect: tuple[float, float, float, float],
        text: str,
        *,
        size: float = 11,
        align: int = 0,
        inset: float = 2.5,
        font: str = _FONT,
    ) -> None:
        box = fitz.Rect(rect)
        box.x0 += inset
        box.x1 -= inset
        box.y0 += max(0.5, (_ROW_HEIGHT - size * 1.25) / 2)
        page.insert_textbox(
            box,
            str(text),
            fontname=font,
            fontsize=size,
            align=align,
            color=(0, 0, 0),
            lineheight=1.0,
        )

    @classmethod
    def _draw_table_grid(cls, page: fitz.Page) -> None:
        cell_spans = {
            3: ((0, 1), (1, 8), (8, 10)),
            4: ((0, 8), (8, 9), (9, 10)),
            5: ((0, 8), (8, 9), (9, 10)),
            6: ((0, 8), (8, 9), (9, 10)),
            7: ((0, 8), (8, 9), (9, 10)),
            8: ((0, 8), (8, 9), (9, 10)),
            9: ((0, 8), (8, 9), (9, 10)),
            10: ((0, 1), (1, 2), (2, 8), (8, 9), (9, 10)),
        }
        for row_index, spans in cell_spans.items():
            for start_column, end_column in spans:
                page.draw_rect(
                    fitz.Rect(cls._cell_rect(row_index, start_column, end_column)),
                    color=(0, 0, 0),
                    width=_THIN,
                )
        top = _TOP + _ROW_HEIGHT * 3
        bottom = _TOP + _ROW_HEIGHT * 11
        page.draw_line((_X[0], top), (_X[10], top), color=(0, 0, 0), width=_MEDIUM)
        page.draw_line((_X[0], bottom), (_X[10], bottom), color=(0, 0, 0), width=_MEDIUM)
        page.draw_line((_X[0], top), (_X[0], bottom), color=(0, 0, 0), width=_MEDIUM)
        page.draw_line((_X[10], top), (_X[10], bottom), color=(0, 0, 0), width=_MEDIUM)

    def _draw_page(
        self,
        page: fitz.Page,
        receipt: dict[str, Any],
        lines: list[dict[str, Any]],
        *,
        page_index: int,
        page_count: int,
    ) -> None:
        self._text(
            page,
            self._cell_rect(0, 0, 10),
            "云南溯源科技有限公司",
            size=16,
            align=1,
            inset=0,
        )
        self._text(
            page,
            self._cell_rect(1, 0, 10),
            "收    据",
            size=16,
            align=1,
            inset=0,
        )
        year, month, day = _date_parts(receipt["date"])
        for column, text in ((2, year), (3, "年"), (4, month), (5, "月"), (6, day), (7, "日")):
            self._text(
                page,
                self._cell_rect(2, column, column + 1),
                text,
                align=1,
                font="helv" if text.isascii() else _FONT,
            )
        if page_count > 1:
            self._text(
                page,
                self._cell_rect(2, 8, 10),
                f"第 {page_index}/{page_count} 页",
                size=8,
                align=2,
            )

        self._draw_table_grid(page)
        self._text(page, self._cell_rect(3, 0, 1), "兹收到", align=1)
        self._text(page, self._cell_rect(3, 1, 8), receipt["payer"], align=1)
        self._text(page, self._cell_rect(3, 8, 10), "交来下列款项", align=1)
        self._text(page, self._cell_rect(4, 0, 8), "摘                  要", align=1)
        self._text(page, self._cell_rect(4, 8, 9), "金额", align=1)
        self._text(page, self._cell_rect(4, 9, 10), "备注", align=1)

        for index, line in enumerate(lines):
            row_index = 5 + index
            self._text(page, self._cell_rect(row_index, 0, 8), line["summary"], size=10)
            self._text(
                page,
                self._cell_rect(row_index, 8, 9),
                _money_text(line["amount"]),
                size=10,
                align=2,
                font="helv",
            )
            self._text(
                page,
                self._cell_rect(row_index, 9, 10),
                line.get("note") or "",
                size=9,
            )

        is_last_page = page_index == page_count
        self._text(
            page,
            self._cell_rect(10, 0, 1),
            "合计：" if is_last_page else "续页：",
            align=2,
        )
        if is_last_page:
            uppercase = _uppercase_rmb(receipt["amount"]).removeprefix("人民币 ")
            self._text(page, self._cell_rect(10, 1, 2), "人民币")
            self._text(page, self._cell_rect(10, 2, 8), uppercase, size=10)
            self._text(
                page,
                self._cell_rect(10, 8, 9),
                f"¥{_money_text(receipt['amount'])}",
                size=10,
                align=2,
                font="helv",
            )

        self._text(
            page,
            self._cell_rect(11, 0, 4),
            f"主管：{receipt.get('supervisor') or ''}",
        )
        self._text(
            page,
            self._cell_rect(11, 6, 10),
            f"经手人：{receipt.get('handler') or ''}",
        )
