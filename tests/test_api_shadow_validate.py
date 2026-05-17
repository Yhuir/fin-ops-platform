import importlib.util
import json
import os
import re
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Barrier, BrokenBarrierError, Thread


def load_shadow_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "api_shadow_validate.py"
    spec = importlib.util.spec_from_file_location("api_shadow_validate", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_compare_payload_classifies_field_sort_money_and_date_diffs() -> None:
    shadow = load_shadow_module()

    python_payload = {
        "rows": [
            {"id": "b", "amount": "2.00", "posted_at": "2026-05-16T10:00:00+08:00"},
            {"id": "a", "amount": "1.00", "posted_at": "2026-05-15"},
        ],
        "summary": {"total_amount": "3.00", "legacy_only": True},
    }
    axum_payload = {
        "rows": [
            {"id": "a", "amount": "1", "posted_at": "2026-05-15T00:00:00Z"},
            {"id": "b", "amount": "2.0", "posted_at": "2026-05-16"},
        ],
        "summary": {"total_amount": "3.000"},
    }

    diff = shadow.compare_payloads(python_payload, axum_payload)

    assert any(item["kind"] == "field" and item["path"] == "$.summary.legacy_only" for item in diff["diffs"])
    assert any(item["kind"] == "sorting" and item["path"] == "$.rows" for item in diff["diffs"])
    assert any(item["kind"] == "money_format" and item["path"] == "$.summary.total_amount" for item in diff["diffs"])
    assert any(item["kind"] == "date_format" and item["path"] == "$.rows[id=b].posted_at" for item in diff["diffs"])


def test_no_go_when_diff_is_not_explained() -> None:
    shadow = load_shadow_module()
    endpoint = {
        "id": "tax-offset-month",
        "method": "GET",
        "path": "/api/tax-offset",
        "explain_diffs": ["$.read_model_status.*"],
    }
    diff = {
        "diffs": [
            {"kind": "field", "path": "$.read_model_status.api_strategy"},
            {"kind": "field", "path": "$.summary.total_amount"},
        ]
    }

    result = shadow.evaluate_endpoint_gate(endpoint, 200, 200, diff)

    assert result["status"] == "NO_GO"
    assert result["unexpected_diff_count"] == 1
    assert result["explained_diff_count"] == 1


def test_explain_diffs_array_wildcard_matches_indexed_paths() -> None:
    shadow = load_shadow_module()
    endpoint = {
        "id": "ledger-status-update",
        "method": "POST",
        "path": "/ledgers/${LEDGER_ID}/status",
        "explain_diffs": ["date_format:$.ledger.events[*].created_at"],
    }
    diff = {
        "diffs": [
            {
                "kind": "date_format",
                "path": "$.ledger.events[0].created_at",
                "python": "2026-05-17T10:45:47Z",
                "axum": "2026-05-17T10:45:46Z",
            }
        ]
    }

    result = shadow.evaluate_endpoint_gate(endpoint, 200, 200, diff)

    assert result["status"] == "GO"
    assert result["unexpected_diff_count"] == 0
    assert result["explained_diff_count"] == 1


def test_shadow_validator_runs_against_two_local_http_services(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"summary": {"total_amount": "3.00"}, "rows": [{"id": "a"}]})
    axum_server = serve_json({"summary": {"total_amount": "3.01"}, "rows": [{"id": "a"}]})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="local-check",
                        method="GET",
                        path="/api/check",
                        expected_status=200,
                        owner="test",
                        risk="low",
                        explain_diffs=[],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "NO_GO"
    assert report["fixture_validation"]["status"] == "GO"
    assert report["summary"]["fixture_error_count"] == 0
    assert report["results"][0]["expected_status"] == 200
    assert report["results"][0]["unexpected_diffs"] == [
        {
            "kind": "value",
            "path": "$.summary.total_amount",
            "python": "3.00",
            "axum": "3.01",
        }
    ]
    assert (tmp_path / "api-shadow-validation-report-20260517.json").exists()
    assert (tmp_path / "api-shadow-validation-report-20260517.md").exists()


def test_shadow_validator_records_strict_accepted_production_change(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"sent_reminders": [{"id": "legacy"}]}, status=200)
    axum_server = serve_json({"job": {"status": "queued"}}, status=202)
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="reminder-run-request",
                        method="POST",
                        path="/reminders/run",
                        expected_status=202,
                        accepted_production_change={
                            "change_id": "p0-platform-reminder-run-queue-only",
                            "legacy_status": 200,
                            "axum_status": 202,
                            "summary": "Legacy sent reminders in request path; Rust queues a worker task.",
                            "source_contract": "docs/architecture/backend-refactor/remaining-api-contracts.md#16",
                            "owner": "platform-ops",
                            "next_verification": "runtime shadow verifies queued job envelope and worker execution evidence.",
                        },
                        explain_diffs=["$.sent_reminders", "$.job"],
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"
    assert report["summary"]["accepted_production_change_count"] == 1
    assert report["accepted_production_changes"] == [
        {
            "endpoint_id": "reminder-run-request",
            "case": "primary",
            "change_id": "p0-platform-reminder-run-queue-only",
            "legacy_status": 200,
            "axum_status": 202,
            "summary": "Legacy sent reminders in request path; Rust queues a worker task.",
            "source_contract": "docs/architecture/backend-refactor/remaining-api-contracts.md#16",
            "owner": "platform-ops",
            "next_verification": "runtime shadow verifies queued job envelope and worker execution evidence.",
        }
    ]
    assert report["results"][0]["accepted_production_change"]["change_id"] == "p0-platform-reminder-run-queue-only"


