from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from typing import Any

from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.bank_transaction_identity_service import BankTransactionIdentityService, normalize_name
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService

OBJECT_IDENTITY_POLICY_SCHEMA_VERSION = "2026-06-object-identity-policy-v1"
CENT = Decimal("0.01")
OA_ATTACHMENT_INVOICE_EVIDENCE_TYPES = frozenset({"tax_invoice", "machine_invoice"})
OA_ATTACHMENT_FORMAL_DOCUMENT_KINDS = frozenset(
    {
        "digital_invoice",
        "railway_e_ticket_invoice",
        "yunnan_machine_invoice",
    }
)


@dataclass(frozen=True, slots=True)
class ObjectIdentity:
    object_type: str
    source_kind: str | None = None
    source_row_id: str | None = None
    canonical_key: str | None = None
    canonical_key_kind: str | None = None
    suspected_key: str | None = None
    missing_fields: tuple[str, ...] = ()
    confidence: str = "missing"
    components: dict[str, str] = field(default_factory=dict)
    audit_fields: dict[str, str | None] = field(default_factory=dict)
    schema_version: str = OBJECT_IDENTITY_POLICY_SCHEMA_VERSION

    @property
    def has_canonical_key(self) -> bool:
        return bool(self.canonical_key)

    @property
    def has_suspected_key(self) -> bool:
        return bool(self.suspected_key)


