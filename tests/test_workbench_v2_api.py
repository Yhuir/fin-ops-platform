import json
import pickle
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from pymongo.errors import ServerSelectionTimeoutError

from fin_ops_platform.app.server import Application, WORKBENCH_READ_MODEL_SCHEMA_VERSION, build_application
from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings
from fin_ops_platform.services.oa_adapter import InMemoryOAAdapter, OAApplicationRecord
from fin_ops_platform.services.settings_data_reset_service import RESET_OA_AND_REBUILD_ACTION
from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
from fin_ops_platform.services.workbench_candidate_match_service import (
    CANDIDATE_MATCH_SCHEMA_VERSION,
    WorkbenchCandidateMatchService,
)
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


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


class WorkbenchV2ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

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
            }
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump({"workbench_candidate_matches": {"candidates": {candidate_key: candidate}}}, handle)

            app = Application(data_dir=data_dir)

        self.assertEqual(
            app._workbench_candidate_match_service.list_candidates_by_month("2026-05"),
            [candidate],
        )

    def test_application_loads_state_without_workbench_candidate_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            with (data_dir / "state.pkl").open("wb") as handle:
                pickle.dump({"imports": {}, "file_imports": {}, "matching": {}}, handle)

            app = Application(data_dir=data_dir)

        self.assertEqual(app._workbench_candidate_match_service.snapshot(), {"candidates": {}})

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

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
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

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            payload = app._build_api_workbench_payload("2026-05")

        self.assertEqual(payload["paired"]["groups"], [])
        self.assertEqual(len(payload["open"]["groups"]), 1)
        self.assertEqual([row["id"] for row in payload["open"]["groups"][0]["oa_rows"]], ["oa-open"])
        self.assertCountEqual(
            [row["id"] for row in payload["open"]["groups"][0]["invoice_rows"]],
            ["invoice-open-1", "invoice-open-2"],
        )

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
        build_raw.assert_called_once_with("2026-03")
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
        build_raw.assert_called_once_with("2026-03")
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

    def test_get_api_workbench_all_falls_back_to_cutoff_month_range_when_month_listing_errors(self) -> None:
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

        with (
            patch.object(app._live_workbench_service, "has_rows_for_month", return_value=False),
            patch.object(Application, "_fallback_retained_oa_end_month", return_value="2026-02", create=True),
        ):
            response = app.handle_request("GET", "/api/workbench?month=all")

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["oa_status"]["code"], "ready")
        oa_ids = [row["id"] for row in flatten_groups(all_groups(payload), "oa")]
        self.assertEqual(set(oa_ids), {"oa-pay-2047", "oa-pay-2048"})
        self.assertEqual(adapter.month_calls, ["2026-01", "2026-02"])

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

    def test_get_api_workbench_persists_salary_auto_match_into_pair_relations(self) -> None:
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 1)
        self.assertEqual(flatten_groups(payload["paired"]["groups"], "bank")[0]["invoice_relation"]["label"], "已匹配：工资")
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id)
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "salary_personal_auto_match")
        self.assertEqual(relation["row_ids"], [salary_row_id])

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

    def test_get_api_workbench_persists_internal_transfer_auto_match_into_pair_relations(self) -> None:
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

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 1)
        paired_bank_rows = flatten_groups(payload["paired"]["groups"], "bank")
        self.assertCountEqual([row["id"] for row in paired_bank_rows], internal_transfer_row_ids)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(internal_transfer_row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "internal_transfer_pair")
        self.assertCountEqual(relation["row_ids"], internal_transfer_row_ids)

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

    def test_get_api_workbench_merges_oa_attachment_invoice_rows_into_live_grouping(self) -> None:
        app = build_application()
        query_service = WorkbenchQueryService(oa_adapter=AttachmentAwareOAAdapter())
        action_service = WorkbenchActionService(query_service)
        app._workbench_query_service = query_service
        app._workbench_action_service = action_service
        app._workbench_api_routes = WorkbenchApiRoutes(query_service, action_service)
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
        self.assertIn("txn-live-202603-001", [row["id"] for row in group["bank_rows"]])
        self.assertEqual(len(group["invoice_rows"]), 1)
        self.assertEqual(group["invoice_rows"][0]["detail_fields"]["来源OA单号"], "OA-ATT-001")

        invoice_row_id = group["invoice_rows"][0]["id"]
        invoice_detail_response = app.handle_request("GET", f"/api/workbench/rows/{invoice_row_id}")
        oa_detail_response = app.handle_request("GET", "/api/workbench/rows/oa-attach-202603-001")
        self.assertEqual(invoice_detail_response.status_code, 200)
        self.assertEqual(oa_detail_response.status_code, 200)
        invoice_detail = json.loads(invoice_detail_response.body)["row"]
        oa_detail = json.loads(oa_detail_response.body)["row"]
        self.assertEqual(invoice_detail["detail_fields"]["附件文件名"], "设备发票.pdf")
        self.assertEqual(oa_detail["detail_fields"]["附件发票数量"], "1")

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
        action_service = WorkbenchActionService(query_service)
        app._workbench_query_service = query_service
        app._workbench_action_service = action_service
        app._workbench_api_routes = WorkbenchApiRoutes(query_service, action_service)

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
            ["oa-offset-202602-001", "oa-att-inv-oa-offset-202602-001-01"],
        )

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
        self.assertNotIn("updated_rows", cancel_payload)

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

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [oa_row["id"], bank_row["id"], invoice_row["id"]],
                    "case_id": "CASE-PAIR-ONLY-001",
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
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertCountEqual(
            confirm_payload["affected_row_ids"],
            ["oa-o-202603-001", "bk-o-202603-001", "iv-o-202603-001"],
        )
        self.assertNotIn("updated_rows", confirm_payload)

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
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        schedule_pair_relation_persist.assert_called_once()
        self.assertEqual(
            schedule_pair_relation_persist.call_args.kwargs,
            {
                "changed_case_ids": ["CASE-ASYNC-PERSIST-001"],
                "request_id": None,
                "action_name": "confirm_link",
            },
        )
        schedule_read_model_persist.assert_called_once()
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
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
        self.assertCountEqual(
            schedule_read_model_persist.call_args.kwargs["changed_scope_keys"],
            ["2026-03", "all"],
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
            ["2026-03", "all"],
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

        with patch.object(app._live_workbench_service, "_rebuild_cache", wraps=app._live_workbench_service._rebuild_cache) as rebuild_cache:
            confirm_response = app._handle_live_workbench_confirm_link(
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-LIVE-BULK-001",
                }
            )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertLessEqual(rebuild_cache.call_count, 1)

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

        updated_payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        updated_oa_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "oa") if row["id"] == oa_row["id"])
        updated_bank_row = next(row for row in flatten_groups(updated_payload["open"]["groups"], "bank") if row["id"] == bank_row["id"])
        self.assertEqual(updated_oa_row["oa_bank_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_oa_row["oa_bank_relation"]["label"], "金额不一致，继续异常")
        self.assertEqual(updated_bank_row["invoice_relation"]["code"], "oa_bank_amount_mismatch")
        self.assertEqual(updated_bank_row["invoice_relation"]["label"], "金额不一致，继续异常")

    def test_oa_bank_exception_rejects_invoice_rows(self) -> None:
        app = build_application()
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=2026-03").body)
        bank_row = flatten_groups(payload["open"]["groups"], "bank")[0]
        invoice_row = flatten_groups(payload["open"]["groups"], "invoice")[0]

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/oa-bank-exception",
            json.dumps(
                {
                    "month": "2026-03",
                    "row_ids": [bank_row["id"], invoice_row["id"]],
                    "exception_code": "oa_bank_amount_mismatch",
                    "exception_label": "金额不一致，继续异常",
                }
            ),
        )

        self.assertEqual(response.status_code, 400)
        response_payload = json.loads(response.body)
        self.assertEqual(response_payload["error"], "invalid_oa_bank_exception_request")

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

    def test_oa_attachment_invoice_cache_update_marks_related_scopes_dirty_without_evicting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(scope_key="all", payload={"month": "all"})
            app._workbench_read_model_service.upsert_read_model(scope_key="2026-03", payload={"month": "2026-03"})

            with patch.object(app, "_schedule_oa_sync_dirty_scope_rebuild") as schedule_rebuild:
                app._handle_oa_attachment_invoice_cache_updated(["2026-03"])
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)

        self.assertIsNotNone(app._workbench_read_model_service.get_read_model("all"))
        self.assertIsNotNone(app._workbench_read_model_service.get_read_model("2026-03"))
        schedule_rebuild.assert_called_once()
        self.assertEqual(status_payload["status"], "refreshing")
        self.assertCountEqual(status_payload["dirty_scopes"], ["2026-03", "all"])

    def test_oa_sync_change_marks_dirty_without_evicting_hot_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(
                scope_key="2026-03",
                payload={
                    "month": "2026-03",
                    "oa_status": {"code": "ready", "message": "OA 已同步"},
                    "summary": {"oa_count": 9, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 9, "exception_count": 0},
                    "paired": {"groups": []},
                    "open": {"groups": []},
                },
            )

            with patch.object(app, "_schedule_oa_sync_dirty_scope_rebuild") as schedule_rebuild:
                app._handle_oa_source_changed(["2026-03"], reason="oa_polling")

            cached = app._workbench_read_model_service.get_read_model("2026-03")
            status_response = app.handle_request("GET", "/api/oa-sync/status")
            status_payload = json.loads(status_response.body)

        self.assertIsNotNone(cached)
        self.assertEqual(cached["payload"]["summary"]["oa_count"], 9)
        schedule_rebuild.assert_called_once()
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_payload["status"], "refreshing")
        self.assertCountEqual(status_payload["dirty_scopes"], ["2026-03", "all"])

    def test_oa_sync_dirty_scope_rebuild_atomically_overwrites_cached_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_read_model_service.upsert_read_model(
                scope_key="2026-03",
                payload={
                    "month": "2026-03",
                    "oa_status": {"code": "ready", "message": "OA 已同步"},
                    "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
                    "paired": {"groups": []},
                    "open": {"groups": []},
                },
            )
            raw_payload = {
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {"oa_count": 2, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 2, "exception_count": 0},
                "paired": {"oa": [], "bank": [], "invoice": []},
                "open": {
                    "oa": [
                        {"id": "oa-new-1", "type": "oa", "case_id": None, "applicant": "A", "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}},
                        {"id": "oa-new-2", "type": "oa", "case_id": None, "applicant": "B", "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}},
                    ],
                    "bank": [],
                    "invoice": [],
                },
            }

            app._handle_oa_source_changed(["2026-03"], reason="oa_polling", schedule_rebuild=False)
            with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
                app._rebuild_oa_sync_dirty_scopes_once()
            cached = app._workbench_read_model_service.get_read_model("2026-03")
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)

        build_raw.assert_any_call("2026-03")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["payload"]["summary"]["oa_count"], 2)
        self.assertEqual(status_payload["status"], "synced")
        self.assertEqual(status_payload["dirty_scopes"], [])

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

    def test_hot_rebuild_refreshes_existing_visibility_scoped_read_models(self) -> None:
        app = build_application()
        app._workbench_read_model_service.upsert_read_model(
            scope_key="visibility:user:test-user-id:2026-03",
            payload={
                "month": "2026-03",
                "oa_status": {"code": "ready", "message": "OA 已同步"},
                "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1, "exception_count": 0},
                "paired": {"groups": []},
                "open": {"groups": []},
            },
        )
        raw_payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready", "message": "OA 已同步"},
            "summary": {"oa_count": 2, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 2, "exception_count": 0},
            "paired": {"oa": [], "bank": [], "invoice": []},
            "open": {
                "oa": [
                    {"id": "oa-hot-rebuild-1", "type": "oa", "case_id": None, "applicant": "测试用户", "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}},
                    {"id": "oa-hot-rebuild-2", "type": "oa", "case_id": None, "applicant": "测试用户", "oa_bank_relation": {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}},
                ],
                "bank": [],
                "invoice": [],
            },
        }

        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload) as build_raw:
            app._hot_rebuild_workbench_read_model_scopes(["2026-03"])

        build_raw.assert_any_call("2026-03")
        cached = app._workbench_read_model_service.get_read_model("visibility:user:test-user-id:2026-03")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["payload"]["summary"]["oa_count"], 2)

    def test_oa_sync_status_endpoint_returns_current_polling_status(self) -> None:
        app = build_application()
        app._handle_oa_source_changed(["2026-03"], reason="oa_polling", schedule_rebuild=False)

        response = app.handle_request("GET", "/api/oa-sync/status")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "refreshing")
        self.assertCountEqual(payload["dirty_scopes"], ["2026-03", "all"])

    def test_oa_polling_change_marks_scope_dirty_and_persists_fingerprints(self) -> None:
        class PollingAdapter:
            def poll_sync_fingerprints(self) -> dict[str, str]:
                return {"2026-04": "new-month", "all": "new-all"}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_sync_poll_fingerprints = {"2026-04": "old-month", "all": "old-all"}
            app._workbench_query_service._oa_adapter = PollingAdapter()
            with patch.object(app, "_schedule_oa_sync_dirty_scope_rebuild") as schedule_rebuild:
                changed_scopes = app._poll_oa_source_once()
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)
            persisted_state = app._state_store.load_oa_sync_state()

        self.assertEqual(status_payload["status"], "refreshing")
        self.assertCountEqual(status_payload["dirty_scopes"], ["2026-04", "all"])
        self.assertCountEqual(changed_scopes, ["2026-04", "all"])
        self.assertEqual(persisted_state["poll_fingerprints"], {"2026-04": "new-month", "all": "new-all"})
        schedule_rebuild.assert_called_once()

    def test_first_oa_polling_snapshot_does_not_trigger_full_rebuild(self) -> None:
        class PollingAdapter:
            def poll_sync_fingerprints(self) -> dict[str, str]:
                return {"2026-04": "baseline-month", "all": "baseline-all"}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._workbench_query_service._oa_adapter = PollingAdapter()
            with patch.object(app, "_schedule_oa_sync_dirty_scope_rebuild") as schedule_rebuild:
                changed_scopes = app._poll_oa_source_once()
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)
            persisted_state = app._state_store.load_oa_sync_state()

        self.assertEqual(changed_scopes, [])
        self.assertEqual(status_payload["status"], "synced")
        self.assertEqual(persisted_state["poll_fingerprints"], {"2026-04": "baseline-month", "all": "baseline-all"})
        schedule_rebuild.assert_not_called()

    def test_oa_polling_ignores_changes_before_retention_cutoff(self) -> None:
        class PollingAdapter:
            def poll_sync_fingerprints(self) -> dict[str, str]:
                return {"2025-12": "new-old-month", "all": "new-all"}

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_sync_poll_fingerprints = {"2025-12": "old-month", "all": "old-all"}
            app._workbench_query_service._oa_adapter = PollingAdapter()
            with patch.object(app, "_schedule_oa_sync_dirty_scope_rebuild") as schedule_rebuild:
                changed_scopes = app._poll_oa_source_once()
            status_payload = json.loads(app.handle_request("GET", "/api/oa-sync/status").body)

        self.assertEqual(changed_scopes, [])
        self.assertEqual(status_payload["status"], "synced")
        schedule_rebuild.assert_not_called()

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
        self.assertEqual(len(preview_payload["before"]["groups"]), 3)
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

    def test_withdraw_link_restores_previous_relation_snapshot(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        partial_row_ids = ["oa-o-202605-001", "iv-o-202605-001"]
        full_row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        partial_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps({"month": "2026-05", "row_ids": partial_row_ids, "case_id": "CASE-PARTIAL"}),
        )
        self.assertEqual(partial_response.status_code, 200)

        full_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids, "case_id": "CASE-FULL"}),
        )
        self.assertEqual(full_response.status_code, 200)

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

        withdraw_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids, "note": "撤回最近一次关联"}),
        )
        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("bk-o-202605-001"))
        restored = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-o-202605-001")
        assert restored is not None
        self.assertEqual(restored["case_id"], "CASE-PARTIAL")
        self.assertCountEqual(restored["row_ids"], partial_row_ids)
        self.assertEqual(app._workbench_pair_relation_service.list_history()[-1]["operation_type"], "withdraw_link")

    def test_withdraw_link_restores_case_group_that_existed_before_confirm(self) -> None:
        app = build_application()
        raw_payload = build_relation_amount_raw_payload(invoice_amount="100.00")
        raw_payload["open"]["oa"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["invoice"][0]["case_id"] = "CASE-EXISTING-PARTIAL"
        raw_payload["open"]["bank"][0]["case_id"] = ""
        with patch.object(app, "_build_raw_workbench_payload", return_value=raw_payload):
            app.handle_request("GET", "/api/workbench?month=2026-05")

        full_row_ids = ["oa-o-202605-001", "bk-o-202605-001", "iv-o-202605-001"]
        full_response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids, "case_id": "CASE-FULL"}),
        )
        self.assertEqual(full_response.status_code, 200)

        preview_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link/preview",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        after_groups = preview_payload["after"]["groups"]
        self.assertEqual(len(after_groups), 2)
        restored_group = next(group for group in after_groups if group["group_id"] == "case:CASE-EXISTING-PARTIAL")
        self.assertEqual([row["id"] for row in restored_group["oa_rows"]], ["oa-o-202605-001"])
        self.assertEqual([row["id"] for row in restored_group["invoice_rows"]], ["iv-o-202605-001"])
        self.assertEqual(restored_group["bank_rows"], [])
        bank_group = next(group for group in after_groups if group["group_id"] == "selected:bk-o-202605-001")
        self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["bk-o-202605-001"])

    def test_withdraw_link_without_history_restores_oa_attachment_invoice_relation(self) -> None:
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
        self.assertEqual(len(after_groups), 2)
        restored_group = next(group for group in after_groups if group["group_id"] == "case:CASE-OA-ATT-oa-exp-2066-2")
        self.assertEqual([row["id"] for row in restored_group["oa_rows"]], ["oa-exp-2066-2"])
        self.assertEqual([row["id"] for row in restored_group["invoice_rows"]], ["oa-att-inv-oa-exp-2066-2-01"])
        self.assertEqual(restored_group["bank_rows"], [])
        bank_group = next(group for group in after_groups if group["bank_rows"])
        self.assertEqual([row["id"] for row in bank_group["bank_rows"]], ["txn_imported_0640"])
        self.assertEqual(preview_payload["restored_relations"][0]["relation_mode"], "oa_attachment_invoice")

        withdraw_response = app.handle_request(
            "POST",
            "/api/workbench/actions/withdraw-link",
            json.dumps({"month": "2026-05", "row_ids": full_row_ids}),
        )

        self.assertEqual(withdraw_response.status_code, 200)
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id("CASE-AUTO-0001"))
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id("txn_imported_0640"))
        restored_relation = app._workbench_pair_relation_service.get_active_relation_by_row_id("oa-exp-2066-2")
        assert restored_relation is not None
        self.assertEqual(restored_relation["case_id"], "CASE-OA-ATT-oa-exp-2066-2")
        self.assertCountEqual(restored_relation["row_ids"], ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"])

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
        self.assertIn("金额不一致", paired_oa["tags"])
        self.assertNotIn("待找发票", paired_oa["tags"])
        self.assertEqual(paired_oa["oa_bank_relation"]["label"], "已关联流水")


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
                "tax_amount": "6,673.45",
                "total_with_tax": "64,673.45",
                "invoice_type": "进项发票",
                "attachment_name": "设备发票.pdf",
                "invoice_kind": "增值税电子专用发票",
            }
        ]


class AttachmentAwareOAAdapter:
    def list_application_records(self, month: str) -> list[object]:
        if month != "2026-03":
            return []
        return [_AttachmentRecord()]


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


class _FailingReadModelStateStore:
    def save_workbench_read_models(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_keys: list[str] | None = None,
    ) -> None:
        raise TimeoutError("mock read model persistence timeout")
