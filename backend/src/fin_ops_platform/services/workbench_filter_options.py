from __future__ import annotations

WORKBENCH_FILTER_OPTION_COLUMNS = {
    "oa": frozenset({"applicant", "projectName", "counterparty"}),
    "bank": frozenset({"counterparty", "amount", "loanRepaymentDate"}),
    "invoice": frozenset({"sellerName", "buyerName"}),
}
WORKBENCH_FILTER_OPTION_FACETS = frozenset({"column", "time_year"})
WORKBENCH_FILTER_MISSING_VALUE = "__workbench_missing__"


def normalize_workbench_filter_option_target(
    *,
    pane: str | None,
    facet: str | None,
    column: str | None,
) -> tuple[str, str, str | None]:
    normalized_pane = str(pane or "").strip()
    normalized_facet = str(facet or "column").strip()
    normalized_column = str(column or "").strip() or None
    if normalized_pane not in WORKBENCH_FILTER_OPTION_COLUMNS:
        raise ValueError("pane must be oa, bank, or invoice.")
    if normalized_facet not in WORKBENCH_FILTER_OPTION_FACETS:
        raise ValueError("facet must be column or time_year.")
    if normalized_facet == "column":
        if normalized_column not in WORKBENCH_FILTER_OPTION_COLUMNS[normalized_pane]:
            raise ValueError("column is not filterable for the selected pane.")
    else:
        normalized_column = None
    return normalized_pane, normalized_facet, normalized_column
