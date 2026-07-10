from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import row_payload, text, text_list


@dataclass(frozen=True)
class RelationDisplayIssue:
    severity: str
    code: str
    message: str
    case_id: str
    scope_key: str = ""
    row_id: str = ""
    row_type: str = ""
    details: dict[str, Any] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run audit for active workbench relations against active Workbench display generations."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report. This tool is read-only either way.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when blocking issues exist.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue code.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    _ = stderr
    args = build_parser().parse_args(argv)
    active_connection = connection or _connection_from_env()
    report = audit_workbench_relation_display(
        active_connection,
        tenant_id=str(args.tenant_id or "default"),
        example_limit=max(int(args.limit or 50), 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default), file=stdout)
    if args.fail_on_issues and int(report["summary"].get("blocking_issue_count") or 0):
        return 1
    return 0


def audit_workbench_relation_display(
    connection: Any,
    *,
    tenant_id: str = "default",
    example_limit: int = 50,
) -> dict[str, Any]:
    relations = [_normalize_relation(row) for row in _fetch_active_relations(connection)]
    active_generations = _fetch_active_generations(connection, tenant_id=tenant_id)
    relation_row_ids = sorted(
        {
            row_id
            for relation in relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id or "").strip()
        }
    )
    group_rows = _fetch_active_group_rows(connection, tenant_id=tenant_id, row_ids=relation_row_ids)
    automatic_decision_group_rows = _fetch_visible_automatic_decision_group_rows(
        connection,
        tenant_id=tenant_id,
        limit=example_limit,
    )
    generation_by_scope = {str(row.get("scope_key") or ""): row for row in active_generations}
    rows_by_scope_and_id = _rows_by_scope_and_row_id(group_rows)
    issues: list[RelationDisplayIssue] = []

    if relations and "all" not in generation_by_scope:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="missing_all_active_generation",
                message="Active relations exist but Workbench all scope has no active generation.",
                case_id="*",
                scope_key="all",
            )
        )

    for relation in relations:
        issues.extend(
            _relation_display_issues(
                relation,
                rows_by_scope_and_id=rows_by_scope_and_id,
                generation_by_scope=generation_by_scope,
            )
        )
    issues.extend(_visible_automatic_decision_issues(automatic_decision_group_rows))

    limited_issues = _limit_issue_examples(issues, example_limit=example_limit)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    all_generation = generation_by_scope.get("all") or {}
    return {
        "mode": "dry-run",
        "tenant_id": tenant_id,
        "overall_status": "pass" if not error_count else "issues_found",
        "summary": {
            "active_relation_count": len(relations),
            "active_generation_scope_count": len(active_generations),
            "audited_relation_row_id_count": len(relation_row_ids),
            "active_group_row_count": len(group_rows),
            "visible_automatic_decision_row_count": len(automatic_decision_group_rows),
            "issue_count": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "blocking_issue_count": error_count,
            "all_generation_id": all_generation.get("generation_id"),
            "all_generation_activated_at": all_generation.get("activated_at"),
            "issue_counts_by_code": _issue_counts_by_code(issues),
        },
        "issues": [asdict(issue) for issue in limited_issues],
    }


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(30_000)
    return connection


def _fetch_active_relations(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          case_id,
          relation_mode,
          status,
          row_ids,
          row_types,
          month_scope::text as month_scope,
          updated_at::text as updated_at,
          raw_payload
        from app.workbench_pair_relations
        where status = 'active'
        order by case_id
        """
    )


def _fetch_active_generations(connection: Any, *, tenant_id: str) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          scope_key,
          generation_id,
          activated_at::text as activated_at,
          row_count,
          group_count,
          build_metadata
        from read_model.workbench_generations
        where tenant_id = %s
          and status = 'active'
        order by scope_key
        """,
        (tenant_id,),
    )


