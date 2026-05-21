from __future__ import annotations

import io
import os
import subprocess
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch
import unittest

from fin_ops_platform.tools import run_runtime_convergence_closure as closure


class RuntimeConvergenceClosureTests(unittest.TestCase):
    def test_static_snapshot_fallbacks_are_classified(self) -> None:
        result = closure._check_static_snapshot_fallbacks()

        self.assertEqual(result.status, closure.PASS)
        self.assertIn("classified", result.metadata or {})

    def test_missing_real_infra_is_skip_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = closure._check_postgres(require_real_infra=False)

        self.assertEqual(result.status, closure.SKIP)

    def test_missing_real_infra_fails_when_required(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = closure._check_postgres(require_real_infra=True)

        self.assertEqual(result.status, closure.FAIL)

    def test_oa_source_requires_mongo_projection_source_config(self) -> None:
        with patch.dict(os.environ, {"FIN_OPS_OA_BASE_URL": "https://oa.example.invalid"}, clear=True):
            result = closure._check_oa_source(require_real_infra=True)

        self.assertEqual(result.status, closure.FAIL)
        self.assertIn("FIN_OPS_OA_MONGO_HOST", result.detail)

    def test_file_object_migration_requires_app_mongo_config(self) -> None:
        with patch.dict(
            os.environ,
            {
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://finops:secret@127.0.0.1:5432/fin_ops_test",
                "OBJECT_STORAGE_BACKEND": "minio",
                "S3_ENDPOINT_URL": "http://127.0.0.1:9000",
                "S3_BUCKET": "fin-ops",
                "S3_ACCESS_KEY_ID": "key",
                "S3_SECRET_ACCESS_KEY": "secret",
            },
            clear=True,
        ):
            result = closure._check_file_object_migration(require_real_infra=True)

        self.assertEqual(result.status, closure.FAIL)
        self.assertIn("FIN_OPS_APP_MONGO_HOST", result.detail)

    def test_file_object_migration_smoke_runs_when_app_mongo_is_present(self) -> None:
        calls: list[list[str]] = []

        def fake_run(command, **_kwargs):
            calls.append(list(command))
            if "fin_ops_platform.app.worker" in command and len([call for call in calls if "fin_ops_platform.app.worker" in call]) >= 2:
                FakeObjectStorage.cleaned = True
            return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}\n', stderr="")

        class FakeObjectStorage:
            cleaned = False
            migrated_key = "objects/gridfs/gridfs-id/test/file.txt"
            temp_body = b""

            def __init__(self, _settings):
                pass

            def put_object(self, key, body, *, content_type=None):  # noqa: ARG002
                FakeObjectStorage.temp_body = bytes(body)

            def get_object(self, key):
                if FakeObjectStorage.cleaned:
                    raise RuntimeError("not found")
                if key == FakeObjectStorage.migrated_key:
                    return FakeObjectStorage.temp_body
                return FakeObjectStorage.temp_body

        with patch.dict(
            os.environ,
            {
                "FIN_OPS_APP_MONGO_HOST": "127.0.0.1",
                "FIN_OPS_APP_MONGO_DATABASE": "app",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://finops:secret@127.0.0.1:5432/fin_ops_test",
                "OBJECT_STORAGE_BACKEND": "minio",
                "S3_ENDPOINT_URL": "http://127.0.0.1:9000",
                "S3_BUCKET": "fin-ops",
                "S3_ACCESS_KEY_ID": "key",
                "S3_SECRET_ACCESS_KEY": "secret",
            },
            clear=True,
        ), patch.object(closure, "_run", side_effect=fake_run), patch.object(
            closure.migrate,
            "run_psql",
            return_value=FakeObjectStorage.migrated_key,
        ), patch.object(
            closure,
            "S3ObjectStorageRepository",
            FakeObjectStorage,
        ):
            result = closure._check_file_object_migration(require_real_infra=True)

        self.assertEqual(result.status, closure.PASS)
        self.assertIn("GridFS backfill", result.detail)
        self.assertTrue(any("fin_ops_platform.app.worker" in command for command in calls for command in command))

    def test_oa_source_smoke_runs_when_mongo_config_is_present(self) -> None:
        def fake_run(*_args, **_kwargs):
            return subprocess.CompletedProcess(
                ["python"],
                0,
                stdout='{"month_count": 1, "sample_month": "2026-05", "sample_record_count": 1, "status": "ready"}\n',
                stderr="",
            )

        with patch.dict(
            os.environ,
            {
                "FIN_OPS_OA_MONGO_HOST": "127.0.0.1",
                "FIN_OPS_OA_MONGO_DATABASE": "oa",
                "FIN_OPS_POSTGRES_DATABASE_URL": "postgresql://finops:secret@127.0.0.1:5432/fin_ops_test",
            },
            clear=True,
        ), patch.object(closure, "_run", side_effect=fake_run), patch.object(
            closure.migrate,
            "run_psql",
            return_value='{"oa_sync_done_count":1,"oa_projection_rows":1,"oa_sync_runs":1,"dirty_scope_count":1}',
        ):
            result = closure._check_oa_source(require_real_infra=True)

        self.assertEqual(result.status, closure.PASS)
        self.assertIn("oa.sync worker projection smoke passed", result.detail)

    def test_overall_status_reports_skip_when_any_check_is_skipped(self) -> None:
        checks = [
            closure.CheckResult("a", closure.PASS, "ok"),
            closure.CheckResult("b", closure.SKIP, "missing"),
        ]

        self.assertEqual(closure._overall_status(checks), closure.SKIP)

    def test_overall_status_reports_fail_when_any_check_fails(self) -> None:
        checks = [
            closure.CheckResult("a", closure.PASS, "ok"),
            closure.CheckResult("b", closure.FAIL, "bad"),
            closure.CheckResult("c", closure.SKIP, "missing"),
        ]

        self.assertEqual(closure._overall_status(checks), closure.FAIL)

    def test_report_output_file_is_written(self) -> None:
        output = Path("docs/database-migration/reports/runtime-convergence-closure-test.json")
        try:
            with patch.object(
                closure,
                "run_checks",
                return_value=[closure.CheckResult("static", closure.PASS, "ok")],
            ):
                with redirect_stdout(io.StringIO()):
                    code = closure.main(["--json", "--output", str(output)], stdout=io.StringIO())

            self.assertEqual(code, 0)
            self.assertIn('"status": "pass"', output.read_text(encoding="utf-8"))
        finally:
            output.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
