from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from fin_ops_platform.services.postgres_repositories.bank_flow_rule_batch_canonical_query import (
    BankFlowRuleBatchCanonicalQueryRepository,
)


def _settings_payload() -> dict[str, object]:
    return {
        "bank_transaction_tags": {
            "version": 3,
            "definitions": [
                {
                    "code": "fee",
                    "label": "手续费",
                    "path": ["费用", "手续费"],
                    "source": "custom",
                    "status": "active",
                    "direction": "expense",
                    "output_primary_label": "费用",
                    "output_sub_label": "手续费",
                    "rules": {
                        "match_fields": ["summary_text"],
                        "contains_any": ["手续费"],
                    },
                }
            ],
        },
        "bank_flow_rule_batch_tag_rules": {
            "version": 7,
            "requirements_by_tag_code": {
                "fee": {
                    "requires_oa": False,
                    "requires_invoice": False,
                }
            },
        },
    }


class _Transaction:
    def __init__(self, connection: "_Connection") -> None:
        self._connection = connection

    def __enter__(self) -> "_Transaction":
        self._connection.transaction_enters += 1
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # type: ignore[no-untyped-def]
        self._connection.transaction_exits += 1

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        return self._connection.execute(sql, params)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        return self._connection.fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return self._connection.fetch_all(sql, params)


class _Connection:
    def __init__(
        self,
        *,
        empty_page: bool = False,
        include_formal_item: bool = False,
    ) -> None:
        self.empty_page = empty_page
        self.include_formal_item = include_formal_item
        self.transaction_enters = 0
        self.transaction_exits = 0
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetched_one: list[tuple[str, tuple[object, ...]]] = []
        self.fetched_all: list[tuple[str, tuple[object, ...]]] = []

    def transaction(self) -> _Transaction:
        return _Transaction(self)

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((" ".join(sql.split()), params))
        return 1

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        normalized = " ".join(sql.split())
        self.fetched_one.append((normalized, params))
        if "from app.app_settings" in normalized:
            return {"settings_payload": _settings_payload()}
        if "candidate_rows" in normalized and "formal_items" in normalized:
            if self.empty_page:
                return {
                    "candidate_rows": [],
                    "active_relations": [],
                    "formal_items": [],
                }
            return {
                "candidate_rows": [
                    {
                        "transaction_id": "bank-1",
                        "account_no": "622200008106",
                        "account_key": "acct:527d1b9348772d1d415d60dc",
                        "bank_name": "建设银行",
                        "account_last4": "8106",
                        "txn_direction": "outflow",
                        "amount": "8.80",
                        "trade_time": datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
                        "category_code": "fee",
                        "category_source": "auto_confirmation",
                        "payload": {},
                    }
                ],
                "active_relations": [],
                "formal_items": (
                    [
                        {
                            "batch_id": "batch-submitted-fee",
                            "status": "submitted",
                            "status_bucket": "submitted",
                            "version": 1,
                            "scope_month": date(2026, 5, 1),
                            "account_key": "未知银行:8106",
                            "total_amount": "8.80",
                            "bank_transaction_ids": ["bank-1"],
                            "has_active_relation": True,
                            "payload": {
                                "batch_id": "batch-submitted-fee",
                                "batch_type": "fee",
                                "bank_name": "未知银行",
                                "account_last4": "8106",
                                "row_ids": ["bank-1"],
                                "row_count": 1,
                            },
                        }
                    ]
                    if self.include_formal_item
                    else []
                ),
            }
        if "from app.bank_flow_rule_batches batch" in normalized and "where batch.batch_id = %s" in normalized:
            return {
                "batch_id": "batch-fee",
                "status": "submitted",
                "status_bucket": "submitted",
                "version": 3,
                "scope_month": date(2026, 5, 1),
                "account_key": "建设银行:8106",
                "total_amount": "8.80",
                "bank_transaction_ids": ["bank-1"],
                "has_active_relation": True,
                "payload": {
                    "batch_id": "batch-fee",
                    "batch_type": "fee",
                    "batch_label": "手续费",
                    "row_ids": ["bank-1"],
                    "row_count": 1,
                    "tag_counts": {"fee": 1},
                    "direction_counts": {"expense": 1},
                    "relation_case_id": "batch-fee",
                },
            }
        return None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.split())
        self.fetched_all.append((normalized, params))
        if "select * from visible_batches" in normalized:
            return [
                {
                    "batch_id": "batch-fee",
                    "status": "draft",
                    "presented_status": "draft",
                    "presented_status_bucket": "unsubmitted",
                    "version": 1,
                    "scope_month": date(2026, 5, 1),
                    "account_key": "建设银行:8106",
                    "total_amount": "8.80",
                    "bank_transaction_ids": ["bank-1"],
                    "has_active_relation": False,
                    "payload": {
                        "batch_id": "batch-fee",
                        "batch_type": "fee",
                        "batch_label": "手续费",
                        "row_ids": ["bank-1"],
                        "row_count": 1,
                    },
                }
            ]
        if "group by batch_type, presented_status" in normalized:
            return [
                {
                    "batch_type": "fee",
                    "presented_status": "draft",
                    "batch_count": 1,
                    "row_count": 1,
                    "batch_label": "手续费",
                    "category_primary_label": "费用",
                    "category_sub_label": "手续费",
                    "total_amount": "8.80",
                }
            ]
        if "with categorized_scopes as" in normalized:
            return [{"scope_key": "2026-05"}, {"scope_key": "2026-07"}]
        if "from app.bank_transactions bank" in normalized:
            return [
                {
                    "transaction_id": "bank-1",
                    "account_no": "622200008106",
                    "txn_direction": "outflow",
                    "normalized_counterparty_name": "银行",
                    "amount": "8.80",
                    "trade_time": datetime(2026, 5, 4, 8, 0, tzinfo=UTC),
                    "summary": "手续费",
                    "remark": "",
                    "category_code": "fee",
                    "category_source": "auto_confirmation",
                    "relation_case_ids": ["batch-fee"],
                    "linked_oa_count": 1,
                    "linked_invoice_count": 0,
                    "payload": {
                        "bank_name": "建设银行",
                        "account_last4": "8106",
                    },
                }
            ]
        if "from app.bank_flow_rule_batch_events" in normalized:
            return [
                {
                    "event_type": "submit",
                    "actor_id": "finance-user",
                    "occurred_at": datetime(2026, 5, 4, 9, 0, tzinfo=UTC),
                    "payload": {"status": "submitted"},
                }
            ]
        return []


