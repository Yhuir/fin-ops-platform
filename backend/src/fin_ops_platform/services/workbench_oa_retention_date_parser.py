from __future__ import annotations

from datetime import datetime


class WorkbenchOaRetentionDateParser:
    """Parses OA retention dates and evaluates retention date predicates."""

    @staticmethod
    def parse(value: object) -> datetime | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        if len(text) < 10:
            return None
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None

    @classmethod
    def row_is_on_or_after(cls, row: dict[str, object], cutoff_date: datetime, *, row_type: str) -> bool:
        for value in cls.row_date_candidates(row, row_type=row_type):
            parsed = cls.parse(value)
            if parsed is not None and parsed >= cutoff_date:
                return True
        return False

    @classmethod
    def row_has_parseable_retention_date(cls, row: dict[str, object], *, row_type: str) -> bool:
        return any(cls.parse(value) is not None for value in cls.row_date_candidates(row, row_type=row_type))

    @staticmethod
    def row_date_candidates(row: dict[str, object], *, row_type: str) -> list[object]:
        candidates: list[object] = []
        if row_type == "oa":
            candidates.extend([row.get("application_date"), row.get("apply_date")])
            for fields_key in ("summary_fields", "detail_fields"):
                fields = row.get(fields_key)
                if isinstance(fields, dict):
                    candidates.extend(
                        fields.get(key)
                        for key in ("申请日期", "报销日期", "审批完成时间", "单据日期", "日期")
                    )
        elif row_type == "bank":
            candidates.extend([row.get("trade_time"), row.get("pay_receive_time"), row.get("txn_date")])
            fields = row.get("summary_fields")
            if isinstance(fields, dict):
                candidates.extend(fields.get(key) for key in ("交易时间", "支付/收款时间", "记账日期", "日期"))
            detail_fields = row.get("detail_fields")
            if isinstance(detail_fields, dict):
                candidates.extend(detail_fields.get(key) for key in ("交易时间", "支付/收款时间", "记账日期", "日期"))
        return candidates
