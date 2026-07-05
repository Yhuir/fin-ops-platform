import json
import os
import pickle
import tempfile
import unittest
from contextlib import contextmanager
from io import BytesIO
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread
from unittest.mock import patch
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from pymongo.errors import ServerSelectionTimeoutError
from openpyxl import load_workbook

from fin_ops_platform.app.server import (
    Application,
    SYSTEM_AUTO_PAIR_RELATION_MODES,
    WORKBENCH_READ_MODEL_SCHEMA_VERSION,
    _build_handler_factory,
)
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.services.bank_details_export_service import BANK_DETAIL_EXPORT_ROW_LIMIT
from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.oa_adapter import InMemoryOAAdapter, OAApplicationRecord
from fin_ops_platform.services.settings_data_reset_service import RESET_OA_AND_REBUILD_ACTION
from fin_ops_platform.services.workbench_candidate_match_service import (
    CANDIDATE_MATCH_SCHEMA_VERSION,
    WorkbenchCandidateMatchService,
)
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WorkbenchDecision,
)
from fin_ops_platform.services.etc_service import UploadedEtcZipFile
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from tests.test_etc_backend import etc_zip
from tests.mock_import_files import INVOICE_JAN


class FailingMongoWorkbenchOAAdapter(MongoOAAdapter):
    def __init__(self) -> None:
        super().__init__(settings=MongoOASettings(host="127.0.0.1", database="form_data_db"))

    def _collection(self):
        raise ServerSelectionTimeoutError("mock mongo unavailable")


class MemoryAttachmentInvoiceCache:
    def __init__(self) -> None:
        self.entries: dict[str, dict[str, object]] = {}

    def load_oa_attachment_invoice_cache_entry(self, cache_key: str) -> dict[str, object] | None:
        return self.entries.get(cache_key)

    def save_oa_attachment_invoice_cache_entry(self, cache_key: str, payload: dict[str, object]) -> None:
        self.entries[cache_key] = dict(payload)


def workbench_reconciliation_decision(key: str, *, scope_month: str, row_ids: tuple[str, ...]) -> WorkbenchDecision:
    return WorkbenchDecision(
        decision_id=key,
        decision_key=key,
        scope_month=scope_month,
        display_state=DISPLAY_STATE_PAIRED,
        decision_status=DECISION_STATUS_PAIRED,
        match_domain=MATCH_DOMAIN_FREE,
        match_shape="oa_bank_invoice",
        rule_code="free.test",
        rule_version="test",
        row_ids=row_ids,
        oa_row_ids=tuple(row_id for row_id in row_ids if str(row_id).startswith("oa-")),
        bank_row_ids=tuple(row_id for row_id in row_ids if str(row_id).startswith("bk-") or str(row_id).startswith("bank-")),
        invoice_row_ids=tuple(row_id for row_id in row_ids if str(row_id).startswith("iv-") or str(row_id).startswith("invoice-")),
        amount="100.00",
        direction="expense",
        payment_amount_closed=True,
        invoice_amount_closed=True,
        source_versions={"rules": "v1"},
    )


class WorkbenchSystemAutoPairModePolicyTests(unittest.TestCase):
    def test_salary_and_internal_transfer_are_not_system_auto_pair_relation_modes(self) -> None:
        self.assertNotIn("salary_personal_auto_match", SYSTEM_AUTO_PAIR_RELATION_MODES)
        self.assertNotIn("internal_transfer_pair", SYSTEM_AUTO_PAIR_RELATION_MODES)
        self.assertIn("bank_flow_rule_batch", SYSTEM_AUTO_PAIR_RELATION_MODES)
        self.assertIn("oa_invoice_offset_auto_match", SYSTEM_AUTO_PAIR_RELATION_MODES)


class StaticMongoWorkbenchOAAdapter(MongoOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict] | None = None,
        attachment_invoice_cache: MemoryAttachmentInvoiceCache | None = None,
    ) -> None:
        super().__init__(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db"),
            attachment_invoice_cache=attachment_invoice_cache,
        )
        self._form_documents = form_documents
        self._project_documents = project_documents or []

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
        normalized_external_ids = {str(external_id).strip() for external_id in external_ids if str(external_id).strip()}
        return [
            document
            for document in documents
            if self._document_external_id(form_id, document) in normalized_external_ids
        ]

    @staticmethod
    def _with_default_completed_status(document: dict) -> dict:
        normalized = dict(document)
        data = dict(normalized.get("data", {}))
        if "status" not in data or data.get("status") in (None, ""):
            data["status"] = "已完成"
        normalized["data"] = data
        return normalized


class RetentionScopedMongoWorkbenchOAAdapter(StaticMongoWorkbenchOAAdapter):
    def __init__(
        self,
        *,
        form_documents: dict[str, list[dict]],
        project_documents: list[dict] | None = None,
        attachment_invoice_cache: MemoryAttachmentInvoiceCache | None = None,
        row_id_records: dict[str, list[OAApplicationRecord]] | None = None,
    ) -> None:
        super().__init__(
            form_documents=form_documents,
            project_documents=project_documents,
            attachment_invoice_cache=attachment_invoice_cache,
        )
        self.month_calls: list[str] = []
        self.bulk_call_count = 0
        self.row_id_calls: list[list[str]] = []
        self._row_id_records = row_id_records or {}

    def list_available_months(self) -> list[str]:
        months: set[str] = set()
        for documents in self._form_documents.values():
            for document in documents:
                data = self._with_default_completed_status(document).get("data", {})
                application_date = str(data.get("applicationDate") or data.get("ApplicationDate") or "")
                if len(application_date) >= 7:
                    months.add(application_date[:7])
        return sorted(months)

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        self.month_calls.append(month)
        return super().list_application_records(month)

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        self.bulk_call_count += 1
        raise AssertionError("should not bulk scan all OA records")

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized = [str(row_id) for row_id in row_ids]
        self.row_id_calls.append(normalized)
        records: list[OAApplicationRecord] = []
        for row_id in normalized:
            records.extend(self._row_id_records.get(row_id, []))
        return records


class ErrorMonthListRetentionMongoWorkbenchOAAdapter(RetentionScopedMongoWorkbenchOAAdapter):
    def list_available_months(self) -> list[str]:
        self._set_read_status("error", "OA 连接失败")
        return []


class MutatingRecordDict(dict):
    def values(self):
        values_iterator = super().values()
        did_mutate = False
        for row in values_iterator:
            if not did_mutate:
                self["oa-mutated-during-iteration"] = {
                    "id": "oa-mutated-during-iteration",
                    "type": "oa",
                    "_month": "2026-01",
                    "_section": "open",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                }
                did_mutate = True
            yield row


class RelationDistributionFacadeStub:
    def __init__(self, rows: list[dict[str, object]] | None = None) -> None:
        self.rows = list(rows or [])
        self.calls: list[dict[str, object]] = []

    def set_rows(self, rows: list[dict[str, object]]) -> None:
        self.rows = list(rows)

    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        wanted = {str(row_id) for row_id in row_ids}
        self.calls.append({"row_ids": list(row_ids), "kwargs": dict(kwargs)})
        return {
            "status": "fresh",
            "rows": [dict(row) for row in self.rows if str(row.get("row_id") or "") in wanted],
            "groups": [],
            "source_versions": {"schema_version": "test"},
            "read_model_scope_keys": ["2026-03", "2026-04", "2026-05"],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }


class BankDetailReadModelFixture:
    def __init__(self, app: Application) -> None:
        self._app = app

    def bank_detail_scope_keys_for_range(self, *, date_from: str | None = None, date_to: str | None = None) -> list[str]:
        months: set[str] = set()
        start_month = str(date_from or "")[:7]
        end_month = str(date_to or "")[:7]
        for transaction in self._app._import_service.list_transactions(month="all"):
            month = str(getattr(transaction, "txn_date", "") or getattr(transaction, "trade_time", "") or "")[:7]
            if len(month) != 7:
                continue
            if start_month and month < start_month:
                continue
            if end_month and month > end_month:
                continue
            months.add(month)
        return sorted(months) or ["all"]

    def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
        return {
            "read_model_status": "fresh",
            "read_model_scope_keys": list(scope_keys),
            "read_model_generated_at": "2026-07-05T00:00:00+00:00",
            "read_model_scope_signatures": {},
        }

    def list_bank_detail_transactions(self, **kwargs: object) -> dict[str, object]:
        payload = self._app._bank_details_service.list_transactions(**kwargs)
        return {
            **payload,
            "read_model_status": "fresh",
            "read_model_scope_keys": self.bank_detail_scope_keys_for_range(
                date_from=kwargs.get("date_from") if isinstance(kwargs.get("date_from"), str) else None,
                date_to=kwargs.get("date_to") if isinstance(kwargs.get("date_to"), str) else None,
            ),
            "read_model_generated_at": "2026-07-05T00:00:00+00:00",
        }

    def list_bank_detail_accounts(self, *, date_from: str | None = None, date_to: str | None = None) -> dict[str, object]:
        payload = self._app._bank_details_service.list_accounts(date_from=date_from, date_to=date_to)
        return {
            **payload,
            "read_model_status": "fresh",
            "read_model_scope_keys": self.bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to),
            "read_model_generated_at": "2026-07-05T00:00:00+00:00",
        }

    def list_bank_account_balances(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, object]:
        del tenant_id
        payload = self._app._bank_details_service.list_accounts(date_from=date_from, date_to=date_to)
        return {
            **payload,
            "read_model_status": "fresh",
            "balance_read_model_status": "fresh",
            "read_model_scope_keys": self.bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to),
            "read_model_generated_at": "2026-07-05T00:00:00+00:00",
        }


