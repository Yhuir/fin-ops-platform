import unittest
from copy import deepcopy

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.cost_statistics_manual_items import validate_manual_items


class ManualCostItemsTests(unittest.TestCase):
    def setUp(self):
        self.options={'projects':[{'id':'p','name':'项目甲'}], 'tags':[{'code':'t','primary_label':'费用','sub_label':'服务费'}]}
        self.item={'unit_id':'manual:00000000-0000-4000-8000-000000000001','project_name':'项目甲','expense_content':' 服务费 ','cost_tag_code':'t'}

    def test_metadata_does_not_accept_or_fabricate_oa_bank_or_amount_fields(self):
        result=validate_manual_items([self.item],self.options,[])
        self.assertEqual(result[0]['expense_content'],'服务费')
        self.assertEqual(result[0]['project_name'],'项目甲')
        for key in ('oa_id','bank_tag_code','amount','project_id'):
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manual_items([{**self.item,key:'invented'}],self.options,[])

    def test_empty_duplicate_invalid_and_stopped_catalogue_choices(self):
        self.assertEqual(validate_manual_items([],self.options,[]),[])
        for items in (None,{},[self.item]*201,[self.item,self.item]):
            with self.subTest(items_type=type(items)),self.assertRaises(ValueError):
                validate_manual_items(items,self.options,[])
        saved=validate_manual_items([self.item],self.options,[])
        # Previously saved selections can be retained, but never selected for a new item.
        self.assertEqual(validate_manual_items([self.item],{'projects':[],'tags':[]},saved),saved)
        changed=deepcopy(self.item);changed['unit_id']='manual:00000000-0000-4000-8000-000000000002'
        with self.assertRaises(ValueError): validate_manual_items([changed],{'projects':[],'tags':[]},saved)
        for field,value in [('project_name','unknown'),('cost_tag_code','unknown'),('expense_content',' '*2),('expense_content','长'*501),('project_name',1)]:
            with self.subTest(field=field,value=str(value)[:10]),self.assertRaises(ValueError):
                validate_manual_items([{**self.item,field:value}],self.options,[])

    def test_project_catalogue_keeps_completed_projects_for_historical_costs(self):
        options = AppSettingsService.cost_manual_options_from_settings(
            {"manual_projects": [{"id": "p", "project_name": "已竣工项目", "project_status": "completed"}]},
            [{"id": "p", "name": "旧名称"}, {"id": "oa-only", "name": "OA项目"}],
        )
        self.assertEqual({p["id"]: p["name"] for p in options["projects"]}, {"p": "已竣工项目", "oa-only": "OA项目"})

    def test_named_canonical_project_needs_no_invented_project_id(self):
        options = {**self.options, "projects": [{"id": "", "name": "项目甲"}]}
        saved = validate_manual_items([self.item], options, [])
        self.assertEqual(saved[0]["project_id"], "")
        self.assertEqual(saved[0]["project_name"], "项目甲")

    def test_manual_catalogue_uses_bank_active_rules_not_internal_path_or_legacy_definitions(self):
        from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
        definitions = [
            {"code": "salary-test", "label": "工资", "path": ["自动识别", "工资"], "output_primary_label": "薪资社保福利", "output_sub_label": "工资", "rules": {}, "status": "active"},
            {"code": "slash-test", "label": "运费/邮费/杂费", "output_primary_label": "费用", "output_sub_label": "运费/邮费/杂费", "rules": {}, "status": "active"},
            {"code": "single-test", "label": "单层", "output_primary_label": "单层", "output_sub_label": "", "rules": {}, "status": "active"},
            {"code": "legacy-test", "label": "旧定义", "status": "active"},
            {"code": "archived-test", "label": "停用", "rules": {}, "status": "archived"},
        ]
        settings = {"bank_transaction_tags": {"definitions": definitions}}
        before = deepcopy(settings)
        tags = AppSettingsService.cost_manual_tags_from_settings(settings)
        by_code = {tag['code']: tag for tag in tags}
        expected = BankTransactionCategoryService.auto_tag_rules_payload(settings['bank_transaction_tags'])
        self.assertEqual(set(by_code), {r['code'] for r in expected['active_rules']} | {'internal_transfer'})
        self.assertEqual(by_code['salary-test']['label'], '薪资社保福利 / 工资')
        self.assertEqual(by_code['slash-test']['sub_label'], '运费/邮费/杂费')
        self.assertEqual(by_code['single-test']['sub_label'], '')
        self.assertEqual(by_code['internal_transfer']['sub_label'], '')
        self.assertEqual(settings, before)

    def test_tag_route_respects_read_permission_and_only_returns_catalogue(self):
        from http import HTTPStatus
        from unittest.mock import Mock
        from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
        settings = Mock()
        settings.get_cost_manual_tags.side_effect = [{'tags': []}, {'tags': self.options['tags']}]
        session = Mock()
        route = CostStatisticsApiRoutes(query_service=Mock(), json_response=lambda status, body: (status, body),
            file_response=Mock(), app_settings_service=settings, resolve_read_session=lambda headers: (session, None))
        for expected in ([], self.options['tags']):
            status, body = route.route('GET', '/api/cost-statistics/manual-tags', {})
            self.assertEqual(status, HTTPStatus.OK)
            self.assertEqual(body, {'tags': expected})
        route._resolve_read_session = lambda headers: (None, (HTTPStatus.FORBIDDEN, {'error':'forbidden'}))
        self.assertEqual(route.route('GET', '/api/cost-statistics/manual-tags', {}), (HTTPStatus.FORBIDDEN, {'error':'forbidden'}))
        self.assertEqual(settings.get_cost_manual_tags.call_count, 2)


class OaCostTagsTests(unittest.TestCase):
    def test_explicit_tags_are_source_owned_and_never_guessed(self):
        from fin_ops_platform.services.cost_statistics_oa_cost_tags import validate_oa_cost_tags
        row={'unit_id':'oa','bank_transaction_id':'bank','cost_tag_code':'interest'}
        args={'units':[{'unit_id':'oa'}], 'cost_lines':[{'unit_id':'oa','bank_transaction_id':'bank','amount':'1497.22'}],
              'tags':[{'code':'interest','primary_label':'费用','sub_label':'利息'}], 'previous':[]}
        self.assertEqual(validate_oa_cost_tags([],**args),[])
        saved=validate_oa_cost_tags([row],**args)
        self.assertEqual(saved,[{**row,'cost_tag_primary_label':'费用','cost_tag_sub_label':'利息'}])
        # Explicit same-code choice remains a decision even after catalogue changes.
        self.assertEqual(validate_oa_cost_tags([row],**{**args,'tags':[],'previous':saved}),saved)
        for value in (None,{},[row,row],[{**row,'cost_tag_code':'unknown'}],[{**row,'unit_id':'manual:foreign'}],
                      [{**row,'bank_transaction_id':'outside'}],[{**row,'cost_tag_code':None}],[{**row,'amount':'0'}]):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_oa_cost_tags(value,**args)
        with self.assertRaises(ValueError):validate_oa_cost_tags([row],**{**args,'cost_lines':[]})
        self.assertEqual(args['previous'],[])
