from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from fin_ops_platform.domain.models import Invoice
from fin_ops_platform.services.app_settings_service import (
    DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE,
    OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
    OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED,
    OA_ATTACHMENT_INVOICE_PROMOTION_MODES,
)
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_attachment_recognition_service import (
    CREATE_INVOICE_AND_LINK,
    IGNORE,
    LINK_EXISTING_INVOICE,
    InvoiceAttachmentRecognitionService,
)
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import expand_scope_month_window


@dataclass(frozen=True, slots=True)
class OAAttachmentInvoiceCandidate:
    cache_source_attachment_key: str
    invoice_index: int
    attachment_invoice: dict[str, Any]
    oa_form_id: str | None
    oa_row_id: str | None
    source_workbench_row_id: str | None
    context: dict[str, Any]


class OAAttachmentInvoicePromotionService:
    """Promote formal OA attachment invoices into the canonical invoice pool."""

    def __init__(self, *, invoice_repository: Any, promotion_mode_provider: Any | None = None) -> None:
        self._invoice_repository = invoice_repository
        self._promotion_mode_provider = promotion_mode_provider
        self._identity_service = InvoiceIdentityService()

    def promote_records(
        self,
        records: list[Any],
        *,
        apply: bool = True,
        example_limit: int = 10,
        ensure_matching: bool = False,
    ) -> dict[str, Any]:
        return self.promote_candidates(
            self.candidates_from_records(records),
            promotion_mode=self._promotion_mode(),
            apply=apply,
            example_limit=example_limit,
            ensure_matching=ensure_matching,
        )

    def promote_candidates(
        self,
        candidates: list[OAAttachmentInvoiceCandidate],
        *,
        promotion_mode: str,
        apply: bool,
        example_limit: int = 10,
        ensure_matching: bool = False,
    ) -> dict[str, Any]:
        normalized_mode = self._normalize_mode(promotion_mode)
        if normalized_mode == OA_ATTACHMENT_INVOICE_PROMOTION_DISABLED:
            return self._report(
                candidates=candidates,
                existing_invoices=[],
                affected_invoices=[],
                action_counts=Counter({IGNORE: len(candidates)}) if candidates else Counter(),
                reason_counts=Counter({"promotion_disabled": len(candidates)}) if candidates else Counter(),
                examples={},
                created_identity_keys=set(),
                linked_invoice_ids=set(),
                apply=apply,
            )

        existing_invoices = self._load_existing_invoices(candidates)
        initial_invoice_ids = {invoice.id for invoice in existing_invoices}
        import_service = ImportNormalizationService(existing_invoices=existing_invoices)
        recognition_service = InvoiceAttachmentRecognitionService(invoice_repository=import_service)
        action_counts: Counter[str] = Counter()
        reason_counts: Counter[str] = Counter()
        examples: dict[str, list[dict[str, Any]]] = {}
        created_identity_keys: set[str] = set()
        linked_invoice_ids: set[str] = set()
        affected_invoices: dict[str, Invoice] = {}
        affected_candidates: list[OAAttachmentInvoiceCandidate] = []

        for candidate in candidates:
            decision = recognition_service.decide(candidate.attachment_invoice)
            action = decision.action
            reason = decision.reason
            if action == IGNORE:
                self._record(
                    candidate,
                    action=action,
                    reason=reason,
                    identity_key=decision.identity_key,
                    action_counts=action_counts,
                    reason_counts=reason_counts,
                    examples=examples,
                    example_limit=example_limit,
                )
                continue
            if not candidate.oa_row_id or not candidate.source_workbench_row_id:
                self._record(
                    candidate,
                    action=IGNORE,
                    reason="missing_oa_context",
                    identity_key=decision.identity_key,
                    action_counts=action_counts,
                    reason_counts=reason_counts,
                    examples=examples,
                    example_limit=example_limit,
                )
                continue
            if action == CREATE_INVOICE_AND_LINK and normalized_mode != OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING:
                self._record(
                    candidate,
                    action=IGNORE,
                    reason="create_missing_disabled",
                    identity_key=decision.identity_key,
                    action_counts=action_counts,
                    reason_counts=reason_counts,
                    examples=examples,
                    example_limit=example_limit,
                )
                continue
            if decision.invoice is not None and self._has_source_context_conflict(decision.invoice, candidate):
                self._record(
                    candidate,
                    action=IGNORE,
                    reason="source_context_conflict",
                    identity_key=decision.identity_key,
                    action_counts=action_counts,
                    reason_counts=reason_counts,
                    examples=examples,
                    example_limit=example_limit,
                )
                continue

            before = deepcopy(decision.invoice) if decision.invoice is not None else None
            invoice = import_service.upsert_oa_attachment_invoice(
                candidate.attachment_invoice,
                oa_form_id=candidate.oa_form_id,
                oa_row_id=candidate.oa_row_id,
                source_workbench_row_id=candidate.source_workbench_row_id,
                allow_create=action == CREATE_INVOICE_AND_LINK,
            )
            if invoice is None:
                self._record(
                    candidate,
                    action=IGNORE,
                    reason="upsert_returned_none",
                    identity_key=decision.identity_key,
                    action_counts=action_counts,
                    reason_counts=reason_counts,
                    examples=examples,
                    example_limit=example_limit,
                )
                continue

            changed = before is None or invoice != before
            effective_action = CREATE_INVOICE_AND_LINK if invoice.id not in initial_invoice_ids else LINK_EXISTING_INVOICE
            effective_reason = reason if changed else "already_linked"
            self._record(
                candidate,
                action=effective_action,
                reason=effective_reason,
                identity_key=decision.identity_key,
                invoice=invoice,
                action_counts=action_counts,
                reason_counts=reason_counts,
                examples=examples,
                example_limit=example_limit,
            )
            if not changed:
                continue
            affected_invoices[invoice.id] = invoice
            affected_candidates.append(candidate)
            if effective_action == CREATE_INVOICE_AND_LINK and decision.identity_key:
                created_identity_keys.add(decision.identity_key)
            elif effective_action == LINK_EXISTING_INVOICE:
                linked_invoice_ids.add(invoice.id)

        if apply and (affected_invoices or (ensure_matching and candidates)):
            invoices_to_save = list(affected_invoices.values())
            save_with_matching_dirty = getattr(
                self._invoice_repository,
                "save_invoices_and_mark_matching_dirty",
                None,
            )
            if callable(save_with_matching_dirty):
                scope_months = self._matching_scope_months(
                    affected_candidates if affected_invoices else candidates
                )
                if not scope_months:
                    raise RuntimeError("OA attachment invoice promotion requires a matching scope month.")
                save_with_matching_dirty(
                    invoices_to_save,
                    scope_months=scope_months,
                    reason=(
                        "oa_attachment_invoice_manual_refresh"
                        if ensure_matching
                        else "oa_attachment_invoice_promotion"
                    ),
                    debounce_seconds=0,
                )
            elif affected_invoices:
                self._invoice_repository.save_invoices(invoices_to_save)
            else:
                raise RuntimeError(
                    "OA attachment invoice manual refresh requires matching reconciliation support."
                )
        return self._report(
            candidates=candidates,
            existing_invoices=existing_invoices,
            affected_invoices=list(affected_invoices.values()),
            action_counts=action_counts,
            reason_counts=reason_counts,
            examples=examples,
            created_identity_keys=created_identity_keys,
            linked_invoice_ids=linked_invoice_ids,
            apply=apply,
        )

    @staticmethod
    def candidates_from_records(records: list[Any]) -> list[OAAttachmentInvoiceCandidate]:
        candidates: list[OAAttachmentInvoiceCandidate] = []
        for record in records:
            oa_row_id = _clean_text(getattr(record, "id", None))
            invoices = [
                dict(item)
                for item in list(getattr(record, "attachment_invoices", None) or [])
                if isinstance(item, dict)
            ]
            if not invoices:
                invoices = [
                    dict(item)
                    for item in list(getattr(record, "attachment_evidences", None) or [])
                    if isinstance(item, dict)
                ]
            for index, attachment_invoice in enumerate(invoices):
                source_workbench_row_id = (
                    FinancialObjectIdentityPolicy.oa_attachment_invoice_row_id(
                        oa_row_id,
                        index,
                        attachment_invoice,
                    )
                    if oa_row_id
                    else None
                )
                candidates.append(
                    OAAttachmentInvoiceCandidate(
                        cache_source_attachment_key=_clean_text(
                            attachment_invoice.get("source_attachment_key")
                        )
                        or "",
                        invoice_index=index,
                        attachment_invoice=attachment_invoice,
                        oa_form_id=oa_row_id,
                        oa_row_id=oa_row_id,
                        source_workbench_row_id=source_workbench_row_id,
                        context={"month": _clean_text(getattr(record, "month", None))},
                    )
                )
        return candidates

    def _load_existing_invoices(self, candidates: list[OAAttachmentInvoiceCandidate]) -> list[Invoice]:
        canonical_keys = {
            identity_key
            for candidate in candidates
            if (
                identity_key := self._identity_service.canonical_key_for_mapping(
                    candidate.attachment_invoice
                )
            )
        }
        if not canonical_keys:
            return []
        return [
            invoice
            for invoice in self._invoice_repository.find_invoices_by_identity_keys(
                canonical_keys=canonical_keys,
            )
            if isinstance(invoice, Invoice)
        ]

    def _promotion_mode(self) -> str:
        if not callable(self._promotion_mode_provider):
            return DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE
        return self._normalize_mode(self._promotion_mode_provider())

    @staticmethod
    def _matching_scope_months(candidates: list[OAAttachmentInvoiceCandidate]) -> list[str]:
        months: set[str] = set()
        for candidate in candidates:
            raw_value = (
                candidate.context.get("month")
                or candidate.attachment_invoice.get("issue_date")
                or candidate.attachment_invoice.get("invoice_date")
            )
            month = str(raw_value or "").strip()[:7]
            if not month:
                continue
            try:
                months.update(expand_scope_month_window(month))
            except ValueError:
                continue
        return sorted(months)

    @staticmethod
    def _normalize_mode(value: Any) -> str:
        mode = str(value or "").strip()
        return mode if mode in OA_ATTACHMENT_INVOICE_PROMOTION_MODES else DEFAULT_OA_ATTACHMENT_INVOICE_PROMOTION_MODE

    @staticmethod
    def _has_source_context_conflict(invoice: Invoice, candidate: OAAttachmentInvoiceCandidate) -> bool:
        incoming_oa_id = _clean_text(candidate.oa_row_id)
        incoming_item_id = _clean_text(candidate.attachment_invoice.get("source_expense_item_id"))
        for source_link in list(invoice.source_links or []):
            if str(source_link.get("source_type") or "") != "oa_attachment_invoice":
                continue
            existing_oa_id = _clean_text(source_link.get("derived_from_oa_id"))
            existing_item_id = _clean_text(source_link.get("source_expense_item_id"))
            if existing_oa_id and incoming_oa_id and existing_oa_id != incoming_oa_id:
                return True
            if existing_item_id and incoming_item_id and existing_item_id != incoming_item_id:
                return True
        return False

    @classmethod
    def _record(
        cls,
        candidate: OAAttachmentInvoiceCandidate,
        *,
        action: str,
        reason: str,
        action_counts: Counter[str],
        reason_counts: Counter[str],
        examples: dict[str, list[dict[str, Any]]],
        example_limit: int,
        identity_key: str | None = None,
        invoice: Invoice | None = None,
    ) -> None:
        action_counts[action] += 1
        reason_counts[reason] += 1
        bucket = examples.setdefault(f"{action}:{reason}", [])
        if len(bucket) >= max(example_limit, 0):
            return
        payload = candidate.attachment_invoice
        bucket.append(
            {
                "action": action,
                "reason": reason,
                "identity_key": identity_key,
                "invoice_id": invoice.id if invoice is not None else None,
                "cache_source_attachment_key": candidate.cache_source_attachment_key,
                "invoice_index": candidate.invoice_index,
                "oa_form_id": candidate.oa_form_id,
                "oa_row_id": candidate.oa_row_id,
                "source_workbench_row_id": candidate.source_workbench_row_id,
                "invoice_no": payload.get("invoice_no"),
                "digital_invoice_no": payload.get("digital_invoice_no"),
                "source_expense_item_id": payload.get("source_expense_item_id"),
                "source_attachment_name": payload.get("source_attachment_name")
                or payload.get("attachment_name"),
            }
        )

    @staticmethod
    def _report(
        *,
        candidates: list[OAAttachmentInvoiceCandidate],
        existing_invoices: list[Invoice],
        affected_invoices: list[Invoice],
        action_counts: Counter[str],
        reason_counts: Counter[str],
        examples: dict[str, list[dict[str, Any]]],
        created_identity_keys: set[str],
        linked_invoice_ids: set[str],
        apply: bool,
    ) -> dict[str, Any]:
        existing_identity_keys = {
            str(key).strip()
            for invoice in existing_invoices
            for key in (invoice.source_unique_key, invoice.digital_invoice_no)
            if str(key or "").strip()
        }
        return {
            "mode": "apply" if apply else "dry_run",
            "summary": {
                "existing_invoice_count": len(existing_invoices),
                "existing_identity_count": len(existing_identity_keys),
                "cache_candidate_count": len(candidates),
                "linked_existing_invoice_count": len(linked_invoice_ids),
                "created_invoice_count": len(created_identity_keys),
                "created_identity_count": len(created_identity_keys),
                "affected_invoice_count": len(affected_invoices),
                "persisted": bool(apply and affected_invoices),
            },
            "action_counts": dict(sorted(action_counts.items())),
            "reason_counts": dict(sorted(reason_counts.items())),
            "examples": examples,
        }


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
