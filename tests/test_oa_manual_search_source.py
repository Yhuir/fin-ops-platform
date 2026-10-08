from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, MongoOASettings, OASearchUnavailable
from fin_ops_platform.services.oa_manual_search_source import OAManualSearchSource
from fin_ops_platform.services.oa_source_identity import OASourceIdentities
from pymongo.errors import ExecutionTimeout

from tests.app_test_support import build_local_state_application


def document(doc_id='old', day='2025-12-31T12:30:00', status='2'):
    return {'_id': doc_id, 'form_id': '32', 'data': {
        'ApplicationDate': day, 'Reimbursement Personnel': '胡瑢', 'processStatus': status,
        'schedule': [{'detailReimbursementAmount': '25.00', 'feeContent': '交通费',
                      'detailReimbursementAttachment': {'files': [
                          {'fileName': 'a.pdf', 'filePath': '/a.pdf'},
                          {'fileName': 'b.pdf', 'filePath': '/b.pdf'}]}}]}}


class ManualOASearchSourceTests(unittest.TestCase):
    def test_runtime_assembly_searches_source_even_when_local_scope_starts_in_2026(self):
        settings = MongoOASettings(host='fixture', database='fixture')
        with tempfile.TemporaryDirectory() as directory, patch(
            'fin_ops_platform.services.oa_manual_search_source.load_mongo_oa_settings', return_value=settings
        ):
            app = build_local_state_application(data_dir=Path(directory))
            self.addCleanup(app.close)
            self.assertIsInstance(app._oa_manual_import_service._oa_adapter, OAManualSearchSource)
            app._app_settings_service.update_settings(bank_account_mappings=[], oa_retention={'cutoff_date':'2026-01-01'})
            collection = MagicMock()
            collection.find.return_value = []
            collection.aggregate.return_value = [{'count':[{'total':1}], 'rows':[document()]}]
            with patch.object(MongoOAAdapter, '_collection', return_value=collection), patch(
                'fin_ops_platform.services.oa_manual_search_source.MongoClient'
            ), patch('fin_ops_platform.services.oa_manual_search_source.PostgresOASourceIdentityRepository') as identities, patch(
                'fin_ops_platform.services.oa_manual_search_source.PostgresOpsTaxEtcRepository'
            ) as cache:
                identities.return_value.load_identities.return_value = OASourceIdentities()
                cache.return_value.load_oa_attachment_invoice_cache_entries.return_value = {}
                cache.return_value.load_oa_search_import_states.return_value = {"oa-exp-old": {"import_status":"not_imported", "imported_at":None}}
                response = app.handle_request('GET', '/api/workbench/settings/oa/manual-search?q=%E8%83%A1&date_from=2025-01-01&date_to=2025-12-31')
                self.assertEqual(response.status_code, 200)
                payload = json.loads(response.body)
                self.assertEqual(payload['total'], 1)
                self.assertEqual(payload['rows'][0]['row_id'], 'oa-exp-old')
                self.assertTrue(payload['rows'][0]['can_import'])
                self.assertEqual(payload['rows'][0]['application_date'], '2025-12-31T12:30:00')
                self.assertEqual(payload['rows'][0]['attachment_file_count'], 2)
                self.assertEqual(payload['rows'][0]['unrecognized_attachment_count'], 0)
                self.assertEqual(payload['rows'][0]['pending_attachment_count'], 2)
                self.assertEqual(payload['rows'][0]['attachment_status'], 'unparsed')
                cache.return_value.load_oa_attachment_invoice_cache_entries.assert_called_once()
                cache.return_value.load_oa_attachment_invoice_cache_entry.assert_not_called()
                cache.return_value.save_oa_attachment_invoice_cache_entry.assert_not_called()
                query = collection.aggregate.call_args.args[0]
                self.assertIn('2025-01-01', str(query))
                self.assertIn('2026-01-01', str(query))  # exclusive end of the last day

    def test_source_pool_is_reused_but_request_adapter_state_is_not_shared(self):
        source = OAManualSearchSource(settings=MongoOASettings(host='fixture', database='fixture'), connection=object())
        with patch('fin_ops_platform.services.oa_manual_search_source.MongoClient') as client, patch(
            'fin_ops_platform.services.oa_manual_search_source.MongoOAAdapter'
        ) as adapter:
            adapter.return_value.search_application_record_rows.return_value = {'rows':[], 'total':0}
            source.search_application_record_rows(q='one')
            source.search_application_record_rows(q='two')
            client.assert_called_once()
            self.assertEqual(adapter.call_count, 2)
            source.close()
            client.return_value.close.assert_called_once()

    def test_search_optional_filters_do_not_become_literal_none(self):
        adapter = MongoOAAdapter(settings=MongoOASettings(host='fixture', database='fixture'))
        collection = MagicMock()
        collection.find.return_value = []
        collection.aggregate.return_value = [{'count':[{'total':1}], 'rows':[document(status='1')]}]
        with patch.object(adapter, '_collection', return_value=collection):
            for date_from, date_to, expected_bounds in (
                (None, None, None),
                ('2025-01-01', None, {'$gte':'2025-01-01'}),
                (None, '2025-12-31', {'$lt':'2026-01-01'}),
            ):
                with self.subTest(date_from=date_from, date_to=date_to):
                    payload = adapter.search_application_record_rows(statuses=['in_progress'],
                        date_from=date_from, date_to=date_to)
                    self.assertEqual(payload['total'], 1)
                    self.assertEqual(payload['rows'][0]['status'], 'in_progress')
                    self.assertFalse(payload['rows'][0]['can_import'])
                    match = collection.aggregate.call_args.args[0][0]['$match']
                    self.assertNotIn('None', str(match))
                    self.assertNotIn('$regex', str(match))
                    if expected_bounds is None:
                        self.assertNotIn('applicationDate', str(match))
                    else:
                        self.assertIn({'$or':[{'data.applicationDate':expected_bounds},
                            {'data.ApplicationDate':expected_bounds}]}, match['$or'][0]['$and'])

    def test_missing_configuration_fails_explicitly(self):
        with self.assertRaises(OASearchUnavailable):
            OAManualSearchSource(settings=None, connection=None).search_application_record_rows()

    def test_count_and_combined_page_share_one_bounded_aggregate(self):
        adapter = MongoOAAdapter(settings=MongoOASettings(host='fixture', database='fixture'))
        collection = MagicMock()
        collection.aggregate.return_value = [{'count':[{'total':42}], 'rows':[document()]}]
        with patch.object(adapter, '_collection', return_value=collection):
            rows, total = adapter._search_documents_page([{'form_id':'2'}, {'form_id':'32'}], 2, 20)
        self.assertEqual(total, 42)
        self.assertEqual(rows, [document()])
        pipeline = collection.aggregate.call_args.args[0]
        page = pipeline[-1]['$facet']['rows']
        self.assertIn({'$skip':40}, page)
        self.assertIn({'$limit':20}, page)
        self.assertEqual(collection.aggregate.call_args.kwargs['maxTimeMS'], 5000)
        collection.find.assert_not_called()

    def test_source_timeout_does_not_return_empty_results(self):
        adapter = MongoOAAdapter(settings=MongoOASettings(host='fixture', database='fixture'))
        collection = MagicMock()
        collection.aggregate.side_effect = ExecutionTimeout('fixture timeout')
        with patch.object(adapter, '_collection', return_value=collection), self.assertRaises(OASearchUnavailable):
            adapter._search_documents_page([{'form_id':'32'}], 0, 20)

    def test_api_maps_source_failure_and_rejects_invalid_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            app = build_local_state_application(data_dir=Path(directory))
            self.addCleanup(app.close)
            with patch.object(app._oa_manual_search_source, 'search_application_record_rows', side_effect=OASearchUnavailable('源库不可用')) as source:
                for suffix in ('date_from=2025-02-30', 'date_from=2026-01-01&date_to=2025-12-31'):
                    response = app.handle_request('GET', '/api/workbench/settings/oa/manual-search?'+suffix)
                    self.assertEqual(response.status_code, 400)
                    self.assertEqual(json.loads(response.body)['error'], 'invalid_oa_manual_search_request')
                source.assert_not_called()
                response = app.handle_request('GET', '/api/workbench/settings/oa/manual-search?q=old')
                self.assertEqual(response.status_code, 503)
                payload = json.loads(response.body)
                self.assertEqual(payload['error'], 'oa_search_unavailable')
                self.assertEqual(payload['message'], '源库不可用')
                self.assertNotIn('rows', payload)
