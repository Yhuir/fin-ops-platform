from __future__ import annotations

from typing import Any

import pytest

from fin_ops_platform.services.postgres_repositories.workbench_page_selection import (
    PostgresWorkbenchPageSelectionRepository,
)
from fin_ops_platform.services.workbench_relation_preview_policy import (
    WorkbenchRelationPreviewSelectionError,
)
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


class _Connection:
    def __init__(
        self,
        rows: list[dict[str, Any]],
        *,
        responses: list[list[dict[str, Any]]] | None = None,
    ) -> None:
        self.rows = rows
        self.responses = list(responses or [])
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        self.calls.append((" ".join(sql.split()), params))
        if self.responses:
            return list(self.responses.pop(0))
        return list(self.rows)


def _descriptor(
    *,
    positions: list[int],
    row_types: list[str],
    row_ids: list[str],
) -> dict[str, Any]:
    return {
        "internal_key": "row:bank:same-id",
        "detail_key": "same-id",
        "group_kind": "unpaired",
        "zone": "unpaired",
        "member_ids": ["same-id"],
        "member_types": ["bank"],
        "selected_positions": positions,
        "selected_row_types": row_types,
        "selected_row_ids": row_ids,
        "selected_source_kinds": row_types,
    }


def _source(position: int, row_type: str, row_id: str) -> dict[str, Any]:
    return {
        "position": position,
        "row_type": row_type,
        "row_id": row_id,
        "source_kind": "bank_transaction" if row_type == "bank" else row_type,
        "external_etc_batch_id": None,
        "scope_month": "2026-07-01",
        "updated_at": "2026-07-01T00:00:00+00:00",
    }


def test_selection_sql_uses_typed_ordinality_and_preserves_request_order() -> None:
    descriptors = [
            _descriptor(
                positions=[2],
                row_types=["invoice"],
                row_ids=["invoice-1"],
            ),
            _descriptor(
                positions=[1],
                row_types=["bank"],
                row_ids=["bank-1"],
            ),
        ]
    connection = _Connection(
        [],
        responses=[
            [_source(1, "bank", "bank-1"), _source(2, "invoice", "invoice-1")],
            descriptors,
        ],
    )
    repository = PostgresWorkbenchPageSelectionRepository(
        connection, tenant_id="test-tenant"
    )

    descriptors = repository._selection_descriptors(
        scope_key="2026-07",
        identities=[("bank", "bank-1"), ("invoice", "invoice-1")],
    )
    matches = repository._validated_matches(
        identities=[("bank", "bank-1"), ("invoice", "invoice-1")],
        descriptors=descriptors,
    )

    assert matches == [("bank", "bank-1"), ("invoice", "invoice-1")]
    source_sql, source_params = connection.calls[0]
    descriptor_sql, descriptor_params = connection.calls[1]
    assert "unnest(%s::text[], %s::text[]) with ordinality" in source_sql.lower()
    assert "canonical_groups" not in source_sql.lower()
    assert "canonical_groups" not in descriptor_sql.lower()
    assert "join selected_sources source" in descriptor_sql.lower()
    assert source_params[:2] == (["bank", "invoice"], ["bank-1", "invoice-1"])
    assert descriptor_params[0] == [1, 2]
    assert descriptor_params[1:3] == (["bank", "invoice"], ["bank-1", "invoice-1"])


def test_untyped_same_text_id_across_panes_fails_closed() -> None:
    with pytest.raises(WorkbenchRelationPreviewSelectionError, match="不一致"):
        PostgresWorkbenchPageSelectionRepository._validated_matches(
            identities=[("", "same-id")],
            descriptors=[
                _descriptor(
                    positions=[1, 1],
                    row_types=["bank", "invoice"],
                    row_ids=["same-id", "same-id"],
                )
            ],
        )


def test_transaction_revalidation_requires_row_types_and_maps_drift_to_conflict() -> None:
    repository = PostgresWorkbenchPageSelectionRepository(
        _Connection([]), tenant_id="test-tenant"
    )

    with pytest.raises(ValueError, match="align"):
        repository.validate_workbench_relation_selection_in_current_transaction(
            scope_key="2026-07",
            row_ids=["bank-1"],
            row_types=[],
        )
    with pytest.raises(WorkbenchWriteConflict) as caught:
        repository.validate_workbench_relation_selection_in_current_transaction(
            scope_key="2026-07",
            row_ids=["bank-1"],
            row_types=["bank"],
        )
    assert caught.value.reason == "canonical_selection_changed"


def test_completed_pending_oa_resolution_is_narrow_and_fails_closed() -> None:
    connection = _Connection([])
    repository = PostgresWorkbenchPageSelectionRepository(
        connection, tenant_id="test-tenant"
    )

    with pytest.raises(ValueError, match="missing"):
        repository._resolve_source_descriptors(
            scope_key="2026-07",
            row_ids=["oa-duplicate"],
            row_types=["oa"],
        )

    sql = connection.calls[0][0].lower()
    assert "oa_pending_payment_admissions" in sql
    assert "oa.row_id = requested.row_id" in sql
    assert "admission.oa_id = requested.row_id" in sql
    assert "canonical_groups" not in sql