class WorkbenchV2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def _install_workbench_query_service(self, app: Application, query_service: WorkbenchQueryService) -> None:
        app._workbench_query_service = query_service
        app._workbench_api_routes = WorkbenchApiRoutes(query_service)
        app._invalidate_workbench_read_models(invalidate_cost_statistics=False)

    def _create_imported_bank_transaction(
        self,
        app: Application,
        *,
        trade_time: str = "2026-04-03 09:00:00",
        counterparty_name: str = "供应商A",
        summary: str = "付款",
        remark: str = "货款",
    ) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank.xlsx",
            imported_by="YNSYLP005",
            rows=[
                {
                    "account_no": "6222000011116386",
                    "account_name": "云南溯源科技有限公司基本户",
                    "txn_date": trade_time[:10],
                    "trade_time": trade_time,
                    "pay_receive_time": trade_time,
                    "counterparty_name": counterparty_name,
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "summary": summary,
                    "remark": remark,
                    "selected_bank_name": "工商银行",
                    "selected_bank_last4": "6386",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        return app._import_service.list_transactions()[-1].id

    def _install_bank_relation_distribution(
        self,
        app: Application,
        rows: list[dict[str, object]],
    ) -> RelationDistributionFacadeStub:
        facade = RelationDistributionFacadeStub(rows)
        app._bank_details_relation_tag_projection_service._relation_facade = facade
        return facade

    def _install_bank_detail_read_model_fixture(self, app: Application) -> BankDetailReadModelFixture:
        repository = BankDetailReadModelFixture(app)
        app._bank_detail_sql_read_repository = repository
        app._bank_account_balance_sql_read_repository = repository
        return repository

    def test_application_restores_workbench_candidate_match_service_from_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            candidate_key = WorkbenchCandidateMatchService.build_candidate_key(
                scope_month="2026-05",
                rule_code="same_amount",
                row_ids=["bank-001", "invoice-001", "oa-001"],
            )
            candidate = {
                "candidate_id": candidate_key,
                "candidate_key": candidate_key,
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "scope_month": "2026-05",
                "candidate_type": "oa_bank_invoice",
                "status": "needs_review",
                "confidence": "medium",
                "rule_code": "same_amount",
                "row_ids": ["bank-001", "invoice-001", "oa-001"],
                "oa_row_ids": ["oa-001"],
                "bank_row_ids": ["bank-001"],
                "invoice_row_ids": ["invoice-001"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "persisted candidate",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-06T10:00:00+00:00",
                "source_versions": {},
                "tags": [],
                "special_metadata": {},
                "consumed_by_case_id": "",
                "consumed_by_relation_case_id": "",
                "suppressed_reason": "",
                "exception_preview": {},
            }
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump({"workbench_candidate_matches": {"candidates": {candidate_key: candidate}}}, handle)

            app = build_application(data_dir=data_dir, bootstrap_mode="legacy")

        self.assertEqual(
            app._workbench_candidate_match_service.list_candidates_by_month("2026-05"),
            [candidate],
        )

    def test_application_loads_state_without_workbench_candidate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump({"imports": {}, "file_imports": {}, "matching": {}}, handle)

            app = build_application(data_dir=data_dir)

        self.assertEqual(
            app._workbench_candidate_match_service.snapshot(),
            {"schema_version": CANDIDATE_MATCH_SCHEMA_VERSION, "candidates": {}, "scope_runs": {}},
        )

    def test_patch_bank_transaction_categories_is_disabled_and_does_not_mutate_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(app)
            app._workbench_read_model_service.upsert_read_model(scope_key="all", payload={"month": "all"})
            app._workbench_candidate_match_service.upsert_candidate(
                {
                    "scope_month": "2026-04",
                    "candidate_type": "bank",
                    "status": "needs_review",
                    "confidence": "low",
                    "rule_code": "no_confident_match",
                    "row_ids": [transaction_id],
                    "bank_row_ids": [transaction_id],
                    "oa_row_ids": [],
                    "invoice_row_ids": [],
                    "amount": "100.00",
                    "amount_delta": "100.00",
                    "explanation": "stale candidate",
                    "conflict_candidate_keys": [],
                    "generated_at": "2026-04-03T00:00:00+00:00",
                    "source_versions": {},
                }
            )

            response = app.handle_request(
                "PATCH",
                "/api/bank-details/transactions/categories",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_id,
                                "category_code": "borrow_in_company_pending_repayment",
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )
            payload = json.loads(response.body)

            self.assertEqual(response.status_code, 410)
            self.assertEqual(payload["error"], "manual_bank_transaction_category_disabled")
            self.assertEqual(app._bank_transaction_category_service.snapshot()["categories"], {})
            self.assertEqual(app._state_store.load_bank_transaction_categories().get("categories", {}), {})
            self.assertEqual(app._workbench_read_model_service.get_read_model("all")["payload"], {"month": "all"})
            self.assertEqual(len(app._workbench_candidate_match_service.list_candidates_by_month("2026-04")), 1)

    def test_http_server_dispatches_patch_bank_transaction_categories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(app)
            server = ThreadingHTTPServer(("127.0.0.1", 0), _build_handler_factory(app))
            thread = Thread(target=server.serve_forever, daemon=True)
            thread.start()
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            try:
                connection.request(
                    "PATCH",
                    "/api/bank-details/transactions/categories",
                    body=json.dumps(
                        {
                            "updates": [
                                {
                                    "transaction_id": transaction_id,
                                    "category_code": "borrow_in_company_pending_repayment",
                                    "expected_version": 0,
                                }
                            ]
                        }
                    ),
                    headers={"Content-Type": "application/json"},
                )
                response = connection.getresponse()
                response_body = response.read().decode("utf-8")
            finally:
                connection.close()
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

        self.assertEqual(response.status, 410)
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")
        payload = json.loads(response_body)
        self.assertEqual(payload["error"], "manual_bank_transaction_category_disabled")

    def test_bank_details_api_returns_auto_and_effective_category_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-03 09:15:30",
                summary="网银手续费",
                remark="转账手续费",
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions?account_key=%E5%B7%A5%E5%95%86%E9%93%B6%E8%A1%8C%3A6386",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        row = next(row for row in payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(row["trade_time"], "2026-04-03 09:15:30")
        self.assertEqual(row["auto_category_code"], "fee")
        self.assertEqual(row["auto_category_label"], "手续费")
        self.assertEqual(row["auto_category_primary_label"], "费用")
        self.assertEqual(row["auto_category_sub_label"], "手续费")
        self.assertEqual(row["auto_category_label_path"], ["费用", "手续费"])
        self.assertEqual(row["auto_category_source"], "auto")
        self.assertEqual(row["effective_category_code"], "fee")
        self.assertEqual(row["effective_category_label"], "手续费")
        self.assertEqual(row["effective_category_primary_label"], "费用")
        self.assertEqual(row["effective_category_sub_label"], "手续费")
        self.assertEqual(row["effective_category_label_path"], ["费用", "手续费"])
        self.assertEqual(row["effective_category_source"], "auto")
        self.assertEqual(row["category_code"], "fee")
        self.assertEqual(row["category_label"], "手续费")
        self.assertEqual(row["category_primary_label"], "费用")
        self.assertEqual(row["category_sub_label"], "手续费")
        self.assertEqual(row["category_label_path"], ["费用", "手续费"])
        self.assertEqual(row["category_source"], "auto")
        self.assertEqual(payload["category_counts"]["fee"], 1)

    def test_bank_details_api_filters_by_auto_category_primary_and_sub_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            fee_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-03 09:15:30",
                summary="网银手续费",
                remark="转账手续费",
            )
            self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-02 09:15:30",
                summary="工资发放",
                remark="员工工资",
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions"
                "?category_primary_label=%E8%B4%B9%E7%94%A8"
                "&category_sub_label=%E6%89%8B%E7%BB%AD%E8%B4%B9",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["rows"]], [fee_id])
        self.assertEqual(payload["pagination"]["total"], 1)

    def test_bank_details_api_filters_uncategorized_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            uncategorized_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-03 09:15:30",
                summary="普通付款",
                remark="普通用途",
            )
            self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-02 09:15:30",
                summary="网银手续费",
                remark="转账手续费",
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions?category_code=uncategorized",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["rows"]], [uncategorized_id])
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)
        self.assertEqual(payload["category_counts"]["fee"], 0)

    def test_bank_details_api_passes_keyword_to_server_side_transaction_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-03 09:00:00",
                counterparty_name="普通供应商A",
                summary="普通付款",
                remark="普通用途",
            )
            self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-02 09:00:00",
                counterparty_name="普通供应商B",
                summary="普通付款",
                remark="普通用途",
            )
            target_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-01 09:00:00",
                counterparty_name="跨页目标供应商",
                summary="网银手续费",
                remark="跨页目标用途",
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions"
                "?account_key=%E5%B7%A5%E5%95%86%E9%93%B6%E8%A1%8C%3A6386"
                "&date_from=2026-04-01"
                "&date_to=2026-04-30"
                "&page=1"
                "&page_size=2"
                "&keyword=%E8%B7%A8%E9%A1%B5%E7%9B%AE%E6%A0%87",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual([row["id"] for row in payload["rows"]], [target_id])
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["category_counts"]["fee"], 1)
        self.assertEqual(payload["category_counts"]["uncategorized"], 0)

    def test_bank_details_export_api_returns_xlsx_and_records_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-04-16 11:09:14+08:00",
                counterparty_name="云南溯源科技有限公司",
                summary="网银手续费",
                remark="工行附言",
            )
            facade = self._install_bank_relation_distribution(
                app,
                [
                    {
                        "row_id": transaction_id,
                        "row_type": "bank_transaction",
                        "group_ids": ["CASE-BANK-DETAIL-EXPORT"],
                        "linked_oa": [{"id": "oa-export"}],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    }
                ],
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions/export"
                "?mode=all"
                "&date_from=2026-04-01"
                "&date_to=2026-05-18"
                "&keyword=%E6%BA%AF%E6%BA%90",
            )
            workbook = load_workbook(BytesIO(response.body))
            audit_entries = app._audit_service.as_dicts()

        self.assertEqual(response.status_code, 200, response.body)
        self.assertIn("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", response.headers["Content-Type"])
        self.assertIn("filename*=UTF-8''", response.headers["Content-Disposition"])
        self.assertEqual(workbook.sheetnames, ["全部流水", "工商银行"])
        sheet = workbook["全部流水"]
        self.assertEqual(sheet["A2"].value, "2026-04-16 11:09:14")
        self.assertEqual(sheet["D2"].value, "云南溯源科技有限公司")
        self.assertEqual(sheet["I2"].value, "手续费")
        self.assertEqual(sheet["J2"].value, "费用")
        self.assertEqual(sheet["K2"].value, "手续费")
        self.assertEqual(sheet["M2"].value, "有oa")
        self.assertEqual(sheet["N2"].value, "无发票")
        self.assertEqual(sheet["Q2"].value, "工行附言")
        self.assertEqual(sheet["R2"].value, transaction_id)
        self.assertEqual(facade.calls[0]["kwargs"]["reason"], "bank_details_relation_tag_projection")
        self.assertEqual(audit_entries[-1]["action"], "bank_detail_export_downloaded")
        self.assertEqual(audit_entries[-1]["entity_type"], "bank_detail_export")
        self.assertEqual(audit_entries[-1]["metadata"]["row_count"], 1)
        self.assertEqual(audit_entries[-1]["metadata"]["filters"]["keyword"], "溯源")

    def test_bank_details_export_api_validates_account_mode_and_row_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            repository = self._install_bank_detail_read_model_fixture(app)
            missing_account_response = app.handle_request(
                "GET",
                "/api/bank-details/transactions/export?mode=account",
            )
            with patch.object(
                repository,
                "list_bank_detail_transactions",
                return_value={
                    "rows": [],
                    "pagination": {"page": 1, "page_size": 100, "total": BANK_DETAIL_EXPORT_ROW_LIMIT + 1},
                    "read_model_status": "fresh",
                    "category_counts": {"uncategorized": 0},
                },
            ):
                row_limit_response = app.handle_request(
                    "GET",
                    "/api/bank-details/transactions/export?mode=all",
                )

        self.assertEqual(missing_account_response.status_code, 400)
        self.assertEqual(json.loads(missing_account_response.body)["error"], "bank_detail_export_account_required")
        self.assertEqual(row_limit_response.status_code, 400)
        self.assertEqual(json.loads(row_limit_response.body)["error"], "bank_detail_export_row_limit_exceeded")

    def test_bank_details_export_api_uses_sql_read_model_refresh_contract_in_sql_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            class FakeBankDetailSqlReadRepository:
                def __init__(self) -> None:
                    self.called = False

                def bank_detail_scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
                    return ["2026-04", "2026-05"]

                def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
                    return {
                        "read_model_status": "refreshing",
                        "read_model_scope_keys": list(scope_keys),
                        "read_model_generated_at": None,
                        "read_model_scope_signatures": {},
                    }

                def list_bank_detail_transactions(self, **_kwargs: object) -> dict[str, object]:
                    self.called = True
                    return {
                        "account_key": None,
                        "date_from": "2026-04-01",
                        "date_to": "2026-05-18",
                        "rows": [],
                        "category_counts": {"uncategorized": 0},
                        "pagination": {"page": 1, "page_size": 100, "total": 0},
                        "read_model_status": "refreshing",
                        "cache_status": "bypass",
                    }

            sql_repository = FakeBankDetailSqlReadRepository()
            with (
                patch.object(app, "_requires_sql_read_model_runtime", return_value=True),
                patch.object(app, "_bank_detail_sql_read_repository", sql_repository),
                patch.object(app._bank_details_service, "list_transactions", side_effect=AssertionError("export should not bypass SQL read model")),
            ):
                response = app.handle_request(
                    "GET",
                    "/api/bank-details/transactions/export?mode=all&date_from=2026-04-01&date_to=2026-05-18",
                )
            audit_entries = app._audit_service.as_dicts()

        self.assertEqual(response.status_code, 202)
        self.assertEqual(json.loads(response.body)["read_model_status"], "refreshing")
        self.assertTrue(sql_repository.called)
        self.assertFalse(any(entry["action"] == "bank_detail_export_downloaded" for entry in audit_entries))

    def test_bank_details_api_projects_workbench_relation_tags(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-05-02 09:00:00",
                summary="付款",
                remark="项目款",
            )
            facade = self._install_bank_relation_distribution(
                app,
                [
                    {
                        "row_id": transaction_id,
                        "row_type": "bank_transaction",
                        "group_ids": ["CASE-BANK-DETAILS"],
                        "linked_oa": [{"id": "oa-bank-details-001"}],
                        "linked_input_invoices": [{"id": "iv-bank-details-001"}],
                        "linked_output_invoices": [],
                    }
                ],
            )
            self._install_bank_detail_read_model_fixture(app)
            with patch.object(app, "_get_or_build_workbench_read_model", side_effect=AssertionError("should not rebuild read model")):
                linked_response = app.handle_request(
                    "GET",
                    "/api/bank-details/transactions?account_key=%E5%B7%A5%E5%95%86%E9%93%B6%E8%A1%8C%3A6386",
                )
            facade.set_rows(
                [
                    {
                        "row_id": transaction_id,
                        "row_type": "bank_transaction",
                        "group_ids": [],
                        "linked_oa": [],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    }
                ]
            )
            app._bank_details_relation_tag_projection_service.clear_cache()
            with patch.object(app, "_get_or_build_workbench_read_model", side_effect=AssertionError("should not rebuild read model")):
                unlinked_response = app.handle_request(
                    "GET",
                    "/api/bank-details/transactions?account_key=%E5%B7%A5%E5%95%86%E9%93%B6%E8%A1%8C%3A6386",
            )
            app.shutdown_background_jobs()

        self.assertEqual(linked_response.status_code, 200, linked_response.body)
        linked_payload = json.loads(linked_response.body)
        linked_row = next(row for row in linked_payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(linked_row["oa_relation_tag"], "有oa")
        self.assertEqual(linked_row["invoice_relation_tag"], "有发票")
        self.assertEqual(linked_row["relation_tags"], ["有oa", "有发票"])
        self.assertEqual(linked_row["relation_case_id"], "CASE-BANK-DETAILS")
        self.assertEqual(facade.calls[0]["kwargs"]["reason"], "bank_details_relation_tag_projection")

        self.assertEqual(unlinked_response.status_code, 200, unlinked_response.body)
        unlinked_payload = json.loads(unlinked_response.body)
        unlinked_row = next(row for row in unlinked_payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(unlinked_row["oa_relation_tag"], "无oa")
        self.assertEqual(unlinked_row["invoice_relation_tag"], "无发票")
        self.assertEqual(unlinked_row["relation_tags"], ["无oa", "无发票"])
        self.assertNotIn("relation_case_id", unlinked_row)

    def test_bank_details_api_projects_candidate_oa_without_invoice_tags_across_months(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-03-12 10:16:38",
                summary="电子转账",
                remark="汽油费",
            )
            candidate = app._workbench_candidate_match_service.upsert_candidate(
                {
                    "scope_month": "2026-02",
                    "candidate_type": "oa_bank",
                    "status": "incomplete",
                    "confidence": "medium",
                    "rule_code": "oa_bank_exact_amount",
                    "row_ids": ["oa-pay-fuel-001", transaction_id],
                    "oa_row_ids": ["oa-pay-fuel-001"],
                    "bank_row_ids": [transaction_id],
                    "invoice_row_ids": [],
                    "amount": "1500.00",
                    "amount_delta": "0.00",
                    "explanation": "OA and bank matched; invoice evidence is missing.",
                    "conflict_candidate_keys": [],
                    "generated_at": "2026-05-07T00:00:00+00:00",
                    "source_versions": {},
                }
            )
            self._install_bank_detail_read_model_fixture(app)

            response = app.handle_request(
                "GET",
                "/api/bank-details/transactions?date_from=2026-03-12&date_to=2026-03-12&page_size=500",
            )

        self.assertEqual(response.status_code, 200, response.body)
        payload = json.loads(response.body)
        row = next(row for row in payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(candidate["bank_row_ids"], [transaction_id])
        self.assertEqual(row["oa_relation_tag"], "无oa")
        self.assertEqual(row["invoice_relation_tag"], "无发票")
        self.assertEqual(row["relation_tags"], ["无oa", "无发票"])
        self.assertNotIn("relation_case_id", row)

    def test_bank_details_api_ignores_raw_workbench_group_relation_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                trade_time="2026-03-12 10:16:38",
                summary="电子转账",
                remark="汽油费",
            )
            candidate_case_id = "candidate:fuel-oa-bank"
            raw_payload = {
                "month": "all",
                "summary": {},
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {
                            "id": "oa-pay-fuel-001",
                            "type": "oa",
                            "case_id": None,
                            "apply_type": "支付申请",
                            "amount": "100.00",
                            "counterparty_name": "供应商A",
                            "oa_bank_relation": {
                                "code": "pending_match",
                                "label": "待找流水与发票",
                                "tone": "warn",
                            },
                        }
                    ],
                    "bank": [
                        {
                            "id": transaction_id,
                            "type": "bank",
                            "case_id": candidate_case_id,
                            "debit_amount": "100.00",
                            "credit_amount": "",
                            "counterparty_name": "供应商A",
                            "trade_time": "2026-03-12 10:16:38",
                            "invoice_relation": {
                                "code": "suggested_match",
                                "label": "待人工确认",
                                "tone": "warn",
                            },
                        }
                    ],
                    "invoice": [],
                },
            }

            self.assertIn(candidate_case_id, json.dumps(raw_payload, ensure_ascii=False))
            self._install_bank_detail_read_model_fixture(app)
            with patch.object(
                app,
                "_build_raw_workbench_payload",
                side_effect=AssertionError("bank details relation tags must not read raw workbench payload"),
            ):
                response = app.handle_request(
                    "GET",
                    "/api/bank-details/transactions?date_from=2026-03-12&date_to=2026-03-12&page_size=500",
                )

        self.assertEqual(response.status_code, 200, response.body)
        payload = json.loads(response.body)
        row = next(row for row in payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(row["oa_relation_tag"], "无oa")
        self.assertEqual(row["invoice_relation_tag"], "无发票")
        self.assertEqual(row["relation_tags"], ["无oa", "无发票"])
        self.assertNotIn("relation_case_id", row)

    def test_disabled_manual_clear_does_not_suppress_auto_in_bank_details_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_imported_bank_transaction(
                app,
                summary="网银手续费",
                remark="转账手续费",
            )
            self._install_bank_detail_read_model_fixture(app)

            save_response = app.handle_request(
                "PATCH",
                "/api/bank-details/transactions/categories",
                body=json.dumps(
                    {
                        "updates": [
                            {
                                "transaction_id": transaction_id,
                                "category_code": None,
                                "expected_version": 0,
                            }
                        ]
                    }
                ),
            )
            save_payload = json.loads(save_response.body)
            list_response = app.handle_request(
                "GET",
                "/api/bank-details/transactions?account_key=%E5%B7%A5%E5%95%86%E9%93%B6%E8%A1%8C%3A6386",
            )
            list_payload = json.loads(list_response.body)

        self.assertEqual(save_response.status_code, 410)
        self.assertEqual(save_payload["error"], "manual_bank_transaction_category_disabled")
        self.assertEqual(list_response.status_code, 200)
        row = next(row for row in list_payload["rows"] if row["id"] == transaction_id)
        self.assertEqual(row["auto_category_code"], "fee")
        self.assertEqual(row["effective_category_code"], "fee")
        self.assertEqual(row["category_code"], "fee")
        self.assertEqual(row["category_source"], "auto")
        self.assertEqual(list_payload["category_counts"]["fee"], 1)
        self.assertEqual(list_payload["category_counts"]["uncategorized"], 0)

    def test_workbench_bank_rows_ignore_saved_manual_category_history(self) -> None:
        app = build_application()
        transaction_id = self._create_imported_bank_transaction(app, trade_time="2026-04-03 09:00:00")

        app._bank_transaction_category_service.apply_updates(
            [
                {
                    "transaction_id": transaction_id,
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                }
            ],
            actor="test",
        )

        response = app.handle_request("GET", "/api/workbench?month=2026-04")
        payload = json.loads(response.body)
        bank_rows = [
            *flatten_groups(payload["paired"]["groups"], "bank"),
            *flatten_groups(payload["open"]["groups"], "bank"),
        ]
        bank_row = next(row for row in bank_rows if row["id"] == transaction_id)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(bank_row["category_code"])
        self.assertIsNone(bank_row["category_label"])
        self.assertIsNone(bank_row["category_source"])
        self.assertEqual(bank_row["category_path"], [])
        self.assertNotIn("公司暂借款：待还款", bank_row["tags"])
        self.assertIn({"label": "摘要", "value": "付款"}, bank_row["bank_text_fields"])
        self.assertIn({"label": "备注", "value": "货款"}, bank_row["bank_text_fields"])

    @contextmanager
    def _without_default_test_auth(self):
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def test_apply_candidate_matches_does_not_link_multi_row_needs_review_candidate(self) -> None:
        app = build_application()
        candidate = app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "bank_invoice",
                "status": "needs_review",
                "confidence": "medium",
                "rule_code": "same_amount",
                "row_ids": ["bank-001", "invoice-001"],
                "oa_row_ids": [],
                "bank_row_ids": ["bank-001"],
                "invoice_row_ids": ["invoice-001"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "persisted review candidate",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-05",
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "bank-001",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "100.00",
                        "credit_amount": "",
                        "invoice_relation": {
                            "code": "pending_invoice_match",
                            "label": "待关联发票",
                            "tone": "warn",
                        },
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-001",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "100.00",
                        "total_with_tax": "100.00",
                        "invoice_bank_relation": {
                            "code": "pending_collection",
                            "label": "待匹配流水",
                            "tone": "warn",
                        },
                    }
                ],
            },
        }

        payload = app._apply_candidate_matches_to_payload(raw_payload, "2026-05")
        grouped = app._group_row_payload(payload)
        bank_row = payload["open"]["bank"][0]
        invoice_row = payload["open"]["invoice"][0]

        self.assertFalse(
            bank_row.get("case_id") == invoice_row.get("case_id") == candidate["candidate_key"]
        )
        self.assertNotEqual(bank_row["invoice_relation"]["code"], "suggested_match")
        self.assertNotEqual(invoice_row["invoice_bank_relation"]["code"], "suggested_match")
        self.assertEqual(grouped["paired"]["groups"], [])
        self.assertEqual(len(grouped["open"]["groups"]), 2)

    def test_apply_candidate_matches_links_multi_row_auto_closed_candidate(self) -> None:
        app = build_application()
        candidate = app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "bank_invoice",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "bank_invoice_exact_amount",
                "row_ids": ["bank-001", "invoice-001"],
                "oa_row_ids": [],
                "bank_row_ids": ["bank-001"],
                "invoice_row_ids": ["invoice-001"],
                "amount": "100.00",
                "amount_delta": "0.00",
                "explanation": "persisted closed candidate",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-05",
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "bank-001",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "100.00",
                        "credit_amount": "",
                        "invoice_relation": {
                            "code": "pending_invoice_match",
                            "label": "待关联发票",
                            "tone": "warn",
                        },
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-001",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "100.00",
                        "total_with_tax": "100.00",
                        "invoice_bank_relation": {
                            "code": "pending_collection",
                            "label": "待匹配流水",
                            "tone": "warn",
                        },
                    }
                ],
            },
        }

        payload = app._apply_candidate_matches_to_payload(raw_payload, "2026-05")
        grouped = app._group_row_payload(payload)
        bank_row = payload["open"]["bank"][0]
        invoice_row = payload["open"]["invoice"][0]

        self.assertEqual(bank_row["case_id"], candidate["candidate_key"])
        self.assertEqual(invoice_row["case_id"], candidate["candidate_key"])
        self.assertEqual(bank_row["invoice_relation"]["code"], "automatic_match")
        self.assertEqual(invoice_row["invoice_bank_relation"]["code"], "automatic_match")
        self.assertEqual(len(grouped["open"]["groups"]), 1)
        self.assertEqual(grouped["open"]["groups"][0]["group_type"], "candidate")

    def test_import_file_confirm_returns_preview_stale_when_existing_records_change(self) -> None:
        app = build_application()
        boundary = "----finops-import-stale-boundary"
        preview_body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="imported_by"\r\n\r\n'
            "user_finance_01\r\n"
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="files"; filename="{INVOICE_JAN.name}"\r\n'
            f"Content-Type: {INVOICE_JAN.content_type}\r\n\r\n"
        ).encode("utf-8") + INVOICE_JAN.content + f"\r\n--{boundary}--\r\n".encode("utf-8")
        preview_response = app.handle_request(
            "POST",
            "/imports/files/preview",
            body=preview_body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        session = app._file_import_service.get_session(preview_payload["session"]["id"])
        competing_preview = app._import_service.preview_import(
            batch_type=session.files[0].batch_type,
            source_name="competing.json",
            imported_by="user_finance_02",
            rows=[session.files[0].row_results[0].raw_payload],
        )
        app._import_service.confirm_import(competing_preview.id)

        confirm_response = app.handle_request(
            "POST",
            "/imports/files/confirm",
            json.dumps(
                {
                    "session_id": preview_payload["session"]["id"],
                    "selected_file_ids": [preview_payload["files"][0]["id"]],
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 409)
        self.assertEqual(json.loads(confirm_response.body)["error"], "preview_stale")

    def test_get_api_workbench_uses_auto_closed_candidate_matches_in_paired_section(self) -> None:
        app = build_application()
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_bank_invoice",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "oa_bank_multi_invoice_exact_sum",
                "row_ids": ["oa-auto", "bank-auto", "invoice-auto-1", "invoice-auto-2"],
                "oa_row_ids": ["oa-auto"],
                "bank_row_ids": ["bank-auto"],
                "invoice_row_ids": ["invoice-auto-1", "invoice-auto-2"],
                "amount": "300.00",
                "amount_delta": "0.00",
                "explanation": "candidate closes the loop",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-05",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 2, "paired_count": 0, "open_count": 4, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-auto",
                        "type": "oa",
                        "case_id": None,
                        "apply_type": "付款申请",
                        "amount": "300.00",
                        "counterparty_name": "设备供应商",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-auto",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "300.00",
                        "credit_amount": "",
                        "counterparty_name": "设备供应商",
                        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-auto-1",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "120.00",
                        "total_with_tax": "120.00",
                        "seller_name": "设备供应商",
                        "invoice_type": "进项发票",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                    {
                        "id": "invoice-auto-2",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "180.00",
                        "total_with_tax": "180.00",
                        "seller_name": "设备供应商",
                        "invoice_type": "进项发票",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                ],
            },
        }

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(app, "_build_oa_workbench_row_payload", return_value=raw_payload),
        ):
            payload = app._build_api_workbench_payload("2026-05")

        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        self.assertEqual([row["id"] for row in paired_groups[0]["oa_rows"]], ["oa-auto"])
        self.assertEqual([row["id"] for row in paired_groups[0]["bank_rows"]], ["bank-auto"])
        self.assertCountEqual(
            [row["id"] for row in paired_groups[0]["invoice_rows"]],
            ["invoice-auto-1", "invoice-auto-2"],
        )
        self.assertEqual(payload["open"]["groups"], [])

    def test_get_api_workbench_keeps_incomplete_candidate_matches_in_open_section(self) -> None:
        app = build_application()
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_invoice",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_multi_invoice_exact_sum",
                "row_ids": ["oa-open", "invoice-open-1", "invoice-open-2"],
                "oa_row_ids": ["oa-open"],
                "bank_row_ids": [],
                "invoice_row_ids": ["invoice-open-1", "invoice-open-2"],
                "amount": "300.00",
                "amount_delta": "0.00",
                "explanation": "missing bank",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-05",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 2, "paired_count": 0, "open_count": 3, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-open",
                        "type": "oa",
                        "case_id": None,
                        "apply_type": "付款申请",
                        "amount": "300.00",
                        "counterparty_name": "会务服务有限公司",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [],
                "invoice": [
                    {
                        "id": "invoice-open-1",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "120.00",
                        "total_with_tax": "120.00",
                        "seller_name": "会务服务有限公司",
                        "invoice_type": "进项发票",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                    {
                        "id": "invoice-open-2",
                        "type": "invoice",
                        "case_id": None,
                        "amount": "180.00",
                        "total_with_tax": "180.00",
                        "seller_name": "会务服务有限公司",
                        "invoice_type": "进项发票",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                ],
            },
        }

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(app, "_build_oa_workbench_row_payload", return_value=raw_payload),
        ):
            payload = app._build_api_workbench_payload("2026-05")

        self.assertEqual(payload["paired"]["groups"], [])
        self.assertEqual(len(payload["open"]["groups"]), 1)
        self.assertEqual([row["id"] for row in payload["open"]["groups"][0]["oa_rows"]], ["oa-open"])
        self.assertCountEqual(
            [row["id"] for row in payload["open"]["groups"][0]["invoice_rows"]],
            ["invoice-open-1", "invoice-open-2"],
        )

    def test_oa_bank_incomplete_candidate_beats_single_row_no_confident_match(self) -> None:
        app = build_application()
        no_confident_candidate = app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "bank",
                "status": "needs_review",
                "confidence": "low",
                "rule_code": "no_confident_match",
                "row_ids": ["bank-open"],
                "oa_row_ids": [],
                "bank_row_ids": ["bank-open"],
                "invoice_row_ids": [],
                "amount": "196.00",
                "amount_delta": "0.00",
                "explanation": "no invoice evidence",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        oa_bank_candidate = app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-05",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-open", "bank-open"],
                "oa_row_ids": ["oa-open"],
                "bank_row_ids": ["bank-open"],
                "invoice_row_ids": [],
                "amount": "196.00",
                "amount_delta": "0.00",
                "explanation": "OA and bank matched; invoice evidence is missing.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-05",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 2, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-open",
                        "type": "oa",
                        "case_id": None,
                        "apply_type": "付款申请",
                        "amount": "196.00",
                        "counterparty_name": "田孟维",
                        "direction": "payment",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-open",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "196.00",
                        "credit_amount": "",
                        "counterparty_name": "田孟维",
                        "direction": "payment",
                        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                    }
                ],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-05")

        self.assertNotEqual(oa_bank_candidate["candidate_key"], no_confident_candidate["candidate_key"])
        self.assertEqual(payload["paired"]["groups"], [])
        self.assertEqual(len(payload["open"]["groups"]), 1)
        open_group = payload["open"]["groups"][0]
        self.assertEqual(open_group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in open_group["oa_rows"]], ["oa-open"])
        self.assertEqual([row["id"] for row in open_group["bank_rows"]], ["bank-open"])
        self.assertEqual(open_group["invoice_rows"], [])
        self.assertEqual(open_group["group_id"], f"case:{oa_bank_candidate['candidate_key']}")
        self.assertEqual(open_group["oa_rows"][0]["case_id"], oa_bank_candidate["candidate_key"])
        self.assertEqual(open_group["bank_rows"][0]["case_id"], oa_bank_candidate["candidate_key"])
        self.assertEqual(open_group["oa_rows"][0]["oa_bank_relation"]["code"], "candidate_incomplete")

    def test_get_api_workbench_keeps_oa_bank_exact_sum_candidate_in_one_open_group(self) -> None:
        app = build_application()
        candidate = app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-04",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_sum",
                "row_ids": ["oa-dali-prepay", "bank-gd-23053", "bank-jh-64996"],
                "oa_row_ids": ["oa-dali-prepay"],
                "bank_row_ids": ["bank-gd-23053", "bank-jh-64996"],
                "invoice_row_ids": [],
                "amount": "88050.00",
                "amount_delta": "0.00",
                "explanation": "OA amount equals the exact sum of multiple credible bank transactions; invoice evidence is missing.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-04",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 0, "paired_count": 0, "open_count": 3, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-dali-prepay",
                        "type": "oa",
                        "case_id": None,
                        "apply_type": "付款申请",
                        "amount": "88050.00",
                        "counterparty_name": "云南辰飞机电工程有限公司",
                        "direction": "payment",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-jh-64996",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "64996.69",
                        "credit_amount": "",
                        "counterparty_name": "云南辰飞机电工程有限公司",
                        "direction": "payment",
                        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                    },
                    {
                        "id": "bank-gd-23053",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "23053.31",
                        "credit_amount": "",
                        "counterparty_name": "云南辰飞机电工程有限公司",
                        "direction": "payment",
                        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                    },
                ],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-04")

        self.assertEqual(payload["paired"]["groups"], [])
        self.assertEqual(len(payload["open"]["groups"]), 1)
        open_group = payload["open"]["groups"][0]
        self.assertEqual(open_group["group_type"], "candidate")
        self.assertEqual(open_group["group_id"], f"case:{candidate['candidate_key']}")
        self.assertEqual([row["id"] for row in open_group["oa_rows"]], ["oa-dali-prepay"])
        self.assertCountEqual(
            [row["id"] for row in open_group["bank_rows"]],
            ["bank-jh-64996", "bank-gd-23053"],
        )
        self.assertEqual(open_group["invoice_rows"], [])
        self.assertEqual(open_group["oa_rows"][0]["oa_bank_relation"]["code"], "candidate_incomplete")
        self.assertEqual(
            {row["invoice_relation"]["code"] for row in open_group["bank_rows"]},
            {"candidate_incomplete"},
        )

    def test_oa_bank_candidate_attaches_to_existing_oa_attachment_case_group(self) -> None:
        app = build_application()
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-01",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-tian-196", "bank-tian-196"],
                "oa_row_ids": ["oa-tian-196"],
                "bank_row_ids": ["bank-tian-196"],
                "invoice_row_ids": [],
                "amount": "196.00",
                "amount_delta": "0.00",
                "explanation": "OA and bank matched; invoice evidence is missing.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-01",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 1,
                "invoice_count": 2,
                "paired_count": 0,
                "open_count": 4,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-tian-196",
                        "type": "oa",
                        "case_id": "CASE-OA-ATT-oa-tian-196",
                        "apply_type": "日常报销",
                        "amount": "196.00",
                        "counterparty_name": "",
                        "applicant": "田孟维",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-tian-196",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "196.00",
                        "credit_amount": "",
                        "counterparty_name": "田孟维",
                        "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-oa-70",
                        "type": "invoice",
                        "case_id": "CASE-OA-ATT-oa-tian-196",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-tian-196",
                        "amount": "66.04",
                        "total_with_tax": "70.00",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                    {
                        "id": "invoice-oa-126",
                        "type": "invoice",
                        "case_id": "CASE-OA-ATT-oa-tian-196",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-tian-196",
                        "amount": "124.75",
                        "total_with_tax": "126.00",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                ],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-01")

        self.assertEqual(payload["open"]["groups"], [])
        self.assertEqual(len(payload["paired"]["groups"]), 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(group["group_id"], "case:CASE-OA-ATT-oa-tian-196")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-tian-196"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-tian-196"])
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["invoice-oa-70", "invoice-oa-126"],
        )

    def test_oa_bank_candidate_extends_existing_confirmed_oa_case_without_downgrading_oa(self) -> None:
        app = build_application()
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-03",
                "candidate_type": "oa_bank",
                "status": "incomplete",
                "confidence": "medium",
                "rule_code": "oa_bank_exact_amount",
                "row_ids": ["oa-cost-confirmed", "bank-cost-confirmed"],
                "oa_row_ids": ["oa-cost-confirmed"],
                "bank_row_ids": ["bank-cost-confirmed"],
                "invoice_row_ids": [],
                "amount": "1250.00",
                "amount_delta": "0.00",
                "explanation": "OA and bank matched; invoice evidence is missing.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 1,
                "invoice_count": 0,
                "paired_count": 1,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {
                "oa": [
                    {
                        "id": "oa-cost-confirmed",
                        "type": "oa",
                        "case_id": "CASE-COST-CONFIRMED",
                        "apply_type": "日常报销",
                        "amount": "1250.00",
                        "counterparty_name": "昆明设备供应商",
                        "direction": "payment",
                        "oa_bank_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
                    }
                ],
                "bank": [],
                "invoice": [],
            },
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "bank-cost-confirmed",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "1,250.00",
                        "credit_amount": "",
                        "counterparty_name": "昆明设备供应商",
                        "direction": "payment",
                        "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    }
                ],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-03")

        self.assertEqual(payload["paired"]["groups"], [])
        self.assertEqual(len(payload["open"]["groups"]), 1)
        group = payload["open"]["groups"][0]
        self.assertEqual(group["group_id"], "case:CASE-COST-CONFIRMED")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-cost-confirmed"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-cost-confirmed"])
        self.assertEqual(group["oa_rows"][0]["oa_bank_relation"]["code"], "fully_linked")
        self.assertEqual(group["bank_rows"][0]["case_id"], "CASE-COST-CONFIRMED")
        self.assertEqual(group["bank_rows"][0]["invoice_relation"]["code"], "candidate_incomplete")

    def test_all_scope_cached_read_model_rebuilds_when_candidate_snapshot_is_missing(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-01",
                "candidate_type": "oa_bank_invoice",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "oa_attachment_invoice_source_link",
                "row_ids": ["oa-tian-196", "bank-tian-196", "invoice-oa-70", "invoice-oa-126"],
                "oa_row_ids": ["oa-tian-196"],
                "bank_row_ids": ["bank-tian-196"],
                "invoice_row_ids": ["invoice-oa-70", "invoice-oa-126"],
                "amount": "196.00",
                "amount_delta": "0.00",
                "explanation": "OA attachment invoices and bank amount close the loop.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {},
            }
        )
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "workbench_read_model_schema_version": WORKBENCH_READ_MODEL_SCHEMA_VERSION,
                "workbench_candidate_match_schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
                "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 2,
                    "paired_count": 0,
                    "open_count": 4,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "temp:oa",
                            "group_type": "candidate",
                            "match_confidence": "low",
                            "reason": "stale",
                            "oa_rows": [{"id": "oa-tian-196", "type": "oa", "applicant": "田孟维", "amount": "196"}],
                            "bank_rows": [],
                            "invoice_rows": [],
                        },
                    ],
                },
            },
        )
        raw_payload = {
            "month": "all",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 1,
                "invoice_count": 2,
                "paired_count": 0,
                "open_count": 4,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-tian-196",
                        "type": "oa",
                        "case_id": None,
                        "apply_type": "日常报销",
                        "amount": "196.00",
                        "counterparty_name": "",
                        "applicant": "田孟维",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-tian-196",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "196.00",
                        "credit_amount": "",
                        "counterparty_name": "田孟维",
                        "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    }
                ],
                "invoice": [
                    {
                        "id": "invoice-oa-70",
                        "type": "invoice",
                        "case_id": None,
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-tian-196",
                        "amount": "66.04",
                        "total_with_tax": "70.00",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                    {
                        "id": "invoice-oa-126",
                        "type": "invoice",
                        "case_id": None,
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-tian-196",
                        "amount": "124.75",
                        "total_with_tax": "126.00",
                        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    },
                ],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            payload = app._build_api_workbench_payload("all")

        build_raw.assert_any_call("all")
        self.assertEqual(payload["open"]["groups"], [])
        self.assertEqual(len(payload["paired"]["groups"]), 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-tian-196"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-tian-196"])
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["invoice-oa-70", "invoice-oa-126"],
        )

    def test_all_scope_refreshes_stale_candidate_run_before_using_matching_cache(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-01",
                "candidate_type": "bank_only",
                "status": "needs_review",
                "confidence": "low",
                "rule_code": "no_confident_match",
                "row_ids": ["bank-tian-196"],
                "oa_row_ids": [],
                "bank_row_ids": ["bank-tian-196"],
                "invoice_row_ids": [],
                "amount": "196.00",
                "amount_delta": "0.00",
                "explanation": "No confident invoice match was found for this bank transaction.",
                "conflict_candidate_keys": [],
                "generated_at": "2026-05-07T00:00:00+00:00",
                "source_versions": {"workbench_matching_rules_version": "old-rules"},
            }
        )
        app._workbench_candidate_match_service.mark_scope_processed(
            "2026-01",
            source_versions={"workbench_matching_rules_version": "old-rules"},
            candidate_count=1,
            request_id="old-run",
            reason="old-run",
        )
        stale_candidate_hash = app._workbench_candidate_snapshot_hash("all")
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "workbench_read_model_schema_version": WORKBENCH_READ_MODEL_SCHEMA_VERSION,
                "workbench_candidate_match_schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
                "workbench_candidate_snapshot_hash": stale_candidate_hash,
                "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 2,
                    "paired_count": 0,
                    "open_count": 4,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "temp:oa",
                            "group_type": "candidate",
                            "match_confidence": "low",
                            "reason": "stale",
                            "oa_rows": [{"id": "oa-tian-196", "type": "oa", "applicant": "田孟维", "amount": "196"}],
                            "bank_rows": [],
                            "invoice_rows": [],
                        },
                    ],
                },
            },
        )

        def raw_payload(month: str, **_kwargs: object) -> dict[str, object]:
            return {
                "month": month,
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 2,
                    "paired_count": 0,
                    "open_count": 4,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {
                            "id": "oa-tian-196",
                            "type": "oa",
                            "case_id": None,
                            "apply_type": "日常报销",
                            "amount": "196.00",
                            "counterparty_name": "",
                            "applicant": "田孟维",
                            "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                        }
                    ],
                    "bank": [
                        {
                            "id": "bank-tian-196",
                            "type": "bank",
                            "case_id": None,
                            "debit_amount": "196.00",
                            "credit_amount": "",
                            "counterparty_name": "田孟维",
                            "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                        }
                    ],
                    "invoice": [
                        {
                            "id": "invoice-oa-70",
                            "type": "invoice",
                            "case_id": None,
                            "source_kind": "oa_attachment_invoice",
                            "derived_from_oa_id": "oa-tian-196",
                            "amount": "66.04",
                            "total_with_tax": "70.00",
                            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                        },
                        {
                            "id": "invoice-oa-126",
                            "type": "invoice",
                            "case_id": None,
                            "source_kind": "oa_attachment_invoice",
                            "derived_from_oa_id": "oa-tian-196",
                            "amount": "124.75",
                            "total_with_tax": "126.00",
                            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                        },
                    ],
                },
            }

        with patch.object(app, "_build_raw_workbench_payload", side_effect=raw_payload) as build_raw:
            payload = app._build_api_workbench_payload("all")

        build_raw.assert_any_call("2026-01", supplement_missing_pair_relation_rows=False)
        build_raw.assert_any_call("all")
        self.assertEqual(payload["open"]["groups"], [])
        self.assertEqual(len(payload["paired"]["groups"]), 1)
        group = payload["paired"]["groups"][0]
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-tian-196"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-tian-196"])
        self.assertCountEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["invoice-oa-70", "invoice-oa-126"],
        )

    def test_monthly_matching_uses_imported_bank_rows_without_month_limit_for_oa_attachment_closure(self) -> None:
        app = build_application()

        def raw_payload(month: str, **_kwargs: object) -> dict[str, object]:
            if month == "2026-03":
                return {
                    "month": month,
                    "oa_status": {"code": "ready", "message": "OA 已同步"},
                    "summary": {
                        "oa_count": 1,
                        "bank_count": 0,
                        "invoice_count": 2,
                        "paired_count": 0,
                        "open_count": 3,
                        "exception_count": 0,
                    },
                    "paired": {"oa": [], "bank": [], "invoice": []},
                    "open": {
                        "oa": [
                            {
                                "id": "oa-tian-318",
                                "type": "oa",
                                "case_id": None,
                                "apply_type": "日常报销",
                                "amount": "318.00",
                                "counterparty_name": "",
                                "applicant": "田孟维",
                                "pay_receive_time": "2026-03-17",
                                "reason": "餐费，刘总已知",
                                "project_name": "大理卷烟厂余热综合利用项目",
                                "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                            }
                        ],
                        "bank": [],
                        "invoice": [
                            {
                                "id": "invoice-oa-174",
                                "type": "invoice",
                                "case_id": None,
                                "source_kind": "oa_attachment_invoice",
                                "derived_from_oa_id": "oa-tian-318",
                                "amount": "172.28",
                                "total_with_tax": "174.00",
                                "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                            },
                            {
                                "id": "invoice-oa-145",
                                "type": "invoice",
                                "case_id": None,
                                "source_kind": "oa_attachment_invoice",
                                "derived_from_oa_id": "oa-tian-318",
                                "amount": "143.56",
                                "total_with_tax": "145.00",
                                "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                            },
                        ],
                    },
                }
            if month == "2026-04":
                return {
                    "month": month,
                    "oa_status": {"code": "ready", "message": "OA 已同步"},
                    "summary": {
                        "oa_count": 0,
                        "bank_count": 1,
                        "invoice_count": 0,
                        "paired_count": 0,
                        "open_count": 1,
                        "exception_count": 0,
                    },
                    "paired": {"oa": [], "bank": [], "invoice": []},
                    "open": {
                        "oa": [],
                        "bank": [
                            {
                                "id": "bank-tian-318",
                                "type": "bank",
                                "case_id": None,
                                "debit_amount": "318.00",
                                "credit_amount": "",
                                "counterparty_name": "田孟维",
                                "trade_time": "2026-04-03 14:30:01",
                                "pay_receive_time": "2026-04-03 14:30:01",
                                "summary": "代收付",
                                "direction": "支出",
                                "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                            }
                        ],
                        "invoice": [],
                    },
                }
            return {
                "month": month,
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {"oa": [], "bank": [], "invoice": []},
            }

        imported_bank = SimpleNamespace(
            id="bank-tian-318",
            txn_direction="outflow",
            amount=Decimal("318.00"),
            counterparty_name_raw="田孟维",
            trade_time="2026-04-03 14:30:01",
            pay_receive_time="2026-04-03 14:30:01",
            txn_date="2026-04-03",
            summary="代收付",
            remark="",
            account_no="8106",
            account_name="建设银行",
            counterparty_account_no="",
        )
        with (
            patch.object(app, "_build_raw_workbench_payload", side_effect=raw_payload) as build_raw,
            patch.object(app._import_service, "list_transactions", return_value=[imported_bank]) as list_transactions,
        ):
            rows = app._workbench_matching_rows_for_scope("2026-03")
            app._run_workbench_auto_matching_for_scopes(["2026-03"], reason="unit_cross_month")

        self.assertIn("bank-tian-318", [row["id"] for row in rows["bank_rows"]])
        list_transactions.assert_called()
        build_raw.assert_any_call("2026-03", supplement_missing_pair_relation_rows=False)
        self.assertNotIn("2026-04", [call.args[0] for call in build_raw.call_args_list])
        candidates = app._workbench_candidate_match_service.list_candidates_by_month("2026-03")
        candidate = next(
            candidate
            for candidate in candidates
            if candidate["rule_code"] == "oa_attachment_invoice_source_link"
        )
        self.assertEqual(candidate["status"], "auto_closed")
        self.assertEqual(candidate["candidate_type"], "oa_bank_invoice")
        self.assertEqual(candidate["amount"], "318.00")
        self.assertEqual(candidate["amount_delta"], "1.00")
        self.assertEqual(candidate["bank_row_ids"], ["bank-tian-318"])
        self.assertCountEqual(candidate["invoice_row_ids"], ["invoice-oa-174", "invoice-oa-145"])
        all_payload = {
            "month": "all",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 1,
                "invoice_count": 2,
                "paired_count": 0,
                "open_count": 4,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [raw_payload("2026-03")["open"]["oa"][0]],
                "bank": [raw_payload("2026-04")["open"]["bank"][0]],
                "invoice": raw_payload("2026-03")["open"]["invoice"],
            },
        }
        grouped = app._group_row_payload(app._apply_candidate_matches_to_payload(all_payload, "all"))
        self.assertEqual(grouped["open"]["groups"], [])
        self.assertEqual(len(grouped["paired"]["groups"]), 1)
        group = grouped["paired"]["groups"][0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-tian-318"])
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["bank-tian-318"])
        self.assertCountEqual([row["id"] for row in group["invoice_rows"]], ["invoice-oa-174", "invoice-oa-145"])

    def test_amount_only_oa_bank_rows_do_not_share_case_id_or_open_group(self) -> None:
        app = build_application()
        candidates = app._workbench_matching_rules.generate_candidates(
            "2026-01",
            oa_rows=[
                {
                    "id": "oa-hurong-350",
                    "type": "oa",
                    "applicant": "胡瑢",
                    "applicant_name": "胡瑢",
                    "apply_type": "日常报销",
                    "amount": "350.00",
                    "project_name": "玉溪卷烟厂复烤车间技术升级改造项目-配电监控系统建设（第2次采购）",
                    "reason": "玉溪德力西买材料；玉溪卓达买工具和材料",
                    "counterparty_name": "",
                    "pay_receive_time": "2026-01-04",
                }
            ],
            bank_rows=[
                {
                    "id": "bank-batch-350",
                    "type": "bank",
                    "trade_time": "2026-01-20 10:40:01",
                    "pay_receive_time": "2026-01-20 10:40:01",
                    "debit_amount": "350.00",
                    "credit_amount": "",
                    "counterparty_name": "批量账务集中处理",
                    "summary": "报销",
                }
            ],
            invoice_rows=[],
        )
        for candidate in candidates:
            app._workbench_candidate_match_service.upsert_candidate(candidate)

        raw_payload = {
            "month": "2026-01",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 2, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-hurong-350",
                        "type": "oa",
                        "case_id": None,
                        "applicant": "胡瑢",
                        "applicant_name": "胡瑢",
                        "apply_type": "日常报销",
                        "amount": "350.00",
                        "counterparty_name": "",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [
                    {
                        "id": "bank-batch-350",
                        "type": "bank",
                        "case_id": None,
                        "debit_amount": "350.00",
                        "credit_amount": "",
                        "counterparty_name": "批量账务集中处理",
                        "summary": "报销",
                        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                    }
                ],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-01")

        open_rows = [
            row
            for group in payload["open"]["groups"]
            for row in [*group["oa_rows"], *group["bank_rows"], *group["invoice_rows"]]
        ]
        rows_by_id = {row["id"]: row for row in open_rows}
        oa_row_payload = rows_by_id["oa-hurong-350"]
        bank_row_payload = rows_by_id["bank-batch-350"]
        self.assertNotEqual(oa_row_payload.get("case_id"), bank_row_payload.get("case_id"))
        self.assertFalse(
            any(
                [row["id"] for row in group["oa_rows"]] == ["oa-hurong-350"]
                and [row["id"] for row in group["bank_rows"]] == ["bank-batch-350"]
                for group in payload["open"]["groups"]
            )
        )

    def test_enqueued_workbench_auto_matching_does_not_run_legacy_matching_engine(self) -> None:
        app = build_application()

        def run_job_inline(job, handler):
            result = handler(job)
            app._background_job_service.succeed_job(job.job_id, "done", result_summary=result)
            return SimpleNamespace(done=lambda: True)

        with (
            patch.object(app._background_job_service, "run_job", side_effect=run_job_inline),
            patch.object(
                app._workbench_matching_orchestrator,
                "run",
                return_value={"processed_months": ["2026-05"], "candidate_count": 2},
            ) as run_orchestrator,
            patch.object(app._matching_service, "run", return_value=SimpleNamespace(result_count=99)) as run_legacy,
        ):
            job = app._enqueue_workbench_auto_matching_for_scopes(
                ["2026-05"],
                reason="unit",
                owner_user_id="system",
            )

        self.assertIsNotNone(job)
        run_orchestrator.assert_called_once()
        run_legacy.assert_not_called()
        job_payload = app._background_job_service.get_job(job.job_id, "system").to_payload()
        self.assertEqual(job_payload["result_summary"]["candidate_count"], 2)
        self.assertEqual(job_payload["result_summary"]["affected_months"], ["2026-05"])
        self.assertNotIn("matching_results", job_payload["result_summary"])

    def test_workbench_auto_matching_failure_queues_dirty_scope_without_raising(self) -> None:
        app = build_application()
        with patch.object(
            app._workbench_matching_orchestrator,
            "run",
            side_effect=RuntimeError("matching unavailable"),
        ):
            result = app._run_workbench_auto_matching_for_scopes(
                ["2026-05"],
                reason="unit_failure",
            )

        self.assertIsNone(result)
        dirty_scopes = app._workbench_matching_dirty_scope_service.list_dirty_scopes()
        self.assertEqual([entry["scope_month"] for entry in dirty_scopes], ["2026-05"])
        self.assertEqual(dirty_scopes[0]["reasons"], ["unit_failure"])
        self.assertEqual(dirty_scopes[0]["last_error"], "matching unavailable")

    def test_dirty_scope_retry_runs_auto_matching_and_clears_scope(self) -> None:
        app = build_application()
        app._workbench_matching_dirty_scope_service.mark_dirty(["2026-05"], reason="unit")
        with patch.object(
            app,
            "_run_workbench_auto_matching_for_scopes",
            return_value={"candidate_count": 0},
        ) as run_matching:
            result = app._rebuild_workbench_matching_dirty_scopes_once()

        self.assertEqual(result, {"candidate_count": 0})
        run_matching.assert_called_once_with(["2026-05"], reason="dirty_scope_retry")
        self.assertEqual(app._workbench_matching_dirty_scope_service.list_dirty_scopes(), [])

    def test_workbench_auto_matching_coalesces_overlapping_running_scope(self) -> None:
        app = build_application()
        app._workbench_matching_running_scope_months.add("2026-05")
        with patch.object(app._workbench_matching_orchestrator, "run") as run_matching:
            result = app._run_workbench_auto_matching_for_scopes(
                ["2026-05"],
                reason="unit_overlap",
            )

        self.assertIsNone(result)
        run_matching.assert_not_called()
        dirty_scopes = app._workbench_matching_dirty_scope_service.list_dirty_scopes()
        self.assertEqual([entry["scope_month"] for entry in dirty_scopes], ["2026-05"])
        self.assertEqual(dirty_scopes[0]["reasons"], ["unit_overlap_coalesced"])

    def test_get_api_workbench_prefers_cached_read_model_when_available(self) -> None:
        app = build_application()
        cached_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 99,
                "bank_count": 88,
                "invoice_count": 77,
                "paired_count": 1,
                "open_count": 0,
                "exception_count": 0,
            },
            "paired": {
                "groups": [
                    {
                        "group_id": "case:CACHE-202603-001",
                        "oa_rows": [{"id": "oa-cached-001", "type": "oa"}],
                        "bank_rows": [],
                        "invoice_rows": [],
                    }
                ]
            },
            "open": {"groups": []},
        }
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload=cached_payload,
            generated_at="2026-04-08T11:00:00+00:00",
        )

        with patch.object(app, "_build_raw_workbench_payload", side_effect=AssertionError("should not rebuild raw payload")):
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["summary"]["oa_count"], 99)
        self.assertEqual(payload["paired"]["groups"][0]["oa_rows"][0]["id"], "oa-cached-001")

    def test_get_api_workbench_rebuilds_cached_mongo_read_model_when_attachment_parser_version_changes(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "workbench_read_model_schema_version": WORKBENCH_READ_MODEL_SCHEMA_VERSION,
                "oa_attachment_invoice_parser_version": "old-parser",
                "summary": {
                    "oa_count": 99,
                    "bank_count": 0,
                    "invoice_count": 18,
                    "paired_count": 0,
                    "open_count": 99,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-rebuilt-001",
                        "type": "oa",
                        "case_id": None,
                        "applicant": "胡瑢",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_raw.call_count, 2)
        build_raw.assert_any_call("2026-03")
        payload = json.loads(response.body)
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["open"]["groups"][0]["oa_rows"][0]["id"], "oa-rebuilt-001")
        read_model = app._workbench_read_model_service.get_read_model("2026-03")
        assert read_model is not None
        self.assertEqual(
            read_model["payload"]["oa_attachment_invoice_parser_version"],
            app._current_oa_attachment_invoice_parser_version(),
        )
        self.assertEqual(read_model["payload"]["workbench_read_model_schema_version"], WORKBENCH_READ_MODEL_SCHEMA_VERSION)

    def test_get_api_workbench_rebuilds_cached_read_model_from_old_oa_attachment_source_group_schema(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )
        old_schema_version = "2026-05-09-cross-month-oa-attachment-bank"
        self.assertNotEqual(WORKBENCH_READ_MODEL_SCHEMA_VERSION, old_schema_version)
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "workbench_read_model_schema_version": old_schema_version,
                "workbench_candidate_match_schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
                "workbench_candidate_snapshot_hash": app._workbench_candidate_snapshot_hash("2026-03"),
                "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 3,
                    "paired_count": 0,
                    "open_count": 4,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "temp:stale-oa",
                            "group_type": "candidate",
                            "match_confidence": "low",
                            "reason": "standalone_row_group",
                            "oa_rows": [{"id": "oa-stale-source", "type": "oa"}],
                            "bank_rows": [],
                            "invoice_rows": [],
                        }
                    ]
                },
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-rebuilt-source",
                        "type": "oa",
                        "case_id": None,
                        "amount": "248.00",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_raw.call_count, 2)
        payload = json.loads(response.body)
        self.assertEqual(payload["open"]["groups"][0]["oa_rows"][0]["id"], "oa-rebuilt-source")
        read_model = app._workbench_read_model_service.get_read_model("2026-03")
        assert read_model is not None
        self.assertEqual(read_model["payload"]["workbench_read_model_schema_version"], WORKBENCH_READ_MODEL_SCHEMA_VERSION)

    def test_current_oa_attachment_invoice_parser_version_includes_source_schema_version(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )

        self.assertEqual(
            app._current_oa_attachment_invoice_parser_version(),
            MongoOAAdapter._attachment_invoice_cache_parser_version(),
        )

    def test_get_api_workbench_rebuilds_cached_mongo_read_model_when_schema_version_missing(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = MongoOAAdapter(
            settings=MongoOASettings(host="127.0.0.1", database="form_data_db")
        )
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                "summary": {
                    "oa_count": 99,
                    "bank_count": 0,
                    "invoice_count": 18,
                    "paired_count": 0,
                    "open_count": 99,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-rebuilt-schema-001",
                        "type": "oa",
                        "case_id": None,
                        "applicant": "胡瑢",
                        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    }
                ],
                "bank": [],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_raw.call_count, 2)
        build_raw.assert_any_call("2026-03")
        payload = json.loads(response.body)
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["open"]["groups"][0]["oa_rows"][0]["id"], "oa-rebuilt-schema-001")

    def test_get_api_workbench_rebuilds_when_cached_read_model_oa_status_is_not_ready(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "oa_status": {"code": "error", "message": "OA 连接失败"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )

        with patch.object(
            app,
            "_build_raw_workbench_payload",
            return_value={
                "month": "all",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [{"id": "oa-rebuilt-001", "type": "oa"}],
                    "bank": [],
                    "invoice": [],
                },
            },
        ) as build_raw_payload:
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_raw_payload.call_count, 1)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "ready")
        self.assertEqual(payload["summary"]["oa_count"], 1)

    def test_get_api_workbench_does_not_persist_read_model_when_oa_status_is_not_ready(self) -> None:
        app = build_application()

        with patch.object(
            app,
            "_build_raw_workbench_payload",
            return_value={
                "month": "all",
                "oa_status": {"code": "error", "message": "OA 连接失败"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {"oa": [], "bank": [], "invoice": []},
            },
        ):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "error")
        self.assertIsNone(app._workbench_read_model_service.get_read_model("all"))

    def test_get_api_workbench_falls_back_to_stale_ready_cache_when_rebuild_oa_fails(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 1,
                    "paired_count": 0,
                    "open_count": 2,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "case:CASE-OA-ATT-stale",
                            "group_type": "candidate",
                            "oa_rows": [
                                {
                                    "id": "oa-stale-001",
                                    "type": "oa",
                                    "case_id": "CASE-OA-ATT-stale",
                                    "applicant": "周洁莹",
                                    "oa_bank_relation": {
                                        "code": "pending_match",
                                        "label": "待找流水与发票",
                                        "tone": "warn",
                                    },
                                }
                            ],
                            "bank_rows": [],
                            "invoice_rows": [
                                {
                                    "id": "oa-att-inv-stale-001",
                                    "type": "invoice",
                                    "case_id": "CASE-OA-ATT-stale",
                                    "source_kind": "oa_attachment_invoice",
                                    "derived_from_oa_id": "oa-stale-001",
                                    "invoice_bank_relation": {
                                        "code": "pending_match",
                                        "label": "待匹配",
                                        "tone": "warn",
                                    },
                                }
                            ],
                        }
                    ]
                },
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )

        with patch.object(
            app,
            "_build_raw_workbench_payload",
            return_value={
                "month": "all",
                "oa_status": {"code": "error", "message": "OA 连接失败"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {"oa": [], "bank": [], "invoice": []},
            },
        ) as build_raw_payload:
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(build_raw_payload.call_count, 1)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "ready")
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["open"]["groups"][0]["oa_rows"][0]["id"], "oa-stale-001")

    def test_get_api_workbench_reports_oa_error_when_mongo_adapter_is_unavailable(self) -> None:
        app = build_application()
        app._workbench_query_service._oa_adapter = FailingMongoWorkbenchOAAdapter()

        response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "error")
        self.assertEqual(payload["oa_status"]["message"], "OA 连接失败")

    def test_get_api_workbench_rebuilds_stale_zero_oa_cache_for_mongo_adapter(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
            generated_at="2026-04-08T11:00:00+00:00",
        )
        app._workbench_query_service._oa_adapter = StaticMongoWorkbenchOAAdapter(
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
                "32": [],
            },
            project_documents=[
                {"_id": "6486ca70cd6cae5d4e2b0b48", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )

        response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "ready")
        self.assertEqual(payload["summary"]["oa_count"], 1)

    def test_get_api_workbench_all_scopes_mongo_oa_reads_to_retention_months(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-01-01"},
        )
        adapter = RetentionScopedMongoWorkbenchOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-old",
                        "form_id": "2",
                        "modifiedTime": "2025-12-20T09:00:00",
                        "data": {
                            "applicationDate": "2025-12-20",
                            "userName": "旧单据",
                            "fromTitle": "支付申请",
                            "amount": "100",
                            "beneficiary": "旧供应商",
                            "cause": "旧付款",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2046",
                        },
                    },
                    {
                        "_id": "payment-doc-202601",
                        "form_id": "2",
                        "modifiedTime": "2026-01-05T09:00:00",
                        "data": {
                            "applicationDate": "2026-01-05",
                            "userName": "近期单据一",
                            "fromTitle": "支付申请",
                            "amount": "200",
                            "beneficiary": "供应商A",
                            "cause": "近期付款A",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2047",
                        },
                    },
                    {
                        "_id": "payment-doc-202602",
                        "form_id": "2",
                        "modifiedTime": "2026-02-08T09:00:00",
                        "data": {
                            "applicationDate": "2026-02-08",
                            "userName": "近期单据二",
                            "fromTitle": "支付申请",
                            "amount": "300",
                            "beneficiary": "供应商B",
                            "cause": "近期付款B",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2048",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )
        app._workbench_query_service._oa_adapter = adapter

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertEqual(set(oa_ids), {"oa-pay-2047", "oa-pay-2048"})
        self.assertEqual(adapter.bulk_call_count, 0)
        self.assertEqual(adapter.month_calls, ["2026-01", "2026-02"])

    def test_get_api_workbench_all_reincludes_old_oa_related_to_recent_bank_after_cutoff(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-01-01"},
        )
        adapter = RetentionScopedMongoWorkbenchOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-202601",
                        "form_id": "2",
                        "modifiedTime": "2026-01-05T09:00:00",
                        "data": {
                            "applicationDate": "2026-01-05",
                            "userName": "近期单据",
                            "fromTitle": "支付申请",
                            "amount": "200",
                            "beneficiary": "供应商A",
                            "cause": "近期付款A",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2047",
                        },
                    }
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
            row_id_records={
                "oa-pay-2046": [
                    OAApplicationRecord(
                        id="oa-pay-2046",
                        month="2025-12",
                        section="open",
                        case_id=None,
                        applicant="旧关联OA",
                        project_name="云南溯源科技",
                        apply_type="支付申请",
                        amount="100",
                        counterparty_name="旧供应商",
                        reason="旧付款",
                        relation_code="pending_match",
                        relation_label="待找流水与发票",
                        relation_tone="warn",
                    )
                ]
            },
        )
        app._workbench_query_service._oa_adapter = adapter
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-RETENTION-001",
            row_ids=["oa-pay-2046", "bank-recent-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="all",
        )
        recent_bank_row = {
            "id": "bank-recent-001",
            "type": "bank",
            "trade_time": "2026-01-06 10:00:00",
            "pay_receive_time": "2026-01-06 10:00:00",
            "invoice_relation": {"code": "fully_linked", "label": "完全关联", "tone": "success"},
            "case_id": "CASE-RETENTION-001",
        }
        live_payload = {
            "month": "all",
            "summary": {
                "oa_count": 0,
                "bank_count": 1,
                "invoice_count": 0,
                "paired_count": 1,
                "open_count": 0,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [recent_bank_row], "invoice": []},
            "open": {"oa": [], "bank": [], "invoice": []},
        }

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=True),
            patch.object(app._live_workbench_service, "get_workbench", return_value=live_payload),
            patch.object(app, "_sync_live_auto_pair_relations", return_value=None),
            patch.object(
                app,
                "_resolve_live_rows_direct",
                side_effect=lambda row_ids, month_hint=None: [recent_bank_row],
            ),
        ):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertIn("oa-pay-2046", oa_ids)
        self.assertIn("oa-pay-2047", oa_ids)
        self.assertEqual(adapter.bulk_call_count, 0)
        self.assertEqual(adapter.month_calls, ["2026-01"])
        self.assertEqual(adapter.row_id_calls, [["oa-pay-2046"]])

    def test_get_api_workbench_all_does_not_fabricate_cutoff_month_range_when_month_listing_errors(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-01-01"},
        )
        adapter = ErrorMonthListRetentionMongoWorkbenchOAAdapter(
            form_documents={
                "2": [
                    {
                        "_id": "payment-doc-202601",
                        "form_id": "2",
                        "modifiedTime": "2026-01-05T09:00:00",
                        "data": {
                            "applicationDate": "2026-01-05",
                            "userName": "近期单据一",
                            "fromTitle": "支付申请",
                            "amount": "200",
                            "beneficiary": "供应商A",
                            "cause": "近期付款A",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2047",
                        },
                    },
                    {
                        "_id": "payment-doc-202602",
                        "form_id": "2",
                        "modifiedTime": "2026-02-08T09:00:00",
                        "data": {
                            "applicationDate": "2026-02-08",
                            "userName": "近期单据二",
                            "fromTitle": "支付申请",
                            "amount": "300",
                            "beneficiary": "供应商B",
                            "cause": "近期付款B",
                            "projectName": "oa-project-001",
                            "flowRequestId": "2048",
                        },
                    },
                ],
                "32": [],
            },
            project_documents=[
                {"_id": "oa-project-001", "data": {"name": "云南溯源科技", "code": "YNSY"}},
            ],
        )
        app._workbench_query_service._oa_adapter = adapter

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "error")
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertEqual(oa_ids, [])
        self.assertEqual(adapter.month_calls, [])

    def test_get_api_workbench_all_does_not_schedule_attachment_invoice_ocr(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-03-01"},
        )
        adapter = RetentionScopedMongoWorkbenchOAAdapter(
            form_documents={
                "2": [],
                "32": [
                    {
                        "_id": "expense-doc-attach-001",
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
                                    "detailReimbursementAttachment": {
                                        "files": [
                                            {
                                                "fileName": "invoice-a.png",
                                                "filePath": "/invoice-a.png",
                                                "suffix": "png",
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
                {"_id": "oa-project-001", "data": {"name": "玉烟维护项目", "code": "YYWH"}},
            ],
            attachment_invoice_cache=MemoryAttachmentInvoiceCache(),
        )
        app._workbench_query_service._oa_adapter = adapter

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(adapter, "_schedule_attachment_invoice_parse", side_effect=AssertionError("should not schedule OCR for all-scope bootstrap")),
        ):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertEqual(oa_ids, ["oa-exp-exp-attach-cache-miss-001"])

    def test_raw_oa_payload_uses_record_snapshot_when_records_change_during_build(self) -> None:
        app = build_application()
        app._workbench_query_service._records_by_id = MutatingRecordDict(
            {
                "oa-existing-001": {
                    "id": "oa-existing-001",
                    "type": "oa",
                    "_month": "2026-01",
                    "_section": "open",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
                "oa-existing-002": {
                    "id": "oa-existing-002",
                    "type": "oa",
                    "_month": "2026-01",
                    "_section": "open",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                },
            }
        )

        payload = app._raw_oa_payload_for_selected_scope(months={"2026-01"}, supplemental_oa_row_ids=set())

        oa_ids = {row["id"] for row in payload["open"]["oa"]}
        self.assertEqual(oa_ids, {"oa-existing-001", "oa-existing-002"})
        self.assertEqual(payload["summary"]["oa_count"], 2)

    def test_retained_all_scope_includes_manual_imported_oa_and_attachment_invoices(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-03-01"},
        )
        app._workbench_query_service._records_by_id = {
            "oa-manual-202512": {
                "id": "oa-manual-202512",
                "type": "oa",
                "_month": "2025-12",
                "_section": "open",
                "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            },
            "oa-att-inv-oa-manual-202512-01": {
                "id": "oa-att-inv-oa-manual-202512-01",
                "type": "invoice",
                "_month": "2025-12",
                "_section": "open",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-manual-202512",
                "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
            },
            "oa-old-not-retained": {
                "id": "oa-old-not-retained",
                "type": "oa",
                "_month": "2025-12",
                "_section": "open",
                "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            },
        }
        app._oa_manual_import_service = SimpleNamespace(
            manual_retained_row_ids=lambda: ["oa-manual-202512"]
        )

        payload = app._raw_oa_payload_for_selected_scope(months={"2026-03"}, supplemental_oa_row_ids=set())

        self.assertEqual([row["id"] for row in payload["open"]["oa"]], ["oa-manual-202512"])
        self.assertEqual(
            [row["id"] for row in payload["open"]["invoice"]],
            ["oa-att-inv-oa-manual-202512-01"],
        )
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["summary"]["invoice_count"], 1)

    def test_pair_relation_application_supplements_missing_active_oa_rows(self) -> None:
        app = build_application()
        oa_row = {
            **build_oa_retention_oa_row("oa-exp-ba-2025", "CASE-BATCH-CROSS-YEAR", "2025-12-23"),
            "_month": "2025-12",
            "_section": "open",
        }
        bank_row = build_oa_retention_bank_row(
            "txn_imported_202601_batch_001",
            "CASE-BATCH-CROSS-YEAR",
            "2026-01-28 16:34:04",
        )
        invoice_row = {
            **build_oa_retention_invoice_row(
                "oa-att-inv-oa-exp-ba-2025-001",
                "CASE-BATCH-CROSS-YEAR",
                "2025-12-23",
            ),
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-exp-ba-2025",
        }
        app._workbench_query_service._records_by_id = {oa_row["id"]: oa_row}
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-BATCH-CROSS-YEAR",
            row_ids=[bank_row["id"], oa_row["id"], invoice_row["id"]],
            row_types=["bank", "oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="tester",
            special_metadata={
                "source": "batch_accounting",
                "bank_row_id": bank_row["id"],
                "oa_row_ids": [oa_row["id"]],
                "invoice_row_ids": [invoice_row["id"]],
                "bank_year": "2026",
                "oa_year": "2025",
            },
        )
        raw_payload = build_oa_retention_raw_payload(
            oa_rows=[],
            bank_rows=[bank_row],
            invoice_rows=[invoice_row],
        )

        relation_payload = app._apply_pair_relations_to_payload(raw_payload)
        grouped_payload = app._group_row_payload(relation_payload)

        self.assertEqual([row["id"] for row in relation_payload["paired"]["oa"]], ["oa-exp-ba-2025"])
        paired_groups = grouped_payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        self.assertEqual([row["id"] for row in paired_groups[0]["oa_rows"]], ["oa-exp-ba-2025"])
        self.assertEqual([row["id"] for row in paired_groups[0]["bank_rows"]], ["txn_imported_202601_batch_001"])
        self.assertEqual([row["id"] for row in paired_groups[0]["invoice_rows"]], ["oa-att-inv-oa-exp-ba-2025-001"])

    def test_get_api_workbench_keeps_salary_auto_match_as_candidate_until_no_oa_submit(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="salary-payment.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id

        response = app.handle_request("GET", "/api/workbench?month=all")
        payload = json.loads(response.body)
        auto_results = app._live_workbench_service.list_auto_pair_candidates("all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(payload["open"]["groups"], "bank")], [salary_row_id])
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "salary_personal_auto_match")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id))

    def test_get_api_workbench_ignores_stale_auto_closed_salary_candidate_match(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="stale-salary-candidate.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-02",
                "candidate_type": "bank",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "salary_personal_auto_match",
                "row_ids": [salary_row_id],
                "bank_row_ids": [salary_row_id],
                "amount": "9.00",
                "amount_delta": "0.00",
                "explanation": "stale legacy salary auto close",
            }
        )
        app._invalidate_workbench_read_models()

        response = app.handle_request("GET", "/api/workbench?month=2026-02")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        open_bank_rows = flatten_groups(payload["open"]["groups"], "bank")
        self.assertEqual([row["id"] for row in open_bank_rows], [salary_row_id])
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id))

    def test_get_api_workbench_exposes_invoice_identity_fields_for_live_invoice_rows(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input-invoice.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "云南供应商有限公司",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)

        response = app.handle_request("GET", "/api/workbench?month=2026-03")
        payload = json.loads(response.body)
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(invoice_row["invoice_code"], "033001")
        self.assertEqual(invoice_row["invoice_no"], "9001")
        self.assertEqual(invoice_row["digital_invoice_no"], "—")

    def test_get_api_workbench_keeps_internal_transfer_auto_match_as_candidate_until_no_oa_submit(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 10:02:00",
                    "pay_receive_time": "2026-02-03 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "内部往来收入",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        internal_transfer_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]

        response = app.handle_request("GET", "/api/workbench?month=all")
        payload = json.loads(response.body)
        auto_results = app._live_workbench_service.list_auto_pair_candidates("all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        open_bank_rows = flatten_groups(payload["open"]["groups"], "bank")
        self.assertCountEqual([row["id"] for row in open_bank_rows], internal_transfer_row_ids)
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "internal_transfer_pair")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(internal_transfer_row_ids[0]))

    def test_get_api_workbench_ignores_stale_auto_closed_internal_transfer_candidate_match(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="stale-internal-transfer-candidate.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 10:02:00",
                    "pay_receive_time": "2026-02-03 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "内部往来收入",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        internal_transfer_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._workbench_candidate_match_service.upsert_candidate(
            {
                "scope_month": "2026-02",
                "candidate_type": "bank",
                "status": "auto_closed",
                "confidence": "high",
                "rule_code": "internal_transfer_pair",
                "row_ids": internal_transfer_row_ids,
                "bank_row_ids": internal_transfer_row_ids,
                "amount": "50000.00",
                "amount_delta": "0.00",
                "explanation": "stale legacy internal transfer auto close",
            }
        )
        app._invalidate_workbench_read_models()

        response = app.handle_request("GET", "/api/workbench?month=2026-02")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        open_bank_rows = flatten_groups(payload["open"]["groups"], "bank")
        self.assertCountEqual([row["id"] for row in open_bank_rows], internal_transfer_row_ids)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(internal_transfer_row_ids[0]))

    def test_workbench_matching_rows_preserve_bank_identity_fields_for_internal_transfer_rules(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer-identity-fields.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "39610188000598826",
                    "account_name": "云南溯源科技有限公司",
                    "txn_date": "2026-02-13",
                    "trade_time": "2026-02-13 17:15:37",
                    "pay_receive_time": "2026-02-13 17:15:37",
                    "counterparty_name": "云南溯源科技有限公司",
                    "counterparty_account_no": "53001905038050548106",
                    "debit_amount": "184597.41",
                    "credit_amount": "",
                    "summary": "工资及过节费",
                },
                {
                    "account_no": "53001905038050548106",
                    "account_name": "云南溯源科技有限公司",
                    "txn_date": "2026-02-13",
                    "trade_time": "2026-02-13 17:15:51",
                    "pay_receive_time": "2026-02-13 17:15:51",
                    "counterparty_name": "云南溯源科技有限公司",
                    "counterparty_account_no": "39610188000598826",
                    "debit_amount": "",
                    "credit_amount": "184597.41",
                    "summary": "电子汇入",
                    "remark": "工资及过节费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        imported_row_ids = {
            transaction.id
            for transaction in app._import_service.list_transactions()
            if transaction.source_batch_id == preview.id
        }

        rows = app._workbench_matching_rows_for_scope("2026-02")["bank_rows"]
        imported_rows = [row for row in rows if str(row.get("id")) in imported_row_ids]

        self.assertEqual(len(imported_rows), 2)
        self.assertCountEqual([row.get("account_no") for row in imported_rows], ["39610188000598826", "53001905038050548106"])
        self.assertTrue(all(row.get("account_name") == "云南溯源科技有限公司" for row in imported_rows))

    def test_stale_single_row_candidate_does_not_auto_pair_no_oa_internal_transfer_rows(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer-stale-candidate.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "39610188000598826",
                    "account_name": "云南溯源科技有限公司",
                    "txn_date": "2026-02-13",
                    "trade_time": "2026-02-13 17:15:37",
                    "pay_receive_time": "2026-02-13 17:15:37",
                    "counterparty_name": "云南溯源科技有限公司",
                    "counterparty_account_no": "53001905038050548106",
                    "debit_amount": "184597.41",
                    "credit_amount": "",
                    "summary": "工资及过节费",
                },
                {
                    "account_no": "53001905038050548106",
                    "account_name": "云南溯源科技有限公司",
                    "txn_date": "2026-02-13",
                    "trade_time": "2026-02-13 17:15:51",
                    "pay_receive_time": "2026-02-13 17:15:51",
                    "counterparty_name": "云南溯源科技有限公司",
                    "counterparty_account_no": "39610188000598826",
                    "debit_amount": "",
                    "credit_amount": "184597.41",
                    "summary": "电子汇入",
                    "remark": "工资及过节费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        bank_row_ids = [
            transaction.id
            for transaction in app._import_service.list_transactions()
            if transaction.source_batch_id == preview.id
        ]
        app.handle_request("GET", "/api/workbench?month=2026-02")
        for row_id in bank_row_ids:
            app._workbench_candidate_match_service.upsert_candidate(
                {
                    "scope_month": "2026-02",
                    "candidate_type": "bank",
                    "status": "needs_review",
                    "confidence": "low",
                    "rule_code": "no_confident_match",
                    "row_ids": [row_id],
                    "bank_row_ids": [row_id],
                    "amount": "184597.41",
                    "amount_delta": "0.00",
                    "explanation": "stale single-row candidate",
                }
            )
        app._invalidate_workbench_read_models()

        response = app.handle_request("GET", "/api/workbench?month=2026-02")
        payload = json.loads(response.body)
        paired_bank_rows = [
            row
            for group in payload["paired"]["groups"]
            for row in group["bank_rows"]
            if row["id"] in bank_row_ids
        ]
        open_bank_rows = [
            row
            for group in payload["open"]["groups"]
            for row in group["bank_rows"]
            if row["id"] in bank_row_ids
        ]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(paired_bank_rows, [])
        self.assertCountEqual([row["id"] for row in open_bank_rows], bank_row_ids)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(bank_row_ids[0]))

    def test_get_api_workbench_ignored_prefers_cached_read_model_when_available(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[
                {
                    "id": "bk-ignored-001",
                    "type": "bank",
                    "counterparty_name": "测试忽略流水",
                }
            ],
            generated_at="2026-04-08T12:00:00+00:00",
        )

        with patch.object(app, "_build_raw_workbench_payload", side_effect=AssertionError("should not rebuild raw payload")):
            response = app.handle_request("GET", "/api/workbench/ignored?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["rows"][0]["id"], "bk-ignored-001")

    def test_get_api_workbench_ignored_uses_sql_read_model_without_rebuild(self) -> None:
        class SqlReadRepository:
            def list_workbench_ignored_rows(self, *, scope_key: str) -> list[dict[str, object]]:
                self.scope_key = scope_key
                return [{"id": "bk-sql-ignored-001", "type": "bank"}]

        app = build_application()
        repository = SqlReadRepository()
        app._workbench_sql_read_repository = repository

        with patch.object(app, "_get_or_build_workbench_read_model", side_effect=AssertionError("should not rebuild read model")):
            response = app.handle_request("GET", "/api/workbench/ignored?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(repository.scope_key, "all")
        self.assertEqual(payload["rows"], [{"id": "bk-sql-ignored-001", "type": "bank"}])

    def test_merge_live_workbench_keeps_oa_rows_when_live_bank_invoice_exist(self) -> None:
        live_payload = {
            "month": "2026-03",
            "summary": {
                "oa_count": 0,
                "bank_count": 1,
                "invoice_count": 1,
                "paired_count": 0,
                "open_count": 2,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "bk-live-001",
                        "type": "bank",
                        "case_id": "match_result_001",
                        "credit_amount": "120.00",
                        "counterparty_name": "云上客户",
                        "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    }
                ],
                "invoice": [
                    {
                        "id": "iv-live-001",
                        "type": "invoice",
                        "case_id": "match_result_001",
                        "amount": "120.00",
                        "invoice_type": "销项发票",
                        "buyer_name": "云上客户",
                        "invoice_bank_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                    }
                ],
            },
        }
        oa_payload = WorkbenchQueryService().get_workbench("2026-03")

        merged = Application._merge_live_workbench_with_oa(live_payload, oa_payload)

        self.assertGreater(merged["summary"]["oa_count"], 0)
        self.assertGreaterEqual(len(merged["open"]["groups"]), 1)
        self.assertTrue(any(group["oa_rows"] for group in merged["open"]["groups"]))
        self.assertEqual(merged["summary"]["bank_count"], 1)
        self.assertEqual(merged["summary"]["invoice_count"], 1)

    def test_get_api_workbench_promotes_oa_attachment_binding_with_live_bank_to_three_way_relation(self) -> None:
        app = build_application()
        query_service = WorkbenchQueryService(oa_adapter=AttachmentAwareOAAdapter())
        self._install_workbench_query_service(app, query_service)
        app._live_workbench_service = _StubLiveWorkbenchService()

        response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        matching_groups = [
            group
            for group in payload["paired"]["groups"]
            if any(row["id"] == "oa-attach-202603-001" for row in group["oa_rows"])
        ]
        self.assertEqual(len(matching_groups), 1)
        group = matching_groups[0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual([row["id"] for row in group["bank_rows"]], ["txn-live-202603-001"])
        self.assertEqual(len(group["invoice_rows"]), 1)
        self.assertEqual(group["invoice_rows"][0]["detail_fields"]["来源OA单号"], "OA-ATT-001")
        self.assertTrue(group["oa_rows"][0]["special_metadata"]["immutable_oa_attachment_binding"])
        self.assertFalse(payload["open"]["groups"])

        invoice_row_id = group["invoice_rows"][0]["id"]
        invoice_detail_response = app.handle_request("GET", f"/api/workbench/rows/{invoice_row_id}")
        oa_detail_response = app.handle_request("GET", "/api/workbench/rows/oa-attach-202603-001")
        self.assertEqual(invoice_detail_response.status_code, 200)
        self.assertEqual(oa_detail_response.status_code, 200)
        invoice_detail = json.loads(invoice_detail_response.body)["row"]
        oa_detail = json.loads(oa_detail_response.body)["row"]
        self.assertEqual(invoice_detail["source_expense_item_id"], "oa-attach-202603-001:item:0:equipment")
        self.assertEqual(invoice_detail["source_attachment_key"], "oa-attach-202603-001:item:0:att:equipment")
        self.assertEqual(invoice_detail["source_attachment_name"], "设备发票.pdf")
        self.assertEqual(invoice_detail["detail_fields"]["来源付款项ID"], "oa-attach-202603-001:item:0:equipment")
        self.assertEqual(invoice_detail["detail_fields"]["来源附件Key"], "oa-attach-202603-001:item:0:att:equipment")
        self.assertEqual(invoice_detail["detail_fields"]["附件文件名"], "设备发票.pdf")
        self.assertEqual(oa_detail["detail_fields"]["附件发票数量"], "1")

    def test_get_api_workbench_groups_repairs_oa_attachment_source_binding_as_open_relation(self) -> None:
        app = build_application()
        query_service = WorkbenchQueryService(oa_adapter=SourceBoundAttachmentOAAdapter())
        self._install_workbench_query_service(app, query_service)

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        source_groups = [
            group
            for group in payload["open"]["groups"]
            if any(row.get("special_metadata", {}).get("immutable_oa_attachment_binding") for row in group["oa_rows"])
        ]

        self.assertEqual(len(source_groups), 2)
        by_oa_id = {group["oa_rows"][0]["id"]: group for group in source_groups}
        self.assertCountEqual(
            list(by_oa_id),
            ["oa-exp-hurong-248", "oa-exp-hurong-292"],
        )

        group_248 = by_oa_id["oa-exp-hurong-248"]
        self.assertEqual(group_248["group_type"], "manual_confirmed")
        self.assertEqual(group_248["match_confidence"], "high")
        self.assertEqual(group_248["reason"], "existing_case_group")
        self.assertEqual(group_248["relation_mode"], "manual_confirmed")
        self.assertCountEqual(
            [row["detail_fields"]["发票号码"] for row in group_248["invoice_rows"]],
            ["24800001", "24800002", "24800003"],
        )
        self.assertTrue(
            all(row["derived_from_oa_id"] == "oa-exp-hurong-248" for row in group_248["invoice_rows"])
        )
        self.assertTrue(
            all(
                row["special_metadata"]["parent_oa_row_id"] == "oa-exp-hurong-248"
                for row in [*group_248["oa_rows"], *group_248["invoice_rows"]]
            )
        )

        group_292 = by_oa_id["oa-exp-hurong-292"]
        self.assertEqual(group_292["group_type"], "manual_confirmed")
        self.assertEqual([row["detail_fields"]["发票号码"] for row in group_292["invoice_rows"]], ["29200001"])
        self.assertEqual(group_292["invoice_rows"][0]["derived_from_oa_id"], "oa-exp-hurong-292")
        self.assertEqual(group_292["oa_rows"][0]["case_id"], "CASE-OA-ATT-oa-exp-hurong-292")

    def test_get_api_workbench_groups_oa_2035_formal_attachment_invoices_only(self) -> None:
        app = build_application()
        record = OAApplicationRecord(
            id="oa-2035",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="胡瑢",
            project_name="2024-2026年度红塔集团工作证管理系统维护项目",
            apply_type="日常报销",
            amount="248.00",
            counterparty_name="",
            reason="OA 2035：过路费和加油费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            expense_type="车辆使用费",
            expense_content="过路费；加油费",
            detail_fields={"OA单号": "OA-2035", "申请日期": "2026-03-04"},
            attachment_evidences=oa_2035_attachment_evidences(),
            attachment_file_count=6,
        )
        query_service = WorkbenchQueryService(oa_adapter=InMemoryOAAdapter({"2026-03": [record]}))
        self._install_workbench_query_service(app, query_service)

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        source_group = next(
            group
            for group in payload["open"]["groups"]
            if any(row["id"] == "oa-2035" for row in group["oa_rows"])
        )
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-2035"])
        self.assertEqual(len(source_group["bank_rows"]), 0)
        self.assertEqual(len(source_group["invoice_rows"]), 3)
        self.assertEqual(
            sum(1 for row in source_group["invoice_rows"] if row["source_kind"] == "oa_attachment_invoice"),
            3,
        )
        self.assertEqual(
            sum(1 for row in source_group["invoice_rows"] if row["source_kind"] == "oa_attachment_payment_receipt"),
            0,
        )
        for row in source_group["invoice_rows"]:
            self.assertEqual(row["derived_from_oa_id"], "oa-2035")
            self.assertTrue(row["source_expense_item_id"])
            self.assertTrue(row["source_attachment_key"])
            self.assertTrue(row["source_attachment_name"])

    def test_get_api_workbench_auto_pairs_offset_applicant_oa_with_attachment_invoice(self) -> None:
        app = build_application()
        target_oa_record = OAApplicationRecord(
            id="oa-offset-202602-001",
            month="2026-02",
            section="open",
            case_id=None,
            applicant="周洁莹",
            project_name="云南溯源科技",
            apply_type="日常报销",
            amount="200.00",
            counterparty_name="云南中油严家山交通服务有限公司",
            reason="汽油费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            expense_type="交通费",
            expense_content="汽油费",
            detail_fields={"OA单号": "OA-OFFSET-001", "申请日期": "2026-02-09"},
            attachment_invoices=[
                {
                    "invoice_code": "053002200111",
                    "invoice_no": "15312761",
                    "seller_name": "云南中油严家山交通服务有限公司",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2025-04-24",
                    "amount": "200.00",
                    "tax_rate": "13%",
                    "tax_amount": "23.01",
                    "invoice_type": "进项发票",
                    "attachment_name": "20240424-汽油费-200.jpg",
                }
            ],
        )
        query_service = WorkbenchQueryService(
            oa_adapter=InMemoryOAAdapter({"2026-02": [target_oa_record]})
        )
        self._install_workbench_query_service(app, query_service)

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=2026-02")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        paired_groups = payload["paired"]["groups"]
        self.assertEqual(len(paired_groups), 1)
        group = paired_groups[0]
        self.assertEqual(group["group_type"], "auto_closed")
        self.assertEqual(len(group["oa_rows"]), 1)
        self.assertEqual(len(group["invoice_rows"]), 1)
        self.assertEqual(group["bank_rows"], [])
        self.assertEqual(group["oa_rows"][0]["oa_bank_relation"]["label"], "待找流水与发票")
        self.assertIn("冲", group["oa_rows"][0]["tags"])
        self.assertTrue(group["oa_rows"][0]["cost_excluded"])
        self.assertIn("冲", group["invoice_rows"][0]["tags"])
        self.assertTrue(group["invoice_rows"][0]["cost_excluded"])
        self.assertEqual(payload["open"]["groups"], [])
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-offset-202602-001")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "oa_invoice_offset_auto_match")
        self.assertCountEqual(
            relation["row_ids"],
            ["oa-offset-202602-001", group["invoice_rows"][0]["id"]],
        )

    def test_get_api_workbench_exposes_multi_project_display_and_real_project_names(self) -> None:
        app = build_application()
        target_oa_record = OAApplicationRecord(
            id="oa-exp-multi-project-001",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="刘际涛",
            project_name="玉烟维护项目；云南溯源科技",
            project_name_display="多个项目",
            project_names=["玉烟维护项目", "云南溯源科技"],
            apply_type="日常报销",
            amount="1500.00",
            counterparty_name="",
            reason="设备材料；邮寄费用",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            expense_type="材料费；运费/邮费/杂费",
            expense_content="设备材料；邮寄费用",
            detail_fields={"OA单号": "OA-MULTI-001", "申请日期": "2026-03-28"},
        )
        query_service = WorkbenchQueryService(
            oa_adapter=InMemoryOAAdapter({"2026-03": [target_oa_record]})
        )
        self._install_workbench_query_service(app, query_service)

        with patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False):
            response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        oa_row = next(
            row
            for row in flatten_groups(payload["open"]["groups"], "oa")
            if row["id"] == "oa-exp-multi-project-001"
        )
        self.assertEqual(oa_row["project_name"], "玉烟维护项目；云南溯源科技")
        self.assertEqual(oa_row["project_name_display"], "多个项目")
        self.assertEqual(oa_row["project_names"], ["玉烟维护项目", "云南溯源科技"])
        self.assertEqual(oa_row["summary_fields"]["项目名称"], "多个项目")
        self.assertIn("玉烟维护项目", oa_row["project_name"])
        self.assertIn("云南溯源科技", oa_row["detail_fields"]["项目名称汇总"])
        self.assertEqual(oa_row["detail_fields"]["项目名称列表"], ["玉烟维护项目", "云南溯源科技"])

    def test_oa_invoice_offset_sync_does_not_cancel_relations_outside_current_payload(self) -> None:
        app = build_application()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-OA-OFFSET-OTHER",
            row_ids=["oa-offset-other", "oa-att-inv-other-01"],
            row_types=["oa", "invoice"],
            relation_mode="oa_invoice_offset_auto_match",
            created_by="system_auto_match",
            month_scope="2026-01",
        )
        payload = {
            "month": "2026-02",
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-current-without-invoice",
                        "type": "oa",
                        "applicant": "周洁莹",
                        "case_id": "CASE-CURRENT",
                    }
                ],
                "bank": [],
                "invoice": [],
            },
        }

        app._sync_oa_invoice_offset_auto_pair_relations(payload)

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-OA-OFFSET-OTHER")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "oa_invoice_offset_auto_match")

    def test_oa_invoice_offset_sync_only_uses_attachment_source_link_not_case_id(self) -> None:
        app = build_application()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-OA-OFFSET-oa-current",
            row_ids=[
                "oa-current",
                "oa-att-inv-current-01",
                "oa-att-inv-current-02",
                "oa-att-inv-other-01",
            ],
            row_types=["oa", "invoice", "invoice", "invoice"],
            relation_mode="oa_invoice_offset_auto_match",
            created_by="system_auto_match",
            month_scope="all",
        )
        payload = {
            "month": "all",
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {
                        "id": "oa-current",
                        "type": "oa",
                        "applicant": "周洁莹",
                        "case_id": "CASE-POLLUTED",
                    }
                ],
                "bank": [],
                "invoice": [
                    {
                        "id": "oa-att-inv-current-01",
                        "type": "invoice",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-current",
                        "case_id": "CASE-POLLUTED",
                    },
                    {
                        "id": "oa-att-inv-current-02",
                        "type": "invoice",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-current",
                        "case_id": "CASE-POLLUTED",
                    },
                    {
                        "id": "oa-att-inv-other-01",
                        "type": "invoice",
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-other",
                        "case_id": "CASE-POLLUTED",
                    },
                ],
            },
        }

        app._sync_oa_invoice_offset_auto_pair_relations(payload)

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(
            "CASE-OA-OFFSET-oa-current"
        )
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["status"], "active")
        self.assertEqual(
            relation["row_ids"],
            ["oa-current", "oa-att-inv-current-01", "oa-att-inv-current-02"],
        )

    def test_row_detail_prefers_cached_read_model_before_query_service_sync(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]

        with (
            patch.object(app._live_workbench_service, "get_row_detail", side_effect=KeyError(oa_row["id"])),
            patch.object(
                app._workbench_query_service,
                "get_row_record",
                side_effect=AssertionError("row detail should resolve from cached read model"),
            ),
        ):
            detail_payload = app._get_api_workbench_row_detail_payload(oa_row["id"])

        self.assertEqual(detail_payload["row"]["id"], oa_row["id"])

    def test_opaque_oa_row_detail_prefers_month_read_model_without_full_oa_sync(self) -> None:
        app = build_application()
        row_id = "oa-exp-69898450db8c0a3633bd748c-0"
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-02",
            payload={
                "month": "2026-02",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 1,
                    "paired_count": 0,
                    "open_count": 2,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "case:CASE-OA-ATT-opaque-001",
                            "group_type": "candidate",
                            "oa_rows": [
                                {
                                    "id": row_id,
                                    "type": "oa",
                                    "case_id": "CASE-OA-ATT-opaque-001",
                                    "applicant": "周洁莹",
                                    "project_name": "云南溯源科技",
                                    "apply_type": "日常报销",
                                    "amount": "200",
                                    "counterparty_name": "",
                                    "reason": "汽油费",
                                    "oa_bank_relation": {
                                        "code": "pending_match",
                                        "label": "待找流水与发票",
                                        "tone": "warn",
                                    },
                                    "available_actions": ["detail", "confirm_link", "mark_exception"],
                                    "summary_fields": {"申请人": "周洁莹"},
                                    "detail_fields": {
                                        "OA单号": "69898450db8c0a3633bd748c",
                                        "附件发票数量": "1",
                                    },
                                }
                            ],
                            "bank_rows": [],
                            "invoice_rows": [],
                        }
                    ]
                },
                "exceptions": {"groups": []},
            },
            ignored_rows=[],
        )

        with (
            patch.object(app._live_workbench_service, "get_row_detail", side_effect=KeyError(row_id)),
            patch.object(
                app._workbench_query_service,
                "get_row_record",
                side_effect=AssertionError("opaque OA row detail should resolve from month read model"),
            ),
            patch.object(
                app._workbench_query_service,
                "_sync_all_oa_rows",
                side_effect=AssertionError("opaque OA row detail should not trigger all-scope OA sync"),
            ),
        ):
            response = app.handle_request("GET", f"/api/workbench/rows/{row_id}")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["row"]["id"], row_id)
        self.assertEqual(payload["row"]["detail_fields"]["附件发票数量"], "1")

    def test_opaque_oa_row_detail_without_cache_returns_404_without_full_oa_sync(self) -> None:
        app = build_application()
        row_id = "oa-exp-opaque-without-month-0"

        with patch.object(
            app._workbench_query_service,
            "_sync_all_oa_rows",
            side_effect=AssertionError("opaque OA row detail should not trigger all-scope OA sync"),
        ):
            response = app.handle_request("GET", f"/api/workbench/rows/{row_id}")

        self.assertEqual(response.status_code, 404)

    def test_row_detail_resolves_flat_cached_read_model_before_live_detail(self) -> None:
        app = build_application()
        row_id = "oa-exp-69fab21659b12d7d42a50a45"
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-05",
            payload={
                "month": "2026-05",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {"groups": [], "oa": [], "bank": [], "invoice": []},
                "open": {
                    "groups": [],
                    "oa": [
                        {
                            "id": row_id,
                            "type": "oa",
                            "applicant": "陈佳玉",
                            "project_name": "大型卷烟厂余热综合利用项目",
                            "amount": "145.00",
                            "reconciliation_amount": "145.00",
                            "available_actions": ["detail", "confirm_link", "mark_exception"],
                        }
                    ],
                    "bank": [],
                    "invoice": [],
                },
                "exceptions": {"groups": []},
            },
            ignored_rows=[],
        )
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda _row_id: (_ for _ in ()).throw(
                AssertionError("row detail must not read live rows before cached read model rows")
            )
        )
        app._workbench_row_detail_api_routes = None

        response = app.handle_request("GET", f"/api/workbench/rows/{row_id}?month=2026-05")

        self.assertEqual(response.status_code, 200, response.body)
        payload = json.loads(response.body)
        self.assertEqual(payload["row"]["id"], row_id)
        self.assertEqual(payload["row"]["applicant"], "陈佳玉")

    def test_get_api_workbench_supports_two_seed_months(self) -> None:
        app = build_application()

        march_response = app.handle_request("GET", "/api/workbench?month=2026-03")
        self.assertEqual(march_response.status_code, 200)
        march_payload = json.loads(march_response.body)
        self.assertEqual(march_payload["month"], "2026-03")
        self.assertGreater(march_payload["summary"]["oa_count"], 0)
        self.assertGreater(len(all_groups(march_payload)), 0)
        self.assertTrue(any(group["oa_rows"] for group in all_groups(march_payload)))
        self.assertTrue(any(group["bank_rows"] for group in all_groups(march_payload)))
        self.assertTrue(any(group["invoice_rows"] for group in all_groups(march_payload)))

        april_response = app.handle_request("GET", "/api/workbench?month=2026-04")
        self.assertEqual(april_response.status_code, 200)
        april_payload = json.loads(april_response.body)
        self.assertEqual(april_payload["month"], "2026-04")
        self.assertNotEqual(
            flatten_groups(all_groups(march_payload), "oa")[0]["id"],
            flatten_groups(all_groups(april_payload), "oa")[0]["id"],
        )

    def test_get_api_workbench_supports_all_time_view(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/workbench?month=all")
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)

        self.assertEqual(payload["month"], "all")
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertIn("oa-o-202603-001", oa_ids)
        self.assertIn("oa-o-202604-001", oa_ids)
        self.assertGreaterEqual(payload["summary"]["oa_count"], 5)

    def test_get_api_workbench_all_keeps_all_ccb_bank_rows_across_paired_and_open(self) -> None:
        app = build_application()
        ccb_rows = [
            build_ccb_bank_row("ccb-jan-open", "2026-01-08 09:00:00", "10.00"),
            build_ccb_bank_row("ccb-feb-open", "2026-02-08 09:00:00", "20.00"),
            build_ccb_bank_row("ccb-mar-open", "2026-03-08 09:00:00", "30.00"),
            build_ccb_bank_row("ccb-apr-paired", "2026-04-08 09:00:00", "40.00"),
        ]
        invoice_row = {
            "id": "invoice-apr-paired",
            "type": "invoice",
            "case_id": None,
            "amount": "40.00",
            "total_with_tax": "40.00",
            "seller_name": "建设银行配对供应商",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-04-08",
            "invoice_type": "进项发票",
            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
            "available_actions": ["detail", "confirm_link", "mark_exception"],
        }
        oa_row = {
            "id": "oa-apr-paired",
            "type": "oa",
            "case_id": None,
            "applicant": "建设银行配对申请人",
            "project_name": "建设银行配对项目",
            "apply_type": "支付申请",
            "amount": "40.00",
            "counterparty_name": "建设银行配对供应商",
            "reason": "建设银行配对 fixture",
            "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            "available_actions": ["detail", "confirm_link", "mark_exception"],
        }
        raw_payload = {
            "month": "all",
            "summary": {
                "oa_count": 1,
                "bank_count": len(ccb_rows),
                "invoice_count": 1,
                "paired_count": 0,
                "open_count": len(ccb_rows) + 2,
                "exception_count": 0,
            },
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {"oa": [oa_row], "bank": ccb_rows, "invoice": [invoice_row]},
        }
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-CCB-PAIRED-001",
            row_ids=["oa-apr-paired", "ccb-apr-paired", "invoice-apr-paired"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="all",
        )

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        paired_bank_rows = flatten_groups(payload["paired"]["groups"], "bank")
        open_bank_rows = flatten_groups(payload["open"]["groups"], "bank")
        all_ccb_rows = [
            row
            for row in [*paired_bank_rows, *open_bank_rows]
            if row.get("payment_account_label") == "建设银行 8106"
        ]

        self.assertEqual(payload["month"], "all")
        self.assertCountEqual([row["id"] for row in all_ccb_rows], [row["id"] for row in ccb_rows])
        self.assertEqual([row["id"] for row in paired_bank_rows], ["ccb-apr-paired"])
        self.assertCountEqual([row["id"] for row in open_bank_rows], ["ccb-jan-open", "ccb-feb-open", "ccb-mar-open"])
        self.assertEqual(len(paired_bank_rows) + len(open_bank_rows), len(ccb_rows))
        self.assertLess(len(open_bank_rows), len(ccb_rows))
        self.assertEqual(payload["summary"]["bank_count"], len(ccb_rows))

    def test_get_api_workbench_row_detail_supports_oa_bank_and_invoice(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row_id = flatten_groups(payload["open"]["groups"], "oa")[0]["id"]
        bank_row_id = flatten_groups(payload["open"]["groups"], "bank")[0]["id"]
        invoice_row_id = flatten_groups(payload["open"]["groups"], "invoice")[0]["id"]

        oa_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{oa_row_id}").body)["row"]
        bank_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{bank_row_id}").body)["row"]
        invoice_detail = json.loads(app.handle_request("GET", f"/api/workbench/rows/{invoice_row_id}").body)["row"]

        self.assertEqual(oa_detail["type"], "oa")
        self.assertIn("申请人", oa_detail["summary_fields"])
        self.assertIn("OA单号", oa_detail["detail_fields"])

        self.assertEqual(bank_detail["type"], "bank")
        self.assertIn("交易时间", bank_detail["summary_fields"])
        self.assertIn("账号", bank_detail["detail_fields"])

        self.assertEqual(invoice_detail["type"], "invoice")
        self.assertIn("购买方名称", invoice_detail["summary_fields"])
        self.assertIn("发票号码", invoice_detail["detail_fields"])

    def test_api_workbench_actions_return_unified_result_structure(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-API-202603-001",
                    "note": "unified result regression covers documented mismatch path",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertTrue(confirm_payload["success"])
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertEqual(confirm_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(confirm_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            confirm_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        self.assertNotIn("updated_rows", confirm_payload)

        updated_workbench = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertIn(oa_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "oa")])
        self.assertIn(bank_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "bank")])
        self.assertIn(invoice_row["id"], [row["id"] for row in flatten_groups(updated_workbench["paired"]["groups"], "invoice")])

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-link",
            json.dumps({"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen for review"}),
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_link")
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertEqual(cancel_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(cancel_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            cancel_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        self.assertNotIn("updated_rows", cancel_payload)

        app_for_cash_special = build_application()
        cash_special_open = json.loads(app_for_cash_special.handle_request("GET", "/api/workbench?month=2026-03").body)
        cash_oa_row = flatten_groups(cash_special_open["open"]["groups"], "oa")[0]
        cash_bank_row = flatten_groups(cash_special_open["open"]["groups"], "bank")[0]
        app_for_cash_special._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-CASH-SPECIAL-001",
            row_ids=[cash_oa_row["id"], cash_bank_row["id"]],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )
        cash_pass_response = app_for_cash_special.handle_request(
            "POST",
            "/api/workbench/actions/confirm-cash-pass-through",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [cash_oa_row["id"], cash_bank_row["id"]],
                    "note": "cash pass target envelope regression",
                }
            ),
        )
        self.assertEqual(cash_pass_response.status_code, 200)
        cash_pass_payload = json.loads(cash_pass_response.body)
        self.assertEqual(cash_pass_payload["action"], "confirm_cash_pass_through")
        self.assertEqual(cash_pass_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(cash_pass_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            cash_pass_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        cash_cancel_response = app_for_cash_special.handle_request(
            "POST",
            "/api/workbench/actions/cancel-cash-special",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [cash_oa_row["id"], cash_bank_row["id"]],
                    "note": "cash cancel target envelope regression",
                }
            ),
        )
        self.assertEqual(cash_cancel_response.status_code, 200)
        cash_cancel_payload = json.loads(cash_cancel_response.body)
        self.assertEqual(cash_cancel_payload["action"], "cancel_cash_special")
        self.assertEqual(cash_cancel_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(cash_cancel_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            cash_cancel_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )

        app_for_cash_ticket = build_application()
        cash_ticket_open = json.loads(app_for_cash_ticket.handle_request("GET", "/api/workbench?month=2026-03").body)
        ticket_oa_row = flatten_groups(cash_ticket_open["open"]["groups"], "oa")[0]
        ticket_bank_row = flatten_groups(cash_ticket_open["open"]["groups"], "bank")[0]
        ticket_invoice_row = flatten_groups(cash_ticket_open["open"]["groups"], "invoice")[0]
        app_for_cash_ticket._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-CASH-TICKET-001",
            row_ids=[ticket_oa_row["id"], ticket_bank_row["id"], ticket_invoice_row["id"]],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )
        cash_ticket_response = app_for_cash_ticket.handle_request(
            "POST",
            "/api/workbench/actions/confirm-cash-ticket-purchase",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [ticket_oa_row["id"], ticket_bank_row["id"], ticket_invoice_row["id"]],
                    "cash_amount": "100.00",
                    "ticket_cost_amount": "0.00",
                    "note": "cash ticket target envelope regression",
                }
            ),
        )
        self.assertEqual(cash_ticket_response.status_code, 200)
        cash_ticket_payload = json.loads(cash_ticket_response.body)
        self.assertEqual(cash_ticket_payload["action"], "confirm_cash_ticket_purchase")
        self.assertEqual(cash_ticket_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(cash_ticket_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            cash_ticket_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )

        app_for_bank_exception = build_application()
        initial_open_for_exception = json.loads(app_for_bank_exception.handle_request("GET", "/api/workbench?month=2026-03").body)
        bank_exception_row = flatten_groups(initial_open_for_exception["open"]["groups"], "bank")[0]
        update_bank_response = app_for_bank_exception.handle_request(
            "POST",
            "/api/workbench/actions/update-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": bank_exception_row["id"],
                    "relation_code": "bank_fee",
                    "relation_label": "银行手续费",
                    "comment": "由出纳补录手续费",
                }
            ),
        )
        self.assertEqual(update_bank_response.status_code, 200)
        update_bank_payload = json.loads(update_bank_response.body)
        self.assertTrue(update_bank_payload["success"])
        self.assertEqual(update_bank_payload["action"], "update_bank_exception")
        self.assertEqual(update_bank_payload["exception_case_ids"], [update_bank_payload["exception_case_id"]])
        self.assertEqual(update_bank_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(update_bank_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            update_bank_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        update_bank_case = app_for_bank_exception._workbench_exception_case_service.snapshot()["cases"][update_bank_payload["exception_case_id"]]
        self.assertEqual(update_bank_case["rule_version"], "exception_rules_v1")
        self.assertEqual(update_bank_case["resolution"]["action_code"], "manual_review")
        self.assertEqual(update_bank_case["resolution"]["legacy_relation_code"], "bank_fee")

        app_for_mark_exception = build_application()
        initial_open_for_mark = json.loads(app_for_mark_exception.handle_request("GET", "/api/workbench?month=2026-03").body)
        open_invoice_after_confirm = flatten_groups(initial_open_for_mark["open"]["groups"], "invoice")[0]
        mark_response = app_for_mark_exception.handle_request(
            "POST",
            "/api/workbench/actions/mark-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": open_invoice_after_confirm["id"],
                    "exception_code": "pending_collection",
                    "comment": "客户尚未付款",
                }
            ),
        )
        self.assertEqual(mark_response.status_code, 200)
        mark_payload = json.loads(mark_response.body)
        self.assertTrue(mark_payload["success"])
        self.assertEqual(mark_payload["action"], "mark_exception")
        self.assertEqual(mark_payload["updated_rows"][0]["id"], open_invoice_after_confirm["id"])
        self.assertEqual(mark_payload["exception_case_ids"], [mark_payload["exception_case_id"]])
        self.assertEqual(mark_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(mark_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            mark_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        mark_case = app_for_mark_exception._workbench_exception_case_service.snapshot()["cases"][mark_payload["exception_case_id"]]
        self.assertEqual(mark_case["rule_version"], "exception_rules_v1")
        self.assertEqual(mark_case["resolution"]["action_code"], "manual_review")
        self.assertEqual(mark_case["resolution"]["legacy_exception_code"], "pending_collection")

    def test_exception_preview_api_returns_backend_scenario_for_oa_bank_missing_invoice(self) -> None:
        app = build_application()
        rows = [
            {
                "id": "oa-exc-api-001",
                "type": "oa",
                "month": "2026-05",
                "apply_type": "付款申请",
                "amount": "100.00",
            },
            {
                "id": "bank-exc-api-001",
                "type": "bank",
                "month": "2026-05",
                "debit_amount": "100.00",
                "credit_amount": "",
                "summary": "支付供应商",
            },
        ]

        with patch.object(app, "_resolve_live_rows_direct", return_value=rows):
            response = app.handle_request(
                "POST",
                "/api/workbench/exception/preview",
                json.dumps({"month": "2026-05", "row_ids": ["oa-exc-api-001", "bank-exc-api-001"]}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["rule_version"], "exception_rules_v1")
        self.assertEqual(payload["scenario"]["business_line"], "expense")
        self.assertEqual(payload["scenario"]["scenario_code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual([action["action_code"] for action in payload["available_actions"]], ["wait_input_invoice"])
        self.assertTrue(payload["can_apply"])

    def test_exception_apply_api_creates_closed_case_and_pair_relation(self) -> None:
        app = build_application()
        rows = [
            {
                "id": "oa-exc-api-001",
                "type": "oa",
                "month": "2026-05",
                "apply_type": "付款申请",
                "amount": "100.00",
            },
            {
                "id": "bank-exc-api-001",
                "type": "bank",
                "month": "2026-05",
                "debit_amount": "100.00",
                "credit_amount": "",
                "summary": "支付供应商",
            },
            {
                "id": "invoice-exc-api-001",
                "type": "invoice",
                "month": "2026-05",
                "issue_date": "2026-05-10",
                "total_with_tax": "100.00",
                "invoice_type": "进项发票",
            },
        ]

        with patch.object(app, "_resolve_live_rows_direct", return_value=rows):
            response = app.handle_request(
                "POST",
                "/api/workbench/exception/apply",
                json.dumps(
                    {
                        "month": "2026-05",
                        "row_ids": ["oa-exc-api-001", "bank-exc-api-001", "invoice-exc-api-001"],
                        "scenario_code": "expense_all_equal",
                        "action_code": "confirm_closed",
                        "payload": {},
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["case"]["status"], "closed")
        self.assertEqual(payload["pair_relation"]["relation_mode"], "normal_match")
        self.assertEqual(payload["pair_relation"]["exception_case_id"], payload["case"]["id"])
        self.assertCountEqual(payload["affected_row_ids"], ["oa-exc-api-001", "bank-exc-api-001", "invoice-exc-api-001"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-05"])
        self.assertEqual(
            payload["freshness_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-05"}],
        )

    def test_cancel_link_uses_existing_case_members_without_rebuilding_workbench(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]
        resolved_rows = [
            app._workbench_query_service.serialize_row(app._workbench_query_service.get_row_record(oa_row["id"])),
            app._resolve_live_row_direct(bank_row["id"]),
            app._resolve_live_row_direct(invoice_row["id"]),
        ]
        relation = app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-FAST-CANCEL-001",
            row_ids=[row["id"] for row in resolved_rows],
            row_types=[row["type"] for row in resolved_rows],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )
        self.assertCountEqual(
            relation["row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            cancel_response = app._handle_live_workbench_cancel_link(
                {"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen for review"}
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", cancel_payload)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FAST-CANCEL-001"))

    def test_confirm_link_persists_pair_relation_without_pairing_override(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]
        decision_store = WorkbenchReconciliationDecisionStore()
        decision_store.upsert_decisions(
            [
                workbench_reconciliation_decision(
                    "decision-confirm-link",
                    scope_month="2026-03",
                    row_ids=(oa_row["id"], bank_row["id"], invoice_row["id"]),
                )
            ]
        )
        app._workbench_reconciliation_decision_store = decision_store

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-PAIR-ONLY-001",
                    "note": "pair relation regression covers documented mismatch path",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-PAIR-ONLY-001")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], [oa_row["id"], bank_row["id"], invoice_row["id"]])
        self.assertIsNone(app._workbench_override_service.case_id_for_row(oa_row["id"]))
        self.assertIsNone(app._workbench_override_service.case_id_for_row(bank_row["id"]))
        self.assertIsNone(app._workbench_override_service.case_id_for_row(invoice_row["id"]))
        stored_decision = decision_store.list_decisions("2026-03")[0]
        self.assertEqual(stored_decision["decision_status"], DECISION_STATUS_CONSUMED)
        self.assertEqual(stored_decision["consumed_by_relation_id"], "CASE-PAIR-ONLY-001")

    def test_withdraw_link_preview_splits_reconciliation_decision_without_active_relation(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]
        decision_store = WorkbenchReconciliationDecisionStore()
        decision_store.upsert_decisions(
            [
                workbench_reconciliation_decision(
                    "decision-withdraw-split",
                    scope_month="2026-03",
                    row_ids=(bank_row["id"], invoice_row["id"]),
                )
            ]
        )
        app._workbench_reconciliation_decision_store = decision_store
        app._workbench_candidate_match_service = WorkbenchCandidateMatchService()

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link/preview",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [bank_row["id"], invoice_row["id"]],
                }
            ),
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["operation_type"], "split_candidate")
        self.assertEqual(preview_payload["candidate_keys"], ["decision-withdraw-split"])
        self.assertEqual(preview_payload["affected_row_ids"], [bank_row["id"], invoice_row["id"]])
        self.assertEqual(preview_payload["affected_scope_keys"], ["2026-03"])
        self.assertIn("decision:decision-withdraw-split", preview_payload["submit_expected_versions"])

        submit_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [bank_row["id"], invoice_row["id"]],
                    "operation_type": "split_candidate",
                    "preview_id": preview_payload["preview_id"],
                    "expected_versions": preview_payload["submit_expected_versions"],
                    "idempotency_key": "api-split-decision-1",
                }
            ),
        )

        self.assertEqual(submit_response.status_code, 200, submit_response.body)
        submit_payload = json.loads(submit_response.body)
        self.assertEqual(submit_payload["operation"], "split_candidate")
        self.assertEqual(submit_payload["affected_months"], ["2026-03"])
        stored_decision = decision_store.list_decisions("2026-03")[0]
        self.assertEqual(stored_decision["decision_status"], "suppressed")
        self.assertEqual(stored_decision["suppressed_by_exception_case_id"], "workbench_split_candidate")

    def test_confirm_link_returns_503_and_rolls_back_when_pair_relation_persist_fails(self) -> None:
        app = build_application()
        app._state_store = _FailingPairRelationStateStore()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-PAIR-PERSIST-FAIL",
                    "note": "persistence failure regression covers documented mismatch path",
                }
            ),
        )

        self.assertEqual(response.status_code, 503)
        response_payload = json.loads(response.body)
        self.assertEqual(response_payload["error"], "workbench_state_persistence_unavailable")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-PAIR-PERSIST-FAIL"))

    def test_confirm_personal_advance_repayment_creates_settled_case_and_pair_relation(self) -> None:
        app = build_application()
        raw_payload = build_personal_advance_repayment_raw_payload()
        row_ids = [
            "oa-personal-advance-001",
            "bank-personal-advance-out-001",
            "bank-personal-advance-in-001",
            "bank-personal-advance-in-002",
        ]

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-03")
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                json.dumps({"month": "2026-03", "row_ids": row_ids, "note": "员工已归还备用金"}),
            )
            updated_workbench = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "confirm_personal_advance_repayment")
        self.assertEqual(payload["amount_summary"]["oa_total"], "300000.00")
        self.assertEqual(payload["amount_summary"]["bank_debit_total"], "300000.00")
        self.assertEqual(payload["amount_summary"]["bank_credit_total"], "300000.00")
        self.assertEqual(payload["amount_summary"]["bank_net_total"], "0.00")
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertEqual(payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(payload["case_id"])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "personal_advance_repayment_settlement")
        self.assertCountEqual(relation["row_ids"], row_ids)
        self.assertEqual(relation["amount_check"]["status"], "matched")
        self.assertEqual(relation["special_metadata"]["special_type"], "personal_advance_repayment_settlement")
        self.assertEqual(relation["special_metadata"]["cost_policy"], "exclude_all")

        exception_snapshot = app._workbench_exception_case_service.snapshot()
        exception_case = exception_snapshot["cases"][payload["exception_case_id"]]
        self.assertEqual(exception_case["status"], "settled")
        self.assertEqual(exception_case["exception_code"], "personal_advance_repayment_settlement")
        self.assertEqual(exception_snapshot["row_case_index"], {})

        paired_rows = flatten_groups(updated_workbench["paired"]["groups"], "oa")
        self.assertIn("oa-personal-advance-001", [row["id"] for row in paired_rows])
        paired_group = next(
            group
            for group in updated_workbench["paired"]["groups"]
            if any(row["id"] == "oa-personal-advance-001" for row in group["oa_rows"])
        )
        self.assertEqual(paired_group["group_type"], "personal_advance_repayment_settlement")
        self.assertEqual(paired_group["oa_rows"][0]["oa_bank_relation"]["label"], "已匹配：还清个人暂借款")
        self.assertIn("还清个人暂借款", paired_group["oa_rows"][0]["tags"])
        self.assertFalse(paired_group["oa_rows"][0].get("handled_exception"))

    def test_confirm_personal_advance_repayment_rejects_unbalanced_amounts(self) -> None:
        app = build_application()
        raw_payload = build_personal_advance_repayment_raw_payload(bank_credit_amounts=["200000.00", "99999.99"])
        row_ids = [
            "oa-personal-advance-001",
            "bank-personal-advance-out-001",
            "bank-personal-advance-in-001",
            "bank-personal-advance-in-002",
        ]

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-03")
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                json.dumps({"month": "2026-03", "row_ids": row_ids}),
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "invalid_personal_advance_repayment_request")
        self.assertEqual(payload["amount_summary"]["bank_credit_total"], "299999.99")

    def test_confirm_personal_advance_repayment_rejects_missing_bank_credit_or_debit(self) -> None:
        app_without_credit = build_application()
        raw_without_credit = build_personal_advance_repayment_raw_payload(bank_credit_amounts=[])

        with patch.object(app_without_credit, "_build_raw_workbench_payload", return_value=raw_without_credit):
            app_without_credit.handle_request("GET", "/api/workbench?month=2026-03")
            missing_credit_response = app_without_credit.handle_request(
                "POST",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                json.dumps({"month": "2026-03", "row_ids": ["oa-personal-advance-001", "bank-personal-advance-out-001"]}),
            )

        self.assertEqual(missing_credit_response.status_code, 400)
        self.assertIn("bank credit", json.loads(missing_credit_response.body)["message"])

        app_without_debit = build_application()
        raw_without_debit = build_personal_advance_repayment_raw_payload(include_bank_debit=False)

        with patch.object(app_without_debit, "_build_raw_workbench_payload", return_value=raw_without_debit):
            app_without_debit.handle_request("GET", "/api/workbench?month=2026-03")
            missing_debit_response = app_without_debit.handle_request(
                "POST",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                json.dumps({"month": "2026-03", "row_ids": ["oa-personal-advance-001", "bank-personal-advance-in-001"]}),
            )

        self.assertEqual(missing_debit_response.status_code, 400)
        self.assertIn("bank debit", json.loads(missing_debit_response.body)["message"])

    def test_confirm_personal_advance_repayment_rejects_invoice_rows(self) -> None:
        app = build_application()
        raw_payload = build_personal_advance_repayment_raw_payload(include_invoice=True)
        row_ids = [
            "oa-personal-advance-001",
            "bank-personal-advance-out-001",
            "bank-personal-advance-in-001",
            "bank-personal-advance-in-002",
            "invoice-personal-advance-001",
        ]

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-03")
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                json.dumps({"month": "2026-03", "row_ids": row_ids}),
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("invoice rows", json.loads(response.body)["message"])

    def test_confirm_and_cancel_link_invalidate_cached_read_model_for_follow_up_get(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(initial_payload["open"]["groups"], "invoice")[0]

        with patch.object(app, "_schedule_workbench_read_model_persist"):
            confirm_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                        "case_id": "CASE-HOT-READMODEL-001",
                        "note": "read model invalidation regression covers documented mismatch path",
                    }
                ),
            )
        self.assertEqual(confirm_response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))
        confirmed_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        self.assertIn(
            oa_row["id"],
            [row["id"] for row in flatten_groups(confirmed_payload["paired"]["groups"], "oa")],
        )

        with patch.object(app, "_schedule_workbench_read_model_persist"):
            cancel_response = app.handle_request(
                "POST",
                "/api/workbench/actions/cancel-link",
                json.dumps({"month": "2026-03", "row_id": bank_row["id"], "comment": "reopen"}),
            )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))
        cancelled_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        self.assertIn(
            bank_row["id"],
            [row["id"] for row in flatten_groups(cancelled_payload["open"]["groups"], "bank")],
        )

    def test_import_confirm_invalidates_cached_read_models_for_changed_workbench_source(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(
                scope_key="all",
                payload={
                    "month": "all",
                    "summary": {
                        "oa_count": 999,
                        "bank_count": 999,
                        "invoice_count": 999,
                        "paired_count": 0,
                        "open_count": 0,
                        "exception_count": 0,
                    },
                    "paired": {"groups": []},
                    "open": {"groups": []},
                },
                ignored_rows=[],
            )

            preview = app._import_service.preview_import(
                batch_type=BatchType.BANK_TRANSACTION,
                source_name="bank-new.xlsx",
                imported_by="user_finance_01",
                rows=[
                    {
                        "account_no": "62220009",
                        "account_name": "云南溯源科技有限公司测试户",
                        "txn_date": "2026-03-21",
                        "trade_time": "2026-03-21 09:00:00",
                        "pay_receive_time": "2026-03-21 09:00:00",
                        "counterparty_name": "测试客户",
                        "debit_amount": "100.00",
                        "credit_amount": "",
                        "summary": "测试导入",
                    }
                ],
            )

            response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview.id}),
            )

            self.assertEqual(response.status_code, 200)
            self.assertIsNone(app._workbench_read_model_service.get_read_model("all"))

    def test_invoice_import_confirm_invalidates_workbench_read_model(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
        )
        preview = app._import_service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input-invoice-read-model-invalidation.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9101",
                    "counterparty_name": "发票导入供应商",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        response = app.handle_request(
            "POST",
            "/imports/confirm",
            json.dumps({"batch_id": preview.id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))

    def test_bank_import_confirm_invalidates_workbench_read_model(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "summary": {
                    "oa_count": 0,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 0,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {"groups": []},
            },
            ignored_rows=[],
        )
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-read-model-invalidation.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220009",
                    "account_name": "云南溯源科技有限公司测试户",
                    "txn_date": "2026-03-21",
                    "trade_time": "2026-03-21 09:00:00",
                    "pay_receive_time": "2026-03-21 09:00:00",
                    "counterparty_name": "银行导入供应商",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "summary": "测试银行导入",
                }
            ],
        )

        response = app.handle_request(
            "POST",
            "/imports/confirm",
            json.dumps({"batch_id": preview.id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(app._workbench_read_model_service.get_read_model("2026-03"))

    def test_oa_clear_and_rebuild_invalidates_workbench_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(
                scope_key="all",
                payload={
                    "month": "all",
                    "summary": {
                        "oa_count": 999,
                        "bank_count": 0,
                        "invoice_count": 0,
                        "paired_count": 0,
                        "open_count": 999,
                        "exception_count": 0,
                    },
                    "paired": {"groups": []},
                    "open": {"groups": []},
                },
                ignored_rows=[],
            )
            app._persist_state()

            result = app._execute_settings_data_reset(RESET_OA_AND_REBUILD_ACTION)

        self.assertEqual(result["action"], RESET_OA_AND_REBUILD_ACTION)
        read_model = app._workbench_read_model_service.get_read_model("all")
        self.assertIsNotNone(read_model)
        assert read_model is not None
        self.assertNotEqual(read_model["payload"]["summary"]["oa_count"], 999)

    def test_confirm_link_resolves_selected_rows_without_rebuilding_grouped_workbench(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-FAST-CONFIRM-001",
                    "note": "fast confirm regression covers documented mismatch path",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertTrue(confirm_payload["success"])
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [oa_row["id"], bank_row["id"], invoice_row["id"]],
        )
        self.assertNotIn("updated_rows", confirm_payload)

    def test_confirm_link_does_not_resolve_source_rows_in_hot_path(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_live_rows_direct", side_effect=AssertionError("should not resolve source rows")):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "all",
                    "row_ids": ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
                    "case_id": "CASE-MINIMAL-CONFIRM-001",
                    "note": "hot path regression covers documented mismatch path",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
        )
        self.assertNotIn("updated_rows", confirm_payload)

    def test_confirm_link_resolves_selected_flat_read_model_rows_without_live_detail(self) -> None:
        app = build_application()
        oa_id = "oa-exp-69fab21659b12d7d42a50a45"
        bank_id = "bk-o-202605-flat-145"
        invoice_id = "iv-o-202605-flat-145"
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-05",
            payload={
                "month": "2026-05",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 1,
                    "paired_count": 0,
                    "open_count": 3,
                    "exception_count": 0,
                },
                "paired": {"groups": [], "oa": [], "bank": [], "invoice": []},
                "open": {
                    "groups": [],
                    "oa": [
                        {
                            "id": oa_id,
                            "type": "oa",
                            "case_id": "",
                            "applicant": "陈佳玉",
                            "project_name": "大型卷烟厂余热综合利用项目",
                            "amount": "145.00",
                            "reconciliation_amount": "145.00",
                            "available_actions": ["detail", "confirm_link", "mark_exception"],
                        }
                    ],
                    "bank": [
                        {
                            "id": bank_id,
                            "type": "bank",
                            "case_id": "",
                            "trade_time": "2026-06-23 09:45:03",
                            "counterparty_name": "陈佳玉",
                            "debit_amount": "145.00",
                            "credit_amount": "",
                            "memo": "报销",
                            "bank_account": "建行 8106",
                            "available_actions": ["detail", "confirm_link", "mark_exception"],
                        }
                    ],
                    "invoice": [
                        {
                            "id": invoice_id,
                            "type": "invoice",
                            "case_id": "",
                            "seller_name": "云南铁路发展有限公司",
                            "buyer_name": "云南溯源科技有限公司",
                            "issue_date": "2026-05-06",
                            "invoice_type": "进项专票",
                            "amount": "145.00",
                            "total_with_tax": "145.00",
                            "available_actions": ["detail", "confirm_link", "mark_exception"],
                        }
                    ],
                },
                "exceptions": {"groups": []},
            },
            ignored_rows=[],
        )
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(
                AssertionError(f"confirm link must resolve {row_id} from the workbench row-detail boundary")
            )
        )
        app._workbench_row_detail_api_routes = None

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": [oa_id, bank_id, invoice_id],
                    "case_id": "CASE-FLAT-READ-MODEL-CONFIRM",
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        confirm_payload = json.loads(confirm_response.body)
        self.assertTrue(confirm_payload["success"])
        self.assertCountEqual(confirm_payload["affected_row_ids"], [oa_id, bank_id, invoice_id])
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(
            "CASE-FLAT-READ-MODEL-CONFIRM"
        )
        assert relation is not None
        self.assertCountEqual(relation["row_ids"], [oa_id, bank_id, invoice_id])

    def test_confirm_link_ignores_empty_row_ids_in_minimal_hot_path(self) -> None:
        app = build_application()

        response = app._handle_live_workbench_confirm_link(
            {
                "month": "2026-03",
                "row_ids": ["oa-o-202603-001", None, "  ", "bk-o-202603-001"],
                "case_id": "CASE-NORMALIZE-ROWIDS-001",
            }
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(
            payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001"],
        )

    def test_confirm_link_includes_existing_oa_attachment_context_rows(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-202605-attachment"
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-OA-ATT-oa-exp-202605-attachment"
        raw_payload["open"]["bank"][0]["id"] = "bk-o-202605-attachment"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-202605-attachment-01"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-OA-ATT-oa-exp-202605-attachment"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        raw_payload["open"]["invoice"][0]["derived_from_oa_id"] = "oa-exp-202605-attachment"

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-05").body)

        source_group = next(
            group
            for group in initial_payload["paired"]["groups"]
            if group["group_id"] == "case:CASE-OA-ATT-oa-exp-202605-attachment"
        )
        self.assertEqual(source_group["reason"], "existing_case_group")
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-exp-202605-attachment"])
        self.assertEqual(
            [row["id"] for row in source_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-attachment-01"],
        )

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": ["oa-exp-202605-attachment", "bk-o-202605-attachment"],
                    "case_id": "CASE-FULL-WITH-ATTACHMENT",
                }
            ),
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_group = preview_payload["after"]["groups"][0]
        self.assertCountEqual(
            [row["id"] for row in after_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-attachment-01"],
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": ["oa-exp-202605-attachment", "bk-o-202605-attachment"],
                    "case_id": "CASE-FULL-WITH-ATTACHMENT",
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [
                "oa-exp-202605-attachment",
                "bk-o-202605-attachment",
                "oa-att-inv-oa-exp-202605-attachment-01",
            ],
        )
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FULL-WITH-ATTACHMENT")
        assert relation is not None
        self.assertCountEqual(
            relation["row_ids"],
            [
                "oa-exp-202605-attachment",
                "bk-o-202605-attachment",
                "oa-att-inv-oa-exp-202605-attachment-01",
            ],
        )

    def test_confirm_link_includes_existing_oa_attachment_context_when_bank_and_invoice_selected(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="145.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-202605-invoice-first"
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-OA-ATT-oa-exp-202605-invoice-first"
        raw_payload["open"]["oa"][0]["applicant"] = "陈佳玉"
        raw_payload["open"]["oa"][0]["amount"] = "145.00"
        raw_payload["open"]["bank"][0]["id"] = "bk-o-202605-invoice-first"
        raw_payload["open"]["bank"][0]["debit_amount"] = "145.00"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-202605-invoice-first-01"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-OA-ATT-oa-exp-202605-invoice-first"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        raw_payload["open"]["invoice"][0]["derived_from_oa_id"] = "oa-exp-202605-invoice-first"
        raw_payload["open"]["invoice"][0]["total_with_tax"] = "145.00"

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-05").body)

        source_group = next(
            group
            for group in initial_payload["paired"]["groups"]
            if group["group_id"] == "case:CASE-OA-ATT-oa-exp-202605-invoice-first"
        )
        self.assertEqual([row["id"] for row in source_group["oa_rows"]], ["oa-exp-202605-invoice-first"])
        self.assertEqual(
            [row["id"] for row in source_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-invoice-first-01"],
        )

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": ["bk-o-202605-invoice-first", "oa-att-inv-oa-exp-202605-invoice-first-01"],
                    "case_id": "CASE-FULL-WITH-OA-CONTEXT",
                }
            ),
        )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_group = preview_payload["after"]["groups"][0]
        self.assertCountEqual(
            [row["id"] for row in after_group["oa_rows"]],
            ["oa-exp-202605-invoice-first"],
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": ["bk-o-202605-invoice-first", "oa-att-inv-oa-exp-202605-invoice-first-01"],
                    "case_id": "CASE-FULL-WITH-OA-CONTEXT",
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            [
                "oa-exp-202605-invoice-first",
                "bk-o-202605-invoice-first",
                "oa-att-inv-oa-exp-202605-invoice-first-01",
            ],
        )
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FULL-WITH-OA-CONTEXT")
        assert relation is not None
        self.assertCountEqual(
            relation["row_ids"],
            [
                "oa-exp-202605-invoice-first",
                "bk-o-202605-invoice-first",
                "oa-att-inv-oa-exp-202605-invoice-first-01",
            ],
        )
        row_type_by_id = dict(zip(relation["row_ids"], relation["row_types"], strict=True))
        self.assertEqual(row_type_by_id["oa-exp-202605-invoice-first"], "oa")
        self.assertEqual(row_type_by_id["bk-o-202605-invoice-first"], "bank")
        self.assertEqual(row_type_by_id["oa-att-inv-oa-exp-202605-invoice-first-01"], "invoice")

    def test_confirm_link_preview_does_not_expand_raw_oa_source_when_canonical_oa_is_selected(self) -> None:
        app = build_application()
        canonical_oa_id = "oa-exp-2156"
        raw_source_oa_id = "oa-exp-69fab21659b12d7d42a50a45"
        bank_id = "txn_imported_0405"
        invoice_id = f"oa-att-inv-{raw_source_oa_id}:item:0:fb2a9c9fab23-b515bf77d490fdfe"
        rows_by_id = {
            canonical_oa_id: {
                "id": canonical_oa_id,
                "type": "oa",
                "applicant": "陈佳玉",
                "project_name": "大型卷烟厂余热综合利用项目",
                "amount": "145.00",
                "reconciliation_amount": "145.00",
                "detail_fields": {
                    "Mongo文档ID": "69fab21659b12d7d42a50a45",
                    "OA单号": "2156",
                },
            },
            bank_id: {
                "id": bank_id,
                "type": "bank",
                "counterparty_name": "陈佳玉",
                "trade_time": "2026-06-23 09:45:03",
                "debit_amount": "145.00",
                "credit_amount": "",
            },
            invoice_id: {
                "id": invoice_id,
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": f"{raw_source_oa_id}:item:0:fb2a9c9fab23",
                "source_expense_item_id": f"{raw_source_oa_id}:item:0:fb2a9c9fab23",
                "source_workbench_row_id": invoice_id,
                "seller_name": "云南铁路发展有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-05-06",
                "amount": "145.00",
                "total_with_tax": "145.00",
            },
        }
        source_group = {
            "group_id": f"source:oa_attachment:{raw_source_oa_id}",
            "group_type": "candidate",
            "match_confidence": "high",
            "reason": "oa_attachment_source_relation",
            "oa_rows": [{"id": raw_source_oa_id, "type": "oa", "amount": "145.00"}],
            "bank_rows": [],
            "invoice_rows": [rows_by_id[invoice_id]],
        }
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-LEGACY-RAW-OA-SOURCE",
            row_ids=[raw_source_oa_id, bank_id, invoice_id],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="all",
        )

        def resolve_cached(row_ids: list[str], **_kwargs: object) -> dict[str, dict[str, object]]:
            return {
                row_id: dict(rows_by_id[row_id])
                for row_id in row_ids
                if row_id in rows_by_id
            }

        def row_detail(row_id: str, **_kwargs: object) -> dict[str, object]:
            if row_id not in rows_by_id:
                raise KeyError(row_id)
            return {"row": dict(rows_by_id[row_id])}

        with (
            patch.object(app, "_cached_existing_context_groups_for_row_ids", return_value=[source_group]),
            patch.object(app, "_resolve_rows_from_cached_read_models", side_effect=resolve_cached),
            patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail),
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link/preview",
                json.dumps(
                    {
                        "month": "all",
                        "row_ids": [canonical_oa_id, bank_id, invoice_id],
                        "case_id": "CASE-CANONICAL-OA-ATTACHMENT-PREVIEW",
                    }
                ),
            )

        self.assertEqual(response.status_code, 200, response.body)
        payload = json.loads(response.body)
        after_group = payload["after"]["groups"][0]
        self.assertEqual([row["id"] for row in after_group["oa_rows"]], [canonical_oa_id])
        self.assertEqual([row["id"] for row in after_group["bank_rows"]], [bank_id])
        self.assertEqual([row["id"] for row in after_group["invoice_rows"]], [invoice_id])
        after_row_ids = [
            row["id"]
            for row_key in ("oa_rows", "bank_rows", "invoice_rows")
            for row in after_group[row_key]
        ]
        self.assertNotIn(raw_source_oa_id, after_row_ids)

    def test_confirm_link_preview_maps_missing_row_to_row_not_found_error(self) -> None:
        app = build_application()

        def missing_row_detail(row_id: str, **_kwargs: object) -> dict[str, object]:
            raise KeyError(row_id)

        with (
            patch.object(app, "_resolve_rows_from_cached_read_models", return_value={}),
            patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=missing_row_detail),
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link/preview",
                json.dumps(
                    {
                        "month": "all",
                        "row_ids": ["oa-exp-missing", "txn_imported_missing"],
                        "case_id": "CASE-MISSING-ROW",
                    }
                ),
            )

        self.assertEqual(response.status_code, 400)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "workbench_row_not_found")
        self.assertEqual(payload["row_id"], "oa-exp-missing")

    def test_confirm_link_expands_oa_attachment_context_from_all_scope_read_model_when_month_filter_hides_invoice(self) -> None:
        app = build_application()
        oa_row = {
            "id": "oa-exp-202605-hidden-invoice",
            "type": "oa",
            "case_id": "CASE-OA-ATT-hidden-invoice",
            "amount": "100.00",
            "counterparty_name": "测试供应商",
        }
        bank_row = {
            "id": "bk-o-202605-hidden-invoice",
            "type": "bank",
            "case_id": "",
            "debit_amount": "100.00",
            "credit_amount": "",
            "counterparty_name": "测试供应商",
        }
        invoice_row = {
            "id": "oa-att-inv-oa-exp-202605-hidden-invoice-01",
            "type": "invoice",
            "case_id": "CASE-OA-ATT-hidden-invoice",
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-exp-202605-hidden-invoice",
            "amount": "100.00",
            "total_with_tax": "100.00",
        }
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-05",
            payload={
                "month": "2026-05",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 2,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "candidate:hidden-invoice",
                            "group_type": "candidate",
                            "match_confidence": "medium",
                            "reason": "selected_rows",
                            "oa_rows": [oa_row],
                            "bank_rows": [bank_row],
                            "invoice_rows": [],
                        }
                    ]
                },
            },
            ignored_rows=[],
        )
        app._workbench_read_model_service.upsert_read_model(
            scope_key="all",
            payload={
                "month": "all",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 1,
                    "paired_count": 0,
                    "open_count": 2,
                    "exception_count": 0,
                },
                "paired": {"groups": []},
                "open": {
                    "groups": [
                        {
                            "group_id": "case:CASE-OA-ATT-hidden-invoice",
                            "group_type": "candidate",
                            "match_confidence": "high",
                            "reason": "oa_attachment_source_relation",
                            "oa_rows": [oa_row],
                            "bank_rows": [],
                            "invoice_rows": [invoice_row],
                        }
                    ]
                },
            },
            ignored_rows=[],
        )

        request_body = {
            "month": "2026-05",
            "row_ids": ["oa-exp-202605-hidden-invoice", "bk-o-202605-hidden-invoice"],
            "case_id": "CASE-FULL-HIDDEN-INVOICE",
        }
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps(request_body),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_group = preview_payload["after"]["groups"][0]
        self.assertEqual(
            [row["id"] for row in after_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-hidden-invoice-01"],
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(request_body),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(
            confirm_payload["affected_row_ids"],
            [
                "oa-exp-202605-hidden-invoice",
                "bk-o-202605-hidden-invoice",
                "oa-att-inv-oa-exp-202605-hidden-invoice-01",
            ],
        )
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FULL-HIDDEN-INVOICE")
        assert relation is not None
        self.assertEqual(
            relation["row_ids"],
            [
                "oa-exp-202605-hidden-invoice",
                "bk-o-202605-hidden-invoice",
                "oa-att-inv-oa-exp-202605-hidden-invoice-01",
            ],
        )

    def test_confirm_link_includes_active_relation_rows_for_selected_oa_context(self) -> None:
        app = build_application()
        oa_row = {
            "id": "oa-exp-202605-active-context",
            "type": "oa",
            "case_id": "CASE-ACTIVE-OA-INVOICE",
            "amount": "100.00",
            "counterparty_name": "测试供应商",
        }
        bank_row = {
            "id": "bk-o-202605-active-context",
            "type": "bank",
            "case_id": "",
            "debit_amount": "100.00",
            "credit_amount": "",
            "counterparty_name": "测试供应商",
        }
        invoice_row = {
            "id": "oa-att-inv-oa-exp-202605-active-context-01",
            "type": "invoice",
            "case_id": "CASE-ACTIVE-OA-INVOICE",
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-exp-202605-active-context",
            "amount": "100.00",
            "total_with_tax": "100.00",
        }
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-05",
            payload={
                "month": "2026-05",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 1,
                    "invoice_count": 1,
                    "paired_count": 1,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {
                    "groups": [
                        {
                            "group_id": "case:CASE-ACTIVE-OA-INVOICE",
                            "group_type": "manual_confirmed",
                            "match_confidence": "high",
                            "reason": "relation_snapshot",
                            "oa_rows": [oa_row],
                            "bank_rows": [],
                            "invoice_rows": [invoice_row],
                        }
                    ]
                },
                "open": {
                    "groups": [
                        {
                            "group_id": "selected:bk-o-202605-active-context",
                            "group_type": "selection",
                            "match_confidence": "low",
                            "reason": "selected_row",
                            "oa_rows": [],
                            "bank_rows": [bank_row],
                            "invoice_rows": [],
                        }
                    ]
                },
            },
            ignored_rows=[],
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-ACTIVE-OA-INVOICE",
            row_ids=["oa-exp-202605-active-context", "oa-att-inv-oa-exp-202605-active-context-01"],
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        request_body = {
            "month": "2026-05",
            "row_ids": ["oa-exp-202605-active-context", "bk-o-202605-active-context"],
            "case_id": "CASE-ACTIVE-CONTEXT-FULL",
        }
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps(request_body),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_group = preview_payload["after"]["groups"][0]
        self.assertEqual(
            [row["id"] for row in after_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-active-context-01"],
        )
        before_group = next(
            group
            for group in preview_payload["before"]["groups"]
            if group["group_id"] == "case:CASE-ACTIVE-OA-INVOICE"
        )
        self.assertEqual(
            [row["id"] for row in before_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-active-context-01"],
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(request_body),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(
            confirm_payload["affected_row_ids"],
            [
                "oa-exp-202605-active-context",
                "bk-o-202605-active-context",
                "oa-att-inv-oa-exp-202605-active-context-01",
            ],
        )
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-ACTIVE-CONTEXT-FULL")
        assert relation is not None
        self.assertEqual(
            relation["row_ids"],
            [
                "oa-exp-202605-active-context",
                "bk-o-202605-active-context",
                "oa-att-inv-oa-exp-202605-active-context-01",
            ],
        )
        history = app._workbench_pair_relation_service.list_history()
        self.assertEqual(history[-1]["operation_type"], "confirm_link")
        self.assertEqual(history[-1]["before_relations"][0]["case_id"], "CASE-ACTIVE-OA-INVOICE")
        self.assertEqual(
            history[-1]["before_relations"][0]["row_ids"],
            ["oa-exp-202605-active-context", "oa-att-inv-oa-exp-202605-active-context-01"],
        )

    def test_open_group_with_active_partial_relation_is_withdrawable(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["paired"]["oa"] = [raw_payload["open"]["oa"][0]]
        raw_payload["paired"]["bank"] = [raw_payload["open"]["bank"][0]]
        raw_payload["open"]["oa"] = []
        raw_payload["open"]["bank"] = []
        raw_payload["open"]["invoice"] = []
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-PARTIAL-WITHDRAWABLE",
            row_ids=["oa-o-202605-001", "bk-o-202605-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-05")

        self.assertEqual(payload["paired"]["groups"], [])
        open_group = next(
            group
            for group in payload["open"]["groups"]
            if group["group_id"] == "case:CASE-PARTIAL-WITHDRAWABLE"
        )
        self.assertTrue(open_group["can_withdraw"])

    def test_read_model_repairs_active_relation_missing_oa_attachment_invoice(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-202605-repair"
        raw_payload["open"]["bank"][0]["id"] = "bk-o-202605-repair"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-202605-repair-01"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        raw_payload["open"]["invoice"][0]["derived_from_oa_id"] = "oa-exp-202605-repair"
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-REPAIR-MISSING-ATTACHMENT",
            row_ids=["oa-exp-202605-repair", "bk-o-202605-repair"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(app, "_build_oa_workbench_row_payload", return_value=raw_payload),
        ):
            payload = app._build_api_workbench_payload("2026-05")

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-REPAIR-MISSING-ATTACHMENT")
        assert relation is not None
        self.assertCountEqual(
            relation["row_ids"],
            ["oa-exp-202605-repair", "bk-o-202605-repair", "oa-att-inv-oa-exp-202605-repair-01"],
        )
        self.assertEqual(
            app._workbench_pair_relation_service.list_history()[-1]["operation_type"],
            "repair_missing_oa_attachment_context",
        )
        repaired_group = next(
            group
            for group in payload["paired"]["groups"]
            if group["group_id"] == "case:CASE-REPAIR-MISSING-ATTACHMENT"
        )
        self.assertEqual([row["id"] for row in repaired_group["oa_rows"]], ["oa-exp-202605-repair"])
        self.assertEqual([row["id"] for row in repaired_group["bank_rows"]], ["bk-o-202605-repair"])
        self.assertEqual(
            [row["id"] for row in repaired_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-repair-01"],
        )

    def test_read_model_repairs_active_relation_missing_parent_oa_for_attachment_invoice(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="145.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-202605-repair-parent"
        raw_payload["open"]["oa"][0]["amount"] = "145.00"
        raw_payload["open"]["bank"][0]["id"] = "bk-o-202605-repair-parent"
        raw_payload["open"]["bank"][0]["debit_amount"] = "145.00"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-202605-repair-parent-01"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        raw_payload["open"]["invoice"][0]["derived_from_oa_id"] = "oa-exp-202605-repair-parent"
        raw_payload["open"]["invoice"][0]["total_with_tax"] = "145.00"
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-REPAIR-MISSING-PARENT-OA",
            row_ids=["bk-o-202605-repair-parent", "oa-att-inv-oa-exp-202605-repair-parent-01"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(app, "_build_oa_workbench_row_payload", return_value=raw_payload),
        ):
            payload = app._build_api_workbench_payload("2026-05")

        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(
            "CASE-REPAIR-MISSING-PARENT-OA"
        )
        assert relation is not None
        self.assertCountEqual(
            relation["row_ids"],
            [
                "oa-exp-202605-repair-parent",
                "bk-o-202605-repair-parent",
                "oa-att-inv-oa-exp-202605-repair-parent-01",
            ],
        )
        self.assertEqual(
            app._workbench_pair_relation_service.list_history()[-1]["operation_type"],
            "repair_missing_oa_attachment_context",
        )
        repaired_group = next(
            group
            for group in payload["paired"]["groups"]
            if group["group_id"] == "case:CASE-REPAIR-MISSING-PARENT-OA"
        )
        self.assertEqual([row["id"] for row in repaired_group["oa_rows"]], ["oa-exp-202605-repair-parent"])
        self.assertEqual([row["id"] for row in repaired_group["bank_rows"]], ["bk-o-202605-repair-parent"])
        self.assertEqual(
            [row["id"] for row in repaired_group["invoice_rows"]],
            ["oa-att-inv-oa-exp-202605-repair-parent-01"],
        )

    def test_confirm_and_cancel_link_defer_read_model_persistence_to_background(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as schedule_pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-ASYNC-PERSIST-001",
                    "note": "async persist regression allows documented mismatch path",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        schedule_pair_relation_persist.assert_called_once()
        self.assertEqual(
            schedule_pair_relation_persist.call_args.kwargs,
            {
                "changed_case_ids": ["CASE-202603-102", "CASE-ASYNC-PERSIST-001"],
                "request_id": None,
                "action_name": "confirm_link",
            },
        )
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "confirm_link")

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist") as schedule_pair_relation_persist,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        schedule_pair_relation_persist.assert_called_once()
        self.assertEqual(
            schedule_pair_relation_persist.call_args.kwargs,
            {
                "changed_case_ids": ["CASE-ASYNC-PERSIST-001"],
                "request_id": None,
                "action_name": "cancel_link",
            },
        )
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "cancel_link")

    def test_mark_exception_invalidates_only_changed_scopes_and_rebuilds_in_background(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]

        with (
            patch.object(app, "_invalidate_workbench_read_models") as invalidate_all_read_models,
            patch.object(app, "_invalidate_workbench_read_model_scopes") as invalidate_read_model_scopes,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/mark-exception",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_id": oa_row["id"],
                        "exception_code": "pending_collection",
                        "comment": "客户尚未付款",
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        invalidate_all_read_models.assert_not_called()
        invalidate_read_model_scopes.assert_called_once()
        self.assertCountEqual(invalidate_read_model_scopes.call_args.args[0], ["2026-03", "all"])
        schedule_read_model_persist.assert_called_once()
        # The lifecycle invalidation above still covers all; the operation-level
        # persist target stays month-scoped so browser barriers do not wait on all.
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "mark_exception")

    def test_oa_bank_exception_invalidates_only_changed_scopes_and_rebuilds_in_background(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]

        with (
            patch.object(app, "_invalidate_workbench_read_models") as invalidate_all_read_models,
            patch.object(app, "_invalidate_workbench_read_model_scopes") as invalidate_read_model_scopes,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/oa-bank-exception",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_ids": [oa_row["id"], bank_row["id"]],
                        "exception_code": "oa_bank_amount_mismatch",
                        "exception_label": "金额不一致，继续异常",
                        "comment": "付款金额与OA金额不一致，继续核查",
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        invalidate_all_read_models.assert_not_called()
        invalidate_read_model_scopes.assert_called_once()
        self.assertCountEqual(invalidate_read_model_scopes.call_args.args[0], ["2026-03", "all"])
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "oa_bank_exception")

    def test_cancel_exception_invalidates_only_changed_scopes_and_rebuilds_in_background(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]

        exception_response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "测试异常处理",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)

        with (
            patch.object(app, "_invalidate_workbench_read_models") as invalidate_all_read_models,
            patch.object(app, "_invalidate_workbench_read_model_scopes") as invalidate_read_model_scopes,
            patch.object(app, "_schedule_workbench_read_model_persist") as schedule_read_model_persist,
        ):
            cancel_response = app.handle_request(
                "POST",
                "/api/workbench/actions/cancel-exception",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_ids": [oa_row["id"], bank_row["id"]],
                        "comment": "撤回异常处理",
                    }
                ),
            )

        self.assertEqual(cancel_response.status_code, 200)
        invalidate_all_read_models.assert_not_called()
        invalidate_read_model_scopes.assert_called_once()
        self.assertCountEqual(invalidate_read_model_scopes.call_args.args[0], ["2026-03", "all"])
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
        )
        self.assertIsNone(schedule_read_model_persist.call_args.kwargs["request_id"])
        self.assertEqual(schedule_read_model_persist.call_args.kwargs["action_name"], "cancel_exception")

    def test_confirm_link_emits_phased_timing_logs(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
            patch.object(app, "_emit_workbench_action_timing") as emit_timing,
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps(
                    {
                        "month": "2026-03",
                        "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                        "case_id": "CASE-TIMING-CONFIRM-001",
                        "note": "timing regression covers documented mismatch path",
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        phases = [call.kwargs["phase"] for call in emit_timing.call_args_list]
        self.assertIn("oa_auth", phases)
        self.assertIn("resolve_rows", phases)
        self.assertIn("pair_relation_update", phases)
        self.assertIn("invalidate_read_model_scopes", phases)
        self.assertIn("schedule_background_persist", phases)
        self.assertIn("request_total", phases)

    def test_background_persist_emits_timing_logs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="CASE-TIMING-BG-001",
                row_ids=["oa-o-202603-001", "txn-o-202603-001"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope="2026-03",
            )
            payload = app._build_api_workbench_payload("2026-03")
            app._workbench_read_model_service.upsert_read_model(scope_key="2026-03", payload=payload, ignored_rows=[])
            app._workbench_read_model_service.upsert_read_model(scope_key="all", payload=payload, ignored_rows=[])

            app._workbench_pair_relation_persist_version = 1
            app._workbench_read_model_persist_version = 1

            with patch.object(app, "_emit_workbench_action_timing") as emit_timing:
                app._persist_workbench_pair_relations_in_background(
                    version=1,
                    case_ids=["CASE-TIMING-BG-001"],
                    request_id="req-bg-001",
                    action_name="confirm_link",
                )
                app._rebuild_workbench_read_models_in_background(
                    version=1,
                    scope_keys=["2026-03", "all"],
                    request_id="req-bg-001",
                    action_name="confirm_link",
                )

        phases = [call.kwargs["phase"] for call in emit_timing.call_args_list]
        self.assertIn("persist_pair_relations", phases)
        self.assertIn("rebuild_read_model_scope", phases)
        self.assertIn("persist_read_models", phases)
        self.assertIn("background_total", phases)

    def test_confirm_and_cancel_link_rebuild_live_cache_only_once_per_action(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-SINGLE-REBUILD-001",
                    "note": "cache rebuild regression covers documented mismatch path",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": bank_row["id"],
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

    def test_cancel_link_does_not_resolve_source_rows_in_hot_path(self) -> None:
        app = build_application()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-MINIMAL-CANCEL-001",
            row_ids=["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="2026-03",
        )

        with patch.object(app, "_resolve_live_rows_direct", side_effect=AssertionError("should not resolve source rows")):
            cancel_response = app._handle_live_workbench_cancel_link(
                {
                    "month": "2026-03",
                    "row_id": "bk-o-202603-001",
                    "comment": "reopen",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertCountEqual(
            cancel_payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
        )
        self.assertNotIn("updated_rows", cancel_payload)

    def test_cancel_exception_resolves_selected_rows_without_rebuilding_grouped_workbench(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        exception_response = app._handle_live_workbench_oa_bank_exception(
            {
                "month": "2026-03",
                "row_ids": [oa_row["id"], bank_row["id"]],
                "exception_code": "oa_bank_amount_mismatch",
                "exception_label": "金额不一致，继续异常",
                "comment": "测试异常处理",
            }
        )
        self.assertEqual(exception_response.status_code, 200)

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            cancel_response = app._handle_live_workbench_cancel_exception(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "comment": "撤回异常处理",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertCountEqual(cancel_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])
        self.assertEqual(cancel_payload["action"], "cancel_exception")

    def test_oa_bank_exception_resolves_selected_rows_without_rebuilding_grouped_workbench(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        with patch.object(app, "_build_api_workbench_payload", side_effect=AssertionError("should not rebuild workbench")):
            exception_response = app._handle_live_workbench_oa_bank_exception(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "测试异常处理",
                }
            )

        self.assertEqual(exception_response.status_code, 200)
        exception_payload = json.loads(exception_response.body)
        self.assertTrue(exception_payload["success"])
        self.assertCountEqual(exception_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])
        self.assertEqual(exception_payload["action"], "oa_bank_exception")

    def test_oa_bank_exception_prefers_cached_read_model_rows_before_query_service(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        app._workbench_query_service._records_by_id.pop(oa_row["id"], None)
        app._workbench_query_service._records_by_id.pop(bank_row["id"], None)

        with (
            patch.object(
                app._workbench_query_service,
                "get_row_record",
                side_effect=AssertionError("should not hit query service when cached read model has selected rows"),
            ),
            patch.object(
                app._live_workbench_service,
                "get_rows_detail",
                side_effect=AssertionError("should not hit live row detail when cached read model has selected rows"),
            ),
        ):
            response = app._handle_live_workbench_oa_bank_exception(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "测试异常处理",
                }
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_bank_exception")
        self.assertCountEqual(payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])

    def test_cancel_exception_does_not_full_sync_all_oa_rows_after_read_model_invalidation(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        app._workbench_query_service._records_by_id.pop(oa_row["id"], None)

        exception_response = app._handle_live_workbench_oa_bank_exception(
            {
                "month": "2026-03",
                "row_ids": [oa_row["id"], bank_row["id"]],
                "exception_code": "oa_bank_amount_mismatch",
                "exception_label": "金额不一致，继续异常",
                "comment": "测试异常处理",
            }
        )
        self.assertEqual(exception_response.status_code, 200)

        app._workbench_query_service._records_by_id.pop(oa_row["id"], None)

        with patch.object(
            app._workbench_query_service,
            "_sync_all_oa_rows",
            side_effect=AssertionError("cancel_exception should not fall back to full OA sync"),
        ):
            cancel_response = app._handle_live_workbench_cancel_exception(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "comment": "撤回异常处理",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_exception")
        self.assertCountEqual(cancel_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])

    def test_cancel_exception_resolves_all_scope_bank_rows_without_oa_query_service(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="cancel-exception-bank-fast-path.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220031",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 09:00:00",
                    "pay_receive_time": "2026-03-10 09:00:00",
                    "counterparty_name": "测试取消异常流水",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "summary": "测试取消异常流水",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        bank_row_id = next(
            transaction.id
            for transaction in app._import_service.list_transactions()
            if transaction.source_batch_id == preview.id
        )
        app.handle_request("GET", "/api/workbench?month=all")

        exception_response = app._handle_live_workbench_oa_bank_exception(
            {
                "month": "all",
                "row_ids": [bank_row_id],
                "exception_code": "oa_bank_amount_mismatch",
                "exception_label": "金额不一致，继续异常",
                "comment": "测试异常处理",
            }
        )
        self.assertEqual(exception_response.status_code, 200)

        with patch.object(
            app._workbench_query_service,
            "get_row_record",
            side_effect=AssertionError("bank rows should resolve from live detail without OA query service"),
        ):
            cancel_response = app._handle_live_workbench_cancel_exception(
                {
                    "month": "all",
                    "row_ids": [bank_row_id],
                    "comment": "撤回异常处理",
                }
            )

        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_exception")
        self.assertEqual(cancel_payload["affected_row_ids"], [bank_row_id])

    def test_confirm_link_rebuilds_live_cache_once_for_multiple_live_rows(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="multi-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220031",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 09:00:00",
                    "pay_receive_time": "2026-03-10 09:00:00",
                    "counterparty_name": "测试对方A",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "summary": "测试流水A",
                },
                {
                    "account_no": "62220032",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-10",
                    "trade_time": "2026-03-10 09:05:00",
                    "pay_receive_time": "2026-03-10 09:05:00",
                    "counterparty_name": "测试对方B",
                    "debit_amount": "",
                    "credit_amount": "100.00",
                    "summary": "测试流水B",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions() if transaction.source_batch_id == preview.id]

        with patch.object(
            app._live_workbench_service,
            "get_rows_detail",
            wraps=app._live_workbench_service.get_rows_detail,
        ) as get_rows_detail:
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-LIVE-BULK-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        get_rows_detail.assert_called_once_with(row_ids)

    def test_cancel_exception_returns_processed_rows_to_open_state(self) -> None:
        app = build_application()
        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)

        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(initial_payload["open"]["groups"], "bank")[0]

        exception_response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "测试异常处理",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "comment": "撤回异常处理",
                }
            ),
        )
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = json.loads(cancel_response.body)
        self.assertTrue(cancel_payload["success"])
        self.assertEqual(cancel_payload["action"], "cancel_exception")
        self.assertEqual(cancel_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])
        self.assertEqual(cancel_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(cancel_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            cancel_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        updated_oa = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank = next(row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"])

        self.assertFalse(updated_oa.get("handled_exception", False))
        self.assertFalse(updated_bank.get("handled_exception", False))
        self.assertEqual(updated_oa["oa_bank_relation"]["tone"], "warn")
        self.assertEqual(updated_bank["invoice_relation"]["tone"], "warn")

    def test_live_oa_bank_exception_keeps_rows_in_open_processed_exception_state(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()

        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = next(
            row for row in flatten_groups(initial_payload["open"]["groups"], "bank") if row["id"] == "txn-live-202603-001"
        )

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "付款金额与OA金额不一致，继续核查",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertEqual(updated_payload["summary"]["paired_count"], 0)
        updated_oa = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank = next(
            row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"]
        )

        self.assertTrue(updated_oa.get("handled_exception", False))
        self.assertTrue(updated_bank.get("handled_exception", False))
        self.assertEqual(updated_oa["oa_bank_relation"]["tone"], "danger")
        self.assertEqual(updated_bank["invoice_relation"]["tone"], "danger")

    def test_cancel_exception_keeps_live_rows_in_open_state_after_revert(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()

        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]
        bank_row = next(
            row for row in flatten_groups(initial_payload["open"]["groups"], "bank") if row["id"] == "txn-live-202603-001"
        )

        exception_response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "付款金额与OA金额不一致，继续核查",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)

        cancel_response = app.handle_request(
            "POST",
            "/api/workbench/actions/cancel-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "comment": "撤回异常处理",
                }
            ),
        )
        self.assertEqual(cancel_response.status_code, 200)

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertEqual(updated_payload["summary"]["paired_count"], 0)
        updated_oa = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank = next(
            row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"]
        )

        self.assertFalse(updated_oa.get("handled_exception", False))
        self.assertFalse(updated_bank.get("handled_exception", False))
        self.assertEqual(updated_oa["oa_bank_relation"]["tone"], "warn")
        self.assertEqual(updated_bank["invoice_relation"]["tone"], "warn")

    def test_confirm_link_supports_live_workbench_rows(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()

        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertTrue(
            any(
                row["id"] == "txn-live-202603-001"
                for row in flatten_groups(initial_payload["open"]["groups"], "bank")
            )
        )

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": ["oa-o-202603-001", "txn-live-202603-001"],
                    "case_id": "CASE-LIVE-202603-001",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "txn-live-202603-001"])

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        paired_oa_ids = [row["id"] for row in flatten_groups(updated_payload["paired"]["groups"], "oa")]
        paired_bank_ids = [row["id"] for row in flatten_groups(updated_payload["paired"]["groups"], "bank")]
        self.assertNotIn("oa-o-202603-001", paired_oa_ids)
        self.assertNotIn("txn-live-202603-001", paired_bank_ids)
        open_group = next(
            group
            for group in updated_payload["open"]["groups"]
            if any(row["id"] == "txn-live-202603-001" for row in group["bank_rows"])
        )
        self.assertEqual(open_group["group_type"], "candidate")
        self.assertEqual([row["id"] for row in open_group["oa_rows"]], ["oa-o-202603-001"])
        self.assertEqual([row["id"] for row in open_group["bank_rows"]], ["txn-live-202603-001"])
        self.assertEqual(open_group["invoice_rows"], [])
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id("txn-live-202603-001")
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "manual_confirmed")

    def test_confirm_link_falls_back_to_underlying_live_row_services_when_group_payload_is_missing_selected_rows(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()
        app._workbench_row_detail_api_routes = app._build_workbench_row_detail_api_routes()

        original_build_api_workbench_payload = app._build_api_workbench_payload

        def _build_payload_without_selected_rows(month: str) -> dict[str, object]:
            payload = original_build_api_workbench_payload(month)
            for section in ("paired", "open"):
                for group in payload[section]["groups"]:
                    group["oa_rows"] = [row for row in group["oa_rows"] if row["id"] != "oa-o-202603-001"]
                    group["bank_rows"] = [row for row in group["bank_rows"] if row["id"] != "txn-live-202603-001"]
            return payload

        app._build_api_workbench_payload = _build_payload_without_selected_rows

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": ["oa-o-202603-001", "txn-live-202603-001"],
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "txn-live-202603-001"])

    def test_ignore_and_unignore_invoice_moves_row_between_open_and_ignored_views(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        ignore_response = app.handle_request(
            "POST",
            "/api/workbench/actions/ignore-row",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": invoice_row["id"],
                    "comment": "暂不处理这张票",
                }
            ),
        )
        self.assertEqual(ignore_response.status_code, 200)
        ignore_payload = json.loads(ignore_response.body)
        self.assertTrue(ignore_payload["success"])
        self.assertEqual(ignore_payload["action"], "ignore_row")
        self.assertEqual(ignore_payload["exception_case_ids"], [ignore_payload["exception_case_id"]])
        self.assertEqual(ignore_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(ignore_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            ignore_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        ignored_case = app._workbench_exception_case_service.snapshot()["cases"][ignore_payload["exception_case_id"]]
        self.assertEqual(ignored_case["status"], "ignored")

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertNotIn(invoice_row["id"], [row["id"] for row in flatten_groups(updated_payload["open"]["groups"], "invoice")])

        ignored_response = app.handle_request("GET", "/api/workbench/ignored?month=2026-03")
        self.assertEqual(ignored_response.status_code, 200)
        ignored_payload = json.loads(ignored_response.body)
        self.assertIn(invoice_row["id"], [row["id"] for row in ignored_payload["rows"]])

        unignore_response = app.handle_request(
            "POST",
            "/api/workbench/actions/unignore-row",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": invoice_row["id"],
                }
            ),
        )
        self.assertEqual(unignore_response.status_code, 200)
        unignore_payload = json.loads(unignore_response.body)
        self.assertTrue(unignore_payload["success"])
        self.assertEqual(unignore_payload["action"], "unignore_row")
        self.assertEqual(unignore_payload["exception_case_ids"], [ignore_payload["exception_case_id"]])
        self.assertEqual(unignore_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(unignore_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            unignore_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        unignored_case = app._workbench_exception_case_service.snapshot()["cases"][ignore_payload["exception_case_id"]]
        self.assertEqual(unignored_case["status"], "cancelled")

        restored_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        self.assertIn(invoice_row["id"], [row["id"] for row in flatten_groups(restored_payload["open"]["groups"], "invoice")])

    def test_oa_bank_exception_updates_selected_oa_and_bank_rows(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "付款金额与OA金额不一致，继续核查",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        response_payload = json.loads(response.body)
        self.assertTrue(response_payload["success"])
        self.assertEqual(response_payload["action"], "oa_bank_exception")
        self.assertEqual(response_payload["affected_row_ids"], [oa_row["id"], bank_row["id"]])
        self.assertEqual(response_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(response_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            response_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        self.assertEqual(response_payload["exception_case_ids"], [response_payload["exception_case_id"]])
        exception_case = app._workbench_exception_case_service.snapshot()["cases"][response_payload["exception_case_id"]]
        self.assertEqual(exception_case["status"], "open")
        self.assertEqual(exception_case["rule_version"], "exception_rules_v1")
        self.assertEqual(exception_case["resolution"]["action_code"], "manual_review")
        self.assertEqual(exception_case["resolution"]["legacy_exception_code"], "oa_bank_amount_mismatch")
        self.assertEqual(exception_case["row_ids"], [oa_row["id"], bank_row["id"]])

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        updated_oa_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"])
        self.assertEqual(updated_oa_row["oa_bank_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_oa_row["oa_bank_relation"]["label"], "金额不一致，继续异常")
        self.assertEqual(updated_bank_row["invoice_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_bank_row["invoice_relation"]["label"], "金额不一致，继续异常")

    def test_oa_bank_exception_accepts_invoice_rows_for_legacy_compatibility(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                    "comment": "带发票的旧入口兼容",
                }
            ),
        )

        self.assertEqual(response.status_code, 200)
        response_payload = json.loads(response.body)
        self.assertTrue(response_payload["success"])
        self.assertEqual(response_payload["action"], "oa_bank_exception")
        self.assertCountEqual(response_payload["affected_row_ids"], [oa_row["id"], bank_row["id"], invoice_row["id"]])
        self.assertEqual(response_payload["affected_scope_keys"], ["2026-03"])
        self.assertEqual(response_payload["read_model_scope_keys"], ["2026-03"])
        self.assertEqual(
            response_payload["operation_barrier_targets"],
            [{"read_model_key": "workbench_relation", "scope_key": "2026-03"}],
        )
        self.assertIn(response_payload["exception_case_id"], app._workbench_exception_case_service.snapshot()["cases"])

    def test_confirm_link_supports_cross_month_selection_in_all_time_view(self) -> None:
        app = build_application()

        confirm_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "all",
                    "row_ids": ["oa-o-202603-001", "bk-o-202604-001"],
                    "case_id": "CASE-CROSS-MONTH-001",
                    "note": "cross-month regression covers documented mismatch path",
                }
            ),
        )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["action"], "confirm_link")
        self.assertEqual(confirm_payload["month"], "all")
        self.assertEqual(confirm_payload["affected_row_ids"], ["oa-o-202603-001", "bk-o-202604-001"])

    def test_mark_exception_returns_503_and_keeps_workbench_loadable_when_override_persist_fails(self) -> None:
        app = build_application()
        app._live_workbench_service = _StubLiveWorkbenchService()
        app._state_store = _FailingOverrideStateStore()

        initial_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        oa_row = flatten_groups(initial_payload["open"]["groups"], "oa")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/mark-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_id": oa_row["id"],
                    "exception_code": "pending_match",
                    "comment": "测试持久化失败",
                }
            ),
        )

        self.assertEqual(response.status_code, 503)
        payload = json.loads(response.body)
        self.assertEqual(payload["error"], "workbench_state_persistence_unavailable")

        reloaded_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        reloaded_oa = next(row for row in flatten_groups(reloaded_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        self.assertFalse(reloaded_oa.get("handled_exception", False))
        self.assertEqual(reloaded_oa["oa_bank_relation"]["tone"], "warn")
        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], {})

    def test_get_api_workbench_uses_in_memory_read_model_when_read_model_persist_fails(self) -> None:
        app = build_application()
        app._state_store = _FailingReadModelStateStore()

        response = app.handle_request("GET", "/api/workbench?month=2026-03")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["month"], "2026-03")
        self.assertGreater(payload["summary"]["open_count"], 0)
        self.assertIsNotNone(app._workbench_read_model_service.get_read_model("2026-03"))

    def test_oa_retention_filters_only_unrelated_old_oa_and_can_reinclude_after_new_bank_relation(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-01-01"},
        )
        old_oa = build_oa_retention_oa_row("oa-old-001", "CASE-OLD-001", "2025-12-20")
        recent_oa = build_oa_retention_oa_row("oa-recent-001", "CASE-RECENT-001", "2026-01-03")
        old_bank = build_oa_retention_bank_row("bank-old-001", "CASE-OLD-001", "2025-12-22 09:00:00")
        recent_oa_invoice = build_oa_retention_invoice_row("invoice-recent-001", "CASE-RECENT-001", "2026-01-04")
        initial_grouped_payload = app._group_row_payload(
            build_oa_retention_raw_payload(
                oa_rows=[old_oa, recent_oa],
                bank_rows=[old_bank],
                invoice_rows=[recent_oa_invoice],
            )
        )

        initial_payload = app._apply_oa_retention_to_grouped_payload(
            initial_grouped_payload
        )
        initial_oa_ids = [row["id"] for row in flatten_groups(initial_payload["open"]["groups"], "oa")]
        initial_bank_ids = [row["id"] for row in flatten_groups(all_groups(initial_payload), "bank")]
        initial_invoice_ids = [row["id"] for row in flatten_groups(all_groups(initial_payload), "invoice")]

        self.assertNotIn("oa-old-001", initial_oa_ids)
        self.assertIn("oa-recent-001", initial_oa_ids)
        self.assertIn("bank-old-001", initial_bank_ids)
        self.assertIn("invoice-recent-001", initial_invoice_ids)
        self.assertEqual(initial_payload["summary"]["oa_count"], 1)

        app._workbench_read_model_service.upsert_read_model(scope_key="all", payload=initial_grouped_payload)
        filtered_cached_payload = app._build_api_workbench_payload("all")
        cached_read_model = app._workbench_read_model_service.get_read_model("all")
        self.assertNotIn("oa-old-001", [row["id"] for row in flatten_groups(filtered_cached_payload["open"]["groups"], "oa")])
        self.assertIn(
            "oa-old-001",
            [row["id"] for row in flatten_groups(all_groups(cached_read_model["payload"]), "oa")],
        )

        related_recent_bank = build_oa_retention_bank_row("bank-recent-001", "CASE-OLD-001", "2026-01-05 10:00:00")
        refreshed_payload = app._apply_oa_retention_to_grouped_payload(
            app._group_row_payload(
                build_oa_retention_raw_payload(
                    oa_rows=[old_oa, recent_oa],
                    bank_rows=[old_bank, related_recent_bank],
                    invoice_rows=[recent_oa_invoice],
                )
            )
        )
        refreshed_oa_ids = [row["id"] for row in flatten_groups(refreshed_payload["open"]["groups"], "oa")]
        refreshed_bank_ids = [row["id"] for row in flatten_groups(all_groups(refreshed_payload), "bank")]

        self.assertIn("oa-old-001", refreshed_oa_ids)
        self.assertIn("oa-recent-001", refreshed_oa_ids)
        self.assertIn("bank-recent-001", refreshed_bank_ids)
        self.assertEqual(refreshed_payload["summary"]["oa_count"], 2)

    def test_oa_retention_keeps_manual_imported_oa_and_derived_attachment_invoice_in_grouped_payload(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-03-01"},
        )
        app._oa_manual_import_service = SimpleNamespace(manual_retained_row_ids=lambda: ["oa-exp-1981"])
        oa_row = build_oa_retention_oa_row("oa-exp-1981", "CASE-OA-1981", "2025-12-23")
        attachment_invoice_row = {
            **build_oa_retention_invoice_row(
                "oa-att-inv-oa-exp-1981-001",
                "CASE-OA-1981",
                "2025-12-23",
            ),
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-exp-1981",
        }
        grouped_payload = {
            "month": "all",
            "summary": {
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 1,
                "paired_count": 0,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {"groups": []},
            "open": {
                "groups": [
                    {
                        "id": "open-source-linked-oa-exp-1981",
                        "group_type": "source_linked",
                        "oa_rows": [oa_row],
                        "bank_rows": [],
                        "invoice_rows": [attachment_invoice_row],
                    }
                ]
            },
        }

        payload = app._apply_oa_retention_to_grouped_payload(grouped_payload)

        group = payload["open"]["groups"][0]
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-exp-1981"])
        self.assertEqual([row["id"] for row in group["invoice_rows"]], ["oa-att-inv-oa-exp-1981-001"])
        self.assertEqual(payload["summary"]["oa_count"], 1)
        self.assertEqual(payload["summary"]["invoice_count"], 1)

    def test_oa_retention_filters_attachment_invoice_when_derived_old_oa_is_filtered(self) -> None:
        app = build_application()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-03-01"},
        )
        app._oa_manual_import_service = SimpleNamespace(manual_retained_row_ids=lambda: [])
        oa_row = build_oa_retention_oa_row("oa-exp-1981", "CASE-OA-1981", "2025-12-23")
        attachment_invoice_row = {
            **build_oa_retention_invoice_row(
                "oa-att-inv-oa-exp-1981-001",
                "CASE-OA-1981",
                "2025-12-23",
            ),
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-exp-1981",
        }
        grouped_payload = {
            "month": "all",
            "summary": {
                "oa_count": 1,
                "bank_count": 0,
                "invoice_count": 1,
                "paired_count": 0,
                "open_count": 1,
                "exception_count": 0,
            },
            "paired": {"groups": []},
            "open": {
                "groups": [
                    {
                        "id": "open-source-linked-oa-exp-1981",
                        "group_type": "source_linked",
                        "oa_rows": [oa_row],
                        "bank_rows": [],
                        "invoice_rows": [attachment_invoice_row],
                    }
                ]
            },
        }

        payload = app._apply_oa_retention_to_grouped_payload(grouped_payload)

        self.assertEqual(payload["open"]["groups"], [])
        self.assertEqual(payload["summary"]["oa_count"], 0)
        self.assertEqual(payload["summary"]["invoice_count"], 0)

    def test_oa_attachment_invoice_cache_update_marks_related_scopes_dirty_without_evicting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(scope_key="all", payload={"month": "all"})
            app._workbench_read_model_service.upsert_read_model(scope_key="2026-03", payload={"month": "2026-03"})
            enqueued: list[dict[str, object]] = []
            app._runtime_repositories = SimpleNamespace(
                queue_repository=SimpleNamespace(enqueue=lambda **kwargs: enqueued.append(kwargs))
            )

            app._handle_oa_attachment_invoice_cache_updated(["2026-03"])
            app._app_status_runtime_statuses = lambda: {
                "read_model_statuses": None,
                "outbox_statuses": {
                    "oa.sync": {
                        "status": "pending",
                        "count": len(enqueued),
                        "scopes": [
                            {
                                "event_type": event["event_type"],
                                "scope_type": event["scope_type"],
                                "scope_key": event["scope_key"],
                                "status": "pending",
                                "count": 1,
                            }
                            for event in enqueued
                        ],
                    }
                },
                "worker_statuses": {"oa-sync": {"status": "ready"}},
            }
            app._postgres_oa_projection_latest_sync_run = lambda: None
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)

        self.assertIsNotNone(app._workbench_read_model_service.get_read_model("all"))
        self.assertIsNotNone(app._workbench_read_model_service.get_read_model("2026-03"))
        self.assertEqual([event["event_type"] for event in enqueued], ["oa.sync", "oa.sync"])
        self.assertCountEqual([event["scope_key"] for event in enqueued], ["2026-03", "all"])
        self.assertEqual(status_payload["status"], "refreshing")
        self.assertCountEqual(status_payload["dirty_scopes"], ["2026-03", "all"])

    def test_oa_attachment_invoice_cache_update_does_not_create_missing_invoice_by_default(self) -> None:
        attachment_invoice = {
            "source_attachment_key": "oa-exp-202603-001:file:1",
            "source_attachment_name": "发票.pdf",
            "evidence_type": "tax_invoice",
            "invoice_type": "进项发票",
            "seller_name": "云南城建物业运营集团",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-06",
            "invoice_no": "26532000000021026521",
            "amount": "566.04",
            "total_with_tax": "600.00",
        }
        oa_record = OAApplicationRecord(
            id="oa-exp-202603-001",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="刘际涛",
            project_name="冷水机组维护",
            apply_type="付款申请",
            amount="600.00",
            counterparty_name="云南城建物业运营集团",
            reason="维护费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            attachment_invoices=[attachment_invoice],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_query_service._oa_adapter = InMemoryOAAdapter({"2026-03": [oa_record]})

            with patch.object(app, "_enqueue_oa_projection_sync_refresh"):
                app._handle_oa_attachment_invoice_cache_updated(["2026-03"])

            invoices = app._import_service.list_invoices()

        self.assertEqual(invoices, [])

    def test_oa_attachment_invoice_cache_update_disabled_mode_skips_promotion(self) -> None:
        attachment_invoice = {
            "source_attachment_key": "oa-exp-202603-001:file:1",
            "source_attachment_name": "发票.pdf",
            "evidence_type": "tax_invoice",
            "invoice_type": "进项发票",
            "seller_name": "云南城建物业运营集团",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-06",
            "invoice_no": "26532000000021026521",
            "amount": "566.04",
            "total_with_tax": "600.00",
        }
        oa_record = OAApplicationRecord(
            id="oa-exp-202603-001",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="刘际涛",
            project_name="冷水机组维护",
            apply_type="付款申请",
            amount="600.00",
            counterparty_name="云南城建物业运营集团",
            reason="维护费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            attachment_invoices=[attachment_invoice],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_import={"attachment_invoice_promotion_mode": "disabled"},
                workbench_column_layouts={},
            )
            app._workbench_query_service._oa_adapter = InMemoryOAAdapter({"2026-03": [oa_record]})

            with (
                patch.object(app._import_service, "upsert_oa_attachment_invoice") as upsert_invoice,
                patch.object(app, "_enqueue_oa_projection_sync_refresh"),
            ):
                app._handle_oa_attachment_invoice_cache_updated(["2026-03"])

            invoices = app._import_service.list_invoices()

        upsert_invoice.assert_not_called()
        self.assertEqual(invoices, [])

    def test_oa_attachment_invoice_cache_update_create_missing_mode_promotes_formal_invoice(self) -> None:
        attachment_invoice = {
            "source_attachment_key": "oa-exp-202603-001:file:1",
            "source_attachment_name": "发票.pdf",
            "evidence_type": "tax_invoice",
            "invoice_type": "进项发票",
            "seller_name": "云南城建物业运营集团",
            "seller_tax_no": "91530103MA6KHJWK8C",
            "buyer_name": "云南溯源科技有限公司",
            "buyer_tax_no": "915300007194052520",
            "issue_date": "2026-03-06",
            "invoice_no": "26532000000021026521",
            "tax_rate": "6%",
            "tax_amount": "33.96",
            "amount": "566.04",
            "total_with_tax": "600.00",
        }
        receipt = {
            "source_attachment_key": "oa-exp-202603-001:file:2",
            "source_attachment_name": "付款截图.jpg",
            "evidence_type": "payment_receipt",
            "issue_date": "2026-03-06",
            "amount": "600.00",
        }
        oa_record = OAApplicationRecord(
            id="oa-exp-202603-001",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="刘际涛",
            project_name="冷水机组维护",
            apply_type="付款申请",
            amount="600.00",
            counterparty_name="云南城建物业运营集团",
            reason="维护费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            attachment_invoices=[attachment_invoice, receipt],
        )
        expected_row_id = FinancialObjectIdentityPolicy.oa_attachment_invoice_row_id(
            oa_record.id,
            0,
            attachment_invoice,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=[],
                readonly_export_usernames=[],
                admin_usernames=[],
                oa_import={"attachment_invoice_promotion_mode": "create_missing"},
                workbench_column_layouts={},
            )
            app._workbench_query_service._oa_adapter = InMemoryOAAdapter({"2026-03": [oa_record]})

            with patch.object(app, "_enqueue_oa_projection_sync_refresh"):
                app._handle_oa_attachment_invoice_cache_updated(["2026-03"])

            invoices = app._import_service.list_invoices()

        self.assertEqual([invoice.id for invoice in invoices], [expected_row_id])
        invoice = invoices[0]
        self.assertEqual(invoice.invoice_no, "26532000000021026521")
        self.assertEqual(invoice.seller_name, "云南城建物业运营集团")
        self.assertEqual(invoice.tags, ["OA附件"])
        self.assertEqual(invoice.source_links[0]["source_type"], "oa_attachment_invoice")
        self.assertEqual(invoice.source_links[0]["source_workbench_row_id"], expected_row_id)
        self.assertEqual(invoice.source_links[0]["derived_from_oa_id"], "oa-exp-202603-001")
        self.assertEqual(invoice.source_links[0]["source_attachment_key"], "oa-exp-202603-001:file:1")

    def test_oa_attachment_invoice_cache_update_ignores_incomplete_ocr_identity(self) -> None:
        partial_invoice = {
            "source_attachment_key": "oa-exp-202603-001:file:1",
            "source_attachment_name": "发票.pdf",
            "evidence_type": "tax_invoice",
            "invoice_type": "进项发票",
            "seller_name": "云南城建物业运营集团",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-06",
            "invoice_no": "21026521",
            "amount": "566.04",
            "total_with_tax": "600.00",
        }
        oa_record = OAApplicationRecord(
            id="oa-exp-202603-001",
            month="2026-03",
            section="open",
            case_id=None,
            applicant="刘际涛",
            project_name="冷水机组维护",
            apply_type="付款申请",
            amount="600.00",
            counterparty_name="云南城建物业运营集团",
            reason="维护费",
            relation_code="pending_match",
            relation_label="待找流水与发票",
            relation_tone="warn",
            attachment_invoices=[partial_invoice],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_query_service._oa_adapter = InMemoryOAAdapter({"2026-03": [oa_record]})

            with patch.object(app, "_enqueue_oa_projection_sync_refresh"):
                app._handle_oa_attachment_invoice_cache_updated(["2026-03"])

            invoices = app._import_service.list_invoices()

        self.assertEqual(invoices, [])

    def test_workbench_read_models_can_be_isolated_by_visibility_key(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {"oa_count": 99, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 99, "exception_count": 0},
                "paired": {"groups": []},
                "open": {"groups": []},
            },
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [{"id": "oa-project-only", "type": "oa", "case_id": None, "applicant": "项目用户", "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}}],
                "bank": [],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            isolated = app._get_or_build_workbench_read_model("2026-03", visibility_key="project:abc")

        build_raw.assert_called_once_with("2026-03")
        self.assertEqual(isolated["scope_key"], "visibility:project:abc:2026-03")
        self.assertEqual(isolated["payload"]["summary"]["oa_count"], 1)
        global_cached = app._workbench_read_model_service.get_read_model("2026-03")
        self.assertEqual(global_cached["payload"]["summary"]["oa_count"], 99)

    def test_oa_sync_status_endpoint_reads_durable_queue_status(self) -> None:
        app = build_application()
        app._app_status_runtime_statuses = lambda: {
            "read_model_statuses": None,
            "outbox_statuses": {
                "oa.sync": {
                    "status": "pending",
                    "count": 1,
                    "scopes": [
                        {
                            "event_type": "oa.sync",
                            "scope_type": "oa",
                            "scope_key": "2026-03",
                            "status": "pending",
                            "count": 1,
                        }
                    ],
                }
            },
            "worker_statuses": {"oa-sync": {"status": "ready"}},
        }
        app._postgres_oa_projection_latest_sync_run = lambda: {
            "id": "oa-run-1",
            "status": "succeeded",
            "finished_at": "2026-07-03T08:10:00+00:00",
            "upserted_count": 334,
            "scanned_count": 334,
        }

        response = app.handle_request("GET", "/api/oa-sync/status")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "refreshing")
        self.assertCountEqual(payload["dirty_scopes"], ["2026-03", "all"])
        self.assertEqual(payload["outbox_status"], "pending")
        self.assertEqual(payload["worker_status"], "ready")
        self.assertEqual(payload["last_synced_at"], "2026-07-03T08:10:00+00:00")
        self.assertEqual(payload["last_upserted_count"], 334)

    def test_oa_sync_status_endpoint_does_not_treat_failed_run_as_synced(self) -> None:
        app = build_application()
        app._app_status_runtime_statuses = lambda: {
            "read_model_statuses": None,
            "outbox_statuses": {},
            "worker_statuses": {"oa-sync": {"status": "ready"}},
        }
        app._postgres_oa_projection_latest_sync_run = lambda: {
            "id": "oa-run-failed",
            "status": "failed",
            "finished_at": "2026-07-03T08:20:00+00:00",
            "last_error": "mongo timeout",
        }

        response = app.handle_request("GET", "/api/oa-sync/status")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["message"], "mongo timeout")
        self.assertIsNone(payload["last_synced_at"])

    def test_in_process_oa_polling_and_hot_rebuild_entrypoints_are_removed(self) -> None:
        app = build_application()

        for method_name in [
            "start_oa_sync_polling_worker",
            "_poll_oa_source_once",
            "_handle_oa_source_changed",
            "_schedule_oa_sync_dirty_scope_rebuild",
            "_rebuild_oa_sync_dirty_scopes_once",
            "_hot_rebuild_workbench_read_model_scopes",
        ]:
            self.assertFalse(hasattr(app, method_name), method_name)

    def test_oa_sync_events_endpoint_is_removed_for_polling_mode(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/oa-sync/events?once=1")

        self.assertEqual(response.status_code, 404)

    def test_confirm_link_preview_and_submit_require_note_for_amount_mismatch(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="99.99")
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps({"month": "2026-05", "row_ids": row_ids, "case_id": "CASE-AMOUNT-MISMATCH"}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["operation"], "confirm_link")
        self.assertTrue(preview_payload["requires_note"])
        self.assertTrue(preview_payload["can_submit"])
        self.assertEqual(preview_payload["amount_summary"]["status"], "mismatch")
        self.assertEqual(len(preview_payload["before"]["groups"]), 2)
        self.assertEqual(len(preview_payload["after"]["groups"]), 1)

        rejected_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps({"month": "2026-05", "row_ids": row_ids, "case_id": "CASE-AMOUNT-MISMATCH"}),
        )

        self.assertEqual(rejected_response.status_code, 400)
        self.assertEqual(json.loads(rejected_response.body)["error"], "workbench_pair_relation_note_required")

        with patch.object(app, "_schedule_workbench_read_model_persist"):
            confirmed_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps(
                    {
                        "month": "2026-05",
                        "row_ids": row_ids,
                        "case_id": "CASE-AMOUNT-MISMATCH",
                        "note": "发票尾差待复核",
                    }
                ),
            )

        self.assertEqual(confirmed_response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-AMOUNT-MISMATCH")
        assert relation is not None
        self.assertEqual(relation["note"], "发票尾差待复核")
        self.assertEqual(relation["amount_check"]["status"], "mismatch")
        history = app._workbench_pair_relation_service.list_history()
        self.assertEqual(history[-1]["note"], "发票尾差待复核")
        self.assertEqual(history[-1]["amount_check"]["status"], "mismatch")

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-05").body)
        paired_invoice = next(
            row for row in flatten_groups(updated_payload["paired"]["groups"], "invoice") if row["id"] == "iv-o-202605-001"
        )
        self.assertIn("金额不一致", paired_invoice["tags"])

    def test_confirm_link_preview_uses_row_detail_boundary_when_read_model_payload_is_lightweight(self) -> None:
        app = build_application()
        row_payloads = {
            "oa-o-202605-001": {
                "id": "oa-o-202605-001",
                "type": "oa",
                "case_id": "",
                "applicant": "陈佳玉",
                "project_name": "大型卷烟厂余热综合利用项目",
                "amount": "145.00",
                "reconciliation_amount": "145.00",
                "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            },
            "bk-o-202605-001": {
                "id": "bk-o-202605-001",
                "type": "bank",
                "case_id": "",
                "trade_time": "2026-05-06 09:45:00",
                "debit_amount": "145.00",
                "credit_amount": "",
                "counterparty_name": "陈佳玉",
                "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
            },
            "iv-o-202605-001": {
                "id": "iv-o-202605-001",
                "type": "invoice",
                "case_id": "",
                "seller_name": "云南铁路发展有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-05-06",
                "amount": "145.00",
                "total_with_tax": "145.00",
                "invoice_type": "进项专票",
                "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
            },
        }
        facade_calls: list[tuple[str | None, str]] = []

        class Facade:
            def row_detail(self, month: str | None, *, row_id: str):
                facade_calls.append((month, row_id))
                return SimpleNamespace(
                    status_code=200,
                    payload={"row": row_payloads[row_id], "read_model_status": "fresh"},
                )

        app._workbench_row_detail_api_routes = None
        app._live_workbench_service = SimpleNamespace(
            get_row_detail=lambda row_id: (_ for _ in ()).throw(KeyError(row_id))
        )
        app._resolve_rows_from_cached_read_models = lambda _row_ids, **_kwargs: {}
        app._workbench_query_facade = lambda: Facade()

        row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps({"month": "all", "row_ids": row_ids, "case_id": "CASE-PREVIEW-DETAIL"}),
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        preview_payload = json.loads(preview_response.body)
        after_group = preview_payload["after"]["groups"][0]
        self.assertEqual(after_group["oa_rows"][0]["applicant"], "陈佳玉")
        self.assertEqual(after_group["bank_rows"][0]["counterparty_name"], "陈佳玉")
        self.assertEqual(after_group["invoice_rows"][0]["seller_name"], "云南铁路发展有限公司")
        self.assertEqual(preview_payload["amount_summary"]["status"], "matched")
        self.assertEqual(preview_payload["amount_summary"]["after"]["oa_total"], "145.00")
        self.assertEqual(preview_payload["amount_summary"]["after"]["bank_total"], "145.00")
        self.assertEqual(preview_payload["amount_summary"]["after"]["invoice_total"], "145.00")
        self.assertEqual(facade_calls, [("all", row_id) for row_id in row_ids])

    def test_confirm_link_preview_uses_directional_bank_total_for_mixed_bank_directions(self) -> None:
        app = build_application()
        raw_payload = build_personal_advance_repayment_raw_payload()
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-03")

        row_ids = [
            "oa-personal-advance-001",
            "bank-personal-advance-out-001",
            "bank-personal-advance-in-001",
            "bank-personal-advance-in-002",
        ]
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps({"month": "2026-03", "row_ids": row_ids, "case_id": "CASE-MIXED-DIRECTION"}),
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["operation"], "confirm_link")
        self.assertFalse(preview_payload["requires_note"])
        self.assertTrue(preview_payload["can_submit"])
        self.assertEqual(preview_payload["amount_summary"]["status"], "matched")
        self.assertEqual(preview_payload["amount_summary"]["direction"], "payment")
        self.assertEqual(preview_payload["amount_summary"]["before"]["oa_total"], "300000.00")
        self.assertEqual(preview_payload["amount_summary"]["before"]["bank_total"], "300000.00")
        self.assertEqual(preview_payload["amount_summary"]["after"]["bank_total"], "300000.00")
        self.assertEqual(preview_payload["amount_summary"]["amount_delta"], "0.00")
        self.assertEqual(preview_payload["amount_summary"]["mismatch_fields"], [])

    def _submit_batch_accounting_mismatch_with_note(
        self,
        app: Application,
        *,
        note: str,
    ) -> dict[str, object]:
        response = app.handle_request(
            "POST",
            "/api/batch-accounting/submit",
            json.dumps(
                {
                    "year": "2026",
                    "bank_row_id": "txn_imported_202601_batch_001",
                    "oa_row_ids": ["oa-exp-ba-001"],
                    "note": note,
                    "actor": "finance-user",
                }
            ),
        )
        self.assertEqual(response.status_code, 200, response.body)
        return json.loads(response.body)

    @staticmethod
    def _find_group_by_row_id(groups: list[dict[str, object]], row_id: str) -> dict[str, object]:
        for group in groups:
            for key in ("oa_rows", "bank_rows", "invoice_rows"):
                for row in list(group.get(key) or []):
                    if isinstance(row, dict) and row.get("id") == row_id:
                        return group
        raise AssertionError(f"group not found for row {row_id}")

    def test_batch_accounting_mismatch_note_projects_to_paired_bank_row(self) -> None:
        app = build_application()
        raw_payload = build_batch_accounting_raw_payload()
        with (
            patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            self._submit_batch_accounting_mismatch_with_note(app, note="财务确认差额闭环")
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200, response.body)
        payload = json.loads(response.body)
        group = self._find_group_by_row_id(payload["paired"]["groups"], "txn_imported_202601_batch_001")
        self.assertEqual(group["relation_note"], "财务确认差额闭环")
        self.assertEqual(group["amount_check"]["status"], "mismatch")
        self.assertEqual(group["amount_check"]["direction"], "expense")
        self.assertEqual(group["amount_check"]["bank_amount"], "1200.00")
        self.assertEqual(group["amount_check"]["oa_amount"], "700.00")
        self.assertEqual(group["amount_check"]["amount_delta"], "500.00")
        self.assertTrue(group["amount_check"]["requires_note"])
        bank_row = next(row for row in group["bank_rows"] if row["id"] == "txn_imported_202601_batch_001")
        self.assertEqual(bank_row["relation_note"], "财务确认差额闭环")
        self.assertEqual(bank_row["relation_amount_check"]["status"], "mismatch")
        self.assertIn("金额不一致", bank_row["tags"])

    def test_batch_accounting_mismatch_with_note_has_no_exception_or_ledger_side_effects(self) -> None:
        app = build_application()
        raw_payload = build_batch_accounting_raw_payload()
        before_exception_cases = app._workbench_exception_case_service.snapshot()["cases"]
        before_turnover_relations = app._turnover_relation_service.snapshot()
        before_ledgers = app._ledger_service.list_ledgers()
        before_reminders = app._ledger_service.list_reminders()
        before_tasks = app._etc_reconciliation_task_service.snapshot()

        with (
            patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            self._submit_batch_accounting_mismatch_with_note(app, note="财务确认差额闭环")

        self.assertEqual(app._workbench_exception_case_service.snapshot()["cases"], before_exception_cases)
        self.assertEqual(app._turnover_relation_service.snapshot(), before_turnover_relations)
        self.assertEqual(app._ledger_service.list_ledgers(), before_ledgers)
        self.assertEqual(app._ledger_service.list_reminders(), before_reminders)
        self.assertEqual(app._etc_reconciliation_task_service.snapshot(), before_tasks)

    def test_withdraw_batch_accounting_mismatch_removes_workbench_projection_and_preserves_history_notes(self) -> None:
        app = build_application()
        raw_payload = build_batch_accounting_raw_payload()
        with (
            patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            submit_payload = self._submit_batch_accounting_mismatch_with_note(app, note="财务确认差额闭环")
            relation_id = str(submit_payload["relation_id"])
            withdraw_response = app.handle_request(
                "POST",
                f"/api/batch-accounting/{relation_id}/withdraw",
                json.dumps({"reason": "选错 OA", "actor": "finance-user"}),
            )
            workbench_response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(withdraw_response.status_code, 200, withdraw_response.body)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(relation_id))
        workbench_payload = json.loads(workbench_response.body)
        paired_bank_rows = flatten_groups(workbench_payload["paired"]["groups"], "bank")
        self.assertFalse(any(row.get("id") == "txn_imported_202601_batch_001" for row in paired_bank_rows))

        histories = app._workbench_pair_relation_service.list_history()
        self.assertEqual(histories[-1]["operation_type"], "withdraw_link")
        self.assertEqual(histories[-1]["note"], "选错 OA")
        submit_history = next(history for history in histories if history["operation_type"] == "confirm_link")
        self.assertEqual(submit_history["note"], "财务确认差额闭环")
        self.assertEqual(submit_history["amount_check"]["status"], "mismatch")

    def test_confirm_link_preview_preserves_existing_case_group_before_submit(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["bank"][0]["case_id"] = ""
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps({"month": "2026-05", "row_ids": row_ids, "case_id": "CASE-FULL"}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        before_groups = preview_payload["before"]["groups"]
        self.assertEqual(len(before_groups), 2)
        existing_group = next(group for group in before_groups if group["group_id"] == "case:CASE-EXISTING-PARTIAL")
        self.assertEqual([row["id"] for row in existing_group["oa_rows"]], ["oa-o-202605-001"])
        self.assertEqual([row["id"] for row in existing_group["invoice_rows"]], ["iv-o-202605-001"])
        self.assertEqual(existing_group["bank_rows"], [])
        self.assertIn("selected:bk-o-202605-001", [group["group_id"] for group in before_groups])
        self.assertEqual(len(preview_payload["after"]["groups"]), 1)

    def test_confirm_link_preview_for_already_active_relation_returns_withdraw_preview(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-ACTIVE-PREVIEW",
            row_ids=["bk-o-202605-001", "iv-o-202605-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
            amount_check={"status": "matched", "direction": "payment"},
        )

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            json.dumps(
                {
                    "month": "2026-05",
                    "row_ids": ["bk-o-202605-001", "iv-o-202605-001"],
                    "case_id": "CASE-ACTIVE-PREVIEW",
                }
            ),
        )

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["operation"], "withdraw_link")
        self.assertEqual(preview_payload["operation_type"], "withdraw_relation")
        self.assertTrue(preview_payload["can_submit"])
        self.assertTrue(str(preview_payload["preview_id"]).startswith("withdraw_relation:"))
        self.assertEqual(preview_payload["active_relation"]["case_id"], "CASE-ACTIVE-PREVIEW")
        before_group = preview_payload["before"]["groups"][0]
        self.assertEqual(before_group["group_id"], "case:CASE-ACTIVE-PREVIEW")
        self.assertEqual([row["id"] for row in before_group["bank_rows"]], ["bk-o-202605-001"])
        self.assertEqual([row["id"] for row in before_group["invoice_rows"]], ["iv-o-202605-001"])

    def test_withdraw_link_restores_previous_relation_snapshot(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        partial_row_ids = ["oa-o-202605-001", "iv-o-202605-001"]
        full_row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        row_detail = row_detail_side_effect_for_raw_payload(raw_payload)
        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            partial_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps({"month": "2026-05", "row_ids": partial_row_ids, "case_id": "CASE-PARTIAL"}),
            )
        self.assertEqual(partial_response.status_code, 200)

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            full_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids, "case_id": "CASE-FULL"}),
            )
        self.assertEqual(full_response.status_code, 200)

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            preview_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link/preview",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
            )
        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertTrue(preview_payload["can_submit"])
        self.assertEqual(preview_payload["restored_relations"][0]["case_id"], "CASE-PARTIAL")
        self.assertEqual(len(preview_payload["before"]["groups"]), 1)
        after_group_ids = [group["group_id"] for group in preview_payload["after"]["groups"]]
        self.assertIn("case:CASE-PARTIAL", after_group_ids)
        self.assertIn("selected:bk-o-202605-001", after_group_ids)

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids, "note": "撤回最近一次关联"}),
            )
        self.assertEqual(withdraw_response.status_code, 200)
        withdraw_payload = json.loads(withdraw_response.body)
        self.assertIn("2026-05", withdraw_payload["affected_months"])
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("bk-o-202605-001"))
        restored = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-o-202605-001")
        assert restored is not None
        self.assertEqual(restored["case_id"], "CASE-PARTIAL")
        self.assertCountEqual(restored["row_ids"], partial_row_ids)
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["operation_type"], "withdraw_link")

    def test_withdraw_link_does_not_restore_display_only_existing_case_group(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["bank"][0]["case_id"] = ""
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        full_row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        row_detail = row_detail_side_effect_for_raw_payload(raw_payload)
        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            full_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids, "case_id": "CASE-FULL"}),
            )
        self.assertEqual(full_response.status_code, 200)

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            preview_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link/preview",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
            )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual(
            [group["group_id"] for group in after_groups],
            [
                "selected:oa-o-202605-001",
                "selected:bk-o-202605-001",
                "selected:iv-o-202605-001",
            ],
        )
        self.assertFalse(any(group["group_id"] == "case:CASE-EXISTING-PARTIAL" for group in after_groups))
        oa_group = next(group for group in after_groups if group["group_id"] == "selected:oa-o-202605-001")
        self.assertEqual([row["id"] for row in oa_group["oa_rows"]], ["oa-o-202605-001"])
        self.assertEqual(oa_group["bank_rows"], [])
        self.assertEqual(oa_group["invoice_rows"], [])
        bank_group = next(group for group in after_groups if group["group_id"] == "selected:bk-o-202605-001")
        self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["bk-o-202605-001"])
        self.assertEqual(bank_group["oa_rows"], [])
        self.assertEqual(bank_group["invoice_rows"], [])
        invoice_group = next(group for group in after_groups if group["group_id"] == "selected:iv-o-202605-001")
        self.assertEqual([row["id"] for row in invoice_group["invoice_rows"]], ["iv-o-202605-001"])
        self.assertEqual(invoice_group["oa_rows"], [])
        self.assertEqual(invoice_group["bank_rows"], [])
        self.assertEqual(preview_payload["restored_relations"], [])

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
            )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-FULL"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-EXISTING-PARTIAL"))
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["after_relations"], [])

    def test_withdraw_link_splits_bank_invoice_rows_when_prior_case_id_was_display_only(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="500.00")
        raw_payload["open"]["bank"][0]["case_id"] = "CASE-DISPLAY-BANK-INVOICE"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-DISPLAY-BANK-INVOICE"
        raw_payload["open"]["oa"][0]["case_id"] = ""
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        row_detail = row_detail_side_effect_for_raw_payload(raw_payload)
        row_ids = ["bk-o-202605-001", "iv-o-202605-001"]
        active_relation = app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-BANK-INVOICE",
            row_ids=row_ids,
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )
        app._workbench_pair_relation_service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-DISPLAY-BANK-INVOICE",
                    "row_ids": row_ids,
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": "2026-05",
                }
            ],
            after_relations=[active_relation],
            affected_row_ids=row_ids,
            created_by="test",
        )

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            preview_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link/preview",
                json.dumps({"month": "2026-05", "row_ids": row_ids}),
            )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["restored_relations"], [])
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual(
            [group["group_id"] for group in after_groups],
            ["selected:bk-o-202605-001", "selected:iv-o-202605-001"],
        )
        self.assertFalse(any(group["bank_rows"] and group["invoice_rows"] for group in after_groups))
        bank_group = next(group for group in after_groups if group["group_id"] == "selected:bk-o-202605-001")
        invoice_group = next(group for group in after_groups if group["group_id"] == "selected:iv-o-202605-001")
        self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["bk-o-202605-001"])
        self.assertEqual([row["id"] for row in invoice_group["invoice_rows"]], ["iv-o-202605-001"])

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "2026-05", "row_ids": row_ids}),
            )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BANK-INVOICE"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-DISPLAY-BANK-INVOICE"))

    def test_withdraw_link_splits_bank_invoice_rows_when_history_snapshot_is_not_restorable(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="500.00")
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        row_detail = row_detail_side_effect_for_raw_payload(raw_payload)
        row_ids = ["bk-o-202605-001", "iv-o-202605-001"]
        active_relation = app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-BANK-INVOICE",
            row_ids=row_ids,
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )
        app._workbench_pair_relation_service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-UNOWNED-MANUAL",
                    "row_ids": row_ids,
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-05",
                }
            ],
            after_relations=[active_relation],
            affected_row_ids=row_ids,
            created_by="test",
        )

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            preview_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link/preview",
                json.dumps({"month": "2026-05", "row_ids": row_ids}),
            )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["restored_relations"], [])
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual(
            [group["group_id"] for group in after_groups],
            ["selected:bk-o-202605-001", "selected:iv-o-202605-001"],
        )
        self.assertFalse(any(group["bank_rows"] and group["invoice_rows"] for group in after_groups))

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "2026-05", "row_ids": row_ids}),
            )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-BANK-INVOICE"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-UNOWNED-MANUAL"))

    def test_withdraw_link_without_history_preserves_oa_attachment_invoice_binding(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="500.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-2066-2"
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-AUTO-0001"
        raw_payload["open"]["oa"][0]["amount"] = "500.00"
        raw_payload["open"]["bank"][0]["id"] = "txn_imported_0640"
        raw_payload["open"]["bank"][0]["case_id"] = "CASE-AUTO-0001"
        raw_payload["open"]["bank"][0]["debit_amount"] = "9,370.53"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-2066-2-01"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-AUTO-0001"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        full_row_ids = ["oa-exp-2066-2", "txn_imported_0640", "oa-att-inv-oa-exp-2066-2-01"]
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-AUTO-0001",
            row_ids=full_row_ids,
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link/preview",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual(preview_payload["amount_summary"]["status"], "mismatch")
        self.assertEqual(preview_payload["amount_summary"]["before"]["oa_total"], "500.00")
        self.assertEqual(preview_payload["amount_summary"]["before"]["bank_total"], "9370.53")
        self.assertEqual(preview_payload["amount_summary"]["before"]["invoice_total"], "500.00")
        self.assertEqual(preview_payload["amount_summary"]["after"]["oa_total"], "500.00")
        self.assertEqual(preview_payload["amount_summary"]["after"]["bank_total"], "9370.53")
        self.assertEqual(preview_payload["amount_summary"]["after"]["invoice_total"], "500.00")
        self.assertEqual(preview_payload["amount_summary"]["mismatch_fields"], ["bank_total"])
        self.assertTrue(after_groups)
        binding_group = next(
            group
            for group in after_groups
            if [row["id"] for row in group["oa_rows"]] == ["oa-exp-2066-2"]
        )
        self.assertEqual(binding_group["group_id"], "case:CASE-OA-ATT-oa-exp-2066-2")
        self.assertEqual([row["id"] for row in binding_group["invoice_rows"]], ["oa-att-inv-oa-exp-2066-2-01"])
        self.assertEqual(binding_group["bank_rows"], [])
        self.assertTrue(any([row["id"] for row in group["bank_rows"]] == ["txn_imported_0640"] for group in after_groups))
        self.assertEqual(preview_payload["restored_relations"][0]["case_id"], "CASE-OA-ATT-oa-exp-2066-2")
        self.assertEqual(
            preview_payload["restored_relations"][0]["row_ids"],
            ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
        )

        rows_by_id = {
            row["id"]: dict(row)
            for pane in ("oa", "bank", "invoice")
            for row in raw_payload["open"][pane]
        }

        def row_detail(row_id: str, **_kwargs: object) -> dict[str, object]:
            return {"row": dict(rows_by_id[row_id])}

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
            )

        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-AUTO-0001"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_0640"))
        restored = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-exp-2066-2")
        assert restored is not None
        self.assertEqual(restored["case_id"], "CASE-OA-ATT-oa-exp-2066-2")
        self.assertEqual(restored["row_ids"], ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"])
        self.assertEqual(
            app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-att-inv-oa-exp-2066-2-01"),
            restored,
        )

    def test_withdraw_link_blocks_plain_oa_attachment_invoice_binding(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="500.00")
        raw_payload["open"]["oa"][0]["id"] = "oa-exp-2066-2"
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-OA-ATT-oa-exp-2066-2"
        raw_payload["open"]["oa"][0]["amount"] = "500.00"
        raw_payload["open"]["invoice"][0]["id"] = "oa-att-inv-oa-exp-2066-2-01"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-OA-ATT-oa-exp-2066-2"
        raw_payload["open"]["invoice"][0]["source_kind"] = "oa_attachment_invoice"
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        row_ids = ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"]
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-OA-ATT-oa-exp-2066-2",
            row_ids=row_ids,
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="test",
            month_scope="2026-05",
        )

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link/preview",
            json.dumps({"month": "2026-05", "row_ids": row_ids}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertFalse(preview_payload["can_submit"])
        self.assertIn("无法撤回", preview_payload["message"])
        self.assertEqual(preview_payload["restored_relations"][0]["row_ids"], row_ids)
        before_groups = preview_payload["before"]["groups"]
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual([row["id"] for row in before_groups[0]["oa_rows"]], ["oa-exp-2066-2"])
        self.assertEqual([row["id"] for row in before_groups[0]["invoice_rows"]], ["oa-att-inv-oa-exp-2066-2-01"])
        self.assertEqual([row["id"] for row in after_groups[0]["oa_rows"]], ["oa-exp-2066-2"])
        self.assertEqual([row["id"] for row in after_groups[0]["invoice_rows"]], ["oa-att-inv-oa-exp-2066-2-01"])

        withdraw_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link",
            json.dumps({"month": "2026-05", "row_ids": row_ids}),
        )

        self.assertEqual(withdraw_response.status_code, 400)
        withdraw_payload = json.loads(withdraw_response.body)
        self.assertEqual(withdraw_payload["error"], "workbench_relation_immutable_oa_attachment_binding")
        self.assertIn("无法撤回", withdraw_payload["message"])
        self.assertIsNotNone(
            app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-OA-ATT-oa-exp-2066-2")
        )

    def test_withdraw_link_without_history_falls_back_to_cancelling_active_relation(self) -> None:
        app = build_application()
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-NO-HISTORY",
            row_ids=["oa-no-history", "bk-no-history"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="test",
            amount_check={
                "status": "mismatch",
                "direction": "payment",
                "oa_total": "100.00",
                "bank_total": "90.00",
                "invoice_total": None,
                "mismatch_fields": ["oa_total", "bank_total"],
                "requires_note": True,
            },
        )

        def row_detail(row_id: str, **_kwargs: object) -> dict[str, object]:
            rows = {
                "oa-no-history": {"id": "oa-no-history", "type": "oa", "amount": "100.00"},
                "bk-no-history": {"id": "bk-no-history", "type": "bank", "debit_amount": "90.00"},
            }
            return {"row": rows[row_id]}

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link/preview",
                json.dumps({"month": "all", "row_ids": ["oa-no-history", "bk-no-history"]}),
            )

        self.assertEqual(response.status_code, 200)
        preview_payload = json.loads(response.body)
        self.assertEqual(preview_payload["operation"], "withdraw_link")
        self.assertEqual(len(preview_payload["before"]["groups"]), 1)
        self.assertEqual(preview_payload["amount_summary"]["status"], "mismatch")
        self.assertEqual(preview_payload["amount_summary"]["before"]["oa_total"], "100.00")
        self.assertEqual(preview_payload["amount_summary"]["before"]["bank_total"], "90.00")
        after_group_ids = [group["group_id"] for group in preview_payload["after"]["groups"]]
        self.assertEqual(after_group_ids, ["selected:oa-no-history", "selected:bk-no-history"])
        self.assertEqual(preview_payload["restored_relations"], [])

        with patch.object(app, "_get_api_workbench_row_detail_payload", side_effect=row_detail):
            withdraw_response = app.handle_request(
                "POST",
                "/api/workbench/actions/withdraw-link",
                json.dumps({"month": "all", "row_ids": ["oa-no-history", "bk-no-history"]}),
            )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-NO-HISTORY"))

    def test_etc_batch_oa_api_tags_wait_only_for_bank(self) -> None:
        app = build_application()
        raw_payload = build_etc_batch_raw_payload(bank_amount=None)

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            response = app.handle_request("GET", "/api/workbench?month=2026-06")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        oa_row = flatten_groups(payload["open"]["groups"], "oa")[0]
        self.assertIn("ETC批量提交", oa_row["tags"])
        self.assertIn("已关联ETC发票", oa_row["tags"])
        self.assertIn("待找流水", oa_row["tags"])
        self.assertNotIn("待找发票", oa_row["tags"])
        self.assertNotIn("待找流水与发票", oa_row["tags"])

    def test_etc_batch_oa_bank_amount_mismatch_keeps_mismatch_tag_without_invoice(self) -> None:
        app = build_application()
        raw_payload = build_etc_batch_raw_payload(bank_amount="90.00")

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-06")

        row_ids = ["oa-etc-202606-001", "bk-etc-202606-001"]
        with patch.object(app, "_schedule_workbench_read_model_persist"):
            confirmed_response = app.handle_request(
                "POST",
                "/api/workbench/actions/confirm-link",
                json.dumps(
                    {
                        "month": "2026-06",
                        "row_ids": row_ids,
                        "case_id": "CASE-ETC-MISMATCH",
                        "note": "ETC批量提交与流水金额不一致，待复核",
                    }
                ),
            )

        self.assertEqual(confirmed_response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-ETC-MISMATCH")
        assert relation is not None
        self.assertEqual(relation["amount_check"]["status"], "mismatch")

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-06").body)
        paired_oa = next(
            row for row in flatten_groups(updated_payload["paired"]["groups"], "oa") if row["id"] == "oa-etc-202606-001"
        )
        self.assertIn("ETC批量提交", paired_oa["tags"])
        self.assertIn("已关联ETC发票", paired_oa["tags"])
        self.assertIn("金额不一致", paired_oa["tags"])
        self.assertNotIn("待找发票", paired_oa["tags"])
        self.assertEqual(paired_oa["oa_bank_relation"]["label"], "已关联流水")

    def test_historical_etc_relation_tags_oa_and_injects_summary_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._etc_service.import_zips([UploadedEtcZipFile("historical.zip", etc_zip(["ETC001", "ETC002"]))])
            batch = app._etc_service.create_historical_submitted_batch(
                case_id="etc-historical-2026-01",
                external_batch_id="ETC-HIST-2026-01",
                invoice_numbers=["ETC001", "ETC002"],
                linked_oa_row_id="oa-exp-1994",
                oa_amount=Decimal("26.14"),
                note="历史补关联",
            )
            app._link_etc_invoices_to_existing_invoices(app._etc_service.list_invoices_by_ids(list(batch.invoice_ids)))
            app._workbench_pair_relation_service.create_active_relation(
                case_id="etc-historical-2026-01",
                row_ids=["oa-exp-1994"],
                row_types=["oa"],
                relation_mode="etc_batch_invoice_link",
                created_by="system",
                amount_check={
                    "status": "matched",
                    "oa_amount": "26.14",
                    "invoice_total": "26.14",
                    "delta": "0.00",
                    "etc_batch_id": batch.id,
                    "external_etc_batch_id": batch.etc_batch_id,
                    "source": "historical_repair",
                },
            )
            raw_payload = {
                "month": "2026-02",
                "summary": {
                    "oa_count": 1,
                    "bank_count": 0,
                    "invoice_count": 0,
                    "paired_count": 0,
                    "open_count": 1,
                    "exception_count": 0,
                },
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {
                            "id": "oa-exp-1994",
                            "type": "oa",
                            "case_id": "",
                            "apply_type": "报销单",
                            "amount": "26.14",
                            "counterparty_name": "刘树刚",
                            "oa_bank_relation": {"code": "pending_match", "label": "待找流水", "tone": "warn"},
                            "available_actions": ["detail"],
                        }
                    ],
                    "bank": [],
                    "invoice": [],
                },
            }

            with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
                payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-02").body)

        group = payload["open"]["groups"][0]
        oa_row = group["oa_rows"][0]
        invoice_rows = group["invoice_rows"]
        self.assertIn("已关联ETC发票", oa_row["tags"])
        self.assertNotIn("待找发票", oa_row["tags"])
        self.assertEqual(len(invoice_rows), 1)
        self.assertEqual(invoice_rows[0]["source_kind"], "etc_invoice_summary")
        self.assertEqual(invoice_rows[0]["seller_name"], "ETC发票 2 张")
        self.assertEqual(invoice_rows[0]["etc_batch_id"], "ETC-HIST-2026-01")
        self.assertEqual(invoice_rows[0]["total_with_tax"], "26.14")


