from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import pickle
import re
import shutil
from pathlib import Path
from threading import Lock
from typing import Any, Iterable

from fin_ops_platform.services.etc_document_parsers import SupplementEvidenceParser, with_task_id
from fin_ops_platform.services.etc_reconciliation_matcher import refresh_reconciliation_matches
from fin_ops_platform.services.etc_reconciliation_models import (
    AuditEvent,
    CreditCardItem,
    EtcReconciliationTask,
    EtcReconciliationTaskStatus,
    ExpectedEtcInvoiceRequirement,
    FileParseResult,
    ParseIssue,
    ParseIssueSeverity,
    ReconciledItem,
    SourceFileKind,
    SubmissionSupplementAttachment,
    SupplementEvidence,
    TicketRootItem,
    UploadedSourceFileMetadata,
    coerce_datetime,
)
from fin_ops_platform.services.runtime_paths import default_data_dir


SCHEMA_VERSION = 1
FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


class EtcReconciliationTaskService:
    def __init__(self, *, data_dir: Path | None = None, state_store: Any | None = None) -> None:
        root = data_dir or getattr(state_store, "data_dir", None) or default_data_dir()
        self._data_dir = Path(root)
        self._state_store = state_store
        self._root = self._data_dir / "etc_reconciliation"
        self._state_path = self._root / "tasks.pkl"
        self._task_counter = 0
        self._file_counter = 0
        self._audit_counter = 0
        self._tasks: dict[str, EtcReconciliationTask] = {}
        self._source_parse_commit_lock = Lock()
        self._root.mkdir(parents=True, exist_ok=True)
        self._hydrate(self._load_snapshot())

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        data_dir: Path | None = None,
        state_store: Any | None = None,
        active_import_session_ids: Iterable[str] | None = None,
        recover_interrupted_imports: bool = True,
    ) -> "EtcReconciliationTaskService":
        service = cls(data_dir=data_dir, state_store=state_store)
        service._hydrate(snapshot or {})
        if recover_interrupted_imports:
            service.recover_interrupted_imports(active_import_session_ids=active_import_session_ids)
        return service

    def create_task(self, *, title: str, created_by: str) -> EtcReconciliationTask:
        self._task_counter += 1
        task_id = f"ETC-RECON-{self._task_counter:06d}"
        now = datetime.now(UTC)
        task = EtcReconciliationTask(
            task_id=task_id,
            status=EtcReconciliationTaskStatus.DRAFT,
            version=1,
            title=title.strip() or task_id,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="task_created",
                actor=created_by,
                after_status=task.status.value,
            )
        )
        self._tasks[task_id] = task
        self._persist()
        return replace(task)

    def get_task(self, task_id: str) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        return _copy_task(task)

    def update_task_title(self, *, task_id: str, title: str, actor: str) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        normalized_title = str(title or "").strip()
        if not normalized_title:
            raise ValueError("task_title_required")
        if str(task.title or "").strip() == normalized_title:
            return _copy_task(task)
        task.title = normalized_title
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="task_title_updated",
                actor=actor,
            )
        )
        self._persist()
        return _copy_task(task)

    def list_tasks(self) -> list[EtcReconciliationTask]:
        return [
            _copy_task(task)
            for task in sorted(self._active_tasks(), key=lambda item: item.created_at, reverse=True)
        ]

    def list_ready_for_import_tasks(self) -> list[EtcReconciliationTask]:
        return [
            _copy_task(task)
            for task in sorted(self._active_tasks(), key=lambda item: item.updated_at, reverse=True)
            if task.status == EtcReconciliationTaskStatus.READY_FOR_IMPORT
        ]

    def _active_tasks(self) -> list[EtcReconciliationTask]:
        return [
            task
            for task in self._tasks.values()
            if task.status != EtcReconciliationTaskStatus.DELETED
        ]

    def _get_active_task_mutable(self, task_id: str) -> EtcReconciliationTask:
        task = self._tasks[task_id]
        if task.status == EtcReconciliationTaskStatus.DELETED:
            raise KeyError(task_id)
        return task

    def delete_task(
        self,
        *,
        task_id: str,
        expected_version: int,
        actor: str,
        import_cleanup_confirmed: bool = False,
    ) -> dict[str, object]:
        task = self._tasks[task_id]
        if task.status == EtcReconciliationTaskStatus.DELETED:
            return {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"}
        self._assert_expected_version(task, expected_version)
        if (
            task.status == EtcReconciliationTaskStatus.IMPORTED
            and str(task.import_batch_id or "").strip()
            and not import_cleanup_confirmed
        ):
            raise ValueError("reconciliation_task_import_cleanup_required")

        self._delete_task_uploads(task)
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.DELETED
        task.period_start = None
        task.period_end = None
        task.statement_period_start = None
        task.statement_period_end = None
        task.approved_delta = None
        task.approved_delta_note = None
        task.card_last4 = None
        task.oa_total_amount = None
        task.etc_invoice_amount = None
        task.supplement_amount = None
        task.etc_invoice_count = 0
        task.supplement_count = 0
        task.vehicle_plates = []
        task.confirmed_by = None
        task.confirmed_at = None
        task.import_batch_id = None
        task.etc_batch_id = None
        task.oa_draft_batch_id = None
        task.oa_draft_status = None
        task.submitted_confirmed_at = None
        task.confirmed_item_set_hash = None
        task.zip_preview_generation += 1
        task.source_files = []
        task.credit_card_items = []
        task.ticket_root_items = []
        task.supplement_evidences = []
        task.reconciled_items = []
        task.expected_etc_invoice_requirements = []
        task.submission_supplement_attachments = []
        task.parse_results = []
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="task_deleted",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return {"deleted": True, "taskId": task_id, "kind": "reconciliation_task"}

    def store_uploaded_source_file(
        self,
        *,
        task_id: str,
        source_kind: SourceFileKind,
        original_name: str,
        content_type: str,
        content: bytes,
        created_by: str,
    ) -> UploadedSourceFileMetadata:
        task = self._get_active_task_mutable(task_id)
        self._assert_mutable_task(task)
        content_bytes = bytes(content or b"")
        sha256 = hashlib.sha256(content_bytes).hexdigest()
        normalized_kind = source_kind if isinstance(source_kind, SourceFileKind) else SourceFileKind(str(source_kind))
        for existing_file in task.source_files:
            if existing_file.source_kind == normalized_kind and existing_file.sha256 == sha256:
                return replace(existing_file)

        previous_file_counter = self._file_counter
        previous_source_files = list(task.source_files)
        previous_audit_events = list(task.audit_events)
        previous_version = task.version
        previous_updated_at = task.updated_at
        self._file_counter += 1
        file_id = f"ETC-RECON-FILE-{self._file_counter:06d}"
        try:
            stored_path = self._store_file(task_id=task_id, file_id=file_id, original_name=original_name, content=content_bytes)
        except Exception:
            self._file_counter = previous_file_counter
            task.source_files = previous_source_files
            task.audit_events = previous_audit_events
            task.version = previous_version
            task.updated_at = previous_updated_at
            raise
        metadata = UploadedSourceFileMetadata(
            file_id=file_id,
            task_id=task_id,
            source_kind=normalized_kind,
            original_name=original_name,
            content_type=content_type,
            size_bytes=len(content_bytes),
            sha256=sha256,
            stored_path=stored_path,
            created_by=created_by,
        )
        task.source_files.append(metadata)
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="source_file_uploaded",
                actor=created_by,
                file_id=file_id,
                file_name=original_name,
                file_sha256=sha256,
            )
        )
        try:
            self._persist()
        except Exception:
            self._file_counter = previous_file_counter
            task.source_files = previous_source_files
            task.audit_events = previous_audit_events
            task.version = previous_version
            task.updated_at = previous_updated_at
            raise
        return replace(metadata)

    def apply_parse_result(
        self,
        *,
        task_id: str,
        parse_result: FileParseResult,
        actor: str,
        require_source_file: bool = False,
    ) -> EtcReconciliationTask:
        with self._source_parse_commit_lock:
            task = self._get_active_task_mutable(task_id)
            self._assert_mutable_task(task)
            result = with_task_id(parse_result, task_id)
            if require_source_file and not any(source.file_id == result.file_id for source in task.source_files):
                raise ValueError("source_file_deleted_during_parse")
            replaced_existing = any(existing.file_id == result.file_id for existing in task.parse_results)
            if replaced_existing and not result.ok:
                raise ValueError("Refusing to replace an existing parse result with blocking parse issues.")
            task.parse_results = [existing for existing in task.parse_results if existing.file_id != result.file_id]
            task.parse_results.append(result)
            self._rebuild_task_from_parse_results(task)
            self._touch(task)
            affected_item_ids = [
                item.item_id
                for item in [*result.credit_card_items, *result.ticket_root_items]
            ] + [evidence.evidence_id for evidence in result.supplement_evidences]
            task.audit_events.append(
                self._new_audit_event(
                    task_id=task_id,
                    event_type="file_parse_result_replaced" if replaced_existing else "file_parsed",
                    actor=actor,
                    file_id=result.file_id,
                    affected_item_ids=affected_item_ids,
                )
            )
            self._persist()
            return _copy_task(task)

    def upload_supplement_evidences_for_card(
        self,
        *,
        task_id: str,
        item_id: str,
        expected_version: int,
        actor: str,
        files: list[dict[str, Any]],
        note: str | None = None,
        evidence_kind_override: str | None = None,
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        self._assert_mutable_task(task)
        if not files:
            raise ValueError("invalid_reconciliation_upload")
        card = self._card_item(task, item_id)
        if self._card_has_linked_etc_evidence(task, card.item_id) or self._card_has_linked_non_etc_submission_supplement(task, card.item_id):
            raise ValueError("credit_card_item_already_covered")
        if card.manual_resolution not in {"unresolved", ""}:
            raise ValueError("credit_card_item_already_resolved")

        previous_task = deepcopy(task)
        previous_file_counter = self._file_counter
        previous_audit_counter = self._audit_counter
        created_source_files: list[UploadedSourceFileMetadata] = []
        try:
            parse_results: list[FileParseResult] = []
            for upload in files:
                original_name = str(upload.get("original_name") or upload.get("file_name") or "supplement-evidence")
                content_type = str(upload.get("content_type") or "application/octet-stream")
                content_bytes = bytes(upload.get("content") or b"")
                sha256 = hashlib.sha256(content_bytes).hexdigest()
                if any(
                    source_file.source_kind == SourceFileKind.SUPPLEMENT_EVIDENCE and source_file.sha256 == sha256
                    for source_file in task.source_files
                ):
                    raise ValueError("duplicate_supplement_evidence_file")

                self._file_counter += 1
                file_id = f"ETC-RECON-FILE-{self._file_counter:06d}"
                stored_path = self._store_file(task_id=task_id, file_id=file_id, original_name=original_name, content=content_bytes)
                source_file = UploadedSourceFileMetadata(
                    file_id=file_id,
                    task_id=task_id,
                    source_kind=SourceFileKind.SUPPLEMENT_EVIDENCE,
                    original_name=original_name,
                    content_type=content_type,
                    size_bytes=len(content_bytes),
                    sha256=sha256,
                    stored_path=stored_path,
                    created_by=actor,
                )
                created_source_files.append(source_file)
                task.source_files.append(source_file)
                task.audit_events.append(
                    self._new_audit_event(
                        task_id=task_id,
                        event_type="source_file_uploaded",
                        actor=actor,
                        file_id=file_id,
                        file_name=original_name,
                        file_sha256=sha256,
                        affected_item_ids=[card.item_id],
                    )
                )
                parse_result = SupplementEvidenceParser().parse_text(
                    file_id=source_file.file_id,
                    text=content_bytes.decode("utf-8", errors="ignore"),
                    source_name=source_file.original_name,
                    evidence_kind_override=evidence_kind_override,
                )
                result = with_task_id(parse_result, task_id)
                if not result.ok:
                    raise ValueError("invalid_supplement_evidence")
                if not result.supplement_evidences:
                    raise ValueError("invalid_supplement_evidence")
                parse_results.append(result)

            task.parse_results.extend(parse_results)
            self._rebuild_task_from_parse_results(task)
            new_evidence_ids = [
                evidence.evidence_id
                for result in parse_results
                for evidence in result.supplement_evidences
            ]
            claim_amount, evidence_amount, amount_delta = self._supplement_claim_amounts(task, card.item_id, new_evidence_ids)
            normalized_note = str(note or "").strip()
            if evidence_amount is None or amount_delta != Decimal("0.00"):
                normalized_note = _required_delta_note(normalized_note)
            amount_delta_note = normalized_note if evidence_amount is None or amount_delta != Decimal("0.00") else None
            updated_card = self._card_item(task, card.item_id)
            self._replace_card(
                task,
                replace(
                    updated_card,
                    manual_resolution="covered_by_supplement",
                    manual_resolution_reason=normalized_note or None,
                    review_note=normalized_note or None,
                ),
            )
            self._upsert_reconciled_item(
                task,
                credit_card_item_id=card.item_id,
                supplement_evidence_ids=new_evidence_ids,
                resolution="covered_by_supplement",
                note=normalized_note or None,
                actor=actor,
                claim_amount=claim_amount,
                evidence_amount=evidence_amount,
                amount_delta=amount_delta,
                amount_delta_note=amount_delta_note,
            )
            self._touch(task)
            task.audit_events.append(
                self._new_audit_event(
                    task_id=task_id,
                    event_type="supplement_evidence_uploaded_and_linked",
                    actor=actor,
                    note=normalized_note or None,
                    before_status=previous_task.status.value,
                    after_status=task.status.value,
                    affected_item_ids=[card.item_id, *new_evidence_ids],
                )
            )
            self._persist()
        except Exception:
            self._tasks[task_id] = previous_task
            self._file_counter = previous_file_counter
            self._audit_counter = previous_audit_counter
            for source_file in created_source_files:
                try:
                    self._delete_uploaded_source_file(source_file)
                except OSError:
                    pass
            raise
        return _copy_task(task)

    def delete_source_file(
        self,
        *,
        task_id: str,
        file_id: str,
        expected_version: int,
        actor: str,
    ) -> EtcReconciliationTask:
        with self._source_parse_commit_lock:
            return self._delete_source_file(
                task_id=task_id,
                file_id=file_id,
                expected_version=expected_version,
                actor=actor,
            )

    def _delete_source_file(
        self,
        *,
        task_id: str,
        file_id: str,
        expected_version: int,
        actor: str,
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        self._assert_mutable_task(task)
        source_file = next((item for item in task.source_files if item.file_id == file_id), None)
        removed_results = [result for result in task.parse_results if result.file_id == file_id]
        if source_file is None and not removed_results:
            raise KeyError("unknown_source_file")

        previous_task = deepcopy(task)
        removed_card_ids = {
            item.item_id
            for result in removed_results
            for item in result.credit_card_items
        }
        removed_ticket_ids = {
            item.item_id
            for result in removed_results
            for item in result.ticket_root_items
        }
        removed_evidence_ids = {
            item.evidence_id
            for result in removed_results
            for item in result.supplement_evidences
        }

        task.source_files = [item for item in task.source_files if item.file_id != file_id]
        task.parse_results = [result for result in task.parse_results if result.file_id != file_id]
        reconciled_items: list[ReconciledItem] = []
        for item in task.reconciled_items:
            if item.credit_card_item_id in removed_card_ids:
                continue
            ticket_root_item_ids = [ticket_id for ticket_id in item.ticket_root_item_ids if ticket_id not in removed_ticket_ids]
            supplement_evidence_ids = [
                evidence_id for evidence_id in item.supplement_evidence_ids if evidence_id not in removed_evidence_ids
            ]
            if not ticket_root_item_ids and not supplement_evidence_ids:
                continue
            reconciled_items.append(
                replace(
                    item,
                    ticket_root_item_ids=ticket_root_item_ids,
                    supplement_evidence_ids=supplement_evidence_ids,
                )
            )
        task.reconciled_items = reconciled_items
        self._rebuild_task_from_parse_results(task)
        self._clear_invalid_manual_resolutions(task)
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="source_file_deleted" if source_file is not None else "orphan_parse_result_deleted",
                actor=actor,
                file_id=file_id,
                file_name=source_file.original_name if source_file is not None else None,
                file_sha256=source_file.sha256 if source_file is not None else None,
            )
        )
        try:
            self._persist()
        except Exception:
            self._tasks[task_id] = previous_task
            raise
        if source_file is not None:
            try:
                self._delete_uploaded_source_file(source_file)
            except OSError:
                pass
        return _copy_task(task)

    def refresh_matches(self, *, task_id: str) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        task.credit_card_items, task.ticket_root_items = refresh_reconciliation_matches(
            credit_card_items=task.credit_card_items,
            ticket_root_items=task.ticket_root_items,
        )
        self._persist()
        return _copy_task(task)

    def patch_item(
        self,
        *,
        task_id: str,
        item_id: str,
        expected_version: int,
        actor: str,
        payload: dict[str, Any],
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        self._assert_mutable_task(task)
        action = str(payload.get("action") or "").strip()
        before_status = task.status.value
        note = _first_text(payload.get("note"), payload.get("reviewNote"), payload.get("reason"))

        if action == "link_ticket":
            ticket_id = _required_text(payload, "ticketItemId")
            card = self._card_item(task, item_id)
            ticket = self._ticket_item(task, ticket_id)
            previous_card_ids = [card_id for card_id in ticket.linked_credit_card_item_ids if card_id != card.item_id]
            for previous_card_id in previous_card_ids:
                previous_card = self._card_item(task, previous_card_id)
                if previous_card.manual_resolution == "included_etc":
                    self._replace_card(
                        task,
                        replace(
                            previous_card,
                            manual_resolution="unresolved",
                            manual_resolution_reason=None,
                            review_note=None,
                        ),
                    )
            self._replace_card(task, replace(card, manual_resolution="included_etc"))
            self._replace_ticket(task, replace(ticket, linked_credit_card_item_ids=[card.item_id]))
            event_type = "item_linked"
            affected = [*previous_card_ids, card.item_id, ticket.item_id]
        elif action == "unlink_ticket":
            ticket_id = _required_text(payload, "ticketItemId")
            card = self._card_item(task, item_id)
            ticket = self._ticket_item(task, ticket_id)
            self._replace_card(task, replace(card, manual_resolution="unresolved"))
            linked = [linked_id for linked_id in ticket.linked_credit_card_item_ids if linked_id != card.item_id]
            self._replace_ticket(task, replace(ticket, linked_credit_card_item_ids=linked))
            event_type = "item_unlinked"
            affected = [card.item_id, ticket.item_id]
        elif action == "remove_ticket":
            ticket = self._ticket_item(task, item_id)
            reason = _required_note(note)
            self._replace_ticket(task, replace(ticket, removed=True, removed_reason=reason))
            event_type = "ticket_item_removed"
            affected = [ticket.item_id]
        elif action == "restore_ticket":
            ticket = self._ticket_item(task, item_id)
            self._replace_ticket(task, replace(ticket, removed=False, removed_reason=None))
            event_type = "ticket_item_restored"
            affected = [ticket.item_id]
        elif action == "exclude_card":
            card = self._card_item(task, item_id)
            resolution = str(payload.get("manualResolution") or payload.get("manual_resolution") or "excluded_non_etc")
            if resolution not in {"excluded_non_etc", "excluded_error"}:
                raise ValueError("invalid_manual_resolution")
            reason = _required_note(note)
            self._replace_card(
                task,
                replace(card, manual_resolution=resolution, manual_resolution_reason=reason, review_note=reason),
            )
            event_type = "item_excluded"
            affected = [card.item_id]
        elif action == "link_supplement":
            evidence_id = _required_text(payload, "supplementEvidenceId")
            card = self._card_item(task, item_id)
            evidence = self._supplement_evidence(task, evidence_id)
            claim_amount, evidence_amount, amount_delta = self._supplement_claim_amounts(task, card.item_id, [evidence.evidence_id])
            if evidence_amount is None or amount_delta != Decimal("0.00"):
                note = _required_delta_note(note)
            self._replace_card(
                task,
                replace(
                    card,
                    manual_resolution="covered_by_supplement",
                    manual_resolution_reason=note,
                    review_note=note,
                ),
            )
            self._upsert_reconciled_item(
                task,
                credit_card_item_id=card.item_id,
                supplement_evidence_ids=[evidence.evidence_id],
                resolution="covered_by_supplement",
                note=note,
                actor=actor,
                claim_amount=claim_amount,
                evidence_amount=evidence_amount,
                amount_delta=amount_delta,
                amount_delta_note=note if evidence_amount is None or amount_delta != Decimal("0.00") else None,
            )
            event_type = "supplement_evidence_linked"
            affected = [card.item_id, evidence.evidence_id]
        elif action == "manual_confirm":
            card = self._card_item(task, item_id)
            reason = _required_note(note)
            self._replace_card(task, replace(card, manual_resolution="manual_confirmed", review_note=reason))
            event_type = "item_manual_confirmed"
            affected = [card.item_id]
        elif action == "set_manual_resolution":
            card = self._card_item(task, item_id)
            resolution = str(payload.get("manualResolution") or payload.get("manual_resolution") or "")
            if resolution not in {"included_etc", "covered_by_supplement", "excluded_non_etc", "excluded_error", "manual_confirmed"}:
                raise ValueError("invalid_manual_resolution")
            if resolution == "included_etc" and not self._card_has_linked_etc_evidence(task, card.item_id):
                raise ValueError("linked_etc_evidence_required")
            if resolution in {"excluded_non_etc", "excluded_error", "manual_confirmed"}:
                note = _required_note(note)
            self._replace_card(task, replace(card, manual_resolution=resolution, manual_resolution_reason=note, review_note=note))
            event_type = "manual_resolution_updated"
            affected = [card.item_id]
        else:
            raise ValueError("invalid_reconciliation_item_action")

        task.credit_card_items, task.ticket_root_items = refresh_reconciliation_matches(
            credit_card_items=task.credit_card_items,
            ticket_root_items=task.ticket_root_items,
        )
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type=event_type,
                actor=actor,
                note=note,
                before_status=before_status,
                after_status=task.status.value,
                affected_item_ids=affected,
            )
        )
        self._persist()
        return _copy_task(task)

    def confirm_task(
        self,
        *,
        task_id: str,
        expected_version: int,
        actor: str,
        approved_delta: Decimal | str | None = None,
        approved_delta_note: str | None = None,
        confirmed_credit_card_item_ids: list[str] | None = None,
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        if task.status == EtcReconciliationTaskStatus.READY_FOR_IMPORT:
            return _copy_task(task)
        if task.status in {
            EtcReconciliationTaskStatus.IMPORTING,
            EtcReconciliationTaskStatus.IMPORTED,
            EtcReconciliationTaskStatus.CLOSED,
        }:
            raise ValueError("invalid_reconciliation_task_status")
        self.refresh_matches(task_id=task_id)
        task = self._get_active_task_mutable(task_id)
        if not task.credit_card_items:
            raise ValueError("credit_card_statement_required")

        selected_card_ids = self._normalize_confirmed_credit_card_item_ids(
            task,
            confirmed_credit_card_item_ids,
        )
        if selected_card_ids is not None:
            self._promote_selected_cards_for_confirmation(
                task,
                selected_card_ids=selected_card_ids,
            )
        items_to_validate = [
            item for item in task.credit_card_items
            if selected_card_ids is None or item.item_id in selected_card_ids
        ]
        final_items = [
            item
            for item in items_to_validate
            if item.manual_resolution in {"included_etc", "covered_by_supplement", "manual_confirmed"}
        ]
        if not final_items:
            raise ValueError("no_confirmable_credit_card_items")
        unresolved = [
            item
            for item in items_to_validate
            if (item.is_etc_candidate or item.manual_resolution != "unresolved")
            and item.manual_resolution == "unresolved"
        ]
        if unresolved:
            raise ValueError("manual_resolution_required")
        if selected_card_ids is not None and len(final_items) != len(selected_card_ids):
            raise ValueError("selected_reconciliation_item_not_pairable")
        for item in items_to_validate:
            if item.manual_resolution == "included_etc" and not self._card_has_linked_etc_evidence(task, item.item_id):
                raise ValueError("linked_etc_evidence_required")
            if item.manual_resolution == "covered_by_supplement":
                if not self._card_has_linked_non_etc_submission_supplement(task, item.item_id):
                    raise ValueError("linked_supplement_evidence_required")
                if self._card_supplement_delta_requires_note(task, item.item_id) and not (item.review_note or "").strip():
                    raise ValueError("supplement_amount_delta_note_required")
            if item.manual_resolution in {"excluded_non_etc", "excluded_error"} and not (item.manual_resolution_reason or "").strip():
                raise ValueError("review_note_required")
            if item.manual_resolution == "manual_confirmed" and not (item.review_note or "").strip():
                raise ValueError("review_note_required")

        requirements = self._build_expected_requirements(task, selected_card_ids=selected_card_ids)
        task.expected_etc_invoice_requirements = requirements
        task.submission_supplement_attachments = self._build_submission_supplement_attachments(
            task,
            selected_card_ids=selected_card_ids,
        )
        final_dates = sorted(item.transaction_date for item in final_items if item.transaction_date)
        task.period_start = final_dates[0] if final_dates else None
        task.period_end = final_dates[-1] if final_dates else None
        task.oa_total_amount = _sum_money(item.settlement_amount for item in final_items)
        task.etc_invoice_amount = _sum_money(requirement.amount for requirement in requirements)
        non_etc_supplement_ids = {
            evidence.evidence_id
            for evidence in task.supplement_evidences
            if not _is_etc_evidence_kind(evidence.evidence_kind) and evidence.include_in_oa_submission
        }
        linked_non_etc_ids = {
            evidence_id
            for reconciled in task.reconciled_items
            for evidence_id in reconciled.supplement_evidence_ids
            if evidence_id in non_etc_supplement_ids
            and (selected_card_ids is None or reconciled.credit_card_item_id in selected_card_ids)
        }
        task.supplement_count = len(linked_non_etc_ids)
        linked_non_etc_card_ids = {
            reconciled.credit_card_item_id
            for reconciled in task.reconciled_items
            if any(evidence_id in linked_non_etc_ids for evidence_id in reconciled.supplement_evidence_ids)
        }
        task.supplement_amount = _sum_money(
            item.settlement_amount
            for item in task.credit_card_items
            if item.item_id in linked_non_etc_card_ids
        )
        task.etc_invoice_count = sum(requirement.invoice_count for requirement in requirements)
        task.approved_delta = _decimal_or_zero(approved_delta)
        task.approved_delta_note = approved_delta_note
        expected_total = (task.etc_invoice_amount or Decimal("0.00")) + (task.supplement_amount or Decimal("0.00"))
        delta = (task.oa_total_amount or Decimal("0.00")) - expected_total
        if delta != Decimal("0.00") and (task.approved_delta != delta or not (task.approved_delta_note or "").strip()):
            raise ValueError("approved_delta_note_required")
        task.confirmed_item_set_hash = self._confirmed_item_set_hash(task, selected_card_ids=selected_card_ids)
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.READY_FOR_IMPORT
        task.confirmed_by = actor
        task.confirmed_at = datetime.now(UTC)
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="task_confirmed",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return _copy_task(task)

    def reopen_task(self, *, task_id: str, expected_version: int, actor: str) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        if task.status in {
            EtcReconciliationTaskStatus.IMPORTING,
            EtcReconciliationTaskStatus.IMPORTED,
            EtcReconciliationTaskStatus.CLOSED,
        }:
            raise ValueError("reconciliation_task_not_reopenable")
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.REVIEWING
        task.confirmed_by = None
        task.confirmed_at = None
        task.confirmed_item_set_hash = None
        task.expected_etc_invoice_requirements = []
        task.zip_preview_generation += 1
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="task_reopened",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return _copy_task(task)

    def begin_import(
        self,
        *,
        task_id: str,
        task_version: int,
        confirmed_item_set_hash: str,
        import_session_id: str,
        actor: str = "system",
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        if (
            task.status == EtcReconciliationTaskStatus.IMPORTING
            and str(task.import_batch_id or "").strip() == str(import_session_id or "").strip()
            and task.version == task_version
            and task.confirmed_item_set_hash == confirmed_item_set_hash
        ):
            return _copy_task(task)
        if task.status != EtcReconciliationTaskStatus.READY_FOR_IMPORT:
            raise ValueError("invalid_reconciliation_task_status")
        if task.version != task_version or task.confirmed_item_set_hash != confirmed_item_set_hash:
            raise ValueError("stale_reconciliation_task_preview")
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.IMPORTING
        task.import_batch_id = import_session_id
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="zip_import_started",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return _copy_task(task)

    def mark_import_failed(
        self,
        *,
        task_id: str,
        task_version: int,
        confirmed_item_set_hash: str,
        actor: str = "system",
        note: str | None = None,
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        if task.status != EtcReconciliationTaskStatus.IMPORTING:
            return _copy_task(task)
        if task.version != task_version or task.confirmed_item_set_hash != confirmed_item_set_hash:
            raise ValueError("stale_reconciliation_task_preview")
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.READY_FOR_IMPORT
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="zip_import_failed",
                actor=actor,
                note=note,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return _copy_task(task)

    def mark_imported(
        self,
        *,
        task_id: str,
        task_version: int,
        confirmed_item_set_hash: str,
        import_batch_id: str | None,
        etc_batch_id: str | None = None,
        actor: str = "system",
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        if task.status == EtcReconciliationTaskStatus.IMPORTED:
            return _copy_task(task)
        if task.status not in {EtcReconciliationTaskStatus.READY_FOR_IMPORT, EtcReconciliationTaskStatus.IMPORTING}:
            raise ValueError("invalid_reconciliation_task_status")
        if task.version != task_version or task.confirmed_item_set_hash != confirmed_item_set_hash:
            raise ValueError("stale_reconciliation_task_preview")
        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.IMPORTED
        task.import_batch_id = import_batch_id
        task.etc_batch_id = etc_batch_id
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="zip_import_confirmed",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
            )
        )
        self._persist()
        return _copy_task(task)

    def remove_imported_invoices(
        self,
        *,
        task_id: str,
        expected_version: int,
        import_batch_id: str,
        actor: str,
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        self._assert_expected_version(task, expected_version)
        normalized_import_batch_id = str(import_batch_id or "").strip()
        if task.status != EtcReconciliationTaskStatus.IMPORTED:
            raise ValueError("invalid_reconciliation_task_status")
        if not normalized_import_batch_id or str(task.import_batch_id or "").strip() != normalized_import_batch_id:
            raise ValueError("reconciliation_task_import_batch_required")
        if (
            str(task.oa_draft_batch_id or "").strip()
            or str(task.etc_batch_id or "").strip()
            or task.submitted_confirmed_at is not None
        ):
            raise ValueError("reconciliation_task_has_submission_link")

        before_status = task.status.value
        task.status = EtcReconciliationTaskStatus.READY_FOR_IMPORT
        task.import_batch_id = None
        task.etc_batch_id = None
        task.zip_preview_generation += 1
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="imported_invoices_removed",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
                affected_item_ids=[normalized_import_batch_id],
            )
        )
        self._persist()
        return _copy_task(task)

    def find_task_for_import_batch_ids(self, import_batch_ids: list[str]) -> EtcReconciliationTask | None:
        normalized_ids = {
            str(import_batch_id).strip()
            for import_batch_id in list(import_batch_ids or [])
            if str(import_batch_id).strip()
        }
        if not normalized_ids:
            return None
        for task in self._active_tasks():
            if str(task.import_batch_id or "").strip() in normalized_ids and task.status in {
                EtcReconciliationTaskStatus.IMPORTED,
                EtcReconciliationTaskStatus.CLOSED,
            }:
                return _copy_task(task)
        return None

    def find_task_for_oa_batch_id(self, batch_id: str) -> EtcReconciliationTask | None:
        normalized_batch_id = str(batch_id or "").strip()
        if not normalized_batch_id:
            return None
        for task in self._active_tasks():
            if str(task.oa_draft_batch_id or "").strip() == normalized_batch_id:
                return _copy_task(task)
        return None

    def find_task_for_submission_batch_id(self, batch_id: str) -> EtcReconciliationTask | None:
        normalized_batch_id = str(batch_id or "").strip()
        if not normalized_batch_id:
            return None
        for task in self._active_tasks():
            if normalized_batch_id in {
                str(task.oa_draft_batch_id or "").strip(),
                str(task.etc_batch_id or "").strip(),
            }:
                return _copy_task(task)
        return None

    def record_oa_draft_created(
        self,
        *,
        task_id: str,
        oa_draft_batch_id: str,
        etc_batch_id: str,
        actor: str = "system",
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        if task.status not in {EtcReconciliationTaskStatus.IMPORTED, EtcReconciliationTaskStatus.CLOSED}:
            raise ValueError("invalid_reconciliation_task_status")
        task.oa_draft_batch_id = oa_draft_batch_id
        task.oa_draft_status = "draft_created"
        task.etc_batch_id = etc_batch_id
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="oa_draft_created",
                actor=actor,
                affected_item_ids=[oa_draft_batch_id],
            )
        )
        self._persist()
        return _copy_task(task)

    def record_oa_submitted_confirmed(
        self,
        *,
        task_id: str,
        oa_draft_batch_id: str,
        actor: str = "system",
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        if task.status == EtcReconciliationTaskStatus.CLOSED and task.submitted_confirmed_at is not None:
            return _copy_task(task)
        if task.status not in {EtcReconciliationTaskStatus.IMPORTED, EtcReconciliationTaskStatus.CLOSED}:
            raise ValueError("invalid_reconciliation_task_status")
        before_status = task.status.value
        task.oa_draft_batch_id = task.oa_draft_batch_id or oa_draft_batch_id
        task.oa_draft_status = "submitted_confirmed"
        task.submitted_confirmed_at = task.submitted_confirmed_at or datetime.now(UTC)
        task.status = EtcReconciliationTaskStatus.CLOSED
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="oa_submitted_confirmed",
                actor=actor,
                before_status=before_status,
                after_status=task.status.value,
                affected_item_ids=[oa_draft_batch_id],
            )
        )
        self._persist()
        return _copy_task(task)

    def record_oa_draft_deleted(
        self,
        *,
        task_id: str,
        oa_draft_batch_id: str,
        etc_batch_id: str | None = None,
        actor: str = "system",
    ) -> EtcReconciliationTask:
        task = self._get_active_task_mutable(task_id)
        normalized_oa_draft_batch_id = str(oa_draft_batch_id or "").strip()
        normalized_etc_batch_id = str(etc_batch_id or "").strip()
        current_oa_draft_batch_id = str(task.oa_draft_batch_id or "").strip()
        current_etc_batch_id = str(task.etc_batch_id or "").strip()
        if current_oa_draft_batch_id:
            if current_oa_draft_batch_id != normalized_oa_draft_batch_id:
                return _copy_task(task)
        elif current_etc_batch_id and current_etc_batch_id not in {normalized_oa_draft_batch_id, normalized_etc_batch_id}:
            return _copy_task(task)
        task.oa_draft_batch_id = None
        task.oa_draft_status = None
        task.etc_batch_id = None
        self._touch(task)
        task.audit_events.append(
            self._new_audit_event(
                task_id=task_id,
                event_type="oa_draft_deleted",
                actor=actor,
                affected_item_ids=[
                    item
                    for item in [normalized_oa_draft_batch_id, normalized_etc_batch_id]
                    if item
                ],
            )
        )
        self._persist()
        return _copy_task(task)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "task_counter": self._task_counter,
            "file_counter": self._file_counter,
            "audit_counter": self._audit_counter,
            "tasks": self._tasks,
        }

    def _hydrate(self, snapshot: dict[str, Any] | None) -> None:
        payload = snapshot if isinstance(snapshot, dict) else {}
        self._task_counter = int(payload.get("task_counter", 0) or 0)
        self._file_counter = int(payload.get("file_counter", 0) or 0)
        self._audit_counter = int(payload.get("audit_counter", 0) or 0)
        raw_tasks = dict(payload.get("tasks") or {})
        self._tasks = {
            str(task_id): _task_from_snapshot(task_payload)
            for task_id, task_payload in raw_tasks.items()
        }

    def recover_interrupted_imports(
        self,
        *,
        active_import_session_ids: Iterable[str] | None = None,
    ) -> bool:
        changed = self._recover_interrupted_imports(active_import_session_ids=active_import_session_ids)
        if changed:
            self._persist()
        return changed

    def _recover_interrupted_imports(
        self,
        *,
        active_import_session_ids: Iterable[str] | None = None,
    ) -> bool:
        active_sessions = {
            str(session_id or "").strip()
            for session_id in (active_import_session_ids or [])
            if str(session_id or "").strip()
        }
        changed = False
        for task in self._active_tasks():
            if task.status != EtcReconciliationTaskStatus.IMPORTING:
                continue
            if str(task.import_batch_id or "").strip() in active_sessions:
                continue
            before_status = task.status.value
            task.status = EtcReconciliationTaskStatus.READY_FOR_IMPORT
            task.import_batch_id = None
            task.zip_preview_generation += 1
            self._touch(task)
            task.audit_events.append(
                self._new_audit_event(
                    task_id=task.task_id,
                    event_type="zip_import_recovered",
                    actor="system",
                    note="Recovered interrupted ETC reconciliation import after service restart.",
                    before_status=before_status,
                    after_status=task.status.value,
                )
            )
            changed = True
        return changed

    def _load_snapshot(self) -> dict[str, Any]:
        if self._state_store is not None and hasattr(self._state_store, "load_etc_reconciliation_state"):
            loaded = self._state_store.load_etc_reconciliation_state()
            return loaded if isinstance(loaded, dict) else {}
        if not self._state_path.exists():
            return {}
        with self._state_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def _persist(self) -> None:
        if self._state_store is not None and hasattr(self._state_store, "save_etc_reconciliation_state"):
            self._state_store.save_etc_reconciliation_state(self.snapshot())
            return
        self._root.mkdir(parents=True, exist_ok=True)
        with self._state_path.open("wb") as handle:
            pickle.dump(self.snapshot(), handle)

    def _store_file(self, *, task_id: str, file_id: str, original_name: str, content: bytes) -> str:
        if self._state_store is not None and hasattr(self._state_store, "store_etc_reconciliation_file"):
            return self._state_store.store_etc_reconciliation_file(
                task_id=task_id,
                file_id=file_id,
                file_name=original_name,
                content=content,
            )
        task_dir = self._root / "tasks" / task_id / "uploads"
        task_dir.mkdir(parents=True, exist_ok=True)
        target_path = task_dir / f"{file_id}_{_sanitize_name(original_name)}"
        target_path.write_bytes(content)
        return str(target_path)

    def _delete_task_uploads(self, task: EtcReconciliationTask) -> None:
        for source_file in list(task.source_files):
            self._delete_uploaded_source_file(source_file)
        task_root = self._root / "tasks" / task.task_id
        if task_root.exists():
            shutil.rmtree(task_root)

    @staticmethod
    def _delete_uploaded_source_file(source_file: UploadedSourceFileMetadata) -> None:
        stored_path = str(source_file.stored_path or "")
        if not stored_path or "://" in stored_path:
            return
        path = Path(stored_path)
        if path.exists():
            path.unlink()

    def _rebuild_task_from_parse_results(self, task: EtcReconciliationTask) -> None:
        previous_cards = {item.item_id: item for item in task.credit_card_items}
        previous_tickets = {item.item_id: item for item in task.ticket_root_items}
        credit_card_items: list[CreditCardItem] = []
        ticket_root_items: list[TicketRootItem] = []
        supplement_evidences: list[SupplementEvidence] = []
        seen_clipboard_ticket_natural_keys: set[tuple[str, str, str, str, str]] = set()
        for result in task.parse_results:
            credit_card_items.extend(_merge_card_item(previous_cards.get(item.item_id), item) for item in result.credit_card_items)
            for item in result.ticket_root_items:
                merged = _merge_ticket_item(previous_tickets.get(item.item_id), item)
                if result.parser_code == "ticket_root_clipboard_text_v1":
                    natural_key = _ticket_natural_key(merged)
                    if natural_key in seen_clipboard_ticket_natural_keys:
                        continue
                    seen_clipboard_ticket_natural_keys.add(natural_key)
                ticket_root_items.append(merged)
            supplement_evidences.extend(result.supplement_evidences)
        task.credit_card_items = credit_card_items
        task.ticket_root_items = ticket_root_items
        task.credit_card_items, task.ticket_root_items = refresh_reconciliation_matches(
            credit_card_items=task.credit_card_items,
            ticket_root_items=task.ticket_root_items,
        )
        task.supplement_evidences = supplement_evidences
        task.vehicle_plates = sorted({item.vehicle_plate for item in ticket_root_items if item.vehicle_plate})
        task.supplement_count = len(supplement_evidences)
        task.supplement_amount = _sum_amounts(evidence.amount for evidence in supplement_evidences)
        task.card_last4 = credit_card_items[0].card_last4 if credit_card_items else None
        if credit_card_items or ticket_root_items:
            task.status = EtcReconciliationTaskStatus.REVIEWING

    def _clear_invalid_manual_resolutions(self, task: EtcReconciliationTask) -> None:
        valid_evidence_ids = {evidence.evidence_id for evidence in task.supplement_evidences}
        task.reconciled_items = [
            replace(
                item,
                supplement_evidence_ids=[evidence_id for evidence_id in item.supplement_evidence_ids if evidence_id in valid_evidence_ids],
            )
            for item in task.reconciled_items
        ]
        task.reconciled_items = [
            item
            for item in task.reconciled_items
            if item.ticket_root_item_ids or item.supplement_evidence_ids
        ]
        changed = False
        updated_cards: list[CreditCardItem] = []
        for card in task.credit_card_items:
            should_reset = False
            if card.manual_resolution == "included_etc":
                should_reset = not self._card_has_linked_etc_evidence(task, card.item_id)
            elif card.manual_resolution == "covered_by_supplement":
                should_reset = not any(
                    item.credit_card_item_id == card.item_id and item.supplement_evidence_ids
                    for item in task.reconciled_items
                )
            if should_reset:
                updated_cards.append(
                    replace(
                        card,
                        manual_resolution="unresolved",
                        manual_resolution_reason=None,
                        review_note=None,
                    )
                )
                changed = True
            else:
                updated_cards.append(card)
        if changed:
            task.credit_card_items = updated_cards
            task.credit_card_items, task.ticket_root_items = refresh_reconciliation_matches(
                credit_card_items=task.credit_card_items,
                ticket_root_items=task.ticket_root_items,
            )
        elif task.status == EtcReconciliationTaskStatus.REVIEWING:
            task.status = EtcReconciliationTaskStatus.DRAFT

    def _touch(self, task: EtcReconciliationTask) -> None:
        task.version += 1
        task.updated_at = datetime.now(UTC)

    def _new_audit_event(
        self,
        *,
        task_id: str,
        event_type: str,
        actor: str,
        note: str | None = None,
        file_id: str | None = None,
        file_name: str | None = None,
        file_sha256: str | None = None,
        before_status: str | None = None,
        after_status: str | None = None,
        affected_item_ids: list[str] | None = None,
    ) -> AuditEvent:
        self._audit_counter += 1
        return AuditEvent(
            event_id=f"ETC-RECON-AUDIT-{self._audit_counter:06d}",
            task_id=task_id,
            event_type=event_type,
            actor=actor,
            note=note,
            file_id=file_id,
            file_name=file_name,
            file_sha256=file_sha256,
            before_status=before_status,
            after_status=after_status,
            affected_item_ids=list(affected_item_ids or []),
        )

    @staticmethod
    def _assert_expected_version(task: EtcReconciliationTask, expected_version: int) -> None:
        if task.version != int(expected_version):
            raise ValueError("task_version_conflict")

    @staticmethod
    def _assert_mutable_task(task: EtcReconciliationTask) -> None:
        if task.status in {
            EtcReconciliationTaskStatus.READY_FOR_IMPORT,
            EtcReconciliationTaskStatus.IMPORTING,
            EtcReconciliationTaskStatus.IMPORTED,
            EtcReconciliationTaskStatus.CLOSED,
        }:
            raise ValueError("reconciliation_task_not_mutable")

    @staticmethod
    def _card_item(task: EtcReconciliationTask, item_id: str) -> CreditCardItem:
        for item in task.credit_card_items:
            if item.item_id == item_id:
                return item
        raise ValueError("unknown_credit_card_item")

    @staticmethod
    def _ticket_item(task: EtcReconciliationTask, item_id: str) -> TicketRootItem:
        for item in task.ticket_root_items:
            if item.item_id == item_id:
                return item
        raise ValueError("unknown_ticket_root_item")

    @staticmethod
    def _supplement_evidence(task: EtcReconciliationTask, evidence_id: str) -> SupplementEvidence:
        for evidence in task.supplement_evidences:
            if evidence.evidence_id == evidence_id:
                return evidence
        raise ValueError("unknown_supplement_evidence")

    @staticmethod
    def _replace_card(task: EtcReconciliationTask, updated: CreditCardItem) -> None:
        task.credit_card_items = [updated if item.item_id == updated.item_id else item for item in task.credit_card_items]

    @staticmethod
    def _replace_ticket(task: EtcReconciliationTask, updated: TicketRootItem) -> None:
        task.ticket_root_items = [updated if item.item_id == updated.item_id else item for item in task.ticket_root_items]

    def _upsert_reconciled_item(
        self,
        task: EtcReconciliationTask,
        *,
        credit_card_item_id: str,
        ticket_root_item_ids: list[str] | None = None,
        supplement_evidence_ids: list[str] | None = None,
        resolution: str,
        note: str | None,
        actor: str,
        claim_amount: Decimal | None = None,
        evidence_amount: Decimal | None = None,
        amount_delta: Decimal | None = None,
        amount_delta_note: str | None = None,
    ) -> None:
        existing = next((item for item in task.reconciled_items if item.credit_card_item_id == credit_card_item_id), None)
        if existing is None:
            self._audit_counter += 0
            task.reconciled_items.append(
                ReconciledItem(
                    item_id=f"RECONCILED-{credit_card_item_id}",
                    task_id=task.task_id,
                    credit_card_item_id=credit_card_item_id,
                    ticket_root_item_ids=list(ticket_root_item_ids or []),
                    supplement_evidence_ids=list(supplement_evidence_ids or []),
                    resolution=resolution,
                    note=note,
                    claim_amount=claim_amount,
                    evidence_amount=evidence_amount,
                    amount_delta=amount_delta,
                    amount_delta_note=amount_delta_note,
                    reviewed_by=actor,
                    reviewed_at=datetime.now(UTC),
                )
            )
            return
        existing.ticket_root_item_ids = list(dict.fromkeys([*existing.ticket_root_item_ids, *(ticket_root_item_ids or [])]))
        existing.supplement_evidence_ids = list(dict.fromkeys([*existing.supplement_evidence_ids, *(supplement_evidence_ids or [])]))
        existing.resolution = resolution
        existing.note = note
        existing.claim_amount = claim_amount
        existing.evidence_amount = evidence_amount
        existing.amount_delta = amount_delta
        existing.amount_delta_note = amount_delta_note
        existing.reviewed_by = actor
        existing.reviewed_at = datetime.now(UTC)

    def _normalize_confirmed_credit_card_item_ids(
        self,
        task: EtcReconciliationTask,
        confirmed_credit_card_item_ids: list[str] | None,
    ) -> set[str] | None:
        if confirmed_credit_card_item_ids is None:
            return None
        selected_ids = [
            str(item_id).strip()
            for item_id in confirmed_credit_card_item_ids
            if str(item_id).strip()
        ]
        if not selected_ids:
            raise ValueError("confirmed_credit_card_items_required")
        known_ids = {item.item_id for item in task.credit_card_items}
        unknown_ids = [item_id for item_id in selected_ids if item_id not in known_ids]
        if unknown_ids:
            raise ValueError("unknown_credit_card_item")
        return set(dict.fromkeys(selected_ids))

    def _promote_selected_cards_for_confirmation(
        self,
        task: EtcReconciliationTask,
        *,
        selected_card_ids: set[str],
    ) -> None:
        for card in list(task.credit_card_items):
            if card.item_id not in selected_card_ids or card.manual_resolution != "unresolved":
                continue
            if self._card_has_linked_etc_evidence(task, card.item_id):
                self._replace_card(task, replace(card, manual_resolution="included_etc"))
                continue
            if self._card_has_linked_non_etc_submission_supplement(task, card.item_id):
                self._replace_card(task, replace(card, manual_resolution="covered_by_supplement"))
                continue
            raise ValueError("selected_reconciliation_item_not_pairable")

    def _card_has_linked_non_etc_submission_supplement(self, task: EtcReconciliationTask, card_id: str) -> bool:
        for reconciled in task.reconciled_items:
            if reconciled.credit_card_item_id != card_id:
                continue
            for evidence_id in reconciled.supplement_evidence_ids:
                evidence = self._supplement_evidence(task, evidence_id)
                if not _is_etc_evidence_kind(evidence.evidence_kind) and evidence.include_in_oa_submission:
                    return True
        return False

    def _supplement_claim_amounts(
        self,
        task: EtcReconciliationTask,
        card_id: str,
        evidence_ids: list[str],
    ) -> tuple[Decimal, Decimal | None, Decimal]:
        card = self._card_item(task, card_id)
        claim_amount = Decimal(card.settlement_amount).quantize(Decimal("0.01"))
        evidences = [self._supplement_evidence(task, evidence_id) for evidence_id in evidence_ids]
        if any(evidence.amount is None for evidence in evidences):
            return claim_amount, None, claim_amount
        evidence_amount = _sum_money(evidence.amount for evidence in evidences)
        return claim_amount, evidence_amount, (claim_amount - evidence_amount).quantize(Decimal("0.01"))

    def _card_supplement_delta_requires_note(self, task: EtcReconciliationTask, card_id: str) -> bool:
        for reconciled in task.reconciled_items:
            if reconciled.credit_card_item_id != card_id or not reconciled.supplement_evidence_ids:
                continue
            _claim_amount, evidence_amount, amount_delta = self._supplement_claim_amounts(
                task,
                card_id,
                list(reconciled.supplement_evidence_ids),
            )
            if evidence_amount is None or amount_delta != Decimal("0.00"):
                return True
        return False

    def _build_expected_requirements(
        self,
        task: EtcReconciliationTask,
        *,
        selected_card_ids: set[str] | None = None,
    ) -> list[ExpectedEtcInvoiceRequirement]:
        requirements: list[ExpectedEtcInvoiceRequirement] = []
        cards = {item.item_id: item for item in task.credit_card_items}
        requirement_index = 0
        for ticket in task.ticket_root_items:
            if ticket.removed:
                continue
            for card_id in ticket.linked_credit_card_item_ids:
                if selected_card_ids is not None and card_id not in selected_card_ids:
                    continue
                card = cards.get(card_id)
                if card is None or card.manual_resolution != "included_etc":
                    continue
                requirement_index += 1
                tx_date = date.fromisoformat(card.transaction_date)
                ticket_date = _parse_iso_date_prefix(ticket.transaction_at) or tx_date
                window_start = min(tx_date - timedelta(days=1), ticket_date)
                window_end = max(tx_date + timedelta(days=1), ticket_date)
                requirements.append(
                    ExpectedEtcInvoiceRequirement(
                        requirement_id=f"{task.task_id}-REQ-{requirement_index:04d}",
                        task_id=task.task_id,
                        credit_card_item_id=card.item_id,
                        ticket_root_item_id=ticket.item_id,
                        vehicle_plate=ticket.vehicle_plate,
                        transaction_at=ticket.transaction_at,
                        date_window_start=window_start.isoformat(),
                        date_window_end=window_end.isoformat(),
                        amount=card.settlement_amount.quantize(Decimal("0.01")),
                        invoice_count=ticket.invoice_count,
                    )
                )
        for reconciled in task.reconciled_items:
            if selected_card_ids is not None and reconciled.credit_card_item_id not in selected_card_ids:
                continue
            card = cards.get(reconciled.credit_card_item_id)
            if card is None or card.manual_resolution != "covered_by_supplement":
                continue
            for evidence_id in reconciled.supplement_evidence_ids:
                evidence = self._supplement_evidence(task, evidence_id)
                if _is_etc_evidence_kind(evidence.evidence_kind) and evidence.include_in_etc_zip_check:
                    requirement_index += 1
                    tx_date = date.fromisoformat(card.transaction_date)
                    requirements.append(
                        ExpectedEtcInvoiceRequirement(
                            requirement_id=f"{task.task_id}-REQ-{requirement_index:04d}",
                            task_id=task.task_id,
                            credit_card_item_id=card.item_id,
                            ticket_root_item_id=None,
                            vehicle_plate="",
                            transaction_at=card.transaction_date,
                            date_window_start=(tx_date - timedelta(days=1)).isoformat(),
                            date_window_end=(tx_date + timedelta(days=1)).isoformat(),
                            amount=card.settlement_amount.quantize(Decimal("0.01")),
                            invoice_count=1,
                            )
                        )
        return requirements

    @staticmethod
    def _card_has_linked_ticket(task: EtcReconciliationTask, card_id: str) -> bool:
        return any(
            not ticket.removed and card_id in ticket.linked_credit_card_item_ids
            for ticket in task.ticket_root_items
        )

    def _card_has_linked_etc_evidence(self, task: EtcReconciliationTask, card_id: str) -> bool:
        if self._card_has_linked_ticket(task, card_id):
            return True
        for reconciled in task.reconciled_items:
            if reconciled.credit_card_item_id != card_id:
                continue
            for evidence_id in reconciled.supplement_evidence_ids:
                evidence = self._supplement_evidence(task, evidence_id)
                if _is_etc_evidence_kind(evidence.evidence_kind) and evidence.include_in_etc_zip_check:
                    return True
        return False

    def _build_submission_supplement_attachments(
        self,
        task: EtcReconciliationTask,
        *,
        selected_card_ids: set[str] | None = None,
    ) -> list[SubmissionSupplementAttachment]:
        files = {file.file_id: file for file in task.source_files}
        attachments: list[SubmissionSupplementAttachment] = []
        linked_ids = {
            evidence_id
            for reconciled in task.reconciled_items
            for evidence_id in reconciled.supplement_evidence_ids
            if selected_card_ids is None or reconciled.credit_card_item_id in selected_card_ids
        }
        for evidence in task.supplement_evidences:
            if evidence.evidence_id not in linked_ids or _is_etc_evidence_kind(evidence.evidence_kind):
                continue
            source_file = files.get(evidence.source_file_id)
            if source_file is None:
                continue
            attachments.append(
                SubmissionSupplementAttachment(
                    attachment_id=f"SUPPLEMENT-ATTACHMENT-{evidence.evidence_id}",
                    task_id=task.task_id,
                    source_file_id=source_file.file_id,
                    evidence_id=evidence.evidence_id,
                    original_name=source_file.original_name,
                    stored_path=source_file.stored_path,
                    sha256=source_file.sha256,
                    amount=evidence.amount,
                    tags=list(evidence.tags),
                )
            )
        return attachments

    @staticmethod
    def _confirmed_item_set_hash(
        task: EtcReconciliationTask,
        *,
        selected_card_ids: set[str] | None = None,
    ) -> str:
        payload = {
            "cards": [
                {
                    "item_id": item.item_id,
                    "amount": f"{item.settlement_amount:.2f}",
                    "manual_resolution": item.manual_resolution,
                    "reason": item.manual_resolution_reason,
                    "note": item.review_note,
                }
                for item in sorted(task.credit_card_items, key=lambda value: value.item_id)
                if item.manual_resolution != "unresolved"
                and (selected_card_ids is None or item.item_id in selected_card_ids)
            ],
            "requirements": [
                {
                    "requirement_id": item.requirement_id,
                    "credit_card_item_id": item.credit_card_item_id,
                    "ticket_root_item_id": item.ticket_root_item_id,
                    "vehicle_plate": item.vehicle_plate,
                    "transaction_at": item.transaction_at,
                    "amount": f"{item.amount:.2f}",
                }
                for item in task.expected_etc_invoice_requirements
            ],
        }
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        return f"sha256:{digest}"


