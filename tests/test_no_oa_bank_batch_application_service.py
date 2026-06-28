from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.no_oa_bank_batch_application_service import (
    NoOaBankBatchApplicationService,
    NoOaBankBatchPersistenceError,
    NoOaPairRelationSnapshotPort,
)
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class WriteBlockingNoOaPairRelationService(WorkbenchPairRelationService):
    def create_active_relation(self, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("no-OA relation writes must delegate to WorkbenchRelationCommandService.")

    def cancel_relation(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("no-OA relation writes must delegate to WorkbenchRelationCommandService.")


class RecordingNoOaRelationCommandService:
    def __init__(self) -> None:
        self.preflight_calls: list[dict[str, object]] = []
        self.confirm_calls: list[dict[str, object]] = []
        self.cancel_calls: list[dict[str, object]] = []

    def assert_write_precondition(self, **kwargs: object) -> dict[str, object]:
        self.preflight_calls.append(dict(kwargs))
        return {
            "status": "ok",
            "affected_scope_keys": [str(kwargs.get("month_scope") or "all")],
        }

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": str(kwargs["case_id"]),
            "row_ids": list(kwargs["row_ids"]),
            "row_types": list(kwargs["row_types"]),
            "status": "active",
            "relation_mode": str(kwargs["relation_mode"]),
            "month_scope": str(kwargs.get("month_scope") or "all"),
            "special_metadata": dict(kwargs.get("special_metadata") or {}),
            "display_tags": list(kwargs.get("display_tags") or []),
            "evidence": dict(kwargs.get("evidence") or {}),
            "version": 1,
        }
        return {
            "status": "confirmed",
            "relation": relation,
            "history": {"operation_type": str(kwargs.get("history_operation_type") or "confirm_relation")},
            "changed_case_ids": [relation["case_id"]],
            "affected_months": [relation["month_scope"]],
            "version": 1,
            "idempotent_replay": False,
        }

    def cancel_relation(self, **kwargs: object) -> dict[str, object]:
        self.cancel_calls.append(dict(kwargs))
        return {
            "status": "cancelled",
            "relation": {
                "case_id": str(kwargs["case_id"]),
                "row_ids": [],
                "status": "cancelled",
                "version": 2,
            },
            "history": {"operation_type": str(kwargs.get("history_operation_type") or "cancel_relation")},
            "changed_case_ids": [str(kwargs["case_id"])],
            "affected_months": ["2026-03"],
            "version": 2,
            "idempotent_replay": False,
        }


class RefreshingNoOaRelationCommandService(RecordingNoOaRelationCommandService):
    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        raise WorkbenchRelationCommandError(
            "workbench_relation_context_not_ready",
            "refreshing",
            payload={"row_ids": list(kwargs.get("row_ids") or [])},
        )


class EmptyWorkbenchRelationFacade:
    def __init__(self) -> None:
        self.last_source_versions: dict[str, object] = {}

    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": month}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
        }

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": "2026-03"}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
        }

    def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        self.last_source_versions = {"schema_version": 52, "scope_key": month}
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": dict(self.last_source_versions),
        }


def no_oa_bank_row(
    row_id: str,
    *,
    category_code: str,
    debit_amount: str = "",
    credit_amount: str = "",
    account_key: str = "CCB:8106",
) -> dict[str, object]:
    return {
        "id": row_id,
        "type": "bank",
        "category_code": category_code,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "amount": debit_amount or credit_amount,
        "direction": "expense" if debit_amount else "income",
        "account_key": account_key,
        "bank_name": account_key.split(":", 1)[0],
        "account_no": f"622200000000{account_key.split(':', 1)[-1]}",
        "account_last4": account_key.split(":", 1)[-1],
        "pay_receive_time": "2026-03-10T09:00:00",
        "counterparty_name": "云南三源",
    }


