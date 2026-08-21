from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.invoice_expense_item_links import (
    InvoiceSourceLinksCasConflict,
    explicit_expense_item_links,
    replace_explicit_expense_item_links,
    source_links,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    canonical_oa_expense_item_ids,
)
from fin_ops_platform.services.workbench_amount_check_service import (
    unassigned_invoice_anomaly_fingerprint,
)
from fin_ops_platform.services.workbench_row_identity import canonical_workbench_row_type


ACTION_NAME = "assign_invoice_expense_items"
ACTION_PATH = "/api/workbench/actions/assign-invoice-expense-items"
MAX_TARGETS = 100


class WorkbenchInvoiceExpenseItemAssignmentError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class InvoiceExpenseItemTarget:
    oa_row_id: str
    expense_item_id: str


@dataclass(frozen=True)
class _AssignInvoiceExpenseItemsCommand:
    case_id: str
    invoice_row_id: str
    targets: tuple[InvoiceExpenseItemTarget, ...]
    anomaly_fingerprint: str
    idempotency_key: str
    actor_id: str
    tenant_id: str
    request_id: str
    payload: dict[str, Any]
    action_name: str = ACTION_NAME
    expected_versions: dict[str, Any] | None = None


class WorkbenchInvoiceExpenseItemAssignmentService:
    """Assign one canonical relation invoice to explicitly selected OA expense items."""

    def __init__(self, *, unit_of_work: Any) -> None:
        self._unit_of_work = unit_of_work

    def assign(
        self,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        command = self._command(
            payload,
            actor_id=actor_id,
            tenant_id=tenant_id,
            request_id=request_id,
        )
        return self._unit_of_work.run(command, lambda context: self._assign(context, command))

    @classmethod
    def _command(
        cls,
        payload: dict[str, Any],
        *,
        actor_id: str,
        tenant_id: str,
        request_id: str,
    ) -> _AssignInvoiceExpenseItemsCommand:
        if not isinstance(payload, dict):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invalid_invoice_expense_item_assignment",
                "请求内容必须是 JSON 对象。",
                status_code=400,
            )
        case_id = cls._required_text(payload.get("case_id"), "case_id")
        invoice_row_id = cls._required_text(payload.get("invoice_row_id"), "invoice_row_id")
        anomaly_fingerprint = cls._required_text(
            payload.get("anomaly_fingerprint"),
            "anomaly_fingerprint",
        )
        idempotency_key = cls._required_text(payload.get("idempotency_key"), "idempotency_key")
        raw_targets = payload.get("targets")
        if not isinstance(raw_targets, list) or not raw_targets:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invalid_invoice_expense_item_assignment",
                "targets 必须至少包含一个 OA 明细目标。",
                status_code=400,
            )
        if len(raw_targets) > MAX_TARGETS:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invalid_invoice_expense_item_assignment",
                f"单次最多可归属 {MAX_TARGETS} 个 OA 明细目标。",
                status_code=400,
            )
        targets: list[InvoiceExpenseItemTarget] = []
        for value in raw_targets:
            if not isinstance(value, dict):
                raise WorkbenchInvoiceExpenseItemAssignmentError(
                    "invalid_invoice_expense_item_assignment",
                    "targets 中的每一项必须是对象。",
                    status_code=400,
                )
            targets.append(
                InvoiceExpenseItemTarget(
                    oa_row_id=cls._required_text(value.get("oa_row_id"), "targets.oa_row_id"),
                    expense_item_id=cls._required_text(
                        value.get("expense_item_id"),
                        "targets.expense_item_id",
                    ),
                )
            )
        target_keys = [(item.oa_row_id, item.expense_item_id) for item in targets]
        if len(set(target_keys)) != len(target_keys):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invalid_invoice_expense_item_assignment",
                "targets 不能包含重复的 OA 明细目标。",
                status_code=400,
            )
        normalized_targets = tuple(
            InvoiceExpenseItemTarget(oa_row_id=oa_row_id, expense_item_id=expense_item_id)
            for oa_row_id, expense_item_id in sorted(target_keys)
        )
        normalized_payload = {
            "case_id": case_id,
            "invoice_row_id": invoice_row_id,
            "targets": [
                {
                    "oa_row_id": item.oa_row_id,
                    "expense_item_id": item.expense_item_id,
                }
                for item in normalized_targets
            ],
            "anomaly_fingerprint": anomaly_fingerprint,
            "idempotency_key": idempotency_key,
        }
        return _AssignInvoiceExpenseItemsCommand(
            case_id=case_id,
            invoice_row_id=invoice_row_id,
            targets=normalized_targets,
            anomaly_fingerprint=anomaly_fingerprint,
            idempotency_key=idempotency_key,
            actor_id=cls._required_text(actor_id, "actor_id"),
            tenant_id=cls._required_text(tenant_id, "tenant_id"),
            request_id=cls._required_text(request_id, "request_id"),
            payload=normalized_payload,
        )

    @classmethod
    def _assign(cls, context: Any, command: _AssignInvoiceExpenseItemsCommand) -> dict[str, Any]:
        pair_relations = getattr(context, "pair_relations", None)
        canonical_query = getattr(context, "canonical_query", None)
        invoices = getattr(context, "invoice_source_links", None)
        audit = getattr(context, "operation_audit", None)
        if any(value is None for value in (pair_relations, canonical_query, invoices, audit)):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invoice_expense_item_assignment_unavailable",
                "发票明细归属服务暂时不可用。",
                status_code=503,
            )

        pair_relations.acquire_relation_member_locks(
            [command.invoice_row_id, *(target.oa_row_id for target in command.targets)],
            row_types=["invoice", *("oa" for _target in command.targets)],
            case_ids=[command.case_id],
        )
        relation = pair_relations.load_active_workbench_pair_relation_by_case_id_for_update(
            command.case_id
        )
        if not isinstance(relation, dict):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "workbench_relation_not_found",
                "当前关联关系不存在或已发生变化，请刷新后重试。",
            )
        relation_ids = [str(value or "").strip() for value in list(relation.get("row_ids") or [])]
        relation_types = [
            canonical_workbench_row_type(value, unknown="")
            for value in list(relation.get("row_types") or [])
        ]
        if len(relation_ids) != len(relation_types) or any(not value for value in relation_types):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "workbench_relation_members_invalid",
                "当前关联关系成员不完整，请刷新后重试。",
            )
        relation_members = set(zip(relation_types, relation_ids, strict=True))
        if ("invoice", command.invoice_row_id) not in relation_members:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invoice_not_in_relation",
                "所选发票已不属于当前关联关系，请刷新后重试。",
            )
        target_oa_ids = sorted({target.oa_row_id for target in command.targets})
        if any(("oa", oa_row_id) not in relation_members for oa_row_id in target_oa_ids):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "oa_target_not_in_relation",
                "所选 OA 明细已不属于当前关联关系，请刷新后重试。",
            )

        oa_member_ids = sorted(
            row_id for row_type, row_id in relation_members if row_type == "oa"
        )
        if not oa_member_ids:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "relation_has_no_oa_expense_items",
                "当前关联关系没有可归属的 OA 明细。",
            )
        try:
            canonical_rows = canonical_query.get_canonical_rows_by_ids_in_current_transaction(
                [*oa_member_ids, command.invoice_row_id],
                row_types=[*("oa" for _row_id in oa_member_ids), "invoice"],
            )
            expense_items_by_oa = (
                canonical_query.get_oa_expense_items_by_row_ids_in_current_transaction(
                    oa_member_ids
                )
            )
        except (KeyError, ValueError) as exc:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "canonical_relation_members_changed",
                "关联关系成员已变化，请刷新后重试。",
            ) from exc
        oa_rows = [
            {
                **canonical_rows[row_id],
                "expense_items": expense_items_by_oa[row_id],
            }
            for row_id in oa_member_ids
        ]
        available_targets = {
            (oa_row_id, expense_item_id)
            for oa_row_id in oa_member_ids
            for item in expense_items_by_oa[oa_row_id]
            if isinstance(item, dict)
            for expense_item_id in [
                str(item.get("id") or item.get("expense_item_id") or "").strip()
            ]
            if expense_item_id
        }
        requested_targets = {
            (target.oa_row_id, target.expense_item_id) for target in command.targets
        }
        if not requested_targets.issubset(available_targets):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "oa_expense_item_target_changed",
                "所选 OA 明细不存在或已变化，请刷新后重试。",
            )

        invoice_snapshot = invoices.load_invoice_source_links_for_update(
            context.transaction,
            invoice_id=command.invoice_row_id,
        )
        if not isinstance(invoice_snapshot, dict):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invoice_not_found",
                "所选发票不存在或已不可用，请刷新后重试。",
            )
        current_source_links = source_links(invoice_snapshot.get("source_links"))
        explicit_links = explicit_expense_item_links(current_source_links)
        if explicit_links:
            explicit_targets: list[tuple[str, str]] = []
            for link in explicit_links:
                source_oa_id = str(
                    link.get("derived_from_oa_id")
                    or link.get("source_workbench_row_id")
                    or ""
                ).strip()
                source_expense_item_id = str(
                    link.get("source_expense_item_id") or ""
                ).strip()
                if not source_oa_id or not source_expense_item_id:
                    raise WorkbenchInvoiceExpenseItemAssignmentError(
                        "invoice_expense_item_assignment_conflict",
                        "发票已有不完整的 OA 明细归属，未覆盖原归属。",
                    )
                explicit_targets.append((source_oa_id, source_expense_item_id))
            if set(explicit_targets) != requested_targets:
                raise WorkbenchInvoiceExpenseItemAssignmentError(
                    "invoice_expense_item_assignment_conflict",
                    "发票已有不同的 OA 明细归属，未覆盖原归属。",
                )
            return {
                "success": True,
                "changed": False,
                "case_id": command.case_id,
                "invoice_row_id": command.invoice_row_id,
                "targets": [
                    {
                        "oa_row_id": target.oa_row_id,
                        "expense_item_id": target.expense_item_id,
                    }
                    for target in command.targets
                ],
            }
        invoice_for_linking = {
            **dict(canonical_rows[command.invoice_row_id]),
            "source_links": current_source_links,
        }
        if cls._has_valid_expense_item_edge(
            invoice_for_linking,
            oa_rows=oa_rows,
            available_targets=available_targets,
        ):
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invoice_expense_item_already_assigned",
                "所选发票已存在有效的 OA 明细归属，请刷新后重试。",
            )

        invoice_total = cls._format_money(invoice_snapshot.get("invoice_total"))
        current_fingerprint = unassigned_invoice_anomaly_fingerprint(
            relation_id=command.case_id,
            invoice_row_id=command.invoice_row_id,
            invoice_total=invoice_total,
        )
        if command.anomaly_fingerprint != current_fingerprint:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "workbench_anomaly_changed",
                "异常证据已变化，请刷新后重试。",
            )

        next_source_links = replace_explicit_expense_item_links(
            current_source_links,
            case_id=command.case_id,
            targets=(
                (target.oa_row_id, target.expense_item_id)
                for target in command.targets
            ),
            entry_method="workbench_manual_assignment",
        )
        try:
            invoices.update_invoice_source_links_cas(
                context.transaction,
                [{
                    "invoice_id": command.invoice_row_id,
                    "before_source_links": source_links(
                        invoice_snapshot.get("stored_source_links")
                    ),
                    "source_links": next_source_links,
                }],
                actor_id=command.actor_id,
                reason="Assign relation invoice to selected OA expense items",
            )
        except InvoiceSourceLinksCasConflict as exc:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invoice_source_links_changed",
                "发票归属已发生变化，请刷新后重试。",
            ) from exc
        result = {
            "success": True,
            "changed": True,
            "case_id": command.case_id,
            "invoice_row_id": command.invoice_row_id,
            "targets": [
                {
                    "oa_row_id": target.oa_row_id,
                    "expense_item_id": target.expense_item_id,
                }
                for target in command.targets
            ],
            "previous_anomaly_fingerprint": current_fingerprint,
        }
        audit.append_operation_event({
            "event_type": "workbench.invoice_expense_items.assigned",
            "object_type": "invoice_expense_item_assignment",
            "object_id": command.invoice_row_id,
            "actor_id": command.actor_id,
            "scope": command.tenant_id,
            "trace_id": command.request_id,
            "action": "workbench.invoice_expense_items.assign",
            "page_key": "reconciliation-workbench",
            "operation_location": ACTION_PATH,
            "outcome": "success",
            "request_id": command.request_id,
            "payload": result,
        })
        return result

    @staticmethod
    def _required_text(value: Any, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise WorkbenchInvoiceExpenseItemAssignmentError(
                "invalid_invoice_expense_item_assignment",
                f"{field_name} 不能为空。",
                status_code=400,
            )
        return normalized

    @staticmethod
    def _format_money(value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{Decimal(str(value)).quantize(Decimal('0.01')):.2f}"
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _has_valid_expense_item_edge(
        invoice_row: dict[str, Any],
        *,
        oa_rows: list[dict[str, Any]],
        available_targets: set[tuple[str, str]],
    ) -> bool:
        links = source_links(invoice_row.get("source_links"))
        explicit = [
            link for link in links
            if str(link.get("source_type") or "").strip() == "oa_expense_item_invoice"
        ]
        effective = explicit or [
            link for link in links
            if str(link.get("source_type") or "").strip() == "oa_attachment_invoice"
        ]
        for link in effective:
            expense_item_id = str(link.get("source_expense_item_id") or "").strip()
            source_oa_id = str(
                link.get("derived_from_oa_id")
                or link.get("source_workbench_row_id")
                or ""
            ).strip()
            exact_owners = {
                oa_row_id
                for oa_row_id, candidate_item_id in available_targets
                if candidate_item_id == expense_item_id
            }
            if exact_owners and (not source_oa_id or source_oa_id in exact_owners):
                return True
        return any(
            canonical_oa_expense_item_ids(oa_row=oa_row, invoice_row=invoice_row)
            for oa_row in oa_rows
        )
