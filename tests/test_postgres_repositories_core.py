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
        raise AssertionError(f"identity lookup must not full-scan facts: {sql}")


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


class NotificationConnection:
    def __init__(self) -> None:
        self.executed_sql: list[str] = []
        self.executed_params: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed_sql.append(" ".join(sql.lower().split()))
        self.executed_params.append(params)
        return 1


def test_save_imports_marks_read_models_dirty_and_outbox_event() -> None:
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
        txn_date="2026-05-02",
        source_batch_id="batch_import_0001",
    )

    repository.save_imports({"invoices": [invoice], "transactions": [transaction]})

    joined_sql = "\n".join(connection.executed_sql) + "\n" + repr(connection.executed_params).lower()
    assert "insert into job.read_model_dirty_scopes" in joined_sql
    assert "insert into job.outbox_events" in joined_sql
    assert "workbench_relation" in joined_sql
    assert "workbench" in joined_sql
    assert "bank_detail" in joined_sql
    assert "pending_invoice" in joined_sql
    assert "input_invoice_usage" in joined_sql
    assert "output_invoice_collection" in joined_sql
    assert "oa_pending_payment" in joined_sql
    assert "no_oa_bank_batch" in joined_sql
    assert "cost_statistics" in joined_sql
    assert "cost" in joined_sql
    assert "tax_offset" in joined_sql
    assert "tax" in joined_sql
    assert "search" in joined_sql
