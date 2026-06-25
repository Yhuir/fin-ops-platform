from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_cache_read_payload_helper import WorkbenchCacheReadPayloadHelper


class WorkbenchCacheReadPayloadHelperTests(unittest.TestCase):
    def _helper(self, *, mongo: bool = False, offset_rebuild: bool = False) -> WorkbenchCacheReadPayloadHelper:
        return WorkbenchCacheReadPayloadHelper(
            is_mongo_oa_adapter=lambda: mongo,
            cached_payload_needs_oa_invoice_offset_rebuild=lambda payload: offset_rebuild,
            workbench_candidate_snapshot_hash=lambda month: f"hash:{month}",
            current_oa_attachment_invoice_parser_version=lambda: "parser-v1",
            workbench_read_model_schema_version="schema-v1",
            candidate_match_schema_version="candidate-v1",
            workbench_matching_rules_version="rules-v1",
        )

    def test_can_use_cached_payload_rejects_not_ready_and_offset_rebuild(self) -> None:
        self.assertFalse(self._helper().can_use_cached_payload({"oa_status": {"code": "syncing"}}))
        self.assertFalse(self._helper(offset_rebuild=True).can_use_cached_payload({"oa_status": {"code": "ready"}}))

    def test_can_use_cached_payload_rejects_stale_candidate_hash(self) -> None:
        payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready"},
            "workbench_candidate_snapshot_hash": "old",
        }

        self.assertFalse(self._helper().can_use_cached_payload(payload))

    def test_can_use_cached_payload_applies_mongo_schema_parser_hash_and_summary_gates(self) -> None:
        payload = {
            "month": "2026-03",
            "oa_status": {"code": "ready"},
            "workbench_read_model_schema_version": "schema-v1",
            "workbench_candidate_match_schema_version": "candidate-v1",
            "workbench_matching_rules_version": "rules-v1",
            "oa_attachment_invoice_parser_version": "parser-v1",
            "workbench_candidate_snapshot_hash": "hash:2026-03",
            "summary": {"oa_count": 1},
        }
        helper = self._helper(mongo=True)

        self.assertTrue(helper.can_use_cached_payload(payload))
        self.assertFalse(helper.can_use_cached_payload({**payload, "workbench_read_model_schema_version": "old"}))
        self.assertFalse(helper.can_use_cached_payload({**payload, "summary": {"oa_count": 0}}))

    def test_persist_and_fallback_use_oa_status_gate(self) -> None:
        helper = self._helper(mongo=True)

        self.assertTrue(helper.can_persist_payload({"oa_status": {"code": "ready"}}))
        self.assertTrue(helper.can_fallback_to_stale_payload({"oa_status": {"code": "ready"}}))
        self.assertFalse(helper.can_persist_payload({"oa_status": {"code": "syncing"}}))

    def test_non_mongo_allows_missing_oa_status(self) -> None:
        self.assertTrue(self._helper(mongo=False).oa_status_is_ready_for_cache({}))
        self.assertFalse(self._helper(mongo=False).oa_status_is_ready_for_cache({"oa_status": {"code": "syncing"}}))


if __name__ == "__main__":
    unittest.main()
