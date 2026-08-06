from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


SCRIPT_PATH = Path("scripts/rehydrate-workbench-read-models.py")
SPEC = importlib.util.spec_from_file_location("rehydrate_workbench_read_models", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class AttachmentIdentityBridgeRepairTests(unittest.TestCase):
    def test_dry_run_fingerprint_is_deterministic(self) -> None:
        first = MODULE._fingerprint_rows(
            [
                {"source_kind": "attachment_identity_invoice", "source_attachment_key": "actual-1"},
                {"source_kind": "attachment_identity_invoice", "source_attachment_key": "actual-2"},
            ]
        )
        second = MODULE._fingerprint_rows(
            [
                {"source_attachment_key": "actual-2", "source_kind": "attachment_identity_invoice"},
                {"source_attachment_key": "actual-1", "source_kind": "attachment_identity_invoice"},
            ]
        )

        self.assertEqual(first, second)

    def test_apply_rejects_changed_bridge_candidate_fingerprint_before_write(self) -> None:
        connection = _Connection()

        with self.assertRaisesRegex(ValueError, "fingerprint changed"):
            MODULE._repair_attachment_identity_bridge(
                connection,
                apply_changes=True,
                expected_fingerprint="stale",
            )

        self.assertFalse(any("insert into app.oa_attachment_invoice_cache_sources" in sql for sql in connection.sql))

    def test_apply_only_updates_changed_rows(self) -> None:
        connection = _Connection()
        fingerprint = MODULE._fingerprint_rows(connection.candidate_rows)

        result = MODULE._repair_attachment_identity_bridge(
            connection,
            apply_changes=True,
            expected_fingerprint=fingerprint,
        )

        insert_sql = next(sql for sql in connection.sql if "insert into app.oa_attachment_invoice_cache_sources" in sql)
        self.assertIn("is distinct from", insert_sql)
        self.assertEqual(result["applied"]["total"], 1)


class _Connection:
    def __init__(self) -> None:
        self.sql: list[str] = []
        self.candidate_rows = [
            {
                "cache_source_attachment_key": "cache-1",
                "source_attachment_key": "actual-1",
                "source_kind": "attachment_identity_invoice",
                "source_expense_item_id": "oa-1:item:0",
                "source_expense_row_index": "0",
                "source_attachment_name": "invoice.pdf",
            }
        ]

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict[str, object]]:
        normalized = " ".join(sql.lower().split())
        self.sql.append(normalized)
        if "group by source_kind" in normalized:
            return [{"source_kind": "attachment_identity_invoice", "count": 1}]
        if "returning source_kind" in normalized:
            return [{"source_kind": "attachment_identity_invoice"}]
        return self.candidate_rows


if __name__ == "__main__":
    unittest.main()
