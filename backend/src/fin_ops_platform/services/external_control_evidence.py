from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import re
from typing import Any, Mapping, Protocol


EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION = "external-control-evidence.v1"
EXTERNAL_CONTROL_EVIDENCE_DOMAINS = ("bank", "oa", "invoice", "etc")
EXTERNAL_CONTROL_EVIDENCE_COVERAGE_MODE = "complete_snapshot"
EXTERNAL_CONTROL_EVIDENCE_SCOPE_KEY = "all"


@dataclass(frozen=True, slots=True)
class ExternalEvidenceItemContract:
    domain: str
    identity_fields: tuple[str, ...]
    field_types: Mapping[str, str]


ITEM_CONTRACTS: dict[str, ExternalEvidenceItemContract] = {
    "bank_transaction": ExternalEvidenceItemContract(
        domain="bank",
        identity_fields=(
            "account_no",
            "txn_direction",
            "trade_time",
            "bank_serial_no",
            "amount",
            "counterparty_name",
        ),
        field_types={
            "account_no": "text",
            "txn_direction": "text",
            "trade_time": "instant",
            "bank_serial_no": "text",
            "amount": "decimal",
            "counterparty_name": "text",
            "balance": "decimal",
            "currency": "text",
            "summary": "text",
            "remark": "text",
            "status": "text",
        },
    ),
    "oa_application": ExternalEvidenceItemContract(
        domain="oa",
        identity_fields=("form_id", "oa_source_id"),
        field_types={
            "form_id": "text",
            "oa_source_id": "text",
            "workflow_no": "text",
            "status": "text",
            "applicant": "text",
            "application_date": "date",
            "amount": "decimal",
            "project_id": "text",
            "project_name": "text",
            "source_updated_at": "instant",
        },
    ),
    "oa_item": ExternalEvidenceItemContract(
        domain="oa",
        identity_fields=("form_id", "oa_source_id", "row_id", "item_type", "item_no", "amount"),
        field_types={
            "form_id": "text",
            "oa_source_id": "text",
            "row_id": "text",
            "item_type": "text",
            "item_no": "text",
            "amount": "decimal",
            "tax_amount": "decimal",
            "project_id": "text",
            "project_name": "text",
        },
    ),
    "oa_attachment": ExternalEvidenceItemContract(
        domain="oa",
        identity_fields=("form_id", "oa_source_id", "source_attachment_key"),
        field_types={
            "form_id": "text",
            "oa_source_id": "text",
            "source_attachment_key": "text",
            "filename": "text",
            "size_bytes": "integer",
            "source_modified_at": "instant",
            "file_sha256": "sha256_optional",
        },
    ),
    "invoice": ExternalEvidenceItemContract(
        domain="invoice",
        identity_fields=(
            "invoice_type",
            "invoice_no",
            "invoice_code",
            "digital_invoice_no",
            "invoice_date",
            "seller_tax_no",
            "buyer_tax_no",
        ),
        field_types={
            "invoice_type": "text",
            "invoice_no": "text",
            "invoice_code": "text",
            "digital_invoice_no": "text",
            "invoice_date": "date",
            "seller_name": "text",
            "seller_tax_no": "text",
            "buyer_name": "text",
            "buyer_tax_no": "text",
            "amount": "decimal",
            "tax_amount": "decimal",
            "total_with_tax": "decimal",
            "currency": "text",
            "status": "text",
        },
    ),
    "tax_certified_invoice": ExternalEvidenceItemContract(
        domain="invoice",
        identity_fields=("certified_unique_key",),
        field_types={
            "certified_unique_key": "text",
            "invoice_no": "text",
            "invoice_code": "text",
            "digital_invoice_no": "text",
            "seller_name": "text",
            "seller_tax_no": "text",
            "invoice_date": "date",
            "amount": "decimal",
            "tax_amount": "decimal",
            "status": "text",
        },
    ),
    "etc_invoice": ExternalEvidenceItemContract(
        domain="etc",
        identity_fields=("etc_invoice_id",),
        field_types={
            "etc_invoice_id": "text",
            "invoice_no": "text",
            "invoice_code": "text",
            "invoice_date": "date",
            "seller_name": "text",
            "buyer_name": "text",
            "amount": "decimal",
            "tax_amount": "decimal",
            "total_with_tax": "decimal",
            "status": "text",
            "file_sha256": "sha256_optional",
        },
    ),
    "etc_archive": ExternalEvidenceItemContract(
        domain="etc",
        identity_fields=("sha256", "size_bytes", "original_filename"),
        field_types={
            "sha256": "sha256_optional",
            "size_bytes": "integer",
            "original_filename": "text",
        },
    ),
}

