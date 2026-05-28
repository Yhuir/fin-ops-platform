from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_attachment_audit import audit_oa_attachment_records


def oa_record(
    *,
    row_id: str,
    month: str = "2026-02",
    application_date: str | None = None,
    attachment_file_count: int = 0,
    attachment_evidences: list[dict[str, str]] | None = None,
    attachment_artifacts: list[dict[str, str]] | None = None,
    detail_fields: dict[str, object] | None = None,
) -> OAApplicationRecord:
    fields = {"申请日期": application_date or f"{month}-02"}
    if detail_fields:
        fields.update(detail_fields)
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="open",
        case_id=None,
        applicant="胡瑢",
        project_name="玉烟维护项目",
        apply_type="日常报销",
        amount="248.00",
        counterparty_name="",
        reason="测试 OA",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        detail_fields=fields,
        attachment_evidences=list(attachment_evidences or []),
        attachment_artifacts=list(attachment_artifacts or []),
        attachment_invoices=[
            dict(evidence)
            for evidence in list(attachment_evidences or [])
            if evidence.get("evidence_type") in {"tax_invoice", "machine_invoice", "non_tax_receipt"}
        ],
        attachment_file_count=attachment_file_count,
    )


class OAAttachmentAuditTests(unittest.TestCase):
    def test_payment_receipt_does_not_count_as_missing_formal_invoice(self) -> None:
        report = audit_oa_attachment_records(
            [
                oa_record(
                    row_id="oa-exp-2007",
                    attachment_file_count=2,
                    attachment_evidences=[
                        {
                            "evidence_type": "payment_receipt",
                            "document_kind": "wechat_etc_payment",
                            "amount": "23.00",
                        }
                    ],
                    attachment_artifacts=[
                        {"parse_status": "parsed", "document_kind": "wechat_etc_payment"},
                        {"parse_status": "no_evidence"},
                    ],
                    detail_fields={"附件凭证期望数": "2"},
                )
            ]
        )

        row = report["rows"][0]
        self.assertEqual(row["status"], "evidence_only_no_formal_invoice")
        self.assertEqual(row["formal_invoice_count"], 0)
        self.assertEqual(row["payment_receipt_count"], 1)
        self.assertEqual(report["summary"]["records_parser_failed"], 0)

    def test_ocr_empty_artifact_is_not_formal_invoice_parser_failure_by_itself(self) -> None:
        report = audit_oa_attachment_records(
            [
                oa_record(
                    row_id="oa-exp-payment-screenshot",
                    attachment_file_count=2,
                    attachment_evidences=[
                        {
                            "evidence_type": "payment_receipt",
                            "document_kind": "wechat_payment",
                            "amount": "60.00",
                        }
                    ],
                    attachment_artifacts=[
                        {"parse_status": "parsed", "document_kind": "wechat_payment"},
                        {"parse_status": "ocr_empty", "attachment_name": "支付截图.jpg"},
                    ],
                )
            ]
        )

        self.assertEqual(report["rows"][0]["status"], "evidence_only_no_formal_invoice")
        self.assertEqual(report["rows"][0]["parser_failed_count"], 0)
        self.assertEqual(report["summary"]["records_parser_failed"], 0)

    def test_source_missing_attachment_is_not_parser_failed(self) -> None:
        report = audit_oa_attachment_records(
            [
                oa_record(
                    row_id="oa-exp-1994",
                    attachment_file_count=0,
                    detail_fields={"附件凭证期望数": "44"},
                )
            ]
        )

        row = report["rows"][0]
        self.assertEqual(row["status"], "source_attachment_missing")
        self.assertEqual(report["summary"]["records_source_attachment_missing"], 1)
        self.assertEqual(report["summary"]["records_parser_failed"], 0)

    def test_before_2026_records_are_out_of_scope(self) -> None:
        report = audit_oa_attachment_records(
            [
                oa_record(
                    row_id="oa-exp-legacy",
                    month="2025-12",
                    application_date="2025-12-31",
                    attachment_file_count=1,
                )
            ]
        )

        self.assertEqual(report["rows"][0]["status"], "out_of_scope_before_2026")
        self.assertEqual(report["summary"]["records_in_scope"], 0)


if __name__ == "__main__":
    unittest.main()
