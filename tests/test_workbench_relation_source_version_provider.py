from __future__ import annotations

import unittest

from fin_ops_platform.services.snapshot_version import snapshot_version
from fin_ops_platform.services.workbench_relation_source_version_provider import WorkbenchRelationSourceVersionProvider


class WorkbenchRelationSourceVersionProviderTests(unittest.TestCase):
    def test_pair_relation_snapshot_version_matches_workbench_read_model_snapshot_hash(self) -> None:
        snapshot = {
            "pair_relations": {
                "CASE-1": {
                    "case_id": "CASE-1",
                    "row_ids": ["oa-1", "bank-1"],
                    "row_types": ["oa", "bank"],
                    "status": "active",
                }
            }
        }

        provider = WorkbenchRelationSourceVersionProvider(lambda: snapshot)

        self.assertEqual(
            provider.pair_relation_snapshot_version(),
            snapshot_version(snapshot),
        )


if __name__ == "__main__":
    unittest.main()
