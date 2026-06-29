from __future__ import annotations

import re
from typing import Any
from urllib.parse import ParseResult, urlparse, urlunparse


SECRET_KEY_PARTS = ("password", "passwd", "secret", "token", "credential", "database_url", "uri", "url")


def redact_secret_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _redact_by_key(key, item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_secret_values(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_secret_values(item) for item in value)
    if isinstance(value, str):
        return redact_uri(value)
    return value


def redact_uri(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return value
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    username = parsed.username or ""
    credentials = f"{username}:***@" if username else ""
    return urlunparse(
        ParseResult(
            scheme=parsed.scheme,
            netloc=f"{credentials}{host}{port}",
            path=parsed.path,
            params="",
            query="",
            fragment="",
        )
    )


def redact_secret_text(value: str) -> str:
    return re.sub(r"[a-z][a-z0-9+.-]*://[^\s'\"<>]+", lambda match: redact_uri(match.group(0)), value)


def _redact_by_key(key: str, value: Any) -> Any:
    lowered = key.lower()
    if lowered.endswith("_env"):
        return redact_secret_values(value)
    if any(part in lowered for part in SECRET_KEY_PARTS):
        if isinstance(value, str):
            redacted_uri = redact_uri(value)
            if "***" in value:
                return value
            return redacted_uri if redacted_uri != value else "<redacted>"
        return "<redacted>"
    return redact_secret_values(value)
