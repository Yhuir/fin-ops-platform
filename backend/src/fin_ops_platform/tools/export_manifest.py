from __future__ import annotations

from dataclasses import MISSING, dataclass, fields, is_dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from bson.binary import Binary


class ExportSerializationError(TypeError):
    pass


@dataclass(frozen=True, slots=True)
class ExportFile:
    path: Path
    record_count: int
    bytes: int
    sha256: str


class NdjsonWriter:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.tmp_path = path.with_suffix(path.suffix + ".tmp")
        self.record_count = 0
        self._handle = self.tmp_path.open("w", encoding="utf-8", newline="\n")

    def write(self, record: dict[str, Any]) -> None:
        payload = safe_jsonable(record, allow_binary_metadata=False)
        if not isinstance(payload, dict):
            raise ExportSerializationError("NDJSON record must serialize to a JSON object.")
        self._handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
        self._handle.write("\n")
        self.record_count += 1

    def close(self) -> ExportFile:
        self._handle.close()
        self.tmp_path.replace(self.path)
        return ExportFile(
            path=self.path,
            record_count=self.record_count,
            bytes=self.path.stat().st_size,
            sha256=sha256_file(self.path),
        )

    def abort(self) -> None:
        self._handle.close()
        self.tmp_path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def binary_metadata(value: bytes | bytearray | Binary) -> dict[str, Any]:
    raw = bytes(value)
    return {"_binary": {"length": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}


def safe_jsonable(value: Any, *, allow_binary_metadata: bool = False) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ExportSerializationError("non-finite float is not allowed in export JSON.")
        return str(Decimal(str(value)))
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return safe_jsonable(value.value, allow_binary_metadata=allow_binary_metadata)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (bytes, bytearray, Binary)):
        if allow_binary_metadata:
            return binary_metadata(value)
        raise ExportSerializationError("binary payload is not allowed directly in export JSON.")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: safe_jsonable(
                _safe_dataclass_field_value(value, field.name),
                allow_binary_metadata=allow_binary_metadata,
            )
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): safe_jsonable(item, allow_binary_metadata=allow_binary_metadata)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [safe_jsonable(item, allow_binary_metadata=allow_binary_metadata) for item in value]
    if value.__class__.__name__ == "ObjectId":
        return str(value)
    raise ExportSerializationError(f"Unsupported export JSON value: {type(value).__name__}")


def _safe_dataclass_field_value(value: Any, field_name: str) -> Any:
    if hasattr(value, field_name):
        return getattr(value, field_name)
    for field in fields(value):
        if field.name != field_name:
            continue
        if field.default is not MISSING:
            return field.default
        if field.default_factory is not MISSING:  # type: ignore[attr-defined]
            return field.default_factory()  # type: ignore[misc]
    return None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(safe_jsonable(payload, allow_binary_metadata=True), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_checksums(path: Path, files: list[ExportFile]) -> None:
    lines = [f"{item.sha256}  {item.path.name}" for item in sorted(files, key=lambda item: item.path.name)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
