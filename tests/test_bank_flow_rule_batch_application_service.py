from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.bank_batch_application_service import BankBatchPairRelationSnapshotPort, BankBatchPersistenceError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.bank_flow_rule_batch_read_model_refresh import BankFlowRuleBatchReadModelPersistencePort


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
