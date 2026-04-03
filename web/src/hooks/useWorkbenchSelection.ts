import { useMemo, useState } from "react";

import type { WorkbenchRecord } from "../features/workbench/types";

export type WorkbenchRowState = "idle" | "selected" | "related";

export default function useWorkbenchSelection() {
  const [selectedRow, setSelectedRow] = useState<WorkbenchRecord | null>(null);
  const [detailRow, setDetailRow] = useState<WorkbenchRecord | null>(null);
  const [selectedPairedRowIds, setSelectedPairedRowIds] = useState<string[]>([]);
  const [selectedOpenRowIds, setSelectedOpenRowIds] = useState<string[]>([]);

  const selectedCaseId = useMemo(() => selectedRow?.caseId ?? null, [selectedRow]);

  const togglePairedRowSelection = (row: WorkbenchRecord) => {
    setSelectedPairedRowIds((current) =>
      current.includes(row.id) ? current.filter((item) => item !== row.id) : [...current, row.id],
    );
  };

  const toggleOpenRowSelection = (row: WorkbenchRecord) => {
    setSelectedOpenRowIds((current) =>
      current.includes(row.id) ? current.filter((item) => item !== row.id) : [...current, row.id],
    );
  };

  const openDetail = (row: WorkbenchRecord) => {
    setSelectedRow(row);
    setDetailRow(row);
  };

  const replaceDetailRow = (row: WorkbenchRecord) => {
    setSelectedRow(row);
    setDetailRow(row);
  };

  const closeDetail = () => {
    setDetailRow(null);
  };

  const clearSelection = () => {
    setSelectedRow(null);
    setDetailRow(null);
    setSelectedPairedRowIds([]);
    setSelectedOpenRowIds([]);
  };

  const clearPairedSelection = () => {
    setSelectedPairedRowIds([]);
  };

  const clearOpenSelection = () => {
    setSelectedOpenRowIds([]);
  };

  const getRowState = (row: WorkbenchRecord, zoneId: "paired" | "open"): WorkbenchRowState => {
    if (zoneId === "open") {
      return selectedOpenRowIds.includes(row.id) ? "selected" : "idle";
    }

    if (selectedPairedRowIds.includes(row.id)) {
      return "selected";
    }

    if (selectedPairedRowIds.length === 0 && selectedRow?.id === row.id) {
      return "selected";
    }

    if (selectedPairedRowIds.length === 0 && selectedCaseId && row.caseId && row.caseId === selectedCaseId) {
      return "related";
    }

    return "idle";
  };

  return {
    detailRow,
    getRowState,
    openDetail,
    replaceDetailRow,
    closeDetail,
    clearSelection,
    clearPairedSelection,
    clearOpenSelection,
    selectedPairedRowIds,
    togglePairedRowSelection,
    selectedOpenRowIds,
    toggleOpenRowSelection,
  };
}
