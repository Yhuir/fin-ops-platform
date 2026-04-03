import unittest

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings


class StubMongoOAAdapter(MongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict],
        settings: MongoOASettings | None = None,
    ) -> None:
        super().__init__(settings=settings or MongoOASettings(host="127.0.0.1", database="form_data_db"))
        self._form_documents = form_documents
        self._project_documents = project_documents

    def _load_form_documents(self, form_id: str, month: str | None = None) -> list[dict]:
        documents = list(self._form_documents.get(str(form_id), []))
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


class QueryRecordingCollection:
    def __init__(self) -> None:
        self.queries: list[dict] = []

    def find(self, query: dict) -> list[dict]:
        self.queries.append(query)
        return []


class QueryRecordingMongoOAAdapter(MongoOAAdapter):
    def __init__(self, collection: QueryRecordingCollection, *, settings: MongoOASettings | None = None) -> None:
        super().__init__(settings=settings or MongoOASettings(host="127.0.0.1", database="form_data_db"))
        self._query_collection = collection

    def _collection(self):
        return self._query_collection


class MongoOAAdapterTests(unittest.TestCase):
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
                            "status": "APPROVED",
                            "processStatus": 2,
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
                            "status": "APPROVED",
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

    def test_load_form_documents_pushes_month_filter_into_query(self) -> None:
        collection = QueryRecordingCollection()
        adapter = QueryRecordingMongoOAAdapter(collection)

        adapter._load_form_documents("2", "2026-03")

        self.assertEqual(len(collection.queries), 1)
        query = collection.queries[0]
        self.assertEqual(query["form_id"], "2")
        self.assertIn("$or", query)
        self.assertIn({"data.applicationDate": {"$regex": "^2026-03"}}, query["$or"])
        self.assertIn({"data.ApplicationDate": {"$regex": "^2026-03"}}, query["$or"])


if __name__ == "__main__":
    unittest.main()
