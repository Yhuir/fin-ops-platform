from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from typing import Any, Callable

from fin_ops_platform.services.no_oa_bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_RELATION_MODE,
)
ROW_TYPES = ("oa", "bank", "invoice")
DISPLAY_ROLES = frozenset({"summary", "collapsed_summary"})
LEGACY_CANDIDATE_CASE_PREFIXES = ("candidate:", "decision:", "temp:")


class WorkbenchRelationGroupingService:
    """Project canonical rows into the exact active-relation/unpaired partition.

    The service is pure: callers own canonical identity arbitration and all I/O.
    Decorations may change display fields, but never membership or zone.
    """

    def group_payload(
        self,
        month: str,
        *,
        rows_by_id: dict[str, dict[str, Any]],
        active_relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        canonical_rows, display_rows = self._normalize_rows(rows_by_id)
        relations = self._normalize_relations(active_relations)
        ownership = self._active_ownership(relations, canonical_rows)

        paired_groups = [
            self._relation_group(relation, canonical_rows, display_rows)
            for relation in relations
        ]
        paired_groups = [group for group in paired_groups if self._group_member_count(group)]

        unpaired_groups = [
            self._unpaired_group(row)
            for row_id, row in sorted(canonical_rows.items(), key=self._row_sort_key)
            if row_id not in ownership
        ]

        self._assert_partition(canonical_rows, paired_groups, unpaired_groups, ownership)
        counts = {row_type: 0 for row_type in ROW_TYPES}
        for row in canonical_rows.values():
            counts[str(row["type"])] += 1
        return {
            "month": str(month or "").strip(),
            "summary": {
                "oa_count": counts["oa"],
                "bank_count": counts["bank"],
                "invoice_count": counts["invoice"],
                "paired_count": len(paired_groups),
                "unpaired_count": len(unpaired_groups),
                "exception_count": sum(1 for group in unpaired_groups if self._group_has_danger(group)),
            },
            "paired": {"groups": paired_groups},
            "unpaired": {"groups": unpaired_groups},
        }

    def _normalize_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
    ) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
        if not isinstance(rows_by_id, dict):
            raise TypeError("rows_by_id must be a dict.")
        canonical: dict[str, dict[str, Any]] = {}
        display_by_case: dict[str, list[dict[str, Any]]] = {}
        identities: dict[tuple[str, str], str] = {}
        for raw_row_id, raw_row in rows_by_id.items():
            if not isinstance(raw_row, dict):
                raise ValueError("Workbench rows must be dictionaries.")
            row = deepcopy(raw_row)
            row_id = str(row.get("id") or raw_row_id or "").strip()
            row_type = str(row.get("type") or "").strip().lower()
            if not row_id or row_type not in ROW_TYPES:
                raise ValueError("Workbench canonical rows require an id and oa/bank/invoice type.")
            row["id"] = row_id
            row["type"] = row_type
            display_role = str(row.get("workbench_display_role") or "").strip()
            if display_role in DISPLAY_ROLES:
                case_id = str(row.get("case_id") or "").strip()
                if case_id:
                    display_by_case.setdefault(case_id, []).append(row)
                continue
            identity = str(row.get("object_identity_key") or "").strip()
            if not identity:
                raise ValueError(f"Workbench canonical row {row_id} is missing object_identity_key.")
            typed_identity = (row_type, identity)
            prior = identities.setdefault(typed_identity, row_id)
            if prior != row_id:
                raise ValueError(
                    f"Workbench canonical identity {row_type}:{identity} is represented by multiple rows."
                )
            if row_id in canonical:
                raise ValueError(f"Duplicate Workbench row id: {row_id}.")
            canonical[row_id] = row
        return canonical, display_by_case

    @staticmethod
    def _normalize_relations(active_relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(active_relations, list):
            raise TypeError("active_relations must be a list.")
        normalized: list[dict[str, Any]] = []
        seen_cases: set[str] = set()
        for raw_relation in active_relations:
            if not isinstance(raw_relation, dict):
                raise ValueError("Active Workbench relations must be dictionaries.")
            relation = deepcopy(raw_relation)
            case_id = str(relation.get("case_id") or "").strip()
            status = str(relation.get("status") or "active").strip()
            if status != "active":
                continue
            row_ids = tuple(dict.fromkeys(str(item).strip() for item in list(relation.get("row_ids") or []) if str(item).strip()))
            if not case_id or not row_ids:
                raise ValueError("Active Workbench relations require case_id and row_ids.")
            if case_id in seen_cases:
                raise ValueError(f"Duplicate active Workbench relation case id: {case_id}.")
            seen_cases.add(case_id)
            relation["case_id"] = case_id
            relation["row_ids"] = list(row_ids)
            relation["status"] = "active"
            normalized.append(relation)
        return sorted(normalized, key=lambda item: str(item["case_id"]))

    @staticmethod
    def _active_ownership(
        relations: list[dict[str, Any]],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, str]:
        ownership: dict[str, str] = {}
        for relation in relations:
            case_id = str(relation["case_id"])
            missing = [row_id for row_id in relation["row_ids"] if row_id not in rows_by_id]
            if missing:
                raise ValueError(
                    f"Active Workbench relation {case_id} references unavailable canonical rows: {','.join(missing)}."
                )
            for row_id in relation["row_ids"]:
                prior = ownership.setdefault(row_id, case_id)
                if prior != case_id:
                    raise ValueError(f"Workbench row {row_id} belongs to multiple active relations.")
        return ownership

    def _relation_group(
        self,
        relation: dict[str, Any],
        rows_by_id: dict[str, dict[str, Any]],
        display_rows_by_case: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        case_id = str(relation["case_id"])
        rows = [self._paired_row(rows_by_id[row_id], relation) for row_id in relation["row_ids"]]
        group = self._base_group(
            group_id=f"case:{case_id}",
            group_type="relation",
            reason="active_formal_relation",
            zone="paired",
            rows=rows,
        )
        relation_mode = str(relation.get("relation_mode") or "manual_confirmed").strip() or "manual_confirmed"
        group["relation_mode"] = relation_mode
        group["case_id"] = case_id
        group["can_withdraw"] = True
        if isinstance(relation.get("amount_check"), dict):
            group["amount_check"] = deepcopy(relation["amount_check"])
        special_metadata = relation.get("special_metadata")
        if isinstance(special_metadata, dict):
            group["special_metadata"] = deepcopy(special_metadata)
        display_tags = self._display_tags(rows, relation)
        if display_tags:
            group["display_tags"] = display_tags
        self._apply_display_summary(group, display_rows_by_case.get(case_id, []), zone="paired")
        if relation_mode in {NO_OA_BANK_BATCH_RELATION_MODE, BANK_FLOW_RULE_BATCH_RELATION_MODE}:
            self._apply_bank_batch_summary(group, relation_mode=relation_mode)
        return group

    @staticmethod
    def _paired_row(row: dict[str, Any], relation: dict[str, Any]) -> dict[str, Any]:
        resolved = deepcopy(row)
        resolved["status"] = "paired"
        resolved["case_id"] = str(relation["case_id"])
        resolved["relation_mode"] = str(relation.get("relation_mode") or "manual_confirmed")
        return resolved

    def _unpaired_group(self, row: dict[str, Any]) -> dict[str, Any]:
        resolved = self._unpaired_row(row)
        display_row = deepcopy(resolved)
        resolved.pop("etc_invoice_detail_rows", None)
        row_type = str(resolved["type"])
        identity = str(resolved["object_identity_key"])
        digest = sha256(f"{row_type}\0{identity}".encode("utf-8")).hexdigest()[:24]
        group = self._base_group(
            group_id=f"unpaired:{row_type}:{digest}",
            group_type="unpaired",
            reason="no_active_relation",
            zone="unpaired",
            rows=[resolved],
        )
        if str(display_row.get("source_kind") or "").strip() == "etc_invoice_summary":
            self._apply_display_summary(group, [display_row], zone="unpaired")
        return group

    @staticmethod
    def _unpaired_row(row: dict[str, Any]) -> dict[str, Any]:
        resolved = deepcopy(row)
        resolved["status"] = "unpaired"
        case_id = str(resolved.get("case_id") or "").strip()
        if case_id.startswith(LEGACY_CANDIDATE_CASE_PREFIXES):
            resolved.pop("case_id", None)
            resolved.pop("relation_mode", None)
            resolved.pop("relation_amount_check", None)
        return resolved

    @staticmethod
    def _base_group(
        *,
        group_id: str,
        group_type: str,
        reason: str,
        zone: str,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        by_type = {row_type: [] for row_type in ROW_TYPES}
        for row in rows:
            by_type[str(row["type"])].append(row)
        return {
            "group_id": group_id,
            "group_type": group_type,
            "match_confidence": "high" if zone == "paired" else "none",
            "reason": reason,
            "zone": zone,
            "status": zone,
            "oa_rows": by_type["oa"],
            "bank_rows": by_type["bank"],
            "invoice_rows": by_type["invoice"],
        }

    @staticmethod
    def _display_tags(rows: list[dict[str, Any]], relation: dict[str, Any]) -> list[str]:
        tags: list[str] = []
        for value in [*list(relation.get("display_tags") or []), *[tag for row in rows for tag in list(row.get("display_tags") or row.get("tags") or [])]]:
            text = str(value or "").strip()
            if text and text not in tags:
                tags.append(text)
        return tags

    @staticmethod
    def _apply_display_summary(
        group: dict[str, Any],
        display_rows: list[dict[str, Any]],
        *,
        zone: str,
    ) -> None:
        if not display_rows:
            return
        summary = deepcopy(sorted(display_rows, key=lambda row: str(row.get("id") or ""))[0])
        details = [deepcopy(row) for row in list(summary.pop("etc_invoice_detail_rows", []) or []) if isinstance(row, dict)]
        summary["status"] = zone
        for detail in details:
            detail["status"] = zone
        group["display_mode"] = "collapsed_summary"
        group["default_collapsed"] = True
        group["summary_row"] = summary
        if details:
            group["collapsed_rows"] = {"invoice": details}
            group["collapsed_row_counts"] = {"invoice": len(details)}

    @staticmethod
    def _apply_bank_batch_summary(group: dict[str, Any], *, relation_mode: str) -> None:
        bank_rows = [deepcopy(row) for row in list(group.get("bank_rows") or [])]
        if len(bank_rows) < 2 or group.get("oa_rows") or group.get("invoice_rows"):
            return
        representative = deepcopy(bank_rows[0])
        metadata = representative.get("special_metadata")
        metadata = deepcopy(metadata) if isinstance(metadata, dict) else {}
        try:
            total = abs(Decimal(str(metadata.get("total_amount"))))
        except (InvalidOperation, TypeError, ValueError):
            total = sum((WorkbenchRelationGroupingService._row_amount(row) for row in bank_rows), Decimal("0.00"))
        case_id = str(group.get("case_id") or "")
        label = "流水规则批次" if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE else "免OA流水"
        actions = [
            str(action)
            for action in list(representative.get("available_actions") or [])
            if str(action)
        ]
        for action in ("detail", "withdraw_no_oa_batch"):
            if action not in actions:
                actions.append(action)
        summary = representative
        summary.update(
            {
                "id": f"relation_summary:{case_id}",
                "type": "bank",
                "source_kind": (
                    "bank_flow_rule_batch_summary"
                    if relation_mode == BANK_FLOW_RULE_BATCH_RELATION_MODE
                    else "no_oa_bank_batch_summary"
                ),
                "label": label,
                "amount": f"{total:.2f}",
                "debit_amount": f"{total:.2f}",
                "credit_amount": "",
                "status": "paired",
                "case_id": case_id,
                "relation_mode": relation_mode,
                "available_actions": actions,
            }
        )
        if metadata:
            summary["special_metadata"] = metadata
        group["display_mode"] = "collapsed_summary"
        group["default_collapsed"] = True
        group["summary_row"] = summary
        group["collapsed_rows"] = {"bank": bank_rows}
        group["collapsed_row_counts"] = {"bank": len(bank_rows)}
        group["bank_rows"] = [deepcopy(summary)]

    @staticmethod
    def _row_amount(row: dict[str, Any]) -> Decimal:
        for field in ("amount_value", "amount", "debit_amount", "credit_amount", "total_with_tax"):
            value = row.get(field)
            if value in (None, ""):
                continue
            try:
                return abs(Decimal(str(value).replace(",", "")))
            except InvalidOperation:
                continue
        return Decimal("0.00")

    @staticmethod
    def _group_member_count(group: dict[str, Any]) -> int:
        if isinstance(group.get("collapsed_rows"), dict):
            collapsed = group["collapsed_rows"]
            return sum(len(list(collapsed.get(row_type) or [])) for row_type in ROW_TYPES)
        return sum(len(list(group.get(f"{row_type}_rows") or [])) for row_type in ROW_TYPES)

    @staticmethod
    def _group_has_danger(group: dict[str, Any]) -> bool:
        return any(
            str(relation.get("tone") or "") == "danger"
            for row_type in ROW_TYPES
            for row in list(group.get(f"{row_type}_rows") or [])
            if isinstance(row, dict)
            for field in ("oa_bank_relation", "invoice_relation", "invoice_bank_relation")
            if isinstance((relation := row.get(field)), dict)
        )

    @staticmethod
    def _row_sort_key(item: tuple[str, dict[str, Any]]) -> tuple[int, str, str]:
        row_id, row = item
        return ROW_TYPES.index(str(row["type"])), str(row["object_identity_key"]), row_id

    @staticmethod
    def _member_identities(groups: list[dict[str, Any]]) -> set[tuple[str, str]]:
        identities: set[tuple[str, str]] = set()
        for group in groups:
            collapsed_rows = group.get("collapsed_rows") if isinstance(group.get("collapsed_rows"), dict) else {}
            for row_type in ROW_TYPES:
                rows = [
                    *list(group.get(f"{row_type}_rows") or []),
                    *list(collapsed_rows.get(row_type) or []),
                ]
                for row in rows:
                    if not isinstance(row, dict) or str(row.get("workbench_display_role") or "") in DISPLAY_ROLES:
                        continue
                    identity = str(row.get("object_identity_key") or "").strip()
                    if identity:
                        identities.add((row_type, identity))
        return identities

    def _assert_partition(
        self,
        canonical_rows: dict[str, dict[str, Any]],
        paired_groups: list[dict[str, Any]],
        unpaired_groups: list[dict[str, Any]],
        ownership: dict[str, str],
    ) -> None:
        canonical = {(str(row["type"]), str(row["object_identity_key"])) for row in canonical_rows.values()}
        active = {
            (str(canonical_rows[row_id]["type"]), str(canonical_rows[row_id]["object_identity_key"]))
            for row_id in ownership
        }
        paired = self._member_identities(paired_groups)
        unpaired = self._member_identities(unpaired_groups)
        if paired != active or unpaired != canonical - active or paired.intersection(unpaired) or paired.union(unpaired) != canonical:
            raise AssertionError("Workbench relation visibility partition invariant failed.")


class WorkbenchRelationPreviewGroupingService:
    """Pure preview projection for formal relations and selected unpaired rows."""

    def __init__(
        self,
        *,
        serialize_value: Callable[[object], object],
        row_type_for_row_id: Callable[[str], str],
        derive_row_tags: Callable[[dict[str, object], dict[str, object], dict[str, object]], list[str]],
    ) -> None:
        self._serialize_value = serialize_value
        self._row_type_for_row_id = row_type_for_row_id
        self._derive_row_tags = derive_row_tags

    def group_relations(
        self,
        relations: list[dict[str, object]],
        *,
        selected_rows: list[dict[str, object]],
        ungrouped_selected_rows: str = "single",
    ) -> list[dict[str, object]]:
        if ungrouped_selected_rows not in {"single", "individual", "separate"}:
            raise ValueError(
                "ungrouped_selected_rows must be single, individual, or separate."
            )
        rows_by_id = {
            str(row.get("id", "")): self._serialized_mapping(row)
            for row in selected_rows
        }
        groups: list[dict[str, object]] = []
        grouped_row_ids: set[str] = set()
        for relation in relations:
            case_id = str(relation.get("case_id") or "")
            group: dict[str, object] = {
                "group_id": f"case:{case_id}",
                "group_type": "relation",
                "match_confidence": "high",
                "reason": "active_formal_relation",
                "zone": "paired",
                "status": "paired",
                "relation_mode": str(relation.get("relation_mode") or "manual_confirmed"),
                "special_metadata": self._serialize_value(relation.get("special_metadata") or {}),
                "oa_rows": [],
                "bank_rows": [],
                "invoice_rows": [],
            }
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            relation_row_ids: set[str] = set()
            for index, row_id in enumerate(row_ids):
                if not row_id or row_id in relation_row_ids:
                    continue
                relation_row_ids.add(row_id)
                grouped_row_ids.add(row_id)
                row_type = row_types[index] if index < len(row_types) else self._row_type_for_row_id(row_id)
                row = dict(rows_by_id.get(row_id) or {"id": row_id, "type": row_type})
                row["case_id"] = case_id
                row["status"] = "paired"
                if isinstance(relation.get("special_metadata"), dict):
                    row["special_metadata"] = self._serialize_value(relation.get("special_metadata") or {})
                row["tags"] = self._derive_row_tags(row, group, relation)
                self._append_row(group, row, row_type)
            groups.append(group)

        ungrouped_rows = [
            row
            for row in selected_rows
            if str(row.get("id", "")).strip() and str(row.get("id", "")).strip() not in grouped_row_ids
        ]
        if ungrouped_selected_rows == "individual":
            for row in ungrouped_rows:
                row_id = str(row.get("id", "")).strip()
                if not row_id:
                    continue
                group = self._selection_group(f"selected:{row_id}", "selected_row")
                preview_row = dict(row)
                preview_row.update(
                    {
                        "case_id": "",
                        "status": "unpaired",
                        "tags": [],
                        "oa_bank_relation": None,
                        "invoice_relation": None,
                        "invoice_bank_relation": None,
                    }
                )
                self._append_row(group, preview_row, str(preview_row.get("type", "")))
                groups.append(group)
        elif ungrouped_selected_rows == "separate":
            selected_groups = {str(group.get("group_id", "")): group for group in groups}
            for row in ungrouped_rows:
                row_id = str(row.get("id", "")).strip()
                case_id = str(row.get("case_id") or "").strip()
                group_id = f"case:{case_id}" if case_id else f"selected:{row_id}"
                group = selected_groups.get(group_id)
                if group is None:
                    group = self._selection_group(
                        group_id,
                        "selected_existing_case" if case_id else "selected_row",
                    )
                    selected_groups[group_id] = group
                    groups.append(group)
                preview_row = dict(row)
                preview_row["status"] = "unpaired"
                self._append_row(group, preview_row, str(preview_row.get("type", "")))
        elif ungrouped_selected_rows == "single" and ungrouped_rows:
            group = self._selection_group("selected", "selected_rows")
            for row in ungrouped_rows:
                preview_row = dict(row)
                preview_row["status"] = "unpaired"
                self._append_row(group, preview_row, str(preview_row.get("type", "")))
            groups.append(group)
        return groups

    def _serialized_mapping(self, value: object) -> dict[str, object]:
        serialized = self._serialize_value(value)
        if not isinstance(serialized, dict):
            raise TypeError("Workbench preview rows must serialize to mappings.")
        return dict(serialized)

    @staticmethod
    def _selection_group(group_id: str, reason: str) -> dict[str, object]:
        return {
            "group_id": group_id,
            "group_type": "selection",
            "match_confidence": "none",
            "reason": reason,
            "zone": "unpaired",
            "status": "unpaired",
            "oa_rows": [],
            "bank_rows": [],
            "invoice_rows": [],
        }

    @staticmethod
    def _append_row(group: dict[str, object], row: dict[str, object], row_type: str) -> None:
        pane_key = {"oa": "oa_rows", "bank": "bank_rows", "invoice": "invoice_rows"}.get(row_type)
        if pane_key is None:
            raise ValueError(f"Unsupported Workbench row type: {row_type}")
        pane = group.get(pane_key)
        if not isinstance(pane, list):
            raise TypeError(f"Workbench preview group pane must be a list: {pane_key}")
        pane.append(row)
