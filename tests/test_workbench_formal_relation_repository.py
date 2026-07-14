from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.workbench_free_matching_engine import relation_fingerprint


class FakeConnection:
    def __init__(
        self,
        *,
        oa_rows: list[dict[str, object]] | None = None,
        bank_rows: list[dict[str, object]] | None = None,
        invoice_rows: list[dict[str, object]] | None = None,
        historical_oa_rows: list[dict[str, object]] | None = None,
        historical_bank_rows: list[dict[str, object]] | None = None,
        historical_invoice_rows: list[dict[str, object]] | None = None,
        active_rows: list[dict[str, object]] | None = None,
        history_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.oa_rows = list(oa_rows or [])
        self.bank_rows = list(bank_rows or [])
        self.invoice_rows = list(invoice_rows or [])
        self.historical_oa_rows = list(historical_oa_rows or [])
        self.historical_bank_rows = list(historical_bank_rows or [])
        self.historical_invoice_rows = list(historical_invoice_rows or [])
        self.active_rows = list(active_rows or [])
        self.history_rows = list(history_rows or [])
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.split())
        self.queries.append((normalized, tuple(params)))
        if "from app.workbench_pair_relations" in normalized:
            return list(self.active_rows)
        if "from app.workbench_pair_relation_history" in normalized:
            return list(self.history_rows)
        historical = "= any(%s::text[])" in normalized
        if "from app.oa_applications" in normalized:
            return list(self.historical_oa_rows if historical else self.oa_rows)
        if "from app.bank_transactions" in normalized:
            return list(self.historical_bank_rows if historical else self.bank_rows)
        if "from app.invoices" in normalized:
            return list(self.historical_invoice_rows if historical else self.invoice_rows)
        raise AssertionError(f"unexpected SQL: {normalized}")


def oa_row(
    row_id: str = "oa-1",
    *,
    amount: object = Decimal("520.00"),
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "canonical_object_identity": row_id,
        "row_id": row_id,
        "amount": amount,
        "currency": "CNY",
        "fact_date": date(2026, 5, 7),
        "workflow_no": "OA-2026-001",
        "project_id": "PROJECT-001",
        "project_name": "项目一",
        "applicant": "张三",
        "status": "active",
        "workflow_status": "completed",
        "normalized_payload": payload
        or {
            "apply_type": "支付申请",
            "counterparty_name": "云南立孚科技有限公司",
        },
        "source_version": datetime(2026, 5, 7, tzinfo=timezone.utc),
    }


def bank_row(row_id: str = "txn-1", *, direction: str = "outflow") -> dict[str, object]:
    return {
        "canonical_object_identity": row_id,
        "row_id": row_id,
        "amount": Decimal("520.00"),
        "signed_amount": Decimal("-520.00" if direction == "outflow" else "520.00"),
        "currency": "CNY",
        "fact_date": date(2026, 5, 8),
        "txn_direction": direction,
        "counterparty_name_raw": "云南立孚科技有限公司",
        "normalized_counterparty_name": "云南立孚科技有限公司",
        "project_id": "PROJECT-001",
        "bank_serial_no": "SERIAL-001",
        "source_unique_key": "BANK-SOURCE-001",
        "summary": "付款",
        "remark": "OA-2026-001",
        "bank_text_fields": [],
        "raw_payload": {},
        "source_version": datetime(2026, 5, 8, tzinfo=timezone.utc),
    }


def invoice_row(
    row_id: str = "inv-1",
    *,
    source_links: list[dict[str, object]] | None = None,
    total_with_tax: object = Decimal("520.00"),
) -> dict[str, object]:
    return {
        "canonical_object_identity": row_id,
        "row_id": row_id,
        "invoice_type": "进项发票",
        "invoice_no": "26532000000716859331",
        "invoice_code": "",
        "digital_invoice_no": "26532000000716859331",
        "fact_date": date(2026, 5, 7),
        "amount": Decimal("460.19"),
        "signed_amount": Decimal("520.00"),
        "total_with_tax": total_with_tax,
        "currency": "CNY",
        "counterparty_name": "云南立孚科技有限公司",
        "seller_name": "云南立孚科技有限公司",
        "seller_tax_no": "915301023095361456",
        "buyer_name": "云南溯源科技有限公司",
        "buyer_tax_no": "91530100778565000X",
        "oa_form_id": "OA-FORM-1",
        "source_unique_key": "INVOICE-SOURCE-1",
        "source_links": list(source_links or []),
        "raw_payload": {"secret": "must-not-leak", "normalized_payload": {}},
        "source_version": datetime(2026, 5, 7, tzinfo=timezone.utc),
    }


