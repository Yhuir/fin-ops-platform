from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "tools" / "api_route_inventory_check.py"


def load_inventory_module():
    spec = importlib.util.spec_from_file_location("api_route_inventory_check", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_inventory(path: Path, routes: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(
            {
                "fixture_name": "unit-test-inventory",
                "routes": routes,
            }
        ),
        encoding="utf-8",
    )


def test_inventory_checker_fails_when_python_route_is_missing(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "covered",
                "python_routes": ["GET /api/covered"],
                "rust_routes": [],
                "frontend_refs": [],
                "migration_status": "pending_contract",
                "risk": "medium",
                "owner": "team",
                "source": "test source",
                "source_categories": ["postgres_facts"],
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=["GET /api/covered", "POST /api/missing"],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "NO_GO"
    assert report["missing_python_routes"] == ["POST /api/missing"]


def test_inventory_checker_requires_blocker_for_unmigrated_python_route(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "turnover-ledger",
                "python_routes": [
                    "GET /api/turnover-ledger/export-preview",
                    "GET /api/turnover-ledger/export",
                ],
                "rust_routes": ["GET /api/turnover-ledger/export-preview"],
                "frontend_refs": [],
                "migration_status": "partial",
                "risk": "high",
                "owner": "finance-ops",
                "source": "preview migrated; binary export pending",
                "source_categories": ["postgres_facts", "pending_contract"],
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "NO_GO"
    assert report["schema_errors"] == [
        {
            "path": "routes[0].blocked_routes",
            "domain": "turnover-ledger",
            "message": "unmigrated python route requires blocked_routes entry",
            "route": "GET /api/turnover-ledger/export",
        }
    ]


def test_inventory_checker_expands_method_groups_and_wildcard_routes(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "etc",
                "python_routes": ["GET|PATCH|DELETE /api/etc/reconciliation-tasks/{task_id}/*"],
                "rust_routes": [],
                "frontend_refs": ["web/src/features/etc/api.ts"],
                "migration_status": "blocked_fact_source",
                "risk": "high",
                "owner": "tax-ops",
                "source": "job/object-storage contract pending",
                "source_categories": ["job_outbox", "object_storage", "pending_contract"],
                "blocked_routes": {
                    "GET|PATCH|DELETE /api/etc/reconciliation-tasks/{task_id}/*": "Reconciliation task attachment/status routes require job and object-storage write contract.",
                },
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[
            "GET /api/etc/reconciliation-tasks/{task_id}/attachments",
            "PATCH /api/etc/reconciliation-tasks/{task_id}/status",
            "DELETE /api/etc/reconciliation-tasks/{task_id}/attachments/{attachment_id}",
        ],
        rust_routes=[],
        frontend_refs=["web/src/features/etc/api.ts"],
    )

    assert report["status"] == "GO"
    assert report["missing_python_routes"] == []


def test_inventory_checker_discovers_python_startswith_routes_as_wildcards(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
if method == "GET" and route_path.startswith("/api/cost-statistics/projects/"):
    return self._handle_api_cost_statistics_project(month, project_name, project_scope)
if method == "GET" and route_path.startswith("/api/cost-statistics/transactions/"):
    return self._handle_api_cost_statistics_transaction(transaction_id, project_scope)
''',
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "cost-statistics",
                "python_routes": [
                    "GET /api/cost-statistics/projects/{project_name}",
                    "GET /api/cost-statistics/transactions/{transaction_id}",
                ],
                "rust_routes": [],
                "frontend_refs": [],
                "migration_status": "partial",
                "risk": "medium",
                "owner": "cost-ops",
                "source": "read_model.cost_statistics_read_models",
                "source_categories": ["read_model"],
                "blocked_routes": {
                    "GET /api/cost-statistics/projects/{project_name}": "Unit fixture has no Rust route for project detail.",
                    "GET /api/cost-statistics/transactions/{transaction_id}": "Unit fixture has no Rust route for transaction detail.",
                },
            }
        ],
    )

    discovered = checker.discover_sources(tmp_path, include_route_prefixes=["/api/cost-statistics"])
    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=discovered["python_routes"],
        rust_routes=[],
        frontend_refs=[],
    )

    assert discovered["python_routes"] == [
        "GET /api/cost-statistics/projects/*",
        "GET /api/cost-statistics/transactions/*",
    ]
    assert report["status"] == "GO"


def test_inventory_checker_discovers_dynamic_suffix_routes_inside_startswith_blocks(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
if method == "GET" and route_path.startswith("/imports/batches/"):
    if route_path.endswith("/download"):
        return self._handle_import_batch_download(batch_id)
    return self._handle_import_batch(batch_id)
if method == "POST" and route_path.startswith("/imports/batches/") and route_path.endswith("/revert"):
    return self._handle_import_batch_revert(batch_id)
''',
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "imports",
                "python_routes": [
                    "GET /imports/batches/{batch_id}",
                    "GET /imports/batches/{batch_id}/download",
                    "POST /imports/batches/{batch_id}/revert",
                ],
                "rust_routes": [],
                "frontend_refs": [],
                "migration_status": "pending_contract",
                "risk": "high",
                "owner": "platform-ops",
                "source": "PostgreSQL app.import_batches and object storage contract pending",
                "source_categories": ["postgres_facts", "object_storage", "pending_contract"],
                "blocked_routes": {
                    "GET /imports/batches/{batch_id}": "Unit fixture has no Rust route for batch detail.",
                    "GET /imports/batches/{batch_id}/download": "Download requires object-storage response contract.",
                    "POST /imports/batches/{batch_id}/revert": "Revert is a write route pending job/outbox contract.",
                },
            }
        ],
    )

    discovered = checker.discover_sources(tmp_path, include_route_prefixes=["/imports"])
    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=discovered["python_routes"],
        rust_routes=[],
        frontend_refs=[],
    )

    assert discovered["python_routes"] == [
        "GET /imports/batches/*",
        "GET /imports/batches/*/download",
        "POST /imports/batches/*",
        "POST /imports/batches/*/revert",
    ]
    assert report["status"] == "GO"


