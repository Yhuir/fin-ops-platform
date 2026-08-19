from __future__ import annotations

import unittest
from typing import Any

from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    audit_workbench_relation_display,
)
from fin_ops_platform.services.workbench_pair_relation_service import (
    WorkbenchPairRelationService,
)
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class WorkbenchPendingOaRelationLockPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def _insert_pending_oa(
        self,
        row_id: str,
        *,
        tenant_id: str,
        scope_key: str = "2026-08",
    ) -> None:
        self.connection.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, applicant,
                project_name, amount, source_signature, source_payload, raw_payload
            ) values (%s, %s, %s, 'in_progress', '测试申请人',
                      '待付款项目', 100, %s, '{}'::jsonb, '{}'::jsonb)
            """,
            (tenant_id, scope_key, row_id, f"signature:{tenant_id}:{scope_key}:{row_id}"),
        )

    def _insert_completed_oa(self, row_id: str) -> None:
        self.connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                %s, %s, '付款申请', %s, 'active', 'completed', '测试申请人',
                '2026-08-10', '2026-08-01', '已完成项目', 100, 'CNY',
                '{}'::jsonb, '{}'::jsonb
            )
            """,
            (f"source:{row_id}", f"form:{row_id}", row_id),
        )

    def _insert_bank(self, row_id: str) -> None:
        self.connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date,
                txn_month, trade_time, summary, raw_payload, status
            ) values (
                %s, '6222000011119999', '基本户', 'outflow', '测试供应商',
                100, -100, '2026-08-11', '2026-08-01',
                '2026-08-11 09:00:00+08', '支付测试供应商', '{}'::jsonb, 'active'
            )
            """,
            (row_id,),
        )

    def _insert_etc_summary(self, external_batch_id: str) -> str:
        business_batch_id = f"business:{external_batch_id}"
        self.connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                %s, 'manually_marked_submitted', '2026-08-01', 1,
                100, jsonb_build_object(
                    'normalized_payload',
                    jsonb_build_object(
                        'external_etc_batch_id', %s::text,
                        'invoice_ids', jsonb_build_array(%s::text)
                    )
                )
            )
            """,
            (business_batch_id, external_batch_id, f"invoice:{external_batch_id}"),
        )
        self.connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values (
                %s, %s, 'submitted', %s,
                '2026-08-09', 'ETC测试供应商', 90, 10, 100,
                '{}'::jsonb
            )
            """,
            (f"invoice:{external_batch_id}", business_batch_id, f"NO:{external_batch_id}"),
        )
        return f"etc-summary-{external_batch_id}"

    @staticmethod
    def _command(transaction: Any) -> WorkbenchRelationCommandService:
        return WorkbenchRelationCommandService(
            relation_repository=WorkbenchRelationCommandRepositoryAdapter(
                pair_relation_service=WorkbenchPairRelationService(),
                repository=PostgresWorkbenchRelationRepository(transaction),
            ),
        )

    def _confirm(self, *, case_id: str, oa_row_id: str, bank_row_id: str, tenant_id: str) -> dict[str, Any]:
        with self.connection.transaction() as transaction:
            return self._command(transaction).confirm_relation(
                case_id=case_id,
                row_ids=[oa_row_id, bank_row_id],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                actor_id="integration-test",
                month_scope="2026-08",
                amount_check={"status": "matched"},
                tenant_id=tenant_id,
            )

    def test_pending_oa_and_bank_confirm_as_one_formal_relation(self) -> None:
        self._insert_pending_oa("oa-pending-lock-1", tenant_id="tenant-a")
        self._insert_bank("bank-pending-lock-1")

        result = self._confirm(
            case_id="CASE-PENDING-OA-LOCK-1",
            oa_row_id="oa-pending-lock-1",
            bank_row_id="bank-pending-lock-1",
            tenant_id="tenant-a",
        )

        self.assertEqual(result["status"], "confirmed")
        persisted = self.connection.fetch_one(
            """
            select case_id, row_ids, row_types, status
            from app.workbench_pair_relations
            where case_id = 'CASE-PENDING-OA-LOCK-1'
            """
        )
        self.assertEqual(
            persisted,
            {
                "case_id": "CASE-PENDING-OA-LOCK-1",
                "row_ids": ["oa-pending-lock-1", "bank-pending-lock-1"],
                "row_types": ["oa", "bank"],
                "status": "active",
            },
        )

    def test_submitted_etc_summary_is_lockable_as_canonical_invoice_member(self) -> None:
        self._insert_completed_oa("oa-etc-summary-lock")
        self._insert_bank("bank-etc-summary-lock")
        summary_row_id = self._insert_etc_summary("etc_202608_lock")

        with self.connection.transaction() as transaction:
            result = self._command(transaction).confirm_relation(
                case_id="CASE-ETC-SUMMARY-LOCK",
                row_ids=["oa-etc-summary-lock", "bank-etc-summary-lock", summary_row_id],
                row_types=["oa", "bank", "invoice"],
                relation_mode="manual_confirmed",
                actor_id="integration-test",
                month_scope="2026-08",
                amount_check={"status": "matched"},
                tenant_id="tenant-a",
            )

        self.assertEqual(result["status"], "confirmed")
        persisted = self.connection.fetch_one(
            """
            select row_ids, row_types
            from app.workbench_pair_relations
            where case_id = 'CASE-ETC-SUMMARY-LOCK'
            """
        )
        self.assertEqual(
            persisted,
            {
                "row_ids": [
                    "oa-etc-summary-lock",
                    "bank-etc-summary-lock",
                    summary_row_id,
                ],
                "row_types": ["oa", "bank", "invoice"],
            },
        )

    def test_historical_relation_case_proves_oa_then_member_repair_closes_audit(self) -> None:
        external_batch_id = "ETC-OA-HISTORICAL-AUDIT"
        case_id = "CASE-ETC-HISTORICAL-AUDIT"
        self._insert_completed_oa("oa-etc-historical-audit")
        self._insert_bank("bank-etc-historical-audit")
        summary_row_id = self._insert_etc_summary(external_batch_id)
        self.connection.execute(
            """
            update app.etc_business_batches
            set raw_payload = jsonb_set(
                raw_payload,
                '{normalized_payload,amount_breakdown}',
                jsonb_build_object('relation_case_id', %s::text),
                true
            )
            where business_batch_id = %s
            """,
            (case_id, f"business:{external_batch_id}"),
        )
        with self.connection.transaction() as transaction:
            command = self._command(transaction)
            relation = command.confirm_relation(
                case_id=case_id,
                row_ids=["oa-etc-historical-audit", "bank-etc-historical-audit"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                actor_id="integration-test",
                month_scope="2026-08",
                amount_check={"status": "matched"},
                special_metadata={"external_etc_batch_id": external_batch_id},
                tenant_id="tenant-a",
            )["relation"]

        before = audit_workbench_relation_display(self.connection)
        self.assertEqual(
            [issue["code"] for issue in before["issues"]],
            ["submitted_etc_batch_relation_member_missing"],
        )

        with self.connection.transaction() as transaction:
            self._command(transaction).confirm_relation(
                case_id=case_id,
                row_ids=[*relation["row_ids"], summary_row_id],
                row_types=[*relation["row_types"], "invoice"],
                relation_mode=str(relation["relation_mode"]),
                actor_id="integration-test",
                month_scope="2026-08",
                amount_check=dict(relation["amount_check"]),
                special_metadata=dict(relation["special_metadata"]),
                before_relations=[relation],
                replace_existing=True,
                tenant_id="tenant-a",
            )

        after = audit_workbench_relation_display(self.connection)
        self.assertEqual(after["issues"], [])

    def test_pending_oa_from_another_tenant_is_not_lockable(self) -> None:
        self._insert_pending_oa("oa-pending-tenant-a", tenant_id="tenant-a")
        self._insert_bank("bank-pending-tenant-a")

        with self.assertRaises(WorkbenchRelationCommandError) as raised:
            self._confirm(
                case_id="CASE-PENDING-CROSS-TENANT",
                oa_row_id="oa-pending-tenant-a",
                bank_row_id="bank-pending-tenant-a",
                tenant_id="tenant-b",
            )

        self.assertEqual(
            raised.exception.error_code,
            "workbench_relation_canonical_member_missing",
        )
        self.assertEqual(
            raised.exception.payload["missing_member_keys"],
            ["oa:oa-pending-tenant-a"],
        )
        self.assertIsNone(
            self.connection.fetch_one(
                "select case_id from app.workbench_pair_relations where case_id = 'CASE-PENDING-CROSS-TENANT'"
            )
        )

    def test_completed_and_pending_sources_with_same_oa_id_fail_closed(self) -> None:
        self._insert_completed_oa("oa-dual-source-lock")
        self._insert_pending_oa("oa-dual-source-lock", tenant_id="tenant-a")
        self._insert_bank("bank-dual-source-lock")

        with self.assertRaises(WorkbenchRelationCommandError) as raised:
            self._confirm(
                case_id="CASE-PENDING-DUAL-SOURCE",
                oa_row_id="oa-dual-source-lock",
                bank_row_id="bank-dual-source-lock",
                tenant_id="tenant-a",
            )

        self.assertEqual(
            raised.exception.error_code,
            "workbench_relation_canonical_member_missing",
        )
        self.assertEqual(
            raised.exception.payload["missing_member_keys"],
            ["oa:oa-dual-source-lock"],
        )
        self.assertIsNone(
            self.connection.fetch_one(
                "select case_id from app.workbench_pair_relations where case_id = 'CASE-PENDING-DUAL-SOURCE'"
            )
        )
