from __future__ import annotations

from copy import deepcopy
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import count
import re
from typing import Any

from fin_ops_platform.services.imports import normalize_name
from fin_ops_platform.services.no_oa_bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_RELATION_MODE,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    oa_attachment_parent_oa_id,
    oa_attachment_source_ids,
)
from fin_ops_platform.services.workbench_exception_projection import EXCEPTION_PROJECTION_VERSION
from fin_ops_platform.services.workbench_invoice_direction import (
    invoice_counterparty_field_from_row,
    invoice_flow_direction_from_row,
)
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SINGLE_BANK_AUTO_PAIRED_CODES = {"salary_personal_auto_match"}
MULTI_BANK_AUTO_PAIRED_CODES = {"internal_transfer_pair"}
OA_INVOICE_AUTO_PAIRED_CODES = {"oa_invoice_offset_auto_match"}
OA_BANK_SETTLEMENT_PAIRED_CODES = {"personal_advance_repayment_settlement"}
NO_OA_BANK_BATCH_PAIRED_CODES = {NO_OA_BANK_BATCH_RELATION_MODE, BANK_FLOW_RULE_BATCH_RELATION_MODE}
BATCH_ACCOUNTING_RELATION_MODE = "batch_accounting"
AUTO_PAIRED_CODES = {
    *SINGLE_BANK_AUTO_PAIRED_CODES,
    *MULTI_BANK_AUTO_PAIRED_CODES,
    *OA_INVOICE_AUTO_PAIRED_CODES,
    *OA_BANK_SETTLEMENT_PAIRED_CODES,
    *NO_OA_BANK_BATCH_PAIRED_CODES,
}
ETC_BATCH_SOURCE = "etc_batch"
ETC_BATCH_TAG = "ETC批量提交"
OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"
OA_ATTACHMENT_PAYMENT_RECEIPT_SOURCE_KIND = "oa_attachment_payment_receipt"
OA_ATTACHMENT_UNKNOWN_SOURCE_KIND = "oa_attachment_unknown"
OA_ATTACHMENT_EVIDENCE_SOURCE_KINDS = {
    OA_ATTACHMENT_INVOICE_SOURCE_KIND,
    OA_ATTACHMENT_PAYMENT_RECEIPT_SOURCE_KIND,
    OA_ATTACHMENT_UNKNOWN_SOURCE_KIND,
}
MAX_AGGREGATED_OA_INVOICE_CANDIDATES = 160
MAX_INVOICE_SUBSET_SUM_STATES = 20000
MAX_OA_BANK_EXACT_SUM_BANK_ROWS = 6


@dataclass(slots=True)
class CandidateGroup:
    group_id: str
    group_type: str
    match_confidence: str
    reason: str
    temp_key: str | None
    oa_rows: list[dict[str, Any]] = field(default_factory=list)
    bank_rows: list[dict[str, Any]] = field(default_factory=list)
    invoice_rows: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def append(self, row: dict[str, Any]) -> None:
        key = row["type"]
        if key == "oa":
            self.oa_rows.append(row)
        elif key == "bank":
            self.bank_rows.append(row)
        else:
            self.invoice_rows.append(row)

    def has_type(self, row_type: str) -> bool:
        return bool(getattr(self, f"{row_type}_rows"))

    def to_payload(self) -> dict[str, Any]:
        return {
            "group_id": self.group_id,
            "group_type": self.group_type,
            "match_confidence": self.match_confidence,
            "reason": self.reason,
            "oa_rows": self.oa_rows,
            "bank_rows": self.bank_rows,
            "invoice_rows": self.invoice_rows,
        }


