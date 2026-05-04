import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { ImportWorkflowMode } from "../features/imports/importRoutes";

export type WorkbenchHeaderIntent = { type: "open_search" };

export type WorkbenchRouteState = {
  workbenchHeaderIntent?: WorkbenchHeaderIntent;
} | null;

export type WorkbenchHeaderActions = {
  canMutateData: boolean;
  onOpenImport: (mode: ImportWorkflowMode) => void;
  onOpenSearch: () => void;
  onOpenSettings: () => void;
};

export type WorkbenchShellStatus = {
  level: "ok" | "pending" | "error";
  reason: string;
};

type AppChromeContextValue = {
  shellHeaderMounted: boolean;
  setShellHeaderMounted: (nextValue: boolean) => void;
  setWorkbenchHeaderActions: (nextValue: WorkbenchHeaderActions | null) => void;
  workbenchStatus: WorkbenchShellStatus | null;
  workbenchHeaderActions: WorkbenchHeaderActions | null;
  setWorkbenchStatus: (nextValue: WorkbenchShellStatus | null) => void;
};

const AppChromeContext = createContext<AppChromeContextValue | null>(null);

export function AppChromeProvider(
  { children, initialShellHeaderMounted = false }: { children: ReactNode; initialShellHeaderMounted?: boolean },
) {
  const [shellHeaderMounted, setShellHeaderMounted] = useState(initialShellHeaderMounted);
  const [workbenchStatus, setWorkbenchStatus] = useState<WorkbenchShellStatus | null>(null);
  const [workbenchHeaderActions, setWorkbenchHeaderActions] = useState<WorkbenchHeaderActions | null>(null);

  const value = useMemo(
    () => ({
      shellHeaderMounted,
      setShellHeaderMounted,
      setWorkbenchHeaderActions,
      workbenchStatus,
      workbenchHeaderActions,
      setWorkbenchStatus,
    }),
    [shellHeaderMounted, workbenchHeaderActions, workbenchStatus],
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