if __name__ == "__main__":
    unittest.main()


def flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    key = f"{record_type}_rows"
    flattened: list[dict[str, object]] = []
    for group in groups:
        flattened.extend(group[key])
    return flattened


def all_groups(payload: dict[str, object]) -> list[dict[str, object]]:
    return [*payload["paired"]["groups"], *payload["open"]["groups"]]


def build_personal_advance_repayment_raw_payload(
    *,
    oa_amount: str = "300000.00",
    bank_debit_amount: str = "300000.00",
    bank_credit_amounts: list[str] | None = None,
    include_bank_debit: bool = True,
    include_invoice: bool = False,
) -> dict[str, object]:
    credit_amounts = ["200000.00", "100000.00"] if bank_credit_amounts is None else list(bank_credit_amounts)
    oa_rows = [
        {
            "id": "oa-personal-advance-001",
            "type": "oa",
            "case_id": None,
            "applicant": "测试员工",
            "project_name": "个人暂借款",
            "apply_type": "支付申请",
            "amount": oa_amount,
            "counterparty_name": "测试员工",
            "reason": "个人暂借款",
            "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
            "available_actions": ["detail", "confirm_link", "mark_exception"],
            "summary_fields": {"申请人": "测试员工"},
            "detail_fields": {"申请日期": "2026-03-01"},
        }
    ]
    bank_rows: list[dict[str, object]] = []
    if include_bank_debit:
        bank_rows.append(
            {
                "id": "bank-personal-advance-out-001",
                "type": "bank",
                "case_id": None,
                "trade_time": "2026-03-02 09:00:00",
                "pay_receive_time": "2026-03-02 09:00:00",
                "debit_amount": bank_debit_amount,
                "credit_amount": "",
                "counterparty_name": "测试员工",
                "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                "available_actions": ["detail", "confirm_link", "mark_exception"],
                "summary_fields": {"交易时间": "2026-03-02 09:00:00"},
                "detail_fields": {"摘要": "个人暂借款付款"},
            }
        )
    for index, amount in enumerate(credit_amounts, start=1):
        bank_rows.append(
            {
                "id": f"bank-personal-advance-in-{index:03d}",
                "type": "bank",
                "case_id": None,
                "trade_time": f"2026-03-{index + 2:02d} 09:00:00",
                "pay_receive_time": f"2026-03-{index + 2:02d} 09:00:00",
                "debit_amount": "",
                "credit_amount": amount,
                "counterparty_name": "测试员工",
                "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
                "available_actions": ["detail", "confirm_link", "mark_exception"],
                "summary_fields": {"交易时间": f"2026-03-{index + 2:02d} 09:00:00"},
                "detail_fields": {"摘要": "个人暂借款还款"},
            }
        )
    invoice_rows = (
        [
            {
                "id": "invoice-personal-advance-001",
                "type": "invoice",
                "case_id": None,
                "amount": "300000.00",
                "total_with_tax": "300000.00",
                "seller_name": "测试供应商",
                "invoice_type": "进项发票",
                "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                "available_actions": ["detail", "confirm_link", "mark_exception"],
            }
        ]
        if include_invoice
        else []
    )
    return {
        "month": "2026-03",
        "summary": {
            "oa_count": len(oa_rows),
            "bank_count": len(bank_rows),
            "invoice_count": len(invoice_rows),
            "paired_count": 0,
            "open_count": len(oa_rows) + len(bank_rows) + len(invoice_rows),
            "exception_count": 0,
        },
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {"oa": oa_rows, "bank": bank_rows, "invoice": invoice_rows},
    }


