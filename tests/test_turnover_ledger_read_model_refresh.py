from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.turnover_ledger_read_model_refresh import TurnoverLedgerReadModelRefreshService
from fin_ops_platform.services.turnover_ledger_sql_projection import (
    TurnoverLedgerSqlProjectionBuilder,
    _turnover_relation_id_from_relation,
    _with_bank_detail_source_versions,
)


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[tuple[str, object]] = []
        self.rebuilt_relation_deltas: list[dict[str, object]] = []

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, object]:
        self.rebuilt.append((scope_key, source_version))
        return {"scope_key": scope_key, "row_count": 2}

    def rebuild_turnover_ledger_relation_delta(
        self,
        scope_key: str,
        *,
        row_ids: list[str],
        source_version: object = None,
    ) -> dict[str, object]:
        self.rebuilt_relation_deltas.append(
            {"scope_key": scope_key, "row_ids": list(row_ids), "source_version": source_version}
        )
        return {"scope_key": scope_key, "row_count": 1, "relation_delta": True}


class FakeQueue:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))


class FakeTurnoverReadRepository:
    def __init__(self) -> None:
        self.saved_payload: dict[str, object] | None = None
        self.saved_scope_key: str | None = None
        self.existing_payload: dict[str, object] | None = None
        self.list_calls: list[dict[str, object]] = []
        self.source_rows: list[dict[str, object]] = []
        self.source_summary: dict[str, object] = {}
        self.source_bundle_calls: list[dict[str, object]] = []
        self.source_summary_calls: list[dict[str, object]] = []
        self.relation_delta_payload: dict[str, object] | None = None
        self.saved_relation_delta: dict[str, object] | None = None
        self.saved_relation_delta_scope_key: str | None = None
        self.generation = 0
        self.acknowledged: list[dict[str, object]] = []

    def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object] | None:
        self.list_calls.append(dict(kwargs))
        return self.existing_payload

    def save_turnover_ledger_rows(self, payload: dict[str, object], *, scope_key: str | None = None) -> None:
        self.saved_payload = payload
        self.saved_scope_key = scope_key

    def turnover_ledger_generation(self) -> int:
        return self.generation

    def acknowledge_unchanged_turnover_ledger_scope(self, **kwargs: object) -> int:
        self.acknowledged.append(dict(kwargs))
        self.generation += 1
        return self.generation

    def load_turnover_ledger_relation_delta(self, **_kwargs: object) -> dict[str, object]:
        return dict(self.relation_delta_payload or {})

    def save_turnover_ledger_relation_delta(
        self,
        payload: dict[str, object],
        *,
        scope_key: str,
    ) -> None:
        self.saved_relation_delta = dict(payload)
        self.saved_relation_delta_scope_key = scope_key

    def workbench_relation_source_bundle_from_source(self, **kwargs: object) -> dict[str, object]:
        self.source_bundle_calls.append(dict(kwargs))
        return {
            "rows": [dict(row) for row in self.source_rows],
            "source_versions": dict(self.source_summary),
        }

    def workbench_relation_source_summary_from_source(self, **kwargs: object) -> dict[str, object]:
        self.source_summary_calls.append(dict(kwargs))
        return dict(self.source_summary)


class FakeGroupedLedgerService:
    def list_grouped_ledger(self, *, page: int = 1, page_size: int = 200, **_kwargs: object) -> dict[str, object]:
        if page > 1:
            return {"groups": [], "pagination": {"page": page, "page_size": page_size, "total": 1}}
        return {
            "groups": [
                {
                    "group_id": "counterparty:personal:李四",
                    "counterparty_name": "李四",
                    "family": "personal",
                    "family_label": "个人往来",
                    "pending_direction": "mixed",
                    "pending_direction_label": "混合余额",
                    "pending_amount": "1500.00",
                    "pending_repayment_amount": "1000.00",
                    "pending_collection_amount": "500.00",
                    "closed_amount": "0.00",
                    "summary_row": {
                        "row_kind": "summary",
                        "relation_id": "rel-personal-mixed",
                        "borrow_amount": "2000.00",
                        "repayment_amount": "500.00",
                        "balance_amount": "1500.00",
                        "bank_account_labels": ["建行 1001", "工行 2002"],
                    },
                    "flow_rows": [
                        {
                            "row_kind": "flow",
                            "relation_id": "rel-personal-mixed",
                            "flow_id": "bank:txn-out-collected",
                            "source_bank_row_id": "txn-out-collected",
                            "category_primary_label": "外部往来款收款",
                            "category_sub_label": "收回借款",
                            "category_third_label": "个人往来",
                            "category_label_path": ["外部往来款收款", "收回借款", "个人往来"],
                            "bank_account_labels": ["工行 2002"],
                            "repayment_remark": "收回周转款 / 收款备注",
                        }
                    ],
                    "allocation_lots": [],
                    "lot_rows": [],
                }
            ],
            "pagination": {"page": page, "page_size": page_size, "total": 1},
        }


