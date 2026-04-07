from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
import json
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, quote, unquote, urlparse

from fin_ops_platform import __version__
from fin_ops_platform.app.auth import (
    ForbiddenOAAccessError,
    UnauthorizedOASessionError,
    resolve_oa_request_session,
)
from fin_ops_platform.app.routes_tax import TaxApiRoutes
from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.access_control_service import AccessControlService
from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.cost_statistics_service import CostStatisticsService
from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_identity_service import (
    OAIdentityConfigurationError,
    OAIdentityService,
    OAIdentityServiceError,
    OASessionExpiredError,
)
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError, OARoleSyncService
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.reconciliation import ManualReconciliationService
from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE, SUPPORTED_SCOPES as SEARCH_SUPPORTED_SCOPES, SUPPORTED_STATUSES as SEARCH_SUPPORTED_STATUSES, SearchService
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService, UploadedCertifiedImportFile
from fin_ops_platform.services.tax_offset_service import TaxOffsetService
from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService
from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from fin_ops_platform.services.seeds import build_demo_seed


@dataclass(slots=True)
class Response:
    status_code: int
    body: str | bytes
    headers: dict[str, str] = field(
        default_factory=lambda: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
    )


def _build_ascii_download_name(filename: str, *, fallback_stem: str = "download", fallback_suffix: str = ".bin") -> str:
    safe = "".join(character if ord(character) < 128 else "_" for character in filename)
    safe = safe.replace('"', "").replace("\\", "_").strip()
    while "__" in safe:
        safe = safe.replace("__", "_")
    safe = safe.strip("._ ")
    if not safe:
        return f"{fallback_stem}{fallback_suffix}"
    return safe


def _build_content_disposition(filename: str) -> str:
    ascii_name = _build_ascii_download_name(
        filename,
        fallback_stem="cost_statistics_export",
        fallback_suffix=Path(filename).suffix or ".bin",
    )
    encoded_name = quote(filename, safe="")
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"