def test_page_query_uses_one_repeatable_read_snapshot_and_two_fixed_selects() -> None:
    connection = _Connection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    result = repository.read_page(
        {"month": "2026-05", "bucket": "unsubmitted"},
        summary_filters={"month": "2026-05"},
        page=2,
        page_size=50,
    )

    assert result["candidate_rows"][0]["id"] == "bank-1"
    assert result["candidate_rows"][0]["category_code"] == "fee"
    assert result["candidate_rows"][0]["bank_name"] == "建设银行"
    assert result["candidate_rows"][0]["account_last4"] == "8106"
    assert result["candidate_rows"][0]["account_key"] == "acct:527d1b9348772d1d415d60dc"
    assert result["active_relations"] == []
    assert result["formal_items"] == []
    assert connection.transaction_enters == connection.transaction_exits == 1
    assert len(connection.fetched_one) == 2
    assert len(connection.fetched_all) == 0
    assert connection.executed == [
        ("set transaction isolation level repeatable read read only", ()),
        ("set local jit = off", ()),
    ]
    all_sql = [sql for sql, _params in [*connection.fetched_one, *connection.fetched_all]]
    assert not any("read_model." in sql for sql in all_sql)
    assert not any("app.no_oa_bank_batches" in sql for sql in all_sql)
    assert any("from app.bank_flow_rule_batches batch" in sql for sql in all_sql)
    assert any("from app.workbench_pair_relations" in sql for sql in all_sql)
    assert any("from app.bank_transaction_category_confirmations" in sql for sql in all_sql)
    source_sql, source_params = next(
        (sql, params)
        for sql, params in connection.fetched_one
        if "candidate_rows" in sql and "formal_items" in sql
    )
    assert "coalesce(candidate.txn_date, candidate.txn_month)" in source_sql
    assert "candidate.account_key as account_key" in source_sql
    assert "candidate.bank_name || ':' || candidate.account_last4" not in source_sql
    assert "2026-05-01" in source_params
    assert "2026-05-31" in source_params
    assert source_params[-1] == "2026-05-01"


