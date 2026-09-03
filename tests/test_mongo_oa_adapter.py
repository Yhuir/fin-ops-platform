import unittest
from datetime import datetime
from unittest.mock import patch

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentOCRRuntimeError
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from pymongo.errors import ServerSelectionTimeoutError


class MemoryAttachmentInvoiceCache:
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, object]] = {}

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        entry = self.entries.get(cache_key)
        return dict(entry) if isinstance(entry, dict) else None

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        self.entries[cache_key] = dict(payload)


class StubMongoOAAdapter(MongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        settings: MongoOASettings | None = None,
        attachment_invoice_cache: MemoryAttachmentInvoiceCache | None = None,
    ) -> None:
        super().__init__(
            settings=settings or MongoOASettings(host="127.0.0.1", database="form_data_db"),
            attachment_invoice_cache=attachment_invoice_cache,
        )
        self._form_documents = form_documents
        self._project_documents = project_documents

    def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
        documents = [self._with_default_completed_status(document) for document in self._form_documents.get(str(form_id), [])]
        if month is None:
            return documents
        filtered: list[dict] = []
        for document in documents:
            data = document.get("data", {})
            application_date = str(data.get("applicationDate") or data.get("ApplicationDate") or "")
            if application_date.startswith(month):
                filtered.append(document)
        return filtered

    def _load_project_documents(self) -> list[dict]:
        return list(self._project_documents)

    def _load_form_month_documents(self, form_id: str) -> list[dict]:
        return [self._with_default_completed_status(document) for document in self._form_documents.get(str(form_id), [])]

    def _load_form_documents_by_external_ids(self, form_id: str, external_ids: set[str]) -> list[dict]:
        documents = [self._with_default_completed_status(document) for document in self._form_documents.get(str(form_id), [])]
        return [
            document
            for document in documents
            if self._document_external_id(form_id, document) in set(external_ids)
        ]

    @staticmethod
    def _with_default_completed_status(document: dict) -> dict:
        normalized = dict(document)
        data = dict(normalized.get("data", {}))
        if "status" not in data or data.get("status") in (None, ""):
            data["status"] = "已完成"
        normalized["data"] = data
        return normalized


class CountingStubMongoOAAdapter(StubMongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        settings: MongoOASettings | None = None,
    ) -> None:
        super().__init__(form_documents=form_documents, project_documents=project_documents, settings=settings)
        self.form_load_calls: list[tuple[str, str | None]] = []

    def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
        self.form_load_calls.append((str(form_id), month))
        return super()._load_form_documents(form_id, month)


class SearchSummaryStubMongoOAAdapter(CountingStubMongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        settings: MongoOASettings | None = None,
    ) -> None:
        super().__init__(form_documents=form_documents, project_documents=project_documents, settings=settings)
        self.search_document_calls: list[dict[str, object]] = []
        self.count_document_calls: list[dict[str, object]] = []

    def _search_form_documents(
        self,
        form_id: str,
        query: dict,
        *,
        projection: dict[str, int] | None = None,
        limit: int,
    ) -> list[dict]:
        self.search_document_calls.append(
            {
                "form_id": str(form_id),
                "query": dict(query),
                "projection": projection,
                "limit": limit,
            }
        )
        return [self._with_default_completed_status(document) for document in self._form_documents.get(str(form_id), [])][:limit]

    def _count_search_documents(self, query: dict) -> int:
        self.count_document_calls.append(dict(query))
        form_id = query.get("form_id")
        if form_id is None:
            for clause in list(query.get("$and") or []):
                if isinstance(clause, dict) and clause.get("form_id") is not None:
                    form_id = clause.get("form_id")
                    break
        if isinstance(form_id, dict):
            candidates = sorted({str(value) for value in list(form_id.get("$in") or [])})
            return sum(len(self._form_documents.get(candidate, [])) for candidate in candidates)
        return len(self._form_documents.get(str(form_id), []))

    def _parse_attachment_evidence_pool(self, files: list[dict[str, object]], *, month: str | None = None) -> dict[str, list[dict[str, str]]]:
        raise AssertionError("search summary must not parse or schedule attachment invoices")


class AttachmentStubMongoOAAdapter(StubMongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        attachment_invoice_rows: list[dict[str, str]] | dict[str, list[dict[str, str]]],
        settings: MongoOASettings | None = None,
    ) -> None:
        super().__init__(form_documents=form_documents, project_documents=project_documents, settings=settings)
        self._attachment_invoice_rows = attachment_invoice_rows

    def _parse_attachment_invoices(self, files: list[dict[str, object]], *, month: str | None = None) -> list[dict[str, str]]:
        if not files:
            return []
        if isinstance(self._attachment_invoice_rows, dict):
            rows: list[dict[str, str]] = []
            for file_entry in files:
                file_name = str(file_entry.get("fileName") or file_entry.get("name") or "")
                rows.extend(dict(row) for row in self._attachment_invoice_rows.get(file_name, []))
            return rows
        return [dict(row) for row in self._attachment_invoice_rows]

    def _parse_attachment_evidence_pool(
        self,
        files: list[dict[str, object]],
        *,
        month: str | None = None,
    ) -> dict[str, list[dict[str, str]]]:
        if not files:
            return {"evidences": [], "invoices": [], "artifacts": []}
        raw_invoices = self._parse_attachment_invoices(files, month=month)
        files_by_name = {
            self._attachment_display_name(file_entry): file_entry
            for file_entry in files
        }
        fallback_file = files[0]
        evidences: list[dict[str, str]] = []
        for invoice in raw_invoices:
            evidence = dict(invoice)
            evidence.setdefault("evidence_type", "tax_invoice")
            attachment_name = str(evidence.get("attachment_name") or evidence.get("source_attachment_name") or "")
            file_entry = files_by_name.get(attachment_name, fallback_file)
            evidences.append(self._normalize_parsed_attachment_evidence(evidence, file_entry=file_entry))
        invoices = self._dedupe_attachment_invoices(self._attachment_invoices_from_evidences(evidences))
        artifacts = [
            self._attachment_artifact_for_file(
                file_entry,
                evidences=[
                    evidence
                    for evidence in evidences
                    if evidence.get("source_attachment_key") == self._source_attachment_key(file_entry)
                ],
            )
            for file_entry in files
        ]
        return {"evidences": evidences, "invoices": invoices, "artifacts": artifacts}


def build_contextual_attachment_cache_fixture(
    adapter: MongoOAAdapter,
    file_entry: dict[str, object],
    *,
    external_id: str,
    row_index: str,
    item: dict,
    project_id: str = "oa-project-001",
    amount: str,
    reimbursement_date: str = "",
) -> tuple[str, dict[str, str]]:
    expense_item_id = adapter._expense_item_id(
        external_id=external_id,
        row_index=row_index,
        item=item,
        project_id=project_id,
        amount=amount,
        reimbursement_date=reimbursement_date,
    )
    contextual_file = adapter._attachment_files_with_source_context(
        [file_entry],
        oa_external_id=external_id,
        source_expense_row_index=row_index,
        source_expense_item_id=expense_item_id,
    )[0]
    return (
        adapter._attachment_invoice_cache_key(contextual_file),
        adapter._attachment_invoice_source_fields(contextual_file),
    )


class QueryRecordingCollection:
    def __init__(self) -> None:
        self.queries: list[dict] = []
        self.projections: list[dict | None] = []

    def find(self, query: dict, projection: dict | None = None) -> list[dict]:
        self.queries.append(query)
        self.projections.append(dict(projection) if isinstance(projection, dict) else None)
        return []


class FlakyMonthCollection:
    def __init__(self) -> None:
        self.call_count = 0

    def find(self, query: dict, projection: dict | None = None) -> list[dict]:
        self.call_count += 1
        if self.call_count == 1:
            raise ServerSelectionTimeoutError("transient mongo timeout")
        return [
            {"data": {"applicationDate": "2026-03-16", "status": "已完成"}},
            {"data": {"ApplicationDate": "2026-04-01", "status": "已完成"}, "modifiedTime": "2026-04-01T09:00:00"},
        ]


class QueryRecordingMongoOAAdapter(MongoOAAdapter):
    def __init__(self, collection: QueryRecordingCollection, *, settings: MongoOASettings | None = None) -> None:
        super().__init__(settings=settings or MongoOASettings(host="127.0.0.1", database="form_data_db"))
        self._query_collection = collection

    def _collection(self):
        return self._query_collection


class FailingMongoOAAdapter(MongoOAAdapter):
    def __init__(self, *, settings: MongoOASettings | None = None) -> None:
        super().__init__(settings=settings or MongoOASettings(host="127.0.0.1", database="form_data_db"))

    def _collection(self):
        raise ServerSelectionTimeoutError("mock mongo unavailable")


class CountingFailingMongoOAAdapter(FailingMongoOAAdapter):
    def __init__(self, *, settings: MongoOASettings | None = None) -> None:
        super().__init__(settings=settings)
        self.collection_call_count = 0

    def _collection(self):
        self.collection_call_count += 1
        return super()._collection()


