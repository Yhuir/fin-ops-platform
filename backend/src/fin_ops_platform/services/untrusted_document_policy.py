from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
import warnings
from zipfile import BadZipFile, ZipFile, is_zipfile

import fitz
from PIL import Image, ImageOps, UnidentifiedImageError


@dataclass(frozen=True)
class DocumentLimits:
    max_bytes: int
    max_image_dimension: int = 20_000
    max_image_pixels: int = 40_000_000
    max_pdf_pages: int = 100
    max_pdf_render_pixels: int = 200_000_000
    max_archive_entries: int = 512
    max_archive_entry_bytes: int = 20 * 1024 * 1024
    max_archive_uncompressed_bytes: int = 100 * 1024 * 1024
    max_archive_compression_ratio: int = 200


ETC_DOCUMENT_LIMITS = DocumentLimits(max_bytes=64 * 1024 * 1024, max_pdf_pages=120)
OA_ATTACHMENT_LIMITS = DocumentLimits(max_bytes=20 * 1024 * 1024)


@dataclass(frozen=True)
class ValidatedDocument:
    file_name: str
    kind: str
    content: bytes
    content_type: str
    content_sha256: str
    ocr_content: bytes | None = None
    pdf_page_count: int = 0


class UntrustedDocumentError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


_SUFFIX_KIND = {
    ".docx": "docx",
    ".jpeg": "jpeg",
    ".jpg": "jpeg",
    ".pdf": "pdf",
    ".png": "png",
    ".text": "text",
    ".txt": "text",
}
_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "jpeg": "image/jpeg",
    "pdf": "application/pdf",
    "png": "image/png",
    "text": "text/plain",
}


def inspect_untrusted_document(
    *,
    file_name: str,
    content: bytes,
    allowed_kinds: frozenset[str],
    limits: DocumentLimits,
) -> ValidatedDocument:
    if not isinstance(content, bytes) or not content:
        raise UntrustedDocumentError("document_empty")
    if len(content) > limits.max_bytes:
        raise UntrustedDocumentError("document_too_large")

    declared_kind = _SUFFIX_KIND.get(Path(file_name).suffix.lower())
    if declared_kind is None or declared_kind not in allowed_kinds:
        raise UntrustedDocumentError("document_format_not_allowed")
    detected_kind = _detect_kind(content, declared_kind)
    if detected_kind != declared_kind:
        raise UntrustedDocumentError("document_signature_mismatch")

    ocr_content: bytes | None = None
    pdf_page_count = 0
    if detected_kind in {"jpeg", "png"}:
        ocr_content = normalize_image_for_ocr(content=content, limits=limits)
    elif detected_kind == "pdf":
        pdf_page_count = _validate_pdf(content=content, limits=limits)
    elif detected_kind == "docx":
        _validate_docx(content=content, limits=limits)

    return ValidatedDocument(
        file_name=file_name,
        kind=detected_kind,
        content=content,
        content_type=_CONTENT_TYPES[detected_kind],
        content_sha256=sha256(content).hexdigest(),
        ocr_content=ocr_content,
        pdf_page_count=pdf_page_count,
    )


def normalize_image_for_ocr(*, content: bytes, limits: DocumentLimits) -> bytes:
    detected_kind = _detect_image_kind(content)
    if detected_kind is None:
        raise UntrustedDocumentError("document_image_signature_invalid")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content), formats=("JPEG", "PNG")) as image:
                if getattr(image, "n_frames", 1) != 1:
                    raise UntrustedDocumentError("document_image_multiframe")
                width, height = image.size
                _validate_image_size(width=width, height=height, limits=limits)
                image.load()
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                if max(width, height) < 1600:
                    width *= 2
                    height *= 2
                    _validate_image_size(width=width, height=height, limits=limits)
                    normalized = normalized.resize((width, height))
                output = BytesIO()
                ImageOps.autocontrast(ImageOps.grayscale(normalized)).save(output, format="PNG")
                return output.getvalue()
    except UntrustedDocumentError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UntrustedDocumentError("document_image_too_large") from None
    except (OSError, UnidentifiedImageError, ValueError):
        raise UntrustedDocumentError("document_image_invalid") from None


def _detect_kind(content: bytes, declared_kind: str) -> str:
    image_kind = _detect_image_kind(content)
    if image_kind is not None:
        return image_kind
    if content.startswith(b"%PDF-"):
        return "pdf"
    if is_zipfile(BytesIO(content)):
        return "docx"
    if declared_kind == "text" and _is_text(content):
        return "text"
    raise UntrustedDocumentError("document_signature_invalid")


def _detect_image_kind(content: bytes) -> str | None:
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if content.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    return None


def _is_text(content: bytes) -> bool:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            value = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        return "\x00" not in value and bool(value.strip())
    return False


def _validate_image_size(*, width: int, height: int, limits: DocumentLimits) -> None:
    if width <= 0 or height <= 0:
        raise UntrustedDocumentError("document_image_invalid")
    if max(width, height) > limits.max_image_dimension or width * height > limits.max_image_pixels:
        raise UntrustedDocumentError("document_image_too_large")


def _validate_pdf(*, content: bytes, limits: DocumentLimits) -> int:
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except Exception:
        raise UntrustedDocumentError("document_pdf_invalid") from None
    try:
        page_count = int(document.page_count)
        if page_count <= 0:
            raise UntrustedDocumentError("document_pdf_empty")
        if page_count > limits.max_pdf_pages:
            raise UntrustedDocumentError("document_pdf_too_many_pages")
        render_pixels = 0
        for page in document:
            width = float(page.rect.width)
            height = float(page.rect.height)
            if width <= 0 or height <= 0:
                raise UntrustedDocumentError("document_pdf_invalid")
            render_pixels += int(width * height * 9)
            if render_pixels > limits.max_pdf_render_pixels:
                raise UntrustedDocumentError("document_pdf_render_too_large")
        return page_count
    finally:
        document.close()


def _validate_docx(*, content: bytes, limits: DocumentLimits) -> None:
    try:
        with ZipFile(BytesIO(content)) as document:
            entries = document.infolist()
            if len(entries) > limits.max_archive_entries:
                raise UntrustedDocumentError("document_archive_too_many_entries")
            total_size = 0
            names: set[str] = set()
            for entry in entries:
                normalized_name = PurePosixPath(entry.filename)
                if normalized_name.is_absolute() or ".." in normalized_name.parts or entry.flag_bits & 0x1:
                    raise UntrustedDocumentError("document_archive_invalid")
                if entry.file_size > limits.max_archive_entry_bytes:
                    raise UntrustedDocumentError("document_archive_entry_too_large")
                if entry.file_size and (
                    entry.compress_size == 0
                    or entry.file_size / entry.compress_size > limits.max_archive_compression_ratio
                ):
                    raise UntrustedDocumentError("document_archive_compression_ratio")
                total_size += entry.file_size
                if total_size > limits.max_archive_uncompressed_bytes:
                    raise UntrustedDocumentError("document_archive_too_large")
                names.add(entry.filename)
            if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                raise UntrustedDocumentError("document_docx_invalid")
    except UntrustedDocumentError:
        raise
    except (BadZipFile, OSError, ValueError):
        raise UntrustedDocumentError("document_docx_invalid") from None
