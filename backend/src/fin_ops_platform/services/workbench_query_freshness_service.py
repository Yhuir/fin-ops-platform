from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder


class WorkbenchQueryFreshnessService:
    """Compare canonical Workbench sources with active generations for page reads."""

    def __init__(
        self,
        *,
        connection: object | None,
        repository: object | None,
        single_scope_stale_reasons: Callable[..., list[str]],
    ) -> None:
        self._connection = connection
        self._repository = repository
        self._single_scope_stale_reasons = single_scope_stale_reasons
        self._expected_source_versions_by_scope: dict[str, dict[str, object]] = {}

    def apply(
        self,
        status_payload: dict[str, object],
        *,
        scope_key: str | None = None,
    ) -> dict[str, object]:
        if status_payload.get("active_refresh_in_progress") is True:
            return status_payload

        normalized_scope_key = str(scope_key or "").strip() or "all"
        refresh_scope_keys: list[str] = []
        if normalized_scope_key == "all" and self._supports_bulk_proof():
            reasons, refresh_scope_keys = self._all_scope_stale_reasons()
        else:
            reasons = self._single_scope_stale_reasons(
                self._status_source_versions(status_payload),
                scope_key=normalized_scope_key,
            )
            if reasons and normalized_scope_key != "all":
                refresh_scope_keys.append(normalized_scope_key)
        if not reasons:
            return status_payload

        result = dict(status_payload)
        existing_reasons = (
            list(result.get("read_model_stale_reasons") or [])
            if isinstance(result.get("read_model_stale_reasons"), list)
            else []
        )
        result["read_model_stale_reasons"] = list(
            dict.fromkeys([*existing_reasons, *reasons])
        )
        result["refresh_scope_keys"] = list(dict.fromkeys(refresh_scope_keys))
        if str(result.get("read_model_status") or "fresh") in {"fresh", "refreshing"}:
            result["read_model_status"] = "stale"
        return result

    def _supports_bulk_proof(self) -> bool:
        return bool(
            self._connection is not None
            and callable(getattr(self._connection, "fetch_all", None))
            and callable(
                getattr(
                    self._repository,
                    "active_workbench_source_versions_by_scope",
                    None,
                )
            )
        )

    def _all_scope_stale_reasons(self) -> tuple[list[str], list[str]]:
        builder = WorkbenchSqlProjectionBuilder(connection=self._connection)
        scope_keys = builder.list_workbench_scope_shards("all")
        expected_by_scope = builder.source_versions_for_scopes(scope_keys)
        self._expected_source_versions_by_scope.update(
            {
                str(scope_key).strip(): dict(source_versions)
                for scope_key, source_versions in expected_by_scope.items()
                if str(scope_key).strip() and isinstance(source_versions, dict)
            }
        )
        active_versions_loader = getattr(
            self._repository,
            "active_workbench_source_versions_by_scope",
        )
        active_by_scope = {
            str(scope_key).strip(): dict(source_versions)
            for scope_key, source_versions in dict(
                active_versions_loader(scope_keys=scope_keys) or {}
            ).items()
            if str(scope_key).strip() and isinstance(source_versions, dict)
        }
        reasons: list[str] = []
        refresh_scope_keys: list[str] = []
        for scope_key in scope_keys:
            scope_reasons = source_version_mismatch_reasons(
                expected=require_expected_source_versions(
                    expected_by_scope.get(scope_key),
                    context=f"workbench_sql_read_model:{scope_key}",
                ),
                actual=active_by_scope.get(scope_key, {}),
            )
            if not scope_reasons:
                continue
            refresh_scope_keys.append(scope_key)
            reasons.extend(f"{scope_key}:{reason}" for reason in scope_reasons)
        return reasons, refresh_scope_keys

    def expected_source_versions(self, scope_key: str) -> dict[str, object] | None:
        source_versions = self._expected_source_versions_by_scope.get(
            str(scope_key or "").strip()
        )
        return dict(source_versions) if source_versions else None

    @staticmethod
    def _status_source_versions(payload: dict[str, object]) -> dict[str, object]:
        generations = (
            payload.get("generations")
            if isinstance(payload.get("generations"), list)
            else []
        )
        active_generation_id = str(payload.get("active_generation_id") or "")
        for generation in generations:
            if not isinstance(generation, dict):
                continue
            if str(generation.get("generation_id") or "") != active_generation_id:
                continue
            source_versions = generation.get("source_versions")
            return dict(source_versions) if isinstance(source_versions, dict) else {}
        source_versions = payload.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}