class MongoOAAdapterTests(unittest.TestCase):
    def test_attachment_invoice_dedupe_keys_delegate_to_identity_policy(self) -> None:
        invoice = {
            "digital_invoice_no": "26372000000990000001",
            "invoice_code": "053002200111",
            "invoice_no": "40512344",
            "seller_name": "云南顺丰速运有限公司",
            "total_with_tax": "12.00",
        }

        self.assertEqual(
            MongoOAAdapter._attachment_invoice_dedupe_keys(invoice),
            FinancialObjectIdentityPolicy().oa_attachment_invoice_dedupe_keys(invoice),
        )

    def test_list_application_records_returns_empty_when_mongo_is_unavailable(self) -> None:
        adapter = FailingMongoOAAdapter()

        records = adapter.list_application_records("2026-03")

        self.assertEqual(records, [])

    def test_list_available_months_returns_empty_when_mongo_is_unavailable(self) -> None:
        adapter = FailingMongoOAAdapter()

        months = adapter.list_available_months()

        self.assertEqual(months, [])

    def test_mongo_outage_backoff_skips_repeated_queries_within_same_window(self) -> None:
        adapter = CountingFailingMongoOAAdapter()

        with patch.object(adapter, "_now", return_value=100.0):
            self.assertEqual(adapter.list_available_months(), [])
            self.assertEqual(adapter.list_application_records("2026-03"), [])

        self.assertEqual(adapter.collection_call_count, 2)

    def test_mongo_outage_backoff_keeps_error_read_status(self) -> None:
        adapter = CountingFailingMongoOAAdapter()

        with patch.object(adapter, "_now", return_value=100.0):
            self.assertEqual(adapter.list_available_months(), [])
            self.assertEqual(adapter.get_read_status().code, "error")
            self.assertEqual(adapter.list_application_records("2026-03"), [])

        status = adapter.get_read_status()
        self.assertEqual(status.code, "error")
        self.assertEqual(status.message, "OA 连接失败")

    def test_list_application_records_maps_payment_requests_and_reimbursement_details(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "modifiedTime": "2026-03-27T09:00:00",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "processId": "proc-2047",
                            "bank": "中国工商银行昆明护国支行",
                            "payeeAccount": "2502013009022108588",
                            "paymentMethod": "Bank_transfer",
                            "paymentProof": "VAT_ordinary_invoice",
                            "status": "已完成",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-1",
                        "form_id": "32",
                        "modifiedTime": "2026-03-27T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-27",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "127",
                                    "feeContent": "角磨机（刘晓宇申请）",
                                    "detailCostStatement": "生产工具采购",
                                    "detailReimbursementDate": "2026-01-06",
                                    "detailTypeOfInvoice": "VAT_ordinary_invoice",
                                },
                                {
                                    "row_index": 1,
                                    "detailProjectName": "6478072593d1377c38f340ce",
                                    "detailReimbursementAmount": "12",
                                    "detailExpenseType": "运费/邮费/杂费",
                                    "detailCostStatement": "工控机改标签邮寄费用",
                                    "detailReimbursementDate": "2026-03-11",
                                    "detailTypeOfInvoice": "Special_invoice",
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
                {"_id": "6478072593d1377c38f340ce", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 2)
        payment = next(record for record in records if record.id == "oa-pay-2047")
        self.assertEqual(payment.applicant, "刘际涛")
        self.assertEqual(payment.project_name, "云南溯源科技")
        self.assertEqual(payment.apply_type, "支付申请")
        self.assertEqual(payment.workflow_status, "completed")
        self.assertEqual(payment.completed_at, "2026-03-27T09:00:00")
        self.assertEqual(payment.counterparty_name, "中国电信股份有限公司昆明分公司")
        self.assertEqual(payment.reason, "托收电话费及宽带")
        self.assertEqual(payment.detail_fields["流程实例ID"], "proc-2047")
        self.assertEqual(payment.detail_fields["流程请求ID"], "2047")
        self.assertEqual(payment.detail_fields["Mongo文档ID"], "payment-doc-1")
        self.assertEqual(payment.detail_fields["收款账号"], "2502013009022108588")

        reimbursement = next(record for record in records if record.id == "oa-exp-exp-001")
        self.assertEqual(reimbursement.project_name, "云南溯源科技；玉烟维护项目")
        self.assertEqual(reimbursement.project_name_display, "多个项目")
        self.assertEqual(reimbursement.project_names, ["云南溯源科技", "玉烟维护项目"])
        self.assertEqual(reimbursement.apply_type, "日常报销")
        self.assertEqual(reimbursement.workflow_status, "completed")
        self.assertEqual(reimbursement.completed_at, "2026-03-27T11:00:00")
        self.assertEqual(reimbursement.detail_fields["流程实例ID"], "exp-001")
        self.assertEqual(reimbursement.detail_fields["流程请求ID"], "")
        self.assertEqual(reimbursement.detail_fields["Mongo文档ID"], "expense-doc-1")
        self.assertEqual(reimbursement.amount, "139")
        self.assertEqual(reimbursement.amount_source, "detail_sum")
        self.assertEqual(reimbursement.reason, "角磨机（刘晓宇申请）；工控机改标签邮寄费用")
        self.assertEqual(reimbursement.expense_type, "运费/邮费/杂费")
        self.assertEqual(reimbursement.expense_content, "角磨机（刘晓宇申请）；工控机改标签邮寄费用")
        self.assertEqual(reimbursement.detail_fields["明细数量"], "2")
        self.assertEqual(reimbursement.detail_fields["明细金额合计"], "139")
        self.assertEqual(reimbursement.detail_fields["金额来源"], "明细合计")
        self.assertEqual(reimbursement.detail_fields["项目名称汇总"], "云南溯源科技；玉烟维护项目")
        self.assertEqual(reimbursement.detail_fields["项目名称列表"], ["云南溯源科技", "玉烟维护项目"])
        self.assertEqual(reimbursement.detail_fields["费用类型汇总"], "运费/邮费/杂费")
        self.assertEqual(reimbursement.detail_fields["费用内容摘要"], "角磨机（刘晓宇申请）；工控机改标签邮寄费用")
        self.assertEqual(reimbursement.detail_fields["报销日期范围"], "2026-01-06 至 2026-03-11")
        self.assertEqual(
            [
                {
                    "row_index": item["row_index"],
                    "project_name": item["project_name"],
                    "amount": item["amount"],
                    "expense_type": item["expense_type"],
                    "expense_content": item["expense_content"],
                    "fee_content": item["fee_content"],
                    "fee_description": item["fee_description"],
                    "reimbursement_date": item["reimbursement_date"],
                    "attachment_file_count": item["attachment_file_count"],
                    "attachment_files": item["attachment_files"],
                    "attachment_invoices": item["attachment_invoices"],
                }
                for item in reimbursement.expense_items
            ],
            [
                {
                    "row_index": "0",
                    "project_name": "云南溯源科技",
                    "amount": "127",
                    "expense_type": "",
                    "expense_content": "角磨机（刘晓宇申请）",
                    "fee_content": "角磨机（刘晓宇申请）",
                    "fee_description": "生产工具采购",
                    "reimbursement_date": "2026-01-06",
                    "attachment_file_count": "0",
                    "attachment_files": [],
                    "attachment_invoices": [],
                },
                {
                    "row_index": "1",
                    "project_name": "玉烟维护项目",
                    "amount": "12",
                    "expense_type": "运费/邮费/杂费",
                    "expense_content": "工控机改标签邮寄费用",
                    "fee_content": "",
                    "fee_description": "工控机改标签邮寄费用",
                    "reimbursement_date": "2026-03-11",
                    "attachment_file_count": "0",
                    "attachment_files": [],
                    "attachment_invoices": [],
                },
            ],
        )
        self.assertTrue(all(item["expense_item_id"].startswith("oa-exp-exp-001:item:") for item in reimbursement.expense_items))

    def test_expense_claim_single_project_display_keeps_real_project_and_dedupes_project_names(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-single-project",
                        "form_id": "32",
                        "modifiedTime": "2026-03-27T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-27",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-single-project",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "100",
                                    "feeContent": "耗材采购",
                                    "detailReimbursementDate": "2026-03-11",
                                },
                                {
                                    "row_index": 1,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "25",
                                    "feeContent": "快递费",
                                    "detailReimbursementDate": "2026-03-12",
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
        )

        records = adapter.list_application_records("2026-03")

        reimbursement = records[0]
        self.assertEqual(reimbursement.project_name, "玉烟维护项目")
        self.assertEqual(reimbursement.project_name_display, "玉烟维护项目")
        self.assertEqual(reimbursement.project_names, ["玉烟维护项目"])
        self.assertEqual(reimbursement.detail_fields["项目名称汇总"], "玉烟维护项目")
        self.assertEqual(reimbursement.detail_fields["项目名称列表"], ["玉烟维护项目"])

    def test_payment_request_marks_etc_batch_from_oa_text_marker(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-etc-batch",
                        "form_id": "2",
                        "modifiedTime": "2026-05-03T09:00:00",
                        "data": {
                            "applicationDate": "2026-05-03",
                            "userName": "刘际涛",
                            "amount": "53.84",
                            "beneficiary": "云南高速通行费",
                            "cause": "ETC批量提交\netc_batch_id=etc_20260503_001\n\n2026-02-27 云ADA0381 13.07",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "etc-flow-001",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_application_records("2026-05")

        self.assertEqual(len(records), 1)
        payment = records[0]
        self.assertEqual(getattr(payment, "source", None), "etc_batch")
        self.assertEqual(getattr(payment, "etc_batch_id", None), "etc_20260503_001")
        self.assertIn("ETC批量提交", getattr(payment, "tags", []))

    def test_list_all_application_records_returns_records_across_months(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "modifiedTime": "2026-03-27T09:00:00",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                        },
                    },
                    {
                        "_id": "payment-doc-2",
                        "form_id": "2",
                        "modifiedTime": "2026-04-13T09:00:00",
                        "data": {
                            "applicationDate": "2026-04-13",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2048",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_all_application_records()

        self.assertEqual([record.id for record in records], ["oa-pay-2047", "oa-pay-2048"])
        self.assertEqual(adapter.get_read_status().code, "ready")

    def test_list_application_records_applies_form_type_and_status_filters(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请单",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "processStatus": "2",
                        },
                    },
                    {
                        "_id": "payment-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-17",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2048",
                            "processStatus": "1",
                        },
                    },
                ],
                "32": [
                    {
                        "_id": "expense-doc-1",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "127",
                                    "feeContent": "角磨机",
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )
        adapter.set_import_filter_provider(
            lambda: {
                "form_types": ["payment_request"],
                "statuses": ["completed"],
            }
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual([record.id for record in records], ["oa-pay-2047"])
        self.assertEqual(
            {record.id: record.workflow_status for record in records},
            {"oa-pay-2047": "completed"},
        )
        self.assertEqual(records[0].apply_type, "支付申请")
        self.assertEqual(adapter.form_load_calls, [("2", "2026-03")])

    def test_search_application_records_uses_full_range_filters_without_global_import_settings(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2025-12-17",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2048",
                            "processStatus": "1",
                        },
                    },
                ],
                "32": [
                    {
                        "_id": "expense-doc-1981",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2025-12-23",
                            "Reimbursement Personnel": "陈雄兵",
                            "titleName": "日常报销",
                            "processId": "1981",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "135",
                                    "feeContent": "去大理检修中水系统餐费",
                                    "detailReimbursementDate": "2025-12-23",
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "大理卷烟厂动力车间中水处理系统升级改造项目"}},
            ],
        )
        adapter.set_import_filter_provider(lambda: {"form_types": ["payment_request"], "statuses": ["completed"]})

        records = adapter.search_application_records(
            q="大理",
            form_types=["expense_claim"],
            statuses=["completed"],
            date_from="2025-01-01",
            date_to="2025-12-31",
        )

        self.assertEqual([record.id for record in records], ["oa-exp-1981"])
        self.assertEqual(records[0].month, "2025-12")

    def test_search_application_record_rows_uses_paged_summary_without_attachment_parse(self) -> None:
        adapter = SearchSummaryStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-2048",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-01-15",
                            "userName": "樊祖芳",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2048",
                            "processStatus": "2",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-1981",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-01-15",
                            "Reimbursement Personnel": "陈雄兵",
                            "titleName": "日常报销",
                            "processId": "1981",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "135",
                                    "feeContent": "餐费",
                                    "detailReimbursementDate": "2025-12-23",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "invoice.pdf", "filePath": "/tmp/invoice.pdf", "suffix": "pdf"}
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "大理卷烟厂动力车间中水处理系统升级改造项目"}},
            ],
        )

        payload = adapter.search_application_record_rows(
            q="大理",
            form_types=["expense_claim"],
            statuses=["completed"],
            date_from="2026-01-01",
            date_to="2026-01-31",
            page=0,
            page_size=20,
            imported_entries={"oa-exp-1981": {"imported_at": "2026-05-18T10:00:00"}},
        )

        self.assertEqual(payload["total"], 1)
        row = payload["rows"][0]
        self.assertEqual(row["row_id"], "oa-exp-1981")
        self.assertEqual(row["application_date"], "2026-01-15")
        self.assertEqual(row["project_name"], "大理卷烟厂动力车间中水处理系统升级改造项目")
        self.assertEqual(row["attachment_file_count"], 1)
        self.assertEqual(row["importable_invoice_count"], 0)
        self.assertEqual(row["import_status"], "imported")
        self.assertEqual(adapter.form_load_calls, [])
        self.assertEqual(adapter.search_document_calls[0]["form_id"], "32")
        self.assertEqual(adapter.search_document_calls[0]["limit"], 20)
        self.assertIn("$and", adapter.count_document_calls[0])

    def test_search_application_record_rows_uses_exact_id_lookup_and_completed_authority(self) -> None:
        adapter = SearchSummaryStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "进行中申请人",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "进行中附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "已完成申请人",
                            "flowRequestId": "3002",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "已完成附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_cached_attachment_invoice_count",
            return_value=0,
        ) as cached_invoice_count:
            payload = adapter.search_application_record_rows(
                q="oa-exp-3002",
                form_types=["expense_claim"],
                statuses=["completed", "in_progress"],
                page=0,
                page_size=2,
            )

        self.assertEqual(payload["total"], 1)
        self.assertEqual(len(payload["rows"]), 1)
        self.assertEqual(payload["rows"][0]["row_id"], "oa-exp-3002")
        self.assertEqual(payload["rows"][0]["status"], "completed")
        self.assertEqual(payload["rows"][0]["applicant"], "已完成申请人")
        cached_invoice_count.assert_called_once()
        self.assertEqual(
            [file_entry["fileName"] for file_entry in cached_invoice_count.call_args.args[0]],
            ["已完成附件.pdf"],
        )
        self.assertEqual(adapter.form_load_calls, [])
        self.assertEqual(adapter.search_document_calls, [])
        self.assertEqual(adapter.count_document_calls, [])

    def test_search_application_records_selects_completed_duplicate_before_attachment_parse(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "进行中申请人",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "进行中附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "已完成申请人",
                            "flowRequestId": "3002",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "已完成附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            return_value={"evidences": [], "invoices": [], "artifacts": []},
        ) as parse_pool:
            records = adapter.search_application_records(
                q="oa-exp-3002",
                form_types=["expense_claim"],
                statuses=["completed", "in_progress"],
            )

        self.assertEqual([record.id for record in records], ["oa-exp-3002"])
        self.assertEqual(records[0].workflow_status, "completed")
        self.assertEqual(records[0].applicant, "已完成申请人")
        parse_pool.assert_called_once()
        self.assertEqual(
            [file_entry["fileName"] for file_entry in parse_pool.call_args.args[0]],
            ["已完成附件.pdf"],
        )

    def test_refresh_application_record_attachments_forces_selected_records_only(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-1981",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2025-12-23",
                            "Reimbursement Personnel": "陈雄兵",
                            "titleName": "日常报销",
                            "processId": "1981",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "135",
                                    "feeContent": "餐费",
                                    "detailReimbursementDate": "2025-12-23",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "invoice.pdf", "filePath": "/tmp/invoice.pdf", "suffix": "pdf"},
                                            {"fileName": "meal.jpg", "filePath": "/tmp/meal.jpg", "suffix": "jpg"},
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "大理卷烟厂动力车间中水处理系统升级改造项目"}},
            ],
            attachment_invoice_rows={
                "invoice.pdf": [{"invoice_no": "INV-001", "attachment_name": "invoice.pdf", "total_with_tax": "135.00"}],
            },
        )

        records = adapter.refresh_application_record_attachments(["oa-exp-1981"])

        self.assertEqual([record.id for record in records], ["oa-exp-1981"])
        self.assertEqual(records[0].attachment_file_count, 2)
        self.assertEqual(len(records[0].attachment_invoices), 1)
        self.assertNotIn("2025-12", adapter._records_cache)

    def test_list_oa_import_filter_options_normalizes_oa_names_and_excludes_unsupported_statuses(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "data": {"fromTitle": "支付申请单", "processStatus": "2"},
                    },
                    {
                        "_id": "payment-doc-2",
                        "form_id": "2",
                        "data": {"fromTitle": "", "status": "REJECTED"},
                    },
                ],
                "32": [
                    {
                        "_id": "expense-doc-1",
                        "form_id": "32",
                        "data": {"titleName": "", "processStatus": "1"},
                    },
                    {
                        "_id": "expense-doc-2",
                        "form_id": "32",
                        "data": {"titleName": "日常报销", "processStatus": "4"},
                    },
                ],
            },
            project_documents=[],
        )

        options = adapter.list_oa_import_filter_options()

        self.assertEqual(
            options,
            {
                "available_form_types": [
                    {"id": "payment_request", "label": "支付申请"},
                    {"id": "expense_claim", "label": "日常报销"},
                ],
                "available_statuses": [
                    {"id": "completed", "label": "已完成"},
                    {"id": "in_progress", "label": "进行中"},
                ],
            },
        )

    def test_list_application_records_by_row_ids_returns_only_requested_rows(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "modifiedTime": "2026-03-27T09:00:00",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-1",
                        "form_id": "32",
                        "modifiedTime": "2025-12-20T11:00:00",
                        "data": {
                            "ApplicationDate": "2025-12-20",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "127",
                                    "feeContent": "旧报销",
                                    "detailReimbursementDate": "2025-12-20",
                                },
                                {
                                    "row_index": 1,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "12",
                                    "feeContent": "补差",
                                    "detailReimbursementDate": "2025-12-21",
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_application_records_by_row_ids(["oa-exp-exp-001-1", "oa-pay-2047"])

        self.assertEqual([record.id for record in records], ["oa-exp-exp-001", "oa-pay-2047"])
        self.assertEqual(records[0].month, "2025-12")
        self.assertEqual(records[1].month, "2026-03")
        self.assertEqual(adapter.get_read_status().code, "ready")

    def test_payment_request_infers_expense_type_from_reason_when_explicit_field_is_missing(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-2",
                        "form_id": "2",
                        "modifiedTime": "2026-03-27T09:00:00",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "873",
                            "beneficiary": "云南城建物业运营集团有限公司盘龙区分公司",
                            "cause": "财富中心1-2月水电费",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2030",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        payment = records[0]
        self.assertEqual(payment.expense_type, "房屋使用费（户租、水电、维修、车位、屋业等）")
        self.assertEqual(payment.detail_fields["费用类型"], "房屋使用费（户租、水电、维修、车位、屋业等）")

    def test_payment_request_reads_explicit_category_without_using_expense_claim_field(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-category",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-08-18",
                            "userName": "测试人员",
                            "amount": "332",
                            "beneficiary": "测试供应商",
                            "cause": "无法从文本可靠推断的付款",
                            "projectName": "project-1",
                            "category": "s4",
                            "purposeType": "s5",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[{"_id": "project-1", "data": {"name": "测试项目"}}],
        )

        payment = adapter.list_application_records("2026-08")[0]

        self.assertEqual(payment.expense_type, "交通费")

    def test_payment_request_uses_configured_expense_type_field(self) -> None:
        adapter = StubMongoOAAdapter(
            settings=MongoOASettings(
                host="127.0.0.1",
                database="form_data_db",
                payment_expense_type_field="customCategory",
            ),
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-custom-category",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-08-18",
                            "userName": "测试人员",
                            "amount": "128",
                            "beneficiary": "测试供应商",
                            "cause": "无法从文本可靠推断的付款",
                            "projectName": "project-1",
                            "category": "s5",
                            "customCategory": "s4",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[{"_id": "project-1", "data": {"name": "测试项目"}}],
        )

        payment = adapter.list_application_records("2026-08")[0]

        self.assertEqual(payment.expense_type, "交通费")

    def test_expense_claim_maps_oa_expense_type_enum_code_without_fallback(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-2290",
                        "form_id": "32",
                        "modifiedTime": "2026-08-14T08:46:03",
                        "data": {
                            "ApplicationDate": "2026-06-08",
                            "Reimbursement Personnel": "黄亮",
                            "titleName": "日常报销",
                            "processId": "2290",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "dali-project",
                                    "detailReimbursementAmount": "144.99",
                                    "purposeType": "s4",
                                    "feeContent": "大理出差返回昆明车费",
                                    "detailReimbursementDate": "2026-06-08",
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "dali-project", "data": {"name": "大理卷烟厂余热综合利用项目"}},
            ],
        )

        records = adapter.list_application_records("2026-06")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.expense_type, "交通费")
        self.assertEqual(reimbursement.detail_fields["费用类型"], "交通费")
        self.assertEqual(reimbursement.expense_items[0]["expense_type"], "交通费")

    def test_expense_claim_ignores_internal_reimbursement_enum_and_keeps_standard_expense_type(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-2",
                        "form_id": "32",
                        "modifiedTime": "2026-01-05T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-01-04",
                            "Reimbursement Personnel": "胡瑢",
                            "titleName": "日常报销",
                            "processId": "1964",
                            "detailReimbursementType": "withdraw_expense",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "yx-project",
                                    "detailReimbursementAmount": "135",
                                    "purposeType": "unknown_expense_code",
                                    "category": "s4",
                                    "feeType": "s4",
                                    "feeContent": "玉溪德力西买材料",
                                    "detailReimbursementDate": "2025-10-02",
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "yx-project", "data": {"name": "玉溪卷烟厂复烤车间技术升级改造项目-配电监控系统建设（第2次采购）"}},
            ],
        )

        records = adapter.list_application_records("2026-01")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.expense_type, "设备货款及材料费")
        self.assertEqual(reimbursement.detail_fields["费用类型"], "设备货款及材料费")

    def test_expense_claim_attachment_invoices_are_exposed_on_record_and_summarized_in_detail_fields(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-3",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementDate": "2026-03-28",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"},
                                            {"fileName": "invoice-b.pdf", "filePath": "/invoice-b.pdf", "suffix": "pdf"},
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_rows=[
                {
                    "invoice_code": "053002200111",
                    "invoice_no": "40512344",
                    "seller_name": "云南顺丰速运有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2023-07-11",
                    "amount": "11.32",
                    "tax_rate": "6%",
                    "tax_amount": "0.68",
                    "total_with_tax": "12.00",
                    "attachment_name": "invoice-a.pdf",
                },
                {
                    "invoice_code": "053002200112",
                    "invoice_no": "40512345",
                    "seller_name": "云南顺丰速运有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2023-07-12",
                    "amount": "20.00",
                    "tax_rate": "6%",
                    "tax_amount": "1.20",
                    "total_with_tax": "21.20",
                    "attachment_name": "invoice-b.pdf",
                },
            ],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        attachment_invoices = getattr(reimbursement, "attachment_invoices", [])
        self.assertEqual(len(attachment_invoices), 2)
        self.assertEqual(attachment_invoices[0]["invoice_no"], "40512344")
        self.assertEqual(attachment_invoices[1]["attachment_name"], "invoice-b.pdf")
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "2")
        self.assertEqual(reimbursement.detail_fields["附件发票识别情况"], "已解析 2 / 2")
        self.assertIn("40512344", reimbursement.detail_fields["附件发票摘要"])
        self.assertIn("40512345", reimbursement.detail_fields["附件发票摘要"])

    def test_expense_claim_binds_attachment_invoices_to_each_expense_item(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-248",
                        "form_id": "32",
                        "modifiedTime": "2026-03-04T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-04",
                            "Reimbursement Personnel": "胡瑢",
                            "titleName": "日常报销",
                            "processId": "exp-248",
                            "amount": "248",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "ht-project",
                                    "detailReimbursementAmount": "120",
                                    "feeContent": "工作证管理系统维护材料",
                                    "detailReimbursementDate": "2026-03-04",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "248-item-0-a.pdf", "filePath": "/248-item-0-a.pdf", "suffix": "pdf"},
                                            {"fileName": "248-item-0-b.pdf", "filePath": "/248-item-0-b.pdf", "suffix": "pdf"},
                                        ]
                                    },
                                },
                                {
                                    "row_index": 1,
                                    "detailProjectName": "ht-project",
                                    "detailReimbursementAmount": "128",
                                    "feeContent": "工作证管理系统维护服务",
                                    "detailReimbursementDate": "2026-03-04",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "248-item-1-a.pdf", "filePath": "/248-item-1-a.pdf", "suffix": "pdf"},
                                        ]
                                    },
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[{"_id": "ht-project", "data": {"name": "2024-2026年度红塔集团工作证管理系统维护项目"}}],
            attachment_invoice_rows={
                "248-item-0-a.pdf": [{"invoice_no": "248001", "attachment_name": "248-item-0-a.pdf", "amount": "60.00"}],
                "248-item-0-b.pdf": [{"invoice_no": "248002", "attachment_name": "248-item-0-b.pdf", "amount": "60.00"}],
                "248-item-1-a.pdf": [{"invoice_no": "248003", "attachment_name": "248-item-1-a.pdf", "amount": "128.00"}],
            },
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.id, "oa-exp-exp-248")
        self.assertEqual(len(reimbursement.expense_items), 2)
        self.assertEqual([len(item["attachment_invoices"]) for item in reimbursement.expense_items], [2, 1])
        self.assertEqual([invoice["invoice_no"] for invoice in reimbursement.attachment_invoices], ["248001", "248002", "248003"])
        for item in reimbursement.expense_items:
            self.assertIn("expense_item_id", item)
            self.assertEqual(item["attachment_file_count"], str(len(item["attachment_files"])))
            for invoice in item["attachment_invoices"]:
                self.assertEqual(invoice["source_expense_row_index"], item["row_index"])
                self.assertEqual(invoice["source_expense_item_id"], item["expense_item_id"])
                self.assertEqual(invoice["source_attachment_name"], invoice["attachment_name"])
                self.assertTrue(invoice["source_attachment_key"])
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "3")
        self.assertEqual(reimbursement.detail_fields["附件发票识别情况"], "已解析 3 / 3")

    def test_expense_claim_oa_2035_parses_attachment_evidences_invoices_and_payment_receipts(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        evidence_by_file = {
            "oa-2035-etc-25.png": [
                {
                    "evidence_type": "payment_receipt",
                    "document_kind": "wechat_etc_payment",
                    "amount": "25.00",
                    "merchant_name": "云南高速公路收费站",
                    "paid_at": "2026-03-04",
                    "transaction_no": "wx-etc-25",
                    "payment_method": "微信",
                }
            ],
            "oa-2035-etc-23.png": [
                {
                    "evidence_type": "payment_receipt",
                    "document_kind": "wechat_etc_payment",
                    "amount": "23.00",
                    "merchant_name": "云南高速公路收费站",
                    "paid_at": "2026-03-04",
                    "transaction_no": "wx-etc-23",
                    "payment_method": "微信",
                }
            ],
            "oa-2035-toll-invoices.jpg": [
                {
                    "evidence_type": "machine_invoice",
                    "document_kind": "yunnan_machine_invoice",
                    "amount": "25.00",
                    "total_with_tax": "25.00",
                    "invoice_code": "053002203501",
                    "invoice_no": "20350025",
                    "seller_name": "云南高速公路收费站",
                    "issue_date": "2026-03-04",
                    "source_region_key": "left",
                },
                {
                    "evidence_type": "machine_invoice",
                    "document_kind": "yunnan_machine_invoice",
                    "amount": "23.00",
                    "total_with_tax": "23.00",
                    "invoice_code": "053002203501",
                    "invoice_no": "20350023",
                    "seller_name": "云南高速公路收费站",
                    "issue_date": "2026-03-04",
                    "source_region_key": "right",
                },
            ],
            "oa-2035-fuel-invoice.pdf": [
                {
                    "evidence_type": "tax_invoice",
                    "document_kind": "digital_invoice",
                    "amount": "200.00",
                    "total_with_tax": "200.00",
                    "digital_invoice_no": "255320000002035200",
                    "seller_name": "中国石化销售股份有限公司云南昆明石油分公司",
                    "issue_date": "2026-03-04",
                }
            ],
            "oa-2035-fuel-payment.png": [
                {
                    "evidence_type": "payment_receipt",
                    "document_kind": "wechat_fuel_payment",
                    "amount": "200.00",
                    "merchant_name": "中国石化销售股份有限公司云南昆明石油分公司",
                    "paid_at": "2026-03-04",
                    "merchant_order_no": "fuel-merchant-order-200",
                    "payment_method": "微信",
                }
            ],
        }

        def parse_evidences(files: list[dict[str, object]]) -> list[dict[str, str]]:
            rows: list[dict[str, str]] = []
            for file_entry in files:
                rows.extend(dict(row) for row in evidence_by_file[str(file_entry.get("fileName"))])
            return rows

        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-2035",
                        "form_id": "32",
                        "modifiedTime": "2026-03-04T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-04",
                            "Reimbursement Personnel": "胡瑢",
                            "titleName": "日常报销",
                            "processId": "2035",
                            "amount": "248",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "yx-project",
                                    "detailReimbursementAmount": "48",
                                    "feeContent": "昆明玉溪来回过路费",
                                    "detailReimbursementDate": "2026-03-04",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "oa-2035-etc-25.png", "filePath": "/oa-2035-etc-25.png", "suffix": "png"},
                                            {"fileName": "oa-2035-etc-23.png", "filePath": "/oa-2035-etc-23.png", "suffix": "png"},
                                            {"fileName": "oa-2035-toll-invoices.jpg", "filePath": "/oa-2035-toll-invoices.jpg", "suffix": "jpg"},
                                        ]
                                    },
                                },
                                {
                                    "row_index": 1,
                                    "detailProjectName": "yx-project",
                                    "detailReimbursementAmount": "200",
                                    "feeContent": "加油费200元",
                                    "detailReimbursementDate": "2026-03-04",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "oa-2035-fuel-invoice.pdf", "filePath": "/oa-2035-fuel-invoice.pdf", "suffix": "pdf"},
                                            {"fileName": "oa-2035-fuel-payment.png", "filePath": "/oa-2035-fuel-payment.png", "suffix": "png"},
                                        ]
                                    },
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[{"_id": "yx-project", "data": {"name": "玉烟维护项目", "code": "YYWH"}}],
            attachment_invoice_cache=cache,
        )

        with (
            adapter.force_attachment_invoice_sync_parse(),
            patch.object(adapter._attachment_invoice_service, "parse_evidences", side_effect=parse_evidences, create=True) as parse_evidences_mock,
            patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("parse_files fallback should not run")),
        ):
            records = adapter.list_application_records("2026-03")

        parse_evidences_mock.assert_called()
        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.id, "oa-exp-2035")
        self.assertEqual(reimbursement.attachment_file_count, 5)
        self.assertEqual(len(reimbursement.expense_items), 2)
        self.assertEqual(len(reimbursement.attachment_artifacts), 5)
        self.assertEqual(len(reimbursement.attachment_evidences), 6)
        self.assertEqual(len(reimbursement.attachment_invoices), 3)
        self.assertEqual(
            [len(item["attachment_evidences"]) for item in reimbursement.expense_items],
            [4, 2],
        )
        self.assertEqual(
            [len(item["attachment_invoices"]) for item in reimbursement.expense_items],
            [2, 1],
        )
        self.assertEqual(
            [evidence["evidence_type"] for evidence in reimbursement.attachment_evidences],
            [
                "payment_receipt",
                "payment_receipt",
                "machine_invoice",
                "machine_invoice",
                "tax_invoice",
                "payment_receipt",
            ],
        )
        self.assertEqual(
            [invoice.get("invoice_no") or invoice.get("digital_invoice_no") for invoice in reimbursement.attachment_invoices],
            ["20350025", "20350023", "255320000002035200"],
        )
        self.assertEqual(reimbursement.detail_fields["附件凭证数量"], "6")
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "3")
        self.assertEqual(reimbursement.detail_fields["付款凭证数量"], "3")
        self.assertEqual(reimbursement.detail_fields["附件凭证识别情况"], "已解析 6 / 5")
        self.assertEqual(reimbursement.detail_fields["附件发票金额合计"], "248")
        self.assertEqual(reimbursement.detail_fields["付款凭证金额合计"], "248")
        self.assertEqual(reimbursement.detail_fields["附件凭证闭环状态"], "付款凭证金额与附件发票金额一致")
        self.assertEqual(len(cache.entries), 5)
        self.assertTrue(all("evidences" in payload for payload in cache.entries.values()))
        self.assertTrue(all("invoices" in payload for payload in cache.entries.values()))
        self.assertTrue(all("artifacts" in payload for payload in cache.entries.values()))

    def test_expense_claim_single_item_does_not_duplicate_attachment_invoice_for_292_case(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-292",
                        "form_id": "32",
                        "modifiedTime": "2026-03-24T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-24",
                            "Reimbursement Personnel": "胡瑢",
                            "titleName": "日常报销",
                            "processId": "exp-292",
                            "amount": "292",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "energy-project",
                                    "detailReimbursementAmount": "292",
                                    "feeContent": "能源管理相关系统运维服务",
                                    "detailReimbursementDate": "2026-03-24",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {"fileName": "292-invoice.pdf", "filePath": "/292-invoice.pdf", "suffix": "pdf"},
                                            {"fileName": "292-invoice-copy.pdf", "filePath": "/292-invoice-copy.pdf", "suffix": "pdf"},
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[{"_id": "energy-project", "data": {"name": "红云红河能源管理运维项目"}}],
            attachment_invoice_rows={
                "292-invoice.pdf": [{"invoice_no": "292001", "attachment_name": "292-invoice.pdf", "amount": "292.00"}],
                "292-invoice-copy.pdf": [{"invoice_no": "292001", "attachment_name": "292-invoice-copy.pdf", "amount": "292.00"}],
            },
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(len(reimbursement.expense_items), 1)
        self.assertEqual([invoice["invoice_no"] for invoice in reimbursement.expense_items[0]["attachment_invoices"]], ["292001"])
        self.assertEqual([invoice["invoice_no"] for invoice in reimbursement.attachment_invoices], ["292001"])
        invoice = reimbursement.attachment_invoices[0]
        self.assertEqual(invoice["source_expense_row_index"], "0")
        self.assertEqual(invoice["source_expense_item_id"], reimbursement.expense_items[0]["expense_item_id"])
        self.assertEqual(invoice["source_attachment_name"], invoice["attachment_name"])
        self.assertTrue(invoice["source_attachment_key"])
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "1")

    def test_expense_claim_uses_header_amount_before_detail_sum(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-header-amount",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-header-001",
                            "amount": "1549.00",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "1000", "feeContent": "设备材料"},
                                {"row_index": 1, "detailReimbursementAmount": "549.00", "feeContent": "邮寄费用"},
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.id, "oa-exp-exp-header-001")
        self.assertEqual(reimbursement.amount, "1549.00")
        self.assertEqual(reimbursement.amount_source, "header")
        self.assertIsNone(reimbursement.amount_mismatch)
        self.assertEqual(reimbursement.detail_fields["金额来源"], "主表总金额")
        self.assertEqual(reimbursement.detail_fields["明细金额合计"], "1549")

    def test_expense_claim_falls_back_to_detail_sum_when_header_amount_is_invalid(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-detail-sum",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-detail-sum-001",
                            "amount": "not-a-number",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "19.50", "feeContent": "停车费"},
                                {"row_index": 1, "detailReimbursementAmount": "80.50", "feeContent": "汽油费"},
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.amount, "100")
        self.assertEqual(reimbursement.amount_source, "detail_sum")
        self.assertEqual(reimbursement.detail_fields["金额来源"], "明细合计")
        self.assertEqual(reimbursement.detail_fields["明细金额合计"], "100")

    def test_expense_claim_records_amount_mismatch_when_header_and_detail_sum_differ(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-mismatch",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-mismatch-001",
                            "amount": "1549.00",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "1000", "feeContent": "设备材料"},
                                {"row_index": 1, "detailReimbursementAmount": "500", "feeContent": "邮寄费用"},
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.amount, "1549.00")
        self.assertEqual(
            reimbursement.amount_mismatch,
            {"header_amount": "1549.00", "detail_sum": "1500", "difference": "49.00"},
        )
        self.assertEqual(reimbursement.detail_fields["金额差异"], "主表总金额 1549.00；明细合计 1500；差异 49.00")

    def test_expense_claim_aggregates_and_dedupes_attachment_invoices_across_schedule_items(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-attach-dedupe",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-dedupe-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "12",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}]
                                    },
                                },
                                {
                                    "row_index": 1,
                                    "detailReimbursementAmount": "21.20",
                                    "feeContent": "顺丰补寄发票",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "invoice-b.pdf", "filePath": "/invoice-b.pdf", "suffix": "pdf"}]
                                    },
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
            attachment_invoice_rows={
                "invoice-a.pdf": [
                    {"invoice_no": "40512344", "attachment_name": "invoice-a.pdf", "amount": "12.00"},
                    {"invoice_no": "40512344", "attachment_name": "invoice-a-copy.pdf", "amount": "12.00"},
                ],
                "invoice-b.pdf": [
                    {"digital_invoice_no": "25532000000191043884", "attachment_name": "invoice-b.pdf", "amount": "21.20"},
                    {"attachment_name": "invoice-b.pdf", "amount": "21.20"},
                ],
            },
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(reimbursement.attachment_file_count, 2)
        self.assertEqual(
            [
                {
                    "invoice_no": invoice.get("invoice_no"),
                    "digital_invoice_no": invoice.get("digital_invoice_no"),
                    "attachment_name": invoice.get("attachment_name"),
                    "amount": invoice.get("amount"),
                    "source_expense_row_index": invoice.get("source_expense_row_index"),
                    "source_attachment_name": invoice.get("source_attachment_name"),
                }
                for invoice in reimbursement.attachment_invoices
            ],
            [
                {
                    "invoice_no": "40512344",
                    "digital_invoice_no": None,
                    "attachment_name": "invoice-a.pdf",
                    "amount": "12.00",
                    "source_expense_row_index": "0",
                    "source_attachment_name": "invoice-a.pdf",
                },
                {
                    "invoice_no": None,
                    "digital_invoice_no": "25532000000191043884",
                    "attachment_name": "invoice-b.pdf",
                    "amount": "21.20",
                    "source_expense_row_index": "1",
                    "source_attachment_name": "invoice-b.pdf",
                },
            ],
        )
        self.assertEqual([len(item["attachment_invoices"]) for item in reimbursement.expense_items], [1, 1])
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "2")
        self.assertEqual(reimbursement.detail_fields["附件发票识别情况"], "已解析 2 / 2")

    def test_list_application_records_by_row_ids_dedupes_new_and_legacy_expense_ids(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-row-id-compat",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "10", "feeContent": "停车费"},
                                {"row_index": 1, "detailReimbursementAmount": "20", "feeContent": "汽油费"},
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
        )

        records = adapter.list_application_records_by_row_ids(["oa-exp-exp-001", "oa-exp-exp-001-1"])

        self.assertEqual([record.id for record in records], ["oa-exp-exp-001"])

    def test_list_application_records_by_row_ids_prefers_exact_new_id_over_legacy_prefix_candidate(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-prefix",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "10", "feeContent": "停车费"},
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-exact",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "周洁莹",
                            "titleName": "日常报销",
                            "processId": "exp-001",
                            "schedule": [
                                {"row_index": 0, "detailReimbursementAmount": "20", "feeContent": "汽油费"},
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        records = adapter.list_application_records_by_row_ids(["oa-exp-exp-001"])

        self.assertEqual([record.id for record in records], ["oa-exp-exp-001"])
        self.assertEqual(records[0].applicant, "周洁莹")

    def test_expense_claim_attachment_list_shape_is_normalized_into_attachment_files(self) -> None:
        adapter = AttachmentStubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-3b",
                        "form_id": "32",
                        "modifiedTime": "2026-02-09T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-02-09",
                            "Reimbursement Personnel": "周洁莹",
                            "titleName": "日常报销",
                            "processId": "69898450db8c0a3633bd748c",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "200",
                                    "feeContent": "汽油费",
                                    "detailReimbursementDate": "2025-04-24",
                                    "detailReimbursementAttachment": {
                                        "list": [
                                            {
                                                "status": "success",
                                                "name": "20240424-汽油费-200.jpg",
                                                "response": {
                                                    "extra": {
                                                        "filePath": "/20240424-汽油费-200.jpg",
                                                        "fileName": "20240424-汽油费-200.jpg",
                                                        "suffix": "jpg",
                                                    }
                                                },
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
            attachment_invoice_rows=[
                {
                    "invoice_code": "053002200111",
                    "invoice_no": "15312761",
                    "seller_name": "云南中油严家山交通服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2025-04-24",
                    "amount": "200.00",
                    "tax_rate": "13%",
                    "tax_amount": "23.01",
                    "total_with_tax": "200.00",
                    "attachment_name": "20240424-汽油费-200.jpg",
                }
            ],
        )

        records = adapter.list_application_records("2026-02")

        self.assertEqual(len(records), 1)
        reimbursement = records[0]
        self.assertEqual(len(reimbursement.attachment_invoices), 1)
        self.assertEqual(reimbursement.attachment_invoices[0]["invoice_no"], "15312761")
        self.assertEqual(reimbursement.detail_fields["附件发票数量"], "1")
        self.assertIn("15312761", reimbursement.detail_fields["附件发票摘要"])

    def test_expense_claim_uses_cached_attachment_invoices_without_sync_parsing(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        item = {
            "row_index": 0,
            "detailProjectName": "oa-project-001",
            "detailReimbursementAmount": "120.00",
            "feeContent": "顺丰邮寄发票",
            "detailReimbursementAttachment": {"files": [file_entry]},
        }
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-4",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-cache-001",
                            "schedule": [
                                item
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )
        cache_key, source_fields = build_contextual_attachment_cache_fixture(
            adapter,
            file_entry,
            external_id="exp-attach-cache-001",
            row_index="0",
            item=item,
            amount="120.00",
        )
        cache.save_oa_attachment_invoice_cache_entry(
            cache_key,
            {
                "parser_version": adapter._attachment_invoice_cache_parser_version(),
                "cache_schema_version": "2026-05-11-evidence-v1",
                "evidences": [
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "40512344",
                        "seller_name": "云南顺丰速运有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2023-07-11",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                        **source_fields,
                    }
                ],
                "invoices": [
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "40512344",
                        "seller_name": "云南顺丰速运有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2023-07-11",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                        **source_fields,
                    }
                ],
                "artifacts": [
                    {
                        "attachment_name": "invoice-a.pdf",
                        "file_path": "/invoice-a.pdf",
                        "suffix": "pdf",
                        "parse_status": "parsed",
                        "parse_error": "",
                        **source_fields,
                    }
                ],
            },
        )

        with patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].attachment_invoices[0]["invoice_no"], "40512344")

    def test_expense_claim_ignores_legacy_attachment_invoice_cache_without_source_fields(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-legacy-cache",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-legacy-cache-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementAttachment": {"files": [file_entry]},
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )
        legacy_cache_key = adapter._attachment_invoice_cache_key(file_entry)
        cache.save_oa_attachment_invoice_cache_entry(
            legacy_cache_key,
            {
                "parser_version": adapter._attachment_invoice_cache_parser_version(),
                "invoices": [
                    {
                        "invoice_no": "legacy-40512344",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                    }
                ],
            },
        )

        with (
            adapter.force_attachment_invoice_sync_parse(),
            patch.object(
                adapter._attachment_invoice_service,
                "parse_evidences",
                return_value=[
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "40512344",
                        "seller_name": "云南顺丰速运有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2023-07-11",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                    }
                ],
            ) as parse_evidences,
        ):
            records = adapter.list_application_records("2026-03")

        parse_evidences.assert_called_once()
        invoice = records[0].attachment_invoices[0]
        self.assertEqual(invoice["invoice_no"], "40512344")
        for field in (
            "source_expense_row_index",
            "source_expense_item_id",
            "source_attachment_key",
            "source_attachment_name",
        ):
            self.assertTrue(invoice.get(field), field)
        current_payload = next(
            payload
            for payload in cache.entries.values()
            if payload.get("parser_version") == adapter._attachment_invoice_cache_parser_version()
            and payload.get("invoices")
            and payload["invoices"][0].get("invoice_no") == "40512344"
        )
        for field in (
            "source_expense_row_index",
            "source_expense_item_id",
            "source_attachment_key",
            "source_attachment_name",
        ):
            self.assertTrue(current_payload["invoices"][0].get(field), field)
        self.assertEqual(cache.entries[legacy_cache_key]["invoices"][0]["invoice_no"], "legacy-40512344")

    def test_expense_claim_attachment_invoice_cache_version_controls_reparse(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-cache-version",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-cache-version-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementAttachment": {"files": [file_entry]},
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )
        stale_cache_key = adapter._attachment_invoice_cache_key(file_entry)
        cache.save_oa_attachment_invoice_cache_entry(
            stale_cache_key,
            {
                "parser_version": "legacy-parser",
                "invoices": [
                    {
                        "invoice_no": "legacy-40512344",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                    }
                ],
            },
        )

        with (
            adapter.force_attachment_invoice_sync_parse(),
            patch.object(
                adapter._attachment_invoice_service,
                "parse_evidences",
                return_value=[
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "40512344",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                    }
                ],
            ),
        ):
            records = adapter.list_application_records("2026-03")

        invoice = records[0].attachment_invoices[0]
        self.assertEqual(invoice["invoice_no"], "40512344")
        cache_payloads = list(cache.entries.values())
        self.assertTrue(
            any(payload.get("parser_version") == adapter._attachment_invoice_cache_parser_version() for payload in cache_payloads)
        )
        saved_invoice = next(
            payload["invoices"][0]
            for payload in cache_payloads
            if payload.get("parser_version") == adapter._attachment_invoice_cache_parser_version()
        )
        for field in (
            "source_expense_row_index",
            "source_expense_item_id",
            "source_attachment_key",
            "source_attachment_name",
        ):
            self.assertTrue(saved_invoice.get(field), field)

    def test_expense_claim_uses_stable_attachment_key_for_source_binding(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        first_file = {"fileName": "invoice.pdf", "filePath": "/expense/row-0/invoice.pdf", "suffix": "pdf"}
        second_file = {"fileName": "invoice.pdf", "filePath": "/expense/row-1/invoice.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-stable-attachment-key",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-stable-attachment-key-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "第一项",
                                    "detailReimbursementAttachment": {"files": [first_file]},
                                },
                                {
                                    "row_index": 1,
                                    "detailReimbursementAmount": "172.00",
                                    "feeContent": "第二项",
                                    "detailReimbursementAttachment": {"files": [second_file]},
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
            attachment_invoice_cache=cache,
        )

        with (
            adapter.force_attachment_invoice_sync_parse(),
            patch.object(
                adapter._attachment_invoice_service,
                "parse_evidences",
                side_effect=[
                    [{"evidence_type": "tax_invoice", "invoice_no": "40512344", "amount": "120.00", "attachment_name": "invoice.pdf"}],
                    [{"evidence_type": "tax_invoice", "invoice_no": "40512345", "amount": "172.00", "attachment_name": "invoice.pdf"}],
                ],
            ),
        ):
            records = adapter.list_application_records("2026-03")

        invoices = records[0].attachment_invoices
        self.assertEqual(len(invoices), 2)
        first_key = invoices[0]["source_attachment_key"]
        second_key = invoices[1]["source_attachment_key"]
        self.assertNotEqual(first_key, second_key)
        self.assertEqual(first_key, records[0].attachment_invoices[0]["source_attachment_key"])
        self.assertNotEqual(
            adapter._attachment_invoice_cache_key(first_file),
            adapter._attachment_invoice_cache_key(second_file),
        )

    def test_expense_claim_parses_shared_physical_attachment_once_and_keeps_two_item_occurrences(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        shared_file = {
            "fileId": "shared-file-36",
            "fileName": "shared.pdf",
            "filePath": "/expense/shared.pdf",
            "suffix": "pdf",
        }
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-shared-attachment",
                        "form_id": "32",
                        "modifiedTime": "2026-07-16T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-07-16",
                            "Reimbursement Personnel": "樊祖芳",
                            "titleName": "日常报销",
                            "processId": "exp-shared-attachment-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "18.00",
                                    "feeContent": "第一项快递费",
                                    "detailReimbursementAttachment": {"files": [shared_file]},
                                },
                                {
                                    "row_index": 1,
                                    "detailReimbursementAmount": "18.00",
                                    "feeContent": "第二项快递费",
                                    "detailReimbursementAttachment": {"files": [shared_file]},
                                },
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
            attachment_invoice_cache=cache,
        )

        with (
            adapter.force_attachment_invoice_sync_parse(),
            patch.object(
                adapter._attachment_invoice_service,
                "parse_evidences",
                return_value=[
                    {
                        "evidence_type": "tax_invoice",
                        "digital_invoice_no": "26532000000000000036",
                        "issue_date": "2026-07-16",
                        "amount": "36.00",
                        "total_with_tax": "36.00",
                        "attachment_name": "shared.pdf",
                    }
                ],
            ) as parse_evidences,
        ):
            record = adapter.list_application_records("2026-07")[0]

        parse_evidences.assert_called_once()
        self.assertEqual(len(record.expense_items), 2)
        self.assertEqual(
            [
                item["attachment_invoices"][0]["source_expense_item_id"]
                for item in record.expense_items
            ],
            [item["expense_item_id"] for item in record.expense_items],
        )
        self.assertNotEqual(
            record.expense_items[0]["attachment_invoices"][0]["source_attachment_key"],
            record.expense_items[1]["attachment_invoices"][0]["source_attachment_key"],
        )

    def test_expense_claim_normalizes_current_cache_entry_amount_to_net_amount(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        item = {
            "row_index": 0,
            "detailProjectName": "oa-project-001",
            "detailReimbursementAmount": "215.00",
            "feeContent": "设备费用",
            "detailReimbursementAttachment": {"files": [file_entry]},
        }
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-cache-normalize",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-cache-normalize-001",
                            "schedule": [
                                item
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )
        cache_key, source_fields = build_contextual_attachment_cache_fixture(
            adapter,
            file_entry,
            external_id="exp-attach-cache-normalize-001",
            row_index="0",
            item=item,
            amount="215.00",
        )
        cache.save_oa_attachment_invoice_cache_entry(
            cache_key,
            {
                "parser_version": adapter._attachment_invoice_cache_parser_version(),
                "cache_schema_version": "2026-05-11-evidence-v1",
                "evidences": [
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "25532000000191043884",
                        "seller_name": "玉溪市卓达自动化科技有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2025-12-26",
                        "amount": "215.00",
                        "net_amount": "212.86",
                        "tax_amount": "2.14",
                        "total_with_tax": "215.00",
                        "attachment_name": "invoice-a.pdf",
                        **source_fields,
                    }
                ],
                "invoices": [
                    {
                        "evidence_type": "tax_invoice",
                        "invoice_no": "25532000000191043884",
                        "seller_name": "玉溪市卓达自动化科技有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2025-12-26",
                        "amount": "215.00",
                        "net_amount": "212.86",
                        "tax_amount": "2.14",
                        "total_with_tax": "215.00",
                        "attachment_name": "invoice-a.pdf",
                        **source_fields,
                    }
                ],
                "artifacts": [
                    {
                        "attachment_name": "invoice-a.pdf",
                        "file_path": "/invoice-a.pdf",
                        "suffix": "pdf",
                        "parse_status": "parsed",
                        "parse_error": "",
                        **source_fields,
                    }
                ],
            },
        )

        with patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices[0]["amount"], "212.86")
        self.assertEqual(cache.entries[cache_key]["invoices"][0]["amount"], "212.86")

    def test_expense_claim_defers_stale_attachment_cache_to_oa_sync_worker(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-stale-cache",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-stale-cache-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementAttachment": {"files": [file_entry]},
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )
        cache.save_oa_attachment_invoice_cache_entry(
            adapter._attachment_invoice_cache_key(file_entry),
            {"invoices": []},
        )

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_files",
            side_effect=AssertionError("API read must not parse attachments"),
        ):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices, [])

    def test_expense_claim_defers_cache_miss_to_oa_sync_worker(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-5",
                        "form_id": "32",
                        "modifiedTime": "2026-03-28T11:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-28",
                            "Reimbursement Personnel": "刘际涛",
                            "titleName": "日常报销",
                            "processId": "exp-attach-cache-miss-001",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "120.00",
                                    "feeContent": "顺丰邮寄发票",
                                    "detailReimbursementAttachment": {"files": [file_entry]},
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=cache,
        )

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_files",
            side_effect=AssertionError("API read must not parse attachments"),
        ):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices, [])

    def test_worker_sync_attachment_parse_saves_cache(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={"2": [], "32": []},
            project_documents=[],
            attachment_invoice_cache=cache,
        )
        cache_key = adapter._attachment_invoice_cache_key(file_entry)

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_evidences",
            return_value=[{"evidence_type": "tax_invoice", "invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}],
        ):
            pool = adapter._parse_attachment_invoice_files_now([(cache_key, file_entry)], month="2026-03")

        invoices = pool["invoices"]
        self.assertEqual(invoices[0]["invoice_no"], "40512344")
        self.assertEqual(invoices[0]["attachment_name"], "invoice-a.pdf")
        self.assertEqual(pool["evidences"][0]["invoice_no"], "40512344")
        self.assertEqual(pool["artifacts"][0]["parse_status"], "parsed")
        for field in (
            "source_expense_row_index",
            "source_expense_item_id",
            "source_attachment_key",
            "source_attachment_name",
        ):
            self.assertTrue(invoices[0].get(field), field)
            self.assertTrue(cache.entries[cache_key]["invoices"][0].get(field), field)
        self.assertEqual(cache.entries[cache_key]["parser_version"], adapter._attachment_invoice_cache_parser_version())
        self.assertEqual(cache.entries[cache_key]["cache_schema_version"], "2026-05-11-evidence-v1")

    def test_worker_sync_does_not_save_cache_when_ocr_runtime_fails(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={"2": [], "32": []},
            project_documents=[],
            attachment_invoice_cache=cache,
        )
        cache_key = adapter._attachment_invoice_cache_key(file_entry)

        with (
            patch.object(
                adapter._attachment_invoice_service,
                "parse_file_result",
                side_effect=OAAttachmentOCRRuntimeError("ocr_inference_failed"),
            ),
            self.assertRaisesRegex(OAAttachmentOCRRuntimeError, "ocr_inference_failed"),
        ):
            adapter._parse_attachment_invoice_files_now([(cache_key, file_entry)], month="2026-03")

        self.assertNotIn(cache_key, cache.entries)

    def test_fetch_projects_and_counterparties_derive_from_form_data(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "amount": "199",
                            "status": "已完成",
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        projects = adapter.fetch_projects()
        counterparties = adapter.fetch_counterparties()
        documents = adapter.fetch_documents("payment_requests")

        self.assertEqual(projects[0]["external_id"], "6486ca70cd6cae5d4e2b0b48")
        self.assertEqual(projects[0]["project_name"], "云南溯源科技")
        self.assertEqual(counterparties[0]["name"], "中国电信股份有限公司昆明分公司")
        self.assertEqual(documents[0]["project_name"], "云南溯源科技")

    def test_default_projection_keeps_completed_rows_and_excludes_in_progress_rows(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "status": "已完成",
                        },
                    },
                    {
                        "_id": "payment-doc-in-progress",
                        "form_id": "2",
                        "modifiedTime": "2026-03-17T09:00:00",
                        "data": {
                            "applicationDate": "2026-04-18",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2048",
                            "status": "进行中",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_application_records("2026-03")
        progress_records = adapter.list_application_records("2026-04")
        documents = adapter.fetch_documents("payment_requests")
        months = adapter.list_available_months()

        self.assertEqual([record.id for record in records], ["oa-pay-2047"])
        self.assertEqual([record.id for record in progress_records], [])
        self.assertEqual([document["external_id"] for document in documents], ["2047"])
        self.assertEqual(months, ["2026-03"])

    def test_sync_batch_parses_unique_in_progress_expense_attachment_without_projecting_it(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "amount": "199",
                            "beneficiary": "供应商 A",
                            "cause": "材料款",
                            "flowRequestId": "2047",
                            "processStatus": "2",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "modifiedTime": "2026-03-19T09:00:00",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "胡瑢",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileId": "file-1", "fileName": "进行中附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
            attachment_invoice_cache=cache,
        )
        adapter.set_import_settings_provider(
            lambda: {"form_types": ["payment_request", "expense_claim"], "statuses": ["completed"]}
        )

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_evidences",
            return_value=[
                {
                    "evidence_type": "tax_invoice",
                    "invoice_no": "40513002",
                    "amount": "88.00",
                    "attachment_name": "进行中附件.pdf",
                }
            ],
            create=True,
        ) as parse_evidences:
            with adapter.force_attachment_invoice_sync_parse():
                batch = adapter.load_sync_application_batch("2026-03")

        self.assertEqual([record.id for record in batch.projection_records], ["oa-pay-2047"])
        self.assertEqual(
            [record.id for record in batch.admission_records],
            ["oa-exp-3002", "oa-pay-2047"],
        )
        in_progress = next(record for record in batch.admission_records if record.id == "oa-exp-3002")
        self.assertEqual(in_progress.workflow_status, "in_progress")
        self.assertEqual(
            [invoice["invoice_no"] for invoice in in_progress.attachment_invoices],
            ["40513002"],
        )
        self.assertEqual(in_progress.expense_items[0]["attachment_files"][0]["fileId"], "file-1")
        parse_evidences.assert_called_once()
        self.assertEqual(len(cache.entries), 1)
        cached_entry = next(iter(cache.entries.values()))
        self.assertEqual(
            cached_entry["parser_version"],
            adapter._attachment_invoice_cache_parser_version(),
        )

    def test_manual_attachment_refresh_parses_in_progress_expense_with_existing_parser_and_cache(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "胡瑢",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileId": "file-1", "fileName": "进行中附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
            attachment_invoice_cache=cache,
        )

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_evidences",
            return_value=[
                {
                    "evidence_type": "tax_invoice",
                    "invoice_no": "40513002",
                    "amount": "88.00",
                    "attachment_name": "进行中附件.pdf",
                }
            ],
            create=True,
        ) as parse_evidences:
            records = adapter.refresh_application_record_attachments(["oa-exp-3002"])

        self.assertEqual([record.id for record in records], ["oa-exp-3002"])
        self.assertEqual(records[0].workflow_status, "in_progress")
        self.assertEqual(
            [invoice["invoice_no"] for invoice in records[0].attachment_invoices],
            ["40513002"],
        )
        self.assertEqual(records[0].expense_items[0]["attachment_files"][0]["fileId"], "file-1")
        parse_evidences.assert_called_once()
        self.assertEqual(len(cache.entries), 1)
        cached_entry = next(iter(cache.entries.values()))
        self.assertEqual(
            cached_entry["parser_version"],
            adapter._attachment_invoice_cache_parser_version(),
        )

    def test_manual_attachment_refresh_selects_completed_duplicate_before_attachment_parse(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "进行中申请人",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {
                                                "fileId": "in-progress-file",
                                                "fileName": "进行中附件.pdf",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "已完成申请人",
                            "flowRequestId": "3002",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {
                                                "fileId": "completed-file",
                                                "fileName": "已完成附件.pdf",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            return_value={"evidences": [], "invoices": [], "artifacts": []},
        ) as parse_pool:
            records = adapter.refresh_application_record_attachments(["oa-exp-3002"])

        self.assertEqual([record.id for record in records], ["oa-exp-3002"])
        self.assertEqual(records[0].workflow_status, "completed")
        self.assertEqual(records[0].applicant, "已完成申请人")
        parse_pool.assert_called_once()
        parsed_files = parse_pool.call_args.args[0]
        self.assertEqual(
            [file_entry["fileName"] for file_entry in parsed_files],
            ["已完成附件.pdf"],
        )

    def test_manual_attachment_refresh_fails_closed_for_same_status_duplicate_before_parse(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": document_id,
                        "form_id": "32",
                        "modifiedTime": modified_time,
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "胡瑢",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": f"{document_id}.pdf"}]
                                    },
                                }
                            ],
                        },
                    }
                    for document_id, modified_time in (
                        ("expense-doc-progress-a", "2026-03-18T09:00:00"),
                        ("expense-doc-progress-b", "2026-03-18T10:00:00"),
                    )
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            side_effect=AssertionError("ambiguous source must fail before attachment parsing"),
        ) as parse_pool:
            with self.assertRaisesRegex(
                RuntimeError,
                "ambiguous workflow documents.*workflow_status=in_progress.*candidates=2",
            ):
                adapter.refresh_application_record_attachments(["oa-exp-3002"])

        parse_pool.assert_not_called()

    def test_manual_attachment_refresh_does_not_merge_different_expense_business_ids(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": f"expense-doc-{external_id}",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": external_id,
                            "flowRequestId": external_id,
                            "processStatus": process_status,
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": f"{external_id}.pdf"}]
                                    },
                                }
                            ],
                        },
                    }
                    for external_id, process_status in (
                        ("3002", "1"),
                        ("3003", "2"),
                    )
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            return_value={"evidences": [], "invoices": [], "artifacts": []},
        ) as parse_pool:
            records = adapter.refresh_application_record_attachments(
                ["oa-exp-3002", "oa-exp-3003"]
            )

        self.assertEqual([record.id for record in records], ["oa-exp-3002", "oa-exp-3003"])
        self.assertEqual(
            [record.workflow_status for record in records],
            ["in_progress", "completed"],
        )
        self.assertEqual(parse_pool.call_count, 2)

    def test_manual_attachment_refresh_does_not_parse_in_progress_payment_request(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-18",
                            "userName": "樊祖芳",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "flowRequestId": "2048",
                            "processStatus": "1",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            side_effect=AssertionError("payment request must not enter expense attachment parsing"),
        ) as parse_pool:
            records = adapter.refresh_application_record_attachments(["oa-pay-2048"])

        self.assertEqual([record.id for record in records], ["oa-pay-2048"])
        self.assertEqual(records[0].workflow_status, "in_progress")
        self.assertEqual(records[0].attachment_invoices, [])
        parse_pool.assert_not_called()

    def test_sync_batch_fails_closed_when_mongo_read_is_incomplete(self) -> None:
        adapter = FailingMongoOAAdapter()

        with self.assertRaisesRegex(RuntimeError, "OA Mongo source read failed"):
            adapter.load_sync_application_batch("2026-03")

    def test_payment_flow_identity_lookup_reads_only_configured_form_ids(self) -> None:
        existing_document = {
            "_id": "flow-existing",
            "form_id": "2",
            "data": {"flowRequestId": "business-1", "processStatus": "2"},
        }
        adapter = StubMongoOAAdapter(
            form_documents={"2": [existing_document]},
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_find_documents",
            side_effect=[[existing_document], []],
        ) as find_documents:
            found = adapter.list_existing_payment_flow_ids(
                ["flow-existing", "flow-missing", "flow-existing"]
            )

        self.assertEqual(found, {"flow-existing"})
        self.assertEqual(find_documents.call_count, 2)
        self.assertEqual(
            [call.args[0]["form_id"] for call in find_documents.call_args_list[:2]],
            [
                adapter._form_id_query_value(adapter._settings.payment_request_form_id),
                adapter._form_id_query_value(adapter._settings.expense_claim_form_id),
            ],
        )
        self.assertTrue(
            all("projection" not in call.kwargs for call in find_documents.call_args_list)
        )

    def test_payment_flow_identity_lookup_excludes_superseded_raw_document(self) -> None:
        superseded_document = {
            "_id": "flow-superseded",
            "form_id": "2",
            "data": {"flowRequestId": "business-1", "processStatus": "1"},
        }
        authoritative_document = {
            "_id": "flow-authoritative",
            "form_id": "2",
            "data": {"flowRequestId": "business-1", "processStatus": "2"},
        }
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [superseded_document, authoritative_document],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_find_documents",
            side_effect=[[superseded_document], []],
        ):
            found = adapter.list_existing_payment_flow_ids(["flow-superseded"])

        self.assertEqual(found, set())

    def test_payment_flow_identity_lookup_accepts_authoritative_business_id(self) -> None:
        authoritative_document = {
            "_id": "flow-authoritative",
            "form_id": "2",
            "data": {"flowRequestId": "business-1", "processStatus": "2"},
        }
        adapter = StubMongoOAAdapter(
            form_documents={"2": [authoritative_document]},
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_find_documents",
            side_effect=[[authoritative_document], []],
        ):
            found = adapter.list_existing_payment_flow_ids(["business-1"])

        self.assertEqual(found, {"business-1"})

    def test_sync_batch_admits_legitimate_in_progress_drafts_with_unfilled_business_fields(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-draft",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-20",
                            "processStatus": "1",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-draft",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-21",
                            "processStatus": "1",
                        },
                    }
                ],
            },
            project_documents=[],
        )
        adapter.set_import_settings_provider(
            lambda: {"form_types": ["payment_request", "expense_claim"], "statuses": ["completed"]}
        )

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_evidences",
            side_effect=AssertionError("draft without attachments must not invoke OCR"),
            create=True,
        ) as parse_evidences:
            batch = adapter.load_sync_application_batch("2026-03")

        self.assertEqual(batch.projection_records, ())
        self.assertEqual(
            [record.id for record in batch.admission_records],
            ["oa-exp-expense-draft", "oa-pay-payment-draft"],
        )
        for record in batch.admission_records:
            self.assertEqual(record.workflow_status, "in_progress")
            self.assertEqual(record.amount, "")
            self.assertEqual(record.applicant, "")
            self.assertEqual(record.attachment_evidences, [])
            self.assertEqual(record.attachment_artifacts, [])
            self.assertEqual(record.attachment_invoices, [])
        parse_evidences.assert_not_called()

    def test_sync_batch_still_fails_closed_for_completed_document_missing_required_business_fields(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-completed-invalid",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-20",
                            "processStatus": "2",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[],
        )

        with self.assertRaisesRegex(RuntimeError, "document failed required-field projection"):
            adapter.load_sync_application_batch("2026-03")

    def test_sync_batch_applies_all_scope_cutoff_before_completed_document_validation(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "historical-invalid-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2023-07-01",
                            "amount": "100",
                            "cause": "历史单据",
                            "processStatus": "2",
                        },
                    },
                    {
                        "_id": "retained-valid-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-20",
                            "userName": "张三",
                            "amount": "200",
                            "cause": "当期单据",
                            "processStatus": "2",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[],
        )

        batch = adapter.load_sync_application_batch(
            "all",
            retention_cutoff_month="2026-01",
        )

        self.assertEqual(
            [record.id for record in batch.projection_records],
            ["oa-pay-retained-valid-completed"],
        )
        self.assertEqual(
            [record.id for record in batch.admission_records],
            ["oa-pay-retained-valid-completed"],
        )
        self.assertEqual(
            batch.authoritative_payment_flow_ids,
            ("historical-invalid-completed", "retained-valid-completed"),
        )
        self.assertEqual(adapter.form_load_calls, [("2", None), ("32", None)])

    def test_full_sync_identity_set_includes_oa_from_projection_disabled_form(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-source-flow",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-20",
                            "userName": "张三",
                            "amount": "200",
                            "cause": "当期单据",
                            "processStatus": "2",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "disabled-expense-source-flow",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "李四",
                            "flowRequestId": "3002",
                            "processStatus": "2",
                            "schedule": [],
                        },
                    }
                ],
            },
            project_documents=[],
        )
        adapter.set_import_settings_provider(
            lambda: {"form_types": ["payment_request"], "statuses": ["completed"]}
        )

        batch = adapter.load_sync_application_batch("all")

        self.assertEqual([record.id for record in batch.projection_records], ["oa-pay-payment-source-flow"])
        self.assertEqual([record.id for record in batch.admission_records], ["oa-pay-payment-source-flow"])
        self.assertEqual(
            batch.authoritative_payment_flow_ids,
            ("3002", "disabled-expense-source-flow", "payment-source-flow"),
        )
        self.assertEqual(adapter.form_load_calls, [("2", None), ("32", None)])

    def test_sync_batch_arbitrates_completed_duplicate_before_all_scope_cutoff(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "进行中申请人",
                            "flowRequestId": "3002",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "进行中附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2025-12-18",
                            "Reimbursement Personnel": "已完成申请人",
                            "flowRequestId": "3002",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileName": "已完成附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            side_effect=AssertionError("cutoff must run after arbitration and before parsing"),
        ) as parse_pool:
            batch = adapter.load_sync_application_batch(
                "all",
                retention_cutoff_month="2026-01",
            )

        self.assertEqual(batch.projection_records, ())
        self.assertEqual(batch.admission_records, ())
        self.assertEqual(
            batch.authoritative_payment_flow_ids,
            ("3002", "expense-doc-completed"),
        )
        parse_pool.assert_not_called()

    def test_sync_batch_fails_closed_after_one_form_succeeds_and_the_next_form_fails(self) -> None:
        class PartialFailureAdapter(StubMongoOAAdapter):
            def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
                if str(form_id) == "32":
                    self._mongo_unavailable_until = float("inf")
                    return []
                return super()._load_form_documents(form_id, month)

        adapter = PartialFailureAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "amount": "199",
                            "beneficiary": "供应商 A",
                            "cause": "材料款",
                            "flowRequestId": "2047",
                            "processStatus": "2",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[],
        )

        with self.assertRaisesRegex(RuntimeError, "after expense_claim read"):
            adapter.load_sync_application_batch("2026-03")

    def test_sync_batch_keeps_completed_expense_attachment_processing(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "胡瑢",
                            "flowRequestId": "3003",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [{"fileId": "file-2", "fileName": "已完成附件.pdf"}]
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            return_value={"evidences": [], "invoices": [], "artifacts": []},
        ) as parse_pool:
            batch = adapter.load_sync_application_batch("2026-03")

        self.assertEqual([record.id for record in batch.projection_records], ["oa-exp-3003"])
        self.assertEqual([record.id for record in batch.admission_records], ["oa-exp-3003"])
        parse_pool.assert_called_once()

    def test_sync_batch_selects_completed_duplicate_before_attachment_parse(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "进行中申请人",
                            "flowRequestId": "3003",
                            "processStatus": "1",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {
                                                "fileId": "in-progress-file",
                                                "fileName": "进行中附件.pdf",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "已完成申请人",
                            "flowRequestId": "3003",
                            "processStatus": "2",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {
                                                "fileId": "completed-file",
                                                "fileName": "已完成附件.pdf",
                                            }
                                        ]
                                    },
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )

        with patch.object(
            adapter,
            "_parse_attachment_evidence_pool",
            return_value={"evidences": [], "invoices": [], "artifacts": []},
        ) as parse_pool:
            batch = adapter.load_sync_application_batch("2026-03")

        self.assertEqual([record.id for record in batch.projection_records], ["oa-exp-3003"])
        self.assertEqual([record.id for record in batch.admission_records], ["oa-exp-3003"])
        self.assertEqual(batch.projection_records[0].workflow_status, "completed")
        self.assertEqual(batch.projection_records[0].applicant, "已完成申请人")
        parse_pool.assert_called_once()
        self.assertEqual(
            [file_entry["fileName"] for file_entry in parse_pool.call_args.args[0]],
            ["已完成附件.pdf"],
        )

    def test_import_settings_filter_form_types_and_statuses(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "status": "已完成",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-completed",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "王五",
                            "titleName": "日常报销",
                            "flowRequestId": "3001",
                            "status": "已完成",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "停车费",
                                }
                            ],
                        },
                    },
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-19",
                            "Reimbursement Personnel": "赵六",
                            "titleName": "日常报销",
                            "flowRequestId": "3002",
                            "status": "进行中",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailReimbursementAmount": "99",
                                    "feeContent": "车费",
                                }
                            ],
                        },
                    },
                ],
            },
            project_documents=[],
        )
        adapter.set_import_settings_provider(
            lambda: {"form_types": ["expense_claim"], "statuses": ["completed", "in_progress"]}
        )

        records = adapter.list_application_records("2026-03")
        payment_documents = adapter.fetch_documents("payment_requests")
        expense_documents = adapter.fetch_documents("expense_claims")
        months = adapter.list_available_months()

        self.assertEqual([record.id for record in records], ["oa-exp-3001", "oa-exp-3002"])
        self.assertEqual(payment_documents, [])
        self.assertEqual([document["external_id"] for document in expense_documents], ["3001", "3002"])
        self.assertEqual(months, ["2026-03"])

    def test_list_application_records_by_row_ids_keeps_completed_and_in_progress_rows(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-completed",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "status": "已完成",
                        },
                    },
                    {
                        "_id": "payment-doc-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-18",
                            "userName": "樊祖芳",
                            "fromTitle": "支付申请",
                            "amount": "88050",
                            "beneficiary": "云南辰飞机电工程有限公司",
                            "cause": "空气源热泵预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2048",
                            "status": "进行中",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        records = adapter.list_application_records_by_row_ids(["oa-pay-2047", "oa-pay-2048"])

        self.assertEqual([record.id for record in records], ["oa-pay-2047", "oa-pay-2048"])
        self.assertEqual(
            {record.id: record.workflow_status for record in records},
            {"oa-pay-2047": "completed", "oa-pay-2048": "in_progress"},
        )

    def test_form_status_normalizes_real_mongo_completed_and_in_progress_values(self) -> None:
        self.assertEqual(MongoOAAdapter._form_status({"status": "APPROVED", "processStatus": "已完成"}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"status": "APPROVED", "processStatus": 2}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": "2"}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": "1"}), "进行中")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": "进行中"}), "进行中")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": 1}), "进行中")
        self.assertEqual(MongoOAAdapter.canonical_process_status({"processStatus": "1"}), "in_progress")
        self.assertEqual(MongoOAAdapter.canonical_process_status({"processStatus": "进行中"}), "in_progress")
        self.assertEqual(MongoOAAdapter.canonical_process_status({"processStatus": 1}), "in_progress")

    def test_list_application_records_projects_in_progress_workflow_status(self) -> None:
        adapter = StubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-in-progress",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "昆明供应商",
                            "cause": "材料预付款",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                            "processStatus": "1",
                        },
                    }
                ],
                "32": [
                    {
                        "_id": "expense-doc-in-progress",
                        "form_id": "32",
                        "data": {
                            "ApplicationDate": "2026-03-18",
                            "Reimbursement Personnel": "胡瑢",
                            "titleName": "日常报销",
                            "processId": "exp-progress-001",
                            "processStatus": "进行中",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "6486ca70cd6cae5d4e2b0b48",
                                    "detailReimbursementAmount": "88",
                                    "feeContent": "交通费",
                                }
                            ],
                        },
                    }
                ],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )
        adapter.set_import_filter_provider(
            lambda: {"form_types": ["payment_request", "expense_claim"], "statuses": ["completed", "in_progress"]}
        )

        records = adapter.list_application_records("2026-03")

        self.assertEqual(
            {record.id: record.workflow_status for record in records},
            {
                "oa-pay-2047": "in_progress",
                "oa-exp-exp-progress-001": "in_progress",
            },
        )
        self.assertTrue(all(record.completed_at is None for record in records))

    def test_list_application_records_uses_month_cache(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-1",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-16",
                            "userName": "刘际涛",
                            "fromTitle": "支付申请",
                            "amount": "199",
                            "beneficiary": "中国电信股份有限公司昆明分公司",
                            "cause": "托收电话费及宽带",
                            "projectName": "6486ca70cd6cae5d4e2b0b48",
                            "flowRequestId": "2047",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db", cache_ttl_seconds=30),
        )

        first_records = adapter.list_application_records("2026-03")
        second_records = adapter.list_application_records("2026-03")

        self.assertEqual([record.id for record in first_records], [record.id for record in second_records])
        self.assertEqual(adapter.form_load_calls.count(("2", "2026-03")), 1)
        self.assertEqual(adapter.form_load_calls.count(("32", "2026-03")), 1)

    def test_invalidate_records_cache_clears_only_target_month_and_all_snapshot(self) -> None:
        adapter = CountingStubMongoOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-mar",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-03-08",
                            "userName": "胡瑢",
                            "fromTitle": "支付申请",
                            "amount": "100",
                            "beneficiary": "供应商 A",
                            "cause": "三月付款",
                            "flowRequestId": "2047",
                        },
                    },
                    {
                        "_id": "payment-doc-apr",
                        "form_id": "2",
                        "data": {
                            "applicationDate": "2026-04-08",
                            "userName": "胡瑢",
                            "fromTitle": "支付申请",
                            "amount": "200",
                            "beneficiary": "供应商 B",
                            "cause": "四月付款",
                            "flowRequestId": "2048",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[],
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db", cache_ttl_seconds=30),
        )

        adapter.list_application_records("2026-03")
        adapter.list_application_records("2026-04")
        adapter.list_all_application_records()
        adapter.invalidate_records_cache(["2026-03"])
        adapter.list_application_records("2026-03")
        adapter.list_application_records("2026-04")
        adapter.list_all_application_records()

        self.assertEqual(adapter.form_load_calls.count(("2", "2026-03")), 2)
        self.assertEqual(adapter.form_load_calls.count(("2", "2026-04")), 1)
        self.assertEqual(adapter.form_load_calls.count(("2", None)), 2)

    def test_load_form_documents_pushes_month_filter_into_query(self) -> None:
        collection = QueryRecordingCollection()
        adapter = QueryRecordingMongoOAAdapter(collection)

        adapter._load_form_documents("2", "2026-03")

        self.assertEqual(len(collection.queries), 1)
        query = collection.queries[0]
        self.assertEqual(query["form_id"], {"$in": ["2", 2]})
        self.assertIn("$or", query)
        self.assertIn({"data.applicationDate": {"$regex": "^2026-03"}}, query["$or"])
        self.assertIn({"data.ApplicationDate": {"$regex": "^2026-03"}}, query["$or"])

    def test_list_available_months_retries_after_transient_query_failure(self) -> None:
        collection = FlakyMonthCollection()
        adapter = QueryRecordingMongoOAAdapter(collection)

        months = adapter.list_available_months()

        self.assertEqual(months, ["2026-03", "2026-04"])
        self.assertEqual(collection.call_count, 3)
        status = adapter.get_read_status()
        self.assertEqual(status.code, "ready")
        self.assertEqual(status.message, "OA 已同步")

    def test_list_available_months_uses_lightweight_projection(self) -> None:
        collection = QueryRecordingCollection()
        adapter = QueryRecordingMongoOAAdapter(collection)

        adapter.list_available_months()

        self.assertEqual(len(collection.projections), 2)
        for projection in collection.projections:
            self.assertEqual(
                projection,
                {
                    "data.applicationDate": 1,
                    "data.ApplicationDate": 1,
                    "data.status": 1,
                    "data.processStatus": 1,
                    "modifiedTime": 1,
                },
            )


if __name__ == "__main__":
    unittest.main()
