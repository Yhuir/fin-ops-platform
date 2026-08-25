from __future__ import annotations

import importlib
import json
import unittest
from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from tests.app_test_support import (
    build_grouped_workbench_projection,
    build_local_state_application as build_application,
    install_direct_workbench_selection_repository,
)


def _flatten_groups(groups: list[dict[str, object]], record_type: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for group in groups:
        rows.extend(group[f"{record_type}_rows"])
    return rows


def _json_response(response) -> dict[str, object]:
    return json.loads(response.body)


class _LocalWithdrawUoW:
    """Runs the write handler through the same transaction-bound selection contract as production."""

    def __init__(self, app: Application) -> None:
        self._app = app

    @staticmethod
    def replay_committed(_command: object) -> None:
        return None

    def run(self, command: object, handler: object) -> dict[str, object]:
        row_ids = list(getattr(command, "row_ids"))
        row_types = list(getattr(command, "row_types"))
        rows_by_id = self._app._workbench_page_selection_repository.get_canonical_rows_by_ids(
            row_ids,
            row_types=row_types,
        )
        canonical_rows = [
            {
                **dict(rows_by_id[row_id]),
                "row_id": row_id,
                "pane": row_type,
            }
            for row_id, row_type in zip(row_ids, row_types, strict=True)
        ]
        canonical_query = SimpleNamespace(
            load_validated_workbench_relation_selection_in_current_transaction=(
                lambda **_: canonical_rows
            )
        )
        return handler(
            SimpleNamespace(
                transaction=object(),
                pair_relations=None,
                canonical_query=canonical_query,
            )
        )


class WorkbenchStaleWriteContractTests(unittest.TestCase):
    def test_write_gate_requires_explicit_synced_status_even_without_dirty_scopes(self) -> None:
        class GateHarness:
            _workbench_oa_sync_safety_guard = Application._workbench_oa_sync_safety_guard

            def __init__(self, status: str, *, dirty_scopes: list[str] | None = None) -> None:
                self.status = status
                self.dirty_scopes = list(dirty_scopes or [])

            def _oa_sync_status_payload(self) -> dict[str, object]:
                return {"status": self.status, "dirty_scopes": self.dirty_scopes}

            @staticmethod
            def _is_oa_sync_rebuild_scheduled() -> bool:
                return False

            @staticmethod
            def _json_response(
                status_code: object,
                payload: dict[str, object],
            ) -> tuple[object, dict[str, object]]:
                return status_code, payload

        for blocked_status in ("error", "refreshing", "unknown", ""):
            with self.subTest(status=blocked_status):
                response = GateHarness(blocked_status)._workbench_oa_sync_safety_guard({})
                self.assertIsNotNone(response)
                status_code, payload = response
                self.assertEqual(status_code, HTTPStatus.CONFLICT)
                self.assertEqual(payload["error"], "workbench_stale")
        self.assertIsNone(GateHarness("ready")._workbench_oa_sync_safety_guard({}))
        self.assertIsNone(GateHarness("synced")._workbench_oa_sync_safety_guard({}))
        response = GateHarness("ready", dirty_scopes=["2026-03"])._workbench_oa_sync_safety_guard({})
        self.assertIsNotNone(response)

    def _build_app(self) -> Application:
        app = build_application()
        app._emit_workbench_action_timing = lambda **kwargs: None
        app._oa_sync_status_payload = lambda: {"status": "ready", "dirty_scopes": []}
        install_direct_workbench_selection_repository(app)
        app._workbench_withdraw_link_uow_override = _LocalWithdrawUoW(app)
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
                    "row_types": ["oa", "bank", "invoice"],
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
                    "row_types": ["oa", "bank", "invoice"],
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

        with patch.object(app, "_schedule_workbench_pair_relation_persist"):
            confirm_response = self._post(
                app,
                "/api/workbench/actions/confirm-link",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "row_types": ["oa", "bank", "invoice"],
                    "case_id": "CASE-WITHDRAW-PREVIEW-VERSION",
                    "note": "withdraw preview covers documented mismatch path",
                },
            )
            preview_response = self._post(
                app,
                "/api/workbench/actions/withdraw-link/preview",
                {
                    "month": "2026-03",
                    "row_ids": row_ids,
                    "row_types": ["oa", "bank", "invoice"],
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

    def test_relation_preview_selection_accepts_large_typed_input_without_truncation(self) -> None:
        captured: dict[str, object] = {}

        class Repository:
            @staticmethod
            def get_workbench_relation_preview_selection(**kwargs: object) -> dict[str, object]:
                captured.update(kwargs)
                return {
                    "selected_row_ids": list(kwargs["row_ids"]),
                    "selected_row_types": list(kwargs["row_types"]),
                    "selected_rows": [],
                    "context_rows": [],
                    "rows": [],
                }

        facade = WorkbenchQueryFacade(
            repository=None,
            selection_repository=Repository(),
            scope_key_for_month=lambda month: str(month or "all"),
        )

        row_ids = [f"row-{index}" for index in range(500)]
        row_types = ["bank"] * len(row_ids)
        result = facade.relation_preview_selection(
            "all",
            row_ids=row_ids,
            row_types=row_types,
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(captured["row_ids"], row_ids)
        self.assertEqual(captured["row_types"], row_types)


if __name__ == "__main__":
    unittest.main()
