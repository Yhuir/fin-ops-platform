from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import (
    normalize_source_versions,
    resolve_read_model_freshness,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway


@dataclass(frozen=True)
class ReadModelQueryResult:
    payload: dict[str, Any]
    cache_hit: bool = False
    refresh_enqueued: bool = False
    freshness_status: str = "fresh"
    stale_reasons: tuple[str, ...] = ()


class ReadModelQueryGateway:
    """Coordinates read-model freshness, Redis cache use, and refresh enqueueing.

    This service deliberately has no dependency on Flask, Application, or SQL
    table details. Callers provide the repository loader and payload shaper.
    """

    def __init__(self, *, queue_repository: Any | None = None, redis_helper: Any | None = None) -> None:
        self._queue_repository = queue_repository
        self._refresh_gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        self._redis_helper = redis_helper

    def load(
        self,
        *,
        scope_type: str,
        scope_key: str,
        load_view: Callable[[], dict[str, Any] | None],
        empty_payload_factory: Callable[[], dict[str, Any]],
        expected_source_versions: dict[str, Any] | None = None,
        expected_schema_version: Any | None = None,
        payload_from_view: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        cache_key: str | None = None,
        cache_ttl_seconds: int | None = None,
        missing_reason: str = "api_miss",
        stale_reason: str = "api_stale",
        source_mismatch_reason: str = "api_source_versions_stale",
    ) -> ReadModelQueryResult:
        expected_versions = normalize_source_versions(expected_source_versions)
        cached_payload = self._get_cached_payload(
            cache_key,
            scope_key=scope_key,
            expected_source_versions=expected_versions,
            expected_schema_version=expected_schema_version,
        )
        if cached_payload is not None:
            payload = dict(cached_payload)
            self._attach_payload_metadata(
                payload,
                scope_key=scope_key,
                status="fresh",
                source_versions=expected_versions,
            )
            payload["refresh_enqueued"] = False
            return ReadModelQueryResult(payload=payload, cache_hit=True)

        view = load_view()
        if not isinstance(view, dict):
            refresh_enqueued = self._enqueue_refresh(
                scope_type=scope_type,
                scope_key=scope_key,
                reason=missing_reason,
            )
            payload = dict(empty_payload_factory())
            self._attach_payload_metadata(
                payload,
                scope_key=scope_key,
                status="refreshing",
                source_versions=expected_versions,
            )
            payload["refresh_enqueued"] = refresh_enqueued
            payload["refresh_reason"] = missing_reason
            return ReadModelQueryResult(
                payload=payload,
                refresh_enqueued=refresh_enqueued,
                freshness_status="missing",
            )

        raw_payload = payload_from_view(view) if payload_from_view is not None else _default_payload_from_view(view)
        payload = dict(raw_payload)
        actual_source_versions = view.get("source_versions") if isinstance(view.get("source_versions"), dict) else {}
        freshness = resolve_read_model_freshness(
            expected_schema_version=expected_schema_version,
            actual_schema_version=view.get("schema_version"),
            expected_source_versions=expected_versions,
            actual_source_versions=actual_source_versions,
            dirty_status=str(view.get("refresh_status") or "fresh"),
        )
        public_status = "fresh" if freshness.status == "fresh" else "refreshing"
        refresh_enqueued = False
        refresh_reason = ""
        if freshness.status != "fresh":
            refresh_reason = (
                source_mismatch_reason
                if any(reason.endswith("_missing") or reason.endswith("_mismatch") for reason in freshness.stale_reasons)
                else stale_reason
            )
            refresh_enqueued = self._enqueue_refresh(
                scope_type=scope_type,
                scope_key=scope_key,
                reason=refresh_reason,
            )
        self._attach_payload_metadata(
            payload,
            scope_key=scope_key,
            status=public_status,
            source_versions=normalize_source_versions(actual_source_versions),
            stale_reasons=freshness.stale_reasons,
            generated_at=view.get("generated_at"),
            schema_version=view.get("schema_version"),
        )
        if freshness.status != "fresh":
            payload["refresh_enqueued"] = refresh_enqueued
            payload["refresh_reason"] = "source_version_mismatch" if refresh_reason == source_mismatch_reason else refresh_reason
        elif cache_key and cache_ttl_seconds:
            payload["refresh_enqueued"] = False
            self._set_cached_payload(
                cache_key,
                payload,
                ttl_seconds=cache_ttl_seconds,
                scope_key=scope_key,
                source_versions=actual_source_versions,
                schema_version=expected_schema_version or view.get("schema_version"),
            )
        else:
            payload["refresh_enqueued"] = False
        return ReadModelQueryResult(
            payload=payload,
            cache_hit=False,
            refresh_enqueued=refresh_enqueued,
            freshness_status=freshness.status,
            stale_reasons=freshness.stale_reasons,
        )

    def _enqueue_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> bool:
        if not self._refresh_gateway.can_enqueue():
            return False
        return bool(self._refresh_gateway.enqueue_many(scope_type, [scope_key], reason=reason))

    def _get_cached_payload(
        self,
        cache_key: str | None,
        *,
        scope_key: str,
        expected_source_versions: dict[str, Any],
        expected_schema_version: Any | None,
    ) -> dict[str, Any] | None:
        if not cache_key:
            return None
        get_json = getattr(self._redis_helper, "get_json", None)
        if not callable(get_json):
            return None
        try:
            cached = get_json(cache_key)
        except Exception:
            return None
        if not isinstance(cached, dict):
            return None
        payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else cached
        if not isinstance(payload, dict):
            return None
        if not _cached_payload_passes_fresh_gate(
            cached,
            payload,
            scope_key=scope_key,
            expected_source_versions=expected_source_versions,
            expected_schema_version=expected_schema_version,
        ):
            return None
        return dict(payload)

    def _set_cached_payload(
        self,
        cache_key: str,
        payload: dict[str, Any],
        *,
        ttl_seconds: int,
        scope_key: str,
        source_versions: dict[str, Any] | None,
        schema_version: Any | None,
    ) -> None:
        set_json = getattr(self._redis_helper, "set_json", None)
        if not callable(set_json):
            return
        try:
            set_json(
                cache_key,
                build_fresh_cache_envelope(
                    payload,
                    scope_key=scope_key,
                    source_versions=source_versions,
                    schema_version=schema_version,
                ),
                ttl_seconds=ttl_seconds,
            )
        except Exception:
            return

    @staticmethod
    def _attach_payload_metadata(
        payload: dict[str, Any],
        *,
        scope_key: str,
        status: str,
        source_versions: dict[str, Any] | None,
        stale_reasons: tuple[str, ...] = (),
        generated_at: Any | None = None,
        schema_version: Any | None = None,
    ) -> None:
        payload["read_model_status"] = status
        payload["read_model_scope_key"] = scope_key
        payload["source_versions"] = normalize_source_versions(source_versions)
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        if generated_at:
            payload["read_model_generated_at"] = generated_at
        if schema_version:
            payload["read_model_schema_version"] = schema_version


def _default_payload_from_view(view: dict[str, Any]) -> dict[str, Any]:
    payload = view.get("payload")
    return dict(payload) if isinstance(payload, dict) else {}


def build_fresh_cache_envelope(
    payload: dict[str, Any],
    *,
    scope_key: str,
    source_versions: dict[str, Any] | None,
    schema_version: Any | None = None,
) -> dict[str, Any]:
    return {
        "payload": payload,
        "fresh_gate": {
            "scope_key": scope_key,
            "read_model_status": "fresh",
            "schema_version": str(schema_version) if schema_version not in (None, "") else "",
            "source_versions": normalize_source_versions(source_versions),
        },
    }


def _cached_payload_passes_fresh_gate(
    cached: dict[str, Any],
    payload: dict[str, Any],
    *,
    scope_key: str,
    expected_source_versions: dict[str, Any],
    expected_schema_version: Any | None,
) -> bool:
    gate = cached.get("fresh_gate") if isinstance(cached.get("fresh_gate"), dict) else {}
    status = str(gate.get("read_model_status") or payload.get("read_model_status") or "fresh").strip().lower()
    if status != "fresh":
        return False

    cached_scope_key = str(
        gate.get("scope_key") or payload.get("read_model_scope_key") or payload.get("scope_key") or ""
    ).strip()
    if cached_scope_key and cached_scope_key != str(scope_key):
        return False

    actual_source_versions = (
        gate.get("source_versions") if isinstance(gate.get("source_versions"), dict) else payload.get("source_versions")
    )
    if source_version_mismatch_reasons(
        expected=expected_source_versions,
        actual=actual_source_versions if isinstance(actual_source_versions, dict) else {},
    ):
        return False

    expected_schema = str(expected_schema_version or "").strip()
    if not expected_schema:
        return True
    actual_schema = str(
        gate.get("schema_version") or payload.get("read_model_schema_version") or payload.get("schema_version") or ""
    ).strip()
    return not actual_schema or actual_schema == expected_schema


class ReadModelRefreshQueueAdapter:
    def __init__(self, *, scope_type: str, refresh_enqueuer: Callable[..., bool]) -> None:
        self._scope_type = scope_type
        self._refresh_enqueuer = refresh_enqueuer

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        if scope_type != self._scope_type:
            raise ValueError(f"Unexpected read model scope type: {scope_type}")
        self._refresh_enqueuer(scope_key, reason=reason)


class ReadModelRedisBestEffortAdapter:
    def __init__(
        self,
        *,
        get_json: Callable[[str], dict[str, Any] | None],
        set_json: Callable[..., bool],
    ) -> None:
        self._get_json = get_json
        self._set_json = set_json

    def get_json(self, key: str) -> dict[str, Any] | None:
        return self._get_json(key)

    def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> bool:
        return self._set_json(key, value, ttl_seconds=ttl_seconds)
