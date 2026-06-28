from __future__ import annotations

import unittest

from fin_ops_platform.services.scope_keys import normalized_scope_keys


class ScopeKeysTests(unittest.TestCase):
    def test_normalized_scope_keys_dedupes_and_keeps_order(self) -> None:
        self.assertEqual(normalized_scope_keys(["2026-05", "", "2026-05", "all"]), ["2026-05", "all"])

    def test_normalized_scope_keys_falls_back_when_no_scope_is_available(self) -> None:
        self.assertEqual(normalized_scope_keys([], fallback="all"), ["all"])


if __name__ == "__main__":
    unittest.main()
