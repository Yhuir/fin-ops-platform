from __future__ import annotations

import unittest
from copy import deepcopy
from decimal import Decimal

from fin_ops_platform.services.invoice_header_fact_repair_service import build_verified_financial_repair_plan
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_verified_financial_repair,
    load_verified_financial_repair_snapshot,
)

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


def sample():
    invoice = dict(invoice_id='repair-1', invoice_type='input', invoice_code='053002400111',
                   invoice_no='23195398', digital_invoice_no=None, invoice_date='2026-01-13',
                   amount='0.33', signed_amount='0.33', tax_amount='3.67', total_with_tax='4.00',
                   tax_rate='9%', raw_payload={'normalized_payload': {'source_links':[{'source_id':'preserved'}]}})
    fact = dict(invoice, amount='3.67', tax_amount='0.33')
    source = dict(file_id='source-1', filename='tax.xlsx', sha256='a'*64, rows=[fact])
    cache = dict(source_attachment_key='cache-1', parser_version='old', invoices=[invoice])
    return invoice, source, cache


class VerifiedFinancialRepairTests(unittest.TestCase):
    def build(self, invoice=None, source=None, cache=None):
        base = sample()
        return build_verified_financial_repair_plan([invoice or base[0]], invoice_ids=['repair-1'],
            sources=[source or base[1]], cache_rows=[cache or base[2]])

    def test_swapped_fields_fixed_without_changing_identity_relations_or_total(self):
        plan = self.build()
        update = plan['updates'][0]
        self.assertEqual((update['amount'], update['tax_amount'], update['total_with_tax']), ('3.67','0.33','4.00'))
        self.assertEqual(update['identity_key'], '053002400111:23195398')
        self.assertEqual(update['raw_payload']['normalized_payload']['source_links'], [{'source_id':'preserved'}])
        self.assertEqual(plan['invalidate_cache_keys'], ['cache-1'])

    def test_missing_tax_is_not_zero_and_conflicting_originals_are_rejected(self):
        invoice, source, cache = sample()
        source['rows'][0]['tax_amount'] = None
        update = self.build(source=source)["updates"][0]
        self.assertIsNone(update["tax_amount"])
        self.assertEqual(update["amount"], "3.67")
        invoice, source, cache = sample()
        other = deepcopy(source)
        other['rows'][0].update(amount='2.00', tax_amount='2.00')
        with self.assertRaisesRegex(ValueError, 'disagree'):
            build_verified_financial_repair_plan([invoice], invoice_ids=['repair-1'], sources=[source,other],cache_rows=[])

    def test_missing_target_date_or_total_changes_fail(self):
        invoice, source, cache = sample()
        with self.assertRaisesRegex(ValueError, 'exactly once'):
            build_verified_financial_repair_plan([], invoice_ids=['repair-1'],sources=[source],cache_rows=[])
        source['rows'][0]['invoice_date']='2026-01-14'
        with self.assertRaisesRegex(ValueError, 'date/type'):
            self.build(source=source)
        source['rows'][0].update(invoice_date='2026-01-13',amount='4.67',total_with_tax='5.00')
        with self.assertRaisesRegex(ValueError, 'total'):
            self.build(source=source)

    def test_second_run_is_zero_and_changed_snapshot_changes_fingerprint(self):
        invoice, source, cache = sample()
        first=self.build()
        invoice.update(amount='3.67',signed_amount='3.67',tax_amount='0.33',raw_payload=first['updates'][0]['raw_payload'])
        again=build_verified_financial_repair_plan([invoice],invoice_ids=['repair-1'],sources=[source],cache_rows=[])
        self.assertEqual(again['updates'],[])
        self.assertEqual(again['invalidate_cache_keys'],[])
        self.assertNotEqual(first['source_fingerprint'],again['source_fingerprint'])

    def test_proof_contains_exact_source_values_identity_and_existing_fingerprint_on_recheck(self):
        invoice, source, _cache = sample()
        source["rows"][0]["source_line_items"] = [{"amount": "3.67", "tax_amount": "0.33", "tax_rate": "9%"}]
        first = self.build(invoice, source)
        proof = first["verified_invoice_facts"][0]
        self.assertEqual(proof["invoice_id"], "repair-1")
        self.assertEqual(proof["identity_key"], "053002400111:23195398")
        self.assertEqual(proof["invoice_type"], "input")
        self.assertEqual(proof["invoice_date"], "2026-01-13")
        self.assertEqual((proof["source_file_id"], proof["source_sha256"]), ("source-1", "a" * 64))
        self.assertEqual(proof["repair_fingerprint"], first["source_fingerprint"])
        self.assertEqual(proof["party_after"], {})
        self.assertEqual(proof["after"], {
            "amount": "3.67", "signed_amount": "3.67", "tax_amount": "0.33",
            "total_with_tax": "4.00", "tax_rate": "9%", "tax_amount_text": None,
            "source_line_items": [{"amount": "3.67", "tax_amount": "0.33", "tax_rate": "9%",
                                   "total_with_tax": None, "tax_amount_text": None}],
        })
        invoice.update({key: first["updates"][0][key] for key in
                        ("amount", "signed_amount", "tax_amount", "total_with_tax", "tax_rate", "raw_payload")})
        before = deepcopy(invoice)
        again = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"], sources=[source], cache_rows=[])
        self.assertEqual(again["update_count"], 0)
        self.assertEqual(again["verified_invoice_facts"], [proof])
        self.assertNotEqual(again["source_fingerprint"], proof["repair_fingerprint"])
        self.assertEqual(invoice, before)

    def test_correct_canonical_values_do_not_certify_inconsistent_normalized_payload(self):
        invoice, source, _cache = sample()
        first = self.build(invoice, source)
        update = first["updates"][0]
        invoice.update({key: update[key] for key in ("amount", "signed_amount", "tax_amount", "total_with_tax", "tax_rate", "raw_payload")})
        for field, value in (("amount", "0.33"), ("source_line_count", 99), ("tax_rate", "13%")):
            with self.subTest(field=field):
                invalid = deepcopy(invoice)
                invalid["raw_payload"]["normalized_payload"][field] = value
                plan = self.build(invalid, source)
                self.assertEqual(plan["update_count"], 1)
                self.assertEqual(plan["verified_invoice_facts"][0]["repair_fingerprint"], plan["source_fingerprint"])
                self.assertEqual(plan["updates"][0]["raw_payload"]["normalized_payload"][field],
                                 invoice["raw_payload"]["normalized_payload"][field])

    def test_recheck_preserves_registered_original_when_duplicate_sources_have_different_positions(self):
        invoice, source, _cache = sample()
        source["rows"][0]["source_line_items"] = [{"amount": "3.67", "tax_amount": "0.33", "source_row_number": 2}]
        first = self.build(invoice, source)
        invoice.update({key: first["updates"][0][key] for key in
                        ("amount", "signed_amount", "tax_amount", "total_with_tax", "tax_rate", "raw_payload")})
        duplicate = deepcopy(source)
        duplicate.update(file_id="other-source", sha256="b" * 64)
        duplicate["rows"][0]["source_line_items"][0]["source_row_number"] = 9
        again = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
            sources=[duplicate, source], cache_rows=[])
        self.assertEqual(again["update_count"], 0)
        self.assertEqual(again["verified_invoice_facts"], first["verified_invoice_facts"])

    def test_real_oa_pdf_parser_to_repair_cli_normalizes_type_and_rejects_direction_mismatch(self):
        import io
        import json
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        import fitz

        from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
        from fin_ops_platform.services.postgres_repositories import import_audit_repair as repository
        from fin_ops_platform.tools import import_audit_repair_ops as cli

        with fitz.open() as document:
            page = document.new_page(width=620, height=800)
            for point, text in [
                ((20, 30), "电子发票（普通发票）"),
                ((350, 60), "发票号码："), ((350, 90), "开票日期："),
                ((20, 130), "名称："), ((320, 130), "名称："),
                ((20, 160), "纳税人识别号："), ((320, 160), "纳税人识别号："),
                ((20, 230), "合计 ¥175.47 ¥10.53"),
                ((20, 260), "价税合计（小写）¥186.00"),
                ((420, 60), "26317000002920092512"), ((420, 90), "2026年08月10日"),
                ((55, 130), "测试购买有限公司"), ((355, 130), "测试销售有限公司"),
                ((110, 160), "915300007194052520"), ((410, 160), "91310110350849784X"),
            ]:
                page.insert_text(point, text, fontname="china-s", fontsize=10)
            content = document.tobytes()
        original = OAAttachmentInvoiceService().parse_content_result(
            {"fileName": "invoice.pdf", "filePath": "/invoice.pdf"}, content)
        self.assertEqual(original["parse_status"], "parsed")
        self.assertEqual(original["evidences"][0]["invoice_type"], "进项发票")
        invoice = dict(sample()[0], invoice_code=None, invoice_no="26317000002920092512",
            digital_invoice_no="26317000002920092512", invoice_date="2026-08-10",
            amount="175.47", signed_amount="175.47", tax_amount="10.53", total_with_tax="186.00")
        connection = Mock()
        transaction = Mock()
        connection.transaction.side_effect = lambda: nullcontext(transaction)
        base = ["--repair-invoice-oa-source", "oa-original", "--invoice-id", "repair-1", "--dry-run"]
        attachment = {"source_attachment_key": "oa-original", "filename": "invoice.pdf",
                      "normalized_payload": {"file_path": "/invoice.pdf"}}
        with patch.object(cli, "PostgresConnection", return_value=connection), \
             patch.object(cli.PostgresSettings, "from_env", return_value=SimpleNamespace()), \
             patch.object(cli, "_build_bank_repair_state_store", return_value=SimpleNamespace()), \
             patch.object(repository, "load_original_invoice_attachments", return_value=[attachment]), \
             patch.object(repository, "load_verified_financial_repair_snapshot", return_value={"snapshot": [invoice], "cache_rows": []}), \
             patch.object(OAAttachmentInvoiceService, "_download_content", return_value=content), \
             patch.object(OAAttachmentInvoiceService, "_run_image_ocr") as ocr:
            output = io.StringIO()
            self.assertEqual(cli.main(base, stdout=output), 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["verified_invoice_count"], 1)
            self.assertEqual(result["updates"][0]["amount"], "175.47")
            self.assertEqual(result["updates"][0]["tax_amount"], "10.53")
            self.assertEqual(result["updates"][0]["total_with_tax"], "186.00")
            ocr.assert_not_called()
            invoice["invoice_type"] = "output"
            with self.assertRaisesRegex(ValueError, "date/type differs"):
                cli.main(base, stdout=io.StringIO())
            invoice["invoice_type"] = "input"
            for bad_type in (None, "unknown"):
                evidence = deepcopy(original)
                evidence["evidences"][0]["invoice_type"] = bad_type
                with self.subTest(invoice_type=bad_type), \
                     patch.object(OAAttachmentInvoiceService, "parse_content_result", return_value=evidence), \
                     self.assertRaisesRegex(ValueError, "unsupported or missing invoice type"):
                    cli.main(base, stdout=io.StringIO())

    def test_audit_service_preserves_large_verified_fact_batches_and_full_source_lines(self):
        from datetime import UTC, datetime
        from unittest.mock import Mock

        from fin_ops_platform.services.audit import AuditTrailService

        proof = self.build()["verified_invoice_facts"][0]
        proof["after"]["source_line_items"] = [
            {"taxable_item_name": "真实原件的长明细名称" * 32, "amount": "1.00", "tax_amount": "*",
             "source_row_number": index, "source_region_key": f"page:1/item:{index}"}
            for index in range(12)
        ]
        facts = [{**proof, "invoice_id": f"invoice-{index}"} for index in range(1500)]
        metadata = {"event_type": "operation.completed", "outcome": "success", "verified_invoice_facts": facts}
        repository = Mock()
        repository.append_operation_event.return_value = {"id": "audit-proof", "occurred_at": datetime.now(UTC)}
        AuditTrailService(repository).record_action(actor_id="tester", action="invoice_financial_source_repair",
            entity_type="invoice", entity_id="source-proof", metadata=metadata)
        recorded = repository.append_operation_event.call_args.args[0]["payload"]["metadata"]
        self.assertEqual(recorded["verified_invoice_facts"], facts)
        self.assertEqual(len(recorded["verified_invoice_facts"]), 1500)
        self.assertEqual(len(recorded["verified_invoice_facts"][-1]["after"]["source_line_items"]), 12)

    def test_zero_update_cli_reverifies_original_and_appends_proof_without_rewriting_facts(self):
        import hashlib
        import io
        import json
        from contextlib import nullcontext
        from types import SimpleNamespace
        from unittest.mock import Mock, patch

        from openpyxl import Workbook

        from fin_ops_platform.services.import_file_service import attach_invoice_line_evidence, parse_invoice_source_rows, read_xlsx_import_rows
        from fin_ops_platform.services.postgres_repositories import import_audit_repair as repository
        from fin_ops_platform.tools import import_audit_repair_ops as cli

        workbook = Workbook()
        workbook.active.title = "发票基础信息"
        workbook.active.append(["发票代码", "发票号码", "开票日期", "金额", "税额", "价税合计", "销方识别号", "购买方名称", "销方名称", "购方识别号"])
        workbook.active.append(["053002400111", "23195398", "2026-01-13", "3.67", "0.33", "4.00", "915300002165678829", "正确购方", "正确销方", "915300007194052520"])
        stream = io.BytesIO()
        workbook.save(stream)
        workbook.close()
        content = stream.getvalue()
        digest = hashlib.sha256(content).hexdigest()
        parsed = read_xlsx_import_rows(content)
        source = {"file_id": "source-1", "filename": "tax.xlsx", "sha256": digest,
                  "rows": attach_invoice_line_evidence(parse_invoice_source_rows(parsed.rows),
                      parsed.invoice_detail_rows or [], header_sheet_name=parsed.invoice_header_sheet_name)}
        invoice = sample()[0]
        original = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"], sources=[source], cache_rows=[])
        invoice.update({key: original["updates"][0][key] for key in
                        ("amount", "signed_amount", "tax_amount", "total_with_tax", "tax_rate", "raw_payload")})
        before = deepcopy(invoice)
        plan = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"], sources=[source], cache_rows=[])
        connection = Mock()
        transaction = Mock()
        connection.transaction.side_effect = lambda: nullcontext(transaction)
        audit = Mock()
        output = io.StringIO()
        with patch.object(cli, "PostgresConnection", return_value=connection), \
             patch.object(cli.PostgresSettings, "from_env", return_value=SimpleNamespace()), \
             patch.object(cli, "load_import_source_file", return_value={"sha256": digest, "stored_file_path": "source", "original_filename": "tax.xlsx"}), \
             patch.object(cli, "_build_bank_repair_state_store", return_value=SimpleNamespace(read_import_file=lambda path: content)), \
             patch.object(repository, "load_verified_financial_repair_snapshot", return_value={"snapshot": [invoice], "cache_rows": []}) as load, \
             patch.object(repository, "apply_verified_financial_repair", return_value={"written_invoice_count": 0, "invalidated_cache_count": 0}) as apply, \
             patch.object(cli, "AuditTrailService", return_value=audit):
            self.assertEqual(cli.main(["--repair-invoice-financial-source", "source-1", "--invoice-id", "repair-1", "--execute",
                "--expected-fingerprint", plan["source_fingerprint"], "--operator-id", "tester", "--reason", "verify original proof"], stdout=output), 0)
        self.assertEqual([call.kwargs["lock"] for call in load.call_args_list], [False, True])
        self.assertEqual(apply.call_args.args[1]["updates"], [])
        self.assertEqual(apply.call_args.args[1]["invalidate_cache_keys"], [])
        audit.record_action.assert_called_once()
        event = audit.record_action.call_args.kwargs
        self.assertEqual((event["action"], event["entity_type"]), ("invoice_financial_source_repair", "invoice"))
        metadata = event["metadata"]
        self.assertEqual((metadata["event_type"], metadata["outcome"]), ("operation.completed", "success"))
        self.assertEqual(metadata["verified_invoice_facts"], original["verified_invoice_facts"])
        self.assertEqual(metadata["corrections"], [])
        self.assertEqual(metadata["sources"], [{"file_id": "source-1", "sha256": digest, "filename": "tax.xlsx"}])
        result = json.loads(output.getvalue())
        self.assertEqual(result["completion"]["written_invoice_count"], 0)
        self.assertEqual(result["verified_invoice_count"], 1)
        self.assertEqual(invoice, before)

    def test_real_source_lines_and_special_tax_remain_distinct_from_missing_and_zero(self):
        invoice, source, cache = sample()
        source["rows"][0].update(amount="4.00", tax_amount="*", tax_rate="不征税",
            source_line_items=[dict(amount="4.00", tax_amount="*", tax_rate="不征税", total_with_tax=None)])
        plan = self.build(invoice, source, cache)
        update = plan["updates"][0]
        self.assertIsNone(update["tax_amount"])
        self.assertEqual(update["tax_amount_text"], "*")
        self.assertEqual(update["tax_rate"], "不征税")
        lines = update["raw_payload"]["normalized_payload"]["source_line_items"]
        self.assertEqual(len(lines), 1)
        self.assertIsNone(lines[0]["total_with_tax"])
        self.assertEqual(lines[0]["tax_amount_text"], "*")
        source["rows"][0].update(amount=None, tax_amount=None, tax_rate=None, source_line_items=[])
        update = self.build(invoice, source, cache)["updates"][0]
        self.assertIsNone(update["amount"])
        self.assertIsNone(update["signed_amount"])
        self.assertEqual(update["raw_payload"]["normalized_payload"]["source_line_items"], [])

    def test_numeric_zero_rate_is_preserved_in_original_header_and_detail(self):
        invoice, source, cache = sample()
        source["rows"][0].update(amount="4.00", tax_amount="0", tax_rate=0,
            source_line_items=[dict(amount="4.00", tax_amount="0", tax_rate=0)])
        update = self.build(invoice, source, cache)["updates"][0]
        self.assertEqual(update["tax_rate"], "0")
        self.assertEqual(update["tax_amount"], "0.00")
        self.assertEqual(update["raw_payload"]["normalized_payload"]["source_line_items"][0]["tax_rate"], "0")

    def test_explicit_empty_normalized_payload_does_not_copy_root_fields_or_retired_marker(self):
        invoice, source, cache = sample()
        invoice["raw_payload"] = {"root_only": "raw source metadata", "inferred_fields": ["amount"], "normalized_payload": {}}
        update = self.build(invoice, source, cache)["updates"][0]
        self.assertEqual(update["raw_payload"]["root_only"], "raw source metadata")
        self.assertNotIn("inferred_fields", update["raw_payload"])
        self.assertNotIn("root_only", update["raw_payload"]["normalized_payload"])
        self.assertNotIn("normalized_payload", update["raw_payload"]["normalized_payload"])
        invoice.update({key: update[key] for key in ("amount", "signed_amount", "tax_amount", "total_with_tax", "tax_rate", "raw_payload")})
        self.assertEqual(self.build(invoice, source, cache)["update_count"], 0)

    def test_duplicate_originals_compare_business_lines_without_source_position_metadata(self):
        invoice, source, cache = sample()
        line = {"amount": "3.67", "tax_amount": "0.33", "tax_rate": "9%", "source_row_number": 2,
                "source_sheet_name": "信息汇总表", "source_region_key": "page:1/item:1"}
        source["rows"][0]["source_line_items"] = [line]
        other = deepcopy(source)
        other["rows"][0]["source_line_items"][0].update(source_row_number=7, source_sheet_name="另一个原件", source_region_key="page:2/item:1")
        plan = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"], sources=[source, other], cache_rows=[])
        self.assertEqual(plan["update_count"], 1)
        self.assertEqual(plan["updates"][0]["raw_payload"]["normalized_payload"]["source_line_items"][0]["source_row_number"], 2)
        other["rows"][0]["source_line_items"].append(dict(line))
        with self.assertRaisesRegex(ValueError, "disagree"):
            build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"], sources=[source, other], cache_rows=[])

    def test_party_repair_is_opt_in_complete_and_preserves_provenance(self):
        invoice, source, cache = sample()
        fields = dict(seller_name="正确销方", seller_tax_no="915300002165678829",
                      buyer_name="正确购方", buyer_tax_no="915300007194052520")
        invoice.update({key: "旧值" for key in fields}, counterparty_name="旧值")
        source["rows"][0].update(fields)
        self.assertEqual(self.build(invoice, source)["updates"][0]["party_fields"], {})
        plan = build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
            sources=[source], cache_rows=[cache], repair_party_fields=True)
        update = plan["updates"][0]
        self.assertEqual(update["party_fields"]["seller_tax_no"], fields["seller_tax_no"])
        normalized = update["raw_payload"]["normalized_payload"]
        self.assertEqual(normalized["counterparty"]["name"], fields["seller_name"])
        self.assertEqual(normalized["source_links"], [{"source_id": "preserved"}])
        invoice.update({key: update[key] for key in ("amount", "signed_amount", "tax_amount", "total_with_tax")})
        # Party-only discrepancies still need correction after an earlier amount-only repair.
        self.assertEqual(build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
            sources=[source], cache_rows=[], repair_party_fields=True)["update_count"], 1)
        invoice.update(update["party_fields"], raw_payload=update["raw_payload"])
        self.assertEqual(build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
            sources=[source], cache_rows=[], repair_party_fields=True)["update_count"], 0)
        other = deepcopy(source)
        other["rows"][0]["seller_tax_no"] = "91530000X22600103R"
        with self.assertRaisesRegex(ValueError, "disagree on party"):
            build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
                sources=[source, other], cache_rows=[], repair_party_fields=True)
        source["rows"][0]["buyer_tax_no"] = ""
        with self.assertRaisesRegex(ValueError, "explicit party"):
            build_verified_financial_repair_plan([invoice], invoice_ids=["repair-1"],
                sources=[source], cache_rows=[], repair_party_fields=True)


class VerifiedFinancialRepairPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url=require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection=PostgresConnection(PostgresSettings(database_url=self.url))
        self.addCleanup(self.connection.close)
        self.connection.execute("""insert into app.invoices(legacy_mongo_id,invoice_type,invoice_code,
            invoice_no,invoice_date,invoice_month,amount,signed_amount,tax_amount,total_with_tax,status,source_unique_key,source_links)
            values ('repair-1','input','053002400111','23195398','2026-01-13','2026-01-01',0.33,0.33,3.67,4,'pending',
                '053002400111:23195398','[{"source_id":"preserved"}]')""")
        self.connection.execute("""insert into app.oa_attachment_invoice_cache(source_attachment_key,parser_version,
            cache_schema_version,parsed_at,invoices) values ('cache-1','old','old',now(),
            '[{"invoice_code":"053002400111","invoice_no":"23195398","amount":"0.33","tax_amount":"3.67"}]')""")

    def plan(self, tx):
        return build_verified_financial_repair_plan(**load_verified_financial_repair_snapshot(tx,['repair-1']),
            invoice_ids=['repair-1'],sources=[sample()[1]])

    def test_nullable_originals_are_persisted_without_zero_and_repeat_is_idempotent(self):
        source = sample()[1]
        source["rows"][0].update(amount=None, tax_amount=None, tax_rate=None)
        with self.connection.transaction() as tx:
            plan = build_verified_financial_repair_plan(**load_verified_financial_repair_snapshot(tx, ["repair-1"]),
                invoice_ids=["repair-1"], sources=[source])
            apply_verified_financial_repair(tx, plan, operator_id="tester", reason="source only total")
        current = self.connection.fetch_one("select amount,signed_amount,tax_amount,total_with_tax from app.invoices where legacy_mongo_id='repair-1'")
        self.assertIsNone(current["amount"])
        self.assertIsNone(current["signed_amount"])
        self.assertIsNone(current["tax_amount"])
        self.assertEqual(current["total_with_tax"], Decimal("4"))
        again = build_verified_financial_repair_plan(**load_verified_financial_repair_snapshot(self.connection, ["repair-1"]),
            invoice_ids=["repair-1"], sources=[source])
        self.assertEqual(again["update_count"], 0)

    def test_transaction_rollback_cas_and_second_run_zero(self):
        with self.assertRaisesRegex(RuntimeError,'injected'):
            with self.connection.transaction() as tx:
                apply_verified_financial_repair(tx,self.plan(tx),operator_id='tester',reason='verified tax header')
                raise RuntimeError('injected')
        before=load_verified_financial_repair_snapshot(self.connection,['repair-1'])
        self.assertEqual(before['snapshot'][0]['amount'],Decimal('0.33'))
        self.assertEqual(len(before['cache_rows']),1)
        with self.connection.transaction() as tx:
            result=apply_verified_financial_repair(tx,self.plan(tx),operator_id='tester',reason='verified tax header')
        self.assertEqual(result,{'written_invoice_count':1,'invalidated_cache_count':1})
        current=self.connection.fetch_one("select amount,tax_amount,source_links from app.invoices where legacy_mongo_id='repair-1'")
        self.assertEqual(current['source_links'],[{'source_id':'preserved'}])
        self.assertEqual(current['tax_amount'],Decimal('0.33'))
        self.assertEqual(self.plan(self.connection)['updates'],[])
        self.assertEqual(self.plan(self.connection)['invalidate_cache_keys'],[])
        self.assertEqual(self.connection.fetch_one("select count(*) as n from app.financial_fact_corrections where entity_type='invoices'")['n'],1)

    def test_existing_cli_verifies_original_and_commits_audited_repair_idempotently(self):
        import hashlib
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch

        from fin_ops_platform.tools import import_audit_repair_ops as cli
        from openpyxl import Workbook

        workbook=Workbook()
        workbook.active.title='发票基础信息'
        workbook.active.append(['发票代码','发票号码','开票日期','金额','税额','价税合计','销方识别号','购买方名称','销方名称','购方识别号'])
        workbook.active.append(['053002400111','23195398','2026-01-13','3.67','0.33','4.00','915300002165678829','正确购方','正确销方','915300007194052520'])
        stream=io.BytesIO()
        workbook.save(stream)
        content=stream.getvalue()
        base=['--repair-invoice-financial-source','source-1','--invoice-id','repair-1']
        source={'sha256':hashlib.sha256(content).hexdigest(),'stored_file_path':'source','original_filename':'tax.xlsx'}
        def run(args):
            output=io.StringIO()
            with patch.object(cli.PostgresSettings,'from_env',return_value=PostgresSettings(database_url=self.url)), \
                 patch.object(cli,'load_import_source_file',return_value=source), \
                 patch.object(cli,'_build_bank_repair_state_store',return_value=SimpleNamespace(read_import_file=lambda path:content)):
                self.assertEqual(cli.main(base+args,stdout=output),0)
            return json.loads(output.getvalue())
        plan=run(['--dry-run'])
        self.assertEqual(plan['update_count'],1)
        self.assertEqual(plan['updates'][0]['before']['tax_amount'],'3.670000')
        with self.assertRaisesRegex(RuntimeError,'changed after dry-run'):
            run(['--execute','--expected-fingerprint','stale','--operator-id','tester','--reason','verified original'])
        result=run(['--execute','--expected-fingerprint',plan['source_fingerprint'],'--operator-id','tester','--reason','verified original'])
        self.assertEqual(result['completion']['written_invoice_count'],1)
        self.assertEqual(run(['--dry-run'])['update_count'],0)
        self.assertEqual(self.connection.fetch_one("select count(*) n from audit.events where action='invoice_financial_source_repair'")['n'],1)
        base.append('--repair-invoice-party-fields')
        party_plan = run(['--dry-run'])
        self.assertEqual(party_plan['update_count'], 1)
        self.assertEqual(party_plan['updates'][0]['party_after']['seller_name'], '正确销方')
        run(['--execute', '--expected-fingerprint', party_plan['source_fingerprint'],
             '--operator-id', 'tester', '--reason', 'verified names and tax IDs'])
        self.assertEqual(run(['--dry-run'])['update_count'], 0)
        event = self.connection.fetch_one("select payload->'metadata' as metadata from audit.events where action='invoice_financial_source_repair' order by occurred_at desc limit 1")
        self.assertEqual(event['metadata']['corrections'][0]['party_after']['seller_tax_no'], '915300002165678829')
        proof = event["metadata"]["verified_invoice_facts"][0]
        self.assertEqual(proof["party_after"]["seller_tax_no"], "915300002165678829")
        before_recheck = load_verified_financial_repair_snapshot(self.connection, ["repair-1"])
        verified_plan = run(["--dry-run"])
        self.assertEqual(verified_plan["update_count"], 0)
        verified_result = run(["--execute", "--expected-fingerprint", verified_plan["source_fingerprint"],
                              "--operator-id", "tester", "--reason", "reverify original"])
        self.assertEqual(verified_result["completion"]["written_invoice_count"], 0)
        self.assertEqual(verified_result["verified_invoice_count"], 1)
        self.assertEqual(load_verified_financial_repair_snapshot(self.connection, ["repair-1"]), before_recheck)
        self.assertEqual(self.connection.fetch_one("select count(*) n from audit.events where action='invoice_financial_source_repair'")["n"], 3)
        recheck = self.connection.fetch_one("select payload->'metadata' as metadata from audit.events where action='invoice_financial_source_repair' order by occurred_at desc limit 1")
        self.assertEqual(recheck["metadata"]["verified_invoice_facts"], [proof])
        self.assertEqual(recheck["metadata"]["corrections"], [])
        source['sha256']='wrong'
        with self.assertRaisesRegex(ValueError,'checksum differs'):
            run(['--dry-run'])

    def test_oa_source_cli_reuses_original_parser_and_persists_source_lines(self):
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from fin_ops_platform.tools import import_audit_repair_ops as cli
        from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
        from fin_ops_platform.services.postgres_repositories import import_audit_repair as repository

        base = ["--repair-invoice-oa-source", "oa-original", "--invoice-id", "repair-1"]
        attachment = {"source_attachment_key": "oa-original", "filename": "invoice.pdf",
                      "normalized_payload": {"file_path": "/invoice.pdf"}}
        evidence = dict(sample()[1]["rows"][0], net_amount="3.67", issue_date="2026-01-13",
            source_line_items=[{"taxable_item_name": "服务", "amount": "3.67", "tax_amount": "0.33", "tax_rate": "9%"}])
        def run(args, content=b"original pdf bytes"):
            output = io.StringIO()
            with patch.object(cli.PostgresSettings, "from_env", return_value=PostgresSettings(database_url=self.url)), \
                 patch.object(cli, "_build_bank_repair_state_store", return_value=SimpleNamespace()), \
                 patch.object(repository, "load_original_invoice_attachments", return_value=[attachment]), \
                 patch.object(OAAttachmentInvoiceService, "_download_content", return_value=content), \
                 patch.object(OAAttachmentInvoiceService, "parse_content_result", return_value={"parse_status": "parsed", "evidences": [evidence]}) as parse:
                self.assertEqual(cli.main(base + args, stdout=output), 0)
                self.assertEqual(parse.call_args.args[1], content)
            return json.loads(output.getvalue())
        plan = run(["--dry-run"])
        with self.assertRaisesRegex(RuntimeError, "changed after dry-run"):
            run(["--execute", "--expected-fingerprint", plan["source_fingerprint"], "--operator-id", "tester", "--reason", "original"], content=b"changed original")
        result = run(["--execute", "--expected-fingerprint", plan["source_fingerprint"], "--operator-id", "tester", "--reason", "original"])
        self.assertEqual(result["completion"]["written_invoice_count"], 1)
        self.assertEqual(run(["--dry-run"])["update_count"], 0)
        row = load_verified_financial_repair_snapshot(self.connection, ["repair-1"])["snapshot"][0]
        source = row["raw_payload"]["normalized_payload"]
        self.assertEqual(source["source_line_items"][0]["taxable_item_name"], "服务")
        self.assertIsNone(source["source_line_items"][0]["total_with_tax"])
        self.assertEqual(source["financial_repair_source_kind"], "oa_attachment")

    def test_party_writer_cas_atomicity_and_canonical_payload(self):
        source = sample()[1]
        source["rows"][0].update(seller_name="正确销方", seller_tax_no="915300002165678829",
            buyer_name="正确购方", buyer_tax_no="915300007194052520")
        def plan(tx):
            return build_verified_financial_repair_plan(**load_verified_financial_repair_snapshot(tx, ["repair-1"]),
                invoice_ids=["repair-1"], sources=[source], repair_party_fields=True)
        stale = plan(self.connection)
        self.connection.execute("update app.invoices set seller_name='concurrent' where legacy_mongo_id='repair-1'")
        with self.assertRaisesRegex(RuntimeError, "target changed"):
            with self.connection.transaction() as tx:
                apply_verified_financial_repair(tx, stale, operator_id="tester", reason="verified original")
        with self.assertRaisesRegex(RuntimeError, "injected"):
            with self.connection.transaction() as tx:
                apply_verified_financial_repair(tx, plan(tx), operator_id="tester", reason="verified original")
                raise RuntimeError("injected")
        before = load_verified_financial_repair_snapshot(self.connection, ["repair-1"])
        self.assertEqual(before["snapshot"][0]["seller_name"], "concurrent")
        self.assertEqual(before["snapshot"][0]["amount"], Decimal("0.33"))
        self.assertEqual(len(before["cache_rows"]), 1)
        with self.connection.transaction() as tx:
            apply_verified_financial_repair(tx, plan(tx), operator_id="tester", reason="verified original")
        row = load_verified_financial_repair_snapshot(self.connection, ["repair-1"])["snapshot"][0]
        for field in ("seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no"):
            self.assertEqual(row[field], source["rows"][0][field])
            self.assertEqual(row["raw_payload"]["normalized_payload"][field], row[field])
        self.assertEqual(row["source_links"], [{"source_id": "preserved"}])
        self.assertEqual(row["counterparty_name"], "正确销方")
        self.assertEqual(plan(self.connection)["update_count"], 0)
