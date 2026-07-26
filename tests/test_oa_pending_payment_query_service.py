from __future__ import annotations

from contextlib import contextmanager
from hashlib import sha1
import json
import unittest

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_pending_payment_query_contract import OaPendingPaymentError
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    PostgresOaPendingPaymentQueryRepository,
)


class OaPendingPaymentQueryServiceTests(unittest.TestCase):
    def test_rows_use_one_snapshot_and_return_only_canonical_page_contract(self) -> None:
        repository = CanonicalQueryRepository()
        service = OaPendingPaymentQueryService(repository=repository)

        payload = service.rows(
            {
                "month": ["2026-05"],
                "keyword": ["申请人"],
                "trade_date_from": ["2026-05-01"],
                "trade_date_to": ["2026-05-31"],
                "filters": [
                    json.dumps(
                        [{"field": "oa_applicant", "operator": "contains", "value": "测试"}],
                        ensure_ascii=False,
                    )
                ],
                "sort_field": ["oa_amount"],
                "sort_direction": ["asc"],
                "page": ["2"],
                "page_size": ["20"],
                "view_mode": ["completed"],
            },
            tenant_id="tenant-a",
        )

        self.assertEqual(repository.snapshot_entries, 1)
        self.assertEqual(repository.snapshot_exits, 1)
        self.assertEqual(repository.select_calls[0]["tenant_id"], "tenant-a")
        self.assertEqual(repository.select_calls[0]["page"], 2)
        self.assertEqual(repository.select_calls[0]["sort_field"], "oa_amount")
        self.assertEqual(payload["rows"][0]["oa"]["id"], "oa-canonical-1")
        self.assertEqual(payload["pagination"], {"page": 2, "pageSize": 20, "total": 1})
        self.assertEqual(payload["summary"]["rowCount"], 1)
        self.assertEqual(payload["viewMode"], "completed")
        for legacy_key in (
            "operationBarrierTargets",
            "readModelStatus",
            "read_model_status",
            "sourceVersions",
            "source_versions",
        ):
            self.assertNotIn(legacy_key, payload)

    def test_empty_page_does_not_hydrate_and_invalid_queries_fail_before_snapshot(self) -> None:
        repository = CanonicalQueryRepository(empty=True)
        service = OaPendingPaymentQueryService(repository=repository)

        payload = service.rows({"page": ["1"], "page_size": ["20"]}, tenant_id="default")

        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["summary"]["rowCount"], 0)
        self.assertEqual(repository.load_calls, [])

        for query, code in (
            ({"month": ["2026-13"]}, "invalid_month"),
            ({"page": ["0"]}, "invalid_paging"),
            (
                {"trade_date_from": ["2026-05-02"], "trade_date_to": ["2026-05-01"]},
                "invalid_trade_date_range",
            ),
        ):
            with self.subTest(query=query), self.assertRaises(OaPendingPaymentError) as caught:
                service.rows(query, tenant_id="default")
            self.assertEqual(caught.exception.error_code, code)
        self.assertEqual(repository.snapshot_entries, 1)

    def test_details_share_canonical_hydration_and_missing_rows_are_404(self) -> None:
        repository = CanonicalQueryRepository()
        service = OaPendingPaymentQueryService(repository=repository)

        detail = service.oa_detail(
            "oa-canonical-1",
            tenant_id="tenant-a",
            requested_scope_key="2026-05",
        )

        self.assertEqual(detail["id"], "oa-canonical-1")
        self.assertEqual(repository.find_calls[0]["tenant_id"], "tenant-a")
        self.assertEqual(repository.find_calls[0]["month"], "2026-05")

        repository.missing_detail = True
        with self.assertRaises(OaPendingPaymentError) as caught:
            service.bank_transaction_detail("missing-bank", tenant_id="tenant-a")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.error_code, "bank_transaction_not_found")

    def test_bank_candidates_use_canonical_snapshot_and_preserve_query_contract(self) -> None:
        repository = CanonicalQueryRepository()
        service = OaPendingPaymentQueryService(repository=repository)

        payload = service.bank_transaction_candidates(
            {
                "relation_status": ["matched"],
                "keyword": ["供应商"],
                "oa_row_ids": ["oa-1", "oa-2", "oa-1"],
                "page": ["2"],
                "page_size": ["20"],
            },
            tenant_id="tenant-a",
        )

        self.assertEqual(repository.snapshot_entries, 1)
        self.assertEqual(repository.snapshot_exits, 1)
        self.assertEqual(repository.candidate_calls[0]["tenant_id"], "tenant-a")
        self.assertEqual(repository.candidate_calls[0]["relation_status"], "matched")
        self.assertEqual(repository.candidate_calls[0]["page"], 2)
        self.assertEqual(payload["rows"][0]["id"], "bank-canonical-1")
        self.assertEqual(payload["filters"]["oaRowIds"], ["oa-1", "oa-2"])