DOMAIN_ITEM_KINDS: dict[str, tuple[str, ...]] = {
    domain: tuple(kind for kind, contract in ITEM_CONTRACTS.items() if contract.domain == domain)
    for domain in EXTERNAL_CONTROL_EVIDENCE_DOMAINS
}


@dataclass(frozen=True, slots=True)
class NormalizedExternalEvidenceItem:
    item_kind: str
    item_key: str
    content_fingerprint: str
    normalized_fields: dict[str, str]

    def safe_payload(self) -> dict[str, str]:
        return {
            "item_kind": self.item_kind,
            "item_key": self.item_key,
            "content_fingerprint": self.content_fingerprint,
        }


@dataclass(frozen=True, slots=True)
class NormalizedExternalEvidenceManifest:
    tenant_id: str
    domain: str
    contract_version: str
    coverage_mode: str
    scope_key: str
    source_system: str
    source_snapshot_id: str
    observed_at: datetime
    valid_until: datetime
    artifact_sha256: str
    artifact_size_bytes: int
    collector_name: str
    collector_version: str
    controls: dict[str, Any]
    items: tuple[NormalizedExternalEvidenceItem, ...]
    manifest_fingerprint: str

    def safe_payload(self) -> dict[str, Any]:
        return {
            "tenant_id": self.tenant_id,
            "domain": self.domain,
            "contract_version": self.contract_version,
            "coverage_mode": self.coverage_mode,
            "scope_key": self.scope_key,
            "source_system": self.source_system,
            "source_snapshot_id": self.source_snapshot_id,
            "observed_at": self.observed_at.isoformat(),
            "valid_until": self.valid_until.isoformat(),
            "artifact_sha256": self.artifact_sha256,
            "artifact_size_bytes": self.artifact_size_bytes,
            "collector_name": self.collector_name,
            "collector_version": self.collector_version,
            "controls": self.controls,
            "item_count": len(self.items),
            "manifest_fingerprint": self.manifest_fingerprint,
        }


class ExternalControlEvidenceRepositoryPort(Protocol):
    def register(
        self,
        manifest: NormalizedExternalEvidenceManifest,
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]: ...

    def revoke(
        self,
        evidence_id: str,
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]: ...

    def inspect(self, *, tenant_id: str, domain: str | None = None) -> list[dict[str, Any]]: ...


