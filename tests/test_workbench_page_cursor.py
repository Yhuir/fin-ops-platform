from __future__ import annotations

import pytest

from fin_ops_platform.services.workbench_filter_options import (
    WORKBENCH_FILTER_MISSING_VALUE,
    normalize_workbench_column_filters,
    normalize_workbench_time_filters,
)
from fin_ops_platform.services.workbench_page_cursor import (
    WorkbenchPageCursor,
    WorkbenchPageCursorError,
    decode_workbench_page_cursor,
    encode_workbench_page_cursor,
    workbench_query_hash,
)


def test_cursor_round_trip_is_bound_to_normalized_query_and_sort() -> None:
    query_hash = workbench_query_hash(
        {"scope_key": "2026-07", "zone": "unpaired", "search": "100"}
    )
    encoded = encode_workbench_page_cursor(
        WorkbenchPageCursor(
            query_hash=query_hash,
            sort="bank:desc",
            missing=False,
            value="2026-07-31",
            group_key="row:bank:txn-1",
        )
    )

    decoded = decode_workbench_page_cursor(
        encoded,
        expected_query_hash=query_hash,
        expected_sort="bank:desc",
    )

    assert decoded is not None
    assert decoded.value == "2026-07-31"
    assert decoded.group_key == "row:bank:txn-1"


def test_cursor_rejects_tampering_and_cross_query_reuse() -> None:
    query_hash = workbench_query_hash({"scope_key": "all", "zone": "paired"})
    encoded = encode_workbench_page_cursor(
        WorkbenchPageCursor(
            query_hash=query_hash,
            sort="default:desc",
            missing=False,
            value="2026-07-01|2026-07-31T10:00:00",
            group_key="case:WB-1",
        )
    )

    with pytest.raises(WorkbenchPageCursorError, match="cursor"):
        decode_workbench_page_cursor(
            encoded[:-1] + ("A" if encoded[-1] != "A" else "B"),
            expected_query_hash=query_hash,
            expected_sort="default:desc",
        )
    with pytest.raises(WorkbenchPageCursorError, match="does not belong"):
        decode_workbench_page_cursor(
            encoded,
            expected_query_hash=workbench_query_hash(
                {"scope_key": "2026-07", "zone": "paired"}
            ),
            expected_sort="default:desc",
        )


def test_column_filter_normalization_is_allowlisted_bounded_and_keeps_missing() -> None:
    result = normalize_workbench_column_filters(
        {
            "oa": {
                "applicant": ["张三", "张三", WORKBENCH_FILTER_MISSING_VALUE],
            },
            "bank": {"amount": ["支出", "尾号1234"]},
        }
    )

    assert result == {
        "oa": {
            "applicant": [WORKBENCH_FILTER_MISSING_VALUE, "张三"],
        },
        "bank": {"amount": ["尾号1234", "支出"]},
    }
    with pytest.raises(ValueError, match="unsupported panes"):
        normalize_workbench_column_filters(
            {"unknown": {"applicant": ["must-not-be-ignored"]}}
        )
    with pytest.raises(ValueError, match="unsupported column"):
        normalize_workbench_column_filters(
            {"oa": {"privateJsonPath": ["must-not-be-ignored"]}}
        )


def test_time_filter_normalization_rejects_invalid_months() -> None:
    with pytest.raises(ValueError, match="invoice.month must be YYYY-MM"):
        normalize_workbench_time_filters(
            {
                "oa": {"mode": "year", "year": "2026"},
                "bank": {"mode": "month", "month": "2026-12"},
                "invoice": {"mode": "month", "month": "2026-19"},
            }
        )
    assert normalize_workbench_time_filters(
        {
            "oa": {"mode": "year", "year": "2026"},
            "bank": {"mode": "month", "month": "2026-12"},
        }
    ) == {
        "oa": {"mode": "year", "year": "2026"},
        "bank": {"mode": "month", "month": "2026-12"},
    }