class CountingMultiMonthLedgerService:
    def __init__(self) -> None:
        self.calls = 0

    def list_grouped_ledger(self, *, page: int = 1, page_size: int = 200, **_kwargs: object) -> dict[str, object]:
        self.calls += 1
        if page > 1:
            return {"groups": [], "pagination": {"page": page, "page_size": page_size, "total": 2}}
        groups = []
        for month in ("2026-04", "2026-05"):
            row_id = f"txn-{month}"
            groups.append(
                {
                    "group_id": f"group-{month}",
                    "summary_row": {
                        "relation_id": f"relation-{month}",
                        "first_transaction_at": f"{month}-01",
                        "bank_row_ids": [row_id],
                    },
                    "flow_rows": [{"source_bank_row_id": row_id}],
                    "allocation_lots": [],
                    "lot_rows": [],
                }
            )
        return {"groups": groups, "pagination": {"page": page, "page_size": page_size, "total": 2}}


class FakeTwoFlowGroupedLedgerService:
    def list_grouped_ledger(self, *, page: int = 1, page_size: int = 200, **_kwargs: object) -> dict[str, object]:
        if page > 1:
            return {"groups": [], "pagination": {"page": page, "page_size": page_size, "total": 1}}
        return {
            "groups": [
                {
                    "group_id": "counterparty:personal:刘涵静",
                    "counterparty_name": "刘涵静",
                    "family": "personal",
                    "family_label": "个人往来",
                    "pending_direction": "closed",
                    "pending_direction_label": "已闭合",
                    "pending_amount": "0.00",
                    "pending_repayment_amount": "0.00",
                    "pending_collection_amount": "0.00",
                    "closed_amount": "240000.00",
                    "summary_row": {
                        "row_kind": "summary",
                        "relation_id": "rel-workbench-cash",
                        "borrow_amount": "240000.00",
                        "repayment_amount": "240000.00",
                        "balance_amount": "0.00",
                        "bank_account_labels": ["建行 8106"],
                    },
                    "flow_rows": [
                        {
                            "row_kind": "flow",
                            "relation_id": "rel-workbench-cash",
                            "flow_id": "bank-income-240000",
                            "source_bank_row_id": "bank-income-240000",
                            "flow_direction": "income",
                            "flow_amount": "240000.00",
                            "borrow_amount": "240000.00",
                            "repayment_amount": "0.00",
                            "bank_row_ids": ["bank-income-240000"],
                        },
                        {
                            "row_kind": "flow",
                            "relation_id": "rel-workbench-cash",
                            "flow_id": "bank-expense-240000",
                            "source_bank_row_id": "bank-expense-240000",
                            "flow_direction": "expense",
                            "flow_amount": "240000.00",
                            "borrow_amount": "0.00",
                            "repayment_amount": "240000.00",
                            "bank_row_ids": ["bank-expense-240000"],
                        },
                    ],
                    "allocation_lots": [],
                    "lot_rows": [],
                }
            ],
            "pagination": {"page": page, "page_size": page_size, "total": 1},
        }


