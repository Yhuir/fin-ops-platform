from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fin_ops_platform.tools.restore_deleted_etc_business_batch import (
    _resolve_business_batch_scope_month,
    _resolve_oa_alias,
    _resolve_oa_identity,
    main,
)


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
        "stored_oa_row_id": "oa-pay-2200",
        "task_id": "ETC-RECON-000004",
        "scope_month": "2026-05",
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
    def test_oa_alias_must_be_active_and_exact(self) -> None:
        connection = SimpleNamespace(
            fetch_one=lambda _sql, params: (
                {"evidence_hash": "proof"}
                if params == ("oa-source-1", "oa-pay-2200")
                else None
            )
        )

        resolution = _resolve_oa_alias(
            connection=connection,
            stored_oa_row_id="oa-source-1",
            expected_oa_row_id="oa-pay-2200",
        )

        self.assertEqual(resolution["mode"], "active_alias")
        self.assertEqual(resolution["evidence_hash"], "proof")

    def test_missing_stored_oa_requires_one_exact_external_batch_owner(self) -> None:
        connection = SimpleNamespace(
            fetch_all=lambda _sql, params: (
                [{"row_id": "oa-pay-2200"}]
                if params == ("etc_20260520_001",)
                else []
            )
        )

        resolution = _resolve_oa_identity(
            connection=connection,
            stored_oa_row_id="",
            expected_oa_row_id="oa-pay-2200",
            external_etc_batch_id="etc_20260520_001",
        )

        self.assertEqual(resolution["mode"], "external_etc_batch_id")
        self.assertEqual(resolution["canonical_oa_row_id"], "oa-pay-2200")

    def test_scope_month_comes_from_canonical_business_batch(self) -> None:
        connection = SimpleNamespace(
            fetch_one=lambda _sql, params: (
                {"scope_month": "2026-05"}
                if params == ("etc_business_batch_0004",)
                else None
            )
        )

        self.assertEqual(
            _resolve_business_batch_scope_month(
                connection=connection,
                business_batch_id="etc_business_batch_0004",
            ),
            "2026-05",
        )

    def test_dry_run_and_fingerprint_guarded_execute_use_exact_preview(self) -> None:
        service = _EtcService()
        app = object()
        refresh_calls: list[tuple[object, list[str], str]] = []
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
                return_value=app,
            ),
            patch("fin_ops_platform.tools.restore_deleted_etc_business_batch.etc_service", return_value=service),
            patch(
                "fin_ops_platform.tools.restore_deleted_etc_business_batch.etc_reconciliation_task_service",
                return_value=SimpleNamespace(
                    get_task_record=lambda _task_id: SimpleNamespace(title="Recovered ETC batch")
                ),
            ),
            patch(
                "fin_ops_platform.tools.restore_deleted_etc_business_batch.refresh_after_historical_etc_repair_link",
                side_effect=lambda runtime, months, *, reason: refresh_calls.append((runtime, months, reason)),
            ),
            patch("fin_ops_platform.tools.restore_deleted_etc_business_batch.PostgresSettings.from_env"),
            patch(
                "fin_ops_platform.tools.restore_deleted_etc_business_batch.PostgresConnection",
                return_value=SimpleNamespace(
                    fetch_one=lambda _sql, params: (
                        {"scope_month": "2026-05"}
                        if params == ("etc_business_batch_0004",)
                        else None
                    )
                ),
            ),
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
                        dry_run["fingerprint"],
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
        self.assertEqual(service.restore_calls[0]["canonical_title"], "Recovered ETC batch")
        self.assertEqual(
            refresh_calls,
            [(app, ["2026-05"], "deleted_submitted_etc_business_batch_restored")],
        )


if __name__ == "__main__":
    unittest.main()
