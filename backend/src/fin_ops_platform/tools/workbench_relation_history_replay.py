from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import row_payload, text_list
from fin_ops_platform.services.workbench_pair_relation_service import DISPLAY_ONLY_PAIR_RELATION_MODES
from fin_ops_platform.services.workbench_relation_command_service import VALID_WORKBENCH_RELATION_MODES


KNOWN_RELATION_STATUSES = {"active", "cancelled", "withdrawn", "superseded", "repair_attention"}


@dataclass(frozen=True)
class RelationReplayIssue:
    severity: str
    code: str
    message: str
    case_ids: list[str]
    row_id: str = ""
    row_type: str = ""
    details: dict[str, Any] | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run workbench relation PostgreSQL history and active row occupation consistency."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report. This tool is read-only either way.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when issues are found.")
    parser.add_argument("--tenant-id", default="default")
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
    report = build_replay_report(active_connection, tenant_id=str(args.tenant_id or "default"))
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default), file=stdout)
    if args.fail_on_issues and report["summary"]["issue_count"]:
        return 1
    return 0


def build_replay_report(connection: Any, *, tenant_id: str = "default") -> dict[str, Any]:
    relation_rows = _fetch_relation_rows(connection)
    history_rows = _fetch_history_rows(connection)
    history_counts = _history_counts(history_rows)
    readiness_rows = _fetch_readiness_rows(connection, tenant_id=tenant_id)
    issues: list[RelationReplayIssue] = []

    normalized_relations = [_normalize_relation_row(row) for row in relation_rows]
    relation_case_ids = {str(relation.get("case_id") or "").strip() for relation in normalized_relations}
    relation_case_ids.discard("")
    active_relations = [relation for relation in normalized_relations if relation.get("status") == "active"]

    issues.extend(_relation_shape_issues(normalized_relations))
    issues.extend(_active_row_occupation_issues(active_relations))
    issues.extend(_history_issues(relation_case_ids, history_counts))
    issues.extend(_history_display_only_relation_issues(history_rows))
    issues.extend(_readiness_issues(readiness_rows))

    issue_payloads = [asdict(issue) for issue in issues]
    error_count = sum(1 for issue in issues if issue.severity == "error")
    warning_count = sum(1 for issue in issues if issue.severity == "warning")
    display_only_history_before_relation_count = sum(
        int(issue.details.get("relation_count") or 0)
        for issue in issues
        if issue.code == "display_only_relation_in_confirm_history" and isinstance(issue.details, dict)
    )
    return {
        "mode": "dry-run",
        "tenant_id": tenant_id,
        "overall_status": "pass" if not issues else "issues_found",
        "summary": {
            "relation_count": len(normalized_relations),
            "active_relation_count": len(active_relations),
            "history_case_count": len(history_counts),
            "readiness_row_count": len(readiness_rows),
            "issue_count": len(issues),
            "error_count": error_count,
            "warning_count": warning_count,
            "display_only_history_before_relation_count": display_only_history_before_relation_count,
        },
        "issues": issue_payloads,
        "readiness": readiness_rows,
    }


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(30_000)
    return connection


