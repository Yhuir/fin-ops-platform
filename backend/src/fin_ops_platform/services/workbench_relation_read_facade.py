from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.common import text, text_list


FRESH_WORKBENCH_RELATION_STATUS = "fresh"
NON_FRESH_WORKBENCH_RELATION_STATUSES = {"unavailable", "missing", "stale"}


class WorkbenchRelationReadFacade:
    """Direct canonical read boundary for OA/bank/invoice relation context."""

    def __init__(self, *, relation_service: Any) -> None:
        self._relation_service = relation_service
        self._last_result: dict[str, Any] = _facade_result(status="missing")

    @property
    def last_source_versions(self) -> dict[str, Any]:
        source_versions = self._last_result.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def get_by_row_ids(
        self,
        row_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
        month_hint: str | None = None,
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = require_fresh, reason
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(row_ids or []))
        if not normalized_ids:
            return self._remember(_facade_result(status=FRESH_WORKBENCH_RELATION_STATUS))
        direct_reader = getattr(self._relation_service, "active_relations_for_row_ids", None)
        scope_keys = _fallback_scope_keys(month_hint=month_hint, scope_keys_hint=scope_keys_hint)
        if not callable(direct_reader):
            return self._remember(_unavailable_result(scope_keys=scope_keys, stale_reasons=["relation_service_unavailable"]))
        return self._remember(
            _direct_relation_payload(
                relations=direct_reader(normalized_ids),
                requested_row_ids=normalized_ids,
                scope_keys=scope_keys,
            )
        )

    def list_by_month(
        self,
        month: str,
        *,
        row_types: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_read",
    ) -> dict[str, Any]:
        _ = require_fresh, reason
        normalized_month = text(month) or ""
        direct_reader = getattr(self._relation_service, "list_active_relations", None)
        if not normalized_month or not callable(direct_reader):
            return self._remember(
                _unavailable_result(
                    scope_keys=[normalized_month] if normalized_month else [],
                    stale_reasons=["month_required" if not normalized_month else "relation_service_unavailable"],
                )
            )
        row_type_filter = set(_dedupe_preserve_order(text(value) for value in list(row_types or [])))
        relations = [
            relation
            for relation in list(direct_reader() or [])
            if isinstance(relation, dict)
            and _relation_matches_month(relation, normalized_month)
            and _relation_matches_row_types(relation, row_type_filter)
        ]
        return self._remember(_direct_relation_payload(relations=relations, scope_keys=[normalized_month]))

    def source_versions_for_month(
        self,
        month: str,
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_source_versions",
    ) -> dict[str, Any]:
        _ = require_fresh, reason
        normalized_month = text(month) or ""
        direct_reader = getattr(self._relation_service, "list_active_relations", None)
        if not normalized_month or not callable(direct_reader):
            return self._remember(
                _unavailable_result(
                    scope_keys=[normalized_month] if normalized_month else [],
                    stale_reasons=["month_required" if not normalized_month else "relation_service_unavailable"],
                )
            )
        relations = [
            relation
            for relation in list(direct_reader() or [])
            if isinstance(relation, dict) and _relation_matches_month(relation, normalized_month)
        ]
        return self._remember(
            _facade_result(
                status=FRESH_WORKBENCH_RELATION_STATUS,
                source_versions=_direct_source_versions(relations),
                scope_keys=[normalized_month],
            )
        )

    def list_unlinked(
        self,
        month: str,
        *,
        row_types: list[str] | None = None,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_unlinked_read",
    ) -> dict[str, Any]:
        _ = row_types, require_fresh, reason
        normalized_month = text(month) or ""
        direct_reader = getattr(self._relation_service, "list_active_relations", None)
        if not normalized_month or not callable(direct_reader):
            return self._remember(
                _unavailable_result(
                    scope_keys=[normalized_month] if normalized_month else [],
                    stale_reasons=["month_required" if not normalized_month else "relation_service_unavailable"],
                )
            )
        relations = [
            relation
            for relation in list(direct_reader() or [])
            if isinstance(relation, dict) and _relation_matches_month(relation, normalized_month)
        ]
        return self._remember(
            _facade_result(
                status=FRESH_WORKBENCH_RELATION_STATUS,
                source_versions=_direct_source_versions(relations),
                scope_keys=[normalized_month],
            )
        )

    def relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        require_fresh: bool = True,
        reason: str = "downstream_workbench_relation_group_read",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        _ = require_fresh, reason
        normalized_ids = _dedupe_preserve_order(text(value) for value in list(group_ids or []))
        if not normalized_ids:
            return self._remember(_facade_result(status=FRESH_WORKBENCH_RELATION_STATUS))
        direct_reader = getattr(self._relation_service, "list_active_relations", None)
        scope_keys = _fallback_scope_keys(scope_keys_hint=scope_keys_hint)
        if not callable(direct_reader):
            return self._remember(_unavailable_result(scope_keys=scope_keys, stale_reasons=["relation_service_unavailable"]))
        requested = set(normalized_ids)
        relations = [
            relation
            for relation in list(direct_reader() or [])
            if isinstance(relation, dict) and text(relation.get("case_id")) in requested
        ]
        return self._remember(_direct_relation_payload(relations=relations, scope_keys=scope_keys))

    def _remember(self, result: dict[str, Any]) -> dict[str, Any]:
        self._last_result = result
        return result


