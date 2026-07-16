from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
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
                "read_model_status": "fresh",
            },
        )

    def group_detail(
        self,
        month: str | None,
        *,
        zone: str,
        group_id: str,
        expected_read_model_version: str | None = None,
    ) -> WorkbenchQueryResult:
        self.calls.append(
            {
                "month": month,
                "zone": zone,
                "group_id": group_id,
                "expected_read_model_version": expected_read_model_version,
            }
        )
        return self.result

    def initial_page(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "initial", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month, "read_model_status": "fresh"})

    def refresh_status(self, month: str | None) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "refresh_status", "month": month})
        return WorkbenchQueryResult(HTTPStatus.ACCEPTED, {"month": month, "read_model_status": "refreshing"})

    def groups(self, month: str | None, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "groups", "month": month, **kwargs})
        return WorkbenchQueryResult(HTTPStatus.OK, {"month": month, "groups": [], "read_model_status": "fresh"})

    def row_detail(self, month: str | None, *, row_id: str, **kwargs: object) -> WorkbenchQueryResult:
        self.calls.append({"endpoint": "row_detail", "month": month, "row_id": row_id, **kwargs})
        return WorkbenchQueryResult(
            HTTPStatus.OK,
            {
                "row": {"id": row_id, "type": "bank"},
                "scope_key": "2026-06",
                "read_model_status": "fresh",
            },
        )


class WorkbenchRowDetailApiRoutesTests(unittest.TestCase):
    def test_row_detail_delegates_all_month_to_query_facade_in_sql_runtime(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchRowDetailApiRoutes(query_facade_provider=lambda: facade)

        payload = routes.get_payload("txn_imported_0396", month="all")

        self.assertEqual(payload["row"], {"id": "txn_imported_0396", "type": "bank"})
        self.assertEqual(
            facade.calls,
            [{"endpoint": "row_detail", "month": "all", "row_id": "txn_imported_0396"}],
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
                    "expected_read_model_version": None,
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
            paired_query='{"sort":"bank:desc","search_by_pane":{"bank":"建行"}}',
            unpaired_query='{"search":"供应商","search_mode":"linked_context"}',
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {"month": "2026-05", "read_model_status": "fresh"})
        self.assertEqual(
            facade.calls,
            [
                {
                    "endpoint": "initial",
                    "month": "2026-05",
                    "paired_query": {"search_by_pane": {"bank": "建行"}, "sort": "bank:desc"},
                    "unpaired_query": {"search": "供应商", "search_mode": "linked_context"},
                }
            ],
        )

    def test_initial_rejects_unknown_or_wrong_typed_fields_without_calling_facade(self) -> None:
        for query in ('{"page":2}', '{"search":123}', '{"search_mode":"global"}'):
            with self.subTest(query=query):
                facade = FakeWorkbenchQueryFacade()
                routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

                status, payload = routes.initial("all", paired_query=query)

                self.assertEqual(status, HTTPStatus.BAD_REQUEST)
                self.assertEqual(payload["error"], "invalid_workbench_initial_query")
                self.assertEqual(facade.calls, [])

    def test_refresh_status_delegates_to_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.refresh_status("2026-05")

        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(payload, {"month": "2026-05", "read_model_status": "refreshing"})
        self.assertEqual(facade.calls, [{"endpoint": "refresh_status", "month": "2026-05"}])

    def test_groups_normalizes_query_and_delegates_to_query_facade(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, payload = routes.groups(
            None,
            zone=" unpaired ",
            page="2",
            page_size="50",
            status="unpaired",
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
                    "zone": "unpaired",
                    "page": "2",
                    "page_size": "50",
                    "status": "unpaired",
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

    def test_groups_forwards_expected_read_model_version(self) -> None:
        facade = FakeWorkbenchQueryFacade()
        routes = WorkbenchReadApiRoutes(query_facade_provider=lambda: facade)

        status, _payload = routes.groups(
            "all",
            zone="paired",
            expected_read_model_version=" generation-set-7 ",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(facade.calls[0]["expected_read_model_version"], "generation-set-7")


class WorkbenchActionGenerationGateTests(unittest.TestCase):
    def test_every_workbench_preview_and_write_handler_stops_at_generation_gate(self) -> None:
        handler_cases = {
            "_handle_api_workbench_exception_preview": {},
            "_handle_api_workbench_exception_apply": {"request_id": "req-1"},
            "_handle_api_workbench_confirm_link": {"request_id": "req-1", "headers": {}},
            "_handle_api_workbench_confirm_link_preview": {},
            "_handle_api_workbench_mark_exception": {},
            "_handle_api_workbench_cancel_link": {"request_id": "req-1", "headers": {}},
            "_handle_api_workbench_withdraw_link_preview": {},
            "_handle_api_workbench_withdraw_link": {"request_id": "req-1", "headers": {}},
            "_handle_api_workbench_confirm_cash_pass_through": {"request_id": "req-1"},
            "_handle_api_workbench_confirm_cash_ticket_purchase": {"request_id": "req-1"},
            "_handle_api_workbench_cancel_cash_special": {"request_id": "req-1"},
            "_handle_api_workbench_update_bank_exception": {},
            "_handle_api_workbench_oa_bank_exception": {},
            "_handle_api_workbench_confirm_personal_advance_repayment": {"request_id": "req-1"},
            "_handle_api_workbench_cancel_exception": {},
            "_handle_api_workbench_ignore_row": {},
            "_handle_api_workbench_unignore_row": {},
        }
        request_payload = {
            "month": "all",
            "row_ids": ["bank-1"],
            "expected_read_model_version": "generation-set-1",
        }

        for handler_name, kwargs in handler_cases.items():
            with self.subTest(handler=handler_name):
                app = object.__new__(Application)
                guarded_payloads: list[dict[str, object]] = []
                sentinel = Application._json_response(
                    HTTPStatus.CONFLICT,
                    {"error": "workbench_read_model_not_fresh"},
                )

                def guard(payload: dict[str, object]):
                    guarded_payloads.append(dict(payload))
                    return sentinel

                app._workbench_write_freshness_guard = guard

                response = getattr(app, handler_name)(json.dumps(request_payload), **kwargs)

                self.assertIs(response, sentinel)
                self.assertEqual(guarded_payloads, [request_payload])


if __name__ == "__main__":
    unittest.main()
