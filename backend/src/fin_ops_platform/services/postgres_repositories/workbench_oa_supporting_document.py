from __future__ import annotations

import json
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import run_in_transaction
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from fin_ops_platform.services.postgres_repositories.supporting_document_invoice_basis import (
    SUPPORTING_DOCUMENT_INVOICE_BASIS_SQL,
)
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)
from fin_ops_platform.services.workbench_oa_supporting_document_service import WorkbenchOaSupportingDocumentError


class PostgresWorkbenchOaSupportingDocumentRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def attach_to_oa_rows(self, rows: list[dict[str, Any]]) -> None:
        """Hydrate active evidence for one bounded canonical OA batch."""
        if not rows:
            return
        documents = self._connection.fetch_all(
            f"""
            with invoice_basis as ({SUPPORTING_DOCUMENT_INVOICE_BASIS_SQL}), documents as (
                select document.oa_row_id, document.expense_item_id,
                       document.id::text as id, document.original_filename as file_name,
                       document.content_type, document.size_bytes,
                       document.created_at::text as created_at,
                       '/api/workbench/oa-invoice-supplements/documents/' ||
                           document.id::text || '/content' as content_url
                from app.workbench_oa_supporting_documents document
                join app.file_objects file on file.id = document.file_object_id
                where document.oa_row_id = any(%s::text[])
                  and document.status = 'active' and file.tombstoned_at is null
            ), bundles as (
                select bundle.oa_row_id, bundle.expense_item_id,
                       case when bundle.invoice_basis = coalesce(basis.invoice_basis, '{{}}'::jsonb)
                            then bundle.total_amount::text end as total_amount, bundle.version
                from app.workbench_oa_supporting_document_bundles bundle
                left join invoice_basis basis using (oa_row_id, expense_item_id)
                where bundle.oa_row_id = any(%s::text[])
            )
            select coalesce(documents.oa_row_id, bundles.oa_row_id) as oa_row_id,
                   coalesce(documents.expense_item_id, bundles.expense_item_id) as expense_item_id,
                   documents.id, documents.file_name, documents.content_type,
                   documents.size_bytes, documents.created_at, documents.content_url,
                   bundles.total_amount, coalesce(bundles.version, 0) as version
            from documents full outer join bundles using (oa_row_id, expense_item_id)
            order by documents.created_at, documents.id
            """,
            ([str(row["id"]) for row in rows], [str(row["id"]) for row in rows]),
        )
        by_item: dict[tuple[str, str], list[dict[str, Any]]] = {}
        by_bundle: dict[tuple[str, str], dict[str, Any]] = {}
        for document in documents:
            key = (document["oa_row_id"], document["expense_item_id"])
            by_bundle[key] = {"total_amount": document["total_amount"], "version": document["version"]}
            if document["id"] is not None:
                by_item.setdefault(key, []).append({
                    name: value for name, value in document.items()
                    if name not in {"oa_row_id", "expense_item_id", "total_amount", "version"}
                })
        for row in rows:
            for item in row.get("expense_items") or []:
                key = (str(row["id"]), str(item["id"]))
                item["supporting_documents"] = by_item.get(key, [])
                item["supporting_document_amount"] = by_bundle.get(key, {}).get("total_amount")
                item["supporting_document_version"] = by_bundle.get(key, {}).get("version", 0)

    def get_bundle(self, *, oa_row_id: str, expense_item_id: str) -> dict[str, Any]:
        def read(connection: Any) -> dict[str, Any]:
            connection.execute("set transaction isolation level repeatable read, read only")
            return self._read_bundle(connection, oa_row_id, expense_item_id)
        return run_in_transaction(self._connection, read)

    @staticmethod
    def _read_bundle(connection: Any, oa_row_id: str, expense_item_id: str) -> dict[str, Any]:
        bundle = connection.fetch_one(
            """select total_amount::text as total_amount, version, invoice_basis
               from app.workbench_oa_supporting_document_bundles
               where oa_row_id = %s and expense_item_id = %s""",
            (oa_row_id, expense_item_id),
        ) or {"total_amount": None, "version": 0, "invoice_basis": {}}
        basis = PostgresWorkbenchOaSupportingDocumentRepository._invoice_basis(connection, oa_row_id, expense_item_id)
        documents = PostgresWorkbenchOaSupportingDocumentRepository(connection).list_active(
            oa_row_id=oa_row_id, expense_item_id=expense_item_id,
        )
        bundle["amount_confirmation_required"] = bool(documents) and bundle.pop("invoice_basis") != basis
        bundle.pop("invoice_basis", None)
        return {**bundle, "documents": documents}

    @staticmethod
    def _invoice_basis(connection: Any, oa_row_id: str, expense_item_id: str) -> dict[str, Any]:
        row = connection.fetch_one(
            f"select invoice_basis from ({SUPPORTING_DOCUMENT_INVOICE_BASIS_SQL}) basis "
            "where oa_row_id = %s and expense_item_id = %s", (oa_row_id, expense_item_id),
        )
        return row["invoice_basis"] if row else {}

    def save_bundle(
        self, *, relation_case_id: str, oa_row_id: str, expense_item_id: str,
        actor_id: str, retained_document_ids: list[str], total_amount: str | None,
        expected_version: int, documents: list[dict[str, Any]],
    ) -> dict[str, Any]:
        def write(connection: Any) -> dict[str, Any]:
            connection.execute(
                """insert into app.workbench_oa_supporting_document_bundles
                   (oa_row_id, expense_item_id, created_by, updated_by)
                   values (%s, %s, %s, %s) on conflict do nothing""",
                (oa_row_id, expense_item_id, actor_id, actor_id),
            )
            bundle = connection.fetch_one(
                """select total_amount::text as total_amount, version, invoice_basis
                   from app.workbench_oa_supporting_document_bundles
                   where oa_row_id = %s and expense_item_id = %s for update""",
                (oa_row_id, expense_item_id),
            )
            basis = self._invoice_basis(connection, oa_row_id, expense_item_id)
            current = PostgresWorkbenchOaSupportingDocumentRepository(connection).list_active(
                oa_row_id=oa_row_id, expense_item_id=expense_item_id,
            )
            by_id = {row["id"]: row for row in current}
            if not set(retained_document_ids).issubset(by_id):
                if bundle["version"] != expected_version:
                    raise WorkbenchOaSupportingDocumentError(
                        "supporting_document_version_conflict", "补充凭证已被其他操作更新，请刷新后重试。",
                        current_version=bundle["version"],
                    )
                raise WorkbenchOaSupportingDocumentError(
                    "supporting_document_selection_invalid", "保留的凭证已删除或不属于当前子付款项。",
                )
            target_hashes = {by_id[key]["content_sha256"] for key in retained_document_ids}
            target_hashes.update(row["content_sha256"] for row in documents)
            if bundle["invoice_basis"] == basis and bundle["total_amount"] == total_amount and target_hashes == {
                row["content_sha256"] for row in current
            }:
                return {**bundle, "amount_confirmation_required": False, "documents": current, "removed_storage_uris": []}
            if bundle["version"] != expected_version:
                raise WorkbenchOaSupportingDocumentError(
                    "supporting_document_version_conflict", "补充凭证已被其他操作更新，请刷新后重试。",
                    current_version=bundle["version"],
                )
            removed = [row for row in current if row["content_sha256"] not in target_hashes]
            if removed:
                connection.execute(
                    """update app.workbench_oa_supporting_documents
                       set status = 'deleted', deleted_by = %s, deleted_at = now()
                       where id = any(%s::uuid[])""",
                    (actor_id, [row["id"] for row in removed]),
                )
                connection.execute(
                    """update app.file_objects set tombstoned_at = now(), updated_at = now()
                       where id = any(%s::uuid[])""",
                    ([row["file_object_id"] for row in removed],),
                )
            active_hashes = {row["content_sha256"] for row in current}
            for document in documents:
                if document["content_sha256"] in active_hashes:
                    continue
                connection.execute(
                    """insert into app.workbench_oa_supporting_documents
                       (relation_case_id, oa_row_id, expense_item_id, file_object_id,
                        original_filename, content_type, content_sha256, size_bytes, created_by)
                       values (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s)""",
                    (relation_case_id or None, oa_row_id, expense_item_id,
                     document["file_object_id"], document["original_filename"],
                     document["content_type"], document["content_sha256"], document["size_bytes"], actor_id),
                )
                active_hashes.add(document["content_sha256"])
            connection.execute(
                """update app.workbench_oa_supporting_document_bundles
                   set total_amount = %s::numeric, invoice_basis = %s::jsonb, version = version + 1,
                       updated_by = %s, updated_at = now()
                   where oa_row_id = %s and expense_item_id = %s""",
                (total_amount, json.dumps(basis), actor_id, oa_row_id, expense_item_id),
            )
            result = self._read_bundle(connection, oa_row_id, expense_item_id)
            PostgresOperationsAuditRepository(connection).append_operation_event({
                "event_type": "workbench.oa_supporting_document_bundle.saved",
                "object_type": "oa_supporting_document_bundle", "object_id": expense_item_id,
                "actor_id": actor_id, "action": "workbench.oa_invoice.document_save",
                "page_key": "reconciliation-workbench", "outcome": "success",
                "payload": {
                    "oa_row_id": oa_row_id, "expense_item_id": expense_item_id,
                    "relation_case_id": relation_case_id,
                    "before": {**bundle, "document_ids": [row["id"] for row in current]},
                    "after": {"total_amount": result["total_amount"], "version": result["version"],
                              "document_ids": [row["id"] for row in result["documents"]]},
                },
            })
            PostgresWorkbenchMatchingQueueRepository(connection).mark_relation_matching_dirty(
                case_ids=[], oa_row_ids=[oa_row_id], reason="oa_supporting_document_changed",
            )
            return {**result, "removed_storage_uris": [row["storage_uri"] for row in removed]}
        return run_in_transaction(self._connection, write)

    def list_active(self, *, oa_row_id: str, expense_item_id: str) -> list[dict[str, Any]]:
        return [dict(row) for row in self._connection.fetch_all(
            """
            select document.id::text as id, document.relation_case_id, document.oa_row_id,
                   document.expense_item_id, document.file_object_id::text as file_object_id,
                   document.original_filename, document.content_type,
                   document.content_sha256, document.size_bytes, document.status,
                   document.created_by, document.created_at::text, file.storage_uri
            from app.workbench_oa_supporting_documents document
            join app.file_objects file on file.id = document.file_object_id
            where document.oa_row_id = %s
              and document.expense_item_id = %s
              and document.status = 'active'
              and file.tombstoned_at is null
            order by document.created_at, document.id
            """,
            (oa_row_id, expense_item_id),
        )]

    def list_active_page(
        self,
        *,
        cursor_created_at: str | None,
        cursor_id: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        cursor_predicate = ""
        params: tuple[Any, ...] = ()
        if cursor_created_at is not None and cursor_id is not None:
            cursor_predicate = (
                "and (document.created_at, document.id) "
                "< (%s::timestamptz, %s::uuid)"
            )
            params = (cursor_created_at, cursor_id)
        return [dict(row) for row in self._connection.fetch_all(
            f"""
            select document.id::text as id, document.relation_case_id, document.oa_row_id,
                   document.expense_item_id, document.original_filename,
                   document.content_type, document.content_sha256, document.size_bytes,
                   document.created_by, document.created_at::text
            from app.workbench_oa_supporting_documents document
            join app.file_objects file on file.id = document.file_object_id
            where document.status = 'active'
              and file.tombstoned_at is null
              {cursor_predicate}
            order by document.created_at desc, document.id desc
            limit %s
            """,
            (*params, limit),
        )]

    def get_active(self, document_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select document.id::text as id, document.relation_case_id, document.oa_row_id,
                   document.expense_item_id, document.file_object_id::text as file_object_id,
                   document.original_filename, document.content_type,
                   document.content_sha256, document.size_bytes, document.status,
                   document.created_by, document.created_at::text, file.storage_uri
            from app.workbench_oa_supporting_documents document
            join app.file_objects file on file.id = document.file_object_id
            where document.id = %s::uuid
              and document.status = 'active'
              and file.tombstoned_at is null
            """,
            (document_id,),
        )
        return dict(row) if row else None
