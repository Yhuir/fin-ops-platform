from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from weakref import finalize

from fin_ops_platform.app.server import Application
from fin_ops_platform.app.server import build_application as _build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.access_control_service import ASSIGNABLE_PAGE_KEYS
from fin_ops_platform.services.import_job_queue import ImportJob, ImportJobIdempotencyConflict
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_role_sync_service import (
    OARoleAssignment,
    OARoleChange,
    OARoleSyncService,
    OAUserSummary,
)
from fin_ops_platform.services.state_store import ApplicationStateStore
from fin_ops_platform.services.state_store_protocol import (
    settings_access_control_from_payload,
    settings_username_comparison_key,
)
from fin_ops_platform.services.workbench_object_identity_arbitration import (
    WorkbenchObjectIdentityArbitrationService,
)
from fin_ops_platform.services.workbench_relation_grouping import WorkbenchRelationGroupingService

DEFAULT_TEST_OA_TOKEN = "test-suite-oa-token"
DEFAULT_TEST_USERNAME = "test_finops_user"


class _TestOARoleSyncExecutor:
    def apply(self, _assignments: list[OARoleAssignment]) -> OARoleChange:
        return OARoleChange((1, 2), frozenset(), frozenset())

    def restore(self, change: OARoleChange) -> None:
        return None

    def resolve_users(self, usernames: list[str]) -> list[OAUserSummary]:
        return [OAUserSummary(username=username, display_name=f"{username} 用户", active=True) for username in usernames]

    def search_users(self, query: str, limit: int) -> list[OAUserSummary]:
        return [OAUserSummary(username=query, display_name=f"{query} 用户", active=True)][:limit]


def build_local_state_application(*args, **kwargs):
    install_test_session = kwargs.pop("install_test_session", True)
    test_username = kwargs.pop("test_username", DEFAULT_TEST_USERNAME)
    data_dir = kwargs.get("data_dir")
    if data_dir is None and args:
        data_dir = args[0]
    if data_dir is None:
        application = _build_application(*args, **kwargs)
        _install_test_oa_directory(application)
        if install_test_session:
            install_default_test_session(application, username=test_username)
        else:
            _install_default_test_access_provider(application)
        return application
    def build_local_store(requested_data_dir: Path | None):
        if requested_data_dir is None:
            return None
        return ApplicationStateStore(requested_data_dir)

    def load_local_bootstrap_state(application: Application) -> dict[str, object]:
        load_local_pickle = getattr(getattr(application, "_state_store", None), "_load_local_pickle", None)
        loaded = load_local_pickle() if callable(load_local_pickle) else {}
        return loaded if isinstance(loaded, dict) else {}

    with (
        patch("fin_ops_platform.app.server.build_state_store", side_effect=build_local_store),
        patch.object(Application, "_runtime_bootstrap_state", load_local_bootstrap_state),
    ):
        application = _build_application(*args, **kwargs)
    _install_test_oa_directory(application)
    if install_test_session:
        install_default_test_session(application, username=test_username)
    else:
        _install_default_test_access_provider(application)
    return application


def _install_test_oa_directory(application: Application) -> None:
    install_durable_import_queue(application)
    application._app_settings_service._oa_role_sync_service = OARoleSyncService(  # noqa: SLF001
        executor=_TestOARoleSyncExecutor()
    )


def _install_default_test_access_provider(application: Application) -> None:
    """Admit the explicit test identity through the canonical ACL contract."""

    service = application._access_control_service  # noqa: SLF001
    canonical_provider = service.access_control_snapshot_provider

    def test_snapshot_provider() -> dict[str, object]:
        snapshot = settings_access_control_from_payload(canonical_provider())
        default_username = DEFAULT_TEST_USERNAME
        default_key = settings_username_comparison_key(default_username)
        if any(
            settings_username_comparison_key(account["username"]) == default_key
            for account in snapshot["page_access_accounts"]
        ):
            return snapshot
        return settings_access_control_from_payload(
            {
                **snapshot,
                "page_access_accounts": [
                    *snapshot["page_access_accounts"],
                    {"username": default_username, "page_keys": sorted(ASSIGNABLE_PAGE_KEYS)},
                ],
            }
        )

    service.access_control_snapshot_provider = test_snapshot_provider


