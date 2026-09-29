from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fin_ops_platform.app.routes_bank_transaction_splits import BankTransactionSplitApiRoutes
from fin_ops_platform.services.bank_transaction_category_service import default_bank_transaction_tag_dictionary_payload
from fin_ops_platform.services.bank_transaction_split_service import (
    BankTransactionSplitError,
    normalize_split_category,
    validate_split_parts,
)
from fin_ops_platform.services.postgres_repositories.bank_transaction_splits import (
    PostgresBankTransactionSplitRepository,
)

DEFINITIONS = [{"code": "principal", "label": "本金", "path": ["本金"], "status": "active"}, {"code": "interest", "label": "利息", "path": ["费用", "利息"], "status": "active"}]


class SplitTagDisplayTests(unittest.TestCase):
    def test_default_dictionary_supports_flat_and_hierarchical_tags(self):
        dictionary = default_bank_transaction_tag_dictionary_payload()
        tags = PostgresBankTransactionSplitRepository.tag_definitions(dictionary)
        by_code = {tag["code"]: tag for tag in tags}
        self.assertEqual(len(tags), len(dictionary["definitions"]))
        for definition in dictionary["definitions"]:
            tag = by_code[definition["code"]]
            self.assertTrue(tag["primary_label"])
            if not definition["path"] and not definition.get("output_primary_label"):
                self.assertEqual(tag["path"], [definition["label"]])
                self.assertEqual(tag["primary_label"], definition["label"])
                self.assertEqual(tag["sub_label"], "")
                part = PostgresBankTransactionSplitRepository.decorate_parts(
                    [{"id": "part", "category_code": tag["code"], "amount": Decimal("1.00")}], tags,
                )[0]
                self.assertEqual(part["category_path"], [definition["label"]])


class SplitValidationTests(unittest.TestCase):
    def validate(self, parts, *, current=None, category=None):
        return validate_split_parts({"parts": parts, "category_code": category}, amount=Decimal("1001497.22"), current_parts=current or [], definitions=DEFINITIONS)

    def test_exact_money_and_stable_same_category_members(self):
        first = str(uuid4())
        second = str(uuid4())
        parts = [{"id": first, "category_code": "interest", "amount": "1000000.00"}, {"id": second, "category_code": "interest", "amount": "1497.22"}]
        result = self.validate(parts, current=parts)
        self.assertEqual([item["id"] for item in result], [first, second])
        self.assertEqual(sum(Decimal(item["amount"]) for item in result), Decimal("1001497.22"))

    def test_rejects_invalid_money_without_inference(self):
        for amount in (0, "0", "-1.00", "1.001", "NaN", "Infinity", "oops", "1e100", "1497.21"):
            with self.subTest(amount=amount), self.assertRaises(BankTransactionSplitError):
                self.validate([{"category_code": "principal", "amount": "1000000.00"}, {"category_code": "interest", "amount": amount}])

    def test_rejects_unknown_archived_foreign_and_duplicate_identities(self):
        own = str(uuid4())
        current = [{"id": own}]
        for second in (
            {"category_code": "missing", "amount": "1497.22"},
            {"category_code": "interest", "amount": "1497.22", "id": str(uuid4())},
            {"category_code": "interest", "amount": "1497.22", "id": own},
        ):
            with self.subTest(second=second), self.assertRaises(BankTransactionSplitError):
                self.validate([{"id": own, "category_code": "principal", "amount": "1000000.00"}, second], current=current)

    def test_clear_requires_explicit_whole_transaction_category(self):
        with self.assertRaises(BankTransactionSplitError):
            self.validate([], current=[{"id": str(uuid4())}])
        self.assertEqual(self.validate([], current=[{"id": str(uuid4())}], category="principal"), [])
        self.assertEqual(self.validate([]), [])

    def test_rejects_single_part_and_non_array(self):
        for value in (None, {}, [{"category_code": "principal", "amount": "1001497.22"}]):
            with self.subTest(value=value), self.assertRaises(BankTransactionSplitError):
                self.validate(value)


