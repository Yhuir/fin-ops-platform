from __future__ import annotations

import hashlib
import io
import json
import os
import unittest
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from fin_ops_platform.services.etc_service import parse_etc_xml
from fin_ops_platform.services.historical_etc_repair_service import build_etc_source_lines_repair_plan
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.tools import import_audit_repair_ops as tool

from tests.test_etc_backend import real_etc_xml


def source_fixture():
    content = real_etc_xml().replace(b"<TaxRate>0.03</TaxRate>",
        "<ItemName>通行费</ItemName><Amount>18.63</Amount><TaxRate>0.03</TaxRate><ComTaxAm>0.56</ComTaxAm>".encode())
    parsed = parse_etc_xml(content)
    digest = hashlib.sha256(content).hexdigest()
    row = {"etc_invoice_id": "etc-1", "invoice_no": parsed.invoice_number, "invoice_date": parsed.issue_date,
           "amount": parsed.amount_without_tax, "tax_amount": parsed.tax_amount,
           "total_with_tax": parsed.total_amount, "version": 1,
           "raw_payload": {"normalized_payload": {"invoice_number": parsed.invoice_number,
               "xml_file_path": "object://original.xml", "xml_file_hash": digest, "tax_rate": parsed.tax_rate,
               "business_batch_id": "keep-batch", "status": "submitted"}}}
    return content, row, {"etc-1": (digest, parsed)}


class EtcSourceLinesRepairTests(unittest.TestCase):
    def test_plan_is_exact_idempotent_and_preserves_business_facts(self):
        _, row, sources = source_fixture()
        before = deepcopy(row)
        plan = build_etc_source_lines_repair_plan([row], sources)
        self.assertEqual(plan["unresolved"], [])
        self.assertEqual(row, before)
        update = plan["updates"][0]
        result = update["after_payload"]["normalized_payload"]
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(result["business_batch_id"], "keep-batch")
        self.assertEqual(result["source_line_items"][0]["taxable_item_name"], "通行费")
        row["raw_payload"] = update["after_payload"]
        self.assertEqual(build_etc_source_lines_repair_plan([row], sources)["updates"], [])

    def test_source_hash_identity_amount_or_empty_detail_blocks_writes(self):
        for field, value in (("invoice_number", "other"), ("amount_without_tax", 100), ("source_line_items", [])):
            with self.subTest(field=field):
                _, row, sources = source_fixture()
                digest, parsed = sources["etc-1"]
                sources["etc-1"] = digest, replace(parsed, **{field: value})
                plan = build_etc_source_lines_repair_plan([row], sources)
                self.assertEqual(plan["updates"], [])
                self.assertTrue(plan["unresolved"])
        _, row, sources = source_fixture()
        row["raw_payload"]["normalized_payload"]["xml_file_hash"] = "wrong"
        self.assertEqual(build_etc_source_lines_repair_plan([row], sources)["updates"], [])

    def test_non_numeric_tax_remains_none_with_source_text(self):
        _, row, sources = source_fixture()
        digest, parsed = sources["etc-1"]
        sources["etc-1"] = digest, replace(parsed, tax_amount=None, tax_amount_text="*")
        row["tax_amount"] = None
        plan = build_etc_source_lines_repair_plan([row], sources)
        self.assertEqual(plan["updates"][0]["after_payload"]["normalized_payload"]["tax_amount_text"], "*")

    def test_repository_updates_only_payload_with_compare_and_swap(self):
        _, row, sources = source_fixture()
        updates = build_etc_source_lines_repair_plan([row], sources)["updates"]
        connection = SimpleNamespace(fetch_one=Mock(return_value={"etc_invoice_id": "etc-1"}))
        self.assertEqual(PostgresOpsTaxEtcRepository(connection).apply_etc_source_lines_repair(updates), 1)
        sql, params = connection.fetch_one.call_args.args
        self.assertIn("and version = %s and raw_payload = %s::jsonb", sql)
        self.assertNotIn("amount =", sql)
        self.assertNotIn("status =", sql)
        self.assertEqual(params[1:3], ("etc-1", 1))
        connection.fetch_one.return_value = None
        with self.assertRaisesRegex(RuntimeError, "changed after preview"):
            PostgresOpsTaxEtcRepository(connection).apply_etc_source_lines_repair(updates)

    def test_cli_discovery_apply_artifact_and_stale_rejection(self):
        content, row, _ = source_fixture()
        connection = Mock()
        @contextmanager
        def transaction():
            yield connection
        connection.transaction = transaction
        repository = Mock()
        repository.load_etc_source_lines_repair_rows.return_value = [row]
        repository.apply_etc_source_lines_repair.return_value = 1
        with TemporaryDirectory() as root, patch.dict(os.environ, {"FIN_OPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT": root}), \
             patch.object(tool, "PostgresConnection", return_value=connection), \
             patch.object(tool.PostgresSettings, "from_env"), \
             patch.object(tool, "_build_bank_repair_state_store", return_value=SimpleNamespace(read_etc_invoice_file=lambda _: content)), \
             patch("fin_ops_platform.services.postgres_repositories.ops_tax_etc.PostgresOpsTaxEtcRepository", return_value=repository), \
             patch.object(tool, "AuditTrailService") as audit:
            os.chmod(root, 0o700)
            artifact = root + "/etc-lines.json"
            output = io.StringIO()
            args = tool.build_parser().parse_args(["--dry-run", "--repair-etc-source-lines", "--rollback-manifest-path", artifact])
            self.assertEqual(tool._run_etc_source_lines_repair(args, stdout=output), 0)
            report = json.loads(output.getvalue())
            self.assertEqual(report["planned_invoice_ids"], ["etc-1"])
            repository.apply_etc_source_lines_repair.assert_not_called()
            execute = tool.build_parser().parse_args(["--execute", "--repair-etc-source-lines", "--invoice-id", "etc-1",
                "--expected-fingerprint", report["source_fingerprint"], "--rollback-manifest-path", artifact,
                "--operator-id", "operator", "--reason", "original XML source repair"])
            self.assertEqual(tool._run_etc_source_lines_repair(execute, stdout=io.StringIO()), 0)
            audit.return_value.record_action.assert_called_once()
            self.assertEqual(repository.load_etc_source_lines_repair_rows.call_args.kwargs, {"lock": True})
            row["version"] = 2
            with self.assertRaisesRegex(RuntimeError, "changed after preview"):
                tool._run_etc_source_lines_repair(execute, stdout=io.StringIO())
            self.assertEqual(repository.apply_etc_source_lines_repair.call_count, 1)
            deletion = tool._delete_private_rollback_manifest_artifact("etc-lines.json",
                expected_fingerprint=report["rollback_manifest_fingerprint"])
            self.assertTrue(deletion)
            self.assertFalse(os.path.exists(artifact))

    def test_execute_requires_explicit_targets_and_cannot_mix_modes(self):
        args = tool.build_parser().parse_args(["--execute", "--repair-etc-source-lines"])
        with self.assertRaisesRegex(SystemExit, "exact ETC IDs"):
            tool._run_etc_source_lines_repair(args, stdout=io.StringIO())
        args = tool.build_parser().parse_args(["--dry-run", "--repair-etc-source-lines", "--repair-etc-invoice-payload"])
        with self.assertRaisesRegex(SystemExit, "another mode"):
            tool._run_etc_source_lines_repair(args, stdout=io.StringIO())
