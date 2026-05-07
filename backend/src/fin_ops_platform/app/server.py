from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
import json
import os
import re
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from time import monotonic, sleep
from typing import Callable, Iterable
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

from pymongo.errors import PyMongoError

from fin_ops_platform import __version__
from fin_ops_platform.app.auth import (
    ForbiddenOAAccessError,
    OAAuthError,
    OARequestSession,
    UnauthorizedOASessionError,
    extract_oa_token,
    resolve_oa_request_session,
)
from fin_ops_platform.app.routes_tax import TaxApiRoutes
from fin_ops_platform.app.routes_workbench import WorkbenchApiRoutes
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.access_control_service import AccessControlService
from fin_ops_platform.services.app_health_alert_service import AppHealthAlertService
from fin_ops_platform.services.app_health_service import AppHealthService
from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.background_job_service import (
    BackgroundJobAccessError,
    BackgroundJobNotFoundError,
    BackgroundJobService,
)
from fin_ops_platform.services.cost_statistics_read_model_service import CostStatisticsReadModelService
from fin_ops_platform.services.cost_statistics_service import CostStatisticsService
from fin_ops_platform.services.etc_service import (
    EtcBatchNotFoundError,
    EtcDraftRequestError,
    EtcOAClientError,
    EtcInvoiceNotFoundError,
    EtcInvoiceRequestError,
    EtcInvoiceStatus,
    HttpEtcOAClient,
    NotConfiguredEtcOAClient,
    EtcService,
    EtcServiceError,
    UploadedEtcZipFile,
)
from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter, load_mongo_oa_settings
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.oa_identity_service import (
    OAIdentityConfigurationError,
    OAIdentityService,
    OAIdentityServiceError,
    OASessionExpiredError,
)
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncError, OARoleSyncService
from fin_ops_platform.services.oa_sync_service import OASyncService
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.reconciliation import ManualReconciliationService
from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE, SUPPORTED_SCOPES as SEARCH_SUPPORTED_SCOPES, SUPPORTED_STATUSES as SEARCH_SUPPORTED_STATUSES, SearchService
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_BANK_TRANSACTIONS_ACTION,
    RESET_INVOICES_ACTION,
    RESET_OA_AND_REBUILD_ACTION,
    SettingsDataResetService,
)
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService, UploadedCertifiedImportFile
from fin_ops_platform.services.tax_offset_read_model_service import TaxOffsetReadModelService
from fin_ops_platform.services.tax_offset_service import TaxOffsetService
from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService
from fin_ops_platform.services.workbench_action_service import WorkbenchActionService
from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_matching_dirty_scope_service import WorkbenchMatchingDirtyScopeService
from fin_ops_platform.services.workbench_matching_orchestrator import WorkbenchMatchingOrchestrator
from fin_ops_platform.services.workbench_matching_rules import WorkbenchMatchingRules
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService
from fin_ops_platform.services.seeds import build_demo_seed


OA_INVOICE_OFFSET_AUTO_MATCH_MODE = "oa_invoice_offset_auto_match"
OA_INVOICE_OFFSET_TAG = "冲"
WORKBENCH_READ_MODEL_SCHEMA_VERSION = "2026-05-06-oa-expense-multi-invoice-sum"
SYSTEM_AUTO_PAIR_RELATION_MODES = {
    "salary_personal_auto_match",
    "internal_transfer_pair",
    OA_INVOICE_OFFSET_AUTO_MATCH_MODE,
}


@dataclass(slots=True)
class Response:
    status_code: int
    body: str | bytes | Iterable[bytes]
    stream: bool = False
    headers: dict[str, str] = field(
        default_factory=lambda: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        }
    )


@dataclass(slots=True)
class DataResetJob:
    job_id: str
    action: str
    status: str
    phase: str
    message: str
    current: int
    total: int
    percent: int
    created_at: str
    updated_at: str
    result: dict[str, object] | None = None
    error: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "job_id": self.job_id,
            "action": self.action,
            "status": self.status,
            "phase": self.phase,
            "message": self.message,
            "current": self.current,
            "total": self.total,
            "percent": self.percent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.result is not None:
            payload["result"] = self.result
        if self.error:
            payload["error"] = self.error
        return payload


class StatePersistenceError(RuntimeError):
    """Raised when critical workbench state cannot be durably persisted."""


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


ROW_ID_MONTH_RE = re.compile(r"(20\d{2})(\d{2})")


