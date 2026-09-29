from decimal import Decimal

import pytest

from fin_ops_platform.services.workbench_search import (
    amount_search_fragment,
    fold_amount_search_minimum,
    search_terms,
)


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


@pytest.mark.parametrize(('fragment', 'minimum'), [
    ('6868', '6868'), ('6868.55', '6868.55'), ('0093', '10093'),
    ('6', '.06'), ('68', '.68'), ('00', '0'), ('000', '1000'),
    ('.55', '.55'), ('.5', '.5'), ('.', '0'), ('6868.', '6868'),
    ('0.5', '.5'), ('00.5', '100.5'), ('0093.50', '10093.50'),
    ('26532000001534911841', '26532000001534911841'),
    ('-6868', None), ('-.55', None), ('.555', None), ('0.000', None),
])
def test_fold_candidate_minimum_preserves_all_possible_display_hits(fragment, minimum):
    expected = Decimal(minimum) if minimum is not None else None
    assert fold_amount_search_minimum(fragment) == expected


def test_fold_minimum_does_not_prune_any_small_two_decimal_match():
    for cents in range(10000):
        amount = Decimal(cents) / 100
        display = format(amount, '.2f')
        for start in range(len(display)):
            for end in range(start + 1, len(display) + 1):
                minimum = fold_amount_search_minimum(display[start:end])
                assert minimum is not None and minimum <= amount
