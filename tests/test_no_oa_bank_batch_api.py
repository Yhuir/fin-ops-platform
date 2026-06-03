from __future__ import annotations

import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.no_oa_managed_rule_policy import NO_OA_MANAGED_BATCH_TYPE_ORDER


AUTO_CATEGORY_TEXT_BY_CODE = {
    "fee": "手续费",
    "salary": "工资",
    "holiday_bonus": "过节费",
    "bonus": "奖金",
    "tax_payment": "电子缴税",
    "treasury_tax_collection": "代理国库税收收缴",
    "social_security": "社保费",
}


class FakeNoOaRelationFacade:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self._relations = list(relations)
        self.last_source_versions = {"schema_version": 52}

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        normalized = {str(row_id) for row_id in row_ids}
        rows = [
            self._row_payload(row_id, relation)
            for relation in self._relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id) in normalized
        ]
        return {"status": "fresh", "rows": rows, "groups": self._groups(), "source_versions": self.last_source_versions}

    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        groups = [
            group
            for group in self._groups()
            if str(group.get("scope_month") or group.get("scope_key") or "").startswith(month)
        ]
        return {"status": "fresh", "rows": [], "groups": groups, "source_versions": self.last_source_versions}

    def _groups(self) -> list[dict[str, object]]:
        groups: list[dict[str, object]] = []
        for relation in self._relations:
            case_id = str(relation.get("case_id") or "")
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            groups.append(
                {
                    "group_id": case_id,
                    "scope_month": str(relation.get("month_scope") or "2026-03"),
                    "scope_key": str(relation.get("month_scope") or "2026-03")[:7],
                    "bank_transaction_ids": row_ids,
                    "payload": {
                        "group_id": case_id,
                        "relation_mode": str(relation.get("relation_mode") or "no_oa_bank_batch"),
                        "row_ids": row_ids,
                        "row_types": row_types,
                        "special_metadata": dict(metadata),
                        "amount_check": dict(relation.get("amount_check") or {}) if isinstance(relation.get("amount_check"), dict) else {},
                    },
                }
            )
        return groups

    @staticmethod
    def _row_payload(row_id: object, relation: dict[str, object]) -> dict[str, object]:
        case_id = str(relation.get("case_id") or "")
        return {
            "row_id": str(row_id),
            "row_type": "bank_transaction",
            "relation_status": "linked",
            "group_ids": [case_id],
            "linked_oa": [],
            "linked_bank_transactions": [{"id": str(item), "relation_case_id": case_id} for item in list(relation.get("row_ids") or [])],
            "linked_input_invoices": [],
            "linked_output_invoices": [],
        }


def bank_transaction(
    transaction_id: str,
    *,
    category_code: str = "fee",
    direction: TransactionDirection = TransactionDirection.OUTFLOW,
    amount: str = "12.34",
    account_no: str = "6222000000008106",
    bank_name: str = "建行",
    account_last4: str = "8106",
    trade_time: str = "2026-03-10T09:00:00",
) -> BankTransaction:
    signed_amount = Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount)
    text = AUTO_CATEGORY_TEXT_BY_CODE.get(category_code, category_code)
    return BankTransaction(
        id=transaction_id,
        account_no=account_no,
        txn_direction=direction,
        counterparty_name_raw="云南三源",
        amount=Decimal(amount),
        signed_amount=signed_amount,
        txn_date=trade_time[:10],
        trade_time=trade_time,
        pay_receive_time=trade_time,
        imported_bank_name=bank_name,
        imported_bank_last4=account_last4,
        summary=text,
        remark=text,
    )


