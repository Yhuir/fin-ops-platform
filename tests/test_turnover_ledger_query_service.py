from __future__ import annotations

import inspect
import unittest

from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresSummaryReadModelRepository,
    _turnover_ledger_page_statistics,
)
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService
from fin_ops_platform.services.turnover_ledger_read_model_repository import TurnoverLedgerReadModelRepositoryPort


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


class FakeRepository:
    def __init__(
        self,
        payload: dict[str, object] | None,
        *,
        changes: list[dict[str, object]] | None = None,
    ) -> None:
        self.payload = payload
        self.changes = list(changes or [])
        self.calls: list[dict[str, object]] = []

    def get_turnover_ledger_freshness_view(self) -> dict[str, object] | None:
        if not isinstance(self.payload, dict):
            return None
        return {
            "source_versions": dict(self.payload.get("source_versions") or {}),
            "refresh_status": self.payload.get("refresh_status") or "fresh",
        }

    def list_turnover_manual_closure_changes(
        self,
        *,
        updated_after: str,
    ) -> list[dict[str, object]]:
        self.change_updated_after = updated_after
        return list(self.changes)

    def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object] | None:
        self.calls.append(dict(kwargs))
        return self.payload


class TurnoverLedgerQueryServiceTests(unittest.TestCase):
    def test_repository_query_is_bounded_and_reads_precomputed_scope_statistics(self) -> None:
        source = inspect.getsource(PostgresSummaryReadModelRepository.list_turnover_ledger_view)

        self.assertIn("limit %s offset %s", source.lower())
        self.assertIn("sum(pending_repayment_amount)", source)
        self.assertIn("read_model.turnover_ledger_scopes", source)
        self.assertIn("scope_summary as materialized", source)
        version_proof_source = source.partition("), version_proof as (")[2].partition(
            "), statistics as ("
        )[0]
        self.assertIn("exists (select 1 from scope_summary)", version_proof_source)
        self.assertNotIn("from base", version_proof_source)
        self.assertNotIn("jsonb_array_elements", source)
        self.assertNotIn("statistics_flows", source)
        self.assertNotIn("raw_payload", source)
        self.assertNotIn("_turnover_ledger_row_payload", source)

    def test_page_statistics_keep_unique_flow_and_group_counts_separate(self) -> None:
        statistics = _turnover_ledger_page_statistics(
            {
                "statistics_transaction_count": 9,
                "statistics_expense_transaction_count": 5,
                "statistics_income_transaction_count": 4,
                "statistics_ledger_group_count": 6,
                "statistics_closed_group_count": 2,
                "statistics_linked_oa_transaction_count": 3,
                "statistics_linked_invoice_transaction_count": 4,
            }
        )

        self.assertEqual(statistics["transaction_count"], 9)
        self.assertEqual(statistics["ledger_group_count"], 6)
        self.assertEqual(statistics["closed_group_count"], 2)
        self.assertEqual(statistics["unclosed_group_count"], 4)
        self.assertEqual(statistics["linked_oa_transaction_count"], 3)
        self.assertEqual(statistics["linked_invoice_transaction_count"], 4)

    def test_stale_sql_read_model_is_not_returned_as_fresh_and_enqueues_refresh(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "stale"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {"turnover_ledger_schema_version": "old"},
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "new"},
        )

        payload = service.list_ledger(family="all", direction="all", status=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.enqueued, [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_stale"}])

    def test_fresh_sql_read_model_is_returned_without_legacy_rebuild(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "fresh"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {"turnover_ledger_schema_version": "same"},
                "generation": 7,
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "same"},
        )

        payload = service.list_ledger(family="company", direction="all", status=None, page=2, page_size=25)

        self.assertEqual(payload["rows"], [{"relation_id": "fresh"}])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertNotIn("generation", payload)
        self.assertEqual(repository.calls[0]["family"], "company")
        self.assertEqual(repository.calls[0]["page"], 2)
        self.assertEqual(queue.enqueued, [])

    def test_scope_proof_mismatch_fails_closed_even_when_row_payload_claims_fresh(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "mixed"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {},
                "source_versions_mixed": True,
                "refresh_status": "fresh",
                "read_model_status": "fresh",
                "statistics": {"transaction_count": 3},
                "statistics_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "current"},
        )

        payload = service.list_ledger(family="all", direction="all", status=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertEqual(payload["source_versions"], {})
        self.assertIsNone(payload["statistics"])
        self.assertEqual(payload["statistics_status"], "refreshing")
        self.assertEqual(
            queue.enqueued,
            [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_stale"}],
        )

    def test_active_exact_scope_returns_lightweight_refreshing_payload_without_duplicate_enqueue(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "mixed-refreshing"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {},
                "source_versions_mixed": True,
                "refresh_status": "refreshing",
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "current"},
        )

        payload = service.list_ledger(family="all", direction="all", status=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_stale")
        self.assertEqual(payload["source_versions"], {})
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.enqueued, [])

    def test_manual_closure_mismatch_enqueues_exact_month_deltas_instead_of_all(self) -> None:
        queue = FakeQueue()
        actual_closure = {
            "source": "workbench_pair_relations",
            "scope_key": "all",
            "relation_count": 2,
            "relation_updated_at": "2026-07-24 10:00:00+00",
        }
        expected_closure = {
            **actual_closure,
            "relation_count": 3,
            "relation_updated_at": "2026-07-24 10:01:00+00",
        }
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "stale"}],
                "source_versions": {
                    "turnover_ledger_schema_version": "same",
                    "turnover_manual_closure_source_version": actual_closure,
                },
            },
            changes=[
                {
                    "case_id": "turnover:case-1",
                    "status": "active",
                    "row_ids": ["bank-1", "bank-2"],
                    "affected_months": ["2026-02", "2026-03"],
                    "updated_at": "2026-07-24 10:01:00+00",
                }
            ],
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {
                "turnover_ledger_schema_version": "same",
                "turnover_manual_closure_source_version": expected_closure,
            },
        )

        payload = service.list_ledger(
            family="all",
            direction="all",
            status=None,
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_relation_delta")
        self.assertEqual(payload["refresh_scope_keys"], ["2026-02", "2026-03"])
        self.assertEqual(repository.calls, [])
        self.assertEqual(repository.change_updated_after, "2026-07-24 10:00:00+00")
        self.assertEqual(
            [(item["scope_key"], item["reason"]) for item in queue.enqueued],
            [
                ("2026-02", "api_relation_delta"),
                ("2026-03", "api_relation_delta"),
            ],
        )
        self.assertTrue(
            all(
                item["metadata"]["row_ids"] == ["bank-1", "bank-2"]
                for item in queue.enqueued
            )
        )

    def test_missing_required_sql_read_model_returns_empty_refreshing_payload_and_enqueues_miss(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(None)
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "expected"},
        )

        payload = service.list_ledger(family="personal", direction="income", status="suggested", page=0, page_size=999)

        self.assertEqual(payload["rows"], [])
        self.assertNotIn("generation", payload)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertTrue(payload["refresh_enqueued"])
        self.assertEqual(payload["refresh_reason"], "api_miss")
        self.assertEqual(payload["source_versions"], {"turnover_ledger_schema_version": "expected"})
        self.assertEqual(payload["filters"], {"family": "personal", "direction": "income", "status": "suggested"})
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 200, "total": 0})
        self.assertEqual(queue.enqueued, [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_miss"}])

    def test_missing_repository_method_fails_closed_and_enqueues_miss(self) -> None:
        queue = FakeQueue()
        service = TurnoverLedgerQueryService(
            read_repository=object(),
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "expected"},
        )

        payload = service.list_ledger(family="company", direction="all", status=None, page=3, page_size=25)

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_miss")
        self.assertEqual(payload["source_versions"], {"turnover_ledger_schema_version": "expected"})
        self.assertEqual(queue.enqueued, [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_miss"}])


class TurnoverLedgerReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("list_turnover_ledger_view", dict(kwargs)))
                return {"rows": [{"relation_id": "turnover-1"}]}

            def get_turnover_ledger_freshness_view(self) -> dict[str, object]:
                self.calls.append(("get_turnover_ledger_freshness_view", {}))
                return {"source_versions": {"proof": "v1"}, "refresh_status": "fresh"}

            def list_turnover_manual_closure_changes(
                self,
                *,
                updated_after: str,
            ) -> list[dict[str, object]]:
                self.calls.append(
                    (
                        "list_turnover_manual_closure_changes",
                        {"updated_after": updated_after},
                    )
                )
                return [{"case_id": "case-1"}]

            def save_turnover_ledger_rows(self, payload: dict[str, object], *, scope_key: str | None = None) -> None:
                self.calls.append(
                    (
                        "save_turnover_ledger_rows",
                        {"payload": dict(payload), "scope_key": scope_key},
                    )
                )

            def get_cost_statistics_view(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("cost statistics should not be exposed through turnover port")

            def get_tax_offset_view(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("tax offset should not be exposed through turnover port")

            def search_index(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("search should not be exposed through turnover port")

            def list_no_oa_bank_batch_rows(self, **_kwargs: object) -> list[dict[str, object]]:
                raise AssertionError("no-OA should not be exposed through turnover port")

            def list_bank_detail_transactions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("bank detail should not be exposed through turnover port")

        repository = Repository()
        port = TurnoverLedgerReadModelRepositoryPort(repository)

        self.assertEqual(
            port.list_turnover_ledger_view(
                family="personal",
                direction="income",
                status="suggested",
                page=2,
                page_size=25,
                scope_key="all",
            ),
            {"rows": [{"relation_id": "turnover-1"}]},
        )
        self.assertEqual(
            port.get_turnover_ledger_freshness_view(),
            {"source_versions": {"proof": "v1"}, "refresh_status": "fresh"},
        )
        self.assertEqual(
            port.list_turnover_manual_closure_changes(updated_after="v1"),
            [{"case_id": "case-1"}],
        )
        port.save_turnover_ledger_rows({"rows": []}, scope_key="all")

        self.assertFalse(hasattr(port, "clear_turnover_ledger_rows"))
        self.assertFalse(hasattr(port, "get_cost_statistics_view"))
        self.assertFalse(hasattr(port, "get_tax_offset_view"))
        self.assertFalse(hasattr(port, "search_index"))
        self.assertFalse(hasattr(port, "list_no_oa_bank_batch_rows"))
        self.assertFalse(hasattr(port, "list_bank_detail_transactions"))
        self.assertEqual(
            repository.calls,
            [
                (
                    "list_turnover_ledger_view",
                    {
                        "family": "personal",
                        "direction": "income",
                        "status": "suggested",
                        "page": 2,
                        "page_size": 25,
                        "scope_key": "all",
                    },
                ),
                (
                    "get_turnover_ledger_freshness_view",
                    {},
                ),
                (
                    "list_turnover_manual_closure_changes",
                    {"updated_after": "v1"},
                ),
                (
                    "save_turnover_ledger_rows",
                    {"payload": {"rows": []}, "scope_key": "all"},
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
