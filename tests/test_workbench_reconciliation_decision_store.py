from __future__ import annotations

import unittest
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_EXPIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_SUPPRESSED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
    MATCH_DOMAIN_FREE,
    WorkbenchDecision,
)


def decision(
    key: str,
    *,
    scope_month: str = "2026-05",
    status: str = DECISION_STATUS_PAIRED,
    row_ids: tuple[str, ...] = ("oa-1", "bank-1"),
    source_versions: dict[str, object] | None = None,
) -> WorkbenchDecision:
    return WorkbenchDecision(
        decision_id=key,
        decision_key=key,
        scope_month=scope_month,
        display_state=DISPLAY_STATE_PAIRED if status == DECISION_STATUS_PAIRED else DISPLAY_STATE_OPEN,
        decision_status=status,
        match_domain=MATCH_DOMAIN_FREE,
        match_shape="oa_bank",
        rule_code="free.oa_bank",
        rule_version="v1",
        row_ids=row_ids,
        oa_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("oa-")),
        bank_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("bank-")),
        invoice_row_ids=tuple(row_id for row_id in row_ids if row_id.startswith("invoice-")),
        amount="100.00",
        direction="expense",
        payment_amount_closed=True,
        invoice_amount_closed=False,
        source_versions=source_versions or {"oa": 1, "bank": 1},
    )