def no_oa_categories(rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    labels = {"fee": "手续费", "salary": "工资", "internal_transfer": "内部往来款"}
    return {
        str(row["id"]): {
            "transaction_id": row["id"],
            "category_code": row["category_code"],
            "category_label": labels.get(str(row["category_code"]), str(row["category_code"])),
            "category_source": "auto",
        }
        for row in rows
    }


class NoOaBankBatchApplicationServiceTests(unittest.TestCase):
    def _application_service(
        self,
        *,
        rows: list[dict[str, object]],
        selected_tag_codes: list[str],
        pair_relation_service: WorkbenchPairRelationService | None = None,
        relation_command_service: object | None = None,
        no_oa_snapshot: dict[str, object] | None = None,
        relation_facade: object | None = None,
    ) -> tuple[NoOaBankBatchApplicationService, NoOaBankBatchService, RecordingNoOaRelationCommandService]:
        categories = no_oa_categories(rows)
        pair_service = pair_relation_service or WorkbenchPairRelationService()
        command_service = (
            relation_command_service
            if isinstance(relation_command_service, RecordingNoOaRelationCommandService)
            else RecordingNoOaRelationCommandService()
        )
        no_oa_service = NoOaBankBatchService.from_snapshot(
            no_oa_snapshot,
            pair_relation_service=pair_service,
            relation_command_service=command_service,
        )
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(list_transactions=lambda month="all": deepcopy(rows)),
            effective_category_provider=SimpleNamespace(
                bulk_get_for_rows=lambda bank_rows: {
                    str(row.get("id")): deepcopy(categories[str(row.get("id"))])
                    for row in bank_rows
                    if str(row.get("id")) in categories
                }
            ),
            no_oa_bank_batch_service=no_oa_service,
            app_settings_service=SimpleNamespace(
                get_no_oa_bank_batch_tag_selection_payload=lambda: {
                    "version": 1,
                    "selected_tag_codes": list(selected_tag_codes),
                }
            ),
            bank_transaction_category_service=SimpleNamespace(
                snapshot=lambda: {},
                tag_dictionary_payload=lambda: {"definitions": []},
            ),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(pair_service),
            state_store=None,
            relation_facade=relation_facade or EmptyWorkbenchRelationFacade(),
            relation_command_service=command_service,
        )
        return service, no_oa_service, command_service
        self.assertEqual(repository.calls, [{"month": "2026-06"}, {"summary_filters": {"month": "2026-06"}}])

    def test_submit_batch_delegates_relation_write_to_command_service(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        pair_service = WriteBlockingNoOaPairRelationService()
        service, no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            pair_relation_service=pair_service,
        )
        service.refresh_batches()
        batch = no_oa_service.list_batches({"bucket": "unsubmitted"})[0]

        result = service.submit_batch(
            str(batch["batch_id"]),
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertEqual(call["case_id"], batch["relation_case_id"])
        self.assertEqual(call["row_ids"], ["fee-1"])
        self.assertEqual(call["row_types"], ["bank"])
        self.assertEqual(call["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["special_metadata"]["source"], "no_oa_bank_batch")
        self.assertEqual(call["special_metadata"]["source_batch_id"], batch["batch_id"])
        self.assertEqual(call["special_metadata"]["row_tag_snapshot"]["fee-1"]["category_code"], "fee")
        self.assertEqual(call["special_metadata"]["row_tag_snapshot"]["fee-1"]["category_label"], "手续费")
        self.assertEqual(call["display_tags"], ["免OA", "手续费"])

    def test_submit_batch_maps_relation_refreshing_to_business_unavailable_error(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        command_service = RefreshingNoOaRelationCommandService()
        service, no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            pair_relation_service=WriteBlockingNoOaPairRelationService(),
            relation_command_service=command_service,
        )
        service.refresh_batches()
        batch = no_oa_service.list_batches({"bucket": "unsubmitted"})[0]

        with self.assertRaisesRegex(ValueError, "no_oa_bank_batch_relation_unavailable") as context:
            service.submit_batch(
                str(batch["batch_id"]),
                actor="finance-user",
                expected_version=int(batch["version"]),
                note="确认",
            )

        self.assertEqual(getattr(context.exception, "error_code", ""), "no_oa_bank_batch_relation_unavailable")

    def test_submitted_batch_detail_keeps_submitted_row_tags_after_bank_category_changes(self) -> None:
        initial_rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        service, no_oa_service, _relation_command = self._application_service(
            rows=initial_rows,
            selected_tag_codes=["fee", "salary"],
        )
        service.refresh_batches()
        batch = no_oa_service.list_batches({"bucket": "unsubmitted"})[0]
        submitted = service.submit_batch(
            str(batch["batch_id"]),
            actor="finance-user",
            expected_version=int(batch["version"]),
            note="确认",
        )

        changed_rows = [no_oa_bank_row("fee-1", category_code="salary", debit_amount="3.00")]
        service_after_change, _no_oa_after_change, _relation_command_after_change = self._application_service(
            rows=changed_rows,
            selected_tag_codes=["fee", "salary"],
            no_oa_snapshot=no_oa_service.snapshot(),
        )

        detail = service_after_change.detail_payload(str(submitted["batch"]["batch_id"]))

        self.assertEqual(detail["batch"]["status"], "submitted")
        self.assertEqual(detail["batch"]["batch_type"], "fee")
        self.assertEqual(detail["rows"][0]["category_code"], "fee")
        self.assertEqual(detail["rows"][0]["category_label"], "手续费")
        self.assertEqual(detail["categories_by_transaction_id"]["fee-1"]["category_code"], "fee")
        self.assertEqual(detail["categories_by_transaction_id"]["fee-1"]["category_label"], "手续费")

    def test_list_batches_explicit_pagination_protects_first_screen_slo(self) -> None:
        rows = [
            no_oa_bank_row(
                f"fee-{index:03d}",
                category_code="fee",
                debit_amount="1.00",
                account_key=f"CCB:{index:04d}",
            )
            for index in range(250)
        ]
        service, _no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
        )
        service.refresh_batches()

        first_page = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]})
        second_page = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["2"], "page_size": ["200"]})

        self.assertEqual(len(first_page["batches"]), 200)
        self.assertEqual(first_page["summary"]["total"], 250)
        self.assertEqual(first_page["pagination"], {"page": 1, "page_size": 200, "pageSize": 200, "total": 250})
        self.assertEqual(len(second_page["batches"]), 50)
        self.assertEqual(second_page["summary"]["total"], 250)
        self.assertEqual(second_page["pagination"], {"page": 2, "page_size": 200, "pageSize": 200, "total": 250})

        with self.assertRaisesRegex(ValueError, "page_size must be <= 200") as context:
            service.list_batches_payload({"page": ["1"], "page_size": ["201"]})
        self.assertEqual(getattr(context.exception, "error_code", ""), "invalid_paging")

    def test_list_batches_uses_direct_service_not_read_model_repository(self) -> None:
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            no_oa_snapshot={
                "batches": {
                    "batch-stale-but-linked": {
                        "batch_id": "batch-stale-but-linked",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "row_count": 2,
                        "total_amount": "86.00",
                        "blocked_reason": "源流水或分类已变化，需要复核后处理。",
                        "can_submit": False,
                        "can_withdraw": True,
                        "version": 4,
                        "source_versions": {},
                    }
                },
                "audit_log": [],
            },
        )

        payload = service.list_batches_payload({"bucket": ["submitted"]})

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["summary"]["stale_count"], 0)
        self.assertEqual(payload["summary"]["categories"][0]["submitted"], 1)
        self.assertEqual(payload["summary"]["categories"][0]["stale"], 0)
        batch = payload["batches"][0]
        self.assertEqual(batch["status"], "submitted")
        self.assertEqual(batch["status_bucket"], "submitted")
        self.assertEqual(batch["can_submit"], False)
        self.assertEqual(batch["can_withdraw"], True)

    def test_empty_direct_list_does_not_refresh_missing_read_model(self) -> None:
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
        )

        payload = service.list_batches_payload(
            {"month": ["2026-06"], "bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]}
        )

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("refresh_reason", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual(payload["batches"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 200, "pageSize": 200, "total": 0})

    def test_direct_list_rows_ignore_stale_read_model_repository(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="1.00")]
        service, _no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
        )
        service.refresh_batches()

        payload = service.list_batches_payload({"bucket": ["unsubmitted"]})

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("refresh_reason", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual(len(payload["batches"]), 1)

    def test_list_batches_does_not_load_relation_source_versions_for_stale_check(self) -> None:
        class RelationFacade:
            def __init__(self) -> None:
                self.calls: list[str] = []
                self.last_source_versions: dict[str, object] = {"scope_key": "2026-01", "source_version": 1}

            def source_versions_for_month(self, month: str, *_args: object, **_kwargs: object) -> dict[str, object]:
                self.calls.append(month)
                self.last_source_versions = {"scope_key": month, "source_version": 2}
                return {
                    "status": "fresh",
                    "rows": [],
                    "groups": [],
                    "source_versions": dict(self.last_source_versions),
                }

        relation_facade = RelationFacade()
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee"],
            relation_facade=relation_facade,
            no_oa_snapshot={
                "batches": {
                    "batch-fresh-fee": {
                        "batch_id": "batch-fresh-fee",
                        "batch_type": "fee",
                        "scope_month": "2026-06",
                        "account_key": "CCB:8106",
                        "status": "draft",
                        "status_bucket": "unsubmitted",
                        "row_count": 1,
                        "total_amount": "12.00",
                        "source_versions": {},
                    }
                },
                "audit_log": [],
            },
        )

        payload = service.list_batches_payload(
            {"month": ["2026-06"], "bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]}
        )

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("read_model_stale_reasons", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual(payload["batches"][0]["batch_id"], "batch-fresh-fee")
        self.assertEqual(relation_facade.calls, [])

    def test_sql_read_model_exception_batches_are_not_public_payload(self) -> None:
        service, _no_oa_service, _relation_command = self._application_service(
            rows=[],
            selected_tag_codes=["fee", "salary", "internal_transfer"],
            no_oa_snapshot={
                "batches": {
                    "batch-draft-fee": {
                        "batch_id": "batch-draft-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "status": "draft",
                        "status_bucket": "unsubmitted",
                        "row_count": 1,
                        "total_amount": "1.00",
                        "can_submit": True,
                        "can_withdraw": False,
                        "version": 1,
                    },
                    "batch-conflict-transfer": {
                        "batch_id": "batch-conflict-transfer",
                        "batch_type": "internal_transfer",
                        "batch_label": "内部往来款",
                        "scope_month": "2026-03",
                        "account_key": "multi",
                        "status": "conflict",
                        "status_bucket": "unsubmitted",
                        "row_count": 1,
                        "total_amount": "1.00",
                        "conflict_reason": "内部往来存在多解，不能自动形成可提交批次。",
                        "can_submit": False,
                        "can_withdraw": False,
                        "version": 1,
                    },
                    "batch-stale-fee": {
                        "batch_id": "batch-stale-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "status": "stale",
                        "status_bucket": "unsubmitted",
                        "row_count": 1,
                        "total_amount": "1.00",
                        "blocked_reason": "源流水或分类已变化，需要复核后处理。",
                        "can_submit": False,
                        "can_withdraw": False,
                        "version": 2,
                    },
                    "batch-submitted-salary": {
                        "batch_id": "batch-submitted-salary",
                        "batch_type": "salary",
                        "batch_label": "工资",
                        "scope_month": "2026-03",
                        "account_key": "ICBC:6386",
                        "status": "submitted",
                        "status_bucket": "submitted",
                        "row_count": 1,
                        "total_amount": "2.00",
                        "can_submit": False,
                        "can_withdraw": True,
                        "version": 3,
                    },
                    "batch-withdrawn-fee": {
                        "batch_id": "batch-withdrawn-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "status": "withdrawn",
                        "status_bucket": "withdrawn",
                        "row_count": 1,
                        "total_amount": "3.00",
                        "can_submit": False,
                        "can_withdraw": False,
                        "version": 4,
                    },
                },
                "audit_log": [],
            },
        )

        payload = service.list_batches_payload({"bucket": ["unsubmitted"], "page": ["1"], "page_size": ["200"]})

        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual([batch["batch_id"] for batch in payload["batches"]], ["batch-draft-fee"])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 200, "pageSize": 200, "total": 1})
        self.assertEqual(payload["summary"]["total"], 3)
        self.assertEqual(payload["summary"]["draft_count"], 1)
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["summary"]["withdrawn_count"], 1)
        self.assertEqual(payload["summary"]["conflict_count"], 0)
        self.assertEqual(payload["summary"]["stale_count"], 0)

    def test_detail_payload_hides_non_public_exception_batches(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="1.00")]
        service, _no_oa_service, _relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            no_oa_snapshot={
                "batches": {
                    "batch-stale-fee": {
                        "batch_id": "batch-stale-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "scope_month": "2026-03",
                        "account_key": "CCB:8106",
                        "bank_name": "CCB",
                        "account_last4": "8106",
                        "status": "stale",
                        "status_bucket": "unsubmitted",
                        "row_ids": ["fee-1"],
                        "row_count": 1,
                        "total_amount": "1.00",
                        "version": 2,
                    }
                },
                "audit_log": [],
            },
        )

        with self.assertRaisesRegex(KeyError, "no_oa_bank_batch_not_found"):
            service.detail_payload("batch-stale-fee")

    def test_withdraw_batch_delegates_relation_cancel_to_command_service(self) -> None:
        rows = [no_oa_bank_row("fee-1", category_code="fee", debit_amount="3.00")]
        setup_pair_service = WorkbenchPairRelationService()
        setup_service = NoOaBankBatchService(pair_relation_service=setup_pair_service)
        draft = setup_service.build_batches(rows, no_oa_categories(rows), [], {})[0]
        submitted = setup_service.submit_batch(
            str(draft["batch_id"]),
            actor="finance-user",
            expected_version=int(draft["version"]),
            note="确认",
        )
        service, _no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["fee"],
            pair_relation_service=WriteBlockingNoOaPairRelationService(),
            no_oa_snapshot=setup_service.snapshot(),
        )

        result = service.withdraw_batch(
            str(submitted["batch_id"]),
            actor="finance-user",
            expected_version=int(submitted["version"]),
            reason="误提交",
        )

        self.assertEqual(result["batch"]["status"], "withdrawn")
        self.assertEqual(len(relation_command.cancel_calls), 1)
        call = relation_command.cancel_calls[0]
        self.assertEqual(call["case_id"], submitted["relation_case_id"])
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["reason"], "误提交")
        self.assertEqual(call["history_operation_type"], "no_oa_bank_batch_withdraw")

    def test_internal_transfer_from_workbench_delegates_relation_write_to_command_service(self) -> None:
        rows = [
            no_oa_bank_row(
                "transfer-out",
                category_code="internal_transfer",
                debit_amount="50000.00",
                account_key="CCB:8106",
            ),
            no_oa_bank_row(
                "transfer-in",
                category_code="internal_transfer",
                credit_amount="50000.00",
                account_key="CMB:3847",
            ),
        ]
        service, _no_oa_service, relation_command = self._application_service(
            rows=rows,
            selected_tag_codes=["internal_transfer"],
            pair_relation_service=WriteBlockingNoOaPairRelationService(),
        )

        result = service.submit_internal_transfer_rows_from_workbench(
            row_ids=["transfer-out", "transfer-in"],
            actor="finance-user",
            note="关联台确认内部往来",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(len(relation_command.confirm_calls), 1)
        call = relation_command.confirm_calls[0]
        self.assertCountEqual(call["row_ids"], ["transfer-out", "transfer-in"])
        self.assertEqual(call["row_types"], ["bank", "bank"])
        self.assertEqual(call["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(call["actor_id"], "finance-user")
        self.assertEqual(call["special_metadata"]["batch_type"], "internal_transfer")
        self.assertEqual(call["display_tags"], ["免OA", "内部往来款"])

    def test_after_mutation_persists_changed_cases_and_expanded_workbench_scopes(self) -> None:
        lifecycle_events: list[dict[str, object]] = []
        cache_clears: list[str] = []

        class StateStore:
            def __init__(self) -> None:
                self.saved_mutations: list[dict[str, object]] = []

            def save_no_oa_bank_batch_mutation(self, **kwargs: object) -> None:
                self.saved_mutations.append(dict(kwargs))

        state_store = StateStore()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {"batches": {}}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            )),
            state_store=state_store,
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
            search_cache_clearer=lambda: cache_clears.append("search"),
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month", "2026-06"],
            changed_case_ids=["case-001", "case-002"],
            persist=True,
            action_name="no_oa_bank_batch_withdraw",
        )

        self.assertTrue(changed)
        self.assertEqual(
            lifecycle_events,
            [
                {
                    "event_type": "no_oa_bank_batch_changed",
                    "months": ["2026-05", "2026-06"],
                    "metadata": {
                        "source": "no_oa_bank_batch",
                        "action_name": "no_oa_bank_batch_withdraw",
                    },
                    "schedule_cost_warmup": False,
                }
            ],
        )
        self.assertEqual(cache_clears, ["search"])
        self.assertEqual(len(state_store.saved_mutations), 1)
        saved = state_store.saved_mutations[0]
        self.assertEqual(saved["changed_case_ids"], ["case-001", "case-002"])
        self.assertEqual(saved["pair_relation_snapshot"], {"relations": ["case-001", "case-002"]})
        self.assertEqual(saved["no_oa_bank_batch_snapshot"], {"batches": {}})
        self.assertNotIn("workbench_read_model_snapshot", saved)

    def test_after_mutation_without_atomic_persistence_boundary_fails_fast(self) -> None:
        class BroadOnlyStateStore:
            def save_workbench_pair_relations(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad pair relation persistence")

            def save_no_oa_bank_batches(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad no-OA batch persistence")

            def save_workbench_read_models(self, *_args: object, **_kwargs: object) -> None:
                raise AssertionError("no-OA mutation must not fall back to broad workbench read model persistence")

        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {"batches": {}}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            )),
            state_store=BroadOnlyStateStore(),
            execute_derived_data_lifecycle_event=lambda *_args, **_kwargs: None,
        )

        with self.assertRaisesRegex(
            NoOaBankBatchPersistenceError,
            "save_no_oa_bank_batch_mutation",
        ):
            service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=True)

    def test_after_mutation_without_persist_only_emits_lifecycle_event(self) -> None:
        lifecycle_events: list[dict[str, object]] = []

        class StateStore:
            def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
                raise AssertionError("persist=False must not save no-OA mutation snapshots")

        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(
                SimpleNamespace(snapshot=lambda: {}, snapshot_case_ids=lambda _case_ids: {})
            ),
            state_store=StateStore(),
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
        )

        changed = service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=False)

        self.assertTrue(changed)
        self.assertEqual(lifecycle_events[0]["event_type"], "no_oa_bank_batch_changed")
        self.assertEqual(lifecycle_events[0]["months"], ["2026-05"])

if __name__ == "__main__":
    unittest.main()
