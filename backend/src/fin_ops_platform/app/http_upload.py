from __future__ import annotations

import os
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser

from fin_ops_platform.services.import_file_service import UploadedImportFile


@dataclass(frozen=True)
class MultipartLimits:
    max_parts: int = 128
    max_files: int = 64
    max_file_bytes: int = 120 * 1024 * 1024
    max_field_bytes: int = 256 * 1024

    @classmethod
    def from_env(cls) -> MultipartLimits:
        return cls(
            max_parts=_positive_int_env("FIN_OPS_MULTIPART_MAX_PARTS", cls.max_parts),
            max_files=_positive_int_env("FIN_OPS_MULTIPART_MAX_FILES", cls.max_files),
            max_file_bytes=_positive_int_env("FIN_OPS_UPLOAD_FILE_MAX_BYTES", cls.max_file_bytes),
            max_field_bytes=_positive_int_env("FIN_OPS_MULTIPART_FIELD_MAX_BYTES", cls.max_field_bytes),
        )


class MultipartBodyError(ValueError):
    def __init__(self, error: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code


def parse_multipart_body(
    body: bytes,
    content_type: str,
    *,
    limits: MultipartLimits | None = None,
) -> tuple[dict[str, list[str]], list[UploadedImportFile]]:
    if not body:
        raise MultipartBodyError("invalid_multipart_body", "Multipart body is required.")
    if "multipart/form-data" not in str(content_type or "").lower():
        raise MultipartBodyError("invalid_multipart_body", "Content-Type must be multipart/form-data.")
    resolved_limits = limits or MultipartLimits.from_env()
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    )
    if not message.is_multipart() or not message.get_boundary():
        raise MultipartBodyError("invalid_multipart_body", "Multipart boundary is missing or invalid.")

    parts = [part for part in message.walk() if not part.is_multipart()]
    if len(parts) > resolved_limits.max_parts:
        raise MultipartBodyError("multipart_too_many_parts", "Multipart part count exceeds the configured limit.", status_code=413)

    fields: dict[str, list[str]] = {}
    files: list[UploadedImportFile] = []
    for part in parts:
        if part.get_content_disposition() != "form-data":
            continue
        name = str(part.get_param("name", header="content-disposition") or "").strip()
        if not name:
            raise MultipartBodyError("invalid_multipart_body", "Multipart part name is required.")
        content = part.get_payload(decode=True) or b""
        filename = part.get_filename()
        if filename is not None:
            if len(files) >= resolved_limits.max_files:
                raise MultipartBodyError("multipart_too_many_files", "Uploaded file count exceeds the configured limit.", status_code=413)
            if len(content) > resolved_limits.max_file_bytes:
                raise MultipartBodyError("upload_file_too_large", "Uploaded file exceeds the configured size limit.", status_code=413)
            files.append(UploadedImportFile(file_name=str(filename), content=content))
            continue
        if len(content) > resolved_limits.max_field_bytes:
            raise MultipartBodyError("multipart_field_too_large", "Multipart field exceeds the configured size limit.", status_code=413)
        charset = part.get_content_charset() or "utf-8"
        try:
            value = content.decode(charset).strip()
        except (LookupError, UnicodeDecodeError) as exc:
            raise MultipartBodyError("invalid_multipart_field", "Multipart text field encoding is invalid.") from exc
        fields.setdefault(name, []).append(value)
    return fields, files


def _positive_int_env(name: str, default: int) -> int:
    raw = str(os.environ.get(name) or "").strip()
    if not raw:
        return int(default)
    try:
        value = int(raw)
    except ValueError as exc:
        raise MultipartBodyError("invalid_multipart_configuration", f"{name} must be an integer.", status_code=500) from exc
    if value <= 0:
        raise MultipartBodyError("invalid_multipart_configuration", f"{name} must be positive.", status_code=500)
    return value
