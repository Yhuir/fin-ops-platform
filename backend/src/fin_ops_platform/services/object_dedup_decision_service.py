from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from fin_ops_platform.domain.enums import ImportDecision
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.bank_transaction_identity_service import (
    BankTransactionIdentityService,
    BankTransactionStatementPosition,
)
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy, ObjectIdentity


@dataclass(frozen=True, slots=True)
class ObjectDedupDecision:
    decision: ImportDecision | str
    decision_reason: str
    identity: ObjectIdentity
    linked_object_type: str | None = None
    linked_object_id: str | None = None
    matched_object: Any | None = None

    @property
    def is_duplicate(self) -> bool:
        return self.decision == ImportDecision.DUPLICATE_SKIPPED

    @property
    def is_suspected_duplicate(self) -> bool:
        return self.decision == ImportDecision.SUSPECTED_DUPLICATE


class ObjectIdentityRepository(Protocol):
    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        ...

    def find_bank_transaction_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> BankTransaction | None:
        ...

    def find_bank_transactions_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[BankTransaction]:
        ...

    def find_bank_transactions_by_statement_position(
        self,
        *,
        position: BankTransactionStatementPosition,
    ) -> list[BankTransaction]:
        ...

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        ...


class ObjectDedupDecisionService:
    """Read-only dedup decision service for financial object imports.

    It returns decisions only. It does not create, update, merge, or delete
    invoices/bank transactions.
    """

    def __init__(
        self,
        *,
        identity_policy: FinancialObjectIdentityPolicy | None = None,
        object_identity_repository: ObjectIdentityRepository | None = None,
        source_versions_provider: Any | None = None,
    ) -> None:
        self._identity_policy = identity_policy or FinancialObjectIdentityPolicy()
        self._bank_identity_service = BankTransactionIdentityService()
        self._repository = object_identity_repository
        self._source_versions_provider = source_versions_provider

    @property
    def identity_policy(self) -> FinancialObjectIdentityPolicy:
        return self._identity_policy

    def decide_invoice_import(self, normalized: dict[str, Any]) -> ObjectDedupDecision:
        identity = (
            self._identity_policy.identify_etc_invoice_mapping(normalized)
            if self._is_etc_invoice(normalized)
            else self._identity_policy.identify_invoice_mapping(normalized)
        )
        existing = self._find_invoice(identity)
        if identity.canonical_key and existing is not None:
            incoming_status = _text(normalized.get("invoice_status_from_source"))
            existing_status = _text(getattr(existing, "invoice_status_from_source", None))
            if incoming_status and incoming_status != existing_status:
                return ObjectDedupDecision(
                    decision=ImportDecision.STATUS_UPDATED,
                    decision_reason="Unique business key matched an existing invoice with a changed source status.",
                    identity=identity,
                    linked_object_type="invoice",
                    linked_object_id=existing.id,
                    matched_object=existing,
                )
            return ObjectDedupDecision(
                decision=ImportDecision.DUPLICATE_SKIPPED,
                decision_reason="Unique business key matched an existing invoice with no source status change.",
                identity=identity,
                linked_object_type="invoice",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        if not identity.canonical_key and identity.suspected_key and existing is not None:
            return ObjectDedupDecision(
                decision=ImportDecision.SUSPECTED_DUPLICATE,
                decision_reason="Fingerprint matched an existing invoice without a stable official unique key.",
                identity=identity,
                linked_object_type="invoice",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        return ObjectDedupDecision(
            decision=ImportDecision.CREATED,
            decision_reason="Ready to create new invoice.",
            identity=identity,
        )

    def decide_oa_attachment_invoice_import(self, normalized: dict[str, Any]) -> ObjectDedupDecision:
        identity = self._identity_policy.identify_oa_attachment_invoice(
            normalized,
            source_row_id=_text(normalized.get("source_workbench_row_id") or normalized.get("source_attachment_key")),
        )
        existing = self._find_invoice(identity)
        if identity.canonical_key and existing is not None:
            return ObjectDedupDecision(
                decision=ImportDecision.DUPLICATE_SKIPPED,
                decision_reason="OA attachment invoice identity matched an existing invoice.",
                identity=identity,
                linked_object_type="invoice",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        if not identity.canonical_key and identity.suspected_key and existing is not None:
            return ObjectDedupDecision(
                decision=ImportDecision.SUSPECTED_DUPLICATE,
                decision_reason="OA attachment invoice fingerprint matched an existing invoice without a stable official unique key.",
                identity=identity,
                linked_object_type="invoice",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        return ObjectDedupDecision(
            decision=ImportDecision.CREATED,
            decision_reason="Ready to create new OA attachment invoice.",
            identity=identity,
        )

    def decide_invoice_confirm(self, normalized: dict[str, Any]) -> ObjectDedupDecision:
        decision = self.decide_invoice_import(normalized)
        if decision.decision == ImportDecision.STATUS_UPDATED:
            return ObjectDedupDecision(
                decision=decision.decision,
                decision_reason="Unique business key matched an existing invoice during confirm with a changed source status.",
                identity=decision.identity,
                linked_object_type=decision.linked_object_type,
                linked_object_id=decision.linked_object_id,
                matched_object=decision.matched_object,
            )
        if decision.decision == ImportDecision.DUPLICATE_SKIPPED:
            return ObjectDedupDecision(
                decision=decision.decision,
                decision_reason="Unique business key matched an existing invoice during confirm.",
                identity=decision.identity,
                linked_object_type=decision.linked_object_type,
                linked_object_id=decision.linked_object_id,
                matched_object=decision.matched_object,
            )
        if decision.decision == ImportDecision.SUSPECTED_DUPLICATE:
            return ObjectDedupDecision(
                decision=decision.decision,
                decision_reason="Fingerprint matched an existing invoice during confirm without a stable official unique key.",
                identity=decision.identity,
                linked_object_type=decision.linked_object_type,
                linked_object_id=decision.linked_object_id,
                matched_object=decision.matched_object,
            )
        return decision

    def decide_bank_transaction_import(self, normalized: dict[str, Any]) -> ObjectDedupDecision:
        identity = self._identity_policy.identify_bank_transaction_mapping(normalized)
        existing, match_kind = self._find_bank_transaction(identity, normalized=normalized)
        if identity.canonical_key and existing is not None and match_kind != "migration_ambiguous":
            return ObjectDedupDecision(
                decision=ImportDecision.DUPLICATE_SKIPPED,
                decision_reason=(
                    "Bank transaction business fields and official reference matched a legacy identity."
                    if match_kind == "migration_exact"
                    else "Bank transaction identity matched an existing transaction."
                ),
                identity=identity,
                linked_object_type="bank_transaction",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        if identity.canonical_key and existing is not None and match_kind == "migration_ambiguous":
            return ObjectDedupDecision(
                decision=ImportDecision.SUSPECTED_DUPLICATE,
                decision_reason=(
                    "Bank transaction business fields matched existing data, but official reference evidence was "
                    "missing or ambiguous."
                ),
                identity=identity,
                linked_object_type="bank_transaction",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        if not identity.canonical_key and identity.suspected_key and existing is not None:
            return ObjectDedupDecision(
                decision=ImportDecision.SUSPECTED_DUPLICATE,
                decision_reason="Bank transaction fingerprint matched without an official bank reference.",
                identity=identity,
                linked_object_type="bank_transaction",
                linked_object_id=existing.id,
                matched_object=existing,
            )
        if identity.canonical_key and match_kind == "canonical_position_conflict":
            position_identity = self._identity_policy.identify_bank_transaction_position_mapping(normalized)
            if position_identity.canonical_key == identity.canonical_key:
                raise ValueError("bank transaction canonical collision lacks statement-position evidence")
            position_match = (
                self._repository.find_bank_transaction_by_identity(
                    canonical_key=position_identity.canonical_key,
                    suspected_key=None,
                )
                if self._repository is not None
                else None
            )
            if position_match is not None:
                if not _bank_position_compatible(normalized, position_match):
                    raise ValueError(
                        "bank transaction statement-position identity collision"
                    )
                return ObjectDedupDecision(
                    decision=ImportDecision.DUPLICATE_SKIPPED,
                    decision_reason=(
                        "Bank transaction statement-position identity matched an existing transaction."
                    ),
                    identity=position_identity,
                    linked_object_type="bank_transaction",
                    linked_object_id=position_match.id,
                    matched_object=position_match,
                )
            statement_position = self._bank_identity_service.statement_position_for_mapping(
                normalized
            )
            legacy_position_matches = (
                self._repository.find_bank_transactions_by_statement_position(
                    position=statement_position
                )
                if self._repository is not None and statement_position is not None
                else []
            )
            if len(legacy_position_matches) == 1:
                legacy_position_match = legacy_position_matches[0]
                return ObjectDedupDecision(
                    decision=ImportDecision.DUPLICATE_SKIPPED,
                    decision_reason=(
                        "Complete statement position matched one legacy transaction without a bank-v4 identity."
                    ),
                    identity=position_identity,
                    linked_object_type="bank_transaction",
                    linked_object_id=legacy_position_match.id,
                    matched_object=legacy_position_match,
                )
            if legacy_position_matches:
                return ObjectDedupDecision(
                    decision=ImportDecision.SUSPECTED_DUPLICATE,
                    decision_reason=(
                        "Complete statement position matched multiple legacy transactions; confirmation requires repair."
                    ),
                    identity=position_identity,
                    linked_object_type="bank_transaction",
                    linked_object_id=legacy_position_matches[0].id,
                    matched_object=legacy_position_matches[0],
                )
            return ObjectDedupDecision(
                decision=ImportDecision.CREATED,
                decision_reason="Canonical bank reference was reused for a distinct statement position.",
                identity=position_identity,
            )
        return ObjectDedupDecision(
            decision=ImportDecision.CREATED,
            decision_reason="Ready to create new bank transaction.",
            identity=identity,
        )

    def canonical_invoice_key_exists(self, canonical_key: str) -> bool:
        normalized = _text(canonical_key)
        if not normalized or self._repository is None:
            return False
        exists = getattr(self._repository, "canonical_invoice_key_exists", None)
        if callable(exists):
            return bool(exists(normalized))
        return self._repository.find_invoice_by_identity(canonical_key=normalized) is not None

    def _find_invoice(self, identity: ObjectIdentity) -> Invoice | None:
        if self._repository is None:
            return None
        invoice = self._repository.find_invoice_by_identity(
            canonical_key=identity.canonical_key,
            suspected_key=None if identity.canonical_key else identity.suspected_key,
        )
        if invoice is not None:
            return invoice
        if identity.canonical_key and identity.suspected_key:
            return self._repository.find_invoice_by_identity(canonical_key=None, suspected_key=identity.suspected_key)
        return None

    def _find_bank_transaction(
        self,
        identity: ObjectIdentity,
        *,
        normalized: dict[str, Any],
    ) -> tuple[BankTransaction | None, str | None]:
        if self._repository is None:
            return None, None
        transaction = self._repository.find_bank_transaction_by_identity(
            canonical_key=identity.canonical_key,
            suspected_key=None if identity.canonical_key else identity.suspected_key,
        )
        if transaction is not None and _bank_position_compatible(normalized, transaction):
            return transaction, "canonical" if identity.canonical_key else "suspected"
        canonical_position_conflict = bool(transaction is not None and identity.canonical_key)
        if identity.canonical_key and identity.suspected_key:
            candidates = self._repository.find_bank_transactions_by_identity(
                canonical_key=None,
                suspected_key=identity.suspected_key,
            )
            exact_matches: list[BankTransaction] = []
            ambiguous_matches: list[BankTransaction] = []
            incoming_references = self._official_reference_values(identity)
            for candidate in candidates:
                if not _bank_position_compatible(normalized, candidate):
                    continue
                candidate_identity = self._identity_policy.identify_bank_transaction(candidate)
                candidate_references = self._official_reference_values(candidate_identity)
                if incoming_references and candidate_references:
                    if incoming_references.intersection(candidate_references):
                        exact_matches.append(candidate)
                    continue
                ambiguous_matches.append(candidate)
            if len(exact_matches) == 1:
                return exact_matches[0], "migration_exact"
            if exact_matches:
                return exact_matches[0], "migration_ambiguous"
            if ambiguous_matches:
                return ambiguous_matches[0], "migration_ambiguous"
        return None, "canonical_position_conflict" if canonical_position_conflict else None

    @staticmethod
    def _official_reference_values(identity: ObjectIdentity) -> set[str]:
        return {
            "".join(str(value).split()).upper()
            for field_name, value in identity.audit_fields.items()
            if field_name in {"account_detail_no", "bank_serial_no", "enterprise_serial_no"} and _text(value)
        }

    @staticmethod
    def _is_etc_invoice(normalized: dict[str, Any]) -> bool:
        tags = {str(tag or "").strip().upper() for tag in list(normalized.get("tags") or [])}
        invoice_source = str(normalized.get("invoice_source") or "").upper()
        invoice_kind = str(normalized.get("invoice_kind") or "").upper()
        return "ETC" in tags or "ETC" in invoice_source or "ETC" in invoice_kind


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _bank_position_compatible(incoming: dict[str, Any], existing: BankTransaction) -> bool:
    incoming_balance = _decimal_value(incoming.get("balance"))
    existing_balance = _decimal_value(getattr(existing, "balance", None))
    if incoming_balance is not None and existing_balance is not None and incoming_balance != existing_balance:
        return False

    incoming_currency = _canonical_currency(incoming.get("currency"))
    existing_currency = _canonical_currency(getattr(existing, "currency", None))
    return not (
        incoming_currency
        and existing_currency
        and incoming_currency != existing_currency
    )


def _decimal_value(value: Any) -> Decimal | None:
    normalized = (_text(value) or "").replace(",", "")
    if not normalized:
        return None
    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def _canonical_currency(value: Any) -> str:
    normalized = "".join((_text(value) or "").upper().split())
    if normalized in {"CNY", "RMB", "人民币", "人民币元"}:
        return "CNY"
    return normalized