class PostgresOaPendingPaymentQueryRepositoryTests(unittest.TestCase):
    def test_selector_uses_canonical_tables_active_relations_and_server_paging(self) -> None:
        connection = RecordingConnection()
        repository = PostgresOaPendingPaymentQueryRepository(connection)

        result = repository.select_page(
            tenant_id="tenant-a",
            month="2026-05",
            keyword="供应商",
            trade_date_from="2026-05-01",
            trade_date_to="2026-05-31",
            filters=[{"field": "bank_direction", "operator": "in", "values": ["outflow"]}],
            sort_field="bank_trade_time",
            sort_direction="desc",
            page=3,
            page_size=20,
            view_mode="completed",
        )

        self.assertEqual(len(connection.fetch_one_calls), 1)
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("from app.oa_applications", sql)
        self.assertIn("from app.oa_pending_payment_admissions", sql)
        self.assertIn("from app.workbench_pair_relations", sql)
        self.assertIn("relation.status = 'active'", sql)
        self.assertIn("from app.oa_pending_payment_bank_relations", sql)
        self.assertIn("limit %s offset %s", sql)
        self.assertNotIn("oa_pending_payment_read_model_rows", sql)
        self.assertNotIn("workbench_relation_read_model", sql)
        self.assertNotIn("job.outbox_events", sql)
        self.assertIn(20, params)
        self.assertIn(40, params)
        self.assertEqual(result["pagination"]["total"], 0)

    def test_bank_candidates_use_canonical_relations_and_server_paging(self) -> None:
        connection = RecordingConnection()
        repository = PostgresOaPendingPaymentQueryRepository(connection)

        result = repository.bank_transaction_candidates(
            tenant_id="tenant-a",
            relation_status="linked_in_progress",
            keyword="供应商",
            page=2,
            page_size=20,
        )

        self.assertEqual(len(connection.fetch_one_calls), 1)
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("from app.bank_transactions", sql)
        self.assertIn("from app.workbench_pair_relations", sql)
        self.assertIn("from app.oa_pending_payment_bank_relations", sql)
        self.assertIn("relation.status = 'active'", sql)
        self.assertIn("limit %s offset %s", sql)
        self.assertNotIn("read_model.", sql)
        self.assertEqual(params, ("tenant-a", "linked_in_progress", "%供应商%", 20, 20))
        self.assertEqual(result["pagination"], {"page": 2, "pageSize": 20, "total": 0})

    def test_snapshot_is_explicit_repeatable_read_read_only(self) -> None:
        connection = RecordingConnection()
        repository = PostgresOaPendingPaymentQueryRepository(connection)

        with repository.snapshot() as snapshot:
            self.assertIsNot(snapshot, repository)

        self.assertEqual(
            connection.transaction_instance.executed,
            ["set transaction isolation level repeatable read read only"],
        )

    def test_snapshot_rejects_connections_without_transaction_support(self) -> None:
        repository = PostgresOaPendingPaymentQueryRepository(object())

        with self.assertRaisesRegex(RuntimeError, "require a PostgreSQL transaction"):
            with repository.snapshot():
                self.fail("snapshot unexpectedly opened")

    def test_fact_hydration_query_count_is_fixed_for_page_size_200(self) -> None:
        one = RecordingConnection()
        many = RecordingConnection()
        one_repository = PostgresOaPendingPaymentQueryRepository(one)
        many_repository = PostgresOaPendingPaymentQueryRepository(many)

        one_repository.load_facts([_descriptor("oa-0")], tenant_id="tenant-a")
        many_repository.load_facts(
            [_descriptor(f"oa-{index}") for index in range(200)],
            tenant_id="tenant-a",
        )

        self.assertEqual(many.read_count, one.read_count)
        self.assertLessEqual(many.read_count, 5)


