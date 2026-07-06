from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchPairRelationSnapshotPort,
    BankBatchPersistenceError,
    BankBatchRelationMutationError,
)
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE, BankBatchService
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.bank_flow_rule_batch_read_model_refresh import (
    BankFlowRuleBatchReadModelPersistencePort,
    BankFlowRuleBatchReadModelRefreshService,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class RecordingStateStore:
    def __init__(self, *, bank_flow_batch_snapshot: dict[str, object] | None = None) -> None:
        self.bank_flow_mutations: list[dict[str, object]] = []
        self.bank_flow_snapshots: list[dict[str, object]] = []
        self.bank_flow_scopes: list[dict[str, object]] = []
        self.bank_flow_batch_snapshot = dict(bank_flow_batch_snapshot or {})
        self.load_bank_flow_batch_calls = 0

    def load_bank_flow_rule_batches(self) -> dict[str, object]:
        self.load_bank_flow_batch_calls += 1
        return dict(self.bank_flow_batch_snapshot)

    def save_bank_flow_rule_batch_mutation(self, **kwargs: object) -> None:
        self.bank_flow_mutations.append(dict(kwargs))

    def save_bank_flow_rule_batches(self, snapshot: dict[str, object]) -> None:
        self.bank_flow_snapshots.append(dict(snapshot))

    def save_bank_flow_rule_batches_scope(self, snapshot: dict[str, object], *, scope_key: str) -> None:
        self.bank_flow_scopes.append({"snapshot": dict(snapshot), "scope_key": scope_key})

    def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
        raise AssertionError("bank-flow mutation must not call no-OA persistence")

    def save_no_oa_bank_batches(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("bank-flow refresh must not call no-OA snapshot persistence")

    def save_no_oa_bank_batches_scope(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("bank-flow refresh must not call no-OA scoped persistence")


class RecordingPairSnapshotPort:
    def __init__(self) -> None:
        self.snapshot_calls = 0
        self.snapshot_case_id_calls: list[list[str]] = []

    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, object]:
        self.snapshot_case_id_calls.append(list(case_ids))
        return {"case_ids": list(case_ids), "pair_relations": {case_id: {"case_id": case_id} for case_id in case_ids}}

    def snapshot(self) -> dict[str, object]:
        self.snapshot_calls += 1
        return {"all": True}


class RecordingWorkbenchReadModelService:
    def snapshot(self) -> dict[str, object]:
        return {"workbench": True}


class RefreshAwareBatchService:
    def __init__(
        self,
        refresh_calls: list[dict[str, object]],
        *,
        requires_refresh_before_lookup: bool = False,
        status: str = "submitted",
    ) -> None:
        self._refresh_calls = refresh_calls
        self._requires_refresh_before_lookup = requires_refresh_before_lookup
        self._status = status
        self._snapshot_batches: dict[str, dict[str, object]] = {}
        self.submit_calls: list[dict[str, object]] = []
        self.withdraw_calls: list[dict[str, object]] = []

    def get_batch(self, batch_id: str) -> dict[str, object]:
        if batch_id in self._snapshot_batches:
            return dict(self._snapshot_batches[batch_id])
        if self._requires_refresh_before_lookup and not self._refresh_calls:
            raise KeyError("stale_runtime_snapshot")
        return {
            "batch_id": batch_id,
            "batch_type": "fee",
            "batch_label": "手续费",
            "status": self._status,
            "status_bucket": "submitted" if self._status == "submitted" else "unsubmitted",
            "version": 2,
            "row_ids": ["bank-1"],
            "row_count": 1,
            "relation_case_id": batch_id,
            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
        }

    def snapshot(self) -> dict[str, object]:
        return {"batches": {}}

    def replace_snapshot(self, snapshot: dict[str, object]) -> None:
        batches = snapshot.get("batches") if isinstance(snapshot, dict) else None
        self._snapshot_batches = {
            str(batch_id): dict(batch)
            for batch_id, batch in dict(batches or {}).items()
            if isinstance(batch, dict)
        }

    def submit_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        note: str | None,
    ) -> dict[str, object]:
        self.submit_calls.append(
            {
                "batch_id": batch_id,
                "actor": actor,
                "expected_version": expected_version,
                "note": note,
            }
        )
        self._status = "submitted"
        if batch_id in self._snapshot_batches:
            self._snapshot_batches[batch_id] = {
                **self._snapshot_batches[batch_id],
                "status": "submitted",
                "status_bucket": "submitted",
            }
        return self.get_batch(batch_id)

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        self.withdraw_calls.append(
            {
                "batch_id": batch_id,
                "actor": actor,
                "expected_version": expected_version,
                "reason": reason,
            }
        )
        return {**self.get_batch(batch_id), "status": "withdrawn"}


class RecordingBankFlowRuleSettings:
    def __init__(self) -> None:
        self.updated_payloads: list[dict[str, object]] = []
        self.actors: list[str] = []

    def get_bank_flow_rule_batch_tag_rules_payload(self) -> dict[str, object]:
        return {"version": 7, "rules": [{"tag_code": "fee"}]}

    def update_bank_flow_rule_batch_tag_rules(
        self,
        payload: dict[str, object],
        *,
        actor_id: str,
    ) -> dict[str, object]:
        self.updated_payloads.append(dict(payload))
        self.actors.append(actor_id)
        return {
            "version": 8,
            "rules": [{"tag_code": "fee", "requires_oa": True, "requires_invoice": False}],
            "requirements_by_tag_code": {"fee": {"requires_oa": True, "requires_invoice": False}},
        }

    def update_no_oa_bank_batch_tag_selection(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("bank-flow tag rules must not use no-OA settings I/O")


class BankFlowRuleBatchApplicationServiceTests(unittest.TestCase):
    @staticmethod
    def _service_with_refresh_aware_batch(
        *,
        requires_refresh_before_lookup: bool = False,
        status: str = "submitted",
    ) -> tuple[
        BankFlowRuleBatchApplicationService,
        RefreshAwareBatchService,
        list[dict[str, object]],
    ]:
        refresh_calls: list[dict[str, object]] = []
        batch_service = RefreshAwareBatchService(
            refresh_calls,
            requires_refresh_before_lookup=requires_refresh_before_lookup,
            status=status,
        )
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = batch_service
        service._state_store = None
        service.refresh_batches = (  # type: ignore[method-assign]
            lambda **kwargs: refresh_calls.append(dict(kwargs)) or ([], {})
        )
        service._public_batch = lambda batch: dict(batch)  # type: ignore[method-assign]
        service.no_oa_bank_transaction_rows_by_ids = lambda _row_ids: []  # type: ignore[method-assign]
        service.effective_categories_for_rows = lambda _rows: {}  # type: ignore[method-assign]
        service._workbench_relation_rows_by_id = lambda _row_ids: {}  # type: ignore[method-assign]
        service.detail_rows = lambda *_args: []  # type: ignore[method-assign]
        service._apply_submitted_row_tag_snapshot = lambda _batch, rows: rows  # type: ignore[method-assign]
        service._apply_relation_status_to_detail_rows = (  # type: ignore[method-assign]
            lambda rows, _relations: rows
        )
        service._detail_categories_by_transaction_id = lambda *_args: {}  # type: ignore[method-assign]
        service._workbench_relation_source_versions = lambda: {}  # type: ignore[method-assign]
        service.resolve_labels = lambda batches: batches  # type: ignore[method-assign]
        service._pair_relation_snapshot_port = SimpleNamespace(snapshot=lambda: {}, restore=lambda _snapshot: None)
        service._cancel_relation_for_batch = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service._confirm_relation_for_batch = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service._mutation_result = lambda batch, **_kwargs: {"batch": dict(batch)}  # type: ignore[method-assign]
        return service, batch_service, refresh_calls

    def test_detail_uses_current_bank_flow_batch_without_all_scope_refresh(self) -> None:
        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch()

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(refresh_calls, [])

    def test_detail_falls_back_to_all_scope_refresh_when_batch_is_missing(self) -> None:
        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
        )

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(
            refresh_calls,
            [
                {
                    "apply_relation_repairs": False,
                    "scope_key": "all",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            ],
        )

    def test_detail_hydrates_missing_runtime_batch_from_read_model_without_all_refresh(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.filters: list[dict[str, object]] = []

            def list_bank_flow_rule_batch_rows(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.filters.append(dict(filters))
                return [
                    {
                        "batch_id": "batch-1",
                        "batch_type": "internal_transfer",
                        "status": "draft",
                        "status_bucket": "unsubmitted",
                        "version": 1,
                        "row_ids": ["bank-1", "bank-2"],
                        "row_count": 2,
                        "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    }
                ]

        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
            status="draft",
        )
        repository = Repository()
        service._bank_batch_read_model_repository = repository

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(repository.filters, [{"batch_id": "batch-1"}])
        self.assertEqual(refresh_calls, [])

    def test_withdraw_uses_current_bank_flow_batch_without_all_scope_refresh(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch()

        result = service.withdraw_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            reason="误提交",
        )

        self.assertEqual(result["batch"]["status"], "withdrawn")
        self.assertEqual(batch_service.withdraw_calls[0]["batch_id"], "batch-1")
        self.assertEqual(refresh_calls, [])

    def test_submit_uses_current_bank_flow_batch_without_all_scope_refresh(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch(status="draft")
        service._pair_relation_snapshot_port = SimpleNamespace(
            snapshot=lambda: (_ for _ in ()).throw(AssertionError("bank-flow submit must not snapshot all relations")),
            restore=lambda _snapshot: (_ for _ in ()).throw(AssertionError("bank-flow submit must not restore all relations")),
        )

        result = service.submit_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(batch_service.submit_calls[0]["batch_id"], "batch-1")
        self.assertEqual(refresh_calls, [])

    def test_submit_restores_persisted_snapshot_before_all_scope_refresh_when_runtime_missing(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
            status="draft",
        )
        state_store = RecordingStateStore(
            bank_flow_batch_snapshot={
                "batches": {
                    "batch-1": {
                        "batch_id": "batch-1",
                        "batch_type": "internal_transfer",
                        "batch_label": "内部往来款",
                        "status": "draft",
                        "status_bucket": "unsubmitted",
                        "version": 2,
                        "row_ids": ["bank-pay", "bank-receive"],
                        "row_count": 2,
                        "total_amount": "7000.00",
                        "relation_case_id": "batch-1",
                        "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    }
                },
                "audit_log": [],
            }
        )
        service._state_store = state_store

        result = service.submit_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(batch_service.submit_calls[0]["batch_id"], "batch-1")
        self.assertEqual(state_store.load_bank_flow_batch_calls, 1)
        self.assertEqual(refresh_calls, [])

    def test_submit_falls_back_to_all_scope_refresh_when_batch_is_missing(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
            status="draft",
        )

        result = service.submit_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(batch_service.submit_calls[0]["batch_id"], "batch-1")
        self.assertEqual(
            refresh_calls,
            [
                {
                    "apply_relation_repairs": False,
                    "scope_key": "all",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            ],
        )

    def test_submit_selected_bank_flow_rows_uses_row_scoped_inputs_without_all_refresh(self) -> None:
        class ImportService:
            def __init__(self) -> None:
                self.list_calls: list[str] = []
                self.get_calls: list[str] = []
                self.rows = {
                    "bank-row-1": {
                        "id": "bank-row-1",
                        "trade_time": "2026-06-03 10:20:00",
                        "account_key": "ccb:8106",
                        "bank_name": "建设银行",
                        "account_last4": "8106",
                        "direction": "expense",
                        "amount": "8.80",
                    },
                    "bank-row-2": {
                        "id": "bank-row-2",
                        "trade_time": "2026-06-04 10:20:00",
                        "account_key": "ccb:8106",
                        "bank_name": "建设银行",
                        "account_last4": "8106",
                        "direction": "expense",
                        "amount": "18.20",
                    },
                }

            def list_transactions(self, *, month: str = "all") -> list[dict[str, object]]:
                self.list_calls.append(month)
                raise AssertionError("selected bank-flow submit must not scan all transactions")

            def get_transaction(self, row_id: str) -> dict[str, object]:
                self.get_calls.append(row_id)
                return dict(self.rows[row_id])

        class CategoryProvider:
            def __init__(self) -> None:
                self.bulk_get_calls: list[list[str]] = []
                self.source_version_scope_calls: list[list[str]] = []

            def bulk_get_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
                row_ids = [str(row.get("id") or "") for row in rows]
                self.bulk_get_calls.append(row_ids)
                return {
                    row_id: {
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_primary_label": "费用",
                        "category_sub_label": "手续费",
                        "category_label_path": ["费用", "手续费"],
                        "category_source": "auto",
                    }
                    for row_id in row_ids
                }

            def source_versions_for_scope_keys(self, scope_keys: list[str], **_kwargs: object) -> dict[str, object]:
                self.source_version_scope_calls.append(list(scope_keys))
                return {
                    "source_versions": {
                        "bank_detail_schema_version": "bd-v1",
                        "row_count": 2,
                    }
                }

        class RelationFacade:
            def __init__(self) -> None:
                self.list_by_month_calls: list[str] = []
                self.source_version_month_calls: list[str] = []

            def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
                self.list_by_month_calls.append(month)
                return {}

            def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
                self.source_version_month_calls.append(month)
                return {"source_versions": {"workbench_relation_schema_version": "wr-v1"}}

        class Settings:
            def get_bank_flow_rule_batch_tag_rules_payload(self) -> dict[str, object]:
                return {
                    "version": 7,
                    "active_tags": [{"code": "fee"}],
                    "requirements_by_tag_code": {
                        "fee": {"requires_oa": False, "requires_invoice": False},
                    },
                }

        import_service = ImportService()
        category_provider = CategoryProvider()
        relation_facade = RelationFacade()
        confirm_calls: list[dict[str, object]] = []
        mutation_calls: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = BankBatchService()
        service._import_service = import_service
        service._effective_category_provider = category_provider
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {})
        service._app_settings_service = Settings()
        service._workbench_matching_source_versions_provider = lambda: {}
        service._relation_facade = relation_facade
        service._confirm_relation_for_batch = (  # type: ignore[method-assign]
            lambda batch, **kwargs: confirm_calls.append({"batch": dict(batch), **kwargs})
        )
        service._mutation_result = (  # type: ignore[method-assign]
            lambda batch, **kwargs: mutation_calls.append(dict(kwargs)) or {"batch": dict(batch)}
        )

        result = service.submit_selected_rows(
            row_ids=["bank-row-1", "bank-row-2"],
            actor="finance-user",
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(import_service.get_calls, ["bank-row-1", "bank-row-2"])
        self.assertEqual(import_service.list_calls, [])
        self.assertEqual(category_provider.bulk_get_calls, [["bank-row-1", "bank-row-2"]])
        self.assertEqual(category_provider.source_version_scope_calls, [["2026-06"]])
        self.assertEqual(relation_facade.list_by_month_calls, ["2026-06"])
        self.assertEqual(relation_facade.source_version_month_calls, ["2026-06"])
        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(result["batch"]["row_ids"], ["bank-row-1", "bank-row-2"])
        self.assertEqual(confirm_calls[0]["relation_mode"], BANK_FLOW_RULE_BATCH_RELATION_MODE)
        self.assertEqual(mutation_calls[0]["read_model_key"], BANK_FLOW_RULE_BATCH_RELATION_MODE)

    def test_submit_selected_bank_flow_internal_transfer_fails_fast_without_legacy_refresh(self) -> None:
        class ImportService:
            def __init__(self) -> None:
                self.get_calls: list[str] = []
                self.list_calls: list[object] = []

            def list_transactions(self, *, month: str = "all") -> list[dict[str, object]]:
                self.list_calls.append(month)
                raise AssertionError("bank-flow submit-selection must not enter legacy full refresh")

            def get_transaction(self, row_id: str) -> dict[str, object]:
                self.get_calls.append(row_id)
                return {
                    "id": row_id,
                    "trade_time": "2026-06-04 10:20:00",
                    "account_key": "ccb:8106",
                    "bank_name": "建设银行",
                    "account_last4": "8106",
                    "direction": "expense",
                    "amount": "18.20",
                }

        class CategoryProvider:
            def bulk_get_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
                row_ids = [str(row.get("id") or "") for row in rows]
                return {
                    row_id: {
                        "category_code": "internal_transfer",
                        "category_label": "内部往来款",
                        "category_primary_label": "内部往来款",
                        "category_sub_label": "",
                        "category_label_path": ["内部往来款"],
                        "category_source": "auto",
                    }
                    for row_id in row_ids
                }

        import_service = ImportService()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = BankBatchService()
        service._import_service = import_service
        service._effective_category_provider = CategoryProvider()
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {})

        with self.assertRaises(BankBatchRelationMutationError) as raised:
            service.submit_selected_rows(
                row_ids=["bank-row-1"],
                actor="finance-user",
                note="提交",
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            )

        self.assertEqual(
            raised.exception.error_code,
            "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
        )
        self.assertEqual(str(raised.exception), "内部往来批次请使用单批提交。")
        self.assertEqual(import_service.get_calls, ["bank-row-1"])
        self.assertEqual(import_service.list_calls, [])

    def test_mutation_rejects_non_bank_flow_relation_mode(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)

        with self.assertRaises(BankBatchRelationMutationError) as submit_batch_error:
            service.submit_batch(
                "batch-1",
                actor="finance-user",
                expected_version=1,
                note=None,
                relation_mode="no_oa_bank_batch",
            )
        self.assertEqual(submit_batch_error.exception.error_code, "invalid_bank_flow_rule_batch_relation_mode")

        with self.assertRaises(BankBatchRelationMutationError) as submit_selection_error:
            service.submit_selected_rows(
                row_ids=["bank-row-1"],
                actor="finance-user",
                note=None,
                relation_mode="no_oa_bank_batch",
            )
        self.assertEqual(submit_selection_error.exception.error_code, "invalid_bank_flow_rule_batch_relation_mode")

    def test_withdraw_uses_bank_flow_relation_mode_for_shared_mutation_boundary(self) -> None:
        service, _batch_service, _refresh_calls = self._service_with_refresh_aware_batch()
        cancel_calls: list[dict[str, object]] = []
        mutation_calls: list[dict[str, object]] = []

        def capture_cancel(*_args: object, **kwargs: object) -> None:
            cancel_calls.append(dict(kwargs))

        def capture_mutation(batch: dict[str, object], **kwargs: object) -> dict[str, object]:
            mutation_calls.append(dict(kwargs))
            return {"batch": dict(batch)}

        service._cancel_relation_for_batch = capture_cancel  # type: ignore[method-assign]
        service._mutation_result = capture_mutation  # type: ignore[method-assign]

        service.withdraw_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            reason="误提交",
        )

        self.assertEqual(cancel_calls[0]["history_operation_type"], "bank_flow_rule_batch_withdraw")
        self.assertEqual(mutation_calls[0]["read_model_key"], BANK_FLOW_RULE_BATCH_RELATION_MODE)

    def test_withdraw_falls_back_to_all_scope_refresh_when_batch_is_missing(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
        )

        result = service.withdraw_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            reason="误提交",
        )

        self.assertEqual(result["batch"]["status"], "withdrawn")
        self.assertEqual(batch_service.withdraw_calls[0]["batch_id"], "batch-1")
        self.assertEqual(
            refresh_calls,
            [
                {
                    "apply_relation_repairs": False,
                    "scope_key": "all",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            ],
        )

    def test_submitted_candidate_lookup_is_relation_mode_scoped(self) -> None:
        class BatchService:
            def __init__(self) -> None:
                self.filters: list[dict[str, object]] = []

            def list_batches(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.filters.append(dict(filters))
                return [{"batch_id": "batch-1", "status": "submitted"}]

        batch_service = BatchService()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = batch_service

        candidates = service._submitted_batches_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE)

        self.assertEqual(candidates, [{"batch_id": "batch-1", "status": "submitted"}])
        self.assertEqual(
            batch_service.filters,
            [{"bucket": "submitted", "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE}],
        )

    def test_reset_submitted_refreshes_affected_months_without_preflight_all_refresh(self) -> None:
        class BatchService:
            def __init__(self) -> None:
                self.withdrawn: list[str] = []

            def snapshot(self) -> dict[str, object]:
                return {"batches": {}}

            def list_batches(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.filters = dict(filters)
                return [
                    {
                        "batch_id": "batch-1",
                        "status": "submitted",
                        "version": 3,
                        "scope_month": "2026-05",
                        "row_count": 1,
                    }
                ]

            def get_batch(self, batch_id: str) -> dict[str, object]:
                return {
                    "batch_id": batch_id,
                    "status": "submitted",
                    "version": 3,
                    "scope_month": "2026-05",
                    "row_count": 1,
                }

            def withdraw_batch(
                self,
                batch_id: str,
                *,
                actor: str,
                expected_version: int,
                reason: str,
            ) -> dict[str, object]:
                self.withdrawn.append(batch_id)
                return {
                    "batch_id": batch_id,
                    "status": "withdrawn",
                    "version": expected_version + 1,
                    "scope_month": "2026-05",
                    "row_count": 1,
                }

        refresh_calls: list[dict[str, object]] = []
        batch_service = BatchService()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = batch_service
        service._pair_relation_snapshot_port = SimpleNamespace(snapshot=lambda: {}, restore=lambda _snapshot: None)
        service._cancel_relation_for_batch = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service.affected_months = lambda _batch: ["2026-05"]  # type: ignore[method-assign]
        service.refresh_batches = lambda **kwargs: refresh_calls.append(dict(kwargs)) or ([], {})  # type: ignore[method-assign]
        service.after_mutation = lambda *_args, **_kwargs: True  # type: ignore[method-assign]
        service._expand_workbench_read_model_scope_keys_for_base_scopes = lambda scope_keys: scope_keys

        result = service.reset_submitted_bank_flow_rule_batches(actor="finance-user", reason="重置")

        self.assertEqual(result["summary"]["reset_count"], 1)
        self.assertEqual(batch_service.withdrawn, ["batch-1"])
        self.assertEqual(
            refresh_calls,
            [{"relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE, "scope_key": "2026-05"}],
        )

    def test_persist_mutation_uses_bank_flow_state_store_boundary(self) -> None:
        state_store = RecordingStateStore()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = state_store
        service._search_cache_clearer = lambda: None
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._workbench_read_model_service = SimpleNamespace(
            snapshot=lambda: (_ for _ in ()).throw(AssertionError("bank-flow persist must not snapshot workbench read model"))
        )
        service._bank_batch_public_snapshot = lambda: {"batches": {"batch-1": {"batch_id": "batch-1"}}}

        service.persist_mutation(changed_case_ids=["case-1"], changed_scope_keys=["2026-05"])

        self.assertEqual(len(state_store.bank_flow_mutations), 1)
        mutation = state_store.bank_flow_mutations[0]
        self.assertEqual(
            mutation["pair_relation_snapshot"],
            {"case_ids": ["case-1"], "pair_relations": {"case-1": {"case_id": "case-1"}}},
        )
        self.assertEqual(mutation["bank_flow_rule_batch_snapshot"], {"batches": {"batch-1": {"batch_id": "batch-1"}}})
        self.assertNotIn("workbench_read_model_snapshot", mutation)
        self.assertEqual(mutation["changed_case_ids"], ["case-1"])
        self.assertEqual(mutation["changed_scope_keys"], ["2026-05"])

    def test_persist_mutation_fails_fast_without_bank_flow_boundary(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = object()
        service._search_cache_clearer = lambda: None
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._workbench_read_model_service = RecordingWorkbenchReadModelService()
        service._bank_batch_public_snapshot = lambda: {"batches": {}}

        with self.assertRaises(BankBatchPersistenceError):
            service.persist_mutation(changed_case_ids=[], changed_scope_keys=["all"])

    def test_after_mutation_skips_legacy_lifecycle_for_online_submit(self) -> None:
        lifecycle_events: list[dict[str, object]] = []
        persist_calls: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._execute_derived_data_lifecycle_event = (  # type: ignore[method-assign]
            lambda event_type, **kwargs: lifecycle_events.append({"event_type": event_type, **kwargs})
        )
        service._expand_workbench_read_model_scope_keys_for_base_scopes = (  # type: ignore[method-assign]
            lambda scope_keys: [f"expanded:{scope_key}" for scope_key in scope_keys]
        )
        service.persist_mutation = (  # type: ignore[method-assign]
            lambda **kwargs: persist_calls.append(dict(kwargs))
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month"],
            changed_case_ids=["case-1"],
            persist=True,
            action_name="bank_flow_rule_batch_submit",
        )

        self.assertTrue(changed)
        self.assertEqual(lifecycle_events, [])
        self.assertEqual(
            persist_calls,
            [
                {
                    "changed_case_ids": ["case-1"],
                    "changed_scope_keys": ["all", "2026-05"],
                }
            ],
        )

    def test_after_mutation_keeps_lifecycle_for_rule_changes(self) -> None:
        lifecycle_events: list[dict[str, object]] = []
        persist_calls: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._execute_derived_data_lifecycle_event = (  # type: ignore[method-assign]
            lambda event_type, **kwargs: lifecycle_events.append({"event_type": event_type, **kwargs})
        )
        service.persist_mutation = (  # type: ignore[method-assign]
            lambda **kwargs: persist_calls.append(dict(kwargs))
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month"],
            changed_case_ids=[],
            persist=False,
            action_name="bank_flow_rule_batch_tag_rules_changed",
        )

        self.assertTrue(changed)
        self.assertEqual(
            lifecycle_events,
            [
                {
                    "event_type": "bank_flow_rule_batch_changed",
                    "months": ["2026-05"],
                    "metadata": {
                        "source": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                        "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                        "action_name": "bank_flow_rule_batch_tag_rules_changed",
                    },
                    "schedule_cost_warmup": False,
                }
            ],
        )
        self.assertEqual(persist_calls, [])

    def test_after_mutation_does_not_expand_workbench_scope_keys(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)
        persist_calls: list[dict[str, object]] = []
        service._execute_derived_data_lifecycle_event = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service._expand_workbench_read_model_scope_keys_for_base_scopes = (  # type: ignore[method-assign]
            lambda _scope_keys: (_ for _ in ()).throw(AssertionError("bank-flow mutation must not list workbench scopes"))
        )
        service.persist_mutation = lambda **kwargs: persist_calls.append(dict(kwargs))  # type: ignore[method-assign]

        service.after_mutation(
            ["2026-05"],
            changed_case_ids=["case-1"],
            persist=True,
            action_name="bank_flow_rule_batch_submit",
        )

        self.assertEqual(persist_calls, [{"changed_case_ids": ["case-1"], "changed_scope_keys": ["all", "2026-05"]}])

    def test_pair_relation_snapshot_by_case_id_uses_scoped_snapshot(self) -> None:
        pair_service = RecordingPairSnapshotPort()
        port = BankBatchPairRelationSnapshotPort(pair_service)

        relation = port.snapshot_by_case_id("case-1")

        self.assertEqual(relation, {"case_id": "case-1"})
        self.assertEqual(pair_service.snapshot_case_id_calls, [["case-1"]])
        self.assertEqual(pair_service.snapshot_calls, 0)

    def test_refresh_persistence_uses_bank_flow_scope_boundary(self) -> None:
        state_store = RecordingStateStore()
        port = BankFlowRuleBatchReadModelPersistencePort(state_store)

        port.save_public_snapshot({"batches": {}}, scope_key="2026-05")

        self.assertEqual(state_store.bank_flow_scopes, [{"snapshot": {"batches": {}}, "scope_key": "2026-05"}])
        self.assertEqual(state_store.bank_flow_snapshots, [])

    def test_tag_selection_payload_reads_bank_flow_rule_settings_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings

        payload = service.tag_selection_payload()

        self.assertEqual(payload, {"version": 7, "rules": [{"tag_code": "fee"}]})

    def test_update_tag_selection_uses_bank_flow_rule_settings_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._sync_bank_flow_rule_relation_requirements = (  # type: ignore[method-assign]
            lambda payload, *, actor_id: {"changed_case_ids": [], "affected_months": []}
        )
        service._sync_turnover_rule_relation_requirements = (  # type: ignore[method-assign]
            lambda payload, *, actor_id: {"changed_case_ids": [], "affected_months": []}
        )
        service.after_mutation = lambda *_args, **_kwargs: False  # type: ignore[method-assign]
        service.enqueue_background_refresh = lambda *_args, **_kwargs: True  # type: ignore[method-assign]
        service._read_model_refresh_metadata_for_relation_mode = (  # type: ignore[method-assign]
            lambda relation_mode: {"relation_mode": relation_mode}
        )

        result = service.update_tag_selection(
            {"expected_version": 7, "rules": [{"tag_code": "fee"}]},
            actor_id="finance-user",
        )

        self.assertEqual(settings.updated_payloads, [{"expected_version": 7, "rules": [{"tag_code": "fee"}]}])
        self.assertEqual(settings.actors, ["finance-user"])
        self.assertEqual(result["version"], 8)

    def test_bank_flow_source_versions_use_bank_flow_rule_version_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._workbench_matching_source_versions_provider = lambda: {"workbench_matching_rules_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {"version": 3})
        service._effective_category_provider = SimpleNamespace(last_source_versions={})
        service._relation_facade = SimpleNamespace(last_source_versions={})

        versions = service.no_oa_bank_batch_source_versions(
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(versions["bank_flow_rule_batch_tag_rules_version"], 7)
        self.assertIn("bank_flow_rule_batch_schema_version", versions)
        self.assertNotIn("no_oa_bank_batch_tag_selection_version", versions)

    def test_bank_flow_scope_source_versions_use_probe_ports_before_row_loading(self) -> None:
        settings = RecordingBankFlowRuleSettings()

        class EffectiveCategoryProvider:
            last_source_versions: dict[str, object] = {}

            def __init__(self) -> None:
                self.source_version_calls: list[list[str]] = []

            def bulk_get_for_rows(self, _rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
                raise AssertionError("source-version precheck must not load bank detail rows")

            def source_versions_for_scope_keys(self, scope_keys: list[str], **_kwargs: object) -> dict[str, object]:
                self.source_version_calls.append(list(scope_keys))
                return {
                    "status": "fresh",
                    "source_versions": {
                        "bank_detail_schema_version": 8,
                        "row_count": 100,
                        "source_version": 12,
                    },
                }

        class RelationFacade:
            last_source_versions: dict[str, object] = {}

            def __init__(self) -> None:
                self.source_version_calls: list[str] = []

            def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("source-version precheck must not load relation rows")

            def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
                self.source_version_calls.append(month)
                return {
                    "status": "fresh",
                    "source_versions": {
                        "scope_key": month,
                        "relation_signature": "relation-v1",
                    },
                }

        provider = EffectiveCategoryProvider()
        relation_facade = RelationFacade()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._workbench_matching_source_versions_provider = lambda: {"workbench_matching_rules_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {"version": 3})
        service._effective_category_provider = provider
        service._relation_facade = relation_facade

        versions = service.read_model_scope_source_versions(
            scope_key="2026-02",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(provider.source_version_calls, [["2026-02"]])
        self.assertEqual(relation_facade.source_version_calls, ["2026-02"])
        self.assertEqual(versions["bank_flow_rule_batch_tag_rules_version"], 7)
        self.assertEqual(
            versions["bank_detail_source_versions"],
            {
                "bank_detail_schema_version": 8,
                "row_count": 100,
            },
        )
        self.assertEqual(
            versions["workbench_relation_source_versions"],
            {
                "scope_key": "2026-02",
                "relation_signature": "relation-v1",
            },
        )
        self.assertEqual(service.bank_row_count_from_source_versions(versions), 100)

    def test_bank_flow_list_freshness_uses_scope_source_versions(self) -> None:
        settings = RecordingBankFlowRuleSettings()

        class EffectiveCategoryProvider:
            last_source_versions = {
                "bank_detail_schema_version": 8,
                "row_count": 999,
            }

            def __init__(self) -> None:
                self.source_version_calls: list[list[str]] = []

            def source_versions_for_scope_keys(self, scope_keys: list[str], **_kwargs: object) -> dict[str, object]:
                self.source_version_calls.append(list(scope_keys))
                return {
                    "status": "fresh",
                    "source_versions": {
                        "bank_detail_schema_version": 8,
                        "row_count": 4,
                        "source_version": 12,
                    },
                }

        class RelationFacade:
            last_source_versions = {
                "scope_key": "wrong",
                "relation_signature": "wrong",
            }

            def __init__(self) -> None:
                self.source_version_calls: list[str] = []

            def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
                self.source_version_calls.append(month)
                return {
                    "status": "fresh",
                    "source_versions": {
                        "scope_key": month,
                        "relation_signature": "relation-v1",
                    },
                }

        provider = EffectiveCategoryProvider()
        relation_facade = RelationFacade()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._workbench_matching_source_versions_provider = lambda: {"workbench_matching_rules_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(
            snapshot=lambda: {"version": 3},
            tag_dictionary_payload=lambda: {
                "definitions": [
                    {
                        "code": "fee",
                        "label": "手续费",
                        "output_primary_label": "费用",
                        "output_sub_label": "手续费",
                    }
                ]
            },
        )
        service._effective_category_provider = provider
        service._relation_facade = relation_facade
        expected_versions = service.read_model_scope_source_versions(
            scope_key="2026-07",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        row = {
            "batch_id": "batch-1",
            "batch_type": "fee",
            "scope_month": "2026-07",
            "status": "draft",
            "status_bucket": "unsubmitted",
            "row_count": 4,
            "total_amount": "12.00",
            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
            "source_versions": expected_versions,
        }

        class Repository:
            def __init__(self) -> None:
                self.filters: list[dict[str, object]] = []

            def list_bank_flow_rule_batch_rows(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.filters.append(dict(filters))
                return [dict(row)]

        repository = Repository()
        service._bank_batch_read_model_repository = repository
        service._bank_batch_service = SimpleNamespace(list_batches=lambda _filters: [])
        service.enqueue_background_refresh = (  # type: ignore[method-assign]
            lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fresh read model must not enqueue refresh"))
        )

        payload = service.list_batches_payload(
            {"month": ["2026-07"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(len(payload["batches"]), 1)
        self.assertEqual(provider.source_version_calls, [["2026-07"], ["2026-07"]])
        self.assertEqual(relation_facade.source_version_calls, ["2026-07", "2026-07", "2026-07"])
        self.assertEqual(
            repository.filters,
            [
                {"month": "2026-07", "account_key": "", "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE},
                {
                    "month": "2026-07",
                    "type": "",
                    "status": "",
                    "bucket": "",
                    "account_key": "",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                },
            ],
        )

    def test_bank_flow_refresh_publishes_prechecked_scope_source_versions(self) -> None:
        class ImportService:
            def list_transactions(self, *, month: str = "all") -> list[dict[str, object]]:
                self.month = month
                return [
                    {
                        "id": "bank-1",
                        "txn_date": "2026-07-01",
                        "txn_direction": "outflow",
                        "amount": "12.00",
                        "bank_name": "CCB",
                        "account_no": "6222000000008106",
                        "counterparty_name": "供应商",
                    }
                ]

        class EffectiveCategoryProvider:
            def __init__(self) -> None:
                self.last_source_versions = {
                    "bank_detail_schema_version": 8,
                    "row_count": 999,
                    "source_version": 50,
                }

            def source_versions_for_scope_keys(self, scope_keys: list[str], **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "fresh",
                    "source_versions": {
                        "bank_detail_schema_version": 8,
                        "row_count": 1,
                        "source_version": 51,
                    },
                }

            def bulk_get_for_rows(self, rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
                self.last_source_versions = {
                    "bank_detail_schema_version": 8,
                    "row_count": 999,
                    "source_version": 52,
                }
                return {
                    str(row["id"]): {
                        "transaction_id": row["id"],
                        "category_code": "fee",
                        "category_label": "手续费",
                        "category_source": "auto",
                    }
                    for row in rows
                }

        class RelationFacade:
            def source_versions_for_month(self, month: str, **_kwargs: object) -> dict[str, object]:
                return {
                    "status": "fresh",
                    "source_versions": {
                        "scope_key": month,
                        "relation_signature": "relation-v1",
                    },
                }

            def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {"rows": [], "groups": []}

        class Repository:
            def bank_flow_rule_batch_source_versions_summary(
                self,
                _filters: dict[str, object],
            ) -> dict[str, object]:
                return {
                    "read_model_status": "fresh",
                    "row_count": 1,
                    "source_versions": {"different": "version"},
                }

        class StateStore:
            bank_flow_rule_batch_sql_read_repository = Repository()

        class QueueRepository:
            def __init__(self) -> None:
                self.completions: list[dict[str, object]] = []

            def read_model_refresh_is_current(self, **_kwargs: object) -> bool:
                return True

            def complete_read_model_refresh(self, **kwargs: object) -> None:
                self.completions.append(dict(kwargs))

        class BatchService:
            def __init__(self) -> None:
                self.published_source_versions: dict[str, object] = {}
                self._snapshot: dict[str, object] = {"batches": {}}

            def build_batches(self, *_args: object, **_kwargs: object) -> None:
                self.published_source_versions = dict(_args[3])
                self._snapshot = {
                    "batches": {
                        "batch-1": {
                            "batch_id": "batch-1",
                            "batch_type": "fee",
                            "status": "draft",
                            "scope_month": "2026-07",
                            "source_versions": self.published_source_versions,
                        }
                    }
                }

            def public_snapshot(self) -> dict[str, object]:
                return dict(self._snapshot)

            def last_legacy_migration_result(self) -> dict[str, object]:
                return {"changed": False}

        class Persistence:
            def __init__(self) -> None:
                self.saved: list[dict[str, object]] = []

            def save_public_snapshot(
                self,
                snapshot: dict[str, object],
                *,
                scope_key: str = "all",
                relation_mode: str = BANK_FLOW_RULE_BATCH_RELATION_MODE,
            ) -> None:
                self.saved.append(
                    {
                        "scope_key": scope_key,
                        "relation_mode": relation_mode,
                        "snapshot": dict(snapshot),
                    }
                )

        batch_service = BatchService()
        persistence = Persistence()
        queue = QueueRepository()
        service = BankFlowRuleBatchReadModelRefreshService(
            import_service=ImportService(),
            effective_category_provider=EffectiveCategoryProvider(),
            bank_batch_service=batch_service,
            app_settings_service=RecordingBankFlowRuleSettings(),
            bank_transaction_category_service=SimpleNamespace(snapshot=lambda: {}),
            pair_relation_service=SimpleNamespace(snapshot=lambda: {}),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=StateStore(),
            read_model_persistence=persistence,
            queue_repository=queue,
            workbench_matching_source_versions_provider=lambda: {"workbench_matching_rules_version": "rules-v1"},
            relation_facade=RelationFacade(),
        )

        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-bank-flow-refresh",
                tenant_id="default",
                event_type="bank_flow_rule_batch.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="2026-07",
                scope_type="bank_flow_rule_batch",
                scope_key="2026-07",
                dedupe_key="bank_flow_rule_batch.read_model.refresh:bank_flow_rule_batch:2026-07",
                payload={
                    "scope_type": "bank_flow_rule_batch",
                    "scope_key": "2026-07",
                    "source_version": 9,
                    "metadata": {"relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE},
                },
                attempts=1,
                status="processing",
                source_version=9,
            )
        )

        self.assertEqual(result["scope_key"], "2026-07")
        self.assertEqual(
            batch_service.published_source_versions["bank_detail_source_versions"],
            {
                "bank_detail_schema_version": 8,
                "row_count": 1,
            },
        )
        self.assertEqual(
            persistence.saved[0]["snapshot"]["batches"]["batch-1"]["source_versions"],
            batch_service.published_source_versions,
        )
        self.assertEqual(
            queue.completions,
            [
                {
                    "tenant_id": "default",
                    "scope_type": "bank_flow_rule_batch",
                    "scope_key": "2026-07",
                    "source_version": 9,
                }
            ],
        )

    def test_unchanged_read_model_scope_uses_bank_flow_source_version_summary(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.filters: list[dict[str, object]] = []

            def bank_flow_rule_batch_source_versions_summary(
                self,
                filters: dict[str, object],
            ) -> dict[str, object]:
                self.filters.append(dict(filters))
                return {
                    "read_model_status": "fresh",
                    "row_count": 4,
                    "source_versions": {"bank_flow_rule_batch_tag_rules_version": 7},
                }

            def no_oa_bank_batch_source_versions_summary(self, _filters: dict[str, object]) -> dict[str, object]:
                raise AssertionError("bank-flow unchanged check must not use no-OA source summary")

            def list_bank_flow_rule_batch_rows(self, _filters: dict[str, object]) -> list[dict[str, object]]:
                raise AssertionError("source summary should avoid bank-flow row scan")

        repository = Repository()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_read_model_repository = repository

        result = service.unchanged_read_model_scope_result(
            scope_key="2026-05",
            source_versions={"bank_flow_rule_batch_tag_rules_version": 7},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(
            result,
            {
                "scope_key": "2026-05",
                "batch_count": 4,
                "source_versions": {"bank_flow_rule_batch_tag_rules_version": 7},
                "skipped": True,
                "skip_reason": "source_versions_unchanged",
            },
        )
        self.assertEqual(repository.filters, [{"month": "2026-05"}])

    def test_unchanged_read_model_scope_requires_fresh_status_by_default(self) -> None:
        class Repository:
            def bank_flow_rule_batch_source_versions_summary(
                self,
                filters: dict[str, object],
            ) -> dict[str, object]:
                return {
                    "read_model_status": "refreshing",
                    "row_count": 4,
                    "source_versions": {"bank_flow_rule_batch_tag_rules_version": 7},
                }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_read_model_repository = Repository()

        default_result = service.unchanged_read_model_scope_result(
            scope_key="2026-05",
            source_versions={"bank_flow_rule_batch_tag_rules_version": 7},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        worker_result = service.unchanged_read_model_scope_result(
            scope_key="2026-05",
            source_versions={"bank_flow_rule_batch_tag_rules_version": 7},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            allow_refreshing_read_model_status=True,
        )

        self.assertIsNone(default_result)
        self.assertEqual(worker_result["skip_reason"], "source_versions_unchanged")


if __name__ == "__main__":
    unittest.main()