def test_submitted_page_query_keeps_candidate_rows_and_active_relations_in_snapshot() -> None:
    connection = _Connection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    repository.read_page(
        {"month": "2026-05", "bucket": "submitted"},
        summary_filters={"month": "2026-05"},
        page=1,
        page_size=50,
    )

    source_sql, source_params = next(
        (sql, params)
        for sql, params in connection.fetched_one
        if "candidate_rows" in sql and "formal_items" in sql
    )
    assert "where bank.status <> 'deleted' and false" not in source_sql
    assert "2026-05-01" in source_params
    assert "2026-05-31" in source_params
    assert source_params[-1] == "2026-05-01"


def test_all_page_query_reads_the_complete_canonical_source_without_a_month_predicate() -> None:
    connection = _Connection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    result = repository.read_page(
        {"bucket": "all"},
        summary_filters={},
        page=1,
        page_size=50,
    )

    assert result["candidate_rows"][0]["id"] == "bank-1"
    source_sql, source_params = next(
        (sql, params)
        for sql, params in connection.fetched_one
        if "candidate_rows" in sql and "formal_items" in sql
    )
    assert "where bank.status <> 'deleted' and false" not in source_sql
    assert "coalesce(candidate.txn_date, candidate.txn_month)" not in source_sql
    assert "or bank.txn_date >= %s::date" in source_sql
    assert "bank.*" not in source_sql.split("), bank_identities", 1)[0]
    assert "select relation.*" not in source_sql
    assert "batch.*" not in source_sql
    assert "confirmed_category_candidates" not in source_sql
    assert "manual_category_candidates" not in source_sql
    assert "from classified_with_semantics candidate" in source_sql
    assert "relation.row_ids && candidate_ids.row_ids" in source_sql
    assert "2026-05-01" not in source_params
    assert source_params
    assert connection.transaction_enters == connection.transaction_exits == 1
    assert len(connection.fetched_one) == 2


def test_submit_guard_reuses_the_same_canonical_sql_classifier() -> None:
    connection = _Connection(empty_page=True)

    with connection.transaction() as transaction:
        result = BankFlowRuleBatchCanonicalQueryRepository.read_candidate_guard_source(
            transaction,
            scope_month="2026-05",
        )

    source_sql, source_params = next(
        (sql, params)
        for sql, params in connection.fetched_one
        if "candidate_rows as materialized" in sql
        and "candidate_identity_array" in sql
        and "formal_items" not in sql
    )
    assert result["candidate_rows"] == []
    assert "from classified_with_semantics candidate" in source_sql
    assert "candidate.account_key as account_key" in source_sql
    assert "candidate.bank_name || ':' || candidate.account_last4" not in source_sql
    assert "category_resolution_authority" in source_sql
    assert "relation.row_ids && candidate_ids.row_ids" in source_sql
    assert "confirmed_category_candidates" not in source_sql
    assert "manual_category_candidates" not in source_sql
    assert "2026-05-01" in source_params
    assert "2026-05-31" in source_params


def test_page_query_returns_an_explicit_empty_result() -> None:
    repository = BankFlowRuleBatchCanonicalQueryRepository(_Connection(empty_page=True))

    result = repository.read_page({"month": "2026-05"})

    assert result["candidate_rows"] == []
    assert result["active_relations"] == []
    assert result["formal_items"] == []


