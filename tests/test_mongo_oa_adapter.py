import unittest
from unittest.mock import patch

from pymongo.errors import ServerSelectionTimeoutError

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings


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


class AttachmentStubMongoOAAdapter(StubMongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        attachment_invoice_rows: list[dict[str, str]],
        settings: MongoOASettings | None = None,
    ) -> None:
        super().__init__(form_documents=form_documents, project_documents=project_documents, settings=settings)
        self._attachment_invoice_rows = attachment_invoice_rows

    def _parse_attachment_invoices(self, files: list[dict[str, object]], *, month: str | None = None) -> list[dict[str, str]]:
        if not files:
            return []
        return [dict(row) for row in self._attachment_invoice_rows]


class QueryRecordingCollection:
    def __init__(self) -> None:
        self.queries: list[dict] = []
        self.projections: list[dict | None] = []

    def find(self, query: dict, projection: dict | None = None) -> list[dict]:
        self.queries.append(query)
        self.projections.append(dict(projection) if isinstance(projection, dict) else None)
        return []


class MutableDocumentCollection:
    def __init__(self, documents: list[dict]) -> None:
        self.documents = documents
        self.queries: list[dict] = []
        self.projections: list[dict | None] = []

    def find(self, query: dict, projection: dict | None = None) -> list[dict]:
        self.queries.append(query)
        self.projections.append(dict(projection) if isinstance(projection, dict) else None)
        form_query = query.get("form_id")
        allowed_form_ids = set(form_query.get("$in", [])) if isinstance(form_query, dict) else {form_query}
        return [
            dict(document)
            for document in self.documents
            if document.get("form_id") in allowed_form_ids
        ]


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

        self.assertEqual(len(records), 3)
        payment = next(record for record in records if record.id == "oa-pay-2047")
        self.assertEqual(payment.applicant, "刘际涛")
        self.assertEqual(payment.project_name, "云南溯源科技")
        self.assertEqual(payment.apply_type, "支付申请")
        self.assertEqual(payment.counterparty_name, "中国电信股份有限公司昆明分公司")
        self.assertEqual(payment.reason, "托收电话费及宽带")
        self.assertEqual(payment.detail_fields["收款账号"], "2502013009022108588")

        reimbursement = next(record for record in records if record.id == "oa-exp-exp-001-1")
        self.assertEqual(reimbursement.project_name, "玉烟维护项目")
        self.assertEqual(reimbursement.apply_type, "日常报销")
        self.assertEqual(reimbursement.amount, "12")
        self.assertEqual(reimbursement.reason, "工控机改标签邮寄费用")
        self.assertEqual(reimbursement.expense_type, "运费/邮费/杂费")
        self.assertEqual(reimbursement.expense_content, "工控机改标签邮寄费用")
        self.assertEqual(reimbursement.detail_fields["票据类型"], "Special_invoice")
        self.assertEqual(reimbursement.detail_fields["费用类型"], "运费/邮费/杂费")
        self.assertEqual(reimbursement.detail_fields["费用内容"], "工控机改标签邮寄费用")

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

    def test_list_application_records_applies_oa_import_form_type_and_status_filters(self) -> None:
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
        self.assertEqual(records[0].apply_type, "支付申请")
        self.assertEqual(adapter.form_load_calls, [("2", "2026-03")])

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

        self.assertEqual([record.id for record in records], ["oa-exp-exp-001-1", "oa-pay-2047"])
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
                            "reimbursementType": "withdraw_expense",
                            "schedule": [
                                {
                                    "row_index": 0,
                                    "detailProjectName": "yx-project",
                                    "detailReimbursementAmount": "135",
                                    "detailReimbursementType": "withdraw_expense",
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
            {
                "parser_version": adapter._attachment_invoice_cache_parser_version(),
                "invoices": [
                    {
                        "invoice_no": "40512344",
                        "seller_name": "云南顺丰速运有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2023-07-11",
                        "amount": "11.32",
                        "attachment_name": "invoice-a.pdf",
                    }
                ]
            },
        )

        with patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].attachment_invoices[0]["invoice_no"], "40512344")

    def test_expense_claim_normalizes_current_cache_entry_amount_to_net_amount(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
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
                                {
                                    "row_index": 0,
                                    "detailProjectName": "oa-project-001",
                                    "detailReimbursementAmount": "215.00",
                                    "feeContent": "设备费用",
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
        cache_key = adapter._attachment_invoice_cache_key(file_entry)
        cache.save_oa_attachment_invoice_cache_entry(
            cache_key,
            {
                "parser_version": adapter._attachment_invoice_cache_parser_version(),
                "invoices": [
                    {
                        "invoice_no": "25532000000191043884",
                        "seller_name": "玉溪市卓达自动化科技有限公司",
                        "buyer_name": "云南溯源科技有限公司",
                        "issue_date": "2025-12-26",
                        "amount": "215.00",
                        "net_amount": "212.86",
                        "tax_amount": "2.14",
                        "total_with_tax": "215.00",
                        "attachment_name": "invoice-a.pdf",
                    }
                ],
            },
        )

        with patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices[0]["amount"], "212.86")
        self.assertEqual(cache.entries[cache_key]["invoices"][0]["amount"], "212.86")

    def test_expense_claim_reparses_stale_attachment_invoice_cache_entry(self) -> None:
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

        with (
            patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")),
            patch.object(adapter, "_schedule_attachment_invoice_parse") as schedule_parse,
        ):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices, [])
        schedule_parse.assert_called_once()

    def test_expense_claim_schedules_background_attachment_parse_on_cache_miss(self) -> None:
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

        with (
            patch.object(adapter._attachment_invoice_service, "parse_files", side_effect=AssertionError("should not parse synchronously")),
            patch.object(adapter, "_schedule_attachment_invoice_parse") as schedule_parse,
        ):
            records = adapter.list_application_records("2026-03")

        self.assertEqual(records[0].attachment_invoices, [])
        schedule_parse.assert_called_once()

    def test_background_attachment_parse_saves_cache_and_notifies_month(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        notified_months: list[str] = []
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={"2": [], "32": []},
            project_documents=[],
            attachment_invoice_cache=cache,
        )
        adapter.set_attachment_invoice_cache_updated_callback(lambda months: notified_months.extend(months))
        cache_key = adapter._attachment_invoice_cache_key(file_entry)

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_files",
            return_value=[{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}],
        ):
            adapter._parse_attachment_invoice_files_in_background([(cache_key, file_entry)], month="2026-03")

        self.assertEqual(cache.entries[cache_key]["invoices"], [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}])
        self.assertEqual(cache.entries[cache_key]["parser_version"], adapter._attachment_invoice_cache_parser_version())
        self.assertEqual(notified_months, ["2026-03"])

    def test_sync_attachment_parse_saves_cache_without_background_notification(self) -> None:
        cache = MemoryAttachmentInvoiceCache()
        notified_months: list[str] = []
        file_entry = {"fileName": "invoice-a.pdf", "filePath": "/invoice-a.pdf", "suffix": "pdf"}
        adapter = StubMongoOAAdapter(
            form_documents={"2": [], "32": []},
            project_documents=[],
            attachment_invoice_cache=cache,
        )
        adapter.set_attachment_invoice_cache_updated_callback(lambda months: notified_months.extend(months))
        cache_key = adapter._attachment_invoice_cache_key(file_entry)

        with patch.object(
            adapter._attachment_invoice_service,
            "parse_files",
            return_value=[{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}],
        ):
            invoices = adapter._parse_attachment_invoice_files_now([(cache_key, file_entry)], month="2026-03")

        self.assertEqual(invoices, [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}])
        self.assertEqual(cache.entries[cache_key]["invoices"], [{"invoice_no": "40512344", "attachment_name": "invoice-a.pdf"}])
        self.assertEqual(cache.entries[cache_key]["parser_version"], adapter._attachment_invoice_cache_parser_version())
        self.assertEqual(notified_months, [])

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

    def test_only_completed_oa_rows_are_returned(self) -> None:
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
        documents = adapter.fetch_documents("payment_requests")
        months = adapter.list_available_months()

        self.assertEqual([record.id for record in records], ["oa-pay-2047"])
        self.assertEqual([document["external_id"] for document in documents], ["2047"])
        self.assertEqual(months, ["2026-03"])

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

        self.assertEqual([record.id for record in records], ["oa-exp-3001-0", "oa-exp-3002-0"])
        self.assertEqual(payment_documents, [])
        self.assertEqual([document["external_id"] for document in expense_documents], ["3001", "3002"])
        self.assertEqual(months, ["2026-03"])

    def test_list_application_records_by_row_ids_skips_non_completed_rows(self) -> None:
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

        self.assertEqual([record.id for record in records], ["oa-pay-2047"])

    def test_form_status_normalizes_real_mongo_completed_and_in_progress_values(self) -> None:
        self.assertEqual(MongoOAAdapter._form_status({"status": "APPROVED", "processStatus": "已完成"}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"status": "APPROVED", "processStatus": 2}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": "2"}), "已完成")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": "进行中"}), "进行中")
        self.assertEqual(MongoOAAdapter._form_status({"processStatus": 1}), "进行中")

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

    def test_poll_sync_fingerprints_hashes_enabled_oa_documents_by_month_and_all(self) -> None:
        collection = MutableDocumentCollection(
            [
                {
                    "_id": "pay-1",
                    "form_id": "2",
                    "modifiedTime": "2026-03-18T10:00:00",
                    "data": {
                        "applicationDate": "2026-03-18",
                        "amount": "100",
                        "beneficiary": "供应商 A",
                        "cause": "三月付款",
                        "flowRequestId": "1001",
                        "status": "已完成",
                    },
                },
                {
                    "_id": "exp-1",
                    "form_id": "32",
                    "modifiedTime": "2026-04-02T10:00:00",
                    "data": {
                        "ApplicationDate": "2026-04-02",
                        "Amount": "200",
                        "Reimbursement Personnel": "张三",
                        "flowRequestId": "2001",
                        "status": "已完成",
                    },
                },
            ]
        )
        adapter = QueryRecordingMongoOAAdapter(collection)

        first = adapter.poll_sync_fingerprints()
        collection.documents[0]["data"]["amount"] = "101"
        second = adapter.poll_sync_fingerprints()

        self.assertCountEqual(first.keys(), ["2026-03", "2026-04", "all"])
        self.assertEqual(first["2026-04"], second["2026-04"])
        self.assertNotEqual(first["2026-03"], second["2026-03"])
        self.assertNotEqual(first["all"], second["all"])
        self.assertEqual(len(collection.projections), 4)
        for projection in collection.projections:
            self.assertIn("data", projection)
            self.assertIn("modifiedTime", projection)

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