def build_oa_retention_raw_payload(
    *,
    oa_rows: list[dict[str, object]],
    bank_rows: list[dict[str, object]],
    invoice_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "month": "all",
        "summary": {
            "oa_count": len(oa_rows),
            "bank_count": len(bank_rows),
            "invoice_count": len(invoice_rows),
            "paired_count": 0,
            "open_count": len(oa_rows) + len(bank_rows) + len(invoice_rows),
            "exception_count": 0,
        },
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {"oa": oa_rows, "bank": bank_rows, "invoice": invoice_rows},
    }


def build_oa_retention_oa_row(row_id: str, case_id: str, application_date: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "oa",
        "case_id": case_id,
        "applicant": "测试申请人",
        "project_name": "测试项目",
        "apply_type": "支付申请",
        "amount": "100.00",
        "counterparty_name": "测试供应商",
        "reason": "测试保OA",
        "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
        "available_actions": ["detail"],
        "summary_fields": {"申请人": "测试申请人"},
        "detail_fields": {"申请日期": application_date},
    }


def build_oa_retention_bank_row(row_id: str, case_id: str, trade_time: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "case_id": case_id,
        "trade_time": trade_time,
        "debit_amount": "100.00",
        "credit_amount": "",
        "counterparty_name": "测试供应商",
        "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
        "available_actions": ["detail"],
    }