class WorkbenchCandidateGroupingService:
    def __init__(self) -> None:
        self._group_counter = count(1)

    def group_payload(
        self,
        month: str,
        *,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        turnover_relations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        invoice_rows = [
            row
            for row in invoice_rows
            if not self._is_non_invoice_oa_attachment_evidence_row(row)
        ]
        all_rows = [*oa_rows, *bank_rows, *invoice_rows]
        paired_rows = [row for row in all_rows if self._is_paired_row(row)]
        open_rows = [row for row in all_rows if not self._is_paired_row(row)]

        paired_groups = self._build_case_or_temp_groups(paired_rows, default_group_type="manual_confirmed")
        valid_paired_groups, demoted_paired_rows = self._split_valid_and_incomplete_paired_groups(paired_groups)
        open_case_groups, unattached_open_rows = self._build_open_case_groups([*open_rows, *demoted_paired_rows])
        target_groups_by_temp_key = self._index_target_groups([*valid_paired_groups, *open_case_groups.values()])
        remaining_rows = self._attach_unique_rows_to_existing_groups(unattached_open_rows, target_groups_by_temp_key)

        oa_attachment_source_groups, open_case_groups, remaining_rows = (
            self._extract_oa_attachment_source_groups_from_candidate_context(open_case_groups, remaining_rows)
        )
        aggregated_oa_invoice_groups, remaining_rows = self._build_aggregated_oa_invoice_sum_groups(remaining_rows)
        turnover_relation_groups, open_case_groups, remaining_rows = self._extract_turnover_relation_groups_from_candidate_context(
            open_case_groups,
            remaining_rows,
            turnover_relations=turnover_relations,
        )
        standalone_temp_groups = self._build_temp_groups(remaining_rows)
        merged_open_case_groups = self._merge_open_case_groups(list(open_case_groups.values()))
        merged_open_case_groups = self._split_unsafe_candidate_case_groups(merged_open_case_groups)
        promoted_oa_attachment_source_groups, candidate_oa_attachment_source_groups = (
            self._split_promoted_and_candidate_groups(oa_attachment_source_groups)
        )
        promoted_open_case_groups, candidate_open_case_groups = self._split_promoted_and_candidate_groups(
            merged_open_case_groups
        )
        promoted_groups, candidate_groups = self._split_promoted_and_candidate_groups(standalone_temp_groups)

        open_groups = [
            *candidate_open_case_groups,
            *candidate_oa_attachment_source_groups,
            *aggregated_oa_invoice_groups,
            *turnover_relation_groups,
            *candidate_groups,
        ]
        paired_output = [
            *valid_paired_groups,
            *promoted_oa_attachment_source_groups,
            *promoted_open_case_groups,
            *promoted_groups,
        ]
        paired_output, open_groups = self._co_locate_oa_attachment_invoices_with_parent_oa_groups(
            paired_output,
            open_groups,
        )

        return {
            "month": month,
            "summary": {
                "oa_count": len(oa_rows),
                "bank_count": len(bank_rows),
                "invoice_count": len(invoice_rows),
                "paired_count": len(paired_output),
                "open_count": len(open_groups),
                "exception_count": sum(1 for group in open_groups if self._group_has_danger(group)),
            },
            "paired": {"groups": [self._serialize_group(group, section="paired") for group in paired_output]},
            "open": {"groups": [self._serialize_group(group, section="open") for group in open_groups]},
        }

    def _co_locate_oa_attachment_invoices_with_parent_oa_groups(
        self,
        paired_groups: list[CandidateGroup],
        open_groups: list[CandidateGroup],
    ) -> tuple[list[CandidateGroup], list[CandidateGroup]]:
        parent_groups_by_oa_id: dict[str, CandidateGroup] = {}
        for group in [*paired_groups, *open_groups]:
            for row in group.oa_rows:
                row_id = self._string_value(row.get("id"))
                if row_id:
                    parent_groups_by_oa_id.setdefault(row_id, group)

        if not parent_groups_by_oa_id:
            return paired_groups, open_groups

        changed = False
        for group in [*paired_groups, *open_groups]:
            retained_invoice_rows: list[dict[str, Any]] = []
            for row in group.invoice_rows:
                target_group = self._oa_attachment_parent_group(row, parent_groups_by_oa_id)
                if target_group is None or target_group is group:
                    retained_invoice_rows.append(row)
                    continue
                self._append_unique_invoice_row(target_group, row)
                self._mark_oa_attachment_source_group(target_group)
                changed = True
            group.invoice_rows = retained_invoice_rows

        if not changed:
            return paired_groups, open_groups
        return self._non_empty_groups(paired_groups), self._non_empty_groups(open_groups)

    def _oa_attachment_parent_group(
        self,
        row: dict[str, Any],
        parent_groups_by_oa_id: dict[str, CandidateGroup],
    ) -> CandidateGroup | None:
        source_id = self._oa_attachment_evidence_source_id(row)
        if source_id is None:
            return None
        return parent_groups_by_oa_id.get(source_id)

    @staticmethod
    def _append_unique_invoice_row(group: CandidateGroup, row: dict[str, Any]) -> None:
        row_id = str(row.get("id") or "").strip()
        if row_id and any(str(existing.get("id") or "").strip() == row_id for existing in group.invoice_rows):
            return
        group.invoice_rows.append(row)

    @staticmethod
    def _mark_oa_attachment_source_group(group: CandidateGroup) -> None:
        if group.group_type in {
            "manual_confirmed",
            "auto_closed",
            "open_exception",
            "processed_exception",
            "ignored",
            "legacy_exception",
        }:
            return
        group.group_type = "source_linked"
        group.match_confidence = "high"
        group.reason = "oa_attachment_source_relation"

    @staticmethod
    def _non_empty_groups(groups: list[CandidateGroup]) -> list[CandidateGroup]:
        return [
            group
            for group in groups
            if group.oa_rows or group.bank_rows or group.invoice_rows
        ]

    def _extract_turnover_relation_groups_from_candidate_context(
        self,
        open_case_groups: "OrderedDict[str, CandidateGroup]",
        remaining_rows: list[dict[str, Any]],
        *,
        turnover_relations: list[dict[str, Any]] | None,
    ) -> tuple[list[CandidateGroup], "OrderedDict[str, CandidateGroup]", list[dict[str, Any]]]:
        # Turnover relations are recommendation evidence only; paired state must come from active pair relations.
        _ = turnover_relations
        return [], open_case_groups, remaining_rows

    def _split_valid_and_incomplete_paired_groups(
        self,
        groups: list[CandidateGroup],
    ) -> tuple[list[CandidateGroup], list[dict[str, Any]]]:
        valid_groups: list[CandidateGroup] = []
        demoted_rows: list[dict[str, Any]] = []
        for group in groups:
            if self._paired_group_has_enough_row_types(group):
                valid_groups.append(group)
                continue
            demoted_rows.extend(
                self._open_context_row(row)
                for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
            )
        return valid_groups, demoted_rows

    @staticmethod
    def _open_context_row(row: dict[str, Any]) -> dict[str, Any]:
        cloned = deepcopy(row)
        cloned["status"] = "open"
        return cloned

    def _build_case_or_temp_groups(
        self,
        rows: list[dict[str, Any]],
        *,
        default_group_type: str,
    ) -> list[CandidateGroup]:
        groups: "OrderedDict[str, CandidateGroup]" = OrderedDict()
        for row in rows:
            case_id = self._case_id(row)
            temp_key = self._temp_key(row)
            if case_id:
                group_id = f"case:{case_id}"
            else:
                group_id = self._next_temp_group_id()
            if group_id not in groups:
                groups[group_id] = CandidateGroup(
                    group_id=group_id,
                    group_type=self._group_type_for_existing_paired_rows([row], default_group_type),
                    match_confidence="high",
                    reason="existing_case_group" if case_id else "existing_temp_group",
                    temp_key=temp_key,
                )
            group = groups[group_id]
            group.append(row)
            if group.temp_key is None:
                group.temp_key = temp_key
            elif temp_key is not None and group.temp_key != temp_key and not self._is_oa_attachment_evidence_row(row):
                group.temp_key = None
            group.group_type = self._group_type_for_existing_paired_rows(
                [*group.oa_rows, *group.bank_rows, *group.invoice_rows],
                default_group_type,
            )
        return list(groups.values())

    def _build_open_case_groups(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple["OrderedDict[str, CandidateGroup]", list[dict[str, Any]]]:
        groups: "OrderedDict[str, CandidateGroup]" = OrderedDict()
        unattached: list[dict[str, Any]] = []
        for row in rows:
            case_id = self._case_id(row)
            if not case_id:
                unattached.append(row)
                continue
            group_id = f"case:{case_id}"
            temp_key = self._temp_key(row)
            if group_id not in groups:
                group_type = self._group_type_for_open_case_rows([row])
                groups[group_id] = CandidateGroup(
                    group_id=group_id,
                    group_type=group_type,
                    match_confidence="high" if group_type != "candidate" else "medium",
                    reason=self._open_case_group_reason(group_type),
                    temp_key=temp_key,
                )
            group = groups[group_id]
            group.append(row)
            if group.temp_key is None:
                group.temp_key = temp_key
            elif temp_key is not None and group.temp_key != temp_key and not self._is_oa_attachment_evidence_row(row):
                group.temp_key = None
            group.group_type = self._group_type_for_open_case_rows(
                [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
            )
            if group.group_type != "candidate":
                group.match_confidence = "high"
                group.reason = self._open_case_group_reason(group.group_type)
        return groups, unattached

    def _index_target_groups(self, groups: list[CandidateGroup]) -> dict[str, list[CandidateGroup]]:
        indexed: dict[str, list[CandidateGroup]] = defaultdict(list)
        for group in groups:
            if group.temp_key is None:
                continue
            indexed[group.temp_key].append(group)
        return indexed

    def _attach_unique_rows_to_existing_groups(
        self,
        rows: list[dict[str, Any]],
        target_groups_by_temp_key: dict[str, list[CandidateGroup]],
    ) -> list[dict[str, Any]]:
        remaining: list[dict[str, Any]] = []
        for row in rows:
            temp_key = self._temp_key(row)
            if temp_key is None:
                remaining.append(row)
                continue
            candidate_groups = [
                group
                for group in target_groups_by_temp_key.get(temp_key, [])
                if not group.has_type(row["type"])
            ]
            if len(candidate_groups) != 1:
                remaining.append(row)
                continue
            group = candidate_groups[0]
            group.append(row)
            if group.group_type != "manual_confirmed":
                group.group_type = "candidate" if group.group_type == "candidate" else "auto_closed"
            if group.group_type == "candidate":
                group.match_confidence = "medium"
                group.reason = "attached_unique_candidate"
            else:
                group.match_confidence = "high"
                group.reason = "attached_unique_auto_close"
        return remaining

    def _build_temp_groups(self, rows: list[dict[str, Any]]) -> list[CandidateGroup]:
        groups: "OrderedDict[str, CandidateGroup]" = OrderedDict()
        for row in rows:
            temp_key = self._temp_key(row)
            group_key = temp_key or self._candidate_key(row) or f"row:{row['id']}"
            if group_key not in groups:
                is_open_decision = self._is_open_reconciliation_decision_row(row)
                groups[group_key] = CandidateGroup(
                    group_id=self._next_temp_group_id(),
                    group_type="open" if is_open_decision else "candidate",
                    match_confidence="low",
                    reason="reconciliation_decision_open" if is_open_decision else ("temp_candidate_group" if temp_key else "standalone_row_group"),
                    temp_key=temp_key,
                )
            groups[group_key].append(row)
        return self._merge_candidate_groups(list(groups.values()))

    def _build_aggregated_oa_invoice_sum_groups(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[list[CandidateGroup], list[dict[str, Any]]]:
        oa_rows = sorted(
            (row for row in rows if self._is_open_oa_multi_invoice_candidate_row(row)),
            key=lambda row: str(row.get("id", "")),
        )
        invoice_rows = [
            row
            for row in rows
            if self._is_manual_imported_open_invoice_row(row)
        ]

        candidate_matches: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
        for oa_row in oa_rows:
            target_amount = self._amount(oa_row)
            if target_amount is None or target_amount <= ZERO:
                continue
            candidate_invoices = [
                row
                for row in invoice_rows
                if self._invoice_matches_aggregated_oa_candidate(row, oa_row)
            ]
            if len(candidate_invoices) > MAX_AGGREGATED_OA_INVOICE_CANDIDATES:
                continue
            matched_invoices = self._find_invoice_sum_match(candidate_invoices, target_amount)
            if not matched_invoices:
                continue
            candidate_matches.append((oa_row, matched_invoices))

        if not candidate_matches:
            return [], rows

        invoice_match_counts: dict[int, int] = defaultdict(int)
        for _, matched_invoices in candidate_matches:
            for invoice_row in matched_invoices:
                invoice_match_counts[id(invoice_row)] += 1
        conflicting_invoice_keys = {
            invoice_key
            for invoice_key, match_count in invoice_match_counts.items()
            if match_count > 1
        }

        groups: list[CandidateGroup] = []
        used_row_keys: set[int] = set()
        for oa_row, matched_invoices in candidate_matches:
            if any(id(invoice_row) in conflicting_invoice_keys for invoice_row in matched_invoices):
                continue
            group = CandidateGroup(
                group_id=self._next_temp_group_id(),
                group_type="candidate",
                match_confidence="medium",
                reason="aggregated_oa_multi_invoice_sum_candidate",
                temp_key=None,
            )
            group.append(oa_row)
            for invoice_row in matched_invoices:
                group.append(invoice_row)
            groups.append(group)
            used_row_keys.add(id(oa_row))
            used_row_keys.update(id(row) for row in matched_invoices)

        if not used_row_keys:
            return [], rows
        return groups, [row for row in rows if id(row) not in used_row_keys]

    def _build_oa_attachment_source_groups(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[list[CandidateGroup], list[dict[str, Any]]]:
        oa_rows_by_id: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
        for row in rows:
            if row.get("type") != "oa" or not self._can_join_oa_attachment_source_group(row):
                continue
            row_id = self._string_value(row.get("id"))
            if row_id:
                oa_rows_by_id[row_id] = row

        invoice_rows_by_source_id: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
        for row in rows:
            source_id = self._oa_attachment_evidence_source_id(row, set(oa_rows_by_id))
            if source_id is None:
                continue
            invoice_rows_by_source_id.setdefault(source_id, []).append(row)

        if not invoice_rows_by_source_id:
            return [], rows

        groups: list[CandidateGroup] = []
        used_row_keys: set[int] = set()
        for source_id, invoice_rows in invoice_rows_by_source_id.items():
            group = CandidateGroup(
                group_id=self._oa_attachment_source_group_id(source_id),
                group_type="source_linked",
                match_confidence="high",
                reason="oa_attachment_source_relation",
                temp_key=None,
            )
            oa_row = oa_rows_by_id[source_id]
            group.append(oa_row)
            for invoice_row in invoice_rows:
                group.append(invoice_row)
            groups.append(group)
            used_row_keys.add(id(oa_row))
            used_row_keys.update(id(row) for row in invoice_rows)

        return groups, [row for row in rows if id(row) not in used_row_keys]

    def _extract_oa_attachment_source_groups_from_candidate_context(
        self,
        open_case_groups: "OrderedDict[str, CandidateGroup]",
        remaining_rows: list[dict[str, Any]],
    ) -> tuple[list[CandidateGroup], "OrderedDict[str, CandidateGroup]", list[dict[str, Any]]]:
        source_candidate_rows = list(remaining_rows)
        splittable_group_ids: set[str] = set()
        for group_id, group in open_case_groups.items():
            if not self._can_split_open_case_group_for_oa_attachment_source(group):
                continue
            splittable_group_ids.add(group_id)
            source_candidate_rows.extend([*group.oa_rows, *group.bank_rows, *group.invoice_rows])

        original_remaining_row_keys = {id(row) for row in remaining_rows}
        source_groups, remaining_source_rows = self._build_oa_attachment_source_groups(source_candidate_rows)
        if not source_groups:
            return [], open_case_groups, remaining_rows
        extra_consumed_row_keys = self._attach_candidate_case_banks_to_oa_attachment_source_groups(
            source_groups,
            open_case_groups,
        )

        consumed_row_keys = {
            id(row)
            for group in source_groups
            for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        }
        consumed_row_keys.update(extra_consumed_row_keys)
        rebuilt_open_case_groups: "OrderedDict[str, CandidateGroup]" = OrderedDict()
        for group_id, group in open_case_groups.items():
            if group_id not in splittable_group_ids:
                rebuilt_open_case_groups[group_id] = group
                continue
            remaining_group_rows = [
                row
                for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
                if id(row) not in consumed_row_keys
            ]
            if not remaining_group_rows:
                continue
            rebuilt_group = CandidateGroup(
                group_id=group.group_id,
                group_type=self._group_type_for_open_case_rows(remaining_group_rows),
                match_confidence=group.match_confidence,
                reason=group.reason,
                temp_key=group.temp_key,
            )
            for row in remaining_group_rows:
                rebuilt_group.append(row)
            if rebuilt_group.group_type != "candidate":
                rebuilt_group.match_confidence = "high"
                rebuilt_group.reason = self._open_case_group_reason(rebuilt_group.group_type)
            rebuilt_open_case_groups[group_id] = rebuilt_group

        rebuilt_remaining_rows = [
            row
            for row in remaining_source_rows
            if id(row) in original_remaining_row_keys
        ]
        return source_groups, rebuilt_open_case_groups, rebuilt_remaining_rows

    def _attach_candidate_case_banks_to_oa_attachment_source_groups(
        self,
        source_groups: list[CandidateGroup],
        open_case_groups: "OrderedDict[str, CandidateGroup]",
    ) -> set[int]:
        consumed_row_keys: set[int] = set()
        candidate_bank_rows_by_oa_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for group in open_case_groups.values():
            if not self._can_split_open_case_group_for_oa_attachment_source(group):
                continue
            if len(group.oa_rows) != 1 or not group.bank_rows:
                continue
            oa_id = self._string_value(group.oa_rows[0].get("id"))
            if not oa_id:
                continue
            candidate_bank_rows_by_oa_id[oa_id].extend(group.bank_rows)

        if not candidate_bank_rows_by_oa_id:
            return consumed_row_keys

        for source_group in source_groups:
            if len(source_group.oa_rows) != 1 or source_group.bank_rows:
                continue
            oa_id = self._string_value(source_group.oa_rows[0].get("id"))
            candidate_banks = candidate_bank_rows_by_oa_id.get(oa_id, [])
            if not candidate_banks:
                continue
            attachable_banks: list[dict[str, Any]] = []
            for bank_row in candidate_banks:
                probe = CandidateGroup(
                    group_id=source_group.group_id,
                    group_type=source_group.group_type,
                    match_confidence=source_group.match_confidence,
                    reason=source_group.reason,
                    temp_key=source_group.temp_key,
                    oa_rows=list(source_group.oa_rows),
                    bank_rows=[bank_row],
                    invoice_rows=list(source_group.invoice_rows),
                    metadata=deepcopy(source_group.metadata),
                )
                if self._qualifies_for_attachment_invoice_auto_close(probe):
                    attachable_banks.append(bank_row)
            if len(attachable_banks) != 1:
                continue
            source_group.bank_rows.append(attachable_banks[0])
            consumed_row_keys.add(id(attachable_banks[0]))
        return consumed_row_keys

    def _can_split_open_case_group_for_oa_attachment_source(self, group: CandidateGroup) -> bool:
        if group.group_type != "candidate":
            return False
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        case_ids = {case_id for case_id in (self._case_id(row) for row in rows) if case_id}
        if not case_ids:
            return True
        return all(case_id.startswith("candidate:") for case_id in case_ids)

    def _merge_candidate_groups(self, groups: list[CandidateGroup]) -> list[CandidateGroup]:
        merged = list(groups)
        changed = True
        while changed:
            changed = False
            next_groups: list[CandidateGroup] = []
            while merged:
                current = merged.pop(0)
                match_indexes = [
                    index
                    for index, candidate in enumerate(merged)
                    if self._should_merge_candidate_groups(current, candidate)
                ]
                if len(match_indexes) == 1:
                    match_group = merged.pop(match_indexes[0])
                    self._absorb_group(current, match_group)
                    current.match_confidence = "medium"
                    current.reason = "complementary_candidate_group"
                    changed = True
                next_groups.append(current)
            merged = next_groups
        return merged

    def _merge_open_case_groups(self, groups: list[CandidateGroup]) -> list[CandidateGroup]:
        merged = list(groups)
        changed = True
        while changed:
            changed = False
            next_groups: list[CandidateGroup] = []
            while merged:
                current = merged.pop(0)
                match_indexes = [
                    index
                    for index, candidate in enumerate(merged)
                    if self._should_merge_open_case_groups(current, candidate)
                ]
                if len(match_indexes) == 1:
                    match_group = merged.pop(match_indexes[0])
                    self._absorb_group(current, match_group)
                    current.match_confidence = "medium"
                    current.reason = "attachment_case_candidate_group"
                    changed = True
                next_groups.append(current)
            merged = next_groups
        return merged

    def _split_unsafe_candidate_case_groups(self, groups: list[CandidateGroup]) -> list[CandidateGroup]:
        split_groups: list[CandidateGroup] = []
        for group in groups:
            if not self._should_split_unsafe_candidate_case_group(group):
                split_groups.append(group)
                continue
            split_groups.extend(self._partition_unsafe_candidate_case_group(group))
        return split_groups

    def _should_split_unsafe_candidate_case_group(self, group: CandidateGroup) -> bool:
        if group.group_type != "candidate":
            return False
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        case_ids = {case_id for case_id in (self._case_id(row) for row in rows) if case_id}
        if len(case_ids) != 1:
            return False
        case_id = next(iter(case_ids))
        if not case_id.startswith("candidate:"):
            return False
        row_type_count = sum(1 for typed_rows in (group.oa_rows, group.bank_rows, group.invoice_rows) if typed_rows)
        if len(rows) <= 1 or row_type_count <= 1:
            return False
        if self._has_confirmed_or_processed_relation(group):
            return False
        return not self._has_deterministic_candidate_relation(group)

    def _has_confirmed_or_processed_relation(self, group: CandidateGroup) -> bool:
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        if any(bool(row.get("handled_exception")) for row in rows):
            return True
        if any(self._is_processed_exception_projection_row(row) for row in rows):
            return True
        relation_codes = {self._relation_code(row) for row in rows}
        return bool(relation_codes.intersection({"fully_linked", "automatic_match", *AUTO_PAIRED_CODES}))

    def _has_deterministic_candidate_relation(self, group: CandidateGroup) -> bool:
        if self._qualifies_for_auto_close(group):
            return True
        if self._has_exact_amount_candidate_relation(group):
            return True
        single_row_groups = [
            self._candidate_group_for_row(row, f"candidate-check:{index}", group.match_confidence, group.reason)
            for index, row in enumerate([*group.oa_rows, *group.bank_rows, *group.invoice_rows], start=1)
        ]
        return len(self._merge_candidate_groups(single_row_groups)) == 1

    def _has_exact_amount_candidate_relation(self, group: CandidateGroup) -> bool:
        row_type_count = sum(1 for rows in (group.oa_rows, group.bank_rows, group.invoice_rows) if rows)
        if row_type_count <= 1:
            return False
        if self._has_oa_bank_exact_sum_candidate_relation(group):
            return True
        if len(group.oa_rows) > 1 or len(group.bank_rows) > 1:
            return False
        if not self._has_group_counterparty_evidence(group) or self._group_direction(group) is None:
            return False

        target_amount = self._amount(group.oa_rows[0]) if group.oa_rows else None
        if target_amount is None and group.bank_rows:
            target_amount = self._amount(group.bank_rows[0])
        if target_amount is None:
            return False

        if group.bank_rows and self._amount(group.bank_rows[0]) != target_amount:
            return False

        if group.invoice_rows:
            if any(self._is_non_invoice_oa_attachment_evidence_row(row) for row in group.invoice_rows):
                return False
            invoice_amounts = [self._invoice_gross_amount(row) for row in group.invoice_rows]
            if any(amount is None for amount in invoice_amounts):
                return False
            if sum((amount for amount in invoice_amounts if amount is not None), ZERO) != target_amount:
                return False

        return True

    def _has_oa_bank_exact_sum_candidate_relation(self, group: CandidateGroup) -> bool:
        if len(group.oa_rows) != 1 or not (2 <= len(group.bank_rows) <= MAX_OA_BANK_EXACT_SUM_BANK_ROWS):
            return False
        if group.invoice_rows:
            return False
        if not self._has_group_counterparty_evidence(group) or self._group_direction(group) is None:
            return False
        target_amount = self._amount(group.oa_rows[0])
        if target_amount is None or target_amount <= ZERO:
            return False
        bank_amounts = [self._amount(row) for row in group.bank_rows]
        if any(amount is None or amount <= ZERO for amount in bank_amounts):
            return False
        return sum((amount for amount in bank_amounts if amount is not None), ZERO) == target_amount

    def _has_group_counterparty_evidence(self, group: CandidateGroup) -> bool:
        if self._group_counterparty(group) is not None:
            return True
        return self._has_oa_bank_counterparty_alias(group)

    def _has_oa_bank_counterparty_alias(self, group: CandidateGroup) -> bool:
        if len(group.oa_rows) != 1 or len(group.bank_rows) != 1 or group.invoice_rows:
            return False
        oa_counterparty = self._counterparty_alias_key(self._counterparty(group.oa_rows[0]))
        bank_counterparty = self._counterparty_alias_key(self._counterparty(group.bank_rows[0]))
        if not oa_counterparty or not bank_counterparty:
            return False
        if oa_counterparty == bank_counterparty:
            return True
        shorter, longer = sorted((oa_counterparty, bank_counterparty), key=len)
        return len(shorter) >= 3 and longer.startswith(shorter)

    @staticmethod
    def _counterparty_alias_key(value: str | None) -> str:
        if not value:
            return ""
        return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "", value)

    def _single_row_candidate_groups(self, group: CandidateGroup) -> list[CandidateGroup]:
        return [
            self._candidate_group_for_row(
                row,
                self._next_temp_group_id(),
                "low",
                "split_unsafe_candidate_case_group",
            )
            for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        ]

    def _partition_unsafe_candidate_case_group(self, group: CandidateGroup) -> list[CandidateGroup]:
        single_row_groups = [
            self._candidate_group_for_row(
                row,
                self._candidate_case_partition_group_id(group, [row]),
                "low",
                "split_unsafe_candidate_case_group",
            )
            for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        ]
        partitioned_groups = self._merge_candidate_groups(single_row_groups)
        if len(partitioned_groups) == 1:
            return [group]

        rebuilt_groups: list[CandidateGroup] = []
        for partition in partitioned_groups:
            rows = [*partition.oa_rows, *partition.bank_rows, *partition.invoice_rows]
            if not rows:
                continue
            row_count = len(rows)
            rebuilt_group = CandidateGroup(
                group_id=self._candidate_case_partition_group_id(group, rows),
                group_type=self._group_type_for_open_case_rows(rows),
                match_confidence="medium" if row_count > 1 else "low",
                reason="deterministic_candidate_case_subgroup" if row_count > 1 else "split_unsafe_candidate_case_group",
                temp_key=partition.temp_key,
                metadata=deepcopy(group.metadata),
            )
            for row in rows:
                rebuilt_group.append(row)
            rebuilt_groups.append(rebuilt_group)
        return rebuilt_groups

    def _candidate_case_partition_group_id(self, group: CandidateGroup, rows: list[dict[str, Any]]) -> str:
        row_ids = sorted(
            row_id
            for row in rows
            if (row_id := self._string_value(row.get("id")))
        )
        if len(row_ids) == 1:
            return f"row:{row_ids[0]}"
        if row_ids:
            return f"{group.group_id}:part:{'|'.join(row_ids)}"
        return self._next_temp_group_id()

    def _candidate_group_for_row(
        self,
        row: dict[str, Any],
        group_id: str,
        match_confidence: str,
        reason: str,
    ) -> CandidateGroup:
        group = CandidateGroup(
            group_id=group_id,
            group_type="candidate",
            match_confidence=match_confidence,
            reason=reason,
            temp_key=self._temp_key(row),
        )
        group.append(row)
        return group

    def _should_merge_open_case_groups(self, left: CandidateGroup, right: CandidateGroup) -> bool:
        if not (self._attachment_group_primary_row(left) or self._attachment_group_primary_row(right)):
            return False
        return self._should_merge_candidate_groups(left, right)

    def _should_merge_candidate_groups(self, left: CandidateGroup, right: CandidateGroup) -> bool:
        if left.group_type == "open" or right.group_type == "open":
            return False
        left_counterparty = self._group_counterparty(left)
        right_counterparty = self._group_counterparty(right)
        if left_counterparty is None or right_counterparty is None or left_counterparty != right_counterparty:
            return False

        left_direction = self._group_direction(left)
        right_direction = self._group_direction(right)
        if left_direction is None or right_direction is None or left_direction != right_direction:
            return False

        if not self._date_buckets_compatible(self._group_date_buckets(left), self._group_date_buckets(right)):
            return False

        left_total = self._group_total_amount(left)
        right_total = self._group_total_amount(right)
        if left_total is None or right_total is None:
            return False
        if left_total != right_total:
            return False

        return not self._same_row_types_only(left, right)

    def _absorb_group(self, target: CandidateGroup, source: CandidateGroup) -> None:
        for row in source.oa_rows:
            target.oa_rows.append(row)
        for row in source.bank_rows:
            target.bank_rows.append(row)
        for row in source.invoice_rows:
            target.invoice_rows.append(row)
        if target.temp_key != source.temp_key:
            target.temp_key = None

    def _split_promoted_and_candidate_groups(
        self,
        groups: list[CandidateGroup],
    ) -> tuple[list[CandidateGroup], list[CandidateGroup]]:
        promoted: list[CandidateGroup] = []
        candidates: list[CandidateGroup] = []
        for group in groups:
            if group.group_type in {"open", "open_exception", "ignored", "legacy_exception", "source_linked"}:
                if group.group_type == "source_linked" and self._qualifies_for_auto_close(group):
                    group.group_type = "auto_closed"
                    group.match_confidence = "high"
                    group.reason = "unique_candidate_chain"
                    promoted.append(group)
                else:
                    candidates.append(group)
                continue
            if self._qualifies_for_auto_close(group):
                group.group_type = "auto_closed"
                group.match_confidence = "high"
                group.reason = "unique_candidate_chain"
                promoted.append(group)
            else:
                if sum(len(rows) for rows in (group.oa_rows, group.bank_rows, group.invoice_rows)) > 1:
                    group.match_confidence = "medium"
                candidates.append(group)
        return promoted, candidates

    def _qualifies_for_auto_close(self, group: CandidateGroup) -> bool:
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        if any(self._is_open_exception_projection_row(row) or self._is_ignored_exception_row(row) for row in rows):
            return False
        if any(bool(row.get("handled_exception")) or bool(row.get("auto_close_suppressed")) for row in rows):
            return False
        if self._qualifies_for_attachment_invoice_auto_close(group):
            return True
        if self._qualifies_for_etc_batch_oa_bank_auto_close(group):
            return True
        if any(self._is_non_invoice_oa_attachment_evidence_row(row) for row in group.invoice_rows):
            return False

        total_count = len(group.oa_rows) + len(group.bank_rows) + len(group.invoice_rows)
        if total_count < 2:
            return False
        if not (group.oa_rows and group.bank_rows and group.invoice_rows):
            return False
        if len(group.oa_rows) > 1 or len(group.bank_rows) > 1 or len(group.invoice_rows) > 1:
            return False
        if not group.bank_rows:
            return False
        if group.oa_rows and self._direction(group.oa_rows[0]) != self._direction(group.bank_rows[0]):
            return False
        if group.invoice_rows and self._direction(group.invoice_rows[0]) != self._direction(group.bank_rows[0]):
            return False
        amounts = {self._amount(row) for row in rows}
        return len(amounts) == 1 and None not in amounts

    def _qualifies_for_attachment_invoice_auto_close(self, group: CandidateGroup) -> bool:
        if len(group.oa_rows) != 1 or len(group.bank_rows) != 1 or not group.invoice_rows:
            return False
        if not all(self._is_oa_attachment_invoice_row(row) for row in group.invoice_rows):
            return False
        bank_direction = self._direction(group.bank_rows[0])
        oa_direction = self._direction(group.oa_rows[0])
        if bank_direction is None or bank_direction != oa_direction:
            return False
        if any(self._direction(row) != bank_direction for row in group.invoice_rows):
            return False

        oa_amount = self._amount(group.oa_rows[0])
        bank_amount = self._amount(group.bank_rows[0])
        invoice_amounts = [self._attachment_invoice_reconciliation_amount(row) for row in group.invoice_rows]
        if oa_amount is None or bank_amount is None or oa_amount != bank_amount:
            return False
        if any(amount is None for amount in invoice_amounts):
            return False
        return sum(invoice_amounts, ZERO) == oa_amount

    def _qualifies_for_etc_batch_oa_bank_auto_close(self, group: CandidateGroup) -> bool:
        if len(group.oa_rows) != 1 or len(group.bank_rows) != 1 or group.invoice_rows:
            return False
        if not self._is_etc_batch_oa_row(group.oa_rows[0]):
            return False
        bank_direction = self._direction(group.bank_rows[0])
        oa_direction = self._direction(group.oa_rows[0])
        if bank_direction is None or bank_direction != oa_direction:
            return False
        oa_amount = self._amount(group.oa_rows[0])
        bank_amount = self._amount(group.bank_rows[0])
        if oa_amount is None or bank_amount is None or oa_amount != bank_amount:
            return False
        oa_counterparty = self._counterparty(group.oa_rows[0])
        bank_counterparty = self._counterparty(group.bank_rows[0])
        return oa_counterparty is not None and oa_counterparty == bank_counterparty

    def _group_has_danger(self, group: CandidateGroup) -> bool:
        return any(self._relation_tone(row) == "danger" for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows])

    def _serialize_group(self, group: CandidateGroup, *, section: str) -> dict[str, Any]:
        payload = {
            "group_id": group.group_id,
            "group_type": group.group_type,
            "match_confidence": group.match_confidence,
            "reason": group.reason,
            "oa_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.oa_rows],
            "bank_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.bank_rows],
            "invoice_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.invoice_rows],
        }
        relation_mode = self._group_relation_mode(group)
        if relation_mode:
            payload["relation_mode"] = relation_mode
        display_tags = self._group_display_tags(group)
        if display_tags:
            payload["display_tags"] = display_tags
        group_metadata = self._group_projection_metadata(group)
        if group_metadata:
            payload["group_metadata"] = group_metadata
        processed_summary = self._group_processed_exception_summary(group)
        if processed_summary:
            payload["processed_exception_summary"] = processed_summary
        self._apply_etc_invoice_summary_collapsed_details(payload)
        if section == "paired" and self._should_collapse_no_oa_bank_batch_group(group):
            self._apply_no_oa_bank_batch_collapsed_summary(payload)
        return payload

    @staticmethod
    def _apply_etc_invoice_summary_collapsed_details(payload: dict[str, Any]) -> None:
        invoice_rows = [row for row in list(payload.get("invoice_rows") or []) if isinstance(row, dict)]
        if len(invoice_rows) != 1:
            return
        summary_row = invoice_rows[0]
        if str(summary_row.get("source_kind") or "").strip() != "etc_invoice_summary":
            return
        detail_rows = [
            dict(row)
            for row in list(summary_row.get("etc_invoice_detail_rows") or [])
            if isinstance(row, dict)
        ]
        if not detail_rows:
            return
        summary_row = dict(summary_row)
        summary_row.pop("etc_invoice_detail_rows", None)
        summary_row["etc_invoice_detail_count"] = len(detail_rows)
        payload["display_mode"] = "collapsed_summary"
        payload["default_collapsed"] = True
        payload["collapsed_rows"] = {"invoice": detail_rows}
        payload["collapsed_row_counts"] = {"invoice": len(detail_rows)}
        payload["invoice_rows"] = [summary_row]

    def _should_collapse_no_oa_bank_batch_group(self, group: CandidateGroup) -> bool:
        if group.oa_rows or group.invoice_rows or not group.bank_rows:
            return False
        if len(group.bank_rows) < 2:
            return False
        relation_codes = {self._relation_code(row) for row in group.bank_rows}
        if not relation_codes.issubset(NO_OA_BANK_BATCH_PAIRED_CODES):
            return False
        if relation_codes == {BANK_FLOW_RULE_BATCH_RELATION_MODE} and len(group.bank_rows) <= 3:
            return False
        source_batch_ids = {
            source_batch_id
            for row in group.bank_rows
            if (source_batch_id := self._no_oa_source_batch_id(row))
        }
        return len(source_batch_ids) == 1 and len(source_batch_ids) == len(
            {self._no_oa_source_batch_id(row) for row in group.bank_rows}
        )

    def _apply_no_oa_bank_batch_collapsed_summary(self, payload: dict[str, Any]) -> None:
        bank_rows = [row for row in list(payload.get("bank_rows") or []) if isinstance(row, dict)]
        summary_row = self._no_oa_bank_batch_summary_row(bank_rows)
        payload["relation_mode"] = self._relation_code(bank_rows[0]) or NO_OA_BANK_BATCH_RELATION_MODE
        payload["display_mode"] = "collapsed_summary"
        payload["default_collapsed"] = True
        payload["summary_row"] = summary_row
        payload["collapsed_rows"] = {"bank": bank_rows}
        payload["bank_rows"] = [deepcopy(summary_row)]

    def _no_oa_bank_batch_summary_row(self, bank_rows: list[dict[str, Any]]) -> dict[str, Any]:
        first_row = bank_rows[0]
        metadata = self._no_oa_summary_metadata(bank_rows)
        source_batch_id = str(metadata.get("source_batch_id") or "")
        batch_label = str(metadata.get("batch_label") or "免OA流水")
        total_amount = str(metadata.get("total_amount") or "0.00")
        account_label = self._first_non_empty(
            first_row.get("payment_account_label"),
            first_row.get("counterparty_name"),
            self._summary_field_value(first_row, "支付账户"),
            self._summary_field_value(first_row, "收款账户"),
        )
        trade_month = self._first_non_empty(
            self._month(first_row),
            self._month_from_value(first_row.get("trade_time")),
            self._month_from_value(first_row.get("pay_receive_time")),
        )
        display_tags = self._no_oa_display_tags(bank_rows, batch_label)
        relation_payload = {
            "code": NO_OA_BANK_BATCH_RELATION_MODE,
            "label": f"已匹配：{batch_label}" if batch_label else "已匹配：免OA流水",
            "tone": "success",
        }
        actions = ["detail"]
        if source_batch_id and bool(metadata.get("withdrawable")):
            actions.append("withdraw_no_oa_batch")
        return {
            "id": f"no_oa_summary:{source_batch_id or self._string_value(first_row.get('case_id')) or 'unknown'}",
            "type": "bank",
            "source_kind": "no_oa_bank_batch_summary",
            "label": f"免OA · {batch_label}" if batch_label else "免OA流水",
            "amount": total_amount,
            "debit_amount": total_amount,
            "credit_amount": "",
            "counterparty_name": account_label or "免OA流水",
            "trade_time": trade_month or "",
            "tags": display_tags,
            "display_tags": display_tags,
            "invoice_relation": relation_payload,
            "special_metadata": metadata,
            "available_actions": actions,
        }

    def _no_oa_summary_metadata(self, bank_rows: list[dict[str, Any]]) -> dict[str, Any]:
        metadata_by_key: dict[str, Any] = {}
        for row in bank_rows:
            row_metadata = row.get("special_metadata")
            if not isinstance(row_metadata, dict):
                continue
            for key in (
                "source_batch_id",
                "batch_version",
                "batch_type",
                "batch_label",
                "withdrawable",
                "cost_policy",
                "relation_mode",
                "display_tags",
                "total_amount",
            ):
                if key in metadata_by_key or key not in row_metadata:
                    continue
                metadata_by_key[key] = deepcopy(row_metadata[key])

        metadata_by_key["source_batch_id"] = str(metadata_by_key.get("source_batch_id") or "")
        metadata_by_key["batch_type"] = str(metadata_by_key.get("batch_type") or "")
        metadata_by_key["batch_label"] = str(metadata_by_key.get("batch_label") or "")
        metadata_by_key["row_count"] = len(bank_rows)
        metadata_by_key["total_amount"] = self._format_decimal_amount(
            self._no_oa_summary_total_amount(bank_rows, metadata_by_key)
        )
        if "withdrawable" in metadata_by_key:
            metadata_by_key["withdrawable"] = bool(metadata_by_key["withdrawable"])
        else:
            metadata_by_key["withdrawable"] = bool(metadata_by_key["source_batch_id"])
        return metadata_by_key

    def _no_oa_summary_total_amount(self, bank_rows: list[dict[str, Any]], metadata: dict[str, Any]) -> Decimal:
        metadata_total = self._amount_from_value(metadata.get("total_amount"))
        if metadata_total is not None:
            return metadata_total
        if str(metadata.get("batch_type") or "") == "internal_transfer":
            income_total = sum(
                (
                    amount
                    for row in bank_rows
                    if self._direction(row) == "inflow" and (amount := self._amount(row)) is not None
                ),
                ZERO,
            )
            expense_total = sum(
                (
                    amount
                    for row in bank_rows
                    if self._direction(row) == "outflow" and (amount := self._amount(row)) is not None
                ),
                ZERO,
            )
            return max(income_total, expense_total)
        return self._bank_rows_total_amount(bank_rows)

    def _bank_rows_total_amount(self, bank_rows: list[dict[str, Any]]) -> Decimal:
        amounts = [amount for row in bank_rows if (amount := self._amount(row)) is not None]
        return sum(amounts, ZERO) if amounts else ZERO

    def _no_oa_display_tags(self, bank_rows: list[dict[str, Any]], batch_label: str) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                tags.append(text)

        for row in bank_rows:
            for tag in list(row.get("display_tags") or row.get("tags") or []):
                add(tag)
        add("免OA")
        add(batch_label)
        return tags

    def _no_oa_source_batch_id(self, row: dict[str, Any]) -> str:
        metadata = row.get("special_metadata")
        if not isinstance(metadata, dict):
            return ""
        return str(metadata.get("source_batch_id") or "").strip()

    @staticmethod
    def _summary_field_value(row: dict[str, Any], field_name: str) -> str:
        summary_fields = row.get("summary_fields")
        if not isinstance(summary_fields, dict):
            return ""
        return str(summary_fields.get(field_name) or "").strip()

    @staticmethod
    def _first_non_empty(*values: Any) -> str:
        for value in values:
            text = str(value or "").strip()
            if text:
                return text
        return ""

    @staticmethod
    def _format_decimal_amount(amount: Decimal) -> str:
        return str(amount.quantize(CENT))

    def _serialize_row_for_group(self, row: dict[str, Any], group: CandidateGroup, *, section: str) -> dict[str, Any]:
        payload = deepcopy(row)
        if section != "paired":
            return payload

        relation_field_name = self._relation_field_name(payload["type"])
        payload[relation_field_name] = self._paired_relation_payload(payload, group)
        payload["available_actions"] = self._paired_available_actions(payload)
        return payload

    def _paired_available_actions(self, row: dict[str, Any]) -> list[str]:
        actions = ["detail"]
        if (
            str(row.get("type") or "") == "bank"
            and self._relation_code(row) == NO_OA_BANK_BATCH_RELATION_MODE
            and self._no_oa_source_batch_id(row)
            and self._no_oa_row_is_withdrawable(row)
        ):
            actions.append("withdraw_no_oa_batch")
        return actions

    @staticmethod
    def _no_oa_row_is_withdrawable(row: dict[str, Any]) -> bool:
        metadata = row.get("special_metadata")
        if not isinstance(metadata, dict):
            return False
        if "withdrawable" in metadata:
            return bool(metadata.get("withdrawable"))
        return bool(str(metadata.get("source_batch_id") or "").strip())

    def _paired_relation_payload(self, row: dict[str, Any], group: CandidateGroup) -> dict[str, str]:
        group_kind = self._paired_group_kind(group)
        row_type = str(row["type"])
        original_relation = self._relation_payload(row)
        original_code = str(original_relation.get("code", ""))
        if self._is_processed_exception_projection_row(row):
            return deepcopy(original_relation)
        if original_code == "automatic_match" or original_code in AUTO_PAIRED_CODES:
            return deepcopy(original_relation)
        if row_type == "invoice" and str(row.get("source_kind") or "").strip() == "etc_invoice_summary":
            return {"code": "fully_linked", "label": "已关联ETC发票", "tone": "success"}
        if group_kind == "oa_bank_invoice":
            return {"code": "fully_linked", "label": "完全关联", "tone": "success"}
        if group_kind == "oa_bank":
            if row_type == "oa":
                return {"code": "fully_linked", "label": "已关联流水", "tone": "success"}
            return {"code": "fully_linked", "label": "已关联OA", "tone": "success"}
        if group_kind == "bank_invoice":
            if row_type == "bank":
                return {"code": "fully_linked", "label": "已关联发票", "tone": "success"}
            return {"code": "fully_linked", "label": "已关联流水", "tone": "success"}
        if group_kind == "single" and row_type == "bank" and original_code in AUTO_PAIRED_CODES:
            return deepcopy(original_relation)
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

    @staticmethod
    def _relation_field_name(row_type: str) -> str:
        if row_type == "oa":
            return "oa_bank_relation"
        if row_type == "bank":
            return "invoice_relation"
        return "invoice_bank_relation"

    @staticmethod
    def _paired_group_kind(group: CandidateGroup) -> str:
        has_oa = bool(group.oa_rows)
        has_bank = bool(group.bank_rows)
        has_invoice = bool(group.invoice_rows)
        if has_oa and has_bank and has_invoice:
            return "oa_bank_invoice"
        if has_oa and has_bank:
            return "oa_bank"
        if has_bank and has_invoice:
            return "bank_invoice"
        if has_oa and has_invoice:
            return "oa_invoice"
        return "single"

    def _paired_group_has_enough_row_types(self, group: CandidateGroup) -> bool:
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        if any(self._is_processed_exception_projection_row(row) for row in rows):
            return True
        row_type_count = sum(1 for rows in (group.oa_rows, group.bank_rows, group.invoice_rows) if rows)
        if self._is_turnover_manual_closure_group(group):
            if self._group_has_explicit_paired_requirements(group):
                return self._no_oa_group_has_required_row_types(group)
            return row_type_count >= 3 and self._is_confirmed_active_relation_group(group)
        relation_codes = {self._relation_code(row) for row in rows}
        if relation_codes and relation_codes.issubset(NO_OA_BANK_BATCH_PAIRED_CODES):
            return self._no_oa_group_has_required_row_types(group)
        if row_type_count == 1 and group.bank_rows and not group.oa_rows and not group.invoice_rows:
            relation_codes = {
                str(row.get("invoice_relation", {}).get("code", ""))
                for row in group.bank_rows
            }
            if relation_codes and relation_codes.issubset(SINGLE_BANK_AUTO_PAIRED_CODES) and len(group.bank_rows) == 1:
                return True
            if relation_codes and relation_codes.issubset(MULTI_BANK_AUTO_PAIRED_CODES) and len(group.bank_rows) >= 2:
                return True
        if row_type_count == 2 and group.oa_rows and group.invoice_rows and not group.bank_rows:
            relation_codes = {
                self._relation_code(row)
                for row in [*group.oa_rows, *group.invoice_rows]
            }
            if relation_codes and relation_codes.issubset(OA_INVOICE_AUTO_PAIRED_CODES):
                return True
        if row_type_count == 2 and group.oa_rows and group.bank_rows and not group.invoice_rows:
            relation_codes = {
                self._relation_code(row)
                for row in [*group.oa_rows, *group.bank_rows]
            }
            if relation_codes and relation_codes.issubset(OA_BANK_SETTLEMENT_PAIRED_CODES):
                return True
            if any(self._is_etc_batch_oa_row(row) for row in group.oa_rows):
                return True
            if any(self._is_batch_accounting_relation_row(row) for row in [*group.oa_rows, *group.bank_rows]):
                return True
        return row_type_count >= 3

    def _no_oa_group_has_required_row_types(self, group: CandidateGroup) -> bool:
        if not group.bank_rows:
            return False
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        requires_oa = any(
            self._no_oa_paired_requirement(row, "paired_requires_oa")
            or self._no_oa_paired_requirement(row, "requires_oa")
            for row in rows
        )
        requires_invoice = any(
            self._no_oa_paired_requirement(row, "paired_requires_invoice")
            or self._no_oa_paired_requirement(row, "requires_invoice")
            for row in rows
        )
        return (not requires_oa or bool(group.oa_rows)) and (not requires_invoice or bool(group.invoice_rows))

    @staticmethod
    def _no_oa_paired_requirement(row: dict[str, Any], key: str) -> bool:
        metadata = row.get("special_metadata")
        return isinstance(metadata, dict) and bool(metadata.get(key))

    @staticmethod
    def _group_has_explicit_paired_requirements(group: CandidateGroup) -> bool:
        for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]:
            metadata = row.get("special_metadata")
            if not isinstance(metadata, dict):
                continue
            if any(
                key in metadata
                for key in (
                    "paired_requires_oa",
                    "paired_requires_invoice",
                    "requires_oa",
                    "requires_invoice",
                )
            ):
                return True
        return False

    def _is_turnover_manual_closure_group(self, group: CandidateGroup) -> bool:
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        if not rows:
            return False
        relation_modes = {
            self._string_value(row.get("relation_mode"))
            for row in rows
            if self._string_value(row.get("relation_mode"))
        }
        return relation_modes == {TURNOVER_MANUAL_CLOSURE_RELATION_MODE}

    def _is_confirmed_active_relation_group(self, group: CandidateGroup) -> bool:
        rows = [*group.oa_rows, *group.bank_rows, *group.invoice_rows]
        if not rows:
            return False
        case_ids = {
            self._string_value(row.get("case_id"))
            for row in rows
            if self._string_value(row.get("case_id"))
        }
        if len(case_ids) != 1:
            return False
        relation_modes = {
            self._string_value(row.get("relation_mode"))
            for row in rows
            if self._string_value(row.get("relation_mode"))
        }
        if not relation_modes or "automatic_decision" in relation_modes:
            return False
        relation_codes = {self._relation_code(row) for row in rows}
        if relation_modes == {TURNOVER_MANUAL_CLOSURE_RELATION_MODE}:
            return bool(relation_codes) and relation_codes.issubset({TURNOVER_MANUAL_CLOSURE_RELATION_MODE})
        return bool(relation_codes) and relation_codes.issubset({"fully_linked"})

    @staticmethod
    def _is_batch_accounting_relation_row(row: dict[str, Any]) -> bool:
        metadata = row.get("special_metadata")
        return (
            isinstance(metadata, dict)
            and str(metadata.get("source") or "").strip() == BATCH_ACCOUNTING_RELATION_MODE
        )

    def _group_counterparty(self, group: CandidateGroup) -> str | None:
        attachment_primary_row = self._attachment_group_primary_row(group)
        if attachment_primary_row is not None:
            counterparty = self._counterparty(attachment_primary_row)
            if counterparty is not None:
                return counterparty
        counterparties = {
            counterparty
            for counterparty in (self._counterparty(row) for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows])
            if counterparty is not None
        }
        if len(counterparties) != 1:
            return None
        return next(iter(counterparties))

    def _group_direction(self, group: CandidateGroup) -> str | None:
        directions = {
            direction
            for direction in (self._direction(row) for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows])
            if direction is not None
        }
        if len(directions) != 1:
            return None
        return next(iter(directions))

    def _group_total_amount(self, group: CandidateGroup) -> Decimal | None:
        attachment_primary_row = self._attachment_group_primary_row(group)
        if attachment_primary_row is not None and not group.bank_rows:
            primary_amount = self._amount(attachment_primary_row)
            if primary_amount is not None:
                return primary_amount
        amounts = [amount for amount in (self._amount(row) for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]) if amount is not None]
        if not amounts:
            return None
        return sum(amounts, ZERO)

    def _group_date_buckets(self, group: CandidateGroup) -> set[str]:
        return {
            bucket
            for bucket in (self._date_bucket(row) for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows])
            if bucket is not None
        }

    @staticmethod
    def _date_buckets_compatible(left: set[str], right: set[str]) -> bool:
        if not left or not right:
            return True
        return not left.isdisjoint(right)

    @staticmethod
    def _same_row_types_only(left: CandidateGroup, right: CandidateGroup) -> bool:
        left_types = {row_type for row_type, rows in (("oa", left.oa_rows), ("bank", left.bank_rows), ("invoice", left.invoice_rows)) if rows}
        right_types = {row_type for row_type, rows in (("oa", right.oa_rows), ("bank", right.bank_rows), ("invoice", right.invoice_rows)) if rows}
        return len(left_types) == 1 and len(right_types) == 1 and left_types == right_types

    def _group_type_for_existing_paired_rows(
        self,
        rows: list[dict[str, Any]],
        default_group_type: str,
    ) -> str:
        if any(self._is_processed_exception_projection_row(row) for row in rows):
            return "processed_exception"
        relation_codes = {self._relation_code(row) for row in rows}
        if "fully_linked" in relation_codes:
            return "manual_confirmed"
        if relation_codes and relation_codes.issubset(OA_BANK_SETTLEMENT_PAIRED_CODES):
            return next(iter(relation_codes))
        if relation_codes.intersection({"automatic_match", *AUTO_PAIRED_CODES}):
            return "auto_closed"
        return default_group_type

    def _is_paired_row(self, row: dict[str, Any]) -> bool:
        if self._is_open_exception_projection_row(row) or self._is_ignored_exception_row(row):
            return False
        if self._is_processed_exception_projection_row(row):
            return True
        if self._is_turnover_manual_closure_row(row):
            return True
        if self._is_batch_accounting_relation_row(row):
            return self._relation_code(row) in {BATCH_ACCOUNTING_RELATION_MODE, "fully_linked"}
        return self._relation_code(row) in {"fully_linked", "automatic_match", *AUTO_PAIRED_CODES}

    def _is_turnover_manual_closure_row(self, row: dict[str, Any]) -> bool:
        return (
            self._string_value(row.get("relation_mode")) == TURNOVER_MANUAL_CLOSURE_RELATION_MODE
            and self._relation_code(row) == TURNOVER_MANUAL_CLOSURE_RELATION_MODE
        )

    def _relation_code(self, row: dict[str, Any]) -> str:
        relation = self._relation_payload(row)
        return str(relation.get("code", ""))

    def _relation_tone(self, row: dict[str, Any]) -> str:
        relation = self._relation_payload(row)
        return str(relation.get("tone", ""))

    def _relation_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        if row["type"] == "oa":
            return dict(row.get("oa_bank_relation") or {})
        if row["type"] == "bank":
            return dict(row.get("invoice_relation") or {})
        return dict(row.get("invoice_bank_relation") or {})

    def _group_type_for_open_case_rows(self, rows: list[dict[str, Any]]) -> str:
        if any(self._is_ignored_exception_row(row) for row in rows):
            return "ignored"
        if any(self._is_open_exception_projection_row(row) for row in rows):
            return "open_exception"
        if any(self._is_legacy_exception_row(row) for row in rows):
            return "legacy_exception"
        if any(self._is_open_reconciliation_decision_row(row) for row in rows):
            return "open"
        return "candidate"

    @staticmethod
    def _open_case_group_reason(group_type: str) -> str:
        if group_type == "open_exception":
            return "open_exception_case"
        if group_type == "ignored":
            return "ignored_exception_case"
        if group_type == "legacy_exception":
            return "legacy_exception_case"
        if group_type == "open":
            return "reconciliation_decision_open"
        return "existing_case_candidate"

    def _is_projection_row(self, row: dict[str, Any]) -> bool:
        return str(row.get("projection_version") or "").strip() == EXCEPTION_PROJECTION_VERSION

    def _is_processed_exception_projection_row(self, row: dict[str, Any]) -> bool:
        if not self._is_projection_row(row):
            return False
        projection_kind = str(row.get("projection_kind") or "").strip()
        case_status = str(row.get("case_status") or "").strip()
        relation_mode = str(row.get("relation_mode") or "").strip()
        if projection_kind == "pair_relation":
            return True
        if case_status in {"closed", "settled"}:
            return True
        return bool(relation_mode and self._relation_tone(row) == "success")

    def _is_open_exception_projection_row(self, row: dict[str, Any]) -> bool:
        if not self._is_projection_row(row):
            return False
        case_status = str(row.get("case_status") or "").strip()
        if case_status in {"open", "confirmed", "reopened", "legacy_confirmed"}:
            return True
        return str(row.get("projection_kind") or "").strip() == "exception_case" and self._relation_tone(row) == "danger"

    @staticmethod
    def _is_open_reconciliation_decision_row(row: dict[str, Any]) -> bool:
        decision = row.get("workbench_reconciliation_decision")
        if not isinstance(decision, dict):
            return False
        return (
            str(decision.get("display_state") or "").strip() == "open"
            and str(decision.get("decision_status") or "").strip() == "open"
        )

    def _is_ignored_exception_row(self, row: dict[str, Any]) -> bool:
        if bool(row.get("ignored")):
            return True
        return self._is_projection_row(row) and str(row.get("case_status") or "").strip() == "ignored"

    def _is_legacy_exception_row(self, row: dict[str, Any]) -> bool:
        if self._is_projection_row(row):
            return False
        return bool(row.get("handled_exception")) and self._relation_tone(row) == "danger"

    def _group_relation_mode(self, group: CandidateGroup) -> str:
        for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]:
            relation_mode = str(row.get("relation_mode") or "").strip()
            if relation_mode:
                return relation_mode
        return ""

    def _group_display_tags(self, group: CandidateGroup) -> list[str]:
        tags: list[str] = []
        seen: set[str] = set()
        for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]:
            for tag in list(row.get("display_tags") or []):
                text = str(tag or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                tags.append(text)
        return tags

    def _group_projection_metadata(self, group: CandidateGroup) -> dict[str, Any]:
        if group.metadata:
            return deepcopy(group.metadata)
        for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]:
            metadata = row.get("group_metadata")
            if isinstance(metadata, dict):
                return deepcopy(metadata)
        if group.group_type not in {"open_exception", "processed_exception", "ignored", "legacy_exception"}:
            return {}
        case_id = self._case_id([*group.oa_rows, *group.bank_rows, *group.invoice_rows][0])
        metadata: dict[str, Any] = {
            "group_id": group.group_id,
            "group_type": group.group_type,
        }
        if case_id:
            metadata["case_id"] = case_id
        relation_mode = self._group_relation_mode(group)
        if relation_mode:
            metadata["relation_mode"] = relation_mode
        display_tags = self._group_display_tags(group)
        if display_tags:
            metadata["display_tags"] = display_tags
        return metadata

    def _group_processed_exception_summary(self, group: CandidateGroup) -> dict[str, Any]:
        if group.group_type != "processed_exception":
            return {}
        for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]:
            summary = row.get("processed_exception_summary")
            if isinstance(summary, dict):
                return deepcopy(summary)
        metadata = self._group_projection_metadata(group)
        if not metadata:
            return {}
        return {
            "case_id": metadata.get("case_id", ""),
            "relation_mode": metadata.get("relation_mode", ""),
            "display_tags": deepcopy(metadata.get("display_tags") or []),
        }

    def _case_id(self, row: dict[str, Any]) -> str | None:
        case_id = row.get("case_id")
        if case_id in (None, ""):
            return None
        return str(case_id)

    def _temp_key(self, row: dict[str, Any]) -> str | None:
        if self._is_open_reconciliation_decision_row(row):
            return None
        direction = self._direction(row)
        counterparty = self._counterparty(row)
        amount = self._amount(row)
        if direction is None or counterparty is None or amount is None:
            return None
        return f"{direction}|{counterparty}|{amount.quantize(CENT)}"

    def _candidate_key(self, row: dict[str, Any]) -> str | None:
        if self._is_open_reconciliation_decision_row(row):
            return None
        direction = self._direction(row)
        counterparty = self._counterparty(row)
        amount_bucket = self._amount_bucket(self._amount(row))
        date_bucket = self._date_bucket(row)
        if direction is None or counterparty is None or amount_bucket is None:
            return None
        return f"{direction}|{counterparty}|{amount_bucket}|{date_bucket or 'na'}"

    def _month(self, row: dict[str, Any]) -> str | None:
        for field_name in ("issue_date", "trade_time", "pay_receive_time"):
            text = self._string_value(row.get(field_name))
            if text:
                return text[:7]
        return None

    def _date_bucket(self, row: dict[str, Any]) -> str | None:
        parsed_date = self._date_value(row)
        if parsed_date is None:
            return None
        iso_year, iso_week, _ = parsed_date.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"

    def _date_value(self, row: dict[str, Any]) -> date | None:
        for field_name in ("trade_time", "pay_receive_time", "issue_date"):
            text = self._string_value(row.get(field_name))
            if not text:
                continue
            normalized = text.replace("/", "-")
            for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
                try:
                    return datetime.strptime(normalized[:16] if fmt.endswith("%H:%M") else normalized[:10], fmt).date()
                except ValueError:
                    continue
        return None

    def _direction(self, row: dict[str, Any]) -> str | None:
        row_type = row["type"]
        if row_type == "oa":
            apply_type = self._string_value(row.get("apply_type")) or ""
            return "inflow" if ("收" in apply_type and "付" not in apply_type) else "outflow"
        if row_type == "bank":
            debit_amount = self._amount_from_value(row.get("debit_amount"))
            credit_amount = self._amount_from_value(row.get("credit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return "outflow"
            if credit_amount is not None and credit_amount > ZERO:
                return "inflow"
            return None
        return invoice_flow_direction_from_row(row)

    def _counterparty(self, row: dict[str, Any]) -> str | None:
        row_type = row["type"]
        if row_type in {"oa", "bank"}:
            value = self._string_value(row.get("counterparty_name"))
            return normalize_name(value) if value else None

        party_field = invoice_counterparty_field_from_row(row)
        if party_field is None:
            return None
        value = self._string_value(row.get(party_field))
        return normalize_name(value) if value else None

    def _amount(self, row: dict[str, Any]) -> Decimal | None:
        if row["type"] == "bank":
            debit_amount = self._amount_from_value(row.get("debit_amount"))
            if debit_amount is not None and debit_amount > ZERO:
                return debit_amount
            return self._amount_from_value(row.get("credit_amount"))
        if self._is_oa_attachment_invoice_row(row):
            total_with_tax = self._amount_from_value(row.get("total_with_tax"))
            if total_with_tax is not None:
                return total_with_tax
        return self._amount_from_value(row.get("amount"))

    def _invoice_gross_amount(self, row: dict[str, Any]) -> Decimal | None:
        total_with_tax = self._amount_from_value(row.get("total_with_tax"))
        if total_with_tax is not None:
            return total_with_tax
        return self._amount(row)

    def _find_invoice_sum_match(
        self,
        invoice_rows: list[dict[str, Any]],
        target_amount: Decimal,
    ) -> list[dict[str, Any]] | None:
        candidates = [
            (row, amount)
            for row in sorted(invoice_rows, key=lambda item: (str(item.get("issue_date", "")), str(item.get("id", ""))))
            if (amount := self._invoice_gross_amount(row)) is not None and amount > ZERO
        ]
        if not candidates:
            return None
        if len(candidates) > MAX_AGGREGATED_OA_INVOICE_CANDIDATES:
            return None
        candidate_total = sum((amount for _, amount in candidates), ZERO).quantize(CENT)
        if candidate_total == target_amount:
            return [row for row, _ in candidates] if len(candidates) > 1 else None

        target_cents = self._to_cents(target_amount)
        if target_cents is None:
            return None
        states: dict[int, tuple[dict[str, Any], ...]] = {0: ()}
        ambiguous_sums: set[int] = set()
        for row, amount in candidates:
            amount_cents = self._to_cents(amount)
            if amount_cents is None or amount_cents > target_cents:
                continue
            for current_total, current_rows in list(states.items()):
                next_total = current_total + amount_cents
                if next_total > target_cents:
                    continue
                next_rows = (*current_rows, row)
                if next_total not in states:
                    states[next_total] = next_rows
                elif {str(item.get("id", "")) for item in states[next_total]} != {
                    str(item.get("id", "")) for item in next_rows
                }:
                    ambiguous_sums.add(next_total)
                if len(states) > MAX_INVOICE_SUBSET_SUM_STATES:
                    return None
        if target_cents in ambiguous_sums:
            return None
        matched_rows = states.get(target_cents)
        if not matched_rows or len(matched_rows) <= 1:
            return None
        return list(matched_rows)

    def _attachment_invoice_reconciliation_amount(self, row: dict[str, Any]) -> Decimal | None:
        if self._is_oa_attachment_invoice_row(row):
            total_with_tax = self._amount_from_value(row.get("total_with_tax"))
            if total_with_tax is not None:
                return total_with_tax
        return self._amount(row)

    def _amount_bucket(self, amount: Decimal | None) -> Decimal | None:
        if amount is None:
            return None
        absolute_amount = abs(amount)
        if absolute_amount >= Decimal("1000"):
            bucket = Decimal("100")
        elif absolute_amount >= Decimal("100"):
            bucket = Decimal("10")
        else:
            bucket = Decimal("1")
        return (amount / bucket).quantize(Decimal("1")) * bucket

    @staticmethod
    def _amount_from_value(value: Any) -> Decimal | None:
        if value in (None, "", "--", "—"):
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(CENT)
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _to_cents(amount: Decimal) -> int | None:
        try:
            return int((amount.quantize(CENT) * 100).to_integral_exact())
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _string_value(value: Any) -> str | None:
        if value in (None, "", "--", "—"):
            return None
        text = str(value).strip()
        return text or None

    def _next_temp_group_id(self) -> str:
        return f"temp:{next(self._group_counter):04d}"

    @staticmethod
    def _oa_attachment_source_group_id(source_id: str) -> str:
        return f"source:oa_attachment:{source_id}"

    @staticmethod
    def _is_oa_attachment_invoice_row(row: dict[str, Any]) -> bool:
        return str(row.get("source_kind", "")) == OA_ATTACHMENT_INVOICE_SOURCE_KIND

    @staticmethod
    def _is_oa_attachment_evidence_row(row: dict[str, Any]) -> bool:
        return str(row.get("source_kind", "")).strip() in OA_ATTACHMENT_EVIDENCE_SOURCE_KINDS

    @classmethod
    def _is_non_invoice_oa_attachment_evidence_row(cls, row: dict[str, Any]) -> bool:
        return cls._is_oa_attachment_evidence_row(row) and not cls._is_oa_attachment_invoice_row(row)

    def _oa_attachment_evidence_source_id(self, row: dict[str, Any], oa_row_ids: set[str] | None = None) -> str | None:
        if row.get("type") != "invoice":
            return None
        if not self._is_oa_attachment_invoice_row(row):
            return None
        if not self._can_join_oa_attachment_source_group(row):
            return None
        source_ids = oa_attachment_source_ids(row)
        if not source_ids:
            return None
        if oa_row_ids is not None:
            if not oa_row_ids:
                return None
            for source_id in source_ids:
                if source_id in oa_row_ids:
                    return source_id
                parent_source_id = oa_attachment_parent_oa_id(source_id)
                if parent_source_id in oa_row_ids:
                    return parent_source_id
            return None
        return oa_attachment_parent_oa_id(source_ids[0])

    def _can_join_oa_attachment_source_group(self, row: dict[str, Any]) -> bool:
        if self._is_paired_row(row):
            return False
        if self._is_ignored_exception_row(row):
            return False
        if self._is_open_exception_projection_row(row) or self._is_processed_exception_projection_row(row):
            return False
        if self._is_legacy_exception_row(row):
            return False
        case_id = self._case_id(row)
        return case_id is None or case_id.startswith("candidate:")

    @staticmethod
    def _is_etc_batch_oa_row(row: dict[str, Any]) -> bool:
        if str(row.get("source", "")).strip() == ETC_BATCH_SOURCE:
            return True
        if str(row.get("etc_batch_id") or row.get("etcBatchId") or "").strip():
            return True
        tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
        return ETC_BATCH_TAG in tags

    def _is_open_oa_multi_invoice_candidate_row(self, row: dict[str, Any]) -> bool:
        if row.get("type") != "oa" or self._case_id(row) or self._is_paired_row(row):
            return False
        amount = self._amount(row)
        if amount is None or amount <= ZERO:
            return False
        return bool(self._aggregated_oa_invoice_month_candidates(row))

    def _is_manual_imported_open_invoice_row(self, row: dict[str, Any]) -> bool:
        if row.get("type") != "invoice":
            return False
        if self._case_id(row) or self._is_paired_row(row):
            return False
        return not self._is_oa_attachment_evidence_row(row)

    def _invoice_matches_aggregated_oa_candidate(self, invoice_row: dict[str, Any], oa_row: dict[str, Any]) -> bool:
        if self._direction(invoice_row) != self._direction(oa_row):
            return False
        oa_counterparty = self._counterparty(oa_row)
        if oa_counterparty is not None and self._counterparty(invoice_row) != oa_counterparty:
            return False
        return self._invoice_month_matches_aggregated_oa(invoice_row, oa_row)

    def _invoice_month_matches_aggregated_oa(self, invoice_row: dict[str, Any], oa_row: dict[str, Any]) -> bool:
        invoice_month = self._month(invoice_row)
        if invoice_month is None:
            return False
        oa_months = self._aggregated_oa_invoice_month_candidates(oa_row)
        return bool(oa_months) and invoice_month in oa_months

    def _aggregated_oa_invoice_month_candidates(self, row: dict[str, Any]) -> set[str]:
        candidate_months: set[str] = set()
        detail_fields = self._detail_fields(row)
        for raw_value in (
            row.get("pay_receive_time"),
            row.get("apply_date"),
            row.get("_month"),
            detail_fields.get("申请日期"),
        ):
            month = self._month_from_value(raw_value)
            if month is None:
                continue
            candidate_months.add(month)
            previous_month = self._previous_month(month)
            if previous_month is not None:
                candidate_months.add(previous_month)
        return candidate_months

    @staticmethod
    def _detail_fields(row: dict[str, Any]) -> dict[str, Any]:
        detail_fields = row.get("_detail_fields")
        if isinstance(detail_fields, dict):
            return detail_fields
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            return detail_fields
        return {}

    def _month_from_value(self, value: Any) -> str | None:
        text = self._string_value(value)
        if not text:
            return None
        normalized = text.replace("/", "-")
        month = normalized[:7]
        if len(month) != 7 or month[4] != "-":
            return None
        try:
            year = int(month[:4])
            month_number = int(month[5:7])
        except ValueError:
            return None
        if year < 1 or not 1 <= month_number <= 12:
            return None
        return month

    @staticmethod
    def _previous_month(month: str) -> str | None:
        try:
            year = int(month[:4])
            month_number = int(month[5:7])
        except ValueError:
            return None
        if month_number == 1:
            return f"{year - 1}-12"
        if 2 <= month_number <= 12:
            return f"{year}-{month_number - 1:02d}"
        return None

    def _attachment_group_primary_row(self, group: CandidateGroup) -> dict[str, Any] | None:
        if len(group.oa_rows) != 1 or group.bank_rows:
            return None
        if not group.invoice_rows or not all(self._is_oa_attachment_invoice_row(row) for row in group.invoice_rows):
            return None
        return group.oa_rows[0]