def test_inventory_checker_ignores_negative_dynamic_suffix_guards(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
if method == "GET" and route_path.startswith("/ledgers/") and not route_path.endswith("/status"):
    return self._handle_ledger_detail(ledger_id)
if method == "POST" and route_path.startswith("/ledgers/") and route_path.endswith("/status"):
    return self._handle_ledger_status(ledger_id, body)
''',
        encoding="utf-8",
    )

    discovered = checker.discover_sources(tmp_path, include_route_prefixes=["/ledgers"])

    assert discovered["python_routes"] == [
        "GET /ledgers/*",
        "POST /ledgers/*",
        "POST /ledgers/*/status",
    ]


def test_repository_prompt_g_inventory_has_required_metadata() -> None:
    checker = load_inventory_module()

    report = checker.validate_inventory(
        inventory_path=ROOT / "docs" / "dev" / "api-fixtures" / "api-route-inventory.json",
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["schema_errors"] == []


def test_repository_prompt_g_inventory_covers_scanned_business_api_surface() -> None:
    checker = load_inventory_module()
    discovered = checker.discover_sources(
        ROOT,
        include_route_prefixes=[
            "/api",
            "/projects",
            "/ledgers",
            "/reminders",
            "/imports",
            "/matching",
        ],
    )

    report = checker.validate_inventory(
        inventory_path=ROOT / "docs" / "dev" / "api-fixtures" / "api-route-inventory.json",
        python_routes=discovered["python_routes"],
        rust_routes=discovered["rust_routes"],
        frontend_refs=discovered["frontend_refs"],
        readiness_entrypoints=discovered["python_readiness_entrypoints"],
        shadow_fixture_path=ROOT
        / "docs"
        / "dev"
        / "api-fixtures"
        / "business-api-shadow-validation.json",
    )

    assert report["missing_python_routes"] == []
    assert report["missing_rust_routes"] == []
    assert report["missing_frontend_refs"] == []
    assert report["missing_readiness_entrypoints"] == []
    assert report["shadow_coverage_errors"] == []
    assert report["status"] == "GO"


def test_repository_route_level_inventory_fixture_matches_generated_inventory() -> None:
    checker = load_inventory_module()
    inventory_path = ROOT / "docs" / "dev" / "api-fixtures" / "api-route-inventory.json"
    route_level_path = ROOT / "docs" / "dev" / "api-fixtures" / "api-route-inventory-route-level.json"
    shadow_fixture_path = ROOT / "docs" / "dev" / "api-fixtures" / "business-api-shadow-validation.json"

    route_inventory = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )["route_inventory"]
    expected = checker.annotate_route_inventory_with_shadow(
        route_inventory,
        shadow_fixture_path=shadow_fixture_path,
    )
    actual_payload = json.loads(route_level_path.read_text(encoding="utf-8"))

    assert actual_payload["fixture_name"] == "prompt-g-route-level-inventory"
    assert actual_payload["source_inventory"] == "docs/dev/api-fixtures/api-route-inventory.json"
    assert actual_payload["shadow_fixture"] == "docs/dev/api-fixtures/business-api-shadow-validation.json"
    assert actual_payload["routes"] == expected


def test_repository_route_level_migrated_routes_have_shadow_fixture_ids() -> None:
    route_level_path = ROOT / "docs" / "dev" / "api-fixtures" / "api-route-inventory-route-level.json"
    payload = json.loads(route_level_path.read_text(encoding="utf-8"))

    missing = [
        f"{route['domain']}: {route['python_route'] or route['rust_routes']}"
        for route in payload["routes"]
        if route.get("rust_routes") and not route.get("shadow_endpoint_ids")
    ]

    assert missing == []


def test_inventory_checker_can_write_route_level_inventory_fixture(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "route-level.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "example",
                "python_routes": ["GET /api/example"],
                "rust_routes": ["GET /api/example"],
                "frontend_refs": ["web/src/features/example/api.ts"],
                "migration_status": "migrated_shadow_required",
                "risk": "medium",
                "owner": "example-ops",
                "source": "PostgreSQL app.example",
                "source_categories": ["postgres_facts"],
            }
        ],
    )
    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    checker.write_route_level_inventory(
        output_path=output_path,
        source_inventory_path=inventory_path,
        route_inventory=report["route_inventory"],
    )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["fixture_name"] == "prompt-g-route-level-inventory"
    assert payload["source_inventory"] == str(inventory_path)
    assert payload["routes"] == [
        {**record, "shadow_endpoint_ids": []}
        for record in report["route_inventory"]
    ]


def test_inventory_checker_annotates_route_level_inventory_with_shadow_fixture_ids(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    output_path = tmp_path / "route-level.json"
    shadow_fixture_path = tmp_path / "shadow.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "example",
                "python_routes": ["GET /api/example/{example_id}", "POST /api/example"],
                "rust_routes": ["GET /api/example/{example_id}"],
                "frontend_refs": ["web/src/features/example/api.ts"],
                "migration_status": "partial",
                "risk": "medium",
                "owner": "example-ops",
                "source": "PostgreSQL app.example",
                "source_categories": ["postgres_facts", "pending_contract"],
            }
        ],
    )
    shadow_fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "example-detail-shadow",
                        "method": "GET",
                        "path": "/api/example/example-001",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    checker.write_route_level_inventory(
        output_path=output_path,
        source_inventory_path=inventory_path,
        route_inventory=report["route_inventory"],
        shadow_fixture_path=shadow_fixture_path,
    )

    routes = json.loads(output_path.read_text(encoding="utf-8"))["routes"]
    assert routes[0]["shadow_endpoint_ids"] == ["example-detail-shadow"]
    assert routes[1]["shadow_endpoint_ids"] == []


def test_inventory_checker_does_not_match_literal_route_to_parameter_route(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "background-jobs",
                "python_routes": ["GET /api/background-jobs/{job_id}"],
                "rust_routes": ["GET /api/background-jobs/{job_id}"],
                "frontend_refs": [],
                "migration_status": "migrated_shadow_required",
                "risk": "medium",
                "owner": "platform-ops",
                "source": "PostgreSQL job.worker_tasks",
                "source_categories": ["job_outbox"],
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=["GET /api/background-jobs/active", "GET /api/background-jobs/{job_id}"],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "NO_GO"
    assert report["missing_python_routes"] == ["GET /api/background-jobs/active"]
    assert report["route_inventory"][0]["rust_routes"] == ["GET /api/background-jobs/{job_id}"]


def test_inventory_checker_matches_route_definition_wildcard_to_parameter_route(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "imports",
                "python_routes": ["GET /imports/batches/{batch_id}"],
                "rust_routes": ["GET /imports/batches/{batch_id}"],
                "frontend_refs": [],
                "migration_status": "migrated_shadow_required",
                "risk": "medium",
                "owner": "platform-ops",
                "source": "PostgreSQL app.import_batches",
                "source_categories": ["postgres_facts"],
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=["GET /imports/batches/*"],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "GO"
    assert report["missing_python_routes"] == []


def test_inventory_checker_rejects_unshadowed_rust_route_when_fixture_is_supplied(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    shadow_fixture_path = tmp_path / "shadow.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "example",
                "python_routes": ["GET /api/example"],
                "rust_routes": ["GET /api/example"],
                "frontend_refs": [],
                "migration_status": "migrated_shadow_required",
                "risk": "medium",
                "owner": "example-ops",
                "source": "PostgreSQL app.example",
                "source_categories": ["postgres_facts"],
            }
        ],
    )
    shadow_fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "other-route-shadow",
                        "method": "GET",
                        "path": "/api/other",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
        shadow_fixture_path=shadow_fixture_path,
    )

    assert report["status"] == "NO_GO"
    assert report["summary"]["shadow_route_coverage_checked"] == 1
    assert report["shadow_coverage_errors"] == [
        {
            "domain": "example",
            "python_route": "GET /api/example",
            "rust_routes": ["GET /api/example"],
            "migration_status": "migrated_shadow_required",
            "risk": "medium",
            "owner": "example-ops",
            "message": "migrated Axum route is missing from the shadow fixture",
        }
    ]


def test_inventory_checker_requires_machine_readable_source_categories(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "missing-source-category",
                "python_routes": ["GET /api/example"],
                "rust_routes": ["GET /api/example"],
                "frontend_refs": [],
                "migration_status": "migrated",
                "risk": "medium",
                "owner": "team",
                "source": "PostgreSQL app.example",
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "NO_GO"
    assert any(
        error["path"] == "routes[0].source_categories"
        for error in report["schema_errors"]
    )


def test_inventory_checker_outputs_route_level_inventory_records(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "mixed-domain",
                "python_routes": ["GET /api/example", "POST /api/example"],
                "rust_routes": ["GET /api/example"],
                "frontend_refs": ["web/src/features/example/api.ts"],
                "migration_status": "partial",
                "risk": "high",
                "owner": "example-ops",
                "source": "PostgreSQL app.example; write contract pending",
                "source_categories": ["postgres_facts", "pending_contract"],
                "blocked_routes": {
                    "POST /api/example": "Write contract pending.",
                },
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["route_inventory"] == [
        {
            "domain": "mixed-domain",
            "route_type": "python",
            "python_route": "GET /api/example",
            "rust_routes": ["GET /api/example"],
            "frontend_refs": ["web/src/features/example/api.ts"],
            "migration_status": "migrated_shadow_required",
            "risk": "high",
            "owner": "example-ops",
            "source": "PostgreSQL app.example; write contract pending",
            "source_categories": ["postgres_facts", "pending_contract"],
        },
        {
            "domain": "mixed-domain",
            "route_type": "python",
            "python_route": "POST /api/example",
            "rust_routes": [],
            "frontend_refs": ["web/src/features/example/api.ts"],
            "migration_status": "pending_contract",
            "risk": "high",
            "owner": "example-ops",
            "source": "PostgreSQL app.example; write contract pending",
            "source_categories": ["postgres_facts", "pending_contract"],
            "blocker": "Write contract pending.",
        },
    ]


def test_inventory_checker_rejects_rust_routes_without_cutover_source_category(tmp_path: Path) -> None:
    checker = load_inventory_module()
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "legacy-only",
                "python_routes": ["GET /api/example"],
                "rust_routes": ["GET /api/example"],
                "frontend_refs": [],
                "migration_status": "migrated",
                "risk": "medium",
                "owner": "team",
                "source": "legacy Python state only",
                "source_categories": ["legacy_python_state_blocked"],
            }
        ],
    )

    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
    )

    assert report["status"] == "NO_GO"
    assert any(
        error["path"] == "routes[0].source_categories"
        and "cutover-capable" in error["message"]
        for error in report["schema_errors"]
    )


def test_inventory_checker_discovers_python_rust_and_frontend_sources(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    rust_file = tmp_path / "rust" / "fin-ops-api" / "crates" / "fin-ops-api" / "src" / "routes" / "business_read.rs"
    frontend_file = tmp_path / "web" / "src" / "features" / "bankDetails" / "api.ts"
    python_file.parent.mkdir(parents=True)
    rust_file.parent.mkdir(parents=True)
    frontend_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
if method == "GET" and route_path == "/api/bank-details/accounts":
    return self._handle_api_bank_detail_accounts(query)
if method == "POST" and route_path == "/api/tax-offset/calculate":
    return self._handle_api_tax_offset_calculate(body)
''',
        encoding="utf-8",
    )
    rust_file.write_text(
        '''
Router::new()
    .route("/api/bank-details/accounts", get(list_bank_detail_accounts))
    .route("/api/no-oa-bank-batches/{batch_id}", get(get_no_oa_bank_batch))
    .route("/projects", get(list_projects).post(create_project))
''',
        encoding="utf-8",
    )
    frontend_file.write_text(
        'return requestJson(`/api/bank-details/transactions?${params.toString()}`);\n',
        encoding="utf-8",
    )

    discovered = checker.discover_sources(tmp_path)

    assert discovered["python_routes"] == [
        "GET /api/bank-details/accounts",
        "POST /api/tax-offset/calculate",
    ]
    assert discovered["rust_routes"] == [
        "GET /api/bank-details/accounts",
        "GET /api/no-oa-bank-batches/{batch_id}",
        "GET /projects",
        "POST /projects",
    ]
    assert discovered["frontend_refs"] == ["web/src/features/bankDetails/api.ts"]


