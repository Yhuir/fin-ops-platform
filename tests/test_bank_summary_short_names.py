from __future__ import annotations

import unittest
from copy import deepcopy
from types import SimpleNamespace

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_details_canonical_query import BankDetailsCanonicalQueryService
from fin_ops_platform.services.bank_settings import bank_account_display_labels_from_settings, bank_short_names_from_mappings, bank_summary_with_short_names
from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsQueryService
from fin_ops_platform.services.cost_statistics_manual_allocation_service import CostStatisticsManualAllocationService
from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from tests.test_bank_details_canonical_query import _SnapshotRepository
from tests import test_cost_statistics_source_allocation as cost_fixture
from tests import test_turnover_ledger_service as turnover_fixture
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import InputInvoiceUsageCanonicalQueryService
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import OutputInvoiceCollectionCanonicalQueryService
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    InvoiceUsageCollectionCanonicalSnapshot,
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
)
from tests.test_invoice_usage_collection_canonical_query import RecordingTransaction, StaticTransactionConnection
from tests import test_oa_pending_payment_canonical_rows as oa_rows_fixture
from tests.test_oa_pending_payment_query_service import CanonicalQueryRepository

MAPPINGS = [{"bank_name": "建设银行", "last4": "0012", "short_name": "建行"}]


class BankSummaryShortNameTests(unittest.TestCase):
    def test_exact_mapping_missing_conflicting_and_leading_zero_accounts(self):
        bank = {"bankName": "建设银行", "accountLast4": "0012", "bankAccount": "建设银行 0012"}
        for mappings, expected in [
            (MAPPINGS, "建行"), (MAPPINGS * 2, "建行"), ([], ""),
            ([{"bank_name": "工商银行", "last4": "0012", "short_name": "工行"}], ""),
            (MAPPINGS + [{**MAPPINGS[0], "short_name": "另一简称"}], ""),
            (MAPPINGS + [{**MAPPINGS[0], "short_name": ""}], ""),
            ([{**MAPPINGS[0], "last4": 12}], ""),
        ]:
            with self.subTest(mappings=mappings):
                before = deepcopy(bank)
                result = bank_summary_with_short_names(bank, bank_short_names_from_mappings(mappings))
                self.assertEqual(result, {**before, "bankShortName": expected})
                self.assertEqual(bank, before)
        self.assertEqual(bank_summary_with_short_names({}, bank_short_names_from_mappings(MAPPINGS)), {"bankShortName": ""})

    def test_invoice_pages_decorate_all_summaries_without_mutating_source_or_fetching_settings(self):
        original = {"bankName": "建设银行", "accountLast4": "0012", "bankAccount": "建设银行 0012",
                    "amount": "100.00", "summaries": [
                        {"bankName": "建设银行", "accountLast4": "0012"},
                        {"bankName": "其他银行", "accountLast4": "0012"},
                    ]}
        before = deepcopy(original)
        snapshot = InvoiceUsageCollectionCanonicalSnapshot(
            groups=[{"group_key": "invoice", "line_items": []}], supporting_groups=[], relations=[],
            transactions=[], oa_records=[], overlays={}, pagination={}, summary={}, statistics={},
            facet_counts={}, payment_status_labels={}, bank_account_mappings=deepcopy(MAPPINGS),
        )
        assembler = SimpleNamespace(_row_payload=lambda *args, **kwargs: {"bankTransactions": original})
        for cls in (InputInvoiceUsageCanonicalQueryService, OutputInvoiceCollectionCanonicalQueryService):
            bank = cls(repository=None, row_assembler=assembler)._rows_from_snapshot(snapshot)[0]["bankTransactions"]
            self.assertEqual(bank["bankShortName"], "建行")
            self.assertEqual([item["bankShortName"] for item in bank["summaries"]], ["建行", ""])
            self.assertEqual(bank["bankAccount"], before["bankAccount"])
            self.assertEqual(bank["amount"], before["amount"])
            self.assertEqual(original, before)

    def test_invoice_repositories_return_mapping_in_existing_snapshot_queries(self):
        class Transaction(RecordingTransaction):
            def fetch_one(self, sql, _params=None):
                self.statements.append(sql)
                if sql.lstrip().startswith("select settings_payload"):
                    return {"settings_payload": {"bank_account_mappings": MAPPINGS}}
                if "as supporting_group_rows" in sql:
                    return {"bank_account_mappings": MAPPINGS}
                return {}
        for cls in (PostgresInputInvoiceUsageQueryRepository, PostgresOutputInvoiceCollectionQueryRepository):
            transaction = Transaction()
            result = cls(StaticTransactionConnection(transaction)).load_page(
                page=1, page_size=20, keyword=None, invoice_date_from=None, invoice_date_to=None,
                month=None, filters=[], sort_field="invoice_date", sort_direction="desc",
            )
            self.assertEqual(result.bank_account_mappings, MAPPINGS)
            standalone = [sql for sql in transaction.statements if sql.lstrip().startswith("select settings_payload")]
            self.assertEqual(len(standalone), 1 if cls is PostgresInputInvoiceUsageQueryRepository else 0)

    def test_oa_page_uses_selected_snapshot_mapping_and_keeps_canonical_bank_unchanged(self):
        fixture = oa_rows_fixture.OaPendingPaymentProjectionRowsTests()
        record, bank = fixture._oa("oa-1", "100.00"), fixture._bank("bank-1", "100.00")
        bank.imported_bank_last4 = "0012"
        bank.account_no = "622200000012"
        before = deepcopy(bank)
        relations = [fixture._relation("case-1", [record.id, bank.id])]
        display = fixture._build(records=[record], relations=relations, banks=[bank])[0]
        repository = CanonicalQueryRepository()
        original_select = repository.select_page
        def select(**kwargs):
            result = original_select(**kwargs)
            return {**result, "bank_account_mappings": MAPPINGS, "descriptors": [{
                "row_id": display["id"], "scope_key": record.month,
                "source_kind": "completed", "oa_ids": [record.id],
            }]}
        repository.select_page = select
        repository.load_facts = lambda *args, **kwargs: {
            "completed_records": [record], "in_progress_records": [], "relations": relations,
            "bank_transactions": [bank], "invoices": [], "payment_statuses": {},
        }
        result = OaPendingPaymentQueryService(repository=repository).rows({}, tenant_id="default")
        summary = result["rows"][0]["bankTransaction"]
        self.assertEqual(summary["bankShortName"], "建行")
        self.assertEqual(summary["summaries"][0]["bankShortName"], "建行")
        self.assertEqual(summary["accountLast4"], "0012")
        self.assertEqual(bank, before)
        self.assertEqual(repository.snapshot_entries, 1)
        self.assertEqual(len(repository.select_calls), 1)

    def test_display_label_uses_every_existing_resolver_format_without_guessing_names(self):
        labels = bank_account_display_labels_from_settings({"bank_account_mappings": MAPPINGS})
        for account_name in (None, "公司基本存款", "一般结算", "项目专户"):
            source = BankAccountResolver().resolve_label(None, account_name, preferred_bank_name="建设银行", preferred_last4="0012")
            self.assertEqual(labels[source], "建行 0012")
        self.assertEqual(labels["建设银行 0012"], "建行 0012")
        for source in ("建设银行 12", "其他银行 0012", "建设银行 账户 0012 附注"):
            self.assertNotIn(source, labels)
        self.assertEqual(bank_account_display_labels_from_settings({"bank_account_mappings": MAPPINGS + [{**MAPPINGS[0], "short_name": "另名"}]}), {})

    def test_bank_details_display_does_not_change_workbench_mapper_or_source_fields(self):
        snapshot = _SnapshotRepository().transactions_snapshot()
        snapshot["settings"]["bank_account_mappings"] = MAPPINGS
        snapshot["rows"][0].update(bank_name="建设银行", account_last4="0012")
        before = deepcopy(snapshot)
        raw = BankDetailsCanonicalQueryService._transactions_payload(snapshot, account_key=None, date_from=None, date_to=None)
        display = BankDetailsCanonicalQueryService._ordered_transactions_payload(snapshot, account_key=None, date_from=None, date_to=None)
        self.assertNotIn("bank_short_name", raw["rows"][0])
        self.assertEqual(display["rows"][0]["bank_short_name"], "建行")
        self.assertEqual(display["rows"][0]["account_last4"], "0012")
        self.assertEqual(snapshot, before)

    def test_cost_snapshot_names_preserve_filter_keys_financial_results_and_decision_fingerprint(self):
        policy, group = cost_fixture.AutomaticFormalSourceTests().policy((100,), (100,))
        group["bank_rows"][0]["payment_account_label"] = "建设银行 账户 0012"
        group["relation_display_groups"] = [{"oa_row_ids": ["0"], "bank_row_ids": ["0"]}]
        snapshot = {"settings": {**policy._settings, "bank_account_mappings": MAPPINGS},
                    "cost_groups": [group], "bank_rows": group["bank_rows"], "bank_statistics": {}, "manual_projects": [], "manual_allocations": {}}
        baseline = CostStatisticsPolicy(snapshot)
        before = deepcopy(snapshot)
        reads = []
        repository = SimpleNamespace(load_snapshot=lambda **kwargs: (reads.append(kwargs) or snapshot),
            load_relation_snapshot=lambda *_, **_kwargs: snapshot,
            load_manual_allocation_task_snapshot=lambda: snapshot,
            load_no_oa_tag_candidate_snapshot=lambda: snapshot)
        query = CostStatisticsQueryService(canonical_repository=repository)
        page = query.get_explorer_page(scope="all", view="time", filters={}, cursor=None, page_size=20)
        self.assertEqual(page["rows"][0]["bank_account_display_label"], "建行 0012")
        self.assertEqual(page["rows"][0]["payment_account_label"], "建设银行 账户 0012")
        facets = query.get_explorer_page(scope="all", view="bank_account", filters={}, cursor=None, page_size=20)["facets"]["bank_accounts"]
        self.assertEqual(facets[0]["bank_account_label"], "建设银行 账户 0012")
        self.assertEqual(facets[0]["bank_account_display_label"], "建行 0012")
        self.assertEqual(len(reads), 2)
        task = CostStatisticsManualAllocationService(canonical_repository=repository, allocation_repository=None).get_task(group["group_id"], can_save=True)
        self.assertEqual(task["bank_events"][0]["bank_account_display_label"], "建行 0012")
        self.assertEqual(task["source_fingerprint"], baseline.allocation_tasks[0]["source_fingerprint"])
        # An automatic-equivalent save is a read-only return and must carry the same DTO.
        unchanged = CostStatisticsManualAllocationService(canonical_repository=repository, allocation_repository=None).save(
            group["group_id"], {
                "relation_case_id": group["group_id"], "expected_version": 0,
                "source_fingerprint": task["source_fingerprint"], "scope_version": task["scope_version"],
                "oa_amount_locks": [{"unit_id": unit["unit_id"], "locked": unit["lock_oa_amount"]} for unit in task["units"]],
                "manual_items": [], "oa_cost_tag_overrides": [], "allocations": task["allocations"],
                "source_allocations": task["source_allocations"], "non_cost_amount": "0.00", "non_cost_reason": "",
            }, actor={"id": "display-test"},
        )
        self.assertEqual(unchanged["bank_events"], task["bank_events"])
        self.assertEqual(unchanged["version"], 0)
        allocation_id = baseline.serialized_cost_rows[0]["allocation_id"]
        detail = query.get_allocation_detail(allocation_id, scope="all", view="project")
        self.assertEqual(detail["allocation"]["bank_account_display_label"], "建行 0012")
        self.assertEqual(detail["payment_evidence"][0]["bank_account_display_label"], "建行 0012")
        self.assertEqual(snapshot, before)

    def test_turnover_display_is_separate_from_raw_labels_relations_and_amounts(self):
        service = turnover_fixture.TurnoverLedgerServiceTests()._grouped_service()
        before = service.list_grouped_ledger()
        service._bank_account_display_labels = {"建行 1001": "真实简称 1001"}
        after = service.list_grouped_ledger()
        self.assertEqual(after["summary"], before["summary"])
        self.assertEqual(after["statistics"], before["statistics"])
        displayed = 0
        for previous, current in zip(before["groups"], after["groups"], strict=True):
            for old, row in zip([previous["summary_row"], *previous["flow_rows"]], [current["summary_row"], *current["flow_rows"]], strict=True):
                self.assertEqual(row["bank_account_labels"], old["bank_account_labels"])
                self.assertEqual({k: v for k, v in row.items() if k != "bank_account_display_labels"}, {k: v for k, v in old.items() if k != "bank_account_display_labels"})
                if "建行 1001" in row["bank_account_labels"]:
                    self.assertIn("真实简称 1001", row["bank_account_display_labels"])
                    displayed += 1
        self.assertGreater(displayed, 0)
