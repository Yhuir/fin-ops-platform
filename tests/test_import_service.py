import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import BatchType, ImportDecision, InvoiceStatus, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService


class BulkInvoiceIdentityRepository:
    def __init__(self, invoices: list[Invoice] | None = None) -> None:
        self.invoices = list(invoices or [])
        self.bulk_calls = 0
        self.single_calls = 0
        self.many_calls = 0

    def find_invoices_by_identity_keys(
        self,
        *,
        canonical_keys: list[str],
        suspected_keys: list[str],
    ) -> list[Invoice]:
        self.bulk_calls += 1
        canonical_set = set(canonical_keys)
        suspected_set = set(suspected_keys)
        return [
            invoice
            for invoice in self.invoices
            if (invoice.source_unique_key and invoice.source_unique_key in canonical_set)
            or (invoice.digital_invoice_no and invoice.digital_invoice_no in canonical_set)
            or (invoice.data_fingerprint and invoice.data_fingerprint in suspected_set)
        ]

    def find_invoice_identity(
        self,
        *,
        source_unique_key: str | None = None,
        data_fingerprint: str | None = None,
    ) -> Invoice | None:
        self.single_calls += 1
        return None

    def find_invoices_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[Invoice]:
        self.many_calls += 1
        return []


class SubmittedEtcIdentityRepository(BulkInvoiceIdentityRepository):
    def __init__(self, *, etc_invoice: object) -> None:
        super().__init__(invoices=[])
        self.etc_invoice = etc_invoice
        self.submitted_lookup_calls = 0
        self.link_calls: list[dict[str, object]] = []

    def find_submitted_etc_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
        invoice_no: str | None = None,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
    ) -> object | None:
        self.submitted_lookup_calls += 1
        expected_invoice_no = getattr(self.etc_invoice, "invoice_number", None)
        if canonical_key == expected_invoice_no or digital_invoice_no == expected_invoice_no or invoice_no == expected_invoice_no:
            return self.etc_invoice
        return None

    def upsert_etc_batch_invoice_link(self, **kwargs: object) -> dict[str, object]:
        self.link_calls.append(dict(kwargs))
        return {"id": "etc-link-1", **kwargs}


class FailingSubmittedEtcIdentityRepository(BulkInvoiceIdentityRepository):
    def find_submitted_etc_invoice_by_identity(self, **kwargs: object) -> object | None:
        raise RuntimeError("submitted etc lookup failed")


class BulkBankTransactionRepository:
    def __init__(self, transactions: list[BankTransaction]) -> None:
        self.transactions = list(transactions)
        self.calls: list[list[str]] = []

    def list_bank_transactions_by_ids(self, transaction_ids: list[str]) -> list[BankTransaction]:
        self.calls.append(list(transaction_ids))
        requested = set(transaction_ids)
        return [transaction for transaction in self.transactions if transaction.id in requested]


class BulkBankIdentityRepository:
    def __init__(self, transactions: list[BankTransaction]) -> None:
        self.transactions = list(transactions)
        self.bulk_calls = 0
        self.single_calls = 0
        self.many_calls = 0

    def find_bank_transactions_by_identity_keys(
        self,
        *,
        canonical_keys: list[str],
        suspected_keys: list[str],
    ) -> list[BankTransaction]:
        self.bulk_calls += 1
        canonical_set = set(canonical_keys)
        suspected_set = set(suspected_keys)
        return [
            transaction
            for transaction in self.transactions
            if (transaction.source_unique_key and transaction.source_unique_key in canonical_set)
            or (transaction.data_fingerprint and transaction.data_fingerprint in suspected_set)
        ]

    def find_bank_transaction_by_identity(self, **_kwargs: object) -> BankTransaction | None:
        self.single_calls += 1
        return None

    def find_bank_transactions_by_identity(self, **_kwargs: object) -> list[BankTransaction]:
        self.many_calls += 1
        return []


class ImportNormalizationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.counterparty = Counterparty(
            id="cp_001",
            name="Acme Supplies",
            normalized_name="acme supplies",
            counterparty_type="vendor",
        )
        self.existing_invoice = Invoice(
            id="inv_existing_001",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="9001",
            counterparty=self.counterparty,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            invoice_date="2026-03-21",
            status=InvoiceStatus.PENDING,
            source_unique_key="033001:9001",
            data_fingerprint="invoice-fp-existing",
            invoice_status_from_source="valid",
        )
        self.existing_invoice_without_unique = Invoice(
            id="inv_existing_002",
            invoice_type=InvoiceType.INPUT,
            invoice_no="N/A",
            counterparty=self.counterparty,
            amount=Decimal("66.00"),
            signed_amount=Decimal("66.00"),
            invoice_date="2026-03-22",
            source_unique_key=None,
            data_fingerprint="invoice:acme supplies:2026-03-22:66.00",
        )
        self.existing_transaction = BankTransaction(
            id="txn_existing_001",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme Supplies Ltd.",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            txn_date="2026-03-23",
            trade_time="2026-03-23 09:15:01",
            source_unique_key="bank-v2:62220001:bank_serial_no:SERIAL-001",
            data_fingerprint="bank:62220001:2026-03-23 09:15:01:outflow:88.00:acme supplies ltd.",
            bank_serial_no="SERIAL-001",
        )
        self.service = ImportNormalizationService(
            existing_invoices=[self.existing_invoice, self.existing_invoice_without_unique],
            existing_transactions=[self.existing_transaction],
        )

    def test_list_transactions_by_ids_uses_one_bulk_repository_read_and_preserves_requested_order(self) -> None:
        second = BankTransaction(
            id="txn_repository_002",
            account_no="62220002",
            txn_direction=TransactionDirection.INFLOW,
            counterparty_name_raw="Beta",
            amount=Decimal("12.00"),
            signed_amount=Decimal("12.00"),
            txn_date="2026-03-24",
        )
        repository = BulkBankTransactionRepository([second])
        service = ImportNormalizationService(
            existing_transactions=[self.existing_transaction],
            fact_repository=repository,
        )

        result = service.list_transactions_by_ids(
            [second.id, self.existing_transaction.id, second.id, "missing"]
        )

        self.assertEqual([transaction.id for transaction in result], [second.id, self.existing_transaction.id])
        self.assertEqual(repository.calls, [[second.id, "missing"]])

    def test_bank_transaction_strict_statement_evidence_requires_all_six_fields(self) -> None:
        transaction = BankTransaction(
            id="txn-strict-evidence",
            account_no="62229999",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor A",
            amount=Decimal("50.00"),
            signed_amount=Decimal("-50.00"),
            txn_date="2026-03-24",
            trade_time="2026-03-24 10:00:00",
            balance=Decimal("950.00"),
            currency="CNY",
        )
        service = ImportNormalizationService(existing_transactions=[transaction])
        normalized = {
            "account_no": "62229999",
            "trade_time": "2026-03-24 10:00:00",
            "txn_direction": "outflow",
            "amount": "50.00",
            "balance": "950.00",
            "currency": "人民币元",
            "counterparty_name": "Vendor A",
        }

        self.assertTrue(
            service.bank_transaction_matches_strict_statement_evidence(
                transaction_id=transaction.id,
                normalized=normalized,
            )
        )
        self.assertFalse(
            service.bank_transaction_matches_strict_statement_evidence(
                transaction_id=transaction.id,
                normalized={**normalized, "balance": "949.99"},
            )
        )
        self.assertFalse(
            service.bank_transaction_matches_strict_statement_evidence(
                transaction_id=transaction.id,
                normalized={**normalized, "trade_time": None},
            )
        )
        self.assertFalse(
            service.bank_transaction_matches_strict_statement_evidence(
                transaction_id="missing-transaction",
                normalized=normalized,
            )
        )

    def test_invoice_identity_service_uses_tax_amount_canonical_key_and_only_suspects_weak_match(self) -> None:
        identity_service = InvoiceIdentityService()

        identity = identity_service.identity_for_mapping(
            {
                "seller_tax_no": "915300007873997205",
                "buyer_tax_no": "915300007194052520",
                "invoice_date": "2026-02-05",
                "total_with_tax": "41.75",
                "seller_name": "云南省交通投资建设集团有限公司",
                "buyer_name": "云南溯源科技有限公司",
            }
        )
        weak_identity = identity_service.identity_for_mapping(
            {
                "seller_name": "云南省交通投资建设集团有限公司",
                "buyer_name": "云南溯源科技有限公司",
                "invoice_date": "2026-02-05",
                "total_with_tax": "41.75",
            }
        )

        self.assertEqual(identity.canonical_key, "tax:915300007873997205:915300007194052520:2026-02-05:41.75")
        self.assertIsNone(identity.suspected_key)
        self.assertIsNone(weak_identity.canonical_key)
        self.assertEqual(weak_identity.suspected_key, "suspected:云南省交通投资建设集团有限公司:云南溯源科技有限公司:2026-02-05:41.75")

    def test_invoice_identity_service_treats_bare_20_digit_invoice_number_as_digital_identity(self) -> None:
        identity = InvoiceIdentityService().identity_for_mapping(
            {"invoice_no": "26539150014000401220"}
        )

        self.assertEqual(identity.canonical_key, "26539150014000401220")
        self.assertIsNone(identity.suspected_key)

    def test_upsert_etc_invoice_does_not_create_missing_canonical_invoice_by_default(self) -> None:
        existing = Invoice(
            id="inv_existing_etc",
            invoice_type=InvoiceType.INPUT,
            invoice_no="OLD-ETC-NO",
            digital_invoice_no="OLD-ETC-NO",
            counterparty=Counterparty(
                id="cp_etc",
                name="云南省交通投资建设集团有限公司",
                normalized_name="云南省交通投资建设集团有限公司",
                counterparty_type="vendor",
            ),
            amount=Decimal("147.25"),
            signed_amount=Decimal("147.25"),
            invoice_date="2026-03-06",
            total_with_tax=Decimal("147.25"),
            source_unique_key="OLD-ETC-NO",
            data_fingerprint="invoice:云南省交通投资建设集团有限公司:2026-03-06:147.25",
        )
        service = ImportNormalizationService(existing_invoices=[existing])
        etc_invoice = type(
            "EtcInvoice",
            (),
            {
                "id": "etc_invoice_new",
                "invoice_number": "NEW-ETC-NO",
                "issue_date": "2026-03-06",
                "seller_name": "云南省交通投资建设集团有限公司",
                "seller_tax_no": "",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "",
                "total_amount": Decimal("147.25"),
                "tax_amount": Decimal("4.29"),
                "tax_rate": "3%",
                "import_batch_id": "etc_import_batch_hist",
                "current_batch_id": "etc_batch_0035",
                "last_batch_id": "etc_batch_0035",
                "status": "submitted",
            },
        )()

        result = service.upsert_etc_invoice(etc_invoice)

        self.assertIsNone(result.invoice)
        self.assertFalse(result.changed)
        self.assertEqual(len(service.list_invoices()), 1)

    def test_upsert_etc_invoice_links_same_amount_same_day_existing_invoices_distinctly(self) -> None:
        counterparty = Counterparty(
            id="cp_etc_same_day",
            name="昆明新机场高速公路建设发展有限公司",
            normalized_name="昆明新机场高速公路建设发展有限公司",
            counterparty_type="vendor",
        )
        service = ImportNormalizationService(
            existing_invoices=[
                Invoice(
                    id="inv_existing_etc_0442",
                    invoice_type=InvoiceType.INPUT,
                    invoice_no="26537911470300077680",
                    digital_invoice_no="26537911470300077680",
                    counterparty=counterparty,
                    amount=Decimal("9.23"),
                    signed_amount=Decimal("9.23"),
                    invoice_date="2026-03-31",
                    total_with_tax=Decimal("9.50"),
                    source_unique_key="26537911470300077680",
                ),
                Invoice(
                    id="inv_existing_etc_0443",
                    invoice_type=InvoiceType.INPUT,
                    invoice_no="26537911470300077790",
                    digital_invoice_no="26537911470300077790",
                    counterparty=counterparty,
                    amount=Decimal("9.23"),
                    signed_amount=Decimal("9.23"),
                    invoice_date="2026-03-31",
                    total_with_tax=Decimal("9.50"),
                    source_unique_key="26537911470300077790",
                ),
            ]
        )
        base_fields = {
            "issue_date": "2026-03-31",
            "seller_name": "昆明新机场高速公路建设发展有限公司",
            "seller_tax_no": "",
            "buyer_name": "云南溯源科技有限公司",
            "buyer_tax_no": "",
            "total_amount": Decimal("9.50"),
            "tax_amount": Decimal("0.27"),
            "tax_rate": "3%",
            "import_batch_id": "etc_import_batch_0012",
            "current_batch_id": "etc_business_batch_0006",
            "last_batch_id": "etc_business_batch_0006",
            "status": "unsubmitted",
        }
        first = type("EtcInvoice", (), {"id": "etc_invoice_0442", "invoice_number": "26537911470300077680", **base_fields})()
        second = type("EtcInvoice", (), {"id": "etc_invoice_0443", "invoice_number": "26537911470300077790", **base_fields})()

        first_result = service.upsert_etc_invoice(first)
        second_result = service.upsert_etc_invoice(second)
        first_invoice = first_result.invoice
        second_invoice = second_result.invoice

        self.assertIsNotNone(first_invoice)
        self.assertIsNotNone(second_invoice)
        self.assertTrue(first_result.changed)
        self.assertTrue(second_result.changed)
        assert first_invoice is not None
        assert second_invoice is not None
        self.assertEqual(first_invoice.id, "inv_existing_etc_0442")
        self.assertEqual(second_invoice.id, "inv_existing_etc_0443")
        self.assertEqual(first_invoice.source_unique_key, "26537911470300077680")
        self.assertEqual(second_invoice.source_unique_key, "26537911470300077790")
        self.assertIsNone(first_invoice.data_fingerprint)
        self.assertIsNone(second_invoice.data_fingerprint)
        self.assertEqual(len(service.list_invoices()), 2)

        replay_result = service.upsert_etc_invoice(first)

        self.assertIs(replay_result.invoice, first_invoice)
        self.assertFalse(replay_result.changed)

    def test_existing_canonical_invoice_drops_weak_fingerprint_on_load(self) -> None:
        stale = Invoice(
            id="inv_existing_etc_stale",
            invoice_type=InvoiceType.INPUT,
            invoice_no="26537911470300077680",
            digital_invoice_no="26537911470300077680",
            counterparty=Counterparty(
                id="cp_etc_stale",
                name="昆明新机场高速公路建设发展有限公司",
                normalized_name="昆明新机场高速公路建设发展有限公司",
                counterparty_type="vendor",
            ),
            amount=Decimal("9.22"),
            signed_amount=Decimal("9.22"),
            invoice_date="2026-03-31",
            total_with_tax=Decimal("9.22"),
            source_unique_key="26537911470300077680",
            data_fingerprint="invoice:昆明新机场高速公路建设发展有限公司:2026-03-31:9.22",
        )

        service = ImportNormalizationService(existing_invoices=[stale])

        loaded = service.get_invoice("inv_existing_etc_stale")
        self.assertEqual(loaded.source_unique_key, "26537911470300077680")
        self.assertIsNone(loaded.data_fingerprint)

    def test_preview_output_invoice_classifies_rows_across_all_decision_types(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="output-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9002",
                    "counterparty_name": "  New Corp Ltd. ",
                    "amount": "120.00",
                    "invoice_date": "2026/03/24",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "cancelled",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "counterparty_name": "Acme Supplies",
                    "amount": "66.00",
                    "invoice_date": "2026-03-22",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9003",
                    "counterparty_name": "Bad Amount Inc",
                    "amount": "abc",
                    "invoice_date": "2026-03-25",
                },
            ],
        )

        decisions = [row.decision for row in preview.row_results]
        self.assertEqual(
            decisions,
            [
                ImportDecision.CREATED,
                ImportDecision.STATUS_UPDATED,
                ImportDecision.DUPLICATE_SKIPPED,
                ImportDecision.SUSPECTED_DUPLICATE,
                ImportDecision.ERROR,
            ],
        )
        self.assertEqual(preview.success_count, 2)
        self.assertEqual(preview.updated_count, 1)
        self.assertEqual(preview.duplicate_count, 1)
        self.assertEqual(preview.suspected_duplicate_count, 1)
        self.assertEqual(preview.error_count, 1)

    def test_preview_bank_transaction_normalizes_direction_and_skips_existing_identity(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62229999",
                    "txn_date": "2026-03-24",
                    "trade_time": "2026-03-24 10:00:00",
                    "counterparty_name": "Vendor A",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-NEW-001",
                    "summary": "purchase",
                },
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "",
                    "voucher_no": "",
                    "enterprise_serial_no": "",
                    "summary": "same as old but no official id",
                },
                {
                    "account_no": "62220001",
                    "txn_date": "bad-date",
                    "counterparty_name": "",
                    "debit_amount": "",
                    "credit_amount": "not-number",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)
        self.assertEqual(preview.normalized_rows[0]["txn_direction"], TransactionDirection.OUTFLOW.value)
        self.assertEqual(preview.normalized_rows[0]["signed_amount"], "-50.00")
        self.assertEqual(preview.row_results[0].identity_kind, "stable")
        self.assertEqual(preview.row_results[0].account_no, "62229999")
        self.assertEqual(preview.row_results[0].trade_time, "2026-03-24 10:00:00")
        self.assertEqual(preview.row_results[0].direction, TransactionDirection.OUTFLOW.value)
        self.assertEqual(preview.row_results[0].amount, "50.00")
        self.assertEqual(preview.row_results[0].counterparty_name, "Vendor A")
        self.assertEqual(preview.row_results[1].decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(preview.row_results[1].identity_kind, "suspected")
        self.assertEqual(preview.row_results[2].decision, ImportDecision.ERROR)

    def test_invoice_placeholder_digital_number_does_not_mask_stable_code_number_key(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="placeholder-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "digital_invoice_no": "--",
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "valid",
                },
            ],
        )

        self.assertEqual(preview.normalized_rows[0]["digital_invoice_no"], None)
        self.assertEqual(preview.normalized_rows[0]["source_unique_key"], "033001:9001")
        self.assertEqual(preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)

    def test_bank_transaction_unique_key_includes_account_number(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-account-scope-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62229999",
                    "txn_date": "2026-03-24",
                    "trade_time": "2026-03-24 10:00:00",
                    "counterparty_name": "Vendor A",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-001",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)
        self.assertTrue(
            preview.normalized_rows[0]["source_unique_key"].startswith(
                "bank-v3:62229999:bank_serial_no:SERIAL-001:"
            )
        )
        self.assertEqual(
            preview.normalized_rows[0]["data_fingerprint"],
            "bank:62229999:2026-03-24 10:00:00:outflow:50.00:vendor a",
        )

    def test_bank_transaction_same_official_serial_with_different_amount_is_created(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-serial-not-key-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "89.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-001",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)

    def test_bank_transaction_new_identity_version_falls_back_to_exact_fingerprint(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-legacy-identity-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-001",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(preview.row_results[0].linked_object_id, self.existing_transaction.id)

    def test_bank_transaction_preview_and_confirm_use_one_bulk_identity_read_each(self) -> None:
        repository = BulkBankIdentityRepository([self.existing_transaction])
        service = ImportNormalizationService(fact_repository=repository)
        preview = service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-bulk-identity-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-001",
                }
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(repository.bulk_calls, 1)
        self.assertEqual(repository.single_calls, 0)
        self.assertEqual(repository.many_calls, 0)

        service.confirm_import(preview.batch.id)

        self.assertEqual(repository.bulk_calls, 2)
        self.assertEqual(repository.single_calls, 0)
        self.assertEqual(repository.many_calls, 0)

    def test_bank_transaction_confirm_cache_detects_duplicate_created_earlier_in_same_batch(self) -> None:
        repository = BulkBankIdentityRepository([])
        service = ImportNormalizationService(fact_repository=repository)
        raw_row = {
            "account_no": "62229999",
            "txn_date": "2026-03-24",
            "trade_time": "2026-03-24 10:00:00",
            "counterparty_name": "Vendor A",
            "debit_amount": "50.00",
            "credit_amount": "",
            "bank_serial_no": "SERIAL-NEW-001",
        }
        preview = service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-same-batch-dedup-demo.json",
            imported_by="user_finance_01",
            rows=[dict(raw_row), dict(raw_row)],
        )

        self.assertEqual(
            [row.decision for row in preview.row_results],
            [ImportDecision.CREATED, ImportDecision.CREATED],
        )
        service.confirm_import(preview.batch.id)

        self.assertEqual(
            [row.decision for row in preview.row_results],
            [ImportDecision.CREATED, ImportDecision.DUPLICATE_SKIPPED],
        )
        self.assertEqual(len(service.list_transactions()), 1)
        self.assertEqual(repository.bulk_calls, 2)
        self.assertEqual(repository.single_calls, 0)
        self.assertEqual(repository.many_calls, 0)

    def test_reused_official_reference_persists_distinct_statement_positions_idempotently(self) -> None:
        existing = BankTransaction(
            id="txn-position-1",
            account_no="62229999",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Vendor A",
            amount=Decimal("50.00"),
            signed_amount=Decimal("-50.00"),
            txn_date="2026-03-24",
            trade_time="2026-03-24 10:00:00",
            bank_serial_no="REUSED-REF",
            balance=Decimal("1000.00"),
            currency="CNY",
        )
        service = ImportNormalizationService(existing_transactions=[existing])
        raw_row = {
            "account_no": "62229999",
            "txn_date": "2026-03-24",
            "trade_time": "2026-03-24 10:00:00",
            "counterparty_name": "Vendor A",
            "debit_amount": "50.00",
            "credit_amount": "",
            "bank_serial_no": "REUSED-REF",
            "balance": "950.00",
            "currency": "人民币元",
        }

        first_preview = service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-reused-reference-1.json",
            imported_by="user_finance_01",
            rows=[raw_row],
        )
        self.assertEqual(first_preview.row_results[0].decision, ImportDecision.CREATED)
        self.assertTrue(str(first_preview.row_results[0].source_unique_key).startswith("bank-v4:"))
        service.confirm_import(first_preview.batch.id)

        transactions = service.list_transactions()
        self.assertEqual(len(transactions), 2)
        self.assertEqual(len({transaction.source_unique_key for transaction in transactions}), 2)

        replay_preview = service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-reused-reference-2.json",
            imported_by="user_finance_01",
            rows=[raw_row],
        )
        self.assertEqual(replay_preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)
        service.confirm_import(replay_preview.batch.id)
        self.assertEqual(len(service.list_transactions()), 2)

    def test_bank_transaction_exact_fingerprint_with_different_official_reference_is_created(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-distinct-reference-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-002",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)

    def test_bank_transaction_official_reference_is_stable_without_second_level_time(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-missing-time-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-DATE-ONLY-001",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.CREATED)
        self.assertEqual(
            preview.row_results[0].source_unique_key,
            "bank-v2:62220001:bank_serial_no:SERIAL-DATE-ONLY-001",
        )
        self.assertEqual(preview.row_results[0].identity_kind, "stable")
        self.assertIsNone(preview.normalized_rows[0]["data_fingerprint"])

        self.service.confirm_import(preview.id)

        created = next(transaction for transaction in self.service.list_transactions() if transaction.bank_serial_no == "SERIAL-DATE-ONLY-001")
        self.assertEqual(created.txn_date, "2026-03-23")
        self.assertEqual(created.source_unique_key, "bank-v2:62220001:bank_serial_no:SERIAL-DATE-ONLY-001")

    def test_confirm_import_does_not_persist_weak_bank_match(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-weak-match-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "txn_date": "2026-03-23",
                    "trade_time": "2026-03-23 09:15:01",
                    "counterparty_name": "Acme Supplies Ltd.",
                    "debit_amount": "88.00",
                    "credit_amount": "",
                },
            ],
        )

        self.assertEqual(preview.row_results[0].decision, ImportDecision.SUSPECTED_DUPLICATE)
        batch = self.service.confirm_import(preview.id)

        self.assertEqual(batch.status.value, "completed_with_errors")
        self.assertEqual(
            preview.row_results[0].decision,
            ImportDecision.SUSPECTED_DUPLICATE,
        )
        self.assertEqual(batch.suspected_duplicate_count, 1)
        self.assertEqual(len(self.service.list_transactions()), 1)

    def test_confirm_import_persists_created_rows_and_updates_source_status(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="confirm-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9010",
                    "counterparty_name": "Created Corp",
                    "amount": "200.00",
                    "invoice_date": "2026-03-25",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                    "invoice_status_from_source": "cancelled",
                },
            ],
        )

        confirmed = self.service.confirm_import(preview.id)

        self.assertEqual(confirmed.status.value, "completed")
        self.assertEqual(len(self.service.list_invoices()), 3)
        updated = self.service.get_invoice("inv_existing_001")
        self.assertEqual(updated.invoice_status_from_source, "cancelled")
        created = next(invoice for invoice in self.service.list_invoices() if invoice.invoice_no == "9010")
        self.assertEqual(created.counterparty.normalized_name, "created corp")

    def test_preview_import_preloads_invoice_identity_in_bulk(self) -> None:
        repository = BulkInvoiceIdentityRepository(invoices=[self.existing_invoice])
        service = ImportNormalizationService(fact_repository=repository)

        preview = service.preview_import(
            batch_type=BatchType.OUTPUT_INVOICE,
            source_name="bulk-preview.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-21",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9011",
                    "counterparty_name": "New Supplies",
                    "amount": "50.00",
                    "invoice_date": "2026-03-22",
                },
            ],
        )

        self.assertEqual(repository.bulk_calls, 1)
        self.assertEqual(repository.single_calls, 0)
        self.assertEqual(repository.many_calls, 0)
        self.assertEqual(preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)
        self.assertEqual(preview.row_results[1].decision, ImportDecision.CREATED)

    def test_confirm_import_refreshes_invoice_identity_in_bulk(self) -> None:
        repository = BulkInvoiceIdentityRepository()
        service = ImportNormalizationService(fact_repository=repository)
        preview = service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="bulk-confirm.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "033001",
                    "invoice_no": "9012",
                    "counterparty_name": "Created Corp",
                    "amount": "200.00",
                    "invoice_date": "2026-03-25",
                },
                {
                    "invoice_code": "033001",
                    "invoice_no": "9013",
                    "counterparty_name": "Created Corp",
                    "amount": "201.00",
                    "invoice_date": "2026-03-26",
                },
            ],
        )

        service.confirm_import(preview.id)

        self.assertEqual(repository.bulk_calls, 2)
        self.assertEqual(repository.single_calls, 0)
        self.assertEqual(repository.many_calls, 0)

    def test_confirm_import_preserves_selected_bank_mapping_fields_on_created_transactions(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="bank-demo.json",
            imported_by="user_finance_01",
            rows=[
                {
                    "account_no": "62220001",
                    "account_name": "云南溯源科技有限公司建设银行基本户",
                    "txn_date": "2026-03-25",
                    "trade_time": "2026-03-25 09:00:00",
                    "pay_receive_time": "2026-03-25 09:00:00",
                    "counterparty_name": "Vendor A",
                    "debit_amount": "50.00",
                    "credit_amount": "",
                    "bank_serial_no": "SERIAL-SELECTED-001",
                    "selected_bank_name": "建设银行",
                    "selected_bank_last4": "8826",
                }
            ],
        )

        self.service.confirm_import(preview.id)

        created = next(transaction for transaction in self.service.list_transactions() if transaction.bank_serial_no == "SERIAL-SELECTED-001")
        self.assertEqual(created.account_no, "62220001")
        self.assertEqual(created.imported_bank_name, "建设银行")
        self.assertEqual(created.imported_bank_last4, "8826")

    def test_confirm_import_skips_duplicate_invoice_rows_within_same_batch(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="duplicate-in-batch.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                },
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                },
            ],
        )

        confirmed = self.service.confirm_import(preview.id)

        matching = [invoice for invoice in self.service.list_invoices() if invoice.digital_invoice_no == "26537912210200143464"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(confirmed.duplicate_count, 1)
        self.assertEqual(confirmed.success_count, 1)
        self.assertEqual(preview.row_results[1].decision, ImportDecision.DUPLICATE_SKIPPED)

    def test_confirm_import_skips_duplicate_invoice_from_later_preview_batch(self) -> None:
        feb_preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="全量发票查询导出结果-2026年2月.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                }
            ],
        )
        mar_preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="全量发票查询导出结果-2026年3月.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "",
                    "invoice_no": "",
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_rate": "3%",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                }
            ],
        )

        first_confirmed = self.service.confirm_import(feb_preview.id)
        second_confirmed = self.service.confirm_import(mar_preview.id)

        matching = [invoice for invoice in self.service.list_invoices() if invoice.digital_invoice_no == "26537912210200143464"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(first_confirmed.duplicate_count, 0)
        self.assertEqual(second_confirmed.duplicate_count, 1)
        self.assertEqual(second_confirmed.success_count, 0)
        self.assertEqual(mar_preview.row_results[0].decision, ImportDecision.DUPLICATE_SKIPPED)

    def test_input_invoice_import_merges_existing_etc_canonical_invoice_without_duplicate(self) -> None:
        etc_invoice = Invoice(
            id="inv_etc_001",
            invoice_type=InvoiceType.INPUT,
            invoice_no="26537912210200143464",
            counterparty=self.counterparty,
            amount=Decimal("41.75"),
            signed_amount=Decimal("41.75"),
            digital_invoice_no="26537912210200143464",
            invoice_date="2026-02-05",
            seller_tax_no="915300007873997205",
            seller_name="云南省交通投资建设集团有限公司",
            buyer_tax_no="915300007194052520",
            buyer_name="云南溯源科技有限公司",
            total_with_tax=Decimal("41.75"),
            source_unique_key="26537912210200143464",
            tags=["ETC"],
            source_links=[
                {
                    "source_type": "etc_import",
                    "source_id": "etc_invoice_0001",
                    "batch_id": "etc_batch_0001",
                    "created_at": "2026-02-05T00:00:00+00:00",
                }
            ],
            etc_invoice_id="etc_invoice_0001",
            etc_import_batch_id="etc_batch_0001",
        )
        service = ImportNormalizationService(existing_invoices=[etc_invoice])

        preview = service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="全量发票查询导出结果-2026年2月.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "digital_invoice_no": "26537912210200143464",
                    "seller_tax_no": "915300007873997205",
                    "seller_name": "云南省交通投资建设集团有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "40.53",
                    "tax_amount": "1.22",
                    "total_with_tax": "41.75",
                    "invoice_status_from_source": "正常",
                }
            ],
        )

        confirmed = service.confirm_import(preview.id)

        invoices = service.list_invoices()
        self.assertEqual(len(invoices), 1)
        self.assertEqual(confirmed.success_count, 1)
        self.assertEqual(preview.row_results[0].linked_object_id, "inv_etc_001")
        merged = service.get_invoice("inv_etc_001")
        self.assertIn("ETC", merged.tags)
        self.assertEqual(merged.etc_invoice_id, "etc_invoice_0001")
        self.assertEqual(
            [link["source_type"] for link in merged.source_links],
            ["etc_import", "manual_invoice_import"],
        )
        self.assertEqual(merged.source_links[1]["batch_id"], preview.id)

    def test_input_invoice_import_links_existing_submitted_etc_metadata_when_formal_invoice_arrives_later(self) -> None:
        etc_invoice = type(
            "EtcInvoice",
            (),
            {
                "id": "etc_invoice_0028",
                "invoice_number": "26537912570200055449",
                "issue_date": "2026-02-28",
                "seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                "seller_tax_no": "9153000077859986X2",
                "buyer_name": "云南溯源科技有限公司",
                "buyer_tax_no": "915300007194052520",
                "total_amount": Decimal("19.19"),
                "tax_amount": Decimal("0.56"),
                "tax_rate": "3%",
                "import_batch_id": "etc_batch_hist_20260413_241125",
                "current_batch_id": "etc_business_batch_hist_20260413_241125",
                "last_batch_id": "etc_business_batch_hist_20260413_241125",
                "status": "submitted",
            },
        )()
        repository = SubmittedEtcIdentityRepository(etc_invoice=etc_invoice)
        service = ImportNormalizationService(fact_repository=repository)

        preview = service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="进项全量发票查询导出结果1-6.22.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "digital_invoice_no": "26537912570200055449",
                    "seller_tax_no": "9153000077859986X2",
                    "seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南国道主干线昆明绕城高速公路建设有限公司",
                    "invoice_date": "2026-02-28",
                    "amount": "18.63",
                    "tax_amount": "0.56",
                    "total_with_tax": "19.19",
                    "invoice_status_from_source": "正常",
                }
            ],
        )

        confirmed = service.confirm_import(preview.id)

        self.assertEqual(confirmed.success_count, 1)
        self.assertEqual(repository.submitted_lookup_calls, 1)
        invoices = service.list_invoices()
        self.assertEqual(len(invoices), 1)
        imported = invoices[0]
        self.assertEqual(imported.etc_invoice_id, "etc_invoice_0028")
        self.assertEqual(imported.workbench_visibility, "hidden_after_etc_submission")
        self.assertIn("ETC", imported.tags)
        self.assertEqual(len(repository.link_calls), 1)
        self.assertEqual(repository.link_calls[0]["invoice_id"], imported.id)
        self.assertEqual(repository.link_calls[0]["etc_invoice_id"], "etc_invoice_0028")
        self.assertEqual(repository.link_calls[0]["business_batch_id"], "etc_business_batch_hist_20260413_241125")
        self.assertEqual(repository.link_calls[0]["link_source"], "formal_invoice_import")
        self.assertEqual(repository.link_calls[0]["confidence"], "strict")
        self.assertEqual(
            [link["source_type"] for link in imported.source_links],
            ["manual_invoice_import", "etc_invoice_import"],
        )

    def test_confirm_import_rolls_back_when_submitted_etc_lookup_fails(self) -> None:
        service = ImportNormalizationService(fact_repository=FailingSubmittedEtcIdentityRepository())
        preview = service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "digital_invoice_no": "26537912570200055449",
                    "seller_tax_no": "9153000077859986X2",
                    "seller_name": "供应商A",
                    "buyer_tax_no": "915300007194052520",
                    "buyer_name": "云南溯源科技有限公司",
                    "counterparty_name": "供应商A",
                    "invoice_date": "2026-02-28",
                    "amount": "18.63",
                    "tax_amount": "0.56",
                    "total_with_tax": "19.19",
                    "invoice_status_from_source": "正常",
                }
            ],
        )

        with self.assertRaisesRegex(RuntimeError, "submitted etc lookup failed"):
            service.confirm_import(preview.id)

        restored = service.get_batch(preview.id)
        self.assertEqual(restored.batch.status.value, "pending")
        self.assertEqual(service.list_invoices(), [])
        self.assertIsNone(restored.row_results[0].linked_object_id)

    def test_batch_persistence_snapshot_can_exclude_formalized_facts(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="input.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_no": "INV-SNAPSHOT",
                    "counterparty_name": "供应商A",
                    "invoice_date": "2026-02-28",
                    "amount": "18.63",
                    "invoice_status_from_source": "正常",
                }
            ],
        )
        self.service.confirm_import(preview.id)

        preview_snapshot = self.service.persistence_snapshot_for_batches(
            [preview.id],
            include_facts=False,
        )

        self.assertNotIn("invoices", preview_snapshot)
        self.assertNotIn("transactions", preview_snapshot)
        self.assertIn(preview.id, preview_snapshot["batches"])

    def test_input_invoice_import_marks_etc_tag_when_source_or_tags_indicate_etc(self) -> None:
        preview = self.service.preview_import(
            batch_type=BatchType.INPUT_INVOICE,
            source_name="etc-ledger.xlsx",
            imported_by="user_finance_01",
            rows=[
                {
                    "invoice_code": "053002",
                    "invoice_no": "ETC-9001",
                    "counterparty_name": "云南省交通投资建设集团有限公司",
                    "invoice_date": "2026-02-05",
                    "amount": "41.75",
                    "invoice_source": "ETC导入",
                    "tags": ["通行费", "ETC"],
                }
            ],
        )

        self.service.confirm_import(preview.id)

        created = next(invoice for invoice in self.service.list_invoices() if invoice.invoice_no == "ETC-9001")
        self.assertIn("ETC", created.tags)
        self.assertEqual(created.source_links[0]["source_type"], "manual_invoice_import")
        self.assertEqual(created.source_links[0]["batch_id"], preview.id)

    def test_oa_attachment_invoice_upsert_creates_canonical_invoice_with_source_context(self) -> None:
        invoice = self.service.upsert_oa_attachment_invoice(
            {
                "evidence_type": "tax_invoice",
                "document_kind": "digital_invoice",
                "digital_invoice_no": "26532000000141671581",
                "seller_tax_no": "91530000431200506F",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "tax_amount": "0.00",
                "total_with_tax": "400.00",
                "tax_rate": "0%",
                "invoice_type": "进项发票",
                "source_attachment_key": "attachment-key-001",
                "source_attachment_name": "invoice.pdf",
                "source_expense_item_id": "expense-item-001",
                "source_expense_row_index": "1",
                "source_region_key": "document:1",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-stable",
            allow_create=True,
        )

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice.id, "oa-att-inv-oa-exp-001-stable")
        self.assertEqual(invoice.invoice_type, InvoiceType.INPUT)
        self.assertEqual(invoice.amount, Decimal("400.00"))
        self.assertEqual(invoice.total_with_tax, Decimal("400.00"))
        self.assertEqual(invoice.oa_form_id, "oa-form-001")
        self.assertIn("OA附件", invoice.tags)
        self.assertEqual(invoice.source_links[0]["source_type"], "oa_attachment_invoice")
        self.assertEqual(invoice.source_links[0]["source_workbench_row_id"], "oa-att-inv-oa-exp-001-stable")
        self.assertEqual(invoice.source_links[0]["derived_from_oa_id"], "oa-exp-001")

    def test_oa_attachment_invoice_upsert_merges_existing_canonical_invoice(self) -> None:
        first = self.service.upsert_oa_attachment_invoice(
            {
                "evidence_type": "tax_invoice",
                "digital_invoice_no": "26532000000141671582",
                "seller_tax_no": "91530000431200506F",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "attachment-key-001",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-first",
            allow_create=True,
        )
        second = self.service.upsert_oa_attachment_invoice(
            {
                "evidence_type": "tax_invoice",
                "digital_invoice_no": "26532000000141671582",
                "seller_tax_no": "91530000431200506F",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "attachment-key-002",
            },
            oa_form_id="oa-form-002",
            oa_row_id="oa-exp-002",
            source_workbench_row_id="oa-att-inv-oa-exp-002-second",
        )

        self.assertIs(first, second)
        self.assertEqual(len([invoice for invoice in self.service.list_invoices() if invoice.invoice_no == "26532000000141671582"]), 1)
        assert first is not None
        self.assertEqual(
            [link["source_attachment_key"] for link in first.source_links if link["source_type"] == "oa_attachment_invoice"],
            ["attachment-key-001", "attachment-key-002"],
        )

    def test_oa_attachment_non_tax_receipt_is_not_promoted_as_formal_invoice(self) -> None:
        invoice = self.service.upsert_oa_attachment_invoice(
            {
                "evidence_type": "non_tax_receipt",
                "document_kind": "non_tax_receipt",
                "seller_name": "云南省财政厅",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "receipt-key-001",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-receipt",
        )

        self.assertIsNone(invoice)
        self.assertFalse(any(link.get("source_type") == "oa_attachment_invoice" for inv in self.service.list_invoices() for link in inv.source_links))

    def test_oa_attachment_allow_create_requires_strong_invoice_identity(self) -> None:
        initial_invoice_ids = {invoice.id for invoice in self.service.list_invoices()}

        invoice = self.service.upsert_oa_attachment_invoice(
            {
                "evidence_type": "tax_invoice",
                "seller_tax_no": "91530000431200506F",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_tax_no": "915300007194052520",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "attachment-key-without-invoice-no",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-weak",
            allow_create=True,
        )

        self.assertIsNone(invoice)
        self.assertEqual({invoice.id for invoice in self.service.list_invoices()}, initial_invoice_ids)

    def test_oa_attachment_allow_create_requires_formal_invoice_evidence(self) -> None:
        initial_invoice_ids = {invoice.id for invoice in self.service.list_invoices()}

        invoice = self.service.upsert_oa_attachment_invoice(
            {
                "digital_invoice_no": "26532000000141671583",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "attachment-key-without-evidence-type",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-unknown-evidence",
            allow_create=True,
        )

        self.assertIsNone(invoice)
        self.assertEqual({invoice.id for invoice in self.service.list_invoices()}, initial_invoice_ids)

    def test_oa_attachment_allow_create_accepts_formal_document_kind_without_evidence_type(self) -> None:
        invoice = self.service.upsert_oa_attachment_invoice(
            {
                "document_kind": "digital_invoice",
                "digital_invoice_no": "26532000000141671583",
                "seller_name": "云南建筑技术发展中心（云南地基技术发展中心）",
                "buyer_name": "云南溯源科技有限公司",
                "issue_date": "2026-01-27",
                "amount": "400.00",
                "total_with_tax": "400.00",
                "source_attachment_key": "attachment-key-formal-document-kind",
            },
            oa_form_id="oa-form-001",
            oa_row_id="oa-exp-001",
            source_workbench_row_id="oa-att-inv-oa-exp-001-formal-document-kind",
            allow_create=True,
        )

        self.assertIsNotNone(invoice)
        assert invoice is not None
        self.assertEqual(invoice.digital_invoice_no, "26532000000141671583")


if __name__ == "__main__":
    unittest.main()
