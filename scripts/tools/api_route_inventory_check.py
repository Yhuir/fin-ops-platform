#!/usr/bin/env python3
"""Validate Prompt G API route inventory coverage."""

from __future__ import annotations

import argparse
import ast
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


VALID_STATUSES = {
    "migrated",
    "migrated_shadow_required",
    "partial",
    "pending_contract",
    "blocked_fact_source",
}
VALID_RISKS = {"low", "medium", "high"}
VALID_SOURCE_CATEGORIES = {
    "postgres_facts",
    "read_model",
    "job_outbox",
    "object_storage",
    "static_contract",
    "oa_identity",
    "pending_contract",
    "legacy_python_state_blocked",
}
CUTOVER_CAPABLE_SOURCE_CATEGORIES = {
    "postgres_facts",
    "read_model",
    "job_outbox",
    "object_storage",
    "static_contract",
    "oa_identity",
}
REQUIRED_ROUTE_FIELDS = {
    "domain",
    "python_routes",
    "rust_routes",
    "frontend_refs",
    "migration_status",
    "risk",
    "owner",
    "source",
    "source_categories",
}
PYTHON_ROUTE_RE = re.compile(
    r'method\s*==\s*["\'](?P<method>[A-Z]+)["\']\s+and\s+route_path\s*==\s*["\'](?P<path>/[^"\']+)["\']'
)
PYTHON_ROUTE_STARTSWITH_RE = re.compile(
    r'method\s*==\s*["\'](?P<method>[A-Z]+)["\']\s+and\s+route_path\.startswith\(\s*["\'](?P<prefix>/[^"\']+)["\']\s*\)'
)
PYTHON_ROUTE_ENDSWITH_RE = re.compile(
    r'route_path\.endswith\(\s*["\'](?P<suffix>/[^"\']+)["\']\s*\)'
)
RUST_ROUTE_RE = re.compile(
    r'\.route\(\s*"(?P<path>/[^"]+)"\s*,\s*(?P<method>get|post|put|patch|delete)\s*\('
)
RUST_CHAINED_ROUTE_RE = re.compile(
    r'\.route\(\s*"(?P<path>/[^"]+)"\s*,\s*'
    r'(?P<first>get|post|put|patch|delete)\s*\([^)]*\)'
    r'(?P<chain>(?:\s*\.\s*(?:get|post|put|patch|delete)\s*\([^)]*\))+)',
    re.DOTALL,
)
RUST_CHAINED_METHOD_RE = re.compile(r'\.\s*(?P<method>get|post|put|patch|delete)\s*\(')
FRONTEND_ENDPOINT_RE = re.compile(
    r'["`](?:/api/|/imports/|/projects/|/ledgers/|/reminders/|/matching/)[^"`]*?["`]'
)
FRONTEND_API_CALL_MARKERS = (
    "requestJson",
    "requestJsonWithByteProgress",
    "requestBlob",
    "fetch(",
    "EventSource(",
    "apiUrl(",
)
ROUTING_METHODS = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
}
SKIP_DIRS = {"node_modules", "target", ".git", "dist", "build", "__pycache__"}
TEST_DIRS = {"test", "tests", "__tests__"}


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str


