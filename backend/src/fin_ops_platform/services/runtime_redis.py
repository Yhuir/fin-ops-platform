from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any


class RuntimeRedisConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeRedisSettings:
    url: str | None = None
    key_prefix: str = "finops"
    wakeup_channel: str = "finops:runtime:wakeup"
    default_ttl_seconds: int = 60

    @property
    def enabled(self) -> bool:
        return bool(self.url)

    @classmethod
    def from_env(cls) -> RuntimeRedisSettings:
        url = (os.environ.get("FIN_OPS_REDIS_URL") or os.environ.get("REDIS_URL") or "").strip() or None
        return cls(
            url=url,
            key_prefix=(os.environ.get("FIN_OPS_REDIS_KEY_PREFIX") or "finops").strip() or "finops",
            wakeup_channel=(os.environ.get("FIN_OPS_REDIS_WAKEUP_CHANNEL") or "finops:runtime:wakeup").strip()
            or "finops:runtime:wakeup",
            default_ttl_seconds=_positive_int_from_env("FIN_OPS_REDIS_DEFAULT_TTL_SECONDS", 60),
        )


class RuntimeRedisHelper:
    def __init__(
        self,
        *,
        client: Any | None = None,
        key_prefix: str = "finops",
        wakeup_channel: str = "finops:runtime:wakeup",
    ) -> None:
        self._client = client
        self._key_prefix = key_prefix.strip(":")
        self._wakeup_channel = wakeup_channel
        self._hit_count = 0
        self._miss_count = 0

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @classmethod
    def disabled(cls) -> RuntimeRedisHelper:
        return cls(client=None)

    @classmethod
    def from_settings(cls, settings: RuntimeRedisSettings) -> RuntimeRedisHelper:
        if not settings.enabled:
            return cls.disabled()
        try:
            import redis
        except ImportError as exc:
            raise RuntimeRedisConfigurationError("Redis support requires the optional redis package.") from exc
        return cls(
            client=redis.Redis.from_url(
                settings.url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            ),
            key_prefix=settings.key_prefix,
            wakeup_channel=settings.wakeup_channel,
        )

    def health_summary(self) -> dict[str, Any]:
        if self._client is None:
            return {"redis_status": "disabled"}
        try:
            self._client.ping()
        except Exception as exc:  # pragma: no cover - concrete exception type comes from optional redis package.
            return {
                "redis_status": "error",
                "redis_error": str(exc),
                "redis_hit_count": self._hit_count,
                "redis_miss_count": self._miss_count,
            }
        return {
            "redis_status": "ready",
            "redis_hit_count": self._hit_count,
            "redis_miss_count": self._miss_count,
        }

    def get_json(self, key: str) -> dict[str, Any] | None:
        if self._client is None:
            return None
        raw = self._client.get(self._key(key))
        if raw is None:
            self._miss_count += 1
            return None
        self._hit_count += 1
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(str(raw))
        if not isinstance(payload, dict):
            raise RuntimeRedisConfigurationError(f"Redis key {key!r} does not contain a JSON object.")
        return payload

    def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        if self._client is None:
            return False
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
        return bool(self._client.set(self._key(key), encoded, ex=ttl_seconds))

    def get_text(self, key: str) -> str | None:
        if self._client is None:
            return None
        raw = self._client.get(self._key(key))
        if raw is None:
            self._miss_count += 1
            return None
        self._hit_count += 1
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return str(raw)

    def set_text(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        if self._client is None:
            return False
        return bool(self._client.set(self._key(key), str(value), ex=ttl_seconds))

    def delete(self, key: str) -> bool:
        if self._client is None:
            return False
        return bool(self._client.delete(self._key(key)))

    def publish_wakeup(self, reason: str, payload: dict[str, Any] | None = None) -> bool:
        if self._client is None:
            return False
        message = json.dumps({"reason": reason, "payload": payload or {}}, ensure_ascii=False, sort_keys=True)
        return bool(self._client.publish(self._wakeup_channel, message))

    def acquire_lock(self, name: str, *, owner: str, ttl_seconds: int) -> bool:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive.")
        if self._client is None:
            return False
        return bool(self._client.set(self._key(f"lock:{name}"), owner, ex=ttl_seconds, nx=True))

    def release_lock(self, name: str) -> bool:
        return self.delete(f"lock:{name}")

    def _key(self, key: str) -> str:
        normalized_key = key.strip(":")
        return f"{self._key_prefix}:{normalized_key}" if self._key_prefix else normalized_key


def _positive_int_from_env(name: str, default: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeRedisConfigurationError(f"{name} must be an integer.") from exc
    if value <= 0:
        raise RuntimeRedisConfigurationError(f"{name} must be positive.")
    return value