def build_ccb_bank_row(row_id: str, trade_time: str, amount: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "case_id": None,
        "trade_time": trade_time,
        "pay_receive_time": trade_time,
        "direction": "支出",
        "debit_amount": amount,
        "credit_amount": "",
        "counterparty_name": "建设银行可见性测试供应商",
        "payment_account_label": "建设银行 8106",
        "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
        "available_actions": ["detail", "confirm_link", "mark_exception"],
        "summary_fields": {"交易时间": trade_time, "账号": "建设银行 8106"},
        "detail_fields": {"交易时间": trade_time, "账号": "建设银行 8106"},
    }


def build_oa_retention_invoice_row(row_id: str, case_id: str, issue_date: str) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "invoice",
        "case_id": case_id,
        "seller_name": "测试供应商",
        "buyer_name": "云南溯源科技有限公司",
        "issue_date": issue_date,
        "amount": "100.00",
        "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
        "available_actions": ["detail"],
    }


def build_relation_amount_raw_payload(*, invoice_amount: str) -> dict[str, object]:
    return {
        "month": "2026-05",
        "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 1, "paired_count": 0, "open_count": 3, "exception_count": 0},
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {
            "oa": [
                {
                    "id": "oa-o-202605-001",
                    "type": "oa",
                    "case_id": "",
                    "apply_type": "支付申请",
                    "amount": "100.00",
                    "counterparty_name": "测试供应商",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    "available_actions": ["detail"],
                }
            ],
            "bank": [
                {
                    "id": "bk-o-202605-001",
                    "type": "bank",
                    "case_id": "",
                    "trade_time": "2026-05-02 09:00:00",
                    "debit_amount": "100.00",
                    "credit_amount": "",
                    "counterparty_name": "测试供应商",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    "available_actions": ["detail"],
                }
            ],
            "invoice": [
                {
                    "id": "iv-o-202605-001",
                    "type": "invoice",
                    "case_id": "",
                    "seller_name": "测试供应商",
                    "buyer_name": "云南溯源科技有限公司",
                    "issue_date": "2026-05-02",
                    "amount": invoice_amount,
                    "total_with_tax": invoice_amount,
                    "invoice_type": "进项专票",
                    "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
                    "available_actions": ["detail"],
                }
            ],
        },
    }


