from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
import unittest

from fin_ops_platform.services.no_oa_bank_batch_application_service import NoOaBankBatchApplicationService
from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


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
            "status": "fresh",
            "read_model_scope_keys": [str(kwargs.get("month_scope") or "all")],
            "stale_reasons": [],
            "refresh_enqueued": False,
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
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": [relation["month_scope"]],
            "refresh_enqueued": False,
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
            "read_model_status": "fresh",
            "read_model_stale_reasons": [],
            "read_model_scope_keys": ["2026-03"],
            "refresh_enqueued": False,
            "idempotent_replay": False,
        }


class EmptyWorkbenchRelationFacade:
    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": {"schema_version": 52},
            "read_model_scope_keys": [month],
        }

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": {"schema_version": 52},
            "read_model_scope_keys": ["2026-03"],
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
    labels = {"fee": "手续费", "internal_transfer": "内部往来款"}
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
            pair_relation_service=pair_service,
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=None,
            relation_facade=EmptyWorkbenchRelationFacade(),
            relation_command_service=command_service,
        )
        return service, no_oa_service, command_service

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
        self.assertEqual(call["display_tags"], ["免OA", "手续费"])

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
            pair_relation_service=SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            ),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {"workbench": "snapshot"}),
            state_store=state_store,
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
            expand_workbench_read_model_scope_keys_for_base_scopes=lambda scope_keys: [
                f"expanded:{scope_key}" for scope_key in scope_keys
            ],
            search_cache_clearer=lambda: cache_clears.append("search"),
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month", "2026-06"],
            changed_case_ids=["case-001", "case-002"],
            persist=True,
        )

        self.assertTrue(changed)
        self.assertEqual(
            lifecycle_events,
            [
                {
                    "event_type": "no_oa_bank_batch_changed",
                    "months": ["2026-05", "2026-06"],
                    "metadata": {"source": "no_oa_bank_batch"},
                    "schedule_cost_warmup": False,
                }
            ],
        )
        self.assertEqual(cache_clears, ["search"])
        self.assertEqual(len(state_store.saved_mutations), 1)
        saved = state_store.saved_mutations[0]
        self.assertEqual(saved["changed_case_ids"], ["case-001", "case-002"])
        self.assertEqual(saved["changed_scope_keys"], ["expanded:all", "expanded:2026-05", "expanded:2026-06"])
        self.assertEqual(saved["pair_relation_snapshot"], {"relations": ["case-001", "case-002"]})
        self.assertEqual(saved["no_oa_bank_batch_snapshot"], {"batches": {}})
        self.assertEqual(saved["workbench_read_model_snapshot"], {"workbench": "snapshot"})

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
            pair_relation_service=SimpleNamespace(snapshot=lambda: {}, snapshot_case_ids=lambda _case_ids: {}),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=StateStore(),
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
        )

        changed = service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=False)

        self.assertTrue(changed)
        self.assertEqual(lifecycle_events[0]["event_type"], "no_oa_bank_batch_changed")
        self.assertEqual(lifecycle_events[0]["months"], ["2026-05"])

    def test_enqueue_background_refresh_uses_durable_queue_boundary(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queue = QueueRepository()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_service=SimpleNamespace(),
            workbench_read_model_service=SimpleNamespace(),
            state_store=None,
            queue_repository=queue,
        )

        enqueued = service.enqueue_background_refresh(["all", "", "2026-05"], reason="unit_test")

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.enqueued,
            [
                {"scope_type": "no_oa_bank_batch", "scope_key": "all", "reason": "unit_test"},
                {"scope_type": "no_oa_bank_batch", "scope_key": "2026-05", "reason": "unit_test"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
