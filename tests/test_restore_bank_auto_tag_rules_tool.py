from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from io import StringIO
from unittest.mock import patch

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.tools.restore_bank_auto_tag_rules import (
    build_restore_plan,
    build_restore_summary,
    critical_code_status,
    main,
    write_settings_backup,
)


class RestoreBankAutoTagRulesToolTests(unittest.TestCase):
    def test_restore_summary_reports_recovered_external_turnover_codes_and_critical_status(self) -> None:
        source = [
            ["流水类型", "分类（一级）", "银行流水标签（贰级）", "选择查询的项", "包含", "必须同时包含", "精准命重", "不包含字样"],
            ["支出", "往来款付款", "借出款", "用途/交易用途、摘要、备注/附言/客户附言", "暂借款、借款", "", "", ""],
        ]
        previous_tags = BankTransactionCategoryService.from_snapshot(None).tag_dictionary_payload()
        previous_tags["version"] = 63
        previous_tags["definitions"].append(
            {
                "code": "custom_a1c21e4bc4c6",
                "label": "借入款",
                "path": ["自动识别", "借入款"],
                "source": "custom",
                "status": "active",
            }
        )

        plan = build_restore_plan(source, previous_settings={"bank_transaction_tags": previous_tags})
        summary = build_restore_summary(plan, mode="dry_run")

        self.assertFalse(summary["write_executed"])
        self.assertEqual(summary["old_version"], 63)
        self.assertEqual(summary["new_version"], 64)
        self.assertIn("custom_a1c21e4bc4c6", summary["recovered_legacy_external_turnover_codes"])
        self.assertEqual(
            summary["critical_code_status"]["custom_a1c21e4bc4c6"]["output_primary_label"],
            "外部往来款收款",
        )
        self.assertEqual(
            summary["critical_code_status"]["custom_a1c21e4bc4c6"]["turnover_action_type"],
            "pending_repayment",
        )
        self.assertTrue(summary["critical_code_status"]["external_turnover"]["has_rules"])

    def test_critical_code_status_marks_missing_codes_without_hiding_existing_codes(self) -> None:
        status = critical_code_status({"version": 1, "definitions": [{"code": "fee", "label": "手续费", "status": "active"}]})

        self.assertTrue(status["fee"]["exists"])
        self.assertEqual(status["fee"]["label"], "手续费")
        self.assertTrue(status["external_turnover"]["exists"])
        self.assertFalse(status["custom_0f16f8a24eca"]["exists"])

    def test_apply_requires_explicit_confirm_write(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "rules.xlsx"
            source.write_bytes(b"not parsed because confirm guard exits first")

            with self.assertRaises(SystemExit) as raised:
                main(["--source", str(source), "--apply"])

        self.assertIn("--confirm-write is required", str(raised.exception))

    def test_main_dry_run_reports_planned_tag_dictionary_not_current_settings(self) -> None:
        class FakeSettingsService:
            def get_settings_payload(self) -> dict[str, object]:
                return {
                    "bank_transaction_tags": {
                        "version": 1,
                        "definitions": [
                            {"code": "fee", "label": "修复前手续费", "source": "system", "status": "active"},
                        ],
                    }
                }

        class FakeApplication:
            _app_settings_service = FakeSettingsService()

        planned_result = {
            "old_version": 1,
            "new_version": 2,
            "changes": {
                "changed": True,
                "source": {"source_name": "rules.xlsx"},
                "reused_codes": ["fee"],
                "added_codes": [],
                "archived_codes": [],
                "recovered_legacy_external_turnover_codes": [],
                "skipped_rows": [],
            },
            "tag_dictionary": {
                "version": 2,
                "definitions": [
                    {
                        "code": "fee",
                        "label": "修复后手续费",
                        "source": "system",
                        "status": "active",
                        "rules": {"contains_any": ["手续费"]},
                    },
                ],
            },
        }
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "rules.xlsx"
            source.write_bytes(b"not parsed because build_restore_plan is mocked")
            stdout = StringIO()
            with (
                patch("fin_ops_platform.tools.restore_bank_auto_tag_rules.build_application", return_value=FakeApplication()),
                patch("fin_ops_platform.tools.restore_bank_auto_tag_rules.build_restore_plan", return_value=planned_result),
                patch("sys.stdout", stdout),
            ):
                self.assertEqual(main(["--source", str(source)]), 0)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["critical_code_status"]["fee"]["label"], "修复后手续费")

    def test_write_settings_backup_records_source_hash_and_settings_snapshot(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "rules.xlsx"
            source.write_bytes(b"rules")

            backup_path = write_settings_backup(
                {"bank_transaction_tags": {"version": 7, "definitions": []}},
                backup_dir=root / "backups",
                actor_id="tester",
                source=source,
            )

            payload = json.loads(backup_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["actor_id"], "tester")
            self.assertEqual(payload["source"], str(source))
            self.assertEqual(payload["source_sha256"], "6c621d1a05138a7888d37d9269a9da8e2e11e4aced2f6cfd24b05ab1b9e61bb0")
            self.assertEqual(payload["settings"]["bank_transaction_tags"]["version"], 7)


if __name__ == "__main__":
    unittest.main()