def test_inventory_checker_requires_readiness_summary_entrypoints_in_inventory(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
class Application:
    def readiness_summary(self):
        return {
            "entrypoints": [
                "/api/covered",
                "/api/missing-readiness",
            ]
        }
''',
        encoding="utf-8",
    )
    inventory_path = tmp_path / "inventory.json"
    write_inventory(
        inventory_path,
        [
            {
                "domain": "covered",
                "python_routes": ["GET /api/covered"],
                "rust_routes": ["GET /api/covered"],
                "frontend_refs": [],
                "migration_status": "migrated_shadow_required",
                "risk": "medium",
                "owner": "team",
                "source": "PostgreSQL app.covered",
                "source_categories": ["postgres_facts"],
            }
        ],
    )

    discovered = checker.discover_sources(tmp_path, include_route_prefixes=["/api"])
    report = checker.validate_inventory(
        inventory_path=inventory_path,
        python_routes=[],
        rust_routes=[],
        frontend_refs=[],
        readiness_entrypoints=discovered["python_readiness_entrypoints"],
    )

    assert discovered["python_readiness_entrypoints"] == [
        "/api/covered",
        "/api/missing-readiness",
    ]
    assert report["status"] == "NO_GO"
    assert report["missing_readiness_entrypoints"] == ["/api/missing-readiness"]


def test_inventory_checker_discovers_frontend_api_calls_outside_features(tmp_path: Path) -> None:
    checker = load_inventory_module()
    page_api_file = tmp_path / "web" / "src" / "pages" / "directApi.tsx"
    imports_api_file = tmp_path / "web" / "src" / "features" / "imports" / "api.ts"
    nav_only_file = tmp_path / "web" / "src" / "features" / "imports" / "routes.tsx"
    test_api_file = tmp_path / "web" / "src" / "features" / "imports" / "api.test.ts"
    page_api_file.parent.mkdir(parents=True)
    imports_api_file.parent.mkdir(parents=True)
    page_api_file.write_text(
        'export const load = () => requestJson("/api/workbench/settings");\n',
        encoding="utf-8",
    )
    imports_api_file.write_text(
        'export const preview = () => requestJson(`/imports/files/preview`);\n',
        encoding="utf-8",
    )
    nav_only_file.write_text(
        'export const route = { to: "/imports/bank-transactions" };\n',
        encoding="utf-8",
    )
    test_api_file.write_text(
        'test("mock api", () => requestJson("/api/test-only"));\n',
        encoding="utf-8",
    )

    discovered = checker.discover_sources(tmp_path)

    assert discovered["frontend_refs"] == [
        "web/src/features/imports/api.ts",
        "web/src/pages/directApi.tsx",
    ]


def test_inventory_checker_can_filter_discovered_routes_to_prompt_scope(tmp_path: Path) -> None:
    checker = load_inventory_module()
    python_file = tmp_path / "backend" / "src" / "fin_ops_platform" / "app" / "server.py"
    python_file.parent.mkdir(parents=True)
    python_file.write_text(
        '''
if method == "GET" and route_path == "/api/app-health":
    return self._handle_api_app_health()
if method == "GET" and route_path == "/api/bank-details/accounts":
    return self._handle_api_bank_detail_accounts(query)
if method == "POST" and route_path == "/imports/confirm":
    return self._handle_import_confirm(body)
''',
        encoding="utf-8",
    )

    discovered = checker.discover_sources(
        tmp_path,
        include_route_prefixes=["/api/bank-details", "/imports"],
    )

    assert discovered["python_routes"] == [
        "GET /api/bank-details/accounts",
        "POST /imports/confirm",
    ]