def install_default_test_session(
    application: Application,
    *,
    username: str = DEFAULT_TEST_USERNAME,
) -> None:
    """Inject an explicit fake OA session at the test boundary, never in production code."""

    _install_default_test_access_provider(application)
    original_resolve_identity = application._oa_identity_service.resolve_identity  # noqa: SLF001
    original_resolve_request_session = application._resolve_request_session  # noqa: SLF001

    def resolve_identity(token: str) -> OAUserIdentity:
        if token != DEFAULT_TEST_OA_TOKEN:
            return original_resolve_identity(token)
        is_admin = username.upper() == "YNSYLP005"
        return OAUserIdentity(
            user_id="005" if is_admin else "test-user-id",
            username=username,
            nickname="测试用户",
            display_name="测试用户",
            roles=[],
            permissions=[],
        )

    def resolve_request_session(
        headers: dict[str, str] | None = None,
    ):
        effective_headers = dict(headers or {})
        has_explicit_auth = any(
            str(key).lower() in {"authorization", "cookie"}
            for key in effective_headers
        )
        if not has_explicit_auth:
            effective_headers["Authorization"] = f"Bearer {DEFAULT_TEST_OA_TOKEN}"
        return original_resolve_request_session(effective_headers)

    application._oa_identity_service.resolve_identity = resolve_identity  # noqa: SLF001
    application._resolve_request_session = resolve_request_session  # type: ignore[method-assign]  # noqa: SLF001


