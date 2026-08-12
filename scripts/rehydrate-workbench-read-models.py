#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
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
from fin_ops_platform.tools.oa_attachment_invoice_promotion import (  # noqa: E402
    APPLY_CONFIRMATION_FLAG,
    audit_oa_attachment_invoice_promotion,
)


def main() -> int:
    script_started_at = perf_counter()
    parser = argparse.ArgumentParser(
        description="Maintain OA attachment identity bridges and canonical attachment invoice promotion."
    )
    parser.add_argument(
        "--scope",
        action="append",
        default=[],
        help="Month scope YYYY-MM for structured attachment diagnostics. Repeatable; 'all' is also supported.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview an OA attachment repair or promotion action.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument(
        "--repair-attachment-identity-bridge",
        action="store_true",
        help="Repair indexed OA attachment cache identity bridge rows. Requires --dry-run or --apply-repair.",
    )
    parser.add_argument(
        "--rollback-attachment-identity-bridge",
        action="store_true",
        help="Delete repairable attachment_identity_* bridge rows. Requires --dry-run or --apply-repair.",
    )
    parser.add_argument(
        "--promote-oa-attachment-invoices",
        action="store_true",
        help="Restore strong-identity OA attachment invoice links. Requires --dry-run or --apply-repair.",
    )
    parser.add_argument("--oa-row-id", action="append", default=[], help="Limit promotion to an exact OA row id.")
    parser.add_argument(
        APPLY_CONFIRMATION_FLAG,
        action="store_true",
        help="Required with --apply-repair --promote-oa-attachment-invoices.",
    )
    parser.add_argument(
        "--apply-repair",
        action="store_true",
        help="Apply an explicit repair or rollback action instead of previewing it.",
    )
    parser.add_argument(
        "--expected-fingerprint",
        help="Required when applying a fingerprinted repair; copy it from the dry-run report.",
    )
    parser.add_argument(
        "--explain-structured-attachments",
        action="store_true",
        help="Run read-only EXPLAIN ANALYZE diagnostics for canonical structured OA attachment lookup.",
    )
    parser.add_argument(
        "--statement-timeout-seconds",
        type=int,
        default=300,
        help="PostgreSQL statement timeout for maintenance queries. Defaults to 300 seconds.",
    )
    args = parser.parse_args()
    if args.statement_timeout_seconds <= 0:
        raise ValueError("--statement-timeout-seconds must be positive.")
    if args.dry_run and args.apply_repair:
        raise ValueError("--dry-run and --apply-repair are mutually exclusive.")
    repair_actions = (
        args.repair_attachment_identity_bridge,
        args.rollback_attachment_identity_bridge,
        args.promote_oa_attachment_invoices,
    )
    maintenance_actions = (*repair_actions, args.explain_structured_attachments)
    if sum(bool(value) for value in maintenance_actions) != 1:
        raise ValueError("Choose exactly one OA attachment maintenance action.")
    repair_mode = any(repair_actions)
    if args.apply_repair and not repair_mode:
        raise ValueError("--apply-repair is only valid with an OA attachment repair action.")
    if (
        args.apply_repair
        and (args.repair_attachment_identity_bridge or args.promote_oa_attachment_invoices)
        and not str(args.expected_fingerprint or "").strip()
    ):
        raise ValueError("Fingerprint-protected OA attachment repair requires --expected-fingerprint.")
    if (
        args.apply_repair
        and args.promote_oa_attachment_invoices
        and not bool(getattr(args, "confirm_apply_oa_attachment_invoices", False))
    ):
        raise ValueError(f"OA attachment invoice promotion apply requires {APPLY_CONFIRMATION_FLAG}.")
    if repair_mode and not (args.dry_run or args.apply_repair):
        raise ValueError("OA attachment repair requires --dry-run or --apply-repair.")
    if args.explain_structured_attachments and not args.scope:
        raise ValueError("--explain-structured-attachments requires at least one --scope to avoid accidental full-table diagnostics.")

    connection = PostgresConnection(PostgresSettings.from_env())
    connection.set_statement_timeout_ms(args.statement_timeout_seconds * 1000)
    if args.explain_structured_attachments:
        diagnostic_started_at = perf_counter()
        scopes = _scope_keys(args.scope)
        report: dict[str, Any] = {
            "action": "explain_structured_attachments",
            "read_only": True,
            "scope_keys": scopes,
            "timings": [],
        }
        report["structured_attachment_diagnostics"] = [
            _structured_attachment_query_diagnostic(connection, scope_key) for scope_key in scopes
        ]
        report["timings"].append(
            {"step": "explain_structured_attachments", "duration_ms": _duration_ms(diagnostic_started_at)}
        )
        report["duration_ms"] = _duration_ms(script_started_at)
        return _print_report(report, json_output=args.json)

    repair_started_at = perf_counter()
    report = {
        "action": (
            "rollback_attachment_identity_bridge"
            if args.rollback_attachment_identity_bridge
            else (
                "promote_oa_attachment_invoices"
                if args.promote_oa_attachment_invoices
                else "repair_attachment_identity_bridge"
            )
        ),
        "dry_run": bool(args.dry_run),
        "apply_repair": bool(args.apply_repair),
        "timings": [],
    }
    if args.promote_oa_attachment_invoices:
        report["oa_attachment_invoice_promotion"] = audit_oa_attachment_invoice_promotion(
            connection=connection,
            example_limit=100,
            apply=bool(args.apply_repair),
            oa_row_ids=list(args.oa_row_id or []),
            expected_fingerprint=str(args.expected_fingerprint or "").strip() or None,
        )
    elif args.rollback_attachment_identity_bridge:
        report["attachment_identity_bridge"] = _rollback_attachment_identity_bridge(
            connection,
            apply_changes=bool(args.apply_repair),
        )
    else:
        report["attachment_identity_bridge"] = _repair_attachment_identity_bridge(
            connection,
            apply_changes=bool(args.apply_repair),
            expected_fingerprint=str(args.expected_fingerprint or "").strip() or None,
        )
    report["timings"].append({"step": report["action"], "duration_ms": _duration_ms(repair_started_at)})
    report["duration_ms"] = _duration_ms(script_started_at)
    return _print_report(report, json_output=args.json)


