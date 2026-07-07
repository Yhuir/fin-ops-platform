from __future__ import annotations

import json
import unittest
from decimal import Decimal
from http import HTTPStatus

from fin_ops_platform.app.server import Application
from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_read_model_repository import InputInvoiceUsageReadModelRepositoryPort
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.invoice_usage_collection_read_model_refresh import (
    InvoiceUsageCollectionReadModelRefreshService,
)
from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    input_invoice_usage_source_versions,
    oa_pending_payment_source_versions,
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import InvoiceUsageCollectionSqlProjectionBuilder
from fin_ops_platform.services.oa_adapter import OAApplicationRecord, OAReadStatus
from fin_ops_platform.services.oa_payment_status_service import PAY_STATUS_PENDING, OAPaymentStatusRecord
from fin_ops_platform.services.output_invoice_collection_read_model_repository import (
    OutputInvoiceCollectionReadModelRepositoryPort,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueEvent
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str, int | None]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int | str | None = None,
    ) -> None:
        self.completed.append(
            (tenant_id, scope_type, scope_key, int(source_version) if source_version is not None else None)
        )

    def read_model_refresh_is_current(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: object,
    ) -> bool:
        return True


def _input_invoice_usage_rows_response(app: Application, query: dict[str, list[str]]):
    payload = app._get_input_invoice_usage_rows_from_sql_read_model(query)
    assert payload is not None
    status = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
    return Application._json_response(status, payload)


def _output_invoice_collection_rows_response(app: Application, query: dict[str, list[str]]):
    payload = app._get_output_invoice_collection_rows_from_sql_read_model(query)
    assert payload is not None
    status = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
    return Application._json_response(status, payload)


class EmptyTransactionConnection:
    def transaction(self) -> "EmptyTransactionConnection":
        return self

    def __enter__(self) -> "EmptyTransactionConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def fetch_all(self, *_args: object, **_kwargs: object) -> list[dict]:
        return []


class FreshEmptyWorkbenchRelationFacade:
    @property
    def last_source_versions(self) -> dict[str, object]:
        return {}

    def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": {},
            "read_model_scope_keys": [],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }

    def get_by_row_ids(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return self.list_by_month()


class FreshStaticWorkbenchRelationFacade:
    def __init__(self, relations: list[dict[str, object]]) -> None:
        self.relations = [dict(relation) for relation in relations]

    @property
    def last_source_versions(self) -> dict[str, object]:
        return {}

    def list_by_month(self, _month: str, **_kwargs: object) -> dict[str, object]:
        return self._payload([self._group(relation) for relation in self.relations])

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        wanted = {str(row_id) for row_id in list(row_ids or [])}
        return self._payload(
            [
                self._group(relation)
                for relation in self.relations
                if wanted & {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            ]
        )

    def _payload(self, groups: list[dict[str, object]]) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            group_id = str(group["group_id"])
            payload = group["payload"]
            assert isinstance(payload, dict)
            row_ids = [str(row_id) for row_id in list(payload["row_ids"])]
            row_types = [str(row_type) for row_type in list(payload["row_types"])]
            for row_id, row_type in zip(row_ids, row_types):
                key = (row_id, group_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {"row_id": row_id, "row_type": row_type, "relation_status": "linked", "group_ids": [group_id]}
                )
        return {"status": "fresh", "rows": rows, "groups": groups, "source_versions": {}, "read_model_scope_keys": []}

    @staticmethod
    def _group(relation: dict[str, object]) -> dict[str, object]:
        case_id = str(relation.get("case_id") or "")
        row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
        return {
            "group_id": case_id,
            "scope_month": relation.get("month_scope") or "2026-05",
            "oa_row_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "oa"],
            "bank_transaction_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "bank"],
            "input_invoice_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "invoice"],
            "output_invoice_ids": [],
            "payload": {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": row_types,
                "relation_mode": relation.get("relation_mode") or "manual_confirmed",
                "amount_check": dict(relation.get("amount_check") or {}),
                "special_metadata": {},
            },
        }


class CrossMonthVersionWorkbenchRelationFacade:
    def __init__(self, *, invoice_id: str, bank_id: str, oa_id: str) -> None:
        self.invoice_id = invoice_id
        self.bank_id = bank_id
        self.oa_id = oa_id
        self._last_source_versions: dict[str, object] = {}

    @property
    def last_source_versions(self) -> dict[str, object]:
        return dict(self._last_source_versions)

    def list_by_month(self, month: str, **_kwargs: object) -> dict[str, object]:
        self._last_source_versions = {"source_version": f"workbench_relation:{month}"}
        return {
            "status": "fresh",
            "rows": [
                {
                    "row_id": self.invoice_id,
                    "row_type": "input_invoice",
                    "relation_status": "unlinked",
                    "group_ids": [],
                }
            ],
            "groups": [],
            "source_versions": dict(self._last_source_versions),
            "read_model_scope_keys": [str(month)],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: object) -> dict[str, object]:
        self._last_source_versions = {"source_version": "workbench_relation:2026-04"}
        if self.invoice_id not in {str(row_id) for row_id in list(row_ids or [])}:
            return {
                "status": "fresh",
                "rows": [],
                "groups": [],
                "source_versions": dict(self._last_source_versions),
                "read_model_scope_keys": ["2026-04"],
                "refresh_enqueued": False,
                "stale_reasons": [],
            }
        return {
            "status": "fresh",
            "rows": [
                {
                    "row_id": self.invoice_id,
                    "row_type": "input_invoice",
                    "relation_status": "linked",
                    "group_ids": ["case-cross-month-version"],
                }
            ],
            "groups": [
                {
                    "group_id": "case-cross-month-version",
                    "scope_month": "2026-04",
                    "relation_status": "linked",
                    "payload": {
                        "case_id": "case-cross-month-version",
                        "row_ids": [self.oa_id, self.bank_id, self.invoice_id],
                        "row_types": ["oa", "bank", "invoice"],
                        "relation_mode": "manual_confirmed",
                        "relation_status": "linked",
                        "amount_check": {"matched": True},
                    },
                }
            ],
            "source_versions": dict(self._last_source_versions),
            "read_model_scope_keys": ["2026-04"],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }


class InvoiceReadModelConnection:
    def __init__(
        self,
        *,
        input_rows: list[dict] | None = None,
        output_rows: list[dict] | None = None,
        oa_rows: list[dict] | None = None,
        input_scope_rows: list[dict] | None = None,
        output_scope_rows: list[dict] | None = None,
        oa_scope_rows: list[dict] | None = None,
        workbench_relation_scope_rows: list[dict] | None = None,
        dirty: bool = False,
        scope_exists: bool = True,
    ) -> None:
        self.input_rows = list(input_rows or [])
        self.output_rows = list(output_rows or [])
        self.oa_rows = list(oa_rows or [])
        self.input_scope_rows = list(input_scope_rows or [])
        self.output_scope_rows = list(output_scope_rows or [])
        self.oa_scope_rows = list(oa_scope_rows or [])
        self.workbench_relation_scope_rows = list(workbench_relation_scope_rows or [])
        self.dirty = dirty
        self.scope_exists = scope_exists
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if "scope_key <> 'all' and scope_key not in" not in normalized:
            return
        allowed_scope_keys = {str(item) for item in params}
        if normalized.startswith("delete from read_model.input_invoice_usage_rows"):
            self.input_rows = [
                row
                for row in self.input_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]
        if normalized.startswith("delete from read_model.input_invoice_usage_scopes"):
            self.input_scope_rows = [
                row
                for row in self.input_scope_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]
        if normalized.startswith("delete from read_model.output_invoice_collection_rows"):
            self.output_rows = [
                row
                for row in self.output_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]
        if normalized.startswith("delete from read_model.output_invoice_collection_scopes"):
            self.output_scope_rows = [
                row
                for row in self.output_scope_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]
        if normalized.startswith("delete from read_model.oa_pending_payment_rows"):
            self.oa_rows = [
                row
                for row in self.oa_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]
        if normalized.startswith("delete from read_model.oa_pending_payment_scopes"):
            self.oa_scope_rows = [
                row
                for row in self.oa_scope_rows
                if str(row.get("scope_key") or "all") == "all" or str(row.get("scope_key")) in allowed_scope_keys
            ]

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.input_invoice_usage_rows" in normalized:
            return self.input_rows
        if "from read_model.output_invoice_collection_rows" in normalized:
            return self.output_rows
        if "from read_model.oa_pending_payment_rows" in normalized:
            if "select distinct scope_key, source_versions" in normalized:
                rows: list[dict] = []
                for row in self.oa_rows:
                    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                    oa_payload = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
                    rows.append(
                        {
                            "scope_key": row.get("scope_key") or oa_payload.get("month") or "2026-05",
                            "source_versions": row.get("source_versions") or oa_pending_payment_source_versions(),
                        }
                    )
                return rows
            return self._oa_rows_for_sql(normalized)
        if "from read_model.input_invoice_usage_scopes" in normalized:
            return self.input_scope_rows
        if "from read_model.output_invoice_collection_scopes" in normalized:
            return self.output_scope_rows
        if "from read_model.oa_pending_payment_scopes" in normalized:
            return self.oa_scope_rows
        if "from read_model.workbench_relation_scopes" in normalized:
            return self.workbench_relation_scope_rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-25T03:00:00+00:00"} if self.dirty else None
        if "from read_model.input_invoice_usage_scopes" in normalized:
            if not self.scope_exists:
                return None
            requested_scope = str(params[0] if params else "2026-05")
            for row in self.input_scope_rows:
                if str(row.get("scope_key")) == requested_scope:
                    return row
            return {"scope_key": requested_scope, "source_versions": input_invoice_usage_source_versions()}
        if "from read_model.output_invoice_collection_scopes" in normalized:
            if not self.scope_exists:
                return None
            requested_scope = str(params[0] if params else "2026-05")
            for row in self.output_scope_rows:
                if str(row.get("scope_key")) == requested_scope:
                    return row
            return {"scope_key": requested_scope, "source_versions": output_invoice_collection_source_versions()}
        if "from read_model.oa_pending_payment_scopes" in normalized:
            if not self.scope_exists:
                return None
            requested_scope = str(params[0] if params else "2026-05")
            for row in self.oa_scope_rows:
                if str(row.get("scope_key")) == requested_scope:
                    return row
            return {"scope_key": requested_scope, "source_versions": oa_pending_payment_source_versions()}
        if "from read_model.workbench_relation_scopes" in normalized:
            if not self.workbench_relation_scope_rows:
                return None
            requested_scope = str(params[1] if len(params) > 1 else params[0] if params else "2026-05")
            for row in self.workbench_relation_scope_rows:
                if str(row.get("scope_key")) == requested_scope:
                    return row
            return None
        if "from read_model.input_invoice_usage_rows" in normalized:
            if "select scope_key, source_versions, payload, raw_payload" in normalized:
                if not self.input_rows:
                    return None
                row = dict(self.input_rows[0])
                row.setdefault("scope_key", "2026-05")
                row.setdefault("source_versions", input_invoice_usage_source_versions())
                return row
            input_invoice_ids: set[str] = set()
            for row in self.input_rows:
                input_invoice_ids.update(self._invoice_row_ids(row))
            return {
                "count": len(self.input_rows),
                "invoice_count": len(input_invoice_ids),
                "total_with_tax": "118.00",
                "matched_oa_count": 1,
                "matched_bank_transaction_count": 1,
                "pending_count": 0,
            }
        if "from read_model.output_invoice_collection_rows" in normalized:
            output_invoice_ids: set[str] = set()
            for row in self.output_rows:
                output_invoice_ids.update(self._invoice_row_ids(row))
            return {
                "count": len(self.output_rows),
                "invoice_count": len(output_invoice_ids),
                "total_with_tax": "118.00",
                "collected_amount": "118.00",
                "pending_amount": "0.00",
                "pending_collection_count": 0,
                "partial_collection_count": 0,
                "receipt_pending_count": 1,
            }
        if "from read_model.oa_pending_payment_rows" in normalized:
            if "select scope_key, source_versions, payload, raw_payload" in normalized:
                if not self.oa_rows:
                    return None
                row = dict(self.oa_rows[0])
                row.setdefault("scope_key", "2026-05")
                row.setdefault("source_versions", oa_pending_payment_source_versions())
                return row
            if "completed_count" in normalized or "in_progress_count" in normalized:
                completed_oa_ids: set[str] = set()
                in_progress_oa_ids: set[str] = set()
                for row in self._oa_rows_for_sql(normalized):
                    payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
                    oa_payload = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
                    workflow_status = str(oa_payload.get("workflowStatus") or row.get("oa_workflow_status") or "")
                    if workflow_status == "in_progress":
                        in_progress_oa_ids.update(self._oa_row_ids(row))
                    else:
                        completed_oa_ids.update(self._oa_row_ids(row))
                return {
                    "completed_count": len(completed_oa_ids),
                    "in_progress_count": len(in_progress_oa_ids),
                }
            rows = self._oa_rows_for_sql(normalized)
            return {
                "count": len(rows),
                "oa_amount_total": str(sum((self._oa_row_decimal(row, "oa", "amount") for row in rows), Decimal("0"))),
                "bank_paid_total": str(
                    sum(
                        (
                            self._oa_row_decimal(row, "bankTransaction", "paidTotal")
                            or self._oa_row_decimal(row, "bankTransaction", "amount")
                            for row in rows
                        ),
                        Decimal("0"),
                    )
                ),
            }
        return None

    def _oa_rows_for_sql(self, normalized_sql: str) -> list[dict]:
        rows = list(self.oa_rows)
        if "deduped_oa_pending_payment_rows" not in normalized_sql:
            return rows
        rows_by_id: dict[str, dict] = {}
        for row in rows:
            row_id = self._oa_row_id(row)
            if row_id:
                rows_by_id[row_id] = row
        rows = list(rows_by_id.values())
        if "completed_count" in normalized_sql or "in_progress_count" in normalized_sql:
            return rows
        if "oa_workflow_status = 'in_progress'" in normalized_sql:
            return [row for row in rows if self._oa_workflow_status(row) == "in_progress"]
        if (
            "oa_workflow_status is null or oa_workflow_status = '' or oa_workflow_status = 'completed'"
            in normalized_sql
        ):
            return [row for row in rows if self._oa_workflow_status(row) != "in_progress"]
        return rows

    @staticmethod
    def _oa_row_id(row: dict) -> str:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        return str(row.get("row_id") or payload.get("id") or "").strip()

    @staticmethod
    def _oa_row_decimal(row: dict, section: str, key: str) -> Decimal:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        section_payload = payload.get(section) if isinstance(payload.get(section), dict) else {}
        try:
            return Decimal(str(section_payload.get(key) or "0"))
        except Exception:
            return Decimal("0")

    @staticmethod
    def _oa_row_ids(row: dict) -> set[str]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        oa_payload = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
        ids: set[str] = set()
        for summary in list(oa_payload.get("summaries") or []):
            if isinstance(summary, dict):
                oa_id = str(summary.get("oaId") or summary.get("id") or "").strip()
                if oa_id:
                    ids.add(oa_id)
        fallback_id = str(oa_payload.get("id") or row.get("oa_id") or "").strip()
        if fallback_id:
            ids.add(fallback_id)
        return ids

    @staticmethod
    def _invoice_row_ids(row: dict) -> set[str]:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        invoice_payload = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
        relation_payload = payload.get("invoiceRelations") if isinstance(payload.get("invoiceRelations"), dict) else {}
        ids: set[str] = set()
        for summary in list(relation_payload.get("summaries") or []):
            if isinstance(summary, dict):
                invoice_id = str(
                    summary.get("invoiceId")
                    or summary.get("id")
                    or summary.get("primaryInvoiceId")
                    or summary.get("relatedInvoiceId")
                    or ""
                ).strip()
                if invoice_id:
                    ids.add(invoice_id)
        fallback_id = str(invoice_payload.get("id") or row.get("invoice_id") or payload.get("invoiceId") or "").strip()
        if fallback_id:
            ids.add(fallback_id)
        return ids

    @staticmethod
    def _oa_workflow_status(row: dict) -> str:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        oa_payload = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
        return str(oa_payload.get("workflowStatus") or row.get("oa_workflow_status") or "")


class ProjectionCoreRepository:
    def __init__(
        self,
        *,
        invoices: list[Invoice] | None = None,
        transactions: list[BankTransaction] | None = None,
    ) -> None:
        self.invoices = list(invoices or [])
        self.transactions = list(transactions or [])
        self.invoice_page_calls: list[dict[str, object]] = []

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        **_kwargs: object,
    ) -> tuple[list[Invoice], int]:
        self.invoice_page_calls.append(
            {"page": page, "page_size": page_size, "month": month, "invoice_type": invoice_type}
        )
        rows = list(self.invoices)
        if month:
            rows = [invoice for invoice in rows if str(invoice.invoice_date or "").startswith(month[:7])]
        if invoice_type:
            rows = [invoice for invoice in rows if invoice.invoice_type.value == invoice_type]
        offset = (page - 1) * page_size
        return rows[offset : offset + page_size], len(rows)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **_kwargs: object,
    ) -> tuple[list[BankTransaction], int]:
        offset = (page - 1) * page_size
        return self.transactions[offset : offset + page_size], len(self.transactions)