def _copy_task(task: EtcReconciliationTask) -> EtcReconciliationTask:
    return _task_from_snapshot(task)


def _task_from_snapshot(value: Any) -> EtcReconciliationTask:
    if isinstance(value, EtcReconciliationTask):
        raw = {field.name: getattr(value, field.name) for field in fields(EtcReconciliationTask)}
    else:
        raw = dict(value or {})
    raw["status"] = _enum_value(raw.get("status"), EtcReconciliationTaskStatus, EtcReconciliationTaskStatus.DRAFT)
    for key in (
        "approved_delta",
        "oa_total_amount",
        "etc_invoice_amount",
        "supplement_amount",
    ):
        raw[key] = _decimal_or_none(raw.get(key))
    for key in (
        "created_at",
        "updated_at",
        "confirmed_at",
        "submitted_confirmed_at",
    ):
        raw[key] = coerce_datetime(raw.get(key))
    raw["source_files"] = [_source_file_from_snapshot(item) for item in raw.get("source_files") or []]
    raw["credit_card_items"] = [_credit_card_item_from_snapshot(item) for item in raw.get("credit_card_items") or []]
    raw["ticket_root_items"] = [_ticket_root_item_from_snapshot(item) for item in raw.get("ticket_root_items") or []]
    raw["supplement_evidences"] = [_supplement_evidence_from_snapshot(item) for item in raw.get("supplement_evidences") or []]
    raw["reconciled_items"] = [_reconciled_item_from_snapshot(item) for item in raw.get("reconciled_items") or []]
    raw["expected_etc_invoice_requirements"] = [
        _expected_requirement_from_snapshot(item)
        for item in raw.get("expected_etc_invoice_requirements") or []
    ]
    raw["submission_supplement_attachments"] = [
        _submission_attachment_from_snapshot(item)
        for item in raw.get("submission_supplement_attachments") or []
    ]
    raw["parse_results"] = [_parse_result_from_snapshot(item) for item in raw.get("parse_results") or []]
    raw["audit_events"] = [_audit_event_from_snapshot(item) for item in raw.get("audit_events") or []]
    return EtcReconciliationTask(**_known_fields(EtcReconciliationTask, raw))


