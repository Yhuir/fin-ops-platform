from __future__ import annotations

from dataclasses import is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, TypeVar
from uuid import NAMESPACE_URL, uuid5


T = TypeVar("T")


def jsonb(value: Any) -> Any:
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def run_in_transaction(connection: Any, callback: Callable[[Any], T]) -> T:
    transaction_factory = getattr(connection, "transaction", None)
    if callable(transaction_factory):
        with transaction_factory() as transaction:
            return callback(transaction)
    return callback(connection)


def serialize_value(value: Any) -> Any:
    if is_dataclass(value):
        return {key: serialize_value(getattr(value, key, None)) for key in value.__dataclass_fields__}  # type: ignore[attr-defined]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [serialize_value(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, bytes):
        return {"sha256": hashlib.sha256(value).hexdigest(), "size_bytes": len(value)}
    return value


def row_payload(row: dict[str, Any] | None, *columns: str) -> Any:
    if not row:
        return None
    for column in columns:
        value = row.get(column)
        if value is None:
            continue
        if isinstance(value, dict) and "normalized_payload" in value:
            return value.get("normalized_payload") or {}
        return value
    raw_payload = row.get("raw_payload")
    if isinstance(raw_payload, dict):
        return raw_payload.get("normalized_payload") or raw_payload
    return None


def without_keys(value: Any, keys: set[str]) -> Any:
    if isinstance(value, dict):
        return {key: without_keys(item, keys) for key, item in value.items() if str(key) not in keys}
    if isinstance(value, list):
        return [without_keys(item, keys) for item in value]
    return value


def load_keyed_rows(connection: Any, sql: str) -> dict[str, Any]:
    rows = connection.fetch_all(sql)
    return {str(row.get("key")): row_payload(row, "payload", "raw_payload") for row in rows}


def text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode()
    normalized = str(value).strip()
    return normalized or None


def int_value(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def decimal_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return str(Decimal(str(value)))
    except Exception:
        return None


def text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [normalized for item in value if (normalized := text(item))]
    normalized = text(value)
    return [normalized] if normalized else []


def month_start(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().replace(day=1).isoformat()
    if isinstance(value, date):
        return value.replace(day=1).isoformat()
    normalized = str(value).strip()
    if not normalized:
        return None
    if len(normalized) >= 7 and normalized[4] == "-" and normalized[5:7].isdigit():
        return f"{normalized[:7]}-01"
    if len(normalized) >= 6 and normalized[:6].isdigit():
        return f"{normalized[:4]}-{normalized[4:6]}-01"
    return None


def iter_mapping(value: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return []
    pairs: list[tuple[str, dict[str, Any]]] = []
    for key, raw_payload in value.items():
        payload = serialize_value(raw_payload)
        if not isinstance(payload, dict):
            continue
        item_key = text(payload.get("id") or key)
        if item_key:
            pairs.append((item_key, payload))
    return pairs


def max_numeric_suffix(values: dict[str, Any]) -> int:
    maximum = 0
    for key in values:
        match = re.search(r"(\d+)$", str(key))
        if match:
            maximum = max(maximum, int(match.group(1)))
    return maximum


def event_uuid(namespace: str, entity_id: str, payload: dict[str, Any]) -> str:
    operation_id = text(payload.get("operation_id") or payload.get("event_id"))
    if operation_id:
        seed = f"{namespace}:{entity_id}:{operation_id}"
    else:
        seed = f"{namespace}:{entity_id}:{json.dumps(serialize_value(payload), ensure_ascii=False, sort_keys=True, default=str)}"
    return str(uuid5(NAMESPACE_URL, seed))
