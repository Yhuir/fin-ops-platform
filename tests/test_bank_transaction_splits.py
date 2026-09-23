from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from fin_ops_platform.app.routes_bank_transaction_splits import BankTransactionSplitApiRoutes
from fin_ops_platform.services.bank_transaction_category_service import default_bank_transaction_tag_dictionary_payload
from fin_ops_platform.services.bank_transaction_split_service import BankTransactionSplitError, validate_split_parts
from fin_ops_platform.services.postgres_repositories.bank_transaction_splits import (
    PostgresBankTransactionSplitRepository,
)

DEFINITIONS = [{"code": "principal", "status": "active"}, {"code": "interest", "status": "active"}]


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
        from fin_ops_platform.services.input_invoice_usage_service import _relation_detail_sections as invoice_sections
        from fin_ops_platform.services.oa_pending_payment_details import _relation_detail_sections as oa_sections
        rows = [{"bankTransactionId":child,"parent_row_id":"parent","parent_amount":"1001497.22",
                 "amount":amount,"direction":"outflow","bank_split_parts":[{"id":"a"},{"id":"b"}]}
                for child,amount in [("a","1000000.00"),("b","1497.22")]]
        for build in (invoice_sections,oa_sections):
            sections=build('bank',rows)
            self.assertEqual(len(sections),1)
            self.assertEqual(sections[0]['bank_transaction_id'],'parent')
            self.assertEqual(next(field['value'] for field in sections[0]['fields'] if field['label']=='金额'),'1001497.22')
