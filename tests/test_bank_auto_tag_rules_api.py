from __future__ import annotations

import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application


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


class BankAutoTagRulesApiTests(unittest.TestCase):
    def test_get_returns_system_active_archived_fields_and_permissions(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app._handle_api_bank_details_auto_tag_rules({})

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["system_rule"]["code"], "internal_transfer")
        self.assertEqual(payload["system_rule"]["priority_label"], "优先级 0")
        self.assertFalse(payload["system_rule"]["editable"])
        self.assertIn("salary", [rule["code"] for rule in payload["active_rules"]])
        self.assertEqual(payload["active_rules"][0]["priority_label"], "优先级 1")
        self.assertEqual(payload["field_options"][0]["value"], "counterparty_name")
        self.assertEqual(payload["permissions"], {"can_save": True})

    def test_put_renames_reorders_adds_archives_audits_and_triggers_lifecycle(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")
        fee = next(rule for rule in current["active_rules"] if rule["code"] == "fee")
        active = [
            {**salary, "label": "人员薪酬", "rules": {**salary["rules"], "contains": ["工资", "薪酬"]}},
            {**fee, "rules": fee["rules"]},
            *[rule for rule in current["active_rules"] if rule["code"] not in {"salary", "fee", "bonus"}],
            {
                "label": "银行利息",
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
                response = app._handle_api_bank_details_auto_tag_rules_update(
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
        self.assertEqual(payload["active_rules"][0]["code"], "salary")
        self.assertEqual(payload["active_rules"][0]["label"], "人员薪酬")
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
        self.assertTrue(metadata["priority_changes"])
        self.assertTrue(metadata["rule_changes"])

    def test_put_updates_auto_category_engine_rule_source(self) -> None:
        app = build_application()
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        active = [
            *current["active_rules"],
            {
                "label": "网银证书服务费",
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
            response = app._handle_api_bank_details_auto_tag_rules_update(
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
        custom_rule = next(rule for rule in payload["active_rules"] if rule["label"] == "网银证书服务费")
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
                "label": "网银证书服务费",
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
            response = app._handle_api_bank_details_auto_tag_rules_update(
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

        self.assertEqual(response.status_code, 200)
        self.assertIn(("bank_detail", "2026-01", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertIn(("bank_detail", "2026-03", "bank_auto_tag_rules_changed"), queue.enqueued)
        self.assertNotIn(("bank_detail", "all", "bank_auto_tag_rules_changed"), queue.enqueued)

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
                    "active_rules": [{**salary, "label": "  "}],
                    "archived_rules": [],
                },
                400,
                "invalid_auto_tag_rule",
            ),
            (
                {
                    "expected_version": current["version"],
                    "active_rules": [
                        salary,
                        {**next(rule for rule in current["active_rules"] if rule["code"] == "fee"), "label": salary["label"]},
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
                    response = app._handle_api_bank_details_auto_tag_rules_update(
                        json.dumps(request_payload, ensure_ascii=False),
                        {},
                    )
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, expected_status)
                    self.assertEqual(payload["error"], expected_error)
                    self.assertIn("field_errors", payload)
                    self.assertIn("references", payload)

    def test_put_rejects_archiving_pending_invoice_referenced_tag(self) -> None:
        app = build_application()
        settings = app._app_settings_service.get_settings_payload()
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            bank_transaction_tags=settings["bank_transaction_tags"],
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
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(), None)):
            response = app._handle_api_bank_details_auto_tag_rules_update(
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
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "bank_transaction_tag_in_use_by_pending_invoice_filter")
        self.assertEqual(payload["references"][0]["tag_code"], "salary")
        self.assertIn("待找发票规则：需要开票", payload["references"][0]["label"])

    def test_put_requires_save_permission(self) -> None:
        app = build_application()

        with patch.object(app, "_resolve_bank_details_read_session", return_value=(_session(can_mutate_data=False), None)):
            response = app._handle_api_bank_details_auto_tag_rules_update("{}", {})

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")


if __name__ == "__main__":
    unittest.main()