def _scope_keys(requested: list[str]) -> list[str]:
    return sorted(dict.fromkeys(str(scope).strip() for scope in requested if str(scope).strip()))


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


def _repair_attachment_identity_bridge(
    connection: Any,
    *,
    apply_changes: bool,
    expected_fingerprint: str | None = None,
) -> dict[str, Any]:
    before = _attachment_identity_bridge_counts(connection)
    candidate_rows = _attachment_identity_bridge_candidate_rows(connection)
    candidates = {
        "total": len(candidate_rows),
        "by_source_kind": _count_rows_by_key(candidate_rows, "source_kind"),
    }
    candidate_fingerprint = _fingerprint_rows(candidate_rows)
    result: dict[str, Any] = {
        "mode": "apply" if apply_changes else "dry_run",
        "before": before,
        "candidates": candidates,
        "candidate_fingerprint": candidate_fingerprint,
    }
    if not apply_changes:
        result["applied"] = {"total": 0, "by_source_kind": {}}
        result["after"] = before
        return result
    if expected_fingerprint != candidate_fingerprint:
        raise ValueError("Attachment identity bridge candidate fingerprint changed; run dry-run again.")

    rows: list[dict[str, Any]] = []
    if candidate_rows:
        values_sql = ", ".join(["(%s, %s, %s, %s, %s, %s)"] * len(candidate_rows))
        params = tuple(
            value
            for row in candidate_rows
            for value in (
                row.get("cache_source_attachment_key"),
                row.get("source_attachment_key"),
                row.get("source_kind"),
                row.get("source_expense_item_id"),
                row.get("source_expense_row_index"),
                row.get("source_attachment_name"),
            )
        )
        rows = connection.fetch_all(
            f"""
        insert into app.oa_attachment_invoice_cache_sources as existing (
            cache_source_attachment_key,
            source_attachment_key,
            source_kind,
            source_expense_item_id,
            source_expense_row_index,
            source_attachment_name,
            updated_at
        )
        select
            candidate.cache_source_attachment_key,
            candidate.source_attachment_key,
            candidate.source_kind,
            candidate.source_expense_item_id,
            candidate.source_expense_row_index,
            candidate.source_attachment_name,
            now()
        from (values {values_sql}) as candidate(
            cache_source_attachment_key,
            source_attachment_key,
            source_kind,
            source_expense_item_id,
            source_expense_row_index,
            source_attachment_name
        )
        on conflict (cache_source_attachment_key, source_attachment_key, source_kind) do update set
            source_expense_item_id = excluded.source_expense_item_id,
            source_expense_row_index = excluded.source_expense_row_index,
            source_attachment_name = excluded.source_attachment_name,
            updated_at = now()
        where (
            existing.source_expense_item_id,
            existing.source_expense_row_index,
            existing.source_attachment_name
        ) is distinct from (
            excluded.source_expense_item_id,
            excluded.source_expense_row_index,
            excluded.source_attachment_name
        )
        returning source_kind
            """,
            params,
        )
    result["applied"] = {"total": len(rows), "by_source_kind": _count_rows_by_key(rows, "source_kind")}
    result["after"] = _attachment_identity_bridge_counts(connection)
    return result


