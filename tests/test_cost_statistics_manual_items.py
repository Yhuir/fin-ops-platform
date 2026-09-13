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
