from __future__ import annotations

from copy import deepcopy
from collections import OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from itertools import count
from typing import Any

from fin_ops_platform.services.imports import normalize_name


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SINGLE_BANK_AUTO_PAIRED_CODES = {"salary_personal_auto_match"}
MULTI_BANK_AUTO_PAIRED_CODES = {"internal_transfer_pair"}
OA_INVOICE_AUTO_PAIRED_CODES = {"oa_invoice_offset_auto_match"}
AUTO_PAIRED_CODES = {*SINGLE_BANK_AUTO_PAIRED_CODES, *MULTI_BANK_AUTO_PAIRED_CODES, *OA_INVOICE_AUTO_PAIRED_CODES}
ETC_BATCH_SOURCE = "etc_batch"
ETC_BATCH_TAG = "ETC批量提交"
MAX_AGGREGATED_OA_INVOICE_CANDIDATES = 160
MAX_INVOICE_SUBSET_SUM_STATES = 20000


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
    ) -> dict[str, Any]:
        all_rows = [*oa_rows, *bank_rows, *invoice_rows]
        paired_rows = [row for row in all_rows if self._is_paired_row(row)]
        open_rows = [row for row in all_rows if not self._is_paired_row(row)]

        paired_groups = self._build_case_or_temp_groups(paired_rows, default_group_type="manual_confirmed")
        valid_paired_groups, demoted_paired_rows = self._split_valid_and_incomplete_paired_groups(paired_groups)
        open_case_groups, unattached_open_rows = self._build_open_case_groups([*open_rows, *demoted_paired_rows])
        target_groups_by_temp_key = self._index_target_groups([*valid_paired_groups, *open_case_groups.values()])
        remaining_rows = self._attach_unique_rows_to_existing_groups(unattached_open_rows, target_groups_by_temp_key)

        aggregated_oa_invoice_groups, remaining_rows = self._build_aggregated_oa_invoice_sum_groups(remaining_rows)
        standalone_temp_groups = self._build_temp_groups(remaining_rows)
        merged_open_case_groups = self._merge_open_case_groups(list(open_case_groups.values()))
        promoted_open_case_groups, candidate_open_case_groups = self._split_promoted_and_candidate_groups(
            merged_open_case_groups
        )
        promoted_groups, candidate_groups = self._split_promoted_and_candidate_groups(standalone_temp_groups)

        open_groups = [*candidate_open_case_groups, *aggregated_oa_invoice_groups, *candidate_groups]
        paired_output = [*valid_paired_groups, *promoted_open_case_groups, *promoted_groups]

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
            demoted_rows.extend([*group.oa_rows, *group.bank_rows, *group.invoice_rows])
        return valid_groups, demoted_rows

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
            elif temp_key is not None and group.temp_key != temp_key and not self._is_oa_attachment_invoice_row(row):
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
                groups[group_id] = CandidateGroup(
                    group_id=group_id,
                    group_type="candidate",
                    match_confidence="medium",
                    reason="existing_case_candidate",
                    temp_key=temp_key,
                )
            group = groups[group_id]
            group.append(row)
            if group.temp_key is None:
                group.temp_key = temp_key
            elif temp_key is not None and group.temp_key != temp_key and not self._is_oa_attachment_invoice_row(row):
                group.temp_key = None
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
                groups[group_key] = CandidateGroup(
                    group_id=self._next_temp_group_id(),
                    group_type="candidate",
                    match_confidence="low",
                    reason="temp_candidate_group" if temp_key else "standalone_row_group",
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

    def _should_merge_open_case_groups(self, left: CandidateGroup, right: CandidateGroup) -> bool:
        if not (self._attachment_group_primary_row(left) or self._attachment_group_primary_row(right)):
            return False
        return self._should_merge_candidate_groups(left, right)

    def _should_merge_candidate_groups(self, left: CandidateGroup, right: CandidateGroup) -> bool:
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
        if any(bool(row.get("handled_exception")) or bool(row.get("auto_close_suppressed")) for row in rows):
            return False
        if self._qualifies_for_attachment_invoice_auto_close(group):
            return True
        if self._qualifies_for_etc_batch_oa_bank_auto_close(group):
            return True

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
        return {
            "group_id": group.group_id,
            "group_type": group.group_type,
            "match_confidence": group.match_confidence,
            "reason": group.reason,
            "oa_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.oa_rows],
            "bank_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.bank_rows],
            "invoice_rows": [self._serialize_row_for_group(row, group, section=section) for row in group.invoice_rows],
        }

    def _serialize_row_for_group(self, row: dict[str, Any], group: CandidateGroup, *, section: str) -> dict[str, Any]:
        payload = deepcopy(row)
        if section != "paired":
            return payload

        relation_field_name = self._relation_field_name(payload["type"])
        payload[relation_field_name] = self._paired_relation_payload(payload, group)
        payload["available_actions"] = ["detail"]
        return payload

    def _paired_relation_payload(self, row: dict[str, Any], group: CandidateGroup) -> dict[str, str]:
        group_kind = self._paired_group_kind(group)
        row_type = str(row["type"])
        original_relation = self._relation_payload(row)
        original_code = str(original_relation.get("code", ""))
        if original_code == "automatic_match" or original_code in OA_INVOICE_AUTO_PAIRED_CODES:
            return deepcopy(original_relation)
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
        row_type_count = sum(1 for rows in (group.oa_rows, group.bank_rows, group.invoice_rows) if rows)
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
            if any(self._is_etc_batch_oa_row(row) for row in group.oa_rows):
                return True
        return row_type_count >= 3

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
        relation_codes = {self._relation_code(row) for row in rows}
        if "fully_linked" in relation_codes:
            return "manual_confirmed"
        if relation_codes.intersection({"automatic_match", *AUTO_PAIRED_CODES}):
            return "auto_closed"
        return default_group_type

    def _is_paired_row(self, row: dict[str, Any]) -> bool:
        return self._relation_code(row) in {"fully_linked", "automatic_match", *AUTO_PAIRED_CODES}

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

    def _case_id(self, row: dict[str, Any]) -> str | None:
        case_id = row.get("case_id")
        if case_id in (None, ""):
            return None
        return str(case_id)

    def _temp_key(self, row: dict[str, Any]) -> str | None:
        direction = self._direction(row)
        counterparty = self._counterparty(row)
        amount = self._amount(row)
        if direction is None or counterparty is None or amount is None:
            return None
        return f"{direction}|{counterparty}|{amount.quantize(CENT)}"

    def _candidate_key(self, row: dict[str, Any]) -> str | None:
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
        invoice_type = self._string_value(row.get("invoice_type")) or ""
        return "inflow" if "销" in invoice_type else "outflow"

    def _counterparty(self, row: dict[str, Any]) -> str | None:
        row_type = row["type"]
        if row_type in {"oa", "bank"}:
            value = self._string_value(row.get("counterparty_name"))
            return normalize_name(value) if value else None

        invoice_type = self._string_value(row.get("invoice_type")) or ""
        value = self._string_value(row.get("buyer_name" if "销" in invoice_type else "seller_name"))
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
            amount = self._amount_from_value(row.get("amount"))
            if amount is not None:
                return amount
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
    def _is_oa_attachment_invoice_row(row: dict[str, Any]) -> bool:
        return str(row.get("source_kind", "")) == "oa_attachment_invoice"

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
        return not self._is_oa_attachment_invoice_row(row)

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
