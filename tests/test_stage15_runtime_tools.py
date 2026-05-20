from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import run_controlled_mirror_write_rehearsal, run_runtime_state_policy_preflight


class FakeConnection:
    def __init__(self) -> None:
        self.counts = {
            "job.background_jobs": 0,
            "audit.app_health_alerts": 0,
            "app.app_settings.runtime_state": 0,
        }

    def fetch_all(self, _sql: str, _params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        return [{"table_name": key, "row_count": value} for key, value in self.counts.items()]


class FakeStore:
    def __init__(
        self,
        *,
        jobs: dict[str, dict[str, object]] | None = None,
        alerts: dict[str, object] | None = None,
        backend: str = "fake",
    ) -> None:
        self._jobs = dict(jobs or {})
        self._alerts = dict(alerts or {"records": {}})
        self.storage_backend = backend
        self.saved_background_jobs: list[dict[str, object]] = []
        self.saved_app_health_alerts: list[dict[str, object]] = []
        self._connection = FakeConnection()
        self.data_dir = Path("/tmp/fake")

    def load_background_jobs(self) -> dict[str, dict[str, object]]:
        return dict(self._jobs)

    def load_app_health_alerts(self) -> dict[str, object]:
        return dict(self._alerts)

    def save_background_jobs(self, snapshot: dict[str, object]) -> None:
        self.saved_background_jobs.append(dict(snapshot))
        self._jobs = dict(snapshot)  # type: ignore[assignment]
        self._connection.counts["job.background_jobs"] = len(snapshot)
        self._connection.counts["app.app_settings.runtime_state"] = 2

    def save_app_health_alerts(self, snapshot: dict[str, object]) -> None:
        self.saved_app_health_alerts.append(dict(snapshot))
        self._alerts = dict(snapshot)
        records = snapshot.get("records") if isinstance(snapshot.get("records"), dict) else snapshot
        self._connection.counts["audit.app_health_alerts"] = len(records)
        self._connection.counts["app.app_settings.runtime_state"] = 2


def queued_job() -> dict[str, object]:
    return {"type": "file_import", "status": "queued", "created_at": "2026-05-20T10:00:00+00:00"}


def terminal_job() -> dict[str, object]:
    return {"type": "file_import", "status": "succeeded", "finished_at": "2026-05-20T10:00:00+00:00"}


def active_alert() -> dict[str, object]:
    return {
        "kind": "dependency_unavailable",
        "severity": "critical",
        "status": "active",
        "first_seen_at": "2026-05-20T10:00:00+00:00",
        "last_seen_at": "2026-05-20T10:00:00+00:00",
    }


class RuntimeStatePolicyPreflightToolTests(unittest.TestCase):
    def test_build_runtime_policy_report_blocks_unknown_live_payload(self) -> None:
        primary = FakeStore(jobs={"job-1": {"type": "new_kind", "status": "scheduled"}}, alerts={"records": {}})
        shadow = FakeStore(jobs={}, alerts={"records": {}})

        report = run_runtime_state_policy_preflight.build_runtime_policy_report(
            primary_store=primary,
            shadow_store=shadow,
            run_id="run-policy",
        )

        self.assertEqual(report["gate_recommendation"], "BLOCKED_RUNTIME_POLICY_UNKNOWN")
        self.assertEqual(report["summary"]["blocked_unknown_count"], 1)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("new_kind", encoded)
        self.assertIn("scheduled", encoded)
        self.assertNotIn("created_at", encoded)

    def test_build_runtime_policy_report_classifies_without_payload_leakage(self) -> None:
        primary = FakeStore(jobs={"job-1": queued_job()}, alerts={"records": {"alert-1": active_alert()}})
        shadow = FakeStore(jobs={"job-2": terminal_job()}, alerts={"records": {}})

        report = run_runtime_state_policy_preflight.build_runtime_policy_report(
            primary_store=primary,
            shadow_store=shadow,
            run_id="run-policy",
        )

        self.assertEqual(report["gate_recommendation"], "PASS")
        self.assertEqual(report["summary"]["blocked_unknown_count"], 0)
        encoded = json.dumps(report, ensure_ascii=False)
        self.assertNotIn("first_seen_at", encoded)
        self.assertNotIn("last_seen_at", encoded)
        self.assertIn("record_key_hash", encoded)

    def test_cli_rejects_write_flags_and_requires_read_only_guard(self) -> None:
        stderr = StringIO()
        exit_code = run_runtime_state_policy_preflight.main(["--execute"], stdout=StringIO(), stderr=stderr)
        self.assertEqual(exit_code, 2)

        stderr = StringIO()
        with patch.dict("os.environ", {}, clear=True):
            exit_code = run_runtime_state_policy_preflight.main(
                ["--production"],
                stdout=StringIO(),
                stderr=stderr,
                primary_store=FakeStore(),
                shadow_store=FakeStore(),
            )
        self.assertEqual(exit_code, 1)
        self.assertIn("FIN_OPS_SHADOW_REHEARSAL_READ_ONLY=1", stderr.getvalue())

    def test_cli_writes_runtime_policy_artifact(self) -> None:
        stdout = StringIO()
        with TemporaryDirectory() as temp_dir, patch.dict(
            "os.environ",
            {"FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1"},
            clear=True,
        ):
            output = Path(temp_dir) / "policy.json"
            exit_code = run_runtime_state_policy_preflight.main(
                ["--production", "--output", str(output), "--run-id", "run-policy"],
                stdout=stdout,
                stderr=StringIO(),
                primary_store=FakeStore(jobs={"job-1": queued_job()}, alerts={"records": {}}),
                shadow_store=FakeStore(),
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["run_id"], "run-policy")
            self.assertEqual(json.loads(stdout.getvalue())["redacted"], True)


class ControlledMirrorWriteRehearsalToolTests(unittest.TestCase):
    def test_dry_run_does_not_write_and_reports_bounds(self) -> None:
        primary = FakeStore(jobs={"job-1": queued_job()}, alerts={"records": {"alert-1": active_alert()}})
        mirror = FakeStore()

        report = run_controlled_mirror_write_rehearsal.build_rehearsal_report(
            primary_store=primary,
            mirror_store=mirror,
            execute=False,
            run_id="run-dry",
        )

        self.assertEqual(report["gate_recommendation"], "DRY_RUN_PASS")
        self.assertFalse(report["executed"])
        self.assertEqual(mirror.saved_background_jobs, [])
        self.assertEqual(report["plan"]["bounds"]["background_jobs"]["planned_count"], 1)

    def test_dry_run_blocks_unknown_policy(self) -> None:
        primary = FakeStore(jobs={"job-1": {"type": "unknown", "status": "queued"}}, alerts={"records": {}})
        mirror = FakeStore()

        report = run_controlled_mirror_write_rehearsal.build_rehearsal_report(
            primary_store=primary,
            mirror_store=mirror,
            execute=False,
            run_id="run-blocked",
        )

        self.assertEqual(report["gate_recommendation"], "BLOCKED_RUNTIME_POLICY_UNKNOWN")
        self.assertFalse(report["executed"])

    def test_dry_run_blocks_row_count_bounds(self) -> None:
        primary = FakeStore(jobs={"job-1": queued_job(), "job-2": terminal_job()}, alerts={"records": {}})
        mirror = FakeStore()

        report = run_controlled_mirror_write_rehearsal.build_rehearsal_report(
            primary_store=primary,
            mirror_store=mirror,
            execute=False,
            run_id="run-bound",
            max_background_jobs=1,
        )

        self.assertEqual(report["gate_recommendation"], "BLOCKED_ROW_COUNT_BOUND")

    def test_execute_requires_guards(self) -> None:
        stderr = StringIO()
        with patch.dict("os.environ", {"FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1"}, clear=True):
            exit_code = run_controlled_mirror_write_rehearsal.main(
                ["--execute", "--production"],
                stdout=StringIO(),
                stderr=stderr,
                primary_store=FakeStore(),
                mirror_store=FakeStore(),
            )

        self.assertEqual(exit_code, 1)
        self.assertIn("FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE=1", stderr.getvalue())

    def test_execute_calls_only_runtime_save_methods(self) -> None:
        primary = FakeStore(jobs={"job-1": queued_job()}, alerts={"records": {"alert-1": active_alert()}})
        mirror = FakeStore()

        with patch.dict(
            "os.environ",
            {
                "FIN_OPS_SHADOW_REHEARSAL_READ_ONLY": "1",
                "FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE": "1",
                "FIN_OPS_STAGE15_BACKUP_CONFIRMED": "1",
            },
            clear=True,
        ):
            stdout = StringIO()
            exit_code = run_controlled_mirror_write_rehearsal.main(
                ["--execute", "--production", "--run-id", "run-execute"],
                stdout=stdout,
                stderr=StringIO(),
                primary_store=primary,
                mirror_store=mirror,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(mirror.saved_background_jobs), 1)
        self.assertEqual(len(mirror.saved_app_health_alerts), 1)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["write_methods_called"], ["save_background_jobs", "save_app_health_alerts"])
        self.assertEqual(report["gate_recommendation"], "PASS")


if __name__ == "__main__":
    unittest.main()
