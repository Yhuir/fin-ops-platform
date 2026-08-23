from __future__ import annotations

from typing import Any


class PostgresWorkbenchOaSupportingDocumentRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def create(
        self,
        *,
        relation_case_id: str,
        oa_row_id: str,
        expense_item_id: str,
        file_object_id: str,
        original_filename: str,
        content_type: str,
        content_sha256: str,
        size_bytes: int,
        created_by: str,
    ) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            insert into app.workbench_oa_supporting_documents(
                relation_case_id, oa_row_id, expense_item_id, file_object_id,
                original_filename, content_type, content_sha256, size_bytes, created_by
            )
            values (%s, %s, %s, %s::uuid, %s, %s, %s, %s, %s)
            on conflict (oa_row_id, expense_item_id, content_sha256)
                where status = 'active'
                do nothing
            returning id::text as id, relation_case_id, oa_row_id, expense_item_id,
                      file_object_id::text as file_object_id, original_filename,
                      content_type, content_sha256, size_bytes, status, created_by,
                      created_at::text
            """,
            (
                relation_case_id or None, oa_row_id, expense_item_id, file_object_id,
                original_filename, content_type, content_sha256, size_bytes, created_by,
            ),
        )
        return dict(row) if row else None

    def find_active_by_content(
        self,
        *,
        oa_row_id: str,
        expense_item_id: str,
        content_sha256: str,
    ) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
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
              and document.content_sha256 = %s
              and document.status = 'active'
              and file.tombstoned_at is null
            limit 1
            """,
            (oa_row_id, expense_item_id, content_sha256),
        )
        return dict(row) if row else None

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

    def soft_delete(self, document_id: str, *, deleted_by: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            update app.workbench_oa_supporting_documents
               set status = 'deleted', deleted_by = %s, deleted_at = now()
             where id = %s::uuid and status = 'active'
            returning id::text as id, file_object_id::text as file_object_id
            """,
            (deleted_by, document_id),
        )
        return dict(row) if row else None
