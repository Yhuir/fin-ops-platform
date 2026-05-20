from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    text,
    text_list,
    without_keys,
)


class PostgresReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def load_workbench_read_models(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select scope_key as key, payload, raw_payload from read_model.workbench_snapshots order by scope_key")
        if rows:
            return {"read_models": {str(row.get("key")): _read_model_payload(row) for row in rows}}
        return {}

    def save_workbench_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    connection.execute(
                        "delete from read_model.workbench_snapshots where scope_key = %s",
                        (scope_key,),
                    )
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                connection.execute(
                    """
                    insert into read_model.workbench_snapshots(scope_key, scope_month, source_versions, generated_at, cache_status, row_count, payload, raw_payload)
                    values (%s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        scope_month = excluded.scope_month,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        row_count = excluded.row_count,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        month_start(payload.get("scope_month") or payload.get("month") or scope_key),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        text(payload.get("cache_status") or "fresh"),
                        len(payload.get("rows")) if isinstance(payload.get("rows"), list) else int_value(payload.get("row_count"), 0),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_workbench_candidate_matches(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select candidate_key as key, payload, raw_payload from read_model.workbench_candidate_matches order by candidate_key"
        )
        values = {
            str(row.get("key")): payload
            for row in rows
            if (payload := _read_model_payload(row, drop_rebuildable_rows=True)) is not None
        }
        return {"candidates": values} if values else {}

    def save_workbench_candidate_matches(self, snapshot: dict[str, Any], *, changed_scope_months: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
            normalized_months = {str(month)[:7] for month in changed_scope_months or set() if str(month or "").strip()}
            for scope_month in sorted(normalized_months):
                connection.execute(
                    "delete from read_model.workbench_candidate_matches where to_char(scope_month, 'YYYY-MM') = %s",
                    (scope_month,),
                )
            for candidate_key, payload in iter_mapping(candidates):
                scope_month = month_start(payload.get("scope_month") or payload.get("month"))
                if normalized_months and str(scope_month or "")[:7] not in normalized_months:
                    continue
                connection.execute(
                    """
                    insert into read_model.workbench_candidate_matches(
                        candidate_key, scope_month, status, row_ids, confidence, source_versions,
                        generated_at, cache_status, payload, raw_payload
                    )
                    values (%s, %s::date, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s)
                    on conflict (candidate_key) do update set
                        scope_month = excluded.scope_month,
                        status = excluded.status,
                        row_ids = excluded.row_ids,
                        confidence = excluded.confidence,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        candidate_key,
                        scope_month,
                        text(payload.get("status") or "active"),
                        text_list(payload.get("row_ids")),
                        decimal_text(payload.get("confidence")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        text(payload.get("cache_status") or "fresh"),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_cost_statistics_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.cost_statistics_read_models order by scope_key",
            "read_models",
        )

    def save_cost_statistics_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        run_in_transaction(
            self._connection,
            lambda connection: self._save_generic_read_model_snapshots(
                connection,
                snapshot,
                table="read_model.cost_statistics_read_models",
                changed_scope_keys=changed_scope_keys,
                default_project_scope="all",
            ),
        )

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.tax_offset_read_models order by scope_key",
            "read_models",
        )

    def save_tax_offset_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        run_in_transaction(
            self._connection,
            lambda connection: self._save_generic_read_model_snapshots(
                connection,
                snapshot,
                table="read_model.tax_offset_read_models",
                changed_scope_keys=changed_scope_keys,
                default_project_scope=None,
            ),
        )

    def _load_table_map(self, sql: str, payload_key: str) -> dict[str, Any]:
        rows = self._connection.fetch_all(sql)
        values = {str(row.get("key")): _read_model_payload(row) for row in rows}
        return {payload_key: values} if values else {}

    def _save_generic_read_model_snapshots(
        self,
        connection: Any,
        snapshot: dict[str, Any],
        *,
        table: str,
        changed_scope_keys: set[str] | None,
        default_project_scope: str | None,
    ) -> None:
        read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
        if changed_scope_keys is not None:
            present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
            for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                connection.execute(f"delete from {table} where scope_key = %s", (scope_key,))
        for scope_key, payload in iter_mapping(read_models):
            if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                continue
            source_counts = payload.get("source_counts") if isinstance(payload.get("source_counts"), dict) else {}
            source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
            row_count = self._read_model_row_count(payload)
            scope_month = month_start(payload.get("scope_month") or payload.get("month") or scope_key)
            if default_project_scope is not None:
                connection.execute(
                    f"""
                    insert into {table}(
                        scope_key, project_scope, scope_month, generated_at, entry_count,
                        source_counts, source_versions, payload, raw_payload
                    )
                    values (%s, %s, %s::date, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        project_scope = excluded.project_scope,
                        scope_month = excluded.scope_month,
                        generated_at = excluded.generated_at,
                        entry_count = excluded.entry_count,
                        source_counts = excluded.source_counts,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        text(payload.get("project_scope") or default_project_scope) or default_project_scope,
                        scope_month,
                        text(payload.get("generated_at")),
                        row_count,
                        jsonb(source_counts),
                        jsonb(source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            else:
                connection.execute(
                    f"""
                    insert into {table}(
                        scope_key, scope_month, generated_at, entry_count,
                        source_counts, source_versions, payload, raw_payload
                    )
                    values (%s, %s::date, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        scope_month = excluded.scope_month,
                        generated_at = excluded.generated_at,
                        entry_count = excluded.entry_count,
                        source_counts = excluded.source_counts,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        scope_month,
                        text(payload.get("generated_at")),
                        row_count,
                        jsonb(source_counts),
                        jsonb(source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

    @staticmethod
    def _read_model_row_count(payload: dict[str, Any]) -> int:
        for key in ("entries", "rows", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        return int_value(payload.get("entry_count") or payload.get("row_count"), 0)


def _read_model_payload(row: dict[str, Any], *, drop_rebuildable_rows: bool = False) -> Any:
    payload = row_payload(row, "payload", "extra_payload", "raw_payload")
    if drop_rebuildable_rows and isinstance(payload, dict) and payload.get("rebuildable") is True:
        return None
    return without_keys(payload, {"rebuildable"})
