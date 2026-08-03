from fin_ops_platform.services.search_query import normalize_money_search_query


def test_normalize_money_search_query_only_strips_grouping_from_amounts() -> None:
    assert normalize_money_search_query(" 4,311.00 ") == "4311.00"
    assert normalize_money_search_query("4311.00") == "4311.00"
    assert normalize_money_search_query("云南,公司") == "云南,公司"