class EmptyWorkbenchRepository:
    def load_workbench_pair_relations(self) -> dict[str, object]:
        return {"pair_relations": {}}


class EmptyOAProjectionRepository:
    def list_application_records_by_row_ids(self, _row_ids: list[str]) -> list[object]:
        return []

    def list_all_application_records(self) -> list[object]:
        return []


class StaticOAProjectionRepository:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = list(records)
        self.list_all_calls = 0
        self.list_month_calls: list[str] = []

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[object]:
        wanted = {str(row_id) for row_id in list(row_ids or [])}
        return [record for record in self.records if record.id in wanted]

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        self.list_month_calls.append(str(month))
        if str(month or "").strip() == "all":
            return self.list_all_application_records()
        return [record for record in self.records if str(record.month or "").startswith(str(month)[:7])]

    def list_all_application_records(self) -> list[object]:
        self.list_all_calls += 1
        return list(self.records)

    def list_available_months(self) -> list[str]:
        return sorted({record.month for record in self.records}, reverse=True)


class RefreshingOAProjectionRepository(StaticOAProjectionRepository):
    def get_read_status(self) -> OAReadStatus:
        return OAReadStatus(code="refreshing", message="OA projection refreshing")


class StaticOAPaymentStatusRepository:
    def __init__(self, *, flow_ids: dict[str, str], admitted_flow_ids: set[str]) -> None:
        self.flow_ids = dict(flow_ids)
        self.admitted_flow_ids = set(admitted_flow_ids)
        self.list_statuses_calls = 0
        self.get_payment_status_calls = 0

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        self.list_statuses_calls += 1
        return {
            flow_id: OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PENDING)
            for flow_id in self.admitted_flow_ids
        }

    def resolve_flow_id(self, record: OAApplicationRecord) -> str | None:
        return self.flow_ids.get(record.id)

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        self.get_payment_status_calls += 1
        return self.list_payment_statuses().get(flow_id)

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PENDING)


