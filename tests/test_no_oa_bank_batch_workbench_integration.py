import json
from types import SimpleNamespace
import unittest

from tests.app_test_support import (
    build_grouped_workbench_projection as _build_grouped_workbench_projection,
    build_local_state_application as build_application,
    install_direct_workbench_selection_repository,
)
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService


def flatten_groups(groups: list[dict[str, object]], row_type: str) -> list[dict[str, object]]:
    return [
        row
        for group in groups
        for row in group[f"{row_type}_rows"]
    ]


def build_grouped_workbench_projection(app: object, month: str) -> dict[str, object]:
    return _build_grouped_workbench_projection(app, month, include_query_rows=False)


class PairSnapshotRelationFacade:
    def __init__(self, pair_service: object) -> None:
        self._pair_service = pair_service

    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        groups: list[dict[str, object]] = []
        rows: list[dict[str, object]] = []
        for relation in list(self._pair_service.list_active_relations()):
            if str(relation.get("month_scope") or month) != month:
                continue
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            case_id = str(relation.get("case_id") or "")
            groups.append(
                {
                    "group_id": case_id,
                    "scope_month": month,
                    "payload": {
                        "group_id": case_id,
                        "row_ids": row_ids,
                        "row_types": row_types,
                        "relation_mode": str(relation.get("relation_mode") or ""),
                        "special_metadata": dict(relation.get("special_metadata") or {})
                        if isinstance(relation.get("special_metadata"), dict)
                        else {},
                    },
                }
            )
            rows.extend(
                {
                    "row_id": row_id,
                    "row_type": "bank_transaction" if row_type == "bank" else row_type,
                    "group_ids": [case_id],
                }
                for row_id, row_type in zip(row_ids, row_types, strict=False)
            )
        return {
            "status": "fresh",
            "rows": rows,
            "groups": groups,
            "source_versions": {"schema_version": 52},
            "read_model_scope_keys": [month],
        }

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        wanted = {str(row_id) for row_id in row_ids}
        payload = self.list_by_month("2026-02")
        group_ids = {
            str(group_id)
            for row in list(payload["rows"])
            if str(row.get("row_id") or "") in wanted
            for group_id in list(row.get("group_ids") or [])
        }
        return {
            **payload,
            "rows": [row for row in list(payload["rows"]) if str(row.get("row_id") or "") in wanted],
            "groups": [group for group in list(payload["groups"]) if str(group.get("group_id") or "") in group_ids],
        }


