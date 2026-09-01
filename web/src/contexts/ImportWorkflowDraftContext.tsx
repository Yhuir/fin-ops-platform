import { type Dispatch, type SetStateAction, useCallback, useMemo, useState } from "react";

import type { EtcImportPreviewResult } from "../features/etc/types";
import type { ImportBatchType, ImportSessionPayload } from "../features/imports/types";

export type FileSelectionState = Record<
  string,
  {
    bankMappingId: string;
    bankName: string;
    bankShortName: string;
    last4: string;
    invoiceBatchType: ImportBatchType | "";
  }
>;

export type ImportWorkflowDraft = {
  selectedFiles: File[];
  fileSelections: FileSelectionState;
  previewPayload: ImportSessionPayload | null;
  etcPreviewPayload: EtcImportPreviewResult | null;
  selectedEtcTaskId: string;
  etcImported: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  isPreviewing: boolean;
  isConfirming: boolean;
};

function createEmptyDraft(): ImportWorkflowDraft {
  return {
    selectedFiles: [],
    fileSelections: {},
    previewPayload: null,
    etcPreviewPayload: null,
    selectedEtcTaskId: "",
    etcImported: false,
    feedbackMessage: null,
    errorMessage: null,
    isPreviewing: false,
    isConfirming: false,
  };
}

export function useImportWorkflowDraft() {
  const [draft, setDraft] = useState<ImportWorkflowDraft>(createEmptyDraft);

  const updateDraft = useCallback((updater: SetStateAction<ImportWorkflowDraft>) => {
    setDraft(updater);
  }, []);

  const createSetter = useCallback(<Key extends keyof ImportWorkflowDraft>(key: Key) => (
    (updater: SetStateAction<ImportWorkflowDraft[Key]>) => {
      updateDraft((current) => ({
        ...current,
        [key]: typeof updater === "function"
          ? (updater as (value: ImportWorkflowDraft[Key]) => ImportWorkflowDraft[Key])(current[key])
          : updater,
      }));
    }
  ), [updateDraft]);

  const resetDraft = useCallback(() => {
    setDraft(createEmptyDraft());
  }, []);

  const draftSetters = useMemo(() => ({
    setSelectedFiles: createSetter("selectedFiles"),
    setFileSelections: createSetter("fileSelections"),
    setPreviewPayload: createSetter("previewPayload"),
    setEtcPreviewPayload: createSetter("etcPreviewPayload"),
    setSelectedEtcTaskId: createSetter("selectedEtcTaskId"),
    setEtcImported: createSetter("etcImported"),
    setFeedbackMessage: createSetter("feedbackMessage"),
    setErrorMessage: createSetter("errorMessage"),
    setIsPreviewing: createSetter("isPreviewing"),
    setIsConfirming: createSetter("isConfirming"),
  }), [createSetter]);

  return {
    draft,
    updateDraft,
    resetDraft,
    ...draftSetters,
  };
}
