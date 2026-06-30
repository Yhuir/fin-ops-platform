from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.services.bank_detail_category_side_effects import BankDetailCategoryMutationSideEffectPort
from fin_ops_platform.services.postgres_repositories.read_models import WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


def _session(*, can_mutate_data: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        can_mutate_data=can_mutate_data,
        identity=SimpleNamespace(username="TESTFULL001", user_id="1"),
    )


class _ReadModelQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class _BankDetailStatusRepository:
    def __init__(self, *, status: str, bank_auto_tag_rules_version: int | None = 1) -> None:
        self.status = status
        self.bank_auto_tag_rules_version = bank_auto_tag_rules_version
        self.transaction_reads = 0
        self.account_reads = 0

    def bank_detail_scope_keys_for_range(self, *, date_from: str | None, date_to: str | None) -> list[str]:
        return [str(date_from or "")[:7] or "2026-01"]

    def bank_detail_scope_summary(self, *, scope_keys: list[str]) -> dict[str, object]:
        return {
            "read_model_status": self.status,
            "read_model_scope_keys": list(scope_keys),
            "read_model_generated_at": "2026-05-27T21:00:00+00:00",
            "read_model_scope_signatures": {
                scope_key: {
                    "status": "fresh",
                    "source_versions": (
                        {"bank_auto_tag_rules_version": self.bank_auto_tag_rules_version}
                        if self.bank_auto_tag_rules_version is not None
                        else {}
                    ),
                    "dirty_status": "pending" if self.status == "refreshing" else None,
                }
                for scope_key in scope_keys
            },
        }

    def list_bank_detail_transactions(self, **_kwargs: object) -> dict[str, object]:
        self.transaction_reads += 1
        return {
            "account_key": None,
            "date_from": _kwargs.get("date_from"),
            "date_to": _kwargs.get("date_to"),
            "rows": [
                {
                    "id": "txn-existing-read-model",
                    "trade_time": "2026-01-02 10:00:00",
                    "counterparty_name": "银行",
                    "direction": "expense",
                    "direction_label": "支",
                    "amount": "10.00",
                    "balance": "90.00",
                    "summary": "手续费",
                    "purpose": "",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "auto_category_code": "fee",
                    "auto_category_label": "手续费",
                    "effective_category_code": "fee",
                    "effective_category_label": "手续费",
                }
            ],
            "category_counts": {"fee": 1, "uncategorized": 0},
            "pagination": {"page": 1, "page_size": 100, "total": 1},
            "read_model_status": self.status,
        }

    def list_bank_detail_accounts(self, **_kwargs: object) -> dict[str, object]:
        self.account_reads += 1
        return {
            "accounts": [
                {
                    "account_key": "icbc:6386",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "display_name": "工商银行 6386",
                    "latest_balance": "90.00",
                    "latest_balance_at": "2026-01-02 10:00:00",
                    "has_balance": True,
                    "transaction_count": 1,
                }
            ],
            "total_balance": "90.00",
            "balance_account_count": 1,
            "missing_balance_account_count": 0,
            "read_model_status": self.status,
        }

    def list_bank_account_balances(self, **kwargs: object) -> dict[str, object]:
        return self.list_bank_detail_accounts(**kwargs)