class Application:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self._state_store = ApplicationStateStore(data_dir) if data_dir is not None else None
        persisted_state = self._state_store.load() if self._state_store is not None else {}
        self._seed_payload = build_demo_seed()
        self._import_service = ImportNormalizationService.from_snapshot(persisted_state.get("imports"))
        self._file_import_service = FileImportService.from_snapshot(
            self._import_service,
            persisted_state.get("file_imports"),
            file_store=self._state_store,
        )
        self._matching_service = MatchingEngineService.from_snapshot(
            self._import_service,
            persisted_state.get("matching"),
        )
        self._workbench_override_service = WorkbenchOverrideService.from_snapshot(
            persisted_state.get("workbench_overrides"),
        )
        mongo_oa_settings = load_mongo_oa_settings(self._state_store.data_dir if self._state_store is not None else None)
        oa_adapter = MongoOAAdapter(settings=mongo_oa_settings) if mongo_oa_settings is not None else None
        self._audit_service = AuditTrailService()
        self._reconciliation_service = ManualReconciliationService(
            self._import_service,
            self._matching_service,
            self._audit_service,
        )
        self._ledger_service = LedgerReminderService(
            self._import_service,
            self._audit_service,
        )
        self._integration_service = IntegrationHubService(
            self._import_service,
            self._audit_service,
            adapter=oa_adapter,
        )
        self._project_costing_service = ProjectCostingService(
            self._import_service,
            self._reconciliation_service,
            self._ledger_service,
            self._integration_service,
            self._audit_service,
        )
        self._oa_role_sync_service = OARoleSyncService.from_environment()
        self._app_settings_service = AppSettingsService(
            self._state_store,
            self._project_costing_service,
            oa_role_sync_service=self._oa_role_sync_service,
        )
        self._oa_identity_service = OAIdentityService()
        self._access_control_service = AccessControlService.from_environment(
            dynamic_allowed_usernames_provider=self._app_settings_service.get_allowed_usernames,
            dynamic_readonly_export_usernames_provider=self._app_settings_service.get_readonly_export_usernames,
            dynamic_admin_usernames_provider=self._app_settings_service.get_admin_usernames,
        )
        bank_account_resolver = BankAccountResolver(self._app_settings_service.get_bank_account_mapping_dict)
        self._candidate_grouping_service = WorkbenchCandidateGroupingService()
        self._workbench_query_service = WorkbenchQueryService(oa_adapter=oa_adapter)
        self._workbench_action_service = WorkbenchActionService(self._workbench_query_service)
        self._live_workbench_service = LiveWorkbenchService(
            self._import_service,
            self._matching_service,
            bank_account_resolver=bank_account_resolver,
        )
        self._tax_certified_import_service = TaxCertifiedImportService(state_store=self._state_store)
        self._tax_offset_service = TaxOffsetService(
            import_service=self._import_service,
            certified_records_loader=self._tax_certified_import_service.list_records_for_month,
        )
        self._cost_statistics_service = CostStatisticsService(
            self._import_service,
            grouped_workbench_loader=self._build_api_workbench_payload,
            row_detail_loader=self._get_api_workbench_row_detail_payload,
            raw_workbench_loader=self._build_raw_workbench_payload,
        )
        self._search_service = SearchService(
            known_months_loader=self._list_search_months,
            raw_workbench_loader=self._build_raw_workbench_payload,
        )
        self._workbench_api_routes = WorkbenchApiRoutes(
            self._workbench_query_service,
            self._workbench_action_service,
        )
        self._tax_api_routes = TaxApiRoutes(self._tax_offset_service)

    def handle_request(
        self,
        method: str,
        path: str,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        parsed = urlparse(path)
        route_path = parsed.path
        query = parse_qs(parsed.query)

        if method == "GET" and route_path == "/health":
            return self._json_response(HTTPStatus.OK, self._health_payload())
        if method == "OPTIONS":
            return Response(status_code=int(HTTPStatus.NO_CONTENT), body="")
        if method == "GET" and route_path == "/foundation/seed":
            return self._json_response(HTTPStatus.OK, self._seed_payload)
        auth_error = self._enforce_route_access(route_path, headers)
        if auth_error is not None:
            return auth_error
        if method == "GET" and route_path == "/api/workbench":
            month = query.get("month", [None])[0]
            return self._handle_api_workbench(month)
        if method == "GET" and route_path == "/api/search":
            q = query.get("q", [""])[0]
            scope = query.get("scope", ["all"])[0]
            month = query.get("month", ["all"])[0]
            project_name = query.get("project_name", [None])[0]
            status = query.get("status", [None])[0]
            limit = query.get("limit", [None])[0]
            return self._handle_api_search(
                q=q,
                scope=scope,
                month=month,
                project_name=project_name,
                status=status,
                limit=limit,
            )
        if method == "GET" and route_path == "/api/session/me":
            return self._handle_api_session_me(headers)
        if method == "GET" and route_path == "/api/workbench/ignored":
            month = query.get("month", [None])[0]
            return self._handle_api_workbench_ignored(month)
        if method == "GET" and route_path == "/api/workbench/settings":
            return self._handle_api_workbench_settings()
        if method == "POST" and route_path == "/api/workbench/settings":
            return self._handle_api_workbench_settings_update(body)
        if method == "GET" and route_path.startswith("/api/workbench/rows/"):
            row_id = route_path.rsplit("/", 1)[-1]
            return self._handle_api_workbench_row_detail(row_id)
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link":
            return self._handle_api_workbench_confirm_link(body)
        if method == "POST" and route_path == "/api/workbench/actions/mark-exception":
            return self._handle_api_workbench_mark_exception(body)
        if method == "POST" and route_path == "/api/workbench/actions/cancel-link":
            return self._handle_api_workbench_cancel_link(body)
        if method == "POST" and route_path == "/api/workbench/actions/update-bank-exception":
            return self._handle_api_workbench_update_bank_exception(body)
        if method == "POST" and route_path == "/api/workbench/actions/oa-bank-exception":
            return self._handle_api_workbench_oa_bank_exception(body)
        if method == "POST" and route_path == "/api/workbench/actions/cancel-exception":
            return self._handle_api_workbench_cancel_exception(body)
        if method == "POST" and route_path == "/api/workbench/actions/ignore-row":
            return self._handle_api_workbench_ignore_row(body)
        if method == "POST" and route_path == "/api/workbench/actions/unignore-row":
            return self._handle_api_workbench_unignore_row(body)
        if method == "GET" and route_path == "/api/tax-offset":
            month = query.get("month", [None])[0]
            return self._handle_api_tax_offset(month)
        if method == "POST" and route_path == "/api/tax-offset/certified-import/preview":
            return self._handle_api_tax_certified_import_preview(body, headers)
        if method == "POST" and route_path == "/api/tax-offset/certified-import/confirm":
            return self._handle_api_tax_certified_import_confirm(body)
        if method == "GET" and route_path == "/api/tax-offset/certified-imports":
            month = query.get("month", [None])[0]
            return self._handle_api_tax_certified_imports(month)
        if method == "POST" and route_path == "/api/tax-offset/calculate":
            return self._handle_api_tax_offset_calculate(body)
        if method == "GET" and route_path == "/api/cost-statistics":
            month = query.get("month", [None])[0]
            return self._handle_api_cost_statistics(month)
        if method == "GET" and route_path == "/api/cost-statistics/explorer":
            month = query.get("month", [None])[0]
            return self._handle_api_cost_statistics_explorer(month)
        if method == "GET" and route_path == "/api/cost-statistics/export-preview":
            month = query.get("month", [None])[0]
            view = query.get("view", [None])[0]
            project_names = query.get("project_name", [])
            expense_types = query.get("expense_type", [])
            start_month = query.get("start_month", [None])[0]
            end_month = query.get("end_month", [None])[0]
            start_date = query.get("start_date", [None])[0]
            end_date = query.get("end_date", [None])[0]
            aggregate_by = query.get("aggregate_by", [None])[0]
            return self._handle_api_cost_statistics_export_preview(
                month=month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
            )
        if method == "GET" and route_path == "/api/cost-statistics/export":
            month = query.get("month", [None])[0]
            view = query.get("view", [None])[0]
            project_names = query.get("project_name", [])
            expense_types = query.get("expense_type", [])
            transaction_id = query.get("transaction_id", [None])[0]
            start_month = query.get("start_month", [None])[0]
            end_month = query.get("end_month", [None])[0]
            start_date = query.get("start_date", [None])[0]
            end_date = query.get("end_date", [None])[0]
            aggregate_by = query.get("aggregate_by", [None])[0]
            include_oa_details = self._parse_optional_bool(query.get("include_oa_details", [None])[0], default=True)
            include_invoice_details = self._parse_optional_bool(query.get("include_invoice_details", [None])[0], default=True)
            include_exception_rows = self._parse_optional_bool(query.get("include_exception_rows", [None])[0], default=True)
            include_ignored_rows = self._parse_optional_bool(query.get("include_ignored_rows", [None])[0], default=True)
            include_expense_content_summary = self._parse_optional_bool(
                query.get("include_expense_content_summary", [None])[0],
                default=True,
            )
            sort_by = query.get("sort_by", [None])[0]
            return self._handle_api_cost_statistics_export(
                month=month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                transaction_id=transaction_id,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
                include_oa_details=include_oa_details,
                include_invoice_details=include_invoice_details,
                include_exception_rows=include_exception_rows,
                include_ignored_rows=include_ignored_rows,
                include_expense_content_summary=include_expense_content_summary,
                sort_by=sort_by,
            )
        if method == "GET" and route_path.startswith("/api/cost-statistics/projects/"):
            month = query.get("month", [None])[0]
            project_name = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_cost_statistics_project(month, project_name)
        if method == "GET" and route_path.startswith("/api/cost-statistics/transactions/"):
            transaction_id = route_path.rsplit("/", 1)[-1]
            return self._handle_api_cost_statistics_transaction(transaction_id)
        if method == "GET" and route_path == "/workbench/prototype":
            return self._handle_workbench_prototype()
        if method == "GET" and route_path == "/workbench":
            month = query.get("month", [None])[0]
            return self._handle_workbench(month)
        if method == "POST" and route_path == "/workbench/actions/confirm":
            return self._handle_workbench_confirm(body)
        if method == "POST" and route_path == "/workbench/actions/difference":
            return self._handle_workbench_difference(body)
        if method == "POST" and route_path == "/workbench/actions/exception":
            return self._handle_workbench_exception(body)
        if method == "POST" and route_path == "/workbench/actions/offline":
            return self._handle_workbench_offline(body)
        if method == "POST" and route_path == "/workbench/actions/offset":
            return self._handle_workbench_offset(body)
        if method == "GET" and route_path == "/integrations/oa":
            return self._handle_oa_dashboard()
        if method == "POST" and route_path == "/integrations/oa/sync":
            return self._handle_oa_sync(body)
        if method == "GET" and route_path == "/integrations/oa/sync-runs":
            return self._handle_oa_sync_runs()
        if method == "GET" and route_path.startswith("/integrations/oa/sync-runs/"):
            run_id = route_path.rsplit("/", 1)[-1]
            return self._handle_oa_sync_run_detail(run_id)
        if method == "GET" and route_path == "/projects":
            return self._handle_projects()
        if method == "POST" and route_path == "/projects":
            return self._handle_project_create(body)
        if method == "POST" and route_path == "/projects/assign":
            return self._handle_project_assign(body)
        if method == "GET" and route_path.startswith("/projects/"):
            project_id = route_path.rsplit("/", 1)[-1]
            return self._handle_project_detail(project_id)
        if method == "GET" and route_path == "/ledgers":
            view = query.get("view", ["all"])[0]
            as_of = query.get("as_of", [None])[0]
            status = query.get("status", [None])[0]
            return self._handle_ledgers(view=view, as_of=as_of, status=status)
        if method == "GET" and route_path.startswith("/ledgers/") and not route_path.endswith("/status"):
            ledger_id = route_path.rsplit("/", 1)[-1]
            return self._handle_ledger_detail(ledger_id)
        if method == "POST" and route_path.startswith("/ledgers/") and route_path.endswith("/status"):
            ledger_id = route_path.rsplit("/", 2)[-2]
            return self._handle_ledger_status_update(ledger_id, body)
        if method == "GET" and route_path == "/reminders":
            as_of = query.get("as_of", [None])[0]
            status = query.get("status", [None])[0]
            return self._handle_reminders(as_of=as_of, status=status)
        if method == "POST" and route_path == "/reminders/run":
            return self._handle_reminder_run(body)
        if method == "GET" and route_path == "/reconciliation/cases":
            return self._handle_reconciliation_cases()
        if method == "GET" and route_path.startswith("/reconciliation/cases/"):
            case_id = route_path.rsplit("/", 1)[-1]
            return self._handle_reconciliation_case_detail(case_id)
        if method == "POST" and route_path == "/imports/preview":
            return self._handle_import_preview(body)
        if method == "POST" and route_path == "/imports/confirm":
            return self._handle_import_confirm(body)
        if method == "GET" and route_path.startswith("/imports/batches/"):
            if route_path.endswith("/download"):
                batch_id = route_path.rsplit("/", 2)[-2]
                return self._handle_import_batch_download(batch_id)
            batch_id = route_path.rsplit("/", 1)[-1]
            return self._handle_import_batch(batch_id)
        if method == "POST" and route_path.startswith("/imports/batches/") and route_path.endswith("/revert"):
            batch_id = route_path.rsplit("/", 2)[-2]
            return self._handle_import_batch_revert(batch_id)
        if method == "GET" and route_path == "/imports/templates":
            return self._handle_import_templates()
        if method == "POST" and route_path == "/imports/files/preview":
            return self._handle_import_file_preview(body, headers)
        if method == "POST" and route_path == "/imports/files/confirm":
            return self._handle_import_file_confirm(body)
        if method == "POST" and route_path == "/imports/files/retry":
            return self._handle_import_file_retry(body)
        if method == "GET" and route_path.startswith("/imports/files/sessions/"):
            session_id = route_path.rsplit("/", 1)[-1]
            return self._handle_import_file_session(session_id)
        if method == "POST" and route_path == "/matching/run":
            return self._handle_matching_run(body)
        if method == "GET" and route_path == "/matching/results":
            return self._handle_matching_results()
        if method == "GET" and route_path.startswith("/matching/results/"):
            result_id = route_path.rsplit("/", 1)[-1]
            return self._handle_matching_result_detail(result_id)
        return self._json_response(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "path": route_path,
                "message": "Route is not defined in the foundation skeleton.",
            },
        )

    def readiness_summary(self) -> dict[str, object]:
        return {
            "service": "fin-ops-platform-api",
            "version": __version__,
            "status": "ready",
            "entrypoints": [
                "/health",
                "/foundation/seed",
                "/imports/preview",
                "/imports/confirm",
                "/imports/templates",
                "/imports/batches/{batch_id}/download",
                "/imports/batches/{batch_id}/revert",
                "/imports/files/preview",
                "/imports/files/confirm",
                "/imports/files/retry",
                "/imports/files/sessions/{session_id}",
                "/matching/run",
                "/matching/results",
                "/api/workbench",
                "/api/search",
                "/api/session/me",
                "/api/workbench/ignored",
                "/api/workbench/settings",
                "/api/workbench/rows/{row_id}",
                "/api/workbench/actions/confirm-link",
                "/api/workbench/actions/mark-exception",
                "/api/workbench/actions/cancel-link",
                "/api/workbench/actions/update-bank-exception",
                "/api/workbench/actions/oa-bank-exception",
                "/api/workbench/actions/cancel-exception",
                "/api/workbench/actions/ignore-row",
                "/api/workbench/actions/unignore-row",
                "/api/tax-offset",
                "/api/tax-offset/certified-import/preview",
                "/api/tax-offset/certified-import/confirm",
                "/api/tax-offset/certified-imports",
                "/api/tax-offset/calculate",
                "/api/cost-statistics",
                "/api/cost-statistics/explorer",
                "/api/cost-statistics/export-preview",
                "/api/cost-statistics/export",
                "/api/cost-statistics/projects/{project_name}",
                "/api/cost-statistics/transactions/{transaction_id}",
                "/workbench",
                "/workbench/actions/confirm",
                "/workbench/actions/difference",
                "/workbench/actions/exception",
                "/workbench/actions/offline",
                "/workbench/actions/offset",
                "/integrations/oa",
                "/integrations/oa/sync",
                "/integrations/oa/sync-runs",
                "/projects",
                "/projects/assign",
                "/ledgers",
                "/reminders",
                "/reconciliation/cases",
            ],
            "capabilities": [
                "reconciliation",
                "audit_trail",
                "seed_data",
                "import_preview",
                "file_import_formalization",
                "import_persistence",
                "matching_engine",
                "manual_workbench",
                "follow_up_ledgers",
                "reminder_scheduler",
                "advanced_exceptions",
                "oa_integration_foundation",
                "oa_session_foundation",
                "project_costing_foundation",
                "workbench_v2_backend_contracts",
                "workbench_global_search_foundation",
                "cost_statistics_foundation",
                "cost_statistics_export",
            ],
            "storage": {
                "mode": self._state_store.storage_mode if self._state_store is not None else "memory",
                "backend": self._state_store.storage_backend if self._state_store is not None else "memory",
                "database": self._state_store.mongo_database_name if self._state_store is not None else None,
            },
            "future_modules": [],
        }

    def _health_payload(self) -> dict[str, object]:
        payload = self.readiness_summary()
        payload["seed_counts"] = {
            key: len(value) for key, value in self._seed_payload.items() if isinstance(value, list)
        }
        payload["module_boundaries"] = {
            "app": ["http entrypoint", "routing", "readiness checks"],
            "domain": ["enums", "core finance models", "status machine boundaries"],
            "services": [
                "audit trail",
                "seed data",
                "imports",
                "matching",
                "ledgers",
                "integrations",
                "workbench v2 contracts",
                "tax offset api",
            ],
            "planned": ["costing"],
        }
        return payload

    def _handle_workbench_prototype(self) -> Response:
        prototype_path = Path(__file__).resolve().parents[4] / "web" / "prototypes" / "reconciliation-workbench-v2.html"
        return Response(
            status_code=int(HTTPStatus.OK),
            body=prototype_path.read_text(encoding="utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    def _handle_api_workbench(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        return self._json_response(HTTPStatus.OK, self._build_api_workbench_payload(current_month))

    def _handle_api_search(
        self,
        *,
        q: str,
        scope: str | None,
        month: str | None,
        project_name: str | None,
        status: str | None,
        limit: str | None,
    ) -> Response:
        resolved_scope = scope or "all"
        resolved_month = month or "all"
        resolved_status = status or None
        try:
            resolved_limit = int(limit) if limit not in (None, "") else 20
        except (TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_search_request", "message": "limit must be an integer."},
            )
        if resolved_scope not in SEARCH_SUPPORTED_SCOPES:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_search_request", "message": "scope must be all, oa, bank, or invoice."},
            )
        if resolved_month != "all" and not SEARCH_MONTH_RE.match(resolved_month):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_search_request", "message": "month must be all or YYYY-MM."},
            )
        if resolved_status is not None and resolved_status not in SEARCH_SUPPORTED_STATUSES:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_search_request",
                    "message": "status must be paired, open, ignored, or processed_exception.",
                },
            )
        payload = self._search_service.search(
            q=q,
            scope=resolved_scope,
            month=resolved_month,
            project_name=project_name,
            status=resolved_status,
            limit=resolved_limit,
        )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_session_me(self, headers: dict[str, str] | None) -> Response:
        try:
            session = resolve_oa_request_session(
                headers,
                identity_service=self._oa_identity_service,
                access_control_service=self._access_control_service,
            )
        except OASessionExpiredError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "OA 登录状态已过期。",
                },
            )
        except OAIdentityConfigurationError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_identity_unavailable",
                    "message": str(error) or "OA 身份服务未配置。",
                },
            )
        except OAIdentityServiceError as error:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_identity_lookup_failed",
                    "message": str(error) or "OA 身份解析失败。",
                },
            )
        except UnauthorizedOASessionError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。",
                },
            )

        return self._json_response(
            HTTPStatus.OK,
            {
                "user": {
                    "user_id": session.identity.user_id,
                    "username": session.identity.username,
                    "nickname": session.identity.nickname,
                    "display_name": session.identity.display_name,
                    "dept_id": session.identity.dept_id,
                    "dept_name": session.identity.dept_name,
                    "avatar": session.identity.avatar,
                },
                "roles": list(session.identity.roles),
                "permissions": list(session.identity.permissions),
                "allowed": session.allowed,
                "access_tier": session.access_tier,
                "can_access_app": session.can_access_app,
                "can_mutate_data": session.can_mutate_data,
                "can_admin_access": session.can_admin_access,
            },
        )

    def _route_requires_oa_access(self, route_path: str) -> bool:
        if route_path == "/api/session/me":
            return False
        protected_prefixes = (
            "/api/",
            "/workbench",
            "/integrations",
            "/projects",
            "/ledgers",
            "/reminders",
            "/reconciliation",
            "/imports",
            "/matching",
        )
        return route_path.startswith(protected_prefixes)

    def _enforce_route_access(self, route_path: str, headers: dict[str, str] | None) -> Response | None:
        if not self._route_requires_oa_access(route_path):
            return None
        try:
            session = resolve_oa_request_session(
                headers,
                identity_service=self._oa_identity_service,
                access_control_service=self._access_control_service,
            )
            if not session.allowed:
                raise ForbiddenOAAccessError("当前 OA 账户未被授权访问财务运营平台。")
        except UnauthorizedOASessionError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。",
                },
            )
        except OASessionExpiredError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "OA 登录状态已过期。",
                },
            )
        except ForbiddenOAAccessError as error:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "forbidden",
                    "message": str(error) or "当前 OA 账户未被授权访问财务运营平台。",
                },
            )
        except OAIdentityConfigurationError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_identity_unavailable",
                    "message": str(error) or "OA 身份服务未配置。",
                },
            )
        except OAIdentityServiceError as error:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_identity_lookup_failed",
                    "message": str(error) or "OA 身份解析失败。",
                },
            )
        return None

    def _handle_api_workbench_ignored(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        raw_payload = self._build_raw_workbench_payload(current_month)
        ignored_rows = self._extract_ignored_rows(raw_payload)
        return self._json_response(
            HTTPStatus.OK,
            {
                "month": current_month,
                "rows": ignored_rows,
            },
        )

    def _handle_api_workbench_settings(self) -> Response:
        return self._json_response(HTTPStatus.OK, self._app_settings_service.get_settings_payload())

    def _handle_api_workbench_settings_update(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        completed_project_ids = payload.get("completed_project_ids", [])
        bank_account_mappings = payload.get("bank_account_mappings", [])
        allowed_usernames = payload.get("allowed_usernames", [])
        readonly_export_usernames = payload.get("readonly_export_usernames", [])
        admin_usernames = payload.get("admin_usernames", [])
        if (
            not isinstance(completed_project_ids, list)
            or not isinstance(bank_account_mappings, list)
            or not isinstance(allowed_usernames, list)
            or not isinstance(readonly_export_usernames, list)
            or not isinstance(admin_usernames, list)
        ):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_request",
                    "message": (
                        "completed_project_ids, bank_account_mappings, allowed_usernames, "
                        "readonly_export_usernames, and admin_usernames must be arrays."
                    ),
                },
            )
        try:
            updated_payload = self._app_settings_service.update_settings(
                completed_project_ids=[str(item) for item in completed_project_ids],
                bank_account_mappings=[item for item in bank_account_mappings if isinstance(item, dict)],
                allowed_usernames=[str(item).strip() for item in allowed_usernames if str(item).strip()],
                readonly_export_usernames=[
                    str(item).strip() for item in readonly_export_usernames if str(item).strip()
                ],
                admin_usernames=[str(item).strip() for item in admin_usernames if str(item).strip()],
            )
        except OARoleSyncError as exc:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_role_sync_failed",
                    "message": f"OA 角色同步失败：{exc}",
                },
            )
        self._search_service.clear_cache()
        return self._json_response(HTTPStatus.OK, updated_payload)

    def _handle_api_workbench_row_detail(self, row_id: str) -> Response:
        try:
            payload = self._get_api_workbench_row_detail_payload(row_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "row_id": row_id},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _get_api_workbench_row_detail_payload(self, row_id: str) -> dict[str, object]:
        try:
            payload = {"row": self._live_workbench_service.get_row_detail(row_id)}
        except KeyError:
            payload = self._workbench_api_routes.get_row_detail(row_id)
        payload["row"] = self._workbench_override_service.apply_to_row(payload["row"])
        return payload

    def _handle_api_cost_statistics(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        payload = self._cost_statistics_service.get_month_statistics(current_month)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_explorer(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        payload = self._cost_statistics_service.get_explorer(current_month)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_project(self, month: str | None, project_name: str) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        payload = self._cost_statistics_service.get_project_statistics(current_month, project_name)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_export(
        self,
        *,
        month: str | None,
        view: str | None,
        project_names: list[str] | None,
        expense_types: list[str] | None,
        transaction_id: str | None,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        aggregate_by: str | None = None,
        include_oa_details: bool = True,
        include_invoice_details: bool = True,
        include_exception_rows: bool = True,
        include_ignored_rows: bool = True,
        include_expense_content_summary: bool = True,
        sort_by: str | None = None,
    ) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        if view not in {"month", "time", "project", "expense_type", "transaction"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_request", "message": "view must be month, time, project, expense_type, or transaction."},
            )
        try:
            filename, content = self._cost_statistics_service.export_view(
                month=current_month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                transaction_id=transaction_id,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
                include_oa_details=include_oa_details,
                include_invoice_details=include_invoice_details,
                include_exception_rows=include_exception_rows,
                include_ignored_rows=include_ignored_rows,
                include_expense_content_summary=include_expense_content_summary,
                sort_by=sort_by or "time",
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        except ValueError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_request", "message": str(error)},
            )
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            },
        )

    def _handle_api_cost_statistics_export_preview(
        self,
        *,
        month: str | None,
        view: str | None,
        project_names: list[str] | None,
        expense_types: list[str] | None,
        start_month: str | None = None,
        end_month: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        aggregate_by: str | None = None,
    ) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        if view not in {"time", "project", "expense_type"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_cost_statistics_export_preview_request",
                    "message": "view must be time, project, or expense_type.",
                },
            )
        try:
            payload = self._cost_statistics_service.get_export_preview(
                month=current_month,
                view=view,
                project_names=project_names,
                expense_types=expense_types,
                start_month=start_month,
                end_month=end_month,
                start_date=start_date,
                end_date=end_date,
                aggregate_by=aggregate_by,
            )
        except ValueError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_preview_request", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_transaction(self, transaction_id: str) -> Response:
        try:
            payload = self._cost_statistics_service.get_transaction_detail(transaction_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_workbench_confirm_link(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_confirm_link(payload)
        return self._handle_api_workbench_action_payload(payload, self._workbench_api_routes.confirm_link, "invalid_confirm_link_request")

    def _handle_api_workbench_mark_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_mark_exception(payload)
        return self._handle_api_workbench_action_payload(payload, self._workbench_api_routes.mark_exception, "invalid_mark_exception_request")

    def _handle_api_workbench_cancel_link(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_cancel_link(payload)
        return self._handle_api_workbench_action_payload(payload, self._workbench_api_routes.cancel_link, "invalid_cancel_link_request")

    def _handle_api_workbench_update_bank_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_update_bank_exception(payload)
        return self._handle_api_workbench_action_payload(
            payload,
            self._workbench_api_routes.update_bank_exception,
            "invalid_update_bank_exception_request",
        )

    def _handle_api_workbench_oa_bank_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_oa_bank_exception(payload)
        return self._handle_live_workbench_oa_bank_exception(payload)

    def _handle_api_workbench_cancel_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_cancel_exception(payload)
        return self._handle_live_workbench_cancel_exception(payload)

    def _handle_api_workbench_ignore_row(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        return self._handle_workbench_ignore_row_payload(payload)

    def _handle_api_workbench_unignore_row(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        return self._handle_workbench_unignore_row_payload(payload)

    def _handle_api_tax_offset(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        return self._json_response(HTTPStatus.OK, self._tax_api_routes.get_tax_offset(current_month))

    def _handle_api_tax_certified_import_preview(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        imported_by = (fields.get("imported_by") or ["system"])[0]
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_request",
                    "message": "至少上传一个已认证发票文件。",
                },
            )
        session = self._tax_certified_import_service.preview_files(
            imported_by=imported_by,
            uploads=[UploadedCertifiedImportFile(file_name=file.file_name, content=file.content) for file in files],
        )
        preview_files = []
        total_matched_plan_count = 0
        total_outside_plan_count = 0
        for preview_file in session.files:
            preview_counts = self._tax_offset_service.summarize_certified_preview_rows(
                preview_file.month,
                preview_file.rows,
            )
            total_matched_plan_count += preview_counts["matched_plan_count"]
            total_outside_plan_count += preview_counts["outside_plan_count"]
            preview_files.append(
                {
                    **asdict(preview_file),
                    **preview_counts,
                }
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "session": session,
                "files": preview_files,
                "summary": {
                    "recognized_count": sum(file["recognized_count"] for file in preview_files),
                    "invalid_count": sum(file["invalid_count"] for file in preview_files),
                    "matched_plan_count": total_matched_plan_count,
                    "outside_plan_count": total_outside_plan_count,
                },
            },
        )

    def _handle_api_tax_certified_import_confirm(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_confirm_request",
                    "message": "session_id is required.",
                },
            )
        try:
            batch = self._tax_certified_import_service.confirm_session(session_id)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "tax_certified_import_session_not_found", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "batch": batch,
            },
        )

    def _handle_api_tax_certified_imports(self, month: str | None) -> Response:
        if month is None or not month.strip():
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_request",
                    "message": "month is required.",
                },
            )
        current_month = month.strip()
        records = self._tax_certified_import_service.list_records_for_month(current_month)
        return self._json_response(
            HTTPStatus.OK,
            {
                "month": current_month,
                "records": records,
            },
        )

    def _handle_api_tax_offset_calculate(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            result = self._tax_api_routes.calculate(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_calculate_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, result)

    def _handle_workbench(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        payload = self._reconciliation_service.build_workbench(month=current_month)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_workbench_action(
        self,
        body: str | bytes | None,
        action_handler: Callable[[dict[str, object]], dict[str, object]],
        error_code: str,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        return self._handle_api_workbench_action_payload(payload, action_handler, error_code)

    def _handle_api_workbench_action_payload(
        self,
        payload: dict[str, object],
        action_handler: Callable[[dict[str, object]], dict[str, object]],
        error_code: str,
    ) -> Response:
        try:
            result = action_handler(payload)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )
        except (TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": error_code, "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, result)

    def _handle_live_workbench_confirm_link(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_ids = [str(row_id) for row_id in list(payload["row_ids"])]
            case_id = str(payload["case_id"]) if payload.get("case_id") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_request", "message": str(exc)},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            rows = [self._resolve_live_row(grouped_payload, row_id) for row_id in row_ids]
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        _, updated_rows = self._workbench_override_service.confirm_link(rows=rows, case_id=case_id)
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_link",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
                "updated_rows": updated_rows,
                "message": f"已确认 {len(updated_rows)} 条记录关联。",
            },
        )

    def _handle_live_workbench_mark_exception(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            exception_code = str(payload["exception_code"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_mark_exception_request", "message": str(exc)},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            row = self._resolve_live_row(grouped_payload, row_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        updated_row = self._workbench_override_service.mark_exception(
            row=row,
            exception_code=exception_code,
            comment=comment,
        )
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "mark_exception",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "updated_rows": [updated_row],
                "message": "已标记异常。",
            },
        )

    def _handle_live_workbench_cancel_link(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_link_request", "message": str(exc)},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        group = self._resolve_live_group(grouped_payload, row_id)
        if group is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        group_rows = [
            *group.get("oa_rows", []),
            *group.get("bank_rows", []),
            *group.get("invoice_rows", []),
        ]
        updated_rows = self._workbench_override_service.cancel_link(rows=group_rows, comment=comment)
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_link",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
                "updated_rows": updated_rows,
                "message": "已取消关联并回退为待处理。",
            },
        )

    def _handle_live_workbench_update_bank_exception(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            relation_code = str(payload["relation_code"])
            relation_label = str(payload["relation_label"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_update_bank_exception_request", "message": str(exc)},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            row = self._resolve_live_row(grouped_payload, row_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        if row.get("type") != "bank":
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_update_bank_exception_request", "message": "update_bank_exception only supports bank rows."},
            )
        updated_row = self._workbench_override_service.update_bank_exception(
            row=row,
            relation_code=relation_code,
            relation_label=relation_label,
            comment=comment,
        )
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "update_bank_exception",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "updated_rows": [updated_row],
                "message": "已更新银行异常分类。",
            },
        )

    def _handle_live_workbench_oa_bank_exception(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_ids = [str(row_id) for row_id in list(payload["row_ids"])]
            exception_code = str(payload["exception_code"])
            exception_label = str(payload["exception_label"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": str(exc)},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            rows = [self._resolve_live_row(grouped_payload, row_id) for row_id in row_ids]
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        if any(str(row.get("type")) == "invoice" for row in rows):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_oa_bank_exception_request",
                    "message": "oa_bank_exception does not support invoice rows.",
                },
            )
        if not rows:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": "row_ids is required."},
            )

        try:
            updated_rows = self._workbench_override_service.apply_oa_bank_exception(
                rows=rows,
                exception_code=exception_code,
                exception_label=exception_label,
                comment=comment,
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": str(exc)},
            )

        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "oa_bank_exception",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
                "updated_rows": updated_rows,
                "message": f"已对 {len(updated_rows)} 条记录执行 OA/流水异常处理。",
            },
        )

    def _handle_live_workbench_cancel_exception(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_ids = [str(row_id) for row_id in list(payload["row_ids"])]
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_exception_request", "message": str(exc)},
            )

        if not row_ids:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_exception_request", "message": "row_ids is required."},
            )

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            rows = [self._resolve_live_row(grouped_payload, row_id) for row_id in row_ids]
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        updated_rows = self._workbench_override_service.cancel_exception(rows=rows, comment=comment)
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_exception",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
                "updated_rows": updated_rows,
                "message": f"已取消 {len(updated_rows)} 条记录的异常处理。",
            },
        )

    def _handle_workbench_ignore_row_payload(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ignore_row_request", "message": str(exc)},
            )

        raw_payload = self._build_raw_workbench_payload(month)
        try:
            row = self._resolve_live_row(self._group_row_payload(raw_payload), row_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        if row.get("type") != "invoice":
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ignore_row_request", "message": "ignore_row only supports invoice rows."},
            )
        updated_row = self._workbench_override_service.ignore_row(row=row, comment=comment)
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "ignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "updated_rows": [updated_row],
                "message": "已忽略 1 条记录。",
            },
        )

    def _handle_workbench_unignore_row_payload(self, payload: dict[str, object]) -> Response:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_unignore_row_request", "message": str(exc)},
            )

        raw_payload = self._build_raw_workbench_payload(month)
        ignored_rows = {str(row["id"]): row for row in self._extract_ignored_rows(raw_payload)}
        row = ignored_rows.get(row_id)
        if row is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        updated_row = self._workbench_override_service.unignore_row(row=row)
        self._persist_workbench_overrides()
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "unignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "updated_rows": [updated_row],
                "message": "已撤回忽略 1 条记录。",
            },
        )

    def _handle_workbench_confirm(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            actor_id = str(payload["actor_id"])
            invoice_ids = list(payload["invoice_ids"])
            transaction_ids = list(payload["transaction_ids"])
        except (KeyError, TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_confirm_request",
                    "message": "actor_id, invoice_ids and transaction_ids are required.",
                },
            )

        try:
            case = self._reconciliation_service.confirm_manual_reconciliation(
                actor_id=actor_id,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                source_result_id=payload.get("source_result_id"),
                remark=payload.get("remark"),
                amount=payload.get("amount"),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_confirm_request", "message": str(exc)},
            )
        ledgers = self._ledger_service.sync_from_case(case)
        return self._json_response(HTTPStatus.OK, {"case": case, "ledgers": ledgers})

    def _handle_workbench_difference(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            actor_id = str(payload["actor_id"])
            invoice_ids = list(payload["invoice_ids"])
            transaction_ids = list(payload["transaction_ids"])
            difference_reason = str(payload["difference_reason"])
        except (KeyError, TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_difference_request",
                    "message": "actor_id, invoice_ids, transaction_ids and difference_reason are required.",
                },
            )

        try:
            case = self._reconciliation_service.confirm_difference_reconciliation(
                actor_id=actor_id,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                difference_reason=difference_reason,
                difference_note=payload.get("difference_note"),
                oa_ids=list(payload.get("oa_ids", [])),
                source_result_id=payload.get("source_result_id"),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_difference_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"case": case})

    def _handle_workbench_exception(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            actor_id = str(payload["actor_id"])
            biz_side = str(payload["biz_side"])
            exception_code = str(payload["exception_code"])
            invoice_ids = list(payload.get("invoice_ids", []))
            transaction_ids = list(payload.get("transaction_ids", []))
        except (KeyError, TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_exception_request",
                    "message": "actor_id, biz_side and exception_code are required.",
                },
            )

        try:
            case, record = self._reconciliation_service.record_exception(
                actor_id=actor_id,
                biz_side=biz_side,
                exception_code=exception_code,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                resolution_action=payload.get("resolution_action"),
                note=payload.get("note"),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_exception_request", "message": str(exc)},
            )
        ledgers = self._ledger_service.sync_from_case(case, exception_record=record)
        return self._json_response(
            HTTPStatus.OK,
            {"case": case, "exception_record": record, "ledgers": ledgers},
        )

    def _handle_workbench_offline(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            actor_id = str(payload["actor_id"])
            biz_side = str(payload["biz_side"])
            amount = payload["amount"]
            payment_method = str(payload["payment_method"])
            occurred_on = str(payload["occurred_on"])
            invoice_ids = list(payload.get("invoice_ids", []))
            transaction_ids = list(payload.get("transaction_ids", []))
        except (KeyError, TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_offline_request",
                    "message": "actor_id, biz_side, amount, payment_method and occurred_on are required.",
                },
            )

        try:
            case, record = self._reconciliation_service.record_offline_reconciliation(
                actor_id=actor_id,
                biz_side=biz_side,
                invoice_ids=invoice_ids,
                transaction_ids=transaction_ids,
                oa_ids=list(payload.get("oa_ids", [])),
                amount=amount,
                payment_method=payment_method,
                occurred_on=occurred_on,
                note=payload.get("note"),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_offline_request", "message": str(exc)},
            )
        ledgers = self._ledger_service.sync_from_case(case)
        return self._json_response(
            HTTPStatus.OK,
            {"case": case, "offline_record": record, "ledgers": ledgers},
        )

    def _handle_workbench_offset(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            actor_id = str(payload["actor_id"])
            receivable_invoice_ids = list(payload["receivable_invoice_ids"])
            payable_invoice_ids = list(payload["payable_invoice_ids"])
            reason = str(payload["reason"])
        except (KeyError, TypeError, ValueError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_offset_request",
                    "message": "actor_id, receivable_invoice_ids, payable_invoice_ids and reason are required.",
                },
            )

        try:
            case, offset_note = self._reconciliation_service.record_offset_reconciliation(
                actor_id=actor_id,
                receivable_invoice_ids=receivable_invoice_ids,
                payable_invoice_ids=payable_invoice_ids,
                reason=reason,
                note=payload.get("note"),
                amount=payload.get("amount"),
                oa_ids=list(payload.get("oa_ids", [])),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_workbench_offset_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"case": case, "offset_note": offset_note})

    def _handle_oa_dashboard(self) -> Response:
        return self._json_response(HTTPStatus.OK, self._integration_service.build_dashboard())

    def _handle_oa_sync(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        actor_id = payload.get("actor_id")
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_sync_request", "message": "actor_id is required."},
            )
        try:
            run = self._integration_service.sync(
                scope=str(payload.get("scope", "all")),
                triggered_by=str(actor_id),
                retry_run_id=payload.get("retry_run_id"),
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "oa_sync_run_not_found", "run_id": payload.get("retry_run_id")},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_sync_request", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"run": self._serialize_sync_run(run), "dashboard": self._integration_service.build_dashboard()},
        )

    def _handle_oa_sync_runs(self) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            {"runs": [self._serialize_sync_run(run) for run in self._integration_service.list_sync_runs()]},
        )

    def _handle_oa_sync_run_detail(self, run_id: str) -> Response:
        try:
            run = self._integration_service.get_sync_run(run_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "oa_sync_run_not_found", "run_id": run_id},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"run": self._serialize_sync_run(run), "issues": self._serialize_value(run.issues)},
        )

    def _handle_projects(self) -> Response:
        return self._json_response(HTTPStatus.OK, self._project_costing_service.build_project_hub())

    def _handle_project_create(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = payload.get("actor_id")
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": "actor_id is required."},
            )
        try:
            project = self._project_costing_service.create_project(
                actor_id=str(actor_id),
                project_code=str(payload.get("project_code", "")),
                project_name=str(payload.get("project_name", "")),
                project_status=str(payload.get("project_status", "active")),
                department_name=payload.get("department_name"),
                owner_name=payload.get("owner_name"),
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"project": project, "hub": self._project_costing_service.build_project_hub()})

    def _handle_project_assign(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = payload.get("actor_id")
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_assign_request", "message": "actor_id is required."},
            )
        try:
            assignment = self._project_costing_service.assign_project(
                actor_id=str(actor_id),
                object_type=str(payload.get("object_type", "")),
                object_id=str(payload.get("object_id", "")),
                project_id=str(payload.get("project_id", "")),
                note=payload.get("note"),
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "project_or_object_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_assign_request", "message": str(exc)},
            )
        detail = self._project_costing_service.get_project_detail(assignment.project_id)
        return self._json_response(HTTPStatus.OK, {"assignment": assignment, **detail})

    def _handle_project_detail(self, project_id: str) -> Response:
        try:
            detail = self._project_costing_service.get_project_detail(project_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "project_not_found", "project_id": project_id},
            )
        return self._json_response(HTTPStatus.OK, detail)

    def _handle_ledgers(self, *, view: str, as_of: str | None, status: str | None) -> Response:
        try:
            ledgers = self._ledger_service.list_ledgers(view=view, as_of=as_of, status=status)
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ledger_query", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"ledgers": ledgers})

    def _handle_ledger_detail(self, ledger_id: str) -> Response:
        try:
            ledger = self._ledger_service.get_ledger(ledger_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "ledger_not_found", "ledger_id": ledger_id},
            )
        return self._json_response(HTTPStatus.OK, {"ledger": ledger})

    def _handle_ledger_status_update(self, ledger_id: str, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = payload.get("actor_id")
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ledger_status_request", "message": "actor_id is required."},
            )
        try:
            ledger = self._ledger_service.update_ledger(
                ledger_id,
                actor_id=str(actor_id),
                status=payload.get("status"),
                expected_date=payload.get("expected_date"),
                note=payload.get("note"),
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "ledger_not_found", "ledger_id": ledger_id},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ledger_status_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"ledger": ledger})

    def _handle_reminders(self, *, as_of: str | None, status: str | None) -> Response:
        try:
            reminders = self._ledger_service.list_reminders(as_of=as_of, status=status)
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_reminder_query", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"reminders": reminders})

    def _handle_reminder_run(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        as_of = payload.get("as_of")
        if not as_of:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_reminder_run_request", "message": "as_of is required."},
            )
        try:
            sent_reminders = self._ledger_service.run_reminders(as_of=str(as_of))
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_reminder_run_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"sent_reminders": sent_reminders})

    def _handle_reconciliation_cases(self) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            {"cases": self._reconciliation_service.list_cases()},
        )

    def _handle_reconciliation_case_detail(self, case_id: str) -> Response:
        try:
            case = self._reconciliation_service.get_case(case_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "reconciliation_case_not_found", "case_id": case_id},
            )
        return self._json_response(HTTPStatus.OK, {"case": case})

    def _handle_import_preview(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        try:
            batch_type = BatchType(payload["batch_type"])
            source_name = payload["source_name"]
            imported_by = payload["imported_by"]
            rows = payload["rows"]
        except (KeyError, ValueError, TypeError):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_preview_request",
                    "message": "batch_type, source_name, imported_by and rows are required.",
                },
            )

        preview = self._import_service.preview_import(
            batch_type=batch_type,
            source_name=source_name,
            imported_by=imported_by,
            rows=rows,
        )
        self._persist_state()
        return self._json_response(HTTPStatus.OK, self._serialize_preview(preview))

    def _handle_import_confirm(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error

        batch_id = payload.get("batch_id")
        if not batch_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_confirm_request",
                    "message": "batch_id is required.",
                },
            )
        try:
            batch = self._import_service.confirm_import(batch_id)
            preview = self._import_service.get_batch(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        self._persist_state()
        return self._json_response(
            HTTPStatus.OK,
            {
                "batch": self._serialize_value(batch),
                "row_results": self._serialize_value(preview.row_results),
            },
        )

    def _handle_import_batch(self, batch_id: str) -> Response:
        try:
            preview = self._import_service.get_batch(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_preview(preview))

    def _handle_import_batch_download(self, batch_id: str) -> Response:
        try:
            preview = self._import_service.get_batch(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        body = json.dumps(self._serialize_preview(preview), ensure_ascii=False)
        return Response(
            status_code=int(HTTPStatus.OK),
            body=body,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Content-Disposition": f'attachment; filename="{batch_id}.json"',
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            },
        )

    def _handle_import_batch_revert(self, batch_id: str) -> Response:
        try:
            batch = self._import_service.revert_import(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        self._file_import_service.mark_batch_reverted(batch_id)
        self._persist_state()
        return self._json_response(HTTPStatus.OK, {"batch": self._serialize_value(batch)})

    def _handle_import_templates(self) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            {
                "templates": self._file_import_service.list_templates(),
            },
        )

    def _handle_import_file_preview(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        imported_by = (fields.get("imported_by") or [""])[0]
        if not imported_by:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_preview_request", "message": "imported_by is required."},
            )
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_preview_request", "message": "At least one file is required."},
            )
        session = self._file_import_service.preview_files(imported_by=imported_by, uploads=files)
        self._persist_state()
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_confirm(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("session_id")
        selected_file_ids = payload.get("selected_file_ids")
        if not session_id or not isinstance(selected_file_ids, list):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_file_confirm_request",
                    "message": "session_id and selected_file_ids are required.",
                },
            )
        try:
            session = self._file_import_service.confirm_session(
                session_id=str(session_id),
                selected_file_ids=[str(item) for item in selected_file_ids],
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": str(exc)},
            )
        matching_run = None
        if any(file.status == "confirmed" for file in session.files):
            matching_run = self._matching_service.run(triggered_by=f"import_session:{session.id}")
        self._persist_state()
        response_payload = self._serialize_file_session(session)
        if matching_run is not None:
            response_payload["matching_run"] = self._serialize_matching_run(matching_run)
        return self._json_response(HTTPStatus.OK, response_payload)

    def _handle_import_file_retry(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("session_id")
        selected_file_ids = payload.get("selected_file_ids")
        if not session_id or not isinstance(selected_file_ids, list):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_file_retry_request",
                    "message": "session_id and selected_file_ids are required.",
                },
            )
        try:
            session = self._file_import_service.retry_session_files(
                session_id=str(session_id),
                selected_file_ids=[str(item) for item in selected_file_ids],
                overrides=payload.get("overrides") if isinstance(payload.get("overrides"), dict) else None,
            )
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_retry_request", "message": str(exc)},
            )
        self._persist_state()
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_session(self, session_id: str) -> Response:
        try:
            session = self._file_import_service.get_session(session_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "session_id": session_id},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_matching_run(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        triggered_by = str(payload.get("triggered_by", "system"))
        run = self._matching_service.run(triggered_by=triggered_by)
        self._persist_state()
        return self._json_response(
            HTTPStatus.OK,
            {
                "run": self._serialize_matching_run(run),
                "results": self._serialize_value(run.results),
            },
        )

    def _handle_matching_results(self) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            {
                "runs": [self._serialize_matching_run(run) for run in self._matching_service.list_runs()],
                "results": self._serialize_value(self._matching_service.list_results()),
            },
        )

    def _handle_matching_result_detail(self, result_id: str) -> Response:
        try:
            result = self._matching_service.get_result(result_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "matching_result_not_found", "result_id": result_id},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"result": self._serialize_value(result)},
        )

    def _serialize_preview(self, preview: object) -> dict[str, object]:
        return {
            "batch": self._serialize_value(preview.batch),
            "row_results": self._serialize_value(preview.row_results),
            "normalized_rows": self._serialize_value(preview.normalized_rows),
        }

    def _persist_state(self) -> None:
        self._search_service.clear_cache()
        if self._state_store is None:
            return
        self._state_store.save(
            {
                "imports": self._import_service.snapshot(),
                "file_imports": self._file_import_service.snapshot(),
                "matching": self._matching_service.snapshot(),
                "workbench_overrides": self._workbench_override_service.snapshot(),
            }
        )

    def _persist_workbench_overrides(self) -> None:
        self._search_service.clear_cache()
        if self._state_store is None:
            return
        self._state_store.save_workbench_overrides(self._workbench_override_service.snapshot())

    def _list_search_months(self) -> list[str]:
        months = set(self._workbench_query_service.list_available_months())
        months.update(
            invoice.invoice_date[:7]
            for invoice in self._import_service.list_invoices()
            if invoice.invoice_date
        )
        months.update(
            transaction.txn_date[:7]
            for transaction in self._import_service.list_transactions()
            if transaction.txn_date
        )
        return sorted(month for month in months if month)

    def _serialize_file_session(self, session: object) -> dict[str, object]:
        return {
            "session": {
                "id": session.id,
                "imported_by": session.imported_by,
                "file_count": session.file_count,
                "status": session.status,
                "created_at": self._serialize_value(session.created_at),
            },
            "files": self._serialize_value(session.files),
        }

    def _serialize_matching_run(self, run: object) -> dict[str, object]:
        payload = self._serialize_value(run)
        payload["result_count"] = run.result_count
        payload["automatic_count"] = run.automatic_count
        payload["suggested_count"] = run.suggested_count
        payload["manual_review_count"] = run.manual_review_count
        return payload

    def _serialize_sync_run(self, run: object) -> dict[str, object]:
        payload = self._serialize_value(run)
        payload["issue_count"] = run.issue_count
        return payload

    def _build_api_workbench_payload(self, month: str) -> dict[str, object]:
        return self._group_row_payload(self._build_raw_workbench_payload(month))

    def _build_raw_workbench_payload(self, month: str) -> dict[str, object]:
        if self._live_workbench_service.has_rows_for_month(month):
            return self._build_live_workbench_row_payload(month)
        payload = self._workbench_api_routes.get_workbench(month)
        return self._workbench_override_service.apply_to_payload(self._serialize_value(payload))

    def _build_live_workbench_row_payload(self, month: str) -> dict[str, object]:
        live_payload = self._live_workbench_service.get_workbench(month)
        oa_payload = self._workbench_api_routes.get_workbench(month)
        merged = self._merge_live_workbench_with_oa_rows(live_payload, oa_payload)
        return self._workbench_override_service.apply_to_payload(merged)

    @staticmethod
    def _merge_live_workbench_with_oa_rows(
        live_payload: dict[str, object],
        oa_payload: dict[str, object],
    ) -> dict[str, object]:
        merged = Application._serialize_value(live_payload)
        merged["paired"]["oa"] = Application._serialize_value(oa_payload["paired"]["oa"])
        merged["open"]["oa"] = Application._serialize_value(oa_payload["open"]["oa"])
        return merged

    @staticmethod
    def _merge_live_workbench_with_oa(
        live_payload: dict[str, object],
        oa_payload: dict[str, object],
    ) -> dict[str, object]:
        return Application._group_row_payload(Application._merge_live_workbench_with_oa_rows(live_payload, oa_payload))

    @staticmethod
    def _group_row_payload(payload: dict[str, object]) -> dict[str, object]:
        grouping_service = WorkbenchCandidateGroupingService()
        paired = payload.get("paired", {})
        open_rows = payload.get("open", {})
        oa_rows = [row for row in [*list(paired.get("oa", [])), *list(open_rows.get("oa", []))] if not row.get("ignored")]
        bank_rows = [row for row in [*list(paired.get("bank", [])), *list(open_rows.get("bank", []))] if not row.get("ignored")]
        invoice_rows = [row for row in [*list(paired.get("invoice", [])), *list(open_rows.get("invoice", []))] if not row.get("ignored")]
        return grouping_service.group_payload(
            str(payload.get("month", "")),
            oa_rows=oa_rows,
            bank_rows=bank_rows,
            invoice_rows=invoice_rows,
        )

    def _apply_grouped_row_overrides(self, payload: dict[str, object]) -> dict[str, object]:
        result = self._serialize_value(payload)
        for section in ("paired", "open"):
            section_payload = result.get(section, {})
            groups = list(section_payload.get("groups", []))
            normalized_groups = []
            for group in groups:
                normalized_group = self._serialize_value(group)
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    normalized_group[key] = [
                        self._workbench_override_service.apply_to_row(row)
                        for row in normalized_group.get(key, [])
                    ]
                normalized_groups.append(normalized_group)
            section_payload["groups"] = normalized_groups
        return result

    def _grouped_rows_by_id(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        rows_by_id: dict[str, dict[str, object]] = {}
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            for group in section_payload.get("groups", []):
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    for row in group.get(key, []):
                        rows_by_id[str(row["id"])] = row
        return rows_by_id

    def _group_for_row_id(self, payload: dict[str, object], row_id: str) -> dict[str, object] | None:
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            for group in section_payload.get("groups", []):
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    if any(str(row["id"]) == row_id for row in group.get(key, [])):
                        return group
        return None

    def _resolve_live_row(self, grouped_payload: dict[str, object], row_id: str) -> dict[str, object]:
        rows_by_id = self._grouped_rows_by_id(grouped_payload)
        row = rows_by_id.get(row_id)
        if row is not None:
            return row

        try:
            oa_row = self._workbench_query_service.serialize_row(self._workbench_query_service.get_row_record(row_id))
            return self._workbench_override_service.apply_to_row(oa_row)
        except KeyError:
            pass

        try:
            live_row = self._live_workbench_service.get_row_detail(row_id)
            return self._workbench_override_service.apply_to_row(live_row)
        except KeyError as exc:
            raise KeyError(row_id) from exc

    def _resolve_live_group(self, grouped_payload: dict[str, object], row_id: str) -> dict[str, object] | None:
        group = self._group_for_row_id(grouped_payload, row_id)
        if group is not None:
            return group

        try:
            row = self._resolve_live_row(grouped_payload, row_id)
        except KeyError:
            return None

        case_id = row.get("case_id")
        if case_id in (None, ""):
            return {
                "group_id": f"row:{row_id}",
                "oa_rows": [row] if row.get("type") == "oa" else [],
                "bank_rows": [row] if row.get("type") == "bank" else [],
                "invoice_rows": [row] if row.get("type") == "invoice" else [],
            }

        related_rows: list[dict[str, object]] = []
        rows_by_id = self._grouped_rows_by_id(grouped_payload)
        for candidate in rows_by_id.values():
            if candidate.get("case_id") == case_id:
                related_rows.append(candidate)

        if not related_rows:
            related_rows = [row]
        elif all(str(candidate.get("id")) != row_id for candidate in related_rows):
            related_rows.append(row)

        return {
            "group_id": f"case:{case_id}",
            "oa_rows": [candidate for candidate in related_rows if candidate.get("type") == "oa"],
            "bank_rows": [candidate for candidate in related_rows if candidate.get("type") == "bank"],
            "invoice_rows": [candidate for candidate in related_rows if candidate.get("type") == "invoice"],
        }

    @staticmethod
    def _extract_ignored_rows(payload: dict[str, object]) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            for key in ("oa", "bank", "invoice"):
                for row in section_payload.get(key, []):
                    if row.get("ignored"):
                        rows.append(row)
        return rows

    @staticmethod
    def _load_json_body(body: str | bytes | None) -> tuple[dict[str, object], Response | None]:
        if not body:
            return {}, Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {"error": "empty_json_body", "message": "Request body is required."},
                    ensure_ascii=False,
                ),
            )
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return {}, Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {"error": "invalid_json_body", "message": "Request body must be valid JSON."},
                    ensure_ascii=False,
                ),
            )
        if not isinstance(payload, dict):
            return {}, Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {"error": "invalid_json_body", "message": "JSON body must be an object."},
                    ensure_ascii=False,
                ),
            )
        return payload, None

    @staticmethod
    def _parse_optional_bool(value: str | None, *, default: bool) -> bool:
        if value is None:
            return default
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def _load_multipart_body(
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> tuple[dict[str, list[str]], list[UploadedImportFile], Response | None]:
        if not body or headers is None:
            return {}, [], Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {"error": "invalid_multipart_body", "message": "Multipart body is required."},
                    ensure_ascii=False,
                ),
            )
        if isinstance(body, str):
            body = body.encode("utf-8")
        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        if "multipart/form-data" not in content_type:
            return {}, [], Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {
                        "error": "invalid_multipart_body",
                        "message": "Content-Type must be multipart/form-data.",
                    },
                    ensure_ascii=False,
                ),
            )
        boundary_marker = "boundary="
        if boundary_marker not in content_type:
            return {}, [], Response(
                status_code=int(HTTPStatus.BAD_REQUEST),
                body=json.dumps(
                    {"error": "invalid_multipart_body", "message": "Multipart boundary is missing."},
                    ensure_ascii=False,
                ),
            )
        boundary = content_type.split(boundary_marker, 1)[1].strip().strip('"')
        delimiter = f"--{boundary}".encode("utf-8")
        fields: dict[str, list[str]] = {}
        files: list[UploadedImportFile] = []
        for raw_part in body.split(delimiter):
            part = raw_part
            if part.startswith(b"\r\n"):
                part = part[2:]
            if part.endswith(b"--\r\n"):
                part = part[:-4]
            elif part.endswith(b"--"):
                part = part[:-2]
            elif part.endswith(b"\r\n"):
                part = part[:-2]
            if not part:
                continue
            header_blob, separator, content = part.partition(b"\r\n\r\n")
            if not separator:
                continue
            header_lines = header_blob.decode("utf-8").split("\r\n")
            header_map: dict[str, str] = {}
            for header_line in header_lines:
                if ":" not in header_line:
                    continue
                key, value = header_line.split(":", 1)
                header_map[key.strip().lower()] = value.strip()
            disposition = header_map.get("content-disposition", "")
            name_match = None
            filename_match = None
            for token in disposition.split(";"):
                token = token.strip()
                if token.startswith("name="):
                    name_match = token.split("=", 1)[1].strip('"')
                elif token.startswith("filename="):
                    filename_match = token.split("=", 1)[1].strip('"')
            if not name_match:
                continue
            if filename_match is not None:
                files.append(UploadedImportFile(file_name=filename_match, content=content))
            else:
                fields.setdefault(name_match, []).append(content.decode("utf-8").strip())
        return fields, files, None

    @staticmethod
    def _json_response(status: HTTPStatus, payload: dict[str, object]) -> Response:
        normalized_payload = Application._serialize_value(payload)
        return Response(status_code=int(status), body=json.dumps(normalized_payload, ensure_ascii=False))

    @staticmethod
    def _serialize_value(value: object) -> object:
        if is_dataclass(value):
            return {key: Application._serialize_value(val) for key, val in asdict(value).items()}
        if isinstance(value, dict):
            return {str(key): Application._serialize_value(val) for key, val in value.items()}
        if isinstance(value, list):
            return [Application._serialize_value(item) for item in value]
        if isinstance(value, Decimal):
            return f"{value:.2f}"
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Enum):
            return value.value
        return value


def build_application(*, data_dir: Path | None = None) -> Application:
    return Application(data_dir=data_dir)


def run_http_server(host: str, port: int, app: Application | None = None) -> None:
    application = app or build_application()
    handler_factory = _build_handler_factory(application)
    server = ThreadingHTTPServer((host, port), handler_factory)
    print(f"Serving fin-ops-platform foundation API on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _build_handler_factory(app: Application) -> Callable[..., BaseHTTPRequestHandler]:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._dispatch("POST")

        def do_OPTIONS(self) -> None:  # noqa: N802
            self._dispatch("OPTIONS")

        def _dispatch(self, method: str) -> None:
            body: bytes | None = None
            if method == "POST":
                content_length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(content_length) if content_length > 0 else None
            response = app.handle_request(method, self.path, body, dict(self.headers.items()))
            encoded = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return RequestHandler
