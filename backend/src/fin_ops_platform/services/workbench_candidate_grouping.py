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
AUTO_PAIRED_CODES = {*SINGLE_BANK_AUTO_PAIRED_CODES, *MULTI_BANK_AUTO_PAIRED_CODES}


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

        standalone_temp_groups = self._build_temp_groups(remaining_rows)
        promoted_open_case_groups, candidate_open_case_groups = self._split_promoted_and_candidate_groups(
            list(open_case_groups.values())
        )
        promoted_groups, candidate_groups = self._split_promoted_and_candidate_groups(standalone_temp_groups)

        open_groups = [*candidate_open_case_groups, *candidate_groups]
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
            elif temp_key is not None and group.temp_key != temp_key:
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
            elif temp_key is not None and group.temp_key != temp_key:
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
        total_count = len(group.oa_rows) + len(group.bank_rows) + len(group.invoice_rows)
        if total_count < 2:
            return False
        if len(group.oa_rows) > 1 or len(group.bank_rows) > 1 or len(group.invoice_rows) > 1:
            return False
        if not group.bank_rows:
            return False
        if group.oa_rows and self._direction(group.oa_rows[0]) != self._direction(group.bank_rows[0]):
            return False
        if group.invoice_rows and self._direction(group.invoice_rows[0]) != self._direction(group.bank_rows[0]):
            return False
        amounts = {self._amount(row) for row in [*group.oa_rows, *group.bank_rows, *group.invoice_rows]}
        return len(amounts) == 1 and None not in amounts

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

    @staticmethod
    def _paired_group_has_enough_row_types(group: CandidateGroup) -> bool:
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
        return row_type_count >= 2

    def _group_counterparty(self, group: CandidateGroup) -> str | None:
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
        return self._amount_from_value(row.get("amount"))

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
    def _string_value(value: Any) -> str | None:
        if value in (None, "", "--", "—"):
            return None
        text = str(value).strip()
        return text or None

    def _next_temp_group_id(self) -> str:
        return f"temp:{next(self._group_counter):04d}"
