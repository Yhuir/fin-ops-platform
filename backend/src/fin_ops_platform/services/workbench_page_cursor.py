from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any


WORKBENCH_PAGE_CURSOR_SCHEMA = "workbench-direct-v1"
WORKBENCH_PAGE_CURSOR_MAX_LENGTH = 2048


class WorkbenchPageCursorError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WorkbenchPageCursor:
    query_hash: str
    sort: str
    missing: bool
    value: str
    group_key: str
    partition: str | None = None


def workbench_query_hash(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def encode_workbench_page_cursor(cursor: WorkbenchPageCursor) -> str:
    unsigned = {
        "v": WORKBENCH_PAGE_CURSOR_SCHEMA,
        "q": cursor.query_hash,
        "s": cursor.sort,
        "m": cursor.missing,
        "k": cursor.value,
        "g": cursor.group_key,
    }
    if cursor.partition is not None:
        unsigned["p"] = cursor.partition
    payload = {**unsigned, "c": _cursor_checksum(unsigned)}
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_workbench_page_cursor(
    value: object,
    *,
    expected_query_hash: str,
    expected_sort: str,
) -> WorkbenchPageCursor | None:
    encoded = str(value or "").strip()
    if not encoded:
        return None
    if len(encoded) > WORKBENCH_PAGE_CURSOR_MAX_LENGTH:
        raise WorkbenchPageCursorError("cursor exceeds the maximum length.")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.b64decode(padded, altchars=b"-_", validate=True))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise WorkbenchPageCursorError("cursor is malformed.") from exc
    if not isinstance(payload, dict):
        raise WorkbenchPageCursorError("cursor is malformed.")
    unsigned = {key: payload.get(key) for key in ("v", "q", "s", "m", "k", "g")}
    if "p" in payload:
        unsigned["p"] = payload.get("p")
    checksum = str(payload.get("c") or "")
    if checksum != _cursor_checksum(unsigned):
        raise WorkbenchPageCursorError("cursor integrity check failed.")
    if unsigned["v"] != WORKBENCH_PAGE_CURSOR_SCHEMA:
        raise WorkbenchPageCursorError("cursor schema is unsupported.")
    if unsigned["q"] != expected_query_hash or unsigned["s"] != expected_sort:
        raise WorkbenchPageCursorError("cursor does not belong to this query.")
    if not isinstance(unsigned["m"], bool):
        raise WorkbenchPageCursorError("cursor sort key is invalid.")
    sort_value = str(unsigned["k"] or "")
    group_key = str(unsigned["g"] or "").strip()
    if len(sort_value) > 128 or not group_key or len(group_key) > 512:
        raise WorkbenchPageCursorError("cursor sort key is invalid.")
    partition = str(unsigned.get("p") or "").strip() or None
    if partition is not None and len(partition) > 128:
        raise WorkbenchPageCursorError("cursor partition is invalid.")
    return WorkbenchPageCursor(
        query_hash=str(unsigned["q"]),
        sort=str(unsigned["s"]),
        missing=unsigned["m"],
        value=sort_value,
        group_key=group_key,
        partition=partition,
    )


def _cursor_checksum(value: dict[str, Any]) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    # The cursor is not an authorization/CAS token. This checksum rejects accidental or
    # stale client mutation while the query hash binds it to one normalized list query.
    return hashlib.sha256(
        f"{WORKBENCH_PAGE_CURSOR_SCHEMA}\0{canonical}".encode("utf-8")
    ).hexdigest()[:32]


__all__ = [
    "WorkbenchPageCursor",
    "WorkbenchPageCursorError",
    "decode_workbench_page_cursor",
    "encode_workbench_page_cursor",
    "workbench_query_hash",
]