def validate_inventory(
    *,
    inventory_path: Path,
    python_routes: list[str],
    rust_routes: list[str],
    frontend_refs: list[str],
    readiness_entrypoints: list[str] | None = None,
    shadow_fixture_path: Path | None = None,
) -> dict[str, Any]:
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    routes = inventory.get("routes")
    if not isinstance(routes, list):
        raise ValueError("inventory must contain routes[]")

    schema_errors = validate_schema(routes)
    inventory_python_specs = route_specs_from_inventory(routes, "python_routes")
    inventory_rust_specs = route_specs_from_inventory(routes, "rust_routes")
    inventory_frontend_refs = {
        str(ref)
        for item in routes
        if isinstance(item, dict)
        for ref in list(item.get("frontend_refs") or [])
    }

    missing_python_routes = missing_routes(python_routes, inventory_python_specs)
    missing_rust_routes = missing_routes(rust_routes, inventory_rust_specs)
    missing_frontend_refs = [
        ref for ref in sorted(set(frontend_refs)) if ref not in inventory_frontend_refs
    ]
    missing_readiness_entrypoints = missing_entrypoints(
        list(readiness_entrypoints or []),
        inventory_python_specs,
    )
    route_inventory = build_route_inventory(routes)
    shadow_coverage_errors = (
        validate_shadow_coverage(route_inventory, shadow_fixture_path=shadow_fixture_path)
        if shadow_fixture_path is not None
        else []
    )
    status = (
        "GO"
        if not schema_errors
        and not missing_python_routes
        and not missing_rust_routes
        and not missing_frontend_refs
        and not missing_readiness_entrypoints
        and not shadow_coverage_errors
        else "NO_GO"
    )
    return {
        "status": status,
        "inventory": str(inventory_path),
        "schema_errors": schema_errors,
        "missing_python_routes": missing_python_routes,
        "missing_rust_routes": missing_rust_routes,
        "missing_frontend_refs": missing_frontend_refs,
        "missing_readiness_entrypoints": missing_readiness_entrypoints,
        "shadow_coverage_errors": shadow_coverage_errors,
        "route_inventory": route_inventory,
        "summary": {
            "inventory_domains": len(routes),
            "python_routes_checked": len(python_routes),
            "rust_routes_checked": len(rust_routes),
            "frontend_refs_checked": len(frontend_refs),
            "readiness_entrypoints_checked": len(readiness_entrypoints or []),
            "shadow_route_coverage_checked": shadow_route_coverage_count(route_inventory)
            if shadow_fixture_path is not None
            else 0,
        },
    }


def discover_sources(
    root: Path,
    *,
    include_route_prefixes: list[str] | None = None,
) -> dict[str, list[str]]:
    root = root.resolve()
    prefixes = [prefix for prefix in (include_route_prefixes or []) if prefix]
    python_routes = filter_routes_by_prefix(discover_python_routes(root), prefixes)
    readiness_entrypoints = filter_entrypoints_by_prefix(
        discover_python_readiness_entrypoints(root),
        prefixes,
    )
    rust_routes = filter_routes_by_prefix(discover_rust_routes(root), prefixes)
    return {
        "python_routes": python_routes,
        "python_readiness_entrypoints": readiness_entrypoints,
        "rust_routes": rust_routes,
        "frontend_refs": discover_frontend_refs(root),
    }


def discover_python_routes(root: Path) -> list[str]:
    app_dir = root / "backend" / "src" / "fin_ops_platform" / "app"
    routes: set[str] = set()
    for path in iter_files(app_dir, {".py"}):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in PYTHON_ROUTE_RE.finditer(text):
            routes.add(f"{match.group('method').upper()} {match.group('path')}")
        for match in PYTHON_ROUTE_STARTSWITH_RE.finditer(text):
            routes.add(f"{match.group('method').upper()} {match.group('prefix')}*")
        routes.update(discover_startswith_suffix_routes(text))
    return sorted(routes)


def discover_python_readiness_entrypoints(root: Path) -> list[str]:
    server_path = root / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    if not server_path.exists():
        return []
    text = server_path.read_text(encoding="utf-8", errors="replace")
    try:
        module = ast.parse(text)
    except SyntaxError:
        return []
    entrypoints: set[str] = set()
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef) or node.name != "readiness_summary":
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Return):
                continue
            entrypoints.update(readiness_entrypoints_from_node(child.value))
    return sorted(entrypoints)


def readiness_entrypoints_from_node(node: ast.AST | None) -> set[str]:
    if not isinstance(node, ast.Dict):
        return set()
    for key, value in zip(node.keys, node.values):
        if not isinstance(key, ast.Constant) or key.value != "entrypoints":
            continue
        if not isinstance(value, (ast.List, ast.Tuple)):
            return set()
        return {
            str(item.value)
            for item in value.elts
            if isinstance(item, ast.Constant)
            and isinstance(item.value, str)
            and item.value.startswith("/")
        }
    return set()


