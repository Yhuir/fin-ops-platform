from __future__ import annotations

import json
import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import (
    InputInvoiceUsageCanonicalQueryService,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.invoice_financial_values import resolve_invoice_financial_values
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.invoice_financial_sql import invoice_financial_sql
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
)

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class _UnexpectedPaymentRulesProvider:
    def __init__(self) -> None:
        self.evaluate_count = 0

    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, object]:
        del can_save
        return {}

    def rules_source_version(self) -> int:
        return 1

    def evaluate(self, _context: object) -> dict[str, str]:
        self.evaluate_count += 1
        raise AssertionError("row assembly must reuse snapshot payment rules")


class InvoiceUsageCollectionPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def test_financial_sql_and_python_agree_on_edge_cases(self):
        fields = invoice_financial_sql("invoice")
        cases = [
            ("1884674.86", "245007.73", "2129682.59", None),
            ("-1884674.86", "-245007.73", "-2129682.59", None),
            ("94.34", "5.66", "100", None), ("100", "13", "113", "0.13"),
            ("100", None, "113", "13%"), (None, "13", "113", "13%"),
            ("0.004", None, "0.005", "13%"),
            ("100", "13", None, "13%"), ("100", "13", "120", None),
            ("100", None, "106", "13%"), (None, "6", "106", "13%"),
            ("0", "0", "0", None), ("100", "0", "100", None),
            ("100", None, None, None), ("100", None, "90", None),
            ("100", "-13", "87", None), ("2000", "190", "2190", None),
            ("100", "0", "100", "免税"), ("100", "0", "100", "0"),
            ("100", "13", "113", "mixed"),
        ]
        sql = "select " + ", ".join(f"{expr} as {field}" for field, expr in fields.items()) + """
            from (select %s::numeric as amount, %s::numeric as tax_amount,
                  %s::numeric as total_with_tax, %s::text as tax_rate, '{}'::jsonb as raw_payload) invoice
        """
        for a, t, g, r in cases:
            with self.subTest(values=(a, t, g, r)):
                row = self.connection.fetch_one(sql, (a, t, g, r))
                expected = resolve_invoice_financial_values(amount=a, tax_amount=t, total_with_tax=g, tax_rate=r)
                for field in ("amount", "tax_amount", "total_with_tax"):
                    self.assertEqual(row[field], getattr(expected, field))
                self.assertEqual(row["tax_rate"], expected.rate_label)

    def test_historical_missing_rate_filter_and_export_are_unknown_without_writes(self):
        self.connection.execute("""insert into app.invoices(legacy_mongo_id, invoice_type, invoice_no,
            invoice_date, invoice_month, buyer_name, amount, signed_amount, tax_amount, total_with_tax, status)
            values ('derived-output', 'output', 'derived-001', '2026-10-03', '2026-10-01', '公司',
                    1884674.86, 1884674.86, 245007.73, 2129682.59, 'pending')""")
        service = OutputInvoiceCollectionCanonicalQueryService(
            repository=PostgresOutputInvoiceCollectionQueryRepository(self.connection),
            row_assembler=OutputInvoiceCollectionQueryService(import_service=ImportNormalizationService()),
        )
        payload = service.list_rows(filters=[{"field": "tax_rate", "operator": "in", "values": ["无法确定"]}])
        self.assertEqual(payload["pagination"]["total"], 1)
        [row] = payload["rows"]
        self.assertEqual(row["invoice"]["taxRate"], "无法确定")
        self.assertEqual(row["invoice"]["inferredFields"], [])
        self.assertEqual(payload["summary"]["totalWithTax"], "2129682.59")
        self.assertEqual(service.list_rows(filters=[{"field": "tax_rate", "operator": "in", "values": ["13%"]}])["pagination"]["total"], 0)
        self.assertEqual(service.list_rows(filters=[{"field": "tax_rate", "operator": "in", "values": ["13%（推算）"]}])["pagination"]["total"], 0)
        self.assertIsNone(self.connection.fetch_one("select tax_rate from app.invoices where legacy_mongo_id='derived-output'")["tax_rate"])
        exported = OutputInvoiceCollectionQueryService._export_row(1, row)
        self.assertEqual(exported["税率"], "无法确定")
        self.assertEqual(exported["价税合计"], Decimal("2129682.59"))

    def test_source_line_rate_evidence_matches_python_and_sql(self):
        known = {"amount": "100", "tax_amount": "13", "total_with_tax": "113", "tax_rate": "0.13"}
        missing = {**known, "tax_rate": None}
        other = {"amount": "100", "tax_amount": "6", "total_with_tax": "106", "tax_rate": "6%"}
        cases = [
            ("200", "26", "226", None, [known, {**known, "tax_rate": "13.00%"}], [], "13%"),
            ("200", "26", "226", "mixed", [known, missing], [], "无法确定"),
            ("200", "19", "219", "mixed", [known, other], [], "多税率"),
            ("300", "32", "332", None, [known, other, missing], [], "多税率"),
            ("200", "26", "226", None, [known], [], "无法确定"),
            ("100", "13", "113", "6%", [known], [], "无法确定"),
            ("100", "13", "113", "13%", [missing], [], "13%"),
            ("100", "13", "113", "13%", [], ["amount", "tax_rate"], "无法确定"),
            ("100", "13", "113", "13%", [known], ["tax_rate"], "13%"),
            ("100", "13", "113", None, [{**known, "total_with_tax": "114"}], [], "无法确定"),
            ("1000", "130", "1130", None, [{**known, "amount": "1,000", "tax_amount": "130", "total_with_tax": "1,130"}], [], "13%"),
            ("100", "0", "100", None, [{**known, "tax_rate": "免税", "tax_amount": "0", "total_with_tax": "100"}], [], "免税"),
        ]
        cases.extend([
            ("100", None, None, None, [{"amount": "100", "total_with_tax": "90", "tax_rate": "13%"}], [], "无法确定"),
            ("0.004", "0.004", None, None, [{"amount": "0.001", "tax_amount": "0.001", "total_with_tax": "0.002", "tax_rate": "13%"}], [], "无法确定"),
        ])
        fields = invoice_financial_sql("invoice")
        sql = "select " + ", ".join(f"{expr} as {field}" for field, expr in fields.items()) + """
            from (select %s::numeric as amount, %s::numeric as tax_amount,
                %s::numeric as total_with_tax, %s::text as tax_rate, %s::jsonb as raw_payload) invoice
        """
        for a, t, g, rate, lines, inferred, expected_rate in cases:
            with self.subTest(header=rate, lines=lines, inferred=inferred):
                payload = {"normalized_payload": {"source_line_items": lines, "inferred_fields": inferred}}
                row = self.connection.fetch_one(sql, (a, t, g, rate, json.dumps(payload)))
                resolved = resolve_invoice_financial_values(amount=a, tax_amount=t, total_with_tax=g,
                    tax_rate=rate, inferred_fields=inferred, source_line_items=lines)
                self.assertEqual(row["tax_rate"], expected_rate)
                self.assertEqual(resolved.rate_label, expected_rate)
                self.assertNotIn("tax_rate", resolved.inferred_fields)
                for field in ("amount", "tax_amount", "total_with_tax"):
                    self.assertEqual(row[field], getattr(resolved, field))

    def test_rate_filter_uses_whole_input_relation_group(self):
        self.connection.execute("""insert into app.invoices(legacy_mongo_id, invoice_type, invoice_no,
            invoice_date, invoice_month, seller_name, amount, signed_amount, tax_amount, total_with_tax, tax_rate, status)
            values ('rate-known', 'input', 'RATE-1', '2026-10-04', '2026-10-01', '供应商', 100, 100, 13, 113, '13%%', 'pending'),
                ('rate-unknown', 'input', 'RATE-2', '2026-10-04', '2026-10-01', '供应商', 100, 100, 13, 113, null, 'pending')""")
        self.connection.execute("""insert into app.workbench_pair_relations(case_id, relation_mode, status,
            version, month_scope, row_ids, row_types, amount_check, special_metadata, raw_payload)
            values ('rate-group', 'manual', 'active', 1, '2026-10-01', array['rate-known','rate-unknown'],
                array['input_invoice','input_invoice'], '{}'::jsonb, '{}'::jsonb, '{}'::jsonb)""")
        service = InputInvoiceUsageCanonicalQueryService(
            repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
            row_assembler=InputInvoiceUsageQueryService(
                import_service=ImportNormalizationService(),
                payment_rules_provider=_UnexpectedPaymentRulesProvider(),
            ),
        )
        def filtered(rate):
            return service.list_rows(filters=[{"field": "tax_rate", "operator": "in", "values": [rate]}], include_statistics=False)
        unknown = filtered("无法确定")
        self.assertEqual(unknown["pagination"]["total"], 1)
        self.assertEqual(unknown["rows"][0]["invoice"]["taxRate"], "无法确定")
        self.assertEqual(unknown["rows"][0]["invoice"]["totalWithTax"], "226.00")
        self.assertEqual(filtered("13%")["pagination"]["total"], 0)
        self.connection.execute("update app.invoices set tax_rate=%s where legacy_mongo_id='rate-unknown'", ("6%",))
        self.assertEqual(filtered("多税率")["rows"][0]["invoice"]["taxRate"], "多税率")
        self.assertEqual(filtered("13%")["pagination"]["total"], 0)

    def test_import_missing_amount_round_trips_provenance_through_postgres(self):
        repository = PostgresCoreRepository(self.connection)
        importer = ImportNormalizationService(fact_repository=repository)
        raw = {"invoice_no": "12345678901234567891", "counterparty_name": "供应商", "invoice_date": "2026-10-03",
               "amount": None, "tax_amount": "13", "total_with_tax": "113", "tax_rate": "13%"}
        raw["source_line_items"] = [{"amount": "100", "tax_amount": "13", "total_with_tax": "113", "tax_rate": "13%"}]
        normalized, errors = importer._normalize_invoice_row(batch_type=BatchType.INPUT_INVOICE, raw_row=raw)
        self.assertEqual(errors, [])
        invoice = importer._build_invoice_from_normalized(BatchType.INPUT_INVOICE, "test-batch", normalized)
        repository._save_invoice(self.connection, repository._serialize(invoice))
        loaded = repository.get_invoice(invoice.id)
        self.assertEqual(loaded.amount, Decimal("100"))
        self.assertEqual(loaded.inferred_fields, ["amount"])
        self.assertEqual(loaded.source_line_items, raw["source_line_items"])
        from fin_ops_platform.services.source_record_details import invoice_source_detail
        detail = invoice_source_detail({"primary": loaded, "line_items": [loaded], "identity_key": "test"})
        self.assertIn("100.00（推算）", [field["value"] for section in detail["sections"] for field in section["fields"]])

    def test_rows_reuse_snapshot_payment_rules_without_row_level_settings_reads(
        self,
    ) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                seller_name, amount, signed_amount, tax_amount, total_with_tax, status
            ) values (
                'input-snapshot-rule-1', 'input', 'INV-001', '2026-07-31', '2026-07-01',
                '材料供应商', 100, 100, 18, 118, 'pending'
            )
            """
        )
        legacy_provider = _UnexpectedPaymentRulesProvider()
        row_assembler = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(),
            payment_rules_provider=legacy_provider,
        )

        payload = InputInvoiceUsageCanonicalQueryService(
            repository=PostgresInputInvoiceUsageQueryRepository(self.connection),
            row_assembler=row_assembler,
        ).list_rows(page=1, page_size=20, include_statistics=False)

        self.assertEqual(payload["pagination"]["total"], 1)
        [row] = payload["rows"]
        self.assertEqual(row["invoiceId"], "input-snapshot-rule-1")
        self.assertEqual(row["paymentStatus"]["code"], "pending")
        self.assertEqual(legacy_provider.evaluate_count, 0)

    def test_output_reversal_remark_keeps_exact_summary_order_and_supporting_group(self) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date, invoice_month, seller_name, buyer_name, amount,
                signed_amount, tax_amount, total_with_tax, status, raw_payload
            ) values
                (
                    'output-blue-1', 'output', 'OUT-BLUE-001',
                    '26532000000809302711', '2026-07-10', '2026-07-01',
                    '销售方', '购买方', 100, 100, 18, 118, 'pending', '{}'::jsonb
                ),
                (
                    'output-red-1', 'output', 'OUT-RED-001',
                    '26532000000808367761', '2026-07-11', '2026-07-01',
                    '销售方', '购买方', -100, -100, -18, -118, 'pending',
                    jsonb_build_object(
                        'normalized_payload',
                        jsonb_build_object(
                            'remark',
                            '被红冲蓝字数电发票号码：26532000000809302711'
                        )
                    )
                )
            """
        )

        repository = PostgresOutputInvoiceCollectionQueryRepository(self.connection)
        snapshot = repository.load_page(
            page=1,
            page_size=1,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-07",
            filters=[],
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertEqual(snapshot.pagination, {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(
            snapshot.summary,
            {
                "invoiceCount": 2,
                "totalWithTax": "0.00",
                "amountWithoutTax": "0.00",
                "collectedAmount": "0.00",
                "pendingAmount": "0.00",
                "pendingCollectionCount": 0,
                "partialCollectionCount": 0,
            },
        )
        self.assertEqual(
            snapshot.statistics,
            {
                "invoiceCount": 2,
                "incomeBankTransactionCount": 0,
                "blueInvoiceCount": 1,
                "redInvoiceCount": 1,
            },
        )
        self.assertEqual(
            snapshot.statistics["blueInvoiceCount"]
            + snapshot.statistics["redInvoiceCount"],
            snapshot.statistics["invoiceCount"],
        )
        self.assertEqual(
            [group["primary"].id for group in snapshot.groups],
            ["output-blue-1"],
        )
        self.assertEqual(snapshot.groups[0]["status_code"], "reversed_by_red")
        self.assertEqual(
            [group["primary"].id for group in snapshot.supporting_groups],
            ["output-red-1"],
        )
        self.assertEqual(snapshot.supporting_groups[0]["status_code"], "reverses_blue")

        query_service = OutputInvoiceCollectionCanonicalQueryService(
            repository=repository,
            row_assembler=OutputInvoiceCollectionQueryService(
                import_service=ImportNormalizationService(),
            ),
        )
        rows = query_service.list_rows(page=1, page_size=20, month="2026-07")["rows"]
        blue_row = next(row for row in rows if row["invoiceId"] == "output-blue-1")

        details = query_service.relation_details(
            blue_row["id"],
            {"kind": ["invoice"]},
        )

        self.assertEqual(details["rowId"], blue_row["id"])
        self.assertEqual(details["relationCount"], 2)
        self.assertEqual(
            [summary["invoiceId"] for summary in details["summaries"]],
            ["output-blue-1", "output-red-1"],
        )

    def test_output_over_collection_is_collected_with_zero_pending_amount(self) -> None:
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                seller_name, buyer_name, amount, signed_amount, tax_amount,
                total_with_tax, status
            ) values (
                'output-over-collected-1', 'output', 'OUT-OVER-001', '2026-07-10',
                '2026-07-01', '销售方', '购买方', 100, 100, 0, 100, 'pending'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            ) values (
                'output-over-collected-bank-1', '62220001', 'inflow', '购买方',
                120, 120, '2026-07-12', '2026-07-01', 'pending'
            )
            """
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'output-over-collected-relation-1', 'manual', 'active', 1,
                '2026-07-01',
                array['output-over-collected-1', 'output-over-collected-bank-1'],
                array['output_invoice', 'bank_transaction'], '{}'::jsonb,
                '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        snapshot = PostgresOutputInvoiceCollectionQueryRepository(
            self.connection
        ).load_page(
            page=1,
            page_size=20,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            month="2026-07",
            filters=[],
            sort_field="total_with_tax",
            sort_direction="desc",
        )

        self.assertEqual(snapshot.pagination, {"page": 1, "pageSize": 20, "total": 1})
        self.assertEqual(snapshot.groups[0]["status_code"], "collected")
        self.assertEqual(snapshot.groups[0]["pending_amount"], "0.00")
        self.assertEqual(
            snapshot.summary,
            {
                "invoiceCount": 1,
                "totalWithTax": "100.00",
                "amountWithoutTax": "100.00",
                "collectedAmount": "120.00",
                "pendingAmount": "0.00",
                "pendingCollectionCount": 0,
                "partialCollectionCount": 0,
            },
        )
        self.assertEqual(
            snapshot.statistics,
            {
                "invoiceCount": 1,
                "incomeBankTransactionCount": 1,
                "blueInvoiceCount": 1,
                "redInvoiceCount": 0,
            },
        )

    def test_output_red_remark_is_searchable_and_preserved_in_canonical_detail(self) -> None:
        target_invoice_no = "26532000000395506981"
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date, invoice_month, seller_name, buyer_name, amount,
                signed_amount, tax_amount, total_with_tax, status, raw_payload
            ) values (
                'output-red-remark-1', 'output', 'OUT-RED-REMARK-001',
                '26532000001069507471', '2026-07-10', '2026-07-01',
                '销售方', '购买方', -100, -100, -6, -106, 'pending',
                jsonb_build_object(
                    'normalized_payload',
                    jsonb_build_object(
                        'invoice_no', 'OUT-RED-REMARK-001',
                        'digital_invoice_no', '26532000001069507471',
                        'invoice_type', 'output',
                        'invoice_date', '2026-07-10',
                        'amount', '-100.00',
                        'tax_amount', '-6.00',
                        'total_with_tax', '-106.00',
                        'seller_name', '销售方',
                        'buyer_name', '购买方',
                        'is_positive_invoice', '否',
                        'remark', '被红冲蓝字数电发票号码：26532000000395506981'
                    )
                )
            )
            """
        )
        repository = PostgresOutputInvoiceCollectionQueryRepository(self.connection)
        query_service = OutputInvoiceCollectionCanonicalQueryService(
            repository=repository,
            row_assembler=OutputInvoiceCollectionQueryService(
                import_service=ImportNormalizationService(),
            ),
        )

        payload = query_service.list_rows(
            page=1,
            page_size=20,
            keyword=target_invoice_no,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        [row] = payload["rows"]
        self.assertEqual(
            row["invoice"]["reversalTargetInvoiceNos"],
            [target_invoice_no],
        )
        detail = query_service.invoice_detail("output-red-remark-1")
        self.assertEqual(
            detail["remark"],
            f"被红冲蓝字数电发票号码：{target_invoice_no}",
        )
        self.assertEqual(
            detail["reversalTargetInvoiceNos"],
            [target_invoice_no],
        )

    def test_output_company_search_keeps_every_canonical_invoice_as_its_own_row(
        self,
    ) -> None:
        buyer_name = "成都智领趋势科技有限公司"
        target_invoice_no = "26532000000809302711"
        self.connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date, invoice_month, seller_name, buyer_name, amount,
                signed_amount, tax_amount, total_with_tax, status, raw_payload
            ) values
                (
                    'company-blue-small', 'output', 'COMPANY-BLUE-SMALL',
                    '26532000001153800406', '2026-07-10', '2026-07-01',
                    '销售方', %s, 3362.83, 3800, 437.17, 3800, 'pending', '{}'::jsonb
                ),
                (
                    'company-blue-collected', 'output', 'COMPANY-BLUE-COLLECTED',
                    '26532000000809764126', '2026-05-21', '2026-05-01',
                    '销售方', %s, 161415.93, 182400, 20984.07, 182400,
                    'pending', '{}'::jsonb
                ),
                (
                    'company-red', 'output', 'COMPANY-RED',
                    '26532000000808367761', '2026-06-29', '2026-06-01',
                    '销售方', %s, -161415.93, -182400, -20984.07, -182400,
                    'pending',
                    jsonb_build_object(
                        'normalized_payload',
                        jsonb_build_object(
                            'remark',
                            '被红冲蓝字数电发票号码：26532000000809302711'
                        )
                    )
                ),
                (
                    'company-blue-target', 'output', 'COMPANY-BLUE-TARGET',
                    %s, '2026-05-21', '2026-05-01',
                    '销售方', %s, 161415.93, 182400, 20984.07, 182400,
                    'pending', '{}'::jsonb
                )
            """,
            (
                buyer_name,
                buyer_name,
                buyer_name,
                target_invoice_no,
                buyer_name,
            ),
        )
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, txn_direction, counterparty_name_raw,
                amount, signed_amount, txn_date, txn_month, status
            ) values (
                'company-bank', '62220001', 'inflow', %s,
                182400, 182400, '2026-05-21', '2026-05-01', 'pending'
            )
            """,
            (buyer_name,),
        )
        self.connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'company-collection-relation', 'manual', 'active', 1,
                '2026-05-01',
                array[
                    'company-blue-collected', 'company-red',
                    'company-blue-target', 'company-bank'
                ],
                array[
                    'output_invoice', 'output_invoice',
                    'output_invoice', 'bank_transaction'
                ],
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        repository = PostgresOutputInvoiceCollectionQueryRepository(self.connection)
        query_service = OutputInvoiceCollectionCanonicalQueryService(
            repository=repository,
            row_assembler=OutputInvoiceCollectionQueryService(
                import_service=ImportNormalizationService(),
            ),
        )

        payload = query_service.list_rows(
            page=1,
            page_size=20,
            keyword=buyer_name,
        )

        self.assertEqual(payload["pagination"]["total"], 4)
        rows = {row["invoiceId"]: row for row in payload["rows"]}
        self.assertEqual(
            set(rows),
            {
                "company-blue-small",
                "company-blue-collected",
                "company-red",
                "company-blue-target",
            },
        )
        self.assertEqual(
            rows["company-blue-collected"]["collectionStatus"]["code"],
            "collected",
        )
        self.assertEqual(
            rows["company-blue-target"]["collectionStatus"]["code"],
            "reversed_by_red",
        )
        self.assertEqual(
            rows["company-red"]["collectionStatus"]["code"],
            "reverses_blue",
        )
        self.assertEqual(
            rows["company-blue-collected"]["bankTransactions"]["receivedTotal"],
            "182400.00",
        )
        self.assertEqual(
            rows["company-blue-target"]["bankTransactions"]["receivedTotal"],
            "0.00",
        )


if __name__ == "__main__":
    unittest.main()
