from __future__ import annotations

import unittest
from http import HTTPStatus
from types import SimpleNamespace

from fin_ops_platform.app.routes_bank_flow_rule_batches import BankFlowRuleBatchApiRoutes
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_batch_application_service import BankBatchRelationMutationError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchPersistenceError


class FakeBankFlowRuleBatchApplicationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.list_relation_modes: list[str] = []

    def list_batches_payload(self, query, *, relation_mode="no_oa_bank_batch"):  # type: ignore[no-untyped-def]
        self.list_relation_modes.append(relation_mode)
        self.calls.append(("list", query))
        return {"summary": {}, "batches": []}

    def tag_selection_payload(self):  # type: ignore[no-untyped-def]
        self.calls.append(("tag_rules", None))
        return {"version": 1, "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}]}

    def update_tag_selection(self, payload, *, actor_id):  # type: ignore[no-untyped-def]
        self.calls.append(("update_tag_rules", {"payload": payload, "actor_id": actor_id}))
        if payload.get("expected_version") == 0:
            raise AppSettingsValidationError("bank_flow_rule_batch_tag_rules_version_conflict", "version conflict")
        if payload.get("duplicate_rule"):
            raise AppSettingsValidationError("duplicate_bank_flow_rule_batch_tag_rule", "duplicate tag rule")
        return {
            "version": 2,
            "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}],
            "eligibility_changed": True,
            "eligibility_changed_tag_codes": ["fee"],
            "affected_months": ["2026-05"],
        }

    def submit_batch(  # type: ignore[no-untyped-def]
        self,
        batch_id,
        *,
        actor,
        expected_version,
        note,
        relation_mode,
        scope_month=None,
    ):
        self.calls.append(
            (
                "submit_batch",
                {
                    "batch_id": batch_id,
                    "actor": actor,
                    "expected_version": expected_version,
                    "note": note,
                    "relation_mode": relation_mode,
                    "scope_month": scope_month,
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


class BankFlowRuleBatchRoutesTests(unittest.TestCase):
    def test_list_route_uses_bank_flow_relation_mode(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(
            application_service=service,  # type: ignore[arg-type]
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        response = routes.route("GET", "/api/bank-flow-rule-batches", {"bucket": ["submitted"]}, None, {})

        self.assertEqual(response["status"], HTTPStatus.OK)
        self.assertNotIn("read_model_status", response["payload"])
        self.assertEqual(service.calls, [("list", {"bucket": ["submitted"]})])
        self.assertEqual(service.list_relation_modes, [BANK_FLOW_RULE_BATCH_RELATION_MODE])

    def test_list_route_does_not_translate_query_failure_into_refresh_status(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        service.list_batches_payload = lambda *_args, **_kwargs: (_ for _ in ()).throw(  # type: ignore[method-assign]
            RuntimeError("bank_flow_rule_batch canonical query failed.")
        )
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]

        with self.assertRaisesRegex(RuntimeError, "canonical query failed"):
            routes.list_batches({})

    def test_tag_rules_return_policy_rules_and_map_conflict(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        routes = BankFlowRuleBatchApiRoutes(application_service=service)  # type: ignore[arg-type]

        status, payload = routes.tag_rules()
        update_status, update_payload = routes.update_tag_rules(
            {"expected_version": 1, "rules": [{"tag_code": "fee"}]},
            session=SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001")),
        )
        conflict_status, conflict_payload = routes.update_tag_rules(
            {"expected_version": 0, "rules": []},
            session=SimpleNamespace(identity=SimpleNamespace(username="finance-user", user_id="oa-001")),
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["rules"], [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}])
        self.assertEqual(update_status, HTTPStatus.OK)
        self.assertEqual(update_payload["affected_months"], ["2026-05"])
        self.assertNotIn("affected_scope_keys", update_payload)
        self.assertNotIn("read_model_scope_keys", update_payload)
        self.assertNotIn("freshness_targets", update_payload)
        self.assertNotIn("operation_barrier_targets", update_payload)
        self.assertNotIn("refresh_enqueued", update_payload)
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

    def test_mutation_permission_denial_stops_before_application_service(self) -> None:
        service = FakeBankFlowRuleBatchApplicationService()
        forbidden = {"status": HTTPStatus.FORBIDDEN, "payload": {"error": "permission_denied"}}
        routes = BankFlowRuleBatchApiRoutes(
            application_service=service,  # type: ignore[arg-type]
            resolve_mutation_session=lambda _headers: forbidden,
        )

        response = routes.route(
            "POST",
            "/api/bank-flow-rule-batches/batch-001/submit",
            {},
            "{}",
            {},
        )

        self.assertIs(response, forbidden)
        self.assertEqual(service.calls, [])

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
        self.assertNotIn("operation_barrier_targets", withdraw_payload)
        self.assertNotIn("freshness_targets", withdraw_payload)
        self.assertNotIn("read_model_scope_keys", withdraw_payload)
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
                        "scope_month": None,
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

    def test_live_candidate_guard_conflict_returns_409(self) -> None:
        class ConflictService(FakeBankFlowRuleBatchApplicationService):
            def submit_batch(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
                raise BankBatchRelationMutationError(
                    "bank_flow_rule_batch_candidate_conflict",
                    "流水规则候选已变化或被占用，请刷新列表后重试。",
                )

        routes = BankFlowRuleBatchApiRoutes(
            application_service=ConflictService(),  # type: ignore[arg-type]
        )

        status, payload = routes.submit_batch(
            "batch-001",
            {"expected_version": 1, "scope_month": "2026-05"},
            session=SimpleNamespace(
                identity=SimpleNamespace(username="finance-user", user_id="oa-001")
            ),
        )

        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload["error"], "bank_flow_rule_batch_candidate_conflict")

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

    def test_http_boundary_uses_bank_flow_error_codes_without_legacy_translation(self) -> None:
        conflict_status, conflict_payload = BankFlowRuleBatchApiRoutes._value_error_response(
            ValueError("bank_flow_rule_batch_version_conflict")
        )
        invalid_status, invalid_payload = BankFlowRuleBatchApiRoutes._value_error_response(
            ValueError("bank_flow_rule_batch_selection_internal_transfer_requires_pair")
        )
        occupied_status, occupied_payload = BankFlowRuleBatchApiRoutes._value_error_response(
            BankBatchRelationMutationError(
                "bank_flow_rule_batch_selection_occupied",
                "所选流水已被其他批次占用。",
                payload={"row_ids": ["bank-1"], "conflicting_case_ids": ["submitted-batch"]},
            )
        )
        persistence_status, persistence_payload = BankFlowRuleBatchApiRoutes._persistence_error_response(
            BankFlowRuleBatchPersistenceError("流水规则批次保存失败，请稍后重试。")
        )

        self.assertEqual(conflict_status, HTTPStatus.CONFLICT)
        self.assertEqual(conflict_payload["error"], "bank_flow_rule_batch_version_conflict")
        self.assertEqual(conflict_payload["message"], "bank_flow_rule_batch_version_conflict")
        self.assertEqual(invalid_status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            invalid_payload["error"],
            "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
        )
        self.assertEqual(occupied_status, HTTPStatus.CONFLICT)
        self.assertEqual(occupied_payload["message"], "所选流水已被其他批次占用。")
        self.assertEqual(occupied_payload["row_ids"], ["bank-1"])
        self.assertEqual(occupied_payload["conflicting_case_ids"], ["submitted-batch"])
        self.assertEqual(persistence_status, HTTPStatus.INTERNAL_SERVER_ERROR)
        self.assertEqual(persistence_payload["error"], "bank_flow_rule_batch_persistence_failed")
        self.assertEqual(persistence_payload["message"], "流水规则批次保存失败，请稍后重试。")


if __name__ == "__main__":
    unittest.main()
