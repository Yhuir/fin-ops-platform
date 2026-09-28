export type ExportSelection = { values: Record<string, string[]>; startDate: string; endDate: string };
export type ExportOption = { value: string; label: string; count: number };
export type ExportGroup = { field: string; label: string; options: ExportOption[] };
export type ExportSummary = { rowCount: number; groups: ExportGroup[] };
export function selectionFilters(selection: ExportSelection) {
  return Object.entries(selection.values).map(([field, values]) => ({ field, operator: 'in' as const, values }));
}
