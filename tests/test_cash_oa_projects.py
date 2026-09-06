from __future__ import annotations

import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError

from bson import ObjectId
from pymongo.errors import ServerSelectionTimeoutError

from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_oa_projects import (
    PROJECT_PROJECTION,
    CashOaProjectService,
    load_project_stages,
)
from fin_ops_platform.services.mongo_oa_adapter import MongoOASettings


STAGES = [{"code": "0", "name": "未中标"}, {"code": "5", "name": "实施阶段"},
          {"code": "4", "name": "采购阶段"}, {"code": "end", "name": "已结束"}]


def document(number: int, phase: str | None, name: str = "虚构项目") -> dict:
    return {"_id": ObjectId(f"{number:024x}"), "data": {"name": name, "code": f"P{number}", "projectPhase": phase}}


class ProjectCursor(list):
    def max_time_ms(self, timeout):
        self.timeout = timeout
        return self


class CashOaProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = {"version": 3, "allowed_stage_codes": ["0", "5"], "configured": True}
        self.rows = [document(1, "5", "A项目"), document(2, "end", "B项目"),
                     document(3, "0", "C项目"), document(4, None, "D项目"), document(5, "new", "E项目")]
        self.collection = Mock()
        self.collection.find.side_effect = lambda *_: ProjectCursor(self.rows)
        self.collection.find_one.side_effect = lambda q, *_args, **_kwargs: next((r for r in self.rows if r["_id"] == q["_id"]), None)
        database = Mock()
        database.__getitem__ = Mock(return_value=self.collection)
        self.client = Mock()
        self.client.__getitem__ = Mock(return_value=database)
        self.stage_loader = Mock(side_effect=lambda: STAGES)
        self.source = CashOaProjectService(
            MongoOASettings(host="not-used", database="oa"), lambda: self.settings, self.stage_loader,
            mongo_client=self.client,
        )

    def test_full_dictionary_count_and_pagination_are_not_derived_from_page(self) -> None:
        payload = self.source.list_projects({"page_size": "2", "page": "2"})
        self.assertEqual(payload["total"], 5)
        self.assertEqual([row["name"] for row in payload["rows"]], ["C项目", "D项目"])
        self.assertEqual(payload["stages"], STAGES)
        self.assertEqual(payload["selection_settings_version"], 3)
        self.assertTrue(payload["configured"])
        self.assertIsNotNone(payload["read_at"])
        self.collection.find.assert_called_once_with({"form_id": "17"}, PROJECT_PROJECTION)
        self.assertEqual(self.source.list_projects({"page": 99})["rows"], [])

    def test_selection_has_precise_reasons_and_zero_is_not_guessed_as_prebid(self) -> None:
        payload = self.source.list_projects({"purpose": "all"})
        self.assertEqual([r["unavailable_reason"] for r in payload["rows"]], [None, "ended", None, "stage_missing", "stage_unknown"])
        self.assertEqual(payload["rows"][2]["stage_name"], "未中标")
        selected = self.source.list_projects({"purpose": "selection"})
        self.assertEqual(selected["total"], 2)
        self.assertEqual([r["stage_code"] for r in selected["rows"]], ["5", "0"])
        self.settings["allowed_stage_codes"] = []
        self.assertEqual(self.source.list_projects({"purpose": "selection"})["total"], 0)
        self.assertEqual(self.source.list_projects({})["rows"][0]["unavailable_reason"], "stage_not_allowed")

    def test_keyword_and_stage_filters_apply_before_count(self) -> None:
        result = self.source.list_projects({"keyword": "p3", "stage_code": "0", "page_size": 1})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["rows"][0]["code"], "P3")
        self.assertEqual(self.source.list_projects({"selectable": "false"})["total"], 3)

    def test_unconfigured_cannot_enable_projects_even_with_stale_allowed_values(self) -> None:
        self.settings["configured"] = False
        self.assertEqual(self.source.list_projects({"purpose": "selection"})["total"], 0)

    def test_resolve_project_returns_stage_configuration_version(self) -> None:
        identity = str(self.rows[0]["_id"])
        self.assertEqual(self.source.resolve_project(identity), {"id": identity, "name": "A项目", "selection_settings_version": 3})
        with self.assertRaises(CashError) as error:
            self.source.resolve_project(str(self.rows[1]["_id"]))
        self.assertEqual(error.exception.code, "cash_project_not_selectable")
        self.assertEqual(error.exception.status, 409)

    def test_historical_opening_checks_real_identity_without_stage_settings_or_dictionary(self) -> None:
        self.stage_loader.side_effect = AssertionError("Historical identity does not request stage eligibility")
        self.source._selection_settings_provider = Mock(side_effect=AssertionError("No stage settings dependency"))
        identity = str(self.rows[1]["_id"])
        self.assertEqual(self.source.resolve_project(identity, allow_historical=True),
                         {"id": identity, "name": "B项目", "selection_settings_version": None})

    def test_deleted_source_is_not_fabricated_or_replaced_by_name(self) -> None:
        with self.assertRaises(CashError) as error:
            self.source.resolve_project("f" * 24, allow_historical=True)
        self.assertEqual(error.exception.code, "cash_project_not_found")

    def test_source_errors_are_not_empty_and_do_not_expose_credentials(self) -> None:
        self.collection.find.side_effect = ServerSelectionTimeoutError("mongodb://secret@host")
        with self.assertRaises(CashError) as error:
            self.source.list_projects({})
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("secret", str(error.exception))

    def test_missing_source_is_explicit_failure_only_when_project_read_is_used(self) -> None:
        service = CashOaProjectService(None, lambda: self.settings, self.stage_loader, mongo_client=None)
        with self.assertRaises(CashError) as error:
            service.resolve_project(str(self.rows[0]["_id"]), allow_historical=True)
        self.assertEqual(error.exception.status, 503)

    def test_missing_required_source_field_rejects_instead_of_skipping_project(self) -> None:
        self.rows[1]["data"]["name"] = None
        with self.assertRaises(CashError) as error:
            self.source.list_projects({})
        self.assertEqual(error.exception.status, 503)

    def test_only_current_known_nonended_codes_can_be_saved(self) -> None:
        self.assertEqual(self.source.validate_stage_codes(["5", "4", "5"]), ["4", "5"])
        self.assertEqual(self.source.validate_stage_codes([]), [])
        for codes in (["end"], ["unknown"], [5], None):
            with self.subTest(codes=codes), self.assertRaises(CashError) as error:
                self.source.validate_stage_codes(codes)
            self.assertEqual(error.exception.status, 400)

    def test_query_validation_precedes_source_io(self) -> None:
        for query in ({"page": 0}, {"page_size": 201}, {"purpose": []}, {"unknown": "x"},
                      {"selectable": "maybe"}, {"purpose": "selection", "selectable": False}):
            with self.subTest(query=query), self.assertRaises(CashError) as error:
                self.source.list_projects(query)
            self.assertEqual(error.exception.status, 400)
        self.collection.find.assert_not_called()


