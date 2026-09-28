from __future__ import annotations

import re
import unittest
from pathlib import Path
from urllib.parse import unquote, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES = REPO_ROOT / "docs/modules"


class DocumentationTests(unittest.TestCase):
    def test_module_index_covers_current_module_documents(self) -> None:
        index = (MODULES / "README.md").read_text(encoding="utf-8")
        linked = set(re.findall(r"\]\(([^/()]+)/README\.md\)", index))
        actual = {path.parent.name for path in MODULES.glob("*/README.md")}
        self.assertTrue(actual)
        self.assertEqual(linked, actual)

    def test_documentation_local_links_resolve(self) -> None:
        documents = [
            *REPO_ROOT.glob("*.md"),
            *(REPO_ROOT / "docs").rglob("*.md"),
            REPO_ROOT / "backend/README.md",
            REPO_ROOT / "web/README.md",
            REPO_ROOT / "deploy/oa/README.md",
            REPO_ROOT / ".github/copilot-instructions.md",
        ]
        failures = []
        for document in documents:
            # Only explicit Markdown links, not examples or inline code paths.
            for target in re.findall(r"\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")):
                parsed = urlsplit(target.strip("<>"))
                if parsed.scheme or not parsed.path:
                    continue
                path = document.parent / unquote(parsed.path)
                if not path.exists():
                    failures.append(f"{document.relative_to(REPO_ROOT)}: {target}")
        self.assertEqual(failures, [])


if __name__ == "__main__":
    unittest.main()
