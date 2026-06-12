#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings  # noqa: E402
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository  # noqa: E402
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository  # noqa: E402
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder  # noqa: E402


def main() -> int:
    script_started_at = perf_counter()
    parser = argparse.ArgumentParser(
        description="Rehydrate Workbench SQL read models from PostgreSQL facts and publish all only after consistency checks pass."
    )
    parser.add_argument("--scope", action="append", default=[], help="Month scope YYYY-MM. Repeatable. Defaults to all fact-backed months.")
    parser.add_argument("--dry-run", action="store_true", help="List scopes and current status without rebuilding.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--profile-internal", action="store_true", help="Include fine-grained builder and repository step timings.")
    parser.add_argument(
        "--explain-structured-attachments",
        action="store_true",
        help="Run read-only EXPLAIN ANALYZE diagnostics for the Workbench structured OA attachment query.",
    )
    parser.add_argument(
        "--statement-timeout-seconds",
        type=int,
        default=300,
        help="PostgreSQL statement timeout for rebuild queries. Defaults to 300 seconds.",
    )
    args = parser.parse_args()
    if args.statement_timeout_seconds <= 0:
        raise ValueError("--statement-timeout-seconds must be positive.")
    if args.explain_structured_attachments and not args.scope:
        raise ValueError("--explain-structured-attachments requires at least one --scope to avoid accidental full-table diagnostics.")

    connection = PostgresConnection(PostgresSettings.from_env())
    connection.set_statement_timeout_ms(args.statement_timeout_seconds * 1000)
    repository = PostgresReadModelRepository(connection)
    queue_repository = RuntimeQueueRepository(connection)
    builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=repository)
    internal_timings: list[dict[str, Any]] = []
    if args.profile_internal:
        _install_internal_profiling(builder, repository, internal_timings)
    scopes = _scope_keys(builder, args.scope)
    report: dict[str, Any] = {
        "action": "rehydrate_workbench_read_models",
        "dry_run": bool(args.dry_run),
        "profile_internal": bool(args.profile_internal),
        "explain_structured_attachments": bool(args.explain_structured_attachments),
        "scope_keys": scopes,
        "rebuilt": [],
        "completed_dirty_scopes": [],
        "all": None,
        "status": None,
        "timings": [],
        "internal_timings": internal_timings,
    }
    if args.explain_structured_attachments:
        diagnostic_started_at = perf_counter()
        report["structured_attachment_diagnostics"] = [
            _structured_attachment_query_diagnostic(connection, scope_key) for scope_key in scopes
        ]
        report["timings"].append(
            {"step": "explain_structured_attachments", "duration_ms": _duration_ms(diagnostic_started_at)}
        )
        report["duration_ms"] = _duration_ms(script_started_at)
        return _print_report(report, json_output=args.json)
    if args.dry_run:
        status_started_at = perf_counter()
        report["status"] = repository.get_workbench_refresh_status(scope_key="all")
        report["timings"].append({"step": "dry_run_status", "duration_ms": _duration_ms(status_started_at)})
        report["duration_ms"] = _duration_ms(script_started_at)
        return _print_report(report, json_output=args.json)

    for scope_key in scopes:
        rebuild_started_at = perf_counter()
        result = builder.rebuild_workbench_read_model_scope(scope_key)
        rebuild_duration_ms = _duration_ms(rebuild_started_at)
        status_started_at = perf_counter()
        status = repository.get_workbench_refresh_status(scope_key=scope_key)
        status_duration_ms = _duration_ms(status_started_at)
        if str(status.get("read_model_status") or "").strip() == "failed":
            raise RuntimeError(str(status.get("last_error") or f"Workbench scope {scope_key} failed consistency validation."))
        complete_started_at = perf_counter()
        completed_dirty_scope = False
        if queue_repository.complete_read_model_refresh(
            tenant_id="default",
            scope_type="workbench",
            scope_key=scope_key,
        ):
            completed_dirty_scope = True
            report["completed_dirty_scopes"].append(scope_key)
        complete_duration_ms = _duration_ms(complete_started_at)
        scope_timings = {
            "rebuild_ms": rebuild_duration_ms,
            "status_ms": status_duration_ms,
            "complete_dirty_scope_ms": complete_duration_ms,
            "completed_dirty_scope": completed_dirty_scope,
        }
        report["timings"].append({"step": "scope", "scope_key": scope_key, **scope_timings})
        report["rebuilt"].append({"scope_key": scope_key, "result": result, "status": status, "timings": scope_timings})

    all_started_at = perf_counter()
    all_result = builder.refresh_workbench_all_scope_from_active_shards("all")
    all_duration_ms = _duration_ms(all_started_at)
    all_status_started_at = perf_counter()
    all_status = repository.get_workbench_refresh_status(scope_key="all")
    all_status_duration_ms = _duration_ms(all_status_started_at)
    if str(all_status.get("read_model_status") or "").strip() == "failed":
        raise RuntimeError(str(all_status.get("last_error") or "Workbench all-scope generation failed consistency validation."))
    complete_all_started_at = perf_counter()
    completed_all_dirty_scope = False
    if queue_repository.complete_read_model_refresh(
        tenant_id="default",
        scope_type="workbench",
        scope_key="all",
    ):
        completed_all_dirty_scope = True
        report["completed_dirty_scopes"].append("all")
    complete_all_duration_ms = _duration_ms(complete_all_started_at)
    report["all"] = all_result
    report["timings"].append(
        {
            "step": "all",
            "rebuild_ms": all_duration_ms,
            "status_ms": all_status_duration_ms,
            "complete_dirty_scope_ms": complete_all_duration_ms,
            "completed_dirty_scope": completed_all_dirty_scope,
        }
    )
    final_status_started_at = perf_counter()
    report["status"] = repository.get_workbench_refresh_status(scope_key="all")
    report["timings"].append({"step": "final_status", "duration_ms": _duration_ms(final_status_started_at)})
    report["duration_ms"] = _duration_ms(script_started_at)
    return _print_report(report, json_output=args.json)


