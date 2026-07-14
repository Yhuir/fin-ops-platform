from __future__ import annotations

from typing import Callable


class WorkbenchOaRawPayloadSignalMonthHelper:
    """Extracts OA attachment signals and source months from raw Workbench payloads."""

    def __init__(
        self,
        *,
        is_month_prefix: Callable[[str], bool],
    ) -> None:
        self._is_month_prefix = is_month_prefix

    def months_from_raw_payload(self, payload: dict[str, object]) -> set[str]:
        months: set[str] = set()
        for section_name in ("paired", "unpaired"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            for row in list(section_payload.get("oa") or []):
                if isinstance(row, dict):
                    month = self.first_month_from_oa_row(row)
                    if month:
                        months.add(month)
        return months

    @staticmethod
    def has_oa_attachment_invoice_signal(payload: dict[str, object]) -> bool:
        for section_name in ("paired", "unpaired"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            for row in list(section_payload.get("oa") or []):
                if not isinstance(row, dict):
                    continue
                tags = {str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()}
                if "OA附件" in tags:
                    return True
                for fields_key in ("detail_fields", "summary_fields"):
                    fields = row.get(fields_key)
                    if not isinstance(fields, dict):
                        continue
                    for key in ("附件发票数量", "附件证据数量", "附件发票明细"):
                        value = str(fields.get(key) or "").strip()
                        if value and value not in {"0", "0 张", "—", "--"}:
                            return True
        return False

    def first_month_from_oa_row(self, row: dict[str, object]) -> str | None:
        candidates: list[object] = [
            row.get("month"),
            row.get("application_date"),
            row.get("apply_date"),
        ]
        for fields_key in ("detail_fields", "summary_fields"):
            fields = row.get(fields_key)
            if isinstance(fields, dict):
                candidates.extend(
                    fields.get(key)
                    for key in ("申请日期", "报销日期", "审批完成时间", "单据日期", "日期")
                )
        for candidate in candidates:
            text = str(candidate or "").strip()
            if len(text) >= 7 and self._is_month_prefix(text[:7]):
                return text[:7]
        return None
