from __future__ import annotations

import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_manual_import_service import OAManualImportService


def oa_record(
    row_id: str,
    *,
    month: str = "2025-12",
    applicant: str = "陈雄兵",
    project_name: str = "大理卷烟厂动力车间中水处理系统升级改造项目",
    apply_type: str = "日常报销",
    status: str = "已完成",
    amount: str = "135.00",
    reason: str = "去大理检修中水系统餐费",
    invoices: list[dict[str, str]] | None = None,
    attachment_file_count: int = 2,
) -> OAApplicationRecord:
    attachment_invoices = invoices if invoices is not None else [{"invoice_no": "001", "attachment_name": "invoice.pdf"}]
    return OAApplicationRecord(
        id=row_id,
        month=month,
        section="unpaired",
        case_id=None,
        applicant=applicant,
        project_name=project_name,
        apply_type=apply_type,
        amount=amount,
        counterparty_name="",
        reason=reason,
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        detail_fields={
            "OA单号": row_id.removeprefix("oa-exp-").removeprefix("oa-pay-"),
            "申请日期": f"{month}-23",
            "流程状态": status,
        },
        attachment_invoices=attachment_invoices,
        attachment_file_count=attachment_file_count,
        expense_items=[
            {
                "row_index": "0",
                "reimbursement_date": f"{month}-23",
                "amount": amount,
                "expense_content": reason,
                "project_name": project_name,
                "attachment_file_count": str(attachment_file_count),
                "attachment_invoices": list(attachment_invoices),
            }
        ],
    )


class MemoryManualImportStore:
    def __init__(self) -> None:
        self.payload: dict[str, object] = {}

    def load_manual_oa_imports(self) -> dict[str, object]:
        return dict(self.payload)

    def add_manual_oa_imports(
        self,
        row_ids: list[str],
        actor_id: str,
        audit: dict[str, object],
    ) -> dict[str, object]:
        entries = dict(self.payload.get("entries") or {})
        imported: list[str] = []
        already_imported: list[str] = []
        for row_id in row_ids:
            if row_id in entries:
                already_imported.append(row_id)
                continue
            entries[row_id] = {"row_id": row_id, "actor_id": actor_id, "audit": dict(audit)}
            imported.append(row_id)
        self.payload["entries"] = entries
        self.payload["row_ids"] = sorted(entries)
        return {"imported": imported, "already_imported": already_imported, "entries": entries}

    def remove_manual_oa_import(self, row_id: str, actor_id: str) -> bool:
        entries = dict(self.payload.get("entries") or {})
        removed = entries.pop(row_id, None) is not None
        self.payload["entries"] = entries
        self.payload["row_ids"] = sorted(entries)
        return removed


class RecordingOAAdapter:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records_by_id = {record.id: record for record in records}
        self.search_calls: list[dict[str, object]] = []

    def search_application_records(self, **kwargs):
        self.search_calls.append(dict(kwargs))
        records = list(self.records_by_id.values())
        form_types = set(kwargs.get("form_types") or [])
        statuses = set(kwargs.get("statuses") or [])
        if form_types:
            records = [record for record in records if self._form_type(record) in form_types]
        if statuses:
            records = [record for record in records if self._status(record) in statuses]
        return records

    def search_application_record_rows(self, **kwargs):
        records = self.search_application_records(**kwargs)
        query = str(kwargs.get("q") or "").lower()
        records = [r for r in records if query in f"{r.id} {r.applicant} {r.project_name} {r.reason}".lower()]
        records = [r for r in records if (not kwargs.get("date_from") or r.detail_fields["申请日期"] >= kwargs["date_from"])
                   and (not kwargs.get("date_to") or r.detail_fields["申请日期"] <= kwargs["date_to"])]
        start = kwargs["page"] * kwargs["page_size"]
        presentation = OAManualImportService(state_store=MemoryManualImportStore(), oa_adapter=self)
        return {"rows": presentation.serialize_import_result_rows(records[start:start + kwargs["page_size"]],
                    imported_entries=kwargs.get("imported_entries", {})), "total": len(records),
                "page": kwargs["page"], "page_size": kwargs["page_size"]}

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        return [self.records_by_id[row_id] for row_id in row_ids if row_id in self.records_by_id]

    @staticmethod
    def _form_type(record: OAApplicationRecord) -> str:
        return "payment_request" if record.apply_type == "支付申请" else "expense_claim"

    @staticmethod
    def _status(record: OAApplicationRecord) -> str:
        return "completed" if record.detail_fields.get("流程状态") == "已完成" else "in_progress"


class RecordingWorkbenchQueryService:
    def __init__(self) -> None:
        self.synced_row_ids: list[list[str]] = []
        self.synced_records: list[OAApplicationRecord] = []

    def sync_oa_row_ids(self, row_ids: list[str]) -> None:
        self.synced_row_ids.append(list(row_ids))


