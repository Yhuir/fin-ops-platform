from __future__ import annotations

from fin_ops_platform.tools.exporters import ExportDefinition


READ_MODEL_EXPORTS: tuple[ExportDefinition, ...] = (
    ExportDefinition(
        "workbench_read_models.ndjson",
        "workbench_read_models",
        "workbench_read_model",
        rebuildable=True,
        identity_fields=("id", "scope_key", "scope_month"),
    ),
    ExportDefinition(
        "workbench_candidate_matches.ndjson",
        "workbench_candidate_matches",
        "workbench_candidate_match",
        rebuildable=True,
        identity_fields=("id", "candidate_key"),
    ),
    ExportDefinition(
        "cost_statistics_read_models.ndjson",
        "cost_statistics_read_models",
        "cost_statistics_read_model",
        rebuildable=True,
        identity_fields=("id", "scope_key", "scope_month"),
    ),
    ExportDefinition(
        "tax_offset_read_models.ndjson",
        "tax_offset_read_models",
        "tax_offset_read_model",
        rebuildable=True,
        identity_fields=("id", "scope_key", "scope_month"),
    ),
)
