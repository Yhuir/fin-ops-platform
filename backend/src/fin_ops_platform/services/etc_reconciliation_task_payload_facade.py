from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable


class EtcReconciliationTaskPayloadFacade:
    def __init__(
        self,
        *,
        etc_import_batch_by_id: Callable[[str], object | None],
        serialize_value: Callable[[object], Any],
    ) -> None:
        self._etc_import_batch_by_id = etc_import_batch_by_id
        self._serialize_value = serialize_value

    def task_payload(self, task: object) -> dict[str, object]:
        imported_summary = self.imported_invoice_summary(task)
        return {
            "taskId": getattr(task, "task_id", ""),
            "status": getattr(getattr(task, "status", ""), "value", getattr(task, "status", "")),
            "version": getattr(task, "version", 0),
            "title": getattr(task, "title", ""),
            "periodStart": getattr(task, "period_start", None),
            "periodEnd": getattr(task, "period_end", None),
            "statementPeriodStart": getattr(task, "statement_period_start", None),
            "statementPeriodEnd": getattr(task, "statement_period_end", None),
            "approvedDelta": getattr(task, "approved_delta", None),
            "approvedDeltaNote": getattr(task, "approved_delta_note", None),
            "cardLast4": getattr(task, "card_last4", None),
            "oaTotalAmount": getattr(task, "oa_total_amount", None),
            "etcInvoiceAmount": getattr(task, "etc_invoice_amount", None),
            "supplementAmount": getattr(task, "supplement_amount", None),
            "etcInvoiceCount": getattr(task, "etc_invoice_count", 0),
            "supplementCount": getattr(task, "supplement_count", 0),
            "canConfirm": self.task_can_confirm(task),
            "vehiclePlates": list(getattr(task, "vehicle_plates", []) or []),
            "confirmedItemSetHash": getattr(task, "confirmed_item_set_hash", None),
            "importBatchId": getattr(task, "import_batch_id", None),
            "etcBatchId": getattr(task, "etc_batch_id", None),
            "hasImportedInvoices": imported_summary["hasImportedInvoices"],
            "importedInvoiceCount": imported_summary["importedInvoiceCount"],
            "importedInvoiceAmount": imported_summary["importedInvoiceAmount"],
            "oaDraftBatchId": getattr(task, "oa_draft_batch_id", None),
            "oaDraftStatus": getattr(task, "oa_draft_status", None),
            "submittedConfirmedAt": getattr(task, "submitted_confirmed_at", None),
            "sourceFiles": self.source_file_payloads(task),
            "creditCardItems": [self._serialize_value(item) for item in getattr(task, "credit_card_items", [])],
            "ticketRootItems": [self._serialize_value(item) for item in getattr(task, "ticket_root_items", [])],
            "supplementEvidences": [self._serialize_value(item) for item in getattr(task, "supplement_evidences", [])],
            "reconciledItems": [self._serialize_value(item) for item in getattr(task, "reconciled_items", [])],
            "expectedEtcInvoiceRequirements": [
                self._serialize_value(item) for item in getattr(task, "expected_etc_invoice_requirements", [])
            ],
            "parseIssues": self.parse_issue_payloads(task),
            "auditEvents": [self._serialize_value(item) for item in getattr(task, "audit_events", [])],
        }

    def unavailable_task_payload(self, task: object) -> dict[str, object]:
        payload = self.task_payload(task)
        payload["importBlockers"] = self.import_blockers(task)
        return payload

    @staticmethod
    def import_blockers(task: object) -> list[dict[str, str]]:
        status = getattr(getattr(task, "status", ""), "value", getattr(task, "status", ""))
        if status in {"draft", "reviewing"}:
            return [
                {
                    "code": "not_confirmed",
                    "message": "请先在 ETC 对账页确认对账。",
                }
            ]
        if status == "importing":
            return [
                {
                    "code": "import_in_progress",
                    "message": "ETC 发票正在导入中，请稍后再试。",
                }
            ]
        if status == "imported":
            return [
                {
                    "code": "already_imported",
                    "message": "该 ETC 对账任务已导入。如需重导，请先移除已导入 ETC 发票。",
                }
            ]
        if status == "closed":
            return [
                {
                    "code": "closed",
                    "message": "该 ETC 对账任务已关闭，不能再次导入。",
                }
            ]
        return [
            {
                "code": "not_ready_for_import",
                "message": "该 ETC 对账任务当前不可导入。",
            }
        ]

    def imported_invoice_summary(self, task: object) -> dict[str, object]:
        import_batch_id = str(getattr(task, "import_batch_id", "") or "").strip()
        if not import_batch_id:
            return {
                "hasImportedInvoices": False,
                "importedInvoiceCount": 0,
                "importedInvoiceAmount": Decimal("0.00"),
            }
        import_batch = self._etc_import_batch_by_id(import_batch_id)
        if import_batch is None:
            return {
                "hasImportedInvoices": False,
                "importedInvoiceCount": 0,
                "importedInvoiceAmount": Decimal("0.00"),
            }
        invoice_count = int(getattr(import_batch, "invoice_count", 0) or 0)
        return {
            "hasImportedInvoices": invoice_count > 0,
            "importedInvoiceCount": invoice_count,
            "importedInvoiceAmount": getattr(import_batch, "total_amount", Decimal("0.00")),
        }

    @staticmethod
    def source_file_payloads(task: object) -> list[dict[str, object]]:
        blocking_file_ids = {
            getattr(issue, "file_id", "")
            for result in getattr(task, "parse_results", []) or []
            for issue in getattr(result, "issues", []) or []
            if getattr(getattr(issue, "severity", ""), "value", getattr(issue, "severity", "")) == "blocking"
        }
        return [
            {
                "fileId": getattr(source_file, "file_id", ""),
                "taskId": getattr(source_file, "task_id", ""),
                "sourceKind": getattr(getattr(source_file, "source_kind", ""), "value", getattr(source_file, "source_kind", "")),
                "originalName": getattr(source_file, "original_name", ""),
                "contentType": getattr(source_file, "content_type", ""),
                "sizeBytes": getattr(source_file, "size_bytes", 0),
                "sha256": getattr(source_file, "sha256", ""),
                "storedPath": getattr(source_file, "stored_path", ""),
                "createdBy": getattr(source_file, "created_by", ""),
                "createdAt": getattr(source_file, "created_at", None),
                "hasBlockingIssue": getattr(source_file, "file_id", "") in blocking_file_ids,
            }
            for source_file in getattr(task, "source_files", []) or []
        ]

    @staticmethod
    def parse_issue_payloads(task: object) -> list[dict[str, object]]:
        source_files = {
            getattr(source_file, "file_id", ""): source_file
            for source_file in getattr(task, "source_files", []) or []
        }
        payloads: list[dict[str, object]] = []
        for result in getattr(task, "parse_results", []) or []:
            for issue in getattr(result, "issues", []) or []:
                source_file = source_files.get(getattr(issue, "file_id", ""))
                payloads.append(
                    {
                        "issueId": getattr(issue, "issue_id", ""),
                        "fileId": getattr(issue, "file_id", ""),
                        "sourceKind": (
                            getattr(getattr(source_file, "source_kind", ""), "value", getattr(source_file, "source_kind", ""))
                            if source_file is not None
                            else None
                        ),
                        "originalName": getattr(source_file, "original_name", None) if source_file is not None else None,
                        "severity": getattr(getattr(issue, "severity", ""), "value", getattr(issue, "severity", "")),
                        "message": getattr(issue, "message", ""),
                        "sourcePage": getattr(issue, "source_page", None),
                        "sourceLine": getattr(issue, "source_line", None),
                        "extractionMethod": getattr(issue, "extraction_method", None),
                        "fieldName": getattr(issue, "field_name", None),
                    }
                )
        return payloads

    @classmethod
    def task_can_confirm(cls, task: object) -> bool:
        status = getattr(getattr(task, "status", ""), "value", getattr(task, "status", ""))
        if status in {"ready_for_import", "importing", "imported", "closed"}:
            return False
        credit_card_items = list(getattr(task, "credit_card_items", []) or [])
        if not credit_card_items:
            return False
        final_resolutions = {"included_etc", "covered_by_supplement", "manual_confirmed"}
        if not any(str(getattr(item, "manual_resolution", "") or "") in final_resolutions for item in credit_card_items):
            return False
        for item in credit_card_items:
            manual_resolution = str(getattr(item, "manual_resolution", "") or "unresolved")
            if (bool(getattr(item, "is_etc_candidate", False)) or manual_resolution != "unresolved") and manual_resolution == "unresolved":
                return False
            if manual_resolution == "included_etc" and not cls._task_card_has_linked_etc_evidence(task, str(getattr(item, "item_id", ""))):
                return False
            if manual_resolution == "covered_by_supplement" and not cls._task_card_has_linked_supplement(task, str(getattr(item, "item_id", ""))):
                return False
            if (
                manual_resolution == "covered_by_supplement"
                and cls._task_card_supplement_delta_requires_note(task, str(getattr(item, "item_id", "")))
                and not str(getattr(item, "review_note", "") or "").strip()
            ):
                return False
            if manual_resolution in {"excluded_non_etc", "excluded_error"} and not str(getattr(item, "manual_resolution_reason", "") or "").strip():
                return False
            if manual_resolution == "manual_confirmed" and not str(getattr(item, "review_note", "") or "").strip():
                return False
        return True

    @staticmethod
    def _task_card_has_linked_etc_evidence(task: object, card_id: str) -> bool:
        for ticket in getattr(task, "ticket_root_items", []) or []:
            if bool(getattr(ticket, "removed", False)):
                continue
            if card_id in list(getattr(ticket, "linked_credit_card_item_ids", []) or []):
                return True
        evidence_by_id = {
            str(getattr(evidence, "evidence_id", "")): evidence
            for evidence in getattr(task, "supplement_evidences", []) or []
        }
        for reconciled in getattr(task, "reconciled_items", []) or []:
            if str(getattr(reconciled, "credit_card_item_id", "")) != card_id:
                continue
            for evidence_id in list(getattr(reconciled, "supplement_evidence_ids", []) or []):
                evidence = evidence_by_id.get(str(evidence_id))
                evidence_kind = str(getattr(evidence, "evidence_kind", "") or "").strip().lower() if evidence is not None else ""
                if evidence_kind in {"etc", "etc_invoice", "etc-invoice"} and bool(getattr(evidence, "include_in_etc_zip_check", False)):
                    return True
        return False

    @staticmethod
    def _task_card_has_linked_supplement(task: object, card_id: str) -> bool:
        evidence_ids = {
            str(getattr(evidence, "evidence_id", ""))
            for evidence in getattr(task, "supplement_evidences", []) or []
        }
        return any(
            str(getattr(reconciled, "credit_card_item_id", "")) == card_id
            and any(str(evidence_id) in evidence_ids for evidence_id in list(getattr(reconciled, "supplement_evidence_ids", []) or []))
            for reconciled in getattr(task, "reconciled_items", []) or []
        )

    @staticmethod
    def _task_card_supplement_delta_requires_note(task: object, card_id: str) -> bool:
        cards = {
            str(getattr(item, "item_id", "")): item
            for item in getattr(task, "credit_card_items", []) or []
        }
        evidences = {
            str(getattr(evidence, "evidence_id", "")): evidence
            for evidence in getattr(task, "supplement_evidences", []) or []
        }
        card = cards.get(card_id)
        if card is None:
            return False
        try:
            claim_amount = Decimal(str(getattr(card, "settlement_amount", "0.00") or "0.00")).quantize(Decimal("0.01"))
        except Exception:
            return True
        for reconciled in getattr(task, "reconciled_items", []) or []:
            if str(getattr(reconciled, "credit_card_item_id", "")) != card_id:
                continue
            evidence_amount = Decimal("0.00")
            found = False
            for evidence_id in list(getattr(reconciled, "supplement_evidence_ids", []) or []):
                evidence = evidences.get(str(evidence_id))
                if evidence is None:
                    continue
                raw_amount = getattr(evidence, "amount", None)
                if raw_amount in (None, ""):
                    return True
                evidence_amount += Decimal(str(raw_amount)).quantize(Decimal("0.01"))
                found = True
            if found and (claim_amount - evidence_amount).quantize(Decimal("0.01")) != Decimal("0.00"):
                return True
        return False
