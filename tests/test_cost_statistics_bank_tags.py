from __future__ import annotations

from fin_ops_platform.services.cost_statistics_bank_tags import (
    bank_tag_context_from_row,
)


def test_candidate_labels_without_effective_code_stay_untagged() -> None:
    result = bank_tag_context_from_row(
        {
            "bank_tag_code": None,
            "bank_tag_label": "借入款",
            "bank_tag_primary_label": "外部往来款收款",
            "bank_tag_sub_label": "借入款",
            "bank_tag_label_path": ["自动识别", "借入款"],
        }
    )

    assert result == {
        "bank_tag_code": "",
        "bank_tag_label": "未标记",
        "bank_tag_primary_label": "未标记",
        "bank_tag_sub_label": "未标记",
        "bank_tag_label_path": ["未标记"],
    }


def test_single_level_internal_transfer_has_one_stable_cost_tag_path() -> None:
    result = bank_tag_context_from_row(
        {
            "bank_tag_code": "internal_transfer",
            "bank_tag_label": "内部往来款",
            "bank_tag_primary_label": "内部往来款",
            "bank_tag_sub_label": None,
            "bank_tag_label_path": ["内部往来款"],
        }
    )

    assert result == {
        "bank_tag_code": "internal_transfer",
        "bank_tag_label": "内部往来款",
        "bank_tag_primary_label": "内部往来款",
        "bank_tag_sub_label": "",
        "bank_tag_label_path": ["内部往来款"],
    }
