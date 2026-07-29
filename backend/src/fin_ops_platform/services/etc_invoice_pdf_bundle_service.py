from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Callable, Iterable

import fitz


@dataclass(frozen=True, slots=True)
class EtcInvoicePdfBundle:
    content: bytes
    filename: str
    invoice_count: int
    page_count: int


class EtcInvoicePdfBundleError(RuntimeError):
    def __init__(self, message: str, *, code: str) -> None:
        self.code = code
        super().__init__(message)


class EtcInvoicePdfBundleService:
    """Builds one deterministic, single-page-per-invoice PDF for an ETC business batch."""

    DEFAULT_MAX_INVOICE_COUNT = 500
    DEFAULT_MAX_TOTAL_BYTES = 512 * 1024 * 1024

    def __init__(
        self,
        *,
        read_invoice_pdf: Callable[[str], bytes],
        max_invoice_count: int = DEFAULT_MAX_INVOICE_COUNT,
        max_total_bytes: int = DEFAULT_MAX_TOTAL_BYTES,
    ) -> None:
        self._read_invoice_pdf = read_invoice_pdf
        self._max_invoice_count = max_invoice_count
        self._max_total_bytes = max_total_bytes

    def build(self, *, batch: object, invoices: Iterable[object]) -> EtcInvoicePdfBundle:
        ordered_invoices = sorted(
            list(invoices),
            key=lambda invoice: (
                str(getattr(invoice, "issue_date", "") or "9999-99-99"),
                str(getattr(invoice, "invoice_number", "") or ""),
                str(getattr(invoice, "id", "") or ""),
            ),
        )
        if not ordered_invoices:
            raise EtcInvoicePdfBundleError(
                "当前 ETC 业务批次没有可下载的发票。",
                code="invoice_pdf_bundle_empty",
            )
        if len(ordered_invoices) > self._max_invoice_count:
            raise EtcInvoicePdfBundleError(
                f"当前批次包含 {len(ordered_invoices)} 张发票，超过单次下载上限 {self._max_invoice_count} 张。",
                code="invoice_pdf_bundle_too_large",
            )

        output = fitz.open()
        total_source_bytes = 0
        try:
            for invoice in ordered_invoices:
                invoice_id = str(getattr(invoice, "id", "") or "").strip()
                invoice_number = str(getattr(invoice, "invoice_number", "") or invoice_id or "未知发票").strip()
                try:
                    content = bytes(self._read_invoice_pdf(invoice_id))
                except Exception as exc:
                    raise EtcInvoicePdfBundleError(
                        f"ETC 发票 {invoice_number} 的 PDF 暂时无法读取，请稍后重试或联系管理员检查文件存储。",
                        code="invoice_pdf_unavailable",
                    ) from exc
                if not content:
                    raise EtcInvoicePdfBundleError(
                        f"ETC 发票 {invoice_number} 缺少 PDF 文件。",
                        code="invoice_pdf_unavailable",
                    )

                total_source_bytes += len(content)
                if total_source_bytes > self._max_total_bytes:
                    raise EtcInvoicePdfBundleError(
                        "当前批次 PDF 总大小超过单次下载上限，请拆分批次后重试。",
                        code="invoice_pdf_bundle_too_large",
                    )

                expected_hash = str(getattr(invoice, "pdf_file_hash", "") or "").strip().lower()
                if expected_hash and hashlib.sha256(content).hexdigest() != expected_hash:
                    raise EtcInvoicePdfBundleError(
                        f"ETC 发票 {invoice_number} 的 PDF 完整性校验失败，请重新导入该发票。",
                        code="invoice_pdf_unavailable",
                    )

                source = None
                try:
                    source = fitz.open(stream=content, filetype="pdf")
                    if source.needs_pass:
                        raise EtcInvoicePdfBundleError(
                            f"ETC 发票 {invoice_number} 的 PDF 已加密，无法合并。",
                            code="invoice_pdf_invalid",
                        )
                    if source.page_count != 1:
                        raise EtcInvoicePdfBundleError(
                            f"ETC 发票 {invoice_number} 的 PDF 必须恰好为 1 页，当前为 {source.page_count} 页。",
                            code="invoice_pdf_page_count_invalid",
                        )
                    output.insert_pdf(source, from_page=0, to_page=0)
                except EtcInvoicePdfBundleError:
                    raise
                except Exception as exc:
                    raise EtcInvoicePdfBundleError(
                        f"ETC 发票 {invoice_number} 的 PDF 已损坏或格式无效，请重新导入该发票。",
                        code="invoice_pdf_invalid",
                    ) from exc
                finally:
                    if source is not None:
                        source.close()

            if output.page_count != len(ordered_invoices):
                raise EtcInvoicePdfBundleError(
                    "ETC 发票 PDF 合并页数校验失败，请稍后重试。",
                    code="invoice_pdf_bundle_invariant_failed",
                )
            output.set_metadata(
                {
                    "title": self._bundle_stem(batch, len(ordered_invoices)),
                    "subject": "ETC 发票合并下载",
                    "creator": "fin-ops-platform",
                    "producer": "fin-ops-platform",
                }
            )
            merged = output.tobytes(garbage=4, deflate=True)
            if len(merged) > self._max_total_bytes:
                raise EtcInvoicePdfBundleError(
                    "合并后的 PDF 超过单次下载上限，请拆分批次后重试。",
                    code="invoice_pdf_bundle_too_large",
                )
            return EtcInvoicePdfBundle(
                content=merged,
                filename=f"{self._bundle_stem(batch, len(ordered_invoices))}.pdf",
                invoice_count=len(ordered_invoices),
                page_count=output.page_count,
            )
        finally:
            output.close()

    @classmethod
    def _bundle_stem(cls, batch: object, invoice_count: int) -> str:
        title = str(getattr(batch, "title", "") or getattr(batch, "business_batch_id", "") or "ETC批次").strip()
        safe_title = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", title).strip(" ._")[:80] or "ETC批次"
        return f"ETC发票_{safe_title}_{invoice_count}张"
