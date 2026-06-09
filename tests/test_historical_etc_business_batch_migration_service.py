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


class HistoricalEtcBusinessBatchMigrationServiceTests(unittest.TestCase):
    def test_migrates_existing_submission_batch_to_business_model_and_syncs_metadata(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir:
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
            service = HistoricalEtcBusinessBatchMigrationService(
                etc_service=app._etc_service,
                pair_relation_service=app._workbench_pair_relation_service,
                sync_etc_invoices_to_canonical_invoices=app._sync_etc_invoices_to_canonical_invoices,
                refresh_after_etc_invoice_sync=lambda months, reason: refreshes.append((list(months), reason)),
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
        self.assertEqual(canonical_invoices["ETC-HIST-001"].workbench_visibility, "hidden_after_etc_submission")
        self.assertEqual(canonical_invoices["ETC-HIST-001"].etc_submission_batch_id, submitted_batch.id)
        self.assertEqual(refreshes[-1], (["2026-01", "2026-02"], "historical_etc_business_batch_migration:ETC-OA-20260215-154900"))
        self.assertEqual(invalidations[-1], ["all", "2026-01", "2026-02"])
        self.assertEqual(persisted_relations[-1], ["CASE-HIST-MIGRATION"])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["amount_check"]["business_batch_id"], "etc_business_batch_hist_20260215_154900")
        self.assertEqual(relation["amount_check"]["external_etc_batch_id"], "ETC-OA-20260215-154900")


if __name__ == "__main__":
    unittest.main()
