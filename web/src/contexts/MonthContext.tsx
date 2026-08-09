import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { currentBusinessMonth } from "../features/dateTime";

type MonthContextValue = {
  currentMonth: string;
  setCurrentMonth: (month: string) => void;
};

export const DEFAULT_MONTH = currentBusinessMonth();

const MonthContext = createContext<MonthContextValue | null>(null);

export function MonthProvider({ children }: { children: ReactNode }) {
  const [currentMonth, setCurrentMonth] = useState(DEFAULT_MONTH);

  const value = useMemo(
    () => ({
      currentMonth,
      setCurrentMonth,
    }),
    [currentMonth],
  );

  return <MonthContext.Provider value={value}>{children}</MonthContext.Provider>;
}

export function useMonth() {
  const context = useContext(MonthContext);
  if (!context) {
    throw new Error("useMonth must be used within MonthProvider");
  }
  return context;
}
