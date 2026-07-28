from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from threading import RLock
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.oa_adapter import (
    ETC_BATCH_SOURCE,
    ETC_BATCH_TAG,
    InMemoryOAAdapter,
    OAAdapter,
    OAApplicationRecord,
    build_attachment_invoice_detail_fields,
    detect_etc_batch_metadata,
)


OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"
OA_ATTACHMENT_PAYMENT_RECEIPT_SOURCE_KIND = "oa_attachment_payment_receipt"
OA_ATTACHMENT_UNKNOWN_SOURCE_KIND = "oa_attachment_unknown"
OA_ATTACHMENT_EVIDENCE_SOURCE_KINDS = {
    OA_ATTACHMENT_INVOICE_SOURCE_KIND,
    OA_ATTACHMENT_PAYMENT_RECEIPT_SOURCE_KIND,
    OA_ATTACHMENT_UNKNOWN_SOURCE_KIND,
}
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()


class WorkbenchQueryService:
    def __init__(
        self,
        *,
        oa_adapter: OAAdapter | None = None,
        bank_account_resolver: BankAccountResolver | None = None,
        seed_demo_rows: bool = True,
    ) -> None:
        self._bank_account_resolver = bank_account_resolver or BankAccountResolver()
        self._oa_adapter = oa_adapter or InMemoryOAAdapter(self._seed_oa_records() if seed_demo_rows else {})
        self._records_by_id: dict[str, dict[str, Any]] = {}
        self._records_lock = RLock()
        self._has_full_oa_snapshot = False
        if seed_demo_rows:
            self._seed_all_rows()

    def get_workbench(self, month: str) -> dict[str, Any]:
        if month == "all":
            self._sync_all_oa_rows()
            month_rows = self.list_record_snapshots()
        else:
            self._sync_oa_rows(month)
            month_rows = [row for row in self.list_record_snapshots() if row["_month"] == month]
        paired_rows = [row for row in month_rows if row["_section"] == "paired"]
        unpaired_rows = [row for row in month_rows if row["_section"] == "unpaired"]

        return {
            "month": month,
            "oa_status": self.oa_status_payload(),
            "summary": {
                "oa_count": sum(1 for row in month_rows if row["type"] == "oa"),
                "bank_count": sum(1 for row in month_rows if row["type"] == "bank"),
                "invoice_count": sum(1 for row in month_rows if row["type"] == "invoice"),
                "paired_count": len(paired_rows),
                "unpaired_count": len(unpaired_rows),
                "exception_count": sum(1 for row in unpaired_rows if self._relation_payload(row)["tone"] == "danger"),
            },
            "paired": self._group_rows(paired_rows),
            "unpaired": self._group_rows(unpaired_rows),
        }

    def list_oa_rows(self, month: str) -> list[dict[str, Any]]:
        """Return only the serialized OA rows needed by the SQL projection."""
        normalized_month = str(month or "").strip()
        if normalized_month == "all":
            self._sync_all_oa_rows()
        else:
            self._sync_oa_rows(normalized_month)
        return [
            self.serialize_row(row)
            for row in self.list_record_snapshots()
            if row["type"] == "oa"
            and (normalized_month == "all" or row["_month"] == normalized_month)
        ]

    def oa_status_payload(self) -> dict[str, str]:
        adapter = self._oa_adapter
        get_read_status = getattr(adapter, "get_read_status", None)
        if callable(get_read_status):
            status = get_read_status()
            code = str(getattr(status, "code", "")).strip() or "ready"
            message = str(getattr(status, "message", "")).strip() or "OA 已同步"
            return {"code": code, "message": message}
        return {"code": "ready", "message": "OA 已同步"}

    def _sync_all_oa_rows(self) -> None:
        list_all_application_records = getattr(self._oa_adapter, "list_all_application_records", None)
        if callable(list_all_application_records):
            self._sync_oa_record_collection(
                list_all_application_records(),
                target_months=self._tracked_oa_months(),
            )
            self._has_full_oa_snapshot = True
            return
        for month in self.list_available_months():
            self._sync_oa_rows(month)
        self._has_full_oa_snapshot = True

    def sync_oa_row_ids(self, row_ids: list[str]) -> None:
        list_application_records_by_row_ids = getattr(self._oa_adapter, "list_application_records_by_row_ids", None)
        if not callable(list_application_records_by_row_ids):
            return
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not normalized_row_ids:
            return
        self._sync_oa_record_collection(
            list_application_records_by_row_ids(normalized_row_ids),
            prune_missing=False,
        )

    def list_available_months(self) -> list[str]:
        months = {
            str(row.get("_month", "")).strip()
            for row in self.list_record_snapshots()
            if str(row.get("_month", "")).strip()
        }
        adapter = self._oa_adapter
        list_available_months = getattr(adapter, "list_available_months", None)
        if callable(list_available_months):
            months.update(
                str(month).strip()
                for month in list_available_months()
                if str(month).strip()
            )
        return sorted(months)

    def get_row_detail(self, row_id: str) -> dict[str, Any]:
        row = self.get_row_record(row_id)
        payload = self.serialize_row(row)
        payload["summary_fields"] = deepcopy(row["_summary_fields"])
        payload["detail_fields"] = deepcopy(row["_detail_fields"])
        return payload

    def get_row_record(self, row_id: str, *, month_hint: str | None = None) -> dict[str, Any]:
        if row_id not in self._records_by_id:
            normalized_month_hint = str(month_hint).strip() if month_hint not in (None, "") else None
            can_lookup_by_row_id = callable(getattr(self._oa_adapter, "list_application_records_by_row_ids", None))
            if self._looks_like_oa_row_id(row_id) and can_lookup_by_row_id:
                self.sync_oa_row_ids([row_id])
            if row_id not in self._records_by_id and normalized_month_hint and normalized_month_hint != "all":
                self._sync_oa_rows(normalized_month_hint)
            elif row_id not in self._records_by_id and not can_lookup_by_row_id:
                self._sync_all_oa_rows()
        if (
            row_id not in self._records_by_id
            and month_hint not in (None, "", "all")
            and self._looks_like_oa_row_id(row_id)
        ):
            self._sync_all_oa_rows()
        return self._records_by_id[row_id]

    @staticmethod
    def _looks_like_oa_row_id(row_id: str) -> bool:
        return str(row_id).strip().lower().startswith("oa-")

    def serialize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = {key: deepcopy(value) for key, value in row.items() if not key.startswith("_")}
        summary_fields = row.get("_summary_fields")
        if isinstance(summary_fields, dict):
            payload["summary_fields"] = deepcopy(summary_fields)
        detail_fields = row.get("_detail_fields")
        if isinstance(detail_fields, dict):
            payload["detail_fields"] = deepcopy(detail_fields)
        return payload

    def relation_field_name(self, row_type: str) -> str:
        return {
            "oa": "oa_bank_relation",
            "bank": "invoice_relation",
            "invoice": "invoice_bank_relation",
        }[row_type]

    def set_relation(self, row: dict[str, Any], *, code: str, label: str, tone: str) -> None:
        row[self.relation_field_name(row["type"])] = {"code": code, "label": label, "tone": tone}

    def pending_relation(self, row_type: str) -> dict[str, str]:
        if row_type == "oa":
            return {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}
        if row_type == "bank":
            return {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"}
        return {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"}

    @staticmethod
    def linked_relation() -> dict[str, str]:
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

    def available_actions(self, row_type: str, section: str) -> list[str]:
        if row_type == "bank":
            return ["detail", "view_relation", "cancel_link", "handle_exception"]
        if row_type == "invoice" and section == "unpaired":
            return ["detail", "confirm_link", "mark_exception", "ignore"]
        if section == "unpaired":
            return ["detail", "confirm_link", "mark_exception"]
        return ["detail", "cancel_link"]

    def replace_row(self, row_id: str, row: dict[str, Any]) -> None:
        with self._records_lock:
            self._records_by_id[row_id] = row

    def list_record_snapshots(self) -> list[dict[str, Any]]:
        with self._records_lock:
            return list(self._records_by_id.copy().values())

    def _relation_payload(self, row: dict[str, Any]) -> dict[str, str]:
        return row[self.relation_field_name(row["type"])]

    def _group_rows(self, rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            grouped[row["type"]].append(self.serialize_row(row))
        return grouped

    def _seed_all_rows(self) -> None:
        for month in ("2026-03", "2026-04"):
            for bank_row in self._seed_bank_rows(month):
                self._add_row(bank_row)
            for invoice_row in self._seed_invoice_rows(month):
                self._add_row(invoice_row)

    def _add_row(self, row: dict[str, Any]) -> None:
        with self._records_lock:
            self._records_by_id[row["id"]] = row

    def _sync_oa_rows(self, month: str) -> None:
        self._sync_oa_record_collection(
            self._oa_adapter.list_application_records(month),
            target_months={str(month).strip()},
        )

    def _sync_oa_record_collection(
        self,
        records: list[OAApplicationRecord | object],
        *,
        target_months: set[str] | None = None,
        prune_missing: bool = True,
    ) -> None:
        with self._records_lock:
            seen_ids: set[str] = set()
            attachment_invoice_rows_by_id: dict[str, dict[str, Any]] = {}
            normalized_target_months = {
                str(month).strip()
                for month in list(target_months or [])
                if str(month).strip()
            }
            for record in records:
                record_month = str(getattr(record, "month", "")).strip()
                if record_month:
                    normalized_target_months.add(record_month)
                new_row = self._build_oa_row(record)
                existing = self._records_by_id.get(new_row["id"])
                if existing is not None:
                    new_row = self._merge_existing_oa_row(existing, new_row)
                self._records_by_id[new_row["id"]] = new_row
                seen_ids.add(new_row["id"])
                for attachment_row in self._build_oa_attachment_invoice_rows(record, new_row):
                    attachment_invoice_rows_by_id[str(attachment_row["id"])] = attachment_row
            self._remove_legacy_attachment_invoice_rows(
                target_months=normalized_target_months if prune_missing else set(),
                derived_from_oa_ids=seen_ids,
            )
            for row_id, attachment_row in attachment_invoice_rows_by_id.items():
                self._records_by_id[row_id] = attachment_row

            if not prune_missing:
                return

            for row_id, row in list(self._records_by_id.items()):
                if normalized_target_months and row["_month"] not in normalized_target_months:
                    continue
                if row["type"] == "oa" and row_id not in seen_ids:
                    relation = row["oa_bank_relation"]
                    if row["_section"] == "unpaired" and relation["code"] in {"pending_match", "oa_pending_approval"}:
                        del self._records_by_id[row_id]
                    continue

    def _build_oa_attachment_invoice_rows(
        self,
        record: OAApplicationRecord | object,
        oa_row: dict[str, Any],
    ) -> list[dict[str, Any]]:
        attachment_invoices = self._attachment_invoices(record)
        if not attachment_invoices:
            attachment_invoices = [
                evidence
                for evidence in self._attachment_evidences(record)
                if self._attachment_evidence_source_kind(evidence) == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            ]
        rows: list[dict[str, Any]] = []
        oa_row_id = str(oa_row.get("id") or "").strip()
        if not oa_row_id:
            return rows
        for index, attachment_invoice in enumerate(attachment_invoices):
            source_kind = self._attachment_evidence_source_kind(attachment_invoice)
            if source_kind != OA_ATTACHMENT_INVOICE_SOURCE_KIND:
                continue
            row_id = OBJECT_IDENTITY_POLICY.oa_attachment_invoice_row_id(oa_row_id, index, attachment_invoice)
            source_expense_item_id = str(attachment_invoice.get("source_expense_item_id") or "").strip()
            source_attachment_key = str(attachment_invoice.get("source_attachment_key") or "").strip()
            source_attachment_name = str(
                attachment_invoice.get("source_attachment_name")
                or attachment_invoice.get("attachment_name")
                or ""
            ).strip()
            invoice_no = self._invoice_identity_display_value(attachment_invoice.get("invoice_no"))
            digital_invoice_no = self._invoice_identity_display_value(attachment_invoice.get("digital_invoice_no"))
            invoice_code = self._invoice_identity_display_value(attachment_invoice.get("invoice_code"))
            issue_date = self._invoice_identity_display_value(
                attachment_invoice.get("issue_date") or attachment_invoice.get("invoice_date")
            )
            amount = str(attachment_invoice.get("amount") or attachment_invoice.get("total_with_tax") or "0.00").strip()
            total_with_tax = str(attachment_invoice.get("total_with_tax") or amount or "0.00").strip()
            tax_amount = str(attachment_invoice.get("tax_amount") or "0.00").strip()
            invoice_type = str(attachment_invoice.get("invoice_type") or "进项发票").strip() or "进项发票"
            seller_name = str(attachment_invoice.get("seller_name") or attachment_invoice.get("merchant_name") or "").strip()
            buyer_name = str(attachment_invoice.get("buyer_name") or "").strip()
            tags = ["OA附件"]
            source_link = {
                "source_type": OA_ATTACHMENT_INVOICE_SOURCE_KIND,
                "derived_from_oa_id": oa_row_id,
                "source_workbench_row_id": row_id,
                "source_expense_item_id": source_expense_item_id,
                "source_attachment_key": source_attachment_key,
                "source_attachment_name": source_attachment_name,
                "source_expense_row_index": str(attachment_invoice.get("source_expense_row_index") or ""),
                "source_region_key": str(attachment_invoice.get("source_region_key") or ""),
                "evidence_type": str(attachment_invoice.get("evidence_type") or ""),
                "document_kind": str(attachment_invoice.get("document_kind") or ""),
            }
            detail_fields = {
                "序号": row_id,
                "发票代码": invoice_code,
                "发票号码": invoice_no,
                "数电发票号码": digital_invoice_no,
                "销方识别号": self._invoice_identity_display_value(attachment_invoice.get("seller_tax_no")),
                "销方名称": seller_name or "—",
                "购方识别号": self._invoice_identity_display_value(attachment_invoice.get("buyer_tax_no")),
                "购买方名称": buyer_name or "—",
                "开票日期": issue_date,
                "金额": amount,
                "税率": str(attachment_invoice.get("tax_rate") or "—"),
                "税额": tax_amount,
                "价税合计": total_with_tax,
                "发票类型": invoice_type,
                "发票来源": "OA附件解析",
                "发票票种": str(attachment_invoice.get("invoice_kind") or "—"),
                "备注": str(attachment_invoice.get("remark") or "—"),
                "标签": "、".join(tags),
                "来源OA单号": self._oa_display_number_for_attachment_invoice(oa_row),
                "来源付款项ID": source_expense_item_id or "—",
                "来源附件Key": source_attachment_key or "—",
                "附件文件名": source_attachment_name or "—",
            }
            rows.append(
                {
                    "id": row_id,
                    "type": "invoice",
                    "source_kind": OA_ATTACHMENT_INVOICE_SOURCE_KIND,
                    "status": "unpaired",
                    "case_id": None,
                    "seller_tax_no": str(attachment_invoice.get("seller_tax_no") or ""),
                    "seller_name": seller_name,
                    "buyer_tax_no": str(attachment_invoice.get("buyer_tax_no") or ""),
                    "buyer_name": buyer_name,
                    "invoice_code": invoice_code,
                    "invoice_no": invoice_no,
                    "digital_invoice_no": digital_invoice_no,
                    "issue_date": issue_date,
                    "counterparty_name": seller_name or buyer_name,
                    "amount": amount,
                    "tax_rate": str(attachment_invoice.get("tax_rate") or "—"),
                    "tax_amount": tax_amount,
                    "total_with_tax": total_with_tax,
                    "invoice_type": invoice_type,
                    "invoice_bank_relation": self.pending_relation("invoice"),
                    "tags": tags,
                    "source_links": [source_link],
                    "derived_from_oa_id": oa_row_id,
                    "source_workbench_row_id": row_id,
                    "source_attachment_key": source_attachment_key,
                    "source_attachment_name": source_attachment_name,
                    "source_expense_item_id": source_expense_item_id,
                    "source_expense_row_index": source_link["source_expense_row_index"],
                    "source_region_key": source_link["source_region_key"],
                    "evidence_type": source_link["evidence_type"],
                    "document_kind": source_link["document_kind"],
                    "source_oa_month": str(getattr(record, "month", "") or oa_row.get("_month") or ""),
                    "available_actions": self.available_actions("invoice", "unpaired"),
                    "summary_fields": {
                        "销方名称": seller_name or "—",
                        "购买方名称": buyer_name or "—",
                        "开票日期": issue_date,
                        "金额": amount,
                        "税额": tax_amount,
                        "价税合计": total_with_tax,
                        "发票类型": invoice_type,
                        "发票来源": "OA附件解析",
                    },
                    "detail_fields": detail_fields,
                    "_month": str(getattr(record, "month", "") or oa_row.get("_month") or ""),
                    "_section": str(oa_row.get("_section") or "unpaired"),
                    "_summary_fields": {
                        "销方名称": seller_name or "—",
                        "购买方名称": buyer_name or "—",
                        "开票日期": issue_date,
                        "价税合计": total_with_tax,
                        "发票类型": invoice_type,
                    },
                    "_detail_fields": detail_fields,
                }
            )
        return rows

    def _remove_legacy_attachment_invoice_rows(
        self,
        *,
        target_months: set[str],
        derived_from_oa_ids: set[str],
    ) -> None:
        for row_id, row in list(self._records_by_id.items()):
            if row.get("type") != "invoice" or row.get("source_kind") not in OA_ATTACHMENT_EVIDENCE_SOURCE_KINDS:
                continue
            row_month = str(row.get("_month", "")).strip()
            derived_from_oa_id = str(row.get("derived_from_oa_id", "")).strip()
            if derived_from_oa_id in derived_from_oa_ids or (target_months and row_month in target_months):
                del self._records_by_id[row_id]

    def _tracked_oa_months(self) -> set[str]:
        tracked_months: set[str] = set()
        for row in self.list_record_snapshots():
            row_type = str(row.get("type"))
            if row_type == "oa":
                row_month = str(row.get("_month", "")).strip()
                if row_month:
                    tracked_months.add(row_month)
        return tracked_months

    def _merge_existing_oa_row(self, existing: dict[str, Any], refreshed: dict[str, Any]) -> dict[str, Any]:
        relation = existing.get("oa_bank_relation", {})
        if relation.get("code") not in {"pending_match", "oa_pending_approval"}:
            refreshed["oa_bank_relation"] = deepcopy(relation)
            refreshed["case_id"] = existing.get("case_id")
            refreshed["_section"] = existing.get("_section", refreshed["_section"])
            refreshed["available_actions"] = self.available_actions("oa", refreshed["_section"])
        return refreshed

    def _build_oa_row(self, record: OAApplicationRecord) -> dict[str, Any]:
        section = self._normalize_workbench_section(record.section)
        source_metadata = self._oa_source_metadata(record)
        source = source_metadata.get("source")
        etc_batch_id = source_metadata.get("etc_batch_id")
        relation = {
            "code": record.relation_code,
            "label": self._oa_relation_label(record, source=source),
            "tone": record.relation_tone,
        }
        attachment_evidences = self._attachment_evidences(record)
        attachment_invoices = self._attachment_invoices(record)
        if attachment_evidences and not attachment_invoices:
            attachment_invoices = [
                evidence
                for evidence in attachment_evidences
                if self._attachment_evidence_source_kind(evidence) == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            ]
        attachment_artifacts = self._attachment_artifacts(record)
        attachment_file_count = self._attachment_file_count(record)
        detail_fields = deepcopy(record.detail_fields)
        self._enrich_aggregated_oa_detail_fields(record, detail_fields)
        project_name = str(getattr(record, "project_name", "") or "--")
        project_names = self._record_project_names(record, project_name)
        project_name_display = self._record_project_name_display(record, project_names, project_name)
        detail_fields.setdefault("项目名称汇总", project_name)
        detail_fields.setdefault("项目名称列表", list(project_names))
        detail_fields.update(
            build_attachment_invoice_detail_fields(
                attachment_invoices,
                attachment_file_count=attachment_file_count,
                attachment_evidences=attachment_evidences,
                attachment_artifacts=attachment_artifacts,
            )
        )
        case_id = record.case_id or None
        apply_time = self._first_oa_time_value(
            detail_fields.get("申请时间"),
            detail_fields.get("申请日期"),
        )
        completed_at = self._first_oa_time_value(detail_fields.get("审批完成时间"))
        tags = self._oa_row_tags(
            existing_tags=list(source_metadata.get("tags") or []),
            attachment_invoice_count=len(attachment_invoices),
            attachment_file_count=attachment_file_count,
            attachment_evidence_count=len(attachment_evidences),
            has_attachment_parse_failure=self._has_attachment_parse_failure(attachment_artifacts),
            has_multiple_expense_items=len(self._expense_items(record)) > 1,
            has_amount_mismatch=self._amount_mismatch(record) is not None,
        )
        reconciliation_amount = self._oa_reconciliation_amount(record, detail_fields)
        return {
            "id": record.id,
            "type": "oa",
            "case_id": case_id,
            "applicant": record.applicant,
            "project_name": project_name,
            "project_name_display": project_name_display,
            "project_names": list(project_names),
            "expense_items": self._workbench_expense_items(record),
            "expense_type": record.expense_type,
            "expense_content": record.expense_content,
            "apply_type": record.apply_type,
            "apply_time": apply_time,
            "application_time": apply_time,
            "application_date": apply_time,
            "completed_at": completed_at,
            "amount": record.amount,
            "amount_source": getattr(record, "amount_source", None),
            "amount_mismatch": self._amount_mismatch(record),
            "reconciliation_amount": reconciliation_amount,
            "counterparty_name": record.counterparty_name,
            "reason": record.reason,
            "oa_bank_relation": relation,
            "available_actions": self.available_actions("oa", section),
            "tags": tags,
            "source": source,
            "etc_batch_id": etc_batch_id,
            "etcBatchId": etc_batch_id,
            "_month": record.month,
            "_section": section,
            "_summary_fields": {
                "申请人": record.applicant,
                "项目名称": project_name_display,
                "申请类型": record.apply_type,
                "金额": record.amount,
                "对方户名": record.counterparty_name,
                "申请事由": record.reason,
                "OA和流水关联情况": record.relation_label,
            },
            "_detail_fields": detail_fields,
        }

    @classmethod
    def _workbench_expense_items(
        cls,
        record: OAApplicationRecord | object,
    ) -> list[dict[str, str]]:
        result: list[dict[str, str]] = []
        for item in cls._expense_items(record):
            item_id = str(item.get("expense_item_id") or "").strip()
            if not item_id:
                continue
            result.append(
                {
                    "id": item_id,
                    "row_index": str(item.get("row_index") or "").strip(),
                    "project_name": str(item.get("project_name") or "—").strip() or "—",
                    "amount": str(item.get("amount") or "").strip(),
                    "fee_content": str(item.get("fee_content") or "").strip(),
                    "fee_description": str(item.get("fee_description") or "").strip(),
                }
            )
        return result

    @staticmethod
    def _normalize_workbench_section(section: object) -> str:
        normalized = str(section or "").strip().lower()
        if normalized == "paired":
            return "paired"
        if normalized == "unpaired":
            return "unpaired"
        raise ValueError(f"Unsupported OA Workbench section: {section!r}")

    @classmethod
    def _record_project_name_display(
        cls,
        record: OAApplicationRecord | object,
        project_names: list[str],
        project_name: str,
    ) -> str:
        display = str(getattr(record, "project_name_display", "") or "").strip()
        if display:
            return display
        if len(project_names) > 1:
            return "多个项目"
        if len(project_names) == 1:
            return project_names[0]
        return project_name or "--"

    @classmethod
    def _record_project_names(cls, record: OAApplicationRecord | object, project_name: str) -> list[str]:
        raw_project_names = getattr(record, "project_names", None)
        if isinstance(raw_project_names, list):
            project_names = cls._unique_detail_values(raw_project_names)
            if project_names:
                return project_names
        return cls._unique_detail_values(str(project_name or "").split("；"))

    @staticmethod
    def _oa_source_metadata(record: OAApplicationRecord | object) -> dict[str, Any]:
        detected = detect_etc_batch_metadata(
            getattr(record, "reason", ""),
            getattr(record, "expense_content", ""),
            getattr(record, "detail_fields", {}),
        )
        source = str(getattr(record, "source", "") or detected.get("source") or "").strip()
        etc_batch_id = str(getattr(record, "etc_batch_id", "") or detected.get("etc_batch_id") or "").strip()
        tags = [
            str(tag).strip()
            for tag in [*list(getattr(record, "tags", []) or []), *list(detected.get("tags") or [])]
            if str(tag).strip()
        ]
        if source == ETC_BATCH_SOURCE and etc_batch_id and ETC_BATCH_TAG not in tags:
            tags.append(ETC_BATCH_TAG)
        return {
            "source": source or None,
            "etc_batch_id": etc_batch_id or None,
            "tags": tags,
        }

    @staticmethod
    def _oa_relation_label(record: OAApplicationRecord | object, *, source: str | None) -> str:
        relation_code = str(getattr(record, "relation_code", "") or "")
        relation_label = str(getattr(record, "relation_label", "") or "")
        if source == ETC_BATCH_SOURCE and relation_code == "pending_match":
            return "待找流水"
        return relation_label

    @staticmethod
    def _oa_row_tags(
        *,
        existing_tags: object,
        attachment_invoice_count: int,
        attachment_file_count: int,
        attachment_evidence_count: int = 0,
        has_attachment_parse_failure: bool = False,
        has_multiple_expense_items: bool = False,
        has_amount_mismatch: bool = False,
    ) -> list[str]:
        tags = [
            str(tag).strip()
            for tag in list(existing_tags or [])
            if str(tag).strip()
        ] if isinstance(existing_tags, list) else []
        has_unparsed_invoice_risk = (
            attachment_file_count > 0
            and attachment_invoice_count == 0
            and (attachment_evidence_count == 0 or has_attachment_parse_failure)
        )
        if has_unparsed_invoice_risk and "未解析发票" not in tags:
            tags.append("未解析发票")
        if has_multiple_expense_items and "多明细" not in tags:
            tags.append("多明细")
        if has_amount_mismatch and "金额差异" not in tags:
            tags.append("金额差异")
        return tags

    @staticmethod
    def _has_attachment_parse_failure(attachment_artifacts: list[dict[str, Any]]) -> bool:
        failure_statuses = {"download_failed", "parse_failed"}
        return any(str(artifact.get("parse_status") or "").strip() in failure_statuses for artifact in attachment_artifacts)

    @staticmethod
    def _expense_items(record: OAApplicationRecord | object) -> list[dict[str, str]]:
        expense_items = getattr(record, "expense_items", [])
        if not isinstance(expense_items, list):
            return []
        return [dict(item) for item in expense_items if isinstance(item, dict)]

    @staticmethod
    def _amount_mismatch(record: OAApplicationRecord | object) -> dict[str, str] | None:
        mismatch = getattr(record, "amount_mismatch", None)
        return dict(mismatch) if isinstance(mismatch, dict) else None

    @classmethod
    def _enrich_aggregated_oa_detail_fields(
        cls,
        record: OAApplicationRecord | object,
        detail_fields: dict[str, Any],
    ) -> None:
        amount_source = str(getattr(record, "amount_source", "") or "").strip()
        if amount_source and "金额来源" not in detail_fields:
            detail_fields["金额来源"] = "主表总金额" if amount_source == "header" else "明细合计"

        expense_items = cls._expense_items(record)
        if expense_items:
            detail_fields.setdefault("明细数量", str(len(expense_items)))
            detail_amounts = [
                str(item.get("amount") or "").strip()
                for item in expense_items
                if str(item.get("amount") or "").strip() not in {"", "—", "--"}
            ]
            contents = cls._unique_detail_values(item.get("expense_content") for item in expense_items)
            if contents:
                detail_fields.setdefault("费用内容摘要", "；".join(contents))
            if detail_amounts:
                detail_fields.setdefault("明细金额合计", cls._sum_amount_texts(detail_amounts))

        mismatch = cls._amount_mismatch(record)
        if mismatch is not None and "金额差异" not in detail_fields:
            detail_fields["金额差异"] = (
                f"主表总金额 {mismatch.get('header_amount') or '—'}；"
                f"明细合计 {mismatch.get('detail_sum') or '—'}；"
                f"差异 {mismatch.get('difference') or '—'}"
            )

    @classmethod
    def _oa_reconciliation_amount(
        cls,
        record: OAApplicationRecord | object,
        detail_fields: dict[str, Any],
    ) -> str | None:
        amount_source = str(getattr(record, "amount_source", "") or "").strip()
        mismatch = cls._amount_mismatch(record)
        if amount_source != "header" or mismatch is None:
            return None
        detail_sum = str(mismatch.get("detail_sum") or detail_fields.get("明细金额合计") or "").strip()
        if not detail_sum:
            return None
        normalized = detail_sum.replace(",", "").replace("，", "")
        try:
            return f"{Decimal(normalized).quantize(Decimal('0.01')):.2f}"
        except (InvalidOperation, ValueError):
            return detail_sum

    @staticmethod
    def _first_oa_time_value(*values: Any) -> str | None:
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in {"—", "--", "None"}:
                return normalized
        return None

    @staticmethod
    def _unique_detail_values(values: Any) -> list[str]:
        result: list[str] = []
        for value in values:
            text = str(value or "").strip()
            if text and text not in {"—", "--"} and text not in result:
                result.append(text)
        return result

    @staticmethod
    def _sum_amount_texts(values: list[str]) -> str:
        total = Decimal("0")
        decimal_places = 0
        for value in values:
            normalized = value.replace(",", "").replace("，", "")
            if "." in normalized:
                decimal_places = max(decimal_places, len(normalized.rsplit(".", 1)[1]))
            try:
                total += Decimal(normalized)
            except (InvalidOperation, ValueError):
                return "；".join(values)
        quantizer = Decimal("1").scaleb(-decimal_places)
        return f"{total.quantize(quantizer):f}"

    @staticmethod
    def _attachment_invoices(record: OAApplicationRecord | object) -> list[dict[str, str]]:
        invoices = getattr(record, "attachment_invoices", [])
        if not isinstance(invoices, list):
            return []
        return [dict(invoice) for invoice in invoices if isinstance(invoice, dict)]

    @staticmethod
    def _attachment_evidences(record: OAApplicationRecord | object) -> list[dict[str, Any]]:
        evidences = getattr(record, "attachment_evidences", [])
        if not isinstance(evidences, list):
            return []
        return [dict(evidence) for evidence in evidences if isinstance(evidence, dict)]

    @staticmethod
    def _attachment_artifacts(record: OAApplicationRecord | object) -> list[dict[str, Any]]:
        artifacts = getattr(record, "attachment_artifacts", [])
        if not isinstance(artifacts, list):
            return []
        return [dict(artifact) for artifact in artifacts if isinstance(artifact, dict)]

    @staticmethod
    def _attachment_file_count(record: OAApplicationRecord | object) -> int:
        try:
            return max(int(getattr(record, "attachment_file_count", 0) or 0), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _invoice_identity_display_value(value: Any) -> str:
        text = str(value or "").strip()
        return text if text and text not in {"—", "--"} else "—"

    @staticmethod
    def _oa_display_number_for_attachment_invoice(oa_row: dict[str, Any]) -> str:
        for fields_key in ("_detail_fields", "detail_fields", "_summary_fields", "summary_fields"):
            fields = oa_row.get(fields_key)
            if isinstance(fields, dict):
                for key in ("OA单号", "单据编号", "申请单号"):
                    value = str(fields.get(key) or "").strip()
                    if value:
                        return value
        return str(oa_row.get("id") or "—")

    @staticmethod
    def _attachment_evidence_source_kind(attachment_evidence: dict[str, Any]) -> str:
        explicit_source_kind = str(attachment_evidence.get("source_kind") or "").strip()
        if explicit_source_kind in OA_ATTACHMENT_EVIDENCE_SOURCE_KINDS:
            return explicit_source_kind
        evidence_type = str(attachment_evidence.get("evidence_type") or "").strip()
        if not evidence_type:
            return (
                OA_ATTACHMENT_INVOICE_SOURCE_KIND
                if WorkbenchQueryService._attachment_evidence_has_invoice_identity(attachment_evidence)
                else OA_ATTACHMENT_UNKNOWN_SOURCE_KIND
            )
        if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(attachment_evidence):
            return OA_ATTACHMENT_INVOICE_SOURCE_KIND
        if evidence_type == "payment_receipt":
            return OA_ATTACHMENT_PAYMENT_RECEIPT_SOURCE_KIND
        return OA_ATTACHMENT_UNKNOWN_SOURCE_KIND

    @staticmethod
    def _attachment_evidence_has_invoice_identity(attachment_evidence: dict[str, Any]) -> bool:
        return OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(attachment_evidence)

    def _seed_oa_records(self) -> dict[str, list[OAApplicationRecord]]:
        return {
            "2026-03": [
                OAApplicationRecord(
                    id="oa-p-202603-001",
                    month="2026-03",
                    section="paired",
                    case_id="CASE-202603-001",
                    applicant="赵华",
                    project_name="华东改造项目",
                    apply_type="供应商付款申请",
                    amount="128,000.00",
                    counterparty_name="华东设备供应商",
                    reason="设备首付款支付",
                    relation_code="fully_linked",
                    relation_label="完全关联",
                    relation_tone="success",
                    detail_fields={
                        "OA单号": "OA-202603-001",
                        "审批完成时间": "2026-03-25 11:05",
                        "当前流程": "财务复核完成",
                        "创建部门": "华东交付部",
                    },
                ),
                OAApplicationRecord(
                    id="oa-o-202603-001",
                    month="2026-03",
                    section="unpaired",
                    case_id="CASE-202603-101",
                    applicant="陈涛",
                    project_name="智能工厂项目",
                    apply_type="供应商付款申请",
                    amount="58,000.00",
                    counterparty_name="智能工厂设备商",
                    reason="设备尾款待支付",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                    detail_fields={
                        "OA单号": "OA-202603-101",
                        "审批完成时间": "2026-03-28 18:10",
                        "当前流程": "待出纳付款",
                        "创建部门": "智能制造事业部",
                    },
                ),
                OAApplicationRecord(
                    id="oa-o-202603-002",
                    month="2026-03",
                    section="unpaired",
                    case_id="CASE-202603-102",
                    applicant="周颖",
                    project_name="项目支持",
                    apply_type="差旅报销",
                    amount="1,320.00",
                    counterparty_name="交通出行",
                    reason="现场拜访交通费",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                    detail_fields={
                        "OA单号": "OA-202603-102",
                        "审批完成时间": "2026-03-29 09:45",
                        "当前流程": "待银行流水确认",
                        "创建部门": "客户成功部",
                    },
                ),
            ],
            "2026-04": [
                OAApplicationRecord(
                    id="oa-p-202604-001",
                    month="2026-04",
                    section="paired",
                    case_id="CASE-202604-001",
                    applicant="刘宁",
                    project_name="智能工厂二期",
                    apply_type="差旅报销",
                    amount="860.00",
                    counterparty_name="差旅服务商",
                    reason="现场实施差旅费",
                    relation_code="fully_linked",
                    relation_label="完全关联",
                    relation_tone="success",
                    detail_fields={
                        "OA单号": "OA-202604-001",
                        "审批完成时间": "2026-04-05 14:20",
                        "当前流程": "自动闭环",
                        "创建部门": "实施交付部",
                    },
                ),
                OAApplicationRecord(
                    id="oa-o-202604-001",
                    month="2026-04",
                    section="unpaired",
                    case_id="CASE-202604-101",
                    applicant="王青",
                    project_name="维保续费项目",
                    apply_type="市场费用",
                    amount="6,000.00",
                    counterparty_name="杭州张三广告有限公司",
                    reason="4月品牌投放尾款",
                    relation_code="pending_match",
                    relation_label="待找流水与发票",
                    relation_tone="warn",
                    detail_fields={
                        "OA单号": "OA-202604-101",
                        "审批完成时间": "2026-04-20 16:00",
                        "当前流程": "待财务核销",
                        "创建部门": "市场部",
                    },
                ),
            ],
        }

    def _seed_bank_rows(self, month: str) -> list[dict[str, Any]]:
        if month == "2026-03":
            return [
                self._build_bank_row(
                    row_id="bk-p-202603-001",
                    month=month,
                    section="paired",
                    case_id="CASE-202603-001",
                    trade_time="2026-03-25 14:22",
                    debit_amount="128,000.00",
                    credit_amount="",
                    counterparty_name="华东设备供应商",
                    account_no="622588889123",
                    account_name="杭州溯源科技有限公司招商银行基本户",
                    relation={"code": "fully_linked", "label": "完全关联", "tone": "success"},
                    pay_receive_time="2026-03-25 14:22",
                    remark="设备采购款，已闭环",
                    repayment_date="",
                    detail_fields={
                        "账号": "6225 **** **** 9123",
                        "账户名称": "杭州溯源科技有限公司招商银行基本户",
                        "余额": "2,488,310.55",
                        "币种": "CNY",
                        "对方账号": "6214 **** **** 4432",
                        "对方开户机构": "中国银行上海张江支行",
                        "记账日期": "2026-03-25",
                        "摘要": "设备供应商付款",
                        "备注": "OA 已闭环，进项票已核销",
                        "账户明细编号-交易流水号": "DET-20260325-101",
                        "企业流水号": "CORP-20260325-7781",
                        "凭证种类": "网银付款",
                        "凭证号": "VCH-031525-01",
                    },
                ),
                self._build_bank_row(
                    row_id="bk-o-202603-001",
                    month=month,
                    section="unpaired",
                    case_id="CASE-202603-101",
                    trade_time="2026-03-28 10:18",
                    debit_amount="58,000.00",
                    credit_amount="",
                    counterparty_name="智能工厂设备商",
                    account_no="621711331138",
                    account_name="杭州溯源科技有限公司建设银行一般户",
                    relation={"code": "pending_invoice_match", "label": "待关联设备票", "tone": "warn"},
                    pay_receive_time="2026-03-28 10:18",
                    remark="设备尾款待进项票",
                    repayment_date="",
                    detail_fields={
                        "账号": "6217 **** **** 1138",
                        "账户名称": "杭州溯源科技有限公司建设银行一般户",
                        "余额": "581,203.18",
                        "币种": "CNY",
                        "对方账号": "6226 **** **** 0021",
                        "对方开户机构": "建设银行苏州园区支行",
                        "记账日期": "2026-03-28",
                        "摘要": "设备尾款支付",
                        "备注": "待补进项票",
                        "账户明细编号-交易流水号": "DET-20260328-001",
                        "企业流水号": "CORP-20260328-0001",
                        "凭证种类": "转账支取",
                        "凭证号": "VCH-032810-02",
                    },
                ),
                self._build_bank_row(
                    row_id="bk-o-202603-002",
                    month=month,
                    section="unpaired",
                    case_id="CASE-202603-102",
                    trade_time="2026-03-29 09:18",
                    debit_amount="",
                    credit_amount="50,000.00",
                    counterparty_name="关联公司溯源科技",
                    account_no="622288885510",
                    account_name="杭州溯源科技有限公司工商银行专户",
                    relation={"code": "internal_review", "label": "待确认内部往来", "tone": "warn"},
                    pay_receive_time="2026-03-29 09:18",
                    remark="内部往来待补 OA / 借款台账",
                    repayment_date="2026-04-29",
                    detail_fields={
                        "账号": "6222 **** **** 5510",
                        "账户名称": "杭州溯源科技有限公司工商银行专户",
                        "余额": "1,608,204.70",
                        "币种": "CNY",
                        "对方账号": "6212 **** **** 7721",
                        "对方开户机构": "工商银行上海浦东支行",
                        "记账日期": "2026-03-29",
                        "摘要": "内部资金往来",
                        "备注": "需确认补贷款还是内部往来",
                        "账户明细编号-交易流水号": "DET-20260329-002",
                        "企业流水号": "CORP-20260329-1062",
                        "凭证种类": "转账收入",
                        "凭证号": "VCH-032909-01",
                    },
                ),
            ]

        return [
            self._build_bank_row(
                row_id="bk-p-202604-001",
                month=month,
                section="paired",
                case_id="CASE-202604-001",
                trade_time="2026-04-05 10:05",
                debit_amount="860.00",
                credit_amount="",
                counterparty_name="差旅服务商",
                account_no="621711331138",
                account_name="杭州溯源科技有限公司建设银行一般户",
                relation={"code": "fully_linked", "label": "完全关联", "tone": "success"},
                pay_receive_time="2026-04-05 10:05",
                remark="差旅报销已闭环",
                repayment_date="",
                detail_fields={
                    "账号": "6217 **** **** 1138",
                    "账户名称": "杭州溯源科技有限公司建设银行一般户",
                    "余额": "512,200.00",
                    "币种": "CNY",
                    "对方账号": "6217 **** **** 8872",
                    "对方开户机构": "建设银行杭州分行营业部",
                    "记账日期": "2026-04-05",
                    "摘要": "差旅报销付款",
                    "备注": "已与 OA 和进项票闭环",
                    "账户明细编号-交易流水号": "DET-20260405-001",
                    "企业流水号": "CORP-20260405-0101",
                    "凭证种类": "转账支取",
                    "凭证号": "VCH-040510-01",
                },
            ),
            self._build_bank_row(
                row_id="bk-o-202604-001",
                month=month,
                section="unpaired",
                case_id="CASE-202604-101",
                trade_time="2026-04-20 09:15",
                debit_amount="6,000.00",
                credit_amount="",
                counterparty_name="杭州张三广告有限公司",
                account_no="621488888821",
                account_name="杭州溯源科技有限公司中国银行基本户",
                relation={"code": "pending_invoice_match", "label": "待关联广告票", "tone": "warn"},
                pay_receive_time="2026-04-20 09:15",
                remark="应付6000，候选 OA-202604-101",
                repayment_date="",
                detail_fields={
                    "账号": "6214 **** **** 8821",
                    "账户名称": "杭州溯源科技有限公司中国银行基本户",
                    "余额": "451,220.56",
                    "币种": "CNY",
                    "对方账号": "6222 9033 1200",
                    "对方开户机构": "中国银行杭州分行",
                    "记账日期": "2026-04-20",
                    "摘要": "广告投放尾款",
                    "备注": "候选 OA-202604-101",
                    "账户明细编号-交易流水号": "B202604200019",
                    "企业流水号": "ENT202604200051",
                    "凭证种类": "转账支付",
                    "凭证号": "VCH-95112",
                },
            ),
        ]

    def _seed_invoice_rows(self, month: str) -> list[dict[str, Any]]:
        if month == "2026-03":
            return [
                self._build_invoice_row(
                    row_id="iv-p-202603-001",
                    month=month,
                    section="paired",
                    case_id="CASE-202603-001",
                    seller_tax_no="91310000MA1K8A001X",
                    seller_name="杭州溯源科技有限公司",
                    buyer_tax_no="91310110MA1F99088Q",
                    buyer_name="华东设备供应商",
                    issue_date="2026-03-25",
                    amount="128,000.00",
                    tax_rate="13%",
                    tax_amount="16,640.00",
                    total_with_tax="144,640.00",
                    invoice_type="进项专票",
                    relation={"code": "fully_linked", "label": "完全关联", "tone": "success"},
                    detail_fields={
                        "序号": "1",
                        "发票代码": "032002600111",
                        "发票号码": "00061345",
                        "数电发票号码": "DZFP-202603-9001",
                        "税收分类编码": "3040201000000000000",
                        "特定业务类型": "设备集成",
                        "货物或应税劳务名称": "工业控制设备",
                        "规格型号": "ICD-2000",
                        "单位": "套",
                        "数量": "1",
                        "单价": "128,000.00",
                        "发票来源": "税局数电",
                        "发票票种": "增值税电子专用发票",
                        "发票状态": "正常",
                        "是否正数发票": "是",
                        "发票风险等级": "低",
                        "开票人": "王青",
                        "备注": "已与银行付款和 OA 闭环",
                    },
                ),
                self._build_invoice_row(
                    row_id="iv-o-202603-001",
                    month=month,
                    section="unpaired",
                    case_id="CASE-202603-101",
                    seller_tax_no="91330108MA27B4011D",
                    seller_name="智能工厂设备商",
                    buyer_tax_no="91310000MA1K8A001X",
                    buyer_name="杭州溯源科技有限公司",
                    issue_date="2026-03-28",
                    amount="58,000.00",
                    tax_rate="13%",
                    tax_amount="7,540.00",
                    total_with_tax="65,540.00",
                    invoice_type="进项专票",
                    relation={"code": "pending_collection", "label": "待匹配付款", "tone": "warn"},
                    detail_fields={
                        "序号": "1",
                        "发票代码": "3300214130",
                        "发票号码": "12561048",
                        "数电发票号码": "--",
                        "税收分类编码": "1070401010000000000",
                        "特定业务类型": "设备采购",
                        "货物或应税劳务名称": "智能工厂设备",
                        "规格型号": "SMF-08",
                        "单位": "套",
                        "数量": "1",
                        "单价": "58,000.00",
                        "发票来源": "纸票扫描导入",
                        "发票票种": "增值税专用发票",
                        "发票状态": "正常",
                        "是否正数发票": "是",
                        "发票风险等级": "中",
                        "开票人": "孙蓉",
                        "备注": "待与设备尾款支出流水核销",
                    },
                ),
                self._build_invoice_row(
                    row_id="iv-o-202603-002",
                    month=month,
                    section="unpaired",
                    case_id="CASE-202603-103",
                    seller_tax_no="91330102MA8T32A2X7",
                    seller_name="杭州张三广告有限公司",
                    buyer_tax_no="91330106589876543T",
                    buyer_name="杭州溯源科技有限公司",
                    issue_date="2026-03-20",
                    amount="6,000.00",
                    tax_rate="6%",
                    tax_amount="339.62",
                    total_with_tax="6,000.00",
                    invoice_type="进项专票",
                    relation={"code": "pending_collection", "label": "待匹配付款", "tone": "warn"},
                    detail_fields={
                        "序号": "1",
                        "发票代码": "0330111200",
                        "发票号码": "90342011",
                        "数电发票号码": "DZFP-202603-1132",
                        "税收分类编码": "3040301000000000000",
                        "特定业务类型": "广告服务",
                        "货物或应税劳务名称": "广告投放服务",
                        "规格型号": "--",
                        "单位": "项",
                        "数量": "1",
                        "单价": "5,660.38",
                        "发票来源": "税局数电",
                        "发票票种": "增值税电子专用发票",
                        "发票状态": "正常",
                        "是否正数发票": "是",
                        "发票风险等级": "低",
                        "开票人": "李萍",
                        "备注": "待与广告付款流水核销",
                    },
                ),
            ]

        return [
            self._build_invoice_row(
                row_id="iv-p-202604-001",
                month=month,
                section="paired",
                case_id="CASE-202604-001",
                seller_tax_no="91310108MA1N22179P",
                seller_name="差旅服务商",
                buyer_tax_no="91310000MA1K8A001X",
                buyer_name="杭州溯源科技有限公司",
                issue_date="2026-04-05",
                amount="860.00",
                tax_rate="6%",
                tax_amount="51.60",
                total_with_tax="911.60",
                invoice_type="进项普票",
                relation={"code": "fully_linked", "label": "完全关联", "tone": "success"},
                detail_fields={
                    "序号": "1",
                    "发票代码": "144001918531",
                    "发票号码": "00853128",
                    "数电发票号码": "DZFP-202604-4021",
                    "税收分类编码": "3070201010000000000",
                    "特定业务类型": "差旅服务",
                    "货物或应税劳务名称": "交通及住宿服务",
                    "规格型号": "--",
                    "单位": "项",
                    "数量": "1",
                    "单价": "860.00",
                    "发票来源": "税局数电",
                    "发票票种": "增值税电子普通发票",
                    "发票状态": "正常",
                    "是否正数发票": "是",
                    "发票风险等级": "低",
                    "开票人": "张静",
                    "备注": "与差旅报销闭环",
                },
            ),
            self._build_invoice_row(
                row_id="iv-o-202604-001",
                month=month,
                section="unpaired",
                case_id="CASE-202604-101",
                seller_tax_no="91330102MA8T32A2X7",
                seller_name="杭州张三广告有限公司",
                buyer_tax_no="91330106589876543T",
                buyer_name="杭州溯源科技有限公司",
                issue_date="2026-04-20",
                amount="6,000.00",
                tax_rate="6%",
                tax_amount="339.62",
                total_with_tax="6,000.00",
                invoice_type="进项专票",
                relation={"code": "pending_collection", "label": "待匹配付款", "tone": "warn"},
                detail_fields={
                    "序号": "1",
                    "发票代码": "0330111201",
                    "发票号码": "90342012",
                    "数电发票号码": "DZFP-202604-9034",
                    "税收分类编码": "3040301000000000000",
                    "特定业务类型": "广告服务",
                    "货物或应税劳务名称": "广告投放服务",
                    "规格型号": "--",
                    "单位": "项",
                    "数量": "1",
                    "单价": "5,660.38",
                    "发票来源": "税局数电",
                    "发票票种": "增值税电子专用发票",
                    "发票状态": "正常",
                    "是否正数发票": "是",
                    "发票风险等级": "低",
                    "开票人": "李萍",
                    "备注": "待与广告投放尾款核销",
                },
            ),
        ]

    def _build_bank_row(
        self,
        *,
        row_id: str,
        month: str,
        section: str,
        case_id: str | None,
        trade_time: str,
        debit_amount: str,
        credit_amount: str,
        counterparty_name: str,
        account_no: str,
        account_name: str,
        relation: dict[str, str],
        pay_receive_time: str,
        remark: str,
        repayment_date: str,
        detail_fields: dict[str, str],
    ) -> dict[str, Any]:
        return {
            "id": row_id,
            "type": "bank",
            "case_id": case_id,
            "trade_time": trade_time,
            "account_no": account_no,
            "account_name": account_name,
            "counterparty_account_no": detail_fields.get("对方账号", ""),
            "debit_amount": debit_amount or None,
            "credit_amount": credit_amount or None,
            "counterparty_name": counterparty_name,
            "payment_account_label": self._bank_account_resolver.resolve_label(account_no, account_name),
            "invoice_relation": relation,
            "pay_receive_time": pay_receive_time,
            "summary": detail_fields.get("摘要", ""),
            "remark": remark,
            "repayment_date": repayment_date or None,
            "available_actions": self.available_actions("bank", section),
            "_month": month,
            "_section": section,
            "_summary_fields": {
                "交易时间": trade_time,
                "借方发生额": debit_amount or "—",
                "贷方发生额": credit_amount or "—",
                "对方户名": counterparty_name,
                "支付账户": self._bank_account_resolver.resolve_label(account_no, account_name),
                "和发票关联情况": relation["label"],
                "支付/收款时间": pay_receive_time,
                "备注": remark,
                "还借款日期": repayment_date or "—",
            },
            "_detail_fields": deepcopy(detail_fields),
        }

    def _build_invoice_row(
        self,
        *,
        row_id: str,
        month: str,
        section: str,
        case_id: str | None,
        seller_tax_no: str,
        seller_name: str,
        buyer_tax_no: str,
        buyer_name: str,
        issue_date: str,
        amount: str,
        tax_rate: str,
        tax_amount: str,
        total_with_tax: str,
        invoice_type: str,
        relation: dict[str, str],
        detail_fields: dict[str, str],
    ) -> dict[str, Any]:
        invoice_code = self._invoice_identity_display_value(detail_fields.get("发票代码"))
        invoice_no = self._invoice_identity_display_value(detail_fields.get("发票号码"))
        digital_invoice_no = self._invoice_identity_display_value(detail_fields.get("数电发票号码"))
        return {
            "id": row_id,
            "type": "invoice",
            "case_id": case_id,
            "seller_tax_no": seller_tax_no,
            "seller_name": seller_name,
            "buyer_tax_no": buyer_tax_no,
            "buyer_name": buyer_name,
            "invoice_code": invoice_code,
            "invoice_no": invoice_no,
            "digital_invoice_no": digital_invoice_no,
            "issue_date": issue_date,
            "amount": amount,
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_with_tax": total_with_tax,
            "invoice_type": invoice_type,
            "invoice_bank_relation": relation,
            "available_actions": self.available_actions("invoice", section),
            "_month": month,
            "_section": section,
            "_summary_fields": {
                "销方识别号": seller_tax_no,
                "销方名称": seller_name,
                "购方识别号": buyer_tax_no,
                "购买方名称": buyer_name,
                "开票日期": issue_date,
                "金额": amount,
                "税率": tax_rate,
                "税额": tax_amount,
                "价税合计": total_with_tax,
                "发票类型": invoice_type,
            },
            "_detail_fields": deepcopy(detail_fields),
        }
