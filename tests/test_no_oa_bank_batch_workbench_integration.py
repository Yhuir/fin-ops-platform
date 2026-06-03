import json
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService


def flatten_groups(groups: list[dict[str, object]], row_type: str) -> list[dict[str, object]]:
    return [
        row
        for group in groups
        for row in group[f"{row_type}_rows"]
    ]


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
    def test_no_oa_bank_batches_do_not_return_stale_sql_source_versions_as_fresh(self) -> None:
        class StaleNoOaReadRepository:
            def list_no_oa_bank_batch_rows(self, _filters: dict[str, object]) -> list[dict[str, object]]:
                return [
                    {
                        "batch_id": "stale_sql_batch",
                        "batch_type": "salary",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "scope_month": "2026-02",
                        "row_ids": ["stale-bank-row"],
                        "row_count": 1,
                        "total_amount": "1.00",
                        "source_versions": {"bank_auto_tag_rules_version": 0},
                    }
                ]

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
        version = json.loads(app.handle_request("GET", "/api/no-oa-bank-batches/tag-selection").body)["version"]
        app.handle_request(
            "PUT",
            "/api/no-oa-bank-batches/tag-selection",
            body=json.dumps({"expected_version": version, "selected_tag_codes": ["salary"]}),
            headers={"Content-Type": "application/json"},
        )
        app._workbench_sql_read_repository = StaleNoOaReadRepository()

        response = app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["read_model_status"], "stale")
        self.assertIn("bank_auto_tag_rules_version_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(payload["batches"][0]["batch_id"], "stale_sql_batch")

    def test_no_oa_bank_batches_missing_sql_read_model_does_not_refresh_in_get_path(self) -> None:
        class MissingNoOaReadRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def list_no_oa_bank_batch_rows(self, filters: dict[str, object]) -> None:
                self.calls.append(dict(filters))
                return None

        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs):
                self.enqueued.append(dict(kwargs))
                return {"event_id": "queued"}

        app = build_application()
        app._workbench_sql_read_repository = MissingNoOaReadRepository()
        app._runtime_repositories = type(
            "RuntimeRepositories",
            (),
            {"queue_repository": QueueRepository()},
        )()
        original_build_batches = app._no_oa_bank_batch_service.build_batches

        def fail_if_refreshed(*_args, **_kwargs):
            raise AssertionError("GET /api/no-oa-bank-batches must not rebuild no-OA batches synchronously")

        app._no_oa_bank_batch_service.build_batches = fail_if_refreshed
        try:
            response = app.handle_request("GET", "/api/no-oa-bank-batches?bucket=unsubmitted")
        finally:
            app._no_oa_bank_batch_service.build_batches = original_build_batches
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["read_model_status"], "missing")
        self.assertEqual(payload["batches"], [])
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(
            app._runtime_repositories.queue_repository.enqueued,
            [
                {
                    "scope_type": "no_oa_bank_batch",
                    "scope_key": "all",
                    "reason": "api_no_oa_read_model_missing",
                }
            ],
        )

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
            app._no_oa_bank_batch_source_versions(),
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

    def test_salary_auto_candidate_does_not_create_active_relation_before_batch_submit(self) -> None:
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

        response = app.handle_request("GET", "/api/workbench?month=all")
        payload = json.loads(response.body)
        auto_results = app._live_workbench_service.list_auto_pair_candidates("all")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(payload["open"]["groups"], "bank")], [salary_row_id])
        self.assertEqual(len(auto_results), 1)
        self.assertEqual(auto_results[0].rule_code, "salary_personal_auto_match")
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
        bank_rows = app._live_workbench_service.get_workbench("all")["open"]["bank"]
        service = app._no_oa_bank_batch_service
        batch = service.build_batches(
            bank_rows,
            {salary_row_id: {"category_code": "salary", "source": "auto"}},
            [],
            {},
        )[0]

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认工资")
        app._invalidate_workbench_read_models()
        paired_response = app.handle_request("GET", "/api/workbench?month=all")
        paired_payload = json.loads(paired_response.body)
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

        service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")
        app._invalidate_workbench_read_models()
        open_response = app.handle_request("GET", "/api/workbench?month=all")
        open_payload = json.loads(open_response.body)

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertEqual([row["id"] for row in flatten_groups(open_payload["open"]["groups"], "bank")], [salary_row_id])

    def test_no_oa_internal_transfer_relation_groups_bank_rows_until_cancelled(self) -> None:
        app = build_application()
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="internal-transfer.xlsx",
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
        row_ids = [transaction.id for transaction in app._import_service.list_transactions()]
        bank_rows = app._live_workbench_service.get_workbench("all")["open"]["bank"]
        service = app._no_oa_bank_batch_service
        batch = service.build_batches(
            bank_rows,
            {row_id: {"category_code": "internal_transfer", "source": "auto"} for row_id in row_ids},
            [],
            {},
        )[0]

        submitted = service.submit_batch(batch["batch_id"], actor="finance-user", expected_version=1, note="确认内部往来")
        app._invalidate_workbench_read_models()
        paired_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
        paired_group = paired_payload["paired"]["groups"][0]

        self.assertEqual(paired_payload["summary"]["paired_count"], 1)
        self.assertEqual(paired_group["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(paired_group["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired_group["bank_rows"]], [f"no_oa_summary:{submitted['batch_id']}"])
        self.assertCountEqual([row["id"] for row in paired_group["collapsed_rows"]["bank"]], row_ids)
        summary_row = paired_group["summary_row"]
        self.assertEqual(summary_row["invoice_relation"]["label"], "已匹配：内部往来款")
        self.assertEqual(summary_row["special_metadata"]["source_batch_id"], submitted["batch_id"])
        self.assertEqual(summary_row["special_metadata"]["batch_version"], submitted["version"])
        self.assertEqual(summary_row["special_metadata"]["row_count"], 2)
        self.assertEqual(summary_row["amount"], "50000.00")
        self.assertEqual(summary_row["special_metadata"]["total_amount"], "50000.00")

        service.withdraw_batch(submitted["batch_id"], actor="finance-user", expected_version=2, reason="误提交")
        app._invalidate_workbench_read_models()
        open_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)

        self.assertEqual(open_payload["summary"]["paired_count"], 0)
        self.assertCountEqual([row["id"] for row in flatten_groups(open_payload["open"]["groups"], "bank")], row_ids)

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
        app._invalidate_workbench_read_models()
        workbench_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
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
        self.assertEqual(paired_group["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired_group["bank_rows"]], [f"no_oa_summary:{salary_batch['batch_id']}"])
        self.assertCountEqual([row["id"] for row in paired_group["collapsed_rows"]["bank"]], salary_row_ids)
        self.assertEqual(paired_group["summary_row"]["special_metadata"]["row_count"], 4)
        self.assertEqual(paired_group["summary_row"]["special_metadata"]["total_amount"], "50.00")

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
        app._invalidate_workbench_read_models()
        workbench_payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
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
        self.assertEqual(paired_group["display_mode"], "collapsed_summary")
        self.assertEqual([row["id"] for row in paired_group["bank_rows"]], [f"no_oa_summary:{salary_batch['batch_id']}"])
        self.assertCountEqual([row["id"] for row in paired_group["collapsed_rows"]["bank"]], salary_row_ids)
        self.assertEqual(paired_group["summary_row"]["special_metadata"]["row_count"], 3)
        self.assertEqual(paired_group["summary_row"]["special_metadata"]["total_amount"], "33.00")

    def test_historical_salary_and_internal_transfer_relations_migrate_to_no_oa_collapsed_summaries(self) -> None:
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
        payload = json.loads(app.handle_request("GET", "/api/workbench?month=all").body)
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
            if group["bank_rows"][0]["special_metadata"]["batch_type"] == "salary"
        )
        transfer_group = next(group for group in paired_groups if group is not salary_group)
        salary_row = salary_group["bank_rows"][0]
        transfer_summary_row = transfer_group["bank_rows"][0]

        self.assertNotEqual(salary_group.get("display_mode"), "collapsed_summary")
        self.assertNotIn("collapsed_rows", salary_group)
        self.assertEqual(salary_row["id"], salary_row_id)
        self.assertEqual(salary_row["special_metadata"]["source_batch_id"], submitted_by_type["salary"]["batch_id"])
        self.assertIn("withdraw_no_oa_batch", salary_row["available_actions"])
        self.assertEqual(transfer_group["display_mode"], "collapsed_summary")
        self.assertEqual(
            transfer_summary_row["id"],
            f"no_oa_summary:{submitted_by_type['internal_transfer']['batch_id']}",
        )
        self.assertCountEqual(
            [row["id"] for row in transfer_group["collapsed_rows"]["bank"]],
            transfer_row_ids,
        )
        summary_rows = flatten_groups(paired_groups, "bank")
        self.assertTrue(
            all(row["invoice_relation"]["code"] == "no_oa_bank_batch" for row in summary_rows)
        )


if __name__ == "__main__":
    unittest.main()
