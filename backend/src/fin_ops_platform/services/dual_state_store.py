from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import uuid4
import re


WRITE_METHODS = frozenset(
    {
        "save",
        "save_app_settings",
        "save_pending_invoice_commands",
        "save_tax_certified_imports",
        "save_etc_state",
        "save_etc_reconciliation_state",
        "save_workbench_pair_relations",
        "save_no_oa_bank_batches",
        "save_bank_transaction_categories",
        "save_turnover_relations",
        "save_workbench_read_models",
        "save_workbench_candidate_matches",
        "save_cost_statistics_read_models",
        "save_tax_offset_read_models",
        "save_background_jobs",
        "save_app_health_alerts",
    }
)

PRIMARY_ONLY_FILE_WRITE_METHODS = frozenset(
    {
        "store_import_file",
        "store_etc_invoice_file",
        "store_etc_reconciliation_file",
        "save_historical_etc_repair_bundle",
    }
)

_URI_RE = re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s'\"<>]+", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|token|secret|authorization|cookie)=([^&\s'\"<>]+)"
)


class DualWriteMirrorError(RuntimeError):
    """Raised when strict dual-write mode cannot persist to the mirror store."""


class DualStateStore:
    def __init__(
        self,
        primary_store: Any | None = None,
        mirror_store: Any | None = None,
        *,
        primary: Any | None = None,
        mirror: Any | None = None,
        strict: bool = False,
        logger: Any | None = None,
        callback: Callable[[dict[str, Any]], None] | None = None,
        operation_id_factory: Callable[[], str] | None = None,
    ) -> None:
        resolved_primary = primary_store if primary_store is not None else primary
        resolved_mirror = mirror_store if mirror_store is not None else mirror
        if resolved_primary is None or resolved_mirror is None:
            raise ValueError("DualStateStore requires both primary and mirror stores.")
        self._primary_store = resolved_primary
        self._mirror_store = resolved_mirror
        self.primary_store = resolved_primary
        self.mirror_store = resolved_mirror
        self._strict = strict
        self._logger = logger
        self._callback = callback
        self._operation_id_factory = operation_id_factory or (lambda: uuid4().hex)
        self._summary: dict[str, Any] = {
            "primary_success": 0,
            "primary_failed": 0,
            "mirror_success": 0,
            "mirror_failed": 0,
            "strict_failures": 0,
            "last_failure": None,
            "primary_only": 0,
            "primary_only_methods": [],
        }

    @property
    def data_dir(self) -> Any:
        return self._primary_store.data_dir

    @property
    def storage_backend(self) -> str:
        return "dual"

    @property
    def storage_mode(self) -> str:
        return "dual"

    @property
    def mongo_database_name(self) -> str | None:
        return self._primary_store.mongo_database_name

    def dual_write_summary(self) -> dict[str, Any]:
        return {
            **self._summary,
            "primary_only_methods": list(self._summary["primary_only_methods"]),
        }

    def __getattr__(self, name: str) -> Any:
        primary_attr = getattr(self._primary_store, name)
        if name in WRITE_METHODS:
            return self._dual_write_method(name, primary_attr)
        if name in PRIMARY_ONLY_FILE_WRITE_METHODS:
            return self._primary_only_method(name, primary_attr)
        return primary_attr

    def _dual_write_method(self, method_name: str, primary_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            operation_id = self._new_operation_id()
            try:
                result = primary_method(*args, **kwargs)
            except Exception as exc:
                self._summary["primary_failed"] += 1
                self._record_failure(
                    operation_id=operation_id,
                    method_name=method_name,
                    stage="primary",
                    error=exc,
                    strict=False,
                )
                raise

            self._summary["primary_success"] += 1
            try:
                getattr(self._mirror_store, method_name)(*args, **kwargs)
            except Exception as exc:
                self._summary["mirror_failed"] += 1
                failure = self._record_failure(
                    operation_id=operation_id,
                    method_name=method_name,
                    stage="mirror",
                    error=exc,
                    strict=self._strict,
                )
                if self._strict:
                    self._summary["strict_failures"] += 1
                    raise DualWriteMirrorError(
                        f"Dual write mirror failed for {method_name} "
                        f"(operation_id={operation_id}): {failure['error']}"
                    ) from exc
                return result

            self._summary["mirror_success"] += 1
            self._emit(
                {
                    "operation_id": operation_id,
                    "method": method_name,
                    "status": "mirror_success",
                }
            )
            return result

        return wrapped

    def _primary_only_method(self, method_name: str, primary_method: Callable[..., Any]) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            operation_id = self._new_operation_id()
            try:
                result = primary_method(*args, **kwargs)
            except Exception as exc:
                self._summary["primary_failed"] += 1
                self._record_failure(
                    operation_id=operation_id,
                    method_name=method_name,
                    stage="primary",
                    error=exc,
                    strict=False,
                )
                raise

            self._summary["primary_success"] += 1
            self._summary["primary_only"] += 1
            primary_only_methods = self._summary["primary_only_methods"]
            if method_name not in primary_only_methods:
                primary_only_methods.append(method_name)
            self._emit(
                {
                    "operation_id": operation_id,
                    "method": method_name,
                    "status": "primary_only",
                    "reason": "file writes require a dedicated file-object mirror strategy",
                }
            )
            return result

        return wrapped

    def _new_operation_id(self) -> str:
        operation_id = self._operation_id_factory()
        return str(operation_id)

    def _record_failure(
        self,
        *,
        operation_id: str,
        method_name: str,
        stage: str,
        error: Exception,
        strict: bool,
    ) -> dict[str, Any]:
        failure = {
            "operation_id": operation_id,
            "method": method_name,
            "stage": stage,
            "error": _redact_text(f"{type(error).__name__}: {error}"),
            "strict": strict,
        }
        self._summary["last_failure"] = failure
        if stage == "mirror" and strict:
            status = "mirror_failed_strict"
        elif stage == "mirror":
            status = "mirror_failed"
        else:
            status = "primary_failed"
        self._emit({**failure, "status": status})
        return failure

    def _emit(self, event: dict[str, Any]) -> None:
        if self._callback is not None:
            self._callback(dict(event))
        if self._logger is None:
            return
        log_method = getattr(self._logger, "warning", None) or getattr(self._logger, "info", None)
        if callable(log_method):
            log_method("dual_state_store event: %s", event)
        elif callable(self._logger):
            self._logger(dict(event))


def _redact_text(value: str) -> str:
    redacted = _SECRET_ASSIGNMENT_RE.sub(lambda match: f"{match.group(1)}=<redacted>", value)
    return _URI_RE.sub("<redacted-uri>", redacted)
