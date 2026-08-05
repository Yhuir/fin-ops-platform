from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import unittest

from fin_ops_platform.services.postgres_repositories.workbench_formal_relation import (
    PostgresWorkbenchFormalRelationFactRepository,
)
from fin_ops_platform.services.workbench_free_matching_engine import (
    WorkbenchFreeMatchingEngine,
    relation_fingerprint,
)


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
        etc_batch_link_rows: list[dict[str, object]] | None = None,
        etc_validation_rows: list[dict[str, object]] | None = None,
        etc_owner_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.oa_rows = list(oa_rows or [])
        self.bank_rows = list(bank_rows or [])
        self.invoice_rows = list(invoice_rows or [])
        self.historical_oa_rows = list(historical_oa_rows or [])
        self.historical_bank_rows = list(historical_bank_rows or [])
        self.historical_invoice_rows = list(historical_invoice_rows or [])
        self.active_rows = list(active_rows or [])
        self.history_rows = list(history_rows or [])
        self.etc_batch_link_rows = list(etc_batch_link_rows or [])
        self.etc_validation_rows = list(etc_validation_rows or [])
        self.etc_owner_rows = list(etc_owner_rows or [])
        self.queries: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.split())
        self.queries.append((normalized, tuple(params)))
        if "pg_advisory_xact_lock" in normalized:
            return []
        if "for update of batch, oa" in normalized:
            return list(self.etc_validation_rows)
        if "select case_id, amount_check, special_metadata" in normalized:
            return list(self.etc_owner_rows)
        if "with submitted_batches as" in normalized:
            return list(self.etc_batch_link_rows)
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
    applicant: str = "张三",
    fact_date: date = date(2026, 5, 7),
    approved_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "canonical_object_identity": row_id,
        "row_id": row_id,
        "amount": amount,
        "currency": "CNY",
        "fact_date": fact_date,
        "approved_at": approved_at,
        "workflow_no": "OA-2026-001",
        "project_id": "PROJECT-001",
        "project_name": "项目一",
        "applicant": applicant,
        "status": "active",
        "workflow_status": "completed",
        "normalized_payload": payload
        or {
            "apply_type": "支付申请",
            "counterparty_name": "云南立孚科技有限公司",
        },
        "source_version": datetime(2026, 5, 7, tzinfo=timezone.utc),
    }


