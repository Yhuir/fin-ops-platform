from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from fin_ops_platform.domain.enums import BatchStatus, BatchType, ImportDecision, InvoiceStatus, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


class CoreReadConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        if "from app.import_batches" in sql and "left join" not in sql:
            return [
                {
                    "legacy_id": "batch_1",
                    "batch_type": BatchType.INPUT_INVOICE.value,
                    "source_name": "input.xlsx",
                    "imported_by": "tester",
                    "row_count": 1,
                    "success_count": 1,
                    "error_count": 0,
                    "duplicate_count": 0,
                    "suspected_duplicate_count": 0,
                    "updated_count": 0,
                    "status": BatchStatus.COMPLETED.value,
                    "imported_at": datetime(2026, 3, 1, tzinfo=UTC),
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "batch_1",
                            "batch_type": BatchType.INPUT_INVOICE.value,
                            "source_name": "input.xlsx",
                            "imported_by": "tester",
                            "row_count": 1,
                            "success_count": 1,
                            "error_count": 0,
                            "status": BatchStatus.COMPLETED.value,
                        }
                    },
                }
            ]
        if "from app.invoices" in sql:
            return [
                {
                    "legacy_id": "invoice_1",
                    "invoice_type": InvoiceType.INPUT.value,
                    "invoice_no": "INV-001",
                    "invoice_date": "2026-03-01",
                    "counterparty_id": "counterparty_1",
                    "counterparty_name": "供应商A",
                    "amount": "100.00",
                    "signed_amount": "100.00",
                    "written_off_amount": "0.00",
                    "currency": "CNY",
                    "legacy_source_batch_id": "batch_1",
                    "workbench_visibility": "visible",
                    "status": InvoiceStatus.PENDING.value,
                    "tags": ["input"],
                    "source_links": [{"source_type": "import", "batch_id": "batch_1"}],
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "invoice_1",
                            "invoice_type": InvoiceType.INPUT.value,
                            "invoice_no": "INV-001",
                            "invoice_date": "2026-03-01",
                            "counterparty": {
                                "id": "counterparty_1",
                                "name": "供应商A",
                                "normalized_name": "供应商A",
                                "counterparty_type": "vendor",
                            },
                            "amount": "100.00",
                            "signed_amount": "100.00",
                            "source_batch_id": "batch_1",
                        }
                    },
                }
            ]
        if "from app.bank_transactions" in sql:
            return []
        if "from app.import_batch_rows" in sql:
            return [
                {
                    "legacy_id": "row_1",
                    "legacy_batch_id": "batch_1",
                    "joined_batch_id": "batch_1",
                    "row_no": 1,
                    "source_record_type": "invoice",
                    "decision": ImportDecision.CREATED.value,
                    "decision_reason": "Ready to create new invoice.",
                    "linked_object_type": "invoice",
                    "linked_object_id": "invoice_1",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "row_1",
                            "batch_id": "batch_1",
                            "row_no": 1,
                            "source_record_type": "invoice",
                            "decision": ImportDecision.CREATED.value,
                            "decision_reason": "Ready to create new invoice.",
                            "linked_object_type": "invoice",
                            "linked_object_id": "invoice_1",
                            "normalized_row": {
                                "invoice_type": InvoiceType.INPUT.value,
                                "invoice_no": "INV-001",
                                "invoice_date": "2026-03-01",
                                "counterparty_name": "供应商A",
                                "amount": "100.00",
                                "signed_amount": "100.00",
                            },
                        }
                    },
                }
            ]
        if "from app.import_files" in sql:
            return [
                {
                    "legacy_id": "file_1",
                    "session_id": "session_1",
                    "stored_file_path": "/tmp/input.xlsx",
                    "original_filename": "input.xlsx",
                    "template_kind": "invoice_export",
                    "status": "confirmed",
                    "uploaded_by": "tester",
                    "uploaded_at": datetime(2026, 3, 1, tzinfo=UTC),
                    "joined_batch_id": "batch_1",
                    "raw_payload": {
                        "normalized_payload": {
                            "id": "file_1",
                            "file_name": "input.xlsx",
                            "template_code": "invoice_export",
                            "batch_type": BatchType.INPUT_INVOICE.value,
                            "status": "confirmed",
                            "row_count": 1,
                            "success_count": 1,
                            "batch_id": "batch_1",
                            "stored_file_path": "/tmp/input.xlsx",
                            "session_id": "session_1",
                        }
                    },
                }
            ]
        return []


