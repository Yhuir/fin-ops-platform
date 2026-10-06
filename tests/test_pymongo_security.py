from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit
from types import SimpleNamespace
from unittest.mock import patch

import pymongo
from bson import Decimal128, ObjectId
from gridfs import GridFSBucket

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("python_dependencies", ROOT / "scripts/python_dependencies.py")
assert SPEC and SPEC.loader
dependencies = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dependencies)


PROBE_SPEC = importlib.util.spec_from_file_location("pymongo_backport_tests", ROOT / "backend/vendor/pymongo/test_security.py")
assert PROBE_SPEC and PROBE_SPEC.loader
probe = importlib.util.module_from_spec(PROBE_SPEC)
PROBE_SPEC.loader.exec_module(probe)
DriverSecurityTests = probe.DriverSecurityTests


class DependencyAuditTests(unittest.TestCase):
    def test_prepare_preserves_existing_versions_except_explicit_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            requirements = root / "requirements.txt"
            requirements.write_text("urllib3==2.8.0\nrapidocr_onnxruntime==1.2.3\n")
            wheels = root / "wheels"
            captured = []

            def download(*args):
                self.assertIn("--only-binary=:all:", args)
                captured.extend(Path(args[args.index("-c") + 1]).read_text().splitlines())
                for name, version in (("urllib3", "2.8.0"), ("rapidocr_onnxruntime", "1.2.3"), ("numpy", "1.26.4")):
                    (wheels / f"{name}-{version}-py3-none-any.whl").write_bytes(b"prepared")

            installed = {"urllib3": "2.2.3", "rapidocr-onnxruntime": "1.2.3", "numpy": "1.26.4"}
            distributions = [SimpleNamespace(metadata={"Name": name}) for name in (*installed, "numpy")]
            with patch.object(dependencies.importlib.metadata, "distributions", return_value=distributions), patch.object(dependencies.importlib.metadata, "version", side_effect=installed.__getitem__), patch.object(dependencies, "run", side_effect=download):
                dependencies.prepare(requirements, wheels)
            self.assertEqual(captured, ["numpy==1.26.4", "rapidocr-onnxruntime==1.2.3"])
            self.assertEqual((wheels / "resolved.txt").read_text().splitlines(), ["numpy==1.26.4", "rapidocr-onnxruntime==1.2.3", "urllib3==2.8.0"])

    def report(self, *, name="pymongo", version="4.17.0", cve="CVE-2026-96749"):
        return {"dependencies": [{"name": name, "version": version, "vulns": [{"id": "GHSA-example", "aliases": [cve]}]}]}

    def test_only_exact_verified_backport_is_classified_fixed(self):
        fixed, unresolved = dependencies.classify_audit(self.report(), patched=True)
        self.assertEqual(len(fixed), 1)
        self.assertEqual(unresolved, [])
        for report, verified in ((self.report(), False), (self.report(version="4.14.1"), True), (self.report(name="another-package"), True), (self.report(cve="CVE-NEW"), True)):
            fixed, unresolved = dependencies.classify_audit(report, patched=verified)
            self.assertEqual(fixed, [])
            self.assertEqual(len(unresolved), 1)

    def test_incomplete_scanner_output_is_not_success(self):
        for report in ({}, {"dependencies": []}, {"dependencies": [{"name": "pymongo", "skip_reason": "unknown version"}]}):
            with self.assertRaises(ValueError):
                dependencies.classify_audit(report, patched=True)

    def test_wrong_patch_or_modified_wheel_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = f"pymongo-{dependencies.VERSION}-cp311-cp311-linux_x86_64.whl"
            wheel = root / name
            wheel.write_bytes(b"original")
            manifest = {
                "version": dependencies.VERSION,
                "source_sha256": dependencies.SOURCE_SHA256,
                "patch_sha256": dependencies.digest((dependencies.VENDOR / "security.patch").read_bytes()),
                "build_requirements_sha256": dependencies.digest((dependencies.VENDOR / "build-requirements.txt").read_bytes()),
                "wheel": name, "wheel_sha256": dependencies.digest(b"original"),
            }
            path = root / "pymongo-build.json"
            path.write_text(json.dumps(manifest))
            self.assertEqual(dependencies.verified_wheel(root), wheel)
            wheel.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "content changed"):
                dependencies.verified_wheel(root)
            wheel.write_bytes(b"original")
            manifest["patch_sha256"] = "wrong"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "provenance"):
                dependencies.verified_wheel(root)


@unittest.skipUnless(os.environ.get("FIN_OPS_TEST_MONGO_URI"), "requires an explicit disposable MongoDB 4.2 test instance")
class Mongo42CompatibilityTests(unittest.TestCase):
    def setUp(self):
        uri = os.environ["FIN_OPS_TEST_MONGO_URI"]
        address = urlsplit(uri)
        self.assertEqual((address.hostname, address.port), ("127.0.0.1", 27028), "only the dedicated local compatibility container is allowed")
        self.client = pymongo.MongoClient(uri, serverSelectionTimeoutMS=3000)
        self.addCleanup(self.client.close)
        self.assertEqual(self.client.server_info()["version"], "4.2.6")
        self.database = self.client[f"fin_ops_driver_test_{uuid4().hex}"]
        self.addCleanup(self.client.drop_database, self.database.name)

    def test_query_types_cursor_count_and_cash_project_contract(self):
        from fin_ops_platform.services.cash_oa_projects import CashOaProjectService
        from fin_ops_platform.services.mongo_oa_adapter import MongoOASettings

        ids = [ObjectId() for _ in range(5)]
        collection = self.database.form_data
        collection.insert_many([{"_id": identity, "form_id": "17", "data": {"name": f"项目{index}", "code": str(index), "projectPhase": "5"}, "amount": Decimal128("4426.11"), "date": datetime(2026, 6, 25), "nullable": None} for index, identity in enumerate(ids)])
        rows = list(collection.find({"form_id": "17"}).sort("_id", 1).batch_size(2))
        self.assertEqual([row["_id"] for row in rows], ids)
        self.assertEqual(rows[0]["amount"], Decimal128("4426.11"))
        self.assertEqual(rows[0]["date"], datetime(2026, 6, 25))
        self.assertIsNone(rows[0]["nullable"])
        self.assertNotIn("missing", rows[0])
        self.assertEqual(collection.count_documents({"form_id": "17"}), 5)
        settings = MongoOASettings(host="unused", database=self.database.name)
        service = CashOaProjectService(settings, lambda: {"version": 1, "allowed_stage_codes": ["5"], "configured": True}, lambda: [{"code": "5", "name": "实施"}, {"code": "end", "name": "结束"}], mongo_client=self.client)
        self.assertEqual(service.list_projects({"page_size": 2})["total"], 5)
        self.assertEqual(service.resolve_project(str(ids[0]))["id"], str(ids[0]))

    def test_gridfs_structured_id_is_matched_literally(self):
        bucket = GridFSBucket(self.database)
        identity = {"literal": "test identity"}
        bucket.upload_from_stream_with_id(identity, "literal", b"keep literal semantics")
        other = bucket.upload_from_stream("other", b"must survive")
        from gridfs.errors import NoFile
        with self.assertRaises(NoFile):
            bucket.delete({"$ne": "unrelated"})
        self.assertEqual(self.database.fs.files.count_documents({}), 2)
        bucket.delete(identity)
        self.assertIsNone(self.database.fs.files.find_one({"_id": {"$eq": identity}}))
        with bucket.open_download_stream(other) as stream:
            self.assertEqual(stream.read(), b"must survive")


if __name__ == "__main__":
    unittest.main()
