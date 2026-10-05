from __future__ import annotations

import hashlib
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_source_identity import (
    OASourceIdentities,
    OASourceIdentityConflict,
    source_document_row_id,
)
from fin_ops_platform.services.postgres_repositories.common import jsonb


class PostgresOASourceIdentityRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_identities(self) -> OASourceIdentities:
        identities = OASourceIdentities()
        for row in self._connection.fetch_all(
            "select alias_row_id, canonical_row_id from app.oa_source_aliases where status = 'active'", ()
        ) or []:
            identities.aliases[row["alias_row_id"]] = row["canonical_row_id"]
        for row in self._connection.fetch_all(
            """
            select row_id, normalized_payload->'detail_fields'->>'Mongo文档ID' as document_id,
                   normalized_payload->>'apply_type' as apply_type
            from app.oa_applications
            union all
            select oa_id, source_payload->'detail_fields'->>'Mongo文档ID', source_payload->>'apply_type'
            from app.oa_pending_payment_admissions
            """, ()
        ) or []:
            if row.get("document_id"):
                identities.add_owner(
                    source_document_row_id(row["apply_type"], row["document_id"]), row["row_id"]
                )
        return identities

    def record_identities(self, records: list[OAApplicationRecord]) -> None:
        """Validate and persist aliases inside the caller's OA owner transaction."""
        records = [record for record in records if record.detail_fields.get("Mongo文档ID")]
        if not records:
            return
        identities = self.load_identities()
        canonical_ids = set(identities.owners.values()) | {record.id for record in records}
        aliases: dict[str, str] = {}
        for record in records:
            document_id = str(record.detail_fields.get("Mongo文档ID") or "").strip()
            if not document_id:
                continue  # Manual facts have no Mongo owner.
            source_id = source_document_row_id(record.apply_type, document_id)
            expected = identities.canonical_id(source_id)
            if (source_id in identities.owners or source_id in identities.aliases) and expected != record.id:
                raise OASourceIdentityConflict(f"oa_source_identity_changed: {source_id}")
            identities.add_owner(source_id, record.id)
            for alias in {source_id, *record.source_aliases} - {record.id}:
                previous = aliases.get(alias) or identities.aliases.get(alias)
                if alias in canonical_ids:
                    raise OASourceIdentityConflict(f"oa_source_identity_canonical_collision: {alias}")
                if previous and previous != record.id:
                    raise OASourceIdentityConflict(f"oa_source_identity_conflict: {alias}")
                if alias not in identities.aliases:
                    aliases[alias] = record.id
        if not aliases:
            return
        payload = [
            {"alias": alias, "canonical": canonical,
             "evidence": hashlib.sha256(f"{alias}|{canonical}".encode()).hexdigest()}
            for alias, canonical in sorted(aliases.items())
        ]
        rows = self._connection.fetch_all(
            """
            insert into app.oa_source_aliases(
                alias_row_id, canonical_row_id, reason, evidence_hash, status, reviewed_by, reviewed_at
            )
            select x.alias, x.canonical, 'verified_source_document_identity', x.evidence,
                   'active', 'system:oa_source_sync', now()
            from jsonb_to_recordset(%s::jsonb) x(alias text, canonical text, evidence text)
            on conflict (alias_row_id) where status in ('pending_review', 'active')
            do update set status = 'active', updated_at = now()
            where app.oa_source_aliases.canonical_row_id = excluded.canonical_row_id
            returning alias_row_id
            """,
            (jsonb(payload),),
        ) or []
        if len(rows) != len(aliases):
            raise OASourceIdentityConflict("oa_source_identity_alias_conflict")