def configure_access_control(
    application: Application,
    *,
    usernames: list[str] | None = None,
    page_access: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    service = application._app_settings_service  # noqa: SLF001
    sync_service = service._oa_role_sync_service  # noqa: SLF001
    if sync_service is None or (isinstance(sync_service, OARoleSyncService) and not sync_service.enabled):
        service._oa_role_sync_service = OARoleSyncService(  # noqa: SLF001
            executor=_TestOARoleSyncExecutor()
        )
    current = service.get_access_control_payload()
    accounts_by_username = {
        username: sorted(ASSIGNABLE_PAGE_KEYS)
        for username in list(usernames or [])
    }
    accounts_by_username.update(page_access or {})
    accounts = [
        {"username": username, "page_keys": page_keys}
        for username, page_keys in accounts_by_username.items()
    ]
    return service.update_access_control(
        expected_version=int(current["version"]),
        accounts=accounts,
        actor_id="YNSYLP005",
        actor_name="test protected administrator",
        request_id="test-settings-acl",
    )


def configure_default_test_access(application: Application) -> dict[str, object]:
    return configure_access_control(application, usernames=["test_finops_user"])


def seed_confirmed_import(
    application: Application,
    *,
    batch_type: BatchType | str,
    source_name: str,
    imported_by: str,
    rows: list[dict[str, object]],
):
    """Create test facts through the service port used by the file/session workflow."""

    preview = application._import_service.preview_import(  # noqa: SLF001
        batch_type=batch_type if isinstance(batch_type, BatchType) else BatchType(batch_type),
        source_name=source_name,
        imported_by=imported_by,
        rows=rows,
    )
    persist = getattr(application._state_store, "save_import_delta", None)  # noqa: SLF001
    if callable(persist):
        persist(
            {
                "imports": application._import_service.persistence_snapshot_for_batches(  # noqa: SLF001
                    [preview.id],
                    include_facts=False,
                )
            }
        )
    batch = application._import_service.confirm_import(preview.id)  # noqa: SLF001
    if callable(persist):
        persist(
            {
                "imports": application._import_service.persistence_snapshot_for_batches([preview.id])  # noqa: SLF001
            }
        )
    return preview, batch


def build_grouped_workbench_projection(
    application: Application,
    month: str,
    *,
    include_query_rows: bool = True,
) -> dict[str, object]:
    """Project local test facts through the current pure Workbench grouping boundary.

    Local-state tests do not have the production PostgreSQL active-generation repository.
    They must inspect canonical facts and formal relations directly instead of restoring the
    removed full-page runtime fallback.
    """

    normalized_month = str(month or "").strip() or "all"
    rows_by_id: dict[str, dict[str, object]] = {}
    if include_query_rows:
        source_payload = application._workbench_query_service.get_workbench(normalized_month)  # noqa: SLF001
        for zone in ("paired", "unpaired"):
            zone_payload = source_payload.get(zone)
            if not isinstance(zone_payload, dict):
                continue
            for row_type in ("oa", "bank", "invoice"):
                for raw_row in list(zone_payload.get(row_type) or []):
                    if not isinstance(raw_row, dict):
                        continue
                    row = dict(raw_row)
                    row_id = str(row.get("id") or "").strip()
                    if row_id:
                        rows_by_id[row_id] = row

    fact_ids = [
        str(fact.id)
        for fact in [
            *application._import_service.list_transactions(month=normalized_month),  # noqa: SLF001
            *application._import_service.list_invoices(month=normalized_month),  # noqa: SLF001
        ]
        if str(getattr(fact, "id", "")).strip()
    ]
    if fact_ids:
        local_repository = DirectWorkbenchSelectionRepository(application)
        for row in local_repository.get_canonical_rows_by_ids(fact_ids).values():
            rows_by_id[str(row["id"])] = dict(row)

    active_relations = [
        dict(relation)
        for relation in application._workbench_pair_relation_service.list_active_relations()  # noqa: SLF001
        if normalized_month == "all"
        or str(relation.get("month_scope") or "all") in {"all", normalized_month}
    ]
    missing_relation_row_ids = [
        str(row_id)
        for relation in active_relations
        for row_id in list(relation.get("row_ids") or [])
        if str(row_id).strip() and str(row_id) not in rows_by_id
    ]
    if missing_relation_row_ids:
        local_repository = DirectWorkbenchSelectionRepository(application)
        for row in local_repository.get_canonical_rows_by_ids(
            list(dict.fromkeys(missing_relation_row_ids))
        ).values():
            rows_by_id[str(row["id"])] = dict(row)

    for relation in active_relations:
        for row_id in list(relation.get("row_ids") or []):
            normalized_row_id = str(row_id).strip()
            row = rows_by_id.get(normalized_row_id)
            if row is None:
                continue
            rows_by_id[normalized_row_id] = application._workbench_override_service.apply_to_row(  # noqa: SLF001
                application._apply_pair_relation_to_row(row, relation)  # noqa: SLF001
            )

    WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)
    return WorkbenchRelationGroupingService().group_payload(
        normalized_month,
        rows_by_id=rows_by_id,
        active_relations=active_relations,
    )


