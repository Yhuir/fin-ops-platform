from __future__ import annotations

import unittest
from contextlib import contextmanager
from copy import deepcopy

from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.manual_invoice_entry_service import ManualInvoiceEntryService
from fin_ops_platform.services.workbench_invoice_supplement_service import (
    ManualInvoiceSupplementCommand,
    WorkbenchInvoiceSupplementError,
    WorkbenchInvoiceSupplementService,
)


class _Recognizer:
    def recognize_uploaded_invoice(self, *, file_name: str, content: bytes) -> dict[str, str]:
        del file_name, content
        return {}


class _Connection:
    def __init__(self) -> None:
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield object()


class _RelationRepository:
    def __init__(self, existing: dict | None) -> None:
        self.existing = existing

    def load_active_workbench_pair_relation_by_case_id(self, case_id: str):
        return self.existing if self.existing and self.existing["case_id"] == case_id else None


class _RelationCommandService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict] = []
        self.runtime_state = {"before": True}
        self.restores: list[dict] = []

    def runtime_snapshot(self):
        return deepcopy(self.runtime_state)

    def restore_runtime_snapshot(self, snapshot):
        self.restores.append(deepcopy(snapshot))
        self.runtime_state = deepcopy(snapshot)

    def confirm_relation(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return {
            "changed_case_ids": [kwargs["case_id"]],
            "relation": {"case_id": kwargs["case_id"], "row_ids": kwargs["row_ids"]},
        }


def _invoice_payload(invoice_number: str, total: str, net: str, tax: str) -> dict[str, str]:
    return {
        "invoice_direction": "input",
        "invoice_nature": "blue",
        "seller_name": "云南供应商有限公司",
        "seller_tax_no": "915300000000000001",
        "buyer_name": "云南溯源科技有限公司",
        "buyer_tax_no": "915300007194052520",
        "invoice_number": invoice_number,
        "invoice_code": "",
        "invoice_date": "2026-08-18",
        "net_amount": net,
        "tax_rate": "10",
        "tax_amount": tax,
        "total_with_tax": total,
    }


class WorkbenchInvoiceSupplementServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.imports = ImportNormalizationService()
        self.files = FileImportService(self.imports)
        preview = ManualInvoiceEntryService(
            file_import_service=self.files,
            document_recognizer=_Recognizer(),
        ).preview_batch(
            payloads=[
                _invoice_payload("26117000001052654674", "350.00", "318.18", "31.82"),
                _invoice_payload("26117000001052654675", "55.00", "50.00", "5.00"),
            ],
            imported_by="finance-user",
        )
        self.session_id = preview.session.id
        self.file_ids = tuple(preview.file_ids)
        self.import_snapshot = deepcopy(self.imports.snapshot())
        self.file_snapshot = deepcopy(self.files.snapshot())
        self.import_restore_count = 0
        self.connection = _Connection()
        self.relation_repository = _RelationRepository({
            "case_id": "CASE-405",
            "row_ids": ["oa-405", "bank-405"],
            "row_types": ["oa", "bank"],
            "relation_mode": "manual_confirmed",
            "month_scope": "2026-01",
            "special_metadata": {},
            "amount_check": {},
            "note": "existing relation",
        })
        self.relation_commands = _RelationCommandService()
        self.target_exists = True
        self.persisted: list[tuple[dict, dict]] = []

    def _service(self) -> WorkbenchInvoiceSupplementService:
        return WorkbenchInvoiceSupplementService(
            connection=self.connection,
            file_import_service=self.files,
            relation_repository_factory=lambda _transaction: self.relation_repository,
            relation_command_service_factory=lambda _repository: self.relation_commands,
            target_exists=lambda _oa_row_id, _expense_item_id: self.target_exists,
            next_case_id=lambda: "CASE-NEW",
            persist_import_delta=lambda _transaction, imports, files: self.persisted.append((imports, files)),
            restore_import_runtime=self._restore_import_runtime,
        )

    def _restore_import_runtime(self) -> None:
        self.import_restore_count += 1
        self.imports = ImportNormalizationService.from_snapshot(deepcopy(self.import_snapshot))
        self.files = FileImportService.from_snapshot(self.imports, deepcopy(self.file_snapshot))

    def _command(self, *, file_ids: tuple[str, ...] | None = None) -> ManualInvoiceSupplementCommand:
        return ManualInvoiceSupplementCommand(
            session_id=self.session_id,
            file_ids=file_ids or self.file_ids,
            oa_row_id="oa-405",
            expense_item_id="oa-405:item:1",
            case_id="CASE-405",
            actor_id="finance-user",
            request_id="request-1",
        )

    def test_confirms_whole_batch_and_extends_relation_in_one_transaction(self) -> None:
        result = self._service().attach_manual_invoices(self._command())

        invoices = self.imports.list_invoices()
        self.assertEqual(len(invoices), 2)
        self.assertEqual(result["invoice_row_ids"], [invoice.id for invoice in invoices])
        self.assertEqual(
            [row["normalized"]["digital_invoice_no"] for row in result["invoice_evidence_rows"]],
            ["26117000001052654674", "26117000001052654675"],
        )
        self.assertEqual(result["invoice_evidence_rows"][0]["normalized"]["seller_name"], "云南供应商有限公司")
        self.assertEqual(self.connection.transaction_count, 1)
        self.assertEqual(len(self.persisted), 1)
        self.assertEqual(self.relation_commands.restores, [])
        self.assertEqual(self.import_restore_count, 0)
        for invoice in invoices:
            self.assertTrue(any(
                link.get("source_type") == "oa_expense_item_invoice"
                and link.get("source_expense_item_id") == "oa-405:item:1"
                for link in invoice.source_links
            ))
        relation_call = self.relation_commands.calls[0]
        self.assertEqual(relation_call["row_ids"][:2], ["oa-405", "bank-405"])
        self.assertEqual(relation_call["row_ids"][2:], result["invoice_row_ids"])
        self.assertTrue(relation_call["replace_existing"])

    def test_relation_failure_rolls_back_import_runtime_state(self) -> None:
        self.relation_commands.error = RuntimeError("relation failed")

        with self.assertRaisesRegex(RuntimeError, "relation failed"):
            self._service().attach_manual_invoices(self._command())

        self.assertEqual(self.imports.list_invoices(), [])
        self.assertEqual(self.files.get_session(self.session_id).status, "preview_ready")
        self.assertEqual(self.import_restore_count, 1)
        self.assertEqual(self.relation_commands.restores, [{"before": True}])

    def test_rejects_partial_batch_before_mutation(self) -> None:
        with self.assertRaisesRegex(WorkbenchInvoiceSupplementError, "必须一次提交本批次全部发票"):
            self._service().attach_manual_invoices(self._command(file_ids=self.file_ids[:1]))

        self.assertEqual(self.connection.transaction_count, 0)
        self.assertEqual(self.imports.list_invoices(), [])

    def test_rejects_stale_or_mismatched_oa_expense_item_before_mutation(self) -> None:
        self.target_exists = False

        with self.assertRaisesRegex(WorkbenchInvoiceSupplementError, "不存在或已变化"):
            self._service().attach_manual_invoices(self._command())

        self.assertEqual(self.connection.transaction_count, 0)
        self.assertEqual(self.imports.list_invoices(), [])


if __name__ == "__main__":
    unittest.main()