def row_detail_side_effect_for_raw_payload(raw_payload: dict[str, object]):
    rows_by_id = {
        row["id"]: dict(row)
        for pane in ("oa", "bank", "invoice")
        for row in raw_payload["open"][pane]
    }

    def row_detail(row_id: str, **_kwargs: object) -> dict[str, object]:
        return {"row": dict(rows_by_id[row_id])}

    return row_detail


def build_batch_accounting_raw_payload() -> dict[str, object]:
    return {
        "month": "all",
        "summary": {"oa_count": 1, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 2, "exception_count": 0},
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {
            "oa": [
                {
                    "id": "oa-exp-ba-001",
                    "type": "oa",
                    "case_id": "",
                    "applicant": "刘晨",
                    "apply_time": "2026-01-06",
                    "project_name": "品牌广告投放",
                    "amount": "700.00",
                    "reason": "1月日常报销",
                    "apply_type": "日常报销",
                    "expense_type": "交通费",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"},
                    "available_actions": ["detail"],
                    "summary_fields": {"申请日期": "2026-01-06"},
                }
            ],
            "bank": [
                {
                    "id": "txn_imported_202601_batch_001",
                    "type": "bank",
                    "case_id": "",
                    "trade_time": "2026-01-07 15:54:00",
                    "pay_receive_time": "2026-01-07 15:54:00",
                    "counterparty_name": "批量账务集中处理",
                    "debit_amount": "1200.00",
                    "credit_amount": "",
                    "payment_account_label": "建行基本户 8106",
                    "bank_name": "建行",
                    "account_last4": "8106",
                    "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                    "available_actions": ["detail"],
                    "summary_fields": {"交易时间": "2026-01-07 15:54:00"},
                }
            ],
            "invoice": [],
        },
    }