def _rollback_attachment_identity_bridge(connection: Any, *, apply_changes: bool) -> dict[str, Any]:
    before = _attachment_identity_bridge_counts(connection)
    result: dict[str, Any] = {
        "mode": "apply" if apply_changes else "dry_run",
        "before": before,
        "candidates": before,
    }
    if not apply_changes:
        result["deleted"] = {"total": 0, "by_source_kind": {}}
        result["after"] = before
        return result

    rows = connection.fetch_all(
        """
        delete from app.oa_attachment_invoice_cache_sources
        where source_kind like 'attachment_identity_%%'
        returning source_kind
        """
    )
    result["deleted"] = {"total": len(rows), "by_source_kind": _count_rows_by_key(rows, "source_kind")}
    result["after"] = _attachment_identity_bridge_counts(connection)
    return result


def _attachment_identity_bridge_counts(connection: Any) -> dict[str, Any]:
    rows = connection.fetch_all(
        """
        select source_kind, count(*)::bigint as count
        from app.oa_attachment_invoice_cache_sources
        where source_kind like 'attachment_identity_%%'
        group by source_kind
        order by source_kind
        """
    )
    by_kind = {str(row.get("source_kind") or ""): int(row.get("count") or 0) for row in rows}
    return {"total": sum(by_kind.values()), "by_source_kind": by_kind}


def _attachment_identity_bridge_candidate_rows(connection: Any) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        f"""
        {_attachment_identity_bridge_matches_cte()}
        select matched.cache_source_attachment_key,
               matched.source_attachment_key,
               matched.source_kind,
               matched.source_expense_item_id,
               matched.source_expense_row_index,
               matched.source_attachment_name
        from identity_matches matched
        left join app.oa_attachment_invoice_cache_sources existing
          on existing.cache_source_attachment_key = matched.cache_source_attachment_key
         and existing.source_attachment_key = matched.source_attachment_key
         and existing.source_kind = matched.source_kind
        where existing.cache_source_attachment_key is null
           or (
                existing.source_expense_item_id,
                existing.source_expense_row_index,
                existing.source_attachment_name
              ) is distinct from (
                matched.source_expense_item_id,
                matched.source_expense_row_index,
                matched.source_attachment_name
              )
        order by matched.cache_source_attachment_key, matched.source_attachment_key, matched.source_kind
        """
    )
    return [dict(row) for row in rows]


def _count_rows_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "").strip() or "unknown"
        result[value] = result.get(value, 0) + 1
    return dict(sorted(result.items()))


