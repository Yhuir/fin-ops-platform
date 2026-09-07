"""Fixed old-code/new-schema write probes; only an explicit synthetic test DB.

The caller applies each candidate schema head first. PYTHONPATH selects the
exact previous release; this file never imports candidate cash application code.
Recovery receipts below are test fixtures, not production backup evidence.
"""

from __future__ import annotations

import os
import unittest
from decimal import Decimal
from uuid import uuid4

from fin_ops_platform.domain.enums import TransactionStatus
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.settings_data_reset import PostgresSettingsDataResetRepository


class CashSchemaCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.connection = PostgresConnection(PostgresSettings(os.environ["FIN_OPS_TEST_DATABASE_URL"], pool_enabled=False))
        self.addCleanup(self.connection.close)
        database = self.connection.fetch_one("SELECT current_database() AS name")["name"]
        if not database.startswith("fin_ops_cash_test_"):
            raise RuntimeError("Compatibility writes require a synthetic fin_ops_cash_test_* database")
        self.core = PostgresCoreRepository(self.connection)
        self.cash_id, account_id, category_id = (str(uuid4()) for _ in range(3))
        with self.connection.transaction() as tx:
            tx.execute("INSERT INTO cash.accounts(id,name,kind,opening_date,opening_amount) VALUES(%s,'Synthetic','cash','2026-01-01',0)", (account_id,))
            tx.execute('INSERT INTO cash.categories(id,name,"group") VALUES(%s,\'Synthetic\',\'receipt\')', (category_id,))
            tx.execute("""INSERT INTO cash.flows(id,occurred_on,kind,amount,to_account_id,category_id,content,source_kind,created_by_account)
                VALUES(%s,'2026-01-15','receipt',987654.32,%s,%s,'Synthetic cash sentinel','manual','test')""",
                (self.cash_id, account_id, category_id))
        self.before = self.connection.fetch_one("SELECT * FROM cash.flows WHERE id=%s", (self.cash_id,))
        self.addCleanup(self.assert_cash_unchanged)

    def assert_cash_unchanged(self):
        self.assertEqual(self.connection.fetch_one("SELECT * FROM cash.flows WHERE id=%s", (self.cash_id,)), self.before)

    def bank(self):
        identity = "bank-cash-compat-" + uuid4().hex
        return {"id": identity, "account_no": "synthetic-account", "txn_direction": "outflow",
                "counterparty_name_raw": "Synthetic vendor", "amount": "100.00", "signed_amount": "-100.00",
                "txn_date": "2026-01-15", "source_unique_key": identity, "data_fingerprint": identity,
                "status": TransactionStatus.PENDING.value, "summary": identity}

    def test_bank_transaction_existing_upsert(self):
        bank = self.bank()
        self.core.save_imports({"transactions": [bank]})
        self.core.save_imports({"transactions": [{**bank, "amount": "120.00", "signed_amount": "-120.00"}]})
        rows, count = self.core.list_bank_transactions_page(keyword=bank["id"])
        self.assertEqual(count, 1)
        self.assertEqual(rows[0].id, bank["id"])
        self.assertEqual(rows[0].amount, Decimal("120.00"))

    def test_correction_audit_same_transaction(self):
        bank = self.bank()
        self.core.save_imports({"transactions": [bank]})
        self.core.save_imports({"transactions": [{**bank, "amount": "140.00", "signed_amount": "-140.00"}]})
        correction = self.connection.fetch_one("""SELECT before_value,after_value,actor_id,reason
            FROM app.financial_fact_corrections WHERE entity_id=%s""", (bank["id"],))
        self.assertEqual(Decimal(str(correction["before_value"]["amount"])), Decimal("100"))
        self.assertEqual(Decimal(str(correction["after_value"]["amount"])), Decimal("140"))
        self.assertEqual(correction["actor_id"], "import-persistence")
        self.assertTrue(correction["reason"])
        before_corrections = self.connection.fetch_one("SELECT count(*) AS n FROM app.financial_fact_corrections")["n"]
        before_audit = self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"]
        with self.assertRaisesRegex(RuntimeError, "synthetic rollback"):
            with self.connection.transaction() as tx:
                PostgresCoreRepository(tx).save_imports({"transactions": [{**bank, "amount": "160.00", "signed_amount": "-160.00"}]})
                self.assertGreater(tx.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], before_audit)
                raise RuntimeError("synthetic rollback")
        self.assertEqual(self.core.get_transaction(bank["id"]).amount, Decimal("140.00"))
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.financial_fact_corrections")["n"], before_corrections)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM audit.events")["n"], before_audit)

    def test_import_enrichment(self):
        bank = self.bank()
        self.core.save_import_delta({"transactions": [bank]}, {})
        self.core.save_import_delta({"transactions": [{**bank, "remark": "Synthetic enrichment", "project_id": "synthetic-project"}]}, {})
        row = self.core.get_transaction(bank["id"])
        self.assertEqual(row.amount, Decimal("100.00"))
        self.assertEqual(row.remark, "Synthetic enrichment")
        self.assertEqual(row.project_id, "synthetic-project")

    def test_invoice_existing_upsert(self):
        invoice_id, invoice_no = "invoice-cash-compat-" + uuid4().hex, str(uuid4().int)[:20]
        invoice = {"id": invoice_id, "invoice_type": "input", "invoice_no": invoice_no,
                   "digital_invoice_no": invoice_no, "source_unique_key": invoice_no,
                   "invoice_date": "2026-01-15", "counterparty": {"id": "synthetic-vendor", "name": "Synthetic vendor"},
                   "amount": "100.00", "signed_amount": "100.00", "tax_amount": "6.00", "total_with_tax": "106.00"}
        self.core.save_imports({"invoices": [invoice]})
        self.core.save_imports({"invoices": [{**invoice, "amount": "200.00", "signed_amount": "200.00", "total_with_tax": "206.00"}]})
        rows, count = self.core.list_invoices_page(keyword=invoice_no)
        self.assertEqual(count, 1)
        self.assertEqual(rows[0].id, invoice_id)
        self.assertEqual(rows[0].amount, Decimal("200.00"))

    def test_settings_data_reset(self):
        bank = self.bank()
        self.core.save_imports({"transactions": [bank]})
        before_invoice_count = self.connection.fetch_one("SELECT count(*) AS n FROM app.invoices")["n"]
        with self.connection.transaction() as tx:
            repository = PostgresSettingsDataResetRepository(tx)
            impact = repository.preview("reset_bank_transactions")["impact_fingerprint"]
            receipt, job = str(uuid4()), "synthetic-reset-" + uuid4().hex
            tx.execute("""INSERT INTO job.settings_data_reset_recovery_receipts
                (receipt_id,action,impact_fingerprint,restore_point_run_id,dump_sha256,dump_size_bytes,
                 created_by,valid_until,consumed_by_job_id,consumed_at)
                VALUES(%s,'reset_bank_transactions',%s,%s,%s,1,'synthetic-test',now()+interval '1 hour',%s,now())""",
                (receipt, impact, job, "a" * 64, job))
            result = repository.reset_bank_transaction_data(expected_impact_fingerprint=impact,
                recovery_receipt_id=receipt, job_id=job, actor_id="synthetic-test", reason="Synthetic compatibility fixture only")
            self.assertGreaterEqual(result["bank_transactions"], 1)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.bank_transactions")["n"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM app.invoices")["n"], before_invoice_count)


if __name__ == "__main__":
    unittest.main()
