import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type ImportProgressTone = "info" | "loading" | "success" | "error";

export type ImportProgressState = {
  tone: ImportProgressTone;
  label: string;
};

type ImportProgressContextValue = {
  progress: ImportProgressState | null;
  setProgress: (progress: ImportProgressState | null) => void;
  clearProgress: () => void;
};

const ImportProgressContext = createContext<ImportProgressContextValue | null>(null);

export function ImportProgressProvider({ children }: { children: ReactNode }) {
  const [progress, setProgress] = useState<ImportProgressState | null>(null);
  const clearProgress = useCallback(() => {
    setProgress(null);
  }, []);

  const value = useMemo(
    () => ({
      progress,
      setProgress,
      clearProgress,
    }),
    [clearProgress, progress],
  );

  return <ImportProgressContext.Provider value={value}>{children}</ImportProgressContext.Provider>;
}

export function useImportProgress() {
  const context = useContext(ImportProgressContext);
  if (!context) {
    throw new Error("useImportProgress must be used within ImportProgressProvider");
  }
  return context;
}