def _fingerprint_rows(rows: list[dict[str, Any]]) -> str:
    normalized = sorted(
        (
            {key: row.get(key) for key in sorted(row)}
            for row in rows
        ),
        key=lambda row: json.dumps(row, ensure_ascii=False, sort_keys=True, default=str),
    )
    payload = json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _attachment_identity_bridge_matches_cte() -> str:
    return """
        with attachment_sources as (
            select distinct
                attachment.source_attachment_key,
                nullif(attachment.normalized_payload->>'source_expense_item_id', '') as source_expense_item_id,
                nullif(attachment.normalized_payload->>'source_expense_row_index', '') as source_expense_row_index,
                nullif(
                    coalesce(
                        attachment.normalized_payload->>'source_attachment_name',
                        attachment.normalized_payload->>'attachment_name',
                        attachment.normalized_payload->>'fileName',
                        attachment.normalized_payload->>'filename'
                    ),
                    ''
                ) as source_attachment_name
            from app.oa_attachments attachment
            where nullif(attachment.source_attachment_key, '') is not null
              and nullif(attachment.normalized_payload->>'source_expense_item_id', '') is not null
              and nullif(
                    coalesce(
                        attachment.normalized_payload->>'source_attachment_name',
                        attachment.normalized_payload->>'attachment_name',
                        attachment.normalized_payload->>'fileName',
                        attachment.normalized_payload->>'filename'
                    ),
                    ''
                  ) is not null
        ),
        cache_evidence_sources as (
            select
                cache.source_attachment_key as cache_source_attachment_key,
                nullif(evidence.value->>'source_attachment_key', '') as parsed_source_attachment_key,
                nullif(evidence.value->>'source_expense_item_id', '') as source_expense_item_id,
                nullif(evidence.value->>'source_expense_row_index', '') as source_expense_row_index,
                nullif(
                    coalesce(
                        evidence.value->>'source_attachment_name',
                        evidence.value->>'attachment_name',
                        evidence.value->>'fileName',
                        evidence.value->>'filename'
                    ),
                    ''
                ) as source_attachment_name,
                cache.parsed_at,
                evidence.source_kind
            from app.oa_attachment_invoice_cache cache
            cross join lateral (
                select invoice.value, 'attachment_identity_invoice'::text as source_kind
                from jsonb_array_elements(coalesce(cache.invoices, '[]'::jsonb)) as invoice(value)
                union all
                select evidence.value, 'attachment_identity_evidence'::text as source_kind
                from jsonb_array_elements(coalesce(cache.evidences, '[]'::jsonb)) as evidence(value)
                union all
                select artifact.value, 'attachment_identity_artifact'::text as source_kind
                from jsonb_array_elements(
                    coalesce(
                        case
                            when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                            when jsonb_typeof(cache.artifacts) = 'object' then jsonb_build_array(cache.artifacts)
                            else '[]'::jsonb
                        end,
                        '[]'::jsonb
                    )
                ) as artifact(value)
            ) evidence
            where nullif(evidence.value->>'source_expense_item_id', '') is not null
              and nullif(
                    coalesce(
                        evidence.value->>'source_attachment_name',
                        evidence.value->>'attachment_name',
                        evidence.value->>'fileName',
                        evidence.value->>'filename'
                    ),
                    ''
                  ) is not null
        ),
        identity_matches as (
            select distinct on (cache.cache_source_attachment_key, attachment.source_attachment_key, cache.source_kind)
                cache.cache_source_attachment_key,
                attachment.source_attachment_key,
                cache.source_kind,
                attachment.source_expense_item_id,
                coalesce(attachment.source_expense_row_index, cache.source_expense_row_index) as source_expense_row_index,
                attachment.source_attachment_name,
                cache.parsed_at
            from attachment_sources attachment
            join cache_evidence_sources cache
              on cache.source_expense_item_id = attachment.source_expense_item_id
             and cache.source_attachment_name = attachment.source_attachment_name
            where cache.cache_source_attachment_key is not null
              and attachment.source_attachment_key <> coalesce(cache.parsed_source_attachment_key, '')
            order by
                cache.cache_source_attachment_key,
                attachment.source_attachment_key,
                cache.source_kind,
                cache.parsed_at desc nulls last
        )
        """


if __name__ == "__main__":
    raise SystemExit(main())