def build_etc_batch_raw_payload(*, bank_amount: str | None) -> dict[str, object]:
    bank_rows: list[dict[str, object]] = []
    if bank_amount is not None:
        bank_rows.append(
            {
                "id": "bk-etc-202606-001",
                "type": "bank",
                "case_id": "",
                "trade_time": "2026-06-03 09:00:00",
                "debit_amount": bank_amount,
                "credit_amount": "",
                "counterparty_name": "云南高速通行费",
                "invoice_relation": {"code": "pending_match", "label": "待匹配", "tone": "warn"},
                "available_actions": ["detail"],
            }
        )
    return {
        "month": "2026-06",
        "summary": {
            "oa_count": 1,
            "bank_count": len(bank_rows),
            "invoice_count": 0,
            "paired_count": 0,
            "open_count": 1 + len(bank_rows),
            "exception_count": 0,
        },
        "paired": {"oa": [], "bank": [], "invoice": []},
        "open": {
            "oa": [
                {
                    "id": "oa-etc-202606-001",
                    "type": "oa",
                    "source": "etc_batch",
                    "etc_batch_id": "etc_20260503_001",
                    "etcBatchId": "etc_20260503_001",
                    "tags": ["ETC批量提交"],
                    "case_id": "",
                    "apply_type": "支付申请",
                    "amount": "100.00",
                    "counterparty_name": "云南高速通行费",
                    "reason": "ETC批量提交\netc_batch_id=etc_20260503_001",
                    "oa_bank_relation": {"code": "pending_match", "label": "待找流水", "tone": "warn"},
                    "available_actions": ["detail"],
                }
            ],
            "bank": bank_rows,
            "invoice": [],
        },
    }