class DirectWorkbenchSelectionRepository:
    """Test-only direct selection port backed by the local app's canonical facts."""

    def __init__(self, application: Application) -> None:
        self._application = application

    def _candidates_by_identity(
        self,
        row_ids: list[str],
    ) -> dict[tuple[str, str], dict[str, object]]:
        normalized_ids = list(
            dict.fromkeys(str(row_id).strip() for row_id in row_ids if str(row_id).strip())
        )
        candidates: dict[tuple[str, str], dict[str, object]] = {}
        for row_id in normalized_ids:
            try:
                row = self._application._workbench_query_service.get_row_detail(row_id)  # noqa: SLF001
            except KeyError:
                continue
            row_type = str(row.get("type") or "").strip().lower()
            if row_type:
                candidates[(row_type, row_id)] = dict(row)
        for row_id, row in self._application._live_workbench_service.get_rows_detail(  # noqa: SLF001
            normalized_ids
        ).items():
            row_type = str(row.get("type") or "").strip().lower()
            if row_type:
                candidates[(row_type, str(row_id))] = dict(row)
        return candidates

    def get_canonical_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
    ) -> dict[str, dict[str, object]]:
        if row_types is not None and len(row_ids) != len(row_types):
            raise ValueError("row_types must align with row_ids.")
        candidates = self._candidates_by_identity(row_ids)
        result: dict[str, dict[str, object]] = {}
        for index, raw_row_id in enumerate(row_ids):
            row_id = str(raw_row_id).strip()
            if not row_id:
                continue
            if row_types is not None:
                row_type = str(row_types[index]).strip().lower()
                row = candidates.get((row_type, row_id))
            else:
                matches = [
                    candidate
                    for (candidate_type, candidate_id), candidate in candidates.items()
                    if candidate_id == row_id and candidate_type in {"oa", "bank", "invoice"}
                ]
                if len(matches) > 1:
                    raise ValueError(f"Ambiguous canonical Workbench row: {row_id}.")
                row = matches[0] if matches else None
            if isinstance(row, dict):
                result[row_id] = dict(row)
        return result

    def get_workbench_relation_preview_selection(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        row_types: list[str],
    ) -> dict[str, object]:
        candidates = self._candidates_by_identity(row_ids)
        selected_rows = []
        for row_id, row_type in zip(row_ids, row_types, strict=True):
            identity = (str(row_type).strip().lower(), str(row_id).strip())
            if identity not in candidates:
                raise ValueError(f"Canonical Workbench row is missing: {identity[0]}:{identity[1]}.")
            row = dict(candidates[identity])
            selected_rows.append(row)
        return {
            "scope_key": scope_key,
            "selected_row_ids": list(row_ids),
            "selected_row_types": list(row_types),
            "selected_rows": selected_rows,
            "context_rows": [],
            "rows": selected_rows,
            "memberships": [],
            "context_groups": [],
        }


def install_direct_workbench_selection_repository(application: Application) -> None:
    application._workbench_page_selection_repository = DirectWorkbenchSelectionRepository(  # noqa: SLF001
        application
    )


class _TestImportCompletion:
    def __init__(self, repository, job):
        self.repository, self.job = repository, job

    def lock(self, transaction):
        current = self.repository.get_job(self.job.import_job_id)
        if current.status != "processing" or current.claim_version != self.job.claim_version:
            raise ImportJobIdempotencyConflict("Import claim lost")

    def succeed(self, transaction, result_payload):
        self.lock(transaction)
        self.repository.update(self.job.import_job_id, status="succeeded", result_payload=dict(result_payload))

    def fail(self, transaction, result_payload, *, error):
        self.lock(transaction)
        self.repository.update(self.job.import_job_id, status="failed", result_payload=dict(result_payload), last_error=error)

    def preview(self, transaction, result_payload, *, status="awaiting_confirmation"):
        self.lock(transaction)
        self.repository.update(self.job.import_job_id, status=status, result_payload=dict(result_payload))


