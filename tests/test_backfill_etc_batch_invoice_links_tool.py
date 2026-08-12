from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.tools.backfill_etc_batch_invoice_links import (
    _etc_batch_invoice_links_table_exists,
    _ensure_apply_candidate_examples_complete,
    apply_etc_batch_invoice_link_backfill,
    audit_etc_batch_invoice_link_backfill,
)


class _BackfillConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
        return [
            {
                "link_id": None,
                "invoice_id": "invoice-auto",
                "invoice_month": "2026-02-01",
                "invoice_no": "26537912570200055449",
                "digital_invoice_no": "26537912570200055449",
                "invoice_date": "2026-02-28",
                "seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                "seller_tax_no": "9153000077859986X2",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "amount": Decimal("18.63"),
                "tax_amount": Decimal("0.56"),
                "total_with_tax": Decimal("19.19"),
                "etc_invoice_id": "etc_invoice_0028",
                "etc_invoice_no": "26537912570200055449",
                "etc_invoice_date": "2026-02-28",
                "etc_seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                "etc_seller_tax_no": "9153000077859986X2",
                "etc_buyer_name": "云南溯源科技有限公司",
                "etc_buyer_tax_no": "915300007194052520",
                "etc_amount": Decimal("18.63"),
                "etc_tax_amount": Decimal("0.56"),
                "etc_total_with_tax": Decimal("19.19"),
                "business_batch_id": "etc_business_batch_hist_20260413_241125",
                "business_batch_status": "manually_marked_submitted",
            },
            {
                "link_id": None,
                "invoice_id": "invoice-manual",
                "invoice_month": "2026-03-01",
                "invoice_no": "26537912330300001801",
                "digital_invoice_no": "26537912330300001801",
                "invoice_date": "2026-03-13",
                "seller_name": "云南高速",
                "buyer_name": "云南溯源科技有限公司",
                "amount": Decimal("20.91"),
                "tax_amount": Decimal("1.88"),
                "total_with_tax": Decimal("22.79"),
                "etc_invoice_id": "etc_invoice_0047",
                "etc_invoice_no": "26537912330300001801",
                "etc_invoice_date": "2026-03-14",
                "etc_seller_name": "云南高速",
                "etc_buyer_name": "云南溯源科技有限公司",
                "etc_amount": Decimal("20.91"),
                "etc_tax_amount": Decimal("1.88"),
                "etc_total_with_tax": Decimal("22.79"),
                "business_batch_id": "etc_business_batch_hist_20260413_241125",
                "business_batch_status": "manually_marked_submitted",
            },
            {
                "link_id": "link-existing",
                "invoice_id": "invoice-linked",
                "invoice_month": "2026-05-01",
                "invoice_no": "26537910570500024764",
                "digital_invoice_no": "26537910570500024764",
                "invoice_date": "2026-05-17",
                "seller_name": "云南宾南高速公路有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "amount": Decimal("25.59"),
                "tax_amount": Decimal("2.30"),
                "total_with_tax": Decimal("27.89"),
                "etc_invoice_id": "etc_invoice_0553",
                "etc_invoice_no": "26537910570500024764",
                "etc_invoice_date": "2026-05-17",
                "etc_seller_name": "云南宾南高速公路有限公司",
                "etc_buyer_name": "云南溯源科技有限公司",
                "etc_amount": Decimal("25.59"),
                "etc_tax_amount": Decimal("2.30"),
                "etc_total_with_tax": Decimal("27.89"),
                "business_batch_id": "etc_business_batch_0014",
                "business_batch_status": "manually_marked_submitted",
            },
        ]

    def fetch_one(self, sql: str, params: tuple = ()) -> dict:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return {"id": f"link-{len(self.fetch_one_calls)}", "business_batch_id": params[3], "identity_key": params[5]}


class _SchemaProbeConnection:
    def __init__(self, table_name: str | None) -> None:
        self.table_name = table_name

    def fetch_one(self, sql: str, params: tuple = ()) -> dict:
        return {"table_name": self.table_name}


class _QueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


class _MatchingDirtyRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def mark_workbench_matching_dirty_scopes(self, **kwargs: object) -> list[str]:
        self.calls.append(dict(kwargs))
        return list(kwargs["scope_months"])


