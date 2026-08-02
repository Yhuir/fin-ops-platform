from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
PAGE_REGISTRY_PATH = REPO_ROOT / "web" / "src" / "app" / "pageRegistry.tsx"
ROLE_MATRIX_SPEC_PATH = REPO_ROOT / "web" / "e2e" / "permissions-role-matrix.spec.ts"
WRITE_ENTRY_INVENTORY_PATH = (
    REPO_ROOT / "docs" / "modules" / "permissions-and-audit" / "write-entry-inventory.md"
)
FEATURES_DIR = REPO_ROOT / "web" / "src" / "features"
COVERAGE_MATRIX_PATH = (
    REPO_ROOT / ".planning" / "phases" / "27-read-model-fan-out" / "27-COVERAGE-MATRIX.md"
)


def _coverage_section(heading: str, next_heading: str) -> str:
    coverage = COVERAGE_MATRIX_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)^## {re.escape(next_heading)}\s*$",
        coverage,
        re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        raise AssertionError(f"Could not find coverage matrix section: {heading}")
    return section_match.group("body")


@dataclass(frozen=True)
class PageRoute:
    path: str
    page_key: str

    @property
    def module_key(self) -> str:
        if self.page_key.startswith("imports."):
            return self.page_key.replace(".", "-")
        return self.page_key


def _page_registry_routes() -> list[PageRoute]:
    registry = PAGE_REGISTRY_PATH.read_text(encoding="utf-8")
    definitions_match = re.search(
        r"export const appPageDefinitions: AppPageDefinition\[] = \[(?P<body>.*?)\];",
        registry,
        re.DOTALL,
    )
    if definitions_match is None:
        raise AssertionError("Could not find appPageDefinitions in pageRegistry.tsx")

    return [
        PageRoute(path=path, page_key=page_key)
        for path, page_key in re.findall(
            r'path:\s*"([^"]+)".*?pageKey:\s*"([^"]+)"',
            definitions_match.group("body"),
            re.DOTALL,
        )
    ]


def _inventory_rows() -> dict[str, tuple[str, str]]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    rows: dict[str, tuple[str, str]] = {}
    for line in inventory.splitlines():
        match = re.match(
            r"^\| `(?P<module>[^`]+)` \| (?P<entry>.*?) \| `(?P<status>[^`]+)` \| (?P<evidence>.*?) \|",
            line,
        )
        if match:
            rows[match.group("module")] = (match.group("status"), match.group("evidence"))
    return rows


def _documented_browser_evidence_paths() -> list[str]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    paths = sorted(set(re.findall(r"web/e2e/[A-Za-z0-9_./*-]+", inventory)))
    if not paths:
        raise AssertionError("Could not find documented Browser E2E evidence paths")
    return paths


def _role_matrix_opener_ids() -> list[str]:
    role_matrix = ROLE_MATRIX_SPEC_PATH.read_text(encoding="utf-8")
    opener_ids = re.findall(r'id:\s*"([^"]+)"', role_matrix)
    if not opener_ids:
        raise AssertionError("Could not find role matrix opener ids")
    return opener_ids


def _role_matrix_readable_paths() -> set[str]:
    role_matrix = ROLE_MATRIX_SPEC_PATH.read_text(encoding="utf-8")
    paths = set(re.findall(r'path:\s*"([^"]+)"', role_matrix))
    if not paths:
        raise AssertionError("Could not find readable page routes in permissions-role-matrix.spec.ts")
    return paths


def _inventory_opener_ids() -> list[str]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Role matrix 动态 opener registry(?P<body>.*?)## 页面写入口矩阵",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Role matrix 动态 opener registry section")
    opener_ids = re.findall(r"^\| `([^`]+)` \| `[^`]+` \|", section_match.group("body"), re.MULTILINE)
    if not opener_ids:
        raise AssertionError("Could not find documented role matrix opener ids")
    return opener_ids


