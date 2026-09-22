from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fin_ops_platform.services.etc_existing_invoice_link_service import EtcExistingInvoiceLinkService
from fin_ops_platform.services.etc_service import EtcService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_repositories.common import serialize_value
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.etc_import_sessions import PostgresEtcImportSessionRepository
from fin_ops_platform.services.postgres_repositories.ops_tax_etc import PostgresOpsTaxEtcRepository
from fin_ops_platform.services.postgres_state_store import PostgresStateStore


class _PreparedEtcState:
    """Explicit domain staging adapter: no database writes and no object I/O."""

    def __init__(self, snapshot: dict[str, Any], prepared: dict[tuple[str, str], str]) -> None:
        self.snapshot = deepcopy(snapshot)
        self.prepared = prepared

    def load_etc_state(self) -> dict[str, Any]:
        return deepcopy(self.snapshot)

    def save_etc_state(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = deepcopy(snapshot)

    def store_etc_invoice_file(self, *, invoice_number: str, file_name: str, content: bytes) -> str:
        return self.prepared[(invoice_number, file_name)]

    @staticmethod
    def etc_invoice_file_exists(path: str) -> bool:
        return bool(path)


class EtcImportUow:
    """Prepare objects first; atomically publish only the current import's facts."""

    def __init__(self, *, connection: Any, archive_store: Any, data_dir: Path) -> None:
        self._connection = connection
        self._archive_store = archive_store
        self._data_dir = data_dir

    def commit(self, *, validated: Any, owner_user_id: str, completion: Any) -> dict[str, Any]:
        session, manifest = validated.session, validated.manifest
        if manifest is None:
            raise ValueError("ETC commit requires its persisted prepared manifest.")
        numbers = sorted({entry.parsed_invoice.invoice_number for file in manifest.files
                          for entry in file.entries if entry.parsed_invoice is not None})
        repository = PostgresOpsTaxEtcRepository(self._connection)
        initial = repository.load_etc_import_scope(task_id=session.task_id, invoice_numbers=numbers)
        prepared: dict[tuple[str, str], str] = {}
        existing = {value["invoice_number"]: value for value in initial["invoices"].values()}
        try:
            for file in manifest.files:
                pdfs = [entry for entry in file.entries if EtcService._is_pdf_entry(entry.path)]
                for xml in file.entries:
                    parsed = xml.parsed_invoice
                    if parsed is None:
                        continue
                    current = existing.get(parsed.invoice_number, {})
                    pdf = EtcService._match_pdf_entry(parsed.invoice_number, xml.path, pdfs)
                    for name, entry, field in (("invoice.xml", xml, "xml_file_path"), ("invoice.pdf", pdf, "pdf_file_path")):
                        key = (parsed.invoice_number, name)
                        if entry is None or current.get(field) or key in prepared:
                            continue
                        prepared[key] = self._archive_store.store_etc_invoice_file(
                            invoice_number=parsed.invoice_number, file_name=name, content=entry.content)

            with self._connection.transaction() as transaction:
                completion.lock(transaction)
                repository = PostgresOpsTaxEtcRepository(transaction)
                task = repository.lock_etc_import_task(task_id=session.task_id, task_version=session.task_version,
                                                      confirmed_item_set_hash=session.confirmed_item_set_hash)
                # Serialize absent-key races as well as existing rows, only for this invoice set.
                repository.lock_etc_import_invoice_keys(numbers)
                before = repository.load_etc_import_scope(task_id=session.task_id, invoice_numbers=numbers, lock=True)
                stage = _PreparedEtcState(before, prepared)
                service = EtcService(data_dir=self._data_dir, state_store=stage)
                batches = service.list_business_batches(task_id=session.task_id)
                batch = next((item for item in batches if item.is_active), None)
                if batch is None:
                    batch = service.create_business_batch(task_id=session.task_id, title=task.get("title"),
                        owner_user_id=owner_user_id, idempotency_key=f"etc_business_task_import:{session.task_id}:{session.session_id}")
                batch, result = service.confirm_business_batch_import(
                    batch.business_batch_id, session.session_id, expected_version=batch.version,
                    idempotency_key=f"etc_import_session:{session.session_id}",
                    uploads=list(validated.uploads), manifest=manifest, atomic=True,
                )
                after = serialize_value(stage.snapshot)
                delta = {key: {identity: value for identity, value in after.get(key, {}).items()
                               if value != before.get(key, {}).get(identity)}
                         for key in ("invoices", "import_batches", "business_batches")}
                # Business-batch summaries use its entire current member set, still task scoped.
                delta["invoice_summary"] = after["invoices"]
                repository.save_etc_state(delta)
                state = PostgresStateStore(data_dir=self._data_dir, connection=transaction)
                import_service = ImportNormalizationService.from_snapshot({}, fact_repository=state.import_fact_repository)
                linker = EtcExistingInvoiceLinkService(import_service=import_service,
                    persist_linked_invoices=PostgresCoreRepository(transaction).save_invoice_etc_metadata)
                months = linker.link_etc_invoices_to_existing_invoices(service.list_invoices_by_ids(batch.invoice_ids))
                now = datetime.now(UTC).isoformat()
                task["status"], task["version"], task["updated_at"] = "imported", session.task_version + 1, now
                task["import_batch_id"] = next(identity for identity, value in after["import_batches"].items()
                                                if value.get("source_session_id") == session.session_id)
                task.setdefault("audit_events", []).append({"event_id": uuid4().hex, "task_id": session.task_id,
                    "event_type": "zip_import_confirmed", "actor": completion.job.payload.get("actor_account") or owner_user_id, "created_at": now,
                    "before_status": "ready_for_import", "after_status": "imported"})
                repository.save_etc_reconciliation_task(task, expected_version=session.task_version, expected_status="ready_for_import")
                PostgresEtcImportSessionRepository(transaction).update_status(
                    session.session_id, status="succeeded", imported_by=owner_user_id, last_error=None)
                summary = {"created": result.imported, "imported": result.imported,
                    "updated": result.attachments_completed, "attachments_completed": result.attachments_completed,
                    "duplicates": result.duplicates_skipped, "failed": 0, "total": len(numbers),
                    "batch_members": len(batch.invoice_ids), "business_batch_id": batch.business_batch_id,
                    "affected_months": months, "affected_scope_keys": months}
                completion.succeed(transaction, summary)
                return summary
        finally:
            self._archive_store.delete_unreferenced_etc_import_files(list(prepared.values()))
