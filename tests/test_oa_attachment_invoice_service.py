from io import BytesIO
import unittest
from zipfile import ZipFile
from unittest.mock import patch

from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService


PNG_INVOICE_TEXT = """
云南增值税电子普通发票
发票代码 ：053002200111
发票号码 ：40512344
开票日期 ：2023年07月11日
名 称 ： 云南溯源科技有限公司
纳税人识别号：915300007194052520
合 计 ¥ 11.32 ¥ 0.68
价税合计 (大写） 壹拾贰元整 （小写） ¥ 12.00
名 称 ： 云南顺丰速运有限公司
纳税人识别号：91530100678728169X
*物流辅助服务*收派服务费 无 次 1.0 11.32 11.32 6% 0.68
"""

OCR_STYLE_PNG_INVOICE_TEXT = """
云南增值税电子普通发票
发票代码：053002200111
发票号码：40512344
开票日期：2023年07月11日
称：云南溯源科技有限公司
纳税人识别号：915300007194052520
￥11.32
￥ 0.68
价税合计(大写)
壹拾贰元整
(小写)
￥ 12.00
称：云南顺丰速运有限公司
纳税人识别号：91530100678728169X
6%
"""

OCR_GASOLINE_JPG_TEXT = """
发票代码：053002200111
电普通发票
发票号码：15312761
云南增值税电
成品油
开票日期：2025年04月24日
国家税务总局
校验码：53614780431357944396
云南省税务局
机器编号：661823756085
<>***01>0332*732-7<1-/-75<3
密码
称：云南溯源科技有限公司
3252>5995<8/3*27*6517/92/>*
购买方
纳税人识别号：530111199504054424
地址、电话：
542-+0701094>893836*677<18
税率
税额
开户行及账号：
金额
单价
数量
单位
23.01
规格型号
176.99
13%
货物或应税劳务、服务名称
25.75
6.87339806
95#汽油
*汽油*95号车用汽油（VIB）
￥23.01
￥176.99
（小写）?200，00
贰佰圆整
价税合计（大写）
称：云南中油严家山交通服务有限公司
销售方
纳税人识别号：91530000709708479E
91530000709708479E
地址、电话：昆曲高速公路五公里处0871-65896284
开户行及账号：工行高新支行2502024509022530714
发票专用章
销售方：（章）
开票人：邓丽梅
复核：刘蕾
收款人：赵亮
"""

DIGITAL_INVOICE_TEXT_WITH_DETACHED_NUMBER_AND_DATE = """
电⼦发票（增值税专用发票）
发票号码：
开票日期：
购 销
买 名称： 售 名称：
方 方
信 信 统一社会信用代码/纳税人识别号： 统一社会信用代码/纳税人识别号：
息 息
项目名称 规格型号 单 位 数 量 单 价 金 额 税率/征收率 税 额
下载次数：1
国
统一发票监
制 26322000000128086591
全 章
国家税务总局 2026年01月07日
江 苏省税务局
云南溯源科技有限公司 中科视拓（南京）科技有限公司
915300007194052520 91320191MA1XM5TX71
*信息系统服务*高性能计 项 1 66.0377358490566 66.04 6% 3.96
算服务费
合 计 ¥66.04 ¥3.96
价税合计（大写） 柒拾圆整 （小写） ¥ 70.00
购方开户银行:中国建设银行昆明金实支行; 银行账号:53001905038050548106;
销方开户银行:招商银行股份有限公司南京星火路支行; 银行账号:125916912310001;
备
注
开票人：卢朦
"""

HOTEL_PDF_TEXT = """
电子发票（普通发票）
发票号码：26532000000423491746
开票日期：2026年03月20日
购 名称：云南溯源科技有限公司 销 名称：弥勒市豪荟酒店（个体工商户）
买 售
方 方
信 统一社会信用代码/纳税人识别号：915300007194052520 信 统一社会信用代码/纳税人识别号：92532526MA6NTMA00H
息 息
项目名称 规格型号 单 位 数 量 单 价 金 额 税率/征收率 税 额
*住宿服务*住宿费 天 4 72.2772277227723 289.11 1% 2.89
合 计 ¥289.11 ¥2.89
价税合计（大写） 贰佰玖拾贰圆整 （小写）¥292.00
备
注
开票人：顾龙姣
顾龙姣
"""

