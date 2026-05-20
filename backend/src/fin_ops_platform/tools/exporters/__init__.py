from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True, slots=True)
class ExportDefinition:
    output_file: str
    source_collection: str | None
    record_type: str
    rebuildable: bool = False
    identity_fields: tuple[str, ...] = ()
    raw_note: str | None = None


def all_export_definitions() -> list[ExportDefinition]:
    from fin_ops_platform.tools.exporters.core import CORE_EXPORTS
    from fin_ops_platform.tools.exporters.ops_tax_etc import OPS_TAX_ETC_EXPORTS
    from fin_ops_platform.tools.exporters.read_models import READ_MODEL_EXPORTS
    from fin_ops_platform.tools.exporters.workbench import WORKBENCH_EXPORTS

    seen: set[str] = set()
    definitions: list[ExportDefinition] = []
    for definition in _chain(CORE_EXPORTS, WORKBENCH_EXPORTS, OPS_TAX_ETC_EXPORTS, READ_MODEL_EXPORTS):
        if definition.output_file in seen:
            raise ValueError(f"Duplicate export output file: {definition.output_file}")
        seen.add(definition.output_file)
        definitions.append(definition)
    return definitions


def _chain(*groups: Iterable[ExportDefinition]) -> Iterable[ExportDefinition]:
    for group in groups:
        yield from group
