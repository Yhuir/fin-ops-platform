"""Read financial fields from labelled invoice text and actual printed item rows.

This module does not recover missing numbers by arithmetic. OCR/PDF callers must
preserve row boundaries; a percentage elsewhere in the document is not a rate.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

MONEY = r"-?(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:[.，][0-9]{2})?"
TAX_TEXT = r"不征税|免税|\*+"
TAX_VALUE = rf"(?:{MONEY}|{TAX_TEXT})"
RATE = rf"(?:[0-9]+(?:\.[0-9]+)?\s*%|{TAX_TEXT})"
ITEM_ROW = re.compile(
    rf"^(?P<prefix>.*?)\s*(?P<amount>{MONEY})\s+"
    rf"(?P<rate>{RATE})\s+(?P<tax>{TAX_VALUE})\s*$"
)


def source_amount(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().replace("，", ".").replace(",", "")
    if not re.fullmatch(r"-?[0-9]+(?:\.[0-9]+)?", text):
        return None
    return format(Decimal(text).quantize(Decimal("0.01")), "f")


def _unique(values: list[str]) -> str | None:
    distinct = set(values)
    return next(iter(distinct)) if len(distinct) == 1 else None


def _normalized_lines(text: str) -> list[str]:
    lines = []
    for line in text.splitlines():
        line = line.strip().replace("：", ":").replace("￥", "¥").replace("％", "%").replace("−", "-")
        for label in ("价税合计", "合计", "不含税金额", "税额", "税率", "金额", "小写"):
            line = re.sub(r"\s*".join(label), label, line)
        line = re.sub(r"(?<=[0-9])\.[ \t]+(?=[0-9]{2}(?![0-9]))", ".", line)
        if line:
            lines.append(line)
    return lines


def invoice_source_line_items(text: str) -> list[dict[str, Any]]:
    """Each result is a printed amount/rate/tax row, including discount rows."""
    items: list[dict[str, Any]] = []
    in_items = False
    for line in _normalized_lines(text):
        compact = re.sub(r"\s+", "", line)
        if ("项目名称" in compact or "货物或应税劳务" in compact) and ("金额" in compact or "税率" in compact):
            in_items = True
            continue
        if re.match(r"(?:合计|价税合计|备注|开票人|收款人|复核)", compact):
            in_items = False
            continue
        match = ITEM_ROW.fullmatch(line)
        if match is None:
            continue
        prefix = match["prefix"].strip()
        # A real item has a table row or tax classification name. Never harvest
        # a percentage from payment terms, remarks or unrelated prose.
        if not in_items and not prefix.startswith("*"):
            continue
        if not prefix and not in_items:
            continue
        # OCR/PDF row text does not prove the boundaries between a multiword
        # item name, specification, unit, quantity and price. Preserve that text
        # instead of assigning positional tokens to the wrong business fields.
        name = prefix if prefix and not re.search(r"\s", prefix) else None
        tax_text = match["tax"]
        items.append({
            "taxable_item_name": name,
            "source_line_text": line,
            "amount": source_amount(match["amount"]),
            "tax_rate": re.sub(r"\s+", "", match["rate"]),
            "tax_amount": source_amount(tax_text),
            "tax_amount_text": tax_text if source_amount(tax_text) is None else None,
            "total_with_tax": None,
        })
    return items


def invoice_source_financials(text: str) -> dict[str, Any] | None:
    lines = _normalized_lines(text)
    joined = "\n".join(lines)
    compact = re.sub(r"\s+", "", joined)
    items = invoice_source_line_items(text)
    # The total label is mandatory: unattached currency values can be unit
    # prices, subtotals or unrelated bank/payment information.
    gross_values: list[str] = []
    gross_pattern = re.compile(rf"价税合计[^\n]*?(?:[¥Y]|[（(]小写[)）]\s*[¥Y]?)\s*(?P<value>{MONEY})(?![0-9.])")
    for match in gross_pattern.finditer(joined):
        gross_values.append(source_amount(match["value"]))
    for index, line in enumerate(lines):
        if "价税合计" not in line:
            continue
        # Digital and legacy forms may put the labelled small total on the next
        # line. Keep this window local, stopping before another labelled field.
        block = "".join(lines[index:index + 4])
        match = re.search(rf"[（(]?小写[)）]?[^0-9-]{{0,8}}(?P<value>{MONEY})(?![0-9.])", block)
        if match:
            gross_values.append(source_amount(match["value"]))
    # Small-total-only forms are accepted only when the invoice has its total
    # heading, even when PDF text extraction places that heading after the value.
    if "价税合计" in compact and not gross_values:
        match = re.search(rf"[（(]?小写[)）]?[^0-9-]{{0,8}}(?P<value>{MONEY})(?![0-9.])", compact)
        if match:
            gross_values.append(source_amount(match["value"]))
    if len(set(gross_values)) > 1:
        return None
    gross = _unique(gross_values)

    net: str | None = None
    tax: str | None = None
    tax_text: str | None = None
    summaries = list(re.finditer(
        rf"(?<!价税)合计\s*[¥Y]\s*(?P<net>{MONEY})(?:\s*[¥Y]\s*|\s+)(?P<tax>{TAX_VALUE})(?![0-9.])", joined
    ))
    if not summaries:
        # The compact variant only joins a labelled pair of currency cells;
        # unlike the former implementation it never orders cells by arithmetic.
        summaries = list(re.finditer(rf"(?<!价税)合计[¥Y](?P<net>{MONEY})[¥Y](?P<tax>{TAX_VALUE})(?![0-9.])", compact))
    if not summaries:
        table_header = next((index for index, line in enumerate(lines)
                            if "金额" in line and "税率" in line and "税额" in line
                            and line.index("金额") < line.index("税率") < line.index("税额")), None)
        if table_header is not None:
            for index in range(table_header + 1, len(lines)):
                if "价税合计" not in lines[index]:
                    continue
                pair = re.fullmatch(
                    rf"[¥Y$]\s*(?P<net>{MONEY})\s+(?:[¥Y$]\s*)?(?P<tax>{TAX_VALUE})(?:\s*合计)?", lines[index - 1])
                if pair:
                    summaries.append(pair)
    if summaries:
        pairs = {(source_amount(match["net"]), match["tax"]) for match in summaries}
        if len(pairs) != 1:
            return None
        net, tax_source = pairs.pop()
        tax = source_amount(tax_source)
        tax_text = tax_source if tax is None else None
    else:
        net_values = [source_amount(match[1]) for match in re.finditer(
            rf"(?<![税总])(?:不含税金额|金额)[ \t]*:?[ \t]*[¥Y]?[ \t]*({MONEY})(?![0-9.])", joined)]
        tax_values = [match[1] for match in re.finditer(
            rf"税额[ \t]*:?[ \t]*[¥Y]?[ \t]*({TAX_VALUE})(?![0-9.])", joined)]
        if len(set(net_values)) > 1 or len(set(tax_values)) > 1:
            return None
        net = _unique(net_values)
        tax_source = _unique(tax_values)
        tax = source_amount(tax_source)
        tax_text = tax_source if tax_source and tax is None else None

    if gross is None and ("铁路" in compact or "电子客票" in compact):
        for pattern in (rf"票价:?¥({MONEY})(?![0-9.])", rf"¥({MONEY})\s*票价"):
            match = re.search(pattern, re.sub(r"[^\S\n]+", "", joined))
            if match:
                gross = source_amount(match[1])
                break
    if gross is None:
        return None
    for label, chosen in ((r"(?<![税总])(?:不含税金额|金额)", net), ("税额", tax)):
        labelled = {source_amount(match[1]) for match in re.finditer(
            rf"{label}[ \t]*:[ \t]*[¥Y]?[ \t]*({MONEY})(?![0-9.])", joined)}
        if len(labelled) > 1 or (chosen is not None and labelled and labelled != {chosen}):
            return None
    if net is not None and tax is not None:
        try:
            if Decimal(net) + Decimal(tax) != Decimal(gross):
                return None
        except InvalidOperation:
            return None
    header_rates = re.findall(rf"^税率(?:/征收率)?\s*:\s*({RATE})\s*$", joined, re.M)
    rates = {re.sub(r"\s+", "", value) for value in header_rates}
    rates.update(item["tax_rate"] for item in items)
    rate = next(iter(rates)) if len(rates) == 1 else "mixed" if len(rates) > 1 else None
    return {
        "amount": net, "net_amount": net, "tax_amount": tax,
        "tax_amount_text": tax_text, "total_with_tax": gross,
        "tax_rate": rate, "source_line_items": items,
    }
