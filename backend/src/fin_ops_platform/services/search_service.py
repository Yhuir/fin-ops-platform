from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import re
from time import monotonic
from typing import Any, Callable


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
COMPANY_SUFFIXES = (
    "有限责任公司",
    "股份有限公司",
    "有限公司",
    "公司",
)
TEXT_NORMALIZE_RE = re.compile(r"[\s,，()（）【】\[\]]+")
SUPPORTED_SCOPES = {"all", "oa", "bank", "invoice"}
SUPPORTED_STATUSES = {"paired", "open", "ignored", "processed_exception"}
STATUS_LABELS = {
    "paired": "已配对",
    "open": "未配对",
    "ignored": "已忽略",
    "processed_exception": "已处理异常",
}


class SearchService:
    def __init__(
        self,
        *,
        known_months_loader: Callable[[], list[str]],
        raw_workbench_loader: Callable[[str], dict[str, Any]] | None = None,
        grouped_workbench_loader: Callable[[str], dict[str, Any]] | None = None,
        ignored_rows_loader: Callable[[str], list[dict[str, Any]]] | None = None,
        cache_ttl_seconds: float = 30.0,
    ) -> None:
        self._known_months_loader = known_months_loader
        self._raw_workbench_loader = raw_workbench_loader
        self._grouped_workbench_loader = grouped_workbench_loader
        self._ignored_rows_loader = ignored_rows_loader
        self._cache_ttl_seconds = max(float(cache_ttl_seconds), 0.0)
        self._now = monotonic
        self._known_months_cache: tuple[float, list[str]] | None = None
        self._month_index_cache: dict[str, tuple[float, dict[str, list[dict[str, Any]]]]] = {}
        self._query_cache: dict[tuple[str, str, str, str, str, int], tuple[float, dict[str, Any]]] = {}

    def clear_cache(self) -> None:
        self._known_months_cache = None
        self._month_index_cache.clear()
        self._query_cache.clear()

    def search(
        self,
        *,
        q: str,
        scope: str = "all",
        month: str = "all",
        project_name: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        query = (q or "").strip()
        normalized_query = self._normalize_text(query)
        resolved_scope = scope if scope in SUPPORTED_SCOPES else "all"
        resolved_status = status if status in SUPPORTED_STATUSES else None
        resolved_limit = max(1, min(int(limit), 100))
        resolved_month = month if month == "all" or MONTH_RE.match(month or "") else "all"
        months = self._resolve_months(resolved_month)
        normalized_project_filter = self._normalize_text(project_name or "")

        if not query or not months:
            return self._empty_payload(
                query=query,
                scope=resolved_scope,
                month=resolved_month,
                project_name=project_name,
                status=resolved_status,
                limit=resolved_limit,
            )

        cache_key = (
            normalized_query,
            resolved_scope,
            resolved_month,
            normalized_project_filter,
            resolved_status or "",
            resolved_limit,
        )
        cached_payload = self._get_cached_query(cache_key)
        if cached_payload is not None:
            return cached_payload

        grouped_results: dict[str, list[dict[str, Any]]] = defaultdict(list)
        resolved_row_types = ("oa", "bank", "invoice") if resolved_scope == "all" else (resolved_scope,)

        for current_month in months:
            month_index = self._load_month_index(current_month)

            for row_type in resolved_row_types:
                if len(grouped_results[row_type]) >= resolved_limit:
                    continue

                for indexed_row in month_index.get(row_type, []):
                    if resolved_status and str(indexed_row["zone_hint"]) != resolved_status:
                        continue
                    if normalized_project_filter and normalized_project_filter not in indexed_row["project_names_normalized"]:
                        continue

                    matched_field = self._match_indexed_row(indexed_row, normalized_query)
                    if matched_field is None:
                        continue

                    grouped_results[row_type].append(
                        self._build_result(
                            row=indexed_row["row"],
                            month=str(indexed_row["month"]),
                            zone_hint=str(indexed_row["zone_hint"]),
                            matched_field=matched_field,
                            project_names=list(indexed_row["project_names"]),
                        )
                    )
                    if len(grouped_results[row_type]) >= resolved_limit:
                        break

            if self._has_reached_limits(grouped_results, resolved_row_types, resolved_limit):
                break

        oa_results = grouped_results["oa"][:resolved_limit]
        bank_results = grouped_results["bank"][:resolved_limit]
        invoice_results = grouped_results["invoice"][:resolved_limit]

        payload = {
            "query": query,
            "filters": {
                "scope": resolved_scope,
                "month": resolved_month,
                "project_name": project_name or None,
                "status": resolved_status,
                "limit": resolved_limit,
            },
            "summary": {
                "total": len(oa_results) + len(bank_results) + len(invoice_results),
                "oa": len(oa_results),
                "bank": len(bank_results),
                "invoice": len(invoice_results),
            },
            "oa_results": oa_results,
            "bank_results": bank_results,
            "invoice_results": invoice_results,
        }
        self._set_cached_query(cache_key, payload)
        return payload

    def _resolve_months(self, month: str | None) -> list[str]:
        if month and month != "all" and MONTH_RE.match(month):
            return [month]
        return list(self._load_known_months())

    def _load_known_months(self) -> list[str]:
        now = self._now()
        if self._cache_ttl_seconds > 0 and self._known_months_cache is not None:
            cached_at, months = self._known_months_cache
            if now - cached_at < self._cache_ttl_seconds:
                return list(months)

        months = sorted({candidate for candidate in self._known_months_loader() if MONTH_RE.match(candidate)}, reverse=True)
        if self._cache_ttl_seconds > 0:
            self._known_months_cache = (now, list(months))
        return months

    def _load_month_index(self, month: str) -> dict[str, list[dict[str, Any]]]:
        now = self._now()
        cached = self._month_index_cache.get(month)
        if self._cache_ttl_seconds > 0 and cached is not None:
            cached_at, index = cached
            if now - cached_at < self._cache_ttl_seconds:
                return index

        if self._grouped_workbench_loader is not None:
            grouped_payload = self._safe_load_payload(self._grouped_workbench_loader, month)
            ignored_rows = (
                self._safe_load_rows(self._ignored_rows_loader, month)
                if self._ignored_rows_loader is not None
                else []
            )
            index = self._index_grouped_payload(grouped_payload, month=month, ignored_rows=ignored_rows)
        else:
            if self._raw_workbench_loader is None:
                raise RuntimeError("SearchService requires either grouped_workbench_loader or raw_workbench_loader.")
            raw_payload = self._safe_load_payload(self._raw_workbench_loader, month)
            project_names_by_row_id = self._project_names_by_row_id(raw_payload)
            index = {"oa": [], "bank": [], "invoice": []}

            for section in ("paired", "open"):
                section_payload = raw_payload.get(section, {})
                if not isinstance(section_payload, dict):
                    continue

                for row_type in ("oa", "bank", "invoice"):
                    rows = section_payload.get(row_type, [])
                    if not isinstance(rows, list):
                        continue

                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        row_id = str(row.get("id"))
                        project_names = project_names_by_row_id.get(row_id, [])
                        index[row_type].append(
                            self._index_row(
                                row=row,
                                month=month,
                                zone_hint=self._zone_hint(section, row),
                                project_names=project_names,
                            )
                        )

        if self._cache_ttl_seconds > 0:
            self._month_index_cache[month] = (now, index)
        return index

    def _index_grouped_payload(
        self,
        grouped_payload: dict[str, Any],
        *,
        month: str,
        ignored_rows: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        index: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}

        for section in ("paired", "open"):
            section_payload = grouped_payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            groups = section_payload.get("groups", [])
            if not isinstance(groups, list):
                continue

            for group in groups:
                if not isinstance(group, dict):
                    continue
                group_project_names = self._project_names_from_group(group)
                for row_type in ("oa", "bank", "invoice"):
                    rows = group.get(f"{row_type}_rows", [])
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        index[row_type].append(
                            self._index_row(
                                row=row,
                                month=month,
                                zone_hint=self._zone_hint(section, row),
                                project_names=self._row_project_names(row, group_project_names),
                            )
                        )

        for row in ignored_rows:
            if not isinstance(row, dict):
                continue
            row_type = str(row.get("type"))
            if row_type not in index:
                continue
            index[row_type].append(
                self._index_row(
                    row=row,
                    month=month,
                    zone_hint="ignored",
                    project_names=self._row_project_names(row, []),
                )
            )

        return index

    def _index_row(
        self,
        *,
        row: dict[str, Any],
        month: str,
        zone_hint: str,
        project_names: list[str],
    ) -> dict[str, Any]:
        normalized_fields = [
            (field_name, normalized_value)
            for field_name, value in self._search_fields(row=row, month=month, project_names=project_names)
            if (normalized_value := self._normalize_text(value))
        ]
        return {
            "row": deepcopy(row),
            "month": month,
            "zone_hint": zone_hint,
            "project_names": list(project_names),
            "project_names_normalized": {
                normalized_name
                for candidate in project_names
                if (normalized_name := self._normalize_text(candidate))
            },
            "fields": normalized_fields,
        }

    def _project_names_by_row_id(self, raw_payload: dict[str, Any]) -> dict[str, list[str]]:
        project_names_by_row_id: dict[str, list[str]] = {}
        case_project_names: dict[str, set[str]] = defaultdict(set)
        case_row_ids: dict[str, set[str]] = defaultdict(set)

        for section in ("paired", "open"):
            section_payload = raw_payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue

            for row_type in ("oa", "bank", "invoice"):
                rows = section_payload.get(row_type, [])
                if not isinstance(rows, list):
                    continue
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    row_id = str(row.get("id"))
                    case_id = str(row.get("case_id") or "").strip()
                    project_name = str(row.get("project_name") or "").strip()

                    if project_name:
                        existing = set(project_names_by_row_id.get(row_id, []))
                        existing.add(project_name)
                        project_names_by_row_id[row_id] = sorted(existing)

                    if case_id:
                        case_row_ids[case_id].add(row_id)
                        if row_type == "oa" and project_name:
                            case_project_names[case_id].add(project_name)

        for case_id, row_ids in case_row_ids.items():
            project_names = sorted(case_project_names.get(case_id, set()))
            if not project_names:
                continue
            for row_id in row_ids:
                existing = set(project_names_by_row_id.get(row_id, []))
                existing.update(project_names)
                project_names_by_row_id[row_id] = sorted(existing)

        return project_names_by_row_id

    @staticmethod
    def _project_names_from_group(group: dict[str, Any]) -> list[str]:
        project_names: set[str] = set()
        for row in group.get("oa_rows", []):
            if not isinstance(row, dict):
                continue
            project_name = str(row.get("project_name") or "").strip()
            if project_name:
                project_names.add(project_name)
        return sorted(project_names)

    @staticmethod
    def _row_project_names(row: dict[str, Any], group_project_names: list[str]) -> list[str]:
        resolved = set(group_project_names)
        project_name = str(row.get("project_name") or "").strip()
        if project_name:
            resolved.add(project_name)
        return sorted(resolved)

    @staticmethod
    def _has_reached_limits(
        grouped_results: dict[str, list[dict[str, Any]]],
        row_types: tuple[str, ...],
        limit: int,
    ) -> bool:
        return all(len(grouped_results[row_type]) >= limit for row_type in row_types)

    @staticmethod
    def _safe_load_payload(loader: Callable[[str], dict[str, Any]], month: str) -> dict[str, Any]:
        try:
            payload = loader(month)
        except KeyError:
            return {"month": month, "paired": {"oa": [], "bank": [], "invoice": []}, "open": {"oa": [], "bank": [], "invoice": []}}
        return payload if isinstance(payload, dict) else {"month": month, "paired": {"oa": [], "bank": [], "invoice": []}, "open": {"oa": [], "bank": [], "invoice": []}}

    @staticmethod
    def _safe_load_rows(loader: Callable[[str], list[dict[str, Any]]], month: str) -> list[dict[str, Any]]:
        try:
            rows = loader(month)
        except KeyError:
            return []
        return rows if isinstance(rows, list) else []

    @staticmethod
    def _zone_hint(section: str, row: dict[str, Any]) -> str:
        if bool(row.get("ignored")):
            return "ignored"
        if bool(row.get("handled_exception")):
            return "processed_exception"
        return "paired" if section == "paired" else "open"

    @staticmethod
    def _match_indexed_row(indexed_row: dict[str, Any], normalized_query: str) -> str | None:
        if not normalized_query:
            return None
        for field_name, normalized_value in indexed_row["fields"]:
            if normalized_query in normalized_value:
                return field_name
        return None

    def _search_fields(
        self,
        *,
        row: dict[str, Any],
        month: str,
        project_names: list[str],
    ) -> list[tuple[str, Any]]:
        row_type = str(row.get("type"))
        detail_fields = row.get("detail_fields", {})
        summary_fields = row.get("summary_fields", {})
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        summary_fields = summary_fields if isinstance(summary_fields, dict) else {}

        if row_type == "oa":
            return [
                ("OA单号", detail_fields.get("OA单号") or row.get("id")),
                ("申请人", row.get("applicant")),
                ("项目名称", row.get("project_name")),
                ("费用类型", row.get("expense_type") or detail_fields.get("费用类型")),
                ("费用内容", row.get("expense_content") or detail_fields.get("费用内容")),
                ("对方户名", row.get("counterparty_name")),
                ("申请事由", row.get("reason")),
                ("金额", row.get("amount")),
                ("月份", month),
            ]

        if row_type == "bank":
            amount = row.get("debit_amount") or row.get("credit_amount")
            return [
                ("交易流水ID", row.get("id")),
                ("对方户名", row.get("counterparty_name")),
                ("金额", amount),
                ("支付账户", row.get("payment_account_label") or summary_fields.get("支付账户") or summary_fields.get("收款账户")),
                ("企业流水号", detail_fields.get("企业流水号")),
                ("账户明细编号-交易流水号", detail_fields.get("账户明细编号-交易流水号")),
                ("凭证号", detail_fields.get("凭证号")),
                ("账号", detail_fields.get("账号")),
                ("交易时间", row.get("trade_time")),
                ("备注", row.get("remark") or summary_fields.get("备注")),
                ("摘要", detail_fields.get("摘要")),
                ("资金方向", row.get("direction")),
                ("项目名称", " / ".join(project_names)),
                ("月份", month),
            ]

        return [
            ("发票号码", detail_fields.get("发票号码")),
            ("发票代码", detail_fields.get("发票代码")),
            ("数电发票号码", detail_fields.get("数电发票号码")),
            ("销方名称", row.get("seller_name")),
            ("购方名称", row.get("buyer_name")),
            ("销方识别号", row.get("seller_tax_no")),
            ("购方识别号", row.get("buyer_tax_no")),
            ("金额", row.get("amount")),
            ("开票日期", row.get("issue_date")),
            ("发票类型", row.get("invoice_type")),
            ("项目名称", " / ".join(project_names)),
            ("月份", month),
        ]

    def _build_result(
        self,
        *,
        row: dict[str, Any],
        month: str,
        zone_hint: str,
        matched_field: str,
        project_names: list[str],
    ) -> dict[str, Any]:
        row_type = str(row.get("type"))
        title, primary_meta, secondary_meta = self._display_payload(row=row, project_names=project_names)
        return {
            "row_id": str(row.get("id", "")),
            "record_type": row_type,
            "month": month,
            "zone_hint": zone_hint,
            "matched_field": matched_field,
            "title": title,
            "primary_meta": self._join_meta(primary_meta),
            "secondary_meta": self._join_meta(secondary_meta),
            "status_label": STATUS_LABELS[zone_hint],
            "jump_target": {
                "month": month,
                "row_id": str(row.get("id", "")),
                "record_type": row_type,
                "zone_hint": zone_hint,
            },
        }

    @staticmethod
    def _display_payload(row: dict[str, Any], *, project_names: list[str]) -> tuple[str, list[str], list[str]]:
        row_type = str(row.get("type"))
        if row_type == "oa":
            title = str(row.get("project_name") or "OA")
            primary_meta = [
                str(row.get("applicant") or "—"),
                str(row.get("counterparty_name") or "—"),
                str(row.get("amount") or "—"),
            ]
            secondary_meta = [
                str(row.get("expense_type") or "—"),
                str(row.get("expense_content") or row.get("reason") or "—"),
            ]
            return title, primary_meta, secondary_meta

        if row_type == "bank":
            title = str(row.get("counterparty_name") or "银行流水")
            amount = row.get("debit_amount") or row.get("credit_amount") or "—"
            primary_meta = [
                str(row.get("trade_time") or "—"),
                str(amount),
                str(row.get("direction") or "—"),
            ]
            secondary_meta = [
                str(row.get("payment_account_label") or "—"),
                " / ".join(project_names) or str(row.get("remark") or "—"),
            ]
            return title, primary_meta, secondary_meta

        detail_fields = row.get("detail_fields", {})
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        title = str(detail_fields.get("发票号码") or detail_fields.get("数电发票号码") or row.get("seller_name") or "发票")
        primary_meta = [
            str(row.get("seller_name") or "—"),
            str(row.get("buyer_name") or "—"),
            str(row.get("amount") or "—"),
        ]
        secondary_meta = [
            str(row.get("issue_date") or "—"),
            str(row.get("invoice_type") or "—"),
            " / ".join(project_names) or "—",
        ]
        return title, primary_meta, secondary_meta

    @staticmethod
    def _join_meta(parts: list[str]) -> str:
        normalized_parts = [part.strip() for part in parts if part and part.strip()]
        return " / ".join(normalized_parts) if normalized_parts else "—"

    def _get_cached_query(self, cache_key: tuple[str, str, str, str, str, int]) -> dict[str, Any] | None:
        now = self._now()
        cached = self._query_cache.get(cache_key)
        if cached is None:
            return None
        cached_at, payload = cached
        if self._cache_ttl_seconds > 0 and now - cached_at >= self._cache_ttl_seconds:
            self._query_cache.pop(cache_key, None)
            return None
        return deepcopy(payload)

    def _set_cached_query(self, cache_key: tuple[str, str, str, str, str, int], payload: dict[str, Any]) -> None:
        if self._cache_ttl_seconds <= 0:
            return
        self._query_cache[cache_key] = (self._now(), deepcopy(payload))

    @staticmethod
    def _normalize_text(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        for suffix in COMPANY_SUFFIXES:
            text = text.replace(suffix, "")
        text = TEXT_NORMALIZE_RE.sub("", text)
        return text

    @staticmethod
    def _empty_payload(
        *,
        query: str,
        scope: str,
        month: str,
        project_name: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, Any]:
        return {
            "query": query,
            "filters": {
                "scope": scope,
                "month": month,
                "project_name": project_name,
                "status": status,
                "limit": limit,
            },
            "summary": {"total": 0, "oa": 0, "bank": 0, "invoice": 0},
            "oa_results": [],
            "bank_results": [],
            "invoice_results": [],
        }