class SplitClassificationTests(unittest.TestCase):
    definition = {"code": "custom", "status": "active", "label": "归还借款", "path": ["外部往来款付款", "归还借款"],
                  "output_primary_label": "外部往来款付款", "output_sub_label": "归还借款",
                  "turnover_role": "external_turnover", "turnover_action_type": "repaid"}

    def test_complete_instance_derives_family_without_definition_third(self):
        selection = {"category_label_path": ["外部往来款付款", "归还借款", "银行往来"]}
        result = normalize_split_category(selection, self.definition)
        self.assertEqual(result["turnover_family"], "bank")
        self.assertEqual(result["category_third_label"], "银行往来")
        self.assertEqual(result["turnover_action_type"], "repaid")
        self.assertNotIn("output_third_label", self.definition)

    def test_invalid_or_contradictory_instance_never_guesses(self):
        for selection in ({}, {"category_label_path": ["外部往来款付款", "归还借款", "陌生往来"]},
                          {"category_label_path": ["费用", "利息", "银行往来"]},
                          {"category_label_path": ["外部往来款付款", "归还借款", "银行往来"], "turnover_family": "company"},
                          {"category_label_path": ["外部往来款付款", "归还借款", "银行往来"], "turnover_action_type": "collected"}):
            with self.subTest(selection=selection), self.assertRaises(BankTransactionSplitError):
                normalize_split_category(selection, self.definition)
        with self.assertRaises(BankTransactionSplitError):
            normalize_split_category({"category_label_path": ["费用", "利息", "银行往来"]}, DEFINITIONS[1])
        with self.assertRaises(BankTransactionSplitError):
            normalize_split_category({"turnover_family": "bank"}, DEFINITIONS[1])


class SplitRouteTests(unittest.TestCase):
    def route(self, service, *, session=True):
        return BankTransactionSplitApiRoutes(
            service=service,
            resolve_session=lambda _headers: (SimpleNamespace(identity=SimpleNamespace(username="actor", user_id="id")) if session else None, None),
            load_json_body=lambda body: (body, None),
            json_response=lambda status, payload: (status, payload),
        )

    def test_read_and_write_return_committed_contract_and_session_actor(self):
        calls = []
        expected = {"transaction_id": "txn", "version": 1, "parts": [], "amount": "1.00"}
        service = SimpleNamespace(read=lambda ident: expected, save=lambda ident, payload, **kwargs: calls.append((ident, payload, kwargs)) or expected)
        route = self.route(service)
        status, payload = route.route("GET", "/api/bank-transactions/txn/splits", None, {})
        self.assertEqual(status, 200)
        self.assertEqual(payload, {**expected, "can_edit": True})
        route.route("PUT", "/api/bank-transactions/txn/splits", {"version": 0, "parts": [], "actor_id": "forged"}, {})
        self.assertEqual(calls[0][2], {"actor_id": "actor"})

    def test_unauthenticated_and_version_conflict_are_not_success(self):
        status, payload = self.route(SimpleNamespace(), session=False).route("GET", "/api/bank-transactions/txn/splits", None, {})
        self.assertEqual(status, 401)
        self.assertEqual(payload["error"], "authentication_required")
        def conflict(*_args, **_kwargs):
            raise BankTransactionSplitError("split_version_conflict", "changed", status=409)
        status, payload = self.route(SimpleNamespace(save=conflict)).route("PUT", "/api/bank-transactions/txn/splits", {}, {})
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "split_version_conflict")

    def test_batch_read_returns_each_detail_and_never_writes(self):
        calls = []
        expected = {"transaction_id": "parent", "version": 4, "parts": [], "amount": "1.00"}
        service = SimpleNamespace(read_many=lambda payload: calls.append(payload) or {"rows": [expected, expected]})
        status, response = self.route(service).route("POST", "/api/bank-transactions/splits/query", {"transaction_ids": ["child1", "child2"]}, {})
        self.assertEqual(status, 200)
        self.assertEqual(response, {"rows": [{**expected, "can_edit": True}] * 2})
        self.assertEqual(calls, [{"transaction_ids": ["child1", "child2"]}])