def _source_file_from_snapshot(value: Any) -> UploadedSourceFileMetadata:
    if isinstance(value, UploadedSourceFileMetadata):
        raw = {field.name: getattr(value, field.name) for field in fields(UploadedSourceFileMetadata)}
    else:
        raw = dict(value or {})
    raw["source_kind"] = _enum_value(raw.get("source_kind"), SourceFileKind, SourceFileKind.CREDIT_CARD_STATEMENT)
    raw["created_at"] = coerce_datetime(raw.get("created_at"))
    return UploadedSourceFileMetadata(**_known_fields(UploadedSourceFileMetadata, raw))


def _credit_card_item_from_snapshot(value: Any) -> CreditCardItem:
    raw = _raw_dataclass(value, CreditCardItem)
    raw["amount"] = Decimal(str(raw.get("amount")))
    raw["settlement_amount"] = Decimal(str(raw.get("settlement_amount")))
    return CreditCardItem(**_known_fields(CreditCardItem, raw))


def _ticket_root_item_from_snapshot(value: Any) -> TicketRootItem:
    raw = _raw_dataclass(value, TicketRootItem)
    raw["amount"] = Decimal(str(raw.get("amount")))
    return TicketRootItem(**_known_fields(TicketRootItem, raw))


def _supplement_evidence_from_snapshot(value: Any) -> SupplementEvidence:
    raw = _raw_dataclass(value, SupplementEvidence)
    raw["amount"] = _decimal_or_none(raw.get("amount"))
    return SupplementEvidence(**_known_fields(SupplementEvidence, raw))


