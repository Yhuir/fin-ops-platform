"""发票原件属性维护的 canonical 读取及版本写入边界。"""

from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


def load_snapshot(connection: Any, *, lock: bool = False) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """select coalesce(legacy_mongo_id,id::text) as invoice_id,
        invoice_type, invoice_no, invoice_code, digital_invoice_no, invoice_date::text, buyer_tax_no, source_links,
        updated_at, raw_payload from app.invoices where status <> 'deleted' order by id"""
        + (" for update" if lock else "")
    )


def load_original_files(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all("""select coalesce(f.legacy_mongo_id,f.id::text) as file_id,
        f.original_filename, f.stored_file_path, o.sha256, f.raw_payload
        from app.import_files f join app.file_objects o on o.id=f.file_object_id
        where o.tombstoned_at is null order by f.id""")


def load_etc_originals(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all("""select coalesce(legacy_mongo_id,id::text) as etc_invoice_id,
        raw_payload from app.etc_invoices order by id""")


def apply_updates(connection: Any, updates: list[dict[str, Any]]) -> None:
    PostgresCoreRepository(connection).repair_verified_invoice_source_attributes(updates)