def _scope_keys(builder: WorkbenchSqlProjectionBuilder, requested: list[str]) -> list[str]:
    if requested:
        return sorted(dict.fromkeys(str(scope).strip() for scope in requested if str(scope).strip()))
    return list(builder.list_workbench_scope_shards("all"))


def _print_report(report: dict[str, Any], *, json_output: bool) -> int:
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def _duration_ms(started_at: float) -> float:
    return round((perf_counter() - started_at) * 1000, 3)


def _structured_attachment_query_diagnostic(connection: PostgresConnection, scope_key: str) -> dict[str, Any]:
    normalized_scope = str(scope_key or "").strip()
    if not normalized_scope:
        raise ValueError("scope_key is required for structured attachment diagnostics.")
    if normalized_scope == "all":
        oa_row = connection.fetch_one(
            """
            select array_agg(row_id order by row_id) as row_ids, count(*)::int as count
            from app.oa_applications
            """
        )
        scope_month_param = None
    else:
        oa_row = connection.fetch_one(
            """
            select array_agg(row_id order by row_id) as row_ids, count(*)::int as count
            from app.oa_applications
            where scope_month = %s::date
            """,
            (f"{normalized_scope}-01",),
        )
        scope_month_param = f"{normalized_scope}-01"
    oa_row_ids = list((oa_row or {}).get("row_ids") or [])
    table_stats = connection.fetch_all(
        """
        select
            relname,
            n_live_tup::bigint as live_rows,
            pg_total_relation_size(relid)::bigint as total_bytes
        from pg_stat_user_tables
        where schemaname = 'app'
          and relname in (
              'oa_applications',
              'oa_application_items',
              'oa_attachments',
              'oa_attachment_invoice_cache',
              'oa_attachment_invoice_cache_sources'
          )
        order by relname
        """
    )
    indexes = connection.fetch_all(
        """
        select tablename, indexname, indexdef
        from pg_indexes
        where schemaname = 'app'
          and tablename in (
              'oa_applications',
              'oa_application_items',
              'oa_attachments',
              'oa_attachment_invoice_cache',
              'oa_attachment_invoice_cache_sources'
          )
        order by tablename, indexname
        """
    )
    explain_rows = connection.fetch_all(
        """
        explain (analyze, buffers, verbose, format text)
        select
            oa.row_id as oa_row_id,
            oa.scope_month,
            item.normalized_payload as item_payload,
            attachment.normalized_payload as attachment_payload,
            coalesce(direct_cache.cache_source_attachment_key, fallback_cache.cache_source_attachment_key) as cache_source_attachment_key,
            coalesce(direct_cache.invoices, fallback_cache.invoices, '[]'::jsonb) as cache_invoices,
            coalesce(direct_cache.evidences, fallback_cache.evidences, '[]'::jsonb) as cache_evidences,
            coalesce(
                case
                    when jsonb_typeof(coalesce(direct_cache.artifacts, fallback_cache.artifacts)) = 'array'
                        then coalesce(direct_cache.artifacts, fallback_cache.artifacts)
                    else '[]'::jsonb
                end,
                '[]'::jsonb
            ) as cache_artifacts
        from app.oa_application_items item
        join app.oa_applications oa on oa.id = item.oa_application_id
        left join app.oa_attachments attachment
          on attachment.oa_application_id = oa.id
         and (
                attachment.row_id = item.row_id
                or attachment.normalized_payload->>'source_expense_item_id' = item.row_id
             )
        left join lateral (
            select matched.cache_source_attachment_key, matched.parsed_at, matched.invoices, matched.evidences, matched.artifacts
            from (
                select
                    0 as match_rank,
                    source.cache_source_attachment_key,
                    cache.parsed_at,
                    cache.invoices,
                    cache.evidences,
                    cache.artifacts
                from app.oa_attachment_invoice_cache_sources source
                join app.oa_attachment_invoice_cache cache
                  on cache.source_attachment_key = source.cache_source_attachment_key
                where source.source_attachment_key = attachment.source_attachment_key
                union all
                select
                    1 as match_rank,
                    cache.source_attachment_key as cache_source_attachment_key,
                    cache.parsed_at,
                    cache.invoices,
                    cache.evidences,
                    cache.artifacts
                from app.oa_attachment_invoice_cache cache
                where cache.source_attachment_key = attachment.source_attachment_key
            ) matched
            order by matched.match_rank, matched.parsed_at desc nulls last, matched.cache_source_attachment_key
            limit 1
        ) direct_cache on true
        left join lateral (
            select cache.source_attachment_key as cache_source_attachment_key, cache.parsed_at, cache.invoices, cache.evidences, cache.artifacts
            from app.oa_attachment_invoice_cache cache
            where direct_cache.cache_source_attachment_key is null
              and nullif(
                    coalesce(
                        item.normalized_payload->>'expense_item_id',
                        item.normalized_payload->>'row_id'
                    ),
                    ''
                  ) is not null
              and nullif(
                    coalesce(
                        attachment.normalized_payload->>'source_attachment_name',
                        attachment.normalized_payload->>'attachment_name',
                        attachment.normalized_payload->>'fileName',
                        attachment.normalized_payload->>'filename'
                    ),
                    ''
                  ) is not null
              and exists (
                    select 1
                    from jsonb_array_elements(
                        coalesce(cache.invoices, '[]'::jsonb)
                        || coalesce(cache.evidences, '[]'::jsonb)
                        || coalesce(
                            case
                                when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                                else '[]'::jsonb
                            end,
                            '[]'::jsonb
                        )
                    ) as evidence(value)
                    where nullif(evidence.value->>'source_expense_item_id', '') = nullif(
                            coalesce(
                                item.normalized_payload->>'expense_item_id',
                                item.normalized_payload->>'row_id'
                            ),
                            ''
                          )
                      and nullif(
                            coalesce(
                                evidence.value->>'source_attachment_name',
                                evidence.value->>'attachment_name',
                                evidence.value->>'fileName',
                                evidence.value->>'filename'
                            ),
                            ''
                          ) = nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                          )
                )
            order by cache.parsed_at desc nulls last, cache.source_attachment_key
            limit 1
        ) fallback_cache on true
        where oa.row_id = any(%s)
          and (%s = 'all' or oa.scope_month = %s::date)
        order by oa.row_id, item.row_id, attachment.source_attachment_key
        """,
        (oa_row_ids, normalized_scope, scope_month_param),
    )
    return {
        "scope_key": normalized_scope,
        "oa_row_count": int((oa_row or {}).get("count") or 0),
        "sample_oa_row_ids": oa_row_ids[:10],
        "table_stats": table_stats,
        "indexes": indexes,
        "plan": [str(row.get("QUERY PLAN") or "") for row in explain_rows],
    }


