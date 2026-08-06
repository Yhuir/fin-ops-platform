from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


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


class OAAttachmentInvoicePromotionRoutingTests(unittest.TestCase):
    def test_promotion_dry_run_uses_the_existing_exact_release_maintenance_entrypoint(self) -> None:
        connection = _RuntimeConnection()
        promotion_report = {"candidate_fingerprint": "abc", "summary": {"affected_invoice_count": 1}}

        with (
            patch.object(
                sys,
                "argv",
                ["rehydrate-workbench-read-models.py", "--promote-oa-attachment-invoices", "--dry-run", "--json"],
            ),
            patch.object(MODULE.PostgresSettings, "from_env", return_value=object()),
            patch.object(MODULE, "PostgresConnection", return_value=connection),
            patch.object(
                MODULE,
                "audit_oa_attachment_invoice_promotion",
                return_value=promotion_report,
            ) as audit,
            patch.object(MODULE, "_print_report", return_value=0) as print_report,
        ):
            self.assertEqual(MODULE.main(), 0)

        audit.assert_called_once_with(
            connection=connection,
            example_limit=100,
            apply=False,
            oa_row_ids=[],
            expected_fingerprint=None,
        )
        self.assertEqual(print_report.call_args.args[0]["oa_attachment_invoice_promotion"], promotion_report)

    def test_promotion_apply_requires_explicit_confirmation(self) -> None:
        with (
            patch.object(
                sys,
                "argv",
                [
                    "rehydrate-workbench-read-models.py",
                    "--promote-oa-attachment-invoices",
                    "--apply-repair",
                    "--expected-fingerprint",
                    "abc",
                ],
            ),
            self.assertRaisesRegex(ValueError, "confirm-apply-oa-attachment-invoices"),
        ):
            MODULE.main()


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


class _RuntimeConnection:
    def __init__(self) -> None:
        self.statement_timeout_ms: int | None = None

    def set_statement_timeout_ms(self, value: int) -> None:
        self.statement_timeout_ms = value


if __name__ == "__main__":
    unittest.main()
