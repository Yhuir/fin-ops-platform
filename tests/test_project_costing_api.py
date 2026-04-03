import json
import unittest

from fin_ops_platform.app.server import build_application


class ProjectCostingApiTests(unittest.TestCase):
    def test_project_create_assign_and_detail_round_trip(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "088101",
                    "invoice_no": "API-PROJ-001",
                    "counterparty_name": "Project API Client",
                    "amount": "150.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        create_response = app.handle_request(
            "POST",
            "/projects",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "project_code": "PJT-API-001",
                    "project_name": "API 项目",
                }
            ),
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = json.loads(create_response.body)
        project_id = create_payload["project"]["id"]

        workbench_payload = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        invoice_id = workbench_payload["open"]["invoice"][0]["id"]

        assign_response = app.handle_request(
            "POST",
            "/projects/assign",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "object_type": "invoice",
                    "object_id": invoice_id,
                    "project_id": project_id,
                    "note": "api assignment",
                }
            ),
        )
        self.assertEqual(assign_response.status_code, 200)
        assign_payload = json.loads(assign_response.body)
        self.assertEqual(assign_payload["assignment"]["project_id"], project_id)

        list_response = app.handle_request("GET", "/projects")
        self.assertEqual(list_response.status_code, 200)
        list_payload = json.loads(list_response.body)
        self.assertEqual(list_payload["projects"][0]["id"], project_id)

        detail_response = app.handle_request("GET", f"/projects/{project_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["project"]["id"], project_id)
        self.assertEqual(detail_payload["summary"]["income_amount"], "150.00")
        self.assertEqual(detail_payload["assignments"][0]["object_id"], invoice_id)

    def _preview_and_confirm(self, app, batch_type: str, rows: list[dict[str, str]]) -> None:
        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": batch_type,
                    "source_name": f"{batch_type}.json",
                    "imported_by": "user_finance_01",
                    "rows": rows,
                }
            ),
        )
        preview_payload = json.loads(preview_response.body)
        app.handle_request(
            "POST",
            "/imports/confirm",
            json.dumps({"batch_id": preview_payload["batch"]["id"]}),
        )


if __name__ == "__main__":
    unittest.main()
