import pytest

from fin_ops_platform.services.workbench_search import amount_search_fragment, search_terms


@pytest.mark.parametrize(('query', 'expected'), [
    ('6868', '6868'), ('0093', '0093'), ('￥6,868.55', '6868.55'),
    ('¥+6,868.55', '6868.55'), ('-6868.55', '-6868.55'), ('.55', '.55'),
    ('6868.', '6868.'), ('.', '.'), ('26532000001534911841', '26532000001534911841'),
    ('NaN', None), ('Infinity', None), ('6e3', None), ('68,68', None),
    ('%', None), ('_', None), ('', None), ('刘树刚', None),
])
def test_amount_fragments_do_not_rewrite_text_identity(query, expected):
    assert amount_search_fragment(query) == expected


def test_search_terms_preserve_literals_and_remove_repeated_terms():
    assert search_terms('  0093\t6868  0093\n材料% _ ') == ['0093', '6868', '材料%', '_']
    assert search_terms(' \n ') == []
