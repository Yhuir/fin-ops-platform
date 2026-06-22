from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import unittest

from fin_ops_platform.tools.repair_submitted_etc_invoice_overlaps import (
    _ensure_apply_candidate_examples_complete,
    audit_submitted_etc_invoice_overlaps,
    apply_submitted_etc_invoice_overlap_repair,
)


class _OverlapConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return [
            {
                "invoice_id": "a6181d79-c3eb-4e20-bbd2-719215ed161d",
                "invoice_legacy_id": "inv_imported_0609",
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
                "workbench_visibility": "visible",
                "invoice_etc_invoice_id": None,
                "etc_row_id": "etc-row-1",
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
                "etc_batch_id": "etc_batch_hist_20260413_241125",
                "business_batch_id": "etc_business_batch_hist_20260413_241125",
                "business_batch_status": "manually_marked_submitted",
            },
            {
                "invoice_id": "manual-review-id",
                "invoice_legacy_id": "manual-review",
                "invoice_month": "2026-03-01",
                "invoice_no": "26537912330300001801",
                "digital_invoice_no": "26537912330300001801",
                "invoice_date": "2026-03-13",
                "seller_name": "云南高速",
                "buyer_name": "云南溯源科技有限公司",
                "amount": Decimal("20.91"),
                "tax_amount": Decimal("1.88"),
                "total_with_tax": Decimal("22.79"),
                "workbench_visibility": "visible",
                "invoice_etc_invoice_id": None,
                "etc_row_id": "etc-row-2",
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
                "invoice_id": "hidden-id",
                "invoice_legacy_id": "hidden",
                "invoice_month": "2026-05-01",
                "invoice_no": "26537910570500024764",
                "digital_invoice_no": "26537910570500024764",
                "invoice_date": "2026-05-17",
                "seller_name": "云南宾南高速公路有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "amount": Decimal("25.59"),
                "tax_amount": Decimal("2.30"),
                "total_with_tax": Decimal("27.89"),
                "workbench_visibility": "hidden_after_etc_submission",
                "invoice_etc_invoice_id": "etc_invoice_0553",
                "etc_row_id": "etc-row-3",
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

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


class _TransactionalOverlapConnection(_OverlapConnection):
    @contextmanager
    def transaction(self):
        yield self


class _QueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.enqueued.append(dict(kwargs))


class RepairSubmittedEtcInvoiceOverlapsToolTests(unittest.TestCase):
    def test_dry_run_classifies_auto_manual_and_no_action_candidates(self) -> None:
        report = audit_submitted_etc_invoice_overlaps(connection=_OverlapConnection())

        self.assertEqual(report["summary"]["overlap_pair_count"], 3)
        self.assertEqual(report["summary"]["auto_fix_candidate_count"], 1)
        self.assertEqual(report["summary"]["manual_review_candidate_count"], 1)
        self.assertEqual(report["summary"]["no_action_candidate_count"], 1)
        self.assertEqual(report["summary"]["affected_workbench_scopes"], ["2026-02", "all"])
        self.assertEqual(report["auto_fix_candidates"][0]["etc_invoice_id"], "etc_invoice_0028")
        self.assertEqual(report["manual_review_candidates"][0]["failed_checks"], ["invoice_date"])

    def test_dry_run_zero_example_limit_keeps_counts_without_samples(self) -> None:
        report = audit_submitted_etc_invoice_overlaps(connection=_OverlapConnection(), example_limit=0)

        self.assertEqual(report["summary"]["overlap_pair_count"], 3)
        self.assertEqual(report["summary"]["auto_fix_candidate_count"], 1)
        self.assertEqual(report["summary"]["manual_review_candidate_count"], 1)
        self.assertEqual(report["summary"]["no_action_candidate_count"], 1)
        self.assertEqual(report["auto_fix_candidates"], [])
        self.assertEqual(report["manual_review_candidates"], [])
        self.assertEqual(report["no_action_candidates"], [])

    def test_apply_updates_only_auto_candidates_and_enqueues_workbench_refresh(self) -> None:
        connection = _TransactionalOverlapConnection()
        queue = _QueueRepository()
        report = audit_submitted_etc_invoice_overlaps(connection=connection)

        result = apply_submitted_etc_invoice_overlap_repair(
            connection=connection,
            auto_fix_candidates=report["auto_fix_candidates"],
            reason="unit_test_repair",
            operator="tester",
            queue_repository=queue,
        )

        self.assertEqual(result["updated_count"], 1)
        self.assertEqual(result["affected_workbench_scopes"], ["2026-02", "all"])
        self.assertEqual(result["enqueued_workbench_scopes"], ["2026-02", "all"])
        self.assertEqual(len(connection.executed), 1)
        self.assertEqual(connection.executed[0][1][-1], "a6181d79-c3eb-4e20-bbd2-719215ed161d")
        self.assertEqual(
            [(item["scope_type"], item["scope_key"], item["priority"]) for item in queue.enqueued],
            [("workbench", "2026-02", "high"), ("workbench", "all", "high")],
        )

    def test_apply_requires_reason_and_operator(self) -> None:
        with self.assertRaises(ValueError):
            apply_submitted_etc_invoice_overlap_repair(
                connection=_OverlapConnection(),
                auto_fix_candidates=[],
                reason="",
                operator="tester",
            )
        with self.assertRaises(ValueError):
            apply_submitted_etc_invoice_overlap_repair(
                connection=_OverlapConnection(),
                auto_fix_candidates=[],
                reason="unit",
                operator="",
            )

    def test_apply_guard_requires_exact_candidate_row_set_in_report(self) -> None:
        report = audit_submitted_etc_invoice_overlaps(connection=_OverlapConnection(), example_limit=0)

        with self.assertRaises(ValueError):
            _ensure_apply_candidate_examples_complete(
                report,
                candidates_key="auto_fix_candidates",
                count_key="auto_fix_candidate_count",
            )


if __name__ == "__main__":
    unittest.main()
