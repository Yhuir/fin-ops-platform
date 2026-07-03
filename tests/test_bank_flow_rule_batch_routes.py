from __future__ import annotations

import unittest
from http import HTTPStatus
from types import SimpleNamespace

from fin_ops_platform.app.routes_bank_flow_rule_batches import BankFlowRuleBatchApiRoutes
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE


class FakeBankFlowRuleBatchApplicationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.list_relation_modes: list[str] = []

    def list_batches_payload(self, query, *, relation_mode="no_oa_bank_batch"):  # type: ignore[no-untyped-def]
        self.list_relation_modes.append(relation_mode)
        self.calls.append(("list", query))
        return {"summary": {}, "batches": [], "read_model_status": "fresh"}

    def tag_selection_payload(self):  # type: ignore[no-untyped-def]
        self.calls.append(("tag_rules", None))
        return {"version": 1, "selected_tag_codes": ["fee"], "rules": [{"tag_code": "fee"}]}

    def update_tag_selection(self, payload, *, actor_id):  # type: ignore[no-untyped-def]
        self.calls.append(("update_tag_rules", {"payload": payload, "actor_id": actor_id}))
        if payload.get("expected_version") == 0:
            raise AppSettingsValidationError("bank_flow_rule_batch_tag_rules_version_conflict", "version conflict")
        if payload.get("duplicate_rule"):
            raise AppSettingsValidationError("duplicate_bank_flow_rule_batch_tag_rule", "duplicate tag rule")
        return {"version": 2, "selected_tag_codes": ["fee"], "rules": [{"tag_code": "fee"}]}

    def submit_batch(self, batch_id, *, actor, expected_version, note, relation_mode):  # type: ignore[no-untyped-def]
        self.calls.append(
            (
                "submit_batch",
                {
                    "batch_id": batch_id,
                    "actor": actor,
                    "expected_version": expected_version,
                    "note": note,
                    "relation_mode": relation_mode,
                },
            )
        )
        return {"batch": {"batch_id": batch_id}, "affected_months": ["2026-05"]}

    def withdraw_batch(self, batch_id, *, actor, expected_version, reason):  # type: ignore[no-untyped-def]
        self.calls.append(
            (
                "withdraw_batch",
                {
                    "batch_id": batch_id,
                    "actor": actor,
                    "expected_version": expected_version,
                    "reason": reason,
                },
            )
        )
        return {
            "batch": {"batch_id": batch_id},
            "affected_months": ["2026-05"],
            "affected_scope_keys": ["2026-05"],
            "read_model_scope_keys": ["2026-05"],
            "freshness_targets": [
                {"read_model_key": "bank_flow_rule_batch", "scope_key": "2026-05"},
                {"read_model_key": "workbench_relation", "scope_key": "all"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
                {"read_model_key": "workbench", "scope_key": "all"},
                {"read_model_key": "workbench", "scope_key": "2026-05"},
            ],
            "operation_barrier_targets": [
                {"read_model_key": "bank_flow_rule_batch", "scope_key": "2026-05"},
                {"read_model_key": "workbench_relation", "scope_key": "all"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
                {"read_model_key": "workbench", "scope_key": "all"},
                {"read_model_key": "workbench", "scope_key": "2026-05"},
            ],
        }

    def submit_selected_rows(self, *, row_ids, actor, note, relation_mode):  # type: ignore[no-untyped-def]
        self.calls.append(
            (
                "submit_selected_rows",
                {"row_ids": list(row_ids), "actor": actor, "note": note, "relation_mode": relation_mode},
            )
        )
        return {"affected_months": ["2026-05"]}

    def reset_submitted_bank_flow_rule_batches(self, *, actor, reason):  # type: ignore[no-untyped-def]
        self.calls.append(("reset", {"actor": actor, "reason": reason}))
        return {"summary": {"reset_count": 2}, "affected_months": ["2026-05"]}

    def rebaseline_submitted_no_oa_batches_dry_run(self):  # type: ignore[no-untyped-def]
        self.calls.append(("rebaseline_dry_run", None))
        return {"dry_run": True}

    def apply_submitted_no_oa_rebaseline(self, *, actor, reason, manifest):  # type: ignore[no-untyped-def]
        self.calls.append(("rebaseline_apply", {"actor": actor, "reason": reason, "manifest": manifest}))
        return {"applied": True}


class BankFlowRuleBatchRoutesTests(unittest.TestCase):
    def test_list_route_uses_bank_flow_relation_mode(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(
            application_service=service,  # type: ignore[arg-type]
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        response = routes.route("GET", "/api/bank-flow-rule-batches", {"bucket": ["submitted"]}, None, {})

        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertEqual(response["payload"]["read_model_status"], "fresh")
        self.assertEqual(service.calls, [("list", {"bucket": ["submitted"]})])
        self.assertEqual(service.list_relation_modes, [BANK_FLOW_RULE_BATCH_RELATION_MODE])

    def test_tag_rules_strip_no_oa_selection_fields_and_map_conflict(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]

        status, payload = routes.tag_rules()
        conflict_status, conflict_payload = routes.update_tag_rules(
            {"expected_version": 0, "rules": []},
            session=SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001")),
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertNotIn("selected_tag_codes", payload)
        self.assertEqual(conflict_status, HTTPStatus.CONFLICT)
        self.assertEqual(conflict_payload["error"], "bank_flow_rule_batch_tag_rules_version_conflict")

    def test_tag_rules_reject_legacy_selection_and_duplicate_rules(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]
        session = SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001"))

        selected_status, selected_payload = routes.update_tag_rules(
            {"expected_version": 1, "selected_tag_codes": ["fee"]},
            session=session,
        )
        duplicate_status, duplicate_payload = routes.update_tag_rules(
            {"expected_version": 1, "duplicate_rule": True},
            session=session,
        )

        self.assertEqual(selected_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(selected_payload["error"], "bank_flow_rule_batch_selected_tag_codes_forbidden")
        self.assertEqual(duplicate_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(duplicate_payload["error"], "duplicate_bank_flow_rule_batch_tag_rule")

    def test_submit_and_withdraw_use_bank_flow_write_targets(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]
        session = SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001"))

        submit_status, _submit_payload = routes.submit_batch(
            "batch-001",
            {"expected_version": "2", "note": " ok "},
            session=session,
        )
        withdraw_status, withdraw_payload = routes.withdraw_batch(
            "batch-001",
            {"expected_version": "3", "reason": "  redo  "},
            session=session,
        )

        self.assertEqual(submit_status, HTTPStatus.OK)
        self.assertEqual(withdraw_status, HTTPStatus.OK)
        self.assertEqual(
            withdraw_payload["operation_barrier_targets"],
            [
                {"read_model_key": "bank_flow_rule_batch", "scope_key": "2026-05"},
                {"read_model_key": "workbench_relation", "scope_key": "all"},
                {"read_model_key": "workbench_relation", "scope_key": "2026-05"},
                {"read_model_key": "workbench", "scope_key": "all"},
                {"read_model_key": "workbench", "scope_key": "2026-05"},
            ],
        )
        self.assertEqual(withdraw_payload["freshness_targets"], withdraw_payload["operation_barrier_targets"])
        self.assertEqual(withdraw_payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(
            service.calls,
            [
                (
                    "submit_batch",
                    {
                        "batch_id": "batch-001",
                        "actor": "finance-user",
                        "expected_version": 2,
                        "note": "ok",
                        "relation_mode": "bank_flow_rule_batch",
                    },
                ),
                (
                    "withdraw_batch",
                    {
                        "batch_id": "batch-001",
                        "actor": "finance-user",
                        "expected_version": 3,
                        "reason": "redo",
                    },
                ),
            ],
        )

    def test_reset_route_maps_actor_and_reason(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]

        status, payload = routes.reset_submitted_batches(
            {"reason": "  全部重新过规则  "},
            session=SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001")),
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["summary"]["reset_count"], 2)
        self.assertEqual(service.calls, [("reset", {"actor": "finance-user", "reason": "全部重新过规则"})])


if __name__ == "__main__":
    unittest.main()
