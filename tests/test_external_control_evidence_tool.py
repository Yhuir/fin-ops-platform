from __future__ import annotations

from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fin_ops_platform.tools import external_control_evidence as tool
from tests.external_evidence_test_support import ARTIFACT_BYTES, bank_item, manifest_payload


class _Repository:
    def __init__(self, _connection) -> None:
        pass

    def register(self, manifest, *, actor: str, reason: str):
        return {
            "evidence_id": "evidence-1",
            "domain": manifest.domain,
            "manifest_fingerprint": manifest.manifest_fingerprint,
            "created": True,
        }

    def revoke(self, evidence_id: str, *, actor: str, reason: str):
        return {"evidence_id": evidence_id, "revoked": True}

    def inspect(self, *, tenant_id: str, domain: str | None = None):
        return [{"evidence_id": "evidence-1", "domain": domain or "bank", "tenant_id": tenant_id}]


class ExternalControlEvidenceToolTests(unittest.TestCase):
    def _files(self, *, artifact_bytes: bytes = ARTIFACT_BYTES):
        temp_dir = tempfile.TemporaryDirectory()
        root = Path(temp_dir.name)
        artifact = root / "source.bin"
        artifact.write_bytes(artifact_bytes)
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(manifest_payload("bank", [bank_item()])), encoding="utf-8")
        return temp_dir, manifest, artifact

    def test_validate_and_register_dry_run_do_not_connect_to_postgres(self) -> None:
        temp_dir, manifest, artifact = self._files()
        self.addCleanup(temp_dir.cleanup)
        for command in ("validate", "register"):
            stdout = StringIO()
            argv = [command, "--manifest", str(manifest), "--artifact", str(artifact)]
            if command == "register":
                argv.extend(["--actor", "operator", "--reason", "reviewed", "--dry-run"])
            code = tool.main(argv, stdout=stdout, connection_factory=lambda: self.fail("must not connect"))
            payload = json.loads(stdout.getvalue())
            self.assertEqual(code, 0)
            self.assertEqual(payload["status"], "validated")
            self.assertFalse(payload["write_applied"])
            self.assertNotIn("items", payload["manifest"])

    def test_artifact_mismatch_fails_before_database_connection(self) -> None:
        temp_dir, manifest, _artifact = self._files()
        self.addCleanup(temp_dir.cleanup)
        wrong_artifact = Path(temp_dir.name) / "wrong.bin"
        wrong_artifact.write_bytes(b"wrong")
        stderr = StringIO()

        code = tool.main(
            ["validate", "--manifest", str(manifest), "--artifact", str(wrong_artifact)],
            stderr=stderr,
            connection_factory=lambda: self.fail("must not connect"),
        )

        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stderr.getvalue())["status"], "input_error")

    def test_apply_register_revoke_and_inspect_use_repository_boundary(self) -> None:
        temp_dir, manifest, artifact = self._files()
        self.addCleanup(temp_dir.cleanup)
        with patch.object(tool, "PostgresExternalControlEvidenceRepository", _Repository):
            stdout = StringIO()
            code = tool.main(
                [
                    "register",
                    "--manifest",
                    str(manifest),
                    "--artifact",
                    str(artifact),
                    "--actor",
                    "operator",
                    "--reason",
                    "reviewed",
                    "--apply",
                ],
                stdout=stdout,
                connection_factory=lambda: object(),
            )
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(stdout.getvalue())["write_applied"])

            stdout = StringIO()
            code = tool.main(
                ["revoke", "--evidence-id", "evidence-1", "--actor", "operator", "--reason", "bad", "--apply"],
                stdout=stdout,
                connection_factory=lambda: object(),
            )
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(stdout.getvalue())["result"]["revoked"])

            stdout = StringIO()
            code = tool.main(
                ["inspect", "--domain", "bank"],
                stdout=stdout,
                connection_factory=lambda: object(),
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["evidence"][0]["domain"], "bank")


if __name__ == "__main__":
    unittest.main()
