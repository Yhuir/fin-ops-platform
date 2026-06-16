from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.turnover_ledger_read_model_refresh import TurnoverLedgerReadModelRefreshService
from fin_ops_platform.services.turnover_ledger_sql_projection import (
    TurnoverLedgerSqlProjectionBuilder,
    _with_bank_detail_source_versions,
)


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[tuple[str, object]] = []

    def rebuild_turnover_ledger_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, object]:
        self.rebuilt.append((scope_key, source_version))
        return {"scope_key": scope_key, "row_count": 2}


class FakeQueue:
    def __init__(self) -> None:
        self.completed: list[dict[str, object]] = []

    def complete_read_model_refresh(self, **kwargs: object) -> None:
        self.completed.append(dict(kwargs))


class FakeTurnoverReadRepository:
    def __init__(self) -> None:
        self.saved_payload: dict[str, object] | None = None
        self.saved_scope_key: str | None = None

    def save_turnover_ledger_rows(self, payload: dict[str, object], *, scope_key: str | None = None) -> None:
        self.saved_payload = payload
        self.saved_scope_key = scope_key


class FakeWorkbenchRelationFacade:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    @property
    def last_source_versions(self) -> dict[str, object]:
        source_versions = self.payload.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def get_by_row_ids(self, row_ids: list[str], **kwargs: object) -> dict[str, object]:
        self.calls.append({"row_ids": list(row_ids), **dict(kwargs)})
        return self.payload


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


class NonFreshLedgerService:
    def list_grouped_ledger(self, **_kwargs: object) -> dict[str, object]:
        raise RuntimeError("bank_detail_read_model_not_fresh")


class TurnoverLedgerReadModelRefreshServiceTests(unittest.TestCase):
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

    def test_projection_enriches_rows_with_fresh_workbench_relation_context(self) -> None:
        repository = FakeTurnoverReadRepository()
        relation_facade = FakeWorkbenchRelationFacade(
            {
                "status": "fresh",
                "rows": [
                    {
                        "row_id": "txn-out-collected",
                        "row_type": "bank_transaction",
                        "relation_status": "linked",
                        "group_ids": ["case-turnover-001"],
                    }
                ],
                "groups": [
                    {
                        "group_id": "case-turnover-001",
                        "relation_status": "linked",
                        "relation_source": "manual",
                        "payload": {
                            "relation_mode": "turnover_manual_closure",
                            "row_ids": ["txn-out-collected", "txn-repayment-001"],
                            "row_types": ["bank", "bank"],
                        },
                    }
                ],
                "source_versions": {"workbench_relation_schema_version": "test"},
                "read_model_scope_keys": ["2026-05"],
            }
        )
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_read_facade=relation_facade,
        )

        builder.rebuild_turnover_ledger_read_model_scope("all", source_version=11)

        self.assertEqual(relation_facade.calls[0]["row_ids"], ["txn-out-collected"])
        rows = list((repository.saved_payload or {}).get("rows") or [])
        row = rows[0]
        self.assertEqual(row["workbench_relation_status"], "linked")
        self.assertEqual(row["workbench_relation_case_ids"], ["case-turnover-001"])
        self.assertEqual(row["workbench_relation_mode"], "turnover_manual_closure")
        self.assertEqual(row["workbench_relation_source"], "manual")
        self.assertEqual(row["workbench_relation_row_ids"], ["txn-out-collected", "txn-repayment-001"])
        self.assertEqual(row["source_versions"]["workbench_relation_source_versions"], {"workbench_relation_schema_version": "test"})
        flow = row["flow_rows"][0]
        self.assertEqual(flow["workbench_relation_status"], "linked")
        self.assertEqual(flow["workbench_relation_case_ids"], ["case-turnover-001"])
        self.assertEqual(flow["workbench_relation_mode"], "turnover_manual_closure")

    def test_projection_does_not_save_when_workbench_relation_context_is_not_fresh(self) -> None:
        repository = FakeTurnoverReadRepository()
        builder = TurnoverLedgerSqlProjectionBuilder(
            read_repository=repository,
            ledger_service=FakeGroupedLedgerService(),  # type: ignore[arg-type]
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "test"},
            workbench_relation_read_facade=FakeWorkbenchRelationFacade(
                {
                    "status": "stale",
                    "rows": [],
                    "groups": [],
                    "read_model_scope_keys": ["2026-05"],
                    "stale_reasons": ["source_version_mismatch"],
                }
            ),
        )

        with self.assertRaisesRegex(RuntimeError, "workbench_relation_read_model_not_fresh"):
            builder.rebuild_turnover_ledger_read_model_scope("all", source_version=12)

        self.assertIsNone(repository.saved_payload)

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
