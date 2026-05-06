import { type Dispatch, type ReactNode, type SetStateAction, useCallback } from "react";

import type { EtcImportPreviewResult } from "../features/etc/types";
import type { ImportWorkflowMode } from "../features/imports/importRoutes";
import type { ImportBatchType, ImportSessionPayload } from "../features/imports/types";
import { usePageSessionState } from "./PageSessionStateContext";

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
  etcImported: boolean;
  feedbackMessage: string | null;
  errorMessage: string | null;
  isPreviewing: boolean;
  isConfirming: boolean;
};

type PersistedImportSession = {
  sessionId: string | null;
};

const IMPORT_DRAFT_TTL_MS = 2 * 60 * 60 * 1000;

function createEmptyDraft(): ImportWorkflowDraft {
  return {
    selectedFiles: [],
    fileSelections: {},
    previewPayload: null,
    etcPreviewPayload: null,
    etcImported: false,
    feedbackMessage: null,
    errorMessage: null,
    isPreviewing: false,
    isConfirming: false,
  };
}

function supportsSessionRestore(mode: ImportWorkflowMode) {
  return mode === "bank_transaction" || mode === "invoice";
}

function persistedSessionInitialValue(): PersistedImportSession {
  return { sessionId: null };
}

function isPersistedImportSession(value: unknown): value is PersistedImportSession {
  if (!value || typeof value !== "object") {
    return false;
  }
  const payload = value as Record<string, unknown>;
  return payload.sessionId === null || typeof payload.sessionId === "string";
}

export function ImportWorkflowDraftProvider({ children }: { children: ReactNode }) {
  return children;
}

export function useImportWorkflowDraft(mode: ImportWorkflowMode) {
  const memoryDraft = usePageSessionState<ImportWorkflowDraft>({
    pageKey: `imports.${mode}`,
    stateKey: "draft.memory",
    version: 1,
    initialValue: createEmptyDraft(),
    ttlMs: IMPORT_DRAFT_TTL_MS,
    storage: "memory",
  });
  const persistedSession = usePageSessionState<PersistedImportSession>({
    pageKey: `imports.${mode}`,
    stateKey: "previewSession",
    version: 1,
    initialValue: persistedSessionInitialValue(),
    ttlMs: IMPORT_DRAFT_TTL_MS,
    storage: supportsSessionRestore(mode) ? "session" : "memory",
    validate: isPersistedImportSession,
  });

  const updateDraft = useCallback((updater: SetStateAction<ImportWorkflowDraft>) => {
    memoryDraft.setValue(updater);
  }, [memoryDraft]);

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

  const clearPersistedSession = useCallback(() => {
    persistedSession.reset();
  }, [persistedSession]);

  const resetDraft = useCallback(() => {
    memoryDraft.reset();
    persistedSession.reset();
  }, [memoryDraft, persistedSession]);

  const readPersistedSessionId = useCallback(() => (
    supportsSessionRestore(mode) ? persistedSession.value.sessionId : null
  ), [mode, persistedSession.value.sessionId]);

  const persistSessionId = useCallback((sessionId: string) => {
    if (!supportsSessionRestore(mode)) {
      return;
    }
    persistedSession.setValue({ sessionId });
  }, [mode, persistedSession]);

  return {
    draft: memoryDraft.value,
    restoreState: memoryDraft.restoreState,
    persistedSessionRestoreState: persistedSession.restoreState,
    updateDraft,
    resetDraft,
    clearPersistedSession,
    readPersistedSessionId,
    persistSessionId,
    setSelectedFiles: createSetter("selectedFiles"),
    setFileSelections: createSetter("fileSelections"),
    setPreviewPayload: createSetter("previewPayload"),
    setEtcPreviewPayload: createSetter("etcPreviewPayload"),
    setEtcImported: createSetter("etcImported"),
    setFeedbackMessage: createSetter("feedbackMessage"),
    setErrorMessage: createSetter("errorMessage"),
    setIsPreviewing: createSetter("isPreviewing"),
    setIsConfirming: createSetter("isConfirming"),
  };
}

