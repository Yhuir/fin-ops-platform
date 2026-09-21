from __future__ import annotations

import json
import logging
import re
from base64 import b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

from fin_ops_platform.services.untrusted_document_policy import (
    DocumentLimits,
    UntrustedDocumentError,
    inspect_untrusted_document,
    render_document_thumbnail,
)

MAX_SUPPORTING_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_GALLERY_PAGE_SIZE = 9
SUPPORTING_DOCUMENT_THUMBNAIL_EDGE = 360
ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".pdf"}
SUPPORTING_DOCUMENT_LIMITS = DocumentLimits(max_bytes=MAX_SUPPORTING_DOCUMENT_BYTES)


class WorkbenchOaSupportingDocumentError(ValueError):
    def __init__(self, error: str, message: str, *, current_version: int | None = None) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.current_version = current_version


@dataclass(frozen=True, slots=True)
class SupportingDocumentUpload:
    file_name: str
    content: bytes


class WorkbenchOaSupportingDocumentService:
    def __init__(
        self,
        *,
        repository: Any,
        file_store: Any,
        target_exists: Callable[[str, str], bool],
    ) -> None:
        self._repository = repository
        self._file_store = file_store
        self._target_exists = target_exists

    def save(
        self,
        *,
        relation_case_id: str,
        oa_row_id: str,
        expense_item_id: str,
        actor_id: str,
        retained_document_ids: list[str],
        total_amount: str | None,
        expected_version: int,
        uploads: list[SupportingDocumentUpload],
    ) -> dict[str, Any]:
        oa_row_id = str(oa_row_id or "").strip()
        expense_item_id = str(expense_item_id or "").strip()
        actor_id = str(actor_id or "").strip()
        if not oa_row_id or not expense_item_id or not actor_id:
            raise WorkbenchOaSupportingDocumentError(
                "invalid_supporting_document_save", "OA付款项、子付款项和操作人不能为空。",
            )
        if type(expected_version) is not int or expected_version < 0:
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_version_invalid", "请提供有效的凭证组版本。",
            )
        if not isinstance(retained_document_ids, list) or any(
            not isinstance(value, str) or not value.strip() for value in retained_document_ids
        ) or len(set(retained_document_ids)) != len(retained_document_ids):
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_selection_invalid", "保留的凭证文件列表无效或有重复。",
            )
        amount = self._validate_amount(total_amount, has_documents=bool(retained_document_ids or uploads))
        if not self._target_exists(oa_row_id, expense_item_id):
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_target_not_found", "目标 OA 子付款项不存在或已变化，请刷新后重试。",
            )
        validated = [self._validate_upload(upload) for upload in uploads]
        prepared: dict[str, dict[str, Any]] = {}
        try:
            for upload, content_type in validated:
                content_sha256 = sha256(upload.content).hexdigest()
                if content_sha256 in prepared:
                    continue
                stored = self._file_store.store_workbench_oa_supporting_document(
                    document_id=f"oa-support-{uuid4().hex}", file_name=upload.file_name,
                    content=upload.content, content_type=content_type,
                )
                prepared[content_sha256] = {
                    **stored, "original_filename": upload.file_name,
                    "content_type": content_type, "content_sha256": content_sha256,
                }
            result = self._repository.save_bundle(
                relation_case_id=str(relation_case_id or "").strip(),
                oa_row_id=oa_row_id, expense_item_id=expense_item_id, actor_id=actor_id,
                retained_document_ids=retained_document_ids, total_amount=amount,
                expected_version=expected_version, documents=list(prepared.values()),
            )
        except Exception:
            self._cleanup_resources([str(document["storage_uri"]) for document in prepared.values()])
            raise
        used = {str(document["file_object_id"]) for document in result["documents"]}
        self._cleanup_resources([
            str(document["storage_uri"]) for document in prepared.values()
            if str(document["file_object_id"]) not in used
        ] + result.pop("removed_storage_uris", []))
        return self._present_bundle(result)

    def _cleanup_resources(self, storage_uris: list[str]) -> None:
        for storage_uri in storage_uris:
            try:
                self._file_store.delete_workbench_oa_supporting_document(storage_uri)
            except Exception:
                # Canonical publication has completed (or rolled back). A storage cleanup
                # failure must never turn a committed edit into an apparent failed edit.
                logging.getLogger(__name__).exception("Supporting document resource cleanup failed")

    @staticmethod
    def _validate_amount(value: str | None, *, has_documents: bool) -> str | None:
        if not has_documents:
            if value not in (None, ""):
                raise WorkbenchOaSupportingDocumentError(
                    "supporting_document_amount_invalid", "没有补充凭证文件时金额必须为空。",
                )
            return None
        if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,2})?", value):
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_amount_invalid", "请填写非负凭证总金额，最多保留两位小数。",
            )
        return format(Decimal(value), ".2f")

    def list(self, *, oa_row_id: str, expense_item_id: str) -> dict[str, Any]:
        return self._present_bundle(self._repository.get_bundle(
            oa_row_id=str(oa_row_id or "").strip(),
            expense_item_id=str(expense_item_id or "").strip(),
        ))

    def _present_bundle(self, bundle: dict[str, Any]) -> dict[str, Any]:
        return {
            "documents": [self._present(document) for document in bundle["documents"]],
            "total_amount": bundle["total_amount"], "version": bundle["version"],
            "amount_confirmation_required": bundle["amount_confirmation_required"],
        }

    def gallery(self, *, page_size: int = MAX_GALLERY_PAGE_SIZE, cursor: str = "") -> dict[str, Any]:
        if not isinstance(page_size, int) or page_size < 1 or page_size > MAX_GALLERY_PAGE_SIZE:
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_page_size_invalid",
                f"每次只能读取 1 至 {MAX_GALLERY_PAGE_SIZE} 个补充凭证。",
            )
        cursor_created_at, cursor_id = _decode_gallery_cursor(cursor)
        rows = self._repository.list_active_page(
            cursor_created_at=cursor_created_at,
            cursor_id=cursor_id,
            limit=page_size + 1,
        )
        has_more = len(rows) > page_size
        page_rows = rows[:page_size]
        return {
            "documents": [self._present(document) for document in page_rows],
            "page_size": page_size,
            "has_more": has_more,
            "next_cursor": _encode_gallery_cursor(page_rows[-1]) if has_more and page_rows else None,
        }

    def content(self, document_id: str) -> tuple[dict[str, Any], bytes]:
        document = self._repository.get_active(str(document_id or "").strip())
        if document is None:
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_not_found",
                "补充凭证不存在或已删除。",
            )
        content = self._file_store.read_workbench_oa_supporting_document(
            str(document.get("storage_uri") or "")
        )
        return document, content

    def thumbnail(self, document_id: str) -> tuple[dict[str, Any], bytes]:
        document, content = self.content(document_id)
        try:
            validated = inspect_untrusted_document(
                file_name=str(document.get("original_filename") or "document"),
                content=content,
                allowed_kinds=frozenset({"jpeg", "png", "pdf"}),
                limits=SUPPORTING_DOCUMENT_LIMITS,
            )
            thumbnail = render_document_thumbnail(
                document=validated,
                max_edge=SUPPORTING_DOCUMENT_THUMBNAIL_EDGE,
            )
        except (UntrustedDocumentError, OSError, ValueError, RuntimeError):
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_preview_unavailable",
                "补充凭证缩略图暂时无法生成，请打开原文件查看。",
            ) from None
        return document, thumbnail

    @staticmethod
    def _validate_upload(
        upload: SupportingDocumentUpload,
    ) -> tuple[SupportingDocumentUpload, str]:
        file_name = str(upload.file_name or "").strip()
        content = bytes(upload.content or b"")
        suffix = Path(file_name).suffix.lower()
        if suffix not in ALLOWED_SUFFIXES:
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_format_not_allowed",
                "仅支持 JPG、JPEG、PNG 或 PDF 文件。",
            )
        if not content or len(content) > MAX_SUPPORTING_DOCUMENT_BYTES:
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_size_invalid",
                "文件不能为空且单个文件不能超过 25MB。",
            )
        is_pdf = content.startswith(b"%PDF-")
        is_jpeg = content.startswith(b"\xff\xd8\xff")
        is_png = content.startswith(b"\x89PNG\r\n\x1a\n")
        if (
            (suffix == ".pdf" and not is_pdf)
            or (suffix in {".jpg", ".jpeg"} and not is_jpeg)
            or (suffix == ".png" and not is_png)
        ):
            raise WorkbenchOaSupportingDocumentError(
                "supporting_document_signature_invalid",
                "文件内容与扩展名不一致。",
            )
        content_type = "application/pdf" if is_pdf else "image/png" if is_png else "image/jpeg"
        return SupportingDocumentUpload(file_name=file_name, content=content), content_type

    @staticmethod
    def _present(document: dict[str, Any]) -> dict[str, Any]:
        document_id = str(document.get("id") or "")
        return {
            "id": document_id,
            "relation_case_id": document.get("relation_case_id"),
            "oa_row_id": document.get("oa_row_id"),
            "expense_item_id": document.get("expense_item_id"),
            "file_name": document.get("original_filename"),
            "content_type": document.get("content_type"),
            "sha256": document.get("content_sha256"),
            "size_bytes": document.get("size_bytes"),
            "created_by": document.get("created_by"),
            "created_at": document.get("created_at"),
            "content_url": f"/api/workbench/oa-invoice-supplements/documents/{document_id}/content",
            "thumbnail_url": f"/api/workbench/oa-invoice-supplements/documents/{document_id}/thumbnail",
        }


def _encode_gallery_cursor(document: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "created_at": str(document.get("created_at") or ""),
            "id": str(document.get("id") or ""),
            "v": 1,
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_gallery_cursor(cursor: str) -> tuple[str | None, str | None]:
    value = str(cursor or "").strip()
    if not value:
        return None, None
    try:
        if len(value) > 512:
            raise ValueError("cursor too long")
        padding = "=" * (-len(value) % 4)
        raw = b64decode(value + padding, altchars=b"-_", validate=True)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("v") != 1:
            raise ValueError("unsupported cursor")
        created_at = str(payload.get("created_at") or "")
        document_id = str(payload.get("id") or "")
        parsed_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if parsed_at.tzinfo is None:
            raise ValueError("cursor timestamp must include a timezone")
        UUID(document_id)
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        raise WorkbenchOaSupportingDocumentError(
            "supporting_document_cursor_invalid",
            "补充凭证分页位置无效，请重新打开列表。",
        ) from None
    return created_at, document_id