class BankAutoTagRulesApiTests(unittest.TestCase):
    def _update_auto_tag_rules_response(self, app, body: str | bytes | None, headers: dict[str, str] | None = None):
        return app.handle_request("PUT", "/api/bank-details/auto-tag-rules", body, headers=headers)

    def _file_replacement_response(self, app, body: str | bytes | None, headers: dict[str, str] | None = None):
        return app.handle_request("POST", "/api/bank-details/auto-tag-rules/file-replacement", body, headers=headers)

    def _confirm_category_response(
        self,
        app,
        transaction_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None = None,
    ):
        return app.handle_request(
            "POST",
            f"/api/bank-details/transactions/{transaction_id}/category-confirmation",
            body,
            headers=headers,
        )

    def _bank_detail_transactions_payload(
        self,
        app,
        *,
        account_key: str | None = None,
        date_from: str | None,
        date_to: str | None,
        keyword: str | None,
        category_code: str | None = None,
        category_primary_label: str | None = None,
        category_sub_label: str | None = None,
        category_third_label: str | None = None,
        page: str | None = "1",
        page_size: str | None = "100",
    ) -> dict[str, object]:
        status, payload = app._bank_details_routes().transactions(
            account_key=account_key,
            date_from=date_from,
            date_to=date_to,
            keyword=keyword,
            category_code=category_code,
            category_primary_label=category_primary_label,
            category_sub_label=category_sub_label,
            category_third_label=category_third_label,
            page=page,
            page_size=page_size,
        )
        self.assertIn(int(status), {200, 202})
        return payload

    def _bank_detail_accounts_payload(
        self,
        app,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> dict[str, object]:
        status, payload = app._bank_details_routes().accounts(date_from=date_from, date_to=date_to)
        self.assertIn(int(status), {200, 202})
        return payload

    def test_get_returns_system_active_archived_fields_and_permissions(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app.handle_request("GET", "/api/bank-details/auto-tag-rules")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["system_rule"]["code"], "internal_transfer")
        self.assertEqual(payload["system_rule"]["priority_label"], "优先级 1")
        self.assertFalse(payload["system_rule"]["editable"])
        self.assertIn("salary", [rule["code"] for rule in payload["active_rules"]])
        self.assertEqual(payload["active_rules"][0]["priority_label"], "优先级 2")
        self.assertEqual({rule["priority"] for rule in payload["active_rules"]}, {2})
        fee = next(rule for rule in payload["active_rules"] if rule["code"] == "fee")
        self.assertEqual(fee["output_primary_label"], "费用")
        self.assertEqual(fee["output_sub_label"], "手续费")
        self.assertEqual(payload["field_options"][0]["value"], "counterparty_name")
        self.assertEqual(payload["permissions"], {"can_save": True})

    def test_file_replacement_endpoint_uses_bundled_rules_and_triggers_lifecycle(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._file_replacement_response(app, None, {})

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(payload["active_rules"]), 30)
        self.assertEqual(payload["system_rule"]["priority_label"], "优先级 1")
        self.assertEqual(payload["active_rules"][0]["priority_label"], "优先级 2")
        self.assertEqual({rule["priority"] for rule in payload["active_rules"]}, {2})
        self.assertIn(("bank_detail", "all", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("turnover_ledger", "all", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("no_oa_bank_batch", "all", "bank_auto_tag_rules_changed"), queue.enqueued)

    def test_put_direction_only_change_persists_reloads_and_triggers_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            queue = _ReadModelQueue()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)
            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            active = [
                {**rule, "direction": "expense"}
                if rule["code"] == "fee"
                else rule
                for rule in current["active_rules"]
            ]

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = self._update_auto_tag_rules_response(
                    app,
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": active,
                            "archived_rules": current["archived_rules"],
                        },
                        ensure_ascii=False,
                    ),
                    {},
                )

            payload = json.loads(response.body)
            reloaded = build_application(data_dir=data_dir)._app_settings_service.get_bank_auto_tag_rules_payload()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["version"], current["version"] + 1)
        self.assertEqual(next(rule for rule in payload["active_rules"] if rule["code"] == "fee")["direction"], "expense")
        self.assertEqual(next(rule for rule in reloaded["active_rules"] if rule["code"] == "fee")["direction"], "expense")
        self.assertIn(("bank_detail", "all", "bank_auto_tag_rules_changed"), queue.enqueued)
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["metadata"]["rule_payload_changes"], [{"code": "fee"}])

    def test_put_retries_transient_stale_settings_read_after_write(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            active = [
                {**rule, "direction": "expense"}
                if rule["code"] == "fee"
                else rule
                for rule in current["active_rules"]
            ]
            original_load = app._state_store.load_app_settings
            original_save = app._state_store.save_app_settings
            stale_read = {"remaining": 0, "snapshot": None}

            def save_app_settings(snapshot: dict[str, object]) -> None:
                stale_read["snapshot"] = original_load()
                original_save(snapshot)
                stale_read["remaining"] = 1

            def load_app_settings() -> dict[str, object]:
                if int(stale_read["remaining"]):
                    stale_read["remaining"] = 0
                    return dict(stale_read["snapshot"] or {})
                return original_load()

            app._state_store.save_app_settings = save_app_settings
            app._state_store.load_app_settings = load_app_settings

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = self._update_auto_tag_rules_response(
                    app,
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": active,
                            "archived_rules": current["archived_rules"],
                        },
                        ensure_ascii=False,
                    ),
                    {},
                )

            payload = json.loads(response.body)
            reloaded = build_application(data_dir=data_dir)._app_settings_service.get_bank_auto_tag_rules_payload()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["version"], current["version"] + 1)
        reloaded_fee = next(rule for rule in reloaded["active_rules"] if rule["code"] == "fee")
        self.assertEqual(reloaded_fee["direction"], "expense")

    def test_reapply_endpoint_enqueues_bank_detail_refresh_without_changing_rules(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        app._bank_detail_available_month_scope_provider = lambda: SimpleNamespace(
            scope_keys=lambda: ["2026-03", "2026-04"]
        )
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app.handle_request("POST", "/api/bank-details/auto-tag-rules/reapply", "{}")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["version"], current["version"])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-03", "2026-04"])
        self.assertEqual(
            payload["freshness_targets"],
            [
                {"read_model_key": "bank_detail", "scope_key": "2026-03"},
                {"read_model_key": "bank_detail", "scope_key": "2026-04"},
            ],
        )
        self.assertEqual(payload["enqueued_jobs"], ["bank_detail.read_model.refresh"])
        self.assertEqual(
            queue.enqueued,
            [
                ("bank_detail", "2026-03", "bank_auto_tag_rules_reapply_requested"),
                ("bank_detail", "2026-04", "bank_auto_tag_rules_reapply_requested"),
            ],
        )
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["action"], "bank_auto_tag_rules_reapply_requested")
        self.assertEqual(audit["metadata"]["scope_keys"], ["2026-03", "2026-04"])
        self.assertEqual(audit["metadata"]["version"], current["version"])

    def test_reapply_endpoint_fails_when_bank_detail_refresh_queue_is_unavailable(self) -> None:
        app = build_application()
        app._runtime_repositories = SimpleNamespace(queue_repository=None)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app.handle_request("POST", "/api/bank-details/auto-tag-rules/reapply", "{}")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "bank_auto_tag_rules_reapply_unavailable")

    def test_reapply_endpoint_requires_mutation_permission(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)

        with patch.object(
            app,
            "_resolve_bank_details_read_session",
            return_value=(_session(can_mutate_data=False), None),
        ):
            response = app.handle_request("POST", "/api/bank-details/auto-tag-rules/reapply", "{}")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")
        self.assertEqual(queue.enqueued, [])

    def test_confirmation_endpoint_rejects_single_auto_match_candidate(self) -> None:
        app = build_application()
        confirm_calls: list[object] = []

        def confirm_stub(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(kwargs)
            return {}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "auto_matched",
            "auto_candidate_category_codes": ["fee"],
            "rule_version": "bank-auto-tag-rules:1",
        }
        app._bank_transaction_category_service.confirm_auto_category = confirm_stub

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._confirm_category_response(app,
                "txn-1",
                json.dumps({"category_code": "fee"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_category_confirmation_candidate")
        self.assertEqual(confirm_calls, [])

    def test_confirmation_endpoint_rejects_unmatched_row_without_current_candidates(self) -> None:
        app = build_application()
        confirm_calls: list[dict[str, object]] = []

        def confirm_stub(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_transaction_category_service.confirm_auto_category = confirm_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: []
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        for suggestion in (None, {"category_resolution_status": "unmatched"}):
            app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id, suggestion=suggestion: suggestion

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = self._confirm_category_response(app,
                    "txn-unmatched",
                    json.dumps({"category_code": "fee"}),
                    {},
                )

            payload = json.loads(response.body)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(payload["error"], "invalid_category_confirmation_candidate")

        self.assertEqual(confirm_calls, [])

    def test_confirmation_endpoint_uses_only_current_needs_confirmation_candidates(self) -> None:
        app = build_application()
        confirm_calls: list[dict[str, object]] = []

        def confirm_stub(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "needs_confirmation",
            "auto_candidate_category_codes": ["fee", "salary", "fee", ""],
            "rule_version": "bank-auto-tag-rules:3",
        }
        app._bank_transaction_category_service.confirm_auto_category = confirm_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: []
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._confirm_category_response(app,
                "txn-candidate",
                json.dumps({"category_code": "salary"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(confirm_calls[0]["transaction_id"], "txn-candidate")
        self.assertEqual(confirm_calls[0]["category_code"], "salary")
        self.assertEqual(confirm_calls[0]["candidate_category_codes"], ["fee", "salary"])

    def test_confirmation_endpoint_allows_external_turnover_third_label_candidate(self) -> None:
        app = build_application()
        confirm_calls: list[dict[str, object]] = []

        def confirm_stub(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "needs_confirmation",
            "auto_candidate_category_codes": ["external_turnover"],
            "rule_version": "bank-auto-tag-rules:7",
            "auto_candidate_categories": [
                {
                    "category_code": "external_turnover",
                    "category_label": "借出款",
                    "category_primary_label": "外部往来款付款",
                    "category_sub_label": "借出款",
                    "category_third_label": "个人往来",
                    "category_label_path": ["外部往来款付款", "借出款", "个人往来"],
                    "turnover_action_type": "pending_collection",
                    "turnover_family": "personal",
                },
                {
                    "category_code": "external_turnover",
                    "category_label": "借出款",
                    "category_primary_label": "外部往来款付款",
                    "category_sub_label": "借出款",
                    "category_third_label": "公司往来",
                    "category_label_path": ["外部往来款付款", "借出款", "公司往来"],
                    "turnover_action_type": "pending_collection",
                    "turnover_family": "company",
                },
            ],
        }
        app._bank_transaction_category_service.confirm_auto_category = confirm_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: []
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._confirm_category_response(app,
                "txn-candidate",
                json.dumps(
                    {
                        "category_code": "external_turnover",
                        "category_third_label": "公司往来",
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(confirm_calls[0]["transaction_id"], "txn-candidate")
        self.assertEqual(confirm_calls[0]["category_code"], "external_turnover")
        self.assertEqual(confirm_calls[0]["category_third_label"], "公司往来")
        self.assertEqual(confirm_calls[0]["category_label_path"], ["外部往来款付款", "借出款", "公司往来"])
        self.assertEqual(confirm_calls[0]["turnover_action_type"], "pending_collection")
        self.assertEqual(confirm_calls[0]["turnover_family"], "company")
        self.assertEqual(confirm_calls[0]["candidate_category_codes"], ["external_turnover"])

    def test_confirmation_endpoint_rejects_non_auto_rule_candidate(self) -> None:
        app = build_application()
        confirm_calls: list[dict[str, object]] = []

        def confirm_stub(**kwargs: object) -> dict[str, object]:
            confirm_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "needs_confirmation",
            "auto_candidate_category_codes": ["fee", "salary", "borrow_in_bank_pending_repayment"],
            "rule_version": "bank-auto-tag-rules:3",
        }
        app._bank_transaction_category_service.confirm_auto_category = confirm_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: []
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._confirm_category_response(app,
                "txn-candidate",
                json.dumps({"category_code": "borrow_in_bank_pending_repayment"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_category_confirmation_candidate")
        self.assertEqual(confirm_calls, [])

    def test_manual_assignment_endpoint_allows_unmatched_row_to_choose_active_tag(self) -> None:
        app = build_application()
        assign_calls: list[dict[str, object]] = []
        mutations: list[dict[str, object]] = []
        saved_snapshots: list[dict[str, object]] = []

        def assign_stub(**kwargs: object) -> dict[str, object]:
            assign_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "unmatched",
        }
        app._bank_transaction_category_service.assign_manual_category = assign_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: ["2026-02"]
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda snapshot: saved_snapshots.append(snapshot))

        with (
            patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)),
            patch.object(BankDetailCategoryMutationSideEffectPort, "after_mutation", lambda _self, **kwargs: mutations.append(dict(kwargs))),
        ):
            response = app._handle_request_untracked(
                "POST",
                "/api/bank-details/transactions/txn-unmatched/category-assignment",
                json.dumps({"category_code": "salary"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["affected_months"], ["2026-02"])
        self.assertEqual(assign_calls[0]["transaction_id"], "txn-unmatched")
        self.assertEqual(assign_calls[0]["category_code"], "salary")
        self.assertEqual(assign_calls[0]["actor"], "TESTFULL001")
        self.assertTrue(saved_snapshots)
        self.assertEqual(mutations[0]["action"], "bank_detail_category_manually_assigned")
        self.assertEqual(mutations[0]["metadata"]["selected_category_code"], "salary")
        self.assertEqual(mutations[0]["metadata"]["previous_resolution_status"], "unmatched")
        self.assertEqual(mutations[0]["metadata"]["assignment_source"], "manual")
        self.assertNotIn("candidate_category_codes", mutations[0]["metadata"])

    def test_manual_assignment_endpoint_rejects_non_auto_rule_tag(self) -> None:
        app = build_application()
        assign_calls: list[dict[str, object]] = []

        def assign_stub(**kwargs: object) -> dict[str, object]:
            assign_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "unmatched",
        }
        app._bank_transaction_category_service.assign_manual_category = assign_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: []
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app._handle_request_untracked(
                "POST",
                "/api/bank-details/transactions/txn-unmatched/category-assignment",
                json.dumps({"category_code": "borrow_in_bank_pending_repayment"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_manual_category_assignment_candidate")
        self.assertEqual(assign_calls, [])

    def test_manual_assignment_endpoint_rejects_auto_candidate_confirmation_targets(self) -> None:
        app = build_application()
        assign_calls: list[dict[str, object]] = []

        def assign_stub(**kwargs: object) -> dict[str, object]:
            assign_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_detail_auto_category_suggestion_provider = lambda _transaction_id: {
            "category_resolution_status": "needs_confirmation",
            "auto_candidate_category_codes": ["fee", "salary"],
        }
        app._bank_transaction_category_service.assign_manual_category = assign_stub

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app._handle_request_untracked(
                "POST",
                "/api/bank-details/transactions/txn-candidate/category-assignment",
                json.dumps({"category_code": "salary"}),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_manual_category_assignment_target")
        self.assertEqual(assign_calls, [])

    def test_manual_assignment_delete_endpoint_clears_manual_category(self) -> None:
        app = build_application()
        clear_calls: list[dict[str, object]] = []
        mutations: list[dict[str, object]] = []

        def clear_stub(**kwargs: object) -> dict[str, object]:
            clear_calls.append(dict(kwargs))
            return {"ok": True}

        app._bank_transaction_category_service.clear_manual_category = clear_stub
        app._bank_transaction_category_affected_months = lambda _transaction_ids: ["2026-02"]
        app._state_store = SimpleNamespace(save_bank_transaction_categories=lambda _snapshot: None)

        with (
            patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)),
            patch.object(BankDetailCategoryMutationSideEffectPort, "after_mutation", lambda _self, **kwargs: mutations.append(dict(kwargs))),
        ):
            response = app._handle_request_untracked(
                "DELETE",
                "/api/bank-details/transactions/txn-manual/category-assignment",
                None,
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(clear_calls[0]["transaction_id"], "txn-manual")
        self.assertEqual(clear_calls[0]["actor"], "TESTFULL001")
        self.assertEqual(mutations[0]["action"], "bank_detail_category_manual_assignment_cleared")
        self.assertEqual(mutations[0]["metadata"]["assignment_source"], "manual")

    def test_put_renames_reorders_adds_archives_audits_and_triggers_lifecycle(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")
        fee = next(rule for rule in current["active_rules"] if rule["code"] == "fee")
        active = [
            {
                **salary,
                "label": "薪酬发放",
                "output_primary_label": "费用",
                "output_sub_label": "薪酬发放",
                "rules": {**salary["rules"], "contains_any": ["工资", "薪酬"], "contains": ["工资", "薪酬"]},
            },
            {**fee, "rules": fee["rules"]},
            *[rule for rule in current["active_rules"] if rule["code"] not in {"salary", "fee", "bonus"}],
            {
                "output_primary_label": "收入",
                "output_sub_label": "银行利息",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact": [],
                    "contains": ["利息"],
                    "excludes": [],
                },
            },
        ]
        archived = [
            {
                "code": "bonus",
                "label": "奖金",
                "output_primary_label": "费用",
                "output_sub_label": "奖金",
                "rules": {
                    "match_fields": [],
                    "exact": [],
                    "contains": [],
                    "excludes": [],
                },
            }
        ]
        lifecycle_calls: list[tuple[str, dict[str, object]]] = []

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            with patch.object(
                app,
                "_execute_derived_data_lifecycle_event",
                side_effect=lambda event, **kwargs: lifecycle_calls.append((event, kwargs)) or {"event": event},
            ):
                response = self._update_auto_tag_rules_response(app,
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": active,
                            "archived_rules": archived,
                        },
                        ensure_ascii=False,
                    ),
                    {},
                )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["version"], current["version"] + 1)
        saved_salary = next(rule for rule in payload["active_rules"] if rule["code"] == "salary")
        self.assertEqual(saved_salary["label"], "薪酬发放")
        self.assertEqual(saved_salary["output_primary_label"], "费用")
        self.assertEqual(saved_salary["output_sub_label"], "薪酬发放")
        self.assertTrue(any(rule["label"] == "银行利息" and rule["code"].startswith("custom_") for rule in payload["active_rules"]))
        self.assertEqual([rule["code"] for rule in payload["archived_rules"]], ["bonus"])
        self.assertEqual(lifecycle_calls[0][0], "bank_auto_tag_rules_changed")
        self.assertEqual(lifecycle_calls[0][1]["scope_keys"], ["all"])
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["action"], "bank_auto_tag_rules_updated")
        metadata = audit["metadata"]
        self.assertEqual(metadata["old_version"], current["version"])
        self.assertEqual(metadata["new_version"], current["version"] + 1)
        self.assertEqual(metadata["renamed_tags"][0]["code"], "salary")
        self.assertIn("bonus", metadata["archived_codes"])
        self.assertTrue(metadata["added_tags"])
        self.assertTrue(metadata["rule_changes"])

    def test_put_updates_auto_category_engine_rule_source(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active = [
            *current["active_rules"],
            {
                "output_primary_label": "费用",
                "output_sub_label": "网银证书服务费",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact_any": [],
                    "contains_any": [],
                    "contains_all": ["网银", "服务费"],
                    "none_of": [],
                    "regex_any": [],
                },
            },
        ]

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "refresh_scope": {"date_from": "2026-01-01", "date_to": "2026-01-31"},
                        "active_rules": active,
                        "archived_rules": current["archived_rules"],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        custom_rule = next(rule for rule in payload["active_rules"] if rule["label"] == "网银证书服务费")
        self.assertEqual(custom_rule["output_primary_label"], "费用")
        self.assertEqual(custom_rule["output_sub_label"], "网银证书服务费")
        suggestions = app._bank_transaction_auto_category_service.suggest_for_rows(
            [
                {
                    "id": "txn-online-banking-certificate-fee",
                    "debit_amount": "100.00",
                    "summary": "网银证书服务费",
                }
            ]
        )

        suggestion = suggestions["txn-online-banking-certificate-fee"]
        self.assertEqual(suggestion["category_code"], custom_rule["code"])
        self.assertEqual(suggestion["auto_category_evidence"]["condition_type"], "contains_all")

    def test_put_primary_label_only_change_persists_reconfigures_engine_and_enqueues_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            app._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
                app._default_bank_auto_tag_rules_file_source(),
                actor_id="settings-owner",
            )
            queue = _ReadModelQueue()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)
            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            target = next(
                rule
                for rule in current["active_rules"]
                if rule["output_primary_label"] == "往来款付款" and rule["output_sub_label"] == "借出款"
            )
            active = []
            for rule in current["active_rules"]:
                next_rule = dict(rule)
                if next_rule.get("output_primary_label") == "往来款付款":
                    next_rule["output_primary_label"] = "外部往来款付款"
                active.append(next_rule)

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = app.handle_request(
                    "PUT",
                    "/api/bank-details/auto-tag-rules",
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": active,
                            "archived_rules": current["archived_rules"],
                        },
                        ensure_ascii=False,
                    ),
                )

            payload = json.loads(response.body)
            reloaded = build_application(data_dir=data_dir)._app_settings_service.get_bank_auto_tag_rules_payload()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["version"], current["version"] + 1)
        saved_target = next(rule for rule in payload["active_rules"] if rule["code"] == target["code"])
        self.assertEqual(saved_target["label"], "借出款")
        self.assertEqual(saved_target["output_primary_label"], "外部往来款付款")
        self.assertEqual(saved_target["output_sub_label"], "借出款")
        reloaded_target = next(rule for rule in reloaded["active_rules"] if rule["code"] == target["code"])
        self.assertEqual(reloaded_target["output_primary_label"], "外部往来款付款")
        suggestions = app._bank_transaction_auto_category_service.suggest_for_rows(
            [
                {
                    "id": "txn-external-turnover-borrow-out",
                    "direction": "expense",
                    "purpose": "借据号 贷款本息",
                    "summary": "贷款扣款",
                }
            ]
        )
        suggestion = suggestions["txn-external-turnover-borrow-out"]
        self.assertIsNone(suggestion["category_code"])
        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        self.assertEqual(
            {
                candidate["category_third_label"]
                for candidate in suggestion["auto_candidate_categories"]
            },
            {"个人往来", "公司往来", "银行往来", "业务往来"},
        )
        self.assertTrue(
            all(
                candidate["category_code"] == target["code"]
                and candidate["category_primary_label"] == "外部往来款付款"
                and candidate["category_sub_label"] == "借出款"
                for candidate in suggestion["auto_candidate_categories"]
            )
        )
        self.assertIn(("bank_detail", "all", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("no_oa_bank_batch", "all", "bank_auto_tag_rules_changed"), queue.enqueued)

    def test_put_external_turnover_rule_clears_legacy_third_label_and_persists_action_type(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            app._app_settings_service.replace_bank_auto_tag_rules_from_file_source(
                app._default_bank_auto_tag_rules_file_source(),
                actor_id="settings-owner",
            )
            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            target = next(
                rule
                for rule in current["active_rules"]
                if rule["output_primary_label"] == "往来款付款" and rule["output_sub_label"] == "借出款"
            )
            active = []
            for rule in current["active_rules"]:
                next_rule = dict(rule)
                if next_rule["code"] == target["code"]:
                    next_rule["output_primary_label"] = "外部往来款付款"
                    next_rule["output_third_label"] = "公司往来"
                    next_rule["turnover_action_type"] = "pending_collection"
                active.append(next_rule)

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = app.handle_request(
                    "PUT",
                    "/api/bank-details/auto-tag-rules",
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": active,
                            "archived_rules": current["archived_rules"],
                        },
                        ensure_ascii=False,
                    ),
                )

            payload = json.loads(response.body)
            reloaded_app = build_application(data_dir=data_dir)
            reloaded = reloaded_app._app_settings_service.get_bank_auto_tag_rules_payload()

        self.assertEqual(response.status_code, 200)
        saved_target = next(rule for rule in payload["active_rules"] if rule["code"] == target["code"])
        self.assertEqual(saved_target["output_primary_label"], "外部往来款付款")
        self.assertEqual(saved_target["output_sub_label"], "借出款")
        self.assertNotIn("output_third_label", saved_target)
        self.assertEqual(saved_target["turnover_action_type"], "pending_collection")
        self.assertEqual(saved_target.get("turnover_family", ""), "")
        reloaded_target = next(rule for rule in reloaded["active_rules"] if rule["code"] == target["code"])
        self.assertNotIn("output_third_label", reloaded_target)
        self.assertEqual(reloaded_target["turnover_action_type"], "pending_collection")

        suggestions = reloaded_app._bank_transaction_auto_category_service.suggest_for_rows(
            [
                {
                    "id": "txn-external-turnover-borrow-out",
                    "direction": "expense",
                    "purpose": "借据号 贷款本息",
                    "summary": "贷款扣款",
                }
            ]
        )
        suggestion = suggestions["txn-external-turnover-borrow-out"]
        self.assertIsNone(suggestion["category_code"])
        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        self.assertEqual(
            [candidate["category_third_label"] for candidate in suggestion["auto_candidate_categories"]],
            ["个人往来", "公司往来", "银行往来", "业务往来"],
        )
        self.assertEqual(suggestion["turnover_action_type"], "pending_collection")

    def test_put_rejects_non_external_rule_with_turnover_fields(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active = []
        for rule in current["active_rules"]:
            next_rule = dict(rule)
            if next_rule["code"] == "fee":
                next_rule["output_third_label"] = "公司往来"
                next_rule["turnover_action_type"] = "pending_collection"
            active.append(next_rule)

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "active_rules": active,
                        "archived_rules": current["archived_rules"],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_auto_tag_rule")
        field_paths = {error["path"] for error in payload["field_errors"]}
        self.assertTrue(any(path.endswith(".output_third_label") for path in field_paths))
        self.assertTrue(any(path.endswith(".turnover_action_type") for path in field_paths))

    def test_put_rejects_false_success_when_settings_store_does_not_persist_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            fee = next(rule for rule in current["active_rules"] if rule["code"] == "fee")
            active = []
            for rule in current["active_rules"]:
                rules = dict(rule["rules"])
                if rule["code"] == "fee":
                    rules["contains_any"] = [*list(rules.get("contains_any") or []), "跨进程保存校验"]
                active.append({**rule, "rules": rules})
            lifecycle_calls: list[tuple[str, dict[str, object]]] = []

            app._state_store.save_app_settings = lambda _snapshot: None

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                with patch.object(
                    app,
                    "_execute_derived_data_lifecycle_event",
                    side_effect=lambda event, **kwargs: lifecycle_calls.append((event, kwargs)) or {"event": event},
                ):
                    response = app.handle_request(
                        "PUT",
                        "/api/bank-details/auto-tag-rules",
                        json.dumps(
                            {
                                "expected_version": current["version"],
                                "active_rules": active,
                                "archived_rules": current["archived_rules"],
                            },
                            ensure_ascii=False,
                        ),
                    )

            payload = json.loads(response.body)
            reloaded = build_application(data_dir=Path(temp_dir))._app_settings_service.get_bank_auto_tag_rules_payload()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "bank_auto_tag_rules_persistence_failed")
        self.assertEqual(reloaded["version"], current["version"])
        self.assertEqual(
            next(rule for rule in reloaded["active_rules"] if rule["code"] == "fee")["rules"],
            fee["rules"],
        )
        self.assertEqual(lifecycle_calls, [])
        self.assertEqual(app._audit_service.as_dicts(), [])

    def test_workbench_source_versions_include_bank_auto_tag_rules_version(self) -> None:
        app = build_application()

        with patch.object(app, "_current_bank_auto_tag_rules_version", return_value=42):
            matching_versions = app._workbench_matching_source_versions()
            read_model_versions = app._workbench_read_model_source_versions()
            sql_versions = app._workbench_sql_read_model_source_versions()
            aggregate_sql_versions = app._workbench_sql_read_model_source_versions("all")

        self.assertEqual(matching_versions["bank_auto_tag_rules_version"], 42)
        self.assertEqual(read_model_versions["bank_auto_tag_rules_version"], 42)
        self.assertEqual(sql_versions["bank_auto_tag_rules_version"], 42)
        self.assertEqual(sql_versions["builder"], WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION)
        self.assertEqual(aggregate_sql_versions["bank_auto_tag_rules_version"], 42)
        self.assertEqual(aggregate_sql_versions["builder"], WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION)

    def test_workbench_refresh_status_marks_old_bank_auto_tag_generation_stale(self) -> None:
        app = build_application()

        class WorkbenchRepository:
            def get_workbench_refresh_status(self, *, scope_key: str) -> dict[str, object]:
                return {
                    "scope_key": scope_key,
                    "read_model_status": "fresh",
                    "active_generation_id": "gen-1",
                    "generations": [
                        {
                            "generation_id": "gen-1",
                            "status": "active",
                            "source_versions": {
                                "builder": "2026-05-25-oa-attachment-source-groups",
                                "bank_auto_tag_rules_version": 1,
                                "oa_attachment_invoice_parser_version": app._current_oa_attachment_invoice_parser_version(),
                                "oa_projection_sync_version": app._current_oa_projection_sync_version(),
                            },
                        }
                    ],
                }

        app._workbench_sql_read_repository = WorkbenchRepository()

        with patch.object(app, "_current_bank_auto_tag_rules_version", return_value=2):
            response = app._handle_api_workbench_refresh_status("2026-05")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertIn("bank_auto_tag_rules_version_mismatch", payload["read_model_stale_reasons"])

    def test_put_derives_label_from_required_primary_and_optional_sub_label(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active = [
            *current["active_rules"],
            {
                "output_primary_label": "收入",
                "output_sub_label": "",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact_any": [],
                    "contains_any": ["利息"],
                    "contains_all": [],
                    "none_of": [],
                    "regex_any": [],
                },
            },
            {
                "output_primary_label": "费用",
                "output_sub_label": "网银证书服务费",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact_any": [],
                    "contains_any": ["网银证书"],
                    "contains_all": [],
                    "none_of": [],
                    "regex_any": [],
                },
            },
        ]

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "active_rules": active,
                        "archived_rules": current["archived_rules"],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        income = next(rule for rule in payload["active_rules"] if rule["output_primary_label"] == "收入")
        cert_fee = next(rule for rule in payload["active_rules"] if rule["output_sub_label"] == "网银证书服务费")
        self.assertEqual(income["label"], "收入")
        self.assertEqual(income["output_sub_label"], "")
        self.assertEqual(cert_fee["label"], "网银证书服务费")
        self.assertEqual(cert_fee["output_primary_label"], "费用")

    def test_put_enqueues_bank_detail_month_shards_for_rule_changes(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        app._import_service = SimpleNamespace(
            list_transactions=lambda month=None: [
                {"id": "txn-jan", "txn_date": "2026-01-24"},
                {"id": "txn-mar", "trade_time": "2026-03-05T10:00:00"},
            ]
        )
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active = [
            *current["active_rules"],
            {
                "output_primary_label": "费用",
                "output_sub_label": "网银证书服务费",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact_any": [],
                    "contains_any": [],
                    "contains_all": ["网银", "服务费"],
                    "none_of": [],
                    "regex_any": [],
                },
            },
        ]

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "refresh_scope": {"date_from": "2026-01-01", "date_to": "2026-01-31"},
                        "active_rules": active,
                        "archived_rules": current["archived_rules"],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(("turnover_ledger", "all", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("bank_detail", "2026-01", "bank_auto_tag_rules_changed_priority"), queue.enqueued)
        self.assertIn(("bank_detail", "2026-01", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("bank_detail", "2026-03", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertNotIn(("bank_detail", "all", "bank_auto_tag_rules_changed"), queue.enqueued)

    def test_bank_category_mutation_side_effect_port_enqueues_turnover_ledger_all_refresh(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        app._invalidate_workbench_after_bank_transaction_categories = lambda _months: True
        app._audit_service = SimpleNamespace(record_action=lambda **_kwargs: None)
        side_effect_port = BankDetailCategoryMutationSideEffectPort(
            enqueue_bank_detail_refresh=app._bank_detail_read_model_refresh_producer().enqueue,
            enqueue_turnover_ledger_refresh=app._turnover_ledger_read_model_refresh_producer().enqueue,
            invalidate_workbench_after_category_mutation=app._invalidate_workbench_after_bank_transaction_categories,
            audit_service=app._audit_service,
        )

        side_effect_port.after_mutation(
            transaction_id="txn-001",
            actor_id="TESTFULL001",
            action="bank_detail_category_confirmed",
            affected_months=["2026-03"],
            metadata={},
        )

        self.assertIn(("bank_detail", "2026-03", "bank_detail_category_confirmation_changed"), queue.enqueued)
        self.assertIn(("turnover_ledger", "all", "bank_detail_category_confirmation_changed"), queue.enqueued)
        self.assertNotIn(("turnover_ledger", "2026-03", "bank_detail_category_confirmation_changed"), queue.enqueued)

    def test_bank_detail_api_does_not_reenqueue_already_refreshing_scopes(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        repository = _BankDetailStatusRepository(status="refreshing")
        app._bank_detail_sql_read_repository = repository
        app._bank_account_balance_sql_read_repository = repository
        app._requires_sql_read_model_runtime = lambda: True

        transactions = self._bank_detail_transactions_payload(
            app,
            account_key=None,
            date_from="2026-01-01",
            date_to="2026-12-31",
            keyword="网银证书服务费",
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            page="1",
            page_size="100",
        )
        accounts = self._bank_detail_accounts_payload(
            app,
            date_from="2026-01-01",
            date_to="2026-12-31",
        )

        self.assertEqual(transactions["read_model_status"], "refreshing")
        self.assertEqual(accounts["read_model_status"], "refreshing")
        self.assertEqual(transactions["rows"][0]["id"], "txn-existing-read-model")
        self.assertEqual(accounts["accounts"][0]["account_key"], "icbc:6386")
        self.assertEqual(repository.transaction_reads, 1)
        self.assertEqual(repository.account_reads, 1)
        self.assertEqual(queue.enqueued, [])

    def test_bank_detail_legacy_sql_helpers_are_removed_from_application_boundary(self) -> None:
        class DelegatingService:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def accounts_payload(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("accounts", dict(kwargs)))
                return {"accounts": [{"account_key": "delegated"}], "read_model_status": "fresh"}

            def transactions_payload(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("transactions", dict(kwargs)))
                return {"rows": [{"id": "delegated-txn"}], "read_model_status": "fresh"}

        class PoisonRepository:
            def bank_detail_scope_keys_for_range(self, **_kwargs: object) -> list[str]:
                raise AssertionError("server helper must not access bank detail repository directly")

            def list_bank_detail_transactions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("server helper must not access bank detail repository directly")

            def list_bank_detail_accounts(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("server helper must not access bank detail repository directly")

        app = build_application()
        service = DelegatingService()
        app._bank_details_application_service = lambda: service
        app._bank_detail_sql_read_repository = PoisonRepository()

        self.assertFalse(hasattr(app, "_get_bank_detail_accounts_from_sql_read_model"))
        self.assertFalse(hasattr(app, "_get_bank_detail_transactions_from_sql_read_model"))
        accounts = self._bank_detail_accounts_payload(app, date_from="2026-05-01", date_to="2026-05-31")
        transactions = self._bank_detail_transactions_payload(
            app,
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword="服务费",
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            category_third_label=None,
            page="1",
            page_size="100",
        )

        self.assertEqual(accounts["accounts"][0]["account_key"], "delegated")
        self.assertEqual(transactions["rows"][0]["id"], "delegated-txn")
        self.assertEqual(
            service.calls,
            [
                ("accounts", {"date_from": "2026-05-01", "date_to": "2026-05-31"}),
                (
                    "transactions",
                    {
                        "account_key": None,
                        "date_from": "2026-05-01",
                        "date_to": "2026-05-31",
                        "keyword": "服务费",
                        "category_code": None,
                        "category_primary_label": None,
                        "category_sub_label": None,
                        "category_third_label": None,
                        "page": 1,
                        "page_size": 100,
                    },
                ),
            ],
        )

    def test_bank_detail_api_reenqueues_stale_scopes_once(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        repository = _BankDetailStatusRepository(status="stale")
        app._bank_detail_sql_read_repository = repository
        app._requires_sql_read_model_runtime = lambda: True

        payload = self._bank_detail_transactions_payload(
            app,
            account_key=None,
            date_from="2026-01-01",
            date_to="2026-12-31",
            keyword="网银证书服务费",
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            page="1",
            page_size="100",
        )

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["rows"][0]["id"], "txn-existing-read-model")
        self.assertEqual(repository.transaction_reads, 1)
        self.assertEqual(queue.enqueued, [("bank_detail", "2026-01", "api_stale")])

    def test_bank_detail_api_treats_old_auto_tag_rule_version_as_stale(self) -> None:
        app = build_application()
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)
        repository = _BankDetailStatusRepository(
            status="fresh",
            bank_auto_tag_rules_version=None,
        )
        app._bank_detail_sql_read_repository = repository
        app._requires_sql_read_model_runtime = lambda: True

        payload = self._bank_detail_transactions_payload(
            app,
            account_key=None,
            date_from="2026-01-01",
            date_to="2026-12-31",
            keyword="网银证书服务费",
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            page="1",
            page_size="100",
        )

        self.assertEqual(payload["read_model_status"], "stale")
        self.assertEqual(payload["rows"][0]["id"], "txn-existing-read-model")
        self.assertEqual(repository.transaction_reads, 1)
        self.assertEqual(queue.enqueued, [("bank_detail", "2026-01", "api_stale")])

    def test_bank_detail_freshness_uses_latest_auto_tag_rules_from_shared_store(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            reader_app = build_application(data_dir=data_dir)
            writer_app = build_application(data_dir=data_dir)
            current = writer_app._app_settings_service.get_bank_auto_tag_rules_payload()
            active_rules = []
            for rule in current["active_rules"]:
                if rule["code"] == "fee":
                    rules = {**rule["rules"]}
                    rules["contains_any"] = [*list(rules.get("contains_any") or []), "跨进程版本测试"]
                    rules["contains"] = [*list(rules.get("contains") or []), "跨进程版本测试"]
                    active_rules.append({**rule, "rules": rules})
                else:
                    active_rules.append(rule)
            saved = writer_app._app_settings_service.update_bank_auto_tag_rules(
                {
                    "expected_version": current["version"],
                    "active_rules": active_rules,
                    "archived_rules": current["archived_rules"],
                },
                actor_id="settings-owner",
            )
            self.assertGreater(saved["version"], current["version"])
            queue = _ReadModelQueue()
            reader_app._runtime_repositories = SimpleNamespace(queue_repository=queue)
            repository = _BankDetailStatusRepository(
                status="fresh",
                bank_auto_tag_rules_version=int(saved["version"]),
            )
            reader_app._bank_detail_sql_read_repository = repository
            reader_app._requires_sql_read_model_runtime = lambda: True

            payload = self._bank_detail_transactions_payload(
                reader_app,
                account_key=None,
                date_from="2026-01-01",
                date_to="2026-12-31",
                keyword="网银证书服务费",
                category_code=None,
                category_primary_label=None,
                category_sub_label=None,
                page="1",
                page_size="100",
            )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(repository.transaction_reads, 1)
        self.assertEqual(queue.enqueued, [])

    def test_put_rejects_invalid_payloads_with_structured_errors(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        cases = [
            (
                {
                    "expected_version": current["version"],
                    "system_rule": current["system_rule"],
                    "active_rules": [],
                    "archived_rules": [],
                },
                400,
                "invalid_bank_auto_tag_rules_request",
            ),
            (
                {
                    "expected_version": current["version"],
                    "active_rules": [{**salary, "rules": {"match_fields": ["bad_field"], "exact": [], "contains": [], "excludes": ["x"]}}],
                    "archived_rules": [],
                },
                400,
                "invalid_auto_tag_rule",
            ),
            (
                {
                    "expected_version": current["version"],
                    "active_rules": [{**salary, "output_primary_label": "  "}],
                    "archived_rules": [],
                },
                400,
                "invalid_auto_tag_rule",
            ),
            (
                {
                    "expected_version": current["version"],
                    "active_rules": [
                        {**salary, "output_primary_label": "费用", "output_sub_label": "手续费"},
                        next(rule for rule in current["active_rules"] if rule["code"] == "fee"),
                        *[rule for rule in current["active_rules"] if rule["code"] not in {"salary", "fee"}],
                    ],
                    "archived_rules": [],
                },
                400,
                "invalid_auto_tag_rule",
            ),
            (
                {
                    "expected_version": current["version"],
                    "active_rules": [
                        {
                            "code": "custom_client_supplied",
                            "label": "自定义",
                            "rules": {"match_fields": ["all_text"], "exact": [], "contains": ["自定义"], "excludes": []},
                        }
                    ],
                    "archived_rules": [],
                },
                400,
                "invalid_auto_tag_rule",
            ),
            (
                {
                    "expected_version": current["version"] - 1,
                    "active_rules": [salary],
                    "archived_rules": [],
                },
                409,
                "bank_transaction_tags_version_conflict",
            ),
        ]

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            for request_payload, expected_status, expected_error in cases:
                with self.subTest(expected_error=expected_error):
                    response = self._update_auto_tag_rules_response(app,
                        json.dumps(request_payload, ensure_ascii=False),
                        {},
                    )
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(payload["error"], expected_error)
                    self.assertIn("field_errors", payload)
                    self.assertIn("references", payload)

    def test_put_rejects_ordinary_priority_below_two_or_non_integer(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        cases = [1, 0, -1, "2.5", "abc"]

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            for priority in cases:
                with self.subTest(priority=priority):
                    response = self._update_auto_tag_rules_response(app,
                        json.dumps(
                            {
                                "expected_version": current["version"],
                                "active_rules": [{**salary, "priority": priority}],
                                "archived_rules": current["archived_rules"],
                            },
                            ensure_ascii=False,
                        ),
                        {},
                    )
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(payload["error"], "invalid_auto_tag_rule")
                    self.assertTrue(
                        any(error["path"] == "active_rules[0].priority" for error in payload["field_errors"])
                    )

    def test_put_rejects_archived_rules_without_existing_code(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        fee = next(rule for rule in current["active_rules"] if rule["code"] == "fee")
        archived_fee_without_code = {**fee}
        archived_fee_without_code.pop("code")

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "active_rules": [rule for rule in current["active_rules"] if rule["code"] != "fee"],
                        "archived_rules": [archived_fee_without_code],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_auto_tag_rule")
        self.assertIn(
            {"path": "archived_rules[0].code", "message": "停用规则必须包含已有标签 code。"},
            payload["field_errors"],
        )

    def test_put_allows_deleting_active_rule_when_archived_has_same_label(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            initial_app = build_application(data_dir=data_dir)
            snapshot = dict(initial_app._app_settings_service._snapshot)
            tag_dictionary = dict(snapshot["bank_transaction_tags"])
            existing_definitions = list(tag_dictionary["definitions"])
            snapshot["bank_transaction_tags"] = {
                **tag_dictionary,
                "definitions": [
                    *existing_definitions,
                    {
                        "code": "custom_online_cert_fee_old",
                        "label": "网银证书服务费",
                        "path": ["自动识别", "网银证书服务费"],
                        "source": "custom",
                        "status": "archived",
                        "direction": "any",
                        "account_scope": {"type": "any", "values": []},
                        "rules": {
                            "match_fields": ["all_text"],
                            "exact_any": ["网银证书服务费"],
                            "contains_any": [],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                        "rule_code": "custom_online_cert_fee_old",
                    },
                    {
                        "code": "custom_online_cert_fee_new",
                        "label": "网银证书服务费",
                        "path": ["自动识别", "网银证书服务费"],
                        "source": "custom",
                        "status": "active",
                        "priority": 90,
                        "direction": "any",
                        "account_scope": {"type": "any", "values": []},
                        "rules": {
                            "match_fields": ["all_text"],
                            "exact_any": [],
                            "contains_any": [],
                            "contains_all": ["网银", "服务费"],
                            "none_of": [],
                            "regex_any": [],
                        },
                        "rule_code": "custom_online_cert_fee_new",
                    },
                ],
            }
            ApplicationStateStore(data_dir).save_app_settings(snapshot)
            app = build_application(data_dir=data_dir)

            current = app._app_settings_service.get_bank_auto_tag_rules_payload()
            target = next(rule for rule in current["active_rules"] if rule["code"] == "custom_online_cert_fee_new")

            with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
                response = self._update_auto_tag_rules_response(app,
                    json.dumps(
                        {
                            "expected_version": current["version"],
                            "active_rules": [
                                rule
                                for rule in current["active_rules"]
                                if rule["code"] != "custom_online_cert_fee_new"
                            ],
                            "archived_rules": [*current["archived_rules"], target],
                        },
                        ensure_ascii=False,
                    ),
                    {},
                )

            payload = json.loads(response.body)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                [
                    rule["code"]
                    for rule in payload["archived_rules"]
                    if rule["label"] == "网银证书服务费"
                ],
                ["custom_online_cert_fee_new", "custom_online_cert_fee_old"],
            )

    def test_put_archives_referenced_tag_and_detaches_pending_invoice_rules_atomically(self) -> None:
        app = build_application()
        settings = app._app_settings_service.get_settings_payload()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            pending_invoice_tag_groups={
                "version": settings["pending_invoice_tag_groups"]["version"],
                "groups": {
                    "requires_invoice": {"tag_codes": ["salary"]},
                    "bank_statement_as_invoice": {"tag_codes": []},
                    "no_invoice_required": {"tag_codes": []},
                },
            },
            actor_id="settings-owner",
        )
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        settings_before_archive = app._app_settings_service.get_settings_payload()
        pending_version_before_archive = settings_before_archive["pending_invoice_tag_groups"]["version"]
        bank_version_before_archive = settings_before_archive["bank_transaction_tags"]["version"]
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = self._update_auto_tag_rules_response(app,
                json.dumps(
                    {
                        "expected_version": current["version"],
                        "active_rules": [rule for rule in current["active_rules"] if rule["code"] != "salary"],
                        "archived_rules": [{**salary, "rules": salary["rules"]}],
                    },
                    ensure_ascii=False,
                ),
                {},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        archived_salary = next(rule for rule in payload["archived_rules"] if rule["code"] == "salary")
        self.assertEqual(archived_salary["status"], "archived")
        updated_settings = app._app_settings_service.get_settings_payload()
        pending_groups = updated_settings["pending_invoice_tag_groups"]["groups"]
        self.assertEqual(pending_groups["requires_invoice"]["tag_codes"], [])
        self.assertEqual(
            updated_settings["pending_invoice_tag_groups"]["version"],
            pending_version_before_archive + 1,
        )
        self.assertEqual(updated_settings["bank_transaction_tags"]["version"], bank_version_before_archive + 1)
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["action"], "bank_auto_tag_rules_updated")
        self.assertEqual(
            audit["metadata"]["detached_pending_invoice_tag_references"],
            [{"group_id": "requires_invoice", "label": "需要开票", "tag_code": "salary"}],
        )

    def test_put_requires_save_permission(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(can_mutate_data=False), None)):
            response = self._update_auto_tag_rules_response(app, "{}", {})

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
