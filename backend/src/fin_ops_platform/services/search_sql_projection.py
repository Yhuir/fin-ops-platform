from __future__ import annotations

import json
import re
from typing import Any

from fin_ops_platform.services.postgres_repositories.read_models import (
    PostgresReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_canonical_query import (
    PostgresWorkbenchCanonicalQueryRepository,
)
from fin_ops_platform.services.search_read_model_repository import SearchReadModelRepositoryPort


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class SearchSqlProjectionBuilder:
    """Build the retained Search index from canonical facts and active relations."""

    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        canonical_query_repository: Any | None = None,
    ) -> None:
        broad_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._search_repository = SearchReadModelRepositoryPort(broad_repository)
        self._canonical_repository = (
            canonical_query_repository
            or PostgresWorkbenchCanonicalQueryRepository(connection)
        )

    def list_search_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope = str(scope_key or "").strip()
        if normalized_scope != "all":
            return [normalized_scope] if MONTH_RE.match(normalized_scope) else []
        return [
            scope
            for item in self._canonical_repository.list_workbench_search_scope_keys()
            if MONTH_RE.match(scope := str(item or "").strip())
        ]

    def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip()
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("search SQL projection scope_key must be a month shard YYYY-MM.")
        source_versions = self._source_versions(normalized_scope)
        summary = self._search_repository.search_index_scope_summary(month=normalized_scope)
        if (
            isinstance(summary, dict)
            and str(summary.get("read_model_status") or "") == "fresh"
            and summary.get("source_versions") == source_versions
        ):
            return {
                "scope_key": normalized_scope,
                "row_count": max(int(summary.get("row_count") or 0), 0),
                "source_versions": source_versions,
                "skipped": True,
                "skip_reason": "source_versions_unchanged",
            }
        rows = self._rows_for_month(normalized_scope)
        source_versions = self._source_versions(normalized_scope)
        self._search_repository.save_search_index_rows(
            scope_key=normalized_scope,
            rows=rows,
            source_versions=source_versions,
        )
        return {
            "scope_key": normalized_scope,
            "row_count": len(rows),
            "source_versions": source_versions,
        }

    def _rows_for_month(self, month: str) -> list[dict[str, object]]:
        result: list[dict[str, object]] = []
        for context in self._canonical_repository.list_canonical_search_rows(
            scope_key=month
        ):
            row = context.get("row")
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or "").strip()
            source_kind = str(row.get("type") or "").strip()
            if not row_id or source_kind not in {"oa", "bank", "invoice"}:
                continue
            zone_hint = str(context.get("zone_hint") or "unpaired").strip()
            group_id = str(context.get("group_id") or "").strip()
            project_names = sorted(
                {
                    str(value).strip()
                    for value in list(context.get("project_names") or [])
                    if str(value).strip()
                }
                | {str(row.get("project_name") or "").strip()}
                - {""}
            )
            title, primary_meta, secondary_meta = _display_payload(
                row,
                project_names=project_names,
            )
            payload: dict[str, Any] = {
                "row_id": row_id,
                "record_type": source_kind,
                "month": month,
                "zone_hint": zone_hint,
                "matched_field": "全文",
                "title": title,
                "primary_meta": primary_meta,
                "secondary_meta": secondary_meta,
                "status_label": _status_label(zone_hint),
                "jump_target": {
                    "month": month,
                    "row_id": row_id,
                    "record_type": source_kind,
                    "zone_hint": zone_hint,
                },
            }
            if group_id:
                payload["group_id"] = group_id
                payload["jump_target"]["group_id"] = group_id
            result.append(
                {
                    "row_id": row_id,
                    "source_kind": source_kind,
                    "status": zone_hint,
                    "title": title,
                    "subtitle": secondary_meta,
                    "searchable_text": " ".join(
                        (
                            row_id,
                            title,
                            primary_meta,
                            secondary_meta,
                            " ".join(project_names),
                            json.dumps(
                                row,
                                ensure_ascii=False,
                                sort_keys=True,
                                default=str,
                            ),
                            group_id,
                        )
                    ).strip(),
                    "project_name": " / ".join(project_names) or None,
                    "counterparty_name": row.get("counterparty_name")
                    or row.get("seller_name")
                    or row.get("buyer_name"),
                    "amount": row.get("amount")
                    or row.get("debit_amount")
                    or row.get("credit_amount"),
                    "generated_at": row.get("updated_at"),
                    "payload": payload,
                }
            )
        return result

    def _source_versions(self, scope_key: str) -> dict[str, object]:
        payload = self._canonical_repository.workbench_search_source_versions(
            scope_key=scope_key
        )
        return dict(payload) if isinstance(payload, dict) else {}


def _display_payload(
    row: dict[str, Any],
    *,
    project_names: list[str],
) -> tuple[str, str, str]:
    row_type = str(row.get("type") or "")
    if row_type == "oa":
        return (
            str(row.get("project_name") or "OA"),
            _join_text(row.get("applicant"), row.get("counterparty_name"), row.get("amount")),
            _join_text(row.get("expense_type"), row.get("expense_content") or row.get("reason")),
        )
    if row_type == "bank":
        return (
            str(row.get("counterparty_name") or "银行流水"),
            _join_text(
                row.get("trade_time"),
                row.get("debit_amount") or row.get("credit_amount") or row.get("amount"),
            ),
            _join_text(row.get("summary"), row.get("remark")),
        )
    return (
        str(row.get("seller_name") or row.get("buyer_name") or "发票"),
        _join_text(
            row.get("invoice_no") or row.get("digital_invoice_no"),
            row.get("issue_date"),
            row.get("amount"),
        ),
        _join_text(" / ".join(project_names), row.get("invoice_type")),
    )


def _join_text(*parts: object) -> str:
    return " / ".join(str(part).strip() for part in parts if str(part or "").strip())


def _status_label(status: str) -> str:
    return {
        "paired": "已配对",
        "unpaired": "未配对",
        "ignored": "已忽略",
        "processed_exception": "已处理异常",
    }.get(status, status)
