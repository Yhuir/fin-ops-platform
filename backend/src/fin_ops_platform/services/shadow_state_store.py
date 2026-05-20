from __future__ import annotations

from pathlib import Path
import random
from typing import Any, Callable

from fin_ops_platform.services.state_store_diff import StateStoreDiffResult, diff_state_snapshots, redact_diff_payload


class ShadowStateStore:
    def __init__(
        self,
        *,
        primary: Any,
        shadow: Any,
        compare_enabled: bool = False,
        compare_sample_rate: float = 1.0,
        ignored_paths: set[str] | list[str] | tuple[str, ...] | None = None,
        max_mismatches: int = 20,
        sample_decider: Callable[[], float] | None = None,
    ) -> None:
        self._primary = primary
        self._shadow = shadow
        self._compare_enabled = compare_enabled
        if compare_sample_rate < 0.0 or compare_sample_rate > 1.0:
            raise ValueError("compare_sample_rate must be between 0.0 and 1.0.")
        self._compare_sample_rate = compare_sample_rate
        self._sample_decider = sample_decider or random.random
        self._ignored_paths = tuple(ignored_paths or ())
        self._max_mismatches = max_mismatches
        self._compared = 0
        self._matched = 0
        self._mismatched = 0
        self._shadow_errors = 0
        self._last_mismatch: dict[str, object] | None = None
        self._last_error: str | None = None

    @property
    def data_dir(self) -> Path:
        return self._primary.data_dir

    @property
    def storage_backend(self) -> str:
        primary_backend = getattr(self._primary, "storage_backend", "primary")
        shadow_backend = getattr(self._shadow, "storage_backend", "shadow")
        return f"shadow:{primary_backend}->{shadow_backend}"

    @property
    def storage_mode(self) -> str:
        return "shadow"

    @property
    def mongo_database_name(self) -> str | None:
        return getattr(self._primary, "mongo_database_name", None)

    def shadow_summary(self) -> dict[str, object]:
        return {
            "compared": self._compared,
            "matched": self._matched,
            "mismatched": self._mismatched,
            "shadow_errors": self._shadow_errors,
            "last_mismatch": self._last_mismatch,
            "last_error": self._last_error,
        }

    def __getattr__(self, name: str) -> Any:
        primary_attr = getattr(self._primary, name)
        if not callable(primary_attr):
            return primary_attr

        def delegated(*args: Any, **kwargs: Any) -> Any:
            primary_result = primary_attr(*args, **kwargs)
            if self._should_compare(name):
                self._compare_shadow(name, args, kwargs, primary_result)
            return primary_result

        return delegated

    def _should_compare(self, method_name: str) -> bool:
        return (
            self._compare_enabled
            and _is_read_method(method_name)
            and self._compare_sample_rate > 0.0
            and self._sample_decider() <= self._compare_sample_rate
        )

    def _compare_shadow(
        self,
        method_name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        primary_result: Any,
    ) -> None:
        try:
            shadow_method: Callable[..., Any] = getattr(self._shadow, method_name)
            shadow_result = shadow_method(*args, **kwargs)
            result = diff_state_snapshots(
                primary_result,
                shadow_result,
                domain=method_name,
                ignored_paths=self._ignored_paths,
                max_mismatches=self._max_mismatches,
            )
        except Exception as exc:  # noqa: BLE001 - shadow reads are explicitly best-effort.
            self._shadow_errors += 1
            self._last_error = str(redact_diff_payload(str(exc)))
            return

        self._record_diff(result)

    def _record_diff(self, result: StateStoreDiffResult) -> None:
        self._compared += 1
        if result.matched:
            self._matched += 1
            return
        self._mismatched += 1
        self._last_mismatch = result.to_dict()


def _is_read_method(name: str) -> bool:
    if name in {"load", "health_summary"}:
        return name == "load"
    return name.startswith("load_") or name.startswith("read_") or name.endswith("_exists")
