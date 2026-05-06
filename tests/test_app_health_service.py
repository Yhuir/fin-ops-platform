from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import unittest

from fin_ops_platform.services.app_health_service import APP_HEALTH_SCHEMA_VERSION, AppHealthService


@dataclass(slots=True)
class FakeIdentity:
    user_id: str = "u1"
    username: str = "tester"
    display_name: str = "测试用户"


@dataclass(slots=True)
class FakeSession:
    identity: FakeIdentity
    allowed: bool = True
    access_tier: str = "admin"
    can_access_app: bool = True
    can_mutate_data: bool = True
    can_admin_access: bool = True


@dataclass(slots=True)
class FakeJob:
    job_id: str
    type: str
    status: str
    created_at: str
    started_at: str | None = None
    label: str = "后台任务"

    def to_payload(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "type": self.type,
            "status": self.status,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "label": self.label,
        }


class AppHealthServiceTests(unittest.TestCase):
    def test_build_snapshot_reports_idle_ok_with_version_metrics_and_alerts(self) -> None:
        service = AppHealthService()

        snapshot = service.build_snapshot(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            oa_sync_payload={"status": "synced", "message": "OA 已同步", "dirty_scopes": []},
            state_store_info={"storage_mode": "auto", "backend": "local_pickle"},
            rebuild_scheduled=False,
            duration_ms=12.345,
            alerts={"active": [], "recent_recovered": []},
        )

        self.assertEqual(snapshot["version"], APP_HEALTH_SCHEMA_VERSION)
        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(snapshot["workbench_read_model"]["status"], "ready")
        self.assertEqual(snapshot["metrics"]["app_health_duration_ms"], 12.35)
        self.assertEqual(snapshot["alerts"]["active"], [])

    def test_dirty_scope_marks_busy_stale_and_tracks_age(self) -> None:
        service = AppHealthService()

        snapshot = service.build_snapshot(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            oa_sync_payload={
                "status": "refreshing",
                "dirty_scopes": ["all"],
                "lag_seconds": 321,
            },
            state_store_info={},
            rebuild_scheduled=False,
            duration_ms=1,
        )

        self.assertEqual(snapshot["status"], "busy")
        self.assertEqual(snapshot["workbench_read_model"]["status"], "stale")
        self.assertEqual(snapshot["metrics"]["dirty_scope_age_seconds"], {"all": 321.0})

    def test_rebuild_job_marks_read_model_rebuilding(self) -> None:
        service = AppHealthService()
        now = datetime.now(UTC)
        job = FakeJob(
            job_id="job_1",
            type="workbench_rebuild",
            status="running",
            created_at=(now - timedelta(minutes=8)).isoformat(),
            started_at=(now - timedelta(minutes=8)).isoformat(),
        )

        snapshot = service.build_snapshot(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[job],
            oa_sync_payload={"status": "synced", "dirty_scopes": []},
            state_store_info={},
            rebuild_scheduled=False,
            duration_ms=1,
            generated_at=now,
        )

        self.assertEqual(snapshot["status"], "busy")
        self.assertEqual(snapshot["workbench_read_model"]["status"], "rebuilding")
        self.assertEqual(snapshot["workbench_read_model"]["rebuild_job_ids"], ["job_1"])
        self.assertGreaterEqual(snapshot["metrics"]["workbench_rebuild_running_seconds_max"], 480)

    def test_dependency_error_marks_blocked(self) -> None:
        service = AppHealthService()

        snapshot = service.build_snapshot(
            session=FakeSession(identity=FakeIdentity()),
            active_jobs=[],
            oa_sync_payload={"status": "error", "message": "OA 同步失败", "dirty_scopes": []},
            state_store_info={},
            rebuild_scheduled=False,
            duration_ms=1,
        )

        self.assertEqual(snapshot["status"], "blocked")
        self.assertEqual(snapshot["dependencies"]["oa_sync"]["status"], "unavailable")
        self.assertEqual(snapshot["workbench_read_model"]["status"], "error")

    def test_sse_event_serializes_named_event(self) -> None:
        body = AppHealthService.serialize_sse_event("app_health", {"status": "ok"})

        self.assertTrue(body.startswith("event: app_health\n"))
        self.assertEqual(json.loads(body.split("data: ", 1)[1]), {"status": "ok"})


if __name__ == "__main__":
    unittest.main()