class SplitDrawerProjectionTests(unittest.TestCase):
    def test_related_child_sections_have_one_parent_editor_and_original_amount(self):
        from fin_ops_platform.services.input_invoice_usage_service import source_relation_sections as invoice_sections
        from fin_ops_platform.services.oa_pending_payment_details import source_relation_sections as oa_sections
        rows = [{"bankTransactionId":child,"parent_row_id":"parent","parent_amount":"1001497.22",
                 "amount":amount,"direction":"outflow","bank_split_parts":[{"id":"a"},{"id":"b"}]}
                for child,amount in [("a","1000000.00"),("b","1497.22")]]
        for build in (invoice_sections,oa_sections):
            from fin_ops_platform.domain.enums import TransactionDirection
            from fin_ops_platform.domain.models import BankTransaction
            parent = BankTransaction(id='parent', account_no='1234', counterparty_name_raw='原始对方',
                txn_direction=TransactionDirection.OUTFLOW, amount=Decimal('1001497.22'), signed_amount=Decimal('-1001497.22'))
            sections=build('bank',rows, groups=[], transactions=[parent], oa_records=[])
            self.assertEqual({section['document_id'] for section in sections}, {'parent'})
            self.assertEqual(sections[0]['bank_transaction_id'],'parent')
            self.assertEqual(next(field['value'] for field in sections[0]['fields'] if field['label']=='支出金额'),'1001497.22')


class SplitSelectableTagsTests(unittest.TestCase):
    def test_formal_rules_only_and_explicit_system_label(self):
        from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
        dictionary = default_bank_transaction_tag_dictionary_payload()
        dictionary['definitions'] += [
            {'code': 'formal_z', 'label': '费用 / 利息', 'path': ['费用', '利息'], 'source': 'custom', 'status': 'active', 'rules': {}, 'priority': 2, 'sort_order': 2, 'output_primary_label': '费用', 'output_sub_label': '利息'},
            {'code': 'formal_a', 'label': '采购 / 设备', 'path': ['采购', '设备'], 'source': 'custom', 'status': 'active', 'rules': {}, 'priority': 2, 'sort_order': 1, 'output_primary_label': '采购', 'output_sub_label': '设备'},
            {'code': 'not_a_rule', 'label': '旧标签', 'path': ['旧标签'], 'source': 'custom', 'status': 'active'},
            {'code': 'archived_rule', 'label': '旧费用', 'path': ['旧费用'], 'source': 'custom', 'status': 'archived', 'rules': {}},
        ]
        selected = BankTransactionCategoryService.selectable_tag_dictionary(dictionary)
        tags = PostgresBankTransactionSplitRepository.tag_definitions(selected)
        codes = [tag['code'] for tag in tags]
        self.assertNotIn('borrow_in_bank_pending_repayment', codes)
        self.assertNotIn('not_a_rule', codes)
        self.assertNotIn('archived_rule', codes)
        self.assertLess(codes.index('formal_a'), codes.index('formal_z'))
        self.assertEqual(next(tag['path'] for tag in tags if tag['code'] == 'internal_transfer'), ['内部往来款'])
        self.assertNotIn('rules', tags[0])

    def test_history_can_be_preserved_but_not_created_changed_or_forged(self):
        from fin_ops_platform.services.bank_transaction_split_service import SPLIT_CATEGORY_FIELDS
        old_id = str(uuid4())
        old = {'id': old_id, 'category_code': 'retired', 'amount': '2.00',
               **normalize_split_category({}, {'code': 'retired', 'label': '旧类', 'path': ['旧类']})}
        request = {'id': old_id, 'category_code': 'retired', 'amount': '2.00', 'category_label_path': ['旧类']}
        fee = {'category_code': 'interest', 'amount': '1.00'}
        def validate(part):
            return validate_split_parts({'parts': [part, fee]}, amount=Decimal('3.00'), current_parts=[old], definitions=DEFINITIONS)
        self.assertEqual(validate(request)[0]['category_payload'], {key: old[key] for key in SPLIT_CATEGORY_FIELDS})
        for patch in ({'id': None}, {'id': str(uuid4())}, {'amount': '1.00'}, {'category_label_path': ['猜测']}, {'turnover_family': 'bank'}):
            with self.subTest(patch=patch), self.assertRaises(BankTransactionSplitError):
                validate({**request, **patch})