def _facade_result(
    *,
    status: str,
    rows: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    source_versions: dict[str, Any] | None = None,
    scope_keys: list[str] | None = None,
    stale_reasons: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": _facade_status(status),
        "rows": list(rows or []),
        "groups": list(groups or []),
        "source_versions": dict(source_versions or {}),
        "scope_keys": list(scope_keys or []),
        "stale_reasons": list(stale_reasons or []),
    }


def _facade_status(value: object) -> str:
    normalized = text(value) or FRESH_WORKBENCH_RELATION_STATUS
    if normalized == FRESH_WORKBENCH_RELATION_STATUS or normalized in NON_FRESH_WORKBENCH_RELATION_STATUSES:
        return normalized
    return "stale"


def _unavailable_result(*, scope_keys: list[str], stale_reasons: list[str]) -> dict[str, Any]:
    return _facade_result(status="unavailable", scope_keys=scope_keys, stale_reasons=stale_reasons)


def _direct_relation_payload(
    *,
    relations: Any,
    requested_row_ids: list[str] | None = None,
    scope_keys: list[str] | None = None,
) -> dict[str, Any]:
    relation_list = [relation for relation in list(relations or []) if isinstance(relation, dict)]
    rows: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    seen_row_ids: set[str] = set()
    requested = _dedupe_preserve_order(text(value) for value in list(requested_row_ids or []))
    requested_set = set(requested)

    for relation in relation_list:
        groups.append(_group_from_relation(relation))
        row_ids = text_list(relation.get("row_ids"))
        row_types = text_list(relation.get("row_types"))
        for index, row_id in enumerate(row_ids):
            if requested_set and row_id not in requested_set:
                continue
            rows.append(_row_from_relation(relation, row_id=row_id, row_type=_row_type_at(row_types, index)))
            seen_row_ids.add(row_id)

    for row_id in requested:
        if row_id in seen_row_ids:
            continue
        rows.append(
            {
                "row_id": row_id,
                "row_type": "",
                "scope_key": "",
                "relation_status": "unlinked",
                "group_ids": [],
                "linked_oa": [],
                "linked_bank_transactions": [],
                "linked_input_invoices": [],
                "linked_output_invoices": [],
                "source_versions": _direct_source_versions(relation_list),
                "payload": {},
            }
        )

    resolved_scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys or []))
    if not resolved_scope_keys:
        resolved_scope_keys = _dedupe_preserve_order(text(relation.get("month_scope")) for relation in relation_list)
    return _facade_result(
        status=FRESH_WORKBENCH_RELATION_STATUS,
        rows=rows,
        groups=groups,
        source_versions=_direct_source_versions(relation_list),
        scope_keys=resolved_scope_keys,
    )


