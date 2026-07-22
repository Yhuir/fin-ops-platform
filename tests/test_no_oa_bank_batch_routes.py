from __future__ import annotations

import unittest
from http import HTTPStatus
from types import SimpleNamespace

from fin_ops_platform.app.auth import OARequestSession
from fin_ops_platform.app.routes_no_oa_bank_batches import NoOaBankBatchApiRoutes
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.no_oa_bank_batch_application_service import NoOaBankBatchRelationMutationError


class FakeNoOaApplicationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self.list_relation_modes: list[str] = []
        self.submit_failures: dict[str, Exception] = {}

    def list_batches_payload(self, query, *, relation_mode="no_oa_bank_batch"):
        self.list_relation_modes.append(relation_mode)
        self.calls.append(("list", query))
        return {"summary": {}, "batches": [], "read_model_status": "fresh"}

    def tag_selection_payload(self):
        self.calls.append(("tag_selection", None))
        return {"version": 1, "selected_tag_codes": []}

    def update_tag_selection(self, payload, *, actor_id):
        self.calls.append(("update_tag_selection", {"payload": payload, "actor_id": actor_id}))
        if payload.get("expected_version") == 0:
            raise AppSettingsValidationError("no_oa_bank_batch_tag_selection_version_conflict", "version conflict")
        return {"version": 2, "selected_tag_codes": list(payload.get("selected_tag_codes") or [])}

    def submit_batch(
        self,
        batch_id,
        *,
        actor,
        expected_version,
        note,
        relation_mode="no_oa_bank_batch",
        persist=True,
    ):
        self.calls.append(
            (
                "submit_batch",
                {
                    "batch_id": batch_id,
                    "actor": actor,
                    "expected_version": expected_version,
                    "note": note,
                    "persist": persist,
                },
            )
        )
        failure = self.submit_failures.get(batch_id)
        if failure is not None:
            raise failure
        return {
            "batch": {"batch_id": batch_id, "version": 2},
            "pair_relation": {"case_id": f"case-{batch_id}"},
            "affected_months": ["2026-05"],
        }

    def withdraw_batch(self, batch_id, *, actor, expected_version, reason):
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
            "batch": {"batch_id": batch_id, "version": 3},
            "affected_months": ["2026-05"],
        }

    def reset_submitted_bank_flow_rule_batches(self, *, actor, reason):
        self.calls.append(
            (
                "reset_submitted_bank_flow_rule_batches",
                {
                    "actor": actor,
                    "reason": reason,
                },
            )
        )
        return {
            "summary": {"reset_count": 2, "batch_count": 2, "row_count": 4, "affected_months": ["2026-05"]},
            "affected_months": ["2026-05"],
            "results": [{"batch_id": "batch-001", "status": "withdrawn"}],
        }

    def after_mutation(self, affected_months, *, changed_case_ids, persist=True, action_name=None):
        self.calls.append(
            (
                "after_mutation",
                {
                    "affected_months": list(affected_months),
                    "changed_case_ids": list(changed_case_ids),
                    "persist": persist,
                    "action_name": action_name,
                },
            )
        )
        return False


def fake_session(username: str = "alice"):
    return SimpleNamespace(identity=SimpleNamespace(username=username, user_id="oa-001"))