def _expected_requirement_from_snapshot(value: Any) -> ExpectedEtcInvoiceRequirement:
    raw = _raw_dataclass(value, ExpectedEtcInvoiceRequirement)
    raw["amount"] = Decimal(str(raw.get("amount")))
    raw.setdefault("ticket_root_item_id", None)
    raw.setdefault("date_window_start", "")
    raw.setdefault("date_window_end", "")
    return ExpectedEtcInvoiceRequirement(**_known_fields(ExpectedEtcInvoiceRequirement, raw))


def _submission_attachment_from_snapshot(value: Any) -> SubmissionSupplementAttachment:
    raw = _raw_dataclass(value, SubmissionSupplementAttachment)
    raw["amount"] = _decimal_or_none(raw.get("amount"))
    return SubmissionSupplementAttachment(**_known_fields(SubmissionSupplementAttachment, raw))


def _reconciled_item_from_snapshot(value: Any) -> ReconciledItem:
    raw = _raw_dataclass(value, ReconciledItem)
    raw["reviewed_at"] = coerce_datetime(raw.get("reviewed_at"))
    return ReconciledItem(**_known_fields(ReconciledItem, raw))


def _parse_result_from_snapshot(value: Any) -> FileParseResult:
    if isinstance(value, FileParseResult):
        raw = {field.name: getattr(value, field.name) for field in fields(FileParseResult)}
    else:
        raw = dict(value or {})
    raw["credit_card_items"] = [_credit_card_item_from_snapshot(item) for item in raw.get("credit_card_items") or []]
    raw["ticket_root_items"] = [_ticket_root_item_from_snapshot(item) for item in raw.get("ticket_root_items") or []]
    raw["supplement_evidences"] = [_supplement_evidence_from_snapshot(item) for item in raw.get("supplement_evidences") or []]
    raw["issues"] = [_parse_issue_from_snapshot(item) for item in raw.get("issues") or []]
    return FileParseResult(**_known_fields(FileParseResult, raw))


