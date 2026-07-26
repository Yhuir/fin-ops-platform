from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.app.routes_workbench import (
    WorkbenchGroupDetailApiRoutes,
    WorkbenchReadApiRoutes,
    WorkbenchRowDetailApiRoutes,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryResult


class FakeWorkbenchQueryFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def initial_page(
        self, month: str | None, **kwargs: object
    ) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "initial", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month})

    def groups(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "groups", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"groups": [], "total": 0})

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
                "endpoint": "group_detail",
                "month": month,
                "zone": zone,
                "group_id": group_id,
                "detail_key": detail_key,
            }
        )
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {"group": {"group_id": group_id}},
        )

    def row_detail(
        self, month: str | None, *, row_id: str
    ) -> WorkbenchQueryResult:
        self.calls.append(
            {"endpoint": "row_detail", "month": month, "row_id": row_id}
        )
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {"row": {"id": row_id, "type": "bank"}},
        )


class WorkbenchRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.facade = FakeWorkbenchQueryFacade()

    def test_initial_normalizes_whitelisted_pane_queries(self) -> None:
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: self.facade)

        status, payload = routes.initial(
            "2026-05",
            paired_query='{"sort":"bank:desc","search":" 建行 "}',
            unpaired_query='{"search":"供应商"}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "2026-05"})
        self.assertEqual(
            self.facade.calls,
            [
                {
                    "endpoint": "initial",
                    "month": "2026-05",
                    "paired_query": {"search": "建行", "sort": "bank:desc"},
                    "unpaired_query": {"search": "供应商"},
                }
            ],
        )

    def test_initial_rejects_unknown_or_wrong_typed_fields(self) -> None:
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: self.facade)

        for query in ('{"page":2}', '{"search":123}', "[]", "{"):
            with self.subTest(query=query):
                status, payload = routes.initial("all", paired_query=query)
                self.assertEqual(status, HTTPStatus.BAD_REQUEST)
                self.assertEqual(payload["error"], "invalid_workbench_initial_query")
        self.assertEqual(self.facade.calls, [])

    def test_groups_normalizes_filters_sort_and_server_pagination(self) -> None:
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: self.facade)

        status, payload = routes.groups(
            None,
            zone=" unpaired ",
            page="2",
            page_size="20",
            status="unpaired",
            source_kind="bank",
            search=" vendor ",
            sort="bank:desc",
            detail_level="summary",
            column_filters='{"bank":{"direction":["支出"]}}',
            time_filters='{"bank":{"mode":"month","month":"2026-05"}}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"groups": [], "total": 0})
        self.assertEqual(self.facade.calls[0]["month"], "all")
        self.assertEqual(self.facade.calls[0]["zone"], "unpaired")
        self.assertEqual(self.facade.calls[0]["page"], "2")
        self.assertEqual(self.facade.calls[0]["page_size"], "20")
        self.assertEqual(self.facade.calls[0]["search"], "vendor")

    def test_groups_rejects_invalid_zone_json_and_oversized_search(self) -> None:
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: self.facade)

        invalid_zone, _ = routes.groups("all", zone="ignored")
        invalid_json, _ = routes.groups(
            "all", zone="unpaired", column_filters="[]"
        )
        oversized, _ = routes.groups(
            "all", zone="unpaired", search="x" * 201
        )

        self.assertEqual(invalid_zone, HTTPStatus.BAD_REQUEST)
        self.assertEqual(invalid_json, HTTPStatus.BAD_REQUEST)
        self.assertEqual(oversized, HTTPStatus.BAD_REQUEST)
        self.assertEqual(self.facade.calls, [])

    def test_group_detail_forwards_stable_detail_key(self) -> None:
        routes = WorkbenchGroupDetailApiRoutes(
            query_facade_provider=lambda: self.facade
        )

        status, payload = routes.get_detail(
            None,
            zone=" paired ",
            group_id=" case:1 ",
            detail_key=" 1 ",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["group"]["group_id"], "case:1")
        self.assertEqual(
            self.facade.calls,
            [
                {
                    "endpoint": "group_detail",
                    "month": "all",
                    "zone": "paired",
                    "group_id": "case:1",
                    "detail_key": "1",
                }
            ],
        )

    def test_group_detail_rejects_invalid_request(self) -> None:
        routes = WorkbenchGroupDetailApiRoutes(
            query_facade_provider=lambda: self.facade
        )

        invalid_zone, _ = routes.get_detail(
            "2026-05", zone="processed", group_id="case:1"
        )
        missing_group, _ = routes.get_detail(
            "2026-05", zone="paired", group_id=" "
        )

        self.assertEqual(invalid_zone, HTTPStatus.BAD_REQUEST)
        self.assertEqual(missing_group, HTTPStatus.BAD_REQUEST)
        self.assertEqual(self.facade.calls, [])

    def test_row_detail_delegates_to_query_facade(self) -> None:
        routes = WorkbenchRowDetailApiRoutes(
            query_facade_provider=lambda: self.facade
        )

        payload = routes.get_payload("bank-1", month="all")

        self.assertEqual(payload["row"]["id"], "bank-1")
        self.assertEqual(
            self.facade.calls,
            [{"endpoint": "row_detail", "month": "all", "row_id": "bank-1"}],
        )

    def test_refresh_and_events_route_owners_are_removed(self) -> None:
        self.assertFalse(hasattr(WorkbenchReadApiRoutes, "refresh_status"))
        routes_module = __import__(
            "fin_ops_platform.app.routes_workbench",
            fromlist=["WorkbenchEventsApiRoutes"],
        )
        self.assertFalse(hasattr(routes_module, "WorkbenchEventsApiRoutes"))


if __name__ == "__main__":
    unittest.main()
