import tempfile
import unittest
from pathlib import Path

from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
)


class SettingsDataResetServiceTests(unittest.TestCase):
    def test_reset_bank_transactions_keeps_invoices_and_protects_form_data_db(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice_preview = app._import_service.preview_import(
                batch_type=BatchType.INPUT_INVOICE,
                source_name="input-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "invoice_code": "033001",
                        "invoice_no": "9002",
                        "counterparty_name": "Vendor A",
                        "amount": "120.00",
                        "tax_amount": "7.20",
                        "total_with_tax": "127.20",
                        "invoice_date": "2026-03-24",
                        "invoice_status_from_source": "valid",
                    }
                ],
            )
            bank_preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "account_no": "62229999",
                        "trade_time": "2026-03-24 00:00:00",
                        "counterparty_name": "Vendor A",
                        "debit_amount": "50.00",
                        "credit_amount": "",
                        "bank_serial_no": "SERIAL-NEW-001",
                        "summary": "purchase",
                    }
                ],
            )
            app._import_service.confirm_import(invoice_preview.id)
            app._import_service.confirm_import(bank_preview.id)
            app._matching_service.run(triggered_by="tester")
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-RESET-001",
                row_ids=["bk-reset-001", "inv-reset-001"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._workbench_override_service.mark_exception(
                row={"id": "bk-reset-001", "type": "bank"},
                exception_code="manual_review",
            )

            result = app._settings_data_reset_service.execute(RESET_BANK_TRANSACTIONS_ACTION)
            persisted = app._state_store.load()

        self.assertIn("form_data_db.form_data", result.protected_targets)
        self.assertEqual(result.deleted_counts["bank_transactions"], 1)
        self.assertEqual(result.deleted_counts["invoices"], 0)
        imports_payload = persisted["imports"]
        self.assertEqual(len(imports_payload["transactions"]), 0)
        self.assertEqual(len(imports_payload["invoices"]), 1)
        self.assertEqual(persisted["matching"], {})
        self.assertEqual(persisted["workbench_pair_relations"], {})
        self.assertEqual(persisted["workbench_overrides"], {})

    def test_reset_invoices_clears_tax_certified_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice_preview = app._import_service.preview_import(
                batch_type=BatchType.OUTPUT_INVOICE,
                source_name="output-demo.json",
                imported_by="tester",
                rows=[
                    {
                        "invoice_code": "033001",
                        "invoice_no": "9003",
                        "counterparty_name": "Customer A",
                        "amount": "200.00",
                        "tax_amount": "26.00",
                        "total_with_tax": "226.00",
                        "invoice_date": "2026-03-24",
                        "invoice_status_from_source": "valid",
                    }
                ],
            )
            app._import_service.confirm_import(invoice_preview.id)
            preview_session = app._tax_certified_import_service.preview_files(
                imported_by="tester",
                uploads=[],
            )
            preview_session.files = []
            app._tax_certified_import_service._sessions[preview_session.id] = preview_session
            app._tax_certified_import_service._records["manual-cert-001"] = {
                "id": "manual-cert-001"
            }
            app._state_store.save_tax_certified_imports(app._tax_certified_import_service.snapshot())

            result = app._settings_data_reset_service.execute(RESET_INVOICES_ACTION)
            persisted = app._state_store.load()
            tax_persisted = app._state_store.load_tax_certified_imports()

        self.assertIn("form_data_db.form_data", result.protected_targets)
        self.assertEqual(result.deleted_counts["invoices"], 1)
        self.assertEqual(len(persisted["imports"]["invoices"]), 0)
        self.assertEqual(tax_persisted, {})

    def test_reset_oa_and_rebuild_preserves_pure_bank_invoice_pair_relation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-MANUAL-BANK-INVOICE",
                row_ids=["txn-imported-1994", "inv-imported-1994"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._state_store.save_workbench_pair_relations(app._workbench_pair_relation_service.snapshot())

            result = app._settings_data_reset_service.execute(RESET_OA_AND_REBUILD_ACTION)
            persisted = app._state_store.load()

        self.assertEqual(result.deleted_counts["workbench_oa_pair_relations"], 0)
        self.assertEqual(result.deleted_counts["workbench_preserved_non_oa_pair_relations"], 1)
        self.assertNotIn("workbench_read_models", result.deleted_counts)
        self.assertIn("CASE-MANUAL-BANK-INVOICE", persisted["workbench_pair_relations"]["pair_relations"])

    def test_reset_oa_and_rebuild_removes_pair_relation_containing_expense_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-OA-EXPENSE",
                row_ids=["txn-imported-1994", "oa-exp-1994"],
                row_types=["bank", "oa"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._state_store.save_workbench_pair_relations(app._workbench_pair_relation_service.snapshot())

            result = app._settings_data_reset_service.execute(RESET_OA_AND_REBUILD_ACTION)
            persisted = app._state_store.load()

        self.assertEqual(result.deleted_counts["workbench_oa_pair_relations"], 1)
        self.assertEqual(result.deleted_counts["workbench_preserved_non_oa_pair_relations"], 0)
        self.assertNotIn("CASE-OA-EXPENSE", persisted["workbench_pair_relations"]["pair_relations"])

    def test_reset_oa_and_rebuild_removes_pair_relation_containing_attachment_invoice_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-OA-ATTACHMENT-INVOICE",
                row_ids=["txn-imported-1994", "oa-att-inv-oa-exp-1994-01"],
                row_types=["bank", "invoice"],
                relation_mode="manual_confirmed",
                created_by="tester",
            )
            app._state_store.save_workbench_pair_relations(app._workbench_pair_relation_service.snapshot())

            result = app._settings_data_reset_service.execute(RESET_OA_AND_REBUILD_ACTION)
            persisted = app._state_store.load()

        self.assertEqual(result.deleted_counts["workbench_oa_pair_relations"], 1)
        self.assertEqual(result.deleted_counts["workbench_preserved_non_oa_pair_relations"], 0)
        self.assertNotIn("CASE-OA-ATTACHMENT-INVOICE", persisted["workbench_pair_relations"]["pair_relations"])

if __name__ == "__main__":
    unittest.main()
