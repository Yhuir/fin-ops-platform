from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import json
import unittest
from unittest.mock import patch

from fin_ops_platform.tools.restore_deleted_etc_business_batch import _fingerprint, main


@dataclass
class _RestoredBatch:
    business_batch_id: str = "etc_business_batch_0004"
    status: str = "manually_marked_submitted"
    version: int = 9
    submission_batch_id: str = "etc_batch_0004"
    invoice_ids: tuple[str, ...] = ("invoice-1", "invoice-2")
    oa_row_id: str = "oa-pay-2200"


class _EtcService:
    preview = {
        "business_batch_id": "etc_business_batch_0004",
        "invoice_count": 2,
        "invoice_ids": ["invoice-1", "invoice-2"],
        "invoice_total": "26.14",
        "oa_row_id": "oa-pay-2200",
        "version": 8,
    }

    def __init__(self) -> None:
        self.restore_calls: list[dict] = []

    def preview_deleted_submitted_business_batch_restore(self, *_args, **_kwargs):
        return dict(self.preview)

    def restore_deleted_submitted_business_batch(self, _batch_id: str, **kwargs):
        self.restore_calls.append(kwargs)
        return _RestoredBatch()


class RestoreDeletedEtcBusinessBatchToolTests(unittest.TestCase):
    def test_dry_run_and_fingerprint_guarded_execute_use_exact_preview(self) -> None:
        service = _EtcService()
        base_args = [
            "--business-batch-id",
            "etc_business_batch_0004",
            "--expected-invoice-count",
            "2",
            "--expected-total-amount",
            "26.14",
            "--expected-oa-row-id",
            "oa-pay-2200",
        ]
        with (
            patch(
                "fin_ops_platform.tools.restore_deleted_etc_business_batch.build_tool_runtime_application",
                return_value=object(),
            ),
            patch("fin_ops_platform.tools.restore_deleted_etc_business_batch.etc_service", return_value=service),
        ):
            dry_run_output = StringIO()
            self.assertEqual(main([*base_args, "--dry-run"], stdout=dry_run_output), 0)
            dry_run = json.loads(dry_run_output.getvalue())

            execute_output = StringIO()
            self.assertEqual(
                main(
                    [
                        *base_args,
                        "--execute",
                        "--expected-fingerprint",
                        _fingerprint(service.preview),
                        "--operator",
                        "ops",
                        "--reason",
                        "approved repair",
                    ],
                    stdout=execute_output,
                ),
                0,
            )
            executed = json.loads(execute_output.getvalue())

        self.assertEqual(dry_run["status"], "ready")
        self.assertEqual(executed["status"], "restored")
        self.assertEqual(executed["invoice_count"], 2)
        self.assertEqual(service.restore_calls[0]["expected_version"], 8)


if __name__ == "__main__":
    unittest.main()