class CanonicalQueryRepository:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.missing_detail = False
        self.snapshot_entries = 0
        self.snapshot_exits = 0
        self.select_calls: list[dict[str, object]] = []
        self.find_calls: list[dict[str, object]] = []
        self.load_calls: list[list[dict[str, object]]] = []
        self.candidate_calls: list[dict[str, object]] = []

    @contextmanager
    def snapshot(self):
        self.snapshot_entries += 1
        try:
            yield self
        finally:
            self.snapshot_exits += 1

    def select_page(self, **kwargs: object) -> dict[str, object]:
        self.select_calls.append(dict(kwargs))
        descriptors = [] if self.empty else [_descriptor("oa-canonical-1")]
        total = len(descriptors)
        return {
            "descriptors": descriptors,
            "pagination": {
                "page": kwargs["page"],
                "pageSize": kwargs["page_size"],
                "total": total,
            },
            "summary": {"rowCount": total, "viewCounts": {"completed": total, "in_progress": 0}},
            "statistics": {"oa_count": total},
            "filterOptions": {},
        }

    def find_descriptor(self, **kwargs: object) -> dict[str, object] | None:
        self.find_calls.append(dict(kwargs))
        return None if self.missing_detail else _descriptor("oa-canonical-1")

    def bank_transaction_candidates(self, **kwargs: object) -> dict[str, object]:
        self.candidate_calls.append(dict(kwargs))
        return {
            "rows": [{"id": "bank-canonical-1", "relationStatus": kwargs["relation_status"]}],
            "pagination": {
                "page": kwargs["page"],
                "pageSize": kwargs["page_size"],
                "total": 1,
            },
        }

    def load_facts(
        self,
        descriptors: list[dict[str, object]],
        *,
        tenant_id: str,
    ) -> dict[str, object]:
        del tenant_id
        self.load_calls.append(descriptors)
        return {
            "completed_records": [_record()],
            "in_progress_records": [],
            "canonical_relations": [],
            "pending_relations": [],
            "bank_transactions": [],
            "invoices": [],
            "payment_statuses": {},
        }


class RecordingTransaction:
    def __init__(self, owner: "RecordingConnection") -> None:
        self.owner = owner
        self.executed: list[str] = []

    def __enter__(self) -> "RecordingTransaction":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, _params: object = None) -> None:
        self.executed.append(sql)

    def fetch_one(self, sql: str, params: object = None) -> dict[str, object] | None:
        return self.owner.fetch_one(sql, params)

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        return self.owner.fetch_all(sql, params)


class RecordingConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, object]] = []
        self.transaction_instance = RecordingTransaction(self)

    @property
    def read_count(self) -> int:
        return len(self.fetch_one_calls) + len(self.fetch_all_calls)

    def transaction(self) -> RecordingTransaction:
        return self.transaction_instance

    def fetch_one(self, sql: str, params: object = None) -> dict[str, object] | None:
        normalized_params = tuple(params or ())
        self.fetch_one_calls.append((sql, normalized_params))
        return {}

    def fetch_all(self, sql: str, params: object = None) -> list[dict[str, object]]:
        self.fetch_all_calls.append((sql, params))
        return []


def _record() -> OAApplicationRecord:
    return OAApplicationRecord(
        id="oa-canonical-1",
        month="2026-05",
        section="unpaired",
        case_id=None,
        applicant="测试申请人",
        project_name="测试项目",
        apply_type="支付申请",
        amount="100.00",
        counterparty_name="测试供应商",
        reason="canonical query",
        relation_code="pending_match",
        relation_label="待找流水与发票",
        relation_tone="warn",
        workflow_status="completed",
        detail_fields={"paymentFlowId": "flow-canonical-1"},
    )


def _descriptor(oa_id: str) -> dict[str, object]:
    return {
        "row_id": "oa_pending_payment_row_" + sha1(oa_id.encode("utf-8")).hexdigest()[:16],
        "scope_key": "2026-05",
        "source_kind": "completed",
        "oa_ids": [oa_id],
    }


if __name__ == "__main__":
    unittest.main()
