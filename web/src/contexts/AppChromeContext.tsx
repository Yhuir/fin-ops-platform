import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { WorkbenchImportMode } from "../components/workbench/WorkbenchImportModal";

export type WorkbenchHeaderIntent =
  | { type: "open_search" }
  | { type: "open_import"; mode: WorkbenchImportMode };

export type WorkbenchRouteState = {
  workbenchHeaderIntent?: WorkbenchHeaderIntent;
} | null;

export type WorkbenchHeaderActions = {
  canMutateData: boolean;
  onOpenImport: (mode: WorkbenchImportMode) => void;
  onOpenSearch: () => void;
  onOpenSettings: () => void;
};

type AppChromeContextValue = {
  shellHeaderMounted: boolean;
  setShellHeaderMounted: (nextValue: boolean) => void;
  setWorkbenchHeaderActions: (nextValue: WorkbenchHeaderActions | null) => void;
  workbenchStatusText: string | null;
  workbenchHeaderActions: WorkbenchHeaderActions | null;
  setWorkbenchStatusText: (nextValue: string | null) => void;
};

const AppChromeContext = createContext<AppChromeContextValue | null>(null);

export function AppChromeProvider(
  { children, initialShellHeaderMounted = false }: { children: ReactNode; initialShellHeaderMounted?: boolean },
) {
  const [shellHeaderMounted, setShellHeaderMounted] = useState(initialShellHeaderMounted);
  const [workbenchStatusText, setWorkbenchStatusText] = useState<string | null>(null);
  const [workbenchHeaderActions, setWorkbenchHeaderActions] = useState<WorkbenchHeaderActions | null>(null);

  const value = useMemo(
    () => ({
      shellHeaderMounted,
      setShellHeaderMounted,
      setWorkbenchHeaderActions,
      workbenchStatusText,
      workbenchHeaderActions,
      setWorkbenchStatusText,
    }),
    [shellHeaderMounted, workbenchHeaderActions, workbenchStatusText],
  );

  return <AppChromeContext.Provider value={value}>{children}</AppChromeContext.Provider>;
}

export function useAppChrome() {
  const context = useContext(AppChromeContext);
  if (!context) {
    throw new Error("useAppChrome must be used within AppChromeProvider");
  }
  return context;
}
