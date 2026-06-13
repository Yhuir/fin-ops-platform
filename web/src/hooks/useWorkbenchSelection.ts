import { useCallback, useMemo, useState } from "react";

import type { WorkbenchRecord } from "../features/workbench/types";

export type WorkbenchRowState = "idle" | "selected" | "related";

export default function useWorkbenchSelection() {
  const [selectedRow, setSelectedRow] = useState<WorkbenchRecord | null>(null);
  const [detailRow, setDetailRow] = useState<WorkbenchRecord | null>(null);
  const [selectedPairedRows, setSelectedPairedRows] = useState<WorkbenchRecord[]>([]);
  const [selectedOpenRows, setSelectedOpenRows] = useState<WorkbenchRecord[]>([]);

  const selectedCaseId = useMemo(() => selectedRow?.caseId ?? null, [selectedRow]);
  const selectedPairedRowIds = useMemo(() => selectedPairedRows.map((row) => row.id), [selectedPairedRows]);
  const selectedOpenRowIds = useMemo(() => selectedOpenRows.map((row) => row.id), [selectedOpenRows]);
  const selectedPairedRowIdSet = useMemo(() => new Set(selectedPairedRowIds), [selectedPairedRowIds]);
  const selectedOpenRowIdSet = useMemo(() => new Set(selectedOpenRowIds), [selectedOpenRowIds]);

  const togglePairedRowSelection = useCallback((row: WorkbenchRecord) => {
    setSelectedPairedRows((current) =>
      current.some((item) => item.id === row.id)
        ? current.filter((item) => item.id !== row.id)
        : [...current, row],
    );
  }, []);

  const toggleOpenRowSelection = useCallback((row: WorkbenchRecord) => {
    setSelectedOpenRows((current) =>
      current.some((item) => item.id === row.id)
        ? current.filter((item) => item.id !== row.id)
        : [...current, row],
    );
  }, []);

  const openDetail = useCallback((row: WorkbenchRecord) => {
    setSelectedRow(row);
    setDetailRow(row);
  }, []);

  const replaceDetailRow = useCallback((row: WorkbenchRecord) => {
    setSelectedRow(row);
    setDetailRow(row);
  }, []);

  const closeDetail = useCallback(() => {
    setDetailRow(null);
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedRow(null);
    setDetailRow(null);
    setSelectedPairedRows([]);
    setSelectedOpenRows([]);
  }, []);

  const clearPairedSelection = useCallback(() => {
    setSelectedPairedRows([]);
  }, []);

  const clearOpenSelection = useCallback(() => {
    setSelectedOpenRows([]);
  }, []);

  const getRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "open"): WorkbenchRowState => {
    if (zoneId === "open") {
      return selectedOpenRowIdSet.has(row.id) ? "selected" : "idle";
    }

    if (selectedPairedRowIdSet.has(row.id)) {
      return "selected";
    }

    if (selectedPairedRowIds.length === 0 && selectedCaseId && row.caseId && row.caseId === selectedCaseId) {
      return "related";
    }

    return "idle";
  }, [selectedCaseId, selectedOpenRowIdSet, selectedPairedRowIdSet, selectedPairedRowIds.length]);

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
    selectedPairedRows,
    togglePairedRowSelection,
    selectedOpenRowIds,
    selectedOpenRows,
    toggleOpenRowSelection,
  };
}
