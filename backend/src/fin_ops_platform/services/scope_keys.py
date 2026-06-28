from __future__ import annotations

from typing import Any


def normalized_scope_keys(scope_keys: Any, *, fallback: str | None = None) -> list[str]:
    result: list[str] = []
    if isinstance(scope_keys, str):
        candidates = [scope_keys]
    elif isinstance(scope_keys, list | tuple | set):
        candidates = list(scope_keys)
    else:
        candidates = []
    for scope_key in candidates:
        text = str(scope_key or "").strip()
        if text and text not in result:
            result.append(text)
    if not result and fallback:
        result.append(fallback)
    return result