def oa_session(username: str = "alice") -> OARequestSession:
    return OARequestSession(
        token="test-token",
        identity=OAUserIdentity(
            user_id="oa-001",
            username=username,
            display_name=username,
            nickname=username,
            roles=("finance",),
        ),
        allowed=True,
        access_tier="full_access",
        can_access_app=True,
        can_mutate_data=True,
        can_admin_access=False,
    )


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
        self.assertEqual(service.list_relation_modes, ["no_oa_bank_batch"])

    def test_no_oa_route_does_not_handle_bank_flow_rule_batches(self) -> None:
        service = FakeNoOaApplicationService()
        routes = NoOaBankBatchApiRoutes(
            application_service=service,
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        response = routes.route("GET", "/api/bank-flow-rule-batches", {"bucket": ["submitted"]}, None, {})

        self.assertIsNone(response)
        self.assertEqual(service.calls, [])
        self.assertEqual(service.list_relation_modes, [])

    def test_route_owner_handles_http_mapping_with_platform_ports(self) -> None:
        service = FakeNoOaApplicationService()
        session = oa_session("route-user")
        routes = NoOaBankBatchApiRoutes(
            application_service=service,
            resolve_mutation_session=lambda _headers: session,
            load_json_body=lambda body: ({"expected_version": "5", "note": " ok ", "body": body}, None),
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        list_response = routes.route("GET", "/api/no-oa-bank-batches", {"bucket": ["unsubmitted"]}, None, {})
        tag_response = routes.route("GET", "/api/no-oa-bank-batches/tag-selection", {}, None, {})
        submit_response = routes.route("POST", "/api/no-oa-bank-batches/batch%2F001/submit", {}, "{}", {})
        withdraw_response = routes.route("POST", "/api/no-oa-bank-batches/batch%2F001/withdraw", {}, "{}", {})

        self.assertEqual(list_response["status"], HTTPStatus.OK)
        self.assertEqual(tag_response["payload"]["version"], 1)
        self.assertEqual(submit_response["status"], HTTPStatus.OK)
        self.assertEqual(withdraw_response["status"], HTTPStatus.OK)
        self.assertEqual(withdraw_response["payload"]["batch"]["version"], 3)
        self.assertEqual(
            service.calls[:4],
            [
                ("list", {"bucket": ["unsubmitted"]}),
                ("tag_selection", None),
                (
                    "submit_batch",
                    {
                        "batch_id": "batch/001",
                        "actor": "route-user",
                        "expected_version": 5,
                        "note": "ok",
                        "persist": True,
                    },
                ),
                (
                    "withdraw_batch",
                    {
                        "batch_id": "batch/001",
                        "actor": "route-user",
                        "expected_version": 5,
                        "reason": "ok",
                    },
                ),
            ],
        )

    def test_route_owner_returns_session_or_body_errors_before_service_call(self) -> None:
        service = FakeNoOaApplicationService()
        load_calls: list[object] = []
        routes = NoOaBankBatchApiRoutes(
            application_service=service,
            resolve_mutation_session=lambda _headers: {"status": HTTPStatus.FORBIDDEN, "payload": {"error": "permission_denied"}},
            load_json_body=lambda body: load_calls.append(body) or ({}, {"status": HTTPStatus.BAD_REQUEST}),
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        forbidden_response = routes.route("PUT", "/api/no-oa-bank-batches/tag-selection", {}, "{}", {})

        self.assertEqual(forbidden_response["status"], HTTPStatus.FORBIDDEN)
        self.assertEqual(load_calls, [])
        self.assertEqual(service.calls, [])

        routes = NoOaBankBatchApiRoutes(
            application_service=service,
            resolve_mutation_session=lambda _headers: oa_session(),
            load_json_body=lambda body: ({}, {"status": HTTPStatus.BAD_REQUEST, "payload": {"error": "invalid_json"}}),
            json_response=lambda status, payload: {"status": status, "payload": payload},
        )

        body_error_response = routes.route("PUT", "/api/no-oa-bank-batches/tag-selection", {}, "{", {})

        self.assertEqual(body_error_response["status"], HTTPStatus.BAD_REQUEST)
        self.assertEqual(service.calls, [])

    def test_list_batches_invalid_paging_returns_structured_400(self) -> None:
        class InvalidPagingService(FakeNoOaApplicationService):
            def list_batches_payload(self, query, *, relation_mode="no_oa_bank_batch"):  # type: ignore[no-untyped-def]
                self.calls.append(("list", query))
                raise NoOaBankBatchRelationMutationError("invalid_paging", "page_size must be <= 200.")

        service = InvalidPagingService()
        routes = NoOaBankBatchApiRoutes(application_service=service)

        status, payload = routes.list_batches({"page": ["1"], "page_size": ["201"]})

        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload["error"], "invalid_paging")
        self.assertEqual(payload["message"], "page_size must be <= 200.")
        self.assertEqual(service.calls, [("list", {"page": ["1"], "page_size": ["201"]})])

    def test_tag_selection_version_conflict_returns_409_and_error_code(self) -> None:
        service = FakeNoOaApplicationService()
        routes = NoOaBankBatchApiRoutes(application_service=service)

        status, payload = routes.update_tag_selection(
            {"expected_version": 0, "selected_tag_codes": ["fee"], "actor": "fin-user"},
            session=fake_session(),
        )

        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload["error"], "no_oa_bank_batch_tag_selection_version_conflict")
        self.assertEqual(
            service.calls,
            [
                (
                    "update_tag_selection",
                    {
                        "payload": {"expected_version": 0, "selected_tag_codes": ["fee"], "actor": "fin-user"},
                        "actor_id": "fin-user",
                    },
                )
            ],
        )

    def test_submit_batch_preserves_expected_version_and_actor_mapping(self) -> None:
        service = FakeNoOaApplicationService()
        routes = NoOaBankBatchApiRoutes(application_service=service)

        status, payload = routes.submit_batch(
            "batch-001",
            {"expected_version": "7", "note": "  reviewed  "},
            session=fake_session("finance-user"),
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["batch"]["version"], 2)
        self.assertEqual(
            service.calls,
            [
                (
                    "submit_batch",
                    {
                        "batch_id": "batch-001",
                        "actor": "finance-user",
                        "expected_version": 7,
                        "note": "reviewed",
                        "persist": True,
                    },
                )
            ],
        )

    def test_bulk_submit_accumulates_partial_failures_and_persists_once(self) -> None:
        service = FakeNoOaApplicationService()
        service.submit_failures["missing"] = KeyError("missing")
        service.submit_failures["conflict"] = ValueError("no_oa_bank_batch_version_conflict")
        routes = NoOaBankBatchApiRoutes(application_service=service)

        status, payload = routes.bulk_submit(
            {
                "batches": [
                    {"batch_id": "batch-001", "expected_version": "3", "note": "ok"},
                    {"batch_id": "missing"},
                    {"batch_id": "conflict"},
                    {"batch_id": ""},
                    "invalid",
                ],
                "note": "fallback",
            },
            session=fake_session("bulk-user"),
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload["summary"], {"submitted": 1, "failed": 4})
        self.assertEqual(payload["affected_months"], ["2026-05"])
        self.assertEqual(payload["affected_scope_keys"], ["2026-05"])
        self.assertEqual(
            payload["operation_barrier_targets"],
            [],
        )
        self.assertFalse(payload["workbench_rebuild_queued"])
        self.assertEqual(payload["results"][0]["status"], "submitted")
        self.assertEqual(payload["results"][1]["error"], "unknown_no_oa_bank_batch")
        self.assertEqual(payload["results"][2]["error"], "no_oa_bank_batch_version_conflict")
        self.assertEqual(payload["results"][3]["error"], "invalid_no_oa_bank_batch_request")
        self.assertEqual(payload["results"][4]["error"], "invalid_no_oa_bank_batch_request")
        self.assertEqual(service.calls[-1][0], "after_mutation")
        self.assertEqual(
            service.calls[-1][1],
            {
                "affected_months": ["2026-05"],
                "changed_case_ids": ["case-batch-001"],
                "persist": True,
                "action_name": "no_oa_bank_batch_submit",
            },
        )


if __name__ == "__main__":
    unittest.main()
