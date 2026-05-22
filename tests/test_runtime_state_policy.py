from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.services.runtime_state_policy import (
    BLOCKED_UNKNOWN,
    CLEANUP_CANDIDATE,
    MIRROR_WRITE_REQUIRED,
    REBUILDABLE,
    RETENTION_ONLY,
    classify_app_health_alert,
    classify_background_job,
)


class RuntimeStatePolicyTests(unittest.TestCase):
    def test_active_background_jobs_require_mirror_write(self) -> None:
        for status in ("queued", "running"):
            with self.subTest(status=status):
                decision = classify_background_job({"type": "file_import", "status": status})

                self.assertEqual(decision.classification, MIRROR_WRITE_REQUIRED)
                self.assertTrue(decision.mirror_write_required)
                self.assertFalse(decision.cutover_blocking)

    def test_unacknowledged_attention_jobs_require_mirror_write(self) -> None:
        for status in ("failed", "partial_success"):
            with self.subTest(status=status):
                decision = classify_background_job({"type": "workbench_matching", "status": status})

                self.assertEqual(decision.classification, MIRROR_WRITE_REQUIRED)
                self.assertTrue(decision.mirror_write_required)

    def test_terminal_background_jobs_are_retention_only(self) -> None:
        for status in ("succeeded", "cancelled", "acknowledged", "superseded"):
            with self.subTest(status=status):
                decision = classify_background_job(
                    {
                        "type": "etc_invoice_import",
                        "status": status,
                        "finished_at": "2026-05-20T10:00:00+00:00",
                    }
                )

                self.assertEqual(decision.classification, RETENTION_ONLY)
                self.assertFalse(decision.mirror_write_required)

    def test_shadow_only_terminal_background_job_is_cleanup_candidate(self) -> None:
        decision = classify_background_job(
            {
                "type": "file_import",
                "status": "succeeded",
                "finished_at": "2026-05-20T10:00:00+00:00",
            },
            present_in_primary=False,
            present_in_shadow=True,
        )

        self.assertEqual(decision.classification, CLEANUP_CANDIDATE)
        self.assertFalse(decision.cutover_blocking)

    def test_terminal_derived_background_job_with_scope_is_rebuildable(self) -> None:
        decision = classify_background_job(
            {
                "type": "workbench_matching",
                "status": "succeeded",
                "affected_months": ["2026-05"],
                "finished_at": "2026-05-20T10:00:00+00:00",
            }
        )

        self.assertEqual(decision.classification, REBUILDABLE)

    def test_unknown_background_job_status_or_type_blocks(self) -> None:
        for payload in (
            {"type": "file_import", "status": "scheduled"},
            {"type": "unknown_job", "status": "succeeded"},
            {"status": "succeeded"},
        ):
            with self.subTest(payload=payload):
                decision = classify_background_job(payload)

                self.assertEqual(decision.classification, BLOCKED_UNKNOWN)
                self.assertTrue(decision.cutover_blocking)

    def test_shadow_only_terminal_job_without_timestamp_blocks_cleanup(self) -> None:
        decision = classify_background_job(
            {"type": "file_import", "status": "succeeded"},
            present_in_primary=False,
            present_in_shadow=True,
        )

        self.assertEqual(decision.classification, BLOCKED_UNKNOWN)
        self.assertTrue(decision.cutover_blocking)

    def test_active_app_health_alerts_require_mirror_write(self) -> None:
        for severity in ("critical", "warning"):
            with self.subTest(severity=severity):
                decision = classify_app_health_alert(
                    {
                        "kind": "dependency_unavailable",
                        "severity": severity,
                        "status": "active",
                    }
                )

                self.assertEqual(decision.classification, MIRROR_WRITE_REQUIRED)
                self.assertTrue(decision.mirror_write_required)

    def test_recovered_app_health_alerts_are_retention_only(self) -> None:
        decision = classify_app_health_alert(
            {
                "kind": "background_job_long_running",
                "severity": "warning",
                "status": "recovered",
            }
        )

        self.assertEqual(decision.classification, RETENTION_ONLY)
        self.assertFalse(decision.mirror_write_required)

    def test_shadow_only_recovered_app_health_alert_is_cleanup_candidate(self) -> None:
        decision = classify_app_health_alert(
            {
                "kind": "workbench_rebuild_long_running",
                "severity": "warning",
                "status": "recovered",
            },
            present_in_primary=False,
            present_in_shadow=True,
        )

        self.assertEqual(decision.classification, CLEANUP_CANDIDATE)

    def test_unknown_app_health_alert_shape_blocks(self) -> None:
        for payload in (
            {"kind": "snapshot", "severity": "warning", "status": "active"},
            {"kind": "session_blocked", "severity": "unknown", "status": "active"},
            {"kind": "session_blocked", "severity": "critical", "status": "acknowledged"},
        ):
            with self.subTest(payload=payload):
                decision = classify_app_health_alert(payload)

                self.assertEqual(decision.classification, BLOCKED_UNKNOWN)
                self.assertTrue(decision.cutover_blocking)

    def test_production_worker_refresh_paths_do_not_use_application_or_snapshot_fallback(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        production_worker_files = [
            repository_root / "backend/src/fin_ops_platform/app/worker.py",
            repository_root / "backend/src/fin_ops_platform/services/workbench_read_model_refresh.py",
            repository_root / "backend/src/fin_ops_platform/services/cost_statistics_read_model_refresh.py",
            repository_root / "backend/src/fin_ops_platform/services/tax_offset_read_model_refresh.py",
            repository_root / "backend/src/fin_ops_platform/services/search_pending_read_model_refresh.py",
            repository_root / "backend/src/fin_ops_platform/services/workbench_sql_projection.py",
            repository_root / "backend/src/fin_ops_platform/services/cost_tax_sql_projection.py",
            repository_root / "backend/src/fin_ops_platform/services/search_pending_sql_projection.py",
        ]
        forbidden_tokens = (
            "build_application",
            ".load()",
            "StateStore.load",
            "ApplicationStateStore.load",
            "PostgresStateStore.load",
            "state:",
        )

        for path in production_worker_files:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path)):
                for token in forbidden_tokens:
                    self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
