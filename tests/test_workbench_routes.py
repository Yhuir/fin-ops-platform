from __future__ import annotations

import unittest
from http import HTTPStatus

from fin_ops_platform.app.routes_workbench import (
    WorkbenchGroupDetailApiRoutes,
    WorkbenchReadApiRoutes,
    WorkbenchRowDetailApiRoutes,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryResult


class FakeWorkbenchQueryFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                "month": "all",
                "scope_key": "all",
                "zone": "unpaired",
                "group_id": "case:1",
                "group": {"group_id": "case:1"},
            },
        )

    def group_detail(
        self,
        month: str | None,
        *,
        zone: str,
        group_id: str,
        detail_key: str | None = None,
    ) -> WorkbenchQueryResult:
        self.calls.append(
            {
                "month": month,
                "zone": zone,
                "group_id": group_id,
                "detail_key": detail_key,
            }
        )
        return self.result

    def initial_page(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "initial", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month})

    def groups(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "groups", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month, "groups": []})

    def filter_options(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "filter_options", "month": month, **kwargs})
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {"month": month, "options": [{"value": "杨丽萍", "label": "杨丽萍"}]},
        )

    def row_detail(self, month: str | None, *, row_id: str, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "row_detail", "month": month, "row_id": row_id, **kwargs})
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                "row": {"id": row_id, "type": "bank"},
                "scope_key": "2026-06",
            },
        )


class WorkbenchRowDetailApiRoutesTests(unittest.TestCase):
    def test_row_detail_delegates_typed_row_to_direct_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchRowDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_result(
            "txn_imported_0396",
            month="all",
            row_type="bank",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["row"], {"id": "txn_imported_0396", "type": "bank"})
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "row_detail",
                    "month": "all",
                    "row_id": "txn_imported_0396",
                    "row_type": "bank",
                }
            ],
        )


class WorkbenchGroupDetailApiRoutesTests(unittest.TestCase):
    def test_group_detail_delegates_normalized_request_and_preserves_facade_result(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchGroupDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_detail(None, zone=" unpaired ", group_id=" case:1 ")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, facade.result.payload)
        self.assertEqual(
            facade.calls,
            [
                {
                    "month": "all",
                    "zone": "unpaired",
                    "group_id": "case:1",
                    "detail_key": None,
                }
            ],
        )

    def test_group_detail_rejects_invalid_zone_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchGroupDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_detail("2026-05", zone="processed", group_id="case:1")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload, {"error": "invalid_workbench_zone", "message": "zone must be unpaired or paired."})
        self.assertEqual(facade.calls, [])

    def test_group_detail_requires_group_id_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchGroupDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_detail("2026-05", zone="paired", group_id=" ")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            payload,
            {"error": "invalid_workbench_group_detail_request", "message": "group_id is required."},
        )
        self.assertEqual(facade.calls, [])


