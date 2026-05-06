from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

from fin_ops_platform.services.app_health_alert_service import AppHealthAlertService


class AppHealthAlertServiceTests(unittest.TestCase):
    def test_dirty_scope_warning_and_critical_thresholds(self) -> None:
        service = AppHealthAlertService()

        warning = service.evaluate(
            {
                "oa_sync": {"dirty_scopes": ["all"], "lag_seconds": 301},
                "metrics": {"dirty_scope_age_seconds": {"all": 301}},
                "workbench_read_model": {"status": "stale"},
                "background_jobs": {"jobs": []},
                "dependencies": {},
                "session": {"status": "authenticated"},
            }
        )
        critical = service.evaluate(
            {
                "oa_sync": {"dirty_scopes": ["all"], "lag_seconds": 901},
                "metrics": {"dirty_scope_age_seconds": {"all": 901}},
                "workbench_read_model": {"status": "stale"},
                "background_jobs": {"jobs": []},
                "dependencies": {},
                "session": {"status": "authenticated"},
            }
        )

        self.assertEqual(warning["active"][0]["severity"], "warning")
        self.assertEqual(critical["active"][0]["severity"], "critical")

    def test_dependency_unavailable_creates_critical_alert(self) -> None:
        service = AppHealthAlertService()

        result = service.evaluate(
            {
                "oa_sync": {"dirty_scopes": []},
                "metrics": {},
                "workbench_read_model": {"status": "error"},
                "background_jobs": {"jobs": []},
                "dependencies": {"oa_sync": {"status": "unavailable", "message": "OA 同步失败"}},
                "session": {"status": "authenticated"},
            }
        )

        self.assertEqual(len(result["active"]), 1)
        self.assertEqual(result["active"][0]["kind"], "dependency_unavailable")
        self.assertEqual(result["active"][0]["severity"], "critical")

    def test_alert_recovers_when_condition_clears(self) -> None:
        service = AppHealthAlertService()
        service.evaluate(
            {
                "oa_sync": {"dirty_scopes": ["all"], "lag_seconds": 901},
                "metrics": {"dirty_scope_age_seconds": {"all": 901}},
                "workbench_read_model": {"status": "stale"},
                "background_jobs": {"jobs": []},
                "dependencies": {},
                "session": {"status": "authenticated"},
            }
        )

        result = service.evaluate(
            {
                "oa_sync": {"dirty_scopes": []},
                "metrics": {},
                "workbench_read_model": {"status": "ready"},
                "background_jobs": {"jobs": []},
                "dependencies": {},
                "session": {"status": "authenticated"},
            }
        )

        self.assertEqual(result["active"], [])
        self.assertEqual(len(result["recent_recovered"]), 1)
        self.assertEqual(result["recent_recovered"][0]["status"], "recovered")

    def test_long_running_background_job_creates_warning(self) -> None:
        service = AppHealthAlertService()
        now = datetime.now(UTC)

        result = service.evaluate(
            {
                "oa_sync": {"dirty_scopes": []},
                "metrics": {},
                "workbench_read_model": {"status": "ready"},
                "background_jobs": {
                    "jobs": [
                        {
                            "job_id": "job_1",
                            "label": "导入发票",
                            "status": "running",
                            "started_at": (now - timedelta(minutes=11)).isoformat(),
                        }
                    ]
                },
                "dependencies": {},
                "session": {"status": "authenticated"},
            },
            now=now,
        )

        self.assertEqual(len(result["active"]), 1)
        self.assertEqual(result["active"][0]["kind"], "background_job_long_running")
        self.assertEqual(result["active"][0]["severity"], "warning")


if __name__ == "__main__":
    unittest.main()
