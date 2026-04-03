from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from decimal import Decimal
from itertools import combinations

from fin_ops_platform.domain.enums import MatchingConfidence, MatchingResultType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Invoice, MatchingResult, MatchingRun
from fin_ops_platform.services.imports import ImportNormalizationService, normalize_name


ZERO = Decimal("0.00")


class MatchingEngineService:
    def __init__(self, import_service: ImportNormalizationService) -> None:
        self._import_service = import_service
        self._run_counter = 0
        self._result_counter = 0
        self._runs: dict[str, MatchingRun] = {}
        self._results: dict[str, MatchingResult] = {}

    @classmethod
    def from_snapshot(
        cls,
        import_service: ImportNormalizationService,
        snapshot: dict[str, object] | None,
    ) -> MatchingEngineService:
        service = cls(import_service)
        if not snapshot:
            return service
        service._run_counter = int(snapshot.get("run_counter", 0))
        service._result_counter = int(snapshot.get("result_counter", 0))
        service._runs = dict(snapshot.get("runs", {}))
        service._results = dict(snapshot.get("results", {}))
        return service

    def snapshot(self) -> dict[str, object]:
        return {
            "run_counter": self._run_counter,
            "result_counter": self._result_counter,
            "runs": self._runs,
            "results": self._results,
        }

    def run(self, *, triggered_by: str) -> MatchingRun:
        invoices = [invoice for invoice in self._import_service.list_invoices() if invoice.outstanding_amount > ZERO]
        transactions = [txn for txn in self._import_service.list_transactions() if txn.outstanding_amount > ZERO]
        available_invoice_ids = {invoice.id for invoice in invoices}
        available_transaction_ids = {txn.id for txn in transactions}

        invoice_by_id = {invoice.id: invoice for invoice in invoices}
        transaction_by_id = {txn.id: txn for txn in transactions}
        results: list[MatchingResult] = []

        results.extend(
            self._build_exact_matches(
                invoice_by_id,
                transaction_by_id,
                available_invoice_ids,
                available_transaction_ids,
            )
        )
        results.extend(
            self._build_combination_suggestions(
                invoice_by_id,
                transaction_by_id,
                available_invoice_ids,
                available_transaction_ids,
            )
        )
        results.extend(
            self._build_partial_suggestions(
                invoice_by_id,
                transaction_by_id,
                available_invoice_ids,
                available_transaction_ids,
            )
        )
        results.extend(
            self._build_manual_review_results(
                invoice_by_id,
                transaction_by_id,
                available_invoice_ids,
                available_transaction_ids,
            )
        )

        run_id = self._next_run_id()
        run_results = [replace(result, run_id=run_id) for result in results]
        run = MatchingRun(
            id=run_id,
            triggered_by=triggered_by,
            invoice_count=len(invoices),
            transaction_count=len(transactions),
            results=run_results,
        )
        self._runs[run.id] = run
        for result in run_results:
            self._results[result.id] = result
        return run

    def list_runs(self) -> list[MatchingRun]:
        return list(self._runs.values())

    def list_results(self) -> list[MatchingResult]:
        return list(self._results.values())

    def get_result(self, result_id: str) -> MatchingResult:
        return self._results[result_id]

    def latest_run(self) -> MatchingRun | None:
        if not self._runs:
            return None
        latest_id = sorted(self._runs.keys())[-1]
        return self._runs[latest_id]

    def _build_exact_matches(
        self,
        invoice_by_id: dict[str, Invoice],
        transaction_by_id: dict[str, BankTransaction],
        available_invoice_ids: set[str],
        available_transaction_ids: set[str],
    ) -> list[MatchingResult]:
        invoice_groups: dict[tuple[str, str, Decimal], list[Invoice]] = defaultdict(list)
        transaction_groups: dict[tuple[str, str, Decimal], list[BankTransaction]] = defaultdict(list)

        for invoice in invoice_by_id.values():
            if invoice.id not in available_invoice_ids:
                continue
            key = (
                invoice.counterparty.normalized_name,
                expected_direction_for_invoice(invoice).value,
                invoice.outstanding_amount,
            )
            invoice_groups[key].append(invoice)
        for transaction in transaction_by_id.values():
            if transaction.id not in available_transaction_ids:
                continue
            key = (
                normalize_name(transaction.counterparty_name_raw),
                transaction.txn_direction.value,
                transaction.outstanding_amount,
            )
            transaction_groups[key].append(transaction)

        results: list[MatchingResult] = []
        for key in sorted(invoice_groups.keys()):
            invoices = invoice_groups[key]
            transactions = transaction_groups.get(key, [])
            if len(invoices) == 1 and len(transactions) == 1:
                invoice = invoices[0]
                transaction = transactions[0]
                if invoice.id not in available_invoice_ids or transaction.id not in available_transaction_ids:
                    continue
                available_invoice_ids.remove(invoice.id)
                available_transaction_ids.remove(transaction.id)
                results.append(
                    self._make_result(
                        result_type=MatchingResultType.AUTOMATIC_MATCH,
                        confidence=MatchingConfidence.HIGH,
                        rule_code="exact_counterparty_amount_one_to_one",
                        explanation="Counterparty, direction, and amount matched exactly.",
                        invoice_ids=[invoice.id],
                        transaction_ids=[transaction.id],
                        amount=invoice.outstanding_amount,
                        counterparty_name=invoice.counterparty.name,
                    )
                )
        return results

    def _build_combination_suggestions(
        self,
        invoice_by_id: dict[str, Invoice],
        transaction_by_id: dict[str, BankTransaction],
        available_invoice_ids: set[str],
        available_transaction_ids: set[str],
    ) -> list[MatchingResult]:
        results: list[MatchingResult] = []

        for transaction in sorted(
            (transaction_by_id[txn_id] for txn_id in list(available_transaction_ids)),
            key=lambda txn: txn.id,
        ):
            candidate_invoices = [
                invoice
                for invoice in invoice_by_id.values()
                if invoice.id in available_invoice_ids
                and invoice.counterparty.normalized_name == normalize_name(transaction.counterparty_name_raw)
                and expected_direction_for_invoice(invoice) == transaction.txn_direction
            ]
            match = find_exact_sum_match(candidate_invoices, transaction.outstanding_amount)
            if match is None:
                continue
            for invoice in match:
                available_invoice_ids.remove(invoice.id)
            available_transaction_ids.remove(transaction.id)
            results.append(
                self._make_result(
                    result_type=MatchingResultType.SUGGESTED_MATCH,
                    confidence=MatchingConfidence.MEDIUM,
                    rule_code="same_counterparty_many_invoices_one_transaction",
                    explanation="Multiple invoices under the same counterparty sum to one transaction.",
                    invoice_ids=[invoice.id for invoice in match],
                    transaction_ids=[transaction.id],
                    amount=transaction.outstanding_amount,
                    counterparty_name=match[0].counterparty.name,
                )
            )

        for invoice in sorted(
            (invoice_by_id[inv_id] for inv_id in list(available_invoice_ids)),
            key=lambda invoice: invoice.id,
        ):
            candidate_transactions = [
                transaction
                for transaction in transaction_by_id.values()
                if transaction.id in available_transaction_ids
                and normalize_name(transaction.counterparty_name_raw) == invoice.counterparty.normalized_name
                and transaction.txn_direction == expected_direction_for_invoice(invoice)
            ]
            match = find_exact_sum_match(candidate_transactions, invoice.outstanding_amount)
            if match is None:
                continue
            for transaction in match:
                available_transaction_ids.remove(transaction.id)
            available_invoice_ids.remove(invoice.id)
            results.append(
                self._make_result(
                    result_type=MatchingResultType.SUGGESTED_MATCH,
                    confidence=MatchingConfidence.MEDIUM,
                    rule_code="same_counterparty_one_invoice_many_transactions",
                    explanation="One invoice amount can be composed by multiple transactions under the same counterparty.",
                    invoice_ids=[invoice.id],
                    transaction_ids=[transaction.id for transaction in match],
                    amount=invoice.outstanding_amount,
                    counterparty_name=invoice.counterparty.name,
                )
            )
        return results

    def _build_partial_suggestions(
        self,
        invoice_by_id: dict[str, Invoice],
        transaction_by_id: dict[str, BankTransaction],
        available_invoice_ids: set[str],
        available_transaction_ids: set[str],
    ) -> list[MatchingResult]:
        results: list[MatchingResult] = []
        for invoice in sorted(
            (invoice_by_id[inv_id] for inv_id in list(available_invoice_ids)),
            key=lambda item: item.id,
        ):
            candidates = [
                transaction
                for transaction in transaction_by_id.values()
                if transaction.id in available_transaction_ids
                and normalize_name(transaction.counterparty_name_raw) == invoice.counterparty.normalized_name
                and transaction.txn_direction == expected_direction_for_invoice(invoice)
            ]
            if len(candidates) != 1:
                continue
            transaction = candidates[0]
            if transaction.outstanding_amount == invoice.outstanding_amount:
                continue
            available_invoice_ids.remove(invoice.id)
            available_transaction_ids.remove(transaction.id)
            difference_amount = abs(invoice.outstanding_amount - transaction.outstanding_amount)
            results.append(
                self._make_result(
                    result_type=MatchingResultType.SUGGESTED_MATCH,
                    confidence=MatchingConfidence.LOW,
                    rule_code="same_counterparty_partial_amount_match",
                    explanation="Counterparty and direction matched, but the amount differed and requires manual confirmation.",
                    invoice_ids=[invoice.id],
                    transaction_ids=[transaction.id],
                    amount=min(invoice.outstanding_amount, transaction.outstanding_amount),
                    difference_amount=difference_amount,
                    counterparty_name=invoice.counterparty.name,
                )
            )
        return results

    def _build_manual_review_results(
        self,
        invoice_by_id: dict[str, Invoice],
        transaction_by_id: dict[str, BankTransaction],
        available_invoice_ids: set[str],
        available_transaction_ids: set[str],
    ) -> list[MatchingResult]:
        results: list[MatchingResult] = []
        for invoice_id in sorted(available_invoice_ids):
            invoice = invoice_by_id[invoice_id]
            results.append(
                self._make_result(
                    result_type=MatchingResultType.MANUAL_REVIEW,
                    confidence=MatchingConfidence.LOW,
                    rule_code="no_confident_match",
                    explanation="No confident bank transaction match was found for this invoice.",
                    invoice_ids=[invoice.id],
                    transaction_ids=[],
                    amount=invoice.outstanding_amount,
                    counterparty_name=invoice.counterparty.name,
                )
            )
        for transaction_id in sorted(available_transaction_ids):
            transaction = transaction_by_id[transaction_id]
            results.append(
                self._make_result(
                    result_type=MatchingResultType.MANUAL_REVIEW,
                    confidence=MatchingConfidence.LOW,
                    rule_code="no_confident_match",
                    explanation="No confident invoice match was found for this bank transaction.",
                    invoice_ids=[],
                    transaction_ids=[transaction.id],
                    amount=transaction.outstanding_amount,
                    counterparty_name=transaction.counterparty_name_raw,
                )
            )
        return results

    def _make_result(
        self,
        *,
        result_type: MatchingResultType,
        confidence: MatchingConfidence,
        rule_code: str,
        explanation: str,
        invoice_ids: list[str],
        transaction_ids: list[str],
        amount: Decimal,
        counterparty_name: str | None,
        difference_amount: Decimal = ZERO,
    ) -> MatchingResult:
        return MatchingResult(
            id=self._next_result_id(),
            run_id="pending",
            result_type=result_type,
            confidence=confidence,
            rule_code=rule_code,
            explanation=explanation,
            invoice_ids=invoice_ids,
            transaction_ids=transaction_ids,
            amount=amount,
            difference_amount=difference_amount,
            counterparty_name=counterparty_name,
        )

    def _next_run_id(self) -> str:
        self._run_counter += 1
        return f"match_run_{self._run_counter:04d}"

    def _next_result_id(self) -> str:
        self._result_counter += 1
        return f"match_result_{self._result_counter:05d}"


def expected_direction_for_invoice(invoice: Invoice) -> TransactionDirection:
    return TransactionDirection.INFLOW if invoice.invoice_type.value == "output" else TransactionDirection.OUTFLOW


def find_exact_sum_match(items: list[Invoice] | list[BankTransaction], target_amount: Decimal) -> list[Invoice] | list[BankTransaction] | None:
    ordered_items = sorted(items, key=lambda item: item.id)
    for size in range(2, min(4, len(ordered_items) + 1)):
        for combo in combinations(ordered_items, size):
            combo_total = sum((item.outstanding_amount for item in combo), start=ZERO)
            if combo_total == target_amount:
                return list(combo)
    return None
