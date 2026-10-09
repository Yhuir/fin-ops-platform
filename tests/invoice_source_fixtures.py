"""Uploaded original fixtures for the source-only invoice entry contract."""

import base64
from decimal import Decimal

import fitz


def with_original(values):
    values = dict(values)
    sign = -1 if values.get("invoice_nature") == "red" else 1

    def money(field):
        return str(Decimal(values[field]) * sign)

    text = f"""电子发票（普通发票）
发票号码：{values["invoice_number"]}
发票代码：{values.get("invoice_code", "")}
开票日期：{values["invoice_date"].replace("-", "年", 1).replace("-", "月", 1)}日
名称：{values["buyer_name"]}
纳税人识别号：{values["buyer_tax_no"]}
名称：{values["seller_name"]}
纳税人识别号：{values["seller_tax_no"]}
合计 ¥{money("net_amount")} ¥{money("tax_amount")}
价税合计（小写）¥{money("total_with_tax")}
税率：{values["tax_rate"]}%
"""
    document = fitz.open()
    try:
        page = document.new_page(width=600, height=700)
        page.insert_text((40, 45), text, fontname="china-s", fontsize=12)
        content = document.tobytes()
    finally:
        document.close()
    values.update(source_file_name="original.pdf", source_file_content=base64.b64encode(content).decode())
    return values