class WorkbenchReconciliationDecisionStoreTests(unittest.TestCase):
    def test_upsert_is_idempotent_by_decision_key_and_list_filters_by_scope_status(self) -> None:
        store = WorkbenchReconciliationDecisionStore()

        store.upsert_decisions([decision("decision-a", status=DECISION_STATUS_PAIRED)])
        store.upsert_decisions([decision("decision-a", status=DECISION_STATUS_OPEN, row_ids=("oa-2",))])
        store.upsert_decisions([decision("decision-b", scope_month="2026-06", status=DECISION_STATUS_PAIRED)])

        self.assertEqual(
            [item["decision_key"] for item in store.list_decisions("2026-05")],
            ["decision-a"],
        )
        self.assertEqual(
            store.list_decisions("2026-05", statuses={DECISION_STATUS_PAIRED}),
            [],
        )
        open_rows = store.list_decisions("2026-05", statuses={DECISION_STATUS_OPEN})
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0]["row_ids"], ["oa-2"])

    def test_consume_and_suppress_by_row_ids_update_overlapping_active_decisions(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        store.upsert_decisions(
            [
                decision("decision-a", row_ids=("oa-1", "bank-1")),
                decision("decision-b", row_ids=("oa-2", "bank-2")),
                decision("decision-c", status=DECISION_STATUS_OPEN, row_ids=("oa-3",)),
            ]
        )

        self.assertEqual(store.consume_by_row_ids(["bank-1", "missing"], relation_id="relation-1"), 1)
        self.assertEqual(store.suppress_by_row_ids(["oa-3"], exception_case_id="exception-1"), 1)

        rows = {item["decision_key"]: item for item in store.list_decisions("2026-05")}
        self.assertEqual(rows["decision-a"]["decision_status"], DECISION_STATUS_CONSUMED)
        self.assertEqual(rows["decision-a"]["consumed_by_relation_id"], "relation-1")
        self.assertEqual(rows["decision-c"]["decision_status"], DECISION_STATUS_SUPPRESSED)
        self.assertEqual(rows["decision-c"]["suppressed_by_exception_case_id"], "exception-1")
        self.assertEqual(rows["decision-b"]["decision_status"], DECISION_STATUS_PAIRED)

    def test_expire_stale_source_versions_only_marks_changed_scope_decisions(self) -> None:
        store = WorkbenchReconciliationDecisionStore()
        store.upsert_decisions(
            [
                decision("stale", source_versions={"oa": 1, "bank": 1}),
                decision("fresh", row_ids=("oa-2",), source_versions={"oa": 2, "bank": 1}),
                decision("other-month", scope_month="2026-06", source_versions={"oa": 1}),
            ]
        )

        self.assertEqual(store.expire_stale(["2026-05"], source_versions={"oa": 2, "bank": 1}), 1)

        rows = {item["decision_key"]: item for item in store.list_decisions("2026-05")}
        self.assertEqual(rows["stale"]["decision_status"], DECISION_STATUS_EXPIRED)
        self.assertEqual(rows["fresh"]["decision_status"], DECISION_STATUS_PAIRED)

    def test_repository_lifecycle_updates_use_text_case_ids_and_jsonb_subset_versions(self) -> None:
        connection = RepositoryRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.consume_workbench_reconciliation_decisions_by_row_ids(
            tenant_id="tenant-a",
            row_ids=["oa-1"],
            relation_id="CASE-REL-1",
        )
        repository.suppress_workbench_reconciliation_decisions_by_row_ids(
            tenant_id="tenant-a",
            row_ids=["oa-2"],
            exception_case_id="CASE-EX-1",
        )
        with patch("fin_ops_platform.services.postgres_repositories.read_models.jsonb", side_effect=lambda value: value):
            repository.expire_stale_workbench_reconciliation_decisions(
                tenant_id="tenant-a",
                scope_months=["2026-05"],
                source_versions={"rules": "v2"},
            )

        consume_sql, consume_params = connection.execute_calls[0]
        suppress_sql, suppress_params = connection.execute_calls[1]
        expire_sql, expire_params = connection.execute_calls[2]
        self.assertNotIn("::uuid", consume_sql)
        self.assertNotIn("::uuid", suppress_sql)
        self.assertIn("CASE-REL-1", consume_params)
        self.assertIn("CASE-EX-1", suppress_params)
        self.assertIn("not (source_versions @>", expire_sql)
        self.assertIn("scope_month = any(%s::date[])", expire_sql)
        self.assertNotIn("to_char(scope_month", expire_sql)
        self.assertEqual(expire_params[1], ["2026-05-01"])

    def test_repository_cleanup_audit_lists_active_relation_overlaps_in_matching_window(self) -> None:
        connection = RepositoryRecordingConnection(
            fetch_all_rows=[
                {
                    "decision_key": "decision-bad",
                    "scope_month": "2026-02-01",
                    "display_state": "paired",
                    "decision_status": "paired",
                    "match_domain": "free",
                    "match_shape": "oa_bank",
                    "rule_code": "oa_bank_exact_sum",
                    "rule_version": "v1",
                    "row_ids": ["oa-pay-2050", "txn_imported_1385"],
                    "oa_row_ids": ["oa-pay-2050"],
                    "bank_row_ids": ["txn_imported_1385"],
                    "invoice_row_ids": [],
                    "amount": "9600.00",
                    "direction": "expenditure",
                    "payment_amount_closed": True,
                    "invoice_amount_closed": False,
                    "warnings": [],
                    "evidence": {},
                    "blockers": [],
                    "source_versions": {},
                    "consumed_by_relation_id": None,
                    "suppressed_by_exception_case_id": None,
                    "decision_id": "decision-bad",
                    "explanation": "",
                    "raw_payload": {},
                    "active_relation_overlaps": [
                        {
                            "case_id": "no_oa_batch_b1a825c98bf5d29b67f0",
                            "relation_mode": "no_oa_bank_batch",
                            "month_scope": "2026-03",
                            "overlap_row_ids": ["txn_imported_1385"],
                        }
                    ],
                    "submitted_no_oa_batch_overlaps": [
                        {
                            "batch_id": "no_oa_batch_b1a825c98bf5d29b67f0",
                            "batch_type": "internal_transfer",
                            "scope_month": "2026-03",
                            "overlap_row_ids": ["txn_imported_1385"],
                        }
                    ],
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        rows = repository.list_active_workbench_reconciliation_decisions_for_cleanup(
            tenant_id="tenant-a",
            scope_months=["2026-02"],
        )

        self.assertEqual(rows[0]["decision_key"], "decision-bad")
        self.assertEqual(rows[0]["active_relation_overlaps"][0]["overlap_row_ids"], ["txn_imported_1385"])
        self.assertEqual(rows[0]["submitted_no_oa_batch_overlaps"][0]["overlap_row_ids"], ["txn_imported_1385"])
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("from app.workbench_pair_relations", sql)
        self.assertIn("from app.no_oa_bank_batches", sql)
        self.assertIn("batch.status = 'submitted'", sql)
        self.assertIn("interval '2 months'", sql)
        self.assertEqual(params[0], "tenant-a")
        self.assertEqual(params[1], ["2026-02-01"])

    def test_repository_cleanup_execute_expires_by_key_and_enqueues_relation_refresh(self) -> None:
        connection = RepositoryRecordingConnection(
            fetch_all_rows=[{"scope_key": "2026-02", "expired_count": 1}]
        )
        repository = PostgresReadModelRepository(connection)

        result = repository.expire_workbench_reconciliation_decisions_by_keys(
            tenant_id="tenant-a",
            decision_keys=["decision-bad"],
            reason="unit-test",
        )

        self.assertEqual(result, {"expired_count": 1, "scope_keys": ["2026-02"]})
        expire_sql, expire_params = connection.fetch_all_calls[0]
        self.assertIn("update read_model.workbench_reconciliation_decisions", expire_sql)
        self.assertIn("decision_status = 'expired'", expire_sql)
        self.assertEqual(expire_params[0], "unit-test")
        self.assertEqual(expire_params[2], "tenant-a")
        self.assertEqual(expire_params[3], ["decision-bad"])
        self.assertTrue(
            any(
                params[1] == "2026-02" and params[2] == "workbench_reconciliation_decision_expired"
                for _sql, params in connection.fetch_one_calls
            )
        )


class RepositoryRecordingConnection:
    def __init__(self, *, fetch_all_rows: list[dict[str, object]] | None = None) -> None:
        self.execute_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_all_rows = list(fetch_all_rows or [])

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1

    def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, int]:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return {"source_version": 1}

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        return list(self.fetch_all_rows)


if __name__ == "__main__":
    unittest.main()
