from __future__ import annotations

import csv
import json
import os
import re
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from hmac import compare_digest
from http import HTTPStatus
from io import StringIO
from pathlib import Path
from threading import Lock
from time import monotonic
from types import SimpleNamespace
from typing import Any, Callable, Iterable
from urllib.parse import parse_qs, quote, unquote, urlparse
from uuid import uuid4

import fin_ops_platform
from fin_ops_platform import __version__
from fin_ops_platform.app.auth import (
    BEARER_PREFIX,
    ForbiddenOAAccessError,
    OAAuthError,
    OARequestSession,
    UnauthorizedOASessionError,
    actor_id_for_session,
    extract_oa_token,
    get_header,
    resolve_oa_request_session,
    tenant_id_for_session,
)
from fin_ops_platform.app.http_upload import MultipartBodyError, parse_multipart_body
from fin_ops_platform.app.route_access_policy import requires_data_mutation
from fin_ops_platform.app.routes_bank_details import BankDetailsApiRoutes
from fin_ops_platform.app.routes_bank_flow_rule_batches import BankFlowRuleBatchApiRoutes
from fin_ops_platform.app.routes_batch_accounting import BatchAccountingApiRoutes
from fin_ops_platform.app.routes_cost_statistics import CostStatisticsApiRoutes
from fin_ops_platform.app.routes_etc import EtcBusinessBatchApiRoutes
from fin_ops_platform.app.routes_etc_import import EtcImportApiRoutes
from fin_ops_platform.app.routes_etc_invoices import EtcInvoiceApiRoutes
from fin_ops_platform.app.routes_etc_reconciliation import EtcReconciliationTaskApiRoutes
from fin_ops_platform.app.routes_input_invoice_usage import InputInvoiceUsageApiRoutes
from fin_ops_platform.app.routes_input_invoice_usage_oa_reverse import InputInvoiceUsageOaReverseApiRoutes
from fin_ops_platform.app.routes_no_oa_bank_batches import NoOaBankBatchApiRoutes
from fin_ops_platform.app.routes_oa_pending_payments import OaPendingPaymentApiRoutes
from fin_ops_platform.app.routes_output_invoice_collections import OutputInvoiceCollectionApiRoutes
from fin_ops_platform.app.routes_pending_invoices import PendingInvoiceApiRoutes, PendingInvoiceExportFile
from fin_ops_platform.app.routes_settings import SettingsApiRoutes
from fin_ops_platform.app.routes_tax import TaxApiRoutes
from fin_ops_platform.app.routes_turnover_ledger import (
    InMemoryTurnoverLedgerExtraService,
    TurnoverLedgerApiRoutes,
)
from fin_ops_platform.app.routes_workbench import (
    WorkbenchGroupDetailApiRoutes,
    WorkbenchReadApiRoutes,
    WorkbenchRowDetailApiRoutes,
)
from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.access_control_service import AccessControlService
from fin_ops_platform.services.api_performance_metrics import ApiPerformanceRecorder, request_database_timing
from fin_ops_platform.services.app_health_alert_service import AppHealthAlertService
from fin_ops_platform.services.app_health_service import AppHealthService
from fin_ops_platform.services.app_settings_service import (
    AppSettingsService,
    AppSettingsValidationError,
)
from fin_ops_platform.services.app_status_overview_service import AppStatusOverviewService
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.background_job_service import (
    BackgroundJobAccessError,
    BackgroundJobIdempotencyConflict,
    BackgroundJobNotFoundError,
    BackgroundJobService,
)
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.bank_batch_application_service import (
    BankBatchPairRelationSnapshotPort,
)
from fin_ops_platform.services.bank_batch_service import (
    BANK_FLOW_RULE_BATCH_ID_PREFIX,
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
    BankBatchRelationRepairReadPort,
    BankBatchService,
)
from fin_ops_platform.services.bank_category_relation_closure_service import (
    BankCategoryRelationClosureService,
)
from fin_ops_platform.services.bank_detail_auto_category_suggestion_provider import (
    BankDetailAutoCategorySuggestionProvider,
)
from fin_ops_platform.services.bank_details_application_service import BankDetailsApplicationService
from fin_ops_platform.services.bank_details_canonical_query import (
    BankDetailsCanonicalQueryService,
    PostgresBankDetailsCanonicalQueryRepository,
)
from fin_ops_platform.services.bank_details_relation_tag_projection_service import (
    BankDetailsRelationTagProjectionService,
)
from fin_ops_platform.services.bank_details_service import BankDetailsService
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.postgres_repositories.bank_relation_requirement_recalculation import (
    PostgresBankRelationRequirementRecalculationRequestRepository,
)
from fin_ops_platform.services.bank_import_withdrawal_service import (
    BankImportWithdrawalConflict,
    BankImportWithdrawalService,
)
from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService
from fin_ops_platform.services.bank_transaction_category_mutation_writer import (
    BankTransactionCategoryMutationWriter,
)
from fin_ops_platform.services.bank_transaction_category_service import (
    BANK_TRANSACTION_CATEGORY_LABELS,
    BankTransactionCategoryService,
    BankTransactionCategoryValidationError,
)
from fin_ops_platform.services.bank_transaction_effective_category_provider import (
    BankTransactionEffectiveCategoryProvider,
)
from fin_ops_platform.services.batch_accounting_service import BatchAccountingService
from fin_ops_platform.services.cost_statistics_canonical_repository import (
    LocalCostStatisticsCanonicalRepository,
    PostgresCostStatisticsCanonicalRepository,
)
from fin_ops_platform.services.cost_statistics_query_service import CostStatisticsQueryService
from fin_ops_platform.services.derived_data_lifecycle_service import DerivedDataLifecycleService
from fin_ops_platform.services.etc_business_batch_application_service import EtcBusinessBatchApplicationService
from fin_ops_platform.services.etc_business_batch_delete_service import EtcBusinessBatchDeleteService
from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.etc_import_preview_service import EtcImportPreviewService
from fin_ops_platform.services.etc_import_session_store import build_etc_import_session_store
from fin_ops_platform.services.etc_invoice_pdf_bundle_service import EtcInvoicePdfBundle, EtcInvoicePdfBundleService
from fin_ops_platform.services.etc_reconciliation_import_cleanup_service import EtcReconciliationImportCleanupService
from fin_ops_platform.services.etc_reconciliation_service import EtcReconciliationTaskService
from fin_ops_platform.services.etc_reconciliation_source_upload_service import (
    EtcReconciliationSourceUploadService,
)
from fin_ops_platform.services.etc_reconciliation_task_payload_facade import EtcReconciliationTaskPayloadFacade
from fin_ops_platform.services.etc_service import (
    EtcBusinessBatchActiveExistsError,
    EtcBusinessBatchInvalidTransitionError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchVersionConflictError,
    EtcDraftRequestError,
    EtcInvoiceNotFoundError,
    EtcOAClientError,
    EtcService,
    EtcServiceError,
    HttpEtcOAClient,
    NotConfiguredEtcOAClient,
    UploadedEtcZipFile,
)
from fin_ops_platform.services.health_payload_compaction import compact_ready_payload
from fin_ops_platform.services.runtime_monitoring import readiness_blockers
from fin_ops_platform.services.historical_etc_repair_service import HistoricalEtcRepairService
from fin_ops_platform.services.http_runtime_metrics import HTTP_RUNTIME_METRICS
from fin_ops_platform.services.import_file_service import FileImportService, UploadedImportFile
from fin_ops_platform.services.import_job_queue import ImportJob, ImportJobIdempotencyConflict, ImportJobRepository
from fin_ops_platform.services.import_lifecycle_service import ImportLifecycleService
from fin_ops_platform.services.import_preview_audit import ImportPreviewStaleError
from fin_ops_platform.services.import_processing_service import ImportProcessingService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.manual_invoice_entry_service import (
    ManualInvoiceEntryError,
    ManualInvoiceEntryService,
)
from fin_ops_platform.services.input_invoice_usage_canonical_query_service import (
    InputInvoiceUsageCanonicalQueryService,
)
from fin_ops_platform.services.input_invoice_usage_export_service import (
    InputInvoiceUsageExportError,
    InputInvoiceUsageExportService,
)
from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
    InMemoryInputInvoiceUsageOaReverseBatchRepository,
    InputInvoiceUsageOaReverseInvalidTransitionError,
    InputInvoiceUsageOaReverseMissingClientError,
    InputInvoiceUsageOaReverseNotFoundError,
    InputInvoiceUsageOaReversePermissionError,
    InputInvoiceUsageOaReverseService,
    InputInvoiceUsageOaReverseServiceError,
    InputInvoiceUsageOaReverseStalePreviewError,
    InputInvoiceUsageOaReverseVersionConflictError,
    NotConfiguredInputInvoiceUsageOaDraftClient,
    OAProjectionInputInvoiceUsageOaEvidenceProvider,
    WorkbenchInputInvoiceUsageOaReverseRelationWriter,
)
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
)
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.live_workbench_service import LiveWorkbenchService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.no_oa_bank_batch_application_service import (
    NoOaBankBatchApplicationService,
    NoOaPairRelationSnapshotPort,
)
from fin_ops_platform.services.no_oa_bank_batch_service import (
    NO_OA_BANK_BATCH_RELATION_MODE,
    NoOaBankBatchService,
)
from fin_ops_platform.services.no_oa_bank_batch_tag_selection_service import (
    NoOaBankBatchTagSelectionApplicationService,
)
from fin_ops_platform.services.no_oa_bank_batch_workbench_display_policy import (
    NoOaBankBatchWorkbenchDisplayPolicy,
)
from fin_ops_platform.services.no_oa_bank_batch_workbench_payload_decorator import (
    NoOaBankBatchWorkbenchPayloadDecorator,
)
from fin_ops_platform.services.no_oa_managed_rule_policy import (
    NO_OA_MANAGED_LABELS,
)
from fin_ops_platform.services.oa_applicant_credentials import (
    InMemoryOaApplicantCredentialRepository,
    OaApplicantCredentialService,
)
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    oa_attachment_matches_oa,
    oa_attachment_parent_oa_id,
    oa_attachment_row_id_matches_oa,
    oa_row_source_ids,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.oa_draft_prefill import (
    ETC_OA_DRAFT_PREFILL_FAMILY,
    INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY,
)
from fin_ops_platform.services.oa_identity_service import (
    OAIdentityConfigurationError,
    OAIdentityService,
    OAIdentityServiceError,
    OASessionExpiredError,
)
from fin_ops_platform.services.oa_manual_import_service import OAManualImportService
from fin_ops_platform.services.oa_payment_admitted_projection import PaymentAdmittedOAProjectionAdapter
from fin_ops_platform.services.oa_payment_status_service import MySQLOAPaymentStatusRepository
from fin_ops_platform.services.oa_pending_payment_command_service import OaPendingPaymentCommandService
from fin_ops_platform.services.oa_pending_payment_query_contract import OaPendingPaymentError
from fin_ops_platform.services.oa_pending_payment_query_service import OaPendingPaymentQueryService
from fin_ops_platform.services.oa_role_sync_service import OARoleSyncService
from fin_ops_platform.services.object_storage import ObjectStorageWriteError
from fin_ops_platform.services.operation_history_evidence import (
    attempted_supporting_document_artifacts,
    build_operation_evidence,
    manual_invoice_record,
    supporting_document_artifact,
    workbench_oa_target,
)
from fin_ops_platform.services.operation_history_semantics import operation_semantics
from fin_ops_platform.services.operations_audit_service import OperationsAuditService, PageAuditUnavailableError
from fin_ops_platform.services.operations_dashboard import OperationsDashboardService
from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService
from fin_ops_platform.services.output_invoice_collection_canonical_query_service import (
    OutputInvoiceCollectionCanonicalQueryService,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.pending_invoice_canonical_query import (
    LocalPendingInvoiceCanonicalRepository,
    PendingInvoiceCanonicalQueryService,
    PostgresPendingInvoiceCanonicalRepository,
)
from fin_ops_platform.services.pending_invoice_rules_application_service import (
    AppSettingsPendingInvoiceRulesGateway,
    PendingInvoiceRulesApplicationService,
)
from fin_ops_platform.services.pending_invoice_service import (
    InMemoryPendingInvoiceCommandRepository,
    PendingInvoiceApplicationService,
    PendingInvoiceError,
    PendingInvoiceQueryService,
    record_pending_invoice_audit,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection
from fin_ops_platform.services.postgres_repositories.bank_import_withdrawal import (
    PostgresBankImportWithdrawalRepository,
)
from fin_ops_platform.services.postgres_repositories.batch_accounting import (
    PostgresBatchAccountingQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.input_invoice_usage_oa_reverse import (
    PostgresInputInvoiceUsageOaReverseBatchRepository,
    input_invoice_usage_oa_reverse_statistics_snapshot,
)
from fin_ops_platform.services.postgres_repositories.import_lifecycle import PostgresImportLifecycleRepository
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    PostgresInputInvoiceUsageQueryRepository,
    PostgresOutputInvoiceCollectionQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_applicant_credentials import (
    PostgresOaApplicantCredentialRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_query import (
    PostgresOaPendingPaymentQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentSourceSnapshotRepository,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    OA_PROJECTION_SYNC_VERSION,
    PostgresOAProjectionAdapter,
    PostgresOAWorkflowRepository,
)
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import (
    APP_SETTINGS_KEY,
    PostgresOpsTaxEtcRepository,
)
from fin_ops_platform.services.postgres_repositories.settings_data_reset_request import (
    PostgresSettingsDataResetRequestRepository,
)
from fin_ops_platform.services.postgres_repositories.tax_offset import (
    LocalTaxOffsetCanonicalRepository,
    PostgresTaxOffsetCanonicalRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench import PostgresWorkbenchRepository
from fin_ops_platform.services.postgres_repositories.workbench_oa_supporting_document import (
    PostgresWorkbenchOaSupportingDocumentRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_query import (
    PostgresWorkbenchPageQueryRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
    PostgresWorkbenchPageSelectionRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_idempotency import PostgresWorkbenchIdempotencyRepository
from fin_ops_platform.services.postgres_repositories.workbench_relation import PostgresWorkbenchRelationRepository
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.prometheus_metrics import PROMETHEUS_CONTENT_TYPE, render_prometheus_metrics
from fin_ops_platform.services.reconciliation import ManualReconciliationService
from fin_ops_platform.services.runtime_bootstrap import RuntimeRepositoryContext
from fin_ops_platform.services.seeds import build_demo_seed
from fin_ops_platform.services.settings_data_reset_request import SettingsDataResetRequestService
from fin_ops_platform.services.settings_data_reset_service import (
    SettingsDataResetPairSnapshotPort,
    SettingsDataResetService,
)
from fin_ops_platform.services.state_store_factory import build_state_store
from fin_ops_platform.services.target_oa_applicant_token_provider import (
    OaLoginClient,
    TargetOaApplicantTokenProvider,
    TargetOaApplicantTokenProviderError,
)
from fin_ops_platform.services.tax_certified_import_application_service import TaxCertifiedImportApplicationService
from fin_ops_platform.services.tax_certified_import_job_service import TaxCertifiedImportJobService
from fin_ops_platform.services.tax_certified_import_service import TaxCertifiedImportService
from fin_ops_platform.services.tax_offset_plan_service import InMemoryTaxOffsetPlanRepository, TaxOffsetPlanService
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQueryService
from fin_ops_platform.services.tax_offset_service import TaxOffsetService
from fin_ops_platform.services.turnover_bank_row_version import turnover_bank_row_version
from fin_ops_platform.services.turnover_ledger_export_service import (
    XLSX_MIME_TYPE,
)
from fin_ops_platform.services.turnover_ledger_query_service import (
    TurnoverLedgerQueryService,
    canonical_turnover_bank_rows_by_ids,
)
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_ledger_write_adapters import (
    TurnoverLedgerBankRowTagsPrimaryWriteFacadeBuilder,
    TurnoverLedgerBankRowTagsRequestBoundaryFacade,
    TurnoverLedgerConfirmPrimaryWriteFacadeBuilder,
    TurnoverLedgerConfirmRequestBoundaryFacade,
    TurnoverLedgerLocalPairSnapshotPort,
    TurnoverLedgerLocalRuntimeSupport,
    TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder,
    TurnoverLedgerRelationExtraRequestBoundaryFacade,
    TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder,
    TurnoverLedgerTagSelectionRequestBoundaryFacade,
    TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder,
    TurnoverLedgerWithdrawRequestBoundaryFacade,
    TurnoverLedgerWritePreconditionError,
)
from fin_ops_platform.services.turnover_ledger_write_facade import TurnoverLedgerWriteFacade
from fin_ops_platform.services.turnover_relation_service import (
    TURNOVER_CATEGORY_RULES,
    TurnoverRelationService,
)
from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
from fin_ops_platform.services.workbench_anomaly_review_service import (
    WorkbenchAnomalyReviewService,
)
from fin_ops_platform.services.workbench_confirm_link_context_relation_read_port import (
    WorkbenchConfirmLinkContextRelationReadPort,
)
from fin_ops_platform.services.workbench_etc_batch_link import WORKBENCH_ETC_BATCH_LINK_VERSION
from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_exception_rollback_restore_service import (
    WorkbenchExceptionRollbackRestoreService,
)
from fin_ops_platform.services.workbench_exception_rules import RULE_VERSION as WORKBENCH_EXCEPTION_RULE_VERSION
from fin_ops_platform.services.workbench_filter_options import normalize_workbench_scope_key
from fin_ops_platform.services.workbench_free_matching_engine import (
    RULE_VERSION as WORKBENCH_FORMAL_RELATION_RULE_VERSION,
)
from fin_ops_platform.services.workbench_idempotency import (
    InMemoryWorkbenchIdempotencyRepository,
)
from fin_ops_platform.services.workbench_invoice_supplement_service import (
    ManualInvoiceSupplementCommand,
    WorkbenchInvoiceSupplementError,
    WorkbenchInvoiceSupplementService,
)
from fin_ops_platform.services.workbench_oa_attachment_context_row_index import (
    WorkbenchOaAttachmentContextRowIndex,
)
from fin_ops_platform.services.workbench_oa_supporting_document_service import (
    SupportingDocumentUpload,
    WorkbenchOaSupportingDocumentError,
    WorkbenchOaSupportingDocumentService,
)
from fin_ops_platform.services.workbench_oa_retention_date_parser import WorkbenchOaRetentionDateParser
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_pair_relation_display_policy import (
    WorkbenchPairRelationDisplayPolicy,
)
from fin_ops_platform.services.workbench_pair_relation_persist_service import WorkbenchPairRelationPersistService
from fin_ops_platform.services.workbench_pair_relation_rollback_restore_service import (
    WorkbenchPairRelationRollbackRestoreService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_payload_relation_read_port import WorkbenchPayloadRelationReadPort
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import WorkbenchReconciliationDirtyQueue
from fin_ops_platform.services.workbench_relation_case_id_allocator import WorkbenchRelationCaseIdAllocator
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
    WorkbenchRelationCommandService,
)
from fin_ops_platform.services.workbench_relation_grouping import (
    WorkbenchRelationGroupingService,
    WorkbenchRelationPreviewGroupingService,
)
from fin_ops_platform.services.workbench_relation_source_version_provider import WorkbenchRelationSourceVersionProvider
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id
from fin_ops_platform.services.workbench_uow import WorkbenchWriteUnitOfWork
from fin_ops_platform.services.workbench_write_facade import (
    WorkbenchWriteFacade,
    WorkbenchWriteRelationReadSnapshotPort,
    WorkbenchWriteRelationSpecialMetadataMutationPort,
    WorkbenchWriteResult,
)

CASH_TURNOVER_TAG = "现金往来"

OA_INVOICE_OFFSET_AUTO_MATCH_MODE = "oa_invoice_offset_auto_match"
OA_INVOICE_OFFSET_TAG = "冲"
CASH_PASS_THROUGH_MODE = "cash_pass_through"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
PERSONAL_ADVANCE_REPAYMENT_MODE = "personal_advance_repayment_settlement"
PRODUCTION_RUNTIME_GUARD_ENV = "FIN_OPS_PRODUCTION_RUNTIME_GUARD"
POSTGRES_FULL_STATE_SNAPSHOT_ENV = "FIN_OPS_ENABLE_POSTGRES_FULL_STATE_SNAPSHOT"
PROMETHEUS_BEARER_TOKEN_ENV = "FIN_OPS_PROMETHEUS_BEARER_TOKEN"
HEALTH_API_PERFORMANCE_ENDPOINT_LIMIT = 20
_REQUEST_AUDIT_ACTOR: ContextVar[tuple[str, str, str]] = ContextVar(
    "request_audit_actor",
    default=("", "", ""),
)
_REQUEST_AUDIT_REQUEST_ID: ContextVar[str | None] = ContextVar(
    "request_audit_request_id",
    default=None,
)
_REQUEST_AUDIT_EVIDENCE: ContextVar[dict[str, Any] | None] = ContextVar(
    "request_audit_evidence",
    default=None,
)


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}

@dataclass(slots=True)
class Response:
    status_code: int
    body: str | bytes
    headers: dict[str, str] = field(
        default_factory=lambda: {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        }
    )

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
MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")

class Application:
    def __init__(self, *, data_dir: Path | None = None, bootstrap_mode: str | None = None) -> None:
        self._bootstrap_mode = self._normalize_bootstrap_mode(bootstrap_mode)
        self._api_performance_recorder = ApiPerformanceRecorder()
        self._state_store = build_state_store(data_dir)
        self._runtime_repositories = RuntimeRepositoryContext.from_state_store(self._state_store)
        self._app_health_dashboard_cache_lock = Lock()
        self._app_health_dashboard_cache: tuple[float, dict[str, object]] | None = None
        self._app_status_runtime_snapshot_cache_lock = Lock()
        self._app_status_runtime_snapshot_cache: tuple[float, dict[str, object]] | None = None
        self._seed_payload = build_demo_seed()
        if self._bootstrap_mode == "lightweight":
            return
        self._initialize_runtime_services(self._runtime_bootstrap_state())

    @property
    def runtime_repositories(self) -> RuntimeRepositoryContext:
        return self._runtime_repositories

    def close(self) -> None:
        close = getattr(self._state_store, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _normalize_bootstrap_mode(value: str | None) -> str:
        raw_value = (value or os.getenv("FIN_OPS_BOOTSTRAP_MODE") or "production").strip().lower()
        if raw_value not in {"production", "legacy", "lightweight"}:
            raise ValueError("bootstrap_mode must be production, legacy, or lightweight.")
        return raw_value

    def _resolve_request_session(self, headers: dict[str, str] | None) -> OARequestSession:
        return resolve_oa_request_session(
            headers,
            identity_service=self._oa_identity_service,
            access_control_service=self._access_control_service,
        )

    def _runtime_bootstrap_state(self) -> dict[str, object]:
        return {}

    def _requires_postgres_runtime(self) -> bool:
        if getattr(self, "_bootstrap_mode", None) not in {"production", "lightweight"}:
            return False
        return str(getattr(self._state_store, "storage_backend", "") or "").strip() == "postgres"

    @staticmethod
    def _workbench_reconciliation_tenant_id() -> str:
        return str(os.getenv("FIN_OPS_TENANT_ID") or "default").strip() or "default"


    def _bank_transaction_tag_reader(self) -> object:
        return self._bank_transaction_effective_category_provider

    def _workbench_reconciliation_dirty_queue_repository(self):
        repository = getattr(self._state_store, "workbench_matching_queue_repository", None)
        required_methods = (
            "mark_workbench_matching_dirty_scopes",
            "claim_workbench_matching_dirty_scopes",
            "complete_workbench_matching_dirty_scope",
            "fail_workbench_matching_dirty_scope",
        )
        if repository is not None and all(
            callable(getattr(repository, method_name, None)) for method_name in required_methods
        ):
            return repository
        return None

    def _runtime_repository_snapshot(
        self,
        persisted_state: dict[str, object],
        key: str,
        loader_name: str,
    ) -> dict[str, object]:
        snapshot = persisted_state.get(key)
        if isinstance(snapshot, dict):
            return snapshot
        loader = getattr(self._state_store, loader_name, None) if self._state_store is not None else None
        if not callable(loader):
            return {}
        loaded = loader()
        if isinstance(loaded, dict):
            return loaded
        return {}

    @staticmethod
    def _build_turnover_ledger_extra_service(snapshot: object) -> object:
        try:
            from fin_ops_platform.services.turnover_ledger_extra_service import TurnoverLedgerExtraService
        except ModuleNotFoundError:
            return InMemoryTurnoverLedgerExtraService.from_snapshot(snapshot if isinstance(snapshot, dict) else None)
        return TurnoverLedgerExtraService.from_snapshot(snapshot if isinstance(snapshot, dict) else None)

    def initialize_tool_runtime_state(self, persisted_state: dict[str, object]) -> None:
        self._initialize_runtime_services(persisted_state)

    def tool_runtime_state_snapshot(self) -> dict[str, object]:
        state_store = self._state_store
        state: dict[str, object] = {}
        for key, loader_name in (
            ("imports", "load_imports_snapshot"),
            ("file_imports", "load_file_imports_snapshot"),
            ("workbench_pair_relations", "load_workbench_pair_relations"),
            ("etc_reconciliation_state", "load_etc_reconciliation_state"),
        ):
            loader = getattr(state_store, loader_name, None)
            if not callable(loader):
                continue
            loaded = loader()
            if isinstance(loaded, dict):
                state[key] = loaded
        return state

    def tool_runtime_ports(self) -> SimpleNamespace:
        state_store = self._state_store
        etc_service = self._etc_service
        etc_reconciliation_task_service = self._etc_reconciliation_task_service
        save_etc_state = getattr(state_store, "save_etc_state", None)
        category_repository = getattr(
            state_store,
            "bank_transaction_category_repository",
            None,
        )
        category_source_proofs = getattr(
            category_repository,
            "turnover_bank_row_selection_proofs",
            None,
        )
        return SimpleNamespace(
            get_settings_payload=self._app_settings_service.get_settings_payload,
            replace_auto_tag_rules_from_file_source=self._bank_details_application_service().replace_auto_tag_rules_from_file_source,
            import_service=self._import_service,
            etc_service=etc_service,
            etc_reconciliation_task_service=etc_reconciliation_task_service,
            workbench_relation_command_service=self._workbench_relation_command_service(),
            workbench_relation_reader=self._workbench_relation_command_service(),
            workbench_canonical_rows_by_ids=self._tool_workbench_canonical_rows_by_ids,
            bank_transaction_effective_category_provider=self._bank_transaction_tag_reader(),
            bank_transaction_category_source_proofs=(
                category_source_proofs if callable(category_source_proofs) else None
            ),
            get_bank_flow_rule_batch_tag_rules_payload=(
                self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload
            ),
            object_identity_repository=(
                self._import_fact_repository
                if callable(getattr(getattr(self, "_import_fact_repository", None), "find_invoice_by_identity", None))
                else self._import_service
            ),
            persist_workbench_pair_relations=lambda case_ids: self._persist_workbench_pair_relations(changed_case_ids=case_ids),
            refresh_after_workbench_requirement_repair=self._refresh_after_workbench_requirement_repair,
            refresh_after_historical_etc_repair_link=self._refresh_after_historical_etc_repair_link,
            save_invoice_etc_metadata=(
                state_store.save_invoice_etc_metadata
                if callable(getattr(state_store, "save_invoice_etc_metadata", None))
                else None
            ),
            persist_etc_state=(lambda: save_etc_state(etc_service.snapshot())) if callable(save_etc_state) else None,
        )

    def _tool_workbench_canonical_rows_by_ids(
        self,
        row_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        connection = getattr(self._state_store, "_connection", None)
        if connection is None:
            raise RuntimeError("Workbench canonical row lookup requires PostgreSQL runtime.")
        return PostgresWorkbenchPageSelectionRepository(
            connection,
            tenant_id=self._workbench_reconciliation_tenant_id(),
        ).get_canonical_rows_by_ids(
            row_ids
        )

    def _initialize_runtime_services(self, persisted_state: dict[str, object]) -> None:
        import_fact_repository = getattr(self._state_store, "import_fact_repository", None)
        postgres_connection = getattr(self._state_store, "_connection", None)
        self._batch_accounting_query_repository = (
            PostgresBatchAccountingQueryRepository(postgres_connection)
            if postgres_connection is not None
            else None
        )
        self._workbench_page_query_repository = (
            PostgresWorkbenchPageQueryRepository(
                postgres_connection,
                tenant_id=self._workbench_reconciliation_tenant_id(),
            )
            if postgres_connection is not None
            else None
        )
        self._workbench_page_selection_repository = (
            PostgresWorkbenchPageSelectionRepository(
                postgres_connection,
                tenant_id=self._workbench_reconciliation_tenant_id(),
            )
            if postgres_connection is not None
            else None
        )
        self._workbench_anomaly_review_service = (
            WorkbenchAnomalyReviewService(
                group_repository=self._workbench_page_query_repository,
                decision_repository=PostgresWorkbenchRepository(postgres_connection),
            )
            if postgres_connection is not None
            else None
        )
        state_connection = getattr(self._state_store, "_connection", None)
        has_postgres = (
            str(getattr(self._state_store, "storage_backend", "") or "").strip() == "postgres"
            and state_connection is not None
        )
        self._input_invoice_usage_canonical_query_repository = (
            PostgresInputInvoiceUsageQueryRepository(state_connection) if has_postgres else None
        )
        self._output_invoice_collection_canonical_query_repository = (
            PostgresOutputInvoiceCollectionQueryRepository(state_connection) if has_postgres else None
        )
        self._oa_pending_payment_sql_read_repository = getattr(self._state_store, "oa_pending_payment_sql_read_repository", None)
        self._bank_flow_rule_batch_canonical_query_repository = getattr(
            self._state_store,
            "bank_flow_rule_batch_canonical_query_repository",
            None,
        )
        self._import_service = ImportNormalizationService.from_snapshot(
            persisted_state.get("imports"),
            id_registry=self._state_store,
            fact_repository=import_fact_repository,
        )
        self._bank_transaction_category_service = BankTransactionCategoryService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "bank_transaction_categories",
                "load_bank_transaction_categories",
            ),
            transaction_exists=self._bank_transaction_exists,
        )
        self._bank_transaction_auto_category_service = BankTransactionAutoCategoryService(
            category_service=self._bank_transaction_category_service
        )
        self._bank_transaction_effective_category_provider = BankTransactionEffectiveCategoryProvider(
            category_service=self._bank_transaction_category_service,
            auto_category_service=self._bank_transaction_auto_category_service,
        )
        self._turnover_relation_service = TurnoverRelationService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "turnover_relations",
                "load_turnover_relations",
            ),
            bank_rows=self._turnover_bank_transaction_rows(),
        )
        self._file_import_service = FileImportService.from_snapshot(
            self._import_service,
            persisted_state.get("file_imports"),
            file_store=self._state_store,
        )
        self._invoice_document_recognizer = OAAttachmentInvoiceService()
        self._manual_invoice_entry_service = ManualInvoiceEntryService(
            file_import_service=self._file_import_service,
            document_recognizer=self._invoice_document_recognizer,
        )
        self._matching_service = MatchingEngineService.from_snapshot(
            self._import_service,
            persisted_state.get("matching"),
        )
        self._workbench_override_service = WorkbenchOverrideService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "workbench_overrides",
                "load_workbench_overrides",
            ),
        )
        self._workbench_exception_case_service = WorkbenchExceptionCaseService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "workbench_exception_cases",
                "load_workbench_exception_cases",
            ),
        )
        self._workbench_pair_relation_service = WorkbenchPairRelationService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "workbench_pair_relations",
                "load_workbench_pair_relations",
            ),
        )
        self._no_oa_bank_batch_service = NoOaBankBatchService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "no_oa_bank_batches",
                "load_no_oa_bank_batches",
            ),
            pair_relation_service=self._workbench_pair_relation_service,
            relation_command_service=self._workbench_relation_command_service(),
        )
        bank_flow_relation_service = getattr(self, "_workbench_pair_relation" + "_service")
        self._bank_flow_rule_batch_service = BankBatchService.from_snapshot(
            self._runtime_repository_snapshot(
                persisted_state,
                "bank_flow_rule_batches",
                "load_bank_flow_rule_batches",
            ),
            relation_read_port=BankBatchRelationRepairReadPort(bank_flow_relation_service),
            relation_command_service=self._workbench_relation_command_service(),
            schema_version=BANK_FLOW_RULE_BATCH_SCHEMA_VERSION,
            batch_id_prefix=BANK_FLOW_RULE_BATCH_ID_PREFIX,
            relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
        )
        self._workbench_amount_check_service = WorkbenchAmountCheckService()
        self._derived_data_lifecycle_service = DerivedDataLifecycleService()
        dirty_queue_repository = self._workbench_reconciliation_dirty_queue_repository()
        self._workbench_reconciliation_dirty_queue = WorkbenchReconciliationDirtyQueue(
            repository=dirty_queue_repository,
            tenant_id=self._workbench_reconciliation_tenant_id(),
        )
        oa_projection_repository = getattr(self._state_store, "oa_projection_repository", None)
        oa_adapter = (
            PostgresOAProjectionAdapter(oa_projection_repository)
            if oa_projection_repository is not None
            else None
        )
        oa_workflow_adapter = (
            PostgresOAProjectionAdapter(
                PostgresOAWorkflowRepository(getattr(self._state_store, "_connection"))
            )
            if getattr(self._state_store, "_connection", None) is not None
            else oa_adapter
        )
        self._audit_service = AuditTrailService(
            getattr(self._runtime_repositories, "operations_audit_repository", None),
            request_id_provider=_REQUEST_AUDIT_REQUEST_ID.get,
        )
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
            bank_transaction_category_service=self._bank_transaction_category_service,
            bank_transaction_auto_category_service=self._bank_transaction_auto_category_service,
            audit_service=self._audit_service,
        )
        self._no_oa_bank_batch_tag_selection_service = NoOaBankBatchTagSelectionApplicationService(
            app_settings_service=self._app_settings_service,
        )
        self._oa_identity_service = OAIdentityService(login_client=OaLoginClient())
        self._access_control_service = AccessControlService.from_environment(
            access_control_snapshot_provider=self._app_settings_service.get_access_control_snapshot,
        )
        bank_account_resolver = BankAccountResolver(self._app_settings_service.get_bank_account_mapping_dict)
        self._workbench_query_service = WorkbenchQueryService(
            oa_adapter=oa_workflow_adapter,
            seed_demo_rows=not self._requires_postgres_runtime(),
        )
        self._oa_manual_import_service = (
            OAManualImportService(
                state_store=self._state_store,
                oa_adapter=oa_adapter,
                workbench_query_service=self._workbench_query_service,
                attachment_invoice_promoter=(
                    OAAttachmentInvoicePromotionService(
                        invoice_repository=(
                            PostgresOAAttachmentInvoiceRepository(state_connection)
                            if has_postgres
                            else import_fact_repository
                        ),
                        promotion_mode_provider=self._app_settings_service.get_oa_attachment_invoice_promotion_mode,
                    )
                    if import_fact_repository is not None
                    else None
                ),
            )
            if self._state_store is not None and oa_adapter is not None
            else None
        )
        self._live_workbench_service = LiveWorkbenchService(
            self._import_service,
            self._matching_service,
            bank_account_resolver=bank_account_resolver,
            category_provider=self._bank_transaction_tag_reader(),
        )
        self._bank_details_relation_tag_projection_service = BankDetailsRelationTagProjectionService(
            relation_reader=self._workbench_relation_command_service(),
        )
        self._bank_details_service = BankDetailsService(
            self._import_service,
            category_service=self._bank_transaction_category_service,
            auto_category_service=self._bank_transaction_auto_category_service,
            relation_tag_provider=self._bank_details_relation_tag_projection_service.relation_tag_for_transaction,
            relation_tag_batch_provider=self._bank_details_relation_tag_projection_service.relation_tags_for_transactions,
            fact_repository=import_fact_repository,
        )
        self._pending_invoice_commands = (
            dict(persisted_state.get("pending_invoice_commands") or {})
            if isinstance(persisted_state.get("pending_invoice_commands"), dict)
            else {}
        )
        self._pending_invoice_command_repository = InMemoryPendingInvoiceCommandRepository(self._pending_invoice_commands)
        self._pending_invoice_query_service = PendingInvoiceQueryService(
            import_service=self._import_service,
            category_service=self._bank_transaction_category_service,
            app_settings_provider=self._app_settings_service.get_pending_invoice_settings_payload,
            effective_category_provider=self._bank_transaction_tag_reader(),
            oa_projection=oa_workflow_adapter,
            income_status_override_provider=self._pending_invoice_command_repository.latest_income_status_override,
            relation_reader=self._workbench_relation_command_service(),
            lifecycle_policy=self._invoice_lifecycle_policy(),
        )
        self._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            import_service=self._import_service,
            relation_reader=self._workbench_relation_command_service(),
            oa_projection=oa_workflow_adapter,
            payment_rules_provider=self._input_invoice_usage_payment_rules_provider(),
            lifecycle_policy=self._invoice_lifecycle_policy(),
        )
        self._output_invoice_collection_query_service = OutputInvoiceCollectionQueryService(
            import_service=self._import_service,
            relation_reader=self._workbench_relation_command_service(),
        )
        self._pending_invoice_application_service = PendingInvoiceApplicationService(
            import_service=self._import_service,
            command_repository=self._pending_invoice_command_repository,
            audit_recorder=lambda event: record_pending_invoice_audit(self._audit_service, event),
            row_provider=lambda transaction_id, direction: self._pending_invoice_query_service.row_for_transaction(
                transaction_id,
                direction=direction,
            ),
            relation_command_service=self._workbench_relation_command_service(),
        )
        self._turnover_ledger_extra_service = self._build_turnover_ledger_extra_service(
            persisted_state.get("turnover_ledger_extras")
        )
        self._turnover_ledger_service = TurnoverLedgerService(
            import_service=self._import_service,
            category_service=self._bank_transaction_category_service,
            relation_service=self._turnover_relation_service,
            extra_service=self._turnover_ledger_extra_service,
            category_provider=self._bank_transaction_tag_reader(),
            selected_tag_codes_provider=self._app_settings_service.turnover_ledger_selected_tag_codes,
        )
        self._turnover_ledger_query_service = TurnoverLedgerQueryService(
            connection=(
                getattr(self._state_store, "_sql_read_connection", None)
                or getattr(self._state_store, "_connection", None)
            ),
            local_ledger_service=self._turnover_ledger_service,
        )
        self._tax_certified_import_service = TaxCertifiedImportService(state_store=self._state_store)
        self._etc_import_session_store = build_etc_import_session_store(self._state_store)
        self._etc_service = EtcService(
            state_store=self._state_store,
            import_session_store=self._etc_import_session_store,
            oa_prefill_provider=lambda: self._app_settings_service.get_oa_draft_prefill_configuration(
                ETC_OA_DRAFT_PREFILL_FAMILY
            ),
        )
        self._etc_service.set_canonical_invoice_key_exists(self._canonical_invoice_key_exists_for_etc_import)
        self._etc_reconciliation_task_service = EtcReconciliationTaskService(state_store=self._state_store)
        self._etc_import_preview_service = EtcImportPreviewService(
            etc_service=self._etc_service,
            task_service=self._etc_reconciliation_task_service,
            session_store=self._etc_import_session_store,
        )
        self._historical_etc_repair_service = (
            HistoricalEtcRepairService(
                state_store=self._state_store,
                etc_service=self._etc_service,
                relation_command_service=self._workbench_relation_command_service(),
                oa_row_exists=self._historical_etc_oa_row_exists,
                link_import_result_to_existing_invoices=self._link_etc_import_result_to_existing_invoices,
                link_etc_invoices_to_existing_invoices=self._link_etc_invoices_to_existing_invoices,
                refresh_after_etc_invoice_link=lambda months, reason: self._refresh_after_historical_etc_repair_link(
                    months,
                    reason=reason,
                ),
                persist_pair_relations=lambda case_ids: self._persist_workbench_pair_relations(
                    changed_case_ids=case_ids,
                ),
                persist_etc_state=lambda: self._state_store.save_etc_state(self._etc_service.snapshot()),
            )
            if self._state_store is not None
            else None
        )
        background_job_service = getattr(self, "_background_job_service", None)
        if background_job_service is None:
            background_job_service = BackgroundJobService(self._state_store)
        self._background_job_service = background_job_service
        self._import_processing_service = ImportProcessingService(
            file_import_service=self._file_import_service,
            tax_certified_import_service=self._tax_certified_import_service,
            etc_service=self._etc_service,
            etc_reconciliation_task_service=self._etc_reconciliation_task_service,
            background_job_service=self._background_job_service,
            serialize_value=self._serialize_value,
            schedule_workbench_matching_scopes=self._schedule_workbench_matching_scopes,
            persist_confirmed_import_delta=self._persist_confirmed_import_delta,
            workbench_matching_scope_months_for_import_file_session=self._workbench_matching_scope_months_for_import_file_session,
            tax_offset_scope_keys_for_import_file_session=self._tax_offset_scope_keys_for_import_file_session,
            bank_scope_keys_for_import_file_session=self._bank_scope_keys_for_import_file_session,
            input_invoice_usage_scope_keys_for_import_file_session=self._input_invoice_usage_scope_keys_for_import_file_session,
            output_invoice_collection_scope_keys_for_import_file_session=self._output_invoice_collection_scope_keys_for_import_file_session,
            link_etc_import_result_to_existing_invoices=self._link_etc_import_result_to_existing_invoices,
            etc_import_preview_service=self._etc_import_preview_service,
            oa_manual_import_create_processor=self._process_oa_manual_import_create_job,
        )
        self._app_health_service = AppHealthService()
        self._app_status_overview_service = AppStatusOverviewService()
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
                workbench_pair_snapshot_port=SettingsDataResetPairSnapshotPort(
                    pair_relation_snapshot=self._workbench_pair_relation_service.snapshot,
                ),
                tax_certified_import_service=self._tax_certified_import_service,
            )
            if self._state_store is not None
            else None
        )
        self._tax_offset_service = TaxOffsetService(
            import_service=self._import_service,
            certified_records_loader=self._tax_certified_import_service.list_records_for_month,
        )
        self._configure_tax_offset_application_services()
        self._configure_cost_statistics_application_services()
        self._workbench_pair_relation_persist_version = 0
        self._pending_workbench_pair_relation_case_ids: set[str] = set()
        self._workbench_group_detail_api_routes = self._build_workbench_group_detail_api_routes()
        self._workbench_row_detail_api_routes = self._build_workbench_row_detail_api_routes()
        self._workbench_action_api_routes = WorkbenchActionApiRoutes(
            write_facade_provider=self._workbench_write_facade,
            anomaly_review_service=self._workbench_anomaly_review_service,
        )
        self._turnover_ledger_api_routes = TurnoverLedgerApiRoutes(
            ledger_service=self._turnover_ledger_service,
            relation_service=self._turnover_relation_service,
            extra_service=self._turnover_ledger_extra_service,
            query_service=self._turnover_ledger_query_service,
            json_response=self._json_response,
            export_response=self._turnover_ledger_export_response,
            tag_selection_provider=self._app_settings_service.get_turnover_ledger_tag_selection_payload,
            mutation_session_resolver=self._turnover_mutation_session,
            session_error_detector=lambda value: isinstance(value, Response),
            load_json_body=self._load_json_body,
            tenant_id_provider=tenant_id_for_session,
            tag_selection_write_boundary_provider=self._turnover_ledger_tag_selection_request_boundary_facade,
            bank_row_tags_request_boundary_provider=self._turnover_ledger_bank_row_tags_request_boundary_facade,
            relation_extra_request_boundary_provider=self._turnover_ledger_relation_extra_request_boundary_facade,
            relation_extra_tenant_id_provider=self._workbench_reconciliation_tenant_id,
            confirm_relation_request_boundary_provider=self._turnover_ledger_confirm_request_boundary_facade,
            closure_request_boundary_provider=lambda: self._turnover_ledger_closure_request_boundary_facade(),
            withdraw_request_boundary_provider=self._turnover_ledger_withdraw_request_boundary_facade,
            write_precondition_error_payload=self._turnover_write_precondition_error_payload,
        )
    def _configure_tax_offset_application_services(self) -> None:
        tax_offset_service = getattr(self, "_tax_offset_service", None)
        connection = (
            getattr(self._state_store, "_sql_read_connection", None)
            or getattr(self._state_store, "_connection", None)
        )
        self._tax_offset_canonical_repository = (
            PostgresTaxOffsetCanonicalRepository(connection)
            if connection is not None
            else LocalTaxOffsetCanonicalRepository(tax_offset_service)
        )
        self._tax_offset_query_service = TaxOffsetQueryService(
            canonical_repository=self._tax_offset_canonical_repository,
            tax_offset_service=tax_offset_service,
        )
        self._tax_certified_import_job_service = TaxCertifiedImportJobService(
            import_job_repository_provider=self._get_import_job_repository,
        )
        self._tax_certified_import_application_service = TaxCertifiedImportApplicationService(
            certified_import_service=getattr(self, "_tax_certified_import_service", None),
            tax_offset_service=tax_offset_service,
        )
        tax_offset_plan_repository = self._tax_offset_plan_repository()
        self._tax_offset_plan_service = TaxOffsetPlanService(
            query_service=self._tax_offset_query_service,
            plan_repository=tax_offset_plan_repository,
        )
        self._tax_api_routes = TaxApiRoutes(
            tax_offset_service,
            query_service=self._tax_offset_query_service,
            certified_import_job_service=self._tax_certified_import_job_service,
            plan_service=self._tax_offset_plan_service,
            json_response=self._json_response,
            resolve_read_session=self._resolve_tax_offset_read_session,
            resolve_mutation_session=self._resolve_tax_offset_mutation_session,
            load_json_body=self._load_json_body,
            load_multipart_body=self._load_multipart_body,
            actor_id_provider=self._tax_offset_actor_id,
            certified_import_records_provider=self._tax_certified_import_application_service.records_payload,
            certified_import_preview_provider=self._tax_certified_import_application_service.preview_payload,
            import_job_processing_enabled=self._import_job_processing_enabled,
            enqueue_import_job=self._enqueue_import_process_job,
            serialize_import_job=self._serialize_import_job,
            execute_tax_certified_import_confirm=self._import_processing_service.execute_tax_certified_import_confirm,
            month_metric_emitter=self._emit_tax_offset_month_metric,
            calculate_metric_emitter=self._emit_tax_offset_calculate_metric,
            duration_ms=self._duration_ms,
        )
        self._tax_offset_dependency_key = self._tax_offset_current_dependency_key()

    def _tax_offset_current_dependency_key(self) -> tuple[int | None, ...]:
        return (
            id(getattr(self, "_tax_offset_service", None)) if getattr(self, "_tax_offset_service", None) is not None else None,
            id(getattr(self, "_tax_certified_import_service", None))
            if getattr(self, "_tax_certified_import_service", None) is not None
            else None,
            id(getattr(getattr(self, "_state_store", None), "save_tax_offset_plan", None)),
            id(self.__dict__.get("_import_job_repository")),
            id(getattr(self, "_import_job_repository_override", None)),
        )

    def _tax_offset_plan_repository(self) -> object:
        state_store = getattr(self, "_state_store", None)
        save_plan = getattr(state_store, "save_tax_offset_plan", None)
        if callable(save_plan):
            return state_store
        repository = getattr(self, "_in_memory_tax_offset_plan_repository", None)
        if repository is None:
            repository = InMemoryTaxOffsetPlanRepository()
            self._in_memory_tax_offset_plan_repository = repository
        return repository

    def _ensure_tax_offset_application_services(self) -> None:
        if (
            not isinstance(getattr(self, "_tax_api_routes", None), TaxApiRoutes)
            or getattr(self, "_tax_offset_dependency_key", None) != self._tax_offset_current_dependency_key()
        ):
            self._configure_tax_offset_application_services()

    def _tax_offset_routes(self) -> TaxApiRoutes:
        self._ensure_tax_offset_application_services()
        return self._tax_api_routes.configure_platform_ports(
            json_response=self._json_response,
            resolve_read_session=self._resolve_tax_offset_read_session,
            resolve_mutation_session=self._resolve_tax_offset_mutation_session,
            load_json_body=self._load_json_body,
            load_multipart_body=self._load_multipart_body,
            actor_id_provider=self._tax_offset_actor_id,
            certified_import_records_provider=self._tax_certified_import_application_service.records_payload,
            certified_import_preview_provider=self._tax_certified_import_application_service.preview_payload,
            import_job_processing_enabled=self._import_job_processing_enabled,
            enqueue_import_job=self._enqueue_import_process_job,
            serialize_import_job=self._serialize_import_job,
            execute_tax_certified_import_confirm=self._import_processing_service.execute_tax_certified_import_confirm,
        )

    def _tax_offset_query(self) -> TaxOffsetQueryService:
        self._ensure_tax_offset_application_services()
        return self._tax_offset_query_service

    def _configure_cost_statistics_application_services(self) -> None:
        connection = (
            getattr(self._state_store, "_sql_read_connection", None)
            or getattr(self._state_store, "_connection", None)
        )
        if connection is not None:
            canonical_repository = PostgresCostStatisticsCanonicalRepository(
                connection
            )
        else:
            canonical_repository = LocalCostStatisticsCanonicalRepository(
                bank_rows_provider=lambda: self._import_service.list_transactions(
                    month="all"
                ),
                relations_provider=(
                    self._workbench_pair_relation_service.list_active_relations
                ),
                oa_rows_by_ids_provider=self._cost_statistics_local_oa_rows_by_ids,
                settings_provider=(
                    self._state_store.load_app_settings
                    if callable(
                        getattr(self._state_store, "load_app_settings", None)
                    )
                    else self._app_settings_service.get_settings_payload
                ),
                category_provider=self._bank_transaction_effective_category_provider,
            )
        self._cost_statistics_canonical_repository = canonical_repository
        self._cost_statistics_query_service = CostStatisticsQueryService(
            canonical_repository=canonical_repository,
        )
        self._cost_statistics_api_routes = CostStatisticsApiRoutes(
            query_service=self._cost_statistics_query_service,
            json_response=self._json_response,
            file_response=self._cost_statistics_file_response,
            metric_emitter=self._emit_cost_statistics_explorer_metric,
            entry_count=CostStatisticsQueryService.explorer_entry_count,
            duration_ms=self._duration_ms,
            optional_bool_parser=lambda value: self._parse_optional_bool(value, default=True),
            app_settings_service=getattr(self, "_app_settings_service", None),
            resolve_read_session=self._resolve_cost_statistics_read_session,
            resolve_write_session=self._resolve_cost_statistics_write_session,
            load_json_body=self._load_json_body,
        )
        self._cost_statistics_dependency_key = self._cost_statistics_current_dependency_key()

    def _cost_statistics_local_oa_rows_by_ids(
        self,
        row_ids: list[str],
    ) -> list[object]:
        rows: list[object] = []
        for row_id in row_ids:
            try:
                row = self._workbench_query_service.get_row_record(row_id, month_hint="all")
                if str(row.get("workflow_status") or "completed") == "completed":
                    rows.append(row)
            except KeyError:
                continue
        return rows

    def _cost_statistics_current_dependency_key(self) -> tuple[int | None, ...]:
        return (
            id(getattr(self._state_store, "_sql_read_connection", None))
            if getattr(self._state_store, "_sql_read_connection", None)
            is not None
            else id(getattr(self._state_store, "_connection", None))
            if getattr(self._state_store, "_connection", None) is not None
            else None,
            id(getattr(self, "_import_service", None))
            if getattr(self, "_import_service", None) is not None
            else None,
            id(getattr(self, "_app_settings_service", None)) if getattr(self, "_app_settings_service", None) is not None else None,
        )

    def _ensure_cost_statistics_application_services(self) -> None:
        if (
            not hasattr(self, "_cost_statistics_api_routes")
            or getattr(self, "_cost_statistics_dependency_key", None) != self._cost_statistics_current_dependency_key()
        ):
            self._configure_cost_statistics_application_services()

    def _cost_statistics_routes(self) -> CostStatisticsApiRoutes:
        self._ensure_cost_statistics_application_services()
        return self._cost_statistics_api_routes

    def _cost_statistics_query(self) -> CostStatisticsQueryService:
        self._ensure_cost_statistics_application_services()
        return self._cost_statistics_query_service

    def _reload_runtime_services(self) -> None:
        self._initialize_runtime_services(self._runtime_bootstrap_state())

    def _bank_transaction_exists(self, transaction_id: str) -> bool:
        normalized_transaction_id = str(transaction_id or "").strip()
        if not normalized_transaction_id:
            return False
        try:
            self._import_service.get_transaction(normalized_transaction_id)
        except KeyError:
            return False
        return True

    def _turnover_bank_transaction_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        transaction_payloads: list[dict[str, object]] = []
        for transaction in list(self._import_service.list_transactions(month="all")):
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            transaction_id = str(payload.get("id") or "").strip()
            if not transaction_id:
                continue
            transaction_payloads.append(payload)
        categories_by_transaction_id = self._bank_transaction_tag_reader().bulk_get_for_rows(
            transaction_payloads
        )
        for payload in transaction_payloads:
            transaction_id = str(payload.get("id") or "").strip()
            category = categories_by_transaction_id.get(transaction_id, {})
            category_code = str(category.get("category_code") or "").strip()
            if category_code not in TURNOVER_CATEGORY_RULES:
                manual_category = self._bank_transaction_category_service.get(transaction_id)
                manual_category_code = str(manual_category.get("category_code") or "").strip()
                manual_category_source = str(manual_category.get("source") or "").strip()
                if manual_category_code in TURNOVER_CATEGORY_RULES and manual_category_source == "turnover_ledger":
                    category = manual_category
                    category_code = manual_category_code
            if category_code not in TURNOVER_CATEGORY_RULES:
                continue
            row = dict(payload)
            row["category_code"] = category_code
            row["category_label"] = category.get("category_label")
            row["category_path"] = list(category.get("category_path") or [])
            raw_category_version = (
                category.get("category_version")
                if category.get("category_version") is not None
                else category.get("manual_category_version")
            )
            if raw_category_version is None:
                raw_category_version = category.get("version")
            try:
                row["category_version"] = int(raw_category_version or 0)
            except (TypeError, ValueError):
                row["category_version"] = 0
            amount = row.get("amount") or "0.00"
            direction = str(row.get("txn_direction") or "").strip().lower()
            row["debit_amount"] = amount if direction == "outflow" else "0.00"
            row["credit_amount"] = amount if direction == "inflow" else "0.00"
            row["counterparty_name"] = str(row.get("counterparty_name_raw") or row.get("counterparty_name") or "")
            rows.append(row)
        return rows

    def _turnover_bank_selection_rows_by_ids(
        self,
        transaction_ids: list[str],
        *,
        transaction: object | None = None,
    ) -> list[dict[str, object]]:
        normalized_ids = [
            str(transaction_id).strip()
            for transaction_id in list(transaction_ids or [])
            if str(transaction_id).strip()
        ]
        if not normalized_ids:
            return []
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() == "postgres":
            if transaction is None:
                raise TurnoverLedgerWritePreconditionError(
                    error_code="turnover_bank_row_selection_unavailable",
                    message="银行流水状态校验暂不可用，请稍后重试。",
                    status_code=503,
                )
            return canonical_turnover_bank_rows_by_ids(
                transaction,
                normalized_ids,
                tenant_id=self._workbench_reconciliation_tenant_id(),
            )
        selected_ids = set(normalized_ids)
        return [
            row
            for row in self._turnover_bank_transaction_rows()
            if selected_ids.intersection(
                {
                    str(row.get("id") or "").strip(),
                    str(row.get("transaction_id") or "").strip(),
                    str(row.get("source_bank_row_id") or "").strip(),
                }
            )
        ]

    def _historical_etc_repair_seeded(self) -> bool:
        if self._state_store is None:
            return False
        try:
            return bool(self._state_store.load_historical_etc_repair_bundle_metadata())
        except Exception:
            return False

    def _maybe_reconcile_historical_etc_repair(self, *, reason: str) -> dict[str, object] | None:
        if self._historical_etc_repair_service is None or not self._historical_etc_repair_seeded():
            return None
        result = self._historical_etc_repair_service.reconcile(reason=reason)
        return self._serialize_value(result.to_payload())

    def _historical_etc_oa_row_exists(self, row_id: str) -> bool:
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id:
            return False
        canonical_rows = self._resolve_rows_from_workbench_canonical_selection(
            [normalized_row_id],
            row_types=["oa"],
        )
        return normalized_row_id in canonical_rows

    def handle_request(
        self,
        method: str,
        path: str,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
        request_id: str | None = None,
    ) -> Response:
        request_started_at = monotonic()
        route_path = self._normalize_route_path(urlparse(path).path)
        mutation_request = requires_data_mutation(method, route_path)
        request_audit_enabled = mutation_request and self._audit_service.is_durable
        effective_request_id = request_id or (uuid4().hex if request_audit_enabled else None)
        status_code = int(HTTPStatus.INTERNAL_SERVER_ERROR)
        response: Response | None = None
        request_error: Exception | None = None
        actor_token = _REQUEST_AUDIT_ACTOR.set(("", "", ""))
        request_id_token = _REQUEST_AUDIT_REQUEST_ID.set(effective_request_id)
        evidence_token = _REQUEST_AUDIT_EVIDENCE.set(None)
        with request_database_timing() as database_timing:
            try:
                response = self._handle_request_untracked(
                    method,
                    path,
                    body=body,
                    headers=headers,
                    authoritative_request_id=effective_request_id,
                )
                status_code = int(response.status_code)
                return response
            except Exception as exc:
                request_error = exc
                raise
            finally:
                actor_id, actor_name, actor_account = _REQUEST_AUDIT_ACTOR.get()
                if request_audit_enabled and actor_id and effective_request_id:
                    try:
                        page_key = self._audit_page_key_for_route(route_path)
                        semantics = operation_semantics(method, route_path, page_key=page_key)
                        self._audit_service.record_action(
                            actor_id=actor_id,
                            action=semantics.action_code,
                            entity_type=semantics.object_type,
                            entity_id=effective_request_id,
                            metadata={
                                "event_type": "operation.completed",
                                "actor_name": actor_name,
                                "actor_account": actor_account,
                                "page_key": page_key,
                                "operation_location": route_path,
                                "outcome": "success" if request_error is None and status_code < 400 else "failed",
                                "request_id": effective_request_id,
                                **semantics.audit_metadata(),
                                "status_code": status_code,
                                "evidence": _REQUEST_AUDIT_EVIDENCE.get(),
                            },
                        )
                    except Exception as exc:
                        print(
                            json.dumps(
                                {
                                    "kind": "operation_audit_completion_failed",
                                    "request_id": effective_request_id,
                                    "route_path": route_path,
                                    "error": str(exc),
                                },
                                ensure_ascii=False,
                            ),
                            flush=True,
                        )
                _REQUEST_AUDIT_ACTOR.reset(actor_token)
                _REQUEST_AUDIT_REQUEST_ID.reset(request_id_token)
                _REQUEST_AUDIT_EVIDENCE.reset(evidence_token)
                self._api_performance_recorder.record_request(
                    method=method,
                    route_path=route_path,
                    status_code=status_code,
                    duration_ms=self._duration_ms(request_started_at),
                    connection_acquire_duration_ms=database_timing.connection_acquire_duration_ms,
                    sql_execute_fetch_duration_ms=database_timing.sql_execute_fetch_duration_ms,
                    database_duration_ms=database_timing.total_duration_ms,
                    database_query_count=database_timing.query_count,
                )

    def _handle_request_untracked(
        self,
        method: str,
        path: str,
        body: str | bytes | None = None,
        headers: dict[str, str] | None = None,
        authoritative_request_id: str | None = None,
    ) -> Response:
        request_started_at = monotonic()
        parsed = urlparse(path)
        route_path = self._normalize_route_path(parsed.path)
        query = parse_qs(parsed.query)
        timed_action = self._workbench_timed_action_for_route(method=method, route_path=route_path)
        request_id = authoritative_request_id or (uuid4().hex[:12] if timed_action is not None else None)

        if method == "GET" and route_path == "/health":
            return self._json_response(HTTPStatus.OK, self._health_payload())
        if method == "GET" and route_path == "/health/ready":
            payload = self._readiness_health_payload()
            return self._json_response(
                HTTPStatus.OK if payload.get("status") == "ready" else HTTPStatus.SERVICE_UNAVAILABLE,
                payload,
            )
        if method == "GET" and route_path == "/health/deep":
            return self._json_response(
                HTTPStatus.OK,
                self._readiness_health_payload(),
            )
        if method == "GET" and route_path == "/metrics":
            return self._handle_prometheus_metrics(headers)
        if method == "OPTIONS":
            return Response(status_code=int(HTTPStatus.NO_CONTENT), body="")
        if method == "GET" and route_path == "/foundation/seed":
            return self._json_response(HTTPStatus.OK, self._seed_payload)
        access_session, auth_error = self._enforce_route_access(
            method,
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
        if requires_data_mutation(method, route_path):
            if access_session is None and self._route_has_module_owned_oa_access(route_path):
                access_session, auth_error = self._resolve_fin_ops_read_session(
                    headers,
                    denied_message="当前账户没有访问权限。",
                )
                if auth_error is not None:
                    return auth_error
            actor_id = actor_id_for_session(access_session) if access_session is not None else ""
            identity = access_session.identity if access_session is not None else None
            actor_name = str(
                getattr(identity, "display_name", "")
                or getattr(identity, "nickname", "")
                or getattr(identity, "username", "")
                or ""
            ).strip()
            actor_account = str(getattr(identity, "username", "") or "").strip()
            _REQUEST_AUDIT_ACTOR.set((actor_id, actor_name, actor_account))
            if actor_id and request_id and self._audit_service.is_durable:
                try:
                    page_key = self._audit_page_key_for_route(route_path)
                    semantics = operation_semantics(method, route_path, page_key=page_key)
                    self._audit_service.record_action(
                        actor_id=actor_id,
                        action=semantics.action_code,
                        entity_type=semantics.object_type,
                        entity_id=request_id,
                        metadata={
                            "event_type": "operation.requested",
                            "actor_name": actor_name,
                            "actor_account": actor_account,
                            "page_key": page_key,
                            "operation_location": route_path,
                            "outcome": "pending",
                            "request_id": request_id,
                            **semantics.audit_metadata(),
                        },
                    )
                except Exception as exc:
                    return self._json_response(
                        HTTPStatus.SERVICE_UNAVAILABLE,
                        {
                            "error": "operation_audit_unavailable",
                            "message": "操作审计暂不可用，本次写入未执行。",
                            "detail": str(exc),
                        },
                    )
        if method == "GET" and route_path == "/api/workbench":
            month = query.get("month", [None])[0]
            response = self._handle_api_workbench(
                month,
                paired_query=query.get("paired_query", [None])[0],
                unpaired_query=query.get("unpaired_query", [None])[0],
            )
            self._emit_workbench_api_metric(
                endpoint="/api/workbench",
                scope_key=self._workbench_metric_scope_key(month),
                status_code=response.status_code,
                duration_ms=self._duration_ms(request_started_at),
            )
            return response
        if method == "GET" and route_path == "/api/workbench/groups/detail":
            return self._handle_api_workbench_group_detail(
                query.get("month", [None])[0],
                zone=query.get("zone", [None])[0],
                group_id=query.get("group_id", [None])[0],
                detail_key=query.get("detail_key", [None])[0],
            )
        if method == "GET" and route_path == "/api/workbench/filter-options":
            month = query.get("month", [None])[0]
            response = self._handle_api_workbench_filter_options(
                month,
                zone=query.get("zone", [None])[0],
                pane=query.get("pane", [None])[0],
                facet=query.get("facet", [None])[0],
                column=query.get("column", [None])[0],
                option_search=query.get("option_search", [None])[0],
                cursor=query.get("cursor", [None])[0],
                page_size=query.get("page_size", [None])[0],
                status=query.get("status", [None])[0],
                source_kind=query.get("source_kind", [None])[0],
                search=query.get("search", [None])[0],
                column_filters=query.get("column_filters", [None])[0],
                time_filters=query.get("time_filters", [None])[0],
                exception_bucket=query.get("exception_bucket", [None])[0],
            )
            self._emit_workbench_api_metric(
                endpoint="/api/workbench/filter-options",
                scope_key=self._workbench_metric_scope_key(month),
                status_code=response.status_code,
                duration_ms=self._duration_ms(request_started_at),
            )
            return response
        if method == "GET" and route_path == "/api/workbench/groups":
            month = query.get("month", [None])[0]
            response = self._handle_api_workbench_groups(
                month,
                zone=query.get("zone", [None])[0],
                cursor=query.get("cursor", [None])[0],
                page_size=query.get("page_size", [None])[0],
                status=query.get("status", [None])[0],
                source_kind=query.get("source_kind", [None])[0],
                search=query.get("search", [None])[0],
                sort=query.get("sort", [None])[0],
                detail_level=query.get("detail_level", [None])[0],
                column_filters=query.get("column_filters", [None])[0],
                time_filters=query.get("time_filters", [None])[0],
                exception_bucket=query.get("exception_bucket", [None])[0],
            )
            self._emit_workbench_api_metric(
                endpoint="/api/workbench/groups",
                scope_key=self._workbench_metric_scope_key(month),
                status_code=response.status_code,
                duration_ms=self._duration_ms(request_started_at),
            )
            return response
        if route_path.startswith("/api/bank-details/"):
            bank_detail_response = self._bank_details_routes().route(method, route_path, query, body, headers)
            if bank_detail_response is not None:
                return bank_detail_response
        if method == "GET" and route_path == "/api/import-facts/invoices":
            return self._handle_api_import_fact_invoices(query)
        if method == "GET" and route_path == "/api/import-facts/batches":
            return self._handle_api_import_fact_batches(query)
        if method == "GET" and route_path == "/api/import-facts/files":
            return self._handle_api_import_fact_files(query)
        if route_path.startswith("/api/pending-invoices"):
            pending_invoice_response = self._pending_invoice_routes().route(method, route_path, query, body, headers)
            if pending_invoice_response is not None:
                return pending_invoice_response
        if route_path.startswith("/api/input-invoice-usage"):
            input_usage_response = self._input_invoice_usage_routes().route(method, route_path, query, body, headers)
            if input_usage_response is not None:
                return input_usage_response
        if route_path.startswith("/api/input-invoice-usage/oa-reverse"):
            oa_reverse_response = self._input_invoice_usage_oa_reverse_routes().route(method, route_path, query, body, headers)
            if oa_reverse_response is not None:
                return oa_reverse_response
        if route_path.startswith("/api/oa-pending-payments"):
            oa_pending_payment_response = self._oa_pending_payment_routes().route(method, route_path, query, body, headers)
            if oa_pending_payment_response is not None:
                return oa_pending_payment_response
        if route_path.startswith("/api/output-invoice-collections"):
            output_collection_response = self._output_invoice_collection_routes().route(method, route_path, query, body, headers)
            if output_collection_response is not None:
                return output_collection_response
        if (
            route_path == "/api/no-oa-bank-batches"
            or route_path.startswith("/api/no-oa-bank-batches/")
        ):
            no_oa_bank_batch_response = self._no_oa_bank_batch_routes().route(method, route_path, query, body, headers)
            if no_oa_bank_batch_response is not None:
                return no_oa_bank_batch_response
        if route_path == "/api/bank-flow-rule-batches" or route_path.startswith("/api/bank-flow-rule-batches/"):
            bank_flow_rule_batch_response = self._bank_flow_rule_batch_routes().route(method, route_path, query, body, headers)
            if bank_flow_rule_batch_response is not None:
                return bank_flow_rule_batch_response
        if method == "GET" and route_path == "/api/batch-accounting/tag-rules":
            return self._handle_api_batch_accounting_tag_rules(headers, access_session=access_session)
        if method == "PUT" and route_path == "/api/batch-accounting/tag-rules":
            return self._handle_api_batch_accounting_tag_rules_update(
                body,
                headers,
                access_session=access_session,
            )
        if method == "GET" and route_path == "/api/batch-accounting":
            return self._handle_api_batch_accounting(query)
        if method == "POST" and route_path == "/api/batch-accounting/submit":
            return self._handle_api_batch_accounting_submit(body, headers, access_session=access_session)
        if method == "POST" and route_path.startswith("/api/batch-accounting/") and route_path.endswith("/withdraw"):
            relation_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_batch_accounting_withdraw(
                relation_id,
                body,
                headers,
                access_session=access_session,
            )
        if route_path == "/api/turnover-ledger" or route_path.startswith("/api/turnover-ledger/"):
            turnover_ledger_response = self._turnover_ledger_api_routes.route(method, route_path, query, body, headers)
            if turnover_ledger_response is not None:
                return turnover_ledger_response
        if method == "GET" and route_path == "/api/oa-sync/status":
            return self._handle_api_oa_sync_status()
        if method == "GET" and route_path == "/api/app-health":
            return self._handle_api_app_health(headers)
        if method == "GET" and route_path == "/api/operations/app-health-dashboard":
            return self._handle_api_operations_app_health_dashboard(headers)
        if method == "GET" and route_path == "/api/operations/import-history":
            return self._handle_api_operations_import_history(query, headers)
        if (
            method == "POST"
            and route_path.startswith("/api/imports/bank-transaction-batches/")
            and route_path.endswith("/withdraw")
        ):
            batch_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_bank_import_withdrawal(
                batch_id,
                body,
                headers,
                request_id=request_id,
            )
        if method == "GET" and route_path == "/api/operations/app-health/page-audit":
            return self._handle_api_operations_page_audit(query, headers)
        if method == "GET" and route_path == "/api/operations/history":
            return self._handle_api_operation_history(query, headers)
        if method == "GET" and route_path == "/api/operations/history/actors":
            return self._handle_api_operation_history_actors(headers)
        if method == "GET" and route_path.startswith("/api/operations/history/"):
            return self._handle_api_operation_history_detail(
                unquote(route_path.rsplit("/", 1)[-1]),
                headers,
            )
        request_actor_id = (
            str(access_session.identity.username or actor_id_for_session(access_session))
            if access_session is not None
            else ""
        )
        if method == "GET" and route_path == "/api/background-jobs/active":
            return self._handle_api_background_jobs_active(request_actor_id)
        if method == "GET" and route_path.startswith("/api/background-jobs/"):
            job_id = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_background_job(job_id, request_actor_id)
        if method == "POST" and route_path.startswith("/api/background-jobs/") and route_path.endswith("/acknowledge"):
            job_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_background_job_acknowledge(job_id, request_actor_id)
        if method == "POST" and route_path.startswith("/api/background-jobs/") and route_path.endswith("/retry"):
            job_id = unquote(route_path.rsplit("/", 2)[-2])
            return self._handle_api_background_job_retry(job_id, request_actor_id)
        if route_path in {"/api/etc/import/preview", "/api/etc/import/confirm"}:
            return self._etc_import_routes().route(method, route_path, body, headers, actor_id=request_actor_id)
        if route_path == "/api/etc/reconciliation-tasks" or route_path.startswith("/api/etc/reconciliation-tasks/"):
            return self._etc_reconciliation_routes().route(method, route_path, body, headers, actor_id=request_actor_id)
        if route_path == "/api/etc/business-batches":
            return self._handle_api_etc_business_batches_route(method, query, body, headers)
        if route_path.startswith("/api/etc/business-batches/"):
            return self._route_api_etc_business_batch_v2(method, route_path, body, headers)
        if route_path == "/api/etc/invoices":
            return self._etc_invoice_routes().route(method, route_path, query, body)
        if method == "GET" and route_path == "/api/session/me":
            return self._handle_api_session_me(headers)
        if route_path == "/api/workbench/settings" or route_path.startswith("/api/workbench/settings/"):
            settings_response = self._settings_routes().route(
                method,
                route_path,
                query,
                body,
                headers,
                request_id=request_id,
            )
            if settings_response is not None:
                return settings_response
        if method == "GET" and route_path.startswith("/api/workbench/rows/"):
            row_id = unquote(route_path.rsplit("/", 1)[-1])
            return self._handle_api_workbench_row_detail(
                row_id,
                month=query.get("month", [None])[0],
                row_type=query.get("row_type", [None])[0],
            )
        if method == "POST" and route_path == "/api/workbench/exceptions/review":
            return self._handle_api_workbench_anomaly_review(
                body,
                headers=headers,
                access_session=access_session,
            )
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link":
            response = self._handle_api_workbench_confirm_link(
                body,
                request_id=request_id,
                headers=headers,
                access_session=access_session,
            )
            response.headers["X-Request-ID"] = request_id or "no-request-id"
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="confirm_link",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link/preview":
            response = self._handle_api_workbench_confirm_link_preview(body)
            response.headers["X-Request-ID"] = request_id or "no-request-id"
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="confirm_link_preview",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/cancel-link":
            response = self._handle_api_workbench_cancel_link(
                body,
                request_id=request_id,
                headers=headers,
                access_session=access_session,
            )
            response.headers["X-Request-ID"] = request_id or "no-request-id"
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="cancel_link",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/withdraw-link/preview":
            response = self._handle_api_workbench_withdraw_link_preview(body)
            response.headers["X-Request-ID"] = request_id or "no-request-id"
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="withdraw_link_preview",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/withdraw-link":
            response = self._handle_api_workbench_withdraw_link(
                body,
                request_id=request_id,
                headers=headers,
                access_session=access_session,
            )
            response.headers["X-Request-ID"] = request_id or "no-request-id"
            self._emit_workbench_action_timing(
                request_id=request_id or "no-request-id",
                action_name="withdraw_link",
                phase="request_total",
                duration_ms=self._duration_ms(request_started_at),
                status=response.status_code,
            )
            return response
        if method == "POST" and route_path == "/api/workbench/actions/confirm-cash-pass-through":
            return self._handle_api_workbench_confirm_cash_pass_through(body, request_id=request_id)
        if method == "POST" and route_path == "/api/workbench/actions/confirm-cash-ticket-purchase":
            return self._handle_api_workbench_confirm_cash_ticket_purchase(body, request_id=request_id)
        if method == "POST" and route_path == "/api/workbench/actions/cancel-cash-special":
            return self._handle_api_workbench_cancel_cash_special(body, request_id=request_id)
        if method == "POST" and route_path == "/api/workbench/actions/confirm-personal-advance-repayment":
            return self._handle_api_workbench_confirm_personal_advance_repayment(body, request_id=request_id)
        if route_path == "/api/tax-offset" or route_path.startswith("/api/tax-offset/"):
            tax_offset_response = self._tax_offset_routes().route(method, route_path, query, body, headers)
            if tax_offset_response is not None:
                return tax_offset_response
        if route_path.startswith("/api/cost-statistics/"):
            cost_statistics_response = self._cost_statistics_routes().route(method, route_path, query, body, headers)
            if cost_statistics_response is not None:
                return cost_statistics_response
        if method == "GET" and route_path == "/reconciliation/cases":
            return self._handle_reconciliation_cases()
        if method == "GET" and route_path.startswith("/reconciliation/cases/"):
            case_id = route_path.rsplit("/", 1)[-1]
            return self._handle_reconciliation_case_detail(case_id)
        if method == "GET" and route_path.startswith("/imports/batches/"):
            if route_path.endswith("/errors.csv"):
                batch_id = route_path.rsplit("/", 2)[-2]
                return self._handle_import_batch_errors_csv(batch_id)
            if route_path.endswith("/download"):
                batch_id = route_path.rsplit("/", 2)[-2]
                return self._handle_import_batch_download(batch_id)
            batch_id = route_path.rsplit("/", 1)[-1]
            return self._handle_import_batch(batch_id)
        if method == "GET" and route_path == "/imports/templates":
            return self._handle_import_templates()
        if method == "POST" and route_path == "/imports/invoices/manual/recognize":
            return self._handle_manual_invoice_recognize(body, headers)
        if method == "POST" and route_path == "/imports/invoices/manual/preview":
            return self._handle_manual_invoice_preview(body, imported_by=request_actor_id)
        if method == "POST" and route_path == "/api/workbench/oa-invoice-supplements/manual":
            return self._handle_workbench_manual_invoice_supplement(
                body,
                actor_id=request_actor_id,
                request_id=request_id,
            )
        if method == "POST" and route_path == "/api/workbench/oa-invoice-supplements/documents":
            return self._handle_workbench_supporting_document_upload(
                body,
                headers,
                actor_id=request_actor_id,
            )
        if method == "GET" and route_path == "/api/workbench/oa-invoice-supplements/documents":
            return self._handle_workbench_supporting_document_list(query)
        if method == "GET" and route_path.startswith("/api/workbench/oa-invoice-supplements/documents/") and route_path.endswith("/content"):
            document_id = route_path.removesuffix("/content").rsplit("/", 1)[-1]
            return self._handle_workbench_supporting_document_content(document_id)
        if method == "DELETE" and route_path.startswith("/api/workbench/oa-invoice-supplements/documents/"):
            document_id = route_path.rsplit("/", 1)[-1]
            return self._handle_workbench_supporting_document_delete(
                document_id,
                actor_id=request_actor_id,
            )
        if method == "POST" and route_path == "/imports/files/preview":
            return self._handle_import_file_preview(body, headers, imported_by=request_actor_id)
        if method == "POST" and route_path == "/imports/files/confirm":
            return self._handle_import_file_confirm(body, owner_user_id=request_actor_id)
        if method == "POST" and route_path == "/imports/files/retry":
            return self._handle_import_file_retry(body, owner_user_id=request_actor_id)
        if method == "POST" and route_path == "/imports/files/discard":
            return self._handle_import_file_discard(body, owner_user_id=request_actor_id)
        if method == "GET" and route_path == "/imports/files/sessions":
            return self._handle_import_file_active_sessions(query, owner_user_id=request_actor_id)
        if method == "GET" and route_path.startswith("/imports/files/sessions/"):
            session_path = route_path.removeprefix("/imports/files/sessions/")
            if session_path.endswith("/review-rows"):
                session_id = session_path.removesuffix("/review-rows").strip("/")
                return self._handle_import_file_review_rows(session_id, query, owner_user_id=request_actor_id)
            return self._handle_import_file_session(session_path, owner_user_id=request_actor_id)
        return self._json_response(
            HTTPStatus.NOT_FOUND,
            {
                "error": "not_found",
                "path": route_path,
                "message": "Route is not defined in the foundation skeleton.",
            },
        )

    def readiness_summary(
        self,
        *,
        check_dependencies: bool = True,
        lightweight_runtime: bool = False,
    ) -> dict[str, object]:
        storage_summary = {
            "mode": self._state_store.storage_mode if self._state_store is not None else "memory",
            "backend": self._state_store.storage_backend if self._state_store is not None else "memory",
            "database": self._state_store.mongo_database_name if self._state_store is not None else None,
        }
        if check_dependencies and self._state_store is not None:
            try:
                summary_provider = None
                if lightweight_runtime:
                    summary_provider = getattr(self._state_store, "ready_health_summary", None)
                if summary_provider is None:
                    summary_provider = getattr(self._state_store, "health_summary", None)
                if callable(summary_provider):
                    storage_summary.update(summary_provider())
            except Exception as exc:  # pragma: no cover - readiness should report degraded dependency state.
                storage_summary.update({"postgres_status": "error", "postgres_error": str(exc)})

        runtime_release = self._runtime_release_summary()
        production_runtime_guard = self._production_runtime_guard_summary(storage_summary, runtime_release)
        runtime_infrastructure = storage_summary.get("runtime_infrastructure")
        if not isinstance(runtime_infrastructure, dict):
            runtime_infrastructure = {}
        blockers = readiness_blockers(
            storage_backend=str(storage_summary.get("backend") or "") if check_dependencies else "",
            postgres_status=storage_summary.get("postgres_status"),
            runtime_release=runtime_release,
            production_runtime_guard=production_runtime_guard,
            runtime_infrastructure=runtime_infrastructure,
        )
        status = "ready" if not blockers else "not_ready"
        return {
            "service": "fin-ops-platform-api",
            "version": __version__,
            "status": status,
            "readiness_blockers": blockers,
            "runtime_release": runtime_release,
            "production_runtime_guard": production_runtime_guard,
            "bootstrap": {
                "mode": self._bootstrap_mode,
                "legacy_snapshot_disabled": self._bootstrap_mode != "legacy",
                "legacy_snapshot": {"allowlist_count": 0, "allowlist": []},
                "repositories": self._runtime_repositories.summary(),
            },
            "entrypoints": [
                "/health",
                "/metrics",
                "/foundation/seed",
                "/imports/templates",
                "/imports/batches/{batch_id}/download",
                "/imports/batches/{batch_id}/errors.csv",
                "/imports/files/preview",
                "/imports/files/confirm",
                "/imports/files/retry",
                "/imports/files/sessions/{session_id}",
                "/imports/invoices/manual/recognize",
                "/imports/invoices/manual/preview",
                "/api/workbench/oa-invoice-supplements/manual",
                "/api/workbench/oa-invoice-supplements/documents",
                "/api/workbench/oa-invoice-supplements/documents/{document_id}/content",
                "/api/workbench",
                "/api/workbench/groups/detail",
                "/api/bank-details/auto-tag-rules/reapply",
                "/api/bank-details/accounts",
                "/api/bank-details/transactions",
                "/api/bank-details/transactions/export",
                "/api/bank-details/transactions/{transaction_id}/category-assignment",
                "/api/pending-invoices/rows",
                "/api/pending-invoices/filter-options",
                "/api/pending-invoices/rows/{transaction_id}/relation-detail",
                "/api/pending-invoices/invoice-candidates",
                "/api/pending-invoices/bank-transactions/{bank_transaction_id}/detail",
                "/api/pending-invoices/invoices/{invoice_id}/detail",
                "/api/pending-invoices/oa/{oa_id}/detail",
                "/api/pending-invoices/rules",
                "/api/pending-invoices/income-statuses",
                "/api/pending-invoices/rows/{transaction_id}/income-status",
                "/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice/preview",
                "/api/pending-invoices/rows/{transaction_id}/attach-existing-invoice",
                "/api/pending-invoices/export-preview",
                "/api/pending-invoices/export",
                "/api/input-invoice-usage/rows",
                "/api/input-invoice-usage/filter-options",
                "/api/input-invoice-usage/export-preview",
                "/api/input-invoice-usage/export",
                "/api/input-invoice-usage/payment-status-rules",
                "/api/input-invoice-usage/oa-reverse/preview",
                "/api/input-invoice-usage/oa-reverse/staged-drafts",
                "/api/input-invoice-usage/oa-reverse/batches",
                "/api/input-invoice-usage/oa-reverse/batches/{batch_id}",
                "/api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft",
                "/api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-draft/revoke",
                "/api/input-invoice-usage/oa-reverse/batches/{batch_id}/oa-status/refresh",
                "/api/input-invoice-usage/oa-reverse/batches/{batch_id}/manual-oa-status",
                "/api/input-invoice-usage/invoices/{invoice_id}/detail",
                "/api/input-invoice-usage/bank-transactions/{bank_transaction_id}/detail",
                "/api/input-invoice-usage/oa/{oa_id}/detail",
                "/api/input-invoice-usage/rows/{row_id}/relation-details",
                "/api/oa-pending-payments/rows",
                "/api/oa-pending-payments/oa/{oa_id}/detail",
                "/api/oa-pending-payments/bank-transactions/{bank_transaction_id}/detail",
                "/api/oa-pending-payments/invoices/{invoice_id}/detail",
                "/api/oa-pending-payments/rows/{row_id}/relation-details",
                "/api/output-invoice-collections/rows",
                "/api/output-invoice-collections/filter-options",
                "/api/output-invoice-collections/invoices/{invoice_id}/detail",
                "/api/output-invoice-collections/bank-transactions/{bank_transaction_id}/detail",
                "/api/output-invoice-collections/rows/{row_id}/relation-details",
                "/api/background-jobs/active",
                "/api/background-jobs/{job_id}",
                "/api/background-jobs/{job_id}/acknowledge",
                "/api/etc/import/preview",
                "/api/etc/import/confirm",
                "/api/etc/invoices",
                "/api/etc/reconciliation-tasks/{task_id}",
                "/api/etc/reconciliation-tasks/{task_id}/ticket-root-texts",
                "/api/etc/reconciliation-tasks/{task_id}/ticket-root-files",
                "/api/etc/reconciliation-tasks/{task_id}/credit-card-statement",
                "/api/etc/reconciliation-tasks/{task_id}/supplement-evidences",
                "/api/etc/reconciliation-tasks/{task_id}/refresh-matches",
                "/api/no-oa-bank-batches",
                "/api/no-oa-bank-batches/tag-selection",
                "/api/no-oa-bank-batches/submit",
                "/api/no-oa-bank-batches/submit-selection",
                "/api/no-oa-bank-batches/{batch_id}",
                "/api/no-oa-bank-batches/{batch_id}/submit",
                "/api/no-oa-bank-batches/{batch_id}/withdraw",
                "/api/bank-flow-rule-batches",
                "/api/bank-flow-rule-batches/tag-rules",
                "/api/bank-flow-rule-batches/submit-selection",
                "/api/bank-flow-rule-batches/{batch_id}",
                "/api/bank-flow-rule-batches/{batch_id}/submit",
                "/api/bank-flow-rule-batches/{batch_id}/withdraw",
                "/api/batch-accounting",
                "/api/batch-accounting/tag-rules",
                "/api/batch-accounting/submit",
                "/api/batch-accounting/{relation_id}/withdraw",
                "/api/session/me",
                "/api/workbench/settings",
                "/api/workbench/settings/oa/manual-search",
                "/api/workbench/settings/oa/manual-search/refresh-attachments",
                "/api/workbench/settings/oa/manual-imports",
                "/api/workbench/settings/data-reset/preview",
                "/api/workbench/settings/data-reset/jobs",
                "/api/workbench/settings/data-reset/jobs/active",
                "/api/workbench/settings/data-reset/jobs/{job_id}",
                "/api/workbench/rows/{row_id}",
                "/api/workbench/actions/confirm-link",
                "/api/workbench/actions/cancel-link",
                "/api/workbench/actions/confirm-personal-advance-repayment",
                "/api/tax-offset",
                "/api/tax-offset/summary",
                "/api/tax-offset/certified-import/preview",
                "/api/tax-offset/certified-import/confirm",
                "/api/tax-offset/certified-import/jobs/{import_job_id}",
                "/api/tax-offset/certified-imports",
                "/api/tax-offset/calculate",
                "/api/tax-offset/plans",
                "/api/cost-statistics/explorer",
                "/api/cost-statistics/export-preview",
                "/api/cost-statistics/export",
                "/api/cost-statistics/bank-transactions/{transaction_id}",
                "/api/cost-statistics/allocations/{allocation_id}",
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
                "cost_statistics_foundation",
                "cost_statistics_export",
                "etc_invoice_management",
                "no_oa_bank_batch_processing",
                "background_job_foundation",
            ],
            "storage": storage_summary,
            "runtime_infrastructure": runtime_infrastructure,
            "future_modules": [],
        }

    def _production_runtime_guard_summary(
        self,
        storage_summary: dict[str, object],
        runtime_release: dict[str, object],
    ) -> dict[str, object]:
        enabled = bool(runtime_release.get("is_release_runtime")) or self._env_flag_enabled(
            PRODUCTION_RUNTIME_GUARD_ENV,
            default=False,
        )
        storage_backend = str(storage_summary.get("backend") or "").strip()
        full_snapshot_enabled = self._env_flag_enabled(POSTGRES_FULL_STATE_SNAPSHOT_ENV, default=False)
        problems: list[str] = []
        if enabled:
            if storage_backend != "postgres":
                problems.append("storage_backend_not_postgres")
            if self._bootstrap_mode == "legacy":
                problems.append("legacy_bootstrap_in_production")
            if full_snapshot_enabled:
                problems.append("postgres_full_state_snapshot_enabled")
        return {
            "enabled": enabled,
            "storage_backend": storage_backend,
            "bootstrap_mode": self._bootstrap_mode,
            "postgres_full_state_snapshot_enabled": full_snapshot_enabled,
            "consistent": not problems,
            "problems": problems,
        }

    @staticmethod
    def _env_flag_enabled(env_name: str, *, default: bool) -> bool:
        raw_value = (os.getenv(env_name) or "").strip()
        if not raw_value:
            return default
        return raw_value.lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _path_is_relative_to(path: Path, parent: Path) -> bool:
        try:
            path.relative_to(parent)
        except ValueError:
            return False
        return True

    @classmethod
    def _runtime_release_summary(cls) -> dict[str, object]:
        working_directory = Path.cwd().resolve()
        expected_source_root = (working_directory / "backend" / "src").resolve()
        package_file = Path(str(getattr(fin_ops_platform, "__file__", ""))).resolve()
        pythonpath_entries = [entry for entry in os.environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
        release_metadata_path = working_directory / "RELEASE.json"
        release_metadata: dict[str, object] | None = None
        release_metadata_error: str | None = None
        if release_metadata_path.exists():
            try:
                raw_metadata = json.loads(release_metadata_path.read_text(encoding="utf-8"))
                if isinstance(raw_metadata, dict):
                    release_metadata = raw_metadata
                else:
                    release_metadata_error = "RELEASE.json must contain an object."
            except Exception as exc:
                release_metadata_error = str(exc)

        is_release_runtime = (
            cls._path_is_relative_to(working_directory, Path("/opt/fin-ops/releases"))
            or release_metadata_path.exists()
        )
        problems: list[str] = []
        if is_release_runtime and not cls._path_is_relative_to(package_file, expected_source_root):
            problems.append("package_import_path_mismatch")
        if is_release_runtime and release_metadata is None:
            problems.append("release_metadata_missing_or_invalid")

        return {
            "working_directory": str(working_directory),
            "package_file": str(package_file),
            "expected_source_root": str(expected_source_root),
            "pythonpath": pythonpath_entries,
            "release_metadata_path": str(release_metadata_path),
            "release_metadata": release_metadata,
            "release_metadata_error": release_metadata_error,
            "is_release_runtime": is_release_runtime,
            "consistent": not problems,
            "problems": problems,
        }

    def _health_payload(self) -> dict[str, object]:
        payload = self.readiness_summary(check_dependencies=False)
        self._attach_health_metadata(payload, api_performance_endpoint_limit=HEALTH_API_PERFORMANCE_ENDPOINT_LIMIT)
        return payload

    def _readiness_health_payload(
        self,
        *,
        api_performance_endpoint_limit: int | None = HEALTH_API_PERFORMANCE_ENDPOINT_LIMIT,
        compact_payload: bool = True,
    ) -> dict[str, object]:
        payload = self.readiness_summary(lightweight_runtime=compact_payload)
        self._attach_health_metadata(payload, api_performance_endpoint_limit=api_performance_endpoint_limit)
        if compact_payload:
            compact_ready_payload(payload)
        return payload

    def _handle_prometheus_metrics(self, headers: dict[str, str] | None) -> Response:
        auth_error = self._authorize_prometheus_metrics(headers)
        if auth_error is not None:
            return auth_error
        payload = self._readiness_health_payload(
            api_performance_endpoint_limit=None,
            compact_payload=False,
        )
        return Response(
            status_code=int(HTTPStatus.OK),
            body=render_prometheus_metrics(payload),
            headers={
                "Content-Type": PROMETHEUS_CONTENT_TYPE,
            },
        )

    def _authorize_prometheus_metrics(self, headers: dict[str, str] | None) -> Response | None:
        expected_token = os.getenv(PROMETHEUS_BEARER_TOKEN_ENV, "").strip()
        if not expected_token:
            return self._plain_json_response(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "not_found",
                    "message": "Resource not found.",
                },
            )
        authorization = (get_header(headers, "authorization") or "").strip()
        provided_token = ""
        if authorization.lower().startswith(BEARER_PREFIX):
            provided_token = authorization[len(BEARER_PREFIX) :].strip()
        if not provided_token or not compare_digest(provided_token, expected_token):
            return self._plain_json_response(
                HTTPStatus.FORBIDDEN,
                {
                    "error": "forbidden",
                    "message": "Prometheus metrics token is required.",
                },
            )
        return None

    def _attach_health_metadata(
        self,
        payload: dict[str, object],
        *,
        api_performance_endpoint_limit: int | None,
    ) -> None:
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
        payload["api_performance"] = self._api_performance_recorder.summary(
            max_endpoints=api_performance_endpoint_limit,
        )
        payload["http_runtime"] = asdict(HTTP_RUNTIME_METRICS.snapshot())

    def _handle_api_workbench(
        self,
        month: str | None,
        *,
        paired_query: str | None = None,
        unpaired_query: str | None = None,
    ) -> Response:
        status_code, payload = self._workbench_read_routes().initial(
            month,
            paired_query=paired_query,
            unpaired_query=unpaired_query,
        )
        return self._json_response(status_code, payload)

    def _workbench_query_facade(self) -> WorkbenchQueryFacade:
        return WorkbenchQueryFacade(
            repository=getattr(self, "_workbench_page_query_repository", None),
            selection_repository=getattr(
                self,
                "_workbench_page_selection_repository",
                None,
            ),
        )

    def _workbench_write_facade(self) -> WorkbenchWriteFacade:
        preview_grouping = WorkbenchRelationPreviewGroupingService(
            serialize_value=self._serialize_value,
            row_type_for_row_id=self._row_type_for_row_id,
            derive_row_tags=self._derive_workbench_row_tags,
        )
        return WorkbenchWriteFacade(
            relation_read_snapshot_port=WorkbenchWriteRelationReadSnapshotPort(
                self._workbench_pair_relation_service
            ),
            relation_special_metadata_mutation_port=WorkbenchWriteRelationSpecialMetadataMutationPort(
                self._workbench_pair_relation_service
            ),
            exception_case_service=self._workbench_exception_case_service,
            next_case_id=self._next_workbench_relation_case_id,
            normalize_row_ids=self._normalize_row_ids,
            relation_preview_selection=self._workbench_query_facade().relation_preview_selection,
            expand_confirm_link_row_ids_for_existing_context=self._expand_confirm_link_row_ids_for_existing_context,
            resolve_rows_for_amount_check=self._resolve_rows_for_amount_check,
            merge_relation_snapshots=self._merge_relation_snapshots,
            synthetic_existing_case_relations=self._synthetic_existing_case_relations,
            month_scope_for_selected_row_ids=self._month_scope_for_selected_row_ids,
            scope_keys_for_row_ids=self._scope_keys_for_row_ids,
            scope_keys_for_rows=self._scope_keys_for_rows,
            resolve_live_rows_direct=self._resolve_live_rows_direct,
            relation_groups=preview_grouping.group_relations,
            withdraw_rows_and_after_relations=self._withdraw_rows_and_after_relations,
            amount_check_for_rows_by_type=self._amount_check_for_rows_by_type,
            transaction_amount_for_row_id=self._workbench_transaction_amount_for_row_id,
            save_exception_cases_snapshot=self._save_workbench_exception_cases_snapshot,
            persist_pair_relations=self._persist_workbench_pair_relations,
            restore_exception_pair_snapshots=self._restore_workbench_exception_pair_snapshots,
            schedule_pair_relation_persist=self._schedule_workbench_pair_relation_persist,
            restore_pair_relation_snapshot=self._restore_workbench_pair_relation_snapshot,
            emit_action_timing=self._emit_workbench_action_timing,
            confirm_link_uow=self._workbench_confirm_link_unit_of_work(),
            cancel_link_uow=self._workbench_cancel_link_unit_of_work(),
            withdraw_link_uow=self._workbench_withdraw_link_unit_of_work(),
            persist_pair_relations_in_transaction=self._persist_workbench_pair_relations_in_transaction,
            bank_transaction_category_codes_for_row_ids=self._bank_transaction_category_codes_for_workbench_row_ids,
            bank_flow_rule_tag_rules_payload=self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload,
            relation_command_service_factory=lambda repository=None: self._workbench_relation_command_service(
                repository=repository,
            ),
        )

    def _next_workbench_relation_case_id(self) -> str:
        allocator = WorkbenchRelationCaseIdAllocator(
            relation_snapshot_provider=self._workbench_pair_relation_service.snapshot,
            next_case_id=self._workbench_override_service._next_case_id,
        )
        return allocator.next_case_id()

    def _bank_transaction_category_codes_for_workbench_row_ids(self, row_ids: list[str]) -> dict[str, str]:
        no_oa_service = self._no_oa_bank_batch_application_service()
        rows = no_oa_service.no_oa_bank_transaction_rows_by_ids(row_ids)
        categories_by_transaction_id = no_oa_service.effective_categories_for_rows(rows)
        rows_by_id = {
            str(row.get("id") or "").strip(): row
            for row in rows
            if str(row.get("id") or "").strip()
        }
        codes: dict[str, str] = {}
        for row_id in [str(item).strip() for item in list(row_ids or []) if str(item).strip()]:
            manual_category = self._bank_transaction_category_service.get(row_id)
            manual_category_code = str(manual_category.get("category_code") or "").strip()
            if manual_category_code:
                codes[row_id] = manual_category_code
                continue
            row = rows_by_id.get(row_id)
            if not isinstance(row, dict):
                continue
            category_code = NoOaBankBatchService._category_code(row, categories_by_transaction_id)
            if category_code:
                codes[row_id] = category_code
        return codes

    def _workbench_relation_command_repository(
        self,
        *,
        repository: object | None = None,
        save_repository: bool = True,
    ) -> WorkbenchRelationCommandRepositoryAdapter:
        if repository is None and str(getattr(self._state_store, "storage_backend", "") or "") == "postgres":
            connection = getattr(self._state_store, "_connection", None)
            if connection is not None:
                repository = PostgresWorkbenchRelationRepository(connection)
        return WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=self._workbench_pair_relation_service,
            repository=repository,
            save_repository=save_repository,
        )

    def _workbench_relation_command_service(
        self,
        *,
        repository: object | None = None,
        save_repository: bool = True,
    ) -> WorkbenchRelationCommandService:
        return WorkbenchRelationCommandService(
            relation_repository=self._workbench_relation_command_repository(
                repository=repository,
                save_repository=save_repository,
            ),
            tenant_id=self._workbench_reconciliation_tenant_id(),
        )

    def _workbench_payload_relation_read_port(self) -> WorkbenchPayloadRelationReadPort:
        return WorkbenchPayloadRelationReadPort(
            self._workbench_relation_command_service()
        )

    def _workbench_relation_source_version_provider(self) -> WorkbenchRelationSourceVersionProvider:
        return WorkbenchRelationSourceVersionProvider(self._workbench_pair_relation_service.snapshot)

    def _workbench_confirm_link_context_relation_read_port(self) -> WorkbenchConfirmLinkContextRelationReadPort:
        return WorkbenchConfirmLinkContextRelationReadPort(
            self._workbench_relation_command_service()
        )

    def _turnover_workbench_relation_command_service(self, transaction: object | None = None) -> WorkbenchRelationCommandService:
        storage_backend = str(getattr(getattr(self, "_state_store", None), "storage_backend", "") or "").strip()
        repository = (
            PostgresWorkbenchRelationRepository(transaction)
            if storage_backend == "postgres" and transaction is not None
            else None
        )
        return self._workbench_relation_command_service(repository=repository)

    def _turnover_cash_closure_relation(self, case_id: str) -> dict[str, object]:
        return self._workbench_relation_command_service().get_active_relation_by_case_id(case_id)

    def _workbench_confirm_link_unit_of_work(self) -> WorkbenchWriteUnitOfWork | None:
        override = getattr(self, "_workbench_confirm_link_uow_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres":
            return None
        connection = getattr(state_store, "_connection", None)
        if connection is None:
            return None
        idempotency_store = self._workbench_write_idempotency_store(
            "_workbench_confirm_link_idempotency_store",
            connection,
        )
        return WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=self._workbench_uow_repository_factory,
            idempotency_store=idempotency_store,
        )

    def _workbench_cancel_link_unit_of_work(self) -> WorkbenchWriteUnitOfWork | None:
        override = getattr(self, "_workbench_cancel_link_uow_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres":
            return None
        connection = getattr(state_store, "_connection", None)
        if connection is None:
            return None
        idempotency_store = self._workbench_write_idempotency_store(
            "_workbench_cancel_link_idempotency_store",
            connection,
        )
        return WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=self._workbench_uow_repository_factory,
            idempotency_store=idempotency_store,
        )

    def _workbench_withdraw_link_unit_of_work(self) -> WorkbenchWriteUnitOfWork | None:
        override = getattr(self, "_workbench_withdraw_link_uow_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres":
            return None
        connection = getattr(state_store, "_connection", None)
        if connection is None:
            return None
        idempotency_store = self._workbench_write_idempotency_store(
            "_workbench_withdraw_link_idempotency_store",
            connection,
        )
        return WorkbenchWriteUnitOfWork(
            connection=connection,
            repository_factory=self._workbench_uow_repository_factory,
            idempotency_store=idempotency_store,
        )

    def _turnover_ledger_relation_extra_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        override = getattr(self, "_turnover_ledger_relation_extra_write_facade_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        support = self._turnover_ledger_local_runtime_support()
        facade = TurnoverLedgerRelationExtraPrimaryWriteFacadeBuilder(
            state_store=state_store,
            routes=self._turnover_ledger_api_routes,
            replace_snapshot=support.replace_turnover_ledger_extra_snapshot,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            extra_service=self._turnover_ledger_extra_service,
            postgres_extra_repository_factory=PostgresWorkbenchRepository,
            postgres_idempotency_store_factory=self._turnover_ledger_relation_extra_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_relation_extra_local_idempotency_store,
        ).build()
        if facade is not None:
            return facade
        return None

    def _turnover_ledger_bank_row_tags_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        override = getattr(self, "_turnover_ledger_bank_row_tags_write_facade_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        support = self._turnover_ledger_local_runtime_support()
        facade = TurnoverLedgerBankRowTagsPrimaryWriteFacadeBuilder(
            state_store=state_store,
            category_service=self._bank_transaction_category_service,
            relation_service=self._turnover_relation_service,
            bank_rows_provider=self._turnover_bank_transaction_rows,
            replace_category_snapshot=support.replace_bank_transaction_category_snapshot,
            replace_relation_snapshot=support.replace_turnover_relation_snapshot,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            persistence_repository_factory=lambda transaction: support.persistence_repository(
                transaction,
                state_store=state_store,
            ),
            category_mutation_service=self._bank_category_relation_closure_service(),
            postgres_idempotency_store_factory=self._turnover_ledger_bank_row_tags_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_bank_row_tags_local_idempotency_store,
        ).build()
        if facade is not None:
            return facade
        return None

    def _turnover_ledger_confirm_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        override = getattr(self, "_turnover_ledger_confirm_write_facade_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        support = self._turnover_ledger_local_runtime_support()
        facade = TurnoverLedgerConfirmPrimaryWriteFacadeBuilder(
            state_store=state_store,
            relation_service=self._turnover_relation_service,
            routes=self._turnover_ledger_api_routes,
            bank_rows_provider=self._turnover_bank_transaction_rows,
            bank_rows_by_ids_provider=self._turnover_bank_selection_rows_by_ids,
            replace_snapshot=support.replace_turnover_relation_snapshot,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            persistence_repository_factory=lambda transaction: support.persistence_repository(
                transaction,
                state_store=state_store,
            ),
            postgres_idempotency_store_factory=self._turnover_ledger_confirm_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_confirm_local_idempotency_store,
            rules_payload_provider=self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload,
        ).build()
        if facade is not None:
            return facade
        return None

    def _turnover_ledger_confirm_request_boundary_facade(self) -> TurnoverLedgerConfirmRequestBoundaryFacade:
        return TurnoverLedgerConfirmRequestBoundaryFacade(
            facade=self._turnover_ledger_confirm_write_facade(),
            affected_months_resolver=self._turnover_bank_transaction_affected_months,
            cash_closure_relation_provider=self._turnover_cash_closure_relation,
        )

    def _turnover_ledger_closure_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        support = self._turnover_ledger_local_runtime_support()
        facade = TurnoverLedgerConfirmPrimaryWriteFacadeBuilder(
            state_store=state_store,
            relation_service=self._turnover_relation_service,
            routes=self._turnover_ledger_api_routes,
            bank_rows_provider=self._turnover_bank_transaction_rows,
            bank_rows_by_ids_provider=self._turnover_bank_selection_rows_by_ids,
            replace_snapshot=support.replace_turnover_relation_snapshot,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            persistence_repository_factory=lambda transaction: support.persistence_repository(
                transaction,
                state_store=state_store,
            ),
            postgres_idempotency_store_factory=self._turnover_ledger_confirm_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_confirm_local_idempotency_store,
            rules_payload_provider=self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload,
            pair_snapshot_port=TurnoverLedgerLocalPairSnapshotPort(
                pair_relation_service=self._workbench_pair_relation_service,
                save_pair_snapshot=lambda snapshot: self._state_store.save_workbench_pair_relations(dict(snapshot)),
            ),
            relation_command_service_factory=self._turnover_workbench_relation_command_service,
        ).build()
        if facade is not None:
            return facade
        return None

    def _turnover_ledger_closure_request_boundary_facade(self) -> TurnoverLedgerConfirmRequestBoundaryFacade:
        return TurnoverLedgerConfirmRequestBoundaryFacade(
            facade=self._turnover_ledger_closure_write_facade(),
            affected_months_resolver=self._turnover_bank_transaction_affected_months,
            cash_closure_relation_provider=self._turnover_cash_closure_relation,
        )

    def _turnover_ledger_withdraw_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        override = getattr(self, "_turnover_ledger_withdraw_write_facade_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        support = self._turnover_ledger_local_runtime_support()
        facade = TurnoverLedgerWithdrawPrimaryWriteFacadeBuilder(
            state_store=state_store,
            relation_service=self._turnover_relation_service,
            routes=self._turnover_ledger_api_routes,
            bank_rows_provider=self._turnover_bank_transaction_rows,
            bank_rows_by_ids_provider=self._turnover_bank_selection_rows_by_ids,
            replace_snapshot=support.replace_turnover_relation_snapshot,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            persistence_repository_factory=lambda transaction: support.persistence_repository(
                transaction,
                state_store=state_store,
            ),
            postgres_idempotency_store_factory=self._turnover_ledger_withdraw_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_withdraw_local_idempotency_store,
            pair_snapshot_port=TurnoverLedgerLocalPairSnapshotPort(
                pair_relation_service=self._workbench_pair_relation_service,
                save_pair_snapshot=lambda snapshot: self._state_store.save_workbench_pair_relations(dict(snapshot)),
            ),
            relation_command_service_factory=self._turnover_workbench_relation_command_service,
        ).build()
        if facade is not None:
            return facade
        return None

    def _turnover_ledger_withdraw_request_boundary_facade(self) -> TurnoverLedgerWithdrawRequestBoundaryFacade:
        return TurnoverLedgerWithdrawRequestBoundaryFacade(
            facade=self._turnover_ledger_withdraw_write_facade(),
            relation_detail_provider=self._turnover_ledger_api_routes.get_relation,
            affected_months_resolver=self._turnover_bank_transaction_affected_months,
        )

    def _postgres_turnover_ledger_persistence_repository(
        self,
        transaction: object,
        *,
        state_store: object,
    ) -> object:
        return self._turnover_ledger_local_runtime_support().persistence_repository(
            transaction,
            state_store=state_store,
        )

    def _turnover_ledger_local_runtime_support(self) -> TurnoverLedgerLocalRuntimeSupport:
        return TurnoverLedgerLocalRuntimeSupport(
            app_settings_service=self._app_settings_service,
            bank_details_service=getattr(self, "_bank_details_service", None),
            turnover_ledger_service=getattr(self, "_turnover_ledger_service", None),
            turnover_ledger_api_routes=getattr(self, "_turnover_ledger_api_routes", None),
            live_workbench_service=getattr(self, "_live_workbench_service", None),
            category_service_from_snapshot=lambda snapshot: BankTransactionCategoryService.from_snapshot(
                dict(snapshot),
                transaction_exists=self._bank_transaction_exists,
            ),
            auto_category_service_factory=lambda category_service: BankTransactionAutoCategoryService(
                category_service=category_service,
            ),
            effective_category_provider_factory=lambda category_service, auto_category_service: BankTransactionEffectiveCategoryProvider(
                category_service=category_service,
                auto_category_service=auto_category_service,
            ),
            relation_service_from_snapshot=lambda snapshot: TurnoverRelationService.from_snapshot(
                dict(snapshot),
                bank_rows=self._turnover_bank_transaction_rows(),
            ),
            extra_service_builder=self._build_turnover_ledger_extra_service,
            emit_persistence_warning=self._emit_workbench_persistence_warning,
            postgres_repository_factory=PostgresWorkbenchRepository,
            category_service_rebinder=self._bind_local_bank_transaction_category_runtime,
            relation_service_rebinder=self._bind_local_turnover_relation_runtime,
            extra_service_rebinder=self._bind_local_turnover_ledger_extra_runtime,
        )

    def _bind_local_bank_transaction_category_runtime(
        self,
        category_service: object,
        auto_category_service: object,
        effective_category_provider: object,
    ) -> None:
        self._bank_transaction_category_service = category_service
        self._bank_transaction_auto_category_service = auto_category_service
        self._bank_transaction_effective_category_provider = effective_category_provider
        tag_reader = self._bank_transaction_tag_reader()
        if getattr(self, "_turnover_ledger_service", None) is not None:
            setattr(self._turnover_ledger_service, "_category_provider", tag_reader)
        if getattr(self, "_live_workbench_service", None) is not None:
            setattr(self._live_workbench_service, "_category_provider", tag_reader)
        if getattr(self, "_pending_invoice_query_service", None) is not None:
            setattr(self._pending_invoice_query_service, "_effective_category_provider", tag_reader)

    def _bind_local_turnover_relation_runtime(self, relation_service: object) -> None:
        self._turnover_relation_service = relation_service

    def _bind_local_turnover_ledger_extra_runtime(self, extra_service: object) -> None:
        self._turnover_ledger_extra_service = extra_service

    def _replace_local_bank_transaction_category_snapshot(self, snapshot: dict[str, object]) -> None:
        support = self._turnover_ledger_local_runtime_support()
        support.replace_bank_transaction_category_snapshot(snapshot)
        self._bank_transaction_category_service = support.category_service
        self._bank_transaction_auto_category_service = support.auto_category_service
        self._bank_transaction_effective_category_provider = support.effective_category_provider
        tag_reader = self._bank_transaction_tag_reader()
        if getattr(self, "_turnover_ledger_service", None) is not None:
            setattr(self._turnover_ledger_service, "_category_provider", tag_reader)
        if getattr(self, "_live_workbench_service", None) is not None:
            setattr(self._live_workbench_service, "_category_provider", tag_reader)
        if getattr(self, "_pending_invoice_query_service", None) is not None:
            setattr(self._pending_invoice_query_service, "_effective_category_provider", tag_reader)

    def _replace_local_turnover_relation_snapshot(self, snapshot: dict[str, object]) -> None:
        support = self._turnover_ledger_local_runtime_support()
        support.replace_turnover_relation_snapshot(snapshot)
        self._turnover_relation_service = support.relation_service

    def _save_local_bank_transaction_categories_snapshot(
        self,
        state_store: object,
        snapshot: dict[str, object],
    ) -> None:
        self._turnover_ledger_local_runtime_support().save_bank_transaction_categories_snapshot(
            state_store,
            snapshot,
        )

    def _save_local_turnover_relations_snapshot(
        self,
        state_store: object,
        snapshot: dict[str, object],
    ) -> None:
        self._turnover_ledger_local_runtime_support().save_turnover_relations_snapshot(
            state_store,
            snapshot,
        )

    def _replace_local_turnover_ledger_extra_snapshot(self, snapshot: dict[str, object]) -> None:
        support = self._turnover_ledger_local_runtime_support()
        support.replace_turnover_ledger_extra_snapshot(snapshot)
        self._turnover_ledger_extra_service = support.extra_service

    def _save_local_turnover_ledger_extras_snapshot(
        self,
        state_store: object,
        snapshot: dict[str, object],
    ) -> None:
        self._turnover_ledger_local_runtime_support().save_turnover_ledger_extras_snapshot(
            state_store,
            snapshot,
        )

    def _turnover_ledger_tag_selection_write_facade(self) -> TurnoverLedgerWriteFacade | None:
        override = getattr(self, "_turnover_ledger_tag_selection_write_facade_override", None)
        if override is not None:
            return override
        state_store = getattr(self, "_state_store", None)
        if state_store is None:
            return None
        facade = TurnoverLedgerTagSelectionPrimaryWriteFacadeBuilder(
            state_store=state_store,
            app_settings_service=self._app_settings_service,
            postgres_settings_repository_factory=lambda transaction: PostgresOpsTaxEtcRepository(transaction),
            postgres_idempotency_store_factory=self._turnover_ledger_tag_selection_postgres_idempotency_store,
            local_idempotency_store_provider=self._turnover_ledger_tag_selection_local_idempotency_store,
        ).build()
        if facade is None:
            return None
        return facade

    def _workbench_write_idempotency_store(self, attribute_name: str, connection: object) -> object:
        idempotency_store = getattr(self, attribute_name, None)
        if idempotency_store is not None:
            return idempotency_store
        state_store = getattr(self, "_state_store", None)
        idempotency_store = (
            PostgresWorkbenchIdempotencyRepository(connection)
            if isinstance(getattr(state_store, "_connection", None), PostgresConnection)
            else InMemoryWorkbenchIdempotencyRepository()
        )
        setattr(self, attribute_name, idempotency_store)
        return idempotency_store

    def _turnover_ledger_relation_extra_postgres_idempotency_store(self, connection: object) -> object:
        return self._workbench_write_idempotency_store(
            "_turnover_ledger_relation_extra_idempotency_store",
            connection,
        )

    def _turnover_ledger_relation_extra_local_idempotency_store(self) -> object:
        idempotency_store = getattr(self, "_turnover_ledger_relation_extra_idempotency_store", None)
        if idempotency_store is None:
            idempotency_store = InMemoryWorkbenchIdempotencyRepository()
            self._turnover_ledger_relation_extra_idempotency_store = idempotency_store
        return idempotency_store

    def _turnover_ledger_bank_row_tags_postgres_idempotency_store(self, connection: object) -> object:
        return self._workbench_write_idempotency_store(
            "_turnover_ledger_bank_row_tags_idempotency_store",
            connection,
        )

    def _turnover_ledger_bank_row_tags_local_idempotency_store(self) -> object:
        idempotency_store = getattr(self, "_turnover_ledger_bank_row_tags_idempotency_store", None)
        if idempotency_store is None:
            idempotency_store = InMemoryWorkbenchIdempotencyRepository()
            self._turnover_ledger_bank_row_tags_idempotency_store = idempotency_store
        return idempotency_store

    def _turnover_ledger_confirm_postgres_idempotency_store(self, connection: object) -> object:
        return self._workbench_write_idempotency_store(
            "_turnover_ledger_confirm_idempotency_store",
            connection,
        )

    def _turnover_ledger_confirm_local_idempotency_store(self) -> object:
        idempotency_store = getattr(self, "_turnover_ledger_confirm_idempotency_store", None)
        if idempotency_store is None:
            idempotency_store = InMemoryWorkbenchIdempotencyRepository()
            self._turnover_ledger_confirm_idempotency_store = idempotency_store
        return idempotency_store

    def _turnover_ledger_withdraw_postgres_idempotency_store(self, connection: object) -> object:
        return self._workbench_write_idempotency_store(
            "_turnover_ledger_withdraw_idempotency_store",
            connection,
        )

    def _turnover_ledger_withdraw_local_idempotency_store(self) -> object:
        idempotency_store = getattr(self, "_turnover_ledger_withdraw_idempotency_store", None)
        if idempotency_store is None:
            idempotency_store = InMemoryWorkbenchIdempotencyRepository()
            self._turnover_ledger_withdraw_idempotency_store = idempotency_store
        return idempotency_store

    def _turnover_ledger_tag_selection_postgres_idempotency_store(self, connection: object) -> object:
        return self._workbench_write_idempotency_store(
            "_turnover_ledger_tag_selection_idempotency_store",
            connection,
        )

    def _turnover_ledger_tag_selection_local_idempotency_store(self) -> object:
        idempotency_store = getattr(self, "_turnover_ledger_tag_selection_idempotency_store", None)
        if idempotency_store is None:
            idempotency_store = InMemoryWorkbenchIdempotencyRepository()
            self._turnover_ledger_tag_selection_idempotency_store = idempotency_store
        return idempotency_store

    def _workbench_uow_repository_factory(self, transaction: object) -> SimpleNamespace:
        workbench_repository = PostgresWorkbenchRepository(transaction)
        relation_repository = PostgresWorkbenchRelationRepository(transaction)
        return SimpleNamespace(
            pair_relations=relation_repository,
            exception_cases=workbench_repository,
            row_overrides=workbench_repository,
            canonical_query=PostgresWorkbenchPageSelectionRepository(
                transaction,
                tenant_id=self._workbench_reconciliation_tenant_id(),
            ),
        )

    def _workbench_write_response(self, result: WorkbenchWriteResult) -> Response:
        return self._json_response(result.status_code, result.payload)

    def _restore_workbench_exception_pair_snapshots(
        self,
        *,
        previous_exception_snapshot: dict[str, object],
        previous_pair_snapshot: dict[str, object],
    ) -> None:
        self._workbench_exception_rollback_restore_service().restore_pair_snapshots(
            previous_exception_snapshot=previous_exception_snapshot,
            previous_pair_snapshot=previous_pair_snapshot,
        )

    def _workbench_transaction_amount_for_row_id(self, row_id: str) -> object:
        return self._import_service.get_transaction(row_id).amount

    def _workbench_exception_rollback_restore_service(self) -> WorkbenchExceptionRollbackRestoreService:
        return WorkbenchExceptionRollbackRestoreService(
            replace_exception_case_service=self._replace_workbench_exception_case_service,
            replace_pair_relation_service=self._replace_workbench_pair_relation_service,
        )

    def _replace_workbench_exception_case_service(self, service: WorkbenchExceptionCaseService) -> None:
        self._workbench_exception_case_service = service

    def _restore_workbench_pair_relation_snapshot(
        self,
        snapshot: dict[str, object],
        *,
        changed_case_ids: list[str],
    ) -> None:
        self._workbench_pair_relation_rollback_restore_service().restore(
            snapshot,
            changed_case_ids=changed_case_ids,
        )

    def _workbench_pair_relation_rollback_restore_service(self) -> WorkbenchPairRelationRollbackRestoreService:
        return WorkbenchPairRelationRollbackRestoreService(
            state_store=self._state_store,
            replace_pair_relation_service=self._replace_workbench_pair_relation_service,
        )

    def _replace_workbench_pair_relation_service(self, service: WorkbenchPairRelationService) -> None:
        self._workbench_pair_relation_service = service
        if hasattr(self, "_workbench_pair_relation_persist_service_instance"):
            delattr(self, "_workbench_pair_relation_persist_service_instance")

    def _handle_api_workbench_groups(
        self,
        month: str | None,
        *,
        zone: str | None,
        cursor: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: str | None = None,
        time_filters: str | None = None,
        exception_bucket: str | None = None,
    ) -> Response:
        status_code, payload = self._workbench_read_routes().groups(
            month,
            zone=zone,
            cursor=cursor,
            page_size=page_size,
            status=status,
            source_kind=source_kind,
            search=search,
            sort=sort,
            detail_level=detail_level,
            column_filters=column_filters,
            time_filters=time_filters,
            exception_bucket=exception_bucket,
        )
        return self._json_response(status_code, payload)

    def _handle_api_workbench_filter_options(
        self,
        month: str | None,
        *,
        zone: str | None,
        pane: str | None,
        facet: str | None = None,
        column: str | None = None,
        option_search: str | None = None,
        cursor: str | None = None,
        page_size: str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        column_filters: str | None = None,
        time_filters: str | None = None,
        exception_bucket: str | None = None,
    ) -> Response:
        status_code, payload = self._workbench_read_routes().filter_options(
            month,
            zone=zone,
            pane=pane,
            facet=facet,
            column=column,
            option_search=option_search,
            cursor=cursor,
            page_size=page_size,
            status=status,
            source_kind=source_kind,
            search=search,
            column_filters=column_filters,
            time_filters=time_filters,
            exception_bucket=exception_bucket,
        )
        return self._json_response(status_code, payload)

    def _handle_api_workbench_anomaly_review(
        self,
        body: str | None,
        *,
        headers: dict[str, str] | None,
        access_session: OARequestSession | None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        auth_context = self._workbench_write_auth_context(headers, session=access_session)
        if isinstance(auth_context, Response):
            return auth_context
        actor_id, _tenant_id = auth_context
        status_code, result = self._workbench_action_api_routes.review_anomaly(
            payload,
            actor_id=actor_id,
        )
        return self._json_response(status_code, result)

    def _handle_api_workbench_group_detail(
        self,
        month: str | None,
        *,
        zone: str | None,
        group_id: str | None,
        detail_key: str | None = None,
    ) -> Response:
        status_code, payload = self._workbench_group_detail_routes().get_detail(
            month,
            zone=zone,
            group_id=group_id,
            detail_key=detail_key,
        )
        return self._json_response(status_code, payload)

    @staticmethod
    def _app_health_workbench_status_cache_ttl_seconds() -> float:
        raw_value = os.getenv("FIN_OPS_APP_HEALTH_WORKBENCH_STATUS_CACHE_TTL_SECONDS", "2").strip()
        try:
            return min(10.0, max(0.0, float(raw_value)))
        except ValueError:
            return 2.0

    @staticmethod
    def _app_health_dashboard_cache_ttl_seconds() -> float:
        raw_value = os.getenv("FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS", "30").strip()
        try:
            return min(120.0, max(0.0, float(raw_value)))
        except ValueError:
            return 30.0

    @staticmethod
    def _app_status_runtime_snapshot_cache_ttl_seconds() -> float:
        raw_value = os.getenv("FIN_OPS_APP_STATUS_RUNTIME_SNAPSHOT_CACHE_TTL_SECONDS", "1").strip()
        try:
            return min(5.0, max(0.0, float(raw_value)))
        except ValueError:
            return 1.0

    def _handle_api_oa_sync_status(self) -> Response:
        return self._json_response(HTTPStatus.OK, self._oa_sync_status_payload())

    def _handle_api_app_health(self, headers: dict[str, str] | None) -> Response:
        started_at = monotonic()
        session, error_response = self._resolve_app_health_session(headers)
        if error_response is not None:
            return error_response
        assert session is not None
        snapshot = self._build_app_health_snapshot(session, started_at=started_at)
        return self._json_response(HTTPStatus.OK, snapshot)

    def _handle_api_operations_app_health_dashboard(self, headers: dict[str, str] | None) -> Response:
        _, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        connection = getattr(self._state_store, "_connection", None)
        if connection is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "postgres_required",
                    "message": "AppHealth dashboard requires PostgreSQL runtime metrics.",
                },
            )
        service = OperationsDashboardService(
            connection,
            api_performance_recorder=self._api_performance_recorder,
        )
        return self._json_response(HTTPStatus.OK, self._cached_operations_app_health_dashboard_payload(service))

    def _handle_api_operations_import_history(
        self,
        query: dict[str, list[str]],
        headers: dict[str, str] | None,
    ) -> Response:
        _, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        try:
            page = max(int((query.get("page") or ["1"])[0] or 1), 1)
            page_size = min(max(int((query.get("page_size") or ["50"])[0] or 50), 1), 100)
        except ValueError:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_history_request", "message": "page and page_size must be integers."},
            )
        connection = getattr(self._state_store, "_connection", None)
        if connection is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "postgres_required", "message": "Import history requires PostgreSQL."},
            )
        payload = ImportLifecycleService(PostgresImportLifecycleRepository(connection)).list_events(
            page=page,
            page_size=page_size,
        )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_bank_import_withdrawal(
        self,
        batch_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        request_id: str | None,
    ) -> Response:
        session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        payload, body_error = self._load_json_body(body)
        if body_error is not None:
            return body_error
        raw_reason = payload.get("reason")
        if raw_reason is not None and not isinstance(raw_reason, str):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_bank_import_withdrawal", "message": "reason must be a string."},
            )
        assert session is not None
        service = self._bank_import_withdrawal_service(tenant_id=tenant_id_for_session(session))
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "postgres_required", "message": "撤回银行流水导入需要 PostgreSQL。"},
            )
        try:
            result = service.withdraw(
                batch_id=batch_id,
                actor_id=actor_id_for_session(session),
                reason=str(raw_reason or "撤回误导入的银行流水"),
                request_id=request_id,
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "bank_import_batch_not_found", "message": "未找到该银行流水导入批次。"},
            )
        except BankImportWithdrawalConflict as error:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "bank_import_withdrawal_conflict",
                    "message": str(error),
                    "blockers": error.blockers,
                },
            )
        except ValueError as error:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_bank_import_withdrawal", "message": str(error)},
            )
        with self._app_health_dashboard_cache_lock:
            self._app_health_dashboard_cache = None
        return self._json_response(HTTPStatus.OK, result)

    def _bank_import_withdrawal_service(self, *, tenant_id: str) -> BankImportWithdrawalService | Any | None:
        override = getattr(self, "_bank_import_withdrawal_service_override", None)
        if override is not None:
            return override
        connection = getattr(getattr(self, "_state_store", None), "_connection", None)
        if connection is None:
            return None
        return BankImportWithdrawalService(
            repository=PostgresBankImportWithdrawalRepository(connection),
            relation_service_for_transaction=lambda transaction: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(transaction),
                tenant_id=tenant_id,
            ),
        )

    def _operations_audit_service(self) -> OperationsAuditService | None:
        repository = getattr(getattr(self, "_runtime_repositories", None), "operations_audit_repository", None)
        if repository is None:
            return None
        return OperationsAuditService(
            repository,
            dashboard_payload_builder=lambda connection: OperationsDashboardService(
                connection,
                api_performance_recorder=self._api_performance_recorder,
            ).build_payload(),
        )

    def _handle_api_operations_page_audit(
        self,
        query: dict[str, list[str]],
        headers: dict[str, str] | None,
    ) -> Response:
        session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        page_key = _operation_text((query.get("page") or [""])[0])
        if not page_key:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "page_audit_page_required",
                    "message": "page is required.",
                },
            )
        service = self._operations_audit_service()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "postgres_required",
                    "message": "Page business audit requires PostgreSQL runtime facts.",
                },
            )
        try:
            payload = service.audit_page(
                page_key=page_key,
                tenant_id=tenant_id_for_session(session),
                sample_limit=50,
            )
        except PageAuditUnavailableError as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "page_audit_proof_unavailable",
                    "message": str(exc),
                    "page_key": page_key,
                    "overall_status": "unavailable",
                    "audit_status": {
                        "integrity": "unavailable",
                        "freshness": "unavailable",
                        "queue": "unavailable",
                    },
                },
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "unsupported_page_audit_page",
                    "message": str(exc),
                },
            )
        except Exception as exc:
            return self._json_response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "error": "page_audit_failed",
                    "message": str(exc) or "Page business audit failed.",
                },
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_operation_history(
        self,
        query: dict[str, list[str]],
        headers: dict[str, str] | None,
    ) -> Response:
        admin_session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        service = self._operations_audit_service()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "postgres_required", "message": "操作历史需要 PostgreSQL。"},
            )
        def value(key: str) -> str | None:
            return (query.get(key) or [None])[0]
        try:
            payload = service.list_operation_history(
                limit=int(value("limit") or 50),
                cursor=value("cursor"),
                actor_id=value("actor_id"),
                action=value("action"),
                page_key=value("page_key"),
                object_type=value("object_type"),
                outcome=value("outcome"),
                date_from=value("date_from"),
                date_to=value("date_to"),
                search=value("search"),
                known_actor=self._operation_history_actor(admin_session),
            )
        except (TypeError, ValueError) as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_operation_history_query", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, payload)

    def _handle_api_operation_history_actors(self, headers: dict[str, str] | None) -> Response:
        admin_session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        service = self._operations_audit_service()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "postgres_required", "message": "操作历史需要 PostgreSQL。"},
            )
        return self._json_response(
            HTTPStatus.OK,
            service.list_operation_history_actors(known_actor=self._operation_history_actor(admin_session)),
        )

    def _handle_api_operation_history_detail(
        self,
        operation_key: str,
        headers: dict[str, str] | None,
    ) -> Response:
        admin_session, admin_error = self._resolve_admin_session(headers)
        if admin_error is not None:
            return admin_error
        service = self._operations_audit_service()
        if service is None:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "postgres_required", "message": "操作历史需要 PostgreSQL。"},
            )
        try:
            operation = service.get_operation_history(
                operation_key,
                known_actor=self._operation_history_actor(admin_session),
            )
        except ValueError:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_operation_history_key", "message": "操作记录编号无效。"},
            )
        if operation is None:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "audit_event_not_found", "message": "操作记录不存在。"},
            )
        return self._json_response(HTTPStatus.OK, {"operation": operation})

    @staticmethod
    def _operation_history_actor(session: object | None) -> dict[str, str] | None:
        if session is None:
            return None
        identity = getattr(session, "identity", None)
        return {
            "actor_id": actor_id_for_session(session),
            "actor_name": str(
                getattr(identity, "display_name", "")
                or getattr(identity, "nickname", "")
                or getattr(identity, "username", "")
                or ""
            ).strip(),
            "actor_account": str(getattr(identity, "username", "") or "").strip(),
        }

    def _cached_operations_app_health_dashboard_payload(self, service: OperationsDashboardService) -> dict[str, object]:
        ttl_seconds = self._app_health_dashboard_cache_ttl_seconds()
        if ttl_seconds <= 0:
            return service.build_payload()
        cached_entry = self._app_health_dashboard_cache_entry()
        cached_payload = cached_entry[0] if cached_entry is not None else None
        if cached_entry is not None and cached_entry[1]:
            return cached_payload
        try:
            payload = service.build_payload()
        except Exception:
            if cached_payload is not None:
                return self._app_health_dashboard_stale_payload(cached_payload)
            raise
        expires_at = monotonic() + ttl_seconds
        with self._app_health_dashboard_cache_lock:
            self._app_health_dashboard_cache = (expires_at, deepcopy(payload))
        return payload

    def _app_health_dashboard_cache_entry(self) -> tuple[dict[str, object], bool] | None:
        now = monotonic()
        with self._app_health_dashboard_cache_lock:
            cached = self._app_health_dashboard_cache
        if not isinstance(cached, tuple) or len(cached) != 2:
            return None
        expires_at, payload = cached
        if not isinstance(expires_at, (int, float)) or not isinstance(payload, dict):
            return None
        return deepcopy(payload), now < float(expires_at)

    @staticmethod
    def _app_health_dashboard_stale_payload(payload: dict[str, object]) -> dict[str, object]:
        stale_payload = deepcopy(payload)
        freshness = stale_payload.get("freshness") if isinstance(stale_payload.get("freshness"), dict) else {}
        freshness = dict(freshness)
        warnings = [str(item) for item in list(freshness.get("warnings") or [])]
        if "dashboard_cache_stale_after_error" not in warnings:
            warnings.append("dashboard_cache_stale_after_error")
        freshness["warnings"] = sorted(set(warnings))
        stale_payload["freshness"] = freshness
        return stale_payload

    def _resolve_app_health_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        try:
            session = self._resolve_request_session(headers)
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
        active_jobs, attention_jobs = self._background_job_service.list_app_health_jobs(
            owner_user_id,
            include_system=True,
        )
        runtime_statuses = self._app_status_runtime_statuses()
        oa_sync_payload = self._app_health_oa_sync_payload(runtime_statuses=runtime_statuses)
        state_store_info = {
            "storage_mode": self._state_store.storage_mode if self._state_store is not None else "memory",
            "backend": self._state_store.storage_backend if self._state_store is not None else "memory",
        }
        snapshot = self._app_health_service.build_snapshot(
            session=session,
            active_jobs=active_jobs,
            oa_sync_payload=oa_sync_payload,
            state_store_info=state_store_info,
            rebuild_scheduled=self._is_oa_sync_rebuild_scheduled(),
            duration_ms=self._duration_ms(started_at),
            attention_jobs=attention_jobs,
            alerts={"active": [], "recent_recovered": []},
        )
        previous_alert_snapshot = self._app_health_alert_service.snapshot()
        alerts = self._app_health_alert_service.evaluate(snapshot)
        current_alert_snapshot = self._app_health_alert_service.snapshot()
        if self._state_store is not None and current_alert_snapshot != previous_alert_snapshot:
            self._state_store.save_app_health_alerts(current_alert_snapshot)
        snapshot["alerts"] = alerts
        metrics = snapshot.get("metrics") if isinstance(snapshot.get("metrics"), dict) else {}
        metrics["active_alert_count"] = len(alerts.get("active", [])) if isinstance(alerts, dict) else 0
        snapshot["metrics"] = metrics
        snapshot["app_status"] = self._app_status_overview_service.build_overview(
            session=session,
            active_jobs=active_jobs,
            attention_jobs=attention_jobs,
            app_health_snapshot=snapshot,
            worker_statuses=runtime_statuses["worker_statuses"],
            outbox_statuses=runtime_statuses["outbox_statuses"],
        )
        self._emit_app_health_timing(snapshot)
        return snapshot

    def _app_status_runtime_statuses(self) -> dict[str, dict[str, dict[str, object]]]:
        snapshot_provider = getattr(self._state_store, "app_status_runtime_snapshot", None) if self._state_store is not None else None
        if not callable(snapshot_provider):
            return {
                "worker_statuses": {},
                "outbox_statuses": {},
            }
        ttl_seconds = self._app_status_runtime_snapshot_cache_ttl_seconds()
        cache_lock = getattr(self, "_app_status_runtime_snapshot_cache_lock", None)

        def load_snapshot() -> dict[str, object]:
            now = monotonic()
            cached = getattr(self, "_app_status_runtime_snapshot_cache", None)
            if isinstance(cached, tuple) and len(cached) == 2:
                expires_at, payload = cached
                if isinstance(expires_at, (int, float)) and now < float(expires_at) and isinstance(payload, dict):
                    return deepcopy(payload)
            snapshot = snapshot_provider()
            normalized = snapshot if isinstance(snapshot, dict) else {
                "worker_statuses": {},
                "outbox_statuses": {},
            }
            self._app_status_runtime_snapshot_cache = (
                monotonic() + ttl_seconds,
                deepcopy(normalized),
            )
            return normalized

        if ttl_seconds > 0 and cache_lock is not None:
            with cache_lock:
                return load_snapshot()
        if ttl_seconds > 0:
            return load_snapshot()
        snapshot = snapshot_provider()
        return snapshot if isinstance(snapshot, dict) else {
            "worker_statuses": {},
            "outbox_statuses": {},
        }

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

    def _oa_sync_status_payload(
        self,
        *,
        runtime_statuses: dict[str, dict[str, dict[str, object]] | None] | None = None,
    ) -> dict[str, object]:
        resolved_runtime_statuses = (
            runtime_statuses if runtime_statuses is not None else self._app_status_runtime_statuses()
        )
        outbox_statuses = resolved_runtime_statuses.get("outbox_statuses")
        worker_statuses = resolved_runtime_statuses.get("worker_statuses")
        outbox_payload = (
            outbox_statuses.get("oa.sync")
            if isinstance(outbox_statuses, dict) and isinstance(outbox_statuses.get("oa.sync"), dict)
            else {}
        )
        worker_payload = (
            worker_statuses.get("oa-sync")
            if isinstance(worker_statuses, dict) and isinstance(worker_statuses.get("oa-sync"), dict)
            else {}
        )
        successful_run_statuses = {"success", "succeeded", "done"}
        latest_run = self._postgres_oa_projection_latest_sync_run() or {}
        outbox_status = str(outbox_payload.get("status") or "").strip().lower()
        worker_status = str(worker_payload.get("status") or "").strip().lower()
        run_status = str(latest_run.get("status") or "").strip().lower()
        dirty_scopes = self._oa_sync_dirty_scopes_from_outbox(outbox_payload)
        last_synced_at = (
            str(latest_run.get("finished_at") or latest_run.get("started_at") or "").strip()
            if run_status in successful_run_statuses
            else ""
        ) or None

        if outbox_status in {"pending", "processing", "publishing"}:
            status = "refreshing"
            message = "OA 同步任务已入队或正在执行。"
        elif outbox_status in {"failed", "dead_lettered", "publish_failed"}:
            status = "error"
            message = str(outbox_payload.get("last_error") or "OA 同步任务失败。")
        elif worker_status in {"missing", "mismatch", "unavailable", "stale"}:
            status = "error"
            warning = str(worker_payload.get("warning_code") or worker_status).strip()
            message = f"OA 同步 worker 不可用：{warning}"
        elif run_status in {"failed", "error"}:
            status = "error"
            message = str(latest_run.get("last_error") or "最近一次 OA 同步失败。")
        elif run_status in successful_run_statuses:
            status = "synced"
            message = "OA 已同步。"
        elif latest_run:
            status = "unknown"
            message = "最近一次 OA 同步状态未知。"
        else:
            status = "unknown"
            message = "尚无 OA 同步运行记录。"

        payload: dict[str, object] = {
            "status": status,
            "message": message,
            "dirty_scopes": dirty_scopes,
            "last_synced_at": last_synced_at,
        }
        if outbox_status:
            payload["outbox_status"] = outbox_status
        if worker_status:
            payload["worker_status"] = worker_status
        if latest_run.get("id"):
            payload["last_run_id"] = latest_run.get("id")
        if latest_run.get("upserted_count") is not None:
            payload["last_upserted_count"] = latest_run.get("upserted_count")
        if latest_run.get("scanned_count") is not None:
            payload["last_scanned_count"] = latest_run.get("scanned_count")
        return payload

    @staticmethod
    def _oa_sync_dirty_scopes_from_outbox(outbox_payload: object) -> list[str]:
        if not isinstance(outbox_payload, dict):
            return []
        scopes: list[str] = []
        for entry in list(outbox_payload.get("scopes") or []):
            if not isinstance(entry, dict):
                continue
            scope_key = str(entry.get("scope_key") or "").strip()
            if scope_key:
                scopes.append(scope_key)
        if not scopes:
            scope_key = str(outbox_payload.get("scope_key") or "").strip()
            if scope_key:
                scopes.append(scope_key)
        if any(scope != "all" for scope in scopes):
            scopes.append("all")
        return sorted(dict.fromkeys(scopes))

    def _app_health_oa_sync_payload(
        self,
        *,
        runtime_statuses: dict[str, dict[str, dict[str, object]] | None] | None = None,
    ) -> dict[str, object]:
        payload = self._serialize_value(self._oa_sync_status_payload(runtime_statuses=runtime_statuses))
        if not isinstance(payload, dict):
            payload = {}
        matching_queue = getattr(self, "_workbench_reconciliation_dirty_queue", None)
        matching_dirty_scopes = (
            [
                entry
                for entry in matching_queue.list_dirty_scopes()
                if isinstance(entry, dict)
                and str(entry.get("status") or "dirty").strip().lower()
                in {"dirty", "retry", "processing", "failed"}
            ]
            if matching_queue is not None
            else []
        )
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
        return False

    def _workbench_oa_sync_safety_guard(self, payload: dict[str, object]) -> Response | None:
        oa_sync_payload = self._oa_sync_status_payload()
        dirty_scopes = [
            str(scope)
            for scope in list(oa_sync_payload.get("dirty_scopes", []) or [])
            if str(scope).strip()
        ]
        oa_sync_status = str(oa_sync_payload.get("status") or "").strip().lower()
        if (
            oa_sync_status in {"ready", "synced"}
            and not dirty_scopes
            and not self._is_oa_sync_rebuild_scheduled()
        ):
            return None
        return self._json_response(
            HTTPStatus.CONFLICT,
            {
                "error": "workbench_stale",
                "message": "OA 正在同步，请刷新完成后再操作。",
                "oa_sync_status": oa_sync_status or "unknown",
                "dirty_scopes": dirty_scopes,
            },
        )

    def _etc_invoice_routes(self) -> EtcInvoiceApiRoutes:
        routes = getattr(self, "_etc_invoice_api_routes", None)
        if isinstance(routes, EtcInvoiceApiRoutes):
            return routes
        routes = EtcInvoiceApiRoutes(
            etc_service=self._etc_service,
            json_response=self._json_response,
            serialize_invoice=self._serialize_etc_invoice,
        )
        self._etc_invoice_api_routes = routes
        return routes

    def _etc_import_routes(self) -> EtcImportApiRoutes:
        routes = getattr(self, "_etc_import_api_routes", None)
        if isinstance(routes, EtcImportApiRoutes):
            return routes
        routes = EtcImportApiRoutes(
            preview_service=self._etc_import_preview_service,
            background_job_service=self._background_job_service,
            json_response=self._json_response,
            load_json_body=self._load_json_body,
            load_multipart_body=self._load_multipart_body,
            reconciliation_error_response=self._reconciliation_error_response,
            enqueue_import_job=self._enqueue_import_process_job,
            serialize_import_job=self._serialize_import_job,
        )
        self._etc_import_api_routes = routes
        return routes

    def _etc_reconciliation_routes(self) -> EtcReconciliationTaskApiRoutes:
        routes = getattr(self, "_etc_reconciliation_task_api_routes", None)
        if isinstance(routes, EtcReconciliationTaskApiRoutes):
            return routes
        payload_facade = self._etc_reconciliation_task_payload_facade()
        routes = EtcReconciliationTaskApiRoutes(
            task_service=self._etc_reconciliation_task_service,
            json_response=self._json_response,
            load_json_body=self._load_json_body,
            load_multipart_body=self._load_multipart_body,
            task_payload=payload_facade.task_payload,
            unavailable_task_payload=payload_facade.unavailable_task_payload,
            cleanup_service=self._etc_reconciliation_import_cleanup_service(),
            expected_version_from_payload=self._expected_version_from_payload,
            expected_version_from_fields=self._expected_version_from_fields,
            reconciliation_error_response=self._reconciliation_error_response,
            reconciliation_storage_error_response=self._reconciliation_storage_error_response,
            refresh_after_etc_invoice_link=lambda changed_months, reason: self._refresh_after_etc_invoice_link(
                changed_months,
                reason=reason,
            ),
            persist_state=self._persist_state,
            source_upload_service=self._etc_reconciliation_source_upload_service(),
        )
        self._etc_reconciliation_task_api_routes = routes
        return routes

    def _etc_reconciliation_source_upload_service(self) -> EtcReconciliationSourceUploadService:
        service = getattr(self, "_etc_reconciliation_source_upload", None)
        if isinstance(service, EtcReconciliationSourceUploadService):
            return service
        service = EtcReconciliationSourceUploadService(task_service=self._etc_reconciliation_task_service)
        self._etc_reconciliation_source_upload = service
        return service

    def _etc_reconciliation_import_cleanup_service(self) -> EtcReconciliationImportCleanupService:
        service = getattr(self, "_etc_reconciliation_import_cleanup", None)
        if isinstance(service, EtcReconciliationImportCleanupService):
            return service
        service = EtcReconciliationImportCleanupService(
            etc_service=self._etc_service,
            reconciliation_task_service=self._etc_reconciliation_task_service,
            existing_etc_invoices_by_ids=self._existing_etc_invoices_by_ids,
            etc_invoice_changed_months=self._etc_invoice_changed_months,
            link_etc_invoices_to_existing_invoices=self._link_etc_invoices_to_existing_invoices,
            etc_import_batch_by_id=self._etc_import_batch_by_id,
            assert_etc_summary_relation_write_precondition_for_batch=self._assert_etc_summary_relation_write_precondition_for_batch,
            cancel_etc_summary_relations_for_batch=self._cancel_etc_summary_relations_for_batch,
        )
        self._etc_reconciliation_import_cleanup = service
        return service

    def _etc_business_batch_delete_service(self) -> EtcBusinessBatchDeleteService:
        service = getattr(self, "_etc_business_batch_delete", None)
        if isinstance(service, EtcBusinessBatchDeleteService):
            return service
        service = EtcBusinessBatchDeleteService(
            etc_service=self._etc_service,
            reconciliation_task_service=self._etc_reconciliation_task_service,
            cleanup_service=self._etc_reconciliation_import_cleanup_service(),
            existing_etc_invoices_by_ids=self._existing_etc_invoices_by_ids,
            etc_invoice_changed_months=self._etc_invoice_changed_months,
            link_etc_invoices_to_existing_invoices=self._link_etc_invoices_to_existing_invoices,
            assert_etc_summary_relation_write_precondition_for_batch=self._assert_etc_summary_relation_write_precondition_for_batch,
            cancel_etc_summary_relations_for_batch=self._cancel_etc_summary_relations_for_batch,
        )
        self._etc_business_batch_delete = service
        return service

    def _etc_reconciliation_task_payload_facade(self) -> EtcReconciliationTaskPayloadFacade:
        facade = getattr(self, "_etc_reconciliation_task_payload_read", None)
        if isinstance(facade, EtcReconciliationTaskPayloadFacade):
            return facade
        facade = EtcReconciliationTaskPayloadFacade(
            etc_import_batch_by_id=self._etc_import_batch_by_id,
            serialize_value=self._serialize_value,
        )
        self._etc_reconciliation_task_payload_read = facade
        return facade

    def _etc_import_batch_by_id(self, batch_id: str) -> object | None:
        normalized_batch_id = str(batch_id or "").strip()
        if not normalized_batch_id:
            return None
        for import_batch in self._etc_service.list_import_batches():
            if str(getattr(import_batch, "id", "") or "") == normalized_batch_id:
                return import_batch
        return None

    def _etc_business_batch_summary_row_ids(self, batch: object) -> list[str]:
        external_ids = {
            str(getattr(batch, "external_etc_batch_id", "") or "").strip(),
            str(getattr(batch, "submission_batch_id", "") or "").strip(),
            str(getattr(batch, "business_batch_id", "") or "").strip(),
        }
        return [
            self._etc_invoice_summary_row_id(external_id)
            for external_id in sorted(external_ids)
            if external_id
        ]

    def _cancel_etc_summary_relations_for_batch(self, batch: object) -> list[str]:
        summary_row_ids = self._etc_business_batch_summary_row_ids(batch)
        if not summary_row_ids:
            return []
        command_service = self._workbench_relation_command_service()
        cancel_for_row_ids = getattr(command_service, "cancel_relations_for_row_ids", None)
        if callable(cancel_for_row_ids):
            result = cancel_for_row_ids(
                row_ids=summary_row_ids,
                actor_id="system",
                reason="ETC业务批次删除，取消对应 summary 关联。",
                history_operation_type="etc_summary_unmerged",
            )
        else:
            result = self._cancel_etc_summary_relations_for_row_ids(
                summary_row_ids,
                command_service=command_service,
            )
        raw_changed_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
        changed_case_ids = [
            str(case_id).strip()
            for case_id in list(raw_changed_case_ids or [])
            if str(case_id).strip()
        ]
        if not changed_case_ids:
            return []
        self._persist_workbench_pair_relations(changed_case_ids=changed_case_ids)
        raw_affected_months = result.get("affected_months") if isinstance(result, dict) else []
        changed_months = [
            str(month).strip()
            for month in list(raw_affected_months or [])
            if str(month).strip() and str(month).strip().lower() != "all"
        ]
        return sorted(set(changed_months))

    def _assert_etc_summary_relation_write_precondition_for_batch(self, batch: object) -> None:
        return None

    @staticmethod
    def _etc_business_batch_relation_month_scope(batch: object) -> str:
        amount_breakdown = getattr(batch, "amount_breakdown", None)
        if isinstance(amount_breakdown, dict):
            scope_month = str(amount_breakdown.get("scope_month") or "").strip()
            if len(scope_month) == 7 and scope_month[4:5] == "-":
                return scope_month
        return "all"

    def _cancel_etc_summary_relations_for_row_ids(
        self,
        summary_row_ids: list[str],
        *,
        command_service: object,
    ) -> dict[str, object]:
        summary_row_id_set = {str(row_id).strip() for row_id in list(summary_row_ids or []) if str(row_id).strip()}
        active_relations = getattr(command_service, "active_relations_for_row_ids", None)
        if not callable(active_relations):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service does not expose active_relations_for_row_ids.",
            )
        relations = [
            dict(relation)
            for relation in list(active_relations(list(summary_row_id_set)) or [])
            if isinstance(relation, dict)
            if summary_row_id_set.intersection(
                {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
            )
        ]
        changed_case_ids: list[str] = []
        affected_months: list[str] = []
        cancel_relation = getattr(command_service, "cancel_relation", None)
        if not callable(cancel_relation):
            raise WorkbenchRelationCommandError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service does not expose cancel_relation.",
            )
        for relation in relations:
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id:
                continue
            result = cancel_relation(
                case_id=case_id,
                actor_id="system",
                reason="ETC业务批次删除，取消对应 summary 关联。",
                history_operation_type="etc_summary_unmerged",
            )
            raw_result_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
            changed_case_ids.extend(
                str(item).strip()
                for item in list(raw_result_case_ids or [])
                if str(item).strip()
            )
            raw_result_months = result.get("affected_months") if isinstance(result, dict) else []
            affected_months.extend(
                str(item).strip()
                for item in list(raw_result_months or [])
                if str(item).strip()
            )
        return {
            "changed_case_ids": list(dict.fromkeys(changed_case_ids)),
            "affected_months": list(dict.fromkeys(affected_months)),
        }

    @staticmethod
    def _expected_version_from_payload(payload: dict[str, object]) -> int:
        raw_value = payload.get("expectedVersion", payload.get("expected_version"))
        if raw_value in (None, ""):
            raise ValueError("expected_version_required")
        try:
            return int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_expected_version") from exc

    @staticmethod
    def _expected_version_from_fields(fields: dict[str, list[str]]) -> int:
        values = fields.get("expectedVersion") or fields.get("expected_version") or []
        raw_value = values[0] if values else None
        if raw_value in (None, ""):
            raise ValueError("expected_version_required")
        try:
            return int(raw_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_expected_version") from exc

    def _reconciliation_error_response(self, error: ValueError) -> Response:
        code = str(error) or "invalid_reconciliation_request"
        if code.startswith("document_"):
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_document_upload",
                    "message": "文件格式、签名或资源大小不符合上传要求，请上传有效的 TXT、PDF、JPG 或 PNG 文件。",
                },
            )
        status = HTTPStatus.CONFLICT if code in {
            "task_version_conflict",
            "stale_reconciliation_task_preview",
            "invalid_reconciliation_task_status",
            "reconciliation_task_has_submission_link",
            "reconciliation_task_import_cleanup_required",
            "ticket_root_source_mode_conflict",
            "ticket_root_source_mode_conflict_pdf",
            "ticket_root_source_mode_conflict_text_file",
            "ticket_root_source_mode_conflict_mixed_upload",
            "source_file_deleted_during_parse",
        } else HTTPStatus.BAD_REQUEST
        messages = {
            "ticket_root_source_mode_conflict": "已有手工粘贴票根网源，请先删除已有票根来源后才能切换导入方式。",
            "ticket_root_source_mode_conflict_pdf": "已有票根网 PDF/JPG 源文件，请先删除已有票根来源后才能切换导入方式。",
            "ticket_root_source_mode_conflict_text_file": "已有票根网 TXT 源文件，请先删除已有票根来源后才能切换导入方式。",
            "ticket_root_source_mode_conflict_mixed_upload": "票根网 TXT 文件和 PDF/JPG 不能同时上传，请先选择一种票根来源导入方式。",
            "reconciliation_task_has_submission_link": "已确认提交 OA 或存在不可删除的提交链路，不能删除。",
            "supplement_amount_delta_note_required": "补充凭证金额与信用卡项不一致或无法识别金额，请填写差异说明。",
            "credit_card_item_already_covered": "该信用卡项已有关联票根或补充凭证。",
            "credit_card_item_already_resolved": "该信用卡项已有处理结果，不能直接上传补充凭证覆盖。",
            "linked_supplement_evidence_required": "补充凭证覆盖项缺少已关联的补充凭证。",
            "duplicate_supplement_evidence_file": "该补充凭证文件已经上传。",
            "source_file_deleted_during_parse": "源文件在解析完成前已被删除，请重新上传。",
        }
        normalized_code = "ticket_root_source_mode_conflict" if code.startswith("ticket_root_source_mode_conflict") else code
        return self._json_response(status, {"error": normalized_code, "message": messages.get(code, code)})

    def _reconciliation_storage_error_response(self, error: ObjectStorageWriteError) -> Response:
        return self._json_response(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "reconciliation_file_storage_unavailable",
                "message": "文件存储暂时不可用，上传未保存。请稍后重试或联系管理员检查对象存储配置。",
            },
        )

    def _handle_api_background_jobs_active(self, owner_user_id: str) -> Response:
        active_jobs = self._background_job_service.list_active_jobs(owner_user_id, include_system=True)
        attention_jobs = self._background_job_service.list_attention_jobs(owner_user_id, include_system=True)
        active_payloads = [self._serialize_background_job(job) for job in active_jobs]
        attention_payloads = [self._serialize_background_job(job) for job in attention_jobs]
        jobs = AppHealthService._combine_job_payloads(active_payloads, attention_payloads)
        return self._json_response(
            HTTPStatus.OK,
            {
                "jobs": jobs,
                "active_jobs": active_payloads,
                "attention_jobs": attention_payloads,
            },
        )

    def _handle_api_background_job(self, job_id: str, owner_user_id: str) -> Response:
        try:
            job = self._background_job_service.get_job(job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "background_job_not_found", "message": "后台任务不存在或不可见。"},
            )
        return self._json_response(HTTPStatus.OK, {"job": self._serialize_background_job(job)})

    def _handle_api_background_job_acknowledge(self, job_id: str, owner_user_id: str) -> Response:
        try:
            job = self._background_job_service.acknowledge_job(job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "background_job_not_found", "message": "后台任务不存在或不可见。"},
            )
        return self._json_response(HTTPStatus.OK, {"job": self._serialize_background_job(job)})

    def _handle_api_background_job_retry(self, job_id: str, owner_user_id: str) -> Response:
        try:
            job = self._background_job_service.get_job(job_id, owner_user_id)
        except (BackgroundJobNotFoundError, BackgroundJobAccessError):
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "background_job_not_found", "message": "后台任务不存在或不可见。"},
            )
        if job.type == "file_import":
            return self._retry_file_import_background_job(job, owner_user_id)
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {"error": "background_job_retry_not_supported", "message": "当前后台任务没有可用的重新执行入口。"},
        )

    @staticmethod
    def _serialize_background_job(job) -> dict[str, object]:
        return AppHealthService._job_payload(job)

    def _retry_file_import_background_job(self, job, owner_user_id: str) -> Response:
        self._reload_file_import_runtime_state()
        source = job.source if isinstance(job.source, dict) else {}
        session_id = str(source.get("session_id") or "").strip()
        selected_file_ids = [
            str(file_id).strip()
            for file_id in list(source.get("selected_file_ids") or [])
            if str(file_id).strip()
        ]
        if not session_id or not selected_file_ids:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "background_job_retry_not_supported", "message": "导入任务缺少重新执行所需的 session_id 或 selected_file_ids。"},
            )
        try:
            session = self._file_import_service.get_session(session_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": "导入会话不存在。"},
            )
        selected = set(selected_file_ids)
        selected_files = [file for file in list(getattr(session, "files", []) or []) if str(getattr(file, "id", "")) in selected]
        if not selected_files:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": "导入会话中没有可重试的文件。"},
            )

        confirmed_files = [file for file in selected_files if str(getattr(file, "status", "")) == "confirmed"]
        if confirmed_files:
            scope_months = self._workbench_matching_scope_months_for_import_file_session(session, selected_file_ids)
            queued_matching_months = self._schedule_workbench_matching_scopes(
                scope_months,
                reason="file_import_retry_after_confirm",
            )
            self._background_job_service.acknowledge_job(job.job_id, owner_user_id)
            return self._json_response(
                HTTPStatus.ACCEPTED,
                {
                    "retry_mode": "workbench_matching",
                    "queued_matching_months": queued_matching_months,
                },
            )

        try:
            session = self._file_import_service.retry_session_files(
                session_id=session_id,
                selected_file_ids=selected_file_ids,
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_retry_request", "message": str(exc)},
            )
        self._background_job_service.acknowledge_job(job.job_id, owner_user_id)
        self._persist_import_preview_delta(session.id)
        return self._json_response(
            HTTPStatus.OK,
            {
                "session": self._serialize_file_session(session),
                "retry_mode": "file_preview",
            },
        )

    def _resolve_task_etc_business_batch(
        self,
        *,
        task_id: str,
        owner_user_id: str,
        idempotency_key: str,
    ):
        return self._import_processing_service.resolve_task_etc_business_batch(
            task_id=task_id,
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _etc_import_job_summary(result, total: int) -> dict[str, int]:
        return ImportProcessingService.etc_import_job_summary(result, total)

    def _link_etc_import_result_to_existing_invoices(self, result: object) -> list[str]:
        return EtcExistingInvoiceLinkService(
            import_service=self._import_service,
            etc_service=self._etc_service,
            persist_linked_invoices=self._persist_linked_invoice_etc_metadata,
        ).link_import_result_to_existing_invoices(result)

    @staticmethod
    def _etc_invoice_changed_months(etc_invoices: list[object]) -> list[str]:
        changed_months: set[str] = set()
        for etc_invoice in etc_invoices:
            for date_value in (
                getattr(etc_invoice, "issue_date", None),
                getattr(etc_invoice, "passage_start_date", None),
                getattr(etc_invoice, "passage_end_date", None),
            ):
                if isinstance(date_value, str) and MONTH_SCOPE_RE.match(date_value[:7]):
                    changed_months.add(date_value[:7])
        return sorted(changed_months)

    def _existing_etc_invoices_by_ids(self, invoice_ids: list[str]) -> list[object]:
        invoices: list[object] = []
        for raw_invoice_id in list(invoice_ids or []):
            invoice_id = str(raw_invoice_id or "").strip()
            if not invoice_id:
                continue
            try:
                invoices.extend(self._etc_service.list_invoices_by_ids([invoice_id]))
            except EtcInvoiceNotFoundError:
                continue
        return invoices

    def _canonical_invoice_key_exists_for_etc_import(self, canonical_key: str) -> bool:
        normalized_key = str(canonical_key or "").strip()
        if not normalized_key:
            return False
        return bool(self._import_service.canonical_invoice_key_exists(normalized_key))

    def _link_etc_invoices_to_existing_invoices(self, etc_invoices: list[object]) -> list[str]:
        return EtcExistingInvoiceLinkService(
            import_service=self._import_service,
            etc_service=self._etc_service,
            persist_linked_invoices=self._persist_linked_invoice_etc_metadata,
        ).link_etc_invoices_to_existing_invoices(etc_invoices)

    def _persist_linked_invoice_etc_metadata(self, invoices: list[object]) -> None:
        persist = getattr(self._state_store, "save_invoice_etc_metadata", None)
        if not callable(persist):
            raise RuntimeError("ETC invoice linking requires the canonical invoice metadata persistence port.")
        persist(invoices)

    def _refresh_after_etc_invoice_link(self, changed_months: list[str], *, reason: str) -> None:
        normalized_months = [
            month
            for month in sorted(dict.fromkeys(str(month).strip() for month in changed_months))
            if MONTH_SCOPE_RE.match(month)
        ]
        if not normalized_months:
            return
        _ = reason

    def _refresh_after_etc_business_batch_status_change(self, changed_months: list[str], *, reason: str) -> None:
        normalized_months = [
            month
            for month in sorted(dict.fromkeys(str(month).strip() for month in changed_months))
            if MONTH_SCOPE_RE.match(month)
        ]
        if not normalized_months:
            return
        _ = reason

    def _refresh_after_workbench_requirement_repair(
        self,
        changed_months: list[str],
        *,
        case_ids: list[str],
        row_ids: list[str],
        reason: str,
    ) -> dict[str, object]:
        normalized_months = [
            month
            for month in sorted(dict.fromkeys(str(month).strip() for month in changed_months))
            if MONTH_SCOPE_RE.match(month)
        ]
        if not normalized_months:
            raise RuntimeError("Workbench requirement repair requires exact month scopes.")
        normalized_reason = str(reason or "workbench_requirement_repair").strip()
        _ = case_ids, row_ids
        dirty_months = self._mark_workbench_matching_dirty_scopes(
            normalized_months,
            reason=normalized_reason,
            debounce_seconds=0,
        )
        return {
            "months": normalized_months,
            "matching_dirty_months": dirty_months,
        }

    def _refresh_after_historical_etc_repair_link(self, changed_months: list[str], *, reason: str) -> None:
        normalized_months = [
            month
            for month in sorted(dict.fromkeys(str(month).strip() for month in changed_months))
            if MONTH_SCOPE_RE.match(month)
        ]
        if not normalized_months:
            return
        metadata = {"source": "historical_etc_repair_link", "reason": reason}
        self._execute_explicit_maintenance_lifecycle(
            "etc_business_batch_changed",
            months=normalized_months,
            include_all=False,
            metadata=metadata,
        )

    def _etc_business_application_service(self) -> EtcBusinessBatchApplicationService:
        dependency_key = (
            id(getattr(self, "_etc_service", None)),
            id(getattr(self, "_etc_reconciliation_task_service", None)),
        )
        service = getattr(self, "_etc_business_batch_application_service", None)
        if isinstance(service, EtcBusinessBatchApplicationService) and getattr(self, "_etc_business_batch_dependency_key", None) == dependency_key:
            return service
        service = EtcBusinessBatchApplicationService(
            etc_service=self._etc_service,
            reconciliation_task_service=self._etc_reconciliation_task_service,
            oa_client_factory=self._build_etc_oa_client,
            link_etc_invoices_to_existing_invoices=self._link_etc_invoices_to_existing_invoices,
            refresh_after_etc_invoice_link=self._refresh_after_etc_invoice_link,
            refresh_after_etc_business_batch_status_change=self._refresh_after_etc_business_batch_status_change,
            invoice_pdf_bundle_service=EtcInvoicePdfBundleService(
                read_invoice_pdf=self._etc_service.read_invoice_pdf_bytes,
            ),
            record_invoice_pdf_download=lambda actor, batch, bundle: self._audit_service.record_action(
                actor_id=actor.actor_id,
                action="etc_invoice_pdf_bundle_downloaded",
                entity_type="etc_business_batch",
                entity_id=batch.business_batch_id,
                metadata={
                    "filename": bundle.filename,
                    "invoice_count": bundle.invoice_count,
                    "page_count": bundle.page_count,
                },
            ),
        )
        self._etc_business_batch_application_service = service
        self._etc_business_batch_dependency_key = dependency_key
        return service

    def _etc_business_routes(self) -> EtcBusinessBatchApiRoutes:
        service = self._etc_business_application_service()
        routes = getattr(self, "_etc_business_batch_api_routes", None)
        if (
            isinstance(routes, EtcBusinessBatchApiRoutes)
            and getattr(routes, "_application_service", None) is service
            and getattr(routes, "_delete_service", None) is self._etc_business_batch_delete_service()
        ):
            return routes
        routes = EtcBusinessBatchApiRoutes(
            service,
            delete_service=self._etc_business_batch_delete_service(),
            load_json_body=self._load_json_body,
            refresh_after_etc_invoice_link=lambda changed_months, reason: self._refresh_after_etc_invoice_link(
                changed_months,
                reason=reason,
            ),
            persist_state=self._persist_state,
        )
        self._etc_business_batch_api_routes = routes
        return routes

    def _etc_business_session(self, headers: dict[str, str] | None, *, require_mutation: bool) -> OARequestSession | Response:
        try:
            session = self._resolve_request_session(headers)
        except OAAuthError as exc:
            return self._etc_business_response(HTTPStatus.UNAUTHORIZED, None, code="unauthorized", message=str(exc))
        if require_mutation and not session.can_mutate_data:
            return self._etc_business_response(
                HTTPStatus.FORBIDDEN,
                None,
                code="permission_denied",
                message="当前账户没有操作 ETC 批次的权限。",
            )
        if not require_mutation and not session.can_access_app:
            return self._etc_business_response(
                HTTPStatus.FORBIDDEN,
                None,
                code="permission_denied",
                message="当前账户没有访问 ETC 批次的权限。",
            )
        return session

    def _handle_api_etc_business_batches_route(
        self,
        method: str,
        query: dict[str, list[str]],
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        if method == "GET":
            session = self._etc_business_session(headers, require_mutation=False)
            if isinstance(session, Response):
                return session
            status_code, payload = self._etc_business_routes().list_batches(query, session=session)
            return self._json_response(status_code, payload)
        if method == "POST":
            session = self._etc_business_session(headers, require_mutation=True)
            if isinstance(session, Response):
                return session
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = self._etc_business_routes().create_batch(payload, session=session)
            return self._json_response(status_code, result)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _route_api_etc_business_batch_v2(
        self,
        method: str,
        route_path: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        relative = route_path.removeprefix("/api/etc/business-batches/").strip("/")
        parts = [unquote(part) for part in relative.split("/") if part]
        if not parts:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})
        business_batch_id = parts[0]
        action = "/".join(parts[1:])
        if len(parts) == 1 and method == "GET":
            session = self._etc_business_session(headers, require_mutation=False)
            if isinstance(session, Response):
                return session
            status_code, payload = self._etc_business_routes().detail(business_batch_id, session=session)
            return self._json_response(status_code, payload)
        if len(parts) == 1 and method == "PATCH":
            session = self._etc_business_session(headers, require_mutation=True)
            if isinstance(session, Response):
                return session
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = self._etc_business_routes().update_batch(business_batch_id, payload, session=session)
            return self._json_response(status_code, result)
        if len(parts) == 1 and method == "DELETE":
            session = self._etc_business_session(headers, require_mutation=True)
            if isinstance(session, Response):
                return session
            result = self._etc_business_routes().delete_batch(business_batch_id, body)
            if isinstance(result, Response):
                return result
            status_code, payload = result
            return self._json_response(status_code, payload)
        if method == "GET" and action == "invoice-pdf":
            session = self._etc_business_session(headers, require_mutation=False)
            if isinstance(session, Response):
                return session
            status_code, result = self._etc_business_routes().invoice_pdf_bundle(
                business_batch_id,
                session=session,
            )
            if not isinstance(result, EtcInvoicePdfBundle):
                return self._json_response(status_code, result)
            return Response(
                status_code=int(status_code),
                body=result.content,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": _build_content_disposition(result.filename),
                    "Cache-Control": "private, no-store",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Expose-Headers": "Content-Disposition",
                    "X-ETC-Invoice-Count": str(result.invoice_count),
                    "X-PDF-Page-Count": str(result.page_count),
                },
            )
        session = self._etc_business_session(headers, require_mutation=True)
        if isinstance(session, Response):
            return session
        routes = self._etc_business_routes()
        if method == "POST" and action == "invoice-pdf/repair":
            fields, files, error = self._load_multipart_body(body, headers)
            if error is not None:
                return error
            if not files or any(not file.file_name.lower().endswith(".zip") for file in files):
                return self._etc_business_response(
                    HTTPStatus.BAD_REQUEST,
                    None,
                    code="invalid_invoice_attachment_repair_request",
                    message="At least one original ETC zip file is required.",
                )
            uploads = [UploadedEtcZipFile(file_name=file.file_name, content=file.content) for file in files]
            status_code, payload = routes.repair_invoice_attachments(
                business_batch_id,
                uploads,
                expected_version=self._optional_int(
                    (fields.get("expectedVersion") or fields.get("expected_version") or [None])[0]
                ),
                reason=str((fields.get("reason") or [""])[0] or "").strip(),
                session=session,
            )
            return self._json_response(status_code, payload)
        if method == "POST" and action == "source-files":
            _fields, files, error = self._load_multipart_body(body, headers)
            if error is not None:
                return error
            status_code, payload = routes.source_files(business_batch_id, files, session=session)
            return self._json_response(status_code, payload)
        if method == "POST" and action == "etc-import/preview":
            fields, files, error = self._load_multipart_body(body, headers)
            if error is not None:
                return error
            if not files:
                return self._etc_business_response(
                    HTTPStatus.BAD_REQUEST,
                    None,
                    code="invalid_etc_import_request",
                    message="At least one zip file is required.",
                )
            invalid_files = [file.file_name for file in files if not file.file_name.lower().endswith(".zip")]
            if invalid_files:
                return self._etc_business_response(
                    HTTPStatus.BAD_REQUEST,
                    None,
                    code="invalid_etc_import_request",
                    message="Only .zip files can be imported.",
                )
            uploads = [UploadedEtcZipFile(file_name=file.file_name, content=file.content) for file in files]
            expected_version = self._optional_int((fields.get("expectedVersion") or fields.get("expected_version") or [None])[0])
            status_code, payload = routes.preview_import(
                business_batch_id,
                uploads,
                expected_version=expected_version,
                session=session,
            )
            return self._json_response(status_code, payload)
        if method == "POST" and action == "etc-import/confirm":
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = routes.confirm_import(business_batch_id, payload, session=session)
            return self._json_response(status_code, result)
        if method == "POST" and action == "oa-draft":
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = routes.create_oa_draft(business_batch_id, payload, session=session, headers=headers)
            return self._json_response(status_code, result)
        if method == "POST" and action == "oa-draft/recover":
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = routes.recover_oa_draft(business_batch_id, payload, session=session)
            return self._json_response(status_code, result)
        if method == "POST" and action == "manual-oa-status":
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = routes.manual_oa_status(business_batch_id, payload, session=session)
            return self._json_response(status_code, result)
        if method == "POST" and action == "oa-draft/revoke":
            payload, error = self._load_json_body(body)
            if error is not None:
                return error
            status_code, result = routes.revoke_oa_draft(business_batch_id, payload, session=session)
            return self._json_response(status_code, result)
        return self._json_response(HTTPStatus.NOT_FOUND, {"error": "not_found"})

    def _etc_business_mutation_session(self, headers: dict[str, str] | None) -> OARequestSession | Response:
        session = self._resolve_request_session(headers)
        if not session.can_mutate_data:
            return self._etc_business_response(
                HTTPStatus.FORBIDDEN,
                None,
                code="permission_denied",
                message="当前账户没有操作 ETC 批次的权限。",
            )
        return session

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    def _etc_business_response(
        self,
        status: HTTPStatus,
        data: object,
        *,
        code: str | None = None,
        message: str | None = None,
        details: dict[str, object] | None = None,
    ) -> Response:
        request_id = uuid4().hex[:12]
        error = None if code is None else {"code": code, "message": message or code, "details": details or {}}
        return self._json_response(
            status,
            {
                "ok": code is None,
                "data": data if code is None else None,
                "error": error,
                "requestId": request_id,
            },
        )

    def _etc_business_error_response(self, error: Exception) -> Response:
        if isinstance(error, EtcBusinessBatchNotFoundError):
            return self._etc_business_response(HTTPStatus.NOT_FOUND, None, code="business_batch_not_found", message=str(error))
        if isinstance(error, EtcBusinessBatchActiveExistsError):
            return self._etc_business_response(HTTPStatus.CONFLICT, None, code="active_business_batch_exists", message=str(error))
        if isinstance(error, EtcBusinessBatchVersionConflictError):
            return self._etc_business_response(
                HTTPStatus.CONFLICT,
                None,
                code="version_conflict",
                message="批次状态已变化，请刷新后重试。",
                details={
                    "businessBatchId": error.business_batch_id,
                    "expectedVersion": error.expected_version,
                    "actualVersion": error.actual_version,
                },
            )
        if isinstance(error, WorkbenchRelationCommandError):
            return self._etc_business_response(
                HTTPStatus.CONFLICT,
                None,
                code=error.error_code,
                message=error.message,
                details=dict(error.payload or {}),
            )
        if isinstance(error, EtcBusinessBatchInvalidTransitionError):
            return self._etc_business_response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                None,
                code=getattr(error, "code", "invalid_status_transition"),
                message=str(error),
            )
        if isinstance(error, EtcDraftRequestError):
            return self._etc_business_response(HTTPStatus.BAD_REQUEST, None, code="invalid_etc_draft_request", message=str(error))
        if isinstance(error, EtcOAClientError):
            return self._etc_business_response(HTTPStatus.BAD_REQUEST, None, code="invalid_etc_draft_request", message=str(error))
        if isinstance(error, EtcServiceError):
            return self._etc_business_response(HTTPStatus.BAD_REQUEST, None, code="invalid_etc_business_batch_request", message=str(error))
        raise error

    def _serialize_etc_invoice(self, invoice: object) -> dict[str, object]:
        payload = Application._serialize_value(invoice)
        if not isinstance(payload, dict):
            return {}
        pdf_path = payload.get("pdf_file_path")
        xml_path = payload.get("xml_file_path")
        payload["has_pdf"] = isinstance(pdf_path, str) and bool(pdf_path)
        payload["has_xml"] = isinstance(xml_path, str) and bool(xml_path)
        return payload

    def _delete_etc_business_batch_via_route_owner(self, business_batch_id: str, body: str | bytes | None) -> Response:
        result = self._etc_business_routes().delete_batch(business_batch_id, body)
        if isinstance(result, Response):
            return result
        status_code, payload = result
        return self._json_response(status_code, payload)

    def _build_etc_oa_client(self, headers: dict[str, str] | None) -> HttpEtcOAClient | None:
        if not isinstance(self._etc_service.oa_client, NotConfiguredEtcOAClient):
            return None
        token = extract_oa_token(headers)
        if not token:
            raise EtcOAClientError("OA 登录 token 缺失，请从 OA 内打开本 app 或重新登录 OA 后再创建草稿。")
        return HttpEtcOAClient(token=token)

    def _handle_api_session_me(self, headers: dict[str, str] | None) -> Response:
        try:
            session = self._resolve_request_session(headers)
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
            "/reconciliation",
            "/imports",
        )
        return route_path.startswith(protected_prefixes)

    @staticmethod
    def _route_has_module_owned_oa_access(route_path: str) -> bool:
        return route_path == "/api/oa-pending-payments" or route_path.startswith("/api/oa-pending-payments/")

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return round((monotonic() - started_at) * 1000, 3)

    @staticmethod
    def _audit_page_key_for_route(route_path: str) -> str:
        route_page_prefixes = (
            ("/api/workbench/settings/data-reset", "settings"),
            ("/api/workbench", "reconciliation-workbench"),
            ("/reconciliation", "reconciliation-workbench"),
            ("/api/etc/", "etc-tickets"),
            ("/api/no-oa-bank-batches", "bank-details"),
            ("/api/oa-sync", "oa-pending-payments"),
            ("/api/operations/history", "operation-history"),
            ("/api/operations/app-health", "app-health-operations"),
            ("/api/imports/bank-transaction-batches", "app-health-operations"),
            ("/api/app-health", "app-health-operations"),
            ("/imports/bank-transactions", "imports.bank-transactions"),
            ("/imports/invoices", "imports.invoices"),
            ("/imports/etc-invoices", "imports.etc-invoices"),
        )
        for prefix, page_key in route_page_prefixes:
            normalized_prefix = prefix.rstrip("/")
            if route_path == normalized_prefix or route_path.startswith(f"{normalized_prefix}/"):
                return page_key
        parts = [part for part in str(route_path or "").split("/") if part]
        if parts and parts[0] == "api":
            parts = parts[1:]
        return parts[0] if parts else "application"

    @staticmethod
    def _safe_list_count(value: object) -> int:
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _workbench_timed_action_for_route(*, method: str, route_path: str) -> str | None:
        if method == "POST" and route_path == "/api/workbench/actions/confirm-link":
            return "confirm_link"
        if method == "POST" and route_path == "/api/workbench/actions/cancel-link":
            return "cancel_link"
        if method == "POST" and route_path == "/api/workbench/actions/withdraw-link":
            return "withdraw_link"
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

    def _emit_workbench_api_metric(
        self,
        *,
        endpoint: str,
        scope_key: str,
        status_code: int,
        duration_ms: float,
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "workbench_api_metric",
                    "metric": "workbench.api.duration_ms",
                    "endpoint": endpoint,
                    "scope_key": scope_key,
                    "status_code": int(status_code),
                    "duration_ms": round(float(duration_ms), 3),
                    "timestamp": datetime.now().isoformat(),
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    @staticmethod
    def _workbench_metric_scope_key(value: object) -> str:
        """Keep metric emission total even when request validation rejects the month."""
        try:
            return normalize_workbench_scope_key(value)
        except ValueError:
            return "invalid"

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
        method: str,
        route_path: str,
        headers: dict[str, str] | None,
        *,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> tuple[OARequestSession | None, Response | None]:
        if self._route_has_module_owned_oa_access(route_path):
            return None, None
        if not self._route_requires_oa_access(route_path):
            return None, None
        auth_started_at = monotonic()
        try:
            session = self._resolve_request_session(headers)
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
        finally:
            if request_id is not None and action_name is not None:
                self._emit_workbench_action_timing(
                    request_id=request_id,
                    action_name=action_name,
                    phase="oa_auth",
                    duration_ms=self._duration_ms(auth_started_at),
                )
        if requires_data_mutation(method, route_path) and not session.can_mutate_data:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有修改数据的权限。"},
            )
        return session, None

    def _workbench_write_auth_context(
        self,
        headers: dict[str, str] | None,
        *,
        session: OARequestSession | None = None,
    ) -> tuple[str, str] | Response:
        try:
            if session is None:
                session = self._resolve_request_session(headers)
            if not session.allowed:
                raise ForbiddenOAAccessError("当前 OA 账户未被授权访问财务运营平台。")
            if not session.can_mutate_data:
                return self._json_response(
                    HTTPStatus.FORBIDDEN,
                    {"error": "permission_denied", "message": "当前账户没有修改工作台数据的权限。"},
                )
        except UnauthorizedOASessionError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "invalid_oa_session", "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。"},
            )
        except OASessionExpiredError as error:
            return self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "invalid_oa_session", "message": str(error) or "OA 登录状态已过期。"},
            )
        except ForbiddenOAAccessError as error:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "forbidden", "message": str(error) or "当前 OA 账户未被授权访问财务运营平台。"},
            )
        except OAIdentityConfigurationError as error:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "oa_identity_unavailable", "message": str(error) or "OA 身份服务未配置。"},
            )
        except OAIdentityServiceError as error:
            return self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {"error": "oa_identity_lookup_failed", "message": str(error) or "OA 身份解析失败。"},
            )
        return actor_id_for_session(session), tenant_id_for_session(session)

    def _input_invoice_usage_service(self) -> InputInvoiceUsageQueryService:
        service = getattr(self, "_input_invoice_usage_query_service", None)
        if isinstance(service, InputInvoiceUsageQueryService):
            return service
        service = InputInvoiceUsageQueryService(
            import_service=self._import_service,
            relation_reader=self._workbench_relation_command_service(),
            oa_projection=getattr(self, "_workbench_query_service", None),
            payment_rules_provider=self._input_invoice_usage_payment_rules_provider(),
            lifecycle_policy=self._invoice_lifecycle_policy(),
        )
        self._input_invoice_usage_query_service = service
        return service

    def _invoice_lifecycle_policy(self) -> InvoiceLifecyclePolicy:
        policy = getattr(self, "_invoice_lifecycle_policy_instance", None)
        if isinstance(policy, InvoiceLifecyclePolicy):
            return policy
        policy = InvoiceLifecyclePolicy(
            input_payment_rules_provider=self._input_invoice_usage_payment_rules_provider(),
        )
        self._invoice_lifecycle_policy_instance = policy
        return policy

    def _input_invoice_usage_export_service(self) -> InputInvoiceUsageExportService:
        service = getattr(self, "_input_invoice_usage_export_service_instance", None)
        if isinstance(service, InputInvoiceUsageExportService):
            return service
        query_service = self._input_invoice_usage_page_query_service()
        service = InputInvoiceUsageExportService(
            row_page_loader=query_service.export_page,
            row_export_loader=query_service.export_rows,
        )
        self._input_invoice_usage_export_service_instance = service
        return service

    def _input_invoice_usage_page_query_service(self) -> InputInvoiceUsageCanonicalQueryService:
        service = getattr(self, "_input_invoice_usage_page_query_service_instance", None)
        repository = getattr(self, "_input_invoice_usage_canonical_query_repository", None)
        if repository is None and self._requires_postgres_runtime():
            raise RuntimeError("Input invoice usage canonical query repository is required in PostgreSQL runtime.")
        row_assembler = self._input_invoice_usage_service()
        if isinstance(service, InputInvoiceUsageCanonicalQueryService) and (
            getattr(service, "_repository", None) is repository
            and getattr(service, "_row_assembler", None) is row_assembler
        ):
            return service
        service = InputInvoiceUsageCanonicalQueryService(
            repository=repository,
            row_assembler=row_assembler,
        )
        self._input_invoice_usage_page_query_service_instance = service
        return service

    def _input_invoice_usage_routes(self) -> InputInvoiceUsageApiRoutes:
        routes = getattr(self, "_input_invoice_usage_api_routes", None)
        query_service = self._input_invoice_usage_page_query_service()
        if isinstance(routes, InputInvoiceUsageApiRoutes) and getattr(routes, "_dependency_identity", None) is query_service:
            return routes
        routes = InputInvoiceUsageApiRoutes(
            query_service=query_service,
            export_service=self._input_invoice_usage_export_service(),
            resolve_read_session=self._resolve_fin_ops_read_session,
            export_query_kwargs=self._input_invoice_usage_export_query_kwargs,
            export_error_response=self._input_invoice_usage_export_error_response,
            record_export_download=self._record_input_invoice_usage_export_download,
            xlsx_response=self._input_invoice_usage_xlsx_response,
            app_settings_service=self._app_settings_service,
            load_json_body=self._load_json_body,
            payment_rules_error_response=self._input_invoice_usage_payment_rules_error_response,
            json_response=self._json_response,
            input_usage_error_response=self._input_invoice_usage_error_response,
            dependency_identity=query_service,
        )
        self._input_invoice_usage_api_routes = routes
        return routes

    def _input_invoice_usage_payment_rules_provider(self) -> AppSettingsInputInvoiceUsagePaymentRulesProvider:
        provider = getattr(self, "_input_invoice_usage_payment_rules_provider_instance", None)
        if isinstance(provider, AppSettingsInputInvoiceUsagePaymentRulesProvider):
            return provider
        provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(
            state_store=getattr(self, "_state_store", None),
            audit_service=getattr(self, "_audit_service", None),
        )
        self._input_invoice_usage_payment_rules_provider_instance = provider
        return provider

    def _oa_applicant_credential_service(self) -> OaApplicantCredentialService:
        service = getattr(self, "_oa_applicant_credential_service_instance", None)
        if isinstance(service, OaApplicantCredentialService):
            return service
        repository = getattr(self, "_oa_applicant_credential_repository", None)
        if repository is None:
            state_store = getattr(self, "_state_store", None)
            connection = getattr(state_store, "_connection", None)
            if str(getattr(state_store, "storage_backend", "") or "").strip() == "postgres" and connection is not None:
                repository = PostgresOaApplicantCredentialRepository(connection)
            else:
                repository = InMemoryOaApplicantCredentialRepository()
            self._oa_applicant_credential_repository = repository
        service = OaApplicantCredentialService(repository=repository)
        self._oa_applicant_credential_service_instance = service
        return service

    def _target_oa_applicant_token_provider(self) -> object:
        provider = getattr(self, "_target_oa_applicant_token_provider_instance", None)
        if callable(getattr(provider, "draft_client_for", None)):
            return provider
        provider = TargetOaApplicantTokenProvider(
            credential_service=self._oa_applicant_credential_service(),
            login_client=OaLoginClient(),
        )
        self._target_oa_applicant_token_provider_instance = provider
        return provider

    def _settings_routes(self) -> SettingsApiRoutes:
        routes = getattr(self, "_settings_api_routes", None)
        if isinstance(routes, SettingsApiRoutes):
            return routes
        routes = SettingsApiRoutes(
            app_settings_service_provider=lambda: self._app_settings_service,
            project_costing_service_provider=lambda: self._project_costing_service,
            settings_data_reset_service_provider=lambda: self._settings_data_reset_service,
            background_job_service_provider=lambda: self._background_job_service,
            oa_applicant_credential_service_provider=self._oa_applicant_credential_service,
            oa_manual_import_service_provider=lambda: getattr(self, "_oa_manual_import_service", None),
            resolve_read_session=lambda headers: self._resolve_fin_ops_read_session(
                headers,
                denied_message="当前账户没有访问设置页面权限。",
            ),
            resolve_admin_session=self._resolve_admin_session,
            verify_reset_oa_password=self._verify_reset_oa_password,
            oa_password_verification_failed_response=self._oa_password_verification_failed_response,
            load_json_body=self._load_json_body,
            json_response=self._json_response,
            finalize_settings_event=self._finalize_workbench_settings_event,
            request_data_reset=self._request_settings_data_reset_job,
            serialize_sync_run=self._serialize_sync_run,
            serialize_data_reset_background_job=self._serialize_data_reset_background_job,
            import_job_processing_enabled=self._import_job_processing_enabled,
            enqueue_import_process_job=self._enqueue_import_process_job,
            serialize_import_job=self._serialize_import_job,
            manual_import_affected_scope_keys=self._settings_oa_manual_import_affected_scope_keys,
            manual_import_affected_scope_payload=self._settings_oa_manual_import_affected_scope_payload,
        )
        self._settings_api_routes = routes
        return routes

    def _request_settings_data_reset_job(
        self,
        *,
        action: str,
        owner_user_id: str,
        idempotency_key: str,
        label: str,
        reason: str,
        impact_fingerprint: str,
        recovery_receipt_id: str,
        request_id: str,
    ) -> tuple[object, bool]:
        service = getattr(self, "_settings_data_reset_request_service_instance", None)
        if isinstance(service, SettingsDataResetRequestService):
            return service.request(
                action=action,
                owner_user_id=owner_user_id,
                idempotency_key=idempotency_key,
                label=label,
                reason=reason,
                impact_fingerprint=impact_fingerprint,
                recovery_receipt_id=recovery_receipt_id,
                request_id=request_id,
            )
        queue = getattr(self._runtime_repositories, "queue_repository", None)
        if queue is None:
            raise RuntimeError("Durable settings maintenance queue is unavailable.")
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        atomic_repository = (
            PostgresSettingsDataResetRequestRepository(connection, queue)
            if str(getattr(state_store, "storage_backend", "") or "").strip() == "postgres"
            and connection is not None
            else None
        )
        service = SettingsDataResetRequestService(
            background_jobs=self._background_job_service,
            queue_repository=queue,
            atomic_repository=atomic_repository,
        )
        self._settings_data_reset_request_service_instance = service
        return service.request(
            action=action,
            owner_user_id=owner_user_id,
            idempotency_key=idempotency_key,
            label=label,
            reason=reason,
            impact_fingerprint=impact_fingerprint,
            recovery_receipt_id=recovery_receipt_id,
            request_id=request_id,
        )

    def _input_invoice_usage_oa_reverse_service(self) -> InputInvoiceUsageOaReverseService:
        service = getattr(self, "_input_invoice_usage_oa_reverse_service_instance", None)
        if isinstance(service, InputInvoiceUsageOaReverseService):
            return service
        repository = getattr(self, "_input_invoice_usage_oa_reverse_repository", None)
        if repository is None:
            state_store = getattr(self, "_state_store", None)
            connection = getattr(state_store, "_connection", None)
            if str(getattr(state_store, "storage_backend", "") or "").strip() == "postgres" and connection is not None:
                repository = PostgresInputInvoiceUsageOaReverseBatchRepository(connection)
            else:
                repository = InMemoryInputInvoiceUsageOaReverseBatchRepository()
            self._input_invoice_usage_oa_reverse_repository = repository
        service = InputInvoiceUsageOaReverseService(
            repository=repository,
            evidence_provider=OAProjectionInputInvoiceUsageOaEvidenceProvider(
                getattr(self._input_invoice_usage_service(), "_oa_projection", None)
            ),
            relation_writer=WorkbenchInputInvoiceUsageOaReverseRelationWriter(self._workbench_relation_command_service()),
            audit_recorder=self._record_input_invoice_usage_oa_reverse_audit,
            rows_loader=lambda query: self._input_invoice_usage_page_query_service().rows(query),
            rows_by_invoice_ids_loader=lambda invoice_ids: self._input_invoice_usage_page_query_service().rows_by_invoice_ids(
                invoice_ids
            ),
            oa_prefill_provider=lambda: self._app_settings_service.get_oa_draft_prefill_configuration(
                INPUT_INVOICE_USAGE_OA_DRAFT_PREFILL_FAMILY
            ),
        )
        self._input_invoice_usage_oa_reverse_service_instance = service
        return service

    def _input_invoice_usage_oa_reverse_routes(self) -> InputInvoiceUsageOaReverseApiRoutes:
        routes = getattr(self, "_input_invoice_usage_oa_reverse_api_routes", None)
        service = self._input_invoice_usage_oa_reverse_service()
        if isinstance(routes, InputInvoiceUsageOaReverseApiRoutes) and getattr(routes, "_service", None) is service:
            return routes
        routes = InputInvoiceUsageOaReverseApiRoutes(
            service=service,
            resolve_read_session=self._resolve_fin_ops_read_session,
            mutation_actor=self._input_invoice_usage_mutation_actor,
            load_json_body=self._load_json_body,
            json_response=self._json_response,
            input_usage_error_response=self._input_invoice_usage_error_response,
            oa_reverse_error_response=self._input_invoice_usage_oa_reverse_error_response,
            target_oa_applicant_token_provider=self._target_oa_applicant_token_provider,
            oa_draft_client_for_batch=self._input_invoice_usage_oa_draft_client_for_batch,
            int_or_none=self._int_or_none,
        )
        self._input_invoice_usage_oa_reverse_api_routes = routes
        return routes

    def _record_input_invoice_usage_oa_reverse_audit(self, event: dict[str, object]) -> None:
        record_action = getattr(getattr(self, "_audit_service", None), "record_action", None)
        if callable(record_action):
            record_action(**event)

    def _input_invoice_usage_oa_draft_client_for_batch(self, batch_id: str) -> object | None:
        try:
            batch = self._input_invoice_usage_oa_reverse_service().get_batch(batch_id)
            target_applicant_code = str(batch.get("targetApplicantCode") or "").strip()
            return self._target_oa_applicant_token_provider().draft_client_for(target_applicant_code)
        except (InputInvoiceUsageOaReverseServiceError, TargetOaApplicantTokenProviderError):
            return NotConfiguredInputInvoiceUsageOaDraftClient()

    def _input_invoice_usage_mutation_actor(
        self,
        headers: dict[str, str] | None,
        *,
        denied_message: str,
    ) -> tuple[str, bool, Response | None]:
        session, auth_error = self._resolve_fin_ops_read_session(headers, denied_message=denied_message)
        if auth_error is not None:
            return "", False, auth_error
        if session is not None and not session.can_mutate_data:
            return "", False, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": denied_message},
            )
        if session is None:
            return "input_invoice_usage_oa_reverse", True, None
        return str(session.identity.username or session.identity.user_id or "input_invoice_usage_oa_reverse"), True, None

    def _record_input_invoice_usage_export_download(
        self,
        session: object | None,
        filename: str,
        query: dict[str, list[str]],
    ) -> None:
        identity = getattr(session, "identity", None)
        self._audit_service.record_action(
            actor_id=str(getattr(identity, "username", None) or "input_invoice_usage_export"),
            action="input_invoice_usage_export_downloaded",
            entity_type="input_invoice_usage_export",
            entity_id=filename,
            metadata={"query": {key: values[0] for key, values in query.items() if values}},
        )

    def _input_invoice_usage_xlsx_response(self, filename: str, content: bytes) -> Response:
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": XLSX_MIME_TYPE,
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    @staticmethod
    def _input_invoice_usage_export_query_kwargs(query: dict[str, list[str]]) -> dict[str, object]:
        return {
            "month": query.get("month", [None])[0],
            "keyword": query.get("keyword", [None])[0],
            "invoice_date_from": query.get("invoice_date_from", [None])[0],
            "invoice_date_to": query.get("invoice_date_to", [None])[0],
            "filters": query.get("filters", [None])[0],
            "sort_field": query.get("sort_field", ["invoice_date"])[0],
            "sort_direction": query.get("sort_direction", ["desc"])[0],
        }

    def _input_invoice_usage_export_error_response(self, exc: InputInvoiceUsageExportError) -> Response:
        return self._json_response(
            HTTPStatus.BAD_REQUEST,
            {"error": {"code": exc.error_code, "message": str(exc), "details": {}}},
        )

    def _input_invoice_usage_payment_rules_error_response(self, exc: AppSettingsValidationError) -> Response:
        status = (
            HTTPStatus.CONFLICT
            if exc.error_code
            in {
                "input_invoice_usage_payment_rules_version_conflict",
                "input_invoice_usage_payment_rules_idempotency_conflict",
            }
            else HTTPStatus.BAD_REQUEST
        )
        return self._json_response(status, {"error": exc.error_code, "message": str(exc)})

    def _input_invoice_usage_oa_reverse_error_response(
        self,
        exc: InputInvoiceUsageOaReverseServiceError | WorkbenchRelationCommandError,
    ) -> Response:
        if isinstance(exc, WorkbenchRelationCommandError):
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": exc.error_code,
                    "message": exc.message,
                    "details": dict(exc.payload or {}),
                },
            )
        if isinstance(exc, InputInvoiceUsageOaReverseNotFoundError):
            status = HTTPStatus.NOT_FOUND
        elif isinstance(exc, (InputInvoiceUsageOaReverseVersionConflictError, InputInvoiceUsageOaReverseStalePreviewError)):
            status = HTTPStatus.CONFLICT
        elif isinstance(exc, InputInvoiceUsageOaReversePermissionError):
            status = HTTPStatus.FORBIDDEN
        elif isinstance(exc, InputInvoiceUsageOaReverseMissingClientError):
            status = HTTPStatus.SERVICE_UNAVAILABLE
        elif isinstance(exc, InputInvoiceUsageOaReverseInvalidTransitionError):
            status = HTTPStatus.BAD_REQUEST
        else:
            status = HTTPStatus.BAD_REQUEST
        payload: dict[str, object] = {"error": getattr(exc, "code", "input_invoice_usage_oa_reverse_error"), "message": str(exc)}
        if isinstance(exc, InputInvoiceUsageOaReverseVersionConflictError):
            payload["details"] = {
                "batchId": exc.batch_id,
                "expectedVersion": exc.expected_version,
                "actualVersion": exc.actual_version,
            }
        return self._json_response(status, payload)

    def _input_invoice_usage_error_response(self, exc: InputInvoiceUsageError) -> Response:
        payload: dict[str, object] = {
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            }
        }
        return self._json_response(exc.status_code, payload)

    def _oa_pending_payment_routes(self) -> OaPendingPaymentApiRoutes:
        routes = getattr(self, "_oa_pending_payment_api_routes", None)
        if isinstance(routes, OaPendingPaymentApiRoutes):
            return self._configure_oa_pending_payment_route_ports(routes)
        routes = OaPendingPaymentApiRoutes(
            query_service=self._oa_pending_payment_query_service(),
            command_service=self._oa_pending_payment_command_service(),
        )
        self._oa_pending_payment_api_routes = self._configure_oa_pending_payment_route_ports(routes)
        return self._oa_pending_payment_api_routes

    def _configure_oa_pending_payment_route_ports(self, routes: OaPendingPaymentApiRoutes) -> OaPendingPaymentApiRoutes:
        return routes.configure_platform_ports(
            resolve_read_session=self._resolve_oa_pending_payment_read_session,
            resolve_read_tenant=lambda session: tenant_id_for_session(session),
            write_auth_context=self._workbench_write_auth_context,
            json_response=self._json_response,
            load_json_body=self._load_json_body,
            error_response=self._oa_pending_payment_error_response,
            xlsx_response=self._oa_pending_payment_xlsx_response,
            record_export_download=self._record_oa_pending_payment_export_download,
        )

    def _oa_payment_status_repository(self):
        override = getattr(self, "_oa_payment_status_repository_override", None)
        if override is not None:
            return override
        repository = getattr(self, "_oa_payment_status_repository_instance", None)
        if repository is not None:
            return repository
        repository = MySQLOAPaymentStatusRepository.from_environment()
        self._oa_payment_status_repository_instance = repository
        return repository

    def _oa_pending_payment_command_service(self) -> OaPendingPaymentCommandService:
        override = getattr(self, "_oa_pending_payment_command_service_override", None)
        if override is not None:
            return override
        service = getattr(self, "_oa_pending_payment_command_service_instance", None)
        if isinstance(service, OaPendingPaymentCommandService):
            return service
        service = OaPendingPaymentCommandService(
            import_service=self._import_service,
            oa_projection=self._oa_pending_payment_command_oa_projection(),
            relation_command_service=self._workbench_relation_command_service(repository=getattr(self, "_state_store", None)),
            payment_status_repository=self._oa_payment_status_repository(),
            payment_status_snapshot_writer=self._oa_pending_payment_source_snapshot_repository(),
            bank_transaction_category_codes_for_row_ids=self._bank_transaction_category_codes_for_workbench_row_ids,
            bank_flow_rule_tag_rules_payload=self._app_settings_service.get_bank_flow_rule_batch_tag_rules_payload,
        )
        self._oa_pending_payment_command_service_instance = service
        return service

    def _oa_pending_payment_command_oa_projection(self) -> object | None:
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        if connection is not None:
            return PostgresOAProjectionAdapter(PostgresOAWorkflowRepository(connection))
        return self._oa_pending_payment_projection()

    def _oa_pending_payment_source_snapshot_repository(self) -> object | None:
        override = getattr(self, "_oa_pending_payment_source_snapshot_repository_override", None)
        if override is not None:
            return override
        repository = getattr(self, "_oa_pending_payment_source_snapshot_repository_instance", None)
        if repository is not None:
            return repository
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        if connection is None:
            if self._requires_postgres_runtime():
                raise RuntimeError("OA pending payment source snapshot writer requires PostgreSQL runtime repositories.")
            return None
        repository = PostgresOaPendingPaymentSourceSnapshotRepository(
            connection,
            relation_command_service_for_transaction=lambda transaction: WorkbenchRelationCommandService(
                relation_repository=PostgresWorkbenchRelationRepository(transaction),
            ),
        )
        self._oa_pending_payment_source_snapshot_repository_instance = repository
        return repository

    def _oa_pending_payment_projection(
        self,
        *,
        source_adapter: object | None = None,
        use_lazy_source: bool = True,
    ) -> PaymentAdmittedOAProjectionAdapter:
        # Explicit source projections are request/builder scoped; caching them can hide current in-progress OA from writes.
        if source_adapter is not None or not use_lazy_source:
            return PaymentAdmittedOAProjectionAdapter(
                source_adapter=source_adapter,
                payment_status_repository=self._oa_payment_status_repository(),
            )
        projection = getattr(self, "_oa_pending_payment_projection_instance", None)
        if isinstance(projection, PaymentAdmittedOAProjectionAdapter):
            return projection
        projection = PaymentAdmittedOAProjectionAdapter(
            source_adapter=self._oa_pending_payment_source_projection(),
            payment_status_repository=self._oa_payment_status_repository(),
        )
        self._oa_pending_payment_projection_instance = projection
        return projection

    def _oa_pending_payment_source_projection(self) -> object | None:
        override = getattr(self, "_oa_pending_payment_source_projection_override", None)
        if override is not None:
            return override
        repository = self._postgres_oa_projection_repository()
        if repository is None and self._requires_postgres_runtime():
            raise RuntimeError("OA pending payment projection requires the PostgreSQL OA projection repository.")
        return repository

    def _oa_pending_payment_query_service(self) -> OaPendingPaymentQueryService:
        service = getattr(self, "_oa_pending_payment_query_service_instance", None)
        if isinstance(service, OaPendingPaymentQueryService):
            return service
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        repository = (
            PostgresOaPendingPaymentQueryRepository(connection)
            if connection is not None
            else None
        )
        service = OaPendingPaymentQueryService(repository=repository)
        self._oa_pending_payment_query_service_instance = service
        return service

    def _oa_pending_payment_error_response(self, exc: OaPendingPaymentError) -> Response:
        payload: dict[str, object] = {
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            }
        }
        return self._json_response(exc.status_code, payload)

    def _record_oa_pending_payment_export_download(
        self,
        session: object | None,
        filename: str,
        sources: list[str],
        counts: dict[str, int],
    ) -> None:
        actor_id = actor_id_for_session(session) if session is not None else "oa_pending_payment_export"
        self._audit_service.record_action(
            actor_id=actor_id,
            action="oa_pending_payment_source_export_downloaded",
            entity_type="oa_pending_payment_source_export",
            entity_id=filename,
            metadata={
                "sources": sources,
                "counts": counts,
                "row_count": sum(counts.values()),
                "filename": filename,
            },
        )

    @staticmethod
    def _oa_pending_payment_xlsx_response(filename: str, content: bytes) -> Response:
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": XLSX_MIME_TYPE,
                "Content-Disposition": _build_content_disposition(filename),
                "Cache-Control": "no-store",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    def _output_invoice_collection_service(self) -> OutputInvoiceCollectionQueryService:
        service = getattr(self, "_output_invoice_collection_query_service", None)
        if isinstance(service, OutputInvoiceCollectionQueryService):
            return service
        service = OutputInvoiceCollectionQueryService(
            import_service=self._import_service,
            relation_reader=self._workbench_relation_command_service(),
        )
        self._output_invoice_collection_query_service = service
        return service

    def _output_invoice_collection_page_query_service(self) -> OutputInvoiceCollectionCanonicalQueryService:
        service = getattr(self, "_output_invoice_collection_page_query_service_instance", None)
        repository = getattr(self, "_output_invoice_collection_canonical_query_repository", None)
        if repository is None and self._requires_postgres_runtime():
            raise RuntimeError("Output invoice collection canonical query repository is required in PostgreSQL runtime.")
        row_assembler = self._output_invoice_collection_service()
        if isinstance(service, OutputInvoiceCollectionCanonicalQueryService) and (
            getattr(service, "_repository", None) is repository
            and getattr(service, "_row_assembler", None) is row_assembler
        ):
            return service
        service = OutputInvoiceCollectionCanonicalQueryService(
            repository=repository,
            row_assembler=row_assembler,
        )
        self._output_invoice_collection_page_query_service_instance = service
        return service

    def _output_invoice_collection_routes(self) -> OutputInvoiceCollectionApiRoutes:
        return OutputInvoiceCollectionApiRoutes(
            query_service=self._output_invoice_collection_page_query_service(),
            resolve_read_session=self._resolve_output_invoice_collection_read_session,
            json_response=self._json_response,
            xlsx_response=self._output_invoice_collection_xlsx_response,
            error_response=self._output_invoice_collection_error_response,
        )

    def _output_invoice_collection_xlsx_response(self, filename: str, content: bytes) -> Response:
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": XLSX_MIME_TYPE,
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    def _output_invoice_collection_error_response(self, exc: OutputInvoiceCollectionError) -> Response:
        payload: dict[str, object] = {
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            }
        }
        return self._json_response(exc.status_code, payload)

    def _input_invoice_usage_statistics_overlay(self) -> dict[str, object]:
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() == "postgres" and connection is not None:
            reverse_statistics = input_invoice_usage_oa_reverse_statistics_snapshot(connection)
            return {
                "oa_reverse_batch_count": int(reverse_statistics["batch_count"]),
            }
        return {"oa_reverse_batch_count": 0}

    def _pending_invoice_routes(self) -> PendingInvoiceApiRoutes:
        routes = getattr(self, "_pending_invoice_api_routes", None)
        if isinstance(routes, PendingInvoiceApiRoutes):
            return routes.configure_platform_ports(
                resolve_read_session=self._resolve_pending_invoice_read_session,
                resolve_write_session=self._resolve_pending_invoice_write_session,
                json_response=self._json_response,
                load_json_body=self._load_json_body,
                error_response=self._pending_invoice_error_response,
                export_response=self._pending_invoice_export_response,
                persist_state=self._persist_state,
            )
        query_service = getattr(self, "_pending_invoice_query_service", None)
        settings_service = getattr(self, "_app_settings_service", None)
        page_query_service = getattr(self, "_pending_invoice_page_query_service", None)
        if not isinstance(page_query_service, PendingInvoiceCanonicalQueryService):
            connection = getattr(getattr(self, "_state_store", None), "_connection", None)
            repository = (
                PostgresPendingInvoiceCanonicalRepository(connection)
                if self._requires_postgres_runtime()
                else LocalPendingInvoiceCanonicalRepository(
                    import_service=getattr(self, "_import_service", None),
                    query_service=query_service,
                    settings_provider=settings_service.get_settings_payload,
                )
            )
            page_query_service = PendingInvoiceCanonicalQueryService(
                repository=repository,
                row_normalizer=getattr(query_service, "normalize_row_payloads", None),
            )
            self._pending_invoice_page_query_service = page_query_service
        rules_service = PendingInvoiceRulesApplicationService(
            settings_gateway=AppSettingsPendingInvoiceRulesGateway(settings_service),
        )
        routes = PendingInvoiceApiRoutes(
            query_service=query_service,
            application_service=getattr(self, "_pending_invoice_application_service", None),
            page_query_service=page_query_service,
            rules_service=rules_service,
            export_content_type=XLSX_MIME_TYPE,
            resolve_read_session=self._resolve_pending_invoice_read_session,
            resolve_write_session=self._resolve_pending_invoice_write_session,
            json_response=self._json_response,
            load_json_body=self._load_json_body,
            error_response=self._pending_invoice_error_response,
            export_response=self._pending_invoice_export_response,
            persist_state=self._persist_state,
        )
        self._pending_invoice_api_routes = routes
        return routes

    def _pending_invoice_export_response(
        self,
        session: OARequestSession | None,
        query: dict[str, list[str]],
        result: PendingInvoiceExportFile,
    ) -> Response:
        self._audit_service.record_action(
            actor_id=str(session.identity.username or "pending_invoice_export") if session is not None else "pending_invoice_export",
            action="pending_invoice_export_downloaded",
            entity_type="pending_invoice_export",
            entity_id=result.filename,
            metadata={"query": {key: values[0] for key, values in query.items() if values}},
        )
        return Response(
            status_code=int(HTTPStatus.OK),
            body=result.content,
            headers={
                "Content-Type": result.content_type,
                "Content-Disposition": _build_content_disposition(result.filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    def _resolve_pending_invoice_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问待找发票页面权限。")

    def _resolve_pending_invoice_write_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        try:
            session = self._resolve_request_session(headers)
        except UnauthorizedOASessionError as exc:
            return None, self._json_response(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized", "message": str(exc)})
        except ForbiddenOAAccessError as exc:
            return None, self._json_response(HTTPStatus.FORBIDDEN, {"error": "permission_denied", "message": str(exc)})
        return session, None

    def _resolve_output_invoice_collection_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问销项发票收款情况页面权限。")

    def _resolve_oa_pending_payment_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问 OA 待付款核对页面权限。")

    def _resolve_tax_offset_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问税金抵扣页面权限。")

    def _resolve_cost_statistics_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问成本统计页面权限。")

    def _resolve_cost_statistics_write_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        session, auth_error = self._resolve_cost_statistics_read_session(headers)
        if auth_error is not None:
            return None, auth_error
        if session is not None and not session.can_mutate_data:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有保存成本统计标签规则权限。"},
            )
        return session, None

    def _resolve_tax_offset_mutation_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        session, auth_error = self._resolve_tax_offset_read_session(headers)
        if auth_error is not None:
            return None, auth_error
        if session is not None and not session.can_mutate_data:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有导入或保存税金抵扣数据权限。"},
            )
        return session, None

    @staticmethod
    def _tax_offset_actor_id(session: OARequestSession | None, payload: dict[str, object], fallback: str) -> str:
        return actor_id_for_session(session) if session is not None else str(payload.get("actor_id") or fallback)

    def _resolve_bank_details_read_session(
        self,
        headers: dict[str, str] | None,
    ) -> tuple[OARequestSession | None, Response | None]:
        return self._resolve_fin_ops_read_session(headers, denied_message="当前账户没有访问银行明细页面权限。")

    def _resolve_fin_ops_read_session(
        self,
        headers: dict[str, str] | None,
        *,
        denied_message: str,
    ) -> tuple[OARequestSession | None, Response | None]:
        identity_service = getattr(self, "_oa_identity_service", None)
        access_control_service = getattr(self, "_access_control_service", None)
        if identity_service is None or access_control_service is None:
            return None, None
        try:
            session = self._resolve_request_session(headers)
        except OASessionExpiredError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "invalid_oa_session", "message": str(error) or "OA 登录状态已过期。"},
            )
        except UnauthorizedOASessionError as error:
            return None, self._json_response(
                HTTPStatus.UNAUTHORIZED,
                {"error": "invalid_oa_session", "message": str(error) or "缺少 OA 登录态，请从 OA 系统进入。"},
            )
        except ForbiddenOAAccessError as error:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": str(error) or "当前 OA 账户未被授权访问财务运营平台。"},
            )
        except OAIdentityConfigurationError as error:
            return None, self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "oa_identity_unavailable", "message": str(error) or "OA 身份服务未配置。"},
            )
        except OAIdentityServiceError as error:
            return None, self._json_response(
                HTTPStatus.BAD_GATEWAY,
                {"error": "oa_identity_lookup_failed", "message": str(error) or "OA 身份解析失败。"},
            )
        if not session.can_access_app:
            return None, self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": denied_message},
            )
        return session, None

    def _pending_invoice_error_response(self, exc: PendingInvoiceError) -> Response:
        payload: dict[str, object] = {"error": exc.error_code, "message": str(exc)}
        if exc.details:
            payload["details"] = exc.details
        return self._json_response(exc.status_code, payload)

    def _finalize_workbench_settings_event(self, event: dict[str, Any]) -> None:
        if event.get("tags_changed"):
            self._finalize_bank_transaction_tag_settings_update(event)
        if not event.get("groups_changed"):
            return
        pending_invoice_service = getattr(self, "_pending_invoice_query_service", None)
        for method_name in ("clear_cache", "invalidate_cache", "refresh"):
            method = getattr(pending_invoice_service, method_name, None)
            if callable(method):
                try:
                    method()
                except TypeError:
                    method(event)
                break

    def _settings_oa_manual_import_affected_scope_keys(
        self,
        result: dict[str, object],
        row_ids: list[str],
    ) -> list[str]:
        scope_keys: set[str] = {"all"}
        rows = result.get("rows") if isinstance(result, dict) else None
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    month = self._settings_oa_manual_import_month_from_row(row)
                    if month:
                        scope_keys.add(month)
        normalized_row_ids = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        if normalized_row_ids:
            for row in self._workbench_query_service.list_record_snapshots():
                if str(row.get("id", "")).strip() in normalized_row_ids:
                    month = str(row.get("_month", "")).strip()
                    if MONTH_SCOPE_RE.match(month):
                        scope_keys.add(month)
            list_application_records_by_row_ids = getattr(
                self._workbench_query_service._oa_adapter,
                "list_application_records_by_row_ids",
                None,
            )
            if callable(list_application_records_by_row_ids):
                try:
                    for record in list_application_records_by_row_ids(sorted(normalized_row_ids)):
                        month = str(getattr(record, "month", "") or "").strip()
                        if MONTH_SCOPE_RE.match(month):
                            scope_keys.add(month)
                except Exception:
                    pass
        resolved_scope_keys = sorted(scope_keys)
        invalidate_records_cache = getattr(self._workbench_query_service._oa_adapter, "invalidate_records_cache", None)
        if callable(invalidate_records_cache):
            invalidate_records_cache([scope_key for scope_key in resolved_scope_keys if scope_key != "all"])
        return resolved_scope_keys

    @staticmethod
    def _settings_oa_manual_import_month_from_row(row: dict[str, object]) -> str:
        for key in ("month", "application_date", "apply_date", "date"):
            value = str(row.get(key) or "").strip()
            if len(value) >= 7 and MONTH_SCOPE_RE.match(value[:7]):
                return value[:7]
        for item in list(row.get("items") or []):
            if not isinstance(item, dict):
                continue
            value = str(item.get("date") or "").strip()
            if len(value) >= 7 and MONTH_SCOPE_RE.match(value[:7]):
                return value[:7]
        return ""

    @staticmethod
    def _settings_oa_manual_import_affected_scope_payload(scope_keys: list[str]) -> dict[str, object]:
        target_scope_keys = sorted(
            dict.fromkeys(str(scope_key).strip() for scope_key in scope_keys if str(scope_key).strip())
        ) or ["all"]
        return {
            "affected_scope_keys": target_scope_keys,
        }

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

    def _handle_api_workbench_row_detail(
        self,
        row_id: str,
        *,
        month: str | None = None,
        row_type: str | None = None,
    ) -> Response:
        status_code, payload = self._workbench_row_detail_routes().get_result(
            row_id,
            month=month,
            row_type=row_type,
        )
        return self._json_response(status_code, payload)

    def _enforce_admin_access(self, headers: dict[str, str] | None) -> Response | None:
        _, error = self._resolve_admin_session(headers)
        return error

    def _resolve_admin_session(
        self, headers: dict[str, str] | None
    ) -> tuple[OARequestSession | None, Response | None]:
        try:
            session = self._resolve_request_session(headers)
            if not session.can_admin_access:
                return None, self._json_response(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "admin_only",
                        "message": "当前账号没有管理员权限，不能访问管理员功能。",
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

    def _workbench_read_routes(self) -> WorkbenchReadApiRoutes:
        routes = getattr(self, "_workbench_read_api_routes", None)
        if routes is None:
            routes = self._build_workbench_read_api_routes()
            self._workbench_read_api_routes = routes
        return routes

    def _build_workbench_read_api_routes(self) -> WorkbenchReadApiRoutes:
        return WorkbenchReadApiRoutes(query_facade_provider=self._workbench_query_facade)

    def _workbench_group_detail_routes(self) -> WorkbenchGroupDetailApiRoutes:
        routes = getattr(self, "_workbench_group_detail_api_routes", None)
        if routes is None:
            routes = self._build_workbench_group_detail_api_routes()
            self._workbench_group_detail_api_routes = routes
        return routes

    def _build_workbench_group_detail_api_routes(self) -> WorkbenchGroupDetailApiRoutes:
        return WorkbenchGroupDetailApiRoutes(query_facade_provider=self._workbench_query_facade)

    def _workbench_row_detail_routes(self) -> WorkbenchRowDetailApiRoutes:
        routes = getattr(self, "_workbench_row_detail_api_routes", None)
        if routes is None:
            routes = self._build_workbench_row_detail_api_routes()
            self._workbench_row_detail_api_routes = routes
        return routes

    def _build_workbench_row_detail_api_routes(self) -> WorkbenchRowDetailApiRoutes:
        return WorkbenchRowDetailApiRoutes(
            query_facade_provider=self._workbench_query_facade,
        )

    def _emit_cost_statistics_explorer_metric(
        self,
        *,
        month: str,
        duration_ms: float,
        entry_count: int,
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "cost_statistics_explorer_metric",
                    "metric": "cost_statistics.explorer.duration_ms",
                    "month": month,
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
        duration_ms: float,
        payload: dict[str, object],
    ) -> None:
        print(
            json.dumps(
                {
                    "kind": "tax_offset_month_metric",
                    "metric": "tax_offset.month.duration_ms",
                    "month": month,
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

    def _cost_statistics_file_response(self, filename: str, content: bytes) -> Response:
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    def _handle_api_workbench_confirm_link(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        access_session: OARequestSession | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        auth_context = self._workbench_write_auth_context(headers, session=access_session)
        if isinstance(auth_context, Response):
            return auth_context
        actor_id, tenant_id = auth_context
        return self._handle_live_workbench_confirm_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    def _handle_api_workbench_confirm_link_preview(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        status, preview = self._workbench_action_api_routes.confirm_link_preview(payload)
        return self._json_response(status, preview)

    def _handle_api_workbench_cancel_link(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        access_session: OARequestSession | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        auth_context = self._workbench_write_auth_context(headers, session=access_session)
        if isinstance(auth_context, Response):
            return auth_context
        actor_id, tenant_id = auth_context
        return self._handle_live_workbench_cancel_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )

    def _handle_api_workbench_withdraw_link_preview(self, body: str | None) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        result = self._workbench_action_api_routes.withdraw_link_preview(payload)
        return self._workbench_write_response(result)

    def _handle_api_workbench_withdraw_link(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
        headers: dict[str, str] | None = None,
        access_session: OARequestSession | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        auth_context = self._workbench_write_auth_context(headers, session=access_session)
        if isinstance(auth_context, Response):
            return auth_context
        actor_id, tenant_id = auth_context
        if not isinstance(getattr(self, "_workbench_action_api_routes", None), WorkbenchActionApiRoutes):
            self._workbench_action_api_routes = WorkbenchActionApiRoutes(
                write_facade_provider=self._workbench_write_facade,
                anomaly_review_service=getattr(self, "_workbench_anomaly_review_service", None),
            )
        result = self._workbench_action_api_routes.withdraw_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        return self._workbench_write_response(result)

    def _handle_api_workbench_confirm_cash_pass_through(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        result = self._workbench_action_api_routes.confirm_cash_pass_through(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _handle_api_workbench_confirm_cash_ticket_purchase(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        result = self._workbench_action_api_routes.confirm_cash_ticket_purchase(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _handle_api_workbench_cancel_cash_special(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        result = self._workbench_action_api_routes.cancel_cash_special(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _handle_api_workbench_confirm_personal_advance_repayment(
        self,
        body: str | None,
        *,
        request_id: str | None = None,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        safety_error = self._workbench_oa_sync_safety_guard(payload)
        if safety_error is not None:
            return safety_error
        result = self._workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _get_or_build_tax_offset_month_payload(self, month: str) -> dict[str, object]:
        return self._tax_offset_query().get_month_payload(month)

    def _get_tax_offset_month_summary_payload(self, month: str) -> dict[str, object]:
        return self._tax_offset_query().get_summary_payload(month)

    @staticmethod
    def _default_bank_auto_tag_rules_file_source() -> dict[str, object]:
        fixture_path = (
            Path(__file__).resolve().parents[4]
            / "fixtures"
            / "bank_auto_tag_rules"
            / "bank_flow_tag_rules_ui2.normalized.json"
        )
        return json.loads(fixture_path.read_text(encoding="utf-8"))

    def _bank_details_export_response(self, status: HTTPStatus, result: object) -> Response:
        content = getattr(result, "content")
        filename = str(getattr(result, "filename"))
        return Response(
            status_code=int(status),
            body=content,
            headers={
                "Content-Type": XLSX_MIME_TYPE,
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )

    def _current_bank_auto_tag_rules_version(self) -> int:
        try:
            payload = self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=False)
        except Exception:
            return 1
        return self._int_or_none(payload.get("version")) or 1

    def _active_bank_auto_tag_rule_codes(self) -> list[str]:
        payload = self._app_settings_service.get_bank_auto_tag_rules_payload(can_save=False)
        active_rules = payload.get("active_rules") if isinstance(payload, dict) else []
        codes: list[str] = []
        seen: set[str] = set()
        if not isinstance(active_rules, list):
            return codes
        for rule in active_rules:
            if not isinstance(rule, dict):
                continue
            code = str(rule.get("code") or "").strip()
            if code and code not in seen:
                seen.add(code)
                codes.append(code)
        return codes

    @staticmethod
    def _int_or_none(value: object) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _handle_api_import_fact_invoices(self, query: dict[str, list[str]]) -> Response:
        repository = getattr(self._state_store, "import_fact_repository", None)
        page_loader = getattr(repository, "list_invoices_page", None)
        if not callable(page_loader):
            return self._json_response(
                HTTPStatus.NOT_IMPLEMENTED,
                {"error": "sql_import_facts_unavailable", "message": "SQL import fact repository is not configured."},
            )
        try:
            page, page_size = self._pagination_from_query(query)
            rows, total = page_loader(
                page=page,
                page_size=page_size,
                month=query.get("month", [None])[0],
                invoice_type=query.get("invoice_type", [None])[0],
                status=query.get("status", [None])[0],
                keyword=query.get("keyword", [None])[0],
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_fact_query", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"items": self._serialize_value(rows), "pagination": {"page": page, "page_size": page_size, "total": total}},
        )

    def _handle_api_import_fact_batches(self, query: dict[str, list[str]]) -> Response:
        repository = getattr(self._state_store, "import_fact_repository", None)
        page_loader = getattr(repository, "list_import_batches_page", None)
        if not callable(page_loader):
            return self._json_response(
                HTTPStatus.NOT_IMPLEMENTED,
                {"error": "sql_import_facts_unavailable", "message": "SQL import fact repository is not configured."},
            )
        try:
            page, page_size = self._pagination_from_query(query)
            rows, total = page_loader(
                page=page,
                page_size=page_size,
                batch_type=query.get("batch_type", [None])[0],
                status=query.get("status", [None])[0],
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_fact_query", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {"items": self._serialize_value(rows), "pagination": {"page": page, "page_size": page_size, "total": total}},
        )

    def _serialize_import_fact_file_list_item(self, item: object) -> dict[str, object]:
        payload = self._serialize_value(item)
        if not isinstance(payload, dict):
            return {}
        payload.pop("row_results", None)
        payload.pop("normalized_rows", None)
        return payload

    def _handle_api_import_fact_files(self, query: dict[str, list[str]]) -> Response:
        repository = getattr(self._state_store, "import_fact_repository", None)
        page_loader = getattr(repository, "list_import_files_page", None)
        if not callable(page_loader):
            return self._json_response(
                HTTPStatus.NOT_IMPLEMENTED,
                {"error": "sql_import_facts_unavailable", "message": "SQL import fact repository is not configured."},
            )
        try:
            page, page_size = self._pagination_from_query(query)
            rows, total = page_loader(
                page=page,
                page_size=page_size,
                session_id=query.get("session_id", [None])[0],
                status=query.get("status", [None])[0],
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_fact_query", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "items": [self._serialize_import_fact_file_list_item(row) for row in rows],
                "pagination": {"page": page, "page_size": page_size, "total": total},
            },
        )

    @staticmethod
    def _pagination_from_query(query: dict[str, list[str]]) -> tuple[int, int]:
        page = max(int((query.get("page") or ["1"])[0] or 1), 1)
        page_size = min(max(int((query.get("page_size") or ["100"])[0] or 100), 1), 500)
        return page, page_size

    def _no_oa_bank_batch_application_service(self) -> NoOaBankBatchApplicationService:
        return NoOaBankBatchApplicationService(
            import_service=self._import_service,
            effective_category_provider=self._bank_transaction_tag_reader(),
            no_oa_bank_batch_service=self._no_oa_bank_batch_service,
            app_settings_service=self._app_settings_service,
            bank_transaction_category_service=self._bank_transaction_category_service,
            pair_relation_snapshot_port=NoOaPairRelationSnapshotPort(self._workbench_pair_relation_service),
            state_store=self._state_store,
            tag_selection_service=self._no_oa_bank_batch_tag_selection_service,
            workbench_matching_source_versions_provider=self._bank_batch_workbench_source_versions,
            bank_transaction_category_affected_months_provider=self._bank_transaction_category_affected_months,
            relation_command_service=self._workbench_relation_command_service(
                repository=self._state_store,
                save_repository=False,
            ),
        )

    def _no_oa_bank_batch_routes(self) -> NoOaBankBatchApiRoutes:
        return NoOaBankBatchApiRoutes(
            self._no_oa_bank_batch_application_service(),
            resolve_mutation_session=self._no_oa_bank_batch_mutation_session,
            load_json_body=self._load_json_body,
            json_response=self._json_response,
        )

    def _bank_flow_rule_batch_application_service(self) -> BankFlowRuleBatchApplicationService:
        query_repository = getattr(self, "_bank_flow_rule_batch_canonical_query_repository", None)
        if not callable(getattr(query_repository, "read_page", None)):
            raise RuntimeError("bank_flow_rule_batch canonical PostgreSQL query repository is unavailable.")
        pair_relation_snapshot_port = BankBatchPairRelationSnapshotPort(
            getattr(self, "_workbench_pair_relation" + "_service")
        )
        relation_source_repository = getattr(
            self._state_store,
            "workbench_relation_repository",
            pair_relation_snapshot_port,
        )
        queue_repository = getattr(
            getattr(self, "_runtime_repositories", None),
            "queue_repository",
            None,
        )
        connection = getattr(self._state_store, "_connection", None)
        recalculation_requests = (
            PostgresBankRelationRequirementRecalculationRequestRepository(
                connection,
                queue_repository,
                self._state_store,
            )
            if connection is not None and queue_repository is not None
            else None
        )
        return BankFlowRuleBatchApplicationService(
            import_service=self._import_service,
            effective_category_provider=self._bank_transaction_tag_reader(),
            bank_batch_service=self._bank_flow_rule_batch_service,
            app_settings_service=self._app_settings_service,
            bank_transaction_category_service=self._bank_transaction_category_service,
            pair_relation_snapshot_port=pair_relation_snapshot_port,
            state_store=self._state_store,
            bank_batch_query_repository=query_repository,
            workbench_matching_source_versions_provider=self._bank_batch_workbench_source_versions,
            bank_transaction_category_affected_months_provider=self._bank_transaction_category_affected_months,
            relation_command_service=self._workbench_relation_command_service(
                repository=self._state_store,
                save_repository=False,
            ),
            relation_source_repository=relation_source_repository,
            background_jobs=self._background_job_service,
            requirement_recalculation_requests=recalculation_requests,
        )

    def _bank_flow_rule_batch_routes(self) -> BankFlowRuleBatchApiRoutes:
        return BankFlowRuleBatchApiRoutes(
            self._bank_flow_rule_batch_application_service(),
            resolve_mutation_session=self._no_oa_bank_batch_mutation_session,
            load_json_body=self._load_json_body,
            json_response=self._json_response,
        )

    def _bank_details_application_service(self) -> BankDetailsApplicationService:
        suggestion_provider = self.__dict__.get("_bank_detail_auto_category_suggestion_provider")
        if suggestion_provider is None:
            import_service = getattr(self, "_import_service", None)
            bank_details_service = getattr(self, "_bank_details_service", None)
            auto_category_service = getattr(self, "_bank_transaction_auto_category_service", None)
            if import_service is not None and bank_details_service is not None and auto_category_service is not None:
                suggestion_provider = BankDetailAutoCategorySuggestionProvider(
                    import_service=import_service,
                    bank_details_service=bank_details_service,
                    bank_transaction_auto_category_service=auto_category_service,
                    serialize_value=self._serialize_value,
                ).latest
        elif not callable(suggestion_provider):
            latest = getattr(suggestion_provider, "latest", None)
            suggestion_provider = latest if callable(latest) else None
        state_store = getattr(self, "_state_store", None)
        storage_backend = str(getattr(state_store, "storage_backend", "") or "").strip()
        category_store = state_store if storage_backend != "postgres" else None
        category_mutation_service = self._bank_category_relation_closure_service()
        connection = (
            getattr(state_store, "_sql_read_connection", None)
            or getattr(state_store, "_connection", None)
        )
        query_service = (
            BankDetailsCanonicalQueryService(
                PostgresBankDetailsCanonicalQueryRepository(connection)
            )
            if connection is not None
            else None
        )
        return BankDetailsApplicationService(
            query_service=query_service,
            app_settings_service=getattr(self, "_app_settings_service", SimpleNamespace(get_bank_auto_tag_rules_payload=lambda **_kwargs: {"version": 1, "active_rules": []})),
            bank_transaction_category_service=getattr(self, "_bank_transaction_category_service", SimpleNamespace(snapshot=lambda: {})),
            bank_transaction_auto_category_service=getattr(self, "_bank_transaction_auto_category_service", SimpleNamespace(current_rule_version=lambda: 1, suggest_for_rows=lambda _rows: {})),
            audit_service=getattr(self, "_audit_service", SimpleNamespace(record_action=lambda **_kwargs: None)),
            bank_transaction_category_store=category_store,
            affected_months_provider=getattr(self, "_bank_transaction_category_affected_months", lambda _transaction_ids: []),
            suggestion_provider=suggestion_provider if callable(suggestion_provider) else None,
            category_mutation_service=category_mutation_service,
        )

    def _bank_category_relation_closure_service(
        self,
    ) -> BankCategoryRelationClosureService | None:
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres":
            return None
        connection = getattr(state_store, "_connection", None)
        category_writer = self._bank_transaction_category_mutation_writer()
        if connection is None or category_writer is None:
            return None
        return BankCategoryRelationClosureService(
            connection=connection,
            category_writer=category_writer,
            relation_repository_factory=PostgresWorkbenchRelationRepository,
            effective_category_rows=(
                PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows
            ),
            settings_snapshot_provider=lambda transaction: (
                AppSettingsService.bank_category_relation_policy_snapshot(
                    PostgresOpsTaxEtcRepository(transaction).load_settings(
                        APP_SETTINGS_KEY
                    )
                )
            ),
            relation_delta_publisher=getattr(
                self,
                "_workbench_pair_relation" + "_service",
            ).apply_snapshot_delta,
        )

    def _bank_transaction_category_mutation_writer(self) -> BankTransactionCategoryMutationWriter | None:
        state_store = getattr(self, "_state_store", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres":
            return None
        category_repository = getattr(state_store, "bank_transaction_category_repository", None)
        connection = getattr(state_store, "_connection", None)
        if connection is None or category_repository is None:
            return None
        return BankTransactionCategoryMutationWriter(
            connection=connection,
            repository=category_repository,
        )

    def _bank_details_routes(self) -> BankDetailsApiRoutes:
        return BankDetailsApiRoutes(
            self._bank_details_application_service(),
            resolve_read_session=self._resolve_bank_details_read_session,
            json_response=self._json_response,
            export_response=self._bank_details_export_response,
            load_json_body=self._load_json_body,
            default_auto_tag_rules_source_provider=self._default_bank_auto_tag_rules_file_source,
        )

    def _no_oa_bank_batch_workbench_payload_decorator(self) -> NoOaBankBatchWorkbenchPayloadDecorator:
        return NoOaBankBatchWorkbenchPayloadDecorator(batch_provider=self._no_oa_bank_batch_service.get_batch)

    def _no_oa_bank_batch_workbench_display_policy(self) -> NoOaBankBatchWorkbenchDisplayPolicy:
        return NoOaBankBatchWorkbenchDisplayPolicy(label_provider=self._bank_transaction_tag_label_current)

    def _batch_accounting_service(self) -> BatchAccountingService:
        return BatchAccountingService(
            query_repository=getattr(self, "_batch_accounting_query_repository", None),
            relation_command_service=self._batch_accounting_relation_command_service(),
            app_settings_service=self._app_settings_service,
        )

    def _batch_accounting_relation_command_service(self) -> WorkbenchRelationCommandService:
        state_store = getattr(self, "_state_store", None)
        storage_backend = str(getattr(state_store, "storage_backend", "") or "").strip()
        connection = getattr(state_store, "_connection", None)
        repository = (
            PostgresWorkbenchRelationRepository(connection)
            if storage_backend == "postgres" and connection is not None
            else None
        )
        return self._workbench_relation_command_service(repository=repository)

    def _batch_accounting_routes(self) -> BatchAccountingApiRoutes:
        routes = getattr(self, "_batch_accounting_api_routes", None)
        if isinstance(routes, BatchAccountingApiRoutes):
            return routes
        routes = BatchAccountingApiRoutes(self._batch_accounting_service)
        self._batch_accounting_api_routes = routes
        return routes

    def _handle_api_batch_accounting(self, query: dict[str, list[str]]) -> Response:
        timings: list[tuple[str, float]] = []
        service_started_at = monotonic()
        status_code, payload = self._batch_accounting_routes().list_payload(
            query,
            timing_observer=lambda phase, duration_ms: timings.append((phase, duration_ms)),
        )
        timings.append(("service_total", self._duration_ms(service_started_at)))
        serialization_started_at = monotonic()
        response = self._json_response(status_code, payload)
        timings.append(("serialization", self._duration_ms(serialization_started_at)))
        response.headers["Server-Timing"] = ", ".join(
            f"batch_{phase};dur={duration_ms:.3f}"
            for phase, duration_ms in timings
        )
        return response

    def _handle_api_batch_accounting_submit(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        access_session: OARequestSession | None = None,
    ) -> Response:
        session = self._batch_accounting_mutation_session(headers, session=access_session)
        if isinstance(session, Response):
            return session
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        status_code, result = self._batch_accounting_routes().submit(payload, session=session)
        return self._json_response(status_code, result)

    def _handle_api_batch_accounting_tag_rules(
        self,
        headers: dict[str, str] | None,
        *,
        access_session: OARequestSession | None = None,
    ) -> Response:
        session = access_session or self._resolve_request_session(headers)
        status_code, result = self._batch_accounting_routes().tag_rules(
            can_save=session.can_mutate_data,
        )
        return self._json_response(status_code, result)

    def _handle_api_batch_accounting_tag_rules_update(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        access_session: OARequestSession | None = None,
    ) -> Response:
        session = self._batch_accounting_mutation_session(headers, session=access_session)
        if isinstance(session, Response):
            return session
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        status_code, result = self._batch_accounting_routes().update_tag_rules(
            payload,
            session=session,
        )
        return self._json_response(status_code, result)

    def _handle_api_batch_accounting_withdraw(
        self,
        relation_id: str,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        access_session: OARequestSession | None = None,
    ) -> Response:
        session = self._batch_accounting_mutation_session(headers, session=access_session)
        if isinstance(session, Response):
            return session
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        status_code, result = self._batch_accounting_routes().withdraw(relation_id, payload, session=session)
        return self._json_response(status_code, result)

    def _batch_accounting_mutation_session(
        self,
        headers: dict[str, str] | None,
        *,
        session: OARequestSession | None = None,
    ) -> OARequestSession | Response:
        session = session or self._resolve_request_session(headers)
        if not session.can_mutate_data:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有提交或撤回批量账务关联的权限。"},
            )
        return session

    def _bank_transaction_tag_definition_current(self, code: str) -> dict[str, object] | None:
        tag_code = str(code or "").strip()
        if not tag_code:
            return None
        payload = self._bank_transaction_category_service.tag_dictionary_payload()
        for definition in list(payload.get("definitions") or []):
            if isinstance(definition, dict) and str(definition.get("code") or "").strip() == tag_code:
                return dict(definition)
        return None

    @staticmethod
    def _bank_transaction_tag_label_from_definition(code: str, definition: dict[str, object] | None) -> str:
        if isinstance(definition, dict):
            return str(definition.get("label") or definition.get("output_sub_label") or definition.get("output_primary_label") or code)
        return NO_OA_MANAGED_LABELS.get(code, BANK_TRANSACTION_CATEGORY_LABELS.get(code, code))

    def _bank_transaction_tag_label_current(self, code: str) -> str:
        tag_code = str(code or "").strip()
        if not tag_code:
            return ""
        return self._bank_transaction_tag_label_from_definition(
            tag_code,
            self._bank_transaction_tag_definition_current(tag_code),
        )

    def _no_oa_bank_batch_mutation_session(self, headers: dict[str, str] | None) -> OARequestSession | Response:
        session = self._resolve_request_session(headers)
        if not session.can_mutate_data:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有提交免OA流水批次的权限。"},
            )
        return session

    @staticmethod
    def _optional_int(value: object) -> int | None:
        if value in (None, ""):
            return None
        return int(value)

    @staticmethod
    def _turnover_ledger_export_response(filename: str, content: bytes) -> Response:
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": XLSX_MIME_TYPE,
                "Content-Disposition": _build_content_disposition(filename),
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    def _turnover_ledger_tag_selection_request_boundary_facade(self) -> TurnoverLedgerTagSelectionRequestBoundaryFacade:
        return TurnoverLedgerTagSelectionRequestBoundaryFacade(
            facade_provider=self._turnover_ledger_tag_selection_write_facade,
        )

    def _turnover_ledger_bank_row_tags_request_boundary_facade(self) -> TurnoverLedgerBankRowTagsRequestBoundaryFacade:
        return TurnoverLedgerBankRowTagsRequestBoundaryFacade(
            facade_provider=self._turnover_ledger_bank_row_tags_write_facade,
            target_validator=self._ensure_turnover_bank_row_tag_targets,
            affected_months_resolver=self._bank_transaction_category_affected_months,
        )

    def _ensure_turnover_bank_row_tag_targets(self, transaction_ids: list[str]) -> None:
        if not transaction_ids:
            raise BankTransactionCategoryValidationError(
                "invalid_turnover_bank_row_tag_update",
                "updates must contain at least one transaction_id.",
            )
        if len(set(transaction_ids)) != len(transaction_ids):
            raise BankTransactionCategoryValidationError(
                "invalid_turnover_bank_row_tag_update",
                "duplicate transaction_id in updates.",
            )
        rows: list[dict[str, object]] = []
        for transaction_id in transaction_ids:
            try:
                transaction = self._import_service.get_transaction(transaction_id)
            except KeyError as exc:
                raise BankTransactionCategoryValidationError(
                    "unknown_transaction_id",
                    f"Unknown bank transaction id: {transaction_id}",
                    transaction_id=transaction_id,
                ) from exc
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                payload = {}
            rows.append(dict(payload, id=transaction_id))
        categories = self._bank_transaction_tag_reader().bulk_get_for_rows(rows)
        for transaction_id in transaction_ids:
            category = categories.get(transaction_id) or {}
            code = str(category.get("category_code") or "").strip()
            manual = self._bank_transaction_category_service.get(transaction_id)
            manual_code = str(manual.get("category_code") or "").strip()
            manual_source = str(manual.get("source") or "").strip()
            if code == "external_turnover" or code in TURNOVER_CATEGORY_RULES:
                continue
            if manual_code in TURNOVER_CATEGORY_RULES and manual_source == "turnover_ledger":
                continue
            raise BankTransactionCategoryValidationError(
                "not_turnover_bank_row",
                f"Bank transaction is not tagged as turnover: {transaction_id}",
                transaction_id=transaction_id,
            )

    def _turnover_ledger_relation_extra_request_boundary_facade(self) -> TurnoverLedgerRelationExtraRequestBoundaryFacade:
        return TurnoverLedgerRelationExtraRequestBoundaryFacade(
            facade_provider=self._turnover_ledger_relation_extra_write_facade,
            relation_detail_provider=self._turnover_ledger_api_routes.get_relation,
        )

    @staticmethod
    def _turnover_write_precondition_error_payload(exc: TurnoverLedgerWritePreconditionError) -> dict[str, object]:
        payload: dict[str, object] = {"error": exc.error_code, "message": str(exc)}
        details = getattr(exc, "payload", None)
        if isinstance(details, dict):
            payload.update(
                {
                    str(key): value
                    for key, value in details.items()
                    if str(key)
                    in {
                        "conflicting_case_ids",
                        "row_ids",
                    }
                }
            )
        return payload

    def _turnover_mutation_session(self, headers: dict[str, str] | None) -> OARequestSession | Response:
        session = self._resolve_request_session(headers)
        if not session.can_mutate_data:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "permission_denied", "message": "当前账户没有操作往来款关系的权限。"},
            )
        return session

    def _bank_transaction_category_affected_months(self, transaction_ids: list[str]) -> list[str]:
        months: set[str] = set()
        for transaction_id in transaction_ids:
            try:
                transaction = self._import_service.get_transaction(transaction_id)
            except KeyError:
                continue
            payload = self._serialize_value(transaction)
            if not isinstance(payload, dict):
                continue
            month = str(payload.get("trade_time") or payload.get("txn_date") or "")[:7]
            if MONTH_SCOPE_RE.match(month):
                months.add(month)
        return sorted(months)

    def _turnover_bank_transaction_affected_months(self, transaction_ids: list[str]) -> list[str]:
        months: set[str] = set()
        transactions = self._import_service.list_transactions_by_ids(transaction_ids)
        for transaction in transactions:
            row = self._serialize_value(transaction)
            if not isinstance(row, dict):
                continue
            month = str(row.get("trade_time") or row.get("txn_date") or "")[:7]
            if MONTH_SCOPE_RE.match(month):
                months.add(month)
        return sorted(months)

    def _finalize_bank_transaction_tag_settings_update(self, event: dict[str, object]) -> None:
        pending_invoice_service = getattr(self, "_pending_invoice_query_service", None)
        for method_name in ("clear_cache", "invalidate_cache", "refresh"):
            method = getattr(pending_invoice_service, method_name, None)
            if callable(method):
                try:
                    method()
                except TypeError:
                    method(event)
                break

    def _handle_live_workbench_confirm_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Response:
        result = self._workbench_action_api_routes.confirm_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        return self._workbench_write_response(result)

    def _handle_live_workbench_cancel_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> Response:
        result = self._workbench_action_api_routes.cancel_link(
            payload,
            request_id=request_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        return self._workbench_write_response(result)

    def _handle_live_workbench_withdraw_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> Response:
        result = self._workbench_action_api_routes.withdraw_link(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _handle_live_workbench_confirm_personal_advance_repayment(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> Response:
        result = self._workbench_action_api_routes.confirm_personal_advance_repayment(payload, request_id=request_id)
        return self._workbench_write_response(result)

    def _postgres_oa_projection_repository(self) -> object | None:
        if not self._requires_postgres_runtime():
            return None
        repository = getattr(self._state_store, "oa_projection_repository", None)
        return repository if repository is not None else None

    def _postgres_oa_projection_latest_sync_run(self) -> dict[str, object] | None:
        repository = self._postgres_oa_projection_repository()
        list_runs = getattr(repository, "list_sync_runs", None)
        if not callable(list_runs):
            return None
        runs = list_runs(limit=1)
        return runs[0] if runs else None

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

    def build_import_job_processors(self) -> dict[str, Callable[[ImportJob], dict[str, object]]]:
        return self._import_processing_service.build_import_job_processors()

    def _process_oa_manual_import_create_job(self, import_job: ImportJob) -> dict[str, object]:
        row_ids = import_job.payload.get("row_ids")
        if not isinstance(row_ids, list):
            raise ValueError("import job payload.row_ids is required.")
        actor_id = str(import_job.payload.get("actor_id") or import_job.created_by or "workbench_settings").strip()
        return self._execute_oa_manual_import_create([str(row_id) for row_id in row_ids], actor_id=actor_id)

    def _handle_import_batch(self, batch_id: str) -> Response:
        try:
            preview = self._import_service.get_batch(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_preview(preview))

    def _import_processing_backend(self) -> str:
        explicit = str(os.getenv("FIN_OPS_IMPORT_PROCESSING_BACKEND") or "").strip().lower()
        if explicit and explicit != "postgres":
            raise RuntimeError("FIN_OPS_IMPORT_PROCESSING_BACKEND must be postgres.")
        return "postgres"

    def _import_job_processing_enabled(self) -> bool:
        self._import_processing_backend()
        queue_repository = getattr(getattr(self, "_runtime_repositories", None), "queue_repository", None)
        return callable(getattr(queue_repository, "enqueue", None))

    def _get_import_job_repository(self) -> ImportJobRepository:
        injected = getattr(self, "_import_job_repository_override", None)
        if injected is None:
            injected = self.__dict__.get("_import_job_repository")
        if injected is not None:
            return injected
        connection = getattr(self._state_store, "_connection", None)
        if connection is None:
            raise RuntimeError("PostgreSQL import job repository is not available.")
        repository = ImportJobRepository(connection)
        self._import_job_repository = repository
        return repository

    def _enqueue_import_process_job(
        self,
        *,
        import_type: str,
        payload: dict[str, object],
        idempotency_key: str,
        import_session_id: str | None = None,
        source_file_id: str | None = None,
        created_by: str | None = None,
        priority: str = "normal",
        reason: str = "import_confirm",
    ):
        queue_repository = getattr(getattr(self, "_runtime_repositories", None), "queue_repository", None)
        if queue_repository is None or not callable(getattr(queue_repository, "enqueue", None)):
            raise RuntimeError("Runtime queue repository is not available.")
        repository = self._get_import_job_repository()
        import_job = repository.create_or_get_job(
            import_type=import_type,
            import_session_id=import_session_id,
            source_file_id=source_file_id,
            idempotency_key=idempotency_key,
            payload=payload,
            raw_payload={"request_payload": payload},
            created_by=created_by,
            priority=priority,
        )
        if import_job.status in {"succeeded", "failed", "canceled"}:
            return import_job, None
        event = repository.enqueue_process_requested(
            queue_repository=queue_repository,
            import_job=import_job,
            reason=reason,
        )
        return import_job, event

    @staticmethod
    def _serialize_import_job(import_job: ImportJob) -> dict[str, object]:
        return TaxCertifiedImportJobService.serialize_import_job(import_job)

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
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    def _handle_import_batch_errors_csv(self, batch_id: str) -> Response:
        try:
            preview = self._import_service.get_batch(batch_id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "batch_not_found", "batch_id": batch_id},
            )
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(
            [
                "行号",
                "数据类型",
                "处理结果",
                "原因",
                "银行账户",
                "交易时间",
                "收支方向",
                "金额",
                "对方名称",
                "发票号码",
                "开票日期",
                "销方名称",
                "购方名称",
                "税额",
                "价税合计",
            ]
        )
        for row in preview.row_results:
            decision = row.decision.value if isinstance(row.decision, Enum) else str(row.decision)
            if decision not in {"error", "suspected_duplicate"}:
                continue
            raw_payload = dict(getattr(row, "raw_payload", {}) or {})
            invoice_no = raw_payload.get("digital_invoice_no") or raw_payload.get("invoice_no")
            writer.writerow(
                [
                    row.row_no,
                    row.source_record_type,
                    decision,
                    row.decision_reason,
                    row.account_no or "",
                    row.trade_time or "",
                    row.direction or "",
                    row.amount or "",
                    row.counterparty_name or "",
                    invoice_no or "",
                    raw_payload.get("invoice_date") or "",
                    raw_payload.get("seller_name") or "",
                    raw_payload.get("buyer_name") or "",
                    raw_payload.get("tax_amount") or "",
                    raw_payload.get("total_with_tax") or "",
                ]
            )
        body = "\ufeff" + output.getvalue()
        return Response(
            status_code=int(HTTPStatus.OK),
            body=body,
            headers={
                "Content-Type": "text/csv; charset=utf-8",
                "Content-Disposition": 'attachment; filename="import-errors.csv"',
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
            },
        )

    def _handle_import_templates(self) -> Response:
        return self._json_response(
            HTTPStatus.OK,
            {
                "templates": self._file_import_service.list_templates(),
            },
        )

    def _handle_manual_invoice_recognize(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
    ) -> Response:
        _fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
        if not files:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "manual_invoice_file_required", "message": "请选择 JPG、JPEG、PNG 或 PDF 发票文件。"},
            )
        upload = files[0]
        try:
            values = self._manual_invoice_entry_service.recognize(
                file_name=upload.file_name,
                content=upload.content,
            )
        except ManualInvoiceEntryError as exc:
            return self._json_response(exc.status_code, {"error": exc.error, "message": exc.message})
        return self._json_response(HTTPStatus.OK, {"values": values})

    def _handle_manual_invoice_preview(
        self,
        body: str | bytes | None,
        *,
        imported_by: str,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        try:
            payloads = payload.get("invoices") if isinstance(payload.get("invoices"), list) else []
            preview = self._manual_invoice_entry_service.preview_batch(
                payloads=[item for item in payloads if isinstance(item, dict)],
                imported_by=imported_by,
            )
            self._persist_import_preview_delta(preview.session.id)
        except ManualInvoiceEntryError as exc:
            return self._json_response(exc.status_code, {"error": exc.error, "message": exc.message})
        except RuntimeError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "manual_invoice_preview_unavailable", "message": str(exc)},
            )
        return self._json_response(
            HTTPStatus.OK,
            {
                "values": preview.values,
                "file_ids": preview.file_ids,
                "import_session": self._serialize_file_session(preview.session),
            },
        )

    def _workbench_invoice_supplement_service(self) -> WorkbenchInvoiceSupplementService:
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres" or connection is None:
            raise RuntimeError("Workbench invoice supplements require PostgreSQL storage.")
        return WorkbenchInvoiceSupplementService(
            connection=connection,
            file_import_service=self._file_import_service,
            relation_repository_factory=PostgresWorkbenchRelationRepository,
            relation_command_service_factory=lambda repository: self._workbench_relation_command_service(
                repository=repository
            ),
            target_exists=self._workbench_oa_expense_item_target_exists,
            next_case_id=self._next_workbench_relation_case_id,
            persist_import_delta=lambda transaction, imports_snapshot, file_imports_snapshot: (
                PostgresCoreRepository(transaction).save_import_delta_in_transaction(
                    transaction,
                    imports_snapshot=imports_snapshot,
                    file_imports_snapshot=file_imports_snapshot,
                )
            ),
            restore_import_runtime=self._reload_file_import_runtime_state,
        )

    def _handle_workbench_manual_invoice_supplement(
        self,
        body: str | bytes | None,
        *,
        actor_id: str,
        request_id: str,
    ) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    failure_code="invalid_manual_invoice_supplement",
                    failure_message="请求内容不是有效的发票录入数据，未写入发票池。",
                )
            )
            return error
        target = workbench_oa_target(
            case_id=str(payload.get("case_id") or ""),
            oa_row_id=str(payload.get("oa_row_id") or ""),
            expense_item_id=str(payload.get("expense_item_id") or ""),
        )
        _REQUEST_AUDIT_EVIDENCE.set(build_operation_evidence(target=target))
        try:
            result = self._workbench_invoice_supplement_service().attach_manual_invoices(
                ManualInvoiceSupplementCommand(
                    session_id=str(payload.get("session_id") or ""),
                    file_ids=tuple(str(value) for value in list(payload.get("file_ids") or [])),
                    oa_row_id=str(payload.get("oa_row_id") or ""),
                    expense_item_id=str(payload.get("expense_item_id") or ""),
                    case_id=str(payload.get("case_id") or ""),
                    actor_id=actor_id,
                    request_id=request_id,
                )
            )
        except WorkbenchInvoiceSupplementError as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    failure_code=exc.error,
                    failure_message=exc.message,
                )
            )
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": exc.error, "message": exc.message},
            )
        except WorkbenchRelationCommandError as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    failure_code=exc.error_code,
                    failure_message=exc.message,
                )
            )
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": exc.error_code, "message": exc.message, **dict(exc.payload or {})},
            )
        except (KeyError, PermissionError, ValueError) as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    failure_code="invalid_manual_invoice_supplement",
                    failure_message=str(exc),
                )
            )
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_manual_invoice_supplement", "message": str(exc)},
            )
        except RuntimeError as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    failure_code="manual_invoice_supplement_unavailable",
                    failure_message=str(exc),
                )
            )
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "manual_invoice_supplement_unavailable", "message": str(exc)},
            )
        invoice_evidence_rows = list(result.pop("invoice_evidence_rows", []))
        invoice_summaries = [
            manual_invoice_record(
                dict(item.get("normalized") or {}),
                record_key=str(item.get("record_key") or ""),
            )
            for item in invoice_evidence_rows
            if isinstance(item, dict)
        ]
        resolved_target = workbench_oa_target(
            case_id=str(result.get("case_id") or payload.get("case_id") or ""),
            oa_row_id=str(payload.get("oa_row_id") or ""),
            expense_item_id=str(payload.get("expense_item_id") or ""),
        )
        _REQUEST_AUDIT_EVIDENCE.set(
            build_operation_evidence(
                target=resolved_target,
                records=invoice_summaries,
                changes=[
                    {
                        "label": "发票处理",
                        "before": "尚未录入",
                        "after": f"{len(invoice_summaries)} 张已录入发票池并关联",
                    }
                ],
            )
        )
        return self._json_response(HTTPStatus.OK, result)

    def _workbench_oa_supporting_document_service(self) -> WorkbenchOaSupportingDocumentService:
        state_store = getattr(self, "_state_store", None)
        connection = getattr(state_store, "_connection", None)
        if str(getattr(state_store, "storage_backend", "") or "").strip() != "postgres" or connection is None:
            raise RuntimeError("Workbench supporting documents require PostgreSQL storage.")
        return WorkbenchOaSupportingDocumentService(
            repository=PostgresWorkbenchOaSupportingDocumentRepository(connection),
            file_store=state_store,
            target_exists=self._workbench_oa_expense_item_target_exists,
        )

    def _handle_workbench_supporting_document_upload(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        actor_id: str,
    ) -> Response:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    failure_code="invalid_supporting_document_upload",
                    failure_message="上传请求格式无效，文件未保存。",
                )
            )
            return error
        case_id = str((fields.get("case_id") or [""])[0] or "")
        oa_row_id = str((fields.get("oa_row_id") or [""])[0] or "")
        expense_item_id = str((fields.get("expense_item_id") or [""])[0] or "")
        target = workbench_oa_target(
            case_id=case_id,
            oa_row_id=oa_row_id,
            expense_item_id=expense_item_id,
        )
        attempted_artifacts = attempted_supporting_document_artifacts(files)
        _REQUEST_AUDIT_EVIDENCE.set(
            build_operation_evidence(target=target, artifacts=attempted_artifacts)
        )
        try:
            documents = self._workbench_oa_supporting_document_service().upload(
                relation_case_id=case_id,
                oa_row_id=oa_row_id,
                expense_item_id=expense_item_id,
                actor_id=actor_id,
                uploads=[
                    SupportingDocumentUpload(file_name=file.file_name, content=file.content)
                    for file in files
                ],
            )
        except WorkbenchOaSupportingDocumentError as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    artifacts=attempted_artifacts,
                    failure_code=exc.error,
                    failure_message=exc.message,
                )
            )
            return self._json_response(HTTPStatus.BAD_REQUEST, {"error": exc.error, "message": exc.message})
        except RuntimeError:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    target=target,
                    artifacts=attempted_artifacts,
                    failure_code="supporting_document_unavailable",
                    failure_message="文件存储暂时不可用，上传未保存。请稍后重试。",
                )
            )
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": "supporting_document_unavailable",
                    "message": "文件存储暂时不可用，上传未保存。请稍后重试。",
                },
            )
        _REQUEST_AUDIT_EVIDENCE.set(
            build_operation_evidence(
                target=target,
                artifacts=[supporting_document_artifact(document) for document in documents],
                changes=[
                    {
                        "label": "补充凭证",
                        "before": "未上传",
                        "after": f"已关联 {len(documents)} 个文件",
                    }
                ],
            )
        )
        return self._json_response(HTTPStatus.CREATED, {"documents": documents})

    def _handle_workbench_supporting_document_list(self, query: dict[str, list[str]]) -> Response:
        try:
            documents = self._workbench_oa_supporting_document_service().list(
                oa_row_id=str((query.get("oa_row_id") or [""])[0] or ""),
                expense_item_id=str((query.get("expense_item_id") or [""])[0] or ""),
            )
        except RuntimeError as exc:
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "supporting_document_unavailable", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, {"documents": documents})

    def _handle_workbench_supporting_document_content(self, document_id: str) -> Response:
        try:
            document, content = self._workbench_oa_supporting_document_service().content(document_id)
        except WorkbenchOaSupportingDocumentError as exc:
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": exc.error, "message": exc.message})
        return Response(
            status_code=int(HTTPStatus.OK),
            body=content,
            headers={
                "Content-Type": str(document.get("content_type") or "application/octet-stream"),
                "Content-Disposition": f'inline; filename="{_build_ascii_download_name(str(document.get("original_filename") or "document"))}"',
                "Cache-Control": "private, max-age=60",
            },
        )

    def _handle_workbench_supporting_document_delete(self, document_id: str, *, actor_id: str) -> Response:
        try:
            document = self._workbench_oa_supporting_document_service().delete(document_id, actor_id=actor_id)
        except WorkbenchOaSupportingDocumentError as exc:
            _REQUEST_AUDIT_EVIDENCE.set(
                build_operation_evidence(
                    failure_code=exc.error,
                    failure_message=exc.message,
                )
            )
            return self._json_response(HTTPStatus.NOT_FOUND, {"error": exc.error, "message": exc.message})
        _REQUEST_AUDIT_EVIDENCE.set(
            build_operation_evidence(
                target=workbench_oa_target(
                    case_id=str(document.get("relation_case_id") or ""),
                    oa_row_id=str(document.get("oa_row_id") or ""),
                    expense_item_id=str(document.get("expense_item_id") or ""),
                ),
                artifacts=[supporting_document_artifact(document, availability="deleted")],
                changes=[{"label": "补充凭证", "before": "可预览", "after": "已删除"}],
            )
        )
        return self._json_response(HTTPStatus.OK, {"status": "deleted", "document_id": document_id})

    def _handle_import_file_preview(
        self,
        body: str | bytes | None,
        headers: dict[str, str] | None,
        *,
        imported_by: str,
    ) -> Response:
        fields, files, error = self._load_multipart_body(body, headers)
        if error is not None:
            return error
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
                    field_mapping=dict(override.get("field_mapping") or {}),
                )
                for file, override in zip(files, file_overrides)
            ]
        session = self._file_import_service.preview_files(imported_by=imported_by, uploads=files)
        self._persist_import_preview_delta(session.id)
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_confirm(self, body: str | bytes | None, *, owner_user_id: str) -> Response:
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
        normalized_selected_file_ids = sorted({str(item).strip() for item in selected_file_ids if str(item).strip()})
        if not normalized_selected_file_ids:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_confirm_request", "message": "selected_file_ids cannot be empty."},
            )
        self._reload_file_import_runtime_state()
        try:
            session = self._file_import_service.get_session(normalized_session_id)
        except KeyError as exc:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": str(exc)},
            )
        if str(session.imported_by) != str(owner_user_id):
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "import_file_session_forbidden", "message": "Import session belongs to another user."},
            )

        selected = set(normalized_selected_file_ids)
        unknown_ids = sorted(selected - {item.id for item in session.files})
        if unknown_ids:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "message": f"Unknown selected file ids: {', '.join(unknown_ids)}"},
            )
        invalid_ids = sorted(
            item.id
            for item in session.files
            if item.id in selected and item.status not in {"preview_ready", "confirmed"}
        )
        if invalid_ids:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "import_file_session_not_confirmable",
                    "message": f"Selected files are not confirmable: {', '.join(invalid_ids)}",
                },
            )
        try:
            if any(item.id in selected and item.status == "preview_ready" for item in session.files):
                self._file_import_service.assert_session_preview_current(session_id=normalized_session_id)
        except ImportPreviewStaleError as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {
                    "error": "preview_stale",
                    "message": "Preview audit is stale. Refresh the preview before confirming.",
                    "preview_audit": exc.preview,
                    "current_audit": exc.current,
                },
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "import_file_session_not_confirmable", "message": str(exc)},
            )
        total = len(normalized_selected_file_ids)
        label = ImportProcessingService.file_import_job_label(session, normalized_selected_file_ids)
        selected_key = ",".join(sorted(normalized_selected_file_ids))
        affected_import_domains, import_route = self._file_import_job_status_scope(
            session,
            normalized_selected_file_ids,
        )
        try:
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
                source={
                    "session_id": normalized_session_id,
                    "selected_file_ids": normalized_selected_file_ids,
                    "affected_domains": affected_import_domains,
                    "route": import_route,
                },
                affected_scopes=["imports", "workbench"],
            )
        except BackgroundJobIdempotencyConflict as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "import_idempotency_conflict", "message": str(exc)},
            )
        try:
            import_job, event = self._enqueue_import_process_job(
                import_type="file_import.confirm",
                import_session_id=normalized_session_id,
                idempotency_key=f"file_import.confirm:{normalized_session_id}:{selected_key}",
                payload={
                    "session_id": normalized_session_id,
                    "selected_file_ids": normalized_selected_file_ids,
                    "owner_user_id": owner_user_id,
                    "background_job_id": job.job_id,
                },
                created_by=owner_user_id,
                reason="file_import_confirm",
            )
            job_payload = job.to_payload()
            job_payload["import_job"] = self._serialize_import_job(import_job)
            job_payload["event_id"] = getattr(event, "event_id", None)
            response_payload = self._serialize_file_session(session)
            response_payload["job"] = job_payload
            return self._json_response(HTTPStatus.ACCEPTED, response_payload)
        except ImportJobIdempotencyConflict as exc:
            response_job = job
            if created:
                response_job = self._background_job_service.fail_job(job.job_id, "导入文件任务未启动。", str(exc))
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "import_idempotency_conflict", "message": str(exc), "job": response_job.to_payload()},
            )
        except RuntimeError as exc:
            response_job = job
            if created:
                response_job = self._background_job_service.fail_job(job.job_id, "导入文件任务未启动。", str(exc))
            return self._json_response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "import_queue_unavailable", "message": str(exc), "job": response_job.to_payload()},
            )

    @staticmethod
    def _file_import_job_status_scope(session, selected_file_ids: list[str]) -> tuple[list[str], str]:
        selected = {str(file_id) for file_id in list(selected_file_ids or []) if str(file_id)}
        domains: list[str] = []
        for item in list(getattr(session, "files", []) or []):
            if str(getattr(item, "id", "")) not in selected:
                continue
            batch_type = getattr(item, "batch_type", None)
            domain = ""
            if batch_type == BatchType.BANK_TRANSACTION:
                domain = "imports_bank_transactions"
            elif batch_type in {BatchType.INPUT_INVOICE, BatchType.OUTPUT_INVOICE}:
                domain = "imports_invoices"
            if domain and domain not in domains:
                domains.append(domain)
        if not domains:
            return [], "/operations/app-health"
        route_by_domain = {
            "imports_bank_transactions": "/imports/bank-transactions",
            "imports_invoices": "/imports/invoices",
        }
        route = route_by_domain.get(domains[0], "/operations/app-health") if len(domains) == 1 else "/operations/app-health"
        return domains, route

    def _handle_import_file_retry(self, body: str | bytes | None, *, owner_user_id: str) -> Response:
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
        self._reload_file_import_runtime_state()
        try:
            self._file_import_service.assert_session_owner(
                session_id=str(session_id),
                imported_by=owner_user_id,
            )
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
        except PermissionError as exc:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "import_file_session_forbidden", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_retry_request", "message": str(exc)},
            )
        self._persist_import_preview_delta(session.id)
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_active_sessions(
        self,
        query: dict[str, list[str]],
        *,
        owner_user_id: str,
    ) -> Response:
        mode = str((query.get("mode") or [""])[0] or "").strip() or None
        if mode not in {None, "bank_transaction", "invoice"}:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_session_mode", "message": "mode must be bank_transaction or invoice."},
            )
        connection = getattr(self._state_store, "_connection", None)
        if connection is not None:
            sessions = ImportLifecycleService(PostgresImportLifecycleRepository(connection)).list_active_sessions(
                imported_by=owner_user_id,
                mode=mode,
            )
        else:
            sessions = [
                {
                    "session_id": session.id,
                    "imported_by": session.imported_by,
                    "file_count": session.file_count,
                    "created_at": self._serialize_value(session.created_at),
                    "updated_at": self._serialize_value(session.created_at),
                    "status": "preview_failed" if session.status == "preview_ready_with_errors" else "awaiting_confirmation",
                    "job_id": None,
                    "job_stage": None,
                    "error": None,
                }
                for session in self._file_import_service.list_active_sessions(
                    imported_by=owner_user_id,
                    mode=mode,
                )
            ]
        return self._json_response(HTTPStatus.OK, {"sessions": sessions})

    def _handle_import_file_discard(self, body: str | bytes | None, *, owner_user_id: str) -> Response:
        payload, error = self._load_json_body(body)
        if error is not None:
            return error
        session_id = str(payload.get("session_id") or "").strip()
        if not session_id:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_file_discard_request", "message": "session_id is required."},
            )
        try:
            connection = getattr(self._state_store, "_connection", None)
            if connection is not None:
                ImportLifecycleService(PostgresImportLifecycleRepository(connection)).discard_session(
                    session_id=session_id,
                    imported_by=owner_user_id,
                )
                try:
                    session = self._file_import_service.discard_session(
                        session_id=session_id,
                        imported_by=owner_user_id,
                    )
                except (KeyError, PermissionError, ValueError):
                    # A different API process may own the in-memory preview. Keep the
                    # PostgreSQL fact authoritative and only pay the snapshot reload
                    # cost when this process cannot synchronize its local session.
                    self._reload_file_import_runtime_state()
                    session = self._file_import_service.get_session(session_id)
            else:
                session = self._file_import_service.discard_session(
                    session_id=session_id,
                    imported_by=owner_user_id,
                )
                self._persist_import_preview_delta(session.id)
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "session_id": session_id},
            )
        except PermissionError as exc:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "import_file_session_forbidden", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.CONFLICT,
                {"error": "import_file_session_not_discardable", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_session(self, session_id: str, *, owner_user_id: str) -> Response:
        self._reload_file_import_runtime_state()
        try:
            session = self._file_import_service.assert_session_owner(
                session_id=session_id,
                imported_by=owner_user_id,
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "session_id": session_id},
            )
        except PermissionError as exc:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "import_file_session_forbidden", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_file_session(session))

    def _handle_import_file_review_rows(
        self,
        session_id: str,
        query: dict[str, list[str]],
        *,
        owner_user_id: str,
    ) -> Response:
        kind = str((query.get("kind") or [""])[0] or "").strip()
        try:
            offset = max(int((query.get("offset") or ["0"])[0] or 0), 0)
            limit = min(max(int((query.get("limit") or ["100"])[0] or 100), 1), 100)
        except ValueError:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_review_rows_request", "message": "offset and limit must be integers."},
            )
        self._reload_file_import_runtime_state()
        try:
            self._file_import_service.assert_session_owner(
                session_id=session_id,
                imported_by=owner_user_id,
            )
            payload = self._file_import_service.review_rows(
                session_id=session_id,
                kind=kind,
                offset=offset,
                limit=limit,
            )
        except KeyError:
            return self._json_response(
                HTTPStatus.NOT_FOUND,
                {"error": "import_file_session_not_found", "session_id": session_id},
            )
        except PermissionError as exc:
            return self._json_response(
                HTTPStatus.FORBIDDEN,
                {"error": "import_file_session_forbidden", "message": str(exc)},
            )
        except ValueError as exc:
            return self._json_response(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_import_review_rows_request", "message": str(exc)},
            )
        return self._json_response(HTTPStatus.OK, self._serialize_value(payload))

    def _reload_file_import_runtime_state(self) -> None:
        if str(getattr(self._state_store, "storage_backend", "") or "").strip() != "postgres":
            return
        load_imports = getattr(self._state_store, "load_imports_snapshot", None)
        load_file_imports = getattr(self._state_store, "load_file_imports_snapshot", None)
        if not callable(load_imports) or not callable(load_file_imports):
            raise RuntimeError("PostgreSQL file import runtime requires explicit import snapshot loaders.")
        import_service = ImportNormalizationService.from_snapshot(
            load_imports(),
            id_registry=self._state_store,
            fact_repository=getattr(self._state_store, "import_fact_repository", None),
        )
        self._import_service = import_service
        self._file_import_service = FileImportService.from_snapshot(
            import_service,
            load_file_imports(),
            file_store=self._state_store,
        )
        self._manual_invoice_entry_service = ManualInvoiceEntryService(
            file_import_service=self._file_import_service,
            document_recognizer=self._invoice_document_recognizer,
        )

    def _parse_import_file_preview_overrides(
        self,
        fields: dict[str, list[str]],
        file_count: int,
    ) -> tuple[list[dict[str, Any]], Response | None]:
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
        normalized: list[dict[str, Any]] = []
        for raw_override in raw_overrides[:file_count]:
            if not isinstance(raw_override, dict):
                normalized.append({})
                continue
            normalized_override: dict[str, Any] = {
                    key: value.strip()
                    for key in ("template_code", "batch_type", "bank_mapping_id", "bank_name", "bank_short_name", "last4")
                    if isinstance((value := raw_override.get(key)), str) and value.strip()
            }
            if isinstance(raw_override.get("field_mapping"), dict):
                normalized_override["field_mapping"] = {
                    str(key): str(value)
                    for key, value in raw_override["field_mapping"].items()
                    if str(key).strip() and str(value).strip()
                }
            normalized.append(normalized_override)
        while len(normalized) < file_count:
            normalized.append({})
        return normalized, None

    def _serialize_preview(self, preview: object) -> dict[str, object]:
        return {
            "batch": self._serialize_value(preview.batch),
            "row_results": self._serialize_value(preview.row_results),
            "normalized_rows": self._serialize_value(preview.normalized_rows),
        }

    def _bank_scope_keys_for_import_preview(self, preview: object) -> list[str]:
        return self._bank_scope_keys_for_import_rows(
            getattr(preview, "normalized_rows", [])
        )

    def _bank_scope_keys_for_import_file_session(
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
        return self._bank_scope_keys_for_import_rows(normalized_rows)

    def _input_invoice_usage_scope_keys_for_import_preview(self, preview: object) -> list[str]:
        return self._invoice_relation_scope_keys_for_import_preview(preview, BatchType.INPUT_INVOICE)

    def _input_invoice_usage_scope_keys_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
    ) -> list[str]:
        return self._invoice_relation_scope_keys_for_import_file_session(
            session,
            selected_file_ids,
            BatchType.INPUT_INVOICE,
        )

    def _output_invoice_collection_scope_keys_for_import_preview(self, preview: object) -> list[str]:
        return self._invoice_relation_scope_keys_for_import_preview(preview, BatchType.OUTPUT_INVOICE)

    def _output_invoice_collection_scope_keys_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
    ) -> list[str]:
        return self._invoice_relation_scope_keys_for_import_file_session(
            session,
            selected_file_ids,
            BatchType.OUTPUT_INVOICE,
        )

    def _invoice_relation_scope_keys_for_import_preview(self, preview: object, batch_type: BatchType) -> list[str]:
        batch = getattr(preview, "batch", None)
        if self._normalized_batch_type(getattr(batch, "batch_type", None)) != batch_type:
            return []
        return self._month_scope_keys_for_import_rows(getattr(preview, "normalized_rows", []))

    def _invoice_relation_scope_keys_for_import_file_session(
        self,
        session: object,
        selected_file_ids: list[str],
        batch_type: BatchType,
    ) -> list[str]:
        selected = {str(file_id) for file_id in list(selected_file_ids or []) if str(file_id)}
        normalized_rows: list[object] = []
        for item in list(getattr(session, "files", []) or []):
            if str(getattr(item, "id", "")) not in selected:
                continue
            if str(getattr(item, "status", "")) != "confirmed":
                continue
            if self._normalized_batch_type(getattr(item, "batch_type", None)) != batch_type:
                continue
            normalized_rows.extend(list(getattr(item, "normalized_rows", []) or []))
        return self._month_scope_keys_for_import_rows(normalized_rows) if normalized_rows else []

    @staticmethod
    def _normalized_batch_type(value: object) -> BatchType | None:
        if isinstance(value, BatchType):
            return value
        try:
            return BatchType(str(value or "").strip())
        except ValueError:
            return None


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
                if MONTH_SCOPE_RE.match(month):
                    months.add(month)
                    break
        return cls._expand_workbench_matching_months(months)

    @classmethod
    def _expand_workbench_matching_months(cls, months: Iterable[str]) -> list[str]:
        expanded: set[str] = set()
        for month in months:
            normalized_month = str(month or "").strip()
            if not MONTH_SCOPE_RE.match(normalized_month):
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
            if MONTH_SCOPE_RE.match(month):
                months.add(month)
        return sorted(months)

    @staticmethod
    def _month_scope_keys_for_import_rows(rows: object) -> list[str]:
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
                if MONTH_SCOPE_RE.match(month):
                    months.add(month)
                    break
        return sorted(months) if months else ["all"]

    @staticmethod
    def _bank_scope_keys_for_import_rows(rows: object) -> list[str]:
        months: set[str] = set()
        for row in list(rows or []):
            if not isinstance(row, dict):
                continue
            if not any(str(row.get(key) or "").strip() for key in ("account_no", "bank_serial_no", "txn_direction")):
                continue
            for field in ("txn_date", "trade_time", "trade_date", "pay_receive_time"):
                raw_value = str(row.get(field) or "").strip()
                if len(raw_value) < 7:
                    continue
                month = raw_value[:7]
                if MONTH_SCOPE_RE.match(month):
                    months.add(month)
                    break
        return sorted(months)

    def _mark_workbench_matching_dirty_scopes(
        self,
        scope_months: list[str],
        *,
        reason: str,
        error: str | None = None,
        debounce_seconds: int | None = None,
    ) -> list[str]:
        normalized_months = [
            str(month).strip()
            for month in list(scope_months or [])
            if MONTH_SCOPE_RE.match(str(month).strip())
        ]
        normalized_months = sorted(dict.fromkeys(normalized_months))
        if not normalized_months:
            return []

        queue = getattr(self, "_workbench_reconciliation_dirty_queue", None)
        mark_dirty_expanded = getattr(queue, "mark_dirty_expanded", None)
        if not callable(mark_dirty_expanded):
            raise RuntimeError("Durable Workbench matching dirty queue is unavailable.")
        arguments: dict[str, object] = {
            "reason": reason,
            "source_versions": self._workbench_matching_source_versions(),
        }
        if debounce_seconds is not None:
            arguments["debounce_seconds"] = debounce_seconds
        return list(mark_dirty_expanded(normalized_months, **arguments))

    def _schedule_workbench_matching_scopes(
        self,
        scope_months: list[str],
        *,
        reason: str,
    ) -> list[str]:
        return self._mark_workbench_matching_dirty_scopes(scope_months, reason=reason)

    def _workbench_matching_source_versions(self) -> dict[str, object]:
        parser_version = self._current_oa_attachment_invoice_parser_version()
        projection_sync_version = self._current_oa_projection_sync_version()
        payload: dict[str, object] = {
            "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
            "workbench_etc_batch_link_version": WORKBENCH_ETC_BATCH_LINK_VERSION,
            "workbench_exception_rules_version": WORKBENCH_EXCEPTION_RULE_VERSION,
            "workbench_exception_projection_version": EXCEPTION_PROJECTION_VERSION,
            "bank_auto_tag_rules_version": self._current_bank_auto_tag_rules_version(),
        }
        if parser_version:
            payload["oa_attachment_invoice_parser_version"] = parser_version
        if projection_sync_version:
            payload["oa_projection_sync_version"] = projection_sync_version
        return payload

    def _bank_batch_workbench_source_versions(self) -> dict[str, object]:
        payload = dict(self._workbench_matching_source_versions())
        relation_source_versions = self._workbench_relation_source_version_provider()
        payload["pair_relation_snapshot_version"] = relation_source_versions.pair_relation_snapshot_version()
        return payload

    def _persist_turnover_relations_best_effort(self, *, operation: str) -> None:
        if self._state_store is None:
            return
        try:
            self._state_store.save_turnover_relations(self._turnover_relation_service.snapshot())
        except Exception as exc:
            self._emit_workbench_persistence_warning(operation=operation, detail=str(exc))

    def _persist_turnover_ledger_extras_best_effort(self, *, operation: str) -> None:
        if self._state_store is None:
            return
        snapshot = self._turnover_ledger_api_routes.extras_snapshot()
        try:
            save_extras = getattr(self._state_store, "save_turnover_ledger_extras", None)
            if callable(save_extras):
                save_extras(snapshot)
                return
            self._emit_workbench_persistence_warning(
                operation=operation,
                detail="state store does not expose save_turnover_ledger_extras.",
            )
        except Exception as exc:
            self._emit_workbench_persistence_warning(operation=operation, detail=str(exc))

    def _persist_state(self) -> None:
        if self._state_store is None:
            return
        persistence_calls = [
            ("save_matching_snapshot", self._matching_service.snapshot()),
            ("save_workbench_overrides", self._workbench_override_service.snapshot()),
            ("save_workbench_exception_cases", self._workbench_exception_case_service.snapshot()),
            ("save_turnover_relations", self._turnover_relation_service.snapshot()),
            ("save_turnover_ledger_extras", self._turnover_ledger_api_routes.extras_snapshot()),
            ("save_pending_invoice_commands", dict(getattr(self, "_pending_invoice_commands", {}) or {})),
        ]
        if str(getattr(self._state_store, "storage_backend", "") or "").strip() != "postgres":
            persistence_calls.insert(
                0,
                ("save_bank_transaction_categories", self._bank_transaction_category_service.snapshot()),
            )
        for method_name, snapshot in persistence_calls:
            persist = getattr(self._state_store, method_name, None)
            if callable(persist):
                persist(snapshot)

    def _persist_import_preview_delta(self, session_id: str) -> None:
        if self._state_store is None:
            return
        persist = getattr(self._state_store, "save_import_delta", None)
        if not callable(persist):
            raise RuntimeError("File import preview requires the import delta persistence port.")
        persist(self._file_import_service.preview_session_persistence_payload(session_id))

    def _persist_confirmed_import_delta(
        self,
        *,
        import_state_payload: dict[str, object],
    ) -> None:
        if self._state_store is not None:
            payload = dict(import_state_payload or {})
            if not payload or set(payload) - {"imports", "file_imports"}:
                raise ValueError("File import persistence requires only imports and file_imports payloads.")
            persist = getattr(self._state_store, "save_import_delta", None)
            if not callable(persist):
                raise RuntimeError("File import confirmation requires the import delta persistence port.")
            persist(payload)

    def _persist_workbench_pair_relations(
        self,
        *,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        service = self._workbench_pair_relation_persist_service()
        service.persist(changed_case_ids=changed_case_ids)
        self._sync_workbench_pair_relation_persist_compat_state(service)

    def _persist_workbench_pair_relations_in_transaction(
        self,
        *,
        transaction: object,
        changed_case_ids: list[str] | None = None,
    ) -> None:
        if transaction is None:
            raise StatePersistenceError("transaction is required for Workbench pair relation persistence.")
        snapshot = (
            self._workbench_pair_relation_service.snapshot_case_ids(changed_case_ids)
            if changed_case_ids is not None
            else self._workbench_pair_relation_service.snapshot()
        )
        PostgresWorkbenchRelationRepository(transaction).save_workbench_pair_relations(
            snapshot,
            changed_case_ids={str(case_id) for case_id in list(changed_case_ids or []) if str(case_id).strip()}
            if changed_case_ids is not None
            else None,
        )

    def _schedule_workbench_pair_relation_persist(
        self,
        *,
        changed_case_ids: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> None:
        service = self._workbench_pair_relation_persist_service()
        service.schedule(
            changed_case_ids=changed_case_ids,
            request_id=request_id,
            action_name=action_name,
        )
        self._sync_workbench_pair_relation_persist_compat_state(service)

    def _workbench_pair_relation_persist_service(self) -> WorkbenchPairRelationPersistService:
        service = getattr(self, "_workbench_pair_relation_persist_service_instance", None)
        if service is None:
            service = WorkbenchPairRelationPersistService(
                pair_relation_service=self._workbench_pair_relation_service,
                state_store=self._state_store,
                emit_action_timing=lambda **kwargs: self._emit_workbench_action_timing(**kwargs),
                duration_ms=self._duration_ms,
                initial_version=getattr(self, "_workbench_pair_relation_persist_version", 0),
                initial_pending_case_ids=getattr(self, "_pending_workbench_pair_relation_case_ids", set()),
            )
            self._workbench_pair_relation_persist_service_instance = service
        return service

    def _sync_workbench_pair_relation_persist_compat_state(
        self,
        service: WorkbenchPairRelationPersistService,
    ) -> None:
        self._workbench_pair_relation_persist_version = service.version
        self._pending_workbench_pair_relation_case_ids = service.pending_case_ids

    @staticmethod
    def _invoice_relation_live_rows(list_rows: Any, *, month: str | None) -> list[dict[str, object]]:
        page_size = 200
        page = 1
        rows: list[dict[str, object]] = []
        total_rows: int | None = None
        while True:
            payload = list_rows(page=page, page_size=page_size, month=month)
            page_rows = [row for row in list((payload or {}).get("rows") or []) if isinstance(row, dict)]
            rows.extend(page_rows)
            pagination = payload.get("pagination") if isinstance(payload, dict) else {}
            if isinstance(pagination, dict):
                raw_total = pagination.get("total")
                try:
                    total_rows = int(raw_total)
                except (TypeError, ValueError):
                    total_rows = len(rows)
            if not page_rows or len(page_rows) < page_size or (total_rows is not None and len(rows) >= total_rows):
                break
            page += 1
        return rows

    def _save_workbench_exception_cases_snapshot(self) -> None:
        if self._state_store is None:
            return
        self._state_store.save_workbench_exception_cases(
            self._workbench_exception_case_service.snapshot(),
        )

    def _serialize_file_session(self, session: object) -> dict[str, object]:
        files = []
        for item in list(getattr(session, "files", []) or []):
            payload = self._serialize_value(item)
            payload.pop("row_results", None)
            payload.pop("normalized_rows", None)
            files.append(payload)
        return {
            "session": {
                "id": session.id,
                "imported_by": session.imported_by,
                "file_count": session.file_count,
                "status": session.status,
                "created_at": self._serialize_value(session.created_at),
                "audit": self._serialize_value(getattr(session, "audit", None)),
            },
            "files": files,
            "duplicate_groups": [],
        }

    def _serialize_sync_run(self, run: object) -> dict[str, object]:
        payload = self._serialize_value(run)
        payload["issue_count"] = run.issue_count
        return payload

    @staticmethod
    def _etc_invoice_summary_row_id(external_batch_id: str) -> str:
        safe_batch_id = re.sub(r"[^A-Za-z0-9_-]+", "-", external_batch_id).strip("-") or "unknown"
        return f"etc-summary-{safe_batch_id}"

    def _current_oa_attachment_invoice_parser_version(self) -> str:
        return attachment_invoice_cache_parser_version()

    def _current_oa_projection_sync_version(self) -> str:
        return OA_PROJECTION_SYNC_VERSION


    def _enqueue_oa_projection_sync_refresh(self, scope_key: str, *, reason: str) -> bool:
        parser_version = self._current_oa_attachment_invoice_parser_version()
        if not parser_version:
            return False
        normalized_scope_key = str(scope_key or "").strip() or "all"
        if normalized_scope_key != "all" and not MONTH_SCOPE_RE.match(normalized_scope_key):
            return False
        queue_repository = getattr(getattr(self, "_runtime_repositories", None), "queue_repository", None)
        enqueue = getattr(queue_repository, "enqueue", None)
        if not callable(enqueue):
            return False
        projection_sync_version = self._current_oa_projection_sync_version()
        if reason == "oa_projection_sync_version_changed":
            dedupe_key = f"oa.sync:{normalized_scope_key}:projection:{projection_sync_version}"
        else:
            dedupe_key = f"oa.sync:{normalized_scope_key}:attachment-parser:{parser_version}"
        enqueue(
            event_type="oa.sync",
            aggregate_type="oa",
            aggregate_id=normalized_scope_key,
            scope_type="oa",
            scope_key=normalized_scope_key,
            dedupe_key=dedupe_key,
            payload={
                "scope_key": normalized_scope_key,
                "triggered_by": "system",
                "reason": reason,
                "oa_attachment_invoice_parser_version": parser_version,
                "oa_projection_sync_version": projection_sync_version,
            },
        )
        return True


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
        return []

    @staticmethod
    def _parse_oa_retention_date(value: object) -> datetime | None:
        return WorkbenchOaRetentionDateParser.parse(value)

    @staticmethod
    def _workbench_oa_attachment_context_row_index() -> WorkbenchOaAttachmentContextRowIndex:
        return WorkbenchOaAttachmentContextRowIndex(
            attachment_parent_oa_id=oa_attachment_parent_oa_id,
            attachment_matches_oa=oa_attachment_matches_oa,
            attachment_row_id_matches_oa=oa_attachment_row_id_matches_oa,
            oa_source_ids=oa_row_source_ids,
        )

    def _apply_pair_relation_to_row(self, row: dict[str, object], relation: dict[str, object]) -> dict[str, object]:
        payload = self._serialize_value(row)
        payload["case_id"] = str(relation.get("case_id", ""))
        relation_field = self._workbench_override_service.relation_field_name(str(payload["type"]))
        relation_mode = str(relation.get("relation_mode", ""))
        relation_payload = (
            self._no_oa_bank_batch_workbench_payload_decorator().relation_with_batch_metadata(relation)
            if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE
            else relation
        )
        linked_relation = self._pair_relation_display_payload(
            relation_mode=relation_mode,
            row_type=str(payload.get("type", "")),
            special_metadata=relation_payload.get("special_metadata") if isinstance(relation_payload.get("special_metadata"), dict) else None,
        )
        payload[relation_field] = self._serialize_value(linked_relation)
        if relation_mode:
            payload["relation_mode"] = relation_mode
        special_metadata = relation.get("special_metadata")
        existing_metadata = payload.get("special_metadata")
        merged_metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
        merged_metadata["active_pair_relation"] = True
        merged_metadata["active_relation_case_id"] = str(relation.get("case_id") or "")
        if isinstance(special_metadata, dict) and special_metadata:
            merged_metadata.update(self._serialize_value(special_metadata))
        payload["special_metadata"] = merged_metadata
        relation_note = str(relation.get("note") or "").strip()
        if relation_note:
            payload["relation_note"] = relation_note
        relation_amount_check = relation.get("amount_check")
        if isinstance(relation_amount_check, dict) and relation_amount_check:
            payload["relation_amount_check"] = self._serialize_value(relation_amount_check)
            external_etc_batch_id = str(
                relation_amount_check.get("external_etc_batch_id")
                or relation_amount_check.get("etc_batch_id")
                or ""
            ).strip()
            if external_etc_batch_id and str(payload.get("type")) == "oa":
                payload["etc_batch_id"] = external_etc_batch_id
                tags = [
                    str(tag).strip()
                    for tag in list(payload.get("tags") or [])
                    if str(tag).strip()
                ]
                if "ETC批量提交" not in tags:
                    tags.append("ETC批量提交")
                payload["tags"] = tags
        self._workbench_override_service._sync_summary_relation(payload, str(linked_relation.get("label", "")))
        if relation_mode == OA_INVOICE_OFFSET_AUTO_MATCH_MODE:
            self._apply_oa_invoice_offset_pair_metadata(payload)
        if relation_mode == "internal_transfer_pair" and str(payload.get("type")) == "bank":
            self._apply_internal_transfer_pair_metadata(payload, relation)
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            payload["relation_mode"] = NO_OA_BANK_BATCH_RELATION_MODE
            self._no_oa_bank_batch_workbench_payload_decorator().apply_pair_metadata(payload, relation_payload)
        self._apply_cash_special_pair_metadata(payload, relation)
        payload["available_actions"] = ["detail"]
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            self._no_oa_bank_batch_workbench_payload_decorator().apply_available_actions(payload)
        self._apply_cash_special_available_actions(payload, relation)
        payload["handled_exception"] = False
        return payload

    def _execute_explicit_maintenance_lifecycle(
        self,
        event: str,
        *,
        months: list[str] | None = None,
        scope_keys: list[str] | None = None,
        include_all: bool = True,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        plan = self._derived_data_lifecycle_service.plan_event(
            event,
            months=months,
            scope_keys=scope_keys,
            include_all=include_all,
            dry_run=False,
            metadata=metadata,
        )
        reason = str((metadata or {}).get("reason") or event).strip()
        for domain_plan in list(plan.get("domains") or []):
            if isinstance(domain_plan, dict):
                domain_plan["reason"] = reason
                if metadata:
                    domain_plan["metadata"] = dict(metadata)
        executors = {
            "workbench_matching_dirty_scopes": self._derived_lifecycle_dirty_scopes_executor,
            "oa_adapter_records_cache": self._derived_lifecycle_oa_adapter_cache_executor,
            "historical_etc_repair_state": self._derived_lifecycle_historical_etc_executor,
        }
        return self._derived_data_lifecycle_service.execute_plan(
            plan,
            executors=executors,
        )

    def _derived_lifecycle_dirty_scopes_executor(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        months = self._months_from_lifecycle_scope_keys(scope_keys)
        if not months and "all" in scope_keys:
            months = self._workbench_query_service.list_available_months()
        if months:
            metadata = self._domain_plan_metadata(domain_plan)
            raw_debounce_seconds = metadata.get("matching_debounce_seconds")
            dirty_months = self._mark_workbench_matching_dirty_scopes(
                months,
                reason=str(domain_plan.get("reason") or "derived_lifecycle"),
                debounce_seconds=(
                    int(raw_debounce_seconds)
                    if raw_debounce_seconds is not None
                    else None
                ),
            )
        else:
            dirty_months = []
        return {
            "deleted_counts": {"workbench_matching_dirty_scopes": 0},
            "invalidated_scopes": dirty_months,
        }

    def _derived_lifecycle_oa_adapter_cache_executor(self, domain_plan: dict[str, object]) -> dict[str, object]:
        adapter = self._workbench_query_service._oa_adapter
        invalidate_records_cache = getattr(adapter, "invalidate_records_cache", None)
        if callable(invalidate_records_cache):
            scope_keys = self._domain_plan_scope_keys(domain_plan)
            months = self._months_from_lifecycle_scope_keys(scope_keys)
            invalidate_records_cache(None if "all" in scope_keys else months)
            invalidated = months or (["all"] if "all" in scope_keys else [])
        else:
            invalidated = []
        return {
            "deleted_counts": {"oa_adapter_records_cache": len(invalidated)},
            "invalidated_scopes": invalidated,
        }

    @staticmethod
    def _derived_lifecycle_historical_etc_executor(domain_plan: dict[str, object]) -> dict[str, object]:
        return {
            "deleted_counts": {"historical_etc_repair_state": 0},
            "invalidated_scopes": Application._domain_plan_scope_keys(domain_plan),
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]

    @staticmethod
    def _domain_plan_metadata(domain_plan: dict[str, object]) -> dict[str, object]:
        metadata = domain_plan.get("metadata")
        return dict(metadata) if isinstance(metadata, dict) else {}

    @staticmethod
    def _months_from_lifecycle_scope_keys(scope_keys: list[str]) -> list[str]:
        return sorted(
            {
                part
                for scope_key in list(scope_keys or [])
                for part in str(scope_key).split(":")
                if MONTH_SCOPE_RE.match(str(part).strip())
            }
        )

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


    def _grouped_rows_by_id(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        rows_by_id: dict[str, dict[str, object]] = {}
        for section in ("paired", "unpaired"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for key in ("oa", "bank", "invoice"):
                for row in list(section_payload.get(key) or []):
                    if isinstance(row, dict) and str(row.get("id") or "").strip():
                        rows_by_id[str(row["id"])] = row
            for group in list(section_payload.get("groups") or []):
                if not isinstance(group, dict):
                    continue
                for key in ("oa_rows", "bank_rows", "invoice_rows"):
                    for row in list(group.get(key) or []):
                        if isinstance(row, dict) and str(row.get("id") or "").strip():
                            rows_by_id[str(row["id"])] = row
        return rows_by_id

    def _resolve_rows_for_amount_check(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        month: str,
    ) -> list[dict[str, object]]:
        if row_types is not None:
            return self._resolve_typed_canonical_rows(
                row_ids,
                row_types,
                month_hint=month,
            )
        return self._resolve_live_rows_direct(row_ids, month_hint=month)

    def _expand_confirm_link_row_ids_for_existing_context(self, row_ids: list[str], *, month: str) -> list[str]:
        expanded_row_ids = self._normalize_row_ids(row_ids)
        seen = set(expanded_row_ids)
        relation_read_port = self._workbench_confirm_link_context_relation_read_port()
        active_relations = relation_read_port.active_relations_for_row_ids(expanded_row_ids)
        selected_oa_source_ids = self._confirm_link_selected_oa_source_ids(
            expanded_row_ids,
            month=month,
        )

        def add(row_id: object) -> None:
            normalized_row_id = str(row_id or "").strip()
            if not normalized_row_id or normalized_row_id in seen:
                return
            seen.add(normalized_row_id)
            expanded_row_ids.append(normalized_row_id)

        for relation in active_relations:
            for relation_row_id in list(relation.get("row_ids") or []):
                if str(relation_row_id or "").strip() in selected_oa_source_ids:
                    continue
                add(relation_row_id)

        has_selected_bank_context = any(
            self._row_type_for_row_id(row_id) == "bank"
            for row_id in expanded_row_ids
        )
        for context_row_id in self._canonical_oa_attachment_context_row_ids(
            selected_row_ids=seen,
            selected_oa_source_ids=selected_oa_source_ids,
            has_selected_bank_context=has_selected_bank_context,
            month_hint=month,
        ):
            add(context_row_id)
        for group in self._canonical_existing_context_groups_for_row_ids(
            expanded_row_ids,
            month_hint=month,
        ):
            for context_row_id in self._confirm_link_context_row_ids_to_preserve(
                group,
                selected_row_ids=seen,
                selected_oa_source_ids=selected_oa_source_ids,
                has_selected_bank_context=has_selected_bank_context,
            ):
                add(context_row_id)
        return expanded_row_ids

    def _canonical_oa_attachment_context_row_ids(
        self,
        *,
        selected_row_ids: set[str],
        selected_oa_source_ids: set[str],
        has_selected_bank_context: bool,
        month_hint: str,
    ) -> list[str]:
        if not has_selected_bank_context:
            return []
        row_index = self._workbench_oa_attachment_context_row_index()
        selection = self._workbench_query_facade().relation_preview_selection(
            month_hint,
            row_ids=sorted(selected_row_ids),
        )
        payload = (
            selection.payload
            if int(selection.status_code) == int(HTTPStatus.OK)
            and isinstance(selection.payload, dict)
            else {}
        )
        rows_by_id = {
            str(row.get("id") or ""): row
            for row in list(payload.get("rows") or [])
            if isinstance(row, dict) and str(row.get("id") or "")
        }
        attachment_ids_by_oa_id = row_index.attachment_row_ids_by_oa_id(rows_by_id)
        selected_attachment_ids = {
            row_id
            for row_id in selected_row_ids
            if row_index.invoice_row_is_attachment_context(rows_by_id.get(row_id, {}))
        }
        result: list[str] = []
        for oa_row_id, attachment_row_ids in sorted(attachment_ids_by_oa_id.items()):
            if oa_row_id not in selected_oa_source_ids and selected_attachment_ids.isdisjoint(attachment_row_ids):
                continue
            result.append(oa_row_id)
            result.extend(attachment_row_ids)
        return self._normalize_row_ids(result) if result else []

    def _confirm_link_selected_oa_source_ids(
        self,
        row_ids: list[str],
        *,
        month: str,
    ) -> set[str]:
        selected_oa_ids = {
            str(row_id).strip()
            for row_id in row_ids
            if str(row_id).strip() and self._row_type_for_row_id(str(row_id).strip()) == "oa"
        }
        if not selected_oa_ids:
            return set()
        source_ids = set(selected_oa_ids)
        for row_id in selected_oa_ids:
            try:
                row = self._resolve_live_rows_direct([row_id], month_hint=month)[0]
            except (IndexError, KeyError):
                continue
            source_ids.update(oa_row_source_ids(row))
        return source_ids

    def _canonical_existing_context_groups_for_row_ids(
        self,
        row_ids: list[str],
        *,
        month_hint: str | None,
    ) -> list[dict[str, object]]:
        selected_row_ids = {str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()}
        if not selected_row_ids:
            return []

        selection = self._workbench_query_facade().relation_preview_selection(
            month_hint,
            row_ids=sorted(selected_row_ids),
        )
        if (
            int(selection.status_code) != int(HTTPStatus.OK)
            or not isinstance(selection.payload, dict)
        ):
            return []
        rows = [
            dict(row)
            for row in list(selection.payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        if not rows:
            return []
        return [
            {
                "oa_rows": [
                    row for row in rows if str(row.get("type") or "") == "oa"
                ],
                "bank_rows": [
                    row for row in rows if str(row.get("type") or "") == "bank"
                ],
                "invoice_rows": [
                    row
                    for row in rows
                    if str(row.get("type") or "") == "invoice"
                ],
            }
        ]

    @staticmethod
    def _workbench_group_preserves_existing_pair_context(group: dict[str, object]) -> bool:
        reason = str(group.get("reason") or "").strip()
        if reason in {"relation_snapshot", "oa_attachment_source_relation"}:
            return True
        group_type = str(group.get("group_type") or "").strip()
        if group_type in {"", "unpaired", "selection", "processed_exception"}:
            return False
        if reason in {"selected_row", "selected_rows"}:
            return False
        return str(group.get("group_id") or "").startswith("case:")

    def _confirm_link_context_row_ids_to_preserve(
        self,
        group: dict[str, object],
        *,
        selected_row_ids: set[str],
        selected_oa_source_ids: set[str] | None = None,
        has_selected_bank_context: bool,
    ) -> list[str]:
        if not self._workbench_group_preserves_existing_pair_context(group):
            return []
        if str(group.get("reason") or "").strip() == "relation_snapshot":
            return [
                str(row.get("id") or "").strip()
                for row_key in ("oa_rows", "bank_rows", "invoice_rows")
                for row in list(group.get(row_key) or [])
                if isinstance(row, dict) and str(row.get("id") or "").strip()
            ]

        group_oa_rows = [row for row in list(group.get("oa_rows") or []) if isinstance(row, dict)]
        group_invoice_rows = [row for row in list(group.get("invoice_rows") or []) if isinstance(row, dict)]
        selected_oa_ids = {
            row_id
            for row_id in selected_row_ids
            if self._row_type_for_row_id(row_id) == "oa"
        }
        if selected_oa_source_ids:
            selected_oa_ids.update(selected_oa_source_ids)
        selected_oa_attachment_invoice_rows = [
            row
            for row in group_invoice_rows
            if str(row.get("id") or "").strip() in selected_row_ids
            and str(row.get("source_kind") or "").strip() == "oa_attachment_invoice"
        ]
        has_selected_bank = any(
            isinstance(row, dict) and str(row.get("id") or "").strip() in selected_row_ids
            for row in list(group.get("bank_rows") or [])
        )
        if not (selected_oa_ids or selected_oa_attachment_invoice_rows) or not (
            has_selected_bank or has_selected_bank_context
        ):
            return []

        preserved_row_ids: list[str] = []

        def preserve(row_id: object) -> None:
            normalized_row_id = str(row_id or "").strip()
            if (
                not normalized_row_id
                or normalized_row_id in selected_row_ids
                or normalized_row_id in preserved_row_ids
            ):
                return
            preserved_row_ids.append(normalized_row_id)

        for row in group_invoice_rows:
            row_id = str(row.get("id") or "").strip()
            if not row_id or row_id in selected_row_ids:
                continue
            if self._invoice_row_belongs_to_selected_oa_attachment(row, selected_oa_ids):
                preserve(row_id)
        selected_oa_attachment_invoice_rows_without_selected_oa = [
            row
            for row in selected_oa_attachment_invoice_rows
            if not self._invoice_row_belongs_to_selected_oa_attachment(row, selected_oa_ids)
        ]
        for row in group_oa_rows:
            oa_row_id = str(row.get("id") or "").strip()
            if not oa_row_id or oa_row_id in selected_row_ids:
                continue
            if any(
                self._invoice_row_belongs_to_selected_oa_attachment(invoice_row, {oa_row_id})
                for invoice_row in selected_oa_attachment_invoice_rows_without_selected_oa
            ):
                preserve(oa_row_id)
        return preserved_row_ids

    @staticmethod
    def _invoice_row_belongs_to_selected_oa_attachment(
        row: dict[str, object],
        selected_oa_ids: set[str],
    ) -> bool:
        source_kind = str(row.get("source_kind") or "").strip()
        if source_kind != "oa_attachment_invoice":
            return False
        row_id = str(row.get("id") or "").strip()
        return any(oa_attachment_matches_oa(row, oa_row_id) or oa_attachment_row_id_matches_oa(row_id, oa_row_id) for oa_row_id in selected_oa_ids)

    @staticmethod
    def _rows_by_type(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        rows_by_type: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type", ""))
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type

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

    @staticmethod
    def _plain_money(value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01')):.2f}"

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
        rows = self._resolve_rows_for_amount_check(affected_row_ids, month=month)
        if after_relations:
            return rows, after_relations, affected_row_ids
        return rows, [], affected_row_ids

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

        relation_mode = (
            str(relation.get("relation_mode"))
            if isinstance(relation, dict)
            else str(group.get("relation_mode") or "")
        )
        has_oa = bool(group.get("oa_rows"))
        has_bank = bool(group.get("bank_rows"))
        has_invoice = bool(group.get("invoice_rows"))
        has_etc_batch_oa = self._group_has_etc_batch_oa(group) or relation_mode == "etc_batch_invoice_link"
        if has_oa and has_invoice and not has_bank:
            add("待找流水")
        elif has_oa and has_bank and not has_invoice:
            if not has_etc_batch_oa:
                add("待找发票")
        elif has_oa and not has_bank and not has_invoice:
            add("待找流水" if has_etc_batch_oa else "待找流水与发票")
        elif has_bank and has_invoice and not has_oa:
            add("待找OA")

        row_type = str(row.get("type", ""))
        if row_type == "oa" and (self._is_etc_batch_oa_row(row) or relation_mode == "etc_batch_invoice_link"):
            add("已关联ETC发票")
        if row_type == "invoice":
            if str(row.get("source_kind", "")) == "etc_invoice" or "ETC" in tags:
                add("ETC")
            elif str(row.get("source_kind", "")) == "etc_supplement_evidence":
                add("ETC补充凭证")
            elif str(row.get("source_kind", "")) == "oa_attachment_invoice":
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
            category_label = str(row.get("category_label") or "").strip()
            category_code = str(row.get("category_code") or "").strip()
            if category_code:
                add(self._bank_transaction_tag_label_current(category_code))
            elif category_label in set(BANK_TRANSACTION_CATEGORY_LABELS.values()):
                add(category_label)

        if relation_mode == "internal_transfer_pair":
            add("内部往来")
        if relation_mode == "salary_personal_auto_match":
            add(self._bank_transaction_tag_label_current("salary"))
        if relation_mode == PERSONAL_ADVANCE_REPAYMENT_MODE:
            add("还清个人暂借款")
        special_metadata = relation.get("special_metadata") if isinstance(relation, dict) else row.get("special_metadata")
        special_type = str(special_metadata.get("special_type") or "") if isinstance(special_metadata, dict) else ""
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            for tag in self._no_oa_bank_batch_workbench_display_policy().row_tags(
                relation=relation if isinstance(relation, dict) else None,
                group=group,
                special_metadata=special_metadata if isinstance(special_metadata, dict) else None,
            ):
                add(tag)
        if special_type == CASH_PASS_THROUGH_MODE:
            add(CASH_TURNOVER_TAG)
            add("过账")
        if special_type == CASH_TICKET_PURCHASE_MODE:
            add(CASH_TURNOVER_TAG)
            add("买票")
        for tag in tags:
            if tag == "工资":
                add(self._bank_transaction_tag_label_current("salary"))
                continue
            if tag in {"ETC", "ETC批量提交", "已关联ETC发票", "ETC补充凭证", "冲", "内部往来", "工资", "非税", CASH_TURNOVER_TAG, "过账", "买票"}:
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
        return row_type_for_workbench_row_id(row_id)

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

    def _resolve_rows_from_workbench_canonical_selection(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        month_hint: str | None = None,
    ) -> dict[str, dict[str, object]]:
        repository = getattr(self, "_workbench_page_selection_repository", None)
        read_rows = getattr(repository, "get_canonical_rows_by_ids", None)
        if not callable(read_rows):
            return {}
        rows = read_rows(row_ids, row_types=row_types)
        return {
            str(row_id): self._serialize_value(row)
            for row_id, row in dict(rows or {}).items()
            if isinstance(row, dict)
        }

    def _workbench_oa_expense_item_target_exists(
        self,
        oa_row_id: str,
        expense_item_id: str,
    ) -> bool:
        normalized_oa_row_id = str(oa_row_id or "").strip()
        normalized_expense_item_id = str(expense_item_id or "").strip()
        if not normalized_oa_row_id or not normalized_expense_item_id:
            return False
        row = self._resolve_rows_from_workbench_canonical_selection(
            [normalized_oa_row_id],
            row_types=["oa"],
        ).get(normalized_oa_row_id)
        if not isinstance(row, dict):
            return False
        raw_items = row.get("expense_items")
        if not isinstance(raw_items, list):
            raw_items = row.get("oa_expense_items")
        return any(
            isinstance(item, dict)
            and str(item.get("id") or "").strip() == normalized_expense_item_id
            for item in list(raw_items or [])
        )

    def _resolve_typed_canonical_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        month_hint: str | None = None,
    ) -> list[dict[str, object]]:
        if len(row_ids) != len(row_types):
            raise ValueError("row_types must align with row_ids.")
        repository = getattr(self, "_workbench_page_selection_repository", None)
        select_rows = getattr(repository, "get_workbench_relation_preview_selection", None)
        if not callable(select_rows):
            raise RuntimeError("Workbench canonical selection repository is unavailable.")
        selection = select_rows(
            scope_key=month_hint or "all",
            row_ids=list(row_ids),
            row_types=list(row_types),
        )
        return [
            self._serialize_value(row)
            for row in list(selection.get("selected_rows") or [])
            if isinstance(row, dict)
        ]

    def _resolve_live_rows_direct(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        month_hint: str | None = None,
    ) -> list[dict[str, object]]:
        normalized_row_ids = [str(row_id) for row_id in row_ids]
        if row_types is not None:
            normalized_row_types = [str(row_type).strip().lower() for row_type in row_types]
            if len(normalized_row_ids) != len(normalized_row_types):
                raise ValueError("row_types must align with row_ids.")
            selected_rows = self._resolve_typed_canonical_rows(
                normalized_row_ids,
                normalized_row_types,
                month_hint=month_hint,
            )
            rows_by_identity: dict[tuple[str, str], dict[str, object]] = {}
            for row in selected_rows:
                identity = (
                    str(row.get("type") or "").strip().lower(),
                    str(row.get("id") or row.get("row_id") or "").strip(),
                )
                if not all(identity) or identity in rows_by_identity:
                    raise RuntimeError("Workbench typed canonical selection is ambiguous.")
                rows_by_identity[identity] = row
            missing = [
                f"{row_type}:{row_id}"
                for row_id, row_type in zip(
                    normalized_row_ids,
                    normalized_row_types,
                    strict=True,
                )
                if (row_type, row_id) not in rows_by_identity
            ]
            if missing:
                raise KeyError(missing[0])
            return [
                rows_by_identity[(row_type, row_id)]
                for row_id, row_type in zip(
                    normalized_row_ids,
                    normalized_row_types,
                    strict=True,
                )
            ]
        resolved_rows = self._resolve_rows_from_workbench_canonical_selection(
            normalized_row_ids,
            row_types=None,
            month_hint=month_hint,
        )
        missing = [row_id for row_id in normalized_row_ids if row_id not in resolved_rows]
        if missing:
            raise KeyError(missing[0])
        return [resolved_rows[row_id] for row_id in normalized_row_ids]



    def _pair_relation_display_payload(
        self,
        *,
        relation_mode: str,
        row_type: str = "",
        special_metadata: dict[str, object] | None = None,
    ) -> dict[str, str]:
        return self._workbench_pair_relation_display_policy().display_payload(
            relation_mode=relation_mode,
            row_type=row_type,
            special_metadata=special_metadata,
        )

    def _workbench_pair_relation_display_policy(self) -> WorkbenchPairRelationDisplayPolicy:
        policy = getattr(self, "_workbench_pair_relation_display_policy_instance", None)
        if policy is None:
            policy = WorkbenchPairRelationDisplayPolicy(
                no_oa_relation_display_payload=self._no_oa_bank_batch_workbench_display_policy().relation_display_payload,
                bank_transaction_tag_label=self._bank_transaction_tag_label_current,
                no_oa_bank_batch_relation_mode=NO_OA_BANK_BATCH_RELATION_MODE,
                bank_flow_rule_batch_relation_mode=BANK_FLOW_RULE_BATCH_RELATION_MODE,
                personal_advance_repayment_mode=PERSONAL_ADVANCE_REPAYMENT_MODE,
                oa_invoice_offset_auto_match_mode=OA_INVOICE_OFFSET_AUTO_MATCH_MODE,
            )
            self._workbench_pair_relation_display_policy_instance = policy
        return policy

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

    @staticmethod
    def _apply_cash_special_pair_metadata(payload: dict[str, object], relation: dict[str, object]) -> None:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict) or not special_metadata:
            return
        special_type = str(special_metadata.get("special_type") or "").strip()
        if special_type not in {CASH_PASS_THROUGH_MODE, CASH_TICKET_PURCHASE_MODE}:
            return
        payload["special_metadata"] = dict(special_metadata)
        tags = [str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()]
        for tag in (CASH_TURNOVER_TAG, "过账" if special_type == CASH_PASS_THROUGH_MODE else "买票"):
            if tag not in tags:
                tags.append(tag)
        payload["tags"] = tags
        cost_policy = str(special_metadata.get("cost_policy") or "").strip()
        if cost_policy == "exclude_all":
            payload["cost_excluded"] = True
        for fields_key in ("summary_fields", "detail_fields"):
            fields = payload.get(fields_key)
            if isinstance(fields, dict):
                fields["现金特殊处理"] = "过账" if special_type == CASH_PASS_THROUGH_MODE else "买票"
                if cost_policy == "exclude_all":
                    fields["成本统计"] = "不计入"
                elif cost_policy == "include_ticket_cost_only":
                    fields["成本统计"] = f"仅计入买票成本 {special_metadata.get('ticket_cost_amount') or '0.00'}"

    @staticmethod
    def _apply_cash_special_available_actions(payload: dict[str, object], relation: dict[str, object]) -> None:
        if str(payload.get("type")) != "bank":
            return
        actions = [str(action).strip() for action in list(payload.get("available_actions") or []) if str(action).strip()]
        if not actions:
            actions = ["detail"]
        row_types = {str(row_type).strip() for row_type in list(relation.get("row_types") or []) if str(row_type).strip()}
        special_metadata = relation.get("special_metadata")
        special_type = str(special_metadata.get("special_type") or "").strip() if isinstance(special_metadata, dict) else ""
        tags = {str(tag).strip() for tag in list(payload.get("tags") or []) if str(tag).strip()}
        if special_type in {CASH_PASS_THROUGH_MODE, CASH_TICKET_PURCHASE_MODE}:
            if "cancel_cash_special" not in actions:
                actions.append("cancel_cash_special")
        elif CASH_TURNOVER_TAG in tags:
            if {"oa", "bank", "invoice"}.issubset(row_types):
                if "confirm_cash_ticket_purchase" not in actions:
                    actions.append("confirm_cash_ticket_purchase")
            elif {"oa", "bank"}.issubset(row_types) and "invoice" not in row_types:
                if "confirm_cash_pass_through" not in actions:
                    actions.append("confirm_cash_pass_through")
        payload["available_actions"] = actions

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
        try:
            fields, files = parse_multipart_body(body, content_type)
        except MultipartBodyError as exc:
            return {}, [], Response(
                status_code=exc.status_code,
                body=json.dumps(
                    {"error": exc.error, "message": exc.message},
                    ensure_ascii=False,
                ),
            )
        return fields, files, None

    @staticmethod
    def _json_response(
        status: HTTPStatus,
        payload: object,
        response_headers: dict[str, str] | None = None,
    ) -> Response:
        normalized_payload = Application._serialize_value(payload)
        response = Response(
            status_code=int(status),
            body="" if status == HTTPStatus.NOT_MODIFIED else json.dumps(normalized_payload, ensure_ascii=False),
        )
        if response_headers:
            response.headers.update(response_headers)
        return response

    @staticmethod
    def _plain_json_response(status: HTTPStatus, payload: dict[str, object]) -> Response:
        normalized_payload = Application._serialize_value(payload)
        return Response(
            status_code=int(status),
            body=json.dumps(normalized_payload, ensure_ascii=False),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )

    @staticmethod
    def _normalize_route_path(route_path: str) -> str:
        normalized = str(route_path or "").strip() or "/"
        for prefix in ("/fin-ops-api",):
            if normalized == prefix:
                return "/"
            if normalized.startswith(f"{prefix}/"):
                return normalized.removeprefix(prefix) or "/"
        return normalized

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

def build_application(*, data_dir: Path | None = None, bootstrap_mode: str | None = None) -> Application:
    return Application(data_dir=data_dir, bootstrap_mode=bootstrap_mode)

def _operation_text(value: object) -> str:
    return str(value or "").strip()