def _parse_issue_from_snapshot(value: Any) -> ParseIssue:
    raw = _raw_dataclass(value, ParseIssue)
    raw["severity"] = _enum_value(raw.get("severity"), type(ParseIssueSeverity.BLOCKING), ParseIssueSeverity.BLOCKING)
    return ParseIssue(**_known_fields(ParseIssue, raw))


def _audit_event_from_snapshot(value: Any) -> AuditEvent:
    raw = _raw_dataclass(value, AuditEvent)
    raw["created_at"] = coerce_datetime(raw.get("created_at"))
    return AuditEvent(**_known_fields(AuditEvent, raw))


def _simple_dataclass_from_snapshot(cls: type[Any], value: Any) -> Any:
    return cls(**_known_fields(cls, _raw_dataclass(value, cls)))


def _raw_dataclass(value: Any, cls: type[Any]) -> dict[str, Any]:
    if isinstance(value, cls):
        return {field.name: getattr(value, field.name) for field in fields(cls)}
    return dict(value or {})


def _known_fields(cls: type[Any], raw: dict[str, Any]) -> dict[str, Any]:
    return {field.name: raw[field.name] for field in fields(cls) if field.name in raw}


def _enum_value(value: Any, enum_cls: type[Any], default: Any) -> Any:
    if isinstance(value, enum_cls):
        return value
    if value in (None, ""):
        return default
    return enum_cls(str(value))


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _sum_amounts(values: Any) -> Decimal | None:
    total = Decimal("0.00")
    found = False
    for value in values:
        if value is None:
            continue
        total += value
        found = True
    return total if found else None