RAILWAY_E_TICKET_TEXT = """
电子发票（铁路电子客票）
发票号码:26539148631000016633
开票日期:2026年02月04日
玉溪 D236 昆明
2026年01月28日 13:08开 05车19C号 二等座
￥38.00
票价:
5303261997****0896 吴云江
电子客票号:4863196086012890415592026
购买方名称:云南溯源科技有限公司
统一社会信用代码:915300007194052520
"""

OCR_DOCX_CNY_MARKER_TEXT = """
电子发【普通发票)
发票号码：26537000000124998164
开票日期：2026年02月06日
购买方信息
名称：云南溯源科技有限公司
销售方信息
名称：中国邮政速递物流股份有限公司昆明市分公司
统一社会信用代码/纳税人识别号：
统一社会信用代码/纳税人识别号：91530100557755195G
项目名称 金额 税率/征收率 税额
*快递服务*快递费 23.58 6% 1.42
Y23.58
Y1.42
价税合计（大写）
（小写）￥25.00
开票人：孔剑
"""

MACHINE_PRINTED_TOLL_INVOICE_TEXT = """
云南通用机打发票
国家税务总局
发票联
云南昆玉高速公路开发有限公司
发票代码153012525093
发票号码00582299
车类：客1
收费金额：15
发票专用章
报销凭证
"""

NON_TAX_PAYMENT_RECEIPT_TEXT = """
云南省非税收入一般缴款书（电子）
缴款码：53010026134004568343
执收单位编码：414001 票据代码：53030124 校验码：HJDsYN
执收单位名称： 昆明市公安局交通管理支队 票据号码：0038285699 填制日期：2026-02-10
莫永洪 昆明市财政局
币种：人民币 金额（大写）壹佰伍拾元整 （小写）150.00
项目编码 收入项目名称 单位 数量 收缴标准 金 额
103050101001 公安交警罚没 元 1.0000 150.00 150.00
"""


def _build_docx_with_media(*media_contents: bytes) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as document:
        document.writestr("word/document.xml", "<w:document xmlns:w=\"urn:test\"><w:t></w:t></w:document>")
        for index, content in enumerate(media_contents, start=1):
            document.writestr(f"word/media/image{index}.png", content)
    return output.getvalue()


