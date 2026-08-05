from fin_ops_platform.services.search_query import (
    canonicalize_money_search_query,
    is_money_search_query,
    normalize_money_search_query,
)


def test_canonicalize_money_search_query_canonicalizes_equivalent_amounts() -> None:
    for query in ("202", "202.0", "202.00", "￥202.00", "¥202.00"):
        assert canonicalize_money_search_query(query) == "202"
    assert canonicalize_money_search_query(" 4,311.00 ") == "4311"
    assert canonicalize_money_search_query("-0.00") == "0"
    assert canonicalize_money_search_query("云南,公司") == "云南,公司"


def test_normalize_money_search_query_preserves_decimal_precision_contract() -> None:
    assert normalize_money_search_query(" 4,311.00 ") == "4311.00"


def test_is_money_search_query_rejects_non_amount_text() -> None:
    assert is_money_search_query("4311.00") is True
    assert is_money_search_query("4,311.00") is True
    assert is_money_search_query("￥4311.00") is False
    assert is_money_search_query("云南4311") is False
