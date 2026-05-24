from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_text_normalization import (
    evidence_tokens,
    matching_tokens,
    normalize_match_text,
)


class WorkbenchTextNormalizationTests(unittest.TestCase):
    def test_company_suffix_alone_is_not_valid_match_evidence(self) -> None:
        left = evidence_tokens({"invoice.seller_name": "有限公司"})
        right = evidence_tokens({"bank.counterparty": "有限公司"})

        self.assertEqual(normalize_match_text("有限公司"), "")
        self.assertEqual(left, [])
        self.assertEqual(matching_tokens(left, right), [])

    def test_low_information_words_cannot_match_alone(self) -> None:
        left = evidence_tokens({"oa.reason": "报销 付款 费用"})
        right = evidence_tokens({"bank.summary": "付款费用报销"})

        self.assertEqual(left, [])
        self.assertEqual(matching_tokens(left, right), [])

    def test_normalization_removes_suffix_punctuation_spaces_and_width(self) -> None:
        self.assertEqual(
            normalize_match_text(" 杭州ＡＢＣ广告有限公司（报销） "),
            "杭州abc广告",
        )

    def test_evidence_tokens_preserve_source_fields_for_all_free_matching_sources(self) -> None:
        tokens = evidence_tokens(
            {
                "oa.applicant": "张三",
                "oa.project": "星河项目",
                "oa.reason": "杭州ABC广告制作",
                "bank.counterparty": "杭州ABC广告有限公司",
                "bank.summary": "星河项目付款",
                "bank.remark": "张三报销",
                "invoice.seller_name": "杭州ABC广告有限公司",
            }
        )

        by_source = {(token.source_field, token.value) for token in tokens}

        self.assertIn(("oa.applicant", "张三"), by_source)
        self.assertIn(("oa.project", "星河项目"), by_source)
        self.assertIn(("oa.reason", "杭州abc广告制作"), by_source)
        self.assertIn(("bank.counterparty", "杭州abc广告"), by_source)
        self.assertIn(("bank.summary", "星河项目"), by_source)
        self.assertIn(("bank.remark", "张三"), by_source)
        self.assertIn(("invoice.seller_name", "杭州abc广告"), by_source)

    def test_matching_tokens_reports_both_source_fields(self) -> None:
        left = evidence_tokens({"oa.reason": "杭州ABC广告制作"})
        right = evidence_tokens({"bank.counterparty": "杭州ABC广告有限公司"})

        matches = matching_tokens(left, right)

        self.assertEqual(
            matches,
            [
                {
                    "token": "杭州abc广告",
                    "left_source_field": "oa.reason",
                    "right_source_field": "bank.counterparty",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
