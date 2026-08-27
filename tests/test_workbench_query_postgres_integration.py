from __future__ import annotations

import json
import os
import time
import unittest
from types import SimpleNamespace
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.operations_audit import (
    PostgresOperationsAuditRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench import (
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import (
    PostgresWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    PostgresWorkbenchPageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
    PostgresWorkbenchPageSelectionRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_relation import (
    PostgresWorkbenchRelationRepository,
)
from fin_ops_platform.services.workbench_canonical_rows import (
    WorkbenchCanonicalRowsBuilder,
)
from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
)
from fin_ops_platform.services.workbench_invoice_expense_item_assignment_service import (
    WorkbenchInvoiceExpenseItemAssignmentService,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork

from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class _InstrumentedConnection:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self.statements: list[dict[str, object]] = []

    def _measure(
        self,
        operation: str,
        sql: str,
        params: tuple[Any, ...],
        callback: Any,
    ) -> Any:
        started = time.perf_counter()
        result: Any = None
        try:
            result = callback()
            return result
        finally:
            statement: dict[str, object] = {
                "operation": operation,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "sql": " ".join(sql.split())[:240],
                "raw_sql": sql,
                "params": params,
            }
            if isinstance(result, list):
                statement["metadata_row_count"] = sum(
                    1
                    for row in result
                    if isinstance(row, dict) and row.get("record_zone") == "metadata"
                )
                statement["page_rows_with_anomaly_payload"] = sum(
                    1
                    for row in result
                    if isinstance(row, dict)
                    and row.get("record_zone") in {"paired", "unpaired"}
                    and (
                        row.get("anomaly_members") not in (None, [])
                        or row.get("ignored_anomaly_fingerprints") not in (None, [])
                    )
                )
            self.statements.append(statement)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "fetch_all",
            sql,
            params,
            lambda: self._connection.fetch_all(sql, params),
        )

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "fetch_one",
            sql,
            params,
            lambda: self._connection.fetch_one(sql, params),
        )

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> Any:
        return self._measure(
            "execute",
            sql,
            params,
            lambda: self._connection.execute(sql, params),
        )

    def transaction(self) -> Any:
        connection = self
        outer_connection = self._connection
        delegate = outer_connection.transaction()

        class _Transaction:
            def __enter__(self) -> _InstrumentedConnection:
                transaction = delegate.__enter__()
                connection._connection = transaction
                return connection

            def __exit__(self, *args: object) -> object:
                try:
                    return delegate.__exit__(*args)
                finally:
                    connection._connection = outer_connection

        return _Transaction()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)


class WorkbenchQueryPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.raw_connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.connection = _InstrumentedConnection(self.raw_connection)
        self.repository = PostgresWorkbenchPageQueryRepository(
            self.connection, tenant_id="default"
        )
        self.selection_repository = PostgresWorkbenchPageSelectionRepository(
            self.connection, tenant_id="default"
        )
        self._insert_canonical_fixtures()

    def tearDown(self) -> None:
        self.raw_connection.close()
        truncate_test_database(self.database_url)

    def _insert_canonical_fixtures(self) -> None:
        settings_payload = {
            "allowed_usernames": ["YNSYLP005"],
            "readonly_export_usernames": [],
            "admin_usernames": ["YNSYLP005"],
            "full_access_usernames": [],
            "access_control_version": 1,
            "bank_transaction_tags": {
                "version": 2,
                "definitions": [
                    {
                        "code": "materials",
                        "label": "材料采购",
                        "path": ["货款", "材料采购"],
                        "output_primary_label": "货款",
                        "output_sub_label": "材料采购",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 1,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "contains_any": ["材料款"],
                        },
                    }
                ],
            },
        }
        self.raw_connection.execute(
            """
            insert into app.app_settings(settings_key, settings_payload, raw_payload)
            values ('app_settings', %s::jsonb, %s::jsonb)
            on conflict (settings_key) do nothing
            """,
            (
                json.dumps(settings_payload, ensure_ascii=False),
                json.dumps(
                    {"normalized_payload": settings_payload},
                    ensure_ascii=False,
                ),
            ),
        )
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values
                (
                    'etc_202607_unlinked', 'oa_submitted', '2026-07-01', 2,
                    99, '{"normalized_payload":{"external_etc_batch_id":"etc_202607_unlinked"}}'::jsonb
                ),
                (
                    'etc_202607_linked', 'oa_submitted', '2026-07-01', 1,
                    44, '{"normalized_payload":{"external_etc_batch_id":"etc_202607_linked"}}'::jsonb
                ),
                (
                    'etc_202607_special', 'oa_submitted', '2026-07-01', 1,
                    33, '{"normalized_payload":{"external_etc_batch_id":"ETC 空格/中文"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values
                (
                    'etc-invoice-direct-1', 'etc_202607_unlinked', 'submitted',
                    'ETC-INV-DIRECT', '2026-07-24', 'ETC供应商', 80, 8, 88,
                    '{}'::jsonb
                ),
                (
                    'etc-invoice-direct-2', 'etc_202607_linked', 'submitted',
                    'ETC-INV-LINKED', '2026-07-24', 'ETC供应商', 40, 4, 44,
                    '{}'::jsonb
                ),
                (
                    'etc-invoice-direct-3', 'etc_202607_special', 'submitted',
                    'ETC-INV-SPECIAL', '2026-07-25', 'ETC特殊供应商', 30, 3, 33,
                    '{}'::jsonb
                ),
                (
                    'etc-invoice-direct-4', 'etc_202607_unlinked', 'submitted',
                    'ETC-INV-DIRECT-SECOND', '2026-07-24', 'ETC供应商', 10, 1, 11,
                    '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-direct', 'payment_request', '付款申请', 'oa-direct-1',
                'active', 'completed', '张三', '2026-07-21', '2026-07-01',
                '直接查询项目', 100, 'CNY',
                '{"id":"oa-direct-1","month":"2026-07","section":"unpaired","applicant":"张三","project_name":"直接查询项目","expense_type":"交通费","amount":"100","workflow_status":"completed","expense_items":[{"id":"oa-direct-1:item:0","amount":"100","attachment_file_count":"0"}]}'::jsonb,
                '{}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values
                ('bank-direct-1', '6222000011118106', '基本户', 'outflow',
                 '云南腾安科技有限公司', 100, -100, '2026-07-22', '2026-07-01',
                 '2026-07-22 10:00:00+08', '材料款', '{}'::jsonb, 'active'),
                ('same-text-id', '6222000011118107', '基本户', 'outflow',
                 '银行同名', 10, -10, '2026-07-23', '2026-07-01',
                 '2026-07-23 10:00:00+08', '同名', '{}'::jsonb, 'active')
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                etc_invoice_id, source_links, raw_payload
            ) values
                (
                    'same-text-id', 'input', 'INV-SAME', '2026-07-23', '2026-07-01',
                    10, 10, 10, 'active', 'visible', null,
                    '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'canonical-etc-direct-1', 'input', 'ETC-INV-DIRECT',
                    '2026-07-24', '2026-07-01', 88, 88, 88, 'active',
                    'hidden_after_etc_submission', 'etc-invoice-direct-1',
                    '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'canonical-etc-direct-2', 'input', 'ETC-INV-LINKED',
                    '2026-07-24', '2026-07-01', 44, 44, 44, 'active',
                    'hidden_after_etc_submission', 'etc-invoice-direct-2',
                    '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'canonical-etc-direct-3', 'input', 'ETC-INV-SPECIAL',
                    '2026-07-25', '2026-07-01', 33, 33, 33, 'active',
                    'hidden_after_etc_submission', 'etc-invoice-direct-3',
                    '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'canonical-etc-direct-4', 'input', 'ETC-INV-DIRECT-SECOND',
                    '2026-07-24', '2026-07-01', 11, 11, 11, 'active',
                    'hidden_after_etc_submission', 'etc-invoice-direct-4',
                    '[]'::jsonb, '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-DIRECT-1', 'manual_confirmed', 'active', 1, '2026-07-01',
                array['oa-direct-1','bank-direct-1','etc-summary-etc_202607_linked'],
                array['oa','bank','invoice'],
                '{}'::jsonb,
                '{"requires_invoice":false,"external_etc_batch_id":"etc_202607_linked"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

    def test_direct_initial_and_groups_use_canonical_facts_without_read_model(self) -> None:
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")

        self.assertEqual(initial["summary"]["oa_count"], 1)
        self.assertEqual(initial["summary"]["bank_count"], 2)
        self.assertEqual(initial["summary"]["invoice_count"], 5)
        self.assertEqual(initial["summary"]["paired_count"], 0)
        self.assertEqual(initial["summary"]["unpaired_count"], 5)
        self.assertEqual(initial["paired"]["total"], 0)
        self.assertEqual(initial["unpaired"]["total"], 5)
        self.assertEqual(initial["paired"]["row_counts"]["canonical_invoice"], 0)
        self.assertEqual(initial["unpaired"]["row_counts"]["invoice"], 4)
        self.assertEqual(initial["unpaired"]["row_counts"]["canonical_invoice"], 5)
        self.assertEqual(
            initial["paired"]["row_counts"]["canonical_invoice"]
            + initial["unpaired"]["row_counts"]["canonical_invoice"],
            initial["statistics"]["invoice_total_count"],
        )
        initial_oa_rows = [
            row
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            for row in list(group.get("oa_rows") or [])
        ]
        self.assertEqual(initial_oa_rows[0]["expense_type"], "交通费")
        initial_bank_rows = [
            row
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            for row in list(group.get("bank_rows") or [])
        ]
        bank_direct = next(
            row for row in initial_bank_rows if row.get("id") == "bank-direct-1"
        )
        self.assertEqual(bank_direct["category_code"], "materials")
        self.assertEqual(bank_direct["category_label"], "材料采购")
        self.assertEqual(bank_direct["category_label_path"], ["货款", "材料采购"])
        self.assertEqual(bank_direct["category_resolution_status"], "auto_matched")
        same_text_bank = next(
            row for row in initial_bank_rows if row.get("id") == "same-text-id"
        )
        self.assertEqual(same_text_bank["category_resolution_status"], "unmatched")
        etc_groups = [
            group
            for group in initial["unpaired"]["groups"]
            if list(group.get("invoice_rows") or [])
            and group["invoice_rows"][0].get("etc_batch_id")
            == "etc_202607_unlinked"
        ]
        self.assertEqual(len(etc_groups), 1)
        self.assertEqual(
            etc_groups[0]["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        special_group = next(
            group
            for group in initial["unpaired"]["groups"]
            if list(group.get("invoice_rows") or [])
            and group["invoice_rows"][0].get("etc_batch_id") == "ETC 空格/中文"
        )
        self.assertEqual(
            special_group["invoice_rows"][0]["id"],
            "etc-summary-ETC-"
        )
        self.assertEqual(
            next(
                group
                for group in initial["unpaired"]["groups"]
                if group.get("detail_key") == "CASE-DIRECT-1"
            )["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        initial_statement = next(
            statement
            for statement in self.connection.statements
            if "with recursive requested_scope" in str(statement.get("sql") or "")
        )
        self.assertEqual(initial_statement["operation"], "fetch_all")
        self.assertEqual(initial_statement["metadata_row_count"], 1)
        self.assertEqual(initial_statement["page_rows_with_anomaly_payload"], 0)
        self.assertNotIn("read_model_version", initial)
        self.assertNotIn("generation_id", initial)
        self.assertFalse(
            any("read_model.workbench_" in str(statement["sql"]) for statement in self.connection.statements)
        )
        classification_statements = [
            statement
            for statement in self.connection.statements
            if "classified_with_semantics" in str(statement.get("raw_sql") or "")
        ]
        self.assertEqual(len(classification_statements), 1)
        self.assertEqual(
            classification_statements[0]["params"][-1],
            ["bank-direct-1", "same-text-id"],
        )

        detail = self.repository.get_workbench_row_detail(
            scope_key="2026-07",
            row_id="bank-direct-1",
            row_type="bank",
        )
        self.assertEqual(detail["row"]["category_code"], "materials")
        self.assertEqual(detail["row"]["category_label"], "材料采购")
        self.assertEqual(detail["row"]["category_resolution_status"], "auto_matched")

        self.connection.statements.clear()
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="云南腾安%",
        )
        self.assertEqual(page["total"], 0, "percent must be treated as a literal")
        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="云南腾安科技有限公司",
        )
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["groups"][0]["detail_key"], "CASE-DIRECT-1")

        unpaired_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=100,
        )
        self.assertEqual(unpaired_page["row_counts"]["invoice"], 4)
        self.assertEqual(unpaired_page["row_counts"]["canonical_invoice"], 5)

    def test_unpaired_submitted_etc_summary_detail_hydrates_all_invoices(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc_detail_49', 'oa_submitted', '2026-07-01', 49, 49,
                '{"normalized_payload":{"external_etc_batch_id":"etc_detail_49"}}'::jsonb
            );
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            )
            select
                'etc-detail-' || item::text,
                'etc_detail_49',
                'submitted',
                'ETC-DETAIL-' || lpad(item::text, 2, '0'),
                '2026-07-20'::date,
                'ETC详情供应商',
                1,
                0,
                1,
                '{}'::jsonb
            from generate_series(1, 49) item
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=100,
        )
        group = next(
            item
            for item in page["groups"]
            if list(item.get("invoice_rows") or [])
            and item["invoice_rows"][0].get("etc_batch_id") == "etc_detail_49"
        )
        self.assertEqual(group["collapsed_row_counts"], {"invoice": 49})
        self.assertNotIn("collapsed_rows", group)
        self.assertEqual(len(group["invoice_rows"]), 1)
        self.assertEqual(
            group["invoice_rows"][0]["source_kind"],
            "etc_invoice_summary",
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="all",
            zone="unpaired",
            group_id=str(group["group_id"]),
            detail_key=str(group["detail_key"]),
        )

        self.assertIsNotNone(detail)
        assert detail is not None
        detailed_group = detail["group"]
        self.assertEqual(detailed_group["collapsed_row_counts"], {"invoice": 49})
        invoice_rows = detailed_group["collapsed_rows"]["invoice"]
        self.assertEqual(len(invoice_rows), 49)
        self.assertEqual(
            {row["source_kind"] for row in invoice_rows},
            {"etc_invoice"},
        )
        self.assertEqual(
            len({row["invoice_no"] for row in invoice_rows}),
            49,
        )
        self.assertNotIn(
            "etc_invoice_summary",
            {row["source_kind"] for row in invoice_rows},
        )

    def test_unified_search_covers_visible_oa_bank_and_invoice_columns(self) -> None:
        self.raw_connection.execute(
            """
            update app.oa_applications
            set normalized_payload = normalized_payload || %s::jsonb
            where row_id = 'oa-direct-1'
            """,
            (
                json.dumps(
                    {
                        "project_name_display": "统一搜索展示项目",
                        "apply_type": "支付申请",
                        "expense_type": "交通费",
                        "counterparty_name": "张丽芬",
                        "reason": "统一搜索申请事由",
                        "apply_time": "2026-07-21 09:08:07",
                        "expense_items": [
                            {
                                "id": "oa-direct-1:item:0",
                                "project_name": "子付款项项目",
                                "expense_type": "住宿费",
                                "amount": "100.00",
                                "fee_content": "酒店住宿",
                                "fee_description": "子付款项搜索说明",
                                "attachment_file_count": "0",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        self.raw_connection.execute(
            """
            with next_settings as (
                select jsonb_set(
                    settings_payload,
                    '{bank_account_mappings}',
                    '[{"last4":"8106","bank_name":"中国建设银行"}]'::jsonb,
                    true
                ) as payload
                from app.app_settings
                where settings_key = 'app_settings'
            )
            update app.app_settings settings
            set settings_payload = next_settings.payload,
                raw_payload = jsonb_build_object(
                    'normalized_payload', next_settings.payload
                )
            from next_settings
            where settings.settings_key = 'app_settings'
            """
        )
        self.raw_connection.execute(
            """
            update app.bank_transactions
            set remark = '统一搜索流水备注'
            where legacy_mongo_id = 'bank-direct-1'
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date, invoice_month, seller_name, seller_tax_no,
                buyer_name, buyer_tax_no, amount, signed_amount, tax_rate,
                tax_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values (
                'invoice-unified-search', 'input', 'INV-UNIFIED-SEARCH',
                'DIGITAL-UNIFIED-SEARCH', '2026-07-25', '2026-07-01',
                '统一搜索销方', 'SELLER-TAX-SEARCH', '统一搜索购方',
                'BUYER-TAX-SEARCH', 91, 91, '9%%', 9, 100,
                'active', 'visible',
                '[{"source_type":"manual_invoice_import"}]'::jsonb,
                '{}'::jsonb
            )
            """
        )

        def assert_search_contains(
            search: str,
            *,
            row_type: str,
            row_id: str,
        ) -> None:
            statement_offset = len(self.connection.statements)
            page = self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
                search=search,
                page_size=100,
            )
            business_statements = [
                statement
                for statement in self.connection.statements[statement_offset:]
                if not str(statement.get("raw_sql") or "")
                .strip()
                .lower()
                .startswith("set ")
            ]
            self.assertLessEqual(len(business_statements), 7)
            self.assertTrue(
                any(
                    row.get("id") == row_id
                    for group in page["groups"]
                    for row in list(group.get(f"{row_type}_rows") or [])
                ),
                f"expected {row_type}:{row_id} for search {search!r}",
            )

        for search in (
            "张丽芬",
            "统一搜索展示项目",
            "支付申请",
            "交通费",
            "统一搜索申请事由",
            "09:08:07",
            "子付款项项目",
            "住宿费",
            "酒店住宿",
            "子付款项搜索说明",
            "已完成",
        ):
            with self.subTest(search=search):
                assert_search_contains(search, row_type="oa", row_id="oa-direct-1")

        for search in (
            "云南腾安科技有限公司",
            "材料款",
            "统一搜索流水备注",
            "支出",
            "建行 基本户 8106",
            "2026-07-22 10:00",
        ):
            with self.subTest(search=search):
                assert_search_contains(search, row_type="bank", row_id="bank-direct-1")

        for search in (
            "INV-UNIFIED-SEARCH",
            "DIGITAL-UNIFIED-SEARCH",
            "统一搜索销方",
            "SELLER-TAX-SEARCH",
            "统一搜索购方",
            "BUYER-TAX-SEARCH",
            "9%",
            "91.00",
            "9.00",
            "100.00",
            "2026-07-25",
            "人工导入",
            "进",
        ):
            with self.subTest(search=search):
                assert_search_contains(
                    search,
                    row_type="invoice",
                    row_id="invoice-unified-search",
                )

        self.raw_connection.execute(
            """
            update app.invoices
            set source_links = '[
                {"source_type":"manual_invoice_import"},
                {"source_type":"oa_attachment_invoice"},
                {"source_type":"oa_expense_item_invoice"}
            ]'::jsonb
            where legacy_mongo_id = 'invoice-unified-search'
            """
        )
        for search in ("OA附件", "明细归属"):
            with self.subTest(search=search):
                assert_search_contains(
                    search,
                    row_type="invoice",
                    row_id="invoice-unified-search",
                )

    def test_pending_oa_uses_nested_application_date_for_display_and_search(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.oa_pending_payment_admissions(
                tenant_id, scope_key, oa_id, workflow_status, applicant,
                project_name, project_name_display, amount, source_signature,
                source_payload, raw_payload
            ) values (
                'default', '2026-07', 'oa-pending-with-time', 'in_progress', '胡琦',
                '大理卷烟厂余热综合利用项目', '大理卷烟厂余热综合利用项目', 175,
                'signature:oa-pending-with-time',
                '{
                    "detail_fields":{"申请日期":"2026-07-17 09:08:07"},
                    "apply_type":"日常报销",
                    "expense_type":"交通费",
                    "counterparty_name":"进行中搜索对方",
                    "reason":"进行中搜索事由",
                    "expense_items":[{
                        "id":"oa-pending-with-time:item:0",
                        "project_name":"进行中子付款项",
                        "expense_type":"差旅费",
                        "amount":"175.00",
                        "fee_content":"进行中费用内容",
                        "fee_description":"进行中费用说明"
                    }]
                }'::jsonb,
                '{}'::jsonb
            )
            """
        )

        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        pending_row = next(
            row
            for group in initial["unpaired"]["groups"]
            for row in list(group.get("oa_rows") or [])
            if row.get("id") == "oa-pending-with-time"
        )
        self.assertEqual(pending_row["apply_time"], "2026-07-17 09:08:07")
        self.assertEqual(pending_row["application_date"], "2026-07-17")
        self.assertEqual(pending_row["expense_type"], "交通费")

        searched = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="2026-07-17",
        )
        self.assertTrue(
            any(
                row.get("id") == "oa-pending-with-time"
                for group in searched["groups"]
                for row in list(group.get("oa_rows") or [])
            )
        )
        for search in (
            "进行中",
            "进行中搜索对方",
            "进行中搜索事由",
            "进行中子付款项",
            "差旅费",
            "进行中费用内容",
            "进行中费用说明",
        ):
            with self.subTest(search=search):
                page = self.repository.get_workbench_groups_page(
                    scope_key="2026-07",
                    zone="unpaired",
                    search=search,
                )
                self.assertTrue(
                    any(
                        row.get("id") == "oa-pending-with-time"
                        for group in page["groups"]
                        for row in list(group.get("oa_rows") or [])
                    )
                )

    def test_oa_applicant_filter_options_use_narrow_projection_without_semantic_loss(
        self,
    ) -> None:
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                'oa-source-filter-unknown', 'travel_request', '差旅申请',
                'oa-filter-unknown', 'active', 'completed', '',
                '2026-07-18', '2026-07-01', '筛选项目', 10, 'CNY',
                '{"id":"oa-filter-unknown","month":"2026-07","apply_type":"差旅申请","amount":"10"}'::jsonb,
                '{}'::jsonb
            )
            """
        )
        self.connection.statements.clear()

        payload = self.repository.get_workbench_filter_options(
            scope_key="2026-07", zone="unpaired", pane="oa",
            facet="column", column="applicant", page_size=100,
        )

        options = {option["value"]: option for option in payload["options"]}
        self.assertEqual(options["oaType:差旅申请"]["label"], "差旅申请")
        self.assertEqual(options["applicant:张三"]["label"], "张三")
        self.assertTrue(options["applicant:__workbench_missing__"]["missing"])
        statement = next(
            item for item in self.connection.statements
            if item["operation"] == "fetch_all"
            and "as application_type" in str(item.get("raw_sql") or "")
        )
        projection_sql = str(statement["raw_sql"]).split(
            "filtered_groups as materialized (", 1
        )[1]
        self.assertNotIn("distinct on (member.row_id)", projection_sql.lower())
        self.assertNotIn("order by member.row_id", projection_sql.lower())

    def test_anomaly_state_is_sql_compact_fingerprint_parity_and_keyset_bounded(self) -> None:
        self.connection.statements.clear()
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        group = next(
            group
            for group in initial["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-DIRECT-1"
        )
        anomaly = dict(group.get("workbench_anomaly") or {})

        self.assertEqual(initial["summary"]["unpaired_exception_count"], 1)
        self.assertEqual(initial["summary"]["paired_exception_count"], 0)
        self.assertEqual(anomaly.get("review_decision"), "pending")
        self.assertTrue(str(anomaly.get("fingerprint") or ""))
        self.assertEqual(
            {str(item.get("code") or "") for item in anomaly.get("items") or []},
            {"oa_invoice_attachment_absent", "oa_bank_equal_invoice_less"},
        )
        candidate_statement = next(
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "overall_group_summary as materialized"
            in str(statement.get("raw_sql") or "")
        )
        self.assertEqual(candidate_statement["page_rows_with_anomaly_payload"], 0)

        ordinary_unpaired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
        )
        self.assertTrue(
            any(
                candidate.get("detail_key") == "CASE-DIRECT-1"
                for candidate in ordinary_unpaired["groups"]
            ),
            ordinary_unpaired,
        )

        self.connection.statements.clear()
        unpaired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=1,
            exception_bucket="unpaired",
        )
        self.assertEqual(unpaired["total"], 1)
        self.assertEqual(
            unpaired["groups"][0]["workbench_anomaly"]["fingerprint"],
            anomaly["fingerprint"],
        )
        self.assertEqual(
            sum(
                statement["operation"] == "fetch_all"
                for statement in self.connection.statements
            ),
            3,
        )
        exception_sql = next(
            str(statement.get("raw_sql") or "")
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "anomaly_states" in str(statement.get("raw_sql") or "")
        )
        self.assertIn("groups.zone = %s", exception_sql)
        self.assertIn("limit %s", exception_sql.lower())
        self.assertIn("relation_amount_classifications", exception_sql)
        self.assertNotIn("expense_component_reach", exception_sql)
        self.assertNotIn("component_anomaly_items", exception_sql)

        PostgresWorkbenchRepository(
            self.raw_connection
        ).set_workbench_anomaly_review_decision(
            fingerprint=str(anomaly["fingerprint"]),
            group_id="case:CASE-DIRECT-1",
            scope_key="2026-07",
            actor_id="test-suite",
            actor_account="test-suite",
            actor_name="测试账户",
            decision="accept_paired",
            note="附件异常与金额异常均已复核",
            detected_classification_codes=[
                str(item["code"]) for item in anomaly["items"]
            ],
            evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
        )
        accepted = self.repository.get_workbench_initial_page(scope_key="2026-07")
        self.assertEqual(accepted["summary"]["unpaired_exception_count"], 0)
        self.assertEqual(accepted["summary"]["paired_exception_count"], 1)
        self.assertEqual(
            accepted["paired"]["groups"][0]["workbench_anomaly"]["review_decision"],
            "accept_paired",
        )
        paired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
        )
        self.assertEqual(paired["total"], 1)
        unpaired_after_review = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
        )
        self.assertFalse(
            any(
                group.get("detail_key") == "CASE-DIRECT-1"
                for group in unpaired_after_review["groups"]
            )
        )

    def test_narrow_anomaly_rehydration_keeps_document_owner_semantics(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values (
                'invoice-narrow-doc', 'input', 'INV-NARROW-DOC', '2026-07-23',
                '2026-07-01', 100, 100, 100, 'active', 'visible',
                '[]'::jsonb, '{}'::jsonb
            );
            update app.oa_applications
            set normalized_payload = jsonb_set(
                normalized_payload,
                '{expense_items,0,attachment_file_count}',
                '"1"'::jsonb
            )
            where row_id = 'oa-direct-1';
            update app.workbench_pair_relations
            set row_ids = array['oa-direct-1','bank-direct-1','invoice-narrow-doc'],
                special_metadata = '{"requires_oa":true,"requires_invoice":true}'::jsonb
            where case_id = 'CASE-DIRECT-1'
            """
        )

        def anomaly_codes() -> set[str]:
            page = self.repository.get_workbench_groups_page(
                scope_key="2026-07", zone="unpaired", exception_bucket="unpaired",
            )
            group = next(
                item for item in page["groups"]
                if item.get("detail_key") == "CASE-DIRECT-1"
            )
            return {
                str(item["code"])
                for item in group["workbench_anomaly"]["items"]
            }

        self.assertEqual(
            anomaly_codes(),
            {"oa_invoice_attachment_unassigned", "oa_invoice_attachment_unparsed"},
        )

        self.raw_connection.execute(
            """
            update app.oa_applications
            set normalized_payload = jsonb_set(
                normalized_payload,
                '{expense_items}',
                '[]'::jsonb
            )
            where row_id = 'oa-direct-1'
            """
        )
        no_expense_item_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07", zone="unpaired", exception_bucket="unpaired",
        )
        self.assertNotIn(
            "CASE-DIRECT-1",
            {item.get("detail_key") for item in no_expense_item_page["groups"]},
        )
        self.raw_connection.execute(
            """
            update app.oa_applications
            set normalized_payload = jsonb_set(
                normalized_payload,
                '{expense_items}',
                '[{"id":"oa-direct-1:item:0","amount":"100","attachment_file_count":"1"}]'::jsonb
            )
            where row_id = 'oa-direct-1'
            """
        )
        historical_link = [{
            "source_type": "oa_attachment_invoice",
            "derived_from_oa_id": "oa-direct-1",
            "source_expense_item_id": "oa-direct-1:item:9:historical",
            "source_expense_row_index": "9",
        }]
        self.raw_connection.execute(
            "update app.invoices set source_links = %s::jsonb where legacy_mongo_id = 'invoice-narrow-doc'",
            (json.dumps(historical_link, ensure_ascii=False),),
        )
        self.assertEqual(
            anomaly_codes(),
            {"oa_invoice_attachment_unassigned", "oa_invoice_attachment_unparsed"},
        )

        explicit_link = {
            "source_type": "oa_expense_item_invoice",
            "derived_from_oa_id": "oa-direct-1",
            "source_expense_item_id": "oa-direct-1:item:0",
            "source_expense_row_index": "0",
            "source_relation_case_id": "CASE-DIRECT-1",
        }
        self.raw_connection.execute(
            "update app.invoices set source_links = %s::jsonb where legacy_mongo_id = 'invoice-narrow-doc'",
            (json.dumps([*historical_link, explicit_link], ensure_ascii=False),),
        )
        exception_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07", zone="unpaired", exception_bucket="unpaired",
        )
        self.assertNotIn(
            "CASE-DIRECT-1",
            {item.get("detail_key") for item in exception_page["groups"]},
        )

    def test_case_auto_0185_assignment_closes_document_only_anomaly_atomically(self) -> None:
        expense_item_ids = [
            "oa-direct-1:item:0",
            "oa-direct-1:item:1",
            "oa-direct-1:item:2",
        ]
        expense_items = [
            {"id": expense_item_ids[0], "row_index": "0", "amount": "436.30", "attachment_file_count": "4"},
            {"id": expense_item_ids[1], "row_index": "1", "amount": "531.92", "attachment_file_count": "2"},
            {"id": expense_item_ids[2], "row_index": "2", "amount": "35.00", "attachment_file_count": "1"},
        ]
        self.raw_connection.execute(
            """
            update app.oa_applications
            set amount = 1003.22,
                normalized_payload = normalized_payload ||
                    jsonb_build_object('amount', '1003.22', 'expense_items', %s::jsonb)
            where row_id = 'oa-direct-1'
            """,
            (json.dumps(expense_items, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            select set_config('fin_ops.correction_reason', 'CASE-AUTO-0185 test fixture', false);
            select set_config('fin_ops.actor_id', 'test-suite', false);
            update app.bank_transactions
            set amount = 1003.22, signed_amount = -1003.22
            where legacy_mongo_id = 'bank-direct-1';
            update app.workbench_pair_relations
            set row_ids = array[
                    'oa-direct-1','bank-direct-1','invoice-assignment-90',
                    'invoice-assignment-58','invoice-assignment-43',
                    'invoice-assignment-24530','invoice-assignment-19392',
                    'invoice-assignment','invoice-assignment-35'
                ],
                row_types = array['oa','bank','invoice','invoice','invoice','invoice','invoice','invoice','invoice'],
                special_metadata = '{"requires_oa":true,"requires_invoice":true}'::jsonb
            where case_id = 'CASE-DIRECT-1'
            """
        )
        invoice_fixtures = [
            ("invoice-assignment-90", "90.00", expense_item_ids[0], "0"),
            ("invoice-assignment-58", "58.00", expense_item_ids[0], "0"),
            ("invoice-assignment-43", "43.00", expense_item_ids[0], "0"),
            ("invoice-assignment-24530", "245.30", expense_item_ids[0], "0"),
            ("invoice-assignment-19392", "193.92", expense_item_ids[1], "1"),
            ("invoice-assignment", "338.00", None, None),
            ("invoice-assignment-35", "35.00", expense_item_ids[2], "2"),
        ]
        for invoice_id, amount, expense_item_id, row_index in invoice_fixtures:
            source_links = [{"source_type": "manual_invoice_import", "source_id": invoice_id}]
            if expense_item_id:
                source_links.append({
                    "source_type": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-direct-1",
                    "source_expense_item_id": expense_item_id,
                    "source_expense_row_index": row_index,
                })
            self.raw_connection.execute(
                """
                insert into app.invoices(
                    legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                    invoice_month, amount, signed_amount, total_with_tax, status,
                    workbench_visibility, source_links, raw_payload
                ) values (%s, 'input', %s, '2026-07-23', '2026-07-01',
                          %s, %s, %s, 'active', 'visible', %s::jsonb, '{}'::jsonb)
                """,
                (invoice_id, f"INV-{invoice_id}", amount, amount, amount, json.dumps(source_links)),
            )
        before_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07", zone="unpaired", exception_bucket="unpaired",
        )
        before_group = next(
            item for item in before_page["groups"]
            if item.get("detail_key") == "CASE-DIRECT-1"
        )
        before_invoice_rows = {row["id"]: row for row in before_group["invoice_rows"]}
        self.assertEqual(len(before_group["oa_rows"]), 1)
        self.assertEqual(len(before_group["bank_rows"]), 1)
        self.assertEqual(len(before_invoice_rows), 7)
        self.assertEqual(
            {
                key: before_group["amount_check"][key]
                for key in ("status", "oa_total", "bank_total", "invoice_total")
            },
            {
                "status": "matched",
                "oa_total": "1003.22",
                "bank_total": "1003.22",
                "invoice_total": "1003.22",
            },
        )
        self.assertEqual(
            before_invoice_rows["invoice-assignment-19392"]["source_expense_item_ids"],
            [expense_item_ids[1]],
        )
        self.assertEqual(
            before_invoice_rows["invoice-assignment"]["source_expense_item_ids"],
            [],
        )
        unassigned_item = next(
            item for item in before_group["workbench_anomaly"]["items"]
            if item.get("code") == "oa_invoice_attachment_unassigned"
            and item.get("display_row_id") == "invoice-assignment"
        )
        self.assertEqual(unassigned_item["display_scope"], "row")
        self.assertEqual(unassigned_item["display_pane"], "invoice")
        self.assertEqual(unassigned_item["invoice_total"], "338.00")
        canonical_expense_item_id = next(
            str(item["id"])
            for item in before_group["oa_rows"][0]["expense_items"]
            if item.get("amount") == "531.92"
        )
        relation_before = self.raw_connection.fetch_one(
            """
            select case_id, relation_mode, status, version, month_scope, row_ids, row_types
            from app.workbench_pair_relations where case_id = 'CASE-DIRECT-1'
            """
        )
        invoice_facts_before = self.raw_connection.fetch_all(
            """
            select legacy_mongo_id, invoice_no, amount, signed_amount, total_with_tax
            from app.invoices
            where legacy_mongo_id in ('invoice-assignment-19392', 'invoice-assignment')
            order by legacy_mongo_id
            """
        )

        def repository_factory(transaction: object) -> SimpleNamespace:
            workbench = PostgresWorkbenchRepository(transaction)
            return SimpleNamespace(
                pair_relations=PostgresWorkbenchRelationRepository(transaction),
                exception_cases=workbench,
                row_overrides=workbench,
                canonical_query=PostgresWorkbenchPageSelectionRepository(
                    transaction,
                    tenant_id="default",
                ),
                invoice_source_links=PostgresCoreRepository(transaction),
                operation_audit=PostgresOperationsAuditRepository(transaction),
            )

        service = WorkbenchInvoiceExpenseItemAssignmentService(
            unit_of_work=WorkbenchWriteUnitOfWork(
                connection=self.raw_connection,
                repository_factory=repository_factory,
                idempotency_store=PostgresWorkbenchIdempotencyRepository(
                    self.raw_connection
                ),
            )
        )
        request = {
            "case_id": "CASE-DIRECT-1",
            "invoice_row_id": "invoice-assignment",
            "targets": [{
                "oa_row_id": "oa-direct-1",
                "expense_item_id": canonical_expense_item_id,
            }],
            "anomaly_fingerprint": unassigned_item["fingerprint"],
            "idempotency_key": "assignment-pg-1",
        }
        first = service.assign(
            request,
            actor_id="test-finance-user",
            tenant_id="default",
            request_id="assignment-request-1",
        )
        replay = service.assign(
            request,
            actor_id="test-finance-user",
            tenant_id="default",
            request_id="assignment-request-2",
        )
        noop = service.assign(
            {**request, "idempotency_key": "assignment-pg-2"},
            actor_id="test-finance-user",
            tenant_id="default",
            request_id="assignment-request-3",
        )

        self.assertEqual(replay, first)
        self.assertTrue(first["success"])
        self.assertFalse(noop["changed"])
        source_row = self.raw_connection.fetch_one(
            """
            select source_links
            from app.invoices
            where legacy_mongo_id = 'invoice-assignment'
            """
        )
        source_links = list((source_row or {}).get("source_links") or [])
        self.assertEqual(source_links[0]["source_type"], "manual_invoice_import")
        self.assertEqual(
            source_links[1]["source_expense_item_id"],
            canonical_expense_item_id,
        )
        business_audit = self.raw_connection.fetch_one(
            """
            select count(*)::integer as count
            from audit.events
            where event_type = 'workbench.invoice_expense_items.assigned'
              and object_id = 'invoice-assignment'
            """
        )
        self.assertEqual(int((business_audit or {}).get("count") or 0), 1)
        after_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07", zone="paired",
        )
        after_group = next(
            item for item in after_page["groups"]
            if item.get("detail_key") == "CASE-DIRECT-1"
        )
        self.assertIsNone(after_group.get("workbench_anomaly"))
        self.assertEqual(after_group["amount_check"], before_group["amount_check"])
        self.assertEqual(
            self.raw_connection.fetch_one(
                """
                select case_id, relation_mode, status, version, month_scope, row_ids, row_types
                from app.workbench_pair_relations where case_id = 'CASE-DIRECT-1'
                """
            ),
            relation_before,
        )
        self.assertEqual(
            self.raw_connection.fetch_all(
                """
                select legacy_mongo_id, invoice_no, amount, signed_amount, total_with_tax
                from app.invoices
                where legacy_mongo_id in ('invoice-assignment-19392', 'invoice-assignment')
                order by legacy_mongo_id
                """
            ),
            invoice_facts_before,
        )
        after_invoice_rows = {row["id"]: row for row in after_group["invoice_rows"]}
        self.assertEqual(len(after_invoice_rows), 7)
        self.assertEqual(
            after_invoice_rows["invoice-assignment-19392"]["source_expense_item_ids"],
            [canonical_expense_item_id],
        )
        self.assertEqual(
            after_invoice_rows["invoice-assignment"]["source_expense_item_ids"],
            [canonical_expense_item_id],
        )

    def test_exception_views_count_unique_relations_and_auto_select_first_amount_code(self) -> None:
        fixtures = [
            {
                "fixture_id": "oa-bank-equal-invoice-more",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 120,
                "has_document_anomaly": True,
            },
            {
                "fixture_id": "oa-bank-equal-invoice-more-2",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 120,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-bank-equal-invoice-less",
                "oa_amount": 100,
                "bank_amount": 100,
                "invoice_amount": 80,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-invoice-equal-bank-more",
                "oa_amount": 100,
                "bank_amount": 120,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "oa-invoice-equal-bank-less",
                "oa_amount": 100,
                "bank_amount": 80,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "bank-invoice-equal-oa-less",
                "oa_amount": 80,
                "bank_amount": 100,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "bank-invoice-equal-oa-more",
                "oa_amount": 120,
                "bank_amount": 100,
                "invoice_amount": 100,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "all-amounts-different",
                "oa_amount": 120,
                "bank_amount": 100,
                "invoice_amount": 80,
                "has_document_anomaly": False,
            },
            {
                "fixture_id": "document-only",
                "oa_amount": 50,
                "bank_amount": 50,
                "invoice_amount": 50,
                "has_document_anomaly": True,
            },
        ]
        fixture_json = json.dumps(fixtures, ensure_ascii=False)
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            )
            select
                'source-' || fixture.fixture_id,
                'payment_request',
                '付款申请',
                'oa-facet-' || fixture.fixture_id,
                'active',
                'completed',
                '测试用户',
                '2026-08-01'::date,
                '2026-08-01'::date,
                '异常分类测试',
                fixture.oa_amount,
                'CNY',
                jsonb_build_object(
                    'id', 'oa-facet-' || fixture.fixture_id,
                    'month', '2026-08',
                    'section', 'unpaired',
                    'applicant', '测试用户',
                    'project_name', '异常分类测试',
                    'amount', fixture.oa_amount::text,
                    'workflow_status', 'completed'
                ) || case
                    when fixture.has_document_anomaly then jsonb_build_object(
                        'expense_items',
                        jsonb_build_array(jsonb_build_object(
                            'id', 'oa-facet-' || fixture.fixture_id || ':item:0',
                            'amount', case
                                when fixture.fixture_id = 'document-only'
                                    then (fixture.oa_amount / 2)::text
                                else fixture.oa_amount::text
                            end,
                            'attachment_file_count', '0'
                        )) || case
                            when fixture.fixture_id = 'document-only'
                                then jsonb_build_array(jsonb_build_object(
                                    'id', 'oa-facet-' || fixture.fixture_id || ':item:1',
                                    'amount', (fixture.oa_amount / 2)::text,
                                    'attachment_file_count', '0'
                                ))
                            else '[]'::jsonb
                        end
                    )
                    else '{}'::jsonb
                end,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            )
            select
                'bank-facet-' || fixture.fixture_id,
                '6222000011118106',
                '基本户',
                'outflow',
                '异常分类测试供应商',
                fixture.bank_amount,
                -fixture.bank_amount,
                '2026-08-02'::date,
                '2026-08-01'::date,
                '2026-08-02 10:00:00+08'::timestamptz,
                '异常分类测试',
                '{}'::jsonb,
                'active'
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            )
            select
                'invoice-facet-' || fixture.fixture_id,
                'input',
                'INV-FACET-' || fixture.fixture_id,
                '2026-08-03'::date,
                '2026-08-01'::date,
                fixture.invoice_amount,
                fixture.invoice_amount,
                fixture.invoice_amount,
                'active',
                'visible',
                '[]'::jsonb,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            )
            select
                'CASE-FACET-' || fixture.fixture_id,
                'manual_confirmed',
                'active',
                1,
                '2026-08-01'::date,
                array[
                    'oa-facet-' || fixture.fixture_id,
                    'bank-facet-' || fixture.fixture_id,
                    'invoice-facet-' || fixture.fixture_id
                ],
                array['oa', 'bank', 'invoice'],
                '{}'::jsonb,
                '{}'::jsonb,
                '{}'::jsonb
            from jsonb_to_recordset(%s::jsonb) as fixture(
                fixture_id text,
                oa_amount numeric,
                bank_amount numeric,
                invoice_amount numeric,
                has_document_anomaly boolean
            )
            """,
            (fixture_json,),
        )

        self.connection.statements.clear()
        amount_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="amount",
        )

        self.assertEqual(amount_page["selected_exception_code"], "oa_bank_equal_invoice_more")
        self.assertEqual(amount_page["total"], 2)
        self.assertEqual(amount_page["exception_counts"], {
            "total": 9,
            "amount_total": 8,
            "document_only": 1,
            "by_code": {
                "oa_bank_equal_invoice_more": 2,
                "oa_bank_equal_invoice_less": 1,
                "oa_invoice_equal_bank_more": 1,
                "oa_invoice_equal_bank_less": 1,
                "bank_invoice_equal_oa_less": 1,
                "bank_invoice_equal_oa_more": 1,
                "all_amounts_different": 1,
            },
        })
        self.assertEqual(
            {group["detail_key"] for group in amount_page["groups"]},
            {
                "CASE-FACET-oa-bank-equal-invoice-more",
                "CASE-FACET-oa-bank-equal-invoice-more-2",
            },
        )
        category_sql = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "exception_counts as materialized" in str(statement.get("raw_sql") or "")
        ]
        self.assertEqual(len(category_sql), 1)

        explicit_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="amount",
            exception_code="all_amounts_different",
        )
        self.assertEqual(explicit_page["selected_exception_code"], "all_amounts_different")
        self.assertEqual(explicit_page["total"], 1)
        self.assertEqual(
            explicit_page["groups"][0]["detail_key"],
            "CASE-FACET-all-amounts-different",
        )

        document_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=20,
            exception_bucket="unpaired",
            exception_view="document_only",
        )
        self.assertIsNone(document_page["selected_exception_code"])
        self.assertEqual(document_page["total"], 1)
        self.assertEqual(len(document_page["groups"]), 1)
        self.assertEqual(
            document_page["groups"][0]["detail_key"],
            "CASE-FACET-document-only",
        )
        self.assertEqual(
            [
                item["code"]
                for item in document_page["groups"][0]["workbench_anomaly"]["items"]
            ],
            [
                "oa_invoice_attachment_unassigned",
                "oa_invoice_attachment_absent",
                "oa_invoice_attachment_absent",
            ],
        )
        self.assertEqual(document_page["exception_counts"], amount_page["exception_counts"])

        cursor_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=1,
            exception_bucket="unpaired",
            exception_view="amount",
        )
        self.assertTrue(cursor_page["has_more"])
        self.assertIsNotNone(cursor_page["next_cursor"])
        review_repository = PostgresWorkbenchRepository(self.raw_connection)
        for group in amount_page["groups"]:
            anomaly = group["workbench_anomaly"]
            review_repository.set_workbench_anomaly_review_decision(
                fingerprint=str(anomaly["fingerprint"]),
                group_id=str(group["group_id"]),
                scope_key="2026-08",
                actor_id="test-suite",
                actor_account="test-suite",
                actor_name="测试账户",
                decision="accept_paired",
                note="验证自动分类 cursor 固定分区",
                detected_classification_codes=[
                    str(item["code"]) for item in anomaly["items"]
                ],
                evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
            )
        continued_page = self.repository.get_workbench_groups_page(
            scope_key="2026-08",
            zone="unpaired",
            page_size=1,
            cursor=cursor_page["next_cursor"],
            exception_bucket="unpaired",
            exception_view="amount",
        )
        self.assertEqual(
            continued_page["selected_exception_code"],
            "oa_bank_equal_invoice_more",
        )
        self.assertEqual(continued_page["total"], 0)
        self.assertEqual(continued_page["groups"], [])
        self.assertEqual(
            continued_page["exception_counts"]["by_code"]["oa_bank_equal_invoice_less"],
            1,
        )

    def test_shared_invoice_sources_are_counted_once_with_sql_fingerprint_parity(self) -> None:
        oa_payload = {
            "id": "oa-shared-36",
            "month": "2026-07",
            "section": "unpaired",
            "applicant": "樊祖芳",
            "project_name": "快递费",
            "apply_type": "日常报销",
            "amount": "36.00",
            "workflow_status": "completed",
            "expense_items": [
                {
                    "id": "oa-shared-36:item:0",
                    "expense_item_id": "oa-shared-36:item:0",
                    "row_index": "0",
                    "amount": "18.00",
                    "attachment_file_count": "1",
                },
                {
                    "id": "oa-shared-36:item:1",
                    "expense_item_id": "oa-shared-36:item:1",
                    "row_index": "1",
                    "amount": "18.00",
                    "attachment_file_count": "1",
                },
            ],
        }
        source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-shared-36",
                "source_expense_item_id": "oa-shared-36:item:0",
                "source_expense_row_index": "0",
            },
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-shared-36",
                "source_expense_item_id": "oa-shared-36:item:1",
                "source_expense_row_index": "1",
            },
        ]
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-shared-36', '32', '日常报销', 'oa-shared-36',
                'active', 'completed', '樊祖芳', '2026-07-16', '2026-07-01',
                '快递费', 36, 'CNY', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(oa_payload, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-shared-36', '6222000011118108', '基本户', 'outflow',
                '云南顺丰速运有限公司', 36, -36, '2026-07-16', '2026-07-01',
                '2026-07-16 10:00:00+08', '快递费', '{}'::jsonb, 'active'
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values (
                'invoice-shared-36', 'input', 'INV-SHARED-36', '2026-07-16', '2026-07-01',
                36, 36, 36, 'active', 'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(source_links, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-SHARED-36', 'manual_confirmed', 'active', 1, '2026-07-01',
                array['oa-shared-36','bank-shared-36','invoice-shared-36'],
                array['oa','bank','invoice'], '{}'::jsonb,
                '{"requires_oa":true,"requires_invoice":true}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        matched = self.repository.get_workbench_initial_page(scope_key="2026-07")
        matched_group = next(
            group
            for group in matched["paired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertNotIn("workbench_anomaly", matched_group)
        self.assertEqual(
            matched_group["invoice_rows"][0]["source_expense_item_ids"],
            ["oa-shared-36:item:0", "oa-shared-36:item:1"],
        )

        with self.raw_connection.transaction() as transaction:
            transaction.execute(
                "select set_config('fin_ops.correction_reason', '多对多金额异常测试', true)"
            )
            transaction.execute("select set_config('fin_ops.actor_id', 'test-suite', true)")
            transaction.execute(
                """
                update app.invoices
                set amount = 35.99, signed_amount = 35.99, total_with_tax = 35.99
                where legacy_mongo_id = 'invoice-shared-36'
                """
            )
        mismatched = self.repository.get_workbench_initial_page(scope_key="2026-07")
        mismatched_group = next(
            group
            for group in mismatched["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        anomaly = mismatched_group["workbench_anomaly"]
        self.assertEqual(anomaly["items"][0]["code"], "oa_bank_equal_invoice_less")
        self.assertEqual(anomaly["items"][0]["display_scope"], "row")
        self.assertEqual(anomaly["items"][0]["display_pane"], "invoice")
        self.assertEqual(anomaly["items"][0]["display_row_id"], "invoice-shared-36")
        self.assertEqual(anomaly["items"][0]["source_expense_item_ids"], [
            "oa-shared-36:item:0",
            "oa-shared-36:item:1",
        ])
        active = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            exception_bucket="unpaired",
        )
        active_group = next(
            group for group in active["groups"] if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertEqual(
            active_group["workbench_anomaly"]["fingerprint"],
            anomaly["fingerprint"],
        )

        PostgresWorkbenchRepository(
            self.raw_connection
        ).set_workbench_anomaly_review_decision(
            fingerprint=str(anomaly["fingerprint"]),
            group_id=str(mismatched_group["group_id"]),
            scope_key="2026-07",
            actor_id="test-suite",
            actor_account="test-suite",
            actor_name="测试账户",
            decision="accept_paired",
            note="production-shape regression",
            detected_classification_codes=[
                str(item["code"]) for item in anomaly["items"]
            ],
            evidence_item_fingerprints=list(anomaly["evidence_item_fingerprints"]),
        )

        accepted = self.repository.get_workbench_initial_page(scope_key="2026-07")
        accepted_group = next(
            group
            for group in accepted["paired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertEqual(
            accepted_group["workbench_anomaly"]["review_decision"],
            "accept_paired",
        )
        summary_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
            detail_level="summary",
        )
        full_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="paired",
            exception_bucket="paired",
            detail_level="full",
        )
        summary_group = next(
            group
            for group in summary_page["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        full_group = next(
            group
            for group in full_page["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="paired",
            group_id=str(accepted_group["group_id"]),
            detail_key=str(accepted_group["detail_key"]),
        )
        self.assertEqual(summary_group["zone"], "paired")
        self.assertEqual(full_group["zone"], "paired")
        self.assertEqual(detail["group"]["zone"], "paired")

        self.raw_connection.execute(
            """
            update app.workbench_pair_relations
            set updated_at = now() + interval '1 second'
            where case_id = 'CASE-SHARED-36'
            """
        )
        stale = self.repository.get_workbench_initial_page(scope_key="2026-07")
        stale_group = next(
            group
            for group in stale["unpaired"]["groups"]
            if group.get("detail_key") == "CASE-SHARED-36"
        )
        self.assertNotEqual(
            stale_group["workbench_anomaly"].get("review_decision"),
            "accept_paired",
        )

    def test_manual_expense_item_invoices_satisfy_missing_attachment_evidence(self) -> None:
        oa_payload = {
            "id": "oa-manual-2308",
            "month": "2026-07",
            "section": "unpaired",
            "applicant": "刘涵静",
            "project_name": "2025年1-12月电话费",
            "apply_type": "日常报销",
            "amount": "2308.02",
            "workflow_status": "completed",
            "expense_items": [
                {
                    "id": "oa-manual-2308:item:0",
                    "expense_item_id": "oa-manual-2308:item:0",
                    "row_index": "0",
                    "amount": "2308.02",
                    "attachment_file_count": "0",
                }
            ],
        }
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-manual-2308', '32', '日常报销', 'oa-manual-2308',
                'active', 'completed', '刘涵静', '2026-07-20', '2026-07-01',
                '2025年1-12月电话费', 2308.02, 'CNY', %s::jsonb, '{}'::jsonb
            )
            """,
            (json.dumps(oa_payload, ensure_ascii=False),),
        )
        self.raw_connection.execute(
            """
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-manual-2038', '6222000011118108', '基本户', 'outflow',
                '中国电信股份有限公司昆明分公司', 2038.02, -2038.02,
                '2026-07-20', '2026-07-01', '2026-07-20 10:00:00+08',
                '2025年1-12月电话费', '{}'::jsonb, 'active'
            )
            """
        )
        source_links = [
            {
                "source_type": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-manual-2308",
                "source_expense_item_id": "oa-manual-2308:item:9:historical",
                "source_expense_row_index": "9",
                "source_attachment_key": "historical-attachment.pdf",
            },
            {
                "source_type": "oa_expense_item_invoice",
                "entry_method": "manual_invoice_import",
                "derived_from_oa_id": "oa-manual-2308",
                "source_expense_item_id": "oa-manual-2308:item:0",
                "source_expense_row_index": "0",
                "source_relation_case_id": "CASE-MANUAL-2308",
            }
        ]
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, total_with_tax, status, workbench_visibility,
                source_links, raw_payload
            ) values
                (
                    'invoice-manual-859', 'input', 'INV-MANUAL-859',
                    '2026-07-18', '2026-07-01', 859.57, 859.57, 859.57,
                    'active', 'visible', %s::jsonb, '{}'::jsonb
                ),
                (
                    'invoice-manual-1178', 'input', 'INV-MANUAL-1178',
                    '2026-07-18', '2026-07-01', 1178.45, 1178.45, 1178.45,
                    'active', 'visible', %s::jsonb, '{}'::jsonb
                )
            """,
            (
                json.dumps(source_links, ensure_ascii=False),
                json.dumps(source_links, ensure_ascii=False),
            ),
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-MANUAL-2308', 'manual_confirmed', 'active', 1, '2026-07-01',
                array[
                    'oa-manual-2308', 'bank-manual-2038',
                    'invoice-manual-859', 'invoice-manual-1178'
                ],
                array['oa','bank','invoice','invoice'], '{}'::jsonb,
                '{"requires_oa":true,"requires_invoice":true}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="INV-MANUAL-859",
            detail_level="summary",
        )
        group = next(
            row for row in page["groups"] if row.get("detail_key") == "CASE-MANUAL-2308"
        )
        self.assertEqual(len(group["invoice_rows"]), 2)
        for invoice_row in group["invoice_rows"]:
            self.assertEqual(
                invoice_row["source_expense_item_ids"],
                ["oa-manual-2308:item:0"],
            )

        expense_item = group["oa_rows"][0]["expense_items"][0]
        self.assertEqual(str(expense_item["attachment_file_count"]), "0")
        anomaly_codes = {
            item["code"] for item in group["workbench_anomaly"]["items"]
        }
        self.assertEqual(anomaly_codes, {"bank_invoice_equal_oa_more"})
        self.assertNotIn("oa_invoice_attachment_absent", anomaly_codes)
        self.assertNotIn("oa_invoice_attachment_unparsed", anomaly_codes)

    def test_etc_batch_accounting_summary_does_not_require_oa_attachment_edges(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc-batch-document-contract', 'oa_submitted', '2026-04-01', 2,
                33.00,
                '{"normalized_payload":{"external_etc_batch_id":"ETC-DOCUMENT-CONTRACT"}}'::jsonb
            );
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values
                (
                    'etc-document-20', 'etc-batch-document-contract', 'submitted',
                    'ETC-DOCUMENT-20', '2026-04-11', 'ETC供应商一',
                    20.00, 0.00, 20.00, '{}'::jsonb
                ),
                (
                    'etc-document-13', 'etc-batch-document-contract', 'submitted',
                    'ETC-DOCUMENT-13', '2026-04-12', 'ETC供应商二',
                    13.00, 0.00, 13.00, '{}'::jsonb
                );
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, amount, currency,
                normalized_payload, raw_payload
            ) values (
                'oa-source-etc-document', 'expense_claim', '日常报销',
                'oa-etc-document', 'active', 'completed', '测试用户',
                '2026-04-10', '2026-04-01', 33.00, 'CNY',
                jsonb_build_object(
                    'id', 'oa-etc-document',
                    'amount', '33.00',
                    'workflow_status', 'completed',
                    'expense_items', jsonb_build_array(
                        jsonb_build_object(
                            'id', 'oa-etc-document:item:0',
                            'row_index', '0',
                            'amount', '20.00',
                            'attachment_file_count', '0'
                        ),
                        jsonb_build_object(
                            'id', 'oa-etc-document:item:1',
                            'row_index', '1',
                            'amount', '13.00',
                            'attachment_file_count', '0'
                        )
                    )
                ),
                '{}'::jsonb
            );
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date,
                txn_month, trade_time, summary, raw_payload, status
            ) values (
                'bank-etc-document', '8106', '建设银行 8106', 'outflow',
                'ETC批量账务集中处理', 33.00, -33.00, '2026-04-13',
                '2026-04-01', '2026-04-13T10:52:01+08:00', '报销',
                '{}'::jsonb, 'active'
            );
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-ETC-DOCUMENT-CONTRACT', 'batch_accounting', 'active', 1,
                '2026-04-01',
                array[
                    'oa-etc-document',
                    'bank-etc-document',
                    'etc-summary-ETC-DOCUMENT-CONTRACT'
                ],
                array['oa','bank','invoice'],
                '{"status":"matched","oa_total":"33.00","bank_total":"33.00","invoice_total":"33.00","amount_delta":"0.00"}'::jsonb,
                '{"external_etc_batch_id":"ETC-DOCUMENT-CONTRACT"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-04",
            zone="paired",
            search="ETC-DOCUMENT-CONTRACT",
            detail_level="summary",
        )

        group = next(
            row
            for row in page["groups"]
            if row.get("detail_key") == "CASE-ETC-DOCUMENT-CONTRACT"
        )
        self.assertEqual(group["zone"], "paired")
        self.assertTrue(group["completion"]["is_complete"])
        self.assertIsNone(group.get("workbench_anomaly"))
        self.assertEqual(group["invoice_rows"][0]["source_kind"], "etc_invoice_summary")
        self.assertEqual(group["invoice_rows"][0]["amount"], "33.00")

    def test_summary_hydration_does_not_transport_large_unused_source_payloads(self) -> None:
        sentinel = "summary-hot-path-unused-" + ("x" * 200_000)
        self.raw_connection.execute(
            """
            update app.oa_applications
            set raw_payload = jsonb_build_object('unused_blob', %s::text),
                normalized_payload = normalized_payload ||
                    jsonb_build_object('unused_blob', %s::text)
            where row_id = 'oa-direct-1'
            """,
            (sentinel, sentinel),
        )
        self.raw_connection.execute(
            """
            update app.bank_transactions
            set raw_payload = jsonb_build_object('unused_blob', %s::text)
            where legacy_mongo_id = 'bank-direct-1'
            """,
            (sentinel,),
        )
        self.raw_connection.execute(
            """
            update app.invoices
            set raw_payload = jsonb_build_object('unused_blob', %s::text)
            where legacy_mongo_id = 'same-text-id'
            """,
            (sentinel,),
        )

        self.connection.statements.clear()
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        encoded = json.dumps(initial, ensure_ascii=False, default=str)

        self.assertNotIn("summary-hot-path-unused", encoded)
        self.assertLess(len(encoded.encode("utf-8")), 80_000)
        self.assertEqual(
            sum(
                statement["operation"] == "fetch_all"
                for statement in self.connection.statements
            ),
            3,
        )

    def test_page_etc_hydration_is_one_statement_and_matches_legacy_dto(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_submission_batches(
                submission_batch_id, status, scope_month, invoice_ids, raw_payload
            ) values
                (
                    'legacy-only-submission', 'submitted', '2026-07-01',
                    array['legacy-only-invoice'],
                    '{"normalized_payload":{"etc_batch_id":"legacy-only"}}'::jsonb
                ),
                (
                    'priority-submission', 'submitted', '2026-07-01',
                    array['priority-submitted-invoice'],
                    '{"normalized_payload":{"etc_batch_id":"priority-batch"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values
                (
                    'legacy-only-invoice', 'input', 'LEGACY-ONLY', '2026-07-27',
                    '2026-07-01', 33, 33, 33, 'active',
                    'hidden_after_etc_submission', '[]'::jsonb,
                    '{"normalized_payload":{"etc_submission_batch_id":"legacy-only-submission"}}'::jsonb
                ),
                (
                    'priority-linked-invoice', 'input', 'PRIORITY-LINK', '2026-07-28',
                    '2026-07-01', 11, 11, 11, 'active', 'visible', '[]'::jsonb,
                    '{}'::jsonb
                ),
                (
                    'priority-submitted-invoice', 'input', 'PRIORITY-SUBMITTED',
                    '2026-07-28', '2026-07-01', 33, 33, 33, 'active',
                    'hidden_after_etc_submission', '[]'::jsonb,
                    '{"normalized_payload":{"etc_submission_batch_id":"priority-submission"}}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'priority-business', 'oa_submitted', '2026-07-01', 2, 33,
                '{"normalized_payload":{"external_etc_batch_id":"priority-batch"}}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values
                (
                    'priority-business-linked', 'priority-business', 'submitted',
                    'PRIORITY-LINK', '2026-07-28', '业务批次供应商', 10, 1, 11,
                    '{}'::jsonb
                ),
                (
                    'priority-business-invoice', 'priority-business', 'submitted',
                    'PRIORITY-BUSINESS', '2026-07-28', '业务批次供应商', 20, 2, 22,
                    '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_batch_invoice_links(
                business_batch_id, invoice_id, identity_key, link_status,
                link_source, confidence, raw_payload
            )
            select
                'priority-business', invoices.id, 'priority-link', 'active',
                'test', 'strict', '{}'::jsonb
            from app.invoices invoices
            where invoices.legacy_mongo_id = 'priority-linked-invoice'
            """
        )
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                'oa-source-priority', 'payment_request', '付款申请', 'oa-priority',
                'active', 'completed', '测试用户', '2026-07-28', '2026-07-01',
                'ETC部分桥接测试', 33, 'CNY',
                '{"id":"oa-priority","month":"2026-07","amount":"33","workflow_status":"completed"}'::jsonb,
                '{}'::jsonb
            );
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-priority', '6222000011118106', '基本户', 'outflow',
                'ETC部分桥接测试', 33, -33, '2026-07-28', '2026-07-01',
                '2026-07-28 10:00:00+08', 'ETC报销', '{}'::jsonb, 'active'
            );
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-ETC-PARTIAL-BRIDGE', 'manual_confirmed', 'active', 1,
                '2026-07-01',
                array['oa-priority','bank-priority','etc-summary-priority-batch'],
                array['oa','bank','invoice'], '{}'::jsonb,
                '{"external_etc_batch_id":"priority-batch"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        row_ids_by_external_id = {
            "etc_202607_unlinked": "etc-summary-etc_202607_unlinked",
            "ETC 空格/中文": "etc-summary-ETC-",
            "legacy-only": "etc-summary-legacy-only",
            "priority-batch": "etc-summary-priority-batch",
        }
        external_ids_by_row_id = {row_id: external_id for external_id, row_id in row_ids_by_external_id.items()}
        builder = WorkbenchCanonicalRowsBuilder(connection=self.connection)

        self.connection.statements.clear()
        page_rows = builder._etc_invoice_summary_rows_by_ids(
            set(external_ids_by_row_id),
            external_ids_by_row_id=external_ids_by_row_id,
        )
        page_statement_count = len(self.connection.statements)

        self.connection.statements.clear()
        legacy_rows = builder._etc_invoice_summary_rows(
            external_batch_ids=set(row_ids_by_external_id),
        )
        legacy_statement_count = len(self.connection.statements)
        expected_rows = {
            external_id: {
                **row,
                "id": row_ids_by_external_id[external_id],
            }
            for external_id, row in legacy_rows.items()
        }

        actual_rows = {str(row["etc_batch_id"]): row for row in page_rows}
        self.assertEqual(set(actual_rows), set(expected_rows))
        for external_batch_id in sorted(expected_rows):
            self.assertEqual(
                actual_rows[external_batch_id],
                expected_rows[external_batch_id],
                external_batch_id,
            )
        self.assertEqual(page_statement_count, 1)
        self.assertEqual(legacy_statement_count, 5)
        self.assertEqual(expected_rows["priority-batch"]["amount"], "33.00")
        self.assertEqual(expected_rows["priority-batch"]["etc_invoice_count"], 2)
        self.assertEqual(
            {
                row["invoice_no"]
                for row in expected_rows["priority-batch"]["etc_invoice_detail_rows"]
            },
            {"PRIORITY-LINK", "PRIORITY-BUSINESS"},
        )
        self.assertNotIn(
            "PRIORITY-SUBMITTED",
            {
                row["invoice_no"]
                for row in expected_rows["priority-batch"]["etc_invoice_detail_rows"]
            },
        )
        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        priority_group = next(
            group
            for zone in ("paired", "unpaired")
            for group in initial[zone]["groups"]
            if group.get("detail_key") == "CASE-ETC-PARTIAL-BRIDGE"
        )
        self.assertEqual(priority_group["invoice_rows"][0]["amount"], "33.00")
        self.assertEqual(priority_group["collapsed_row_counts"], {"invoice": 2})
        self.assertNotIn("collapsed_rows", priority_group)
        anomaly_items = list(
            (priority_group.get("workbench_anomaly") or {}).get("items") or []
        )
        self.assertFalse(
            {
                "oa_bank_equal_invoice_more",
                "oa_bank_equal_invoice_less",
                "oa_invoice_equal_bank_more",
                "oa_invoice_equal_bank_less",
                "bank_invoice_equal_oa_less",
                "bank_invoice_equal_oa_more",
                "all_amounts_different",
            }
            & {item.get("code") for item in anomaly_items},
        )

    def test_typed_selection_accepts_cross_pane_same_text_id_and_untyped_fails_closed(self) -> None:
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["same-text-id", "same-text-id"],
            row_types=["bank", "invoice"],
        )

        self.assertEqual(selection["selected_row_types"], ["bank", "invoice"])
        self.assertEqual(
            [row["type"] for row in selection["selected_rows"]],
            ["bank", "invoice"],
        )
        with self.assertRaisesRegex(Exception, "内容不一致"):
            self.selection_repository.get_workbench_relation_preview_selection(
                scope_key="2026-07",
                row_ids=["same-text-id"],
            )

    def test_preview_selection_queries_only_requested_typed_sources_and_owned_relation(self) -> None:
        self.connection.statements.clear()
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["oa-direct-1"],
            row_types=["oa"],
        )

        self.assertEqual(selection["selected_row_ids"], ["oa-direct-1"])
        self.assertEqual(
            {(row["type"], row["id"]) for row in selection["context_rows"]},
            {
                ("bank", "bank-direct-1"),
                ("invoice", "etc-summary-etc_202607_linked"),
                ("invoice", "etc-invoice-direct-2"),
            },
        )
        fetches = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
        ]
        source_sql = str(fetches[0].get("raw_sql") or "").lower()
        descriptor_sql = str(fetches[1].get("raw_sql") or "").lower()
        self.assertIn("oa.row_id = requested.row_id", source_sql)
        self.assertNotIn("canonical_groups", source_sql)
        self.assertNotIn("canonical_groups", descriptor_sql)
        self.assertIn("join selected_sources source", descriptor_sql)

    def test_non_prefixed_oa_id_hydrates_initial_detail_and_preview(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.oa_applications(
                oa_source_id, form_id, form_type, row_id, status, workflow_status,
                applicant, application_date, scope_month, project_name, amount,
                currency, normalized_payload, raw_payload
            ) values (
                'oa-source-object-id', 'payment_request', '付款申请',
                '64ef01a2b3c4d5e6f7890123', 'active', 'completed',
                '李四', '2026-07-26', '2026-07-01', '对象ID项目', 20, 'CNY',
                '{"id":"64ef01a2b3c4d5e6f7890123","month":"2026-07","applicant":"李四","project_name":"对象ID项目","amount":"20","workflow_status":"completed"}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        initial = self.repository.get_workbench_initial_page(scope_key="2026-07")
        oa_group = next(
            group
            for group in initial["unpaired"]["groups"]
            if any(
                row.get("id") == "64ef01a2b3c4d5e6f7890123"
                for row in list(group.get("oa_rows") or [])
            )
        )
        detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="unpaired",
            group_id=str(oa_group["group_id"]),
            detail_key=str(oa_group["detail_key"]),
        )
        selection = self.selection_repository.get_workbench_relation_preview_selection(
            scope_key="2026-07",
            row_ids=["64ef01a2b3c4d5e6f7890123"],
            row_types=["oa"],
        )

        self.assertEqual(detail["group"]["oa_rows"][0]["id"], "64ef01a2b3c4d5e6f7890123")
        self.assertEqual(selection["selected_rows"][0]["id"], "64ef01a2b3c4d5e6f7890123")

    def test_etc_legacy_identity_collision_fails_closed(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.etc_business_batches(
                business_batch_id, status, scope_month, invoice_count,
                total_amount, raw_payload
            ) values (
                'etc_202607_collision', 'oa_submitted', '2026-07-01', 1,
                11, '{"normalized_payload":{"external_etc_batch_id":"ETC/中文"}}'::jsonb
            )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.etc_invoices(
                etc_invoice_id, business_batch_id, status, invoice_no,
                invoice_date, seller_name, amount, tax_amount, total_with_tax,
                raw_payload
            ) values (
                'etc-invoice-collision', 'etc_202607_collision', 'submitted',
                'ETC-INV-COLLISION', '2026-07-26', 'ETC碰撞供应商', 10, 1, 11,
                '{}'::jsonb
            )
            """
        )

        with self.assertRaises(WorkbenchDirectQueryUnavailable):
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
            )

    def test_invalid_relation_member_arrays_fail_closed_in_postgres(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-INVALID-TYPED-MEMBERS', 'manual_confirmed', 'active', 1,
                '2026-07-01', array['same-text-id'], array['unsupported'],
                '{}'::jsonb, '{}'::jsonb, '{}'::jsonb
            )
            """
        )

        with self.assertRaises(WorkbenchDirectQueryUnavailable):
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
            )

    def test_invoice_identity_arbitration_uses_global_active_owner(self) -> None:
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values
                (
                    'invoice-july-duplicate', 'input', 'GLOBAL-DUPLICATE', 'GLOBAL-DUPLICATE',
                    '2026-07-25', '2026-07-01', 12, 12, 12, 'active',
                    'visible', '[]'::jsonb, '{}'::jsonb
                ),
                (
                    'invoice-august-owner', 'input', 'GLOBAL-DUPLICATE', 'GLOBAL-DUPLICATE',
                    '2026-08-01', '2026-08-01', 12, 12, 12, 'active',
                    'visible', '[]'::jsonb, '{}'::jsonb
                )
            """
        )
        self.raw_connection.execute(
            """
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-GLOBAL-INVOICE-OWNER', 'manual_confirmed', 'active', 1,
                '2026-08-01', array['invoice-august-owner'], array['invoice'],
                '{}'::jsonb,
                '{"requires_oa":false,"requires_invoice":false}'::jsonb,
                '{}'::jsonb
            )
            """
        )

        page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="GLOBAL-DUPLICATE",
        )

        self.assertEqual(page["total"], 0, page)
        self.assertEqual(page["groups"], [])

        with self.assertRaisesRegex(ValueError, "missing"):
            self.selection_repository._resolve_source_descriptors(
                scope_key="2026-07",
                row_ids=["invoice-july-duplicate"],
                row_types=["invoice"],
            )
        owner = self.selection_repository._resolve_source_descriptors(
            scope_key="2026-08",
            row_ids=["invoice-august-owner"],
            row_types=["invoice"],
        )
        self.assertEqual(
            [(row["row_type"], row["row_id"]) for row in owner],
            [("invoice", "invoice-august-owner")],
        )

    def test_oa_attachment_source_owner_groups_are_readable_and_formal_safe(self) -> None:
        self.raw_connection.execute(
            """
            with inserted_oa as (
                insert into app.oa_applications(
                    oa_source_id, form_id, form_type, row_id, status,
                    workflow_status, applicant, application_date, scope_month,
                    project_name, amount, currency, normalized_payload, raw_payload
                ) values (
                    'oa-source-owned-unpaired', 'daily-expense', '日常报销',
                    'oa-source-owned-unpaired', 'active', 'completed', '测试员',
                    '2026-06-20', '2026-06-01', '来源归属未关联', 290, 'CNY',
                    '{"source_aliases":["oa-source-owned-historical"],"expense_items":[{"id":"oa-source-owned-unpaired:item:0:current","row_index":"0","amount":"290"}]}'::jsonb,
                    '{}'::jsonb
                ) returning id
            )
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id, item_type,
                item_no, amount, normalized_payload, raw_payload
            )
            select id, 'oa-source-owned-unpaired', 'daily-expense',
                   'oa-source-owned-unpaired:item:0:current', 'expense', '0',
                   290, '{"row_index":"0"}'::jsonb, '{}'::jsonb
            from inserted_oa
            """
        )
        source_links = json.dumps(
            [
                {
                    "source_type": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-source-owned-historical",
                    "source_expense_item_id": (
                        "oa-source-owned-unpaired:item:0:current"
                    ),
                    "source_expense_row_index": "0",
                }
            ],
            ensure_ascii=False,
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values
                (
                    'invoice-source-owned-145-a', 'input',
                    'SOURCE-OWNED-INV-145-A', '2026-07-20', '2026-07-01',
                    145, 145, 145, 'active', 'visible', %s::jsonb, '{}'::jsonb
                ),
                (
                    'invoice-source-owned-145-b', 'input',
                    'SOURCE-OWNED-INV-145-B', '2026-07-20', '2026-07-01',
                    145, 145, 145, 'active', 'visible', %s::jsonb, '{}'::jsonb
                )
            """,
            (source_links, source_links),
        )
        incomplete_source_links = json.dumps(
            [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": (
                        "oa-source-owned-unpaired:item:0:current"
                    ),
                },
                {
                    "source_type": "oa_attachment_invoice",
                },
            ],
            ensure_ascii=False,
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values (
                'invoice-source-owner-incomplete', 'input',
                'INCOMPLETE-SOURCE-OWNER', '2026-07-20', '2026-07-01',
                17, 17, 17, 'active', 'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (incomplete_source_links,),
        )
        self.raw_connection.execute(
            """
            with inserted_oa as (
                insert into app.oa_applications(
                    oa_source_id, form_id, form_type, row_id, status,
                    workflow_status, applicant, application_date, scope_month,
                    project_name, amount, currency, normalized_payload, raw_payload
                ) values (
                    'oa-source-owned-second', 'daily-expense', '日常报销',
                    'oa-source-owned-second', 'active', 'completed', '第二测试员',
                    '2026-07-19', '2026-07-01', '第二来源归属未关联', 88, 'CNY',
                    '{"expense_items":[{"id":"oa-source-owned-second:item:0","row_index":"0","amount":"88"}]}'::jsonb,
                    '{}'::jsonb
                ) returning id
            )
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id, item_type,
                item_no, amount, normalized_payload, raw_payload
            )
            select id, 'oa-source-owned-second', 'daily-expense',
                   'oa-source-owned-second:item:0', 'expense', '0', 88,
                   '{"row_index":"0"}'::jsonb, '{}'::jsonb
            from inserted_oa
            """
        )
        second_source_link = json.dumps(
            [
                {
                    "source_type": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-source-owned-second",
                    "source_expense_item_id": "oa-source-owned-second:item:0",
                    "source_expense_row_index": "0",
                }
            ],
            ensure_ascii=False,
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values (
                'invoice-source-owned-second', 'input',
                'SOURCE-OWNED-INV-SECOND', '2026-07-19', '2026-07-01',
                88, 88, 88, 'active', 'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (second_source_link,),
        )

        unpaired = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE-OWNED-INV-145",
        )

        self.assertEqual(unpaired["total"], 1, unpaired)
        source_group = unpaired["groups"][0]
        self.assertEqual(
            [row["id"] for row in source_group["oa_rows"]],
            ["oa-source-owned-unpaired"],
        )
        self.assertEqual(
            {row["id"] for row in source_group["invoice_rows"]},
            {"invoice-source-owned-145-a", "invoice-source-owned-145-b"},
        )
        incomplete_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="INCOMPLETE-SOURCE-OWNER",
        )
        self.assertEqual(incomplete_page["total"], 1, incomplete_page)
        self.assertEqual(incomplete_page["groups"][0]["oa_rows"], [])
        self.assertEqual(
            [row["id"] for row in incomplete_page["groups"][0]["invoice_rows"]],
            ["invoice-source-owner-incomplete"],
        )
        source_detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="unpaired",
            group_id=str(source_group["group_id"]),
            detail_key=str(source_group["detail_key"]),
        )
        self.assertIsNotNone(source_detail)
        assert source_detail is not None
        self.assertEqual(
            {row["id"] for row in source_detail["group"]["invoice_rows"]},
            {"invoice-source-owned-145-a", "invoice-source-owned-145-b"},
        )
        all_source_page = self.repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            search="SOURCE-OWNED-INV-145",
        )
        self.assertEqual(all_source_page["total"], 1, all_source_page)
        all_source_group = all_source_page["groups"][0]
        self.assertEqual(
            {row["id"] for row in all_source_group["invoice_rows"]},
            {"invoice-source-owned-145-a", "invoice-source-owned-145-b"},
        )
        all_source_detail = self.repository.get_workbench_group_detail(
            scope_key="all",
            zone="unpaired",
            group_id=str(all_source_group["group_id"]),
            detail_key=str(all_source_group["detail_key"]),
        )
        self.assertIsNotNone(all_source_detail)
        assert all_source_detail is not None
        self.assertEqual(
            {row["id"] for row in all_source_detail["group"]["invoice_rows"]},
            {"invoice-source-owned-145-a", "invoice-source-owned-145-b"},
        )
        filtered_source = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE-OWNED-INV-145",
            source_kind="oa_attachment_invoice",
            column_filters={
                "oa": {"applicant": ["applicant:测试员"]},
            },
        )
        self.assertEqual(filtered_source["total"], 1, filtered_source)
        cursor_first = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE-OWNED-INV",
            page_size=1,
        )
        self.assertEqual(cursor_first["total"], 2, cursor_first)
        self.assertTrue(cursor_first["has_more"])
        self.assertIsNotNone(cursor_first["next_cursor"])
        cursor_second = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE-OWNED-INV",
            page_size=1,
            cursor=cursor_first["next_cursor"],
        )
        self.assertEqual(cursor_second["total"], 2, cursor_second)
        self.assertFalse(cursor_second["has_more"])
        self.assertNotEqual(
            cursor_first["groups"][0]["group_id"],
            cursor_second["groups"][0]["group_id"],
        )
        source_row_detail = self.repository.get_workbench_row_detail(
            scope_key="2026-07",
            row_id="invoice-source-owned-145-a",
            row_type="invoice",
        )
        self.assertIsNotNone(source_row_detail)
        assert source_row_detail is not None
        self.assertEqual(
            source_row_detail["row"]["id"],
            "invoice-source-owned-145-a",
        )

        self.raw_connection.execute(
            """
            with inserted_oa as (
                insert into app.oa_applications(
                    oa_source_id, form_id, form_type, row_id, status,
                    workflow_status, applicant, application_date, scope_month,
                    project_name, amount, currency, normalized_payload, raw_payload
                ) values (
                    'oa-source-display', 'payment-request', '支付申请',
                    'oa-source-display', 'active', 'completed', '展示归属测试员',
                    '2026-07-21', '2026-07-01', '展示归属正式关系', 300, 'CNY',
                    '{"expense_items":[{"id":"oa-source-display:item:0","row_index":"0","amount":"300"}]}'::jsonb,
                    '{}'::jsonb
                ) returning id
            )
            insert into app.oa_application_items(
                oa_application_id, oa_source_id, form_id, row_id, item_type,
                item_no, amount, normalized_payload, raw_payload
            )
            select id, 'oa-source-display', 'payment-request',
                   'oa-source-display:item:0', 'expense', '0', 300,
                   '{"row_index":"0"}'::jsonb, '{}'::jsonb
            from inserted_oa;
            insert into app.bank_transactions(
                legacy_mongo_id, account_no, account_name, txn_direction,
                counterparty_name_raw, amount, signed_amount, txn_date, txn_month,
                trade_time, summary, raw_payload, status
            ) values (
                'bank-source-display', '6222000011118109', '基本户', 'outflow',
                'SOURCE DISPLAY OWNER BANK', 300, -300, '2026-07-21',
                '2026-07-01', '2026-07-21 10:00:00+08', '展示归属',
                '{}'::jsonb, 'active'
            );
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, version, month_scope,
                row_ids, row_types, amount_check, special_metadata, raw_payload
            ) values (
                'CASE-SOURCE-DISPLAY', 'manual_confirmed', 'active', 9,
                '2026-07-01', array['oa-source-display','bank-source-display'],
                array['oa','bank'], '{}'::jsonb,
                '{"requires_oa":true,"requires_invoice":false}'::jsonb,
                '{}'::jsonb
            )
            """
        )
        baseline_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE DISPLAY OWNER BANK",
        )
        self.assertEqual(baseline_page["total"], 1, baseline_page)
        baseline_group = baseline_page["groups"][0]
        relation_before = self.raw_connection.fetch_one(
            """
            select row_ids, row_types, version
            from app.workbench_pair_relations
            where case_id = 'CASE-SOURCE-DISPLAY'
            """
        )
        display_link = json.dumps(
            [
                {
                    "source_type": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-source-display",
                    "source_expense_item_id": "oa-source-display:item:0",
                    "source_expense_row_index": "0",
                }
            ],
            ensure_ascii=False,
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values (
                'invoice-source-display', 'input', 'SOURCE-DISPLAY-INVOICE',
                '2026-07-21', '2026-07-01', 300, 300, 300, 'active',
                'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (display_link,),
        )
        self.raw_connection.execute(
            """
            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, invoice_date,
                invoice_month, amount, signed_amount, total_with_tax, status,
                workbench_visibility, source_links, raw_payload
            ) values (
                'invoice-source-display-cross-month', 'input',
                'SOURCE-DISPLAY-CROSS-MONTH', '2026-08-02', '2026-08-01',
                50, 50, 50, 'active', 'visible', %s::jsonb, '{}'::jsonb
            )
            """,
            (display_link,),
        )

        display_page = self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            search="SOURCE-DISPLAY-INVOICE",
        )

        self.assertEqual(display_page["total"], 1, display_page)
        display_group = display_page["groups"][0]
        self.assertEqual(display_group["detail_key"], "CASE-SOURCE-DISPLAY")
        self.assertEqual(
            display_group["formal_member_ids"],
            ["oa-source-display", "bank-source-display"],
        )
        self.assertEqual(display_group["formal_member_types"], ["oa", "bank"])
        self.assertEqual(
            display_group["invoice_rows"][0]["workbench_membership_role"],
            "source_owned_display",
        )
        self.assertEqual(
            display_group["completion"],
            baseline_group["completion"],
        )
        self.assertEqual(
            display_group.get("workbench_anomaly"),
            baseline_group.get("workbench_anomaly"),
        )
        self.assertEqual(display_group["can_withdraw"], baseline_group["can_withdraw"])
        relation_after = self.raw_connection.fetch_one(
            """
            select row_ids, row_types, version
            from app.workbench_pair_relations
            where case_id = 'CASE-SOURCE-DISPLAY'
            """
        )
        self.assertEqual(relation_after, relation_before)

        self.connection.statements.clear()
        display_detail = self.repository.get_workbench_group_detail(
            scope_key="2026-07",
            zone="unpaired",
            group_id=str(display_group["group_id"]),
            detail_key=str(display_group["detail_key"]),
        )
        self.assertIsNotNone(display_detail)
        assert display_detail is not None
        detail_group = display_detail["group"]
        self.assertEqual(
            detail_group["formal_member_ids"],
            ["oa-source-display", "bank-source-display"],
        )
        self.assertEqual(detail_group["formal_member_types"], ["oa", "bank"])
        self.assertEqual(detail_group["relation_version"], 9)
        self.assertEqual(detail_group["completion"], baseline_group["completion"])
        self.assertEqual(
            detail_group.get("workbench_anomaly"),
            baseline_group.get("workbench_anomaly"),
        )
        self.assertEqual(detail_group["can_withdraw"], baseline_group["can_withdraw"])
        self.assertEqual(
            {row["id"] for row in detail_group["invoice_rows"]},
            {"invoice-source-display", "invoice-source-display-cross-month"},
        )
        self.assertTrue(
            all(
                row["workbench_membership_role"] == "source_owned_display"
                and row["available_actions"] == ["detail"]
                for row in detail_group["invoice_rows"]
            )
        )
        concrete_target_queries = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "requested_target as" in str(statement.get("raw_sql") or "").lower()
        ]
        self.assertEqual(len(concrete_target_queries), 1)
        all_display_page = self.repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            search="SOURCE DISPLAY OWNER BANK",
        )
        self.assertEqual(all_display_page["total"], 1, all_display_page)
        all_display_group = all_display_page["groups"][0]
        self.assertEqual(
            {row["id"] for row in all_display_group["invoice_rows"]},
            {"invoice-source-display", "invoice-source-display-cross-month"},
        )
        self.connection.statements.clear()
        all_display_detail = self.repository.get_workbench_group_detail(
            scope_key="all",
            zone="unpaired",
            group_id=str(all_display_group["group_id"]),
            detail_key=str(all_display_group["detail_key"]),
        )
        self.assertIsNotNone(all_display_detail)
        assert all_display_detail is not None
        self.assertEqual(
            {
                row["id"]
                for row in all_display_detail["group"]["invoice_rows"]
            },
            {"invoice-source-display", "invoice-source-display-cross-month"},
        )
        target_queries = [
            statement
            for statement in self.connection.statements
            if statement["operation"] == "fetch_all"
            and "requested_target as" in str(statement.get("raw_sql") or "").lower()
        ]
        self.assertEqual(len(target_queries), 1)
        target_sql = str(target_queries[0]["raw_sql"]).lower()
        self.assertIn(
            "invoice.invoice_month = invoice_scope.scope_month",
            target_sql,
        )
        self.assertNotIn(
            "scope.scope_key = 'all' or invoice.invoice_month",
            target_sql,
        )
        self.assertNotIn("scoped_source_keys", target_sql)
        self.assertNotIn("canonical_groups as materialized", target_sql)

    def test_statement_count_is_page_size_independent_and_emits_timings(self) -> None:
        statement_counts: list[int] = []
        for page_size in (50, 100):
            self.connection.statements.clear()
            self.repository.get_workbench_groups_page(
                scope_key="2026-07",
                zone="unpaired",
                page_size=page_size,
            )
            statement_counts.append(
                sum(
                    statement["operation"] == "fetch_all"
                    for statement in self.connection.statements
                )
            )
            self.assertTrue(
                all(float(statement["duration_ms"]) >= 0 for statement in self.connection.statements)
            )
        self.assertEqual(statement_counts[0], statement_counts[1])
        self.assertEqual(statement_counts, [3, 3])
        if os.environ.get("FIN_OPS_PRINT_QUERY_TIMINGS") == "1":
            print(json.dumps(self.connection.statements, ensure_ascii=False, indent=2))

    def test_direct_page_snapshot_uses_hash_merge_plan_for_canonical_spine(self) -> None:
        self.connection.statements.clear()

        self.repository.get_workbench_groups_page(
            scope_key="2026-07",
            zone="unpaired",
            page_size=50,
        )

        executed_sql = [
            str(statement.get("raw_sql") or "").strip().lower()
            for statement in self.connection.statements
            if statement["operation"] == "execute"
        ]
        self.assertIn("set local jit = off", executed_sql)
        self.assertIn("set local enable_nestloop = off", executed_sql)
        self.assertIn("set local max_parallel_workers_per_gather = 0", executed_sql)


if __name__ == "__main__":
    unittest.main()