class DurableImportQueueHarness:
    """Explicit in-memory test implementation of the single durable job boundary."""

    def __init__(self, application: Application) -> None:
        self.application = application
        self.events = []
        self.jobs: list[ImportJob] = []
        self.fail_next_enqueue = False

    def update(self, job_id, **changes):
        job = self.get_job(job_id)
        updated = replace(job, version=job.version + 1, **changes)
        self.jobs[self.jobs.index(job)] = updated
        return updated

    def create_or_get_job(self, **kwargs) -> ImportJob:
        if self.fail_next_enqueue:
            self.fail_next_enqueue = False
            raise RuntimeError("test durable import queue unavailable")
        key = str(kwargs.get("idempotency_key") or "")
        existing = next((job for job in self.jobs if job.idempotency_key == key), None)
        if existing:
            if existing.payload != dict(kwargs.get("payload") or {}):
                raise ImportJobIdempotencyConflict("Import request changed")
            return existing
        job = ImportJob(
            import_job_id=f"test-import-job-{len(self.jobs) + 1}", tenant_id="default",
            import_type=kwargs["import_type"], import_session_id=kwargs.get("import_session_id"),
            source_file_id=kwargs.get("source_file_id"), idempotency_key=key, request_fingerprint=None,
            status=kwargs.get("status", "pending"), stage=kwargs.get("stage", "commit"),
            priority=kwargs.get("priority", "normal"), attempt_count=0, max_attempts=5,
            last_error=None, payload=dict(kwargs.get("payload") or {}), result_payload={},
            raw_payload={}, created_by=kwargs.get("created_by"), trace_id=None,
        )
        self.jobs.append(job)
        return job

    def get_job(self, job_id):
        return next((job for job in self.jobs if job.import_job_id == job_id), None)

    def get_by_idempotency_key(self, key, *, created_by):
        return next((job for job in self.jobs if job.idempotency_key == key and job.created_by == created_by), None)

    def list_by_session(self, session_id):
        return [job for job in reversed(self.jobs) if job.import_session_id == session_id]

    def list_jobs(self, *, created_by, limit=100, statuses=None):
        return [job for job in reversed(self.jobs) if job.created_by == created_by
                and (statuses is None or job.status in statuses)][:limit]

    def confirm_job(self, job_id, *, expected_version, payload):
        job = self.get_job(job_id)
        if job.version != expected_version or job.status not in {"awaiting_confirmation", "needs_review"}:
            raise ImportJobIdempotencyConflict("Preview changed")
        return self.update(job_id, payload=dict(payload), status="pending", stage="commit", acknowledged_at=None)

    def retry_job(self, job_id, *, expected_version):
        job = self.get_job(job_id)
        if job.version != expected_version or "disposition" in job.result_payload:
            raise ImportJobIdempotencyConflict("Task changed or disposed")
        return self.update(job_id, status="pending", last_error=None, acknowledged_at=None)

    def acknowledge_job(self, job_id, *, created_by):
        job = self.get_job(job_id)
        if job.created_by != created_by:
            raise KeyError(job_id)
        self.update(job_id, acknowledged_at="acknowledged")
        return True

    def mark_preview_needs_review(self, job_id, *, expected_version, transaction=None):
        job = self.get_job(job_id)
        if job.status != "awaiting_confirmation" or job.version != expected_version:
            raise ImportJobIdempotencyConflict("Preview version changed")
        return self.update(job_id, status="needs_review")

    def reprepare_job(self, job_id, *, expected_version, payload=None, transaction=None):
        job = self.get_job(job_id)
        if job.version != expected_version or job.status not in {"awaiting_confirmation", "needs_review", "failed"}:
            raise ImportJobIdempotencyConflict("Preview changed")
        return self.update(job_id, payload=dict(payload or job.payload), status="pending", stage="prepare",
                           result_payload={}, last_error=None, acknowledged_at=None, claim_version=job.claim_version + 1)

    def cancel_job(self, job_id, *, created_by, transaction=None):
        job = self.get_job(job_id)
        if job.created_by != created_by:
            raise KeyError(job_id)
        if job.status == "succeeded":
            raise ImportJobIdempotencyConflict("Already committed")
        return self.update(job_id, status="canceled", claim_version=job.claim_version + 1)

    def process_all(self, *, raise_errors=True):
        processors = self.application._import_processing_service.build_import_job_processors()
        for original in list(self.jobs):
            if original.status != "pending":
                continue
            job = self.update(original.import_job_id, status="processing", claim_version=original.claim_version + 1)
            job = replace(job, completion=_TestImportCompletion(self, job))
            try:
                if job.import_type == "tax_certified_import.confirm":
                    batch = self.application._tax_certified_import_service.confirm_session(job.payload["session_id"])
                    job.completion.succeed(None, {"success": True, "batch": self.application._serialize_value(batch)})
                elif job.import_type == "oa_manual_import.create":
                    result = self.application._oa_manual_import_service.import_row_ids(
                        job.payload["row_ids"], actor_id=job.created_by)
                    result["affected_scope_keys"] = sorted({str(row.get("application_date") or "")[:7] for row in result["rows"]} - {""})
                    if result["failed"] and not result["imported"] and not result["already_imported"]:
                        result["outcome"] = "failed"
                        job.completion.fail(None, result, error="所有选中 OA 均未导入")
                    else:
                        result["outcome"] = "partial_success" if result["failed"] else "success"
                        job.completion.succeed(None, result)
                else:
                    processors[job.import_type](job)
                if self.get_job(job.import_job_id).status == "processing":
                    raise RuntimeError("Processor did not persist its result")
            except Exception as exc:
                self.update(job.import_job_id, status="failed", last_error=str(exc))
                if raise_errors:
                    raise