def test_core_repository_loads_domain_snapshots_accepted_by_services() -> None:
    repository = PostgresCoreRepository(CoreReadConnection())

    imports_snapshot = repository.load_imports()
    import_service = ImportNormalizationService.from_snapshot(imports_snapshot)

    assert list(imports_snapshot["batches"]) == ["batch_1"]
    assert import_service.list_invoices()[0].id == "invoice_1"
    assert import_service.list_invoices()[0].source_batch_id == "batch_1"

    file_snapshot = repository.load_file_imports()
    file_service = FileImportService.from_snapshot(import_service, file_snapshot)

    sessions = file_service.snapshot()["sessions"]
    assert sessions["session_1"].files[0].id == "file_1"
    assert sessions["session_1"].files[0].batch_id == "batch_1"


class PagedFactConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "with normalized as" in normalized and "from app.bank_transactions" in normalized and "latest_balances" in normalized:
            return [
                {
                    "bank_name": "交通银行",
                    "account_last4": "3847",
                    "transaction_count": 51,
                    "balance": "16091.81",
                    "latest_balance_at": "2026-04-23 17:33:58+08",
                }
            ]
        if "from app.invoices" in normalized:
            assert "limit %s offset %s" in normalized
            return [
                {
                    "legacy_id": "invoice_page_1",
                    "invoice_type": InvoiceType.INPUT.value,
                    "invoice_no": "INV-PAGE-1",
                    "invoice_date": "2026-05-01",
                    "counterparty_id": "cp_1",
                    "counterparty_name": "供应商A",
                    "amount": "128.00",
                    "signed_amount": "128.00",
                    "written_off_amount": "0.00",
                    "currency": "CNY",
                    "legacy_source_batch_id": "batch_import_0007",
                    "workbench_visibility": "visible",
                    "status": InvoiceStatus.PENDING.value,
                    "tags": [],
                    "source_links": [],
                    "raw_payload": {"normalized_payload": {"id": "invoice_page_1"}},
                }
            ]
        if "from app.bank_transactions" in normalized:
            assert "limit %s offset %s" in normalized
            return [
                {
                    "legacy_id": "txn_page_1",
                    "account_no": "62220000",
                    "txn_direction": TransactionDirection.OUTFLOW.value,
                    "counterparty_name_raw": "供应商A",
                    "amount": "99.00",
                    "signed_amount": "-99.00",
                    "written_off_amount": "0.00",
                    "txn_date": "2026-05-02",
                    "trade_time": "2026-05-02 09:00:00",
                    "legacy_source_batch_id": "batch_import_0008",
                    "status": "pending",
                    "raw_payload": {"normalized_payload": {"id": "txn_page_1"}},
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "count(*)" in normalized:
            return {"total": 123}
        return None

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.execute_calls.append((" ".join(sql.lower().split()), params))
        return 1


class BankAutoCategoryContextConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        return [
            {
                "legacy_id": "txn_context_1",
                "account_no": "6222000011116386",
                "txn_direction": TransactionDirection.OUTFLOW.value,
                "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                "amount": "13000.00",
                "signed_amount": "-13000.00",
                "written_off_amount": "0.00",
                "txn_date": "2026-04-03",
                "trade_time": "2026-04-03 10:00:00",
                "legacy_source_batch_id": "batch_import_0008",
                "status": "pending",
                "raw_payload": {"normalized_payload": {"id": "txn_context_1"}},
            }
        ]


def test_core_repository_lists_invoice_and_bank_facts_with_sql_pagination() -> None:
    connection = PagedFactConnection()
    repository = PostgresCoreRepository(connection)

    invoices, invoice_total = repository.list_invoices_page(page=3, page_size=50, month="2026-05")
    transactions, transaction_total = repository.list_bank_transactions_page(page=2, page_size=25, keyword="供应商")

    assert invoice_total == 123
    assert invoices[0].id == "invoice_page_1"
    assert transaction_total == 123
    assert transactions[0].id == "txn_page_1"
    assert all("from app.invoices order by" not in sql for sql, _params in connection.fetch_all_calls)
    assert all("from app.bank_transactions order by" not in sql for sql, _params in connection.fetch_all_calls)


def test_core_repository_lists_bank_auto_category_context_without_account_keyword_or_pagination() -> None:
    connection = BankAutoCategoryContextConnection()
    repository = PostgresCoreRepository(connection)

    transactions = repository.list_bank_transactions_auto_category_context(
        date_from="2026-04-01",
        date_to="2026-04-30",
    )

    assert [transaction.id for transaction in transactions] == ["txn_context_1"]
    sql, params = connection.fetch_all_calls[0]
    assert "from app.bank_transactions" in sql
    assert "limit %s offset %s" not in sql
    assert "counterparty_name_raw ilike" not in sql
    assert "raw_payload->'normalized_payload'->>'imported_bank_name'" not in sql
    assert params == ("2026-04-01", "2026-04-30")


def test_core_repository_restores_imported_bank_identity_from_normalized_payload() -> None:
    repository = PostgresCoreRepository(CoreReadConnection())

    transaction = repository._transaction_from_row(
        {
            "legacy_id": "txn_imported_1537",
            "account_no": "531899991015003383847",
            "txn_direction": TransactionDirection.OUTFLOW.value,
            "counterparty_name_raw": "单位国内汇款手续费收入",
            "amount": "1.00",
            "signed_amount": "-1.00",
            "written_off_amount": "0.00",
            "txn_date": "2026-04-23",
            "status": "pending",
            "raw_payload": {
                "normalized_payload": {
                    "id": "txn_imported_1537",
                    "account_no": "531899991015003383847",
                    "imported_bank_name": "交通银行",
                    "imported_bank_last4": "3847",
                }
            },
        }
    )

    assert transaction.imported_bank_name == "交通银行"
    assert transaction.imported_bank_last4 == "3847"


def test_core_repository_lists_bank_transaction_accounts_with_sql_aggregation() -> None:
    connection = PagedFactConnection()
    repository = PostgresCoreRepository(connection)

    accounts = repository.list_bank_transaction_accounts(date_from="2026-01-01", date_to="2026-12-31")

    assert accounts == [
        {
            "bank_name": "交通银行",
            "account_last4": "3847",
            "transaction_count": 51,
            "latest_balance": Decimal("16091.81"),
            "latest_balance_at": "2026-04-23",
        }
    ]
    sql, params = connection.fetch_all_calls[0]
    assert "filtered_counts" in sql
    assert params == ("2026-01-01", "2026-12-31")


class IdentityConnection:
    def __init__(self) -> None:
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.invoices" in normalized:
            return {
                "legacy_id": "invoice_existing_sql",
                "invoice_type": InvoiceType.OUTPUT.value,
                "invoice_no": "9001",
                "invoice_date": "2026-03-21",
                "counterparty_id": "cp_sql",
                "counterparty_name": "Acme Supplies",
                "amount": "100.00",
                "signed_amount": "100.00",
                "written_off_amount": "0.00",
                "currency": "CNY",
                "source_unique_key": params[0],
                "invoice_status_from_source": "valid",
                "workbench_visibility": "visible",
                "status": InvoiceStatus.PENDING.value,
                "tags": [],
                "source_links": [],
                "raw_payload": {"normalized_payload": {"id": "invoice_existing_sql", "invoice_status_from_source": "valid"}},
            }
        if "from app.bank_transactions" in normalized:
            return {
                "legacy_id": "txn_existing_sql",
                "account_no": "62220000",
                "txn_direction": TransactionDirection.OUTFLOW.value,
                "counterparty_name_raw": "Acme Supplies",
                "amount": "88.00",
                "signed_amount": "-88.00",
                "written_off_amount": "0.00",
                "txn_date": "2026-03-23",
                "source_unique_key": params[0],
                "status": "pending",
                "raw_payload": {"normalized_payload": {"id": "txn_existing_sql"}},
            }
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from app.invoices" in normalized and "source_unique_key = any(%s)" in normalized:
            return [
                {
                    "legacy_id": "invoice_existing_sql",
                    "invoice_type": InvoiceType.OUTPUT.value,
                    "invoice_no": "9001",
                    "invoice_date": "2026-03-21",
                    "counterparty_id": "cp_sql",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "signed_amount": "100.00",
                    "written_off_amount": "0.00",
                    "currency": "CNY",
                    "source_unique_key": params[0][0],
                    "invoice_status_from_source": "valid",
                    "workbench_visibility": "visible",
                    "status": InvoiceStatus.PENDING.value,
                    "tags": [],
                    "source_links": [],
                    "raw_payload": {"normalized_payload": {"id": "invoice_existing_sql", "invoice_status_from_source": "valid"}},
                }
            ]
        raise AssertionError(f"identity lookup must not full-scan facts: {sql}")


class DuplicateInvoiceIdentityConnection:
    def __init__(self) -> None:
        self.fetch_all_sql: list[str] = []
        self.fetch_all_params: list[tuple] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        self.fetch_all_sql.append(" ".join(sql.lower().split()))
        self.fetch_all_params.append(params)
        return [
            {
                "legacy_id": "invoice_duplicate_1",
                "invoice_type": InvoiceType.INPUT.value,
                "invoice_no": "26532000000141671581",
                "digital_invoice_no": "26532000000141671581",
                "invoice_date": "2026-01-27",
                "counterparty_id": "cp_sql",
                "counterparty_name": "云南建筑技术发展中心",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "amount": "400.00",
                "signed_amount": "400.00",
                "written_off_amount": "0.00",
                "total_with_tax": "400.00",
                "currency": "CNY",
                "source_unique_key": "26532000000141671581",
                "workbench_visibility": "visible",
                "status": InvoiceStatus.PENDING.value,
                "tags": [],
                "source_links": [],
                "raw_payload": {"normalized_payload": {"id": "invoice_duplicate_1"}},
            },
            {
                "legacy_id": "invoice_duplicate_2",
                "invoice_type": InvoiceType.INPUT.value,
                "invoice_no": "26532000000141671581",
                "digital_invoice_no": "26532000000141671581",
                "invoice_date": "2026-01-27",
                "counterparty_id": "cp_sql",
                "counterparty_name": "云南建筑技术发展中心",
                "seller_name": "云南建筑技术发展中心",
                "buyer_name": "云南溯源科技有限公司",
                "amount": "400.00",
                "signed_amount": "400.00",
                "written_off_amount": "0.00",
                "total_with_tax": "400.00",
                "currency": "CNY",
                "source_unique_key": "duplicate-source-key",
                "workbench_visibility": "visible",
                "status": InvoiceStatus.PENDING.value,
                "tags": [],
                "source_links": [],
                "raw_payload": {"normalized_payload": {"id": "invoice_duplicate_2"}},
            },
        ]


def test_import_service_uses_sql_identity_repository_without_snapshot_facts() -> None:
    repository = PostgresCoreRepository(IdentityConnection())
    service = ImportNormalizationService(fact_repository=repository)

    preview = service.preview_import(
        batch_type=BatchType.OUTPUT_INVOICE,
        source_name="output.json",
        imported_by="tester",
        rows=[
            {
                "invoice_code": "033001",
                "invoice_no": "9001",
                "counterparty_name": "Acme Supplies",
                "amount": "100.00",
                "invoice_date": "2026-03-21",
                "invoice_status_from_source": "valid",
            }
        ],
    )

    assert preview.row_results[0].decision == ImportDecision.DUPLICATE_SKIPPED
    assert preview.row_results[0].linked_object_id == "invoice_existing_sql"


def test_find_invoices_by_identity_returns_all_digital_invoice_matches() -> None:
    connection = DuplicateInvoiceIdentityConnection()
    repository = PostgresCoreRepository(connection)

    matches = repository.find_invoices_by_identity(canonical_key="26532000000141671581")

    assert [invoice.id for invoice in matches] == ["invoice_duplicate_1", "invoice_duplicate_2"]
    assert connection.fetch_all_params == [("26532000000141671581", "26532000000141671581")]
    assert "source_unique_key = %s or digital_invoice_no = %s" in connection.fetch_all_sql[0]


def test_find_invoices_by_identity_keys_uses_single_bulk_lookup() -> None:
    connection = DuplicateInvoiceIdentityConnection()
    repository = PostgresCoreRepository(connection)

    matches = repository.find_invoices_by_identity_keys(
        canonical_keys=["26532000000141671581", "26532000000141671581", ""],
        suspected_keys=["suspected-key"],
    )

    assert [invoice.id for invoice in matches] == ["invoice_duplicate_1", "invoice_duplicate_2"]
    assert connection.fetch_all_params == [(["26532000000141671581"], ["26532000000141671581"], ["suspected-key"])]
    assert "source_unique_key = any(%s)" in connection.fetch_all_sql[0]
    assert "data_fingerprint = any(%s)" in connection.fetch_all_sql[0]


class SubmittedEtcInvoiceIdentityConnection:
    def __init__(self) -> None:
        self.fetch_one_sql: list[str] = []
        self.fetch_one_params: list[tuple] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_sql.append(" ".join(sql.lower().split()))
        self.fetch_one_params.append(params)
        return {
            "etc_invoice_id": "etc_invoice_0028",
            "invoice_no": "26537912570200055449",
            "invoice_code": None,
            "invoice_date": "2026-02-28",
            "seller_name": "云南国道主干线昆明绕城高速公路建设有限公司",
            "seller_tax_no": "9153000077859986X2",
            "buyer_name": "云南溯源科技有限公司",
            "buyer_tax_no": "915300007194052520",
            "amount": Decimal("18.63"),
            "tax_amount": Decimal("0.56"),
            "total_with_tax": Decimal("19.19"),
            "tax_rate": "3%",
            "batch_id": "etc_batch_hist_20260413_241125",
            "business_batch_id": "etc_business_batch_hist_20260413_241125",
            "status": "submitted",
            "business_batch_status": "manually_marked_submitted",
        }


def test_find_submitted_etc_invoice_by_identity_returns_active_batch_metadata() -> None:
    connection = SubmittedEtcInvoiceIdentityConnection()
    repository = PostgresCoreRepository(connection)

    invoice = repository.find_submitted_etc_invoice_by_identity(
        canonical_key="26537912570200055449",
        digital_invoice_no="26537912570200055449",
    )

    assert invoice is not None
    assert invoice.id == "etc_invoice_0028"
    assert invoice.invoice_number == "26537912570200055449"
    assert invoice.issue_date == "2026-02-28"
    assert invoice.amount_without_tax == Decimal("18.63")
    assert invoice.tax_amount == Decimal("0.56")
    assert invoice.total_amount == Decimal("19.19")
    assert invoice.current_batch_id == "etc_business_batch_hist_20260413_241125"
    assert connection.fetch_one_params == [
        (
            ["26537912570200055449", "26537912570200055449"],
            None,
            None,
            None,
            None,
        )
    ]
    assert "from app.etc_invoices" in connection.fetch_one_sql[0]
    assert "manually_marked_submitted" in connection.fetch_one_sql[0]
    assert "coalesce(etc_business_batches.status, '') <> 'deleted'" in connection.fetch_one_sql[0]


class EtcBatchInvoiceLinkConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        return {
            "id": "link-uuid-1",
            "tenant_id": "default",
            "business_batch_id": "etc_business_batch_hist_20260413_241125",
            "etc_invoice_id": "etc_invoice_0028",
            "invoice_id": "invoice-uuid-1",
            "identity_key": "26537912570200055449",
            "link_status": "active",
            "link_source": "formal_invoice_import",
            "confidence": "strict",
        }


def test_upsert_etc_batch_invoice_link_is_idempotent_by_batch_identity() -> None:
    connection = EtcBatchInvoiceLinkConnection()
    repository = PostgresCoreRepository(connection)

    link = repository.upsert_etc_batch_invoice_link(
        invoice_id="a6181d79-c3eb-4e20-bbd2-719215ed161d",
        business_batch_id="etc_business_batch_hist_20260413_241125",
        etc_invoice_id="etc_invoice_0028",
        invoice_no="26537912570200055449",
        digital_invoice_no="26537912570200055449",
        invoice_date="2026-02-28",
        link_source="formal_invoice_import",
        confidence="strict",
        raw_payload={"reason": "unit"},
    )

    sql, params = connection.fetch_one_calls[0]
    assert link["id"] == "link-uuid-1"
    assert "insert into app.etc_batch_invoice_links" in sql
    assert "on conflict (tenant_id, business_batch_id, identity_key) where link_status = 'active'" in sql
    assert "select id from app.invoices where legacy_mongo_id = %s or id::text = %s" in sql
    assert params[0] == "a6181d79-c3eb-4e20-bbd2-719215ed161d"
    assert params[1] == "a6181d79-c3eb-4e20-bbd2-719215ed161d"
    assert params[2] == "default"
    assert params[3] == "etc_business_batch_hist_20260413_241125"
    assert params[4] == "etc_invoice_0028"
    assert params[5] == "26537912570200055449"
    assert params[10] == "formal_invoice_import"
    assert params[11] == "strict"


class NotificationConnection:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.executed_params: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed_sql.append(" ".join(sql.lower().split()))
        self.executed_params.append(params)
        return 1


def test_save_imports_does_not_emit_import_fact_refresh_from_full_snapshot() -> None:
    connection = NotificationConnection()
    repository = PostgresCoreRepository(connection)
    counterparty = Counterparty(id="cp_1", name="供应商A", normalized_name="供应商A", counterparty_type="vendor")
    invoice = Invoice(
        id="invoice_1",
        invoice_type=InvoiceType.INPUT,
        invoice_no="INV-001",
        counterparty=counterparty,
        amount=Decimal("100.00"),
        signed_amount=Decimal("100.00"),
        invoice_date="2026-05-01",
        source_batch_id="batch_import_0001",
    )
    transaction = BankTransaction(
        id="txn_1",
        account_no="62220000",
        txn_direction=TransactionDirection.OUTFLOW,
        counterparty_name_raw="供应商A",
        amount=Decimal("100.00"),
        signed_amount=Decimal("-100.00"),
        txn_date="2026-06-02",
        source_batch_id="batch_import_0001",
    )

    repository.save_imports({"invoices": [invoice], "transactions": [transaction]})

    joined_sql = "\n".join(connection.executed_sql) + "\n" + repr(connection.executed_params).lower()
    assert "insert into job.read_model_dirty_scopes" not in joined_sql
    assert "insert into job.outbox_events" not in joined_sql
    dirty_params = [
        params
        for sql, params in zip(connection.executed_sql, connection.executed_params, strict=True)
        if "insert into job.read_model_dirty_scopes" in sql
    ]
    outbox_params = [
        params
        for sql, params in zip(connection.executed_sql, connection.executed_params, strict=True)
        if "insert into job.outbox_events" in sql
    ]
    assert dirty_params == []
    assert outbox_params == []
    assert "workbench_relation" not in repr(dirty_params).lower()
    assert "pending_invoice" not in repr(dirty_params).lower()
    assert "2026-05" not in repr(dirty_params)
