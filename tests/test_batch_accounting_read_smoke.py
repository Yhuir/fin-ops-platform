from __future__ import annotations

import unittest
from datetime import date

from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.tools.batch_accounting_read_smoke import run_smoke
from tests.test_batch_accounting_api import HistoryRepository


class NonSerializableService:
    def build_payload(self, **_: object) -> dict[str, object]:
        return {"rows": [{"trade_time": date(2026, 1, 1)}]}


class BatchAccountingReadSmokeTests(unittest.TestCase):
    def test_smoke_validates_history_and_serialization(self):
        report = run_smoke(
            BatchAccountingService(query_repository=HistoryRepository()),
            bank_year="all",
            iterations=2,
            warmup=0,
            target_ms=1000,
        )
        self.assertEqual(report["status"], "pass")
        self.assertEqual(report["row_count"], 1)
        self.assertEqual(report["summary"]["transaction_count"], 2)
        self.assertEqual(report["contract_errors"], [])
        self.assertEqual(report["detail_check"]["checked"], 1)
        self.assertEqual(report["detail_check"]["bank_members"], 2)
        self.assertEqual(report["detail_check"]["missing_members"], 0)
        self.assertNotIn("CASE-BATCH-1", str(report))

    def test_smoke_reports_unavailable_repository_as_failure(self):
        report = run_smoke(BatchAccountingService(), bank_year="all", iterations=1, warmup=0, target_ms=1000)
        self.assertEqual(report["status"], "fail")
        self.assertIn("unexpected_status:503", report["contract_errors"])

    def test_smoke_marks_missing_history_members_as_failure(self):
        repository = HistoryRepository()
        repository.detail_payload["member_rows"] = []
        report = run_smoke(
            BatchAccountingService(query_repository=repository), bank_year="all", iterations=1, warmup=0, target_ms=1000
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["detail_check"]["missing_members"], 4)
        self.assertEqual(report["contract_errors"], ["detail_missing_canonical_members"])

    def test_smoke_marks_disappeared_relation_as_failure(self):
        repository = HistoryRepository()
        repository.snapshot["rows"][0]["relation_id"] = "missing"
        report = run_smoke(
            BatchAccountingService(query_repository=repository), bank_year="all", iterations=1, warmup=0, target_ms=1000
        )
        self.assertEqual(report["status"], "fail")
        self.assertEqual(report["detail_check"]["checked"], 1)
        self.assertEqual(report["contract_errors"], ["detail_unexpected_status:404"])

    def test_smoke_fails_fast_when_payload_is_not_json_serializable(self):
        with self.assertRaises(TypeError):
            run_smoke(NonSerializableService(), bank_year="2026", iterations=1, warmup=0, target_ms=1000)
