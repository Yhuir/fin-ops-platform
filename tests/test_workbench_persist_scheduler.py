from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fin_ops_platform.app import server as server_module
from fin_ops_platform.app.server import Application, build_application


class CapturedThread:
    started_kwargs: list[dict[str, object]] = []

    def __init__(self, *, target, kwargs: dict[str, object], daemon: bool) -> None:
        self._target = target
        self._kwargs = kwargs
        self._daemon = daemon

    def start(self) -> None:
        self.started_kwargs.append(dict(self._kwargs))


class WorkbenchPersistSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()
        CapturedThread.started_kwargs = []

    def test_pair_relation_scheduler_coalesces_case_ids_when_stale_workers_are_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_relation(app, case_id="CASE-BATCH-42931", row_ids=["txn-batch-42931", "oa-batch-001"])
            self._create_relation(app, case_id="CASE-BATCH-154900", row_ids=["txn-batch-154900", "oa-batch-002"])

            with (
                patch.object(Application, "_workbench_pair_relation_persist_async_enabled", return_value=True),
                patch.object(server_module, "Thread", CapturedThread),
            ):
                app._schedule_workbench_pair_relation_persist(
                    changed_case_ids=["CASE-BATCH-42931"],
                    action_name="submit_batch_accounting",
                )
                app._schedule_workbench_pair_relation_persist(
                    changed_case_ids=["CASE-BATCH-154900"],
                    action_name="submit_batch_accounting",
                )

            self.assertEqual(len(CapturedThread.started_kwargs), 2)
            app._persist_workbench_pair_relations_in_background(**CapturedThread.started_kwargs[0])
            app._persist_workbench_pair_relations_in_background(**CapturedThread.started_kwargs[1])

            reloaded = build_application(data_dir=Path(temp_dir), bootstrap_mode="legacy")
            self.assertIsNotNone(
                reloaded._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BATCH-42931")
            )
            self.assertIsNotNone(
                reloaded._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BATCH-154900")
            )

    def test_pair_relation_scheduler_persists_synchronously_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_relation(app, case_id="CASE-BATCH-DURABLE", row_ids=["txn-batch-durable", "oa-batch-003"])

            with patch.object(server_module, "Thread", CapturedThread):
                app._schedule_workbench_pair_relation_persist(
                    changed_case_ids=["CASE-BATCH-DURABLE"],
                    action_name="submit_batch_accounting",
                )

            self.assertEqual(CapturedThread.started_kwargs, [])
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
