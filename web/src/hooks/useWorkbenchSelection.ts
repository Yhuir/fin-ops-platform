import { useCallback, useMemo, useState } from "react";

import type { WorkbenchRecord } from "../features/workbench/types";

export type WorkbenchRowState = "idle" | "selected" | "related";

export default function useWorkbenchSelection() {
  const [selectedRow, setSelectedRow] = useState<WorkbenchRecord | null>(null);
  const [detailRow, setDetailRow] = useState<WorkbenchRecord | null>(null);
  const [selectedPairedRowIds, setSelectedPairedRowIds] = useState<string[]>([]);
  const [selectedOpenRowIds, setSelectedOpenRowIds] = useState<string[]>([]);

  const selectedCaseId = useMemo(() => selectedRow?.caseId ?? null, [selectedRow]);
  const selectedRowId = selectedRow?.id ?? null;
  const selectedPairedRowIdSet = useMemo(() => new Set(selectedPairedRowIds), [selectedPairedRowIds]);
  const selectedOpenRowIdSet = useMemo(() => new Set(selectedOpenRowIds), [selectedOpenRowIds]);

  const togglePairedRowSelection = useCallback((row: WorkbenchRecord) => {
    setSelectedPairedRowIds((current) =>
      current.includes(row.id) ? current.filter((item) => item !== row.id) : [...current, row.id],
    );
  }, []);

  const toggleOpenRowSelection = useCallback((row: WorkbenchRecord) => {
    setSelectedOpenRowIds((current) =>
      current.includes(row.id) ? current.filter((item) => item !== row.id) : [...current, row.id],
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
    setSelectedPairedRowIds([]);
    setSelectedOpenRowIds([]);
  }, []);

  const clearPairedSelection = useCallback(() => {
    setSelectedPairedRowIds([]);
  }, []);

  const clearOpenSelection = useCallback(() => {
    setSelectedOpenRowIds([]);
  }, []);

  const getRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "open"): WorkbenchRowState => {
    if (zoneId === "open") {
      return selectedOpenRowIdSet.has(row.id) ? "selected" : "idle";
    }

    if (selectedPairedRowIdSet.has(row.id)) {
      return "selected";
    }

    if (selectedPairedRowIds.length === 0 && selectedRowId === row.id) {
      return "selected";
    }

    if (selectedPairedRowIds.length === 0 && selectedCaseId && row.caseId && row.caseId === selectedCaseId) {
      return "related";
    }

    return "idle";
  }, [selectedCaseId, selectedOpenRowIdSet, selectedPairedRowIdSet, selectedPairedRowIds.length, selectedRowId]);

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
