from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from fin_ops_platform.services.workbench_relation_preview_policy import (
    WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS,
    WorkbenchRelationPreviewSelectionError,
)


def scope_key_for_month(month: str | None) -> str:
    return str(month or "all").strip() or "all"


class RecordingRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def get_workbench_initial_page(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("initial", dict(kwargs)))
        return {
            "summary": {"oa_count": 1},
            "statistics": {"oa_count": 1},
            "paired": {"groups": [], "total": 0},
            "unpaired": {"groups": [], "total": 0},
        }

    def get_workbench_groups_page(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("groups", dict(kwargs)))
        return {"groups": [], "total": 0}

    def get_workbench_group_detail(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("group_detail", dict(kwargs)))
        return {"group": {"group_id": "case:1"}}

    def get_workbench_row_detail(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("row_detail", dict(kwargs)))
        return {"row": {"id": kwargs["row_id"], "type": "bank"}}

    def get_workbench_relation_preview_selection(
        self, **kwargs: object
    ) -> dict[str, object]:
        self.calls.append(("preview", dict(kwargs)))
        row_ids = list(kwargs["row_ids"])
        return {
            "selected_row_ids": row_ids,
            "selected_rows": [{"id": row_id} for row_id in row_ids],
            "context_rows": [],
            "rows": [{"id": row_id} for row_id in row_ids],
        }


class WorkbenchQueryFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = RecordingRepository()
        self.facade = WorkbenchQueryFacade(
            repository=self.repository,
            scope_key_for_month=scope_key_for_month,
        )

    def test_initial_page_reads_canonical_repository_without_runtime_status_fields(
        self,
    ) -> None:
        result = self.facade.initial_page(
            "2026-05",
            paired_query={"sort": "bank:desc"},
            unpaired_query={"search": "供应商"},
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["month"], "2026-05")
        self.assertEqual(result.payload["scope_key"], "2026-05")
        self.assertNotIn("read_model_status", result.payload)
        self.assertNotIn("read_model_version", result.payload)
        self.assertEqual(
            self.repository.calls,
            [
                (
                    "initial",
                    {
                        "scope_key": "2026-05",
                        "paired_query": {"sort": "bank:desc"},
                        "unpaired_query": {"search": "供应商"},
                    },
                )
            ],
        )

    def test_groups_forwards_server_pagination_filters_and_sort(self) -> None:
        result = self.facade.groups(
            "all",
            zone="unpaired",
            page="3",
            page_size="20",
            search="供应商",
            sort="bank:desc",
            detail_level="summary",
            column_filters={"bank": {"direction": ["支出"]}},
            time_filters={"bank": {"mode": "month", "month": "2026-05"}},
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["zone"], "unpaired")
        self.assertEqual(self.repository.calls[0][0], "groups")
        self.assertEqual(self.repository.calls[0][1]["page"], "3")
        self.assertEqual(self.repository.calls[0][1]["page_size"], "20")
        self.assertEqual(self.repository.calls[0][1]["search"], "供应商")
        self.assertEqual(self.repository.calls[0][1]["sort"], "bank:desc")

    def test_group_and_row_detail_use_page_repository(self) -> None:
        group = self.facade.group_detail(
            "all",
            zone="paired",
            group_id="case:1",
            detail_key="1",
        )
        row = self.facade.row_detail("2026-05", row_id="bank-1")

        self.assertEqual(group.status_code, HTTPStatus.OK)
        self.assertEqual(row.status_code, HTTPStatus.OK)
        self.assertEqual(
            self.repository.calls,
            [
                (
                    "group_detail",
                    {
                        "scope_key": "all",
                        "zone": "paired",
                        "group_id": "case:1",
                        "detail_key": "1",
                    },
                ),
                (
                    "row_detail",
                    {"scope_key": "2026-05", "row_id": "bank-1"},
                ),
            ],
        )

    def test_missing_repository_fails_closed_without_refresh_enqueue(self) -> None:
        facade = WorkbenchQueryFacade(
            repository=None,
            scope_key_for_month=scope_key_for_month,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "workbench_canonical_query_unavailable")
        self.assertNotIn("read_model_status", result.payload)
        self.assertNotIn("refresh_enqueued", result.payload)

    def test_relation_preview_deduplicates_selection_and_preserves_order(self) -> None:
        result = self.facade.relation_preview_selection(
            "all",
            row_ids=["bank-1", "oa-1", "bank-1"],
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(
            self.repository.calls,
            [
                (
                    "preview",
                    {
                        "scope_key": "all",
                        "row_ids": ["bank-1", "oa-1"],
                    },
                )
            ],
        )

    def test_relation_preview_rejects_empty_and_oversized_selection(self) -> None:
        empty = self.facade.relation_preview_selection("all", row_ids=[])
        oversized = self.facade.relation_preview_selection(
            "all",
            row_ids=[
                f"bank-{index}"
                for index in range(WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS + 1)
            ],
        )

        self.assertEqual(empty.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(empty.payload["error"], "relation_preview_selection_required")
        self.assertEqual(oversized.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            oversized.payload["error"],
            "relation_preview_selection_too_large",
        )
        self.assertEqual(self.repository.calls, [])

    def test_relation_preview_maps_canonical_selection_conflict_to_409(self) -> None:
        class ConflictRepository:
            @staticmethod
            def get_workbench_relation_preview_selection(
                **_kwargs: object,
            ) -> dict[str, object]:
                raise WorkbenchRelationPreviewSelectionError(
                    code="relation_preview_rows_missing",
                    message="所选工作台记录已变化，请刷新后重试。",
                )

        facade = WorkbenchQueryFacade(
            repository=ConflictRepository(),
            scope_key_for_month=scope_key_for_month,
        )

        result = facade.relation_preview_selection("all", row_ids=["bank-1"])

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["error"], "relation_preview_rows_missing")


if __name__ == "__main__":
    unittest.main()