def _inventory_role_matrix_static_modules() -> set[str]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Role matrix 页面级静态覆盖 registry(?P<body>.*?)## 页面写入口矩阵",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Role matrix 页面级静态覆盖 registry section")
    modules = set(re.findall(r"^\| `([^`]+)` \|", section_match.group("body"), re.MULTILINE))
    if not modules:
        raise AssertionError("Could not find documented role matrix static coverage modules")
    return modules


def _inventory_opener_modules() -> set[str]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Role matrix 动态 opener registry(?P<body>.*?)## Role matrix 页面级静态覆盖 registry",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Role matrix 动态 opener registry section")
    modules = set(re.findall(r"^\| `[^`]+` \| `([^`]+)` \|", section_match.group("body"), re.MULTILINE))
    if not modules:
        raise AssertionError("Could not find documented role matrix opener modules")
    return modules


def _inventory_mutating_api_coverage() -> dict[str, tuple[str, ...]]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Mutating feature API coverage map(?P<body>.*?)## Role matrix 动态 opener registry",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Mutating feature API coverage map section")
    rows: dict[str, tuple[str, ...]] = {}
    for api_file, modules_cell in re.findall(
        r"^\| `([^`]+)` \| (?P<modules>.*?) \|",
        section_match.group("body"),
        re.MULTILINE,
    ):
        modules = tuple(re.findall(r"`([^`]+)`", modules_cell))
        if not modules:
            raise AssertionError(f"Could not find inventory modules for {api_file}")
        rows[api_file] = modules
    if not rows:
        raise AssertionError("Could not find documented mutating feature API coverage rows")
    return rows


def _inventory_write_control_keywords() -> list[str]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Write control keyword registry(?P<body>.*?)## Mutating feature API coverage map",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Write control keyword registry section")
    keywords = re.findall(r"^\| `([^`]+)` \|", section_match.group("body"), re.MULTILINE)
    if not keywords:
        raise AssertionError("Could not find documented write control keywords")
    return keywords


def _inventory_source_write_control_sentinels() -> list[tuple[str, str]]:
    inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
    section_match = re.search(
        r"## Source write-control keyword sentinels(?P<body>.*?)## Mutating feature API coverage map",
        inventory,
        re.DOTALL,
    )
    if section_match is None:
        raise AssertionError("Could not find Source write-control keyword sentinels section")
    sentinels = re.findall(
        r"^\| `([^`]+)` \| `([^`]+)` \|",
        section_match.group("body"),
        re.MULTILINE,
    )
    if not sentinels:
        raise AssertionError("Could not find documented source write-control keyword sentinels")
    return sentinels


def _role_matrix_write_control_pattern() -> str:
    role_matrix = ROLE_MATRIX_SPEC_PATH.read_text(encoding="utf-8")
    pattern_match = re.search(
        r"const enabledWriteControlPattern = /(?P<pattern>.*?)/;",
        role_matrix,
    )
    if pattern_match is None:
        raise AssertionError("Could not find enabledWriteControlPattern in permissions-role-matrix.spec.ts")
    return pattern_match.group("pattern")


def _role_matrix_write_control_keywords() -> list[str]:
    keywords: list[str] = []
    for raw_keyword in _role_matrix_write_control_pattern().split("|"):
        keyword = raw_keyword.strip()
        if keyword.startswith("^"):
            keyword = keyword[1:]
        if keyword.endswith("$"):
            keyword = keyword[:-1]
        if keyword:
            keywords.append(keyword)
    if not keywords:
        raise AssertionError("Could not parse enabledWriteControlPattern keywords")
    return keywords


def _mutating_feature_api_files() -> list[str]:
    mutating_files: list[str] = []
    mutation_pattern = re.compile(
        r"method:\s*[\"'](?:POST|PUT|PATCH|DELETE)[\"']|\{\s*method:\s*[\"'](?:POST|PUT|PATCH|DELETE)[\"']"
    )
    for path in sorted(FEATURES_DIR.glob("*/api.ts")):
        source = path.read_text(encoding="utf-8")
        if mutation_pattern.search(source):
            mutating_files.append(path.relative_to(FEATURES_DIR).as_posix())
    return mutating_files