def test_shadow_validator_rejects_incomplete_accepted_production_change(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="incomplete-change",
                        method="POST",
                        path="/api/incomplete",
                        expected_status=202,
                        accepted_production_change={
                            "change_id": "missing-required-fields",
                            "legacy_status": 200,
                            "axum_status": 202,
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    validation = shadow.validate_shadow_fixture(fixture_path)

    assert validation["status"] == "NO_GO"
    assert "accepted_production_change.source_contract is required" in validation["endpoint_errors"][0]["messages"]


def test_shadow_validator_runs_before_group_hook_for_reseed_boundaries(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    hook_log = tmp_path / "hook.log"
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="ledger-detail",
                        method="GET",
                        path="/ledgers/seeded",
                        expected_status=200,
                        isolation_group="ledger-readonly",
                    ),
                    complete_endpoint(
                        id="ledger-status-update",
                        method="POST",
                        path="/ledgers/seeded/status",
                        expected_status=200,
                        isolation_group="ledger-status-write",
                        requires_reseed=True,
                    ),
                    complete_endpoint(
                        id="reminder-run-request",
                        method="POST",
                        path="/reminders/run",
                        expected_status=200,
                        isolation_group="reminder-run-write",
                        requires_reseed=True,
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )
    hook = (
        f"{sys.executable} -c \"import os,pathlib;"
        f"pathlib.Path(os.environ['HOOK_LOG']).open('a').write(os.environ['SHADOW_ISOLATION_GROUP']+'\\n')\""
    )
    old_hook_log = os.environ.get("HOOK_LOG")
    os.environ["HOOK_LOG"] = str(hook_log)
    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            before_group_hook=hook,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()
        if old_hook_log is None:
            os.environ.pop("HOOK_LOG", None)
        else:
            os.environ["HOOK_LOG"] = old_hook_log

    assert hook_log.read_text(encoding="utf-8").splitlines() == [
        "ledger-readonly",
        "ledger-status-write",
        "reminder-run-write",
    ]
    assert report["seed_generation"]["before_group_hook_configured"] is True
    assert report["side_effect_probe_results"] == []
    assert report["results"][1]["isolation_group"] == "ledger-status-write"
    assert report["results"][1]["seed_applied_at"] is not None
    assert report["results"][1]["legacy_seed_applied"] is True
    assert report["results"][1]["postgres_cleanup_applied"] is True


def test_shadow_validator_blocks_requests_when_reseed_hook_reports_restart_required(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"request": "must-not-be-sent"})
    axum_server = serve_json({"request": "must-not-be-sent"})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="ledger-status-update",
                        method="POST",
                        path="/ledgers/seeded/status",
                        expected_status=200,
                        isolation_group="ledger-status-write",
                        requires_reseed=True,
                    )
                ]
            }
        ),
        encoding="utf-8",
    )
    hook = (
        f"{sys.executable} -c \"import json,sys;"
        "print(json.dumps({'status':'NO_GO','postgres_cleanup_applied':True,"
        "'legacy_seed_applied':True,'restart_required':True,"
        "'message':'legacy Python process must restart to load reseeded data-dir'}));"
        "sys.exit(4)\""
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            before_group_hook=hook,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    result = report["results"][0]
    assert report["status"] == "NO_GO"
    assert result["case"] == "seed_isolation"
    assert result["python_error"] == "request_not_sent_seed_isolation_failed"
    assert result["postgres_cleanup_applied"] is True
    assert result["legacy_seed_applied"] is True
    assert result["hook_report"]["restart_required"] is True
    assert "restart" in result["unexpected_diffs"][0]["message"]


def test_markdown_report_includes_diff_details() -> None:
    shadow = load_shadow_module()
    markdown = shadow.render_markdown_report(
        {
            "report": "api-shadow-validation-report-20260517",
            "status": "NO_GO",
            "python_base_url": "http://python",
            "axum_base_url": "http://axum",
            "fixture": "fixture.json",
            "filters": {"endpoint_ids": [], "risks": []},
            "generated_at": "2026-05-17T00:00:00Z",
            "redaction": {"sensitive_value": "[REDACTED]"},
            "summary": {
                "total": 1,
                "go": 0,
                "no_go": 1,
                "unexpected_diff_count": 2,
                "permission_failure_cases": 0,
            },
            "results": [
                {
                    "endpoint_id": "amount-check",
                    "case": "primary",
                    "method": "GET",
                    "path": "/api/amount",
                    "risk": "high",
                    "owner": "finance-ops",
                    "status": "NO_GO",
                    "unexpected_diff_count": 2,
                    "explained_diff_count": 1,
                    "unexpected_diffs": [
                        {
                            "kind": "money_format",
                            "path": "$.summary.total_amount",
                            "python": "3.00",
                            "axum": "3",
                        },
                        {
                            "kind": "sorting",
                            "path": "$.rows",
                            "python_order": ["b", "a"],
                            "axum_order": ["a", "b"],
                        },
                    ],
                    "explained_diffs": [
                        {
                            "kind": "date_format",
                            "path": "$.generated_at",
                            "python": "2026-05-17T08:00:00+08:00",
                            "axum": "2026-05-17T00:00:00Z",
                        }
                    ],
                }
            ],
        }
    )

    assert "## Diff Details" in markdown
    assert "`money_format`" in markdown
    assert "`$.summary.total_amount`" in markdown
    assert "`sorting`" in markdown
    assert "`$.rows`" in markdown
    assert "## Explained Diffs" in markdown
    assert "`date_format`" in markdown
    assert "`$.generated_at`" in markdown


def test_shadow_report_preserves_endpoint_source_in_json_and_markdown(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="source-check",
                        method="GET",
                        path="/api/check",
                        expected_status=200,
                        owner="platform-ops",
                        risk="medium",
                        source="PostgreSQL app.file_objects plus object storage presigned access provider; no app Mongo read.",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    markdown = (tmp_path / "api-shadow-validation-report-20260517.md").read_text(encoding="utf-8")

    assert report["results"][0]["source"] == (
        "PostgreSQL app.file_objects plus object storage presigned access provider; no app Mongo read."
    )
    assert "| Endpoint | Method | Risk | Owner | Source | Gate | Unexpected diffs |" in markdown
    assert "PostgreSQL app.file_objects plus object storage presigned access provider; no app Mongo read." in markdown


def test_shadow_report_derives_source_categories_from_endpoint_source(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="source-category-check",
                        method="GET",
                        path="/api/check",
                        expected_status=200,
                        source="PostgreSQL app.file_objects plus object storage provider; no app Mongo read.",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["results"][0]["source_categories"] == ["object_storage", "postgres_facts"]


def test_shadow_report_records_fixture_endpoint_ids(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="alpha-check",
                        method="GET",
                        path="/api/alpha",
                        expected_status=200,
                    ),
                    complete_endpoint(
                        id="beta-check",
                        method="GET",
                        path="/api/beta",
                        expected_status=200,
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["fixture_validation"]["endpoint_ids"] == ["alpha-check", "beta-check"]


def test_shadow_fixture_validation_filters_endpoint_ids(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="alpha-check",
                        method="GET",
                        path="/api/alpha",
                        expected_status=200,
                    ),
                    complete_endpoint(
                        id="beta-check",
                        method="GET",
                        path="/api/beta",
                        expected_status=200,
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path, endpoint_ids={"beta-check"})

    assert report["status"] == "GO"
    assert report["filters"]["endpoint_ids"] == ["beta-check"]
    assert report["endpoint_count"] == 1
    assert report["endpoint_ids"] == ["beta-check"]


def test_shadow_fixture_validation_rejects_unknown_endpoint_filter(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="alpha-check",
                        method="GET",
                        path="/api/alpha",
                        expected_status=200,
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path, endpoint_ids={"missing-check"})

    assert report["status"] == "NO_GO"
    assert report["endpoint_count"] == 0
    assert report["endpoint_errors"][0]["messages"] == ["no endpoints matched the selected filters"]


def test_shadow_fixture_records_permission_failure_endpoint_ids(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    complete_endpoint(
                        id="protected-check",
                        method="GET",
                        path="/api/protected",
                        expected_status=200,
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    ),
                    complete_endpoint(
                        id="public-check",
                        method="GET",
                        path="/api/public",
                        expected_status=200,
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    validation = shadow.validate_shadow_fixture(fixture_path)

    assert validation["status"] == "GO"
    assert validation["permission_failure_endpoint_ids"] == ["protected-check"]


def test_shadow_fixture_rejects_required_permission_failure_without_request_spec(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="protected-check",
                        method="GET",
                        path="/api/protected",
                        expected_status=200,
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    validation = shadow.validate_shadow_fixture(fixture_path)

    assert validation["status"] == "NO_GO"
    assert validation["endpoint_errors"] == [
        {
            "endpoint_id": "protected-check",
            "path": "$.endpoints[0]",
            "missing_fields": [],
            "messages": [
                "permission_failure.request_headers must be configured in defaults.permission_failure or endpoint.permission_failure"
            ],
        }
    ]


def test_shadow_fixture_accepts_endpoint_level_permission_failure_request_spec(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="protected-check",
                        method="GET",
                        path="/api/protected",
                        expected_status=200,
                        permission_failure={
                            "request_headers": {},
                            "expected_status": 401,
                        },
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    validation = shadow.validate_shadow_fixture(fixture_path)

    assert validation["status"] == "GO"
    assert validation["permission_failure_endpoint_ids"] == ["protected-check"]


def test_shadow_validator_requests_python_and_axum_concurrently(tmp_path) -> None:
    shadow = load_shadow_module()
    request_barrier = Barrier(2)
    python_server = serve_json({"ok": True}, sync_barrier=request_barrier)
    axum_server = serve_json({"ok": True}, sync_barrier=request_barrier)
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    {
                        "id": "concurrency-check",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "low",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "not applicable",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=3.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"


def test_unfiltered_shadow_run_is_no_go_when_required_permission_failures_are_not_included(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    complete_endpoint(
                        id="protected-check",
                        method="GET",
                        path="/api/protected",
                        expected_status=200,
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "NO_GO"
    assert report["summary"]["permission_failure_required_count"] == 1
    assert report["summary"]["permission_failure_missing_count"] == 1
    assert report["results"][-1] == {
        "endpoint_id": "protected-check#permission_failure",
        "case": "permission_failure_coverage",
        "method": None,
        "path": None,
        "owner": "unassigned",
        "risk": "unknown",
        "source": "fixture permission_failure coverage static contract",
        "source_categories": ["static_contract"],
        "status": "NO_GO",
        "python_status": None,
        "axum_status": None,
        "diff_count": 0,
        "explained_diff_count": 0,
        "unexpected_diff_count": 1,
        "explained_diffs": [],
        "unexpected_diffs": [
            {
                "kind": "permission_failure_coverage",
                "path": "$.fixture_validation.permission_failure_endpoint_ids",
                "message": "required permission-failure case was not run; rerun with --include-permission-failures",
            }
        ],
        "diff_summary": {},
        "python_error": None,
        "axum_error": None,
    }


def test_scoped_shadow_run_can_skip_permission_failure_cases_for_diagnostics(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    complete_endpoint(
                        id="protected-check",
                        method="GET",
                        path="/api/protected",
                        expected_status=200,
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            endpoint_ids={"protected-check"},
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"
    assert report["summary"]["permission_failure_missing_count"] == 0


def test_shadow_validator_reads_first_sse_events_without_hanging(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_sse(
        [
            ("app_health", {"status": "ok", "generated_at": "2026-05-17T00:00:00Z"}),
            ("heartbeat", {"generated_at": "2026-05-17T00:00:00Z"}),
        ]
    )
    axum_server = serve_sse(
        [
            ("app_health", {"status": "ok", "generated_at": "2026-05-17T00:00:00Z"}),
            ("heartbeat", {"generated_at": "2026-05-17T00:00:00Z"}),
        ]
    )
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    complete_endpoint(
                        id="app-health-stream",
                        method="GET",
                        path="/api/app-health/stream",
                        expected_status=200,
                        owner="platform-ops",
                        risk="medium",
                        response_mode="sse_first_events",
                        contract_cases={
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "not applicable",
                            "sse_events": ["app_health", "heartbeat"],
                        },
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"
    result = report["results"][0]
    assert result["diff_count"] == 0


def test_shadow_fixture_validation_requires_sse_events_for_sse_mode(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="bad-sse",
                        method="GET",
                        path="/api/app-health/stream",
                        expected_status=200,
                        response_mode="sse_first_events",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "NO_GO"
    assert "contract_cases.sse_events must be a non-empty list for sse_first_events" in report["endpoint_errors"][0]["messages"]


def test_shadow_validator_redacts_sensitive_diff_values_from_report(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json(
        {
            "safe": "legacy",
            "access_token": "python-token-secret",
            "nested": {"password": "python-password-secret"},
        }
    )
    axum_server = serve_json(
        {
            "safe": "axum",
            "access_token": "axum-token-secret",
            "nested": {"password": "axum-password-secret"},
        }
    )
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    {
                        "id": "sensitive-report-check",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "medium",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    report_text = (tmp_path / "api-shadow-validation-report-20260517.json").read_text(encoding="utf-8")

    assert report["status"] == "NO_GO"
    assert "python-token-secret" not in report_text
    assert "axum-token-secret" not in report_text
    assert "python-password-secret" not in report_text
    assert "axum-password-secret" not in report_text
    assert "[REDACTED]" in report_text
    assert "legacy" in report_text
    assert "axum" in report_text


def test_compare_payloads_redacts_non_json_body_snippets() -> None:
    shadow = load_shadow_module()

    diff = shadow.compare_payloads(
        {"_non_json_body": "legacy raw body password-secret"},
        {"_non_json_body": "axum raw body token-secret"},
    )

    assert diff["diffs"] == [
        {
            "kind": "value",
            "path": "$._non_json_body",
            "python": "[REDACTED]",
            "axum": "[REDACTED]",
        }
    ]


def test_compare_payloads_redacts_presigned_access_urls() -> None:
    shadow = load_shadow_module()

    diff = shadow.compare_payloads(
        {"access": {"url": "https://storage.local/object?X-Amz-Signature=python-secret"}},
        {"access": {"url": "https://storage.local/object?X-Amz-Signature=axum-secret"}},
    )

    assert diff["diffs"] == [
        {
            "kind": "value",
            "path": "$.access.url",
            "python": "[REDACTED]",
            "axum": "[REDACTED]",
        }
    ]


def test_json_report_template_redaction_hints_match_validator() -> None:
    shadow = load_shadow_module()
    template_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "dev"
        / "api-shadow-validation-report-template.json"
    )
    template = json.loads(template_path.read_text(encoding="utf-8"))

    assert template["redaction"]["field_hints"] == list(shadow.SENSITIVE_FIELD_HINTS)


def test_markdown_report_template_lists_every_shadow_fixture_route() -> None:
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads(
        (root / "docs" / "dev" / "api-fixtures" / "business-api-shadow-validation.json").read_text(
            encoding="utf-8"
        )
    )
    template_text = (root / "docs" / "dev" / "api-shadow-validation-report-template.md").read_text(
        encoding="utf-8"
    )

    fixture_routes = {
        (str(endpoint["method"]).upper(), normalize_template_route(str(endpoint["path"])))
        for endpoint in fixture["endpoints"]
    }
    template_routes = set()
    for line in template_text.splitlines():
        if not line.startswith("| `"):
            continue
        path_match = re.search(r"`([^`]+)`", line)
        if path_match is None:
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if len(columns) < 2:
            continue
        template_routes.add((columns[1].upper(), normalize_template_route(path_match.group(1))))

    assert sorted(fixture_routes - template_routes) == []


def normalize_template_route(path: str) -> str:
    path = re.sub(r"\$\{[^}]+\}", "{param}", path)
    return re.sub(r"\{[^}]+\}", "{param}", path)


def test_expected_status_mismatch_is_no_go_even_when_services_match() -> None:
    shadow = load_shadow_module()
    endpoint = {
        "id": "status-contract",
        "method": "GET",
        "path": "/api/check",
        "expected_status": 200,
        "explain_diffs": [],
    }
    diff = shadow.compare_payloads({"error": "bad"}, {"error": "bad"})

    result = shadow.evaluate_endpoint_gate(endpoint, 503, 503, diff)

    assert result["status"] == "NO_GO"
    assert result["unexpected_diff_count"] == 1
    assert result["unexpected_diffs"][0]["kind"] == "expected_status"


def test_shadow_fixture_validation_requires_complete_contract_cases(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    {
                        "id": "incomplete-contract",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "low",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": [],
                            "body": None,
                            "status": [200],
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "NO_GO"
    assert report["endpoint_errors"][0]["endpoint_id"] == "incomplete-contract"
    assert "contract_cases.error_shape" in report["endpoint_errors"][0]["missing_fields"]


def test_shadow_fixture_validation_requires_allowed_cutover_source(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="unsupported-source",
                        method="GET",
                        path="/api/check",
                        source="legacy service state",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "NO_GO"
    assert report["endpoint_errors"][0]["endpoint_id"] == "unsupported-source"
    assert "source must name at least one allowed cutover source family" in report["endpoint_errors"][0]["messages"]


def test_shadow_fixture_validation_rejects_app_mongo_as_active_source(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="app-mongo-source",
                        method="GET",
                        path="/api/check",
                        source="app Mongo app_health_alerts collection",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "NO_GO"
    assert report["endpoint_errors"][0]["endpoint_id"] == "app-mongo-source"
    assert "source must not use app Mongo as an active route source" in report["endpoint_errors"][0]["messages"]


def test_shadow_fixture_validation_allows_negative_app_mongo_statement(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="postgres-with-negative-app-mongo",
                        method="GET",
                        path="/api/check",
                        source="PostgreSQL app.bank_transactions; no app Mongo read",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "GO"
    assert report["endpoint_errors"] == []


def test_shadow_fixture_validation_requires_sample_query_and_body_to_match_contract(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "query-body-contract-mismatch",
                        "method": "POST",
                        "path": "/api/check",
                        "query": {"month": "2026-05", "page": 1},
                        "body": {"selected_output_ids": ["invoice-1"]},
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "medium",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": ["month"],
                            "body": None,
                            "status": [200, 400, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "page starts at 1",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "NO_GO"
    assert report["endpoint_errors"][0]["endpoint_id"] == "query-body-contract-mismatch"
    assert "contract_cases.query must include sample query key: page" in report["endpoint_errors"][0]["messages"]
    assert "contract_cases.body must describe sample body" in report["endpoint_errors"][0]["messages"]


def test_shadow_run_marks_incomplete_fixture_no_go_without_requests(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "incomplete-runtime-contract",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "low",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.run_shadow_validation(
        python_base_url="http://127.0.0.1:1",
        axum_base_url="http://127.0.0.1:2",
        fixture_path=fixture_path,
        output_dir=tmp_path,
        report_date="20260517",
        timeout=0.1,
    )

    assert report["status"] == "NO_GO"
    assert report["fixture_validation"]["status"] == "NO_GO"
    assert report["summary"]["fixture_error_count"] == 1
    assert report["results"][0]["unexpected_diffs"][0]["kind"] == "fixture_validation"
    assert (tmp_path / "api-shadow-validation-report-20260517.json").exists()


def test_shadow_fixture_validation_allows_expected_error_status_contracts(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": permission_failure_defaults(),
                "endpoints": [
                    {
                        "id": "removed-contract",
                        "method": "POST",
                        "path": "/api/removed",
                        "expected_status": 410,
                        "owner": "test",
                        "risk": "medium",
                        "source": "static contract removed route",
                        "contract_cases": {
                            "query": [],
                            "body": {},
                            "status": [410, 401, 403],
                            "error_shape": {"error": "removed", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "GO"
    assert report["endpoint_errors"] == []


def test_shadow_run_enforces_error_shape_for_expected_error_status(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"detail": "removed"}, status=410)
    axum_server = serve_json({"detail": "removed"}, status=410)
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "removed-error-shape",
                        "method": "POST",
                        "path": "/api/removed",
                        "expected_status": 410,
                        "owner": "test",
                        "risk": "medium",
                        "source": "static contract removed route",
                        "contract_cases": {
                            "query": [],
                            "body": {},
                            "status": [410, 401, 403],
                            "error_shape": {"error": "removed", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "not applicable",
                        },
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "NO_GO"
    assert report["results"][0]["unexpected_diffs"] == [
        {
            "kind": "error_shape",
            "path": "$.error_shape.python",
            "message": "missing $.error",
        },
        {
            "kind": "error_shape",
            "path": "$.error_shape.axum",
            "message": "missing $.error",
        },
    ]


def test_permission_failure_case_uses_permission_error_shape_override(tmp_path, monkeypatch) -> None:
    shadow = load_shadow_module()
    monkeypatch.setenv("FIN_OPS_SHADOW_TEST_TOKEN", "fixture-token")
    python_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    axum_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "headers": {"Authorization": "Bearer ${FIN_OPS_SHADOW_TEST_TOKEN}"},
                    "permission_failure": {
                        "request_headers": {},
                        "expected_status": 401,
                        "error_shape": {"error": "invalid_oa_session", "message": "string"},
                    },
                },
                "endpoints": [
                    {
                        "id": "protected-check",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "medium",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            include_permission_failures=True,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["results"][1]["case"] == "permission_failure"
    assert report["results"][1]["unexpected_diffs"] == [
        {
            "kind": "error_shape",
            "path": "$.error_shape.python",
            "message": "$.error expected 'invalid_oa_session'",
        },
        {
            "kind": "error_shape",
            "path": "$.error_shape.axum",
            "message": "$.error expected 'invalid_oa_session'",
        },
    ]


def test_repository_prompt_g_shadow_fixture_is_contract_complete() -> None:
    shadow = load_shadow_module()
    fixture_path = Path(__file__).resolve().parents[1] / "docs" / "dev" / "api-fixtures" / "business-api-shadow-validation.json"

    report = shadow.validate_shadow_fixture(fixture_path)

    assert report["status"] == "GO"
    assert report["endpoint_errors"] == []


def test_repository_prompt_g_shadow_fixture_covers_inventory_axum_routes() -> None:
    root = Path(__file__).resolve().parents[1]
    inventory = json.loads((root / "docs" / "dev" / "api-fixtures" / "api-route-inventory.json").read_text(encoding="utf-8"))
    fixture = json.loads((root / "docs" / "dev" / "api-fixtures" / "business-api-shadow-validation.json").read_text(encoding="utf-8"))
    endpoint_routes = {
        (endpoint["method"].upper(), endpoint["path"])
        for endpoint in fixture["endpoints"]
    }
    required_routes = []
    for domain in inventory["routes"]:
        for raw_route in domain.get("rust_routes", []):
            method, path = raw_route.split(" ", 1)
            required_routes.append((domain["domain"], method, path))

    missing = [
        f"{domain}: {method} {path}"
        for domain, method, path in required_routes
        if not route_has_shadow_endpoint(method, path, endpoint_routes)
    ]

    assert missing == []


def test_repository_has_json_shadow_report_template_for_readiness_gate() -> None:
    template_path = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "dev"
        / "api-shadow-validation-report-template.json"
    )

    payload = json.loads(template_path.read_text(encoding="utf-8"))

    assert payload["report"] == "api-shadow-validation-report-YYYYMMDD"
    assert payload["status"] in {"GO", "NO_GO"}
    assert payload["summary"]["no_go"] == 0
    assert isinstance(payload["results"], list)
    assert payload["results"]
    assert {"endpoint_id", "method", "path", "source", "status", "unexpected_diffs"} <= set(payload["results"][0])


def route_has_shadow_endpoint(method: str, inventory_path: str, endpoint_routes: set[tuple[str, str]]) -> bool:
    inventory_prefix = inventory_path.split("{", 1)[0]
    for endpoint_method, endpoint_path in endpoint_routes:
        if endpoint_method != method:
            continue
        if endpoint_path == inventory_path:
            return True
        if inventory_prefix and endpoint_path.startswith(inventory_prefix):
            return True
    return False


def test_shadow_validator_applies_default_headers_with_env_substitution(tmp_path, monkeypatch) -> None:
    shadow = load_shadow_module()
    monkeypatch.setenv("FIN_OPS_SHADOW_TEST_TOKEN", "fixture-token")
    python_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    axum_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "headers": {
                        "Authorization": "Bearer ${FIN_OPS_SHADOW_TEST_TOKEN}",
                        "Accept": "application/json",
                    }
                },
                "endpoints": [
                    complete_endpoint(
                        id="default-header-check",
                        method="GET",
                        path="/api/check",
                        expected_status=200,
                        owner="test",
                        risk="low",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"


def test_shadow_validator_can_run_permission_failure_contract_cases(tmp_path, monkeypatch) -> None:
    shadow = load_shadow_module()
    monkeypatch.setenv("FIN_OPS_SHADOW_TEST_TOKEN", "fixture-token")
    python_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    axum_server = serve_json({"ok": True}, required_headers={"Authorization": "Bearer fixture-token"})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "headers": {
                        "Authorization": "Bearer ${FIN_OPS_SHADOW_TEST_TOKEN}",
                    },
                    "permission_failure": {
                        "request_headers": {},
                        "expected_status": 401,
                        "error_shape": {"error": "string", "message": "string"},
                    },
                },
                "endpoints": [
                    {
                        "id": "protected-check",
                        "method": "GET",
                        "path": "/api/check",
                        "expected_status": 200,
                        "owner": "test",
                        "risk": "medium",
                        "source": "PostgreSQL test source",
                        "contract_cases": {
                            "query": [],
                            "body": None,
                            "status": [200, 401, 403],
                            "error_shape": {"error": "string", "message": "string"},
                            "pagination": "not paginated",
                            "empty_result": "not applicable",
                            "permission_failure": "401 invalid_oa_session or 403 permission_denied",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            include_permission_failures=True,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"
    assert [result["endpoint_id"] for result in report["results"]] == [
        "protected-check",
        "protected-check#permission_failure",
    ]
    assert report["results"][1]["case"] == "permission_failure"
    assert report["results"][1]["python_status"] == 401
    assert report["results"][1]["axum_status"] == 401


def test_shadow_validator_filters_endpoints_by_id_and_risk(tmp_path) -> None:
    shadow = load_shadow_module()
    python_server = serve_json({"ok": True})
    axum_server = serve_json({"ok": True})
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="low-check",
                        method="GET",
                        path="/api/low",
                        expected_status=200,
                        owner="test",
                        risk="low",
                    ),
                    complete_endpoint(
                        id="high-check",
                        method="GET",
                        path="/api/high",
                        expected_status=200,
                        owner="test",
                        risk="high",
                    ),
                ]
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
            endpoint_ids={"high-check"},
            risks={"high"},
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"
    assert report["summary"]["total"] == 1
    assert report["filters"] == {"endpoint_ids": ["high-check"], "risks": ["high"]}
    assert [result["endpoint_id"] for result in report["results"]] == ["high-check"]


def test_shadow_validator_marks_empty_filtered_selection_no_go(tmp_path) -> None:
    shadow = load_shadow_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="available-check",
                        method="GET",
                        path="/api/check",
                        expected_status=200,
                        owner="test",
                        risk="low",
                    )
                ]
            }
        ),
        encoding="utf-8",
    )

    report = shadow.run_shadow_validation(
        python_base_url="http://127.0.0.1:1",
        axum_base_url="http://127.0.0.1:2",
        fixture_path=fixture_path,
        output_dir=tmp_path,
        report_date="20260517",
        timeout=0.1,
        endpoint_ids={"missing-check"},
    )

    assert report["status"] == "NO_GO"
    assert report["summary"]["total"] == 1
    assert report["results"][0]["case"] == "selection"
    assert report["results"][0]["unexpected_diffs"][0]["kind"] == "selection"


def test_shadow_validator_expands_endpoint_path_env_vars(tmp_path, monkeypatch) -> None:
    shadow = load_shadow_module()
    monkeypatch.setenv("FIN_OPS_SHADOW_PROJECT_PATH", "Alpha%20Project")
    python_server = serve_json({"ok": True}, required_path="/api/projects/Alpha%20Project")
    axum_server = serve_json({"ok": True}, required_path="/api/projects/Alpha%20Project")
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="path-env-check",
                        method="GET",
                        path="/api/projects/${FIN_OPS_SHADOW_PROJECT_PATH}",
                        expected_status=200,
                        owner="test",
                        risk="low",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"


def test_shadow_validator_expands_query_and_body_env_vars(tmp_path, monkeypatch) -> None:
    shadow = load_shadow_module()
    monkeypatch.setenv("FIN_OPS_SHADOW_BATCH_ID", "batch-001")
    monkeypatch.setenv("FIN_OPS_SHADOW_VERSION", "7")
    expected_body = {"batch_id": "batch-001", "expected_version": "7"}
    python_server = serve_json(
        {"ok": True},
        required_path="/api/check?batch_id=batch-001",
        required_json_body=expected_body,
    )
    axum_server = serve_json(
        {"ok": True},
        required_path="/api/check?batch_id=batch-001",
        required_json_body=expected_body,
    )
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    complete_endpoint(
                        id="query-body-env-check",
                        method="POST",
                        path="/api/check",
                        query={"batch_id": "${FIN_OPS_SHADOW_BATCH_ID}"},
                        body={
                            "batch_id": "${FIN_OPS_SHADOW_BATCH_ID}",
                            "expected_version": "${FIN_OPS_SHADOW_VERSION}",
                        },
                        expected_status=200,
                        owner="test",
                        risk="low",
                    )
                ],
            }
        ),
        encoding="utf-8",
    )

    try:
        report = shadow.run_shadow_validation(
            python_base_url=server_url(python_server),
            axum_base_url=server_url(axum_server),
            fixture_path=fixture_path,
            output_dir=tmp_path,
            report_date="20260517",
            timeout=2.0,
        )
    finally:
        python_server.shutdown()
        axum_server.shutdown()

    assert report["status"] == "GO"


def load_platform_shadow_preflight_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "platform_shadow_preflight.py"
    spec = importlib.util.spec_from_file_location("platform_shadow_preflight", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules["platform_shadow_preflight"] = module
    spec.loader.exec_module(module)
    return module


def load_platform_shadow_runtime_module():
    module_path = Path(__file__).resolve().parents[1] / "scripts" / "tools" / "platform_shadow_runtime.py"
    spec = importlib.util.spec_from_file_location("platform_shadow_runtime", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec is not None
    assert spec.loader is not None
    sys.modules["platform_shadow_runtime"] = module
    spec.loader.exec_module(module)
    return module


def test_platform_shadow_preflight_parse_postgres_major() -> None:
    preflight = load_platform_shadow_preflight_module()

    assert preflight.parse_postgres_major("psql (PostgreSQL) 16.12") == 16
    assert preflight.parse_postgres_major("PostgreSQL 17.4 on aarch64-apple-darwin") == 17
    assert preflight.parse_postgres_major("not postgres") is None


def test_platform_shadow_preflight_finds_missing_runtime_inputs() -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_validation = {"status": "GO", "endpoint_count": 16}
    ok_command = preflight.CommandResult(["true"], "GO", 0, "psql (PostgreSQL) 16.12", "")
    no_go_command = preflight.CommandResult(["docker"], "NO_GO", 1, "", "daemon unavailable")

    findings = preflight.findings_for_report(
        fixture_validation=fixture_validation,
        python_base_url=None,
        axum_base_url=None,
        database_url_env="DATABASE_URL",
        database_url_present=False,
        postgres_major=14,
        psql_version=ok_command,
        docker_info=no_go_command,
        sqlx_version=no_go_command,
        python_check=ok_command,
    )

    assert [finding["code"] for finding in findings] == [
        "PYTHON_BASE_URL_MISSING",
        "AXUM_BASE_URL_MISSING",
        "AXUM_DATABASE_URL_MISSING",
        "LOCAL_POSTGRES_VERSION_TOO_OLD",
        "DOCKER_DAEMON_UNAVAILABLE",
    ]


def test_platform_shadow_preflight_reports_missing_fixture_variables(tmp_path) -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "headers": {
                        "Authorization": "Bearer ${FIN_OPS_SHADOW_OA_TOKEN}",
                    }
                },
                "endpoints": [
                    {
                        "id": "project-detail",
                        "method": "GET",
                        "path": "/projects/${PROJECT_ID}",
                        "query": {"run_id": "${SHADOW_RUN_ID}"},
                    },
                    {
                        "id": "ledger-detail",
                        "method": "GET",
                        "path": "/ledgers/${LEDGER_ID}",
                    },
                    {
                        "id": "unselected",
                        "method": "GET",
                        "path": "/ignored/${IGNORED_ID}",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    runtime_variables = preflight.collect_runtime_variable_requirements(
        fixture_path,
        endpoint_ids={"project-detail", "ledger-detail"},
        environ={"SHADOW_RUN_ID": "p0-runtime"},
    )
    findings = preflight.findings_for_report(
        fixture_validation={"status": "GO", "endpoint_count": 2},
        python_base_url="http://python",
        axum_base_url="http://axum",
        database_url_env="DATABASE_URL",
        database_url_present=True,
        postgres_major=16,
        psql_version=preflight.CommandResult(["psql"], "GO", 0, "psql (PostgreSQL) 16.12", ""),
        docker_info=preflight.CommandResult(["docker"], "GO", 0, "26.0.0", ""),
        sqlx_version=preflight.CommandResult(["cargo", "sqlx"], "GO", 0, "cargo-sqlx 0.8.0", ""),
        python_check=preflight.CommandResult(["python3"], "GO", 0, "ready", ""),
        runtime_variables=runtime_variables,
    )

    assert runtime_variables["status"] == "NO_GO"
    assert runtime_variables["missing_variables"] == [
        "FIN_OPS_SHADOW_OA_TOKEN",
        "LEDGER_ID",
        "PROJECT_ID",
    ]
    required = {item["name"]: item for item in runtime_variables["required_variables"]}
    assert required["FIN_OPS_SHADOW_OA_TOKEN"]["classification"] == "auth_secret"
    assert required["PROJECT_ID"]["classification"] == "fixture_fact_id"
    assert required["SHADOW_RUN_ID"]["classification"] == "run_correlation"
    assert "IGNORED_ID" not in required
    assert [finding["code"] for finding in findings] == ["PLATFORM_FIXTURE_VARIABLES_MISSING"]


def test_platform_shadow_preflight_builds_seed_requirements_without_database_url(tmp_path) -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {"headers": {"Authorization": "Bearer ${FIN_OPS_SHADOW_OA_TOKEN}"}},
                "endpoints": [
                    {
                        "id": "project-detail",
                        "method": "GET",
                        "path": "/projects/${PROJECT_ID}",
                    },
                    {
                        "id": "ledger-detail",
                        "method": "GET",
                        "path": "/ledgers/${LEDGER_ID}",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    runtime_variables = preflight.collect_runtime_variable_requirements(
        fixture_path,
        endpoint_ids={"project-detail", "ledger-detail"},
        environ={
            "FIN_OPS_SHADOW_OA_TOKEN": "token",
            "PROJECT_ID": "11111111-1111-1111-1111-111111111111",
            "LEDGER_ID": "22222222-2222-2222-2222-222222222222",
        },
    )
    seed_requirements = preflight.collect_seed_requirements(
        runtime_variables,
        database_url_env="DATABASE_URL",
        environ={
            "FIN_OPS_SHADOW_OA_TOKEN": "token",
            "PROJECT_ID": "11111111-1111-1111-1111-111111111111",
            "LEDGER_ID": "22222222-2222-2222-2222-222222222222",
        },
    )

    by_variable = {item["variable"]: item for item in seed_requirements["requirements"]}
    assert seed_requirements["status"] == "NO_GO"
    assert by_variable["PROJECT_ID"]["postgres_fact_source"] == "app.project_profiles"
    assert by_variable["PROJECT_ID"]["probe"]["status"] == "SKIPPED_DATABASE_URL_MISSING"
    assert by_variable["LEDGER_ID"]["postgres_fact_source"] == "app.ledgers"
    assert by_variable["FIN_OPS_SHADOW_OA_TOKEN"]["probe"]["status"] == "SKIPPED_NOT_POSTGRES_FACT"


def test_platform_shadow_preflight_flags_invalid_seed_uuid() -> None:
    preflight = load_platform_shadow_preflight_module()
    runtime_variables = {
        "required_variables": [
            {
                "name": "PROJECT_ID",
                "present": True,
                "classification": "fixture_fact_id",
                "used_by": ["project-detail"],
            }
        ]
    }

    seed_requirements = preflight.collect_seed_requirements(
        runtime_variables,
        database_url_env="DATABASE_URL",
        environ={
            "DATABASE_URL": "postgres://user:secret@localhost/db",
            "PROJECT_ID": "not-a-uuid",
        },
    )
    findings = preflight.findings_for_report(
        fixture_validation={"status": "GO", "endpoint_count": 1},
        python_base_url="http://python",
        axum_base_url="http://axum",
        database_url_env="DATABASE_URL",
        database_url_present=True,
        postgres_major=16,
        psql_version=preflight.CommandResult(["psql"], "GO", 0, "psql (PostgreSQL) 16.12", ""),
        docker_info=preflight.CommandResult(["docker"], "GO", 0, "26.0.0", ""),
        sqlx_version=preflight.CommandResult(["cargo", "sqlx"], "GO", 0, "cargo-sqlx 0.8.0", ""),
        python_check=preflight.CommandResult(["python3"], "GO", 0, "ready", ""),
        runtime_variables={"missing_variables": []},
        seed_requirements=seed_requirements,
    )

    assert seed_requirements["status"] == "NO_GO"
    assert seed_requirements["requirements"][0]["probe"]["status"] == "NO_GO"
    assert [finding["code"] for finding in findings] == ["PLATFORM_SEED_FACTS_MISSING"]


def test_platform_fixture_data_reset_shadow_actions_do_not_self_conflict() -> None:
    fixture = json.loads(Path("docs/dev/api-fixtures/business-api-shadow-validation.json").read_text(encoding="utf-8"))
    actions = {
        endpoint["id"]: endpoint["body"]["action"]
        for endpoint in fixture["endpoints"]
        if endpoint.get("id") in {"settings-data-reset-create-job", "settings-data-reset-direct-queues-job"}
    }

    assert actions == {
        "settings-data-reset-create-job": "reset_invoices",
        "settings-data-reset-direct-queues-job": "reset_bank_transactions",
    }


def test_platform_shadow_preflight_detects_static_fixture_conflicts(tmp_path) -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "endpoints": [
                    {
                        "id": "delete-project",
                        "method": "DELETE",
                        "path": "/api/workbench/settings/projects/${PROJECT_ID}",
                        "body": {"idempotency_key": "same-${SHADOW_RUN_ID}"},
                    },
                    {
                        "id": "project-detail",
                        "method": "GET",
                        "path": "/projects/${PROJECT_ID}",
                    },
                    {
                        "id": "reset-one",
                        "method": "POST",
                        "path": "/api/workbench/settings/data-reset/jobs",
                        "expected_status": 202,
                        "body": {"idempotency_key": "same-${SHADOW_RUN_ID}", "action": "reset_invoices"},
                    },
                    {
                        "id": "reset-two",
                        "method": "POST",
                        "path": "/api/workbench/settings/data-reset",
                        "expected_status": 202,
                        "body": {"idempotency_key": "other-${SHADOW_RUN_ID}", "action": "reset_invoices"},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    checks = preflight.collect_fixture_static_checks(
        fixture_path,
        endpoint_ids={"delete-project", "project-detail", "reset-one", "reset-two"},
    )
    conflicts = {item["kind"]: item for item in checks["conflicts"]}

    assert checks["status"] == "NO_GO"
    assert conflicts["duplicate_idempotency_key"]["endpoint_ids"] == ["delete-project", "reset-one"]
    assert conflicts["data_reset_action_reuse"]["endpoint_ids"] == ["reset-one", "reset-two"]
    assert conflicts["destructive_target_reuse"]["value"] == "PROJECT_ID"


def test_platform_shadow_fixture_has_no_static_write_order_conflicts() -> None:
    preflight = load_platform_shadow_preflight_module()
    checks = preflight.collect_fixture_static_checks(
        Path("docs/dev/api-fixtures/business-api-shadow-validation.json"),
        endpoint_ids=set(preflight.PLATFORM_ENDPOINT_IDS),
    )

    assert checks == {"status": "GO", "conflict_count": 0, "conflicts": []}


def test_platform_shadow_fixture_declares_axum_trusted_auth_headers() -> None:
    fixture = json.loads(Path("docs/dev/api-fixtures/business-api-shadow-validation.json").read_text(encoding="utf-8"))
    headers = {key.lower(): value for key, value in fixture["defaults"]["headers"].items()}

    assert headers["authorization"] == "Bearer ${FIN_OPS_SHADOW_OA_TOKEN}"
    assert headers["x-fin-ops-oa-user-id"] == "${FIN_OPS_SHADOW_OA_USER_ID}"
    assert headers["x-fin-ops-oa-username"] == "${FIN_OPS_SHADOW_OA_USERNAME}"
    assert headers["x-fin-ops-oa-permissions"] == "finops:app:view"


def test_platform_shadow_preflight_auth_requirements(tmp_path) -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {
                    "headers": {
                        "Authorization": "Bearer ${FIN_OPS_SHADOW_OA_TOKEN}",
                        "x-fin-ops-oa-user-id": "${FIN_OPS_SHADOW_OA_USER_ID}",
                        "x-fin-ops-oa-username": "${FIN_OPS_SHADOW_OA_USERNAME}",
                        "x-fin-ops-oa-permissions": "finops:app:view",
                    }
                },
                "endpoints": [
                    {
                        "id": "settings",
                        "method": "POST",
                        "path": "/api/workbench/settings",
                    },
                    {
                        "id": "assign",
                        "method": "POST",
                        "path": "/projects/assign",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    checks = preflight.collect_auth_requirements(
        fixture_path,
        endpoint_ids={"settings", "assign"},
        axum_base_url=None,
        environ={
            "FIN_OPS_SHADOW_OA_TOKEN": "token",
            "FIN_OPS_SHADOW_OA_USER_ID": "test-id",
            "FIN_OPS_SHADOW_OA_USERNAME": "YNSYLP005",
            "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE": "production_oa_test_user",
            "FIN_OPS_OA_IDENTITY_ADAPTER": "trusted_headers",
        },
    )

    assert checks["status"] == "GO"
    by_code = {item["code"]: item for item in checks["checks"]}
    assert by_code["AXUM_ADMIN_USERNAME_PRESENT_FOR_ADMIN_ROUTES"]["admin_route_count"] == 1
    assert by_code["OA_IDENTITY_SOURCE_ACCEPTED"]["source"] == "production_oa_test_user"
    assert by_code["OA_IDENTITY_SOURCE_ACCEPTED"]["environment"] == "production"


def test_platform_shadow_preflight_auth_requirements_report_blockers(tmp_path) -> None:
    preflight = load_platform_shadow_preflight_module()
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps(
            {
                "defaults": {"headers": {"Authorization": "Bearer ${FIN_OPS_SHADOW_OA_TOKEN}"}},
                "endpoints": [
                    {
                        "id": "settings",
                        "method": "POST",
                        "path": "/api/workbench/settings",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    auth_requirements = preflight.collect_auth_requirements(
        fixture_path,
        endpoint_ids={"settings"},
        axum_base_url=None,
        environ={},
    )
    findings = preflight.findings_for_report(
        fixture_validation={"status": "GO", "endpoint_count": 1},
        python_base_url="http://python",
        axum_base_url="http://axum",
        database_url_env="DATABASE_URL",
        database_url_present=True,
        postgres_major=16,
        psql_version=preflight.CommandResult(["psql"], "GO", 0, "psql (PostgreSQL) 16.12", ""),
        docker_info=preflight.CommandResult(["docker"], "GO", 0, "26.0.0", ""),
        sqlx_version=preflight.CommandResult(["cargo", "sqlx"], "GO", 0, "cargo-sqlx 0.8.0", ""),
        python_check=preflight.CommandResult(["python3"], "GO", 0, "ready", ""),
        runtime_variables={"missing_variables": []},
        seed_requirements={"status": "GO", "requirements": []},
        auth_requirements=auth_requirements,
    )

    assert auth_requirements["status"] == "NO_GO"
    assert [finding["code"] for finding in findings] == ["PLATFORM_AUTH_REQUIREMENTS_NO_GO"]


def test_platform_shadow_preflight_builds_runtime_input_plan() -> None:
    preflight = load_platform_shadow_preflight_module()
    args = type(
        "Args",
        (),
        {
            "fixture": Path("docs/dev/api-fixtures/business-api-shadow-validation.json"),
            "python_base_url": None,
            "axum_base_url": None,
            "database_url_env": "DATABASE_URL",
        },
    )()
    runtime_variables = {
        "status": "NO_GO",
        "required_variables": [
            {
                "name": "PROJECT_ID",
                "present": False,
                "classification": "fixture_fact_id",
                "used_by": ["project-detail"],
            },
            {
                "name": "FIN_OPS_SHADOW_OA_TOKEN",
                "present": False,
                "classification": "auth_secret",
                "used_by": ["project-detail"],
            },
        ],
    }
    seed_requirements = {
        "status": "NO_GO",
        "requirements": [
            {
                "variable": "PROJECT_ID",
                "postgres_fact_source": "app.project_profiles",
                "probe": {"status": "SKIPPED_MISSING_VARIABLE"},
            },
            {
                "variable": "FIN_OPS_SHADOW_OA_TOKEN",
                "postgres_fact_source": None,
                "probe": {"status": "SKIPPED_NOT_POSTGRES_FACT"},
            },
        ],
    }

    input_plan = preflight.runtime_shadow_input_plan(
        runtime_variables=runtime_variables,
        seed_requirements=seed_requirements,
        auth_requirements={"status": "GO", "checks": []},
        args=args,
    )

    exports = {item["name"]: item for item in input_plan["environment_exports"]}
    assert input_plan["status"] == "NO_GO"
    assert exports["FIN_OPS_SHADOW_PYTHON_BASE_URL"]["example"] == "http://127.0.0.1:8001"
    assert exports["FIN_OPS_SHADOW_AXUM_BASE_URL"]["example"] == "http://127.0.0.1:8002"
    assert exports["FIN_OPS_SHADOW_OA_TOKEN"]["sensitive"] is True
    assert exports["FIN_OPS_SHADOW_OA_IDENTITY_SOURCE"]["example"] == "production_oa_test_user"
    assert "FIN_OPS_DEV_ALLOW_LOCAL_SESSION=0" in input_plan["python_service_start_command"]
    assert "FIN_OPS_TEST_DEFAULT_AUTH=0" in input_plan["python_service_start_command"]
    assert input_plan["fact_probe_commands"] == [
        {
            "variable": "PROJECT_ID",
            "postgres_fact_source": "app.project_profiles",
            "status": "SKIPPED_MISSING_VARIABLE",
            "command": (
                "psql \"$DATABASE_URL\" -X -v ON_ERROR_STOP=1 -At -c "
                "\"select exists (select 1 from app.project_profiles "
                "where id = '${PROJECT_ID}'::uuid and project_status = 'active')\""
            ),
        }
    ]
    assert input_plan["service_start_order"][-1]["name"] == "runtime_shadow_validation"


def test_platform_shadow_runtime_skips_shadow_when_preflight_no_go(tmp_path) -> None:
    runtime = load_platform_shadow_runtime_module()
    args = type(
        "Args",
        (),
        {
            "fixture": Path("fixture.json"),
            "output_dir": tmp_path,
            "report_date": "20260517",
            "python_base_url": None,
            "axum_base_url": None,
            "database_url_env": "DATABASE_URL",
            "timeout": 1.0,
            "skip_python_check": False,
        },
    )()

    def fail_if_called(**_kwargs):
        raise AssertionError("shadow runner must not be called when preflight is NO_GO")

    report = runtime.build_runtime_report(
        args,
        preflight_builder=lambda _args: {
            "status": "NO_GO",
            "findings": [{"code": "PYTHON_BASE_URL_MISSING", "severity": "blocking"}],
        },
        shadow_runner=fail_if_called,
        http_probe=lambda name, url, timeout: runtime.HttpProbe(name, url, "GO", 200, None),
    )

    assert report["status"] == "NO_GO"
    assert report["shadow_validation_status"] == "SKIPPED"
    assert "preflight_no_go" in report["blocking_reasons"]


def test_platform_shadow_runtime_runs_shadow_after_preflight_and_health_go(tmp_path) -> None:
    runtime = load_platform_shadow_runtime_module()
    captured = {}
    args = type(
        "Args",
        (),
        {
            "fixture": Path("fixture.json"),
            "output_dir": tmp_path,
            "report_date": "20260517",
            "python_base_url": "http://python.test",
            "axum_base_url": "http://axum.test",
            "database_url_env": "DATABASE_URL",
            "timeout": 2.0,
            "skip_python_check": False,
            "before_group_hook": None,
        },
    )()

    def shadow_runner(**kwargs):
        captured.update(kwargs)
        return {
            "status": "GO",
            "json_path": str(tmp_path / "shadow.json"),
            "markdown_path": str(tmp_path / "shadow.md"),
            "summary": {"total": 32, "go": 32, "no_go": 0},
            "filters": {"endpoint_ids": sorted(kwargs["endpoint_ids"])},
        }

    report = runtime.build_runtime_report(
        args,
        preflight_builder=lambda _args: {"status": "GO", "findings": []},
        shadow_runner=shadow_runner,
        http_probe=lambda name, url, timeout: runtime.HttpProbe(name, url, "GO", 200, None),
    )

    assert report["status"] == "GO"
    assert report["python_shadow_auth_environment"] == {
        "FIN_OPS_DEV_ALLOW_LOCAL_SESSION": "0",
        "FIN_OPS_TEST_DEFAULT_AUTH": "0",
    }
    assert captured["python_base_url"] == "http://python.test"
    assert captured["axum_base_url"] == "http://axum.test"
    assert captured["include_permission_failures"] is True
    assert captured["endpoint_ids"] == set(runtime.PLATFORM_ENDPOINT_IDS)
    assert "platform_shadow_reseed_hook.py" in captured["before_group_hook"]
    assert report["shadow_validation_report"]["summary"] == {"total": 32, "go": 32, "no_go": 0}


def test_platform_shadow_preflight_markdown_handles_scalar_checks() -> None:
    preflight = load_platform_shadow_preflight_module()
    report = {
        "report": "p0-platform-shadow-preflight-20260517",
        "status": "NO_GO",
        "generated_at": "2026-05-17T00:00:00Z",
        "fixture": "fixture.json",
        "platform_endpoint_ids": ["alpha"],
        "inputs": {"python_base_url_present": False},
        "fixture_validation": {"status": "GO", "endpoint_count": 1},
        "environment_checks": {
            "postgres_major_detected": 14,
            "python_readiness_check": {"status": "SKIPPED"},
        },
        "findings": [],
        "next_runtime_shadow_command": ["python3", "scripts/tools/api_shadow_validate.py"],
    }

    markdown = preflight.render_markdown(report)

    assert "| `postgres_major_detected` | `observed` | `14` |" in markdown
    assert "| `python_readiness_check` | `SKIPPED` | `` |" in markdown


def complete_endpoint(**overrides):
    expected_status = overrides.get("expected_status", 200)
    method = str(overrides.get("method", "GET")).upper()
    query = overrides.get("query")
    contract_body = None if method == "GET" else overrides.get("body", {})
    endpoint = {
        "id": "complete-check",
        "method": method,
        "path": "/api/check",
        "expected_status": expected_status,
        "owner": "test",
        "risk": "low",
        "source": "PostgreSQL test source",
        "contract_cases": {
            "query": sorted(query) if isinstance(query, dict) else [],
            "body": contract_body,
            "status": sorted({expected_status, 401, 403}),
            "error_shape": {"error": "string", "message": "string"},
            "pagination": "not paginated",
            "empty_result": "not applicable",
            "permission_failure": "not applicable",
        },
    }
    endpoint.update(overrides)
    return endpoint


def permission_failure_defaults():
    return {
        "permission_failure": {
            "request_headers": {},
            "expected_status": 401,
            "error_shape": {"error": "string", "message": "string"},
        }
    }


def serve_json(
    payload: dict,
    *,
    status: int = 200,
    required_headers: dict[str, str] | None = None,
    required_path: str | None = None,
    required_json_body: dict | None = None,
    sync_barrier: Barrier | None = None,
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self._handle_test_request()

        def do_POST(self):  # noqa: N802
            self._handle_test_request()

        def _handle_test_request(self):
            if sync_barrier is not None:
                try:
                    sync_barrier.wait(timeout=1.0)
                except BrokenBarrierError:
                    body = json.dumps({"error": "request_not_concurrent"}).encode("utf-8")
                    self.send_response(504)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            if required_path is not None and self.path != required_path:
                body = json.dumps({"error": "wrong_path", "message": "wrong request path", "path": self.path}).encode("utf-8")
                self.send_response(404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            for key, value in (required_headers or {}).items():
                if self.headers.get(key) != value:
                    body = json.dumps({"error": "missing_header", "message": "required header missing", "header": key}).encode("utf-8")
                    self.send_response(401)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            if required_json_body is not None:
                length = int(self.headers.get("Content-Length") or "0")
                raw_body = self.rfile.read(length) if length else b""
                try:
                    parsed_body = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError:
                    parsed_body = None
                if parsed_body != required_json_body:
                    body = json.dumps({"error": "wrong_body", "message": "wrong request body", "body": parsed_body}).encode("utf-8")
                    self.send_response(400)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def serve_sse(events: list[tuple[str, dict]]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = "".join(
                f"event: {event_name}\ndata: {json.dumps(payload)}\n\n"
                for event_name, payload in events
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def server_url(server: ThreadingHTTPServer) -> str:
    host, port = server.server_address
    return f"http://{host}:{port}"