class ExternalControlEvidenceService:
    def __init__(self, repository: ExternalControlEvidenceRepositoryPort | None = None) -> None:
        self._repository = repository

    def validate_manifest(self, payload: Mapping[str, Any]) -> NormalizedExternalEvidenceManifest:
        if not isinstance(payload, Mapping):
            raise ValueError("external evidence manifest must be an object")
        contract_version = _required_text(payload, "contract_version")
        if contract_version != EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION:
            raise ValueError(f"unsupported external evidence contract_version: {contract_version}")
        domain = _required_text(payload, "domain").lower()
        if domain not in EXTERNAL_CONTROL_EVIDENCE_DOMAINS:
            raise ValueError(f"unsupported external evidence domain: {domain}")
        coverage_mode = _required_text(payload, "coverage_mode")
        scope_key = _required_text(payload, "scope_key")
        if coverage_mode != EXTERNAL_CONTROL_EVIDENCE_COVERAGE_MODE or scope_key != EXTERNAL_CONTROL_EVIDENCE_SCOPE_KEY:
            raise ValueError("external evidence v1 only accepts coverage_mode=complete_snapshot and scope_key=all")

        observed_at = _datetime(payload.get("observed_at"), "observed_at")
        valid_until = _datetime(payload.get("valid_until"), "valid_until")
        if valid_until <= observed_at:
            raise ValueError("valid_until must be later than observed_at")
        artifact = payload.get("artifact")
        if not isinstance(artifact, Mapping):
            raise ValueError("artifact must be an object")
        artifact_sha256 = _sha256(artifact.get("sha256"), "artifact.sha256")
        artifact_size_bytes = _nonnegative_integer(artifact.get("size_bytes"), "artifact.size_bytes")
        collector = payload.get("collector")
        if not isinstance(collector, Mapping):
            raise ValueError("collector must be an object")

        raw_items = payload.get("items")
        if not isinstance(raw_items, list):
            raise ValueError("items must be an array")
        items = tuple(normalize_external_evidence_item(domain=domain, payload=item) for item in raw_items)
        item_identities = [(item.item_kind, item.item_key) for item in items]
        if len(item_identities) != len(set(item_identities)):
            raise ValueError("external evidence manifest contains duplicate item identity")
        sorted_items = tuple(sorted(items, key=lambda item: (item.item_kind, item.item_key)))
        controls = external_evidence_controls(sorted_items)
        declared_controls = payload.get("controls")
        if not isinstance(declared_controls, Mapping):
            raise ValueError("controls must be an object")
        if _canonical_json(dict(declared_controls)) != _canonical_json(controls):
            raise ValueError("declared controls do not match normalized manifest items")

        tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
        fingerprint_payload = {
            "contract_version": contract_version,
            "tenant_id": tenant_id,
            "domain": domain,
            "coverage_mode": coverage_mode,
            "scope_key": scope_key,
            "source_system": _required_text(payload, "source_system"),
            "source_snapshot_id": _required_text(payload, "source_snapshot_id"),
            "observed_at": observed_at.isoformat(),
            "valid_until": valid_until.isoformat(),
            "artifact_sha256": artifact_sha256,
            "artifact_size_bytes": artifact_size_bytes,
            "collector_name": _required_text(collector, "name"),
            "collector_version": _required_text(collector, "version"),
            "controls": controls,
            "items": [item.safe_payload() for item in sorted_items],
        }
        return NormalizedExternalEvidenceManifest(
            tenant_id=tenant_id,
            domain=domain,
            contract_version=contract_version,
            coverage_mode=coverage_mode,
            scope_key=scope_key,
            source_system=fingerprint_payload["source_system"],
            source_snapshot_id=fingerprint_payload["source_snapshot_id"],
            observed_at=observed_at,
            valid_until=valid_until,
            artifact_sha256=artifact_sha256,
            artifact_size_bytes=artifact_size_bytes,
            collector_name=fingerprint_payload["collector_name"],
            collector_version=fingerprint_payload["collector_version"],
            controls=controls,
            items=sorted_items,
            manifest_fingerprint=_fingerprint(fingerprint_payload),
        )

    def register(
        self,
        payload: Mapping[str, Any],
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        manifest = self.validate_manifest(payload)
        repository = self._required_repository()
        return repository.register(manifest, actor=_required_argument(actor, "actor"), reason=_required_argument(reason, "reason"))

    def revoke(self, evidence_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        repository = self._required_repository()
        return repository.revoke(
            _required_argument(evidence_id, "evidence_id"),
            actor=_required_argument(actor, "actor"),
            reason=_required_argument(reason, "reason"),
        )

    def inspect(self, *, tenant_id: str = "default", domain: str | None = None) -> list[dict[str, Any]]:
        normalized_domain = str(domain or "").strip().lower() or None
        if normalized_domain is not None and normalized_domain not in EXTERNAL_CONTROL_EVIDENCE_DOMAINS:
            raise ValueError(f"unsupported external evidence domain: {normalized_domain}")
        return self._required_repository().inspect(
            tenant_id=str(tenant_id or "default").strip() or "default",
            domain=normalized_domain,
        )

    def _required_repository(self) -> ExternalControlEvidenceRepositoryPort:
        if self._repository is None:
            raise RuntimeError("external control evidence repository is not configured")
        return self._repository


def normalize_external_evidence_item(*, domain: str, payload: Any) -> NormalizedExternalEvidenceItem:
    if not isinstance(payload, Mapping):
        raise ValueError("external evidence item must be an object")
    item_kind = _required_text(payload, "kind")
    contract = ITEM_CONTRACTS.get(item_kind)
    if contract is None or contract.domain != domain:
        raise ValueError(f"item kind {item_kind!r} does not belong to external evidence domain {domain!r}")
    fields = payload.get("fields")
    if not isinstance(fields, Mapping):
        raise ValueError(f"{item_kind}.fields must be an object")
    unknown_fields = sorted(set(fields) - set(contract.field_types))
    if unknown_fields:
        raise ValueError(f"{item_kind}.fields contains unsupported fields: {unknown_fields}")
    normalized_fields = {
        field_name: _normalize_field(fields.get(field_name), field_type, f"{item_kind}.{field_name}")
        for field_name, field_type in contract.field_types.items()
    }
    if any(not normalized_fields[field_name] for field_name in contract.identity_fields):
        missing = [field_name for field_name in contract.identity_fields if not normalized_fields[field_name]]
        raise ValueError(f"{item_kind} identity fields must be non-empty: {missing}")
    item_key = f"{item_kind}:{_fingerprint([normalized_fields[field] for field in contract.identity_fields])}"
    content_fingerprint = _fingerprint(normalized_fields)
    supplied_key = str(payload.get("key") or "").strip()
    if supplied_key and supplied_key != item_key:
        raise ValueError(f"{item_kind} supplied key does not match normalized identity")
    supplied_fingerprint = str(payload.get("fingerprint") or "").strip().lower()
    if supplied_fingerprint and supplied_fingerprint != content_fingerprint:
        raise ValueError(f"{item_kind} supplied fingerprint does not match normalized fields")
    return NormalizedExternalEvidenceItem(
        item_kind=item_kind,
        item_key=item_key,
        content_fingerprint=content_fingerprint,
        normalized_fields=normalized_fields,
    )


def external_evidence_controls(items: tuple[NormalizedExternalEvidenceItem, ...]) -> dict[str, Any]:
    counts_by_kind: dict[str, int] = {}
    amount_totals_by_kind: dict[str, Decimal] = {}
    tax_totals_by_kind: dict[str, Decimal] = {}
    for item in items:
        counts_by_kind[item.item_kind] = counts_by_kind.get(item.item_kind, 0) + 1
        fields = item.normalized_fields
        amount_totals_by_kind[item.item_kind] = amount_totals_by_kind.get(item.item_kind, Decimal("0")) + _decimal(
            fields.get("amount")
        )
        tax_totals_by_kind[item.item_kind] = tax_totals_by_kind.get(item.item_kind, Decimal("0")) + _decimal(
            fields.get("tax_amount")
        )
    return {
        "item_count": len(items),
        "counts_by_kind": {key: counts_by_kind[key] for key in sorted(counts_by_kind)},
        "amount_totals_by_kind": {key: _decimal_text(amount_totals_by_kind[key]) for key in sorted(amount_totals_by_kind)},
        "tax_totals_by_kind": {key: _decimal_text(tax_totals_by_kind[key]) for key in sorted(tax_totals_by_kind)},
    }


def _normalize_field(value: Any, field_type: str, label: str) -> str:
    if field_type == "text":
        return str(value or "").strip()
    if field_type == "decimal":
        if value in (None, ""):
            return "0"
        try:
            return _decimal_text(Decimal(str(value).strip()))
        except InvalidOperation as exc:
            raise ValueError(f"{label} must be a decimal") from exc
    if field_type == "integer":
        if value in (None, ""):
            return "0"
        return str(_nonnegative_integer(value, label))
    if field_type == "date":
        if value in (None, ""):
            return ""
        text = str(value).strip()
        try:
            return datetime.fromisoformat(text).date().isoformat()
        except ValueError as exc:
            raise ValueError(f"{label} must be an ISO date") from exc
    if field_type == "instant":
        if value in (None, ""):
            return ""
        return _datetime(value, label).isoformat()
    if field_type == "sha256_optional":
        if value in (None, ""):
            return ""
        return _sha256(value, label)
    raise ValueError(f"unsupported field type: {field_type}")


def _datetime(value: Any, label: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label} is required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be an ISO datetime") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must include a timezone")
    return parsed.astimezone(UTC)


def _required_text(payload: Mapping[str, Any], key: str) -> str:
    value = str(payload.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _required_argument(value: Any, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _sha256(value: Any, label: str) -> str:
    normalized = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError(f"{label} must be a lowercase sha256 hex digest")
    return normalized


def _nonnegative_integer(value: Any, label: str) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a non-negative integer") from exc
    if normalized < 0:
        raise ValueError(f"{label} must be a non-negative integer")
    return normalized


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or "0"))
    except InvalidOperation:
        return Decimal("0")


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
