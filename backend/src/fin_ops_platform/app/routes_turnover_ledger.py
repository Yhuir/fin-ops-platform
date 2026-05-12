from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.turnover_ledger_export_service import TurnoverLedgerExportService
from fin_ops_platform.services.turnover_ledger_service import TurnoverLedgerService
from fin_ops_platform.services.turnover_relation_service import TurnoverRelationService


VALID_EXTRA_RATE_TYPES = {"annual", "monthly", "none"}
VALID_FAMILIES = {"all", "personal", "company", "bank", "business"}
MONEY_QUANT = Decimal("0.01")
RATE_QUANT = Decimal("0.000001")
ZERO = Decimal("0.00")


class TurnoverLedgerExtraValidationError(ValueError):
    pass


class InMemoryTurnoverLedgerExtraService:
    def __init__(self, snapshot: dict[str, object] | None = None) -> None:
        self._extras: dict[str, dict[str, object]] = {}
        if isinstance(snapshot, dict):
            for item in list(snapshot.get("extras") or []):
                if not isinstance(item, dict):
                    continue
                relation_id = str(item.get("relation_id") or "").strip()
                if relation_id:
                    self._extras[relation_id] = self._normalize_extra(relation_id, item, actor=None, touch=False)

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object] | None) -> "InMemoryTurnoverLedgerExtraService":
        return cls(snapshot)

    def snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "extras": [dict(extra) for _, extra in sorted(self._extras.items())],
        }

    def get(self, relation_id: str) -> dict[str, object]:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        return dict(self._extras.get(normalized_relation_id) or self._default_extra(normalized_relation_id))

    def upsert(self, relation_id: str, payload: dict[str, object], *, actor: str) -> dict[str, object]:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        if not isinstance(payload, dict):
            raise TurnoverLedgerExtraValidationError("payload must be an object.")
        current = self.get(normalized_relation_id)
        merged = {**current, **payload, "relation_id": normalized_relation_id}
        normalized = self._normalize_extra(normalized_relation_id, merged, actor=actor, touch=True)
        self._extras[normalized_relation_id] = normalized
        return dict(normalized)

    @staticmethod
    def _normalize_relation_id(relation_id: str) -> str:
        normalized = str(relation_id or "").strip()
        if not normalized:
            raise TurnoverLedgerExtraValidationError("relation_id is required.")
        return normalized

    @classmethod
    def _default_extra(cls, relation_id: str) -> dict[str, object]:
        return {
            "relation_id": relation_id,
            "interest_rate_type": "none",
            "interest_rate_value": "0.000000",
            "interest_paid_amount": "0.00",
            "interest_paid_date": None,
            "interest_payment_method": "",
            "note": "",
            "updated_at": None,
            "updated_by": None,
        }

    @classmethod
    def _normalize_extra(
        cls,
        relation_id: str,
        payload: dict[str, object],
        *,
        actor: str | None,
        touch: bool,
    ) -> dict[str, object]:
        rate_type = str(payload.get("interest_rate_type") or "none").strip().lower()
        if rate_type not in VALID_EXTRA_RATE_TYPES:
            raise TurnoverLedgerExtraValidationError("interest_rate_type must be annual, monthly, or none.")
        rate_value = ZERO if rate_type == "none" else cls._non_negative_decimal(payload.get("interest_rate_value"), RATE_QUANT)
        paid_amount = cls._non_negative_decimal(payload.get("interest_paid_amount"), MONEY_QUANT)
        paid_date = cls._date_or_none(payload.get("interest_paid_date"))
        now = datetime.now(UTC).isoformat() if touch else payload.get("updated_at")
        updated_by = actor if touch else payload.get("updated_by")
        return {
            "relation_id": relation_id,
            "interest_rate_type": rate_type,
            "interest_rate_value": f"{rate_value.quantize(RATE_QUANT):.6f}",
            "interest_paid_amount": f"{paid_amount.quantize(MONEY_QUANT):.2f}",
            "interest_paid_date": paid_date,
            "interest_payment_method": cls._trim_text(payload.get("interest_payment_method"), max_length=80),
            "note": cls._trim_text(payload.get("note"), max_length=500),
            "updated_at": str(now) if now else None,
            "updated_by": str(updated_by) if updated_by else None,
        }

    @staticmethod
    def _non_negative_decimal(value: object, quant: Decimal) -> Decimal:
        if value is None or str(value).strip() == "":
            return ZERO.quantize(quant)
        try:
            amount = Decimal(str(value).replace(",", "").strip()).quantize(quant)
        except (InvalidOperation, ValueError):
            raise TurnoverLedgerExtraValidationError("decimal fields must be valid numbers.") from None
        if amount < ZERO:
            raise TurnoverLedgerExtraValidationError("decimal fields must be non-negative.")
        return amount

    @staticmethod
    def _date_or_none(value: object) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise TurnoverLedgerExtraValidationError("date fields must be ISO date strings.") from None

    @staticmethod
    def _trim_text(value: object, *, max_length: int) -> str:
        return str(value or "").strip()[:max_length]


