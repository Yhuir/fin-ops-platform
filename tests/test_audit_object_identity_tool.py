from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.tools.audit_object_identity import audit_object_identity


def _attachment_cache_row(cache_key: str, *, digital_invoice_no: str) -> dict[str, object]:
    invoice = {
        "digital_invoice_no": digital_invoice_no,
        "seller_name": "供应商",
        "buyer_name": "云南溯源科技有限公司",
        "total_with_tax": "10.00",
        "source_attachment_key": cache_key,
    }
    return {
        "source_attachment_key": cache_key,
        "parser_version": "test",
        "cache_schema_version": "1",
        "parsed_at": "2026-03-01 00:00:00",
        "invoices": [invoice],
        "evidences": [{**invoice, "evidence_type": "tax_invoice"}],
        "normalized_payload": {},
    }


def _weak_attachment_cache_row(cache_key: str, *, passenger_name: str) -> dict[str, object]:
    invoice = {
        "seller_tax_no": "91530111MA6KHWY107",
        "buyer_tax_no": "915300007194052520",
        "seller_name": "云南滇约出行科技有限公司",
        "buyer_name": "云南溯源科技有限公司",
        "issue_date": "2026-01-12",
        "total_with_tax": "45.00",
        "passenger_name": passenger_name,
        "source_attachment_key": cache_key,
    }
    return {
        "source_attachment_key": cache_key,
        "parser_version": "test",
        "cache_schema_version": "1",
        "parsed_at": "2026-03-01 00:00:00",
        "invoices": [invoice],
        "evidences": [{**invoice, "evidence_type": "tax_invoice"}],
        "normalized_payload": {},
    }


class _FakeConnection:
    def __init__(
        self,
        *,
        invoice_rows: list[dict[str, object]] | None = None,
        bank_rows: list[dict[str, object]] | None = None,
        etc_rows: list[dict[str, object]] | None = None,
        attachment_cache_rows: list[dict[str, object]] | None = None,
        attachment_cache_source_rows: list[dict[str, object]] | None = None,
        attachment_rows: list[dict[str, object]] | None = None,
        oa_source_alias_rows: list[dict[str, object]] | None = None,
        missing_tables: set[str] | None = None,
    ) -> None:
        self._invoice_rows = invoice_rows
        self._bank_rows = bank_rows
        self._etc_rows = etc_rows
        self._attachment_cache_rows = attachment_cache_rows
        self._attachment_cache_source_rows = attachment_cache_source_rows
        self._attachment_rows = attachment_rows
        self._oa_source_alias_rows = oa_source_alias_rows
        self._missing_tables = set(missing_tables or set())

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        table_name = str(params[0]) if params else ""
        if table_name in self._missing_tables:
            return {"table_name": None}
        if table_name in {
            "app.etc_invoices",
            "app.oa_attachment_invoice_cache",
            "app.oa_attachment_invoice_cache_sources",
            "app.oa_attachments",
            "app.oa_source_aliases",
        }:
            return {"table_name": table_name}
        return {"table_name": None}

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.split()).lower()
        if "from app.invoices" in normalized:
            return list(self._invoice_rows) if self._invoice_rows is not None else [
                {
                    "id": "inv-1",
                    "legacy_id": "inv-1",
                    "invoice_type": "input",
                    "invoice_no": "ETC-001",
                    "invoice_code": None,
                    "digital_invoice_no": "ETC-001",
                    "source_unique_key": "ETC-001",
                    "data_fingerprint": None,
                    "invoice_date": "2026-03-01",
                    "counterparty_name": "ETC",
                    "seller_name": "ETC",
                    "seller_tax_no": None,
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": None,
                    "amount": Decimal("70.00"),
                    "signed_amount": Decimal("70.00"),
                    "total_with_tax": Decimal("70.00"),
                    "status": "active",
                    "etc_invoice_id": "etc-1",
                }
            ]
        if "from app.bank_transactions" in normalized:
            return list(self._bank_rows or [])
        if "from app.etc_invoices" in normalized:
            return list(self._etc_rows) if self._etc_rows is not None else [
                {
                    "id": "etc-1",
                    "legacy_id": "etc-1",
                    "etc_invoice_id": "etc-1",
                    "invoice_no": "ETC-001",
                    "invoice_code": None,
                    "invoice_date": "2026-03-01",
                    "seller_name": "ETC",
                    "buyer_name": "云南溯源科技有限公司",
                    "amount": Decimal("70.00"),
                    "tax_amount": Decimal("0.00"),
                    "total_with_tax": Decimal("70.00"),
                    "status": "active",
                }
            ]
        if "from app.oa_attachment_invoice_cache_sources" in normalized:
            return list(self._attachment_cache_source_rows or [])
        if "from app.oa_source_aliases" in normalized:
            return list(self._oa_source_alias_rows or [])
        if "from app.oa_attachments" in normalized:
            return list(self._attachment_rows or [])
        if "from app.oa_attachment_invoice_cache" in normalized:
            return list(self._attachment_cache_rows) if self._attachment_cache_rows is not None else [
                {
                    "source_attachment_key": "att-1",
                    "parser_version": "test",
                    "cache_schema_version": "1",
                    "parsed_at": "2026-03-01 00:00:00",
                    "invoices": [
                        {
                            "digital_invoice_no": "26372000000990000001",
                            "seller_name": "云南顺丰速运有限公司",
                            "buyer_name": "云南溯源科技有限公司",
                            "total_with_tax": "12.00",
                        }
                    ],
                    "evidences": [
                        {
                            "evidence_type": "payment_receipt",
                            "transaction_no": "4200003046202603030281812965",
                            "amount": "23.00",
                        },
                        {
                            "evidence_type": "tax_invoice",
                            "digital_invoice_no": "26372000000990000002",
                            "total_with_tax": "13.00",
                        }
                    ],
                    "normalized_payload": {},
                }
            ]
        return []


