from __future__ import annotations

from typing import Any, Callable


class BankDetailReadModelRefreshProducer:
    def __init__(
        self,
        *,
        refresh_gateway_provider: Callable[[], Any],
        redis_helper_provider: Callable[[], Any | None] | None = None,
    ) -> None:
        self._refresh_gateway_provider = refresh_gateway_provider
        self._redis_helper_provider = redis_helper_provider or (lambda: None)

    def enqueue(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        refresh_gateway = self._refresh_gateway_provider()
        if not refresh_gateway.can_enqueue():
            return False
        target_scope_keys = [str(item).strip() for item in list(scope_keys or []) if str(item).strip()]
        for scope_key in target_scope_keys:
            self._publish_wakeup(scope_key)
        return bool(refresh_gateway.enqueue_many("bank_detail", target_scope_keys, reason=reason, metadata=metadata))

    def _publish_wakeup(self, scope_key: str) -> None:
        redis_helper = self._redis_helper_provider()
        publish_wakeup = getattr(redis_helper, "publish_wakeup", None)
        if callable(publish_wakeup):
            try:
                publish_wakeup("bank_detail_read_model_refresh", {"scope_key": scope_key})
            except Exception:
                pass
