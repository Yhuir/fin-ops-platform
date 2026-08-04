from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from time import perf_counter
from typing import Any, Callable, Iterable

from fin_ops_platform.services.search_query import normalize_money_search_query
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


BATCH_ACCOUNTING_SOURCE = "batch_accounting"
BATCH_ACCOUNTING_COUNTERPARTY_NAME = "批量账务集中处理"


class BatchAccountingError(ValueError):
    def __init__(self, code: str, message: str | None = None, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.payload = payload or {}


@dataclass(frozen=True)
class _SubmissionContext:
    rows_by_id: dict[str, dict[str, Any]]
    oa_rows: list[dict[str, Any]]
    invoice_ids_by_oa_id: dict[str, list[str]]
    tag_selection_version: int
    selected_tag_codes: frozenset[str]


class BatchAccountingService:
    def __init__(
        self,
        *,
        query_repository: Any | None = None,
        case_id_provider: Callable[[str], str] | None = None,
        relation_command_service: Any | None = None,
        app_settings_service: Any | None = None,
    ) -> None:
        self._query_repository = query_repository
        self._case_id_provider = case_id_provider or self._default_case_id_for_bank_row
        self._relation_command_service = relation_command_service
        self._app_settings_service = app_settings_service

    def build_payload(
        self,
        *,
        year: str | None = None,
        bank_year: str | None = None,
        bucket: str,
        page: int | str | None = None,
        page_size: int | str | None = None,
        bank_page: int | str | None = None,
        bank_page_size: int | str | None = None,
        oa_page: int | str | None = None,
        oa_page_size: int | str | None = None,
        oa_search: str | None = None,
        timing_observer: Callable[[str, float], None] | None = None,
    ) -> dict[str, Any]:
        resolved_bank_year = self._validate_year(bank_year or year or "")
        if bucket not in {"unsubmitted", "submitted"}:
            raise BatchAccountingError("invalid_batch_accounting_bucket", "bucket must be unsubmitted or submitted.")
        bank_pagination = self._pagination_from_values(
            page=bank_page if bank_page is not None else page,
            page_size=bank_page_size if bank_page_size is not None else page_size,
        )
        oa_pagination = self._pagination_from_values(
            page=oa_page if oa_page is not None else page,
            page_size=oa_page_size if oa_page_size is not None else page_size,
        )
        normalized_search = normalize_money_search_query(oa_search)
        if len(normalized_search) > 200:
            raise BatchAccountingError("invalid_batch_accounting_search", "oa_search must be <= 200 characters.")

        repository = self._require_query_repository()
        load_started_at = perf_counter()
        snapshot = repository.list_snapshot(
            bank_year=resolved_bank_year,
            bucket=bucket,
            bank_page=bank_pagination["page"],
            bank_page_size=bank_pagination["page_size"],
            oa_page=oa_pagination["page"],
            oa_page_size=oa_pagination["page_size"],
            oa_search=normalized_search,
        )
        self._record_read_timing(timing_observer, "canonical_snapshot", load_started_at)
        if not isinstance(snapshot, dict):
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务 canonical 查询不可用，请稍后重试。",
            )

        assembly_started_at = perf_counter()
        if bucket == "submitted":
            bank_rows, relations_by_bank_row_id = self._submitted_payload(snapshot)
            oa_rows: list[dict[str, Any]] = []
        else:
            invoice_ids_by_oa_id = self._invoice_ids_by_oa_id(list(snapshot.get("invoice_rows") or []))
            bank_rows = [
                self._bank_row_payload(row)
                for row in list(snapshot.get("bank_rows") or [])
                if isinstance(row, dict)
            ]
            oa_rows = [
                self._oa_row_payload(
                    row,
                    invoice_ids_by_oa_id.get(str(row.get("id") or ""), []),
                )
                for row in list(snapshot.get("oa_rows") or [])
                if isinstance(row, dict)
            ]
            relations_by_bank_row_id = {}
        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), dict) else {}
        pagination = snapshot.get("pagination") if isinstance(snapshot.get("pagination"), dict) else {}
        payload = {
            "summary": {
                "unsubmitted_count": self._optional_int(summary.get("unsubmitted_count")) or 0,
                "submitted_count": self._optional_int(summary.get("submitted_count")) or 0,
                "bank_year": resolved_bank_year,
            },
            "bank_rows": bank_rows,
            "oa_rows": oa_rows,
            "relations_by_bank_row_id": relations_by_bank_row_id,
            "pagination": pagination,
            "tag_selection_version": self._optional_int(snapshot.get("tag_selection_version")) or 1,
        }
        self._record_read_timing(timing_observer, "payload_assembly", assembly_started_at)
        return payload

    def submit(
        self,
        *,
        year: str | None = None,
        bank_year: str | None = None,
        bank_row_id: str,
        oa_row_ids: list[str],
        actor: str,
        note: str | None = None,
        expected_version: int | None = None,
        expected_tag_selection_version: int | None = None,
    ) -> dict[str, Any]:
        resolved_bank_year = self._validate_year(bank_year or year or "")
        normalized_bank_row_id = self._required_id(bank_row_id, "bank_row_id")
        normalized_oa_row_ids = self._normalize_ids(oa_row_ids)
        context = self._load_submission_context(
            bank_year=resolved_bank_year,
            bank_row_id=normalized_bank_row_id,
            oa_row_ids=normalized_oa_row_ids,
        )
        bank_row = context.rows_by_id.get(normalized_bank_row_id)
        if not isinstance(bank_row, dict) or not self._is_batch_bank_row(bank_row, resolved_bank_year):
            raise BatchAccountingError("invalid_batch_accounting_bank_row", "银行流水不符合批量账务提交条件。")
        if expected_version is not None:
            row_version = self._optional_int(bank_row.get("version"))
            if row_version is not None and row_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "银行流水版本已变化，请刷新后重试。")
        if (
            expected_tag_selection_version is not None
            and context.tag_selection_version != expected_tag_selection_version
        ):
            raise BatchAccountingError(
                "batch_accounting_tag_selection_version_conflict",
                "批量账务标签规则已变化，请刷新后重试。",
            )
        tag_code = self._clean_text(bank_row.get("tag_code"))
        if not tag_code or tag_code not in context.selected_tag_codes:
            raise BatchAccountingError(
                "batch_accounting_bank_tag_not_selected",
                "该流水的当前标签已不在批量账务规则中，请刷新后重试。",
            )

        eligible_oa_by_id = {
            str(row.get("id") or ""): row
            for row in context.oa_rows
            if self._is_eligible_oa_row(row)
        }
        selected_oa_rows: list[dict[str, Any]] = []
        for oa_row_id in normalized_oa_row_ids:
            oa_row = eligible_oa_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict):
                raise BatchAccountingError("invalid_batch_accounting_oa_row", "OA 单据不符合批量账务提交条件。")
            selected_oa_rows.append(oa_row)

        bank_amount = self._bank_expense_amount(bank_row)
        oa_amount = sum(
            (self._money(row.get("amount")) or Decimal("0.00") for row in selected_oa_rows),
            Decimal("0.00"),
        )
        amount_check = self._batch_amount_check(bank_amount=bank_amount, oa_amount=oa_amount)
        submit_note = str(note or "").strip()
        if amount_check["status"] == "mismatch" and not submit_note:
            raise BatchAccountingError(
                "batch_accounting_note_required",
                "银行流水金额与所选 OA 金额合计不一致，请填写差额说明。",
                payload={"amount_check": amount_check},
            )
        relation_note = submit_note if amount_check["status"] == "mismatch" else "日常报销批量账务管理提交"

        invoice_row_ids = self._linked_invoice_row_ids(normalized_oa_row_ids, context)
        row_ids = self._dedupe([normalized_bank_row_id, *normalized_oa_row_ids, *invoice_row_ids])
        rows = [
            context.rows_by_id.get(row_id, {"id": row_id, "type": self._row_type_for_row_id(row_id)})
            for row_id in row_ids
        ]
        row_types = [self._row_type(row, row_id) for row, row_id in zip(rows, row_ids, strict=False)]
        month_scope = self._month_scope(rows)
        affected_scope_keys = self._affected_scope_keys_for_rows(rows, fallback_month_scope=month_scope)
        before_relations = self._active_relations_for_row_ids(row_ids)
        if any(normalized_bank_row_id in self._relation_row_id_set(relation) for relation in before_relations):
            raise BatchAccountingError("batch_accounting_bank_row_already_linked", "银行流水已有关联关系，请刷新后重试。")
        for oa_row_id in normalized_oa_row_ids:
            if any(
                oa_row_id in self._relation_row_id_set(relation) and self._relation_has_bank_row(relation)
                for relation in before_relations
            ):
                raise BatchAccountingError("invalid_batch_accounting_oa_row", "OA 单据已有关联流水，请刷新后重试。")

        actor_id = str(actor or "").strip() or "web_finance_user"
        special_metadata = {
            "source": BATCH_ACCOUNTING_SOURCE,
            "bank_year": resolved_bank_year,
            "oa_years": self._selected_oa_years(selected_oa_rows),
            "affected_scope_keys": affected_scope_keys,
            "created_by": actor_id,
            "bank_tag_code": tag_code,
            "tag_selection_version": context.tag_selection_version,
        }
        case_id = self._case_id_provider(normalized_bank_row_id)
        command_service = self._require_relation_command_service()
        try:
            command_result = command_service.confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=row_types,
                relation_mode=BATCH_ACCOUNTING_SOURCE,
                actor_id=actor_id,
                month_scope=month_scope,
                note=relation_note,
                amount_check=amount_check,
                special_metadata=special_metadata,
                before_relations=before_relations,
                replace_existing=True,
                history_operation_type="confirm_link",
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc
        relation = dict(command_result.get("relation") or {})
        return {
            "success": True,
            "action": "submit_batch_accounting",
            "relation_id": str(relation.get("case_id") or ""),
            "pair_relation": relation,
            "affected_row_ids": row_ids,
            "changed_case_ids": self._dedupe(
                [str(item) for item in list(command_result.get("changed_case_ids") or [])]
            ),
            "month_scope": str(relation.get("month_scope") or "all"),
            "affected_scope_keys": affected_scope_keys,
            "amount_check": amount_check,
            "message": f"已关联批量账务流水与 {len(normalized_oa_row_ids)} 项 OA。",
        }

    def withdraw(
        self,
        *,
        relation_id: str,
        actor: str,
        reason: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        normalized_relation_id = self._required_id(relation_id, "relation_id")
        note = str(reason or "").strip()
        if not note:
            raise BatchAccountingError("batch_accounting_withdraw_reason_required", "撤回原因不能为空。")
        active_relation = self._active_relation_by_case_id(normalized_relation_id)
        if not self._is_batch_accounting_relation(active_relation):
            raise BatchAccountingError("batch_accounting_relation_not_found", "批量账务关联不存在或不可撤回。")
        if expected_version is not None:
            relation_version = self._optional_int(active_relation.get("version"))
            if relation_version is not None and relation_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "关联版本已变化，请刷新后重试。")
        row_ids = self._dedupe(list(active_relation.get("row_ids") or []))
        affected_scope_keys = self._affected_scope_keys_for_relation(active_relation)
        command_service = self._require_relation_command_service()
        cancel_relation = getattr(command_service, "cancel_relation", None)
        if not callable(cancel_relation):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联写入服务不可用，请稍后重试。",
            )
        try:
            command_result = cancel_relation(
                case_id=normalized_relation_id,
                actor_id=str(actor or "").strip() or "web_finance_user",
                reason=note,
                history_operation_type="withdraw_link",
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc
        return {
            "success": True,
            "action": "withdraw_batch_accounting",
            "relation_id": normalized_relation_id,
            "affected_row_ids": self._dedupe(
                list(command_result.get("affected_row_ids") or row_ids)
            ),
            "restored_relations": list(command_result.get("restored_relations") or []),
            "changed_case_ids": self._dedupe(
                [str(item) for item in list(command_result.get("changed_case_ids") or [])]
            ),
            "month_scope": str(active_relation.get("month_scope") or "all"),
            "affected_scope_keys": affected_scope_keys,
            "message": "已撤回批量账务关联。",
        }

    def _require_query_repository(self) -> Any:
        repository = self._query_repository
        if repository is None or not callable(getattr(repository, "list_snapshot", None)):
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务 canonical 查询不可用，请稍后重试。",
            )
        return repository

    def _load_submission_context(
        self,
        *,
        bank_year: str,
        bank_row_id: str,
        oa_row_ids: list[str],
    ) -> _SubmissionContext:
        repository = self._query_repository
        loader = getattr(repository, "load_submission_context", None) if repository is not None else None
        if not callable(loader):
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务 canonical 查询不可用，请稍后重试。",
            )
        payload = loader(
            bank_year=bank_year,
            bank_row_id=bank_row_id,
            oa_row_ids=list(oa_row_ids),
        )
        if not isinstance(payload, dict):
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务 canonical 查询不可用，请稍后重试。",
            )
        bank_rows = [row for row in list(payload.get("bank_rows") or []) if isinstance(row, dict)]
        oa_rows = [row for row in list(payload.get("oa_rows") or []) if isinstance(row, dict)]
        invoice_rows = [row for row in list(payload.get("invoice_rows") or []) if isinstance(row, dict)]
        rows_by_id = {
            str(row.get("id") or ""): dict(row)
            for row in [*bank_rows, *oa_rows, *invoice_rows]
            if str(row.get("id") or "").strip()
        }
        return _SubmissionContext(
            rows_by_id=rows_by_id,
            oa_rows=oa_rows,
            invoice_ids_by_oa_id=self._invoice_ids_by_oa_id(invoice_rows),
            tag_selection_version=self._optional_int(payload.get("tag_selection_version")) or 1,
            selected_tag_codes=frozenset(
                str(code)
                for code in list(payload.get("selected_tag_codes") or [])
                if str(code).strip()
            ),
        )

    def tag_rules_payload(self, *, can_save: bool) -> dict[str, Any]:
        repository = self._require_query_repository()
        loader = getattr(repository, "tag_rules_snapshot", None)
        settings_service = self._app_settings_service
        if not callable(loader) or settings_service is None:
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务标签规则暂时不可用，请稍后重试。",
            )
        snapshot = loader()
        return settings_service.get_batch_accounting_tag_selection_payload(
            observed_tag_codes=list(snapshot.get("observed_tag_codes") or []),
            can_save=can_save,
        )

    def update_tag_rules(self, payload: dict[str, Any], *, actor: str) -> dict[str, Any]:
        repository = self._require_query_repository()
        loader = getattr(repository, "tag_rules_snapshot", None)
        settings_service = self._app_settings_service
        if not callable(loader) or settings_service is None:
            raise BatchAccountingError(
                "batch_accounting_canonical_query_unavailable",
                "批量账务标签规则暂时不可用，请稍后重试。",
            )
        observed = list(loader().get("observed_tag_codes") or [])
        return settings_service.update_batch_accounting_tag_selection(
            payload,
            actor_id=str(actor or "batch_accounting").strip() or "batch_accounting",
            observed_tag_codes=observed,
        )

    def _require_relation_command_service(self) -> Any:
        command_service = self._relation_command_service
        if command_service is None:
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联写入服务不可用，请稍后重试。",
            )
        return command_service

    def _active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        command_service = self._require_relation_command_service()
        reader = getattr(command_service, "active_relations_for_row_ids", None)
        if not callable(reader):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联读取服务不可用，请稍后重试。",
            )
        return [
            deepcopy(relation)
            for relation in list(reader(list(row_ids or [])) or [])
            if isinstance(relation, dict)
        ]

    def _active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        command_service = self._require_relation_command_service()
        reader = getattr(command_service, "get_active_relation_by_case_id", None)
        if not callable(reader):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联读取服务不可用，请稍后重试。",
            )
        try:
            relation = reader(case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return None
            raise BatchAccountingError(exc.error_code, exc.message, payload=exc.payload) from exc
        return deepcopy(relation) if isinstance(relation, dict) else None

    def _submitted_payload(self, snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        member_rows: dict[str, dict[str, Any]] = {}
        for row in list(snapshot.get("member_rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "").strip()
            payload = row.get("payload")
            if row_id and isinstance(payload, dict):
                member_rows[row_id] = dict(payload)
        bank_rows_by_id = {
            str(row.get("id") or ""): dict(row)
            for row in list(snapshot.get("bank_rows") or [])
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }
        bank_rows: list[dict[str, Any]] = []
        relations_by_bank_row_id: dict[str, Any] = {}
        for relation in list(snapshot.get("relations") or []):
            if not isinstance(relation, dict) or not self._is_batch_accounting_relation(relation):
                continue
            bank_row_ids = self._relation_member_ids(relation, "bank")
            if len(bank_row_ids) != 1:
                continue
            bank_row_id = bank_row_ids[0]
            bank_row = bank_rows_by_id.get(bank_row_id) or dict(relation.get("bank_row") or {})
            bank_rows.append(
                self._bank_row_payload(
                    bank_row,
                    relation_id=str(relation.get("case_id") or ""),
                    version=self._optional_int(relation.get("version")),
                )
            )
            oa_row_ids = self._relation_member_ids(relation, "oa")
            invoice_row_ids = self._relation_member_ids(relation, "invoice")
            invoice_ids_by_oa_id = self._invoice_ids_by_oa_id(
                [member_rows[row_id] for row_id in invoice_row_ids if row_id in member_rows]
            )
            oa_rows = [
                self._oa_row_payload(
                    member_rows.get(row_id, {"id": row_id, "type": "oa"}),
                    invoice_ids_by_oa_id.get(row_id, []),
                )
                for row_id in oa_row_ids
            ]
            relation_id = str(relation.get("case_id") or "")
            relations_by_bank_row_id[bank_row_id] = {
                "relation_id": relation_id,
                "relation": {
                    "relation_id": relation_id,
                    "note": str(relation.get("note") or ""),
                    "amount_check": deepcopy(relation.get("amount_check") or {}),
                },
                "oa_rows": oa_rows,
                "invoice_rows": [
                    deepcopy(member_rows.get(row_id, {"id": row_id, "type": "invoice"}))
                    for row_id in invoice_row_ids
                ],
            }
        return bank_rows, relations_by_bank_row_id

    @classmethod
    def _relation_member_ids(cls, relation: dict[str, Any], expected_type: str) -> list[str]:
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        accepted_types = {
            "bank": {"bank", "bank_transaction"},
            "oa": {"oa"},
            "invoice": {"invoice", "input_invoice", "output_invoice"},
        }.get(expected_type, {expected_type})
        result: list[str] = []
        for index, raw_row_id in enumerate(row_ids):
            row_id = str(raw_row_id or "").strip()
            row_type = str(row_types[index] or "").strip().lower() if index < len(row_types) else ""
            if row_id and row_type in accepted_types:
                result.append(row_id)
        return cls._dedupe(result)

    @classmethod
    def _invoice_ids_by_oa_id(cls, invoice_rows: list[dict[str, Any]]) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for row in invoice_rows:
            invoice_id = str(row.get("id") or "").strip()
            source_oa_id = cls._invoice_source_oa_id(row)
            if invoice_id and source_oa_id:
                result.setdefault(source_oa_id, []).append(invoice_id)
        return {oa_id: cls._dedupe(invoice_ids) for oa_id, invoice_ids in result.items()}

    @classmethod
    def _invoice_source_oa_id(cls, invoice_row: dict[str, Any]) -> str | None:
        for key in ("source_oa_id", "derived_from_oa_id", "source_oa_row_id", "oa_row_id"):
            value = cls._clean_text(invoice_row.get(key))
            if value:
                return value.split(":item:", 1)[0]
        for source_link in list(invoice_row.get("source_links") or []):
            if not isinstance(source_link, dict) or source_link.get("source_type") != "oa_attachment_invoice":
                continue
            for key in ("derived_from_oa_id", "source_expense_item_id", "source_workbench_row_id"):
                value = cls._clean_text(source_link.get(key))
                if value:
                    return value.split(":item:", 1)[0]
        return None

    def _linked_invoice_row_ids(self, oa_row_ids: list[str], context: _SubmissionContext) -> list[str]:
        return self._dedupe(
            invoice_row_id
            for oa_row_id in oa_row_ids
            for invoice_row_id in context.invoice_ids_by_oa_id.get(oa_row_id, [])
        )

    def _bank_row_payload(
        self,
        row: dict[str, Any],
        *,
        relation_id: str = "",
        version: int | None = None,
    ) -> dict[str, Any]:
        bank_name, account_last4 = self._bank_account_parts(row)
        return {
            "id": str(row.get("id") or ""),
            "trade_time": str(row.get("trade_time") or row.get("pay_receive_time") or row.get("txn_date") or ""),
            "counterparty_name": self._clean_text(row.get("counterparty_name")),
            "direction": "expense",
            "direction_label": "支出",
            "amount": self._format_amount(self._bank_expense_amount(row)),
            "bank_name": bank_name,
            "account_last4": account_last4,
            "relation_id": relation_id or str(row.get("relation_id") or ""),
            "version": version or self._optional_int(row.get("version")) or 1,
            "tag_code": self._clean_text(row.get("tag_code")),
            "tag_label": self._clean_text(row.get("tag_label")),
            "tag_primary_label": self._clean_text(row.get("tag_primary_label")),
            "tag_sub_label": self._clean_text(row.get("tag_sub_label")),
        }

    def _oa_row_payload(self, row: dict[str, Any], linked_invoice_row_ids: list[str]) -> dict[str, Any]:
        return {
            "id": str(row.get("id") or ""),
            "applicant": self._first_text(row, ("applicant", "applicant_name", "apply_user", "userName"), ("申请人",)),
            "apply_time": self._first_text(
                row,
                ("apply_time", "application_time", "application_date", "date", "created_at"),
                ("申请日期", "单据日期", "日期"),
            ),
            "project_name": self._first_text(row, ("project_name", "project"), ("项目名称", "项目")),
            "amount": self._format_amount(self._money(row.get("amount")) or Decimal("0.00")),
            "reason": self._first_text(row, ("reason", "remark"), ("申请事由", "报销事由", "事由", "备注")),
            "apply_type": str(row.get("apply_type") or ""),
            "expense_type": str(row.get("expense_type") or ""),
            "linked_invoice_row_ids": list(linked_invoice_row_ids),
        }

    def _affected_scope_keys_for_relation(self, relation: dict[str, Any]) -> list[str]:
        metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
        metadata_scope_keys = self._normalize_scope_keys(metadata.get("affected_scope_keys"))
        if metadata_scope_keys:
            return metadata_scope_keys
        fallback_month_scope = str(relation.get("month_scope") or "").strip()
        row_ids = self._dedupe(list(relation.get("row_ids") or []))
        bank_row_ids = self._relation_member_ids(relation, "bank")
        bank_row_id = bank_row_ids[0] if len(bank_row_ids) == 1 else ""
        oa_row_ids = self._relation_member_ids(relation, "oa")
        bank_year = str(metadata.get("bank_year") or "").strip()
        if not bank_year and re.fullmatch(r"20\d{2}-\d{2}", fallback_month_scope):
            bank_year = fallback_month_scope[:4]
        if bank_row_id and oa_row_ids and re.fullmatch(r"20\d{2}", bank_year):
            try:
                context = self._load_submission_context(
                    bank_year=bank_year,
                    bank_row_id=bank_row_id,
                    oa_row_ids=oa_row_ids,
                )
                rows = [
                    context.rows_by_id.get(
                        row_id,
                        {"id": row_id, "type": self._row_type_for_row_id(row_id)},
                    )
                    for row_id in row_ids
                ]
                scope_keys = self._affected_scope_keys_for_rows(
                    rows,
                    fallback_month_scope=fallback_month_scope,
                )
                if scope_keys:
                    return scope_keys
            except BatchAccountingError:
                pass
        return self._affected_scope_keys_for_rows([], fallback_month_scope=fallback_month_scope)

    @classmethod
    def _is_batch_accounting_relation(cls, relation: dict[str, Any] | None) -> bool:
        return (
            isinstance(relation, dict)
            and relation.get("status") == "active"
            and relation.get("relation_mode") == BATCH_ACCOUNTING_SOURCE
        )

    def _is_batch_bank_row(self, row: dict[str, Any], year: str) -> bool:
        row_id = str(row.get("id") or "").strip()
        return (
            bool(row_id)
            and (str(row.get("type") or "bank") == "bank" or self._row_type_for_row_id(row_id) == "bank")
            and self._clean_text(row.get("counterparty_name")) == BATCH_ACCOUNTING_COUNTERPARTY_NAME
            and self._row_year_matches(
                row,
                year,
                keys=("trade_time", "pay_receive_time", "txn_date", "transaction_date", "date"),
            )
            and self._bank_expense_amount(row) > Decimal("0.00")
        )

    def _is_eligible_oa_row(self, row: dict[str, Any]) -> bool:
        row_id = str(row.get("id") or "").strip()
        return (
            bool(row_id)
            and (str(row.get("type") or "oa") == "oa" or self._row_type_for_row_id(row_id) == "oa")
            and ":item:" not in row_id
            and str(row.get("row_kind") or "").strip() not in {"schedule_detail", "detail"}
            and self._contains_daily_reimbursement(row)
        )

    @staticmethod
    def _command_error(exc: WorkbenchRelationCommandError) -> BatchAccountingError:
        if exc.error_code == "workbench_relation_active_row_conflict":
            return BatchAccountingError(
                "batch_accounting_relation_conflict",
                "所选流水或 OA 已有关联关系，请刷新后重试。",
                payload=dict(exc.payload),
            )
        if exc.error_code == "workbench_relation_not_found":
            return BatchAccountingError(
                "batch_accounting_relation_not_found",
                "批量账务关联不存在或不可撤回。",
                payload=dict(exc.payload),
            )
        return BatchAccountingError(exc.error_code, exc.message, payload=dict(exc.payload))

    @classmethod
    def _affected_scope_keys_for_rows(
        cls,
        rows: Iterable[dict[str, Any]],
        *,
        fallback_month_scope: str | None = None,
    ) -> list[str]:
        months = sorted(
            {
                month
                for row in rows
                if isinstance(row, dict)
                for month in [cls._row_month(row)]
                if month is not None
            }
        )
        if months:
            return months
        return cls._normalize_scope_keys(fallback_month_scope)

    @classmethod
    def _normalize_scope_keys(cls, value: Any) -> list[str]:
        values = [value] if isinstance(value, str) else list(value) if isinstance(value, Iterable) else []
        concrete = sorted(
            cls._dedupe(
                str(item or "").strip()
                for item in values
                if re.fullmatch(r"20\d{2}-\d{2}", str(item or "").strip())
            )
        )
        if concrete:
            return concrete
        return ["all"] if any(str(item or "").strip() == "all" for item in values) else []

    @staticmethod
    def _validate_year(year: str) -> str:
        resolved_year = str(year or "").strip()
        if not re.fullmatch(r"20\d{2}", resolved_year):
            raise BatchAccountingError("invalid_batch_accounting_year", "year must be a four-digit year.")
        return resolved_year

    @staticmethod
    def _required_id(value: str, field_name: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise BatchAccountingError("invalid_batch_accounting_request", f"{field_name} is required.")
        return resolved

    @classmethod
    def _normalize_ids(cls, values: list[Any]) -> list[str]:
        ids = cls._dedupe(str(value or "").strip() for value in values)
        if not ids:
            raise BatchAccountingError("invalid_batch_accounting_request", "at least one OA row is required.")
        return ids

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    @staticmethod
    def _default_case_id_for_bank_row(bank_row_id: str) -> str:
        safe_bank_row_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(bank_row_id or "").strip()).strip("-")
        if not safe_bank_row_id:
            raise BatchAccountingError("invalid_batch_accounting_bank_row", "银行流水 ID 不能为空。")
        return f"CASE-BATCH-{safe_bank_row_id[:96]}"

    @classmethod
    def _relation_has_bank_row(cls, relation: Any) -> bool:
        if not isinstance(relation, dict):
            return False
        row_ids = [cls._clean_text(value) for value in list(relation.get("row_ids") or [])]
        row_types = [cls._clean_text(value) for value in list(relation.get("row_types") or [])]
        return any(
            (
                (row_types[index] if index < len(row_types) else cls._row_type_for_row_id(row_id))
                in {"bank", "bank_transaction"}
                or cls._row_type_for_row_id(row_id) == "bank"
            )
            for index, row_id in enumerate(row_ids)
        )

    @staticmethod
    def _relation_row_id_set(relation: dict[str, Any]) -> set[str]:
        return {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _first_text(
        cls,
        row: dict[str, Any],
        keys: tuple[str, ...],
        nested_keys: tuple[str, ...] = (),
    ) -> str:
        for key in keys:
            value = cls._clean_text(row.get(key))
            if value:
                return value
        for nested_field in ("summary_fields", "detail_fields", "normalized_payload", "raw_payload"):
            nested = row.get(nested_field)
            if not isinstance(nested, dict):
                continue
            if isinstance(nested.get("normalized_payload"), dict):
                nested = nested["normalized_payload"]
            for key in nested_keys:
                value = cls._clean_text(nested.get(key))
                if value:
                    return value
        return ""

    @classmethod
    def _contains_daily_reimbursement(cls, row: dict[str, Any]) -> bool:
        if "日常报销" in cls._clean_text(row.get("apply_type")) or "日常报销" in cls._clean_text(row.get("expense_type")):
            return True
        payload = row.get("normalized_payload")
        return isinstance(payload, dict) and (
            "日常报销" in cls._clean_text(payload.get("apply_type"))
            or "日常报销" in cls._clean_text(payload.get("expense_type"))
        )

    @classmethod
    def _row_year_matches(cls, row: dict[str, Any], year: str, *, keys: tuple[str, ...]) -> bool:
        return any(str(row.get(key) or "").strip().startswith(year) for key in keys)

    @classmethod
    def _bank_expense_amount(cls, row: dict[str, Any]) -> Decimal:
        debit = cls._money(row.get("debit_amount"))
        if debit is not None and debit > Decimal("0.00"):
            return debit
        direction = cls._clean_text(
            row.get("direction") or row.get("txn_direction") or row.get("direction_code")
        ).lower()
        amount = cls._money(row.get("amount")) or cls._money(row.get("signed_amount")) or Decimal("0.00")
        if direction in {"expense", "outflow", "支出"}:
            return abs(amount)
        signed_value = row.get("signed_amount")
        signed_amount = cls._money(signed_value)
        try:
            if signed_amount is not None and Decimal(str(signed_value).replace(",", "")) < Decimal("0.00"):
                return signed_amount
        except (InvalidOperation, ValueError):
            pass
        return Decimal("0.00")

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "")).copy_abs()
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def _format_amount(cls, value: Decimal) -> str:
        return f"{cls._quantize(value):.2f}"

    def _batch_amount_check(self, *, bank_amount: Decimal, oa_amount: Decimal) -> dict[str, Any]:
        amount_delta = self._quantize(bank_amount) - self._quantize(oa_amount)
        status = "matched" if amount_delta == Decimal("0.00") else "mismatch"
        return {
            "status": status,
            "direction": "expense",
            "bank_amount": self._format_amount(bank_amount),
            "oa_amount": self._format_amount(oa_amount),
            "amount_delta": self._format_amount(amount_delta),
            "requires_note": status == "mismatch",
        }

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _bank_account_parts(cls, row: dict[str, Any]) -> tuple[str, str]:
        label = cls._clean_text(row.get("payment_account_label") or row.get("account_label"))
        bank_name = cls._clean_text(
            row.get("bank_name")
            or row.get("selected_bank_name")
            or row.get("imported_bank_name")
        )
        account_no = cls._clean_text(row.get("account_no"))
        account_last4 = cls._clean_text(
            row.get("account_last4")
            or row.get("selected_bank_last4")
            or row.get("imported_bank_last4")
        )
        if label:
            parts = label.split()
            if not bank_name and parts:
                bank_name = parts[0].replace("基本户", "").replace("一般户", "")
            if not account_last4:
                digit_groups = re.findall(r"\d{4,}", label)
                if digit_groups:
                    account_last4 = digit_groups[-1][-4:]
        if not account_last4 and account_no:
            digits = re.sub(r"\D", "", account_no)
            account_last4 = digits[-4:] if digits else ""
        return bank_name, account_last4

    @classmethod
    def _row_type(cls, row: dict[str, Any], row_id: str) -> str:
        return str(row.get("type") or cls._row_type_for_row_id(row_id) or "unknown")

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        return row_type_for_workbench_row_id(row_id)

    @classmethod
    def _month_scope(cls, rows: Iterable[dict[str, Any]]) -> str:
        months = {month for row in rows for month in [cls._row_month(row)] if month is not None}
        return next(iter(months)) if len(months) == 1 else "all"

    @classmethod
    def _row_month(cls, row: dict[str, Any]) -> str | None:
        for key in (
            "trade_time",
            "pay_receive_time",
            "txn_date",
            "apply_time",
            "application_time",
            "application_date",
            "issue_date",
        ):
            value = str(row.get(key) or "").strip()
            if re.match(r"20\d{2}-\d{2}", value):
                return value[:7]
        return None

    @classmethod
    def _selected_oa_years(cls, rows: Iterable[dict[str, Any]]) -> list[str]:
        return sorted(
            {
                month[:4]
                for row in rows
                for month in [cls._row_month(row)]
                if month is not None
            }
        )

    @classmethod
    def _pagination_from_values(
        cls,
        *,
        page: int | str | None,
        page_size: int | str | None,
    ) -> dict[str, int]:
        return {
            "page": cls._positive_int(page if page is not None else 1, "page"),
            "page_size": cls._positive_int(
                page_size if page_size is not None else 100,
                "page_size",
                maximum=200,
            ),
        }

    @staticmethod
    def _positive_int(value: object, field: str, *, maximum: int | None = None) -> int:
        try:
            number = int(value if value not in (None, "") else 1)
        except (TypeError, ValueError) as exc:
            raise BatchAccountingError("invalid_paging", f"{field} must be a positive integer.") from exc
        if number < 1:
            raise BatchAccountingError("invalid_paging", f"{field} must be a positive integer.")
        if maximum is not None and number > maximum:
            raise BatchAccountingError("invalid_paging", f"{field} must be <= {maximum}.")
        return number

    @staticmethod
    def _record_read_timing(
        observer: Callable[[str, float], None] | None,
        phase: str,
        started_at: float,
    ) -> None:
        if observer is not None:
            observer(phase, round(max(0.0, (perf_counter() - started_at) * 1000), 3))