def _coverage_page_routes() -> list[PageRoute]:
    body = _coverage_section("Registered page coverage", "Read model coverage")
    routes = [
        PageRoute(path=path, page_key=page_key)
        for page_key, path in re.findall(
            r"^\| `([^`]+)` \| `([^`]+)` \|",
            body,
            re.MULTILINE,
        )
    ]
    if not routes:
        raise AssertionError("Could not find registered page rows in Phase 27 coverage matrix")
    return routes


def _top_level_function_segments(source: str) -> dict[str, tuple[bool, str]]:
    declarations = list(
        re.finditer(
            r"^(?P<export>export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_]\w*)\s*\(",
            source,
            re.MULTILINE,
        )
    )
    segments: dict[str, tuple[bool, str]] = {}
    for index, declaration in enumerate(declarations):
        end = declarations[index + 1].start() if index + 1 < len(declarations) else len(source)
        segments[declaration.group("name")] = (
            declaration.group("export") is not None,
            source[declaration.start():end],
        )
    return segments


def _mutating_exported_functions(source: str) -> set[str]:
    segments = _top_level_function_segments(source)
    mutation_pattern = re.compile(r"method:\s*[\"'](?:POST|PUT|PATCH|DELETE)[\"']")
    call_pattern = re.compile(r"\b([A-Za-z_]\w*)\s*\(")

    def reaches_mutation(function_name: str, visiting: set[str]) -> bool:
        if function_name in visiting:
            return False
        function = segments.get(function_name)
        if function is None:
            return False
        _exported, body = function
        if mutation_pattern.search(body):
            return True
        next_visiting = {*visiting, function_name}
        return any(
            called_name in segments and reaches_mutation(called_name, next_visiting)
            for called_name in call_pattern.findall(body)
        )

    return {
        function_name
        for function_name, (exported, _body) in segments.items()
        if exported and reaches_mutation(function_name, set())
    }


def _mutating_feature_api_function_ids() -> set[str]:
    function_ids: set[str] = set()
    for path in sorted(FEATURES_DIR.glob("*/api.ts")):
        relative_path = path.relative_to(FEATURES_DIR).as_posix()
        for function_name in _mutating_exported_functions(path.read_text(encoding="utf-8")):
            function_ids.add(f"{relative_path}#{function_name}")
    return function_ids


def _coverage_mutating_api_function_ids() -> set[str]:
    body = _coverage_section("Mutating frontend API function coverage", "Drawer component coverage")
    function_ids = set(re.findall(r"`([^`|\s]+/api\.ts#[A-Za-z_]\w*)`", body))
    if not function_ids:
        raise AssertionError("Could not find mutating frontend API function ids in coverage matrix")
    return function_ids


def _business_drawer_sources() -> set[str]:
    sources = {
        path.relative_to(REPO_ROOT).as_posix()
        for root in (REPO_ROOT / "web" / "src" / "components", REPO_ROOT / "web" / "src" / "features")
        for path in root.rglob("*Drawer.tsx")
    }
    sources.discard("web/src/components/common/AppDrawer.tsx")
    return sources


def _coverage_drawer_sources() -> dict[str, str]:
    body = _coverage_section("Drawer component coverage", "Executable dynamic opener coverage")
    rows = {
        source: classification
        for source, classification in re.findall(
            r"^\| `([^`]+Drawer\.tsx)` \| .*? \| `([^`]+)` \|",
            body,
            re.MULTILINE,
        )
    }
    if not rows:
        raise AssertionError("Could not find Drawer component rows in coverage matrix")
    return rows


