from __future__ import annotations

import unittest
from types import SimpleNamespace

from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchPairRelationSnapshotPort,
    BankBatchPersistenceError,
    BankBatchRelationMutationError,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchService,
)
from fin_ops_platform.services.bank_flow_rule_batch_application_service import (
    BankFlowRuleBatchApplicationService,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)


class RecordingStateStore:
    def __init__(self, *, bank_flow_batch_snapshot: dict[str, object] | None = None) -> None:
        self.bank_flow_mutations: list[dict[str, object]] = []
        self.bank_flow_batch_snapshot = dict(bank_flow_batch_snapshot or {})
        self.load_bank_flow_batch_calls = 0

    def load_bank_flow_rule_batches(self) -> dict[str, object]:
        self.load_bank_flow_batch_calls += 1
        return dict(self.bank_flow_batch_snapshot)

    def save_bank_flow_rule_batch_mutation(self, **kwargs: object) -> None:
        self.bank_flow_mutations.append(dict(kwargs))

    def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
        raise AssertionError("bank-flow mutation must not call no-OA persistence")

    def save_no_oa_bank_batches(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("bank-flow refresh must not call no-OA snapshot persistence")

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
        self.accepted_updates: list[dict[str, object]] = []

    def get_bank_flow_rule_batch_tag_rules_payload(self) -> dict[str, object]:
        return {
            "version": 7,
            "active_tags": [{"code": "fee", "status": "active"}],
            "rules": [{"tag_code": "fee", "requires_oa": True, "requires_invoice": False}],
            "requirements_by_tag_code": {
                "fee": {"requires_oa": True, "requires_invoice": False},
            },
        }

    def normalize_bank_flow_rule_batch_tag_rules_update(
        self,
        payload: dict[str, object],
        *,
        actor_id: str,
    ) -> dict[str, object]:
        self.updated_payloads.append(dict(payload))
        self.actors.append(actor_id)
        return {
            "changed": True,
            "previous_snapshot": {"bank_flow_rule_batch_tag_rules": {"version": 7}},
            "next_snapshot": {"bank_flow_rule_batch_tag_rules": {"version": 8}},
            "previous_public_payload": self.get_bank_flow_rule_batch_tag_rules_payload(),
            "public_payload": {
                "version": 8,
                "active_tags": [{"code": "fee", "status": "active"}],
                "rules": [{"tag_code": "fee", "requires_oa": False, "requires_invoice": False}],
                "requirements_by_tag_code": {
                    "fee": {"requires_oa": False, "requires_invoice": False},
                },
            },
            "audit_event": {"old_version": 7, "new_version": 8},
        }

    def accept_bank_flow_rule_batch_tag_rules_update(self, **kwargs: object) -> None:
        self.accepted_updates.append(dict(kwargs))

    def update_no_oa_bank_batch_tag_selection(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("bank-flow tag rules must not use no-OA settings I/O")


class RecordingTransaction:
    def __init__(self) -> None:
        self.exited_with: type[BaseException] | None = None

    def __enter__(self) -> "RecordingTransaction":
        return self

    def __exit__(self, exc_type, _exc, _tb) -> None:
        self.exited_with = exc_type


class RecordingTransactionConnection:
    def __init__(self) -> None:
        self.recording_transaction = RecordingTransaction()

    def transaction(self) -> RecordingTransaction:
        return self.recording_transaction


class BankFlowRuleBatchApplicationServiceTests(unittest.TestCase):
    def test_bank_flow_domain_contract_uses_new_namespace_and_keeps_historical_ids_readable(self) -> None:
        historical_id = "no_oa_batch_historical"
        service = BankBatchService(
            batches={
                historical_id: {
                    "batch_id": historical_id,
                    "batch_type": "fee",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "version": 2,
                    "scope_month": "2026-07",
                    "row_ids": ["bank-1"],
                    "row_count": 1,
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            },
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(service.snapshot()["schema_version"], BANK_FLOW_RULE_BATCH_SCHEMA_VERSION)
        self.assertTrue(service._batch_id("fee|2026-07|acct").startswith(BANK_FLOW_RULE_BATCH_ID_PREFIX))
        self.assertEqual(service.get_batch(historical_id)["batch_id"], historical_id)
        with self.assertRaisesRegex(ValueError, "bank_flow_rule_batch_version_conflict"):
            service.submit_batch(
                historical_id,
                actor="finance-user",
                expected_version=1,
                note="提交",
            )

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
        canonical_batch = {
            "batch_id": "batch-1",
            "batch_type": "fee",
            "batch_label": "手续费",
            "status": status,
            "status_bucket": "submitted" if status == "submitted" else "unsubmitted",
            "version": 2,
            "row_ids": ["bank-1"],
            "row_count": 1,
            "relation_case_id": "batch-1",
            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
        }
        service._query_repository = SimpleNamespace(
            read_batch=lambda batch_id: (
                {**canonical_batch, "batch_id": batch_id}
                if batch_id == "batch-1"
                else None
            ),
            read_detail=lambda batch_id: (
                {
                    "batch": {**canonical_batch, "batch_id": batch_id},
                    "rows": [],
                    "events": [],
                    "tag_policy": {"active_tags": []},
                }
                if batch_id == "batch-1"
                else None
            ),
            read_submitted_batches=lambda: (
                [dict(canonical_batch)]
                if status == "submitted"
                else []
            ),
        )
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
        service.resolve_labels = lambda batches, **_kwargs: batches  # type: ignore[method-assign]
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

    def test_detail_reads_canonical_repository_when_runtime_batch_is_missing(self) -> None:
        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
        )

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(refresh_calls, [])

    def test_detail_reads_canonical_repository_without_projection_refresh(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.batch_ids: list[str] = []

            def read_detail(self, batch_id: str) -> dict[str, object]:
                self.batch_ids.append(batch_id)
                return {
                    "batch": {
                        "batch_id": "batch-1",
                        "batch_type": "internal_transfer",
                        "status": "draft",
                        "status_bucket": "unsubmitted",
                        "version": 1,
                        "row_ids": ["bank-1", "bank-2"],
                        "row_count": 2,
                        "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                    },
                    "rows": [],
                    "events": [],
                    "tag_policy": {"active_tags": []},
                }

        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch(
            requires_refresh_before_lookup=True,
            status="draft",
        )
        repository = Repository()
        service._query_repository = repository

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(repository.batch_ids, ["batch-1"])
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
                self.source_proof_calls: list[list[str]] = []

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

            def canonical_category_source_proof_for_rows(
                self,
                rows: list[dict[str, object]],
            ) -> dict[str, object]:
                self.source_proof_calls.append(
                    [str(row.get("id") or "") for row in rows]
                )
                return {
                    "source": "canonical_bank_transaction_categories",
                    "row_count": len(rows),
                    "membership_category_digest": "category-v1",
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

        class RelationSourceRepository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def workbench_relation_source_bundle_from_source(
                self,
                *,
                scope_key: str,
                row_ids: list[str],
            ) -> dict[str, object]:
                self.calls.append({"scope_key": scope_key, "row_ids": list(row_ids)})
                return {
                    "rows": [],
                    "source_versions": {
                        "source": "workbench_pair_relations",
                        "scope_key": scope_key,
                        "relation_count": 0,
                        "relation_updated_at": "",
                    },
                }

        class Settings:
            def get_bank_flow_rule_batch_tag_rules_payload(self) -> dict[str, object]:
                return {
                    "version": 7,
                    "active_tags": [{"code": "fee"}],
                    "requirements_by_tag_code": {
                        "fee": {"requires_oa": True, "requires_invoice": True},
                    },
                }

        import_service = ImportService()
        category_provider = CategoryProvider()
        relation_facade = RelationFacade()
        relation_source_repository = RelationSourceRepository()
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
        service._relation_source_repository = relation_source_repository
        service._confirm_relation_for_batch = (  # type: ignore[method-assign]
            lambda batch, **kwargs: confirm_calls.append({"batch": dict(batch), **kwargs})
        )
        service._mutation_result = (  # type: ignore[method-assign]
            lambda batch, **kwargs: mutation_calls.append(dict(kwargs)) or {"batch": dict(batch)}
        )
        service._live_selected_rows = (  # type: ignore[method-assign]
            lambda _row_ids, *, scope_month: (
                [dict(import_service.rows["bank-row-1"]), dict(import_service.rows["bank-row-2"])],
                {
                    "bank-row-1": {"category_code": "fee", "effective_category_code": "fee"},
                    "bank-row-2": {"category_code": "fee", "effective_category_code": "fee"},
                },
                {
                    "active_relations": [],
                    "tag_policy": {
                        "version": 11,
                        "active_tags": [{"code": "fee"}],
                        "requirements_by_tag_code": {
                            "fee": {"requires_oa": False, "requires_invoice": False},
                        },
                    },
                },
            )
        )

        result = service.submit_selected_rows(
            row_ids=["bank-row-1", "bank-row-2"],
            actor="finance-user",
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            scope_month="2026-06",
        )

        self.assertEqual(import_service.get_calls, [])
        self.assertEqual(import_service.list_calls, [])
        self.assertEqual(category_provider.source_proof_calls, [])
        self.assertEqual(relation_facade.list_by_month_calls, [])
        self.assertEqual(relation_facade.source_version_month_calls, [])
        self.assertEqual(
            relation_source_repository.calls,
            [{"scope_key": "2026-06", "row_ids": ["bank-row-1", "bank-row-2"]}],
        )
        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(result["batch"]["row_ids"], ["bank-row-1", "bank-row-2"])
        self.assertEqual(confirm_calls[0]["relation_mode"], BANK_FLOW_RULE_BATCH_RELATION_MODE)
        self.assertEqual(
            confirm_calls[0]["requirement_metadata"],
            {
                "paired_requires_oa": False,
                "paired_requires_invoice": False,
                "paired_requirement_tag_code": "fee",
                "paired_requirement_version": 11,
            },
        )
        self.assertTrue(mutation_calls[0]["persist"])
        self.assertEqual(
            mutation_calls[0]["candidate_guard"]["guard_mode"],
            "selected_rows",
        )
        self.assertEqual(
            [
                proof["row_id"]
                for proof in mutation_calls[0]["candidate_guard"]["selected_row_proofs"]
            ],
            ["bank-row-1", "bank-row-2"],
        )
        self.assertEqual(
            mutation_calls[0]["candidate_guard"]["rule_proof"],
            {
                "tag_code": "fee",
                "rule_version": 11,
                "requires_oa": False,
                "requires_invoice": False,
                "eligible": True,
            },
        )
        self.assertNotIn("read_model_key", mutation_calls[0])

    def test_live_selected_rows_reads_current_canonical_source_not_import_snapshot(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def read_page(self, filters, *, summary_filters, page, page_size):  # type: ignore[no-untyped-def]
                self.calls.append(
                    {
                        "filters": dict(filters),
                        "summary_filters": dict(summary_filters),
                        "page": page,
                        "page_size": page_size,
                    }
                )
                return {
                    "candidate_rows": [
                        {
                            "id": "bank-row-current",
                            "trade_time": "2026-06-03 10:20:00",
                            "account_key": "ccb:8106",
                            "direction": "expense",
                            "amount": "8.80",
                            "category_code": "fee",
                            "category_source": "manual",
                            "category_version": 4,
                        }
                    ],
                    "tag_dictionary": {},
                    "active_relations": [],
                    "tag_policy": {
                        "version": 4,
                        "active_tags": [{"code": "fee"}],
                        "requirements_by_tag_code": {
                            "fee": {"requires_oa": False, "requires_invoice": False},
                        },
                    },
                }

        class ImportSnapshot:
            def list_transactions_by_ids(self, _row_ids):  # type: ignore[no-untyped-def]
                raise AssertionError("bank-flow selected submit must not read the process-local import snapshot")

        repository = Repository()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = repository
        service._import_service = ImportSnapshot()

        rows, categories, source = service._live_selected_rows(
            ["bank-row-current"],
            scope_month="2026-06",
        )

        self.assertEqual(repository.calls, [{
            "filters": {"month": "2026-06", "bucket": "unsubmitted"},
            "summary_filters": {"month": "2026-06"},
            "page": 1,
            "page_size": None,
        }])
        self.assertEqual(rows[0]["id"], "bank-row-current")
        self.assertEqual(categories["bank-row-current"]["effective_category_code"], "fee")
        self.assertEqual(source["tag_policy"]["version"], 4)

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
        service._live_selected_rows = (  # type: ignore[method-assign]
            lambda _row_ids, *, scope_month: (
                [{
                    "id": "bank-row-1",
                    "trade_time": "2026-06-04 10:20:00",
                    "account_key": "ccb:8106",
                    "bank_name": "建设银行",
                    "account_last4": "8106",
                    "direction": "expense",
                    "amount": "18.20",
                }],
                {"bank-row-1": {"category_code": "internal_transfer", "effective_category_code": "internal_transfer"}},
                {
                    "active_relations": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {"requires_oa": False, "requires_invoice": False},
                        },
                    },
                },
            )
        )

        with self.assertRaises(BankBatchRelationMutationError) as raised:
            service.submit_selected_rows(
                row_ids=["bank-row-1"],
                actor="finance-user",
                note="提交",
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                scope_month="2026-06",
            )

        self.assertEqual(
            raised.exception.error_code,
            "bank_flow_rule_batch_selection_internal_transfer_requires_pair",
        )
        self.assertEqual(str(raised.exception), "内部往来批次请使用单批提交。")
        self.assertEqual(import_service.get_calls, [])
        self.assertEqual(import_service.list_calls, [])

    def test_submit_selected_guard_conflict_restores_relation_and_batch(self) -> None:
        rows = [
            {
                "id": "bank-fee-1",
                "trade_time": "2026-06-03 10:20:00",
                "account_key": "ccb:8106",
                "direction": "expense",
                "amount": "8.80",
            },
            {
                "id": "bank-fee-2",
                "trade_time": "2026-06-04 10:20:00",
                "account_key": "ccb:8106",
                "direction": "expense",
                "amount": "18.20",
            },
        ]
        categories = {
            str(row["id"]): {
                "category_code": "fee",
                "effective_category_code": "fee",
            }
            for row in rows
        }

        class RejectingStateStore:
            def save_bank_flow_rule_batch_mutation(self, **kwargs: object) -> None:
                guard = kwargs.get("candidate_guard")
                assert isinstance(guard, dict)
                assert guard["guard_mode"] == "selected_rows"
                raise RuntimeError("bank_flow_rule_batch_candidate_guard_conflict")

        pair_service = WorkbenchPairRelationService()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        service._pair_relation_snapshot_port = BankBatchPairRelationSnapshotPort(
            pair_service
        )
        service._state_store = RejectingStateStore()
        service._bank_transaction_category_affected_months_provider = lambda _row_ids: []
        service._live_selected_rows = lambda _row_ids, *, scope_month: (  # type: ignore[method-assign]
            list(rows),
            dict(categories),
            {
                "active_relations": [],
                "tag_policy": {
                    "active_tags": [{"code": "fee"}],
                    "requirements_by_tag_code": {
                        "fee": {"requires_oa": False, "requires_invoice": False},
                    },
                },
            },
        )
        service.active_relation_source_bundle_for_bank_rows = (  # type: ignore[method-assign]
            lambda _rows, **_kwargs: {"rows": [], "source_versions": {}}
        )
        service.candidate_source_versions_for_scope = lambda **_kwargs: {}  # type: ignore[method-assign]
        service._eligible_tag_codes_for_relation_mode = lambda _mode: {"fee"}  # type: ignore[method-assign]

        def confirm_relation(batch: dict[str, object], **_kwargs: object) -> None:
            pair_service.create_active_relation(
                case_id=str(batch["batch_id"]),
                row_ids=[str(row_id) for row_id in list(batch["row_ids"])],
                row_types=["bank_transaction", "bank_transaction"],
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                created_by="finance-user",
                month_scope="2026-06",
            )

        service._confirm_relation_for_batch = confirm_relation  # type: ignore[method-assign]

        with self.assertRaises(BankBatchRelationMutationError) as raised:
            service.submit_selected_rows(
                row_ids=["bank-fee-1", "bank-fee-2"],
                actor="finance-user",
                note="提交",
                scope_month="2026-06",
            )

        self.assertEqual(
            raised.exception.error_code,
            "bank_flow_rule_batch_candidate_conflict",
        )
        self.assertEqual(pair_service.list_active_relations(), [])
        self.assertEqual(service._bank_batch_service.snapshot()["batches"], {})

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

    def test_withdraw_uses_bank_flow_relation_mode_for_relation_command(self) -> None:
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
        self.assertTrue(mutation_calls[0]["persist"])
        self.assertNotIn("read_model_key", mutation_calls[0])

    def test_withdraw_does_not_refresh_projection_when_runtime_batch_is_missing(self) -> None:
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
        self.assertEqual(refresh_calls, [])

    def test_submit_selected_rows_rejects_invalid_amount_or_direction_without_writes(self) -> None:
        valid_row = {
            "id": "bank-fee-1",
            "trade_time": "2026-06-03 10:20:00",
            "account_key": "ccb:8106",
            "direction": "expense",
            "amount": "8.80",
        }
        invalid_rows = {
            "invalid_amount": {
                **valid_row,
                "amount": "not-a-number",
            },
            "invalid_direction": {
                **valid_row,
                "direction": "",
            },
        }

        for expected_suffix, row in invalid_rows.items():
            with self.subTest(expected_suffix=expected_suffix):
                pair_service = WorkbenchPairRelationService()
                service = object.__new__(BankFlowRuleBatchApplicationService)
                service._bank_batch_service = BankBatchService()
                service._pair_relation_snapshot_port = BankBatchPairRelationSnapshotPort(
                    pair_service
                )
                service._live_selected_rows = lambda _row_ids, *, scope_month, selected=row: (  # type: ignore[method-assign]
                    [dict(selected)],
                    {"bank-fee-1": {"category_code": "fee", "effective_category_code": "fee"}},
                    {
                        "active_relations": [],
                        "tag_policy": {
                            "active_tags": [{"code": "fee"}],
                            "requirements_by_tag_code": {
                                "fee": {"requires_oa": False, "requires_invoice": False},
                            },
                        },
                    },
                )
                service.active_relation_source_bundle_for_bank_rows = (  # type: ignore[method-assign]
                    lambda _rows, **_kwargs: {"rows": [], "source_versions": {}}
                )
                service.candidate_source_versions_for_scope = (  # type: ignore[method-assign]
                    lambda **_kwargs: {}
                )
                service.bank_batch_source_versions = lambda **_kwargs: {}  # type: ignore[method-assign]
                service._eligible_tag_codes_for_relation_mode = lambda _mode: {"fee"}  # type: ignore[method-assign]
                confirm_calls: list[dict[str, object]] = []
                service._confirm_relation_for_batch = (  # type: ignore[method-assign]
                    lambda batch, **_kwargs: confirm_calls.append(dict(batch))
                )

                with self.assertRaisesRegex(
                    ValueError,
                    f"bank_flow_rule_batch_selection_{expected_suffix}",
                ):
                    service.submit_selected_rows(
                        row_ids=["bank-fee-1"],
                        actor="finance-user",
                        note="提交",
                        scope_month="2026-06",
                    )

                self.assertEqual(confirm_calls, [])
                self.assertEqual(pair_service.list_active_relations(), [])
                self.assertEqual(service._bank_batch_service.snapshot()["batches"], {})

    def test_persist_mutation_uses_bank_flow_state_store_boundary(self) -> None:
        state_store = RecordingStateStore()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = state_store
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._bank_batch_public_snapshot = lambda: {"batches": {"batch-1": {"batch_id": "batch-1"}}}

        service.persist_mutation(
            changed_case_ids=["case-1"],
            changed_scope_keys=["2026-05", "not-a-month"],
            changed_batch_ids=["batch-1"],
        )

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
        self.assertEqual(mutation["changed_batch_ids"], ["batch-1"])

    def test_persist_mutation_fails_fast_without_bank_flow_boundary(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = object()
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._bank_batch_public_snapshot = lambda: {"batches": {}}

        with self.assertRaises(BankBatchPersistenceError):
            service.persist_mutation(changed_case_ids=[], changed_scope_keys=["all"])

    def test_pair_relation_snapshot_by_case_id_uses_scoped_snapshot(self) -> None:
        pair_service = RecordingPairSnapshotPort()
        port = BankBatchPairRelationSnapshotPort(pair_service)

        relation = port.snapshot_by_case_id("case-1")

        self.assertEqual(relation, {"case_id": "case-1"})
        self.assertEqual(pair_service.snapshot_case_id_calls, [["case-1"]])
        self.assertEqual(pair_service.snapshot_calls, 0)

    def test_pair_relation_snapshot_port_exposes_atomic_canonical_source_bundle(self) -> None:
        port = BankBatchPairRelationSnapshotPort(
            SimpleNamespace(
                snapshot=lambda: {
                    "pair_relations": {
                        "case-active": {
                            "case_id": "case-active",
                            "status": "active",
                            "row_ids": ["bank-1", "oa-1"],
                            "row_types": ["bank_transaction", "oa"],
                        },
                        "case-unrelated": {
                            "case_id": "case-unrelated",
                            "status": "active",
                            "row_ids": ["bank-2"],
                            "row_types": ["bank_transaction"],
                        },
                        "case-cancelled": {
                            "case_id": "case-cancelled",
                            "status": "cancelled",
                            "row_ids": ["bank-1"],
                            "row_types": ["bank_transaction"],
                        },
                    }
                }
            )
        )

        bundle = port.workbench_relation_source_bundle_from_source(
            scope_key="2026-07",
            row_ids=["bank-1"],
        )

        self.assertEqual([row["case_id"] for row in bundle["rows"]], ["case-active"])
        self.assertEqual(bundle["source_versions"]["source"], "workbench_pair_relations_memory")
        self.assertEqual(bundle["source_versions"]["scope_key"], "2026-07")
        self.assertTrue(bundle["source_versions"]["snapshot_version"])

    def test_tag_selection_payload_reads_bank_flow_rule_settings_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings

        payload = service.tag_selection_payload()

        self.assertEqual(payload, settings.get_bank_flow_rule_batch_tag_rules_payload())

    def test_update_tag_selection_uses_bank_flow_rule_settings_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        commit_calls: list[dict[str, object]] = []
        enqueue_calls: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._query_repository = SimpleNamespace(
            affected_scope_keys_for_tag_codes=lambda codes: ["2026-05"] if codes == ["fee"] else []
        )
        service._commit_tag_rule_update = (  # type: ignore[method-assign]
            lambda **kwargs: commit_calls.append(dict(kwargs))
        )

        result = service.update_tag_selection(
            {"expected_version": 7, "rules": [{"tag_code": "fee"}]},
            actor_id="finance-user",
        )

        self.assertEqual(settings.updated_payloads, [{"expected_version": 7, "rules": [{"tag_code": "fee"}]}])
        self.assertEqual(settings.actors, ["finance-user"])
        self.assertEqual(result["version"], 8)
        self.assertTrue(result["eligibility_changed"])
        self.assertEqual(result["eligibility_changed_tag_codes"], ["fee"])
        self.assertNotIn("affected_scope_keys", result)
        self.assertNotIn("refresh_enqueued", result)
        self.assertEqual(set(commit_calls[0]), {"prepared"})
        self.assertEqual(enqueue_calls, [])

    def test_update_tag_selection_noop_does_not_enqueue_refresh(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        current = settings.get_bank_flow_rule_batch_tag_rules_payload()
        settings.normalize_bank_flow_rule_batch_tag_rules_update = (  # type: ignore[method-assign]
            lambda _payload, *, actor_id: {
                "changed": False,
                "previous_public_payload": current,
                "public_payload": current,
            }
        )
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._commit_tag_rule_update = (  # type: ignore[method-assign]
            lambda **_kwargs: (_ for _ in ()).throw(AssertionError("no-op must not commit or enqueue"))
        )

        result = service.update_tag_selection(
            {"expected_version": 7, "rules": [{"tag_code": "fee"}]},
            actor_id="finance-user",
        )

        self.assertEqual(result["version"], 7)
        self.assertFalse(result["eligibility_changed"])
        self.assertNotIn("affected_scope_keys", result)

    def test_update_tag_selection_eligibility_neutral_change_saves_without_refresh_scope(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        prepared = settings.normalize_bank_flow_rule_batch_tag_rules_update(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )
        next_public = dict(prepared["public_payload"])
        next_public["requirements_by_tag_code"] = {
            "fee": {"requires_oa": False, "requires_invoice": True},
        }
        prepared["public_payload"] = next_public
        settings.normalize_bank_flow_rule_batch_tag_rules_update = (  # type: ignore[method-assign]
            lambda _payload, *, actor_id: prepared
        )
        commit_calls: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._commit_tag_rule_update = (  # type: ignore[method-assign]
            lambda **kwargs: commit_calls.append(dict(kwargs))
        )

        result = service.update_tag_selection(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )

        self.assertFalse(result["eligibility_changed"])
        self.assertNotIn("refresh_enqueued", result)
        self.assertNotIn("affected_scope_keys", result)
        self.assertEqual(set(commit_calls[0]), {"prepared"})

    def test_commit_tag_rule_update_uses_one_postgres_transaction_for_settings_only(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        prepared = settings.normalize_bank_flow_rule_batch_tag_rules_update(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )
        connection = RecordingTransactionConnection()
        calls: list[tuple[str, object]] = []

        def save_settings(
            payload: dict[str, object], *, expected_version: int, transaction: object
        ) -> dict[str, object]:
            calls.append(("settings", transaction))
            self.assertEqual(expected_version, 7)
            return payload

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = SimpleNamespace(
            storage_backend="postgres",
            _connection=connection,
            save_app_settings_for_bank_flow_rule_version_in_transaction=save_settings,
        )
        service._queue_repository = SimpleNamespace(
            enqueue_read_model_refreshes_in_transaction=lambda **_kwargs: (_ for _ in ()).throw(
                AssertionError("tag-rule save must not enqueue page rebuilds")
            ),
        )
        service._app_settings_service = settings

        service._commit_tag_rule_update(prepared=prepared)

        transaction = connection.recording_transaction
        self.assertEqual(calls, [("settings", transaction)])
        self.assertIsNone(transaction.exited_with)
        self.assertEqual(len(settings.accepted_updates), 1)

    def test_commit_tag_rule_update_does_not_depend_on_refresh_queue(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        prepared = settings.normalize_bank_flow_rule_batch_tag_rules_update(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )
        connection = RecordingTransactionConnection()

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = SimpleNamespace(
            storage_backend="postgres",
            _connection=connection,
            save_app_settings_for_bank_flow_rule_version_in_transaction=(
                lambda payload, *, expected_version, transaction: payload
            ),
        )
        service._queue_repository = SimpleNamespace(
            enqueue_read_model_refreshes_in_transaction=(
                lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("queue unavailable"))
            ),
        )
        service._app_settings_service = settings

        service._commit_tag_rule_update(prepared=prepared)

        self.assertIsNone(connection.recording_transaction.exited_with)
        self.assertEqual(len(settings.accepted_updates), 1)

    def test_commit_tag_rule_update_rejects_stale_database_version_without_queue_io(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        prepared = settings.normalize_bank_flow_rule_batch_tag_rules_update(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )
        connection = RecordingTransactionConnection()
        enqueue_calls: list[object] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = SimpleNamespace(
            storage_backend="postgres",
            _connection=connection,
            save_app_settings_for_bank_flow_rule_version_in_transaction=(
                lambda _payload, *, expected_version, transaction: None
            ),
        )
        service._queue_repository = SimpleNamespace(
            enqueue_read_model_refreshes_in_transaction=lambda **kwargs: enqueue_calls.append(kwargs),
        )
        service._app_settings_service = settings

        with self.assertRaises(AppSettingsValidationError) as context:
            service._commit_tag_rule_update(prepared=prepared)

        self.assertEqual(context.exception.error_code, "bank_flow_rule_batch_tag_rules_version_conflict")
        self.assertIs(connection.recording_transaction.exited_with, AppSettingsValidationError)
        self.assertEqual(enqueue_calls, [])
        self.assertEqual(settings.accepted_updates, [])

    def test_commit_tag_rule_update_saves_local_settings_without_queue_io(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        prepared = settings.normalize_bank_flow_rule_batch_tag_rules_update(
            {"expected_version": 7, "rules": []},
            actor_id="finance-user",
        )
        saved_snapshots: list[dict[str, object]] = []
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = SimpleNamespace(
            storage_backend="local",
            save_app_settings=lambda payload: saved_snapshots.append(dict(payload)),
        )
        service._app_settings_service = settings

        service._commit_tag_rule_update(prepared=prepared)

        self.assertEqual(saved_snapshots, [prepared["next_snapshot"]])
        self.assertEqual(len(settings.accepted_updates), 1)

    def test_bank_flow_source_versions_use_eligibility_signature_boundary(self) -> None:
        settings = RecordingBankFlowRuleSettings()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._workbench_matching_source_versions_provider = lambda: {"workbench_formal_relation_rule_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {"version": 3})
        service._effective_category_provider = SimpleNamespace(
            canonical_category_source_proof_for_rows=lambda rows: {
                "source": "canonical_bank_transaction_categories",
                "row_count": len(rows),
                "membership_category_digest": "category-v1",
            }
        )
        service._import_service = SimpleNamespace(
            list_transactions=lambda *, month: [{"id": f"{month}-bank"}]
        )
        service._relation_facade = SimpleNamespace(last_source_versions={})

        versions = service.no_oa_bank_batch_source_versions(
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertIn("bank_flow_rule_batch_eligibility_version", versions)
        self.assertNotIn("bank_flow_rule_batch_tag_rules_version", versions)
        self.assertIn("bank_flow_rule_batch_schema_version", versions)
        self.assertNotIn("no_oa_bank_batch_tag_selection_version", versions)

    def test_bank_flow_eligibility_requires_both_oa_and_invoice_unchecked(self) -> None:
        payload = {
            "active_tags": [
                {"code": "neither"},
                {"code": "oa"},
                {"code": "invoice"},
                {"code": "both"},
                {"code": "missing"},
            ],
            "requirements_by_tag_code": {
                "neither": {"requires_oa": False, "requires_invoice": False},
                "oa": {"requires_oa": True, "requires_invoice": False},
                "invoice": {"requires_oa": False, "requires_invoice": True},
                "both": {"requires_oa": True, "requires_invoice": True},
            },
        }

        self.assertEqual(
            BankFlowRuleBatchApplicationService._eligible_bank_flow_rule_batch_tag_codes(payload),
            {"neither"},
        )

    def test_summary_keeps_frozen_submitted_history_for_now_ineligible_tag(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)

        summary = service._summary_from_aggregates(
            [
                {
                    "batch_type": "archived_fee",
                    "presented_status": "submitted",
                    "batch_count": 2,
                    "row_count": 7,
                    "total_amount": "88.00",
                    "batch_label": "历史手续费",
                    "category_primary_label": "历史费用",
                    "category_sub_label": "历史手续费",
                }
            ],
            eligible_tag_codes={"current_fee"},
            definitions_by_code={
                "current_fee": {
                    "code": "current_fee",
                    "label": "当前手续费",
                    "output_primary_label": "费用",
                    "output_sub_label": "当前手续费",
                }
            },
        )

        categories = {item["code"]: item for item in summary["categories"]}
        self.assertEqual(categories["current_fee"]["draft"], 0)
        self.assertEqual(categories["archived_fee"]["label"], "历史手续费")
        self.assertEqual(categories["archived_fee"]["primary_label"], "历史费用")
        self.assertEqual(categories["archived_fee"]["submitted"], 2)
        self.assertEqual(categories["archived_fee"]["submitted_row_count"], 7)
        self.assertEqual(summary["submitted_count"], 2)
        self.assertEqual(summary["submitted_row_count"], 7)

    def test_bank_flow_scope_source_versions_use_canonical_relation_bundle(self) -> None:
        settings = RecordingBankFlowRuleSettings()

        class EffectiveCategoryProvider:
            def __init__(self) -> None:
                self.proof_row_ids: list[list[str]] = []

            def bulk_get_for_rows(self, _rows: list[dict[str, object]]) -> dict[str, dict[str, object]]:
                raise AssertionError("source-version precheck must not load bank detail rows")

            def canonical_category_source_proof_for_rows(
                self,
                rows: list[dict[str, object]],
            ) -> dict[str, object]:
                self.proof_row_ids.append([str(row["id"]) for row in rows])
                return {
                    "source": "canonical_bank_transaction_categories",
                    "row_count": len(rows),
                    "membership_category_digest": "category-v1",
                }

        class RelationFacade:
            last_source_versions: dict[str, object] = {}

            def __init__(self) -> None:
                self.source_version_calls: list[str] = []
                self.source_version_reasons: list[str] = []

            def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("source-version precheck must not load relation rows")

            def source_versions_for_month(self, month: str, **kwargs: object) -> dict[str, object]:
                self.source_version_calls.append(month)
                self.source_version_reasons.append(str(kwargs.get("reason") or ""))
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
        service._workbench_matching_source_versions_provider = lambda: {"workbench_formal_relation_rule_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(snapshot=lambda: {"version": 3})
        service._effective_category_provider = provider
        service._relation_facade = relation_facade
        service._import_service = SimpleNamespace(
            list_transactions=lambda *, month: [
                {"id": f"{month}-bank-{index}"}
                for index in range(100)
            ]
        )

        versions = service.candidate_source_versions_for_scope(
            scope_key="2026-02",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            relation_source_versions={
                "source": "workbench_pair_relations",
                "scope_key": "2026-02",
                "relation_count": 3,
                "relation_updated_at": "2026-07-21 16:20:00+08",
            },
        )

        self.assertEqual(
            provider.proof_row_ids,
            [[f"2026-02-bank-{index}" for index in range(100)]],
        )
        self.assertEqual(relation_facade.source_version_calls, [])
        self.assertEqual(relation_facade.source_version_reasons, [])
        self.assertIn("bank_flow_rule_batch_eligibility_version", versions)
        self.assertNotIn("bank_flow_rule_batch_tag_rules_version", versions)
        self.assertEqual(
            versions["category_source_proof"],
            {
                "source": "canonical_bank_transaction_categories",
                "row_count": 100,
                "membership_category_digest": "category-v1",
            },
        )
        self.assertEqual(
            versions["workbench_relation_source_versions"],
            {
                "source": "workbench_pair_relations",
                "scope_key": "2026-02",
                "relation_count": 3,
                "relation_updated_at": "2026-07-21 16:20:00+08",
            },
        )
        self.assertEqual(service.bank_row_count_from_source_versions(versions), 100)

    def test_bank_flow_list_uses_canonical_page_result_without_refresh_fields(self) -> None:
        settings = RecordingBankFlowRuleSettings()

        class EffectiveCategoryProvider:
            def __init__(self) -> None:
                self.proof_calls: list[list[str]] = []

            def canonical_category_source_proof_for_rows(
                self,
                rows: list[dict[str, object]],
            ) -> dict[str, object]:
                self.proof_calls.append([str(row["id"]) for row in rows])
                return {
                    "source": "canonical_bank_transaction_categories",
                    "row_count": len(rows),
                    "membership_category_digest": "category-v1",
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
        tag_dictionary_calls: list[bool] = []

        def tag_dictionary_payload() -> dict[str, object]:
            tag_dictionary_calls.append(True)
            return {
                "definitions": [
                    {
                        "code": "fee",
                        "label": "手续费",
                        "output_primary_label": "费用",
                        "output_sub_label": "手续费",
                    }
                ]
            }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._app_settings_service = settings
        service._workbench_matching_source_versions_provider = lambda: {"workbench_formal_relation_rule_version": "rules-v1"}
        service._bank_transaction_category_service = SimpleNamespace(
            snapshot=lambda: {"version": 3},
            tag_dictionary_payload=tag_dictionary_payload,
        )
        service._effective_category_provider = provider
        service._relation_facade = relation_facade
        service._import_service = SimpleNamespace(
            list_transactions=lambda *, month: [
                {"id": f"{month}-bank-{index}"}
                for index in range(4)
            ]
        )
        expected_versions = service.candidate_source_versions_for_scope(
            scope_key="2026-07",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            relation_source_versions={
                "source": "workbench_pair_relations",
                "scope_key": "2026-07",
                "relation_count": 1,
                "relation_updated_at": "2026-07-21 16:20:00+08",
            },
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
                self.calls: list[dict[str, object]] = []
                self.status = "fresh"

            def read_page(
                self,
                filters: dict[str, object],
                *,
                summary_filters: dict[str, object],
                page: int,
                page_size: int | None,
            ) -> dict[str, object]:
                self.calls.append(
                    {
                        "filters": dict(filters),
                        "summary_filters": dict(summary_filters),
                        "page": page,
                        "page_size": page_size,
                    }
                )
                return {
                    "candidate_rows": [
                        {
                            "id": "bank-1",
                            "trade_time": "2026-07-04T10:20:00",
                            "account_key": "CCB:8106",
                            "bank_name": "建设银行",
                            "account_no": "6222000000008106",
                            "direction": "expense",
                            "amount": "12.00",
                            "category_code": "fee",
                            "category_source": "auto_confirmation",
                        }
                    ],
                    "active_relations": [],
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [
                            {
                                "code": "fee",
                                "label": "手续费",
                                "output_primary_label": "费用",
                                "output_sub_label": "手续费",
                            }
                        ],
                        "requirements_by_tag_code": {
                            "fee": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        repository = Repository()
        service._query_repository = repository
        service._bank_batch_service = SimpleNamespace(list_batches=lambda _filters: [])
        provider_calls_before = list(provider.proof_calls)
        relation_calls_before = list(relation_facade.source_version_calls)

        payload = service.list_batches_payload(
            {"month": ["2026-07"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(len(payload["batches"]), 1)
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("read_model_version", payload)
        self.assertNotIn("refresh_enqueued", payload)
        self.assertEqual(provider.proof_calls, provider_calls_before)
        self.assertEqual(relation_facade.source_version_calls, relation_calls_before)
        self.assertEqual(len(tag_dictionary_calls), 0)
        self.assertEqual(
            repository.calls,
            [
                {
                    "filters": {
                        "month": "2026-07",
                        "type": "",
                        "status": "",
                        "bucket": "",
                        "account_key": "",
                    },
                    "summary_filters": {"month": "2026-07", "account_key": ""},
                    "page": 1,
                    "page_size": None,
                },
            ],
        )

    def test_bank_flow_list_derives_188500_internal_transfer_from_live_canonical_rows(self) -> None:
        class Repository:
            def read_detail(self, _batch_id: str) -> None:
                return None

            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "candidate_rows": [
                        {
                            "id": "bank-out-188500",
                            "trade_time": "2026-05-14T09:00:00",
                            "account_key": "CCB:8106",
                            "bank_name": "建设银行",
                            "account_no": "6222000000008106",
                            "counterparty_name": "云南溯源科技有限公司",
                            "direction": "expense",
                            "amount": "188500.00",
                        },
                        {
                            "id": "bank-in-188500",
                            "trade_time": "2026-05-14T09:30:00",
                            "account_key": "ICBC:6386",
                            "bank_name": "工商银行",
                            "account_no": "6222000000006386",
                            "counterparty_name": "云南溯源科技有限公司",
                            "direction": "income",
                            "amount": "188500.00",
                        },
                    ],
                    "active_relations": [],
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(len(payload["batches"]), 1)
        batch = payload["batches"][0]
        self.assertEqual(batch["batch_type"], "internal_transfer")
        self.assertEqual(
            batch["row_ids"],
            ["bank-in-188500", "bank-out-188500"],
        )
        self.assertEqual(batch["total_amount"], "188500.00")
        self.assertEqual(payload["summary"]["draft_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "188500.00")

        detail = service.detail_payload(
            str(batch["batch_id"]),
            scope_month="2026-05",
        )

        self.assertEqual(detail["batch"]["batch_id"], batch["batch_id"])
        self.assertEqual(
            [row["id"] for row in detail["rows"]],
            ["bank-in-188500", "bank-out-188500"],
        )

    def test_submitted_bucket_rebuilds_formal_batch_from_canonical_rows_and_relation(self) -> None:
        rows = [
            {
                "id": "bank-fee-1",
                "trade_time": "2026-05-14T09:00:00",
                "account_key": "CCB:8106",
                "direction": "expense",
                "amount": "8.80",
                "category_code": "fee",
                "category_source": "auto_confirmation",
            }
        ]
        candidate_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        candidate_service.build_batches(
            rows,
            {
                "bank-fee-1": {
                    "category_code": "fee",
                    "category_source": "auto_confirmation",
                }
            },
            [],
            {},
            eligible_batch_types={"fee"},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        submitted = candidate_service.list_batches()[0]
        submitted.update(
            {
                "status": "submitted",
                "status_bucket": "submitted",
                "version": 2,
            }
        )

        class Repository:
            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "candidate_rows": rows,
                    "active_relations": [
                        {
                            "case_id": submitted["batch_id"],
                            "status": "active",
                            "row_ids": ["bank-fee-1"],
                            "row_types": ["bank"],
                            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                        }
                    ],
                    "formal_items": [submitted],
                    "tag_policy": {
                        "active_tags": [{"code": "fee", "label": "手续费"}],
                        "requirements_by_tag_code": {
                            "fee": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["submitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(
            [(batch["batch_id"], batch["status"]) for batch in payload["batches"]],
            [(submitted["batch_id"], "submitted")],
        )
        self.assertEqual(payload["summary"]["submitted_count"], 1)
        self.assertEqual(payload["summary"]["submitted_row_count"], 1)

    def test_submit_live_candidate_rederives_the_bounded_month_before_write(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def read_batch(self, _batch_id: str) -> None:
                return None

            def read_page(
                self,
                filters: dict[str, object],
                *,
                summary_filters: dict[str, object],
                page: int,
                page_size: int | None,
            ) -> dict[str, object]:
                self.calls.append(
                    {
                        "filters": dict(filters),
                        "summary_filters": dict(summary_filters),
                        "page": page,
                        "page_size": page_size,
                    }
                )
                return {
                    "candidate_rows": [
                        {
                            "id": "bank-out-188500",
                            "trade_time": "2026-05-14T09:00:00",
                            "account_key": "CCB:8106",
                            "direction": "expense",
                            "amount": "188500.00",
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                        },
                        {
                            "id": "bank-in-188500",
                            "trade_time": "2026-05-14T09:30:00",
                            "account_key": "ICBC:6386",
                            "direction": "income",
                            "amount": "188500.00",
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                        },
                    ],
                    "active_relations": [],
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        repository = Repository()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = repository
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        service._confirm_relation_for_batch = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service._mutation_result = (  # type: ignore[method-assign]
            lambda batch, **_kwargs: {"batch": dict(batch)}
        )
        candidate = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )["batches"][0]
        repository.calls.clear()

        result = service.submit_batch(
            str(candidate["batch_id"]),
            actor="finance-user",
            expected_version=int(candidate["version"]),
            note="提交",
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
            scope_month="2026-05",
        )

        self.assertEqual(result["batch"]["status"], "submitted")
        self.assertEqual(
            repository.calls,
            [
                {
                    "filters": {"month": "2026-05", "bucket": "unsubmitted"},
                    "summary_filters": {"month": "2026-05"},
                    "page": 1,
                    "page_size": None,
                }
            ],
        )

    def test_submit_without_scope_rejects_lingering_persisted_draft_without_write(self) -> None:
        class Repository:
            def read_batch(self, _batch_id: str) -> dict[str, object]:
                return {
                    "batch_id": "bank_flow_rule_batch_v1_lingering",
                    "status": "draft",
                    "status_bucket": "unsubmitted",
                    "scope_month": "2026-05",
                    "batch_type": "fee",
                    "row_ids": ["bank-lingering"],
                    "total_amount": "8.80",
                }

            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("missing scope must fail before live candidate re-derive")

        state_store = RecordingStateStore()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._state_store = state_store
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        service._pair_relation_snapshot_port = None

        with self.assertRaises(BankBatchRelationMutationError) as raised:
            service.submit_batch(
                "bank_flow_rule_batch_v1_lingering",
                actor="finance-user",
                expected_version=1,
                note=None,
                scope_month=None,
            )

        self.assertEqual(
            raised.exception.error_code,
            "bank_flow_rule_batch_candidate_conflict",
        )
        self.assertEqual(state_store.bank_flow_mutations, [])
        self.assertEqual(service._bank_batch_service.snapshot()["batches"], {})

    def test_candidate_guard_conflict_restores_relation_and_writes_no_formal_batch(self) -> None:
        class Repository:
            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "candidate_rows": [
                        {
                            "id": "bank-out-188500",
                            "trade_time": "2026-05-14T09:00:00",
                            "account_key": "CCB:8106",
                            "direction": "expense",
                            "amount": "188500.00",
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                        },
                        {
                            "id": "bank-in-188500",
                            "trade_time": "2026-05-14T09:30:00",
                            "account_key": "ICBC:6386",
                            "direction": "income",
                            "amount": "188500.00",
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                        },
                    ],
                    "active_relations": [],
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        class GuardRejectingStateStore:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def save_bank_flow_rule_batch_mutation(self, **kwargs: object) -> None:
                self.calls.append(dict(kwargs))
                raise RuntimeError("bank_flow_rule_batch_candidate_guard_conflict")

        pair_service = WorkbenchPairRelationService()
        batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._bank_batch_service = batch_service
        service._pair_relation_snapshot_port = BankBatchPairRelationSnapshotPort(pair_service)
        service._state_store = GuardRejectingStateStore()
        service._bank_transaction_category_affected_months_provider = lambda _row_ids: []
        service.resolve_labels = lambda batches, **_kwargs: batches  # type: ignore[method-assign]

        candidate = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )["batches"][0]

        def create_relation(batch: dict[str, object], **_kwargs: object) -> None:
            pair_service.create_active_relation(
                case_id=str(batch["batch_id"]),
                row_ids=[str(row_id) for row_id in list(batch["row_ids"])],
                row_types=["bank", "bank"],
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                created_by="finance-user",
                month_scope="2026-05",
            )

        service._confirm_relation_for_batch = create_relation  # type: ignore[method-assign]

        with self.assertRaises(BankBatchRelationMutationError) as raised:
            service.submit_batch(
                str(candidate["batch_id"]),
                actor="finance-user",
                expected_version=int(candidate["version"]),
                note="提交",
                relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                scope_month="2026-05",
            )

        self.assertEqual(
            raised.exception.error_code,
            "bank_flow_rule_batch_candidate_conflict",
        )
        self.assertEqual(pair_service.list_active_relations(), [])
        self.assertEqual(batch_service.snapshot()["batches"], {})
        self.assertEqual(len(service._state_store.calls), 1)
        self.assertEqual(
            service._state_store.calls[0]["candidate_guard"]["row_ids"],
            ["bank-in-188500", "bank-out-188500"],
        )

    def test_withdrawn_formal_item_does_not_hide_requalified_live_candidate(self) -> None:
        class Repository:
            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                rows = [
                    {
                        "id": "bank-out-188500",
                        "trade_time": "2026-05-14T09:00:00",
                        "account_key": "CCB:8106",
                        "direction": "expense",
                        "amount": "188500.00",
                        "category_code": "internal_transfer",
                        "category_source": "auto_confirmation",
                    },
                    {
                        "id": "bank-in-188500",
                        "trade_time": "2026-05-14T09:30:00",
                        "account_key": "ICBC:6386",
                        "direction": "income",
                        "amount": "188500.00",
                        "category_code": "internal_transfer",
                        "category_source": "auto_confirmation",
                    },
                ]
                candidate_service = BankBatchService(
                    schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
                    batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
                    relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                )
                candidate_service.build_batches(
                    rows,
                    {
                        str(row["id"]): {
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                        }
                        for row in rows
                    },
                    [],
                    {},
                    eligible_batch_types={"internal_transfer"},
                    relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                )
                withdrawn = candidate_service.list_batches()[0]
                withdrawn.update(
                    {
                        "status": "withdrawn",
                        "status_bucket": "withdrawn",
                        "version": 3,
                    }
                )
                return {
                    "candidate_rows": rows,
                    "active_relations": [],
                    "formal_items": [withdrawn],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(len(payload["batches"]), 1)
        self.assertEqual(payload["batches"][0]["status"], "draft")
        self.assertEqual(payload["batches"][0]["total_amount"], "188500.00")

    def test_bank_flow_live_internal_transfer_keeps_unique_pair_and_fails_closed_on_ambiguous_remainder(
        self,
    ) -> None:
        class Repository:
            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                def row(
                    row_id: str,
                    *,
                    direction: str,
                    trade_time: str,
                    account_key: str,
                ) -> dict[str, object]:
                    return {
                        "id": row_id,
                        "trade_time": trade_time,
                        "account_key": account_key,
                        "direction": direction,
                        "amount": "188500.00",
                        "category_code": "internal_transfer",
                        "category_source": "auto_confirmation",
                    }

                return {
                    "candidate_rows": [
                        row(
                            "unique-out",
                            direction="expense",
                            trade_time="2026-05-10T08:00:00",
                            account_key="CCB:8106",
                        ),
                        row(
                            "unique-in",
                            direction="income",
                            trade_time="2026-05-10T08:01:00",
                            account_key="ICBC:6386",
                        ),
                        row(
                            "ambiguous-out-a",
                            direction="expense",
                            trade_time="2026-05-12T10:00:00",
                            account_key="CCB:8106",
                        ),
                        row(
                            "ambiguous-out-b",
                            direction="expense",
                            trade_time="2026-05-12T10:00:00",
                            account_key="ABC:7777",
                        ),
                        row(
                            "ambiguous-in",
                            direction="income",
                            trade_time="2026-05-12T10:00:00",
                            account_key="ICBC:6386",
                        ),
                    ],
                    "active_relations": [],
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = Repository()
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        self.assertEqual(
            [batch["row_ids"] for batch in payload["batches"]],
            [["unique-in", "unique-out"]],
        )

    def test_bank_flow_live_internal_transfer_has_one_stable_owner_across_month_boundary(
        self,
    ) -> None:
        rows = [
            {
                "id": "boundary-out",
                "trade_time": "2026-05-31T23:30:00",
                "account_key": "CCB:8106",
                "direction": "expense",
                "amount": "188500.00",
                "category_code": "internal_transfer",
                "category_source": "auto_confirmation",
            },
            {
                "id": "boundary-in",
                "trade_time": "2026-06-01T00:30:00",
                "account_key": "ICBC:6386",
                "direction": "income",
                "amount": "188500.00",
                "category_code": "internal_transfer",
                "category_source": "auto_confirmation",
            },
        ]

        class Repository:
            def __init__(self) -> None:
                self.active_relations: list[dict[str, object]] = []

            def read_page(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "candidate_rows": rows,
                    "active_relations": list(self.active_relations),
                    "formal_items": [],
                    "tag_policy": {
                        "active_tags": [{"code": "internal_transfer", "label": "内部往来款"}],
                        "requirements_by_tag_code": {
                            "internal_transfer": {
                                "requires_oa": False,
                                "requires_invoice": False,
                            }
                        },
                    },
                }

        repository = Repository()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._query_repository = repository
        service._bank_batch_service = BankBatchService(
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )

        payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        repeated_payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        self.assertEqual(
            [batch["row_ids"] for batch in payload["batches"]],
            [["boundary-in", "boundary-out"]],
        )
        self.assertEqual(
            [batch["batch_id"] for batch in payload["batches"]],
            [batch["batch_id"] for batch in repeated_payload["batches"]],
        )
        self.assertEqual(
            [batch["row_ids"] for batch in payload["batches"]],
            [batch["row_ids"] for batch in repeated_payload["batches"]],
        )
        self.assertEqual(payload["batches"][0]["scope_month"], "2026-05")
        self.assertEqual(payload["batches"][0]["total_amount"], "188500.00")
        self.assertEqual(
            payload["batches"][0]["evidence"]["scope_owner_rule"],
            "earliest_member_month",
        )

        adjacent_month_payload = service.list_batches_payload(
            {"month": ["2026-06"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        self.assertEqual(adjacent_month_payload["batches"], [])

        repository.active_relations = [
            {
                "case_id": "occupied-case",
                "status": "active",
                "row_ids": ["boundary-out"],
                "row_types": ["bank"],
            }
        ]
        occupied_payload = service.list_batches_payload(
            {"month": ["2026-05"], "bucket": ["unsubmitted"]},
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        self.assertEqual(occupied_payload["batches"], [])



if __name__ == "__main__":
    unittest.main()
