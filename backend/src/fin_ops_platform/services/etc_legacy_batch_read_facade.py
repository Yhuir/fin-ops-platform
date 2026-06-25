from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

from fin_ops_platform.services.etc_service import (
    EtcBatchNotFoundError,
    EtcBusinessBatchNotFoundError,
    EtcBusinessBatchStatus,
)


class EtcLegacyBatchReadFacade:
    def __init__(
        self,
        *,
        etc_service: Any,
        reconciliation_task_service: Any,
        existing_etc_invoices_by_ids: Callable[[list[str]], list[object]],
        serialize_value: Callable[[object], Any],
        serialize_etc_invoice: Callable[[object], dict[str, object]],
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._existing_etc_invoices_by_ids = existing_etc_invoices_by_ids
        self._serialize_value = serialize_value
        self._serialize_etc_invoice = serialize_etc_invoice

    def list_payload(
        self,
        *,
        status: str,
        month: str | None,
        plate: str | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> dict[str, object]:
        batches = self._list_items(
            status=status,
            month=month,
            plate=plate,
            keyword=keyword,
        )
        counts = self._counts()
        total = len(batches)
        safe_page = max(page, 1)
        safe_page_size = min(max(page_size, 1), 500)
        start = (safe_page - 1) * safe_page_size
        paged_items = batches[start:start + safe_page_size]
        selected = paged_items[0] if paged_items else None
        selected_summary = selected.get("summary", {}) if isinstance(selected, dict) else {}
        selected_batch_id = (
            str(selected_summary.get("id", "") or "").strip()
            if isinstance(selected_summary, dict)
            else ""
        )
        selected_detail = self.detail_payload(selected_batch_id) if selected_batch_id else None
        selected_for_payload = (
            self.detail_filtered_for_query(selected_detail, plate=plate, keyword=keyword)
            if selected_detail is not None
            else None
        )
        return {
            "items": [item["summary"] for item in paged_items],
            "counts": {**counts, "current": total},
            "pagination": {"page": safe_page, "page_size": safe_page_size, "total": total},
            "selectedBatch": selected_for_payload,
            "plateSummary": (
                selected_for_payload.get("plateSummary", [])
                if isinstance(selected_for_payload, dict)
                else []
            ),
            "invoiceItems": (
                selected_detail.get("invoiceItems", [])
                if isinstance(selected_detail, dict)
                else []
            ),
        }

    def detail_payload(self, batch_id: str) -> dict[str, object] | None:
        try:
            business_batch = self._etc_service.get_business_batch(batch_id)
        except EtcBusinessBatchNotFoundError:
            business_batch = None
        if business_batch is not None:
            return self._business_batch_detail_payload(business_batch)
        try:
            batch = self._etc_service.get_batch(batch_id)
        except EtcBatchNotFoundError:
            batch = None
        if batch is not None:
            return self._submission_batch_detail_payload(batch)
        for import_batch in self._etc_service.list_import_batches():
            if str(import_batch.id) == str(batch_id):
                return self._import_batch_detail_payload(import_batch)
        return None

    def _counts(self) -> dict[str, int]:
        business_batches = self._etc_service.list_business_batches()
        visible_business_batches = [
            batch for batch in business_batches if not self._is_task_scoped_active_business_batch(batch)
        ]
        business_import_batch_ids = {
            import_batch_id
            for batch in business_batches
            for import_batch_id in list(getattr(batch, "import_batch_ids", []) or [])
        }
        business_submission_batch_ids = {
            str(getattr(batch, "submission_batch_id", "") or "").strip()
            for batch in business_batches
            if str(getattr(batch, "submission_batch_id", "") or "").strip()
        }
        business_submitted_count = sum(
            1
            for batch in visible_business_batches
            if self._business_batch_legacy_status(batch) == "submitted"
        )
        business_unsubmitted_count = len(visible_business_batches) - business_submitted_count
        import_batches = [
            batch
            for batch in self._etc_service.list_import_batches()
            if not str(getattr(batch, "submission_batch_id", "") or "").strip()
            and str(getattr(batch, "id", "") or "").strip() not in business_import_batch_ids
            and int(getattr(batch, "invoice_count", 0) or 0) > 0
            and not self._is_reconciliation_import_batch(batch)
        ]
        unsubmitted_submission_batches = [
            batch
            for batch in self._etc_service.list_batches(status="unsubmitted")
            if str(getattr(batch, "id", "") or "").strip() not in business_submission_batch_ids
        ]
        submitted_batches = [
            batch
            for batch in self._etc_service.list_batches(status="submitted")
            if str(getattr(batch, "id", "") or "").strip() not in business_submission_batch_ids
        ]
        return {
            "unsubmitted": business_unsubmitted_count
            + len(import_batches)
            + len(unsubmitted_submission_batches),
            "submitted": business_submitted_count + len(submitted_batches),
        }

    def _list_items(
        self,
        *,
        status: str,
        month: str | None,
        plate: str | None,
        keyword: str | None,
    ) -> list[dict[str, object]]:
        include_submitted = status in {"", "submitted"}
        include_unsubmitted = status in {"", "unsubmitted"}
        items: list[dict[str, object]] = []
        business_batches = self._etc_service.list_business_batches()
        business_import_batch_ids = {
            import_batch_id
            for batch in business_batches
            for import_batch_id in list(getattr(batch, "import_batch_ids", []) or [])
        }
        business_submission_batch_ids = {
            str(getattr(batch, "submission_batch_id", "") or "").strip()
            for batch in business_batches
            if str(getattr(batch, "submission_batch_id", "") or "").strip()
        }
        for business_batch in business_batches:
            if self._is_task_scoped_active_business_batch(business_batch):
                continue
            legacy_status = self._business_batch_legacy_status(business_batch)
            if (
                legacy_status == "submitted"
                and not include_submitted
            ) or (
                legacy_status == "unsubmitted"
                and not include_unsubmitted
            ):
                continue
            item = self._business_batch_summary_payload(business_batch)
            if self._summary_matches_filters(
                item,
                month=month,
                plate=plate,
                keyword=keyword,
                invoice_ids=list(getattr(business_batch, "invoice_ids", []) or []),
            ):
                items.append(item)
        if include_submitted:
            for batch in self._etc_service.list_batches(status="submitted"):
                if str(getattr(batch, "id", "") or "").strip() in business_submission_batch_ids:
                    continue
                item = self._submission_batch_summary_payload(batch)
                if self._summary_matches_filters(
                    item,
                    month=month,
                    plate=plate,
                    keyword=keyword,
                    invoice_ids=list(getattr(batch, "invoice_ids", []) or []),
                ):
                    items.append(item)
        if include_unsubmitted:
            for batch in self._etc_service.list_batches(status="unsubmitted"):
                if str(getattr(batch, "id", "") or "").strip() in business_submission_batch_ids:
                    continue
                item = self._submission_batch_summary_payload(batch)
                if self._summary_matches_filters(
                    item,
                    month=month,
                    plate=plate,
                    keyword=keyword,
                    invoice_ids=list(getattr(batch, "invoice_ids", []) or []),
                ):
                    items.append(item)
            for import_batch in self._etc_service.list_import_batches():
                if str(getattr(import_batch, "id", "") or "").strip() in business_import_batch_ids:
                    continue
                if self._is_reconciliation_import_batch(import_batch):
                    continue
                if str(getattr(import_batch, "submission_batch_id", "") or "").strip():
                    continue
                if int(getattr(import_batch, "invoice_count", 0) or 0) <= 0:
                    continue
                invoice_ids = [
                    str(invoice_id)
                    for invoice_id in list(getattr(import_batch, "invoice_ids", []) or [])
                ]
                invoices = self._existing_etc_invoices_by_ids(invoice_ids)
                item = self._import_batch_summary_payload(import_batch, invoices=invoices)
                if self._summary_matches_filters(
                    item,
                    month=month,
                    plate=plate,
                    keyword=keyword,
                    invoices=invoices,
                ):
                    items.append(item)
        return sorted(
            items,
            key=lambda item: str(
                item.get("summary", {}).get("created_at", "")
                if isinstance(item.get("summary"), dict)
                else ""
            ),
            reverse=True,
        )

    def _is_reconciliation_import_batch(self, import_batch: object) -> bool:
        batch_id = str(getattr(import_batch, "id", "") or "").strip()
        if not batch_id:
            return False
        return self._reconciliation_task_service.find_task_for_import_batch_ids([batch_id]) is not None

    def _is_task_scoped_active_business_batch(self, batch: object) -> bool:
        task_id = str(getattr(batch, "task_id", "") or "").strip()
        if not task_id:
            return False
        try:
            self._reconciliation_task_service.get_task(task_id)
        except KeyError:
            return False
        return self._business_batch_legacy_status(batch) != "submitted"

    @staticmethod
    def _business_batch_legacy_status(batch: object) -> str:
        submitted_statuses = {
            EtcBusinessBatchStatus.OA_SUBMITTED.value,
            EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value,
            EtcBusinessBatchStatus.CLOSED.value,
        }
        return "submitted" if str(getattr(batch, "status", "") or "") in submitted_statuses else "unsubmitted"

    def _business_batch_detail_payload(self, batch: object) -> dict[str, object]:
        invoice_ids = [str(invoice_id) for invoice_id in list(getattr(batch, "invoice_ids", []) or [])]
        invoices = self._existing_etc_invoices_by_ids(invoice_ids)
        invoice_items = [self._serialize_etc_invoice(invoice) for invoice in invoices]
        payload = self._business_batch_summary_payload(batch)
        payload["invoiceItems"] = invoice_items
        payload["businessBatch"] = self._etc_service.business_batch_payload(batch)
        return payload

    def _business_batch_summary_payload(self, batch: object) -> dict[str, object]:
        invoice_ids = [str(invoice_id) for invoice_id in list(getattr(batch, "invoice_ids", []) or [])]
        invoices = self._existing_etc_invoices_by_ids(invoice_ids)
        amount = sum(
            (Decimal(str(getattr(invoice, "total_amount", "0"))) for invoice in invoices),
            Decimal("0.00"),
        ).quantize(Decimal("0.01"))
        amount_breakdown = (
            getattr(batch, "amount_breakdown", {})
            if isinstance(getattr(batch, "amount_breakdown", {}), dict)
            else {}
        )
        reported_amount = amount_breakdown.get("reported_amount") or amount_breakdown.get("oa_amount")
        if reported_amount not in (None, ""):
            try:
                amount = Decimal(str(reported_amount)).quantize(Decimal("0.01"))
            except (ArithmeticError, ValueError):
                amount = amount
        issue_dates = sorted(
            str(getattr(invoice, "issue_date", "") or "")
            for invoice in invoices
            if str(getattr(invoice, "issue_date", "") or "")
        )
        passage_dates = sorted(
            date_value
            for invoice in invoices
            for date_value in (
                str(getattr(invoice, "passage_start_date", "") or ""),
                str(getattr(invoice, "passage_end_date", "") or ""),
            )
            if date_value
        )
        plate_summary = self._plate_summary_for_invoices(invoices)
        summary = self._serialize_batch_summary(
            id_value=str(getattr(batch, "business_batch_id", "")),
            etc_batch_id=str(
                getattr(batch, "external_etc_batch_id", "")
                or getattr(batch, "business_batch_id", "")
            ),
            status=self._business_batch_legacy_status(batch),
            source_type="etc_business_batch",
            invoice_count=len(invoices),
            total_amount=amount,
            issue_start_date=issue_dates[0] if issue_dates else None,
            issue_end_date=issue_dates[-1] if issue_dates else None,
            passage_start_date=passage_dates[0] if passage_dates else None,
            passage_end_date=passage_dates[-1] if passage_dates else None,
            plate_summary=plate_summary,
            linked_oa_row_id=getattr(batch, "oa_row_id", None),
            linked_oa_case_id=None,
            amount_delta=None,
            note=str(getattr(batch, "status", "") or ""),
            created_at=getattr(batch, "created_at", None),
        )
        summary["business_batch_id"] = str(getattr(batch, "business_batch_id", ""))
        summary["businessBatchId"] = str(getattr(batch, "business_batch_id", ""))
        summary["business_status"] = str(getattr(batch, "status", ""))
        summary["submissionBatchId"] = getattr(batch, "submission_batch_id", None)
        summary["scope_month"] = str(amount_breakdown.get("scope_month") or "")
        summary["amount_breakdown"] = dict(amount_breakdown)
        return {
            "batch": self._etc_service.business_batch_payload(batch),
            "summary": summary,
            "plateSummary": summary["plate_summary"],
            "invoiceItems": [],
            "supplementItems": [],
        }

    def _submission_batch_detail_payload(self, batch: object) -> dict[str, object] | None:
        detail = self._etc_service.get_batch_detail(str(getattr(batch, "id", "")))
        invoices = list(detail.get("invoice_items") or [])
        supplement_items = list(
            detail.get("supplement_items") or getattr(batch, "supplement_items", []) or []
        )
        summary = self._submission_batch_summary(batch)
        summary.update(self._reconciliation_summary_payload(batch))
        return {
            "batch": self._serialize_value(batch),
            "summary": summary,
            "plateSummary": summary["plate_summary"],
            "invoiceItems": invoices,
            "supplementItems": self._serialize_value(supplement_items),
        }

    def _submission_batch_summary_payload(self, batch: object) -> dict[str, object]:
        summary = self._submission_batch_summary(batch)
        summary.update(self._reconciliation_summary_payload(batch))
        return {
            "batch": self._serialize_value(batch),
            "summary": summary,
            "plateSummary": summary["plate_summary"],
            "invoiceItems": [],
            "supplementItems": self._serialize_value(list(getattr(batch, "supplement_items", []) or [])),
        }

    def _submission_batch_summary(self, batch: object) -> dict[str, object]:
        return self._serialize_batch_summary(
            id_value=str(getattr(batch, "id", "")),
            etc_batch_id=str(getattr(batch, "etc_batch_id", "")),
            status=(
                "submitted"
                if str(getattr(batch, "status", "")) == "submitted_confirmed"
                else str(getattr(batch, "status", ""))
            ),
            source_type=str(getattr(batch, "source_type", "normal_oa_draft") or "normal_oa_draft"),
            invoice_count=int(getattr(batch, "invoice_count", 0) or 0),
            total_amount=getattr(batch, "total_amount", Decimal("0.00")),
            issue_start_date=getattr(batch, "issue_start_date", None),
            issue_end_date=getattr(batch, "issue_end_date", None),
            passage_start_date=getattr(batch, "passage_start_date", None),
            passage_end_date=getattr(batch, "passage_end_date", None),
            plate_summary=list(getattr(batch, "plate_summary", []) or []),
            linked_oa_row_id=getattr(batch, "linked_oa_row_id", None),
            linked_oa_case_id=getattr(batch, "linked_oa_case_id", None),
            amount_delta=getattr(batch, "amount_delta", None),
            note=getattr(batch, "note", ""),
            created_at=getattr(batch, "created_at", None),
        )

    def _import_batch_detail_payload(self, import_batch: object) -> dict[str, object] | None:
        invoice_ids = list(getattr(import_batch, "invoice_ids", []) or [])
        invoices = self._existing_etc_invoices_by_ids([str(invoice_id) for invoice_id in invoice_ids])
        invoice_items = [self._serialize_etc_invoice(invoice) for invoice in invoices]
        payload = self._import_batch_summary_payload(import_batch, invoices=invoices)
        payload["invoiceItems"] = invoice_items
        return payload

    def _import_batch_summary_payload(
        self,
        import_batch: object,
        *,
        invoices: list[object],
    ) -> dict[str, object]:
        plate_summary = self._plate_summary_for_invoices(invoices)
        summary = self._serialize_batch_summary(
            id_value=str(getattr(import_batch, "id", "")),
            etc_batch_id=str(getattr(import_batch, "id", "")),
            status="unsubmitted",
            source_type="etc_import",
            invoice_count=int(getattr(import_batch, "invoice_count", 0) or len(invoices)),
            total_amount=getattr(import_batch, "total_amount", Decimal("0.00")),
            issue_start_date=getattr(import_batch, "issue_date_start", None),
            issue_end_date=getattr(import_batch, "issue_date_end", None),
            passage_start_date=getattr(import_batch, "passage_date_start", None),
            passage_end_date=getattr(import_batch, "passage_date_end", None),
            plate_summary=plate_summary,
            linked_oa_row_id=None,
            linked_oa_case_id=None,
            amount_delta=None,
            note="",
            created_at=getattr(import_batch, "created_at", None),
        )
        return {
            "batch": self._serialize_value(import_batch),
            "summary": summary,
            "plateSummary": summary["plate_summary"],
            "invoiceItems": [],
        }

    @staticmethod
    def _serialize_batch_summary(
        *,
        id_value: str,
        etc_batch_id: str,
        status: str,
        source_type: str,
        invoice_count: int,
        total_amount: object,
        issue_start_date: object,
        issue_end_date: object,
        passage_start_date: object,
        passage_end_date: object,
        plate_summary: list[dict[str, object]],
        linked_oa_row_id: object,
        linked_oa_case_id: object,
        amount_delta: object,
        note: object,
        created_at: object,
    ) -> dict[str, object]:
        plate_items = [
            {
                "plate_number": str(item.get("plate_number", "") or ""),
                "invoice_count": int(item.get("invoice_count", 0) or 0),
                "total_amount": item.get("total_amount", "0.00"),
            }
            for item in plate_summary
            if isinstance(item, dict)
        ]
        return {
            "id": id_value,
            "batch_id": id_value,
            "etc_batch_id": etc_batch_id,
            "external_batch_id": etc_batch_id,
            "status": status,
            "source_type": source_type,
            "invoice_count": invoice_count,
            "total_amount": total_amount,
            "tax_amount": "0.00",
            "issue_start_date": issue_start_date,
            "issue_end_date": issue_end_date,
            "passage_start_date": passage_start_date,
            "passage_end_date": passage_end_date,
            "plate_count": len(plate_items),
            "plate_summary": plate_items,
            "linked_oa_row_id": linked_oa_row_id,
            "linked_oa_case_id": linked_oa_case_id,
            "linked_oa_applicant": "",
            "linked_oa_apply_date": "",
            "linked_oa_amount": "",
            "amount_delta": amount_delta,
            "note": note,
            "created_at": created_at,
        }

    @staticmethod
    def _reconciliation_summary_payload(batch: object) -> dict[str, object]:
        task_id = str(getattr(batch, "reconciliation_task_id", "") or "").strip()
        if not task_id:
            return {}
        etc_invoice_count = int(
            getattr(batch, "etc_invoice_count", None) or getattr(batch, "invoice_count", 0) or 0
        )
        supplement_count = int(getattr(batch, "supplement_count", 0) or 0)
        return {
            "reconciliationTaskId": task_id,
            "oaTotalAmount": getattr(batch, "oa_total_amount", None)
            or getattr(batch, "total_amount", None),
            "etcInvoiceAmount": getattr(batch, "etc_invoice_amount", None)
            or getattr(batch, "total_amount", None),
            "supplementAmount": getattr(batch, "supplement_amount", None),
            "etcInvoiceCount": etc_invoice_count,
            "supplementCount": supplement_count,
            "displayCountText": getattr(batch, "display_count_text", None)
            or f"ETC票 {etc_invoice_count} + 补充凭证 {supplement_count}",
            "statementPeriodStart": getattr(batch, "statement_period_start", None),
            "statementPeriodEnd": getattr(batch, "statement_period_end", None),
        }

    @staticmethod
    def _plate_summary_for_invoices(invoices: list[object]) -> list[dict[str, object]]:
        totals: dict[str, dict[str, object]] = {}
        for invoice in invoices:
            plate_number = str(getattr(invoice, "plate_number", "") or "未识别车牌").strip() or "未识别车牌"
            item = totals.setdefault(
                plate_number,
                {"plate_number": plate_number, "invoice_count": 0, "total_amount": Decimal("0.00")},
            )
            item["invoice_count"] = int(item["invoice_count"]) + 1
            item["total_amount"] = (
                Decimal(str(item["total_amount"]))
                + Decimal(str(getattr(invoice, "total_amount", "0")))
            ).quantize(Decimal("0.01"))
        summary = list(totals.values())
        summary.sort(key=lambda item: -int(item["invoice_count"]))
        return summary

    @staticmethod
    def _payload_matches_filters(
        detail: dict[str, object],
        *,
        month: str | None,
        plate: str | None,
        keyword: str | None,
    ) -> bool:
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        invoice_items = list(detail.get("invoiceItems") or [])
        normalized_month = str(month or "").strip()
        if normalized_month:
            date_values = [
                str(summary.get("scope_month", "") or ""),
                str(summary.get("issue_start_date", "") or ""),
                str(summary.get("issue_end_date", "") or ""),
                str(summary.get("passage_start_date", "") or ""),
                str(summary.get("passage_end_date", "") or ""),
                *[str(item.get("issue_date", "") or "") for item in invoice_items if isinstance(item, dict)],
                *[
                    str(item.get("passage_start_date", "") or "")
                    for item in invoice_items
                    if isinstance(item, dict)
                ],
                *[
                    str(item.get("passage_end_date", "") or "")
                    for item in invoice_items
                    if isinstance(item, dict)
                ],
            ]
            if not any(value.startswith(normalized_month) for value in date_values):
                return False
        normalized_plate = str(plate or "").strip().lower()
        if normalized_plate and not any(
            normalized_plate in str(item.get("plate_number", "") or "").lower()
            for item in invoice_items
            if isinstance(item, dict)
        ):
            return False
        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword:
            haystack = [
                str(value or "").lower()
                for value in (
                    summary.get("id"),
                    summary.get("etc_batch_id"),
                    summary.get("note"),
                    *[
                        field
                        for item in invoice_items
                        if isinstance(item, dict)
                        for field in (
                            item.get("invoice_number"),
                            item.get("seller_name"),
                            item.get("buyer_name"),
                            item.get("plate_number"),
                        )
                    ],
                )
            ]
            if not any(normalized_keyword in value for value in haystack):
                return False
        return True

    def _summary_matches_filters(
        self,
        detail: dict[str, object],
        *,
        month: str | None,
        plate: str | None,
        keyword: str | None,
        invoices: list[object] | None = None,
        invoice_ids: list[str] | None = None,
    ) -> bool:
        if not str(month or "").strip() and not str(plate or "").strip() and not str(keyword or "").strip():
            return True
        resolved_invoices = invoices
        if resolved_invoices is None and invoice_ids:
            resolved_invoices = self._existing_etc_invoices_by_ids(
                [str(invoice_id) for invoice_id in invoice_ids]
            )
        return self._payload_matches_filters(
            {
                **detail,
                "invoiceItems": [
                    self._invoice_filter_payload(invoice)
                    for invoice in list(resolved_invoices or [])
                ],
            },
            month=month,
            plate=plate,
            keyword=keyword,
        )

    @staticmethod
    def _invoice_filter_payload(invoice: object) -> dict[str, object]:
        return {
            "invoice_number": getattr(invoice, "invoice_number", ""),
            "issue_date": getattr(invoice, "issue_date", ""),
            "passage_start_date": getattr(invoice, "passage_start_date", ""),
            "passage_end_date": getattr(invoice, "passage_end_date", ""),
            "plate_number": getattr(invoice, "plate_number", ""),
            "seller_name": getattr(invoice, "seller_name", ""),
            "buyer_name": getattr(invoice, "buyer_name", ""),
        }

    @staticmethod
    def detail_filtered_for_query(
        detail: dict[str, object],
        *,
        plate: str | None,
        keyword: str | None,
    ) -> dict[str, object]:
        normalized_plate = str(plate or "").strip().lower()
        normalized_keyword = str(keyword or "").strip().lower()
        if not normalized_plate and not normalized_keyword:
            return detail
        invoice_items = [
            item
            for item in list(detail.get("invoiceItems") or [])
            if isinstance(item, dict)
            and (
                not normalized_plate
                or normalized_plate in str(item.get("plate_number", "") or "").lower()
            )
            and (
                not normalized_keyword
                or any(
                    normalized_keyword in str(item.get(field, "") or "").lower()
                    for field in ("invoice_number", "seller_name", "buyer_name", "plate_number")
                )
            )
        ]
        plates = {
            str(item.get("plate_number", "") or "").strip()
            for item in invoice_items
            if str(item.get("plate_number", "") or "").strip()
        }
        plate_summary = [
            item
            for item in list(detail.get("plateSummary") or [])
            if isinstance(item, dict)
            and (not plates or str(item.get("plate_number", "") or "").strip() in plates)
        ]
        return {
            **detail,
            "plateSummary": plate_summary,
            "invoiceItems": list(invoice_items),
        }