def _coverage_opener_ids() -> set[str]:
    body = _coverage_section("Executable dynamic opener coverage", "Lifecycle, enqueue and barrier call sites")
    opener_ids = set(re.findall(r"^\| `([^`]+:[^`]+)` \|", body, re.MULTILINE))
    if not opener_ids:
        raise AssertionError("Could not find dynamic opener ids in coverage matrix")
    return opener_ids


def _direct_lifecycle_enqueue_barrier_sites() -> Counter[tuple[str, str]]:
    sites: Counter[tuple[str, str]] = Counter()
    backend_patterns = (
        ".plan_event(",
        ".enqueue_read_model_refresh(",
        ".enqueue_read_model_refreshes_in_transaction(",
    )
    for path in (REPO_ROOT / "backend" / "src" / "fin_ops_platform").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(REPO_ROOT).as_posix()
        for sentinel in backend_patterns:
            count = source.count(sentinel)
            if count:
                sites[(relative_path, sentinel)] += count

    for root in (REPO_ROOT / "web" / "src" / "pages", REPO_ROOT / "web" / "src" / "components"):
        for path in root.rglob("*.tsx"):
            source = path.read_text(encoding="utf-8")
            count = source.count("waitForOperationFreshness(")
            if count:
                sites[(path.relative_to(REPO_ROOT).as_posix(), "waitForOperationFreshness(")] += count
    return sites


def _coverage_lifecycle_enqueue_barrier_sites() -> Counter[tuple[str, str]]:
    body = _coverage_section("Lifecycle, enqueue and barrier call sites", "Migration and deletion rule")
    sites: Counter[tuple[str, str]] = Counter()
    rows = re.findall(
        r"^\| `[^`]+` \| `([^`]+)` \| `([^`]+)` \| `(\d+)` \| `(retain|migrate|delete)` \|",
        body,
        re.MULTILINE,
    )
    if not rows:
        raise AssertionError("Could not find lifecycle/enqueue/barrier site rows in coverage matrix")
    for source_path, sentinel, calls, _status in rows:
        sites[(source_path, sentinel)] += int(calls)
    return sites


