from __future__ import annotations

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES_DIR = REPO_ROOT / "docs" / "modules"
MODULE_INDEX_PATH = MODULES_DIR / "README.md"
SPEC_FIRST_INVENTORY_PATH = REPO_ROOT / "docs" / "dev" / "spec-first-e2e-inventory.md"
SPEC_ID_PATTERN = re.compile(r"\b[A-Z][A-Z0-9-]*-E2E-\d{3}\b")
BROWSER_EVIDENCE_PATH_PATTERN = re.compile(r"web/e2e/[A-Za-z0-9_./*-]+")


def _module_dirs() -> list[Path]:
    return sorted(path.parent for path in MODULES_DIR.glob("*/README.md"))


def _module_keys_from_index() -> set[str]:
    index = MODULE_INDEX_PATH.read_text(encoding="utf-8")
    keys = set(re.findall(r"^\| `([^`]+)` \|", index, re.MULTILINE))
    if not keys:
        raise AssertionError("Could not find module rows in docs/modules/README.md")
    return keys


def _spec_ids(path: Path) -> set[str]:
    return set(SPEC_ID_PATTERN.findall(path.read_text(encoding="utf-8")))


def _browser_evidence_paths_by_doc() -> dict[Path, set[str]]:
    paths_by_doc: dict[Path, set[str]] = {}
    docs = [SPEC_FIRST_INVENTORY_PATH, *sorted(MODULES_DIR.glob("*/e2e-coverage.md"))]

    for doc_path in docs:
        paths = set(BROWSER_EVIDENCE_PATH_PATTERN.findall(doc_path.read_text(encoding="utf-8")))
        if paths:
            paths_by_doc[doc_path] = paths

    if not paths_by_doc:
        raise AssertionError("Could not find any Browser E2E evidence paths in Spec-first docs")
    return paths_by_doc


class SpecFirstE2EDocumentationTests(unittest.TestCase):
    def test_every_documented_module_has_spec_first_e2e_files(self) -> None:
        missing: list[str] = []
        for module_dir in _module_dirs():
            for filename in ("e2e-spec.md", "e2e-coverage.md"):
                if not (module_dir / filename).is_file():
                    missing.append(f"{module_dir.relative_to(REPO_ROOT)}/{filename}")

        self.assertEqual(
            missing,
            [],
            "Every docs/modules/<module>/README.md entry must have Spec-first E2E "
            "documentation so new pages/resources cannot skip the audit workflow.",
        )

    def test_module_index_matches_module_directories(self) -> None:
        index_keys = _module_keys_from_index()
        directory_keys = {path.name for path in _module_dirs()}

        self.assertEqual(
            sorted(directory_keys - index_keys),
            [],
            "Every docs/modules/<module>/README.md directory must be registered in docs/modules/README.md.",
        )
        self.assertEqual(
            sorted(index_keys - directory_keys),
            [],
            "Every docs/modules/README.md row must point to an existing module directory.",
        )

    def test_spec_first_inventory_mentions_every_module(self) -> None:
        inventory = SPEC_FIRST_INVENTORY_PATH.read_text(encoding="utf-8")
        missing = sorted(module_dir.name for module_dir in _module_dirs() if f"`{module_dir.name}`" not in inventory)

        self.assertEqual(
            missing,
            [],
            "Every module must appear in docs/dev/spec-first-e2e-inventory.md so "
            "the global controller can choose the next uncovered page/resource.",
        )

    def test_every_spec_id_is_mapped_in_coverage(self) -> None:
        failures: list[str] = []
        for module_dir in _module_dirs():
            spec_path = module_dir / "e2e-spec.md"
            coverage_path = module_dir / "e2e-coverage.md"
            spec_ids = _spec_ids(spec_path)
            coverage_ids = _spec_ids(coverage_path)
            if not spec_ids:
                failures.append(f"{spec_path.relative_to(REPO_ROOT)} has no Spec IDs")
                continue
            missing = sorted(spec_ids - coverage_ids)
            if missing:
                failures.append(
                    f"{coverage_path.relative_to(REPO_ROOT)} missing coverage rows for: {', '.join(missing)}"
                )

        self.assertEqual(
            failures,
            [],
            "Every Spec ID declared in e2e-spec.md must be mapped in e2e-coverage.md.",
        )

    def test_documented_browser_evidence_paths_resolve_to_current_files(self) -> None:
        failures: list[str] = []

        for doc_path, evidence_paths in _browser_evidence_paths_by_doc().items():
            for evidence_path in sorted(evidence_paths):
                if "*" in evidence_path:
                    matches = [path for path in REPO_ROOT.glob(evidence_path) if path.is_file()]
                    if not matches:
                        failures.append(
                            f"{doc_path.relative_to(REPO_ROOT)}: {evidence_path} matched no files"
                        )
                    continue

                if not (REPO_ROOT / evidence_path).is_file():
                    failures.append(f"{doc_path.relative_to(REPO_ROOT)}: {evidence_path} does not exist")

        self.assertEqual(
            failures,
            [],
            "Spec-first Browser E2E evidence paths must resolve to current files or matching globs.",
        )


if __name__ == "__main__":
    unittest.main()