def _sum_money(values: Any) -> Decimal:
    total = Decimal("0.00")
    for value in values:
        if value is None:
            continue
        total += Decimal(value).quantize(Decimal("0.01"))
    return total.quantize(Decimal("0.01"))


def _ticket_natural_key(item: TicketRootItem) -> tuple[str, str, str, str, str]:
    return (
        str(item.vehicle_plate or "").strip(),
        str(item.transaction_at or "").strip(),
        f"{item.amount.quantize(Decimal('0.01')):.2f}",
        str(item.entry_station or "").strip(),
        str(item.exit_station or "").strip(),
    )


def _decimal_or_zero(value: Decimal | str | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    return Decimal(str(value)).quantize(Decimal("0.01"))


def _parse_iso_date_prefix(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _first_text(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _is_etc_evidence_kind(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"etc", "etc_invoice", "etc-invoice"}


def _required_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key}_required")
    return value.strip()


def _required_note(note: str | None) -> str:
    if not (note or "").strip():
        raise ValueError("review_note_required")
    return str(note).strip()


def _required_delta_note(note: str | None) -> str:
    if not (note or "").strip():
        raise ValueError("supplement_amount_delta_note_required")
    return str(note).strip()


def _merge_card_item(previous: CreditCardItem | None, current: CreditCardItem) -> CreditCardItem:
    if previous is None:
        return current
    return replace(
        current,
        recommendation_status=previous.recommendation_status,
        manual_resolution=previous.manual_resolution,
        manual_resolution_reason=previous.manual_resolution_reason,
        review_note=previous.review_note,
    )


def _merge_ticket_item(previous: TicketRootItem | None, current: TicketRootItem) -> TicketRootItem:
    if previous is None:
        return current
    return replace(
        current,
        recommendation_status=previous.recommendation_status,
        linked_credit_card_item_ids=list(previous.linked_credit_card_item_ids),
        removed=previous.removed,
        removed_reason=previous.removed_reason,
    )


def _sanitize_name(file_name: str) -> str:
    cleaned = FILENAME_SAFE_RE.sub("_", str(file_name or "")).strip("._")
    return cleaned or "uploaded_file"