def test_page_query_repairs_historical_bank_display_without_rewriting_identity() -> None:
    repository = BankFlowRuleBatchCanonicalQueryRepository(
        _Connection(include_formal_item=True)
    )

    result = repository.read_page({"month": "2026-05"})

    batch = result["formal_items"][0]
    assert batch["bank_name"] == "建设银行"
    assert batch["account_last4"] == "8106"
    assert batch["account_key"] == "未知银行:8106"


def test_page_query_returns_live_candidate_inputs_in_the_same_snapshot() -> None:
    class LiveSourceConnection(_Connection):
        def fetch_one(
            self,
            sql: str,
            params: tuple[object, ...] = (),
        ) -> dict[str, object] | None:
            normalized = " ".join(sql.split())
            self.fetched_one.append((normalized, params))
            if "from app.app_settings" in normalized:
                return {"settings_payload": _settings_payload()}
            if "candidate_rows" in normalized and "formal_items" in normalized:
                return {
                    "candidate_rows": [
                        {
                            "transaction_id": "bank-out-188500",
                            "amount": "188500.00",
                            "txn_direction": "outflow",
                            "trade_time": datetime(2026, 5, 14, 9, 0, tzinfo=UTC),
                            "category_code": "internal_transfer",
                            "category_source": "auto_confirmation",
                            "payload": {
                                "bank_name": "建设银行",
                                "account_key": "CCB:8106",
                            },
                        }
                    ],
                    "active_relations": [],
                    "formal_items": [],
                }
            return None

    connection = LiveSourceConnection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    result = repository.read_page(
        {"month": "2026-05", "bucket": "unsubmitted"},
        summary_filters={"month": "2026-05"},
        page=1,
        page_size=50,
    )

    assert result["candidate_rows"][0]["id"] == "bank-out-188500"
    assert result["candidate_rows"][0]["category_code"] == "internal_transfer"
    assert result["active_relations"] == []
    assert result["formal_items"] == []
    assert connection.transaction_enters == connection.transaction_exits == 1
    assert len(connection.fetched_one) == 2
    combined_sql = connection.fetched_one[1][0]
    assert "from app.bank_transactions" in combined_sql
    assert "from app.workbench_pair_relations" in combined_sql
    assert "from app.bank_flow_rule_batches" in combined_sql
    assert "manual_category.category, '' ) = any" not in combined_sql
    assert "read_model." not in combined_sql


def test_detail_reads_bank_rows_events_and_only_active_canonical_relations() -> None:
    connection = _Connection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    detail = repository.read_detail("batch-fee")

    assert detail is not None
    assert detail["batch"]["can_withdraw"] is True
    assert detail["batch"]["bank_name"] == "建设银行"
    assert detail["batch"]["account_last4"] == "8106"
    assert detail["batch"]["account_key"] == "建设银行:8106"
    assert detail["rows"][0]["relation_status"] == "linked"
    assert detail["rows"][0]["relation_case_ids"] == ["batch-fee"]
    assert detail["events"][0]["event_type"] == "submit"
    assert connection.transaction_enters == connection.transaction_exits == 1
    assert len(connection.fetched_one) == 2
    assert len(connection.fetched_all) == 2
    detail_sql = " ".join(sql for sql, _params in connection.fetched_all)
    assert "relation.status = 'active'" in detail_sql
    assert "from app.workbench_pair_relations relation" in detail_sql
    assert "from app.bank_flow_rule_batch_events" in detail_sql
    assert "read_model." not in detail_sql


@pytest.mark.parametrize(
    ("filters", "error_code"),
    [
        ({"month": "2026-13"}, "invalid_bank_flow_rule_batch_month"),
        ({"status": "processing"}, "invalid_bank_flow_rule_batch_status"),
        ({"bucket": "refreshing"}, "invalid_bank_flow_rule_batch_bucket"),
    ],
)
def test_invalid_page_filters_fail_before_opening_snapshot(
    filters: dict[str, object],
    error_code: str,
) -> None:
    connection = _Connection()
    repository = BankFlowRuleBatchCanonicalQueryRepository(connection)

    with pytest.raises(ValueError, match=error_code):
        repository.read_page(filters)

    assert connection.transaction_enters == 0
