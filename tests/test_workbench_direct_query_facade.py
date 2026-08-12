from __future__ import annotations

from http import HTTPStatus

import pytest

from fin_ops_platform.services.workbench_direct_query_errors import (
    WorkbenchDirectQueryUnavailable,
    is_workbench_data_integrity_query_error,
    is_transient_postgres_query_error,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade


class _Repository:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error

    def get_workbench_groups_page(self, **_query: object) -> dict[str, object]:
        if self.error is not None:
            raise self.error
        return {
            "groups": [],
            "total": 0,
            "row_counts": {"oa": 0, "bank": 0, "invoice": 0, "rows": 0},
            "page_size": 50,
            "has_more": False,
            "next_cursor": None,
        }


class _SqlstateError(RuntimeError):
    def __init__(self, sqlstate: str) -> None:
        super().__init__("database failure")
        self.sqlstate = sqlstate


class _SelectionRepository:
    def __init__(self) -> None:
        self.query: dict[str, object] = {}

    def get_workbench_relation_preview_selection(
        self, **query: object
    ) -> dict[str, object]:
        self.query = query
        return {
            "selected_row_ids": list(query["row_ids"]),
            "selected_row_types": list(query["row_types"]),
        }


def test_direct_facade_returns_only_business_payload_without_runtime_fields() -> None:
    result = WorkbenchQueryFacade(repository=_Repository()).groups(
        "2026-07",
        zone="unpaired",
        cursor=None,
        page_size=50,
    )

    assert result.status_code == HTTPStatus.OK
    assert set(result.payload) == {
        "groups",
        "total",
        "row_counts",
        "page_size",
        "has_more",
        "next_cursor",
    }


def test_direct_facade_maps_known_query_unavailable_to_503_without_partial_payload() -> None:
    result = WorkbenchQueryFacade(
        repository=_Repository(error=WorkbenchDirectQueryUnavailable("timeout"))
    ).groups("all", zone="paired")

    assert result.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert result.payload == {
        "error": "workbench_query_unavailable",
        "message": "工作台查询暂时不可用，请稍后重试。",
        "scope_key": "all",
    }


def test_direct_facade_does_not_hide_unexpected_repository_errors() -> None:
    facade = WorkbenchQueryFacade(repository=_Repository(error=RuntimeError("bug")))

    with pytest.raises(RuntimeError, match="bug"):
        facade.groups("all", zone="paired")


@pytest.mark.parametrize("sqlstate", ["57014", "08006", "57P03", "53300"])
def test_postgres_transient_classifier_uses_sqlstate(sqlstate: str) -> None:
    assert is_transient_postgres_query_error(_SqlstateError(sqlstate)) is True


def test_postgres_transient_classifier_rejects_contract_and_integrity_errors() -> None:
    assert is_transient_postgres_query_error(_SqlstateError("23505")) is False
    assert is_transient_postgres_query_error(ValueError("bad cursor")) is False


def test_direct_integrity_classifier_recognizes_fail_closed_sql_guard() -> None:
    assert is_workbench_data_integrity_query_error(_SqlstateError("22012")) is True
    assert is_workbench_data_integrity_query_error(_SqlstateError("23505")) is False


def test_relation_preview_preserves_ordered_typed_collision_selection() -> None:
    selection = _SelectionRepository()
    result = WorkbenchQueryFacade(
        repository=_Repository(),
        selection_repository=selection,
    ).relation_preview_selection(
        "2026-07",
        row_ids=["same-id", "same-id"],
        row_types=["bank", "invoice"],
    )

    assert result.status_code == HTTPStatus.OK
    assert selection.query["row_ids"] == ["same-id", "same-id"]
    assert selection.query["row_types"] == ["bank", "invoice"]


@pytest.mark.parametrize(
    ("row_ids", "row_types", "message"),
    [
        (["row-1"], None, "row_types is required"),
        (["row-1", "row-2"], ["bank"], "same length"),
        (["same-id", "same-id"], ["bank", "bank"], "duplicate typed row"),
    ],
)
def test_relation_preview_rejects_missing_misaligned_or_duplicate_typed_identity(
    row_ids: list[str],
    row_types: list[str] | None,
    message: str,
) -> None:
    result = WorkbenchQueryFacade(
        repository=_Repository(),
        selection_repository=_SelectionRepository(),
    ).relation_preview_selection(
        "2026-07",
        row_ids=row_ids,
        row_types=row_types,
    )

    assert result.status_code == HTTPStatus.BAD_REQUEST
    assert message in str(result.payload["message"])