def discover_startswith_suffix_routes(text: str) -> set[str]:
    routes: set[str] = set()
    lines = text.splitlines()
    for index, line in enumerate(lines):
        start_match = PYTHON_ROUTE_STARTSWITH_RE.search(line)
        if start_match is None:
            continue
        method = start_match.group("method").upper()
        prefix = start_match.group("prefix")
        search_window = "\n".join(route_block_lines(lines, index))
        for suffix_match in positive_route_endswith_matches(search_window):
            routes.add(f"{method} {prefix}*{suffix_match.group('suffix')}")
    return routes


def positive_route_endswith_matches(text: str) -> list[re.Match[str]]:
    matches = []
    for match in PYTHON_ROUTE_ENDSWITH_RE.finditer(text):
        preceding = text[max(0, match.start() - 8) : match.start()]
        if re.search(r"\bnot\s+$", preceding):
            continue
        matches.append(match)
    return matches


def route_block_lines(lines: list[str], start_index: int) -> list[str]:
    start_indent = leading_space_count(lines[start_index])
    block = [lines[start_index]]
    for line in lines[start_index + 1 : min(start_index + 8, len(lines))]:
        stripped = line.strip()
        if (
            stripped.startswith("if method ==")
            and leading_space_count(line) <= start_indent
        ):
            break
        block.append(line)
    return block