class FastSearchOAAdapter(RecordingOAAdapter):
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        super().__init__(records)
        self.fast_search_calls: list[dict[str, object]] = []

    def search_application_record_rows(self, **kwargs):
        self.fast_search_calls.append(dict(kwargs))
        return {
            "rows": [
                {
                    "row_id": "oa-exp-1981",
                    "oa_no": "1981",
                    "applicant": "陈雄兵",
                    "application_date": "2026-01-15",
                    "form_type": "expense_claim",
                    "form_type_label": "日常报销",
                    "status": "completed",
                    "status_label": "已完成",
                    "project_name": "大理项目",
                    "reason": "餐费",
                    "amount": "135.00",
                    "attachment_file_count": 1,
                    "importable_invoice_count": 0,
                    "unrecognized_attachment_count": 1,
                    "import_status": "not_imported",
                    "imported_at": None,
                    "can_import": True,
                    "disabled_reason": "",
                    "items": [],
                }
            ],
            "total": 1,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
        }


class OAManualImportServiceTests(unittest.TestCase):
    def test_search_uses_adapter_fast_paged_rows_when_available(self) -> None:
        store = MemoryManualImportStore()
        adapter = FastSearchOAAdapter([oa_record("oa-exp-1981")])
        service = OAManualImportService(
            state_store=store,
            oa_adapter=adapter,
        )

        payload = service.search(
            q="陈雄兵",
            form_types=["expense_claim"],
            statuses=["completed"],
            date_from="2026-01-01",
            date_to="2026-01-31",
            page=2,
            page_size=50,
        )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["rows"][0]["row_id"], "oa-exp-1981")
        self.assertEqual(adapter.search_calls, [])
        self.assertEqual(
            adapter.fast_search_calls,
            [
                {
                    "q": "陈雄兵",
                    "form_types": ["expense_claim"],
                    "statuses": ["completed"],
                    "date_from": "2026-01-01",
                    "date_to": "2026-01-31",
                    "page": 2,
                    "page_size": 50,
                }
            ],
        )

    def test_search_returns_non_completed_rows_but_marks_them_not_importable(self) -> None:
        store = MemoryManualImportStore()
        adapter = RecordingOAAdapter(
            [
                oa_record("oa-exp-1981", status="已完成"),
                oa_record("oa-pay-2048", apply_type="支付申请", status="进行中", amount="88050", applicant="樊祖芳"),
            ]
        )
        service = OAManualImportService(state_store=store, oa_adapter=adapter)

        payload = service.search(q="樊祖芳", form_types=["payment_request"], statuses=["in_progress"])

        self.assertEqual(payload["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["row_id"], "oa-pay-2048")
        self.assertEqual(row["status"], "in_progress")
        self.assertFalse(row["can_import"])
        self.assertEqual(row["disabled_reason"], "流程未完成")
        self.assertEqual(adapter.search_calls[0]["statuses"], ["in_progress"])

    def test_completed_search_row_includes_attachment_counts_and_import_status(self) -> None:
        store = MemoryManualImportStore()
        store.add_manual_oa_imports(["oa-exp-1981"], "tester", {})
        service = OAManualImportService(
            state_store=store,
            oa_adapter=RecordingOAAdapter([oa_record("oa-exp-1981", invoices=[])]),
        )

        payload = {"rows": service.serialize_import_result_rows([oa_record("oa-exp-1981", invoices=[])],
            imported_entries=store.load_manual_oa_imports()["entries"])}

        row = payload["rows"][0]
        self.assertTrue(row["can_import"])
        self.assertEqual(row["import_status"], "imported")
        self.assertEqual(row["attachment_file_count"], 2)
        self.assertEqual(row["importable_invoice_count"], 0)
        self.assertEqual(row["unrecognized_attachment_count"], 2)
        self.assertEqual(row["items"][0]["importable_invoice_count"], 0)

    def test_remove_manual_import_removes_marker_only(self) -> None:
        store = MemoryManualImportStore()
        store.add_manual_oa_imports(["oa-exp-1981"], "tester", {})
        adapter = RecordingOAAdapter([oa_record("oa-exp-1981")])
        service = OAManualImportService(state_store=store, oa_adapter=adapter)

        result = service.remove_manual_import("oa-exp-1981", actor_id="tester")

        self.assertEqual(result, {"removed": True, "row_id": "oa-exp-1981"})
        self.assertEqual(store.load_manual_oa_imports()["row_ids"], [])
        self.assertIn("oa-exp-1981", adapter.records_by_id)


if __name__ == "__main__":
    unittest.main()