class ProjectDictionaryHttpTests(unittest.TestCase):
    def test_only_exact_read_endpoint_and_required_dto_are_used(self) -> None:
        payload = {"code": 200, "data": [{"dictType": "XMJD", "dictValue": s["code"], "dictLabel": s["name"]} for s in STAGES]}
        with patch("fin_ops_platform.services.cash_oa_projects.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            self.assertEqual(load_project_stages("https://oa.example/api/", "test-only-token", 2), STAGES)
        call = request.call_args
        self.assertEqual(call.args[0].full_url, "https://oa.example/api/system/dict/data/type/XMJD")
        self.assertEqual(call.args[0].method, "GET")
        self.assertIsNone(call.args[0].data)
        self.assertEqual(call.kwargs["timeout"], 2)

    def test_unknown_empty_wrong_type_duplicate_or_missing_end_dictionary_is_failure(self) -> None:
        payloads = [{"code": 401}, {"code": 200, "data": []},
                    {"code": 200, "data": [{"dictType": "OTHER", "dictValue": "end", "dictLabel": "结束"}]},
                    {"code": 200, "data": [{"dictType": "XMJD", "dictValue": "5", "dictLabel": "实施"}]},
                    {"code": 200, "data": [{"dictType": "XMJD", "dictValue": "end", "dictLabel": "结束"}] * 2}]
        for payload in payloads:
            with self.subTest(payload=payload), patch("fin_ops_platform.services.cash_oa_projects.urlopen", return_value=io.BytesIO(json.dumps(payload).encode())):
                with self.assertRaises(CashError) as error:
                    load_project_stages("https://oa.example", "test-only-token")
                self.assertEqual(error.exception.status, 503)

    def test_network_failure_is_sanitized_and_never_uses_old_dictionary(self) -> None:
        with patch("fin_ops_platform.services.cash_oa_projects.urlopen", side_effect=URLError("secret")):
            with self.assertRaises(CashError) as error:
                load_project_stages("https://oa.example", "test-only-token")
        self.assertEqual(error.exception.status, 503)
        self.assertNotIn("secret", str(error.exception))


if __name__ == "__main__":
    unittest.main()
