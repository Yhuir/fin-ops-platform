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


def test_batch_writer_commits_canonical_facts_without_write_time_fan_out() -> None:
    repository = BatchRepository()
    transaction = object()
    writer = BankTransactionCategoryMutationWriter(
        connection=SimpleNamespace(),
        repository=repository,
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
    assert result["affected_months"] == ["2026-02", "2026-03"]
    assert "outbox_event_ids" not in result
    assert "operation_barrier_targets" not in result


def test_batch_writer_can_commit_canonical_facts_without_write_time_fan_out() -> None:
    repository = BatchRepository()
    writer = BankTransactionCategoryMutationWriter(
        connection=SimpleNamespace(),
        repository=repository,
    )

    result = writer.persist_many(
        mutations=[
            {
                "transaction_id": "bank-1",
                "mutation_type": "manual_assign",
                "record": {"category_code": "salary"},
                "actor_id": "finance-user",
                "action": "bank_detail_category_manual_assignment_saved",
                "metadata": {},
            }
        ],
        transaction=object(),
    )

    assert len(repository.calls) == 1
    assert result["changed"] is True
    assert result["affected_months"] == ["2026-02"]
    assert "outbox_event_ids" not in result
    assert "operation_barrier_targets" not in result


class ManualAssignReplacementTransaction:
    def __init__(self) -> None:
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
            return {
                "id": CATEGORY_UUID,
                "category": "fee",
                "source": "turnover_ledger",
                "version": 3,
                "raw_payload": {"normalized_payload": {"category_code": "fee"}},
            }
        if "from app.bank_transaction_category_confirmations" in normalized_sql and "status = 'active'" in normalized_sql:
            return {
                "id": "33333333-3333-3333-3333-333333333333",
                "category_code": "fee",
                "candidate_category_codes": ["fee", "salary"],
                "rule_version": "rules:3",
                "version": 4,
                "raw_payload": {},
            }
        if "select coalesce(max(version), 0) as version" in normalized_sql:
            return {"version": 4}
        if "insert into app.bank_transaction_categories" in normalized_sql:
            return {"id": "44444444-4444-4444-4444-444444444444"}
        raise AssertionError(f"unexpected fetch_one SQL: {normalized_sql} {params}")

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


def test_manual_assignment_atomically_replaces_active_category_and_confirmation() -> None:
    transaction = ManualAssignReplacementTransaction()
    repository = PostgresBankTransactionCategoryRepository(SimpleNamespace())

    result = repository.apply_mutation(
        transaction=transaction,
        transaction_id="bank-row-1",
        mutation_type="manual_assign",
        record={
            "category_code": "salary",
            "category_primary_label": "薪资社保福利",
            "category_sub_label": "工资",
        },
        actor_id="finance-user",
        action="bank_detail_category_manually_assigned",
        metadata={"assignment_source": "manual"},
    )

    statements = [statement for statement, _params in transaction.executed]
    assert result["changed"] is True
    assert result["version"] == 5
    assert any("set status = 'superseded'" in statement for statement in statements)
    assert any("set status = 'revoked'" in statement for statement in statements)
    assert any("insert into app.bank_transaction_category_events" in statement for statement in statements)
    assert any("insert into audit.events" in statement for statement in statements)


class SelectionProofTransaction:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append((" ".join(sql.lower().split()), params))
        return [
            {
                "canonical_transaction_id": BANK_TRANSACTION_UUID,
                "transaction_id": "bank-row-1",
                "bank_transaction_updated_at": "2026-07-26 01:02:03+00",
                "category_code": "borrow_out_personal_pending_collection",
                "category_source": "manual",
                "category_version": 7,
            }
        ]


def test_turnover_selection_proofs_lock_and_return_both_bank_identities() -> None:
    transaction = SelectionProofTransaction()
    repository = PostgresBankTransactionCategoryRepository(SimpleNamespace())

    proofs = repository.turnover_bank_row_selection_proofs(
        ["bank-row-1"],
        transaction=transaction,
        tenant_id="default",
    )

    assert proofs["bank-row-1"] is proofs[BANK_TRANSACTION_UUID]
    assert proofs["bank-row-1"]["category_version"] == 7
    assert "for share of b" in transaction.calls[0][0]
    assert transaction.calls[0][1] == ("default", ["bank-row-1"], ["bank-row-1"])


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
