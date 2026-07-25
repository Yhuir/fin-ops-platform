from __future__ import annotations

import importlib
import json
import unittest
from http import HTTPStatus
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from fin_ops_platform.services.workbench_read_model_version import WorkbenchReadModelVersionConflictError
from tests.app_test_support import (
    build_grouped_workbench_projection,
    build_local_state_application as build_application,
    install_fresh_workbench_write_gate,
)


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[f"{record_type}_rows"])
    return rows


def _json_response(response) -> dict[str, object]:
    return json.loads(response.body)


class WorkbenchStaleWriteContractTests(unittest.TestCase):
    READ_MODEL_VERSION = "stale-write-test-generation-1"

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        install_fresh_workbench_write_gate(app, version=self.READ_MODEL_VERSION)
        return app

    def _default_open_row_ids(self, app: Application) -> list[str]:
        payload = build_grouped_workbench_projection(app, "2026-03")
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

        with patch.object(app, "_schedule_workbench_pair_relation_persist"):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-WITHDRAW-COMPAT",
                    "note": "withdraw compatibility covers documented mismatch path",
                    "expected_read_model_version": self.READ_MODEL_VERSION,
                },
            )
            withdraw_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "expected_versions": {"relation:CASE-WITHDRAW-COMPAT": 1},
                    "expected_read_model_version": self.READ_MODEL_VERSION,
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

        with patch.object(app, "_schedule_workbench_pair_relation_persist"):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "case_id": "CASE-WITHDRAW-PREVIEW-VERSION",
                    "note": "withdraw preview covers documented mismatch path",
                    "expected_read_model_version": self.READ_MODEL_VERSION,
                },
            )
            preview_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link/preview",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "expected_read_model_version": self.READ_MODEL_VERSION,
                },
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

    def test_relation_preview_selection_maps_generation_drift_to_stable_conflict(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_relation_preview_selection(**_kwargs: object) -> dict[str, object]:
                raise WorkbenchReadModelVersionConflictError(
                    expected="generation-old",
                    current="generation-new",
                )

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=lambda *_args, **_kwargs: None,
            scope_key_for_month=lambda month: str(month or "all"),
            stale_reasons=lambda *_args, **_kwargs: [],
            emit_status_metric=lambda **_kwargs: None,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.relation_preview_selection(
            "2026-05",
            row_ids=["oa-1", "bank-1"],
            expected_read_model_version="generation-old",
        )

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["error"], "workbench_read_model_version_conflict")
        self.assertEqual(result.payload["message"], "工作台数据已变化，请刷新后重试。")
        self.assertEqual(result.payload["read_model_version"], "generation-new")

    def test_relation_preview_selection_rejects_unbounded_client_input_before_repository(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_relation_preview_selection(**_kwargs: object) -> dict[str, object]:
                raise AssertionError("oversized selection must not reach the repository")

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=lambda *_args, **_kwargs: None,
            scope_key_for_month=lambda month: str(month or "all"),
            stale_reasons=lambda *_args, **_kwargs: [],
            emit_status_metric=lambda **_kwargs: None,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.relation_preview_selection(
            "all",
            row_ids=[f"row-{index}" for index in range(21)],
            expected_read_model_version="generation-set-1",
        )

        self.assertEqual(result.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(result.payload["error"], "relation_preview_selection_too_large")


if __name__ == "__main__":
    unittest.main()