class WorkbenchReadApiRoutesTests(unittest.TestCase):
    def test_initial_whitelists_pane_queries_and_delegates_to_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.initial(
            "2026-05",
            paired_query='{"sort":"bank:desc","search":"建行"}',
            unpaired_query='{"search":"供应商"}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "2026-05"})
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "initial",
                    "month": "2026-05",
                    "paired_query": {"search": "建行", "sort": "bank:desc"},
                    "unpaired_query": {"search": "供应商"},
                }
            ],
        )

    def test_initial_rejects_unknown_or_wrong_typed_fields_without_calling_facade(self) -> None:
        for query in ('{"page":2}', '{"search":123}', '{"search_mode":"global"}', '{"search_by_pane":{}}'):
            with self.subTest(query=query):
                facade = FakeWorkbenchQueryFacade()
                routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

                status, payload = routes.initial("all", paired_query=query)

                self.assertEqual(status, HTTPStatus.BAD_REQUEST)
                self.assertEqual(payload["error"], "invalid_workbench_initial_query")
                self.assertEqual(facade.calls, [])

    def test_refresh_status_route_has_no_read_route_handler(self) -> None:
        self.assertFalse(hasattr(WorkbenchReadApiRoutes, "refresh_status"))

    def test_groups_normalizes_query_and_delegates_to_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups(
            None,
            zone=" unpaired ",
            cursor="opaque-cursor",
            page_size="50",
            status="unpaired",
            source_kind="bank",
            search=" vendor ",
            sort="bank:desc",
            detail_level="summary",
            column_filters='{"amount": {"min": 10}}',
            time_filters='{"trade_date": {"from": "2026-05-01"}}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "all", "groups": []})
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "groups",
                    "month": "all",
                    "zone": "unpaired",
                    "cursor": "opaque-cursor",
                    "page_size": 50,
                    "status": "unpaired",
                    "source_kind": "bank",
                    "search": "vendor",
                    "sort": "bank:desc",
                    "detail_level": "summary",
                    "column_filters": {"amount": {"min": 10}},
                    "time_filters": {"trade_date": {"from": "2026-05-01"}},
                    "exception_bucket": None,
                }
            ],
        )

    def test_groups_normalizes_equivalent_money_search_queries(self) -> None:
        for query in ("202", "202.0", "202.00", "￥202.00", "¥202.00"):
            with self.subTest(query=query):
                facade = FakeWorkbenchQueryFacade()
                routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

                status, _payload = routes.groups("all", zone="unpaired", search=query)

                self.assertEqual(status, HTTPStatus.OK)
                self.assertEqual(facade.calls[0]["search"], "202")

    def test_groups_rejects_search_longer_than_contract_limit(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups("all", zone="paired", search="x" * 201)

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "invalid_workbench_groups_query")
        self.assertIn("at most 200 characters", payload["message"])
        self.assertEqual(facade.calls, [])

    def test_groups_rejects_invalid_zone_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups("2026-05", zone="ignored")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload, {"error": "invalid_workbench_zone", "message": "zone must be unpaired or paired."})
        self.assertEqual(facade.calls, [])

    def test_groups_rejects_invalid_json_query_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups("2026-05", zone="unpaired", column_filters="[1, 2]")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            payload,
            {"error": "invalid_workbench_groups_query", "message": "column_filters must be a JSON object."},
        )
        self.assertEqual(facade.calls, [])

    def test_groups_contract_does_not_accept_expected_read_model_version(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        with self.assertRaises(TypeError):
            routes.groups(
                "all",
                zone="paired",
                expected_read_model_version="generation-set-7",  # type: ignore[call-arg]
            )

    def test_filter_options_normalizes_query_and_delegates_to_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.filter_options(
            "all",
            zone=" unpaired ",
            pane="oa",
            facet="column",
            column="applicant",
            option_search=" 杨 ",
            cursor="opaque-cursor",
            page_size="100",
            search=" 1320 ",
            column_filters='{"oa":{"applicant":["杨丽萍"],"projectName":["大理项目"]}}',
            time_filters='{"oa":{"mode":"year","year":"2026"}}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["options"][0]["value"], "杨丽萍")
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "filter_options",
                    "month": "all",
                    "zone": "unpaired",
                    "pane": "oa",
                    "facet": "column",
                    "column": "applicant",
                    "option_search": "杨",
                    "cursor": "opaque-cursor",
                    "page_size": 100,
                    "status": None,
                    "source_kind": None,
                    "search": "132",
                    "column_filters": {
                        "oa": {"applicant": ["杨丽萍"], "projectName": ["大理项目"]}
                    },
                    "time_filters": {"oa": {"mode": "year", "year": "2026"}},
                    "exception_bucket": None,
                }
            ],
        )

    def test_filter_options_accepts_time_year_without_column(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, _payload = routes.filter_options(
            "all",
            zone="paired",
            pane="invoice",
            facet="time_year",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertIsNone(facade.calls[0]["column"])

    def test_filter_options_rejects_unknown_target_and_unbounded_page_size(self) -> None:
        cases = (
            {"pane": "unknown", "facet": "column", "column": "applicant"},
            {"pane": "oa", "facet": "column", "column": "reason"},
            {"pane": "oa", "facet": "column", "column": "applicant", "page_size": "201"},
            {"pane": "oa", "facet": "column", "column": "applicant", "option_search": "x" * 101},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                facade = FakeWorkbenchQueryFacade()
                routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

                status, payload = routes.filter_options("all", zone="unpaired", **kwargs)

                self.assertEqual(status, HTTPStatus.BAD_REQUEST)
                self.assertEqual(payload["error"], "invalid_workbench_filter_options_query")
                self.assertEqual(facade.calls, [])

if __name__ == "__main__":
    unittest.main()
