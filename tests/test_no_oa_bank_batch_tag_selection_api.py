import json
from pathlib import Path
import shutil
import tempfile
import unittest
from types import SimpleNamespace

from tests.app_test_support import build_local_state_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


def _json(response):
    return json.loads(response.body)


def build_application(**kwargs):
    app = build_local_state_application(**kwargs)
    service = app._bank_flow_rule_batch_service
    app._bank_flow_rule_batch_canonical_query_repository = SimpleNamespace(
        read_page=lambda *_args, **_kwargs: {},
        read_batch=lambda batch_id: service.get_batch(batch_id),
        read_submitted_batches=lambda: service.list_batches({"bucket": "submitted"}),
    )
    return app


class _ReadModelQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class NoOaBankBatchTagSelectionApiTests(unittest.TestCase):
    def _set_bank_flow_rule_requirements(
        self,
        app,
        *,
        tag_code: str,
        requires_oa: bool,
        requires_invoice: bool,
    ) -> dict[str, object]:
        current = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))
        rules = [
            {
                **rule,
                "requires_oa": requires_oa,
                "requires_invoice": requires_invoice,
            }
            if rule["tag_code"] == tag_code
            else rule
            for rule in current["rules"]
        ]
        response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current["version"], "rules": rules}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 200)
        return _json(response)

    def test_bank_flow_rule_tag_rules_hide_and_reject_selected_tag_codes(self) -> None:
        app = build_application()
        payload = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))

        self.assertIn("active_tags", payload)
        self.assertIn("rules", payload)
        self.assertNotIn("selected_tag_codes", payload)
        self.assertNotIn("inactive_selected_tag_codes", payload)

        response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({
                "expected_version": payload["version"],
                "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}],
                "selected_tag_codes": ["fee"],
            }),
            headers={"Content-Type": "application/json"},
        )
        error = _json(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(error["error"], "bank_flow_rule_batch_selected_tag_codes_forbidden")

    def test_tag_selection_active_tags_are_bank_auto_rule_tags_only(self) -> None:
        app = build_application()
        auto_rules = app._app_settings_service.get_bank_auto_tag_rules_payload()
        selection = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))

        expected_codes = [
            auto_rules["system_rule"]["code"],
            *[rule["code"] for rule in auto_rules["active_rules"]],
        ]

        self.assertEqual(selection["bank_auto_tag_rules_version"], auto_rules["version"])
        self.assertEqual([tag["code"] for tag in selection["active_tags"]], expected_codes)

    def test_no_oa_tag_selection_save_does_not_scan_or_rewrite_turnover_relations(self) -> None:
        app = build_application()

        class RelationCommandMustNotBeRead:
            def __init__(self) -> None:
                self.list_calls = 0
                self.update_calls = 0

            def list_active_relations(self) -> list[dict[str, object]]:
                self.list_calls += 1
                raise AssertionError("no-OA tag selection must not scan Workbench relations")

            def update_relation_metadata_for_case_id(self, **_kwargs: object) -> dict[str, object]:
                self.update_calls += 1
                raise AssertionError("no-OA tag selection must not rewrite Workbench relations")

        relation_command = RelationCommandMustNotBeRead()
        app._workbench_relation_command_service = lambda **_kwargs: relation_command  # type: ignore[method-assign]
        current = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))

        response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps(
                {
                    "expected_version": current["version"],
                    "rules": [
                        {"tag_code": "fee", "requires_oa": False, "requires_invoice": False}
                    ],
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(relation_command.list_calls, 0)
        self.assertEqual(relation_command.update_calls, 0)

    def test_tag_selection_reflects_bank_auto_rule_label_changes_immediately(self) -> None:
        app = build_application()
        current_rules = app._app_settings_service.get_bank_auto_tag_rules_payload()
        next_active_rules = []
        for rule in current_rules["active_rules"]:
            if rule["code"] == "fee":
                next_active_rules.append({
                    **rule,
                    "label": "银行手续费规则",
                    "output_primary_label": "银行费用",
                    "output_sub_label": "手续费自动规则",
                    "direction": "expense",
                })
            else:
                next_active_rules.append(rule)

        saved_rules = app._app_settings_service.update_bank_auto_tag_rules(
            {
                "expected_version": current_rules["version"],
                "active_rules": next_active_rules,
                "archived_rules": current_rules["archived_rules"],
            },
            actor_id="settings-owner",
        )
        updated_selection = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))
        saved_fee_rule = next(rule for rule in saved_rules["active_rules"] if rule["code"] == "fee")
        fee_tag = next(tag for tag in updated_selection["active_tags"] if tag["code"] == "fee")

        self.assertEqual(updated_selection["bank_auto_tag_rules_version"], saved_rules["version"])
        self.assertEqual(fee_tag["label"], saved_fee_rule["label"])
        self.assertEqual(fee_tag["output_primary_label"], saved_fee_rule["output_primary_label"])
        self.assertEqual(fee_tag["output_sub_label"], saved_fee_rule["output_sub_label"])
        self.assertEqual(fee_tag["direction"], "expense")

    def test_tag_selection_starts_empty_and_no_oa_list_reads_canonical_batches_directly(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fee.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        queue = _ReadModelQueue()
        app._runtime_repositories = SimpleNamespace(queue_repository=queue)

        selection_response = app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection")
        selection_payload = _json(selection_response)
        empty_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(selection_response.status_code, 200)
        self.assertEqual(selection_payload["bank_auto_tag_rules_version"], 1)
        self.assertEqual(selection_payload["selected_tag_codes"], [])
        self.assertIn("fee", [tag["code"] for tag in selection_payload["active_tags"]])
        initial_fee_rule = next(rule for rule in selection_payload["rules"] if rule["tag_code"] == "fee")
        self.assertTrue(initial_fee_rule["requires_oa"])
        self.assertTrue(initial_fee_rule["requires_invoice"])
        self.assertEqual(empty_batches["batches"], [])
        self.assertNotIn("read_model_status", empty_batches)
        self.assertNotIn("refresh_enqueued", empty_batches)

        save_response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({
                "expected_version": selection_payload["version"],
                "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": True}],
            }),
            headers={"Content-Type": "application/json"},
        )
        app._no_oa_bank_batch_application_service().refresh_batches()
        still_blocked_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(_json(save_response)["selected_tag_codes"], [])
        self.assertEqual(still_blocked_batches["batches"], [])
        self.assertNotIn("read_model_status", still_blocked_batches)
        self.assertNotIn("refresh_enqueued", still_blocked_batches)

        next_selection = _json(save_response)
        save_response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({
                "expected_version": next_selection["version"],
                "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}],
            }),
            headers={"Content-Type": "application/json"},
        )
        app._no_oa_bank_batch_application_service().refresh_batches()
        enabled_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(_json(save_response)["selected_tag_codes"], ["fee"])
        self.assertEqual(
            _json(save_response)["requirements_by_tag_code"]["fee"],
            {"requires_oa": False, "requires_invoice": False},
        )
        self.assertEqual(len(enabled_batches["batches"]), 1)
        self.assertEqual(enabled_batches["batches"][0]["batch_type"], "fee")
        self.assertNotIn("read_model_status", enabled_batches)
        self.assertNotIn("refresh_enqueued", enabled_batches)
        self.assertNotIn(("no_oa_bank_batch", "all", "no_oa_bank_batch_tag_selection_changed"), queue.enqueued)
        self.assertEqual(queue.enqueued, [])

    def test_new_auto_tag_rule_is_available_but_not_selected_by_default(self) -> None:
        app = build_application()
        initial_selection = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))
        current_rules = app._app_settings_service.get_bank_auto_tag_rules_payload()
        fee_rule = next(rule for rule in current_rules["active_rules"] if rule["code"] == "fee")
        new_rule = {
            **fee_rule,
            "code": "",
            "label": "短信平台费",
            "output_primary_label": "平台费用",
            "output_sub_label": "短信平台费",
            "rules": {
                **fee_rule["rules"],
                "contains_any": ["短信平台费"],
                "contains": ["短信平台费"],
            },
        }

        saved_rules = app._app_settings_service.update_bank_auto_tag_rules(
            {
                "expected_version": current_rules["version"],
                "active_rules": [*current_rules["active_rules"], new_rule],
                "archived_rules": current_rules["archived_rules"],
            },
            actor_id="settings-owner",
        )
        updated_selection = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))
        new_tag_codes = [
            tag["code"]
            for tag in updated_selection["active_tags"]
            if tag["output_primary_label"] == "平台费用" and tag["output_sub_label"] == "短信平台费"
        ]

        self.assertEqual(updated_selection["bank_auto_tag_rules_version"], saved_rules["version"])
        self.assertEqual(updated_selection["selected_tag_codes"], initial_selection["selected_tag_codes"])
        self.assertEqual(len(new_tag_codes), 1)
        self.assertNotIn(new_tag_codes[0], updated_selection["selected_tag_codes"])
        new_tag_rule = next(rule for rule in updated_selection["rules"] if rule["tag_code"] == new_tag_codes[0])
        self.assertTrue(new_tag_rule["requires_oa"])
        self.assertTrue(new_tag_rule["requires_invoice"])

    def test_archived_selected_tag_is_removed_by_auto_tag_rule_update(self) -> None:
        app = build_application()
        selection = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))
        save_response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": selection["version"], "selected_tag_codes": ["salary"]}),
            headers={"Content-Type": "application/json"},
        )
        saved_selection = _json(save_response)
        current = app._app_settings_service.get_bank_auto_tag_rules_payload()
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        app._app_settings_service.update_bank_auto_tag_rules(
            {
                "expected_version": current["version"],
                "active_rules": [rule for rule in current["active_rules"] if rule["code"] != "salary"],
                "archived_rules": [{**salary, "rules": salary["rules"]}],
            },
            actor_id="settings-owner",
        )
        updated = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))

        self.assertEqual(updated["selected_tag_codes"], [])
        self.assertEqual(updated["version"], saved_selection["version"] + 1)
        self.assertEqual(updated["bank_auto_tag_rules_version"], current["version"] + 1)
        self.assertNotIn("salary", [tag["code"] for tag in updated["active_tags"]])
        self.assertEqual(updated["inactive_selected_tag_codes"], [])
        self.assertNotIn("salary", updated["requirements_by_tag_code"])
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(
            audit["metadata"]["detached_no_oa_bank_batch_tag_references"],
            [{"tag_code": "salary"}],
        )

    def test_selected_row_submit_creates_one_batch_for_same_bank_subset(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-04",
                    "trade_time": "2026-05-04 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "18.20",
                    "credit_amount": "",
                    "summary": "账户管理手续费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"} for row_id in row_ids],
            actor="tester",
        )
        version = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_ids[0]], "note": "提交单条手续费"}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["batch"]["status"], "submitted")
        self.assertEqual(payload["batch"]["batch_type"], "fee")
        self.assertEqual(payload["batch"]["row_ids"], [row_ids[0]])
        self.assertEqual(payload["batch"]["row_count"], 1)
        self.assertEqual(payload["batch"]["total_amount"], "8.80")
        self.assertEqual(payload["results"], [{"batch_id": payload["batch"]["batch_id"], "status": "submitted"}])

        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(relation["row_ids"], [row_ids[0]])
        self.assertEqual(
            relation["special_metadata"]["paired_requirement_tag_code"],
            "fee",
        )
        self.assertFalse(relation["special_metadata"]["paired_requires_oa"])
        self.assertFalse(relation["special_metadata"]["paired_requires_invoice"])

    def test_bank_flow_rule_submit_selection_uses_new_relation_mode_and_rule_metadata(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-bank-flow.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        self._set_bank_flow_rule_requirements(
            app,
            tag_code="fee",
            requires_oa=False,
            requires_invoice=False,
        )

        response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id], "note": "提交流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["batch"]["status"], "submitted")
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_mode"], "bank_flow_rule_batch")
        metadata = relation["special_metadata"]
        self.assertEqual(metadata["source"], "bank_flow_rule_batch")
        self.assertEqual(metadata["flow_rule_tag_code"], "fee")
        self.assertFalse(metadata["requires_oa"])
        self.assertFalse(metadata["requires_invoice"])
        self.assertEqual(metadata["source_row_count"], 1)
        self.assertFalse(metadata["collapsed_bank_rows"])
        self.assertNotIn("operation_barrier_targets", payload)
        self.assertNotIn("read_model_scope_keys", payload)

    def test_bank_flow_rule_tag_rule_update_preserves_submitted_relation_history(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-bank-flow-resync.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        self._set_bank_flow_rule_requirements(
            app,
            tag_code="fee",
            requires_oa=False,
            requires_invoice=False,
        )
        submit_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id], "note": "提交流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(submit_response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
        self.assertIsNotNone(relation)
        self.assertEqual(relation["relation_mode"], "bank_flow_rule_batch")
        self.assertFalse(relation["special_metadata"]["requires_oa"])
        self.assertFalse(relation["special_metadata"]["requires_invoice"])

        current_rules = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))
        next_rules = [
            {
                **rule,
                "requires_oa": True,
                "requires_invoice": False,
            }
            if rule["tag_code"] == "fee"
            else rule
            for rule in current_rules["rules"]
        ]
        save_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current_rules["version"], "rules": next_rules}),
            headers={"Content-Type": "application/json"},
        )
        saved_rules = _json(save_response)

        self.assertEqual(save_response.status_code, 200)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
        self.assertIsNotNone(relation)
        metadata = relation["special_metadata"]
        self.assertEqual(metadata["flow_rule_tag_code"], "fee")
        self.assertFalse(metadata["requires_oa"])
        self.assertFalse(metadata["requires_invoice"])
        self.assertNotEqual(metadata["flow_rule_version"], saved_rules["version"])

    def test_bank_flow_rule_tag_rule_update_does_not_rewrite_persistent_relation(self) -> None:
        data_dir = Path(tempfile.mkdtemp(prefix="finops-test-bank-flow-rules-"))
        self.addCleanup(shutil.rmtree, data_dir, ignore_errors=True)
        app = build_application(data_dir=data_dir)
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-bank-flow-persistent-resync.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        self._set_bank_flow_rule_requirements(
            app,
            tag_code="fee",
            requires_oa=False,
            requires_invoice=False,
        )
        submit_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id], "note": "提交流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        batch_id = _json(submit_response)["batch"]["batch_id"]
        app._workbench_pair_relation_service = WorkbenchPairRelationService()

        current_rules = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))
        next_rules = [
            {**rule, "requires_oa": True, "requires_invoice": False}
            if rule["tag_code"] == "fee"
            else rule
            for rule in current_rules["rules"]
        ]
        save_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current_rules["version"], "rules": next_rules}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(save_response.status_code, 200)

        relation_snapshot = app._state_store.load_workbench_pair_relations()["pair_relations"][batch_id]
        metadata = relation_snapshot["special_metadata"]
        self.assertEqual(relation_snapshot["relation_mode"], "bank_flow_rule_batch")
        self.assertFalse(metadata["requires_oa"])
        self.assertFalse(metadata["requires_invoice"])

    def test_tag_rule_update_does_not_upgrade_turnover_relation(self) -> None:
        data_dir = Path(tempfile.mkdtemp(prefix="finops-test-turnover-rules-"))
        self.addCleanup(shutil.rmtree, data_dir, ignore_errors=True)
        app = build_application(data_dir=data_dir)
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="turnover-bank-rule-sync.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-10",
                    "trade_time": "2026-05-10 10:20:00",
                    "counterparty_name": "杨丽萍",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "暂借款",
                },
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-22",
                    "trade_time": "2026-05-22 14:40:00",
                    "counterparty_name": "杨丽萍",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "还借款",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {"transaction_id": row_ids[0], "category_code": "borrow_in_company_pending_repayment"},
                {"transaction_id": row_ids[1], "category_code": "borrow_in_company_repaid"},
            ],
            actor="tester",
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="turnover:turnover_rel_legacy",
            row_ids=[*row_ids, "oa-pay-turnover"],
            row_types=["bank", "bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="legacy-script",
            month_scope="all",
            note="旧往来款闭环关系",
        )
        app._state_store.save_workbench_pair_relations(app._workbench_pair_relation_service.snapshot())
        before_relation_snapshot = app._state_store.load_workbench_pair_relations()["pair_relations"][
            "turnover:turnover_rel_legacy"
        ]
        app._workbench_pair_relation_service = WorkbenchPairRelationService()

        current_rules = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))
        next_rules = [
            {**rule, "requires_oa": True, "requires_invoice": False}
            if rule["tag_code"] == "external_turnover"
            else rule
            for rule in current_rules["rules"]
        ]
        save_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current_rules["version"], "rules": next_rules}),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(save_response.status_code, 200)
        relation_snapshot = app._state_store.load_workbench_pair_relations()["pair_relations"]["turnover:turnover_rel_legacy"]
        self.assertEqual(relation_snapshot, before_relation_snapshot)

    def test_bank_flow_rule_update_does_not_pollute_manual_relation(self) -> None:
        data_dir = Path(tempfile.mkdtemp(prefix="finops-test-manual-bank-policy-"))
        self.addCleanup(shutil.rmtree, data_dir, ignore_errors=True)
        app = build_application(data_dir=data_dir)
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="manual-turnover-bank-policy.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-10",
                    "trade_time": "2026-05-10 10:20:00",
                    "counterparty_name": "贾小花",
                    "debit_amount": "",
                    "credit_amount": "100000.00",
                    "summary": "暂借款",
                },
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-22",
                    "trade_time": "2026-05-22 14:40:00",
                    "counterparty_name": "贾小花",
                    "debit_amount": "200000.00",
                    "credit_amount": "",
                    "summary": "还借款",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {"transaction_id": row_ids[0], "category_code": "borrow_in_company_pending_repayment"},
                {"transaction_id": row_ids[1], "category_code": "borrow_in_company_repaid"},
            ],
            actor="tester",
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="CASE-MANUAL-TURNOVER-POLICY",
            row_ids=[*row_ids, "oa-pay-turnover"],
            row_types=["bank", "bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="finance-user",
            month_scope="all",
            note="普通关联台手工关系",
        )
        app._state_store.save_workbench_pair_relations(app._workbench_pair_relation_service.snapshot())
        before_relation_snapshot = app._state_store.load_workbench_pair_relations()["pair_relations"][
            "CASE-MANUAL-TURNOVER-POLICY"
        ]
        app._workbench_pair_relation_service = WorkbenchPairRelationService()

        current_rules = _json(app.handle_request("GET", "/api/bank-flow-rule-batches/tag-rules"))
        next_rules = [
            {**rule, "requires_oa": True, "requires_invoice": False}
            if rule["tag_code"] == "external_turnover"
            else rule
            for rule in current_rules["rules"]
        ]
        save_response = app.handle_request(
            "PUT",
            "/api/bank-flow-rule-batches/tag-rules",
            body=json.dumps({"expected_version": current_rules["version"], "rules": next_rules}),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(save_response.status_code, 200)
        relation_snapshot = app._state_store.load_workbench_pair_relations()["pair_relations"][
            "CASE-MANUAL-TURNOVER-POLICY"
        ]
        self.assertEqual(relation_snapshot, before_relation_snapshot)

    def test_bank_flow_rule_reset_submitted_withdraws_all_submitted_batches(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-bank-flow-reset.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        self._set_bank_flow_rule_requirements(
            app,
            tag_code="fee",
            requires_oa=False,
            requires_invoice=False,
        )
        submit_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id], "note": "提交流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        batch_id = _json(submit_response)["batch"]["batch_id"]
        self.assertIsNotNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(row_id))

        reset_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/reset-submitted",
            body=json.dumps({"reason": "全部重新过流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        reset = _json(reset_response)

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(reset["summary"]["reset_count"], 1)
        self.assertEqual(reset["summary"]["row_count"], 1)
        self.assertEqual(reset["results"], [{"batch_id": batch_id, "status": "withdrawn"}])
        self.assertNotIn("operation_barrier_targets", reset)
        self.assertNotIn("read_model_scope_keys", reset)
        self.assertEqual(app._bank_flow_rule_batch_service.get_batch(batch_id)["status"], "withdrawn")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(row_id))

        app._bank_flow_rule_batch_application_service().refresh_batches(
            scope_key="2026-05",
            relation_mode="bank_flow_rule_batch",
        )
        unsubmitted = app._bank_flow_rule_batch_service.list_batches(
            {"relation_mode": "bank_flow_rule_batch", "status": "draft"}
        )
        self.assertEqual([batch["batch_type"] for batch in unsubmitted], ["fee"])

    def test_bank_flow_rule_reset_submitted_tolerates_missing_active_relation(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-bank-flow-reset-missing-relation.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        self._set_bank_flow_rule_requirements(
            app,
            tag_code="fee",
            requires_oa=False,
            requires_invoice=False,
        )
        submit_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id], "note": "提交流水规则"}),
            headers={"Content-Type": "application/json"},
        )
        batch_id = _json(submit_response)["batch"]["batch_id"]
        app._workbench_pair_relation_service.cancel_relation(batch_id)

        reset_response = app.handle_request(
            "POST",
            "/api/bank-flow-rule-batches/reset-submitted",
            body=json.dumps({"reason": "全部重新过流水规则"}),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(reset_response.status_code, 200)
        self.assertEqual(_json(reset_response)["results"], [{"batch_id": batch_id, "status": "withdrawn"}])
        self.assertEqual(app._bank_flow_rule_batch_service.get_batch(batch_id)["status"], "withdrawn")
        app._bank_flow_rule_batch_application_service().refresh_batches(
            scope_key="2026-05",
            relation_mode="bank_flow_rule_batch",
        )
        unsubmitted = app._bank_flow_rule_batch_service.list_batches(
            {"relation_mode": "bank_flow_rule_batch", "status": "draft"}
        )
        self.assertEqual([batch["batch_type"] for batch in unsubmitted], ["fee"])

    def test_selected_row_submit_rejects_cross_bank_selection(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fees-cross-bank.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "8.80",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
                {
                    "account_no": "95599001",
                    "account_name": "云南溯源科技有限公司工商银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:30:00",
                    "counterparty_name": "工商银行",
                    "debit_amount": "9.90",
                    "credit_amount": "",
                    "summary": "网银手续费",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"} for row_id in row_ids],
            actor="tester",
        )
        version = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit-selection",
            body=json.dumps({"transaction_ids": row_ids}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "no_oa_bank_batch_selection_cross_bank")

    def test_selected_row_submit_rejects_single_sided_internal_transfer_selection(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer-single-side.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-05-03",
                    "trade_time": "2026-05-03 10:20:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "1000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "internal_transfer"}],
            actor="tester",
        )
        version = _json(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection"))["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["internal_transfer"]}),
            headers={"Content-Type": "application/json"},
        )

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit-selection",
            body=json.dumps({"transaction_ids": [row_id]}),
            headers={"Content-Type": "application/json"},
        )
        payload = _json(response)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "no_oa_bank_batch_selection_internal_transfer_requires_pair")


if __name__ == "__main__":
    unittest.main()