class BackfillEtcBatchInvoiceLinksToolTests(unittest.TestCase):
    def test_dry_run_classifies_auto_manual_and_existing_links_with_rollback_plan(self) -> None:
        report = audit_etc_batch_invoice_link_backfill(connection=_BackfillConnection(), example_limit=10)

        self.assertEqual(report["summary"]["candidate_count"], 3)
        self.assertEqual(report["summary"]["auto_backfill_count"], 1)
        self.assertEqual(report["summary"]["manual_review_count"], 1)
        self.assertEqual(report["summary"]["already_linked_count"], 1)
        self.assertEqual(report["summary"]["affected_months"], ["2026-02"])
        self.assertTrue(report["summary"]["rollback_plan_available"])
        self.assertEqual(report["auto_backfill_candidates"][0]["invoice_id"], "invoice-auto")
        self.assertEqual(report["manual_review_candidates"][0]["failed_checks"], ["invoice_date"])
        self.assertEqual(report["already_linked"][0]["link_id"], "link-existing")
        self.assertIn("link_status='removed'", report["rollback_plan"]["sql_template"])

    def test_apply_requires_reason_and_operator_and_only_applies_auto_candidates(self) -> None:
        connection = _BackfillConnection()
        queue = _QueueRepository()
        matching = _MatchingDirtyRepository()
        report = audit_etc_batch_invoice_link_backfill(connection=connection, example_limit=10)

        with self.assertRaises(ValueError):
            apply_etc_batch_invoice_link_backfill(connection=connection, auto_backfill_candidates=[], reason="", operator="tester")
        with self.assertRaises(ValueError):
            apply_etc_batch_invoice_link_backfill(connection=connection, auto_backfill_candidates=[], reason="unit", operator="")

        result = apply_etc_batch_invoice_link_backfill(
            connection=connection,
            auto_backfill_candidates=report["auto_backfill_candidates"],
            reason="unit",
            operator="tester",
            queue_repository=queue,
            matching_dirty_repository=matching,
        )

        self.assertEqual(result["requested_count"], 1)
        self.assertEqual(result["linked_count"], 1)
        self.assertEqual(result["affected_months"], ["2026-02"])
        self.assertEqual(result["workbench_relation_scopes"], ["2026-02"])
        self.assertEqual(
            [(item["scope_type"], item["scope_key"], item["priority"]) for item in queue.enqueued],
            [("workbench_relation", "2026-02", "high")],
        )
        self.assertEqual(
            matching.calls,
            [
                {
                    "tenant_id": "default",
                    "scope_months": ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04"],
                    "reason": "etc_batch_invoice_link_backfill",
                    "source_versions": {},
                    "debounce_seconds": 0,
                }
            ],
        )
        self.assertEqual(
            result["matching_dirty_scopes"],
            ["2025-12", "2026-01", "2026-02", "2026-03", "2026-04"],
        )
        self.assertEqual(len(connection.fetch_one_calls), 1)

    def test_apply_guard_requires_exact_candidate_row_set_in_report(self) -> None:
        report = audit_etc_batch_invoice_link_backfill(connection=_BackfillConnection(), example_limit=0)

        with self.assertRaises(ValueError):
            _ensure_apply_candidate_examples_complete(
                report,
                candidates_key="auto_backfill_candidates",
                count_key="auto_backfill_count",
            )

    def test_dry_run_can_be_limited_to_one_exact_business_batch(self) -> None:
        connection = _BackfillConnection()

        report = audit_etc_batch_invoice_link_backfill(
            connection=connection,
            example_limit=10,
            business_batch_id="etc_business_batch_0014",
        )

        self.assertEqual(report["summary"]["candidate_count"], 1)
        self.assertEqual(report["summary"]["already_linked_count"], 1)
        self.assertEqual(
            connection.fetch_all_calls[0][1],
            ("etc_business_batch_0014", "etc_business_batch_0014"),
        )
        self.assertIn("%s::text is null", connection.fetch_all_calls[0][0])

    def test_schema_preflight_reports_missing_link_table(self) -> None:
        self.assertFalse(_etc_batch_invoice_links_table_exists(_SchemaProbeConnection(None)))
        self.assertTrue(_etc_batch_invoice_links_table_exists(_SchemaProbeConnection("app.etc_batch_invoice_links")))


if __name__ == "__main__":
    unittest.main()
