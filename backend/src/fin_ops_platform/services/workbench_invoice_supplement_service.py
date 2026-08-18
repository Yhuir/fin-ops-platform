from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.domain.enums import ImportDecision


class WorkbenchInvoiceSupplementError(ValueError):
    def __init__(self, error: str, message: str) -> None:
        super().__init__(message)
        self.error = error
        self.message = message


@dataclass(frozen=True, slots=True)
class ManualInvoiceSupplementCommand:
    session_id: str
    file_ids: tuple[str, ...]
    oa_row_id: str
    expense_item_id: str
    case_id: str
    actor_id: str
    request_id: str


class WorkbenchInvoiceSupplementService:
    """Atomic boundary for manual invoice import plus Workbench relation replacement."""

    def __init__(
        self,
        *,
        connection: Any,
        file_import_service: Any,
        relation_repository_factory: Callable[[Any], Any],
        relation_command_service_factory: Callable[[Any], Any],
        target_exists: Callable[[str, str], bool],
        next_case_id: Callable[[], str],
        persist_import_delta: Callable[[Any, dict[str, Any], dict[str, Any]], None],
        restore_import_runtime: Callable[[], None],
    ) -> None:
        self._connection = connection
        self._file_import_service = file_import_service
        self._relation_repository_factory = relation_repository_factory
        self._relation_command_service_factory = relation_command_service_factory
        self._target_exists = target_exists
        self._next_case_id = next_case_id
        self._persist_import_delta = persist_import_delta
        self._restore_import_runtime = restore_import_runtime

    def attach_manual_invoices(self, command: ManualInvoiceSupplementCommand) -> dict[str, Any]:
        session_id = str(command.session_id or "").strip()
        file_ids = list(dict.fromkeys(str(value).strip() for value in command.file_ids if str(value).strip()))
        oa_row_id = str(command.oa_row_id or "").strip()
        expense_item_id = str(command.expense_item_id or "").strip()
        actor_id = str(command.actor_id or "").strip()
        if not session_id or not file_ids or not oa_row_id or not expense_item_id or not actor_id:
            raise WorkbenchInvoiceSupplementError(
                "invalid_manual_invoice_supplement",
                "会话、发票、OA子付款项和操作人不能为空。",
            )
        if not self._target_exists(oa_row_id, expense_item_id):
            raise WorkbenchInvoiceSupplementError(
                "manual_invoice_supplement_target_not_found",
                "目标 OA 子付款项不存在或已变化，请刷新后重试。",
            )

        session = self._file_import_service.assert_session_owner(
            session_id=session_id,
            imported_by=actor_id,
        )
        selected = set(file_ids)
        if selected != {item.id for item in session.files}:
            raise WorkbenchInvoiceSupplementError(
                "manual_invoice_batch_must_be_complete",
                "必须一次提交本批次全部发票。",
            )
        if any(item.template_code != "manual_invoice_entry" for item in session.files):
            raise WorkbenchInvoiceSupplementError(
                "invalid_manual_invoice_supplement_session",
                "仅允许关联手工录入发票批次。",
            )

        runtime_relation_commands = self._relation_command_service_factory(None)
        pair_snapshot = runtime_relation_commands.runtime_snapshot()
        try:
            with self._connection.transaction() as transaction:
                confirmed = self._file_import_service.confirm_session(
                    session_id=session_id,
                    selected_file_ids=file_ids,
                    atomic_batch=True,
                )
                row_results = [
                    row_result
                    for item in confirmed.files
                    if item.id in selected
                    for row_result in item.row_results
                ]
                if len(row_results) != len(file_ids) or any(
                    row_result.decision != ImportDecision.CREATED
                    or str(row_result.linked_object_type or "") != "invoice"
                    or not str(row_result.linked_object_id or "").strip()
                    for row_result in row_results
                ):
                    raise WorkbenchInvoiceSupplementError(
                        "manual_invoice_batch_changed",
                        "发票池状态已变化，整批未录入，请重新校验。",
                    )
                invoice_ids = [str(row_result.linked_object_id).strip() for row_result in row_results]
                source_links = [{
                    "source_type": "oa_expense_item_invoice",
                    "source_workbench_row_id": oa_row_id,
                    "derived_from_oa_id": oa_row_id,
                    "source_expense_item_id": expense_item_id,
                    "entry_method": "manual",
                }]
                self._file_import_service.attach_source_links_to_invoices(
                    invoice_ids,
                    source_links=source_links,
                    oa_form_id=oa_row_id,
                )
                import_payload = self._file_import_service.confirmed_session_persistence_payload(
                    session_id=session_id,
                    selected_file_ids=file_ids,
                )
                self._persist_import_delta(
                    transaction,
                    dict(import_payload.get("imports") or {}),
                    dict(import_payload.get("file_imports") or {}),
                )

                relation_repository = self._relation_repository_factory(transaction)
                existing = None
                requested_case_id = str(command.case_id or "").strip()
                if requested_case_id:
                    existing = relation_repository.load_active_workbench_pair_relation_by_case_id(
                        requested_case_id
                    )
                if existing is not None and oa_row_id not in list(existing.get("row_ids") or []):
                    raise WorkbenchInvoiceSupplementError(
                        "manual_invoice_relation_oa_mismatch",
                        "目标关联关系不包含该 OA 付款项。",
                    )

                case_id = str(existing.get("case_id") or "").strip() if existing else self._next_case_id()
                existing_row_ids = list(existing.get("row_ids") or []) if existing else [oa_row_id]
                existing_row_types = list(existing.get("row_types") or []) if existing else ["oa"]
                members = list(zip(existing_row_ids, existing_row_types, strict=True))
                members.extend((invoice_id, "invoice") for invoice_id in invoice_ids)
                unique_members = list(dict.fromkeys(members))
                metadata = deepcopy(existing.get("special_metadata") or {}) if existing else {}
                metadata["manual_oa_invoice_entry"] = {
                    "oa_row_id": oa_row_id,
                    "expense_item_id": expense_item_id,
                    "invoice_row_ids": invoice_ids,
                }
                relation_result = self._relation_command_service_factory(
                    relation_repository
                ).confirm_relation(
                    case_id=case_id,
                    row_ids=[row_id for row_id, _row_type in unique_members],
                    row_types=[row_type for _row_id, row_type in unique_members],
                    relation_mode=str(existing.get("relation_mode") or "manual_confirmed") if existing else "manual_confirmed",
                    actor_id=actor_id,
                    month_scope=str(existing.get("month_scope") or "all") if existing else "all",
                    note=str(existing.get("note") or "") if existing else "OA子付款项手工补录发票",
                    amount_check=deepcopy(existing.get("amount_check") or {}) if existing else {},
                    special_metadata=metadata,
                    evidence={"source": "manual_oa_invoice_entry", "expense_item_id": expense_item_id},
                    idempotency_key=f"manual-oa-invoice:{command.request_id or session_id}",
                    before_relations=[existing] if existing else [],
                    replace_existing=existing is not None,
                    history_operation_type="attach_manual_oa_invoices",
                    request_id=command.request_id,
                )
            return {
                "status": "confirmed",
                "case_id": case_id,
                "invoice_row_ids": invoice_ids,
                "file_ids": file_ids,
                "relation": relation_result.get("relation"),
            }
        except Exception:
            self._restore_import_runtime()
            runtime_relation_commands.restore_runtime_snapshot(pair_snapshot)
            raise