def _fetch_active_group_rows(connection: Any, *, tenant_id: str, row_ids: list[str]) -> list[dict[str, Any]]:
    if not row_ids:
        return []
    return connection.fetch_all(
        """
        select
          gen.scope_key,
          gen.generation_id,
          gen.activated_at::text as generation_activated_at,
          gr.group_id,
          gr.zone,
          gr.pane,
          gr.row_id,
          gr.row_role,
          gr.source_kind,
          gr.status,
          gr.payload
        from read_model.workbench_generations gen
        join read_model.workbench_group_rows gr
          on gr.generation_id = gen.generation_id
         and gr.scope_key = gen.scope_key
        where gen.tenant_id = %s
          and gen.status = 'active'
          and gr.row_role <> 'summary'
          and gr.row_id = any(%s)
        order by gen.scope_key, gr.row_id, gr.group_id
        """,
        (tenant_id, row_ids),
    )


def _fetch_visible_automatic_decision_group_rows(connection: Any, *, tenant_id: str, limit: int) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          gen.scope_key,
          gen.generation_id,
          gen.activated_at::text as generation_activated_at,
          gr.group_id,
          gr.zone,
          gr.pane,
          gr.row_id,
          gr.row_role,
          gr.source_kind,
          gr.status,
          gr.payload
        from read_model.workbench_generations gen
        join read_model.workbench_group_rows gr
          on gr.generation_id = gen.generation_id
         and gr.scope_key = gen.scope_key
        where gen.tenant_id = %s
          and gen.status = 'active'
          and gr.row_role <> 'summary'
          and (
            gr.group_id like 'case:decision:%%'
            or gr.payload->>'relation_mode' = 'automatic_decision'
            or gr.payload->>'case_id' like 'decision:%%'
            or gr.payload ? 'workbench_reconciliation_decision'
          )
        order by gen.scope_key, gr.group_id, gr.row_id
        limit %s
        """,
        (tenant_id, limit),
    )
    return [row for row in rows if _row_is_visible_automatic_decision(row)]


def _normalize_relation(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "raw_payload")
    relation_payload = payload if isinstance(payload, dict) else {}
    row_ids = text_list(row.get("row_ids")) or text_list(relation_payload.get("row_ids"))
    row_types = text_list(row.get("row_types")) or text_list(relation_payload.get("row_types"))
    return {
        "case_id": text(row.get("case_id") or relation_payload.get("case_id")) or "",
        "relation_mode": text(row.get("relation_mode") or relation_payload.get("relation_mode")) or "",
        "status": text(row.get("status") or relation_payload.get("status")) or "active",
        "row_ids": row_ids,
        "row_types": row_types,
        "month_scope": text(row.get("month_scope") or relation_payload.get("month_scope")) or "",
        "updated_at": text(row.get("updated_at")) or "",
    }


def _rows_by_scope_and_row_id(rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        scope_key = text(row.get("scope_key")) or ""
        row_id = text(row.get("row_id")) or ""
        if scope_key and row_id:
            grouped[(scope_key, row_id)].append(row)
    return grouped


def _visible_automatic_decision_issues(rows: list[dict[str, Any]]) -> list[RelationDisplayIssue]:
    issues: list[RelationDisplayIssue] = []
    for row in rows:
        payload = row_payload(row, "payload")
        payload_dict = payload if isinstance(payload, dict) else {}
        group_id = text(row.get("group_id")) or ""
        row_id = text(row.get("row_id")) or text(payload_dict.get("id")) or ""
        pane = text(row.get("pane") or payload_dict.get("type") or payload_dict.get("source_kind")) or ""
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="visible_automatic_decision_group",
                message="Active Workbench generation contains visible automatic decision rows; same-row display must come from active linked relations only.",
                case_id=group_id,
                scope_key=text(row.get("scope_key")) or "",
                row_id=row_id,
                row_type=pane,
                details={
                    "group_id": group_id,
                    "payload_case_id": text(payload_dict.get("case_id")) or "",
                    "payload_relation_mode": text(payload_dict.get("relation_mode")) or "",
                },
            )
        )
    return issues


def _row_is_visible_automatic_decision(row: dict[str, Any]) -> bool:
    group_id = text(row.get("group_id")) or ""
    if group_id.startswith("case:decision:"):
        return True
    payload = row_payload(row, "payload")
    payload_dict = payload if isinstance(payload, dict) else {}
    if text(payload_dict.get("relation_mode")) == "automatic_decision":
        return True
    case_id = text(payload_dict.get("case_id"))
    if case_id and case_id.startswith("decision:"):
        return True
    return isinstance(payload_dict.get("workbench_reconciliation_decision"), dict)


def _relation_display_issues(
    relation: dict[str, Any],
    *,
    rows_by_scope_and_id: dict[tuple[str, str], list[dict[str, Any]]],
    generation_by_scope: dict[str, dict[str, Any]],
) -> list[RelationDisplayIssue]:
    case_id = str(relation.get("case_id") or "")
    row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or []) if str(row_id or "").strip()]
    row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
    relation_mode = str(relation.get("relation_mode") or "")
    issues: list[RelationDisplayIssue] = []
    if not case_id or not row_ids:
        return issues

    all_rows_by_id = {row_id: list(rows_by_scope_and_id.get(("all", row_id), [])) for row_id in row_ids}
    missing_all = [row_id for row_id, rows in all_rows_by_id.items() if not rows]
    if missing_all:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="relation_rows_missing_from_all_generation",
                message="Active relation members are missing from the active Workbench all generation.",
                case_id=case_id,
                scope_key="all",
                details={"missing_row_ids": missing_all, "relation_mode": relation_mode},
            )
        )

    issues.extend(
        _scope_group_issues(
            case_id=case_id,
            relation_mode=relation_mode,
            row_ids=row_ids,
            row_types=row_types,
            scope_key="all",
            rows_by_id=all_rows_by_id,
            require_complete=not missing_all,
        )
    )

    relation_scopes = sorted(
        {
            scope_key
            for (scope_key, row_id), rows in rows_by_scope_and_id.items()
            if scope_key != "all" and row_id in set(row_ids) and rows
        }
    )
    all_generation = generation_by_scope.get("all")
    all_activated_at = text((all_generation or {}).get("activated_at")) or ""
    for scope_key in relation_scopes:
        scope_rows_by_id = {row_id: list(rows_by_scope_and_id.get((scope_key, row_id), [])) for row_id in row_ids}
        missing_scope = [row_id for row_id, rows in scope_rows_by_id.items() if not rows]
        if missing_scope:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="relation_rows_missing_from_member_scope_generation",
                    message="Active relation members are not complete in a member Workbench month scope.",
                    case_id=case_id,
                    scope_key=scope_key,
                    details={"missing_row_ids": missing_scope, "relation_mode": relation_mode},
                )
            )
        issues.extend(
            _scope_group_issues(
                case_id=case_id,
                relation_mode=relation_mode,
                row_ids=row_ids,
                row_types=row_types,
                scope_key=scope_key,
                rows_by_id=scope_rows_by_id,
                require_complete=not missing_scope,
            )
        )
        scope_generation = generation_by_scope.get(scope_key) or {}
        scope_activated_at = text(scope_generation.get("activated_at")) or ""
        if all_activated_at and scope_activated_at and scope_activated_at > all_activated_at:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="all_generation_older_than_member_scope_generation",
                    message="Workbench all generation is older than a member month scope generation.",
                    case_id=case_id,
                    scope_key=scope_key,
                    details={
                        "all_activated_at": all_activated_at,
                        "member_scope_activated_at": scope_activated_at,
                        "all_generation_id": (all_generation or {}).get("generation_id"),
                        "member_generation_id": scope_generation.get("generation_id"),
                    },
                )
            )
    return issues


def _scope_group_issues(
    *,
    case_id: str,
    relation_mode: str,
    row_ids: list[str],
    row_types: list[str],
    scope_key: str,
    rows_by_id: dict[str, list[dict[str, Any]]],
    require_complete: bool,
) -> list[RelationDisplayIssue]:
    issues: list[RelationDisplayIssue] = []
    rows = [row for row_id in row_ids for row in rows_by_id.get(row_id, [])]
    group_ids = sorted({str(row.get("group_id") or "") for row in rows if str(row.get("group_id") or "").strip()})
    if require_complete and len(group_ids) > 1:
        issues.append(
            RelationDisplayIssue(
                severity="error",
                code="relation_rows_split_across_groups",
                message="Active relation members are visible in more than one Workbench group.",
                case_id=case_id,
                scope_key=scope_key,
                details={"group_ids": group_ids, "relation_mode": relation_mode},
            )
        )
    expected_group_ids = {case_id, f"case:{case_id}"}
    if require_complete and len(group_ids) == 1 and group_ids[0] not in expected_group_ids:
        issues.append(
            RelationDisplayIssue(
                severity="warning",
                code="relation_group_id_not_case_based",
                message="Active relation members are grouped together but not under the canonical case group id.",
                case_id=case_id,
                scope_key=scope_key,
                details={"group_id": group_ids[0], "expected_group_ids": sorted(expected_group_ids)},
            )
        )
    for row_index, row_id in enumerate(row_ids):
        rows_for_id = list(rows_by_id.get(row_id) or [])
        row_type = _row_type_at(row_types, row_index)
        distinct_groups = sorted({str(row.get("group_id") or "") for row in rows_for_id if str(row.get("group_id") or "").strip()})
        if len(distinct_groups) > 1:
            issues.append(
                RelationDisplayIssue(
                    severity="error",
                    code="relation_row_duplicate_visible_owner",
                    message="A relation member row has multiple visible owners in one active Workbench scope.",
                    case_id=case_id,
                    scope_key=scope_key,
                    row_id=row_id,
                    row_type=row_type,
                    details={"group_ids": distinct_groups},
                )
            )
        for row in rows_for_id:
            payload = row_payload(row, "payload")
            row_payload_dict = payload if isinstance(payload, dict) else {}
            payload_case_id = text(row_payload_dict.get("case_id") or row_payload_dict.get("relation_id"))
            if payload_case_id and payload_case_id != case_id:
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_row_payload_case_mismatch",
                        message="A relation member row payload points at a different relation case.",
                        case_id=case_id,
                        scope_key=scope_key,
                        row_id=row_id,
                        row_type=row_type,
                        details={"payload_case_id": payload_case_id},
                    )
                )
            payload_mode = text(row_payload_dict.get("relation_mode"))
            if payload_mode and payload_mode != relation_mode:
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_row_payload_mode_mismatch",
                        message="A relation member row payload has a different relation mode.",
                        case_id=case_id,
                        scope_key=scope_key,
                        row_id=row_id,
                        row_type=row_type,
                        details={"payload_relation_mode": payload_mode, "relation_mode": relation_mode},
                    )
                )
            if (
                require_complete
                and _relation_has_multiple_oa_rows(row_types)
                and row_type == "bank"
                and not _payload_source_oa_id(row_payload_dict)
            ):
                issues.append(
                    RelationDisplayIssue(
                        severity="error",
                        code="relation_bank_row_missing_source_oa_alignment",
                        message="A bank row in a multi-OA active relation is missing row-level source OA alignment evidence.",
                        case_id=case_id,
                        scope_key=scope_key,
                        row_id=row_id,
                        row_type=row_type,
                        details={
                            "relation_mode": relation_mode,
                            "expected_fields": ["source_oa_id", "source_oa_row_id", "derived_from_oa_id"],
                        },
                    )
                )
    return issues


def _row_type_at(row_types: list[str], index: int) -> str:
    if index < len(row_types):
        return row_types[index]
    return ""


def _relation_has_multiple_oa_rows(row_types: list[str]) -> bool:
    return sum(1 for row_type in row_types if str(row_type or "").strip() == "oa") >= 2


def _payload_source_oa_id(payload: dict[str, Any]) -> str:
    for key in ("source_oa_id", "source_oa_row_id", "derived_from_oa_id", "oa_row_id", "oa_id"):
        value = text(payload.get(key))
        if value:
            return value
    detail_fields = payload.get("detail_fields")
    if isinstance(detail_fields, dict):
        for key in ("source_oa_id", "source_oa_row_id", "derived_from_oa_id", "oa_row_id", "oa_id"):
            value = text(detail_fields.get(key))
            if value:
                return value
    return ""


def _limit_issue_examples(issues: list[RelationDisplayIssue], *, example_limit: int) -> list[RelationDisplayIssue]:
    counts: dict[str, int] = defaultdict(int)
    result: list[RelationDisplayIssue] = []
    for issue in issues:
        count = counts[issue.code]
        if count < example_limit:
            result.append(issue)
        counts[issue.code] = count + 1
    return result


def _issue_counts_by_code(issues: list[RelationDisplayIssue]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for issue in issues:
        counts[issue.code] += 1
    return dict(sorted(counts.items()))


def _json_default(value: Any) -> str:
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
