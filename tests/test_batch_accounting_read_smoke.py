from __future__ import annotations

from datetime import date
import unittest

from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.tools.batch_accounting_read_smoke import run_smoke


class SnapshotRepository:
    def list_snapshot(self, *, bucket: str, **_: object) -> dict[str, object]:
        if bucket == "unsubmitted":
            return {
                "summary": {"unsubmitted_count": 1, "submitted_count": 1},
                "bank_rows": [],
                "oa_rows": [],
                "invoice_rows": [],
                "pagination": {},
            }
        return {
            "summary": {"unsubmitted_count": 1, "submitted_count": 1},
            "bank_rows": [],
            "oa_rows": [],
            "invoice_rows": [],
            "relations": [],
            "pagination": {},
        }


class NonSerializableService:
    def build_payload(self, **_: object) -> dict[str, object]:
        return {
            "summary": {},
            "bank_rows": [{"trade_date": date(2026, 1, 1)}],
            "oa_rows": [],
            "relations_by_bank_row_id": {},
            "pagination": {},
        }


class BatchAccountingReadSmokeTests(unittest.TestCase):
    def test_smoke_validates_both_canonical_buckets_and_serialization(self) -> None:
        report = run_smoke(
            BatchAccountingService(query_repository=SnapshotRepository()),
            bank_year="2026",
            iterations=2,
            warmup=0,
            target_ms=1_000,
        )

        self.assertEqual(report["status"], "pass")
        self.assertEqual([item["bucket"] for item in report["buckets"]], ["unsubmitted", "submitted"])
        self.assertTrue(all(item["contract_errors"] == [] for item in report["buckets"]))

    def test_smoke_fails_fast_when_payload_is_not_json_serializable(self) -> None:
        with self.assertRaises(TypeError):
            run_smoke(
                NonSerializableService(),  # type: ignore[arg-type]
                bank_year="2026",
                iterations=1,
                warmup=0,
                target_ms=1_000,
            )
