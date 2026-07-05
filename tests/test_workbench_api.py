import json
import unittest

from tests.app_test_support import build_local_state_application as build_application


class WorkbenchApiTests(unittest.TestCase):
    def test_relation_groups_dedupes_duplicate_relation_row_ids(self) -> None:
        app = build_application()

        groups = app._relation_groups(  # pylint: disable=protected-access
            [
                {
                    "case_id": "CASE-DUPE-OA",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["oa-exp-1", "bank-1", "oa-exp-1"],
                    "row_types": ["oa", "bank", "oa"],
                    "special_metadata": {},
                }
            ],
            selected_rows=[
                {"id": "oa-exp-1", "type": "oa", "amount": "100.00"},
                {"id": "bank-1", "type": "bank", "amount": "100.00"},
            ],
        )

        self.assertEqual([row["id"] for row in groups[0]["oa_rows"]], ["oa-exp-1"])
        self.assertEqual([row["id"] for row in groups[0]["bank_rows"]], ["bank-1"])

    def test_legacy_workbench_endpoints_are_removed(self) -> None:
        app = build_application()
        for path in (
            "/workbench",
            "/workbench/prototype",
            "/workbench/actions/confirm",
            "/workbench/actions/difference",
            "/workbench/actions/exception",
            "/workbench/actions/offline",
            "/workbench/actions/offset",
        ):
            method = "GET" if path in {"/workbench", "/workbench/prototype"} else "POST"
            response = app.handle_request(method, path, json.dumps({}))
            self.assertEqual(response.status_code, 404, path)


if __name__ == "__main__":
    unittest.main()
