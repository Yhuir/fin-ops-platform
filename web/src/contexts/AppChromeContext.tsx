import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type AppChromeContextValue = {
  isWorkbenchFocusMode: boolean;
  setWorkbenchFocusMode: (nextValue: boolean) => void;
};

const AppChromeContext = createContext<AppChromeContextValue | null>(null);

export function AppChromeProvider({ children }: { children: ReactNode }) {
  const [isWorkbenchFocusMode, setWorkbenchFocusMode] = useState(false);

  const value = useMemo(
    () => ({
      isWorkbenchFocusMode,
      setWorkbenchFocusMode,
    }),
    [isWorkbenchFocusMode],
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
