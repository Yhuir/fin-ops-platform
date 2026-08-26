import unittest

from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService


class WorkbenchAmountCheckServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchAmountCheckService()

    def test_flags_only_isolated_oa_total_when_bank_and_invoice_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [self._invoice_row("90")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], ["oa_total"])

    def test_flags_only_isolated_invoice_total_when_oa_and_bank_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [self._invoice_row("90")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], ["invoice_total"])

    def test_flags_both_comparable_totals_when_invoice_missing(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(result["mismatch_fields"], ["oa_total", "bank_total"])

    def test_etc_batch_oa_bank_mismatch_without_invoice_requires_note(self) -> None:
        oa_row = self._oa_row("100")
        oa_row["source"] = "etc_batch"
        oa_row["etc_batch_id"] = "etc_20260503_001"

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("90")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(result["mismatch_fields"], ["oa_total", "bank_total"])

    def test_flags_all_totals_when_three_amounts_all_differ(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("90")],
                "invoice": [self._invoice_row("80")],
            }
        )

        self.assertEqual(result["status"], "mismatch")
        self.assertTrue(result["requires_note"])
        self.assertCountEqual(
            result["mismatch_fields"],
            ["oa_total", "bank_total", "invoice_total"],
        )

    def test_matched_when_all_three_totals_match(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [self._invoice_row("100")],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], [])
        self.assertEqual(result["oa_total"], "100.00")
        self.assertEqual(result["bank_total"], "100.00")
        self.assertEqual(result["invoice_total"], "100.00")

    def test_unknown_invoice_type_is_not_defaulted_to_payment_direction(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [
                    {
                        "type": "invoice",
                        "id": "inv-unknown",
                        "invoice_type": "电子普通发票",
                        "total_with_tax": "100",
                    }
                ],
            }
        )

        self.assertEqual(result["status"], "unknown")
        self.assertTrue(result["requires_note"])
        self.assertEqual(result["invoice_total"], "100.00")

    def test_missing_total_remains_null_when_persistable(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("100")],
                "bank": [self._bank_row("100")],
                "invoice": [],
            }
        )

        self.assertEqual(result["oa_total"], "100.00")
        self.assertEqual(result["bank_total"], "100.00")
        self.assertIsNone(result["invoice_total"])

    def test_payment_relation_nets_refund_receipts_inside_the_same_relation(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("1015")],
                "bank": [
                    self._bank_row("1050"),
                    self._bank_income_row("35"),
                ],
                "invoice": [self._invoice_row("1015")],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["direction"], "payment")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["mismatch_fields"], [])
        self.assertEqual(result["oa_total"], "1015.00")
        self.assertEqual(result["bank_total"], "1015.00")
        self.assertEqual(result["invoice_total"], "1015.00")
        self.assertEqual(result["bank_gross_total"], "1050.00")
        self.assertEqual(result["bank_contra_total"], "35.00")
        self.assertEqual(result["bank_net_total"], "1015.00")
        self.assertEqual(result["oa_amount"], "1015.00")
        self.assertEqual(result["bank_amount"], "1015.00")
        self.assertEqual(result["amount_delta"], "0.00")

        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{**self._oa_row("1015"), "id": "oa-1015"}],
                    "bank": [
                        {**self._bank_row("1050"), "id": "bank-payment-1050"},
                        {**self._bank_income_row("35"), "id": "bank-refund-35"},
                    ],
                    "invoice": [
                        {**self._invoice_row(amount), "id": f"invoice-{index}"}
                        for index, amount in enumerate(("240", "710", "18", "35", "12"))
                    ],
                },
                relation_id="CASE-NET-1015",
            )
        )

    def test_turnover_manual_closure_compares_oa_with_same_direction_bank_leg(self) -> None:
        rows = {
            "oa": [{**self._oa_row("240000"), "id": "oa-240000"}],
            "bank": [
                {**self._bank_row("240000"), "id": "bank-payment-240000"},
                {**self._bank_income_row("240000"), "id": "bank-income-240000"},
            ],
            "invoice": [],
        }

        result = self.service.check(rows, relation_mode="turnover_manual_closure")

        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["bank_total"], "240000.00")
        self.assertEqual(result["bank_gross_total"], "240000.00")
        self.assertEqual(result["bank_contra_total"], "240000.00")
        self.assertEqual(result["bank_net_total"], "0.00")
        self.assertIsNone(
            self.service.workbench_anomaly(
                rows,
                relation_id="CASE-TURNOVER-240000",
                relation_mode="turnover_manual_closure",
            )
        )

    def test_turnover_manual_closure_still_reports_real_oa_bank_difference(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{**self._oa_row("230000"), "id": "oa-230000"}],
                "bank": [
                    {**self._bank_row("240000"), "id": "bank-payment-240000"},
                    {**self._bank_income_row("240000"), "id": "bank-income-240000"},
                ],
                "invoice": [{**self._invoice_row("240000"), "id": "invoice-240000"}],
            },
            relation_id="CASE-TURNOVER-MISMATCH",
            relation_mode="turnover_manual_closure",
        )

        assert anomaly is not None
        mismatch = anomaly["items"][0]
        self.assertEqual(mismatch["code"], "bank_invoice_equal_oa_less")
        self.assertEqual(mismatch["oa_total"], "230000.00")
        self.assertEqual(mismatch["bank_total"], "240000.00")

    def test_oa_reconciliation_amount_overrides_header_amount_for_preview_check(self) -> None:
        result = self.service.check(
            {
                "oa": [self._oa_row("2308.02", reconciliation_amount="2038.02")],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_explicit_reconciliation_amount_wins_over_legacy_detail_mismatch_fields(self) -> None:
        oa_row = self._oa_row("2308.02", reconciliation_amount="2038.02")
        oa_row["detail_fields"] = {
            "金额来源": "主表总金额",
            "明细金额合计": "1999.99",
            "金额差异": "主表总金额 2308.02；明细合计 1999.99；差异 308.03",
        }

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_legacy_oa_detail_sum_is_used_when_header_amount_has_recorded_mismatch(self) -> None:
        oa_row = self._oa_row("2308.02")
        oa_row["detail_fields"] = {
            "金额来源": "主表总金额",
            "明细金额合计": "2038.02",
            "金额差异": "主表总金额 2308.02；明细合计 2038.02；差异 270.00",
        }

        result = self.service.check(
            {
                "oa": [oa_row],
                "bank": [self._bank_row("2038.02")],
                "invoice": [],
            }
        )

        self.assertEqual(result["status"], "matched")
        self.assertFalse(result["requires_note"])
        self.assertEqual(result["oa_total"], "2038.02")
        self.assertEqual(result["bank_total"], "2038.02")
        self.assertEqual(result["amount_delta"], "0.00")

    def test_workbench_anomaly_uses_exact_cent_oa_invoice_totals_across_all_rows(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{**self._oa_row("1079.87"), "id": "oa-1"}],
                "bank": [{**self._bank_row("1079.87"), "id": "bank-1"}],
                "invoice": [
                    {**self._invoice_row("290.00"), "id": "invoice-1"},
                    {**self._invoice_row("789.86"), "id": "invoice-2"},
                ],
            },
            relation_id="CASE-1",
        )

        self.assertIsNotNone(anomaly)
        assert anomaly is not None
        self.assertEqual(anomaly["code"], "workbench_anomaly")
        self.assertEqual(len(anomaly["items"]), 1)
        item = anomaly["items"][0]
        self.assertEqual(item["label"], "OA 流水一致，票少")
        self.assertEqual(item["oa_total"], "1079.87")
        self.assertEqual(item["invoice_total"], "1079.86")
        self.assertEqual(item["amount_delta"], "0.01")
        self.assertEqual(len(anomaly["fingerprint"]), 64)

    def test_workbench_anomaly_classifies_all_seven_three_way_amount_relations(self) -> None:
        cases = [
            ("100", "100", "120", "oa_bank_equal_invoice_more", "OA 流水一致，票多"),
            ("100", "100", "80", "oa_bank_equal_invoice_less", "OA 流水一致，票少"),
            ("100", "120", "100", "oa_invoice_equal_bank_more", "OA 发票一致，付多"),
            ("100", "80", "100", "oa_invoice_equal_bank_less", "OA 发票一致，付少"),
            ("80", "100", "100", "bank_invoice_equal_oa_less", "发票流水一致，OA 提少了"),
            ("120", "100", "100", "bank_invoice_equal_oa_more", "发票流水一致，OA 提多了"),
            ("120", "100", "80", "all_amounts_different", "三项不一致"),
        ]
        for index, (oa_amount, bank_amount, invoice_amount, code, label) in enumerate(cases):
            with self.subTest(code=code):
                anomaly = self.service.workbench_anomaly(
                    {
                        "oa": [{**self._oa_row(oa_amount), "id": "oa-1"}],
                        "bank": [{**self._bank_row(bank_amount), "id": "bank-1"}],
                        "invoice": [{**self._invoice_row(invoice_amount), "id": "invoice-1"}],
                    },
                    relation_id=f"CASE-SEVEN-{index}",
                )
                assert anomaly is not None
                self.assertEqual(len(anomaly["items"]), 1)
                self.assertEqual(anomaly["items"][0]["code"], code)
                self.assertEqual(anomaly["items"][0]["label"], label)
                self.assertTrue(anomaly["evidence_item_fingerprints"])

    def test_workbench_anomaly_is_absent_for_exact_match_or_missing_side(self) -> None:
        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{**self._oa_row("76.80"), "id": "oa-1"}],
                    "invoice": [
                        {**self._invoice_row("29"), "id": "invoice-1"},
                        {**self._invoice_row("47.8"), "id": "invoice-2"},
                    ],
                },
                relation_id="CASE-1",
            )
        )

    def test_workbench_anomaly_does_not_guess_when_a_three_way_direction_is_unknown(self) -> None:
        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{**self._oa_row("100"), "id": "oa-1"}],
                    "bank": [{**self._bank_row("100"), "id": "bank-1"}],
                    "invoice": [{
                        "type": "invoice",
                        "id": "invoice-unknown",
                        "invoice_type": "电子普通发票",
                        "total_with_tax": "80",
                    }],
                },
                relation_id="CASE-UNKNOWN-DIRECTION",
            )
        )

    def test_expense_items_compare_all_explicitly_bound_invoices_per_item(self) -> None:
        oa_row = {
            **self._oa_row("640.00"),
            "id": "oa-1",
            "expense_items": [
                {"id": "item-290", "amount": "290.00", "attachment_file_count": "2"},
                {"id": "item-350", "amount": "350.00", "attachment_file_count": "3"},
            ],
        }
        invoices = [
            {**self._invoice_row("145.00"), "id": "invoice-145-a", "source_expense_item_ids": ["item-290"]},
            {**self._invoice_row("145.00"), "id": "invoice-145-b", "source_expense_item_ids": ["item-290"]},
            {**self._invoice_row("150.00"), "id": "invoice-150", "source_expense_item_ids": ["item-350"]},
            {**self._invoice_row("100.00"), "id": "invoice-100-a", "source_expense_item_ids": ["item-350"]},
            {**self._invoice_row("100.00"), "id": "invoice-100-b", "source_expense_item_ids": ["item-350"]},
        ]

        self.assertIsNone(
            self.service.workbench_anomaly(
                {"oa": [oa_row], "invoice": invoices},
                relation_id="CASE-ITEMS",
            )
        )

    def test_expense_item_mismatch_without_three_way_context_does_not_create_an_eighth_class(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("290.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-290", "amount": "290.00", "attachment_file_count": "2"}],
                }],
                "invoice": [
                    {**self._invoice_row("145.00"), "id": "invoice-1", "source_expense_item_ids": ["item-290"]},
                    {**self._invoice_row("144.99"), "id": "invoice-2", "source_expense_item_ids": ["item-290"]},
                ],
            },
            relation_id="CASE-ITEM-MISMATCH",
        )

        self.assertIsNone(anomaly)

    def test_uploaded_expense_item_without_parsed_invoice_is_unparsed_anomaly(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("38.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-38", "amount": "38.00", "attachment_file_count": "1"}],
                }],
                "invoice": [],
            },
            relation_id="CASE-MISSING",
        )

        assert anomaly is not None
        self.assertEqual(len(anomaly["items"]), 1)
        item = anomaly["items"][0]
        self.assertEqual(item["code"], "oa_invoice_attachment_unparsed")
        self.assertEqual(item["label"], "发票附件未解析")
        self.assertEqual(item["source_expense_item_ids"], ["item-38"])
        self.assertEqual(item["attachment_file_count"], 1)
        self.assertEqual(item["invoice_row_ids"], [])
        self.assertIsNone(
            self.service.workbench_anomaly(
                {"oa": [{**self._oa_row("76.80"), "id": "oa-1"}], "invoice": []},
                relation_id="CASE-1",
            )
        )

    def test_expense_item_without_attachment_is_explicit_absent_status(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("38.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-38", "amount": "38.00", "attachment_file_count": "0"}],
                }],
                "invoice": [],
            },
            relation_id="CASE-ABSENT",
        )

        assert anomaly is not None
        self.assertEqual(anomaly["items"][0]["code"], "oa_invoice_attachment_absent")
        self.assertEqual(anomaly["items"][0]["label"], "发票附件缺失")

    def test_manual_invoice_binding_satisfies_zero_attachment_evidence(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("2308.02"),
                    "id": "oa-2308",
                    "expense_items": [{
                        "id": "item-2308",
                        "amount": "2308.02",
                        "attachment_file_count": "0",
                    }],
                }],
                "bank": [{
                    "id": "bank-2038",
                    "type": "bank",
                    "txn_direction": "expense",
                    "amount": "2038.02",
                }],
                "invoice": [
                    {
                        **self._invoice_row("859.57"),
                        "id": "invoice-859",
                        "source_expense_item_ids": ["item-2308"],
                    },
                    {
                        **self._invoice_row("1178.45"),
                        "id": "invoice-1178",
                        "source_expense_item_ids": ["item-2308"],
                    },
                ],
            },
            relation_id="CASE-MANUAL-2308",
        )

        assert anomaly is not None
        anomaly_codes = {item["code"] for item in anomaly["items"]}
        self.assertEqual(
            anomaly_codes,
            {"bank_invoice_equal_oa_more"},
        )
        self.assertNotIn("oa_invoice_attachment_absent", anomaly_codes)
        self.assertNotIn("oa_invoice_attachment_unparsed", anomaly_codes)

    def test_explicit_invoice_item_binding_overrides_attachment_item_for_amount_checks(self) -> None:
        invoice = {
            "type": "invoice",
            "id": "invoice-27-05",
            "source_expense_item_ids": ["item-4-current"],
            "source_links": [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "item-3",
                },
                {
                    "source_type": "oa_expense_item_invoice",
                    "source_expense_item_id": "item-4-written",
                },
            ],
        }

        self.assertEqual(self.service._source_expense_item_ids(invoice), ["item-4-current"])

    def test_malformed_explicit_binding_does_not_fall_back_to_attachment_item(self) -> None:
        invoice = {
            "type": "invoice",
            "id": "invoice-malformed-explicit",
            "source_expense_item_ids": [],
            "source_links": [
                {
                    "source_type": "oa_attachment_invoice",
                    "source_expense_item_id": "item-3",
                },
                {
                    "source_type": "oa_expense_item_invoice",
                    "source_expense_item_id": "",
                },
            ],
        }

        self.assertEqual(self.service._source_expense_item_ids(invoice), [])

    def test_exact_single_invoice_mismatch_is_displayed_on_that_invoice(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("55.00"),
                    "id": "oa-1",
                    "expense_items": [{"id": "item-55", "amount": "55.00", "attachment_file_count": "1"}],
                }],
                "bank": [{**self._bank_row("55.00"), "id": "bank-55"}],
                "invoice": [{
                    **self._invoice_row("54.99"),
                    "id": "invoice-55",
                    "source_expense_item_ids": ["item-55"],
                }],
            },
            relation_id="CASE-EXACT-MISMATCH",
        )

        assert anomaly is not None
        item = anomaly["items"][0]
        self.assertEqual(item["display_scope"], "row")
        self.assertEqual(item["display_pane"], "invoice")
        self.assertEqual(item["display_row_id"], "invoice-55")

    def test_group_bank_invoice_mismatch_is_not_attached_to_arbitrary_invoice(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{**self._oa_row("405.00"), "id": "oa-1"}],
                "bank": [
                    {"id": "bank-1", "type": "bank", "txn_direction": "expense", "amount": "200.00"},
                    {"id": "bank-2", "type": "bank", "txn_direction": "expense", "amount": "200.00"},
                ],
                "invoice": [
                    {**self._invoice_row("350.00"), "id": "invoice-350"},
                    {**self._invoice_row("55.00"), "id": "invoice-55"},
                ],
            },
            relation_id="CASE-GROUP-MISMATCH",
        )

        assert anomaly is not None
        item = anomaly["items"][0]
        self.assertEqual(item["code"], "oa_invoice_equal_bank_less")
        self.assertEqual(item["display_scope"], "group")
        self.assertEqual(item["display_pane"], "group")
        self.assertEqual(item["display_row_id"], "")

    def test_shared_invoice_is_counted_once_across_two_expense_items(self) -> None:
        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{
                        **self._oa_row("36.00"),
                        "id": "oa-1",
                        "expense_items": [
                            {"id": "item-18-a", "amount": "18.00", "attachment_file_count": "1"},
                            {"id": "item-18-b", "amount": "18.00", "attachment_file_count": "1"},
                        ],
                    }],
                    "invoice": [{
                        **self._invoice_row("36.00"),
                        "id": "invoice-36",
                        "source_expense_item_ids": ["item-18-a", "item-18-b"],
                    }],
                },
                relation_id="CASE-SHARED-INVOICE",
            )
        )

    def test_unassigned_is_distinct_and_any_unusable_attachment_uses_unparsed_status(self) -> None:
        unassigned = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("38.00"),
                    "id": "oa-1",
                    "expense_items": [
                        {"id": "item-38", "amount": "38.00", "attachment_file_count": "1"},
                    ],
                }],
                "invoice": [{
                    **self._invoice_row("38.00"),
                    "id": "invoice-38",
                    "source_links": [{
                        "source_type": "oa_attachment_invoice",
                        "derived_from_oa_id": "oa-1",
                    }],
                }],
            },
            relation_id="CASE-UNASSIGNED",
        )
        assert unassigned is not None
        unassigned_items = [
            item
            for item in unassigned["items"]
            if item["code"] == "oa_invoice_attachment_unassigned"
        ]
        self.assertEqual(len(unassigned_items), 1)
        self.assertEqual(unassigned_items[0]["display_scope"], "row")
        self.assertEqual(unassigned_items[0]["display_row_id"], "invoice-38")
        self.assertEqual(unassigned_items[0]["source_expense_item_ids"], [])

        unparsed = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("38.00"),
                    "id": "oa-1",
                    "expense_items": [{
                        "id": "item-38",
                        "amount": "38.00",
                        "attachment_file_count": "1",
                    }],
                }],
                "invoice": [],
            },
            relation_id="CASE-PARSE-FAILED",
        )
        assert unparsed is not None
        self.assertEqual(unparsed["items"][0]["code"], "oa_invoice_attachment_unparsed")
        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{**self._oa_row("76.80"), "id": "oa-1"}],
                    "invoice": [
                        {**self._invoice_row("29.00"), "id": "invoice-1"},
                        {"type": "invoice", "id": "invoice-without-amount"},
                    ],
                },
                relation_id="CASE-1",
            )
        )

    def test_each_unowned_relation_invoice_yields_one_row_anomaly_not_one_per_item(self) -> None:
        anomaly = self.service.workbench_anomaly(
            {
                "oa": [{
                    **self._oa_row("30.00"),
                    "id": "oa-1",
                    "expense_items": [
                        {"id": "item-1", "amount": "10.00", "attachment_file_count": "0"},
                        {"id": "item-2", "amount": "20.00", "attachment_file_count": "0"},
                    ],
                }],
                "invoice": [
                    {**self._invoice_row("12.00"), "id": "invoice-a", "source_links": []},
                    {**self._invoice_row("18.00"), "id": "invoice-b", "source_links": []},
                ],
            },
            relation_id="CASE-ROW-UNASSIGNED",
        )

        assert anomaly is not None
        unassigned = [
            item
            for item in anomaly["items"]
            if item["code"] == "oa_invoice_attachment_unassigned"
        ]
        self.assertEqual(len(unassigned), 2)
        self.assertEqual(
            [item["display_row_id"] for item in unassigned],
            ["invoice-a", "invoice-b"],
        )
        self.assertTrue(all(item["display_scope"] == "row" for item in unassigned))

    def test_etc_summary_is_not_unassigned_but_still_counts_toward_invoice_total(self) -> None:
        rows = {
            "oa": [{
                **self._oa_row("30.00"),
                "id": "oa-1",
                "expense_items": [
                    {"id": "item-1", "amount": "30.00", "attachment_file_count": "1"},
                ],
            }],
            "bank": [self._bank_row("30.00")],
            "invoice": [
                {
                    **self._invoice_row("12.00"),
                    "id": "etc-summary-batch-1",
                    "source_kind": "etc_invoice_summary",
                    "source_links": [],
                },
                {
                    **self._invoice_row("18.00"),
                    "id": "invoice-real",
                    "source_links": [],
                },
            ],
        }

        amount_check = self.service.check(rows, relation_mode="manual_confirmed")
        anomaly = self.service.workbench_anomaly(
            rows,
            relation_id="CASE-ETC-SUMMARY",
            relation_mode="manual_confirmed",
        )

        self.assertEqual(amount_check["invoice_total"], "30.00")
        assert anomaly is not None
        self.assertEqual(
            [
                item["display_row_id"]
                for item in anomaly["items"]
                if item["code"] == "oa_invoice_attachment_unassigned"
            ],
            ["invoice-real"],
        )

    def test_etc_batch_accounting_summary_closes_document_evidence(self) -> None:
        rows = {
            "oa": [{
                **self._oa_row("2411.25"),
                "id": "oa-exp-2080",
                "expense_items": [
                    {
                        "id": "oa-exp-2080:item:0",
                        "amount": "2169.68",
                        "attachment_file_count": "0",
                    },
                    {
                        "id": "oa-exp-2080:item:1",
                        "amount": "241.57",
                        "attachment_file_count": "0",
                    },
                ],
            }],
            "bank": [self._bank_row("2411.25")],
            "invoice": [{
                **self._invoice_row("2411.25"),
                "id": "etc-summary-ETC-OA-20260413-241125",
                "source_kind": "etc_invoice_summary",
                "source_links": [],
            }],
        }

        self.assertIsNone(
            self.service.workbench_anomaly(
                rows,
                relation_id="CASE-BATCH-txn_imported_1453",
                relation_mode="batch_accounting",
            )
        )

        manual_anomaly = self.service.workbench_anomaly(
            rows,
            relation_id="CASE-MANUAL-ETC-SUMMARY",
            relation_mode="manual_confirmed",
        )
        assert manual_anomaly is not None
        self.assertEqual(
            [item["code"] for item in manual_anomaly["items"]],
            ["oa_invoice_attachment_absent", "oa_invoice_attachment_absent"],
        )

    def test_relation_without_oa_expense_items_does_not_create_unassigned_anomaly(self) -> None:
        self.assertIsNone(
            self.service.workbench_anomaly(
                {
                    "oa": [{**self._oa_row("30.00"), "id": "oa-1"}],
                    "invoice": [{**self._invoice_row("30.00"), "id": "invoice-1"}],
                },
                relation_id="CASE-NO-EXPENSE-ITEMS",
            )
        )

    @staticmethod
    def _oa_row(amount: str, *, reconciliation_amount: str | None = None) -> dict[str, str]:
        row = {
            "type": "oa",
            "apply_type": "付款",
            "amount": amount,
        }
        if reconciliation_amount is not None:
            row["reconciliation_amount"] = reconciliation_amount
        return row

    @staticmethod
    def _bank_row(amount: str) -> dict[str, str]:
        return {
            "type": "bank",
            "debit_amount": amount,
        }

    @staticmethod
    def _bank_income_row(amount: str) -> dict[str, str]:
        return {
            "type": "bank",
            "credit_amount": amount,
        }

    @staticmethod
    def _invoice_row(amount: str) -> dict[str, str]:
        return {
            "type": "invoice",
            "invoice_type": "input",
            "total_with_tax": amount,
        }


if __name__ == "__main__":
    unittest.main()
