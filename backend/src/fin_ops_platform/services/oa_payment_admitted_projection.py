from __future__ import annotations

from datetime import datetime
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord, OAReadStatus
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRepository


MONTH_FORMAT = "%Y-%m"


class PaymentAdmittedOAProjectionAdapter:
    """OA projection for pages whose OA scope is admitted by t_payment_simple."""

    def __init__(
        self,
        *,
        source_adapter: Any,
        payment_status_repository: OAPaymentStatusRepository | None,
    ) -> None:
        self._source_adapter = source_adapter
        self._payment_status_repository = payment_status_repository

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        normalized_month = str(month or "").strip()
        if normalized_month == "all":
            return self.list_all_application_records()
        return [
            record
            for record in self.list_all_application_records()
            if str(getattr(record, "month", "") or "").strip() == normalized_month
        ]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        flow_ids = self._admitted_flow_ids()
        if not flow_ids:
            return []
        records = self._load_source_records_for_flow_ids(flow_ids)
        return self._filter_admitted(records, flow_ids)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_row_ids = _dedupe_texts(row_ids)
        if not normalized_row_ids:
            return []
        flow_ids = self._admitted_flow_ids()
        if not flow_ids:
            return []
        records = self._load_source_records_by_row_ids(normalized_row_ids)
        records_by_id = {record.id: record for record in self._filter_admitted(records, flow_ids)}
        return [records_by_id[row_id] for row_id in normalized_row_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        return sorted(
            {
                month
                for record in self.list_all_application_records()
                if (month := str(getattr(record, "month", "") or "").strip())
                and _is_month_scope(month)
            },
            reverse=True,
        )

    def get_read_status(self) -> OAReadStatus:
        get_status = getattr(self._source_adapter, "get_read_status", None)
        if callable(get_status):
            return get_status()
        return OAReadStatus(code="ready", message="OA payment-admitted projection ready")

    def _admitted_flow_ids(self) -> set[str]:
        repository = self._payment_status_repository
        if repository is None:
            return set()
        list_statuses = getattr(repository, "list_payment_statuses", None)
        if not callable(list_statuses):
            return set()
        statuses = list_statuses()
        if not isinstance(statuses, dict):
            return set()
        return {str(flow_id or "").strip() for flow_id in statuses if str(flow_id or "").strip()}

    def _load_source_records_for_flow_ids(self, flow_ids: set[str]) -> list[OAApplicationRecord]:
        row_ids = _row_id_candidates_for_flow_ids(flow_ids)
        return self._load_source_records_by_row_ids(row_ids)

    def _load_source_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        if self._source_adapter is None:
            return []
        list_by_ids = getattr(self._source_adapter, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            return [record for record in list(list_by_ids(row_ids) or []) if isinstance(record, OAApplicationRecord)]
        list_all = getattr(self._source_adapter, "list_all_application_records", None)
        if callable(list_all):
            wanted = set(row_ids)
            return [
                record
                for record in list(list_all() or [])
                if isinstance(record, OAApplicationRecord) and str(getattr(record, "id", "") or "").strip() in wanted
            ]
        return []

    def _filter_admitted(self, records: list[OAApplicationRecord], flow_ids: set[str]) -> list[OAApplicationRecord]:
        repository = self._payment_status_repository
        if repository is None:
            return []
        admitted: list[OAApplicationRecord] = []
        seen_ids: set[str] = set()
        for record in records:
            flow_id = repository.resolve_flow_id(record)
            record_id = str(getattr(record, "id", "") or "").strip()
            if not flow_id or flow_id not in flow_ids or not record_id or record_id in seen_ids:
                continue
            seen_ids.add(record_id)
            admitted.append(record)
        return admitted


def _row_id_candidates_for_flow_ids(flow_ids: set[str]) -> list[str]:
    candidates: list[str] = []
    for flow_id in sorted(flow_ids):
        if flow_id.startswith(("oa-pay-", "oa-exp-")):
            candidates.append(flow_id)
            suffix = flow_id.removeprefix("oa-pay-").removeprefix("oa-exp-")
        else:
            suffix = flow_id
        candidates.append(f"oa-pay-{suffix}")
        candidates.append(f"oa-exp-{suffix}")
    return _dedupe_texts(candidates)


def _dedupe_texts(values: list[str] | set[str] | tuple[str, ...]) -> list[str]:
    deduped: list[str] = []
    for value in list(values or []):
        normalized = str(value or "").strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _is_month_scope(value: str) -> bool:
    try:
        datetime.strptime(value, MONTH_FORMAT)
    except ValueError:
        return False
    return True