class RecordingInvoiceRelationReadRepository:
    def __init__(self) -> None:
        self.saved_input: dict[str, object] | None = None
        self.saved_output: dict[str, object] | None = None
        self.saved_oa: dict[str, object] | None = None
        self.marked_input: dict[str, object] | None = None
        self.marked_output: dict[str, object] | None = None
        self.marked_oa: dict[str, object] | None = None
        self.pruned_input: list[str] | None = None
        self.pruned_output: list[str] | None = None
        self.pruned_oa: list[str] | None = None
        self.workbench_relation_versions_by_scope: dict[str, dict[str, object]] = {}
        self.existing_source_versions_by_method: dict[str, dict[str, object]] = {}
        self.existing_row_count_by_method: dict[str, int] = {}

    def _existing_payload(self, method_name: str) -> dict[str, object] | None:
        source_versions = self.existing_source_versions_by_method.get(method_name)
        if source_versions is None:
            return None
        return {
            "rows": [{"row_id": "existing-row"}],
            "pagination": {
                "page": 1,
                "pageSize": 1,
                "total": self.existing_row_count_by_method.get(method_name, 1),
            },
            "source_versions": dict(source_versions),
            "refresh_status": "refreshing",
        }

    def list_input_invoice_usage_rows(self, **_kwargs: object) -> dict[str, object] | None:
        return self._existing_payload("list_input_invoice_usage_rows")

    def list_output_invoice_collection_rows(self, **_kwargs: object) -> dict[str, object] | None:
        return self._existing_payload("list_output_invoice_collection_rows")

    def list_oa_pending_payment_rows(self, **_kwargs: object) -> dict[str, object] | None:
        return self._existing_payload("list_oa_pending_payment_rows")

    def save_input_invoice_usage_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_input = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def save_output_invoice_collection_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_output = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def mark_input_invoice_usage_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_input = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}

    def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
        self.pruned_input = list(current_scope_keys)

    def mark_output_invoice_collection_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_output = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}

    def prune_output_invoice_collection_scope_shards(self, current_scope_keys: list[str]) -> None:
        self.pruned_output = list(current_scope_keys)

    def save_oa_pending_payment_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_oa = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def mark_oa_pending_payment_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_oa = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}

    def prune_oa_pending_payment_scope_shards(self, current_scope_keys: list[str]) -> None:
        self.pruned_oa = list(current_scope_keys)

    def workbench_relation_source_versions(self, *, scope_key: str, tenant_id: str = "default") -> dict[str, object]:
        _ = tenant_id
        return dict(self.workbench_relation_versions_by_scope.get(str(scope_key), {}))


class WriteRecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []
        self.executed_many: list[tuple[str, list[object]]] = []

    def execute(self, sql: str, params: object = ()) -> None:
        self.executed.append((" ".join(sql.lower().split()), params))

    def execute_many(self, sql: str, params_seq: list[object]) -> int:
        self.executed_many.append((" ".join(sql.lower().split()), list(params_seq)))
        return len(params_seq)


class OaPendingRelationCleanupConnection(EmptyTransactionConnection):
    def __init__(self) -> None:
        self.relations: dict[str, dict[str, object]] = {
            "rel-missing-admission": {
                "relation_id": "rel-missing-admission",
                "status": "active",
                "version": 1,
                "scope_month": "2026-05-01",
                "oa_row_ids": ["oa-pay-missing-admission"],
                "bank_transaction_ids": ["bank-missing-admission"],
                "source_action": "link_bank_transactions",
                "note": None,
                "amount_check": {},
                "writeback_status": {},
                "migrated_from_workbench_case_id": None,
                "promoted_workbench_case_id": None,
                "created_by": "system",
                "created_at": "2026-06-22T00:00:00+08:00",
                "updated_at": "2026-06-22T00:00:00+08:00",
                "raw_payload": {
                    "normalized_payload": {
                        "relation_id": "rel-missing-admission",
                        "status": "active",
                        "month_scope": "2026-05",
                        "oa_row_ids": ["oa-pay-missing-admission"],
                        "bank_transaction_ids": ["bank-missing-admission"],
                    }
                },
            }
        }
        self.claims: dict[str, dict[str, object]] = {
            "bank-missing-admission": {
                "bank_transaction_id": "bank-missing-admission",
                "owner_type": "oa_pending_payment_relation",
                "owner_id": "rel-missing-admission",
                "status": "active",
            }
        }
        self.executed: list[tuple[str, object]] = []

    def fetch_all(self, sql: str, params: object = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.oa_pending_payment_bank_relations" not in normalized:
            return []
        rows = [dict(relation) for relation in self.relations.values() if relation.get("status") == "active"]
        if "scope_month = %s::date" in normalized:
            admitted = {
                str(row_id) for row_id in list(params[1] if isinstance(params, tuple) and len(params) > 1 else [])
            }
            return [
                row
                for row in rows
                if str(row.get("scope_month", ""))[:7] == "2026-05"
                and not ({str(row_id) for row_id in list(row.get("oa_row_ids") or [])} & admitted)
            ]
        if "oa_row_ids && %s or bank_transaction_ids && %s" in normalized:
            wanted = {str(row_id) for row_id in list(params[0] if isinstance(params, tuple) and params else [])}
            return [
                row
                for row in rows
                if ({str(row_id) for row_id in list(row.get("oa_row_ids") or [])} & wanted)
                or ({str(row_id) for row_id in list(row.get("bank_transaction_ids") or [])} & wanted)
            ]
        return []

    def fetch_one(self, sql: str, params: object = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "update app.oa_pending_payment_bank_relations" not in normalized:
            return None
        reason, actor, relation_id = params
        relation = dict(self.relations[str(relation_id)])
        relation["status"] = "cancelled"
        relation["version"] = int(relation["version"]) + 1
        relation["raw_payload"] = {
            "normalized_payload": {
                **dict(relation.get("raw_payload", {}).get("normalized_payload", {})),
                "status": "cancelled",
                "cancellation_reason": str(reason),
                "cancelled_by": str(actor),
            }
        }
        self.relations[str(relation_id)] = relation
        return dict(relation)

    def execute(self, sql: str, params: object = ()) -> None:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if "update app.bank_transaction_relation_claims" in normalized:
            actor, reason, relation_id = params
            for claim in self.claims.values():
                if claim.get("owner_id") == relation_id and claim.get("status") == "active":
                    claim["status"] = "released"
                    claim["released_by"] = actor
                    claim["release_reason"] = reason


class InputInvoiceUsageReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Underlying:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []

            def list_input_invoice_usage_rows(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("list_input_invoice_usage_rows", dict(kwargs)))
                return {"rows": [{"id": "input-1"}], "refresh_status": "fresh"}

            def list_input_invoice_usage_filter_options(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("list_input_invoice_usage_filter_options", dict(kwargs)))
                return {
                    "options": {"payment_status": [{"value": "pending", "label": "待处理", "count": 1}]},
                    "refresh_status": "fresh",
                }

            def save_input_invoice_usage_rows(self, **kwargs: object) -> None:
                self.calls.append(("save_input_invoice_usage_rows", dict(kwargs)))

            def mark_input_invoice_usage_scope(self, **kwargs: object) -> None:
                self.calls.append(("mark_input_invoice_usage_scope", dict(kwargs)))

            def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
                self.calls.append(("prune_input_invoice_usage_scope_shards", list(current_scope_keys)))

            def get_input_invoice_usage_row_by_row_id(self, row_id: str) -> dict[str, object]:
                self.calls.append(("get_input_invoice_usage_row_by_row_id", row_id))
                return {"row": {"id": row_id}, "refresh_status": "fresh"}

            def list_input_invoice_usage_rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, object]:
                self.calls.append(("list_input_invoice_usage_rows_by_invoice_ids", list(invoice_ids)))
                return {"rows": [{"invoiceId": invoice_ids[0]}], "refresh_status": "fresh"}

            def list_output_invoice_collection_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("input invoice usage port must not expose output collection reads")

            def list_oa_pending_payment_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("input invoice usage port must not expose OA pending payment reads")

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("input invoice usage port must not expose pending invoice reads")

        underlying = Underlying()
        port = InputInvoiceUsageReadModelRepositoryPort(underlying)

        self.assertEqual(
            port.list_input_invoice_usage_rows(month="2026-05", page=1, page_size=50)["rows"][0]["id"],
            "input-1",
        )
        self.assertEqual(
            port.get_input_invoice_usage_row_by_row_id("input-1")["row"]["id"],
            "input-1",
        )
        self.assertEqual(
            port.list_input_invoice_usage_rows_by_invoice_ids(["invoice-1"])["rows"][0]["invoiceId"],
            "invoice-1",
        )
        self.assertEqual(
            port.list_input_invoice_usage_filter_options(month="2026-05")["options"]["payment_status"][0]["label"],
            "待处理",
        )
        port.save_input_invoice_usage_rows(
            scope_key="2026-05",
            rows=[{"id": "input-1"}],
            source_versions={"schema": "v1"},
        )
        port.mark_input_invoice_usage_scope(
            scope_key="2026-05",
            row_count=1,
            source_versions={"schema": "v1"},
        )
        port.prune_input_invoice_usage_scope_shards(["2026-05"])

        self.assertFalse(hasattr(port, "list_output_invoice_collection_rows"))
        self.assertFalse(hasattr(port, "list_oa_pending_payment_rows"))
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "list_input_invoice_usage_rows",
                "get_input_invoice_usage_row_by_row_id",
                "list_input_invoice_usage_rows_by_invoice_ids",
                "list_input_invoice_usage_filter_options",
                "save_input_invoice_usage_rows",
                "mark_input_invoice_usage_scope",
                "prune_input_invoice_usage_scope_shards",
            ],
        )


class OutputInvoiceCollectionReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Underlying:
            def __init__(self) -> None:
                self.calls: list[tuple[str, object]] = []

            def list_output_invoice_collection_rows(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(("list_output_invoice_collection_rows", dict(kwargs)))
                return {"rows": [{"id": "output-1"}], "refresh_status": "fresh"}

            def get_output_invoice_collection_row_by_row_id(self, row_id: str) -> dict[str, object]:
                self.calls.append(("get_output_invoice_collection_row_by_row_id", row_id))
                return {"row": {"id": row_id}, "refresh_status": "fresh"}

            def save_output_invoice_collection_rows(self, **kwargs: object) -> None:
                self.calls.append(("save_output_invoice_collection_rows", dict(kwargs)))

            def mark_output_invoice_collection_scope(self, **kwargs: object) -> None:
                self.calls.append(("mark_output_invoice_collection_scope", dict(kwargs)))

            def prune_output_invoice_collection_scope_shards(self, current_scope_keys: list[str]) -> None:
                self.calls.append(("prune_output_invoice_collection_scope_shards", list(current_scope_keys)))

            def list_input_invoice_usage_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("output collection port must not expose input usage reads")

            def list_oa_pending_payment_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("output collection port must not expose OA pending payment reads")

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("output collection port must not expose pending invoice reads")

            def workbench_relation_source_versions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("output collection port must not expose workbench relation source versions")

        underlying = Underlying()
        port = OutputInvoiceCollectionReadModelRepositoryPort(underlying)

        self.assertEqual(
            port.list_output_invoice_collection_rows(month="2026-05", page=1, page_size=50)["rows"][0]["id"],
            "output-1",
        )
        self.assertEqual(
            port.get_output_invoice_collection_row_by_row_id("output-1")["row"]["id"],
            "output-1",
        )
        port.save_output_invoice_collection_rows(
            scope_key="2026-05",
            rows=[{"id": "output-1"}],
            source_versions={"schema": "v1"},
        )
        port.mark_output_invoice_collection_scope(
            scope_key="2026-05",
            row_count=1,
            source_versions={"schema": "v1"},
        )
        port.prune_output_invoice_collection_scope_shards(["2026-05"])

        self.assertFalse(hasattr(port, "list_input_invoice_usage_rows"))
        self.assertFalse(hasattr(port, "list_oa_pending_payment_rows"))
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertFalse(hasattr(port, "workbench_relation_source_versions"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "list_output_invoice_collection_rows",
                "get_output_invoice_collection_row_by_row_id",
                "save_output_invoice_collection_rows",
                "mark_output_invoice_collection_scope",
                "prune_output_invoice_collection_scope_shards",
            ],
        )


class InvoiceUsageCollectionSqlRuntimeTests(unittest.TestCase):
    def test_input_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(input_rows=[], dirty=False, scope_exists=True)
        )

        payload = repository.list_input_invoice_usage_rows(month="2026-05", page=1, page_size=50)

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

    def test_input_repository_uses_native_bank_account_and_direction_columns(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_rows(
            month="2026-05",
            filters='[{"field":"bank_account","operator":"in","values":["交通银行 3847"]},{"field":"bank_direction","operator":"in","values":["outflow"]}]',
            sort_field="bank_account",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("bank_account", executed_sql)
        self.assertIn("bank_direction", executed_sql)
        self.assertIn("bank_account asc", executed_sql)

    def test_input_repository_summary_counts_relation_invoice_members_not_rows(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "payload": {
                        "id": "input_invoice_usage_grouped_row_1",
                        "invoiceId": "invoice-primary",
                        "invoice": {"id": "invoice-primary", "invoiceNo": "1001", "totalWithTax": "300.00"},
                        "invoiceRelations": {
                            "summaries": [
                                {"invoiceId": "invoice-primary"},
                                {"invoiceId": "invoice-related-a"},
                                {"invoiceId": "invoice-related-b"},
                            ],
                        },
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_rows(month="2026-05", page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["invoiceCount"], 3)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("invoice_count_ids", executed_sql)

    def test_input_repository_filter_options_use_sql_aggregation_without_payload_rows(self) -> None:
        class FilterOptionConnection:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple]] = []
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from job.read_model_dirty_scopes" in normalized:
                    return None
                if "from read_model.input_invoice_usage_scopes" in normalized:
                    return {"scope_key": "2026-05", "source_versions": input_invoice_usage_source_versions()}
                return None

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                assert "cross join lateral" in normalized
                assert "payment_status_label" in normalized
                assert "select payload, raw_payload" not in normalized
                return [
                    {"field": "payment_status", "value": "pending", "label": "待处理", "option_count": 2},
                    {"field": "bank_direction", "value": "outflow", "label": "outflow", "option_count": 2},
                ]

        connection = FilterOptionConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_filter_options(month="2026-05")

        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual(payload["options"]["payment_status"], [{"value": "pending", "label": "待处理", "count": 2}])
        self.assertEqual(payload["options"]["bank_direction"], [{"value": "outflow", "label": "支出", "count": 2}])
        self.assertEqual(connection.fetch_all_calls[0][1], ("2026-05",))

    def test_input_repository_save_persists_bank_account_and_direction_columns(self) -> None:
        connection = WriteRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_input_invoice_usage_rows(
            scope_key="2026-05",
            rows=[
                {
                    "id": "input_invoice_usage_row_1",
                    "invoiceId": "invoice-1",
                    "invoice": {"invoiceNo": "1001", "invoiceDate": "2026-05-21", "totalWithTax": "118.00"},
                    "paymentStatus": {"code": "pending", "label": "待处理"},
                    "oa": {"relationCount": 1},
                    "bankTransactions": {
                        "primaryBankTransactionId": "bank-1",
                        "tradeTime": "2026-05-21 10:00:00",
                        "amount": "118.00",
                        "direction": "outflow",
                        "directionLabel": "支出",
                        "bankName": "交通银行",
                        "accountLast4": "3847",
                        "bankAccount": "交通银行 3847",
                        "relationCount": 1,
                    },
                }
            ],
            source_versions=input_invoice_usage_source_versions(),
        )

        insert_calls = [
            (sql, params_seq)
            for sql, params_seq in connection.executed_many
            if "insert into read_model.input_invoice_usage_rows" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        sql, params_seq = insert_calls[0]
        params = params_seq[0]
        self.assertIn("bank_account", sql)
        self.assertIn("bank_direction", sql)
        self.assertEqual(params["bank_account"], "交通银行 3847")
        self.assertEqual(params["bank_direction"], "outflow")

    def test_input_repository_prunes_orphan_scope_shards(self) -> None:
        connection = InvoiceReadModelConnection()
        repository = PostgresReadModelRepository(connection)

        repository.prune_input_invoice_usage_scope_shards(["2026-06", "2026-06", "not-a-month", ""])

        self.assertEqual(
            connection.executed,
            [
                (
                    "delete from read_model.input_invoice_usage_rows where scope_key <> 'all' and scope_key not in (%s)",
                    ("2026-06",),
                ),
                (
                    "delete from read_model.input_invoice_usage_scopes where scope_key <> 'all' and scope_key not in (%s)",
                    ("2026-06",),
                ),
            ],
        )

    def test_input_repository_all_scope_keeps_base_source_versions_when_relation_versions_differ(self) -> None:
        base_versions = input_invoice_usage_source_versions()
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ],
            input_scope_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": {
                        **base_versions,
                        "workbench_relation_source_versions": {
                            "workbench_pair_relations_updated_at": "2026-06-10 01:39:49+08",
                            "workbench_reconciliation_decisions_updated_at": "2026-06-10 03:06:22+08",
                        },
                    },
                    "cache_status": "fresh",
                },
                {
                    "scope_key": "2026-04",
                    "source_versions": {
                        **base_versions,
                        "workbench_relation_source_versions": {
                            "workbench_pair_relations_updated_at": "2026-06-10 09:58:40+08",
                            "workbench_reconciliation_decisions_updated_at": "2026-06-10 09:13:13+08",
                        },
                    },
                    "cache_status": "fresh",
                },
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_rows(month=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["source_versions"], base_versions)

    def test_output_repository_uses_native_columns_for_filters_and_sort(self) -> None:
        connection = InvoiceReadModelConnection(
            output_rows=[
                {
                    "payload": {
                        "id": "output_invoice_collection_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "collectionStatus": {
                            "code": "collected",
                            "label": "已收款",
                            "collectedAmount": "118.00",
                            "pendingAmount": "0.00",
                        },
                        "bankTransactions": {"relationCount": 1},
                        "redInvoiceRelation": {"relationCount": 0},
                        "receipt": {"status": "pending", "label": "待出收据"},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_output_invoice_collection_rows(
            month="2026-05",
            filters='[{"field":"collection_status","operator":"in","values":["collected"]}]',
            sort_field="buyer_name",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("collection_status", executed_sql)
        self.assertIn("buyer_name asc", executed_sql)

    def test_output_repository_summary_counts_relation_invoice_members_not_rows(self) -> None:
        connection = InvoiceReadModelConnection(
            output_rows=[
                {
                    "payload": {
                        "id": "output_invoice_collection_grouped_row_1",
                        "invoiceId": "output-primary",
                        "invoice": {"id": "output-primary", "invoiceNo": "1001", "totalWithTax": "300.00"},
                        "invoiceRelations": {
                            "summaries": [
                                {"relatedInvoiceId": "output-primary"},
                                {"relatedInvoiceId": "output-related-a"},
                                {"relatedInvoiceId": "output-related-b"},
                            ],
                        },
                        "collectionStatus": {
                            "code": "collected",
                            "label": "已收款",
                            "collectedAmount": "300.00",
                            "pendingAmount": "0.00",
                        },
                        "bankTransactions": {"relationCount": 1},
                        "redInvoiceRelation": {"relationCount": 0},
                        "receipt": {"status": "pending", "label": "待出收据"},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_output_invoice_collection_rows(month="2026-05", page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["invoiceCount"], 3)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("invoice_count_ids", executed_sql)

    def test_output_repository_save_persists_oa_relation_columns(self) -> None:
        connection = WriteRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_output_invoice_collection_rows(
            scope_key="2026-05",
            rows=[
                {
                    "id": "output_invoice_collection_row_1",
                    "invoiceId": "invoice-1",
                    "invoice": {"invoiceNo": "9001", "invoiceDate": "2026-05-08", "totalWithTax": "118.00"},
                    "collectionStatus": {
                        "code": "pending_collection",
                        "label": "待收款",
                        "collectedAmount": "0.00",
                        "pendingAmount": "118.00",
                    },
                    "oa": {
                        "applicantName": "张三",
                        "applicationType": "付款申请",
                        "projectName": "项目A",
                        "relationCount": 2,
                    },
                    "bankTransactions": {"relationCount": 1},
                    "invoiceRelations": {"relationCount": 2},
                    "redInvoiceRelation": {"relationCount": 0},
                    "receipt": {"status": "pending", "label": "待出收据"},
                }
            ],
            source_versions=output_invoice_collection_source_versions(),
        )

        insert_calls = [
            (sql, params_seq)
            for sql, params_seq in connection.executed_many
            if "insert into read_model.output_invoice_collection_rows" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        sql, params_seq = insert_calls[0]
        params = params_seq[0]
        self.assertIn("oa_relation_count", sql)
        self.assertEqual(params["oa_applicant"], "张三")
        self.assertEqual(params["oa_application_type"], "付款申请")
        self.assertEqual(params["oa_project_name"], "项目A")
        self.assertEqual(params["oa_relation_count"], 2)

    def test_oa_repository_uses_native_columns_for_filters_sort_and_bank_total_summary(self) -> None:
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {
                            "id": "oa-1",
                            "applicantName": "张三",
                            "amount": "100.00",
                            "workflowStatus": "in_progress",
                        },
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"paidTotal": "100.00"},
                        "invoice": {},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(
            month="2026-05",
            filters='[{"field":"payment_status","operator":"in","values":["paid"]}]',
            sort_field="bank_trade_time",
            sort_direction="desc",
            view_mode="in_progress",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["bankPaidTotal"], "100.00")
        self.assertEqual(payload["summary"]["viewCounts"], {"completed": 0, "in_progress": 1})
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("payment_status", executed_sql)
        self.assertIn("oa_workflow_status = 'in_progress'", executed_sql)
        self.assertIn("bank_trade_time desc", executed_sql)

    def test_oa_repository_all_scope_aggregates_monthly_scope_source_versions(self) -> None:
        source_versions = oa_pending_payment_source_versions()
        stale_source_versions = {
            **source_versions,
            "oa_pending_payment_source_version": "oa-pending-payment:v1",
            "oa_projection_sync_version": "2026-05-28-scope-replace-v1",
        }
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": source_versions,
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00"},
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"paidTotal": "100.00"},
                        "invoice": {},
                    },
                    "raw_payload": {},
                }
            ],
            oa_scope_rows=[
                {"scope_key": "2026-05", "source_versions": source_versions, "cache_status": "fresh"},
                {"scope_key": "2026-04", "source_versions": source_versions, "cache_status": "fresh"},
                {"scope_key": "2025-09", "source_versions": stale_source_versions, "cache_status": "fresh"},
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(month=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["source_versions"], source_versions)
        self.assertEqual(payload["pagination"]["total"], 1)
        executed_scope_fetches = [
            sql for sql, _params in connection.fetch_all_calls if "from read_model.oa_pending_payment_scopes" in sql
        ]
        self.assertTrue(executed_scope_fetches)

    def test_oa_repository_all_scope_dedupes_cross_scope_relation_rows(self) -> None:
        source_versions = oa_pending_payment_source_versions()
        duplicate_payload = {
            "id": "oa_pending_payment_relation_cross_month",
            "oa": {
                "id": "oa-pay-2073",
                "applicantName": "樊祖芳",
                "amount": "270000.00",
                "workflowStatus": "completed",
                "summaries": [
                    {"oaId": "oa-pay-2073"},
                    {"oaId": "oa-pay-2214"},
                    {"oaId": "oa-pay-2181"},
                ],
            },
            "paymentStatus": {"code": "paid", "label": "已支付"},
            "bankTransaction": {"paidTotal": "270000.00", "tradeTime": "2026-05-25 15:00:03"},
            "invoice": {"primaryInvoiceId": "inv-0276"},
        }
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "row_id": "oa_pending_payment_relation_cross_month",
                    "scope_key": "2026-04",
                    "source_versions": source_versions,
                    "payload": duplicate_payload,
                    "raw_payload": {},
                },
                {
                    "row_id": "oa_pending_payment_relation_cross_month",
                    "scope_key": "2026-05",
                    "source_versions": source_versions,
                    "payload": duplicate_payload,
                    "raw_payload": {},
                },
            ],
            oa_scope_rows=[
                {"scope_key": "2026-04", "source_versions": source_versions, "cache_status": "fresh"},
                {"scope_key": "2026-05", "source_versions": source_versions, "cache_status": "fresh"},
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(month=None, page=1, page_size=50, view_mode="completed")

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["rowCount"], 1)
        self.assertEqual(payload["summary"]["oaAmountTotal"], "270000.00")
        self.assertEqual(payload["summary"]["bankPaidTotal"], "270000.00")
        self.assertEqual(payload["summary"]["viewCounts"], {"completed": 3, "in_progress": 0})
        self.assertEqual([row["id"] for row in payload["rows"]], ["oa_pending_payment_relation_cross_month"])
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("deduped_oa_pending_payment_rows", executed_sql)

    def test_oa_repository_save_persists_source_versions_and_bank_total(self) -> None:
        connection = WriteRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_oa_pending_payment_rows(
            scope_key="2026-05",
            rows=[
                {
                    "id": "oa_pending_payment_row_1",
                    "oa": {
                        "id": "oa-1",
                        "applicantName": "张三",
                        "amount": "100.00",
                        "month": "2026-05",
                        "workflowStatus": "in_progress",
                    },
                    "paymentStatus": {"code": "paid", "label": "已支付"},
                    "bankTransaction": {
                        "primaryBankTransactionId": "bank-1",
                        "tradeTime": "2026-05-21 10:00:00",
                        "amount": "40.00",
                        "paidTotal": "100.00",
                    },
                    "invoice": {},
                }
            ],
            source_versions=oa_pending_payment_source_versions(),
        )

        insert_calls = [
            (sql, params_seq)
            for sql, params_seq in connection.executed_many
            if "insert into read_model.oa_pending_payment_rows" in sql
        ]
        self.assertEqual(len(insert_calls), 1)
        sql, params_seq = insert_calls[0]
        params = params_seq[0]
        self.assertIn("bank_paid_total", sql)
        self.assertIn("oa_workflow_status", sql)
        self.assertEqual(params["oa_workflow_status"], "in_progress")
        self.assertEqual(params["bank_paid_total"], "100.00")
        self.assertEqual(params["source_versions"].obj, oa_pending_payment_source_versions())

    def test_oa_repository_detail_lookups_use_native_columns(self) -> None:
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": oa_pending_payment_source_versions(),
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00"},
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"primaryBankTransactionId": "bank-1", "paidTotal": "100.00"},
                        "invoice": {"primaryInvoiceId": "inv-1"},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        oa_payload = repository.get_oa_pending_payment_row_by_oa_id("oa-1")
        bank_payload = repository.get_oa_pending_payment_row_by_bank_transaction_id("bank-1")
        invoice_payload = repository.get_oa_pending_payment_row_by_invoice_id("inv-1")
        row_payload = repository.get_oa_pending_payment_row_by_row_id("oa_pending_payment_row_1")

        self.assertEqual(oa_payload["row"]["oa"]["id"], "oa-1")
        self.assertEqual(bank_payload["row"]["bankTransaction"]["primaryBankTransactionId"], "bank-1")
        self.assertEqual(invoice_payload["row"]["invoice"]["primaryInvoiceId"], "inv-1")
        self.assertEqual(row_payload["row"]["id"], "oa_pending_payment_row_1")
        executed_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertIn("oa_id = %s", executed_sql)
        self.assertIn("bank_transaction_id = %s", executed_sql)
        self.assertIn("invoice_id = %s", executed_sql)
        self.assertIn("row_id = %s", executed_sql)

    def test_input_repository_detail_lookup_uses_row_id_native_column(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": input_invoice_usage_source_versions(),
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "input-invoice-1",
                        "oa": {"relationCount": 2},
                        "bankTransactions": {"relationCount": 1},
                        "invoiceRelations": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        row_payload = repository.get_input_invoice_usage_row_by_row_id("input_invoice_usage_row_1")

        self.assertEqual(row_payload["row"]["id"], "input_invoice_usage_row_1")
        self.assertEqual(row_payload["refresh_status"], "fresh")
        self.assertEqual(row_payload["source_versions"], input_invoice_usage_source_versions())
        executed_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertIn("from read_model.input_invoice_usage_rows", executed_sql)
        self.assertIn("row_id = %s", executed_sql)

    def test_input_repository_invoice_id_lookup_uses_native_column(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "scope_key": "2026-05",
                    "invoice_id": "input-invoice-1",
                    "source_versions": input_invoice_usage_source_versions(),
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "input-invoice-1",
                        "invoice": {"invoiceNo": "1001"},
                        "oa": {"relationCount": 0},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        row_payload = repository.list_input_invoice_usage_rows_by_invoice_ids(["input-invoice-1", "missing-invoice"])

        self.assertEqual(row_payload["rows"][0]["invoiceId"], "input-invoice-1")
        self.assertEqual(row_payload["missing_invoice_ids"], ["missing-invoice"])
        self.assertEqual(row_payload["refresh_status"], "fresh")
        self.assertEqual(
            row_payload["source_versions_by_scope"],
            {"2026-05": input_invoice_usage_source_versions(), "all": input_invoice_usage_source_versions()},
        )
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("from read_model.input_invoice_usage_rows", executed_sql)
        self.assertIn("invoice_id = any(%s)", executed_sql)

    def test_input_repository_invoice_id_lookup_matches_relation_member_invoice_ids(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "scope_key": "2026-05",
                    "invoice_id": "input-invoice-primary",
                    "source_versions": input_invoice_usage_source_versions(),
                    "payload": {
                        "id": "input_invoice_usage_row_grouped",
                        "invoiceId": "input-invoice-primary",
                        "invoice": {"invoiceNo": "1001"},
                        "invoiceRelations": {
                            "summaries": [
                                {"invoiceId": "input-invoice-primary"},
                                {"invoiceId": "input-invoice-secondary"},
                            ]
                        },
                        "oa": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        row_payload = repository.list_input_invoice_usage_rows_by_invoice_ids(["input-invoice-secondary"])

        self.assertEqual(row_payload["rows"][0]["id"], "input_invoice_usage_row_grouped")
        self.assertEqual(row_payload["missing_invoice_ids"], [])
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("jsonb_array_elements", executed_sql)
        self.assertIn("invoice_id = any(%s)", executed_sql)

    def test_input_api_miss_enqueues_refresh_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None),
            import_service=ImportNormalizationService(),
        )
        app._input_invoice_usage_sql_read_repository = type(
            "InputRepo",
            (),
            {"list_input_invoice_usage_rows": lambda *_args, **_kwargs: None},
        )()
        app._input_invoice_usage_query_service = type(
            "InputService",
            (),
            {
                "list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("input API miss must not live scan")
                )
            },
        )()

        response = _input_invoice_usage_rows_response(app, {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_miss")])

    def test_input_api_requires_sql_repository_in_production_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_sql_read_repository = None
        app._input_invoice_usage_query_service = type(
            "InputService",
            (),
            {
                "list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("production input API must not live scan")
                )
            },
        )()

        response = _input_invoice_usage_rows_response(app, {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_sql_repository_unavailable")])

    def test_output_api_requires_sql_repository_in_production_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._output_invoice_collection_sql_read_repository = None

        payload = app._get_output_invoice_collection_rows_from_sql_read_model(
            {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]}
        )

        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "api_sql_repository_unavailable")])

    def test_output_api_schema_stale_enqueues_refresh_when_unified_relation_fields_missing(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        app._output_invoice_collection_sql_read_repository = type(
            "OutputRepo",
            (),
            {
                "list_output_invoice_collection_rows": lambda *_args, **_kwargs: {
                    "rows": [
                        {
                            "id": "schema-stale-row",
                            "invoice": {},
                            "collectionStatus": {},
                            "bankTransactions": {},
                            "redInvoiceRelation": {},
                            "receipt": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"invoiceCount": 1},
                    "filterConfig": [],
                    "refresh_status": "fresh",
                    "source_versions": output_invoice_collection_source_versions(),
                }
            },
        )()

        response = _output_invoice_collection_rows_response(
            app,
            {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]}
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "api_schema_stale")])

    def test_input_api_source_version_miss_enqueues_refresh_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_sql_read_repository = type(
            "InputRepo",
            (),
            {
                "list_input_invoice_usage_rows": lambda *_args, **_kwargs: {
                    "rows": [
                        {
                            "id": "stale-source-row",
                            "invoice": {},
                            "paymentStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"invoiceCount": 1},
                    "filterConfig": [],
                    "refresh_status": "fresh",
                    "source_versions": {},
                }
            },
        )()

        response = _input_invoice_usage_rows_response(app, {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("input_invoice_usage_source_version_missing", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_source_versions_stale")])

    def test_input_api_relation_source_version_mismatch_enqueues_refresh_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None),
            import_service=ImportNormalizationService(),
        )
        old_relation_versions = {"source_version": "1"}
        current_relation_versions = {"source_version": "2"}
        app._input_invoice_usage_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                input_rows=[
                    {
                        "payload": {
                            "id": "stale-relation-row",
                            "invoice": {},
                            "paymentStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                        },
                        "raw_payload": {},
                    }
                ],
                input_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "source_versions": {
                            **input_invoice_usage_source_versions(),
                            "workbench_relation_source_versions": old_relation_versions,
                        },
                        "cache_status": "fresh",
                    }
                ],
                workbench_relation_scope_rows=[
                    {"scope_key": "2026-05", "source_versions": current_relation_versions, "cache_status": "fresh"}
                ],
            )
        )

        response = _input_invoice_usage_rows_response(app, {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("workbench_relation_source_versions_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_source_versions_stale")])

    def test_input_api_all_scope_uses_rows_when_month_relation_versions_differ(self) -> None:
        base_versions = input_invoice_usage_source_versions()
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None),
            import_service=ImportNormalizationService(),
        )
        app._input_invoice_usage_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                input_rows=[
                    {
                        "payload": {
                            "id": "input_invoice_usage_row_1",
                            "invoiceId": "invoice-1",
                            "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                            "paymentStatus": {"code": "pending", "label": "待处理"},
                            "oa": {"relationCount": 1},
                            "bankTransactions": {"relationCount": 1},
                        },
                        "raw_payload": {},
                    }
                ],
                input_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "source_versions": {
                            **base_versions,
                            "workbench_relation_source_versions": {
                                "workbench_pair_relations_updated_at": "2026-06-10 01:39:49+08",
                            },
                        },
                        "cache_status": "fresh",
                    },
                    {
                        "scope_key": "2026-04",
                        "source_versions": {
                            **base_versions,
                            "workbench_relation_source_versions": {
                                "workbench_pair_relations_updated_at": "2026-06-10 09:58:40+08",
                            },
                        },
                        "cache_status": "fresh",
                    },
                ],
                scope_exists=False,
            )
        )

        response = _input_invoice_usage_rows_response(app, {"page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], "input_invoice_usage_row_1")
        self.assertNotIn("read_model_stale_reasons", payload)
        self.assertEqual(queue.refreshes, [])

    def test_input_api_all_scope_recovers_after_orphan_scope_prune(self) -> None:
        base_versions = input_invoice_usage_source_versions()
        stale_versions = {
            **base_versions,
            "oa_projection_sync_version": "2026-06-17-workflow-status-v1",
        }
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None),
            import_service=ImportNormalizationService(),
        )
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "scope_key": "2026-06",
                    "payload": {
                        "id": "input_invoice_usage_current_row",
                        "invoiceId": "invoice-current",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ],
            input_scope_rows=[
                {"scope_key": "2026-06", "row_count": 1, "source_versions": base_versions, "cache_status": "fresh"},
                {"scope_key": "2026-05", "row_count": 1, "source_versions": stale_versions, "cache_status": "fresh"},
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)
        app._input_invoice_usage_sql_read_repository = repository

        stale_response = _input_invoice_usage_rows_response(app, {"page": ["1"], "page_size": ["50"]})
        stale_payload = json.loads(stale_response.body)

        self.assertEqual(stale_response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(stale_payload["rows"], [])
        self.assertEqual(stale_payload["read_model_status"], "refreshing")
        self.assertIn("oa_projection_sync_version_missing", stale_payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "all", "api_source_versions_stale")])

        repository.prune_input_invoice_usage_scope_shards(["2026-06"])
        fresh_response = _input_invoice_usage_rows_response(app, {"page": ["1"], "page_size": ["50"]})
        fresh_payload = json.loads(fresh_response.body)

        self.assertEqual(fresh_response.status_code, int(HTTPStatus.OK))
        self.assertEqual(fresh_payload["read_model_status"], "fresh")
        self.assertEqual(fresh_payload["read_model_scope_key"], "all")
        self.assertEqual(fresh_payload["rows"][0]["id"], "input_invoice_usage_current_row")
        self.assertNotIn("read_model_stale_reasons", fresh_payload)
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "all", "api_source_versions_stale")])

    def test_output_api_all_scope_ignores_stale_empty_month_scope_versions(self) -> None:
        base_versions = output_invoice_collection_source_versions()
        stale_versions = {
            **base_versions,
            "oa_projection_sync_version": "2026-05-28-scope-replace-v1",
        }
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        app._workbench_relation_facade = FreshEmptyWorkbenchRelationFacade()
        app._output_invoice_collection_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                output_rows=[
                    {
                        "scope_key": "2026-05",
                        "payload": {
                            "id": "output_invoice_collection_row_1",
                            "invoiceId": "invoice-1",
                            "invoice": {"invoiceNo": "9001", "invoiceDate": "2026-05-08", "totalWithTax": "118.00"},
                            "collectionStatus": {
                                "code": "pending_collection",
                                "label": "待收款",
                                "collectedAmount": "0.00",
                                "pendingAmount": "118.00",
                            },
                            "oa": {"relationCount": 0},
                            "bankTransactions": {"relationCount": 0},
                            "invoiceRelations": {"relationCount": 0},
                            "redInvoiceRelation": {"relationCount": 0},
                            "receipt": {"status": "pending", "label": "待出收据"},
                        },
                        "raw_payload": {},
                    }
                ],
                output_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "row_count": 1,
                        "source_versions": base_versions,
                        "cache_status": "fresh",
                    },
                    {
                        "scope_key": "2025-12",
                        "row_count": 0,
                        "source_versions": stale_versions,
                        "cache_status": "fresh",
                    },
                ],
                scope_exists=False,
            )
        )

        response = _output_invoice_collection_rows_response(app, {"page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], "output_invoice_collection_row_1")
        self.assertNotIn("read_model_stale_reasons", payload)
        self.assertEqual(queue.refreshes, [])

    def test_output_api_all_scope_does_not_loop_on_relation_all_versions(self) -> None:
        base_versions = output_invoice_collection_source_versions()
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        app._workbench_relation_facade = FreshEmptyWorkbenchRelationFacade()
        app._output_invoice_collection_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                output_rows=[
                    {
                        "scope_key": "2026-05",
                        "payload": {
                            "id": "output_invoice_collection_row_1",
                            "invoiceId": "invoice-1",
                            "invoice": {"invoiceNo": "9001", "invoiceDate": "2026-05-08", "totalWithTax": "118.00"},
                            "collectionStatus": {
                                "code": "pending_collection",
                                "label": "待收款",
                                "collectedAmount": "0.00",
                                "pendingAmount": "118.00",
                            },
                            "oa": {"relationCount": 0},
                            "bankTransactions": {"relationCount": 0},
                            "invoiceRelations": {"relationCount": 0},
                            "redInvoiceRelation": {"relationCount": 0},
                            "receipt": {"status": "pending", "label": "待出收据"},
                        },
                        "raw_payload": {},
                    }
                ],
                output_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "row_count": 1,
                        "source_versions": {
                            **base_versions,
                            "workbench_relation_source_versions": {
                                "workbench_pair_relations_updated_at": "2026-06-21 15:00:00+08",
                            },
                        },
                        "cache_status": "fresh",
                    }
                ],
                workbench_relation_scope_rows=[
                    {
                        "scope_key": "2026-04",
                        "source_versions": {"workbench_pair_relations_updated_at": "2026-06-21 14:00:00+08"},
                    },
                    {
                        "scope_key": "2026-05",
                        "source_versions": {"workbench_pair_relations_updated_at": "2026-06-21 15:00:00+08"},
                    },
                ],
                scope_exists=False,
            )
        )

        response = _output_invoice_collection_rows_response(app, {"page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(queue.refreshes, [])

    def test_output_api_stale_returns_refreshing_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        app._output_invoice_collection_sql_read_repository = type(
            "OutputRepo",
            (),
            {
                "list_output_invoice_collection_rows": lambda *_args, **_kwargs: {
                    "rows": [
                        {
                            "id": "stale-row",
                            "invoice": {},
                            "collectionStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                            "invoiceRelations": {},
                            "redInvoiceRelation": {},
                            "receipt": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"invoiceCount": 1},
                    "filterConfig": [],
                    "refresh_status": "stale",
                }
            },
        )()

        response = _output_invoice_collection_rows_response(
            app,
            {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]}
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "api_stale")])

    def test_output_api_relation_source_version_mismatch_enqueues_refresh_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        old_relation_versions = {"source_version": "1"}
        current_relation_versions = {"source_version": "2"}
        app._output_invoice_collection_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                output_rows=[
                    {
                        "payload": {
                            "id": "stale-output-relation-row",
                            "invoice": {"totalWithTax": "118.00"},
                            "collectionStatus": {
                                "code": "pending_collection",
                                "collectedAmount": "0.00",
                                "pendingAmount": "118.00",
                            },
                            "oa": {},
                            "bankTransactions": {},
                            "invoiceRelations": {},
                            "redInvoiceRelation": {},
                            "receipt": {"status": "pending"},
                        },
                        "raw_payload": {},
                    }
                ],
                output_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "source_versions": {
                            **output_invoice_collection_source_versions(),
                            "workbench_relation_source_versions": old_relation_versions,
                        },
                        "cache_status": "fresh",
                    }
                ],
                workbench_relation_scope_rows=[
                    {"scope_key": "2026-05", "source_versions": current_relation_versions, "cache_status": "fresh"}
                ],
            )
        )

        response = _output_invoice_collection_rows_response(
            app,
            {"month": ["2026-05"], "page": ["1"], "page_size": ["50"]}
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("workbench_relation_source_versions_mismatch", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "api_source_versions_stale")])

    def test_projection_builder_persists_invoice_relation_source_versions(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
        )
        builder._core_repository = ProjectionCoreRepository(
            invoices=[
                self._invoice("input-invoice-1", InvoiceType.INPUT),
                self._invoice("output-invoice-1", InvoiceType.OUTPUT),
            ]
        )
        builder._workbench_repository = EmptyWorkbenchRepository()
        builder._oa_projection_repository = EmptyOAProjectionRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._input_invoice_usage_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        builder._oa_projection_repository = type(
            "OaProjection",
            (),
            {"list_all_application_records": lambda _self: []},
        )()

        input_result = builder.rebuild_input_invoice_usage_read_model_scope("2026-05")
        output_result = builder.rebuild_output_invoice_collection_read_model_scope("2026-05")
        oa_result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertEqual(input_result["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(output_result["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(oa_result["source_versions"], oa_pending_payment_source_versions())
        self.assertIsNotNone(read_repository.saved_input)
        self.assertIsNotNone(read_repository.saved_output)
        self.assertIsNotNone(read_repository.saved_oa)
        self.assertEqual(read_repository.saved_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.saved_output["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(read_repository.saved_oa["source_versions"], oa_pending_payment_source_versions())
        self.assertEqual(input_result["row_count"], 1)
        self.assertEqual(output_result["row_count"], 1)
        self.assertEqual(oa_result["row_count"], 0)

    def test_projection_builder_skips_unchanged_input_scope_without_resaving_rows(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        expected_source_versions = input_invoice_usage_source_versions()
        read_repository.existing_source_versions_by_method["list_input_invoice_usage_rows"] = expected_source_versions
        read_repository.existing_row_count_by_method["list_input_invoice_usage_rows"] = 154
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
        )
        builder._core_repository = ProjectionCoreRepository(
            invoices=[self._invoice("input-invoice-1", InvoiceType.INPUT)],
        )
        builder._read_repository = read_repository
        builder._input_invoice_usage_read_model_repository = read_repository

        result = builder.rebuild_input_invoice_usage_read_model_scope("2026-05")

        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertEqual(result["row_count"], 154)
        self.assertEqual(result["source_versions"], expected_source_versions)
        self.assertIsNone(read_repository.saved_input)

    def test_input_projection_keeps_current_scope_relation_versions_after_cross_month_fallback(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        read_repository.workbench_relation_versions_by_scope = {
            "2026-05": {"source_version": "workbench_relation:2026-05"}
        }
        invoice = self._invoice("input-invoice-cross-month", InvoiceType.INPUT, total="75799.00")
        bank = self._bank("bank-cross-month", "75799.00")
        relation_facade = CrossMonthVersionWorkbenchRelationFacade(
            invoice_id=invoice.id,
            bank_id=bank.id,
            oa_id="oa-cross-month",
        )
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=relation_facade,
        )
        builder._core_repository = ProjectionCoreRepository(invoices=[invoice], transactions=[bank])
        builder._workbench_repository = EmptyWorkbenchRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._input_invoice_usage_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository
        builder._oa_projection_repository = StaticOAProjectionRepository(
            [self._oa("oa-cross-month", "杨丽萍", "75799.00")]
        )

        result = builder.rebuild_input_invoice_usage_read_model_scope("2026-05")

        expected_source_versions = {
            **input_invoice_usage_source_versions(),
            "workbench_relation_source_versions": {"source_version": "workbench_relation:2026-05"},
        }
        self.assertEqual(result["source_versions"], expected_source_versions)
        self.assertIsNotNone(read_repository.saved_input)
        self.assertEqual(read_repository.saved_input["source_versions"], expected_source_versions)
        row = read_repository.saved_input["rows"][0]
        self.assertEqual(row["oa"]["relationCount"], 1)
        self.assertEqual(row["bankTransactions"]["relationCount"], 1)

    def test_projection_builder_persists_grouped_oa_pending_payment_relation_as_one_row(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        bank = self._bank("bank-grouped-projection", "4450.00")
        invoice = self._invoice("input-invoice-grouped-projection", InvoiceType.INPUT, total="4450.00")
        relation_facade = FreshStaticWorkbenchRelationFacade(
            [
                {
                    "case_id": "case-grouped-projection",
                    "row_ids": [
                        "oa-pay-projection-a",
                        "oa-pay-projection-b",
                        "oa-pay-projection-c",
                        bank.id,
                        invoice.id,
                    ],
                    "row_types": ["oa", "oa", "oa", "bank", "invoice"],
                    "amount_check": {"matched": True},
                }
            ]
        )
        oa_source_adapter = StaticOAProjectionRepository(
            [
                self._oa("oa-pay-projection-a", "刘际涛", "1690.00"),
                self._oa("oa-pay-projection-b", "刘际涛", "1980.00"),
                self._oa("oa-pay-projection-c", "刘际涛", "780.00"),
            ]
        )
        payment_repository = StaticOAPaymentStatusRepository(
            flow_ids={
                "oa-pay-projection-a": "projection-a",
                "oa-pay-projection-b": "projection-b",
                "oa-pay-projection-c": "projection-c",
            },
            admitted_flow_ids={"projection-a", "projection-b", "projection-c"},
        )
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=relation_facade,
            payment_status_repository=payment_repository,
            oa_source_adapter=oa_source_adapter,
        )
        builder._core_repository = ProjectionCoreRepository(invoices=[invoice], transactions=[bank])
        builder._workbench_repository = EmptyWorkbenchRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository
        builder._oa_projection_repository = oa_source_adapter

        result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertIsNotNone(read_repository.saved_oa)
        rows = read_repository.saved_oa["rows"]
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["oa"]["amount"], "4450.00")
        self.assertEqual(row["oa"]["relationCount"], 3)
        self.assertEqual(
            [summary["oaId"] for summary in row["oa"]["summaries"]],
            [
                "oa-pay-projection-a",
                "oa-pay-projection-b",
                "oa-pay-projection-c",
            ],
        )
        self.assertEqual(row["bankTransaction"]["paidTotal"], "4450.00")
        self.assertEqual(row["invoice"]["totalWithTax"], "4450.00")
        self.assertEqual(read_repository.saved_oa["source_versions"], oa_pending_payment_source_versions())

    def test_projection_builder_uses_payment_status_table_as_oa_admission_source(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        payment_repository = StaticOAPaymentStatusRepository(
            flow_ids={
                "oa-pay-mongo-admitted": "mongo-admitted",
                "oa-pay-mongo-duplicate": "mongo-duplicate",
            },
            admitted_flow_ids={"mongo-admitted"},
        )
        oa_source_adapter = StaticOAProjectionRepository(
            [
                self._oa("oa-pay-mongo-admitted", "刘际涛", "100.00", workflow_status="in_progress"),
                self._oa("oa-pay-mongo-duplicate", "刘际涛", "100.00", workflow_status="in_progress"),
            ]
        )
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
            payment_status_repository=payment_repository,
            oa_source_adapter=oa_source_adapter,
        )
        builder._core_repository = ProjectionCoreRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertIsNotNone(read_repository.saved_oa)
        rows = read_repository.saved_oa["rows"]
        self.assertEqual(result["row_count"], 1)
        self.assertEqual([row["oa"]["id"] for row in rows], ["oa-pay-mongo-admitted"])

    def test_projection_builder_releases_pending_relation_when_oa_admission_disappears(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        connection = OaPendingRelationCleanupConnection()
        payment_repository = StaticOAPaymentStatusRepository(
            flow_ids={
                "oa-pay-mongo-admitted": "mongo-admitted",
                "oa-pay-missing-admission": "mongo-missing-admission",
            },
            admitted_flow_ids={"mongo-admitted"},
        )
        oa_source_adapter = StaticOAProjectionRepository(
            [
                self._oa("oa-pay-mongo-admitted", "刘际涛", "100.00", workflow_status="in_progress"),
                self._oa("oa-pay-missing-admission", "张三", "1500.00", workflow_status="in_progress"),
            ]
        )
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=connection,
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
            payment_status_repository=payment_repository,
            oa_source_adapter=oa_source_adapter,
        )
        builder._core_repository = ProjectionCoreRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertIsNotNone(read_repository.saved_oa)
        self.assertEqual([row["oa"]["id"] for row in read_repository.saved_oa["rows"]], ["oa-pay-mongo-admitted"])
        self.assertEqual(result["pending_relation_cleanup"]["changed_relation_ids"], ["rel-missing-admission"])
        self.assertEqual(connection.relations["rel-missing-admission"]["status"], "cancelled")
        self.assertEqual(connection.claims["bank-missing-admission"]["status"], "released")
        self.assertEqual(
            connection.claims["bank-missing-admission"]["release_reason"],
            "oa_pending_payment_admission_missing",
        )

    def test_projection_builder_does_not_release_pending_relation_when_oa_admission_projection_is_refreshing(
        self,
    ) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        connection = OaPendingRelationCleanupConnection()
        payment_repository = StaticOAPaymentStatusRepository(
            flow_ids={"oa-pay-missing-admission": "mongo-missing-admission"},
            admitted_flow_ids=set(),
        )
        oa_source_adapter = RefreshingOAProjectionRepository(
            [
                self._oa("oa-pay-missing-admission", "张三", "1500.00", workflow_status="in_progress"),
            ]
        )
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=connection,
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
            payment_status_repository=payment_repository,
            oa_source_adapter=oa_source_adapter,
        )
        builder._core_repository = ProjectionCoreRepository()
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertEqual(result["pending_relation_cleanup"]["skipped"], "oa_admission_projection_not_ready")
        self.assertEqual(connection.relations["rel-missing-admission"]["status"], "active")
        self.assertEqual(connection.claims["bank-missing-admission"]["status"], "active")

    def test_projection_builder_reads_completed_from_unified_projection_and_in_progress_from_admission(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        payment_repository = StaticOAPaymentStatusRepository(
            flow_ids={
                "oa-pay-mongo-progress": "mongo-progress",
                "oa-pay-mongo-duplicate": "mongo-duplicate",
            },
            admitted_flow_ids={"mongo-progress"},
        )
        oa_source_adapter = StaticOAProjectionRepository(
            [
                self._oa("oa-pay-mongo-progress", "刘际涛", "100.00", workflow_status="in_progress"),
                self._oa("oa-pay-mongo-duplicate", "刘际涛", "100.00", workflow_status="in_progress"),
            ]
        )
        core_repository = ProjectionCoreRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
            payment_status_repository=payment_repository,
            oa_source_adapter=oa_source_adapter,
        )
        builder._core_repository = core_repository
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository
        completed_projection = StaticOAProjectionRepository(
            [
                self._oa("oa-completed-unified", "张三", "80.00", workflow_status="completed"),
                self._oa("oa-completed-other-month", "李四", "90.00", workflow_status="completed", month="2026-04"),
            ]
        )
        builder._oa_projection_repository = completed_projection

        result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertIsNotNone(read_repository.saved_oa)
        rows = read_repository.saved_oa["rows"]
        self.assertEqual(result["row_count"], 2)
        self.assertEqual([row["oa"]["id"] for row in rows], ["oa-completed-unified", "oa-pay-mongo-progress"])
        self.assertEqual(completed_projection.list_month_calls, ["2026-05"])
        self.assertEqual(completed_projection.list_all_calls, 0)
        self.assertEqual(payment_repository.list_statuses_calls, 1)
        self.assertEqual(payment_repository.get_payment_status_calls, 0)
        self.assertEqual(
            core_repository.invoice_page_calls,
            [{"page": 1, "page_size": 500, "month": None, "invoice_type": InvoiceType.INPUT.value}],
        )
        self.assertEqual(builder.list_oa_pending_payment_scope_shards("all"), ["2026-05", "2026-04"])

    def test_projection_builder_marks_empty_scopes_with_source_versions(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=object())
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._input_invoice_usage_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        builder.mark_input_invoice_usage_scope_empty("2026-05")
        builder.mark_output_invoice_collection_scope_empty("2026-05")
        builder.mark_oa_pending_payment_scope_empty("2026-05")

        self.assertEqual(read_repository.marked_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.marked_output["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(read_repository.marked_oa["source_versions"], oa_pending_payment_source_versions())

    def test_projection_builder_prunes_invoice_usage_collection_scope_shards(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=object())
        builder._read_repository = read_repository
        builder._output_invoice_collection_read_model_repository = read_repository
        builder._input_invoice_usage_read_model_repository = read_repository
        builder._oa_pending_payment_read_model_repository = read_repository

        builder.prune_input_invoice_usage_scope_shards(["2026-06"])
        builder.prune_output_invoice_collection_scope_shards(["2026-05"])
        builder.prune_oa_pending_payment_scope_shards(["2026-04"])

        self.assertEqual(read_repository.pruned_input, ["2026-06"])
        self.assertEqual(read_repository.pruned_output, ["2026-05"])
        self.assertEqual(read_repository.pruned_oa, ["2026-04"])

    def test_refresh_handler_expands_all_scopes_and_completes_with_source_version(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(f"input-list:{scope_key}")
                return ["2026-05", "2026-04"]

            def prune_input_invoice_usage_scope_shards(self, scope_keys: list[str]) -> None:
                self.calls.append(f"input-prune:{','.join(scope_keys)}")

            def rebuild_input_invoice_usage_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(f"input-build:{scope_key}")
                return {"scope_key": scope_key, "row_count": 1}

            def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        service = InvoiceUsageCollectionReadModelRefreshService(
            projection_builder=FakeBuilder(), queue_repository=queue
        )
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="input_invoice_usage.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="input_invoice_usage",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(service._projection_builder.calls, ["input-list:all", "input-prune:2026-05,2026-04"])
        self.assertEqual(
            queue.refreshes,
            [
                ("input_invoice_usage", "2026-05", "input_invoice_usage_month_shard"),
                ("input_invoice_usage", "2026-04", "input_invoice_usage_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "input_invoice_usage", "all", 7)])

    def test_refresh_handler_requires_projection_builder_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            InvoiceUsageCollectionReadModelRefreshService(queue_repository=object())

    def test_oa_refresh_handler_expands_all_scopes_and_completes_with_source_version(self) -> None:
        class FakeBuilder:
            def list_oa_pending_payment_scope_shards(self, scope_key: str) -> list[str]:
                self.scope_key = scope_key
                return ["2026-05"]

            def rebuild_oa_pending_payment_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"all scope should enqueue shards before rebuild: {scope_key}")

        queue = QueueRecorder()
        service = InvoiceUsageCollectionReadModelRefreshService(
            projection_builder=FakeBuilder(), queue_repository=queue
        )
        event = RuntimeQueueEvent(
            event_id="event-oa",
            tenant_id="tenant-a",
            event_type="oa_pending_payment.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="oa_pending_payment",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
            source_version=9,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05"], "row_count": 0})
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "oa_pending_payment_month_shard")])
        self.assertEqual(queue.completed, [("tenant-a", "oa_pending_payment", "all", 9)])

    def test_oa_refresh_handler_skips_stale_source_version_before_rebuild(self) -> None:
        class FakeBuilder:
            def list_oa_pending_payment_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(f"stale event should not list shards: {scope_key}")

            def rebuild_oa_pending_payment_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"stale event should not rebuild: {scope_key}")

        class StaleQueue(QueueRecorder):
            def __init__(self) -> None:
                super().__init__()
                self.current_checks: list[tuple[str, str, str, object]] = []

            def read_model_refresh_is_current(
                self,
                *,
                tenant_id: str,
                scope_type: str,
                scope_key: str,
                source_version: object,
            ) -> bool:
                self.current_checks.append((tenant_id, scope_type, scope_key, source_version))
                return False

        queue = StaleQueue()
        service = InvoiceUsageCollectionReadModelRefreshService(
            projection_builder=FakeBuilder(), queue_repository=queue
        )
        event = RuntimeQueueEvent(
            event_id="event-oa-stale",
            tenant_id="tenant-a",
            event_type="oa_pending_payment.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="oa_pending_payment",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
            source_version=9,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            result,
            {
                "scope_key": "2026-05",
                "skipped": True,
                "skip_reason": "stale_source_version",
                "source_version": 9,
            },
        )
        self.assertEqual(queue.current_checks, [("tenant-a", "oa_pending_payment", "2026-05", 9)])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [])

    def test_rabbitmq_event_types_include_invoice_usage_collection_read_models(self) -> None:
        self.assertIn("input_invoice_usage.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("output_invoice_collection.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("oa_pending_payment.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("input_invoice_usage.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("output_invoice_collection.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("oa_pending_payment.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)

    @staticmethod
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        workflow_status: str | None = "completed",
        month: str = "2026-05",
    ) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month=month,
            section="审批通过",
            case_id=None,
            applicant=applicant,
            project_name="投影测试项目",
            apply_type="支付申请",
            amount=amount,
            counterparty_name="测试往来单位",
            reason="投影测试付款",
            relation_code="",
            relation_label="",
            relation_tone="",
            workflow_status=workflow_status,
            detail_fields={"申请日期": "2026-05-20"},
            project_name_display="投影测试项目",
        )

    @staticmethod
    def _bank(bank_id: str, amount: str) -> BankTransaction:
        return BankTransaction(
            id=bank_id,
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="测试往来单位",
            amount=Decimal(amount),
            signed_amount=-Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            account_name="云南溯源科技有限公司",
            balance=Decimal("900.00"),
            currency="人民币元",
            counterparty_account_no="621700001",
            counterparty_bank_name="建行昆明支行",
            booked_date="20260521",
            summary="电子转账",
            remark="投影测试付款备注",
            account_detail_no=f"detail-{bank_id}",
            enterprise_serial_no=f"enterprise-{bank_id}",
            voucher_kind="电子转账凭证",
            voucher_no=f"voucher-{bank_id}",
            imported_bank_name="建设银行",
            imported_bank_last4="1234",
        )

    @staticmethod
    def _invoice(invoice_id: str, invoice_type: InvoiceType, *, total: str = "118.00") -> Invoice:
        counterparty = Counterparty(
            id=f"cp-{invoice_id}",
            name="测试往来单位",
            normalized_name="测试往来单位",
            counterparty_type="supplier" if invoice_type == InvoiceType.INPUT else "customer",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=invoice_type,
            invoice_no=f"NO-{invoice_id}",
            counterparty=counterparty,
            amount=Decimal(total),
            signed_amount=Decimal(total),
            invoice_date="2026-05-20",
            seller_name="测试销方",
            buyer_name="测试购方",
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal("6.68"),
            total_with_tax=Decimal(total),
            taxable_item_name="服务费",
        )


if __name__ == "__main__":
    unittest.main()
