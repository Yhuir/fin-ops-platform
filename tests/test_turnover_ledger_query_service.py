from __future__ import annotations

import inspect
import unittest

from fin_ops_platform.services.postgres_repositories.read_models import PostgresSummaryReadModelRepository
from fin_ops_platform.services.turnover_ledger_query_service import TurnoverLedgerQueryService
from fin_ops_platform.services.turnover_ledger_read_model_repository import TurnoverLedgerReadModelRepositoryPort


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


class FakeRepository:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def list_turnover_ledger_view(self, **kwargs: object) -> dict[str, object] | None:
        self.calls.append(dict(kwargs))
        return self.payload


class TurnoverLedgerQueryServiceTests(unittest.TestCase):
    def test_repository_query_is_bounded_and_has_no_raw_payload_fallback(self) -> None:
        source = inspect.getsource(PostgresSummaryReadModelRepository.list_turnover_ledger_view)

        self.assertIn("limit %s offset %s", source.lower())
        self.assertIn("sum(pending_repayment_amount)", source)
        self.assertNotIn("raw_payload", source)
        self.assertNotIn("_turnover_ledger_row_payload", source)

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
        self.assertEqual(payload["rows"], [{"relation_id": "stale"}])
        self.assertEqual(queue.enqueued, [{"scope_type": "turnover_ledger", "scope_key": "all", "reason": "api_stale"}])

    def test_fresh_sql_read_model_is_returned_without_legacy_rebuild(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "fresh"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {"turnover_ledger_schema_version": "same"},
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
        self.assertEqual(repository.calls[0]["family"], "company")
        self.assertEqual(repository.calls[0]["page"], 2)
        self.assertEqual(queue.enqueued, [])

    def test_mixed_all_scope_row_versions_use_dirty_scope_status_instead_of_reenqueueing_all(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "mixed"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {},
                "source_versions_mixed": True,
                "refresh_status": "fresh",
                "read_model_status": "fresh",
            }
        )
        service = TurnoverLedgerQueryService(
            read_repository=repository,
            refresh_queue_repository=queue,
            source_versions_provider=lambda: {"turnover_ledger_schema_version": "current"},
        )

        payload = service.list_ledger(family="all", direction="all", status=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertFalse(payload["refresh_enqueued"])
        self.assertEqual(payload["source_versions"], {"turnover_ledger_schema_version": "current"})
        self.assertEqual(queue.enqueued, [])

    def test_mixed_all_scope_row_versions_still_refresh_when_dirty_scope_is_active(self) -> None:
        queue = FakeQueue()
        repository = FakeRepository(
            {
                "rows": [{"relation_id": "mixed-refreshing"}],
                "pagination": {"page": 1, "page_size": 50, "total": 1},
                "source_versions": {},
                "source_versions_mixed": True,
                "refresh_status": "processing",
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
        self.assertEqual(payload["refresh_reason"], "source_version_mismatch")
        self.assertEqual(payload["source_versions"], {})

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
                    "save_turnover_ledger_rows",
                    {"payload": {"rows": []}, "scope_key": "all"},
                ),
            ],
        )


if __name__ == "__main__":
    unittest.main()