class TurnoverLedgerApiRoutes:
    def __init__(
        self,
        *,
        ledger_service: TurnoverLedgerService,
        relation_service: TurnoverRelationService,
        extra_service: Any | None = None,
    ) -> None:
        self._ledger_service = ledger_service
        self._relation_service = relation_service
        self._extra_service = extra_service or InMemoryTurnoverLedgerExtraService()
        self._export_service = TurnoverLedgerExportService(self.list_grouped_ledger)

    def list_ledger(
        self,
        *,
        view: str | None = None,
        family: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        if str(view or "").strip().lower() == "grouped":
            return self.list_grouped_ledger(
                family=family,
                status=status,
                page=page,
                page_size=page_size,
            )
        return self._ledger_service.list_ledger(
            family=family,
            status=status,
            page=page,
            page_size=page_size,
        )

    def list_grouped_ledger(
        self,
        *,
        family: str = "all",
        status: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, object]:
        list_grouped = getattr(self._ledger_service, "list_grouped_ledger", None)
        if callable(list_grouped):
            payload = list_grouped(family=family, status=status, page=page, page_size=page_size)
            return self._normalize_grouped_payload(payload)
        flat_payload = self._ledger_service.list_ledger(
            family=family,
            status=status,
            page=page,
            page_size=page_size,
        )
        return self._normalize_grouped_payload(self._flat_payload_to_grouped(flat_payload))

    def get_relation(self, relation_id: str) -> dict[str, object]:
        return self._ledger_service.get_relation_detail(relation_id)

    def get_relation_extra(self, relation_id: str) -> dict[str, object]:
        self._ledger_service.get_relation_detail(relation_id)
        extra = self._extra_service.get(relation_id)
        if extra is None:
            extra = InMemoryTurnoverLedgerExtraService._default_extra(str(relation_id or "").strip())
        return {"extra": extra}

    def update_relation_extra(
        self,
        relation_id: str,
        payload: dict[str, object],
        *,
        actor: str,
    ) -> dict[str, object]:
        self._ledger_service.get_relation_detail(relation_id)
        extra = self._extra_service.upsert(relation_id, payload, actor=actor)
        detail = self._ledger_service.get_relation_detail(relation_id)
        row = dict(detail.get("row") or {})
        row.update(self._row_extra_fields(extra))
        return {"extra": extra, "row": row}

    def extras_snapshot(self) -> dict[str, object]:
        snapshot = getattr(self._extra_service, "snapshot", None)
        if not callable(snapshot):
            return {"version": 1, "extras": []}
        return snapshot()

    def export_preview(self, *, family: str = "all", limit: int = 20) -> dict[str, object]:
        return self._export_service.preview(family=family, limit=limit)

    def export(self, *, family: str = "all", today: date | None = None) -> tuple[str, bytes]:
        return self._export_service.export(family=family, today=today)

    def confirm_relation(
        self,
        *,
        bank_row_ids: list[str],
        actor: str,
        note: str | None = None,
    ) -> dict[str, object]:
        relation = self._relation_service.confirm_relation(
            bank_row_ids,
            actor=actor,
            note=note,
        )
        return {"relation": relation}

    def withdraw_relation(
        self,
        *,
        relation_id: str,
        actor: str,
        note: str | None = None,
    ) -> dict[str, object]:
        relation = self._relation_service.withdraw_relation(
            relation_id,
            actor=actor,
            note=note,
        )
        return {"relation": relation}

    def _flat_payload_to_grouped(self, payload: dict[str, object]) -> dict[str, object]:
        groups_by_key: dict[tuple[str, str], dict[str, object]] = {}
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_with_extra = dict(row)
            relation_id = str(row_with_extra.get("relation_id") or "")
            if relation_id:
                row_with_extra.update(self._row_extra_fields(self._extra_service.get(relation_id)))
            family = str(row_with_extra.get("family") or "")
            counterparty = str(row_with_extra.get("counterparty_name") or "")
            key = (family, counterparty)
            group = groups_by_key.setdefault(
                key,
                {
                    "group_id": f"counterparty:{family}:{counterparty}",
                    "counterparty_name": counterparty,
                    "family": family,
                    "family_label": row_with_extra.get("family_label") or "",
                    "pending_direction": self._pending_direction(row_with_extra),
                    "pending_direction_label": self._pending_direction_label(row_with_extra),
                    "pending_amount": "0.00",
                    "row_span": 0,
                    "group_tone": row_with_extra.get("row_tone") or "muted",
                    "rows": [],
                },
            )
            group_rows = list(group.get("rows") or [])
            grouped_row = self._grouped_row_from_flat_row(row_with_extra)
            group_rows.append(grouped_row)
            group["rows"] = group_rows
            group["row_span"] = len(group_rows)
            group["pending_amount"] = self._format_money(
                self._money(group.get("pending_amount")) + self._money(row_with_extra.get("balance_amount"))
            )
        groups = list(groups_by_key.values())
        return {
            "summary": payload.get("summary") or {},
            "family_summaries": list(payload.get("family_summaries") or []),
            "groups": groups,
            "pagination": {
                **dict(payload.get("pagination") or {}),
                "total": len(groups),
            },
            "filters": dict(payload.get("filters") or {}),
        }

    @classmethod
    def _normalize_grouped_payload(cls, payload: dict[str, object]) -> dict[str, object]:
        normalized_groups: list[dict[str, object]] = []
        for group in list(payload.get("groups") or []):
            if not isinstance(group, dict):
                continue
            normalized_group = dict(group)
            legacy_rows = [row for row in list(group.get("rows") or []) if isinstance(row, dict)]
            explicit_summary = group.get("summary_row")
            summary_row = dict(explicit_summary) if isinstance(explicit_summary, dict) else None
            explicit_lot_rows = [row for row in list(group.get("lot_rows") or []) if isinstance(row, dict)]
            explicit_flow_rows = [row for row in list(group.get("flow_rows") or []) if isinstance(row, dict)]
            explicit_allocation_lots = [
                row for row in list(group.get("allocation_lots") or []) if isinstance(row, dict)
            ]
            if summary_row is None:
                summary_row = cls._summary_row_from_legacy_rows(legacy_rows)
            lot_rows = [cls._normalized_lot_row(row) for row in explicit_lot_rows]
            allocation_lots = [
                cls._normalized_allocation_lot(row) for row in (explicit_allocation_lots or explicit_lot_rows)
            ]
            flow_rows = cls._normalized_flow_rows(explicit_flow_rows)
            summary_row = cls._normalized_summary_row(summary_row)
            normalized_group["summary_row"] = summary_row
            normalized_group["flow_rows"] = flow_rows
            normalized_group["allocation_lots"] = allocation_lots
            normalized_group["lot_rows"] = lot_rows
            normalized_group["row_span"] = 1 + len(flow_rows)
            normalized_group.pop("rows", None)
            normalized_groups.append(normalized_group)
        return {
            **dict(payload),
            "groups": normalized_groups,
        }

    @classmethod
    def _summary_row_from_legacy_rows(cls, rows: list[dict[str, object]]) -> dict[str, object]:
        for row in rows:
            if str(row.get("row_kind") or "").strip().lower() == "summary":
                return dict(row)
        return dict(rows[0]) if rows else {}

    @staticmethod
    def _normalized_summary_row(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "summary"
        normalized["display_level"] = "group_summary"
        return normalized

    @staticmethod
    def _normalized_lot_row(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "lot"
        return normalized

    @classmethod
    def _normalized_flow_rows(cls, rows: list[dict[str, object]]) -> list[dict[str, object]]:
        normalized_rows: list[dict[str, object]] = []
        seen_source_ids: set[str] = set()
        for row in rows:
            normalized = dict(row)
            normalized["row_kind"] = "flow"
            source_bank_row_id = str(normalized.get("source_bank_row_id") or "").strip()
            if source_bank_row_id:
                if source_bank_row_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_bank_row_id)
            normalized_rows.append(normalized)
        return normalized_rows

    @staticmethod
    def _normalized_allocation_lot(row: dict[str, object]) -> dict[str, object]:
        normalized = dict(row)
        normalized["row_kind"] = "allocation_lot"
        return normalized

    @classmethod
    def _grouped_row_from_flat_row(cls, row: dict[str, object]) -> dict[str, object]:
        principal = cls._format_money(cls._money(row.get("principal_amount")))
        settled = cls._format_money(cls._money(row.get("settled_amount")))
        return {
            "relation_id": str(row.get("relation_id") or ""),
            "status": row.get("status") or "",
            "status_label": row.get("status_label") or "",
            "row_tone": row.get("row_tone") or "muted",
            "borrow_amount": row.get("borrow_amount") or principal,
            "borrow_date": cls._date_text(row.get("borrow_date") or row.get("first_transaction_at")),
            "borrow_direction": row.get("borrow_direction") or ("income" if row.get("business_type") == "borrow_in" else "expense"),
            "repayment_amount": row.get("repayment_amount") or settled,
            "repayment_date": cls._date_text(row.get("repayment_date") or row.get("last_settlement_at")) or None,
            "repayment_direction": row.get("repayment_direction") or ("expense" if row.get("business_type") == "borrow_in" else "income"),
            "counterparty_bank_name": row.get("counterparty_bank_name") or cls._join_list(row.get("bank_account_labels")),
            "repayment_remark": row.get("repayment_remark") or row.get("summary_text") or "",
            "interest_rate_type": row.get("interest_rate_type") or "none",
            "interest_rate_value": row.get("interest_rate_value") or "0.000000",
            "interest_paid_amount": row.get("interest_paid_amount") or "0.00",
            "loan_days": row.get("loan_days"),
            "accrued_interest": row.get("accrued_interest") or "0.00",
            "interest_paid_date": row.get("interest_paid_date"),
            "interest_payment_method": row.get("interest_payment_method") or "",
            "note": row.get("note") or "",
            "bank_row_ids": list(row.get("bank_row_ids") or []),
            "family": row.get("family") or "",
            "family_label": row.get("family_label") or "",
            "counterparty_name": row.get("counterparty_name") or "",
            "balance_amount": row.get("balance_amount") or "0.00",
            "principal_amount": principal,
            "settled_amount": settled,
            "business_type": row.get("business_type") or "",
        }

    @staticmethod
    def _row_extra_fields(extra: dict[str, object]) -> dict[str, object]:
        return {
            "interest_rate_type": extra.get("interest_rate_type") or "none",
            "interest_rate_value": extra.get("interest_rate_value") or "0.000000",
            "interest_paid_amount": extra.get("interest_paid_amount") or "0.00",
            "interest_paid_date": extra.get("interest_paid_date"),
            "interest_payment_method": extra.get("interest_payment_method") or "",
            "note": extra.get("note") or "",
        }

    @staticmethod
    def _pending_direction(row: dict[str, object]) -> str:
        business_type = str(row.get("business_type") or "")
        balance = TurnoverLedgerApiRoutes._money(row.get("balance_amount"))
        if balance == ZERO:
            return "closed"
        if business_type == "borrow_in":
            return "repayment"
        if business_type in {"borrow_out", "business_receivable"}:
            return "collection"
        return "mixed"

    @staticmethod
    def _pending_direction_label(row: dict[str, object]) -> str:
        return {
            "repayment": "待还款",
            "collection": "待收款",
            "closed": "已闭合",
            "mixed": "混合余额",
        }[TurnoverLedgerApiRoutes._pending_direction(row)]

    @staticmethod
    def _join_list(value: object) -> str:
        if not isinstance(value, list):
            return ""
        return " / ".join(str(item) for item in value if str(item).strip())

    @staticmethod
    def _date_text(value: object) -> str:
        text = str(value or "").strip()
        return text[:10] if text else ""

    @staticmethod
    def _money(value: object) -> Decimal:
        if value is None:
            return ZERO
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO
        try:
            return Decimal(text).quantize(MONEY_QUANT)
        except (InvalidOperation, ValueError):
            return ZERO

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value.quantize(MONEY_QUANT):.2f}"
