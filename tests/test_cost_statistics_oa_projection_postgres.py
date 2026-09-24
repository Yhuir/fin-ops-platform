import json
import unittest

from fin_ops_platform.services.cost_statistics_canonical_repository import _cost_oa_payload, _postgres_oa_rows
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import row_payload

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class CostOaProjectionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.addCleanup(truncate_test_database, self.database_url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)

    def test_narrow_projection_preserves_all_cost_fields_without_attachment_payloads(self):
        large_attachment = {'content': 'attachment content ' * 10000}
        payload = {
            'application_date': '2026-08-01', 'project_id': 'project-1', 'project_name': '项目',
            'expense_type': '住宿费', 'expense_content': '出差', 'applicant': '申请人',
            'counterparty_name': '酒店', 'amount': '145.00', 'reconciliation_amount': '145.00',
            'reason': '报销', 'currency': 'CNY', 'attachments': [large_attachment],
            'detail_fields': {'申请时间': '2026-08-02', '申请日期': '2026-08-01', '项目名称': '项目',
                              '项目编号': 'project-1', '费用类型': '住宿费', '费用内容': '出差',
                              '申请人': '申请人', '收款账号': 'test-account', '附件': large_attachment},
            'expense_items': [{'expense_item_id': 'item-1', 'row_id': 'row-1', 'item_id': 'old-item',
                               'project_id': 'project-1', 'project_name': '项目', 'expense_type': '住宿费',
                               'expense_content': '出差', 'reason': '报销', 'settlement_amount': '145.00',
                               'amount': '145.00', 'total_with_tax': '145.00', 'attachments': [large_attachment]},
                              None, 'not-an-item', {}, {'attachments': [large_attachment]}],
        }
        variants = [payload, {**payload, 'detail_fields': None, 'expense_items': []},
                    {**payload, 'detail_fields': 'not-an-object', 'expense_items': None}, {},
                    {'normalized_payload': payload}, None, False, [], 'invalid',
                    {'normalized_payload': None}, {'normalized_payload': False},
                    {'normalized_payload': []}, {'normalized_payload': 'invalid'}]
        for index, raw in enumerate(variants):
            oa_id = f'projection-oa-{index}'
            self.connection.execute('''insert into app.oa_applications
                (oa_source_id, form_id, form_type, row_id, status, workflow_status,
                 application_date, scope_month, amount, currency, normalized_payload, raw_payload)
                values (%s,%s,'日常报销',%s,'active','completed','2026-08-01','2026-08-01',145,'CNY',%s::jsonb,'{}')''',
                (oa_id, oa_id, oa_id, json.dumps(raw)))
        rows = _postgres_oa_rows(self.connection, oa_ids=[f'projection-oa-{i}' for i in range(len(variants))])
        expected = [_cost_oa_payload(row_payload({'normalized_payload': raw}, 'normalized_payload'), row_id=f'projection-oa-{i}', apply_type='日常报销', workflow_status='completed')
                    for i, raw in enumerate(variants)]
        expected = [row for row in expected if row]
        self.assertEqual(rows, sorted(expected, key=lambda row: row["id"]))
        self.assertNotIn('attachment content', json.dumps(rows))
        self.assertEqual(_postgres_oa_rows(self.connection, oa_ids=['projection-oa-1']), [expected[1]])
        self.assertEqual(_postgres_oa_rows(self.connection, oa_ids=[]), [])