def leading_space_count(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def discover_rust_routes(root: Path) -> list[str]:
    routes_dir = root / "rust" / "fin-ops-api" / "crates" / "fin-ops-api" / "src" / "routes"
    routes: set[str] = set()
    for path in iter_files(routes_dir, {".rs"}):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in RUST_ROUTE_RE.finditer(text):
            routes.add(f"{ROUTING_METHODS[match.group('method')]} {match.group('path')}")
        for match in RUST_CHAINED_ROUTE_RE.finditer(text):
            route_path = match.group("path")
            routes.add(f"{ROUTING_METHODS[match.group('first')]} {route_path}")
            for chained_match in RUST_CHAINED_METHOD_RE.finditer(match.group("chain")):
                routes.add(f"{ROUTING_METHODS[chained_match.group('method')]} {route_path}")
    return sorted(routes)


def discover_frontend_refs(root: Path) -> list[str]:
    web_src = root / "web" / "src"
    refs: set[str] = set()
    for path in iter_files(web_src, {".ts", ".tsx", ".js", ".jsx"}):
        if is_frontend_test_file(path):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if has_frontend_api_call(text):
            refs.add(path.relative_to(root).as_posix())
    return sorted(refs)


def is_frontend_test_file(path: Path) -> bool:
    if any(part in TEST_DIRS for part in path.parts):
        return True
    return bool(re.search(r"\.(test|spec)\.[tj]sx?$", path.name))


def has_frontend_api_call(text: str) -> bool:
    if not FRONTEND_ENDPOINT_RE.search(text):
        return False
    return any(marker in text for marker in FRONTEND_API_CALL_MARKERS)


def filter_routes_by_prefix(routes: list[str], prefixes: list[str]) -> list[str]:
    if not prefixes:
        return routes
    filtered = []
    for route in routes:
        specs = expand_route_spec(route)
        if specs and any(specs[0].path.startswith(prefix) for prefix in prefixes):
            filtered.append(route)
    return filtered


def filter_entrypoints_by_prefix(entrypoints: list[str], prefixes: list[str]) -> list[str]:
    if not prefixes:
        return entrypoints
    return [
        entrypoint
        for entrypoint in entrypoints
        if any(entrypoint.startswith(prefix) for prefix in prefixes)
    ]


def iter_files(root: Path, suffixes: set[str]) -> list[Path]:
    if not root.exists():
        return []
    files = []
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and path.suffix in suffixes:
            files.append(path)
    return sorted(files)


def validate_schema(routes: list[Any]) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for index, item in enumerate(routes):
        if not isinstance(item, dict):
            errors.append({"path": f"routes[{index}]", "message": "route entry must be an object"})
            continue
        missing_fields = sorted(REQUIRED_ROUTE_FIELDS - set(item))
        if missing_fields:
            errors.append(
                {
                    "path": f"routes[{index}]",
                    "domain": item.get("domain"),
                    "message": "missing required fields",
                    "fields": missing_fields,
                }
            )
        for list_field in ("python_routes", "rust_routes", "frontend_refs"):
            if not isinstance(item.get(list_field), list):
                errors.append(
                    {
                        "path": f"routes[{index}].{list_field}",
                        "domain": item.get("domain"),
                        "message": "field must be a list",
                    }
                )
        if item.get("migration_status") not in VALID_STATUSES:
            errors.append(
                {
                    "path": f"routes[{index}].migration_status",
                    "domain": item.get("domain"),
                    "message": "invalid migration_status",
                    "value": item.get("migration_status"),
                }
            )
        if item.get("risk") not in VALID_RISKS:
            errors.append(
                {
                    "path": f"routes[{index}].risk",
                    "domain": item.get("domain"),
                    "message": "invalid risk",
                    "value": item.get("risk"),
                }
            )
        if not str(item.get("owner") or "").strip():
            errors.append(
                {
                    "path": f"routes[{index}].owner",
                    "domain": item.get("domain"),
                    "message": "owner is required",
                }
            )
        source_categories = item.get("source_categories")
        if not isinstance(source_categories, list) or not source_categories:
            errors.append(
                {
                    "path": f"routes[{index}].source_categories",
                    "domain": item.get("domain"),
                    "message": "source_categories must be a non-empty list",
                }
            )
            continue
        invalid_categories = [
            category for category in source_categories if category not in VALID_SOURCE_CATEGORIES
        ]
        if invalid_categories:
            errors.append(
                {
                    "path": f"routes[{index}].source_categories",
                    "domain": item.get("domain"),
                    "message": "invalid source_categories",
                    "value": invalid_categories,
                }
            )
        if item.get("rust_routes") and not (
            set(source_categories) & CUTOVER_CAPABLE_SOURCE_CATEGORIES
        ):
            errors.append(
                {
                    "path": f"routes[{index}].source_categories",
                    "domain": item.get("domain"),
                    "message": "rust_routes require at least one cutover-capable source category",
                    "value": source_categories,
                }
            )
        errors.extend(validate_blocked_routes(item, index))
    return errors


def validate_blocked_routes(item: dict[str, Any], index: int) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    python_routes = [str(route) for route in list(item.get("python_routes") or [])]
    rust_routes = [str(route) for route in list(item.get("rust_routes") or [])]
    blocked_routes = item.get("blocked_routes")
    if blocked_routes is not None and not isinstance(blocked_routes, dict):
        errors.append(
            {
                "path": f"routes[{index}].blocked_routes",
                "domain": item.get("domain"),
                "message": "blocked_routes must be an object",
            }
        )
        return errors
    for python_route in python_routes:
        if any(route_specs_intersect(python_route, rust_route) for rust_route in rust_routes):
            continue
        blocker = blocked_route_reason(item, python_route)
        if not blocker:
            errors.append(
                {
                    "path": f"routes[{index}].blocked_routes",
                    "domain": item.get("domain"),
                    "message": "unmigrated python route requires blocked_routes entry",
                    "route": python_route,
                }
            )
    return errors


def build_route_inventory(routes: list[Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or "")
        frontend_refs = [str(ref) for ref in list(item.get("frontend_refs") or [])]
        rust_routes = [str(route) for route in list(item.get("rust_routes") or [])]
        python_routes = [str(route) for route in list(item.get("python_routes") or [])]
        used_rust_routes: set[str] = set()

        for python_route in python_routes:
            matched_rust_routes = [
                rust_route
                for rust_route in rust_routes
                if route_specs_intersect(python_route, rust_route)
            ]
            used_rust_routes.update(matched_rust_routes)
            records.append(
                route_inventory_record(
                    item,
                    domain=domain,
                    route_type="python",
                    python_route=python_route,
                    rust_routes=matched_rust_routes,
                    frontend_refs=frontend_refs,
                )
            )

        for rust_route in rust_routes:
            if rust_route in used_rust_routes:
                continue
            records.append(
                route_inventory_record(
                    item,
                    domain=domain,
                    route_type="rust_only",
                    python_route=None,
                    rust_routes=[rust_route],
                    frontend_refs=frontend_refs,
                )
            )
    return records


def route_inventory_record(
    item: dict[str, Any],
    *,
    domain: str,
    route_type: str,
    python_route: str | None,
    rust_routes: list[str],
    frontend_refs: list[str],
) -> dict[str, Any]:
    source_categories = [str(category) for category in list(item.get("source_categories") or [])]
    record = {
        "domain": domain,
        "route_type": route_type,
        "python_route": python_route,
        "rust_routes": rust_routes,
        "frontend_refs": frontend_refs,
        "migration_status": route_migration_status(item, rust_routes),
        "risk": item.get("risk"),
        "owner": item.get("owner"),
        "source": item.get("source"),
        "source_categories": source_categories,
    }
    blocker = blocked_route_reason(item, python_route) if python_route and not rust_routes else None
    if blocker:
        record["blocker"] = blocker
    return record


def blocked_route_reason(item: dict[str, Any], python_route: str | None) -> str | None:
    if not python_route:
        return None
    blocked_routes = item.get("blocked_routes")
    if not isinstance(blocked_routes, dict):
        return None
    for blocked_route, reason in blocked_routes.items():
        if route_specs_intersect(str(blocked_route), python_route):
            normalized = str(reason or "").strip()
            return normalized or None
    return None


def route_migration_status(item: dict[str, Any], rust_routes: list[str]) -> str:
    domain_status = str(item.get("migration_status") or "")
    source_categories = {str(category) for category in list(item.get("source_categories") or [])}
    if rust_routes:
        if domain_status == "migrated":
            return "migrated"
        return "migrated_shadow_required"
    if "legacy_python_state_blocked" in source_categories:
        return "blocked_fact_source"
    if "pending_contract" in source_categories:
        return "pending_contract"
    return domain_status


def route_specs_intersect(left_route: str, right_route: str) -> bool:
    left_specs = expand_route_spec(left_route)
    right_specs = expand_route_spec(right_route)
    return any(
        left.method == right.method
        and (
            definition_path_covered(left.path, right.path)
            or definition_path_covered(right.path, left.path)
        )
        for left in left_specs
        for right in right_specs
    )


def write_route_level_inventory(
    *,
    output_path: Path,
    source_inventory_path: Path,
    route_inventory: list[dict[str, Any]],
    shadow_fixture_path: Path | None = None,
) -> None:
    annotated_inventory = annotate_route_inventory_with_shadow(
        route_inventory,
        shadow_fixture_path=shadow_fixture_path,
    )
    payload = {
        "fixture_name": "prompt-g-route-level-inventory",
        "description": (
            "Generated route-level audit view for Prompt G. Source of truth is "
            "api-route-inventory.json; this file is kept in sync by tests."
        ),
        "source_inventory": str(source_inventory_path),
        "shadow_fixture": str(shadow_fixture_path) if shadow_fixture_path else None,
        "routes": annotated_inventory,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def annotate_route_inventory_with_shadow(
    route_inventory: list[dict[str, Any]],
    *,
    shadow_fixture_path: Path | None,
) -> list[dict[str, Any]]:
    shadow_endpoints = load_shadow_endpoints(shadow_fixture_path)
    annotated = []
    for record in route_inventory:
        copied = dict(record)
        copied["shadow_endpoint_ids"] = matching_shadow_endpoint_ids(
            list(copied.get("rust_routes") or []),
            shadow_endpoints,
        )
        annotated.append(copied)
    return annotated


def validate_shadow_coverage(
    route_inventory: list[dict[str, Any]],
    *,
    shadow_fixture_path: Path,
) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for record in annotate_route_inventory_with_shadow(
        route_inventory,
        shadow_fixture_path=shadow_fixture_path,
    ):
        rust_routes = list(record.get("rust_routes") or [])
        if not rust_routes:
            continue
        if record.get("shadow_endpoint_ids"):
            continue
        errors.append(
            {
                "domain": record.get("domain"),
                "python_route": record.get("python_route"),
                "rust_routes": rust_routes,
                "migration_status": record.get("migration_status"),
                "risk": record.get("risk"),
                "owner": record.get("owner"),
                "message": "migrated Axum route is missing from the shadow fixture",
            }
        )
    return errors


def shadow_route_coverage_count(route_inventory: list[dict[str, Any]]) -> int:
    return sum(1 for record in route_inventory if record.get("rust_routes"))


def load_shadow_endpoints(shadow_fixture_path: Path | None) -> list[dict[str, str]]:
    if shadow_fixture_path is None:
        return []
    fixture = json.loads(shadow_fixture_path.read_text(encoding="utf-8"))
    endpoints = fixture.get("endpoints")
    if not isinstance(endpoints, list):
        return []
    loaded = []
    for endpoint in endpoints:
        if not isinstance(endpoint, dict):
            continue
        loaded.append(
            {
                "id": str(endpoint.get("id") or endpoint.get("path") or ""),
                "method": str(endpoint.get("method") or "").upper(),
                "path": str(endpoint.get("path") or ""),
            }
        )
    return loaded


def matching_shadow_endpoint_ids(
    rust_routes: list[str],
    shadow_endpoints: list[dict[str, str]],
) -> list[str]:
    endpoint_ids: list[str] = []
    for rust_route in rust_routes:
        specs = expand_route_spec(str(rust_route))
        for spec in specs:
            for endpoint in shadow_endpoints:
                if spec.method != endpoint["method"]:
                    continue
                if path_covered(spec.path, endpoint["path"]) or path_covered(endpoint["path"], spec.path):
                    endpoint_id = endpoint["id"]
                    if endpoint_id and endpoint_id not in endpoint_ids:
                        endpoint_ids.append(endpoint_id)
    return endpoint_ids


def route_specs_from_inventory(routes: list[Any], field: str) -> list[RouteSpec]:
    specs: list[RouteSpec] = []
    for item in routes:
        if not isinstance(item, dict):
            continue
        for raw_route in list(item.get(field) or []):
            specs.extend(expand_route_spec(str(raw_route)))
    return specs


def expand_route_spec(raw_route: str) -> list[RouteSpec]:
    text = " ".join(raw_route.strip().split())
    if " " not in text:
        return []
    method_part, path = text.split(" ", 1)
    return [
        RouteSpec(method=method.strip().upper(), path=path.strip())
        for method in method_part.split("|")
        if method.strip()
    ]


def missing_routes(required_routes: list[str], inventory_specs: list[RouteSpec]) -> list[str]:
    missing = []
    for route in sorted(set(required_routes)):
        expanded = expand_route_spec(route)
        if not expanded:
            missing.append(route)
            continue
        if not all(route_covered(required, inventory_specs) for required in expanded):
            missing.append(route)
    return missing


def missing_entrypoints(required_entrypoints: list[str], inventory_specs: list[RouteSpec]) -> list[str]:
    missing = []
    for entrypoint in sorted(set(required_entrypoints)):
        if not any(definition_path_covered(entrypoint, candidate.path) for candidate in inventory_specs):
            missing.append(entrypoint)
    return missing


def route_covered(required: RouteSpec, inventory_specs: list[RouteSpec]) -> bool:
    return any(
        required.method == candidate.method
        and definition_path_covered(required.path, candidate.path)
        for candidate in inventory_specs
    )


def definition_path_covered(required_path: str, inventory_path: str) -> bool:
    if required_path == inventory_path:
        return True
    if required_path.endswith("*"):
        return inventory_path.startswith(required_path[:-1])
    if inventory_path.endswith("*"):
        return required_path.startswith(inventory_path[:-1])
    return route_definition_segments_match(required_path, inventory_path)


def route_definition_segments_match(required_path: str, inventory_path: str) -> bool:
    required_segments = path_segments(required_path)
    inventory_segments = path_segments(inventory_path)
    if len(required_segments) != len(inventory_segments):
        return False
    return all(
        left == right
        or (path_segment_is_wildcard(left) and path_segment_is_wildcard(right))
        for left, right in zip(required_segments, inventory_segments)
    )


def path_covered(required_path: str, inventory_path: str) -> bool:
    if required_path == inventory_path:
        return True
    if path_segments_match(required_path, inventory_path):
        return True
    if required_path.endswith("*"):
        prefix = required_path[:-1]
        return inventory_path.startswith(prefix)
    if inventory_path.endswith("*"):
        prefix = inventory_path[:-1]
        return required_path.startswith(prefix)
    return False


def path_segments_match(required_path: str, inventory_path: str) -> bool:
    required_segments = path_segments(required_path)
    inventory_segments = path_segments(inventory_path)
    if len(required_segments) != len(inventory_segments):
        return False
    return all(
        left == right or path_segment_is_wildcard(left) or path_segment_is_wildcard(right)
        for left, right in zip(required_segments, inventory_segments)
    )


def path_segments(path: str) -> list[str]:
    return [segment for segment in path.strip("/").split("/") if segment]


def path_segment_is_wildcard(segment: str) -> bool:
    return segment == "*" or (segment.startswith("{") and segment.endswith("}"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Prompt G API route inventory coverage.")
    parser.add_argument(
        "--inventory",
        type=Path,
        default=Path("docs/dev/api-fixtures/api-route-inventory.json"),
    )
    parser.add_argument("--python-route", action="append", default=[])
    parser.add_argument("--rust-route", action="append", default=[])
    parser.add_argument("--frontend-ref", action="append", default=[])
    parser.add_argument(
        "--scan-root",
        type=Path,
        help="Discover Python routes, Axum routes, and frontend refs from this repository root.",
    )
    parser.add_argument(
        "--include-route-prefix",
        action="append",
        default=[],
        help="When scanning, only check discovered routes whose path starts with this prefix.",
    )
    parser.add_argument(
        "--write-route-level-inventory",
        type=Path,
        help="Write the generated route_inventory[] audit view to this JSON fixture path.",
    )
    parser.add_argument(
        "--shadow-fixture",
        type=Path,
        help="Optional shadow fixture used to annotate route-level inventory with shadow endpoint ids.",
    )
    args = parser.parse_args()

    discovered = (
        discover_sources(args.scan_root, include_route_prefixes=list(args.include_route_prefix))
        if args.scan_root
        else {}
    )
    report = validate_inventory(
        inventory_path=args.inventory,
        python_routes=[*list(args.python_route), *discovered.get("python_routes", [])],
        rust_routes=[*list(args.rust_route), *discovered.get("rust_routes", [])],
        frontend_refs=[*list(args.frontend_ref), *discovered.get("frontend_refs", [])],
        readiness_entrypoints=discovered.get("python_readiness_entrypoints", []),
        shadow_fixture_path=args.shadow_fixture,
    )
    if discovered:
        report["discovered"] = discovered
    if args.write_route_level_inventory:
        write_route_level_inventory(
            output_path=args.write_route_level_inventory,
            source_inventory_path=args.inventory,
            route_inventory=report["route_inventory"],
            shadow_fixture_path=args.shadow_fixture,
        )
        report["route_level_inventory_path"] = str(args.write_route_level_inventory)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
