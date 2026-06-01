import json
import unittest
from types import SimpleNamespace

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType


def _json(response):
    return json.loads(response.body)


class _ReadModelQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))


class NoOaBankBatchTagSelectionApiTests(unittest.TestCase):
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

    def test_tag_selection_starts_empty_and_controls_unsubmitted_candidates(self) -> None:
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
        self.assertEqual(empty_batches["batches"], [])

        save_response = app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": selection_payload["version"], "selected_tag_codes": ["fee"]}),
            headers={"Content-Type": "application/json"},
        )
        enabled_batches = _json(app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted"))

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(_json(save_response)["selected_tag_codes"], ["fee"])
        self.assertEqual([batch["batch_type"] for batch in enabled_batches["batches"]], ["fee"])
        self.assertIn(("no_oa_bank_batch", "all", "no_oa_bank_batch_tag_selection_changed"), queue.enqueued)

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