def _group_from_relation(relation: dict[str, Any]) -> dict[str, Any]:
    row_ids = text_list(relation.get("row_ids"))
    row_types = text_list(relation.get("row_types"))
    case_id = text(relation.get("case_id"))
    return {
        "group_id": case_id,
        "scope_key": text(relation.get("month_scope")) or "all",
        "relation_source": text(relation.get("relation_source")) or text(relation.get("relation_mode")) or "canonical",
        "relation_kind": text(relation.get("relation_kind")) or text(relation.get("relation_mode")) or "workbench_relation",
        "relation_status": _relation_status(relation),
        "oa_row_ids": [row_id for index, row_id in enumerate(row_ids) if _row_type_at(row_types, index) == "oa"],
        "bank_transaction_ids": [
            row_id for index, row_id in enumerate(row_ids) if _row_type_at(row_types, index) in {"bank", "bank_transaction"}
        ],
        "input_invoice_ids": [
            row_id for index, row_id in enumerate(row_ids) if _row_type_at(row_types, index) in {"invoice", "input_invoice"}
        ],
        "output_invoice_ids": [
            row_id for index, row_id in enumerate(row_ids) if _row_type_at(row_types, index) == "output_invoice"
        ],
        "source_versions": _direct_source_versions([relation]),
        "payload": dict(relation),
    }


def _row_from_relation(relation: dict[str, Any], *, row_id: str, row_type: str) -> dict[str, Any]:
    return {
        "row_id": row_id,
        "row_type": row_type,
        "scope_key": text(relation.get("month_scope")) or "all",
        "relation_status": _relation_status(relation),
        "group_ids": [text(relation.get("case_id"))] if text(relation.get("case_id")) else [],
        "linked_oa": [],
        "linked_bank_transactions": [],
        "linked_input_invoices": [],
        "linked_output_invoices": [],
        "source_versions": _direct_source_versions([relation]),
        "payload": dict(relation),
    }


def _relation_status(relation: dict[str, Any]) -> str:
    status = text(relation.get("status"))
    if status == "active":
        return "linked"
    return status or "linked"


def _row_type_at(row_types: list[str], index: int) -> str:
    if index < 0 or index >= len(row_types):
        return ""
    row_type = text(row_types[index])
    if row_type == "bank":
        return "bank_transaction"
    if row_type == "invoice":
        return "input_invoice"
    return row_type


def _relation_matches_month(relation: dict[str, Any], month: str) -> bool:
    month_scope = text(relation.get("month_scope"))
    if not month_scope or month_scope == "all":
        return False
    return month_scope == month or month_scope.startswith(f"{month}-")


def _relation_matches_row_types(relation: dict[str, Any], row_type_filter: set[str]) -> bool:
    if not row_type_filter:
        return True
    normalized_filter = {_row_type_at([row_type], 0) for row_type in row_type_filter}
    return bool(normalized_filter.intersection({_row_type_at([row_type], 0) for row_type in text_list(relation.get("row_types"))}))


def _direct_source_versions(relations: list[dict[str, Any]]) -> dict[str, Any]:
    case_ids = _dedupe_preserve_order(text(relation.get("case_id")) for relation in list(relations or []))
    return {
        "workbench_relation_source": "canonical",
        "workbench_relation_count": len(case_ids),
        "workbench_relation_case_ids": case_ids,
    }


def _fallback_scope_keys(*, month_hint: str | None = None, scope_keys_hint: list[str] | None = None) -> list[str]:
    scope_keys = _dedupe_preserve_order(text(value) for value in list(scope_keys_hint or []))
    if scope_keys:
        return scope_keys
    month = text(month_hint)
    return [month] if month else []


def _dedupe_preserve_order(values: Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result