class FinancialObjectIdentityPolicy:
    """Pure business policy for financial object identity.

    This service intentionally has no persistence, HTTP, auth, queue, or
    Application dependency. It centralizes identity rules that were previously
    spread across import, invoice usage, output collection, ETC, and workbench
    attachment handling.
    """

    def __init__(
        self,
        *,
        invoice_identity_service: InvoiceIdentityService | None = None,
        bank_transaction_identity_service: BankTransactionIdentityService | None = None,
    ) -> None:
        self._invoice_identity_service = invoice_identity_service or InvoiceIdentityService()
        self._bank_transaction_identity_service = bank_transaction_identity_service or BankTransactionIdentityService()

    def identify_invoice_mapping(
        self,
        values: dict[str, Any],
        *,
        source_kind: str | None = None,
        source_row_id: str | None = None,
        object_type: str = "invoice",
    ) -> ObjectIdentity:
        identity = self._invoice_identity_service.identity_for_mapping(values)
        canonical_key = identity.canonical_key
        suspected_key = identity.suspected_key or self._legacy_counterparty_invoice_suspected_key(values)
        canonical_key_kind = self._invoice_canonical_key_kind(values, canonical_key)
        missing_fields = self._invoice_missing_fields(values, canonical_key=canonical_key, suspected_key=suspected_key)
        confidence = "canonical" if canonical_key else "suspected" if suspected_key else "missing"
        components = self._invoice_components(values)
        return ObjectIdentity(
            object_type=object_type,
            source_kind=source_kind,
            source_row_id=source_row_id,
            canonical_key=canonical_key,
            canonical_key_kind=canonical_key_kind,
            suspected_key=suspected_key,
            missing_fields=tuple(missing_fields),
            confidence=confidence,
            components=components,
            audit_fields={"suspected_key_kind": self._invoice_suspected_key_kind(values, suspected_key)},
        )

    def identify_invoice(
        self,
        invoice: Invoice,
        *,
        source_kind: str | None = None,
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        return self.identify_invoice_mapping(
            {
                "digital_invoice_no": invoice.digital_invoice_no,
                "invoice_code": invoice.invoice_code,
                "invoice_no": invoice.invoice_no,
                "seller_tax_no": invoice.seller_tax_no,
                "buyer_tax_no": invoice.buyer_tax_no,
                "seller_name": invoice.seller_name,
                "buyer_name": invoice.buyer_name,
                "invoice_date": invoice.invoice_date,
                "total_with_tax": invoice.total_with_tax,
                "amount": invoice.amount,
                "counterparty_name": getattr(invoice.counterparty, "name", None),
                "normalized_counterparty_name": getattr(invoice.counterparty, "normalized_name", None),
            },
            source_kind=source_kind,
            source_row_id=source_row_id or invoice.id,
            object_type="invoice",
        )

    def identify_bank_transaction_mapping(
        self,
        values: dict[str, Any],
        *,
        source_kind: str | None = None,
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        identity = self._bank_transaction_identity_service.identity_for_mapping(values)
        confidence = "canonical" if identity.identity_key else "suspected" if identity.suspected_key else "missing"
        return ObjectIdentity(
            object_type="bank_transaction",
            source_kind=source_kind,
            source_row_id=source_row_id,
            canonical_key=identity.identity_key,
            canonical_key_kind=identity.canonical_key_kind,
            suspected_key=identity.suspected_key,
            missing_fields=tuple(identity.missing_fields),
            confidence=confidence,
            components=dict(identity.components),
            audit_fields=dict(identity.audit_fields),
        )

    def identify_bank_transaction(
        self,
        transaction: BankTransaction,
        *,
        source_kind: str | None = None,
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        return self.identify_bank_transaction_mapping(
            {
                "account_no": transaction.account_no,
                "trade_time": transaction.trade_time,
                "pay_receive_time": transaction.pay_receive_time,
                "txn_date": transaction.txn_date,
                "txn_direction": transaction.txn_direction,
                "amount": transaction.amount,
                "counterparty_name": transaction.counterparty_name_raw,
                "bank_serial_no": transaction.bank_serial_no,
                "account_detail_no": transaction.account_detail_no,
                "enterprise_serial_no": transaction.enterprise_serial_no,
                "voucher_no": transaction.voucher_no,
            },
            source_kind=source_kind,
            source_row_id=source_row_id or transaction.id,
        )

    def identify_oa_attachment_invoice(
        self,
        attachment_invoice: dict[str, Any] | None,
        *,
        source_kind: str | None = "oa_attachment_invoice",
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        values = dict(attachment_invoice or {})
        invoice_identity = self.identify_invoice_mapping(
            {
                "digital_invoice_no": values.get("digital_invoice_no"),
                "invoice_code": values.get("invoice_code"),
                "invoice_no": values.get("invoice_no"),
                "seller_tax_no": values.get("seller_tax_no"),
                "buyer_tax_no": values.get("buyer_tax_no"),
                "seller_name": values.get("seller_name"),
                "buyer_name": values.get("buyer_name"),
                "invoice_date": values.get("issue_date") or values.get("invoice_date"),
                "total_with_tax": values.get("total_with_tax") or values.get("amount"),
            },
            source_kind=source_kind,
            source_row_id=source_row_id,
            object_type="oa_attachment_invoice",
        )
        stable_key = self.oa_attachment_invoice_stable_identity(values)
        candidate_key = self.oa_attachment_invoice_candidate_identity(values)
        weak_tax_amount_key = (
            invoice_identity.canonical_key
            if invoice_identity.canonical_key_kind == "tax_amount_fingerprint"
            else None
        )
        strong_invoice_key = None if weak_tax_amount_key else invoice_identity.canonical_key
        canonical_key = strong_invoice_key or (f"oa_attachment:{stable_key}" if stable_key else None)
        canonical_key_kind = (
            invoice_identity.canonical_key_kind
            if strong_invoice_key
            else ("oa_attachment_stable_hash" if stable_key else None)
        )
        suspected_key = weak_tax_amount_key or invoice_identity.suspected_key or (
            f"oa_attachment_candidate:{candidate_key}" if candidate_key else None
        )
        return ObjectIdentity(
            object_type="oa_attachment_invoice",
            source_kind=source_kind,
            source_row_id=source_row_id,
            canonical_key=canonical_key,
            canonical_key_kind=canonical_key_kind,
            suspected_key=suspected_key,
            missing_fields=invoice_identity.missing_fields,
            confidence="canonical" if canonical_key else "suspected" if suspected_key else "missing",
            components=invoice_identity.components,
            audit_fields={
                "stable_identity": stable_key or None,
                "candidate_identity": candidate_key or None,
                "weak_invoice_identity": weak_tax_amount_key,
            },
        )

    def oa_attachment_invoice_dedupe_keys(self, attachment_invoice: dict[str, Any] | None) -> list[tuple[str, str]]:
        """Return dedupe keys for OA attachment invoice evidence.

        The first two keys preserve the legacy exact-match priority used by
        the OA parser. Stable/candidate hashes give downstream caches a single
        policy-owned fallback without duplicating invoice identity rules.
        """

        if not isinstance(attachment_invoice, dict):
            return []
        values = dict(attachment_invoice)
        keys: list[tuple[str, str]] = []
        identity = self.identify_oa_attachment_invoice(values)
        if identity.canonical_key_kind == "digital_invoice_no" and identity.canonical_key:
            keys.append(("invoice:digital_invoice_no", identity.canonical_key))
        invoice_code = self._clean_identity_part(values.get("invoice_code"))
        invoice_no = self._clean_identity_part(values.get("invoice_no"))
        if invoice_code and invoice_no:
            keys.append(("invoice:code_no", f"{invoice_code}:{invoice_no}"))

        legacy_fallback = self._legacy_oa_attachment_invoice_fallback_key(values)
        if legacy_fallback:
            keys.append(("invoice:fallback", legacy_fallback))
        stable_key = str(identity.audit_fields.get("stable_identity") or "").strip()
        if stable_key:
            keys.append(("invoice:stable", stable_key))
        candidate_key = str(identity.audit_fields.get("candidate_identity") or "").strip()
        if candidate_key and candidate_key != stable_key:
            keys.append(("invoice:candidate", candidate_key))
        return _dedupe_ordered_pairs(keys)

    def is_oa_attachment_invoice_evidence(self, evidence: dict[str, Any] | None) -> bool:
        """Return whether an OA attachment evidence payload should enter invoice identity.

        Payment receipts and unknown artifacts intentionally stay outside
        invoice identity/dedup even when they carry amounts or merchant names.
        """

        if not isinstance(evidence, dict):
            return False
        evidence_type = self._clean_identity_part(evidence.get("evidence_type"))
        if evidence_type in OA_ATTACHMENT_INVOICE_EVIDENCE_TYPES:
            return True
        if evidence_type:
            return False
        document_kind = self._clean_identity_part(evidence.get("document_kind") or evidence.get("invoice_type"))
        return self._is_formal_oa_attachment_document_kind(document_kind) and bool(
            evidence.get("invoice_no") or evidence.get("digital_invoice_no") or evidence.get("invoice_code")
        )

    @staticmethod
    def _is_formal_oa_attachment_document_kind(document_kind: str | None) -> bool:
        if not document_kind:
            return False
        if document_kind in OA_ATTACHMENT_FORMAL_DOCUMENT_KINDS:
            return True
        return "发票" in document_kind or "电子客票" in document_kind

    def identify_etc_invoice_mapping(
        self,
        values: dict[str, Any],
        *,
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        identity = self.identify_invoice_mapping(
            values,
            source_kind="etc_invoice",
            source_row_id=source_row_id,
            object_type="etc_invoice",
        )
        if not identity.canonical_key:
            return identity
        audit_fields = dict(identity.audit_fields)
        if identity.suspected_key:
            audit_fields["weak_suspected_key_suppressed"] = identity.suspected_key
        return replace(identity, suspected_key=None, audit_fields=audit_fields)

    def identify_tax_certified_invoice_mapping(
        self,
        values: dict[str, Any],
        *,
        source_row_id: str | None = None,
    ) -> ObjectIdentity:
        return self.identify_invoice_mapping(
            {
                "digital_invoice_no": values.get("digital_invoice_no"),
                "invoice_code": values.get("invoice_code"),
                "invoice_no": values.get("invoice_no"),
                "seller_tax_no": values.get("seller_tax_no"),
                "buyer_tax_no": values.get("taxpayer_tax_no") or values.get("buyer_tax_no"),
                "seller_name": values.get("seller_name"),
                "buyer_name": values.get("taxpayer_name") or values.get("buyer_name"),
                "invoice_date": values.get("issue_date") or values.get("invoice_date"),
                "total_with_tax": values.get("total_with_tax") or values.get("amount"),
            },
            source_kind="tax_certified_invoice",
            source_row_id=source_row_id,
            object_type="tax_certified_invoice",
        )

    def tax_certified_unique_key(self, values: dict[str, Any]) -> str:
        identity = self.identify_tax_certified_invoice_mapping(values)
        if identity.canonical_key_kind == "digital_invoice_no" and identity.canonical_key:
            return f"digital:{identity.canonical_key}"
        if identity.canonical_key_kind == "invoice_code_no" and identity.canonical_key:
            return f"invoice:{identity.canonical_key}"
        seller_part = (
            self._clean_identity_part(values.get("seller_tax_no"))
            or self._clean_identity_part(values.get("seller_name"))
            or "unknown-seller"
        )
        issue_part = (
            self._clean_identity_part(values.get("issue_date") or values.get("invoice_date"))
            or "unknown-date"
        )
        tax_part = self._format_amount(values.get("tax_amount") or values.get("amount")) or "0.00"
        return f"fallback:{seller_part}:{issue_part}:{tax_part}"

    def legacy_invoice_identity_key(self, invoice: Invoice) -> str:
        identity = self.identify_invoice(invoice)
        if identity.canonical_key_kind == "digital_invoice_no" and identity.canonical_key:
            return f"digital:{identity.canonical_key}"
        if identity.canonical_key_kind == "invoice_code_no" and identity.canonical_key:
            return f"code_no:{identity.canonical_key}"
        return f"id:{invoice.id}"

    @classmethod
    def oa_attachment_invoice_row_id(
        cls,
        oa_row_id: str,
        index: int,
        attachment_invoice: dict[str, Any] | None = None,
    ) -> str:
        stable_identity = cls.oa_attachment_invoice_stable_identity(attachment_invoice)
        if stable_identity:
            return f"oa-att-inv-{oa_row_id}-{stable_identity}"
        return f"oa-att-inv-{oa_row_id}-{index + 1:02d}"

    @classmethod
    def oa_attachment_invoice_stable_identity(cls, attachment_invoice: dict[str, Any] | None) -> str:
        if not isinstance(attachment_invoice, dict):
            return ""
        identity_parts = [
            cls._clean_identity_part(attachment_invoice.get("evidence_id")),
            cls._clean_identity_part(attachment_invoice.get("evidence_type")),
            cls._clean_identity_part(attachment_invoice.get("document_kind")),
            cls._clean_identity_part(attachment_invoice.get("source_expense_item_id")),
            cls._clean_identity_part(attachment_invoice.get("source_attachment_key")),
            cls._clean_identity_part(attachment_invoice.get("source_region_key")),
            cls._clean_identity_part(attachment_invoice.get("digital_invoice_no")),
            cls._clean_identity_part(attachment_invoice.get("invoice_no")),
            cls._clean_identity_part(attachment_invoice.get("invoice_code")),
            cls._clean_identity_part(attachment_invoice.get("transaction_no")),
            cls._clean_identity_part(attachment_invoice.get("merchant_order_no")),
            cls._clean_identity_part(attachment_invoice.get("issue_date")),
            cls._clean_identity_part(attachment_invoice.get("paid_at")),
            cls._clean_identity_part(attachment_invoice.get("total_with_tax")),
            cls._clean_identity_part(attachment_invoice.get("net_amount")),
            cls._clean_identity_part(attachment_invoice.get("amount")),
            cls._clean_identity_part(attachment_invoice.get("tax_amount")),
            cls._clean_identity_part(attachment_invoice.get("source_attachment_name")),
            cls._clean_identity_part(attachment_invoice.get("attachment_name")),
        ]
        material = "|".join(part for part in identity_parts if part)
        if not material:
            return ""
        return sha1(material.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def oa_attachment_invoice_candidate_identity(cls, attachment_invoice: dict[str, Any] | None) -> str:
        if not isinstance(attachment_invoice, dict):
            return ""
        identity_parts = [
            cls._clean_identity_part(attachment_invoice.get("source_attachment_key")),
            cls._clean_identity_part(attachment_invoice.get("source_expense_item_id")),
            cls._clean_identity_part(attachment_invoice.get("digital_invoice_no")),
            cls._clean_identity_part(attachment_invoice.get("invoice_no")),
            cls._clean_identity_part(attachment_invoice.get("invoice_code")),
            cls._clean_identity_part(attachment_invoice.get("seller_tax_no")),
            cls._clean_identity_part(attachment_invoice.get("seller_name")),
            cls._clean_identity_part(attachment_invoice.get("buyer_tax_no")),
            cls._clean_identity_part(attachment_invoice.get("buyer_name")),
            cls._clean_identity_part(attachment_invoice.get("total_with_tax")),
            cls._clean_identity_part(attachment_invoice.get("amount")),
            cls._clean_identity_part(attachment_invoice.get("tax_amount")),
        ]
        material = "|".join(part for part in identity_parts if part)
        if material:
            return sha1(material.encode("utf-8")).hexdigest()[:16]
        return cls.oa_attachment_invoice_stable_identity(attachment_invoice)

    @staticmethod
    def _clean_identity_part(value: Any) -> str:
        text = str(value or "").strip()
        return "" if text in {"—", "--"} else text

    def _invoice_canonical_key_kind(self, values: dict[str, Any], canonical_key: str | None) -> str | None:
        if not canonical_key:
            return None
        digital_invoice_no = self._clean(values.get("digital_invoice_no"))
        if digital_invoice_no and canonical_key == digital_invoice_no:
            return "digital_invoice_no"
        invoice_code = self._clean(values.get("invoice_code"))
        invoice_no = self._clean(values.get("invoice_no"))
        if invoice_code and invoice_no and canonical_key == f"{invoice_code}:{invoice_no}":
            return "invoice_code_no"
        return "tax_amount_fingerprint"

    def _invoice_missing_fields(
        self,
        values: dict[str, Any],
        *,
        canonical_key: str | None,
        suspected_key: str | None,
    ) -> list[str]:
        if canonical_key or suspected_key:
            return []
        return [
            field_name
            for field_name in ("digital_invoice_no", "invoice_code", "invoice_no", "seller_tax_no", "buyer_tax_no", "invoice_date", "total_with_tax")
            if not self._clean(values.get(field_name))
        ]

    def _invoice_components(self, values: dict[str, Any]) -> dict[str, str]:
        components: dict[str, str] = {}
        for field_name in (
            "digital_invoice_no",
            "invoice_code",
            "invoice_no",
            "seller_tax_no",
            "buyer_tax_no",
            "seller_name",
            "buyer_name",
            "invoice_date",
        ):
            value = self._clean(values.get(field_name))
            if value:
                components[field_name] = value
        amount = self._format_amount(values.get("total_with_tax"))
        if amount:
            components["total_with_tax"] = amount
        return components

    def _invoice_suspected_key_kind(self, values: dict[str, Any], suspected_key: str | None) -> str | None:
        if not suspected_key:
            return None
        if self._clean(values.get("seller_name")) and self._clean(values.get("buyer_name")):
            return "seller_buyer_name_amount"
        return "legacy_counterparty_amount"

    def _legacy_counterparty_invoice_suspected_key(self, values: dict[str, Any]) -> str | None:
        """Preserve the historical import fingerprint as a centralized weak key.

        Older import templates only carry a generic counterparty name, invoice
        date, and amount. That key is not safe for automatic merge, but it is a
        real production duplicate hint and must live in the identity policy
        instead of scattered import-service fallback code.
        """

        counterparty_name = self._clean(values.get("normalized_counterparty_name"))
        if counterparty_name:
            counterparty_name = normalize_name(counterparty_name)
        else:
            raw_name = self._clean(values.get("counterparty_name") or values.get("counterparty_name_raw"))
            counterparty_name = normalize_name(raw_name) if raw_name else None
        invoice_date = self._clean(values.get("invoice_date"))
        amount = self._format_amount(values.get("total_with_tax") or values.get("amount"))
        if counterparty_name and invoice_date and amount:
            return f"invoice:{counterparty_name}:{invoice_date}:{amount}"
        return None

    @classmethod
    def _legacy_oa_attachment_invoice_fallback_key(cls, values: dict[str, Any]) -> str:
        invoice_code = cls._clean_identity_part(values.get("invoice_code"))
        invoice_no = cls._clean_identity_part(values.get("invoice_no"))
        fallback = {
            "document_kind": cls._clean_identity_part(values.get("document_kind")),
            "invoice_no": invoice_no,
            "invoice_code": invoice_code,
            "amount": cls._clean_identity_part(values.get("total_with_tax") or values.get("amount")),
            "seller_name": cls._clean_identity_part(values.get("seller_name")),
            "issue_date": cls._clean_identity_part(values.get("issue_date") or values.get("invoice_date")),
        }
        if not invoice_no and not invoice_code:
            fallback["source_attachment_name"] = cls._clean_identity_part(
                values.get("source_attachment_name") or values.get("attachment_name")
            )
            fallback["source_region_key"] = cls._clean_identity_part(values.get("source_region_key"))
        return json.dumps(fallback, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _format_amount(value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{Decimal(str(value)).quantize(CENT)}"
        except (InvalidOperation, ValueError):
            return None


def _dedupe_ordered_pairs(values: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[tuple[str, str]] = []
    for key_kind, key_value in values:
        normalized_kind = str(key_kind or "").strip()
        normalized_value = str(key_value or "").strip()
        if not normalized_kind or not normalized_value:
            continue
        pair = (normalized_kind, normalized_value)
        if pair in seen:
            continue
        seen.add(pair)
        deduped.append(pair)
    return deduped
