from __future__ import annotations

import unittest

from fin_ops_platform.services.read_model_freshness import (
    normalize_source_versions,
    read_model_freshness_token,
    require_expected_source_versions,
    resolve_read_model_freshness,
    source_version_mismatch_reasons,
    source_versions_match,
)


class ReadModelFreshnessTests(unittest.TestCase):
    def test_freshness_token_is_stable_for_equivalent_source_versions_and_scope_bound(self) -> None:
        first = read_model_freshness_token(
            scope_type="workbench",
            scope_key="2026-05",
            expected_source_versions={"relation": {"b": 2, "a": 1}, "builder": "v6"},
        )
        second = read_model_freshness_token(
            scope_type="workbench",
            scope_key="2026-05",
            expected_source_versions={"builder": "v6", "relation": {"a": 1, "b": 2}},
        )

        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            read_model_freshness_token(
                scope_type="workbench",
                scope_key="2026-06",
                expected_source_versions={"builder": "v6", "relation": {"a": 1, "b": 2}},
            ),
        )

    def test_normalize_source_versions_drops_empty_values_and_stringifies(self) -> None:
        self.assertEqual(
            normalize_source_versions({"source_version": 3, "empty": "", "none": None}),
            {"source_version": "3"},
        )

    def test_normalize_source_versions_canonicalizes_nested_values(self) -> None:
        self.assertEqual(
            normalize_source_versions(
                {
                    "source_version": 3,
                    "by_month": {
                        "2026-05": {"updated_at": "b", "schema": 1},
                        "2026-04": {"schema": 1, "updated_at": "a"},
                    },
                }
            ),
            {
                "source_version": "3",
                "by_month": '{"2026-04":{"schema":1,"updated_at":"a"},"2026-05":{"schema":1,"updated_at":"b"}}',
            },
        )

    def test_source_versions_match_when_expected_subset_matches(self) -> None:
        self.assertTrue(
            source_versions_match(
                expected={"source_version": 3},
                actual={"source_version": "3", "extra": "kept"},
            )
        )

    def test_source_versions_report_missing_and_mismatch_reasons(self) -> None:
        self.assertEqual(
            source_version_mismatch_reasons(
                expected={"bank_auto_tag_rules_version": 2, "source_version": 7},
                actual={"source_version": 8},
            ),
            ["bank_auto_tag_rules_version_missing", "source_version_mismatch"],
        )

    def test_dirty_scope_pending_takes_refreshing_status(self) -> None:
        freshness = resolve_read_model_freshness(
            expected_source_versions={"source_version": 7},
            actual_source_versions={"source_version": 7},
            dirty_status="pending",
        )

        self.assertEqual(freshness.status, "refreshing")

    def test_schema_mismatch_is_explicit(self) -> None:
        freshness = resolve_read_model_freshness(
            expected_schema_version="schema-v2",
            actual_schema_version="schema-v1",
        )

        self.assertEqual(freshness.status, "schema_mismatch")
        self.assertEqual(freshness.stale_reasons, ("schema_version_mismatch",))

    def test_missing_schema_is_not_fresh_when_expected_schema_is_set(self) -> None:
        freshness = resolve_read_model_freshness(
            expected_schema_version="schema-v2",
            actual_schema_version=None,
            expected_source_versions={"source_version": 3},
            actual_source_versions={"source_version": 3},
        )

        self.assertEqual(freshness.status, "schema_mismatch")
        self.assertEqual(freshness.stale_reasons, ("schema_version_missing",))

    def test_expected_source_versions_contract_must_not_be_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "missing expected source versions"):
            require_expected_source_versions({}, context="unit_test")

    def test_source_version_mismatch_is_stale(self) -> None:
        freshness = resolve_read_model_freshness(
            expected_source_versions={"bank_auto_tag_rules_version": 2},
            actual_source_versions={"bank_auto_tag_rules_version": 1},
        )

        self.assertEqual(freshness.status, "stale")
        self.assertEqual(freshness.stale_reasons, ("bank_auto_tag_rules_version_mismatch",))

if __name__ == "__main__":
    unittest.main()