def bank_row(
    row_id: str = "txn-1",
    *,
    direction: str = "outflow",
    counterparty: str = "云南立孚科技有限公司",
) -> dict[str, object]:
    return {
        "canonical_object_identity": row_id,
        "row_id": row_id,
        "amount": Decimal("520.00"),
        "signed_amount": Decimal("-520.00" if direction == "outflow" else "520.00"),
        "currency": "CNY",
        "fact_date": date(2026, 5, 8),
        "txn_direction": direction,
        "counterparty_name_raw": counterparty,
        "normalized_counterparty_name": counterparty,
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
    def test_exact_etc_candidate_query_is_bounded_and_preserves_ambiguity_evidence(self) -> None:
        connection = FakeConnection(
            etc_batch_link_rows=[
                {
                    "oa_row_id": "oa-etc",
                    "business_batch_id": "etc_business_batch_0014",
                    "external_etc_batch_id": "etc_20260622_001",
                    "submission_batch_id": "etc_submission_0014",
                    "invoice_count": 34,
                    "total_amount": Decimal("1584.35"),
                    "external_batch_owner_count": 2,
                    "oa_scope_month": "2026-06",
                    "batch_scope_month": "2026-06",
                }
            ]
        )

        candidates = PostgresWorkbenchFormalRelationFactRepository(
            connection
        ).load_etc_batch_link_candidates(["2026-06"])

        self.assertEqual(candidates[0]["invoice_count"], 34)
        self.assertEqual(candidates[0]["external_batch_owner_count"], 2)
        self.assertEqual(candidates[0]["scope_keys"], ["2026-06"])
        sql, params = connection.queries[0]
        self.assertIn("batch.scope_month between %s::date and %s::date", sql)
        self.assertIn("oa.normalized_payload->>'etc_batch_id'", sql)
        self.assertNotIn("like", sql.lower())
        self.assertEqual(len(params), 4)

    def test_transactional_etc_validation_rejects_changed_totals_and_other_relation_owner(self) -> None:
        connection = FakeConnection(
            etc_validation_rows=[
                {
                    "oa_row_id": "oa-etc",
                    "business_batch_id": "etc_business_batch_0014",
                    "external_etc_batch_id": "etc_20260622_001",
                    "invoice_count": 33,
                    "total_amount": Decimal("1584.35"),
                }
            ],
            etc_owner_rows=[
                {
                    "case_id": "case:other",
                    "amount_check": {},
                    "special_metadata": {
                        "etc_batch_link": {"external_etc_batch_id": "etc_20260622_001"}
                    },
                }
            ],
        )
        link = {
            "case_id": "case:target",
            "oa_row_id": "oa-etc",
            "business_batch_id": "etc_business_batch_0014",
            "external_etc_batch_id": "etc_20260622_001",
            "invoice_count": 34,
            "total_amount": "1584.35",
        }

        result = PostgresWorkbenchFormalRelationFactRepository(connection).validate_etc_batch_links([link])

        self.assertFalse(result["valid"])
        self.assertEqual(
            {issue["code"] for issue in result["issues"]},
            {"canonical_batch_totals_changed", "active_relation_owner_conflict"},
        )
        self.assertIn("pg_advisory_xact_lock", connection.queries[0][0])
        self.assertIn("for update of batch, oa", connection.queries[1][0])
        self.assertIn("for update", connection.queries[2][0])
        self.assertEqual(len(connection.queries[2][1]), 8)

    def test_transactional_etc_validation_rejects_second_completed_oa_claim(self) -> None:
        connection = FakeConnection(
            etc_validation_rows=[
                {
                    "oa_row_id": oa_row_id,
                    "business_batch_id": "etc_business_batch_0014",
                    "external_etc_batch_id": "etc_20260622_001",
                    "invoice_count": 34,
                    "total_amount": Decimal("1584.35"),
                }
                for oa_row_id in ("oa-etc", "oa-duplicate")
            ],
        )
        link = {
            "case_id": "case:target",
            "oa_row_id": "oa-etc",
            "business_batch_id": "etc_business_batch_0014",
            "external_etc_batch_id": "etc_20260622_001",
            "invoice_count": 34,
            "total_amount": "1584.35",
        }

        result = PostgresWorkbenchFormalRelationFactRepository(connection).validate_etc_batch_links([link])

        self.assertFalse(result["valid"])
        self.assertEqual(result["issues"], [
            {
                "code": "canonical_owner_changed",
                "external_etc_batch_id": "etc_20260622_001",
            }
        ])

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
        self.assertIn("actor_id not like 'system:%%'", sql)
        self.assertIn("actor_id not like 'migration:%%'", sql)
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
        history_query = [
            query
            for query, params in connection.queries
            if "app.oa_applications" in query and params[0] == ["oa-history"]
        ]
        self.assertEqual(len(history_query), 1)

    def test_oa_source_alias_is_canonicalized_before_formal_matching(self) -> None:
        source_alias = "6a0ee8613bb8164165d8c61a"
        connection = FakeConnection(
            oa_rows=[
                oa_row(
                    "oa-exp-2206",
                    amount=Decimal("413.00"),
                    payload={
                        "apply_type": "日常报销",
                        "detail_fields": {
                            "Mongo文档ID": source_alias,
                            "OA单号": "2206",
                        },
                    },
                )
            ],
            invoice_rows=[
                invoice_row(
                    "inv_imported_0058",
                    total_with_tax=Decimal("60.00"),
                    source_links=[
                        {
                            "source_kind": "oa_attachment_invoice",
                            "metadata": {
                                "derived_from_oa_id": f"oa-exp-{source_alias}:item:2:9ca59ea6e4ab",
                            },
                        }
                    ],
                )
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])
        invoice = next(fact for fact in result.facts if fact.row_type == "invoice")

        self.assertEqual(
            {
                reference.target_member_key
                for reference in invoice.references
                if reference.kind == "attachment_source"
            },
            {("oa", "oa-exp-2206")},
        )

    def test_owned_attachment_item_alias_is_canonicalized_when_oa_payload_lacks_source_id(self) -> None:
        source_alias = "6a0ee8613bb8164165d8c61a"
        oa = oa_row("oa-exp-2206", amount=Decimal("413.00"), payload={"apply_type": "日常报销"})
        oa["source_aliases"] = [f"oa-exp-{source_alias}:item:2:9ca59ea6e4ab"]
        connection = FakeConnection(
            oa_rows=[oa],
            invoice_rows=[
                invoice_row(
                    "inv_imported_0058",
                    total_with_tax=Decimal("60.00"),
                    source_links=[
                        {
                            "source_kind": "oa_attachment_invoice",
                            "metadata": {
                                "derived_from_oa_id": f"oa-exp-{source_alias}:item:2:9ca59ea6e4ab",
                            },
                        }
                    ],
                )
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])
        invoice = next(fact for fact in result.facts if fact.row_type == "invoice")

        self.assertEqual(
            {
                reference.target_member_key
                for reference in invoice.references
                if reference.kind == "attachment_source"
            },
            {("oa", "oa-exp-2206")},
        )
        self.assertIn("from app.oa_attachments attachment", connection.queries[0][0])

    def test_historical_oa_source_alias_lookup_is_exact_and_canonicalized(self) -> None:
        source_alias = "6a0ee8613bb8164165d8c61a"
        connection = FakeConnection(
            invoice_rows=[
                invoice_row(
                    source_links=[
                        {
                            "source_kind": "oa_attachment_invoice",
                            "metadata": {
                                "derived_from_oa_id": f"oa-exp-{source_alias}:item:2:9ca59ea6e4ab",
                            },
                        }
                    ]
                )
            ],
            historical_oa_rows=[
                oa_row(
                    "oa-exp-2206",
                    payload={
                        "apply_type": "日常报销",
                        "detail_fields": {"Mongo文档ID": source_alias},
                    },
                )
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        self.assertEqual(
            {fact.member_key for fact in result.facts},
            {("invoice", "inv-1"), ("oa", "oa-exp-2206")},
        )
        historical_params = next(
            params
            for query, params in connection.queries
            if "jsonb_each_text" in query
        )
        self.assertIn(source_alias, historical_params[2])
        self.assertEqual(historical_params[3], [source_alias, f"oa-exp-{source_alias}"])

    def test_conflicting_oa_source_aliases_fail_closed(self) -> None:
        payload = {
            "apply_type": "日常报销",
            "detail_fields": {"Mongo文档ID": "duplicate-source-id"},
        }
        connection = FakeConnection(
            oa_rows=[
                oa_row("oa-exp-2206", payload=payload),
                oa_row("oa-exp-2207", payload=payload),
            ]
        )

        with self.assertRaisesRegex(ValueError, "resolves to multiple canonical rows"):
            PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

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

    def test_single_member_bank_batch_relation_is_a_claim_not_a_formal_anchor(self) -> None:
        connection = FakeConnection(
            bank_rows=[bank_row("txn-1")],
            active_rows=[
                {
                    "case_id": "no_oa_batch_001",
                    "relation_mode": "bank_flow_rule_batch",
                    "row_ids": ["txn-1"],
                    "row_types": ["bank"],
                }
            ],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        self.assertEqual(result.facts, ())
        self.assertEqual(result.active_relations, ())

    def test_single_member_manual_relation_remains_invalid(self) -> None:
        connection = FakeConnection(
            bank_rows=[bank_row("txn-1")],
            active_rows=[
                {
                    "case_id": "case:invalid",
                    "relation_mode": "manual_confirmed",
                    "row_ids": ["txn-1"],
                    "row_types": ["bank"],
                }
            ],
        )

        with self.assertRaisesRegex(ValueError, "at least two row_ids"):
            PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

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

    def test_renminbi_currency_aliases_share_the_canonical_matching_bucket(self) -> None:
        oa = oa_row()
        bank = bank_row()
        invoice = invoice_row()
        oa["currency"] = "人民币"
        bank["currency"] = "人民币元"
        invoice["currency"] = "rmb"

        result = PostgresWorkbenchFormalRelationFactRepository(
            FakeConnection(oa_rows=[oa], bank_rows=[bank], invoice_rows=[invoice])
        ).load_batch(["2026-05"])

        self.assertEqual({fact.currency for fact in result.facts}, {"CNY"})

    def test_renminbi_bank_alias_can_complete_existing_daily_reimbursement_relation(self) -> None:
        oa = oa_row(
            "oa-exp-2363",
            applicant="樊祖芳",
            payload={"apply_type": "日常报销"},
            approved_at=datetime(2026, 5, 8, tzinfo=timezone.utc),
        )
        bank = bank_row("txn_imported_1061", counterparty="樊祖芳")
        bank["currency"] = "人民币元"
        connection = FakeConnection(
            oa_rows=[oa],
            bank_rows=[bank],
            invoice_rows=[invoice_row("inv-attachment")],
            active_rows=[
                {
                    "case_id": "CASE-AUTO-0076EC3CA6BA0F837824",
                    "row_ids": ["oa-exp-2363", "inv-attachment"],
                    "row_types": ["oa", "invoice"],
                }
            ],
        )

        batch = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])
        result = WorkbenchFreeMatchingEngine().plan_relations(batch)

        self.assertEqual(len(result.plans), 1)
        self.assertEqual(result.plans[0].target_case_id, "CASE-AUTO-0076EC3CA6BA0F837824")
        self.assertEqual(result.plans[0].rule_code, "strong_evidence_exact_singleton_extension")

    def test_daily_reimbursement_applicant_and_bank_payee_are_strong_employee_evidence(self) -> None:
        connection = FakeConnection(
            oa_rows=[
                oa_row(
                    "oa-exp-2363",
                    applicant="樊祖芳",
                    payload={"apply_type": "日常报销"},
                    fact_date=date(2026, 7, 17),
                    approved_at=datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc),
                )
            ],
            bank_rows=[bank_row("txn_imported_1061", counterparty="樊祖芳")],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-07"])
        facts = {fact.row_type: fact for fact in result.facts}

        self.assertIn(("employee_reimbursement_payee", "樊祖芳"), facts["oa"].evidence_keys)
        self.assertIn(("employee_reimbursement_payee", "樊祖芳"), facts["bank"].evidence_keys)
        self.assertNotIn(("counterparty", "樊祖芳"), facts["bank"].evidence_keys)
        self.assertEqual(facts["oa"].fact_date, date(2026, 8, 1))
        self.assertIn("oa.approved_at", connection.queries[0][0])

    def test_payment_application_applicant_is_not_employee_reimbursement_evidence(self) -> None:
        connection = FakeConnection(
            oa_rows=[oa_row(applicant="樊祖芳", payload={"apply_type": "支付申请"})],
        )

        result = PostgresWorkbenchFormalRelationFactRepository(connection).load_batch(["2026-05"])

        self.assertNotIn(
            ("employee_reimbursement_payee", "樊祖芳"),
            result.facts[0].evidence_keys,
        )

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
