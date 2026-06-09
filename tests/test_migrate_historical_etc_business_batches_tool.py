from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.historical_etc_business_batch_migration_service import (
    HistoricalEtcBusinessBatchMigrationSpec,
)
from fin_ops_platform.tools.migrate_historical_etc_business_batches import _dry_run_spec, _refresh_after_historical_migration
from fin_ops_platform.tools import link_existing_etc_batches


class _EtcService:
    def __init__(self, *, submission_batch: object, invoices: list[object], business_batch: object | None = None) -> None:
        self._submission_batch = submission_batch
        self._invoices = list(invoices)
        self._business_batch = business_batch

    def get_batch(self, batch_id: str) -> object:
        if batch_id != getattr(self._submission_batch, "id"):
            raise KeyError(batch_id)
        return self._submission_batch

    def get_business_batch(self, business_batch_id: str) -> object:
        if self._business_batch is None or business_batch_id != getattr(self._business_batch, "business_batch_id"):
            raise KeyError(business_batch_id)
        return self._business_batch

    def list_invoices_by_ids(self, invoice_ids: list[str]) -> list[object]:
        ids = {str(invoice_id) for invoice_id in invoice_ids}
        return [invoice for invoice in self._invoices if str(getattr(invoice, "id")) in ids]


class _RelationService:
    def __init__(self, relation: dict[str, object] | None) -> None:
        self._relation = relation

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
        return self._relation


class MigrateHistoricalEtcBusinessBatchesToolTests(unittest.TestCase):
    def test_shared_application_builder_uses_default_data_dir_when_none_is_provided(self) -> None:
        calls: list[tuple[object, object]] = []
        default_dir = object()
        partial_state = {
            "imports": {"invoices": []},
            "file_imports": {},
            "workbench_pair_relations": {"pair_relations": {}},
            "etc_reconciliation_state": {"tasks": {}},
        }

        class StateStore:
            def load(self) -> dict[str, object]:
                raise AssertionError("full state load should not be used by ETC migration tools")

            def load_imports_snapshot(self) -> dict[str, object]:
                return partial_state["imports"]

            def load_file_imports_snapshot(self) -> dict[str, object]:
                return partial_state["file_imports"]

            def load_workbench_pair_relations(self) -> dict[str, object]:
                return partial_state["workbench_pair_relations"]

            def load_etc_reconciliation_state(self) -> dict[str, object]:
                return partial_state["etc_reconciliation_state"]

        app = SimpleNamespace(
            _state_store=StateStore(),
            _initialize_runtime_services=lambda state: calls.append(("initialize", state)),
        )

        original_build_application = link_existing_etc_batches.build_application
        original_default_data_dir = link_existing_etc_batches.default_data_dir
        try:
            link_existing_etc_batches.default_data_dir = lambda: default_dir
            link_existing_etc_batches.build_application = lambda *, data_dir=None, bootstrap_mode=None: calls.append(
                (data_dir, bootstrap_mode)
            ) or app

            result = link_existing_etc_batches._build_full_snapshot_application(None)
        finally:
            link_existing_etc_batches.build_application = original_build_application
            link_existing_etc_batches.default_data_dir = original_default_data_dir

        self.assertIs(result, app)
        self.assertEqual(calls, [(default_dir, "lightweight"), ("initialize", partial_state)])

    def test_dry_run_reports_ready_from_existing_submission_batch_without_scanning_all_invoices(self) -> None:
        submission_batch = SimpleNamespace(
            id="etc_batch_0034",
            etc_batch_id="ETC-OA-20260215-154900",
            invoice_ids=["etc-inv-1", "etc-inv-2"],
        )
        app = SimpleNamespace(
            _etc_service=_EtcService(
                submission_batch=submission_batch,
                invoices=[
                    SimpleNamespace(id="etc-inv-1", total_amount=Decimal("23.50")),
                    SimpleNamespace(id="etc-inv-2", total_amount=Decimal("21.52")),
                ],
            ),
            _workbench_pair_relation_service=_RelationService(
                {
                    "case_id": "CASE-HIST-MIGRATION",
                    "row_ids": ["oa-hist", "txn-hist"],
                    "amount_check": {"external_etc_batch_id": "ETC-OA-20260215-154900"},
                }
            ),
        )

        payload = _dry_run_spec(
            app,
            HistoricalEtcBusinessBatchMigrationSpec(
                label="2026年2月 ETC",
                business_batch_id="etc_business_batch_hist_20260215_154900",
                task_id="ETC-RECON-HIST-20260215-154900",
                submission_batch_id="etc_batch_0034",
                external_batch_id="ETC-OA-20260215-154900",
                reported_amount=Decimal("1549.00"),
                relation_case_id="CASE-HIST-MIGRATION",
                oa_row_id="oa-hist",
                scope_month="2026-02",
            ),
        )

        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["invoice_count"], 2)
        self.assertEqual(payload["invoice_total"], "45.02")
        self.assertEqual(payload["amount_delta"], "1503.98")
        self.assertEqual(payload["active_relation_found"], True)
        self.assertEqual(payload["existing_business_batch_found"], False)

    def test_historical_migration_refresh_is_noop_before_scope_invalidation(self) -> None:
        calls: list[tuple[str, object]] = []
        app = SimpleNamespace(
            _execute_derived_data_lifecycle_event=lambda event, **kwargs: calls.append(("lifecycle", (event, kwargs))),
            _schedule_or_run_workbench_auto_matching_for_scopes=lambda months, **kwargs: calls.append(("matching", (months, kwargs))),
            _persist_state=lambda: calls.append(("persist", {})),
        )

        _refresh_after_historical_migration(app, ["2026-03", "bad", "2026-03"], "migration:test")

        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
