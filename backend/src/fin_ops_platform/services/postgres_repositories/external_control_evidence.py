from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.external_control_evidence import NormalizedExternalEvidenceManifest


class PostgresExternalControlEvidenceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def register(
        self,
        manifest: NormalizedExternalEvidenceManifest,
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._connection.transaction() as transaction:
            existing = transaction.fetch_one(
                """
                select evidence_id::text as evidence_id, status, registered_at, revoked_at
                from audit.external_control_evidence
                where tenant_id = %s and domain = %s and manifest_fingerprint = %s
                """,
                (manifest.tenant_id, manifest.domain, manifest.manifest_fingerprint),
            )
            if existing is not None:
                return {
                    "evidence_id": str(existing.get("evidence_id") or ""),
                    "domain": manifest.domain,
                    "manifest_fingerprint": manifest.manifest_fingerprint,
                    "status": str(existing.get("status") or "registered"),
                    "created": False,
                    "idempotent_replay": True,
                    "registered_at": existing.get("registered_at"),
                    "revoked_at": existing.get("revoked_at"),
                }

            row = transaction.fetch_one(
                """
                insert into audit.external_control_evidence (
                    tenant_id, domain, contract_version, coverage_mode, scope_key,
                    source_system, source_snapshot_id, observed_at, valid_until,
                    artifact_sha256, artifact_size_bytes, collector_name, collector_version,
                    manifest_fingerprint, declared_controls, item_count,
                    registered_by, registration_reason
                ) values (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s
                )
                returning evidence_id::text as evidence_id, status, registered_at
                """,
                (
                    manifest.tenant_id,
                    manifest.domain,
                    manifest.contract_version,
                    manifest.coverage_mode,
                    manifest.scope_key,
                    manifest.source_system,
                    manifest.source_snapshot_id,
                    manifest.observed_at,
                    manifest.valid_until,
                    manifest.artifact_sha256,
                    manifest.artifact_size_bytes,
                    manifest.collector_name,
                    manifest.collector_version,
                    manifest.manifest_fingerprint,
                    _json(manifest.controls),
                    len(manifest.items),
                    actor,
                    reason,
                ),
            )
            evidence_id = str((row or {}).get("evidence_id") or "")
            if not evidence_id:
                raise RuntimeError("external evidence registration did not return an evidence_id")
            transaction.execute_many_values(
                """
                insert into audit.external_control_evidence_items (
                    evidence_id, item_kind, item_key, content_fingerprint, normalized_fields
                ) values (%s::uuid, %s, %s, %s, %s::jsonb)
                """,
                [
                    (
                        evidence_id,
                        item.item_kind,
                        item.item_key,
                        item.content_fingerprint,
                        _json(item.normalized_fields),
                    )
                    for item in manifest.items
                ],
            )
            audit_id = self._record_event(
                transaction,
                event_type="external_control_evidence.registered",
                object_id=evidence_id,
                actor=actor,
                reason=reason,
                payload={
                    "tenant_id": manifest.tenant_id,
                    "domain": manifest.domain,
                    "source_system": manifest.source_system,
                    "source_snapshot_id": manifest.source_snapshot_id,
                    "observed_at": manifest.observed_at.isoformat(),
                    "valid_until": manifest.valid_until.isoformat(),
                    "artifact_sha256": manifest.artifact_sha256,
                    "artifact_size_bytes": manifest.artifact_size_bytes,
                    "manifest_fingerprint": manifest.manifest_fingerprint,
                    "item_count": len(manifest.items),
                    "controls": manifest.controls,
                    "reason": reason,
                },
            )
            return {
                "evidence_id": evidence_id,
                "domain": manifest.domain,
                "manifest_fingerprint": manifest.manifest_fingerprint,
                "status": str((row or {}).get("status") or "registered"),
                "created": True,
                "idempotent_replay": False,
                "registered_at": (row or {}).get("registered_at"),
                "audit_id": audit_id,
            }

    def revoke(
        self,
        evidence_id: str,
        *,
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        with self._connection.transaction() as transaction:
            current = transaction.fetch_one(
                """
                select evidence_id::text as evidence_id, tenant_id, domain, status, manifest_fingerprint, revoked_at
                from audit.external_control_evidence
                where evidence_id = %s::uuid
                for update
                """,
                (evidence_id,),
            )
            if current is None:
                raise KeyError(evidence_id)
            if str(current.get("status") or "") == "revoked":
                return {
                    "evidence_id": evidence_id,
                    "domain": str(current.get("domain") or ""),
                    "manifest_fingerprint": str(current.get("manifest_fingerprint") or ""),
                    "status": "revoked",
                    "revoked": False,
                    "idempotent_replay": True,
                    "revoked_at": current.get("revoked_at"),
                }
            updated = transaction.fetch_one(
                """
                update audit.external_control_evidence
                set status = 'revoked', revoked_by = %s, revocation_reason = %s, revoked_at = now()
                where evidence_id = %s::uuid and status = 'registered'
                returning revoked_at
                """,
                (actor, reason, evidence_id),
            )
            if updated is None:
                raise RuntimeError("external evidence revoke lost its locked row")
            audit_id = self._record_event(
                transaction,
                event_type="external_control_evidence.revoked",
                object_id=evidence_id,
                actor=actor,
                reason=reason,
                payload={
                    "tenant_id": str(current.get("tenant_id") or "default"),
                    "domain": str(current.get("domain") or ""),
                    "manifest_fingerprint": str(current.get("manifest_fingerprint") or ""),
                    "reason": reason,
                },
            )
            return {
                "evidence_id": evidence_id,
                "domain": str(current.get("domain") or ""),
                "manifest_fingerprint": str(current.get("manifest_fingerprint") or ""),
                "status": "revoked",
                "revoked": True,
                "idempotent_replay": False,
                "revoked_at": updated.get("revoked_at"),
                "audit_id": audit_id,
            }

    def inspect(self, *, tenant_id: str, domain: str | None = None) -> list[dict[str, Any]]:
        domain_filter = ""
        params: tuple[Any, ...] = (tenant_id,)
        if domain:
            domain_filter = "and evidence.domain = %s"
            params = (tenant_id, domain)
        return self._connection.fetch_all(
            f"""
            select
                evidence.evidence_id::text as evidence_id,
                evidence.tenant_id,
                evidence.domain,
                evidence.contract_version,
                evidence.coverage_mode,
                evidence.scope_key,
                evidence.source_system,
                evidence.source_snapshot_id,
                evidence.observed_at,
                evidence.valid_until,
                evidence.artifact_sha256,
                evidence.artifact_size_bytes,
                evidence.collector_name,
                evidence.collector_version,
                evidence.manifest_fingerprint,
                evidence.declared_controls,
                evidence.item_count,
                evidence.status,
                evidence.registered_by,
                evidence.registration_reason,
                evidence.registered_at,
                evidence.revoked_by,
                evidence.revocation_reason,
                evidence.revoked_at
            from audit.external_control_evidence evidence
            where evidence.tenant_id = %s
              {domain_filter}
            order by evidence.domain, evidence.observed_at desc, evidence.registered_at desc, evidence.evidence_id desc
            """,
            params,
        )

    @staticmethod
    def _record_event(
        transaction: Any,
        *,
        event_type: str,
        object_id: str,
        actor: str,
        reason: str,
        payload: dict[str, Any],
    ) -> str:
        row = transaction.fetch_one(
            """
            insert into audit.events (
                event_type, object_type, object_id, actor_id, scope, payload, raw_payload
            ) values (%s, 'external_control_evidence', %s, %s, 'external_evidence', %s::jsonb, %s::jsonb)
            returning id::text as audit_id
            """,
            (
                event_type,
                object_id,
                actor,
                _json(payload),
                _json(
                    {
                        "event_type": event_type,
                        "object_type": "external_control_evidence",
                        "object_id": object_id,
                        "actor": actor,
                        "reason": reason,
                        "payload": payload,
                    }
                ),
            ),
        )
        return str((row or {}).get("audit_id") or "")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
