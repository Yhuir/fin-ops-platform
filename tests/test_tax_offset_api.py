import json
import unittest
from http import HTTPStatus
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import Mock

from openpyxl import load_workbook

from fin_ops_platform.app.routes_tax import TaxApiRoutes
from fin_ops_platform.app.server import Application
from fin_ops_platform.services.import_job_queue import ImportJobIdempotencyConflict
from fin_ops_platform.services.tax_certified_import_job_service import TaxCertifiedImportJobService
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQueryService
from tests.test_tax_offset_canonical_repository import FakeConnection


def json_body(body):
    try:
        payload = json.loads(body or '{}')
    except (ValueError, TypeError):
        return {}, (HTTPStatus.BAD_REQUEST, {'error': 'invalid_json'})
    if not isinstance(payload, dict):
        return {}, (HTTPStatus.BAD_REQUEST, {'error': 'invalid_json'})
    return payload, None


class TaxOffsetApiTests(unittest.TestCase):
    def setUp(self):
        self.session = SimpleNamespace(identity=SimpleNamespace(username='tax-user'))
        self.repository = Mock()
        self.repository.load_page.return_value = {
            'rows': [{'id': 'invoice-1', 'certification_status': 'certified', 'tax_amount': '6.00'}],
            'total': 1, 'page': 1, 'page_size': 50,
            'summary': {'certified': {'count': 1, 'tax_amount': '6.00'}, 'uncertified': {'count': 0}},
            'inventory_statistics': {'input_invoice_count': 9, 'special_invoice_count': 1,
                'general_invoice_count': 3, 'toll_invoice_count': 2, 'other_invoice_count': 2,
                'unclassified_invoice_count': 1},
        }
        self.exporter = Mock()
        self.exporter.export.return_value = ('专票清单.xlsx', b'xlsx')
        self.records = Mock(return_value={'records': [], 'batches': []})
        self.preview = Mock(return_value={'session': {'id': 'session-1'}, 'files': [], 'summary': {}})
        self.revoke = Mock(return_value={'status': 'revoked', 'batch_id': 'batch-1'})
        self.jobs = Mock()
        self.jobs.validate_session_owner.return_value = None
        self.queue = Mock(return_value={'import_job_id': 'job-1'})
        self.routes = TaxApiRoutes(
            query_service=TaxOffsetQueryService(canonical_repository=self.repository),
            export_service=self.exporter,
            export_response=lambda name, content: (HTTPStatus.OK, {'filename': name, 'content': content}),
            certified_import_job_service=self.jobs,
            resolve_read_session=lambda headers: (self.session, None),
            resolve_mutation_session=lambda headers: (self.session, None),
            load_json_body=json_body,
            certified_import_records_provider=self.records,
            certified_import_preview_provider=self.preview,
            revoke_batch_provider=self.revoke,
            enqueue_import_job=self.queue,
            serialize_import_job=lambda job: job,
        )

    def route(self, method, path, payload=None, query=None):
        return self.routes.route(method, path, query or {}, json.dumps(payload) if payload is not None else None, {})

    def test_inventory_reads_paged_rows_summary_and_export_catalog(self):
        status, payload = self.route('GET', '/api/tax-offset', query={'status': ['certified'], 'issue_month': ['2026-09'], 'selection_year': ['2027']})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload['total'], 1)
        self.assertEqual(payload['rows'][0]['tax_amount'], '6.00')
        self.assertEqual(payload['summary']['certified']['count'], 1)
        self.assertEqual(payload['inventory_statistics'], self.repository.load_page.return_value['inventory_statistics'])
        self.assertEqual(sum(field['default_selected'] for field in payload['export_fields']), 8)
        query = self.repository.load_page.call_args.args[0]
        self.assertEqual(query.issue_month, '2026-09')
        self.assertEqual(query.selection_year, '2027')
        self.assertEqual(query.status, 'certified')

    def test_invalid_and_retired_query_parameters_are_rejected_before_sql(self):
        for query in ({'month': ['2026-09']}, {'status': ['bad']}, {'page': ['0']},
                      {'issue_month': ['2026-13']}, {'issue_year': ['2026'], 'issue_month': ['2026-01']},
                      {'selection_year': ['bad']}, {'issue_year': ['2025', '2026']}, {'sort_by': ['amount']}, {'page': ['1', '2']}):
            with self.subTest(query=query):
                status, payload = self.route('GET', '/api/tax-offset', query=query)
                self.assertEqual(status, HTTPStatus.BAD_REQUEST)
                self.assertEqual(payload['error'], 'invalid_tax_certification_query')
        self.repository.load_page.assert_not_called()

    def test_missing_repository_does_not_fall_back_to_empty_inventory(self):
        self.routes._query_service = None
        status, payload = self.route('GET', '/api/tax-offset')
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(payload['error'], 'tax_certification_unavailable')
        self.assertNotIn('rows', payload)

    def test_retired_plan_and_calculation_routes_are_absent(self):
        for method, path in [('GET', '/api/tax-offset/summary'), ('POST', '/api/tax-offset/calculate'), ('POST', '/api/tax-offset/plans')]:
            self.assertIsNone(self.route(method, path, {}))

    def test_query_and_export_enforce_read_permission(self):
        denied = (HTTPStatus.FORBIDDEN, {'error': 'page_access_denied'})
        self.routes._resolve_read_session = lambda headers: (None, denied)
        self.assertEqual(self.route('GET', '/api/tax-offset'), denied)
        self.assertEqual(self.route('POST', '/api/tax-offset/export', {}), denied)
        self.repository.load_page.assert_not_called()
        self.exporter.export.assert_not_called()

    def test_export_passes_exact_filters_and_fields_and_returns_file(self):
        filters = {'status': 'certified', 'search': '测试', 'sort_by': 'selection_time', 'sort_direction': 'asc'}
        status, payload = self.route('POST', '/api/tax-offset/export', {'filters': filters, 'fields': ['invoice_no', 'tax_amount']})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {'filename': '专票清单.xlsx', 'content': b'xlsx'})
        self.exporter.export.assert_called_once_with(filters, ['invoice_no', 'tax_amount'])

    def test_application_wiring_exports_real_xlsx_with_two_argument_download_port(self):
        connection = FakeConnection(count=1)
        app = Application.__new__(Application)
        app._state_store = SimpleNamespace(_sql_read_connection=connection)
        app._tax_certified_import_service = Mock()
        app._resolve_tax_offset_read_session = lambda headers: (self.session, None)
        app._load_json_body = json_body
        app._configure_tax_offset_application_services()
        response = app._tax_api_routes.route('POST', '/api/tax-offset/export', {}, json.dumps({
            'filters': {'status': 'certified', 'issue_year': '2026'},
            'fields': ['digital_invoice_no', 'tax_amount'],
        }), {})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn('spreadsheetml.sheet', response.headers['Content-Type'])
        self.assertIn("filename*=UTF-8''", response.headers['Content-Disposition'])
        response.headers['Content-Disposition'].encode('ascii')
        workbook = load_workbook(BytesIO(response.body), read_only=True)
        self.addCleanup(workbook.close)
        self.assertEqual(list(workbook.active.values), [('数电发票号码', '税额'), ('001234567890123456789', 0)])
        self.assertEqual(len(connection.queries), 2)
        self.assertEqual(connection.queries[-1][1][-2:], (20001, 0))

    def test_export_rejects_invalid_shapes_and_surfaces_failures(self):
        for payload in ({'filters': []}, {'fields': 'invoice_no'}, {'fields': [123]}, {'unknown': 1}):
            self.assertEqual(self.route('POST', '/api/tax-offset/export', payload)[0], HTTPStatus.BAD_REQUEST)
        self.exporter.export.assert_not_called()
        self.exporter.export.side_effect = ValueError('导出数量超出上限。')
        status, payload = self.route('POST', '/api/tax-offset/export', {})
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload['message'], '导出数量超出上限。')

    def test_batch_history_has_no_required_month(self):
        status, payload = self.route('GET', '/api/tax-offset/certified-imports')
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload, {'records': [], 'batches': []})
        self.records.assert_called_once_with(None, records_page=1, batches_page=1, page_size=20)

    def test_preview_parse_error_is_not_reported_as_success(self):
        self.preview.side_effect = ValueError('未找到发票工作表。')
        status, payload = self.routes.handle_certified_import_preview(imported_by='tax-user', uploads=[])
        self.assertEqual(status, HTTPStatus.BAD_REQUEST)
        self.assertEqual(payload['message'], '未找到发票工作表。')

    def test_batch_history_rejects_unbounded_or_invalid_page_size(self):
        for query in ({'page_size': ['101']}, {'records_page': ['0']}, {'batches_page': ['wrong']}):
            status, payload = self.route('GET', '/api/tax-offset/certified-imports', query=query)
            self.assertEqual(status, HTTPStatus.BAD_REQUEST)
            self.assertEqual(payload['error'], 'invalid_tax_certified_import_request')
        self.records.assert_not_called()

    def test_confirmation_binds_actor_and_explicit_corrections(self):
        corrections = [{'unique_key': 'digital:123', 'expected_version': 2}]
        status, payload = self.route('POST', '/api/tax-offset/certified-import/confirm', {'session_id': 'session-1', 'actor_id': 'spoof', 'corrections': corrections})
        self.assertEqual(status, HTTPStatus.ACCEPTED)
        self.assertEqual(payload['status'], 'queued')
        self.assertEqual(payload['import_job']['import_job_id'], 'job-1')
        self.jobs.validate_session_owner.assert_called_once_with('session-1', owner_user_id='tax-user')
        args = self.queue.call_args.kwargs
        self.assertEqual(args['created_by'], 'tax-user')
        self.assertEqual(args['idempotency_key'], 'tax_certified_import.confirm:session-1')
        self.assertEqual(args['payload']['corrections'], corrections)

    def test_confirmation_rejects_invalid_or_duplicate_corrections(self):
        for corrections in ({}, [{'unique_key': 'x', 'expected_version': True}], [{'unique_key': 'x', 'expected_version': 0}], [{'unique_key': 'x', 'expected_version': 1}] * 2):
            status, payload = self.route('POST', '/api/tax-offset/certified-import/confirm', {'session_id': 'session-1', 'corrections': corrections})
            self.assertEqual(status, HTTPStatus.BAD_REQUEST)
            self.assertEqual(payload['error'], 'invalid_tax_certified_corrections')
        self.queue.assert_not_called()

    def test_confirmation_rejects_other_owner_and_queue_unavailability(self):
        self.jobs.validate_session_owner.side_effect = KeyError('session-1')
        self.assertEqual(self.route('POST', '/api/tax-offset/certified-import/confirm', {'session_id': 'session-1'})[0], HTTPStatus.NOT_FOUND)
        self.queue.assert_not_called()
        self.jobs.validate_session_owner.side_effect = None
        self.queue.side_effect = RuntimeError('queue unavailable')
        status, payload = self.route('POST', '/api/tax-offset/certified-import/confirm', {'session_id': 'session-1'})
        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertNotIn('import_job', payload)

    def test_revocation_checks_version_and_uses_session_actor(self):
        status, payload = self.route('POST', '/api/tax-offset/certified-imports/batch-1/revoke', {'expected_version': 1, 'actor_id': 'spoof'})
        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual(payload['status'], 'revoked')
        self.revoke.assert_called_once_with(batch_id='batch-1', actor_id='tax-user', expected_version=1)
        self.revoke.side_effect = ValueError('批次已变化。')
        status, payload = self.route('POST', '/api/tax-offset/certified-imports/batch-1/revoke', {'expected_version': 1})
        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload['error'], 'tax_certified_batch_conflict')

    def test_confirmation_payload_conflict_requires_new_preview(self):
        self.queue.side_effect = ImportJobIdempotencyConflict('different request')
        status, payload = self.route('POST', '/api/tax-offset/certified-import/confirm', {'session_id': 'session-1'})
        self.assertEqual(status, HTTPStatus.CONFLICT)
        self.assertEqual(payload['error'], 'tax_certified_import_confirmation_conflict')
        self.assertNotIn('import_job', payload)

    def test_revocation_cannot_change_another_users_batch(self):
        self.revoke.side_effect = PermissionError('只能撤销本人导入的批次。')
        status, payload = self.route('POST', '/api/tax-offset/certified-imports/batch-1/revoke', {'expected_version': 1})
        self.assertEqual(status, HTTPStatus.FORBIDDEN)
        self.assertEqual(payload['error'], 'tax_certified_batch_forbidden')

    def test_mutations_enforce_permission_before_side_effect(self):
        denied = (HTTPStatus.FORBIDDEN, {'error': 'page_access_denied'})
        self.routes._resolve_mutation_session = lambda headers: (None, denied)
        for path in ['/api/tax-offset/certified-import/preview', '/api/tax-offset/certified-import/confirm', '/api/tax-offset/certified-imports/batch-1/revoke']:
            self.assertEqual(self.route('POST', path, {'expected_version': 1, 'session_id': 'session-1'}), denied)
        self.preview.assert_not_called()
        self.queue.assert_not_called()
        self.revoke.assert_not_called()

    def test_job_payload_is_private_to_owner_and_type(self):
        repo = Mock()
        repo.get_job.return_value = SimpleNamespace(import_type='tax_certified_import.confirm', created_by='another-user')
        service = TaxCertifiedImportJobService(import_job_repository_provider=lambda: repo)
        with self.assertRaises(KeyError):
            service.get_confirm_job_payload('job-1', owner_user_id='tax-user')
