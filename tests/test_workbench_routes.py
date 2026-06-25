from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.app.routes_workbench import WorkbenchGroupDetailApiRoutes, WorkbenchReadApiRoutes
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryResult


class FakeWorkbenchQueryFacade:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self.result = WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                "month": "all",
                "scope_key": "all",
                "zone": "open",
                "group_id": "case:1",
                "group": {"group_id": "case:1"},
                "read_model_status": "fresh",
            },
        )

    def group_detail(self, month: str | None, *, zone: str, group_id: str) -> WorkbenchQueryResult:
        self.calls.append({"month": month, "zone": zone, "group_id": group_id})
        return self.result

    def summary(self, month: str | None) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "summary", "month": month})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month, "read_model_status": "fresh"})

    def groups(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "groups", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month, "groups": [], "read_model_status": "fresh"})


class WorkbenchGroupDetailApiRoutesTests(unittest.TestCase):
    def test_group_detail_delegates_normalized_request_and_preserves_facade_result(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchGroupDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_detail(None, zone=" open ", group_id=" case:1 ")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, facade.result.payload)
        self.assertEqual(facade.calls, [{"month": "all", "zone": "open", "group_id": "case:1"}])

    def test_group_detail_rejects_invalid_zone_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchGroupDetailApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.get_detail("2026-05", zone="processed", group_id="case:1")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload, {"error": "invalid_workbench_zone", "message": "zone must be open or paired."})
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
    def test_summary_delegates_to_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.summary("2026-05")

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "2026-05", "read_model_status": "fresh"})
        self.assertEqual(facade.calls, [{"endpoint": "summary", "month": "2026-05"}])

    def test_groups_normalizes_query_and_delegates_to_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups(
            None,
            zone=" open ",
            page="2",
            page_size="50",
            status="candidate",
            source_kind="bank",
            search="vendor",
            search_mode="pane",
            search_by_pane='{"bank": "foo", "oa": ["bar"]}',
            sort="amount_desc",
            detail_level="summary",
            column_filters='{"amount": {"min": 10}}',
            time_filters='{"trade_date": {"from": "2026-05-01"}}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "all", "groups": [], "read_model_status": "fresh"})
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "groups",
                    "month": "all",
                    "zone": "open",
                    "page": "2",
                    "page_size": "50",
                    "status": "candidate",
                    "source_kind": "bank",
                    "search": "vendor",
                    "search_mode": "pane",
                    "search_by_pane": {"bank": "foo", "oa": ["bar"]},
                    "sort": "amount_desc",
                    "detail_level": "summary",
                    "column_filters": {"amount": {"min": 10}},
                    "time_filters": {"trade_date": {"from": "2026-05-01"}},
                }
            ],
        )

    def test_groups_rejects_invalid_zone_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups("2026-05", zone="ignored")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload, {"error": "invalid_workbench_zone", "message": "zone must be open or paired."})
        self.assertEqual(facade.calls, [])

    def test_groups_rejects_invalid_json_query_without_calling_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups("2026-05", zone="open", column_filters="[1, 2]")

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            payload,
            {"error": "invalid_workbench_groups_query", "message": "column_filters must be a JSON object."},
        )
        self.assertEqual(facade.calls, [])


if __name__ == "__main__":
    unittest.main()