def _fetch_relation_rows(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          case_id,
          relation_mode,
          status,
          row_ids,
          row_types,
          month_scope::text as month_scope,
          created_at::text as created_at,
          updated_at::text as updated_at,
          raw_payload
        from app.workbench_pair_relations
        order by case_id
        """
    )


def _fetch_history_rows(connection: Any) -> list[dict[str, Any]]:
    return connection.fetch_all(
        """
        select
          case_id,
          event_type,
          occurred_at::text as occurred_at,
          before_payload,
          after_payload,
          raw_payload
        from app.workbench_pair_relation_history
        order by occurred_at, case_id
        """
    )


def _history_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        result[case_id] = int(result.get(case_id) or 0) + 1
    return result


def _fetch_readiness_rows(connection: Any, *, tenant_id: str) -> list[dict[str, Any]]:
    try:
        return connection.fetch_all(
            """
            select
              read_model_key,
              scope_type,
              scope_key,
              status,
              schema_version,
              row_count,
              generated_at::text as generated_at,
              last_error
            from read_model.app_status_readiness
            where tenant_id = %s
              and read_model_key = 'workbench_relation'
            order by scope_key
            """,
            (tenant_id,),
        )
    except Exception as exc:
        return [
            {
                "read_model_key": "workbench_relation",
                "status": "unavailable",
                "last_error": str(exc) or exc.__class__.__name__,
            }
        ]


def _normalize_relation_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "raw_payload")
    relation_payload = payload if isinstance(payload, dict) else {}
    case_id = str(row.get("case_id") or relation_payload.get("case_id") or "").strip()
    row_ids = text_list(row.get("row_ids")) or text_list(relation_payload.get("row_ids"))
    row_types = text_list(row.get("row_types")) or text_list(relation_payload.get("row_types"))
    return {
        "case_id": case_id,
        "relation_mode": str(row.get("relation_mode") or relation_payload.get("relation_mode") or "").strip(),
        "status": str(row.get("status") or relation_payload.get("status") or "active").strip(),
        "row_ids": row_ids,
        "row_types": row_types,
        "month_scope": str(row.get("month_scope") or relation_payload.get("month_scope") or "").strip(),
        "raw_payload_case_id": str(relation_payload.get("case_id") or "").strip(),
    }


def _relation_shape_issues(relations: list[dict[str, Any]]) -> list[RelationReplayIssue]:
    issues: list[RelationReplayIssue] = []
    for relation in relations:
        case_id = str(relation.get("case_id") or "")
        relation_mode = str(relation.get("relation_mode") or "")
        status = str(relation.get("status") or "")
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        if status not in KNOWN_RELATION_STATUSES:
            issues.append(
                RelationReplayIssue(
                    severity="warning",
                    code="unknown_relation_status",
                    message=f"Relation has unknown status: {status}",
                    case_ids=[case_id],
                    details={"status": status},
                )
            )
        if relation_mode in DISPLAY_ONLY_PAIR_RELATION_MODES:
            severity = "error" if status == "active" else "warning"
            issues.append(
                RelationReplayIssue(
                    severity=severity,
                    code="display_only_relation_mode_in_write_model",
                    message=(
                        "Active relation uses a display-only relation mode."
                        if severity == "error"
                        else "Non-active relation uses a display-only relation mode."
                    ),
                    case_ids=[case_id],
                    details={"relation_mode": relation_mode, "status": status},
                )
            )
        elif relation_mode not in VALID_WORKBENCH_RELATION_MODES:
            severity = "error" if status == "active" else "warning"
            issues.append(
                RelationReplayIssue(
                    severity=severity,
                    code="unknown_relation_mode",
                    message=(
                        "Active relation mode is not registered for write facts."
                        if severity == "error"
                        else "Historical non-active relation mode is not registered for new write facts."
                    ),
                    case_ids=[case_id],
                    details={"relation_mode": relation_mode, "status": status},
                )
            )
        if len(row_ids) != len(row_types):
            issues.append(
                RelationReplayIssue(
                    severity="error",
                    code="row_ids_row_types_length_mismatch",
                    message="Relation row_ids and row_types lengths differ.",
                    case_ids=[case_id],
                    details={"row_ids": row_ids, "row_types": row_types},
                )
            )
        if status == "active" and not row_ids:
            issues.append(
                RelationReplayIssue(
                    severity="error",
                    code="active_relation_without_rows",
                    message="Active relation has no row_ids.",
                    case_ids=[case_id],
                )
            )
        seen_rows: set[tuple[str, str]] = set()
        duplicate_rows: set[tuple[str, str]] = set()
        for row_id, row_type in zip(row_ids, row_types, strict=False):
            key = (str(row_type), str(row_id))
            if key in seen_rows:
                duplicate_rows.add(key)
            seen_rows.add(key)
        for row_type, row_id in sorted(duplicate_rows):
            issues.append(
                RelationReplayIssue(
                    severity="error",
                    code="duplicate_row_within_relation",
                    message="Relation contains the same row more than once.",
                    case_ids=[case_id],
                    row_id=row_id,
                    row_type=row_type,
                )
            )
        raw_payload_case_id = str(relation.get("raw_payload_case_id") or "")
        if raw_payload_case_id and raw_payload_case_id != case_id:
            issues.append(
                RelationReplayIssue(
                    severity="warning",
                    code="payload_case_id_mismatch",
                    message="Relation table case_id differs from raw_payload.normalized_payload.case_id.",
                    case_ids=[case_id],
                    details={"raw_payload_case_id": raw_payload_case_id},
                )
            )
    return issues


def _active_row_occupation_issues(relations: list[dict[str, Any]]) -> list[RelationReplayIssue]:
    occupants: dict[tuple[str, str], set[str]] = defaultdict(set)
    for relation in relations:
        case_id = str(relation.get("case_id") or "")
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        for row_id, row_type in zip(row_ids, row_types, strict=False):
            normalized_row_id = str(row_id).strip()
            normalized_row_type = str(row_type).strip()
            if normalized_row_id and normalized_row_type:
                occupants[(normalized_row_type, normalized_row_id)].add(case_id)
    issues: list[RelationReplayIssue] = []
    for (row_type, row_id), case_ids in sorted(occupants.items()):
        if len(case_ids) <= 1:
            continue
        issues.append(
            RelationReplayIssue(
                severity="error",
                code="active_row_occupied_by_multiple_cases",
                message="One active row is occupied by multiple active relation cases.",
                case_ids=sorted(case_ids),
                row_id=row_id,
                row_type=row_type,
            )
        )
    return issues


def _history_issues(relation_case_ids: set[str], history_counts: dict[str, int]) -> list[RelationReplayIssue]:
    issues: list[RelationReplayIssue] = []
    for case_id in sorted(relation_case_ids):
        if int(history_counts.get(case_id) or 0) > 0:
            continue
        issues.append(
            RelationReplayIssue(
                severity="warning",
                code="relation_without_history",
                message="Relation has no history rows.",
                case_ids=[case_id],
            )
        )
    for case_id in sorted(set(history_counts).difference(relation_case_ids)):
        issues.append(
            RelationReplayIssue(
                severity="warning",
                code="orphan_history_case",
                message="History exists for a case_id that is not present in app.workbench_pair_relations.",
                case_ids=[case_id],
                details={"history_count": int(history_counts.get(case_id) or 0)},
            )
        )
    return issues


def _history_display_only_relation_issues(history_rows: list[dict[str, Any]]) -> list[RelationReplayIssue]:
    issues: list[RelationReplayIssue] = []
    for row in history_rows:
        case_id = str(row.get("case_id") or "").strip()
        payload = row_payload(row, "raw_payload")
        history_payload = payload if isinstance(payload, dict) else {}
        operation_type = str(row.get("event_type") or history_payload.get("operation_type") or "").strip()
        before_relations = row.get("before_payload")
        if not isinstance(before_relations, list):
            before_relations = history_payload.get("before_relations")
        display_only_relations = [
            relation
            for relation in list(before_relations or [])
            if _is_non_restorable_display_only_relation(relation)
        ]
        if not display_only_relations:
            continue
        relation_modes = sorted(
            {
                str(relation.get("relation_mode") or "").strip()
                for relation in display_only_relations
                if isinstance(relation, dict)
            }
        )
        relation_case_ids = sorted(
            {
                str(relation.get("case_id") or "").strip()
                for relation in display_only_relations
                if isinstance(relation, dict) and str(relation.get("case_id") or "").strip()
            }
        )
        issues.append(
            RelationReplayIssue(
                severity="warning",
                code="display_only_relation_in_confirm_history",
                message=(
                    "Confirm history contains display-only before_relations. "
                    "Runtime withdraw filters these snapshots; active display-only relations require data repair."
                ),
                case_ids=[case_id],
                details={
                    "operation_type": operation_type,
                    "relation_count": len(display_only_relations),
                    "relation_modes": relation_modes,
                    "relation_case_ids": relation_case_ids,
                },
            )
        )
    return issues


def _is_non_restorable_display_only_relation(relation: Any) -> bool:
    if not isinstance(relation, dict):
        return False
    relation_mode = str(relation.get("relation_mode") or "").strip()
    if relation_mode not in DISPLAY_ONLY_PAIR_RELATION_MODES:
        return False
    if relation.get("restorable_on_withdraw") is True:
        return False
    special_metadata = relation.get("special_metadata")
    return not (isinstance(special_metadata, dict) and special_metadata.get("restorable_on_withdraw") is True)


def _readiness_issues(readiness_rows: list[dict[str, Any]]) -> list[RelationReplayIssue]:
    issues: list[RelationReplayIssue] = []
    if not readiness_rows:
        return [
            RelationReplayIssue(
                severity="warning",
                code="workbench_relation_readiness_missing",
                message="No app_status_readiness row exists for workbench_relation.",
                case_ids=[],
            )
        ]
    for row in readiness_rows:
        status = str(row.get("status") or "").strip()
        if status == "fresh":
            continue
        issues.append(
            RelationReplayIssue(
                severity="warning",
                code="workbench_relation_readiness_not_fresh",
                message="workbench_relation read model readiness is not fresh.",
                case_ids=[],
                details={key: value for key, value in row.items() if key in {"scope_key", "status", "last_error"}},
            )
        )
    return issues


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
