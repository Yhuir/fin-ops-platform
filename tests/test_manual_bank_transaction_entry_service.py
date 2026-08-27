from __future__ import annotations

import unittest

from fin_ops_platform.domain.enums import ImportDecision, TransactionDirection
from fin_ops_platform.services.import_file_service import FileImportService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.manual_bank_transaction_entry_service import (
    ManualBankTransactionEntryError,
    ManualBankTransactionEntryService,
    manual_bank_reference_field,
)


def mapping(
    *,
    mapping_id: str = "ccb-8106",
    bank_name: str = "中国建设银行",
    last4: str = "8106",
) -> dict[str, str]:
    return {
        "id": mapping_id,
        "bank_name": bank_name,
        "short_name": bank_name.removeprefix("中国"),
        "last4": last4,
    }


def payload(**overrides: str) -> dict[str, str]:
    values = {
        "bank_mapping_id": "ccb-8106",
        "account_no": "6227000012348106",
        "account_name": "云南溯源科技有限公司",
        "direction": "outflow",
        "amount": "100.00",
        "balance": "900.00",
        "trade_time": "2026-08-28T09:01:02",
        "currency": "CNY",
        "counterparty_name": "测试供应商",
        "counterparty_account_no": "621234567890",
        "counterparty_bank_name": "测试银行",
        "summary": "电子转账",
        "remark": "人工录入",
        "account_detail_no": "CCB-001",
    }
    values.update(overrides)
    return values


class ManualBankTransactionEntryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.file_import_service = FileImportService(self.import_service)
        self.mappings = [mapping()]
        self.service = ManualBankTransactionEntryService(
            file_import_service=self.file_import_service,
            bank_account_mappings_provider=lambda: self.mappings,
        )

    def test_preview_and_confirm_use_the_canonical_bank_import_contract(self) -> None:
        preview = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")

        self.assertEqual(preview.session.file_count, 1)
        self.assertEqual(preview.session.files[0].template_code, "manual_bank_transaction_entry")
        self.assertEqual(preview.file_ids, [preview.session.files[0].id])
        normalized = preview.session.files[0].normalized_rows[0]
        self.assertEqual(normalized["txn_direction"], "outflow")
        self.assertEqual(normalized["amount"], "100.00")
        self.assertEqual(normalized["balance"], "900.00")
        self.assertEqual(normalized["account_detail_no"], "CCB-001")
        self.assertTrue(normalized["source_unique_key"].startswith("bank-v3:"))

        self.file_import_service.confirm_session(
            session_id=preview.session.id,
            selected_file_ids=preview.file_ids,
        )
        transaction = self.import_service.list_transactions()[0]
        self.assertEqual(transaction.txn_direction, TransactionDirection.OUTFLOW)
        self.assertEqual(str(transaction.amount), "100.00")
        self.assertEqual(transaction.account_detail_no, "CCB-001")
        self.assertEqual(transaction.imported_bank_last4, "8106")

    def test_multiple_entries_remain_independently_confirmable(self) -> None:
        preview = self.service.preview_batch(
            payloads=[
                payload(),
                payload(
                    account_detail_no="CCB-002",
                    trade_time="2026-08-28T09:02:03",
                    direction="inflow",
                    amount="20.00",
                    balance="920.00",
                ),
            ],
            imported_by="finance-user",
        )

        self.assertEqual(preview.session.file_count, 2)
        self.assertEqual([item.file_name for item in preview.session.files], ["新流水1", "新流水2"])
        self.assertEqual(len(preview.file_ids), 2)

    def test_multiple_entries_bulk_load_existing_identities_once(self) -> None:
        class CountingFactRepository:
            def __init__(self) -> None:
                self.identity_queries = 0

            def find_bank_transactions_by_identity_keys(
                self,
                *,
                canonical_keys: list[str],
                suspected_keys: list[str],
            ) -> list[object]:
                self.identity_queries += 1
                return []

        repository = CountingFactRepository()
        import_service = ImportNormalizationService(fact_repository=repository)
        service = ManualBankTransactionEntryService(
            file_import_service=FileImportService(import_service),
            bank_account_mappings_provider=lambda: self.mappings,
        )

        service.preview_batch(
            payloads=[
                payload(),
                payload(account_detail_no="CCB-002", trade_time="2026-08-28T09:02:03"),
            ],
            imported_by="finance-user",
        )

        self.assertEqual(repository.identity_queries, 1)

    def test_existing_canonical_duplicate_is_visible_but_not_confirmable(self) -> None:
        first = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")
        self.file_import_service.confirm_session(
            session_id=first.session.id,
            selected_file_ids=first.file_ids,
        )

        duplicate = self.service.preview_batch(payloads=[payload()], imported_by="finance-user")

        self.assertEqual(duplicate.file_ids, [])
        self.assertEqual(
            duplicate.session.files[0].row_results[0].decision,
            ImportDecision.DUPLICATE_SKIPPED,
        )
        self.assertEqual(len(self.import_service.list_transactions()), 1)

    def test_duplicate_inside_one_batch_is_rejected_before_session_creation(self) -> None:
        with self.assertRaisesRegex(ManualBankTransactionEntryError, "本次录入中存在重复流水"):
            self.service.preview_batch(payloads=[payload(), payload()], imported_by="finance-user")

        self.assertEqual(
            self.file_import_service.list_active_sessions(
                imported_by="finance-user",
                mode="bank_transaction",
            ),
            [],
        )

    def test_mapping_account_time_and_reference_contracts_fail_fast(self) -> None:
        cases = (
            ({"bank_mapping_id": "missing"}, "不存在或已被删除"),
            ({"account_no": "6227000012340000"}, "尾号与所选账户"),
            ({"trade_time": "2026-08-28T09:01"}, "精确到秒"),
            ({"account_detail_no": ""}, "账户明细编号-交易流水号"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(ManualBankTransactionEntryError, message):
                    self.service.preview_batch(
                        payloads=[payload(**overrides)],
                        imported_by="finance-user",
                    )

    def test_reference_field_is_derived_from_the_selected_bank(self) -> None:
        self.assertEqual(
            manual_bank_reference_field("中国建设银行"),
            {"key": "account_detail_no", "label": "账户明细编号-交易流水号"},
        )
        self.assertEqual(
            manual_bank_reference_field("中国光大银行"),
            {"key": "enterprise_serial_no", "label": "企业流水号"},
        )
        self.assertEqual(
            manual_bank_reference_field("云南本地银行"),
            None,
        )

    def test_unknown_bank_does_not_fall_back_to_a_guessed_reference_field(self) -> None:
        self.mappings = [mapping(bank_name="云南本地银行")]

        with self.assertRaisesRegex(ManualBankTransactionEntryError, "尚未配置手工流水录入字段"):
            self.service.preview_batch(
                payloads=[payload(bank_serial_no="LOCAL-001")],
                imported_by="finance-user",
            )


if __name__ == "__main__":
    unittest.main()
