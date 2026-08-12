import { useCallback, useMemo, useState } from "react";

import { workbenchRowIdentityKey } from "../features/workbench/selectionModel";
import type { WorkbenchRecord } from "../features/workbench/types";

export type WorkbenchRowState = "idle" | "selected" | "related";

export default function useWorkbenchSelection() {
  const [selectedRow, setSelectedRow] = useState<WorkbenchRecord | null>(null);
  const [detailRow, setDetailRow] = useState<WorkbenchRecord | null>(null);
  const [selectedPairedRows, setSelectedPairedRows] = useState<WorkbenchRecord[]>([]);
  const [selectedOpenRows, setSelectedOpenRows] = useState<WorkbenchRecord[]>([]);

  const selectedCaseId = useMemo(() => selectedRow?.caseId ?? null, [selectedRow]);
  const selectedPairedRowIdentityKeys = useMemo(
    () => selectedPairedRows.map(workbenchRowIdentityKey),
    [selectedPairedRows],
  );
  const selectedOpenRowIdentityKeys = useMemo(
    () => selectedOpenRows.map(workbenchRowIdentityKey),
    [selectedOpenRows],
  );
  const selectedPairedRowIdentityKeySet = useMemo(
    () => new Set(selectedPairedRowIdentityKeys),
    [selectedPairedRowIdentityKeys],
  );
  const selectedOpenRowIdentityKeySet = useMemo(
    () => new Set(selectedOpenRowIdentityKeys),
    [selectedOpenRowIdentityKeys],
  );

  const togglePairedRowSelection = useCallback((row: WorkbenchRecord) => {
    const identityKey = workbenchRowIdentityKey(row);
    setSelectedPairedRows((current) => {
      const isSelected = current.some((item) => workbenchRowIdentityKey(item) === identityKey);
      return isSelected
        ? current.filter((item) => workbenchRowIdentityKey(item) !== identityKey)
        : [...current, row];
    });
  }, []);

  const toggleOpenRowSelection = useCallback((row: WorkbenchRecord) => {
    const identityKey = workbenchRowIdentityKey(row);
    setSelectedOpenRows((current) => {
      const isSelected = current.some((item) => workbenchRowIdentityKey(item) === identityKey);
      return isSelected
        ? current.filter((item) => workbenchRowIdentityKey(item) !== identityKey)
        : [...current, row];
    });
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

  const getRowState = useCallback((row: WorkbenchRecord, zoneId: "paired" | "unpaired"): WorkbenchRowState => {
    const identityKey = workbenchRowIdentityKey(row);
    if (zoneId === "unpaired") {
      return selectedOpenRowIdentityKeySet.has(identityKey) ? "selected" : "idle";
    }

    if (selectedPairedRowIdentityKeySet.has(identityKey)) {
      return "selected";
    }

    if (selectedPairedRowIdentityKeys.length === 0 && selectedCaseId && row.caseId && row.caseId === selectedCaseId) {
      return "related";
    }

    return "idle";
  }, [
    selectedCaseId,
    selectedOpenRowIdentityKeySet,
    selectedPairedRowIdentityKeySet,
    selectedPairedRowIdentityKeys.length,
  ]);

  return {
    detailRow,
    getRowState,
    openDetail,
    replaceDetailRow,
    closeDetail,
    clearSelection,
    clearPairedSelection,
    clearOpenSelection,
    selectedPairedRows,
    togglePairedRowSelection,
    selectedOpenRows,
    toggleOpenRowSelection,
  };
}
