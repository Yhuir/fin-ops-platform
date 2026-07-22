from __future__ import annotations

from io import StringIO
import json
from types import SimpleNamespace

from fin_ops_platform.services.bank_transaction_category_mutation_writer import (
    BankTransactionCategoryMutationWriter,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_category import (
    PostgresBankTransactionCategoryRepository,
)
from fin_ops_platform.tools.repair_unknown_bank_transaction_categories import main as repair_main


BANK_TRANSACTION_UUID = "11111111-1111-1111-1111-111111111111"
CATEGORY_UUID = "22222222-2222-2222-2222-222222222222"


class ManualClearTransaction:
    def __init__(self, *, active: bool = True) -> None:
        self.active = active
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized_sql = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized_sql:
            return {
                "bank_transaction_id": BANK_TRANSACTION_UUID,
                "public_transaction_id": "bank-row-1",
                "scope_month": "2026-02",
            }
        if "from app.bank_transaction_categories" in normalized_sql and "status = 'active'" in normalized_sql:
            if not self.active:
                return None
            return {
                "id": CATEGORY_UUID,
                "category": "unknown",
                "source": "manual",
                "version": 2,
                "raw_payload": {
                    "normalized_payload": {
                        "category_code": "unknown",
                        "source": "manual",
                        "manual_assignment": True,
                    }
                },
            }
        if "from app.bank_transaction_categories" in normalized_sql:
            return {
                "version": 3,
                "source": "manual",
                "status": "cleared",
                "raw_payload": {},
            }
        raise AssertionError(f"unexpected fetch_one SQL: {normalized_sql} {params}")

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


def test_manual_clear_marks_existing_fact_cleared_without_inserting_unknown() -> None:
    transaction = ManualClearTransaction()
    repository = PostgresBankTransactionCategoryRepository(SimpleNamespace())

    result = repository.apply_mutation(
        transaction=transaction,
        transaction_id="bank-row-1",
        mutation_type="manual_clear",
        record={"category_version": 3},
        actor_id="finance-user",
        action="bank_detail_category_manual_assignment_cleared",
        metadata={"assignment_source": "manual"},
    )

    sql = [statement for statement, _params in transaction.executed]
    assert result["changed"] is True
    assert result["affected_months"] == ["2026-02"]
    assert any("set status = 'cleared'" in statement for statement in sql)
    assert any("'updated_by', %s::text" in statement for statement in sql)
    assert any("'version', %s::integer" in statement for statement in sql)
    assert any("insert into app.bank_transaction_category_events" in statement for statement in sql)
    assert any("insert into audit.events" in statement for statement in sql)
    assert all("insert into app.bank_transaction_categories" not in statement for statement in sql)
    assert all("'unknown'" not in statement for statement in sql)


def test_manual_clear_is_idempotent_after_fact_is_already_cleared() -> None:
    transaction = ManualClearTransaction(active=False)
    repository = PostgresBankTransactionCategoryRepository(SimpleNamespace())

    result = repository.apply_mutation(
        transaction=transaction,
        transaction_id="bank-row-1",
        mutation_type="manual_clear",
        record={"category_version": 3},
        actor_id="finance-user",
        action="bank_detail_category_manual_assignment_cleared",
        metadata={},
    )

    assert result["changed"] is False
    assert transaction.executed == []


class BatchRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def apply_mutation(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        transaction_id = str(kwargs["transaction_id"])
        month = "2026-02" if transaction_id == "bank-1" else "2026-03"
        return {"changed": True, "transaction_id": transaction_id, "affected_months": [month], "version": 2}


class BatchQueue:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def enqueue_read_model_refreshes_in_transaction(self, **kwargs: object) -> list[dict[str, object]]:
        self.calls.append(dict(kwargs))
        return [{"event_id": "event-1"}]


class MatchingRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def mark_workbench_matching_dirty_scopes_in_transaction(self, **kwargs: object) -> list[str]:
        self.calls.append(dict(kwargs))
        return []


def test_batch_writer_deduplicates_refresh_io_and_expands_matching_once() -> None:
    repository = BatchRepository()
    queue = BatchQueue()
    matching = MatchingRepository()
    transaction = object()
    writer = BankTransactionCategoryMutationWriter(
        connection=SimpleNamespace(),
        repository=repository,
        queue_repository=queue,
        workbench_matching_repository=matching,
        workbench_matching_source_versions_provider=lambda: {"bank_transaction_category_version": "v1"},
    )

    result = writer.persist_many(
        mutations=[
            {
                "transaction_id": transaction_id,
                "mutation_type": "turnover_update",
                "record": {"category_code": "borrow_in"},
                "actor_id": "finance-user",
                "action": "turnover_bank_transaction_category_updated",
                "metadata": {},
            }
            for transaction_id in ("bank-1", "bank-2")
        ],
        transaction=transaction,
    )

    assert len(repository.calls) == 2
    assert len(queue.calls) == 1
    assert len(matching.calls) == 1
    assert result["affected_months"] == ["2026-02", "2026-03"]
    refreshes = list(queue.calls[0]["refreshes"])
    assert {item["scope_type"] for item in refreshes} == {
        "bank_detail",
        "bank_flow_rule_batch",
        "workbench",
        "workbench_relation",
        "invoice_lifecycle",
        "cost_statistics",
        "search",
        "turnover_ledger",
        "pending_invoice",
    }
    assert matching.calls[0]["scope_months"] == [
        "2025-12",
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
    ]


class InspectionConnection:
    def fetch_all(self, _sql: str, _params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return [
            {
                "category_id": CATEGORY_UUID,
                "transaction_id": "bank-row-1",
                "bank_transaction_id": BANK_TRANSACTION_UUID,
                "scope_month": "2026-02",
                "version": 2,
                "updated_at": "2026-02-03T00:00:00+00:00",
                "raw_payload": {"normalized_payload": {"manual_assignment": True}},
                "clear_event_evidence": True,
            },
            {
                "category_id": "33333333-3333-3333-3333-333333333333",
                "transaction_id": "legacy-only",
                "bank_transaction_id": None,
                "scope_month": None,
                "version": 1,
                "updated_at": "2026-02-03T00:00:00+00:00",
                "raw_payload": {},
                "clear_event_evidence": False,
            },
        ]


def test_unknown_repair_dry_run_separates_strict_and_manual_review_candidates() -> None:
    stdout = StringIO()

    exit_code = repair_main(
        ["--dry-run"],
        connection=InspectionConnection(),
        stdout=stdout,
    )

    payload = json.loads(stdout.getvalue())
    assert exit_code == 1
    assert payload["strict_candidate_count"] == 1
    assert payload["manual_review_candidate_count"] == 1
    assert payload["affected_months"] == ["2026-02"]
