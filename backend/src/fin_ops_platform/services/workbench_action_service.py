from __future__ import annotations

from itertools import count
from typing import Any

from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService


class WorkbenchActionService:
    def __init__(self, query_service: WorkbenchQueryService) -> None:
        self._query_service = query_service
        self._case_sequence = count(1)

    def confirm_link(self, *, month: str, row_ids: list[str], case_id: str | None = None) -> dict[str, Any]:
        if not row_ids:
            raise ValueError("row_ids is required.")

        rows = [self._validated_row(row_id, month=month) for row_id in row_ids]
        resolved_case_id = case_id or rows[0].get("case_id") or f"CASE-AUTO-{next(self._case_sequence):04d}"
        updated_rows: list[dict[str, Any]] = []

        for row in rows:
            row["_section"] = "paired"
            row["case_id"] = resolved_case_id
            relation = self._query_service.linked_relation()
            self._query_service.set_relation(row, **relation)
            row["available_actions"] = self._query_service.available_actions(row["type"], "paired")
            self._sync_relation_label(row)
            updated_rows.append(self._query_service.serialize_row(row))

        return self._result(
            action="confirm_link",
            month=month,
            updated_rows=updated_rows,
            message=f"已确认 {len(updated_rows)} 条记录关联。",
        )

    def mark_exception(
        self,
        *,
        month: str,
        row_id: str,
        exception_code: str,
        comment: str | None,
    ) -> dict[str, Any]:
        row = self._validated_row(row_id, month=month)
        row["_section"] = "open"
        self._query_service.set_relation(
            row,
            code=exception_code,
            label=comment or "待人工处理",
            tone="danger",
        )
        row["available_actions"] = self._query_service.available_actions(row["type"], "open")
        self._append_detail_note(row, comment or exception_code)
        self._sync_relation_label(row)
        return self._result(
            action="mark_exception",
            month=month,
            updated_rows=[self._query_service.serialize_row(row)],
            message="已标记异常。",
        )

    def cancel_link(self, *, month: str, row_id: str, comment: str | None = None) -> dict[str, Any]:
        row = self._validated_row(row_id, month=month)
        row["_section"] = "open"
        pending = self._query_service.pending_relation(row["type"])
        if comment:
            pending["label"] = "取消关联，待重新处理"
        self._query_service.set_relation(row, **pending)
        row["available_actions"] = self._query_service.available_actions(row["type"], "open")
        self._append_detail_note(row, comment or "已取消关联")
        self._sync_relation_label(row)
        return self._result(
            action="cancel_link",
            month=month,
            updated_rows=[self._query_service.serialize_row(row)],
            message="已取消关联并回退为待处理。",
        )

    def update_bank_exception(
        self,
        *,
        month: str,
        row_id: str,
        relation_code: str,
        relation_label: str,
        comment: str | None,
    ) -> dict[str, Any]:
        row = self._validated_row(row_id, month=month)
        if row["type"] != "bank":
            raise ValueError("update_bank_exception only supports bank rows.")

        row["_section"] = "open"
        self._query_service.set_relation(
            row,
            code=relation_code,
            label=relation_label,
            tone="danger",
        )
        row["available_actions"] = self._query_service.available_actions("bank", "open")
        self._append_detail_note(row, comment or relation_label)
        self._sync_relation_label(row)
        return self._result(
            action="update_bank_exception",
            month=month,
            updated_rows=[self._query_service.serialize_row(row)],
            message="已更新银行异常分类。",
        )

    def _validated_row(self, row_id: str, *, month: str) -> dict[str, Any]:
        row = self._query_service.get_row_record(row_id)
        if month != "all" and row["_month"] != month:
            raise ValueError("row month does not match request month.")
        return row

    def _append_detail_note(self, row: dict[str, Any], note: str) -> None:
        row["_detail_fields"]["备注"] = note
        summary_fields = row["_summary_fields"]
        if "备注" in summary_fields:
            summary_fields["备注"] = note

    def _sync_relation_label(self, row: dict[str, Any]) -> None:
        relation = row[self._query_service.relation_field_name(row["type"])]
        summary_fields = row["_summary_fields"]
        if row["type"] == "oa":
            summary_fields["OA和流水关联情况"] = relation["label"]
        elif row["type"] == "bank":
            summary_fields["和发票关联情况"] = relation["label"]

    @staticmethod
    def _result(
        *,
        action: str,
        month: str,
        updated_rows: list[dict[str, Any]],
        message: str,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "action": action,
            "month": month,
            "affected_row_ids": [row["id"] for row in updated_rows],
            "updated_rows": updated_rows,
            "message": message,
        }