class OAAttachmentInvoiceServiceTests(unittest.TestCase):
    def test_build_download_url_percent_encodes_absolute_unicode_url(self) -> None:
        service = OAAttachmentInvoiceService()

        url = service.build_download_url("https://oa.example.com/files/2026年/发票.pdf?name=发票.pdf")

        self.assertIn("2026%E5%B9%B4", url)
        self.assertIn("%E5%8F%91%E7%A5%A8.pdf", url)
        self.assertNotIn("年", url)
        self.assertNotIn("发票", url)

    def test_parse_files_skips_attachment_when_download_raises_unicode_error(self) -> None:
        service = OAAttachmentInvoiceService()
        file_entry = {
            "fileName": "发票.pdf",
            "filePath": "https://oa.example.com/files/2026年/发票.pdf",
            "suffix": "pdf",
        }

        with patch.object(
            service,
            "_download_content",
            side_effect=UnicodeEncodeError("ascii", "2026年", 4, 5, "ordinal not in range"),
        ):
            invoices = service.parse_files([file_entry])

        self.assertEqual(invoices, [])

    def test_parse_files_uses_image_ocr_for_png_invoice_attachment(self) -> None:
        service = OAAttachmentInvoiceService()
        file_entry = {
            "fileName": "invoice-image.png",
            "filePath": "/invoice-image.png",
            "suffix": "png",
        }

        with (
            patch.object(service, "_download_content", return_value=b"fake-png-bytes"),
            patch.object(service, "_extract_image_text", return_value=PNG_INVOICE_TEXT),
        ):
            invoices = service.parse_files([file_entry])

        self.assertEqual(len(invoices), 1)
        invoice = invoices[0]
        self.assertEqual(invoice["attachment_name"], "invoice-image.png")
        self.assertEqual(invoice["invoice_no"], "40512344")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["seller_name"], "云南顺丰速运有限公司")
        self.assertEqual(invoice["tax_rate"], "6%")
        self.assertEqual(invoice["total_with_tax"], "12.00")

    def test_parse_files_reads_embedded_invoice_images_from_docx_attachment(self) -> None:
        service = OAAttachmentInvoiceService()
        file_entry = {
            "fileName": "报销附件.docx",
            "filePath": "/报销附件.docx",
            "suffix": "docx",
        }

        with (
            patch.object(service, "_download_content", return_value=_build_docx_with_media(b"image-one")),
            patch.object(service, "_run_image_ocr", return_value=PNG_INVOICE_TEXT.splitlines()),
        ):
            invoices = service.parse_files([file_entry])

        self.assertEqual(len(invoices), 1)
        self.assertEqual(invoices[0]["attachment_name"], "报销附件.docx")
        self.assertEqual(invoices[0]["invoice_no"], "40512344")

    def test_parse_files_keeps_multiple_invoices_from_one_docx_attachment(self) -> None:
        service = OAAttachmentInvoiceService()
        file_entry = {
            "fileName": "多张发票.docx",
            "filePath": "/多张发票.docx",
            "suffix": "docx",
        }
        second_invoice_text = PNG_INVOICE_TEXT.replace("40512344", "40512345")

        with (
            patch.object(service, "_download_content", return_value=_build_docx_with_media(b"image-one", b"image-two")),
            patch.object(
                service,
                "_run_image_ocr",
                side_effect=[PNG_INVOICE_TEXT.splitlines(), second_invoice_text.splitlines()],
            ),
        ):
            invoices = service.parse_files([file_entry])

        self.assertEqual([invoice["invoice_no"] for invoice in invoices], ["40512344", "40512345"])
        self.assertTrue(all(invoice["attachment_name"] == "多张发票.docx" for invoice in invoices))

    def test_parse_files_skips_image_attachment_when_ocr_returns_empty_text(self) -> None:
        service = OAAttachmentInvoiceService()
        file_entry = {
            "fileName": "invoice-image.jpg",
            "filePath": "/invoice-image.jpg",
            "suffix": "jpg",
        }

        with (
            patch.object(service, "_download_content", return_value=b"fake-jpg-bytes"),
            patch.object(service, "_extract_image_text", return_value=""),
        ):
            invoices = service.parse_files([file_entry])

        self.assertEqual(invoices, [])

    def test_parse_invoice_text_accepts_ocr_style_amount_and_name_layout(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(OCR_STYLE_PNG_INVOICE_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_no"], "40512344")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["seller_name"], "云南顺丰速运有限公司")
        self.assertEqual(invoice["net_amount"], "11.32")
        self.assertEqual(invoice["tax_amount"], "0.68")
        self.assertEqual(invoice["total_with_tax"], "12.00")
        self.assertEqual(invoice["tax_rate"], "6%")

    def test_parse_invoice_text_accepts_gasoline_jpg_ocr_with_nonstandard_small_total(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(OCR_GASOLINE_JPG_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_code"], "053002200111")
        self.assertEqual(invoice["invoice_no"], "15312761")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["seller_name"], "云南中油严家山交通服务有限公司")
        self.assertEqual(invoice["issue_date"], "2025-04-24")
        self.assertEqual(invoice["net_amount"], "176.99")
        self.assertEqual(invoice["tax_amount"], "23.01")
        self.assertEqual(invoice["total_with_tax"], "200.00")
        self.assertEqual(invoice["tax_rate"], "13%")
        self.assertEqual(invoice["amount"], "176.99")

    def test_parse_invoice_text_accepts_digital_invoice_when_number_and_date_are_detached(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(DIGITAL_INVOICE_TEXT_WITH_DETACHED_NUMBER_AND_DATE)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_no"], "26322000000128086591")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["seller_name"], "中科视拓（南京）科技有限公司")
        self.assertEqual(invoice["buyer_tax_no"], "915300007194052520")
        self.assertEqual(invoice["seller_tax_no"], "91320191MA1XM5TX71")
        self.assertEqual(invoice["issue_date"], "2026-01-07")
        self.assertEqual(invoice["net_amount"], "66.04")
        self.assertEqual(invoice["tax_amount"], "3.96")
        self.assertEqual(invoice["total_with_tax"], "70.00")
        self.assertEqual(invoice["tax_rate"], "6%")

    def test_parse_invoice_text_keeps_net_amount_separate_from_total_with_tax(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(HOTEL_PDF_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_no"], "26532000000423491746")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["seller_name"], "弥勒市豪荟酒店")
        self.assertEqual(invoice["amount"], "289.11")
        self.assertEqual(invoice["net_amount"], "289.11")
        self.assertEqual(invoice["tax_amount"], "2.89")
        self.assertEqual(invoice["total_with_tax"], "292.00")
        self.assertEqual(invoice["tax_rate"], "1%")

    def test_parse_invoice_text_accepts_railway_e_ticket_invoice_amount_layout(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(RAILWAY_E_TICKET_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_no"], "26539148631000016633")
        self.assertEqual(invoice["issue_date"], "2026-02-04")
        self.assertEqual(invoice["buyer_name"], "云南溯源科技有限公司")
        self.assertEqual(invoice["buyer_tax_no"], "915300007194052520")
        self.assertEqual(invoice["net_amount"], "38.00")
        self.assertEqual(invoice["tax_amount"], "0.00")
        self.assertEqual(invoice["total_with_tax"], "38.00")
        self.assertEqual(invoice["invoice_kind"], "电子发票（铁路电子客票）")

    def test_parse_invoice_text_accepts_ocr_y_as_currency_marker(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(OCR_DOCX_CNY_MARKER_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_no"], "26537000000124998164")
        self.assertEqual(invoice["seller_name"], "中国邮政速递物流股份有限公司")
        self.assertEqual(invoice["net_amount"], "23.58")
        self.assertEqual(invoice["tax_amount"], "1.42")
        self.assertEqual(invoice["total_with_tax"], "25.00")

    def test_parse_invoice_text_accepts_machine_printed_toll_invoice_without_issue_date(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(MACHINE_PRINTED_TOLL_INVOICE_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_code"], "153012525093")
        self.assertEqual(invoice["invoice_no"], "00582299")
        self.assertEqual(invoice["seller_name"], "云南昆玉高速公路开发有限公司")
        self.assertEqual(invoice["issue_date"], "")
        self.assertEqual(invoice["net_amount"], "15.00")
        self.assertEqual(invoice["tax_amount"], "0.00")
        self.assertEqual(invoice["total_with_tax"], "15.00")
        self.assertEqual(invoice["invoice_kind"], "云南通用机打发票")

    def test_parse_invoice_text_accepts_non_tax_payment_receipt(self) -> None:
        service = OAAttachmentInvoiceService()

        invoice = service._parse_invoice_text(NON_TAX_PAYMENT_RECEIPT_TEXT)

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice["invoice_code"], "53030124")
        self.assertEqual(invoice["invoice_no"], "0038285699")
        self.assertEqual(invoice["seller_name"], "昆明市公安局交通管理支队")
        self.assertEqual(invoice["issue_date"], "2026-02-10")
        self.assertEqual(invoice["net_amount"], "150.00")
        self.assertEqual(invoice["tax_amount"], "0.00")
        self.assertEqual(invoice["total_with_tax"], "150.00")
        self.assertEqual(invoice["invoice_kind"], "云南省非税收入一般缴款书（电子）")


if __name__ == "__main__":
    unittest.main()
