from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import jsonb


class PostgresSharedImportRepository:
    """Transaction-bound persistence for manual OA imports."""

    def __init__(self, transaction: Any) -> None:
        self._transaction = transaction

    def save_oa_records(self, records: list[Any]) -> None:
        from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository
        repository = PostgresOAProjectionRepository(self._transaction)
        for month in sorted({record.month for record in records}):
            repository.upsert_targeted_application_records(
                [record for record in records if record.month == month], scope_key=month)

    def add_manual_oa_imports(self, row_ids: list[str], *, actor_id: str) -> dict[str, object]:
        imported: list[str] = []
        already_imported: list[str] = []
        entries: dict[str, object] = {}
        for row_id in sorted(set(row_ids)):
            if not row_id.strip():
                raise ValueError("OA row id must not be empty.")
            payload = {"row_id": row_id, "source": "manual_oa_import", "actor_id": actor_id, "audit": {}}
            row = self._transaction.fetch_one("""
                insert into app.manual_oa_imports(row_id,source,actor_id,imported_at,status,audit_payload,raw_payload)
                values (%s,'manual_oa_import',%s,now(),'active','{}',%s)
                on conflict(row_id) do update set status='active', actor_id=excluded.actor_id,
                    imported_at=now(), raw_payload=excluded.raw_payload
                where app.manual_oa_imports.status <> 'active'
                returning row_id, imported_at
            """, (row_id, actor_id, jsonb({"normalized_payload": payload})))
            (imported if row else already_imported).append(row_id)
            if row:
                payload["imported_at"] = row["imported_at"].isoformat()
            entries[row_id] = payload
        existing = self._transaction.fetch_all("""
            select row_id, imported_at, actor_id from app.manual_oa_imports
            where row_id=any(%s::text[]) and status='active'
        """, (already_imported,)) if already_imported else []
        for row in existing:
            entries[row["row_id"]].update(imported_at=row["imported_at"].isoformat(), actor_id=row["actor_id"])
        return {"imported": imported, "already_imported": already_imported, "entries": entries, "row_ids": sorted(entries)}
