from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from openpyxl import Workbook


@dataclass(frozen=True)
class MockImportFile:
    name: str
    content: bytes

    @property
    def suffix(self) -> str:
        return self.name.rsplit(".", 1)[-1].lower() if "." in self.name else ""

    @property
    def content_type(self) -> str:
        if self.suffix == "xlsx":
            return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        if self.suffix == "xls":
            return "application/vnd.ms-excel"
        return "application/octet-stream"


def xlsx_bytes(rows: list[list[Any]], *, sheet_name: str | None = None) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    if sheet_name:
        sheet.title = sheet_name
    for row in rows:
        sheet.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def invoice_export_file(name: str = "全量发票查询导出结果-2026年1月.xlsx") -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                [
                    "序号",
                    "发票代码",
                    "发票号码",
                    "数电发票号码",
                    "销方识别号",
                    "销方名称",
                    "购方识别号",
                    "购买方名称",
                    "开票日期",
                    "税收分类编码",
                    "特定业务类型",
                    "货物或应税劳务名称",
                    "规格型号",
                    "单位",
                    "数量",
                    "单价",
                    "金额",
                    "税率",
                    "税额",
                    "价税合计",
                    "发票来源",
                    "发票票种",
                    "发票状态",
                    "是否正数发票",
                    "发票风险等级",
                    "开票人",
                    "备注",
                ],
                [
                    "1",
                    "255020000001",
                    "45098656",
                    "25502000000145098656",
                    "91500226MA60KH3C0Q",
                    "重庆高新技术产业开发区国家税务局",
                    "915300007194052520",
                    "云南溯源科技有限公司",
                    "2026-01-02 10:30:00",
                    "1090510990000000000",
                    "",
                    "*服务*测试服务",
                    "",
                    "项",
                    "1",
                    "6000.00",
                    "6000.00",
                    "3%",
                    "180.00",
                    "6180.00",
                    "电子发票服务平台",
                    "数电发票（普通发票）",
                    "正常",
                    "是",
                    "正常",
                    "测试员",
                    "",
                ],
            ]
        ),
    )


def icbc_history_file(name: str = "historydetail14080.xlsx") -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                [
                    "[HISTORYDETAIL]",
                    "凭证号",
                    "交易时间",
                    "对方单位",
                    "对方账号",
                    "转入金额",
                    "转出金额",
                    "余额",
                    "摘要",
                    "附言",
                ],
                [
                    "",
                    "ICBC-001",
                    "2026-01-03 09:12:00",
                    "重庆高新技术产业开发区国家税务局",
                    "500000000000001",
                    "",
                    "6180.00",
                    "12000.00",
                    "服务费",
                    "ICBC-001",
                ],
            ]
        ),
    )


def pingan_transaction_file(name: str = "2026-01-01至2026-01-31交易明细.xlsx") -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                [
                    "交易时间",
                    "账号",
                    "收入",
                    "支出",
                    "账户余额",
                    "对方户名",
                    "对方账号",
                    "对方账号开户行",
                    "摘要",
                    "交易流水号",
                    "核心唯一流水号",
                    "交易用途",
                    "币种",
                ],
                [
                    "2026-01-03 09:12:00",
                    "1100000000000093",
                    "",
                    "6180.00",
                    "12000.00",
                    "重庆高新技术产业开发区国家税务局",
                    "500000000000001",
                    "重庆银行",
                    "服务费",
                    "PINGAN-001",
                    "PINGAN-CORE-001",
                    "服务费",
                    "CNY",
                ],
            ]
        ),
    )


def ceb_transaction_file(name: str = "光大银行EXCEL账户明细_39610188000598826_20260101-20260423.xlsx") -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                ["中国光大银行对公账户对账单"],
                ["查询日期：2026-04-24 11:19:56"],
                ["交易日期：20260101-20260423", "", "借贷方向：全部"],
                ["账号：39610188000598826", "", "账户名称：云南溯源科技有限公司"],
                ["交易日期", "交易时间", "借方发生额（元）", "贷方发生额（元）", "账户余额（元）", "对方账号", "对方名称", "摘要"],
                ["2026-04-23", "11:18:17", "23053.31", "", "3518.86", "2502046609100018276", "云南辰飞机电工程有限公司", "货款"],
            ]
        ),
    )