class PostgresWorkbenchFormalRelationFactRepositoryTests(unittest.TestCase):
    def test_load_batch_is_fixed_query_bulk_io_and_uses_canonical_tables_only(self) -> None:
        connection = FakeConnection(
            oa_rows=[oa_row()],
            bank_rows=[bank_row()],
            invoice_rows=[invoice_row()],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(
            ["2026-05"],
            source_versions={"matching": "v1"},
        )

        self.assertEqual(len(result.facts), 3)
        self.assertEqual(len(connection.queries), 5)
        self.assertEqual(result.affected_scopes, ("2026-05", "all"))
        self.assertEqual(result.source_versions, (("matching", "v1"),))
        sql = "\n".join(query for query, _params in connection.queries)
        self.assertIn("app.oa_applications", sql)
        self.assertIn("app.bank_transactions", sql)
        self.assertIn("app.invoices", sql)
        self.assertIn("app.workbench_pair_relations", sql)
        self.assertIn("app.workbench_pair_relation_history", sql)
        self.assertNotIn("read_model.workbench_candidate_matches", sql)
        self.assertNotIn("read_model.workbench_reconciliation_decisions", sql)

    def test_explicit_reference_uses_one_bounded_historical_lookup_per_target_type(self) -> None:
        source_links = [
            {
                "source_kind": "oa_attachment_invoice",
                "metadata": {"derived_from_oa_id": "oa-history:item:1:abc"},
            }
        ]
        connection = FakeConnection(
            invoice_rows=[invoice_row(source_links=source_links)],
            historical_oa_rows=[oa_row("oa-history")],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        self.assertEqual({fact.member_key for fact in result.facts}, {("invoice", "inv-1"), ("oa", "oa-history")})
        self.assertEqual(len(connection.queries), 6)
        history_query = [query for query, params in connection.queries if "app.oa_applications" in query and params == (["oa-history"],)]
        self.assertEqual(len(history_query), 1)

    def test_active_relation_and_historical_case_prefix_are_stable_typed_anchors(self) -> None:
        connection = FakeConnection(
            oa_rows=[oa_row()],
            invoice_rows=[invoice_row()],
            active_rows=[
                {
                    "case_id": "case:decision:historical",
                    "row_ids": ["oa-1", "inv-1"],
                    "row_types": ["oa", "invoice"],
                }
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        self.assertEqual(len(result.active_relations), 1)
        self.assertEqual(result.active_relations[0].case_id, "case:decision:historical")
        self.assertEqual(result.active_relations[0].member_keys, (("oa", "oa-1"), ("invoice", "inv-1")))

    def test_explicit_user_withdrawal_records_exact_typed_fingerprint(self) -> None:
        before_relation = {
            "case_id": "CASE-WITHDRAWN",
            "row_ids": ["oa-1", "inv-1"],
            "row_types": ["oa", "invoice"],
        }
        connection = FakeConnection(
            oa_rows=[oa_row()],
            invoice_rows=[invoice_row()],
            history_rows=[
                {
                    "event_type": "withdraw_link",
                    "actor_id": "user:finance",
                    "before_payload": [before_relation],
                },
                {
                    "event_type": "withdraw_link",
                    "actor_id": "system:migration",
                    "before_payload": [
                        {
                            "case_id": "CASE-SYSTEM",
                            "row_ids": ["oa-1", "txn-1"],
                            "row_types": ["oa", "bank"],
                        }
                    ],
                },
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        expected = relation_fingerprint((("oa", "oa-1"), ("invoice", "inv-1")))
        self.assertEqual(result.withdrawal_fingerprints, frozenset({expected}))

    def test_amount_direction_currency_and_source_version_are_typed(self) -> None:
        connection = FakeConnection(
            oa_rows=[oa_row()],
            bank_rows=[bank_row()],
            invoice_rows=[invoice_row()],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])
        facts = {fact.row_type: fact for fact in result.facts}

        self.assertEqual({fact.amount_minor for fact in result.facts}, {52_000})
        self.assertEqual({fact.currency for fact in result.facts}, {"CNY"})
        self.assertEqual({fact.direction for fact in result.facts}, {"expenditure"})
        self.assertTrue(all(fact.source_version.startswith("2026-05-") for fact in result.facts))
        self.assertNotIn("secret", repr(facts["invoice"]))

    def test_invalid_scope_duplicate_identity_and_fractional_minor_unit_fail_fast(self) -> None:
        repository = PostgresWorkbenchFormalRelationFactRepository(FakeConnection())
        with self.assertRaises(ValueError):
            repository.load_batch([])
        with self.assertRaises(ValueError):
            repository.load_batch(["2026-13"])

        duplicate = FakeConnection(oa_rows=[oa_row(), oa_row(payload={"counterparty_name": "不同供应商"})])
        with self.assertRaises(ValueError):
            PostgresWorkbenchFormalRelationFactRepository(duplicate).load_batch(["2026-05"])

        fractional = FakeConnection(invoice_rows=[invoice_row(total_with_tax=Decimal("520.001"))])
        with self.assertRaises(ValueError):
            PostgresWorkbenchFormalRelationFactRepository(fractional).load_batch(["2026-05"])


if __name__ == "__main__":
    unittest.main()
