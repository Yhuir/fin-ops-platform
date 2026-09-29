from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location("frontend_assets", Path(__file__).parents[1] / "scripts/frontend_assets.py")
assert SPEC and SPEC.loader
assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assets)


class FrontendAssetsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.releases = self.root / "releases"
        self.now = time.time()
        self.a = self.build("A")
        self.dist = self.root / "live/dist"
        shutil.copytree(self.a, self.dist)
        self.publisher = assets.FrontendAssets(self.dist)

    def build(self, name, files=None):
        dist = self.releases / name / "src/web/dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text(f'<script src="/fin-ops/assets/{name}.js"></script>')
        for filename, body in (files or {f"{name}.js": name, f"{name}.css": name, "shared.js": "shared"}).items():
            (dist / "assets" / filename).write_text(body)
        return dist

    def publish(self, source, days=0):
        self.publisher.publish(source, self.releases, self.now + days * 86400)

    def test_publish_retains_old_lazy_chunks_and_css_and_verifies_new_release(self):
        b = self.build("B")
        self.publish(b)
        self.publisher.verify(b)
        for file in ("A.js", "A.css", "B.js", "B.css", "shared.js"):
            self.assertTrue((self.dist / "assets" / file).is_file())
        self.assertEqual((self.dist / "index.html").read_bytes(), (b / "index.html").read_bytes())

    def test_first_publish_recovers_recent_previous_build_not_only_current(self):
        old = self.build("older")
        self.publish(self.build("B"))
        self.assertEqual((self.dist / "assets/older.js").read_bytes(), (old / "assets/older.js").read_bytes())

    def test_partial_asset_copy_never_switches_html_and_can_resume(self):
        self.publisher.bootstrap(self.releases, self.now)
        b = self.build("B")
        original = assets.atomic_write

        def fail_one(path, data, mode=0o644):
            if path.name == "B.js":
                raise OSError("disk full")
            original(path, data, mode)

        with patch.object(assets, "atomic_write", side_effect=fail_one), self.assertRaises(OSError):
            self.publish(b)
        self.assertEqual((self.dist / "index.html").read_bytes(), (self.a / "index.html").read_bytes())
        self.publish(b)
        self.publisher.verify(b)

    def test_interruption_before_html_replace_keeps_old_entry_and_resumes(self):
        b = self.build("B")
        original = assets.atomic_write

        def fail_index(path, data, mode=0o644):
            if path == self.dist / "index.html":
                raise OSError("interrupted")
            original(path, data, mode)

        with patch.object(assets, "atomic_write", side_effect=fail_index), self.assertRaises(OSError):
            self.publish(b)
        self.publisher.verify(self.a)
        self.publish(b)
        self.publisher.verify(b)

    def test_rollback_keeps_new_browser_resources_and_is_idempotent(self):
        b = self.build("B")
        self.publish(b)
        self.publish(self.a)
        self.publish(self.a)
        self.publisher.verify(self.a)
        self.assertTrue((self.dist / "assets/B.js").is_file())

    def test_retention_starts_when_active_build_retires(self):
        self.publish(self.a)
        self.publish(self.build("B"), days=100)
        self.publish(self.build("C"), days=101)
        self.publisher.cleanup(self.now + 106 * 86400)
        self.assertTrue((self.dist / "assets/A.js").exists())
        self.publisher.cleanup(self.now + 108 * 86400)
        self.assertFalse((self.dist / "assets/A.js").exists())
        self.assertTrue((self.dist / "assets/B.js").exists())  # rollback version
        self.assertTrue((self.dist / "assets/C.js").exists())  # active
        self.assertTrue((self.dist / "assets/shared.js").exists())

    def test_backend_release_pruning_does_not_remove_published_assets(self):
        self.publish(self.build("B"))
        shutil.rmtree(self.a.parents[1])
        self.publish(self.build("C"))
        self.assertTrue((self.dist / "assets/A.js").exists())

    def test_inventory_cleanup_is_repeatable(self):
        self.publish(self.build("B"))
        self.publish(self.build("C"), days=1)
        self.publisher.cleanup(self.now + 9 * 86400)
        first = self.publisher.load()
        self.publisher.cleanup(self.now + 9 * 86400)
        self.assertEqual(self.publisher.load(), first)
        self.assertNotIn("A", first["versions"])

    def test_unknown_files_are_rejected_and_never_deleted(self):
        self.publish(self.build("B"))
        stray = self.dist / "assets/unmanaged.js"
        stray.write_text("unmanaged")
        with self.assertRaisesRegex(ValueError, "unmanaged"):
            self.publisher.verify(self.releases / "B/src/web/dist")
        self.publisher.cleanup(self.now + 100 * 86400)
        self.assertTrue(stray.exists())

    def test_conflicting_immutable_asset_never_overwrites_live_content(self):
        b = self.build("B", {"shared.js": "changed", "B.js": "B"})
        with self.assertRaisesRegex(ValueError, "conflict"):
            self.publish(b)
        self.assertEqual((self.dist / "assets/shared.js").read_text(), "shared")
        self.assertEqual((self.dist / "index.html").read_bytes(), (self.a / "index.html").read_bytes())

    def test_missing_current_build_refuses_bootstrap(self):
        shutil.rmtree(self.a)
        with self.assertRaisesRegex(ValueError, "no intact release"):
            self.publish(self.build("B"))

    def test_index_remains_complete_during_repeated_publication(self):
        b = self.build("B")
        valid = {(self.a / "index.html").read_bytes(), (b / "index.html").read_bytes()}
        stop = Event()
        samples = []

        def read_entries():
            while not stop.is_set():
                samples.append((self.dist / "index.html").read_bytes())

        with ThreadPoolExecutor(max_workers=1) as pool:
            reader = pool.submit(read_entries)
            try:
                for source in [b, self.a] * 5:
                    self.publish(source)
            finally:
                stop.set()
            reader.result()
        self.assertGreater(len(samples), 0)
        self.assertTrue(all(value in valid for value in samples))

    def test_cleanup_failure_surfaces_and_preserves_current_release(self):
        b = self.build("B")
        c = self.build("C")
        self.publish(b)
        self.publish(c, days=1)
        original = Path.unlink

        def reject_old(path, *args, **kwargs):
            if path.name == "A.js":
                raise PermissionError("cannot remove old asset")
            return original(path, *args, **kwargs)

        with patch.object(Path, "unlink", reject_old), self.assertRaises(PermissionError):
            self.publisher.cleanup(self.now + 9 * 86400)
        self.publisher.verify(c)
        # A partially completed cleanup must not require a pruned old release on next publish.
        shutil.rmtree(self.a.parents[1])
        self.publish(self.build("D"), days=10)
        self.publisher.cleanup(self.now + 10 * 86400)
        self.publisher.verify(self.releases / "D/src/web/dist")

    def test_invalid_path_or_symlink_cannot_escape_resource_directory(self):
        for name in ("../outside", "/etc/passwd", "assets/../../outside"):
            with self.assertRaises(ValueError):
                assets.asset_path(self.dist, name)
        (self.dist / "assets/link.js").symlink_to(self.root / "outside")
        with self.assertRaises(ValueError):
            assets.asset_path(self.dist, "assets/link.js")

    def test_corrupted_inventory_is_not_silently_reset(self):
        self.publisher.inventory_path.write_text("invalid json")
        with self.assertRaises(json.JSONDecodeError):
            self.publish(self.build("B"))

    def test_verify_detects_missing_or_changed_current_resource(self):
        b = self.build("B")
        self.publish(b)
        (self.dist / "assets/B.js").write_text("corrupted")
        with self.assertRaisesRegex(ValueError, "differs"):
            self.publisher.verify(b)
        (self.dist / "assets/B.js").unlink()
        with self.assertRaises(FileNotFoundError):
            self.publisher.verify(b)


if __name__ == "__main__":
    unittest.main()