class _StubLiveWorkbenchService:
    def has_rows_for_month(self, month: str) -> bool:
        return month == "2026-03"

    def get_workbench(self, month: str) -> dict[str, object]:
        if month != "2026-03":
            return {
                "month": month,
                "summary": {"oa_count": 0, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 0, "exception_count": 0},
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {"oa": [], "bank": [], "invoice": []},
            }
        return {
            "month": "2026-03",
            "summary": {"oa_count": 0, "bank_count": 1, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [],
                "bank": [
                    {
                        "id": "txn-live-202603-001",
                        "type": "bank",
                        "case_id": "CASE-LIVE-202603-001",
                        "trade_time": "2026-03-28 11:20:00",
                        "debit_amount": "58,000.00",
                        "credit_amount": "",
                        "counterparty_name": "智能工厂设备商",
                        "payment_account_label": "工商银行 账户 8888",
                        "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
                        "pay_receive_time": "2026-03-28 11:20:00",
                        "remark": "设备尾款待支付",
                        "repayment_date": "",
                        "available_actions": ["detail"],
                    }
                ],
                "invoice": [],
            },
        }

    def get_row_detail(self, row_id: str) -> dict[str, object]:
        if row_id != "txn-live-202603-001":
            raise KeyError(row_id)
        return {
            "id": "txn-live-202603-001",
            "type": "bank",
            "case_id": "CASE-LIVE-202603-001",
            "trade_time": "2026-03-28 11:20:00",
            "debit_amount": "58,000.00",
            "credit_amount": "",
            "counterparty_name": "智能工厂设备商",
            "payment_account_label": "工商银行 账户 8888",
            "invoice_relation": {"code": "suggested_match", "label": "待人工确认", "tone": "warn"},
            "pay_receive_time": "2026-03-28 11:20:00",
            "remark": "设备尾款待支付",
            "repayment_date": "",
            "available_actions": ["detail"],
            "summary_fields": {"和发票关联情况": "待人工确认", "备注": "设备尾款待支付"},
            "detail_fields": {"备注": "设备尾款待支付"},
        }


class _AttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-attach-202603-001"
        self.month = "2026-03"
        self.section = "open"
        self.case_id = None
        self.applicant = "刘际涛"
        self.project_name = "玉烟维护项目"
        self.apply_type = "日常报销"
        self.amount = "58,000.00"
        self.counterparty_name = "智能工厂设备商"
        self.reason = "设备尾款报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "设备货款及材料费"
        self.expense_content = "设备尾款报销"
        self.detail_fields = {
            "OA单号": "OA-ATT-001",
            "申请日期": "2026-03-28",
            "明细行号": "0",
        }
        self.attachment_invoices = [
            {
                "invoice_code": "053002200111",
                "invoice_no": "40512344",
                "seller_tax_no": "91530100678728169X",
                "seller_name": "智能工厂设备商",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-28",
                "amount": "58,000.00",
                "tax_rate": "13%",
                "tax_amount": "0.00",
                "total_with_tax": "58,000.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-attach-202603-001:item:0:equipment",
                "source_attachment_key": "oa-attach-202603-001:item:0:att:equipment",
                "source_attachment_name": "设备发票.pdf",
                "attachment_name": "设备发票.pdf",
                "invoice_kind": "增值税电子专用发票",
            }
        ]


class AttachmentAwareOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [_AttachmentRecord()]


class _SourceBoundAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-hurong-248"
        self.month = "2026-03"
        self.section = "open"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "2024-2026年度红塔集团工作证管理系统维护项目"
        self.apply_type = "日常报销"
        self.amount = "248.00"
        self.counterparty_name = ""
        self.reason = "工作证管理系统维护项目报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "项目费用"
        self.expense_content = "工作证维护费用"
        self.detail_fields = {"OA单号": "OA-HR-248", "申请日期": "2026-03-04"}
        self.expense_items = [
            {
                "row_index": "0",
                "expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "amount": "196.00",
                "expense_content": "付款项1",
            },
            {
                "row_index": "1",
                "expense_item_id": "oa-exp-hurong-248:item:1:service",
                "amount": "52.00",
                "expense_content": "付款项2",
            },
        ]
        self.attachment_invoices = [
            {
                "invoice_no": "24800001",
                "seller_name": "红塔供应商A",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "100.00",
                "total_with_tax": "100.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "source_attachment_key": "oa-exp-hurong-248:item:0:att:a",
                "source_attachment_name": "付款项1-发票A.pdf",
            },
            {
                "invoice_no": "24800002",
                "seller_name": "红塔供应商B",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "96.00",
                "total_with_tax": "96.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "0",
                "source_expense_item_id": "oa-exp-hurong-248:item:0:maint",
                "source_attachment_key": "oa-exp-hurong-248:item:0:att:b",
                "source_attachment_name": "付款项1-发票B.pdf",
            },
            {
                "invoice_no": "24800003",
                "seller_name": "红塔供应商C",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-03-04",
                "amount": "52.00",
                "total_with_tax": "52.00",
                "invoice_type": "进项发票",
                "source_expense_row_index": "1",
                "source_expense_item_id": "oa-exp-hurong-248:item:1:service",
                "source_attachment_key": "oa-exp-hurong-248:item:1:att:c",
                "source_attachment_name": "付款项2-发票C.pdf",
            },
        ]
        self.attachment_file_count = 3


class _SingleSourceAttachmentRecord:
    def __init__(self) -> None:
        self.id = "oa-exp-hurong-292"
        self.month = "2026-03"
        self.section = "open"
        self.case_id = None
        self.applicant = "胡瑢"
        self.project_name = "红云红河烟草能源管理运维项目"
        self.apply_type = "日常报销"
        self.amount = "292.00"
        self.counterparty_name = ""
        self.reason = "能源管理运维项目报销"
        self.relation_code = "pending_match"
        self.relation_label = "待找流水与发票"
        self.relation_tone = "warn"
        self.expense_type = "项目费用"
        self.expense_content = "能源管理运维费用"
        self.detail_fields = {"OA单号": "OA-HR-292", "申请日期": "2026-03-24", "明细行号": "0"}
        source_invoice = {
            "invoice_no": "29200001",
            "seller_name": "能源运维供应商",
            "buyer_name": "云南溯源科技有限公司",
            "issue_date": "2026-03-24",
            "amount": "292.00",
            "total_with_tax": "292.00",
            "invoice_type": "进项发票",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-exp-hurong-292:item:0:energy",
            "source_attachment_key": "oa-exp-hurong-292:item:0:att:only",
            "source_attachment_name": "能源管理运维发票.pdf",
        }
        self.expense_items = [
            {
                "row_index": "0",
                "expense_item_id": "oa-exp-hurong-292:item:0:energy",
                "amount": "292.00",
                "attachment_invoices": [dict(source_invoice)],
            }
        ]
        self.attachment_invoices = [source_invoice]
        self.attachment_file_count = 1


class SourceBoundAttachmentOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [_SourceBoundAttachmentRecord(), _SingleSourceAttachmentRecord()]


def oa_2035_attachment_evidences() -> list[dict[str, str]]:
    base = {
        "issue_date": "2026-03-04",
        "paid_at": "2026-03-04 09:00:00",
        "buyer_name": "云南溯源科技有限公司",
    }
    return [
        {
            **base,
            "evidence_id": "oa2035-inv-25",
            "evidence_type": "machine_invoice",
            "document_kind": "云南通用机打发票",
            "invoice_no": "20350025",
            "seller_name": "云南高速公路联网收费有限公司",
            "amount": "25.00",
            "total_with_tax": "25.00",
            "tax_amount": "0.00",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-2035:item:0:toll",
            "source_attachment_key": "oa-2035:item:0:att:invoice-a",
            "source_attachment_name": "过路费机打发票合图.jpg",
        },
        {
            **base,
            "evidence_id": "oa2035-inv-23",
            "evidence_type": "machine_invoice",
            "document_kind": "云南通用机打发票",
            "invoice_no": "20350023",
            "seller_name": "云南高速公路联网收费有限公司",
            "amount": "23.00",
            "total_with_tax": "23.00",
            "tax_amount": "0.00",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-2035:item:0:toll",
            "source_attachment_key": "oa-2035:item:0:att:invoice-b",
            "source_attachment_name": "过路费机打发票合图.jpg",
        },
        {
            **base,
            "evidence_id": "oa2035-inv-200",
            "evidence_type": "tax_invoice",
            "document_kind": "增值税电子普通发票",
            "invoice_no": "20350200",
            "seller_name": "云南中油严家山交通服务有限公司",
            "amount": "176.99",
            "total_with_tax": "200.00",
            "tax_amount": "23.01",
            "source_expense_row_index": "1",
            "source_expense_item_id": "oa-2035:item:1:fuel",
            "source_attachment_key": "oa-2035:item:1:att:invoice",
            "source_attachment_name": "加油费电子发票.pdf",
        },
        {
            **base,
            "evidence_id": "oa2035-pay-25",
            "evidence_type": "payment_receipt",
            "document_kind": "微信支付凭证",
            "merchant_name": "云南高速公路联网收费有限公司",
            "transaction_no": "wx-toll-25",
            "payment_method": "微信",
            "amount": "25.00",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-2035:item:0:toll",
            "source_attachment_key": "oa-2035:item:0:att:payment-25",
            "source_attachment_name": "微信付款凭证25.jpg",
        },
        {
            **base,
            "evidence_id": "oa2035-pay-23",
            "evidence_type": "payment_receipt",
            "document_kind": "微信支付凭证",
            "merchant_name": "云南高速公路联网收费有限公司",
            "transaction_no": "wx-toll-23",
            "payment_method": "微信",
            "amount": "23.00",
            "source_expense_row_index": "0",
            "source_expense_item_id": "oa-2035:item:0:toll",
            "source_attachment_key": "oa-2035:item:0:att:payment-23",
            "source_attachment_name": "微信付款凭证23.jpg",
        },
        {
            **base,
            "evidence_id": "oa2035-pay-200",
            "evidence_type": "payment_receipt",
            "document_kind": "微信支付凭证",
            "merchant_name": "云南中油严家山交通服务有限公司",
            "transaction_no": "wx-fuel-200",
            "payment_method": "微信",
            "amount": "200.00",
            "source_expense_row_index": "1",
            "source_expense_item_id": "oa-2035:item:1:fuel",
            "source_attachment_key": "oa-2035:item:1:att:payment",
            "source_attachment_name": "微信加油付款凭证200.jpg",
        },
    ]


class _FailingOverrideStateStore:
    def save_workbench_overrides(self, snapshot: dict[str, object], *, changed_row_ids: list[str] | None = None) -> None:
        raise TimeoutError("mock override persistence timeout")

    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        return None


class _FailingPairRelationStateStore:
    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        raise TimeoutError("mock pair relation persistence timeout")

    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        return None


class _FailingReadModelStateStore:
    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        raise TimeoutError("mock read model persistence timeout")


class _BankCategoryPersistenceSpyStateStore:
    def __init__(self) -> None:
        self.full_save_calls = 0
        self.category_save_calls = 0
        self.candidate_save_calls = 0
        self.read_model_save_calls = 0
        self.dirty_scope_save_calls = 0
        self.turnover_relation_save_calls = 0
        self.candidate_changed_scope_months: list[str] = []

    def save(self, payload: dict[str, object]) -> None:
        self.full_save_calls += 1
        raise AssertionError("bank category saves must not persist full application state")

    def save_bank_transaction_categories(self, snapshot: dict[str, object]) -> None:
        self.category_save_calls += 1

    def save_workbench_candidate_matches(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_months: list[str] | None = None,
    ) -> None:
        self.candidate_save_calls += 1
        self.candidate_changed_scope_months = list(changed_scope_months or [])

    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        self.read_model_save_calls += 1

    def save_workbench_matching_dirty_scopes(self, snapshot: dict[str, object]) -> None:
        self.dirty_scope_save_calls += 1

    def save_turnover_relations(self, snapshot: dict[str, object]) -> None:
        self.turnover_relation_save_calls += 1

    def save_cost_statistics_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        return None
