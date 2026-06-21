from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.historical_etc_business_batch_migration_service import (
    HistoricalEtcBusinessBatchMigrationService,
    HistoricalEtcBusinessBatchMigrationSpec,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class HistoricalEtcBusinessBatchMigrationServiceTests(unittest.TestCase):
    def test_migrates_existing_submission_batch_to_business_model_and_syncs_metadata(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_historical_invoices_from_records(
                records=[
                    {
                        "invoice_number": "ETC-HIST-001",
                        "issue_date": "2026-01-04",
                        "passage_start_date": "2026-01-04",
                        "passage_end_date": "2026-01-04",
                        "plate_number": "云ADA0381",
                        "seller_name": "云南昆玉高速公路开发有限公司",
                        "seller_tax_no": "91530000ETC001",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052520",
                        "amount_without_tax": "22.80",
                        "tax_amount": "0.70",
                        "total_amount": "23.50",
                    },
                    {
                        "invoice_number": "ETC-HIST-002",
                        "issue_date": "2026-01-05",
                        "passage_start_date": "2026-01-05",
                        "passage_end_date": "2026-01-05",
                        "plate_number": "云ADA0381",
                        "seller_name": "云南昆玉高速公路开发有限公司",
                        "seller_tax_no": "91530000ETC001",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052520",
                        "amount_without_tax": "20.88",
                        "tax_amount": "0.64",
                        "total_amount": "21.52",
                    },
                ],
                source_name="historical-migration-test",
            )
            submitted_batch = app._etc_service.create_historical_submitted_batch(
                case_id="CASE-HIST-MIGRATION",
                external_batch_id="ETC-OA-20260215-154900",
                invoice_numbers=["ETC-HIST-001", "ETC-HIST-002"],
                linked_oa_row_id="oa-hist-migration",
                oa_amount=Decimal("1549.00"),
                note="旧批次已和 OA-银行关系配对",
            )
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-HIST-MIGRATION",
                row_ids=["oa-hist-migration", "txn-hist-migration"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-02",
                amount_check={
                    "status": "mismatch",
                    "direction": "expense",
                    "oa_amount": "1549.00",
                    "bank_amount": "1549.00",
                    "invoice_total": "45.02",
                    "amount_delta": "1503.98",
                    "external_etc_batch_id": "ETC-OA-20260215-154900",
                },
            )
            refreshes: list[tuple[list[str], str]] = []
            invalidations: list[list[str]] = []
            persisted_relations: list[list[str]] = []
            original_update_relation_metadata = app._workbench_pair_relation_service.update_relation_metadata_for_case_id

            def forbidden_direct_relation_metadata_update(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("historical ETC migration must update relation metadata via command service.")

            app._workbench_pair_relation_service.update_relation_metadata_for_case_id = forbidden_direct_relation_metadata_update

            class RecordingRelationCommandService:
                def __init__(self) -> None:
                    self.metadata_calls: list[dict[str, object]] = []

                def get_active_relation_by_case_id(self, case_id: str) -> dict[str, object] | None:
                    return app._workbench_pair_relation_service.get_active_relation_by_case_id(case_id)

                def update_relation_metadata_for_case_id(self, **kwargs: object) -> dict[str, object]:
                    self.metadata_calls.append(dict(kwargs))
                    pair_kwargs = {
                        key: value
                        for key, value in kwargs.items()
                        if key not in {"actor_id", "history_operation_type"}
                    }
                    pair_kwargs["updated_by"] = kwargs["actor_id"]
                    pair_kwargs["operation_type"] = kwargs["history_operation_type"]
                    relation, history = original_update_relation_metadata(**pair_kwargs)
                    return {
                        "status": "updated",
                        "relation": relation,
                        "history": history,
                        "changed_case_ids": [str(kwargs["case_id"])],
                        "affected_months": ["2026-02"],
                        "read_model_status": "fresh",
                        "read_model_stale_reasons": [],
                        "read_model_scope_keys": ["2026-02"],
                        "refresh_enqueued": False,
                    }

            relation_command_service = RecordingRelationCommandService()
            service = HistoricalEtcBusinessBatchMigrationService(
                etc_service=app._etc_service,
                relation_command_service=relation_command_service,
                link_etc_invoices_to_existing_invoices=app._link_etc_invoices_to_existing_invoices,
                refresh_after_etc_invoice_link=lambda months, reason: refreshes.append((list(months), reason)),
                persist_pair_relations=lambda case_ids: persisted_relations.append(list(case_ids)),
                invalidate_workbench_scopes=lambda scopes: invalidations.append(list(scopes)),
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )

            result = service.migrate(
                HistoricalEtcBusinessBatchMigrationSpec(
                    label="2026年2月 ETC",
                    business_batch_id="etc_business_batch_hist_20260215_154900",
                    task_id="ETC-RECON-HIST-20260215-154900",
                    submission_batch_id=submitted_batch.id,
                    external_batch_id="ETC-OA-20260215-154900",
                    reported_amount=Decimal("1549.00"),
                    relation_case_id="CASE-HIST-MIGRATION",
                    oa_row_id="oa-hist-migration",
                    scope_month="2026-02",
                    gap_reason="旧 OA 金额包含骑行费，ETC 发票保持旧事实源金额。",
                )
            )
            repeat = service.migrate(
                HistoricalEtcBusinessBatchMigrationSpec(
                    label="2026年2月 ETC",
                    business_batch_id="etc_business_batch_hist_20260215_154900",
                    task_id="ETC-RECON-HIST-20260215-154900",
                    submission_batch_id=submitted_batch.id,
                    external_batch_id="ETC-OA-20260215-154900",
                    reported_amount=Decimal("1549.00"),
                    relation_case_id="CASE-HIST-MIGRATION",
                    oa_row_id="oa-hist-migration",
                    scope_month="2026-02",
                    gap_reason="旧 OA 金额包含骑行费，ETC 发票保持旧事实源金额。",
                )
            )
            business_batches = app._etc_service.list_business_batches(status="manually_marked_submitted")
            business_batch = app._etc_service.get_business_batch("etc_business_batch_hist_20260215_154900")
            invoices = app._etc_service.list_invoices_by_ids(list(business_batch.invoice_ids))
            canonical_invoices = {invoice.invoice_no: invoice for invoice in app._import_service.list_invoices()}
            relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-HIST-MIGRATION")

        self.assertEqual(result.status, "ok")
        self.assertEqual(repeat.status, "ok")
        self.assertEqual(result.business_batch_id, "etc_business_batch_hist_20260215_154900")
        self.assertEqual(result.submission_batch_id, submitted_batch.id)
        self.assertEqual(result.invoice_count, 2)
        self.assertEqual(result.invoice_total, Decimal("45.02"))
        self.assertEqual(result.reported_amount, Decimal("1549.00"))
        self.assertEqual(result.amount_delta, Decimal("1503.98"))
        self.assertEqual(len(business_batches), 1)
        self.assertEqual(business_batch.submission_batch_id, submitted_batch.id)
        self.assertEqual(business_batch.external_etc_batch_id, "ETC-OA-20260215-154900")
        self.assertEqual({invoice.business_batch_id for invoice in invoices}, {"etc_business_batch_hist_20260215_154900"})
        self.assertEqual(canonical_invoices, {})
        self.assertEqual(refreshes[-1], (["2026-01", "2026-02"], "historical_etc_business_batch_migration:ETC-OA-20260215-154900"))
        self.assertEqual(invalidations[-1], ["all", "2026-01", "2026-02"])
        self.assertEqual(persisted_relations[-1], ["CASE-HIST-MIGRATION"])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["amount_check"]["business_batch_id"], "etc_business_batch_hist_20260215_154900")
        self.assertEqual(relation["amount_check"]["external_etc_batch_id"], "ETC-OA-20260215-154900")
        self.assertEqual(relation_command_service.metadata_calls[-1]["case_id"], "CASE-HIST-MIGRATION")
        self.assertEqual(
            relation_command_service.metadata_calls[-1]["history_operation_type"],
            "historical_etc_business_batch_migration",
        )

    def test_migration_requires_relation_command_service_before_business_batch_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_historical_invoices_from_records(
                records=[
                    {
                        "invoice_number": "ETC-HIST-NO-COMMAND",
                        "issue_date": "2026-01-04",
                        "passage_start_date": "2026-01-04",
                        "passage_end_date": "2026-01-04",
                        "plate_number": "云ADA0381",
                        "seller_name": "云南昆玉高速公路开发有限公司",
                        "seller_tax_no": "91530000ETC001",
                        "buyer_name": "云南溯源科技有限公司",
                        "buyer_tax_no": "915300007194052520",
                        "amount_without_tax": "22.80",
                        "tax_amount": "0.70",
                        "total_amount": "23.50",
                    },
                ],
                source_name="historical-migration-no-command-test",
            )
            submitted_batch = app._etc_service.create_historical_submitted_batch(
                case_id="CASE-HIST-NO-COMMAND",
                external_batch_id="ETC-OA-NO-COMMAND",
                invoice_numbers=["ETC-HIST-NO-COMMAND"],
                linked_oa_row_id="oa-hist-no-command",
                oa_amount=Decimal("23.50"),
                note="旧批次已和 OA-银行关系配对",
            )
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-HIST-NO-COMMAND",
                row_ids=["oa-hist-no-command", "txn-hist-no-command"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-02",
                amount_check={
                    "status": "matched",
                    "oa_amount": "23.50",
                    "bank_amount": "23.50",
                    "invoice_total": "23.50",
                    "amount_delta": "0.00",
                    "external_etc_batch_id": "ETC-OA-NO-COMMAND",
                },
            )

            def forbidden_direct_relation_metadata_update(*_args: object, **_kwargs: object) -> None:
                raise AssertionError("historical ETC migration must fail fast instead of using pair service fallback.")

            app._workbench_pair_relation_service.update_relation_metadata_for_case_id = forbidden_direct_relation_metadata_update
            service = HistoricalEtcBusinessBatchMigrationService(
                etc_service=app._etc_service,
                link_etc_invoices_to_existing_invoices=app._link_etc_invoices_to_existing_invoices,
                refresh_after_etc_invoice_link=lambda months, reason: None,
                persist_pair_relations=lambda case_ids: app._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                invalidate_workbench_scopes=app._invalidate_workbench_read_model_scopes,
                persist_etc_state=lambda: app._state_store.save_etc_state(app._etc_service.snapshot()),
            )

            with self.assertRaises(WorkbenchRelationCommandError) as context:
                service.migrate(
                    HistoricalEtcBusinessBatchMigrationSpec(
                        label="缺少 command 历史 ETC",
                        business_batch_id="etc_business_batch_hist_no_command",
                        task_id="ETC-RECON-HIST-NO-COMMAND",
                        submission_batch_id=submitted_batch.id,
                        external_batch_id="ETC-OA-NO-COMMAND",
                        reported_amount=Decimal("23.50"),
                        relation_case_id="CASE-HIST-NO-COMMAND",
                        oa_row_id="oa-hist-no-command",
                        scope_month="2026-02",
                    )
                )
            business_batches = app._etc_service.list_business_batches()

        self.assertEqual(context.exception.error_code, "workbench_relation_command_unavailable")
        self.assertEqual(business_batches, [])


if __name__ == "__main__":
    unittest.main()