class Application:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self._state_store = ApplicationStateStore(data_dir) if data_dir is not None else None
        self._data_reset_jobs: dict[str, DataResetJob] = {}
        self._data_reset_jobs_lock = Lock()
        persisted_oa_sync_state = self._state_store.load_oa_sync_state() if self._state_store is not None else {}
        self._oa_sync_service = OASyncService()
        persisted_poll_fingerprints = persisted_oa_sync_state.get("poll_fingerprints", {})
        self._oa_sync_poll_fingerprints = (
            dict(persisted_poll_fingerprints)
            if isinstance(persisted_poll_fingerprints, dict)
            else {}
        )
        self._oa_sync_rebuild_lock = Lock()
        self._oa_sync_rebuild_scheduled = False
        self._oa_sync_polling_lock = Lock()
        self._oa_sync_polling_started = False
        self._workbench_matching_dirty_worker_lock = Lock()
        self._workbench_matching_dirty_worker_started = False
        self._workbench_matching_run_lock = Lock()
        self._workbench_matching_running_scope_months: set[str] = set()
        self._seed_payload = build_demo_seed()
        self._initialize_runtime_services(self._load_persisted_state())

    def _load_persisted_state(self) -> dict[str, object]:
        return self._state_store.load() if self._state_store is not None else {}

    def _initialize_runtime_services(self, persisted_state: dict[str, object]) -> None:
        self._import_service = ImportNormalizationService.from_snapshot(
            persisted_state.get("imports"),
            id_registry=self._state_store,
        )
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
        self._workbench_pair_relation_service = WorkbenchPairRelationService.from_snapshot(
            persisted_state.get("workbench_pair_relations"),
        )
        self._workbench_amount_check_service = WorkbenchAmountCheckService()
        self._workbench_read_model_service = WorkbenchReadModelService.from_snapshot(
            persisted_state.get("workbench_read_models"),
        )
        self._workbench_candidate_match_service = WorkbenchCandidateMatchService.from_snapshot(
            persisted_state.get("workbench_candidate_matches"),
        )
        self._workbench_matching_dirty_scope_service = WorkbenchMatchingDirtyScopeService.from_snapshot(
            persisted_state.get("workbench_matching_dirty_scopes"),
        )
        self._cost_statistics_read_model_service = CostStatisticsReadModelService.from_snapshot(
            persisted_state.get("cost_statistics_read_models"),
        )
        self._tax_offset_read_model_service = TaxOffsetReadModelService.from_snapshot(
            persisted_state.get("tax_offset_read_models"),
        )
        mongo_oa_settings = load_mongo_oa_settings(self._state_store.data_dir if self._state_store is not None else None)
        oa_adapter = (
            MongoOAAdapter(settings=mongo_oa_settings, attachment_invoice_cache=self._state_store)
            if mongo_oa_settings is not None
            else None
        )
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
        oa_import_options_provider = (
            oa_adapter.list_oa_import_filter_options
            if isinstance(oa_adapter, MongoOAAdapter)
            else None
        )
        self._app_settings_service = AppSettingsService(
            self._state_store,
            self._project_costing_service,
            oa_role_sync_service=self._oa_role_sync_service,
            oa_import_options_provider=oa_import_options_provider,
        )
        if oa_adapter is not None:
            oa_adapter.set_import_settings_provider(self._app_settings_service.get_oa_import_settings)
        self._oa_identity_service = OAIdentityService()
        self._access_control_service = AccessControlService.from_environment(
            dynamic_allowed_usernames_provider=self._app_settings_service.get_allowed_usernames,
            dynamic_readonly_export_usernames_provider=self._app_settings_service.get_readonly_export_usernames,
            dynamic_admin_usernames_provider=self._app_settings_service.get_admin_usernames,
        )
        bank_account_resolver = BankAccountResolver(self._app_settings_service.get_bank_account_mapping_dict)
        self._candidate_grouping_service = WorkbenchCandidateGroupingService()
        self._workbench_query_service = WorkbenchQueryService(oa_adapter=oa_adapter)
        self._workbench_matching_rules = WorkbenchMatchingRules()
        self._workbench_matching_orchestrator = WorkbenchMatchingOrchestrator(
            row_provider=self._workbench_matching_rows_for_scope,
            pair_relation_service=self._workbench_pair_relation_service,
            candidate_match_service=self._workbench_candidate_match_service,
            read_model_service=self._workbench_read_model_service,
            rules=self._workbench_matching_rules,
            settings_provider=self._workbench_matching_settings,
            source_versions_provider=self._workbench_matching_source_versions,
        )
        self._workbench_action_service = WorkbenchActionService(self._workbench_query_service)
        self._live_workbench_service = LiveWorkbenchService(
            self._import_service,
            self._matching_service,
            bank_account_resolver=bank_account_resolver,
        )
        self._bank_details_service = BankDetailsService(self._import_service)
        self._tax_certified_import_service = TaxCertifiedImportService(state_store=self._state_store)
        self._etc_service = EtcService(state_store=self._state_store)
        self._background_job_service = BackgroundJobService(self._state_store)
        self._app_health_service = AppHealthService()
        self._app_health_alert_service = AppHealthAlertService.from_snapshot(
            self._state_store.load_app_health_alerts() if self._state_store is not None else {}
        )
        self._settings_data_reset_service = (
            SettingsDataResetService(
                state_store=self._state_store,
                import_service=self._import_service,
                file_import_service=self._file_import_service,
                matching_service=self._matching_service,
                workbench_override_service=self._workbench_override_service,
                workbench_pair_relation_service=self._workbench_pair_relation_service,
                workbench_read_model_service=self._workbench_read_model_service,
                tax_certified_import_service=self._tax_certified_import_service,
            )
            if self._state_store is not None
            else None
        )
        self._tax_offset_service = TaxOffsetService(
            import_service=self._import_service,
            certified_records_loader=self._tax_certified_import_service.list_records_for_month,
            oa_attachment_invoice_rows_loader=self._list_tax_offset_oa_attachment_invoice_rows,
        )
        self._cost_statistics_service = CostStatisticsService(
            self._import_service,
            grouped_workbench_loader=self._build_api_workbench_payload,
            row_detail_loader=self._get_api_workbench_row_detail_payload,
            raw_workbench_loader=self._build_raw_workbench_payload,
            project_active_checker=self._app_settings_service.is_project_active,
        )
        self._search_service = SearchService(
            known_months_loader=self._list_search_months,
            grouped_workbench_loader=self._build_api_workbench_payload,
            ignored_rows_loader=self._build_api_workbench_ignored_rows_payload,
        )
        self._workbench_read_model_persist_version = 0
        self._workbench_read_model_persist_version_lock = Lock()
        self._workbench_pair_relation_persist_version = 0
        self._workbench_pair_relation_persist_version_lock = Lock()
        self._workbench_api_routes = WorkbenchApiRoutes(
            self._workbench_query_service,
            self._workbench_action_service,
        )
        if isinstance(oa_adapter, MongoOAAdapter):
            oa_adapter.set_attachment_invoice_cache_updated_callback(self._handle_oa_attachment_invoice_cache_updated)
        self._tax_api_routes = TaxApiRoutes(self._tax_offset_service)

    def _reload_runtime_services(self) -> None:
        self._initialize_runtime_services(self._load_persisted_state())

    def handle_request(
        self,
        method: str,
        path: str,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
    ) -> Response:
        request_started_at = monotonic()
        parsed = urlparse(path)
        route_path = parsed.path
        query = parse_qs(parsed.query)
        timed_action = self._workbench_timed_action_for_route(method=method, route_path=route_path)
        request_id = uuid4().hex[:12] if timed_action is not None else None

        if method == "GET" and route_path == "/health":
            return self._json_response(HTTPStatus.OK, self._health_payload())
        if method == "OPTIONS":
            return Response(status_code=int(HTTPStatus.NO_CONTENT), body="")
        if method == "GET" and route_path == "/foundation/seed":
            return self._json_response(HTTPStatus.OK, self._seed_payload)
        auth_error = self._enforce_route_access(
            route_path,
            headers,
            request_id=request_id,
            action_name=timed_action,
        )
        if auth_error is not None:
            if request_id is not None and timed_action is not None:
                self._emit_workbench_action_timing(
                    request_id=request_id,
                    action_name=timed_action,
                    phase="request_total",
                    duration_ms=self._duration_ms(request_started_at),
                    status="auth_error",
                )
            return auth_error
        if method == "GET" and route_path == "/api/workbench":
            month = query.get("month", [None])[0]
            return self._handle_api_workbench(month)
        if method == "GET" and route_path == "/api/bank-details/accounts":
            return self._handle_api_bank_details_accounts(
                date_from=query.get("date_from", [None])[0],
                date_to=query.get("date_to", [None])[0],
            )
        if method == "GET" and route_path == "/api/bank-details/transactions":
            return self._handle_api_bank_details_transactions(
                account_key=query.get("account_key", [None])[0],
                date_from=query.get("date_from", [None])[0],
                date_to=query.get("date_to", [None])[0],
                page=query.get("page", [None])[0],
                page_size=query.get("page_size", [None])[0],
            )
        if method == "GET" and route_path == "/api/oa-sync/status":
            return self._handle_api_oa_sync_status()
        if method == "GET" and route_path == "/api/app-health/stream":
            return self._handle_api_app_health_stream(headers)
        if method == "GET" and route_path == "/api/app-health":
            return self._handle_api_app_health(headers)
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
        if method == "GET" and route_path == "/api/background-jobs/active":
            return self._handle_api_background_jobs_active(headers)
        if method == "GET" and route_path.startswith("/api/background-jobs/"):
            job_id = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_background_job(job_id, headers)
        if method == "POST" and route_path.startswith("/api/background-jobs/") and route_path.endswith("/acknowledge"):
            job_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_background_job_acknowledge(job_id, headers)
        if method == "POST" and route_path == "/api/etc/import/preview":
            return self._handle_api_etc_import_preview(body, headers)
        if method == "POST" and route_path == "/api/etc/import/confirm":
            return self._handle_api_etc_import_confirm(body, headers)
        if method == "POST" and route_path == "/api/etc/import":
            return self._handle_api_etc_import(body, headers)
        if method == "GET" and route_path == "/api/etc/invoices":
            return self._handle_api_etc_invoices(
                status=query.get("status", [None])[0],
                month=query.get("month", [None])[0],
                plate=query.get("plate", [None])[0],
                keyword=query.get("keyword", [None])[0],
                page=query.get("page", [None])[0],
                page_size=query.get("page_size", [None])[0],
            )
        if method == "POST" and route_path == "/api/etc/invoices/revoke-submitted":
            return self._handle_api_etc_revoke_submitted(body)
        if method == "POST" and route_path == "/api/etc/batches/draft":
            return self._handle_api_etc_batch_draft(body, headers)
        if method == "POST" and route_path.startswith("/api/etc/batches/") and route_path.endswith("/confirm-submitted"):
            batch_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_etc_batch_confirm_submitted(batch_id)
        if method == "POST" and route_path.startswith("/api/etc/batches/") and route_path.endswith("/mark-not-submitted"):
            batch_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_etc_batch_mark_not_submitted(batch_id)
        if method == "GET" and route_path == "/api/session/me":
            return self._handle_api_session_me(headers)
        if method == "GET" and route_path == "/api/workbench/ignored":
            month = query.get("month", [None])[0]
            return self._handle_api_workbench_ignored(month)
        if method == "GET" and route_path == "/api/workbench/settings":
            return self._handle_api_workbench_settings()
        if method == "POST" and route_path == "/api/workbench/settings":
            return self._handle_api_workbench_settings_update(body)
        if method == "POST" and route_path == "/api/workbench/settings/projects/sync":
            return self._handle_api_workbench_settings_projects_sync(body)
        if method == "POST" and route_path == "/api/workbench/settings/projects":
            return self._handle_api_workbench_settings_project_create(body)
        if method == "DELETE" and route_path.startswith("/api/workbench/settings/projects/"):
            project_id = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_workbench_settings_project_delete(project_id)
        if method == "POST" and route_path == "/api/workbench/settings/data-reset/jobs":
            return self._handle_api_workbench_settings_data_reset_job_create(body, headers)
        if method == "GET" and route_path == "/api/workbench/settings/data-reset/jobs/active":
            return self._handle_api_workbench_settings_data_reset_active_job(headers)
        if method == "GET" and route_path.startswith("/api/workbench/settings/data-reset/jobs/"):
            job_id = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_workbench_settings_data_reset_job(job_id, headers)
        if method == "POST" and route_path == "/api/workbench/settings/data-reset":
            return self._handle_api_workbench_settings_data_reset(body, headers)
        if method == "GET" and route_path.startswith("/api/workbench/rows/"):
            row_id = route_path.rsplit("/", 1)[-1]
            return self._handle_api_workbench_row_detail(row_id)
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link":
            response = self._handle_api_workbench_confirm_link(body, request_id=request_id)
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="confirm_link",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link/preview":
            return self._handle_api_workbench_confirm_link_preview(body)
        if method == "POST" and route_path == "/api/workbench/actions/mark-exception":
            return self._handle_api_workbench_mark_exception(body)
        if method == "POST" and route_path == "/api/workbench/actions/cancel-link":
            response = self._handle_api_workbench_cancel_link(body, request_id=request_id)
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="cancel_link",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/withdraw-link/preview":
            return self._handle_api_workbench_withdraw_link_preview(body)
        if method == "POST" and route_path == "/api/workbench/actions/withdraw-link":
            return self._handle_api_workbench_withdraw_link(body, request_id=request_id)
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
            project_scope = query.get("project_scope", [None])[0]
            return self._handle_api_cost_statistics(month, project_scope)
        if method == "GET" and route_path == "/api/cost-statistics/explorer":
            month = query.get("month", [None])[0]
            project_scope = query.get("project_scope", [None])[0]
            return self._handle_api_cost_statistics_explorer(month, project_scope)
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
            project_scope = query.get("project_scope", [None])[0]
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
                project_scope=project_scope,
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
            project_scope = query.get("project_scope", [None])[0]
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
                project_scope=project_scope,
            )
        if method == "GET" and route_path.startswith("/api/cost-statistics/projects/"):
            month = query.get("month", [None])[0]
            project_scope = query.get("project_scope", [None])[0]
            project_name = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_cost_statistics_project(month, project_name, project_scope)
        if method == "GET" and route_path.startswith("/api/cost-statistics/transactions/"):
            transaction_id = route_path.rsplit("/", 1)[-1]
            project_scope = query.get("project_scope", [None])[0]
            return self._handle_api_cost_statistics_transaction(transaction_id, project_scope)
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
            return self._handle_import_file_confirm(body, headers)
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
                "/api/background-jobs/active",
                "/api/background-jobs/{job_id}",
                "/api/background-jobs/{job_id}/acknowledge",
                "/api/etc/import/preview",
                "/api/etc/import/confirm",
                "/api/etc/invoices",
                "/api/etc/invoices/revoke-submitted",
                "/api/etc/batches/draft",
                "/api/etc/batches/{batch_id}/confirm-submitted",
                "/api/etc/batches/{batch_id}/mark-not-submitted",
                "/api/session/me",
                "/api/workbench/ignored",
                "/api/workbench/settings",
                "/api/workbench/settings/data-reset",
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
                "etc_invoice_management",
                "background_job_foundation",
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
                "etc invoice management",
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
        current_month = month or "all"
        return self._json_response(HTTPStatus.OK, self._build_api_workbench_payload(current_month))

    def _handle_api_oa_sync_status(self) -> Response:
        return self._json_response(HTTPStatus.OK, self._oa_sync_service.status_payload())

    def _handle_api_app_health(self, headers: dict[str, str] | None) -> Response:
        started_at = monotonic()
        session, error_response = self._resolve_app_health_session(headers)
        if error_response is not None:
            return error_response
        assert session is not None
        snapshot = self._build_app_health_snapshot(session, started_at=started_at)
        return self._json_response(HTTPStatus.OK, snapshot)

    def _handle_api_app_health_stream(self, headers: dict[str, str] | None) -> Response:
        session, error_response = self._resolve_app_health_session(headers)
        if error_response is not None:
            return error_response
        assert session is not None

        def event_stream() -> Iterable[str]:
            while True:
                started_at = monotonic()
                snapshot = self._build_app_health_snapshot(session, started_at=started_at)
                heartbeat = {"generated_at": snapshot.get("generated_at")}
                yield self._app_health_service.serialize_sse_event("app_health", snapshot)
                yield self._app_health_service.serialize_sse_event("heartbeat", heartbeat)
                sleep(5)

        return Response(
            status_code=int(HTTPStatus.OK),
            body=event_stream(),
            stream=True,
            headers={
                "Content-Type": "text/event-stream; charset=utf-8",
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            },
        )

    def _resolve_app_health_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        try:
            session = resolve_oa_request_session(
                headers,
                identity_service=self._oa_identity_service,
                access_control_service=self._access_control_service,
            )
            if not session.allowed:
                raise ForbiddenOAAccessError("当前 OA 账户未被授权访问财务运营平台。")
        except UnauthorizedOASessionError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。",
                },
            )
        except OASessionExpiredError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "OA 登录状态已过期。",
                },
            )
        except ForbiddenOAAccessError as error:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "forbidden",
                    "message": str(error) or "当前 OA 账户未被授权访问财务运营平台。",
                },
            )
        except OAIdentityConfigurationError as error:
            return None, self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_identity_unavailable",
                    "message": str(error) or "OA 身份服务未配置。",
                },
            )
        except OAIdentityServiceError as error:
            return None, self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_identity_lookup_failed",
                    "message": str(error) or "OA 身份解析失败。",
                },
            )
        return session, None

    def _build_app_health_snapshot(self, session: OARequestSession, *, started_at: float) -> dict[str, object]:
        owner_user_id = session.identity.username or session.identity.user_id or "web_finance_user"
        active_jobs = self._background_job_service.list_active_jobs(owner_user_id, include_system=True)
        oa_sync_payload = self._app_health_oa_sync_payload()
        state_store_info = {
            "storage_mode": self._state_store.storage_mode if self._state_store is not None else "memory",
            "backend": self._state_store.storage_backend if self._state_store is not None else "memory",
        }
        snapshot_without_alerts = self._app_health_service.build_snapshot(
            session=session,
            active_jobs=active_jobs,
            oa_sync_payload=oa_sync_payload,
            state_store_info=state_store_info,
            rebuild_scheduled=self._is_oa_sync_rebuild_scheduled(),
            duration_ms=self._duration_ms(started_at),
            alerts={"active": [], "recent_recovered": []},
        )
        alerts = self._app_health_alert_service.evaluate(snapshot_without_alerts)
        if self._state_store is not None:
            self._state_store.save_app_health_alerts(self._app_health_alert_service.snapshot())
        snapshot = self._app_health_service.build_snapshot(
            session=session,
            active_jobs=active_jobs,
            oa_sync_payload=oa_sync_payload,
            state_store_info=state_store_info,
            rebuild_scheduled=self._is_oa_sync_rebuild_scheduled(),
            duration_ms=self._duration_ms(started_at),
            alerts=alerts,
        )
        self._emit_app_health_timing(snapshot)
        return snapshot

    @staticmethod
    def _emit_app_health_timing(snapshot: dict[str, object]) -> None:
        metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}
        log_payload = {
            "event": "app_health.snapshot",
            "status": snapshot.get("status"),
            "duration_ms": metrics.get("app_health_duration_ms"),
            "dirty_scope_count": metrics.get("dirty_scope_count"),
            "background_jobs_running_count": metrics.get("background_jobs_running_count"),
            "active_alert_count": metrics.get("active_alert_count"),
        }
        print(json.dumps(log_payload, ensure_ascii=False))

    def _app_health_oa_sync_payload(self) -> dict[str, object]:
        payload = self._serialize_value(self._oa_sync_service.status_payload())
        if not isinstance(payload, dict):
            payload = {}
        matching_dirty_scopes = self._workbench_matching_dirty_scope_service.list_dirty_scopes()
        with self._workbench_matching_run_lock:
            matching_running_scopes = sorted(self._workbench_matching_running_scope_months)
        if matching_running_scopes:
            payload["workbench_matching_running_scopes"] = matching_running_scopes
        if not matching_dirty_scopes:
            return payload
        payload["workbench_matching_dirty_scopes"] = matching_dirty_scopes
        raw_dirty_scopes = [
            str(scope).strip()
            for scope in list(payload.get("dirty_scopes") or [])
            if str(scope).strip()
        ]
        matching_scope_months = [
            str(entry.get("scope_month") or "").strip()
            for entry in matching_dirty_scopes
            if str(entry.get("scope_month") or "").strip()
        ]
        payload["dirty_scopes"] = sorted(dict.fromkeys([*raw_dirty_scopes, *matching_scope_months]))
        age_payload = payload.get("dirty_scope_age_seconds")
        dirty_scope_ages = dict(age_payload) if isinstance(age_payload, dict) else {}
        now = datetime.now(UTC)
        for entry in matching_dirty_scopes:
            scope_month = str(entry.get("scope_month") or "").strip()
            if not scope_month:
                continue
            dirty_scope_ages[scope_month] = AppHealthService.seconds_since(entry.get("updated_at"), now)
        payload["dirty_scope_age_seconds"] = dirty_scope_ages
        if not payload.get("message"):
            payload["message"] = "关联台自动配对存在待重算月份。"
        return payload

    def _is_oa_sync_rebuild_scheduled(self) -> bool:
        with self._oa_sync_rebuild_lock:
            return self._oa_sync_rebuild_scheduled

    @staticmethod
    def _is_workbench_read_model_rebuild_job(job: object) -> bool:
        return AppHealthService.is_workbench_read_model_rebuild_job(job)

    def _workbench_write_freshness_guard(self) -> Response | None:
        oa_sync_payload = self._oa_sync_service.status_payload()
        dirty_scopes = [
            str(scope)
            for scope in list(oa_sync_payload.get("dirty_scopes", []) or [])
            if str(scope).strip()
        ]
        if not dirty_scopes and not self._is_oa_sync_rebuild_scheduled():
            return None
        return self._json_response(
            HTTPStatus.CONFLICT,
            {
                "error": "workbench_stale",
                "message": "关联台正在同步，请刷新完成后再操作。",
                "dirty_scopes": dirty_scopes,
            },
        )

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

    def _handle_api_etc_import(self, body: str | bytes | None, headers: dict[str, str] | None) -> Response:
        return self._json_response(
            HTTPStatus.GONE,
            {
                "error": "etc_direct_import_removed",
                "message": "Use /api/etc/import/preview and /api/etc/import/confirm.",
            },
        )

    def _handle_api_background_jobs_active(self, headers: dict[str, str] | None) -> Response:
        owner_user_id = self._resolve_background_job_owner(headers)
        jobs = self._background_job_service.list_active_jobs(owner_user_id, include_system=True)
        return self._json_response(HTTPStatus.OK, {"jobs": [job.to_payload() for job in jobs]})

    def _handle_api_background_job(self, job_id: str, headers: dict[str, str] | None) -> Response:
        owner_user_id = self._resolve_background_job_owner(headers)
        try:
            job = self._background_job_service.get_job(job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "background_job_not_found", "message": "后台任务不存在或不可见。"},
            )
        return self._json_response(HTTPStatus.OK, {"job": job.to_payload()})

    def _handle_api_background_job_acknowledge(self, job_id: str, headers: dict[str, str] | None) -> Response:
        owner_user_id = self._resolve_background_job_owner(headers)
        try:
            job = self._background_job_service.acknowledge_job(job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "background_job_not_found", "message": "后台任务不存在或不可见。"},
            )
        return self._json_response(HTTPStatus.OK, {"job": job.to_payload()})

    def _resolve_background_job_owner(self, headers: dict[str, str] | None) -> str:
        try:
            session = resolve_oa_request_session(
                headers,
                identity_service=self._oa_identity_service,
                access_control_service=self._access_control_service,
            )
        except (OAAuthError, OAIdentityConfigurationError, OAIdentityServiceError, OASessionExpiredError):
            return "web_finance_user"
        return session.identity.username or session.identity.user_id or "web_finance_user"

    def _handle_api_etc_import_preview(self, body: str | bytes | None, headers: dict[str, str] | None) -> Response:
        _fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "At least one zip file is required."},
            )
        invalid_files = [file.file_name for file in files if not file.file_name.lower().endswith(".zip")]
        if invalid_files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "Only .zip files can be imported."},
            )
        uploads = [UploadedEtcZipFile(file_name=file.file_name, content=file.content) for file in files]
        payload = self._etc_service.preview_import_zips(uploads)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_etc_import_confirm(self, body: str | bytes | None, headers: dict[str, str] | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = payload.get("sessionId")
        if not isinstance(session_id, str) or not session_id.strip():
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_import_request", "message": "sessionId is required."},
            )
        normalized_session_id = session_id.strip()
        try:
            total = self._etc_service.get_import_session_item_total(normalized_session_id)
        except EtcServiceError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_import_session_not_found", "message": str(error)})

        owner_user_id = self._resolve_background_job_owner(headers)
        idempotency_key = f"etc_import_session:{normalized_session_id}"
        initial_summary = {
            "created": 0,
            "imported": 0,
            "updated": 0,
            "attachments_completed": 0,
            "duplicates": 0,
            "failed": 0,
            "total": total,
        }
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="etc_invoice_import",
            label="导入 ETC发票",
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
            phase="queued",
            current=0,
            total=total,
            message="ETC发票导入任务已创建。",
            result_summary=initial_summary,
            source={"session_id": normalized_session_id},
            affected_scopes=["etc_invoices"],
            reuse_any_status=True,
        )
        if not created:
            return self._json_response(HTTPStatus.ACCEPTED, {"job": job.to_payload()})

        def run_etc_import(running_job):
            def progress_callback(result) -> None:
                summary = self._etc_import_job_summary(result, total)
                self._background_job_service.update_progress(
                    running_job.job_id,
                    phase="persist_items",
                    message=f"正在导入 ETC发票 {summary['total_current']}/{total}。",
                    current=int(summary["total_current"]),
                    total=total,
                    result_summary={key: value for key, value in summary.items() if key != "total_current"},
                )

            result = self._etc_service.confirm_import_session_with_progress(
                normalized_session_id,
                progress_callback=progress_callback,
            )
            summary = self._etc_import_job_summary(result, total)
            result_summary = {key: value for key, value in summary.items() if key != "total_current"}
            status = "partial_success" if result.failed > 0 else "succeeded"
            message = "ETC发票导入部分完成。" if status == "partial_success" else "ETC发票导入完成。"
            self._background_job_service.succeed_job(
                running_job.job_id,
                message,
                result_summary=result_summary,
                status=status,
            )
            return result_summary

        self._background_job_service.run_job(job, run_etc_import)
        return self._json_response(
            HTTPStatus.ACCEPTED,
            {"job": job.to_payload()},
        )

    @staticmethod
    def _etc_import_job_summary(result, total: int) -> dict[str, int]:
        total_current = result.imported + result.attachments_completed + result.duplicates_skipped + result.failed
        return {
            "created": result.imported,
            "imported": result.imported,
            "updated": result.attachments_completed,
            "attachments_completed": result.attachments_completed,
            "duplicates": result.duplicates_skipped,
            "failed": result.failed,
            "total": total,
            "total_current": total_current,
        }

    def _handle_api_etc_invoices(
        self,
        *,
        status: str | None,
        month: str | None,
        plate: str | None,
        keyword: str | None,
        page: str | None,
        page_size: str | None,
    ) -> Response:
        try:
            resolved_page = int(page) if page not in (None, "") else 1
            resolved_page_size = int(page_size) if page_size not in (None, "") else 50
            invoices, total, counts = self._etc_service.list_invoices(
                status=status or None,
                month=month or None,
                plate=plate or None,
                keyword=keyword or None,
                page=resolved_page,
                page_size=resolved_page_size,
            )
        except (ValueError, EtcInvoiceRequestError) as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_invoice_request", "message": str(error)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "items": [self._serialize_etc_invoice(invoice) for invoice in invoices],
                "counts": counts,
                "page": max(resolved_page, 1),
                "pageSize": min(max(resolved_page_size, 1), 500),
                "total": total,
            },
        )

    @staticmethod
    def _serialize_etc_invoice(invoice: object) -> dict[str, object]:
        payload = Application._serialize_value(invoice)
        if not isinstance(payload, dict):
            return {}
        pdf_path = payload.get("pdf_file_path")
        xml_path = payload.get("xml_file_path")
        payload["has_pdf"] = bool(isinstance(pdf_path, str) and pdf_path and Path(pdf_path).exists())
        payload["has_xml"] = bool(isinstance(xml_path, str) and xml_path and Path(xml_path).exists())
        return payload

    def _handle_api_etc_revoke_submitted(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        invoice_ids = payload.get("invoiceIds")
        if not isinstance(invoice_ids, list) or not all(isinstance(item, str) for item in invoice_ids):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_invoice_request", "message": "invoiceIds must be a string array."},
            )
        try:
            result = self._etc_service.revoke_submitted(invoice_ids)
        except EtcInvoiceNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_invoice_not_found", "message": str(error)})
        except EtcInvoiceRequestError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_invoice_request", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, result)

    def _handle_api_etc_batch_draft(self, body: str | bytes | None, headers: dict[str, str] | None = None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        invoice_ids = payload.get("invoiceIds")
        if not isinstance(invoice_ids, list) or not all(isinstance(item, str) for item in invoice_ids):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": "invoiceIds must be a string array."},
            )
        try:
            result = self._etc_service.create_oa_draft(invoice_ids, oa_client=self._build_etc_oa_client(headers))
        except EtcInvoiceNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_invoice_not_found", "message": str(error)})
        except EtcOAClientError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": str(error)},
            )
        except EtcDraftRequestError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_draft_request", "message": str(error)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "batchId": result.batch_id,
                "etcBatchId": result.etc_batch_id,
                "oaDraftId": result.oa_draft_id,
                "oaDraftUrl": result.oa_draft_url,
            },
        )

    def _build_etc_oa_client(self, headers: dict[str, str] | None) -> HttpEtcOAClient | None:
        if not isinstance(self._etc_service.oa_client, NotConfiguredEtcOAClient):
            return None
        token = extract_oa_token(headers)
        if not token:
            raise EtcOAClientError("OA 登录 token 缺失，请从 OA 内打开本 app 或重新登录 OA 后再创建草稿。")
        return HttpEtcOAClient(token=token)

    def _handle_api_etc_batch_confirm_submitted(self, batch_id: str) -> Response:
        try:
            batch = self._etc_service.confirm_submitted(batch_id)
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        except EtcDraftRequestError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_etc_batch_request", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, {"batch": batch})

    def _handle_api_etc_batch_mark_not_submitted(self, batch_id: str) -> Response:
        try:
            batch = self._etc_service.mark_not_submitted(batch_id)
        except EtcBatchNotFoundError as error:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "etc_batch_not_found", "message": str(error)})
        return self._json_response(HTTPStatus.OK, {"batch": batch})

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
        if route_path.startswith("/api/workbench/settings/data-reset/jobs/"):
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

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return round((monotonic() - started_at) * 1000, 3)

    @staticmethod
    def _safe_list_count(value: object) -> int:
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _workbench_timed_action_for_route(*, method: str, route_path: str) -> str | None:
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link":
            return "confirm_link"
        if method == "POST" and route_path == "/api/workbench/actions/cancel-link":
            return "cancel_link"
        return None

    def _emit_workbench_action_timing(
        self,
        *,
        request_id: str,
        action_name: str,
        phase: str,
        duration_ms: float,
        status: str | int | None = None,
        detail: str | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "kind": "workbench_action_timing",
            "request_id": request_id,
            "action": action_name,
            "phase": phase,
            "duration_ms": round(float(duration_ms), 3),
            "timestamp": datetime.now().isoformat(),
        }
        if status is not None:
            payload["status"] = status
        if detail is not None and detail.strip():
            payload["detail"] = detail.strip()
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    def _emit_workbench_persistence_warning(self, *, operation: str, detail: str) -> None:
        print(
            json.dumps(
                {
                    "kind": "workbench_persistence_warning",
                    "operation": operation,
                    "detail": detail,
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def _persist_workbench_read_models_best_effort(
        self,
        *,
        snapshot: dict[str, object],
        changed_scope_keys: list[str] | None = None,
        operation: str,
    ) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save_workbench_read_models(
                snapshot,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            self._emit_workbench_persistence_warning(operation=operation, detail=str(exc))

    def _persist_cost_statistics_read_models_best_effort(
        self,
        *,
        snapshot: dict[str, object],
        changed_scope_keys: list[str] | None = None,
        operation: str,
    ) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save_cost_statistics_read_models(
                snapshot,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "kind": "cost_statistics_persistence_warning",
                        "operation": operation,
                        "detail": str(exc),
                        "timestamp": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    def _persist_tax_offset_read_models_best_effort(
        self,
        *,
        snapshot: dict[str, object],
        changed_scope_keys: list[str] | None = None,
        operation: str,
    ) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save_tax_offset_read_models(
                snapshot,
                changed_scope_keys=changed_scope_keys,
            )
        except Exception as exc:
            print(
                json.dumps(
                    {
                        "kind": "tax_offset_persistence_warning",
                        "operation": operation,
                        "detail": str(exc),
                        "timestamp": datetime.now().isoformat(),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

    def _persist_workbench_override_change(
        self,
        *,
        changed_row_ids: list[str],
        mutation: Callable[[], object],
        changed_scope_keys: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> object:
        previous_snapshot = self._workbench_override_service.snapshot()
        result = mutation()
        try:
            if changed_scope_keys is None:
                self._persist_workbench_overrides(changed_row_ids=changed_row_ids)
            else:
                self._save_workbench_overrides_snapshot(changed_row_ids=changed_row_ids)
        except Exception as exc:
            self._workbench_override_service = WorkbenchOverrideService.from_snapshot(previous_snapshot)
            raise StatePersistenceError("工作台状态暂时无法保存，请稍后重试。") from exc
        if changed_scope_keys is not None:
            self._invalidate_workbench_read_model_scopes(changed_scope_keys)
            self._schedule_workbench_read_model_persist(
                changed_scope_keys=changed_scope_keys,
                request_id=request_id,
                action_name=action_name,
            )
        return result

    def _workbench_persistence_unavailable_response(self, exc: StatePersistenceError) -> Response:
        return self._json_response(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "workbench_state_persistence_unavailable",
                "message": str(exc),
            },
        )

    def _handle_oa_attachment_invoice_cache_updated(self, months: list[str]) -> None:
        scope_keys = {
            str(month).strip()
            for month in list(months or [])
            if str(month).strip()
        }
        if not scope_keys:
            return
        scope_keys.add("all")
        normalized_scope_keys = sorted(scope_keys)
        self._handle_oa_source_changed(normalized_scope_keys, reason="oa_attachment_invoice_cache")
        self._invalidate_tax_offset_read_model_scopes(
            [scope_key for scope_key in normalized_scope_keys if SEARCH_MONTH_RE.match(scope_key)],
            reason="oa_attachment_invoice_cache",
        )

    def _handle_oa_source_changed(
        self,
        scope_keys: list[str],
        *,
        reason: str = "oa_changed",
        schedule_rebuild: bool = True,
    ) -> None:
        normalized_scope_keys = self._normalize_oa_sync_scope_keys(scope_keys)
        if not normalized_scope_keys:
            return
        self._oa_sync_service.mark_changed(normalized_scope_keys, reason=reason)
        if schedule_rebuild:
            self._schedule_oa_sync_dirty_scope_rebuild()

    def start_oa_sync_polling_worker(self, *, interval_seconds: float | None = None) -> bool:
        adapter = self._workbench_query_service._oa_adapter
        poll_sync_fingerprints = getattr(adapter, "poll_sync_fingerprints", None)
        if not callable(poll_sync_fingerprints):
            return False
        with self._oa_sync_polling_lock:
            if self._oa_sync_polling_started:
                return True
            self._oa_sync_polling_started = True
        resolved_interval = interval_seconds
        if resolved_interval is None:
            try:
                resolved_interval = float(os.getenv("FIN_OPS_OA_POLL_INTERVAL_SECONDS", "5"))
            except ValueError:
                resolved_interval = 5
        Thread(
            target=self._run_oa_sync_polling_worker,
            kwargs={"interval_seconds": max(2.0, float(resolved_interval))},
            daemon=True,
        ).start()
        return True

    def start_workbench_matching_dirty_scope_worker(self, *, interval_seconds: float | None = None) -> bool:
        resolved_interval = interval_seconds
        if resolved_interval is None:
            try:
                resolved_interval = float(os.getenv("FIN_OPS_WORKBENCH_MATCHING_DIRTY_INTERVAL_SECONDS", "900"))
            except ValueError:
                resolved_interval = 900
        if float(resolved_interval) <= 0:
            return False
        with self._workbench_matching_dirty_worker_lock:
            if self._workbench_matching_dirty_worker_started:
                return True
            self._workbench_matching_dirty_worker_started = True
        Thread(
            target=self._run_workbench_matching_dirty_scope_worker,
            kwargs={"interval_seconds": max(60.0, float(resolved_interval))},
            daemon=True,
        ).start()
        return True

    def _run_workbench_matching_dirty_scope_worker(self, *, interval_seconds: float) -> None:
        while True:
            self._rebuild_workbench_matching_dirty_scopes_once()
            sleep(interval_seconds)

    def _rebuild_workbench_matching_dirty_scopes_once(self) -> dict[str, object] | None:
        scope_months = self._workbench_matching_dirty_scope_service.take_dirty_scopes()
        if not scope_months:
            return None
        return self._run_workbench_auto_matching_for_scopes(
            scope_months,
            reason="dirty_scope_retry",
        )

    def _run_oa_sync_polling_worker(self, *, interval_seconds: float) -> None:
        while True:
            self._poll_oa_source_once()
            sleep(interval_seconds)

    def _poll_oa_source_once(self) -> list[str]:
        adapter = self._workbench_query_service._oa_adapter
        poll_sync_fingerprints = getattr(adapter, "poll_sync_fingerprints", None)
        if not callable(poll_sync_fingerprints):
            return []
        try:
            current_fingerprints = poll_sync_fingerprints()
        except Exception as exc:
            self._oa_sync_service.mark_error(f"OA 轮询失败：{exc}")
            return []
        if not isinstance(current_fingerprints, dict):
            self._oa_sync_service.mark_error("OA 轮询失败：返回值无效")
            return []

        normalized_current = {
            str(scope_key).strip(): str(fingerprint)
            for scope_key, fingerprint in current_fingerprints.items()
            if str(scope_key).strip() and str(fingerprint)
        }
        previous_fingerprints = {
            str(scope_key).strip(): str(fingerprint)
            for scope_key, fingerprint in self._oa_sync_poll_fingerprints.items()
            if str(scope_key).strip() and str(fingerprint)
        }
        is_initial_snapshot = not previous_fingerprints
        changed_scopes = [] if is_initial_snapshot else sorted(
            scope_key
            for scope_key in set(normalized_current).union(previous_fingerprints)
            if normalized_current.get(scope_key) != previous_fingerprints.get(scope_key)
        )
        changed_scopes = self._filter_oa_poll_changed_scopes_for_retention(changed_scopes)
        self._oa_sync_poll_fingerprints = dict(normalized_current)
        if self._state_store is not None:
            self._state_store.save_oa_sync_state(
                {
                    "poll_fingerprints": dict(normalized_current),
                    "last_polled_at": datetime.now().isoformat(),
                }
            )
        if changed_scopes:
            self._handle_oa_source_changed(changed_scopes, reason="oa_polling")
        return changed_scopes

    def _filter_oa_poll_changed_scopes_for_retention(self, changed_scopes: list[str]) -> list[str]:
        normalized_scopes = {
            str(scope).strip()
            for scope in list(changed_scopes or [])
            if str(scope).strip()
        }
        if not normalized_scopes:
            return []
        cutoff_date = self._parse_oa_retention_date(self._app_settings_service.get_oa_retention_cutoff_date())
        if cutoff_date is None:
            return sorted(normalized_scopes)
        cutoff_month = cutoff_date.strftime("%Y-%m")
        retained_months = {
            scope
            for scope in normalized_scopes
            if SEARCH_MONTH_RE.match(scope) and scope >= cutoff_month
        }
        if retained_months:
            return sorted({*retained_months, "all"})
        if any(scope != "all" and SEARCH_MONTH_RE.match(scope) for scope in normalized_scopes):
            return []
        return sorted(normalized_scopes)

    def _schedule_oa_sync_dirty_scope_rebuild(self) -> None:
        with self._oa_sync_rebuild_lock:
            if self._oa_sync_rebuild_scheduled:
                return
            self._oa_sync_rebuild_scheduled = True
        Thread(target=self._run_scheduled_oa_sync_dirty_scope_rebuild, daemon=True).start()

    def _run_scheduled_oa_sync_dirty_scope_rebuild(self) -> None:
        try:
            self._rebuild_oa_sync_dirty_scopes_once()
        finally:
            with self._oa_sync_rebuild_lock:
                self._oa_sync_rebuild_scheduled = False
            if self._oa_sync_service.status_payload().get("dirty_scopes"):
                self._schedule_oa_sync_dirty_scope_rebuild()

    def _rebuild_oa_sync_dirty_scopes_once(self) -> None:
        scope_keys = self._oa_sync_service.take_dirty_scopes()
        if not scope_keys:
            return
        try:
            self._hot_rebuild_workbench_read_model_scopes(scope_keys)
        except Exception as exc:
            self._oa_sync_service.mark_error(f"OA 同步刷新失败：{exc}", scopes=scope_keys)
            return
        self._oa_sync_service.mark_synced(scope_keys)

    def _hot_rebuild_workbench_read_model_scopes(self, scope_keys: list[str]) -> None:
        normalized_scope_keys = self._normalize_oa_sync_scope_keys(scope_keys)
        if not normalized_scope_keys:
            return
        read_model_scope_keys = self._expand_workbench_read_model_scope_keys_for_base_scopes(normalized_scope_keys)
        self._run_workbench_auto_matching_for_scopes(
            normalized_scope_keys,
            reason="oa_sync_hot_rebuild",
        )
        self._search_service.clear_cache()
        invalidate_records_cache = getattr(self._workbench_query_service._oa_adapter, "invalidate_records_cache", None)
        if callable(invalidate_records_cache):
            invalidate_records_cache([scope_key for scope_key in normalized_scope_keys if scope_key != "all"])
        for scope_key in read_model_scope_keys:
            base_scope_key = self._workbench_read_model_base_scope_key(scope_key)
            raw_payload = self._build_raw_workbench_payload(base_scope_key)
            candidate_payload = self._apply_candidate_matches_to_payload(raw_payload, base_scope_key)
            grouped_payload = self._group_row_payload(candidate_payload)
            self._apply_workbench_runtime_metadata(grouped_payload)
            ignored_rows = self._extract_ignored_rows(candidate_payload)
            if not self._can_persist_workbench_payload(grouped_payload):
                raise RuntimeError(str(grouped_payload.get("oa_status", {}).get("message") or "OA read model is not ready"))
            self._workbench_read_model_service.upsert_read_model(
                scope_key=scope_key,
                payload=grouped_payload,
                ignored_rows=ignored_rows,
            )
        if self._state_store is not None:
            self._persist_workbench_read_models_best_effort(
                snapshot=self._workbench_read_model_service.snapshot_scope_keys(read_model_scope_keys),
                changed_scope_keys=read_model_scope_keys,
                operation="oa_sync_hot_rebuild_read_models",
            )
        self._invalidate_cost_statistics_read_model_scopes(
            normalized_scope_keys,
            reason="oa_sync_hot_rebuild",
        )

    def _expand_workbench_read_model_scope_keys_for_base_scopes(self, base_scope_keys: list[str]) -> list[str]:
        normalized_base_scope_keys = {
            self._workbench_read_model_base_scope_key(scope_key)
            for scope_key in list(base_scope_keys or [])
            if str(scope_key).strip()
        }
        expanded = set(normalized_base_scope_keys)
        for scope_key in self._workbench_read_model_service.list_scope_keys():
            base_scope_key = self._workbench_read_model_base_scope_key(scope_key)
            if base_scope_key in normalized_base_scope_keys:
                expanded.add(scope_key)
        return sorted(expanded)

    @staticmethod
    def _normalize_oa_sync_scope_keys(scope_keys: list[str]) -> list[str]:
        normalized = {
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        }
        if any(scope_key != "all" for scope_key in normalized):
            normalized.add("all")
        return sorted(normalized)

    def _enforce_route_access(
        self,
        route_path: str,
        headers: dict[str, str] | None,
        *,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> Response | None:
        if not self._route_requires_oa_access(route_path):
            return None
        auth_started_at = monotonic()
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
        finally:
            if request_id is not None and action_name is not None:
                self._emit_workbench_action_timing(
                    request_id=request_id,
                    action_name=action_name,
                    phase="oa_auth",
                    duration_ms=self._duration_ms(auth_started_at),
                )
        return None

    def _handle_api_workbench_ignored(self, month: str | None) -> Response:
        current_month = month or "all"
        return self._json_response(
            HTTPStatus.OK,
            {
                "month": current_month,
                "rows": self._build_api_workbench_ignored_rows_payload(current_month),
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
        workbench_column_layouts = payload.get("workbench_column_layouts", {})
        oa_retention = payload.get("oa_retention", {})
        oa_invoice_offset = payload.get("oa_invoice_offset", {})
        oa_import = payload.get("oa_import", {})
        if (
            not isinstance(completed_project_ids, list)
            or not isinstance(bank_account_mappings, list)
            or not isinstance(allowed_usernames, list)
            or not isinstance(readonly_export_usernames, list)
            or not isinstance(admin_usernames, list)
            or not isinstance(workbench_column_layouts, dict)
            or not isinstance(oa_retention, dict)
            or not isinstance(oa_import, dict)
            or not isinstance(oa_invoice_offset, dict)
        ):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_request",
                    "message": (
                        "completed_project_ids, bank_account_mappings, allowed_usernames, "
                        "readonly_export_usernames, and admin_usernames must be arrays, "
                        "and workbench_column_layouts, oa_retention, oa_import, and oa_invoice_offset must be objects."
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
                workbench_column_layouts=workbench_column_layouts,
                oa_retention=oa_retention,
                oa_import=oa_import,
                oa_invoice_offset=oa_invoice_offset,
            )
        except OARoleSyncError as exc:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_role_sync_failed",
                    "message": f"OA 角色同步失败：{exc}",
                },
            )
        except PyMongoError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "app_settings_persistence_failed",
                    "message": f"设置保存失败：无法写入 app Mongo，请检查 139.155.5.132:27017 连接后重试。底层错误：{exc}",
                },
            )
        self._invalidate_workbench_read_models()
        if self._state_store is not None:
            self._persist_workbench_read_models_best_effort(
                snapshot=self._workbench_read_model_service.snapshot(),
                operation="invalidate_read_models_after_settings_update",
            )
        self._search_service.clear_cache()
        return self._json_response(HTTPStatus.OK, updated_payload)

    def _handle_api_workbench_settings_projects_sync(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = str(payload.get("actor_id", "")).strip()
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_sync_request", "message": "actor_id is required."},
            )
        try:
            run = self._project_costing_service.sync_projects_from_oa(actor_id=actor_id)
        except Exception as exc:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_project_sync_failed",
                    "message": f"OA 项目同步失败：{exc}",
                },
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "sync": self._serialize_sync_run(run),
                "settings": self._app_settings_service.get_settings_payload(),
            },
        )

    def _handle_api_workbench_settings_project_create(self, body: str | bytes | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        actor_id = str(payload.get("actor_id", "")).strip()
        if not actor_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": "actor_id is required."},
            )
        try:
            settings_payload = self._app_settings_service.create_manual_project(
                actor_id=actor_id,
                project_code=str(payload.get("project_code", "")),
                project_name=str(payload.get("project_name", "")),
                department_name=payload.get("department_name"),
                owner_name=payload.get("owner_name"),
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_create_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"settings": settings_payload})

    def _handle_api_workbench_settings_project_delete(self, project_id: str) -> Response:
        normalized_project_id = str(project_id).strip()
        if not normalized_project_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_project_delete_request", "message": "project_id is required."},
            )
        settings_payload = self._app_settings_service.delete_project(normalized_project_id)
        return self._json_response(HTTPStatus.OK, {"settings": settings_payload})

    def _handle_api_workbench_settings_data_reset(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        payload, error = self._validate_settings_data_reset_request(body, headers)
        if error is not None:
            return error
        action = str(payload.get("action") or "").strip()
        try:
            result = self._execute_settings_data_reset(action)
        except ValueError:
            return self._unsupported_settings_data_reset_response()
        return self._json_response(HTTPStatus.OK, result)

    def _handle_api_workbench_settings_data_reset_job_create(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        payload, error = self._validate_settings_data_reset_request(body, headers)
        if error is not None:
            return error
        action = str(payload.get("action") or "").strip()
        if action not in self._settings_data_reset_service.supported_actions():
            return self._unsupported_settings_data_reset_response()

        owner_user_id = self._resolve_background_job_owner(headers)
        active_job = self._active_data_reset_background_job(owner_user_id)
        if active_job is not None:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "settings_data_reset_job_running",
                    "message": "已有数据重置任务正在执行，请等待当前任务完成。",
                    "job": self._serialize_data_reset_background_job(active_job),
                },
            )

        job = self._background_job_service.create_job(
            job_type="settings_data_reset",
            label=self._data_reset_job_label(action),
            owner_user_id=owner_user_id,
            visibility="system",
            phase="queued",
            current=1,
            total=100,
            message="数据重置任务已排队。",
            result_summary={"action": action},
            source={"action": action},
            affected_scopes=["settings", "workbench"],
        )
        self._background_job_service.run_job(job, lambda running_job: self._run_settings_data_reset_background_job(running_job, action))
        return self._json_response(HTTPStatus.ACCEPTED, {"job": self._serialize_data_reset_background_job(job)})

    def _run_settings_data_reset_background_job(self, running_job, action: str) -> dict[str, object]:
        def update(phase: str, message: str, percent: int) -> None:
            self._background_job_service.update_progress(
                running_job.job_id,
                phase=phase,
                message=message,
                current=max(0, min(int(percent), 100)),
                total=100,
                result_summary={"action": action},
            )

        update("start", "数据重置任务已开始。", 1)
        result = self._execute_settings_data_reset(action, progress=update)
        failed = str(result.get("status") or "") == "partial" or str(result.get("rebuild_status") or "") == "failed"
        self._background_job_service.update_progress(
            running_job.job_id,
            phase="failed" if failed else "complete",
            message=str(result.get("message") or ("数据重置失败。" if failed else "数据重置已完成。")),
            current=100,
            total=100,
            result_summary=result,
        )
        if failed:
            self._background_job_service.fail_job(
                running_job.job_id,
                str(result.get("message") or "数据重置失败。"),
                str(result.get("message") or "数据重置失败。"),
            )
        else:
            self._background_job_service.succeed_job(
                running_job.job_id,
                str(result.get("message") or "数据重置已完成。"),
                result_summary=result,
            )
        return result

    def _handle_api_workbench_settings_data_reset_job(
        self,
        job_id: str,
        headers: dict[str, str] | None,
    ) -> Response:
        normalized_job_id = str(job_id or "").strip()
        owner_user_id = self._resolve_background_job_owner(headers)
        try:
            job = self._background_job_service.get_job(normalized_job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "settings_data_reset_job_not_found", "message": "数据重置任务不存在或已过期。"},
            )
        if job.type != "settings_data_reset":
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "settings_data_reset_job_not_found", "message": "数据重置任务不存在或已过期。"},
            )
        return self._json_response(HTTPStatus.OK, {"job": self._serialize_data_reset_background_job(job)})

    def _handle_api_workbench_settings_data_reset_active_job(
        self,
        headers: dict[str, str] | None,
    ) -> Response:
        owner_user_id = self._resolve_background_job_owner(headers)
        active_job = self._active_data_reset_background_job(owner_user_id)
        return self._json_response(
            HTTPStatus.OK,
            {"job": self._serialize_data_reset_background_job(active_job) if active_job is not None else None},
        )

    def _validate_settings_data_reset_request(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> tuple[dict[str, object], Response | None]:
        if self._settings_data_reset_service is None:
            return {}, self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "settings_data_reset_unavailable",
                    "message": "当前运行模式未启用持久化状态存储，不能执行数据重置。",
                },
            )
        admin_session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return {}, admin_error
        payload, error = self._load_json_body(body)
        if error is not None:
            return {}, error
        action = str(payload.get("action") or "").strip()
        if not action:
            return {}, self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_workbench_settings_reset_request",
                    "message": "action is required.",
                },
            )
        oa_password = payload.get("oa_password")
        if not isinstance(oa_password, str) or not oa_password:
            return {}, self._oa_password_verification_failed_response()
        password_error = self._verify_reset_oa_password(admin_session, oa_password)
        if password_error is not None:
            return {}, password_error
        return dict(payload), None

    def _unsupported_settings_data_reset_response(self) -> Response:
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {
                "error": "invalid_workbench_settings_reset_request",
                "message": "unsupported action.",
                "supported_actions": self._settings_data_reset_service.supported_actions(),
                "protected_targets": self._settings_data_reset_service.protected_targets(),
            },
        )

    def _execute_settings_data_reset(
        self,
        action: str,
        progress: Callable[[str, str, int], None] | None = None,
    ) -> dict[str, object]:
        if progress is not None:
            progress("clear", "正在清理 app 内部状态。", 5)
        service_progress_end = 15 if action == RESET_OA_AND_REBUILD_ACTION else 80

        def service_progress(phase: str, message: str, current: int, total: int) -> None:
            if progress is None:
                return
            safe_total = max(int(total), 1)
            safe_current = max(0, min(int(current), safe_total))
            percent = 5 + round((safe_current / safe_total) * (service_progress_end - 5))
            progress(phase, message, percent)

        try:
            result = self._settings_data_reset_service.execute(action, progress_callback=service_progress)
        except ValueError:
            raise
        if progress is not None:
            reload_percent = 15 if action == RESET_OA_AND_REBUILD_ACTION else 90
            progress("reload", "正在重新载入运行时服务。", reload_percent)
        self._reload_runtime_services()
        if action == RESET_OA_AND_REBUILD_ACTION:
            self._workbench_matching_dirty_scope_service = WorkbenchMatchingDirtyScopeService()
        self._search_service.clear_cache()
        self._invalidate_tax_offset_read_models()
        if action == RESET_OA_AND_REBUILD_ACTION:
            try:
                if progress is not None:
                    progress("rebuild", "正在按 OA 导入设置重新拉取 OA 并重建关联台缓存。", 95)
                self._run_workbench_auto_matching_for_scopes(
                    self._expand_workbench_matching_months(self._workbench_query_service.list_available_months()),
                    reason="oa_reset_rebuild",
                )
                self._build_api_workbench_payload("all")
                result.rebuild_status = "completed"
                result.message = "已按 OA 导入设置重新拉取 OA 并重建关联台，已保留 OA 附件发票解析结果。"
            except Exception as exc:
                result.status = "partial"
                result.rebuild_status = "failed"
                result.message = f"已清空 OA 工作台人工状态并保留 OA 附件发票解析结果，但 OA 重建失败：{exc}"
        if progress is not None:
            progress("complete", "数据重置已完成。", 100)
        return result.to_payload()

    def _active_data_reset_job(self) -> DataResetJob | None:
        with self._data_reset_jobs_lock:
            for job in self._data_reset_jobs.values():
                if job.status in {"queued", "running"}:
                    return job
        return None

    def _active_data_reset_background_job(self, owner_user_id: str):
        for job in self._background_job_service.list_active_jobs(owner_user_id, include_system=True):
            if job.type == "settings_data_reset" and job.status in {"queued", "running"}:
                return job
        return None

    @staticmethod
    def _data_reset_job_label(action: str) -> str:
        if action == RESET_BANK_TRANSACTIONS_ACTION:
            return "重置银行流水"
        if action == RESET_INVOICES_ACTION:
            return "重置发票数据"
        if action == RESET_OA_AND_REBUILD_ACTION:
            return "重置OA数据"
        return "数据重置"

    @staticmethod
    def _serialize_data_reset_background_job(job) -> dict[str, object]:
        result = dict(job.result_summary) if isinstance(job.result_summary, dict) else {}
        action = str(job.source.get("action") or result.get("action") or "")
        status = str(job.status)
        legacy_status = {
            "succeeded": "completed",
            "partial_success": "failed",
            "cancelled": "cancelled",
            "acknowledged": "completed",
        }.get(status, status)
        payload: dict[str, object] = {
            "job_id": job.job_id,
            "action": action,
            "status": legacy_status,
            "phase": job.phase,
            "message": job.message,
            "current": job.current,
            "total": job.total,
            "percent": job.percent,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
        }
        if job.error:
            payload["error"] = job.error
        if result and ("cleared_collections" in result or "deleted_counts" in result or legacy_status == "completed"):
            result.setdefault("action", action)
            result.setdefault("status", legacy_status)
            result.setdefault("job_id", job.job_id)
            payload["result"] = result
        return payload

    def _run_settings_data_reset_job(self, job_id: str) -> None:
        def update(phase: str, message: str, percent: int) -> None:
            self._update_data_reset_job(
                job_id,
                status="running",
                phase=phase,
                message=message,
                current=max(0, min(int(percent), 100)),
                total=100,
                percent=max(0, min(int(percent), 100)),
            )

        with self._data_reset_jobs_lock:
            job = self._data_reset_jobs.get(job_id)
            action = job.action if job is not None else ""
        if not action:
            return
        update("start", "数据重置任务已开始。", 1)
        try:
            result = self._execute_settings_data_reset(action, progress=update)
        except Exception as exc:
            self._update_data_reset_job(
                job_id,
                status="failed",
                phase="failed",
                message="数据重置失败。",
                current=100,
                total=100,
                percent=100,
                error=str(exc),
            )
            return

        failed = str(result.get("status") or "") == "partial" or str(result.get("rebuild_status") or "") == "failed"
        self._update_data_reset_job(
            job_id,
            status="failed" if failed else "completed",
            phase="failed" if failed else "complete",
            message=str(result.get("message") or ("数据重置失败。" if failed else "数据重置已完成。")),
            current=100,
            total=100,
            percent=100,
            result=result,
            error=str(result.get("message") or "") if failed else None,
        )

    def _update_data_reset_job(
        self,
        job_id: str,
        *,
        status: str,
        phase: str,
        message: str,
        current: int,
        total: int,
        percent: int,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        with self._data_reset_jobs_lock:
            job = self._data_reset_jobs.get(job_id)
            if job is None:
                return
            job.status = status
            job.phase = phase
            job.message = message
            job.current = current
            job.total = total
            job.percent = percent
            job.updated_at = datetime.now().isoformat()
            if result is not None:
                job.result = result
            if error is not None:
                job.error = error

    def _parse_oa_attachment_invoices_for_reset_rebuild(
        self,
        *,
        progress: Callable[[str, str, int], None] | None = None,
    ) -> None:
        adapter = self._workbench_query_service._oa_adapter
        parse_attachment_invoices_for_months = getattr(adapter, "parse_attachment_invoices_for_months", None)
        if not callable(parse_attachment_invoices_for_months):
            return
        cutoff_date = self._parse_oa_retention_date(self._app_settings_service.get_oa_retention_cutoff_date())
        if cutoff_date is None:
            months = self._workbench_query_service.list_available_months()
        else:
            months = self._retained_oa_months_for_all_scope(cutoff_date)
        if not months:
            return
        total_months = len(months)
        for index, month in enumerate(months, start=1):
            if progress is not None:
                percent = 20 + int(((index - 1) / total_months) * 70)
                progress("parse_oa_attachments", f"正在解析 OA 附件发票（{index}/{total_months}）：{month}", percent)
            parse_attachment_invoices_for_months([month])
        if progress is not None:
            progress("parse_oa_attachments", f"OA 附件发票解析完成（{total_months}/{total_months}）。", 90)

    def _handle_api_workbench_row_detail(self, row_id: str) -> Response:
        try:
            payload = self._get_api_workbench_row_detail_payload(row_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "row_id": row_id},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _enforce_admin_access(self, headers: dict[str, str] | None) -> Response | None:
        _, error = self._resolve_admin_session(headers)
        return error

    def _resolve_admin_session(
        self, headers: dict[str, str] | None
    ) -> tuple[OARequestSession | None, Response | None]:
        try:
            session = resolve_oa_request_session(
                headers,
                identity_service=self._oa_identity_service,
                access_control_service=self._access_control_service,
            )
            if not session.can_admin_access:
                return None, self._json_response(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "admin_only",
                        "message": "当前账号没有管理员权限，不能执行数据重置。",
                    },
                )
        except UnauthorizedOASessionError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。",
                },
            )
        except OASessionExpiredError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": str(error) or "OA 登录状态已过期。",
                },
            )
        except ForbiddenOAAccessError as error:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "forbidden",
                    "message": str(error) or "当前 OA 账户未被授权访问财务运营平台。",
                },
            )
        except OAIdentityConfigurationError as error:
            return None, self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_identity_unavailable",
                    "message": str(error) or "OA 身份服务未配置。",
                },
            )
        except OAIdentityServiceError as error:
            return None, self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_identity_lookup_failed",
                    "message": str(error) or "OA 身份解析失败。",
                },
            )
        return session, None

    def _verify_reset_oa_password(self, session: OARequestSession | None, oa_password: str) -> Response | None:
        if session is None:
            return self._oa_password_verification_failed_response()
        if session.token == "local-dev-token" and os.getenv("FIN_OPS_DEV_ALLOW_LOCAL_SESSION", "").strip() == "1":
            expected_password = os.getenv("FIN_OPS_DEV_OA_PASSWORD", "local-dev-password")
            if oa_password == expected_password:
                return None
            return self._oa_password_verification_failed_response()
        try:
            if self._oa_identity_service.verify_current_user_password(session.token, oa_password):
                return None
        except OASessionExpiredError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {
                    "error": "invalid_oa_session",
                    "message": "OA 登录状态已过期。",
                },
            )
        except OAIdentityConfigurationError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "oa_password_verification_unavailable",
                    "message": "OA 用户密码复核服务未配置。",
                },
            )
        except OAIdentityServiceError as error:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {
                    "error": "oa_password_verification_unavailable",
                    "message": "OA 用户密码复核服务暂时不可用，请稍后重试。",
                },
            )
        return self._oa_password_verification_failed_response()

    def _oa_password_verification_failed_response(self) -> Response:
        return self._json_response(
            HTTPStatus.FORBIDDEN,
            {
                "error": "oa_password_verification_failed",
                "message": "当前 OA 用户密码复核失败，未执行数据重置。",
            },
        )

    def _get_api_workbench_row_detail_payload(self, row_id: str) -> dict[str, object]:
        try:
            payload = {"row": self._live_workbench_service.get_row_detail(row_id)}
        except KeyError:
            month_hint = self._row_month_scope_from_row_id(row_id)
            cached_rows = self._resolve_rows_from_cached_read_models(
                [row_id],
                month_hint=month_hint,
            )
            if row_id in cached_rows:
                payload = {"row": cached_rows[row_id]}
            elif month_hint is None and self._workbench_query_service._looks_like_oa_row_id(row_id):
                raise KeyError(row_id)
            else:
                payload = self._workbench_api_routes.get_row_detail(row_id)
        payload["row"] = self._workbench_override_service.apply_to_row(payload["row"])
        return payload

    def _handle_api_cost_statistics(self, month: str | None, project_scope: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        try:
            payload = self._cost_statistics_service.get_month_statistics(
                current_month,
                project_scope=project_scope or "active",
            )
        except ValueError as error:
            return self._cost_statistics_project_scope_error_response(error)
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_explorer(self, month: str | None, project_scope: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        normalized_project_scope = str(project_scope or "active").strip().lower()
        started_at = monotonic()
        cache_hit = False
        try:
            if normalized_project_scope not in {"active", "all"}:
                raise ValueError("project_scope must be active or all")
            payload, cache_hit = self._get_or_build_cost_statistics_explorer(
                current_month,
                normalized_project_scope,
            )
        except ValueError as error:
            return self._cost_statistics_project_scope_error_response(error)
        self._emit_cost_statistics_explorer_metric(
            month=current_month,
            project_scope=normalized_project_scope,
            cache_hit=cache_hit,
            duration_ms=self._duration_ms(started_at),
            entry_count=self._cost_statistics_explorer_entry_count(payload),
        )
        return self._json_response(HTTPStatus.OK, payload)

    def _get_or_build_cost_statistics_explorer(
        self,
        month: str,
        project_scope: str,
    ) -> tuple[dict[str, object], bool]:
        read_model_service = self._cost_statistics_read_model_service
        if read_model_service is not None:
            cached_read_model = read_model_service.get_read_model(month, project_scope)
            if isinstance(cached_read_model, dict):
                cached_payload = cached_read_model.get("payload")
                if isinstance(cached_payload, dict):
                    return cached_payload, True

        if month == "all":
            self._schedule_cost_statistics_cache_warmup(["all"], reason="explorer_all_cache_miss")
            return self._empty_cost_statistics_explorer_payload(month), False

        payload = self._cost_statistics_service.get_explorer(
            month,
            project_scope=project_scope,
        )
        if read_model_service is not None:
            read_model = read_model_service.upsert_read_model(
                month,
                project_scope,
                payload,
                generated_at=datetime.now().isoformat(),
                source_scope_keys=[month],
                cache_status="ready",
            )
            scope_key = self._cost_statistics_read_model_scope_key(month, project_scope, read_model=read_model)
            self._persist_cost_statistics_read_models_best_effort(
                snapshot=read_model_service.snapshot_scope_keys([scope_key]),
                changed_scope_keys=[scope_key],
                operation="upsert_cost_statistics_explorer_read_model",
            )
        return payload, False

    @staticmethod
    def _empty_cost_statistics_explorer_payload(month: str) -> dict[str, object]:
        return {
            "month": month,
            "summary": {
                "row_count": 0,
                "transaction_count": 0,
                "total_amount": "0.00",
            },
            "time_rows": [],
            "project_rows": [],
            "expense_type_rows": [],
        }

    @staticmethod
    def _cost_statistics_explorer_entry_count(payload: dict[str, object]) -> int:
        time_rows = payload.get("time_rows")
        if isinstance(time_rows, list):
            return len(time_rows)
        summary = payload.get("summary")
        if isinstance(summary, dict):
            raw_count = summary.get("transaction_count", summary.get("row_count", 0))
            try:
                return int(raw_count)
            except (TypeError, ValueError):
                return 0
        return 0

    def _emit_cost_statistics_explorer_metric(
        self,
        *,
        month: str,
        project_scope: str,
        cache_hit: bool,
        duration_ms: float,
        entry_count: int,
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "cost_statistics_explorer_metric",
                    "metric": "cost_statistics.explorer.duration_ms",
                    "month": month,
                    "project_scope": project_scope,
                    "cache_hit": bool(cache_hit),
                    "duration_ms": round(float(duration_ms), 3),
                    "entry_count": int(entry_count),
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def _emit_tax_offset_month_metric(
        self,
        *,
        month: str,
        cache_hit: bool,
        duration_ms: float,
        payload: dict[str, object],
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "tax_offset_month_metric",
                    "metric": "tax_offset.month.duration_ms",
                    "month": month,
                    "cache_hit": bool(cache_hit),
                    "duration_ms": round(float(duration_ms), 3),
                    "output_count": self._safe_list_count(payload.get("output_items")),
                    "input_plan_count": self._safe_list_count(payload.get("input_plan_items")),
                    "certified_count": self._safe_list_count(payload.get("certified_items")),
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def _emit_tax_offset_calculate_metric(
        self,
        *,
        month: str,
        selected_output_count: int,
        selected_input_count: int,
        duration_ms: float,
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "tax_offset_calculate_metric",
                    "metric": "tax_offset.calculate.duration_ms",
                    "month": month,
                    "selected_output_count": int(selected_output_count),
                    "selected_input_count": int(selected_input_count),
                    "duration_ms": round(float(duration_ms), 3),
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    def _handle_api_cost_statistics_project(
        self,
        month: str | None,
        project_name: str,
        project_scope: str | None,
    ) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        try:
            payload = self._cost_statistics_service.get_project_statistics(
                current_month,
                project_name,
                project_scope=project_scope or "active",
            )
        except ValueError as error:
            return self._cost_statistics_project_scope_error_response(error)
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
        project_scope: str | None = None,
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
                project_scope=project_scope or "active",
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        except ValueError as error:
            if str(error) == "project_scope must be active or all":
                return self._cost_statistics_project_scope_error_response(error)
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
        project_scope: str | None = None,
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
                project_scope=project_scope or "active",
            )
        except ValueError as error:
            if str(error) == "project_scope must be active or all":
                return self._cost_statistics_project_scope_error_response(error)
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cost_statistics_export_preview_request", "message": str(error)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_cost_statistics_transaction(
        self,
        transaction_id: str,
        project_scope: str | None,
    ) -> Response:
        try:
            payload = self._cost_statistics_service.get_transaction_detail(
                transaction_id,
                project_scope=project_scope or "active",
            )
        except ValueError as error:
            return self._cost_statistics_project_scope_error_response(error)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "cost_statistics_transaction_not_found", "transaction_id": transaction_id},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _cost_statistics_project_scope_error_response(self, error: ValueError) -> Response:
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {
                "error": "invalid_cost_statistics_project_scope",
                "message": str(error),
            },
        )

    def _handle_api_workbench_confirm_link(self, body: str | None, *, request_id: str | None = None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        return self._handle_live_workbench_confirm_link(payload, request_id=request_id)

    def _handle_api_workbench_confirm_link_preview(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            preview = self._preview_confirm_link(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_preview_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, preview)

    def _handle_api_workbench_mark_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_mark_exception(payload)
        return self._handle_api_workbench_action_payload(payload, self._workbench_api_routes.mark_exception, "invalid_mark_exception_request")

    def _handle_api_workbench_cancel_link(self, body: str | None, *, request_id: str | None = None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        return self._handle_live_workbench_cancel_link(payload, request_id=request_id)

    def _handle_api_workbench_withdraw_link_preview(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            preview = self._preview_withdraw_link(payload)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history", "message": str(exc)},
            )
        except (TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_preview_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, preview)

    def _handle_api_workbench_withdraw_link(self, body: str | None, *, request_id: str | None = None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        return self._handle_live_workbench_withdraw_link(payload, request_id=request_id)

    def _handle_api_workbench_update_bank_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
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
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_oa_bank_exception(payload)
        return self._handle_live_workbench_oa_bank_exception(payload)

    def _handle_api_workbench_cancel_exception(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        month = str(payload.get("month", ""))
        if self._live_workbench_service.has_rows_for_month(month):
            return self._handle_live_workbench_cancel_exception(payload)
        return self._handle_live_workbench_cancel_exception(payload)

    def _handle_api_workbench_ignore_row(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        return self._handle_workbench_ignore_row_payload(payload)

    def _handle_api_workbench_unignore_row(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        freshness_error = self._workbench_write_freshness_guard()
        if freshness_error is not None:
            return freshness_error
        return self._handle_workbench_unignore_row_payload(payload)

    def _handle_api_tax_offset(self, month: str | None) -> Response:
        current_month = month or datetime.now().strftime("%Y-%m")
        started_at = monotonic()
        cache_hit = False
        try:
            payload, cache_hit = self._get_or_build_tax_offset_month_payload(current_month)
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_request", "message": str(exc)},
            )
        self._emit_tax_offset_month_metric(
            month=current_month,
            cache_hit=cache_hit,
            duration_ms=self._duration_ms(started_at),
            payload=payload,
        )
        return self._json_response(HTTPStatus.OK, payload)

    def _get_or_build_tax_offset_month_payload(self, month: str) -> tuple[dict[str, object], bool]:
        read_model_service = self._tax_offset_read_model_service
        if read_model_service is not None:
            cached_read_model = read_model_service.get_read_model(month)
            if isinstance(cached_read_model, dict):
                cached_payload = cached_read_model.get("payload")
                if isinstance(cached_payload, dict):
                    return cached_payload, True

        payload = self._tax_api_routes.get_tax_offset(month)
        if read_model_service is not None:
            read_model = read_model_service.upsert_read_model(
                month,
                payload,
                generated_at=datetime.now().isoformat(),
                source_scope_keys=[month],
                cache_status="ready",
            )
            scope_key = self._tax_offset_read_model_scope_key(month, read_model=read_model)
            self._persist_tax_offset_read_models_best_effort(
                snapshot=read_model_service.snapshot_scope_keys([scope_key]),
                changed_scope_keys=[scope_key],
                operation="upsert_tax_offset_read_model",
            )
        return payload, False

    def _handle_api_bank_details_accounts(self, *, date_from: str | None, date_to: str | None) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            self._bank_details_service.list_accounts(date_from=date_from, date_to=date_to),
        )

    def _handle_api_bank_details_transactions(
        self,
        *,
        account_key: str | None,
        date_from: str | None,
        date_to: str | None,
        page: str | None,
        page_size: str | None,
    ) -> Response:
        try:
            payload = self._bank_details_service.list_transactions(
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                page=int(page or 1),
                page_size=int(page_size or 100),
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_bank_details_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _list_tax_offset_oa_attachment_invoice_rows(self, month: str) -> list[dict[str, object]]:
        return self._workbench_query_service.list_attachment_invoice_rows_by_issue_month(month)

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
        self._invalidate_tax_offset_read_model_scopes(
            list(getattr(batch, "months", []) or []),
            reason="tax_certified_import_confirm",
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
        started_at = monotonic()
        try:
            result = self._tax_api_routes.calculate(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_calculate_request", "message": str(exc)},
            )
        self._emit_tax_offset_calculate_metric(
            month=str(payload.get("month") or ""),
            selected_output_count=self._safe_list_count(payload.get("selected_output_ids")),
            selected_input_count=self._safe_list_count(payload.get("selected_input_ids")),
            duration_ms=self._duration_ms(started_at),
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

    def _handle_live_workbench_confirm_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> Response:
        action_name = "confirm_link"
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            case_id = str(payload["case_id"]) if payload.get("case_id") is not None else None
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_request", "message": str(exc)},
            )

        row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        if not self._can_confirm_link_row_types(row_ids=row_ids, row_types=row_types, month=month):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_confirm_link_request",
                    "message": "confirm link requires rows from at least two panes.",
                },
            )
        amount_check = self._amount_check_for_row_ids(row_ids, month=month, allow_direct=False)
        if amount_check.get("requires_note") and not note:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "workbench_pair_relation_note_required",
                    "message": "金额不一致或方向不确定，请填写备注。",
                    "amount_check": amount_check,
                },
            )

        resolve_rows_started_at = monotonic()
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="resolve_rows",
                duration_ms=self._duration_ms(resolve_rows_started_at),
                detail=f"rows={len(row_ids)}",
            )

        resolved_case_id = case_id or self._workbench_override_service._next_case_id()
        before_relations = self._workbench_pair_relation_service.active_relations_for_row_ids(row_ids)
        selected_rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=False)
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                selected_rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
        pair_relation_started_at = monotonic()
        self._workbench_pair_relation_service.replace_with_confirmed_relation(
            case_id=resolved_case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by="system",
            month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            note=note,
            amount_check=amount_check,
            before_relations=history_before_relations,
        )
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                duration_ms=self._duration_ms(pair_relation_started_at),
                detail=f"case_id={resolved_case_id}",
            )
        changed_scope_keys = list(self._scope_keys_for_row_ids(month=month, row_ids=row_ids))
        invalidate_started_at = monotonic()
        self._invalidate_workbench_read_model_scopes(changed_scope_keys)
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="invalidate_read_model_scopes",
                duration_ms=self._duration_ms(invalidate_started_at),
                detail=",".join(changed_scope_keys),
            )
        schedule_started_at = monotonic()
        self._schedule_workbench_pair_relation_persist(
            changed_case_ids=[
                *[str(relation.get("case_id", "")) for relation in before_relations if str(relation.get("case_id", "")).strip()],
                resolved_case_id,
            ],
            request_id=request_id,
            action_name=action_name,
        )
        self._schedule_workbench_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            request_id=request_id,
            action_name=action_name,
        )
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="schedule_background_persist",
                duration_ms=self._duration_ms(schedule_started_at),
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_link",
                "month": month,
                "case_id": resolved_case_id,
                "affected_row_ids": row_ids,
                "amount_check": amount_check,
                "message": f"已确认 {len(row_ids)} 条记录关联。",
            },
        )

    def _preview_confirm_link(self, payload: dict[str, object]) -> dict[str, object]:
        month = str(payload["month"])
        row_ids = self._normalize_row_ids(list(payload["row_ids"]))
        row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        if not self._can_confirm_link_row_types(row_ids=row_ids, row_types=row_types, month=month):
            raise ValueError("confirm link requires rows from at least two panes.")
        rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
        rows_by_type = self._rows_by_type(rows)
        amount_check = self._amount_check_for_rows_by_type(rows_by_type)
        before_relations = self._workbench_pair_relation_service.active_relations_for_row_ids(row_ids)
        before_groups = self._relation_groups(before_relations, selected_rows=rows, ungrouped_selected_rows="separate")
        case_id = str(payload.get("case_id") or "preview:confirm")
        after_relation = {
            "case_id": case_id,
            "row_ids": row_ids,
            "row_types": row_types,
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            "amount_check": amount_check,
        }
        after_groups = self._relation_groups([after_relation], selected_rows=rows)
        requires_note = bool(amount_check.get("requires_note"))
        return {
            "operation": "confirm_link",
            "can_submit": True,
            "requires_note": requires_note,
            "message": "金额不一致，请填写备注。" if requires_note else "",
            "before": {"groups": before_groups},
            "after": {"groups": after_groups},
            "amount_summary": {
                "before": amount_check,
                "after": amount_check,
                **amount_check,
            },
        }

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
        try:
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=[row])
            updated_row = self._persist_workbench_override_change(
                changed_row_ids=[row_id],
                mutation=lambda: self._workbench_override_service.mark_exception(
                    row=row,
                    exception_code=exception_code,
                    comment=comment,
                ),
                changed_scope_keys=changed_scope_keys,
                action_name="mark_exception",
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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

    def _handle_live_workbench_cancel_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> Response:
        action_name = "cancel_link"
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_link_request", "message": str(exc)},
            )

        resolve_rows_started_at = monotonic()
        active_relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
        if not isinstance(active_relation, dict):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_pair_relation_not_found", "message": row_id},
            )
        affected_row_ids = self._normalize_row_ids(list(active_relation.get("row_ids") or []))
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="resolve_rows",
                duration_ms=self._duration_ms(resolve_rows_started_at),
                detail=f"rows={len(affected_row_ids)}",
            )
        pair_relation_started_at = monotonic()
        cancelled_relation = self._workbench_pair_relation_service.cancel_relation_for_row_id(row_id)
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                duration_ms=self._duration_ms(pair_relation_started_at),
                detail=f"row_id={row_id}",
            )
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=affected_row_ids,
                month_scope=str(active_relation.get("month_scope") or ""),
            )
        )
        invalidate_started_at = monotonic()
        self._invalidate_workbench_read_model_scopes(changed_scope_keys)
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="invalidate_read_model_scopes",
                duration_ms=self._duration_ms(invalidate_started_at),
                detail=",".join(changed_scope_keys),
            )
        changed_case_ids = []
        if isinstance(cancelled_relation, dict):
            changed_case_ids.append(str(cancelled_relation.get("case_id", "")))
        schedule_started_at = monotonic()
        self._schedule_workbench_pair_relation_persist(
            changed_case_ids=changed_case_ids,
            request_id=request_id,
            action_name=action_name,
        )
        self._schedule_workbench_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            request_id=request_id,
            action_name=action_name,
        )
        if request_id is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="schedule_background_persist",
                duration_ms=self._duration_ms(schedule_started_at),
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_link",
                "month": month,
                "case_id": str(active_relation.get("case_id") or ""),
                "affected_row_ids": affected_row_ids,
                "message": "已取消关联并回退为待处理。",
            },
        )

    def _handle_live_workbench_withdraw_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> Response:
        action_name = "withdraw_link"
        try:
            month = str(payload["month"])
            raw_row_ids = payload.get("row_ids")
            if raw_row_ids is None and payload.get("row_id") is not None:
                raw_row_ids = [payload.get("row_id")]
            row_ids = self._normalize_row_ids(list(raw_row_ids or []))
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_request", "message": str(exc)},
            )

        try:
            preview = self._workbench_pair_relation_service.preview_withdraw_for_row_ids(row_ids)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history", "message": str(exc)},
            )

        active_relation = preview["active_relation"]
        _rows, after_relations, affected_row_ids = self._withdraw_rows_and_after_relations(
            active_relation=active_relation,
            after_relations=list(preview.get("after_relations") or []),
            month=month,
        )
        restored_relations, _history = self._workbench_pair_relation_service.withdraw_latest_for_row_ids(
            row_ids,
            created_by="system",
            note=note,
            fallback_after_relations=after_relations,
        )
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=affected_row_ids,
                month_scope=str(active_relation.get("month_scope") or ""),
            )
        )
        self._invalidate_workbench_read_model_scopes(changed_scope_keys)
        changed_case_ids = [
            str(active_relation.get("case_id") or ""),
            *[str(relation.get("case_id") or "") for relation in restored_relations],
        ]
        self._schedule_workbench_pair_relation_persist(
            changed_case_ids=changed_case_ids,
            request_id=request_id,
            action_name=action_name,
        )
        self._schedule_workbench_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            request_id=request_id,
            action_name=action_name,
        )
        return self._json_response(
            HTTPStatus.OK,
            {
                "success": True,
                "operation": "withdraw_link",
                "action": "withdraw_link",
                "month": month,
                "changed_scopes": changed_scope_keys,
                "affected_row_ids": affected_row_ids,
                "restored_relations": restored_relations,
            },
        )

    def _preview_withdraw_link(self, payload: dict[str, object]) -> dict[str, object]:
        month = str(payload["month"])
        raw_row_ids = payload.get("row_ids")
        if raw_row_ids is None and payload.get("row_id") is not None:
            raw_row_ids = [payload.get("row_id")]
        row_ids = self._normalize_row_ids(list(raw_row_ids or []))
        preview = self._workbench_pair_relation_service.preview_withdraw_for_row_ids(row_ids)
        active_relation = preview["active_relation"]
        rows, after_relations, _affected_row_ids = self._withdraw_rows_and_after_relations(
            active_relation=active_relation,
            after_relations=list(preview.get("after_relations") or []),
            month=month,
        )
        before_groups = self._relation_groups([active_relation], selected_rows=rows)
        after_groups = self._relation_groups(after_relations, selected_rows=rows, ungrouped_selected_rows="separate")
        amount_check = self._amount_check_for_withdraw_preview(active_relation=active_relation, rows=rows)
        return {
            "operation": "withdraw_link",
            "can_submit": True,
            "requires_note": False,
            "message": "",
            "before": {"groups": before_groups},
            "after": {"groups": after_groups},
            "amount_summary": {
                "before": amount_check,
                "after": amount_check,
                **amount_check,
            },
            "restored_relations": after_relations,
        }

    def _amount_check_for_withdraw_preview(
        self,
        *,
        active_relation: dict[str, object],
        rows: list[dict[str, object]],
    ) -> dict[str, object]:
        relation_amount_check = active_relation.get("amount_check")
        if isinstance(relation_amount_check, dict) and any(
            relation_amount_check.get(key) is not None
            for key in ("oa_total", "bank_total", "invoice_total")
        ):
            return dict(relation_amount_check)
        return self._amount_check_for_rows_by_type(self._rows_by_type(rows))

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
        try:
            updated_row = self._persist_workbench_override_change(
                changed_row_ids=[row_id],
                mutation=lambda: self._workbench_override_service.update_bank_exception(
                    row=row,
                    relation_code=relation_code,
                    relation_label=relation_label,
                    comment=comment,
                ),
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            exception_code = str(payload["exception_code"])
            exception_label = str(payload["exception_label"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": str(exc)},
            )

        try:
            rows = self._resolve_live_rows_direct(row_ids, month_hint=month)
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
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=rows)
            updated_rows = self._persist_workbench_override_change(
                changed_row_ids=[str(row["id"]) for row in rows],
                mutation=lambda: self._workbench_override_service.apply_oa_bank_exception(
                    rows=rows,
                    exception_code=exception_code,
                    exception_label=exception_label,
                    comment=comment,
                ),
                changed_scope_keys=changed_scope_keys,
                action_name="oa_bank_exception",
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
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

        try:
            rows = self._resolve_live_rows_direct(row_ids, month_hint=month)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        try:
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=rows)
            updated_rows = self._persist_workbench_override_change(
                changed_row_ids=row_ids,
                mutation=lambda: self._workbench_override_service.cancel_exception(rows=rows, comment=comment),
                changed_scope_keys=changed_scope_keys,
                action_name="cancel_exception",
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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

        grouped_payload = self._build_api_workbench_payload(month)
        try:
            row = self._resolve_live_row(grouped_payload, row_id)
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
        try:
            updated_row = self._persist_workbench_override_change(
                changed_row_ids=[row_id],
                mutation=lambda: self._workbench_override_service.ignore_row(row=row, comment=comment),
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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

        ignored_rows = {
            str(row["id"]): row
            for row in self._build_api_workbench_ignored_rows_payload(month)
        }
        row = ignored_rows.get(row_id)
        if row is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        try:
            updated_row = self._persist_workbench_override_change(
                changed_row_ids=[row_id],
                mutation=lambda: self._workbench_override_service.unignore_row(row=row),
            )
        except StatePersistenceError as exc:
            return self._workbench_persistence_unavailable_response(exc)
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
        self._run_workbench_auto_matching_for_scopes(
            self._expand_workbench_matching_months(self._workbench_query_service.list_available_months()),
            reason="oa_integration_sync",
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
        self._persist_state_with_workbench_invalidation(invalidate_cost_statistics=False)
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
        self._invalidate_tax_offset_read_model_scopes(
            self._tax_offset_scope_keys_for_import_preview(preview),
            reason="invoice_import_confirm",
        )
        self._run_workbench_auto_matching_for_scopes(
            self._workbench_matching_scope_months_for_import_preview(preview),
            reason="import_confirm",
        )
        self._persist_state_with_workbench_invalidation(
            cost_statistics_scope_keys=self._cost_statistics_scope_keys_for_import_preview(preview),
        )
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
            preview = self._import_service.get_batch(batch_id)
            batch = self._import_service.revert_import(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        self._file_import_service.mark_batch_reverted(batch_id)
        self._invalidate_tax_offset_read_model_scopes(
            self._tax_offset_scope_keys_for_import_preview(preview),
            reason="invoice_import_revert",
        )
        self._persist_state_with_workbench_invalidation(
            cost_statistics_scope_keys=self._cost_statistics_scope_keys_for_import_preview(preview),
        )
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
        file_overrides, override_error = self._parse_import_file_preview_overrides(fields, len(files))
        if override_error is not None:
            return override_error
        if file_overrides:
            files = [
                UploadedImportFile(
                    file_name=file.file_name,
                    content=file.content,
                    template_code_override=override.get("template_code"),
                    batch_type_override=override.get("batch_type"),
                    selected_bank_mapping_id=override.get("bank_mapping_id"),
                    selected_bank_name=override.get("bank_name"),
                    selected_bank_short_name=override.get("bank_short_name"),
                    selected_bank_last4=override.get("last4"),
                )
                for file, override in zip(files, file_overrides)
            ]
        session = self._file_import_service.preview_files(imported_by=imported_by, uploads=files)
        self._persist_state_with_workbench_invalidation()
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_confirm(self, body: str | bytes | None, headers: dict[str, str] | None) -> Response:
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
        normalized_session_id = str(session_id)
        normalized_selected_file_ids = [str(item) for item in selected_file_ids]
        try:
            session = self._file_import_service.get_session(normalized_session_id)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": str(exc)},
            )

        selected = set(normalized_selected_file_ids)
        unknown_ids = sorted(selected - {item.id for item in session.files})
        if unknown_ids:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": f"Unknown selected file ids: {', '.join(unknown_ids)}"},
            )
        total = len(normalized_selected_file_ids)
        label = self._file_import_job_label(session, normalized_selected_file_ids)
        owner_user_id = self._resolve_background_job_owner(headers)
        selected_key = ",".join(sorted(normalized_selected_file_ids))
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="file_import",
            label=label,
            owner_user_id=owner_user_id,
            idempotency_key=f"file_import_session:{normalized_session_id}:{selected_key}",
            phase="queued",
            current=0,
            total=total,
            message=f"{label}任务已创建。",
            result_summary={"confirmed": 0, "selected": total, "matching_results": 0},
            source={"session_id": normalized_session_id, "selected_file_ids": normalized_selected_file_ids},
            affected_scopes=["imports", "workbench"],
        )
        if created:
            def run_file_import(running_job):
                def progress_callback(progress_session, current: int, progress_total: int) -> None:
                    confirmed_count = sum(1 for file in progress_session.files if file.id in selected and file.status == "confirmed")
                    self._background_job_service.update_progress(
                        running_job.job_id,
                        phase="confirm_files",
                        message=f"正在{label} {current}/{max(progress_total, 1)}。",
                        current=current,
                        total=progress_total,
                        result_summary={
                            "confirmed": confirmed_count,
                            "selected": progress_total,
                            "matching_results": 0,
                        },
                    )

                confirmed_session = self._file_import_service.confirm_session(
                    session_id=normalized_session_id,
                    selected_file_ids=normalized_selected_file_ids,
                    progress_callback=progress_callback,
                )
                matching_run = None
                if any(file.status == "confirmed" for file in confirmed_session.files):
                    matching_run = self._matching_service.run(triggered_by=f"import_session:{confirmed_session.id}")
                    self._run_workbench_auto_matching_for_scopes(
                        self._workbench_matching_scope_months_for_import_file_session(
                            confirmed_session,
                            normalized_selected_file_ids,
                        ),
                        reason="import_file_confirm",
                    )
                self._invalidate_tax_offset_read_model_scopes(
                    self._tax_offset_scope_keys_for_import_file_session(
                        confirmed_session,
                        normalized_selected_file_ids,
                    ),
                    reason="invoice_file_import_confirm",
                )
                self._persist_state_with_workbench_invalidation(
                    cost_statistics_scope_keys=self._cost_statistics_scope_keys_for_import_file_session(
                        confirmed_session,
                        normalized_selected_file_ids,
                    ),
                )
                confirmed_count = sum(1 for file in confirmed_session.files if file.id in selected and file.status == "confirmed")
                result_summary = {
                    "confirmed": confirmed_count,
                    "selected": total,
                    "matching_results": matching_run.result_count if matching_run is not None else 0,
                }
                self._background_job_service.succeed_job(
                    running_job.job_id,
                    f"{label}完成。",
                    result_summary=result_summary,
                )
                return result_summary

            self._background_job_service.run_job(job, run_file_import)

        response_payload = self._serialize_file_session(session)
        response_payload["job"] = job.to_payload()
        return self._json_response(HTTPStatus.ACCEPTED, response_payload)

    @staticmethod
    def _file_import_job_label(session, selected_file_ids: list[str]) -> str:
        selected = set(selected_file_ids)
        batch_types = {
            file.batch_type.value if isinstance(file.batch_type, BatchType) else str(file.batch_type)
            for file in session.files
            if file.id in selected and file.batch_type is not None
        }
        if batch_types == {BatchType.BANK_TRANSACTION.value}:
            return "导入 银行流水"
        if batch_types and batch_types.issubset({BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value}):
            return "导入 发票"
        return "导入文件"

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

    def _parse_import_file_preview_overrides(
        self,
        fields: dict[str, list[str]],
        file_count: int,
    ) -> tuple[list[dict[str, str]], Response | None]:
        raw_values = fields.get("file_overrides") or []
        if not raw_values:
            return [{} for _ in range(file_count)], None
        try:
            raw_overrides = json.loads(raw_values[0])
        except json.JSONDecodeError:
            return [], self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_file_preview_request",
                    "message": "file_overrides must be a JSON array.",
                },
            )
        if not isinstance(raw_overrides, list):
            return [], self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_import_file_preview_request",
                    "message": "file_overrides must be a JSON array.",
                },
            )
        normalized: list[dict[str, str]] = []
        for raw_override in raw_overrides[:file_count]:
            if not isinstance(raw_override, dict):
                normalized.append({})
                continue
            normalized.append(
                {
                    key: value.strip()
                    for key in ("template_code", "batch_type", "bank_mapping_id", "bank_name", "bank_short_name", "last4")
                    if isinstance((value := raw_override.get(key)), str) and value.strip()
                }
            )
        while len(normalized) < file_count:
            normalized.append({})
        return normalized, None

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

    def _cost_statistics_scope_keys_for_import_preview(self, preview: object) -> list[str]:
        normalized_rows = getattr(preview, "normalized_rows", [])
        return self._cost_statistics_scope_keys_for_import_rows(normalized_rows)

    def _cost_statistics_scope_keys_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
    ) -> list[str]:
        selected = {str(file_id) for file_id in list(selected_file_ids or []) if str(file_id)}
        normalized_rows: list[object] = []
        for item in list(getattr(session, "files", []) or []):
            if str(getattr(item, "id", "")) not in selected:
                continue
            if str(getattr(item, "status", "")) != "confirmed":
                continue
            normalized_rows.extend(list(getattr(item, "normalized_rows", []) or []))
        return self._cost_statistics_scope_keys_for_import_rows(normalized_rows)

    def _workbench_matching_scope_months_for_import_preview(self, preview: object) -> list[str]:
        return self._workbench_matching_scope_months_for_import_rows(getattr(preview, "normalized_rows", []))

    def _workbench_matching_scope_months_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
    ) -> list[str]:
        selected = {str(file_id) for file_id in list(selected_file_ids or []) if str(file_id)}
        normalized_rows: list[object] = []
        for item in list(getattr(session, "files", []) or []):
            if str(getattr(item, "id", "")) not in selected:
                continue
            if str(getattr(item, "status", "")) != "confirmed":
                continue
            normalized_rows.extend(list(getattr(item, "normalized_rows", []) or []))
        return self._workbench_matching_scope_months_for_import_rows(normalized_rows)

    @classmethod
    def _workbench_matching_scope_months_for_import_rows(cls, rows: object) -> list[str]:
        months: set[str] = set()
        date_fields = (
            "txn_date",
            "invoice_date",
            "issue_date",
            "trade_time",
            "pay_receive_time",
            "date",
        )
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            for field in date_fields:
                raw_value = str(row.get(field) or "").strip()
                if len(raw_value) < 7:
                    continue
                month = raw_value[:7]
                if SEARCH_MONTH_RE.match(month):
                    months.add(month)
                    break
        return cls._expand_workbench_matching_months(months)

    @classmethod
    def _expand_workbench_matching_months(cls, months: Iterable[str]) -> list[str]:
        expanded: set[str] = set()
        for month in months:
            normalized_month = str(month or "").strip()
            if not SEARCH_MONTH_RE.match(normalized_month):
                continue
            expanded.add(normalized_month)
            expanded.add(cls._shift_month(normalized_month, -1))
            expanded.add(cls._shift_month(normalized_month, 1))
        return sorted(expanded)

    @staticmethod
    def _shift_month(month: str, delta: int) -> str:
        current = datetime.strptime(f"{month}-01", "%Y-%m-%d")
        month_index = current.year * 12 + current.month - 1 + delta
        year = month_index // 12
        resolved_month = month_index % 12 + 1
        return f"{year:04d}-{resolved_month:02d}"

    def _tax_offset_scope_keys_for_import_preview(self, preview: object) -> list[str]:
        batch = getattr(preview, "batch", None)
        if getattr(batch, "batch_type", None) not in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
            return []
        normalized_rows = getattr(preview, "normalized_rows", [])
        return self._tax_offset_scope_keys_for_import_rows(normalized_rows)

    def _tax_offset_scope_keys_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
    ) -> list[str]:
        selected = {str(file_id) for file_id in list(selected_file_ids or []) if str(file_id)}
        normalized_rows: list[object] = []
        for item in list(getattr(session, "files", []) or []):
            if str(getattr(item, "id", "")) not in selected:
                continue
            if str(getattr(item, "status", "")) != "confirmed":
                continue
            if getattr(item, "batch_type", None) not in (BatchType.OUTPUT_INVOICE, BatchType.INPUT_INVOICE):
                continue
            normalized_rows.extend(list(getattr(item, "normalized_rows", []) or []))
        return self._tax_offset_scope_keys_for_import_rows(normalized_rows)

    @staticmethod
    def _tax_offset_scope_keys_for_import_rows(rows: object) -> list[str]:
        months: set[str] = set()
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            raw_value = str(row.get("invoice_date") or row.get("issue_date") or row.get("date") or "").strip()
            if len(raw_value) < 7:
                continue
            month = raw_value[:7]
            if SEARCH_MONTH_RE.match(month):
                months.add(month)
        return sorted(months)

    @staticmethod
    def _cost_statistics_scope_keys_for_import_rows(rows: object) -> list[str]:
        months: set[str] = set()
        date_fields = (
            "txn_date",
            "invoice_date",
            "issue_date",
            "trade_time",
            "pay_receive_time",
            "date",
        )
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            for field in date_fields:
                raw_value = str(row.get(field) or "").strip()
                if len(raw_value) < 7:
                    continue
                month = raw_value[:7]
                if SEARCH_MONTH_RE.match(month):
                    months.add(month)
                    break
        return sorted(months) if months else ["all"]

    def _run_workbench_auto_matching_for_scopes(
        self,
        scope_months: list[str],
        *,
        reason: str,
        request_id: str | None = None,
    ) -> dict[str, object] | None:
        normalized_months = [
            str(month).strip()
            for month in list(scope_months or [])
            if SEARCH_MONTH_RE.match(str(month).strip())
        ]
        normalized_months = sorted(dict.fromkeys(normalized_months))
        if not normalized_months:
            return None
        with self._workbench_matching_run_lock:
            running_overlap = sorted(set(normalized_months).intersection(self._workbench_matching_running_scope_months))
            if running_overlap:
                self._workbench_matching_dirty_scope_service.mark_dirty(
                    normalized_months,
                    reason=f"{reason}_coalesced",
                )
                if self._state_store is not None:
                    self._persist_state()
                return None
            self._workbench_matching_running_scope_months.update(normalized_months)
        try:
            summary = self._workbench_matching_orchestrator.run(
                changed_scope_months=normalized_months,
                reason=reason,
                request_id=request_id or f"workbench-match-{uuid4().hex}",
            )
        except Exception as exc:
            self._workbench_matching_dirty_scope_service.mark_dirty(
                normalized_months,
                reason=reason,
                error=str(exc),
            )
            if self._state_store is not None:
                self._persist_state()
            self._emit_workbench_persistence_warning(
                operation=f"{reason}_auto_matching",
                detail=f"queued dirty scopes after matching failure: {exc}",
            )
            return None
        finally:
            with self._workbench_matching_run_lock:
                for month in normalized_months:
                    self._workbench_matching_running_scope_months.discard(month)
        read_model_scope_keys = self._expand_workbench_read_model_scope_keys_for_base_scopes(normalized_months)
        for scope_key in read_model_scope_keys:
            self._workbench_read_model_service.delete_read_model(scope_key)
        if self._state_store is not None:
            self._persist_workbench_candidate_matches_best_effort(operation=f"{reason}_candidate_matches")
            self._persist_workbench_read_models_best_effort(
                snapshot=self._workbench_read_model_service.snapshot(),
                changed_scope_keys=read_model_scope_keys,
                operation=f"{reason}_invalidate_read_models",
            )
        self._search_service.clear_cache()
        return summary

    def _workbench_matching_rows_for_scope(self, scope_month: str) -> dict[str, list[dict[str, object]]]:
        payload = self._build_raw_workbench_payload(scope_month)
        return {
            "oa_rows": self._workbench_matching_rows_from_payload(payload, "oa"),
            "bank_rows": self._workbench_matching_rows_from_payload(payload, "bank"),
            "invoice_rows": self._workbench_matching_rows_from_payload(payload, "invoice"),
        }

    @staticmethod
    def _workbench_matching_rows_from_payload(
        payload: dict[str, object],
        row_type: str,
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for section_name in ("paired", "open"):
            section = payload.get(section_name)
            if isinstance(section, dict):
                section_rows = section.get(row_type)
                if isinstance(section_rows, list):
                    rows.extend(row for row in section_rows if isinstance(row, dict))
                groups = section.get("groups")
                if isinstance(groups, list):
                    for group in groups:
                        if not isinstance(group, dict):
                            continue
                        group_rows = group.get(f"{row_type}_rows")
                        if isinstance(group_rows, list):
                            rows.extend(row for row in group_rows if isinstance(row, dict))
        seen: set[str] = set()
        deduped: list[dict[str, object]] = []
        for row in rows:
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if row_id and row_id not in seen:
                seen.add(row_id)
                deduped.append(row)
        return deduped

    def _workbench_matching_settings(self) -> dict[str, object]:
        return {
            "offset_applicant_names": self._app_settings_service.get_oa_invoice_offset_applicant_names(),
        }

    def _workbench_matching_source_versions(self) -> dict[str, object]:
        parser_version = self._current_oa_attachment_invoice_parser_version()
        payload: dict[str, object] = {
            "workbench_read_model_schema_version": WORKBENCH_READ_MODEL_SCHEMA_VERSION,
        }
        if parser_version:
            payload["oa_attachment_invoice_parser_version"] = parser_version
        return payload

    def _persist_workbench_candidate_matches_best_effort(self, *, operation: str) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save_workbench_candidate_matches(
                self._workbench_candidate_match_service.snapshot()
            )
        except Exception as exc:
            self._emit_workbench_persistence_warning(operation=operation, detail=str(exc))

    def _persist_state(self) -> None:
        self._search_service.clear_cache()
        if self._state_store is None:
            return
        cost_statistics_snapshot = (
            self._cost_statistics_read_model_service.snapshot()
            if self._cost_statistics_read_model_service is not None
            else {}
        )
        tax_offset_snapshot = (
            self._tax_offset_read_model_service.snapshot()
            if self._tax_offset_read_model_service is not None
            else {}
        )
        self._state_store.save(
            {
                "imports": self._import_service.snapshot(),
                "file_imports": self._file_import_service.snapshot(),
                "matching": self._matching_service.snapshot(),
                "workbench_overrides": self._workbench_override_service.snapshot(),
                "workbench_pair_relations": self._workbench_pair_relation_service.snapshot(),
                "workbench_read_models": self._workbench_read_model_service.snapshot(),
                "workbench_candidate_matches": self._workbench_candidate_match_service.snapshot(),
                "workbench_matching_dirty_scopes": self._workbench_matching_dirty_scope_service.snapshot(),
                "cost_statistics_read_models": cost_statistics_snapshot,
                "tax_offset_read_models": tax_offset_snapshot,
            }
        )

    def _persist_state_with_workbench_invalidation(
        self,
        *,
        cost_statistics_scope_keys: list[str] | None = None,
        invalidate_cost_statistics: bool = True,
    ) -> None:
        self._search_service.clear_cache()
        self._invalidate_workbench_read_models(invalidate_cost_statistics=False)
        if invalidate_cost_statistics:
            if cost_statistics_scope_keys is None:
                self._invalidate_cost_statistics_read_models()
            else:
                self._invalidate_cost_statistics_read_model_scopes(
                    cost_statistics_scope_keys,
                    reason="import_state_changed",
                )
        self._persist_state()

    def _persist_workbench_pair_relations(
        self,
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        self._search_service.clear_cache()
        if self._state_store is None:
            return
        snapshot = (
            self._workbench_pair_relation_service.snapshot_case_ids(changed_case_ids)
            if changed_case_ids is not None
            else self._workbench_pair_relation_service.snapshot()
        )
        self._state_store.save_workbench_pair_relations(
            snapshot,
            changed_case_ids=changed_case_ids,
        )

    def _schedule_workbench_pair_relation_persist(
        self,
        *,
        changed_case_ids: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        normalized_case_ids = [
            str(case_id)
            for case_id in list(changed_case_ids or [])
            if str(case_id).strip()
        ]
        if not normalized_case_ids:
            return
        with self._workbench_pair_relation_persist_version_lock:
            self._workbench_pair_relation_persist_version += 1
            version = self._workbench_pair_relation_persist_version
        Thread(
            target=self._persist_workbench_pair_relations_in_background,
            kwargs={
                "version": version,
                "case_ids": normalized_case_ids,
                "request_id": request_id,
                "action_name": action_name,
            },
            daemon=True,
        ).start()

    def _persist_workbench_pair_relations_in_background(
        self,
        *,
        version: int,
        case_ids: list[str],
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        with self._workbench_pair_relation_persist_version_lock:
            if version != self._workbench_pair_relation_persist_version:
                return
        persist_started_at = monotonic()
        self._persist_workbench_pair_relations(changed_case_ids=case_ids)
        if request_id is not None and action_name is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="persist_pair_relations",
                duration_ms=self._duration_ms(persist_started_at),
                detail=",".join(case_ids),
            )

    def _schedule_workbench_read_model_persist(
        self,
        *,
        changed_scope_keys: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        normalized_scope_keys = [
            str(scope_key)
            for scope_key in list(changed_scope_keys or [])
            if str(scope_key).strip()
        ]
        if not normalized_scope_keys:
            return
        with self._workbench_read_model_persist_version_lock:
            self._workbench_read_model_persist_version += 1
            version = self._workbench_read_model_persist_version
        Thread(
            target=self._rebuild_workbench_read_models_in_background,
            kwargs={
                "version": version,
                "scope_keys": normalized_scope_keys,
                "request_id": request_id,
                "action_name": action_name,
            },
            daemon=True,
        ).start()

    def _rebuild_workbench_read_models_in_background(
        self,
        *,
        version: int,
        scope_keys: list[str],
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        if self._state_store is None:
            return
        with self._workbench_read_model_persist_version_lock:
            if version != self._workbench_read_model_persist_version:
                return
        rebuild_started_at = monotonic()
        for scope_key in scope_keys:
            scope_started_at = monotonic()
            base_scope_key = self._workbench_read_model_base_scope_key(scope_key)
            raw_payload = self._build_raw_workbench_payload(base_scope_key)
            candidate_payload = self._apply_candidate_matches_to_payload(raw_payload, base_scope_key)
            grouped_payload = self._group_row_payload(candidate_payload)
            self._apply_workbench_runtime_metadata(grouped_payload)
            ignored_rows = self._extract_ignored_rows(candidate_payload)
            self._workbench_read_model_service.upsert_read_model(
                scope_key=scope_key,
                payload=grouped_payload,
                ignored_rows=ignored_rows,
            )
            if request_id is not None and action_name is not None:
                self._emit_workbench_action_timing(
                    request_id=request_id,
                    action_name=action_name,
                    phase="rebuild_read_model_scope",
                    duration_ms=self._duration_ms(scope_started_at),
                    detail=scope_key,
                )
        persist_started_at = monotonic()
        snapshot = self._workbench_read_model_service.snapshot_scope_keys(scope_keys)
        self._persist_workbench_read_models_best_effort(
            snapshot=snapshot,
            changed_scope_keys=scope_keys,
            operation="background_rebuild_read_models",
        )
        if request_id is not None and action_name is not None:
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="persist_read_models",
                duration_ms=self._duration_ms(persist_started_at),
                detail=",".join(scope_keys),
            )
            self._emit_workbench_action_timing(
                request_id=request_id,
                action_name=action_name,
                phase="background_total",
                duration_ms=self._duration_ms(rebuild_started_at),
                detail=",".join(scope_keys),
            )

    def _save_workbench_overrides_snapshot(self, *, changed_row_ids: list[str] | None = None) -> None:
        self._search_service.clear_cache()
        if self._state_store is None:
            return
        self._state_store.save_workbench_overrides(
            self._workbench_override_service.snapshot(),
            changed_row_ids=changed_row_ids,
        )

    def _persist_workbench_overrides(self, *, changed_row_ids: list[str] | None = None) -> None:
        self._save_workbench_overrides_snapshot(changed_row_ids=changed_row_ids)
        self._invalidate_workbench_read_models()
        self._persist_workbench_read_models_best_effort(
            snapshot=self._workbench_read_model_service.snapshot(),
            operation="invalidate_read_models_after_override_save",
        )

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

    def _get_or_build_workbench_read_model(self, month: str, *, visibility_key: str = "global") -> dict[str, object]:
        read_model_scope_key = self._workbench_read_model_scope_key(month, visibility_key=visibility_key)
        cached_read_model = self._workbench_read_model_service.get_read_model(read_model_scope_key)
        fallback_read_model: dict[str, object] | None = None
        if isinstance(cached_read_model, dict):
            cached_payload = cached_read_model.get("payload")
            cached_ignored_rows = cached_read_model.get("ignored_rows")
            if (
                isinstance(cached_payload, dict)
                and isinstance(cached_ignored_rows, list)
                and self._can_use_cached_workbench_payload(cached_payload)
            ):
                return cached_read_model
            if (
                isinstance(cached_payload, dict)
                and isinstance(cached_ignored_rows, list)
                and self._can_fallback_to_stale_workbench_payload(cached_payload)
            ):
                fallback_read_model = cached_read_model

        raw_payload = self._build_raw_workbench_payload(month)
        relation_payload = self._apply_pair_relations_to_payload(raw_payload)
        candidate_payload = self._apply_candidate_matches_to_payload(relation_payload, month)
        grouped_payload = self._group_row_payload(candidate_payload)
        self._apply_workbench_runtime_metadata(grouped_payload)
        ignored_rows = self._extract_ignored_rows(candidate_payload)
        if not self._can_persist_workbench_payload(grouped_payload):
            if fallback_read_model is not None:
                return fallback_read_model
            self._workbench_read_model_service.delete_read_model(read_model_scope_key)
            return {
                "scope_key": read_model_scope_key,
                "scope_type": "all_time" if month == "all" else "month",
                "generated_at": datetime.now().isoformat(),
                "payload": grouped_payload,
                "ignored_rows": ignored_rows,
            }
        read_model = self._workbench_read_model_service.upsert_read_model(
            scope_key=read_model_scope_key,
            payload=grouped_payload,
            ignored_rows=ignored_rows,
        )
        if self._state_store is not None:
            self._persist_workbench_read_models_best_effort(
                snapshot=self._workbench_read_model_service.snapshot_scope_keys([read_model_scope_key]),
                changed_scope_keys=[read_model_scope_key],
                operation="get_or_build_read_model",
            )
        return read_model

    def _build_api_workbench_payload(self, month: str, *, visibility_key: str = "global") -> dict[str, object]:
        read_model = self._get_or_build_workbench_read_model(month, visibility_key=visibility_key)
        payload = read_model.get("payload")
        retained = self._apply_oa_retention_to_grouped_payload(payload if isinstance(payload, dict) else {})
        return self._derive_tags_for_grouped_payload(retained)

    def _apply_workbench_runtime_metadata(self, payload: dict[str, object]) -> None:
        payload["workbench_read_model_schema_version"] = WORKBENCH_READ_MODEL_SCHEMA_VERSION
        parser_version = self._current_oa_attachment_invoice_parser_version()
        if parser_version:
            payload["oa_attachment_invoice_parser_version"] = parser_version

    def _current_oa_attachment_invoice_parser_version(self) -> str:
        if isinstance(self._workbench_query_service._oa_adapter, MongoOAAdapter):
            return OAAttachmentInvoiceService.PARSER_VERSION
        return ""

    def _build_api_workbench_ignored_rows_payload(self, month: str, *, visibility_key: str = "global") -> list[dict[str, object]]:
        read_model = self._get_or_build_workbench_read_model(month, visibility_key=visibility_key)
        ignored_rows = read_model.get("ignored_rows")
        return self._serialize_value(ignored_rows if isinstance(ignored_rows, list) else [])

    @staticmethod
    def _workbench_read_model_scope_key(month: str, *, visibility_key: str = "global") -> str:
        normalized_month = str(month or "").strip() or "all"
        normalized_visibility = str(visibility_key or "global").strip() or "global"
        if normalized_visibility == "global":
            return normalized_month
        return f"visibility:{normalized_visibility}:{normalized_month}"

    @staticmethod
    def _workbench_read_model_base_scope_key(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key.startswith("visibility:"):
            return normalized_scope_key or "all"
        terminal_scope = normalized_scope_key.rsplit(":", 1)[-1].strip()
        return terminal_scope or "all"

    def _build_raw_workbench_payload(self, month: str) -> dict[str, object]:
        if self._live_workbench_service.has_rows_for_month(month):
            self._sync_live_auto_pair_relations()
            payload = self._build_live_workbench_row_payload(month)
        else:
            payload = self._build_oa_workbench_row_payload(month)
        self._sync_oa_invoice_offset_auto_pair_relations(payload)
        paired_payload = self._apply_pair_relations_to_payload(payload)
        return self._workbench_override_service.apply_to_payload(paired_payload)

    def _build_live_workbench_row_payload(self, month: str) -> dict[str, object]:
        live_payload = self._live_workbench_service.get_workbench(month)
        oa_payload = self._build_oa_workbench_row_payload(month)
        merged = self._merge_live_workbench_with_oa_rows(live_payload, oa_payload)
        return self._serialize_value(merged)

    def _build_oa_workbench_row_payload(self, month: str) -> dict[str, object]:
        if month == "all" and isinstance(self._workbench_query_service._oa_adapter, MongoOAAdapter):
            return self._build_retained_all_oa_row_payload()
        return self._serialize_value(self._workbench_api_routes.get_workbench(month))

    def _build_retained_all_oa_row_payload(self) -> dict[str, object]:
        cutoff_date = self._parse_oa_retention_date(self._app_settings_service.get_oa_retention_cutoff_date())
        if cutoff_date is None:
            return self._serialize_value(self._workbench_api_routes.get_workbench("all"))

        scoped_months = self._retained_oa_months_for_all_scope(cutoff_date)
        supplemental_oa_row_ids = self._supplemental_retained_oa_row_ids(cutoff_date)
        oa_adapter = self._workbench_query_service._oa_adapter
        suppress_attachment_parse = getattr(oa_adapter, "suppress_attachment_invoice_background_parse", None)
        parse_context = suppress_attachment_parse() if callable(suppress_attachment_parse) else nullcontext()
        with parse_context:
            for scoped_month in scoped_months:
                self._workbench_query_service._sync_oa_rows(scoped_month)
            if supplemental_oa_row_ids:
                self._workbench_query_service.sync_oa_row_ids(supplemental_oa_row_ids)
        return self._serialize_value(
            self._raw_oa_payload_for_selected_scope(
                months=set(scoped_months),
                supplemental_oa_row_ids=set(supplemental_oa_row_ids),
            )
        )

    def _retained_oa_months_for_all_scope(self, cutoff_date: datetime) -> list[str]:
        cutoff_month = cutoff_date.strftime("%Y-%m")
        list_available_months = getattr(self._workbench_query_service._oa_adapter, "list_available_months", None)
        available_months: list[str]
        try:
            if callable(list_available_months):
                available_months = [
                    str(month).strip()
                    for month in list_available_months()
                    if str(month).strip()
                ]
            else:
                available_months = self._workbench_query_service.list_available_months()
        except Exception:
            available_months = []
        if available_months:
            return sorted(month for month in available_months if month >= cutoff_month)

        oa_status = self._workbench_query_service.oa_status_payload()
        if isinstance(self._workbench_query_service._oa_adapter, MongoOAAdapter) and str(oa_status.get("code", "")).strip() != "ready":
            return self._fallback_retained_oa_months_for_all_scope(cutoff_date)
        return []

    def _fallback_retained_oa_months_for_all_scope(self, cutoff_date: datetime) -> list[str]:
        cutoff_month = cutoff_date.strftime("%Y-%m")
        end_month = self._fallback_retained_oa_end_month()
        if not SEARCH_MONTH_RE.match(cutoff_month) or not SEARCH_MONTH_RE.match(end_month):
            return [cutoff_month] if SEARCH_MONTH_RE.match(cutoff_month) else []
        months: list[str] = []
        current = datetime.strptime(f"{cutoff_month}-01", "%Y-%m-%d")
        end = datetime.strptime(f"{end_month}-01", "%Y-%m-%d")
        while current <= end:
            months.append(current.strftime("%Y-%m"))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return months

    @staticmethod
    def _fallback_retained_oa_end_month() -> str:
        return datetime.now().strftime("%Y-%m")

    def _supplemental_retained_oa_row_ids(self, cutoff_date: datetime) -> list[str]:
        retained_row_ids: set[str] = set()
        for relation in self._workbench_pair_relation_service.list_active_relations():
            row_ids = [
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            ]
            row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
            oa_row_ids = [
                row_id
                for index, row_id in enumerate(row_ids)
                if (row_types[index] if index < len(row_types) else "") == "oa"
            ]
            bank_row_ids = [
                row_id
                for index, row_id in enumerate(row_ids)
                if (row_types[index] if index < len(row_types) else "") == "bank"
            ]
            if not oa_row_ids or not bank_row_ids:
                continue
            try:
                bank_rows = self._resolve_live_rows_direct(bank_row_ids, month_hint="all")
            except KeyError:
                continue
            if any(self._row_is_on_or_after(row, cutoff_date, row_type="bank") for row in bank_rows):
                retained_row_ids.update(oa_row_ids)
        return sorted(retained_row_ids)

    def _raw_oa_payload_for_selected_scope(
        self,
        *,
        months: set[str],
        supplemental_oa_row_ids: set[str],
    ) -> dict[str, object]:
        paired: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        open_rows: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}

        for row in self._workbench_query_service.list_record_snapshots():
            row_type = str(row.get("type", "")).strip()
            row_month = str(row.get("_month", "")).strip()
            include_row = False
            if row_type == "oa":
                include_row = row_month in months or str(row.get("id", "")) in supplemental_oa_row_ids
            elif row_type == "invoice" and str(row.get("source_kind", "")) == "oa_attachment_invoice":
                include_row = row_month in months or str(row.get("derived_from_oa_id", "")) in supplemental_oa_row_ids
            if not include_row:
                continue
            section_payload = paired if row.get("_section") == "paired" else open_rows
            section_payload[row_type].append(self._workbench_query_service.serialize_row(row))

        month_rows = [*paired["oa"], *open_rows["oa"], *paired["invoice"], *open_rows["invoice"]]
        return {
            "month": "all",
            "oa_status": self._workbench_query_service.oa_status_payload(),
            "summary": {
                "oa_count": len(paired["oa"]) + len(open_rows["oa"]),
                "bank_count": 0,
                "invoice_count": len(paired["invoice"]) + len(open_rows["invoice"]),
                "paired_count": len(paired["oa"]) + len(paired["invoice"]),
                "open_count": len(open_rows["oa"]) + len(open_rows["invoice"]),
                "exception_count": sum(
                    1
                    for row in month_rows
                    if str(
                        row.get("oa_bank_relation", row.get("invoice_bank_relation", {})).get("tone", "")
                    )
                    == "danger"
                ),
            },
            "paired": paired,
            "open": open_rows,
        }

    @staticmethod
    def _merge_live_workbench_with_oa_rows(
        live_payload: dict[str, object],
        oa_payload: dict[str, object],
    ) -> dict[str, object]:
        merged = Application._serialize_value(live_payload)
        merged["oa_status"] = Application._serialize_value(oa_payload.get("oa_status") or {"code": "ready", "message": "OA 已同步"})
        merged["paired"]["oa"] = Application._serialize_value(oa_payload["paired"]["oa"])
        merged["open"]["oa"] = Application._serialize_value(oa_payload["open"]["oa"])
        merged["paired"]["invoice"] = [
            *Application._serialize_value(merged["paired"].get("invoice", [])),
            *[
                row
                for row in Application._serialize_value(oa_payload["paired"].get("invoice", []))
                if str(row.get("source_kind", "")) == "oa_attachment_invoice"
            ],
        ]
        merged["open"]["invoice"] = [
            *Application._serialize_value(merged["open"].get("invoice", [])),
            *[
                row
                for row in Application._serialize_value(oa_payload["open"].get("invoice", []))
                if str(row.get("source_kind", "")) == "oa_attachment_invoice"
            ],
        ]
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
        grouped = grouping_service.group_payload(
            str(payload.get("month", "")),
            oa_rows=oa_rows,
            bank_rows=bank_rows,
            invoice_rows=invoice_rows,
        )
        oa_status = payload.get("oa_status")
        if isinstance(oa_status, dict):
            grouped["oa_status"] = Application._serialize_value(oa_status)
        return grouped

    def _can_use_cached_workbench_payload(self, payload: dict[str, object]) -> bool:
        if not self._oa_status_is_ready_for_cache(payload):
            return False
        if self._cached_payload_needs_oa_invoice_offset_rebuild(payload):
            return False
        if isinstance(self._workbench_query_service._oa_adapter, MongoOAAdapter):
            cached_schema_version = str(payload.get("workbench_read_model_schema_version") or "").strip()
            if cached_schema_version != WORKBENCH_READ_MODEL_SCHEMA_VERSION:
                return False
            expected_parser_version = self._current_oa_attachment_invoice_parser_version()
            cached_parser_version = str(payload.get("oa_attachment_invoice_parser_version") or "").strip()
            if expected_parser_version and cached_parser_version != expected_parser_version:
                return False
            summary = payload.get("summary")
            if isinstance(summary, dict):
                try:
                    return int(summary.get("oa_count", 0) or 0) > 0
                except (TypeError, ValueError):
                    return False
        return True

    def _can_persist_workbench_payload(self, payload: dict[str, object]) -> bool:
        return self._oa_status_is_ready_for_cache(payload)

    def _can_fallback_to_stale_workbench_payload(self, payload: dict[str, object]) -> bool:
        return self._oa_status_is_ready_for_cache(payload)

    def _oa_status_is_ready_for_cache(self, payload: dict[str, object]) -> bool:
        oa_status = payload.get("oa_status")
        if isinstance(self._workbench_query_service._oa_adapter, MongoOAAdapter):
            return isinstance(oa_status, dict) and str(oa_status.get("code", "")).strip() == "ready"
        return not isinstance(oa_status, dict) or str(oa_status.get("code", "")).strip() == "ready"

    def _cached_payload_needs_oa_invoice_offset_rebuild(self, payload: dict[str, object]) -> bool:
        applicant_names = {
            str(name).strip()
            for name in self._app_settings_service.get_oa_invoice_offset_applicant_names()
            if str(name).strip()
        }
        if not applicant_names:
            return False
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for group in list(section_payload.get("groups", [])):
                if not isinstance(group, dict):
                    continue
                oa_rows = [row for row in list(group.get("oa_rows", [])) if isinstance(row, dict)]
                invoice_rows = [row for row in list(group.get("invoice_rows", [])) if isinstance(row, dict)]
                for oa_row in oa_rows:
                    if str(oa_row.get("applicant", "")).strip() not in applicant_names:
                        continue
                    if not self._oa_attachment_invoice_rows_for_oa(oa_row, invoice_rows):
                        continue
                    if section == "open":
                        return True
                    for row in [*oa_rows, *invoice_rows]:
                        tags = {str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()}
                        if OA_INVOICE_OFFSET_TAG not in tags or not bool(row.get("cost_excluded")):
                            return True
        return False

    def _apply_oa_retention_to_grouped_payload(self, payload: dict[str, object]) -> dict[str, object]:
        cutoff_date = self._parse_oa_retention_date(self._app_settings_service.get_oa_retention_cutoff_date())
        if cutoff_date is None:
            return self._serialize_value(payload)

        result = self._serialize_value(payload)
        changed = False
        for section in ("paired", "open"):
            section_payload = result.setdefault(section, {})
            original_groups = list(section_payload.get("groups", []))
            filtered_groups: list[dict[str, object]] = []
            for group in original_groups:
                normalized_group = self._serialize_value(group)
                oa_rows = list(normalized_group.get("oa_rows", []))
                bank_rows = list(normalized_group.get("bank_rows", []))
                invoice_rows = list(normalized_group.get("invoice_rows", []))
                keep_all_group_oa = any(self._row_is_on_or_after(row, cutoff_date, row_type="oa") for row in oa_rows) or any(
                    self._row_is_on_or_after(row, cutoff_date, row_type="bank") for row in bank_rows
                )
                retained_oa_rows = [
                    row
                    for row in oa_rows
                    if keep_all_group_oa or not self._row_has_parseable_retention_date(row, row_type="oa")
                ]
                if len(retained_oa_rows) != len(oa_rows):
                    changed = True
                normalized_group["oa_rows"] = retained_oa_rows
                normalized_group["bank_rows"] = bank_rows
                normalized_group["invoice_rows"] = invoice_rows
                if normalized_group["oa_rows"] or normalized_group["bank_rows"] or normalized_group["invoice_rows"]:
                    filtered_groups.append(normalized_group)
            if len(filtered_groups) != len(original_groups):
                changed = True
            section_payload["groups"] = filtered_groups
        if changed:
            result["summary"] = self._workbench_grouped_summary(result)
        return result

    @classmethod
    def _row_is_on_or_after(cls, row: dict[str, object], cutoff_date: datetime, *, row_type: str) -> bool:
        for value in cls._row_date_candidates(row, row_type=row_type):
            parsed = cls._parse_oa_retention_date(value)
            if parsed is not None and parsed >= cutoff_date:
                return True
        return False

    @classmethod
    def _row_has_parseable_retention_date(cls, row: dict[str, object], *, row_type: str) -> bool:
        return any(cls._parse_oa_retention_date(value) is not None for value in cls._row_date_candidates(row, row_type=row_type))

    @staticmethod
    def _row_date_candidates(row: dict[str, object], *, row_type: str) -> list[object]:
        candidates: list[object] = []
        if row_type == "oa":
            candidates.extend([row.get("application_date"), row.get("apply_date")])
            for fields_key in ("summary_fields", "detail_fields"):
                fields = row.get(fields_key)
                if isinstance(fields, dict):
                    candidates.extend(
                        fields.get(key)
                        for key in ("申请日期", "报销日期", "审批完成时间", "单据日期", "日期")
                    )
        elif row_type == "bank":
            candidates.extend([row.get("trade_time"), row.get("pay_receive_time"), row.get("txn_date")])
            fields = row.get("summary_fields")
            if isinstance(fields, dict):
                candidates.extend(fields.get(key) for key in ("交易时间", "支付/收款时间", "记账日期", "日期"))
            detail_fields = row.get("detail_fields")
            if isinstance(detail_fields, dict):
                candidates.extend(detail_fields.get(key) for key in ("交易时间", "支付/收款时间", "记账日期", "日期"))
        return candidates

    @staticmethod
    def _parse_oa_retention_date(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if len(text) < 10:
            return None
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _workbench_grouped_summary(payload: dict[str, object]) -> dict[str, int]:
        paired_groups = list(payload.get("paired", {}).get("groups", []))
        open_groups = list(payload.get("open", {}).get("groups", []))
        all_groups = [*paired_groups, *open_groups]
        return {
            "oa_count": sum(len(group.get("oa_rows", [])) for group in all_groups),
            "bank_count": sum(len(group.get("bank_rows", [])) for group in all_groups),
            "invoice_count": sum(len(group.get("invoice_rows", [])) for group in all_groups),
            "paired_count": len(paired_groups),
            "open_count": len(open_groups),
            "exception_count": sum(1 for group in open_groups if Application._group_has_danger_relation(group)),
        }

    @staticmethod
    def _group_has_danger_relation(group: dict[str, object]) -> bool:
        for key, relation_key in (
            ("oa_rows", "oa_bank_relation"),
            ("bank_rows", "invoice_relation"),
            ("invoice_rows", "invoice_bank_relation"),
        ):
            for row in group.get(key, []):
                relation = row.get(relation_key) if isinstance(row, dict) else None
                if isinstance(relation, dict) and str(relation.get("tone", "")) == "danger":
                    return True
        return False

    def _apply_pair_relations_to_payload(self, payload: dict[str, object]) -> dict[str, object]:
        result = self._serialize_value(payload)
        paired_section = result.setdefault("paired", {})
        open_section = result.setdefault("open", {})
        for row_type in ("oa", "bank", "invoice"):
            source_paired_rows = list(paired_section.get(row_type, []))
            source_open_rows = list(open_section.get(row_type, []))
            patched_paired_rows: list[dict[str, object]] = []
            patched_open_rows: list[dict[str, object]] = []
            for row in [*source_paired_rows, *source_open_rows]:
                relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(str(row.get("id", "")))
                if isinstance(relation, dict):
                    patched_paired_rows.append(self._apply_pair_relation_to_row(row, relation))
                elif row in source_paired_rows:
                    patched_paired_rows.append(self._serialize_value(row))
                else:
                    patched_open_rows.append(self._serialize_value(row))
            paired_section[row_type] = patched_paired_rows
            open_section[row_type] = patched_open_rows
        return result

    def _apply_candidate_matches_to_payload(self, payload: dict[str, object], month: str) -> dict[str, object]:
        result = self._serialize_value(payload)
        candidates = self._candidate_matches_for_scope(month)
        if not candidates:
            return result

        rows_by_id: dict[str, dict[str, object]] = {}
        for section_name in ("paired", "open"):
            section = result.get(section_name)
            if not isinstance(section, dict):
                continue
            for row_type in ("oa", "bank", "invoice"):
                for row in list(section.get(row_type) or []):
                    if isinstance(row, dict):
                        row_id = str(row.get("id") or row.get("row_id") or "").strip()
                        if row_id:
                            rows_by_id[row_id] = row

        claimed_row_ids: set[str] = set()
        for candidate in sorted(candidates, key=self._candidate_display_sort_key):
            if not isinstance(candidate, dict):
                continue
            row_ids = [
                str(row_id).strip()
                for row_id in list(candidate.get("row_ids") or [])
                if str(row_id).strip()
            ]
            if not row_ids:
                continue
            if any(self._row_has_manual_relation(rows_by_id.get(row_id)) for row_id in row_ids):
                continue
            if any(row_id in claimed_row_ids for row_id in row_ids):
                continue

            relation = self._candidate_relation_payload(candidate)
            case_id = str(candidate.get("candidate_key") or candidate.get("candidate_id") or "").strip()
            if not case_id:
                continue
            for row_id in row_ids:
                row = rows_by_id.get(row_id)
                if not isinstance(row, dict):
                    continue
                row["case_id"] = case_id
                relation_field = self._workbench_query_service.relation_field_name(str(row.get("type") or ""))
                row[relation_field] = self._serialize_value(relation)
                if str(candidate.get("rule_code") or "") == OA_INVOICE_OFFSET_AUTO_MATCH_MODE:
                    tags = [
                        str(tag).strip()
                        for tag in list(row.get("tags") or [])
                        if str(tag).strip()
                    ]
                    if OA_INVOICE_OFFSET_TAG not in tags:
                        tags.append(OA_INVOICE_OFFSET_TAG)
                    row["tags"] = tags
                    row["cost_excluded"] = True
            claimed_row_ids.update(row_ids)
        return result

    def _candidate_matches_for_scope(self, month: str) -> list[dict[str, object]]:
        normalized_month = str(month or "").strip()
        if SEARCH_MONTH_RE.match(normalized_month):
            return self._workbench_candidate_match_service.list_candidates_by_month(normalized_month)
        snapshot = self._workbench_candidate_match_service.snapshot()
        candidates = snapshot.get("candidates")
        if not isinstance(candidates, dict):
            return []
        return [
            self._serialize_value(candidate)
            for candidate in candidates.values()
            if isinstance(candidate, dict)
        ]

    @staticmethod
    def _candidate_display_sort_key(candidate: dict[str, object]) -> tuple[int, str, str]:
        status_priority = {
            "auto_closed": 0,
            "conflict": 1,
            "needs_review": 2,
            "incomplete": 3,
        }
        return (
            status_priority.get(str(candidate.get("status") or ""), 9),
            str(candidate.get("rule_code") or ""),
            str(candidate.get("candidate_key") or candidate.get("candidate_id") or ""),
        )

    def _candidate_relation_payload(self, candidate: dict[str, object]) -> dict[str, str]:
        status = str(candidate.get("status") or "").strip()
        rule_code = str(candidate.get("rule_code") or "").strip()
        if status == "auto_closed":
            if rule_code == "salary_personal_auto_match":
                return {"code": rule_code, "label": "已匹配：工资", "tone": "success"}
            if rule_code == "internal_transfer_pair":
                return {"code": rule_code, "label": "已匹配：内部往来款", "tone": "success"}
            if rule_code == OA_INVOICE_OFFSET_AUTO_MATCH_MODE:
                return {"code": rule_code, "label": "冲", "tone": "success"}
            return {"code": "automatic_match", "label": "自动匹配", "tone": "success"}
        if status == "conflict":
            return {"code": "candidate_conflict", "label": "候选冲突", "tone": "danger"}
        if status == "incomplete":
            return {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"}
        return {"code": "suggested_match", "label": "待人工确认", "tone": "warn"}

    def _row_has_manual_relation(self, row: dict[str, object] | None) -> bool:
        if not isinstance(row, dict):
            return False
        row_type = str(row.get("type") or "")
        try:
            relation_field = self._workbench_query_service.relation_field_name(row_type)
        except KeyError:
            return False
        relation = row.get(relation_field)
        return isinstance(relation, dict) and str(relation.get("code") or "") == "fully_linked"

    def _sync_oa_invoice_offset_auto_pair_relations(self, payload: dict[str, object]) -> None:
        desired_relations = self._oa_invoice_offset_desired_relations(payload)
        scanned_row_ids = self._raw_workbench_payload_row_ids(payload)
        active_auto_relations = {
            str(relation.get("case_id")): relation
            for relation in self._workbench_pair_relation_service.list_active_relations()
            if str(relation.get("relation_mode")) == OA_INVOICE_OFFSET_AUTO_MATCH_MODE
        }
        changed = False
        changed_case_ids: list[str] = []
        changed_scope_keys: set[str] = {"all"}

        for case_id, desired_relation in desired_relations.items():
            existing_relation = active_auto_relations.get(case_id)
            if (
                isinstance(existing_relation, dict)
                and list(existing_relation.get("row_ids") or []) == desired_relation["row_ids"]
                and str(existing_relation.get("relation_mode")) == OA_INVOICE_OFFSET_AUTO_MATCH_MODE
                and str(existing_relation.get("month_scope")) == str(desired_relation["month_scope"])
                and str(existing_relation.get("status")) == "active"
            ):
                continue
            self._workbench_pair_relation_service.create_active_relation(
                case_id=case_id,
                row_ids=list(desired_relation["row_ids"]),
                row_types=list(desired_relation["row_types"]),
                relation_mode=OA_INVOICE_OFFSET_AUTO_MATCH_MODE,
                created_by="system_auto_match",
                month_scope=str(desired_relation["month_scope"]),
            )
            changed = True
            changed_case_ids.append(case_id)
            if str(desired_relation["month_scope"]) != "all":
                changed_scope_keys.add(str(desired_relation["month_scope"]))

        for case_id in sorted(set(active_auto_relations).difference(desired_relations)):
            relation_row_ids = {str(row_id) for row_id in list(active_auto_relations[case_id].get("row_ids") or [])}
            if not scanned_row_ids or not relation_row_ids.intersection(scanned_row_ids):
                continue
            self._workbench_pair_relation_service.cancel_relation(case_id)
            changed = True
            changed_case_ids.append(case_id)
            month_scope = str(active_auto_relations[case_id].get("month_scope", ""))
            if month_scope and month_scope != "all":
                changed_scope_keys.add(month_scope)

        if not changed:
            return
        self._search_service.clear_cache()
        self._invalidate_workbench_read_model_scopes(list(changed_scope_keys))
        self._persist_workbench_pair_relations(changed_case_ids=changed_case_ids)

    @staticmethod
    def _raw_workbench_payload_row_ids(payload: dict[str, object]) -> set[str]:
        row_ids: set[str] = set()
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for pane in ("oa", "bank", "invoice"):
                for row in list(section_payload.get(pane, [])):
                    if isinstance(row, dict) and str(row.get("id", "")).strip():
                        row_ids.add(str(row.get("id", "")).strip())
        return row_ids

    def _oa_invoice_offset_desired_relations(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        applicant_names = {
            str(name).strip()
            for name in self._app_settings_service.get_oa_invoice_offset_applicant_names()
            if str(name).strip()
        }
        if not applicant_names:
            return {}

        oa_rows: list[dict[str, object]] = []
        invoice_rows: list[dict[str, object]] = []
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            oa_rows.extend(
                self._serialize_value(row)
                for row in list(section_payload.get("oa", []))
                if isinstance(row, dict)
            )
            invoice_rows.extend(
                self._serialize_value(row)
                for row in list(section_payload.get("invoice", []))
                if isinstance(row, dict)
            )

        desired_relations: dict[str, dict[str, object]] = {}
        for oa_row in oa_rows:
            if str(oa_row.get("applicant", "")).strip() not in applicant_names:
                continue
            attachment_invoice_rows = self._oa_attachment_invoice_rows_for_oa(oa_row, invoice_rows)
            if not attachment_invoice_rows:
                continue
            row_ids = [
                str(oa_row.get("id", "")).strip(),
                *[
                    str(invoice_row.get("id", "")).strip()
                    for invoice_row in attachment_invoice_rows
                    if str(invoice_row.get("id", "")).strip()
                ],
            ]
            row_ids = [row_id for row_id in row_ids if row_id]
            if len(row_ids) < 2 or self._auto_pair_conflicts_with_manual_relation(row_ids):
                continue
            case_id = str(oa_row.get("case_id") or f"CASE-OA-OFFSET-{row_ids[0]}").strip()
            month_scope = self._month_scope_for_oa_invoice_offset_relation([oa_row, *attachment_invoice_rows])
            desired_relations[case_id] = {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": ["oa", *(["invoice"] * (len(row_ids) - 1))],
                "month_scope": month_scope,
            }
        return desired_relations

    @staticmethod
    def _oa_attachment_invoice_rows_for_oa(
        oa_row: dict[str, object],
        invoice_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        oa_row_id = str(oa_row.get("id", "")).strip()
        case_id = str(oa_row.get("case_id", "")).strip()
        matches: list[dict[str, object]] = []
        for invoice_row in invoice_rows:
            if str(invoice_row.get("source_kind", "")) != "oa_attachment_invoice":
                continue
            derived_from_oa_id = str(invoice_row.get("derived_from_oa_id", "")).strip()
            invoice_case_id = str(invoice_row.get("case_id", "")).strip()
            if derived_from_oa_id == oa_row_id or (case_id and invoice_case_id == case_id):
                matches.append(invoice_row)
        return matches

    def _month_scope_for_oa_invoice_offset_relation(self, rows: list[dict[str, object]]) -> str:
        row_months = {self._row_month_scope(row) for row in rows}
        normalized_months = {month for month in row_months if month}
        if len(normalized_months) == 1:
            return next(iter(normalized_months))
        return "all"

    def _apply_pair_relation_to_row(self, row: dict[str, object], relation: dict[str, object]) -> dict[str, object]:
        payload = self._serialize_value(row)
        payload["case_id"] = str(relation.get("case_id", ""))
        relation_field = self._workbench_override_service.relation_field_name(str(payload["type"]))
        relation_mode = str(relation.get("relation_mode", ""))
        linked_relation = self._pair_relation_display_payload(
            relation_mode=relation_mode,
            row_type=str(payload.get("type", "")),
        )
        payload[relation_field] = self._serialize_value(linked_relation)
        self._workbench_override_service._sync_summary_relation(payload, str(linked_relation.get("label", "")))
        if relation_mode == OA_INVOICE_OFFSET_AUTO_MATCH_MODE:
            self._apply_oa_invoice_offset_pair_metadata(payload)
        if relation_mode == "internal_transfer_pair" and str(payload.get("type")) == "bank":
            self._apply_internal_transfer_pair_metadata(payload, relation)
        payload["available_actions"] = ["detail"]
        payload["handled_exception"] = False
        return payload

    def _invalidate_workbench_read_models(self, *, invalidate_cost_statistics: bool = True) -> None:
        snapshot = self._workbench_read_model_service.snapshot()
        for scope_key in list(snapshot.get("read_models", {}).keys()):
            self._workbench_read_model_service.delete_read_model(str(scope_key))
        if invalidate_cost_statistics:
            self._invalidate_cost_statistics_read_models()

    def _invalidate_workbench_read_model_scopes(self, scope_keys: list[str]) -> list[str]:
        normalized_scope_keys = {
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        }
        expanded_scope_keys = self._expand_workbench_read_model_scope_keys_for_base_scopes(list(normalized_scope_keys))
        for scope_key in expanded_scope_keys:
            self._workbench_read_model_service.delete_read_model(scope_key)
        self._invalidate_cost_statistics_read_model_scopes(
            list(normalized_scope_keys),
            reason="workbench_scope_invalidated",
        )
        return expanded_scope_keys

    def _invalidate_cost_statistics_read_models(self) -> list[str]:
        read_model_service = self._cost_statistics_read_model_service
        if read_model_service is None:
            return []
        deleted_scope_keys = read_model_service.clear()
        self._persist_cost_statistics_read_models_best_effort(
            snapshot=read_model_service.snapshot(),
            changed_scope_keys=deleted_scope_keys,
            operation="invalidate_cost_statistics_read_models",
        )
        if not deleted_scope_keys:
            return deleted_scope_keys
        warmup_months = self._cost_statistics_warmup_months_from_read_model_scope_keys(deleted_scope_keys)
        if not warmup_months:
            warmup_months = ["all"]
        self._schedule_cost_statistics_cache_warmup(warmup_months, reason="cost_statistics_read_model_invalidated")
        return deleted_scope_keys

    def _invalidate_cost_statistics_read_model_scopes(
        self,
        scope_keys: list[str],
        *,
        reason: str = "",
    ) -> list[str]:
        read_model_service = self._cost_statistics_read_model_service
        if read_model_service is None:
            return []
        months = self._cost_statistics_months_from_workbench_scope_keys(scope_keys)
        if not months:
            return []
        specific_months = sorted(month for month in months if month != "all")
        if specific_months:
            deleted_scope_keys = read_model_service.invalidate_months(
                specific_months,
                project_scopes=["active", "all"],
                include_all=True,
            )
            warmup_months = [*specific_months, "all"]
        else:
            deleted_scope_keys = read_model_service.invalidate_months(
                [],
                project_scopes=["active", "all"],
                include_all=True,
            )
            warmup_months = ["all"]
        self._persist_cost_statistics_read_models_best_effort(
            snapshot=read_model_service.snapshot(),
            changed_scope_keys=deleted_scope_keys,
            operation=reason or "invalidate_cost_statistics_read_model_scopes",
        )
        self._schedule_cost_statistics_cache_warmup(
            warmup_months,
            reason=reason or "cost_statistics_scope_invalidated",
        )
        return deleted_scope_keys

    @staticmethod
    def _cost_statistics_months_from_workbench_scope_keys(scope_keys: list[str]) -> set[str]:
        months: set[str] = set()
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key).strip()
            if not scope_key:
                continue
            for part in reversed(scope_key.split(":")):
                normalized_part = str(part).strip()
                if normalized_part == "all" or SEARCH_MONTH_RE.match(normalized_part):
                    months.add(normalized_part)
                    break
        return months

    def _cost_statistics_warmup_months_from_read_model_scope_keys(self, scope_keys: list[str]) -> list[str]:
        months = self._cost_statistics_months_from_workbench_scope_keys(scope_keys)
        specific_months = sorted(month for month in months if month != "all")
        if specific_months:
            return [*specific_months, "all"]
        if "all" in months:
            return ["all"]
        return []

    def _cost_statistics_read_model_scope_key(
        self,
        month: str,
        project_scope: str,
        *,
        read_model: dict[str, object] | None = None,
    ) -> str:
        if isinstance(read_model, dict):
            scope_key = str(read_model.get("scope_key", "")).strip()
            if scope_key:
                return scope_key
        return str(self._cost_statistics_read_model_service.scope_key(month, project_scope))

    def _schedule_cost_statistics_cache_warmup(self, months: list[str], reason: str) -> None:
        read_model_service = self._cost_statistics_read_model_service
        if read_model_service is None:
            return
        normalized_months = {
            str(month).strip()
            for month in list(months or [])
            if str(month).strip()
        }
        if not normalized_months:
            return
        ordered_months = sorted((month for month in normalized_months if month != "all"), reverse=True)
        if "all" in normalized_months or ordered_months:
            ordered_months.append("all")
        deduped_months = list(dict.fromkeys(ordered_months))
        project_scopes = ["active", "all"]
        affected_scope_keys = [
            self._cost_statistics_read_model_scope_key(month, project_scope)
            for month in deduped_months
            for project_scope in project_scopes
        ]
        idempotency_key = f"cost_statistics_cache_warmup:{reason}:{','.join(deduped_months)}"
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="cost_statistics_cache_warmup",
            label="预热成本统计缓存",
            owner_user_id="system",
            idempotency_key=idempotency_key,
            visibility="system",
            phase="queued",
            current=0,
            total=len(affected_scope_keys),
            message="成本统计缓存预热任务已创建。",
            result_summary={"warmed": 0, "failed": 0},
            source={"reason": reason},
            affected_scopes=affected_scope_keys,
            affected_months=deduped_months,
        )
        if not created:
            return
        self._background_job_service.run_job(
            job,
            lambda running_job: self._run_cost_statistics_cache_warmup_job(
                running_job,
                months=deduped_months,
                project_scopes=project_scopes,
            ),
        )

    def _run_cost_statistics_cache_warmup_job(
        self,
        running_job,
        *,
        months: list[str],
        project_scopes: list[str],
    ) -> dict[str, object]:
        read_model_service = self._cost_statistics_read_model_service
        if read_model_service is None:
            return {"warmed": 0, "failed": 0}
        targets = [
            (month, project_scope)
            for month in list(months or [])
            for project_scope in list(project_scopes or [])
        ]
        total = len(targets)
        warmed_scope_keys: list[str] = []
        failed_scope_keys: list[str] = []
        for index, (month, project_scope) in enumerate(targets, start=1):
            scope_key = self._cost_statistics_read_model_scope_key(month, project_scope)
            self._background_job_service.update_progress(
                running_job.job_id,
                phase="build_cost_statistics_cache",
                message=f"正在预热成本统计缓存 {index}/{max(total, 1)}。",
                current=index - 1,
                total=total,
                result_summary={"warmed": len(warmed_scope_keys), "failed": len(failed_scope_keys)},
            )
            try:
                payload = self._cost_statistics_service.get_explorer(
                    month,
                    project_scope=project_scope,
                )
            except Exception:
                failed_scope_keys.append(scope_key)
                continue
            read_model = read_model_service.upsert_read_model(
                month,
                project_scope,
                payload,
                generated_at=datetime.now().isoformat(),
                source_scope_keys=[month],
                cache_status="ready",
            )
            warmed_scope_key = self._cost_statistics_read_model_scope_key(
                month,
                project_scope,
                read_model=read_model,
            )
            warmed_scope_keys.append(warmed_scope_key)
            self._persist_cost_statistics_read_models_best_effort(
                snapshot=read_model_service.snapshot_scope_keys([warmed_scope_key]),
                changed_scope_keys=[warmed_scope_key],
                operation="cost_statistics_cache_warmup",
            )

        result_summary = {
            "warmed": len(warmed_scope_keys),
            "failed": len(failed_scope_keys),
        }
        message = "成本统计缓存预热完成。" if not failed_scope_keys else "成本统计缓存预热部分完成。"
        self._background_job_service.succeed_job(
            running_job.job_id,
            message,
            result_summary=result_summary,
            status="partial_success" if failed_scope_keys else "succeeded",
        )
        return result_summary

    def _invalidate_tax_offset_read_models(self) -> list[str]:
        self._tax_offset_service.clear_month_cache()
        read_model_service = self._tax_offset_read_model_service
        if read_model_service is None:
            return []
        deleted_scope_keys = read_model_service.clear()
        self._persist_tax_offset_read_models_best_effort(
            snapshot=read_model_service.snapshot(),
            changed_scope_keys=deleted_scope_keys,
            operation="invalidate_tax_offset_read_models",
        )
        warmup_months = self._tax_offset_warmup_months_from_scope_keys(deleted_scope_keys)
        if not warmup_months:
            warmup_months = self._default_tax_offset_warmup_months()
        self._schedule_tax_offset_cache_warmup(warmup_months, reason="tax_offset_read_model_invalidated")
        return deleted_scope_keys

    def _invalidate_tax_offset_read_model_scopes(
        self,
        scope_keys: list[str],
        *,
        reason: str = "",
    ) -> list[str]:
        months = self._tax_offset_months_from_scope_keys(scope_keys)
        if not months:
            return []
        ordered_months = sorted(months)
        self._tax_offset_service.clear_month_cache(ordered_months)
        read_model_service = self._tax_offset_read_model_service
        deleted_scope_keys: list[str] = []
        if read_model_service is not None:
            deleted_scope_keys = read_model_service.invalidate_months(ordered_months)
            self._persist_tax_offset_read_models_best_effort(
                snapshot=read_model_service.snapshot(),
                changed_scope_keys=deleted_scope_keys,
                operation=reason or "invalidate_tax_offset_read_model_scopes",
            )
        self._schedule_tax_offset_cache_warmup(
            ordered_months,
            reason=reason or "tax_offset_scope_invalidated",
        )
        return deleted_scope_keys

    @staticmethod
    def _tax_offset_months_from_scope_keys(scope_keys: list[str]) -> set[str]:
        months: set[str] = set()
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key).strip()
            if SEARCH_MONTH_RE.match(scope_key):
                months.add(scope_key)
        return months

    @staticmethod
    def _tax_offset_warmup_months_from_scope_keys(scope_keys: list[str]) -> list[str]:
        return sorted(
            {
                str(scope_key).strip()
                for scope_key in list(scope_keys or [])
                if SEARCH_MONTH_RE.match(str(scope_key).strip())
            }
        )

    @staticmethod
    def _default_tax_offset_warmup_months() -> list[str]:
        current_month = datetime.now().strftime("%Y-%m")
        current_year = int(current_month[:4])
        current_month_number = int(current_month[5:7])
        if current_month_number == 1:
            previous_month = f"{current_year - 1}-12"
        else:
            previous_month = f"{current_year}-{current_month_number - 1:02d}"
        return [previous_month, current_month]

    def _tax_offset_read_model_scope_key(
        self,
        month: str,
        *,
        read_model: dict[str, object] | None = None,
    ) -> str:
        if isinstance(read_model, dict):
            scope_key = str(read_model.get("scope_key", "")).strip()
            if scope_key:
                return scope_key
        return str(self._tax_offset_read_model_service.scope_key(month))

    def _schedule_tax_offset_cache_warmup(self, months: list[str], reason: str) -> None:
        read_model_service = self._tax_offset_read_model_service
        if read_model_service is None:
            return
        if not self._tax_offset_cache_warmup_enabled():
            return
        deduped_months = sorted(
            {
                str(month).strip()
                for month in list(months or [])
                if SEARCH_MONTH_RE.match(str(month).strip())
            },
            reverse=True,
        )
        if not deduped_months:
            return
        affected_scope_keys = [self._tax_offset_read_model_scope_key(month) for month in deduped_months]
        idempotency_key = f"tax_offset_cache_warmup:{reason}:{','.join(deduped_months)}"
        job, created = self._background_job_service.create_or_get_idempotent_job_with_created(
            job_type="tax_offset_cache_warmup",
            label="预热税金抵扣缓存",
            owner_user_id="system",
            idempotency_key=idempotency_key,
            visibility="system",
            phase="queued",
            current=0,
            total=len(affected_scope_keys),
            message="税金抵扣缓存预热任务已创建。",
            result_summary={"warmed": 0, "failed": 0},
            source={"reason": reason},
            affected_scopes=affected_scope_keys,
            affected_months=deduped_months,
        )
        if not created:
            return
        self._background_job_service.run_job(
            job,
            lambda running_job: self._run_tax_offset_cache_warmup_job(
                running_job,
                months=deduped_months,
            ),
        )

    def _run_tax_offset_cache_warmup_job(
        self,
        running_job,
        *,
        months: list[str],
    ) -> dict[str, object]:
        read_model_service = self._tax_offset_read_model_service
        if read_model_service is None:
            return {"warmed": 0, "failed": 0}
        warmed_scope_keys: list[str] = []
        failed_scope_keys: list[str] = []
        total = len(list(months or []))
        for index, month in enumerate(list(months or []), start=1):
            scope_key = self._tax_offset_read_model_scope_key(month)
            self._background_job_service.update_progress(
                running_job.job_id,
                phase="build_tax_offset_cache",
                message=f"正在预热税金抵扣缓存 {index}/{max(total, 1)}。",
                current=index - 1,
                total=total,
                result_summary={"warmed": len(warmed_scope_keys), "failed": len(failed_scope_keys)},
            )
            try:
                payload = self._tax_api_routes.get_tax_offset(month)
            except Exception:
                failed_scope_keys.append(scope_key)
                continue
            read_model = read_model_service.upsert_read_model(
                month,
                payload,
                generated_at=datetime.now().isoformat(),
                source_scope_keys=[month],
                cache_status="ready",
            )
            warmed_scope_key = self._tax_offset_read_model_scope_key(month, read_model=read_model)
            warmed_scope_keys.append(warmed_scope_key)
            self._persist_tax_offset_read_models_best_effort(
                snapshot=read_model_service.snapshot_scope_keys([warmed_scope_key]),
                changed_scope_keys=[warmed_scope_key],
                operation="tax_offset_cache_warmup",
            )

        result_summary = {
            "warmed": len(warmed_scope_keys),
            "failed": len(failed_scope_keys),
        }
        message = "税金抵扣缓存预热完成。" if not failed_scope_keys else "税金抵扣缓存预热部分完成。"
        self._background_job_service.succeed_job(
            running_job.job_id,
            message,
            result_summary=result_summary,
            status="partial_success" if failed_scope_keys else "succeeded",
        )
        return result_summary

    @staticmethod
    def _tax_offset_cache_warmup_enabled() -> bool:
        return os.getenv("FIN_OPS_TAX_OFFSET_CACHE_WARMUP_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

    def _scope_keys_for_row_ids(
        self,
        *,
        month: str,
        row_ids: list[str],
        month_scope: str | None = None,
    ) -> set[str]:
        scope_keys = {"all"}
        if month and month != "all":
            scope_keys.add(month)
        if month_scope and month_scope != "all":
            scope_keys.add(month_scope)
        for row_id in row_ids:
            row_month = self._row_month_scope_from_row_id(row_id)
            if row_month:
                scope_keys.add(row_month)
        return scope_keys

    def _scope_keys_for_rows(
        self,
        *,
        month: str,
        rows: list[dict[str, object]],
    ) -> list[str]:
        scope_keys = {"all"}
        if month and month != "all":
            scope_keys.add(month)
        for row in rows:
            row_month = self._row_month_scope(row)
            if row_month:
                scope_keys.add(row_month)
        return list(scope_keys)

    @staticmethod
    def _row_month_scope_from_row_id(row_id: str) -> str | None:
        match = ROW_ID_MONTH_RE.search(str(row_id))
        if match is not None:
            return f"{match.group(1)}-{match.group(2)}"
        return None

    def _row_month_scope(self, row: dict[str, object]) -> str | None:
        row_type = str(row.get("type", ""))
        if row_type == "bank":
            for value in (row.get("trade_time"), row.get("pay_receive_time")):
                resolved_month = self._normalize_month_from_value(value)
                if resolved_month is not None:
                    return resolved_month
        elif row_type == "invoice":
            resolved_month = self._normalize_month_from_value(row.get("issue_date"))
            if resolved_month is not None:
                return resolved_month
        elif row_type == "oa":
            summary_fields = row.get("summary_fields")
            if isinstance(summary_fields, dict):
                for key in ("申请日期", "日期"):
                    resolved_month = self._normalize_month_from_value(summary_fields.get(key))
                    if resolved_month is not None:
                        return resolved_month
            detail_fields = row.get("detail_fields")
            if isinstance(detail_fields, dict):
                for key in ("申请日期", "单据日期"):
                    resolved_month = self._normalize_month_from_value(detail_fields.get(key))
                    if resolved_month is not None:
                        return resolved_month
        return self._row_month_scope_from_row_id(str(row.get("id", "")))

    @staticmethod
    def _normalize_month_from_value(value: object) -> str | None:
        if value in (None, ""):
            return None
        resolved = str(value).strip()
        if len(resolved) >= 7 and resolved[4] == "-" and resolved[5:7].isdigit():
            return resolved[:7]
        return None

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

    def _resolve_rows_for_amount_check(
        self,
        row_ids: list[str],
        *,
        month: str,
        allow_direct: bool,
    ) -> list[dict[str, object]]:
        resolved = self._resolve_rows_from_cached_read_models(row_ids, month_hint=month)
        rows: list[dict[str, object]] = []
        missing: list[str] = []
        for row_id in row_ids:
            row = resolved.get(row_id)
            if row is None:
                missing.append(row_id)
            else:
                rows.append(row)
        if missing and allow_direct:
            try:
                rows.extend(self._resolve_live_rows_direct(missing, month_hint=month))
            except KeyError:
                rows.extend({"id": row_id, "type": self._row_type_for_row_id(row_id)} for row_id in missing)
            missing = []
        for row_id in missing:
            rows.append({"id": row_id, "type": self._row_type_for_row_id(row_id)})
        return rows

    @staticmethod
    def _rows_by_type(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        rows_by_type: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type", ""))
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type

    def _amount_check_for_row_ids(self, row_ids: list[str], *, month: str, allow_direct: bool) -> dict[str, object]:
        rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=allow_direct)
        return self._amount_check_for_rows_by_type(self._rows_by_type(rows))

    def _amount_check_for_rows_by_type(self, rows_by_type: dict[str, list[dict[str, object]]]) -> dict[str, object]:
        amount_check = self._workbench_amount_check_service.check(rows_by_type)
        if (
            amount_check.get("status") == "unknown"
            and amount_check.get("oa_total") is None
            and amount_check.get("bank_total") is None
            and amount_check.get("invoice_total") is None
        ):
            amount_check["status"] = "matched"
            amount_check["direction"] = "unknown"
            amount_check["requires_note"] = False
        return amount_check

    def _can_confirm_link_row_types(self, *, row_ids: list[str], row_types: list[str], month: str) -> bool:
        known_types = {row_type for row_type in row_types if row_type != "unknown"}
        if len(known_types) >= 2:
            return True
        if known_types == {"bank"}:
            return self._is_balanced_bank_only_selection(row_ids=row_ids, month=month)
        return False

    def _resolved_row_types_for_row_ids(self, row_ids: list[str], *, month: str) -> list[str]:
        fallback_types = self._row_types_for_row_ids(row_ids)
        if "unknown" not in fallback_types:
            return fallback_types
        rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
        rows_by_id = {str(row.get("id", "")): row for row in rows}
        resolved_types: list[str] = []
        for index, row_id in enumerate(row_ids):
            row_type = str(rows_by_id.get(row_id, {}).get("type") or fallback_types[index])
            resolved_types.append(row_type if row_type else "unknown")
        return resolved_types

    def _is_balanced_bank_only_selection(self, *, row_ids: list[str], month: str) -> bool:
        if len(row_ids) < 2:
            return False
        rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
        debit_total = Decimal("0.00")
        credit_total = Decimal("0.00")
        has_debit = False
        has_credit = False
        for row in rows:
            if str(row.get("type", "")) != "bank":
                return False
            debit = self._decimal_from_value(row.get("debit_amount"))
            credit = self._decimal_from_value(row.get("credit_amount"))
            if debit is not None and debit > 0:
                debit_total += debit
                has_debit = True
            if credit is not None and credit > 0:
                credit_total += credit
                has_credit = True
        return has_debit and has_credit and debit_total == credit_total

    def _relation_groups(
        self,
        relations: list[dict[str, object]],
        *,
        selected_rows: list[dict[str, object]],
        ungrouped_selected_rows: str = "single",
    ) -> list[dict[str, object]]:
        rows_by_id = {str(row.get("id", "")): self._serialize_value(row) for row in selected_rows}
        groups: list[dict[str, object]] = []
        grouped_row_ids: set[str] = set()
        for relation in relations:
            group = {
                "group_id": f"case:{relation.get('case_id', '')}",
                "group_type": str(relation.get("relation_mode") or "manual_confirmed"),
                "match_confidence": "high",
                "reason": "relation_snapshot",
                "oa_rows": [],
                "bank_rows": [],
                "invoice_rows": [],
            }
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            for index, row_id in enumerate(row_ids):
                grouped_row_ids.add(row_id)
                row_type = row_types[index] if index < len(row_types) else self._row_type_for_row_id(row_id)
                row = dict(rows_by_id.get(row_id) or {"id": row_id, "type": row_type})
                row["case_id"] = str(relation.get("case_id") or "")
                row["tags"] = self._derive_workbench_row_tags(row, group, relation)
                if row_type == "oa":
                    group["oa_rows"].append(row)
                elif row_type == "bank":
                    group["bank_rows"].append(row)
                elif row_type == "invoice":
                    group["invoice_rows"].append(row)
            groups.append(group)
        ungrouped_rows = [
            row
            for row in selected_rows
            if str(row.get("id", "")).strip() and str(row.get("id", "")).strip() not in grouped_row_ids
        ]
        if ungrouped_selected_rows == "separate":
            selected_groups: dict[str, dict[str, object]] = {str(group.get("group_id", "")): group for group in groups}
            for row in ungrouped_rows:
                row_id = str(row.get("id", "")).strip()
                case_id = str(row.get("case_id") or "").strip()
                group_id = f"case:{case_id}" if case_id else f"selected:{row_id}"
                group = selected_groups.get(group_id)
                if group is None:
                    group = {
                        "group_id": group_id,
                        "group_type": "selection",
                        "match_confidence": "low",
                        "reason": "selected_existing_case" if case_id else "selected_row",
                        "oa_rows": [],
                        "bank_rows": [],
                        "invoice_rows": [],
                    }
                    selected_groups[group_id] = group
                    groups.append(group)
                row_type = str(row.get("type", ""))
                if row_type == "oa":
                    group["oa_rows"].append(row)
                elif row_type == "bank":
                    group["bank_rows"].append(row)
                elif row_type == "invoice":
                    group["invoice_rows"].append(row)
        elif not groups and ungrouped_rows:
            group = {
                "group_id": "selected",
                "group_type": "selection",
                "match_confidence": "low",
                "reason": "selected_rows",
                "oa_rows": [],
                "bank_rows": [],
                "invoice_rows": [],
            }
            for row in ungrouped_rows:
                row_type = str(row.get("type", ""))
                if row_type == "oa":
                    group["oa_rows"].append(row)
                elif row_type == "bank":
                    group["bank_rows"].append(row)
                elif row_type == "invoice":
                    group["invoice_rows"].append(row)
            groups.append(group)
        return groups

    def _withdraw_rows_and_after_relations(
        self,
        *,
        active_relation: dict[str, object],
        after_relations: list[dict[str, object]],
        month: str,
    ) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
        affected_row_ids = self._normalize_row_ids(
            [
                *list(active_relation.get("row_ids") or []),
                *[row_id for relation in after_relations for row_id in list(relation.get("row_ids") or [])],
            ]
        )
        rows = self._resolve_rows_for_amount_check(affected_row_ids, month=month, allow_direct=True)
        if after_relations:
            return rows, after_relations, affected_row_ids

        inferred_relations = self._infer_oa_attachment_withdraw_relations(
            active_relation=active_relation,
            rows=rows,
        )
        if inferred_relations:
            affected_row_ids = self._normalize_row_ids(
                [
                    *affected_row_ids,
                    *[row_id for relation in inferred_relations for row_id in list(relation.get("row_ids") or [])],
                ]
            )
        return rows, inferred_relations, affected_row_ids

    def _infer_oa_attachment_withdraw_relations(
        self,
        *,
        active_relation: dict[str, object],
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        active_row_ids = {
            str(row_id).strip()
            for row_id in list(active_relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        oa_row_ids = [
            str(row.get("id", "")).strip()
            for row in rows
            if str(row.get("id", "")).strip() in active_row_ids and str(row.get("type", "")) == "oa"
        ]
        if not oa_row_ids:
            return []

        invoice_ids_by_oa_id: dict[str, list[str]] = {}
        for row in rows:
            invoice_id = str(row.get("id", "")).strip()
            is_invoice_row = str(row.get("type", "")) == "invoice" or invoice_id.startswith("oa-att-inv-")
            if invoice_id not in active_row_ids or not is_invoice_row:
                continue
            source_oa_id = self._oa_id_from_attachment_invoice_id(invoice_id, oa_row_ids)
            if source_oa_id:
                invoice_ids_by_oa_id.setdefault(source_oa_id, []).append(invoice_id)

        month_scope = str(active_relation.get("month_scope") or "all")
        inferred_relations: list[dict[str, object]] = []
        for oa_row_id in oa_row_ids:
            invoice_ids = invoice_ids_by_oa_id.get(oa_row_id, [])
            if not invoice_ids:
                continue
            inferred_relations.append(
                {
                    "case_id": f"CASE-OA-ATT-{oa_row_id}",
                    "row_ids": [oa_row_id, *invoice_ids],
                    "row_types": ["oa", *(["invoice"] * len(invoice_ids))],
                    "status": "active",
                    "relation_mode": "oa_attachment_invoice",
                    "month_scope": month_scope,
                }
            )
        return inferred_relations

    @staticmethod
    def _oa_id_from_attachment_invoice_id(invoice_id: str, oa_row_ids: list[str]) -> str | None:
        prefix = "oa-att-inv-"
        if not invoice_id.startswith(prefix):
            return None
        tail = invoice_id[len(prefix):]
        for oa_row_id in sorted(oa_row_ids, key=len, reverse=True):
            if tail == oa_row_id or tail.startswith(f"{oa_row_id}-"):
                return oa_row_id
        return None

    def _synthetic_existing_case_relations(
        self,
        rows: list[dict[str, object]],
        *,
        existing_relations: list[dict[str, object]],
        month_scope: str,
    ) -> list[dict[str, object]]:
        covered_row_ids = {
            str(row_id).strip()
            for relation in existing_relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        rows_by_case_id: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            row_id = str(row.get("id", "")).strip()
            case_id = str(row.get("case_id") or "").strip()
            if not row_id or not case_id or row_id in covered_row_ids:
                continue
            rows_by_case_id.setdefault(case_id, []).append(row)

        relations: list[dict[str, object]] = []
        for case_id, case_rows in rows_by_case_id.items():
            if len(case_rows) < 2:
                continue
            relations.append(
                {
                    "case_id": case_id,
                    "row_ids": [str(row.get("id", "")).strip() for row in case_rows],
                    "row_types": [str(row.get("type", "")).strip() for row in case_rows],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": month_scope,
                }
            )
        return relations

    @staticmethod
    def _merge_relation_snapshots(
        primary_relations: list[dict[str, object]],
        secondary_relations: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        merged: dict[str, dict[str, object]] = {}
        for relation in [*primary_relations, *secondary_relations]:
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id:
                continue
            merged[case_id] = relation
        return list(merged.values())

    def _derive_tags_for_grouped_payload(self, payload: dict[str, object]) -> dict[str, object]:
        result = self._serialize_value(payload)
        for section in ("paired", "open"):
            section_payload = result.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for group in list(section_payload.get("groups", [])):
                if not isinstance(group, dict):
                    continue
                relation = self._relation_for_group(group)
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    for row in list(group.get(key, [])):
                        if isinstance(row, dict):
                            row["tags"] = self._derive_workbench_row_tags(row, group, relation)
        return result

    def _relation_for_group(self, group: dict[str, object]) -> dict[str, object] | None:
        for key in ("oa_rows", "bank_rows", "invoice_rows"):
            for row in list(group.get(key, [])):
                if not isinstance(row, dict):
                    continue
                relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(str(row.get("id", "")))
                if isinstance(relation, dict):
                    return relation
        return None

    def _derive_workbench_row_tags(
        self,
        row: dict[str, object],
        group: dict[str, object],
        relation: dict[str, object] | None,
    ) -> list[str]:
        tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
        visible: list[str] = []

        def add(tag: str) -> None:
            if tag and tag not in visible:
                visible.append(tag)

        has_oa = bool(group.get("oa_rows"))
        has_bank = bool(group.get("bank_rows"))
        has_invoice = bool(group.get("invoice_rows"))
        has_etc_batch_oa = self._group_has_etc_batch_oa(group)
        if has_oa and has_invoice and not has_bank:
            add("待找流水")
        elif has_oa and has_bank and not has_invoice:
            if not has_etc_batch_oa:
                add("待找发票")
        elif has_oa and not has_bank and not has_invoice:
            add("待找流水" if has_etc_batch_oa else "待找流水与发票")
        elif has_bank and has_invoice and not has_oa:
            add("待找OA")

        amount_check = relation.get("amount_check") if isinstance(relation, dict) else None
        if isinstance(amount_check, dict) and str(amount_check.get("status")) == "mismatch":
            add("金额不一致")

        row_type = str(row.get("type", ""))
        if row_type == "invoice":
            if str(row.get("source_kind", "")) == "oa_attachment_invoice":
                add("OA附件")
            else:
                add("人工导入")
            invoice_type = str(row.get("invoice_type") or "")
            add("销" if "销" in invoice_type or invoice_type == "output" else "进")
        elif row_type == "bank":
            debit = self._decimal_from_value(row.get("debit_amount"))
            credit = self._decimal_from_value(row.get("credit_amount"))
            if credit is not None and credit > 0:
                add("收")
            elif debit is not None and debit > 0:
                add("支")

        relation_mode = str(relation.get("relation_mode")) if isinstance(relation, dict) else ""
        if relation_mode == "internal_transfer_pair":
            add("内部往来")
        if relation_mode == "salary_personal_auto_match":
            add("工资")
        for tag in tags:
            if tag in {"ETC批量提交", "冲", "内部往来", "工资", "非税"}:
                add(tag)
        if any(str(row.get(key, "")).find("非税") >= 0 for key in ("summary", "remark", "reason", "purpose")):
            add("非税")
        return visible

    @staticmethod
    def _group_has_etc_batch_oa(group: dict[str, object]) -> bool:
        for row in list(group.get("oa_rows") or []):
            if isinstance(row, dict) and Application._is_etc_batch_oa_row(row):
                return True
        return False

    @staticmethod
    def _is_etc_batch_oa_row(row: dict[str, object]) -> bool:
        if str(row.get("source", "")).strip() == "etc_batch":
            return True
        if str(row.get("etc_batch_id") or row.get("etcBatchId") or "").strip():
            return True
        tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
        return "ETC批量提交" in tags

    @staticmethod
    def _decimal_from_value(value: object) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", ""))
        except Exception:
            return None

    def _group_for_row_id(self, payload: dict[str, object], row_id: str) -> dict[str, object] | None:
        for section in ("paired", "open"):
            section_payload = payload.get(section, {})
            for group in section_payload.get("groups", []):
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    if any(str(row["id"]) == row_id for row in group.get(key, [])):
                        return group
        return None

    def _resolve_live_row_direct(self, row_id: str, *, month_hint: str | None = None) -> dict[str, object]:
        return self._resolve_live_rows_direct([row_id], month_hint=month_hint)[0]

    @staticmethod
    def _normalize_row_ids(row_ids: list[object]) -> list[str]:
        normalized_row_ids: list[str] = []
        seen_row_ids: set[str] = set()
        for row_id in row_ids:
            if row_id is None:
                continue
            normalized_row_id = str(row_id).strip()
            if not normalized_row_id or normalized_row_id in seen_row_ids:
                continue
            seen_row_ids.add(normalized_row_id)
            normalized_row_ids.append(normalized_row_id)
        if not normalized_row_ids:
            raise ValueError("at least one row_id is required.")
        return normalized_row_ids

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        lowered_row_id = str(row_id).strip().lower()
        if lowered_row_id.startswith("oa-att-inv-"):
            return "invoice"
        if lowered_row_id.startswith("oa-"):
            return "oa"
        if (
            lowered_row_id.startswith("bk-")
            or lowered_row_id.startswith("txn-")
            or lowered_row_id.startswith("txn_")
            or lowered_row_id.startswith("bank-")
        ):
            return "bank"
        if lowered_row_id.startswith("iv-") or lowered_row_id.startswith("invoice-"):
            return "invoice"
        return "unknown"

    def _row_types_for_row_ids(self, row_ids: list[str]) -> list[str]:
        return [self._row_type_for_row_id(row_id) for row_id in row_ids]

    def _month_scope_for_selected_row_ids(self, *, month: str, row_ids: list[str]) -> str:
        if month != "all":
            return month
        row_months = {
            resolved_month
            for resolved_month in (self._row_month_scope_from_row_id(row_id) for row_id in row_ids)
            if resolved_month
        }
        if len(row_months) == 1:
            return next(iter(row_months))
        return "all"

    def _resolve_rows_from_cached_read_models(
        self,
        row_ids: list[str],
        *,
        month_hint: str | None = None,
    ) -> dict[str, dict[str, object]]:
        normalized_month_hint = str(month_hint).strip() if month_hint not in (None, "") else None
        scope_keys: list[str] = []
        if normalized_month_hint:
            scope_keys.append(normalized_month_hint)
        if normalized_month_hint != "all":
            scope_keys.append("all")
        if normalized_month_hint is None:
            scope_keys.extend(self._workbench_read_model_service.list_scope_keys())

        resolved_rows: dict[str, dict[str, object]] = {}
        seen_scope_keys: set[str] = set()
        for scope_key in scope_keys:
            if not scope_key or scope_key in seen_scope_keys:
                continue
            seen_scope_keys.add(scope_key)
            read_model = self._workbench_read_model_service.get_read_model(scope_key)
            if not isinstance(read_model, dict):
                continue
            payload = read_model.get("payload")
            if not isinstance(payload, dict):
                continue
            rows_by_id = self._grouped_rows_by_id(payload)
            for row_id in row_ids:
                if row_id in resolved_rows:
                    continue
                row = rows_by_id.get(row_id)
                if row is not None:
                    resolved_rows[row_id] = self._serialize_value(row)
        return resolved_rows

    def _resolve_live_rows_direct(self, row_ids: list[str], *, month_hint: str | None = None) -> list[dict[str, object]]:
        normalized_row_ids = [str(row_id) for row_id in row_ids]
        resolved_rows = self._resolve_rows_from_cached_read_models(normalized_row_ids, month_hint=month_hint)
        unresolved_live_row_ids: list[str] = []

        for row_id in normalized_row_ids:
            if row_id in resolved_rows:
                continue
            if (
                not self._workbench_query_service._looks_like_oa_row_id(row_id)
                and row_id not in self._workbench_query_service._records_by_id
            ):
                unresolved_live_row_ids.append(row_id)
                continue
            try:
                oa_row = self._workbench_query_service.serialize_row(
                    self._workbench_query_service.get_row_record(row_id, month_hint=month_hint)
                )
                pair_relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
                paired_row = self._apply_pair_relation_to_row(oa_row, pair_relation) if isinstance(pair_relation, dict) else oa_row
                resolved_rows[row_id] = self._workbench_override_service.apply_to_row(paired_row)
            except KeyError:
                unresolved_live_row_ids.append(row_id)

        if unresolved_live_row_ids:
            get_rows_detail = getattr(self._live_workbench_service, "get_rows_detail", None)
            if callable(get_rows_detail):
                live_rows = get_rows_detail(unresolved_live_row_ids)
            else:
                live_rows = {
                    row_id: self._live_workbench_service.get_row_detail(row_id)
                    for row_id in unresolved_live_row_ids
                }
            for row_id in unresolved_live_row_ids:
                live_row = live_rows.get(row_id)
                if live_row is None:
                    raise KeyError(row_id)
                pair_relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
                paired_row = self._apply_pair_relation_to_row(live_row, pair_relation) if isinstance(pair_relation, dict) else live_row
                resolved_rows[row_id] = self._workbench_override_service.apply_to_row(paired_row)

        return [resolved_rows[row_id] for row_id in normalized_row_ids]

    def _resolve_live_row(self, grouped_payload: dict[str, object], row_id: str) -> dict[str, object]:
        rows_by_id = self._grouped_rows_by_id(grouped_payload)
        row = rows_by_id.get(row_id)
        if row is not None:
            return row
        return self._resolve_live_row_direct(row_id)

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

    def _sync_live_auto_pair_relations(self) -> None:
        if not hasattr(self._live_workbench_service, "list_auto_pair_candidates"):
            return
        desired_relations: dict[str, dict[str, object]] = {}
        for result in self._live_workbench_service.list_auto_pair_candidates("all"):
            row_ids = [str(row_id).strip() for row_id in list(result.transaction_ids or []) if str(row_id).strip()]
            if not row_ids:
                continue
            if self._auto_pair_conflicts_with_manual_relation(row_ids):
                continue
            desired_relations[str(result.id)] = {
                "case_id": str(result.id),
                "row_ids": row_ids,
                "row_types": ["bank"] * len(row_ids),
                "relation_mode": str(result.rule_code),
                "month_scope": self._month_scope_for_auto_relation(row_ids),
            }

        active_auto_relations = {
            str(relation.get("case_id")): relation
            for relation in self._workbench_pair_relation_service.list_active_relations()
            if str(relation.get("relation_mode")) in {"salary_personal_auto_match", "internal_transfer_pair"}
        }
        changed = False

        for case_id, desired_relation in desired_relations.items():
            existing_relation = active_auto_relations.get(case_id)
            if (
                isinstance(existing_relation, dict)
                and list(existing_relation.get("row_ids") or []) == desired_relation["row_ids"]
                and str(existing_relation.get("relation_mode")) == str(desired_relation["relation_mode"])
                and str(existing_relation.get("month_scope")) == str(desired_relation["month_scope"])
                and str(existing_relation.get("status")) == "active"
            ):
                continue

            self._workbench_pair_relation_service.create_active_relation(
                case_id=case_id,
                row_ids=list(desired_relation["row_ids"]),
                row_types=list(desired_relation["row_types"]),
                relation_mode=str(desired_relation["relation_mode"]),
                created_by="system_auto_match",
                month_scope=str(desired_relation["month_scope"]),
            )
            changed = True

        for case_id in set(active_auto_relations).difference(desired_relations):
            self._workbench_pair_relation_service.cancel_relation(case_id)
            changed = True

        if changed:
            self._search_service.clear_cache()
            self._invalidate_workbench_read_models()
            if self._state_store is not None:
                changed_case_ids = list(desired_relations.keys())
                changed_case_ids.extend(set(active_auto_relations).difference(desired_relations))
                changed_scope_keys = {"all"}
                changed_scope_keys.update(
                    str(relation["month_scope"])
                    for relation in desired_relations.values()
                    if relation.get("month_scope")
                )
                self._state_store.save_workbench_pair_relations(
                    self._workbench_pair_relation_service.snapshot(),
                    changed_case_ids=changed_case_ids,
                )
                self._persist_workbench_read_models_best_effort(
                    snapshot=self._workbench_read_model_service.snapshot(),
                    changed_scope_keys=list(changed_scope_keys),
                    operation="sync_live_auto_pair_relations",
                )

    def _auto_pair_conflicts_with_manual_relation(self, row_ids: list[str]) -> bool:
        for row_id in row_ids:
            active_relation = self._workbench_pair_relation_service.get_active_relation_by_row_id(row_id)
            if not isinstance(active_relation, dict):
                continue
            if str(active_relation.get("relation_mode")) not in SYSTEM_AUTO_PAIR_RELATION_MODES:
                return True
        return False

    def _month_scope_for_auto_relation(self, row_ids: list[str]) -> str:
        row_months = {
            self._row_month_scope(self._resolve_live_row_direct(row_id))
            for row_id in row_ids
        }
        normalized_months = {month for month in row_months if month}
        if len(normalized_months) == 1:
            return next(iter(normalized_months))
        return "all"

    @staticmethod
    def _pair_relation_display_payload(*, relation_mode: str, row_type: str = "") -> dict[str, str]:
        if relation_mode == "internal_transfer_pair":
            return {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"}
        if relation_mode == "salary_personal_auto_match":
            return {"code": "salary_personal_auto_match", "label": "已匹配：工资", "tone": "success"}
        if relation_mode == OA_INVOICE_OFFSET_AUTO_MATCH_MODE:
            if row_type == "invoice":
                return {"code": OA_INVOICE_OFFSET_AUTO_MATCH_MODE, "label": "已关联OA", "tone": "success"}
            return {"code": OA_INVOICE_OFFSET_AUTO_MATCH_MODE, "label": "待找流水与发票", "tone": "warn"}
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

    @classmethod
    def _apply_oa_invoice_offset_pair_metadata(cls, payload: dict[str, object]) -> None:
        payload["cost_excluded"] = True
        tags = [
            str(tag).strip()
            for tag in list(payload.get("tags") or [])
            if str(tag).strip()
        ]
        if OA_INVOICE_OFFSET_TAG not in tags:
            tags.append(OA_INVOICE_OFFSET_TAG)
        payload["tags"] = tags
        for fields_key in ("summary_fields", "detail_fields"):
            fields = payload.get(fields_key)
            if isinstance(fields, dict):
                fields["冲账标记"] = OA_INVOICE_OFFSET_TAG
                fields["成本统计"] = "不计入"

    def _apply_internal_transfer_pair_metadata(self, payload: dict[str, object], relation: dict[str, object]) -> None:
        row_id = str(payload.get("id", ""))
        counterpart_row_ids = [
            str(candidate_id)
            for candidate_id in list(relation.get("row_ids") or [])
            if str(candidate_id) and str(candidate_id) != row_id
        ]
        if not counterpart_row_ids:
            return
        try:
            counterpart_row = self._live_workbench_service.get_row_detail(counterpart_row_ids[0])
        except KeyError:
            return

        compact_label = self._compact_bank_account_label(str(counterpart_row.get("payment_account_label") or ""))
        if not compact_label:
            return

        prefix = "支付账户" if str(payload.get("direction")) == "收入" else "收款账户"
        counterpart_text = f"{prefix}：{compact_label}"
        base_remark = str(payload.get("remark") or "").strip()
        if counterpart_text not in base_remark:
            base_remark = counterpart_text if not base_remark else f"{base_remark}；{counterpart_text}"

        payload["remark"] = base_remark
        summary_fields = payload.get("summary_fields")
        if isinstance(summary_fields, dict):
            summary_fields["备注"] = base_remark or "—"
        detail_fields = payload.get("detail_fields")
        if isinstance(detail_fields, dict):
            detail_fields["备注"] = base_remark or "—"

    @staticmethod
    def _compact_bank_account_label(label: str) -> str:
        compact_label = str(label or "").strip()
        for marker in (" 基本户 ", " 一般户 ", " 专户 ", " 账户 "):
            compact_label = compact_label.replace(marker, " ")
        return " ".join(compact_label.split())

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
    if os.getenv("FIN_OPS_OA_POLLING_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}:
        application.start_oa_sync_polling_worker()
    if os.getenv("FIN_OPS_WORKBENCH_MATCHING_DIRTY_WORKER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}:
        application.start_workbench_matching_dirty_scope_worker()
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
            self.send_response(response.status_code)
            for key, value in response.headers.items():
                self.send_header(key, value)
            if response.stream:
                self.end_headers()
                for chunk in response.body:
                    encoded_chunk = chunk.encode("utf-8") if isinstance(chunk, str) else chunk
                    if not encoded_chunk:
                        continue
                    self.wfile.write(encoded_chunk)
                    self.wfile.flush()
                return
            encoded = response.body.encode("utf-8") if isinstance(response.body, str) else response.body
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, format: str, *args: object) -> None:
            return

    return RequestHandler