class NoOaBankBatchApiTests(unittest.TestCase):
    def _app_with_transactions(
        self,
        transactions: list[BankTransaction],
        categories: dict[str, str] | None = None,
        selected_tag_codes: list[str] | None = None,
    ):
        app = build_application()
        app._import_service = ImportNormalizationService(existing_transactions=transactions)
        updates = [
            {"transaction_id": transaction.id, "category_code": (categories or {}).get(transaction.id, "fee")}
            for transaction in transactions
        ]
        if updates:
            app._bank_transaction_category_service.apply_updates(updates, actor="tester")
        selected_codes = (
            selected_tag_codes
            if selected_tag_codes is not None
            else sorted({str(update["category_code"]) for update in updates if str(update["category_code"])})
        )
        selection = app._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        app._app_settings_service.update_no_oa_bank_batch_tag_selection(
            {
                "expected_version": selection["version"],
                "selected_tag_codes": selected_codes,
            },
            actor_id="tester",
        )
        return app

    def _replace_transaction_text(self, app, transaction_id: str, text: str) -> None:
        transaction = app._import_service.get_transaction(transaction_id)
        transaction.summary = text
        transaction.remark = text
        transaction.bank_text_fields = []

    def _list_batches(self, app, query: str = ""):
        response = app.handle_request("GET", f"/api/no-oa-bank-batches{query}")
        self.assertEqual(response.status_code, 200, response.body)
        return json.loads(response.body)

    def test_list_returns_summary_and_batches(self) -> None:
        app = self._app_with_transactions(
            [
                bank_transaction("bank-202603-fee-1", amount="3.00"),
                bank_transaction("bank-202603-fee-2", amount="2.50"),
            ]
        )

        payload = self._list_batches(app)

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["draft"], 1)
        self.assertEqual(payload["batches"][0]["row_count"], 2)
        self.assertEqual(payload["batches"][0]["total_amount"], "5.50")
        self.assertEqual(payload["batches"][0]["status_bucket"], "unsubmitted")
        self.assertEqual(payload["batches"][0]["tag_counts"], {"fee": 2})
        self.assertEqual(payload["batches"][0]["direction_counts"], {"income": 0, "expense": 2})
        self.assertTrue(payload["batches"][0]["can_submit"])
        self.assertFalse(payload["batches"][0]["can_withdraw"])
        self.assertEqual(payload["batches"][0]["blocked_reason"], "")

    def test_list_uses_fact_repository_when_runtime_starts_without_transaction_snapshot(self) -> None:
        class FactRepository:
            def list_bank_transactions_page(self, *, page: int, page_size: int, **_filters):
                rows = [bank_transaction("bank-202603-fee-1", amount="3.00")]
                return (rows, len(rows)) if page == 1 else ([], len(rows))

        class CategoryProvider:
            def bulk_get_for_rows(self, rows):
                return {
                    str(row.get("id")): {
                        "transaction_id": str(row.get("id")),
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_source": "manual",
                    }
                    for row in rows
                }

        app = build_application()
        app._import_service = ImportNormalizationService(fact_repository=FactRepository())
        app._bank_transaction_effective_category_provider = CategoryProvider()
        selection = app._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        app._app_settings_service.update_no_oa_bank_batch_tag_selection(
            {"expected_version": selection["version"], "selected_tag_codes": ["fee"]},
            actor_id="tester",
        )

        payload = self._list_batches(app)

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["batches"][0]["row_ids"], ["bank-202603-fee-1"])
        self.assertEqual(payload["batches"][0]["total_amount"], "3.00")

    def test_list_summary_always_returns_managed_no_oa_categories(self) -> None:
        app = self._app_with_transactions(
            [
                bank_transaction("bank-202603-fee-1", amount="3.00"),
                bank_transaction(
                    "bank-202604-salary-1",
                    category_code="salary",
                    amount="1000.00",
                    trade_time="2026-04-10T09:00:00",
                ),
            ],
            categories={"bank-202603-fee-1": "fee", "bank-202604-salary-1": "salary"},
            selected_tag_codes=list(NO_OA_MANAGED_BATCH_TYPE_ORDER),
        )

        payload = self._list_batches(app)

        categories = payload["summary"]["categories"]
        self.assertEqual(
            [category["code"] for category in categories],
            [
                "fee",
                "salary",
                "holiday_bonus",
                "bonus",
                "tax_payment",
                "treasury_tax_collection",
                "social_security",
                "internal_transfer",
            ],
        )
        self.assertEqual(
            [category["label"] for category in categories],
            ["手续费", "工资", "过节费", "奖金", "税款", "代理国库税收收缴", "社保款", "内部往来款"],
        )
        by_code = {category["code"]: category for category in categories}
        self.assertEqual(by_code["fee"]["total"], 1)
        self.assertEqual(by_code["salary"]["total"], 1)
        self.assertEqual(by_code["bonus"]["total"], 0)
        self.assertEqual(by_code["bonus"]["draft"], 0)
        self.assertEqual(by_code["tax_payment"]["total_amount"], "0.00")
        self.assertEqual(by_code["treasury_tax_collection"]["total_amount"], "0.00")
        self.assertEqual(by_code["social_security"]["total_amount"], "0.00")
        self.assertEqual(by_code["internal_transfer"]["total_amount"], "0.00")

    def test_detail_returns_batch_and_serialized_rows(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch_id = self._list_batches(app)["batches"][0]["batch_id"]

        response = app.handle_request("GET", f"/api/no-oa-bank-batches/{batch_id}")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["batch"]["batch_id"], batch_id)
        self.assertEqual(payload["tag_counts"], {"fee": 1})
        self.assertEqual(payload["direction_counts"], {"income": 0, "expense": 1})
        self.assertEqual(payload["rows"][0]["id"], "bank-202603-fee-1")
        self.assertEqual(payload["rows"][0]["category_code"], "fee")
        self.assertEqual(payload["rows"][0]["category_label"], "手续费")
        self.assertEqual(payload["rows"][0]["category_primary_label"], "费用")
        self.assertEqual(payload["rows"][0]["category_sub_label"], "手续费")
        self.assertEqual(payload["rows"][0]["category_label_path"], ["费用", "手续费"])
        self.assertEqual(payload["rows"][0]["category_source"], "auto")

    def test_detail_rows_include_workbench_relation_distribution_status(self) -> None:
        class RelationFacade:
            def __init__(self) -> None:
                self.last_source_versions = {"schema_version": 52, "source_version": 8}
                self.calls: list[list[str]] = []

            def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
                normalized = [str(row_id) for row_id in row_ids]
                self.calls.append(normalized)
                return {
                    "status": "fresh",
                    "rows": [
                        {
                            "row_id": "bank-202603-fee-1",
                            "row_type": "bank_transaction",
                            "relation_status": "linked",
                            "group_ids": ["case_no_oa_linked"],
                            "linked_oa": [{"id": "oa-no-oa-1"}],
                            "linked_input_invoices": [{"id": "inv-no-oa-1"}],
                            "linked_output_invoices": [],
                            "linked_bank_transactions": [{"id": "bank-202603-fee-1"}],
                        }
                    ],
                    "groups": [],
                    "source_versions": self.last_source_versions,
                    "read_model_scope_keys": ["2026-03"],
                    "refresh_enqueued": False,
                    "stale_reasons": [],
                }

        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        relation_facade = RelationFacade()
        app._workbench_relation_facade = relation_facade
        batch_id = self._list_batches(app)["batches"][0]["batch_id"]

        response = app.handle_request("GET", f"/api/no-oa-bank-batches/{batch_id}")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["rows"][0]["relation_status"], "linked")
        self.assertEqual(payload["rows"][0]["relation_case_ids"], ["case_no_oa_linked"])
        self.assertEqual(payload["rows"][0]["linked_oa_count"], 1)
        self.assertEqual(payload["rows"][0]["linked_invoice_count"], 1)
        self.assertEqual(payload["workbench_relation_source_versions"], {"schema_version": 52, "source_version": 8})
        self.assertEqual(relation_facade.calls[0], ["bank-202603-fee-1"])

    def test_list_summary_and_submitted_batches_use_current_bank_auto_tag_labels_after_rename(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        draft_batch = self._list_batches(app)["batches"][0]
        submit_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{draft_batch['batch_id']}/submit",
            body=json.dumps({"expected_version": draft_batch["version"]}),
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.body)
        submitted = json.loads(submit_response.body)["batch"]
        current_rules = app._app_settings_service.get_bank_auto_tag_rules_payload()
        renamed_rules = []
        for rule in current_rules["active_rules"]:
            next_rule = dict(rule)
            if rule["code"] == "fee":
                next_rule["output_primary_label"] = "运营费用"
                next_rule["output_sub_label"] = "银行手续费"
                next_rule["label"] = "银行手续费"
            renamed_rules.append(next_rule)
        app._app_settings_service.update_bank_auto_tag_rules(
            {
                "expected_version": current_rules["version"],
                "active_rules": renamed_rules,
                "archived_rules": current_rules["archived_rules"],
            },
            actor_id="settings-owner",
        )

        payload = self._list_batches(app, "?bucket=submitted")
        batch = payload["batches"][0]
        categories_by_code = {category["code"]: category for category in payload["summary"]["categories"]}
        withdraw_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{submitted['batch_id']}/withdraw",
            body=json.dumps({"expected_version": batch["version"], "reason": "标签改名后撤回"}),
        )

        self.assertEqual(batch["batch_id"], submitted["batch_id"])
        self.assertEqual(batch["category_primary_label"], "运营费用")
        self.assertEqual(batch["category_sub_label"], "银行手续费")
        self.assertEqual(batch["category_label_path"], ["运营费用", "银行手续费"])
        self.assertEqual(categories_by_code["fee"]["primary_label"], "运营费用")
        self.assertEqual(categories_by_code["fee"]["sub_label"], "银行手续费")
        self.assertEqual(withdraw_response.status_code, 200, withdraw_response.body)

    def test_bucket_filter_returns_unsubmitted_and_submitted_after_category_drift(self) -> None:
        app = self._app_with_transactions(
            [
                bank_transaction("bank-202603-fee-1", amount="3.00"),
                bank_transaction(
                    "bank-202604-salary-1",
                    category_code="salary",
                    amount="1000.00",
                    trade_time="2026-04-10T09:00:00",
                ),
            ],
            categories={"bank-202603-fee-1": "fee", "bank-202604-salary-1": "salary"},
        )
        batches = self._list_batches(app)["batches"]
        fee_batch = next(batch for batch in batches if batch["batch_type"] == "fee")
        salary_batch = next(batch for batch in batches if batch["batch_type"] == "salary")

        submit_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{fee_batch['batch_id']}/submit",
            body=json.dumps({"expected_version": fee_batch["version"]}),
        )
        submitted = json.loads(submit_response.body)["batch"]
        app._workbench_relation_facade = FakeNoOaRelationFacade(app._workbench_pair_relation_service.list_active_relations())
        submitted_payload = self._list_batches(app, "?bucket=submitted")
        self.assertEqual([batch["batch_id"] for batch in submitted_payload["batches"]], [submitted["batch_id"]])
        self.assertEqual(submitted_payload["summary"]["submitted_count"], 1)
        self.assertEqual(submitted_payload["summary"]["draft_count"], 1)
        self._replace_transaction_text(app, "bank-202603-fee-1", "其他流水")
        app._workbench_relation_facade = FakeNoOaRelationFacade([])
        stale = next(
            batch
            for batch in self._list_batches(app, "?bucket=unsubmitted")["batches"]
            if batch["batch_id"] == submitted["batch_id"]
        )
        withdraw_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{stale['batch_id']}/withdraw",
            body=json.dumps({"expected_version": stale["version"], "reason": "测试"}),
        )
        self.assertEqual(withdraw_response.status_code, 400, withdraw_response.body)
        self.assertEqual(json.loads(withdraw_response.body)["error"], "stale_no_oa_bank_batch_has_no_active_relation_to_withdraw")

        unsubmitted = self._list_batches(app, "?bucket=unsubmitted")
        withdrawn_payload = self._list_batches(app, "?bucket=withdrawn")
        all_payload = self._list_batches(app, "?bucket=all")

        self.assertEqual([batch["batch_id"] for batch in unsubmitted["batches"]], [submitted["batch_id"], salary_batch["batch_id"]])
        self.assertEqual(withdrawn_payload["batches"], [])
        self.assertEqual({batch["status_bucket"] for batch in all_payload["batches"]}, {"unsubmitted"})
        self.assertEqual(withdrawn_payload["summary"]["withdrawn_count"], 0)
        self.assertEqual(withdrawn_payload["summary"]["draft_count"], 1)

    def test_submit_persists_batch_and_pair_relation_and_invalidates_workbench(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
            app._state_store = build_application(data_dir=Path(temp_dir))._state_store
            batch = self._list_batches(app)["batches"][0]

            response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
                body=json.dumps({"expected_version": batch["version"], "note": "确认免OA"}),
            )
            payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(payload["batch"]["status"], "submitted")
            self.assertEqual(payload["batch"]["status_bucket"], "submitted")
            self.assertTrue(payload["batch"]["can_withdraw"])
            self.assertEqual(payload["pair_relation"]["relation_mode"], "no_oa_bank_batch")
            self.assertEqual(payload["affected_months"], ["2026-03"])
            self.assertTrue(payload["workbench_rebuild_queued"])
            self.assertEqual(payload["results"][0]["status"], "submitted")
            self.assertEqual(app._state_store.load_no_oa_bank_batches()["batches"][batch["batch_id"]]["status"], "submitted")
            pair_relations = app._state_store.load().get("workbench_pair_relations", {}).get("pair_relations", {})
            self.assertIn(payload["pair_relation"]["case_id"], pair_relations)

    def test_submit_returns_error_and_rolls_back_when_no_oa_batch_persistence_fails(self) -> None:
        class FailingNoOaBatchStore:
            def __init__(self) -> None:
                self.atomic_calls = 0

            def save_no_oa_bank_batch_mutation(self, **_kwargs) -> None:
                self.atomic_calls += 1
                raise RuntimeError("no oa mutation unavailable")

            def save_workbench_pair_relations(self, *_args, **_kwargs) -> None:
                raise AssertionError("no-OA mutations must use the atomic persistence boundary")

            def save_workbench_read_models(self, *_args, **_kwargs) -> None:
                raise AssertionError("no-OA mutations must use the atomic persistence boundary")

            def save_no_oa_bank_batches(self, *_args, **_kwargs) -> None:
                raise AssertionError("no-OA mutations must use the atomic persistence boundary")

        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]
        before_snapshot = app._no_oa_bank_batch_service.snapshot()
        before_relations = app._workbench_pair_relation_service.snapshot()
        failing_store = FailingNoOaBatchStore()
        app._state_store = failing_store

        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body=json.dumps({"expected_version": batch["version"], "note": "确认免OA"}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 500, response.body)
        self.assertEqual(payload["error"], "no_oa_bank_batch_persistence_failed")
        self.assertEqual(failing_store.atomic_calls, 1)
        self.assertEqual(app._no_oa_bank_batch_service.snapshot(), before_snapshot)
        self.assertEqual(app._workbench_pair_relation_service.snapshot(), before_relations)

    def test_withdraw_cancels_pair_relation_and_persists_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
            app._state_store = build_application(data_dir=Path(temp_dir))._state_store
            batch = self._list_batches(app)["batches"][0]
            submit_response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
                body=json.dumps({"expected_version": batch["version"]}),
            )
            submitted = json.loads(submit_response.body)["batch"]

            response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{submitted['batch_id']}/withdraw",
                body=json.dumps({"expected_version": submitted["version"], "reason": "误提交"}),
            )
            payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(payload["batch"]["status"], "withdrawn")
            self.assertEqual(payload["affected_months"], ["2026-03"])
            self.assertEqual(payload["pair_relation"]["status"], "cancelled")
            self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(submitted["relation_case_id"]))
            self.assertEqual(app._state_store.load_no_oa_bank_batches()["batches"][submitted["batch_id"]]["status"], "withdrawn")

    def test_bulk_submit_returns_partial_results(self) -> None:
        transactions = [
            bank_transaction("bank-202603-fee-1", amount="3.00"),
            bank_transaction(
                "bank-202604-salary-1",
                category_code="salary",
                amount="1000.00",
                trade_time="2026-04-10T09:00:00",
            ),
        ]
        app = self._app_with_transactions(
            transactions,
            categories={"bank-202603-fee-1": "fee", "bank-202604-salary-1": "salary"},
        )
        batches = self._list_batches(app)["batches"]
        draft_by_type = {batch["batch_type"]: batch for batch in batches}

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit",
            body=json.dumps(
                {
                    "batches": [
                        {
                            "batch_id": draft_by_type["fee"]["batch_id"],
                            "expected_version": draft_by_type["fee"]["version"],
                        },
                        {
                            "batch_id": draft_by_type["salary"]["batch_id"],
                            "expected_version": 999,
                        },
                    ]
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["summary"]["submitted"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual(payload["affected_months"], ["2026-03"])
        self.assertEqual([result["status"] for result in payload["results"]], ["submitted", "failed"])
        self.assertEqual(payload["results"][1]["error"], "no_oa_bank_batch_version_conflict")

    def test_stale_batch_after_category_drift_clears_relation_and_is_not_withdrawable(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]
        submit_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body=json.dumps({"expected_version": batch["version"]}),
        )
        submitted = json.loads(submit_response.body)["batch"]
        self._replace_transaction_text(app, "bank-202603-fee-1", "其他流水")

        stale_payload = self._list_batches(app, "?bucket=unsubmitted")
        stale = stale_payload["batches"][0]
        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{stale['batch_id']}/withdraw",
            body=json.dumps({"expected_version": stale["version"], "reason": "源分类变化"}),
        )
        payload = json.loads(response.body)

        self.assertEqual(stale["batch_id"], submitted["batch_id"])
        self.assertEqual(stale["status"], "stale")
        self.assertFalse(stale["can_withdraw"])
        self.assertEqual(response.status_code, 400, response.body)
        self.assertEqual(payload["error"], "stale_no_oa_bank_batch_has_no_active_relation_to_withdraw")
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(submitted["relation_case_id"]))

    def test_submit_version_conflict_returns_409(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]

        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body=json.dumps({"expected_version": 999}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "no_oa_bank_batch_version_conflict")

    def test_invalid_json_body_returns_json_error(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]

        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body="{bad json",
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_json_body")

    def test_unknown_batch_returns_404(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])

        response = app.handle_request("GET", "/api/no-oa-bank-batches/no_oa_batch_missing")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error"], "unknown_no_oa_bank_batch")


if __name__ == "__main__":
    unittest.main()
