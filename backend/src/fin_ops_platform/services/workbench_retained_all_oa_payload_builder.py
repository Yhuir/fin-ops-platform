from __future__ import annotations

from contextlib import nullcontext
from typing import Callable, ContextManager


class WorkbenchRetainedAllOaPayloadBuilder:
    """Builds retained all-scope OA raw payloads through explicit ports."""

    def __init__(
        self,
        *,
        retention_cutoff_date: Callable[[], object | None],
        get_all_workbench_payload: Callable[[], object],
        serialize_value: Callable[[object], object],
        raw_payload_has_oa_attachment_invoice_signal: Callable[[dict[str, object]], bool],
        oa_months_from_raw_workbench_payload: Callable[[dict[str, object]], set[str]],
        promote_oa_attachment_invoices_to_canonical: Callable[[set[str]], int],
        retained_oa_months_for_all_scope: Callable[[object], list[str]],
        supplemental_retained_oa_row_ids: Callable[[object], list[str]],
        suppress_attachment_invoice_background_parse: Callable[[], ContextManager[object]] | None,
        sync_oa_rows: Callable[[str], None],
        sync_oa_row_ids: Callable[[list[str]], None],
        record_snapshots: Callable[[], list[dict[str, object]]],
        raw_oa_payload_for_selected_scope: Callable[..., dict[str, object]],
        is_month_scope: Callable[[str], bool],
    ) -> None:
        self._retention_cutoff_date = retention_cutoff_date
        self._get_all_workbench_payload = get_all_workbench_payload
        self._serialize_value = serialize_value
        self._raw_payload_has_oa_attachment_invoice_signal = raw_payload_has_oa_attachment_invoice_signal
        self._oa_months_from_raw_workbench_payload = oa_months_from_raw_workbench_payload
        self._promote_oa_attachment_invoices_to_canonical = promote_oa_attachment_invoices_to_canonical
        self._retained_oa_months_for_all_scope = retained_oa_months_for_all_scope
        self._supplemental_retained_oa_row_ids = supplemental_retained_oa_row_ids
        self._suppress_attachment_invoice_background_parse = suppress_attachment_invoice_background_parse
        self._sync_oa_rows = sync_oa_rows
        self._sync_oa_row_ids = sync_oa_row_ids
        self._record_snapshots = record_snapshots
        self._raw_oa_payload_for_selected_scope = raw_oa_payload_for_selected_scope
        self._is_month_scope = is_month_scope

    def build(self) -> dict[str, object]:
        cutoff_date = self._retention_cutoff_date()
        if cutoff_date is None:
            serialized = self._serialize_value(self._get_all_workbench_payload())
            payload = serialized if isinstance(serialized, dict) else {}
            if self._raw_payload_has_oa_attachment_invoice_signal(payload):
                self._promote_oa_attachment_invoices_to_canonical(
                    self._oa_months_from_raw_workbench_payload(payload)
                )
            return payload

        scoped_months = self._retained_oa_months_for_all_scope(cutoff_date)
        supplemental_oa_row_ids = self._supplemental_retained_oa_row_ids(cutoff_date)
        with self._parse_context():
            for scoped_month in scoped_months:
                self._sync_oa_rows(scoped_month)
            if supplemental_oa_row_ids:
                self._sync_oa_row_ids(supplemental_oa_row_ids)
        promotion_scopes = set(scoped_months)
        if supplemental_oa_row_ids:
            supplemental_row_id_set = set(supplemental_oa_row_ids)
            promotion_scopes.update(
                str(row.get("_month", "")).strip()
                for row in self._record_snapshots()
                if str(row.get("id", "")).strip() in supplemental_row_id_set
            )
        serialized = self._serialize_value(
            self._raw_oa_payload_for_selected_scope(
                months=set(scoped_months),
                supplemental_oa_row_ids=set(supplemental_oa_row_ids),
            )
        )
        payload = serialized if isinstance(serialized, dict) else {}
        if self._raw_payload_has_oa_attachment_invoice_signal(payload):
            self._promote_oa_attachment_invoices_to_canonical(
                {scope_key for scope_key in promotion_scopes if self._is_month_scope(scope_key)}
            )
        return payload

    def _parse_context(self) -> ContextManager[object]:
        if self._suppress_attachment_invoice_background_parse is None:
            return nullcontext()
        return self._suppress_attachment_invoice_background_parse()