class AuditObjectIdentityToolTests(unittest.TestCase):
    def test_audit_reports_etc_and_oa_attachment_invoice_identity_without_writes(self) -> None:
        report = audit_object_identity(
            connection=_FakeConnection(),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["invoice_count"], 1)
        self.assertEqual(report["summary"]["canonical_etc_invoice_count"], 1)
        self.assertEqual(report["summary"]["etc_invoice_count"], 1)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_entry_count"], 1)
        self.assertEqual(report["summary"]["oa_attachment_invoice_count"], 2)
        self.assertEqual(report["summary"]["etc_invoice_table_status"], "available")
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_table_status"], "available")
        self.assertEqual(report["missing_canonical_oa_attachment_invoices"], [])
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_blocking_duplicate_group_count"], 0)

    def test_audit_summary_counts_all_duplicates_even_when_examples_are_limited(self) -> None:
        invoice_rows = []
        for group_index in range(3):
            for row_index in range(2):
                invoice_rows.append(
                    {
                        "id": f"inv-{group_index}-{row_index}",
                        "legacy_id": f"inv-{group_index}-{row_index}",
                        "invoice_type": "input",
                        "invoice_no": f"INV-{group_index}",
                        "invoice_code": None,
                        "digital_invoice_no": f"DIGITAL-{group_index}",
                        "source_unique_key": f"DIGITAL-{group_index}",
                        "data_fingerprint": None,
                        "invoice_date": "2026-03-01",
                        "counterparty_name": "供应商",
                        "seller_name": "供应商",
                        "seller_tax_no": None,
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": None,
                        "amount": Decimal("70.00"),
                        "signed_amount": Decimal("70.00"),
                        "total_with_tax": Decimal("70.00"),
                        "status": "active",
                        "etc_invoice_id": None,
                    }
                )

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=invoice_rows,
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=[],
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=1,
        )

        self.assertEqual(report["summary"]["invoice_duplicate_group_count"], 3)
        self.assertEqual(report["summary"]["invoice_blocking_duplicate_group_count"], 3)
        self.assertEqual(report["summary"]["invoice_weak_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["blocking_issue_count"], 3)
        self.assertEqual(len(report["invoice_duplicate_groups"]), 1)
        self.assertEqual(len(report["invoice_blocking_duplicate_groups"]), 1)

    def test_audit_keeps_invoice_tax_amount_duplicates_as_warning_not_blocking(self) -> None:
        invoice_rows = []
        for index in range(2):
            invoice_rows.append(
                {
                    "id": f"weak-inv-{index}",
                    "legacy_id": f"weak-inv-{index}",
                    "invoice_type": "input",
                    "invoice_no": "",
                    "invoice_code": None,
                    "digital_invoice_no": None,
                    "source_unique_key": f"invoice:legacy:{index}",
                    "data_fingerprint": None,
                    "invoice_date": "2026-03-01",
                    "counterparty_name": "供应商",
                    "seller_name": "供应商",
                    "seller_tax_no": "SELLER-TAX",
                    "buyer_name": "云南溯源科技有限公司",
                    "buyer_tax_no": "BUYER-TAX",
                    "amount": Decimal("70.00"),
                    "signed_amount": Decimal("70.00"),
                    "total_with_tax": Decimal("70.00"),
                    "status": "active",
                    "etc_invoice_id": None,
                }
            )

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=invoice_rows,
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=[],
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["invoice_duplicate_group_count"], 1)
        self.assertEqual(report["summary"]["invoice_blocking_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["invoice_weak_duplicate_group_count"], 1)
        self.assertEqual(report["summary"]["invoice_key_mismatch_count"], 2)
        self.assertEqual(report["summary"]["invoice_blocking_key_mismatch_count"], 0)
        self.assertEqual(report["summary"]["invoice_weak_key_mismatch_count"], 2)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(len(report["invoice_weak_duplicate_groups"]), 1)
        self.assertEqual(len(report["invoice_blocking_duplicate_groups"]), 0)
        self.assertEqual(len(report["invoice_weak_key_mismatches"]), 2)

    def test_audit_keeps_raw_etc_duplicates_as_warning_not_blocking(self) -> None:
        etc_rows = []
        for index in range(2):
            etc_rows.append(
                {
                    "id": f"etc-raw-{index}",
                    "legacy_id": f"etc-raw-{index}",
                    "etc_invoice_id": f"etc-raw-{index}",
                    "invoice_no": "ETC-DUP-001",
                    "invoice_code": None,
                    "invoice_date": "2026-03-01",
                    "seller_name": "ETC",
                    "buyer_name": "云南溯源科技有限公司",
                    "amount": Decimal("70.00"),
                    "tax_amount": Decimal("0.00"),
                    "total_with_tax": Decimal("70.00"),
                    "status": "active",
                }
            )

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=etc_rows,
                attachment_cache_rows=[],
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["etc_duplicate_group_count"], 1)
        self.assertEqual(report["summary"]["etc_duplicate_warning_group_count"], 1)
        self.assertEqual(report["summary"]["etc_blocking_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(len(report["etc_duplicate_groups"]), 1)

    def test_audit_does_not_block_oa_attachment_invoice_cache_aliases_for_same_attachment(self) -> None:
        attachment_cache_rows = [
            _attachment_cache_row("cache-a", digital_invoice_no="DUP-001"),
            _attachment_cache_row("cache-b", digital_invoice_no="DUP-001"),
        ]
        attachment_cache_source_rows = [
            {
                "cache_source_attachment_key": "cache-a",
                "source_attachment_key": "actual-attachment-1",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-row-1",
                "oa_source_id": "oa-exp-1",
                "applicant": "张三",
                "application_date": "2026-03-01",
                "project_name": "项目A",
                "amount": Decimal("10.00"),
            },
            {
                "cache_source_attachment_key": "cache-b",
                "source_attachment_key": "actual-attachment-1",
                "source_kind": "evidence",
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-row-1",
                "oa_source_id": "oa-exp-1",
                "applicant": "张三",
                "application_date": "2026-03-01",
                "project_name": "项目A",
                "amount": Decimal("10.00"),
            },
        ]

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=attachment_cache_rows,
                attachment_cache_source_rows=attachment_cache_source_rows,
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["oa_attachment_invoice_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_blocking_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_alias_group_count"], 1)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(
            report["summary"]["oa_attachment_invoice_cache_alias_classification_counts"],
            {"same_actual_attachment": 1},
        )
        self.assertEqual(report["summary"]["oa_attachment_invoice_duplicate_classification_counts"], {})
        self.assertEqual(report["oa_attachment_invoice_cache_alias_groups"][0]["classification"], "same_actual_attachment")

    def test_audit_blocks_oa_attachment_invoice_duplicate_across_distinct_oa(self) -> None:
        attachment_cache_rows = [
            _attachment_cache_row("cache-a", digital_invoice_no="DUP-001"),
            _attachment_cache_row("cache-b", digital_invoice_no="DUP-001"),
        ]
        attachment_cache_source_rows = [
            {
                "cache_source_attachment_key": "cache-a",
                "source_attachment_key": "actual-attachment-1",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-row-1",
                "oa_source_id": "oa-exp-1",
                "applicant": "张三",
                "application_date": "2026-03-01",
                "project_name": "项目A",
                "amount": Decimal("10.00"),
            },
            {
                "cache_source_attachment_key": "cache-b",
                "source_attachment_key": "actual-attachment-2",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-2",
                "oa_row_id": "oa-row-2",
                "oa_source_id": "oa-exp-2",
                "applicant": "李四",
                "application_date": "2026-03-01",
                "project_name": "项目B",
                "amount": Decimal("10.00"),
            },
        ]

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=attachment_cache_rows,
                attachment_cache_source_rows=attachment_cache_source_rows,
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["oa_attachment_invoice_duplicate_group_count"], 1)
        self.assertEqual(report["summary"]["oa_attachment_invoice_blocking_duplicate_group_count"], 1)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_alias_group_count"], 0)
        self.assertEqual(report["summary"]["blocking_issue_count"], 1)
        self.assertEqual(
            report["summary"]["oa_attachment_invoice_duplicate_classification_counts"],
            {"cross_oa": 1},
        )
        duplicate_group = report["oa_attachment_invoice_blocking_duplicate_groups"][0]
        self.assertEqual(duplicate_group["classification"], "cross_oa")
        self.assertEqual(duplicate_group["distinct_oa_count"], 2)

    def test_active_oa_source_alias_downgrades_lifecycle_duplicate(self) -> None:
        attachment_cache_rows = [
            _attachment_cache_row("cache-a", digital_invoice_no="DUP-001"),
            _attachment_cache_row("cache-b", digital_invoice_no="DUP-001"),
        ]
        attachment_cache_source_rows = [
            {
                "cache_source_attachment_key": "cache-a",
                "source_attachment_key": "actual-attachment-1",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-exp-2005",
                "oa_source_id": "oa-exp-2005",
                "applicant": "周洁莹",
                "application_date": "2026-02-01",
                "project_name": "云南溯源科技",
                "amount": Decimal("800.00"),
            },
            {
                "cache_source_attachment_key": "cache-b",
                "source_attachment_key": "actual-attachment-2",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-2",
                "oa_row_id": "oa-exp-69898450db8c0a3633bd748c",
                "oa_source_id": "oa-exp-69898450db8c0a3633bd748c",
                "applicant": "周洁莹",
                "application_date": "2026-02-01",
                "project_name": "云南溯源科技",
                "amount": Decimal("800.00"),
            },
        ]

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=attachment_cache_rows,
                attachment_cache_source_rows=attachment_cache_source_rows,
                oa_source_alias_rows=[
                    {
                        "alias_row_id": "oa-exp-69898450db8c0a3633bd748c",
                        "canonical_row_id": "oa-exp-2005",
                    }
                ],
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["oa_attachment_invoice_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_blocking_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_alias_group_count"], 1)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(report["oa_attachment_invoice_cache_alias_groups"][0]["classification"], "same_oa_multiple_actual_attachments")

    def test_audit_treats_weak_oa_attachment_tax_amount_cross_oa_as_suspected_only(self) -> None:
        attachment_cache_rows = [
            _weak_attachment_cache_row("cache-a", passenger_name="吴云江"),
            _weak_attachment_cache_row("cache-b", passenger_name="马涛"),
        ]
        attachment_cache_source_rows = [
            {
                "cache_source_attachment_key": "cache-a",
                "source_attachment_key": "actual-attachment-1",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-1",
                "oa_row_id": "oa-row-1",
                "oa_source_id": "oa-exp-1",
                "applicant": "吴云江",
                "application_date": "2026-01-01",
                "project_name": "项目A",
                "amount": Decimal("353.00"),
            },
            {
                "cache_source_attachment_key": "cache-b",
                "source_attachment_key": "actual-attachment-2",
                "source_kind": "invoice",
                "oa_application_id": "oa-app-2",
                "oa_row_id": "oa-row-2",
                "oa_source_id": "oa-exp-2",
                "applicant": "马涛",
                "application_date": "2026-01-01",
                "project_name": "项目B",
                "amount": Decimal("470.40"),
            },
        ]

        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=attachment_cache_rows,
                attachment_cache_source_rows=attachment_cache_source_rows,
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["oa_attachment_invoice_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_blocking_duplicate_group_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_alias_group_count"], 0)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_suspected_duplicate_group_count"], 1)

    def test_audit_reports_missing_optional_tables_without_blocking(self) -> None:
        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                missing_tables={"app.etc_invoices", "app.oa_attachment_invoice_cache"},
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertEqual(report["summary"]["etc_invoice_table_status"], "missing")
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_table_status"], "missing")
        self.assertEqual(report["summary"]["etc_invoice_count"], 0)
        self.assertEqual(report["summary"]["oa_attachment_invoice_cache_entry_count"], 0)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)

    def test_audit_does_not_depend_on_retired_workbench_page_projection(self) -> None:
        report = audit_object_identity(
            connection=_FakeConnection(
                invoice_rows=[],
                bank_rows=[],
                etc_rows=[],
                attachment_cache_rows=[],
            ),
            policy=FinancialObjectIdentityPolicy(),
            example_limit=10,
        )

        self.assertNotIn("workbench_audit_status", report["summary"])
        self.assertNotIn("workbench_identity_audit", report)
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)


if __name__ == "__main__":
    unittest.main()
