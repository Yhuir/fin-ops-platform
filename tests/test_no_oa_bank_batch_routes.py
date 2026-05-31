from __future__ import annotations

import unittest
from http import HTTPStatus

from fin_ops_platform.app.routes_no_oa_bank_batches import NoOaBankBatchApiRoutes


class FakeNoOaApplicationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def list_batches_payload(self, query):
        self.calls.append(("list", query))
        return {"summary": {}, "batches": [], "read_model_status": "fresh"}

    def tag_selection_payload(self):
        self.calls.append(("tag_selection", None))
        return {"version": 1, "selected_tag_codes": []}


class NoOaBankBatchRoutesTests(unittest.TestCase):
    def test_routes_facade_delegates_list_and_tag_selection_to_application_service(self) -> None:
        service = FakeNoOaApplicationService()
        routes = NoOaBankBatchApiRoutes(application_service=service)

        list_status, list_payload = routes.list_batches({"bucket": ["unsubmitted"]})
        selection_status, selection_payload = routes.tag_selection()

        self.assertEqual(list_status, HTTPStatus.OK)
        self.assertEqual(list_payload["read_model_status"], "fresh")
        self.assertEqual(selection_status, HTTPStatus.OK)
        self.assertEqual(selection_payload["version"], 1)
        self.assertEqual(
            service.calls,
            [
                ("list", {"bucket": ["unsubmitted"]}),
                ("tag_selection", None),
            ],
        )


if __name__ == "__main__":
    unittest.main()
