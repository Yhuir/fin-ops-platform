from __future__ import annotations

import importlib
import json
import unittest
from http import HTTPStatus
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from tests.app_test_support import build_local_state_application as build_application


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[f"{record_type}_rows"])
    return rows


def _json_response(response) -> dict[str, object]:
    return json.loads(response.body)


class WorkbenchStaleWriteContractTests(unittest.TestCase):
    def setUp(self) -> None:
        cost_warmup_patcher = patch.object(Application, "_schedule_cost_statistics_cache_warmup")
        self.addCleanup(cost_warmup_patcher.stop)
        cost_warmup_patcher.start()

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        return app

    def _default_open_row_ids(self, app: Application) -> list[str]:
        payload = _json_response(app.handle_request("GET", "/api/workbench?month=2026-03"))
        return [
            _flatten_groups(payload["unpaired"]["groups"], "oa")[0]["id"],
            _flatten_groups(payload["unpaired"]["groups"], "bank")[0]["id"],
            _flatten_groups(payload["unpaired"]["groups"], "invoice")[0]["id"],
        ]

    def _post(self, app: Application, path: str, payload: dict[str, object]):
        return app.handle_request("POST", path, json.dumps(payload))

    def test_withdraw_submit_accepts_expected_versions_payload_without_breaking_existing_success_shape(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-WITHDRAW-COMPAT",
                    "note": "withdraw compatibility covers documented mismatch path",
                },
            )
            withdraw_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "expected_versions": {"relation:CASE-WITHDRAW-COMPAT": 1},
                },
            )

        self.assertEqual(confirm_response.status_code, int(HTTPStatus.OK), confirm_response.body)
        self.assertEqual(withdraw_response.status_code, int(HTTPStatus.OK), withdraw_response.body)
        payload = _json_response(withdraw_response)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "withdraw_link")
        self.assertEqual(payload["month"], "2026-03")
        self.assertCountEqual(payload["affected_row_ids"], row_ids)
        self.assertIn("restored_relations", payload)

    def test_withdraw_preview_exposes_relation_identity_and_version_for_submit_expected_versions(self) -> None:
        app = self._build_app()
        row_ids = self._default_open_row_ids(app)

        with (
            patch.object(app, "_schedule_workbench_pair_relation_persist"),
            patch.object(app, "_schedule_workbench_read_model_persist"),
        ):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-WITHDRAW-PREVIEW-VERSION",
                    "note": "withdraw preview covers documented mismatch path",
                },
            )
            preview_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link/preview",
                {"month": "2026-03", "row_ids": row_ids},
            )

        self.assertEqual(confirm_response.status_code, int(HTTPStatus.OK), confirm_response.body)
        self.assertEqual(preview_response.status_code, int(HTTPStatus.OK), preview_response.body)
        payload = _json_response(preview_response)

        # PF-P023 target contract: preview must expose stable identity/version so
        # submit can reject stale writes rather than operating on the current relation.
        self.assertEqual(payload["active_relation"]["case_id"], "CASE-WITHDRAW-PREVIEW-VERSION")
        self.assertIsInstance(payload["active_relation"]["version"], int)
        self.assertEqual(
            payload["submit_expected_versions"],
            {f"relation:{payload['active_relation']['case_id']}": payload["active_relation"]["version"]},
        )

    def test_target_workbench_write_conflict_response_shape_is_stable(self) -> None:
        module = importlib.import_module("fin_ops_platform.services.workbench_uow")
        conflict_cls = getattr(module, "WorkbenchWriteConflict")

        conflict = conflict_cls(
            action="cancel_link",
            reason="stale_relation_version",
            expected={"relation:CASE-OLD": 2},
            actual={"relation:CASE-NEW": 5},
            message="工作台数据已变化，请刷新后重试。",
        )
        response = conflict.to_response_payload()

        self.assertEqual(response["status_code"], int(HTTPStatus.CONFLICT))
        payload = response["payload"]
        self.assertEqual(payload["error"], "workbench_write_conflict")
        self.assertEqual(payload["message"], "工作台数据已变化，请刷新后重试。")
        self.assertEqual(payload["conflict"]["action"], "cancel_link")
        self.assertEqual(payload["conflict"]["reason"], "stale_relation_version")
        self.assertEqual(payload["conflict"]["expected"], {"relation:CASE-OLD": 2})
        self.assertEqual(payload["conflict"]["actual"], {"relation:CASE-NEW": 5})


if __name__ == "__main__":
    unittest.main()
