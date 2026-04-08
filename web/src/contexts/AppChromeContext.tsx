import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type AppChromeContextValue = {
  workbenchStatusText: string | null;
  setWorkbenchStatusText: (nextValue: string | null) => void;
};

const AppChromeContext = createContext<AppChromeContextValue | null>(null);

export function AppChromeProvider({ children }: { children: ReactNode }) {
  const [workbenchStatusText, setWorkbenchStatusText] = useState<string | null>(null);

  const value = useMemo(
    () => ({
      workbenchStatusText,
      setWorkbenchStatusText,
    }),
    [workbenchStatusText],
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