def _install_internal_profiling(builder: Any, repository: Any, timings: list[dict[str, Any]]) -> None:
    for attr in (
        "_current_dirty_scope_source_version",
        "_workbench_rows_for_month",
        "_oa_projection_rows",
        "_attachment_invoice_rows_from_structured_oa_tables",
        "_bank_rows",
        "_invoice_rows",
        "_open_etc_invoice_summary_rows",
        "_active_pair_relations_for_month",
        "_active_reconciliation_decisions_for_month",
        "_supplement_missing_relation_rows",
        "_supplement_missing_decision_rows",
        "_group_payload",
        "_current_bank_auto_tag_rules_version",
        "refresh_workbench_all_scope_from_active_shards",
    ):
        _wrap_timed_method(builder, attr, f"builder.{attr}", timings)
    for attr in (
        "save_workbench_read_models",
        "_refresh_workbench_all_scope_from_month_shards",
        "_workbench_generation_consistency_failures",
        "_start_workbench_generation",
        "_upsert_workbench_generation_stats",
        "_activate_workbench_generation",
        "get_workbench_refresh_status",
    ):
        _wrap_timed_method(repository, attr, f"repository.{attr}", timings)


def _wrap_timed_method(obj: Any, attr: str, label: str, timings: list[dict[str, Any]]) -> None:
    original = getattr(obj, attr, None)
    if not callable(original):
        return

    def timed(*args: Any, **kwargs: Any) -> Any:
        started_at = perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            item: dict[str, Any] = {"step": label, "duration_ms": _duration_ms(started_at)}
            changed_scope_keys = kwargs.get("changed_scope_keys")
            if changed_scope_keys is not None:
                item["changed_scope_keys"] = sorted(str(scope_key) for scope_key in changed_scope_keys)
            if args and attr in {"_workbench_rows_for_month", "_oa_projection_rows", "_bank_rows", "_invoice_rows"}:
                item["scope_key"] = str(args[0])
            timings.append(item)

    setattr(obj, attr, timed)


if __name__ == "__main__":
    raise SystemExit(main())