class PermissionsWriteEntryInventoryTests(unittest.TestCase):
    def test_app_authorization_runtime_has_no_permission_role_or_environment_admission(self) -> None:
        access_control_source = (
            REPO_ROOT / "backend/src/fin_ops_platform/services/access_control_service.py"
        ).read_text(encoding="utf-8")
        auth_source = (REPO_ROOT / "backend/src/fin_ops_platform/app/auth.py").read_text(encoding="utf-8")
        forbidden = (
            "_parse_csv_environment",
            "required_permission",
            "allowed_usernames",
            "allowed_roles",
            "readonly_export_usernames",
            "FIN_OPS_ALLOWED_USERNAMES",
            "FIN_OPS_ALLOWED_ROLES",
            "FIN_OPS_READONLY_EXPORT_USERNAMES",
            "FIN_OPS_OA_REQUIRED_PERMISSION",
        )

        for token in forbidden:
            with self.subTest(token=token):
                self.assertNotIn(token, access_control_source + auth_source)

    def test_phase_27_page_coverage_matches_current_page_registry_bidirectionally(self) -> None:
        self.assertEqual(
            _coverage_page_routes(),
            _page_registry_routes(),
            "Phase 27 coverage must list exactly the current appPageDefinitions entries in registry order.",
        )

    def test_phase_27_mutating_api_function_coverage_is_bidirectional(self) -> None:
        actual = _mutating_feature_api_function_ids()
        documented = _coverage_mutating_api_function_ids()

        self.assertEqual(
            sorted(actual - documented),
            [],
            "Every exported feature API function that reaches POST/PUT/PATCH/DELETE must have a "
            "Phase 27 operation-classification row.",
        )
        self.assertEqual(
            sorted(documented - actual),
            [],
            "Phase 27 API function rows must reference current exported mutating/read-like command clients.",
        )

    def test_mutating_api_parser_distinguishes_read_like_exports_and_local_write_helpers(self) -> None:
        synthetic_source = """
async function sendWrite() {
  return request('/write', { method: 'POST' });
}
export async function previewOnly() {
  return request('/preview');
}
export async function commitThroughHelper() {
  return sendWrite();
}
"""
        self.assertEqual(_mutating_exported_functions(synthetic_source), {"commitThroughHelper"})

    def test_phase_27_drawer_component_coverage_is_bidirectional_and_classified(self) -> None:
        actual = _business_drawer_sources()
        documented = _coverage_drawer_sources()

        self.assertEqual(sorted(actual - set(documented)), [], "Every business Drawer must be classified.")
        self.assertEqual(sorted(set(documented) - actual), [], "Drawer rows must point to current components.")
        self.assertEqual(
            sorted(
                source
                for source, classification in documented.items()
                if classification not in {"read-only", "writable", "mixed"}
            ),
            [],
            "Each Drawer must explicitly declare read-only, writable, or mixed behavior.",
        )

    def test_phase_27_dynamic_opener_coverage_matches_role_matrix_and_inventory(self) -> None:
        documented = _coverage_opener_ids()
        self.assertEqual(documented, set(_role_matrix_opener_ids()))
        self.assertEqual(documented, set(_inventory_opener_ids()))

    def test_phase_27_lifecycle_enqueue_and_barrier_call_counts_are_bidirectional(self) -> None:
        self.assertEqual(
            _coverage_lifecycle_enqueue_barrier_sites(),
            _direct_lifecycle_enqueue_barrier_sites(),
            "Every direct lifecycle/enqueue/barrier production call must be classified retain/migrate/delete, "
            "including its current call count, so same-file additions cannot bypass review.",
        )

    def test_every_page_registry_route_has_a_write_entry_inventory_row(self) -> None:
        routes = _page_registry_routes()
        inventory_modules = set(_inventory_rows())

        missing = sorted(route.module_key for route in routes if route.module_key not in inventory_modules)

        self.assertEqual(
            missing,
            [],
            "Every page registered in pageRegistry.tsx must have a row in "
            "docs/modules/permissions-and-audit/write-entry-inventory.md so PERM-E2E-003 "
            "does not silently miss newly added pages.",
        )

    def test_write_entry_inventory_rows_match_current_page_registry_modules(self) -> None:
        registry_modules = {route.module_key for route in _page_registry_routes()}
        stale_modules = sorted(module for module in _inventory_rows() if module not in registry_modules)

        self.assertEqual(
            stale_modules,
            [],
            "Every module row in write-entry-inventory.md must still exist in pageRegistry.tsx. "
            "Otherwise PERM-E2E-003 can keep claiming coverage for removed or renamed pages.",
        )

    def test_every_readable_page_registry_route_is_in_role_matrix_smoke(self) -> None:
        routes = _page_registry_routes()
        readable_paths = _role_matrix_readable_paths()

        admin_only_paths = {"/operations/app-health"}
        missing = sorted(
            route.path
            for route in routes
            if route.path not in admin_only_paths and route.path not in readable_paths
        )

        self.assertEqual(
            missing,
            [],
            "Every non-admin page route must be opened by permissions-role-matrix read-export "
            "smoke, otherwise a new page can skip the zero-mutation browser gate.",
        )

    def test_role_matrix_readable_paths_match_current_page_registry(self) -> None:
        registry_paths = {route.path for route in _page_registry_routes()}
        admin_only_paths = {"/operations/app-health"}
        stale_paths = sorted(
            path
            for path in _role_matrix_readable_paths()
            if path not in registry_paths and path not in admin_only_paths
        )

        self.assertEqual(
            stale_paths,
            [],
            "Every readable route in permissions-role-matrix.spec.ts must still exist in "
            "pageRegistry.tsx. Otherwise the role matrix can claim coverage for a removed "
            "or renamed page while the real page skips the browser permission gate.",
        )

    def test_inventory_covered_rows_have_browser_evidence(self) -> None:
        rows = _inventory_rows()
        missing_browser_evidence = sorted(
            module for module, (status, evidence) in rows.items()
            if status.startswith("covered") and "web/e2e/" not in evidence
        )

        self.assertEqual(
            missing_browser_evidence,
            [],
            "Covered write-entry inventory rows must cite Browser E2E evidence. Use partial "
            "or covered-mixed when the proof is not browser-backed.",
        )

    def test_documented_browser_evidence_paths_resolve_to_current_files(self) -> None:
        missing_paths: list[str] = []

        for evidence_path in _documented_browser_evidence_paths():
            if "*" in evidence_path:
                matches = [path for path in REPO_ROOT.glob(evidence_path) if path.is_file()]
                if not matches:
                    missing_paths.append(f"{evidence_path} (glob matched no files)")
                continue

            if not (REPO_ROOT / evidence_path).is_file():
                missing_paths.append(evidence_path)

        self.assertEqual(
            missing_paths,
            [],
            "Browser E2E evidence paths documented in write-entry-inventory.md must resolve "
            "to current files or matching globs. Otherwise PERM-E2E-003 can claim coverage "
            "from a renamed or deleted Playwright spec.",
        )

    def test_role_matrix_opener_registry_is_documented(self) -> None:
        inventory = WRITE_ENTRY_INVENTORY_PATH.read_text(encoding="utf-8")
        missing_ids = sorted(
            opener_id
            for opener_id in _role_matrix_opener_ids()
            if f"`{opener_id}`" not in inventory
        )

        self.assertEqual(
            missing_ids,
            [],
            "Every role matrix opener id must be documented in "
            "write-entry-inventory.md so PERM-E2E-003 dynamic drawer coverage remains auditable.",
        )

    def test_documented_role_matrix_openers_are_implemented(self) -> None:
        role_matrix_ids = set(_role_matrix_opener_ids())
        missing_ids = sorted(opener_id for opener_id in _inventory_opener_ids() if opener_id not in role_matrix_ids)

        self.assertEqual(
            missing_ids,
            [],
            "Every documented role matrix opener id must exist in permissions-role-matrix.spec.ts. "
            "Otherwise write-entry-inventory.md can claim Browser drawer coverage without a real opener.",
        )

    def test_covered_browser_rows_have_dynamic_opener_or_documented_static_role_matrix_proof(self) -> None:
        rows = _inventory_rows()
        opener_modules = _inventory_opener_modules()
        static_modules = _inventory_role_matrix_static_modules()
        browser_covered_modules = {
            module
            for module, (status, _evidence) in rows.items()
            if status == "covered-browser"
        }

        missing_permission_matrix_proof = sorted(browser_covered_modules - opener_modules - static_modules)

        self.assertEqual(
            missing_permission_matrix_proof,
            [],
            "`covered-browser` write-entry inventory rows must either have at least one "
            "dynamic role-matrix opener or be explicitly registered in the static page-level "
            "coverage registry. Otherwise a page can be marked covered while its nested write "
            "controls are never opened by the Browser permission matrix.",
        )

    def test_role_matrix_opener_and_static_coverage_modules_are_current_covered_browser_rows(self) -> None:
        rows = _inventory_rows()
        opener_modules = _inventory_opener_modules()
        static_modules = _inventory_role_matrix_static_modules()
        browser_covered_modules = {
            module
            for module, (status, _evidence) in rows.items()
            if status == "covered-browser"
        }

        self.assertEqual(
            sorted(opener_modules - browser_covered_modules),
            [],
            "Role matrix dynamic opener modules must be current `covered-browser` inventory rows. "
            "Otherwise the opener registry can keep coverage for a removed, renamed, or "
            "non-browser-covered module.",
        )
        self.assertEqual(
            sorted(static_modules - browser_covered_modules),
            [],
            "Role matrix static coverage modules must be current `covered-browser` inventory rows. "
            "Otherwise the static registry can claim permission coverage for a removed, renamed, "
            "or non-browser-covered module.",
        )
        self.assertEqual(
            sorted(static_modules & opener_modules),
            [],
            "A module should not be in both the dynamic opener registry and the static coverage "
            "registry. If a dynamic opener exists, keep the proof in the opener registry.",
        )

    def test_role_matrix_write_control_keywords_cover_known_deep_actions(self) -> None:
        pattern = _role_matrix_write_control_pattern()
        required_keywords = _inventory_write_control_keywords()
        missing_keywords = [keyword for keyword in required_keywords if keyword not in pattern]

        self.assertEqual(
            missing_keywords,
            [],
            "permissions-role-matrix enabled write-control scan must include known deep "
            "write action labels. Otherwise read-export Browser smoke can miss an enabled "
            "button when a page exposes a nested drawer or menu action.",
        )

    def test_role_matrix_write_control_keywords_are_documented(self) -> None:
        inventory_keywords = set(_inventory_write_control_keywords())
        undocumented_keywords = sorted(
            keyword for keyword in _role_matrix_write_control_keywords() if keyword not in inventory_keywords
        )

        self.assertEqual(
            undocumented_keywords,
            [],
            "Every literal keyword in enabledWriteControlPattern must be documented in "
            "write-entry-inventory.md so the Browser DOM write-control scan remains auditable.",
        )

    def test_source_write_control_sentinels_are_registered_and_present(self) -> None:
        inventory_keywords = set(_inventory_write_control_keywords())
        missing_from_registry: list[str] = []
        missing_from_source: list[str] = []
        invalid_paths: list[str] = []

        for keyword, relative_path in _inventory_source_write_control_sentinels():
            if keyword not in inventory_keywords:
                missing_from_registry.append(keyword)
            source_path = REPO_ROOT / relative_path
            if not source_path.exists() or not source_path.is_file():
                invalid_paths.append(relative_path)
                continue
            if keyword not in source_path.read_text(encoding="utf-8"):
                missing_from_source.append(f"{keyword} in {relative_path}")

        self.assertEqual(
            sorted(set(missing_from_registry)),
            [],
            "Every source write-control sentinel keyword must also be registered in "
            "the Write control keyword registry.",
        )
        self.assertEqual(
            invalid_paths,
            [],
            "Source write-control sentinel paths must point at current source files.",
        )
        self.assertEqual(
            missing_from_source,
            [],
            "Source write-control sentinel keywords must still exist in their documented "
            "source files. If a button/action label changed, update the registry and "
            "role matrix scan deliberately.",
        )

    def test_mutating_feature_api_files_are_mapped_to_write_entry_inventory(self) -> None:
        mutating_files = set(_mutating_feature_api_files())
        api_coverage = _inventory_mutating_api_coverage()
        mapped_files = set(api_coverage)
        inventory_modules = set(_inventory_rows())

        self.assertEqual(
            sorted(mutating_files - mapped_files),
            [],
            "Every frontend feature api.ts that sends POST/PUT/PATCH/DELETE must be mapped "
            "in write-entry-inventory.md so new write clients cannot skip the permissions "
            "write-entry inventory review.",
        )

        stale_mappings = sorted(mapped_files - mutating_files)
        self.assertEqual(
            stale_mappings,
            [],
            "write-entry-inventory.md contains feature api.ts files that no longer send "
            "mutations. Remove stale mappings or update the guard.",
        )

        missing_inventory_rows = sorted(
            {
                module
                for modules in api_coverage.values()
                for module in modules
                if module not in inventory_modules
            }
        )
        self.assertEqual(
            missing_inventory_rows,
            [],
            "Every module reached by a mutating frontend API client must have a row in "
            "write-entry-inventory.md.",
        )


if __name__ == "__main__":
    unittest.main()