class NoOaBankBatchWorkbenchIntegrationTests(unittest.TestCase):
    def _enable_no_oa_tags(self, app: object, tag_codes: list[str]) -> None:
        selection = app._app_settings_service.get_no_oa_bank_batch_tag_selection_payload()
        app._app_settings_service.update_no_oa_bank_batch_tag_selection(
            {
                "expected_version": selection["version"],
                "selected_tag_codes": tag_codes,
            },
            actor_id="tester",
        )

    def _set_bank_flow_rule_requirements(
        self,
        app: object,
        tag_code: str,
        *,
        requires_oa: bool,
        requires_invoice: bool,
    ) -> None:
        rules_payload = app._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload()
        app._app_settings_service.update_bank_flow_rule_batch_tag_rules(
            {
                "expected_version": rules_payload["version"],
                "rules": [
                    {
                        **rule,
                        "requires_oa": requires_oa if rule["tag_code"] == tag_code else rule["requires_oa"],
                        "requires_invoice": requires_invoice if rule["tag_code"] == tag_code else rule["requires_invoice"],
                    }
                    for rule in rules_payload["rules"]
                ],
            },
            actor_id="tester",
        )

    def _app_with_balanced_bank_rows(
        self,
        *,
        category_codes: list[str],
        summaries: list[str] | None = None,
    ) -> tuple[object, list[str]]:
        app = build_application()
        row_summaries = summaries or ["内部往来支出", "内部往来收入"]
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="workbench-balanced-bank-rows.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": row_summaries[0],
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 10:02:00",
                    "pay_receive_time": "2026-02-03 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": row_summaries[1],
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {"transaction_id": row_id, "category_code": category_code}
                for row_id, category_code in zip(row_ids, category_codes, strict=True)
            ],
            actor="tester",
        )
        self._enable_no_oa_tags(app, sorted(set(category_codes)))
        return app, row_ids

    def _post_confirm_link(self, app: object, row_ids: list[str]):
        install_direct_workbench_selection_repository(app)
        app._oa_sync_status_payload = lambda: {"status": "synced", "dirty_scopes": []}
        return app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            body=json.dumps(
                {
                    "month": "2026-02",
                    "row_ids": row_ids,
                    "row_types": ["bank"] * len(row_ids),
                    "case_id": "CASE-WORKBENCH-INTERNAL-TRANSFER",
                    "note": "关联台确认内部往来",
                }
            ),
        )

    def _post_confirm_link_preview(self, app: object, row_ids: list[str]):
        install_direct_workbench_selection_repository(app)
        app._oa_sync_status_payload = lambda: {"status": "synced", "dirty_scopes": []}
        return app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link/preview",
            body=json.dumps(
                {
                    "month": "2026-02",
                    "row_ids": row_ids,
                    "row_types": ["bank"] * len(row_ids),
                    "case_id": "CASE-WORKBENCH-INTERNAL-TRANSFER",
                }
            ),
        )

    def test_workbench_confirm_internal_transfer_bank_rows_uses_manual_relation_chain(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "internal_transfer"]
        )

        preview = self._post_confirm_link_preview(app, row_ids)
        response = self._post_confirm_link(app, row_ids)

        self.assertEqual(preview.status_code, 200, preview.body)
        preview_payload = json.loads(preview.body)
        self.assertEqual(preview_payload["operation"], "confirm_link")
        self.assertTrue(preview_payload["can_submit"])
        self.assertEqual(response.status_code, 200, response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
        self.assertCountEqual(relation["row_ids"], row_ids)
        history = app._workbench_pair_relation_service.snapshot()["pair_relation_history"]
        self.assertEqual(history[-1]["operation_type"], "confirm_link")

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        submitted = app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
        self.assertEqual(submitted, [])

    def test_workbench_confirm_non_internal_bank_only_rows_keeps_manual_relation(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["fee", "fee"],
            summaries=["手续费支出", "手续费退回"],
        )

        response = self._post_confirm_link(app, row_ids)

        self.assertEqual(response.status_code, 200, response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        app._no_oa_bank_batch_application_service().refresh_batches()
        submitted = app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
        self.assertEqual(submitted, [])

    def test_workbench_confirm_mixed_internal_transfer_bank_rows_uses_manual_relation_chain(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "fee"]
        )

        preview = self._post_confirm_link_preview(app, row_ids)
        response = self._post_confirm_link(app, row_ids)

        self.assertEqual(preview.status_code, 200, preview.body)
        self.assertEqual(json.loads(preview.body)["operation"], "confirm_link")
        self.assertEqual(response.status_code, 200, response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "manual_confirmed")
        self.assertCountEqual(relation["row_ids"], row_ids)
        history = app._workbench_pair_relation_service.snapshot()["pair_relation_history"]
        self.assertEqual(history[-1]["operation_type"], "confirm_link")

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        submitted = app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
        self.assertEqual(submitted, [])

    def test_application_service_submits_internal_transfer_rows_from_workbench_via_batch_submit(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "internal_transfer"]
        )
        application_service = app._no_oa_bank_batch_application_service()
        submit_from_workbench = getattr(
            application_service,
            "submit_internal_transfer_rows_from_workbench",
            None,
        )
        self.assertTrue(
            callable(submit_from_workbench),
            "NoOaBankBatchApplicationService must expose submit_internal_transfer_rows_from_workbench.",
        )

        result = submit_from_workbench(
            row_ids=row_ids,
            actor="finance-user",
            note="关联台确认内部往来",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(result["batch"]["batch_type"], "internal_transfer")
        self.assertEqual(set(result["batch"]["row_ids"]), set(row_ids))
        self.assertEqual(result["pair_relation"]["relation_mode"], "no_oa_bank_batch")

    def test_bank_flow_internal_transfer_batch_submit_publishes_paired_workbench_group(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "internal_transfer"]
        )
        self._set_bank_flow_rule_requirements(
            app,
            "internal_transfer",
            requires_oa=False,
            requires_invoice=False,
        )
        source_service = app._no_oa_bank_batch_application_service()
        candidate_rows = source_service.no_oa_bank_transaction_rows_by_ids(row_ids)
        categories = source_service.effective_categories_for_rows(candidate_rows)
        for row in candidate_rows:
            category = categories.get(str(row.get("id") or "")) or {}
            row["category_code"] = category.get("category_code")
        app._bank_flow_rule_batch_canonical_query_repository = SimpleNamespace(
            read_page=lambda *_args, **_kwargs: {
                "candidate_rows": candidate_rows,
                "active_relations": [],
                "formal_items": [],
                "tag_policy": app._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload(),
            }
        )
        application_service = app._bank_flow_rule_batch_application_service()
        draft = next(
            batch
            for batch in application_service.list_batches_payload(
                {"month": ["2026-02"], "bucket": ["unsubmitted"]}
            )["batches"]
            if batch["batch_type"] == "internal_transfer"
            and set(batch["row_ids"]) == set(row_ids)
        )
        app._bank_flow_rule_batch_application_service = lambda: application_service

        response = app.handle_request(
            "POST",
            f"/api/bank-flow-rule-batches/{draft['batch_id']}/submit",
            body=json.dumps(
                {
                    "expected_version": draft["version"],
                    "note": "流水规则提交内部往来",
                    "scope_month": draft["scope_month"],
                }
            ),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(response.status_code, 200, response.body)
        submit_payload = json.loads(response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_row_id(row_ids[0])
        self.assertIsNotNone(relation)
        assert relation is not None
        self.assertEqual(relation["relation_mode"], "bank_flow_rule_batch")
        self.assertCountEqual(relation["row_ids"], row_ids)
        self.assertFalse(relation["special_metadata"]["requires_oa"])
        self.assertFalse(relation["special_metadata"]["requires_invoice"])
        self.assertEqual(relation["display_tags"], ["流水规则", "内部往来款"])
        self.assertEqual(relation["special_metadata"]["display_tags"], ["流水规则", "内部往来款"])
        self.assertNotIn("免OA", relation["display_tags"])
        self.assertNotIn("operation_barrier_targets", submit_payload)
        self.assertNotIn("read_model_scope_keys", submit_payload)

        workbench_payload = build_grouped_workbench_projection(app, "all")
        paired_group = next(
            group for group in workbench_payload["paired"]["groups"]
            if group.get("relation_mode") == "bank_flow_rule_batch"
        )
        self.assertEqual(workbench_payload["summary"]["paired_count"], 1)
        self.assertCountEqual([row["id"] for row in paired_group["bank_rows"]], row_ids)
        self.assertNotIn("collapsed_rows", paired_group)
        self.assertTrue(
            all(row["invoice_relation"]["code"] == "bank_flow_rule_batch" for row in paired_group["bank_rows"])
        )

    def test_workbench_confirm_after_no_oa_submit_previews_withdraw_then_manual_replace(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "internal_transfer"]
        )
        application_service = app._no_oa_bank_batch_application_service()
        application_service.refresh_batches()
        draft = next(
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "unsubmitted"})
            if batch["batch_type"] == "internal_transfer"
            and set(batch["row_ids"]) == set(row_ids)
        )
        submit_response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{draft['batch_id']}/submit",
            body=json.dumps({"expected_version": draft["version"], "note": "免OA页面提交内部往来"}),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(submit_response.status_code, 200, submit_response.body)
        submitted_payload = json.loads(submit_response.body)
        original_case_id = submitted_payload["pair_relation"]["case_id"]

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        preview_response = self._post_confirm_link_preview(app, row_ids)
        confirm_response = self._post_confirm_link(app, row_ids)

        self.assertEqual(preview_response.status_code, 200, preview_response.body)
        self.assertEqual(json.loads(preview_response.body)["operation"], "withdraw_link")
        self.assertEqual(confirm_response.status_code, 200, confirm_response.body)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["case_id"], "CASE-WORKBENCH-INTERNAL-TRANSFER")
        active_relations = app._workbench_pair_relation_service.list_active_relations()
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["case_id"], "CASE-WORKBENCH-INTERNAL-TRANSFER")
        self.assertEqual(active_relations[0]["relation_mode"], "manual_confirmed")
        self.assertCountEqual(active_relations[0]["row_ids"], row_ids)

        application_service.refresh_batches()
        submitted = [
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
            if batch["batch_type"] == "internal_transfer"
            and set(batch["row_ids"]) == set(row_ids)
        ]
        self.assertEqual(len(submitted), 1)
        self.assertEqual(submitted[0]["relation_case_id"], original_case_id)
        unsubmitted = app._no_oa_bank_batch_service.list_batches({"bucket": "unsubmitted"})
        self.assertFalse(any(set(batch.get("row_ids") or []).intersection(row_ids) for batch in unsubmitted))

    def test_no_oa_list_api_reads_canonical_rows_without_read_model_lifecycle(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="salary-payment.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "salary"}],
            actor="tester",
        )
        self._enable_no_oa_tags(app, ["salary"])

        response = app.handle_request("GET", "/api/no-oa-bank-batches?month=2026-02&bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["batches"][0]["row_ids"], [row_id])
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("refresh_enqueued", payload)

    def test_no_oa_bank_batch_detail_does_not_refresh_all_batches(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="fee.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "手续费",
                    "remark": "手续费",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"}],
            actor="tester",
        )
        bank_rows = app._no_oa_bank_batch_application_service().no_oa_bank_transaction_rows()
        app._no_oa_bank_batch_service.build_batches(
            bank_rows,
            {row_id: {"category_code": "fee", "source": "auto"}},
            [],
            app._no_oa_bank_batch_application_service().no_oa_bank_batch_source_versions(),
            eligible_batch_types=["fee"],
        )
        batch_id = app._no_oa_bank_batch_service.list_batches()[0]["batch_id"]
        original_build_batches = app._no_oa_bank_batch_service.build_batches

        def fail_if_refreshed(*_args, **_kwargs):
            raise AssertionError("GET /api/no-oa-bank-batches/{batch_id} must not rebuild all batches synchronously")

        app._no_oa_bank_batch_service.build_batches = fail_if_refreshed
        try:
            response = app.handle_request("GET", f"/api/no-oa-bank-batches/{batch_id}")
        finally:
            app._no_oa_bank_batch_service.build_batches = original_build_batches
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["batch"]["batch_id"], batch_id)
        self.assertEqual(payload["rows"][0]["id"], row_id)

    def test_salary_row_remains_a_visible_unpaired_singleton_before_batch_submit(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="salary-payment.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id

        payload = build_grouped_workbench_projection(app, "all")
        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(payload["unpaired"]["groups"], "bank")], [salary_row_id])
        self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_row_id(salary_row_id))

    def test_no_oa_salary_batch_relation_pairs_then_cancel_returns_to_open(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="salary-payment.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id = app._import_service.list_transactions()[0].id
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": salary_row_id, "category_code": "salary"}],
            actor="tester",
        )
        self._enable_no_oa_tags(app, ["salary"])
        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        application_service = app._no_oa_bank_batch_application_service()
        application_service.refresh_batches()
        batch = next(
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "unsubmitted"})
            if salary_row_id in list(batch.get("row_ids") or [])
        )

        submit_result = application_service.submit_batch(
            batch["batch_id"],
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认工资",
        )
        submitted = submit_result["batch"]
        paired_payload = build_grouped_workbench_projection(app, "all")
        paired_group = paired_payload["paired"]["groups"][0]
        paired_row = paired_group["bank_rows"][0]

        self.assertEqual(paired_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_group["relation_mode"], "no_oa_bank_batch")
        self.assertNotEqual(paired_group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", paired_group)
        self.assertEqual(paired_row["id"], salary_row_id)
        self.assertEqual(paired_row["invoice_relation"]["code"], "no_oa_bank_batch")
        self.assertEqual(paired_row["invoice_relation"]["label"], "已匹配：工资")
        self.assertEqual(paired_row["special_metadata"]["source_batch_id"], submitted["batch_id"])
        self.assertEqual(paired_row["special_metadata"]["batch_version"], submitted["version"])
        self.assertEqual(paired_row["special_metadata"]["row_count"], 1)
        self.assertEqual(paired_row["special_metadata"]["total_amount"], "9.00")
        self.assertIn("withdraw_no_oa_batch", paired_row["available_actions"])
        self.assertIn("免OA", paired_row["tags"])
        self.assertIn("工资", paired_row["tags"])

        application_service.withdraw_batch(
            submitted["batch_id"],
            actor="finance-user",
            expected_version=int(submitted["version"]),
            reason="误提交",
        )
        open_payload = build_grouped_workbench_projection(app, "all")

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(open_payload["unpaired"]["groups"], "bank")], [salary_row_id])

    def test_submit_selection_fee_rows_render_as_collapsed_paired_workbench_group(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-fees.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "1.00",
                    "credit_amount": "",
                    "summary": "网银手续费",
                    "remark": "手续费明细 A",
                },
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:16:00",
                    "pay_receive_time": "2026-02-03 09:16:00",
                    "counterparty_name": "建设银行",
                    "debit_amount": "4.50",
                    "credit_amount": "",
                    "summary": "网银手续费",
                    "remark": "手续费明细 B",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "fee"} for row_id in row_ids],
            actor="tester",
        )
        self._enable_no_oa_tags(app, ["fee"])
        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)

        submit_result = app._no_oa_bank_batch_application_service().submit_selected_rows(
            row_ids=row_ids,
            actor="finance-user",
            note="确认手续费",
        )
        submitted = submit_result["batch"]
        workbench_payload = build_grouped_workbench_projection(app, "all")
        paired_group = workbench_payload["paired"]["groups"][0]
        bank_rows = paired_group["bank_rows"]

        self.assertEqual(workbench_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_group["relation_mode"], "no_oa_bank_batch")
        self.assertNotIn("display_mode", paired_group)
        self.assertNotIn("collapsed_rows", paired_group)
        self.assertCountEqual([row["id"] for row in bank_rows], row_ids)
        self.assertTrue(all(row["invoice_relation"]["code"] == "no_oa_bank_batch" for row in bank_rows))
        self.assertTrue(all(row["invoice_relation"]["label"] == "已匹配：手续费" for row in bank_rows))
        self.assertTrue(all(row["special_metadata"]["source_batch_id"] == submitted["batch_id"] for row in bank_rows))
        self.assertTrue(all("withdraw_no_oa_batch" in row["available_actions"] for row in bank_rows))

    def test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled(self) -> None:
        app, row_ids = self._app_with_balanced_bank_rows(
            category_codes=["internal_transfer", "internal_transfer"]
        )
        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        application_service = app._no_oa_bank_batch_application_service()
        application_service.refresh_batches()
        batch = next(
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "unsubmitted"})
            if set(batch.get("row_ids") or []) == set(row_ids)
        )

        submit_result = application_service.submit_batch(
            batch["batch_id"],
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认内部往来",
        )
        submitted = submit_result["batch"]
        paired_payload = build_grouped_workbench_projection(app, "all")
        paired_group = paired_payload["paired"]["groups"][0]

        self.assertEqual(paired_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_group["relation_mode"], "no_oa_bank_batch")
        self.assertNotIn("display_mode", paired_group)
        self.assertCountEqual([row["id"] for row in paired_group["bank_rows"]], row_ids)
        self.assertNotIn("collapsed_rows", paired_group)

        application_service.withdraw_batch(
            submitted["batch_id"],
            actor="finance-user",
            expected_version=int(submitted["version"]),
            reason="误提交",
        )
        open_payload = build_grouped_workbench_projection(app, "all")

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertCountEqual([row["id"] for row in flatten_groups(open_payload["unpaired"]["groups"], "bank")], row_ids)

    def test_historical_salary_relations_same_month_account_collapse_into_one_submitted_group(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="historical-salary-relations.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": f"2026-02-28 17:0{index}:00",
                    "pay_receive_time": f"2026-02-28 17:0{index}:00",
                    "counterparty_name": f"员工{index}",
                    "debit_amount": amount,
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
                for index, amount in enumerate(["9.00", "11.00", "13.00", "17.00"], start=1)
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {"transaction_id": row_id, "category_code": "salary"}
                for row_id in salary_row_ids
            ],
            actor="tester",
        )
        for index, row_id in enumerate(salary_row_ids, start=1):
            app._workbench_pair_relation_service.create_active_relation(
                case_id=f"salary_auto_history_{index}",
                row_ids=[row_id],
                row_types=["bank"],
                relation_mode="salary_personal_auto_match",
                created_by="system_auto_match",
                month_scope="2026-02",
            )

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        app._no_oa_bank_batch_application_service().refresh_batches()
        salary_batches = [
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
            if batch["batch_type"] == "salary"
        ]
        workbench_payload = build_grouped_workbench_projection(app, "all")
        paired_group = workbench_payload["paired"]["groups"][0]
        active_relations = app._workbench_pair_relation_service.list_active_relations()

        self.assertEqual(len(salary_batches), 1)
        salary_batch = salary_batches[0]
        self.assertEqual(salary_batch["status"], "submitted")
        self.assertEqual(salary_batch["row_count"], 4)
        self.assertEqual(salary_batch["total_amount"], "50.00")
        self.assertCountEqual(salary_batch["row_ids"], salary_row_ids)
        self.assertEqual(len(salary_batch["evidence"]["legacy_relations"]), 4)
        self.assertEqual(len(app._no_oa_bank_batch_service.audit_log()), 1)
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["relation_mode"], "no_oa_bank_batch")
        self.assertCountEqual(active_relations[0]["row_ids"], salary_row_ids)
        self.assertTrue(
            all(
                app._workbench_pair_relation_service.get_active_relation_by_case_id(f"salary_auto_history_{index}") is None
                for index in range(1, 5)
            )
        )
        self.assertEqual(workbench_payload["summary"]["paired_count"], 1)
        self.assertNotIn("display_mode", paired_group)
        self.assertCountEqual([row["id"] for row in paired_group["bank_rows"]], salary_row_ids)
        self.assertNotIn("collapsed_rows", paired_group)

    def test_existing_single_row_salary_no_oa_batches_consolidate_before_workbench_grouping(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="existing-single-row-salary-no-oa.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": f"2026-02-28 17:0{index}:00",
                    "pay_receive_time": f"2026-02-28 17:0{index}:00",
                    "counterparty_name": f"员工{index}",
                    "debit_amount": amount,
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                }
                for index, amount in enumerate(["9.00", "11.00", "13.00"], start=1)
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [{"transaction_id": row_id, "category_code": "salary"} for row_id in salary_row_ids],
            actor="tester",
        )
        for index, row_id in enumerate(salary_row_ids, start=1):
            old_batch_key = f"legacy:salary_personal_auto_match:salary_auto_history_{index}:{row_id}"
            old_batch_id = NoOaBankBatchService._batch_id(old_batch_key)
            app._no_oa_bank_batch_service._batches[old_batch_id] = app._no_oa_bank_batch_service._normalize_batch(
                {
                    "batch_id": old_batch_id,
                    "batch_key": old_batch_key,
                    "batch_type": "salary",
                    "batch_label": "工资",
                    "scope_month": "2026-02",
                    "account_key": "建设银行:0003",
                    "bank_name": "建设银行",
                    "account_last4": "0003",
                    "status": "submitted",
                    "row_ids": [row_id],
                    "row_count": 1,
                    "total_amount": ["9.00", "11.00", "13.00"][index - 1],
                    "tag_counts": {"salary": 1},
                    "direction_counts": {"income": 0, "expense": 1},
                    "relation_case_id": old_batch_id,
                    "evidence": {
                        "legacy_relation_mode": "salary_personal_auto_match",
                        "legacy_case_id": f"salary_auto_history_{index}",
                        "migration_source": "no_oa_legacy_relation_migration",
                        "migrated_at": "2026-05-15T00:00:00+00:00",
                    },
                    "category_source": "legacy_relation_migration",
                    "created_by": "no_oa_legacy_relation_migration",
                    "created_at": "2026-05-15T00:00:00+00:00",
                    "submitted_by": "no_oa_legacy_relation_migration",
                    "submitted_at": "2026-05-15T00:00:00+00:00",
                }
            )
            app._workbench_pair_relation_service.create_active_relation(
                case_id=old_batch_id,
                row_ids=[row_id],
                row_types=["bank"],
                relation_mode="no_oa_bank_batch",
                created_by="no_oa_legacy_relation_migration",
                month_scope="2026-02",
                special_metadata={
                    "source": "no_oa_bank_batch",
                    "source_batch_id": old_batch_id,
                    "batch_type": "salary",
                    "batch_label": "工资",
                    "relation_mode": "no_oa_bank_batch",
                },
                display_tags=["免OA", "工资"],
            )

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        app._no_oa_bank_batch_application_service().refresh_batches()
        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        app._no_oa_bank_batch_application_service().refresh_batches()
        salary_batches = [
            batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
            if batch["batch_type"] == "salary"
        ]
        workbench_payload = build_grouped_workbench_projection(app, "all")
        paired_group = workbench_payload["paired"]["groups"][0]
        active_relations = app._workbench_pair_relation_service.list_active_relations()

        self.assertEqual(len(salary_batches), 1)
        salary_batch = salary_batches[0]
        self.assertEqual(salary_batch["batch_key"], "legacy_single:salary:2026-02:建设银行:0003")
        self.assertEqual(salary_batch["row_count"], 3)
        self.assertEqual(salary_batch["total_amount"], "33.00")
        self.assertCountEqual(salary_batch["row_ids"], salary_row_ids)
        self.assertEqual(salary_batch["evidence"]["consolidation_source"], "submitted_no_oa_single_side_batches")
        self.assertEqual(len(active_relations), 1)
        self.assertEqual(active_relations[0]["relation_mode"], "no_oa_bank_batch")
        self.assertCountEqual(active_relations[0]["row_ids"], salary_row_ids)
        self.assertEqual(workbench_payload["summary"]["paired_count"], 1)
        self.assertNotIn("display_mode", paired_group)
        self.assertNotIn("collapsed_rows", paired_group)
        self.assertCountEqual([row["id"] for row in paired_group["bank_rows"]], salary_row_ids)
        self.assertTrue(
            all(
                row["special_metadata"]["source_batch_id"] == salary_batch["batch_id"]
                for row in paired_group["bank_rows"]
            )
        )

    def test_historical_salary_and_internal_transfer_relations_migrate_to_direct_no_oa_rows(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="historical-special-relations.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220003",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-28",
                    "trade_time": "2026-02-28 17:08:00",
                    "pay_receive_time": "2026-02-28 17:08:00",
                    "counterparty_name": "李四",
                    "debit_amount": "9.00",
                    "credit_amount": "",
                    "summary": "2月工资发放",
                    "remark": "工资",
                },
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 09:15:00",
                    "pay_receive_time": "2026-02-03 09:15:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "50000.00",
                    "credit_amount": "",
                    "summary": "内部往来支出",
                },
                {
                    "account_no": "62220002",
                    "account_name": "云南溯源科技有限公司招商银行一般户",
                    "txn_date": "2026-02-03",
                    "trade_time": "2026-02-03 10:02:00",
                    "pay_receive_time": "2026-02-03 10:02:00",
                    "counterparty_name": "云南溯源科技有限公司",
                    "debit_amount": "",
                    "credit_amount": "50000.00",
                    "summary": "内部往来收入",
                },
            ],
        )
        app._import_service.confirm_import(preview.id)
        salary_row_id, *transfer_row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        app._bank_transaction_category_service.apply_updates(
            [
                {"transaction_id": salary_row_id, "category_code": "salary"},
                *[
                    {"transaction_id": row_id, "category_code": "internal_transfer"}
                    for row_id in transfer_row_ids
                ],
            ],
            actor="tester",
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="salary_auto_history",
            row_ids=[salary_row_id],
            row_types=["bank"],
            relation_mode="salary_personal_auto_match",
            created_by="system_auto_match",
            month_scope="2026-02",
        )
        app._workbench_pair_relation_service.create_active_relation(
            case_id="internal_transfer_history",
            row_ids=transfer_row_ids,
            row_types=["bank", "bank"],
            relation_mode="internal_transfer_pair",
            created_by="system_auto_match",
            month_scope="2026-02",
        )

        app._workbench_relation_facade = PairSnapshotRelationFacade(app._workbench_pair_relation_service)
        app._no_oa_bank_batch_application_service().refresh_batches()
        submitted_by_type = {
            batch["batch_type"]: batch
            for batch in app._no_oa_bank_batch_service.list_batches({"bucket": "submitted"})
        }
        payload = build_grouped_workbench_projection(app, "all")
        paired_groups = payload["paired"]["groups"]
        active_modes = [
            relation["relation_mode"]
            for relation in app._workbench_pair_relation_service.list_active_relations()
        ]

        self.assertEqual(set(submitted_by_type), {"salary", "internal_transfer"})
        self.assertEqual(submitted_by_type["salary"]["status"], "submitted")
        self.assertEqual(submitted_by_type["salary"]["evidence"]["legacy_relation_mode"], "salary_personal_auto_match")
        self.assertEqual(submitted_by_type["internal_transfer"]["evidence"]["legacy_relation_mode"], "internal_transfer_pair")
        self.assertCountEqual(active_modes, ["no_oa_bank_batch", "no_oa_bank_batch"])
        self.assertEqual(payload["summary"]["paired_count"], 2)
        salary_group = next(
            group
            for group in paired_groups
            if group["case_id"] == submitted_by_type["salary"]["batch_id"]
        )
        transfer_group = next(group for group in paired_groups if group is not salary_group)
        salary_row = salary_group["bank_rows"][0]
        transfer_rows = transfer_group["bank_rows"]

        self.assertNotEqual(salary_group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", salary_group)
        self.assertEqual(salary_row["id"], salary_row_id)
        self.assertEqual(salary_row["special_metadata"]["source_batch_id"], submitted_by_type["salary"]["batch_id"])
        self.assertIn("withdraw_no_oa_batch", salary_row["available_actions"])
        self.assertNotIn("display_mode", transfer_group)
        self.assertNotIn("collapsed_rows", transfer_group)
        self.assertCountEqual([row["id"] for row in transfer_rows], transfer_row_ids)
        summary_rows = flatten_groups(paired_groups, "bank")
        self.assertTrue(
            all(row["invoice_relation"]["code"] == "no_oa_bank_batch" for row in summary_rows)
        )


if __name__ == "__main__":
    unittest.main()