def install_durable_import_queue(application: Application) -> DurableImportQueueHarness:
    current = getattr(application, "_import_job_repository", None)
    if isinstance(current, DurableImportQueueHarness):
        return current
    if application._state_store is None:
        application._test_import_storage_tmp = TemporaryDirectory(prefix="finops-import-fixture-")
        finalize(application, application._test_import_storage_tmp.cleanup)
        application._state_store = ApplicationStateStore(Path(application._test_import_storage_tmp.name))
        application._file_import_service._file_store = application._state_store
    harness = DurableImportQueueHarness(application)
    application._import_job_repository = harness
    install_etc_import_test_uow(application)
    return harness


def install_etc_import_test_uow(application):
    """Local API fixture only; real transaction guarantees live in PostgreSQL tests."""
    from copy import deepcopy

    service = application._etc_service
    def fixture_identity(prefix):
        counters = {"etc_invoice": service._invoice_counter, "etc_import_batch": service._import_batch_counter,
                    "etc_business_batch": service._business_batch_counter}
        return f"{prefix}_{counters[prefix]:04d}"
    service._new_import_identity = fixture_identity

    class LocalEtcImportTestUow:
        def commit(self, *, validated, owner_user_id, completion):
            session = validated.session
            processor = application._import_processing_service
            task_service = application._etc_reconciliation_task_service
            before = deepcopy(service.snapshot())
            task_before = deepcopy(task_service.snapshot())
            completion.lock(None)
            try:
                batch = next((batch for batch in service.list_business_batches(task_id=session.task_id)
                              if batch.is_active), None)
                if batch is None:
                    batch = service.create_business_batch(task_id=session.task_id, owner_user_id=owner_user_id,
                        idempotency_key=f"etc_business_task_import:{session.task_id}:{session.session_id}")
                batch, result = service.confirm_business_batch_import(
                    batch.business_batch_id, session.session_id, expected_version=batch.version,
                    idempotency_key=f"etc_import_session:{session.session_id}",
                    uploads=list(validated.uploads), manifest=validated.manifest, atomic=True)
                months = application._link_etc_import_result_to_existing_invoices(result)
                import_batch_id = next(batch.id for batch in service.list_import_batches()
                                       if batch.source_session_id == session.session_id)
                task_service.mark_imported(task_id=session.task_id, task_version=session.task_version,
                    confirmed_item_set_hash=session.confirmed_item_set_hash, import_batch_id=import_batch_id,
                    actor=owner_user_id)
                processor._etc_import_preview_service.mark_status(session.session_id, status="succeeded", imported_by=owner_user_id)
                summary = {"created": result.imported, "imported": result.imported, "updated": result.attachments_completed,
                    "attachments_completed": result.attachments_completed, "duplicates": result.duplicates_skipped,
                    "failed": 0, "total": validated.item_total, "batch_members": len(batch.invoice_ids),
                    "affected_months": months, "affected_scope_keys": months}
                completion.succeed(None, summary)
                return summary
            except Exception:
                service._hydrate(before)
                service._persist()
                task_service._hydrate(task_before)
                raise

    application._import_processing_service._etc_import_uow = LocalEtcImportTestUow()