def ccb_transaction_file(
    name: str = "A058171TB_ND94389000000501277800011_CN000_20260424111011_20192063_resp.xlsx",
) -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                [
                    "账号",
                    "账户名称",
                    "交易时间",
                    "记账日期",
                    "借方发生额（支取）",
                    "贷方发生额（收入）",
                    "余额",
                    "对方账号",
                    "对方户名",
                    "对方开户机构",
                    "摘要",
                    "账户明细编号-交易流水号",
                    "币种",
                ],
                [
                    "6217000000008826",
                    "云南溯源科技有限公司",
                    "2026-01-04 10:00:00",
                    "2026-01-04",
                    "100.00",
                    "",
                    "9900.00",
                    "330000000000001",
                    "杭州测试供应商",
                    "建设银行杭州支行",
                    "货款",
                    "CCB-001",
                    "CNY",
                ],
            ]
        ),
    )


def cmbc_transaction_file(name: str = "活期账户交易明细查询20260424114738585.xlsx") -> MockImportFile:
    return MockImportFile(
        name=name,
        content=xlsx_bytes(
            [
                ["账号：6226000000001122", "", "账户名称：云南溯源科技有限公司", "币种：CNY"],
                ["交易时间", "交易流水号", "借方发生额", "贷方发生额", "账户余额", "对方账号", "对方账号名称", "对方开户行", "客户附言"],
                ["2026-01-05 11:00:00", "CMBC-001", "200.00", "", "9800.00", "440000000000001", "广州测试供应商", "民生银行广州支行", "货款"],
            ]
        ),
    )


def unsupported_text_file(name: str = "README.md") -> MockImportFile:
    return MockImportFile(name=name, content=b"# unsupported fixture\n")


def certified_invoice_file(
    name: str,
    *,
    month: str,
    tax_amounts: list[str],
    invalid_count: int = 0,
) -> MockImportFile:
    compact_month = month.replace("-", "")
    rows: list[list[Any]] = [
        ["用途确认信息"],
        ["", "915300007194052520", "", "", "", compact_month, "", "", "云南溯源科技有限公司"],
        [
            "序号",
            "勾选状态",
            "数电发票号码",
            "发票代码",
            "发票号码",
            "开票日期",
            "销售方纳税人识别号",
            "销售方纳税人名称",
            "金额",
            "税额",
            "有效抵扣税额",
            "发票状态",
            "勾选时间",
            "发票来源",
            "发票票种",
            "发票风险等级",
        ],
    ]
    for index, tax_amount in enumerate(tax_amounts, start=1):
        invoice_no = "45098656" if index == 1 and month == "2026-01" else f"{month[-2:]}{index:06d}"
        digital_invoice_no = (
            "25502000000145098656" if index == 1 and month == "2026-01" else f"255020000001{invoice_no}"
        )
        seller_tax_no = "91500226MA60KH3C0Q" if index == 1 else f"91530000TEST{index:04d}"
        rows.append(
            [
                str(index),
                "已勾选",
                digital_invoice_no,
                "255020000001",
                invoice_no,
                f"{month}-02",
                seller_tax_no,
                "重庆高新技术产业开发区国家税务局" if index == 1 else f"测试供应商{index}",
                "6000.00",
                tax_amount,
                tax_amount,
                "正常",
                f"{month}-05 10:00:00",
                "电子发票服务平台",
                "数电发票（普通发票）",
                "正常",
            ]
        )
    for index in range(invalid_count):
        rows.append(
            [
                f"X{index + 1}",
                "未勾选",
                f"INVALID{index + 1}",
                "",
                f"INVALID{index + 1}",
                f"{month}-03",
                "INVALIDSELLER",
                "无效供应商",
                "100.00",
                "10.00",
                "10.00",
                "正常",
                "",
                "电子发票服务平台",
                "数电发票（普通发票）",
                "正常",
            ]
        )
    return MockImportFile(name=name, content=xlsx_bytes(rows, sheet_name="发票"))


INVOICE_JAN = invoice_export_file()
ICBC_JAN = icbc_history_file()
PINGAN_JAN = pingan_transaction_file()
CEB_JAN = ceb_transaction_file()
CCB_JAN = ccb_transaction_file()
CMBC_JAN = cmbc_transaction_file()
UNSUPPORTED = unsupported_text_file()
CERTIFIED_JAN = certified_invoice_file(
    "2026年1月 进项认证结果  用途确认信息.xlsx",
    month="2026-01",
    tax_amounts=["180.00", "70.75"],
    invalid_count=1,
)
CERTIFIED_FEB = certified_invoice_file(
    "2026年2月 进项认证结果  用途确认信息.xlsx",
    month="2026-02",
    tax_amounts=["39.00"],
)
