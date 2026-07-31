from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from fin_ops_platform.app.server import Application
from tests.app_test_support import build_local_state_application as build_application


class WorkbenchPersistSchedulerTests(unittest.TestCase):
    def test_pair_relation_scheduler_persists_before_returning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_relation(app, case_id="CASE-BATCH-DURABLE", row_ids=["txn-batch-durable", "oa-batch-003"])

            app._schedule_workbench_pair_relation_persist(
                changed_case_ids=["CASE-BATCH-DURABLE"],
                action_name="submit_batch_accounting",
            )

            reloaded = build_application(data_dir=Path(temp_dir), bootstrap_mode="legacy")
            self.assertIsNotNone(
                reloaded._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BATCH-DURABLE")
            )

    @staticmethod
    def _create_relation(app: Application, *, case_id: str, row_ids: list[str]) -> None:
        app._workbench_pair_relation_service.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="finance-user",
            month_scope="2026-01",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": row_ids[0],
                "oa_row_ids": [row_ids[1]],
                "year": "2026",
            },
        )


if __name__ == "__main__":
    unittest.main()
