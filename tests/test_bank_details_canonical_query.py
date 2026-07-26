from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import unittest

from fin_ops_platform.services.bank_details_canonical_query import (
    BANK_DETAIL_EXPORT_ROW_LIMIT,
    BankDetailsCanonicalQueryService,
    PostgresBankDetailsCanonicalQueryRepository,
    _classification_cte,
)


class _Transaction:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.reads: list[tuple[str, tuple[object, ...]]] = []
        self.main_rows = [
            {
                "row_id": "bank-legacy-1",
                "canonical_transaction_id": "00000000-0000-0000-0000-000000000001",
                "result_total": 1,
                "result_expense_count": 1,
                "result_income_count": 0,
                "result_classified_count": 1,
                "result_unclassified_count": 0,
                "result_category_counts": {"fee": 1},
            }
        ]

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> None:
        self.executed.append(" ".join(sql.split()).lower())

    def fetch_one(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> dict[str, object] | None:
        self.reads.append((sql, tuple(params)))
        return {"settings_payload": {}}

    def fetch_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        self.reads.append((sql, tuple(params)))
        normalized = " ".join(sql.split()).lower()
        if "from app.workbench_pair_relations" in normalized:
            return [
                {
                    "case_id": "case-1",
                    "row_ids": ["bank-legacy-1", "invoice-1"],
                    "row_types": ["bank", "invoice"],
                }
            ]
        if "latest_balances as" in normalized:
            return [
                {
                    "account_identity": "acct:one",
                    "account_key": "acct:one",
                    "bank_name": "工商银行",
                    "account_last4": "1234",
                    "currency": "CNY",
                    "transaction_total_count": 2,
                    "latest_balance": Decimal("88.00"),
                }
            ]
        if "count(*)::bigint as transaction_count" in normalized:
            return [{"account_identity": "acct:one", "transaction_count": 1}]
        if "page_rows as" in normalized:
            return list(self.main_rows)
        raise AssertionError(f"Unexpected SQL: {normalized[:160]}")


class _Connection:
    def __init__(self) -> None:
        self.transaction_object = _Transaction()
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.transaction_object


class _SnapshotRepository:
    def transactions_snapshot(self, **_kwargs: object) -> dict[str, object]:
        definition = {
            "code": "fee",
            "label": "手续费",
            "status": "active",
            "priority": 2,
            "output_primary_label": "费用",
            "output_sub_label": "手续费",
            "rules": {
                "match_fields": ["summary_text"],
                "contains_any": ["手续费"],
            },
        }
        return {
            "settings": {
                "bank_transaction_tags": {
                    "version": 3,
                    "definitions": [definition],
                }
            },
            "rows": [
                {
                    "row_id": "bank-legacy-1",
                    "canonical_transaction_id": "00000000-0000-0000-0000-000000000001",
                    "account_key": "acct:one",
                    "bank_name": "工商银行",
                    "account_last4": "1234",
                    "trade_time": "2026-05-10T10:00:00+08:00",
                    "direction": "expense",
                    "amount": Decimal("12.34"),
                    "balance": Decimal("88.00"),
                    "counterparty_name_raw": "银联商务",
                    "purpose_text": "",
                    "summary_text": "短信服务费",
                    "note_text": "",
                    "detail_text": "",
                    "auto_resolution_status": "auto_matched",
                    "matched_definitions": [definition],
                }
            ],
            "relations": [
                {
                    "case_id": "case-1",
                    "row_ids": ["bank-legacy-1", "invoice-1"],
                    "row_types": ["bank", "invoice"],
                }
            ],
            "category_counts": {"fee": 1},
            "statistics": {
                "transaction_count": 1,
                "expense_transaction_count": 1,
                "income_transaction_count": 0,
                "classified_transaction_count": 1,
                "unclassified_transaction_count": 0,
            },
            "pagination": {"page": 1, "page_size": 25, "total": 1},
        }


class BankDetailsCanonicalQueryTests(unittest.TestCase):
    def test_transaction_snapshot_uses_one_fixed_repeatable_read_query_set(self) -> None:
        connection = _Connection()
        repository = PostgresBankDetailsCanonicalQueryRepository(connection)

        payload = repository.transactions_snapshot(
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword="服务费",
            category_code="fee",
            category_primary_label="费用",
            category_sub_label="手续费",
            category_third_label=None,
            page=2,
            page_size=25,
        )

        transaction = connection.transaction_object
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            transaction.executed,
            ["set transaction isolation level repeatable read read only"],
        )
        self.assertEqual(len(transaction.reads), 3)
        main_sql, main_params = transaction.reads[1]
        relation_sql, relation_params = transaction.reads[2]
        normalized_main = " ".join(main_sql.split()).lower()
        normalized_relation = " ".join(relation_sql.split()).lower()
        self.assertIn("from app.bank_transactions bank", normalized_main)
        self.assertIn("left join lateral", normalized_main)
        self.assertIn("limit %s offset %s", normalized_main)
        self.assertNotIn("read_model.", normalized_main)
        self.assertEqual(main_params[-2:], (25, 25))
        self.assertIn("from app.workbench_pair_relations", normalized_relation)
        self.assertIn("status = 'active'", normalized_relation)
        self.assertIn("row_ids && %s::text[]", normalized_relation)
        self.assertNotIn("read_model.", normalized_relation)
        self.assertEqual(
            relation_params[1],
            [
                "bank-legacy-1",
                "00000000-0000-0000-0000-000000000001",
            ],
        )
        self.assertEqual(payload["pagination"]["total"], 1)

    def test_accounts_snapshot_aggregates_canonical_rows_in_sql(self) -> None:
        connection = _Connection()
        repository = PostgresBankDetailsCanonicalQueryRepository(connection)

        snapshot = repository.accounts_snapshot(
            date_from="2026-05-01",
            date_to="2026-05-31",
        )

        transaction = connection.transaction_object
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(len(transaction.reads), 3)
        sql_text = "\n".join(sql for sql, _params in transaction.reads)
        self.assertIn("from app.bank_transactions", sql_text)
        self.assertIn("latest_balances", sql_text)
        self.assertIn("group by account_identity", sql_text)
        self.assertNotIn("read_model.", sql_text)
        self.assertEqual(snapshot["transaction_counts"], {"acct:one": 1})

    def test_service_maps_direct_categories_and_bounded_active_relations(self) -> None:
        service = BankDetailsCanonicalQueryService(_SnapshotRepository())  # type: ignore[arg-type]

        payload = service.transactions_payload(
            account_key=None,
            date_from="2026-05-01",
            date_to="2026-05-31",
            keyword=None,
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            category_third_label=None,
            page=1,
            page_size=25,
        )

        row = payload["rows"][0]
        self.assertEqual(row["id"], "bank-legacy-1")
        self.assertEqual(row["effective_category_code"], "fee")
        self.assertEqual(row["relation_status"], "linked")
        self.assertEqual(row["oa_relation_tag"], "无oa")
        self.assertEqual(row["invoice_relation_tag"], "有发票")
        for obsolete in (
            "read_model_status",
            "source_versions",
            "cache_status",
            "refresh_scope",
        ):
            self.assertNotIn(obsolete, payload)

    def test_invalid_dates_and_pagination_fail_before_repository_reads(self) -> None:
        service = BankDetailsCanonicalQueryService(_SnapshotRepository())  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            service.accounts_payload(date_from="2026-99-01", date_to=None)
        with self.assertRaisesRegex(ValueError, "不能晚于"):
            service.accounts_payload(
                date_from="2026-06-01",
                date_to="2026-05-31",
            )
        with self.assertRaisesRegex(ValueError, "page 必须"):
            service.transactions_payload(
                account_key=None,
                date_from=None,
                date_to=None,
                keyword=None,
                category_code=None,
                category_primary_label=None,
                category_sub_label=None,
                category_third_label=None,
                page=0,
                page_size=25,
            )
        with self.assertRaisesRegex(ValueError, "page_size 必须"):
            service.transactions_payload(
                account_key=None,
                date_from=None,
                date_to=None,
                keyword=None,
                category_code=None,
                category_primary_label=None,
                category_sub_label=None,
                category_third_label=None,
                page=1,
                page_size=501,
            )

    def test_rule_sql_has_aligned_parameters_for_all_supported_predicates(self) -> None:
        sql, params = _classification_cte(
            definitions=[
                {
                    "code": "complex",
                    "label": "复杂规则",
                    "status": "active",
                    "priority": 2,
                    "direction": "expense",
                    "account_scope": {
                        "type": "bank_account",
                        "values": ["acct:one"],
                    },
                    "rules": {
                        "match_fields": ["summary_text", "note_text"],
                        "exact_any": ["精确"],
                        "contains_any": ["包含"],
                        "contains_all": ["全部"],
                        "none_of": ["排除"],
                        "regex_any": ["^规则"],
                    },
                }
            ],
            date_from="2026-05-01",
            date_to="2026-05-31",
        )

        self.assertEqual(sql.count("%s"), len(params))
        self.assertIn("base.direction = %s", sql)
        self.assertIn("lower(base.account_key) = any(%s::text[])", sql)
        self.assertIn("~* %s", sql)

    def test_export_snapshot_reads_at_most_limit_plus_one_rows(self) -> None:
        connection = _Connection()
        repository = PostgresBankDetailsCanonicalQueryRepository(connection)

        repository.export_snapshot(
            include_accounts=False,
            account_key=None,
            date_from=None,
            date_to=None,
            keyword=None,
            category_code=None,
            category_primary_label=None,
            category_sub_label=None,
            category_third_label=None,
        )

        main_params = connection.transaction_object.reads[1][1]
        self.assertEqual(main_params[-2:], (BANK_DETAIL_EXPORT_ROW_LIMIT + 1, 0))


if __name__ == "__main__":
    unittest.main()