class NonFreshLedgerService:
    def list_grouped_ledger(self, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("bank_detail_read_model_not_fresh")


class FailIfCalledLedgerService:
    def list_grouped_ledger(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("ledger service should not be called for unchanged source versions")

    def list_ledger(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("ledger service should not be called for unchanged source versions")


class MutatingGroupedLedgerService:
    def __init__(self, mutate: object) -> None:
        self._mutate = mutate

    def list_grouped_ledger(self, *, page: int = 1, page_size: int = 200, **_kwargs: object) -> dict[str, object]:
        if callable(self._mutate):
            self._mutate()
        if page > 1:
            return {"groups": [], "pagination": {"page": page, "page_size": page_size, "total": 1}}
        return {
            "groups": [
                {
                    "group_id": "counterparty:personal:version",
                    "counterparty_name": "version",
                    "family": "personal",
                    "family_label": "个人往来",
                    "summary_row": {
                        "row_kind": "summary",
                        "relation_id": "rel-version",
                        "bank_row_ids": ["bank-version-1"],
                    },
                    "flow_rows": [],
                    "allocation_lots": [],
                    "lot_rows": [],
                }
            ],
            "pagination": {"page": page, "page_size": page_size, "total": 1},
        }


class TurnoverLedgerReadModelRefreshServiceTests(unittest.TestCase):
    def test_legacy_turnover_relation_id_requires_explicit_relation_metadata(self) -> None:
        self.assertEqual(
            _turnover_relation_id_from_relation(
                {
                    "case_id": "turnover:turnover_rel_legacy",
                    "special_metadata": {"turnover_relation_id": "turnover_rel_legacy"},
                }
            ),
            "turnover_rel_legacy",
        )
        self.assertEqual(
            _turnover_relation_id_from_relation(
                {
                    "case_id": "turnover:turnover_rel_canonical",
                    "special_metadata": {},
                }
            ),
            "",
        )

    def test_projection_source_versions_include_bank_detail_source_versions(self) -> None:
        class CategoryProvider:
            last_source_versions = {"bank_detail": {"scope_key": "2026-04", "source_version": 12}}

        self.assertEqual(
            _with_bank_detail_source_versions(
                {"turnover_ledger_schema_version": "test"},
                CategoryProvider(),
            ),
            {
                "turnover_ledger_schema_version": "test",
                "bank_detail_source_versions": {"bank_detail": {"scope_key": "2026-04", "source_version": 12}},
            },
        )

    def test_facade_non_fresh_error_does_not_save_turnover_read_model(self) -> None:
        repository = FakeTurnoverReadRepository()
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=NonFreshLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
        )

        with self.assertRaisesRegex(RuntimeError, "bank_detail_read_model_not_fresh"):
            builder.rebuild_turnover_ledger_read_model_scope("all", source_version=10)

        self.assertIsNone(repository.saved_payload)

    def test_projection_preserves_group_breakdowns_tags_and_bank_labels(self) -> None:
        repository = FakeTurnoverReadRepository()
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=9)

        self.assertEqual(result, {"scope_key": "all", "row_count": 1, "source_version": 9})
        self.assertEqual(repository.saved_scope_key, "all")
        rows = list((repository.saved_payload or {}).get("rows") or [])
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["pending_repayment_amount"], "1000.00")
        self.assertEqual(row["pending_collection_amount"], "500.00")
        self.assertEqual(row["bank_account_labels"], ["建行 1001", "工行 2002"])
        self.assertEqual(row["flow_rows"][0]["category_label_path"], ["外部往来款收款", "收回借款", "个人往来"])
        self.assertEqual(row["flow_rows"][0]["bank_account_labels"], ["工行 2002"])
        self.assertEqual(row["flow_rows"][0]["repayment_remark"], "收回周转款 / 收款备注")

    def test_projection_reuses_version_bound_base_rows_across_month_shards(self) -> None:
        repository = FakeTurnoverReadRepository()
        ledger_service = CountingMultiMonthLedgerService()
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=ledger_service,  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "same-version"},
        )

        april = builder.rebuild_turnover_ledger_read_model_scope("2026-04", source_version=10)
        may = builder.rebuild_turnover_ledger_read_model_scope("2026-05", source_version=11)

        self.assertEqual(april["row_count"], 1)
        self.assertEqual(may["row_count"], 1)
        self.assertEqual(ledger_service.calls, 1)

    def test_projection_does_not_reuse_base_rows_after_source_version_changes(self) -> None:
        repository = FakeTurnoverReadRepository()
        ledger_service = CountingMultiMonthLedgerService()
        source_versions = {"turnover_ledger_schema_version": "version-1"}
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=ledger_service,  # type: ignore[arg-type]
            source_versions_provider=lambda: dict(source_versions),
        )

        builder.rebuild_turnover_ledger_read_model_scope("2026-04", source_version=10)
        source_versions["turnover_ledger_schema_version"] = "version-2"
        builder.rebuild_turnover_ledger_read_model_scope("2026-05", source_version=11)

        self.assertEqual(ledger_service.calls, 2)

    def test_projection_source_versions_are_captured_before_relation_rebuild_side_effects(self) -> None:
        repository = FakeTurnoverReadRepository()
        relation_snapshot = {"turnover_relation_snapshot_version": "before-rebuild"}

        def mutate_relation_snapshot() -> None:
            relation_snapshot["turnover_relation_snapshot_version"] = "after-rebuild"

        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=MutatingGroupedLedgerService(mutate_relation_snapshot),  # type: ignore[arg-type]
            source_versions_provider=lambda: dict(relation_snapshot),
        )

        builder.rebuild_turnover_ledger_read_model_scope("all", source_version=14)

        rows = list((repository.saved_payload or {}).get("rows") or [])
        self.assertEqual(
            (repository.saved_payload or {}).get("source_versions"),
            {"turnover_relation_snapshot_version": "before-rebuild"},
        )
        self.assertEqual(
            rows[0]["source_versions"],
            {"turnover_relation_snapshot_version": "before-rebuild"},
        )

    def test_projection_enriches_rows_with_fresh_workbench_relation_context(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.source_rows = [
            {
                "case_id": "case-turnover-001",
                "status": "active",
                "relation_mode": "turnover_manual_closure",
                "row_ids": ["txn-out-collected", "txn-repayment-001"],
                "row_types": ["bank", "bank"],
                "amount_check": {},
                "raw_payload": {"normalized_payload": {"relation_source": "manual"}},
            }
        ]
        repository.source_summary = {"workbench_relation_schema_version": "test"}
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        builder.rebuild_turnover_ledger_read_model_scope("all", source_version=11)

        self.assertEqual(
            repository.source_bundle_calls[0],
            {"scope_key": "all", "row_ids": ["txn-out-collected"]},
        )
        rows = list((repository.saved_payload or {}).get("rows") or [])
        row = rows[0]
        self.assertEqual(row["workbench_relation_status"], "linked")
        self.assertEqual(row["workbench_relation_case_ids"], ["case-turnover-001"])
        self.assertEqual(row["workbench_relation_mode"], "turnover_manual_closure")
        self.assertEqual(row["workbench_relation_source"], "manual")
        self.assertEqual(row["workbench_relation_row_ids"], ["txn-out-collected", "txn-repayment-001"])
        self.assertEqual(
            row["workbench_relations"],
            [
                {
                    "case_id": "case-turnover-001",
                    "relation_status": "linked",
                    "relation_mode": "turnover_manual_closure",
                    "relation_source": "manual",
                    "row_ids": ["txn-out-collected", "txn-repayment-001"],
                    "row_types": ["bank", "bank"],
                }
            ],
        )
        self.assertFalse(row["linked_oa"])
        self.assertFalse(row["linked_invoice"])
        self.assertTrue(row["cash_closure_linked"])
        self.assertEqual(row["cash_closure_case_id"], "case-turnover-001")
        self.assertEqual(row["cash_closure_source"], "turnover_ledger")
        self.assertEqual(row["cash_closure_relation_id"], "")
        self.assertEqual(row["source_versions"]["workbench_relation_source_versions"], {"workbench_relation_schema_version": "test"})
        flow = row["flow_rows"][0]
        self.assertEqual(flow["workbench_relation_status"], "linked")
        self.assertEqual(flow["workbench_relation_case_ids"], ["case-turnover-001"])
        self.assertEqual(flow["workbench_relation_mode"], "turnover_manual_closure")
        self.assertEqual(flow["workbench_relations"], row["workbench_relations"])
        self.assertTrue(flow["cash_closure_linked"])
        self.assertEqual(flow["cash_closure_case_id"], "case-turnover-001")
        self.assertNotIn("__workbench_relation_details", flow)

    def test_projection_skips_unchanged_scope_after_fresh_relation_version_check(self) -> None:
        repository = FakeTurnoverReadRepository()
        relation_source_versions = {"workbench_relation_schema_version": "test"}
        existing_source_versions = {
            "turnover_ledger_schema_version": "test",
            "workbench_relation_source_versions": relation_source_versions,
        }
        repository.existing_payload = {
            "rows": [
                {
                    "relation_id": "rel-existing",
                    "first_transaction_at": "2026-05-18",
                    "flow_rows": [{"source_bank_row_id": "txn-existing"}],
                }
            ],
            "pagination": {"page": 1, "page_size": 200, "total": 83},
            "source_versions": existing_source_versions,
            "read_model_status": "refreshing",
        }
        repository.source_summary = relation_source_versions
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FailIfCalledLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=15)

        self.assertEqual(
            result,
            {
                "scope_key": "all",
                "row_count": 83,
                "source_versions": existing_source_versions,
                "skipped": True,
                "skip_reason": "source_versions_unchanged",
                "generation": 1,
            },
        )
        self.assertEqual(
            repository.acknowledged,
            [{"scope_key": "all", "source_version": 15, "expected_generation": 0}],
        )
        self.assertEqual(repository.list_calls, [{"scope_key": "all", "page": 1, "page_size": 200}])
        self.assertIsNone(repository.saved_payload)
        self.assertEqual(repository.source_bundle_calls, [])
        self.assertEqual(
            repository.source_summary_calls,
            [{"scope_key": "all", "row_ids": ["txn-existing"], "include_row_ids": True}],
        )

    def test_projection_republishes_unchanged_rows_when_scope_summary_is_missing(self) -> None:
        repository = FakeTurnoverReadRepository()
        source_versions = {"turnover_ledger_schema_version": "test"}
        repository.existing_payload = {
            "rows": [
                {
                    "relation_id": "rel-existing",
                    "first_transaction_at": "2026-05-18",
                    "flow_rows": [{"source_bank_row_id": "txn-existing"}],
                }
            ],
            "pagination": {"page": 1, "page_size": 200, "total": 1},
            "source_versions": source_versions,
            "statistics": None,
            "statistics_status": "stale",
        }
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FailIfCalledLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: source_versions,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=16)

        self.assertTrue(result["refreshed_from_existing_scope"])
        self.assertEqual(repository.saved_scope_key, "all")
        self.assertIsNotNone(repository.saved_payload)
        assert repository.saved_payload is not None
        self.assertEqual(repository.saved_payload["rows"][0]["relation_id"], "rel-existing")
        self.assertEqual(repository.saved_payload["rows"][0]["source_versions"], source_versions)

    def test_projection_rebuilds_without_relation_check_when_base_source_versions_changed(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.existing_payload = {
            "rows": [
                {
                    "relation_id": "rel-existing",
                    "first_transaction_at": "2026-05-18",
                    "flow_rows": [{"source_bank_row_id": "txn-existing"}],
                }
            ],
            "pagination": {"page": 1, "page_size": 200, "total": 1},
            "source_versions": {
                "turnover_ledger_schema_version": "old",
                "workbench_relation_source_versions": {"workbench_relation_schema_version": "old"},
            },
        }
        repository.source_summary = {"workbench_relation_schema_version": "current"}
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        builder.rebuild_turnover_ledger_read_model_scope("all", source_version=16)

        self.assertEqual(len(repository.source_bundle_calls), 1)
        self.assertIsNotNone(repository.saved_payload)

    def test_mixed_all_scope_versions_converge_through_full_all_rebuild(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.generation = 6
        repository.existing_payload = {
            "rows": [{"relation_id": "mixed-existing", "first_transaction_at": "2026-05-18"}],
            "pagination": {"page": 1, "page_size": 200, "total": 1},
            "source_versions": {},
            "source_versions_mixed": True,
            "generation": 6,
        }
        expected_source_versions = {"turnover_ledger_schema_version": "current"}
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: expected_source_versions,
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=21)

        self.assertEqual(result["scope_key"], "all")
        self.assertIsNotNone(repository.saved_payload)
        assert repository.saved_payload is not None
        self.assertEqual(repository.saved_payload["expected_generation"], 6)
        self.assertEqual(repository.saved_payload["source_version"], 21)
        self.assertTrue(repository.saved_payload["rows"])
        self.assertTrue(
            all(
                row["source_versions"] == expected_source_versions
                for row in repository.saved_payload["rows"]
            )
        )

    def test_projection_refreshes_month_scope_from_existing_rows_when_only_relation_versions_changed(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.existing_payload = {
            "rows": [
                {
                    "relation_id": "rel-existing",
                    "first_transaction_at": "2026-05-18",
                    "bank_row_ids": ["txn-existing"],
                    "flow_rows": [{"source_bank_row_id": "txn-existing"}],
                }
            ],
            "pagination": {"page": 1, "page_size": 200, "total": 1},
            "source_versions": {
                "turnover_ledger_schema_version": "test",
                "workbench_relation_source_versions": {"workbench_relation_schema_version": "old"},
            },
        }
        relation_source_versions = {"workbench_relation_schema_version": "current"}
        repository.source_summary = relation_source_versions
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FailIfCalledLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("2026-05", source_version=17)

        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 1)
        self.assertTrue(result["refreshed_from_existing_scope"])
        self.assertEqual(result["source_versions"]["workbench_relation_source_versions"], relation_source_versions)
        self.assertEqual(repository.saved_scope_key, "2026-05")
        self.assertIsNotNone(repository.saved_payload)
        assert repository.saved_payload is not None
        saved_rows = repository.saved_payload["rows"]
        self.assertEqual(saved_rows[0]["source_versions"]["workbench_relation_source_versions"], relation_source_versions)
        self.assertEqual(len(repository.source_summary_calls), 1)
        self.assertEqual(len(repository.source_bundle_calls), 1)
        self.assertEqual(repository.list_calls, [{"scope_key": "2026-05", "page": 1, "page_size": 200}])

    def test_projection_refreshes_all_scope_from_existing_rows_when_only_relation_versions_changed(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.existing_payload = {
            "rows": [
                {
                    "relation_id": "rel-existing",
                    "first_transaction_at": "2026-05-18",
                    "bank_row_ids": ["txn-existing"],
                    "flow_rows": [{"source_bank_row_id": "txn-existing"}],
                }
            ],
            "pagination": {"page": 1, "page_size": 200, "total": 1},
            "source_versions": {
                "turnover_ledger_schema_version": "test",
                "workbench_relation_source_versions": {"workbench_relation_schema_version": "old"},
            },
        }
        relation_source_versions = {"workbench_relation_schema_version": "current"}
        repository.source_summary = relation_source_versions
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FailIfCalledLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=18)

        self.assertEqual(result["scope_key"], "all")
        self.assertEqual(result["row_count"], 1)
        self.assertTrue(result["refreshed_from_existing_scope"])
        self.assertEqual(result["source_versions"]["workbench_relation_source_versions"], relation_source_versions)
        self.assertEqual(repository.saved_scope_key, "all")
        self.assertIsNotNone(repository.saved_payload)
        assert repository.saved_payload is not None
        saved_rows = repository.saved_payload["rows"]
        self.assertEqual(saved_rows[0]["source_versions"]["workbench_relation_source_versions"], relation_source_versions)
        self.assertEqual(len(repository.source_summary_calls), 1)
        self.assertEqual(len(repository.source_bundle_calls), 1)

    def test_projection_marks_workbench_bank_pair_as_cash_closure_when_group_zeroes_out(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.source_rows = [
            {
                "case_id": "case-workbench-cash-1",
                "status": "active",
                "relation_mode": "manual_confirmed",
                "row_ids": ["bank-income-240000", "bank-expense-240000"],
                "row_types": ["bank", "bank"],
                "amount_check": {},
                "raw_payload": {"normalized_payload": {"relation_source": "manual"}},
            }
        ]
        repository.source_summary = {"workbench_relation_schema_version": "test"}
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeTwoFlowGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        builder.rebuild_turnover_ledger_read_model_scope("all", source_version=13)

        rows = list((repository.saved_payload or {}).get("rows") or [])
        row = rows[0]
        self.assertTrue(row["cash_closure_linked"])
        self.assertEqual(row["cash_closure_case_id"], "case-workbench-cash-1")
        self.assertEqual(row["cash_closure_source"], "workbench_relation")
        flow_rows = row["flow_rows"]
        self.assertEqual([flow["cash_closure_linked"] for flow in flow_rows], [True, True])
        self.assertEqual([flow["cash_closure_case_id"] for flow in flow_rows], ["case-workbench-cash-1", "case-workbench-cash-1"])
        self.assertNotIn("__workbench_relation_details", row)

    def test_projection_does_not_depend_on_workbench_relation_read_model_freshness(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.source_summary = {
            "source": "workbench_pair_relations",
            "scope_key": "all",
            "relation_count": 0,
            "relation_updated_at": "",
        }
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_read_model_scope("all", source_version=12)

        self.assertEqual(result["row_count"], 1)
        self.assertIsNotNone(repository.saved_payload)

    def test_worker_handler_rebuilds_scope_and_completes_dirty_scope(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = TurnoverLedgerReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="turnover_ledger.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-03",
            scope_type="turnover_ledger",
            scope_key="2026-03",
            dedupe_key=None,
            payload={"scope_type": "turnover_ledger", "scope_key": "2026-03", "source_version": 7},
            attempts=0,
            status="pending",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "2026-03", "row_count": 2})
        self.assertEqual(builder.rebuilt, [("2026-03", 7)])
        self.assertEqual(
            queue.completed,
            [{"tenant_id": "default", "scope_type": "turnover_ledger", "scope_key": "2026-03", "source_version": 7}],
        )

    def test_worker_handler_uses_explicit_relation_delta_contract(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = TurnoverLedgerReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-relation-delta",
            tenant_id="default",
            event_type="turnover_ledger.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-03",
            scope_type="turnover_ledger",
            scope_key="2026-03",
            dedupe_key=None,
            payload={
                "metadata": {
                    "row_ids": ["bank-1", "bank-1", "bank-2"],
                    "relation_deltas": {"case-1": {"status": "active"}},
                }
            },
            attempts=0,
            status="pending",
            source_version=8,
        )

        result = service.handle_runtime_event(event)

        self.assertTrue(result["relation_delta"])
        self.assertEqual(builder.rebuilt, [])
        self.assertEqual(
            builder.rebuilt_relation_deltas,
            [{"scope_key": "2026-03", "row_ids": ["bank-1", "bank-2"], "source_version": 8}],
        )
        self.assertEqual(len(queue.completed), 1)

    def test_worker_handler_does_not_use_relation_delta_for_all_scope(self) -> None:
        builder = FakeProjectionBuilder()
        service = TurnoverLedgerReadModelRefreshService(projection_builder=builder)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="default",
            event_type="turnover_ledger.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="turnover_ledger",
            scope_key="all",
            dedupe_key=None,
            payload={
                "metadata": {
                    "row_ids": ["bank-1"],
                    "relation_deltas": {"case-1": {"status": "active"}},
                }
            },
            attempts=0,
            status="pending",
        )

        service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, [("all", None)])
        self.assertEqual(builder.rebuilt_relation_deltas, [])

    def test_projection_relation_delta_reenriches_only_overlapping_rows(self) -> None:
        repository = FakeTurnoverReadRepository()
        repository.relation_delta_payload = {
            "scope_exists": True,
            "source_versions": {"turnover_ledger_schema_version": "test"},
            "source_versions_mixed": False,
            "rows": [
                {
                    "relation_id": "relation-2026-03",
                    "first_transaction_at": "2026-03-01",
                    "bank_row_ids": ["bank-1"],
                    "flow_rows": [{"source_bank_row_id": "bank-1", "bank_row_ids": ["bank-1"]}],
                }
            ],
        }
        repository.source_rows = [
            {
                "case_id": "case-1",
                "status": "active",
                "relation_mode": "turnover_manual_closure",
                "row_ids": ["bank-1", "bank-2"],
                "row_types": ["bank", "bank"],
                "raw_payload": {"normalized_payload": {"case_id": "case-1"}},
            }
        ]
        repository.source_summary = {
            "source": "workbench_pair_relations",
            "scope_key": "2026-03",
            "relation_count": 1,
            "relation_updated_at": "2026-07-20T12:00:00+00:00",
        }
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FailIfCalledLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"should_not_be_loaded": True},
            workbench_relation_source_repository=repository,
        )

        result = builder.rebuild_turnover_ledger_relation_delta(
            "2026-03",
            row_ids=["bank-1", "bank-2"],
            source_version=9,
        )

        self.assertTrue(result["relation_delta"])
        self.assertEqual(repository.saved_relation_delta_scope_key, "2026-03")
        rows = list((repository.saved_relation_delta or {}).get("rows") or [])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["cash_closure_linked"])
        self.assertEqual(rows[0]["cash_closure_case_id"], "case-1")
        self.assertEqual(
            rows[0]["source_versions"]["workbench_relation_source_versions"]["relation_count"],
            1,
        )

    def test_worker_handler_rejects_wrong_event_type(self) -> None:
        service = TurnoverLedgerReadModelRefreshService(projection_builder=FakeProjectionBuilder())
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="default",
            event_type="bank_detail.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-03",
            scope_type="turnover_ledger",
            scope_key="2026-03",
            dedupe_key=None,
            payload={},
            attempts=0,
            status="pending",
        )

        with self.assertRaises(ValueError):
            service.handle_runtime_event(event)


if __name__ == "__main__":
    unittest.main()
